// What the map gains when the camera comes close: streets with a width (a paper band between two inked kerbs),
// the ground of a rise as a surface (so what stands behind or below it is hidden), and hachures: the short
// pencil strokes a cartographer draws down a slope. All follow the world's relief in the vertex shader.

import { BufferGeometry, Float32BufferAttribute, Group, Mesh, PlaneGeometry, ShaderMaterial } from "three";
import { createSegments, reliefHeight, RELIEF_PARS, type Relief, type Segments, type Streets, type World } from "../world";
import { card, merge, plate, RAD, type Pt } from "./build";

const ROAD_VERT = /* glsl */ `
attribute vec2 aSide;
uniform float uHalf;
uniform vec3 uArea;
uniform float uLift;
${RELIEF_PARS}
void main() {
  vec3 p = position;
  // full width near the middle of the area, tapering to a hairline at its edge
  float k = 1.0 - smoothstep(uArea.z * 0.55, uArea.z, distance(p.xz, uArea.xy));
  p.xz += aSide * uHalf * k;
  p.y = relief(p.xz) + uLift;
  gl_Position = projectionMatrix * viewMatrix * vec4(p, 1.0);
}
`;
const FLAT_FRAG = /* glsl */ `
uniform vec3 uColor;
void main() {
  gl_FragColor = vec4(uColor, 1.0);
}
`;

export interface Roads {
  group: Group;
  /** 0 to 1: how wide the streets are drawn (0 hides them: only the centre lines of the map remain). */
  setWidth(amount: number): void;
}

export interface RoadsOptions {
  /** The middle of the area, and how far out the streets have a width. */
  x: number;
  z: number;
  radius: number;
  /** Half the width of a street in metres (default 4.2). */
  half?: number;
  /** The width of the kerb line in metres (default 0.3). */
  kerb?: number;
}

/** The streets near a point, as bands of the second paper colour between two ink kerbs. */
export function createRoads(world: World, streets: Streets, options: RoadsOptions): Roads {
  const { xy, count } = streets;
  const half = options.half ?? 4.2;
  const kerb = options.kerb ?? 0.2;
  const position: number[] = [];
  const side: number[] = [];
  const nodes = new Set<string>();
  const cap = (x: number, z: number): void => {
    const key = `${x},${z}`;
    if (nodes.has(key)) return;
    nodes.add(key);
    const n = 10;
    for (let i = 0; i < n; i++) {
      const a0 = (i / n) * Math.PI * 2, a1 = ((i + 1) / n) * Math.PI * 2;
      position.push(x, 0, z, x, 0, z, x, 0, z);
      side.push(0, 0, Math.cos(a1), Math.sin(a1), Math.cos(a0), Math.sin(a0));
    }
  };
  const r2 = options.radius * options.radius;
  for (let i = 0; i < count; i++) {
    const x1 = xy[i * 4]!, z1 = -xy[i * 4 + 1]!, x2 = xy[i * 4 + 2]!, z2 = -xy[i * 4 + 3]!;
    const d1 = (x1 - options.x) ** 2 + (z1 - options.z) ** 2;
    const d2 = (x2 - options.x) ** 2 + (z2 - options.z) ** 2;
    if (d1 > r2 && d2 > r2) continue;
    const len = Math.hypot(x2 - x1, z2 - z1);
    if (len < 0.5) continue;
    const nx = -(z2 - z1) / len, nz = (x2 - x1) / len;
    // a long street is cut into pieces, so it follows the rise of the ground
    const pieces = Math.max(1, Math.ceil(len / 24));
    for (let k = 0; k < pieces; k++) {
      const ax = x1 + ((x2 - x1) * k) / pieces, az = z1 + ((z2 - z1) * k) / pieces;
      const bx = x1 + ((x2 - x1) * (k + 1)) / pieces, bz = z1 + ((z2 - z1) * (k + 1)) / pieces;
      position.push(ax, 0, az, bx, 0, bz, bx, 0, bz, ax, 0, az, bx, 0, bz, ax, 0, az);
      side.push(nx, nz, nx, nz, -nx, -nz, nx, nz, -nx, -nz, -nx, -nz);
    }
    cap(x1, z1);
    cap(x2, z2);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(position, 3));
  geometry.setAttribute("aSide", new Float32BufferAttribute(side, 2));
  const u = world.uniforms;
  const layer = (color: { value: unknown }, lift: number, order: number): { mesh: Mesh; half: { value: number } } => {
    const uHalf = { value: 0 };
    const material = new ShaderMaterial({
      vertexShader: ROAD_VERT,
      fragmentShader: FLAT_FRAG,
      depthWrite: false,
      side: 2,
      uniforms: { uRelief: u.uRelief, uReliefAmount: u.uReliefAmount, uColor: color, uHalf, uArea: { value: [options.x, options.z, options.radius] }, uLift: { value: lift } },
    });
    const mesh = new Mesh(geometry, material);
    mesh.frustumCulled = false;
    mesh.renderOrder = order;
    return { mesh, half: uHalf };
  };
  const casing = layer(u.uInk, 0.05, -2);
  const fill = layer(u.uPaper2, 0.09, -1.5);
  const group = new Group();
  group.add(casing.mesh, fill.mesh);
  group.visible = false;
  let last = -1;
  return {
    group,
    setWidth(amount) {
      const a = amount < 0.01 ? 0 : amount;
      if (a === last) return;
      last = a;
      group.visible = a > 0;
      fill.half.value = half * a;
      // the kerb keeps its weight while the street narrows, until the street is nearly a line
      casing.half.value = half * a + kerb * Math.min(1, a * 3);
      world.invalidate();
    },
  };
}

const GROUND_VERT = /* glsl */ `
${RELIEF_PARS}
void main() {
  vec4 w = modelMatrix * vec4(position, 1.0);
  w.y = relief(w.xz) - 0.4;
  gl_Position = projectionMatrix * viewMatrix * w;
}
`;

export interface Ground3D {
  mesh: Mesh;
}

/** The ground of a rise as a paper-coloured surface: it draws nothing you can see, and hides what is under or
 *  behind the hill. `size` is the side of the square of ground, in metres. */
export function createGround(world: World, relief: Relief, size = relief.radius * 4.4, cells = 72): Ground3D {
  const geometry = new PlaneGeometry(size, size, cells, cells);
  geometry.rotateX(-Math.PI / 2);
  geometry.translate(relief.x, 0, relief.z);
  const u = world.uniforms;
  const material = new ShaderMaterial({
    vertexShader: GROUND_VERT,
    fragmentShader: FLAT_FRAG,
    polygonOffset: true,
    polygonOffsetFactor: 2,
    polygonOffsetUnits: 2,
    uniforms: { uRelief: u.uRelief, uReliefAmount: u.uReliefAmount, uColor: u.uPaper },
  });
  const mesh = new Mesh(geometry, material);
  mesh.frustumCulled = false;
  mesh.renderOrder = -3;
  return { mesh };
}

export interface Hachures {
  lines: Segments;
  /** 0 to 1: drawn on from the top of the rise outward. */
  setDraw(amount: number): void;
}

export interface HachureOptions {
  /** Leave these places bare: return true for a point where nothing should be drawn. */
  avoid?: (x: number, z: number) => boolean;
  /** Streets to keep clear of (strokes within `clear` metres of a street are left out). */
  streets?: Streets;
  clear?: number;
  /** Metres between the rings of strokes (default 20) and between strokes along a ring (default 8.5). */
  ring?: number;
  spacing?: number;
}

/** Hachures down the slopes of a rise: short pencil strokes pointing downhill, longer where it is steeper. */
export function createHachures(world: World, relief: Relief, options: HachureOptions = {}): Hachures {
  const ringStep = options.ring ?? 20;
  const spacing = options.spacing ?? 8.5;
  const clear = options.clear ?? 8;
  const k = 0.36 * relief.radius * relief.radius;
  const slopeAt = (r: number): number => ((relief.height * 2 * r) / k) * Math.exp(-(r * r) / k);
  // the streets near the rise, for keeping clear of them
  const near: number[] = [];
  if (options.streets) {
    const { xy, count } = options.streets;
    const reach = relief.radius * 1.3;
    for (let i = 0; i < count; i++) {
      const x1 = xy[i * 4]!, z1 = -xy[i * 4 + 1]!, x2 = xy[i * 4 + 2]!, z2 = -xy[i * 4 + 3]!;
      if (Math.hypot((x1 + x2) / 2 - relief.x, (z1 + z2) / 2 - relief.z) < reach) near.push(x1, z1, x2, z2);
    }
  }
  const tooNear = (x: number, z: number): boolean => {
    for (let i = 0; i < near.length; i += 4) {
      const ax = near[i]!, az = near[i + 1]!, bx = near[i + 2]!, bz = near[i + 3]!;
      const dx = bx - ax, dz = bz - az;
      const t = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz || 1)));
      if (Math.hypot(x - ax - dx * t, z - az - dz * t) < clear) return true;
    }
    return false;
  };
  const hash = (n: number): number => {
    const s = Math.sin(n * 127.1 + 311.7) * 43758.5453;
    return s - Math.floor(s);
  };
  const starts: number[] = [];
  const ends: number[] = [];
  const order: number[] = [];
  const far = relief.radius * 1.05;
  let n = 0;
  for (let r = 62, ring = 0; r < far; r += ringStep, ring++) {
    const slope = slopeAt(r);
    if (slope < 0.045) continue;
    const length = Math.min(ringStep * 0.66, Math.max(3.5, slope * 52));
    const steps = Math.floor((Math.PI * 2 * r) / spacing);
    for (let i = 0; i < steps; i++) {
      n++;
      const a = ((i + (ring % 2) * 0.5 + (hash(n) - 0.5) * 0.5) / steps) * Math.PI * 2;
      const r0 = r + (hash(n + 0.37) - 0.5) * 5;
      const len = length * (0.7 + hash(n + 0.71) * 0.5);
      const cx = Math.cos(a), cz = Math.sin(a);
      const x0 = relief.x + cx * r0, z0 = relief.z + cz * r0;
      const x1 = relief.x + cx * (r0 + len), z1 = relief.z + cz * (r0 + len);
      const mx = (x0 + x1) / 2, mz = (z0 + z1) / 2;
      if (options.avoid?.(mx, mz) || tooNear(mx, mz) || tooNear(x0, z0) || tooNear(x1, z1)) continue;
      starts.push(x0, 0, z0);
      ends.push(x1, 0, z1);
      order.push(Math.min(1, r0 / far));
    }
  }
  const lines = createSegments(world, {
    starts: new Float32Array(starts),
    ends: new Float32Array(ends),
    order: new Float32Array(order),
    width: 0.9,
    color: "ink2",
    opacity: 0.62,
    depthTest: true,
    renderOrder: 0.5,
  });
  lines.setFeather(0.12);
  lines.setDraw(0);
  return {
    lines,
    setDraw(amount) {
      lines.mesh.visible = amount > 0;
      lines.setDraw(amount >= 1 ? 2 : amount * 1.12);
    },
  };
}

export interface Trees {
  group: Group;
  /** 0 to 1: the trees come up out of the ground, one after another. */
  setGrow(amount: number): void;
}

export interface TreesOptions {
  /** How many, and how far from the top of the rise they stand (metres). */
  count?: number;
  near?: number;
  far?: number;
  /** Leave these places bare. */
  avoid?: (x: number, z: number) => boolean;
  /** Streets to keep clear of, and by how much. */
  streets?: Streets;
  clear?: number;
}

/** A scatter of trees on the slopes of a rise, drawn as a pop-up book draws them: each is two flat cards cut to
 *  a cypress's outline and slotted together at right angles, one paper, one in the shade colour, both inked round
 *  their edges. Each a different size and turn. They stand on the risen ground and come up through it (so use
 *  them with createGround). */
export function createTrees(world: World, relief: Relief, options: TreesOptions = {}): Trees {
  const count = options.count ?? 16;
  const nearR = options.near ?? 40, farR = options.far ?? 170;
  const clear = options.clear ?? 10;
  const streets: number[] = [];
  if (options.streets) {
    const { xy, count: n } = options.streets;
    for (let i = 0; i < n; i++) {
      const x1 = xy[i * 4]!, z1 = -xy[i * 4 + 1]!, x2 = xy[i * 4 + 2]!, z2 = -xy[i * 4 + 3]!;
      if (Math.hypot((x1 + x2) / 2 - relief.x, (z1 + z2) / 2 - relief.z) < farR + 120) streets.push(x1, z1, x2, z2);
    }
  }
  const tooNear = (x: number, z: number): boolean => {
    for (let i = 0; i < streets.length; i += 4) {
      const ax = streets[i]!, az = streets[i + 1]!, dx = streets[i + 2]! - ax, dz = streets[i + 3]! - az;
      const t = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz || 1)));
      if (Math.hypot(x - ax - dx * t, z - az - dz * t) < clear) return true;
    }
    return false;
  };
  const hash = (n: number): number => {
    const s = Math.sin(n * 91.7 + 17.3) * 43758.5453;
    return s - Math.floor(s);
  };
  /** A cypress cut from card: a short trunk and a tall, pointed crown, `h` high and `w` across at its widest. */
  const cypress = (h: number, w: number): Pt[] => {
    const t = h * 0.17, tw = Math.max(0.28, h * 0.028), c = h - t, r = w / 2;
    const side: Pt[] = [
      [tw, 0],
      [tw, t],
      [r * 0.62, t],
      [r * 0.94, t + c * 0.16],
      [r, t + c * 0.34],
      [r * 0.8, t + c * 0.56],
      [r * 0.46, t + c * 0.78],
      [r * 0.16, t + c * 0.94],
    ];
    return [...side, [0, h], ...side.slice().reverse().map(p => [-p[0], p[1]] as Pt)];
  };
  const paper: BufferGeometry[] = [];
  const shade: BufferGeometry[] = [];
  const placed: [number, number][] = [];
  for (let n = 1; placed.length < count && n < count * 40; n++) {
    const a = hash(n) * Math.PI * 2;
    const r = nearR + hash(n + 0.5) * (farR - nearR);
    const x = relief.x + Math.cos(a) * r, z = relief.z + Math.sin(a) * r;
    if (options.avoid?.(x, z) || tooNear(x, z) || placed.some(p => Math.hypot(p[0] - x, p[1] - z) < 13)) continue;
    placed.push([x, z]);
    const h = 9 + hash(n + 0.25) * 6;
    const w = h * (0.34 + hash(n + 0.75) * 0.14);
    const y = reliefHeight([relief], x, z) - 0.4;
    const turn = (hash(n + 0.6) - 0.5) * 50 * RAD;
    const outline = cypress(h, w);
    paper.push(plate(outline).rotateY(turn).translate(x, y, z));
    shade.push(plate(outline.map(p => [p[0] * 0.92, p[1]] as Pt)).rotateY(turn + Math.PI / 2).translate(x, y, z));
  }
  const group = new Group();
  if (paper.length) {
    const faces = card(world, merge(...paper), { flat: true, outline: 0.9 });
    const sides = card(world, merge(...shade), { flat: true, fillColor: "shade", outline: 0.9 });
    sides.setFill(1);
    group.add(sides.group, faces.group);
  }
  let last = -1;
  const api: Trees = {
    group,
    setGrow(amount) {
      const a = amount < 0.002 ? 0 : amount;
      if (a === last) return;
      last = a;
      group.visible = a > 0;
      group.scale.y = Math.max(0.0001, a);
      world.invalidate();
    },
  };
  api.setGrow(0);
  return api;
}
