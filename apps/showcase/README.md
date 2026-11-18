# showcase

The front end of **SF Conditions Search** (the public search of the conditions San Francisco's Planning Commission
attached to restaurants, bars and venues), and its local pages. The front page is "the living grid": a stamp gate
over the city's street grid, the story of one motion flown over it, and the search beside the map. Prototypes A and
B, which shared this foundation, are not part of this repository.

| Local page | What it is | Public site |
| --- | --- | --- |
| `/` | A short contents page of the local build | (none) |
| `/c/` | **The front page**: the gate, the story, the search in the world (`src/c/`, `src/pages/c.ts`; notes in `docs/ui/notes-c.md`) | `/` and `/index.html` |
| `/search/` | The search on its own | (none) |
| `/coverage/` | What the search covers: the numbers, the reviewed list, the detail | `/coverage.html` |

A returning visitor, and a link that carries a search (`#q=…`, `#card=…`, any of the search's keys), open the front
page on the search alone: the story is put away, not scrolled past, and the seal by the wordmark or the line "See the
story of one motion, from the stamp" brings the gate and the story back (Escape puts them away again). On a phone the
search alone loads no map; with the map, the band of it over the search scrolls away with the page. A window too
short for the scrolled story (a page zoomed to 200% or more, a phone on its side) lays the story out as plain
sections. The button by the theme flip pauses the map's own motion (as the system's "reduce motion" does), and a
gate or a view of the city left alone for 25 seconds rests, drawing nothing. `?gate=1` always shows the gate;
`?nowebgl=1` forces the drawn map.

## Run

From the repo root (or drop `--filter showcase` inside `apps/showcase`):

```sh
pnpm --filter showcase dev        # http://localhost:4310, hot reload
pnpm --filter showcase build      # typecheck, then build the local pages into apps/showcase/dist
pnpm --filter showcase preview    # serve the build on http://localhost:4311
pnpm --filter showcase test:e2e   # Playwright: builds, serves :4311 and the current site on :4312, runs e2e/
pnpm --filter showcase test:site  # the public site's build, held to the live site (local only: see below)
pnpm --filter showcase typecheck
pnpm --filter showcase sizes      # per-page JS/CSS/font sizes of the last build
pnpm --filter showcase shots      # rewrite the screenshots in docs/ui/media/foundation-*.png
```

The e2e run starts and stops its own servers; ports 4311 and 4312 must be free. CI runs typecheck, build and
test:e2e (`.github/workflows/ci.yml`, job "showcase").

## The public site

`vite build --mode site` builds the public site's front end: `index.html` (the front page), `coverage.html`, and
everything else under `assets/`, named by content. It is run by the site's builder, which prepares the public data
and passes it in (`SHOWCASE_DATA`, `SHOWCASE_COVERAGE_MD`, `SHOWCASE_CONTACT` (optional: without it there is no
contact line and no card link), `SHOWCASE_PDF_BASE`), checks every file and writes `vercel.json`. The build also
writes `assets/third-party-licenses.<hash>.md`, the notices of every package in it:

```sh
python3 scripts/validation/build_public_conditions_site.py --front c --out <dir> --manifest <file>
node apps/showcase/tools/serve-site.mjs <dir> 4413          # look at it, with vercel.json's headers and CSP
SITE_DIR=<dir> pnpm --filter showcase test:site             # same results as the live site, no CSP violation
```

See `docs/ui/production-c.md`. In the site build `src/core/site.ts` (`SITE`) carries the site's name, contact address,
the motion store, the content-named data files and the two pages; on the local pages it is null.

## Structure

```
index.html, c/, search/, coverage/   the four local pages (Vite multi-page; each is a few lines of HTML)
src/core/                           the shared foundation
  tokens.css                        colours (paper / blueprint), the graph-paper ground, type scale, focus, utilities
  fonts.css                         @font-face for the five families (latin, woff2, swap)
  shell.css, shell.ts               page chrome: wordmark, "skip to search", theme flip, footer facts (and the
                                    public site's contact line)
  base.css                          fonts + tokens + shell, linked from every page's <head>
  brand.ts                          WORDMARK and the mark (the product name lives here and nowhere else)
  site.ts                           SITE: the public site's settings (null on the local pages), the contact line
  theme.ts                          get / set / toggle theme, "themechange" event, the flip button, <meta theme-color>
  env.ts                            hasWebGL(), reducedMotion(), onReducedMotionChange(), isTouch(), lowPower()
  visitor.ts                        hasVisited(key) / markVisited(key) / reset(key)
  paths.ts                          sitePath(), dataUrl(), streetsUrl(), motionsUrl(), searchPage(), coveragePage()
  favicon.svg                       the icon: the double-ruled stamp, drawn in code
  search/                           mountSearch() and its parts (below)
  stamp/, world/, story/, props/    the stamp, the street grid, the scroll engine, the drawn objects (own READMEs)
src/c/                              the front page's own parts: scene, gate, sheet, story, flat map, flip, HUD
src/pages/                          one entry per page (hub.ts, c.ts, search.ts, coverage.ts)
src/data/story.json                 the fact sheet of the story's case (only what the story shows ships:
                                    tools/story-facts.mjs, the module "virtual:story-facts")
public/data/                        the map's streets and motions (scripts/ makes them)
e2e/                                c.spec.ts (the front page), parity.spec.ts (same results as the current site),
                                    search.spec.ts, robust.spec.ts, layout.spec.ts, perf.spec.ts, shots.spec.ts,
                                    helpers/ (parity, cases)
e2e-site/site.spec.ts               the public site's build against the live site (playwright.site.config.ts)
tools/serve-site.mjs                a built site served as Vercel serves it (vercel.json's headers, the CSP)
tools/sizes.mjs, tools/record.mjs   the size report; the frame-time recorder and GIF (tools/demos/)
vite.config.ts                      pages, aliases, the plugins that serve the data, and the site build
THIRD-PARTY.md                      fonts and libraries, with versions and licences
```

### Where the search logic and the data come from

- `@conditions/search` and `@conditions/coverage` are Vite aliases for `tools/conditions-search/search.js` and
  `coverage.js`. They are imported as they are: no copy, no fork. A change to the search rules there is a change
  here on the next build.
- The data stays at `tools/conditions-search/data/conditions.json`. A small plugin in `vite.config.ts` serves it
  at `/data/conditions.json` in dev and writes it to `dist/data/` on build. No copy is kept in this app.
  `SHOWCASE_DATA=/path/to/conditions.json` points the app at another copy.
- The coverage page shows four sections of `tools/conditions-search/README.md`, as `coverage.html` does. A second
  small plugin (`virtual:coverage-sections`) cuts them out with the current site's own `markdownSection()` when
  the dev server or the build starts; the README is not copied.
- Motion links go to the public copies, `https://example.public.blob.vercel-storage.com/motions/<record>.pdf#page=N`,
  with Planning's own download link (`showopendialog=0`) as the second, smaller link: the same two rewrites the
  public site's build makes (`scripts/validation/build_public_conditions_site.py`: `pdf_url`, `public_pdf`).

**The public build never uses the local data file:** it still carries the `raw_text` field and the build notes. The
site's builder prepares the public data (private contacts withheld, `raw_text` dropped, motion links to the store) and
passes it to `vite build --mode site` as `SHOWCASE_DATA`; its guards stop the build if anything private is left.

**Ports and build folder.** `SHOWCASE_PORT` sets the dev server's port (default 4310; the preview server takes
the next port up), `SHOWCASE_CURRENT_PORT` the port the tests serve the current site on (default: dev port + 2),
and `SHOWCASE_OUT` the build folder (default `dist`). Builders working at the same time each set their own.

## Mounting the search in a page

```ts
import { mountShell } from "../core/shell";
import { mountSearch, loadConditions } from "../core/search";
import { dataUrl } from "../core/paths";

const shell = mountShell({
  current: "c",
  // the skip link is always visible and first in the tab order: here it ends the opening and focuses the field
  // (a page with no opening passes `quiet: true`: the link then shows only when the keyboard reaches it)
  skip: { onActivate: () => { endTheGate(); search.focus(); } },
});

const root = document.createElement("div");
shell.main.append(root);

const data = loadConditions(dataUrl());          // optional: start the download early and share it
data.onProgress(p => drawProgress(p.ratio));     // real progress, 0 to 1 (null when the size is unknown)

const search = mountSearch(root, {
  data,                                          // or leave out: mountSearch fetches dataUrl itself
  onResults(hits, state) {                       // every search: all matches in display order + the state
    lightUp(hits.map(c => c.record));            // e.g. points on a map. Read `hits`; do not change it
  },
});

await search.ready;                              // data loaded, first results drawn (rejects if the first load fails)
search.setQuery("outdoor seating");              // type for the visitor
search.getState();                               // { q, business, category, zoning, year, kind, total, motions, hidden, shown, ready }
search.destroy();                                // remove it and everything it listens to
```

Options: `dataUrl`, `pdfBase` (default: the public store; `""` keeps the data's own links), `data`,
`onResults`, `autofocus`, `feedbackTo` (the address for "Wrong or missing? Tell me"; empty, so no link, as on
the local page), `hash` (default `true`: the state lives in the URL hash, with the current site's keys, so a
link from the live site works here; pass `false` if the page needs the hash), `headingLevel` (1 or 2),
`coverageHref` (the coverage page: `sitePath("coverage/")`; the three coverage links only show when it is set),
`slashKey` (default `true`: "/" puts the cursor in the field; the front page turns it off, since a single-key
shortcut there could not be turned off). A condition read with no page opens its motion where the conditions begin
(`src/core/search/section-pages.json`), never at page 1. While typing, the first 12 cards are written with the
keystroke and the rest of the page a frame later; the data is applied in a few tasks, not one.

The root element also dispatches two bubbling events, for code that does not own the mount call: `cs:results`
(`detail: { hits, state }`) after every search, and `cs:data` (`detail: { data }`) each time the data has
loaded. Use `cs:data` rather than `search.data` for anything that should follow the data: if the first load
fails the page offers "Try again", and a later success is only announced by the event (the pages fill the
footer's facts this way). On every page that has the search, `window.showcase.search` is the handle and
`window.showcase.mountSearch` the function, for the console and the tests.

What to rely on:

- **One search per element.** Mounting again on the same element destroys the earlier search first.
- **Before the data is here** the field already shows the hash's query, `setQuery()` and anything the visitor
  types are kept and searched when it arrives, and the menus are disabled.
- **If the data cannot be loaded or is not the data** (`data-cs-state="error"`): `ready` rejects, the field is
  read-only, and "Try again" fetches `dataUrl` afresh.
- **`destroy()`** removes every listener and timer; if this search started the download itself and nobody else
  called `loadConditions()` for it, the download is cancelled. A page that started the download (the example
  above) keeps it.
- **The hash** is written at once for a menu, a click or Enter, and 150 ms after typing pauses (browsers ration
  `history.replaceState`).

The search sets itself by the width of the element it is mounted in (container queries), not the window: under
720 px it is one column with "Filters" and "Coverage" folded away in one row; from 720 px the condition numbers
hang in a ruled margin and "Coverage" is a word under the field that opens the notice; from 1040 px the five
menus share a line and the coverage notice sits in the right-hand margin, beside the results and the notes.

What it must keep doing is written down as tests: `e2e/parity.spec.ts` loads 41 hashes on the current site's
page and on `/search/` and requires the same conditions in the same order with the same count sentence. To hold
a page to it, add its path to `PATHS` there (or run with `PARITY_PATHS=/search/,/c/`); if the page
has an opening to get past, call `expectParity(context, hash, { path, enter })` from `e2e/helpers/parity.ts`.

## Other shared pieces

```ts
import { reducedMotion, onReducedMotionChange, hasWebGL, isTouch, lowPower } from "../core/env";
import { hasVisited, markVisited, reset } from "../core/visitor";
import { getTheme, setTheme, toggleTheme, onThemeChange } from "../core/theme";

if (hasVisited("gate")) skipTheGate(); else onStamped(() => markVisited("gate"));
if (reducedMotion() || !hasWebGL()) showTheStillVersion();
onThemeChange(theme => scene.setPalette(theme));   // "paper" | "blueprint"; also a "themechange" event on window
```

Colours, type and spacing are CSS variables in `src/core/tokens.css` (`--paper`, `--paper-2`, `--ink`,
`--ink-2`, `--line`, `--stamp`, and the mixes `--rule`, `--edge`, `--wash`; `--font-display`, `--font-ui`,
`--font-data`, `--font-stamp`, `--font-hand`; the sizes `--fs-micro` 11, `--fs-small` 13, `--fs-note` 15,
`--fs-body` 16, `--fs-read` 17, `--fs-lead` 20: use these and nothing in between; `--tap` 44 px, the least height
of anything a finger has to hit, applied under `@media (pointer: coarse)`). The mono face is used in one weight
(400): a second weight is a second download.
Read them from CSS, or from script with `getComputedStyle(document.documentElement).getPropertyValue("--line")`
so a scene follows the theme. Every page is `.sheet` wide: at most 1152 px, always a whole number of 16 px, so
its edges sit on the graph-paper grid.

## Changing the wordmark

One line, in `src/core/brand.ts`:

```ts
export const WORDMARK = "Working Title";
```

The mark (the double-ruled stamp top left) is drawn from it and sizes itself to the words, and the tab titles
follow. No other file names the product; `e2e/search.spec.ts` checks the mark's label on every page.
