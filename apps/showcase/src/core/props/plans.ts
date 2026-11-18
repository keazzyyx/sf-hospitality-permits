// The measures of the drawn objects, in metres, each in its object's own frame. No three.js here, so a page's
// first script (labels, a drawing made without WebGL) can read them.

/** The castle: x along the street (east), y up, z towards the street. The origin is the middle of the hall's
 *  floor, on top of the base card. */
export const CASTLE_PLAN = {
  hall: { w: 26, d: 16, h: 15 },
  wing: { x0: 13, x1: 29, z0: -4, z1: 8, h: 8.5 },
  turret: { x: -13, z: 8, r: 5, h: 32 },
  keep: { x0: 4, x1: 13, z0: -8, z1: 0, h: 22 },
  // the base card stops just past the wing's east wall: a longer one reads as a platform, not as a building's foot
  base: { x0: -20, x1: 31.4, z0: -12, z1: 13.4, depth: 16 },
  /** The middle of the door's sill, and its size. */
  door: { x: 3.4, z: 8, w: 3.4, h: 5.6 },
} as const;

/** The tower: a round shaft on a square podium. */
export const TOWER_PLAN = { height: 58, radius: 8.6, podium: 30 } as const;

/** The civic hall: x along the facade, y up, z out of the front door. The origin is the middle of its floor. */
export const CITY_HALL_PLAN = { width: 108, depth: 70, height: 22, top: 82, portico: 9 } as const;
