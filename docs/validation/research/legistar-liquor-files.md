> Feasibility research, 2026-11-10. Report only; nothing was built. Written by a research agent and checked by a second one; the check is at the end and corrects the report where they differ.

# SF Board of Supervisors liquor-licence (PCN) files on Legistar: feasibility report

**Bottom line:** usable as a source of police-recommended licence conditions and Board outcomes, but small (about 16–31 adopted files a year) and almost entirely bars, venues and off-sale shops, not restaurants. The public Legistar API is dead for this purpose: it holds nothing after December 2018. Everything for 2019–2026 has to come from the Legistar web pages and PDF attachments.

Access notes: 59 HTTP requests in total, counting redirects; GET only; the prescribed User-Agent; nothing sent to abc.ca.gov. One deviation to flag: I sent a `Cookie` header on one GET to select the calendar year (see section 1).

## 1. How to select the files, and counts per year

**The API cannot select them for 2019–2026.**
- `https://webapi.legistar.com/v1/sfgov/matters?$top=3&$orderby=MatterId desc` returns a newest numbered file of 181184 (introduced 2018-12-04). The only later rows are two strays: `TMP-014` (2019) and `T19-021` (2020).
- A `MatterIntroDate ge datetime'2018-12-01'` filter returns only December 2018 files plus those two strays.
- For 1998–2018 the working selector is `$filter=substringof('Liquor License',MatterName)`, which returns 587 matters.

**How the files look (same pattern on the live site):**
- Name: `Liquor License [Transfer|Issuance] - <address> - <business>`. Variants seen: "Liquor Licenses -", "Liquor License Transfers -", "Liquor License Double Transfer -", "Liquor License Transfer and Issuance -". The plain "Liquor License -" form was used for issuances until about 2023.
- Type: starts as `Hearing`. On approval the same file number becomes a `Resolution`; the history for file 230891 shows "PREPARED IN COMMITTEE AS A RESOLUTION" then "RECOMMENDED" then "ADOPTED".
- Body: Public Safety and Neighborhood Services Committee (API BodyId 168; earlier committee names before 2017).
- Index/keywords: none. The index and sponsor fields are empty on the detail pages I opened.
- Title example, from the API (`...matters?$filter=substringof('Liquor License',MatterName)&$top=5&$orderby=MatterId desc`): "Hearing to consider that the premise-to-premise transfer of a Type-48 on-sale general public premises liquor license to Presidio Coctail Corporation".

**Live-site routes that work with GET:**
- `https://sfgov.legistar.com/Legislation.aspx` returns zero rows on GET; search is a POST form. Not usable under GET-only rules.
- `https://sfbos.org/resolutions-<year>` (redirects to `sfbos.archive.sf.gov`) is an HTML table of file number, enactment number, title and PDF link. It lists adopted resolutions only.
- `https://sfgov.legistar.com/Calendar.aspx` with cookie `Setting-60-Calendar Year=2023` returns that year's meetings, but only the first 100 rows (June–December); paging is a postback. The body-filter cookie was ignored.
- `MeetingDetail.aspx?ID=..&GUID=..` lists agenda items with File #, Name, Type, Status, Title, Action, Result and a link to the file.
- `https://sfgov.legistar.com/gateway.aspx?m=l&id=/matter.aspx?key=<MatterId>` redirects to the file's detail page. In 2018 the key was 32869 plus the file's sequence number (checked on 4 files). Keys for 2019 onward are not known.

**Adopted resolutions whose name starts "Liquor License", by enactment year** (from the `resolutions-<year>` tables):

| Year | Adopted | Transfer | Issuance | Plain "Liquor License -" |
|---|---|---|---|---|
| 2019 | 23 | 13 | 1 | 9 |
| 2020 | 21 | 15 | 1 | 5 |
| 2021 | 16 | 13 | 1 | 2 |
| 2022 | 20 | 14 | 0 | 6 |
| 2023 | 25 | 18 | 4 | 3 |
| 2024 | 31 | 10 | 21 | 0 |
| 2025 | 18 | 11 | 7 | 0 |
| 2026 | 4 (partial) | 4 | 0 | 0 |

- The 2026 table stops at Resolution 198-26 (file 260243), so the archive site is stale for 2026.
- The Legistar site itself is current: a Type-42 file (261000) is on the 12 November 2026 committee agenda.
- **Not established:** total files per year including non-approved ones for 2019–2026. That needs the POST search or a crawl of every committee meeting.

## 2. What a file contains

**Detail-page fields** (HTML spans, e.g. `https://sfgov.legistar.com/LegislationDetail.aspx?ID=8203527&GUID=5076B6DB-1370-434C-8505-2676B06A6443&Options=ID|Text|&Search=&FullText=1`): File #, Version, Name, Type, Status, Introduced, In control, Final action, Enactment date, Enactment #, Title, Related files, an attachments list and a history grid.

**The title carries licence type, applicant, business, address and district.** From file 261000: "issuance of a Type-42 on-sale beer and wine liquor license to [applicant] doing business as Bark 77, located at 77 Cambon Drive".

**Attachment names are consistent:**
- Pending file 261000: `PCN Request`, `PCN Referral`, `SFPD Response`, `Planning Response`, `Comm Pkt`.
- Adopted file 230891 adds: `Letters of Support`, `Leg Ver2`, `Board Pkt`, `Leg Final`, `COB Ltr`.
- 2018 files use `ABC 211`, `ABC License Query`, `LL PC or N Request Ltr`, `LL PC or N Referral` (`https://webapi.legistar.com/v1/sfgov/matters/33632/attachments`).

**Referral form** (`https://sfgov.legistar.com/View.ashx?M=F&ID=15835324&GUID=CF7CD174-9DC3-416D-851B-3C970C55CDC1`): applicant name, business name, address, applicant's consultant, zoning district, and "AP Block/Lot Nos.: 7324/001".

**Planning response** (`https://sfgov.legistar.com/View.ashx?M=F&ID=16113830&GUID=4E8F39CE-721C-481C-9463-359EF097BFE6`): the same form returned with a staff name, a date and a Planning record number ("Record No.: 2026-008011MIS"). The Approval/Denial tick is not in the text layer.

**Police memo** (`https://sfgov.legistar.com/View.ashx?M=F&ID=16113831&GUID=73D21ED6-26D5-49CD-AA64-657C15CF243E`): ABC file number, licence type, hours of operation ("12 PM to 2 AM, Sunday to Saturday"), counts of protest and support letters, calls for service, police reports, police plot and high-crime threshold, census tract with authorised versus active on-sale and off-sale licence counts, high/low concentration flag, station position, and the recommendation with numbered conditions.

**Resolution text** (`https://sfbos.archive.sf.gov/sites/default/files/r0503-23.pdf`): recites both recommendations. Planning "has verified that the area is properly zoned and recommends approval"; the Board "hereby endorses and adopts the recommendations of the Police Department listed above".

**Licence types seen:**
- 2019–2026 samples: 20, 21, 42, 48, 64 ("Type-64 special on-sale general theater liquor license", committee meeting of 14 Sept 2023) and 90.
- API 2012–2018, 183 files by "Type NN" in title: 21 ×53, 42 ×41, 48 ×38, 20 ×24, 64 ×9, 40 ×8, 87 ×5, 51 ×2, 57 ×2, and one each of 41, 47, 75, 86.

**Relevant to the 995 Valencia report:** file 230891 is next door (999 Valencia, Whole Foods, Type-20). Its police memo records 10 protests, 3 support letters, a high-crime plot and a high-concentration tract (208.01: 12 on-sale authorised vs 39 active; 3 off-sale authorised vs 6 active).

## 3. Outcomes

**Status values seen:** Passed, Filed, Withdrawn, Killed, Failed, Mayors Office, Pending Committee Action, Scheduled for Committee Hearing.

**Counts, API 1998–2018** (587 matters; `...matters?$filter=substringof('Liquor License',MatterName)&$top=1000&$orderby=MatterIntroDate asc`):

| Type / Status | Count |
|---|---|
| Resolution / Passed | 436 |
| Hearing / Filed | 127 |
| Motion / Passed | 5 |
| Resolution / Filed | 4 |
| Hearing / Pending Committee Action (frozen 2018 snapshot) | 4 |
| Resolution / Killed | 3 |
| Ordinance / Passed | 3 |
| Hearing / Withdrawn | 2 |
| Ordinance / Filed | 1 |
| Resolution / Failed | 1 |
| Resolution / Mayors Office | 1 |

- For files introduced 2010–2017: 173 passed, 36 not passed (17%, about 4–5 a year).
- Reading "Hearing / Filed" as "not approved" is my inference. I verified it on two files only.

**2019–2026:** non-approval counts not established. In the 7 committee meetings I opened for July–December 2023, all 9 liquor files heard were later adopted. Non-approvals appear to be filed by the Clerk without reaching a hearing, so meeting pages will not surface them.

**The Status field is unreliable.** File 230891 shows Status "Mayors Office" although its history shows Mayor APPROVED on 10/26/2023 and Enactment # 503-23. Derive outcome from history actions and the enactment number.

**Examples that did not end in approval:**
- **File 181106** — St. Joseph's Art Society, 1401 Howard St, Type-48 transfer. Status Filed; Clerk action FILED on 1/30/2019, the same day the Planning response arrived. The OCR of that response shows a mark beside "Denial" (low confidence; the handwriting is unreadable). Related file 200354 was adopted as Resolution 433-20. `https://sfgov.legistar.com/LegislationDetail.aspx?ID=3758384&GUID=CEBBCC82-7F01-4875-A792-564D06DD124A`
- **File 150217** — King Kong Bida, 745 O'Farrell St, Type 42 issuance. Status Withdrawn; "WITHDRAWN AND FILED" on 4/28/2015 after the Planning response. `https://sfgov.legistar.com/LegislationDetail.aspx?ID=2234102&GUID=935682AB-0A8A-4A9E-9D50-EAD2ED5A9C66`
- **File 110789** — Whole Foods, 3950-24th St, Type 21 transfer. Status Killed. Committee action was "PREPARED IN COMMITTEE AS A RESOLUTION APPROVING THE REQUEST WITH CONDITIONS"; the Board then CONTINUED it (12/13/2011) and TABLED it (1/24/2012). `https://sfgov.legistar.com/LegislationDetail.aspx?ID=937013&GUID=481547DD-90AA-49D9-99EC-1CB7F0D10AD7`
- API only, not opened on the live site: file 060589 (845 Market St, Type 21, Resolution / Failed, 2006); file 170704 (Amsterdam Café, 930 Geary, Type-42, Hearing / Filed, 2017).

Only the first example falls in the 2019–2026 window.

## 4. Conditions

**Yes: every adopted resolution I opened lists the police conditions verbatim** in a WHEREAS clause, numbered "1) … 2) …". The police memo lists the same conditions.

**Quoted examples:**
1. Loitering — file 230891 draft resolution: "Petitioner(s) shall actively monitor the area under their control in an effort to prevent the loitering of persons". `https://sfgov.legistar.com/View.ashx?M=F&ID=12338755&GUID=3E2CF4C3-D501-4FEA-8BB0-6649EC4D6DC5`
2. Litter — file 230891 police attachment: "The petitioner(s) shall be responsible for maintaining free of litter the area adjacent to the premises over which they have control". `https://sfgov.legistar.com/View.ashx?M=F&ID=12316367&GUID=9F52FE78-F5D1-45EC-BE95-4298B49865BA`
3. Noise — file 261000 police memo: "no noise shall be audible beyond the area under the control of the licensee". It is followed by an Entertainment Permit carve-out. `https://sfgov.legistar.com/View.ashx?M=F&ID=16113831&GUID=73D21ED6-26D5-49CD-AA64-657C15CF243E`
4. Security — Resolution 528-24 (Eve Nightclub, "Type-90 on-sale general music venue liquor license"): "the petitioner(s) shall have two (2) uniformed security guard(s) on the premises". `https://sfbos.archive.sf.gov/sites/default/files/r0528-24.pdf`
5. Five conditions (noise, entertainment permit, security guards, loitering, litter) — Resolution 2-26: "Type-48 on-sale general public premises beer, wine, and distilled spirits liquor license to Big Skye LLC, doing business as Club 895". `https://sfbos.archive.sf.gov/sites/default/files/r0002-26.pdf`

The 261000 police memo also has a patio-supervision condition.

**Not seen in my 5 samples:** hours-of-sale limits or single-serve bans. Hours appear only as a descriptive "Hours of Operation" line in the police memo. Whether such conditions occur elsewhere is not established.

**Machine-readability:**

| Document | Format | Quality |
|---|---|---|
| Legistar detail page | HTML | No resolution text; `FullText=1` returns none |
| API | JSON | No text; `/versions` gives only version keys, `/histories` returned HTTP 500, data frozen at 2018 |
| `Leg Ver2` (draft resolution) | Word-generated PDF | Clean text; the best source |
| `Leg Final` and `rNNNN-YY.pdf` | Scan with OCR layer | Good, with artefacts (e.g. "1011012024" for 10/10/2024) |
| Police memo | 300 dpi scan with OCR layer | Usable, with errors ("Cityw'de", letter O for zero) |
| Clerk's cover email (in the 2023 police attachment, absent in the 2026 one) | Born-digital | Clean restatement of the conditions |
| Planning response | Scanned form | Approval/Denial tick not readable; comments handwritten in the 2018 example |

## 5. Which applications need a Board PCN determination

**What the Board's fact sheet says** (`https://sfbos.org/sites/default/files/PC_or_N_Request_Fact_Sheet.pdf`, revised May 2018):
- A PCN showing is needed only where the premises is in an area of undue licence concentration or reported crime.
- The determination is made by either the state ABC office or the local governing body, depending on licence type.
- "The state ABC Office will advise when it is necessary for a liquor license applicant to receive a PC or N determination".
- The Board has 90 days to act; after that the ABC may issue the licence if the applicant shows PCN.

**What the files show:**
- Board files are overwhelmingly off-sale (Types 20, 21) and public-premises on-sale (Types 40, 42, 48), plus special types 64 and 90.
- Type 87 comes as motions verifying a pre-application meeting, not PCN resolutions.
- Restaurant types 41 and 47 appear once each in 183 files (2012–2018).
- So this source covers bars, venues, groceries and liquor stores in over-concentrated or high-crime areas, and essentially not ordinary restaurants.

**Not established:**
- The statutory list of licence types in Business and Professions Code §23958.4. The leginfo page returned HTTP 403 and a mirror returned 404.
- The share of all San Francisco ABC applications this represents. abc.ca.gov was off-limits and no Board page gives a denominator.

## 6. Verdict

**Usable, with limits.** It is a reliable source of police-recommended conditions and Board outcomes for the licence types above. It is not a source for restaurant licences, and not for final ABC-imposed conditions: the Board only recommends them to the ABC.

**Structured fields (HTML, no OCR):**
- File number, name, type, status, introduced / final-action / enactment dates, enactment number, related files.
- History actions with dates and actors.
- Attachment names and links.
- Title text, which a regex can split into transfer kind, licence type, applicant, business name, address and supervisorial district.

**Semi-structured (PDF text):**
- Numbered conditions; Planning and police recommendation sentences; protest and support counts.
- From the police memo: hours of operation, ABC file number, census tract and licence counts, high-crime and concentration flags.
- From the referral form: block/lot, zoning, Planning record number.

**What a parser would need:**
1. An enumerator. Options: the POST search on `Legislation.aspx` (type Hearing/Resolution, name contains "Liquor License"); the `resolutions-<year>` tables plus a crawl of committee meeting pages; or a walk of matter keys through the gateway URL (about 1,250 files a year, most irrelevant).
2. A detail-page scraper for the fields, attachments and history.
3. A title regex.
4. PDF text extraction, preferring `Leg Ver*` over `Leg Final`: strip line numbers, split conditions on "n)". Nested "(1)…(2)" numbering inside the noise condition needs care.
5. An OCR-tolerant reader for the police memo.
6. Outcome logic based on history and enactment number, not the Status field.
7. Fallback handling for Planning's tick-box, which is not machine-readable: for adopted files, use the resolution's WHEREAS sentence.

**Expected rows per year:**
- 16–31 adopted files (mean 22 for 2019–2025).
- Perhaps 3–6 non-approved files, extrapolated from 2010–2017 and unverified for 2019 onward.
- 2–5 conditions per adopted file in my samples, so roughly 50–110 condition rows a year.

**Files saved:**
- Pages and PDFs (49 files): (scratch folder, not kept)
- Throwaway parsing scripts: (scratch folder, not kept)

## Sources (URLs actually fetched)

**Legistar API**
- `https://webapi.legistar.com/v1/sfgov/matters?$filter=substringof('Liquor License',MatterTitle) and MatterIntroDate ge datetime'2019-01-01'&$top=1000&$orderby=MatterIntroDate asc` (returned `[]`)
- `https://webapi.legistar.com/v1/sfgov/matters?$filter=substringof('Liquor License',MatterName)&$top=5&$orderby=MatterId desc`
- `https://webapi.legistar.com/v1/sfgov/matters?$top=3&$orderby=MatterLastModifiedUtc desc`
- `https://webapi.legistar.com/v1/sfgov/matters?$filter=MatterIntroDate ge datetime'2018-12-01'&$top=5&$orderby=MatterIntroDate desc`
- `https://webapi.legistar.com/v1/sfgov/matters?$top=3&$orderby=MatterId desc`
- `https://webapi.legistar.com/v1/sfgov/matters?$filter=substringof('Liquor License',MatterName)&$top=1000&$orderby=MatterIntroDate asc`
- `https://webapi.legistar.com/v1/sfgov/bodies/168`
- `https://webapi.legistar.com/v1/sfgov/matters/33632/histories` (HTTP 500)
- `https://webapi.legistar.com/v1/sfgov/matters/33632/attachments`
- `https://webapi.legistar.com/v1/sfgov/matters/33632/versions`

**Board of Supervisors site** (sfbos.org redirects to sfbos.archive.sf.gov)
- `https://sfbos.org/resolutions-2019`, `-2020`, `-2021`, `-2022`, `-2023`, `-2024`, `-2025`, `-2026`
- `https://sfbos.archive.sf.gov/sites/default/files/r0503-23.pdf`
- `https://sfbos.archive.sf.gov/sites/default/files/r0528-24.pdf`
- `https://sfbos.archive.sf.gov/sites/default/files/r0002-26.pdf`
- `https://sfbos.org/sites/default/files/PC_or_N_Request_Fact_Sheet.pdf`

**Legistar web site: listing pages**
- `https://sfgov.legistar.com/Calendar.aspx` (twice; the second with cookie `Setting-60-Calendar Year=2023`)
- `https://sfgov.legistar.com/Departments.aspx`
- `https://sfgov.legistar.com/Legislation.aspx`

**Legistar web site: committee meetings** (each URL ends `&Options=info|&Search=`)
- `https://sfgov.legistar.com/MeetingDetail.aspx?ID=1461861&GUID=E9C038E3-C29F-4BAC-9188-3B603F943476` (12 Nov 2026)
- `https://sfgov.legistar.com/MeetingDetail.aspx?ID=1144526&GUID=F6BC56D8-3576-46FE-94C4-852FB01D33E1` (14 Dec 2023)
- `https://sfgov.legistar.com/MeetingDetail.aspx?ID=1133840&GUID=7DEF072B-D1D3-498B-B4E0-C66E5B44A799` (9 Nov 2023)
- `https://sfgov.legistar.com/MeetingDetail.aspx?ID=1127277&GUID=CD924F8E-A9E3-4D0B-AE71-EDA46380D0B3` (26 Oct 2023)
- `https://sfgov.legistar.com/MeetingDetail.aspx?ID=1123951&GUID=55293B25-514D-45AE-AD80-3AC269F1B1D5` (12 Oct 2023)
- `https://sfgov.legistar.com/MeetingDetail.aspx?ID=1120570&GUID=412CE640-260C-48F9-BB1A-57977962F5CE` (28 Sept 2023)
- `https://sfgov.legistar.com/MeetingDetail.aspx?ID=1119810&GUID=5812E7D7-6360-444B-94EE-0C23F08B8946` (14 Sept 2023)
- `https://sfgov.legistar.com/MeetingDetail.aspx?ID=1111227&GUID=C6F229ED-9740-4088-8625-1AFBFFCFFA3E` (13 July 2023)

**Legistar web site: file detail pages**
- `https://sfgov.legistar.com/LegislationDetail.aspx?ID=8203527&GUID=5076B6DB-1370-434C-8505-2676B06A6443&Options=ID|Text|&Search=&FullText=1` (file 261000)
- `https://sfgov.legistar.com/LegislationDetail.aspx?ID=6326039&GUID=F9313D6D-71A0-4F5F-B978-A4CE715D3D00&Options=ID|Text|&Search=&FullText=1` (file 230891)
- `https://sfgov.legistar.com/gateway.aspx?m=l&id=/matter.aspx?key=33975` → `https://sfgov.legistar.com/LegislationDetail.aspx?ID=3758384&GUID=CEBBCC82-7F01-4875-A792-564D06DD124A` (file 181106)
- `https://sfgov.legistar.com/gateway.aspx?m=l&id=/matter.aspx?key=29127` → `https://sfgov.legistar.com/LegislationDetail.aspx?ID=2234102&GUID=935682AB-0A8A-4A9E-9D50-EAD2ED5A9C66` (file 150217)
- `https://sfgov.legistar.com/gateway.aspx?m=l&id=/matter.aspx?key=24497` → `https://sfgov.legistar.com/LegislationDetail.aspx?ID=937013&GUID=481547DD-90AA-49D9-99EC-1CB7F0D10AD7` (file 110789)

**Legistar web site: attachments**
- `https://sfgov.legistar.com/View.ashx?M=F&ID=16113831&GUID=73D21ED6-26D5-49CD-AA64-657C15CF243E` (261000 police memo)
- `https://sfgov.legistar.com/View.ashx?M=F&ID=15835324&GUID=CF7CD174-9DC3-416D-851B-3C970C55CDC1` (261000 referral)
- `https://sfgov.legistar.com/View.ashx?M=F&ID=16113830&GUID=4E8F39CE-721C-481C-9463-359EF097BFE6` (261000 Planning response)
- `https://sfgov.legistar.com/View.ashx?M=F&ID=12338755&GUID=3E2CF4C3-D501-4FEA-8BB0-6649EC4D6DC5` (230891 Leg Ver2)
- `https://sfgov.legistar.com/View.ashx?M=F&ID=12316367&GUID=9F52FE78-F5D1-45EC-BE95-4298B49865BA` (230891 police attachment)
- `https://sfgov.legistar.com/View.ashx?M=F&ID=7010217&GUID=BE7C977A-A28B-4682-85B1-5ABF7230A301` (181106 Planning response)

**Statute attempts (both failed)**
- `https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=BPC&sectionNum=23958.4` (HTTP 403)
- `https://california.public.law/codes/bus_and_prof_code_section_23958.4` (HTTP 404)
---

## Second reader's check

A second agent re-fetched the pages behind the 8 claims that matter most; 7 were supported.

VERDICT STANDS WITH ONE MATERIAL CORRECTION: the source is usable, the counts are right, but the report treats "adopted/Passed" as "approved" and that is wrong. The Board also adopts denial resolutions, and two of them sit inside the 2019-2026 window.

WHAT I RE-FETCHED (28 GET requests of 60, prescribed User-Agent, >=2.5 s spacing, no cookie, nothing to abc.ca.gov). Files: (scratch folder, not kept) ; request log: (scratch folder, not kept)

SUPPORTED (7 of 8):
1. API frozen at December 2018. https://webapi.legistar.com/v1/sfgov/matters?$top=3&$orderby=MatterId desc returns T19-021 (2020), TMP-014 (2019), then file 181184 introduced 2018-12-04. A MatterIntroDate >= 2018-12-01 filter returns 16 rows: 14 from December 2018 plus the same two strays.
2. API counts. 587 matters with 'Liquor License' in MatterName, 1998-2018; every cell of the type/status table reproduces (436 Resolution/Passed, 127 Hearing/Filed, etc.). Same URL family, $top=1000.
3. Per-year adopted table 2019-2026. All eight rows and all three sub-columns reproduce exactly from https://sfbos.org/resolutions-<year> (redirects to sfbos.archive.sf.gov). Mean 2019-2025 is 22.
4. Three non-approval examples. File 181106: Status Filed, Clerk FILED 1/30/2019 same day as Planning RESPONSE RECEIVED, related file 200354 (Res 0433-20 in the 2020 table) - https://sfgov.legistar.com/LegislationDetail.aspx?ID=3758384&GUID=CEBBCC82-7F01-4875-A792-564D06DD124A . File 150217: Status Withdrawn, "WITHDRAWN AND FILED" 4/28/2015 - https://sfgov.legistar.com/LegislationDetail.aspx?ID=2234102&GUID=935682AB-0A8A-4A9E-9D50-EAD2ED5A9C66 . File 110789: Status Killed, CONTINUED 12/13/2011, TABLED 1/24/2012 - https://sfgov.legistar.com/LegislationDetail.aspx?ID=937013&GUID=481547DD-90AA-49D9-99EC-1CB7F0D10AD7 .
5. Status field unreliable. File 230891 shows Status "Mayors Office" with Mayor APPROVED 10/26/2023 and Enactment # 503-23; attachment names and history as reported; Index and Sponsors empty - https://sfgov.legistar.com/LegislationDetail.aspx?ID=6326039&GUID=F9313D6D-71A0-4F5F-B978-A4CE715D3D00&Options=ID|Text|&Search=&FullText=1 . File 261000 fields, title and five attachment names also match, and it is on the 11/12/2026 committee page.
6. Conditions are recorded verbatim in the resolution. r0503-23.pdf (loitering, litter, Planning "recommends approval", "endorses and adopts"), r0528-24.pdf (Type-90, "two (2) uniformed security guard(s)") and r0002-26.pdf (five conditions, Club 895) all say what the report quotes - https://sfbos.archive.sf.gov/sites/default/files/r0503-23.pdf , .../r0528-24.pdf , .../r0002-26.pdf .
7. Police memo content and machine-readability. The 261000 memo has ABC File# , "12 PM to 2 AM, Sunday to Saturday", calls for service, plot/high-crime threshold, tract 332.03 authorised vs active counts, the noise condition with Entertainment Permit carve-out, and the patio condition; it is a 300 dpi scan with OCR errors ("Cityw'de") - https://sfgov.legistar.com/View.ashx?M=F&ID=16113831&GUID=73D21ED6-26D5-49CD-AA64-657C15CF243E . The 230891 Leg Ver2 is a Microsoft Word 2016 PDF with clean text and no page images - https://sfgov.legistar.com/View.ashx?M=F&ID=12338755&GUID=3E2CF4C3-D501-4FEA-8BB0-6649EC4D6DC5 .
Also confirmed (extra): the fact sheet says PCN applies in areas of undue concentration or reported crime, is decided by ABC or the local body "depending on the license type", gives the Board 90 days, and is revised May 10, 2018 - https://sfbos.org/sites/default/files/PC_or_N_Request_Fact_Sheet.pdf .

NOT SUPPORTED (1 of 8) - AND THE THING THE REPORT SHOULD HAVE CHECKED:
8. The report never opened an adopted resolution to see whether it approves or denies. Resolution 42-19 (file 181025, Museum of Ice Cream, 1 Grant Ave, Type-42, adopted 1/29/2019, 11 ayes) determines the licence "will not serve the public convenience or necessity" and asks ABC to deny it - https://sfbos.archive.sf.gov/sites/default/files/r0042-19.pdf . Resolution 200-19 (file 190195, same business) is a second adopted denial - https://sfbos.archive.sf.gov/sites/default/files/r0200-19.pdf . In the denial, Planning recommended approval and police recommended approval with conditions; the Board's stated ground was undue concentration. This overturns three statements: that 181106 is the only non-approval example in the window; that non-approvals are filed by the Clerk without a hearing; and that outcome can be derived from history plus enactment number. The same blind spot exists in the 1998-2018 API data: 19 Resolution/Passed titles carry denial wording, including 160184 (Jackalope, 2016) and 170848 (BevMo!, 2017).

CORRECTIONS TO CARRY INTO THE REPORT:
- Relabel the per-year table "adopted resolutions (approvals and denials)". 2019 has at least 2 denials among 23, and 21 distinct premises. Denials per year for 2019-2026 are not established (3 of 154 resolutions opened beyond the report's samples).
- Outcome logic must read the title/RESOLVED text: "will serve" = approval, "will not serve ... deny" = denial; history + enactment number only says a resolution was adopted.
- For a denial, do not record the WHEREAS-listed police conditions as Board-endorsed.
- 2010-2017 non-approval rate is 38 of 211 (about 18%), not 36 (17%).
- Hours-of-sale conditions do exist (Res 42-19 and 136-19, both 2019), as does an off-premises-consumption ban; the 2023-2026 samples under-describe earlier condition types.
- Expect clerical errors in adopted text: Res 136-19's title is Decant SF (Type-42) but its RESOLVED clause names Chiotras Grocery (Type-21) - https://sfbos.archive.sf.gov/sites/default/files/r0136-19.pdf .

UNCHANGED: small source (16-31 adopted files a year), dominated by off-sale and public-premises types; restaurant types 41 and 47 appear once each in the 183 API files for 2012-2018; the Board only recommends, ABC decides. The denial finding makes the source somewhat more valuable for the reader, not less: it gives real Board denials with stated grounds, which the report said it could not find.

STILL NOT ESTABLISHED: total files per year including non-adopted ones for 2019-2026; denial counts per year; the statutory licence-type list in B&P 23958.4; the Planning tick on 181106; whether the restaurant-type absence holds for 2019-2026 (licence type is not in the resolutions-<year> table, only in each PDF/title).

### Problems found

- **Claim:** Section 3: for 2019-2026 only file 181106 is a non-approval example; 'Non-approvals appear to be filed by the Clerk without reaching a hearing, so meeting pages will not surface them'; and (section 6) outcome can be derived from history actions plus the enactment number.
  **Finding:** NOT SUPPORTED - contradicted by the report's own source family. Resolution 42-19 (file 181025, Museum of Ice Cream, 1 Grant Ave, Type-42) was prepared in committee on 1/23/2019 and ADOPTED by the Board on 1/29/2019 as a denial: it resolves the licence 'will not serve the public convenience or necessity' and asks ABC to 'deny the issuance of the license' (https://sfbos.archive.sf.gov/sites/default/files/r0042-19.pdf). Resolution 200-19 (file 190195, same business, mezzanine level) is a second adopted denial (https://sfbos.archive.sf.gov/sites/default/files/r0200-19.pdf). Both sit in the 2019 table at https://sfbos.org/resolutions-2019 and are counted in the report's '23 adopted'. So denials in the window do reach committee and the full Board, they carry an enactment number and an ADOPTED history action, and the proposed outcome logic (history + enactment number) would label them approvals. The parser must read the title/RESOLVED text ('will serve' vs 'will not serve').
- **Claim:** Section 1 table headed 'Adopted resolutions ... by enactment year' (23/21/16/20/25/31/18/4), used in section 6 as '16-31 adopted files' and read throughout as approvals.
  **Finding:** The numbers are exactly right: I re-fetched all eight tables (https://sfbos.org/resolutions-2019 ... -2026, served from sfbos.archive.sf.gov) and got the same totals and the same transfer/issuance/plain split for every year, and the 2026 table does end at file 260243 / 0198-26. But 'adopted' is not 'approved': at least 2 of the 23 in 2019 are denials (above). Also the 2019 count holds two premises twice (Museum of Ice Cream: files 181025 and 190195; Decant SF: files 190135 and 190322), so 23 files is 21 premises. I opened only 3 of the 154 resolutions for 2019-2025 beyond the report's samples, so the number of denials per year is NOT established.
- **Claim:** Section 3 API table (587 matters; Resolution/Passed 436; Hearing/Filed 127; ...) and 'For files introduced 2010-2017: 173 passed, 36 not passed (17%)'.
  **Finding:** Counts reproduce exactly from https://webapi.legistar.com/v1/sfgov/matters?$filter=substringof('Liquor License',MatterName)&$top=1000&$orderby=MatterIntroDate asc (587 rows; every type/status cell matches). But 'Passed' is being read as 'approved'. In that same API response, 19 Resolution/Passed matters have titles with denial wording ('will not serve', 'disapproving', 'deny'), 15 of them with 'will not serve'; two fall in 2010-2017 (file 160184 Jackalope, 1104 Polk St, Type 48, Res 487-16; file 170848 BevMo!, 150 Kearny St, Res 378-17). So 2010-2017 is 211 matters (the report's 173+36 leaves out 1 ordinance and 1 motion that passed), with 171 approving resolutions and 38 not approved (about 18%), not 36. Small change in rate, but it shows Board denials are a real, recurring outcome the report's outcome section never mentions.
- **Claim:** Section 4: 'Not seen in my 5 samples: hours-of-sale limits ... Hours appear only as a descriptive Hours of Operation line in the police memo. Whether such conditions occur elsewhere is not established.'
  **Finding:** Now established: they do occur. Resolution 42-19 condition 1: 'sales, service, and consumption of alcoholic beverages shall be permitted only between the hours of 9:00a.m. and 12:00 a.m. Sunday through Wednesday' (https://sfbos.archive.sf.gov/sites/default/files/r0042-19.pdf). Resolution 136-19 (Decant SF): hours '11:00 a.m. and 12:00 a.m. daily' plus 'no noise shall be audible at any nearby residence' (https://sfbos.archive.sf.gov/sites/default/files/r0136-19.pdf). Resolution 42-19 also has an off-premises-consumption ban. The report's five samples were all 2023-2026, so its condition vocabulary (noise / entertainment permit / security / loitering / litter) under-describes 2019-era files. Single-serve bans: still not established.
- **Claim:** Section 4: 'every adopted resolution I opened lists the police conditions verbatim' and section 6 step 4 (split conditions out of the resolution text).
  **Finding:** True for the three resolutions the report cites (re-checked: r0503-23, r0528-24, r0002-26 all contain the quoted condition text and 'hereby endorses and adopts the recommendations of the Police Department'). Two parser hazards the report missed: (a) a denial resolution (42-19) still recites the police conditions in a WHEREAS clause but does not endorse them, so a naive parser would record conditions as Board-recommended on a denied licence; (b) Resolution 136-19's RESOLVED clause names a different applicant and licence ('[applicant], doing business as Chiotras Grocery ... Type-21') than its title (Decant SF, Type-42) - a clerical error in the adopted text; a second Decant SF resolution (166-19, file 190322) follows, which I did not open. Title and RESOLVED clause cannot be assumed to agree.
- **Claim:** Section 2 licence-type tally for API 2012-2018: '42 x41' among 183 files.
  **Finding:** 183 files and 21 x53, 48 x38, 20 x24, 64 x9, 40 x8, 87 x5, 51 x2, 57 x2, 41 x1, 47 x1, 75 x1 reproduce. Type 42 came out as 37 with my first-match regex (Type[- ]NN) versus the report's 41; the difference is probably titles naming several types or a different spelling, but I did not resolve it. Not material to the verdict; the restaurant finding (types 41 and 47 once each) holds.
- **Claim:** Items not re-checked (outside the 8 claims chosen).
  **Finding:** Could not establish / did not re-fetch: the 'Denial' tick on the 181106 Planning response (report itself rates it low confidence); '7 committee meetings, 9 liquor files, all later adopted' for July-Dec 2023; Calendar.aspx cookie behaviour and the 100-row limit; the gateway key offset (32869 + sequence); Type-64 on the 14 Sept 2023 agenda; the 230891 police memo figures (10 protests / 3 support are confirmed in Resolution 503-23, the tract 208.01 counts were not re-checked); B&P Code 23958.4 text (still unverified, so which licence types go to the Board versus ABC rests only on the fact sheet's general wording and the observed file mix).
