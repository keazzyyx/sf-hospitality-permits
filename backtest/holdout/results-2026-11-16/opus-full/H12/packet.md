# H12: 3233 22nd St, San Francisco, CA 94110

Record 2023-011780CUA, filed 2023-12-29, approved_with_conditions. Rules date 2023-12-28.

## Ground truth (decision record)

- Correct pathway: **further_review** (conditional)
- Rule coverage on the record's facts: 
- Why closed: decided
- Regulatory problem: n/a
- Concept as filed (not given to the report): CB3P approved project is seeking Conditional Use Authorization pursuant to Planning Code Section 249.60 for a change of use from Limited Service Restaurant to Full Service Restaurant and Specialty Grocery to secure a Type 41 ABC license.
- Concept given to the report: Change a limited restaurant into a full-service restaurant and specialty grocery, to get an ABC Type 41 licence.
- Intake answers given: {"part_of_chain": true, "other_locations": 1, "floor_area_sqft": 2100}

Triggers:

- Use control of the zoning district: conditional at filing (stated_in_record)
- Use control of a special use district: conditional at filing (stated_in_record)

## What each run said

| | Full report, end to end | Full report, conditional | Rules only, end to end | Rules only, conditional |
|---|---|---|---|---|
| alcohol | insufficient_information | insufficient_information | insufficient_information | insufficient_information |
| building_change_of_use | further_review | further_review | further_review | further_review |
| health | allowed | allowed | allowed | allowed |
| zoning_use | insufficient_information | further_review | insufficient_information | further_review |

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

