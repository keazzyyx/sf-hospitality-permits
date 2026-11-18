# core/world

The paper map of San Francisco as a three.js scene: the city's real street lines, points for the motions, a camera
set by plain numbers, and objects drawn like a two-colour print. Nothing in here knows about any page. Built for
prototype B (`/b/`, not part of this repository); `/c/` stands on the same module.

Two halves:

- **No three.js** (safe to import from a page's first script): `projection.ts`, `data.ts`, `graph.ts`, `relief.ts`.
- **three.js** (import from a lazy chunk; `index.ts` re-exports everything): `world.ts`, `rig.ts`, `lines.ts`,
  `streets.ts`, `pins.ts`, `print.ts`.

## Coordinates

The data (`public/data/sf-streets.bin`, `motions.json`; see `scripts/README.md`) is in whole metres on a grid about
lon -122.4376, lat 37.7577: grid x east, grid y north. The world is y-up: **world x = grid x (east), world z = -grid y
(north is -z), world y = height in metres.** One unit is one metre.

```ts
import { project, unproject, fromGrid, formatLatLon, niceLength, formatLength } from "../core/world/projection";

project(-122.405066, 37.803029);   // { x: 2860, z: -5040 }   longitude, latitude -> ground
unproject(2860, -5040);            // { lon, lat }            the inverse (for a readout under the pointer)
fromGrid(2877, 5025);              // { x: 2877, z: -5025 }   a point given in the data's own grid
formatLatLon(37.803, -122.4051);   // "37.8030° N  122.4051° W"
niceLength(137);                   // 100: the largest of 1, 2, 5 x 10^k at most this (for a scale bar)
```

## Data

```ts
import { loadStreets, loadMotions, motionPosition, streetsPath } from "../core/world/data";

const streets = await loadStreets(sitePath("data/sf-streets.bin"));   // { count, minor, major, xy: Int16Array }
const motions = await loadMotions(sitePath("data/motions.json"));     // { points, byRecord }
motionPosition(motions.byRecord.get("2016-001273CUA"));               // its point on the street network, or null
streetsPath(streets, box, "major");                                    // an SVG path, for drawings without WebGL
```

Each URL is fetched once. 350 of the 352 motions have a place; `motionPosition` returns `null` for the other two.

## The route helper

```ts
import { streetGraph, makeRoute } from "../core/world/graph";

const graph = streetGraph(streets);            // built on first use (13,861 nodes, 19,841 edges), then kept
const route = graph.route(from, to);           // shortest path along real streets between the nearest nodes, or null
route.length;                                  // metres
route.at(0.5);                                 // the ground point half way along
route.smooth(0.5, 0.05);                       // the same without corners: a camera target
makeRoute([{ x, z }, ...]);                    // a Route from your own points
```

## The world

```ts
import { createWorld, setPose, createStreets, createPins, createSegments, printObject, FULL } from "../core/world";

const world = createWorld(canvas, { relief: [{ x, z, radius: 330, height: 40 }] });  // throws without WebGL
world.setSize(width, height);                  // CSS pixels; the pixel ratio is capped at 2 (1.5 when lowPower())
world.scene.add(createStreets(world, streets, { origin }).group);

setPose(world, { tx, ty, tz, distance, heading, pitch, fov, shiftX, shiftY });   // see "Camera"
world.invalidate();                            // something changed

// in the page's one animation frame (render on demand: nothing is drawn while nothing changes):
if (world.update(now)) world.render();
```

`World`:

| | |
| --- | --- |
| `scene`, `camera`, `renderer`, `canvas` | the three.js objects; one renderer for the life of the page |
| `uniforms` | shared uniform objects (`uPaper`, `uInk`, `uInk2`, `uLine`, `uStamp`, `uShade`, `uViewport`, `uPixelRatio`, `uRelief`, `uReliefAmount`, `uLight`): every material references the same ones |
| `setTheme({ instant? })` | reads `--paper`, `--ink`, `--ink-2`, `--line`, `--stamp` again from the CSS tokens and tweens the shared colours over 300 ms. Nothing is rebuilt. The canvas is transparent: the ground is the page's own background |
| `setRelief(amount)`, `heightAt(x, z)` | how far the ground has risen (0 to 1); the lines follow in the vertex shader |
| `invalidate()`, `update(now)`, `render()` | render on demand |
| `groundAt(px, py)` | the ground point under a canvas pixel (ray to the plane y = 0), or `null` |
| `toScreen(x, y, z, out)` | where a world point lands on the canvas, and whether it is behind the camera |
| `metresPerPixel(x, z)` | for a scale bar that is true to the camera |
| `dispose()` | |

## Camera

A pose is plain numbers (`rig.ts`), so it can be interpolated and tested without three.js:

| field | meaning |
| --- | --- |
| `tx, ty, tz` | the point looked at |
| `distance` | metres from the camera to it |
| `heading` | compass direction the camera looks in, degrees clockwise from north (0: from the south, looking north) |
| `pitch` | degrees the camera looks down from the horizon (90: straight down) |
| `fov` | vertical field of view |
| `shiftX, shiftY` | where the looked-at point sits on the canvas, as a fraction of its size from the centre (to compose a shot beside a text panel or in a band) |

`core/story` has the table that produces poses from a timeline position (`poseAt`).

## Lines

Everything that is a line is one material: instanced quads with a width in CSS pixels, static buffers, the motion
in the vertex shader.

```ts
const line = createSegments(world, { starts, ends, order, width: 3, color: "line", depthTest: true });
line.setDraw(0.4);      // sweeps through each segment's `order` (0 to 1): segments grow from their start. FULL = all
line.setFeather(0.05);  // how long each takes to grow
line.setFade(near, far) // fade with distance from the camera
line.setTone(values)    // per segment 0..1: towards a second colour, opacity, width and length
```

- `createStreets(world, streets, { origin })`: minor and major streets; `setDraw(0..1)` draws the city on outward
  from `origin`, major streets first; `setFade`, `setStrength`.
- `createPins(world, [{ x, z, height, order }])`: thin standing pins with a dot at the top; `setRise(0..1)` in
  their order; `setDim(values)` dims and lowers pins (a search result).
- Lines never write depth; with `depthTest: true` objects hide the lines behind them. Among themselves lines draw
  in `renderOrder` (streets 0 and 1, outlines 3, pins 4 and 5).

## Print objects

```ts
const tower = printObject(world, geometry, { crease: 40, shadow: "relief" });
tower.group.position.set(x, world.heightAt(x, z), z);
tower.setFill(1);   // faces filled with the line colour
```

Paper-colour faces, the shade colour for faces turned from the light (one threshold, no other lighting), an ink
outline on creases (`inkEdges`), a slightly heavier profile line round the silhouette, and an optional flat cast
shadow. Options: `crease`, `outline`, `profile`, `flat`, `fillColor`, `outlineColor`, `shadow`, `side`, `bare`.

## Rules the module keeps

- Colours only from the tokens. `--stamp` is exposed (`uStamp`) for the stamp's mark and nothing else.
- Time-based motion belongs to the caller; the world only tweens the theme.
- No per-frame allocation in `update`, `render`, `toScreen`, `groundAt` (pass `out` objects).

## The living grid (opt-in: `living.ts`)

Added for `/c/`. A separate file that nothing else in this folder imports and `index.ts` does not re-export, so a
page that does not ask for it (prototype B did not) loads none of it and draws exactly as before.

```ts
import { createLiving, createLivingStreets, createLivingLines, createStacks } from "../core/world/living";

const living = createLiving(world);                              // one set of uniforms shared by every living material
const streets = createLivingStreets(world, living, streetData);  // the whole city in one draw call
const stacks = createStacks(world, living, [{ x, z, n, order }]); // one instanced mesh + one point cloud
world.scene.add(streets.mesh, stacks.mesh, stacks.dots);

living.setPointer(x, z, sigma); living.setBulge(height, glow);   // a dome under a ground point (negative: a dent)
living.setRing(0, x, z, radius, height, width, glow);            // two rings at once (0 and 1)
living.uniforms.uTime.value = seconds;                           // the caller's clock, for the stacks' tweens
```

- **What moves is in the vertex shader** (`LIVING_PARS`: `living(xz, out glow)` = the relief + the dome + two rings,
  and how much each brightens what it lifts). Buffers are static. `living.liftAt(x, z)` is the same arithmetic in
  script, for a label or a DOM element that has to ride the ground.
- **Lines** (`createLivingLines`): `aSeg` (x1, z1, x2, z2), a kind (two widths and opacities), an order for a
  draw-on (`setDraw`); `setReveal` (the city drawn on outward from a point, with a bright front), `setSpot`
  (lines round a point brighten), `setDim`, `setFade`, `setGlow`, `setOpacities`, `setWidths`. Normal blending,
  explicit strengths: tune each theme by number.
- **Stacks** (`createStacks`): each motion is a stack of `n` lines (one stripe per line; an even tone where the
  stripes would be finer than a pixel) with a dot at its top. `setTargets(grow, tone, { delay, duration })` and
  `setOne(i, grow, tone)` upload per-instance tweens once (from, to, start, length: the shader does the easing),
  so nothing is uploaded per frame; `setWave(amount, heroGrow)` raises them in their `order`; `setHero` makes one
  stack the story's own (its width, metres per line, one line picked out, the stamp colour for its dot and a ring).
  `growOf`, `toneOf`, `heightOf` answer in script what the shader is drawing.
