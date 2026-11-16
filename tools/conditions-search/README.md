# Conditions of approval: local search

A local page to search the conditions of approval in San Francisco Planning Commission motions on food, drink
and entertainment premises. Filters: business type, condition category, zoning district, year decided, and
which conditions (see below); plus a text search. Each result shows the condition text, the case and its
decision date, and a link that opens the motion at the page where the condition starts ("near page" when the
page was found from a passage further into the condition), with a second, smaller link to Planning's own copy
(Planning's link downloads the PDF, so it cannot open at the page). No statuses, conclusions or summaries.

Local only. Build the data and the links to the cached motion PDFs, then serve the folder:

    apps/api/.venv/bin/python scripts/validation/build_conditions_index.py
    python3 -m http.server 8765 --bind 127.0.0.1 --directory tools/conditions-search

and open http://127.0.0.1:8765/. `pdf/` holds links to the PDFs under $LOCAL_DATA_DIR/raw and is not
committed. Tests: `make test-conditions` (node --test, against the real `data/conditions.json` and `index.html`).

## Coverage

The page opens with a short coverage note. This section is the detail behind it. The page links to it as
`coverage.html`, which shows this section with a table of the numbers from the current data file on top: how
many cases were looked up, how many motions were found, kept and left out, the dates, and the text and page-link
counts. The note and that table are worked out from `data/conditions.json` when the page loads (`coverage.js`),
so they change with the data. This section gives no counts, so it does not go out of date when the data is built
again.

### What is included

- **Type of decision.** San Francisco Planning Commission motions on Conditional Use cases (DataSF Planning
  records of kind "cua"). Amendments to an earlier approval (records ending in "-02") count as their own case.
- **Type of premises.** Food, drink and entertainment premises, as the premises classifier labels them and a
  AI review corrected (see [Reviewed list](#reviewed-list) below). The business type on the page is the
  classifier's use, or the review's where the review gives one: restaurant or cafe, bar, nighttime
  entertainment, or other food and drink.
- **Outcome.** Approved, approved with conditions, or denied. A denial usually has no conditions.
- **Dates.** Cases decided on or after 1 Jan 2010 (`SINCE` in `scripts/validation/full_conditions.py`). The
  first and last decision dates in the data are in the table on `coverage.html`.

### How the motions were found and picked

1. **Cases.** `full_conditions.py` took every Conditional Use case in the local copy of Planning's DataSF
   records that was decided on or after 1 Jan 2010, was approved, approved with conditions or denied, and that
   the classifier's labels at the time of the look-up said was a food-or-drink premises and a use decision.
   The labels were made again later, so some of these cases no longer pass that test. Step 3 deals with that.
2. **Motions.** For each case it looked for the motion PDF in Planning's hearing document index. It then took
   every numbered condition from the motion's conditions section.
   Motions of older cases (decided before `OLDER_FORMATS_BEFORE` in `full_conditions.py`, by the case's
   decision date, the date this page filters on) are read for the older layouts too
   (`all_conditions(older_formats=True)`); newer motions are read exactly as before. How older motions are
   read and numbered is in [Older motions](#older-motions) under Text quality.
3. **Food-or-drink check.** `build_conditions_index.py` checks every motion found against the current labels
   (local table `record_labels`, made by `classify_records.py` with Claude Haiku, plus a fixed rule for cannabis
   and gyms). It keeps a motion only when they say it is a food-or-drink premises with a food-or-drink use.
4. **Review (by an AI model, not a person).** The reviewed list, `reviewed-labels.json`, then overrides the classifier in both
   directions: an "include" brings a motion it left out back onto the page with the business type the decision
   gives (or sets the business type of a motion it kept), an "exclude" takes off a motion it kept. Each decision
   has what the motion is and the reason. The rules the review followed are in `REVIEWED.md`. The motions left
   out are listed, with who left them out (the classifier or the review).
5. **Conditions.** Most kept motions have conditions. A denial often has none; those motions are listed in the
   page footer.

### What is not included

- Motions that are not food or drink, after the review. They are listed in
  [Motions left out](#motions-left-out-not-food-or-drink) below and in the page footer.
- Cases with no motion in Planning's document index. `coverage.html` lists them, and says which ones are food or
  drink under the current labels.
- Motions with no conditions section.
- Cases decided before 1 Jan 2010, and cases decided after Planning's records were last copied (the date is on
  `coverage.html`).
- Entertainment Commission permits and their conditions.
- Board of Appeals decisions.
- ABC (state alcohol licence) conditions.
- Building permits.
- Approvals made without a Planning Commission motion, such as administrative approvals.

Entertainment Commission data, when it arrives, is a separate dataset. It will not be merged into this page.

### Known gaps

- **The classifier makes mistakes; the review corrects the ones it found.** The corrections are in
  [Reviewed list](#reviewed-list) below. A motion the review did not catch can still be on the wrong side.
- **Some text could not be read.** A few conditions are still flagged as unreadable and link to the motion page
  instead. See [Text quality](#text-quality).
- **Some text comes from OCR.** Older motions are scanned. Where the first reading of a condition was garbled,
  it was read again by OCR. Single misread words can still show in conditions marked readable.
- **Some page links are approximate.** Some conditions link to a page near the condition ("near page"), not the
  page where it starts.
- **Page links need a copy of the PDF.** Locally they open the cached motion (`pdf/`). The public site links
  smaller copies of the same adopted motions, kept in the site's file storage (a public Vercel Blob store); see
  [Motion PDFs on the public site](#motion-pdfs-on-the-public-site).
- **Dates.** Nothing decided after Planning's records were last copied is here. New cases are added only when
  the records are copied, looked up and built again.
- **Cases with no motion are not looked up again.** `full_conditions.py` skips every case it has already looked
  up, including cases where it found no motion. If Planning posts that motion later, it is not added. To retry a
  case, delete its row in the local table `case_motions` and run the look-up again.

## What the page shows by default

Case-specific conditions first, then standard ones, newest decision first in each. Approval boilerplate is
hidden. Pick it under "Which conditions" ("Approval boilerplate only" or "Everything"); the count bar also says
how many boilerplate conditions are hidden and has a "show them" link.

**Approval boilerplate** is the set of conditions about the approval itself, worded the same on every motion.
They are the conditions with these titles (set in `BOILERPLATE_TITLES` in the build script, matched on the
title's letters, so OCR spacing does not matter):

- Validity (and "Validity and Expiration", its title on older motions)
- Expiration and Renewal (also the OCR misreading "Eacpiration and Renewal")
- Diligent Pursuit
- Extension
- Conformity with Current Law
- Enforcement
- Revocation due to Violation of Conditions
- Monitoring (the monitoring-fee condition)
- Severability (none in the data today)

Shared operating conditions are **not** boilerplate, because they say how the business must run: community
liaison, sidewalk maintenance, garbage, odor control, lighting, noise, notices posted at bars and entertainment
venues, and so on. They show as "Standard". "Standard" means the same wording opens the same-titled condition on
at least five motions, or the title is on at least half of the approved motions for that kind of use. Everything
else is "Case-specific".

One more rule, set in the build script (`template_parts`): a lettered part of a set, such as "Liquor Stores (B)"
or "Chapter 116 Residential Projects (C)", is "Standard" when the same part is worded the same (90% of its first
300 letters) on at least two motions. These are Planning's template conditions. The five-motion rule missed them
because each set is on only two to four motions, so they used to lead the default view as if they were
case-specific. In the current build 21 conditions are standard by this rule (for example
Liquor Stores (A)-(C) and Chapter 116 Residential Projects (A)-(E)).
A set on one motion only (for example Good Neighbor Policies (A)-(E) at
2021-009937CUA) stays case-specific, even when its wording matches another set.

## Search

- Every word you type must appear in the condition (title or text), in any order.
- A case number finds its motion's conditions, as the card shows it or shorter: "2023-005418CUA", "2023-005418",
  "2023-005418 CUA", "005418", "2015-002658CUA-02", "2011.0097CUA-02", "0097CUA", "002658CUA-02". The one case
  number with an underscore, "2010.1070C_3" (as Planning's data lists it), is read the same way, the underscore
  as the hyphen of "-02": "2010.1070C_3", "2010.1070C" and "1070C_3" find it. The serial
  part alone counts only when it is six digits or starts with a zero, so "2022" or "1036" stays a plain number. A
  case number that is not on the page (an earlier case quoted in a condition, "2013.0023C") is searched in the
  condition text instead; year ranges ("2019-2020") and phone numbers are ordinary words.
- A house number followed by its street finds the conditions at that address: "2351 Mission", "2351 Mission St",
  "2351 Mission Street", "2351 Mission 94110", "36 W Portal Ave", "2505 3rd Street" (Planning writes "2505 03Rd St"). Street types match written out or
  short (Street/St, Avenue/Ave/Av, Boulevard/Blvd/Bl...). It counts as an address only when those words begin an
  address on the page; a number, a street type or a zip code on its own ("500 feet", "2022", "street", "st",
  "94110") searches the condition text only. Other words narrow it: "2351 Mission noise".
- A street name with no house number finds every motion on that street, and any condition whose text names the
  street: "Valencia St", "Valencia Street", "Mission", "24th St", "24 St", "9th Avenue", "Broadway", "Van Ness
  Ave", "W Portal". The street of a motion is read from its address (`streetOf` in `search.js`): the words after
  the house number, or the range of house numbers, up to and including the street type ("2740 - 2744 Mission St"
  is on Mission St, "1210 09Th Ave" on 9th Ave, "412 Broadway" on Broadway, "2200 A Market St" on Market St).
  - Written alone, the name finds the street whatever its type: "19th" finds 19th St and 19th Ave. With a type,
    written short or long, it is that street only: "19th St" is not 19th Ave, "Geary Blvd" is not Geary St. The
    text is searched as before streets were: a condition whose text has every word typed, in any order, also
    counts, and a typed street type counts in any of its forms ("Valencia St" counts a condition that says
    "Valencia Street"). So a street search finds everything the same words found before, and more.
  - Ordinals match however Planning or you write them: "24th St", "24Th St", "09Th Ave" = "9th Ave". A number
    followed by a street type is that ordinal street when it is on the page ("24 St" is 24th St); a bare number
    ("24") stays a number.
  - A direction may be a letter ("W Portal" is West Portal). A street named with a direction also answers to its
    name without it, unless that is another street: "Portal" is West Portal Ave, but "Van Ness" is Van Ness Ave
    only (South Van Ness Ave is another street).
  - Street names are compared word for word as written, not by their stem, so "posted" is not Post St and "pins"
    is not Pine St. A street word counts only when a motion on the page is on that street; others ("San
    Francisco", "Embarcadero") stay ordinary words.
  - Other words narrow it: "Mission noise" is the Mission St motions, and conditions naming Mission, that speak of
    noise. A house number before the street makes it an address ("2351 Mission"), as above.
  - A street's motions whose only conditions are approval boilerplate (three today: one each on Sloat Blvd, West
    Portal Ave and Ocean Ave) are behind the "Which conditions" filter like any boilerplate; the count bar offers
    "show them".
  An address Planning writes as a range of house numbers ("2740 - 2744 Mission St") answers to the range as written
  and to each number in it on the same side of the street (2740, 2742, 2744); a range wider than 100 numbers answers
  to its two ends only. The matched case number or address (or the address on a matched street) is
  marked on each card.
- Simple word endings do not matter: guard, guards, guarded and guarding are the same word; so are odor and
  odors, close and closing, light and lighting.
- Some words keep their ending because it is part of the word (`KEEP_ENDING` in `search.js`): parking is not
  park, building is not build, planning is not plan, news is not new.
- Single letters are ignored. "a.m." or "p.m." on its own finds any morning or evening time.
- Times match however they are written: "10 p.m.", "10pm", "10 PM", "10:00 p.m." and "10:00PM" are the same.
  A bare number finds that hour too ("10" finds "10:00 p.m.").
- A short synonym list (`SYNONYM_GROUPS` in `search.js`). Within a group every entry counts as every other, so
  a word you type also finds the conditions that use any other entry of its group:
  - guard, security guard, security personnel, security staff, security officer, bouncer, doorman, door staff
  - hours, closing time, opening hours
  - noise, sound, amplified, loud
  - live music, live entertainment, live performance
  - midnight, 12 a.m.
  - odor, odour
  - liquor, alcohol, alcoholic

  Entries follow the same rules (endings and time forms do not matter). A two-word entry ("security
  personnel", "closing time") matches the two words side by side, and typing it counts as one word. The page
  shows the list under "Search tips", below the search box. "Security staff", not "staff" alone: on these
  motions "staff" is always Planning Department staff ("subject to Department staff review", 60 conditions), so
  a bare "staff" would make "guard" find those.
- The search box and the filters are kept in the address (`#q=...&kind=...`), so a link shares a search. The
  page runs the search again whenever the address changes (a shared link opened in the same tab, the back
  button, an edit in the address bar); fields the new address leaves out are cleared (`stateFromHash` in
  `search.js`).

The search code is `search.js`. The page and the tests both load it.

**"Security guard" finds the few conditions that require security staff, all on older motions.** "Security
guard" is one entry of the guard group, so it finds conditions that use any entry of the group. Four conditions
do, all on motions decided before 2019:

- 2010.0970C 22 (Trigger, a bar): "Police Specials" or other trained security within a block, and staff or hired
  security guards at every entrance and exit.
- 2013.0834C 15 and 45 (Nob Hill Masonic Center): security personnel directing garage traffic at events with more
  than 1,250 ticketed patrons, and the venue's security personnel, private security or police for an event with a
  record of safety problems.
- 2017-006766CUA 27: a mandatory security guard on duty in the evening.

No 2019+ condition mentions a guard, security personnel, security staff, a security officer, a bouncer or door
staff (the one that said "security personnel", 2021-010728CUA, is a cannabis store the review removed; two
motions, 2018-015652CUA and 2024-002799CUA, mention security personnel in their findings, not in a condition).
"Law enforcement personnel" (window signage at liquor stores) is not matched, on purpose. Security staffing for
bars and venues is usually set by the Entertainment Commission or the ABC licence, not in the Planning motion.

What the page does about it:

- The placeholder shows examples that find real conditions: odor, amplified music, 10 p.m., outdoor seating,
  patrons. A test checks that every placeholder example finds at least one condition.
- When a search finds nothing, the page names the words no condition uses: "No condition on these motions uses
  “zzz”." When the missing word is one of the guard group it adds why (`GROUP_NOTES` in `search.js`): security
  staffing is usually a condition of the Entertainment Commission permit or the ABC licence, which the page does
  not include, and the nearest Planning condition is the notice asking patrons to leave quietly ("patrons"). It
  is shown only when no condition on the page uses any word of the group, so with the four conditions above it
  does not show; the tests check it on the data without them.
- "Loud" is not on any condition either; it is in the noise group, so "loud music" finds the music conditions
  that speak of noise, sound or amplified music.
- The tests check every synonym group on made-up conditions (so "security guard" finds security personnel and
  security staff, and not Department staff or law enforcement personnel) and on the real data.

## Text quality

Older motions are scanned, and their text comes from OCR. The build checks every condition for pieces that do not
read (`scripts/validation/condition_text.py`):

- **Hard pieces**, never real condition text: a word with a stray symbol ("commu~~ity", "tvzvzv_s~"), letters
  mixed with digits ("Tl1e", "Apri120th"), and page furniture or web-address pieces left behind ("SAN FRANCISCO
  13P LANNING", "www.s - Tannin .or", a dangling "For information about compliance, contact"). **One is enough.**
- **Unreadable words**: lower-case words that are neither in the system word list (/usr/share/dict/words) nor
  used in at least three motions ("informatiofi"). Two or more (or 8% of the words) are enough. A single one is
  allowed, because real words such as "graffiti", "online" and "weeknights" are missing from the word list too.

The steps, in order:

1. Clean-up. Most junk is page furniture that leaked into a condition: the "For information about compliance,
   contact Code Enforcement ... www.sf-planning.org" line (also when the reader split a word: "info rmation",
   "comp liance"), the "SAN FRANCISCO PLANNING DEPARTMENT" page footer in its OCR forms ("SAN FRANCISCO 13P
   LANNING", "SAN fRANCISC~ 6"), the running header ("Motion No. ... RECORD NO. ...", or its date and street
   address after the footer), mangled web addresses ("unow. L a n n i ng. org") and section headings in
   capitals. These are removed. Words split by a stray space ("comme ncing") are joined. Times with the letter O
   for zero ("7:OOAM") are fixed.
   Text from a page that is not a condition, run on into a condition's end, is cut off at the condition's last
   sentence (`leak_cut`, 2026-11-13): a **drawing sheet** bound in after the conditions (2018-015652CUA #28 ended
   "... between midnight and 6 a.m. DRAFTING HOMES DraftingHomes.com Drawn by Job 9005 ... 68.75 88.75 37.75
   137.50 ... Powell St.") and the **page header** in the forms the clean-up above missed ("Motion No. 20113 Case
   Number 2017-015083CUA February 22, 2018 721 Lincoln Way", "RECORD NO. 2017-010011 CUA"). The signatures are
   title-block words (Drawn by, Checked by, Job No., Sheet No., Scale:, Date - Description - Revision), a drafting
   firm's web address, "FLOOR PLAN"/"SITE PLAN", four or more dimensions in a row ("68.75 88.75 37.75 137.50"),
   feet-inch dimensions (12'-6"), seven or more room labels or numbers in a row, and the running header. One only
   counts when everything from it to the end reads as labels and numbers, not prose, so a condition about plans
   "drawn by the architect", hours ("10 p.m."), code sections ("303.1"), phone numbers or addresses is never cut.
   After the last sentence, more text that is not the condition is cut off (`tail_cut`, 2026-11-13, second pass):
   the page footer and header in the OCR forms the clean-up above missed ("SAN FRANCISCO 13P L/tNNiNG", "saw
   FRnNcisco 15P LARIMW6 DBPARTNlEMT", "P LANNING D£PAR7MENT Page 7 of", "Page 3 of 5SAN"; a word counts when its
   letters are close to FRANCISCO, PLANNING or DEPARTMENT and it is not written as a word of a sentence), the
   **next section's heading** ("Operation", "Monitoring - After Entitlement", "Design – Compliance at Plan Stage",
   "Parking and Traffic", "Provisions", "O PERATION": the headings that start the condition groups in the
   motions' Exhibit A, `SECTION_HEADINGS`), a word-processor **file path** ("U:\DVu\...\Final Motion.doc") and the
   plan set's cover title ("EXHIBIT B: Plans & Renderings"). Pieces come off the end one at a time and the cut is
   kept only where what is left ends a sentence or a contact line, so a condition is never cut inside its own
   text. Two more kinds (third pass): an **image page's OCR noise**, a run of symbols and non-words after the last
   sentence (2016-008418CUA #15: ":r~' ~ Yrsf~ ~:~"a ~ ..." from a picture page bound in after the conditions;
   cut when what follows the sentence end is mostly symbols, few words by the build's vocabulary, never three
   words in a row), and the **next condition's title** whose text the first reading lost: a title-case phrase
   that is the whole last sentence and a title used on 10+ conditions ("Rooftop Mechanical Equipment.",
   "Sidewalk Maintenance."), after the last sentence or after what is kept of a contact line, which stays. Those
   lost conditions are listed in the list file ("Conditions missing from the data"), not added to the data.
   Page furniture between two words of a sentence, where a page broke, is taken out in a few exact shapes
   (`inside_cut`: "the Zoning CASE NO.2015-005989CUA Administrator", and the footer as OCR garbled it: "SAN
   fRANCI$CO 1 7", "sam FRa~rcisco ~2", "DBPARTMENT", "~ 2"). Contact lines ("For information about
   compliance, contact ...") are left as they are, a separate decision. Which reading of a condition is shown
   (first reading, text layer, OCR) is picked before these cuts; the picked reading is then cut.
   190 conditions were cut in all: 39 page header, 11 page header inside a sentence, 130 section heading, 3 file
   path, 2 drawing sheet, 1 image-page OCR noise, 4 next condition's title; 63 on motions decided before 2019,
   127 on 2019+ motions (all junk: 119 headings, 2 running headers, 2 plan sets, 3 next-condition titles, 1 page
   number inside a sentence). Every one is listed, with what was removed, in
   [sheet-leaks-2026-11-13.md](sheet-leaks-2026-11-13.md), and each was checked against the motion PDF. A test
   checks the built data with patterns of its own (page furniture, a heading from a fixed list, file paths, the
   plan set's title, title-block words and dimension runs at the end of a condition, a symbol-heavy tail after a
   sentence end, a last sentence that is a title used on 10+ conditions) and expects none.
2. Split. When the reader missed a section heading ("MONITORING - AFTER ENTITLEMENT") and the next condition ran
   on into this one, the next condition is split out with its own number and title, instead of being cut off
   with the heading. Three conditions came back this way, all "Enforcement" (2019-006951CUA #7, 2018-016600CUA
   #6, 2019-020852CUA #6). Two of them only had their title or a few words in the first reading; their text
   comes from OCR.
3. Text layer. A condition with any hard piece or unreadable word is read again from the PDF's own text layer
   (`pdftotext -layout`).
4. OCR. If it still has a hard piece or is garbled, its pages (one either side too) are OCR'd with tesseract at
   300 dpi. The results are cached under $LOCAL_DATA_DIR/conditions_ocr/<record>/ (not in the repo).
5. Matching a second reading. A second reading counts when it has the same condition number and a close title
   and opening. When it lost the number (OCR often does), the condition is found by its title, and the length
   that best matches the first reading is taken.
6. The second reading must be the same text, word for word, read better: no added words (a running header, the
   next condition's opening), no lost readable words (only junk, or furniture at the very end), and no new symbols
   ("April 20%" for "Apri120th" is refused). The reading with the fewest bad pieces wins.
7. A condition that still has a hard piece or is still garbled is marked unreadable. The page shows "The text of
   this condition could not be read cleanly" with a link to the motion page, and keeps the extracted text behind
   a "show anyway" toggle.

Counts from the current build (`text_quality` in `data/conditions.json`; conditions on the 371 motions kept
after the review, decided 2010 on):

| | Conditions |
|---|---|
| Garbled as extracted | 673 |
| Fixed by clean-up | 589 |
| Fixed by the PDF text layer | 14 |
| Fixed by OCR | 49 |
| Still unreadable (flagged, linked to the motion page) | 21 |
| Split out of the condition before it | 3 |
| Title read again from its condition's second reading (older motions) | 2 |
| Title read again: an OCR misreading of a title used on 10+ conditions (older motions) | 3 |
| Drawing-sheet text cut off (see [the list](sheet-leaks-2026-11-13.md)) | 2 |
| Page-header text cut off (see [the list](sheet-leaks-2026-11-13.md)) | 39 |
| Page-header text taken out of a sentence (see [the list](sheet-leaks-2026-11-13.md)) | 11 |
| Next section's heading cut off (see [the list](sheet-leaks-2026-11-13.md)) | 130 |
| File path cut off (see [the list](sheet-leaks-2026-11-13.md)) | 3 |
| Image-page OCR noise cut off (see [the list](sheet-leaks-2026-11-13.md)) | 1 |
| Next condition's title cut off (see [the list](sheet-leaks-2026-11-13.md)) | 4 |

The 21 still flagged (18 on motions decided before 2019, 3 on 2019+ motions; 43 before the cuts of 2026-11-13,
which let 22 read cleanly): a condition is flagged when, after
the clean-up and the second readings, it still has a hard piece or is still garbled (the rules above). They are
2010.0514C #1, 2013.0224C #17, 2013.0834C #15, 2013.0834C #17, 2013.0834C #22, 2013.0834C #24, 2013.0834C #40,
2013.0834C #43, 2016-000388CUA #12, 2016-008229CUA #17, 2016-013271CUA #1, 2014-001457CUA #8, 2017-000519CUA #5,
2017-007658CUA #12, 2016-010348CUA #9, 2017-012471CUA #8, 2016-005799CUA #20, 2018-003874CUA #8B,
2018-012330CUA #11, 2018-016600CUA #11, 2019-004664CUA #8A. A test (`make test-conditions`)
runs the same hard-piece check over every condition shown as readable and expects none, with an explicit allow-list
(empty today), and checks every title, readable or not, for stray symbols ("#" included).

Single unreadable words can still show in readable conditions, for example a misread such as "anck" for "and".

### Older motions

Motions of cases decided before 2019 are read with `all_conditions(older_formats=True)`, which also reads the
2009-2018 layouts: untitled numbered paragraphs (2009-2010, title "Condition"), titled paragraphs with no numbers
in the text layer (2012, numbered in order), numbers written "1)" (2016-2017) or "10..", numbers lost or garbled
by OCR (restored from the titled paragraphs in the gap, one per missing number; when there are fewer titled
paragraphs than numbers missing they take the first missing numbers, as 2016-002786CUA's unnumbered
"Enforcement." between 5 and 8 becomes 6; an "S." or "$." where only the 8 is missing is the 8), untitled numbered
paragraphs that go on after the last titled condition (2010.1162C 30-33, 2011.0126C 24, 2013.0224C 23: they ran on
inside the last condition, whose text is cut at 600 characters, so most of them were lost), titles that open with
a quotation mark or carry curly quotes and Unicode dashes (2011.0701C "‘Bar Use’ ‐ Hours of Operation"), and "For
information about compliance" contact lines in their OCR forms ("Far information", "For .information", a page
footer between "For" and "information"). The Monitoring template's own last sentence ("... work with the Planning
Department for information about compliance.") is kept whole; only the contact line after it is removed. A
motion whose text ends before its conditions (a short last page taken for a plan sheet) is read again with
`pdftotext`, and a Mitigation Monitoring and Reporting Program appended as Exhibit C after the conditions is cut
off, so its table rows are not read as conditions. A motion dated more than a year after the case's decision is
for a later decision on the same record (2015-002658CUA, decided 2015-12-11, was given Motion No. 21682 of
2025-02-13, the motion of 2015-002658CUA-02): it is refused and the case is recorded as not found ("motion found
is for a later decision"). 2019+ motions are read exactly as before.

Some older motions restart their numbering under each heading. 2012.0262CUA prints PERFORMANCE 1-6, then
DESIGN 1 (its number lost in OCR) and 2, MONITORING 3, OPERATION 4-5 (numbers lost) and 6. Each condition must
keep a number of its own, so a later list that repeats a number already used gets its position in the motion as
a prefix with a dot: **"2.3" is condition 3 of the motion's second list**, and its lettered parts are "2.3A",
"2.3B". A plain number ("3") or a lettered part ("8A") never has a dot, so the two cannot be confused; conditions
sort by list, then number, then letter. A later list that repeats no number keeps its numbers as printed. A
number printed twice with the numbering going on after it is a printing slip, not a restart: 2010.0514C prints
1-5, a second "5.", then 6-13; the second 5 is a list of its own, "2.5", and 6-13 keep their numbers.

On older motions only, the clean-up also finds the contact line when the reader split "about" or "compliance"
("abou t", "c ompliance": 2012.0525C #4, 2013.0290C #7) or laid it out in a column beside the condition's last
line, so the two came out interleaved ("... in compliance with the For information about Department of Public
Works ... Standards. compliance, contact Bureau of Street Use ...": 2010.0912C #18; only the exact opening "For
information about" and a "compliance, contact" within 200 characters, the condition's own words between them
kept). A title OCR misread is read again (`retitle` in the build script), and the condition's kind and standard
flag are worked out again under the new title:

- a title with a stray symbol takes its kept second reading's own heading ("E~ctension" becomes "Extension",
  2016-005799CUA #4);
- a title used on fewer than 10 conditions that is one OCR swap or two from a title used on 10 or more conditions (letters at
  least 93% the same, characters only swapped, no word added or lost, no digit for a digit, the same lettered
  part) takes that title, or the kept reading's own heading when that is such a title. Today: "Revocation dne to
  Violation of Conditions" (2016-000455CUA #11, 2016-000332CUA #7, now boilerplate), "Gazbage, composting and
  recycling storage" (2017-000519CUA #6, from its OCR reading's heading) and "Notices Posted at Bars and
  Entertainmen# Venues" (2017-015181CUA #13), both now standard.

Titles and contact lines of 2019+ motions are never changed this way.

## Counts

The page lists 5,049 conditions: 1,919 approval boilerplate (hidden by default), 2,374 standard and
756 case-specific. The default view shows 3,130.

The header and the list count the same thing: motions that have conditions on the page. The count bar reads
"N conditions from X of Y motions", where Y is that total and X is how many match the filters.

How the motions were picked, from the 488 motions found:

| | Motions |
|---|---|
| Kept by the classifier | 423 |
| Left out by the classifier | 65 |
| Added back by the review | 4 |
| Removed by the review | 56 |
| Kept, business type corrected by the review | 29 |
| **Kept in the end** | **371** |
| Left out in the end | 117 |

Of the 371 kept, 352 have conditions (5,049 conditions) and 19 have none (the motion has no
conditions section):

- 2010.0360C, 1411 - 1433 Polk St, San Francisco, Ca 94109 (denied)
- 2010.0072C, 627 Vallejo St, San Francisco, Ca 94133 (outcome not read from the motion)
- 2010.0436C, 1685 Sacramento St, San Francisco, Ca 94109 (denied)
- 2010.0969C, 116 - 118 Taylor St, San Francisco, Ca 94102 (denied)
- 2011.1404C, 2201 - 2207 Market St, San Francisco, Ca 94114 (denied)
- 2012.1356C, 2100 - 2114 Market St, San Francisco, Ca (denied)
- 2012.0822C, 1881 Post St, San Francisco, Ca 94115 (outcome not read from the motion)
- 2013.1456C, 3100 - 3112 24Th St, San Francisco, Ca 94110 (approved with conditions, no conditions section found)
- 2014.0675C, 2275 Market St, San Francisco, Ca 94114 (approved with conditions, no conditions section found)
- 2014.1111C, 2232 - 2240 Taraval St, San Francisco, Ca 94116 (approved with conditions, no conditions section found)
- 2014.0977C, 2300 - 2312 Market St, San Francisco, Ca 94114 (approved with conditions, no conditions section found)
- 2014.0762C, 3000 - 3012 Taraval St, San Francisco, Ca 94116 (approved with conditions, no conditions section found)
- 2015-005723CUA, 3995 Alemany Blvd 94132 (approved with conditions, no conditions section found)
- 2014-000285CUA, 1515 Pine St 94109 (approved with conditions, no conditions section found)
- 2015-005379CUA, 2261 Fillmore St 94115 (approved with conditions, no conditions section found)
- 2015-016033CUA, 3629 Taraval St 94116 (approved with conditions, no conditions section found)
- 2016-010632CUA, 201 Steiner St 94117 (denied)
- 2018-008372CUA, 1123 Folsom St 94103 (denied)
- 2018-006127CUA, 201 19Th Ave 94121 (denied)

The page footer names them.

## Motions left out: not food or drink

A motion stays when the premises classifier (local table `record_labels`, built by
`scripts/validation/classify_records.py`) says its record is about a food-or-drink premises (`premises` true)
AND gives it a food-or-drink use (`use_class` not "none"), unless the reviewed list says otherwise (see
[Reviewed list](#reviewed-list)). The build prints every motion it leaves out, and the page lists them in its
footer.

Left out now: 117 motions (of 488): 61 by the classifier and 56 removed by the review. "Left out
by" says which. "Classifier" is what the classifier said (for a motion the review removed, the classifier had
kept it). Where the review has a decision on the motion, "What it is" is the review's description.

| Record | Address | What it is | Left out by | Classifier |
|---|---|---|---|---|
| 2009.1103C | 1878 Haight St, San Francisco, Ca 94117 | Whole Foods Market, a formula retail grocery store at 690 Stanyan Street, allowed to operate 24 hours a day | review | food or drink (other food and drink) |
| 2009.0845C | 2535 - 2539 Taraval St, San Francisco, Ca 94116 | Natural Health Center, a massage establishment at 2535A Taraval, modifying hours of operation | review | food or drink (restaurant or cafe) |
| 2010.0033C | 1538 Situs To Be Assigned St, San Francisco, Ca 94117 | Expansion of Haight Street Market grocery store into adjacent space formerly occupied by Massawa Restaurant, 1530-1538 Haight Street | review | food or drink (other food and drink) |
| 2010.0161C | 1722 - 1724 Divisadero St, San Francisco, Ca 94115 | Utoepia Spa, a nail salon adding foot massage chairs (a massage establishment) at 1722-1724 Divisadero St. | review | food or drink (other food and drink) |
| 2010.0676C | 445 Sutter St, San Francisco, Ca 94108 | massage establishment | classifier | premises, but no food-or-drink use |
| 2010.0414C | 4856 Geary Bl, San Francisco, Ca 94118 | Park Presidio 76 gas station at 4850 Geary converted to an automobile gas station with an accessory food mart | review | food or drink (other food and drink) |
| 2010.0311C | 1890 19Th Av, San Francisco, Ca | Expansion of existing nonconforming commercial use (Gas and automobile Service station). | classifier | premises, but no food-or-drink use |
| 2013.0266C | 2224 - 2230 Union St, San Francisco, Ca 94123 | Sur La Table, a formula retail cookware store with an accessory cooking class area, approved on Union Street | review | food or drink (restaurant or cafe) |
| 2013.0282C | 2701 Folsom St, San Francisco, Ca 94110 | 2701-2703 Folsom St: vacant ground-floor spaces approved as a Buddhist meditation center (religious institution) and a small retail use. | review | food or drink (restaurant or cafe) |
| 2013.1328C | 1656 Mission St, San Francisco, Ca 94103 | 1650 Mission St: change of former limited-restaurant space to Public (office) use plus a retained limited-restaurant space of about 1,000 sq ft | review | food or drink (restaurant or cafe) |
| 2013.1464C | 2071 Union St, San Francisco, Ca 94123 | Nike retail apparel store (Formula Retail) replacing Rugby at 2071 Union Street, a retail apparel use. | review | food or drink (other food and drink) |
| 2013.1432C | 2385 California St, San Francisco, Ca 94115 | Rag and Bone, a formula retail apparel store at 2060 Fillmore Street, approved with conditions | review | food or drink (restaurant or cafe) |
| 2011.0477C | 1900 19Th Av, San Francisco, Ca | CVS Pharmacy formula retail pharmacy store at 1900 19th Avenue, change of use from former post office, approved with conditions. | review | food or drink (restaurant or cafe) |
| 2012.0435C | 2320 Lombard St, San Francisco, Ca 94123 | America's Best Value Inn motel at 2322 Lombard converted to tourist hotel, with a 4th floor addition and legalized guest rooms | review | food or drink (other food and drink) |
| 2014.0799C | 3600 - 3628 Geary Bl, San Francisco, Ca 94118 | CVS Pharmacy formula retail store at 3600 Geary Blvd, a pharmacy selling drugs, household items and limited convenience grocery; no alcohol or tobacco. | review | food or drink (other food and drink) |
| 2014-001722CUA |  | Transfer of a Type 21 off-sale alcohol license from New Santa Clara Market to Santa Clara Natural Organic Market, a grocery store | review | food or drink (other food and drink) |
| 2015-008251CUA | 2120 Greenwich St 94123 | Transfer of an ABC Type 47 liquor license within the Union Street NCD at 2120 Greenwich St | review | food or drink (bar) |
| 2015-014877CUA | 3325 Sacramento St 94118 | SkinSpirit, a personal service with accessory medical service (cosmetic injections, laser) replacing a toy store at 3325 Sacramento St, approved with conditions | review | food or drink (other food and drink) |
| 2015-007896CUA | 1699 Van Ness Ave 94109 | First Republic Bank, a Formula Retail financial service replacing a vacant former restaurant space at 1699 Van Ness Ave. | review | food or drink (restaurant or cafe) |
| 2015-015784CUA | 1901 Fillmore St 94115 | 45RPM, a Japanese clothing retailer, Formula Retail use in Upper Fillmore NCD | review | food or drink (other food and drink) |
| 2016-006961CUA | 1977 B Union St 94123 | Globo, a Limited-Restaurant at 1977 B Union St approved as change of use from vacant retail; motion text provided is for a different project (651 Geary Street mixed-use building). | review | food or drink (restaurant or cafe) |
| 2016-003525CUA | 1150 Ocean Ave 94112 | Whole Foods Market at 1150 Ocean Ave, a formula retail grocery store, allowed an on-sale beer and wine (Type 41) license for its bona fide eating area. | review | food or drink (other food and drink) |
| 2012.0262CUA | 500 Geneva Ave 94112 | Geneva Car Barn/Powerhouse at 500 Geneva Ave: adaptive reuse as youth-arts community facility with exhibition space, retail and a restaurant | review | food or drink (restaurant or cafe) |
| 2015-010606CUA | 898 South Van Ness Ave 94110 | Fiesta Laundromat at 898 South Van Ness, a self-service laundromat, allowed to extend hours to 2-6 a.m. and legalize 24-hour operation | review | food or drink (other food and drink) |
| 2015-007338CUA | 3431 Taraval St 94116 | Conditional Use Application for change of use from a Laundromat to a medical office/ health clinic. | classifier | premises, but no food-or-drink use |
| 2015-014461CUA | 1441 Ocean Ave 94112 | North East Medical Services clinic replacing a former limited restaurant at 1441 Ocean Ave, with social service on third floor and vertical addition | review | food or drink (restaurant or cafe) |
| 2016-011198CUA | 1650 Mission St 94103 | Change of use from vacant Limited Restaurant to a Public Office Use (MOEWD Satellite Small Business Services). | classifier | premises, but no food-or-drink use |
| 2015-006857CUA | 4529 18Th St 94114 | Reactivation of a ground-floor LCU commercial tenant space at 4529 18th Street, previously an interior designer office/showroom, under Planning Code 186(g). | review | food or drink (other food and drink) |
| 2016-008356CUA | 3146 Mission St 94110 | EagleRider, a Formula Retail motorcycle sales and rental use at 3146 Mission Street, approved with conditions | review | food or drink (other food and drink) |
| 2017-004187CUA | 2162 Union St 94123 | Verizon Wireless retail store, a formula retail wireless communications shop, at 2162 Union Street | review | food or drink (other food and drink) |
| 2015-005788CUA | 372 07Th Ave 94118 | Tian Yun Clinic at 372 7th Avenue, a medical service with an accessory massage establishment, legalized with conditions | review | food or drink (other food and drink) |
| 2016-000378CUA | 1600 Jackson St 94109 | Formula Retail Application for 365 by Whole Foods to permit an approximately 19,450 square foot grocery store within an existing, vacant, ground-floor… | classifier | not a food-or-drink premises |
| 2018-013462CUA | 3995 Alemany Blvd 94132 | H Mart grocery store | review | food or drink (other food and drink) |
| 2018-014721CUA | 1685 Haight St 94117 | To establish a cannabis retail store. | classifier | not a food-or-drink premises |
| 2018-003264CUA | 2498 Lombard St 94123 | Circle K convenience store in a gas station food mart | review | food or drink (other food and drink) |
| 2018-015127CUA | 4526 03Rd St 94124 | The Project would establish a Cannabis Retail Use measuring 1,616 square feet at the ground level of an existing two-story mixed-use building. | classifier | not a food-or-drink premises |
| 2018-014905CUA | 1711 Haight St 94117 | Iyara Traditional Thai Massage | review | food or drink (other food and drink) |
| 2019-004216CUA | 3989 17Th St 94114 | Conditional Use Authorization for change of use from vacant space to Cannabis retail sales. | classifier | not a food-or-drink premises |
| 2017-004654CUA | 1901 Fillmore St 94115 | Saje Natural Wellness, an aromatherapy supply store | review | food or drink (other food and drink) |
| 2019-001013CUA | 375 32Nd Ave 94121 | To establish a Formula Retail Use for a retail establishment dba Andronico's Community Market. | classifier | not a food-or-drink premises |
| 2019-012580CUA | 61 Cambon Dr 94132 | Conditional Use Authorization for change of use to establish Cannabis Retail within a ground floor retail space. | classifier | not a food-or-drink premises |
| 2014.1573CUA | 2050 Van Ness Av, San Francisco, Ca 94109 | 63-unit apartment building with about 776 sq ft of ground-floor commercial space | review | food or drink (restaurant or cafe) |
| 2019-005500CUA | 2934 Cesar Chavez St 94110 | The Project would establish a Cannabis Retail Use measuring 171 square feet at the ground level of an existing two-story mixed-use building. | classifier | not a food-or-drink premises |
| 2019-004451CUA | 2075 Mission St 94110 | Conditional Use Authorization for change of use from existing cosmetic school to Cannabis Retail Dispensary and Lounge. | classifier | not a food-or-drink premises |
| 2019-014257CUA | 401 Potrero Ave 94110 | Circle K convenience store at a 76 gas station | review | food or drink (other food and drink) |
| 2019-016523CUA | 313 Ivy St 94102 | Fig & Thistle, a cannabis store | review | food or drink (other food and drink) |
| 2019-016911CUA | 855 Brannan St 94103 | Conditional Use Authorization for Formula Retail Personal Services Use (per Planning Code Section 303.1) (d.b.a. StretchLab). | classifier | premises, but no food-or-drink use |
| 2019-015067CUA | 968 Valencia St 94110 | HUF skateboard clothing store | review | food or drink (restaurant or cafe) |
| 2019-015579CUA | 99 Missouri St 94107 | The Project site contains an 8,060 square foot retail space (1250 17th Street), a 5,000 square foot vacant auto-body shop (1240 17th Street), and a 6,940… | classifier | not a food-or-drink premises |
| 2019-004021CUA | 1335 Grant Ave 94133 | Conditional Use Authorization to permit a cannabis retail use. | classifier | not a food-or-drink premises |
| 2019-021940CUA | 545 Francisco St 94133 | Restaurant space converted to a real-estate office | review | food or drink (restaurant or cafe) |
| 2019-020831CUA | 1117 Irving St Com'L 1/F 94122 | Conditional Use Authorization request to include message services in existing foot message establishment dba "U Feet". | classifier | not a food-or-drink premises |
| 2020-001158CUA | 899 Columbus Ave 94133 | Conditional Use Authorization to permit the establishment of a new Cannabis Retail Use measuring roughly 800 square feet at the ground level (fronting… | classifier | not a food-or-drink premises |
| 2019-004110CUA | 2675 Geary Blvd 94115 | To permit a formula retail establishment d.b.a. Whole Foods. | classifier | not a food-or-drink premises |
| 2020-002615CUA | 2000 Van Ness Ave 94109 | CB3P - Conditional Use Authorization request for change of use from existing location currently dba "Diamond Club Tattoo" to new location. | classifier | premises, but no food-or-drink use |
| 2020-001294CUA | 2441 Mission St 94110 | Request for authorization of on-site smoking and/or vaporizing at existing Medical Cannabis Dispensary. | classifier | not a food-or-drink premises |
| 2019-021084CUA | 355 Bay Shore Blvd 94124 | Grocery Outlet grocery store | review | food or drink (other food and drink) |
| 2017-007063CUA | 518 Brannan St 94107 | Conditional Use Authorization to permit the change of use from an Automotive Repair facility to Cannabis Retail | classifier | not a food-or-drink premises |
| 2019-023428CUA | 123 Collingwood St 94114 | LYRIC, a community center for LGBTQQ youth | review | food or drink (nighttime entertainment) |
| 2020-006148CUA | 2843 Geary Blvd 94118 | Conditional Use Authorization request for conversion of the restaurant into a cannabis retail store at ground level. | classifier | premises, but no food-or-drink use |
| 2020-007023CUA | 1649 Divisadero St 94115 | Conditional Use Authorization request for change of use from vacant storage ground floor space to Cannabis Retail Sales (no BPA filed). | classifier | not a food-or-drink premises |
| 2020-007488CUA | 1095 Columbus Ave 94133 | Orange Pen, LLC proposes a Commercial Cannabis Retail Dispensary located at 1095 Columbus Avenue, San Francisco. | classifier | not a food-or-drink premises |
| 2020-010132CUA | 150 07Th St 94103 | West Bay Pilipino Multi-Service Center | review | food or drink (restaurant or cafe) |
| 2020-007461CUA | 1057 Howard St 94103 | Blue Pen, LLC proposes a Commercial Cannabis Retail Dispensary located at 1057 Howard Street, San Francisco. | classifier | not a food-or-drink premises |
| 2018-012222CUA | 1385 Carroll Ave 94124 | Conditional Use Authorization to permit the change of use from an existing warehouse to a new cannabis grow facility in a PDR zone. | classifier | not a food-or-drink premises |
| 2020-007346CUA | 2284 Union St 94123 | Le Bamboo Wellness massage | review | food or drink (other food and drink) |
| 2020-006747CUA | 3109 Fillmore St 94123 | Conditional Use Authorization request for new cannabis retail sales with on-site lounge consumption in existing second-floor. | classifier | not a food-or-drink premises |
| 2019-023090CUA | 1428 Irving St 94122 | Irving Pet Hospital expansion | review | food or drink (other food and drink) |
| 2020-009148CUA | 353 Divisadero St 94117 | Conditional Use Authorization request for change of use from existing 1400 square ft Coffee Shop to Cannabis Retail Use (dba"TBD"). | classifier | not a food-or-drink premises |
| 2020-007152CUA | 5801 Mission St 94112 | Conditional Use Authorization request to permit Cannabis Retail Sales. | classifier | not a food-or-drink premises |
| 2014.1058CUA | 6424 03Rd St, San Francisco, Ca 94124 | The Project includes demolition of the existing one-story building on the project site, and new construction of a four-story, 40-ft tall, mixed-use building… | classifier | not a food-or-drink premises |
| 2021-000603CUA | 5 Leland Ave 94134 | Establish a cannabis retail storefront at 5 Leland Avenue and 2400 Bayshore Blvd. Both retail sweets are part of the same structure/building and have same… | classifier | not a food-or-drink premises |
| 2019-017481CUA | 424 Merchant St 94111 | Conditional Use Authorization request for demolition of existing structures and construction of a 17-story mixed-use hotel and office tower that will… | classifier | not a food-or-drink premises |
| 2020-011603CUA | 2424 Polk St 94109 | The proposal is for a new Cannabis Retail Use (d.b.a. Russian Hill Cannabis Club) within an existing vacant commercial storefront. | classifier | not a food-or-drink premises |
| 2016-013012CUA | 480 Haight St 94117 | Conditional Use Authorization to permit the demolition of the existing single family over retail building and construct an approximately 40-foot tall,… | classifier | not a food-or-drink premises |
| 2021-001579CUA | 2715 Judah St 94122 | Conditional Use Authorization request for Cannabis Retail Sales. | classifier | not a food-or-drink premises |
| 2021-003400CUA | 1285 10Th Ave 94122 | The planned use is storefront retail cannabis for medicinal and recreational purposes. | classifier | not a food-or-drink premises |
| 2021-007109CUA | 1885 Lombard St 94123 | CUA to establish Cannabis Retail use with on-site consumption lounge on ground floor and ancillary office use on second floor. | classifier | not a food-or-drink premises |
| 2021-006392CUA | 2109 Fillmore St 94115 | Conditional Use Authorization request - CB3P. | classifier | premises, but no food-or-drink use |
| 2021-002698CUA | 317 Cortland Ave 94110 | Cannabis store replacing a restaurant | review | food or drink (other food and drink) |
| 2021-000313CUA | 4221 Geary Blvd 94118 | Conditional Use Authorization for change of use from Restaurant use to Cannabis Retail use with no on-site consumption. | classifier | premises, but no food-or-drink use |
| 2021-007350CUA | 4033 Judah St A 94122 | The Project would establish a Cannabis Retail use measuring 1,275 sq. ft. in an existing retail space. | classifier | not a food-or-drink premises |
| 2016-004823CUA-02 | 744 Harrison St 94107 | TO ERECT 8 STORIES, 1 BASEMENT, 4 UNITS RESIDENTIAL, 55 HOTEL ROOMS, RESTAURANT & STORAGE, ROOF DECK BUILDING. ** MAHER: DISTURBANCE OF AT LEAST 50 CU.YD.… | classifier | not a food-or-drink premises |
| 2021-002045CUA |  | Formula Retail Conditional Use Authorization for a change in use to "US Foods" | classifier | not a food-or-drink premises |
| 2021-007323CUA | 2205 Lombard St 94123 | Conditional Use Authorization request for change of use from restaurant and office space to cannabis retail sales. [No building permit filed; hold for… | classifier | not a food-or-drink premises |
| 2021-008697CUA | 4400 17Th St 94114 | Corona Heights Market and Deli, a small grocery store with an accessory deli | review | food or drink (other food and drink) |
| 2022-004128CUA | 2044 Fillmore St 94115 | RedMint massage | review | food or drink (other food and drink) |
| 2021-011365CUA | 2257 Irving St 94122 | Cathay Bank branch | review | food or drink (other food and drink) |
| 2021-009937CUA | 447 Ofarrell St 94102 | A small grocery (a General Grocery use) moving an off-sale liquor licence | review | food or drink (other food and drink) |
| 2022-008002CUA | 939 Post St 94109 | Alchemy Springs health spa | review | food or drink (other food and drink) |
| 2022-007603CUA | 944 Irving St 94122 | This project seeks a conditional use authorization to change existing office to a massage establishment. | classifier | premises, but no food-or-drink use |
| 2022-001838CUA | 800 Taraval St 94116 | Conditional Use Authorization application request for change of use as required per San Francisco Planning Code Section 745 to convert an existing mezzanine… | classifier | not a food-or-drink premises |
| 2022-012037CUA | 2050 Chestnut St 94123 | Mejuri jewelry store | review | food or drink (other food and drink) |
| 2022-008360CUA | 580 Green St 94133 | Luke's Local grocery store | review | food or drink (other food and drink) |
| 2023-001114CUA | 3998 18Th St 94114 | Conditional Use Authorization application pursuant to Planning Code Sections 102,178 (3) (A) (E), 303,303.1, 715 to permit formula retail use dba Muuu Meat… | classifier | not a food-or-drink premises |
| 2022-011750CUA | 372 Ritch St 94107 | The proposal is for a Conditional Use Authorization, pursuant to Planning Code Sections 202.2, 303, and 848 to establish an approximately 2,800 square-foot… | classifier | not a food-or-drink premises |
| 2023-000361CUA | 6000 Geary Blvd 94121 | Conditional Use Authorization (CUA) application related to an existing Chevron gas station proposing the remodel of a 1989 sq. ft. convenience store,… | classifier | not a food-or-drink premises |
| 2023-002340CUA | 999 Valencia St 94110 | Valencia Whole Foods, a small family-owned grocery (a General Grocery use) taking over a beer and wine off-sale licence | review | food or drink (other food and drink) |
| 2022-008162CUA | 3995 Alemany Blvd 94132 | H Mart grocery store expansion | review | food or drink (other food and drink) |
| 2023-002804CUA | 450 Sutter St 94108 | Just For You Bodywork & Massage | review | food or drink (other food and drink) |
| 2015-016326CUA-02 | 0 Unknown 94111 | The project is seeking Conditional Use Authorization pursuant to Planning Code Section 303 to amend the conditions of approval per Planning Commission… | classifier | not a food-or-drink premises |
| 2019-004110CUA-02 | 2675 Geary Blvd 94115 | The project is seeking Conditional Use Authorization pursuant to Planning Code Sections 303 and 303.1 for a Formula Retail use in the NC-3 Zoning District. | classifier | not a food-or-drink premises |
| 2023-011096CUA | 225 San Leandro Way 94127 | The Gregangelo Museum, a folk-art house museum approved as a General Entertainment use for tours, private events and shows (10 am to 9:30 pm at the latest) | classifier | not a food-or-drink premises |
| 2024-007477CUA | 1699 Van Ness Ave 94109 | Chase bank branch replacing First Republic | review | food or drink (restaurant or cafe) |
| 2021-010728CUA | 4994 Mission St 94112 | Basanova cannabis store replacing a restaurant | review | food or drink (other food and drink) |
| 2024-010541CUA | 1542 Haight St 94117 | The project seeks a Conditional Use Authorization pursuant to Planning Code Sections 121.2 and 719 to expand an existing use exceeding 2,500 sq. ft. Gus's… | classifier | not a food-or-drink premises |
| 2024-009645CUA | 1345 Howard St 94103 | AutoZone auto-parts store | review | food or drink (restaurant or cafe) |
| 2023-010016CUA | 3225 Fillmore St 94123 | The project is seeking Conditional Use Authorization pursuant to Planning Code Sections 303, 303.1, and 725 to establish a Formula Retail gym (dba Solidcore). | classifier | not a food-or-drink premises |
| 2024-010499CUA | 1571 Wallace Ave 94124 | The project is seeking a Conditional Use Authorization pursuant to Planning Code Section 210.3 to permit additional use for cannabis cultivation. | classifier | not a food-or-drink premises |
| 2025-003445CUA | 2675 Geary Blvd 94115 | The project proposes a formula retail T&T Supermarket and bakery/cafe. | classifier | not a food-or-drink premises |
| 2025-006395CUA | 1034 Valencia St 94110 | A Conditional Use authorization is sought pursuant to Planning Code Section 303.1 for a Formula Retail fitness studio, dba Club Pilates. | classifier | not a food-or-drink premises |
| 2025-003031CUA | 312 Columbus Ave 94133 | The Project proposes to expand the existing Hotel use (d.b.a. Europa Hotel) on the ground floor of the existing commercial building with a use size over… | classifier | not a food-or-drink premises |
| 2025-007879CUA | 690 Van Ness Ave 94102 | Conditional Use Authorization pursuant to Planning Code Section 209.3 "Institutional Use" requirement to permit Farming Hope a 501c3 nonprofit to operate… | classifier | not a food-or-drink premises |
| 2025-005235CUA | 1270 Mission St 94103 | Conditional Use Authorization request for 16220 sqf of parking use (33 parking spaces) | classifier | not a food-or-drink premises |
| 2025-010376CUA | 4620 Mission St 94112 | Total Wireless phone store | review | food or drink (other food and drink) |
| 2025-011827CUA | 1868 Lombard Street | Conditional Use Authorization pursuant to Planning Code Section 303, 303.1, and 712 to establish Formula Retail Use. | classifier | not a food-or-drink premises |
| 2025-010921CUA | 5300 03Rd St 94124 | A Conditional Use authorization is sought pursuant to Planning Code Sections 303, 303.1, 210.3 (PDR-1-B Zoning), 210.4 (M-1 Zoning), and 786 (Third Street… | classifier | not a food-or-drink premises |

## Reviewed list

`reviewed-labels.json` (the 2019+ motions reviewed 2026-11-12, the 2010-2018 motions 2026-11-13; the rules
and how each review was done are in `REVIEWED.md`) overrides the classifier
after it runs (`apply_review` in `scripts/validation/build_conditions_index.py`). An "include" of a motion the
classifier left out brings it back with the business type the decision gives; an "include" of a motion it kept
sets that business type when it differs; an "exclude" of a motion it kept removes it. A decision that matches
what the classifier already did changes nothing, and a record that is not among the motions found is reported
by the build. The data file records every change (`review` in `data/conditions.json`: `added_back`,
`removed`, `business_set`, and every decision with how it was applied), and `coverage.html` shows the list.

93 decisions: 4 motions added back, 56 removed, 29 kept with their business type
corrected, 4 already as decided.

| Record | Address | What it is | Decision | Reason | Applied |
|---|---|---|---|---|---|
| 2014.1573CUA | 2050 Van Ness Av, San Francisco, Ca 94109 | 63-unit apartment building with about 776 sq ft of ground-floor commercial space | exclude | A whole-building housing project; the small commercial space is incidental and the conditions are about the building. | removed |
| 2015-009955CUA | 1525 Pine St 94109 | Grubstake, a restaurant with beer and wine, rebuilt on the ground floor of a new eight-story housing building and allowed to open 24 hours | include as restaurant or cafe | Part of the approval is for the restaurant itself (24-hour opening hours), and its conditions include the bona fide eating place, eating and drinking and odor conditions. | added back |
| 2017-004654CUA | 1901 Fillmore St 94115 | Saje Natural Wellness, an aromatherapy supply store | exclude | A retail store with no food or drink. | removed |
| 2018-003264CUA | 2498 Lombard St 94123 | Circle K convenience store in a gas station food mart | exclude | A convenience store at a gas station; the motion says it does not intend to sell beer or wine. | removed |
| 2018-010482CUA | 3501 California St 94118 | SusieCakes Bakery, a chain bakery approved as a limited restaurant | include as restaurant or cafe | The motion approves a limited restaurant (a bakery selling food), which counts as restaurant or cafe. | added back |
| 2018-013462CUA | 3995 Alemany Blvd 94132 | H Mart grocery store | exclude | A grocery store, which stays out even with restaurants inside. | removed |
| 2018-014905CUA | 1711 Haight St 94117 | Iyara Traditional Thai Massage | exclude | A massage establishment, not food or drink. | removed |
| 2019-014257CUA | 401 Potrero Ave 94110 | Circle K convenience store at a 76 gas station | exclude | A gas-station convenience store; the motion is about formula retail and does not involve alcohol or food service. | removed |
| 2019-015067CUA | 968 Valencia St 94110 | HUF skateboard clothing store | exclude | A clothing store replacing a coffee shop, so the approved use is not food or drink. | removed |
| 2019-016523CUA | 313 Ivy St 94102 | Fig & Thistle, a cannabis store | exclude | A cannabis store, not food or drink. | removed |
| 2019-017055CUA | 1881 Post St 94115 | AMC Kabuki, a multiplex movie theatre | include as nighttime entertainment | Already on the page; this only corrects its business type from Restaurant or cafe, since it is a movie theatre and its conditions cover entertainment and hours. | business type set |
| 2019-021084CUA | 355 Bay Shore Blvd 94124 | Grocery Outlet grocery store | exclude | A grocery store, which stays out. | removed |
| 2019-021940CUA | 545 Francisco St 94133 | Restaurant space converted to a real-estate office | exclude | The motion converts a restaurant away to an office use. | removed |
| 2019-023090CUA | 1428 Irving St 94122 | Irving Pet Hospital expansion | exclude | A pet hospital, not food or drink. | removed |
| 2019-023428CUA | 123 Collingwood St 94114 | LYRIC, a community center for LGBTQQ youth | exclude | A non-profit community facility; it even removes meal programs, and nothing in it is food, drink or entertainment. | removed |
| 2020-007346CUA | 2284 Union St 94123 | Le Bamboo Wellness massage | exclude | A massage establishment, not food or drink. | removed |
| 2020-010132CUA | 150 07Th St 94103 | West Bay Pilipino Multi-Service Center | exclude | The motion approves a social service and assembly use; the existing restaurant next door is left out of the project. | removed |
| 2021-002698CUA | 317 Cortland Ave 94110 | Cannabis store replacing a restaurant | exclude | A cannabis store that converts a restaurant away from food. | removed |
| 2021-008697CUA | 4400 17Th St 94114 | Corona Heights Market and Deli, a small grocery store with an accessory deli | exclude | A grocery store with a deli counter as an accessory use; grocery stores stay out. | removed |
| 2021-008851CUA | 728 Geary St 94109 | Domino's Pizza, a chain take-out pizza restaurant | include as restaurant or cafe | The motion approves a formula retail restaurant selling take-out food. | added back |
| 2021-009937CUA | 447 Ofarrell St 94102 | A small grocery (a General Grocery use) moving an off-sale liquor licence | exclude | Planning approved it as a General Grocery use, and grocery stores stay out. | removed |
| 2021-010728CUA | 4994 Mission St 94112 | Basanova cannabis store replacing a restaurant | exclude | A cannabis store (sales only) that converts a restaurant away from food. | removed |
| 2021-011365CUA | 2257 Irving St 94122 | Cathay Bank branch | exclude | A bank, not food or drink. | removed |
| 2022-001407CUA | 2700 45Th Ave 94116 | United Irish Cultural Center, a new community building with a restaurant, bar, ballroom and nighttime entertainment | include as nighttime entertainment | The motion approves restaurant, bar and nighttime entertainment uses, and its conditions include the eating and drinking, entertainment and bar-notice conditions, like the Nob Hill Masonic Center kept on the page. | added back |
| 2022-004128CUA | 2044 Fillmore St 94115 | RedMint massage | exclude | A massage establishment, not food or drink. | removed |
| 2022-008002CUA | 939 Post St 94109 | Alchemy Springs health spa | exclude | A health spa with an outdoor area; no food or alcohol service. | removed |
| 2022-008162CUA | 3995 Alemany Blvd 94132 | H Mart grocery store expansion | exclude | A grocery store, which stays out. | removed |
| 2022-008360CUA | 580 Green St 94133 | Luke's Local grocery store | exclude | A grocery store (with prepared foods and beer and wine), which stays out. | removed |
| 2022-012037CUA | 2050 Chestnut St 94123 | Mejuri jewelry store | exclude | A jewelry store, not food or drink. | removed |
| 2023-002340CUA | 999 Valencia St 94110 | Valencia Whole Foods, a small family-owned grocery (a General Grocery use) taking over a beer and wine off-sale licence | exclude | Planning approved it as a General Grocery use, and grocery stores stay out. | removed |
| 2023-002804CUA | 450 Sutter St 94108 | Just For You Bodywork & Massage | exclude | A massage establishment, not food or drink. | removed |
| 2023-011096CUA | 225 San Leandro Way 94127 | The Gregangelo Museum, a folk-art house museum approved as a General Entertainment use for tours, private events and shows (10 am to 9:30 pm at the latest) | exclude | No food or drink is served and it is not nighttime entertainment; the request was for food and drink. The classifier left it out too; this row records the call. | no change: already as decided |
| 2024-007477CUA | 1699 Van Ness Ave 94109 | Chase bank branch replacing First Republic | exclude | A bank, not food or drink. | removed |
| 2024-009645CUA | 1345 Howard St 94103 | AutoZone auto-parts store | exclude | An auto-parts store, not food or drink. | removed |
| 2024-011113CUA | 401 Columbus Ave 94133 | Steps of Rome, an existing restaurant taking a full liquor license | include as restaurant or cafe | Already on the page; this only corrects its business type from Other food and drink, since the motion moves a Type 47 eating-place license to an existing restaurant. | business type set |
| 2025-007559CUA | 1416 Haight St 94117 | Amal's Market, a grocery and deli of about 2,800 sq ft moving up from a beer and wine license to a full off-sale liquor license | include as other food and drink | The motion is only about an off-sale liquor license at a small market (Planning treats it as a Liquor Store use and its conditions are the liquor store ones), so it counts as off-sale alcohol. Already on the page; this row records the grocery rule. | no change: already as decided |
| 2025-010376CUA | 4620 Mission St 94112 | Total Wireless phone store | exclude | A phone store, not food or drink. | removed |
| 2026-000475CUA | 284 Noe St 94114 | Love Potion Library, a romance bookstore and tea room with wine service | include as bar | Already on the page; this only corrects its business type from Other food and drink, since the motion establishes a Bar use. | business type set |
| 2009.1103C | 1878 Haight St, San Francisco, Ca 94117 | Whole Foods Market, a formula retail grocery store at 690 Stanyan Street, allowed to operate 24 hours a day | exclude | The approved use is a General Grocery store (Whole Foods Market), which is excluded under the grocery rule even though the motion also addresses 24-hour operation. (Motion: "to place a grocery store in a building formerly occupied by a grocery store") | removed |
| 2009.1010C | 1701 Octavia St, San Francisco, Ca 94109 | Baker and Banker restaurant at 1701 Octavia: adds self-service specialty food (baked goods, beverages) sales and extends hours. | include as restaurant or cafe | The motion approves a self-service specialty food use and changes to the existing full-service restaurant's hours, both food service uses under the rules. (Motion: "The proposed new use is for the incidental sales of baked goods and beverages, to the general public, from the existing restaurant kitchen") | business type set |
| 2009.0845C | 2535 - 2539 Taraval St, San Francisco, Ca 94116 | Natural Health Center, a massage establishment at 2535A Taraval, modifying hours of operation | exclude | The approved use is a massage establishment, which is excluded from the page, not a food, drink or entertainment use. (Motion: "to modify the hours of operation for the existing massage establishment (dba Natural Health Center)") | removed |
| 2009.1079C | 401 - 451 Columbus Av, San Francisco, Ca 94133 | Specialty Food, Self Service use at 658 Vallejo Street: take-out deli, specialty foods and catering within an existing storefront, approved with conditions. | include as restaurant or cafe | Approved use is a Specialty Food, Self Service take-out deli, which is a self-service specialty food restaurant-type use selling prepared food to customers. (Motion: "establish a business offering specialty foods, a take‐out deli, and catering services") | business type set |
| 2010.0036C | 1750 - 1758 Polk St, San Francisco, Ca 94109 | La Parrilla Grill at 1760 Polk St, a full-service restaurant with a full bar, amended to extend hours from 10 pm to 2 am | include as restaurant or cafe | The motion approves an extension of hours for an existing full-service restaurant with a bar use, which is a change to an existing food and drink use. (Motion: "to allow expansion of hours of operation limited under Planning Commission Motion 17551 for an existing full-service restaurant and bar") | business type set |
| 2010.0033C | 1538 Situs To Be Assigned St, San Francisco, Ca 94117 | Expansion of Haight Street Market grocery store into adjacent space formerly occupied by Massawa Restaurant, 1530-1538 Haight Street | exclude | The approved use is a grocery store (Haight Street Market) expansion, and the restaurant space being absorbed is not approved as a food or drink use, so the grocery rule excludes it. (Motion: "propose to expand the existing grocery store (Haight Street Market) at 1530 Haight Street into the existing, adjacent commercial space") | removed |
| 2010.0161C | 1722 - 1724 Divisadero St, San Francisco, Ca 94115 | Utoepia Spa, a nail salon adding foot massage chairs (a massage establishment) at 1722-1724 Divisadero St. | exclude | The approved use is a massage establishment added to a nail salon, which is a personal service use outside the food, drink and entertainment categories. (Motion: "ADOPTING FINDINGS RELATING TO THE APPROVAL OF A CONDITIONAL USE AUTHORIZATION PURSUANT TO SECTIONS 303, 712.54, AND 790.60 OF THE PLANNING CODE TO ALLOW A MASSAGE ESTABLISHMENT") | removed |
| 2010.0414C | 4856 Geary Bl, San Francisco, Ca 94118 | Park Presidio 76 gas station at 4850 Geary converted to an automobile gas station with an accessory food mart | exclude | The approved use is an automobile gas station; the accessory food mart is described as a retail grocery store use, which is excluded under the grocery rule and is not a food or drink service approval. (Motion: "The existing food mart establishment is an accessory retail grocery store use affiliated with the existing '76' service station") | removed |
| 2010.0710C | 777 Valencia St, San Francisco, Ca 94110 | Preservation Hall West: two full-service restaurant and bar establishments plus a jazz club (Other Entertainment) at 777 Valencia Street, with outdoor activity area | include as nighttime entertainment | The motion approves restaurant, bar and Other Entertainment (jazz club) uses together, and when restaurant, bar and entertainment uses are approved together the entertainment category applies. (Motion: "convert an existing vacant two-story building to two new Full-Service Restaurant & Bar Establishments on the ground floor, an Other Entertainment Establishment (Jazz Club)") | business type set |
| 2010.1162C | 739 - 741 Valencia St, San Francisco, Ca 94110 | Tacolicious, a full-service restaurant and bar with outdoor seating at 741 Valencia Street, approved with conditions | include as restaurant or cafe | The motion approves a new full-service restaurant with a bar (type 47) and outdoor activity area, so it is a restaurant motion; the main service is food, so it is classed as Restaurant or cafe. (Motion: "to convert the vacant ground floor commercial unit of an existing two-story commercial and residential building to a new Full-Service Restaurant & Bar Establishment") | business type set |
| 2009.0342C | 2516 - 2524 Mission St, San Francisco, Ca 94110 | Medjool, a full-service restaurant, bar and other entertainment venue, legalizing a rooftop outdoor activity area | include as nighttime entertainment | The motion changes an existing use approved together as restaurant, bar and Other Entertainment, so the rules assign the entertainment type. (Motion: "to allow an existing Full‐Service Restaurant, Bar And Other Entertainment (d.b.a. Medjool) to legalize an Outdoor Activity Area") | business type set |
| 2011.0565C | 2011 - 2015 Fillmore St, San Francisco, Ca 94115 | Bun Mee, a large fast-food restaurant at 2015 Fillmore, allowed to add beer and wine service via amended conditional use | include as restaurant or cafe | The motion approves changes to an existing Large Fast-Food Restaurant use, removing the bar on alcohol sales for beer and wine, which is a food service use changed under the rules. (Motion: "the current owner proposes to serve beer and wine and has applied for a Type 41 ABC license") | business type set |
| 2011.0701C | 545 Irving St, San Francisco, Ca 94122 | InnerFog wine bar at 545 Irving St, amended to extend hours of operation to 10 a.m.-2 a.m. seven days a week | include as bar | The motion approves changes to an existing wine bar use (extended hours), and a wine bar is a Bar use, so it is included as Bar. (Motion: "to modify the conditions of a prior Conditional Use authorization under Case No. 2009.1048C (Motion No. 18014) to extend the hours of operation of an existing wine bar") | business type set |
| 2011.1344C | 101 - 115 06Th St, San Francisco, Ca | Monarch, a bar/entertainment venue at 101 6th Street, approved to intensify its entertainment use into the basement and extend hours to 4am | include as nighttime entertainment | The motion approves intensifying an existing entertainment use and extending bar and entertainment hours, so it is a change to a nighttime entertainment venue. (Motion: "intensify a non‐conforming entertainment use by expanding it to the basement level of the approximately 3,111 square‐foot bar") | business type set |
| 2012.0525C | 1150 Ocean Av, San Francisco, Ca 94112 | Yogurtland, a formula retail self-serve frozen yogurt limited restaurant at 1250 Ocean Avenue, approved with conditions | include as restaurant or cafe | The motion approves a limited restaurant (self-serve frozen yogurt), a food use, so it belongs on the page as a restaurant or cafe. (Motion: "to establish a 1,615 square -foot, formula retail, limited-restaurant (d.b.a. "Yogurtland") witin the ground floor commercial space") | business type set |
| 2012.0953C | 401 Keith St, San Francisco, Ca 94124 | Speakeasy Ales and Lagers brewery expansion into adjacent warehouse storage space at 1195 Evans Avenue; storage only, no tasting room or on-site drinking described. | include as other food and drink | Independent audit (2026-11-13) of the review: I couldn't refute the dispute. Motion 18701 grants a Conditional Use under Sec. 226(h) for a brewery use. Finding 6A says "The Project Sponsor is proposing a significant expansion to the existing brewery use". The use Planning approved is therefore the brewery (Speakeasy Ales and Lagers), expanded by 4,600 sq ft. The new space is only storage, but it stores the beer brewed on site, so it is part of the brewery use. … | no change: already as decided |
| 2012.0145C | 1721 - 1737 Haight St, San Francisco, Ca 94117 | Red Vic Movie House converted to an Alembic Bar restaurant/bar expansion, an Other Entertainment event space and retail kiosks | include as nighttime entertainment | The motion approves a restaurant/bar expansion together with an Other Entertainment event space, and when restaurant, bar and entertainment uses are approved together the type is Nighttime entertainment. (Motion: "CREAT ION AN EVENT SPACE ALLOW ING “OTHER ENTERTAINMENT” IN THE FORMER MOVIE HOUSE AREA") | business type set |
| 2012.0370C | 1127 Market St, San Francisco, Ca 94103 | American Conservatory Theater second stage: conversion of a former movie theater into a 299-seat live theater with a ground-floor restaurant/cafe fronting Market Street | include as nighttime entertainment | The motion approves conversion of the building into a live entertainment theater, which is an entertainment use, and the ground-floor restaurant/cafe is also approved, so the entertainment use governs the business type. (Motion: "to allow conversion of vacant commercial space previously occupied by a movie theater (d.b.a. Strand Theater) into a live entertainment theater (d.b.a. ACT Second Stage)") | business type set |
| 2011.1339C | 1301 - 1327 Polk St, San Francisco, Ca 94109 | The Pour House, a wine store with tasting room and bar at 1327 Polk St; Conditional Use to clarify continuation of the liquor store and bar, with hours extended to 2 a.m. in conditions. | include as bar | The motion approves a Bar use (wine tasting room and bar, clarified as liquor store and bar), and drinking is a main service, so it is a bar motion. (Motion: "to clarify the continuation of the existing wine store, tasting room and bar (liquor store and bar) (d.b.a. The Pour House)") | business type set |
| 2012.1031C | 1595 Sloat Bl, San Francisco, Ca 94132 | Sushi Avenue, a formula retail limited restaurant inside the Lucky grocery store at Lakeshore Plaza, legalized | include as restaurant or cafe | The motion approves a formula retail limited restaurant (Sushi Avenue), a food use, not the grocery store itself, so it is included as a restaurant. (Motion: "to allow the legalization of a formula retail limited restaurant , ( d.b.a. Sushi Avenue ) inside the existing Luckys grocery store") | business type set |
| 2013.0336C | 1096 South Van Ness Av, San Francisco, Ca | Urban Putt, a restaurant with indoor miniature golf course, with extended hours, at 1096 South Van Ness Avenue | include as nighttime entertainment | The motion approves a restaurant together with a miniature golf entertainment use and extended hours, so it is an entertainment approval, and the restaurant and entertainment uses together map to Nighttime entertainment. (Motion: "to allow an approximately 9,500 gross square foot restaurant and miniature golf establishment (d.b.a. Urban Putt) with extended hours") | business type set |
| 2013.0266C | 2224 - 2230 Union St, San Francisco, Ca 94123 | Sur La Table, a formula retail cookware store with an accessory cooking class area, approved on Union Street | exclude | The approved use is a formula retail cookware store with a cooking class, which is retail rather than a restaurant, cafe, bar or entertainment use. (Motion: "to allow a new Formula Retail establishment (d.b.a. Sur La Table ) within the Union Street NCD") | removed |
| 2013.0282C | 2701 Folsom St, San Francisco, Ca 94110 | 2701-2703 Folsom St: vacant ground-floor spaces approved as a Buddhist meditation center (religious institution) and a small retail use. | exclude | The motion itself approves a religious institution and a retail use, not a restaurant, bar or entertainment use; Planning's restaurant description does not match the motion text. (Motion: "to establish an approximately 2,400 square-foot religious institution and an approximately 400 square -foot retail use") | removed |
| 2013.1464C | 2071 Union St, San Francisco, Ca 94123 | Nike retail apparel store (Formula Retail) replacing Rugby at 2071 Union Street, a retail apparel use. | exclude | The approved use is a Formula Retail apparel store (Nike), which is retail rather than a restaurant, bar, or entertainment use. (Motion: "to convert a vacant ground floor commercial space with approximately 3,500 gross square feet of floor area (previously occupied by "Rugby"") | removed |
| 2013.1137C | 4054 24Th St, San Francisco, Ca 94114 | Valley Tavern, an existing bar, seeks legalization of its rear patio as an outdoor activity area with 24 patrons seating. | include as bar | The motion approves an expansion of an existing bar use (Valley Tavern, type 48 ABC license) through an outdoor activity area, so it is a change to a drink use. (Motion: "to allow for the expansion of a bar use (d.b.a. Valley Tavern) through the legalization of an outdoor activity area located within the rear yard") | business type set |
| 2013.1432C | 2385 California St, San Francisco, Ca 94115 | Rag and Bone, a formula retail apparel store at 2060 Fillmore Street, approved with conditions | exclude | The approved use is an apparel store (formula retail), not a restaurant, bar, or entertainment use. (Motion: "The subject use will be an apparel store (d.b.a. Rag and Bone).") | removed |
| 2011.0477C | 1900 19Th Av, San Francisco, Ca | CVS Pharmacy formula retail pharmacy store at 1900 19th Avenue, change of use from former post office, approved with conditions. | exclude | The approved use is a pharmacy store (retail), not a restaurant, bar, or entertainment use; the motion's conditions cover alcohol and tobacco sales only as incidental retail, not as a food or drink use. (Motion: "establish a 17,920 gross square foot formula retail pharmacy store (d.b.a. CVS Pharmacy)") | removed |
| 2012.0435C | 2320 Lombard St, San Francisco, Ca 94123 | America's Best Value Inn motel at 2322 Lombard converted to tourist hotel, with a 4th floor addition and legalized guest rooms | exclude | The approved use is a tourist hotel and building project, not a food, drink or entertainment use; the existing small cafe is not what Planning approved. (Motion: "to allow the conversion of use from a motel to a tourist hotel (d.b.a. America's Best Value Inn and Suites Golden Gate)") | removed |
| 2013.0255C | 620 Jones St, San Francisco, Ca 94102 | Jones restaurant at 620 Jones St, modifying conditions to extend outdoor activity area hours to 2:00 a.m. Fridays/Saturdays and permit outdoor live entertainment until 7 p.m. daily | include as restaurant or cafe | The motion modifies conditions for an existing restaurant (d.b.a. Jones) and its outdoor activity area hours and live entertainment, so it concerns a food service use and its operating conditions. (Motion: "to extend the permitted hours of operation for an existing outdoor activity area until 2:00 a.m. on Fridays, Saturdays, New Year's Eve, and Gay Pride Sunday") | business type set |
| 2014.0799C | 3600 - 3628 Geary Bl, San Francisco, Ca 94118 | CVS Pharmacy formula retail store at 3600 Geary Blvd, a pharmacy selling drugs, household items and limited convenience grocery; no alcohol or tobacco. | exclude | The approved use is a pharmacy/retail store, not a restaurant, bar, entertainment venue or liquor store; limited convenience grocery items do not make it a food or drink use. (Motion: "will sell a range of household and personal items such as prescription and over- the-counter drugs, health and beauty products") | removed |
| 2014-001722CUA |  | Transfer of a Type 21 off-sale alcohol license from New Santa Clara Market to Santa Clara Natural Organic Market, a grocery store | exclude | The approved use is a grocery store receiving an alcohol license, and under the grocery rule a grocery is out even for an alcohol licence; no Liquor Store or food service use is approved. (Motion: "to allow the transfer of an Off -Sale General alcoholic beverage license between two grocery stores") | removed |
| 2014.1426C | 4022 - 4026 24Th St, San Francisco, Ca 94114 | Tom Rai, a restaurant replacing Bliss Bar with a Type 47 license and existing place of entertainment, enlarged to 2,695 sq ft at 4022-4026 24th St | include as restaurant or cafe | The motion approves a new restaurant (Tom Rai, Type 47 ABC license) and maintains a place of entertainment, so it is a food and entertainment use; the restaurant is the main approved use, with the entertainment use also approved. (Motion: "to allow a 1,906 square foot, ground floor commercial space, formerly occupied by a bar use (d.b.a. Bliss Bar) to be enlarged beyond the use size limitation for the District to approximately 2,695 square feet and converted into a restaurant (d.b.a. Tom Rai)") | business type set |
| 2015-014877CUA | 3325 Sacramento St 94118 | SkinSpirit, a personal service with accessory medical service (cosmetic injections, laser) replacing a toy store at 3325 Sacramento St, approved with conditions | exclude | The approved use is a Personal Service with accessory Medical Service, not a food, drink or entertainment use, so it falls under the excluded beauty and clinic category. (Motion: "a change of use from a Retail toy store (d.b.a. The Ark) to a Retail and Personal Service use with accessory Medical Service (d.b.a. SkinSpirit)") | removed |
| 2015-014178CUA | 653 Union St 94133 | Ferry Plaza Seafood, a bona fide restaurant, allowed to upgrade its liquor license from Type 41 beer and wine to Type 47 general | include as restaurant or cafe | The approved use is an upgraded liquor license for an existing bona fide eating place restaurant, so food service remains the main use under the restaurant rules. (Motion: "to allow an upgrade from ABC License Type 41 (Restaurant, Beer and Wine) to Type 47 (Restaurant, General) at an existing Restaurant (d.b.a. Ferry Plaza Seafood) operating as a Bona Fide Eating Place") | business type set |
| 2015-007896CUA | 1699 Van Ness Ave 94109 | First Republic Bank, a Formula Retail financial service replacing a vacant former restaurant space at 1699 Van Ness Ave. | exclude | The approved use is a financial service (bank), not a food, drink or entertainment use, so it falls outside the page's scope. (Motion: "Conditional Use Authorization request to change of use from vacant retail (Restaurant) to a new Formula Retail Financial Service (First Republic Bank).") | removed |
| 2015-015784CUA | 1901 Fillmore St 94115 | 45RPM, a Japanese clothing retailer, Formula Retail use in Upper Fillmore NCD | exclude | The approved use is a clothing retailer, which is other retail, not a food, drink or entertainment use. (Motion: "to establish the establishment of a Formula Retail use (a clothing retailer dba "45RPM") in the existing tenant space") | removed |
| 2015-010606CUA | 898 South Van Ness Ave 94110 | Fiesta Laundromat at 898 South Van Ness, a self-service laundromat, allowed to extend hours to 2-6 a.m. and legalize 24-hour operation | exclude | The approved use is a self-service laundromat, which is a retail service use rather than a restaurant, bar, entertainment venue, or liquor store. (Motion: "The Project Sponsor proposes to extend the permitted hours of operation to operate between the hours of 2:00 a.m. and 6:00 a.m. for an existing self-service Laundromat") | removed |
| 2015-014461CUA | 1441 Ocean Ave 94112 | North East Medical Services clinic replacing a former limited restaurant at 1441 Ocean Ave, with social service on third floor and vertical addition | exclude | The approved use is a medical service and social service institution, not a food, drink or entertainment use; the prior restaurant is being converted into another use. (Motion: "proposes to open a new medical service use and social service establishment d.b.a. North East Medical Services") | removed |
| 2016-009074CUA | 701 Haight St 94117 | Black Sands Brewery, a brew pub restaurant at 701 Haight St, allowed to extend hours to midnight Sun-Thu and 2 a.m. Fri-Sat | include as restaurant or cafe | The approved use is an existing brew pub restaurant with a restaurant liquor licence, and the motion extends its hours, which is a change to an existing food use. (Motion: "to allow a brew pub/restaurant (d.b.a. Black Sands Brewery) to extend hours of operation from 11 p.m. to midnight (12 a.m.)") | business type set |
| 2015-006857CUA | 4529 18Th St 94114 | Reactivation of a ground-floor LCU commercial tenant space at 4529 18th Street, previously an interior designer office/showroom, under Planning Code 186(g). | exclude | The approved use is an architect/interior designer office and showroom, which is an office use rather than a restaurant, bar, or entertainment use. (Motion: "The Project Sponsor proposes continuing the same type of use (architect/designer office/showroom) at this commercial location.") | removed |
| 2016-013754CUA | 323 Octavia St 94102 | Local Method, a restaurant with a micro brewery bar at 323 Octavia St, approved to exceed use size limit | include as restaurant or cafe | The motion approves a new restaurant use (Local Method) with a micro brewery bar component, and its conditions govern running that food and drink use including hours and odor control. (Motion: "to establish a new Restaurant Use (d.b.a. "Local Method") within a vacant, ground-floor tenant space") | business type set |
| 2016-008356CUA | 3146 Mission St 94110 | EagleRider, a Formula Retail motorcycle sales and rental use at 3146 Mission Street, approved with conditions | exclude | The approved use is motorcycle sales and rental (Automobile Sale or Rental, non-automotive vehicle rental), which is not a food, drink or entertainment use. (Motion: "to establish a Formula Retail motorcycle sales and rentals use (dba EagleRider) within an 19,640 square foot ground-floor") | removed |
| 2017-004187CUA | 2162 Union St 94123 | Verizon Wireless retail store, a formula retail wireless communications shop, at 2162 Union Street | exclude | The approved use is a wireless communications retail store, which is ordinary retail rather than a restaurant, bar, entertainment or liquor use, so it falls outside the page. (Motion: "Formula Retail Use (d.b.a. Verizon, a wireless communications retail store)") | removed |
| 2017-007658CUA | 4522 03Rd St 94124 | Sav Mor Market, an existing liquor establishment/grocery store relocated to 4522 3rd Street in the Third Street Alcohol Restricted Use District | include as other food and drink | Independent audit (2026-11-13) of the review: I couldn't refute the dispute. The grocery rule says the use Planning approved decides. Rule 1 only excludes a motion that approves a General or Specialty Grocery use, and the reviewers' reason depends on a "General Grocery use" label that does not appear anywhere in Motion 20076 (M-20076.pdf, read in full). The only Code finding that triggers the Conditional Use is §249.62(a)(3)(B)(iv): relocating an existing … | no change: already as decided |
| 2015-005788CUA | 372 07Th Ave 94118 | Tian Yun Clinic at 372 7th Avenue, a medical service with an accessory massage establishment, legalized with conditions | exclude | The approved use is a Medical Service with accessory massage, which is a massage/health use rather than a restaurant, bar, or entertainment use, so it falls outside the page's scope. (Motion: "Conditional Use Authorization to establish an accessory Massage Establishment with the existing acupuncture clinic.") | removed |
| 2018-008372CUA | 1123 Folsom St 94103 | Denied Conditional Use to legalize an outdoor activity area for two bar uses (Trademark & Copyright) at 1123-1127 Folsom Street | include as bar | The motion is a denial of an outdoor activity area serving two existing bar uses, and denied food or drink uses count as in scope, with the approved use being a Bar. (Motion: "to legalize and establish an outdoor activity area measuring approximately 728 square feet in size in the rear of two existing bar uses") | business type set |
| 2010.1070C_3 | 580 - 584 Valencia St, San Francisco, Ca 94110 | The Slanted Door (Dosa), a full-service restaurant at 580-584 Valencia, approved to add bar service with a Type 47 ABC license | include as bar | Independent audit (2026-11-13) of the review: I could not refute the dispute. Motion 18402 (2010.1070C) grants a Conditional Use under Planning Code Sections 303, 726.41 and 790.22. Section 726.41 is the Bar line in the Valencia NCT table, and 790.22 defines a Bar. The motion's title says the purpose is "to authorize the addition of bar service (Type 47 ABC license)" to an existing full-service restaurant. The project description adds that under Section 790.92 … | business type set |
| 2013.1328C | 1656 Mission St, San Francisco, Ca 94103 | 1650 Mission St: change of former limited-restaurant space to Public (office) use plus a retained limited-restaurant space of about 1,000 sq ft | exclude | Independent audit (2026-11-13) of the review: I could not refute the dispute. The motion's own wording settles it. The title and the Exhibit A authorization approve only "a conditional use to allow a Public (office) use located at 1650 Mission Street" under Sec. 731.83. The finding states the request is "a change of use from a limited-restaurant to Public use". The 1,000 sq ft of limited-restaurant space is called "retained" and "existing". It is not something … | removed |
| 2015-005989CUA | 493 Broadway 94133 | Prohibition, a 3,008 sq ft restaurant and lounge with up to 200 sq ft of other entertainment (DJ, live performances) replacing a bar and adult entertainment use at 493 Broadway. | include as restaurant or cafe | Independent audit (2026-11-13) of the review: I couldn't refute the dispute. Prohibition belongs on the page as Restaurant or cafe, not Nighttime entertainment. 1. The Authorization section of Motion 19616 (Exhibit A) reads "conditional use to allow a restaurant exceeding 2,999 square feet (d.b.a. Prohibition)" under Sections 303, 714.21 and 714.44 only. The title and preamble say the same. 2. The motion did not authorize the entertainment. Finding 6.C says … | business type set |
| 2016-003525CUA | 1150 Ocean Ave 94112 | Whole Foods Market at 1150 Ocean Ave, a formula retail grocery store, allowed an on-sale beer and wine (Type 41) license for its bona fide eating area. | exclude | Independent audit (2026-11-13) of the review: I could not refute the dispute. The motion (M-19713) approves only a General Grocery use, and grocery rule 1 in REVIEWED.md keeps that out. Its authorization paragraph says the conditional use is "to allow an on-sale liquor license (Type 41) at an existing formula retail grocery store (d.b.a. Whole Foods)". The CUA was needed only because the 2006 approval (Motion 17885) carried a condition banning on-sale licences. … | removed |
| 2012.0262CUA | 500 Geneva Ave 94112 | Geneva Car Barn/Powerhouse at 500 Geneva Ave: adaptive reuse as youth-arts community facility with exhibition space, retail and a restaurant | exclude | Independent audit (2026-11-13) of the review: I could not refute the dispute. Motion M-19559 (pdf/4474047901c588ec2b511129.pdf) grants a Conditional Use under Planning Code sections 211.2 and 303 for a community facility in the P (Public Use) District. Its project description says the authorization "would approve phase 1 scope of work at the Powerhouse", which is a 300-person, roughly 2,058 sf exhibition space. The best case for keeping it is Exhibit A: its … | removed |
| 2016-006961CUA | 1977 B Union St 94123 | Globo, a Limited-Restaurant at 1977 B Union St approved as change of use from vacant retail; motion text provided is for a different project (651 Geary Street mixed-use building). | exclude | Independent audit (2026-11-13) of the review: I could not refute the dispute. The record itself is Globo, a change from vacant retail to a Limited Restaurant at 1977B Union St. With its own motion it would be in as Restaurant or cafe. But the motion cached for this record (sidecar 20261113T080127973819Z-2016-006961CUA-motion.json, pdf/97febffa171d34fd7050bc32.pdf) is a different case: Planning Commission Motion 19694, Case 2014.0482CVAR, 651 Geary Street, heard … | removed |
| 2016-002754CUA | 2379 Chestnut St 94123 | Cultivar, a wine bar/restaurant at 2379 Chestnut St, approved to use an existing rear patio as an outdoor activity area with paving, trees and seating. | include as restaurant or cafe | Independent audit (2026-11-13) of the review: I could not refute the dispute. I read the full PDF text of Motion 20049 (pdf/74f761dbff7e434a437c2f36.pdf). Every time it names Cultivar's use, it calls it a Restaurant: in the title ("FOR USE BY AN EXISTING RESTAURANT (DBA "CULTIVAR")"), in the preamble ("a proposed Restaurant"), in the project description ("customers of the Restaurant use") and in Exhibit A. The motion never mentions a Bar use, wine, alcohol, a … | business type set |
| 2017-003058CUA | 2323 Mission St 94110 | Teeth, a restaurant/bar at 2323 Mission St, legalized outdoor activity area in rear patio with hours to 10pm | include as restaurant or cafe | Independent audit (2026-11-13) of the review: I could not refute the dispute. Under REVIEWED.md, the business type follows the use Planning approved: Steps of Rome is an existing restaurant, so Restaurant or cafe; Love Potion Library is "establishes a Bar use", so Bar. Motion 20061 (PDF M-20061, read past the opening text) only ever names a Restaurant use. The title says "OUTDOOR ACTIVITY AREA IN THE REAR OF AN EXISTING RESTAURANT USE (D.B.A. TEETH)". The … | business type set |
| 2015-008251CUA | 2120 Greenwich St 94123 | Transfer of an ABC Type 47 liquor license within the Union Street NCD at 2120 Greenwich St | exclude | The motion Planning files under this record is another case's (Motion 19474, 2018 Clement Street, 2015-007387CUA), so no motion or conditions for 2120 Greenwich St are on hand; left out rather than shown with the wrong motion. | removed |

## Motion PDFs on the public site

The public copy of this page ("SF Conditions Search", built by `scripts/validation/build_public_conditions_site.py`)
links each condition to a copy of the adopted motion kept in the site's file storage, the public Vercel Blob
store `sf-conditions-motions` (`<blob store id>`, region sfo1, connected only to the `sf-conditions-search`
Vercel project and kept apart from the app:
`https://example.public.blob.vercel-storage.com/motions/<record>.pdf#page=N`; `--pdf-base-url` for
another place), which opens at the page, with a second, smaller link to Planning's own copy. Planning's link (`link.ashx?Action=Download`) makes the browser
download the PDF, which loses the page jump. The hearing packets on commissions.sfplanning.org hold the staff
report and the DRAFT motion, so their page numbers differ and changes made at the hearing are not in them
(checked on 2018-005694CUA, 229 pages against the adopted motion's 22, and 2021-003599CUA, 43 against 19); for
2024-001899CUA and 2025-007559CUA there was no packet at the plain address. So no packet link is used.

The hosted copies are the cached adopted motions made smaller with ghostscript, the same pages in the same
order. Each copy is checked against the original: the same page count, and each condition's opening words still
on its page (pdftotext on both). Copies are cached under $LOCAL_DATA_DIR/conditions_pdf_public/ (by the
original's sha256). A cached copy is checked again on every build against the current conditions (their opening
words on their pages, and no picture page among the condition pages) and made again when it no longer fits,
since a later data build can move a condition to another page.

Since 2026-11-13 the copies are not part of the deploy: the site is only HTML, scripts and JSON (well under the
host's size limit). The build writes a manifest of the copies next to the site folder
(`$LOCAL_DATA_DIR/sf-conditions-search-pdfs/manifest.json`: `public_base_url`, `upload_limit_bytes`, and per
copy the record, object name, local file, bytes, sha256 and public URL), and `upload-pdfs.mjs` in this folder puts
them in the store at the pathname `motions/<record>.pdf` with the `@vercel/blob` SDK (`put` with
`access: "public"`, `addRandomSuffix: false`, `allowOverwrite: true`, `contentType: "application/pdf"`,
`cacheControlMaxAge: 31536000`). The CLI's `vercel blob put` adds a random suffix to the name, which breaks the
links, so it is not used. Node 22 or later; install the SDK once with
`cd tools/conditions-search && npm install --ignore-scripts` (`node_modules/` is gitignored).

```sh
node tools/conditions-search/upload-pdfs.mjs [manifest.json]            # dry run: count, MB, largest, pathnames
node tools/conditions-search/upload-pdfs.mjs [manifest.json] check      # which copies the store holds
node tools/conditions-search/upload-pdfs.mjs [manifest.json] --apply    # upload what is missing or of another size
#   add --only <record,...> or --skip <record,...> to work on a subset
```

- Every run first checks the manifest: its `public_base_url` must be the store's
  (`https://example.public.blob.vercel-storage.com/motions/`), and every file must have the manifest's
  bytes and sha256 on disk and be under `upload_limit_bytes` (50 MB, a sanity bound; the largest copy is about
  11 MB). Anything else is refused (exit 2) before any network call.
- The dry run (the default) needs no token and makes no network call.
- `check` lists the store (`list({prefix: "motions/"})`) and reports each manifest file as present with the same
  size, missing, or of a different size, and the total bytes stored; exit 1 unless all are present.
- `--apply` lists the store the same way, then uploads every file that is missing or of a different size (a copy
  of the same size is skipped), up to 4 at a time, retrying a failed upload at most twice, and prints how many were
  uploaded, skipped and failed and the MB sent; exit 1 if any failed. It stops if the store answers with a URL
  that is not this store's (a token for another store).
- `check` and `--apply` need `BLOB_READ_WRITE_TOKEN` in the environment (the SDK reads it there): the store's
  read-write token, kept outside the repo. It is never printed, and any `vercel_blob_rw_...` string in an error
  is masked.

Tests: `tools/conditions-search/tests/upload-pdfs.test.mjs` (no network: `put` and `list` are fakes). The store
serves the copies with `Cache-Control: public, max-age=31536000`, so upload before deploying the site, and a copy
made again later keeps its URL: browsers that opened the old one can keep it for up to a year. The Hobby plan
gives the store 1 GB of storage and 10 GB of transfer a month; going over blocks the store (not the app) for 30
days. There are two kinds of copy, by the motion's decision date:

- **Decided 2019 on: the copies hosted since 2026-11-12, kept byte for byte.** Images at 150 dpi (`/ebook`),
  the text layer kept. Plan drawings (pages outside the conditions that add more than 200 KB to the file on
  their own, mostly vector lines) are 100 dpi pictures of the page: they look the same but lose their
  selectable text. Their settings and cache version (`PDF_CACHE_VERSION` 4) must not change, or every one of
  these files changes; a test (`apps/api/tests/test_public_site_pdfs.py`) holds them.
- **Decided before 2019: harder (since 2026-11-13).** Every page in grayscale. A scan's black-and-white text
  layer (and its OCR text) is kept at 150 dpi on every page; the other images are 100 dpi at low JPEG quality on
  the pages that hold conditions (from the first condition's page to the page where the last one ends) and
  50 dpi at the lowest quality on the rest. Pages outside the conditions that still add more than 100 KB on
  their own (1 MB in the original: straight away) become grayscale pictures at 72 dpi (less for a big sheet),
  which lose their selectable text and small print. Most 2010-2015 motions are Word exports that ghostscript
  only makes bigger; they are hosted as they are.

Hosting the 2010-2018 motions adds about 125 MB (the 242 decided before 2019 that have conditions on the page,
from 207 MB; the largest 5.6 MB, 2016-005799CUA) to the 247 MB of the 2019-on copies (110 motions): about 372 MB
of PDFs in all, over the target of about 250 MB (`PDF_TOTAL_TARGET_BYTES`; the build prints a warning). Of the
125 MB, 70 MB are the 2016-2018 scans (80 motions), 46 MB the Word exports hosted as they are (147 motions) and
9 MB the other 15 motions of 2011-2015, which ghostscript made smaller. These are the sizes of the cached copies
($LOCAL_DATA_DIR/conditions_pdf_public/) of the motions on the page after the 2026-11-13 review; the public
build prints the same totals when it runs.

## Analytics and the feedback link on the public site

Since 2026-11-16 both pages (`index.html`, `coverage.html`) load **Vercel Web Analytics**, the plain-HTML snippet
from Vercel's quickstart: an inline `window.va` queue, then `<script defer src="/_vercel/insights/script.js">`,
served by the site itself. It is the only tracker, and no script comes from another site.

- **What is collected:** page views only (no custom events): the page's address, the referrer, the country,
  region and city, the browser, the operating system and the device type, with a timestamp (Vercel's
  "Privacy and Compliance" page). Vercel tells visitors apart by a hash of the request that it discards after
  24 hours; it sets **no cookies**, and the page stores nothing in the browser (no localStorage or
  sessionStorage). The queue's `beforeSend` takes everything after `#` off the
  address before a view is sent, so the search typed and the filters (kept in the address after `#`) are not
  collected: a page view is just `/` or `/coverage.html`. Vercel's docs say the plain-HTML snippet has no route
  support, so a search typed on the page should not count as a new view; any view that is sent has the part after
  `#` taken off all the same.
- **Where:** the script and its requests go to the site's own origin (`/_vercel/insights/...`), which the site's
  Content-Security-Policy already allows (`script-src 'self' 'unsafe-inline'`, `connect-src 'self'`). The build
  leaves the path alone (it renames only its own scripts and data), and stops if a page no longer loads it once.
- **Needs:** Web Analytics enabled for the `sf-conditions-search` project in the Vercel dashboard (Analytics,
  Enable). Until it is, the script is not served there and nothing is counted. On the local page the script is not
  found (a 404 in the console), which is harmless. The public page's contact line says page views are counted by
  Vercel Web Analytics, without cookies.
- **The path:** Vercel's quickstart (read 2026-11-16) now shows the script at a project-specific path
  (`/<unique-path>/script.js`, given in the dashboard) and says enabling adds routes under both
  `/_vercel/insights/*` and that path. The site uses `/_vercel/insights/script.js`. After the first deploy with
  analytics enabled, check that it loads (200, not 404) and that a `view` request follows; if not, put the
  dashboard's path in both pages and in `ANALYTICS_SCRIPT` in the build (still same-origin, so the CSP holds).

**"Wrong or missing? Tell me".** On the public site every result card ends with this link. It opens an email
(`mailto:`) to the contact address with the subject "Wrong or missing: <case number>, condition <number>" and a
body that gives the case number, the condition number, the condition's title, the address, a link to the card
and the motion page, then "What is wrong or missing:" for the reader to fill in. The link to the card is the
search for its case number with every kind of condition shown, plus the card's condition number
(`#q=2015-009955CUA&kind=all&card=30`): the page shows enough cards to include it (it may be past the first 50),
marks it, scrolls to it below the sticky filters and focuses it. The `card` part is used once; the address the
page writes back leaves it out (`cardLink`, `cardTarget`, `cardIndex`, `shownFor` in `search.js`). Subject and body are encoded with `encodeURIComponent`, lines end in CRLF.
The address is written once, as `CONTACT` in the public build, which also uses it for the contact line under the
page: the build sets the page's `FEEDBACK_TO` to it. The local page leaves `FEEDBACK_TO` empty and shows no link.
The wording is in `FEEDBACK` in `search.js` (`feedbackHref`, `feedbackLink`).

Tests: `tests/analytics.test.mjs` and `tests/feedback.test.mjs` (every card of the real data, made by the page's
own `card()`, and the page script itself opened at each motion's last card's link), and the build tests in
`apps/api/tests/test_public_site_storage.py`.
