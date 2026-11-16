# Holdout set: 20 new cases for scoring rule fixes

Written 2026-11-12, before any rule was changed. The 40 backtest cases (`../cases.yaml`) showed where the rules
disagree with the record. Rule fixes will be tuned on those 40. This set is for scoring the fixes on cases the
fixes were not tuned on. Nothing in this folder may be edited to fit the tool once it is committed.

## 1. Who is eligible (written before the candidates were read)

A record is eligible when all of these hold:

1. It is a San Francisco Planning **Conditional Use Authorization** record (the record number ends in `CUA`,
   with or without a `-01`, `-02` suffix).
2. It was **filed from 2022-01-01 to 2025-12-31**.
3. It is about **one food, drink or entertainment premises**: a restaurant, limited restaurant, bar, liquor store
   or other off-sale alcohol, nighttime or general entertainment, or something similar (a cafe, a brewery taproom,
   an event venue). A whole-building project with a restaurant somewhere in it is not eligible. Neither is a
   cannabis shop, a massage or fitness business, a grocery or other store whose alcohol is not part of the request,
   a phone store, an office, or housing.
4. It **closed with a decision record**: approved by a Planning Commission motion, or withdrawn or cancelled with a
   file that shows what happened (status, dates, related records). A case still open or pending is not eligible.
   A disapproval would be eligible; there is none in the records.
5. It is **not one of the 40** in `../cases.yaml`.

Eligibility is decided from the record number, filing date, status, project description and the premises label.
How the tool behaves on a case plays no part. Nobody ran a report or a rule on any candidate, and the rule code
(`apps/api/app/memo/`) was not opened while this set was built.

The `reserves` listed at the end of `../cases.yaml` are not among the 40. They are eligible like any other record
if they meet the rules above.

## 2. The pool

Starting query on the local copy (`sfhp_local`): Planning records whose number contains `CUA`, labelled
premises in `record_labels`, filed 2022-01-01 to 2025-12-31, any record kind. That gives 83 records. 40 are the
backtest cases. 43 are not.

Records the labels missed were looked for in two ways: every 2022-2025 CUA record not labelled premises whose
description names a food, drink or entertainment word, and every withdrawn or cancelled 2022-2025 CUA record not
labelled premises (145). One eligible record was found that way: 2023-011096CUA (a house turned into a General
Entertainment use, Motion 21636).

**Eligible: 25.** 23 decided by a Planning Commission motion and 2 withdrawn. The full list, with each record's
order key, is in `selection.json`.

**Excluded: 24**, each for the reason below (also in `selection.json`).

| Record | Why not eligible |
|---|---|
| 2021-012886CUA | Cannabis shop |
| 2022-003199CUA | Pending (On Hold) |
| 2022-004128CUA | Massage |
| 2022-006364CUA | Eyewear store (Warby Parker) |
| 2022-007253CUA | Pending (Submitted) |
| 2022-007603CUA | Massage |
| 2022-008002CUA | Health spa |
| 2022-008162CUA | Grocery store expansion (H Mart); alcohol not part of the request |
| 2022-008360CUA | Grocery store (Luke's Local) in a former bank; sells alcohol, but alcohol is not part of the request |
| 2022-012037CUA | Jewellery store (Mejuri) |
| 2023-002411CUA | A restaurant and banquet hall to become a grocery store; the new use is not food or drink service |
| 2023-002804CUA | Massage |
| 2023-003652CUA | Pending (On Hold) |
| 2024-000669CUA | Beauty salon |
| 2024-005019CUA | Pending (Accepted) |
| 2024-006280CUA | Massage |
| 2024-007477CUA | Bank (Chase taking over First Republic), labelled restaurant by mistake |
| 2024-009645CUA | Auto parts store (AutoZone, Motion 21694) |
| 2025-010376CUA | Phone store (Total Wireless) |
| 2018-001788CUA | Found outside the labels. Cancelled. 554 Fillmore St, the former Sacred Heart Church: the description names the nave as a space for entertainment, arts and recreation, so it was first counted eligible. The file then showed the CUA is one part of a whole-building conversion with seven homes and offices (plan check letters of 2023-05-10 and 2024-01-08). Excluded under rule 3 before any ground truth was written. |
| 2022-001407CUA | Found outside the labels. A whole-building cultural centre (pool, library, museum, offices, gym) with a pub and a restaurant inside |
| 2025-003445CUA | Found outside the labels. A supermarket (T&T) with a small bakery-cafe inside |
| 2025-003391CUA | Found outside the labels. A food and drink space becoming a music studio |
| 2025-007879CUA | Found outside the labels. Nonprofit culinary job training (an institutional use) |

Four withdrawn or cancelled records name only a use size or "formula retail" with no use (2023-007950CUA,
2023-008718CUA, 2023-009589CUA, 2025-002632CUA). No other record at those addresses names a food, drink or
entertainment use, so they are not eligible on the record text.

The 7 `reserves` in `../cases.yaml` were checked like any other record, and all 7 are eligible (2011.0097CUA-02,
2023-000022CUA, 2023-011780CUA, 2024-002799CUA, 2024-006641CUA, 2024-006665CUA, 2025-005018CUA). Outside the rule
code, which was not opened, they appear only in `../cases.yaml`, the conditions search data and, for
2011.0097CUA-02, a hearings-parser test fixture. None is in the API tests.

## 3. How the 20 were picked

The rule was fixed before any case's outcome was read in detail:

1. Order key: `sha256(record number + "holdout-2026-11-12")`, as hex, smallest first.
2. Keep the 40's mix where the pool allows. The 40 are 25 decided and 15 that did not reach approval, so 20 would
   be about 12 decided and 8 not. Take every eligible case that did not reach approval, up to 8, in key order.
3. Fill the rest of the 20 with decided cases in key order.

Only **2** eligible cases did not reach approval, so the set is **18 decided and 2 withdrawn**. That is fewer
non-approvals than the 40 have: the 40 already used 15 of the 17 hospitality CUAs filed 2022-2025 that were
withdrawn or cancelled. Scores on the holdout will say little about cases that did not reach approval.

The next five decided cases in key order are spares, used only if a selected case turns out to be ineligible
(and the reason is written down): 2024-007818CUA, 2024-003662CUA, 2015-002658CUA-02, 2023-005339CUA,
2025-010554CUA. (2024-003662CUA has no motion in the local cache. The record's document list names it as
M-21680, which would have to be fetched first.)

## 4. The 20 cases

Motion PDFs are cached at `$LOCAL_DATA_DIR/raw/sf_planning_hearings/pdf/<file>`; the public link is
`sources.motion_pdf` in `cases.yaml`. Each motion number was read from the first page of its PDF (`motions.json`),
and each PDF says "hereby APPROVES". The H01 and H02 files are cached in `$LOCAL_DATA_DIR/raw/holdout_files/`.

"Net result" is the zoning answer at the filing date, from `triggers.json`. A family marked "(inferred)" is not named
in the decision record; it follows from the code and the facts. "(unclear)" means the code text at filing could not
be read with certainty.

| Id | Record | Address | Outcome | Net result | Trigger families | Decision record |
|---|---|---|---|---|---|---|
| H01 | 2024-006665CUA | 2999 Mission St | Withdrawn 2026-04-13 | conditional | alcohol_licence_in_restricted_district | Three Incomplete Application Notices on 2024-006665PRJ |
| H02 | 2024-006641CUA | 3400 Cesar Chavez St | Withdrawn 2025-01-15 | not_permitted | alcohol_licence_in_restricted_district (inferred) | Application, CU supplement and intake checklist of 2024-006641PRJ |
| H03 | 2024-001899CUA | 1657 Powell St | Approved with conditions 2024-09-12 | conditional | new_use_control | Motion 21605, `dc4c5a0f1fefc98b03626662.pdf` |
| H04 | 2022-004869CUA | 3352 Steiner St | Approved with conditions 2023-03-16 | conditional | formula_retail (baseline stated; change-of-operator sub-rule inferred) | Motion 21275, `b5a1c279c324843ab73adc2f.pdf` |
| H05 | 2025-005018CUA | 2007 Franklin St | Approved with conditions 2025-09-25 | conditional | landmark_use_in_residential_district, nighttime_entertainment, outdoor_activity_area | Motion 21820, `cf98ce0bf30954a7894f0233.pdf` |
| H06 | 2025-003933CUA | 620 Jones St | Approved with conditions 2025-10-02 | conditional | amend_prior_conditions, enlarge_or_intensify_existing_use (inferred) | Motion 21839, `cc7185a67f7d88fc532c6eb0.pdf` |
| H07 | 2023-011096CUA | 225 San Leandro Way | Approved with conditions 2024-10-24 | conditional | landmark_use_in_residential_district | Motion 21636, `2591f06e2ddf271b6484eee6.pdf` |
| H08 | 2011.0097CUA-02 | 1423 Polk St | Approved with conditions 2024-11-14 | conditional | amend_prior_conditions, enlarge_or_intensify_existing_use | Motion 21646, `a927f667c0d67262db12c3c1.pdf` |
| H09 | 2023-000022CUA | 786 Lombard St | Approved with conditions 2024-02-22 | conditional | legacy_business_replacement | Motion 21522, `745e176afbfac2f4d837ad24.pdf` |
| H10 | 2023-002340CUA | 999 Valencia St | Approved with conditions 2023-07-27 | conditional | alcohol_licence_in_restricted_district | Motion 21370, `94810a5b8e80db871c6774df.pdf` |
| H11 | 2013.0530CUA-02 | 1301 Van Ness Ave | Approved with conditions 2025-10-16 | conditional | amend_prior_conditions | Motion 21845, `4f2d24d0b688140685e1752a.pdf` |
| H12 | 2023-011780CUA | 3233 22nd St | Approved with conditions 2024-03-07 | conditional | new_use_control, new_use_control_special_district | Motion 21531, `8e7c1ebc442509338d818576.pdf` |
| H13 | 2024-004781CUA | 1457 Haight St | Approved with conditions 2024-09-12 | conditional | alcohol_licence_in_restricted_district | Motion 21606, `b41b31914ac2b3e6064f51ce.pdf` |
| H14 | 2022-001116CUA | 1548 California St | Approved with conditions 2022-04-28 | conditional | new_use_control | Motion 21107, `d0356e19d76c533cb3dccaeb.pdf` |
| H15 | 2025-007559CUA | 1416 Haight St | Approved with conditions 2025-12-11 | conditional | alcohol_licence_in_restricted_district | Motion 21879, `f8d89ffb6b9ed2b4d9189ba7.pdf` |
| H16 | 2024-009436CUA | 1210 9th Ave | Approved with conditions 2025-01-23 | conditional | formula_retail | Motion 21672, `8c207b4c90d44c262346ee82.pdf` |
| H17 | 2022-009099CUA | 1111 California St | Approved with conditions 2023-07-13 | conditional | amend_prior_conditions, enlarge_or_intensify_existing_use (inferred) | Motion 21356, `9ac1339b5a5dbfea2eba412d.pdf` |
| H18 | 2025-000941CUA | 3065 16th St | Approved with conditions 2025-04-10 | conditional | new_use_control | Motion 21723, `f323d5663f7871d4c3748fb6.pdf` |
| H19 | 2024-002799CUA | 906 Broadway | Approved with conditions 2025-10-02 | conditional | landmark_use_in_residential_district | Motion 21838, `a7ef4e3c95909403631bc54a.pdf` |
| H20 | 2023-008363CUA | 1567 Sloat Blvd | Approved with conditions 2024-03-21 | conditional | formula_retail, hours_of_operation, new_use_control_special_district (unclear) | Motion 21536, `15723ae819c9ba83aeb19bde.pdf` |

Four of the 18 decided cases change the conditions of an earlier approval (H06, H08, H11, H17). The 40 have such
cases too (D17, D24). Two families are new in the holdout and have no rule yet: `landmark_use_in_residential_district`
(H05, H07, H19) and `hours_of_operation` (H20). `legacy_business_replacement` (H09) has no rule either.

## 5. How the cases were read and settled

Two readers read every case on their own (`reading-A.json`, `reading-B.json`). Neither saw the other's work, the
rule code (`apps/api/app/memo/`) or any report. Each wrote the triggers, the input facts (only what the neutral
text says), the record facts (what the decision record says), the intake answers and an audit of the neutral text.

Where the readings differed, the adjudicator went back to the decision record (the motion PDFs, and for H02 the
application) and settled each point. Every settlement is written down:

- **Triggers:** `triggers.json`, each case's `settlement` (what differed, what the record says, which reading was
  kept). The readings agreed on the trigger families for 13 cases and differed for 7 (H05, H06, H07, H08, H13,
  H17, H19). Most differences were labels. The real ones: whether § 178 (enlarging or intensifying a conditional
  use) is a trigger when a motion amends an earlier approval (H06, H08, H17), settled the way the 40 settled D17,
  D20 and D24; and whether the Haight Restaurant row counts on its own (H13), settled as D19. Reader A's code
  reading is the base, because reader B marked several "changed since filing" points as not checked.
- **Input and record facts:** `inputs.json`, `input_facts_readings_differed` and `record_facts_settled` (field,
  first reading, second reading, answer, which reading was kept, source, why). The local ABC licence copy and other
  data outside the decision record were not used for record facts.
- **Intake answers:** where the readings differed (H02, H06, H08, H10, H13, H17, H18), the note in
  `intake_answers_notes` says what was kept and why.
- **H02 why closed:** changed from "reason unknown" to "use not permitted, inferred", as N09 of the 40: the request
  as filed (a new Type 21 in the Mission Alcoholic Beverage SUD) had no path under § 249.60. The file does not
  state the reason.
- **Rules date:** the day before the filing date on the record, as for the 40.

Open points are listed in `triggers.json` (`notes.open_points`): the designation date of Landmark No. 318 (H07),
the Lakeshore Plaza restaurant control before 2024-01-14 (H20), the North Beach liquor licence clause the H09 motion
is silent on, the handwritten H02 floor area, and one agreed value that differs from a 40 convention (H15).

### Changes to the neutral texts

The audits flagged three texts and noted two more. Each change is recorded on the case in `cases.yaml`
(`concept_input_edit`, with the old text); `concept_as_filed` is unchanged.

- H10: "Whole Foods on Valencia Street" read like the national chain. Now "Valencia Whole Foods", the record's name.
- H15: "off-sale liquor establishment" is the Haight RUSD's own category name. Now "a new business ... that sells
  liquor to take away".
- H18: "a general entertainment use" restored from the description, as H07 and H19 keep it.
- H19: "from an institutional use" restored from the description.
- H05: the sentence about revenue for the landmark was flagged and kept: it is the applicant's stated reason, not the
  approval sought, a code section or the outcome (`concept_input_audit` on the case).

## 6. Using the holdout in the harness

The backtest reads these files with `--case-file`; the defaults still read the 40:

    cd apps/api && .venv/bin/python -m app.backtest.run --case-file ../../backtest/holdout/cases.yaml ...

The prompt scan (`app.backtest.scan`) was removed with the memo writer on 2026-11-12. It scanned the prompts of the
writer's stages, which are gone. It is kept on the branch `writer`.

Inputs and motion numbers come from this folder, so the leak guard refuses a request that carries a holdout case's
own record, project or motion number. Results go to `holdout/results/` unless `--results-dir` says otherwise. This
folder has no `coverage.json` (writing one runs the rules), so the trigger inventory is read from `triggers.json`.

Checked on 2026-11-12, after the files above were written and with no API use (before the writer was removed): the
prompt scan of all 20 cases found no case's own number in any prompt. The only later date was 2024-12-20, the
laundromat rule's end date written in the rule text, the same one the 40's scan shows. A dry run of H02 and H08 with a scripted model sent nothing the
leak guard refused and no later date. Their rule outputs were deleted unread.

## 7. Freeze

Once committed, nothing here is changed to fit the tool. A case found to be ineligible is swapped for the next
spare, with the reason written here. A mistake in reading a record is corrected with a dated note saying what
changed.

**While rules are being fixed, these 20 cases must not be opened.** Do not read their records, triggers, facts or
any report on them, and do not run a rule, a report or the backtest on them, until the fixes are done and the scored
run starts. The fixes are tuned on the 40 only. No rule may be tuned on these 20 cases. Score the fixes on them once.
