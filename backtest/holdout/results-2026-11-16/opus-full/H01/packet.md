# H01: 2999 Mission St, San Francisco, CA 94110

Record 2024-006665CUA, filed 2024-07-23, withdrawn. Rules date 2024-07-22.

## Ground truth (decision record)

- Correct pathway: **further_review** (conditional)
- Rule coverage on the record's facts: 
- Why closed: The file shows three Incomplete Application Notices on the parent 2024-006665PRJ, dated 30 Aug 2024, 27 Sep 2024 and 18 Dec 2024. They ask for missing plan items and, in the first two, the unpaid Conditional Use fee ($1,998, then $2,869). Each says the project "will not be assigned to a planner until the items listed in the attached checklist are submitted" and that after 90 days "the application may be canceled." No hearing, motion, staff report or later correspondence. Status "Closed - Withdrawn" 2026-04-13. Most likely closed for never being completed; nothing in the file shows a zoning objection or opposition.
- Regulatory problem: no
- Concept as filed (not given to the report): Conditional Use Authorization pursuant to Planning Code Section(s) 249.60 (b)(2) to permit transfer of Type 20 license to an existing grocery /produce store of 4,647 sf.
- Concept given to the report: An existing grocery and produce store of 4,647 square feet wants to bring in an ABC Type 20 licence by transfer.
- Intake answers given: {"floor_area_sqft": 4647, "liquor_licence": "transfer_from_another_location"}

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

