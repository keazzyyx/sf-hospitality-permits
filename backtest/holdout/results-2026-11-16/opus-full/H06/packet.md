# H06: 620 Jones St, San Francisco, CA 94102

Record 2025-003933CUA, filed 2025-05-05, approved_with_conditions. Rules date 2025-05-04.

## Ground truth (decision record)

- Correct pathway: **further_review** (conditional)
- Rule coverage on the record's facts: 
- Why closed: decided
- Regulatory problem: n/a
- Concept as filed (not given to the report): Conditional Use Authorization pursuant to Planning Code Section 209.3. RC to amend a condition of approval from Planning Commission Motion No. 19270 to extend the hours of operation for entertainment in the outdoor activity area to 8pm Sunday - Thurs and 10:00pm Friday and Saturday. No proposed construction.
- Concept given to the report: A business operates under an existing permission whose conditions limit the hours of entertainment in its outdoor activity area. It wants to extend those hours to 8 p.m. Sunday to Thursday and 10 p.m. Friday and Saturday. No construction.
- Intake answers given: none

Triggers:

- Changing the conditions of an earlier approval: conditional at filing (stated_in_record)
- Enlarging or intensifying an existing use: conditional at filing (inferred_from_code)

## What each run said

| | Full report, end to end | Full report, conditional | Rules only, end to end | Rules only, conditional |
|---|---|---|---|---|
| building_change_of_use | insufficient_information | insufficient_information | insufficient_information | insufficient_information |
| entertainment | - | further_review | - | further_review |
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

