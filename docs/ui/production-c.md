# C in production: the front end of SF Conditions Search

Written 2026-11-17. Prototype C ("the living grid": the stamp gate over San Francisco's street grid, the story of one
motion flown over it, the search beside the map) is the front end of the public site,
https://sf-conditions-search.vercel.app, replacing the plain page. The search behind it is unchanged: C imports
`tools/conditions-search/search.js` as it is, so the results, their order and the counts are the live site's own.
How C was built and reviewed as a prototype is in [notes-c.md](notes-c.md); this file is what changed for production,
how to build and deploy it, what guards the build, and what was measured.

## What changed from the prototype

- **One branch, one front end.** Prototypes A and B (and their pages, tests, demos and notes) are not part of
  this repository. Every shared module C uses stays (`src/core/stamp`, `world`, `story`, `props`,
  `search`, the shell). The local build's `/` is now a short contents page of the three local pages (`/c/`,
  `/search/`, `/coverage/`).
- **A site build.** `vite build --mode site` (apps/showcase/vite.config.ts) writes the public site: `index.html` (the
  front page, also served as `/index.html`) and `coverage.html` at the top, every other file under `assets/`, named by
  its content. Titles "SF Conditions Search" and "Coverage · SF Conditions Search", the live meta description, no
  `noindex`, the live analytics snippet once in each page's head, no source maps, nothing inlined (a `data:` font
  would need a looser CSP), no `public/` folder copied. The wordmark on the page stays "WORKING TITLE"
  (`src/core/brand.ts`). `src/core/site.ts` (`SITE`) carries the site's settings into the code; on the local pages it
  is null.
- **The same URLs as the live site.** `/#q=…`, `/#card=…`, any search state in the hash, `/index.html#…` and
  `/coverage.html` all work, with the live site's hash keys (the search writes them).
- **The live site's promises.** The contact line, in the live words and with the same address (the builder's
  `CONTACT`, passed in as `SHOWCASE_CONTACT`), sits in the footer under the search on both pages; every card's
  "Wrong or missing? Tell me" emails it (`mountSearch` `feedbackTo`). The coverage page shows what the live
  `coverage.html` shows: the numbers worked out from the data, the reviewed list, and the four detail sections cut
  from the public coverage text (`public/coverage.md` plus the builder's "Text quality" and "Motions left out"),
  which it reads as the page loads, as the live page does; both themes.
- **The data, byte for byte.** The builder prepares the public data exactly as before (private contacts withheld,
  `raw_text` and the build notes dropped, motion links to the Blob store) and hands it to Vite: the site ships
  `assets/conditions.93c39b2c3683.json`, the very file that is live now (sha256
  `93c39b2c3683a749645c964ebdcbb5bb75bcdea89aa6b4970ee94fb57f0cafc6`), and `assets/coverage.5ee77b381916.md`, also the
  live file.
- **The story ships only what it shows.** C used to import `src/data/story.json` whole (its open questions, the notes
  about page 1, how the facts were checked, a local database address). It now imports `virtual:story-facts`
  (`tools/story-facts.mjs`): the fields the story uses and nothing else. The map's motions ship as their points only
  (no notes on how they were located).
- **Returning visitors and links get the search directly.** The prototype scrolled them to the end of a ten-screen
  story, with nothing saying the story was above. Now the story is *put away* (`html.c-direct`: not in the page; the
  scroll engine's new `setCollapsed()` holds it at its end): the page is the search, from the top. One line over the
  search, "See the story of one motion, from the stamp", and the seal by the wordmark bring the gate and the story
  back; Escape puts them away again, the search as it was.
- **A phone coming back sees the search first.** On a phone the search alone loads no map at all (`html.c-mapless`:
  no three.js, no street file, no band over the list); the field is under the header. The seal or the line brings the
  story, and its map, back. A window 900 px wide or more, and wider than it is tall, gets the map beside the search; a
  phone on its side is too short for the scrolled story and gets the plain layout (below).
- **The map costs the search nothing.** It was already updated at the next animation frame after a search and rests
  when nothing moves; a visitor who opens on the search waits for none of the map (it is asked for after the data).
  Measured below: typing in the search with the 3D map beside it holds 16.7 ms frames.
- **The icon** moved from `public/favicon.svg` to `src/core/favicon.svg` so that it is content-named too.

## After the production review (2026-11-17)

Four independent reviews (a mid-range phone's performance, accessibility, a reviewer trying to break it, a release
audit) were run on the build above. What they found, and what was done:

**Performance**
- **The page now rests.** Nothing asks for frames once nothing moves: the scroll engine sleeps (`sleep: true`), the
  scene's loop stops when every lag has arrived and nothing is alive or on the clock, and wakes from any setter, the
  tab coming back or a restored WebGL context; the cue's arrow nudges four times while the first chapter is read,
  never on a hidden element. Measured (headless Chromium with Metal): the search at rest asks for 0 frames a second
  (was 120); a typed search settles within about 0.3 s.
- **A gate, or a view of the whole city, left alone rests.** After 25 s with no move, key, scroll or touch the map's
  drift and rings stop and the stamp lies down on the page: 0 frames a second (was 60, with about 1,000 draw calls).
  The next move wakes it (`setResting`, `REST_MS` in `pages/c.ts` and `c/gate.ts`). A stamp lying flat no longer keeps
  its loop running for its bob (`core/stamp/stamp.ts`).
- **The data is applied in a few tasks, not one** (`onData` in `core/search/index.ts`: copy, index, the link's
  search prepared a slice at a time, then the page), with a breath (`scheduler.yield()` or a zero timeout) between.
  At 4x CPU on a 390 by 844 phone the longest task at load is now 180 ms (was 290 to 345 ms; 801 ms on a deep link);
  what is left is the browser parsing the 5.7 MB of JSON.
- **Typing writes 12 cards with the keystroke and the rest of the page a frame later.** At 4x CPU: keydown median
  16 ms, worst 72 ms, none over 100 ms in 39 typed keys (was 104 to 112 ms on the first key of a query).
- three.js no longer reads every shader's compile log synchronously outside the dev server
  (`renderer.debug.checkShaderErrors`).

**Accessibility**
- **Every line of the story can be read.** A chapter longer than its panel scrolls inside it first (the wheel, via
  Lenis's `allowNestedScroll`, and the arrow keys, via `data-story-scroll` in the engine), its foot fades and a
  "More ↓" cue says so. A window shorter than 480 px under the header (a page zoomed to 200% or more, a phone on its
  side) lays the story out as plain sections the page scrolls through (`html.c-flow`, `story.setFlow()`; the map
  shows at the gate only): every condition and its link are there. Tested at 640 by 450, 320 by 256, 844 by 390,
  375 by 667, 390 by 844, 1024 by 600, and 1280 by 720 with the WCAG text-spacing override.
- **The map's band over the search on a phone scrolls away with the page** (as if it stood at the top of the
  search) and comes back with it: it never covers a result, a focused link or the field, and once it is gone the
  scene draws nothing. At 400% zoom there is no band at all (the plain layout).
- **Focus is never hidden or dropped.** `scroll-padding-top` keeps focused elements clear of the sticky header; an
  arrow key that changes chapter (or condition) moves the focus to the new heading; a rail tick moves it to its
  chapter's heading on arrival; the rail's last tick (or "Next" at the end) moves it to the search field; Escape after
  a replay returns it to the seal (or the line) that brought the gate up. Nothing behind the gate is in the tab order
  (the search is `inert` while the gate is up: Tab past the stamp no longer takes the gate down).
- **A pause button** by the theme flip (`aria-pressed`, remembered in this browser) holds the map and the story
  still, as the system's "reduce motion" does (stills, no drift, no rings, no drum at the gate). It is hidden when
  the system setting is on; a change of that setting while the page is open is followed.
- **Forced colours:** matches use the system's `Mark`/`MarkText`, the rail its `CanvasText`/`Highlight`, the
  current row of the page facsimile an outline.
- **Contrast:** a highlighted word is set in the ink (7.8:1 on the dark ground, was 4.05:1 for the address); the
  current row's number too (was 3.03:1); the pencil notes at the gate have a halo of the ground.
- **The stamp is announced once** ("Stamped: approved with conditions."); the first chapter's heading, which takes the
  focus, carries how to go on as its description.
- **No single-key shortcut** on the front page ("/" is off there: `mountSearch({ slashKey: false })`, and its hint
  with it; the skip link is the way to the search). The local `/search/` page keeps "/".
- The page's one h1 ("SF Conditions Search", visually hidden) comes first; the search heading is an h2. The phone's
  stepper is "Previous" / "Next" (it moves one stop) and says where it arrived. The seal's name starts with its
  visible words.

**Robustness and the release**
- **A condition with no page never opens page 1.** The 12 conditions of 2011.0186C (read with no page numbers) opened
  their motion at page 1 on the live site, which prints the project sponsor's name and address. They now open at
  page 11, where the motion's conditions (Exhibit A) begin, found by reading the PDF; the card says "Exhibit A, p. 11"
  (`src/core/search/section-pages.json`). Only those 12 links differ from the live site; the parity tests expect
  exactly that, and the build stops on any new condition without a page that is not in that file.
- **A map that cannot be loaded** leaves no empty panel: the search takes the width, no band is kept, the story says
  once, where the map would be, that it reads without it, and no count is written over that.
- **Licence notices** ship: `assets/third-party-licenses.<hash>.md` (three, Lenis, motion and its parts, the five font
  packages, each with its licence text), named in each page's head; `THIRD-PARTY.md` is rewritten for the site.
- `SHOWCASE_CONTACT` is optional (no contact line and no card link without it), the story's motion links use the
  build's own store (`SHOWCASE_PDF_BASE`), and the site's search keeps the data's links as written;
  `e2e-site/site.spec.ts` reads the contact address and the store off the live site's files instead of naming them.
- Without JavaScript, both pages say what they are, and the front page gives the contact address.
- Fallback colours for browsers without `color-mix()` (iOS Safari before 16.2). Failed font downloads no longer raise
  unhandled rejections.
- The prototype briefs and the research notes are not part of this repository;
  `concepts.md` keeps the short record of how C was chosen. `story-runners-up.json` is gone; `public/data/
  sf-streets.json` stays (it describes the street file's layout for `scripts/build-grid.mjs`; it is not shipped); the
  note in `public/data/motions.json` no longer names a local database address.

**Not done, and why**
- *The theme default* (the front page opens in the blueprint, the coverage page follows the system): the owner's
  call; unchanged.
- *Fewer font preloads* (PERF-6): the gate's first frame uses all five faces; dropping a preload would swap a face in
  front of the visitor. First paint is within budget.
- *A pixel-ratio governor* (PERF-8) and *a real phone's GPU, Safari and Firefox*: need a real device; for the live
  check. `sf-streets.bin`'s compression on Vercel (PERF-7) is to be read off the deploy
  (`curl -sI -H 'Accept-Encoding: br, gzip'`).
- *A hold handed from one input to another* (Space, then the mouse) still cancels; *a 210k-character query* behaves as
  on the live site (capping it would change results).
- `window.showcase` and `window.__story` stay in the public bundle: the built-site tests drive the page through them.

## After the second verification (2026-11-17)

An independent verification of the build above left four things to fix; all four are fixed, with tests:

- **No feedback e-mail opens page 1.** The card's "Wrong or missing? Tell me" e-mail for 2011.0186C named the motion
  with no `#page`, so it opened on page 1 (the sponsor's name and address): its body comes from `feedbackLink` in the
  unchanged `search.js`, which reads `c.pdf`. `card()` (`core/search/index.ts`) now hands it the condition at the page
  its button opens (`feedbackCondition`: the section page; a condition with no page and no section page gets no
  motion link in the e-mail at all). Guarded three ways: `e2e/c.spec.ts` and `e2e-site/site.spec.ts` read every href
  and every decoded mailto body on the page (`e2e/helpers/links.ts`: no `.pdf` without `#page=N`, N >= 2), and the
  builder's `check_site` now opens the built C site in headless Chromium (`apps/showcase/tools/check-links.mjs`,
  served by Playwright's routing, no port) at every motion read with no page and at a long list, and stops on any
  such link (checked: the unfixed bundle is stopped); a check that cannot run stops the build too.
- **The header fits at 400% zoom.** Under 400 px the skip link keeps its arrow and gives up its words (they stay its
  name), so the pause and theme buttons keep their size (they were squeezed to 16-34 px at 360 to 399 px); in the
  plain layout under 560 px the seal waits, as it does in the story on a phone (the skip link stays in sight there).
  At 360 by 225 the theme button was off screen and the page scrolled 12 px sideways; at 320 by 256 the seal sat
  over the wordmark. Tested at both: no overlap, no sideways scroll, the theme button on screen, the skip link named.
- **The arrow keys never drop the focus at the story's end.** Leaving the last chapter (its heading goes inert) with
  the focus in it, by a key or by scrolling, moves the focus to the search field (`onFocusLeft`), as the rail's last
  tick does; with the focus elsewhere nothing takes it.
- **A gate held still sleeps.** With motion paused (or the system's setting turned on while the gate is up) the gate
  asked for 60 frames a second until its 25 s rest. The stamp now has a still mode (`setStill`: no bob, it lies down
  at once) and the gate's loop sleeps once what it follows stops changing, woken by a move, a key or a timer for its
  next note; `Gate.setStill()` follows the pause button. Measured: 0 frames in 2 s at the gate under reduced motion,
  paused, or switched to reduced while up (was 120 in 2 s).

## Build and deploy

```sh
pnpm install                                     # once (the site build needs apps/showcase's node_modules)
pnpm --filter showcase exec playwright install chromium   # once (the build reads its cards' links in a browser)
python3 scripts/validation/build_public_conditions_site.py --front c \
  [--out DIR] [--manifest FILE] [--pdf-root /path/to/sf-hospitality-permits/tools/conditions-search]
```

`--front c` is the default; `--front classic` rebuilds the old plain page, byte for byte as deployed until now
(checked: its index.html, coverage.html, vercel.json and assets are identical to the live folder's backup). The
default output is `$LOCAL_DATA_DIR/sf-conditions-search-site/` (its `.vercel/` link is kept) and the PDF
manifest goes beside it. `--pdf-root` is only needed in a git worktree, which has no `pdf/` folder of its own. The
motion PDFs are the same as before (same cache, same manifest), so nothing needs uploading for this change.

Look at a build before deploying it, as Vercel would serve it:

```sh
node apps/showcase/tools/serve-site.mjs DIR 4413       # vercel.json's headers and CSP; a stand-in for analytics
SITE_DIR=DIR pnpm --filter showcase test:site           # same results as the live site, no CSP violation (below)
```

Deploy, by hand: from the site folder (linked to the `sf-conditions-search` project),
`vercel deploy --prod`. Before deploying, record the current production deployment as the rollback target
(`vercel ls sf-conditions-search` / the dashboard); to go back, `vercel rollback <that deployment>` or rebuild with
`--front classic` and deploy that.

## The guards (`check_site`, before any file is written)

Every text file of the output is read: both pages, every Vite script and style bundle (three.js included), the data,
the motions, the coverage text, the icon. The build stops on:

- the product name or an internal path, table or tool (`FORBIDDEN`, as before; nothing in three.js or the other
  bundles trips it, so no exception was needed);
- a `"raw_text"` field anywhere, or in the data;
- a link to page 1 of a motion (`#page=1`), or a condition whose page is 1;
- a private contact: any of the strings the withholding takes out (`private_contact_strings`, new in
  `private_contacts.py`), read from the local data, from `story.json`, and from the data as it was before the
  withholding began (git, the commit before `private_contacts.py` was added, where the history has it: the
  liaisons' names, phone numbers, e-mail and address, held in memory only, never printed; a clone of this repository
  starts after the withholding, so there that source is skipped); any phone number that is not one of the City's;
  any e-mail address that is not the City's or `CONTACT`; any published condition the withholding would still change;
- the analytics queue and script not exactly once each, in each page's head, queue first;
- a motion link outside the Blob store;
- for the C front end: a source map; any file outside the expected set (the two pages, `vercel.json`, Vite's
  `assets/<name>-<hash>.<ext>` and the content-named `assets/<name>.<sha256-12>.<ext>`, the licence notices among
  them); a content name that is not its content's; a missing data file (conditions, motions, streets, coverage text);
  the data or coverage text not byte-identical to the classic build's, under the same name; a condition with no page
  whose motion is not in `src/core/search/section-pages.json` (it would open page 1); and, read in headless
  Chromium (`check_links`), a card link or feedback e-mail that opens a motion without a page of 2 or more.

## The CSP

Unchanged, the same for both front ends:
`default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;
connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`. C needs nothing more: its scripts,
styles, fonts, icon and data are the site's own files; WebGL and canvas need no directive; its one inline script is
the theme set before the first paint (beside the analytics queue that needed `'unsafe-inline'` already); its inline
styles are set through `element.style`. Checked in the browser: zero `securitypolicyviolation` events through the
gate, the stamp, all eight chapters, the search, the flip and the coverage page, with the drawn map and with the 3D
scene, and for a returning visitor on desktop and phone.

## Tests

- `apps/api/tests/test_public_site_front_c.py` (new, 28 tests with the reviews' (the browser link check on a made-up
  card, in `check_site`, and failing closed): a condition with no page, the
  licence file, the store and the noscript contact in the build, a build with no contact address): every guard on a small made-up site (a source map, a
  stray file, an internal name in a bundle, `raw_text`, `#page=1`, a private phone or e-mail, a withheld name in any
  case, analytics missing or twice, a wrong content name, a missing data file, a condition still holding a contact or
  linked to page 1), `private_contact_strings`, the withheld strings read from git (skips without the history), the
  command's default, and two that run the real Vite build (skip without pnpm/node_modules): the whole C build, held
  byte for byte to the classic build's data, coverage text and vercel.json; and a name only in a bundle stopping it.
  The older `test_public_site_*.py` and `test_private_contacts.py` pass unchanged.
- `apps/showcase/e2e-site/site.spec.ts` (new, run by `pnpm --filter showcase test:site`, local only; skips when a
  folder is missing): the built site and the live site's backup, each served by `tools/serve-site.mjs` with its own
  `vercel.json` headers; the 41 parity cases of `e2e/parity.spec.ts` plus "security guard", a case number, "Valencia
  St", "2740 Mission", "2740 - 2744 Mission St" (a range address as its card shows it) and a card link, and a link to
  `/index.html#…`, each with the same count sentence, conditions in the same order, linked card, written-back hash,
  "show more" clicks and motion links (Blob URL + `#page=N`); the same headers and CSP; no CSP violation or console
  error the whole way (drawn map and 3D scene); a returning visitor and a phone; titles, wordmark, no prototype words;
  analytics counting each page once without the hash; the coverage page's numbers, reviewed list and detail equal to
  the live page's.
- `apps/showcase/e2e/` (CI): `c.spec.ts` gains the put-away story (a returning visitor, a link, Escape, a phone that
  loads no map) and, after the review, a page at rest asking for no frames (the search, and a gate left alone), the
  pause button, the focus never falling to the page, the plain layout at 640 by 450, the band scrolling away on a
  phone, a condition with no page, the headings, and a failed map; the A and B tests are gone; `parity.spec.ts` runs
  `/search/` and `/c/`. `e2e-site/site.spec.ts` adds 2011.0186C (its 12 links at page 11) and holds every motion link
  to carry a page of 2 or more.
- CI (`.github/workflows/ci.yml`, job "showcase"): the 66 conditions tests (node only), then `pnpm install
  --frozen-lockfile`, typecheck, build, Playwright's Chromium, `test:e2e`. On CI the 3D tests use SwiftShader
  (`--use-angle=swiftshader --enable-unsafe-swiftshader`), the typing budget is report-only with a 500 ms ceiling and
  the four-times-slower run is skipped, and a failed test gets one retry (a held key loses to a busy runner).

## Numbers (2026-11-17, Apple M2)

- Site folder: 29 files, 7.07 MB (the data is 5.72 MB of it; the licence notices 30 kB); the classic site was 7
  files, 5.80 MB.
- Front page, gzip: initial JS 55.3 kB (budget 70), CSS 13.8 kB, fonts preloaded 96.9 kB; lazy: three.js 140.2 kB.
- After the review, emulated 390 by 844 phone, 4x CPU, Metal: longest task at load 180 ms (first visit, a returning
  visitor and a deep link alike); typing keydown median 16 ms, worst 72 ms; frames asked for at rest: 0 a second in
  the search, at a gate or a city view left alone 25 s.
- Frames, headed Chromium with Metal at 1440 by 900, DPR 2, built site served with its CSP, 25.8 s of the gate
  (pointer sweeping, a held stamp, the crack), the story by wheel (70 notches) and the search (four queries typed,
  a card hovered, the pointer over the map), 1,541 frames: median 16.7 ms, p95 17.7, p99 17.7, worst 50 (the stamp's
  hit-stop). Gate 16.7 / 17.7, story 16.7 / 17.7 (worst 49), search 16.7 / 17.7 (worst 17.7).
- Screenshots at 1440 by 900 and 390 by 844 in both themes (gate, chapters 2, 4, 6, 8, search, returning, a deep link
  to a range address, coverage): no console error or warning.

## Still rough

- Chromium only; no Safari, Firefox, real phone or weaker graphics card has been tried. A mid-range phone's frame
  rate (its GPU) is unmeasured: check on one real iPhone and one Android in the live check (gate tap and hold, story
  scroll in both orientations, typing, a PDF link).
- The phone that opens on the search alone has no map until the story is replayed (by design, but it means a
  returning phone visitor never sees the map unless they ask).
- `sf-streets.bin` (179 kB; 83 kB gzipped) is served uncompressed unless Vercel compresses
  `application/octet-stream`: read it off the deploy.
- The search's own heading still reads "Conditions of approval" (the tab title is "SF Conditions Search"); the
  name comes later with the wordmark.
- The rest of [notes-c.md](notes-c.md)'s "Rough or unfinished" stands (the thinner no-WebGL map, the phone band's
  full-window canvas, label placement by hand).
