# Holdout re-run, 2026-11-16

Written by the AI agent (Claude) that ran the re-run; "I" below is that agent.

The 20 frozen holdout cases were run again at 22501ef (the head of spelling-and-intake-questions). There were four arms: two sets of ABC licences (the full as-of set, and 94110 only) crossed with two intake models (the product's Sonnet 4.5 and Opus 5.5). No rules were changed and the test set was not fitted. Two model runs were paid for, $0.93 in total.

## In short

- **The ABC licence gap in production did not affect the backtest, and on these 20 cases it moved no score.** The backtest never reads today's `abc_license` table. When licences are restricted to 94110 (the only ZIP production had loaded), every scored measure stays the same in every case, under both intake models. The reports' text does get worse: nearby-licence counts drop to 0 in 14 cases, three cases lose the licence at the address, and three lose the tract-concentration lines. The scorer does not measure any of that.
- **Main arm (product intake, full licences): 12 of 20 cases are materially unsafe end to end (60%), and 7 of 28 critical issues are found (25%).** With the record's facts supplied (conditional), it is also 12 of 20 (60%).
- **Opus 5.5 as the intake model did worse here: 14 of 20 unsafe end to end (70%) and 5 of 28 found.** Some of the gap comes from the product's stated-facts check clearing Opus's answers, not from Opus misreading.
- **Against 2026-11-12, the unsafe counts are about the same.** 22501ef lacks the 2026-11-12 rule fixes, and that shows in two cases (H09, H17). Intake changes since then fixed H04.
- **Double-check:** four independent AI reviewers (Claude agents, not people) re-scored all 20 cases, reading the labels and reports rather than running the scorer. They agree with the scorer on 36 of the 40 main-arm case-by-set safety verdicts (20 cases, full e2e and full conditional). The other 4 verdicts fall in three cases. This write-up sides with the reviewers on H14 and H15 end to end, both counted as "unknown" when they are really misses. It sides with the scorer on H04, where the reviewer disputed both the e2e and conditional verdicts. On the stricter reading, full end-to-end unsafe is **14 of 20 (70%)**, not 12. Both numbers are given below.
- **N = 20.** One case is 5 percentage points. The 95% range on 12 of 20 runs from about 39% to 78%. Differences of one or two cases between arms or dates are not evidence of a real change.

## 1. What was run

**Code.** 22501ef, the head of `spelling-and-intake-questions`, run from a separate worktree. This commit does **not** contain the 2026-11-12 rule fixes: 0b73d1c (rule-fixes) is not an ancestor, and the scorer's ADDED_RULES mapping is absent. `backtest/holdout/cases.yaml`, `inputs.json` and `triggers.json` are byte-identical to b14f560, where the test set was frozen; only the README differs. Nothing under `apps/api/app/memo/` was edited.

**Harness-only change.** A separate commit, 448d260, touches only `app/backtest`:
- `run.py` gains `--intake-model` and `--licences-file`. For Opus 5.5 it sends no temperature and uses tool_choice auto, as apps/api/.env advises for that model.
- `batch.py` gains Opus 5.5 prices.

**Each run does exactly what 2026-11-12 did.** That is four result sets per arm:
- rules only, end to end (hand-entered facts);
- rules only, conditional (the record's facts and pathway supplied);
- full, end to end (intake is the only model call, through Message Batches with one-hour caching);
- full, conditional (no model call).

**Arms.**

| | Full as-of licences (`licences_asof.json`, 5,505 files) | 94110 only (603 files) |
|---|---|---|
| Intake: product (claude-sonnet-4-5-20250929) | **main arm** | answers replayed from the journal, $0 |
| Intake: Opus 5.5 (claude-opus-5-5, API default effort) | paid run | answers replayed from the journal, $0 |

**Why the ABC fix cannot move the FULL arm.** This was checked in the code and in a test run.
- **Code.** `AsOfStore.mask_application` returns None for every `abc` row, so the database's `abc_license` rows are dropped. Licence reads (nearby, at the address, by kind) come only from `licence_set(as_of)`, which is built from `licences_asof.json`. Tract active counts are computed from that same set. Only the tracts' authorised numbers come from the bundled `sf_tract_licences.json`.
- **Test run.** A rules-only run with an *empty* as-of licence file gave 0 licences within 1,000 ft in all 40 rules-only results, and no `abc:` id anywhere. That held although the local database holds 3,949 `abc_license` rows across 29 ZIPs.
- All 14 licence ids cited in the FULL results are in `licences_asof.json`.
- **Coverage of the as-of file.** The "30 ZIPs" count includes a blank. The file has 28 SF ZIPs, plus 94609 (Oakland) and 94518 (Concord) with one file each. Another 1,953 files have no ZIP: these are licences that ended after 2021 and are not in today's export.

So production loading only 94110 never affected the backtest. Fixing production's table changes nothing here.

**How the 94110 arm was built** (`scripts/validation/make_licences_94110.py`). It keeps the 398 files with ZIP 94110. It also places 205 no-ZIP files in 94110, using these steps in order:
1. a zipped file at the same normalised address (145);
2. ABC's export at the same premises address (6);
3. a registered business at the same street address (33);
4. the majority ZIP of the 5 nearest zipped files (21).

64 no-ZIP files had no address match and no map point. They were left out.

The licences, the at-address check, the unknown-status line, the unknown-as-active sensitivity check and the tract counts are all rebuilt from this one set. **Caveat:** production took its tract counts from the bundled file, not from `abc_license`, so on tract figures this arm is harsher than production was.

## 2. The four tables (scorer's numbers; 20 cases, 28 critical issues)

The FULL and 94110 arms give identical tables under both intake models, so each table stands for both licence arms.

**Table 1: product intake (main arm). sonnet-full = sonnet-94110**

| Measure | Full e2e | Full conditional | Rules e2e | Rules conditional |
|---|---|---|---|---|
| Critical issues found | 7 (25%) | 7 (25%) | 6 (21%) | 7 (25%) |
| Listed as unknown, naming the missing input | 8 | 6 | 6 | 6 |
| Missed or a different control | 13 (13+0) | 15 (14+1) | 16 (15+1) | 15 (14+1) |
| Materially unsafe cases | 12 (60%) | 12 (60%) | 13 (65%) | 12 (60%) |
| False blockers | 0 | 2 rows in 1 case (H05) | 6 rows in 2 cases (H05, H09) | 2 rows in 1 case (H05) |

**Table 2: Opus 5.5 intake. opus-full = opus-94110**

| Measure | Full e2e | Full conditional | Rules e2e | Rules conditional |
|---|---|---|---|---|
| Critical issues found | 5 (18%) | 7 (25%) | 6 (21%) | 7 (25%) |
| Listed as unknown, naming the missing input | 5 | 6 | 6 | 6 |
| Missed or a different control | 18 (17+1) | 15 (14+1) | 16 (15+1) | 15 (14+1) |
| Materially unsafe cases | 14 (70%) | 12 (60%) | 13 (65%) | 12 (60%) |
| False blockers | 6 rows in 2 cases (H05, H09) | 2 rows in 1 case | 6 rows in 2 cases | 2 rows in 1 case |

Only the full e2e column depends on the intake model. The other three make no model call and are the same in both tables.

**Stricter reading after the double-check (section 6).** It counts H14 and H15 end to end as misses instead of "unknown". The scorer's figure comes first, then the stricter one. The conditional columns do not change.

| Measure | Product, full e2e | Product, rules e2e | Opus, full e2e |
|---|---|---|---|
| Listed as unknown | 8 → 6 | 6 → 4 | 5 → 4 |
| Missed or a different control | 13 → 15 | 16 → 18 | 18 → 19 |
| Materially unsafe cases | 12 (60%) → **14 (70%)** | 13 (65%) → **15 (75%)** | 14 (70%) → **15 (75%)** |
| H14 only (the firm one) | 13 (65%) | 14 (70%) | 15 (75%) |

**Presentation note (H20; section 6).** H20 has a "special use district" item whose control at filing is "unclear". The scorer counts it among the 28 and as missed in every set. It never makes a case unsafe. Leave it out, and the denominator is 27. For example, product full e2e then reads 7 of 27 found (26%) and 12 missed.

## 3. 94110 vs full: what the production gap cost on these 20 cases

**Scored: nothing.** Across all four result sets and both intake models, no trigger result, safety verdict, false blocker, pathway, row status or "insufficient information" entry changes. I re-checked this directly against both arms' `scores.json`. The four 94110 cases (H01, H02, H10, H12) are identical line for line.

**Unscored: the reports get factually worse.**
- **Nearby licences.** Licences within 500 and 1,000 ft drop to 0 in 14 cases: H03, H04, H05, H06, H08, H09, H11, H13, H14, H15, H16, H17, H19, H20. H07 already had 0. H18 (3065 16th St, next to 94110) drops from 35/66 to 16/27. A reader would be told there are no licences nearby when there are dozens.
- **Licence at the address.** H06, H08 and H17 lose the licence at the address. For example, H08 (1423 Polk) goes from "an active Type 48 is on file, read as a Bar" to "no active ABC licence on file".
  - Knock-on effects: in H08 and H17 the laundromat check (T8) turns from "not a laundromat" to "not decided", and the zoning status line adds "removal of a laundromat".
  - In H08 conditional, the change-of-use line now rests on the stated use, not the licence.
  - No laundromat item is in these cases' inventories, so no score moves.
- **Tract concentration.** The "tract over its authorised number" lines disappear in H14, H15 and H18 (conditional sets; also H14 full e2e under Opus). The alcohol row status is unchanged.
- **Unknown-status licence line.** It changes, usually to "none", in 10 cases. The scorer's "licence status unknown at the address" group has 1 case (H14, licence 523357) in FULL and 0 in 94110.

**Why no score moves.** No inventory item in the 20 cases turns on the nearby counts, the licence at the address or tract concentration. The restricted-district liquor rule (T4) reads the district, not the licences. This is a limit of the test, not proof that the gap was harmless. A case where an existing licence decides the pathway would have been exposed, and none of these 20 is that kind of case.

Diff files: `compare-{sonnet,opus}-full-vs-94110.txt` and `linediff-{sonnet,opus}-full-vs-94110.txt`.

## 4. Product intake vs Opus intake (full e2e only; the same under both licence arms)

Opus is worse on these cases: 5 found against 7, and 14 unsafe against 12. Case by case:

| Case | Product (Sonnet) | Opus | What happened |
|---|---|---|---|
| H11 | changing conditions **found**; safe | **missed; unsafe** | Opus left `amends_prior_approval` unset. Its `changes_existing_business=intensify` was then cleared by the stated-facts check: the check's pattern wants "longer hours", and the text says "longer delivery hours". Sonnet's find rested on `amends_prior_approval` and `closing_hour` values that the scorer lists as *assumed*, not stated. |
| H15 | Haight liquor rule **unknown**; safe | **missed; unsafe** | Opus read "sells liquor to take away" as `serves_alcohol=false`, so there is no alcohol row and T4 says "not described as serving alcohol". The input facts say `serves_alcohol=true`. This is a genuine reading difference about whether take-away sales count as "serving". |
| H17 | changing conditions **found**; unsafe (enlarge missed) | changing conditions **missed**; unsafe | Opus set `amends_prior_approval=true`, but its quote ("wants the cap on large entertainment events raised from 79 to 91") has none of the cue words `app/memo/stated.py` requires, so the check cleared it. |
| H05 | unsafe (landmark missed; nighttime entertainment and outdoor area "unknown") | unsafe, plus 3 false-blocker rows | Opus set `live_entertainment=false` although the text says "nighttime entertainment". It kept the rear outdoor area, so T9 returns not permitted (a different control) and three rows read not permitted. **This is the same result rules-only e2e gives on the hand-entered facts.** Sonnet escaped it partly because the stated-facts check removed its correct `outdoor_area` ("front and rear gardens"), which leaves "where the outdoor area is" as a wrong "insufficient information". |
| H09 | unsafe (Legacy Business rule missed); no false blocker | unsafe, plus 3 false-blocker rows | Opus read the existing use as a limited restaurant, as the input facts do. With the proposed use read as a Restaurant, the North Beach prior-use note makes T1 not permitted, and zoning, health and building all read not permitted. **Again identical to rules-only e2e on the hand-entered facts.** Sonnet avoided the blockers because it missed the existing use. The Opus memo also contradicts itself: it lists first-story conditional and second-story not permitted, then says "the table reads the same for a Restaurant on every story". |

What this does and does not show:
- In H11 and H17, part of Opus's loss is the product's own stated-facts check clearing Opus's values on narrow cue words.
- In H05 and H09, Opus reproduces what the rules do with the correct facts. Sonnet's better score there comes from losing facts.
- Only H15 is a plain Opus misread.
- So this is not evidence that Opus reads worse in general. It does show that swapping the intake model, without touching the stated-facts check and the rules, would not have improved these 20 cases.
- Intake rows: Opus 11 misread and 6 assumed, against Sonnet's 12 and 8.

## 5. Comparison with 2026-11-12

**Rule-fixes branch, 2026-11-12, against 22501ef today (product intake).** Each cell gives found / unknown / missed or different control / unsafe / false blockers.

| Set | 2026-11-12 (rule-fixes) | 2026-11-16 (22501ef, no rule fixes) |
|---|---|---|
| Full e2e | 6 (21%) / 8 / 14 / 12 (60%) / 3 rows in 1 case (H05) | 7 (25%) / 8 / 13 / 12 (60%) / 0 |
| Full conditional | 7 (25%) / 7 / 14 / 11 (55%) / 2 rows in 1 case | 7 (25%) / 6 / 15 / 12 (60%) / 2 rows in 1 case |
| Rules e2e | 5 (18%) / 8 / 15 / 13 (65%) / 6 rows in 2 cases | 6 (21%) / 6 / 16 / 13 (65%) / 6 rows in 2 cases |
| Rules conditional | 7 (25%) / 7 / 14 / 11 (55%) / 2 rows in 1 case | 7 (25%) / 6 / 15 / 12 (60%) / 2 rows in 1 case |

**Local main without the rule fixes, rules only (2026-11-12):** e2e 6 found and 13 unsafe (65%); conditional 7 found and 12 unsafe (60%). Today's rules-only numbers reproduce this exactly, as they should at a commit without the fixes.

**Every case-level change from the stored 2026-11-12 scores** (checked against `scores-2026-11-12.json`):
- **H04, full e2e: formula retail goes from missed to found, so the case turns safe.** In rules e2e it goes from unknown to found. This comes from intake and input-question changes since 2026-11-12, not from rules.
- **H09, e2e sets: the Legacy Business replacement rule goes from unknown to missed (no rule).** The case turns unsafe in full e2e; it was already unsafe in rules e2e through its false blockers. This is one of the absent rule fixes.
- **H17, conditional sets: enlarging or intensifying goes from unknown to missed, so the case turns unsafe.** This is the other absent rule fix.
- **H05, full e2e: the outdoor area goes from a different control to unknown, and the 3 false-blocker rows disappear.** It is still unsafe because of the landmark issue. This is not a real improvement: the stated-facts check now clears the stated rear-garden outdoor area, so the report asks for a fact the description gives.

So the unsafe count in full e2e is unchanged (H04 out, H09 in), and each conditional set gains H17. With the rule fixes merged, H09 and H17 would be expected to return to "unknown". That would leave full e2e at about 11 of 20 and the conditional sets at about 11. This is an expectation, not a measurement.

## 6. Double-check result

Four AI reviewers (Claude agents, not people) each took five cases (H01–H05, H06–H10, H11–H15, H16–H20). Each read the frozen labels, inputs and memo JSON, and made their own calls before opening the scorer's output. None ran a model or edited the repo.

**Agreement.** Reviewers agreed with the scorer's safety verdicts on 36 of the 40 main-arm case-by-set verdicts (20 cases × full e2e and full conditional). The 4 others are H04 (both sets), H14 e2e and H15 e2e. They also agreed on all false-blocker and pathway calls. They found ARM 94110 changes no verdict.

**Disagreements, and my decision on each.** I read the memo and the labels myself in every case.

1. **H04: two formula-retail entries scored as one item (reviewer: unsafe; scorer: found).**
   - **Decision: the scorer is right under the frozen method.**
   - `cases.py:inventory_from_triggers` makes "one item per family; two entries of one family are one item with the more severe control". The 40 were scored the same way: N09, D05 and D14 each have two entries in one family in `backtest/coverage.json`. Both H04 entries are conditional, T5 returned conditional, so the item is found.
   - The second entry (change of a formula-retail operator, § 178(c)(3) and § 303.1(j), inferred from code) has no rule. The memo has only an unevaluated note on it: "a change of owner or operator of an existing formula retail business needs a new Conditional Use in the cases Planning Code § 178(c)(3) lists".
   - Counted per entry instead, there would be 29 issues, and H04 would be unsafe in all four sets (full e2e 13 of 20). I do not adopt that, because it would change the method from the 40's. In practice the report already sends this concept to a Conditional Use hearing.
2. **H03: "unknown" on an input the description gives (reviewer caveat; the reviewer's full note on this point was not kept).**
   - **Decision: the scorer's "unknown" stands, with a caveat.**
   - The description says "an existing liquor store", yet T1 asks "what kind of business it is". The scorer already counts that as a wrong "insufficient information".
   - The rule table has no Liquor Store use (only Bar, Restaurant, Limited Restaurant and Nighttime Entertainment). So no answer would let T1 decide, but the report never gives an all-clear either.
3. **H14 end to end: "unknown" is really a miss (reviewer, firm).**
   - **Decision: I agree with the reviewer. The scorer applied its rule mechanically, and the result is wrong in substance.**
   - The record's issue is the Liquor Store control (723 Table, Liquor Store: C) for the package store in the front of the bar. The report reads the use as a Bar only, and no line mentions a liquor or package store.
   - T1 is undecided only on whether the bar stays (`T1.maybe_continues`, missing "whether an existing business is to be enlarged or intensified").
   - Either truthful answer goes wrong. If the bar stays, the conditional run shows what follows: "A Bar already exists at this address and continues, so the control for a new use was not applied" (does not apply). If it is intensified, the result is an enlargement control, a different control.
   - The same lines appear in rules e2e and in Opus e2e. Corrected numbers are in section 2.
4. **H15 end to end: "unknown" is really a miss (reviewer, weaker).**
   - **Decision: I agree, and keep the reviewer's "weaker" label.**
   - The undecided T4 line is the *on-sale* rule (Types 40, 41, 42, 47, 48, 57). The concept is off-sale ("to take away").
   - Given the record's licence (Type 21), the conditional run says "Type 21 … is not one of the licence types this rule reaches … so it was not applied" (principal). Answering the question truthfully therefore produces a miss.
   - It is weaker than H14 because the line names § 781.9(c)(2), the Haight Alcohol RUSD and "Conditional Use", and the zoning row already reads further review (through use size). A careful reader is pointed at the right section.
5. **H18 end to end: borderline "unknown" (reviewer agrees with the scorer).**
   - **Decision: keep "unknown".**
   - The question asks what kind of business it is. The concept says general entertainment, which the rule table does not cover, and the zoning row says so ("Use authorization (not covered by the rule table)").
   - The conditional run misses because the record's facts frame the case as a continuing restaurant. It is not shown that a truthful answer end to end would give an all-clear.
6. **H20: the "unclear" control counted as a missed critical issue (reviewer).**
   - **Decision: the scorer follows the 40's practice of counting every inventory item.** The 40's 62 included 2 items that needed nothing, and the unsafe count correctly leaves this one out.
   - Calling it "missed" overstates, though: the record does not show that it needed anything. The 40 had no "unclear" item, so this path was untested. The 27-issue figures are in section 2.
7. **Intake labels, H07 and H06 (reviewer; no safety effect).**
   - **H07: the reviewer is right.** The model read the existing use correctly (`["other"]`), and the product's stated-facts check removed it. The scorer's "misread" row compares the profile *after* that check.
   - Across product full e2e, 5 of the 12 "misread" facts are fields the check cleared: H03, H05 ×2, H07, H19. Under Opus it is 5 of 11. Read that row as "intake plus stated-facts check", not "the model".
   - **H06:** `outdoor_seating=true` filed as "assumed" is a fair label quibble; the text says "its outdoor activity area". No change.

Reviewers also noted two things that are not scoring issues:
- **H13 conditional:** the memo carries two answers under one rule id. The `pathway.lines` copy of `T4:haight.new_on_sale_establishment` says "a conditional use", while the trigger's own line says not decided.
- **H11 end to end:** the issue was found only because the model filled `amends_prior_approval`, which the settled reading of the text leaves blank.

**A pattern the 40 did not show.** The 40's write-up says "no case is safe end to end and unsafe in the conditional run". Here, three are: H14, H15 and H18. In each, the end-to-end report defers ("unknown"), and given the record's facts the rules then miss. That is why the stricter reading matters for the holdout.

## 7. Per-case results (full licences; the 94110 arm is identical on every scored item)

Results for each case's critical issues, in the order listed.

| Case | Address, district | Critical issues | Full e2e (product) | Full conditional | Rules e2e | Rules conditional | Full e2e (Opus) |
|---|---|---|---|---|---|---|---|
| H01 | 2999 Mission St, NCT-MISSION | Liquor licence rule of a restricted district | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) |
| H02 | 3400 Cesar Chavez St, NCT-MISSION | Liquor licence rule of a restricted district | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) |
| H03 | 1657 Powell St, NCD-NORTH BEACH | Use control of the zoning district | unknown (safe) | unknown (safe) | unknown (safe) | unknown (safe) | unknown (safe) |
| H04 | 3352 Steiner St, NC-2 | Formula retail | found (safe) | found (safe) | found (safe) | found (safe) | found (safe) |
| H05 | 2007 Franklin St, RH-2 | Landmark use in RH / Nighttime entertainment / Outdoor activity area | missed / unknown / unknown (**unsafe**) | missed / missed / different control (**unsafe**, 2 false-blocker rows) | missed / missed / different control (**unsafe**, 3 rows) | missed / missed / different control (**unsafe**, 2 rows) | missed / missed / different control (**unsafe**, 3 rows) |
| H06 | 620 Jones St, RC-4 | Changing conditions / Enlarging or intensifying | found / missed (**unsafe**) | found / unknown (safe) | found / missed (**unsafe**) | found / unknown (safe) | found / missed (**unsafe**) |
| H07 | 225 San Leandro Way, RH-1(D) | Landmark use in RH | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) |
| H08 | 1423 Polk St, NCD-POLK | Changing conditions / Enlarging or intensifying | found / missed (**unsafe**) | found / unknown (safe) | found / missed (**unsafe**) | found / unknown (safe) | found / missed (**unsafe**) |
| H09 | 786 Lombard St, NCD-NORTH BEACH | Legacy Business replacement | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**, 3 rows) | missed (**unsafe**) | missed (**unsafe**, 3 rows) |
| H10 | 999 Valencia St, NCT-VALENCIA | Liquor licence rule of a restricted district | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) |
| H11 | 1301 Van Ness Ave, RC-4 | Changing conditions | found (safe) | found (safe) | missed (**unsafe**) | found (safe) | missed (**unsafe**) |
| H12 | 3233 22nd St, NCT-MISSION | Use control of the zoning district / Use control of a special use district | unknown / found (safe) | unknown / found (safe) | unknown / found (safe) | unknown / found (safe) | unknown / found (safe) |
| H13 | 1457 Haight St, NCD-HAIGHT | Liquor licence rule of a restricted district | missed (**unsafe**) | unknown (safe) | missed (**unsafe**) | unknown (safe) | missed (**unsafe**) |
| H14 | 1548 California St, NCD-POLK | Use control of the zoning district | unknown (safe); **stricter: missed, unsafe** | missed (**unsafe**) | unknown (safe); **stricter: missed, unsafe** | missed (**unsafe**) | unknown (safe); **stricter: missed, unsafe** |
| H15 | 1416 Haight St, NCD-HAIGHT | Liquor licence rule of a restricted district | unknown (safe); **stricter: missed, unsafe** | missed (**unsafe**) | unknown (safe); **stricter: missed, unsafe** | missed (**unsafe**) | missed (**unsafe**) |
| H16 | 1210 9th Ave, NCD-INNER SUNSET | Formula retail | found (safe) | found (safe) | found (safe) | found (safe) | found (safe) |
| H17 | 1111 California St, RM-4 | Changing conditions / Enlarging or intensifying | found / missed (**unsafe**) | found / missed (**unsafe**) | found / missed (**unsafe**) | found / missed (**unsafe**) | missed / missed (**unsafe**) |
| H18 | 3065 16th St, NCT-VALENCIA | Use control of the zoning district | unknown (safe; borderline) | missed (**unsafe**) | unknown (safe) | missed (**unsafe**) | unknown (safe) |
| H19 | 906 Broadway, RM-2 | Landmark use in a residential district | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) | missed (**unsafe**) |
| H20 | 1567 Sloat Blvd, NC-S | Formula retail / Hours / Special use district ("unclear") | missed / unknown / missed (**unsafe**) | missed / unknown / missed (**unsafe**) | missed / unknown / missed (**unsafe**) | missed / unknown / missed (**unsafe**) | missed / unknown / missed (**unsafe**) |

**What the misses come from (main arm, full e2e):**
- **No rule at all:** landmark use in a residential district, § 186.3 (H05, H07, H19), and Legacy Business replacement (H09).
- **A rule that asks nothing where the record shows a Conditional Use:**
  - the § 249.60(b)(2)(A) Mission Alcohol SUD rule, where the report only gives the § 249.60(d) good-neighbour line (H01, H02, H10);
  - enlarging or intensifying (H06, H08, H17).
- **An input problem:** alcohol not in the text (H13).
- **Formula retail not applied** because the concept has no covered use (H20, "A Crumbl Cookies location.").

## 8. Costs

Exact figures, computed from the usage in each journal (re-summed for this write-up). Batch pricing is half price, and one-hour cache writes are billed at 2x.

| Run | Model | Requests | Input + cache write + cache read | Output | Cost |
|---|---|---|---|---|---|
| Intake, product arm (FULL) | claude-sonnet-4-5-20250929 | 24 in 3 batches | 52,911 + 23,718 + 260,578 | 25,885 | **$0.3837** (2026-11-12: $0.3883) |
| Intake, Opus arm (FULL) | claude-opus-5-5 | 21 in 2 batches | 55,510 + 32,787 + 311,011 | 27,059 (thinking included) | **$0.5439** ($0.575 if cache reads cost 0.1x) |
| Both 94110 arms | (journal replay) | 0 | 0 | 0 | $0 |
| **Total** | | | | | **$0.93** |

The pre-run ceilings were about $1.3 (Sonnet) and $1.5 (Opus), so no job came near the $50 single-job review line. The runs are logged in `docs/validation/spend.md`. Scoring and all checks used no model.

## 9. Caveats

- **N = 20 cases, 28 issues.** One case moves the unsafe rate by 5 points.
  - The 95% range on 12 of 20 is roughly 39%–78%.
  - The product vs Opus gap (2 cases) and the 2026-11-12 vs today changes (0–1 cases per set) are within noise.
  - Read the per-case causes, not the percentages.
- **Not a test of the 2026-11-12 rule fixes.** 22501ef does not contain them. A holdout run on a commit with the fixes merged is still needed for the number that matters.
- **Comparison with the 40.** `docs/validation/backtest-results.md` reports 15 of 40 unsafe end to end (38%) and 9 of 40 conditional (22%). Those 40 were the development set and were run on other code, so they are not a like-for-like baseline. The gap is still large. The holdout's conditional rate (60%, with the record's facts supplied) suggests the rules, more than intake, carry most of it.
- **The stricter reading is my judgement after the double-check, not the frozen scorer's definition.** Both are reported. The same pattern (H15, and H14 in rules e2e) was in the 2026-11-12 scores too, so comparisons across dates hold under either reading.
- **The 94110 result is "no scored change", not "no harm".** The scorer does not measure nearby-licence counts, the licence at the address or tract concentration, and the reports were factually wrong on them.
- The Opus arm used the API's default effort and no forced tool choice. Other settings were not tried.

## Files

- **Code:** branch `spelling-and-intake-questions`; the harness flags `--intake-model` and `--licences-file` (commit 448d260) are merged into it.
- **Results and scores (JSON, no PDFs):** `backtest/holdout/results-2026-11-16/{sonnet-full,sonnet-94110,opus-full,opus-94110}/` (each with `scores.json` and `summary.md`).
- **Journals:** `$LOCAL_DATA_DIR/backtest/journal-holdout-sonnet.jsonl`, `journal-holdout-opus.jsonl`.
- **94110 licence set:** `$LOCAL_DATA_DIR/backtest/licences_asof_94110.json` and `licences_asof_94110-nozip-decisions.json`, built by `scripts/validation/make_licences_94110.py`.
- **Costs:** `docs/validation/spend.md`, cycle from 2026-11-16.
