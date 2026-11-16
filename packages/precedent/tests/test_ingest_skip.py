"""`--skip` leaves a source out without failing the run and says how stale that source is."""

from __future__ import annotations

import datetime as dt

import pytest

from precedent.ingest import select_sources, skip_notice
from precedent.models import IngestionRun
from precedent.store.local import LocalStore

UTC = dt.UTC


def _run(status: str, day: int, rows: int = 0) -> IngestionRun:
    started = dt.datetime(2026, 10, day, 20, 0, tzinfo=UTC)
    return IngestionRun(
        source="abc",
        started_at=started,
        finished_at=started + dt.timedelta(minutes=5),
        status=status,
        rows_upserted=rows,
    )


def test_select_sources_removes_skipped() -> None:
    available = {"abc", "datasf_planning", "static"}
    assert select_sources(["abc", "datasf_planning", "static"], ["abc"], available) == [
        "datasf_planning",
        "static",
    ]


def test_select_sources_rejects_unknown_names() -> None:
    with pytest.raises(SystemExit):
        select_sources(["datasf_planning"], ["nope"], {"datasf_planning"})


def test_skip_notice_names_last_success_and_newer_failure() -> None:
    latest = {"status": "failed", "finished_at": "2026-11-08T04:29:02+00:00"}
    assert skip_notice("abc", _run("ok", 28, 439), latest) == (
        "abc: SKIPPED by request; last successful refresh 2026-10-28T20:05+00:00 (439 rows); "
        "latest attempt 2026-11-08T04:29:02+00:00 failed"
    )


def test_skip_notice_quiet_when_latest_is_the_success() -> None:
    assert skip_notice("abc", _run("ok", 28, 439), {"status": "ok"}).endswith("(439 rows)")


def test_skip_notice_when_never_run() -> None:
    assert "never been refreshed" in skip_notice("abc", None, None)


async def test_local_store_last_successful_run(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = LocalStore(tmp_path / "data")
    for run in (_run("ok", 20, 400), _run("ok", 28, 439), _run("failed", 30)):
        await store.record_run(run)
    last = await store.last_successful_run("abc")
    assert last is not None and last.rows_upserted == 439
    assert await store.last_successful_run("datasf_planning") is None


async def test_postgis_last_successful_run() -> None:
    from tests.conftest import pg_url, requires_postgis

    if pg_url() is None:
        pytest.skip(requires_postgis.kwargs["reason"])
    from precedent.store.postgres import PostgresStore

    s = PostgresStore(pg_url() or "")
    await s.ensure_schema()
    try:
        for run in (_run("ok", 20, 400), _run("ok", 28, 439), _run("failed", 30)):
            await s.record_run(run)
        last = await s.last_successful_run("abc")
        assert last is not None and last.rows_upserted == 439 and last.status == "ok"
    finally:
        async with s.pool.connection() as conn:
            await conn.execute("delete from ingestion_runs where source = 'abc'")
        await s.close()
