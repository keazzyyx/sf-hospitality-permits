# Rule table extension: binding spec (v2 of the pathway rules)

Written 2026-11-10 from the trigger inventory of the 40 backtest cases
([`../../backtest/triggers.json`](../../backtest/triggers.json)). This spec is the contract for the data
readers and for the engine. Nothing here is built yet.

Scope: the triggers that caused these 40 hearings, under the rules in force at each filing date. Every rule is
cited to the code, checked blind by a second reader, and tested.

## 1. Trigger families (ten appear in two or more of the 40)

| Rule id | Family | Cases | What decides it |
|---|---|---|---|
| T1 | New use control: the district table makes the use conditional or not permitted | 12 | District, use, story, date |
| T2 | Special district makes the use itself conditional (§ 249.60(f)(1), SoMa Youth and Family) | 6 | Overlay, use, date |
| T3 | Enlarging or intensifying an existing conditional or nonconforming use (§§ 178, 186.1, 182) | 8 | Existing use and its standing, the change proposed |
| T4 | Liquor licence in a restricted district (North Beach, Mission, Haight, Third Street) | 7 | Overlay, licence type, new or existing, date |
| T5 | Formula retail (§§ 303.1, 703.4, each table's row) | 6 | District, formula retail yes or no, use, date |
| T6 | Nighttime entertainment (table row, § 102) | 5 | District, story, entertainment kind, date |
| T7 | Use size (§ 121.2, table row) | 5 | District, floor area, new / merged / enlarged, date |
| T8 | Laundromat removal (§ 202.12, in force 2021-12-20 to about 2024-12-20) | 3 | Last use is a laundromat or dry cleaner, date |
| T9 | Outdoor activity area (§ 145.2, table row, § 202.2(a)(7)) | 3 | District, where the outdoor area is |
| T10 | Amending the conditions of a prior Conditional Use (§§ 303(e), 174) | 2 | A prior motion exists and the proposal exceeds it |
| T11 | Hours of operation (table row) | from the test cases | District, closing hour |

Seen once only, not built, counted as not covered: legacy business replacement (§ 754(c)(4)), storefront merger
control (§ 754(c)(2)), unscreened open-air use in the Waterfront SUD (§ 240.2(d)).

## 1a. Each trigger in detail (binding)

Every trigger returns one of: `principal` (it asks for nothing), `conditional`, `not_permitted`, `not_decided`
(it matters here and an input is missing: name the input), `does_not_apply`, or `code_and_practice_differ`.
"Matters here" means the district's data gives a C or NP outcome for this trigger on the rules date. A missing
input is never filled with an assumption. Controls are read from `sf_dated_controls.json` for the rules date.
Story: the stories stated. When none is stated no story is assumed (the user's decision of 2026-11-12, which
replaces reading the first story): a cell that reads differently on different stories, a rule for the First
Story only whose First Story reading asks for something or is not decided, and the first-story control of a
district the dated data does not carry (unless its table has no story columns), is `not_decided` and names
"which stories the business occupies"; the
zoning row is then insufficient information even where another trigger is conditional. A cell that reads the
same on every story is read as it reads (see docs/api-contract-memo.md, "A missing story").

- **T1 new use control.** For each § 102 use of the concept and each story read: the district's cell (or the
  governing row where the cell is NA). Does not apply to a use that already exists at the address and
  continues (that is T3's ground). District not in the dated data: the v1 table answers for Bar and Restaurant;
  other uses are `not_decided` ("the rule table does not carry this district").
- **T2 special district use control.** Mission Alcoholic Beverage SUD § 249.60(f)(1): any proposed Restaurant
  east of the western boundary of the Mission Street NCT and north of Cesar Chavez Street is conditional. In
  NCT-MISSION and NCT-24TH-MISSION the address is inside that area: `conditional`. Elsewhere inside the SUD the
  rules cannot place the address and Planning's own records treat such restaurants as permitted:
  `code_and_practice_differ`. SoMa Youth and Family SUD: a Restaurant is `conditional`. Not applied to a
  restaurant that already exists and continues.
- **T3 enlarging or intensifying an existing use.** Applies only where a business continues at the address
  (`changes_existing_business` stated, or an existing use shown by records and the same use proposed). The
  change is `enlarge`, `intensify` or both. If the existing use would be conditional or not permitted as a new
  use on the rules date: `conditional` (§ 178(c) for a conditional use; § 186.1 for a nonconforming use in an
  NC district; § 182 elsewhere, as the data's rule text states). If it would be principal: `principal`.
  Existing business with the change not stated, where the use is C or NP as new: `not_decided`.
- **T4 liquor licence in a restricted district.** One bound rule per district rule in the data, each read for
  the rules date: North Beach (a Restaurant adding licence types 02, 23, 41, 47, 49, 59 or 75 on the first
  story: conditional until 2025-12-14, nothing after); Mission (enlarging an existing liquor establishment:
  conditional; a new Bar must use a licence transferred from inside the district: a requirement, not a
  control); Haight (a new on-sale or off-sale establishment: not permitted with a capped restaurant exception
  before 2024-01-14, conditional from then); Third Street (a new on-sale establishment: not permitted; a Type
  42 in the Bayview NCD: conditional from 2025-04-07). Needs the licence type and whether the establishment is
  new: `not_decided` naming whichever is missing.
- **T5 formula retail.** `formula_retail` true: the district's formula retail control, `not_permitted` where the
  data bars formula retail for this use. False: `principal`. Missing, where the control is C or NP:
  `not_decided` ("whether the business is part of a chain"). The change-of-operator rule (§ 178(c)(3)) is
  printed as a note with its dates; the rules do not evaluate it.
- **T6 nighttime entertainment.** The concept includes Nighttime Entertainment: the district's cell by story.
  Entertainment is described but the kind is not (Limited Live Performance or Place of Entertainment), where
  the cell is C or NP: `not_decided`. No entertainment: `does_not_apply`.
- **T7 use size.** Applies to a use that is new, merged or enlarged, not to taking over an existing space
  unchanged. Floor area against the district's threshold on the rules date: below it `principal`; from it
  `conditional`; from the cap `not_permitted`. Floor area missing where a threshold exists: `not_decided`.
- **T8 laundromat removal.** In force 2021-12-20 to 2024-12-20, any district. Last use is a laundromat or dry
  cleaner and the project changes it: `conditional`. Last use not stated, rules date inside the window:
  `not_decided`. Outside the window: `does_not_apply`, with a line giving the dates.
- **T9 outdoor activity area.** Outdoor area at the front: the "in front" control. Elsewhere on the lot (rear,
  side, rooftop, parking lot): the "elsewhere" control; where the row lets an area elsewhere be principally
  permitted within the § 202.2(a)(7) limits, `not_decided` naming those limits unless the input shows they are
  met. On the sidewalk: `does_not_apply` (public right of way, a different approval). An outdoor area described
  without its place: `not_decided`. None: `does_not_apply`.
- **T10 amending an earlier approval.** `amends_prior_approval` true: `conditional` (§ 303(e)). An earlier
  Conditional Use decision is on file at the address, an existing business continues, and the input does not
  say whether the proposal exceeds a condition: `not_decided`. Otherwise `does_not_apply`.
- **T11 hours of operation.** The closing time against the district's hours windows on the rules date: C
  `conditional`; NP `not_permitted`; a minute no window covers `not_decided`. Closing time not stated, where a
  C or NP window begins before 2 a.m.: `not_decided` ("the closing time"). An existing business keeping hours
  it already lawfully keeps is not decided by the rules: the line says so.

Where the Historic Buildings rule (§ 202.11, from 2026-04-11) could change a cell, the line says so; the rules
do not evaluate it (whether the building qualifies is a determination by the Planning Director).

## 2. Inputs

Concept facts (new optional profile fields; `None` means the input did not say, and is never read as "no"):

| Field | Values |
|---|---|
| `planning_use` (derived) | bar, restaurant, limited_restaurant, nighttime_entertainment, not_covered |
| `licence_type` | ABC type number as text, e.g. "41", "47", "42", "48", "90" |
| `alcohol_transaction` | new_licence, person_to_person_transfer, premises_transfer, licence_already_held |
| `formula_retail` | true / false |
| `floor_area_sqft`, `floor_area_before_sqft` | integers |
| `existing_use_stated` | bar, restaurant, limited_restaurant, nighttime_entertainment, retail, laundromat, other, vacant |
| `changes_existing_business` | none, enlarge, intensify, enlarge_and_intensify |
| `story` | first, second, third_or_above, basement |
| `closing_hour` | "HH:MM" |
| `entertainment_kind` | none, limited_live_performance, place_of_entertainment |
| `outdoor_area` | none, front, rear_or_side, rooftop, parking_lot, sidewalk |
| `amends_prior_approval` | true / false |
| `seats` (exists) | integer |

Site facts, from records: zoning district; overlays; licences at the address as they stood on the rules date;
prior Conditional Use motions at the address; census tract.

`rules_date`: the date whose rules apply. Today for a live report; the day before filing in the backtest.

## 3. The dated control data

One file, `apps/api/app/memo/data/sf_dated_controls.json`, read by the engine. Every entry carries the code
section, the ordinance and effective date of each change since 2022-01-01, a verbatim quote of the row or
sentence relied on, the URL read and the date read.

```json
{
  "districts": {
    "NCD-POLK": {
      "section": "723",
      "rows": {
        "bar":                     [{"from": null, "to": null, "first": "C", "second": "NP", "third": "NP", "note": "", "ordinance": null, "quote": "…", "url": "…", "read_on": "2026-11-10"}],
        "restaurant":              [ … ],
        "limited_restaurant":      [ … ],
        "nighttime_entertainment": [{"from": null, "to": "2024-05-26", "first": "C", "second": "NP", "third": "NP", …}, {"from": "2024-05-27", "to": null, "first": "P", "second": "C", "third": "NP", "ordinance": "Ord. 85-24, File 231221", …}],
        "formula_retail":          [{"from": null, "to": null, "control": "C", "applies_to": "all", …}],
        "use_size":                [{"from": null, "to": "2025-10-05", "principal_below_sqft": 2000, "not_permitted_from_sqft": 4000, "exemption": "", …}, …],
        "outdoor_activity_area":   [{"from": null, "to": null, "in_front": "P", "elsewhere": "C", "elsewhere_principal_if_202_2_a_7": false, …}],
        "hours":                   [{"from": null, "to": null, "windows": [["P", "06:00", "02:00"], ["C", "02:00", "06:00"]], …}]
      }
    }
  },
  "special_districts": { "<overlay key>": {"rules": [{"rule": "…", "applies_to": "…", "control": "C", "from": …, "to": …, "section": "…", "quote": "…", …}]} },
  "citywide": { "laundromat_removal": [ … ], "enlarge_or_intensify": [ … ], "amend_prior_conditions": [ … ], "neighbourhood_notification": [ … ], "formula_retail_definition": [ … ] }
}
```

- Cell values: `P`, `C`, `NP`, or `NA` (the table has no such row; say what governs instead in `note`).
- `from` null = already in force on 2022-01-01. `to` null = in force today. Versions must not overlap or leave
  a gap.
- Use size: a use below `principal_below_sqft` is P; from there up it is C; from `not_permitted_from_sqft`
  (null = no cap) it is NP.
- A version is established by comparing the text in force in early 2022 (an archived copy of the section) with
  today's text; where the cell differs, the ordinance and its effective date come from the section's
  legislative history.

Districts to carry: the 23 districts of the 40 cases and the 9 others in the pathway test fixture: C-2, CRNC,
CVR, CCB, NCD-POLK, NCD-LOWER POLK STREET, NCT-FILLMORE, NCD-NORTH BEACH, NCD-BROADWAY, NCT-MISSION,
NCT-24TH-MISSION, NCT-VALENCIA, NCD-IRVING, NCD-INNER SUNSET, NCD-INNER CLEMENT, NCD-CASTRO, NCD-HAIGHT,
NCD-WEST PORTAL, NCD-LAKESIDE VILLAGE, NCD-BAYVIEW, NCD-PACIFIC, NC-1, NC-2, NC-3, NCT-3, RC-4, RM-3, RH-2,
MUR, UMU, C-3-G, RH DTR. Any other district stays "not covered" for the new rows.

## 3a. Referral steps are not approvals

The data keeps two kinds of rule apart, and the report never mixes them:

- `approval_required`: a permit, licence or authorization the operator must obtain (a Conditional Use
  Authorization, an ABC licence, a Place of Entertainment permit, a health permit, a building permit).
- `referral_step`: a step inside an approval where one agency sends the application to another for review (the
  Entertainment Commission sending an application to Planning; ABC's application going to Planning and Police;
  the health permit going to Planning).

Each is dated on its own. Removing a referral shortens an approval; it does not remove the approval. A row's
status is set only by `approval_required` rules. Referral steps are listed under the row as steps, with the
date from which each applies or stopped applying.

Ordinance 118-25 (Board of Supervisors File No. 250537, "Police Code - Entertainment Permits") is the test case.
Two readers each read the ordinance text as published by the Board, without seeing the other's notes, and agree:

- **Dates:** first reading 8 July 2025, finally passed 15 July 2025, approved by the Mayor 17 July 2025. The
  ordinance says only "30 days after enactment". The Board's ordinance table and the Police Code's cover page
  give 17 August 2025 as the effective date; the City's PermitSF page gives 16 August. The data uses 17 August,
  so each removed step ends on 16 August 2025.
- **Referrals removed:** the Department of Building Inspection referral for Place of Entertainment permits
  (§ 1060.2(b)(3)) and Extended-Hours Premises permits (§ 1070.2(b)); the Planning Department referral for
  Limited Live Performance permits (§ 1060.2.1(b)) and Fixed Place Outdoor Amplified Sound permits
  (§ 1060.2.2(b)).
- **Referrals narrowed:** for Extended-Hours Premises permits, no referral to Public Health or Fire where the
  applicant already holds that department's current permit.
- **Referrals kept:** Police for all four; Planning for Place of Entertainment and Extended-Hours Premises.
- **All four permits are still required.** Only review steps inside them changed.
- **Approvals removed outright:** ball or ring throwing game permits (§ 1021) and dance hall and dance permits
  (§§ 1022 to 1027). The ordinance's title also names masked ball permits, but that permit (§ 1029) had already
  been deleted by Ordinance 250-23, effective 14 January 2024.
- **Earlier, by Ordinance 250-23 (effective 14 January 2024):** the Public Health referral for Fixed Place
  Outdoor Amplified Sound permits was removed, and the exception to the Building Inspection referral for Place
  of Entertainment permits was widened.

Not read: today's text of the Police Code sections themselves (the code site refuses automated requests and no
archived copy exists), so "still in force today" for the surviving referrals rests on the chain of ordinances,
not on today's printed code.

## 4. How a row's status is set

Zoning and use row: every trigger is evaluated and listed with its own rule line.

- any trigger not permitted -> **Not permitted**
- else any trigger conditional -> **Further review** (Conditional Use Authorization), naming each trigger
- else a trigger that matters in this district cannot be decided because an input is missing ->
  **Insufficient information**, naming the missing input
- else the Code and Planning's own records are known to differ here -> **Further review: Code and Planning
  practice differ**
- else -> **Allowed**

A missing input never becomes an assumption. A trigger "matters in this district" when the district's data has
a C or NP outcome for it on the rules date.

Alcohol row:

- zoning row Not permitted -> Not permitted (Business and Professions Code § 23790)
- licence type or transaction type not given -> **Insufficient information**, naming which
- a licence rule of a restricted district applies (T4) -> its control: conditional -> Further review; a stated
  requirement that could stop it (Mission: a new Bar must use a licence transferred from inside the district) ->
  Potential blocker
- the census tract is over its authorised number -> **Further review: public convenience or necessity finding
  likely required** (Business and Professions Code § 23958.4). Never a blocker and never Not permitted on this
  fact alone
- otherwise -> Further review (investigation, notice, referral)

Change of use is three separate answers, each yes / no / not established, each with its own rule line:

1. **Planning Code change of use**: the last lawful use (from records, else as stated) against the proposed
   § 102 use.
2. **Building Code change of occupancy**: proposed occupancy group from the use and the stated occupant count
   against the existing group. The existing group is not in public records, so this is "not established" unless
   stated.
3. **Neighbourhood notification**: whether the change needs notice under the Planning Code as in force on the
   rules date.

Building row: any of the first two is yes -> Further review; both no -> Allowed; otherwise Insufficient
information, naming what is missing.

Every report carries one fixed line: physical and cost issues (ventilation, exits, accessibility, landlord
consent) are outside what public records can show.

## 5. Coverage of the 40

For each case the rules are run on the facts in the decision record, at the filing date. A case is **fully
covered** when the rules return every trigger in the inventory with the right control, **partly covered** when
they return some, **not covered** when they return none. Cases whose deciding fact is not in the project
description are listed separately: the rules cover them, the input does not.
