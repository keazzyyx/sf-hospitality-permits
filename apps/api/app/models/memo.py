"""Location Risk Memo models: what the rules decide and the final Memo.

Report format 3 (2026-11-12): the report is the rules and the evidence only; no field holds text a model wrote.
Each row shows its status (set by rules in code, app.memo.pathway), the rule lines, the facts the rules read (each
with where it came from: the applicant's words with the quote, an intake answer, or a record), what is not
known, the referral steps and the source links. Comparable cases are the top of a fixed ranking, each with what
its record says; the outcome counts list the decisions they count (app.memo.evidence). A memo stored in an
earlier format is served as legacy (app.services.memos).
"""

from __future__ import annotations

from typing import Any, Literal

from annotated_types import MaxLen
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.memo.intake import IntakeAnswers
from app.models.profile import BusinessProfile, ClarifyingQuestion

ApprovalArea = Literal[
    "zoning_use", "alcohol", "entertainment", "health", "building_change_of_use", "outdoor"
]
ApprovalStatus = Literal[
    "allowed", "further_review", "potential_blocker", "not_permitted", "insufficient_information"
]
UnknownNeeds = Literal["plans", "inspection", "applicant_history", "agency_answer"]
# The Planning Code use a concept is looked up as (Planning Code § 102). "not_covered": the rule table has no
# control on file for the concept's use.
PlanningUse = Literal["bar", "restaurant", "limited_restaurant", "nighttime_entertainment", "not_covered"]
# Rule table v2: each reason the code can require a hearing is a trigger, evaluated on its own.
TriggerFamily = Literal[
    "new_use_control",  # T1: the district table makes the use conditional or not permitted
    "special_district_use_control",  # T2: a special use district makes the use itself conditional
    "enlarge_or_intensify",  # T3: enlarging or intensifying an existing conditional or nonconforming use
    "licence_in_restricted_district",  # T4: a liquor licence rule of a restricted district
    "formula_retail",  # T5
    "nighttime_entertainment",  # T6
    "use_size",  # T7
    "laundromat_removal",  # T8 (in force 2021-12-20 to 2024-12-20)
    "outdoor_activity_area",  # T9
    "amend_prior_conditions",  # T10
    "hours_of_operation",  # T11
]
# principal: this trigger asks for nothing. conditional / not_permitted: it does. not_decided: it matters in
# this district and an input is missing. does_not_apply: the concept or the district is outside it.
# code_and_practice_differ: the code text and Planning's own records are known to differ here.
TriggerControl = Literal[
    "principal", "conditional", "not_permitted", "not_decided", "does_not_apply", "code_and_practice_differ"
]
NoticeAnswer = Literal["required", "not_required", "not_established"]
# What the zoning control tables say about a NEW use of that kind at the address.
UsePermission = Literal["principal", "conditional", "not_permitted", "not_covered"]
ChangeOfUse = Literal["yes", "no", "not_established"]
CitationKind = Literal["application", "overlay", "zoning", "license", "statistic", "feedback", "catalog"]
MemoStatus = Literal["pending_clarification", "generating", "ready", "failed"]
Access = Literal["teaser", "full"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _soften_length_caps(cls, data: Any) -> Any:
        """Clamp over-long prose and over-full lists to the field's declared cap instead of rejecting.

        The caps still appear in the tool schema, so the model aims for them; but a sentence that runs
        a few hundred characters long must never sink a seven-minute memo run (production failed
        three resubmissions in a row on a 700-character ``what_to_say``). Citation and minimum-length
        rules are untouched: those are correctness, not style.
        """
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for name, field in cls.model_fields.items():
            if name not in out:
                continue
            cap = next((m.max_length for m in field.metadata if isinstance(m, MaxLen)), None)
            if cap is None:
                continue
            value = out[name]
            if isinstance(value, str) and len(value) > cap:
                out[name] = value[: cap - 1].rstrip() + "…"
            elif isinstance(value, list) and len(value) > cap:
                out[name] = value[:cap]
        return out


# Where one fact the rules read came from (app.memo.evidence).
FactOrigin = Literal["description", "intake_answer", "clarification_answer", "request", "record", "not_known"]
FACT_ORIGIN_LABELS: dict[str, str] = {
    "description": "Your description",
    "intake_answer": "Your answer to an intake question",
    "clarification_answer": "Your answer to a follow-up question",
    "request": "Given with the request",
    "record": "Records on file at this address",
    "not_known": "Not known",
}


class Citation(Strict):
    id: str
    kind: CitationKind
    label: str
    source_url: str
    excerpt: str | None = None


# ---- approvals ------------------------------------------------------------------------------------
# One row per approval the concept needs. The status vocabulary is fixed; its definitions are part of the report.
APPROVAL_AREA_LABELS: dict[str, str] = {
    "zoning_use": "Zoning and use",
    "alcohol": "Alcohol licence",
    "entertainment": "Entertainment permit",
    "health": "Health permit",
    "building_change_of_use": "Building permit and change of use",
    "outdoor": "Outdoor seating or activity area",
}
STATUS_DEFINITIONS: dict[str, str] = {
    "allowed": (
        "Allowed: the cited records or code sections show this approval is available as of right, or already "
        "exists for this space, without a discretionary hearing."
    ),
    "further_review": (
        "Further review: the approval is obtainable only through a discretionary or multi-step review (a hearing, "
        "a referral, a licence investigation) whose result the records do not settle."
    ),
    "potential_blocker": (
        "Potential blocker: a cited rule, cap or record could stop this approval or force a change to the concept "
        "unless a specific condition is met."
    ),
    "not_permitted": (
        "Not permitted: a cited code section prohibits this use or approval at this address as the concept is "
        "described."
    ),
    "insufficient_information": (
        "Insufficient information: the records in hand do not show whether this approval is needed or obtainable; "
        "the could-not-establish section says what would settle it."
    ),
}
# Most to least severe; the report's overall status is the most severe status among its rows, and never less
# severe than a definite headline finding (app.memo.pathway rule 8).
STATUS_SEVERITY: tuple[ApprovalStatus, ...] = (
    "not_permitted",
    "potential_blocker",
    "further_review",
    "insufficient_information",
    "allowed",
)
NO_HISTORY_NOTE = "No outcome history for this pathway yet."
NO_HISTORY_AREAS: frozenset[str] = frozenset({"alcohol", "entertainment"})


class OpenQuestion(Strict):
    """Something the records cannot establish, and what would."""

    question: str = Field(min_length=15, max_length=300)
    needs: UnknownNeeds = Field(
        description="plans = drawings or a code analysis; inspection = a site visit; applicant_history = the "
        "operator's own record; agency_answer = a written answer from the agency."
    )
    ask: str | None = Field(default=None, max_length=240, description="Who or which document settles it.")
    # The id of the optional intake question (app.memo.intake.QUESTIONS) whose answer gives this input, when one
    # does: the page offers that question, and the report run again with the answer settles it. None for a question
    # only an agency or the records can answer, and on memos stored before 2026-11-15.
    intake_question: str | None = Field(default=None, max_length=40)


# ---- final memo --------------------------------------------------------------------------------------
PLANNING_USE_LABELS: dict[str, str] = {
    "bar": "Bar",
    "restaurant": "Restaurant",
    "limited_restaurant": "Limited Restaurant",
    "not_covered": "a use the rule table does not cover",
}
USE_PERMISSION_LABELS: dict[str, str] = {
    "principal": "Permitted",
    "conditional": "Conditional use",
    "not_permitted": "Not permitted",
    "not_covered": "Not covered by the rule table",
}
TRIGGER_LABELS: dict[str, str] = {
    "new_use_control": "Use control of the zoning district",
    "special_district_use_control": "Use control of a special use district",
    "enlarge_or_intensify": "Enlarging or intensifying an existing use",
    "licence_in_restricted_district": "Liquor licence rule of a restricted district",
    "formula_retail": "Formula retail",
    "nighttime_entertainment": "Nighttime entertainment",
    "use_size": "Use size",
    "laundromat_removal": "Removal of a laundromat",
    "outdoor_activity_area": "Outdoor activity area",
    "amend_prior_conditions": "Changing the conditions of an earlier approval",
    "hours_of_operation": "Hours of operation",
}
# One fixed line on every report: what public records cannot show.
RECORDS_LIMITS = (
    "Physical and cost issues are outside what public records can show: ventilation and kitchen exhaust, exits "
    "and occupant load, accessibility, the condition of the space, and the landlord's consent."
)
CHANGE_OF_USE_LABELS: dict[str, str] = {
    "yes": "Change of use",
    "no": "No change of use",
    "not_established": "Change of use not established",
}


class RuleLine(Strict):
    """One rule the code applied, as a sentence built from the fields of the records it read. No model writes
    these, and the same facts always give the same lines."""

    rule_id: str  # stable id of the rule in app.memo.pathway, e.g. "zoning.use_control"
    text: str
    code_section: str | None  # the code section the rule rests on, e.g. "Planning Code § 762"
    source_url: str | None = None  # where that section can be read
    citations: list[str] = Field(default_factory=list)  # ids of the records the rule read


class ContingentReading(Strict):
    """What a trigger's own reading gives if inputs not known go one way. Set by rule; no model writes it."""

    control: Literal["conditional", "not_permitted"]
    condition: (
        str  # the way, in plain words, printed after "if" ("the floor area grows or storefronts are merged")
    )
    missing_inputs: list[str] = Field(
        default_factory=list
    )  # the inputs the condition turns on, as named phrases


class TriggerFinding(Strict):
    """One trigger, evaluated by rule on the rules date. Deterministic; no model writes these."""

    rule_id: str  # "T1" to "T11"
    family: TriggerFamily
    label: str  # TRIGGER_LABELS[family]
    control: TriggerControl
    missing_inputs: list[str] = Field(default_factory=list)  # plain names of what the input did not give
    lines: list[RuleLine]  # at least one: what was read and what it means here
    in_force_from: str | None = None  # the version of the control used: its start date, None = before 2022
    ordinance: str | None = None  # the ordinance that made that version, when the data names one
    differs_today: bool = False  # the control on the rules date is not today's control
    # What the trigger's own reading gives once inputs not known go one way (app.memo.triggers, "Contingent
    # readings", change of 2026-11-16): each a control that asks for something ("conditional" or "not_permitted")
    # and the way the inputs must go for it, checked against the trigger itself for every value those inputs can
    # take. Empty when there is none, and on reports made before 2026-11-16. It never changes `control`: the
    # report leads with each as a finding that depends on a missing input (app.memo.pathway rule 9).
    contingent: list[ContingentReading] = Field(default_factory=list)
    # The inputs not known that could still change a decided `control` (T7 reads the last use of the space
    # without naming it): the control is not then a definite headline finding. Empty otherwise.
    unsettled_by: list[str] = Field(default_factory=list)


# What a headline finding is (app.memo.pathway rule 9): a trigger bars the concept, a trigger asks for a
# Conditional Use Authorization, or a trigger asks for one (or bars the use) only if a missing input goes one way.
HeadlineKind = Literal["not_permitted", "conditional", "conditional_if", "not_permitted_if"]


class HeadlineFinding(Strict):
    """A finding that changes what the business needs at this address (a Planning Commission hearing, or a rule
    that bars it), printed first in the report. Set by rule (app.memo.pathway rule 9); no model writes it."""

    kind: HeadlineKind
    sentence: (
        str  # the fixed sentence, filled from the trigger's label and, for a contingent one, its condition
    )
    area: ApprovalArea  # the row that carries it
    status: ApprovalStatus  # what the finding gives the report; for a contingent one, its row's own status
    trigger: str  # "T1" to "T11"
    trigger_label: str  # the trigger's label as the sentence names it, e.g. "use size"
    definite: (
        bool  # False for a finding that depends on a missing input (`conditional_if`, `not_permitted_if`)
    )
    condition: str | None = None  # the way the missing input must go, in plain words; None when definite
    missing_inputs: list[str] = Field(default_factory=list)  # what is not known, for a contingent finding
    code_section: str | None = None  # the section the deciding line rests on
    source_url: str | None = None
    citations: list[str] = Field(default_factory=list)  # ids of the records the deciding line read
    basis: list[RuleLine] = Field(default_factory=list)  # the trigger's line that gives the reason


class ChangeAnswers(Strict):
    """Change of use is three separate questions. Each has its own answer and its own rule lines."""

    planning_use: ChangeOfUse  # Planning Code § 102 use categories: last lawful use against the proposed use
    planning_use_lines: list[RuleLine]
    building_occupancy: ChangeOfUse  # Building Code occupancy group; "not_established" unless the input says
    building_occupancy_lines: list[RuleLine]
    neighbourhood_notice: (
        NoticeAnswer  # Planning Code neighbourhood notification, as in force on the rules date
    )
    neighbourhood_notice_lines: list[RuleLine]


class Pathway(Strict):
    """The zoning answer for this concept at this address, looked up in code: zoning district + special use
    districts + the use + the hours. No model sets or changes it."""

    use: PlanningUse
    use_label: str
    district: str | None
    permission: UsePermission  # for a NEW use of this kind here: district control, SUDs and hours combined
    permission_label: str
    existing_use: PlanningUse | None  # what the records show the space is used as now; None = not shown
    change_of_use: ChangeOfUse
    change_of_use_label: str
    lines: list[RuleLine]  # the rules applied, in order
    notes: list[RuleLine]  # notes on file for the district and its SUDs that the rules do not evaluate
    # Rule table v2 (empty / None on a report made before it):
    rules_date: str | None = None  # the date whose rules were applied (today, or a past date in the backtest)
    triggers: list[TriggerFinding] = Field(default_factory=list)
    changes: ChangeAnswers | None = None


class RowDetermination(Strict):
    """One approval row as the rules set it."""

    area: ApprovalArea
    approval: str  # the specific approval, e.g. "Conditional Use Authorization (Planning Code § 303)"
    agency: str
    status: ApprovalStatus
    # A fixed qualifier printed after the status, e.g. "Code and Planning practice differ" or "public convenience
    # or necessity finding likely required". It never changes the status.
    status_note: str | None = None
    basis: list[RuleLine] = Field(min_length=1)
    # Steps inside this approval where one agency sends the application to another. A referral step is not an
    # approval: it never sets or changes the status, and a referral that was removed does not remove the approval.
    referral_steps: list[RuleLine] = Field(default_factory=list)
    missing_inputs: list[str] = Field(
        default_factory=list
    )  # named when the status is insufficient_information


class Determinations(Strict):
    """Everything the rules decide for one report: the pathway, every row's status, the overall line."""

    pathway: Pathway
    rows: list[RowDetermination]  # one per approval the concept needs, in report order
    # the most severe row status, and never less severe than a definite headline finding (pathway rule 8)
    overall_status: ApprovalStatus
    overall_line: str  # computed sentence: the headline findings first, then each row's status
    entitlement_path: str  # computed: the approvals to obtain, in order
    open_questions: list[OpenQuestion] = Field(default_factory=list)  # what the rules could not establish
    # the findings that change what the business needs here, most severe first (pathway rule 9)
    headline_findings: list[HeadlineFinding] = Field(default_factory=list)


class MemoFact(Strict):
    """One fact the rules read, and where it came from. Built by code (app.memo.evidence); no model writes it."""

    fact: str  # the fact's name, e.g. "closing" (app.memo.facts.MISSING_PHRASES keys, or a record fact)
    label: str  # e.g. "Closing time"
    value: str | None  # in plain words; None when not known
    origin: FactOrigin
    origin_label: str  # FACT_ORIGIN_LABELS[origin], with "Worked out by the rules from" when derived
    derived: bool = False  # the rules worked the value out from what the origin gave
    quotes: list[str] = Field(
        default_factory=list
    )  # the applicant's words that state it (origin "description")
    citations: list[str] = Field(default_factory=list)  # the records that show it (origin "record")


class MemoApprovalRow(Strict):
    area: ApprovalArea
    area_label: str
    approval: str  # set by rule
    agency: str  # set by rule
    status: ApprovalStatus  # set by rule
    status_note: str | None = None  # set by rule; a fixed qualifier printed after the status
    basis: list[RuleLine]  # the rules that set the status
    referral_steps: list[RuleLine] = Field(
        default_factory=list
    )  # steps inside the approval; never an approval
    missing_inputs: list[str] = Field(default_factory=list)
    facts: list[MemoFact] = Field(default_factory=list)  # the known facts this row's rules read
    history_note: str | None = None  # "No outcome history for this pathway yet." on alcohol and entertainment


class MemoOverall(Strict):
    # computed: the most severe status among the rows, and never less severe than a definite headline finding
    status: ApprovalStatus
    line: str  # computed: Determinations.overall_line
    citations: list[str]  # computed: the ids the rows' rule lines cite


class SourceNote(Strict):
    source: str
    label: str
    leaves_out: str


# What a record is, as distinct from what premises it concerns. Pathway counts (the base rate and the comparables)
# use only use decisions and agency referrals; building work and "other" records belong to the site history.
RecordKind = Literal[
    "use_decision",  # conditional use, change of use, variance, zoning letters and determinations
    "agency_referral",  # Planning's answer to an ABC, health or entertainment referral
    "building_work",  # kitchen hoods, tenant improvements, storefront and other building permits and reviews
    "other",  # project review meetings, complaints, enforcement, appeals
    "licence",  # an ABC licence on file
    "entertainment_permit",  # an Entertainment Commission permit on file
    "not_labelled",  # the record has not been through the record classifier
]
RECORD_KIND_LABELS: dict[str, str] = {
    "use_decision": "Use decision",
    "agency_referral": "Agency referral",
    "building_work": "Building work",
    "other": "Other record",
    "licence": "ABC licence",
    "entertainment_permit": "Entertainment permit",
    "not_labelled": "Not labelled",
}
# Record kinds that may appear among the comparables and, for use decisions only, in the base rate.
PATHWAY_RECORD_KINDS: frozenset[str] = frozenset({"use_decision", "agency_referral"})
SITE_HISTORY_LIMIT = 20


class SiteHistoryEntry(Strict):
    """One record on file at the report's own address or parcel. Deterministic: no model writes these."""

    application_id: str
    citation_id: str
    source: str
    source_label: str
    record_kind: RecordKind
    record_kind_label: str
    permit_type: str
    description: str = Field(max_length=300)
    address: str | None
    filed_at: str | None
    decided_at: str | None
    outcome: str
    status: str
    source_url: str
    # recorded facts, where the record carries them
    use_types: list[str] = Field(default_factory=list)
    hours_close: str | None = None
    conditions: list[str] = Field(default_factory=list)


class SiteHistory(Strict):
    """Every record on file at the report's address or parcel, newest first, building work included."""

    matched_by: str  # how records were tied to the site, e.g. "parcel 3596/024 or address 995 Valencia St"
    total: int  # all records at the site; `entries` lists at most SITE_HISTORY_LIMIT of them
    by_kind: dict[str, int]  # record_kind -> count over all `total` records
    entries: list[SiteHistoryEntry]
    note: str  # one sentence: what the list is, and what an empty list does and does not mean


class ComparableCase(Strict):
    application_id: str
    citation_id: str
    source: str
    source_label: str
    record_kind: RecordKind
    record_kind_label: str
    permit_type: str
    use_types: list[str]
    address: str | None
    distance_m: float
    filed_at: str | None
    decided_at: str | None
    days_to_decision: int | None
    outcome: str
    hours_close: str | None
    conditions: list[str]
    opposition_noted: bool | None
    similarity_score: float  # the score of the fixed ranking (app.memo.analytics.similarity)
    lat: float | None
    lng: float | None
    source_url: str


class ZoningBlock(Strict):
    district: str
    name: str
    bar_permission: str
    restaurant_permission: str
    rules: str
    code_section: str
    citation_id: str


class OverlayBlock(Strict):
    name: str
    kind: str
    effect: str
    code_section: str
    citation_id: str


class CountedDecision(Strict):
    """One dated decision counted in the base rate, with its source link."""

    application_id: str
    permit_type: str
    address: str | None
    outcome: str
    filed_at: str | None
    decided_at: str | None
    source_url: str


class BaseRateBlock(Strict):
    """Counts of dated comparables with known outcomes. A rate appears only when ``total`` is 10 or more, and
    the pool never includes grant-only sources (Entertainment Commission permits, ABC licences) or undated rows."""

    approved: int
    approved_with_conditions: int
    denied: int
    withdrawn: int
    total: int  # N: dated comparables with a known outcome
    window_years: int
    scope: str
    rate_shown: bool
    approval_rate_pct: float | None  # None unless rate_shown
    excluded_grant_only: int
    excluded_undated: int
    # Labelled Planning rows near the address left out because they are not a use decision about a food, drink or
    # entertainment premises: agency referrals, building work, other records, and records about other uses.
    # 0 when the store's records carry no labels.
    excluded_not_use_decision: int
    citation_id: str
    counted: list[CountedDecision] = Field(default_factory=list)  # the N decisions counted, newest first


class Memo(Strict):
    format_version: Literal[3] = 3
    address: str
    lat: float
    lng: float
    parcel: str | None
    description: str = ""  # the applicant's own words, as sent
    # Printed first (change of 2026-11-16): the findings that change what the business needs at this address, set
    # by rule (Determinations.headline_findings). Empty when there is none, and on memos stored before that date.
    headline_findings: list[HeadlineFinding] = Field(default_factory=list)
    overall: MemoOverall
    pathway: Pathway
    approvals: list[MemoApprovalRow]
    # every fact the rules read, known or not, with where it came from (app.memo.evidence)
    facts: list[MemoFact] = Field(default_factory=list)
    could_not_establish: list[OpenQuestion]  # the rules' open questions ("Not known: X. Needed for: Y.")
    records_limits: str = RECORDS_LIMITS  # fixed line: what public records cannot show
    zoning: ZoningBlock | None
    overlays: list[OverlayBlock]
    base_rate: BaseRateBlock
    comparable_cases: list[ComparableCase]
    comparables_note: str = ""  # fixed line: how the comparable cases were chosen
    site_history: SiteHistory
    source_notes: list[SourceNote]
    entitlement_path: str  # set by rule: the approvals to file, in order
    status_definitions: dict[str, str]
    citations: list[Citation]
    disclaimers: list[str]
    generated_at: str
    model_versions: dict[str, str]
    data_as_of: str


class MemoTeaser(Strict):
    overall_status: ApprovalStatus
    overall_line: str
    comparable_count: int
    approvals_count: int
    blockers_count: int  # rows that are potential_blocker or not_permitted


class MemoRecord(Strict):
    id: str
    user_id: str
    address: str
    lat: float | None
    lng: float | None
    description: str
    profile: BusinessProfile | None
    status: MemoStatus
    access: Access
    teaser: MemoTeaser | None
    memo: Memo | None
    legacy_format: bool = (
        False  # stored before format_version 3: memo and teaser are withheld; re-run to refresh
    )
    # A legacy memo the user unlocked whose one free re-run is still unused (app.services.memos): re-running it
    # with `rerun_of` makes a new memo unlocked, with no credit used and no free teaser counted. Always False on
    # a current memo, on a legacy memo that was never unlocked, and once the free re-run has been used.
    rerun_free: bool = False
    # The legacy memo this memo is a free re-run of (POST /v1/memos with `rerun_of`, when that re-run was free);
    # None otherwise. The page's Re-run link on a failed or abandoned free re-run carries it, so the retry is free.
    rerun_of: str | None = None
    clarification: dict[str, Any] | None = None
    # the applicant's answers to the optional intake questions, as sent with the create request and merged with
    # those of each answer round since; None when none was answered. A clarification run applies them again, and
    # the page's re-run link carries them.
    intake: IntakeAnswers | None = None
    batch_id: str | None
    created_at: str
    updated_at: str
    unlocked_at: str | None
    error: str | None
    # Answer rounds (POST /v1/memos/{id}/answers, app.memo.answers): the rounds that finished and were saved (0: the
    # report is the one the memo was made with), how many are left, whether a round is running now, whether this
    # memo can be answered that way (a ready memo in the current format, made since the intake result is kept, with
    # rounds left), and when the last round was saved.
    answers_round: int = 0
    answers_rounds_left: int = 0
    answers_running: bool = False
    answers_available: bool = False
    answered_at: str | None = None


class MemoRevision(Strict):
    """A version of a memo that an answer round replaced (GET /v1/memos/{id}/revisions). `round` is the round that
    replaced it: the version replaced by round 1 is the report the memo was made with. The memo is shown only when
    the memo is unlocked, as on every route; a teaser shows the version's teaser."""

    round: int
    replaced_at: str
    generated_at: str | None
    intake: IntakeAnswers | None
    teaser: MemoTeaser | None
    memo: Memo | None
    legacy_format: bool = False


class MemoSummary(Strict):
    id: str
    address: str
    concept: str
    status: MemoStatus
    access: Access
    overall_status: ApprovalStatus | None
    comparable_count: int | None
    legacy_format: bool = False
    created_at: str
    batch_id: str | None


class ClarificationPayload(Strict):
    questions: list[ClarifyingQuestion]
    answers: dict[str, Any] = Field(default_factory=dict)
