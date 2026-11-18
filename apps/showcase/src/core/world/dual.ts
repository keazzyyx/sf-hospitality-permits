// Dual carriageways as one line. The city's centreline data draws a divided street (Van Ness Avenue, Lombard
// Street, Geary Boulevard…) as two lines, one for each direction, that meet at every crossing: on a map of single
// lines that reads as a chain of lozenges, like a twisted ribbon. mergeDual() finds each pair of major-street
// chains that leave one crossing together and arrive at the next together, close beside each other, and replaces
// the pair with the line between them. No three.js here.

import type { Streets } from "./data";

/** Distance from a point to a polyline given as x, y pairs; also where on it the nearest point is. */
function nearest(px: number, py: number, line: number[], out: { x: number; y: number }): number {
  let best = Infinity;
  for (let i = 0; i + 3 < line.length; i += 2) {
    const ax = line[i]!, ay = line[i + 1]!, dx = line[i + 2]! - ax, dy = line[i + 3]! - ay;
    const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy || 1)));
    const qx = ax + dx * t, qy = ay + dy * t;
    const d = Math.hypot(px - qx, py - qy);
    if (d < best) {
      best = d;
      out.x = qx;
      out.y = qy;
    }
  }
  return best;
}

const length = (line: number[]): number => {
  let sum = 0;
  for (let i = 0; i + 3 < line.length; i += 2) sum += Math.hypot(line[i + 2]! - line[i]!, line[i + 3]! - line[i + 1]!);
  return sum;
};

/**
 * The same streets with each dual carriageway among the major streets drawn as one line. `gap` is the most two
 * lines may be apart, in metres, to count as one street (default 34: the widest boulevards' medians).
 * Minor streets are left as they are. The result is a new Streets; the input is not changed.
 */
export function mergeDual(streets: Streets, gap = 34): Streets {
  const { xy, count, minor } = streets;
  const key = (x: number, y: number): number => (x + 32768) * 65536 + (y + 32768);
  // the major streets as a graph: node -> the segments that end there
  const at = new Map<number, { seg: number; to: number }[]>();
  const link = (a: number, b: number, seg: number): void => {
    let list = at.get(a);
    if (!list) at.set(a, (list = []));
    list.push({ seg, to: b });
  };
  for (let i = minor; i < count; i++) {
    const a = key(xy[i * 4]!, xy[i * 4 + 1]!), b = key(xy[i * 4 + 2]!, xy[i * 4 + 3]!);
    if (a === b) continue;
    link(a, b, i);
    link(b, a, i);
  }
  const xOf = (k: number): number => Math.floor(k / 65536) - 32768;
  const yOf = (k: number): number => (k % 65536) - 32768;
  // chains: runs of segments through nodes that only two segments meet at, from one crossing to the next
  interface Chain {
    a: number;
    b: number;
    segs: number[];
    line: number[];
  }
  const used = new Uint8Array(count);
  const groups = new Map<string, Chain[]>();
  for (const [node, list] of at) {
    if (list.length === 2) continue;
    for (const first of list) {
      if (used[first.seg]) continue;
      const segs = [first.seg];
      used[first.seg] = 1;
      const line = [xOf(node), yOf(node), xOf(first.to), yOf(first.to)];
      let cur = first.to;
      for (;;) {
        const next = at.get(cur)!;
        if (next.length !== 2) break;
        const on = next[0]!.seg === segs[segs.length - 1] ? next[1]! : next[0]!;
        if (used[on.seg]) break;
        used[on.seg] = 1;
        segs.push(on.seg);
        cur = on.to;
        line.push(xOf(cur), yOf(cur));
      }
      if (cur === node) continue;
      // both chains of a pair are kept running the same way
      const forward = node < cur;
      const chain: Chain = { a: forward ? node : cur, b: forward ? cur : node, segs, line: forward ? line : reversed(line) };
      const id = `${chain.a}|${chain.b}`;
      const group = groups.get(id);
      if (group) group.push(chain);
      else groups.set(id, [chain]);
    }
  }
  const drop = new Uint8Array(count);
  const added: number[] = [];
  const q = { x: 0, y: 0 };
  for (const group of groups.values()) {
    if (group.length < 2) continue;
    const [p, s] = group;
    if (!p || !s) continue;
    // beside each other all the way, and no more than one street apart
    let apart = 0;
    for (let i = 0; i < p.line.length; i += 2) apart = Math.max(apart, nearest(p.line[i]!, p.line[i + 1]!, s.line, q));
    for (let i = 0; i < s.line.length; i += 2) apart = Math.max(apart, nearest(s.line[i]!, s.line[i + 1]!, p.line, q));
    const chord = Math.hypot(p.line[p.line.length - 2]! - p.line[0]!, p.line[p.line.length - 1]! - p.line[1]!);
    if (apart > gap || chord < apart * 1.5 || Math.max(length(p.line), length(s.line)) > chord * 1.35) continue;
    for (const seg of p.segs) drop[seg] = 1;
    for (const seg of s.segs) drop[seg] = 1;
    // the line between them: each bend of the one with more bends, moved halfway to the other
    const guide = p.line.length >= s.line.length ? p : s, other = guide === p ? s : p;
    const mid = [guide.line[0]!, guide.line[1]!];
    for (let i = 2; i < guide.line.length - 2; i += 2) {
      nearest(guide.line[i]!, guide.line[i + 1]!, other.line, q);
      mid.push(Math.round((guide.line[i]! + q.x) / 2), Math.round((guide.line[i + 1]! + q.y) / 2));
    }
    mid.push(guide.line[guide.line.length - 2]!, guide.line[guide.line.length - 1]!);
    // a bend of less than a few metres is the data's, not the street's: leave it out
    const line = simplify(mid, 3.5);
    for (let i = 0; i + 3 < line.length; i += 2) {
      if (line[i] === line[i + 2] && line[i + 1] === line[i + 3]) continue;
      added.push(line[i]!, line[i + 1]!, line[i + 2]!, line[i + 3]!);
    }
  }
  let kept = 0;
  for (let i = minor; i < count; i++) if (!drop[i]) kept++;
  const major = kept + added.length / 4;
  const out = new Int16Array((minor + major) * 4);
  out.set(xy.subarray(0, minor * 4));
  let w = minor * 4;
  for (let i = minor; i < count; i++) {
    if (drop[i]) continue;
    out.set(xy.subarray(i * 4, i * 4 + 4), w);
    w += 4;
  }
  out.set(added, w);
  return { count: minor + major, minor, major, xy: out };
}

function reversed(line: number[]): number[] {
  const out: number[] = [];
  for (let i = line.length - 2; i >= 0; i -= 2) out.push(line[i]!, line[i + 1]!);
  return out;
}

/** A polyline (x, y pairs) without the bends that stand less than `tolerance` off the line through their
 *  neighbours (Douglas and Peucker's rule). */
function simplify(line: number[], tolerance: number): number[] {
  const n = line.length / 2;
  if (n <= 2) return line;
  const keep = new Uint8Array(n);
  keep[0] = keep[n - 1] = 1;
  const stack: [number, number][] = [[0, n - 1]];
  while (stack.length) {
    const [a, b] = stack.pop()!;
    const ax = line[a * 2]!, ay = line[a * 2 + 1]!, dx = line[b * 2]! - ax, dy = line[b * 2 + 1]! - ay;
    const len = Math.hypot(dx, dy) || 1;
    let worst = -1, far = tolerance;
    for (let i = a + 1; i < b; i++) {
      const d = Math.abs((line[i * 2]! - ax) * dy - (line[i * 2 + 1]! - ay) * dx) / len;
      if (d > far) {
        far = d;
        worst = i;
      }
    }
    if (worst >= 0) {
      keep[worst] = 1;
      stack.push([a, worst], [worst, b]);
    }
  }
  const out: number[] = [];
  for (let i = 0; i < n; i++) if (keep[i]) out.push(line[i * 2]!, line[i * 2 + 1]!);
  return out;
}
