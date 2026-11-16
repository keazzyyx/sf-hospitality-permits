# Label coverage: what the precedent data can and cannot support

Validation Part 1, run 2026-11-09 against the production precedent store (Supabase PostGIS), read-only.
Every number below comes from `scripts/validation/label_coverage.py`, which refuses to run outside a
read-only transaction; its full output is in [`label-coverage.tables.md`](label-coverage.tables.md) and
the raw numbers in `scripts/validation/label_coverage.json`. The hearing hand-check inputs and grades are
in [`hearing-check/`](hearing-check/).

## Summary

- **One approval pathway has usable labelled history: Planning conditional use.** 249 hospitality
  conditional-use cases filed 2019–2026 have a concept, a location, an outcome and a filing date; 61 of
  them failed (withdrawn, cancelled or disapproved).
- **ABC and Entertainment Commission data cannot label anything yet.** Neither source has filing dates,
  and neither can contain a denial or withdrawal. Both have zero complete records.
- **Planning's referral reviews are the best dated evidence for ABC, entertainment and health permits.**
  They are Planning's recommendation on another agency's application, not that agency's decision.
- **Conditions are rare outside the hearing PDFs.** 92 of 1,666 hospitality conditional-use rows carry an
  extracted condition. The "approved with conditions" label in the Planning dataset is inferred from the
  word "condition" in a free-text description and should not be trusted.
- **The hearing extractor is accurate where it looks and blind where it was told not to look.** All 53
  extracted conditions in a random sample of 30 were correct and it missed 1 in-scope condition. It skips
  odour, garbage, lighting and signage conditions by design, and its opposition flag is wrong 17 times in
  30.

## Definitions

- **Hospitality use**: the row's parsed use types include bar, restaurant, cafe, nightclub, live
  entertainment, outdoor seating or retail alcohol. Use types are keyword matches on the description.
- **Pathway** (derived for this report):
  - `planning_cua`: Planning record type CUA.
  - `referral_abc`, `referral_entertainment`, `referral_dph`: Planning "Miscellaneous Permit" records
    whose description is a referral from ABC, the Entertainment Commission or the Department of Public
    Health. The outcome is Planning's recommendation.
  - `planning_other`: every other hospitality Planning record (project review meetings, variances,
    discretionary review, letters of determination, older free-text records).
  - `abc_new` / `abc_transfer`: ABC licences without / with a "From License Number" transfer entry.
  - `entertainment`: the DataSF Entertainment Commission permit set.
- **Outcome**: Planning's raw status mapped to approved, approved with conditions, disapproved,
  withdrawn, cancelled, pending or unknown. The stored outcome folds cancelled into withdrawn; this report
  separates them again from the raw status.
- **Complete record**: hospitality use, a geocoded location, a pathway, a decided outcome (approved,
  approved with conditions, disapproved, withdrawn or cancelled) and a filing date.

## Per source

Hospitality rows only. "Hearing PDFs" are the Planning rows enriched from a Planning Commission motion or
minutes, so they are also counted under Planning.

| Source | Rows | Filing date | Decision date | Approved | Appr. w/ cond. | Disapproved | Withdrawn | Cancelled | Pending | Unknown | ≥1 condition | Parcel |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Planning (all hospitality rows) | 19,658 | 19,658 | 17,344 | 15,872 | 843 | 332 | 262 | 88 | 83 | 2,178 | 253 | 19,497 |
| …hearing PDFs | 97 | 97 | 97 | 84 | 11 | 1 | 1 | 0 | 0 | 0 | 89 | 97 |
| ABC licences (ZIP 94110 only) | 432 | 18 | 414 | 414 | 0 | 0 | 0 | 0 | 18 | 0 | 322 | 403 |
| Entertainment Commission | 657 | 0 | 0 | 657 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

All rows, hospitality or not: Planning 26,510, ABC 439, Entertainment 740, hearing PDFs 381.

Registered businesses: 9,310 rows, 9,139 food or drink, 945 flagged as bars, all with a start date,
2,335 with an end date, 9,073 geocoded. There is no outcome, condition or filing to count.

### Can the source contain a failure?

| Source | Failures possible? | Why |
|---|---|---|
| Planning cases | Yes | Statuses include Disapproved, Withdrawn and Cancelled, and the fetch does not filter on status. |
| Hearing PDFs | Yes | Motions record disapprovals and continuances; minutes record withdrawals. The sample held 1 withdrawal. |
| ABC daily export | No | It lists licences that are active or pending today. A denied or withdrawn application leaves the export. "CANCELED", "EXPIRED" and "SURRENDERED" rows are licences that were granted and later ended, stored as approved. The protest flag is false on all 439 rows. |
| Entertainment Commission (DataSF) | No | Every row is an active permit. No dates, no conditions, no parcel. |
| Registered businesses | No | A register of operating businesses. An end date means the business closed, not that an application failed. |

## Complete records by pathway and filing year

| Pathway | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | Total | Failures |
|---|---|---|---|---|---|---|---|---|---|---|
| Planning conditional use | 48 | 30 | 33 | 29 | 36 | 36 | 28 | 9 | 249 | 61 |
| ABC new | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ABC transfer | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Entertainment | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| *Referral: ABC* | 232 | 114 | 157 | 152 | 193 | 152 | 162 | 96 | 1,258 | 11 |
| *Referral: entertainment* | 49 | 11 | 22 | 24 | 53 | 59 | 37 | 16 | 271 | 10 |
| *Referral: health (DPH)* | 470 | 317 | 264 | 35 | 34 | 69 | 112 | 94 | 1,395 | 15 |
| *Planning, other* | 79 | 28 | 24 | 9 | 7 | 7 | 8 | 11 | 173 | 25 |

Rows in italics are proxies, not decisions on the pathway itself. ABC and Entertainment are zero because
neither source carries a filing date and neither can hold a failure.

Of the 249 conditional-use records, 240 also have a decision date. Their 61 failures are almost all
withdrawals and cancellations: hospitality conditional-use **disapprovals** filed 2019–2026 number one
(2024). Most of the 78 disapprovals on record were filed before 2000.

## Hospitality applications per year

Every hospitality row by filing year, whatever the outcome.

| Pathway | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| Planning conditional use | 48 | 34 | 40 | 31 | 39 | 39 | 30 | 15 |
| Referral: ABC | 232 | 116 | 157 | 152 | 197 | 152 | 163 | 98 |
| Referral: entertainment | 54 | 11 | 22 | 25 | 53 | 59 | 40 | 17 |
| Referral: health (DPH) | 478 | 321 | 267 | 35 | 35 | 72 | 115 | 105 |
| ABC new (pending only) | 1 | 0 | 0 | 1 | 0 | 2 | 0 | 9 |
| ABC transfer (pending only) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 |

The ABC rows with a filing year are the 18 applications pending today. The referral counts are the
closest thing to a citywide count of ABC and entertainment applications, and only for applications that
were referred to Planning.

## Days from filing to decision

Hospitality rows filed 2019 or later with both dates and a decided outcome.

| Pathway | N | Median days | 90th percentile |
|---|---|---|---|
| Planning conditional use | 242 | 192 | 619 |
| …approved | 172 | 186 | 537 |
| …approved, conditions in description | 16 | 102 | 379 |
| …withdrawn | 37 | 311 | 1,039 |
| …cancelled | 16 | 226 | 1,047 |
| Referral: ABC | 1,251 | 14 | 55 |
| Referral: entertainment | 270 | 12 | 28 |
| Referral: health (DPH) | 1,394 | 13 | 37 |
| ABC new / transfer | — | — | — |
| Entertainment | — | — | — |

Referral times measure Planning's review only, not the licensing agency's full process. ABC's
`decided_at` is the licence's original issue date (393 of 420 rows) and there is no filing date to
measure from.

## Hearing extractions: hand-check of 30

A reproducible random sample (seed 20261109) of 30 of the 381 hearing extractions: 28 motions and 2
minutes. Each decision PDF was converted with poppler's `pdftotext`, a different tool from the
extractor's own, and graded against the document by three independent reviewers. I re-read four of
their calls; all four agreed. The extractor targets only operating conditions: hours, entertainment,
security, good-neighbour, noise, alcohol, outdoor space and community liaison.

| Check | Result |
|---|---|
| Extracted conditions that are real and faithful | 53 of 53 |
| …partial or wrong | 0 |
| …off-topic (real, but not an operating rule) | 1 |
| In-scope conditions in the documents | 53 |
| In-scope conditions missed | 1 (case 27, 11B soundproofing) |
| Numbered conditions in the documents, all kinds | 342 |
| Restaurant-relevant conditions skipped by design (odour, garbage, lighting, signage) | 42 |
| Outcome correct | 30 of 30 |
| Closing hour correct | 28 of 30 |
| Opposition flag correct | 13 of 30 |

**Conditions extracted correctly: 53 of 53, with 1 in-scope miss.** Within its scope the extractor is
reliable.

Problems the hand-check found:

- **Opposition flag.** Stored "opposed" was right in 2 of 7 cases. In 4 the document is silent and in 1
  it says nobody objected. In 3 cases the document records opposition and the store holds unknown. In 4
  the document says no comments were received and the store holds unknown instead of false, and in 5
  the store says "not opposed" where the document is silent.
- **Scope gaps.** Odour control, garbage, lighting and signage conditions are routine for restaurants and
  bars and are dropped by design: 42 of them in these 30 documents.
- **Hours lose context.** One stored closing hour is the patio limit, not the business's closing time.
  Another came from Planning Code text quoted in the findings, not from a condition.
- **Conditions by reference.** Two motions carry forward the conditions of an earlier motion that is not
  fetched, so the record looks lightly conditioned when it is not.
- **The sample is mostly not hospitality.** The hearing population is every conditional use in the
  period, so only 5 of the 30 cases are restaurants or bars. Three more were tagged as hospitality by
  keyword (a library relocation, an office amenity and a gym) but are not. The restaurant and bar
  categories were exercised in only 5 documents.

## What this means for Parts 2–4

- A backtest weighted toward failures can draw planning failures from cases filed 2022–2025: 19
  withdrawn, 9 cancelled and 1 disapproved hospitality conditional-use case. Disapprovals in that window
  are far too rare to sample 10.
- ABC "protested or withdrawn" cases do not exist in the current data at all. Part 2's citywide pull and
  the ABC query system will decide whether they can be found.
- Base rates from the current pool would mix grant-only Entertainment rows and undated ABC rows. Part 2
  removes both.
- A hand-check restricted to the 97 hospitality hearing extractions would test the categories that matter
  for this product; this sample barely did.
