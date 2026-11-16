"""Archive California ABC's public licensing reports before they roll off the site.

ABC publishes, for the whole state:

- three **daily** reports — Issued Licenses (RPTTYPE=1), New Applications (2), Status Changes (3) — at
  ``/licensing/licensing-reports/<slug>/?RPTTYPE=<n>&RPTDATE=MM/DD/YYYY``. Status Changes carries the outcome
  history the licence export lacks (``PEND → ACTIVE``, ``PEND → WITHDRAWN`` …).
- two **weekly** reports — Legal Actions Finalized (17, lists licence denials) and Legal Actions Filed (16) —
  loaded by the page's own script with a POST to ``/wp-admin/admin-ajax.php``.
- the **Daily Data Export** (every licence and application, refreshed each business day ~7 a.m. Pacific).

Each run writes into a checkout of a separate data repository (``--repo``; never this repository, whose
every commit may redeploy the site and the API):

    daily/<YYYY-MM-DD>/<report>.html.gz   raw page, gzip with a fixed mtime
    daily/<YYYY-MM-DD>/<report>.csv       parsed rows, mailing-address columns removed
    weekly/<report>/<YYYY-MM-DD>/…        same, keyed by week-ending date
    export/baseline/<YYYY-MM-DD>.csv.gz   one full copy, committed once
    export/changes/<YYYY-MM-DD>.csv       rows added, removed, or whose status changed vs the previous copy
    export/latest.csv.gz                  previous copy for the next diff (git-ignored, kept on this Mac)
    index.csv                             one line per saved report: date, report, rows, sha256 of the CSV

Files are rewritten only when the parsed rows change, so re-running is a no-op and never duplicates.
Requests are sequential, ``--delay`` seconds apart (default 3), with the User-Agent
``CA ABC public-report archiver/1.0 (independent research; contact: <ABC_ARCHIVE_CONTACT>)``. abc.ca.gov answers 403 to GitHub's hosted runners, so
this runs on a workstation (launchd) rather than in Actions.

    python -m precedent.abc_archive --repo ~/abc-archive-data [--days 6] [--from 2026-01-01 --to 2026-01-31]
                                    [--weeks 2] [--no-export] [--commit] [--push]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import fcntl
import gzip
import hashlib
import html as html_lib
import io
import logging
import os
import re
import subprocess
import sys
import time
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx

from precedent.sources.abc import parse_report_html
from precedent.sources.base import abc_user_agent

log = logging.getLogger("precedent.abc_archive")

ABC = "https://www.abc.ca.gov"
REPORTS = f"{ABC}/licensing/licensing-reports"
AJAX_URL = f"{ABC}/wp-admin/admin-ajax.php"
EXPORT_URL = f"{ABC}/wp-content/uploads/DailyExport-CSV.zip"

DAILY = {"issued-licenses": "1", "new-applications": "2", "status-changes": "3"}
WEEKLY = {"legal-actions-finalized": "17", "legal-actions-filed": "16"}

EXPORT_KEY = ("File Number", "License Type")
EXPORT_STATUS = "Type Status"

_MAIL_RE = re.compile(
    r"(?:^|[\s_])mail", re.I
)  # "Mailing Street", "Mail Zip", "licensee_mailing_address"; not "email"


def user_agent(contact: str | None = None) -> str:
    return abc_user_agent(contact)


# ---- small pure helpers ------------------------------------------------------------------------------------
def drop_mailing(row: dict[str, str]) -> dict[str, str]:
    """Remove every mailing-address column (``Mailing Addr.``, ``Mailing Street``, ``Mail Zip`` …)."""
    return {k: v for k, v in row.items() if not _MAIL_RE.search(k or "")}


def csv_bytes(rows: Sequence[dict[str, str]], columns: Sequence[str] | None = None) -> bytes:
    """Deterministic CSV: fixed column order, rows sorted, ``\\n`` line endings."""
    cols = list(columns) if columns is not None else _columns(rows)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in sorted(rows, key=lambda r: tuple(str(r.get(c, "")) for c in cols)):
        w.writerow({c: r.get(c, "") for c in cols})
    return buf.getvalue().encode()


def _columns(rows: Iterable[dict[str, str]]) -> list[str]:
    cols: list[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    return cols


def gzip_bytes(data: bytes) -> bytes:
    """gzip with mtime 0 so identical input gives identical bytes (no spurious git diffs)."""
    return gzip.compress(data, mtime=0)


def write_if_changed(path: Path, data: bytes) -> bool:
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return True


def _text(fragment: str) -> str:
    t = re.sub(r"<br\s*/?>", " | ", fragment, flags=re.I)
    t = re.sub(r"</(?:tr|h2|h3|h4|p|div|li|dd|dt|td|th)>", "\n", t, flags=re.I)
    t = re.sub(r"<!--|-->", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    lines = (re.sub(r"\s+", " ", html_lib.unescape(ln)).strip() for ln in t.splitlines())
    return "\n".join(ln for ln in lines if ln)


# ---- weekly legal actions ----------------------------------------------------------------------------------
_SECTIONS = ("License Types", "File Information", "Licensee Details", "Proceedings")


def parse_legal_actions(page: str) -> tuple[str | None, list[dict[str, str]]]:
    """Parse one AJAX response of the Legal Actions Filed/Finalized report into flat rows.

    Each ``<h2>File Number …</h2>`` starts one file. Inside, ``Label:`` lines are followed by their value; the
    same label (``Status:``) appears in several sections, so keys are prefixed with the section name.
    Licence types repeat, so they are joined as ``type/status/issued`` items separated by ``; ``.
    """
    m = re.search(r"Report Date:\s*</strong>\s*([^<]+)", page)
    week = m.group(1).strip() if m else None
    rows: list[dict[str, str]] = []
    for block in re.split(r"(?=<h2[^>]*>\s*File Number)", page)[1:]:
        lines = _text(block).splitlines()
        if not lines or not lines[0].startswith("File Number"):
            continue
        row: dict[str, str] = {"file_number": lines[0].removeprefix("File Number").strip()}
        section = ""
        types: list[str] = []
        current_type: dict[str, str] = {}
        i = 1
        while i < len(lines):
            ln = lines[i]
            if ln in _SECTIONS:
                section = ln
                i += 1
                continue
            if section == "License Types":
                if re.fullmatch(r"Type \w+", ln):
                    if current_type:
                        types.append("/".join(current_type.get(k, "") for k in ("type", "status", "issued")))
                    current_type = {"type": ln.removeprefix("Type ").strip()}
                elif ln.endswith(":") and i + 1 < len(lines) and current_type:
                    label = ln[:-1].strip().lower()
                    if label == "status":
                        current_type["status"] = lines[i + 1]
                    elif label == "issue date":
                        current_type["issued"] = lines[i + 1]
                    i += 1
                i += 1
                continue
            if ln.endswith(":"):
                value = lines[i + 1] if i + 1 < len(lines) and not lines[i + 1].endswith(":") else ""
                prefix = {
                    "File Information": "file",
                    "Licensee Details": "licensee",
                    "Proceedings": "proceeding",
                }.get(section, "file")
                key = f"{prefix}_{re.sub(r'[^a-z0-9]+', '_', ln[:-1].strip().lower()).strip('_')}"
                if key in row and value:
                    row[key] = f"{row[key]} | {value}"
                elif key not in row:
                    row[key] = value
                i += 2 if value else 1
                continue
            i += 1
        if current_type:
            types.append("/".join(current_type.get(k, "") for k in ("type", "status", "issued")))
        # The licence-type table (Type | MI | Status | Issued | Expires | Dups | Term) is the reliable source:
        # the Filed report leaves the per-type detail lines empty.
        table_types = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", block, re.S):
            cells = [
                _text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)
            ]  # type code is a <th>
            if len(cells) >= 4 and re.fullmatch(r"\d{1,3}", cells[0]):
                table_types.append(f"{cells[0]}/{cells[2]}/{cells[3]}")
        row["license_types"] = "; ".join(table_types or types)
        rows.append(drop_mailing(row))
    return week, rows


# ---- export diff -------------------------------------------------------------------------------------------
def read_export_csv(data: bytes) -> tuple[str, list[dict[str, str]]]:
    """Rows of ABC-DailyDataExport.csv (latin-1, one title line before the header) with mailing columns removed.

    Returns (title line, rows). Column names are stripped of the stray spaces ABC puts in some headers.
    """
    text = data.decode("latin-1").lstrip("﻿").lstrip("ï»¿")
    lines = text.splitlines()
    head = next(i for i, ln in enumerate(lines[:20]) if "File Number" in ln)
    title = lines[0].strip().strip('"') if head > 0 else ""
    reader = csv.DictReader(io.StringIO("\n".join(lines[head:])))
    rows = [drop_mailing({(k or "").strip(): (v or "").strip() for k, v in r.items()}) for r in reader]
    return title, rows


def export_key(row: dict[str, str]) -> tuple[str, str, str]:
    """(File Number, License Type, Lic or App), leading zeros stripped. Not unique: a file can carry several
    application rows of one type, and the export repeats some rows verbatim."""
    return (
        row.get("File Number", "").lstrip("0"),
        row.get("License Type", "").lstrip("0"),
        row.get("Lic or App", ""),
    )


def diff_exports(old: Sequence[dict[str, str]], new: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    """What changed between two copies of the export.

    Rows are compared as a multiset of whole rows, so duplicates and non-unique keys cannot produce phantom
    changes. A removed row and an added row with the same key are paired: ``status_changed`` when the
    ``Type Status`` differs, ``updated`` when only other fields did (a renewed expiry date). Unpaired rows are
    ``added`` or ``removed``.
    """
    cols = _columns([*old[:1], *new[:1]])

    def as_tuple(r: dict[str, str]) -> tuple[str, ...]:
        return tuple(r.get(c, "") for c in cols)

    gone = Counter(as_tuple(r) for r in old)
    came = Counter(as_tuple(r) for r in new)
    removed = [dict(zip(cols, t, strict=True)) for t in (gone - came).elements()]
    added = [dict(zip(cols, t, strict=True)) for t in (came - gone).elements()]

    by_key: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for r in removed:
        by_key.setdefault(export_key(r), []).append(r)
    out: list[dict[str, str]] = []
    for r in added:
        olds = by_key.get(export_key(r))
        if olds:
            before = olds.pop(0)
            old_status = before.get(EXPORT_STATUS, "")
            change = "status_changed" if old_status != r.get(EXPORT_STATUS, "") else "updated"
            out.append({"change": change, "old_status": old_status, **r})
        else:
            out.append({"change": "added", "old_status": "", **r})
    for rows in by_key.values():
        for r in rows:
            out.append({"change": "removed", "old_status": r.get(EXPORT_STATUS, ""), **r})
    return out


# ---- the archive -------------------------------------------------------------------------------------------
@dataclass
class Saved:
    kind: str  # daily | weekly | export
    report: str
    date: str
    rows: int
    changed: bool
    note: str = ""


LOCK_NAME = ".archive.lock"


class UnexpectedPageError(RuntimeError):
    """A 200 response that is not an ABC page (a block or challenge page, an error shell)."""


def is_stop_error(exc: BaseException) -> bool:
    """Errors that end a run at once, with no retry: blocked, rate-limited, timing out, or not ABC's page."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (403, 429) or exc.response.status_code >= 500
    return isinstance(exc, httpx.TimeoutException | httpx.TransportError | UnexpectedPageError)


@contextmanager
def repo_lock(repo: Path) -> Iterator[None]:
    """Exclusive lock shared by the daily collector and the backfill, so only one talks to ABC at a time."""
    repo.mkdir(parents=True, exist_ok=True)
    with (repo / LOCK_NAME).open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


class Archive:
    def __init__(
        self, repo: Path, client: httpx.Client, delay: float = 3.0, raw_root: Path | None = None
    ) -> None:
        """``raw_root``: write raw pages under this folder (the backfill's staging area) instead of beside
        the CSVs in the repository."""
        self.repo = repo
        self.client = client
        self.delay = delay
        self.raw_root = raw_root
        self._last = 0.0
        self.requests = 0

    # polite, sequential requests
    def _wait(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self._last = time.monotonic()

    def get(self, url: str) -> httpx.Response:
        self._wait()
        self.requests += 1
        r = self.client.get(url)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "html" in ctype and ("abc.ca.gov" not in r.text or len(r.text) < 5000):
            raise UnexpectedPageError(f"{url}: {len(r.text)} bytes that do not look like an ABC page")
        return r

    def post(self, url: str, data: dict[str, str], referer: str) -> httpx.Response:
        self._wait()
        self.requests += 1
        r = self.client.post(
            url, data=data, headers={"Referer": referer, "X-Requested-With": "XMLHttpRequest"}
        )
        r.raise_for_status()
        return r

    # daily reports
    def save_daily(self, slug: str, day: dt.date) -> Saved:
        rpttype = DAILY[slug]
        page = self.get(f"{REPORTS}/{slug}/?RPTTYPE={rpttype}&RPTDATE={day.strftime('%m/%d/%Y')}").text
        report_date, rows = parse_report_html(page)
        if report_date != day:
            # weekends/holidays (and dates outside the report's history) render without a table
            return Saved("daily", slug, day.isoformat(), 0, False, "no report for this date")
        rows = [drop_mailing(r) for r in rows]
        folder = self.repo / "daily" / day.isoformat()
        data = csv_bytes(rows)
        changed = write_if_changed(folder / f"{slug}.csv", data)
        raw = (
            self.raw_root / "daily" / str(day.year) / slug / f"{day.isoformat()}.html.gz"
            if self.raw_root
            else folder / f"{slug}.html.gz"
        )
        if changed or not raw.exists():
            write_if_changed(raw, gzip_bytes(page.encode()))
        return Saved("daily", slug, day.isoformat(), len(rows), changed)

    # weekly legal actions
    def week_endings(self, slug: str) -> tuple[list[str], str]:
        page = self.get(f"{REPORTS}/{slug}/").text
        nonce_m = re.search(r'name="abclqs_dynamic_report" value="([^"]+)"', page)
        if not nonce_m:
            raise RuntimeError(f"{slug}: no form nonce on the page")
        weeks = re.findall(r'<option value="(\d\d-\d\d-\d{4})"', page)
        return weeks, nonce_m.group(1)

    def save_weekly(self, slug: str, week: str, nonce: str) -> Saved:
        page = self.post(
            AJAX_URL,
            {
                "action": "abclqs_dynamic_report",
                "nonce": nonce,
                "params[rpttype]": WEEKLY[slug],
                "params[week_ending]": week,
            },
            referer=f"{REPORTS}/{slug}/",
        ).text
        _, rows = parse_legal_actions(page)
        iso = dt.datetime.strptime(week, "%m-%d-%Y").date().isoformat()
        folder = self.repo / "weekly" / slug / iso
        changed = write_if_changed(folder / "rows.csv", csv_bytes(rows))
        raw = (
            self.raw_root / "weekly" / iso[:4] / slug / f"{iso}.html.gz"
            if self.raw_root
            else folder / "raw.html.gz"
        )
        if changed or not raw.exists():
            write_if_changed(raw, gzip_bytes(page.encode()))
        return Saved("weekly", slug, iso, len(rows), changed)

    # daily data export
    def save_export(self) -> Saved:
        resp = self.get(EXPORT_URL)
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            title, rows = read_export_csv(z.read(name))
        stamp = resp.headers.get("last-modified")
        day = dt.datetime.strptime(stamp, "%a, %d %b %Y %H:%M:%S GMT").date() if stamp else dt.date.today()
        columns = _columns(rows)
        export_dir = self.repo / "export"
        latest = export_dir / "latest.csv.gz"
        note = title
        changed = False
        baseline_dir = export_dir / "baseline"
        if not baseline_dir.exists() or not any(baseline_dir.glob("*.csv.gz")):
            blob = gzip_bytes(csv_bytes(rows, columns))
            if len(blob) > 50 * 1024 * 1024:
                note += " | baseline over 50 MB, not written"
            else:
                changed |= write_if_changed(baseline_dir / f"{day.isoformat()}.csv.gz", blob)
        if latest.exists():
            _, old = read_export_csv_gz(latest)
            changes = diff_exports(old, rows)
            if changes:
                cols = ["change", "old_status", *columns]
                changed |= write_if_changed(
                    export_dir / "changes" / f"{day.isoformat()}.csv", csv_bytes(changes, cols)
                )
            note += f" | {len(changes)} changes"
        latest.parent.mkdir(parents=True, exist_ok=True)
        write_if_changed(latest, gzip_bytes(csv_bytes(rows, columns)))
        return Saved("export", "daily-data-export", day.isoformat(), len(rows), changed, note)

    def write_index(self) -> None:
        recs: list[dict[str, str]] = []
        for p in sorted((self.repo / "daily").glob("*/*.csv")):
            recs.append(_index_row("daily", p.stem, p.parent.name, p))
        for p in sorted((self.repo / "weekly").glob("*/*/rows.csv")):
            recs.append(_index_row("weekly", p.parent.parent.name, p.parent.name, p))
        write_if_changed(
            self.repo / "index.csv", csv_bytes(recs, ["kind", "report", "date", "rows", "sha256"])
        )


def read_export_csv_gz(path: Path) -> tuple[str, list[dict[str, str]]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        return "", list(csv.DictReader(fh))


def _index_row(kind: str, report: str, date: str, path: Path) -> dict[str, str]:
    data = path.read_bytes()
    rows = max(0, data.count(b"\n") - 1)
    return {
        "kind": kind,
        "report": report,
        "date": date,
        "rows": str(rows),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def recent_days(n: int, today: dt.date | None = None) -> list[dt.date]:
    """The ``n`` calendar days before ``today`` (today's report is still filling up)."""
    today = today or dt.date.today()
    return [today - dt.timedelta(days=k) for k in range(1, n + 1)]


def date_range(start: dt.date, end: dt.date) -> list[dt.date]:
    return [start + dt.timedelta(days=k) for k in range((end - start).days + 1)]


GITIGNORE = "export/latest.csv.gz\n*.tmp\n.DS_Store\n.archive.lock\n"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def commit(
    repo: Path, message: str, push: bool, today: dt.date | None = None, heartbeat: bool = True
) -> bool:
    """Commit everything under ``repo``. A one-line heartbeat (the run date) changes every day, so the
    nightly freshness check in the app repository measures whether this job ran, not whether ABC published."""
    write_if_changed(repo / ".gitignore", GITIGNORE.encode())
    if heartbeat:  # only the daily collector proves it is alive; backfill commits pass heartbeat=False
        write_if_changed(repo / "last_run.txt", f"{(today or dt.date.today()).isoformat()}\n".encode())
    git(repo, "add", "-A")
    if not git(repo, "status", "--porcelain").strip():
        return False
    git(repo, "commit", "-q", "-m", message)
    if push:
        git(repo, "push", "-q")
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="abc-archive", description=__doc__.split("\n\n")[0] if __doc__ else None)
    p.add_argument("--repo", type=Path, required=True, help="checkout of the abc-archive-data repository")
    p.add_argument(
        "--days", type=int, default=6, help="calendar days of daily reports before today (default 6)"
    )
    p.add_argument("--from", dest="start", type=dt.date.fromisoformat, help="backfill start (YYYY-MM-DD)")
    p.add_argument("--to", dest="end", type=dt.date.fromisoformat, help="backfill end (YYYY-MM-DD)")
    p.add_argument("--reports", nargs="*", default=list(DAILY), choices=list(DAILY))
    p.add_argument("--weeks", type=int, default=2, help="most recent weekly legal-action reports (default 2)")
    p.add_argument("--no-export", action="store_true")
    p.add_argument("--delay", type=float, default=3.0, help="seconds between requests (default 3)")
    p.add_argument("--commit", action="store_true")
    p.add_argument("--push", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
    )

    days = (
        date_range(args.start, args.end or dt.date.today() - dt.timedelta(days=1))
        if args.start
        else recent_days(args.days)
    )
    saved: list[Saved] = []
    failures: list[str] = []
    stopped = False

    def attempt(label: str, fn: Callable[[], None]) -> None:
        nonlocal stopped
        if stopped:
            return
        try:
            fn()
        except Exception as exc:
            failures.append(f"{label}: {type(exc).__name__}: {exc}")
            if is_stop_error(exc):
                stopped = True
                failures.append("stopped: ABC refused, rate-limited, timed out or served an unexpected page")

    with (
        repo_lock(args.repo),
        httpx.Client(headers={"User-Agent": user_agent()}, follow_redirects=True, timeout=120) as client,
    ):
        arc = Archive(args.repo, client, delay=args.delay)
        for day in days:
            for slug in args.reports:

                def daily(slug: str = slug, day: dt.date = day) -> None:
                    saved.append(arc.save_daily(slug, day))

                attempt(f"daily {slug} {day}", daily)
        if args.weeks > 0:
            for slug in WEEKLY:

                def weekly(slug: str = slug) -> None:
                    weeks, nonce = arc.week_endings(slug)
                    for week in weeks[: args.weeks]:
                        saved.append(arc.save_weekly(slug, week, nonce))

                attempt(f"weekly {slug}", weekly)
        if not args.no_export:
            attempt("export", lambda: saved.append(arc.save_export()))
        arc.write_index()

    for s in saved:
        log.info(
            "%-7s %-24s %s rows=%-5d %s %s",
            s.kind,
            s.report,
            s.date,
            s.rows,
            "changed" if s.changed else "same",
            s.note,
        )
    for f in failures:
        log.error(f)
    if args.commit:
        last = max(
            (s.date for s in saved if s.kind == "daily" and s.rows), default=dt.date.today().isoformat()
        )
        with repo_lock(args.repo):
            made = commit(
                args.repo,
                f"ABC reports through {last} ({sum(s.changed for s in saved)} files changed)",
                args.push,
            )
        log.info("commit: %s", "made" if made else "nothing to commit")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
