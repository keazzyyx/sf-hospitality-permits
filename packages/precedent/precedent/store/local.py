"""File-backed store: JSONL snapshots per table under <data_dir>/snapshots. Spatial ops in Python.

Used for tests, `make dev` without a database, and as the fallback the API boots with when
PRECEDENT_DATABASE_URL is not set. Same semantics as the PostGIS store (distances in metres,
point-in-polygon for overlays).
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel
from shapely.geometry import Point, shape

from precedent.models import (
    Application,
    ApplicationKind,
    Business,
    IngestionRun,
    OutcomeFeedback,
    Overlay,
)
from precedent.store.base import Nearby, ZoningInfo, haversine_m, merge_applications

TABLES: dict[str, type[BaseModel]] = {
    "applications": Application,
    "overlays": Overlay,
    "businesses": Business,
    "feedback": OutcomeFeedback,
    "runs": IngestionRun,
}


class LocalStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.snap = self.data_dir / "snapshots"
        self.snap.mkdir(parents=True, exist_ok=True)
        self.applications: dict[str, Application] = {}
        self.overlays: dict[str, Overlay] = {}
        self.businesses: dict[str, Business] = {}
        self.feedback: list[OutcomeFeedback] = []
        self.runs: list[IngestionRun] = []
        self._shapes: dict[str, Any] = {}
        self._load()

    # ---- persistence ---------------------------------------------------------------------
    def _file(self, table: str) -> Path:
        return self.snap / f"{table}.jsonl"

    def _load(self) -> None:
        for table, model in TABLES.items():
            path = self._file(table)
            if not path.exists():
                continue
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                obj = model.model_validate_json(line)
                self._put(table, obj)

    def _put(self, table: str, obj: BaseModel) -> None:
        if table == "applications":
            assert isinstance(obj, Application)
            self.applications[obj.id] = obj
        elif table == "overlays":
            assert isinstance(obj, Overlay)
            self.overlays[obj.id] = obj
            self._shapes.pop(obj.id, None)
        elif table == "businesses":
            assert isinstance(obj, Business)
            self.businesses[obj.id] = obj
        elif table == "feedback":
            assert isinstance(obj, OutcomeFeedback)
            self.feedback.append(obj)
        elif table == "runs":
            assert isinstance(obj, IngestionRun)
            self.runs.append(obj)

    def _flush(self, table: str) -> None:
        rows: list[BaseModel]
        if table == "applications":
            rows = list(self.applications.values())
        elif table == "overlays":
            rows = list(self.overlays.values())
        elif table == "businesses":
            rows = list(self.businesses.values())
        elif table == "feedback":
            rows = list(self.feedback)
        else:
            rows = list(self.runs)
        self._file(table).write_text("".join(r.model_dump_json() + "\n" for r in rows))

    # ---- writes ----------------------------------------------------------------------------
    async def upsert_applications(self, rows: list[Application]) -> int:
        for r in rows:
            existing = self.applications.get(r.id)
            self.applications[r.id] = merge_applications(existing, r) if existing is not None else r
        self._flush("applications")
        return len(rows)

    async def upsert_overlays(self, rows: list[Overlay]) -> int:
        for r in rows:
            self.overlays[r.id] = r
            self._shapes.pop(r.id, None)
        self._flush("overlays")
        return len(rows)

    async def upsert_businesses(self, rows: list[Business]) -> int:
        for r in rows:
            self.businesses[r.id] = r
        self._flush("businesses")
        return len(rows)

    async def record_run(self, run: IngestionRun) -> None:
        self.runs.append(run)
        self._flush("runs")

    async def insert_feedback(self, row: OutcomeFeedback) -> OutcomeFeedback:
        saved = row.model_copy(update={"id": row.id or str(uuid4())})
        self.feedback.append(saved)
        self._flush("feedback")
        return saved

    # ---- reads -----------------------------------------------------------------------------
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
        out: list[Nearby[Application]] = []
        for a in self.applications.values():
            if a.lat is None or a.lng is None:
                continue
            if kinds and a.kind not in kinds:
                continue
            if since and (a.filed_at or a.decided_at or dt.date.min) < since:
                continue
            d = haversine_m(lat, lng, a.lat, a.lng)
            if d <= radius_m:
                out.append(Nearby(a, d))
        out.sort(key=lambda n: (n.distance_m, n.item.id))
        return out[:limit]

    async def nearby_businesses(
        self, lat: float, lng: float, radius_m: float, *, active_only: bool = True, limit: int = 1000
    ) -> list[Nearby[Business]]:
        out: list[Nearby[Business]] = []
        for b in self.businesses.values():
            if b.lat is None or b.lng is None:
                continue
            if active_only and b.end_date is not None:
                continue
            d = haversine_m(lat, lng, b.lat, b.lng)
            if d <= radius_m:
                out.append(Nearby(b, d))
        out.sort(key=lambda n: (n.distance_m, n.item.id))
        return out[:limit]

    def _shape(self, o: Overlay) -> Any:
        if o.id not in self._shapes:
            self._shapes[o.id] = shape(o.geom) if o.geom else None
        return self._shapes[o.id]

    async def overlays_at(self, lat: float, lng: float, *, snap_m: float = 30.0) -> list[Overlay]:
        """Overlays containing the point. Zoning polygons follow parcel lines, so a street-centreline
        geocode can fall a metre outside every district: when no zoning polygon covers the point, the
        nearest one within `snap_m` metres is used (same rule as the PostGIS store)."""
        pt = Point(lng, lat)
        hits = [o for o in self.overlays.values() if (g := self._shape(o)) is not None and g.covers(pt)]
        if not any(o.kind == "zoning_district" for o in hits):
            deg = snap_m / 111_000.0
            nearest = min(
                (
                    (g.distance(pt), o)
                    for o in self.overlays.values()
                    if o.kind == "zoning_district" and (g := self._shape(o)) is not None
                ),
                key=lambda t: t[0],
                default=None,
            )
            if nearest is not None and nearest[0] <= deg:
                hits.append(nearest[1])
        # rule-only rows attach through district codes of the zoning district the point is in
        codes = {o.name for o in hits if o.kind == "zoning_district"} | {
            o.id.split(":")[-1] for o in hits if o.kind == "zoning_district"
        }
        hits += [o for o in self.overlays.values() if o.geom is None and codes & set(o.district_codes)]
        return sorted(hits, key=lambda o: (o.kind, o.id))

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
        return self.applications.get(app_id)

    async def applications_of_kind(self, kind: ApplicationKind) -> list[Application]:
        return sorted((a for a in self.applications.values() if a.kind == kind), key=lambda a: a.id)

    async def all_businesses(self) -> list[Business]:
        return sorted(self.businesses.values(), key=lambda b: b.id)

    async def feedback_near(self, lat: float, lng: float, radius_m: float) -> list[Nearby[OutcomeFeedback]]:
        out = [
            Nearby(f, haversine_m(lat, lng, f.lat, f.lng))
            for f in self.feedback
            if f.lat is not None and f.lng is not None
        ]
        return sorted((n for n in out if n.distance_m <= radius_m), key=lambda n: n.distance_m)

    async def feedback_stats(self) -> dict[str, Any]:
        by_outcome = Counter(f.outcome for f in self.feedback)
        by_concept = Counter(f.concept_type for f in self.feedback)
        return {"total": len(self.feedback), "by_outcome": dict(by_outcome), "by_concept": dict(by_concept)}

    async def status(self) -> dict[str, Any]:
        latest: dict[str, IngestionRun] = {}
        for r in self.runs:
            cur = latest.get(r.source)
            if cur is None or r.started_at > cur.started_at:
                latest[r.source] = r
        return {
            "backend": "local",
            "counts": {
                "applications": len(self.applications),
                "overlays": len(self.overlays),
                "businesses": len(self.businesses),
                "feedback": len(self.feedback),
            },
            "by_source": dict(Counter(a.source for a in self.applications.values())),
            "last_runs": {s: json.loads(r.model_dump_json()) for s, r in latest.items()},
        }

    async def last_successful_run(self, source: str) -> IngestionRun | None:
        ok = [r for r in self.runs if r.source == source and r.status == "ok"]
        return max(ok, key=lambda r: r.started_at) if ok else None

    async def close(self) -> None:
        return None
