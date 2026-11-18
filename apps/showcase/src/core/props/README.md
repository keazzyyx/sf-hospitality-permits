# core/props

Drawn objects for the map of `core/world`, in the print language (paper faces, cobalt for faces in shadow, ink
outlines), built as paper pop-ups: every object takes one number, 0 (the closed book: flat on the map) to 1
(standing). Made for prototype B (not part of this repository); nothing in here knows about any page, so `/c/` can stand the same castle and City Hall
on its own world. Needs three.js: import from a page's 3D chunk. `plans.ts` alone has no three.js (the objects'
measures, for labels and for drawings made without WebGL).

```ts
import { createCastle, createTower, createCityHall, createRoads, createGround, createHachures } from "../core/props";

const castle = createCastle(world);              // origin: the middle of the hall's floor, on its base card
castle.group.position.set(x, world.heightAt(x, z), z);
castle.group.rotation.y = bearing;               // its front is +z; x runs along the street
scene.add(castle.group);
castle.setBase(castle.group.position.y);         // the level its shadow is cast from
castle.fold(t);                                  // 0 to 1, any order, any number of times (scrub it with a scroll)
```

| | |
| --- | --- |
| `createCastle(world)` | A crenellated hall, a round corner turret in three telescoping sections, a square keep and a lower wing with a roof terrace (tables, a parasol), on a base card whose walls go down 16 m to be planted in a slope. Walls hinge up from lying inwards, the roofs rise between them, the turret telescopes, the battlements flip up last. About 45 draw calls, 3,000 triangles |
| `createTower(world)` | A fluted shaft on a podium, an arcaded gallery that slides up out of it, a crown that slides out of the gallery. `setShadow(0..1)` shortens its shadow for a shot that leaves the tower out |
| `createCityHall(world)` | A facade that hinges up, the block behind it, a portico (steps, eight columns, entablature, pediment) and a dome on a colonnaded drum with a lantern. Its front is +z |
| `createRoads(world, streets, { x, z, radius })` | The streets near a point as bands of the second paper colour between two ink kerbs (an ink band under a narrower paper band, so junctions join themselves). `setWidth(0..1)`: grow them as the camera comes down |
| `createGround(world, relief)` | The ground of a rise as a paper-coloured surface: it shows nothing and hides what is under or behind the hill |
| `createHachures(world, relief, { streets, avoid })` | Pencil hachures down the slopes of a rise, clear of the streets; `setDraw(0..1)` draws them on from the top outward |

## The parts (`build.ts`)

- Geometry: `box`, `drum`, `disc`, `merge`; `plate(outline, holes)` (a flat plate cut to an outline, facing +z),
  `slab(outline, y)` (the same lying flat); outlines `rect`, `arch`, `battlement`.
- Printed parts: `card(world, geometry)` (a sheet of paper, both sides drawn), `inked(world, geometry)` (a flat
  shape filled with the line colour: a window, a door).
- The three ways a part comes up, each a `Fold` (`{ group, set(0..1) }`): `hinge(world, children, { at, yaw, from })`
  (a leaf drawn in its own plane turns up about its foot), `grow(world, children, at)` (rises from its base),
  `riser(world, children, from, to, hide)` (slides from one height to another: a floor between its walls, a section
  of a telescope). Compose them by adding one fold's group to another's.
- `castShadow(world, solid, onRelief, renderOrder)`: the flat shadow of a plain solid along the world's light, on the
  ground as the street lines know it or on a level. Give an object one shadow of plain solids its size and scale
  that with the fold, rather than a shadow per folding part.
- Eases: `settle` (arrives a little past and comes back: paper has spring), `smooth`, `span`.

## Rules kept

- Colours only from the world's shared uniforms; nothing here uses `uStamp`.
- No per-frame allocation in a `fold()` or `set()`; each returns at once when its number has not changed, and
  calls `world.invalidate()` when it has.
- The light is the world's (`world.uniforms.uLight`): a page that wants a wall lit turns the light, not the object.
