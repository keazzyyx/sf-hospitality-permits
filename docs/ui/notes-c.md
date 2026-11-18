# Notes: prototype C, "the living grid" (`/c/`)

> **2026-11-17:** this prototype became the public site's front end; what changed for production is in [production-c.md](production-c.md). The `/a/` and `/b/` routes and their notes are not part of this repository.

Built 2026-11-17 on top of A's stamp (`src/core/stamp/`) and B's world, props and scroll engine (`src/core/world/`,
`src/core/props/`, `src/core/story/`). Its build brief is not part of this repository. Reworked the same day after three reviews
(visual, performance and accessibility, break-it); the section "After the reviews" says what changed and what was
turned down. This file says what is there, how it is put together, what was measured, what is rough, and what it
would take to finish.

## What was built

One page, one world. San Francisco's street grid (11,160 segments, one draw call) is the ground of the whole
page, with the 350 motions that have an address as points on it. Blueprint (dark) is the default; the mark in
the corner (or `T`) flips it to paper and back, and the flip travels as a circle from the mark.

1. **The first frame is DOM.** The header, the motion sheet (laid on the ground plane by a `matrix3d` worked out
   from the camera as plain arithmetic, `src/c/project.ts`), a dashed outline of the city on the same camera, the
   button and "Skip to search" paint before any 3D code has loaded (`<body class="page-c">` is in the HTML, so
   there is no flash of the other pages' graph paper). The scene arrives after two frames, the outline fades and
   the streets draw on outward from the castle (1.6 s); the sheet does not move when the scene takes over.
2. **The world is never still where it is meant to be alive.** At the gate and in the two whole-city chapters: a
   slow drift, a ring every 5.2 s from a different motion, points floating over the street plane. Inside a close
   chapter and in the search it rests (see "Render loop").
3. **It answers the cursor.** The view tilts toward it (250 ms lag), the ground rises in a dome under it (75 ms),
   and the motion under it is named on a plate with a short leader. The label and a click ask the same function
   (`scene.pick`), and a click searches the case the label names. A legend in the corner (on its own paper plate)
   has a north arrow that turns with the camera, a scale bar true to it, and the latitude and longitude under the
   pointer only while the pointer is on the map.
4. **The gate.** Motion No. 19958 lies on the grid at its address, just over the button. The stamp waits over the
   sheet's ruled band under "Preamble" (and goes back there when the pointer is over the header). Press and hold:
   the stamp lowers, a pencil ring closes, the grid sinks in a dent; the slam (70 ms hit-stop, a jolt) leaves the
   mark and sends a ring through the whole city. The stamp lifts straight up, waits a beat, and is taken up and
   away off the top of the window, whole. The sheet cracks through the mark: the halves part, each tips on its
   broken edge and goes down into the grid where it lies, one after the other, while the grid in the gap stays at
   its resting tone; then the case's point turns vermilion on a pin taller than any stack. An early release heals
   with A's pencil notes; one Enter (on the button or with nothing focused), a click without holding, or a tap
   stamps at once; a press made before the gate's script has arrived is kept and done on arrival.
5. **The story, flown, with drawn objects.** B's nine chapters and timeline (`core/story`), staged on the grid:
   the city · the address (the hill rises, B's castle folds up on its street, Greenwich St and Montgomery St named
   on plates beside their lines) · the application (two rows of cards on the street, 23 filled, 11 plain, each row
   counted on a plate at its west end) · the hearing (the route line along real streets, B's City Hall folding up
   at its end, seven seats that fill one by one, the names under them, "Ayes 7 of 7") · the motion (the mark laid
   on the ground in front of the castle at the ground's tilt; the 22 conditions rise as a stack of 22 slabs beside
   it, paper faces, cobalt shade, ink edges, hiding the streets behind) · the conditions (eight steps; each inks one
   slab and writes its gloss in pencil beside it) · the exact page (a facsimile in type of page 15) · 5,048 more
   (every motion grows its stack in a wave from Telegraph Hill; "More than the one you just read: 5,049 conditions in
   all, from 352 motions.") · the search. Every label stands on a paper plate, with a hairline to what it names.
   The rail stands on its own strip of paper. A scroll that stops between chapters, or while a chapter's text is
   still fading in, is carried on to where the text reads whole.
6. **The search, in the world.** An opaque panel on the left 64%, and the map fitted to the column beside it (the
   city's outline fitted with margins, north up, the pitch raised to use a tall column). Every search lights the
   matching stacks and sinks the rest, and one ring leaves from the matches; then the map rests. A card under the
   pointer inks its stack, steps the other matches down, and draws a hairline from the panel's edge that ends in
   a ring at the stack's top with its case number. Five matches or fewer are each named where they stand. A click
   on a stack searches that case alone (the filters are cleared through the address, so it is never "0 found").
7. **Nobody is trapped.** "Skip to search" from any state, also before the gate's script arrives; "/" from
   anywhere goes the whole way to the search; Tab into the search from the gate or the rail opens it; a search hash
   that arrives while the gate or the story is showing opens it (and a `card=` target is kept); `#search` (the skip
   link's own address) opens on the search; a returning visit, `?gate=1`, the seal to replay (always at the top of
   the page, the stamp at its true size) and Escape to put a replayed gate away and return. While the gate is up
   the footer is inert, the page cannot be scrolled under it, and the search's live regions are quiet.
8. **Phone (390 by 844).** The sheet is fitted between the header and the button; the story's text is a panel
   under the map that scrolls when it does not fit, over a strip for the previous / next pair; the search's map is
   a band with its caption on its own row of paper. The header's controls stay put in every state.
9. **Reduced motion.** No drift, rings, dome, tilt or draw-on; "Stamp it", a 150 ms fade; B's stills; the flip is
   a cut. The scene draws nothing while nothing changes (0 draws in 5 s in every state measured).
10. **No WebGL** (`?nowebgl=1`, no context, or WebGL drawn in software): the same streets and motions drawn as SVG
    through the same camera arithmetic (`src/c/flat.ts`), with streets heavier close up as in the scene, the route,
    the 22 slabs and the picked one, the seven seats, the labels, the lit points, the hairline and click-to-search.

## How it is put together

- `src/pages/c.ts`: the entry and the one state machine (`gate → story → search`, skip from anywhere). It owns
  the canvas, the pointer, the hand-offs, the keys that work everywhere ("/", Escape, Enter at the gate), the
  page's one status line (outside the gate, so the gate's last words are heard), and what is tied to the camera
  after each frame.
- `src/c/scene.ts` (lazy, the only three.js): the world, the camera (a resting pose that its owner sets, eased on
  hand-offs; drift, tilt and jolt on top), dome and dent, rings, stacks, picking (nearest stack on the screen),
  B's castle and City Hall (`core/props`), and this page's small solids (`src/c/blocks.ts`: the slabs, the cards,
  the seats, each set one instanced draw call with everything that moves in the vertex shader).
- `src/core/world/living.ts` (opt-in, not imported by `/b/`): the living materials.
- `src/c/gate.ts` (lazy): the stamping, on `core/stamp`. `src/c/sheet.ts`: the gate's DOM.
- `src/c/story.ts`: the story's DOM, camera keys, the labels on plates, and every drawing change as a function of
  the scroll. `src/c/content.ts`: B's text, copied. `src/c/places.ts`, `poses.ts`, `project.ts`: geography,
  resting poses (the gate's and the search's are fitted to the window), and the camera as arithmetic.
- `src/c/flip.ts`: the flip (a second press during a flip is queued). `src/c/hud.ts`: legend, tag, caption, marks,
  hairline. `src/c/flat.ts` (lazy): the drawn map. `src/c/gpu.ts`: one WebGL probe, after the first paint.
- Draw calls in a close chapter: streets 1, stacks 2, route 1, castle about 45, slabs 1, cards 2, seats 1.

## Measured (Apple M2, built app on `vite preview`, headed Chromium with ANGLE Metal, 1440 by 900 at DPR 2)

"rAF" is the page's frame clock; "draws" is the gap between frames the scene actually drew (`scene.onRender`),
which is what the eye sees. Long draw gaps at rest are the scene resting, not stalls.

| What | rAF median / p95 / p99 / worst | draws median / p95 |
| --- | --- | --- |
| Gate, pointer sweeping, 8 s (638 frames) | 16.7 / 18.2 / 18.6 / 33.9 ms | 16.7 / 19.5 ms |
| Hold, slam, crack, fall, 6 s (365) | 16.7 / 18.0 / 18.6 / 18.7 ms | 16.7 / 18.3 ms (one 102 ms gap: the 70 ms hit-stop) |
| Story by wheel, 8 s (791) | 16.7 / 18.2 / 18.6 / 33.3 ms | 16.7 / 18.7 ms (was 33.4 / 34.9: travel was drawn at half rate) |
| Search: typing 4 queries, card hover, map pointer (377) | 16.7 / 18.2 / 18.6 / 18.6 ms | 16.6 / 18.8 ms |

The recorder (`node tools/record.mjs c`, built app, 1280 by 800): 12.6 s, median 16.7 ms, p95 17.4, p99 17.6, worst
33.3, no frame over 33 ms, first contentful paint 192 ms, no console problems; the GIF is 11.9 s (the gate, a let-go,
the slam and ring, the crack, the castle chapter, the flip). `tools/demos/c.mjs` is unchanged and still shows that.

Draws in 5 s at rest: gate idle 150 (the drift and the rings, at half rate, as the brief asks); search with the
pointer on the panel 0; search with the pointer parked on the map 0; a close chapter's hold 0 to 10 (the end of a
lag); the skyline chapter with the pointer on the map 118 (its rings). Under reduced motion: 0 everywhere.

Sizes (built, gzip; `pnpm sizes` with `SHOWCASE_OUT=dist-c`): initial JS on `/c/` 60.8 kB (budget 70; up from 56.4
because `places.ts` reads the castle's and the hall's measures from `core/props/plans.ts`, 10 kB); CSS 13.7 kB.
Lazy: three.js 137.9 kB (budget 220), scene 12.0 kB, City Hall 8.5 kB, gate 4.1 kB, A's stamp 16.1 kB and its 3D
half 5.5 kB, drawn map 2.4 kB. A visitor who opens straight on the search (a link, a return) now waits for none of
the map: three.js and the street and motion files are asked for once the search's data is in.

## Tests

`e2e/c.spec.ts`, 28 tests. New since the reviews: the label names what a click searches (with the 3D scene forced;
it waits for the software-drawn view to settle), every chapter readable to its end at 375 by 667, 844 by 390 and
720 by 450, a hash that arrives at the gate, `#search`, the seal right after a wheel scroll and Escape back, "/" from
inside the story, focus on the first heading after a keyboard stamp and the gate's last words in the status line.
Last full run with C's ports: **367 passed, 11 skipped, 0 failed** (5.7 min). `tsc --noEmit` clean, `vite build`
clean, `node --test tools/conditions-search/tests/*.test.mjs` 66 of 66.

## After the reviews: what changed, by finding

Visual review: 1 one pick for label and click (label anchored to that stack's top; hand cursor from the same
answer; GPU check: 20 of 20 labelled stacks agree, against 6 of 37 before) · 2 plates under every label, street
names beside their streets with leaders, the legend on a plate, no legend on a phone, the phone caption on its own
row, the rail on a paper strip · 3 the stack as 22 slabs, the mark on the ground, B's castle and City Hall, cards and
seats, names upright on plates · 4 the stamp lifts and leaves whole; no dome over the sheet after the slam; the
halves tip and fall in turn, the half with the mark on top · 5 the search's map fitted to its column · 6 no idle
rings in the search, one ring per change; no lean while the pointer is on a panel; no drift in the story · 7 labels
kept inside the map's window, tallies stacked, seat names left to the panel on a phone, the header steady · 8 ring
and case number at the hairline's end, the hovered stack inked and the rest stepped down, five or fewer matches
named · 9 the drawn map: heavier streets close up, the route (it was set before the map existed), the slabs and the
seats · 10 a stop between chapters is carried on; travels shortened (earlier in the day) · 11 the sub-line now adds
up · 12 one 48 px gutter for the header, the story, the search and the legend · 13 the mark lands on the ruled band;
the stamp perches there · 14 the pin (earlier) and the note in the skyline · 15 `page-c` in the HTML, the outline ·
16 a second flip is queued, Enter with nothing focused stamps, focus goes to the first heading · 17 the legend.

Performance and accessibility review: 1 chapters scroll inside their panel (sources and asides are back on phones),
with a test · 2 any change of camera or drawing keeps the scene at full rate (draw gaps above) · 3 the rail is
inert past the end · 4 status line outside the gate, focus to the chapter heading · 5 "/" and Tab into the search
go the whole way · 6 lags that have arrived snap, `setHero` uploads only on change: the scene rests · 7 the map
waits for the search's data on a direct open · 8 the search's live regions are quiet under the gate; the sheet's
title is not a heading · 9 44 px for the page links and the seal · 11 the WebGL probe after the first paint, one
context · 12 forced colours get the drawn stamp; the panel's edge is measured on layout, not per frame.

Break-it review: 1 the die is re-measured while the camera eases in · 2 the gate goes to the top through the scroll
engine and keeps the page there; a stamp always starts the story at its start; `#search` opens the search · 3
`hashchange` · 4 one pick · 5 "since January 2010", the definition sentence, "Filbert St" and the "City Hall" label
are gone · 6 commas in the vote · 7 the footer is inert under the gate · 8 "/" · 9 an early press is kept; a failed
gate script opens the story; a failed map says so · 10 a map click clears the filters; the kind of condition counts
for lighting · 11 chapters scroll; a short window takes a smaller sheet · 12 tag flips left at the edge, plates,
footer over the legend · 13 colours from tokens only (the sheet on paper is the paper itself) · 14 Escape · 15 a Space
carried from the gate into the search is not typed · 18 44 px, pinch-zoom on the gate, "(PDF, opens in a new tab)"
· 19 labels and legend hidden while the context is lost; the search fitted to the whole street outline.

Turned down or left: **V10, something to pass in the chase** (cross-street names or a distance counting up): the
street names are not in `story.json` (the review struck "Filbert St" for that reason) and a distance along the
drawn route would read as a fact of the case; the chase is shortened and a stop in it is carried on instead.
**V16, a tap of Space counts as a let-go hold**: that is `core/stamp/hold.ts` (A's); a single Enter or click stamps
at once. **B16, resizing during a glide**: `core/story/engine.ts` (B's), which now finishes a glide at its stop on a
layout change. **P6, the phone band draws a whole window**: left (see below). **P12, the flip's one long frame**:
inherent to view transitions, as the review says.

## Shared files touched

- `src/core/world/living.ts`: opt-in file (not imported by `/b/`); this pass made `setHero` upload only on change
  and gave the story's motion a pin. `src/core/world/README.md`: the section on it.
- Nothing else shared: no change to `tokens.css`, `shell.*`, `search/*`, `stamp/*`, `story/*`, `props/*`, the
  configs, the package files, `parity.spec.ts` or `search.spec.ts`. `c/index.html` and `e2e/c.spec.ts` are C's.

## Rough or unfinished (blunt)

- **The no-WebGL map is thinner than the scene**: no castle, no City Hall, no cards (the slabs, route and seats
  are drawn).
- **The phone's search band draws a full-window canvas** clipped to the band; it rests when idle, but while it
  moves it shades about three times the pixels it shows. A scissor or a band-sized canvas would fix it.
- **The mark in the story is ink on the map**: streets show through its letters, as ink on a printed map would.
- **The first frame's outline is the street data's convex hull**: a dashed polygon, not a coastline.
- **The dome lifts stacks under the pointer in the search**, so the named stack can change as the dome rises (the
  label and the click still agree, frame by frame).
- **B's text and places are copied** (`src/c/content.ts`, `places.ts`), not shared.
- **The e2e suite still runs the drawn map**, except four tests that force the scene in software.
- Chromium only, no real phone, no Safari or Firefox; no weaker graphics card.
- `sf-streets.bin` is served uncompressed by `vite preview` (83 kB with gzip against 179 kB): a host setting.

## What it would take to finish

1. One shared module for the story's text and places (B and C).
2. Label placement as a small solver rather than hand-set offsets and clamps.
3. A GPU-backed Playwright project in CI with pixel checks of the scene (dome, rings, stacks, flip).
4. A band-sized canvas (or a scissor) for the phone's search.
5. The castle and City Hall drawn as SVG line work for the no-WebGL map.
6. Safari, Firefox and a real phone; compression for the street file at the host.
