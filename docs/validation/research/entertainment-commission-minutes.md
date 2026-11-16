> Feasibility research, 2026-11-10. Report only; nothing was built. Written by a research agent and checked by a second one; the check is at the end and corrects the report where they differ.

# SF Entertainment Commission hearing record: feasibility as a source of outcomes (including failures)

Short answer: the minutes are a usable, machine-readable source of hearing outcomes and they do record continuances and denials. Denials are rare, though, and I found no withdrawals. In 19 sets of minutes (2019–2026) I counted 110 permit decisions: 102 approved, 7 continued, 1 denied, 0 withdrawn.

Fetched files are in (scratch folder, not kept). Nothing in the fetched pages contained instructions aimed at an agent.

## 1. Where agendas and minutes are published

**Current site (sf.gov), July 2022 to today**
- Department page: `https://www.sf.gov/departments--city-administrator--entertainment-commission`. It states: "We meet on the 1st and 3rd Tuesday of the month."
- One HTML page per meeting, with the agenda inline: `https://www.sf.gov/meeting--<month>-<d>-<yyyy>--<month>-<d>-<yyyy>-entertainment-commission-meeting`. Cancelled and special meetings vary the slug, so take URLs from `https://www.sf.gov/sitemap.xml` rather than building them.
- The sitemap lists 109 such meeting pages, from July 19, 2022 to November 3, 2026.
- Minutes up to mid-2025 are PDFs linked from the meeting page, e.g. `https://media.api.sf.gov/documents/EC_Meeting_Minutes_Sept_20_2022_0.pdf`. Filenames are irregular (`Sept`/`September`, `_0`, `_Draft`, random suffixes), so they must be scraped from the meeting page.
- Minutes from October 21, 2025 onward are HTML pages: `https://www.sf.gov/sf-entertainment-commission-minutes-for-<month>-<d>-<yyyy>` (20 in the sitemap). The first HTML date comes from the sitemap; April 1, 2025 was still a PDF.
- The October 20, 2026 meeting page also links a staff "Permit Memo for Commissioners" PDF, an enforcement memo, and one application packet PDF per item. The 2022–April 2025 meeting pages I saved link only agenda and minutes PDFs. I did not establish when memos and packets started being posted.
- Video is linked from each meeting page (Granicus, `sanfrancisco.granicus.com/ViewPublisher.php?view_id=99`). I did not fetch it.
- A "Noticed Permits" page lists pending applications with hearing dates, e.g. `https://www.sf.gov/noticed-permits-september-29-2026`. The sitemap holds 9 dated snapshots, starting February 2026.

**Older site (sfgov.org/entertainment)**
- The live site did not respond: `https://sfgov.org/entertainment/` redirected to `www.sfgov.org/entertainment` and timed out.
- The department page links an Archive-It copy: `https://wayback.archive-it.org/org-571/3/https://sfgov.org/entertainment/`.
- The archived "Public Notices & Meetings" page links "Agendas (2015-present)", "Minutes (2015-present)" and "Archived Meetings (2009-2014)".
- The archived listing is `.../sfgov.org/entertainment/meetings/10?page=N`, 10 meetings per page. Page 0 covers March–August 2022 and page 8 covers February–June 2019. The pager shows at least 13 pages.
- Old minutes are HTML: `.../sfgov.org/entertainment/meeting/meetings-<month>-<d>-<yyyy>-minutes`, with `-agenda` and sometimes `-supporting-documents` siblings.
- Archive-It rate-limits: I got one HTTP 429 at 2.5-second spacing.

**Hearings per year** (sitemap meeting pages, minus those titled cancelled or holiday party)

| Year | Pages | Cancelled | Holiday party | Held |
|---|---|---|---|---|
| 2022 (from July 19) | 11 | 4 | 1 | 6 |
| 2023 | 25 | 8 | 1 | 16 |
| 2024 | 26 | 5 | 1 | 20 |
| 2025 | 26 | 7 | 1 | 18 |
| 2026 (to Nov 3) | 21 | 4 | 0 | 17 |

So roughly 16–20 hearings a year, one or two of which are special or summit meetings.

**Not established:** the earliest date actually retrievable in the archive (I verified 2019 only), the format of the 2009–2014 archive, and where 2003–2008 records live. The Commission was established in 2003 per its About page.

## 2. What a permit item records

**Agenda and minutes item line** (same text in both): permit number, applicant person and entity, dba, address, permit type and modifiers.
- Example, October 20, 2026 minutes: "EC-1972 - [applicant], dba Café International, 508 Haight St, Limited Live Performance". Modifiers seen elsewhere include "change in ownership", "amendment", and outdoor amplified sound.
- One-time events use `ECOTE<yy>-<nnn>` numbers, with event name, location and dates/hours instead of a street address (e.g. March 21, 2023 agenda).

**Minutes add, per item:**
- Motion maker and seconder, an "Action:" sentence, and Ayes/Nays by commissioner name.
- Recusals, and whether a consent item was pulled to the regular agenda.
- Public commenters, tagged +, - or = for support, opposition or neutral.
- Typical action (October 20, 2026): "Action: The Commission approved the permit with staff recommendations."

**Staff and police recommendation:**
- Routine minutes do not spell these out; they only say "with staff recommendations".
- The September 20, 2022 minutes word it as approval with the Good Neighbor Policy and staff and SFPD recommendations.
- The detail is in the staff memo. The October 20, 2026 memo says: "There were no added conditions from SFPD, and the staff recommendation is to approve the consent calendar with the staff recs listed below."
- The same memo gives a narrative per item (history, outreach, opposition letters, SFPD station recommendation) and a numbered "Staff recommendation: Approval with:" list.
- The application packet (EC-1975, 26 pages, an Airtable export) holds the application form, the Planning approval letter and the SFPD station email thread. It contains personal contact details.

**Vote:** always by name. The only non-unanimous vote in my sample was 4-1, on the 1217 Lounge Place of Entertainment permit (June 18, 2024).

## 3. Do denials, continuances and withdrawals appear?

Continuances: yes, regularly. Denials: yes, but rarely. Withdrawals of applications: none found.

| Date | Business, address | Permit | Action | Source |
|---|---|---|---|---|
| Sep 20, 2022 | That's Amore SF, 1901 Ocean Ave (EC-1651) | Limited Live Performance | Continued: "Commissioner Falzon made a motion to continue this item at the Commission meeting on October 4, 2022" | `https://media.api.sf.gov/documents/EC_Meeting_Minutes_Sept_20_2022_0.pdf` |
| Jun 4, 2024 | 1217 Lounge, 1217 Sutter St (EC-1783) | Place of Entertainment + Extended Hours Premises | Continued: "The Commission approved to continue the item to the next hearing." | `https://media.api.sf.gov/documents/EC_Meeting_Minutes_June_4_2024_Draft.pdf` |
| Jun 18, 2024 | 1217 Lounge, 1217 Sutter St (EC-1783) | Extended Hours Premises | Denied 5-0: "the Entertainment Commission hereby DENIED the Extended Hours Premises Permit for dba 1217 Lounge". The Place of Entertainment permit was conditionally granted 4-1. | `https://media.api.sf.gov/documents/EC_Meeting_Minutes_June_18_2024.pdf` |
| Jun 18, 2024 | Yasmin, 799 Valencia St (EC-1791) | Limited Live Performance with parklet sound | Continued to the next meeting; approved July 16, 2024 with amendments to "reduce the number of special events to two times per month" | same June 18 PDF; `https://media.api.sf.gov/documents/EC_Meeting_Minutes_July_16_2024.pdf` |
| Nov 4, 2025 | Kiddleton, 3995 Alemany Blvd (EC-1907) | Mechanical Amusement Device | Continued: "The Commission approved to continue this permit application to a future hearing." | `https://www.sf.gov/sf-entertainment-commission-minutes-for-november-4-2025` |
| Feb 3, 2026 | Rikki's Bar, 2223 Market St (EC-1917) | Limited Live Performance with outdoor sound | Continued: "The Commission approved to continue this item to a future Commission meeting." | `https://www.sf.gov/sf-entertainment-commission-minutes-for-february-3-2026` |

Two more continuances: Hideaway Café, 850 Jones St (EC-1928), April 7, 2026; and The Howard House, 847 Howard St (EC-1925), June 2, 2026.

**Denial detail.** The 1217 Lounge minutes record the reason: SFPD Northern Station recommended denial of the extended-hours permit because of proximity to a place of worship. The eight conditions on the granted permit are written out in full, including a sound limit and security staffing.

**Count across the 19 sets of minutes:**

| Outcome | Decisions |
|---|---|
| Approved (including approved with added or amended conditions) | 102 |
| Continued | 7 |
| Denied | 1 |
| Withdrawn | 0 |
| Total | 110 |

- The 110 decisions come from 109 items: 79 brick-and-mortar (EC-) and 30 one-time-event or Just Add Music items.
- Sets read: 2019 (1), 2022 (1), 2023 (3), 2024 (6), 2025 (3), 2026 (5).
- Two of the 2024 sets (June 18 and July 16) were chosen because they followed a continuance, so the sample slightly over-represents contested items.
- A continuance is not a final outcome. The two I traced ended in approval (Yasmin) and a split grant/denial (1217 Lounge). I did not trace the other five.

**Other adverse actions in the minutes** (not application outcomes):
- A revocation hearing for Stratos Night Club, 358 Ocean Ave (EC-1452), September 19, 2023: "The Commission determined that the appropriate penalty is to revoke Respondent's Permit".
- Reconditioning of The Brixton, 2140 Union St (EC-1616), June 4, 2024, limiting entertainment to Fridays and Saturdays, 6–9pm.
- Board of Appeals appeals noted in the Director's report, e.g. Appeal No. 24-039 on EC-1783 (July 16, 2024 minutes).

## 4. Permits that never reach the Commission

- **Routine One Time Outdoor Event permits** are decided by staff. The Commission's guidelines say: "The following shall be reviewed administratively by the Director or designated staff and do not require a hearing".
- **Hearing triggers for one-time events** under the same guidelines: 24 or more days per 12 months at one premises, sound before 9am or after 10pm without precedent, or a Director referral. Just Add Music permit transfers are also administrative.
- **Staff can refuse late applications:** "The SF Entertainment Commission has the right to deny an application submitted less than 7 days before an event." Such refusals would not appear in minutes.
- **Place of Entertainment and Limited Live Performance** do go to hearing. The service pages require a public hearing; the Place of Entertainment page says of commissioners: "They will vote on whether to approve your permit."
- **Also seen on agendas:** Extended Hours Premises, Fixed Place Amplified Sound, Billiard Parlor, Mechanical Amusement Device, changes of ownership and amendments.
- **Director-level enforcement** (e.g. the Executive Director's limited suspension of The Brixton) shows up only through the Director's report or an appeal item.

**Not established:**
- Whether One Time Indoor Event, sound truck and Temporary (60-day pop-up) Limited Live Performance permits are staff-issued. I did not fetch those pages, and the Limited Live Performance page does not say.
- What happens to applications withdrawn or abandoned before being calendared. No document I read addresses it. Comparing the "Noticed Permits" snapshots with later minutes is the only public trace I found, and it only exists from February 2026.

## 5. How conditions are recorded

- **Standard conditions sit in the staff memo, not the minutes.** The October 20, 2026 memo lists, for every item: compliance with Police Code Articles 15, 15.1, 15.2 and 29; the Commission-approved Security Plan; and the Good Neighbor Policy.
- **Case-specific conditions are in the same memo.** Examples from that memo:
  - Hours: indoor entertainment daily until 2am (St. Mary's Pub).
  - Sound limits: internal limit 85dBA/90dBC measured from the middle of the bar (St. Mary's Pub); external limit 82dBA/87dBC on each patio (Mars Bar).
  - Police conditions: SFPD Southern Station's monthly event-calendar condition (Mars Bar); a security guard doing bag checks (St. Mary's Pub, from Ingleside Station).
- **The minutes then incorporate the memo by reference** ("approved the permit with staff recommendations").
- **Minutes spell conditions out only in two cases:**
  - When the Commission amends them. Examples: Ora, 1519 Polk St, entertainment to end by 10pm (September 20, 2022); 620 Jones, revised outdoor hours and 8 special events a year (February 3, 2026); Sacred Taco, 1875 Union St, Fridays–Mondays only (June 2, 2026).
  - In contested decisions such as 1217 Lounge.
- **The Good Neighbor Policy** is a fixed 8-point text at `https://www.sf.gov/information--good-neighbor-policy`, e.g. "Permit holder shall take measures to reduce the amount of sound that escapes the venue."
- **Gap:** for 2022–April 2025 the saved meeting pages link no memo, so the standard and SFPD conditions for routine approvals in that period are not in the public hearing record I saw. Sound limits are sometimes left to staff after the hearing ("Direct staff to set an internal sound limit"), so they are not always in the memo either.

## 6. Verdict

**Outcomes: usable.** The minutes give a clean, consistent record per item: permit number, applicant, dba, address, type, action, named vote and public support/opposition. Continuances are recorded reliably.

**Failures: thin.** Roughly 1 denial in 110 decisions and no recorded withdrawals. This will not produce a failure sample comparable to the 46 Planning failures. The better risk signals here are continuances (about 6%), Commission-added restrictions, counted opposition speakers, and the gap between first hearing and approval.

**Conditions: partly usable.** Full conditions need the staff memo (confirmed for October 2026 only) or the application packet. From minutes alone you get the Commission's amendments and the conditions in contested cases.

**What a parser would need:**
1. Discovery from `sitemap.xml` (meeting pages and HTML minutes), then scrape each meeting page for the minutes and memo links. Do not construct PDF names.
2. Three minutes formats: sf.gov HTML (October 2025 onward), PDF via `pdftotext` (2022–2025, with a letterhead repeated mid-item at page breaks), and Archive-It HTML (before July 2022, uppercase `MOTION:/ACTION:/AYES:` and older wording such as "conditionally granted").
3. Item segmentation on the lettered lines (`a. EC-…`, `ECOTE…`, `JAM-…`), handling consent items acted on by one vote, items pulled to the regular agenda and listed twice, and items heard out of order.
4. Action classification: approved, approved with amendments, continued, denied, conditionally granted. Split multi-permit items (1217 Lounge had two permits and two votes).
5. Linking across hearings by permit number, with a fallback on dba and address. Numbers are not reliable keys: ECOTE24-136 is used for two different applicants (May 7 and June 4, 2024), ECOTE25-054 likewise (March 18 and April 1, 2025), and "EC-1995" in July 2024 is out of sequence.
6. Memo parsing for the numbered "Staff recommendation: Approval with:" lists; sound limits and hours are regular enough for patterns.
7. Address normalisation (unit suffixes, "401 Columbus" with no street type, block descriptions for events). Link labels can be wrong: the May 21, 2024 page labels the June 4 minutes as that meeting's.
8. Redaction if packets are ingested (they contain personal emails and phone numbers), and slow crawling of Archive-It.

**Rows per year (estimate):**
- About 85–115 permit decisions a year, from about 5.8 decisions per hearing in my sample times 15–19 permit hearings.
- Of those, about 60–80 are brick-and-mortar. Permit numbers back this up: EC-1651 in September 2022 to EC-1975 in October 2026 is about 79 a year.
- The other 25–35 are one-time events with extended duration or hours.
- Expect about 5–8 continuances and 0–2 denials a year.
- Back to 2019 that is roughly 600–800 rows; earlier years are unverified.

**Process notes:**
- 58 HTTP requests in total, counting redirect hops, against the cap of 60.
- One was a HEAD request to www.sf.gov made in error, against the GET-only rule.
- Redirect hops ran back-to-back without the 2-second gap.
- abc.ca.gov was never requested.

## Sources (URLs actually fetched)

sf.gov pages
- https://www.sf.gov/departments--entertainment-commission (404)
- https://www.sf.gov/departments/entertainment-commission (308 to a 404 page)
- https://www.sf.gov/sitemap.xml
- https://www.sf.gov/departments--city-administrator--entertainment-commission
- https://www.sf.gov/departments--city-administrator--entertainment-commission--about
- https://www.sf.gov/information--entertainment-rules-and-notices
- https://www.sf.gov/information--good-neighbor-policy
- https://www.sf.gov/noticed-permits-september-29-2026
- https://www.sf.gov/get-place-entertainment-permit-your-business
- https://www.sf.gov/get-limited-live-performance-permit
- https://www.sf.gov/get-entertainment-permit-your-outdoor-event

sf.gov meeting pages
- https://www.sf.gov/meeting--september-20-2022--september-20-2022-entertainment-commission-meeting
- https://www.sf.gov/meeting--march-21-2023--march-21-2023-entertainment-commission-meeting
- https://www.sf.gov/meeting--october-3-2023--october-3-2023-entertainment-commission-meeting
- https://www.sf.gov/meeting--may-21-2024--may-21-2024-entertainment-commission-meeting
- https://www.sf.gov/meeting--june-18-2024--june-18-2024-entertainment-commission-meeting
- https://www.sf.gov/meeting--july-16-2024--july-16-2024-entertainment-commission-meeting
- https://www.sf.gov/meeting--october-15-2024--october-15-2024-entertainment-commission-meeting
- https://www.sf.gov/meeting--april-1-2025--april-1-2025-entertainment-commission-meeting
- https://www.sf.gov/meeting--october-20-2026--october-20-2026-entertainment-commission-meeting

sf.gov HTML minutes
- https://www.sf.gov/sf-entertainment-commission-minutes-for-november-4-2025
- https://www.sf.gov/sf-entertainment-commission-minutes-for-february-3-2026
- https://www.sf.gov/sf-entertainment-commission-minutes-for-april-7-2026
- https://www.sf.gov/sf-entertainment-commission-minutes-for-june-2-2026
- https://www.sf.gov/sf-entertainment-commission-minutes-for-september-1-2026
- https://www.sf.gov/sf-entertainment-commission-minutes-for-october-20-2026

PDF minutes and documents
- https://media.api.sf.gov/documents/EC_Meeting_Minutes_Sept_20_2022_0.pdf
- https://media.api.sf.gov/documents/EC_Meeting_Minutes_Mar_21_2023.pdf
- https://media.api.sf.gov/documents/EC_Meeting_Minutes_Sept_19_2023_Draft_0.pdf
- https://media.api.sf.gov/documents/EC_Meeting_Minutes_Oct_3_2023.pdf
- https://media.api.sf.gov/documents/EC_Meeting_Minutes_May_7_2024_Draft_0.pdf
- https://media.api.sf.gov/documents/EC_Meeting_Minutes_June_4_2024_Draft.pdf
- https://media.api.sf.gov/documents/EC_Meeting_Minutes_June_18_2024.pdf
- https://media.api.sf.gov/documents/EC_Meeting_Minutes_July_16_2024.pdf
- https://media.api.sf.gov/documents/EC_Meeting_Minutes_October_1_2024_Draft_0.pdf
- https://media.api.sf.gov/documents/EC_Meeting_Minutes_October_15_2024.pdf
- https://media.api.sf.gov/documents/EC_Meeting_Minutes_March_18_2025_Draft.pdf
- https://media.api.sf.gov/documents/EC_Meeting_Minutes_April_1_2025.pdf
- https://www.sf.gov/documents/64666/10-20-26_memo_for_Commissioners.pdf (redirects to https://media.api.sf.gov/documents/10-20-26_memo_for_Commissioners.pdf)
- https://media.api.sf.gov/documents/EC-1975_St._Marys_Pub_POE_permit_application.pdf
- https://media.api.sf.gov/documents/One_Time_Outdoor_Events_with_Extended_Hours_Criteria-amended100323_signed_remediated.pdf

Old site and archive
- https://sfgov.org/entertainment/ (301, then timed out)
- https://wayback.archive-it.org/org-571/3/https://sfgov.org/entertainment/
- https://wayback.archive-it.org/org-571/20230120172206/https://sfgov.org/entertainment/public-notices-meetings (served from the 20230120185727 capture)
- https://wayback.archive-it.org/org-571/20230120185727/https://sfgov.org/entertainment/meetings/10
- https://wayback.archive-it.org/org-571/20230120171909/https://sfgov.org/entertainment/meetings/10?page=8
- https://wayback.archive-it.org/org-571/20230120171909/https://sfgov.org/entertainment/meeting/meetings-june-21-2022-minutes (HTTP 429, not read)
- https://wayback.archive-it.org/org-571/20230120190624/https://sfgov.org/entertainment/meeting/meetings-june-4-2019-minutes
---

## Second reader's check

A second agent re-fetched the pages behind the 8 claims that matter most; 7 were supported.

Seven of the eight claims checked are supported by the cited pages; the report's main conclusion holds, with one correction that matters: failures are not absent, they are hidden as continuances that never return.

**Checked and supported (re-fetched by me)**
1. Denial example. June 18, 2024 minutes: "the Entertainment Commission hereby DENIED the Extended Hours Premises Permit for dba 1217 Lounge", 5-0; the Place of Entertainment permit was conditionally granted 4-1 with eight written conditions; the stated reason is the Northern Station recommendation over proximity to a place of worship. https://media.api.sf.gov/documents/EC_Meeting_Minutes_June_18_2024.pdf
2. Continuance, Sept 20, 2022 (That's Amore, EC-1651): the motion text matches the quote. https://media.api.sf.gov/documents/EC_Meeting_Minutes_Sept_20_2022_0.pdf
3. Continuances June 4, 2024 (1217 Lounge) and June 18, 2024 (Yasmin), and Yasmin's July 16, 2024 approval with amendments to "reduce the number of special events to two times per month". https://media.api.sf.gov/documents/EC_Meeting_Minutes_June_4_2024_Draft.pdf and https://media.api.sf.gov/documents/EC_Meeting_Minutes_July_16_2024.pdf
4. Continuances in HTML minutes: Kiddleton (Nov 4, 2025) and Rikki's Bar (Feb 3, 2026), quotes exact; Hideaway Cafe (Apr 7, 2026) and The Howard House (Jun 2, 2026) also confirmed. https://www.sf.gov/sf-entertainment-commission-minutes-for-november-4-2025 and https://www.sf.gov/sf-entertainment-commission-minutes-for-february-3-2026
5. The headline count. Across the same 19 sets of minutes I reproduced 7 continuances, 1 denial, 0 withdrawals and otherwise approvals. My automated item count was 108 against the report's 109; not reconciled.
6. Conditions live in the staff memo. The Oct 20, 2026 memo has the quoted sentence, the three standard conditions for every item, and the case-specific ones (85dBA/90dBC from the middle of the bar and daily until 2am for St. Mary's Pub; 82dBA/87dBC on each patio and the monthly calendar condition for Mars Bar). The minutes only say "approved the permit with staff recommendations". https://media.api.sf.gov/documents/10-20-26_memo_for_Commissioners.pdf and https://www.sf.gov/sf-entertainment-commission-minutes-for-october-20-2026
7. Permits that skip the Commission. The guidelines say: "The following shall be reviewed administratively by the Director or designated staff and do not require a hearing"; the three hearing triggers (24 or more days, before 9am or after 10pm, Director referral) match. The Place of Entertainment page says "They will vote on whether to approve your permit." https://media.api.sf.gov/documents/One_Time_Outdoor_Events_with_Extended_Hours_Criteria-amended100323_signed_remediated.pdf and https://www.sf.gov/get-place-entertainment-permit-your-business

**Checked and not fully supported**
8. Sitemap counts (https://www.sf.gov/sitemap.xml). 109 meeting pages, the per-year page/cancelled/holiday tallies, 9 Noticed Permits snapshots from February 2026 and the Oct 21, 2025 start of HTML minutes all reproduce. Two errors: 2022 "Held" should be 7, not 6 (one page is both cancelled and holiday and was subtracted twice); and the "20 HTML minutes" figure needs a second slug pattern for the May 6, 2026 special meeting.

**What the report should have checked: the fate of continued items**
- Three of the five untraced continuances ended in approval at the next hearing (That's Amore, Kiddleton, Rikki's Bar).
- Two never reappear: Hideaway Cafe (EC-1928, continued Apr 7 and again Apr 21, 2026) and The Howard House (EC-1925, continued Jun 2, 2026). Neither is in any later minutes through Nov 3, 2026, nor on the Sept 29, 2026 Noticed Permits page.
- In 12 further sets of minutes outside the report's sample (Nov 2025 to Nov 2026, about 71 items) I found 6 more application continuances, no denials and no use of "withdraw". The continuance rate (roughly 6-8%) holds.

**Corrected verdict**
- Outcomes: usable, as the report says.
- Failures: still thin, but not zero beyond the one denial. The record never says "withdrawn"; a stalled or abandoned application shows up as a continuance with no later action. In the sample that is 2 of 7 continuances, so the realistic failure signal is "denied, or continued and not re-heard within N months", which requires linking items across hearings. This still will not match the 46 Planning failures in volume: expect a handful a year.
- Conditions: partly usable, as the report says (memo confirmed for October 2026 only).
- Volume: the 60-80 brick-and-mortar rows a year is backed by the Commission's own annual report (53 and 76 new fixed-place permits issued in FY2022-23 and FY2023-24). https://media.api.sf.gov/documents/San_Francisco_Entertainment_Commission_Report_Final_12-30-25.pdf

**Not established**
- Whether Hideaway Cafe and The Howard House were withdrawn, abandoned, or are still pending.
- The exact item count (108 vs 109).
- I did not re-check: the claim that 2022-April 2025 meeting pages link no staff memo, the Archive-It listing structure beyond the single June 4, 2019 minutes page, the application packet contents, or the duplicate ECOTE numbers.

**Process**
- 42 GET requests, all with the required User-Agent, at least 2.5 seconds apart per host; abc.ca.gov never requested. One Archive-It request returned a 302 that I followed as a separate request.
- Nothing fetched contained instructions aimed at an agent.
- Files: (scratch folder, not kept) ; request log: (scratch folder, not kept)

### Problems found

- **Claim:** Hearings-per-year table: 2022 (from July 19) = 11 pages, 4 cancelled, 1 holiday party, 6 held (source: https://www.sf.gov/sitemap.xml)
  **Finding:** Not supported as written. The sitemap does list 109 meeting pages (11/25/26/26/21 by year) and the cancelled/holiday tallies match, but the December 6, 2022 page is a single page titled both cancelled and holiday (slug ends '-meeting-cancelled-and-holiday'), so it was subtracted twice. Seven 2022 pages are not titled cancelled or holiday (Jul 19, Aug 16, Sep 20, Oct 4, Oct 18, Nov 15, Dec 20), so Held should be 7, not 6. The other years reproduce (16, 20, 18, 17). Side note: a 110th page, https://www.sf.gov/cancelled-january-16-2024-entertainment-commission-meeting, sits outside the 'meeting--' slug pattern; it does not change the held count.
- **Claim:** Withdrawn: 0 of 110 decisions; 'no recorded withdrawals'; 'A continuance is not a final outcome ... I did not trace the other five.'
  **Finding:** Literally true (no minutes I fetched use 'withdraw' for an application), but this is the thing the report should have checked and did not, and it changes the verdict. I traced all five untraced continuances. Three ended in approval: That's Amore on Oct 4, 2022 (https://media.api.sf.gov/documents/EC_Meeting_Minutes_Oct_4_2022.pdf), Kiddleton on Nov 18, 2025 (https://www.sf.gov/sf-entertainment-commission-minutes-for-november-18-2025), Rikki's Bar on Feb 17, 2026 (https://www.sf.gov/sf-entertainment-commission-minutes-for-february-17-2026). Two never come back: Hideaway Cafe (EC-1928) was continued a second time on Apr 21, 2026 (https://www.sf.gov/sf-entertainment-commission-minutes-for-april-21-2026) and then appears in none of the 11 later sets of minutes through Nov 3, 2026; The Howard House (EC-1925), continued Jun 2, 2026, appears in none of the 8 later sets through Nov 3, 2026. Neither is on the Sept 29, 2026 Noticed Permits page (https://www.sf.gov/noticed-permits-september-29-2026). So 2 of the 7 sampled continuances have no recorded outcome 5 to 7 months later. Failures in this record look like 'continued and never re-calendared', not like a 'withdrawn' line. I could not establish whether those two were withdrawn, abandoned or are still pending.
- **Claim:** HTML minutes follow https://www.sf.gov/sf-entertainment-commission-minutes-for-<month>-<d>-<yyyy> (20 in the sitemap)
  **Finding:** Count is right only if a second slug pattern is included. The stated pattern matches 19 sitemap URLs (Oct 21, 2025 to Nov 3, 2026); the 20th is https://www.sf.gov/sf-entertainment-special-commission-minutes-for-may-6-2026. A parser using only the stated pattern would miss special-meeting minutes. Source: https://www.sf.gov/sitemap.xml.
- **Claim:** The 110 decisions come from 109 items: 79 brick-and-mortar and 30 one-time-event or Just Add Music items
  **Finding:** Minor, unresolved. I re-fetched all 19 sets and reproduced the outcome split exactly (7 continuances, 1 denial, 0 withdrawals, the rest approvals), but my pattern-based item count gave 108 unique lettered items (about 79 EC and 29 ECOTE), one short of 109. I did not hand-reconcile the one-item difference; it does not move the percentages.
- **Claim:** Rows per year: about 60-80 brick-and-mortar decisions, supported only by the permit-number sequence
  **Finding:** An official cross-check exists that the report did not use. The Commission's annual reports are linked from https://www.sf.gov/archived-reports-entertainment-commission; the 2022-24 combined report (https://media.api.sf.gov/documents/San_Francisco_Entertainment_Commission_Report_Final_12-30-25.pdf) lists new fixed-place permits issued: 53 in FY2022-23 and 76 in FY2023-24. That is consistent with the estimate. The same report gives no counts of denied or withdrawn applications (keyword search of the PDF text), so it does not supply a failure sample either.
