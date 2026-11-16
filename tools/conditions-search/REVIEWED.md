# Reviewed labels for the conditions search page

The page's classifier decides which motions are about a food, drink or entertainment business. Two reviews, both
by AI models reading each motion (the project description in the motion PDF and in the local applications table),
not by a person, checked every motion it looked at. The decisions are in `reviewed-labels.json` and override the
classifier. Motions the classifier got right are not listed, except a few rows that record a call the classifier
already made (see "Recorded calls" below); they change nothing.

1. **Motions decided 2019 on: reviewed 2026-11-12.** One AI review read all 197 motions found (the 136 the
   classifier kept and the 61 it left out); a second pass the same day checked that list against an independent
   review (what it changed is in "Changes from the first list" at the end). 38 rows. Their rows have no `review`
   field.
2. **Motions decided 2010-2018: reviewed 2026-11-13, when the page reached back to 2010.** 291 motions found (the
   287 the classifier kept and the 4 it left out). Two Claude Haiku passes (a reader and a checker) read every
   motion against the rules below; where they disagreed, Claude Opus decided (`scripts/validation/
   review_hospitality_batch.py`). An independent audit then checked every decision against this file and corrected
   11 (9 where the reader and checker had agreed with the classifier, 2 where they had agreed on a change).
   Two of the corrections leave a motion out because the PDF Planning files under its record is another case's
   motion, so its conditions would be the wrong ones: 2015-008251CUA (2120 Greenwich St; the motion is 2015-007387CUA,
   2018 Clement St) and 2016-006961CUA (Globo, 1977B Union St; the motion is 2014.0482CVAR, 651 Geary St). 55 rows
   were added: 27 remove a motion, 26 correct a business type, 2 record a call that changes nothing. Each row's
   `review` field says who decided it.

## What counts

In: restaurants, limited restaurants, cafes, bakeries selling food, take-out food, bars, wine bars, tasting rooms,
breweries, nightclubs, live music and entertainment venues already on the page, liquor stores and other off-sale
alcohol (shown as "Other food and drink").

Out: grocery stores and supermarkets (see the grocery rule), convenience stores that do not sell alcohol, cannabis
stores and lounges, massage and spas, banks, clinics and pet hospitals, other retail, gyms, offices, community
facilities, a restaurant being converted to another use, and housing or whole-building projects where the food use
is incidental.

## The grocery rule

Grocery stores stay out (the owner's rule). What decides is the use Planning approved in the motion:

1. A General Grocery or Specialty Grocery use is out, whatever the motion is about (opening, a chain-store
   approval, an expansion, or an alcohol licence), and even with a deli, bakery or cafe inside.
2. A Liquor Store use (Planning Code § 102) is in, as "Other food and drink", also when the business calls itself a
   market.
3. A motion that also approves a food or drink use (for example a Limited Restaurant inside a gas-station store)
   is in for that use.

Applied to every grocery-type motion in the set:

| Record | Address | Store | Motion is about | Result |
|---|---|---|---|---|
| 2025-007559CUA | 1416 Haight St | Amal's Market, grocery and deli, about 2,800 sq ft | Upgrading to a full off-sale liquor license (Planning calls it a Liquor Store use) | In (rule 2) |
| 2023-002340CUA | 999 Valencia St | Valencia Whole Foods, family-owned corner grocery, about 1,700 sq ft (not the Whole Foods Market chain) | Taking over a beer and wine off-sale license (approved as a General Grocery use) | Out (rule 1) |
| 2021-009937CUA | 447 O'Farrell St | Small grocery, about 1,900 sq ft | Moving a full off-sale liquor license (approved as a General Grocery use) | Out (rule 1) |
| 2019-006951CUA | 1401 19th Ave | Chevron gas station food mart | A beer and wine off-sale license; the motion also approves a Limited Restaurant (Kal's) | In (rule 3) |
| 2021-008697CUA | 4400 17th St | Corona Heights Market and Deli | Re-opening the grocery with a deli | Out (rule 1) |
| 2022-008360CUA | 580 Green St | Luke's Local | Opening a grocery in a former bank | Out (rule 1) |
| 2018-013462CUA, 2022-008162CUA | 3995 Alemany Blvd | H Mart, with restaurants inside | Opening and expanding the supermarket | Out (rule 1) |
| 2019-021084CUA | 355 Bay Shore Blvd | Grocery Outlet | Opening the chain store | Out (rule 1) |
| 2016-000378CUA, 2019-004110CUA, 2019-004110CUA-02 | 1600 Jackson St, 2675 Geary Blvd | Whole Foods Market (the chain) | Opening the chain store | Out (rule 1) |
| 2019-001013CUA | 375 32nd Ave | Andronico's | Opening the chain store | Out (rule 1) |
| 2024-010541CUA | 1542 Haight St | Gus's Community Market | Expanding the store | Out (rule 1) |
| 2025-003445CUA | 2675 Geary Blvd | T&T Supermarket with a bakery-cafe | Opening the chain store | Out (rule 1) |
| 2021-002045CUA | 170 South Van Ness Ave | US Foods Chef'Store | Opening the chain store | Out (rule 1) |
| 2023-001114CUA | 3998 18th St | Muuu Meat, a butcher | Opening the chain store | Out (rule 1) |

The first list had removed Valencia Whole Foods and kept Amal's Market. Under the rule what decides is the use
Planning approved: Valencia Whole Foods and 447 O'Farrell St are General Grocery uses (out, rule 1), Amal's Market a
Liquor Store use (in, rule 2). To put the two grocery motions back, change their rows in `reviewed-labels.json` to
"include" with business "Other food and drink".

The same rule on the grocery-type motions decided 2010-2018 (rows added on 2026-11-13 when the page reached back
to 2010; each row's `review` field says who decided it):

| Record | Address | Store | Motion is about | Result |
|---|---|---|---|---|
| 2009.1103C | 690 Stanyan St | Whole Foods Market (the chain) | A grocery store open 24 hours | Out (rule 1) |
| 2010.0033C | 1530-1538 Haight St | Haight Street Market | Expanding the grocery into a former restaurant space | Out (rule 1) |
| 2012.1031C | 1595 Sloat Blvd | Sushi Avenue inside the Lucky grocery store | Legalizing Sushi Avenue, a formula retail Limited Restaurant | In as Restaurant or cafe (rule 3) |
| 2014-001722CUA | | Santa Clara Natural Organic Market | Moving an off-sale liquor license between two grocery stores | Out (rule 1) |
| 2016-003525CUA | 1150 Ocean Ave | Whole Foods Market (the chain) | An on-sale beer and wine license for its eating area | Out (rule 1) |
| 2017-007658CUA | 4522 3rd St | Sav Mor Market | Relocating an existing liquor establishment; the motion approves no General Grocery use (independent audit) | In as Other food and drink (rule 2) |

The counts in "Counts" give both reviews; the tables after them (added back, removed, business type corrected,
recorded calls, borderline cases, changes from the first list) are for the first review (2019 on) only. The rows of
the 2010-2018 review, with each one's reason, are in `reviewed-labels.json` and on `coverage.html` (Reviewed list).

## Building projects

A building project counts when part of the approval is for the restaurant, bar or entertainment use itself (its
hours, its liquor license, its use) and its conditions are about running that use (for example the "Eating and
Drinking Uses" or "Bona Fide Eating Place" conditions). It stays out when the food use is only a ground-floor
tenant space in a housing, hotel or office building.

## Counts

| | 2019 on (2026-11-12) | 2010-2018 (2026-11-13) | All |
|---|---|---|---|
| Motions found and reviewed | 197 | 291 | 488 |
| Kept by the classifier | 136 | 287 | 423 |
| Left out by the classifier | 61 | 4 | 65 |
| Added back by the review | 4 | 0 | 4 |
| Removed by the review | 29 | 27 | 56 |
| Kept, business type corrected (no change to the count) | 3 | 26 | 29 |
| Recorded calls that change nothing | 2 | 2 | 4 |
| **Final on the page** | **111** | **260** | **371** |
| of which with conditions | 110 | 242 | 352 |
| Rows in `reviewed-labels.json` | 38 | 55 | 93 |

`reviewed-labels.json` has 93 rows. The first review's 38: 8 "include" (4 added back, 3 business type corrections,
1 recorded call) and 30 "exclude" (29 removed, 1 recorded call). The second review's 55: 28 "include" (26 business
type corrections, 2 recorded calls) and 27 "exclude" (all removed). Of the second review's rows, 40 are calls the
reader and checker agreed on, 4 were decided by Opus where they disagreed, and 11 were corrected by the
independent audit.

Kept motions without conditions: 2018-006127CUA (2019 on, denied), and 18 decided 2010-2018 whose motion has no
conditions section (the build prints them; the README's Counts lists all 19).

Conditions: the 136 motions of 2019 on that the classifier kept carry 2,047. The 29 the review removed carry 425
and the 4 it added back carry 112 (51 Grubstake, 36 United Irish Cultural Center, 15 Domino's, 10 SusieCakes), so
that part of the page has 1,734. The 287 motions of 2010-2018 that the classifier kept carry 3,648; the 27 the
review removed carry 333, so that part has 3,315. The page has 5,049 in all. These numbers are from the build
(`review` and `removed_motions` in `data/conditions.json`).

## Added back (4)

| Record | Address | What it is | Business type | Why |
|---|---|---|---|---|
| 2015-009955CUA | 1525 Pine St 94109 | Grubstake, a restaurant with beer and wine, rebuilt on the ground floor of a new eight-story housing building and allowed to open 24 hours | Restaurant or cafe | Part of the approval is for the restaurant itself: Planning approves it to stay open 24 hours (Section 723), and its conditions include Bona Fide Eating Place, Eating and Drinking Uses and Odor Control. |
| 2018-010482CUA | 3501 California St 94118 | SusieCakes Bakery, a chain bakery approved as a limited restaurant | Restaurant or cafe | The motion approves a limited restaurant (a bakery selling food). |
| 2021-008851CUA | 728 Geary St 94109 | Domino's Pizza, a chain take-out pizza restaurant | Restaurant or cafe | The motion approves a chain restaurant selling take-out food. |
| 2022-001407CUA | 2700 45Th Ave 94116 | United Irish Cultural Center, a new community building with a restaurant, bar, ballroom and nighttime entertainment | Nighttime entertainment | The motion approves Restaurant, Bar and Nighttime Entertainment uses, and its conditions include Eating and Drinking Uses, Other Entertainment and Notices Posted at Bars and Entertainment Venues, like the Nob Hill Masonic Center already on the page. |

## Removed (29)

| Record | Address | What it is | Why |
|---|---|---|---|
| 2014.1573CUA | 2050 Van Ness Av 94109 | 63-unit apartment building with about 776 sq ft of ground-floor commercial space | A whole-building housing project; the small commercial space is incidental and the conditions are about the building. |
| 2017-004654CUA | 1901 Fillmore St 94115 | Saje Natural Wellness, an aromatherapy supply store | A retail store with no food or drink. |
| 2018-003264CUA | 2498 Lombard St 94123 | Circle K convenience store in a gas station food mart | The motion says it does not intend to sell beer or wine. |
| 2018-013462CUA | 3995 Alemany Blvd 94132 | H Mart grocery store | Grocery rule 1. |
| 2018-014905CUA | 1711 Haight St 94117 | Iyara Traditional Thai Massage | Massage, not food or drink. |
| 2019-014257CUA | 401 Potrero Ave 94110 | Circle K convenience store at a 76 gas station | A chain-store approval with no alcohol or food service. |
| 2019-015067CUA | 968 Valencia St 94110 | HUF skateboard clothing store | A clothing store replacing a coffee shop. |
| 2019-016523CUA | 313 Ivy St 94102 | Fig & Thistle, a cannabis store | Cannabis, not food or drink. |
| 2019-021084CUA | 355 Bay Shore Blvd 94124 | Grocery Outlet grocery store | Grocery rule 1. |
| 2019-021940CUA | 545 Francisco St 94133 | Restaurant space converted to a real-estate office | A restaurant converted to another use. |
| 2019-023090CUA | 1428 Irving St 94122 | Irving Pet Hospital expansion | A pet hospital. |
| 2019-023428CUA | 123 Collingwood St 94114 | LYRIC, a community center for LGBTQQ youth | A community facility; nothing in it is food, drink or entertainment. |
| 2020-007346CUA | 2284 Union St 94123 | Le Bamboo Wellness massage | Massage, not food or drink. |
| 2020-010132CUA | 150 07Th St 94103 | West Bay Pilipino Multi-Service Center | A social service and assembly use; the restaurant next door is outside the project. |
| 2021-002698CUA | 317 Cortland Ave 94110 | Cannabis store replacing a restaurant | Cannabis; a restaurant converted to another use. |
| 2021-009937CUA | 447 O'Farrell St 94102 | A small grocery moving a full off-sale liquor license | Grocery rule 1: approved as a General Grocery use. |
| 2021-008697CUA | 4400 17Th St 94114 | Corona Heights Market and Deli | Grocery rule 1: the motion re-opens the grocery; there is no alcohol in it. |
| 2021-010728CUA | 4994 Mission St 94112 | Basanova cannabis store replacing a restaurant | Cannabis; a restaurant converted to another use. |
| 2021-011365CUA | 2257 Irving St 94122 | Cathay Bank branch | A bank. |
| 2022-004128CUA | 2044 Fillmore St 94115 | RedMint massage | Massage, not food or drink. |
| 2022-008002CUA | 939 Post St 94109 | Alchemy Springs health spa | A spa with no food or alcohol service. |
| 2022-008162CUA | 3995 Alemany Blvd 94132 | H Mart grocery store expansion | Grocery rule 1. |
| 2022-008360CUA | 580 Green St 94133 | Luke's Local grocery store | Grocery rule 1: the motion opens the grocery. |
| 2022-012037CUA | 2050 Chestnut St 94123 | Mejuri jewelry store | A jewelry store. |
| 2023-002340CUA | 999 Valencia St 94110 | Valencia Whole Foods, a small family-owned grocery taking over a beer and wine license | Grocery rule 1: approved as a General Grocery use. |
| 2023-002804CUA | 450 Sutter St 94108 | Just For You Bodywork & Massage | Massage, not food or drink. |
| 2024-007477CUA | 1699 Van Ness Ave 94109 | Chase bank branch replacing First Republic | A bank. |
| 2024-009645CUA | 1345 Howard St 94103 | AutoZone auto-parts store | An auto-parts store. |
| 2025-010376CUA | 4620 Mission St 94112 | Total Wireless phone store | A phone store. |

## Kept, business type corrected (3)

These stay on the page. Their rows say "include" with the right business type, which the build reads as a
correction of the type.

| Record | Address | What it is | Was | Now | Why |
|---|---|---|---|---|---|
| 2019-017055CUA | 1881 Post St 94115 | AMC Kabuki, a multiplex movie theatre | Restaurant or cafe | Nighttime entertainment | A movie theatre, so an entertainment venue. |
| 2024-011113CUA | 401 Columbus Ave 94133 | Steps of Rome, an existing restaurant taking a full liquor license | Other food and drink | Restaurant or cafe | The motion moves a Type 47 eating-place license to an existing restaurant. |
| 2026-000475CUA | 284 Noe St 94114 | Love Potion Library, a romance bookstore and tea room with wine service | Other food and drink | Bar | The motion establishes a Bar use. |

## Recorded calls (2, no change on the page)

| Record | Address | What it is | Row | Result |
|---|---|---|---|---|
| 2025-007559CUA | 1416 Haight St 94117 | Amal's Market, a grocery and deli upgrading to a full off-sale liquor license | include, Other food and drink | Stays on the page (grocery rule 2). |
| 2023-011096CUA | 225 San Leandro Way 94127 | The Gregangelo Museum, a folk-art house museum approved as General Entertainment for tours, private events and shows | exclude | Stays off the page. |

The Gregangelo Museum is a judgment call. Planning approves it as General Entertainment, the same use as Escape SF
(2018-012330CUA), which the classifier kept. But it serves no food or drink, its hours end at 9:30 pm at the latest,
and the request was to bring back motions that are food or drink. So it stays out. Changing its row to "include"
with business "Nighttime entertainment" would put it on the page (11 conditions).

## Borderline cases left as the classifier had them

Kept on the page:

- **2019-006951CUA, 1401 19th Ave (Chevron food mart).** Off-sale alcohol at a gas-station store that also gets a
  Limited Restaurant; see the grocery rule (rule 3). (2021-009937CUA, 447 O'Farrell St, is removed: rule 1.)
- **2021-003994CUA, 3995 Alemany Blvd (Paris Baguette inside H Mart).** The approved use is the bakery-cafe itself,
  a limited restaurant, not the grocery store.
- **2019-004211CUA (Four Star Market) and 2023-011780CUA, 3233 22nd St.** Both approve a restaurant, with some retail
  or specialty grocery alongside. Kept as restaurants.
- **2019-017349CUA, 2266 Union St (Made by True).** A jerky shop approved to operate as a limited restaurant.
- **2020-001384CUA, 1650 Polk St.** A children's family entertainment center (General Entertainment) with a limited
  restaurant.
- **2020-007075CUA, 2166 Market St (The Academy).** A members' event space adding a bar use for a private club
  liquor license.
- **2018-015652CUA, 1524 Powell St (PrestigeSF).** A private social club legalized as General Entertainment.
- **2018-012330CUA, 447 Broadway (Escape SF).** An escape-room venue (General Entertainment) with no food or drink.
  Kept because entertainment venues are part of the page; see the Gregangelo Museum above for the contrast.
- **2025-005018CUA, 2007 Franklin St (SF Heritage).** A house museum, but the motion formalizes entertainment, bar
  and outdoor event uses.

Left out:

- **2025-007879CUA, 690 Van Ness Ave (Farming Hope).** An institutional use for culinary job training; the motion
  approves no restaurant or cafe.
- **2023-000361CUA, 6000 Geary Blvd (Chevron).** Approved as an automotive service use; no alcohol or food service.
- **2015-016326CUA-02 (hotel, entertainment venue and park at the Embarcadero and Broadway).** Only extends the
  deadline of a whole-site hotel, theatre and park project.
- **2014.1058CUA, 2019-017481CUA, 2016-004823CUA-02.** Housing, hotel or office buildings with a ground-floor
  restaurant; the approval is for the building and the food use is incidental. (2014.1058CUA carries the standard
  eating and drinking conditions, but its restaurant is only a likely future tenant.)
- **2020-009148CUA, 2020-006148CUA, 2021-000313CUA, 2021-007323CUA.** A coffee shop or restaurant being converted
  to a cannabis store.
- **2025-003031CUA, 312 Columbus Ave (Europa Hotel).** A hotel lobby expanding into a vacant shop; no food or drink.
- Grocery stores: see the grocery rule table.

## Changes from the first list

| Record | Place | First list | Now | Why |
|---|---|---|---|---|
| 2015-009955CUA | Grubstake, 1525 Pine St | Left out (incidental restaurant) | Added back, Restaurant or cafe | The motion approves the restaurant's 24-hour hours and carries restaurant conditions. |
| 2022-001407CUA | United Irish Cultural Center, 2700 45th Ave | Left out (building conditions) | Added back, Nighttime entertainment | The motion approves Restaurant, Bar and Nighttime Entertainment uses with their conditions. |
| 2023-011096CUA | Gregangelo Museum, 225 San Leandro Way | Added back, Nighttime entertainment | Left out | No food or drink, not nighttime. |
| 2023-002340CUA | Valencia Whole Foods, 999 Valencia St | Removed (grocery) | Removed | Grocery rule 1: approved as a General Grocery use (the first list also mistook it for the Whole Foods Market chain). |
| 2025-007559CUA | Amal's Market, 1416 Haight St | Kept, no row | Kept, with a row | Grocery rule 2, now written down and applied the same way as Valencia Whole Foods. |
| 2019-017055CUA | AMC Kabuki, 1881 Post St | Kept as Restaurant or cafe | Nighttime entertainment | A movie theatre. |
| 2024-011113CUA | Steps of Rome, 401 Columbus Ave | Kept as Other food and drink | Restaurant or cafe | A restaurant taking a Type 47 license. |
| 2026-000475CUA | Love Potion Library, 284 Noe St | Kept as Other food and drink | Bar | The motion establishes a Bar use. |

Net effect on the 2019-on motions: 111 motions and 1,734 conditions (the grocery rule as written above also takes
off 2021-009937CUA and 2023-002340CUA). With the 2010-2018 review the page has 371 motions and 5,049 conditions.


The review was done by AI models (one reading every motion, a second checking its decisions), not by a person. The grocery rule above was set by the owner on 2026-11-12 and applied by the lead.
