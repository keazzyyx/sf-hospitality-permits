# core/story

The scroll engine: a tall parent with a sticky stage; scroll position maps linearly to one timeline position;
everything on screen is a function of that position, so the story is fully reversible. No three.js in here.
Built for prototype B (`/b/`, not part of this repository); `/c/` uses the same module.

```ts
import { createStory, createRail, poseAt, emptyPose, range, ease } from "../core/story";

const story = createStory({
  root,                      // the tall parent (class "story-root"): the engine sets its height
  stage,                     // the sticky stage inside it (class "story-stage"; --story-top is where it sticks)
  chapters: [
    { id: "city", title: "The city", travel: 0, hold: 1 },
    { id: "address", title: "The address", travel: 0.7, hold: 1.2 },
    { id: "conditions", title: "The conditions", travel: 1, hold: 2.5, steps: 8 },
  ],
  unit: stageHeight => stageHeight,              // pixels of scroll per "screen" of the timeline
  mode: reducedMotion() ? "stills" : "scrub",
  onUpdate(state) { /* the position changed: set the camera, the drawing, the text */ },
  onFrame(now) { /* every frame, after onUpdate: tick a renderer */ },
});
stage.append(createRail(story).element);         // nine real buttons, a progress line, a previous / next pair
```

## The timeline

Chapters are laid end to end, in screens of scroll. Each has a **travel** span (the camera moves to it; no text is
on screen) and then a **hold** span (the camera is still; the text is on screen; only the drawing changes).

`story.timeline` (`buildTimeline(specs)` on its own is pure arithmetic and easy to test):

| | |
| --- | --- |
| `chapters[i]` | `{ start, holdStart, end, travel, hold, steps }` |
| `length` | total screens |
| `locate(pos)` | `{ chapter, phase: "travel" \| "hold", travel, hold }` |
| `holdAt(i, pos)`, `travelAt(i, pos)` | 0 to 1 through chapter i's hold or travel (0 before, 1 after): what a drawing change is a function of |
| `textAt(i, pos)` | 0 to 1: how much of chapter i's text shows (in after the frame moves, out before the hold ends) |
| `frameAt(i, pos)` | 0 to 1: how far the frame has moved aside for chapter i's text |
| `stepAt(i, pos)` | `{ index, t }` for a chapter with `steps` (they share 14% to 90% of the hold) |
| `stops`, `nearestStop(pos)` | where the rail and the arrow keys put a visitor: one per chapter, or one per step |

A drawing change is written as `range(timeline.holdAt(i, pos), 0.3, 0.6)` and eased with `ease.inOut`, `ease.out`,
`ease.back`. **Finish every change by `REST` (0.72 of the hold, or of a step):** that is where a stop is, and where a
reduced-motion still is taken.

## The state passed to `onUpdate`

`{ pos, progress, chapter, phase, step, still, ended, timeline, unit, scroll }`. `scroll` is the raw position in
screens; `pos` is clamped to the story (and snapped to a stop in "stills" mode).

## The camera table

```ts
const keys: CameraKey[] = [ /* one pose per chapter, plus optional arc, rise, via, easing */ ];
const pose = emptyPose();
poseAt(keys, story.timeline, state.pos, pose);   // the chapter's key during its hold; an eased blend from the
setPose(world, pose);                            // previous key during its travel (core/world/rig.ts applies it)
```

`arc` lifts the camera away in the middle of a travel, `rise` tips it down, `via(t)` makes the target follow a path
(a route along streets), `easing` replaces ease-in-out. The camera never moves inside a hold.

## Moving

`story.goTo(chapter)`, `goToStop(stop)`, `next()`, `prev()`, `toEnd()` (to where the page below the story begins;
instant unless `{ smooth: true }`), `scrollOf(pos)`, `configure({ chapters, unit })` (a layout change keeps the
visitor's place), `refresh()`, `setMode()`, `destroy()`.

Keys (while the story is on screen and the focus is not in a field): Arrow Down, Arrow Right and Page Down go to
the next stop; Arrow Up, Arrow Left and Page Up to the previous; Home to the start. Past the story's end the keys
scroll the page as usual.

## Modes

- **scrub**: wheel input is smoothed with Lenis (lerp 0.11; touch scrolling is left native); programmatic moves
  ease over 0.9 to 2.4 s.
- **stills** (reduced motion): no Lenis, no scrubbing. The state snaps to the nearest stop, `state.still` is true
  (show every drawing complete; cut, do not move), and `onUpdate` is called only when the still changes.

## The rail

`createRail(story, { label })` returns `{ element, update(state) }`: a `<nav>` with one real button per chapter
(a thin tick, the current one longer and `aria-current="step"`, named on hover and focus), a line that fills with
progress, and a previous / next pair for small touch screens (add the class `story-rail--across` to show the pair
instead of the ticks; nine ticks cannot each be 44 px wide on a phone). Styles are in `story.css`.
