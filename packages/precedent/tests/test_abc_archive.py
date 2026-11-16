"""The ABC report archiver: parsing, mailing-address removal, idempotent writes and the export diff."""

from __future__ import annotations

import datetime as dt
import gzip
from pathlib import Path

import httpx

from precedent.abc_archive import (
    Archive,
    csv_bytes,
    diff_exports,
    drop_mailing,
    gzip_bytes,
    parse_legal_actions,
    read_export_csv,
    recent_days,
    user_agent,
    write_if_changed,
)

FIXTURES = Path(__file__).parent / "fixtures" / "abc_archive"


def _daily_page(day: dt.date, rows: list[list[str]]) -> str:
    headers = [
        "License Number",
        "Status Changed From/To",
        "Prem Street",
        "City",
        "Mailing Addr.",
        "Mailing Street",
        "Mailing Zip Code",
    ]
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return (
        f"<p><strong>Report Date: </strong>{day.strftime('%A, %B %d, %Y')}</p>"
        f'<table id="license_report"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
    )


def _archive(tmp_path: Path, pages: dict[str, str]) -> Archive:
    def handler(request: httpx.Request) -> httpx.Response:
        for needle, page in pages.items():
            if needle in str(request.url):
                return httpx.Response(200, text=page)
        return httpx.Response(200, text="<p>no table</p>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Archive(tmp_path, client, delay=0)


def test_legal_actions_parse_one_row_per_file() -> None:
    week, rows = parse_legal_actions((FIXTURES / "legal_actions_finalized_sample.html").read_text())
    assert week == "Week ending 10/31/2026"
    assert [r["file_number"] for r in rows] == ["140562", "209197", "327095"]
    sf = rows[1]
    assert sf["licensee_premises_address"] == "3900 17TH ST, SAN FRANCISCO, CA 94114"
    assert sf["file_action"] == "ACCUSATION"
    assert sf["proceeding_penalty"] == "ALL STAYED"
    assert sf["license_types"] == "21/ACTIVE/21-DEC-1987"


def test_drop_mailing_removes_every_mailing_column_only() -> None:
    row = {
        "Mailing Addr.": "x",
        "Mailing Street": "x",
        "Mail Zip": "x",
        "licensee_mailing_address": "x",
        "Prem Street": "keep",
        "Email": "keep",
    }
    assert drop_mailing(row) == {"Prem Street": "keep", "Email": "keep"}


def test_csv_bytes_is_deterministic_and_sorted() -> None:
    a = csv_bytes([{"k": "2", "v": "b"}, {"k": "1", "v": "a"}])
    b = csv_bytes([{"k": "1", "v": "a"}, {"k": "2", "v": "b"}])
    assert a == b == b"k,v\n1,a\n2,b\n"
    assert gzip_bytes(a) == gzip_bytes(a)  # fixed mtime: identical bytes


def test_write_if_changed(tmp_path: Path) -> None:
    p = tmp_path / "a" / "b.csv"
    assert write_if_changed(p, b"x") is True
    assert write_if_changed(p, b"x") is False
    assert write_if_changed(p, b"y") is True


def test_daily_save_is_idempotent_and_drops_mailing(tmp_path: Path) -> None:
    day = dt.date(2026, 11, 3)
    page = _daily_page(
        day, [["123", "PEND | ACTIVE", "1 MAIN ST", "SAN FRANCISCO", "|", "PO BOX 1", "94110"]]
    )
    arc = _archive(tmp_path, {"status-changes": page})
    first = arc.save_daily("status-changes", day)
    second = arc.save_daily("status-changes", day)
    assert (first.rows, first.changed) == (1, True)
    assert (second.rows, second.changed) == (1, False)
    text = (tmp_path / "daily" / "2026-11-03" / "status-changes.csv").read_text()
    assert "Mailing" not in text and "PO BOX" not in text
    assert text.splitlines()[0] == "License Number,Status Changed From/To,Prem Street,City"
    raw = gzip.decompress((tmp_path / "daily" / "2026-11-03" / "status-changes.html.gz").read_bytes())
    assert b"license_report" in raw
    arc.write_index()
    index = (tmp_path / "index.csv").read_text().splitlines()
    assert index[0] == "kind,report,date,rows,sha256" and index[1].startswith(
        "daily,status-changes,2026-11-03,1,"
    )


def test_daily_page_for_another_date_is_not_saved(tmp_path: Path) -> None:
    page = _daily_page(dt.date(2026, 11, 6), [["1", "A | B", "", "", "", "", ""]])
    arc = _archive(tmp_path, {"status-changes": page})
    saved = arc.save_daily("status-changes", dt.date(2026, 11, 7))
    assert saved.rows == 0 and saved.note == "no report for this date"
    assert not (tmp_path / "daily").exists()


def test_export_diff_added_removed_status_changed() -> None:
    old = [
        {"File Number": "00000001", "License Type": "41", "Type Status": "PEND"},
        {"File Number": "00000002", "License Type": "47", "Type Status": "ACTIVE"},
        {"File Number": "00000003", "License Type": "20", "Type Status": "ACTIVE"},
    ]
    new = [
        {"File Number": "1", "License Type": "41", "Type Status": "ACTIVE"},
        {"File Number": "00000003", "License Type": "20", "Type Status": "ACTIVE"},
        {"File Number": "00000004", "License Type": "48", "Type Status": "PEND"},
    ]
    changes = {
        (c["change"], c["File Number"].lstrip("0"), c["old_status"], c["Type Status"])
        for c in diff_exports(old, new)
    }
    assert changes == {
        ("added", "4", "", "PEND"),
        ("removed", "2", "ACTIVE", "ACTIVE"),
        ("status_changed", "1", "PEND", "ACTIVE"),
    }


def test_read_export_csv_skips_title_and_mailing() -> None:
    data = (
        '﻿"Updated Monday 9th of November 2026 02:50:23 AM"\n'
        '"License Type","File Number","Type Status"," Prem Addr 2","Mail Addr 1","Mail Zip","Prem County"\n'
        '41,00000001,ACTIVE," ","PO BOX 9",94110,SAN FRANCISCO\n'
    ).encode("latin-1", errors="ignore")
    title, rows = read_export_csv(data)
    assert title.startswith("Updated Monday")
    assert rows == [
        {
            "License Type": "41",
            "File Number": "00000001",
            "Type Status": "ACTIVE",
            "Prem Addr 2": "",
            "Prem County": "SAN FRANCISCO",
        }
    ]


def test_recent_days_excludes_today() -> None:
    assert recent_days(2, dt.date(2026, 11, 9)) == [dt.date(2026, 11, 8), dt.date(2026, 11, 7)]


def test_user_agent_names_the_project_and_optional_contact() -> None:
    assert user_agent("") == "CA ABC public-report archiver/1.0 (independent research)"
    assert (
        user_agent("ops@example.org")
        == "CA ABC public-report archiver/1.0 (independent research; contact: ops@example.org)"
    )
    assert "memo" not in user_agent("x").lower()  # no app name in the archive's User-Agent


def test_commit_writes_heartbeat_and_is_a_noop_when_unchanged(tmp_path: Path) -> None:
    import subprocess

    from precedent.abc_archive import commit

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@example.org"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    day = dt.date(2026, 11, 9)
    assert commit(tmp_path, "first", push=False, today=day) is True
    assert (tmp_path / "last_run.txt").read_text() == "2026-11-09\n"
    assert commit(tmp_path, "again", push=False, today=day) is False
    assert commit(tmp_path, "next day", push=False, today=day + dt.timedelta(days=1)) is True


def test_export_diff_ignores_duplicates_and_reports_updates() -> None:
    lic = {
        "File Number": "00000009",
        "License Type": "47",
        "Lic or App": "LIC",
        "Type Status": "ACTIVE",
        "Expir Date": "2026",
    }
    app = {
        "File Number": "00000009",
        "License Type": "47",
        "Lic or App": "APP",
        "Type Status": "PEND",
        "Expir Date": "",
    }
    old = [lic, app, dict(app), dict(app)]  # repeated application rows, as in the real export
    assert diff_exports(old, list(reversed(old))) == []  # same rows, different order: nothing changed
    renewed = {**lic, "Expir Date": "2027"}
    granted = {**app, "Type Status": "ACTIVE"}
    changes = diff_exports(old, [renewed, granted, dict(app), dict(app)])
    assert sorted((c["change"], c["Lic or App"], c["old_status"]) for c in changes) == [
        ("status_changed", "APP", "PEND"),
        ("updated", "LIC", "ACTIVE"),
    ]


def test_filed_report_takes_licence_types_from_the_table() -> None:
    _, rows = parse_legal_actions((FIXTURES / "legal_actions_filed_sample.html").read_text())
    assert len(rows) == 2
    assert all(r["license_types"] and r["license_types"].count("/") >= 2 for r in rows)
    assert all(r["file_action"] == "ACCUSATION" for r in rows)
