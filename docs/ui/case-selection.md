# Which case the scroll story tells

**Choice: Julius' Castle, 302 Greenwich Street, Telegraph Hill.** Record 2016-001273CUA, Planning Commission Motion No. 19958, adopted 6 July 2017 by 7 votes to 0, with 22 conditions.

Runners-up: Preservation Hall West (777 Valencia Street) and Giordano Bros. (1784 Union Street). Fact sheets: `apps/showcase/src/data/story.json` (the runners-up's are not part of this repository).

## Method

1. **Score all 352 motions with code**, from `conditions.json` and the text of each PDF. Points for each kind of condition present (hours, noise, outdoor, odour, garbage, liaison, alcohol and so on), for conditions written for that case alone, for vivid words in them (patio, roof, amplified, queue), for a well-known district, for signs of an eventful hearing (dissent, continuance, opposition, petitions), for a business name, and for exact page numbers. Points off for formula retail and cannabis. Scores ran from 3 to 59, median 20.
2. **Search every motion for well-known names**, which the score cannot see.
3. **Shortlist 12 and read them.** The top three cover to cover; for the other nine, the preamble, site and project descriptions, public comment, decision page and every condition.

Left out before reading: a formula-retail restaurant (531 Castro Street), a housing project where the restaurant is a side note (1525 Pine Street), two large venues with unreadable or inexact pages (1111 California Street, 429 Castro Street), and a bar whose liaison condition names a private person (3111 Fillmore Street).

## Shortlist

| Record | Business | Where | Adopted | Conditions (case-specific) | Vote | Score rank | After reading |
|---|---|---|---|---|---|---|---|
| 2016-001273CUA | Julius' Castle | Telegraph Hill | 2017-07-06 | 22 (8) | 7–0 | 31 | **Chosen** |
| 2010.0710C | Preservation Hall West | Valencia Street | 2010-11-18 | 25 (17) | 6–0 | 4 | Runner-up |
| 2009.0996C | Giordano Bros. | Union Street | 2010-02-25 | 18 (12) | 6–0 | 1 | Runner-up |
| 2009.0342C | Medjool | Mission Street | 2011-09-08 | 18 (7) | 5–1 | 11 | Vivid rooftop conditions, but an enforcement story with named opponents |
| 2010.1162C | Tacolicious | Valencia Street | 2011-04-28 | 33 (10) | Unanimous | 2 | Longest list, quiet hearing, stray fragments in the dataset text |
| 2013.1137C | Valley Tavern | Noe Valley | 2014-03-06 | 13 (6) | 7–0 | 15 | Beer garden cut back to 8 pm; short list; starts from a violation |
| 2014-001343CUA | Riptide | Taraval Street | 2016-06-23 | 16 (2) | 5–1 | 56 | Rebuilt after a fire, about 400 letters of support; two case-specific conditions |
| 2016-010652CUA | Doc's Clock | Mission Street | 2016-12-01 | 14 (5) | 6–0 | 21 | Legacy bar moving with its vintage sign; no public comment |
| 2012.0145C | The Alembic | Haight Street | 2012-10-04 | 21 (5) | 7–0 | 24 | Mostly standard conditions |
| 2022-008254CUA | Casements | Mission Street | 2024-01-25 | 23 (3) | 5–0 | 41 | Continued twice; four inexact pages |
| 2010.0970C | Trigger | Upper Market | 2010-12-09 | 24 (20) | 6–0 | 8 | Out: a penalties case, and a liaison condition that names a person |
| 2010.0912C | The Ice Cream Bar | Cole Valley | 2011-01-20 | 18 (3) | 6–0 | 35 | Charming and uneventful |

All conditions have exact page numbers except one in Preservation Hall West, two in Trigger and four in Casements.

## The top three

**1. Julius' Castle (chosen)**

- Strong: a place a stranger can picture. A turreted landmark about 150 feet downslope from Coit Tower, a restaurant from 1923 to 2007, asking to be one again. The motion records 23 letters for and 11 against, and the neighbours' worries about traffic and noise. The conditions answer them one by one: roof terrace closed by 9 pm, no amplified live entertainment, deliveries only from 8 am to 5 pm, no garbage pick-up before 6:30 am, a valet and parking plan, and a follow-up hearing six months after opening. Page 15 holds six conditions (17 to 22), three of them from this list (roof terrace, entertainment, deliveries), and no private name. The planning record adds a last beat: an appeal record, closed as denied on 12 September 2017.
- Weak: no alcohol condition and no separate noise condition. The PDF is a scan; it reads well, but six condition texts in the dataset say "T'he" or "'The" for "The" (the fact sheet carries a corrected display text beside the original). The record does not say whether the restaurant reopened, so the story must not either.

**2. Preservation Hall West, 777 Valencia Street**

- Strong: the widest spread of conditions (patio hours, 8-foot sound walls, a noise test, deliveries, litter, liaison, a six-month review), 17 of 25 written for this case, a clean PDF, and a hook: a New Orleans jazz band opening a West Coast home.
- Weak: the conditions have no titles, the hearing was quiet, and the findings lean on named private individuals.

**3. Giordano Bros., 1784 Union Street**

- Strong: the liveliest hearing (58 letters and 73 signatures against; 18 letters and 1,116 signatures for), and the Commission changed the project: the rear patio was asked for and refused.
- Weak: untitled conditions, a shorter list, and objections in the findings that describe the business unkindly.

## Why Julius' Castle

1. Its address is a story before the planning starts.
2. Its 22 conditions are few enough to show in full and concrete enough to read aloud.
3. The findings and the conditions line up: a worry, then the condition that answers it.
4. It has a full arc with dates: restoration approved in 2013, application filed 23 February 2017, heard and adopted 6 July 2017, appeal denied 12 September 2017.
5. It can be told without naming any private person.

The score placed it 31st because it rewards the number of condition kinds, and this motion has five. The reading outweighed that.

## Notes for the build

- The local PostGIS cluster was not running; planning record facts came from the local snapshot of 9 November 2026.
- Fact-checked on 17 November 2026 against the motion PDF, `conditions.json` and the same snapshot. The score ranks and the score range in this note were not re-run.
- The motion records an expansion at the rear built without a permit around 2007, and the planning record mentions a CEQA appeal and a lawsuit. Neither says who built the expansion or how the lawsuit ended, so the story should not either.
- The dataset's "decided" date for this record (19 July 2017) is the day the planning record closed. The motion was adopted on 6 July 2017.
- Page 1 of this motion, and of both runners-up, prints the project sponsor's name and address. Open the PDF on page 10 (the vote) or page 15 (the conditions).
- "5,048 more" is 5,049 conditions minus the one on screen. Outside this motion there are 5,027 conditions in 351 motions.
