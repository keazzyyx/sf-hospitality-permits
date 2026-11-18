# The shared foundation (apps/showcase)

What the three prototypes stand on. Built 2026-11-16; revised 2026-11-17 after two reviews (the changes are
listed at the end). How to run it and how to mount the search:
`apps/showcase/README.md`. Fonts and libraries: `apps/showcase/THIRD-PARTY.md`.

## What is decided, and where it lives

| Decision | Where |
| --- | --- |
| Paper, ink and a rubber stamp. Paper theme: `#F2EDE1` ground, `#E8E1D0` wells, `#171A21` ink, `#474C5B` second ink, `#1C3BC4` cobalt line, `#E23A2B` stamp. Blueprint: `#0A0F1F`, `#131B36`, `#DDE1EE`, `#9AA3C0`, `#9DB2FF`, `#FF4D3A`. Contrast on the ground: ink 14.9 and 14.6 to 1, second ink 7.3 and 7.6, cobalt 7.3 and 9.3 | `src/core/tokens.css` |
| Every other colour on a page is a `color-mix` of two of those six: `--rule` (hairlines, 30% ink), `--edge` (the one line that bounds a control, 50% ink, 3 to 1 or more), `--wash` (the highlighter, cobalt at 26% on paper and 30% on blueprint), the grid | `tokens.css` |
| Type sizes: 11 (labels), 13 (data, small print), 15 (notes, menus), 16 (body), 17 (the conditions), 20 (a condition's title), then the display sizes. Nothing in between. One weight of the mono face | `tokens.css`: `--fs-*` |
| Anything a finger has to hit is at least 44 px tall on a touch screen (`@media (pointer: coarse)`), without the type or the page growing | `tokens.css`: `--tap`; `shell.css`, `search.css` |
| Graph-paper ground: 8 px minor, 64 px major, cobalt at 3.25% and 7.5%. The grid is centred and the sheet is a whole number of 16 px wide, so page edges always sit on grid lines (on major lines at full width, 1152 px) | `tokens.css`: `body`, `.sheet` |
| Type: Instrument Serif (display, the search field), Public Sans (UI, body), IBM Plex Mono (data), Big Shoulders Display (stamp, wordmark), Architects Daughter (margin notes) | `src/core/fonts.css`, `--font-*` |
| Hairlines, radius 0 to 2 px, no shadows, no shading. Motion 120 to 320 ms; `prefers-reduced-motion` zeroes it | `tokens.css` |
| Vermilion is the stamp's colour: the wordmark, the icon, the hub's eyebrow square, and a 1 px rule beside a condition that could not be read or data that could not be loaded. Never text other than the wordmark | |
| One name, one place: `WORDMARK = "Working Title"` | `src/core/brand.ts` |

## The search page, as set

- The query field is the hero: Instrument Serif at 56 px (34 px on a phone) on a ruled line; the rule turns
  cobalt and doubles when the field has focus. Label in mono capitals (a shorter wording on a phone, one line).
  Examples cycle in the placeholder (one every 3.2 s, still under reduced motion). A link's search is in the
  field from the first paint, and what is typed while the data downloads is kept.
- Under the field: the hint, and "Search tips" (and, between a phone and a wide page, "Coverage") as words that
  open a panel.
- Filters: five form fields with mono labels; a set filter turns its label and rule cobalt. From 1040 px they
  share one line, "Which conditions" as wide as its longest choice; from 720 px three and two; under 720 px
  they fold away behind "Filters", which shares one 48 px row with "Coverage".
- Count sentence in mono between a full rule and a hairline. On a phone it is two lines ("43 conditions from 1
  of 352 motions" / "8 boilerplate hidden show them"), with "Clear all" ending the last one; the full sentence
  stays in the text.
- A result, in scanning order: a mono kicker (kind, categories); the condition number in the margin, left of a
  ruled-paper margin line, and the title in Public Sans semibold at 20 px; two mono lines of record data (case
  number and address, then business, decision date and zoning; a line breaks between facts, never inside one);
  the text at 17/28 in a 552 px column (median 67 characters a line), its opening repeat of the title set
  quieter; matches as a cobalt highlighter stroke with no underline; "p. 12 · open the motion" as the one boxed
  control, then the two small links.
- A list that comes from one motion names the motion once, above the list; its cards do not repeat it on the
  screen (it stays for screen readers, in print, and on a card a link points at).
- The coverage notice (included, not included, known gaps, "Coverage details") stays in the right-hand margin on
  a wide screen, beside the results and the notes, which keep to the left column.
- Nothing found: what was searched for, the current site's note on why, "Clear the search" (or "Clear the
  filters") and three searches that find something.
- Loading: "Reading 352 motions…" in serif italic over a hairline that fills with the real download. If the data
  cannot be loaded, or is not the data, the page says so beside a vermilion rule and offers "Try again".
- The main rules sit on the 8 px grid at every width: header 64, title, field (56 or 80 with its rule), the
  row of menus, the count bar (48). The conditions' 28 px leading does not; that is accepted.
- `/coverage/`: the current site's `coverage.html` restyled (the numbers, the reviewed list, four sections of its
  README), reached from the three coverage links on the search.

## Screenshots

`docs/ui/media/foundation-*.png` (`pnpm --filter showcase shots` rewrites all 37): `/search/` with "outdoor
seating" and with no query, in both themes, at 1440x900 and 390x844 (plus full-page, phone-results and
end-of-page views); 1024x768 with the coverage panel closed and open; 820 px; a list from one motion (desktop
paper, phone blueprint); a linked card (desktop and phone); keyboard focus; the no-match, loading, error,
filters and search-tips states; a prototype page at 1440 and 320 px; the hub; the coverage page (desktop paper,
its reviewed list, phone blueprint).

## Known limits

- The local data file is the unredacted one: the public build replaces private liaison contacts and drops
  `raw_text`, and this app does neither. Build from the public build's data before anything is published
  (see the README).
- Tested in Chromium (the e2e suite). WebKit was checked by hand with an older Playwright build that matches
  the installed WebKit (the suite's own WebKit is not installed): pages render, the search runs, the console
  has no errors. It still warns that the preloaded fonts "were not used" and requests each twice; Chromium
  requests each once. Not confirmed in Safari itself.
- Each card is three tab stops (the motion, Planning's copy, the link to the card), so 50 cards is 150 Tabs to
  "Show 50 more". No card-to-card keys yet.
- The wordmark's vermilion is 3.7 to 1 on paper: fine for a logotype, not for text, and it is used for no text.
- three, motion and lenis are installed for the prototypes and not used yet.

## Changes after the two reviews (2026-11-17)

Behaviour:
- Data that downloads but is not the data (`{}`, `null`, a wrong shape) is an error the page states, with "Try
  again", instead of a page stuck on "Reading 352 motions…" that threw on every key.
- `/coverage/` exists; the three coverage links and "The reviewed list gives each change and its reason" are back.
- "show them" from the keyboard opens the folded filters and focuses the menu it changed.
- Text typed during the download is kept; a link's search shows in the field at once; the line under the title
  no longer changes when the data arrives.
- Mounting twice on one element replaces the first search. `destroy()` during the download cancels it.
- The hash is written when typing pauses (150 ms) and a refused write cannot stop a search.
- The data file cannot inject markup through the two counts or put a non-web link on a card.
- The count is announced from its own live region, once typing stops, with the no-match reason; a card's facts
  are a flat list of name and value pairs.
- A linked card lands at the top of the window (the list is laid out in full for that one render).

Layout and type: see "The search page, as set" above. Measured: the first result starts at 488 px of 900 at
1440 (was 576), 560 of 768 at 1024 (was 700), 456 of 844 on a phone (was 583 to 651). Transfer without the
data: 128.6 kB on `/search/` (was 142.5), five font files instead of six.

Deliberate differences from the current site that these changes add: the no-match headline names the search
("No condition matches “xylophone”." where the current page says "No condition matches these filters."); the
19 motions with no conditions are a folded table, not a run-on sentence.
