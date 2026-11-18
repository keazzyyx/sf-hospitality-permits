// The camera as arithmetic (no three.js): where a world point lands on the screen for a pose, exactly as
// core/world/rig.ts puts the camera. The motion sheet is laid on the ground with this on the first paint, before
// the 3D chunk has loaded, and the drawing made without WebGL is projected with it.

import type { Pose } from "../core/world/rig";

const RAD = Math.PI / 180;

export interface Projector {
  /** A world point as a point of the window (CSS pixels); `behind` when it is behind the camera. */
  (x: number, y: number, z: number, out: { x: number; y: number; behind: boolean }): { x: number; y: number; behind: boolean };
}

export function projector(pose: Pose, width: number, height: number): Projector {
  const h = pose.heading * RAD;
  const p = Math.min(89.9, Math.max(1, pose.pitch)) * RAD;
  // forward, right and up of the camera
  const fx = Math.sin(h) * Math.cos(p), fy = -Math.sin(p), fz = -Math.cos(h) * Math.cos(p);
  const cx = pose.tx - fx * pose.distance, cy = pose.ty - fy * pose.distance, cz = pose.tz - fz * pose.distance;
  // right = forward x up(0,1,0), normalised; up' = right x forward
  let rx = -fz, rz = fx;
  const rl = Math.hypot(rx, rz) || 1;
  rx /= rl;
  rz /= rl;
  const ux = -rz * fy, uy = rz * fx - rx * fz, uz = rx * fy;
  const t = Math.tan((pose.fov * RAD) / 2);
  const aspect = width / height;
  return (x, y, z, out) => {
    const vx = x - cx, vy = y - cy, vz = z - cz;
    const depth = vx * fx + vy * fy + vz * fz;
    const sx = vx * rx + vz * rz;
    const sy = vx * ux + vy * uy + vz * uz;
    out.behind = depth <= 1e-3;
    const d = out.behind ? 1e-3 : depth;
    out.x = (sx / (d * t * aspect) * 0.5 + 0.5 + pose.shiftX) * width;
    out.y = (-sy / (d * t) * 0.5 + 0.5 + pose.shiftY) * height;
    return out;
  };
}

/** A 3 by 3 homography, row-major: local (x, y) to the screen. */
export type Homography = [number, number, number, number, number, number, number, number, number];

/** The homography that takes a `w` by `h` rectangle to four screen points (top left, top right, bottom right,
 *  bottom left). */
export function quadHomography(w: number, h: number, q: readonly { x: number; y: number }[]): Homography {
  const [p0, p1, p2, p3] = q as [{ x: number; y: number }, { x: number; y: number }, { x: number; y: number }, { x: number; y: number }];
  const dx1 = p1.x - p2.x, dx2 = p3.x - p2.x, dx3 = p0.x - p1.x + p2.x - p3.x;
  const dy1 = p1.y - p2.y, dy2 = p3.y - p2.y, dy3 = p0.y - p1.y + p2.y - p3.y;
  const den = dx1 * dy2 - dx2 * dy1 || 1e-9;
  const g = (dx3 * dy2 - dx2 * dy3) / den;
  const k = (dx1 * dy3 - dx3 * dy1) / den;
  const a = p1.x - p0.x + g * p1.x, b = p3.x - p0.x + k * p3.x, c = p0.x;
  const d = p1.y - p0.y + g * p1.y, e = p3.y - p0.y + k * p3.y, f = p0.y;
  return [a / w, b / h, c, d / w, e / h, f, g / w, k / h, 1];
}

/** The homography as a CSS transform (the element's transform-origin must be 0 0). */
export function matrix3d(m: Homography): string {
  const n = (v: number): string => (Math.abs(v) < 1e-12 ? "0" : v.toPrecision(9));
  return `matrix3d(${n(m[0])},${n(m[3])},0,${n(m[6])},${n(m[1])},${n(m[4])},0,${n(m[7])},0,0,1,0,${n(m[2])},${n(m[5])},0,1)`;
}

/** A local point through a homography. */
export function applyH(m: Homography, x: number, y: number): { x: number; y: number } {
  const w = m[6] * x + m[7] * y + m[8];
  return { x: (m[0] * x + m[1] * y + m[2]) / w, y: (m[3] * x + m[4] * y + m[5]) / w };
}

/** The inverse homography (screen to local). */
export function invertH(m: Homography): Homography {
  const [a, b, c, d, e, f, g, h, i] = m;
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
  const det = a * A + b * B + c * C || 1e-12;
  return [A / det, -(b * i - c * h) / det, (b * f - c * e) / det, B / det, (a * i - c * g) / det, -(a * f - c * d) / det, C / det, -(a * h - b * g) / det, (a * e - b * d) / det];
}
