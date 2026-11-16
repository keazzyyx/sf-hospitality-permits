# Step 2b: two-field labels, the count that did not add up, and the motion hand check

Run 2026-11-10 on the local copy (`$LOCAL_DATA_DIR`); production was only read. Tables:
[`label-coverage-step2.tables.md`](label-coverage-step2.tables.md), regenerated with
`scripts/validation/label_coverage.py --local`. This supersedes the counts in
[`step2-corrections.md`](step2-corrections.md).

## 1. Labels: premises and record kind

`scripts/validation/classify_records.py` relabelled all 26,510 Planning records through the Message Batches
API (`claude-haiku-5-5`, cached system prompt): **$0.43**. Each record now has:

- **premises**: is the record about one space that is, or is meant to be, a restaurant, cafe, bar, venue or other
  food-and-drink business? A kitchen hood at an operating restaurant is yes; a whole-building project with a
  ground-floor restaurant is no.
- **use class**: restaurant or cafe, bar, nighttime entertainment, other food and drink (liquor stores, grocery
  with alcohol, catering, hotels).
- **record kind**: use decision, agency referral, building work, other.

Pathway counts and the backtest use only premises records that are **use decisions or agency referrals**.
Building work is kept for the site-history part of the report.

| Premises records | Records | Addresses | Filed 2019 on |
|---|---|---|---|
| Agency referral | 15,110 | 10,429 | 3,037 |
| Use decision | 2,962 | 2,374 | 658 |
| Building work | 831 | 705 | 444 |
| Other (project review meetings, complaints) | 213 | 199 | 69 |

(Counted before the cannabis and gym rule below, which removed 21 premises records.)

The two wrong-class cases are fixed: the Marker Hotel's licences are now other food and drink, and the Type 41 at
1233 Van Ness is a restaurant. The foot-massage case and the supermarket alteration are now not premises.

**Correction to my Step 2 hand check.** I called 2298 Market St a miss ("renovate existing restaurant for new
non-formula retail operator"). It is a restaurant: "non-formula retail" only means the operator is not a chain.
The Step 2 hospitality sample was 48 of 50 right, not 47.

### Re-check, 30 + 30

**30 random records labelled premises (seed 0.20261112):** premises right on 30 (1 borderline: a health referral
for a limited restaurant inside The RealReal's store), use class right on 30, record kind right on 30.

**30 random records labelled not premises, from the 694 that mention food, drink, bar, restaurant or
entertainment (seed 0.20261113):** 26 right, 2 clear misses, 2 borderline.

| # | Record | Why |
|---|---|---|
| 4 | "Place of Entertainment and Extended Hours… is a permitted use" (referral) | Miss: an Entertainment Commission referral |
| 19 | 395 South Van Ness, Syzygy Academy, "EC referral - Limited Live Performance" | Miss: an Entertainment Commission referral |
| 8 | 1259-61 Folsom, convert three dwellings to a ground-floor restaurant and workshops | Borderline: mixed project |
| 26 | Google, Inc., "full service restaurant permitted" (referral) | Borderline: reads as a restaurant referral; likely a staff cafeteria |

Both misses are Entertainment Commission referrals, so I added a rule: an agency referral whose text names an
entertainment permit is a premises record in the entertainment pathway (33 records changed).

The motion hand check below then showed a second pattern the 30 + 30 did not catch: cannabis shops and a Pilates
studio labelled "other food and drink". A second rule removed them: cannabis or fitness records with no food or
drink terms are not premises (21 records changed, 16 of them conditional uses).

## 2. The count that did not add up

Both Step 2 tables were right; they counted different sets.

- **198 complete records** required a geocoded location and did not require a decision date.
- **193 in the timing table** required a decision date and did not require a geocoded location.
- 7 of the 198 had no decision date (5 of them failures: withdrawn or cancelled cases Planning never closed out),
  which left 191; 2 approvals without a geocode were in the timing table, which made 193.
- The failures followed the same split: 51 = 46 with a decision date + 5 without.

The timing tables now use the complete-records set, and the tables file has a reconciliation table. With the new
labels and rules:

| | Complete records, filed 2019–2026 | Failures |
|---|---|---|
| Conditional use, all | 170 | 47 |
| …with a decision date (used for timing) | 162 | 41 |
| …no decision date | 8 | 6 |

| Outcome (with a decision date) | N | Median days | 90th percentile |
|---|---|---|---|
| Approved with conditions | 119 | 173 | 414 |
| Withdrawn | 28 | 313 | 965 |
| Cancelled | 13 | 145 | 886 |
| Approved, no conditions listed | 2 | — | — |
| **All** | **162** | **178** | **539** |

119 + 28 + 13 + 2 = 162, and 28 + 13 = 41. There is no hospitality conditional-use disapproval filed since 2019;
the two earlier candidates were a Pilates studio and a cannabis shop.

| Pathway | Complete records | Failures | Median days | 90th pct | N (timing) |
|---|---|---|---|---|---|
| Conditional use | 170 | 47 | 178 | 539 | 162 |
| Other use decisions (variances, change of use, letters) | see tables | | | | |
| Referral: ABC | 1,250 | 11 | 14 | 55 | 1,240 |
| Referral: entertainment | 271 | 10 | 12 | 28 | 270 |
| Referral: health | 1,375 | 15 | 13 | 37 | 1,373 |
| ABC new or transfer, Entertainment permits | 0 | 0 | — | — | — |

Hospitality conditional-use applications by filing year: 2019 39, 2020 21, 2021 30, 2022 19, 2023 21, 2024 24,
2025 18 (2026 is in the tables file).

**Backtest pool** (conditional uses filed 2022–2025): 54 approved with conditions, every one with its motion's
conditions extracted; 15 withdrawn; 6 cancelled. That is 21 failures and no disapproval.

## 3. Hand check of 20 motions

20 random motions from the full-conditions pass (seed 20261110). Each PDF was converted with poppler and read by
one reviewer; a second reviewer then tried to refute every finding and re-counted the conditions. 15 first-reader
claims were refuted and dropped. Sample and grades: `hearing-check/motion-check-*.json`.

| | First extraction | After the fixes below |
|---|---|---|
| Conditions in the 20 documents | 292 | 292 |
| Extracted | 270 | 291 |
| **Missed** | **22** (21 of them operating conditions) | **1** |
| **Invented** | **0** | 0 |
| Text that changes the meaning | 5 | not re-graded |
| **Standard flag wrong** | **40 of 270** (all flagged case-specific, really boilerplate) | 24 of 268 |
| Motion outcome read correctly | 19 of 20 | 20 of 20 |

What was wrong, and what I changed:

- **Missed conditions: one bug.** The "Eating and Drinking Uses" condition has lettered sub-items; the extractor
  deleted everything after the first "For information about compliance…" line, so sub-items C (odour) and D
  (garbage) were lost on every restaurant motion, and parenthesised sub-items "(B)…(G)" were not split at all.
  Fixed in the extractor itself (it also affected production's hearing extraction: this is the soundproofing miss
  from Part 1). Re-extracting from the cached PDFs recovers 21 of the 22; one "Validity" condition is still
  missed.
- **Standard flag: the rule was too strict.** I had flagged a condition standard when its *title* was on half the
  approvals for that use. PDF spacing glitches split titles ("Revocation due to Viola tion"), and boilerplate
  under a less common title counted as case-specific. The flag now uses the wording: the same opening text under
  the same title on five or more motions is standard. Agreement with the reviewers rose from 85% to 91%. Of the
  24 remaining disagreements, 20 are boilerplate the new rule calls standard and the reviewers left as
  case-specific (garbage storage, odour control units, cannabis licence conditions; the reviewers were not
  consistent with each other on these), and 4 are the other way (a Signage condition with unusual wording, three
  liquor-store sub-items).
- **Text errors (5).** Four are the 600-character clip cutting a long condition's last sentences; one was the
  sub-item bug. Not fixed: the clip is deliberate, and the full text is in the PDF the citation links to.
- **Outcome.** One motion read as unknown because the PDF text split the verb ("hereby AP PROVES"). Fixed.
- **Use labels.** 2 of the 20 were cannabis shops and 1 a Pilates studio, which led to the rule in section 1.

After the fixes, for hospitality conditional uses decided since 2019:

| | Cases |
|---|---|
| In scope | 142 |
| Motion found | 140 |
| Motion with conditions | 139 |
| Conditions extracted | 2,096 (1,866 standard, 230 case-specific) |

The 230 case-specific conditions are mostly hours, entertainment, signage, alcohol and outdoor-area terms.
