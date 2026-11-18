// The camera table: one key frame per chapter, interpolated with an eased curve during that chapter's travel and
// held still for its hold. Plain numbers in, a plain Pose out: no three.js here (../world/rig.ts applies a Pose).

import type { Pose } from "../world/rig";
import { ease, type Timeline } from "./timeline";

/** Where the camera rests for a chapter, and how it gets there. */
export interface CameraKey extends Pose {
  /** Lift the camera away in the middle of the travel to this key: the distance is multiplied by up to 1 + arc. */
  arc?: number;
  /** Tip the camera further down in the middle of the travel to this key, by up to this many degrees: a long
   *  move reads as a flight over the map. */
  rise?: number;
  /** The looked-at point during the travel to this key, for a camera that follows a path: given the eased
   *  progress (0 to 1), return the ground point. The start and end still blend from and to the two keys. */
  via?: (t: number) => { x: number; z: number };
  /** The easing of the travel to this key (default: ease in and out). */
  easing?: (t: number) => number;
}

const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;

/** The shortest way round from heading a to heading b, in degrees. */
function turn(a: number, b: number, t: number): number {
  let d = (b - a) % 360;
  if (d > 180) d -= 360;
  if (d < -180) d += 360;
  return a + d * t;
}

/** The pose at a timeline position: the chapter's key during its hold, and a blend from the previous key during
 *  its travel. `out` is filled and returned. */
export function poseAt(keys: CameraKey[], timeline: Timeline, pos: number, out: Pose): Pose {
  const where = timeline.locate(pos);
  const to = keys[where.chapter] ?? keys[keys.length - 1]!;
  const from = keys[where.chapter - 1];
  if (where.phase === "hold" || !from) return copyPose(to, out);
  const e = (to.easing ?? ease.inOut)(where.travel);
  out.tx = lerp(from.tx, to.tx, e);
  out.ty = lerp(from.ty, to.ty, e);
  out.tz = lerp(from.tz, to.tz, e);
  if (to.via) {
    // follow the path, but leave from and arrive at the keys' own targets
    const p = to.via(e);
    const blend = Math.sin(Math.PI * e) ** 0.5; // 0 at both ends, 1 through the middle
    const k = Math.min(1, blend * 1.6);
    out.tx = lerp(out.tx, p.x, k);
    out.tz = lerp(out.tz, p.z, k);
  }
  out.distance = Math.exp(lerp(Math.log(from.distance), Math.log(to.distance), e)) * (1 + (to.arc ?? 0) * Math.sin(Math.PI * e));
  out.heading = turn(from.heading, to.heading, e);
  out.pitch = lerp(from.pitch, to.pitch, e) + (to.rise ?? 0) * Math.sin(Math.PI * e);
  out.fov = lerp(from.fov, to.fov, e);
  out.shiftX = lerp(from.shiftX, to.shiftX, e);
  out.shiftY = lerp(from.shiftY, to.shiftY, e);
  return out;
}

export function copyPose(from: Pose, out: Pose): Pose {
  out.tx = from.tx;
  out.ty = from.ty;
  out.tz = from.tz;
  out.distance = from.distance;
  out.heading = from.heading;
  out.pitch = from.pitch;
  out.fov = from.fov;
  out.shiftX = from.shiftX;
  out.shiftY = from.shiftY;
  return out;
}

export function emptyPose(): Pose {
  return { tx: 0, ty: 0, tz: 0, distance: 1000, heading: 0, pitch: 55, fov: 30, shiftX: 0, shiftY: 0 };
}
