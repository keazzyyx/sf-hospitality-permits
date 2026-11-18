// The stamp's shape, once: a turned wooden handle, a wooden mount, a rubber die. Both renderers read it (the
// three.js one builds geometry from it, the SVG one projects it), so the drawn stamp and the 3D stamp agree.
//
// Units are the die's own: the die is DIE.width wide, and everything scales with it. Axes: x to the right, y up
// (the stamp's axis), z toward the viewer along the page. The origin is the centre of the die's face.

import { MARK_BOX } from "./mark";

/** How high the camera looks down from, in radians above the page. */
export const ELEVATION = (52 * Math.PI) / 180;
const SE = Math.sin(ELEVATION);
const CE = Math.cos(ELEVATION);

/** The rubber die: its face is exactly the mark. */
export const DIE = { width: MARK_BOX.width, depth: MARK_BOX.height, height: 13 } as const;
/** The wooden mount on top of the die. `bevel` is how far the top edge is cut back. */
export const MOUNT = { width: DIE.width + 6, depth: DIE.depth + 6, height: 40, bevel: 7 } as const;
/** Height of the top of the mount: where the handle stands. */
export const MOUNT_TOP = DIE.height + MOUNT.height;

/**
 * The handle's profile, as [radius, height above the mount] from its foot to the top of the knob: a foot ring, a
 * waist, a knob.
 */
export const HANDLE: readonly (readonly [number, number])[] = [
  [49.2, 0],
  [49.2, 7],
  [45.6, 11],
  [37.2, 18],
  [28.8, 29],
  [22.8, 44],
  [19.8, 62],
  [19.2, 82],
  [21, 101],
  [26.4, 119],
  [34.2, 135],
  [40.2, 150],
  [42.6, 164],
  [41.4, 177],
  [36, 188],
  [26.4, 196],
  [13.2, 200.5],
  [0, 201.5],
];
/** Heights (above the mount) of the two grooves turned into the handle, drawn as ink lines. */
export const GROOVES = [9, 122] as const;
/** Finer lines turned beside them (a second ring at the foot, one under the knob, one round its widest part). */
export const GROOVES_FINE = [14.5, 127.5, 166] as const;
/** The two brass screws that hold the handle's plate to the mount: [x, z] on the mount's top, and their radius. */
export const SCREWS = { at: [[-112, 0], [112, 0]] as const, radius: 6.2, slot: 26 } as const;
/** The whole stamp's height, die face to the top of the knob. */
export const STAMP_HEIGHT = MOUNT_TOP + 201.5;

/** Where the light comes from (a unit vector in view space: x right, y up the screen, z toward the viewer). */
export const LIGHT = normalize([-0.6, 0.56, 0.57]);
/** A face is lit when normal·LIGHT is above this. */
export const TONE_THRESHOLD = 0;

function normalize(v: [number, number, number]): [number, number, number] {
  const l = Math.hypot(v[0], v[1], v[2]);
  return [v[0] / l, v[1] / l, v[2] / l];
}

/** A point on the screen relative to where the die's centre touches the page (x right, y down), in die units. */
export interface Flat {
  x: number;
  y: number;
}

/**
 * Project a point of the stamp to the screen: turned by `yaw` about its own axis (radians, the mark's tilt on the
 * page: negative rises to the right), then seen from ELEVATION.
 */
export function project(x: number, y: number, z: number, yaw: number): Flat {
  const c = Math.cos(yaw);
  const s = Math.sin(yaw);
  const px = x * c - z * s;
  const pz = x * s + z * c;
  return { x: px, y: pz * SE - y * CE };
}

/** A direction of the stamp in view space (x right, y up the screen, z toward the viewer), for shading. */
export function toView(x: number, y: number, z: number, yaw: number): [number, number, number] {
  const c = Math.cos(yaw);
  const s = Math.sin(yaw);
  const px = x * c - z * s;
  const pz = x * s + z * c;
  return [px, y * CE - pz * SE, y * SE + pz * CE];
}

/** True when a face with this normal (in the stamp's axes) catches the light. */
export function lit(nx: number, ny: number, nz: number, yaw: number): boolean {
  const v = toView(nx, ny, nz, yaw);
  return v[0] * LIGHT[0] + v[1] * LIGHT[1] + v[2] * LIGHT[2] > TONE_THRESHOLD;
}

/** How much shorter a length along the stamp's axis looks on the screen, and a depth along the page. */
export const FORESHORTEN = { up: CE, depth: SE } as const;
