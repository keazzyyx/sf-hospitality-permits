# H17: 1111 California St, San Francisco, CA 94108

Record 2022-009099CUA, filed 2022-09-20, approved_with_conditions. Rules date 2022-09-19.

## Ground truth (decision record)

- Correct pathway: **further_review** (conditional)
- Rule coverage on the record's facts: 
- Why closed: decided
- Regulatory problem: n/a
- Concept as filed (not given to the report): In Motion No. 19020, dated November 14, 2013, the Planning Commission approved a conditional use application to change the use of the Nob Hill Masonic Center at 1111 California Street to "Other Entertainment" and to authorize food and beverage service within the building. The Commission imposed 50 conditions of approval, including Condition 49 that limits the annual number of music events with more than 250 attendees to 54, and Condition 48 that limits the annual number of entertainment events with more than 250 attendees to 79, including music events. The owner and applicant are filing this application to request a modification to Condition 48 to increase the annual number of large entertainment events from 79 to 91, while retaining the Condition 49 annual limit of 54 large music events. These additional 12 large entertainment events are contemplated to be primarily comedy shows. The owner and application seek no other modification to Motion No. 19020 and its 49 other conditions of approval.
- Concept given to the report: The Nob Hill Masonic Center, an entertainment venue with food and beverage service, operates under an existing permission whose conditions cap events with more than 250 attendees at 79 entertainment events a year, of which at most 54 may be music events. The operator wants the cap on large entertainment events raised from 79 to 91 a year, mostly for comedy shows, and keeps the limit of 54 large music events. No other change.
- Intake answers given: {"floor_area_sqft": 118000}

Triggers:

- Changing the conditions of an earlier approval: conditional at filing (stated_in_record)
- Enlarging or intensifying an existing use: conditional at filing (inferred_from_code)

## What each run said

| | Full report, end to end | Full report, conditional | Rules only, end to end | Rules only, conditional |
|---|---|---|---|---|
| alcohol | - | insufficient_information | - | insufficient_information |
| building_change_of_use | insufficient_information | insufficient_information | insufficient_information | insufficient_information |
| entertainment | insufficient_information | further_review | further_review | further_review |
| health | allowed | allowed | allowed | allowed |
| zoning_use | insufficient_information | further_review | further_review | further_review |

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

