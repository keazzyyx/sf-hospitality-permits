# H19: 906 Broadway, San Francisco, CA 94133

Record 2024-002799CUA, filed 2024-03-29, approved_with_conditions. Rules date 2024-03-28.

## Ground truth (decision record)

- Correct pathway: **further_review** (conditional)
- Rule coverage on the record's facts: 
- Why closed: decided
- Regulatory problem: n/a
- Concept as filed (not given to the report): Conditional Use Authorization pursuant to Planning Code Sections 186.3, 209.2, 303, and 710 to convert vacant church building (Landmark #204) from an institutional use to an event space and change of use to General Entertainment. Proposed Hours of Operation 8 a.m. - 10 p.m. daily.
- Concept given to the report: Convert a vacant church building, a city landmark (No. 204), from an institutional use into an event space (general entertainment), open 8 a.m. to 10 p.m. daily.
- Intake answers given: {"floor_area_sqft": 15012}

Triggers:

- landmark_use_in_residential_district: conditional at filing (stated_in_record)

## What each run said

| | Full report, end to end | Full report, conditional | Rules only, end to end | Rules only, conditional |
|---|---|---|---|---|
| alcohol | - | insufficient_information | - | insufficient_information |
| building_change_of_use | further_review | further_review | insufficient_information | further_review |
| entertainment | insufficient_information | further_review | - | further_review |
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

