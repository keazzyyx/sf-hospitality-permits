// The street network as a graph, and the shortest path along real streets between two points.
// Nodes are the segment end points (about 13,900); edges are the segments (about 19,800). No three.js here.

import type { Streets } from "./data";
import type { Ground } from "./projection";

/** A path on the ground with distances, for a line that draws on and a camera that follows it. */
export interface Route {
  /** x, z per point. */
  points: Float32Array;
  /** Distance along the path at each point, in metres. */
  along: Float32Array;
  /** Total length in metres. */
  length: number;
  /** The point at fraction t (0 to 1) of the length. */
  at(t: number, out?: Ground): Ground;
  /** The mean of the path over ± `window` (a fraction of the length) around t: a path without corners, for a
   *  camera target. */
  smooth(t: number, window?: number, out?: Ground): Ground;
}

/** Make a Route from points on the ground. */
export function makeRoute(pts: Ground[]): Route {
  const n = pts.length;
  const points = new Float32Array(n * 2);
  const along = new Float32Array(n);
  let length = 0;
  for (let i = 0; i < n; i++) {
    const p = pts[i]!;
    points[i * 2] = p.x;
    points[i * 2 + 1] = p.z;
    if (i > 0) length += Math.hypot(p.x - pts[i - 1]!.x, p.z - pts[i - 1]!.z);
    along[i] = length;
  }
  const at = (t: number, out: Ground = { x: 0, z: 0 }): Ground => {
    if (n === 0) return out;
    const d = Math.min(1, Math.max(0, t)) * length;
    let i = 1;
    while (i < n - 1 && along[i]! < d) i++;
    const d0 = along[i - 1] ?? 0;
    const d1 = along[i] ?? d0;
    const k = d1 > d0 ? (d - d0) / (d1 - d0) : 0;
    const j = Math.max(0, i - 1);
    out.x = points[j * 2]! + ((points[i * 2] ?? points[j * 2]!) - points[j * 2]!) * k;
    out.z = points[j * 2 + 1]! + ((points[i * 2 + 1] ?? points[j * 2 + 1]!) - points[j * 2 + 1]!) * k;
    return out;
  };
  const probe: Ground = { x: 0, z: 0 };
  const smooth = (t: number, window = 0.06, out: Ground = { x: 0, z: 0 }): Ground => {
    let x = 0, z = 0;
    const samples = 9;
    for (let s = 0; s < samples; s++) {
      at(t + ((s / (samples - 1)) * 2 - 1) * window, probe);
      x += probe.x;
      z += probe.z;
    }
    out.x = x / samples;
    out.z = z / samples;
    return out;
  };
  return { points, along, length, at, smooth };
}

export interface StreetGraph {
  /** Number of nodes. */
  nodes: number;
  /** The node nearest a point on the ground. */
  nearest(p: Ground): number;
  /** Where a node is. */
  position(node: number): Ground;
  /** The shortest path along the streets from the node nearest `from` to the node nearest `to`, or null when the
   *  two are not connected. */
  route(from: Ground, to: Ground): Route | null;
}

const graphs = new WeakMap<Streets, StreetGraph>();

/** The graph of a street set: built the first time it is asked for, then kept. */
export function streetGraph(streets: Streets): StreetGraph {
  let g = graphs.get(streets);
  if (!g) {
    g = build(streets);
    graphs.set(streets, g);
  }
  return g;
}

function build(streets: Streets): StreetGraph {
  const { xy, count } = streets;
  // nodes: one per distinct end point (grid coordinates are whole metres within ±32,767, so a pair packs into a key)
  const ids = new Map<number, number>();
  const nx: number[] = [];
  const nz: number[] = [];
  const node = (gx: number, gy: number): number => {
    const key = (gx + 32768) * 65536 + (gy + 32768);
    let id = ids.get(key);
    if (id === undefined) {
      id = nx.length;
      ids.set(key, id);
      nx.push(gx);
      nz.push(-gy);
    }
    return id;
  };
  const a = new Int32Array(count);
  const b = new Int32Array(count);
  const w = new Float32Array(count);
  const degree: number[] = [];
  for (let i = 0; i < count; i++) {
    const x1 = xy[i * 4]!, y1 = xy[i * 4 + 1]!, x2 = xy[i * 4 + 2]!, y2 = xy[i * 4 + 3]!;
    const u = node(x1, y1), v = node(x2, y2);
    a[i] = u;
    b[i] = v;
    w[i] = Math.hypot(x2 - x1, y2 - y1);
    degree[u] = (degree[u] ?? 0) + 1;
    degree[v] = (degree[v] ?? 0) + 1;
  }
  const n = nx.length;
  // adjacency in compressed rows
  const start = new Int32Array(n + 1);
  for (let i = 0; i < n; i++) start[i + 1] = start[i]! + (degree[i] ?? 0);
  const fill = start.slice(0, n);
  const to = new Int32Array(count * 2);
  const cost = new Float32Array(count * 2);
  for (let i = 0; i < count; i++) {
    const u = a[i]!, v = b[i]!;
    let k = fill[u]!;
    fill[u] = k + 1;
    to[k] = v;
    cost[k] = w[i]!;
    k = fill[v]!;
    fill[v] = k + 1;
    to[k] = u;
    cost[k] = w[i]!;
  }

  const nearest = (p: Ground): number => {
    let best = 0, bd = Infinity;
    for (let i = 0; i < n; i++) {
      const dx = nx[i]! - p.x, dz = nz[i]! - p.z;
      const d = dx * dx + dz * dz;
      if (d < bd) {
        bd = d;
        best = i;
      }
    }
    return best;
  };

  const route = (from: Ground, target: Ground): Route | null => {
    const s = nearest(from), t = nearest(target);
    const dist = new Float64Array(n).fill(Infinity);
    const prev = new Int32Array(n).fill(-1);
    // a binary heap of (distance, node)
    const heapD: number[] = [0];
    const heapN: number[] = [s];
    dist[s] = 0;
    while (heapN.length) {
      const d = heapD[0]!, u = heapN[0]!;
      const lastD = heapD.pop()!, lastN = heapN.pop()!;
      if (heapN.length) {
        let i = 0;
        const len = heapN.length;
        for (;;) {
          const l = i * 2 + 1, r = l + 1;
          let m = i;
          const md = lastD;
          let best = md;
          if (l < len && heapD[l]! < best) { m = l; best = heapD[l]!; }
          if (r < len && heapD[r]! < best) { m = r; }
          if (m === i) break;
          heapD[i] = heapD[m]!;
          heapN[i] = heapN[m]!;
          i = m;
        }
        heapD[i] = lastD;
        heapN[i] = lastN;
      }
      if (u === t) break;
      if (d > dist[u]!) continue;
      for (let k = start[u]!; k < start[u + 1]!; k++) {
        const v = to[k]!;
        const nd = d + cost[k]!;
        if (nd < dist[v]!) {
          dist[v] = nd;
          prev[v] = u;
          let i = heapN.length;
          heapD.push(nd);
          heapN.push(v);
          while (i > 0) {
            const parent = (i - 1) >> 1;
            if (heapD[parent]! <= nd) break;
            heapD[i] = heapD[parent]!;
            heapN[i] = heapN[parent]!;
            i = parent;
          }
          heapD[i] = nd;
          heapN[i] = v;
        }
      }
    }
    if (s !== t && prev[t] === -1) return null;
    const path: Ground[] = [];
    for (let u = t; u !== -1; u = prev[u]!) path.push({ x: nx[u]!, z: nz[u]! });
    path.reverse();
    return makeRoute(path);
  };

  return { nodes: n, nearest, position: i => ({ x: nx[i] ?? 0, z: nz[i] ?? 0 }), route };
}
