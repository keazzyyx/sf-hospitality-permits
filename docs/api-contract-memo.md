# Permit Memo API contract — Location Risk Memo (v1, report format 3)

Extends `docs/api-contract.md` (same auth, error shape, SSE framing). Base URL `NEXT_PUBLIC_API_URL`.

**Report format 3 (2026-11-12): the rules and the evidence only.** No sentence in the report, the teaser, the
PDF or the web page is written by a model. The only model call left is the intake: it reads the description
into facts, and the stated-facts check keeps only what the text states. Each row shows its status, the rule
lines (with code section and source link), the facts the rules read (each with where it came from: the
applicant's words with the quote, an intake answer, or a record), what is not known, the referral steps and the
source links. The comparables are the top of a fixed ranking, each with what its record says. The outcome counts
list each decision they count. Clarifying questions a model wrote are not asked: what is missing is named by
the rules ("Not known: X. Needed for: Y."). `Memo.format_version` is `3`; every memo stored before it is served
as a legacy memo (see "Legacy memos"). New fields: `Memo.description`, `Memo.facts`, `Memo.comparables_note`,
`Memo.entitlement_path`, `MemoApprovalRow.facts`, `BaseRate.counted`, and `use_types`, `hours_close`,
`conditions` on `SiteHistoryEntry`. See "The evidence". Routes, pricing, credits and auth are unchanged.

The model writer of format 2 (the records, precedent, risk and verify stages, and every field they filled) is
removed from the code. It is kept on the branch `writer` for comparison. The notes on format 2 below are
history. A memo the `writer` branch stores with the writer off has the same keys as this report (its
empty writer fields are left out) and is read as it is; one the writer filled is served as legacy.

**Report format 2 (2026-11).** The single Likely / Conditional / Unlikely verdict is gone. A memo now has one
row per approval the concept needs, each with a status from a fixed list; every finding carries an evidence
label; there is one overall line and one recommended next step, a "could not establish" section, comparables
shown as evidence with their source, and a second pass that checks each cited sentence against its record.
There is no narrative. `Memo.format_version` is `2`. Memos stored before this change have no `format_version`:
they are served with `legacy_format: true` and `memo: null`, `teaser: null` (see "Legacy memos").

**Statuses set by rule (2026-11-10).** The pathway (permitted, conditional use or not permitted, and whether it
is a change of use), every row's status, approval and agency, the overall status and line and the entitlement
path are set by rules in code from the records found. The writer model explains them and cannot change them;
the citation check reads the writer's sentences only. See "Pathway and statuses: set by rule". New fields:
`Memo.pathway`, `MemoApprovalRow.basis`, `VerificationSummary.trimmed`, and `"trimmed"` as a `Verification`
value. Removed: `MemoApprovalRow.original_status` and `VerificationSummary.rows_reset`.

**Rule table v2 (2026-11-11).** The rules now evaluate eleven triggers (each reason the Planning Code can
require a hearing) for a rules date, answer change of use as three separate questions, and keep referral steps
apart from approvals. A row may carry a status note, referral steps and the inputs the rules name as not
given; a missing input is never filled with an assumption. Days read from the records are printed per outcome,
never as one figure. New fields, all optional so a memo stored before this change still validates:
`Pathway.rules_date`, `Pathway.triggers`, `Pathway.changes`, `MemoApprovalRow.status_note`,
`MemoApprovalRow.referral_steps`, `MemoApprovalRow.missing_inputs`, `Memo.records_limits`; `"nighttime_entertainment"`
as a `PlanningUse` value; `"cancelled"` as a value of `ComparableCase.outcome`. No route changes. See "Pathway
and statuses: set by rule" and "Days from filing, by outcome".

## Routes

| method | path | body | returns |
|---|---|---|---|
| GET | `/v1/geocode?q=<text>&limit=8` | – | `{suggestions: GeocodeSuggestion[]}` (no auth; 60/min/IP). SF only for now. |
| POST | `/v1/memos` | `{address, description, lat?, lng?, profile_overrides?, intake?: IntakeAnswers, rerun_of?: uuid}` | SSE → `memo` (see events); `422` when an intake answer is outside its allowed values, `rerun_of` is not a UUID, or `profile_overrides` is sent with `rerun_of`; with `rerun_of`: `404 not_found` for a memo that is not the user's, `409 rerun_not_legacy` for a memo in the current format (see "Legacy memos") |
| POST | `/v1/memos/{id}/clarify` | `{answers}` | SSE → `memo`; the intake answers stored with the memo are applied again |
| POST | `/v1/memos/{id}/answers` | `IntakeAnswers` (the answers only, at the top level) | SSE → `answers_round`, then `memo` (the same memo, updated) or `error`; free, no model call, at most 5 rounds a memo (see "Answer rounds"). `422` for any other key (`address`, `description`, `profile_overrides`, `rerun_of`, `intake`, ...), an answer outside its values, two answers that contradict each other, a count of other locations with no `part_of_chain: true` sent or stored, a kind of food or drink service over stored answers that say alcohol is served with no `liquor_licence: "none"` sent, no answer (`validation_error`) or the answers the memo already has (`no_new_answers`); `404 not_found` for another user's memo; `409 legacy_format`, `not_ready`, `answers_running`, `answers_unavailable`, `answers_round_limit`; `429 rate_limited` |
| GET | `/v1/memos/{id}/revisions` | – | `{revisions: MemoRevision[]}`, oldest first: the versions answer rounds replaced (owner only; `404` otherwise) |
| GET | `/v1/memos` | – | `{memos: MemoSummary[]}` newest first |
| GET | `/v1/memos/{id}` | – | `{memo: MemoRecord}` — `memo.memo` is `null` and `memo.teaser` is set unless `access == "full"`; both are `null` when `legacy_format` is true; `rerun_free` and `rerun_of` are set here only |
| POST | `/v1/memos/{id}/unlock` | – | `{memo: MemoRecord}` with `access: "full"`; consumes a memo credit or requires Pro; `402 paywall_memo` otherwise; `409 legacy_format` for a locked legacy memo (no credit is spent); `409 not_ready` for a memo still being made (a memo in an answer round, running or stopped, holds its earlier report and can be unlocked) |
| GET | `/v1/memos/{id}/export.pdf` | – | `application/pdf` (full access only, else 402; `409 legacy_format` for a legacy memo) |
| GET | `/v1/memos/{id}/map.geojson` | – | GeoJSON FeatureCollection: subject point (`properties.overall_status`) + comparable cases + overlays (full access only, else 402; `409 legacy_format` for a legacy memo) |
| POST | `/v1/memos/bulk` | multipart `file` (CSV with header `address,description`) | `{batch_id, memo_ids, skipped: [{row, reason}]}` — Pro only (`403 pro_required`), max 25 rows |
| GET | `/v1/memos/bulk/{batch_id}` | – | `{batch_id, memos: MemoSummary[]}` |
| DELETE | `/v1/memos/{id}` | – | 204 |
| GET | `/v1/feedback/{token}` | – | `{memo_id, address, concept_type, already_answered: bool}` (no auth; signed token from the 90-day email) |
| POST | `/v1/feedback/{token}` | `{outcome, notes?}` | `201 {ok: true}` |
| GET | `/v1/admin/overview` | – | `AdminOverview` — only for emails in `ADMIN_EMAILS` (`403 forbidden`) |
| POST | `/v1/billing/checkout` | `{mode: "plan"\|"subscription"\|"memo"\|"pro", success_url, cancel_url}` | `{url}` (modes `memo` = $499 one-time, `pro` = $299/month) |

`GET /v1/me` → `Me` now also includes `memo_credits`, `pro_status`, `free_teasers_remaining`, `can_create_memo`.

Entitlements: a memo is always generated in full server-side and stored; the response is a **teaser**
(overall status, the overall line, which names each row's status, and counts; everything else withheld) until
the user unlocks it. Free accounts may generate
`FREE_TEASER_LIMIT` (2) teaser memos; after that `POST /v1/memos` returns `402 {"code":"paywall_memo"}` until
they buy a credit or Pro. Unlock: Pro (`pro_status ∈ {active, trialing}`) → unlimited; else consumes one
`memo_credit`. Bulk upload requires Pro. One exception: the first re-run of a legacy memo the user unlocked is
free (see "Legacy memos").

### The optional intake questions

The page where a report is started asks optional questions under the description, and sends the answers as
`intake` (`app.memo.intake`; every key optional, a missing or `null` key is a skipped question). Each question
gives one fact the rules read. Since 2026-11-15 there is a question for almost every input a row or a trigger can name
as not given (the licence type, the licences held, the Planning uses and the seat count have none; see below), so a report that leaves a row "Insufficient information" for want of such an input can be run again
with the answer (before that date only the first four keys existed, and the report of that day for 2301 Chestnut
St left four of its five rows undecided with no way to give the missing facts but to rewrite the description).
The questions are in two groups: the **main** ones are always shown; the ones under **More details** are asked
for by only some reports.

| Key | Question (as the page asks it) | Allowed answers |
|---|---|---|
| `part_of_chain` | Is the business part of a chain that shares its name, look or menu with other locations? | `true`, `false` |
| `other_locations` | How many other locations does the chain have, open or approved, anywhere in the world? (asked only when `part_of_chain` is `true`) | integer 0 to 100,000; refused unless `part_of_chain` is `true` |
| `floor_area_sqft` | What is the floor area of the business, in square feet? | integer 1 to 1,000,000 |
| `liquor_licence` | How will the liquor licence be obtained? | `"new"`, `"transfer_from_another_owner"`, `"transfer_from_another_location"`, `"already_held"` (shown as "Already hold a licence at this address"), `"none"` (shown as "No alcohol") |
| `stories` | Which stories does the business occupy? | a list of one or more of `"basement"`, `"first"`, `"second"`, `"third_or_above"`, each once (stored in the order first, second, third or above, basement) |
| `alcohol_served` | What alcohol will be served: beer and wine, or spirits too? (not asked after "No alcohol") | `"beer_wine"`, `"full_liquor"`; refused with `liquor_licence: "none"` |
| `closing_time` | What is the closing time? | `"HH:MM"`, 24-hour (`"02:00"` is 2 a.m.) |
| `last_use` | What was the space last used as? | `"restaurant"`, `"bar"`, `"limited_restaurant"`, `"nighttime_entertainment"`, `"retail"`, `"laundromat"`, `"other"` (not `"vacant"`: an empty space is asked what it was last used as) |
| `fewer_than_50_people` | Is the space for fewer than 50 people? | `true`, `false` |
| `outdoor_area` | Where is the outdoor area? | `"none"` (shown as "No outdoor area"), `"front"`, `"rear_or_side"`, `"rooftop"`, `"parking_lot"`, `"sidewalk"` |
| `outdoor_alcohol_service` | Will alcohol be served in the outdoor area? (asked only when there is an outdoor area) | `true`, `false`; refused with `outdoor_area: "none"`, and `true` is refused with `liquor_licence: "none"` |
| `food_service` | What kind of food or drink service is it? (from 2026-11-16; shown under the liquor licence question once "No alcohol" is answered, or when the report asks for it because the description says the bar serves no alcohol; never once an answer says alcohol is served) | `"restaurant"` (shown as "A Restaurant (cooked food served on the premises, with seating)"), `"limited_restaurant"` ("A Limited Restaurant (ready-to-eat food or drinks, with or without seating)"), `"other"` ("Other, or not sure"); refused with an answer that says alcohol is served (`liquor_licence` other than `"none"`, `alcohol_served`, `outdoor_alcohol_service: true`) |
| `existing_business_change` (More details) | Is an existing business to be enlarged or intensified? | `"none"`, `"enlarge"`, `"intensify"`, `"enlarge_and_intensify"`. Any answer, `"none"` included, tells the rules that a business of the same kind is already at the address and stays or is taken over, so it is answered only then |
| `floor_area_before_sqft` (More details) | What was the floor area before the project, in square feet? | integer 1 to 1,000,000 |
| `merges_storefronts` (More details) | Are storefronts to be merged? | `true`, `false` |
| `amends_prior_approval` (More details) | Are the conditions of an earlier approval to be changed? | `true`, `false` |
| `entertainment` (More details) | Is there entertainment, and what kind? | `"none"`, `"limited_live_performance"`, `"place_of_entertainment"` |
| `existing_occupancy_group` (More details) | What occupancy group do the plans or the certificate of occupancy of the existing space show? | `"B"`, `"A-2"` |

Two answers that contradict each other are refused with `422`, so neither is silently dropped. Three inputs have
no question: the kind of business (the description itself), the seat count (it decides nothing the "fewer than 50
people" question does not) and the licences already held (read only for an existing business in a district that
restricts licences, where the liquor licence question answers it). The kind of food or drink service, named in
place of the kind of business for a bar that serves no alcohol, has its own question since the owner decision of
2026-11-16 ("a business that serves no alcohol is not a Bar use (Planning Code § 102). No alcohol row, and ask
what kind of food or drink service it is; don't assume"); before it the report named the input and no question
gave it. The help under the question quotes the two Planning Code § 102 definitions: a Restaurant "serves prepared,
ready-to-eat cooked foods to customers for consumption on the premises" and has seating (take-away only as a minor
and incidental use); a Limited Restaurant "serves ready-to-eat foods and/or drinks to customers for consumption on
or off the premises", with or without seating (a sandwich shop, coffee house, pizzeria or ice cream shop). Neither
is offered as the likely one.

The answers are applied by code (`apply_intake_answers`), after the intake model has built the profile from
the description and before the rules read it. An answer always wins over the description; a skipped one
changes nothing, so a fact neither gives stays missing and the rules name it in the question's own words.

| Answer | Profile |
|---|---|
| `part_of_chain: false` | `formula_retail: false` |
| `part_of_chain: true`, `other_locations` ≥ 11 | `formula_retail: true` (Planning Code § 303.1(b): eleven or more other establishments, in operation or approved, anywhere in the world) |
| `part_of_chain: true`, `other_locations` < 11 | `formula_retail: false` (trigger T5 says the chain is below the count) |
| `part_of_chain: true`, count skipped | `formula_retail: null`: T5 is not decided and names "how many other locations the chain has, open or approved, anywhere in the world" |
| `floor_area_sqft` | `square_feet` |
| `liquor_licence: "new"` / `"transfer_from_another_owner"` / `"transfer_from_another_location"` / `"already_held"` | `alcohol_transaction: "new_licence"` / `"person_to_person_transfer"` / `"premises_transfer"` / `"licence_already_held"`, and `serves_alcohol: true` (`alcohol_type` stays as the description gave it: `"unknown"` when it does not say what is served) |
| `liquor_licence: "none"` ("No alcohol") | `serves_alcohol: false`, `alcohol_type: "none"`, and the licence type and transaction the description gave are cleared, whatever the description said: the answer wins. Where the description mentioned alcohol, the pathway's first line (rule id `intake.no_alcohol`) says so |
| `stories` | `stories`, in the fixed order |
| `alcohol_served` | `serves_alcohol: true`, `alcohol_type` as answered; the rules then derive the licence type (a Restaurant: Type 41 or 47; a Bar: Type 42 or 48), and a licence type the intake model read and the stated-facts check cleared is then not named as not known |
| `closing_time` | `closing_hour`, and `closes_after_midnight` / `closes_after_2am` from the same time (after midnight up to 6 a.m. is a late close) |
| `last_use` | `existing_use_stated: [that use]` |
| `fewer_than_50_people` | `occupants_under_50` (the intake model never sets it: seats are not the occupant load). `true` with a seat count of 50 or more in the description is a conflict: the building row reads neither over the other, the proposed occupancy group is not established, and the row names whether the space is for fewer than 50 people |
| `outdoor_area: "none"` | `outdoor_area: "none"`, `outdoor_seating: false`, `sidewalk_or_parklet: false`, `outdoor_alcohol_service: false`: the answer wins over a description that mentioned an outdoor area or alcohol in one, and the report has no outdoor row and no question about alcohol outdoors |
| `outdoor_area`, a place | `outdoor_area` as answered, `outdoor_seating: true`, `sidewalk_or_parklet: true` for `"sidewalk"` only |
| `outdoor_alcohol_service` | `outdoor_alcohol_service`; `true` also sets `serves_alcohol: true`, so the alcohol row is read. Where it is the only alcohol answer and the description did not say alcohol is served (or said none is), the answer is read (the safe reading: the licence is checked) and the alcohol row's first line (rule id `alcohol.outdoor_answer`) says the two disagree |
| `existing_business_change` | `changes_existing_business` |
| `floor_area_before_sqft`, `merges_storefronts`, `amends_prior_approval` | the profile fields of the same names |
| `entertainment: "none"` | `entertainment_kind: "none"`, and `live_entertainment`, `amplified_sound` and `dancing` false: the answer wins over the description |
| `entertainment`, a kind | `entertainment_kind` as answered |
| `existing_occupancy_group` | `existing_occupancy_group` (a profile field only this answer sets; no public record shows the group). The building row compares it with the proposed group: the same group is no change of occupancy, a different one is a change, and the row no longer waits for plans |
| `food_service` | `food_service` (a profile field only this answer sets; the intake model never does). Read only for a business described as a bar that serves no alcohol, by the "No alcohol" answer or the description's own words (pathway rule 1b): `"restaurant"` and `"limited_restaurant"` are then the concept's use (`pathway.use`), the rules run for that use, and there is still no alcohol row. The pathway's and the zoning row's first line (rule id `zoning.food_service`) says "... so it is not a Bar: Planning Code § 102 defines a Bar by its on-site alcoholic beverage sales. You answered that it is a Limited Restaurant, and the rules read that use.", and the fact list shows the kind of business as the applicant's answer. `"other"` gives no use: the input stays not known and named, T1 is not decided, and its line says "You answered that it is another kind of food or drink service, or that you are not sure". For any other business the kind of business the description gives decides the use, and a line (rule id `zoning.food_service`, "To the question on the kind of food or drink service, you answered that it is a Limited Restaurant. That question is read only for a business described as a bar that serves no alcohol ...") says the answer was not read |

**Where a line's fact came from.** `apply_intake_answers` records the profile fields the answers set
(`BusinessProfile.intake_answered`, set only by code; the intake model's tool schema does not show it). A rule line
whose fact an answer gave says so: "You answered that the space is for fewer than 50 people ...", "... with the
last use of the space as you answered", "The same use continues and you answered that the business stays as it
is ...", "You answered the kind of entertainment ...". A fact the description gave keeps "The description says
...". The fact list already shows each fact's origin (`MemoFact.origin`).

**Which question to answer.** Every open question of a report (`Memo.could_not_establish`) that an intake
question answers carries that question's id in `intake_question` (`app.memo.pathway.intake_question_for`). An
input no answer settles carries none: "the licence type" is named only where what is poured would not decide it
(a hotel, a caterer, or what is poured already given), and where it would, the report names "what alcohol will be
served" and points at that question; a licence type the stated-facts check cleared is named the same way. The kind
of food or drink service of a bar that serves no alcohol points at `food_service` (from 2026-11-16), also after the
answer "Other, or not sure", so the applicant can answer it once they know. The
page shows the question under it ("You can answer it"), and one link, "Answer and run again", opens the form with
the same address, description and answers, the questions the report asked for marked, and waits for the answers
(`/app/memo?...&answer=1&ask=<ids>`; any other link with an address and a concept starts the report at once). The
PDF prints "Question to answer: “…”" after each such question. Answering is a new report: the rules run again on
the new answers. Answering can open a further question (in a space that was a shop, 6,000 square feet makes the
size rules ask for the floor area before the project and whether storefronts are merged); the next report names
it the same way. A test (`tests/test_all_rows_decided.py`) checks, for six concepts built straight from the
profile, that answering what is asked ends with no question left that the applicant could answer; others run a
description through the stated-facts check in the runner's order and check that a cleared licence type and a
cleared reading of alcohol outdoors are settled by the answers. That is not every description: an answer that
conflicts with the description (fewer than 50 people with 50 seats or more) leaves its question open until the
two agree.

A licence already held at the address is never read from the description: only the `"already_held"` answer
sets it.

### Answer rounds: the questions answered on the same memo (2026-11-16)

Owner decision of 2026-11-16. The report's "Answer and run again" runs **the same memo** again with more intake
answers, free, up to five times a memo (`ANSWER_ROUND_LIMIT`, `app.memo.answers`). Before it, the link opened the
new-memo form and made a new memo, so a normal account spent a free preview or a credit to give an answer the report
asked for. Changing the description is still a new memo, charged like any new one (the Re-run link).

- **The body is the answers only**: `IntakeAnswers` at the top level, the same keys and values as `intake` on
  `POST /v1/memos`. The address and the description are fixed: any other key is refused (`422`). Two answers in the
  request that contradict each other are refused (`422`), as on a new memo. A follow-up may come on its own when the
  answer it follows is stored with the memo (`RoundAnswers`): `{"other_locations": 7}` on a memo whose answers say
  `part_of_chain: true` is a new count. With no `part_of_chain: true`, sent or stored, the count is `422
  validation_error` with `ANSWERS_FOLLOW_UP_MESSAGE`; the chain is never inferred from the count. A body with no
  answer is `422 validation_error`; answers that, merged, are the ones the memo already has are `422
  no_new_answers`.
- **Merging.** The answers sent win; a question the request does not answer keeps the answer stored with the memo,
  so a round changes answers and never takes one back. A stored answer that cannot stand with a new one is dropped,
  so the new one wins (`merge_answers`): a stored count of other locations by a new "not a chain", what is poured by a
  new "No alcohol", alcohol outdoors by a new "No alcohol" (when yes) or "No outdoor area", a stored "No alcohol" by a
  new answer for what is poured or alcohol outdoors (yes), a stored "No outdoor area" by a new answer for alcohol
  outdoors; a stored kind of food or drink service by a new answer that says alcohol is served (from 2026-11-16). The
  usage event lists the dropped ones as `replaced`. A new kind of food or drink service is refused (`422
  validation_error`, `ANSWERS_FOOD_SERVICE_MESSAGE`) where the stored answers the round keeps say alcohol is served
  (a licence other than "No alcohol", what is poured, alcohol outdoors yes): the question is asked only for a
  business that serves no alcohol, and the rules read the answer only for a bar that serves none, so it never drops
  answers the rules read. Sent with `liquor_licence: "none"` it is accepted, and the "No alcohol" answer drops what
  is poured as above.
- **An answer against the description** is read exactly as on a new memo: the answer wins, and where the rules read
  the two as disagreeing they say so (fewer than 50 people against 50 seats or more: the building row says the two
  disagree and the proposed occupancy group is not established).
- **No model call, no second check.** When a memo is made, what the intake left before the answers is kept with it
  (`memos.intake_basis`, `IntakeBasis`): the profile after the stated-facts check with the clarification answers and
  overrides applied, what the check cleared, the applicant's words each fact came from, the fields given after the
  check, the model that read the description, and the address record the run read. A round puts the merged answers
  on that by the same function a new memo uses (`apply_basis`) and then reads the records and the rules exactly as a
  run does after its intake, at the same point and parcel (the address is not geocoded again). The
  report is the one a new memo with the same description and the merged answers gets from the same intake reading
  (tested), with the records, and the rules, as they are on the day of the round, headline findings included (a
  T7 "If the existing business is enlarged ..." finding at 2301 Chestnut St becomes definite after
  `existing_business_change: "enlarge"` and goes after `"none"`; tested through the route). `Memo.model_versions` names the model that read the
  description when the memo was made. A memo made before the basis was kept is `409 answers_unavailable`: answering
  it is a new memo, as before (the page says so).
- **Who and which memo.** Only the owner (`404 not_found` otherwise); a ready memo in the current format (`409
  legacy_format` for a legacy memo, `409 not_ready` for one still being made or waiting for a clarification answer,
  `409 answers_running` while a round runs); a sixth round is `409 answers_round_limit` with `answers_round_limit: 5`.
  Rate limited per account (`MEMO_ANSWERS_RATE_LIMIT_PER_HOUR`, 20; `429 rate_limited`).
- **Nothing is charged and no access is gained.** The memo keeps its id and its `access`: a teaser stays a teaser
  (the stream's `memo` event and every route withhold the full report as before), an unlocked memo stays unlocked,
  `unlocked_at` is unchanged, no free preview is counted and no credit is used, whatever the account's previews or
  credits. A round running holds no free preview on the create paywall. A free re-run's memo in a round was ready,
  so neither deleting it nor a round left stalled gives the legacy memo's free re-run back.
- **While it runs** the memo is `generating` (`answers_running: true`) and still holds the report from before the
  round, which `GET /v1/memos/{id}` serves as before. A round that ends with an error, or whose run raises, leaves
  the memo as it was: `ready`, the same report and answers, the round not counted, `error` =
  `ANSWERS_FAILED_MESSAGE`. A round still `generating` 15 minutes after it started (`GENERATING_TIMEOUT`, an API
  restart) reads as `ready` with `error` = `ANSWERS_STOPPED_MESSAGE`, the report from before it, and can be started
  again; the stalled round, if it ever finishes, saves nothing and is not counted, as the page said: when a later
  round took the memo over, its claim (`memos.answers_run`) has changed; when none did, the save sees the round has
  stalled and ends the row as `ready` with `ANSWERS_STOPPED_MESSAGE` instead. A round saves or ends the row only while
  its own claim is the row's, so a round left behind never overwrites or ends the one running now. A memo whose run
  as a new memo stalls reads `failed`, as before.
- **Unlocking during a round.** A memo in a round, running or stopped, still holds the report from before it, and a
  round never changes `access` or `unlocked_at`, so `POST /v1/memos/{id}/unlock` unlocks it as it does a ready memo
  (one credit, or Pro); the round's report, when it is saved, keeps that access. Only a memo still being made as a
  new memo is `409 not_ready`.
- **History.** Before a round's report replaces the memo's, the version it replaces is written to
  `memo_revisions` (round, intake, profile, memo, teaser, created_at; RLS: the owner can read, the service role
  writes). `GET /v1/memos/{id}/revisions` lists them oldest first as `MemoRevision`; `round` is the round that
  replaced it (the version replaced by round 1 is the report the memo was made with). A revision shows the full
  report only while the memo is unlocked, its teaser otherwise. Deleting the memo deletes them.
- **Usage event** `memo_answers_rerun` when a round starts: `{memo_id, round, answered, replaced, access}`.

### Only what the text states (the stated-facts check)

The intake model may only record facts the text states (decision of 2026-11-12). The rule is enforced in code
(`app.memo.stated`), not only asked for in the prompt:

1. `MemoIntakeResult.quotes` is a list of `{field, quote}`. For every field the memo's rules read
   (`app.models.profile.QUOTED_FIELDS`: the business type, whether and what alcohol is served, the licence type
   and the licences held, the floor area before and after, the seats, the existing use, whether an existing
   business is enlarged or intensified, the storefront merger, an earlier approval, the stories, the closing time
   and the two "closes after" flags, entertainment and its kind, live music, amplified sound, dancing, the outdoor
   area, outdoor seating, the sidewalk, alcohol outdoors, the change of use and new construction), the model
   gives the exact words of the description that state the value. Words from a clarification answer typed in
   words count too.
2. Code keeps a value only when one of its quotes is found in the text (both lower-cased, accents and
   punctuation dropped, spaces collapsed, "3,953" read as "3953") and the quoted words can state that value.
   **A spelling mistake does not lose a fact** (`app.memo.spelling`, change of 2026-11-15, approved with the release of 2026-11-16; the rules as fixed by the review of that day). A word of five or more letters, written all in lower
   case, that is one slip (a letter dropped, added or changed, or two neighbours swapped) from exactly one word of
   the tables is read as that word: "alochol license" states alcohol, "outside ppatio" an outdoor area. A real word
   is never changed (`app/memo/data/spelling_real_words.json`, built from every word list on the Mac, the macOS
   spell checker and a list of modern words and names: "mocktails" is not "cocktails", "newer" is not "never"),
   nor is a word one slip from two different table words, nor a word the text writes anywhere with a capital or an
   accent (a name: "Patino Family Kitchen"). No word is respelt into a negation; a word that respells into a hedge
   ("Mabye") is read as the hedge in any case. And a quote the model wrote with the spelling put right ("outside
   patio") still counts when each of its words is one slip at most from the word of the text it points at
   (numbers and words under four letters must be equal: "40" is never "400"); the value is then read from the
   applicant's own words, cut from the text, never from the model's. The report shows the applicant's words as
   written.
   Mapping stated words to a value is allowed ("ground-floor" is the first story; "wine bar" is a bar that pours
   beer and wine). A number must be in the quote with its unit: "square feet" for a floor area; for seats, a
   number next to a word for seated places ("40 seats", "seating for 40", "40 people sitting", "40 guests
   seated"), never people with no word for sitting ("room for 40 guests"), covers, staff, a limit ("fewer than
   50"), or a number its clause makes a rate, a time, a count per table or a clock time ("we seat 300 people a
   day", "first seating 5:30 pm"). A closing time
   must be a time the quote gives after a closing word ("until 2 a.m.", "7am-2am"), not an opening time. A "no"
   needs a negation next to its own subject ("no live music"; a "not part of a chain" says nothing about music).
   A quote that hedges ("maybe live music") states no yes/no fact, hours or outdoor area. A quote with "..." is
   read part by part: the words of a value must sit inside one part. The words for each value are in the
   tables of `app.memo.stated`.
3. Anything else goes back to "not stated" (null, an empty list, `false`, `"other"` for the business type). From
   a list only the values no quote states are removed: "two ground-floor units ... with a mezzanine" gives
   `stories: ["first"]`, because a mezzanine is not a story.
4. `BusinessProfile.intake_cleared` records each field cleared, in whole or in part, with the value removed
   (`{"seats": 120, "stories": ["second"]}`). An intake answer, a clarification answer or an operator override
   that later gives the field takes it off the record, whatever the value: a "No alcohol" answer gives whether
   alcohol is served even though it leaves the same `false` the check left. The model cannot set this field (hidden from its tool
   schema, and in `MODEL_MAY_NOT_SET`).
5. The report names every cleared fact whose value the text does not give some other way, in the fixed phrase
   of `MISSING_PHRASES`: a row or trigger that needs it is insufficient information and lists it in
   `missing_inputs`; every other one is asked in `could_not_establish` as "Not known: <phrase>. The description
   does not state it, so the report does not assume it." (pathway rule 7a).
6. A cleared "yes" is not read as "no". When the model read that alcohol is served, that there is entertainment,
   that there is an outdoor area, or which story the business is on, and the text does not state it, the fact is
   not known (`ConceptFacts.cleared_readings`). The alcohol, entertainment or outdoor row is added and is
   insufficient information, naming "what alcohol will be served: beer and wine, or spirits too", "whether there
   is entertainment, and what kind" or "where the outdoor area is". The zoning triggers that read it are not
   decided (T4, T6). A story the text does not state is a missing story, as below. A removed "no" (`"none"`,
   `false`) is the same as a fact never mentioned: it adds no row and is asked under rule 7a.
7. No model reads the profile after the intake. The report shows each fact the rules read with where it came
   from (`Memo.facts`); a removed value is shown as not known, never as the model's guess.

The facts only the applicant gives (`MODEL_MAY_NOT_SET`: the chain, the count, how the licence is obtained, the
occupant count) are still cleared from the model's profile before any of this. The memo's intake has its own
prompt (`prompts.MEMO_INTAKE`: the checklist's, with the lines that fill a likely value replaced and the quotes
rule added) and its own submit tool (`MemoIntakeResult`). The checklist (`/v1/plans`) keeps its intake prompt
and tool unchanged and does not run the check.

**What is served.** `BusinessProfile.alcohol_type` is `"beer_wine"` or `"full_liquor"` only when the description
says what is served ("wine bar", "beer and wine"; "cocktails", "full bar", "spirits"), `"none"` when no alcohol is
served, and `"unknown"` when the concept serves alcohol without saying what ("a bar", "with drinks"). It is never
filled with a guess: with `"unknown"` and no stated licence type no licence type is derived, the alcohol row is
insufficient information and names "what alcohol will be served: beer and wine, or spirits too" (in place of "the
licence type"), and every licence rule that turns on the type is not decided and names the same phrase. A stated
licence type still decides it.

**A missing story.** The zoning tables set the use controls story by story. When the story the business is on is
not given (not by the description, an intake answer or the records, or the model read one the text does not
state), no story is assumed (the user's decision of 2026-11-12: "MISSING STORY: always 'Insufficient information',
naming it. Never default to the first story."). Every rule whose answer depends on the story is not decided and
names "which stories the business occupies": the district's cells for T1, T3 and T6 when the table does not read
the same on every story (the line says "the table sets a different control for <the use> on different stories.
Which story the business is on is not given, so no story is assumed and this is not decided until it is"); a
special district rule for the First Story only, read for the First Story (on any other story it does not apply),
when that reading asks for something or is itself not decided (T2, T4; it then names the other missing input as
well); and the control of a district the dated rule table does not carry, because the zoning control table on file
gives first-story controls only, unless the district's own table has no story columns (Tables 209.1, 209.2, 209.3,
210.1, 210.2 and 827, as the dated data records: one control on every story) and no overlay adds its own control.
A First Story rule that asks for nothing on the First Story (a licence type it does not reach, a rule repealed on
the date) stands as it reads, and the story is not named for it. The zoning row is then
insufficient information naming the story, even where the first story would need a Conditional Use or another
trigger asks for one; only a trigger that is not permitted outranks it. The control on a new use is `not_covered`
("Not decided by the rules"), and a row whose status turns on such a rule (the alcohol row, through a district's
licence rule for the First Story) is insufficient information naming the story too. No line says the first story
was read. Where the table reads the same on every story (the first, second and third-and-above columns give the
same control and leave the same inputs open: for example a Bar not permitted on any story of NCD-PACIFIC) the story
does not change the answer: every column is printed and one line says "Which story the business is on is not given.
The table reads the same for <the use> on every story, so the story does not change this." A stated story
("ground-floor" is the first story) is read as before. Only a numbered story states a story above the first:
"upstairs", "an upper floor" or "top floor" do not say which, so they leave the story missing.

`BusinessProfile.part_of_chain` keeps the chain answer (the intake model's tool schema does not show it), so the
rules can tell a chain whose count was skipped from a skipped chain question. The answers are stored with the
memo (`memos.intake`, migration `20261111000000_memo_intake.sql`, written only when one was answered) and
returned as `MemoRecord.intake` (every question's key, a skipped one `null`; the field is `null` when none was
answered). A clarification run applies them again; the page's re-run link carries them. Bulk upload asks none.
Reading a stored row (`MemoService.intake_of`) keeps every answer this version knows: a key it does not know (one
a later version wrote, read after a rollback) is dropped, and so is a known key whose value no longer validates;
only answers that contradict each other leave none.
The local script `scripts/validation/run_report_local.py` takes the same answers as `--intake <file or JSON>`.

### Legacy memos

A stored memo whose JSON is not `format_version: 3` is never parsed and never raises; a format-2 memo (written by
the model writer) is served exactly as a format-1 memo is. `GET /v1/memos/{id}` and
`GET /v1/memos` return it with `legacy_format: true`; `memo` and `teaser` are `null`, and in the summary
`overall_status` and `comparable_count` are `null`. `export.pdf` and `map.geojson` answer
`409 {"code": "legacy_format"}` (after the usual 402 if the memo is still locked), and so does `unlock` on a
locked legacy memo, before any credit is consumed. The fix for the user is to run the address again. A legacy
memo the user unlocked keeps `access: "full"`, but its report is withheld too.

**Re-running a legacy memo (`rerun_of`).** The page's Re-run button on a legacy memo sends
`POST /v1/memos` with `rerun_of` set to that memo's id (the web sends it only while the form still holds the
memo's own address and description).

- `rerun_of` must be one of the user's own memos (another user's id, or an unknown one, is `404 not_found`, and
  nothing is created) and must be legacy, by the same test the routes above use (a memo in the current format is
  `409 rerun_not_legacy`, and nothing is created: its report is shown, so a new memo with a new description is a
  plain create without `rerun_of`).
- A re-run is the same concept. The new memo uses the legacy memo's stored address, coordinates and description.
  The `address`, `lat`, `lng` and `description` sent with `rerun_of` are ignored (they are still required by the
  schema). A non-empty `profile_overrides` with `rerun_of` is refused (`422 validation_error`, nothing created).
  `intake` is accepted and used: the intake questions refine the same description, and a legacy memo never asked
  them. Without it, the legacy memo's stored intake answers are used.
- **Free once, for a memo the user unlocked.** When the legacy memo has `access: "full"` and its free re-run is
  unused, the new memo skips the create paywall (it runs with no previews and no credit left), is saved with
  `access: "full"` and `unlocked_at`, uses no memo credit and does not count a free teaser.
- **How it is recorded (no migration).** Attempt `k` (0, 1, ...) at the free re-run of legacy memo `L` creates its
  memo with the id `uuid5(FREE_RERUN_NAMESPACE, "L:k")` (`app.services.memos`). That primary key is the claim:
  two requests that find attempt `k` open at the same moment insert the same id, the database accepts one, and
  the other request is charged like any new memo (no second free memo). Right after the insert, a `usage_events`
  row `event = "memo_rerun_free"`, `properties = {legacy_memo_id, memo_id, attempt}` records it; saving the new
  memo reads that row. If the row cannot be written, the new memo row is removed and the request fails.
- **When the free re-run is given back.** An attempt gives it back when its new memo is `failed` (a failed memo is
  never charged; a run still `generating` 15 minutes after it last changed counts as failed, see "Stalled runs"
  below), was deleted before it was `ready` (the row gets `properties.released_at`), or is still
  `pending_clarification` 30 minutes after it last changed (`FREE_RERUN_RELEASE_AFTER`: the clarification
  question was left unanswered). An attempt that is `ready`, still running, or deleted once ready keeps it used. If an abandoned
  attempt finishes after a later attempt was made, only the latest attempt is free; the earlier one is saved as a
  teaser and counted like any new memo.
- **Runs outlive their stream (2026-11-13).** `POST /v1/memos` and `POST /v1/memos/{id}/clarify` start the run in
  its own server task (`_detached` in `app/routes/memos.py`); the SSE stream only listens to it. A page closed or
  left mid-run no longer stops the run: the memo is saved (and charged) exactly as if the page had stayed, and the
  page that comes back reads it with `GET /v1/memos/{id}`. A run that raises is marked `failed` unless its memo was
  already saved (`MemoService.mark_failed_if_running`).
- **Stalled runs (2026-11-13).** An API restart still ends a run in progress, and its row stays `generating`. Every read
  (`GET /v1/memos/{id}`, `GET /v1/memos`, `GET /v1/memos/bulk/{batch_id}`, the free re-run rules) reports a row
  still `generating` `GENERATING_TIMEOUT` (15 minutes) after it last changed as `failed`, with `error` =
  `STALLED_MESSAGE`; the stored row is not rewritten. Nothing is charged for it: a free preview is counted only when
  a memo is ready, a credit only on unlock. A bulk upload refreshes the rows of its batch still waiting before it
  starts each memo (`MemoService.touch_batch`), so a queued row is not reported as stalled.
- `GET /v1/memos/{id}` on a free re-run's memo sets `MemoRecord.rerun_of` to the legacy memo's id. The page's
  Re-run link on such a memo that is not `ready` (failed or abandoned) sends that id as `rerun_of`, so the retry
  is free while the free re-run is given back.
- **After that**, a re-run of the same legacy memo is charged like any new memo: a free preview, or the `402
  paywall_memo` with none left, then an unlock with a memo credit or Pro.
- A legacy memo that was **never unlocked** re-runs like any new memo (unchanged).
- **Pro and owner accounts** behave as before: every memo is created unlocked, and their re-run does not use the
  free one (no `memo_rerun_free` row is written).
- `GET /v1/memos/{id}` sets `MemoRecord.rerun_free: true` on a ready legacy memo with `access: "full"` whose free
  re-run is unused (it is `false` everywhere else, and on other routes). The re-run card shows "re-running it is
  free" while it is true, and "another re-run ... charged like any new one" once it is used.
- `memo_started` gains `rerun_of` and `free_rerun` when the request has `rerun_of`.

A row
marked format 3 that no longer fits the schema is treated the same way on every one of these routes,
including the list and `unlock` (no credit is spent). That covers format-2 memos stored before `site_history`,
`ComparableCase.record_kind`, `BaseRate.excluded_not_use_decision`, `pathway` and `MemoApprovalRow.basis` were
added (2026-11-10): all are required, and a stored memo that still carries `original_status` or `rows_reset`
no longer fits either, so such a memo is served as `legacy_format: true`, never as an error. The admin
overview counts such a row the same way: it is in `memos.legacy_format` and not in `memos.by_overall_status`.

## SSE events for `POST /v1/memos` and `/clarify`

| event | data |
|---|---|
| `memo_created` | `{memo_id}` |
| `stage` | `{stage, status, message}` with stage, in order: `intake, records, precedent, finalize`. `records` also applies the rules; `precedent` ranks the comparables by the fixed score; no stage after `intake` calls a model |
| `tool` | `{stage, tool, status, message, rows?}` tools: `geocode_address, nearby_applications, nearby_licenses, nearby_businesses, overlays_at, zoning_at, base_rate, read_decision` |
| `needs_clarification` | `{memo_id, questions, profile}` → `POST /v1/memos/{id}/clarify`. No longer sent: a question a model wrote is not asked, and the rules name what is missing instead. The route stays for memos already waiting for an answer |
| `memo` | `MemoRecord` (teaser or full depending on entitlement) |
| `error` | `{code, message}`; codes: `address_not_found`, `outside_coverage` (not SF), `generation_failed`. The memo stream has no triage stage, so it never sends `not_hospitality`. |

`POST /v1/memos/{id}/answers` (an answer round) sends `answers_round` `{memo_id, round}` first in place of
`memo_created`, then the same `stage` and `tool` events (the `intake` stage's message is "Applying your answers to
the facts read from your description…": no model call), then `memo` with the updated `MemoRecord`, or `error`
(the memo is then as it was before the round).

There is no `narrative` event: no stage streams prose. Every `tool` event with status
`started` is followed by one with status `completed` for the same `stage` and `tool` (the zoning and overlay
lookup at the start of the records stage is one pair under `zoning_at`).

## Pathway and statuses: set by rule

`apps/api/app/memo/pathway.py` (`determine`, rule table v2) decides, with no model call, everything in the
report that is a decision. It runs once, when the records are collected. The same facts always give the same
answer. The binding spec is `docs/validation/rule-table-extension-spec.md`; the rules and every fixed sentence
and code reference are in the module docstrings and tables of `pathway.py` (`LEGAL_BASIS`), `triggers.py`
(`TEXT`), `rows.py` (`ROW_BASIS`) and `facts.py` (`MISSING_PHRASES`).

**What the rules read.** The concept profile, as stated and derived facts (`app.memo.facts`: the Planning Code
use, the licence type and how the licence is to be obtained, whether the business is part of a chain, the
floor area, what the space was last used as, whether an existing business stays and changes, the story, the
closing hour, the kind of entertainment, the outdoor area, whether an earlier approval is amended, the seats);
the zoning district at the address and every overlay there; the dated control data
(`apps/api/app/memo/data/sf_dated_controls.json`) read for the **rules date**; the records on file at the
report's own street address as they stood on the rules date (active ABC licences, earlier Conditional Use
decisions); and the census tract of the geocoded point (`app.memo.tracts.tract_at`), for the licence
concentration lines of the alcohol row. Nothing else is read: not the comparables, not the base rate, not any
model text.

**The rules date.** `MemoRunInput.rules_date` is the date whose rules apply. `None` (every report made through
the API) means today. A past date reads every control as it stood on that day; the records, the comparables
and the counts stay today's. `Memo.pathway.rules_date` carries the date (ISO), and the report prints "Rules
applied as of <date>". The local scripts take it as `--rules-date YYYY-MM-DD`.

**A missing input is never an assumption.** A fact the description does not give has no value. A trigger that
needs it is `not_decided` and names it; a row that needs it is `insufficient_information` and lists it in
`missing_inputs`, in a fixed phrase ("the floor area of the business, in square feet", "whether the business is
part of a chain that shares its name, look or menu with other locations", "how many other locations the chain
has, open or approved, anywhere in the world" (named instead of the chain question when the applicant says it is
a chain but skips the count), "how the liquor licence will be obtained (new, or a transfer from another owner or
another location)", "what alcohol will be served: beer and wine, or spirits too" (named instead of "the licence
type" when the concept serves alcohol without saying what and that would decide the type)). The inputs an intake question asks for are named in the question's words. Each missing input is
also asked once in `could_not_establish` ("Not known: <phrase>. Needed for: <rows>."); a trigger's input is
not asked when the zoning row is not permitted, because no answer changes that. A fact the intake model filled
without a quote from the text is cleared first and treated the same way (see "Only what the text states").

**What the rules set.**

| | Field | How |
|---|---|---|
| Proposed use | `pathway.use` (bar, restaurant, limited restaurant, nighttime entertainment, or not covered) | Planning Code § 102, from the kind of business. A bar that serves no alcohol, by the "No alcohol" answer or by the description's own words ("a zero-proof cocktail bar", "an alcohol-free bar"), is not a Bar (§ 102 defines a Bar by its on-site alcohol sales; from 2026-11-16): no use is assumed in its place (`not_covered`), there is no alcohol row, T1 is not decided, and the report asks "what kind of food or drink service it is, ...: a Restaurant (prepared food, with seating), a Limited Restaurant (ready-to-eat food or drinks) or another use", pointing at the intake question `food_service`. Its answer `"restaurant"` or `"limited_restaurant"` is then the use, read from the answer (line `zoning.food_service`), still with no alcohol row; `"other"` keeps it not known and named. A bar the description is silent about is still a Bar, and so is a "sober-curious" or "mocktail" bar that answered nothing (neither word says no alcohol is served); the phrase a no-alcohol word modifies is left out whole ("a non-alcoholic beer and wine bar" pours none) |
| Triggers | `pathway.triggers`: always eleven `TriggerFinding`s, T1 to T11 (use control of the district, use control of a special use district, enlarging or intensifying an existing use, liquor licence rule of a restricted district, formula retail, nighttime entertainment, use size, removal of a laundromat, outdoor activity area, changing the conditions of an earlier approval, hours of operation) | Each has a `control`: `principal` (asks for nothing), `conditional`, `not_permitted`, `not_decided` (an input is missing: `missing_inputs` names it), `does_not_apply`, `code_and_practice_differ`. `in_force_from` and `ordinance` give the version of the control read. `differs_today` is true when the control on the rules date is not today's control; the trigger then carries one line (rule id `T<n>.differs`) saying when it changed and what it reads today |
| Control on a new use | `pathway.permission`, `pathway.permission_label` | The most restrictive of T1, T2, T4 and T11 (and T6 when the use is Nighttime Entertainment), read as for a new use. Not decided or "Code and Planning practice differ" is `not_covered` with the label saying which. No story given: `not_covered`, "Not decided by the rules", unless one of them is not permitted |
| Change of use | `pathway.changes`: three separate answers, each with its own rule lines | `planning_use` (yes / no / not established: the last lawful use against the proposed § 102 use), `building_occupancy` (yes / no / not established: not established unless the existing occupancy group is stated), `neighbourhood_notice` (required / not required / not established, under the Planning Code on the rules date). `pathway.change_of_use` is `changes.planning_use` |
| Zoning row | status | Any trigger not permitted → not permitted; else a trigger not decided because no story is given (it names "which stories the business occupies") → insufficient information, with `missing_inputs` naming the story, even where another trigger is conditional (no story is ever assumed); else any conditional → further review (Conditional Use Authorization); else any not decided → insufficient information, with `missing_inputs`; else Code and practice differ → further review with the status note "Code and Planning practice differ"; else allowed |
| Alcohol row | status | Not permitted where the zoning row is not permitted and the business is new (the use itself, formula retail, use size, the hours or anything else zoning bars; Business and Professions Code § 23790), where a prohibited use bars it even if the business stays (the use itself or formula retail; decided 2026-11-12), or where a district's licence rule bars the licence; insufficient information when the licence type (or what alcohol will be served, which decides it) or how the licence is to be obtained is not given; potential blocker for a requirement that could stop the licence; otherwise further review. Where the census tract is over its authorised number the row gets the status note "public convenience or necessity finding likely required" (Business and Professions Code § 23958.4); that fact alone never makes the row a blocker or not permitted |
| Entertainment row | status | Not permitted when the use itself, formula retail or Nighttime Entertainment is not permitted (Planning Code § 175(a)); otherwise further review, naming the permits |
| Health row | status | Not permitted when a prohibited use makes the zoning row not permitted: the use itself (T1, T2) or formula retail (T5) (Planning Code § 175(a): no City department may issue a permit for a use the Code does not permit; decided 2026-11-12). The status line names what bars the concept. Hours, use size, Nighttime Entertainment, the outdoor area, a liquor licence rule and the other triggers do not reach this row. Allowed otherwise |
| Building row | status | Not permitted when a prohibited use (the use itself or formula retail) makes the zoning row not permitted (Planning Code § 175(a)). Otherwise from the first two change-of-use answers: either is yes → further review; both no → allowed; otherwise insufficient information, with `missing_inputs` |
| Outdoor row | status | Not permitted when a prohibited use (the use itself or formula retail) makes the zoning row not permitted (Planning Code § 175(a)), or when T9 bars the outdoor area itself. Otherwise by T9 where the area is on the lot; further review for a sidewalk or parking-lane area |
| Notes | `pathway.notes`: text on file for the district and its overlays that the rules do not evaluate, printed as "Note on file, not evaluated by the rules: …" | |

**Status notes.** `MemoApprovalRow.status_note` is a fixed qualifier the report prints after the status:
"Further review: Code and Planning practice differ", "Further review: public convenience or necessity finding
likely required". It is part of the status as printed, it never changes `status`, and it is `null` on most
rows.

**Referral steps are not approvals.** `MemoApprovalRow.referral_steps` lists the steps inside the row's
approval where one agency sends the application to another (ABC to Police and Planning; the Entertainment
Commission to Police, Planning, Public Health and Fire; the health permit and the building permit to
Planning), each a `RuleLine` with rule id `referral.step`, dated on its own. A referral step never sets or
changes a status, is never a row, and is never in `entitlement_path`. A referral that was removed is still
listed, with the day it ended ("That step has ended. The permit is still required."): removing a referral
shortens an approval and does not remove it. A row that is not permitted lists none.

**Read this first: the headline findings (from 2026-11-16).** `Memo.headline_findings` lists, ahead of everything
else, what changes the business's plans at the address, whatever else is still not known: every trigger that
bars the concept (and then nothing else), otherwise every trigger that asks for a Conditional Use Authorization
("The concept needs a Conditional Use Authorization, which the Planning Commission decides at a public hearing
(Planning Code § 303). What asks for one: use size."), then every reading that would ask for one, or bar the use,
only if inputs not given go one way (`TriggerFinding.contingent`: T1 and T6 for the story, T5 for a chain of eleven
or more, T7 for the floor area, an enlargement, a merger, the floor area before and the space's last use; "If the
existing business is enlarged or storefronts are merged, the concept needs a Conditional Use Authorization ... Not
known: whether an existing business is to be enlarged or intensified; whether storefronts are to be merged.").
Each condition is checked by running the trigger itself again over every value those inputs can take, and kept
only where every such run gives the control it names: with the floor area not given, "If the floor area is from
2,501 to 4,000 square feet, ... needs a Conditional Use Authorization" and "If the floor area is 4,001 square feet
or more, zoning does not permit the concept ..." (CRNC), "If the floor area is 5,001 square feet or more, zoning
does not permit ..." and no Conditional Use (CVR, a Restaurant: Table 811 Note 1), "If the floor area is 4,001
square feet or more and either the floor area grows or storefronts are merged, ..." (a former restaurant in
NC-2, Interpretation 121.2). An answer already given is never offered again as a way. A decided control that an
input not given could change (`TriggerFinding.unsettled_by`: T7 reads a space whose last use is not given as new)
gives no definite finding, only its contingent readings ("If the space was last used as another use (not a Bar,
...), or the floor area grows, or storefronts are merged, ..."). A contingent finding is never worded as definite;
it takes its row's own status and its inputs are still asked in `could_not_establish`. Where no
story is given the zoning row stays insufficient information (no story is assumed), and a definite Conditional
Use says "Whatever the story, ..." and that the rules cannot yet say whether zoning permits the use there at all.
No status of a row changes. The text report, the PDF ("Read this first", before "Overall") and the web page (a
block above the overall card) print the findings first.

Each row also gets its `approval` and `agency` by rule. `overall.status` is the most severe row status, and never
less severe than a definite headline finding (a Conditional Use makes it at least further review even where the
zoning row is insufficient information for a missing story; a contingent finding never raises it);
`overall.line` opens with one sentence per kind of headline finding ("A Conditional Use Authorization is needed
(use size).", "A Conditional Use Authorization is needed if the existing business is enlarged or storefronts are
merged (use size).") and then names each row's status ("Of the 5 approvals this concept needs: 3 further review
(…), 1 insufficient information (alcohol licence), 1 allowed (health permit)."); the teaser's `overall_line` is
the same line. `Memo.entitlement_path` lists the
approvals to file, in order, joined with "; ". A row that is insufficient information adds no approval to the
path (the rules do not know which approval it is), and the zoning and outdoor entries are left out when those
rows are allowed (nothing is filed with Planning). When any row is not permitted the path is the sentence "No
approval path: zoning does not permit the concept as described at this address." and lists no approval; the
PDF and the web page then print no days and no cost beside it. With nothing to file it is "No approval to
file." `overall.citations` are the record ids the rows' rule lines cite.

**What could not be established.** `could_not_establish` is the rules' questions, in their order: one per
missing input, then the question for Planning where the Code and Planning practice differ, then the
last-legal-use question where "no change of use" rests on a licence type alone. Every question of the rules is
kept, and there is no other. `Memo.records_limits` is one fixed line printed at the end of the
section on every report: "Physical and cost issues are outside what public records can show: ventilation and
kitchen exhaust, exits and occupant load, accessibility, the condition of the space, and the landlord's
consent."

**Rule lines.** Every rule that was applied leaves one `RuleLine`: a sentence built from the fields of the
records it read, the code section it rests on when there is one, and the ids of those records. A row's lines
are `MemoApprovalRow.basis`; the pathway's are `Memo.pathway.lines`. No model writes them.

**Same input, same statuses.** The rules are pure code, so the same profile and the same records give the same
pathway and statuses. The profile still comes from a model (the intake stage). Intake is sent at temperature
0 to keep the profile as steady as the model allows. Over the same records, a profile that differs between
two runs is the only way their statuses can differ.

In the PDF each approval row prints, in this order: its status with its status note ("Further review: Code
and Planning practice differ"); "Rules applied" (the row's rule lines, each followed by its code section
unless the sentence already names it); "Steps inside this approval" with the sentence "These are review steps
inside the approval, where one agency sends the application to another. They are not separate approvals." and
the referral steps; "Not given" with the missing inputs; under the building row "Change of use: three separate
answers" with the three answers each on its own line (and any rule line of an answer that "Rules applied" did
not already print); then "Facts the rules read" with each fact and where it came from. A part with nothing in
it is left out.
The approvals table prints the status with its note too. "What the records could not establish" ends with
the fixed `records_limits` line. "At a glance" starts with a "Pathway" block: proposed use, zoning district,
control on a new use, existing use, change of use, "Rules applied as of <date>", then the notes, then
"Triggers": every trigger with its control ("T7 Use size: Not decided (control in force from 2025-10-06, Ord.
173-25, File No. 250634). Not given: the floor area") and, under a trigger whose control on the rules date is
not today's, the sentence that says so. The plain-text report prints the same under `PATHWAY (set by rule)`,
`TRIGGERS:` and `rule [<rule id>] …` / `step [referral.step] …` lines, and ends with a `STATUSES:` line (each
row's status and rule ids) for comparing runs. The local run scripts also print, under `ROWS`, the rules date
and one line per row: its status with its note and the inputs not given.

## The evidence

Built in code (`app.memo.evidence`) from what the runner already holds; no model call.

**The facts the rules read.** `Memo.facts` lists every fact the rules read about the concept that is known, then
every one that is not known and that a row or trigger names (or that the stated-facts check cleared). Each is a
`MemoFact`: `label` ("Closing time"), `value` in plain words ("After midnight", "40", "Type 42 (on-sale beer and
wine, public premises)") or `null` when not known, and where it came from: `origin` is `description` (with
`quotes`, the applicant's words that state it, each cut from the text they sent, never the model's own string; a
quote the model gave in parts, "a ... b", is shown as one snippet per part), `intake_answer`, `clarification_answer`, `request`, `record`
(with `citations`) or `not_known`. `origin_label` is the fixed phrase the report prints ("Your description",
"Your answer to an intake question", "Records on file at this address", "Not known"); a value the rules worked
out from another one says so ("Worked out by the rules from your description"). A description that says nothing
about alcohol gives "No alcohol" with the label "Your description does not mention alcohol". Each row's `facts`
holds the known facts that row's rules read (`ROW_FACTS` in `app.memo.evidence`), the record facts last: the use
the records show at the address, the active ABC licences there and the earlier approved use decisions there,
each citing its records. What a row is not given is its `missing_inputs`, as before.

**Comparable cases** are the top 10 of the fixed ranking (`app.memo.analytics.rank_candidates`: the kind of
business in common 40%, the distance 25%, how recent 15%, late-night hours in common 10%, decided or not 10%, a
little more for a Conditional Use case), in ranking order. Each carries what its record says (record id, kind,
address, use, filed and decided dates, days from filing, outcome, closing hour, conditions on file) and its
source link. `Memo.comparables_note` is the fixed line saying how they were chosen, or "No Planning or
Entertainment Commission record within 1,000 ft matched this kind of business." when there is none.

**Site history** entries carry the record's `use_types`, `hours_close` and `conditions` where the record has
them.

**The outcome counts** list each decision counted in `base_rate.counted` (record id, permit type, address,
outcome, dates, source link), newest first. The days from filing by outcome are computed from the comparables
listed. The density counts (businesses and licences within 500 ft) are not in the live report: they are not shown
with their records. The census tract's licence counts stay in the alcohol row's rule lines, with their source.

**Fixed lines.** The rule lines, status lines, missing-input phrases, the overall line, the entitlement path
(`Memo.entitlement_path`), the comparables note and the disclaimers are fixed sentences written by code.
`model_versions` holds `intake` only.

## Record kinds, comparables, the base rate and the site history

Planning records in the store can carry three labels in `extra`, written by a classifier: `premises` (true
when the record is about one food, drink or entertainment premises), `use_class`, and `record_kind`
(`use_decision`, `agency_referral`, `building_work` or `other`). A record is **labelled** when `extra` has a
`record_kind` key.

**Record kind of a record** (`record_kind` / `record_kind_label` on comparables and site-history entries):
an ABC record is `licence`; an Entertainment Commission record is `entertainment_permit`; otherwise the
classifier's label when it is one of the four values; otherwise `not_labelled`.

| | Labelled Planning record | Record without labels |
|---|---|---|
| Comparable candidate | only when `premises` is true and the kind is `use_decision` or `agency_referral` | as before: the 200 nearest non-licence records within 1,000 ft are ranked |
| Base rate pool | only when `premises` is true and the kind is `use_decision` | as before: every dated, decided Planning record that shares a use type |
| Site history | listed when it is at the site | listed when it is at the site, as `not_labelled` |

Agency referrals are not in the rate: Planning answers nearly every referral "permitted", which is a different
pathway from a contested use decision. Building work and `other` records are never comparables and never in
the rate; they appear only in the site history. ABC licences and Entertainment Commission permits are
unchanged: licences are never candidates, and neither enters the rate.

**The candidate window.** Comparables are ranked from the 200 nearest non-licence records within 1,000 ft.
Labelled records that can never be comparables (building work, other records, records about other premises)
must not use that window up: when fewer than 200 of those rows can be comparables, the list is topped up with
the nearest records within 1,000 ft that can be, until 200 are in hand. The added records get citations like any
other. With no labels every record can be a comparable, so nothing is added.

**Fall-back.** Production records do not carry labels yet. Until they do, every rule above takes the right-hand
column: the comparables and the base rate are computed exactly as before, `excluded_not_use_decision` is 0,
`scope` is unchanged, comparables report `record_kind: "not_labelled"`, and the site history still lists the
records at the address (it does not depend on labels).

**What the base rate leaves out.** Each left-out record is counted under exactly one field, checked in this
order: `excluded_grant_only` (Entertainment Commission permits and ABC licences), `excluded_not_use_decision`
(labelled Planning records that fail the pool rule above: referrals, building work, other records, records
about other premises; counted whatever their use type, outcome or dates), `excluded_undated` (comparable decided
Planning records without both dates in order). When `excluded_not_use_decision` is above 0, `scope` ends with
the three counts in plain words, zero counts skipped, e.g.
`"N = 12 dated decisions within 1,000 ft, last 5 years; left out: 14 permits and licences, 31 records that are not use decisions for this kind of business, 3 undated"`
(singular: `1 permit or licence`, `1 record that is not a use decision for this kind of business`). The tail
always starts with `"; left out:"`. When the count is 0, `scope` is the same string as before. The PDF and the
plain-text report then say what each count is: "Entertainment Commission permits and ABC licences are lists of
grants only, so they are not counted." (when that count is above 0), "Agency referrals, building work, other
records and decisions about other kinds of business are not counted." and "Decided Planning records without
both dates are not counted." (when that count is above 0).

**Site history** (`Memo.site_history`) is built in code; no model writes it. A record is at the site when:

1. its parcel equals the report's parcel (both present; compared without spaces or the slash), or
2. its street address is the report's street address after normalising: upper case; city, state and ZIP
   dropped; unit and suite text dropped (`#2`, `Suite 200`, `Apt B`, `2nd Floor`); a letter or fraction on the
   number dropped; the street suffix abbreviated (`STREET` → `ST`, `AVENUE` and `AV` → `AVE`, and the Planning
   case list's `BL` → `BLVD`, `WY` → `WAY`, `PZ` → `PLZ`, `TR` → `TER`, `HY` → `HWY`, `CR` → `CIR`); compass
   words shortened (`SOUTH` → `S`); numbered streets written one way (`03RD`, `THIRD` → `3RD`). The street
   ends at its suffix, so the floor and unit text the Planning case list writes after it is dropped
   (`995 VALENCIA ST STREET LEV`, `70 OCEAN AV 0001`, `5320 GEARY BL GROUND`); a compass word straight after
   the suffix is kept (`BUENA VISTA AVE E`), and the first word of a street is never read as a suffix
   (`AVENUE OF THE PALMS`, `ST FRANCIS BLVD`). Both ends of a number range are kept (`993-995`, `991 - 999`,
   `997/999`, `997, 999`): the addresses match when the streets are equal and one number is the other's number
   or lies inside the other's range on the same side of the street (same odd or even as the range's first
   number; any number when the two ends differ). So `993-995 VALENCIA ST` and `991 - 999 VALENCIA ST` are at
   995 Valencia St, and `997-999 VALENCIA ST` is not. A range written backwards or wider than 100 numbers is
   read as its first number. A street written without its suffix (`995 VALENCIA`) matches only when the record
   is mapped within 30 metres of the report's point, because 3rd St and 3rd Ave both exist. An address with no
   street number cannot match by address, or
3. it has no parcel and no number anywhere in its address, and is mapped within 12 metres of the report's
   point.

A record that names a different parcel and a different address is not at the site, however close it is. That
includes an address with a number in it that cannot be read as number and street (`Valencia St & 21st St`,
`Pier 39`): it names a place of its own, so the 12 metre rule does not apply to it.

A record tied to the site by its parcel can be filed under another street number on the same lot, which may be
another unit or storefront. `SiteHistoryEntry.address` carries the record's own address; when it is readable
and is not the report's address (by rule 2, a missing suffix allowed), the PDF and the plain-text report print
"Filed under 993 Valencia St" in the row.
Records come from the reads the report already makes within 1,000 ft, plus one read of every record of any
kind within 30 m of the point, merged by id. A record the store holds without a map point is not found.
All record kinds are listed: use decisions, referrals, building work, other records, ABC licences,
Entertainment Commission permits and records without labels. Entries are newest first by decision date, or
else filing date; undated records come last. `entries` holds at most 20; `total` and `by_kind` count them all
(the PDF prints "Showing 20 of 37" when the list is cut). Each listed entry is a citation `app:<id>` in
`Memo.citations`, an ABC licence included. Each entry also carries the record's uses, closing hour and conditions where it has them. The rows read only the records at the report's own street address (the facts they read cite them).

`site_history.note` is one of two fixed sentences: "Records on file at this address or parcel, newest first.
Building work is listed here and is not counted in the outcome counts." or, when nothing was found, "No
records at this address or parcel in the data. That does not mean nothing was ever filed here."

In the PDF, "Site history" follows "What the records could not establish" and comes before the comparables:
the note, the matching rule, then a table Date | Kind | What | Outcome. "What" is the permit type, the
description and, for a record filed under another address, "Filed under <address>". The comparables table
prints the record kind under the source.

## Days from filing, by outcome

A number of days read from the records means different things by outcome, so the report never prints one
figure across outcomes, and never a mean or a median.

* `ComparableCase.days_to_decision` is unchanged: decided minus filed for that one case. What it measures
  depends on that case's `outcome`.
* `ComparableCase.outcome` is the store's outcome, except that a withdrawn case whose own status says
  cancelled (the Planning case list's "Closed - Cancelled" and "Cancelled") is `"cancelled"`. The store has no
  outcome for a cancelled case; naming it keeps cancelled and withdrawn cases apart. The citation label and
  the site-history entry of such a case say "cancelled" too, and so does the outcome the precedent tool sends.
  `base_rate.withdrawn` still counts both, and the report labels it "withdrawn or cancelled".
* In the PDF and on the web page the comparables column is "Days from filing", and each cell names the outcome
  its figure is for:
  "120 days to approval", "120 days to denial", "77 days to withdrawal", "400 days to cancellation", "121 days
  to closing, outcome not recorded", and for a case still pending "pending 312 days so far": its age on the
  records date (`data_as_of`), not a time to a decision. A dash when a date is missing.
* Under the table (PDF and web) and under `DAYS FROM FILING, BY OUTCOME` (plain text) the report gives one line per
  outcome that has a figure, in this order: Approved (with or without conditions), Denied, Withdrawn,
  Cancelled, Outcome not recorded, Still pending. Each line gives the number of cases and their lowest and
  highest figure ("Approved: 3 cases, 120 to 140 days from filing to approval."); the pending line says "age so
  far as of <date>, not a time to a decision". A last line counts the cases with no figure.
* The base rate block holds counts only; it has no days.

## Types

```ts
export interface GeocodeSuggestion { address: string; normalized_address: string; lat: number; lng: number; parcel: string | null; zip_code: string | null; confidence: number }

export type ApprovalArea = "zoning_use" | "alcohol" | "entertainment" | "health" | "building_change_of_use" | "outdoor";
// display: Allowed · Further review · Potential blocker · Not permitted · Insufficient information
export type ApprovalStatus = "allowed" | "further_review" | "potential_blocker" | "not_permitted" | "insufficient_information";
export type PlanningUse = "bar" | "restaurant" | "limited_restaurant" | "nighttime_entertainment" | "not_covered";   // not_covered: the rule table has no control on file for the concept's use
// Rule table v2: each reason the code can require a hearing is a trigger, evaluated on its own (T1 to T11).
export type TriggerFamily = "new_use_control" | "special_district_use_control" | "enlarge_or_intensify" | "licence_in_restricted_district" | "formula_retail" | "nighttime_entertainment" | "use_size" | "laundromat_removal" | "outdoor_activity_area" | "amend_prior_conditions" | "hours_of_operation";
// principal: asks for nothing. not_decided: it matters here and an input is missing. code_and_practice_differ: the code text and Planning's own records are known to differ here.
export type TriggerControl = "principal" | "conditional" | "not_permitted" | "not_decided" | "does_not_apply" | "code_and_practice_differ";
export type NoticeAnswer = "required" | "not_required" | "not_established";
export type UsePermission = "principal" | "conditional" | "not_permitted" | "not_covered";   // for a NEW use of that kind at the address
export type ChangeOfUse = "yes" | "no" | "not_established";

export interface Citation {
  // every site-history entry is cited as "app:<record id>", an ABC licence included ("app:abc:123456")
  id: string;                      // "app:datasf_planning:2019-012345CUA" | "overlay:static:sf:mission_alcoholic_beverage_sud" | "zoning:NCT-3" | "license:abc:123456" | "stat:base_rate" | "stat:density" | "catalog:sf.conditional_use_authorization" | "feedback:<uuid>"
  kind: "application" | "overlay" | "zoning" | "license" | "statistic" | "feedback" | "catalog";
  label: string;                   // short human label shown in the memo footnote
  source_url: string;              // public record / code section URL
  excerpt: string | null;          // the sentence from the record that supports the claim
}

export interface MemoTeaser {
  overall_status: ApprovalStatus; overall_line: string;
  comparable_count: number; approvals_count: number;
  blockers_count: number;          // rows that are potential_blocker or not_permitted
}

// Where one fact the rules read came from.
export type FactOrigin = "description" | "intake_answer" | "clarification_answer" | "request" | "record" | "not_known";

// One fact the rules read, and where it came from. Built by code (app.memo.evidence); no model writes it.
export interface MemoFact {
  fact: string;                    // the fact's name, e.g. "closing", "seats", "existing_use_records"
  label: string;                   // "Closing time"
  value: string | null;            // in plain words; null when not known
  origin: FactOrigin;
  origin_label: string;            // "Your description", "Your answer to an intake question", "Records on file at this address", "Not known"; "Worked out by the rules from …" when derived
  derived: boolean;                // the rules worked the value out from what the origin gave
  quotes: string[];                // the applicant's words that state it (origin "description")
  citations: string[];             // the records that show it (origin "record"); all are in Memo.citations
}

// One dated decision counted in the outcome counts.
export interface CountedDecision { application_id: string; permit_type: string; address: string | null; outcome: string; filed_at: string | null; decided_at: string | null; source_url: string }

// One rule the code applied. Built from record fields; no model writes it.
export interface RuleLine {
  rule_id: string;                 // stable id of the rule, e.g. "zoning.use", "T1.cell", "T4.differs", "alcohol.status", "change.notice", "referral.step"
  text: string;
  code_section: string | null;     // the code section the rule rests on, when there is one
  source_url: string | null;       // where that section can be read, when on file
  citations: string[];             // ids of the records the rule read; all are in Memo.citations
}

// The zoning answer for this concept at this address, looked up by rule. No model sets or changes it.
export interface Pathway {
  use: PlanningUse; use_label: string;                         // "Bar" · "Restaurant" · "Limited Restaurant" · "Nighttime Entertainment" · "a use the rule table does not cover"
  district: string | null;
  permission: UsePermission; permission_label: string;         // "Permitted" · "Conditional use" · "Not permitted" · "Not covered by the rule table" · "Not decided by the rules" · "Code and Planning practice differ" (permission is "not_covered" for the last three)
  existing_use: PlanningUse | null;                            // what the records show the space is used as now; null = not shown
  change_of_use: ChangeOfUse; change_of_use_label: string;     // "Change of use" · "No change of use" · "Change of use not established"
  lines: RuleLine[];               // the rules applied, in order
  notes: RuleLine[];               // text on file for the district and its overlays that the rules do not evaluate
  // Rule table v2 (null / empty on a memo stored before it):
  rules_date: string | null;       // ISO date whose rules were applied: today for a live report, a past date in the backtest
  triggers: TriggerFinding[];      // always T1 to T11, in order
  changes: ChangeAnswers | null;   // change of use as three separate answers
}

// One trigger, evaluated by rule on the rules date. No model writes it.
export interface TriggerFinding {
  rule_id: string;                 // "T1" to "T11"
  family: TriggerFamily; label: string;   // label: "Use control of the zoning district", "Formula retail", "Hours of operation", …
  control: TriggerControl;
  missing_inputs: string[];        // fixed phrases naming what the input did not give; set when control is not_decided
  lines: RuleLine[];               // at least one: what was read and what it means here
  in_force_from: string | null;    // start date of the version of the control used; null = in force before 2022
  ordinance: string | null;        // the ordinance that made that version, when the data names one
  differs_today: boolean;          // the control on the rules date is not today's control; `lines` then holds one line with rule id "T<n>.differs" saying so
  // From 2026-11-16 (T1, T5, T6, T7): what the trigger's own reading gives once inputs not given go one way, each checked
  // by running the trigger again over every value those inputs can take ("the existing business is enlarged or storefronts
  // are merged", "the floor area is from 2,501 to 4,000 square feet", "the business has eleven or more other locations").
  // `control` is unchanged. [] when there is none; absent on older reports.
  contingent?: { control: "conditional" | "not_permitted"; condition: string; missing_inputs: string[] }[];
  // the inputs not given that could change a decided `control` (T7: the space's last use); the control is then no
  // definite headline finding. [] otherwise; absent on older reports.
  unsettled_by?: string[];
}

// A finding that changes what the business needs at this address, printed first (rule 9, from 2026-11-16). Set by rule.
export interface HeadlineFinding {
  kind: "not_permitted" | "conditional" | "conditional_if" | "not_permitted_if";
  sentence: string;                // fixed sentence: "The concept needs a Conditional Use Authorization, which the Planning Commission decides at a public hearing (Planning Code § 303). What asks for one: use size."
  area: ApprovalArea;              // the row that carries it: the outdoor row for T9 when there is one, else zoning_use
  status: ApprovalStatus;          // not_permitted / further_review; for a contingent one, its row's own status
  trigger: string; trigger_label: string;   // "T7", "use size"
  definite: boolean;               // false for conditional_if / not_permitted_if: it depends on a missing input
  condition: string | null;        // for a contingent one: its reading's condition
  missing_inputs: string[];        // for a contingent one: the inputs its condition turns on
  code_section: string | null; source_url: string | null; citations: string[];
  basis: RuleLine[];               // the trigger's line the finding rests on
}

// Change of use is three separate questions, each with its own answer and rule lines.
export interface ChangeAnswers {
  planning_use: ChangeOfUse; planning_use_lines: RuleLine[];             // Planning Code § 102 use categories
  building_occupancy: ChangeOfUse; building_occupancy_lines: RuleLine[]; // Building Code occupancy group; not_established unless the input says
  neighbourhood_notice: NoticeAnswer; neighbourhood_notice_lines: RuleLine[];   // Planning Code neighbourhood notification on the rules date
}


export interface MemoApprovalRow {
  area: ApprovalArea; area_label: string;            // "Zoning and use", "Alcohol licence", "Entertainment permit", "Health permit", "Building permit and change of use", "Outdoor seating or activity area"
  approval: string; agency: string;                  // set by rule
  status: ApprovalStatus;                            // set by rule
  status_note: string | null;                        // set by rule: a fixed qualifier printed after the status ("Code and Planning practice differ", "public convenience or necessity finding likely required"). It never changes the status
  basis: RuleLine[];                                 // the rules that set the status ("Rules applied"); at least one
  referral_steps: RuleLine[];                        // set by rule: steps inside this approval where one agency sends the application to another ("Steps inside this approval"). Never an approval: not a row, not in entitlement_path, never sets a status
  missing_inputs: string[];                          // set by rule: fixed phrases naming what was not given ("Not given"); set when the status is insufficient_information
  facts: MemoFact[];                                 // the known facts this row's rules read, each with where it came from
  history_note: string | null;                       // "No outcome history for this pathway yet." on alcohol and entertainment rows, else null
}

export interface OpenQuestion {
  question: string; needs: "plans" | "inspection" | "applicant_history" | "agency_answer"; ask: string | null;   // question at most 300 characters, ask at most 240
  // the optional intake question whose answer gives this input, when one does (the page offers it; the report run
  // again with the answer settles it); null for a question only an agency or the records answer, and absent on a
  // memo stored before 2026-11-15
  intake_question?: IntakeQuestionId | null;
}

// What a record is. licence = an ABC licence; entertainment_permit = an Entertainment Commission permit;
// not_labelled = a Planning record the classifier has not labelled.
export type RecordKind = "use_decision" | "agency_referral" | "building_work" | "other" | "licence" | "entertainment_permit" | "not_labelled";
// record_kind_label: "Use decision" · "Agency referral" · "Building work" · "Other record" · "ABC licence" · "Entertainment permit" · "Not labelled"

// One record on file at the report's own address or parcel. Built in code; no model writes it.
export interface SiteHistoryEntry {
  application_id: string; citation_id: string;       // citation_id is "app:<application_id>" and is in Memo.citations
  source: string; source_label: string;              // same rule as ComparableCase.source
  record_kind: RecordKind; record_kind_label: string;
  permit_type: string;
  description: string;             // the record's description on one line, at most 300 characters, ending in "…" when cut
  address: string | null;          // the record's own address; a record tied by parcel can be filed under another street number (the PDF then prints "Filed under <address>")
  filed_at: string | null; decided_at: string | null;
  outcome: string;                 // approved | approved_with_conditions | denied | withdrawn | pending | unknown
  status: string;                  // the source's own status text
  source_url: string;
  use_types: string[]; hours_close: string | null; conditions: string[];   // what the record carries, where it does
}

export interface SiteHistory {
  matched_by: string;              // "Parcel 3616/065 or the address 995 Valencia St"; adds ", or a record with no parcel or street number within 12 m of the address point" when one was matched that way
  total: number;                   // every record at the site; entries lists at most 20 of them, newest first, undated last
  by_kind: Record<string, number>; // RecordKind -> count over all `total` records; kinds with no record are absent
  entries: SiteHistoryEntry[];
  note: string;                    // one of the two fixed sentences above
}

export interface ComparableCase {
  application_id: string; citation_id: string;
  record_kind: RecordKind; record_kind_label: string;   // use_decision or agency_referral when the record is labelled; entertainment_permit; not_labelled when the store's records carry no labels
  source: string;                  // "sf_planning_hearings" when a Commission motion was read for the case, "sf_planning_minutes" when only the Commission's hearing minutes were read, else the record's own source
  source_label: string;            // "Planning Commission motion", "Planning Commission minutes", "Planning case list (DataSF)", …
  permit_type: string; use_types: string[]; address: string | null; distance_m: number;
  filed_at: string | null; decided_at: string | null;
  days_to_decision: number | null; // decided minus filed; null unless both dates exist and decided >= filed. For a case known only from the DataSF list, decided is the date Planning closed the record
  outcome: string;                 // the store's outcome ("approved", "approved_with_conditions", "denied", "withdrawn", "pending", "unknown"), or "cancelled" for a withdrawn case whose own status says cancelled. days_to_decision is always read with it: see "Days from filing, by outcome"
  hours_close: string | null; conditions: string[]; opposition_noted: boolean | null;   // opposition_noted is null while the flag is withheld. An empty conditions list means "none extracted": only a motion carries the adopted conditions (the PDF prints a dash, not 0, for other sources)
  similarity_score: number;        // 0..1 deterministic
  lat: number | null; lng: number | null; source_url: string;
}

// What each source that appears among the comparables, the nearby records or the site history leaves out.
// source ∈ datasf_planning | sf_planning_hearings | sf_planning_minutes | datasf_entertainment | abc | user_feedback
export interface SourceNote { source: string; label: string; leaves_out: string }

export interface BaseRate {
  approved: number; approved_with_conditions: number; denied: number; withdrawn: number;
  total: number;                   // N: dated Planning decisions with a known outcome (filed and decided dates both present, decided not before filed, decided inside the window)
  window_years: number;
  scope: string;                   // always prints N, e.g. "N = 7 dated decisions within 1,000 ft, last 5 years; too few for a rate". Ends with "; left out: 14 permits and licences, 31 records that are not use decisions for this kind of business, 3 undated" only when excluded_not_use_decision > 0
  rate_shown: boolean;             // true only when N >= 10
  approval_rate_pct: number | null;   // approvals as a share of N; null unless rate_shown
  excluded_grant_only: number;     // nearby Entertainment Commission permits and ABC licences left out (grant-only lists never enter the pool)
  excluded_undated: number;        // comparable decided Planning rows left out for lacking a filing or decision date, or with a decision date before the filing date
  excluded_not_use_decision: number;   // labelled Planning records left out because they are not a use decision about a food, drink or entertainment premises (referrals, building work, other records, other premises). 0 when the records carry no labels. A record is counted under one excluded_* field only: grant-only, then this, then undated
  citation_id: string;
  counted: CountedDecision[];      // the N decisions counted, newest first, each with its source link
}

export interface Memo {
  format_version: 3;
  address: string; lat: number; lng: number; parcel: string | null;
  description: string;             // the applicant's own words, as sent
  headline_findings: HeadlineFinding[];   // printed first; [] when there is none and on memos stored before 2026-11-16 (may be absent there)
  overall: { status: ApprovalStatus; line: string; citations: string[] };   // status = the most severe row status, never below a definite headline finding; line opens with the headline findings, then counts the rows
  pathway: Pathway;                // set by rule; see "Pathway and statuses: set by rule"
  approvals: MemoApprovalRow[];    // one row per approval the concept needs: zoning_use, health, building_change_of_use always; alcohol, entertainment, outdoor when the concept has them
  facts: MemoFact[];               // every fact the rules read, known or not, with where it came from; see "The evidence"
  could_not_establish: OpenQuestion[];   // the rules' questions ("Not known: X. Needed for: Y.")
  records_limits: string;          // one fixed line on every report: what public records cannot show (ventilation, exits, accessibility, the condition of the space, the landlord's consent)
  zoning: { district: string; name: string; bar_permission: string; restaurant_permission: string; rules: string; code_section: string; citation_id: string } | null;
  overlays: { name: string; kind: string; effect: string; code_section: string; citation_id: string }[];
  base_rate: BaseRate;
  comparable_cases: ComparableCase[];   // the top 10 of the fixed ranking
  comparables_note: string;        // fixed line: how the comparable cases were chosen
  site_history: SiteHistory;       // records on file at this address or parcel, building work included; see "Record kinds, comparables, the base rate and the site history"
  source_notes: SourceNote[];
  entitlement_path: string;        // set by rule: the approvals to file, in order
  status_definitions: Record<ApprovalStatus, string>;         // the definition shown with each status
  citations: Citation[];
  disclaimers: string[];
  generated_at: string; model_versions: Record<string, string>; data_as_of: string;   // model_versions: intake only
}

export interface MemoRecord {
  id: string; user_id: string; address: string; lat: number | null; lng: number | null;
  description: string; profile: BusinessProfile | null;   // never the intake model's own text: `assumptions` is [], `business_name` and `neighborhood` are null (app.memo.stated.without_model_text), whatever an older row stored
  status: "pending_clarification" | "generating" | "ready" | "failed";   // a row still "generating" 15 min after it last changed reads "failed" (stalled run; `error` says nothing was charged)
  access: "teaser" | "full";
  teaser: MemoTeaser | null;       // present once ready; null when legacy_format
  memo: Memo | null;               // only when access == "full"; null when legacy_format
  legacy_format: boolean;          // stored before report format 3: memo and teaser are withheld; run the address again
  rerun_free: boolean;             // GET /v1/memos/{id} only: a legacy memo the user unlocked whose one free re-run (`rerun_of`) is unused
  rerun_of: string | null;         // GET /v1/memos/{id} only: the legacy memo this memo is the free re-run of; null otherwise
  clarification: { questions: ClarifyingQuestion[]; answers: Record<string, unknown> } | null;
  intake: IntakeAnswers | null;    // the optional intake answers sent with the create request, merged with each answer round's; null when none was answered
  batch_id: string | null; created_at: string; updated_at: string; unlocked_at: string | null; error: string | null;
  answers_round: number;           // answer rounds that finished and were saved (0: the report the memo was made with)
  answers_rounds_left: number;     // 5 - answers_round
  answers_running: boolean;        // a round is running now (status "generating"; the report from before it is still served)
  answers_available: boolean;      // POST /v1/memos/{id}/answers can be used: ready, current format, intake basis kept, a round left
  answered_at: string | null;      // when the last round was saved
}

export interface MemoRevision {    // GET /v1/memos/{id}/revisions: a version an answer round replaced
  round: number;                   // the round that replaced it (1: the version replaced is the report the memo was made with)
  replaced_at: string;
  generated_at: string | null;     // Memo.generated_at of that version
  intake: IntakeAnswers | null;    // the answers that version was run with
  teaser: MemoTeaser | null;
  memo: Memo | null;               // only while the memo is unlocked
  legacy_format: boolean;
}

export type LiquorLicence = "new" | "transfer_from_another_owner" | "transfer_from_another_location" | "already_held" | "none";
export type IntakeQuestionId =
  | "part_of_chain" | "other_locations" | "floor_area_sqft" | "liquor_licence" | "stories" | "alcohol_served"
  | "closing_time" | "last_use" | "fewer_than_50_people" | "outdoor_area" | "outdoor_alcohol_service"
  | "food_service" | "existing_business_change" | "floor_area_before_sqft" | "merges_storefronts"
  | "amends_prior_approval" | "entertainment" | "existing_occupancy_group";
export interface IntakeAnswers {   // every key optional; null or absent = skipped; the keys are the IntakeQuestionId values
  part_of_chain?: boolean | null;
  other_locations?: number | null; // only with part_of_chain true; 0..100000
  floor_area_sqft?: number | null; // 1..1000000
  liquor_licence?: LiquorLicence | null;
  stories?: ("basement" | "first" | "second" | "third_or_above")[] | null;   // one or more, each once
  alcohol_served?: "beer_wine" | "full_liquor" | null;                       // refused with liquor_licence "none"
  closing_time?: string | null;                                              // "HH:MM", 24-hour
  last_use?: "restaurant" | "bar" | "limited_restaurant" | "nighttime_entertainment" | "retail" | "laundromat" | "other" | null;
  fewer_than_50_people?: boolean | null;
  outdoor_area?: "none" | "front" | "rear_or_side" | "rooftop" | "parking_lot" | "sidewalk" | null;
  outdoor_alcohol_service?: boolean | null;                                  // refused with outdoor_area "none"; true refused with liquor_licence "none"
  food_service?: "restaurant" | "limited_restaurant" | "other" | null;       // refused with an answer that says alcohol is served
  existing_business_change?: "none" | "enlarge" | "intensify" | "enlarge_and_intensify" | null;
  floor_area_before_sqft?: number | null;                                    // 1..1000000
  merges_storefronts?: boolean | null;
  amends_prior_approval?: boolean | null;
  entertainment?: "none" | "limited_live_performance" | "place_of_entertainment" | null;
  existing_occupancy_group?: "B" | "A-2" | null;
}

export interface MemoSummary { id: string; address: string; concept: string; status: MemoRecord["status"]; access: MemoRecord["access"]; overall_status: ApprovalStatus | null; comparable_count: number | null; legacy_format: boolean; created_at: string; batch_id: string | null }

export interface AdminOverview {
  ingestion: { backend: string; counts: Record<string, number>; by_source: Record<string, number>; last_runs: Record<string, { started_at: string; finished_at: string | null; status: string; rows_fetched: number; rows_upserted: number; error: string | null }> };
  feedback: { total: number; by_outcome: Record<string, number>; by_concept: Record<string, number>; response_rate_pct: number | null; emails_sent: number };
  memos: { total: number; full: number; teaser: number; last_7_days: number; by_overall_status: Record<string, number>; legacy_format: number };
  users: { total: number; pro: number };
}
```

Analytics events (web): `memo_started`, `memo_completed` (properties: `memo_id`, `overall_status`, `access`), `memo_teaser_viewed`, `memo_unlocked`, `memo_paywall_hit`, `memo_pdf_exported`, `bulk_uploaded`, `feedback_submitted`.

Error codes added by this contract: `paywall_memo` (402), `pro_required` (403), `legacy_format` (409), `not_ready` (409), `not_pending` (409), `rerun_not_legacy` (409).
