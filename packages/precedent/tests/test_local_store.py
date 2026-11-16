"""The JSONL store must behave like the PostGIS store for the memo tools."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from precedent.models import Application, Overlay
from precedent.store.local import LocalStore

NOW = dt.datetime(2026, 10, 21, tzinfo=dt.UTC)
LAT, LNG = 37.7577, -122.4213
SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [[-122.43, 37.75], [-122.41, 37.75], [-122.41, 37.765], [-122.43, 37.765], [-122.43, 37.75]]
    ],
}


def _app(i: int, dlat: float, **kw):  # type: ignore[no-untyped-def]
    base = dict(
        id=f"datasf_planning:L{i}",
        source="datasf_planning",
        source_id=f"L{i}",
        source_url="https://x",
        fetched_at=NOW,
        kind="cua",
        permit_type="CUA",
        use_types=["bar"],
        lat=LAT + dlat,
        lng=LNG,
        outcome="approved",
        decided_at=dt.date(2024, 1, 1),
    )
    base.update(kw)
    return Application.model_validate(base)


async def test_local_store_persists_and_queries(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    await store.upsert_applications([_app(1, 0.0005), _app(2, 0.01), _app(1, 0.0005, status="dup")])
    await store.upsert_overlays(
        [
            Overlay(
                id="datasf_zoning:NCT-3",
                kind="zoning_district",
                name="NCT-3",
                rules="x",
                code_section="§ 752",
                geom=SQUARE,
                source="datasf_zoning",
                source_url="https://x",
                fetched_at=NOW,
            ),
            Overlay(
                id="static:rule",
                kind="nc_rule",
                name="rule",
                rules="bars conditional",
                code_section="§ 303",
                district_codes=["NCT-3"],
                bar_permission="conditional",
                restaurant_permission="principal",
                source="static",
                source_url="https://x",
                fetched_at=NOW,
            ),
        ]
    )
    near = await store.nearby_applications(LAT, LNG, 304.8)
    assert (
        [n.item.id for n in near] == ["datasf_planning:L1"]
        and near[0].item.status == "dup"
        and 50 < near[0].distance_m < 60
    )
    z = await store.zoning_at(LAT, LNG)
    assert z is not None and z.district == "NCT-3" and z.bar_permission == "conditional"
    reopened = LocalStore(tmp_path)  # snapshots survive a restart
    assert len(reopened.applications) == 2 and len(await reopened.overlays_at(LAT, LNG)) == 2
    status = await reopened.status()
    assert status["backend"] == "local" and status["counts"]["applications"] == 2
