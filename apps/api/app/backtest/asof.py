"""The records as they stood on a past day: the cut-off for one backtest case (docs/validation/backtest-plan.md §3).

A report in the backtest is made as if on the day before the case was filed (the case's rules date, called
`as_of` here). Filtering rows by filing date is not enough, because most fields are stored as they read today.
`AsOfStore` wraps the store every data function reads and applies the plan's treatment field by field:

Planning records (kinds cua, planning_other)
  - no filing date, or filed after `as_of`: left out;
  - every record of the case's own project (same record number before the suffix, e.g. 2022-003434): left out;
  - decided on or before `as_of`: kept as stored;
  - otherwise "open at the cut-off": status "Open at the cut-off", outcome pending, and the decision date,
    description, conditions, decision summary, closing hour, late-night flag, extraction confidence, use types
    and the labels derived from today's description removed (only fields fixed at filing are kept in `extra`);
  - closed but with no decision date (cannot be placed in time): left out.
  Fields that can carry later facts (`building_permits`, `data_as_of`) are dropped from every kept record.
Entertainment Commission permits: left out (the dataset has no dates).
ABC licences: today's rows are never returned. In their place, the licences as they stood on `as_of`, rebuilt
  from ABC's export and the Step 1b histories (`licences_asof.json`, scripts/validation/build_asof_licences.py):
  issued on or before `as_of` and not ended by then. The status shown is the status on `as_of`
  (status_on_cut_off below); a file whose status that day cannot be told is left out and counted.
Registered businesses: kept only if started on or before `as_of` and not ended by then; a later end date is
  removed (it is a fact from after the cut-off).
User-reported outcomes: none.
Zoning districts and overlays: today's map (the rules read the dated controls; see the plan).

The census-tract licence counts the alcohol row prints are recounted from the same as-of licence set
(`tract_licence_data`), installed for one case at a time through a context variable, so cases can run at once.
"""

from __future__ import annotations

import contextvars
import dataclasses
import datetime as dt
import json
import math
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from precedent.models import Application, Business, OutcomeFeedback, Overlay
from precedent.store.base import Nearby, ZoningInfo

LICENCES_FILE = (
    Path(os.environ.get("LOCAL_DATA_DIR", "~/sfhp-local")).expanduser() / "backtest/licences_asof.json"
)

OPEN_STATUS = "Open at the cut-off"
# extra keys fixed when the record is filed; everything else is removed from a record open at the cut-off
KEEP_EXTRA_OPEN = frozenset(
    {"record_type", "neighborhood", "zoning", "zoning_name", "parent_id", "applicant_org"}
)
# extra keys that can carry facts from after the cut-off on any record
DROP_EXTRA_ALWAYS = frozenset({"building_permits", "data_as_of", "active_licenses"})
PLANNING_KINDS = frozenset({"cua", "planning_other"})
PROJECT_RE = re.compile(r"^(\d{4}-\d{6})")

# ABC status codes (Step 1b): held = the licence exists on that day
ACTIVE = "ACTIVE"
HELD_NOT_ACTIVE = frozenset({"SUSPEN", "REVPEN", "SUREND", "R64B"})
STATUS_WORDS = {
    "ACTIVE": "ACTIVE",
    "SUSPEN": "SUSPENDED",
    "REVPEN": "REV PENDING",
    "SUREND": "SURRENDERED",
    "R64B": "RULE 64B",
}
UNKNOWN = "UNKNOWN"


def project_of(record: str | None) -> str | None:
    """'2022-003434' from '2022-003434CUA' (Planning's record number before its suffix)."""
    m = PROJECT_RE.match((record or "").strip())
    return m.group(1) if m else None


def _day(value: str | None) -> dt.date | None:
    return dt.date.fromisoformat(value) if value else None


# ---- ABC licences on a past day ----------------------------------------------------------------------------


@dataclass(frozen=True)
class LicenceFile:
    file_number: str
    types: tuple[str, ...]
    primary_type: str
    name: str
    address: str
    zip: str
    issued: dt.date
    in_export_today: bool
    status_today: str
    status_dates: tuple[dt.date, ...]
    latest_from: str | None
    latest_to: str | None
    latest_date: dt.date | None
    lat: float | None
    lng: float | None
    parcel: str | None
    tract: str | None

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> LicenceFile:
        lt = d.get("latest_transition") or {}
        return cls(
            file_number=d["file_number"],
            types=tuple(d["types"]),
            primary_type=d["primary_type"],
            name=d.get("name") or "",
            address=d.get("address") or "",
            zip=d.get("zip") or "",
            issued=dt.date.fromisoformat(d["issued"]),
            in_export_today=bool(d["in_export_today"]),
            status_today=(d.get("status_today") or "").upper(),
            status_dates=tuple(dt.date.fromisoformat(x) for x in d.get("status_dates") or ()),
            latest_from=lt.get("from"),
            latest_to=lt.get("to"),
            latest_date=_day(lt.get("date")),
            lat=d.get("lat"),
            lng=d.get("lng"),
            parcel=d.get("parcel"),
            tract=d.get("tract"),
        )


def status_on_cut_off(f: LicenceFile, as_of: dt.date) -> str | None:
    """The file's status code on `as_of`: None when it was not issued yet, UNKNOWN when the archive cannot tell.

    ABC's Status Changes report keeps only a record's latest transition, listed on every date the record changed
    (Step 1b). So the status on a past day is known when nothing changed after it (the status then is today's), or
    when the only change after it is the latest transition (the status then is that transition's starting status).
    With two or more changes after the day, the status in between is not in the archive: UNKNOWN."""
    if f.issued > as_of:
        return None
    later = sorted({d for d in f.status_dates if d > as_of})
    if not later:
        return f.status_today if f.in_export_today or not f.latest_to else f.latest_to
    if len(later) == 1 and f.latest_date == later[0] and f.latest_from:
        return f.latest_from
    return UNKNOWN


@lru_cache(maxsize=1)
def licence_files(path: str = str(LICENCES_FILE)) -> tuple[LicenceFile, ...]:
    data = json.loads(Path(path).read_text())
    return tuple(LicenceFile.from_json(d) for d in data["files"])


def _type_label(code: str) -> str:
    from precedent.sources.abc import type_label

    return str(type_label(code))


def _use_types(types: Iterable[str], name: str) -> list[Any]:
    from precedent.sources.abc import TYPE_USE_TYPES
    from precedent.textparse import classify_use_types

    out: list[Any] = []
    for t in types:
        for u in TYPE_USE_TYPES.get(t, []):
            if u not in out:
                out.append(u)
    for u in classify_use_types(name):
        if u not in out:
            out.append(u)
    return out


def _cut_off_time(as_of: dt.date) -> dt.datetime:
    """The time a record is said to have been read: the end of the cut-off day, never the real fetch time."""
    return dt.datetime.combine(as_of, dt.time(23, 59), tzinfo=dt.UTC)


def licence_application(f: LicenceFile, status: str, as_of: dt.date) -> Application:
    """An ABC licence as the report reads it, with its status on `as_of` and nothing from after it."""
    from precedent.sources.abc import lookup_url

    label = _type_label(f.primary_type)
    word = STATUS_WORDS.get(status, status)
    address = (
        ", ".join(p for p in (f.address, "SAN FRANCISCO", f"CA {f.zip}".strip()) if p) if f.address else None
    )
    return Application(
        id=f"abc:{f.file_number}",
        source="abc",
        source_id=f.file_number,
        source_url=lookup_url(f.file_number),
        fetched_at=_cut_off_time(as_of),
        kind="abc_license",
        permit_type=label,
        use_types=_use_types(f.types, f.name),
        description=f"{f.name or 'ABC licensee'} — {label} ({word} on {as_of.isoformat()})",
        address=address,
        lat=f.lat,
        lng=f.lng,
        parcel=f.parcel,
        status=word,
        outcome="approved",
        filed_at=None,
        decided_at=f.issued,
        extraction_confidence="high",
        license_type=f.primary_type,
        extra={
            "license_types": [{"type": t, "label": _type_label(t)} for t in f.types],
            "census_tract": f.tract,
            "status_basis": f"status on {as_of.isoformat()}, rebuilt from ABC's daily licensing reports",
        },
    )


@dataclass(frozen=True)
class LicenceSet:
    as_of: dt.date
    held: tuple[tuple[LicenceFile, str], ...]  # (file, status code on as_of), issued and not ended
    unknown: tuple[LicenceFile, ...]  # issued by as_of, status that day not in the archive
    not_placed: int  # held files with no map point (cannot be within a distance)


def licence_set(as_of: dt.date, files: Sequence[LicenceFile] | None = None) -> LicenceSet:
    held: list[tuple[LicenceFile, str]] = []
    unknown: list[LicenceFile] = []
    for f in files if files is not None else licence_files():
        s = status_on_cut_off(f, as_of)
        if s is None:
            continue
        if s == UNKNOWN:
            unknown.append(f)
        elif s == ACTIVE or s in HELD_NOT_ACTIVE:
            held.append((f, s))
    return LicenceSet(
        as_of=as_of,
        held=tuple(held),
        unknown=tuple(unknown),
        not_placed=sum(1 for f, _ in held if f.lat is None),
    )


def tract_licence_data(ls: LicenceSet, base: dict[str, Any]) -> dict[str, Any]:
    """The tract figures file (app/memo/data/sf_tract_licences.json) with the active counts replaced by the
    licences held on `as_of`. The authorised numbers stay as published (2026); the label says so."""
    from app.memo.tracts import ACTIVE_STATUS, KINDS, RETAIL_TYPES, normalise_tract

    active: dict[str, dict[str, set[str]]] = {k: {} for k in KINDS}
    other: dict[str, dict[str, set[str]]] = {k: {} for k in KINDS}
    for f, s in ls.held:
        tract = normalise_tract(f.tract)
        if tract is None:
            continue
        for kind in KINDS:
            if any(t in RETAIL_TYPES[kind] for t in f.types):
                (active if s == ACTIVE_STATUS else other)[kind].setdefault(tract, set()).add(f.file_number)
    tracts = {}
    for key, row in base["tracts"].items():
        new = dict(row)
        for kind in KINDS:
            on = active[kind].get(key, set())
            new[f"active_{kind}"] = len(on)
            new[f"issued_not_active_{kind}"] = len(other[kind].get(key, set()) - on)
        tracts[key] = new
    return {
        **base,
        "active": {
            **base["active"],
            "export_date": ls.as_of.isoformat(),
            "described_as": "ABC's licences as they stood on",
            "source": "ABC licences held on the cut-off day, rebuilt from ABC's daily export of 2026-11-09 and its "
            "daily licensing reports from 2019 (Step 1b histories)",
        },
        "tracts": tracts,
        "not_placed": {},
    }


def with_unknown_as_active(ls: LicenceSet) -> LicenceSet:
    """The other assumption, for the sensitivity check only: every licence whose status on the day is not in the
    archive counted as active that day."""
    return LicenceSet(
        as_of=ls.as_of,
        held=(*ls.held, *((f, ACTIVE) for f in ls.unknown)),
        unknown=(),
        not_placed=ls.not_placed + sum(1 for f in ls.unknown if f.lat is None),
    )


def at_address(f: LicenceFile, normalized_address: str | None, parcel: str | None) -> bool:
    """A licence file on the report's own parcel or at its own street address (EAS normalised form)."""
    if parcel and f.parcel and f.parcel.replace(" ", "") == parcel.replace(" ", ""):
        return True
    norm = (f.address or "").upper().split(",")[0].strip()
    want = (normalized_address or "").upper().split(",")[0].strip()
    return bool(want) and norm == want


UNKNOWN_RADIUS_M = 304.8  # 1,000 ft, the radius of the report's licence counts
AT_ADDRESS_M = 15.0


def unknown_at_address(
    ls: LicenceSet, normalized_address: str | None, parcel: str | None
) -> list[LicenceFile]:
    return [f for f in ls.unknown if at_address(f, normalized_address, parcel)]


def unknown_status_line(
    ls: LicenceSet,
    lat: float,
    lng: float,
    tract: str | None,
    *,
    normalized_address: str | None = None,
    parcel: str | None = None,
) -> Any:
    """The alcohol row's line on the licences the archive cannot place in time: how many near the address had an
    unknown status on the cut-off day, and that they are left out. A fixed sentence built from counts."""
    from app.memo.tracts import normalise_tract
    from app.models.memo import RuleLine

    placed = [f for f in ls.unknown if f.lat is not None and f.lng is not None]
    near = [f for f in placed if _haversine_m(lat, lng, f.lat, f.lng) <= UNKNOWN_RADIUS_M]  # type: ignore[arg-type]
    here = unknown_at_address(ls, normalized_address, parcel)
    key = normalise_tract(tract)
    in_tract = [f for f in ls.unknown if key is not None and normalise_tract(f.tract) == key]
    day = ls.as_of.isoformat()
    if not near and not in_tract:
        text = f"Licences with an unknown status on {day}: none within 1,000 ft or in the census tract."
    else:
        n = len(near)
        text = (
            f"Licences with an unknown status on {day}: {n} ABC licence{'' if n == 1 else 's'} within 1,000 ft"
            + (f" ({len(here)} at this address)" if here else "")
            + f" and {len(in_tract)} in the census tract were on file, but ABC's daily reports do not show "
            "their status that day (it changed two or more times since). They are left out of the licence "
            "counts, the census tract count and what the space is read as."
        )
    return RuleLine(rule_id="backtest.licences_status_unknown", text=text, code_section=None)


# one case's tract figures; None = the bundled figures (a live report)
TRACT_DATA: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "asof_tract_data", default=None
)


# ---- the masking store -------------------------------------------------------------------------------------


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def mask_application(
    app: Application, as_of: dt.date, *, excluded_projects: frozenset[str] = frozenset()
) -> Application | None:
    """A non-licence record as it could be known on `as_of`, or None when it must be left out."""
    if app.kind == "abc_license" or app.source == "abc":
        return None  # served from the as-of licence set only
    if app.kind not in PLANNING_KINDS:
        return None  # Entertainment Commission permits: no dates
    if project_of(app.source_id) in excluded_projects:
        return None
    if app.filed_at is None or app.filed_at > as_of:
        return None
    extra = {k: v for k, v in app.extra.items() if k not in DROP_EXTRA_ALWAYS}
    read = _cut_off_time(as_of)
    if app.decided_at is not None and app.decided_at <= as_of:
        return app.model_copy(update={"extra": extra, "fetched_at": read})
    if app.decided_at is None and (app.status or "").strip().lower().startswith("closed"):
        return None  # closed with no decision date: cannot be placed in time
    if app.decided_at is None and app.outcome not in ("pending", "unknown"):
        return None
    return app.model_copy(
        update={
            "status": OPEN_STATUS,
            "outcome": "pending",
            "decided_at": None,
            "description": "",
            "conditions": [],
            "decision_summary": None,
            "hours_close": None,
            "late_night": None,
            "extraction_confidence": None,
            "opposition_noted": None,
            "use_types": [],
            "fetched_at": read,
            "extra": {k: v for k, v in extra.items() if k in KEEP_EXTRA_OPEN},
        }
    )


def mask_business(b: Business, as_of: dt.date) -> Business | None:
    if b.start_date is None or b.start_date > as_of:
        return None
    if b.end_date is not None and b.end_date <= as_of:
        return None
    return b.model_copy(update={"end_date": None}) if b.end_date is not None else b


def dated_text(as_of: dt.date) -> str:
    return (
        f"The controls as they stood on {as_of.isoformat()} are in the rule lines (read from the dated Planning Code "
        "controls); today's summary of this district is not shown in a report made as of a past day."
    )


class WriteRefusedError(RuntimeError):
    pass


class AsOfStore:
    """The `precedent.store.Store` reads as of one day. Every write is refused."""

    def __init__(
        self,
        inner: Any,
        as_of: dt.date,
        *,
        excluded_records: Iterable[str] = (),
        licences: LicenceSet | None = None,
    ) -> None:
        self.inner = inner
        self.as_of = as_of
        self.excluded_projects = frozenset(p for p in (project_of(r) for r in excluded_records) if p)
        self.licences = licences if licences is not None else licence_set(as_of)
        self._licence_apps = [
            (licence_application(f, s, as_of), f)
            for f, s in self.licences.held
            if f.lat is not None and f.lng is not None
        ]
        self._licence_by_id = {a.id: a for a, _ in self._licence_apps}

    # ---- writes ----------------------------------------------------------------------------------------
    async def upsert_applications(self, rows: list[Application]) -> int:
        raise WriteRefusedError("the backtest store is read-only")

    async def upsert_overlays(self, rows: list[Overlay]) -> int:
        raise WriteRefusedError("the backtest store is read-only")

    async def upsert_businesses(self, rows: list[Business]) -> int:
        raise WriteRefusedError("the backtest store is read-only")

    async def record_run(self, run: Any) -> None:
        raise WriteRefusedError("the backtest store is read-only")

    async def insert_feedback(self, row: OutcomeFeedback) -> OutcomeFeedback:
        raise WriteRefusedError("the backtest store is read-only")

    # ---- reads -----------------------------------------------------------------------------------------
    def _mask(self, app: Application) -> Application | None:
        return mask_application(app, self.as_of, excluded_projects=self.excluded_projects)

    async def nearby_applications(
        self,
        lat: float,
        lng: float,
        radius_m: float,
        *,
        kinds: list[Any] | None = None,
        since: dt.date | None = None,
        limit: int = 500,
    ) -> list[Nearby[Application]]:
        want_licences = kinds is None or "abc_license" in kinds
        other = None if kinds is None else [k for k in kinds if k != "abc_license"]
        out: list[Nearby[Application]] = []
        if other is None or other:
            rows = await self.inner.nearby_applications(
                lat, lng, radius_m, kinds=other, since=since, limit=max(limit * 5, 5000)
            )
            for n in rows:
                masked = self._mask(n.item)
                if masked is not None:
                    out.append(Nearby(masked, n.distance_m))
        if want_licences:
            for app, f in self._licence_apps:
                assert f.lat is not None and f.lng is not None
                d = _haversine_m(lat, lng, f.lat, f.lng)
                if d > radius_m:
                    continue
                if since is not None and (app.decided_at is None or app.decided_at < since):
                    continue
                out.append(Nearby(app, d))
        out.sort(key=lambda n: (n.distance_m, n.item.id))
        return out[:limit]

    async def nearby_businesses(
        self, lat: float, lng: float, radius_m: float, *, active_only: bool = True, limit: int = 1000
    ) -> list[Nearby[Business]]:
        rows = await self.inner.nearby_businesses(
            lat, lng, radius_m, active_only=False, limit=max(limit * 5, 5000)
        )
        out = []
        for n in rows:
            b = mask_business(n.item, self.as_of)
            if b is not None:
                out.append(Nearby(b, n.distance_m))
        return out[:limit]

    async def overlays_at(self, lat: float, lng: float) -> list[Overlay]:
        """Today's map (the match), without today's summary of the controls: a district or special use district
        is named and drawn as today, and what it allows is what the dated rule lines say for the cut-off day."""
        return [
            o.model_copy(
                update={
                    "rules": dated_text(self.as_of),
                    "bar_permission": "unknown",
                    "restaurant_permission": "unknown",
                    "late_night_rule": None,
                    "fetched_at": _cut_off_time(self.as_of),
                }
            )
            for o in await self.inner.overlays_at(lat, lng)
        ]

    async def zoning_at(self, lat: float, lng: float) -> ZoningInfo | None:
        z = await self.inner.zoning_at(lat, lng)
        if z is None:
            return None
        return dataclasses.replace(
            z, rules=dated_text(self.as_of), bar_permission="unknown", restaurant_permission="unknown"
        )

    async def application(self, app_id: str) -> Application | None:
        if app_id.startswith("abc:"):
            return self._licence_by_id.get(app_id)
        app = await self.inner.application(app_id)
        return self._mask(app) if app is not None else None

    async def applications_of_kind(self, kind: Any) -> list[Application]:
        if kind == "abc_license":
            return [a for a, _ in self._licence_apps]
        return [
            m for m in (self._mask(a) for a in await self.inner.applications_of_kind(kind)) if m is not None
        ]

    async def all_businesses(self) -> list[Business]:
        return [
            m
            for m in (mask_business(b, self.as_of) for b in await self.inner.all_businesses())
            if m is not None
        ]

    async def feedback_near(self, lat: float, lng: float, radius_m: float) -> list[Nearby[OutcomeFeedback]]:
        return []

    async def feedback_stats(self) -> dict[str, Any]:
        return {}

    async def status(self) -> dict[str, Any]:
        return {"as_of": self.as_of.isoformat()}

    async def last_successful_run(self, source: str) -> Any:
        return None

    async def close(self) -> None:
        return None
