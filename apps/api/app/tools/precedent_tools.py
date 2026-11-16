"""Function tools over the precedent store. Each is a Neatlogs TOOL span with `rows` in its attributes."""

from __future__ import annotations

import contextvars
import datetime as dt
import logging
import re
from typing import Any, Literal

import neatlogs
from precedent.models import Application
from precedent.store import Store
from precedent.store.base import Nearby
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.observability import set_span_attributes
from app.memo.analytics import (
    BASE_RATE_KINDS,
    BASE_RATE_LIMIT,
    FT_1000_M,
    GRANT_ONLY_KINDS,
    ON_SALE_TYPES,
    BaseRate,
    record_kind,
)
from app.memo.analytics import base_rate as compute_base_rate
from app.memo.context import get_geocoder, get_store
from app.memo.report import case_outcome
from app.models.profile import BusinessProfile
from app.tools.base import ToolExecutionError, ToolSpec

log = logging.getLogger(__name__)
# The day the report is made as of, for the base-rate tool's window: None (a live report) is today. Only the
# backtest sets it, to the case's cut-off day.
REPORT_DAY: contextvars.ContextVar[dt.date | None] = contextvars.ContextVar("report_day", default=None)

Kind = Literal[
    "cua",
    "planning_other",
    "entertainment_poe",
    "entertainment_llp",
    "entertainment_sound",
    "entertainment_other",
    "abc_license",
]


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


# ---- geocode ---------------------------------------------------------------------------------
class GeocodeInput(BaseModel):
    address: str = Field(min_length=4, description="Street address in San Francisco, e.g. '995 Valencia St'.")


class GeocodeOutput(BaseModel):
    found: bool
    address: str | None
    normalized_address: str | None
    lat: float | None
    lng: float | None
    parcel: str | None
    zip_code: str | None
    source: str | None
    source_url: str | None
    confidence: float | None


@neatlogs.span(kind="TOOL", name="tool.geocode_address")
async def _geocode(inp: BaseModel) -> BaseModel:
    assert isinstance(inp, GeocodeInput)
    res = await get_geocoder().geocode(inp.address)
    set_span_attributes(rows=1 if res else 0, geocode_source=res.source if res else None)
    if res is None:
        return GeocodeOutput(
            found=False,
            address=None,
            normalized_address=None,
            lat=None,
            lng=None,
            parcel=None,
            zip_code=None,
            source=None,
            source_url=None,
            confidence=None,
        )
    return GeocodeOutput(
        found=True,
        address=res.address,
        normalized_address=res.normalized_address,
        lat=res.lat,
        lng=res.lng,
        parcel=res.parcel,
        zip_code=res.zip_code,
        source=res.source,
        source_url=res.source_url,
        confidence=res.confidence,
    )


GEOCODE_ADDRESS = ToolSpec(
    name="geocode_address",
    description="Resolve a San Francisco street address to coordinates, parcel (block/lot) and ZIP using the city's Enterprise Addressing System.",
    input_model=GeocodeInput,
    handler=_geocode,
)


# ---- nearby applications / licenses -----------------------------------------------------------------
class NearbyInput(LatLng):
    radius_m: float = Field(
        default=FT_1000_M,
        gt=0,
        le=1609,
        description="Search radius in metres (500 ft = 152.4, 1,000 ft = 304.8).",
    )
    kinds: list[Kind] | None = Field(
        default=None, description="Restrict to these record kinds; default all non-license records."
    )
    since: str | None = Field(default=None, description="YYYY-MM-DD; only records filed/decided on or after.")
    limit: int = Field(default=60, ge=1, le=200)


class ApplicationOut(BaseModel):
    id: str
    citation_id: str
    kind: str
    record_kind: str = Field(
        description="What the record is: use_decision, agency_referral, building_work, other, licence, "
        "entertainment_permit, or not_labelled when the record has not been classified."
    )
    permit_type: str
    use_types: list[str]
    description: str
    address: str | None
    distance_m: float
    status: str
    outcome: str
    filed_at: str | None
    decided_at: str | None
    hours_close: str | None
    late_night: bool | None
    conditions: list[str]
    opposition_noted: bool | None
    decision_summary: str | None
    extraction_confidence: str | None
    license_type: str | None
    zoning_district: str | None
    source_url: str


class NearbyOutput(BaseModel):
    radius_m: float
    count: int
    rows: list[ApplicationOut]


_OPPOSITION_SENTENCE_RE = re.compile(
    r"\s*(?:Opposition was recorded in public comment\.|\d+ speaker\(s\) spoke in opposition at the hearing\.)"
)


def scrub_summary(text: str | None) -> str | None:
    """Drop the generated opposition sentences from a stored decision summary while the flag is withheld.
    Summaries written before 2026-11-10 carry them; re-ingested ones do not."""
    if text is None or get_settings().REPORT_OPPOSITION_FLAG:
        return text
    return _OPPOSITION_SENTENCE_RE.sub("", text).strip()


def _cid(app_id: str) -> str:
    return f"app:{app_id}"


def _app_out(a: Any, d: float, *, brief: bool = False) -> ApplicationOut:
    return ApplicationOut(
        id=a.id,
        citation_id=_cid(a.id),
        kind=a.kind,
        record_kind=record_kind(a),
        permit_type=a.permit_type,
        use_types=list(a.use_types),
        description=(a.description[:400] if brief else a.description),
        address=a.address,
        distance_m=round(d, 1),
        status=a.status,
        outcome=case_outcome(a),  # a cancelled case is "cancelled", as in the candidates block
        filed_at=a.filed_at.isoformat() if a.filed_at else None,
        decided_at=a.decided_at.isoformat() if a.decided_at else None,
        hours_close=a.hours_close,
        late_night=a.late_night,
        conditions=list(a.conditions)[:8] if brief else list(a.conditions),
        opposition_noted=a.opposition_noted if get_settings().REPORT_OPPOSITION_FLAG else None,
        decision_summary=scrub_summary(a.decision_summary),
        extraction_confidence=a.extraction_confidence,
        license_type=a.license_type,
        zoning_district=a.zoning_district,
        source_url=a.source_url,
    )


def _since(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ToolExecutionError("invalid_date", "since must be YYYY-MM-DD") from exc


@neatlogs.span(kind="TOOL", name="tool.nearby_applications")
async def _nearby_apps(inp: BaseModel) -> BaseModel:
    assert isinstance(inp, NearbyInput)
    kinds = inp.kinds or [
        "cua",
        "planning_other",
        "entertainment_poe",
        "entertainment_llp",
        "entertainment_sound",
        "entertainment_other",
    ]
    rows = await get_store().nearby_applications(
        inp.lat, inp.lng, inp.radius_m, kinds=kinds, since=_since(inp.since), limit=inp.limit
    )
    set_span_attributes(rows=len(rows), radius_m=inp.radius_m)
    return NearbyOutput(
        radius_m=inp.radius_m,
        count=len(rows),
        rows=[_app_out(n.item, n.distance_m, brief=True) for n in rows],
    )


NEARBY_APPLICATIONS = ToolSpec(
    name="nearby_applications",
    description="Planning (CUA, change of use) and Entertainment Commission applications within a radius of a point, nearest first, with outcome and conditions where known.",
    input_model=NearbyInput,
    handler=_nearby_apps,
)


class NearbyLicensesInput(LatLng):
    radius_m: float = Field(default=FT_1000_M, gt=0, le=1609)
    license_types: list[str] | None = Field(
        default=None, description="ABC type codes to include, e.g. ['41','42','47','48']. Default: all."
    )
    active_only: bool = True
    limit: int = Field(default=100, ge=1, le=300)


@neatlogs.span(kind="TOOL", name="tool.nearby_licenses")
async def _nearby_licenses(inp: BaseModel) -> BaseModel:
    assert isinstance(inp, NearbyLicensesInput)
    rows = await get_store().nearby_applications(
        inp.lat, inp.lng, inp.radius_m, kinds=["abc_license"], limit=inp.limit * 2
    )
    out = []
    for n in rows:
        if inp.license_types and (n.item.license_type or "") not in set(inp.license_types):
            continue
        if inp.active_only and not n.item.status.lower().startswith("act"):
            continue
        out.append(_app_out(n.item, n.distance_m, brief=True))
    out = out[: inp.limit]
    set_span_attributes(rows=len(out), radius_m=inp.radius_m)
    return NearbyOutput(radius_m=inp.radius_m, count=len(out), rows=out)


NEARBY_LICENSES = ToolSpec(
    name="nearby_licenses",
    description="California ABC licenses (Types 41/42/47/48 etc.) within a radius of a point: type, status, issue date and conditions where known.",
    input_model=NearbyLicensesInput,
    handler=_nearby_licenses,
)


class NearbyBusinessesInput(LatLng):
    radius_m: float = Field(default=152.4, gt=0, le=1609)
    limit: int = Field(default=100, ge=1, le=500)


class BusinessOut(BaseModel):
    id: str
    dba_name: str
    naics_description: str | None
    address: str | None
    distance_m: float
    is_bar: bool
    start_date: str | None


class NearbyBusinessesOutput(BaseModel):
    radius_m: float
    count: int
    food_or_drink: int
    bars: int
    rows: list[BusinessOut]


@neatlogs.span(kind="TOOL", name="tool.nearby_businesses")
async def _nearby_businesses(inp: BaseModel) -> BaseModel:
    assert isinstance(inp, NearbyBusinessesInput)
    rows = await get_store().nearby_businesses(inp.lat, inp.lng, inp.radius_m, limit=inp.limit)
    set_span_attributes(rows=len(rows), radius_m=inp.radius_m)
    return NearbyBusinessesOutput(
        radius_m=inp.radius_m,
        count=len(rows),
        food_or_drink=sum(1 for n in rows if n.item.is_food_or_drink),
        bars=sum(1 for n in rows if n.item.is_bar),
        rows=[
            BusinessOut(
                id=n.item.id,
                dba_name=n.item.dba_name,
                naics_description=n.item.naics_description,
                address=n.item.address,
                distance_m=round(n.distance_m, 1),
                is_bar=n.item.is_bar,
                start_date=n.item.start_date.isoformat() if n.item.start_date else None,
            )
            for n in rows
        ],
    )


NEARBY_BUSINESSES = ToolSpec(
    name="nearby_businesses",
    description="Registered food & drink businesses within a radius (density / undue-concentration signal).",
    input_model=NearbyBusinessesInput,
    handler=_nearby_businesses,
)


# ---- overlays / zoning ----------------------------------------------------------------------------
class OverlayOut(BaseModel):
    id: str
    citation_id: str
    kind: str
    name: str
    rules: str
    code_section: str
    bar_permission: str
    restaurant_permission: str
    late_night_rule: str | None
    source_url: str


class OverlaysOutput(BaseModel):
    count: int
    rows: list[OverlayOut]


@neatlogs.span(kind="TOOL", name="tool.overlays_at")
async def _overlays_at(inp: BaseModel) -> BaseModel:
    assert isinstance(inp, LatLng)
    rows = await get_store().overlays_at(inp.lat, inp.lng)
    set_span_attributes(rows=len(rows))
    return OverlaysOutput(
        count=len(rows),
        rows=[
            OverlayOut(
                id=o.id,
                citation_id=f"overlay:{o.id}",
                kind=o.kind,
                name=o.name,
                rules=o.rules,
                code_section=o.code_section,
                bar_permission=o.bar_permission,
                restaurant_permission=o.restaurant_permission,
                late_night_rule=o.late_night_rule,
                source_url=o.source_url,
            )
            for o in rows
        ],
    )


OVERLAYS_AT = ToolSpec(
    name="overlays_at",
    description="Zoning district polygon, Special Use Districts (e.g. alcohol restricted districts) and Planning Code rule rows that apply at a point, each with its code section.",
    input_model=LatLng,
    handler=_overlays_at,
)


class ZoningOutput(BaseModel):
    found: bool
    citation_id: str | None
    district: str | None
    name: str | None
    code_section: str | None
    bar_permission: str | None
    restaurant_permission: str | None
    rules: str | None
    source_url: str | None


@neatlogs.span(kind="TOOL", name="tool.zoning_at")
async def _zoning_at(inp: BaseModel) -> BaseModel:
    assert isinstance(inp, LatLng)
    z = await get_store().zoning_at(inp.lat, inp.lng)
    set_span_attributes(rows=1 if z else 0)
    if z is None:
        return ZoningOutput(
            found=False,
            citation_id=None,
            district=None,
            name=None,
            code_section=None,
            bar_permission=None,
            restaurant_permission=None,
            rules=None,
            source_url=None,
        )
    return ZoningOutput(
        found=True,
        citation_id=f"zoning:{z.district}",
        district=z.district,
        name=z.name,
        code_section=z.code_section,
        bar_permission=z.bar_permission,
        restaurant_permission=z.restaurant_permission,
        rules=z.rules,
        source_url=z.source_url,
    )


ZONING_AT = ToolSpec(
    name="zoning_at",
    description="The zoning district at a point and whether a bar / restaurant is principally permitted, conditional or prohibited there.",
    input_model=LatLng,
    handler=_zoning_at,
)


# ---- base rate -----------------------------------------------------------------------------------------
class BaseRateInput(LatLng):
    profile: BusinessProfile
    zoning_district: str | None = None
    window_years: int = Field(default=5, ge=1, le=15)


class BaseRateOutput(BaseModel):
    approved: int
    approved_with_conditions: int
    denied: int
    withdrawn: int
    total: int = Field(description="N: dated Planning decisions with a known outcome.")
    window_years: int
    scope: str = Field(description="Always prints N; says so when N is too small for a rate.")
    rate_shown: bool = Field(description="True only when N >= 10. When false, do not state a rate.")
    approval_rate_pct: float | None = Field(description="Approvals as a share of N; null unless rate_shown.")
    excluded_grant_only: int = Field(
        description="Nearby Entertainment Commission permits and ABC licences left out: those lists show grants only."
    )
    excluded_undated: int = Field(
        description="Comparable decided Planning rows left out for lacking a filing or decision date, or with a "
        "decision date before the filing date."
    )
    excluded_not_use_decision: int = Field(
        description="Labelled Planning rows left out because they are not a use decision about a food, drink or "
        "entertainment premises: agency referrals, building work, other records. 0 when the records carry no labels."
    )
    citation_id: str = "stat:base_rate"


def _rate_out(r: BaseRate) -> BaseRateOutput:
    return BaseRateOutput(
        approved=r.approved,
        approved_with_conditions=r.approved_with_conditions,
        denied=r.denied,
        withdrawn=r.withdrawn,
        total=r.total,
        window_years=r.window_years,
        scope=r.scope,
        rate_shown=r.rate_shown,
        approval_rate_pct=r.approval_rate_pct,
        excluded_grant_only=r.excluded_grant_only,
        excluded_undated=r.excluded_undated,
        excluded_not_use_decision=r.excluded_not_use_decision,
    )


async def read_base_rate_rows(store: Store, lat: float, lng: float) -> list[Nearby[Application]]:
    """Every record within 1,000 ft that the base rate looks at, read as two groups with a limit each: the
    Planning rows that can enter the pool, and the Entertainment Commission permits and ABC licences that are
    only counted as left out. One shared read would let the grant-only rows (hundreds of ABC licences on a
    dense corridor) push the farthest Planning decisions past the limit and understate N."""
    pool = await store.nearby_applications(
        lat, lng, FT_1000_M, kinds=sorted(BASE_RATE_KINDS), limit=BASE_RATE_LIMIT
    )
    grants = await store.nearby_applications(
        lat, lng, FT_1000_M, kinds=sorted(GRANT_ONLY_KINDS), limit=BASE_RATE_LIMIT
    )
    for what, rows in (("Planning", pool), ("grant-only", grants)):
        if len(rows) >= BASE_RATE_LIMIT:
            log.warning(
                "base rate: the %s read returned the limit of %s rows within 1,000 ft; counts may be understated",
                what,
                BASE_RATE_LIMIT,
            )
    return [*pool, *grants]


@neatlogs.span(kind="TOOL", name="tool.base_rate")
async def _base_rate(inp: BaseModel) -> BaseModel:
    assert isinstance(inp, BaseRateInput)
    # every record kind within 1,000 ft: the pool is Planning only, the grant-only rows are counted as left out
    apps = await read_base_rate_rows(get_store(), inp.lat, inp.lng)
    r = compute_base_rate(
        apps,
        inp.profile,
        REPORT_DAY.get() or dt.date.today(),
        zoning_district=inp.zoning_district,
        window_years=inp.window_years,
    )
    set_span_attributes(
        rows=r.total,
        rate_shown=r.rate_shown,
        approval_rate_pct=r.approval_rate_pct,
        excluded_grant_only=r.excluded_grant_only,
        excluded_undated=r.excluded_undated,
        excluded_not_use_decision=r.excluded_not_use_decision,
    )
    return _rate_out(r)


BASE_RATE = ToolSpec(
    name="base_rate",
    description=(
        "Deterministic outcome counts for comparable, dated Planning decisions near a point over the last N years. "
        "Entertainment Commission permits and ABC licences are never counted (grant-only lists), nor are undated "
        "rows. Where records carry a record kind, only use decisions about a food, drink or entertainment premises "
        "are counted: agency referrals and building work are left out. An approval rate is returned only when the "
        "count is 10 or more."
    ),
    input_model=BaseRateInput,
    handler=_base_rate,
)


# ---- read a decision -------------------------------------------------------------------------------------
class ReadDecisionInput(BaseModel):
    application_id: str = Field(description="Record id, e.g. 'datasf_planning:2019-012345CUA'.")


@neatlogs.span(kind="TOOL", name="tool.read_decision")
async def _read_decision(inp: BaseModel) -> BaseModel:
    assert isinstance(inp, ReadDecisionInput)
    app = await get_store().application(inp.application_id)
    set_span_attributes(rows=1 if app else 0)
    if app is None:
        raise ToolExecutionError("not_found", f"No record {inp.application_id}")
    return _app_out(app, 0.0)


READ_DECISION = ToolSpec(
    name="read_decision",
    description="Full record for one application: description, decision summary, every extracted condition and source link.",
    input_model=ReadDecisionInput,
    handler=_read_decision,
)

__all__ = [
    "BASE_RATE",
    "GEOCODE_ADDRESS",
    "NEARBY_APPLICATIONS",
    "NEARBY_BUSINESSES",
    "NEARBY_LICENSES",
    "ON_SALE_TYPES",
    "OVERLAYS_AT",
    "READ_DECISION",
    "ZONING_AT",
]
