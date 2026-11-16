# H04: 3352 Steiner St, San Francisco, CA 94123

Record 2022-004869CUA, filed 2022-06-01, approved_with_conditions. Rules date 2022-05-31.

## Ground truth (decision record)

- Correct pathway: **further_review** (conditional)
- Rule coverage on the record's facts: 
- Why closed: decided
- Regulatory problem: n/a
- Concept as filed (not given to the report): Convert existing Formula Retail restaurant space to new Formula Retail restaurant user known as "Bluestone Lane"
- Concept given to the report: Bluestone Lane, a restaurant that is part of a chain, wants to take over an existing restaurant space last used by another restaurant that is part of a chain.
- Intake answers given: {"part_of_chain": true, "other_locations": "11_or_more", "floor_area_sqft": 2374}

Triggers:

- Formula retail: conditional at filing (stated_in_record)

## What each run said

| | Full report, end to end | Full report, conditional | Rules only, end to end | Rules only, conditional |
|---|---|---|---|---|
| building_change_of_use | insufficient_information | further_review | insufficient_information | further_review |
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

