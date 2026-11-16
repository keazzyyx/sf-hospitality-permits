# Backtest plan (for approval; nothing run)

Status 2026-11-11: ready for approval. Nothing has been run. Coverage is after the review fixes; the cost is from five
measured report runs on the final code.

Cases: [`../../backtest/cases.yaml`](../../backtest/cases.yaml), 40 San Francisco Conditional Use cases about
food, drink and entertainment premises, filed 2022 to 2025: 25 decided with conditions extracted from the motion,
15 that did not reach approval (withdrawn or cancelled; N01 to N15). There is no disapproved case of this kind filed since
2019. The list is not changed to fit the tool: a case the rules do not cover stays in and counts as a miss,
reported separately.

## 1. What is being tested

For each case the report is generated as if on the day before the case was filed (the "rules date": every
dated control is read as it stood that day), and compared with what the decision record shows.

**What the report is given:** the address, the neutral concept text (`concept_input` in `cases.yaml`), and the
answers to the three optional intake questions where the case file states them (`intake_answers` in
`backtest/inputs.json`):

| Intake question | Cases where the file states it |
|---|---|
| Part of a chain, and how many other locations | 7 (5 chains, 2 not chains) |
| Floor area | 26 |
| How the liquor licence will be obtained (new, transfer from another owner, transfer from another location, already hold a licence at this address, no alcohol) | 6 (1 new, 2 transfer from another location, 3 already hold a licence at the address) |

A skipped question stays skipped: the report then says "Insufficient information" and names what is missing,
exactly as a live user who skips it would see. 30 of the 40 cases answer at least one question. For a chain the files never give the exact number of locations;
where the record calls the use Formula Retail, the answer is "11 or more other locations", which is what that
term means in Planning Code § 303.1.

Two versions are scored on every case:

- **Full report:** rules plus the language model (intake, writer, citation check).
- **Rules only:** no language model at all. The facts are entered by hand (`backtest/inputs.json`, read twice by
  independent readers and settled), the rules set the pathway and every row's status, and the site history and
  counts are printed. The difference between the two is what the model adds.

Each is scored two ways (section 8): **end to end** (from the inputs above) and **conditional** (with the correct
pathway supplied).

## 2. Labels (requirement 1)

- Withdrawn and cancelled cases are **"did not reach approval"**, never "failures".
- For each of the 15 the ground truth records **what the file shows about why** (staff report, continuances,
  letters, related records, a later filing at the address).
- A case counts as a **regulatory problem** only where the file supports that. Otherwise it is **"reason
  unknown"** and is reported in its own group, not scored as a hit or a miss.

What the 15 files show (two independent readings of each file; details and quotes in `cases.yaml` and
`backtest/triggers.json`). No file states a reason in words except N08.

| What the file shows | Cases | Regulatory problem? |
|---|---|---|
| The Conditional Use turned out not to be needed and the project went ahead | N01, N05, N08, N13, N15, and probably N14 | No. The right pathway was "no hearing needed" |
| The use was not permitted at all, so no hearing could cure it | N09 (formula retail limited restaurant, Irving Street) | Yes |
| Dropped after a Notice of Violation; the space was converted to comply | N07 | Yes |
| Application never completed (missing plans, unpaid fee) | N12 | No |
| Withdrawn at the hearing although staff recommended approval | N11 | Unknown |
| Reason unknown | N02, N03, N04, N06, N10 | Unknown, reported separately |

Six of the 15 closed because the hearing was not needed. For those the report is right if it says no
Conditional Use is required. Two are supported as regulatory problems. Six are unknown and are not scored as a
hit or a miss. N08 is stated in the record; the others in the first four rows are inferred from related records
and are marked so.

## 3. Leakage (requirement 2)

Filtering rows by filing date is not enough: most fields are stored as they read today. For every field the
report reads, the table says whether its value was knowable before the case's filing date (the cut-off) and what
the backtest does with it.

Always excluded: the case's own record, and every record at the same address or parcel filed on or after the
cut-off.

| Source | Field | Knowable before the cut-off? | Treatment |
|---|---|---|---|
| Planning record | record number, permit type, address, parcel, filing date | Yes, fixed at filing | Kept for records filed before the cut-off |
| Planning record | status, outcome, decision date | Only if the decision date is before the cut-off. The value on file is today's | Record decided before the cut-off: kept. Otherwise shown as "open at the cut-off", with outcome, status and decision date removed |
| Planning record | description | No guarantee. Staff edit it over the life of a case, and for referrals it often holds the closing note ("Recommend approval…") | Record decided before the cut-off: kept. Otherwise removed |
| Planning record | conditions, decision summary, closing hour, late-night flag, extraction confidence | Only if the motion is dated before the cut-off | Kept only then; otherwise removed |
| Planning record | use types, premises / use / record-kind labels | Derived by us from today's description | Record decided before the cut-off: kept. Otherwise removed (record kind falls back to the permit type) |
| Planning record | zoning district on the record | Today's district at that address | Display only; not used by the rules |
| Planning record | undated rows (no filing date, or closed with no decision date) | Cannot be placed in time | Excluded |
| ABC licence | existence, type, status | The table is today's export: it includes licences issued after the cut-off (possibly to the case's own business) and omits licences since cancelled | Replaced by licences **as they stood at the cut-off**, rebuilt from the Step 1b histories: issued before the cut-off and not ended before it. Status is shown as "active at the cut-off", never today's status |
| ABC licence | density counts (500 ft, 1,000 ft), existing use at the address | Same | Computed from the as-of set |
| ABC | census-tract authorised numbers | Today's figures (September 2026); they move a little each year | Used, labelled "authorised numbers as published in 2026"; the licence count against them is as-of |
| Entertainment Commission permits | everything | The dataset has no dates at all | Excluded from the backtest |
| Registered businesses | name, activity code, bar flag, density | The dataset has start and end dates | Kept only if started before the cut-off and not ended before it |
| Zoning and overlays | district controls, special use district rules | Rules are today's unless dated | The rule table carries effective dates; the rules in force at the cut-off are used, and every case whose controls changed since is listed and graded against the rules at filing |
| Zoning and overlays | district and overlay boundaries | Today's map | Used; a case whose district or overlay was created or redrawn after filing is flagged |
| Address lookup | point, parcel | Today's | Used; flagged where the parcel changed after filing |
| User-reported outcomes | everything | Dated, but the local table is empty | Excluded |
| Permit catalogue | typical times and fees | Today's, not case-specific | Used, labelled as today's figures; not scored |
| Base rate, comparables, site history | everything | Derived from the rows above | Built only from the treated rows |

Three channels that row filtering cannot close:

- **The input text.** The project description on the Planning record often names the approval sought and the
  code section ("Conditional Use Authorization pursuant to Section 754 to establish a Bar"), which hands the
  pathway to the report. Decided 2026-11-10: each case has a **neutral concept text** (`concept_input` in
  `cases.yaml`), and that is the only text the report is given. It keeps what an operator would know before
  applying: what the business is, hours, alcohol type, entertainment, outdoor seating, size, whether it is part
  of a chain, and what the space was last used as. Anything that names the approval, a code section or the
  outcome is removed. Nothing is added: where the description lacks a deciding fact, the report should say
  "Insufficient information", and the case is scored under input coverage. The original description stays in
  the case file (`concept_as_filed`) for audit. A word check rejects approval, section and outcome terms; a
  second reader checks each text against its original for added or dropped facts before the run.
- **The model's own memory.** The language model may have read about well-known cases (the Castro Theatre, case
  D05) in its training data. Those cases are flagged; the rules-only version is immune.
- **Today's licences as evidence of yesterday's use.** Closed by the as-of licence set above.

**The test that proves it** (written before any run):

- For random cut-off dates, every record any data function returns has a filing date before the cut-off; every
  decision date, condition, outcome and description it carries belongs to a record decided before the cut-off;
  every licence was issued before it and had not ended; every business had started and not ended.
- A planted-record test: records carrying a marker string in every answer-bearing field (status, outcome,
  description, conditions, decision summary, licence status, business name), dated on or after the cut-off or
  decided after it, are put in a test store. The marker must not appear anywhere in what the rules read or in
  the text sent to the model.
- The case's own record number and its motion number must not appear in the text sent to the model.

## 4. Timing (requirement 3)

Days are reported separately for **approved**, **withdrawn**, **cancelled** and **still pending** (age so far).
No blended figure appears anywhere, in the backtest results or in the report's own timing lines.

## 5. Report rules in place for the run (requirements 4 to 7)

All built in rule table v2 and tested (each rule cited to the code text, read twice, reviewed, with tests), and
seen working in the five 995 Valencia runs.

- **Over-concentration (4).** A census tract over its authorised number of licences shows on the alcohol row as
  "Further review: public convenience or necessity finding likely required", citing Business and Professions
  Code § 23958.4. It is never a blocker and never "Not permitted" on that fact alone.
- **Change of use (5).** Three separate answers, each with its own rule line: Planning Code change of use
  (§ 102 use categories), Building Code change of occupancy, and neighbourhood notification. No single generic
  answer.
- **Inputs (6).** The alcohol row needs the transaction type (new licence, transfer from another owner,
  transfer from another location, already held) and what alcohol is served. Where the input does not give one,
  the row says "Insufficient information" and names what is missing; nothing is guessed (the intake model may
  not set chain status, the licence route or the occupant count, and never fills what is served). The same
  applies to the last lawful use of the space where the records do not show it. The three optional intake
  questions (chain and number of locations, floor area, licence route) are how a user supplies them.
- **Referral steps (Ordinance 118-25).** A step inside an approval where one agency refers the application to
  another is shown as a step, never as an approval; a removed referral reads as ended, and the permit stays.
- **Limits (7).** Every report states that physical and cost issues (ventilation, exits, accessibility, landlord
  consent) are outside what records can show.
- **Code against practice.** Where the Code text and Planning's own records differ (a restaurant east of Mission
  Street inside the Mission alcohol district), the row reads "Further review: Code and Planning practice
  differ". That case is kept out of the pass/fail count until Planning answers in writing.

## 6. Rule coverage of the 40

The rule table carries the eleven trigger families that caused these hearings (spec section 1a), read from dated
controls so each case is judged by the rules in force at its filing date. Each case was run through the rules
without a model: once on the facts the decision record shows, once on what the neutral text states. Full detail:
[`rule-coverage-of-the-40.md`](rule-coverage-of-the-40.md) and `backtest/coverage.json`, written by
`scripts/validation/backtest_coverage.py`. Figures after the 53 review fixes; the input run does not yet use the
intake answers.

| | Fully covered | Partly | Not covered |
|---|---|---|---|
| Rules, on the decision record's facts | 23 | 11 | 6 |
| - decided (25) | 15 | 8 | 2 |
| - did not reach approval (15) | 8 | 3 | 4 |
| Rules, on the neutral text only | 18 | 7 | 15 |

By trigger: the inventory holds 62 triggers. On the record's facts the rules return 44 with the right control; 9
come back "not decided" naming the missing fact; 4 are not returned; 5 have no rule (three triggers seen once
only, and the formula-retail change-of-operator rule in two cases).

- **Read "Allowed" where a hearing was required:** N01 (an open-air use in the Waterfront special use district)
  and D16 (replacing a Legacy Business). Each has only a trigger with no rule.
- **Not covered for other reasons:** N11 (which outdoor-area limit was exceeded is not in the record), N13 (the
  applicant's own theory, which Planning did not adopt; the rules agree with Planning), and three cases where a
  deciding fact is not in the record.
- **The text, not the rules:** 16 triggers in 11 cases are found on the record's facts and not on the neutral
  text, because the text does not give the deciding fact. These are scored under input coverage. The intake
  answers (section 1) supply some of them.
- **Possible false triggers:** 5 on the record's facts, 2 on the neutral text.
- **Dating the rules matters:** under today's rules instead of the filing-date rules, at least one trigger reads
  differently in 14 cases and the zoning row changes in 9.
- **Uncovered cases stay in the backtest** and count as misses, reported separately.

## 7. Ground truth per case

From the decision record: the pathway required and every trigger; the outcome; every condition; every stated
ground of opposition or denial; days to decision; whether the governing controls changed between filing and
today. For cases that did not reach approval: what the file shows about why.

## 8. Scoring

Every case is scored two ways, and both are reported for the full report and for the rules-only version:

- **End to end:** given only the address, the neutral concept text and the intake answers the case file states.
  This measures the whole chain, including what the input does not say.
- **Conditional:** with the correct pathway supplied: the zoning row is set from the trigger inventory (the
  triggers and controls the decision record shows, at the filing date) instead of from the rules, and the facts
  are the decision record's. This measures what comes after the pathway: the issues flagged, the blockers, the
  conditions, the unsupported sentences. A wrong pathway cannot hide or excuse what follows it.

That is four result sets: full report end to end, full report conditional, rules only end to end, rules only
conditional. The measures below are reported separately in each, never as one score:

| Measure | What counts |
|---|---|
| Critical issues found | An issue that made the use impossible, forced a different pathway, led to withdrawal, or imposed a condition that changed the concept, and that the report flagged |
| Critical issues missed | The same, neither flagged nor listed as unknown |
| Missed pathways | The report named a different pathway from the one the decision record shows, graded against the rules at filing |
| False blockers | A "Potential blocker" or "Not permitted" that the record shows was not one |
| Unsupported findings | Share of sampled cited sentences their cited record does not support |
| Correct "Insufficient information" | The report said it could not tell, and the missing fact was truly not in the input or the records |
| Wrong "Insufficient information" | The report said it could not tell when the input or the records did say |

Results are split by: decided / did not reach approval; rules covered / partly / not covered; controls changed
since filing or not; reason known / reason unknown.

## 9. Outputs

`results/summary.md` with a per-case table and the totals above, and a reviewer packet per case (report PDF,
rules-only sheet, ground truth, blank grading sheet) for a human professional. Each run is tagged
`backtest:<case_id>` with its real token cost and time.

## 10. Cost

Measured on the final code: five 995 Valencia reports run at once on 2026-11-11, with token usage recorded by
stage ([`rule-table-v2-995-valencia.md`](rule-table-v2-995-valencia.md)).

| | Per report |
|---|---|
| End to end (every stage), standard prices | $1.94 average, $2.01 highest |
| Conditional (writer and citation check only; records and comparables reused from the end-to-end run) | $1.32 average |

**The two-way backtest: 40 end-to-end reports and 40 conditional reports, through the Message Batches API at half
price.**

| | Two-way total |
|---|---|
| With prompt caching working as it did in the measured runs | **about $65** (highest run: $67) |
| With no cache hits at all inside the batches | about $83 (highest run: $88) |
| At standard prices, for comparison | about $130 |
| Rules-only version | $0 (no model) |

Caching inside batches is best-effort, so the true figure sits between $65 and $83. Under the budget rule (run it all
this cycle if the two-way backtest is $80 or less through the Batches API), the plan is to **run it all this
cycle**, with a stop:

1. Every request uses the one-hour cache lifetime, and each stage's requests for all 40 cases go in one batch, so
   the shared instructions and records are cached across cases.
2. **Pilot:** 2 cases end to end and conditional through the same batch pipeline (about $4), to check the
   pipeline, the leakage tests and the scoring sheets before spending more.
3. **End-to-end half:** the other 38 cases (about $37 to $47). Its actual cost is read from the API's usage figures.
4. **Conditional half:** run this cycle only if the actual end-to-end cost plus the conditional estimate at the
   same cache rate stays at or under $80. Otherwise it waits for the next billing cycle.
5. Re-runs of a failed case come out of the same $80.

Budget position: validation work has spent about $38.29 of the $130 cap, so $80 of backtest would bring it to
about $118. No step above passes $80 in total or $20 in a single batch without a separate approval. This plan is the
request for the run as a whole.

Time: batches usually finish within an hour each (the API allows up to 24 hours); there are about six stage
batches per half.

## 11. After this plan: a conditions search page (not part of the backtest)

One simple local page to search the conditions of approval already extracted from Planning Commission motions.
Filters: business type, condition category, zoning district, year, case-specific or standard. Each result shows
the condition text, the case and its decision date, and a link to the exact passage in the source motion. No
statuses, no conclusions, no AI summary. Local only at first. It is for showing permit professionals.
Built after this plan is ready.

## 12. What is built and what is not

Built: the 40 cases and their trigger inventory, the neutral concept texts (audited by a second reader), the
hand-entered facts for the rules-only version and the conditional scoring (read twice and settled), the intake
answers from the case files, rule table v2 with dated controls, and the coverage count.

Still to build before the run, with no model spend:

- The cut-off (`as_of`) through every data function, the as-of licence set rebuilt from the Step 1b histories,
  the masking in section 3, and the leakage tests, including the planted-record test.
- The backtest runner (`python -m permit_memo.backtest`) on the Message Batches API, stage by stage, with the
  conditional run reusing the first stages; the scoring sheets; the per-case reviewer packets;
  `results/summary.md`.
