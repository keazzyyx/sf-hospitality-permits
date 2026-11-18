// The camera's resting places that do not belong to the story (the gate, the search), and the motion sheet as a
// rectangle on the ground. Plain numbers, no three.js: the first paint lays the sheet with these.

import type { Pose } from "../core/world/rig";
import type { Ground } from "../core/world/projection";
import { CASTLE } from "./places";
import { projector } from "./project";

const RAD = Math.PI / 180;

/** The sheet's own size in CSS pixels, before it is laid on the ground. */
export const SHEET_W = 560;
export const SHEET_H = 724;
/** Where on the sheet the mark goes when nobody pointed, and so where the castle's own point is under it. */
export const SHEET_ANCHOR = { x: 0.57, y: 0.555 };
/** How far the sheet is turned on the ground from square to the camera, in degrees. */
export const SHEET_TURN = -5;

export interface View {
  /** The window, in CSS pixels. */
  w: number;
  h: number;
  /** Height of the page's header. */
  top: number;
  /** A wide window (the text sits beside the map) or a tall one (a phone: the text sits below it). */
  wide: boolean;
}

export function measureView(top: number): View {
  // the page's own box: a classic scroll bar is not part of it
  const w = document.documentElement.clientWidth || window.innerWidth, h = window.innerHeight;
  return { w, h, top, wide: w >= 900 && w > h * 1.05 };
}

const ahead = (heading: number, metres: number): Ground => ({ x: CASTLE.x + Math.sin(heading * RAD) * metres, z: CASTLE.z - Math.cos(heading * RAD) * metres });

/** The opening: from over the bay, looking south-west across the whole city, Telegraph Hill in the foreground.
 *  The picture is moved so that the motion sheet lying at the castle sits between the header and the button. */
export function gatePose(view: View): Pose {
  let pose: Pose;
  if (view.wide) {
    const heading = 214;
    const t = ahead(heading, 2900);
    pose = { tx: t.x, ty: 0, tz: t.z, distance: 21600 * Math.max(1, (1.55 * view.h) / view.w), heading, pitch: 50, fov: 30, shiftX: -0.02, shiftY: -0.015 };
  } else {
    const heading = 208;
    const t = ahead(heading, 2500);
    pose = { tx: t.x, ty: 0, tz: t.z, distance: 23500, heading, pitch: 53, fov: 30, shiftX: 0.08, shiftY: 0.02 };
  }
  const corners = sheetCorners(pose, view, sheetWidthPx(view));
  const P = projector(pose, view.w, view.h);
  const out = { x: 0, y: 0, behind: false };
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const c of corners) {
    P(c.x, 0, c.z, out);
    x0 = Math.min(x0, out.x);
    x1 = Math.max(x1, out.x);
    y0 = Math.min(y0, out.y);
    y1 = Math.max(y1, out.y);
  }
  // just over the button at the foot of the window, the city spread out above it (and never under the header)
  const bottom = view.h - GATE_FOOT;
  pose.shiftY += (Math.max(view.top + 20 + (y1 - y0), bottom) - y1) / view.h;
  if (!view.wide) pose.shiftX += (view.w / 2 - (x0 + x1) / 2) / view.w;
  return pose;
}
/** The room the button takes at the foot of the gate, with a margin over it. */
const GATE_FOOT = 22 + 44 + 26;

/** The outline of the city's streets (their convex hull, in the data's own grid: x east, y north), for framing. */
const CITY_HULL: [number, number][] = [
  [-6683, 2334], [-6119, -2788], [-6054, -3311], [-5336, -5504], [-2456, -5613], [2207, -5524], [3883, -5482], [4912, -5390],
  [6411, -3234], [6021, -1837], [4358, 3495], [3153, 5145], [2679, 5525], [1629, 5924], [-3429, 5891], [-6433, 2709],
];

/** The search: a calm high view, north up, the whole city fitted to the part of the window the panel leaves free,
 *  with a margin all round (room for the caption above and the legend below, and for the lean toward the pointer). */
export function searchPose(view: View, free: { x: number; y: number; w: number; h: number }): Pose {
  const fov = 28;
  // a tall column has height to spare: the view looks further down, so the city is drawn deeper
  const pitch = view.wide ? clampTo(52 + 30 * (free.h / Math.max(1, free.w) - 0.9), 52, 74) : 50;
  // (the stacks stand up to about 40 px over the ground: room is left above it for them)
  const m = view.wide ? { l: 30, r: 30, t: 64, b: 70 } : { l: 12, r: 12, t: 40, b: 8 };
  const W = Math.max(60, free.w - m.l - m.r), H = Math.max(60, free.h - m.t - m.b);
  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  for (const [x, y] of CITY_HULL) {
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minZ = Math.min(minZ, -y);
    maxZ = Math.max(maxZ, -y);
  }
  const pose: Pose = { tx: (minX + maxX) / 2, ty: 0, tz: (minZ + maxZ) / 2, distance: 30000, heading: 0, pitch, fov, shiftX: 0, shiftY: 0 };
  const out = { x: 0, y: 0, behind: false };
  const box = { x0: 0, x1: 0, y0: 0, y1: 0 };
  const measure = (): void => {
    const P = projector(pose, view.w, view.h);
    box.x0 = box.y0 = Infinity;
    box.x1 = box.y1 = -Infinity;
    for (const [x, y] of CITY_HULL) {
      P(x, 0, -y, out);
      box.x0 = Math.min(box.x0, out.x);
      box.x1 = Math.max(box.x1, out.x);
      box.y0 = Math.min(box.y0, out.y);
      box.y1 = Math.max(box.y1, out.y);
    }
  };
  for (let i = 0; i < 5; i++) {
    measure();
    pose.distance *= Math.max((box.x1 - box.x0) / W, (box.y1 - box.y0) / H);
  }
  measure();
  // the outline's middle on the screen goes to the middle of the free part (a shift is a move of the picture)
  pose.shiftX = (free.x + m.l + W / 2 - (box.x0 + box.x1) / 2) / view.w;
  pose.shiftY = (free.y + m.t + H / 2 - (box.y0 + box.y1) / 2) / view.h;
  return pose;
}
const clampTo = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));

/** The city's outline as the camera sees it, as an SVG path in window pixels: the first paint draws it so the
 *  ground is there before the streets draw on. */
export function cityOutline(pose: Pose, view: View): string {
  const P = projector(pose, view.w, view.h);
  const pts = CITY_HULL.map(([x, y]) => {
    const o = P(x, 0, -y, { x: 0, y: 0, behind: false });
    return { x: o.x, y: o.y };
  });
  // each edge cut to the window (Liang and Barsky): nothing of the drawing lies outside it
  let d = "";
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i]!, b = pts[(i + 1) % pts.length]!;
    let t0 = 0, t1 = 1;
    const dx = b.x - a.x, dy = b.y - a.y;
    let inside = true;
    for (const [p, q] of [[-dx, a.x], [dx, view.w - a.x], [-dy, a.y], [dy, view.h - a.y]] as const) {
      if (p === 0) {
        if (q < 0) inside = false;
        continue;
      }
      const r = q / p;
      if (p < 0) t0 = Math.max(t0, r);
      else t1 = Math.min(t1, r);
    }
    if (!inside || t0 > t1) continue;
    d += `M${(a.x + dx * t0).toFixed(1)} ${(a.y + dy * t0).toFixed(1)}L${(a.x + dx * t1).toFixed(1)} ${(a.y + dy * t1).toFixed(1)}`;
  }
  return d;
}

/** The sheet's four corners on the ground (top left, top right, bottom right, bottom left), for a pose: it lies
 *  with its top away from the camera, a little turned, the castle's point under its anchor, and is as wide on
 *  the screen as `widthPx` at the castle. */
export function sheetCorners(pose: Pose, view: View, widthPx: number): Ground[] {
  const P = projector(pose, view.w, view.h);
  const a = P(CASTLE.x, 0, CASTLE.z, { x: 0, y: 0, behind: false });
  const h = (pose.heading + SHEET_TURN) * RAD;
  const up = { x: Math.sin(h), z: -Math.cos(h) };
  const right = { x: Math.cos(h), z: Math.sin(h) };
  const b = P(CASTLE.x + right.x * 100, 0, CASTLE.z + right.z * 100, { x: 0, y: 0, behind: false });
  const pxPer100 = Math.hypot(b.x - a.x, b.y - a.y) || 1;
  const W = (widthPx / pxPer100) * 100;
  const H = (W * SHEET_H) / SHEET_W;
  const tl = { x: CASTLE.x - right.x * W * SHEET_ANCHOR.x + up.x * H * SHEET_ANCHOR.y, z: CASTLE.z - right.z * W * SHEET_ANCHOR.x + up.z * H * SHEET_ANCHOR.y };
  const tr = { x: tl.x + right.x * W, z: tl.z + right.z * W };
  const br = { x: tr.x - up.x * H, z: tr.z - up.z * H };
  const bl = { x: tl.x - up.x * H, z: tl.z - up.z * H };
  return [tl, tr, br, bl];
}

/** How wide the sheet is on the screen (at the castle), for a window. */
export function sheetWidthPx(view: View): number {
  // (a short window takes a smaller sheet: it lies between the header and the button, about 1.15 times as tall
  // on the screen as it is wide)
  const fit = (view.h - view.top - 20 - GATE_FOOT) / 1.15;
  return Math.max(150, Math.min(view.wide ? Math.min(470, Math.max(330, view.w * 0.31)) : Math.min(380, view.w * 0.8), fit));
}

/** The shortest way round from heading a to heading b, in degrees. */
function turn(a: number, b: number, t: number): number {
  let d = (b - a) % 360;
  if (d > 180) d -= 360;
  if (d < -180) d += 360;
  return a + d * t;
}

/** A pose between two poses (the distance on a log scale, the heading the short way round). */
export function mixPose(a: Pose, b: Pose, t: number, out: Pose): Pose {
  out.tx = a.tx + (b.tx - a.tx) * t;
  out.ty = a.ty + (b.ty - a.ty) * t;
  out.tz = a.tz + (b.tz - a.tz) * t;
  out.distance = Math.exp(Math.log(a.distance) + (Math.log(b.distance) - Math.log(a.distance)) * t);
  out.heading = turn(a.heading, b.heading, t);
  out.pitch = a.pitch + (b.pitch - a.pitch) * t;
  out.fov = a.fov + (b.fov - a.fov) * t;
  out.shiftX = a.shiftX + (b.shiftX - a.shiftX) * t;
  out.shiftY = a.shiftY + (b.shiftY - a.shiftY) * t;
  return out;
}
