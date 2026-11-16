# H14: 1548 California St, San Francisco, CA 94109

Record 2022-001116CUA, filed 2022-02-08, approved_with_conditions. Rules date 2022-02-07.

## Ground truth (decision record)

- Correct pathway: **further_review** (conditional)
- Rule coverage on the record's facts: 
- Why closed: decided
- Regulatory problem: n/a
- Concept as filed (not given to the report): Conditional Use Authorization application request, pursuant to Planning Code Section 303, Section 723, Section 102, and Section 202(a)(6) to convert the front portion of an existing bar (ABC-Type 48 License), Soda Popinski's, into a retail package store selling beer, wine, and distilled spirits for off-site consumption. The new liquor store area of the retail establishment measures approximately 250 sq. ft. There will be no exterior or interior changes.
- Concept given to the report: An existing bar, Soda Popinski's, with an ABC Type 48 licence, wants to turn the front part of the bar into a package store selling beer, wine and spirits to take away. The liquor store area would be about 250 square feet. No exterior or interior changes.
- Intake answers given: {"floor_area_sqft": 853}

Triggers:

- Use control of the zoning district: conditional at filing (stated_in_record)

## What each run said

| | Full report, end to end | Full report, conditional | Rules only, end to end | Rules only, conditional |
|---|---|---|---|---|
| alcohol | insufficient_information | insufficient_information | insufficient_information | insufficient_information |
| building_change_of_use | insufficient_information | allowed | insufficient_information | allowed |
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

