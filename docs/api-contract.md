# Permit Memo API contract (v1)

Base URL: `NEXT_PUBLIC_API_URL` (local: `http://localhost:8000`). All responses are JSON unless noted.

## Authentication

Every `/v1/*` route requires `Authorization: Bearer <Supabase access token>` (the JWT from
`supabase.auth.getSession()`), **except**: `POST /v1/preview`, `POST /v1/preview/{id}/clarify`,
`POST /v1/leads`, `POST /v1/billing/webhook`, `GET /v1/catalog/cities`, `GET /healthz`.
Invalid / expired / missing tokens → `401 {"detail": {"code": "unauthorized", "message": "..."}}`.

Error body shape everywhere: `{"detail": {"code": "<snake_case>", "message": "<human>", ...extra}}`.

Codes: `unauthorized`, `not_found`, `validation_error`, `paywall` (402), `rate_limited` (429),
`not_hospitality` (422, triage rejected the description), `generation_failed` (500), `stripe_error`.

## Streaming (SSE)

`POST /v1/preview`, `POST /v1/plans`, `POST /v1/plans/{id}/clarify`, `POST /v1/plans/{id}/rerun`
respond with `Content-Type: text/event-stream`. Use `fetch` + a reader (not `EventSource`, which
cannot POST or send headers). Each event is `event: <name>\ndata: <json>\n\n`.

| event | data | notes |
|---|---|---|
| `plan_created` | `{plan_id}` | first event on `/v1/plans` (not on preview) |
| `stage` | `{stage, status: "started"\|"completed", message, elapsed_ms?}` | stage ∈ `triage, intake, requirements, timeline, blocker, finalize`. `message` is user-facing ("Checking San Francisco Department of Public Health requirements…") |
| `tool` | `{stage, tool, status: "started"\|"completed", message}` | tool ∈ `lookup_permit_catalog, check_dependencies, estimate_timeline, get_fee_total, web_verify` |
| `narrative` | `{delta}` | streamed text from the blocker stage (plan narrative). Concatenate deltas. |
| `needs_clarification` | `{plan_id?, preview_id?, questions: ClarifyingQuestion[], profile: BusinessProfile}` | terminal for this request; UI renders a form and POSTs `/clarify` |
| `preview` | `PreviewResult` | terminal for `/v1/preview` |
| `plan` | `PlanRecord` | terminal for plan routes |
| `error` | `{code, message}` | terminal |

Before the stream starts the server may reject with a normal JSON error (`402 paywall`, `429 rate_limited`, `401`).

## Routes

| method | path | body | returns |
|---|---|---|---|
| GET | `/healthz` | – | `{status:"ok", version, env, neatlogs: {status: "pass"\|"warn"\|"fail", checks: [...]}}` |
| GET | `/v1/catalog/cities` | – | `{cities: [{slug, name, state, supported: true}]}` |
| POST | `/v1/preview` | `{description}` | SSE → `preview` (no auth; 10/hour/IP) |
| POST | `/v1/preview/{preview_id}/clarify` | `{answers: Record<question_id, value>}` | SSE → `preview` |
| POST | `/v1/leads` | `{email, city?, state?, description?}` | `201 {ok: true}` (no auth) |
| GET | `/v1/me` | – | `{profile: Me}` |
| POST | `/v1/plans` | `{description, target_open_date?: "YYYY-MM-DD", preview_id?}` | SSE → `plan` |
| POST | `/v1/plans/{id}/clarify` | `{answers}` | SSE → `plan` |
| POST | `/v1/plans/{id}/rerun` | `{description?, target_open_date?, profile_overrides?: Partial<BusinessProfile>}` | SSE → `plan` (bumps `version`, resets step done flags only for steps that no longer exist) |
| GET | `/v1/plans` | – | `{plans: PlanSummary[]}` newest first |
| GET | `/v1/plans/{id}` | – | `{plan: PlanRecord}` |
| PATCH | `/v1/plans/{id}/steps/{step_id}` | `{done?: boolean, notes?: string}` | `{step: PlanStepRecord}` |
| GET | `/v1/plans/{id}/export.pdf` | – | `application/pdf` (server-rendered) |
| DELETE | `/v1/plans/{id}` | – | `204` |
| POST | `/v1/billing/checkout` | `{mode: "plan"\|"subscription", success_url, cancel_url}` | `{url}` (Stripe Checkout) |
| POST | `/v1/billing/portal` | `{return_url}` | `{url}` (Stripe customer portal) |
| POST | `/v1/billing/webhook` | Stripe event (raw body + `Stripe-Signature`) | `{received: true}` |

Entitlement rule: a user may create **3 free plans** (`plans_created` counts `POST /v1/plans`
successes; reruns and clarifications are free). After that `POST /v1/plans` returns
`402 {"detail": {"code": "paywall", "plans_created": 3, "free_limit": 3}}` unless the user has
`subscription_status = "active"|"trialing"` or `plan_credits > 0` (one credit is consumed per plan).

## Types (TypeScript)

```ts
export type BusinessType = "restaurant" | "bar" | "cafe" | "food_truck" | "hotel" | "catering" | "other";
export type CookingType = "none" | "limited" | "full";
export type AlcoholType = "none" | "beer_wine" | "full_liquor";
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
  // Location Risk Memo entitlements (see api-contract-memo.md)
  memo_credits: number; pro_status: string | null; pro_current_period_end: string | null;
  free_teasers_remaining: number; can_create_memo: boolean; can_unlock_memo: boolean; is_admin: boolean;
}
```

## Analytics events (PostHog, fired by the web app)

`plan_started`, `plan_completed`, `signup`, `paywall_hit`, `upgrade` (+ `preview_started`,
`preview_completed`, `clarification_shown`, `step_toggled`, `pdf_exported`, `lead_captured`).
