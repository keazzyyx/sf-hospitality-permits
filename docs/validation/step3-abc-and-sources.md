# Step 3: citywide ABC licences, referrals as the dated application list, and three more sources

Run 2026-11-10. Everything here is local: the citywide ABC pull sits in the local table `abc_export_sf`, and
nothing was written to production.

## 1. Citywide ABC licences next to production

Source: ABC's Daily Data Export of 2026-11-09, filtered to San Francisco.

| | Citywide export (local) | Export, ZIP 94110 only | Production today |
|---|---|---|---|
| Rows (one per licence type on a file) | 5,538 | 539 | 542 licence types on 439 rows |
| Files (premises licences) | 3,926 | 437 | 439 |
| Licence types | 51 | — | — |
| ZIP codes covered | all of SF | 94110 | 94110 only |

Production holds one ZIP code. The two extra production files are licences that have left the export since they
were loaded.

| Licence type | Citywide rows | of which active | pending | ZIP 94110 | Production |
|---|---|---|---|---|---|
| 41 On-sale beer and wine, eating place | 1,726 | 1,616 | 83 | 231 | 232 |
| 47 On-sale general, eating place | 1,091 | 1,010 | 43 | 76 | 76 |
| 21 Off-sale general | 669 | 627 | 23 | 82 | 82 |
| 58 Caterer's permit | 549 | 510 | 28 | 39 | 39 |
| 48 On-sale general, public premises (bar) | 439 | 421 | 10 | 51 | 51 |
| 20 Off-sale beer and wine | 146 | 132 | 6 | 12 | 12 |
| 68 Portable bar | 90 | 89 | 1 | 2 | — |
| 66 Controlled access cabinet | 75 | 75 | 0 | 0 | — |
| 17 Beer and wine wholesaler | 71 | 68 | 3 | 3 | — |
| 42 On-sale beer and wine, public premises | 65 | 60 | 4 | 2 | — |
| 41 other types | 617 | | | | |

| Status in the export | Citywide rows | Production (439 rows) |
|---|---|---|
| Active | 5,178 | 374 |
| Pending | 240 | 19 |
| Surrendered | 73 | 3 |
| Revocation pending | 24 | 2 |
| Suspended | 18 | 3 |
| Rule 64(b) | 5 | 1 |
| Cancelled, expired, auto-revoked (from the licence detail page, not the export) | 0 | 37 |

**The export has no withdrawn, denied or cancelled applications.** It is a list of licences that exist today plus
the 240 pending. Every non-pending ABC row in production has the outcome "approved". ABC rows are therefore a
grant-only source and cannot go into any rate.

## 2. Planning's ABC referrals as the dated list of applications

Planning reviews most ABC applications as a referral, which has a filing date. `scripts/validation/
abc_referral_match.py` matches each ABC referral filed since 2019 (premises records, kind "agency referral", text
naming ABC or a licence type) to the citywide export by street address.

| Filed | Referrals | No licence found | Nearby address or business name | Address only | + licence type | + issued after filing, or pending | No usable address |
|---|---|---|---|---|---|---|---|
| 2019 | 253 | 53 | 22 | 18 | 11 | 143 | 6 |
| 2020 | 126 | 22 | 10 | 10 | 10 | 66 | 8 |
| 2021 | 165 | 20 | 12 | 3 | 13 | 111 | 6 |
| 2022 | 152 | 13 | 10 | 7 | 12 | 110 | 0 |
| 2023 | 198 | 24 | 9 | 4 | 14 | 145 | 2 |
| 2024 | 154 | 24 | 10 | 2 | 11 | 106 | 1 |
| 2025 | 164 | 13 | 9 | 5 | 23 | 113 | 1 |
| 2026 | 102 | 7 | 1 | 0 | 4 | 89 | 1 |
| **Total** | **1,314** | **176** | 83 | 49 | 98 | 883 | 25 |

- **1,113 of 1,314 (85%) match a licence that exists today.** 883 (67%) match at the strictest level: same
  address, the licence type the referral names, issued after the referral was filed or still pending.
- **176 (13%) have no licence today**, and 25 have no usable address.
- "No licence today" is not "never issued". The hand check below shows why.

### Hand check of 20 non-matches

20 random referrals with no licence at the address under the first, stricter address rules (seed 20261110), each
looked up on ABC's address search, which also shows closed licences.

| Result | Count | Cases |
|---|---|---|
| Active licence, address written differently | 11 | 515 Broadway, 1396 La Playa, 303 2nd St #186, 409 Gough, 665 Chestnut, 553-561 Geary (Swig), 1 South Park (The Farmacy), 2312 Irving (Easy Money), 1538 Fillmore (Origin), 1800 Divisadero, 418 Geary |
| Issued, later closed | 3 | 692 Sutter (L'Ottavo, cancelled), 1551 Ocean (Homran, cancelled), 59 9th St (Sunset Squares, automatically revoked) |
| Never issued, by ABC's record | 2 | 1145 Polk, 1826 Buchanan |
| Could not resolve | 4 | 693 14th St, 920 North Point (two referrals), 345 3rd St |

The 11 false non-matches came from unit numbers, two-address lines, a missing street suffix ("Broadway"), "South"
against "S", and a neighbouring street number. I loosened the address rules for these and added the nearby-address
and business-name level; that is the table above. After the fix, the 176 remaining should be mostly the last three
rows of this table: by the sample's proportions (3 closed, 2 never issued, 4 unresolved), about a third issued
and later closed, about a fifth never issued, and the rest unknown. That is 9 cases, so treat it as a direction,
not a rate.

What this means for the report: a referral with no licence today is a count we can print ("176 of 1,314 referrals
filed since 2019 have no licence today"), not a failure rate. The withdrawn and denied applications themselves
come from the ABC daily reports (Step 1b).

## 3. ABC Census Tract Authorizations

**Yes: it gives the number of licences authorized per census tract.** The report lists, for every tract, the
tract population and the number of on-sale and off-sale licences authorized, from the county ratio (San Francisco:
one on-sale licence per 288 people, one off-sale per 1,183; figures as of September 2026). Saved as
[`abc-census-tract-authorizations-sf-2026-09.csv`](abc-census-tract-authorizations-sf-2026-09.csv): 244 tracts.

Counting today's active licences per tract from the export against it, 74 tracts are over their authorized
on-sale number and 98 over their off-sale number. The count of which licence types are on-sale is my approximation;
ABC does not publish its own per-tract count in this report. The 995 Valencia tract (208.01, population 3,618) is
authorized 12 on-sale and 3 off-sale licences and has about 27 active on-sale licences.

This is what makes a new licence need a "public convenience or necessity" finding, so it belongs in the alcohol
row of the report as a verified fact. Not built.

## 4. Entertainment Commission agendas and minutes

Full report: [`research/entertainment-commission-minutes.md`](research/entertainment-commission-minutes.md).

- **Usable for outcomes.** Meeting pages on sf.gov from July 2022, Archive-It before that. About 85 to 115 permit
  decisions a year.
- In 110 decisions sampled: 102 approved, 7 continued, 1 denied, 0 withdrawn. Two continued items never came back.
- **Conditions are in the staff memos**, not the minutes; confirmed only for October 2026.
- Permits decided by staff never reach the minutes, so the minutes are the contested or larger cases only.
- This would give the entertainment row real outcomes (the current permits dataset is grant-only), but denials are
  about 1 in 100. Not built.

## 5. Board of Supervisors liquor files (Legistar)

Full report: [`research/legistar-liquor-files.md`](research/legistar-liquor-files.md).

- The Legistar API stops at December 2018. 2019–2026 files are on `sfbos.org/resolutions-<year>`.
- Adopted "Liquor License" resolutions per year, 2019 to 2026: 23, 21, 16, 20, 25, 31, 18, 4 (2026 partial).
- The resolutions quote the Police Department's recommended conditions word for word.
- They cover mostly licence types 20, 21, 42, 48, 64 and 90: liquor stores, bars and venues, not restaurants.
- **"Adopted" does not mean approved.** The Board also adopts resolutions that the licence would *not* serve public
  convenience (Resolutions 42-19 and 200-19). The outcome has to be read from the title.
- The Board only recommends conditions to ABC; ABC decides.
- Small, clean and dated. Useful for the bar and liquor-store pathway. Not built.

## 6. Base-rate rule

The report prints **counts, not rates, unless there are 10 or more dated comparables with known outcomes**, and
always prints the N. A rate never comes from a pool that includes:

- **grant-only sources**: ABC licences (above) and the Entertainment Commission permits dataset; a pool of
  licences that exist is 100% "approved" by construction;
- **undated rows**: records with no filing date.

Rows left out for either reason are counted and shown ("excluded: 14 grant-only, 3 undated"). This is implemented
in the report's base-rate block as part of Part 3.

| Pathway | Dated records with known outcomes today | Rate allowed? |
|---|---|---|
| Conditional use | 162 (41 failures) | Yes, citywide; per neighbourhood only where N ≥ 10 |
| Planning referrals (ABC, health, entertainment) | 1,240 / 1,373 / 270 | Yes, but they record Planning's answer, not the agency's |
| ABC licence | 0 until Step 1b | No. "No outcome history for this pathway yet." |
| Entertainment permit | 0 | No. Same line |
