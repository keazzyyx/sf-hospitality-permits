// Where things are on this page's map (world metres: x east, z south; see core/world/projection.ts). No three.js.
// The castle's point is the planning record's own (story.json "location"). The other points are read off the
// street data, as the scroll-story prototype read them (not part of this repository): the corner nearest the castle, the block of Polk
// Street in front of City Hall, the three streets named in the second chapter. The drawing is not a survey.

import { CASTLE_PLAN, CITY_HALL_PLAN } from "../core/props/plans";
import { fromGrid, project, type Ground } from "../core/world/projection";

const pick = <T>(found: Record<string, T>): T => {
  const value = Object.values(found)[0];
  if (value === undefined) throw new Error("story.json is missing the case's location");
  return value;
};
const location = pick(import.meta.glob<{ lat: number; lon: number }>("../data/story.json", { eager: true, import: "location" }));
export const RECORD = pick(import.meta.glob<string>("../data/story.json", { eager: true, import: "record" }));

const RAD = Math.PI / 180;

/** The castle, from the planning record's coordinates. */
export const CASTLE: Ground = project(location.lon, location.lat);
/** Where Montgomery Street meets Greenwich Street: where the route starts. */
export const CASTLE_CORNER: Ground = fromGrid(2877, 5025);
/** Telegraph Hill's rise under the lines, centred on the summit loop. */
export const HILL = { x: 2795, z: -4970, radius: 330, height: 40 };
/** The block of Polk Street in front of City Hall, and its middle: where the route ends. */
export const POLK_SOUTH: Ground = fromGrid(1703, 2312);
export const POLK_NORTH: Ground = fromGrid(1670, 2509);
export const CITY_HALL_DOOR: Ground = fromGrid(1686.5, 2410.5);
/** The street grid at City Hall runs 9.5 degrees off east. */
export const CIVIC_GRID_DEG = 9.5;
/** The middle of the city's street data, for the wide shots. */
export const CITY_CENTRE: Ground = fromGrid(-136, 155);

/** A point `east` and `north` metres from an origin, along a grid turned `deg` off east. */
export function offset(origin: Ground, deg: number, east: number, north: number): Ground {
  const c = Math.cos(deg * RAD), s = Math.sin(deg * RAD);
  return { x: origin.x + east * c - north * s, z: origin.z - (east * s + north * c) };
}

/** The streets named in the second chapter, each with a point beside it for its plate and the point on the
 *  street the plate's leader runs to. Both names are in the motion's own address (story.json "address"). */
export const STREET_NAMES: { name: string; at: Ground; on: Ground }[] = [
  { name: "Greenwich St", at: fromGrid(2928, 5008), on: fromGrid(2930, 5033) },
  { name: "Montgomery St", at: fromGrid(2934, 4944), on: fromGrid(2904, 4940) },
];

/** Height of the hill under a point, fully risen. */
export function hillAt(p: Ground): number {
  const dx = p.x - HILL.x, dz = p.z - HILL.z;
  return HILL.height * Math.exp(-(dx * dx + dz * dz) / (0.36 * HILL.radius * HILL.radius));
}

// ---- the drawn objects (core/props) and the small solids of this page, placed as prototype B places its own ---------

/** The street grid on Telegraph Hill runs 9 degrees off east (Greenwich Street's bearing in the data). */
export const HILL_GRID_DEG = 9;
/** The castle is drawn a quarter larger than its plan, so it reads at the size of the drawing (it is not a survey). */
export const CASTLE_SCALE = 1.25;
/** The drawn castle's own origin (the middle of its hall): a little back from the record's point, so its front
 *  stands clear of the street. */
export const CASTLE_ORIGIN: Ground = offset(CASTLE, HILL_GRID_DEG, 0, 7.5);
/** A ground point given in the castle's own frame (x along Greenwich Street to the east, z towards the street). */
export function castleGround(lx: number, lz: number): Ground {
  return offset(CASTLE_ORIGIN, HILL_GRID_DEG, lx * CASTLE_SCALE, -lz * CASTLE_SCALE);
}
/** The level the castle's base card stands at on the risen hill: the ground at the street side of its door. */
export const CASTLE_LEVEL = hillAt(castleGround(CASTLE_PLAN.door.x - 4, CASTLE_PLAN.base.z1 - 1));

/** The drawn hall at the end of the route: in its block west of Polk Street, its steps back from the kerb. */
export const HALL: Ground = offset(CITY_HALL_DOOR, CIVIC_GRID_DEG, -(CITY_HALL_PLAN.depth / 2 + CITY_HALL_PLAN.portico + 13), 0);
/** Seven seats in a row across Polk Street from the hall: the seven votes. */
export const SEAT_SPACING = 15;
export const SEATS: Ground[] = Array.from({ length: 7 }, (_, i) => offset(CITY_HALL_DOOR, CIVIC_GRID_DEG, 40, (3 - i) * SEAT_SPACING));

/** The 22 conditions as a stack of slabs: where it stands (beside the castle, on the street's side), the size of
 *  a slab and the rise from one to the next, in metres. */
export const SLABS = { at: castleGround(-38, 19), w: 24, d: 17, thick: 2.1, pitch: 3.1 };
/** The mark, laid on the ground in front of the castle: its middle and its width in metres. */
export const MARK_GROUND = { at: castleGround(12, 72), width: 58 };
/** The letters: two rows of cards standing along the street in front of the castle. Where each row starts (its
 *  west end), the gap between cards, and a card's size. */
export const LETTER_ROWS = {
  support: castleGround(-26, 31),
  opposition: castleGround(-26, 41),
  gap: 3.3,
  card: { w: 1, h: 6.5, d: 6 },
};
