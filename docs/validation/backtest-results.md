# Backtest results: 40 San Francisco Conditional Use cases

Run 2026-11-11 and 12 on the plan as approved (`backtest-plan.md`), after the pilot and its review
(`backtest-pilot.md`). Every report was made as of the day before its case was filed. Nothing was written to
production.

Full tables, every case: [`../../backtest/results/summary.md`](../../backtest/results/summary.md) (built by
`python -m app.backtest.score`), per-case reviewer packets `backtest/results/<case>/packet.md` (with the two report
PDFs, the rules-only sheets, `leakage.json` and a blank grading sheet), raw scores `backtest/results/scores.json`.

## What ran

| Result set | Cases | What it is given |
|---|---|---|
| Full report, end to end | 40 | address, neutral concept text, the intake answers the case file states |
| Full report, conditional | 40 | the decision record's facts and the correct pathway; records and comparables from the end-to-end run |
| Rules only, end to end | 40 | the hand-entered facts of the neutral text (+ intake answers); no model |
| Rules only, conditional | 40 | the decision record's facts and the correct pathway; no model |

D10's first end-to-end report failed: the comparables stage gave no structured answer in its 8 turns. That is a
product failure and is reported as one. Under the plan's re-run rule it was re-run fresh, without replaying its
answers, and passed. Its scores are from the re-run.

Cost: $63.36 of the $80 backtest cap: the pilot and its rerun $5.14, the end-to-end half $32.99 (D10's re-run
included), the conditional half $23.55, the restatement check $1.68. Validation total about $101.65 of $130.

## The measures, each result set on its own

All 40 cases. The conditional sets have the correct pathway supplied, so their pathway rows are not results. Their
statuses are set by the same rules on the same facts, so the full report and the rules-only baseline agree there by
construction; they differ only in the model's text.

| Measure | Full, end to end | Rules only, end to end | Full, conditional | Rules only, conditional |
|---|---|---|---|---|
| Critical issues found (of 62) | 33 (53%) | 31 (50%) | 42 (68%) | 42 (68%) |
| Materially unsafe cases (of 40; see the next section) | 15 (38%) | 13 (32%) | 9 (22%) | 9 (22%) |
| Listed as unknown, naming the missing input | 11 | 16 | 9 | 9 |
| Raised with a different control | 2 | 0 | 0 | 0 |
| Missed (no rule, or not returned) | 16 | 15 | 11 | 11 |
| Pathway right | 31 | 27 | supplied | supplied |
| Missed pathways | 3 | 3 | supplied | supplied |
| Zoning row "Insufficient information" | 6 | 10 | supplied | supplied |
| False blockers | 3 rows in 1 case (D22) | 0 | 0 | 0 |
| Correct "Insufficient information" (missing inputs named) | 105 | 131 | 63 | 63 |
| Wrong "Insufficient information" | 4 | 5 | 0 | 0 |
| Unsupported findings (unsupported outright, of cited sentences) | 356 / 1,205 (30%) | n/a | 345 / 1,222 (28%) | n/a |

By group (full report, end to end): decided cases 23 of 42 critical issues found (55%), cases that did not reach
approval 10 of 20 (50%).

## Materially unsafe cases

A second measure, by case rather than by issue. **A case is materially unsafe when the report misses at least one
of the case's critical issues, or shows a false blocker.** Missed means: no rule covers the issue, the rules
returned nothing for it, they returned a control that asks nothing where the record shows one, or they raised it
with a different control than the record's (for example "conditional" where the record says "not permitted").
A missed issue only counts when the record shows it needed something: a Conditional Use, or "not permitted".

What does **not** make a case unsafe:

- An issue listed as unknown, naming the missing input. The report says plainly that it cannot decide the issue
  and what it needs to know, so the reader is not misled.
- A missed issue that needed nothing. In the 40 this is one issue: N15's change of operator for formula retail.
  No rule covers it, so it still counts as missed among the 62 issues. But Planning approved it by letter, with
  no hearing, so missing it does not put the applicant at risk.
- A trigger that reads "Code and Planning practice differ" (none in the 40).
- A missed pathway on its own. In the 40 the only case with a missed pathway that is not unsafe is N15, end to end
  (full report and rules only). There the report says "further review" where the record needed nothing. That is
  too cautious, not unsafe. Every other case with a missed pathway is unsafe anyway, for an issue or a false
  blocker.

False blockers are only scored where the record shows there was none (decided cases whose answer is not "not
permitted", and cases that closed because no hearing was needed). In the other cases only a missed issue counts.

| Group | Full, end to end | Rules only, end to end | Full, conditional | Rules only, conditional |
|---|---|---|---|---|
| All 40 | 15 (38%); issues found 33 of 62 (53%) | 13 (32%); 31 of 62 (50%) | 9 (22%); 42 of 62 (68%) | 9 (22%); 42 of 62 (68%) |
| Decided (25) | 10 (40%); 23 of 42 (55%) | 8 (32%); 20 of 42 (48%) | 5 (20%); 30 of 42 (71%) | 5 (20%); 30 of 42 (71%) |
| Did not reach approval (15) | 5 (33%); 10 of 20 (50%) | 5 (33%); 11 of 20 (55%) | 4 (27%); 12 of 20 (60%) | 4 (27%); 12 of 20 (60%) |
| Licence status unknown at the address (8) | 1 (12%); 9 of 13 (69%) | 1 (12%); 7 of 13 (54%) | 1 (12%); 11 of 13 (85%) | 1 (12%); 11 of 13 (85%) |
| All other cases (32) | 14 (44%); 24 of 49 (49%) | 12 (38%); 24 of 49 (49%) | 8 (25%); 31 of 49 (63%) | 8 (25%); 31 of 49 (63%) |

Every case that is unsafe in at least one result set (16 cases). "Yes" names the issue. N15 is not in the
table: it is unsafe in no set (see above).

| Case | Full, end to end | Rules only, end to end | Full, conditional | Rules only, conditional |
|---|---|---|---|---|
| N01 | yes: open-air use, Waterfront SUD (no rule) | yes, same | yes, same | yes, same |
| N03 | no (entertainment listed as unknown) | yes: nighttime entertainment (not returned) | no | no |
| N04 | yes: formula retail, change of operator (no rule) | yes, same | yes, same | yes, same |
| N05 | yes: liquor licence in a restricted district (rules ask nothing) | yes, same | yes, same | yes, same |
| N10 | yes: enlarging an existing use (intake model dropped it) | no | no | no |
| N13 | yes: enlarging an existing use (rules ask nothing) | yes, same | yes, same | yes, same |
| D04 | yes: enlarging an existing use (rules ask nothing) | yes, same | yes, same | yes, same |
| D05 | yes: nighttime entertainment | yes: nighttime entertainment; enlarging | yes: use control; enlarging | yes: use control; enlarging |
| D07 | yes: use control of the district | no (listed as unknown) | no | no |
| D09 | yes: liquor licence in a restricted district | yes, same | no | no |
| D12 | yes: laundromat removal; enlarging | yes: laundromat removal | no (enlarging listed as unknown) | no (same) |
| D13 | yes: laundromat removal | no | no | no |
| D14 | yes: nighttime entertainment (different control) | yes: nighttime entertainment (not returned) | no | no |
| D16 | yes: legacy business replacement (no rule) | yes, same | yes, same | yes, same |
| D22 | yes: storefront merger (no rule); use control (different control); false blocker on 3 rows | yes: storefront merger | yes: storefront merger | yes: storefront merger |
| D24 | yes: enlarging an existing use | yes, same | yes: nighttime entertainment | yes, same |

What this shows:

- **9 cases are unsafe in all four sets.** Giving the report the record's facts does not help them: 4 have an
  issue no rule covers (N01, N04, D16, D22), 3 have a rule that asks nothing where the record shows a
  Conditional Use (N05, N13, D04), and in D05 and D24 the record's facts move the miss to another issue.
- **6 cases are unsafe end to end but not with the record's facts** (N10, D07, D09, D12, D13, D14). These are the
  input problems that "Where the 9-issue gap comes from" (below) breaks down.
- No case is safe end to end and unsafe in the conditional run.

The 20 holdout cases will be scored the same way, with the same definition, when they are run. Their unsafe rate
will be reported next to their issue-level numbers, per result set and per group, as above:
`python -m app.backtest.score --case-file ../../backtest/holdout/cases.yaml --results-dir ../../backtest/holdout/results`
(from `apps/api`). Their scores go to the holdout's own results folder; the scorer refuses to write them into the
40's. The holdout has not been run or scored yet.

## Every critical miss, and why

Full report, end to end. "Full only" marks a miss the rules-only version (hand-entered facts) does not have; there
the difference is what the intake model read from the text.

| Case | Issue missed | Why |
|---|---|---|
| N01 | Unscreened open-air use, Waterfront SUD | no rule (seen once in the 40; § 240.2(d)) |
| N04 | Formula retail: change of operator | no rule (§ 178(c)(3) is printed as a note, not evaluated) |
| N05 | Liquor licence in a restricted district | the rules returned principal; the record shows conditional |
| N10 | Enlarging or intensifying an existing use | full only: the intake model did not keep the stated enlargement |
| N13 | Enlarging or intensifying an existing use | the rules returned principal |
| N15 | Formula retail: change of operator; and the pathway | no rule; the report says a Conditional Use where Planning approved the change of operator administratively |
| D04 | Enlarging or intensifying an existing use | the rules returned principal |
| D05 | Nighttime entertainment (second story, not permitted at filing) | not returned |
| D07 | Use control of the district | full only: not returned on the intake model's profile |
| D09 | Liquor licence in a restricted district | the rules returned principal |
| D12 | Laundromat removal; enlarging or intensifying (full only) | the rules returned principal; the enlargement was not returned on the intake model's profile |
| D13 | Laundromat removal | full only |
| D14 | Nighttime entertainment (different control) and the pathway | the rules returned conditional where the second story was not permitted at filing; the pathway reads further review, the record not permitted |
| D16 | Legacy business replacement | no rule (seen once; § 754(c)(4)) |
| D22 | Storefront merger; use control (different control, full only); the pathway (full only) | no rule for the merger (§ 754(c)(2)); the intake model read "a mezzanine" as a second story, where a Restaurant is not permitted (below) |
| D24 | Enlarging or intensifying an existing use | not returned |

Rules only, end to end, misses these that the full report does not: N03 (nighttime entertainment), D05 (enlarging
or intensifying), N13's pathway (the rules say a Conditional Use; Planning decided none was needed), and D14's
nighttime entertainment is not returned at all rather than returned with a different control.

Conditional (identical for the full report and the rules only, 11 misses): N01, N04, N15 (no rule); N05 (liquor
licence in a restricted district); N13, D04 (enlarging or intensifying); D05 (use control, and enlarging or
intensifying); D16, D22 (no rule: legacy business, storefront merger); D24 (nighttime entertainment). Each with its
source line in `summary.md`.

## The false blocker

D22 (Honey Cove Restaurant, 2573 Mission St, approved). The full report reads zoning **Not permitted**, and with it
the health and building rows. The neutral text says one unit has "a mezzanine"; the intake model read that as a second
story, and a Restaurant on the second story is not permitted in NCT-MISSION. The rules-only version, given the
hand-entered facts (first story), reads further review, as the record does.

## Where the 9-issue gap comes from (end to end 33, conditional 42)

Full report, end to end against full report, conditional, issue by issue. Sources: each case's `e2e/` and
`conditional/` files (memo.json triggers, profile.json), `rules_only_e2e.json` (the hand-entered facts of the same
text, no model), and `backtest/inputs.json` (`input_facts` against `record_facts`). No model was run for this. Where
a row says "run again", the saved profile was put through the rules again on this machine, with one fact changed
(rules only, no model, no network). Each such run first gave back the saved memo's own answer unchanged.

The causes:

- **(a) Wrong pathway.** None of the 13. In this harness a wrong pathway cannot stop a trigger. The rules work out
  each trigger from the facts first, and the zoning row's answer follows from the triggers. The conditional run
  supplies only the zoning row's answer from the record; every trigger in it is still computed by the rules from
  the record's facts (`supply_pathway` in `app/backtest/run.py` changes the zoning row and nothing else). Three of
  the cases below also had the wrong pathway end to end (D12 and D13: "Insufficient information" where the record
  needed a hearing; D14: further review where the record says not permitted). In all three the pathway and the
  trigger went wrong for the same reason, a fact missing from the text or misread, so they are counted under that
  cause. The "End-to-end pathway" column shows this for each case.
- **(b) Missing input.** The neutral text does not state the fact that decides the issue. The record does. This is
  judged on the text, not on what the product can hold: a fact the text states but the product has no place for
  is (d).
- **(c) Misread input.** The text states the fact, and the intake model read it wrongly or left it out (or filled
  a fact the text does not state). Two checks: the trigger's own reasoning line in the end-to-end memo, and the
  rules-only run on the hand-entered facts of the same text (where it finds the issue and the full report does
  not, the difference is the intake model).
- **(d) Other.** Said in each row. Two kinds come up:
  - **No field for a stated use.** The text or the record states the use itself (for example "nighttime
    entertainment" or "a bar"). The product's profile has no field for it (`planning_use` is in
    `FACTS_WITHOUT_A_PROFILE_FIELD` in `app/memo/facts.py`), so the rules never see it. The backtest runs the
    product's own path, so it has the same limit. `docs/validation/rule-coverage-of-the-40.md` describes it.
  - **A rule gap.** The rules have the facts and still cannot answer.

**Found in conditional, not end to end (11 issues)**

| Case | Issue | End to end | Conditional | End-to-end pathway | Cause | What happened |
|---|---|---|---|---|---|---|
| N03 | Nighttime entertainment | unknown | found | right | (d) no field for the stated use | The text says "Convert a bar/restaurant to nighttime entertainment". That states the use. The profile cannot hold it, so the rules read the entertainment only from the live-entertainment answer, and then need the kind (Limited Live Performance or Place of Entertainment), which the text does not give. The report named the kind as missing. Run again with the stated use carried, the rules return conditional: found. Conditional found it from the record's kind. |
| N10 | Enlarging an existing use | missed | found | right | (c) misread | The text says "An existing bar wants to expand." The intake model kept neither the existing bar nor the expansion, so the rule saw nothing to enlarge ("No existing business is described as staying"). Rules only (hand-entered facts) finds it. |
| D05 | Nighttime entertainment (second story not permitted) | missed | found | right | (c) misread | The model recorded the existing use as Nighttime Entertainment (the text says "an existing historic movie theatre"). So the rule read the entertainment as continuing ("Nighttime Entertainment already exists at this address and continues") and did not apply the control for a new use. (Rules only misses it too, for another reason: the hand-entered facts state the use, Nighttime Entertainment and a Bar, but the profile cannot hold it, so the rules never see the entertainment. With the stated use carried they return not permitted: found.) |
| D07 | Use control of the district | missed | found | right | (b) missing input, made worse by (c) | The text says "an existing restaurant"; the record shows a Limited Restaurant, so a Restaurant is a new use here. The text cannot give that. The model also filled "intensify", which the text does not say, so the rule read the restaurant as continuing: a miss where rules only lists it as unknown. Counted once, under (b). |
| D09 | Liquor licence in a restricted district | missed | found | right | (b) missing input | The text: "Convert the existing parking lot into an outdoor dining patio." The record: an existing restaurant with a Type 41 licence expands onto the lot, and the Mission alcohol district's expansion rule (§ 249.60(c)(3)) needs a Conditional Use. The text does not say a licensed restaurant is expanding. Rules only misses it the same way. |
| D12 | Laundromat removal | missed | found | "Insufficient information" | (b) missing input | The text says "the vacant retail space next door". The record says it was last a dry cleaner, which is a Laundromat under § 102. Rules only misses it the same way. |
| D13 | Laundromat removal | missed | found | "Insufficient information" | (c) misread | The text says "Convert a dry cleaner into a restaurant." The model recorded the last use as "other", not a laundromat. Rules only (last use: laundromat) finds it. |
| D14 | Nighttime entertainment (second story not permitted) | different control | found | missed (further review; record: not permitted) | (b) missing input | The text gives no story, so the rules read the first story: conditional. The record has the first and second stories, and the second was not permitted at filing. The missed pathway comes from the same missing story. |
| D17 | Nighttime entertainment | unknown | found | right | (b) missing input | The text says "change its existing entertainment hours and add amplified sound", not the kind. The record says a Place of Entertainment. The report named the kind as missing. |
| D23 | Liquor licence in a restricted district | unknown | found | right | (b) missing input | The text: "Gratta Wines wants an ABC Type 42 licence." The record: a grocery (a retail use) that already holds a Type 02 licence. The report named both missing facts (how the licence is obtained, the last use). |
| D24 | Enlarging an existing use | missed | found | right | (c) misread (left out), and (d) no field for the stated use | The text asks to "extend the hours" and "add amplified live music". The product's own word check (`app/memo/stated.py`) reads that as stating an intensification. The model left it out. So did the hand-entered facts, which is why rules only misses it too. Recording it would not have been enough. Run again with "intensify" added, the rule still reads "no use the rule table covers continues": the model called the business a Bar, and the profile cannot hold the stated Nighttime Entertainment use. With both "intensify" and the stated use (the hand-entered facts, run again), the rules return conditional: found. Counted once, under (c). |

**Found end to end, not in conditional (2 issues)**

| Case | Issue | End to end | Conditional | End-to-end pathway | Cause | What happened |
|---|---|---|---|---|---|---|
| D05 | Use control of the district | found | missed | right | (d) no field for the stated use | The record gives two uses, Nighttime Entertainment and a Bar, with the business type "other". The profile cannot hold the stated uses, so the rules see only the entertainment (read under the entertainment trigger) and never look up the Bar. With the stated uses carried (`coverage.json`, D05's `record_run`; and the saved conditional profile run again) the use control returns conditional: found. End to end found it because the model called the business a bar (the text says "and a bar"). |
| D05 | Enlarging an existing use | found | missed | right | (d) a rule gap; found end to end only by the misread | The record's existing use is a Movie Theater, which the rule table has no row for, so the rule sees no continuing use. Carrying the stated uses does not change this. End to end found it only because of the same misread that lost the entertainment issue above. |

**The arithmetic**

| | Issues |
|---|---|
| Found end to end | 33 |
| plus found in conditional only | +11 |
| minus found end to end only | −2 |
| Found in conditional | 42 |

| Cause | Issues | Net |
|---|---|---|
| (a) wrong pathway | 0 | 0 |
| (b) missing input | 6 (D07, D09, D12, D14, D17, D23) | +6 |
| (c) misread input | 4 (N10, D05 entertainment, D13, D24 enlarging) | +4 |
| (d) no field for a stated use | 1 gained (N03), 1 lost (D05 use control) | 0 |
| (d) a rule gap (D05 enlarging: no row for a Movie Theater; found end to end only through the misread) | 1 lost | −1 |
| **Total** | 11 gained, 2 lost | **+9** |

So 6 of the 11 are facts the neutral text does not give. The intake model's misreads account for 4 (D24 also
needs the stated use). The missing field for a stated use moves one issue each way, so here it nets to zero. But
it matters on its own: it is why rules only misses D05's entertainment, and why N03 is unknown rather than found.

**Other changes between the two that do not move the "found" count** (they do move the unsafe count):

| Case | Issue | End to end | Conditional | Cause |
|---|---|---|---|---|
| D12 | Enlarging an existing use | missed | unknown | (c) the model recorded the last use as "retail" and dropped the stated restaurant, so the rule saw no continuing use. Rules only lists it as unknown, as conditional does. |
| D22 | Use control of the district | different control (not permitted) | unknown | (c) the model read "a mezzanine" as a second story (the false blocker). |
| D24 | Nighttime entertainment | unknown | missed | (d) on the record's facts the rule reads the entertainment as continuing and does not apply the control for a new use; the record shows a Conditional Use was needed. |

### What the 2026-11-12 decisions would change (expected, not run)

The strict-intake decision has two parts: (1) the model may record only facts the text states, and (2) anything
else becomes unknown and is named in "Insufficient information" (a cleared "yes" is not read as "no"). The code
check only removes values. It never adds a fact the text does not give. Nothing was run for this; it is read from
the saved profiles and the check's word lists (`app/memo/stated.py`).

- **(a) wrong pathway:** none to change.
- **(b) missing input, 6 issues:** not fixed. The deciding facts are not in the text. Two may change from missed or
  different control to unknown, which matters for the unsafe count:
  - D07: the guessed "intensify" would be cleared (adding a licence is not an intensification in the check's
    words), so the use control would read "not decided", as in rules only.
  - D14: the model filled live entertainment, amplified sound and dancing; the text's words state none of them, so
    they would be cleared. The trigger may then read "not decided" for the kind of entertainment, as in N03. But
    if the model records the kind from "nighttime entertainment", which the check accepts, it stays conditional on
    the first story. D14 cannot be found either way: the second story is not in the text.
  - D09, D12, D17, D23: no change. The text has no words for the deciding fact.
- **(c) misread input, 4 issues:**
  - D05: the existing use "Nighttime Entertainment" would be cleared if the model quotes only the theatre words
    ("movie theatre" cannot state it). But the same sentence also says "nighttime entertainment", and the check
    cannot tell which use a word names (one of its stated limits), so the misread may survive. Run again with the
    existing use removed: the entertainment is read as new and found (not permitted), the use control is lost
    (the Bar is then read under the entertainment trigger), and the enlarging issue stays found. Net for D05: zero
    either way.
  - D13: the model's "other" would be cleared ("Convert a dry cleaner" has no words for an earlier use), so the
    laundromat rule would likely read "not decided" (unless the address's own records name a last use): unknown
    instead of missed. Found only if the model now writes
    "laundromat" (the check's words for it include "dry clean").
  - N10: the model left stated facts out. The check does not add them, so no change is expected from the check.
  - D24: the check accepts "extend the hours" and "add amplified live music" for "intensify", so if the model now
    records it, the check keeps it. That alone does not find the issue (run again with "intensify" added, above),
    and the entertainment issue stays unknown. No change expected.
  - Not in the count: D22's misread mezzanine was tested on 2026-11-12 and goes away (zoning back to further
    review, the false blocker gone). D12's "retail" is quoted from "the vacant retail space", which the check
    accepts, so no change.
- **(d) other, 3 issues:**
  - N03: strict intake adds no field for the stated use. N03 could still be found if the model now records the
    kind of entertainment from "nighttime entertainment", which the check accepts as a Place of Entertainment;
    that is not certain.
  - D05 use control (no field for the stated use) and D05 enlarging (rule gap): no change.

The two other decisions of 2026-11-12 (a prohibited use bars every later row; the citation check sees each
finding's rule lines) touch no trigger and no intake reading, so they change none of these causes.

Expected overall: the end-to-end "found" count moves little (D05 trades one issue for another if its misread is
cleared; D13 and N03 move only if the model now records the fact). The unsafe count may fall by two cases (D07, D13), perhaps three
(D14). D22 loses its false blocker but stays unsafe for the storefront merger (no rule). Only a re-run would
confirm this.

## Licences whose status on the cut-off day is unknown

Matched by parcel or street address, 8 cases (8 licences) have a licence on file at the case's own address whose
status on the cut-off day is not in ABC's archive. That is 8 cases, not the 10 I said earlier (that count was by
distance). They are scored with everything else; only those licences are left out, and the alcohol row says how many
within 1,000 ft and in the census tract had an unknown status that day.

- As their own group (full report, end to end): 9 of 13 critical issues found (69%), against 24 of 49 (49%) in
  the other 32 cases. No false blocker, 1 wrong "Insufficient information".
- **Did the gap change an answer?** Re-running the rules with every such licence counted as active changes no row
  status and no inventory trigger in any of the 40 cases. In two cases (D01, D18) it changes triggers outside the
  inventory and one missing input on the building row (the space then reads as a continuing restaurant). In 12 cases
  only the licence counts on the alcohol row differ.

## The writer's over-claiming

Share of cited sentences not kept as written (cut down, stripped of the citation, or removed), per case in
`summary.md` (table "The writer's over-claiming, per case").

| | End to end | Conditional |
|---|---|---|
| Cited sentences checked | 1,205 | 1,222 |
| Kept as written | 185 (15%) | 176 (14%) |
| Over-claiming, as the citation check decided | 85% | 86% |
| Of the not-kept sentences, everything in the row's rule lines | 211 | 169 |
| Over-claiming without those restatements | 67% | 72% |

The citation check is not shown a finding's rule lines, so a sentence that only restates them can be cut as "not in
the records". A Haiku comparison of every not-kept sentence with its row's rule lines found 211 (end to end) that
restate them in full; leaving those out, over-claiming is 67%. The rest is the writer.

**Harder cases:** it does not get clearly better or worse.

| Group (end to end) | Cases | Mean over-claiming |
|---|---|---|
| Rules fully cover the case | 23 | 86% |
| Partly cover | 11 | 84% |
| Do not cover | 6 | 80% |
| One trigger | 23 | 84% |
| Two triggers | 13 | 82% |
| Three or more | 4 | 93% |
| Decided | 25 | 86% |
| Did not reach approval | 15 | 81% |

The four cases with three or more triggers are highest, but four cases are too few to call it a trend. Longer reports
over-claim slightly more (correlation 0.24 between sentences checked and the share).

## The intake model

Across the 40 end-to-end reports the intake model listed 293 assumptions. Against the hand-entered facts, 61
rule-read facts were filled where the text does not state them, and 22 were read differently from the text
(table in `summary.md`). D22's mezzanine is the one that changed a status to a blocker.

## Timing (requirement 3)

From the decision records, by outcome, never blended: approved with conditions, 25 cases, median 135 days (57 to
353); withdrawn, 12 cases with a closing date, median 176 days (44 to 817). Three withdrawn cases have no closing date
on file. No case is pending.

## Leakage

Every prompt the data builds was scanned for all 40 cases before the run (`python -m app.backtest.scan`). The only
date after a cut-off is the laundromat rule's sunset (2024-12-20), fixed by the ordinance that created it. No case's
own record, project or motion number reached the model. During the run, every request was scanned again; the dates
the model was sent are in each case's `leakage.json`.

## Not changed, left open

- **N09's health row** reads "Allowed" while zoning reads "Not permitted" (the § 175(a) rule is applied to the use
  controls, not to the formula-retail prohibition). Decided 2026-11-12: a prohibited use (the use itself, or
  formula retail) now makes every later row "Not permitted". Hours, use size, Nighttime Entertainment, the outdoor
  area and a liquor licence rule do not. In the rules-only runs this changes N09 only.
- **The citation check does not see a finding's rule lines** (above): 211 end-to-end sentences were cut or removed
  only for restating them. Decided 2026-11-12: each finding is now checked with its row's rule lines. Re-checking
  the 21 such sentences of N14 and D02: 14 now kept as written, 5 kept in part, 2 still cut.
- **The intake model fills facts the text does not state** (61 rule-read facts), and its "mezzanine" reading produced
  the one false blocker.
- **D10's comparables stage** can fail to return a structured answer within its turn limit.
