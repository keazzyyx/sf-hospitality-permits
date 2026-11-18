# The rubber stamp (`src/core/stamp`)

A stamp that hangs under the cursor, a press-and-hold that drives it, the mark it leaves, and the crack through
what it stamped. Built for prototype A (not part of this repository; `src/c/gate.ts` is the worked example here); nothing in this folder knows which
page it is on, so C can mount it over another surface and B can use the mark alone.

```ts
import {
  createStamp, createHold, renderMark, crackThrough,   // the four main pieces
  createShaker, ripple, flecks,                         // what the impact does to the page
  frameOf, freshSeed, MARK_RATIO, MARK_TILT,
} from "../core/stamp";                                 // importing it brings stamp.css with it
```

Everything is drawn in code. `three` is only loaded by `createStamp` (as its own chunk, and only where a graphics
card draws WebGL); `motion` (the `mini` build, plus its `spring`) is only used by `crackThrough`.

## The pieces

### `createStamp(stage, options): Stamp`

The stamp as an actor. `stage` is any positioned element; the stamp adds its layers to it (they fill it, sit on
top of what is already there, and take no pointer events). All positions are **CSS pixels of the stage**, and the
point you give is where the centre of the die would touch the page: the stamp is drawn above that point by its
height, and its shadow under it.

```ts
const stamp = createStamp(stage, { dieWidth: 300 });   // the die, and so the mark, is 300 px wide
stamp.place(x, y);       // put it somewhere at once
stamp.show();            // it starts hidden: fade it in
stamp.moveTo(x, y);      // follow this point with a 75 ms lag (third argument: another lag, in seconds)
await stamp.arrive();    // resolves when it has got there
```

| Option | Default | |
| --- | --- | --- |
| `dieWidth` | required | width of the die in CSS px; everything scales with it |
| `tilt` | `MARK_TILT` (-7) | degrees the die is turned on the page; pass the same to `renderMark` |
| `lines` | `["APPROVED", "WITH CONDITIONS"]` | the words on the die's face and on the mount's label |
| `webgl` | `true` | `false`: the drawn (SVG) stamp only. With `true` the three.js stamp is used only where `hardwareWebGL()` is true |
| `hover` | `0.3 * dieWidth` | height above the page while it hangs |
| `pressed` | `0.14 * dieWidth` | height at full pressure: what is left for it to drop |
| `patience` | `700` | ms to wait for the three.js chunk before the drawn stamp shows instead (it is swapped in later with a 300 ms cross-fade, never in the middle of a press). `0`: the drawn stamp at once |
| `after` | none | a promise: the three.js chunk is not asked for until it settles (the page's own data, say), and then in idle time. A (`gate.ts`) passes the search's `ready`, so three.js never competes with the first paint |
| `onKind` | none | called with `"2d"` or `"3d"` whenever the picture on the stage changes (also when a lost WebGL context hands the stage back to the drawn stamp) |

| Method | |
| --- | --- |
| `place(x, y)`, `moveTo(x, y, lag?)`, `arrive()` | position: at once, followed with a lag, and a promise for "it is there" |
| `show(visible?)` | fade in or out |
| `stand(onPage)` | `true`: standing on the page (no bob, no lean); `false`: hanging in the air (the default) |
| `press(p)` | pressure 0 to 1 lowers it from `hover` to `pressed`; call it on every frame of a hold |
| `release()` | the pressure is gone: it springs back up |
| `slam(onContact?, rise?)` | winds up (rises `rise` px, default `0.095 * dieWidth`, in 90 ms; pass 0 for none) and drops the rest of the way under gravity: with the defaults a fall of about 72 px in 130 ms. `onContact` runs **in the frame the die meets the page, before that frame is drawn**: place the mark there. The stamp squashes about 20% and stays down until `lift()` |
| `lift(to?)` | come up off the page after a slam. With `to` (a height in px) it rises straight up to that height from rest, a little nearer the viewer (`pose.zoom`), and hangs there clear of the mark until it is next pressed or stood down |
| `tap(onTouch?)` | a light tap and back up (drumming, dabbing an ink pad); only while it is hanging |
| `freeze(ms)` | hit-stop: nothing moves and no frame callback runs for `ms` |
| `lie(down)` | lie on its back (the inked face shows), or get up |
| `onFrame(cb)` | `cb(dt, pose, now)` on every frame that advances, before it is drawn; returns the function that removes it. Use it for anything that must move in step with the stamp (a parallax, a shaker) and so stop with it in a hit-stop. A callback that returns `false` says "nothing of mine is moving": when every callback says so and the stamp is at rest, the loop sleeps (a callback that returns nothing keeps it awake, as before) |
| `wake()` | start the loop again if it is asleep (when something of your own starts moving without the stamp being told anything) |
| `resize(dieWidth?)` | the stage or the die changed size |
| `destroy()` | removes the layers, the loop and (three.js) the WebGL context |
| `ready`, `kind`, `pose`, `down` | a promise for `"3d"` or `"2d"` once a picture is showing; which one it is now; the pose (`x, y, h, leanX, leanZ, squash, lying, alpha, zoom`); true between contact and lift |

One `requestAnimationFrame` loop, stepped by time. It draws only when the pose changes (a third of the frame rate
while only the hover bob moves; the bob itself rests after ten seconds with nothing asked of the stamp), sleeps
altogether when nothing can change (a stamp standing on its pad, a reduced-motion page), and stops while the tab
is hidden. A theme change (`themechange` on `window`) eases the colours in the shaders over 300 ms; nothing is
rebuilt.

The stamp is one shape (`shape.ts`: lathe handle with its turned grooves, bevelled mount with two screw heads,
rubber die, the light) drawn two ways: `stamp3d.ts` (three.js: two-step toon shading, a canvas no bigger than the
stamp that follows it, pixel ratio capped at 2, or 1.5 on a low-power device, the default GPU) and `stamp2d.ts`
(the same shape projected to SVG in code, standing and lying). About 1,850 triangles, outlines included.

- **Outlines.** The two boxes (die, mount) are outlined by an inverted hull. The handle is concave, where an
  inverted hull leaves gaps and stray slivers, so it is outlined another way: the handle marks the stencil buffer
  where it shows, and an expanded copy pulled a hair toward the viewer is inked wherever the handle is not. That
  is its silhouette against everything behind it (the mount's top included) and nothing inside it, as in the SVG.
- **The shadow** is drawn, not shaded: a flat shape with hard edges, hatched in `--stamp-shadow` (the line
  colour). Height reads from its offset, its size, and its hatching, which opens up and thins out as the stamp
  rises; a stamp standing on something throws none.
- **A lost WebGL context** hands the stage back to the drawn stamp for good (`onKind("2d")`); nothing is logged.
- **Forced colours:** the drawn stamp keeps its lines and gives up its tones (`stamp.css`). Pass `webgl: false`
  there (A does), since the three.js stamp cannot follow the system colours.

### `createHold(target, options): Hold`

Press and hold as one number.

```ts
const hold = createHold(desk, {
  duration: 1200,                 // ms from nothing to complete
  button,                         // the real <button>: Space or Enter held on it charges too
  globalSpace: true,              // and Space held with nothing focused
  ignore: "a, button, input",     // presses that start on these are left alone
  enabled: () => idle,
  onStart({ source, point, progress }) {},   // point: where the pointer went down (client px), null for a key
  onProgress(p) {},               // every frame of a hold, 0 to 1
  onComplete({ source, point }) {},          // reached 1, the press may still be down
  onCancel({ progress, count }) {},          // let go early; count = how many times so far
  onTap({ source }) {},           // a single press that was never a hold: do the whole act at once
});
```

- Letting go early cancels; pressing again within `resume` ms (500) starts from the progress that was kept, which
  drains to nothing over that half second.
- **Holding is never the only way.** A press on `button` shorter than `tap` ms (250), with a key or a pointer, and
  a click on it that came from no pointer at all (a screen reader, `element.click()`), call `onTap`.
- After `onComplete` or `onTap` the hold is spent until `reset()`. `abort()` drops a hold in progress without the
  cancel callback; `destroy()` removes every listener.
- **A key that is still down when the hold completes is swallowed until it comes up** (capture phase, on
  `window`): Space and Enter, repeats included, never reach whatever takes the focus next (a search field would
  be typed over). `hold.keyHeld` says so. The guard outlives `destroy()` and ends with the key or the window's
  blur.
- A second finger lets go of a pointer hold (the visitor is pinching): give the target `touch-action: pinch-zoom`
  (or `none`), and `user-select: none` where a finger does the holding.

### `renderMark(host, options): Mark`

The mark as one inline SVG: two lines in the stamp face inside a double rule, in `--stamp`, with worn ink (a
wobbling edge, a thin bleed, grain, missing patches, heavier at one end). The small second line is worn less (its
own filter: no patches, never lighter than about four fifths), so it can be read. The seed decides the wear.
`MARK_TYPE` gives the sizes and baselines of the two lines (the die's face is lettered from the same numbers).

```ts
const mark = renderMark(sheet, { seed: freshSeed(), width: 300 });   // height = width * MARK_RATIO
mark.el.style.left = `${x}px`;    // .stamp-mark centres itself on its left/top and turns by its tilt
mark.el.style.top = `${y}px`;
```

Options: `lines`, `seed`, `width`, `tilt`, `wear` (`"full"`, `"light"` for a small copy such as a seal, `"none"`),
`label` (what a screen reader calls it; default "Stamped: " and the words; `""` hides it). The host must be
positioned. The mark's `transform` is left free for whoever animates it.

### `crackThrough(element, point, options): Crack`

A jagged line through `point` (the element's own pixels) to two edges of the element (long, nearly straight runs
broken by short sharp jogs), drawn as a dark gap that is widest at the point and a hair at the edges, with two or
three fine branches, growing outward from the point in both directions; then the element in two halves that pull
apart and fall away with a few shards.

```ts
const crack = crackThrough(sheet, { x, y }, { seed, angle: -16, bleed: 28 });
await crack.draw(300);                       // the line runs out from the point
await crack.open({ onPart() { reveal(); } }); // halves jump apart (springs), then fall; resolves when gone
```

- The element must be absolutely positioned and take its rotation from the CSS `rotate` property (not
  `transform`). It is hidden (`visibility`), not removed; `destroy(true)` shows it again.
- The halves are copies of the element (`cloneNode`), each clipped with `clip-path: polygon(...)`, in a box put
  right after it. Ids inside the copies are renamed, and `inert` is set on them. `bleed` keeps what overhangs
  the element's box (pages underneath, flecks).
- `crack.line` and `crack.normal` are there for things that should come out of the crack; `crackLine(w, h,
  point, options)` gives the line alone.
- More options: `strip` (a selector for things the copies should not carry), `edge: true` (ink the torn edge of
  each half once the box has the class `is-parted`; `open()` adds it), `keep: true` (leave the element showing
  under its halves at `split()`, so the cut cannot be seen before they move: hide it yourself when they do).
  `crack.erase()` takes the drawn line away. After `split()`, `draw()` draws over the halves. A copy restarts no
  CSS animation of the flecks.
- A (`gate.ts`) cracks its whole desk this way: `split()` early with `keep`, `draw()`, then its own slide of the
  two halves. The colour of the gap is `--stamp-crack` (and `--stamp-crack-edge`, a lip of light on a dark
  ground).

### Impact: `createShaker`, `ripple`, `flecks`

```ts
const shaker = createShaker(stageEl);        // stiffness 500, damping 12: a kick is gone in about 400 ms
stamp.onFrame((dt, _pose, now) => shaker.step(dt, now));
shaker.rumble(p * p * 1.5);                  // the tremble under a hold, in px
shaker.kick(0, 230, 5);                      // at contact: px/s across, px/s down, degrees/s
await ripple(layer, x, y, { radius: 600 });  // a ring through `layer`, which carries the ground's own lines
flecks(sheet, x, y, { seed, width: 300, height: 300 * MARK_RATIO, tilt: MARK_TILT });
```

`ripple` needs a layer of your own over the ground with the ground's lines drawn a little stronger (A: the
graph-paper grid; prototype A drew it with `.gate__ripple`, not part of this repository); the class `stamp-ripple` masks it to a ring. The shaken
element must have no transform of its own.

### Small things

- `frameOf(el)`: where an element's own pixels are on the screen (`toClient`, `toLocal`, `angle`, `scale`),
  whatever rotates or shifts it or its ancestors. Use it to turn a pointer position into a point of the sheet.
- `hardwareWebGL()`: false under a software renderer (SwiftShader, llvmpipe); the stamp then draws in SVG.
- `rng(seed)`, `between(r, lo, hi)`, `freshSeed()`; `Spring`, `follow(current, target, dt, tau)`, `clamp`, `lerp`.

## The order of a stamping (what A does)

```ts
onStart:     aim; stamp.moveTo(target, 0.06)
onProgress:  stamp.press(p); shaker.rumble(p * p * 1.5); your own gauge, dent, blur
onCancel:    stamp.release(); undo your effects over about 300 ms
onComplete:  await stamp.slam(() => {        // wind-up, fall, then the contact frame
               renderMark(...); flecks(...);
               shaker.kick(±50, 250, ±8); stamp.freeze(80);   // hit-stop: 80 ms
             });
             wait 260 ms                     // the weight rests
             stamp.lift(die * 0.92)          // straight up, clear of the mark
             wait about 740 ms               // nothing moves: the mark is read (make the halves ready here)
             stamp.stand(true); stamp.moveTo(home)            // home while the crack runs
             await crack.draw(320); then part the halves
```

## Colours

`stamp.css` defines them from the theme tokens; override on any ancestor of the stage.

| Variable | Paper | Blueprint |
| --- | --- | --- |
| `--stamp-lit` (faces in the light) | `--paper` | `--line` |
| `--stamp-shade` (faces in shadow) | `--line` | paper with a little cobalt |
| `--stamp-outline` | `--ink` | `--ink` |
| `--stamp-detail` (creases, grooves, the label's letters) | `--ink` | `--paper` |
| `--stamp-rubber`, `--stamp-rubber-shade`, `--stamp-relief` | `--stamp` and darker mixes | the same |
| `--stamp-shadow`, `--stamp-shadow-alpha` (the hatching) | `--line`, 0.42 | `--line`, 0.34 |
| `--stamp-crack`, `--stamp-crack-edge` | `--ink`, none | `--paper`, a dim lip of `--ink` |
| `--stamp-blend` (how the mark sits on the page) | `multiply` | `normal` |
| `--stamp-paper` (the shards of a cracked thing) | `--paper` | `--paper` |

## Reduced motion

This folder does not decide for you. A (see `gate.ts`) does not create a hold at all under reduced motion: it
places the drawn stamp standing (`webgl: false`, `stand(true)`), and one press fades the mark in. The flecks'
fly-out is already switched off by `prefers-reduced-motion` in `stamp.css`.
