// A crack through an element: a jagged line through a point to both edges (a seeded random walk: long, nearly
// straight runs broken by short sharp jogs), drawn out from the point as a dark gap that is widest where it
// starts and a hair where it ends, with a few fine branches; then the element is replaced by two copies of itself,
// each clipped to one side of the line, which pull apart on springs and fall away with a few shards of blank
// paper. What was under it shows through.

import { spring } from "motion";
import { animate } from "motion/mini";
import type { Point } from "./geometry";
import { between, rng, type Rng } from "./rng";

const NS = "http://www.w3.org/2000/svg";
let copies = 0;

export interface CrackOptions {
  seed?: number;
  /** The way the crack runs, in degrees (0 is straight across; negative rises to the right). Default -14. */
  angle?: number;
  /** How far each zig may turn from that, in degrees. Default 40. */
  wander?: number;
  /** Shortest and longest zig, in CSS pixels. Default [14, 38]. */
  step?: readonly [number, number];
  /** How many shards break off. Default 7. */
  shards?: number;
  /** How far past the element's own box its halves are kept, in CSS pixels, for things that overhang it (pages
   *  underneath, flecks of ink). Default 0. */
  bleed?: number;
  /** A selector for things inside the element that its copies should not carry (a layer that only makes sense
   *  once, something still fading). */
  strip?: string;
  /** Ink the torn edge of each half once they have parted (the box gets the class `is-parted`: open() adds it;
   *  add it yourself if you move the halves). Default false. */
  edge?: boolean;
  /** Leave the element showing under its halves when it is split (they cover it exactly), so the cut cannot be
   *  seen before the halves move. Hide it yourself when they do. Default false: split() hides it. */
  keep?: boolean;
}

export interface OpenOptions {
  /** How far each half pulls back from the line before it falls, in CSS pixels. Default 26. */
  gap?: number;
  /** How far the halves fall. Default: the height of the window. */
  fall?: number;
  /** Called once the halves have begun to part (what is underneath can show now). */
  onPart?: () => void;
}

export interface Crack {
  /** The line, edge to edge, in the element's own pixels. */
  readonly line: readonly Point[];
  /** A unit vector square to the crack, pointing at the first half. */
  readonly normal: Point;
  /** Draw the line outward from the point. Resolves when it has reached both edges. (After split() the line is
   *  drawn over the halves; erase() takes it away.) */
  draw(duration?: number): Promise<void>;
  /** Take the drawn line away (the halves' own edges take over). */
  erase(): void;
  /** Replace the element by its two halves (it is hidden, not removed). Called by open() if not before. */
  split(): readonly [HTMLElement, HTMLElement];
  /** Pull the halves apart and let them fall away. Resolves when they are gone. */
  open(options?: OpenOptions): Promise<void>;
  /** Take away the line, the halves and the shards. `restore` shows the element again. */
  destroy(restore?: boolean): void;
}

/** Walk from `from` in direction `heading` (radians) until the walk leaves the box; the last point is on the
 *  box's edge. Paper does not tear in even zigzags: it runs nearly straight for a while, then jogs sharply. */
function walk(r: Rng, from: Point, heading: number, w: number, h: number, wander: number, step: readonly [number, number]): Point[] {
  const out: Point[] = [];
  let p = from;
  let side = r() < 0.5 ? 1 : -1;
  // how far the walk has strayed to one side of its heading: jogs lean back toward the line
  let stray = 0;
  for (let i = 0; i < 240; i++) {
    const long = i > 0 && r() < 0.58;
    let turn: number;
    let len: number;
    if (long) {
      turn = between(r, -0.14, 0.14) * wander - Math.sign(stray) * 0.05 * wander;
      len = between(r, step[1] * 1.1, step[1] * 3.4);
    } else {
      if (Math.abs(stray) > step[1] * 0.9) side = -Math.sign(stray);
      turn = side * between(r, 0.55, 1.25) * wander;
      side = -side;
      len = between(r, step[0] * 0.45, step[0] * 1.5);
    }
    // a long run is not ruler-straight: it goes in two or three lengths that barely differ in direction
    if (long && len > step[1] * 1.6) {
      const parts = len > step[1] * 2.5 ? 3 : 2;
      len /= parts;
      for (let k = 1; k < parts; k++) {
        const bend = turn + between(r, -0.09, 0.09);
        const m = { x: p.x + Math.cos(heading + bend) * len, y: p.y + Math.sin(heading + bend) * len };
        if (m.x <= 0 || m.x >= w || m.y <= 0 || m.y >= h) break;
        stray += Math.sin(bend) * len;
        out.push(m);
        p = m;
      }
    }
    stray += Math.sin(turn) * len;
    const q = { x: p.x + Math.cos(heading + turn) * len, y: p.y + Math.sin(heading + turn) * len };
    if (q.x <= 0 || q.x >= w || q.y <= 0 || q.y >= h) {
      // stop on the edge
      let t = 1;
      if (q.x < 0) t = Math.min(t, p.x / (p.x - q.x));
      if (q.x > w) t = Math.min(t, (w - p.x) / (q.x - p.x));
      if (q.y < 0) t = Math.min(t, p.y / (p.y - q.y));
      if (q.y > h) t = Math.min(t, (h - p.y) / (q.y - p.y));
      out.push({ x: Math.min(w, Math.max(0, p.x + (q.x - p.x) * t)), y: Math.min(h, Math.max(0, p.y + (q.y - p.y) * t)) });
      return out;
    }
    out.push(q);
    p = q;
  }
  return out;
}

/** A polyline as a filled sliver: `from` px wide at its first point, tapering to `to` at its last. */
function sliver(points: readonly Point[], from: number, to: number): string {
  if (points.length < 2) return "";
  const lengths = [0];
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1] as Point;
    const b = points[i] as Point;
    lengths.push((lengths[i - 1] ?? 0) + Math.hypot(b.x - a.x, b.y - a.y));
  }
  const total = lengths[lengths.length - 1] || 1;
  const left: string[] = [];
  const right: string[] = [];
  for (let i = 0; i < points.length; i++) {
    const p = points[i] as Point;
    const a = points[Math.max(0, i - 1)] as Point;
    const b = points[Math.min(points.length - 1, i + 1)] as Point;
    const l = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    const nx = -(b.y - a.y) / l;
    const ny = (b.x - a.x) / l;
    // the taper is quick at first and slow after: most of the line is thin
    const t = (lengths[i] ?? 0) / total;
    const half = (to + (from - to) * (1 - t) ** 1.7) / 2;
    left.push(`${(p.x + nx * half).toFixed(1)} ${(p.y + ny * half).toFixed(1)}`);
    right.push(`${(p.x - nx * half).toFixed(1)} ${(p.y - ny * half).toFixed(1)}`);
  }
  return `M${left.join("L")}L${right.reverse().join("L")}Z`;
}

/** A jagged line across a `w` by `h` box through `point`, from one edge to another. */
export function crackLine(w: number, h: number, point: Point, options: CrackOptions = {}): { line: Point[]; origin: number } {
  const r = rng(options.seed ?? 1);
  const heading = ((options.angle ?? -14) * Math.PI) / 180;
  const wander = ((options.wander ?? 40) * Math.PI) / 180;
  const step = options.step ?? [14, 38];
  const centre = { x: Math.min(w - 1, Math.max(1, point.x)), y: Math.min(h - 1, Math.max(1, point.y)) };
  const ahead = walk(r, centre, heading, w, h, wander, step);
  const back = walk(r, centre, heading + Math.PI, w, h, wander, step);
  return { line: [...back.reverse(), centre, ...ahead], origin: back.length };
}

/** How far round the box's edge a point on the edge is, clockwise from the top left corner. */
function along(p: Point, w: number, h: number): number {
  const e = 0.5;
  if (p.y <= e) return p.x;
  if (p.x >= w - e) return w + p.y;
  if (p.y >= h - e) return w + h + (w - p.x);
  return 2 * w + h + (h - p.y);
}

/** The two pieces a line from edge to edge cuts a box into, as polygons. */
function halves(line: readonly Point[], w: number, h: number): [Point[], Point[]] {
  const corners: { t: number; p: Point }[] = [
    { t: 0, p: { x: 0, y: 0 } },
    { t: w, p: { x: w, y: 0 } },
    { t: w + h, p: { x: w, y: h } },
    { t: 2 * w + h, p: { x: 0, y: h } },
  ];
  const around = 2 * (w + h);
  const first = line[0] as Point;
  const last = line[line.length - 1] as Point;
  const t0 = along(first, w, h);
  const t1 = along(last, w, h);
  // from the line's end, round the edge back to its start: once clockwise, once the other way
  const clockwise = corners
    .map(c => ({ ...c, d: (c.t - t1 + around) % around }))
    .filter(c => c.d > 0 && c.d < (t0 - t1 + around) % around)
    .sort((a, b) => a.d - b.d)
    .map(c => c.p);
  const counter = corners
    .map(c => ({ ...c, d: (t1 - c.t + around) % around }))
    .filter(c => c.d > 0 && c.d < (t1 - t0 + around) % around)
    .sort((a, b) => a.d - b.d)
    .map(c => c.p);
  return [
    [...line, ...clockwise],
    [...line, ...counter],
  ];
}

const polygon = (ps: readonly Point[]): string => `polygon(${ps.map(p => `${p.x.toFixed(1)}px ${p.y.toFixed(1)}px`).join(", ")})`;
const centroid = (ps: readonly Point[]): Point => ({ x: ps.reduce((s, p) => s + p.x, 0) / ps.length, y: ps.reduce((s, p) => s + p.y, 0) / ps.length });

/**
 * Crack `element` through `point` (in its own pixels). The element should be absolutely positioned and take its
 * rotation, if any, from the CSS `rotate` property (not `transform`): its halves are copies of it in a box that is
 * put after it, in the same place and at the same turn.
 */
export function crackThrough(element: HTMLElement, point: Point, options: CrackOptions = {}): Crack {
  const w = element.offsetWidth;
  const h = element.offsetHeight;
  const seed = options.seed ?? 1;
  const { line, origin } = crackLine(w, h, point, options);
  const first = line[0] as Point;
  const last = line[line.length - 1] as Point;
  const run = Math.hypot(last.x - first.x, last.y - first.y) || 1;
  // square to the crack, pointing up the page (so the first half is the upper one)
  let normal = { x: (last.y - first.y) / run, y: -(last.x - first.x) / run };
  if (normal.y > 0) normal = { x: -normal.x, y: -normal.y };

  let svg: SVGSVGElement | null = null;
  let pieces: [HTMLElement, HTMLElement] | null = null;
  let box: HTMLElement | null = null;
  const shards: HTMLElement[] = [];
  let gone = false;

  function draw(duration = 300): Promise<void> {
    svg?.remove();
    svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "stamp-crack");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    const mid = line[origin] as Point;
    const arms = [line.slice(0, origin + 1).reverse(), line.slice(origin)];
    // the gap is widest at the point it starts from, and a hair where it meets the edges
    let d = arms.map(arm => sliver(arm, 3.2, 0.5)).join("");
    // two or three hairline branches leave it near the start
    const r = rng(seed ^ 0x3b1d);
    const branches = 2 + (r() < 0.5 ? 1 : 0);
    for (let i = 0; i < branches; i++) {
      const arm = arms[i % 2] as Point[];
      const at = Math.min(arm.length - 2, 1 + Math.floor(r() * 3));
      const p = arm[at];
      const q = arm[at + 1];
      if (!p || !q) continue;
      const along = Math.atan2(q.y - p.y, q.x - p.x);
      const turn = (r() < 0.5 ? 1 : -1) * between(r, 0.5, 1.0);
      const len = between(r, 16, 44);
      const kink = between(r, -0.5, 0.5);
      const b1 = { x: p.x + Math.cos(along + turn) * len * 0.55, y: p.y + Math.sin(along + turn) * len * 0.55 };
      const b2 = { x: b1.x + Math.cos(along + turn + kink) * len * 0.45, y: b1.y + Math.sin(along + turn + kink) * len * 0.45 };
      d += sliver([p, b1, b2], 1.1, 0.25);
    }
    // on a dark ground the far lip of the gap catches a little light: the same shape, a pixel across
    const edge = document.createElementNS(NS, "path");
    edge.setAttribute("class", "stamp-crack__edge");
    edge.setAttribute("d", d);
    edge.setAttribute("transform", "translate(0.7 0.9)");
    const core = document.createElementNS(NS, "path");
    core.setAttribute("class", "stamp-crack__core");
    core.setAttribute("d", d);
    svg.append(edge, core);
    (box ?? element).append(svg);
    if (duration <= 0) return Promise.resolve();
    // it runs out from the point in both directions at once, fast at first and slowing as it goes: a crack, not
    // a pen
    const reach = Math.max(...line.map(p => Math.hypot(p.x - mid.x, p.y - mid.y))) + 6;
    const at = `${mid.x.toFixed(1)}px ${mid.y.toFixed(1)}px`;
    const drawing = svg;
    const run = drawing.animate([{ clipPath: `circle(0px at ${at})` }, { clipPath: `circle(${reach.toFixed(0)}px at ${at})` }], {
      duration,
      easing: "cubic-bezier(0.16, 0.72, 0.3, 1)",
      fill: "both",
    });
    return run.finished.then(
      () => run.cancel(),
      () => {},
    );
  }

  function erase(): void {
    svg?.remove();
    svg = null;
  }

  function split(): readonly [HTMLElement, HTMLElement] {
    if (pieces) return pieces;
    erase();
    const bleed = options.bleed ?? 0;
    // push every point on the box's edge out by the bleed, so what overhangs the box stays with its half
    const out = (ps: Point[]): Point[] =>
      bleed <= 0
        ? ps
        : ps.map(p => ({
            x: p.x <= 0.5 ? -bleed : p.x >= w - 0.5 ? w + bleed : p.x,
            y: p.y <= 0.5 ? -bleed : p.y >= h - 0.5 ? h + bleed : p.y,
          }));
    const [a, b] = halves(line, w, h).map(out) as [Point[], Point[]];
    // the first half is the one the normal points at
    const mid = line[origin] as Point;
    const ca = centroid(a);
    const upperFirst = (ca.x - mid.x) * normal.x + (ca.y - mid.y) * normal.y > 0;
    const shapes = upperFirst ? [a, b] : [b, a];
    // the pieces live in one box that sits where the element sits and is turned as it is, so each piece can
    // tumble about its own middle
    box = document.createElement("div");
    box.className = "stamp-pieces";
    box.setAttribute("aria-hidden", "true");
    const style = getComputedStyle(element);
    box.style.cssText = `left:${element.offsetLeft}px;top:${element.offsetTop}px;width:${w}px;height:${h}px;rotate:${style.rotate};translate:${style.translate};`;
    const made = shapes.map(shape => {
      const copy = element.cloneNode(true) as HTMLElement;
      copy.removeAttribute("id");
      if (options.strip) for (const el of copy.querySelectorAll(options.strip)) el.remove();
      // ids inside the copy (an inline SVG's filters and masks) get new names, and what points at them follows
      const suffix = `-half${++copies}`;
      const renamed = new Map<string, string>();
      for (const el of copy.querySelectorAll("[id]")) {
        renamed.set(el.id, el.id + suffix);
        el.id += suffix;
      }
      if (renamed.size) {
        for (const el of copy.querySelectorAll("*")) {
          for (const attr of ["filter", "mask", "fill", "stroke", "clip-path", "href"]) {
            const value = el.getAttribute(attr);
            if (!value || !value.includes("#")) continue;
            el.setAttribute(attr, value.replace(/#([\w-]+)/g, (all, id: string) => (renamed.has(id) ? `#${renamed.get(id)}` : all)));
          }
        }
      }
      copy.setAttribute("inert", "");
      copy.classList.add("stamp-half");
      copy.style.cssText += `;position:absolute;left:0;top:0;margin:0;width:${w}px;height:${h}px;rotate:none;translate:none;visibility:visible;`;
      copy.style.clipPath = polygon(shape);
      const c = centroid(shape);
      copy.style.transformOrigin = `${c.x.toFixed(1)}px ${c.y.toFixed(1)}px`;
      if (options.edge) {
        // the torn edge, inked: a stroke along the line, of which the clip keeps the half that is on this piece
        const edge = document.createElementNS(NS, "svg");
        edge.setAttribute("class", "stamp-half__edge");
        edge.setAttribute("aria-hidden", "true");
        edge.setAttribute("focusable", "false");
        edge.setAttribute("viewBox", `0 0 ${w} ${h}`);
        const path = document.createElementNS(NS, "path");
        path.setAttribute("d", `M${line.map(p => `${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join("L")}`);
        edge.append(path);
        copy.append(edge);
      }
      return copy;
    }) as [HTMLElement, HTMLElement];
    box.append(...made);
    element.after(box);
    if (!options.keep) element.style.visibility = "hidden";

    // shards: slivers of blank paper along the line
    const r = rng(seed ^ 0x51ab);
    const count = options.shards ?? 7;
    for (let i = 0; i < count; i++) {
      const at = 1 + Math.floor(r() * (line.length - 2));
      const p = line[at] as Point;
      const q = line[at + (r() < 0.5 ? 1 : -1)] ?? p;
      const t = between(r, 0.25, 0.7);
      const side = r() < 0.5 ? 1 : -1;
      const reach = between(r, 7, 20);
      const tri = [p, { x: p.x + (q.x - p.x) * t, y: p.y + (q.y - p.y) * t }, { x: p.x + normal.x * side * reach + between(r, -6, 6), y: p.y + normal.y * side * reach + between(r, -6, 6) }];
      const shard = document.createElement("div");
      shard.className = "stamp-shard";
      shard.style.clipPath = polygon(tri);
      const c = centroid(tri);
      shard.style.transformOrigin = `${c.x.toFixed(1)}px ${c.y.toFixed(1)}px`;
      shard.dataset.side = String(side);
      shards.push(shard);
    }
    box.append(...shards);
    pieces = made;
    return made;
  }

  async function open(o: OpenOptions = {}): Promise<void> {
    const [a, b] = split();
    erase();
    element.style.visibility = "hidden";
    box?.classList.add("is-parted");
    const gap = o.gap ?? 26;
    const fall = o.fall ?? window.innerHeight;
    const r = rng(seed ^ 0x77c1);
    // every pose of a piece is the same list of transforms, so the browser can run the whole thing itself
    const pose = (x: number, y: number, turn: number, tip = 0): string =>
      `perspective(1100px) translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0) rotate(${turn.toFixed(2)}deg) rotateX(${tip.toFixed(1)}deg)`;
    const jump = { type: spring, stiffness: 420, damping: 19, mass: 1 };
    // 1. the halves jump apart, square to the line
    const twistA = between(r, 0.9, 1.9);
    const twistB = between(r, 0.7, 1.6);
    const apartA = { x: normal.x * gap, y: normal.y * gap };
    const apartB = { x: -normal.x * gap * 0.8, y: -normal.y * gap * 0.8 };
    animate(a, { transform: [pose(0, 0, 0), pose(apartA.x, apartA.y, -twistA)] }, jump);
    animate(b, { transform: [pose(0, 0, 0), pose(apartB.x, apartB.y, twistB)] }, jump);
    for (const shard of shards) {
      const side = Number(shard.dataset.side) || 1;
      const out = between(r, 50, 170);
      const dx = normal.x * side * out + between(r, -70, 70);
      const dy = normal.y * side * out;
      animate(
        shard,
        {
          transform: [pose(0, 0, 0), pose(dx, dy, between(r, -160, 160)), pose(dx * 1.25, dy + between(r, 260, 520), between(r, -420, 420))],
          opacity: [1, 1, 0],
        },
        { duration: between(r, 0.62, 0.9), times: [0, 0.32, 1], ease: ["easeOut", "easeIn"] },
      );
    }
    o.onPart?.();
    await new Promise(done => setTimeout(done, 150));
    if (gone) return;
    // 2. and fall away: the upper one is thrown up a little first, the lower one just drops
    const drop = [0.5, 0, 0.9, 0.55] as const;
    const upper = animate(
      a,
      {
        transform: [
          pose(apartA.x, apartA.y, -twistA),
          pose(normal.x * (gap + 36) - 26, normal.y * (gap + 44), -twistA - 4, -14),
          pose(normal.x * (gap + 60) - 90, fall * 0.95, -twistA - 24, -58),
        ],
        opacity: [1, 1, 0.6],
      },
      { duration: 0.68, times: [0, 0.3, 1], ease: ["easeOut", drop] },
    );
    const lower = animate(
      b,
      { transform: [pose(apartB.x, apartB.y, twistB), pose(-normal.x * gap + 70, fall * 0.9, twistB + 19, 46)], opacity: [1, 0.6] },
      { duration: 0.6, ease: drop },
    );
    await Promise.all([upper.finished, lower.finished]);
    box?.remove();
  }

  return {
    line,
    normal,
    draw,
    erase,
    split,
    open,
    destroy(restore = false) {
      gone = true;
      svg?.remove();
      svg = null;
      box?.remove();
      box = null;
      pieces = null;
      shards.length = 0;
      if (restore) element.style.visibility = "";
    },
  };
}
