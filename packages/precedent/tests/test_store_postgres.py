"""PostGIS store tests. Run with PRECEDENT_TEST_DATABASE_URL pointing at a database with PostGIS available."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from precedent.models import Application, Business, IngestionRun, OutcomeFeedback, Overlay
from tests.conftest import pg_url, requires_postgis

NOW = dt.datetime(2026, 10, 21, tzinfo=dt.UTC)
LAT, LNG = 37.7577, -122.4213  # 995 Valencia St
SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [[-122.43, 37.75], [-122.41, 37.75], [-122.41, 37.765], [-122.43, 37.765], [-122.43, 37.75]]
    ],
}
FAR_SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [[-122.50, 37.70], [-122.49, 37.70], [-122.49, 37.71], [-122.50, 37.71], [-122.50, 37.70]]
    ],
}

pytestmark = requires_postgis


def _app(i: int, dlat: float, dlng: float, **kw):  # type: ignore[no-untyped-def]
    base = dict(
        id=f"datasf_planning:T{i}",
        source="datasf_planning",
        source_id=f"T{i}",
        source_url=f"https://example.org/{i}",
        fetched_at=NOW,
        kind="cua",
        permit_type="Conditional Use Authorization",
        use_types=["bar"],
        description=f"test {i}",
        address=f"{i} Test St",
        lat=LAT + dlat,
        lng=LNG + dlng,
        status="Approved",
        outcome="approved",
        filed_at=dt.date(2024, 1, 1),
        decided_at=dt.date(2024, 6, 1),
    )
    base.update(kw)
    return Application.model_validate(base)


@pytest.fixture
async def store():  # type: ignore[no-untyped-def]
    from precedent.store.postgres import PostgresStore

    s = PostgresStore(pg_url() or "")
    await s.ensure_schema()
    async with s.pool.connection() as conn:
        for table in ("applications", "overlays", "businesses", "outcomes_feedback", "ingestion_runs"):
            await conn.execute(f"truncate {table}")
    yield s
    await s.close()


async def test_upsert_is_idempotent_and_merges_hearing_enrichment(store) -> None:  # type: ignore[no-untyped-def]
    a = _app(1, 0, 0)
    assert await store.upsert_applications([a, a]) == 2
    again = await store.upsert_applications([a.model_copy(update={"status": "Approved w/ conditions"})])
    assert again == 1
    got = await store.application(a.id)
    assert (
        got is not None and got.status == "Approved w/ conditions" and got.lat == pytest.approx(LAT, abs=1e-6)
    )
    # hearing enrichment: same id, richer fields, must not wipe existing values when incoming is empty
    enriched = a.model_copy(
        update={
            "source": "sf_planning_hearings",
            "conditions": ["Close by 2:00 a.m."],
            "opposition_noted": True,
            "decision_summary": "Motion 21000 approved with conditions",
            "extraction_confidence": "high",
        }
    )
    await store.upsert_applications([enriched])
    await store.upsert_applications([a])  # the nightly dataset refresh comes back with empty conditions
    got = await store.application(a.id)
    assert (
        got is not None
        and got.conditions == ["Close by 2:00 a.m."]
        and got.opposition_noted is True
        and got.decision_summary
    )
    async with store.pool.connection() as conn, conn.cursor() as cur:
        await cur.execute("select count(*) as n from applications")
        assert (await cur.fetchone())["n"] == 1


async def test_nearby_applications_distance_kind_and_window(store) -> None:  # type: ignore[no-untyped-def]
    rows = [
        _app(1, 0.0005, 0.0, decided_at=dt.date(2025, 1, 1)),  # ~55 m
        _app(2, 0.002, 0.0, kind="entertainment_poe", use_types=["live_entertainment"]),  # ~220 m
        _app(3, 0.01, 0.0),  # ~1.1 km → outside 1,000 ft
        _app(4, 0.0001, 0.0001, kind="abc_license", license_type="42", status="Active"),
        _app(5, 0.0003, 0.0, decided_at=dt.date(2018, 1, 1), filed_at=dt.date(2017, 1, 1)),
    ]
    await store.upsert_applications(rows)
    near = await store.nearby_applications(LAT, LNG, 304.8)
    ids = [n.item.id for n in near]
    assert ids == ["datasf_planning:T4", "datasf_planning:T5", "datasf_planning:T1", "datasf_planning:T2"]
    assert near[0].distance_m < near[-1].distance_m and 200 < near[-1].distance_m < 240
    cua_only = await store.nearby_applications(LAT, LNG, 304.8, kinds=["cua"])
    assert {n.item.id for n in cua_only} == {"datasf_planning:T1", "datasf_planning:T5"}
    recent = await store.nearby_applications(LAT, LNG, 304.8, kinds=["cua"], since=dt.date(2020, 1, 1))
    assert [n.item.id for n in recent] == ["datasf_planning:T1"]
    assert [n.item.id for n in await store.nearby_applications(LAT, LNG, 2000, limit=2)][:1] == [
        "datasf_planning:T4"
    ]


async def test_overlays_zoning_and_rule_attachment(store) -> None:  # type: ignore[no-untyped-def]
    await store.upsert_overlays(
        [
            Overlay(
                id="datasf_zoning:NCT-3",
                kind="zoning_district",
                name="NCT-3",
                rules="Moderate-scale NCT",
                code_section="Planning Code § 752",
                geom=SQUARE,
                source="datasf_zoning",
                source_url="https://data.sf.gov/d/z",
                fetched_at=NOW,
            ),
            Overlay(
                id="datasf_zoning:RH-2",
                kind="zoning_district",
                name="RH-2",
                rules="Residential",
                code_section="Planning Code § 209.1",
                geom=FAR_SQUARE,
                bar_permission="prohibited",
                restaurant_permission="prohibited",
                source="datasf_zoning",
                source_url="https://data.sf.gov/d/z",
                fetched_at=NOW,
            ),
            Overlay(
                id="static:sf:nc_rule",
                kind="nc_rule",
                name="NC bar rule",
                rules="Bars conditional, restaurants principal",
                code_section="§ 303",
                district_codes=["NCT-3"],
                bar_permission="conditional",
                restaurant_permission="principal",
                source="static",
                source_url="https://x",
                fetched_at=NOW,
            ),
            Overlay(
                id="static:sf:far_rule",
                kind="nc_rule",
                name="Other rule",
                rules="n/a",
                code_section="§ 1",
                district_codes=["NC-1"],
                source="static",
                source_url="https://x",
                fetched_at=NOW,
            ),
        ]
    )
    hits = await store.overlays_at(LAT, LNG)
    assert {o.id for o in hits} == {"datasf_zoning:NCT-3", "static:sf:nc_rule"}
    poly = next(o for o in hits if o.kind == "zoning_district")
    assert poly.geom and poly.geom["type"] == "MultiPolygon"
    z = await store.zoning_at(LAT, LNG)
    assert (
        z is not None
        and z.district == "NCT-3"
        and z.bar_permission == "conditional"
        and z.code_section == "§ 303"
    )
    assert await store.zoning_at(0.0, 0.0) is None
    # re-upserting the same polygon with new rules updates in place
    await store.upsert_overlays(
        [
            Overlay(
                id="datasf_zoning:NCT-3",
                kind="zoning_district",
                name="NCT-3",
                rules="updated",
                code_section="§ 752",
                geom=SQUARE,
                source="datasf_zoning",
                source_url="https://data.sf.gov/d/z",
                fetched_at=NOW,
            )
        ]
    )
    assert (
        next(o for o in await store.overlays_at(LAT, LNG) if o.kind == "zoning_district").rules == "updated"
    )


async def test_businesses_feedback_runs_and_status(store) -> None:  # type: ignore[no-untyped-def]
    await store.upsert_businesses(
        [
            Business(
                id="datasf_business:1",
                dba_name="Bar One",
                naics_code="722410",
                address="1 Test",
                lat=LAT + 0.0002,
                lng=LNG,
                start_date=dt.date(2020, 1, 1),
                is_food_or_drink=True,
                is_bar=True,
                source_url="https://x",
                fetched_at=NOW,
            ),
            Business(
                id="datasf_business:2",
                dba_name="Closed Cafe",
                naics_code="722515",
                address="2 Test",
                lat=LAT + 0.0002,
                lng=LNG,
                start_date=dt.date(2015, 1, 1),
                end_date=dt.date(2022, 1, 1),
                is_food_or_drink=True,
                source_url="https://x",
                fetched_at=NOW,
            ),
        ]
    )
    active = await store.nearby_businesses(LAT, LNG, 152.4)
    assert [b.item.id for b in active] == ["datasf_business:1"]
    assert len(await store.nearby_businesses(LAT, LNG, 152.4, active_only=False)) == 2
    memo_id = str(uuid.uuid4())
    saved = await store.insert_feedback(
        OutcomeFeedback(
            memo_id=memo_id,
            user_id=None,
            address="995 Valencia St",
            lat=LAT,
            lng=LNG,
            concept_type="bar",
            outcome="approved_with_conditions",
            notes="1am close",
            reported_at=NOW,
        )
    )
    assert saved.id
    near = await store.feedback_near(LAT, LNG, 100)
    assert len(near) == 1 and near[0].item.outcome == "approved_with_conditions" and near[0].distance_m < 1
    stats = await store.feedback_stats()
    assert stats == {"total": 1, "by_outcome": {"approved_with_conditions": 1}, "by_concept": {"bar": 1}}
    await store.record_run(
        IngestionRun(
            source="datasf_business",
            started_at=NOW,
            finished_at=NOW,
            status="ok",
            rows_fetched=2,
            rows_upserted=2,
        )
    )
    status = await store.status()
    assert (
        status["backend"] == "postgis"
        and status["counts"]["businesses"] == 2
        and status["counts"]["feedback"] == 1
    )
    assert status["last_runs"]["datasf_business"]["status"] == "ok"


async def test_applications_of_kind_and_all_businesses(store) -> None:  # type: ignore[no-untyped-def]
    await store.upsert_applications(
        [_app(2, 0.0, 0.0), _app(1, 0.0, 0.0, kind="abc_license", license_type="48", status="ACTIVE")]
    )
    lic = await store.applications_of_kind("abc_license")
    assert [a.id for a in lic] == ["datasf_planning:T1"] and lic[0].lat == pytest.approx(LAT, abs=1e-6)
    assert [a.id for a in await store.applications_of_kind("cua")] == ["datasf_planning:T2"]
    biz = [
        Business(
            id=f"datasf_business:{i}",
            dba_name=f"Bar {i}",
            address=f"{i} Test St",
            lat=LAT,
            lng=LNG,
            is_food_or_drink=True,
            source_url="https://data.sf.gov/d/g8m3-pdis",
            fetched_at=NOW,
        )
        for i in (2, 1)
    ]
    await store.upsert_businesses(biz)
    got = await store.all_businesses()
    assert [b.id for b in got] == ["datasf_business:1", "datasf_business:2"]
    assert got[0].lng == pytest.approx(LNG, abs=1e-6) and got[0].is_bar is False
