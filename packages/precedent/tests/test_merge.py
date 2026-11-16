"""Hearing-enrichment merge rules: identical behaviour in the pure function (LocalStore) and in PostGIS."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from precedent.models import Application
from precedent.store.base import merge_applications
from precedent.store.local import LocalStore
from tests.conftest import pg_url, requires_postgis

NOW = dt.datetime(2026, 10, 21, tzinfo=dt.UTC)
LAT, LNG = 37.7577, -122.4213


def planning_row(**kw):  # type: ignore[no-untyped-def]
    base = dict(
        id="datasf_planning:2025-010163CUA",
        source="datasf_planning",
        source_id="2025-010163CUA",
        source_url="https://data.sf.gov/d/y673-d69b",
        fetched_at=NOW,
        raw_ref="raw/p1.json",
        kind="cua",
        permit_type="Conditional Use Authorization",
        use_types=["bar"],
        description="Bar with live music at 4100 24th St",
        address="4100 24th St",
        lat=LAT,
        lng=LNG,
        parcel="6508/028",
        zoning_district="NCD-24TH",
        status="Open",
        outcome="pending",
        filed_at=dt.date(2025, 9, 1),
        decided_at=None,
        hours_close="01:00",
        late_night=True,
    )
    base.update(kw)
    return Application.model_validate(base)


def hearing_row(**kw):  # type: ignore[no-untyped-def]
    base = dict(
        id="datasf_planning:2025-010163CUA",
        source="sf_planning_hearings",
        source_id="2025-010163CUA",
        source_url="https://citypln-m-extnl.sfgov.org/External/link.ashx?M-21928",
        fetched_at=NOW + dt.timedelta(days=1),
        raw_ref="raw/h1.json",
        kind="cua",
        permit_type="Conditional Use Authorization",
        use_types=[],
        description="",
        address=None,
        lat=None,
        lng=None,
        parcel=None,
        zoning_district=None,
        status="",
        outcome="approved_with_conditions",
        filed_at=None,
        decided_at=dt.date(2026, 7, 9),
        hours_close="02:00",
        late_night=True,
        conditions=["Hours of operation shall end at 2:00 a.m.", "Community Liaison"],
        opposition_noted=False,
        decision_summary="Motion 21928 approved with conditions 4-0",
        extraction_confidence="high",
        extra={"motion_number": "21928", "vote": "4-0"},
    )
    base.update(kw)
    return Application.model_validate(base)


def _assert_enriched(got: Application) -> None:
    assert (
        got.source == "datasf_planning"
        and got.source_url.startswith("https://data.sf.gov")
        and got.raw_ref == "raw/p1.json"
    )
    assert (
        got.lat == pytest.approx(LAT)
        and got.lng == pytest.approx(LNG)
        and got.parcel == "6508/028"
        and got.address == "4100 24th St"
    )
    assert got.use_types == ["bar"] and got.description.startswith("Bar with") and got.status == "Open"
    assert (
        got.outcome == "approved_with_conditions"
        and got.decided_at == dt.date(2026, 7, 9)
        and got.filed_at == dt.date(2025, 9, 1)
    )
    assert got.hours_close == "02:00" and got.late_night is True
    assert (
        got.conditions == ["Hours of operation shall end at 2:00 a.m.", "Community Liaison"]
        and got.opposition_noted is False
    )
    assert got.decision_summary and got.extraction_confidence == "high"
    assert got.extra["motion_number"] == "21928" and got.extra["motion_url"].startswith("https://citypln")


def test_pure_merge_both_directions() -> None:
    # dataset first, then hearing
    _assert_enriched(merge_applications(planning_row(), hearing_row()))
    # hearing first, then dataset refresh (still pending in the dataset) → enrichment and decided outcome survive
    _assert_enriched(merge_applications(hearing_row(), planning_row()))
    # a later dataset refresh that now says denied wins over the hearing's older reading
    got = merge_applications(
        merge_applications(planning_row(), hearing_row()),
        planning_row(outcome="denied", status="Disapproved"),
    )
    assert got.outcome == "denied" and got.status == "Disapproved" and got.conditions  # enrichment kept
    # hours read from the hearing survive dataset refreshes; hours the hearing did not give do refresh
    got = merge_applications(
        merge_applications(planning_row(), hearing_row()), planning_row(hours_close="23:00", late_night=False)
    )
    assert got.hours_close == "02:00" and got.extra["hours_source"] == "hearing"
    got = merge_applications(
        merge_applications(planning_row(), hearing_row(hours_close=None, late_night=None)),
        planning_row(hours_close="23:00", late_night=False),
    )
    assert got.hours_close == "23:00" and "hours_source" not in got.extra


async def test_local_store_merges(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    await store.upsert_applications([hearing_row()])
    await store.upsert_applications([planning_row()])
    got = await store.application("datasf_planning:2025-010163CUA")
    assert got is not None
    _assert_enriched(got)
    assert len(await store.nearby_applications(LAT, LNG, 50)) == 1  # geometry present → spatially queryable


@requires_postgis
async def test_postgis_merges_identically() -> None:
    from precedent.store.postgres import PostgresStore

    s = PostgresStore(pg_url() or "")
    await s.ensure_schema()
    try:
        async with s.pool.connection() as conn:
            await conn.execute("delete from applications where id = 'datasf_planning:2025-010163CUA'")
        for order in ((planning_row(), hearing_row()), (hearing_row(), planning_row())):
            async with s.pool.connection() as conn:
                await conn.execute("delete from applications where id = 'datasf_planning:2025-010163CUA'")
            for row in order:
                await s.upsert_applications([row])
            got = await s.application("datasf_planning:2025-010163CUA")
            assert got is not None
            _assert_enriched(got)
            # other PostGIS tests may leave rows at these coordinates; the merged case must appear exactly once
            near = [n.item.id for n in await s.nearby_applications(LAT, LNG, 50)]
            assert near.count("datasf_planning:2025-010163CUA") == 1
        await s.upsert_applications([planning_row(outcome="denied", status="Disapproved")])
        got = await s.application("datasf_planning:2025-010163CUA")
        assert got is not None and got.outcome == "denied" and got.conditions and got.hours_close == "02:00"
    finally:
        await s.close()
