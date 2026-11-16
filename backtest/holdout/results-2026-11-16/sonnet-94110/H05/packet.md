# H05: 2007 Franklin St, San Francisco, CA 94109

Record 2025-005018CUA, filed 2025-06-05, approved_with_conditions. Rules date 2025-06-04.

## Ground truth (decision record)

- Correct pathway: **further_review** (conditional)
- Rule coverage on the record's facts: 
- Why closed: decided
- Regulatory problem: n/a
- Concept as filed (not given to the report): Conditional Use Authorization pursuant to Planning Code Section(s) 186.3 209.1, 303, and 710 to permit SF Heritage to formalize General Entertainment, Nighttime Entertainment, and Bar uses and Outdoor Activity Area in the front and rear gardens of the Property (the “Project”). The Project maintains the existing uses of the Property, including as a residence, museum, office, and events space. The Project seeks Conditional Use authorization pursuant to Planning Code Sections 186.3, 209.1, 303, and 710 for General Entertainment, Nighttime Entertainment, and Bar uses and Outdoor Activity Area. The Project seeks to formalize the Outdoor Activity Area in the front and rear gardens of the Property pursuant to Planning Code Sections 145.2, 186.3, 209.1, 303, and 710. The Project will generate increased revenue needed to maintain this landmark building. Allowing these uses will enhance the feasibility of preserving the landmark building for another 130 years. No alteration or construction is proposed by the Project.
- Concept given to the report: SF Heritage wants to formalize general entertainment, nighttime entertainment and bar uses at a landmark building, and an outdoor activity area in its front and rear gardens. The building's existing uses stay: a residence, a museum, an office and an events space. The new uses would bring in revenue needed to maintain the landmark building. No alteration or construction.
- Intake answers given: none

Triggers:

- landmark_use_in_residential_district: conditional at filing (stated_in_record)
- Nighttime entertainment: conditional at filing (stated_in_record)
- Outdoor activity area: conditional at filing (stated_in_record)

## What each run said

| | Full report, end to end | Full report, conditional | Rules only, end to end | Rules only, conditional |
|---|---|---|---|---|
| alcohol | insufficient_information | not_permitted | not_permitted | not_permitted |
| building_change_of_use | insufficient_information | insufficient_information | insufficient_information | insufficient_information |
| entertainment | insufficient_information | - | - | - |
| health | allowed | allowed | allowed | allowed |
| outdoor | insufficient_information | not_permitted | not_permitted | not_permitted |
| zoning_use | insufficient_information | further_review | not_permitted | further_review |

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

