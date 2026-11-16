# D17: 1326 Grant Ave, San Francisco, CA 94133

Record 2024-002223CUA, filed 2024-03-13, approved_with_conditions. Rules date 2024-03-12.

## Ground truth (decision record)

- Correct pathway: **further_review** (conditional)
- Rule coverage on the record's facts: fully
- Why closed: decided
- Regulatory problem: n/a
- Concept as filed (not given to the report): Conditional Use Authorization to amend the existing entertainment hours and add amplified sound for Legacy North Beach Bar.
- Concept given to the report: An existing bar, described as a legacy bar, wants to change its existing entertainment hours and add amplified sound.
- Intake answers given: {"floor_area_sqft": 985}

Triggers:

- Changing the conditions of an earlier approval: conditional at filing (stated_in_record)
- Enlarging or intensifying an existing use: conditional at filing (stated_in_record)
- Nighttime entertainment: conditional at filing (inferred_from_code)

## What each run said

| | Full report, end to end | Full report, conditional | Rules only, end to end | Rules only, conditional |
|---|---|---|---|---|
| alcohol | insufficient_information | insufficient_information | insufficient_information | insufficient_information |
| building_change_of_use | insufficient_information | further_review | insufficient_information | further_review |
| entertainment | further_review | further_review | further_review | further_review |
| health | allowed | allowed | allowed | allowed |
| zoning_use | further_review | further_review | insufficient_information | further_review |

In the conditional runs the zoning row is supplied from the decision record.

Files: `e2e/memo.json`, `conditional/memo.json` (the report PDFs are not in this repository), `rules_only_e2e.json`, `rules_only_conditional.json`, `leakage.json`.

## Grading sheet (for a permit professional)

| Question | Full, end to end | Full, conditional |
|---|---|---|
| Did the report flag every issue that made the use impossible, forced the pathway, led to withdrawal or imposed a concept-changing condition? Which did it miss? | | |
| Any finding the cited record does not support? | | |
| Any blocker that was not one? | | |
| Are the expected conditions close to the motion's conditions? | | |
| Anything materially wrong not covered above? | | |

