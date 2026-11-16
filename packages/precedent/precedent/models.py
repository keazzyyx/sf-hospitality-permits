"""Normalized records shared by every ingestion source, the store, and the memo agents.

Everything carries `source`, `source_url`, `fetched_at` and `raw_ref` (where the raw response was
saved) so any sentence in a memo can be traced back to a public record.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Source = Literal[
    "datasf_planning",  # Planning Department permits / applications (CUA etc.)
    "datasf_entertainment",  # Entertainment Commission permits
    "datasf_business",  # Registered business locations
    "datasf_zoning",  # Zoning district polygons
    "datasf_sud",  # Special Use District polygons
    "abc",  # California ABC licenses
    "sf_planning_hearings",  # Planning Commission motions / minutes (PDF)
    "static",  # hand-maintained tables (Planning Code rules)
    "user_feedback",  # outcomes reported by Permit Memo users
]

ApplicationKind = Literal[
    "cua",  # Conditional Use Authorization
    "planning_other",  # other Planning entitlements (variance, change of use, etc.)
    "entertainment_poe",
    "entertainment_llp",
    "entertainment_sound",  # outdoor amplified sound / one-time / fixed place
    "entertainment_other",
    "abc_license",
]
UseType = Literal[
    "bar",
    "restaurant",
    "cafe",
    "nightclub",
    "live_entertainment",
    "outdoor_seating",
    "hotel",
    "retail_alcohol",
    "cannabis",
    "other",
]
Outcome = Literal["approved", "approved_with_conditions", "denied", "withdrawn", "pending", "unknown"]
Confidence = Literal["high", "medium", "low"]
OverlayKind = Literal["zoning_district", "alcohol_sud", "special_use_district", "nc_rule", "late_night_rule"]
FeedbackOutcome = Literal["approved", "approved_with_conditions", "denied", "withdrew", "still_pending"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(Strict):
    source: Source
    source_id: str = Field(
        description="Primary key in the source system (record number, license number, objectid)."
    )
    source_url: str = Field(description="Public URL a reader can open to see the record.")
    fetched_at: dt.datetime
    raw_ref: str | None = Field(default=None, description="Path / object key of the saved raw response page.")


class Application(Provenance):
    """One permit / entitlement / license application. Primary key `id` = f"{source}:{source_id}"."""

    id: str
    kind: ApplicationKind
    permit_type: str = Field(
        description="Source's own label, e.g. 'Conditional Use Authorization', 'Place of Entertainment', 'Type 42'."
    )
    use_types: list[UseType] = Field(default_factory=list)
    description: str = ""
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    parcel: str | None = Field(default=None, description="Assessor block/lot, e.g. '3596/024'.")
    zoning_district: str | None = None
    status: str = Field(default="", description="Source's own status string.")
    outcome: Outcome = "unknown"
    filed_at: dt.date | None = None
    decided_at: dt.date | None = None
    hours_close: str | None = Field(default=None, description="Latest closing time mentioned, 24h 'HH:MM'.")
    late_night: bool | None = Field(
        default=None, description="Operates after midnight (2am+ for 'extended')."
    )
    conditions: list[str] = Field(default_factory=list)
    opposition_noted: bool | None = None
    decision_summary: str | None = None
    extraction_confidence: Confidence | None = None
    license_type: str | None = Field(
        default=None, description="ABC license type code when kind == abc_license."
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Source-specific fields worth keeping (hearing date, planner, etc.).",
    )

    @field_validator("id")
    @classmethod
    def _id_shape(cls, v: str) -> str:
        if ":" not in v:
            raise ValueError("id must be '<source>:<source_id>'")
        return v

    @property
    def has_geom(self) -> bool:
        return self.lat is not None and self.lng is not None


class Location(Strict):
    """A normalized SF address with parcel, geometry and zoning context."""

    address: str
    normalized_address: str
    parcel: str | None = None
    lat: float
    lng: float
    zoning_district: str | None = None
    zoning_name: str | None = None
    overlays: list[str] = Field(default_factory=list, description="Overlay ids that contain the point.")
    neighborhood: str | None = None
    source: Source = "datasf_zoning"
    source_url: str = ""
    fetched_at: dt.datetime


class Overlay(Strict):
    """A polygon with rules: zoning districts, Special Use Districts, NC-district bar rules."""

    id: str
    kind: OverlayKind
    name: str
    rules: str = Field(description="Plain-English effect on bars / restaurants / late hours / entertainment.")
    code_section: str = Field(description="Planning Code section(s), e.g. 'Planning Code § 249.60'.")
    geom: dict[str, Any] | None = Field(
        default=None,
        description="GeoJSON geometry (Polygon / MultiPolygon) in WGS84, or None for rule-only rows.",
    )
    district_codes: list[str] = Field(
        default_factory=list,
        description="Zoning district codes this rule row applies to (for rule-only rows).",
    )
    bar_permission: Literal["principal", "conditional", "prohibited", "unknown"] = "unknown"
    restaurant_permission: Literal["principal", "conditional", "prohibited", "unknown"] = "unknown"
    late_night_rule: str | None = None
    source: Source = "static"
    source_url: str
    fetched_at: dt.datetime


class Business(Strict):
    """A registered business location (density / undue-concentration signal)."""

    id: str
    dba_name: str
    naics_code: str | None = None
    naics_description: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    is_food_or_drink: bool = False
    is_bar: bool = False
    source: Source = "datasf_business"
    source_url: str
    fetched_at: dt.datetime


class OutcomeFeedback(Strict):
    id: str | None = None
    memo_id: str
    user_id: str | None
    address: str
    lat: float | None
    lng: float | None
    concept_type: str
    outcome: FeedbackOutcome
    notes: str | None = None
    reported_at: dt.datetime


class IngestionRun(Strict):
    source: Source
    started_at: dt.datetime
    finished_at: dt.datetime | None = None
    status: Literal["running", "ok", "failed"] = "running"
    rows_fetched: int = 0
    rows_upserted: int = 0
    error: str | None = None
    notes: str | None = None


class SourceBatch(Strict):
    """What one source's parser produces from one raw file."""

    applications: list[Application] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    overlays: list[Overlay] = Field(default_factory=list)
    businesses: list[Business] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.applications) + len(self.locations) + len(self.overlays) + len(self.businesses)
