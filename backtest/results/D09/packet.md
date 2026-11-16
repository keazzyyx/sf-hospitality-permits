# D09: 2214 Mission St, San Francisco, CA 94110

Record 2023-001895CUA, filed 2023-03-02, approved_with_conditions. Rules date 2023-03-01.

## Ground truth (decision record)

- Correct pathway: **further_review** (conditional)
- Rule coverage on the record's facts: partly
- Why closed: decided
- Regulatory problem: n/a
- Concept as filed (not given to the report): Application for Conditional Use to convert the existing parking lot to an outdoor dining patio pursuant to Planning Code Section 145.2 (Outdoor Activity Area).
- Concept given to the report: Convert the existing parking lot into an outdoor dining patio.
- Intake answers given: {"floor_area_sqft": 3227, "liquor_licence": "already_held"}

Triggers:

- Outdoor activity area: conditional at filing (stated_in_record)
- Liquor licence in a restricted district: conditional at filing (stated_in_record)

## What each run said

| | Full report, end to end | Full report, conditional | Rules only, end to end | Rules only, conditional |
|---|---|---|---|---|
| alcohol | insufficient_information | further_review | insufficient_information | further_review |
| building_change_of_use | insufficient_information | insufficient_information | insufficient_information | insufficient_information |
| health | allowed | allowed | allowed | allowed |
| outdoor | insufficient_information | insufficient_information | insufficient_information | insufficient_information |
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

