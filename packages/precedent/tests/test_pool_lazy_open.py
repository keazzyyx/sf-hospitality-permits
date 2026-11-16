"""Regression: the store must open its pool on first query, not only after ensure_schema().

The API, the nightly jobs and the memo demo construct PostgresStore and query it directly; before the
fix the first query raised psycopg_pool.PoolClosed ("the pool is not open yet") in production.
"""

from __future__ import annotations

import pytest

from tests.conftest import pg_url, requires_postgis


@requires_postgis
@pytest.mark.asyncio
async def test_queries_open_the_pool_lazily() -> None:
    from precedent.store.postgres import PostgresStore

    s = PostgresStore(pg_url() or "")
    assert s.pool.closed
    try:
        rows = await s.nearby_applications(37.757, -122.4208, radius_m=100.0)
        assert isinstance(rows, list)
        await s.zoning_at(37.757, -122.4208)
        assert not s.pool.closed
    finally:
        await s.close()
