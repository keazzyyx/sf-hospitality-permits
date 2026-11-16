# D10: 2351 Mission St, San Francisco, CA 94110

Record 2022-008254CUA, filed 2023-03-30, approved_with_conditions. Rules date 2023-03-29.

## Ground truth (decision record)

- Correct pathway: **further_review** (conditional)
- Rule coverage on the record's facts: partly
- Why closed: decided
- Regulatory problem: n/a
- Concept as filed (not given to the report): Conditional Use Authorization to establish an Outdoor Activity Area, measuring 1,777 square feet, in part of an existing public parking lot adjacent to the associated restaurant (d.b.a. “Casements”). The Project also proposes to expand the existing liquor establishment, as the Outdoor Activity Area would include serving of alcohol. Ten of the 81 parking spaces would be converted for the Outdoor Activity Area. The remaining spaces would be retained and continue to operate as the authorized public parking lot use.
- Concept given to the report: A restaurant (Casements) wants a 1,777-square-foot outdoor area in part of the existing public parking lot next to it. The restaurant already serves alcohol, and its alcohol service would expand into the outdoor area. Ten of the lot's 81 parking spaces would be used; the rest stay a public parking lot.
- Intake answers given: {"floor_area_sqft": 1952, "liquor_licence": "already_held"}

Triggers:

- Outdoor activity area: conditional at filing (stated_in_record)
- Liquor licence in a restricted district: conditional at filing (stated_in_record)

## What each run said

| | Full report, end to end | Full report, conditional | Rules only, end to end | Rules only, conditional |
|---|---|---|---|---|
| alcohol | insufficient_information | further_review | insufficient_information | further_review |
| building_change_of_use | insufficient_information | insufficient_information | insufficient_information | insufficient_information |
| entertainment | - | further_review | - | further_review |
| health | allowed | allowed | allowed | allowed |
| outdoor | insufficient_information | insufficient_information | insufficient_information | insufficient_information |
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

