# H02: 3400 Cesar Chavez St, San Francisco, CA 94110

Record 2024-006641CUA, filed 2024-07-23, withdrawn. Rules date 2024-07-22.

## Ground truth (decision record)

- Correct pathway: **not_permitted** (not_permitted)
- Rule coverage on the record's facts: 
- Why closed: Reason not stated. The parent 2024-006641PRJ holds only the application, the Conditional Use supplement, plans and an intake checklist (last changed 2024-12-09). No hearing, motion, staff report or letter. Status "Closed - Withdrawn" 2025-01-15, about six months after filing. Likely reason (inferred from the code, as N09): the request as filed, a new ABC Type 21 at a store in the Mission Alcoholic Beverage SUD, had no path, because the SUD allows no new Liquor Store and lets a grocery take only a licence transferred from inside the SUD (§ 249.60(a), (b)(2)). Context only, from the local copy of the ABC licence data: a Type 20 off-sale beer and wine licence (Casa Guadalupe Supermarket 2) was issued at this address on 2025-07-16 by transfer from licence 20-394431. That fits the transfer route, but the file never says why the Conditional Use was withdrawn.
- Regulatory problem: yes
- Concept as filed (not given to the report): Conditional Use Authorization pursuant to Planning Code Section 754 to permit new ABC Type 21 license for an existing vacant store.
- Concept given to the report: A new ABC Type 21 licence for an existing store space that is vacant.
- Intake answers given: {"liquor_licence": "new", "floor_area_sqft": 10976}

Triggers:

- Liquor licence rule of a restricted district: not_permitted at filing (inferred_from_code)

## What each run said

| | Full report, end to end | Full report, conditional | Rules only, end to end | Rules only, conditional |
|---|---|---|---|---|
| alcohol | further_review | further_review | further_review | further_review |
| building_change_of_use | insufficient_information | insufficient_information | insufficient_information | insufficient_information |
| health | allowed | allowed | allowed | allowed |
| zoning_use | insufficient_information | not_permitted | insufficient_information | not_permitted |

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

