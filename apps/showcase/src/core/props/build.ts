// The parts a paper pop-up is made of, for objects standing on the map of core/world: flat plates cut to an
// outline, simple solids, and the three ways a part comes up out of the map (a leaf that hinges up from flat, a
// part that grows from its base, a part that slides up out of the one below it). Everything is drawn by
// core/world's printObject, so it is paper where the light falls, cobalt in shadow and inked along its edges.
// Loaded with a page's 3D chunk (it needs three.js). Nothing here knows about any page.

import {
  BoxGeometry,
  BufferGeometry,
  CylinderGeometry,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  Mesh,
  ShaderMaterial,
  Shape,
  ShapeGeometry,
  type Object3D,
} from "three";
import { printObject, RELIEF_PARS, type PrintObject, type PrintOptions, type World } from "../world";

export const RAD = Math.PI / 180;

export type Pt = readonly [number, number];

// ---- geometry -----------------------------------------------------------------------------------------------------

/** A box standing on y. */
export function box(w: number, h: number, d: number, x = 0, y = 0, z = 0, ry = 0): BufferGeometry {
  const g = new BoxGeometry(w, h, d);
  g.translate(0, h / 2, 0);
  if (ry) g.rotateY(ry * RAD);
  g.translate(x, y, z);
  return g;
}

/** A drum standing on y. `open` leaves its two ends off (a tube). */
export function drum(r: number, h: number, x = 0, y = 0, z = 0, segments = 20, rTop = r, open = false): BufferGeometry {
  const g = new CylinderGeometry(rTop, r, h, segments, 1, open);
  g.translate(x, y + h / 2, z);
  return g;
}

/** A disc facing the viewer of a wall (its axis along z), centred on a point. */
export function disc(r: number, depth: number, x: number, y: number, z: number, segments = 20): BufferGeometry {
  const g = new CylinderGeometry(r, r, depth, segments);
  g.rotateX(90 * RAD);
  g.translate(x, y, z);
  return g;
}

/** Several geometries as one (positions and normals only). The parts are disposed. */
export function merge(...parts: BufferGeometry[]): BufferGeometry {
  const flat = parts.map(p => (p.index ? p.toNonIndexed() : p));
  let total = 0;
  for (const p of flat) total += p.getAttribute("position").count;
  const position = new Float32Array(total * 3);
  const normal = new Float32Array(total * 3);
  let at = 0;
  for (const p of flat) {
    position.set(p.getAttribute("position").array as Float32Array, at * 3);
    normal.set(p.getAttribute("normal").array as Float32Array, at * 3);
    at += p.getAttribute("position").count;
  }
  const g = new BufferGeometry();
  g.setAttribute("position", new Float32BufferAttribute(position, 3));
  g.setAttribute("normal", new Float32BufferAttribute(normal, 3));
  for (const p of parts) p.dispose();
  for (const p of flat) p.dispose();
  return g;
}

/** A flat plate cut to an outline, in the plane z = 0, facing +z: x across, y up. `holes` are cut out of it. */
export function plate(outline: readonly Pt[], holes: readonly (readonly Pt[])[] = [], z = 0): BufferGeometry {
  const shape = new Shape();
  outline.forEach((p, i) => (i === 0 ? shape.moveTo(p[0], p[1]) : shape.lineTo(p[0], p[1])));
  shape.closePath();
  for (const hole of holes) {
    const path = new Shape();
    hole.forEach((p, i) => (i === 0 ? path.moveTo(p[0], p[1]) : path.lineTo(p[0], p[1])));
    path.closePath();
    shape.holes.push(path);
  }
  const g = new ShapeGeometry(shape);
  g.deleteAttribute("uv");
  if (z) g.translate(0, 0, z);
  return g;
}

/** A plate lying flat, facing up: the outline's x is x, its y runs towards -z (so a plan drawn north-up lies north-up). */
export function slab(outline: readonly Pt[], y = 0, holes: readonly (readonly Pt[])[] = []): BufferGeometry {
  const g = plate(outline, holes);
  g.rotateX(-90 * RAD);
  if (y) g.translate(0, y, 0);
  return g;
}

/** The outline of a rectangle standing on y = `y`, centred on x = `x`. */
export function rect(w: number, h: number, x = 0, y = 0): Pt[] {
  return [
    [x - w / 2, y],
    [x + w / 2, y],
    [x + w / 2, y + h],
    [x - w / 2, y + h],
  ];
}

/** The outline of an opening with a round head: `h` is its whole height. */
export function arch(w: number, h: number, x = 0, y = 0, segments = 7): Pt[] {
  const r = w / 2;
  const pts: Pt[] = [
    [x - r, y],
    [x + r, y],
  ];
  for (let i = 0; i <= segments; i++) {
    const a = (i / segments) * Math.PI;
    pts.push([x + Math.cos(a) * r, y + h - r + Math.sin(a) * r]);
  }
  return pts;
}

/** The outline of a battlement: a band `band` high and `length` long (from x = 0), with teeth `tooth` wide and
 *  `rise` high on top, as many as fit, the first and the last at its two ends. */
export function battlement(length: number, band: number, tooth: number, rise: number, gap = tooth * 0.8): Pt[] {
  const n = Math.max(2, Math.round((length + gap) / (tooth + gap)));
  const g = (length - n * tooth) / (n - 1);
  const top = band + rise;
  const pts: Pt[] = [
    [0, 0],
    [length, 0],
  ];
  for (let i = n - 1; i >= 0; i--) {
    const x0 = i * (tooth + g);
    pts.push([i === n - 1 ? length : x0 + tooth, top], [x0, top]);
    if (i > 0) pts.push([x0, band], [x0 - g, band]);
  }
  return pts;
}

// ---- the ways a part comes up ---------------------------------------------------------------------------------------

/** A part of a pop-up: `set(0)` is how it lies in the closed book, `set(1)` is standing. */
export interface Fold {
  group: Group;
  /** 0 to 1 (values a little past 1 are an overshoot). */
  set(amount: number): void;
}

const keep = (world: World, apply: (a: number) => void): ((a: number) => void) => {
  let last = Number.NaN;
  return a => {
    if (a === last) return;
    last = a;
    apply(a);
    world.invalidate();
  };
};

export interface HingeOptions {
  /** Where the hinge's middle is. */
  at: readonly [number, number, number];
  /** Degrees about y: which way the standing leaf faces (0: +z, 90: +x, 180: -z, -90: -x). */
  yaw?: number;
  /** Degrees the leaf is turned about its hinge when closed: -90 lies flat towards its own back (inwards), 90
   *  lies flat on its face (outwards). Default -90. */
  from?: number;
}

/** A leaf: things drawn in a wall's own plane (x along its foot, y up it, z out of its face) that hinge up about
 *  the foot. */
export function hinge(world: World, children: Object3D[], options: HingeOptions): Fold {
  const group = new Group();
  group.position.set(options.at[0], options.at[1], options.at[2]);
  group.rotation.y = (options.yaw ?? 0) * RAD;
  const leaf = new Group();
  leaf.add(...children);
  group.add(leaf);
  const from = (options.from ?? -90) * RAD;
  const set = keep(world, a => {
    leaf.rotation.x = from * (1 - a);
  });
  set(0);
  return { group, set };
}

/** A part that grows up from its base (its height scales from nothing). Hidden at 0. */
export function grow(world: World, children: Object3D[], at: readonly [number, number, number] = [0, 0, 0]): Fold {
  const group = new Group();
  group.position.set(at[0], at[1], at[2]);
  group.add(...children);
  const set = keep(world, a => {
    group.visible = a > 0.002;
    group.scale.y = Math.max(0.0001, a);
  });
  set(0);
  return { group, set };
}

/** A part that slides straight up from one height to another (a floor rising between its walls, a section of a
 *  telescope coming out of the one below). `hide` keeps it out of sight until it starts to move. */
export function riser(world: World, children: Object3D[], from: readonly [number, number, number], to: readonly [number, number, number], hide = false): Fold {
  const group = new Group();
  group.add(...children);
  const set = keep(world, a => {
    group.visible = !hide || a > 0.002;
    group.position.set(from[0] + (to[0] - from[0]) * a, from[1] + (to[1] - from[1]) * a, from[2] + (to[2] - from[2]) * a);
  });
  set(0);
  return { group, set };
}

// ---- printed parts --------------------------------------------------------------------------------------------------

/** A flat sheet of paper cut to an outline (both sides drawn). */
export function card(world: World, geometry: BufferGeometry, options: PrintOptions = {}): PrintObject {
  return printObject(world, geometry, { side: DoubleSide, crease: 1, ...options });
}

/** A flat shape in the line colour (a window, a door): inked solid, outlined. */
export function inked(world: World, geometry: BufferGeometry, options: PrintOptions = {}): PrintObject {
  const object = printObject(world, geometry, { side: DoubleSide, crease: 1, flat: true, outline: 0.9, ...options });
  object.setFill(1);
  return object;
}

// ---- cast shadows ---------------------------------------------------------------------------------------------------

const SHADOW_VERT = /* glsl */ `
uniform vec3 uLight;
uniform float uBase;
uniform float uOnRelief;
${RELIEF_PARS}
void main() {
  vec4 w = modelMatrix * vec4(position, 1.0);
  float t = max(0.0, w.y - uBase) / uLight.y;
  w.xyz -= uLight * t;
  w.y = mix(uBase, relief(w.xz), uOnRelief) + 0.14;
  gl_Position = projectionMatrix * viewMatrix * w;
}
`;
const SHADOW_FRAG = /* glsl */ `
uniform vec3 uShade;
void main() {
  gl_FragColor = vec4(uShade, 1.0);
}
`;

export interface Shadow {
  mesh: Mesh;
  /** The height (world y) of the ground the thing stands on. */
  setBase(y: number): void;
}

/** The flat shadow a solid casts along the world's light: on the ground as the street lines know it (following a
 *  rise), or on a level. Give it a plain solid the size of the thing, not the thing's own folding parts. Shadows
 *  are drawn before the printed faces, so a shadow that must lie on a printed face (a sheet of paper) needs a
 *  `renderOrder` above 2. */
export function castShadow(world: World, geometry: BufferGeometry, onRelief = true, renderOrder = -0.5): Shadow {
  const u = world.uniforms;
  const material = new ShaderMaterial({
    vertexShader: SHADOW_VERT,
    fragmentShader: SHADOW_FRAG,
    side: DoubleSide,
    depthWrite: false,
    uniforms: { uLight: u.uLight, uShade: u.uShade, uRelief: u.uRelief, uReliefAmount: u.uReliefAmount, uBase: { value: 0 }, uOnRelief: { value: onRelief ? 1 : 0 } },
  });
  const mesh = new Mesh(geometry, material);
  mesh.renderOrder = renderOrder;
  mesh.frustumCulled = false;
  const base = material.uniforms.uBase as { value: number };
  return {
    mesh,
    setBase(y) {
      if (base.value !== y) {
        base.value = y;
        world.invalidate();
      }
    },
  };
}

/** Eases for folds: `settle` arrives a little past and comes back (paper has spring). */
export const settle = (t: number): number => {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  const s = 1.35;
  const u = t - 1;
  return 1 + u * u * ((s + 1) * u + s);
};
export const smooth = (t: number): number => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));
/** 0 before a, 1 after b, linear between. */
export const span = (t: number, a: number, b: number): number => (t <= a ? 0 : t >= b ? 1 : (t - a) / (b - a));
