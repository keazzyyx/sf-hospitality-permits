"""The ABC backfill: resumes without re-fetching, stops at once on 403, and packs only verified archives."""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

import httpx

from precedent.abc_backfill import STATE_NAME, State, pack, run

PAD = "<!-- www.abc.ca.gov -->" + " " * 6000  # real pages are large and mention abc.ca.gov


def _page(day: dt.date, n: int) -> str:
    head = "".join(
        f"<th>{h}</th>" for h in ("License Number", "Status Changed From/To", "Mailing Street", "County")
    )
    body = "".join(
        f"<tr><td>{i}</td><td>PEND | ACTIVE</td><td>PO BOX {i}</td><td>38</td></tr>" for i in range(n)
    )
    return (
        f"<html>{PAD}<p><strong>Report Date: </strong>{day.strftime('%A, %B %d, %Y')}</p>"
        f'<table id="license_report"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></html>'
    )


def _empty() -> str:
    return f"<html>{PAD}<p>no table</p></html>"


def _args(repo: Path, staging: Path, start: dt.date, end: dt.date, **over: object) -> argparse.Namespace:
    base = {
        "repo": repo,
        "staging": staging,
        "start": start,
        "to": end,
        "delay": 0.0,
        "commit_every": 1000,
        "newapp_empty_days": 30,
        "no_weekly": True,
        "commit": False,
        "push": False,
    }
    base.update(over)
    return argparse.Namespace(**base)


class Fake:
    """Serves daily report pages; dates in ``empty`` have no report; ``fail_after`` requests then 403."""

    def __init__(self, empty: set[dt.date] = frozenset(), fail_after: int | None = None) -> None:  # type: ignore[assignment]
        self.empty = set(empty)
        self.fail_after = fail_after
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            return httpx.Response(403, text="Forbidden")
        m = re.search(r"RPTDATE=(\d\d)/(\d\d)/(\d{4})", str(request.url))
        assert m, request.url
        day = dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        page = _empty() if day in self.empty else _page(day, 2)
        return httpx.Response(200, text=page, headers={"content-type": "text/html"})


def _client(fake: Fake) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(fake))


START, END = dt.date(2026, 1, 1), dt.date(2026, 1, 3)


def test_run_saves_csvs_and_stages_raw_then_resumes_without_requests(tmp_path: Path) -> None:
    repo, staging = tmp_path / "repo", tmp_path / "staging"
    fake = Fake(empty={dt.date(2026, 1, 2)})
    assert run(_args(repo, staging, START, END), client=_client(fake)) == 0
    assert len(fake.calls) == 9  # 3 days x 3 reports
    csv = (repo / "daily" / "2026-01-03" / "status-changes.csv").read_text()
    assert "Mailing" not in csv and "PO BOX" not in csv
    assert (staging / "raw" / "daily" / "2026" / "status-changes" / "2026-01-03.html.gz").exists()
    assert not (
        repo / "daily" / "2026-01-03" / "status-changes.html.gz"
    ).exists()  # raw stays out of the repo
    state = State.load(staging / STATE_NAME)
    assert "status-changes|2026-01-02" in state.no_report

    again = Fake(empty={dt.date(2026, 1, 2)})
    assert run(_args(repo, staging, START, END), client=_client(again)) == 0
    assert again.calls == []


def test_run_stops_at_the_first_403_and_resumes_later(tmp_path: Path) -> None:
    repo, staging = tmp_path / "repo", tmp_path / "staging"
    blocked = Fake(fail_after=4)
    assert run(_args(repo, staging, START, END), client=_client(blocked)) == 2
    assert len(blocked.calls) == 5  # four pages, then the 403, then nothing
    assert State.load(staging / STATE_NAME).stopped
    resumed = Fake()
    assert run(_args(repo, staging, START, END), client=_client(resumed)) == 0
    assert len(resumed.calls) == 5  # only what was left


def test_new_applications_stop_after_an_empty_streak(tmp_path: Path) -> None:
    repo, staging = tmp_path / "repo", tmp_path / "staging"
    days = {START + dt.timedelta(days=k) for k in range(40)}
    fake = Fake(empty=days)
    end = START + dt.timedelta(days=39)
    run(_args(repo, staging, START, end, newapp_empty_days=5), client=_client(fake))
    newapp_calls = [c for c in fake.calls if "new-applications" in c]
    assert len(newapp_calls) == 5
    assert State.load(staging / STATE_NAME).newapp_stopped_before


def test_pack_verifies_before_deleting_and_refuses_on_mismatch(tmp_path: Path) -> None:
    repo, staging = tmp_path / "repo", tmp_path / "staging"
    run(_args(repo, staging, START, END), client=_client(Fake()))
    # corrupt one committed CSV: its year/report archive must not be written and its pages must stay loose
    (repo / "daily" / "2026-01-01" / "issued-licenses.csv").write_text("tampered\n")
    assert pack(repo, staging) == 1
    archives = sorted(p.relative_to(repo).as_posix() for p in (repo / "raw-archives").glob("*/*/*.tar.xz"))
    assert archives == [
        "raw-archives/daily/2026/new-applications-2026.tar.xz",
        "raw-archives/daily/2026/status-changes-2026.tar.xz",
    ]
    assert len(list((staging / "raw" / "daily" / "2026" / "issued-licenses").glob("*.html.gz"))) == 3
    assert not list((staging / "raw" / "daily" / "2026" / "status-changes").glob("*.html.gz"))
    sums = (repo / "raw-archives" / "SHA256SUMS").read_text().splitlines()
    assert len(sums) == 2 and all(len(line.split()[0]) == 64 for line in sums)
    members = (repo / "raw-archives" / "daily" / "2026" / "status-changes-2026.members.sha256").read_text()
    assert "status-changes/2026-01-03.html" in members
