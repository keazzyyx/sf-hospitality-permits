"""Backfill ABC's daily and weekly licensing reports into abc-archive-data, newest first.

    python -m precedent.abc_backfill run  --repo ~/abc-archive-data --staging ~/abc-archive-data-staging --from 2019-01-01
    python -m precedent.abc_backfill pack --repo ~/abc-archive-data --staging ~/abc-archive-data-staging
    python -m precedent.abc_backfill status --repo ~/abc-archive-data --staging ~/abc-archive-data-staging

``run`` walks every calendar day from yesterday back to ``--from`` (weekends included) and fetches Status
Changes, Issued Licenses and New Applications for each, then every week of Legal Actions Finalized and Filed.
Parsed CSVs go into the repository exactly where the daily collector puts them; raw pages go to the staging
folder. Rules:

- One request at a time, ``--delay`` seconds apart (default 3), with the archive's User-Agent.
- Any 403, 429, 5xx, timeout, transport error or non-ABC page stops the run at once. Nothing is retried.
- Resumable: a (report, date) is skipped when its CSV is already in the repository or the date is recorded
  as having no report. Re-running continues where it stopped.
- New Applications only exists back to mid-2025, so after ``--newapp-empty-days`` consecutive dates without
  that report (default 30) the run stops asking for it and records the date.
- Each date is fetched while holding the lock the daily collector uses, so the daily run always gets in.
- Commits (and pushes) every ``--commit-every`` dates and at the end.

``pack`` turns the staged raw pages into compressed yearly archives in the repository
(``raw-archives/<daily|weekly>/<year>/<report>-<year>[-part].tar.xz``, each under 49 MB), writes member
checksums beside each archive and ``raw-archives/SHA256SUMS`` for the archives, then unpacks every archive
and re-parses each page. Only when every page reproduces its CSV byte for byte are the loose pages deleted.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
import logging
import os
import sys
import tarfile
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from precedent.abc_archive import (
    DAILY,
    WEEKLY,
    Archive,
    commit,
    csv_bytes,
    drop_mailing,
    is_stop_error,
    parse_legal_actions,
    repo_lock,
    user_agent,
)
from precedent.sources.abc import parse_report_html

log = logging.getLogger("precedent.abc_backfill")

MAX_ARCHIVE_BYTES = 49 * 1024 * 1024
STATE_NAME = "backfill-state.json"


# ---- state -------------------------------------------------------------------------------------------------
@dataclass
class State:
    no_report: set[str] = field(default_factory=set)  # "slug|YYYY-MM-DD"
    newapp_empty_streak: int = 0
    newapp_stopped_before: str | None = None  # the run stopped asking for New Applications before this date
    requests: int = 0
    stopped: str | None = None

    @classmethod
    def load(cls, path: Path) -> State:
        if not path.exists():
            return cls()
        d = json.loads(path.read_text())
        return cls(
            no_report=set(d.get("no_report", [])),
            newapp_empty_streak=int(d.get("newapp_empty_streak", 0)),
            newapp_stopped_before=d.get("newapp_stopped_before"),
            requests=int(d.get("requests", 0)),
            stopped=d.get("stopped"),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "no_report": sorted(self.no_report),
                    "newapp_empty_streak": self.newapp_empty_streak,
                    "newapp_stopped_before": self.newapp_stopped_before,
                    "requests": self.requests,
                    "stopped": self.stopped,
                },
                indent=1,
            )
        )
        tmp.replace(path)


def daily_csv(repo: Path, slug: str, day: dt.date) -> Path:
    return repo / "daily" / day.isoformat() / f"{slug}.csv"


def days_back(start: dt.date, end: dt.date) -> list[dt.date]:
    """``end`` back to ``start`` inclusive, newest first."""
    return [end - dt.timedelta(days=k) for k in range((end - start).days + 1)]


def pending_daily(repo: Path, state: State, days: list[dt.date]) -> list[tuple[dt.date, str]]:
    out = []
    for day in days:
        for slug in DAILY:
            if (
                slug == "new-applications"
                and state.newapp_stopped_before
                and day.isoformat() < state.newapp_stopped_before
            ):
                continue
            if daily_csv(repo, slug, day).exists() or f"{slug}|{day.isoformat()}" in state.no_report:
                continue
            out.append((day, slug))
    return out


# ---- run ---------------------------------------------------------------------------------------------------
class Stop(Exception):  # noqa: N818 — control flow, not an error condition
    pass


def run(args: argparse.Namespace, client: httpx.Client | None = None) -> int:
    repo: Path = args.repo
    staging: Path = args.staging
    state_path = staging / STATE_NAME
    state = State.load(state_path)
    if state.stopped:
        log.info("previous run stopped (%s); resuming", state.stopped)
        state.stopped = None
    end = args.to or (dt.date.today() - dt.timedelta(days=1))
    days = days_back(args.start, end)
    todo = pending_daily(repo, state, days)
    weekly_estimate = 0 if args.no_weekly else 760
    total = len(todo) + weekly_estimate
    log.info(
        "backfill %s → %s: %d daily requests to go (+~%d weekly); %.1f h at %.0fs apart",
        end,
        args.start,
        len(todo),
        weekly_estimate,
        total * (args.delay + 0.8) / 3600,
        args.delay,
    )
    own = client is None
    client = client or httpx.Client(headers={"User-Agent": user_agent()}, follow_redirects=True, timeout=60)
    arc = Archive(repo, client, delay=args.delay, raw_root=staging / "raw")
    started = time.monotonic()
    done = 0
    dates_since_commit = 0

    def progress(where: str) -> None:
        rate = (time.monotonic() - started) / max(done, 1)
        eta = dt.timedelta(seconds=int(rate * max(total - done, 0)))
        log.info("progress %d/%d requests, at %s, about %s left", done, total, where, eta)

    def checkpoint(message: str) -> None:
        state.save(state_path)
        if args.commit:
            with repo_lock(repo):
                arc.write_index()
                commit(repo, message, push=args.push, heartbeat=False)

    try:
        current: dt.date | None = None
        for day, slug in todo:
            if slug == "new-applications" and state.newapp_stopped_before:
                continue
            if current != day:
                if current is not None:
                    dates_since_commit += 1
                    if dates_since_commit >= args.commit_every:
                        checkpoint(f"ABC backfill through {current}")
                        dates_since_commit = 0
                current = day
            with repo_lock(repo):
                try:
                    saved = arc.save_daily(slug, day)
                except Exception as exc:
                    if is_stop_error(exc):
                        raise Stop(f"{slug} {day}: {type(exc).__name__}: {exc}") from exc
                    raise
            done += 1
            state.requests += 1
            if saved.rows == 0 and saved.note:
                state.no_report.add(f"{slug}|{day.isoformat()}")
                if slug == "new-applications":
                    state.newapp_empty_streak += 1
                    if state.newapp_empty_streak >= args.newapp_empty_days:
                        state.newapp_stopped_before = (
                            day + dt.timedelta(days=args.newapp_empty_days)
                        ).isoformat()
                        log.info(
                            "New Applications: %d consecutive dates without a report; not asking before %s",
                            state.newapp_empty_streak,
                            state.newapp_stopped_before,
                        )
            elif slug == "new-applications":
                state.newapp_empty_streak = 0
            if done % 25 == 0:
                progress(f"{day} {slug}")
                state.save(state_path)
        checkpoint(f"ABC backfill: daily reports back to {args.start}")

        if not args.no_weekly:
            for slug in WEEKLY:
                with repo_lock(repo):
                    try:
                        weeks, nonce = arc.week_endings(slug)
                    except Exception as exc:
                        raise Stop(f"{slug} week list: {type(exc).__name__}: {exc}") from exc
                done += 1
                for week in weeks:
                    iso = dt.datetime.strptime(week, "%m-%d-%Y").date().isoformat()
                    if (repo / "weekly" / slug / iso / "rows.csv").exists():
                        continue
                    with repo_lock(repo):
                        try:
                            arc.save_weekly(slug, week, nonce)
                        except Exception as exc:
                            if is_stop_error(exc):
                                raise Stop(f"{slug} {iso}: {type(exc).__name__}: {exc}") from exc
                            raise
                    done += 1
                    state.requests += 1
                    if done % 25 == 0:
                        progress(f"{slug} week {iso}")
                        state.save(state_path)
            checkpoint("ABC backfill: every week of Legal Actions Finalized and Filed")
    except Stop as stop:
        state.stopped = f"{dt.datetime.now().isoformat(timespec='seconds')} {stop}"
        log.error("STOPPED, nothing retried: %s. Re-run the same command to resume.", stop)
        checkpoint("ABC backfill: partial (stopped)")
        return 2
    finally:
        state.save(state_path)
        if own:
            client.close()
    log.info("backfill complete: %d requests this run, %d in total", done, state.requests)
    return 0


# ---- pack --------------------------------------------------------------------------------------------------
def _staged(staging: Path) -> dict[tuple[str, str, str], list[Path]]:
    """Group staged raw pages by (kind, year, report)."""
    groups: dict[tuple[str, str, str], list[Path]] = {}
    for p in sorted((staging / "raw").glob("*/*/*/*.html.gz")):
        kind, year, slug = p.parts[-4], p.parts[-3], p.parts[-2]
        groups.setdefault((kind, year, slug), []).append(p)
    return groups


def _expected_csv(repo: Path, kind: str, slug: str, date: str) -> Path:
    if kind == "daily":
        return repo / "daily" / date / f"{slug}.csv"
    return repo / "weekly" / slug / date / "rows.csv"


def reparse(kind: str, html: str) -> bytes:
    if kind == "daily":
        _, rows = parse_report_html(html)
        return csv_bytes([drop_mailing(r) for r in rows])
    _, wrows = parse_legal_actions(html)
    return csv_bytes(wrows)


def _split(paths: list[Path], parts: int) -> list[list[Path]]:
    """Split by date order into ``parts`` contiguous chunks."""
    size = -(-len(paths) // parts)
    return [paths[i : i + size] for i in range(0, len(paths), size)]


def build_tar_xz(members: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz", preset=9) as tar:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def iter_tar(data: bytes) -> Iterator[tuple[str, bytes]]:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as tar:
        for m in tar.getmembers():
            if not m.isfile():
                continue
            fh = tar.extractfile(m)
            if fh is not None:
                yield m.name, fh.read()


def pack(repo: Path, staging: Path) -> int:
    out_root = repo / "raw-archives"
    problems = 0
    for (kind, year, slug), pages in sorted(_staged(staging).items()):
        for parts in (1, 2, 4, 12):
            chunks = _split(pages, parts)
            blobs = []
            for i, chunk in enumerate(chunks, 1):
                members = [
                    (f"{slug}/{p.name.removesuffix('.gz')}", gzip.decompress(p.read_bytes())) for p in chunk
                ]
                suffix = "" if parts == 1 else f"-part{i:02d}"
                blobs.append((f"{slug}-{year}{suffix}", chunk, members, build_tar_xz(members)))
            if all(len(b[3]) <= MAX_ARCHIVE_BYTES for b in blobs):
                break
        else:
            log.error("%s/%s/%s: still over the size limit at 12 parts; leaving loose", kind, year, slug)
            problems += 1
            continue
        for name, chunk, members, blob in blobs:
            # verify: unpack and re-parse every page; it must reproduce the committed CSV exactly
            mismatches = []
            unpacked = dict(iter_tar(blob))
            if set(unpacked) != {m[0] for m in members}:
                mismatches.append("member list differs after unpacking")
            for member, html in unpacked.items():
                date = Path(member).name.removesuffix(".html")
                expected = _expected_csv(repo, kind, slug, date)
                if not expected.exists() or reparse(kind, html.decode()) != expected.read_bytes():
                    mismatches.append(member)
            if mismatches:
                log.error(
                    "%s: %d pages do not re-parse to their CSV (%s…); loose pages kept",
                    name,
                    len(mismatches),
                    mismatches[:3],
                )
                problems += 1
                continue
            target = out_root / kind / year / f"{name}.tar.xz"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
            sums = "".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in sorted(unpacked.items()))
            target.with_name(f"{name}.members.sha256").write_text(sums)
            for p in chunk:
                p.unlink()
            log.info(
                "packed %s: %d pages, %.1f MB, verified",
                target.relative_to(repo),
                len(chunk),
                len(blob) / 1e6,
            )
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out_root)}\n"
        for p in sorted(out_root.glob("*/*/*.tar.xz"))
    ]
    if lines:
        (out_root / "SHA256SUMS").write_text("".join(lines))
    return 1 if problems else 0


# ---- status ------------------------------------------------------------------------------------------------
def status(repo: Path, staging: Path) -> int:
    state = State.load(staging / STATE_NAME)
    daily = sorted({p.parent.name for p in repo.glob("daily/*/*.csv")})
    weekly = len(list(repo.glob("weekly/*/*/rows.csv")))
    staged = len(list((staging / "raw").glob("*/*/*/*.html.gz")))
    print(
        f"daily report dates saved: {len(daily)} ({daily[0] if daily else '—'} → {daily[-1] if daily else '—'})"
    )
    print(
        f"weekly reports saved: {weekly}; dates with no report: {len(state.no_report)}; staged raw pages: {staged}"
    )
    print(
        f"requests so far: {state.requests}; New Applications not asked before: {state.newapp_stopped_before or '—'}"
    )
    print(f"stopped: {state.stopped or 'no'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="abc-backfill")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "pack", "status"):
        sp = sub.add_parser(name)
        sp.add_argument("--repo", type=Path, required=True)
        sp.add_argument("--staging", type=Path, required=True)
        if name == "run":
            sp.add_argument("--from", dest="start", type=dt.date.fromisoformat, required=True)
            sp.add_argument("--to", type=dt.date.fromisoformat)
            sp.add_argument("--delay", type=float, default=3.0)
            sp.add_argument("--commit-every", type=int, default=60, help="dates between commits (default 60)")
            sp.add_argument("--newapp-empty-days", type=int, default=30)
            sp.add_argument("--no-weekly", action="store_true")
            sp.add_argument("--commit", action="store_true")
            sp.add_argument("--push", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.cmd == "run":
        return run(args)
    if args.cmd == "pack":
        code = pack(args.repo, args.staging)
        with repo_lock(args.repo):
            commit(
                args.repo,
                "ABC backfill: raw pages packed into verified yearly archives",
                push=True,
                heartbeat=False,
            )
        return code
    return status(args.repo, args.staging)


if __name__ == "__main__":
    sys.exit(main())
