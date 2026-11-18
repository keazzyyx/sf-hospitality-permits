// Loads the two data files the world is drawn from. No three.js here.

import { fromGrid, type Ground } from "./projection";

/** San Francisco's street centrelines as independent segments (public/data/sf-streets.bin). */
export interface Streets {
  /** Number of segments. */
  count: number;
  /** Minor streets are segments [0, minor); major streets are [minor, count). */
  minor: number;
  major: number;
  /** x1, y1, x2, y2 per segment in grid metres (x east, y north). */
  xy: Int16Array;
}

/** One Planning Commission motion on the map (public/data/motions.json "points"). */
export interface MotionPoint {
  record: string;
  address: string;
  business: string;
  zoning: string;
  /** ISO date the planning record closed. */
  decided: string;
  year: number;
  /** Number of conditions in the motion. */
  n: number;
  /** The address point in grid metres, or null when the motion could not be located. */
  x: number | null;
  y: number | null;
  /** The nearest point on the drawn street network. */
  sx: number | null;
  sy: number | null;
}

export interface Motions {
  points: MotionPoint[];
  byRecord: Map<string, MotionPoint>;
}

const cache = new Map<string, Promise<unknown>>();
function once<T>(key: string, make: () => Promise<T>): Promise<T> {
  let p = cache.get(key) as Promise<T> | undefined;
  if (!p) {
    p = make();
    cache.set(key, p);
    p.catch(() => cache.delete(key));
  }
  return p;
}

/** Fetch and read sf-streets.bin (once per URL). */
export function loadStreets(url: string): Promise<Streets> {
  return once(url, async () => {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`streets: ${response.status}`);
    const buf = await response.arrayBuffer();
    const head = new DataView(buf);
    const magic = String.fromCharCode(head.getUint8(0), head.getUint8(1), head.getUint8(2), head.getUint8(3));
    if (magic !== "SFG1") throw new Error("streets: not an SFG1 file");
    const count = head.getUint32(8, true);
    const major = head.getUint32(12, true);
    return { count, major, minor: count - major, xy: new Int16Array(buf, 16, count * 4) };
  });
}

/** Fetch motions.json (once per URL). */
export function loadMotions(url: string): Promise<Motions> {
  return once(url, async () => {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`motions: ${response.status}`);
    const json = (await response.json()) as { points: MotionPoint[] };
    const points = json.points;
    return { points, byRecord: new Map(points.map(p => [p.record, p])) };
  });
}

/** Where a motion stands on the ground: its point on the street network (so a pin is planted on a line), or
 *  null for the motions with no usable address. Pass `onStreet: false` for the address point itself. */
export function motionPosition(point: MotionPoint | undefined, { onStreet = true } = {}): Ground | null {
  if (!point) return null;
  const gx = onStreet ? (point.sx ?? point.x) : (point.x ?? point.sx);
  const gy = onStreet ? (point.sy ?? point.y) : (point.y ?? point.sy);
  return gx === null || gy === null ? null : fromGrid(gx, gy);
}

/** The streets inside a box of grid metres, as an SVG path ("M x y L x y …") in the box's own coordinates
 *  (x east, y down from the box's north edge), for drawings made without WebGL. */
export function streetsPath(
  streets: Streets,
  box: { minX: number; minY: number; maxX: number; maxY: number },
  which: "minor" | "major" | "all" = "all",
): string {
  const from = which === "major" ? streets.minor : 0;
  const to = which === "minor" ? streets.minor : streets.count;
  const { xy } = streets;
  const parts: string[] = [];
  for (let i = from; i < to; i++) {
    const x1 = xy[i * 4]!, y1 = xy[i * 4 + 1]!, x2 = xy[i * 4 + 2]!, y2 = xy[i * 4 + 3]!;
    if (Math.max(x1, x2) < box.minX || Math.min(x1, x2) > box.maxX || Math.max(y1, y2) < box.minY || Math.min(y1, y2) > box.maxY) continue;
    parts.push(`M${x1 - box.minX} ${box.maxY - y1}L${x2 - box.minX} ${box.maxY - y2}`);
  }
  return parts.join("");
}
