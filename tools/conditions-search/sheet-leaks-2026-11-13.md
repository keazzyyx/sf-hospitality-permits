# Text that is not the condition, cut off conditions (2026-11-13)

Every condition in `data/conditions.json` whose text changed against the data at git HEAD (c885309), with what was removed. The build cuts text that is not part of the condition and ran on into it from the motion's other pages (`scripts/validation/condition_text.py`):

- **page header**: the page footer "SAN FRANCISCO PLANNING DEPARTMENT" with its page number, "Page 3 of 5", and the running header ("Motion No. 20113 Case Number 2017-015083CUA February 22, 2018 721 Lincoln Way", "CASE NO. 2017-000519CUA"), in the OCR forms the older clean-up missed ("SAN FRANCISCO 13P L/tNNiNG", "saw FRnNcisco 15P LARIMW6 DBPARTNlEMT", "P LANNING D£PAR7MENT Page 7 of", "SAN PRANCtSCO"), after the condition's last sentence (`leak_cut`, `tail_cut`);
- **mid-condition page header**: the same furniture where a page broke between two words of a sentence ("the Zoning CASE NO.2015-005989CUA Administrator", "which are not SAN FRANCISCO 15P LANNINti DEPARTMENT resolved"); and the footer as OCR garbled it there ("litter or SAN fRANCI$CO 1 7 block driveways", "the Zoning sam FRa~rcisco ~2 Administrator", "clearly DBPARTMENT labeled", "collection and ~ O PLANNING D<PARTMtNT storage", "storage of '~ O recyclable", "block ~ 2 driveways"); only the furniture is taken out, the words around it stay (`inside_cut`);
- **section heading**: the heading of the next group of conditions ("Operation", "Monitoring - After Entitlement", "Design – Compliance at Plan Stage", "Parking and Traffic", "Provisions", "Entertainment Commission – Noise Attenuation Conditions", "STANDARD CONDITIONS", "MAXIMUM OCCUPANCY AND EVENTS", the OCR forms "O PERATION", "D ESIGN", "ITORING - AFTER ENTITLEMENT"), after the condition's last sentence or after its contact line (`tail_cut`; the headings are `SECTION_HEADINGS`, the ones that start the condition groups in the motions' Exhibit A);
- **file path**: the word-processor file name printed under the motion ("U:\DVu\Documents\CUs\...\Final Motion.doc"), or the typist's initials left of one ("ESJ:");
- **drawing sheet**: a plan set bound in after the conditions: its title block and dimensions (2018-015652CUA #28) or its cover title ("EXHIBIT B: Plans & Renderings", 2021-008505CUA #20);
- **drawing sheet / image-page OCR noise**: what OCR made of a page bound in after the conditions as a picture (a map or plan scanned as an image): a run of symbols and letters that are not words (":r~' ~ Yrsf~ ~:~"a ~ ...", 2016-008418CUA #15, from page 18 of its PDF, an image page). It is cut after the last sentence when the whole of what follows is long (5 tokens and 30 characters or more), at most 30% words (known to the build's vocabulary), at least 25% symbols, never three words in a row, and does not start with a word or a number (`tail_cut`);
- **next condition's title**: the title of the next condition, whose number and text the first reading lost (an unnumbered paragraph in the PDF): a short phrase in title case ending in ".", the whole of the last sentence, that is a condition title used on 10 or more conditions in the data ("Rooftop Mechanical Equipment.", "Sidewalk Maintenance.", "Revocation due to Violation of Conditions."), after the condition's last sentence or after what is kept of its contact line, which stays ("Public Works at 415-554-.5810,", "www.sf-planning.org") (`tail_cut`). The conditions those titles belong to are listed under "Conditions missing from the data" below; they are not added to the data.

**190 conditions changed**: 63 on motions decided before 2019, 127 on 2019+ motions. Each one had one piece cut.

| Kind | Before 2019 | 2019+ | All |
|---|---|---|---|
| page header | 37 | 2 | 39 |
| mid-condition page header | 10 | 1 | 11 |
| section heading | 11 | 119 | 130 |
| file path | 3 | 0 | 3 |
| drawing sheet | 0 | 2 | 2 |
| drawing sheet / image-page OCR noise | 1 | 0 | 1 |
| next condition's title | 1 | 3 | 4 |
| **all** | 63 | 127 | 190 |

How each cut is made. Pieces are taken off the end of the condition one at a time while they read as furniture, and the cut is kept only when what is left ends where a sentence ends, or at the end of a contact line (its phone number or web address). So a condition is never cut inside its own text. A furniture word counts when its letters are close to FRANCISCO, PLANNING or DEPARTMENT and it is not written as a word of a sentence ("Planning", "planning", "Francisco" are never furniture), or when it follows the "13P" of "13P LANNING". Mid-condition furniture is only taken out in these exact shapes, between two words. On 2019+ motions the only changes are junk: 119 section headings, two running headers ("Motion No. 20414 RECORD NO. 2017-010011 CUA"; the "ENT" of "DEP4RTM ENT", 2019-006951CUA #5), two plan sets, three titles of the next condition (2018-010700CUA #8, 2018-015439CUA #8D, 2018-016549CUA #8D) and one page number left inside a sentence ("block ~ 2 driveways", 2019-004664CUA #11).

Each cut was checked against the motion PDF (`pdftotext` of `$LOCAL_DATA_DIR/conditions_pdf_public/<record>.pdf`): in every one, what follows the kept text in the PDF is the contact line, the page footer and header, the next section's heading and the next condition's number, a file name at the foot of the page, or the plan set, not more of the condition. Where the page broke inside a sentence (the 11 mid-condition cuts), the PDF has the sentence go on after the page furniture. Where a title was cut, the PDF has that title open an unnumbered paragraph after the condition (see "Conditions missing from the data"); where the OCR noise was cut (2016-008418CUA #15), the condition is the last one, on page 17, and page 18 is an image.

Contact lines are left as they are, a separate decision: "For information about compliance, contact ...", its phone number and the web address after it. Where page furniture or a heading followed a contact line, the cut is made after the contact line (2017-000519CUA #5, 2020-008474CUA #6 and #9, 2021-003599CUA #9, 2021-008505CUA #13, 2022-002437CUA #5, 2025-003645CUA #6). A piece of a web address left on its own between the last sentence and the furniture, with no contact line before it, is what the clean-up left of a contact line it took off ("org", "planning.org", "zvww. s f-p lanning. orb", "wwZas -Tannin orb", "sf.gov/entertainmentcommission", "sfplanning.org."); it is cut with the furniture, as the first pass did ("planning.org Motion No. ...") and as the clean-up already does when such a piece ends any condition. That is 14 of the cuts: 10 before 2019, and 4 on 2019+ motions (2018-015652CUA #6, 2019-017867CUA #12, 2026-002061CUA #6, 2026-004873CUA #6, each before a section heading). Where the next condition's title followed what is kept of a contact line, only the title is cut and the contact line stays (2018-015439CUA #8D and 2018-016549CUA #8D keep "Public Works at 415-554-.5810,"; 2018-002906CUA #6 keeps "www.sf-planning.org").

Nothing else in the data changed: the same 5,049 conditions in the same order, and in the changed ones only `text`, `raw_text`, `readable` and `text_source`; outside the conditions, only the `text_quality` counts. Which reading of a condition is shown (first reading, PDF text layer or OCR) is picked as before these cuts, and the picked reading is then cut, so the cuts never swap one reading for another. 22 conditions that were flagged unreadable only because of the furniture or the noise now read cleanly and are shown ("unreadable → readable" below); 2015-014718CUA #11 and 2018-011926CUA #12 show their second reading, which reads cleanly once its running header is cut (the first pass).

`text_quality` before (git HEAD) and after:

| Count | Before | After |
|---|---|---|
| garbled as extracted | 673 | 673 |
| still unreadable | 43 | 21 |
| fixed by clean-up | 570 | 589 |
| fixed by ocr | 48 | 49 |
| fixed by text layer | 12 | 14 |
| title read again: an OCR misreading of a title used on 10+ conditions | 3 | 3 |
| title read again from its condition's second reading | 2 | 2 |
| split out of the condition before it | 3 | 3 |
| section heading text cut off | 0 | 130 |
| file path text cut off | 0 | 3 |
| page header text cut off | 0 | 39 |
| mid-condition page header text cut off | 0 | 11 |
| drawing sheet / image-page OCR noise text cut off | 0 | 1 |
| next condition's title text cut off | 0 | 4 |
| drawing sheet text cut off | 0 | 2 |

## Every condition changed

"Removed" is the text taken out, as it was in the data before. "Also": what else changed on the condition.

| Decided | Record | # | Era | Kind | Removed | Chars | Also |
|---|---|---|---|---|---|---|---|
| 2015-10-29 | 2015-003049CUA | 4 | before 2019 | page header | Page 3 of | 10 |  |
| 2016-02-04 | 2015-010314CUA | 5 | before 2019 | page header | Page 2 of 5SAN FRANCISCO Motion No. 19542 CASE NO. 2015-010314CUA January 7, 2016 3128 16th Street | 99 |  |
| 2016-02-04 | 2015-010314CUA | 11 | before 2019 | page header | Page 3 of 5SAN | 15 |  |
| 2016-02-04 | 2015-010314CUA | 17 | before 2019 | page header | Page 5 of 5SAN | 15 |  |
| 2016-06-21 | 2016-000455CUA | 5 | before 2019 | page header | Motion No. 19659 CASE NO. 2016-000455CUA June 9, 2016 1327 Polk Street | 71 |  |
| 2016-06-21 | 2016-000455CUA | 16 | before 2019 | page header | SAN FRANCISCO 13P L/tNNiNG | 27 |  |
| 2016-06-21 | 2016-000455CUA | 20 | before 2019 | page header | DEP/4RTMENT | 12 |  |
| 2016-07-05 | 2016-002830CUA | 7 | before 2019 | page header | org SAN FRANCISCO 13P UNNING | 29 |  |
| 2016-07-28 | 2016-005407CUA | 5 | before 2019 | page header | SAN FRANCISCO Page 4 0# 7P LANNING DEPARTMENT Motion No. 19698 Case No. 2016-005407CUA July 14, 2016 901 Polk Street | 117 | unreadable → readable |
| 2016-07-28 | 2016-005407CUA | 17 | before 2019 | page header | P LANNING D£PAR7MENT Page 7 of | 31 | unreadable → readable |
| 2016-10-05 | 2016-005143CUA | 5 | before 2019 | page header | Motion No. 19733 Case No. 2016-005143CUA September 15, 2016 1331-1335 Polk Street | 82 |  |
| 2016-10-05 | 2016-005143CUA | 16 | before 2019 | page header | DEP/fRTMENT Motion IVo. | 24 |  |
| 2016-10-05 | 2016-005143CUA | 18 | before 2019 | page header | SAN FRANCISCO 14P tAliNING | 27 |  |
| 2016-11-21 | 2016-007216CUA | 5 | before 2019 | page header | planning.org Motion No. 19752 CASE NO. 2016-007216CUA October 6, 2016 1116 Polk Street | 87 |  |
| 2016-12-12 | 2016-002498CUA | 5 | before 2019 | page header | SAN PRANCtSCO | 14 |  |
| 2017-06-19 | 2015-014718CUA | 11 | before 2019 | page header | 'iM6NT CASE NO.2015-014718CUA | 30 | unreadable → readable; clean-up → text layer |
| 2017-07-03 | 2016-014361CUA | 11 | before 2019 | page header | SAN FRANCISCQ 16P LMINING | 26 |  |
| 2017-07-21 | 2017-000519CUA | 5 | before 2019 | page header | '~ 3 P LANNING ~6PARTM.ENT CASE NO. 2017-p00519CUA | 51 |  |
| 2017-07-21 | 2017-000519CUA | 10 | before 2019 | page header | zvww. s f-p lanning. orb SAN FRARCISCO 14P LJ~NNING ~lPApTM | 60 | unreadable → readable |
| 2017-07-21 | 2017-000519CUA | 11 | before 2019 | page header | zvunu. org saw FRnNcisco 15P LARIMW6 DBPARTNlEMT | 49 | unreadable → readable |
| 2017-08-01 | 2016-016026CUA | 15 | before 2019 | page header | org SAN FRANCISCD 15P LANNINQ | 30 |  |
| 2017-10-30 | 2016-016610CUA | 5 | before 2019 | page header | planning.org Motion No. 19991 CASE NO. 2016-016610CUA September 7, 2017 3368 19`h Street | 89 | unreadable → readable |
| 2017-11-20 | 2017-008253CUA | 5 | before 2019 | page header | saN FRanasco ~ 4P LANNING DEPARTMENT Motion No. 20051 CASE NO. 2017-008253CUA November 2, 2017 2598 Folsom Street | 114 | unreadable → readable |
| 2017-12-07 | 2017-003058CUA | 17 | before 2019 | page header | wzvw.sf pianning.org ~EP'ARTMENT | 33 | unreadable → readable |
| 2017-12-14 | 2017-012465CUA | 18 | before 2019 | page header | wwZas -Tannin orb SAN PPANCISCO | 32 | first reading → clean-up |
| 2018-01-05 | 2017-007658CUA | 5 | before 2019 | page header | SAN iRANCISCO '~ `2 Motion No. 20076 CASE NO. 2017-007658CUA December 14, 2017 4522 3`d Street | 95 | unreadable → readable |
| 2018-03-12 | 2017-010871CUA | 10 | before 2019 | page header | SAN FRANCISCO 14P L/\NNING DEPARTMENT OPERATION GASE NO. | 57 | unreadable → readable; first reading → clean-up |
| 2018-03-26 | 2017-015083CUA | 5 | before 2019 | page header | Motion No. 20113 Case Number 2017-015083CUA February 22, 2018 721 Lincoln Way | 78 |  |
| 2018-04-23 | 2017-012471CUA | 18 | before 2019 | page header | planning.org SAW FRANCISCO 8 P LANNINQi | 40 |  |
| 2018-06-13 | 2018-002906CUA | 11 | before 2019 | page header | P L/WNING | 10 |  |
| 2018-06-14 | 2016-005799CUA | 20 | before 2019 | page header | SAN FRANCISC6 | 14 |  |
| 2018-06-14 | 2017-014693CUA | 11 | before 2019 | page header | SAN FRANCISCO 16P LANNINli DEPORTMENT | 38 | first reading → clean-up |
| 2018-08-13 | 2018-003141CUA | 16 | before 2019 | page header | org DBPARTMENT | 15 |  |
| 2018-08-16 | 2018-008376CUA | 5 | before 2019 | page header | Motion No. 20243 CASE NO. 2018-008376CUA July 26, 2018 2011 Mission Street | 75 |  |
| 2018-08-16 | 2018-008376CUA | 13D | before 2019 | page header | SAN FRANCISCO 16P LANNINQ | 26 |  |
| 2018-11-19 | 2018-009951CUA | 5 | before 2019 | page header | ~ O Motion No. 20331 RECORD NO. 2018-009951 CUA November 8, 2018 1541 Sloat Boulevard | 86 | unreadable → readable |
| 2018-11-20 | 2018-011926CUA | 12 | before 2019 | page header | D6PARTMtNT | 11 | unreadable → readable; clean-up → ocr |
| 2019-04-12 | 2017-010011CUA | 5 | 2019+ | page header | Motion No. 20414 RECORD NO. 2017-010011 CUA | 44 |  |
| 2020-01-29 | 2019-006951CUA | 5 | 2019+ | page header | ENT | 4 |  |
| 2016-04-22 | 2015-005989CUA | 10 | before 2019 | mid-condition page header | CASE NO.2015-005989CUA | 23 |  |
| 2016-06-21 | 2016-000455CUA | 11 | before 2019 | mid-condition page header | sam FRa~rcisco ~2 | 18 | unreadable → readable |
| 2016-08-19 | 2016-002372CUA | 10 | before 2019 | mid-condition page header | SAN PRAFlCISCO 1 O | 19 |  |
| 2016-09-06 | 2016-004115CUA | 15 | before 2019 | mid-condition page header | SAN fRANCI$CO 1 7 | 18 | first reading → clean-up |
| 2017-03-30 | 2016-015957CUA | 11 | before 2019 | mid-condition page header | SAN FRANCISCO 15P LANNINti DEPARTMENT | 38 | unreadable → readable; first reading → clean-up |
| 2018-01-02 | 2017-008461CUA | 6 | before 2019 | mid-condition page header | '~ O | 5 | unreadable → readable |
| 2018-02-01 | 2017-006766CUA | 12 | before 2019 | mid-condition page header | SAN FRANCISCO 16P LANNINC3 DEPARTMENT | 38 | unreadable → readable; first reading → clean-up |
| 2018-03-12 | 2017-010871CUA | 6 | before 2019 | mid-condition page header | DBPARTMENT | 11 |  |
| 2018-06-05 | 2017-000514CUA | 6A | before 2019 | mid-condition page header | P UINNING DEPARTMENT 11 | 24 | unreadable → readable; first reading → clean-up |
| 2018-11-20 | 2018-011926CUA | 6 | before 2019 | mid-condition page header | ~ O PLANNING D<PARTMtNT | 24 | unreadable → readable |
| 2019-12-06 | 2019-004664CUA | 11 | 2019+ | mid-condition page header | ~ 2 | 4 | unreadable → readable |
| 2010-01-21 | 2009.1048C | 6 | before 2019 | section heading | STANDARD CONDITIONS | 20 | first reading → clean-up |
| 2010-01-28 | 2009.0251C | 6 | before 2019 | section heading | STANDARD CONDITIONS | 20 | first reading → clean-up |
| 2011-05-05 | 2011.0071C | 8 | before 2019 | section heading | Design | 7 | first reading → clean-up |
| 2011-05-05 | 2011.0071C | 9 | before 2019 | section heading | Monitoring | 11 |  |
| 2011-05-05 | 2011.0071C | 12 | before 2019 | section heading | Operation | 10 |  |
| 2011-05-05 | 2011.0097C | 11 | before 2019 | section heading | Operation | 10 |  |
| 2012-03-08 | 2011.1283C | 2 | before 2019 | section heading | D ESIGN | 8 | first reading → clean-up |
| 2012-03-08 | 2011.1283C | 4 | before 2019 | section heading | ITORING - AFTER ENTITLEMENT | 28 | first reading → clean-up |
| 2012-03-08 | 2011.1283C | 5 | before 2019 | section heading | O PERATION | 11 | first reading → clean-up |
| 2013-11-14 | 2013.0834C | 46 | before 2019 | section heading | MAXIMUM OCCUPANCY AND EVENTS | 29 | first reading → clean-up |
| 2018-06-14 | 2016-005799CUA | 6 | before 2019 | section heading | ENTERTAINMENT COMMISSION -NOISE ATTENUATION CONDITIONS Chapter 116 Residential Projects. | 89 |  |
| 2020-09-03 | 2018-015652CUA | 6 | 2019+ | section heading | sf.gov/entertainmentcommission Entertainment Commission – Noise Attenuation Conditions | 87 | first reading → clean-up |
| 2020-09-03 | 2018-015652CUA | 7E | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2020-09-03 | 2018-015652CUA | 16 | 2019+ | section heading | Operation | 10 |  |
| 2020-12-01 | 2019-017867CUA | 12 | 2019+ | section heading | planning.org Operation | 23 | first reading → clean-up |
| 2020-12-01 | 2019-017867CUA | 18 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2021-03-09 | 2020-007075CUA | 9 | 2019+ | section heading | Parking and Traffic | 20 | first reading → clean-up |
| 2021-03-09 | 2020-007075CUA | 11 | 2019+ | section heading | Provisions | 11 | first reading → clean-up |
| 2021-03-09 | 2020-007075CUA | 14 | 2019+ | section heading | Operation | 10 |  |
| 2021-03-24 | 2020-010157CUA | 10 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2021-04-15 | 2019-020049CUA | 9 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2021-04-15 | 2019-020049CUA | 13 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2021-06-09 | 2020-008474CUA | 6 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2021-06-09 | 2020-008474CUA | 9 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2021-07-16 | 2020-001973CUA | 10 | 2019+ | section heading | Monitoring - After Entitlement | 31 |  |
| 2021-07-19 | 2021-002352CUA | 5 | 2019+ | section heading | Design – Compliance At Plan Stage | 34 | first reading → clean-up |
| 2021-07-19 | 2021-002352CUA | 10 | 2019+ | section heading | Monitoring - After Entitlement | 31 |  |
| 2021-07-19 | 2021-002352CUA | 12 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2021-08-05 | 2021-002259CUA | 10 | 2019+ | section heading | Operation | 10 |  |
| 2021-08-10 | 2019-012888CUA | 13 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2021-08-13 | 2020-011615CUA | 10 | 2019+ | section heading | Operation | 10 |  |
| 2021-08-31 | 2015-009955CUA | 6 | 2019+ | section heading | Entertainment Commission – Noise Attenuation Conditions | 56 | first reading → clean-up |
| 2021-08-31 | 2015-009955CUA | 7E | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2021-08-31 | 2015-009955CUA | 18 | 2019+ | section heading | Parking and Traffic | 20 | first reading → clean-up |
| 2021-10-04 | 2021-003599CUA | 9 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2021-10-04 | 2021-003599CUA | 11 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2021-10-21 | 2021-005099CUA | 12 | 2019+ | section heading | Operation | 10 |  |
| 2021-12-22 | 2021-003396CUA | 11 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2022-01-04 | 2021-009720CUA | 12 | 2019+ | section heading | Monitoring - After Entitlement | 31 |  |
| 2022-01-04 | 2021-009720CUA | 14 | 2019+ | section heading | Operation | 10 |  |
| 2022-01-07 | 2021-003994CUA | 8 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2022-01-07 | 2021-003994CUA | 10 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2022-03-02 | 2021-008505CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2022-03-02 | 2021-008505CUA | 13 | 2019+ | section heading | Monitoring - After Entitlement | 31 |  |
| 2022-03-02 | 2021-008505CUA | 15 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2022-06-07 | 2022-001116CUA | 11 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2022-06-24 | 2021-013003CUA | 9 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2022-06-24 | 2021-013003CUA | 11 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2022-07-21 | 2022-000030CUA | 6 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2022-07-21 | 2022-000030CUA | 12 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2022-08-29 | 2021-008851CUA | 8 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2022-08-29 | 2022-000313CUA | 12 | 2019+ | section heading | Operation | 10 |  |
| 2022-11-29 | 2022-002437CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2022-11-29 | 2022-002437CUA | 8 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2022-12-05 | 2022-002108CUA | 9 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2022-12-05 | 2022-002108CUA | 11 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2023-03-17 | 2022-011855CUA | 5 | 2019+ | section heading | Design – Compliance At Plan Stage | 34 | first reading → clean-up |
| 2023-03-17 | 2022-011855CUA | 9 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2023-04-05 | 2022-004869CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2023-04-05 | 2022-004869CUA | 8 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2023-04-06 | 2019-017055CUA | 5 | 2019+ | section heading | Provisions | 11 | first reading → clean-up |
| 2023-04-06 | 2019-017055CUA | 8 | 2019+ | section heading | Operation | 10 |  |
| 2023-04-06 | 2022-012273CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2023-04-06 | 2022-012273CUA | 10 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2023-06-15 | 2022-005675CUA | 11 | 2019+ | section heading | Parking and Traffic | 20 | first reading → clean-up |
| 2023-06-15 | 2022-005675CUA | 12 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2023-06-15 | 2022-005675CUA | 15 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2023-07-27 | 2022-001407CUA | 14 | 2019+ | section heading | Parking and Traffic | 20 | first reading → clean-up |
| 2023-07-27 | 2022-001407CUA | 21 | 2019+ | section heading | Provisions | 11 | first reading → clean-up |
| 2023-07-27 | 2022-001407CUA | 24 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2023-09-14 | 2023-005278CUA | 6 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2023-09-14 | 2023-005278CUA | 8 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2023-09-28 | 2023-001895CUA | 14 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2023-11-09 | 2023-005418CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2023-11-09 | 2023-005418CUA | 11 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2023-11-30 | 2023-005339CUA | 9 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2024-01-25 | 2022-008254CUA | 11 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2024-01-25 | 2022-008254CUA | 13 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2024-02-01 | 2023-007347CUA | 5 | 2019+ | section heading | Entertainment Commission – Noise Attenuation Conditions | 56 | first reading → clean-up |
| 2024-02-01 | 2023-007347CUA | 6E | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2024-02-01 | 2023-007347CUA | 14 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2024-02-22 | 2023-000022CUA | 5 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2024-02-22 | 2023-000022CUA | 7 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2024-03-07 | 2023-011780CUA | 2 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2024-03-07 | 2023-011780CUA | 4 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2024-03-21 | 2023-008363CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2024-03-21 | 2023-008363CUA | 9 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2024-04-25 | 2023-011251CUA | 5 | 2019+ | section heading | Design – Compliance At Plan Stage | 34 | first reading → clean-up |
| 2024-04-25 | 2023-011251CUA | 10 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2024-04-25 | 2023-011251CUA | 12 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2024-08-01 | 2019-007297CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2024-08-01 | 2019-007297CUA | 8 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2024-08-01 | 2024-002929CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2024-08-01 | 2024-002929CUA | 8 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2024-09-12 | 2024-001899CUA | 5 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2024-09-12 | 2024-001899CUA | 7 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2024-09-12 | 2024-002223CUA | 2 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2024-09-12 | 2024-004781CUA | 5 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2024-09-12 | 2024-004781CUA | 7 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2024-09-19 | 2024-001579CUA | 2 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2024-09-19 | 2024-001579CUA | 4 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2025-01-16 | 2024-007818CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2025-01-16 | 2024-007818CUA | 8 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2025-01-23 | 2024-009436CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2025-01-23 | 2024-009436CUA | 8 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2025-02-27 | 2024-011113CUA | 2 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2025-02-27 | 2024-011113CUA | 4 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2025-04-10 | 2025-000941CUA | 5 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2025-04-10 | 2025-000941CUA | 7 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2025-05-15 | 2025-000726CUA | 6 | 2019+ | section heading | Design – Compliance At Plan Stage | 34 | first reading → clean-up |
| 2025-07-31 | 2025-003645CUA | 6 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2025-09-18 | 2025-003139CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2025-09-18 | 2025-003139CUA | 11 | 2019+ | section heading | Operation | 10 |  |
| 2025-09-18 | 2025-005009CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2025-09-18 | 2025-005009CUA | 8 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2025-09-25 | 2025-005018CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2025-09-25 | 2025-005018CUA | 8 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2025-10-02 | 2024-002799CUA | 6 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2025-10-02 | 2024-002799CUA | 12 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2025-12-11 | 2025-007559CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2025-12-11 | 2025-007559CUA | 8 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2026-01-15 | 2025-002411CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2026-01-15 | 2025-002411CUA | 8 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2026-02-26 | 2025-010554CUA | 8 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2026-04-23 | 2026-000475CUA | 5 | 2019+ | section heading | Design – Compliance at Plan Stage | 34 | first reading → clean-up |
| 2026-04-23 | 2026-000475CUA | 8 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2026-07-30 | 2026-002061CUA | 4 | 2019+ | section heading | Monitoring - After Entitlement | 31 | first reading → clean-up |
| 2026-07-30 | 2026-002061CUA | 6 | 2019+ | section heading | sfplanning.org. Design – Compliance at Plan Stage | 50 | first reading → clean-up |
| 2026-07-30 | 2026-002061CUA | 7 | 2019+ | section heading | Operation | 10 | first reading → clean-up |
| 2026-09-03 | 2026-004873CUA | 6 | 2019+ | section heading | sfplanning.org. Design – Compliance at Plan Stage | 50 | first reading → clean-up |
| 2010-09-02 | 2010.0255C | 20 | before 2019 | file path | SV:G:\DOCUMENTS\CONDITIONAL USES\2010.0255C - 3111 Fillmore\Motion.doc | 71 | unreadable → readable; first reading → clean-up |
| 2010-11-18 | 2010.0710C | 25 | before 2019 | file path | ESJ: | 5 |  |
| 2012-02-09 | 2011.1138C | 12 | before 2019 | file path | U:\DVu\Documents\CUs\3801 18th Street_2011.1138C\Final Motion.doc | 66 | unreadable → readable; first reading → clean-up |
| 2020-09-03 | 2018-015652CUA | 28 | 2019+ | drawing sheet | DRAFTING HOMES DraftingHomes.com Drawn by Job 9005 Date - Description - Revision 3/29/19 - Initial - 0 4/10/19 - Scope of each Floor - 1 N 68.75 88.75 37.75 137.50 38.75 68.75 29.75 88.75 29.75 Powell St. | 205 | first reading → clean-up |
| 2022-03-02 | 2021-008505CUA | 20 | 2019+ | drawing sheet | EXHIBIT B: Plans & Renderings | 30 | first reading → clean-up |
| 2016-12-19 | 2016-008418CUA | 15 | before 2019 | drawing sheet / image-page OCR noise | :r~' ~ Yrsf~ ~:~"a ~ ' I r'I_~~__ ~' " 1_ ~L ~.li~ _yf~ ~ r _ I'~ ~ VIII ~~_~~~ ~I ',l a~~~{ r ~ ~±'~~~1~'~ ~~~~ ~.J': I IT!~l-i~Y ~~A1~~i C~ ~~ 'I .11 ' ~~'~~. :~Y:al n1k 5~~~ f _ ~ ~ _~ ~~ rl: ".~ ~' ~''„;{ .~ hLl ~ F NL', \~J:• ~' _? ~1;~ ~~'~ ='~_~LYt.•I'~.~J''' I~ I'n:P~ tint :~ ~~' r n :~lay~~.' ~.l~7~7'~~1 ~~ ,~~ .ti ~ - .7 -"~J11~7C ~~ I -~A~~"~ y' -4_~~: ~ -fir 'L | 376 | unreadable → readable |
| 2018-06-13 | 2018-002906CUA | 6 | before 2019 | next condition's title | Revocation due to Violation of Conditions. | 43 | first reading → clean-up |
| 2019-02-01 | 2018-010700CUA | 8 | 2019+ | next condition's title | Rooftop Mechanical Equipment. | 30 | first reading → clean-up |
| 2019-03-06 | 2018-015439CUA | 8D | 2019+ | next condition's title | Sidewalk Maintenance. | 22 |  |
| 2019-04-24 | 2018-016549CUA | 8D | 2019+ | next condition's title | Sidewalk Maintenance. | 22 |  |

## Seen in the scan, not changed

- 2010.1080C #4 ends "... and work with the Planning Department. pla Jill in gory". The verifier listed it with the page furniture, but it is the OCR of the contact line's web address (the PDF reads "www.sfpla Jill in gory", after "Planning Department at 415-575-6863,"), with no furniture after it, so it is left with the other contact lines. So are the other conditions that end in a contact line or a piece of one with nothing after it: for example "orb" (2016-007531CUA #7, 2018-016600CUA #13, 2019-004664CUA #7), "planning," (2016-008229CUA #9), "men" (2016-000892CUA #21, from "entertain men t"), "F or information about compliance, contact" (2024-002223CUA #1) and the phone numbers on 2010-2011 motions ("6863,"). 2016-002372CUA #10 keeps "Works, 415-695-2017," after the footer taken out of it; 2018-008376CUA #13D keeps "Public Works." (the end of its contact line) before the footer that was cut.
- 2016-005143CUA #16 ends "... Should the contact information change, the Zoning Administrator shall be made aware of such change. T'he community liaison": the first reading lost the rest of the sentence, which the PDF has after the page header ("shall report to the Zoning Administrator what issues, if any, are of concern to the community ..."). The header was cut; the lost words are not restored here.
- 2013.0292C #4 and 2017-005533CUA #6 have no text after their title ("Condition:"): text lost by the first reading, not text from another page.
- Conditions whose text stops without a full stop because the first reading cut it short ("… and work with the Planning Department", 29 conditions; "… as set forth…") are real text and are left.

## Conditions missing from the data

Conditions the motion PDF has but the data does not: the first reading took each one's title onto the end of the condition before it and lost its text (the PDF prints it as an unnumbered paragraph, so it was not split off). The title is now cut off the condition before it (above, or with the section heading for 2016-005799CUA #6); the missing condition is **not** added to the data (left open). Pages are the PDF's pages (`$LOCAL_DATA_DIR/conditions_pdf_public/<record>.pdf`), the same as the printed page numbers.

| Record | Decided | After condition | Missing condition (its title as in the PDF, and how it starts) | PDF page | Numbering in the data |
|---|---|---|---|---|---|
| 2016-005799CUA | 2018-06-14 | #6 Additional Project Authorization | Chapter 116 Residential Projects. "The Project Sponsor shall comply with the \"Recommended Noise Attenuation Conditions for Chapter 116 Residential Projects,\" ... These conditions state:" (under the heading ENTERTAINMENT COMMISSION - NOISE ATTENUATION CONDITIONS; the lead-in of #7 and the conditions after it) | 14 | 6 -> 7: no gap, the paragraph is unnumbered |
| 2018-002906CUA | 2018-06-13 | #6 Enforcement | Revocation due to Violation of Conditions. "Should implementation of this Project result in complaints from interested property owners ..." | 15 | 6 -> 7A: no gap, the paragraph is unnumbered (before OPERATION, 7. Eating and Drinking Uses) |
| 2018-010700CUA | 2019-02-01 | #8 Signs and Awnings | Rooftop Mechanical Equipment. "Pursuant to Planning Code 141, the Project Sponsor shall submit a roof plan ..." | 6 | 8 -> 10: it is #9 |
| 2018-015439CUA | 2019-03-06 | #8D Eating and Drinking Uses (D) | Sidewalk Maintenance. "The Project Sponsor shall maintain the main entrance to the building and all sidewalks abutting the subject property ..." | 7 | 8D -> 10: it is #9 |
| 2018-016549CUA | 2019-04-24 | #8D Eating and Drinking Uses (D) | Sidewalk Maintenance. "The Project Sponsor shall maintain the main entrance to the building and all sidewalks abutting the subject property ..." | 7 | 8D -> 10: it is #9 |
