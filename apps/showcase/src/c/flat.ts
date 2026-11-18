// The map without WebGL: the same streets and the same motions, drawn once as SVG through the same camera
// arithmetic (project.ts), so the sheet, the panels and the search stand over a still drawing of the same world.
// It does not move; it is redrawn when the page asks for another view (a chapter's camera, the search's).

import type { Motions, Streets } from "../core/world/data";
import type { Pose } from "../core/world/rig";
import { CASTLE, HILL_GRID_DEG, offset, RECORD, SEATS, SLABS } from "./places";
import { gatePose, type View } from "./poses";
import { projector } from "./project";
import type { Eye } from "./story";

const NS = "http://www.w3.org/2000/svg";

/** Cut a segment to the window (Liang and Barsky): false when none of it is inside. The points are changed. */
function clip(a: { x: number; y: number }, b: { x: number; y: number }, w: number, h: number): boolean {
  let t0 = 0, t1 = 1;
  const dx = b.x - a.x, dy = b.y - a.y;
  const edges: [number, number][] = [[-dx, a.x], [dx, w - a.x], [-dy, a.y], [dy, h - a.y]];
  for (const [p, q] of edges) {
    if (p === 0) {
      if (q < 0) return false;
      continue;
    }
    const r = q / p;
    if (p < 0) {
      if (r > t1) return false;
      if (r > t0) t0 = r;
    } else {
      if (r < t0) return false;
      if (r < t1) t1 = r;
    }
  }
  const ax = a.x + dx * t0, ay = a.y + dy * t0;
  b.x = a.x + dx * t1;
  b.y = a.y + dy * t1;
  a.x = ax;
  a.y = ay;
  return true;
}

export interface Flat {
  el: SVGSVGElement;
  /** What the story needs of it: where things are on the drawing, and the drawn objects it can show. */
  eye: Eye;
  /** Draw the map as a camera pose sees it. `stacks`: the motions stand as lines, as tall as their conditions.
   *  `route`: how much of the route line is drawn (0 to 1). `slabs`: the story's own stack of conditions stands
   *  by the address. */
  draw(pose: Pose, stacks: boolean, route?: number, slabs?: boolean): void;
  /** The route along the streets (x, z per point), drawn when a chapter asks for it. */
  setRoute(points: Float32Array): void;
  /** Where a world point is on the drawing, as it was last drawn. */
  project(x: number, y: number, z: number, out: { x: number; y: number; behind: boolean }): { x: number; y: number; behind: boolean };
  /** The motion drawn under a point of the window (its case number), or null. */
  pick(x: number, y: number, reach?: number): string | null;
  /** Where a motion's dot is drawn; false when it is not on the drawing. */
  topOf(record: string, out: { x: number; y: number }): boolean;
  setLit(records: ReadonlySet<string> | null): void;
  setHero(on: boolean): void;
  hover(record: string | null): void;
  resize(view: View): void;
}

export function mountFlat(options: { streets: Streets; motions: Motions; view: View }): Flat {
  const { streets } = options;
  let view = options.view;
  const el = document.createElementNS(NS, "svg");
  el.setAttribute("class", "c-flat");
  el.setAttribute("aria-hidden", "true");
  el.setAttribute("focusable", "false");
  const minor = document.createElementNS(NS, "path");
  minor.setAttribute("class", "c-flat__minor");
  const major = document.createElementNS(NS, "path");
  major.setAttribute("class", "c-flat__major");
  const stems = document.createElementNS(NS, "g");
  stems.setAttribute("class", "c-flat__stems");
  const dots = document.createElementNS(NS, "g");
  dots.setAttribute("class", "c-flat__dots");
  const routePath = document.createElementNS(NS, "path");
  routePath.setAttribute("class", "c-flat__route");
  // the story's own drawings: the stack of 22 slabs by the address, and the seven seats at the end of the route
  const slabGroup = document.createElementNS(NS, "g");
  slabGroup.setAttribute("class", "c-flat__slabs");
  const seatGroup = document.createElementNS(NS, "g");
  seatGroup.setAttribute("class", "c-flat__seats");
  el.append(minor, major, routePath, stems, dots, slabGroup, seatGroup);
  const slabCount = 22;
  const slabHull = Array.from({ length: slabCount }, () => {
    const hull = document.createElementNS(NS, "polygon");
    const top = document.createElementNS(NS, "polygon");
    top.setAttribute("class", "c-flat__slab-top");
    slabGroup.append(hull, top);
    return { hull, top };
  });
  const seatDots = SEATS.map(() => {
    const c = document.createElementNS(NS, "circle");
    c.setAttribute("r", "5");
    seatGroup.append(c);
    return c;
  });
  let slabGrow = 0, slabLine = -1, slabAmount = 0, slabsOn = false;
  let seatsUp = 0, seatsVoted = 0;
  let routePoints: Float32Array | null = null;
  let lastRoute = 0;

  const points = options.motions.points
    .filter(p => (p.sx ?? p.x) !== null && (p.sy ?? p.y) !== null)
    .map(p => {
      const hero = p.record === RECORD;
      const circle = document.createElementNS(NS, "circle");
      circle.setAttribute("r", "2.2");
      const stem = document.createElementNS(NS, "line");
      dots.append(circle);
      stems.append(stem);
      return { record: p.record, n: p.n, x: hero ? CASTLE.x : (p.sx ?? p.x)!, z: hero ? CASTLE.z : -(p.sy ?? p.y)!, hero, circle, stem, sx: 0, sy: 0, shown: false };
    });

  let lit: ReadonlySet<string> | null = null;
  let heroOn = false;
  let hovered: string | null = null;
  let lastPose: Pose = gatePose(view);
  let lastStacks = false;
  const out = { x: 0, y: 0, behind: false };
  const out2 = { x: 0, y: 0, behind: false };

  const classes = (): void => {
    for (const p of points) {
      const match = !lit || lit.has(p.record);
      p.circle.setAttribute("class", `${p.hero && heroOn ? "is-hero" : ""}${match ? "" : " is-dim"}${(lit && match) || p.record === hovered ? " is-lit" : ""}`);
      p.stem.setAttribute("opacity", match ? "0.85" : "0.12");
    }
  };

  /** The corners of slab i (0 at the bottom) as it stands at a grow of `g`: four at its base, four at its top. */
  const slabLevel = (i: number, g: number): number => {
    const k = Math.min(1, Math.max(0, g * 1.5 - (0.5 * i) / (slabCount - 1)));
    const e = 1 - (1 - k) ** 3;
    return i * SLABS.pitch * e;
  };
  const hullOf = (pts: { x: number; y: number }[]): string => {
    const p = [...pts].sort((a, b) => a.x - b.x || a.y - b.y);
    const cross = (o: { x: number; y: number }, a: { x: number; y: number }, b: { x: number; y: number }): number => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
    const lower: { x: number; y: number }[] = [];
    for (const q of p) {
      while (lower.length >= 2 && cross(lower[lower.length - 2]!, lower[lower.length - 1]!, q) <= 0) lower.pop();
      lower.push(q);
    }
    const upper: { x: number; y: number }[] = [];
    for (const q of p.reverse()) {
      while (upper.length >= 2 && cross(upper[upper.length - 2]!, upper[upper.length - 1]!, q) <= 0) upper.pop();
      upper.push(q);
    }
    return lower.slice(0, -1).concat(upper.slice(0, -1)).map(q => `${q.x.toFixed(1)},${q.y.toFixed(1)}`).join(" ");
  };
  const corner = (lx: number, lz: number): { x: number; z: number } => offset(SLABS.at, HILL_GRID_DEG, lx, lz);
  const slabFoot = [corner(-SLABS.w / 2, -SLABS.d / 2), corner(SLABS.w / 2, -SLABS.d / 2), corner(SLABS.w / 2, SLABS.d / 2), corner(-SLABS.w / 2, SLABS.d / 2)];
  function drawSlabs(): void {
    const on = slabsOn && slabGrow > 0.001;
    slabGroup.style.display = on ? "" : "none";
    if (!on) return;
    const pts: { x: number; y: number }[] = [];
    slabHull.forEach((s, i) => {
      const y0 = slabLevel(i, slabGrow);
      const shows = slabGrow * 1.5 - (0.5 * i) / (slabCount - 1) > 0.003;
      s.hull.style.display = s.top.style.display = shows ? "" : "none";
      if (!shows) return;
      pts.length = 0;
      const top: string[] = [];
      for (const c of slabFoot) {
        P(c.x, y0, c.z, out);
        pts.push({ x: out.x, y: out.y });
        P(c.x, y0 + SLABS.thick, c.z, out);
        pts.push({ x: out.x, y: out.y });
        top.push(`${out.x.toFixed(1)},${out.y.toFixed(1)}`);
      }
      s.hull.setAttribute("points", hullOf(pts));
      s.top.setAttribute("points", top.join(" "));
      const picked = i === slabLine && slabAmount > 0.5;
      s.hull.setAttribute("class", picked ? "c-flat__slab is-picked" : slabAmount > 0.5 ? "c-flat__slab is-back" : "c-flat__slab");
    });
  }
  function drawSeats(): void {
    SEATS.forEach((at, i) => {
      const c = seatDots[i]!;
      const shows = i < Math.ceil(seatsUp - 0.001);
      c.style.display = shows ? "" : "none";
      if (!shows) return;
      P(at.x, 0, at.z, out);
      c.setAttribute("cx", out.x.toFixed(1));
      c.setAttribute("cy", out.y.toFixed(1));
      c.setAttribute("class", i < seatsVoted ? "is-lit" : "");
    });
  }

  let P = projector(lastPose, view.w, view.h);
  function draw(pose: Pose, stacks: boolean, route = lastRoute, slabs = slabsOn): void {
    lastPose = pose;
    lastStacks = stacks;
    lastRoute = route;
    slabsOn = slabs;
    P = projector(pose, view.w, view.h);
    // lines are drawn heavier close to the ground, as the scene draws them
    const near = 1 - Math.min(1, Math.max(0, (pose.distance - 1200) / 9000));
    el.style.setProperty("--near", near.toFixed(2));
    let d = "";
    if (routePoints && route > 0.001) {
      const n = Math.max(2, Math.round((routePoints.length / 2) * Math.min(1, route)));
      for (let i = 0; i < n; i++) {
        P(routePoints[i * 2]!, 0, routePoints[i * 2 + 1]!, out);
        if (i > 0 && !out.behind && !out2.behind) {
          const a = { x: out2.x, y: out2.y }, b = { x: out.x, y: out.y };
          if (clip(a, b, view.w, view.h)) d += `M${a.x.toFixed(1)} ${a.y.toFixed(1)}L${b.x.toFixed(1)} ${b.y.toFixed(1)}`;
        }
        out2.x = out.x;
        out2.y = out.y;
        out2.behind = out.behind;
      }
    }
    routePath.setAttribute("d", d);
    el.setAttribute("viewBox", `0 0 ${view.w} ${view.h}`);
    const { xy, count, minor: nMinor } = streets;
    const parts: [string[], string[]] = [[], []];
    for (let i = 0; i < count; i++) {
      P(xy[i * 4]!, 0, -xy[i * 4 + 1]!, out);
      P(xy[i * 4 + 2]!, 0, -xy[i * 4 + 3]!, out2);
      if (out.behind || out2.behind) continue;
      if (!clip(out, out2, view.w, view.h)) continue;
      parts[i < nMinor ? 0 : 1].push(`M${out.x.toFixed(1)} ${out.y.toFixed(1)}L${out2.x.toFixed(1)} ${out2.y.toFixed(1)}`);
    }
    minor.setAttribute("d", parts[0].join(""));
    major.setAttribute("d", parts[1].join(""));
    for (const p of points) {
      P(p.x, 0, p.z, out);
      const h = stacks ? p.n * 30 : 0;
      P(p.x, h, p.z, out2);
      // a point is drawn whole or not at all: nothing hangs over the edge of the window
      const hide = out.behind || out2.behind || out2.x < 5 || out2.x > view.w - 5 || out2.y < 5 || out2.y > view.h - 5 || out.x < 2 || out.x > view.w - 2 || out.y > view.h - 2;
      p.circle.setAttribute("cx", out2.x.toFixed(1));
      p.circle.setAttribute("cy", out2.y.toFixed(1));
      p.circle.style.display = hide ? "none" : "";
      p.sx = out2.x;
      p.sy = out2.y;
      p.shown = !hide;
      p.stem.setAttribute("x1", out.x.toFixed(1));
      p.stem.setAttribute("y1", out.y.toFixed(1));
      p.stem.setAttribute("x2", out2.x.toFixed(1));
      p.stem.setAttribute("y2", out2.y.toFixed(1));
      p.stem.style.display = hide || !stacks ? "none" : "";
    }
    classes();
    drawSlabs();
    drawSeats();
  }
  draw(lastPose, false);

  const eye: Eye = {
    project: (x, y, z, o) => P(x, y, z, o),
    heightAt: () => 0,
    heroLine(i) {
      const end = offset(SLABS.at, HILL_GRID_DEG, SLABS.w / 2, 0);
      return { x: end.x, y: slabLevel(i, slabGrow) + SLABS.thick / 2, z: end.z };
    },
    heroTop(o) {
      o.x = CASTLE.x;
      o.y = 0;
      o.z = CASTLE.z;
      return o;
    },
    setCastle() {},
    setHall() {},
    setLetters() {},
    setSeats(standing, voted) {
      if (standing === seatsUp && voted === seatsVoted) return;
      seatsUp = standing;
      seatsVoted = voted;
      drawSeats();
    },
    setSlabs(grow, line, amount) {
      if (grow === slabGrow && line === slabLine && amount === slabAmount) return;
      slabGrow = grow;
      slabLine = line;
      slabAmount = amount;
      drawSlabs();
    },
  };

  return {
    el,
    eye,
    draw,
    setRoute(points) {
      routePoints = points;
    },
    project: (x, y, z, o) => P(x, y, z, o),
    pick(x, y, reach = 14) {
      let best: string | null = null;
      let bestD = reach;
      for (const p of points) {
        if (!p.shown) continue;
        const dim = lit && !lit.has(p.record) ? 5 : 0;
        const dd = Math.hypot(p.sx - x, p.sy - y) + dim;
        if (dd < bestD) {
          bestD = dd;
          best = p.record;
        }
      }
      return best;
    },
    topOf(record, o) {
      const p = points.find(q => q.record === record);
      if (!p || !p.shown) return false;
      o.x = p.sx;
      o.y = p.sy;
      return true;
    },
    setLit(records) {
      lit = records;
      classes();
    },
    setHero(on) {
      heroOn = on;
      classes();
    },
    hover(record) {
      hovered = record;
      classes();
    },
    resize(next) {
      view = next;
      draw(lastPose, lastStacks, lastRoute, slabsOn);
    },
  };
}
