"""Send the report's model calls through the Message Batches API (half price) instead of one by one.

Every call of every stage goes through `AgentRunner._stream`. In the backtest a runner hands that call to a
`BatchQueue` instead: the queue collects the calls of all cases running at once and, once no new call has come
in for `quiet_s` seconds, sends them as one batch, waits for it, and gives each caller its message. Because the
cases run side by side, each stage's calls for all of them land in the same batch, so the cached instructions
are shared across cases. Nothing in the report code changes.

Every answered request is written to a journal (JSONL, keyed by a hash of the exact request). A request already
in the journal is answered from it at no cost, so a run that stops can be started again without paying twice.

Money:
  - usage is priced at half the standard rate (`PRICES`), cache writes at 2x input for the one-hour lifetime and
    1.25x for five minutes, cache reads at 0.1x, all halved;
  - before a batch is sent its cost is estimated from its size; a batch estimated over `max_batch_usd` is not
    sent (the user asks to be asked before any single batch over $20);
  - `cap_usd` is the total the whole backtest may spend: `spent_before` (what earlier runs paid, `journal_spend`
    of the journal) plus this queue's spend plus batches in flight plus the estimate of everything about to be
    sent. A flush that splits into several batches is checked as a whole before any of them is sent; once it
    would pass the cap nothing more is sent and every waiting call fails with `SpendCapReachedError`.
A request the API rejects for the account (credit balance, spend or rate limit) stops the queue: no retry loops.
The other answers of that batch are still journaled and its ledger row written first; when one of several batches
sent together fails, the others run to their end and journal their answers before the queue stops.

Reading a batch's status or results is retried with a growing wait (`retry_tries`, `backoff_s` up to
`backoff_max_s`) when it fails for a reason that may pass; that never stops the queue on its own. Each batch sent
is noted in `inflight.jsonl` next to the journal (batch id, API version, custom_id -> key, tags) before it is
waited on, and `recover()` (awaited by the runner at start) journals the paid answers of an earlier run's batches
that were never read back. An earlier batch is never dropped from the cap: one still running is counted at its
estimate and watched, and a call for one of its requests waits for its answer instead of paying for it again; one
that cannot be read is counted at its estimate; one whose requests a later run paid for again is counted at its
cost. A batch is created with the SDK's own retries off (`max_retries=0`), so a create that timed out cannot make
a second paid batch; a create that failed in a way that may still have made the batch counts its estimate.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import hashlib
import json
import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, TypeVar

import anthropic
from anthropic import AsyncAnthropic
from anthropic.types import Message

log = logging.getLogger(__name__)

# $ per million tokens, standard price: input, output
PRICES = {
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-opus-5-5": (4.00, 20.00),
}
# cache reads as a share of the input price: 0.1 unless listed (Opus 5.5 reads its cache at $0.20, 0.05x)
CACHE_READ_SHARE = {"claude-opus-5-5": 0.05}
BATCH_DISCOUNT = 0.5
CASE: contextvars.ContextVar[str] = contextvars.ContextVar("backtest_case", default="none")
RUN: contextvars.ContextVar[str] = contextvars.ContextVar("backtest_run", default="none")
STAGE: contextvars.ContextVar[str] = contextvars.ContextVar("backtest_stage", default="unknown")
ACCOUNT_ERRORS = ("credit balance", "spend limit", "rate_limit", "billing", "usage limit", "hit your")


class SpendCapReachedError(RuntimeError):
    pass


class BatchTooLargeError(RuntimeError):
    pass


class QueueStoppedError(RuntimeError):
    pass


def price_for(model: str) -> tuple[float, float]:
    for name, p in PRICES.items():
        if model.startswith(name):
            return p
    raise KeyError(f"no price on file for {model!r}")


def cache_read_share(model: str) -> float:
    for name, share in CACHE_READ_SHARE.items():
        if model.startswith(name):
            return share
    return 0.1


def usage_cost(model: str, u: Any, *, batch: bool = True) -> float:
    pin, pout = price_for(model)

    def as_dict(obj: Any) -> dict[str, Any]:
        if obj is None:
            return {}
        return dict(obj) if isinstance(obj, dict) else dict(obj.model_dump())

    d = as_dict(u)
    c = as_dict(d.get("cache_creation"))

    def get(k: str) -> int:
        return int(d.get(k) or 0)

    def cget(k: str) -> int:
        return int(c.get(k) or 0)

    w1h, w5 = cget("ephemeral_1h_input_tokens"), cget("ephemeral_5m_input_tokens")
    if not (w1h or w5):
        w5 = get("cache_creation_input_tokens")
    cost = (
        get("input_tokens") * pin
        + w5 * pin * 1.25
        + w1h * pin * 2.0
        + get("cache_read_input_tokens") * pin * cache_read_share(model)
        + get("output_tokens") * pout
    ) / 1e6
    return cost * (BATCH_DISCOUNT if batch else 1.0)


def _plain(obj: Any) -> Any:
    """A content block of an earlier answer as the next request sends it, in one canonical form: the same block
    gives the same dict whether it was parsed from the API's answer or rebuilt from the journal (the SDK marks
    different fields as set in the two cases, which changed the request's hash and broke replay)."""
    kind = getattr(obj, "type", None)
    if kind == "text":
        return {"type": "text", "text": obj.text}
    if kind == "tool_use":
        return {"type": "tool_use", "id": obj.id, "name": obj.name, "input": obj.input}
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", exclude_none=True)
    raise TypeError(f"not serialisable: {type(obj)}")


def plain_params(params: dict[str, Any]) -> dict[str, Any]:
    """The request as plain JSON (assistant turns hold the SDK's content block objects), with every prompt cache
    marker given the one-hour lifetime, so a case's later batch still reads what an earlier one wrote."""
    p = json.loads(json.dumps(params, default=_plain))

    def one_hour(node: Any) -> None:
        if isinstance(node, dict):
            cc = node.get("cache_control")
            if isinstance(cc, dict) and cc.get("type") == "ephemeral":
                cc["ttl"] = "1h"
            for v in node.values():
                one_hour(v)
        elif isinstance(node, list):
            for v in node:
                one_hour(v)

    one_hour(p)
    assert isinstance(p, dict)
    # The SDK's way to send a temperature on the API version that still takes one (app.agents.runner
    # .sampling_params): the value in the body and the version in a header. A batch request has neither field;
    # the value goes in the request and the version on the batch (requests are batched by version).
    version = (p.pop("extra_headers", None) or {}).get("anthropic-version")
    p.update(p.pop("extra_body", None) or {})
    if version:
        p[VERSION_KEY] = version
    return p


VERSION_KEY = "_api_version"  # kept in the request (and its key) until it is sent; never sent as a field


def request_key(params: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def estimate_usd(params: dict[str, Any]) -> float:
    """A rough ceiling for one request: every input character at 3.5 per token, uncached, and half of max_tokens
    of output (the measured runs used well under that), at batch prices."""
    pin, pout = price_for(params["model"])
    chars = len(json.dumps({k: params.get(k) for k in ("system", "messages", "tools")}))
    out = min(int(params.get("max_tokens", 4096)), 16000) * 0.5
    return (chars / 3.5 * pin + out * pout) / 1e6 * BATCH_DISCOUNT


@dataclass
class _Pending:
    key: str
    params: dict[str, Any]
    tag: dict[str, str]
    future: asyncio.Future[Message]
    attempts: int = 0


@dataclass
class Ledger:
    by: dict[tuple[str, str, str], dict[str, float]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(float))
    )
    batches: list[dict[str, Any]] = field(default_factory=list)

    def add(self, tag: dict[str, str], model: str, u: Any) -> float:
        cost = usage_cost(model, u)
        row = self.by[(tag["case"], tag["run"], tag["stage"])]
        d = u if isinstance(u, dict) else u.model_dump()
        row["calls"] += 1
        row["cost_usd"] += cost
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            row[k] += d.get(k) or 0
        return cost

    @property
    def total(self) -> float:
        return sum(r["cost_usd"] for r in self.by.values())


def journal_spend(journal: Path) -> float:
    """What the answers in a journal cost, at batch prices: the spend of every earlier run of the backtest, so a
    queue can be given it (`spent_before`) and keep the cap a total for the whole backtest."""
    if not journal.exists():
        return 0.0
    total = 0.0
    for line in journal.read_text().splitlines():
        if not line.strip():
            continue
        msg = json.loads(line).get("message") or {}
        if msg.get("model") and msg.get("usage") is not None:
            total += usage_cost(msg["model"], msg["usage"])
    return total


def _transient(exc: BaseException) -> bool:
    """Whether reading a batch's status or results may work if asked again: a dropped connection, a timeout, an
    overloaded or failing server, a rate limit. A refusal (bad request, auth, not found) is not."""
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code >= 500 or exc.status_code in (408, 409, 429)
    if isinstance(exc, anthropic.APIConnectionError | OSError | TimeoutError):
        return True
    return type(exc).__module__.split(".")[0] in ("httpx", "httpx2", "httpcore")


def _maybe_created(exc: BaseException) -> bool:
    """Whether a create that raised may still have made (and so be paid for) the batch: a timeout, a dropped
    connection or a server error may come after the batch was made; a refusal or a rate limit comes before."""
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code >= 500 or exc.status_code == 408
    return _transient(exc)


T = TypeVar("T")


class BatchQueue:
    def __init__(
        self,
        client: AsyncAnthropic,
        journal: Path,
        *,
        cap_usd: float,
        max_batch_usd: float = 20.0,
        quiet_s: float = 20.0,
        poll_s: float = 20.0,
        dry_run: bool = False,
        spent_before: float = 0.0,
        inflight: Path | None = None,
        retry_tries: int = 10,
        backoff_s: float = 15.0,
        backoff_max_s: float = 120.0,
    ) -> None:
        self.client = client
        self.journal = journal
        self.inflight = inflight or journal.with_name("inflight.jsonl")
        self.cap_usd = cap_usd
        self.max_batch_usd = max_batch_usd
        self.quiet_s = quiet_s
        self.poll_s = poll_s
        self.dry_run = dry_run
        self.spent_before = spent_before  # earlier runs (journal_spend) plus what recover() finds
        self.retry_tries = retry_tries
        self.backoff_s = backoff_s
        self.backoff_max_s = backoff_max_s
        self.ledger = Ledger()
        self.replayed = 0
        self.recovered = 0  # answers of an earlier run's batches written to the journal by recover()
        self.unrecovered: list[str] = []  # earlier batches not read back (yet); their estimate is counted
        self.failed_requests = 0  # calls that raised instead of getting an answer
        self.reserved = 0.0  # estimates of batches sent and not yet ended
        self.pending: list[_Pending] = []
        self.last_submit = time.monotonic()
        self.stopped: str | None = None
        self._cache: dict[str, dict[str, Any]] = {}
        if journal.exists():
            for n, line in enumerate(journal.read_text().splitlines(), 1):
                if line.strip():
                    row = json.loads(line)
                    if "key" not in row:
                        raise ValueError(f"{journal}:{n}: journal row without a 'key' field: {sorted(row)}")
                    self._cache[row["key"]] = row
        self._task: asyncio.Task[None] | None = None
        self._earlier: dict[str, asyncio.Task[None]] = {}  # key -> watcher of the earlier batch that holds it
        self._wake = asyncio.Event()
        self._seq = 0

    @property
    def spent(self) -> float:
        """Spend counted against the cap: earlier runs plus this queue's batches."""
        return self.spent_before + self.ledger.total

    # ---- what a runner calls ----------------------------------------------------------------------------
    async def submit(self, params: dict[str, Any]) -> Message:
        p = plain_params(params)
        key = request_key(p)
        tag = {"case": CASE.get(), "run": RUN.get(), "stage": STAGE.get()}
        hit = self._cache.get(key)
        watcher = self._earlier.get(key) if hit is None else None
        if watcher is not None:
            # an earlier run's batch still running holds this very request: wait for its answer, do not pay twice
            await asyncio.shield(watcher)
            hit = self._cache.get(key)
        if hit is not None:
            self.replayed += 1
            return Message.model_validate(hit["message"])
        if self.stopped:
            self.failed_requests += 1
            raise QueueStoppedError(self.stopped)
        fut: asyncio.Future[Message] = asyncio.get_running_loop().create_future()
        self.pending.append(_Pending(key, p, tag, fut))
        self.last_submit = time.monotonic()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
        self._wake.set()
        return await fut

    async def recover(self) -> int:
        """Write to the journal the paid answers of batches an earlier run sent and never read back (it stopped
        or crashed while they ran), so they are replayed instead of paid again, and count every such batch against
        the cap: one whose answers are journaled under it is counted by `journal_spend` already; one whose
        requests a later run sent again is read and counted at its cost (it was paid twice); one still running is
        counted at its estimate and watched, and a call for one of its requests waits for it; one that cannot be
        read is counted at its estimate. Returns how many answers were recovered now; nothing to do when there
        is no in-flight record."""
        if not self.inflight.exists():
            return 0
        records: dict[str, dict[str, Any]] = {}
        done: set[str] = set()
        for line in self.inflight.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec.get("done"):
                    done.add(rec["batch_id"])
                else:
                    records[rec["batch_id"]] = rec
        found = 0
        for bid, rec in records.items():
            if bid in done:
                continue
            ids: dict[str, str] = rec["requests"]
            if all((self._cache.get(k) or {}).get("batch") == bid for k in ids.values()):
                self._mark_done(bid)  # its own answers are in the journal, so journal_spend counts them
                continue
            version = rec.get("version")
            headers = {"anthropic-version": version} if version else None
            est = float(rec.get("estimate_usd") or 0.0)
            try:
                batch = await self._retry(
                    f"status of earlier batch {bid}",
                    functools.partial(self.client.messages.batches.retrieve, bid, extra_headers=headers),
                )
                if batch.processing_status != "ended":
                    self.spent_before += est
                    self.unrecovered.append(bid)
                    watcher = asyncio.create_task(self._watch_earlier(bid, rec, headers, est))
                    for k in ids.values():
                        if k not in self._cache:
                            self._earlier[k] = watcher
                    log.warning("earlier batch %s has not ended yet; its estimate is counted as spent and its "
                                "calls wait for it", bid)  # fmt: skip
                    continue
                found += await self._take_earlier(bid, rec, headers)
            except Exception as exc:
                self.spent_before += est
                self.unrecovered.append(bid)
                log.warning("could not recover earlier batch %s: %s: %s; its estimate $%.2f is counted as spent",
                            bid, type(exc).__name__, exc, est)  # fmt: skip
        return found

    async def _take_earlier(self, bid: str, rec: dict[str, Any], headers: dict[str, str] | None) -> int:
        """Read an earlier run's ended batch: journal the answers not in the journal yet, count what they cost,
        and also count (without journaling) the answers a later batch was paid for again."""
        results = await self._retry(
            f"results of earlier batch {bid}", functools.partial(self._read_results, bid, headers)
        )
        ids: dict[str, str] = rec["requests"]
        n = again = 0
        cost = 0.0
        with self.journal.open("a") as fh:
            for r in results:
                rkey = ids.get(r.custom_id)
                if rkey is None or r.result.type != "succeeded":
                    continue
                msg = r.result.message
                have = self._cache.get(rkey)
                if have is not None:
                    if have.get("batch") != bid:  # answered again by a later batch: this one was paid as well
                        cost += usage_cost(msg.model, msg.usage)
                        again += 1
                    continue
                tag = rec.get("tags", {}).get(r.custom_id) or {"case": "?", "run": "?", "stage": "?"}
                self._journal(fh, rkey, bid, r.custom_id, tag, msg)
                cost += usage_cost(msg.model, msg.usage)
                n += 1
        self.spent_before += cost
        self.recovered += n
        self._mark_done(bid)
        log.info("earlier batch %s: recovered %d answers, %d paid again later, $%.4f", bid, n, again, cost)
        return n

    async def _watch_earlier(
        self, bid: str, rec: dict[str, Any], headers: dict[str, str] | None, est: float
    ) -> None:
        """Wait for an earlier run's batch that was still running at start, then take in its answers (its
        estimate, counted meanwhile, gives way to its cost). If it cannot be read, its estimate stays counted and
        the calls waiting for it are sent again."""
        me = asyncio.current_task()
        try:
            while True:
                await asyncio.sleep(self.poll_s)
                batch = await self._retry(
                    f"status of earlier batch {bid}",
                    functools.partial(self.client.messages.batches.retrieve, bid, extra_headers=headers),
                )
                if batch.processing_status == "ended":
                    break
            self.spent_before -= est
            try:
                await self._take_earlier(bid, rec, headers)
            except Exception:
                self.spent_before += est
                raise
            self.unrecovered.remove(bid)
        except Exception as exc:
            log.warning("earlier batch %s could not be read back: %s: %s; its estimate stays counted and its calls "
                        "are sent again", bid, type(exc).__name__, exc)  # fmt: skip
        finally:
            for k in [k for k, t in self._earlier.items() if t is me]:
                del self._earlier[k]

    async def close(self) -> None:
        """Stop watching earlier batches and stop the sender (for the runner's end; nothing is lost: an earlier
        batch not read back is read by the next start's `recover()`)."""
        tasks = {*self._earlier.values(), *([self._task] if self._task else [])}
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._earlier.clear()

    # ---- the sender --------------------------------------------------------------------------------------
    def _fail(self, p: _Pending, exc: Exception) -> None:
        if not p.future.done():
            p.future.set_exception(exc)
            self.failed_requests += 1

    def _stop(self, exc: Exception, take: list[_Pending] | None = None) -> None:
        """Stop the queue: every call still waiting (and every later one) fails."""
        reason = f"{type(exc).__name__}: {exc}"
        self.stopped = f"{self.stopped}; {reason}" if self.stopped else reason
        log.error("batch queue stopped: %s", reason)
        for p in [*(take or []), *self.pending]:
            self._fail(p, exc)
        self.pending = []

    async def _loop(self) -> None:
        while self.pending and not self.stopped:
            wait = self.quiet_s - (time.monotonic() - self.last_submit)
            if wait > 0:
                await asyncio.sleep(min(wait, 2.0))
                continue
            take, self.pending = self.pending, []
            await self._flush(take)

    async def _flush(self, take: list[_Pending]) -> None:
        """Send the calls collected so far: grouped by API version, split into batches under the single-batch
        limit, all checked against the cap together before any is sent, then sent side by side. A batch that
        fails does not cut short the others: each one sent runs to its end and journals what it was paid for;
        only then are the failed batches' calls failed and the queue stopped."""
        groups: dict[str | None, list[_Pending]] = defaultdict(list)
        for p in take:
            groups[p.params.get(VERSION_KEY)].append(p)
        parts = [(v, part, _by_key(part)) for v, g in groups.items() for part in self._split(g)]
        estimates = [sum(estimate_usd(ps[0].params) for ps in bk.values()) for _, _, bk in parts]
        total = sum(estimates)
        stages = sorted({f"{p.tag['run']}/{p.tag['stage']}" for p in take})
        try:
            big = max(estimates, default=0.0)
            if big > self.max_batch_usd:
                raise BatchTooLargeError(f"a batch is estimated at ${big:.2f}, over the ${self.max_batch_usd:.2f} "
                                         f"a single batch may cost without asking")  # fmt: skip
            if self.spent + self.reserved + total > self.cap_usd:
                raise SpendCapReachedError(f"spent ${self.spent:.2f} (${self.spent_before:.2f} before this run, "
                                           f"${self.reserved:.2f} more in batches in flight); the next {len(parts)} "
                                           f"batches (estimate ${total:.2f}) would pass the ${self.cap_usd:.2f} cap")  # fmt: skip
            if self.dry_run:
                n = sum(len(bk) for _, _, bk in parts)
                raise QueueStoppedError(f"dry run: would send {n} requests ({stages}), estimate ${total:.2f}")
        except Exception as exc:  # nothing was sent
            self._stop(exc, take)
            return
        self.reserved += total
        try:
            results = await asyncio.gather(
                *(self._send(part, bk, est, v) for (v, part, bk), est in zip(parts, estimates, strict=True)),
                return_exceptions=True,
            )
        finally:
            self.reserved -= total
        failed: list[Exception] = []
        for (_, part, _), res in zip(parts, results, strict=True):
            if isinstance(res, BaseException):
                err = res if isinstance(res, Exception) else QueueStoppedError(repr(res))
                failed.append(err)
                for p in part:
                    self._fail(p, err)
        if failed:
            # an account refusal names the cause best; otherwise the first failure
            first = next((e for e in failed if "refused a request for the account" in str(e)), failed[0])
            self._stop(first)

    def _split(self, take: list[_Pending]) -> list[list[_Pending]]:
        """The calls in parts whose estimate stays under the single-batch limit (with a margin), so a large stage
        goes out as several batches at once instead of one that would need asking first. Calls with the same key
        stay together."""
        limit = self.max_batch_usd * 0.9
        parts: list[list[_Pending]] = [[]]
        cost = 0.0
        for ps in _by_key(take).values():
            est = estimate_usd(ps[0].params)
            if parts[-1] and cost + est > limit:
                parts.append([])
                cost = 0.0
            parts[-1].extend(ps)
            cost += est
        return parts

    async def _retry(self, what: str, fn: Callable[[], Awaitable[T]]) -> T:
        """`fn()`, asked again with a growing wait when it fails for a reason that may pass (see `_transient`)."""
        delay = self.backoff_s
        for attempt in range(1, self.retry_tries + 1):
            try:
                return await fn()
            except Exception as exc:
                if attempt >= self.retry_tries or not _transient(exc):
                    raise
                log.warning("%s: %s: %s (try %d of %d, again in %.0fs)", what, type(exc).__name__, exc, attempt,
                            self.retry_tries, delay)  # fmt: skip
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.backoff_max_s)
        raise AssertionError("unreachable")

    async def _read_results(self, batch_id: str, headers: dict[str, str] | None) -> list[Any]:
        """All of a batch's results, read to the end (so a read that breaks off can be started again)."""
        decoder = await self.client.messages.batches.results(batch_id, extra_headers=headers)
        return [r async for r in decoder]

    def _journal(
        self, fh: IO[str], key: str, batch_id: str, cid: str, tag: dict[str, str], msg: Message
    ) -> None:
        row = {
            "key": key,
            "batch": batch_id,
            "custom_id": cid,
            "tag": tag,
            "message": msg.model_dump(mode="json"),
        }
        fh.write(json.dumps(row) + "\n")
        fh.flush()
        self._cache[key] = row

    def _note_inflight(self, rec: dict[str, Any]) -> None:
        with self.inflight.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")

    def _mark_done(self, batch_id: str) -> None:
        self._note_inflight({"batch_id": batch_id, "done": True})

    async def _send(
        self, take: list[_Pending], by_key: dict[str, list[_Pending]], estimate: float, version: str | None
    ) -> None:
        # one request per key: two cases asking the very same thing share one answer
        stages = sorted({f"{p.tag['run']}/{p.tag['stage']}" for p in take})
        ids: dict[str, str] = {}
        tags: dict[str, dict[str, str]] = {}
        requests = []
        for key, ps in by_key.items():
            self._seq += 1
            cid = f"r{self._seq:06d}-{ps[0].tag['case']}-{ps[0].tag['stage']}"[:64]
            ids[cid] = key
            tags[cid] = ps[0].tag
            requests.append(
                {"custom_id": cid, "params": {k: v for k, v in ps[0].params.items() if k != VERSION_KEY}}
            )
        started = time.monotonic()
        headers = {"anthropic-version": version} if version else None
        try:
            # the SDK's own retries are off for the create: a retry after a timeout or a dropped connection may
            # make a second paid batch while the first gets no in-flight record and is never counted
            batch = await self.client.with_options(max_retries=0).messages.batches.create(
                requests=requests,  # type: ignore[arg-type]
                extra_headers=headers,
            )
        except Exception as exc:
            if _maybe_created(exc):
                self.spent_before += estimate
                log.warning("creating a batch of %d requests failed (%s: %s) in a way that may still have made "
                            "it; its estimate $%.2f is counted as spent", len(requests), type(exc).__name__, exc,
                            estimate)  # fmt: skip
            raise
        bid = batch.id
        # written before waiting, so a run that dies while the batch runs can still read its paid answers
        self._note_inflight({"batch_id": bid, "version": version, "requests": ids, "tags": tags,
                             "estimate_usd": round(estimate, 4), "created": time.time()})  # fmt: skip
        log.info("batch %s: %d requests %s, estimate $%.2f", bid, len(requests), stages, estimate)
        while batch.processing_status != "ended":
            await asyncio.sleep(self.poll_s)
            batch = await self._retry(
                f"status of batch {bid}",
                lambda: self.client.messages.batches.retrieve(bid, extra_headers=headers),
            )
        results = await self._retry(f"results of batch {bid}", lambda: self._read_results(bid, headers))
        # every result is taken in before anything is raised: a refusal for the account does not drop the paid
        # answers that come after it, and the batch still gets its ledger row
        retry: list[_Pending] = []
        cost = 0.0
        errors: dict[str, int] = defaultdict(int)
        account: str | None = None
        seen: set[str] = set()
        with self.journal.open("a") as fh:
            for r in results:
                rkey = ids.get(r.custom_id)
                if rkey is None:
                    continue
                seen.add(rkey)
                ps = by_key[rkey]
                res = r.result
                if res.type == "succeeded":
                    msg = res.message
                    cost += self.ledger.add(ps[0].tag, msg.model, msg.usage)
                    self._journal(fh, rkey, bid, r.custom_id, ps[0].tag, msg)
                    for p in ps:
                        if not p.future.done():
                            p.future.set_result(msg)
                    continue
                detail = (
                    json.dumps(getattr(res, "error", None), default=_plain)
                    if res.type == "errored"
                    else res.type
                )
                errors[res.type] += 1
                if any(w in detail.lower() for w in ACCOUNT_ERRORS):
                    account = account or detail[:300]
                    continue  # its calls fail with the queue below
                transient = res.type == "expired" or (
                    res.type == "errored" and "invalid_request" not in detail
                )
                for p in ps:
                    p.attempts += 1
                    if transient and p.attempts < 2:
                        retry.append(p)
                    else:
                        self._fail(p, RuntimeError(f"batch request {r.custom_id} {res.type}: {detail[:300]}"))
        for key, ps in by_key.items():
            if key not in seen:
                for p in ps:
                    self._fail(p, RuntimeError("no result returned for the request"))
        self.ledger.batches.append({"id": bid, "requests": len(requests), "stages": stages,
                                    "estimate_usd": round(estimate, 4), "cost_usd": round(cost, 4),
                                    "errors": dict(errors), "minutes": round((time.monotonic() - started) / 60, 1)})  # fmt: skip
        self._mark_done(bid)
        log.info("batch %s ended: $%.4f (estimate $%.2f), %s, total $%.2f", bid, cost, estimate, dict(errors),
                 self.spent)  # fmt: skip
        if account:
            raise QueueStoppedError(f"the API refused a request for the account: {account}")
        if retry:
            self.pending.extend(retry)
            self.last_submit = time.monotonic() - self.quiet_s


def _by_key(take: list[_Pending]) -> dict[str, list[_Pending]]:
    by_key: dict[str, list[_Pending]] = defaultdict(list)
    for p in take:
        by_key[p.key].append(p)
    return by_key
