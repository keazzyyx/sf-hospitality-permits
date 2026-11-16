# H10: 999 Valencia St, San Francisco, CA 94110

Record 2023-002340CUA, filed 2023-04-04, approved_with_conditions. Rules date 2023-04-03.

## Ground truth (decision record)

- Correct pathway: **further_review** (conditional)
- Rule coverage on the record's facts: 
- Why closed: decided
- Regulatory problem: n/a
- Concept as filed (not given to the report): The Project is seeking Conditional Use authorization from Planning Code Section 249.60 related to Valencia Whole Foods' purchase of a Type 20 liquor license from Ish's Community Market Corp.
- Concept given to the report: Valencia Whole Foods wants to buy an ABC Type 20 licence from Ish's Community Market Corp.
- Intake answers given: {"floor_area_sqft": 1700, "liquor_licence": "transfer_from_another_location", "part_of_chain": false}

Triggers:

- Liquor licence rule of a restricted district: conditional at filing (stated_in_record)

## What each run said

| | Full report, end to end | Full report, conditional | Rules only, end to end | Rules only, conditional |
|---|---|---|---|---|
| alcohol | further_review | further_review | further_review | further_review |
| building_change_of_use | insufficient_information | insufficient_information | insufficient_information | insufficient_information |
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

