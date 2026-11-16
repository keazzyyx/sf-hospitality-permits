from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Protocol

from precedent.models import (
    Application,
    ApplicationKind,
    Business,
    IngestionRun,
    OutcomeFeedback,
    Overlay,
    Source,
)


@dataclass(frozen=True)
class ZoningInfo:
    district: str
    name: str
    code_section: str
    bar_permission: str
    restaurant_permission: str
    rules: str
    source_url: str


@dataclass(frozen=True)
class Nearby[T]:
    item: T
    distance_m: float


class Store(Protocol):
    """Everything the ingestion scripts write and the memo tools read."""

    # ---- writes -------------------------------------------------------------------------
    async def upsert_applications(self, rows: list[Application]) -> int: ...
    async def upsert_overlays(self, rows: list[Overlay]) -> int: ...
    async def upsert_businesses(self, rows: list[Business]) -> int: ...
    async def record_run(self, run: IngestionRun) -> None: ...
    async def insert_feedback(self, row: OutcomeFeedback) -> OutcomeFeedback: ...

    # ---- reads ----------------------------------------------------------------------------
    async def nearby_applications(
        self,
        lat: float,
        lng: float,
        radius_m: float,
        *,
        kinds: list[ApplicationKind] | None = None,
        since: dt.date | None = None,
        limit: int = 500,
    ) -> list[Nearby[Application]]: ...
    async def nearby_businesses(
        self, lat: float, lng: float, radius_m: float, *, active_only: bool = True, limit: int = 1000
    ) -> list[Nearby[Business]]: ...
    async def overlays_at(self, lat: float, lng: float) -> list[Overlay]: ...
    async def zoning_at(self, lat: float, lng: float) -> ZoningInfo | None: ...
    async def application(self, app_id: str) -> Application | None: ...
    async def applications_of_kind(self, kind: ApplicationKind) -> list[Application]: ...
    async def all_businesses(self) -> list[Business]: ...
    async def feedback_near(
        self, lat: float, lng: float, radius_m: float
    ) -> list[Nearby[OutcomeFeedback]]: ...
    async def feedback_stats(self) -> dict[str, Any]: ...
    async def status(self) -> dict[str, Any]: ...
    async def last_successful_run(self, source: str) -> IngestionRun | None: ...
    async def close(self) -> None: ...


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math

    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def run_row(source: Source, **kw: Any) -> IngestionRun:
    return IngestionRun(source=source, started_at=dt.datetime.now(dt.UTC), **kw)


ENRICHMENT_SOURCES = {"sf_planning_hearings"}
UNDECIDED = {"unknown", "pending"}


def merge_applications(existing: Application, incoming: Application) -> Application:
    """Combine a stored application with a fresh row for the same id.

    Two directions, same id (e.g. ``datasf_planning:2025-010163CUA``):
      * an ENRICHMENT row (Planning Commission motion / minutes) arriving on a dataset row keeps the
        dataset's identity, geometry, status and dates, and contributes decision text, conditions,
        opposition, confidence, hours, a decided outcome when the dataset still says pending, and extra;
      * a DATASET refresh arriving on an enriched row refreshes identity/geometry/status/dates but never
        erases the enrichment, and keeps a decided outcome over a stale 'pending'.
    The PostGIS store implements the identical rules in SQL (see postgres.py).
    """
    inc_enrich = incoming.source in ENRICHMENT_SOURCES
    ex_enriched = existing.source in ENRICHMENT_SOURCES or "motion_url" in existing.extra
    base, other = (existing, incoming) if inc_enrich else (incoming, existing)
    hearing_hours = existing.extra.get("hours_source") == "hearing" or (
        existing.source in ENRICHMENT_SOURCES and existing.hours_close is not None
    )

    def first(*vals: Any) -> Any:
        return next((v for v in vals if v not in (None, "", [])), None)

    outcome = base.outcome
    if inc_enrich and existing.outcome in UNDECIDED and incoming.outcome not in UNDECIDED:
        outcome = incoming.outcome
    if not inc_enrich and incoming.outcome in UNDECIDED and ex_enriched and existing.outcome not in UNDECIDED:
        outcome = existing.outcome
    decided_at = (
        incoming.decided_at
        if inc_enrich and incoming.decided_at
        else first(base.decided_at, other.decided_at)
    )
    data = base.model_dump()
    data.update(
        {
            "fetched_at": max(existing.fetched_at, incoming.fetched_at),
            "address": first(base.address, other.address),
            "lat": first(base.lat, other.lat),
            "lng": first(base.lng, other.lng),
            "parcel": first(base.parcel, other.parcel),
            "zoning_district": first(base.zoning_district, other.zoning_district),
            "description": first(base.description, other.description) or "",
            "use_types": base.use_types or other.use_types,
            "outcome": outcome,
            "filed_at": first(base.filed_at, other.filed_at),
            "decided_at": decided_at,
            # hearing text beats dataset heuristics for hours
            "hours_close": first(incoming.hours_close, existing.hours_close)
            if inc_enrich
            else first(
                existing.hours_close if hearing_hours else None, incoming.hours_close, existing.hours_close
            ),
            "late_night": first(incoming.late_night, existing.late_night)
            if inc_enrich
            else first(
                existing.late_night if hearing_hours else None, incoming.late_night, existing.late_night
            ),
            "conditions": incoming.conditions or existing.conditions,
            "opposition_noted": first(incoming.opposition_noted, existing.opposition_noted),
            "decision_summary": first(incoming.decision_summary, existing.decision_summary),
            "extraction_confidence": first(incoming.extraction_confidence, existing.extraction_confidence),
            "license_type": first(incoming.license_type, existing.license_type),
            "extra": {**existing.extra, **incoming.extra},
        }
    )
    motion_url = (
        incoming.source_url
        if inc_enrich
        else (existing.source_url if existing.source in ENRICHMENT_SOURCES else None)
    )
    if motion_url:
        data["extra"] = {**data["extra"], "motion_url": motion_url}
    if (inc_enrich and incoming.hours_close) or (
        existing.source in ENRICHMENT_SOURCES and existing.hours_close
    ):
        data["extra"] = {**data["extra"], "hours_source": "hearing"}
    return Application.model_validate(data)
