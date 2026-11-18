// The drawn stamp: the same stamp as the three.js one, projected to SVG in code from the same shape and the same
// light. It stands in until the 3D chunk has loaded, and it is the stamp when WebGL is missing. Two drawings are
// made, standing and lying on its back; leaning and squashing are 2D transforms of the standing one, and the
// shadow is a flat hatched shape (hard edges, the line colour) whose offset, size and hatch spacing follow the
// height.

import { MARK_BOX, MARK_TYPE } from "./mark";
import { DIE, FORESHORTEN, GROOVES, GROOVES_FINE, HANDLE, LIGHT, MOUNT, MOUNT_TOP, SCREWS, STAMP_HEIGHT, TONE_THRESHOLD, type Flat } from "./shape";
import type { StampPose, StampRenderer } from "./pose";

const NS = "http://www.w3.org/2000/svg";
const SE = FORESHORTEN.depth;
const CE = FORESHORTEN.up;
/** Outline width in die units (about 1.6 px at full size). */
const OUTLINE = 1.7;

const f = (n: number): string => (Math.round(n * 100) / 100).toString();
const points = (ps: Flat[]): string => ps.map(p => `${f(p.x)},${f(p.y)}`).join(" ");

type V3 = [number, number, number];

/** How the stamp is posed for a drawing: turned by `yaw` about its axis, tipped by `pitch` about the page's
 *  x axis (negative: the top goes away from the viewer), then raised by `lift` and moved toward the viewer by
 *  `near`. */
interface View {
  yaw: number;
  pitch: number;
  lift: number;
  near: number;
}

function camera(view: View): { at: (x: number, y: number, z: number) => V3; dir: (x: number, y: number, z: number) => V3; flat: (x: number, y: number, z: number) => Flat } {
  const cy = Math.cos(view.yaw);
  const sy = Math.sin(view.yaw);
  const cp = Math.cos(view.pitch);
  const sp = Math.sin(view.pitch);
  /** A direction of the stamp in view space: x right, y up the screen, z toward the viewer. */
  const dir = (x: number, y: number, z: number): V3 => {
    const px = x * cy - z * sy;
    const pz = x * sy + z * cy;
    const y2 = y * cp - pz * sp;
    const z2 = y * sp + pz * cp;
    return [px, y2 * CE - z2 * SE, y2 * SE + z2 * CE];
  };
  const at = (x: number, y: number, z: number): V3 => {
    const v = dir(x, y, z);
    return [v[0], v[1] + view.lift * CE - view.near * SE, v[2] + view.lift * SE + view.near * CE];
  };
  return { at, dir, flat: (x, y, z) => ({ x: at(x, y, z)[0], y: -at(x, y, z)[1] }) };
}

const lightOn = (n: V3): number => n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2] - TONE_THRESHOLD;

function el<K extends keyof SVGElementTagNameMap>(name: K, attrs: Record<string, string | number>): SVGElementTagNameMap[K] {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

interface Quad {
  corners: [V3, V3, V3, V3];
  normal: V3;
}

/** A box with its top edge cut back by `bevel`, as quads with outward normals (the stamp's own axes). */
function boxQuads(w: number, d: number, y0: number, y1: number, bevel: number): Quad[] {
  const hw = w / 2;
  const hd = d / 2;
  const ys = y1 - bevel;
  const tw = hw - bevel;
  const td = hd - bevel;
  const k = Math.SQRT1_2;
  const quads: Quad[] = [
    { corners: [[-hw, y0, -hd], [hw, y0, -hd], [hw, y0, hd], [-hw, y0, hd]], normal: [0, -1, 0] },
    { corners: [[-hw, y0, hd], [hw, y0, hd], [hw, ys, hd], [-hw, ys, hd]], normal: [0, 0, 1] },
    { corners: [[hw, y0, -hd], [-hw, y0, -hd], [-hw, ys, -hd], [hw, ys, -hd]], normal: [0, 0, -1] },
    { corners: [[hw, y0, hd], [hw, y0, -hd], [hw, ys, -hd], [hw, ys, hd]], normal: [1, 0, 0] },
    { corners: [[-hw, y0, -hd], [-hw, y0, hd], [-hw, ys, hd], [-hw, ys, -hd]], normal: [-1, 0, 0] },
    { corners: [[-tw, y1, td], [tw, y1, td], [tw, y1, -td], [-tw, y1, -td]], normal: [0, 1, 0] },
  ];
  if (bevel > 0) {
    quads.push(
      { corners: [[-hw, ys, hd], [hw, ys, hd], [tw, y1, td], [-tw, y1, td]], normal: [0, k, k] },
      { corners: [[hw, ys, -hd], [-hw, ys, -hd], [-tw, y1, -td], [tw, y1, -td]], normal: [0, k, -k] },
      { corners: [[hw, ys, hd], [hw, ys, -hd], [tw, y1, -td], [tw, y1, td]], normal: [k, k, 0] },
      { corners: [[-hw, ys, -hd], [-hw, ys, hd], [-tw, y1, td], [-tw, y1, -td]], normal: [-k, k, 0] },
    );
  }
  return quads;
}

/** A drawing of the stamp in one pose, with the centre of its die face (standing) at (0, 0). */
function drawStamp(view: View, words: readonly [string, string?]): { svg: SVGSVGElement; box: { x: number; y: number; w: number; h: number } } {
  const cam = camera(view);
  const svg = el("svg", { class: "stamp2d__body", "aria-hidden": "true", focusable: "false" });
  const face = "var(--font-stamp)";

  /** A flat matrix that carries a rectangle's own coordinates (u right, v down) to the screen. */
  const matrix = (origin: V3, u: V3, v: V3): string => {
    const o = cam.flat(...origin);
    const a = cam.flat(origin[0] + u[0], origin[1] + u[1], origin[2] + u[2]);
    const b = cam.flat(origin[0] + v[0], origin[1] + v[1], origin[2] + v[2]);
    return `matrix(${f(a.x - o.x)} ${f(a.y - o.y)} ${f(b.x - o.x)} ${f(b.y - o.y)} ${f(o.x)} ${f(o.y)})`;
  };

  // ---- the die and the mount: boxes --------------------------------------------------------------------------
  function box(quads: Quad[], rubber: boolean, extra?: (g: SVGGElement) => void): { depth: number; node: SVGGElement } {
    const g = el("g", {});
    const under = el("g", { class: "stamp2d__ink", "stroke-width": OUTLINE * 2, "stroke-linejoin": "round" });
    const over = el("g", {});
    const crease = el("g", { class: "stamp2d__crease", fill: "none", "stroke-width": 0.9, "stroke-linejoin": "round" });
    let depth = 0;
    let n = 0;
    for (const q of quads) {
      const normal = cam.dir(...q.normal);
      for (const c of q.corners) {
        depth += cam.at(...c)[2];
        n += 1;
      }
      if (normal[2] <= 0.02) continue;
      const ps = points(q.corners.map(c => cam.flat(...c)));
      under.append(el("polygon", { points: ps }));
      // the die's underside is its inked face: the ground of the relief
      const inked = rubber && q.normal[1] < 0;
      over.append(el("polygon", { points: ps, class: inked ? "stamp2d__relief" : `${rubber ? "stamp2d__rubber" : "stamp2d__wood"} is-${lightOn(normal) > 0 ? "lit" : "shade"}` }));
      crease.append(el("polygon", { points: ps }));
    }
    g.append(under, over);
    if (!rubber) over.append(crease);
    extra?.(over);
    return { depth: depth / Math.max(1, n), node: g };
  }

  const hw = DIE.width / 2;
  const hd = DIE.depth / 2;
  const die = box(boxQuads(DIE.width, DIE.depth, 0, DIE.height, 0), true, g => {
    // the face, when it shows: the frame and the words in relief, mirrored as on a real die
    if (cam.dir(0, -1, 0)[2] <= 0.02) return;
    const W = MARK_BOX.width;
    const H = MARK_BOX.height;
    const relief = el("g", { class: "stamp2d__rubber is-lit", transform: matrix([hw, 0, hd], [-1, 0, 0], [0, 0, -1]) });
    relief.append(
      el("path", {
        "fill-rule": "evenodd",
        d: `M3 3h${W - 6}v${H - 6}H3zM9.5 9.5v${H - 19}h${W - 19}V9.5zM14 14h${W - 28}v${H - 28}H14zM16 16v${H - 32}h${W - 32}V16z`,
      }),
    );
    const set = words[1] ? MARK_TYPE.first : MARK_TYPE.alone;
    const first = el("text", { x: W / 2, y: set.y, "text-anchor": "middle", "font-size": set.size, "font-weight": 800, textLength: set.length, lengthAdjust: "spacingAndGlyphs" });
    first.textContent = words[0];
    first.style.fontFamily = face;
    relief.append(first);
    if (words[1]) {
      const second = el("text", { x: W / 2, y: MARK_TYPE.second.y, "text-anchor": "middle", "font-size": MARK_TYPE.second.size, "font-weight": 800, textLength: MARK_TYPE.second.length, lengthAdjust: "spacing" });
      second.textContent = words[1];
      second.style.fontFamily = face;
      relief.append(second);
    }
    g.append(relief);
  });

  const mw = MOUNT.width / 2;
  const md = MOUNT.depth / 2;
  const mount = box(boxQuads(MOUNT.width, MOUNT.depth, DIE.height, MOUNT_TOP, MOUNT.bevel), false, g => {
    // two screw heads on the top face, either side of the handle
    if (cam.dir(0, 1, 0)[2] > 0.02) {
      for (const [sx, sz] of SCREWS.at) {
        const screw = el("g", { transform: matrix([sx, MOUNT_TOP, sz], [1, 0, 0], [0, 0, 1]), class: "stamp2d__screw" });
        const a = (SCREWS.slot * Math.PI) / 180;
        const r = SCREWS.radius;
        screw.append(
          el("circle", { r, class: "stamp2d__wood is-lit" }),
          el("circle", { r, fill: "none", class: "stamp2d__crease", "stroke-width": 1.5 }),
          el("line", { x1: f(-Math.cos(a) * r * 0.78), y1: f(-Math.sin(a) * r * 0.78), x2: f(Math.cos(a) * r * 0.78), y2: f(Math.sin(a) * r * 0.78), class: "stamp2d__crease", "stroke-width": 1.4 }),
        );
        g.append(screw);
      }
    }
    // the paper label on the front, which says what the stamp stamps
    if (cam.dir(0, 0, 1)[2] <= 0.02) return;
    const h = MOUNT.height - MOUNT.bevel;
    const w = MOUNT.width;
    const label = el("g", { transform: matrix([-mw, MOUNT_TOP - MOUNT.bevel, md], [1, 0, 0], [0, -1, 0]) });
    label.append(el("rect", { x: w * 0.2, y: h * 0.17, width: w * 0.6, height: h * 0.66, class: "stamp2d__wood is-lit" }));
    const text = el("text", { x: w / 2, y: h * 0.5 + h * 0.46 * 0.36, "text-anchor": "middle", "font-size": h * 0.46, "font-weight": 800, textLength: w * 0.52, lengthAdjust: "spacing", class: "stamp2d__lettering" });
    text.textContent = words.filter(Boolean).join(" ");
    text.style.fontFamily = face;
    label.append(text);
    g.append(label);
  });

  // ---- the handle: rings up the axis ----------------------------------------------------------------------------
  // finer than the profile's own points, so the edge of the shade runs smoothly
  const profile: { r: number; y: number; a: number; b: number }[] = [];
  const raw = HANDLE.map(([r, y]) => ({ r, y: MOUNT_TOP + y }));
  const normalAt = (i: number): [number, number] => {
    const prev = raw[Math.max(0, i - 1)] ?? raw[0];
    const next = raw[Math.min(raw.length - 1, i + 1)] ?? raw[raw.length - 1];
    if (!prev || !next) return [1, 0];
    const dr = next.r - prev.r;
    const dy = next.y - prev.y;
    const l = Math.hypot(dr, dy) || 1;
    return [dy / l, -dr / l];
  };
  const SUB = 3;
  for (let i = 0; i + 1 < raw.length; i++) {
    const p = raw[i];
    const q = raw[i + 1];
    if (!p || !q) continue;
    const [a0, b0] = normalAt(i);
    const [a1, b1] = normalAt(i + 1);
    for (let j = 0; j < SUB; j++) {
      const t = j / SUB;
      const a = a0 + (a1 - a0) * t;
      const b = b0 + (b1 - b0) * t;
      const l = Math.hypot(a, b) || 1;
      profile.push({ r: p.r + (q.r - p.r) * t, y: p.y + (q.y - p.y) * t, a: a / l, b: b / l });
    }
  }
  const top = raw[raw.length - 1];
  if (top) profile.push({ r: top.r, y: top.y, a: 0, b: 1 });

  const axis = cam.dir(0, 1, 0);
  /** How round a ring looks: 1 seen along the axis, 0 edge on. */
  const round = Math.abs(axis[2]);
  const rings = profile.map(p => {
    const c = cam.at(0, p.y, 0);
    return { ...p, cx: c[0], cy: -c[1], depth: c[2] };
  });
  const ellipse = (ring: { r: number; cx: number; cy: number }): string =>
    ring.r < 0.5 ? "" : `M${f(ring.cx - ring.r)} ${f(ring.cy)}a${f(ring.r)} ${f(ring.r * round)} 0 1 1 ${f(2 * ring.r)} 0a${f(ring.r)} ${f(ring.r * round)} 0 1 1 ${f(-2 * ring.r)} 0z`;
  const bandHull = (a: (typeof rings)[number], b: (typeof rings)[number]): string =>
    `${ellipse(a)}${ellipse(b)}M${f(a.cx - a.r)} ${f(a.cy)}L${f(b.cx - b.r)} ${f(b.cy)}L${f(b.cx + b.r)} ${f(b.cy)}L${f(a.cx + a.r)} ${f(a.cy)}z`;

  /** Where on a ring the surface faces the viewer and is in shade: one run of angles, as points on the screen. */
  const STEPS = 72;
  const shadeRun = (ring: (typeof rings)[number]): Flat[] => {
    const shaded: boolean[] = [];
    const where: Flat[] = [];
    for (let i = 0; i < STEPS; i++) {
      const phi = (i / STEPS) * Math.PI * 2;
      const n = cam.dir(Math.cos(phi) * ring.a, ring.b, Math.sin(phi) * ring.a);
      shaded.push(n[2] > 0 && lightOn(n) <= 0);
      const p = cam.at(Math.cos(phi) * ring.r, ring.y, Math.sin(phi) * ring.r);
      where.push({ x: p[0], y: -p[1] });
    }
    // the longest run, walking round from a sample that is not in it
    const start = shaded.indexOf(false);
    if (start < 0) return where;
    let best: number[] = [];
    let run: number[] = [];
    for (let k = 1; k <= STEPS; k++) {
      const i = (start + k) % STEPS;
      if (shaded[i]) run.push(i);
      else {
        if (run.length > best.length) best = run;
        run = [];
      }
    }
    if (run.length > best.length) best = run;
    return best.map(i => where[i] as Flat);
  };

  const handle = el("g", {});
  const handleInk = el("g", { class: "stamp2d__ink", "stroke-width": OUTLINE * 2, "stroke-linejoin": "round" });
  const handleOver = el("g", {});
  let hull = "";
  // far bands first, so nearer ones cover them
  const order = rings.map((_, i) => i).slice(0, -1);
  const rising = (rings[rings.length - 1]?.depth ?? 0) >= (rings[0]?.depth ?? 0);
  if (!rising) order.reverse();
  for (const i of order) {
    const a = rings[i];
    const b = rings[i + 1];
    if (!a || !b) continue;
    const d = bandHull(a, b);
    hull += d;
    handleOver.append(el("path", { d, class: "stamp2d__wood is-lit stamp2d__band" }));
    const ra = shadeRun(a);
    const rb = shadeRun(b);
    if (ra.length > 1 && rb.length > 1) handleOver.append(el("polygon", { points: points([...ra, ...rb.reverse()]), class: "stamp2d__wood is-shade stamp2d__band" }));
    // a groove turned into the handle: an ink line round it, where it faces the viewer (the finer ones are thinner)
    for (const groove of [...GROOVES, ...GROOVES_FINE]) {
      const fine = !(GROOVES as readonly number[]).includes(groove);
      const y = MOUNT_TOP + groove;
      if (!(a.y <= y && b.y > y)) continue;
      const pts: Flat[] = [];
      for (let k = 0; k <= STEPS; k++) {
        const phi = (k / STEPS) * Math.PI * 2;
        const n = cam.dir(Math.cos(phi) * a.a, a.b, Math.sin(phi) * a.a);
        if (n[2] <= 0) {
          if (pts.length > 1) break;
          pts.length = 0;
          continue;
        }
        const rr = a.r + ((b.r - a.r) * (y - a.y)) / Math.max(0.001, b.y - a.y);
        const p = cam.at(Math.cos(phi) * rr, y, Math.sin(phi) * rr);
        pts.push({ x: p[0], y: -p[1] });
      }
      if (pts.length > 1) handleOver.append(el("polyline", { points: points(pts), class: "stamp2d__crease", fill: "none", "stroke-width": fine ? 0.8 : 1.3 }));
    }
  }
  handleInk.append(el("path", { d: hull }));
  handle.append(handleInk, handleOver);
  const handleDepth = rings.reduce((s, r) => s + r.depth, 0) / Math.max(1, rings.length);

  // the furthest part first
  const parts = [die, mount, { depth: handleDepth, node: handle }].sort((p, q) => p.depth - q.depth);
  for (const part of parts) svg.append(part.node);

  // a box that holds the drawing in either pose
  const reach = STAMP_HEIGHT + 30;
  const left = -MOUNT.width / 2 - 40;
  const topEdge = -reach;
  const w = MOUNT.width + 80;
  const h = reach + MOUNT.depth + 60;
  svg.setAttribute("viewBox", `${f(left)} ${f(topEdge)} ${f(w)} ${f(h)}`);
  return { svg, box: { x: left, y: topEdge, w, h } };
}

export function createStamp2D(tiltDegrees: number, words: readonly [string, string?] = ["APPROVED", "WITH CONDITIONS"]): StampRenderer {
  const yaw = (tiltDegrees * Math.PI) / 180;
  const root = document.createElement("div");
  root.className = "stamp-layer stamp2d";
  root.setAttribute("aria-hidden", "true");
  const actor = document.createElement("div");
  actor.className = "stamp2d__actor";
  const shadow = document.createElement("div");
  shadow.className = "stamp2d__shadow";
  const lean = document.createElement("div");
  lean.className = "stamp2d__lean";
  const standing = drawStamp({ yaw, pitch: 0, lift: 0, near: 0 }, words);
  // on its back: the top away from the viewer, resting on the back of the mount (as the three.js stamp lies)
  const lying = drawStamp({ yaw, pitch: -(Math.PI / 2 + 0.02), lift: MOUNT.depth / 2, near: MOUNT_TOP * 0.5 }, words);
  lying.svg.classList.add("stamp2d__lying");
  lying.svg.style.opacity = "0";
  lean.append(standing.svg, lying.svg);
  actor.append(shadow, lean);
  root.append(actor);

  let scale = 1;
  let gap = "";
  // the shadow leans the way the die does on the page (the tilt, foreshortened)
  const seen = Math.atan(Math.tan(yaw) * SE);

  return {
    el: root,
    resize(_w, _h, dieWidth) {
      scale = dieWidth / DIE.width;
      for (const { svg, box } of [standing, lying]) {
        svg.style.width = `${box.w * scale}px`;
        svg.style.height = `${box.h * scale}px`;
        svg.style.left = `${box.x * scale}px`;
        svg.style.top = `${box.y * scale}px`;
        svg.style.transformOrigin = `${-box.x * scale}px ${-box.y * scale}px`;
      }
      shadow.style.width = `${(DIE.width + 10) * scale}px`;
      shadow.style.height = `${((DIE.depth + 10) * SE) * scale}px`;
      shadow.style.setProperty("--hatch-w", `${Math.max(1, 1.5 * scale).toFixed(2)}px`);
      gap = "";
    },
    draw(p: StampPose) {
      actor.style.transform = `translate3d(${p.x}px, ${p.y}px, 0)`;
      actor.style.opacity = p.alpha >= 0.999 ? "" : String(p.alpha);
      const lift = p.h * CE;
      // a lean toward or away from the viewer shows as the drawing getting a little shorter or taller
      const nod = 1 - Math.max(-0.1, Math.min(0.1, p.leanZ * 0.3));
      const near = 1 + (p.zoom || 0);
      lean.style.transform = `translate3d(0, ${-lift}px, 0) rotate(${p.leanX * 0.9}rad) scale(${(1 + p.squash * 0.42) * near}, ${(1 - p.squash) * nod * near})`;
      // lying down: the standing drawing tips back and gives way to the lying one
      const l = Math.max(0, Math.min(1, p.lying));
      const cross = l * l * (3 - 2 * l);
      standing.svg.style.opacity = cross > 0.001 ? String(1 - cross) : "";
      standing.svg.style.transform = cross > 0.001 ? `scale(1, ${1 - cross * 0.3})` : "";
      lying.svg.style.opacity = String(cross);
      lying.svg.style.transform = `scale(1, ${0.82 + cross * 0.18})`;
      // the shadow: flat and hatched. The higher the stamp, the further it is thrown, the larger it is and the
      // wider its hatching opens
      const hn = p.h / scale;
      const grow = 1 + hn * 0.0012 + l * 0.06;
      shadow.style.transform =
        `translate(-50%, -50%) translate3d(${p.h * 0.34 + l * 10 * scale}px, ${p.h * 0.2 - l * 22 * scale}px, 0) rotate(${seen}rad) scale(${grow}, ${grow + l * 0.9})`;
      // (standing on something, it throws no shadow that can be seen: the die covers it)
      shadow.style.opacity = String((1 - Math.min(0.8, hn * 0.0036)) * (1 - l * 0.3) * Math.min(1, hn / 10 + l));
      const next = ((3.6 + hn * 0.03) * scale).toFixed(1);
      if (next !== gap) {
        gap = next;
        shadow.style.setProperty("--hatch-gap", `${next}px`);
      }
    },
    setPalette() {
      // the drawing is coloured by CSS variables: nothing to do
    },
    busy: () => false,
    destroy() {
      root.remove();
    },
  };
}
