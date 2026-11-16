"""Plan models (strict Pydantic). These are the API contract — see docs/api-contract.md."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.catalog.loader import Category, Confidence, JurisdictionLevel, Range
from app.models.profile import BusinessProfile, BusinessType, ClarifyingQuestion

UrlStatus = Literal["live", "dead", "unchecked"]
Severity = Literal["high", "medium", "low"]
Likelihood = Literal["likely", "possible", "unlikely"]
PlanStatus = Literal["pending_clarification", "generating", "ready", "failed"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- stage outputs (what each agent must submit) ---------------------------------------
class RequiredPermit(StrictModel):
    permit_id: str = Field(description="Exact catalog id, e.g. 'sf.health_permit'.")
    why_required: str = Field(
        min_length=12,
        max_length=400,
        description="One or two sentences tying this permit to THIS business's facts.",
    )
    priority: Literal["critical", "standard", "optional"] = "standard"


class RequirementsResult(StrictModel):
    permits: list[RequiredPermit] = Field(min_length=1)
    unsupported_city_note: str | None = Field(
        default=None,
        description="When the city is not in the catalog: tell the user what is covered (federal + state + generic city checklist) and what to confirm locally.",
    )
    notes: str = Field(
        default="",
        description="Anything the operator should know about how the list was assembled (e.g. assumptions that added/removed permits).",
    )


class WeekNarrative(StrictModel):
    week_number: int = Field(ge=1)
    focus: str = Field(min_length=4, max_length=120)
    actions: list[str] = Field(min_length=1, max_length=6)


class TimelineNarrative(StrictModel):
    weeks: list[WeekNarrative] = Field(min_length=1)
    sequencing_rationale: str = Field(
        min_length=20, description="Why the plan is ordered this way: what gates what, what runs in parallel."
    )
    feasibility_assessment: str = Field(
        min_length=10, description="Whether the target open date is realistic, and what to compress if not."
    )


class Blocker(StrictModel):
    id: str = Field(pattern=r"^b[0-9]+$")
    title: str = Field(min_length=4, max_length=120)
    severity: Severity
    likelihood: Likelihood
    impact_days_min: int = Field(ge=0)
    impact_days_max: int = Field(ge=0)
    description: str = Field(min_length=20)
    mitigation: str = Field(min_length=20)
    related_step_ids: list[str] = Field(default_factory=list)

    @field_validator("impact_days_max")
    @classmethod
    def _max_ge_min(cls, v: int, info: Any) -> int:
        lo = int(info.data.get("impact_days_min", 0))
        return max(v, lo)


class BlockerResult(StrictModel):
    executive_summary: str = Field(
        min_length=80,
        description="2–4 short paragraphs of plain prose (no markdown headers) summarising the plan for the operator.",
    )
    blockers: list[Blocker] = Field(min_length=1, max_length=8)


# ---- final plan -----------------------------------------------------------------------
class PlanStep(StrictModel):
    id: str
    name: str
    category: Category
    issuing_agency: str
    jurisdiction_level: JurisdictionLevel
    application_url: str
    url_status: UrlStatus = "unchecked"
    typical_timeline_days: Range
    fee_range_usd: Range
    prerequisites: list[str]
    confidence: Confidence
    notes: str
    why_required: str
    stall_risk: str | None = None
    order: int
    track: str
    earliest_start_day: int
    earliest_finish_day: int
    latest_start_day: int
    latest_finish_day: int
    slack_days: int
    on_critical_path: bool
    scheduled_start: str
    scheduled_end: str


class TimelineWeek(StrictModel):
    week_number: int
    start_date: str
    end_date: str
    focus: str
    actions: list[str]
    step_ids_starting: list[str]
    step_ids_due: list[str]


class ParallelTrack(StrictModel):
    name: str
    step_ids: list[str]


class Timeline(StrictModel):
    start_date: str
    target_open_date: str | None
    projected_open_date: str
    optimistic_open_date: str
    total_days_min: int
    total_days_max: int
    feasible: bool | None
    days_short: int | None
    critical_path: list[str]
    parallel_tracks: list[ParallelTrack]
    weeks: list[TimelineWeek]
    sequencing_rationale: str


class FeeByCategory(StrictModel):
    category: Category
    min: float
    max: float


class FeeByStep(StrictModel):
    step_id: str
    min: float
    max: float


class FeeSummary(StrictModel):
    total_min: float
    total_max: float
    by_category: list[FeeByCategory]
    by_step: list[FeeByStep]
    notes: str


class PlanJurisdiction(StrictModel):
    city_name: str | None
    city_slug: str | None
    state: str | None
    county: str | None


class Plan(StrictModel):
    summary: str
    city_supported: bool
    jurisdiction: PlanJurisdiction
    steps: list[PlanStep]
    timeline: Timeline
    fees: FeeSummary
    blockers: list[Blocker]
    unsupported_city_note: str | None
    disclaimers: list[str]
    generated_at: str
    model_versions: dict[str, str]


# ---- previews ---------------------------------------------------------------------------
class PermitPreview(StrictModel):
    id: str
    name: str
    category: Category
    issuing_agency: str
    jurisdiction_level: JurisdictionLevel
    confidence: Confidence
    typical_timeline_days: Range
    fee_range_usd: Range
    why_required: str


class PreviewResult(StrictModel):
    preview_id: str
    profile: BusinessProfile
    city_supported: bool
    unsupported_city_note: str | None
    permits: list[PermitPreview]
    permit_count: int
    estimated_total_days: Range


# ---- persisted records -------------------------------------------------------------------
class Clarification(StrictModel):
    questions: list[ClarifyingQuestion]
    answers: dict[str, Any] = Field(default_factory=dict)


class PlanStepRecord(StrictModel):
    id: str
    plan_id: str
    step_key: str
    position: int
    name: str
    done: bool
    done_at: str | None
    notes: str | None


class PlanRecord(StrictModel):
    id: str
    user_id: str
    title: str
    description: str
    target_open_date: str | None
    status: PlanStatus
    version: int
    created_at: str
    updated_at: str
    profile: BusinessProfile | None
    clarification: Clarification | None
    plan: Plan | None
    steps: list[PlanStepRecord]
    error: str | None


class PlanSummary(StrictModel):
    id: str
    title: str
    status: PlanStatus
    version: int
    city_name: str | None
    business_type: BusinessType | None
    target_open_date: str | None
    projected_open_date: str | None
    steps_total: int
    steps_done: int
    created_at: str
    updated_at: str


class Entitlement(StrictModel):
    kind: Literal["free", "credits", "subscription"]
    plan_credits: int
    subscription_status: str | None
    current_period_end: str | None


class Me(StrictModel):
    id: str
    email: str | None
    plans_created: int
    free_limit: int
    free_plans_remaining: int
    entitlement: Entitlement
    can_create_plan: bool
    memo_credits: int = 0
    pro_status: str | None = None
    pro_current_period_end: str | None = None
    free_teasers_remaining: int = 0
    can_create_memo: bool = True
    can_unlock_memo: bool = False
    is_admin: bool = False
