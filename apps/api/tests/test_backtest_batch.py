"""The batch queue the backtest sends model calls through (app.backtest.batch), against a fake Batches API."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from anthropic.types import Message

from app.backtest import batch as bq


def message(text: str = "ok") -> dict[str, Any]:
    return {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-4-5-20250929",
        "content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 1000, "output_tokens": 100, "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 0},
    }  # fmt: skip


class FakeBatches:
    """The Batches API: `fail` maps a word in a request to the error it gets; `create_fails` the 1-based numbers of
    the creates that raise (`create_error`, by default a refusal); a batch is `in_progress` for its first `polls` reads of its status; `retrieve_errors`
    and `results_errors` are raised (in order) by the next reads of status or results."""

    def __init__(
        self,
        fail: dict[str, str] | None = None,
        *,
        create_fails: tuple[int, ...] = (),
        create_error: Exception | None = None,
        polls: int = 0,
        retrieve_errors: list[Exception] | None = None,
        results_errors: list[Exception] | None = None,
    ) -> None:
        self.created: list[dict[str, Any]] = []
        self.fail = fail or {}
        self.create_fails = create_fails
        self.create_error = create_error
        self.polls = polls
        self.retrieve_errors = list(retrieve_errors or [])
        self.results_errors = list(results_errors or [])
        self.retrieved: dict[str, int] = {}
        self.results_read: list[str] = []

    async def create(self, *, requests: list[dict[str, Any]], extra_headers: Any = None) -> Any:
        self.created.append({"requests": requests, "headers": extra_headers})
        if len(self.created) in self.create_fails:
            raise self.create_error or RuntimeError("create refused")
        return SimpleNamespace(
            id=f"b{len(self.created)}", processing_status="in_progress" if self.polls else "ended"
        )

    async def retrieve(self, batch_id: str, extra_headers: Any = None) -> Any:
        if self.retrieve_errors:
            raise self.retrieve_errors.pop(0)
        self.retrieved[batch_id] = n = self.retrieved.get(batch_id, 0) + 1
        return SimpleNamespace(id=batch_id, processing_status="ended" if n >= self.polls else "in_progress")

    async def results(self, batch_id: str, extra_headers: Any = None) -> Any:
        if self.results_errors:
            raise self.results_errors.pop(0)
        self.results_read.append(batch_id)
        reqs = self.created[int(batch_id[1:]) - 1]["requests"]

        async def gen() -> Any:
            for r in reqs:
                text = json.dumps(r["params"]["messages"])
                kind = next((k for k in self.fail if k in text), None)
                if kind:
                    # the SDK's error object is a pydantic model: model_dump takes mode, exclude_none, ...
                    err = SimpleNamespace(
                        model_dump=lambda *a, m=self.fail[kind], **kw: {"error": {"type": m}}
                    )
                    yield SimpleNamespace(
                        custom_id=r["custom_id"], result=SimpleNamespace(type="errored", error=err)
                    )
                else:
                    msg = Message.model_validate(message(r["params"]["messages"][0]["content"]))
                    yield SimpleNamespace(
                        custom_id=r["custom_id"], result=SimpleNamespace(type="succeeded", message=msg)
                    )

        return gen()


class FakeClient:
    """The client: `with_options` (the SDK's per-call options) is noted in `options` and returns the same client."""

    def __init__(self, batches: FakeBatches) -> None:
        self.messages = SimpleNamespace(batches=batches)
        self.options: list[dict[str, Any]] = []

    def with_options(self, **kw: Any) -> FakeClient:
        self.options.append(kw)
        return self


def client(fail: dict[str, str] | None = None, **kw: Any) -> Any:
    return FakeClient(FakeBatches(fail, **kw))


def connection_error() -> Exception:
    return anthropic.APIConnectionError(
        request=httpx2.Request("GET", "https://api.invalid/v1/messages/batches")
    )


def journal_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


ONE_CALL = (1000 * 3 + 100 * 15) / 1e6 * 0.5  # the cost of one fake answer at batch prices


def params(text: str, *, temperature: bool = False, size: int = 10) -> dict[str, Any]:
    p: dict[str, Any] = {
        "model": "claude-sonnet-4-5-20250929", "max_tokens": 1000,
        "system": [{"type": "text", "text": "x" * size, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": text}], "tools": [],
    }  # fmt: skip
    if temperature:
        p |= {"extra_headers": {"anthropic-version": "2023-06-01"}, "extra_body": {"temperature": 0.0}}
    return p


async def test_calls_are_batched_split_under_the_limit_and_journaled(tmp_path: Path) -> None:
    c = client()
    q = bq.BatchQueue(c, tmp_path / "j.jsonl", cap_usd=100, max_batch_usd=0.05, quiet_s=0.05, poll_s=0.01)
    one = bq.estimate_usd(bq.plain_params(params("a0", size=20000)))
    n = 12
    msgs = await asyncio.gather(*(q.submit(params(f"a{i}", size=20000)) for i in range(n)))
    assert [m.content[0].text for m in msgs] == [f"a{i}" for i in range(n)]
    sent = c.messages.batches.created
    assert len(sent) > 1 and sum(len(b["requests"]) for b in sent) == n
    assert all(len(b["requests"]) * one <= 0.05 for b in sent)  # no batch over the single-batch limit
    # the one-hour cache lifetime is set on every cache marker
    assert all(r["params"]["system"][0]["cache_control"]["ttl"] == "1h" for b in sent for r in b["requests"])
    assert q.ledger.total == pytest.approx(n * (1000 * 3 + 100 * 15) / 1e6 * 0.5)
    # a second queue on the same journal answers the same calls without sending anything
    c2 = client()
    q2 = bq.BatchQueue(c2, tmp_path / "j.jsonl", cap_usd=0.0, quiet_s=0.05, poll_s=0.01)
    again = await asyncio.gather(*(q2.submit(params(f"a{i}", size=20000)) for i in range(n)))
    assert [m.content[0].text for m in again] == [m.content[0].text for m in msgs]
    assert c2.messages.batches.created == [] and q2.replayed == n and q2.ledger.total == 0


async def test_the_temperature_goes_in_the_request_and_the_version_on_its_own_batch(tmp_path: Path) -> None:
    c = client()
    q = bq.BatchQueue(c, tmp_path / "j.jsonl", cap_usd=100, quiet_s=0.05, poll_s=0.01)
    await asyncio.gather(q.submit(params("intake", temperature=True)), q.submit(params("other")))
    sent = c.messages.batches.created
    assert len(sent) == 2
    old = next(b for b in sent if b["headers"])
    assert old["headers"] == {"anthropic-version": "2023-06-01"}
    r = old["requests"][0]["params"]
    assert (
        r["temperature"] == 0.0
        and "extra_body" not in r
        and "extra_headers" not in r
        and bq.VERSION_KEY not in r
    )
    assert next(b for b in sent if not b["headers"])["requests"][0]["params"].get("temperature") is None


async def test_the_cap_stops_everything_and_nothing_is_sent(tmp_path: Path) -> None:
    c = client()
    q = bq.BatchQueue(c, tmp_path / "j.jsonl", cap_usd=0.000001, quiet_s=0.05, poll_s=0.01)
    with pytest.raises(bq.SpendCapReachedError):
        await q.submit(params("x"))
    assert c.messages.batches.created == [] and q.stopped
    with pytest.raises(bq.QueueStoppedError):
        await q.submit(params("y"))


async def test_an_account_error_stops_the_queue_and_a_bad_request_fails_only_its_call(tmp_path: Path) -> None:
    c = client({"bad": "invalid_request_error", "money": "billing_error: credit balance too low"})
    q = bq.BatchQueue(c, tmp_path / "j.jsonl", cap_usd=100, quiet_s=0.05, poll_s=0.01)
    ok, bad = await asyncio.gather(q.submit(params("fine")), q.submit(params("bad")), return_exceptions=True)
    assert not isinstance(ok, Exception) and isinstance(bad, RuntimeError)
    with pytest.raises(bq.QueueStoppedError):
        await q.submit(params("money"))
    assert q.stopped and "credit balance" in q.stopped


def test_an_earlier_answer_hashes_the_same_whether_fresh_or_rebuilt_from_the_journal() -> None:
    raw = {**message(), "content": [{"type": "text", "text": "thinking aloud"},
                                    {"type": "tool_use", "id": "toolu_1", "name": "read_decision", "input": {"id": "x"}}]}  # fmt: skip
    fresh = Message.model_validate(raw)  # as parsed from the API's answer
    rebuilt = Message.model_validate(fresh.model_dump(mode="json"))  # as replayed from the journal

    def request(m: Message) -> dict[str, Any]:
        return {"model": "claude-sonnet-4-5", "max_tokens": 10, "messages": [
            {"role": "user", "content": "q"}, {"role": "assistant", "content": m.content}]}  # fmt: skip

    assert bq.request_key(bq.plain_params(request(fresh))) == bq.request_key(
        bq.plain_params(request(rebuilt))
    )
    sent = bq.plain_params(request(fresh))["messages"][1]["content"]
    assert sent == [{"type": "text", "text": "thinking aloud"},
                    {"type": "tool_use", "id": "toolu_1", "name": "read_decision", "input": {"id": "x"}}]  # fmt: skip


# ---- the whole flush is checked against the cap; a failing batch does not take the others down -----------------


async def test_a_split_flush_is_checked_against_the_cap_as_a_whole_and_nothing_is_sent(
    tmp_path: Path,
) -> None:
    c = client()
    one = bq.estimate_usd(bq.plain_params(params("a0", size=20000)))
    n = 12
    # each batch of the split fits the cap on its own; all of them together do not
    q = bq.BatchQueue(
        c, tmp_path / "j.jsonl", cap_usd=n * one * 0.9, max_batch_usd=0.05, quiet_s=0.05, poll_s=0.01
    )
    assert n * one * 0.9 > 0.05
    out = await asyncio.gather(
        *(q.submit(params(f"a{i}", size=20000)) for i in range(n)), return_exceptions=True
    )
    assert all(isinstance(r, bq.SpendCapReachedError) for r in out)
    assert c.messages.batches.created == [] and q.stopped and q.failed_requests == n


async def test_spend_before_this_run_counts_against_the_cap(tmp_path: Path) -> None:
    c = client()
    est = bq.estimate_usd(bq.plain_params(params("x")))
    q = bq.BatchQueue(
        c, tmp_path / "j.jsonl", cap_usd=1.0, spent_before=1.0 - est / 2, quiet_s=0.05, poll_s=0.01
    )
    with pytest.raises(bq.SpendCapReachedError):
        await q.submit(params("x"))
    assert c.messages.batches.created == []
    q = bq.BatchQueue(
        client(), tmp_path / "j2.jsonl", cap_usd=1.0, spent_before=0.5, quiet_s=0.05, poll_s=0.01
    )
    await q.submit(params("x"))
    assert q.spent == pytest.approx(0.5 + ONE_CALL)


async def test_a_failing_batch_does_not_lose_the_answers_of_another_sent_with_it(tmp_path: Path) -> None:
    # two batches go out together; the second is refused at once while the first is still running
    c = client(create_fails=(2,), polls=2)
    j = tmp_path / "j.jsonl"
    q = bq.BatchQueue(c, j, cap_usd=100, max_batch_usd=0.05, quiet_s=0.05, poll_s=0.01)
    n = 12
    out = await asyncio.gather(
        *(q.submit(params(f"a{i}", size=20000)) for i in range(n)), return_exceptions=True
    )
    sent = c.messages.batches.created
    assert len(sent) >= 2
    refused = {r["params"]["messages"][0]["content"] for r in sent[1]["requests"]}
    for i, r in enumerate(out):
        if f"a{i}" in refused:
            assert isinstance(r, RuntimeError) and "create refused" in str(r)
        else:
            assert isinstance(r, Message) and r.content[0].text == f"a{i}"
    answered = {f"a{i}" for i in range(n)} - refused
    rows = journal_rows(j)
    assert {r["message"]["content"][0]["text"] for r in rows} == answered and all(r["key"] for r in rows)
    assert "b2" not in {b["id"] for b in q.ledger.batches} and len(q.ledger.batches) == len(sent) - 1
    assert q.ledger.total == pytest.approx(len(answered) * ONE_CALL)
    assert q.stopped and "create refused" in q.stopped and q.failed_requests == len(refused)
    with pytest.raises(bq.QueueStoppedError):
        await q.submit(params("later"))


# ---- reading a batch back survives a dropped connection; a crashed run's answers are recovered ---------------


async def test_a_status_read_that_fails_twice_then_works_still_delivers(tmp_path: Path) -> None:
    c = client(polls=1, retrieve_errors=[connection_error(), ConnectionResetError("reset")])
    q = bq.BatchQueue(c, tmp_path / "j.jsonl", cap_usd=100, quiet_s=0.05, poll_s=0.01, backoff_s=0.001)
    msg = await q.submit(params("fine"))
    assert msg.content[0].text == "fine" and not q.stopped and q.failed_requests == 0
    assert c.messages.batches.retrieved == {"b1": 1}  # the third read got through


async def test_a_results_read_that_breaks_off_is_read_again(tmp_path: Path) -> None:
    c = client(results_errors=[connection_error()])
    q = bq.BatchQueue(c, tmp_path / "j.jsonl", cap_usd=100, quiet_s=0.05, poll_s=0.01, backoff_s=0.001)
    assert (await q.submit(params("fine"))).content[0].text == "fine"
    assert not q.stopped and c.messages.batches.results_read == ["b1"]


async def test_a_read_that_keeps_failing_stops_the_queue_after_its_tries(tmp_path: Path) -> None:
    c = client(polls=1, retrieve_errors=[connection_error() for _ in range(5)])
    q = bq.BatchQueue(
        c, tmp_path / "j.jsonl", cap_usd=100, quiet_s=0.05, poll_s=0.01, backoff_s=0.001, retry_tries=3
    )
    with pytest.raises(anthropic.APIConnectionError):
        await q.submit(params("fine"))
    assert q.stopped and len(c.messages.batches.retrieve_errors) == 2


async def test_recover_journals_the_answers_of_a_batch_an_earlier_run_never_read(tmp_path: Path) -> None:
    j = tmp_path / "j.jsonl"
    assert await bq.BatchQueue(client(), j, cap_usd=100).recover() == 0  # no in-flight record: nothing to do
    # the first run's batch is paid for, but reading its results fails for good and the run stops
    c = client(results_errors=[RuntimeError("the run died")])
    q = bq.BatchQueue(c, j, cap_usd=100, quiet_s=0.05, poll_s=0.01, backoff_s=0.001)
    with pytest.raises(RuntimeError):
        await q.submit(params("paid"))
    assert not j.exists() and (tmp_path / "inflight.jsonl").exists()
    # the next run recovers the answer before it starts and replays it instead of paying again
    q2 = bq.BatchQueue(c, j, cap_usd=100, quiet_s=0.05, poll_s=0.01)
    assert await q2.recover() == 1
    assert q2.recovered == 1 and q2.spent_before == pytest.approx(ONE_CALL)
    rows = journal_rows(j)
    assert len(rows) == 1 and rows[0]["key"] == bq.request_key(bq.plain_params(params("paid")))
    assert rows[0]["batch"] == "b1" and rows[0]["tag"]["case"] == "none"
    assert (await q2.submit(params("paid"))).content[0].text == "paid"
    assert len(c.messages.batches.created) == 1 and q2.replayed == 1
    # the batch is marked done: a later start does not read it again
    reads = list(c.messages.batches.results_read)
    q3 = bq.BatchQueue(c, j, cap_usd=100)
    assert await q3.recover() == 0 and c.messages.batches.results_read == reads
    assert bq.journal_spend(j) == pytest.approx(ONE_CALL)


def inflight_record(tmp_path: Path, bid: str = "b9", estimate: float = 1.5) -> None:
    (tmp_path / "inflight.jsonl").write_text(
        json.dumps(
            {"batch_id": bid, "version": None, "requests": {"r1": "k1"}, "tags": {}, "estimate_usd": estimate}
        )
        + "\n"
    )


async def test_recover_counts_an_earlier_batch_still_running_as_spent(tmp_path: Path) -> None:
    j = tmp_path / "j.jsonl"
    inflight_record(tmp_path)
    c = client(polls=5)
    q = bq.BatchQueue(c, j, cap_usd=100)
    assert await q.recover() == 0
    assert q.unrecovered == ["b9"] and q.spent_before == pytest.approx(1.5) and not j.exists()
    assert set(q._earlier) == {"k1"}  # a call for its request waits for it
    await q.close()
    assert q._earlier == {}


async def test_recover_counts_an_earlier_batch_it_cannot_read_as_spent(tmp_path: Path) -> None:
    inflight_record(tmp_path)
    c = client(retrieve_errors=[RuntimeError("not found")])  # a refusal: not asked again
    q = bq.BatchQueue(c, tmp_path / "j.jsonl", cap_usd=100, backoff_s=0.001)
    assert await q.recover() == 0
    assert q.unrecovered == ["b9"] and q.spent_before == pytest.approx(1.5) and q._earlier == {}
    # the results of an ended batch that cannot be read count the same way
    c = client(results_errors=[RuntimeError("gone")])
    c.messages.batches.created.append({"requests": [], "headers": None})
    inflight_record(tmp_path, bid="b1", estimate=0.75)
    q = bq.BatchQueue(c, tmp_path / "j.jsonl", cap_usd=100, backoff_s=0.001)
    assert await q.recover() == 0
    assert q.unrecovered == ["b1"] and q.spent_before == pytest.approx(0.75)


async def test_recover_counts_an_earlier_batch_whose_requests_a_later_run_paid_for_again(
    tmp_path: Path,
) -> None:
    j = tmp_path / "j.jsonl"
    # run 1: its batch b1 is paid for, but reading its results fails and the run stops
    c = client(results_errors=[RuntimeError("the run died")])
    with pytest.raises(RuntimeError):
        await bq.BatchQueue(c, j, cap_usd=100, quiet_s=0.05, poll_s=0.01).submit(params("paid"))
    # run 2 (without recover) sends the same request again as b2 and journals that answer
    q2 = bq.BatchQueue(c, j, cap_usd=100, quiet_s=0.05, poll_s=0.01)
    await q2.submit(params("paid"))
    assert [r["batch"] for r in journal_rows(j)] == ["b2"]
    # run 3: every key of b1 is in the journal, but under b2: b1 was paid as well and is counted, not journaled
    q3 = bq.BatchQueue(c, j, cap_usd=100, spent_before=bq.journal_spend(j))
    assert await q3.recover() == 0
    assert q3.spent_before == pytest.approx(2 * ONE_CALL) and q3.recovered == 0
    assert len(journal_rows(j)) == 1 and c.messages.batches.results_read == ["b2", "b1"]
    # and only once
    q4 = bq.BatchQueue(c, j, cap_usd=100)
    assert await q4.recover() == 0 and q4.spent_before == 0.0
    assert c.messages.batches.results_read == ["b2", "b1"]


async def test_a_call_waits_for_an_earlier_batch_still_running_instead_of_paying_again(
    tmp_path: Path,
) -> None:
    j = tmp_path / "j.jsonl"
    # run 1 creates b1 and dies while it runs
    c = client(polls=3, retrieve_errors=[RuntimeError("the run died")])
    with pytest.raises(RuntimeError):
        await bq.BatchQueue(c, j, cap_usd=100, quiet_s=0.05, poll_s=0.01).submit(params("paid"))
    est = bq.estimate_usd(bq.plain_params(params("paid")))
    q = bq.BatchQueue(c, j, cap_usd=100, quiet_s=0.05, poll_s=0.01)
    assert await q.recover() == 0
    assert q.unrecovered == ["b1"] and q.spent_before == pytest.approx(round(est, 4))
    msg = await q.submit(params("paid"))
    assert msg.content[0].text == "paid" and q.replayed == 1 and q.recovered == 1
    assert len(c.messages.batches.created) == 1  # not sent again
    assert q.unrecovered == [] and q.spent_before == pytest.approx(ONE_CALL) and q._earlier == {}
    assert [r["batch"] for r in journal_rows(j)] == ["b1"]


# ---- a create is never repeated by the SDK; one that may have made the batch counts it ------------------------


async def test_a_batch_is_created_with_the_sdks_retries_off(tmp_path: Path) -> None:
    c = client()
    q = bq.BatchQueue(c, tmp_path / "j.jsonl", cap_usd=100, quiet_s=0.05, poll_s=0.01)
    await q.submit(params("fine"))
    assert c.options == [{"max_retries": 0}]


async def test_a_create_that_may_have_made_the_batch_counts_its_estimate(tmp_path: Path) -> None:
    est = bq.estimate_usd(bq.plain_params(params("x")))
    c = client(create_fails=(1,), create_error=anthropic.APITimeoutError(
        request=httpx2.Request("POST", "https://api.invalid/v1/messages/batches")))  # fmt: skip
    q = bq.BatchQueue(c, tmp_path / "j.jsonl", cap_usd=100, quiet_s=0.05, poll_s=0.01)
    with pytest.raises(anthropic.APITimeoutError):
        await q.submit(params("x"))
    assert q.spent_before == pytest.approx(est) and q.stopped
    # a refusal comes before any batch is made: nothing is counted
    q = bq.BatchQueue(
        client(create_fails=(1,)), tmp_path / "j2.jsonl", cap_usd=100, quiet_s=0.05, poll_s=0.01
    )
    with pytest.raises(RuntimeError, match="create refused"):
        await q.submit(params("x"))
    assert q.spent_before == 0.0


# ---- an account refusal keeps the answers paid for in the same batch -------------------------------------------


async def test_an_account_error_after_successes_keeps_them_in_journal_and_ledger(tmp_path: Path) -> None:
    j = tmp_path / "j.jsonl"
    c = client({"money": "billing_error: credit balance too low"})
    q = bq.BatchQueue(c, j, cap_usd=100, quiet_s=0.05, poll_s=0.01)
    a, money, b = await asyncio.gather(
        q.submit(params("fine1")),
        q.submit(params("money")),
        q.submit(params("fine2")),
        return_exceptions=True,
    )
    assert isinstance(a, Message) and isinstance(b, Message) and b.content[0].text == "fine2"
    assert isinstance(money, bq.QueueStoppedError) and "credit balance" in str(money)
    rows = journal_rows(j)
    assert sorted(r["message"]["content"][0]["text"] for r in rows) == ["fine1", "fine2"]
    assert all(
        r["key"] == bq.request_key(bq.plain_params(params(r["message"]["content"][0]["text"]))) for r in rows
    )
    assert q.ledger.total == pytest.approx(2 * ONE_CALL)
    assert len(q.ledger.batches) == 1 and q.ledger.batches[0]["errors"] == {"errored": 1}
    assert q.ledger.batches[0]["cost_usd"] == pytest.approx(2 * ONE_CALL, abs=1e-4)
    assert q.stopped and "credit balance" in q.stopped and q.failed_requests == 1
    with pytest.raises(bq.QueueStoppedError):
        await q.submit(params("later"))
    assert q.failed_requests == 2


# ---- what the journal says was spent ----------------------------------------------------------------------------


def test_journal_spend_sums_every_row_at_batch_prices(tmp_path: Path) -> None:
    j = tmp_path / "j.jsonl"
    assert bq.journal_spend(j) == 0.0
    sonnet = message()
    haiku = {**message(), "model": "claude-haiku-4-5-20251001", "usage": {
        "input_tokens": 200, "output_tokens": 50, "cache_read_input_tokens": 10000,
        "cache_creation_input_tokens": 3000,
        "cache_creation": {"ephemeral_1h_input_tokens": 2000, "ephemeral_5m_input_tokens": 1000}}}  # fmt: skip
    rows = [
        {"key": "k1", "message": sonnet},
        {"key": "k2", "message": haiku},
        {"key": "k3", "message": sonnet},
    ]
    j.write_text("".join(json.dumps(r) + "\n" for r in rows) + "\n")
    want = 2 * ONE_CALL + (200 * 1 + 10000 * 1 * 0.1 + 2000 * 1 * 2.0 + 1000 * 1 * 1.25 + 50 * 5) / 1e6 * 0.5
    assert bq.journal_spend(j) == pytest.approx(want)


def test_a_journal_row_without_a_key_is_refused(tmp_path: Path) -> None:
    j = tmp_path / "j.jsonl"
    j.write_text(json.dumps({"request_key": "k1", "message": message()}) + "\n")
    with pytest.raises(ValueError, match="key"):
        bq.BatchQueue(client(), j, cap_usd=1)
