"""Street-centreline points a metre outside the parcel-based zoning polygon still resolve to that district."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from precedent.models import Overlay
from precedent.store.local import LocalStore
from tests.conftest import pg_url, requires_postgis

NOW = dt.datetime(2026, 10, 21, tzinfo=dt.UTC)
# a block polygon; the test point sits 1 m east of its eastern edge, another 60 m away
BLOCK = {
    "type": "Polygon",
    "coordinates": [
        [
            [-122.4220, 37.7570],
            [-122.4214, 37.7570],
            [-122.4214, 37.7580],
            [-122.4220, 37.7580],
            [-122.4220, 37.7570],
        ]
    ],
}
EDGE_LNG = -122.4214
NEAR = (37.7575, EDGE_LNG + 0.0000113)  # ≈1 m east
FAR = (37.7575, EDGE_LNG + 0.00068)  # ≈60 m east

ROW = Overlay(
    id="datasf_zoning:NCT-VALENCIA",
    kind="zoning_district",
    name="NCT-VALENCIA",
    rules="Valencia Street NCT",
    code_section="Planning Code § 762",
    geom=BLOCK,
    bar_permission="conditional",
    restaurant_permission="principal",
    source="datasf_zoning",
    source_url="https://data.sf.gov/d/3i4a-hu95",
    fetched_at=NOW,
)


async def test_local_store_snaps_to_nearest_zoning(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    await store.upsert_overlays([ROW])
    assert (await store.zoning_at(*NEAR)) is not None and (
        await store.zoning_at(*NEAR)
    ).district == "NCT-VALENCIA"  # type: ignore[union-attr]
    assert await store.zoning_at(*FAR) is None


@requires_postgis
async def test_postgis_snaps_to_nearest_zoning() -> None:
    from precedent.store.postgres import PostgresStore

    s = PostgresStore(pg_url() or "")
    await s.ensure_schema()
    try:
        async with s.pool.connection() as conn:
            await conn.execute("delete from overlays where id = 'datasf_zoning:NCT-VALENCIA'")
        await s.upsert_overlays([ROW])
        near = await s.zoning_at(*NEAR)
        assert near is not None and near.district == "NCT-VALENCIA"
        assert await s.zoning_at(*FAR) is None
    finally:
        await s.close()
