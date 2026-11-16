// Copied verbatim from docs/api-contract.md ("Types (TypeScript)"). Keep in sync with the contract.

export type BusinessType = "restaurant" | "bar" | "cafe" | "food_truck" | "hotel" | "catering" | "other";
export type CookingType = "none" | "limited" | "full";
// "unknown": the concept serves alcohol and the description does not say what (never filled with a guess).
export type AlcoholType = "none" | "beer_wine" | "full_liquor" | "unknown";
export type Confidence = "verified" | "estimated";
export type UrlStatus = "live" | "dead" | "unchecked";
export type Category =
  | "business_registration" | "federal_tax" | "state_tax" | "local_tax" | "health" | "food_safety_cert"
  | "building" | "fire" | "alcohol" | "zoning" | "signage" | "grease" | "entertainment" | "outdoor_dining"
  | "labor" | "music_licensing" | "hotel" | "mobile_vending" | "other";

export interface Range { min: number; max: number }

export interface BusinessProfile {
  business_type: BusinessType;
  business_name: string | null;
  city_name: string | null;        // as the user wrote it ("SF Mission")
  city_slug: string | null;        // catalog slug or null if unsupported/unknown
  state: string | null;            // "CA"
  neighborhood: string | null;
  seats: number | null;
  square_feet: number | null;
  employees: number | null;
  hotel_rooms: number | null;
  serves_food: boolean;
  has_kitchen: boolean;
  cooking_type: CookingType;
  serves_alcohol: boolean;
  alcohol_type: AlcoholType;
  closes_after_midnight: boolean;
  closes_after_2am: boolean;
  live_entertainment: boolean;
  amplified_sound: boolean;
  dancing: boolean;
  outdoor_seating: boolean;
  sidewalk_or_parklet: boolean;
  change_of_use: boolean;
  tenant_improvements: boolean;
  new_construction: boolean;
  exterior_signage: boolean;
  plays_recorded_music: boolean;
  mobile_vending: boolean;
  uses_commissary: boolean;
  sells_packaged_goods: boolean;
  target_open_date: string | null; // YYYY-MM-DD
  assumptions: string[];           // what the intake agent assumed (shown in UI)
}

export interface ClarifyingQuestion {
  id: string;                       // e.g. "q1"
  question: string;
  kind: "single_choice" | "boolean" | "number" | "text";
  options: { value: string; label: string }[] | null;  // for single_choice
  maps_to: keyof BusinessProfile;   // which profile field the answer sets
  required: boolean;
}

export interface PlanStep {
  id: string;                        // permit id, e.g. "sf.health_permit"
  name: string;
  category: Category;
  issuing_agency: string;
  jurisdiction_level: "federal" | "state" | "county" | "city";
  application_url: string;
  url_status: UrlStatus;
  typical_timeline_days: Range;
  fee_range_usd: Range;
  prerequisites: string[];           // only ids that are also in this plan
  confidence: Confidence;
  notes: string;
  why_required: string;              // agent-written, specific to this business
  stall_risk: string | null;
  order: number;                     // 1-based topological order (ties broken by earliest start)
  track: string;                     // parallel track label: "Entity & tax", "Build-out", "Alcohol", ...
  earliest_start_day: number;        // days from timeline.start_date (0-based)
  earliest_finish_day: number;       // using max duration
  latest_start_day: number;          // backward pass from the deadline
  latest_finish_day: number;
  slack_days: number;                // latest_start - earliest_start
  on_critical_path: boolean;
  scheduled_start: string;           // ISO date = start_date + earliest_start_day
  scheduled_end: string;             // ISO date = start_date + earliest_finish_day
}

export interface TimelineWeek {
  week_number: number;               // 1-based
  start_date: string; end_date: string;
  focus: string;                     // agent-written headline for the week
  actions: string[];                 // agent-written concrete to-dos
  step_ids_starting: string[];
  step_ids_due: string[];
}

export interface Timeline {
  start_date: string;
  target_open_date: string | null;
  projected_open_date: string;       // start + total_days_max (realistic)
  optimistic_open_date: string;      // start + total_days_min
  total_days_min: number; total_days_max: number;
  feasible: boolean | null;          // null when no target date
  days_short: number | null;         // positive when target is earlier than projected
  critical_path: string[];           // step ids, in order
  parallel_tracks: { name: string; step_ids: string[] }[];
  weeks: TimelineWeek[];
  sequencing_rationale: string;
}

export interface FeeSummary {
  total_min: number; total_max: number;
  by_category: { category: Category; min: number; max: number }[];
  by_step: { step_id: string; min: number; max: number }[];
  notes: string;
}

export interface Blocker {
  id: string;
  title: string;
  severity: "high" | "medium" | "low";
  likelihood: "likely" | "possible" | "unlikely";
  impact_days_min: number; impact_days_max: number;
  description: string;
  mitigation: string;
  related_step_ids: string[];
}

export interface Plan {
  summary: string;                   // executive summary (markdown-free prose, 2–4 paragraphs)
  city_supported: boolean;
  jurisdiction: { city_name: string | null; city_slug: string | null; state: string | null; county: string | null };
  steps: PlanStep[];
  timeline: Timeline;
  fees: FeeSummary;
  blockers: Blocker[];
  unsupported_city_note: string | null;  // set when city_supported = false
  disclaimers: string[];
  generated_at: string;              // ISO datetime
  model_versions: Record<string, string>;
}

export interface PlanStepRecord {
  id: string;                        // uuid
  plan_id: string;
  step_key: string;                  // permit id
  position: number;
  name: string;
  done: boolean;
  done_at: string | null;
  notes: string | null;
}

export interface PlanRecord {
  id: string; user_id: string;
  title: string;                     // e.g. "Wine bar · San Francisco, CA"
  description: string;
  target_open_date: string | null;
  status: "pending_clarification" | "generating" | "ready" | "failed";
  version: number;
  created_at: string; updated_at: string;
  profile: BusinessProfile | null;
  clarification: { questions: ClarifyingQuestion[]; answers: Record<string, unknown> } | null;
  plan: Plan | null;
  steps: PlanStepRecord[];
  error: string | null;
}

export interface PlanSummary {
  id: string; title: string; status: PlanRecord["status"]; version: number;
  city_name: string | null; business_type: BusinessType | null;
  target_open_date: string | null; projected_open_date: string | null;
  steps_total: number; steps_done: number;
  created_at: string; updated_at: string;
}

export interface PermitPreview {
  id: string; name: string; category: Category; issuing_agency: string;
  jurisdiction_level: PlanStep["jurisdiction_level"]; confidence: Confidence;
  typical_timeline_days: Range; fee_range_usd: Range; why_required: string;
}

export interface PreviewResult {
  preview_id: string;
  profile: BusinessProfile;
  city_supported: boolean;
  unsupported_city_note: string | null;
  permits: PermitPreview[];          // the full list; timeline/fees/blockers are behind signup
  permit_count: number;
  estimated_total_days: Range;       // rough, from catalog maxima on the longest chain
}

export interface Me {
  id: string; email: string | null;
  plans_created: number; free_limit: number; free_plans_remaining: number;
  entitlement: { kind: "free" | "credits" | "subscription"; plan_credits: number;
                 subscription_status: string | null; current_period_end: string | null };
  can_create_plan: boolean;
  // Added by docs/api-contract-memo.md ("GET /v1/me now also includes ...").
  memo_credits: number;
  pro_status: string | null;        // "active" | "trialing" | "past_due" | "canceled" | null
  pro_current_period_end: string | null;
  free_teasers_remaining: number;
  can_create_memo: boolean;
  can_unlock_memo: boolean;         // Pro, or a memo credit on the account
  is_admin?: boolean;               // only for emails in ADMIN_EMAILS; treat missing as false
}

// ---- SSE event payloads (from the "Streaming (SSE)" section of the contract) ----

export type PlanStageName = "triage" | "intake" | "requirements" | "timeline" | "blocker" | "finalize";
/** The live memo stream: intake (the one model call), records (and the rules), precedent (the fixed ranking), finalize. */
export type MemoStageName = "intake" | "records" | "precedent" | "finalize";
export type StageName = PlanStageName | MemoStageName;
export type PlanToolName =
  | "lookup_permit_catalog" | "check_dependencies" | "estimate_timeline" | "get_fee_total" | "web_verify";
export type MemoToolName =
  | "geocode_address" | "nearby_applications" | "nearby_licenses" | "nearby_businesses" | "overlays_at"
  | "zoning_at" | "base_rate" | "read_decision";
export type ToolName = PlanToolName | MemoToolName;

export interface StageEvent {
  stage: StageName;
  status: "started" | "completed";
  message: string;
  elapsed_ms?: number;
}

export interface ToolEvent {
  stage: StageName;
  tool: ToolName;
  status: "started" | "completed";
  message: string;
  rows?: number;                     // memo streams: records touched by this tool call
}

/** Plan streams only. Memo streams send no text events. */
export interface NarrativeEvent { delta: string }

export interface NeedsClarificationEvent {
  plan_id?: string;
  preview_id?: string;
  memo_id?: string;
  questions: ClarifyingQuestion[];
  profile: BusinessProfile;
}

export interface StreamErrorEvent { code: string; message: string }

export type StreamEvent =
  | { event: "plan_created"; data: { plan_id: string } }
  | { event: "stage"; data: StageEvent }
  | { event: "tool"; data: ToolEvent }
  | { event: "narrative"; data: NarrativeEvent }
  | { event: "needs_clarification"; data: NeedsClarificationEvent }
  | { event: "preview"; data: PreviewResult }
  | { event: "plan"; data: PlanRecord }
  | { event: "memo_created"; data: { memo_id: string } }
  | { event: "answers_round"; data: { memo_id: string; round: number } }
  | { event: "memo"; data: MemoRecord }
  | { event: "error"; data: StreamErrorEvent };

export type StreamEventName = StreamEvent["event"];

// ---------------------------------------------------------------------------
// Mirrors docs/api-contract-memo.md ("Types"). Keep in sync with the contract.
// ---------------------------------------------------------------------------

export interface GeocodeSuggestion { address: string; normalized_address: string; lat: number; lng: number; parcel: string | null; zip_code: string | null; confidence: number }

// Report format 3 (2026-11-12): the rules and the evidence only; no text a model wrote. Mirrors
// apps/api/app/models/memo.py; that file is the source of truth.
export type ApprovalArea = "zoning_use" | "alcohol" | "entertainment" | "health" | "building_change_of_use" | "outdoor";
export type ApprovalStatus = "allowed" | "further_review" | "potential_blocker" | "not_permitted" | "insufficient_information";
export type UnknownNeeds = "plans" | "inspection" | "applicant_history" | "agency_answer";
/** The Planning Code use a concept is looked up as (Planning Code § 102). "not_covered": the rule table has no control on file for it. */
export type PlanningUse = "bar" | "restaurant" | "limited_restaurant" | "nighttime_entertainment" | "not_covered";
/** Rule table v2: each reason the code can require a hearing is a trigger, evaluated on its own (rule ids T1 to T11). */
export type TriggerFamily =
  | "new_use_control"               // T1: the district table makes the use conditional or not permitted
  | "special_district_use_control"  // T2: a special use district makes the use itself conditional
  | "enlarge_or_intensify"          // T3: enlarging or intensifying an existing conditional or nonconforming use
  | "licence_in_restricted_district" // T4: a liquor licence rule of a restricted district
  | "formula_retail"                // T5
  | "nighttime_entertainment"       // T6
  | "use_size"                      // T7
  | "laundromat_removal"            // T8 (in force 2021-12-20 to 2024-12-20)
  | "outdoor_activity_area"         // T9
  | "amend_prior_conditions"        // T10
  | "hours_of_operation";           // T11
/**
 * principal: this trigger asks for nothing. conditional / not_permitted: it does. not_decided: it matters in this
 * district and an input is missing. does_not_apply: the concept or the district is outside it.
 * code_and_practice_differ: the code text and Planning's own records are known to differ here.
 */
export type TriggerControl = "principal" | "conditional" | "not_permitted" | "not_decided" | "does_not_apply" | "code_and_practice_differ";
export type NoticeAnswer = "required" | "not_required" | "not_established";
/**
 * What the zoning control tables say about a new use of that kind at the address. "not_covered" is also the value
 * where a trigger is not decided or where the Code and Planning practice differ; `permission_label` says which.
 */
export type UsePermission = "principal" | "conditional" | "not_permitted" | "not_covered";
export type ChangeOfUse = "yes" | "no" | "not_established";
export type MemoStatus = "pending_clarification" | "generating" | "ready" | "failed";
export type MemoAccess = "teaser" | "full";

export interface Citation {
  id: string;                      // "app:datasf_planning:2019-012345CUA" | "overlay:static:sf:mission_alcoholic_beverage_sud" | "zoning:NCT-3" | "license:abc:123456" | "stat:base_rate" | "stat:density" | "geo:address" | "catalog:sf.conditional_use_authorization" | "feedback:<uuid>"
  kind: "application" | "overlay" | "zoning" | "license" | "statistic" | "feedback" | "catalog";
  label: string;                   // short human label shown in the memo footnote
  source_url: string;              // public record / code section URL
  excerpt: string | null;          // the sentence from the record that supports the claim
}

/** Where one fact the rules read came from. */
export type FactOrigin = "description" | "intake_answer" | "clarification_answer" | "request" | "record" | "not_known";

/** One fact the rules read, and where it came from. Built by code (apps/api/app/memo/evidence.py); no model writes it. */
export interface MemoFact {
  fact: string;                    // the fact's name, e.g. "closing", "seats", "existing_use_records"
  label: string;                   // e.g. "Closing time"
  value: string | null;            // in plain words; null when not known
  origin: FactOrigin;
  origin_label: string;            // "Your description", "Your answer to an intake question", "Records on file at this address", "Not known"; "Worked out by the rules from your description" when derived
  derived: boolean;                // the rules worked the value out from what the origin gave
  quotes: string[];                // the applicant's words that state it (origin "description")
  citations: string[];             // the records that show it (origin "record"); all are in Memo.citations
}

/**
 * One rule the API's code applied, as a sentence built from the fields of the records it read. No model writes
 * these, the citation check does not rewrite them, and the same facts always give the same lines.
 */
export interface RuleLine {
  rule_id: string;                 // stable id of the rule in apps/api/app/memo/pathway.py, e.g. "zoning.use_control"
  text: string;
  code_section: string | null;     // the code section the rule rests on, e.g. "Planning Code § 762"
  source_url: string | null;       // where that section can be read
  citations: string[];             // ids of the records the rule read
}

/** One trigger, evaluated by rule on the rules date. Deterministic; no model writes these. */
export interface TriggerFinding {
  rule_id: string;                 // "T1" to "T11"
  family: TriggerFamily;
  label: string;                   // TRIGGER_LABELS[family] in apps/api/app/models/memo.py
  control: TriggerControl;
  missing_inputs: string[];        // plain names of what the input did not give
  lines: RuleLine[];               // at least one: what was read and what it means here
  in_force_from: string | null;    // the version of the control used: its start date, null = before 2022
  ordinance: string | null;        // the ordinance that made that version, when the data names one
  differs_today: boolean;          // the control on the rules date is not today's control (the line says so)
  // From 2026-11-16: what the trigger's own reading gives once inputs not given go one way, each checked against
  // the trigger for every value they can take; and the inputs not given that could change a decided control.
  // Absent on older reports.
  contingent?: ContingentReading[];
  unsettled_by?: string[];
}

/** What a trigger's own reading gives if inputs not given go one way. `ContingentReading` in apps/api/app/models/memo.py. */
export interface ContingentReading {
  control: "conditional" | "not_permitted";
  condition: string;               // the way, in plain words, printed after "if"
  missing_inputs: string[];        // the inputs the condition turns on
}

/** What a headline finding is (app.memo.pathway rule 9). */
export type HeadlineKind = "not_permitted" | "conditional" | "conditional_if" | "not_permitted_if";

/**
 * A finding that changes what the business needs at this address (a Planning Commission hearing, or a rule that
 * bars it), printed first. Set by rule; no model writes it. `HeadlineFinding` in apps/api/app/models/memo.py.
 */
export interface HeadlineFinding {
  kind: HeadlineKind;
  sentence: string;                // the fixed sentence, filled from the trigger's label and its condition
  area: ApprovalArea;              // the row that carries it
  status: ApprovalStatus;          // what it gives the report; for a contingent one, its row's own status
  trigger: string;                 // "T1" to "T11"
  trigger_label: string;           // e.g. "use size"
  definite: boolean;               // false when it depends on a missing input
  condition: string | null;        // the way the missing input must go; null when definite
  missing_inputs: string[];
  code_section: string | null;
  source_url: string | null;
  citations: string[];
  basis: RuleLine[];               // the trigger's line that gives the reason
}

/** Change of use is three separate questions. Each has its own answer and its own rule lines. */
export interface ChangeAnswers {
  planning_use: ChangeOfUse;       // Planning Code § 102 use categories: last lawful use against the proposed use
  planning_use_lines: RuleLine[];
  building_occupancy: ChangeOfUse; // Building Code occupancy group; "not_established" unless the input says
  building_occupancy_lines: RuleLine[];
  neighbourhood_notice: NoticeAnswer; // Planning Code neighbourhood notification, as in force on the rules date
  neighbourhood_notice_lines: RuleLine[];
}

/**
 * The zoning answer for this concept at this address, looked up in code: zoning district + special use
 * districts + the use + the hours.
 */
export interface Pathway {
  use: PlanningUse;
  use_label: string;
  district: string | null;
  permission: UsePermission;       // for a NEW use of this kind here: district control, SUDs and hours combined
  permission_label: string;
  existing_use: PlanningUse | null; // what the records show the space is used as now; null = not shown
  change_of_use: ChangeOfUse;
  change_of_use_label: string;
  lines: RuleLine[];               // the rules applied, in order
  notes: RuleLine[];               // notes on file for the district and its SUDs that the rules do not evaluate
  // Rule table v2. A report stored before it has none of the three (the API then sends null / an empty list).
  rules_date?: string | null;      // "YYYY-MM-DD": the date whose rules were applied (today, or a past date in the backtest)
  triggers?: TriggerFinding[];     // every trigger, T1 to T11, in order
  changes?: ChangeAnswers | null;
}

/** One row per approval the concept needs. `status`, `approval` and `agency` are set by rules in code. */
export interface MemoApprovalRow {
  area: ApprovalArea;
  area_label: string;
  approval: string;                // set by rule, e.g. "Conditional Use Authorization (Planning Code § 303)"
  agency: string;                  // set by rule
  status: ApprovalStatus;          // set by rule
  // Set by rule: a fixed qualifier printed after the status, e.g. "Code and Planning practice differ" or "public
  // convenience or necessity finding likely required". It never changes the status.
  status_note?: string | null;
  basis: RuleLine[];               // the rules that set the status ("Rules applied")
  // Steps inside this approval where one agency sends the application to another. A referral step is not an
  // approval: it never sets or changes the status, and a referral that was removed does not remove the approval.
  referral_steps?: RuleLine[];
  missing_inputs?: string[];       // named when the status is insufficient_information ("Not given")
  facts: MemoFact[];               // the known facts this row's rules read, each with where it came from
  history_note: string | null;     // "No outcome history for this pathway yet." on alcohol and entertainment
}

export interface MemoOverall {
  status: ApprovalStatus;          // computed: the most severe row status, never below a definite headline finding
  line: string;                    // computed by rule: the headline findings first, then each row's status
  citations: string[];             // computed: the ids the rows' rule lines cite
}

/** Something the records cannot establish, and what would. */
export interface OpenQuestion {
  question: string;
  needs: UnknownNeeds;
  ask: string | null;              // who or which document settles it
  // The optional intake question whose answer gives this input, when one does: the page offers it, and the report
  // run again with the answer settles it. Null or absent for a question only an agency or the records can answer,
  // and on memos stored before 2026-11-15.
  intake_question?: IntakeQuestionId | null;
}

export interface SourceNote { source: string; label: string; leaves_out: string }

/**
 * What a record is, as distinct from what premises it concerns. Pathway counts (the base rate and the comparables)
 * use only use decisions and agency referrals; building work and "other" records belong to the site history.
 */
export type RecordKind =
  | "use_decision"          // conditional use, change of use, variance, zoning letters and determinations
  | "agency_referral"       // Planning's answer to an ABC, health or entertainment referral
  | "building_work"         // kitchen hoods, tenant improvements, storefront and other building permits and reviews
  | "other"                 // project review meetings, complaints, enforcement, appeals
  | "licence"               // an ABC licence on file
  | "entertainment_permit"  // an Entertainment Commission permit on file
  | "not_labelled";         // the record has not been through the record classifier

/** One record on file at the report's own address or parcel. Deterministic: no model writes these. */
export interface SiteHistoryEntry {
  application_id: string; citation_id: string;
  source: string; source_label: string;
  record_kind: RecordKind; record_kind_label: string;
  permit_type: string;
  description: string;             // at most 300 characters
  address: string | null;
  filed_at: string | null; decided_at: string | null;
  outcome: string;
  status: string;                  // the source's own status string
  source_url: string;
  use_types: string[];             // recorded facts, where the record carries them
  hours_close: string | null;
  conditions: string[];
}

/** Every record on file at the report's address or parcel, newest first, building work included. */
export interface SiteHistory {
  matched_by: string;              // how records were tied to the site, e.g. "Parcel 3596/024 or the address 995 Valencia St"
  total: number;                   // all records at the site; `entries` lists at most 20 of them (SITE_HISTORY_LIMIT)
  by_kind: Record<string, number>; // record_kind -> count over all `total` records
  entries: SiteHistoryEntry[];
  note: string;                    // one sentence: what the list is, and what an empty list does and does not mean
}

export interface ComparableCase {
  application_id: string; citation_id: string;
  source: string; source_label: string;
  record_kind: RecordKind; record_kind_label: string;  // use_decision or agency_referral; not_labelled when the store has no labels; entertainment_permit either way
  permit_type: string; use_types: string[]; address: string | null; distance_m: number;
  filed_at: string | null; decided_at: string | null; days_to_decision: number | null;
  outcome: string;
  hours_close: string | null; conditions: string[]; opposition_noted: boolean | null;
  similarity_score: number;        // 0..1 deterministic: the rank in the fixed ranking
  lat: number | null; lng: number | null; source_url: string;
}

export interface ZoningBlock { district: string; name: string; bar_permission: string; restaurant_permission: string; rules: string; code_section: string; citation_id: string }
export interface OverlayBlock { name: string; kind: string; effect: string; code_section: string; citation_id: string }

/** One dated decision counted in the outcome counts, with its source link. */
export interface CountedDecision {
  application_id: string; permit_type: string; address: string | null;
  outcome: string; filed_at: string | null; decided_at: string | null; source_url: string;
}

/**
 * Counts of dated comparables with known outcomes. A rate appears only when `rate_shown` is true
 * (`total` is 10 or more); the pool never includes grant-only sources or undated rows.
 */
export interface BaseRateBlock {
  approved: number; approved_with_conditions: number; denied: number; withdrawn: number;
  total: number;                   // N: dated comparables with a known outcome
  window_years: number; scope: string;
  rate_shown: boolean;
  approval_rate_pct: number | null; // null unless rate_shown
  excluded_grant_only: number; excluded_undated: number;
  // Labelled Planning rows near the address left out because they are not a use decision about a food, drink or
  // entertainment premises (agency referrals, building work, other records, other uses). 0 when the records carry no labels.
  excluded_not_use_decision: number;
  citation_id: string;
  counted: CountedDecision[];      // the N decisions counted, newest first, each with its source link
}

export interface Memo {
  format_version: 3;
  address: string; lat: number; lng: number; parcel: string | null;
  description: string;             // the applicant's own words, as sent
  headline_findings?: HeadlineFinding[];  // printed first; absent on memos stored before 2026-11-16
  overall: MemoOverall;
  pathway: Pathway;
  approvals: MemoApprovalRow[];
  facts: MemoFact[];               // every fact the rules read, known or not, with where it came from
  could_not_establish: OpenQuestion[];   // the rules' open questions: "Not known: X. Needed for: Y."
  records_limits?: string;         // one fixed line (RECORDS_LIMITS in the API): what public records cannot show
  zoning: ZoningBlock | null;
  overlays: OverlayBlock[];
  base_rate: BaseRateBlock;
  comparable_cases: ComparableCase[];
  comparables_note: string;        // fixed line: how the comparable cases were chosen
  site_history: SiteHistory;
  source_notes: SourceNote[];
  entitlement_path: string;        // set by rule: the approvals to file, in order
  status_definitions: Record<string, string>;      // keyed by ApprovalStatus
  citations: Citation[];
  disclaimers: string[];
  generated_at: string; model_versions: Record<string, string>; data_as_of: string;
}

export interface MemoTeaser {
  overall_status: ApprovalStatus;
  overall_line: string;
  comparable_count: number;
  approvals_count: number;
  blockers_count: number;          // rows that are potential_blocker or not_permitted
}

export interface MemoRecord {
  id: string; user_id: string; address: string; lat: number | null; lng: number | null;
  description: string; profile: BusinessProfile | null;
  status: MemoStatus;
  access: MemoAccess;
  teaser: MemoTeaser | null;       // present once ready, unless legacy_format
  memo: Memo | null;               // only when access == "full", and never when legacy_format
  legacy_format: boolean;          // stored before format_version 3: memo and teaser are withheld; re-run to refresh
  // A legacy memo the user unlocked whose one free re-run is unused: POST /v1/memos with `rerun_of` makes the new
  // memo unlocked, with no credit used and no free teaser counted. Set on GET /v1/memos/{id}; absent elsewhere.
  rerun_free?: boolean;
  // The earlier-format memo this memo is the free re-run of; absent or null otherwise. When such a re-run failed
  // or was abandoned, the page's Re-run link sends it as `rerun_of`, so the retry is free too.
  rerun_of?: string | null;
  clarification: { questions: ClarifyingQuestion[]; answers: Record<string, unknown> } | null;
  // The optional intake answers sent with the create request (every question's key, a skipped one null); null when none
  // was answered. Absent on records stored before the intake questions.
  intake?: IntakeAnswers | null;
  batch_id: string | null; created_at: string; updated_at: string; unlocked_at: string | null; error: string | null;
  // Answer rounds (POST /v1/memos/{id}/answers, owner decision of 2026-11-16): the same memo run again with more
  // intake answers, free, up to five times. The rounds that finished, how many are left, whether one is running now,
  // whether this memo can be answered that way, and when the last round was saved. Absent from an older API build.
  answers_round?: number;
  answers_rounds_left?: number;
  answers_running?: boolean;
  answers_available?: boolean;
  answered_at?: string | null;
}

/** A version of a memo that an answer round replaced (GET /v1/memos/{id}/revisions). `round` is the round that
 * replaced it: the version replaced by round 1 is the report the memo was made with. `memo` only when the memo is
 * unlocked. */
export interface MemoRevision {
  round: number;
  replaced_at: string;
  generated_at: string | null;
  intake: IntakeAnswers | null;
  teaser: MemoTeaser | null;
  memo: Memo | null;
  legacy_format: boolean;
}

/** How the liquor licence will be obtained (the intake question). "already_held": a licence already held at this
 * address; "none": no alcohol (the applicant's answer wins over the description). */
export type LiquorLicence =
  | "new" | "transfer_from_another_owner" | "transfer_from_another_location" | "already_held" | "none";

export type StoryAnswer = "basement" | "first" | "second" | "third_or_above";
export type AlcoholServed = "beer_wine" | "full_liquor";
/** What the space was last used as. "vacant" is not an answer: an empty space is asked what it was last used as. */
export type LastUse = "restaurant" | "bar" | "limited_restaurant" | "nighttime_entertainment" | "retail" | "laundromat" | "other";
export type OutdoorAreaAnswer = "none" | "front" | "rear_or_side" | "rooftop" | "parking_lot" | "sidewalk";
export type ExistingBusinessChange = "none" | "enlarge" | "intensify" | "enlarge_and_intensify";
export type EntertainmentAnswer = "none" | "limited_live_performance" | "place_of_entertainment";
export type OccupancyGroup = "B" | "A-2";
/** The kind of food or drink service of a bar that serves no alcohol, which is not a Bar (Planning Code § 102):
 * "other" is another use, or not sure, and gives no use (the report then still names it). */
export type FoodServiceAnswer = "restaurant" | "limited_restaurant" | "other";

/** The ids of the optional intake questions, in the order they are asked (apps/api/app/memo/intake.py, `QUESTIONS`). */
export type IntakeQuestionId =
  | "part_of_chain" | "other_locations" | "floor_area_sqft" | "liquor_licence" | "stories" | "alcohol_served"
  | "closing_time" | "last_use" | "fewer_than_50_people" | "outdoor_area" | "outdoor_alcohol_service"
  | "food_service" | "existing_business_change" | "floor_area_before_sqft" | "merges_storefronts" | "amends_prior_approval"
  | "entertainment" | "existing_occupancy_group";

/**
 * The optional intake questions (apps/api/app/memo/intake.py). Every key optional; absent or null = skipped. Each
 * gives one fact the rules read; an answer wins over the description. The API refuses answers that contradict each
 * other (422): `alcohol_served`, or `outdoor_alcohol_service: true`, with `liquor_licence: "none"`;
 * `outdoor_alcohol_service` with `outdoor_area: "none"`; and `food_service` with an answer that says alcohol is
 * served (a liquor licence other than "none", `alcohol_served`, or `outdoor_alcohol_service: true`).
 */
export interface IntakeAnswers {
  part_of_chain?: boolean | null;
  other_locations?: number | null;  // only with part_of_chain true; 0..100000
  floor_area_sqft?: number | null;  // square feet, 1..1000000
  liquor_licence?: LiquorLicence | null;
  stories?: StoryAnswer[] | null;   // one or more, each once
  alcohol_served?: AlcoholServed | null;
  closing_time?: string | null;     // "HH:MM", 24-hour ("02:00" is 2 a.m.)
  last_use?: LastUse | null;
  fewer_than_50_people?: boolean | null;
  outdoor_area?: OutdoorAreaAnswer | null;
  outdoor_alcohol_service?: boolean | null;
  food_service?: FoodServiceAnswer | null;  // read only for a bar that serves no alcohol (not a Bar)
  existing_business_change?: ExistingBusinessChange | null;  // any answer says a business of the same kind is already there
  floor_area_before_sqft?: number | null;  // square feet, 1..1000000
  merges_storefronts?: boolean | null;
  amends_prior_approval?: boolean | null;
  entertainment?: EntertainmentAnswer | null;
  existing_occupancy_group?: OccupancyGroup | null;  // from the plans or the certificate of occupancy
}

/** `POST /v1/memos`. */
export interface CreateMemoBody {
  address: string;
  description: string;
  lat?: number;
  lng?: number;
  profile_overrides?: Partial<BusinessProfile>;
  intake?: IntakeAnswers;           // sent only when at least one question is answered
  // Re-run of a memo in an earlier report format: the API uses that memo's address, coordinates and description
  // (the ones sent here are ignored; profile_overrides is refused with it). The first re-run of one the user
  // unlocked is free.
  rerun_of?: string;
}

export interface MemoSummary {
  id: string; address: string; concept: string; status: MemoStatus; access: MemoAccess;
  overall_status: ApprovalStatus | null; comparable_count: number | null;
  legacy_format: boolean;
  created_at: string; batch_id: string | null;
}

export interface AdminOverview {
  ingestion: { backend: string; counts: Record<string, number>; by_source: Record<string, number>; last_runs: Record<string, { started_at: string; finished_at: string | null; status: string; rows_fetched: number; rows_upserted: number; error: string | null }> };
  feedback: { total: number; by_outcome: Record<string, number>; by_concept: Record<string, number>; response_rate_pct: number | null; emails_sent: number };
  memos: { total: number; full: number; teaser: number; last_7_days: number; by_overall_status: Record<string, number>; legacy_format: number };  // by_overall_status leaves out the legacy_format memos
  users: { total: number; pro: number };
}

// ---- Non-type-table shapes from the same contract (route tables) ----

export interface FeedbackInfo { memo_id: string; address: string; concept_type: string; already_answered: boolean }
export type FeedbackOutcome = "approved" | "approved_with_conditions" | "denied" | "withdrew" | "still_pending";
export interface BulkUploadResult { batch_id: string; memo_ids: string[]; skipped: { row: number; reason: string }[] }
export interface BulkBatch { batch_id: string; memos: MemoSummary[] }
export type CheckoutMode = "plan" | "subscription" | "memo" | "pro";

/** Minimal GeoJSON typing for `GET /v1/memos/{id}/map.geojson`. */
export interface GeoJsonGeometry { type: string; coordinates: unknown }
export interface GeoJsonFeature { type: "Feature"; geometry: GeoJsonGeometry | null; properties: Record<string, unknown> | null }
export interface GeoJsonFeatureCollection { type: "FeatureCollection"; features: GeoJsonFeature[] }
