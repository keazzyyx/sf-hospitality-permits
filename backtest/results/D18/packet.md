# D18: 737 Irving St, San Francisco, CA 94122

Record 2024-002929CUA, filed 2024-04-02, approved_with_conditions. Rules date 2024-04-01.

## Ground truth (decision record)

- Correct pathway: **further_review** (conditional)
- Rule coverage on the record's facts: fully
- Why closed: decided
- Regulatory problem: n/a
- Concept as filed (not given to the report): Conditional Use Authorization pursuant to Planning Code Section 303.1 to establish a Formula Retail, Restaurant use (dba Super Duper Burgers). Project includes interior tenant improvements, and repairs to front facade. New business signage under separate permit.
- Concept given to the report: Super Duper Burgers, part of a chain, wants to open a restaurant. Interior tenant improvements and repairs to the front facade.
- Intake answers given: {"part_of_chain": true, "other_locations": "11_or_more", "floor_area_sqft": 2231}

Triggers:

- Formula retail: conditional at filing (stated_in_record)

## What each run said

| | Full report, end to end | Full report, conditional | Rules only, end to end | Rules only, conditional |
|---|---|---|---|---|
| building_change_of_use | insufficient_information | insufficient_information | insufficient_information | insufficient_information |
| health | allowed | allowed | allowed | allowed |
| zoning_use | further_review | further_review | further_review | further_review |

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

