"""PostGIS-backed store over psycopg3. Distances use geography (metres); overlays use ST_Covers."""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from precedent.models import (
    Application,
    ApplicationKind,
    Business,
    IngestionRun,
    OutcomeFeedback,
    Overlay,
)
from precedent.store.base import Nearby, ZoningInfo

SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text()


def _pt(lat: float | None, lng: float | None) -> str | None:
    return None if lat is None or lng is None else f"SRID=4326;POINT({lng} {lat})"


class PostgresStore:
    def __init__(self, database_url: str, *, min_size: int = 1, max_size: int = 6) -> None:
        self.pool = AsyncConnectionPool(
            database_url,
            min_size=min_size,
            max_size=max_size,
            open=False,
            kwargs={"row_factory": dict_row, "autocommit": True},
        )

    async def open(self) -> None:
        if self.pool.closed:
            await self.pool.open()

    async def ensure_schema(self) -> None:
        await self.open()
        async with self._connection() as conn:
            await conn.execute(SCHEMA_SQL)  # type: ignore[arg-type,unused-ignore]

    async def close(self) -> None:
        if not self.pool.closed:
            await self.pool.close()

    async def _conn(self) -> AsyncConnection[Any]:
        await self.open()
        return await self.pool.getconn()

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[AsyncConnection[Any]]:
        """Open the pool on first use. psycopg_pool >= 3.2 no longer opens it in the constructor,
        and the API/jobs never call ensure_schema(), so every query path goes through here."""
        await self.open()
        async with self.pool.connection() as conn:
            yield conn

    # ---- writes ----------------------------------------------------------------------------
    async def upsert_applications(self, rows: list[Application]) -> int:
        if not rows:
            return 0
        sql = """
        insert into applications (id, source, source_id, source_url, fetched_at, raw_ref, kind, permit_type, use_types,
          description, address, geom, parcel, zoning_district, status, outcome, filed_at, decided_at, hours_close,
          late_night, conditions, opposition_noted, decision_summary, extraction_confidence, license_type, extra, updated_at)
        values (%(id)s, %(source)s, %(source_id)s, %(source_url)s, %(fetched_at)s, %(raw_ref)s, %(kind)s, %(permit_type)s,
          %(use_types)s, %(description)s, %(address)s, %(geom)s::geography, %(parcel)s, %(zoning_district)s, %(status)s,
          %(outcome)s, %(filed_at)s, %(decided_at)s, %(hours_close)s, %(late_night)s, %(conditions)s, %(opposition_noted)s,
          %(decision_summary)s, %(extraction_confidence)s, %(license_type)s, %(extra)s, now())
        on conflict (id) do update set
          -- enrichment rows (hearing motions/minutes) keep the dataset row's identity; dataset refreshes keep enrichment
          source      = case when excluded.source = 'sf_planning_hearings' then applications.source else excluded.source end,
          source_id   = case when excluded.source = 'sf_planning_hearings' then applications.source_id else excluded.source_id end,
          source_url  = case when excluded.source = 'sf_planning_hearings' then applications.source_url else excluded.source_url end,
          raw_ref     = case when excluded.source = 'sf_planning_hearings' then applications.raw_ref else excluded.raw_ref end,
          fetched_at  = greatest(excluded.fetched_at, applications.fetched_at),
          kind        = case when excluded.source = 'sf_planning_hearings' then applications.kind else excluded.kind end,
          permit_type = case when excluded.source = 'sf_planning_hearings' then applications.permit_type else excluded.permit_type end,
          use_types   = case when excluded.source = 'sf_planning_hearings'
                             then (case when cardinality(applications.use_types) > 0 then applications.use_types else excluded.use_types end)
                             else (case when cardinality(excluded.use_types) > 0 then excluded.use_types else applications.use_types end) end,
          description = case when excluded.source = 'sf_planning_hearings'
                             then coalesce(nullif(applications.description, ''), excluded.description)
                             else coalesce(nullif(excluded.description, ''), applications.description) end,
          address         = case when excluded.source = 'sf_planning_hearings' then coalesce(applications.address, excluded.address) else coalesce(excluded.address, applications.address) end,
          geom            = case when excluded.source = 'sf_planning_hearings' then coalesce(applications.geom, excluded.geom) else coalesce(excluded.geom, applications.geom) end,
          parcel          = case when excluded.source = 'sf_planning_hearings' then coalesce(applications.parcel, excluded.parcel) else coalesce(excluded.parcel, applications.parcel) end,
          zoning_district = case when excluded.source = 'sf_planning_hearings' then coalesce(applications.zoning_district, excluded.zoning_district) else coalesce(excluded.zoning_district, applications.zoning_district) end,
          status      = case when excluded.source = 'sf_planning_hearings' then applications.status else excluded.status end,
          outcome     = case
                          when excluded.source = 'sf_planning_hearings'
                            then (case when applications.outcome in ('unknown', 'pending') and excluded.outcome not in ('unknown', 'pending') then excluded.outcome else applications.outcome end)
                          when excluded.outcome in ('unknown', 'pending') and (applications.source = 'sf_planning_hearings' or applications.extra ? 'motion_url') and applications.outcome not in ('unknown', 'pending')
                            then applications.outcome
                          else excluded.outcome end,
          filed_at    = case when excluded.source = 'sf_planning_hearings' then coalesce(applications.filed_at, excluded.filed_at) else coalesce(excluded.filed_at, applications.filed_at) end,
          decided_at  = case when excluded.source = 'sf_planning_hearings' then coalesce(excluded.decided_at, applications.decided_at) else coalesce(excluded.decided_at, applications.decided_at) end,
          hours_close = case when excluded.source = 'sf_planning_hearings' then coalesce(excluded.hours_close, applications.hours_close)
                             when applications.extra->>'hours_source' = 'hearing' or (applications.source = 'sf_planning_hearings' and applications.hours_close is not null) then coalesce(applications.hours_close, excluded.hours_close)
                             else coalesce(excluded.hours_close, applications.hours_close) end,
          late_night  = case when excluded.source = 'sf_planning_hearings' then coalesce(excluded.late_night, applications.late_night)
                             when applications.extra->>'hours_source' = 'hearing' or (applications.source = 'sf_planning_hearings' and applications.hours_close is not null) then coalesce(applications.late_night, excluded.late_night)
                             else coalesce(excluded.late_night, applications.late_night) end,
          conditions  = case when cardinality(excluded.conditions) > 0 then excluded.conditions else applications.conditions end,
          opposition_noted      = coalesce(excluded.opposition_noted, applications.opposition_noted),
          decision_summary      = coalesce(excluded.decision_summary, applications.decision_summary),
          extraction_confidence = coalesce(excluded.extraction_confidence, applications.extraction_confidence),
          license_type = coalesce(excluded.license_type, applications.license_type),
          extra       = applications.extra || excluded.extra
                        || case when excluded.source = 'sf_planning_hearings' and excluded.source_url <> '' then jsonb_build_object('motion_url', excluded.source_url)
                                when applications.source = 'sf_planning_hearings' and applications.source_url <> '' then jsonb_build_object('motion_url', applications.source_url)
                                else '{}'::jsonb end
                        || case when (excluded.source = 'sf_planning_hearings' and excluded.hours_close is not null)
                                  or (applications.source = 'sf_planning_hearings' and applications.hours_close is not null)
                                then '{"hours_source": "hearing"}'::jsonb else '{}'::jsonb end,
          updated_at  = now()
        """
        params = [
            {
                **r.model_dump(exclude={"lat", "lng", "extra"}),
                "geom": _pt(r.lat, r.lng),
                "extra": Jsonb(r.extra),
            }
            for r in rows
        ]
        async with self._connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.executemany(sql, params)
        return len(rows)

    async def upsert_overlays(self, rows: list[Overlay]) -> int:
        if not rows:
            return 0
        sql = """
        insert into overlays (id, kind, name, rules, code_section, geom, district_codes, bar_permission,
          restaurant_permission, late_night_rule, source, source_url, fetched_at)
        values (%(id)s, %(kind)s, %(name)s, %(rules)s, %(code_section)s,
          case when %(geom)s::text is null then null else ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s::text), 4326)) end,
          %(district_codes)s, %(bar_permission)s, %(restaurant_permission)s, %(late_night_rule)s, %(source)s,
          %(source_url)s, %(fetched_at)s)
        on conflict (id) do update set kind = excluded.kind, name = excluded.name, rules = excluded.rules,
          code_section = excluded.code_section, geom = excluded.geom, district_codes = excluded.district_codes,
          bar_permission = excluded.bar_permission, restaurant_permission = excluded.restaurant_permission,
          late_night_rule = excluded.late_night_rule, source = excluded.source, source_url = excluded.source_url,
          fetched_at = excluded.fetched_at
        """
        params = [
            {**r.model_dump(exclude={"geom"}), "geom": json.dumps(r.geom) if r.geom else None} for r in rows
        ]
        async with self._connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.executemany(sql, params)
        return len(rows)

    async def upsert_businesses(self, rows: list[Business]) -> int:
        if not rows:
            return 0
        sql = """
        insert into businesses (id, dba_name, naics_code, naics_description, address, geom, start_date, end_date,
          is_food_or_drink, is_bar, source, source_url, fetched_at)
        values (%(id)s, %(dba_name)s, %(naics_code)s, %(naics_description)s, %(address)s, %(geom)s::geography,
          %(start_date)s, %(end_date)s, %(is_food_or_drink)s, %(is_bar)s, %(source)s, %(source_url)s, %(fetched_at)s)
        on conflict (id) do update set dba_name = excluded.dba_name, naics_code = excluded.naics_code,
          naics_description = excluded.naics_description, address = excluded.address, geom = excluded.geom,
          start_date = excluded.start_date, end_date = excluded.end_date, is_food_or_drink = excluded.is_food_or_drink,
          is_bar = excluded.is_bar, source_url = excluded.source_url, fetched_at = excluded.fetched_at
        """
        params = [{**r.model_dump(exclude={"lat", "lng"}), "geom": _pt(r.lat, r.lng)} for r in rows]
        async with self._connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.executemany(sql, params)
        return len(rows)

    async def record_run(self, run: IngestionRun) -> None:
        async with self._connection() as conn:
            await conn.execute(
                """insert into ingestion_runs (source, started_at, finished_at, status, rows_fetched, rows_upserted, error, notes)
                   values (%(source)s, %(started_at)s, %(finished_at)s, %(status)s, %(rows_fetched)s, %(rows_upserted)s, %(error)s, %(notes)s)""",
                run.model_dump(),
            )

    async def insert_feedback(self, row: OutcomeFeedback) -> OutcomeFeedback:
        async with self._connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """insert into outcomes_feedback (memo_id, user_id, address, geom, concept_type, outcome, notes, reported_at)
                   values (%(memo_id)s, %(user_id)s, %(address)s, %(geom)s::geography, %(concept_type)s, %(outcome)s, %(notes)s, %(reported_at)s)
                   returning id""",
                {**row.model_dump(exclude={"id", "lat", "lng"}), "geom": _pt(row.lat, row.lng)},
            )
            rec = await cur.fetchone()
        return row.model_copy(update={"id": str(rec["id"]) if rec else None})

    # ---- reads -------------------------------------------------------------------------------
    @staticmethod
    def _app(row: dict[str, Any]) -> Application:
        data = {k: v for k, v in row.items() if k not in {"geom", "lat", "lng", "updated_at", "distance_m"}}
        data["lat"], data["lng"] = row.get("lat"), row.get("lng")
        return Application.model_validate(data)

    async def nearby_applications(
        self,
        lat: float,
        lng: float,
        radius_m: float,
        *,
        kinds: list[ApplicationKind] | None = None,
        since: dt.date | None = None,
        limit: int = 500,
    ) -> list[Nearby[Application]]:
        sql = """
        select a.*, ST_Y(a.geom::geometry) as lat, ST_X(a.geom::geometry) as lng,
               ST_Distance(a.geom, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography) as distance_m
        from applications a
        where a.geom is not null
          and ST_DWithin(a.geom, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography, %(radius)s)
          and (%(kinds)s::text[] is null or a.kind = any(%(kinds)s::text[]))
          and (%(since)s::date is null or coalesce(a.filed_at, a.decided_at) >= %(since)s::date)
        order by distance_m, a.id
        limit %(limit)s
        """
        async with self._connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                sql,
                {"lat": lat, "lng": lng, "radius": radius_m, "kinds": kinds, "since": since, "limit": limit},
            )
            rows = await cur.fetchall()
        return [Nearby(self._app(r), float(r["distance_m"])) for r in rows]

    async def nearby_businesses(
        self, lat: float, lng: float, radius_m: float, *, active_only: bool = True, limit: int = 1000
    ) -> list[Nearby[Business]]:
        sql = """
        select b.*, ST_Y(b.geom::geometry) as lat, ST_X(b.geom::geometry) as lng,
               ST_Distance(b.geom, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography) as distance_m
        from businesses b
        where b.geom is not null
          and ST_DWithin(b.geom, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography, %(radius)s)
          and (not %(active_only)s or b.end_date is null)
        order by distance_m, b.id
        limit %(limit)s
        """
        async with self._connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                sql, {"lat": lat, "lng": lng, "radius": radius_m, "active_only": active_only, "limit": limit}
            )
            rows = await cur.fetchall()
        out = []
        for r in rows:
            data = {k: v for k, v in r.items() if k not in {"geom", "distance_m"}}
            out.append(Nearby(Business.model_validate(data), float(r["distance_m"])))
        return out

    @staticmethod
    def _overlay(row: dict[str, Any]) -> Overlay:
        data = {k: v for k, v in row.items() if k != "geom"}
        data["geom"] = json.loads(row["geom"]) if row.get("geom") else None
        return Overlay.model_validate(data)

    async def overlays_at(self, lat: float, lng: float) -> list[Overlay]:
        sql = """
        with pt as (select ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326) as g),
        covering as (
          select o.* from overlays o, pt where o.geom is not null and ST_Covers(o.geom, pt.g)
        ), snapped as (
          -- parcel-based zoning polygons miss street-centreline points by a metre or two: snap to the nearest within 30 m
          select o.* from overlays o, pt
          where o.kind = 'zoning_district' and o.geom is not null
            and not exists (select 1 from covering c where c.kind = 'zoning_district')
            and ST_DWithin(o.geom::geography, pt.g::geography, 30)
          order by ST_Distance(o.geom::geography, pt.g::geography) limit 1
        ), hits as (
          select * from covering union all select * from snapped
        ), codes as (
          select name as code from hits where kind = 'zoning_district'
          union select split_part(id, ':', array_length(string_to_array(id, ':'), 1)) from hits where kind = 'zoning_district'
        )
        select h.id, h.kind, h.name, h.rules, h.code_section, ST_AsGeoJSON(h.geom) as geom, h.district_codes,
               h.bar_permission, h.restaurant_permission, h.late_night_rule, h.source, h.source_url, h.fetched_at
        from hits h
        union all
        select o.id, o.kind, o.name, o.rules, o.code_section, null as geom, o.district_codes, o.bar_permission,
               o.restaurant_permission, o.late_night_rule, o.source, o.source_url, o.fetched_at
        from overlays o where o.geom is null and o.district_codes && (select coalesce(array_agg(code), '{}') from codes)
        order by 2, 1
        """
        async with self._connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, {"lat": lat, "lng": lng})
            rows = await cur.fetchall()
        return [self._overlay(r) for r in rows]

    async def zoning_at(self, lat: float, lng: float) -> ZoningInfo | None:
        overlays = await self.overlays_at(lat, lng)
        zoning = next((o for o in overlays if o.kind == "zoning_district"), None)
        if zoning is None:
            return None
        rule = next((o for o in overlays if o.kind == "nc_rule"), None)
        src = rule or zoning
        return ZoningInfo(
            district=zoning.name,
            name=rule.name if rule else zoning.name,
            code_section=src.code_section,
            bar_permission=src.bar_permission,
            restaurant_permission=src.restaurant_permission,
            rules=src.rules,
            source_url=src.source_url,
        )

    async def application(self, app_id: str) -> Application | None:
        async with self._connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "select a.*, ST_Y(a.geom::geometry) as lat, ST_X(a.geom::geometry) as lng from applications a where id = %s",
                (app_id,),
            )
            row = await cur.fetchone()
        return self._app(row) if row else None

    async def applications_of_kind(self, kind: ApplicationKind) -> list[Application]:
        sql = """
        select a.*, ST_Y(a.geom::geometry) as lat, ST_X(a.geom::geometry) as lng
        from applications a where a.kind = %(kind)s order by a.id
        """
        async with self._connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, {"kind": kind})
            rows = await cur.fetchall()
        return [self._app(r) for r in rows]

    async def all_businesses(self) -> list[Business]:
        sql = """
        select b.*, ST_Y(b.geom::geometry) as lat, ST_X(b.geom::geometry) as lng
        from businesses b order by b.id
        """
        async with self._connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql)
            rows = await cur.fetchall()
        return [Business.model_validate({k: v for k, v in r.items() if k != "geom"}) for r in rows]

    async def feedback_near(self, lat: float, lng: float, radius_m: float) -> list[Nearby[OutcomeFeedback]]:
        sql = """
        select f.id::text, f.memo_id::text, f.user_id::text, f.address, f.concept_type, f.outcome, f.notes, f.reported_at,
               ST_Y(f.geom::geometry) as lat, ST_X(f.geom::geometry) as lng,
               ST_Distance(f.geom, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography) as distance_m
        from outcomes_feedback f
        where f.geom is not null and ST_DWithin(f.geom, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography, %(radius)s)
        order by distance_m
        """
        async with self._connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, {"lat": lat, "lng": lng, "radius": radius_m})
            rows = await cur.fetchall()
        return [
            Nearby(
                OutcomeFeedback.model_validate({k: v for k, v in r.items() if k != "distance_m"}),
                float(r["distance_m"]),
            )
            for r in rows
        ]

    async def feedback_stats(self) -> dict[str, Any]:
        async with self._connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "select outcome, concept_type, count(*) as n from outcomes_feedback group by 1, 2"
            )
            rows = await cur.fetchall()
        by_outcome: Counter[str] = Counter()
        by_concept: Counter[str] = Counter()
        for r in rows:
            by_outcome[r["outcome"]] += int(r["n"])
            by_concept[r["concept_type"]] += int(r["n"])
        return {
            "total": sum(by_outcome.values()),
            "by_outcome": dict(by_outcome),
            "by_concept": dict(by_concept),
        }

    async def last_successful_run(self, source: str) -> IngestionRun | None:
        async with self._connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """select source, started_at, finished_at, status, rows_fetched, rows_upserted, error, notes
                   from ingestion_runs where source = %(source)s and status = 'ok'
                   order by started_at desc limit 1""",
                {"source": source},
            )
            row = await cur.fetchone()
            return IngestionRun.model_validate(row) if row else None

    async def status(self) -> dict[str, Any]:
        async with self._connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("select source, count(*) as n from applications group by 1")
            by_source = {r["source"]: int(r["n"]) for r in await cur.fetchall()}
            counts = {}
            for table in ("applications", "overlays", "businesses", "outcomes_feedback"):
                await cur.execute(f"select count(*) as n from {table}")
                counts[table] = int((await cur.fetchone() or {"n": 0})["n"])
            await cur.execute(
                """select distinct on (source) source, started_at, finished_at, status, rows_fetched, rows_upserted, error, notes
                   from ingestion_runs order by source, started_at desc"""
            )
            last = {
                r["source"]: {
                    **r,
                    "started_at": r["started_at"].isoformat(),
                    "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
                }
                for r in await cur.fetchall()
            }
        return {
            "backend": "postgis",
            "counts": {**counts, "feedback": counts.pop("outcomes_feedback")},
            "by_source": by_source,
            "last_runs": last,
        }
