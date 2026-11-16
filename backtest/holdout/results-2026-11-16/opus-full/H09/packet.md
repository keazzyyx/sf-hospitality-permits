# H09: 786 Lombard St, San Francisco, CA 94133

Record 2023-000022CUA, filed 2023-01-06, approved_with_conditions. Rules date 2023-01-05.

## Ground truth (decision record)

- Correct pathway: **further_review** (conditional)
- Rule coverage on the record's facts: 
- Why closed: decided
- Regulatory problem: n/a
- Concept as filed (not given to the report): The proposal is for a Conditional Use Authorization (CUA) to seek legalization of the limited use restaurant on the property per Planning Code Section 780.3 (c)(6).
- Concept given to the report: Legalize the limited restaurant on this property.
- Intake answers given: {"floor_area_sqft": 800}

Triggers:

- legacy_business_replacement: conditional at filing (stated_in_record)

## What each run said

| | Full report, end to end | Full report, conditional | Rules only, end to end | Rules only, conditional |
|---|---|---|---|---|
| alcohol | - | insufficient_information | - | insufficient_information |
| building_change_of_use | not_permitted | allowed | not_permitted | allowed |
| health | not_permitted | allowed | not_permitted | allowed |
| zoning_use | not_permitted | further_review | not_permitted | further_review |

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

