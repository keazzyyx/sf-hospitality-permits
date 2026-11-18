// Small solids in the print language, many at once: paper-colour faces, the shade colour for faces turned from the
// light (one threshold, as core/world/print.ts), an ink line along every edge. One instanced mesh and one draw
// call for a whole set (the 22 slabs of a motion's conditions, the letters standing in two rows, seven seats), with
// everything that moves in the vertex shader: nothing is uploaded after the set is made.
//
// Each block is a box standing on its base. A set can
//   rise as a stack (setGrow: the levels open like a concertina, the top ones last),
//   stand up one by one in its order (setRise),
//   fill with the line colour up to a count (setLit: a seat that has voted), and
//   pick one out in ink while the rest hold back (setPick).

import { Float32BufferAttribute, InstancedBufferAttribute, InstancedBufferGeometry, Mesh, ShaderMaterial, Vector2 } from "three";
import type { World } from "../core/world";

export interface BlockSpec {
  /** The middle of its base, in the set's own frame (metres; y up). */
  x: number;
  y: number;
  z: number;
  /** Width (along x), height and depth (along z) before it is turned. */
  w: number;
  h: number;
  d: number;
  /** Turned about its own upright axis, in radians. */
  yaw?: number;
  /** 0: paper faces. 1: faces filled with the line colour. */
  kind?: 0 | 1;
  /** Its place in the set's order (default: its index). */
  order?: number;
}

export interface Blocks {
  mesh: Mesh;
  count: number;
  /** 0 to 1: the set as a stack. At 0 every block lies at the level of the lowest; at 1 each is at its own. */
  setGrow(amount: number): void;
  /** How many blocks have stood up, in their order (a fraction stands the next one part of the way). */
  setRise(count: number): void;
  /** How many blocks, in their order, are filled with the line colour. */
  setLit(count: number): void;
  /** One block (by its order) picked out in ink, the rest held back: amount 0 to 1. */
  setPick(order: number, amount: number): void;
}

const VERT = /* glsl */ `
attribute vec3 aAt;
attribute vec3 aSize;
attribute vec3 aMore;
uniform float uGrow;
uniform float uRise;
uniform float uLit;
uniform float uCount;
uniform vec2 uPick;
varying vec3 vNormal;
varying vec2 vUv;
varying vec2 vFace;
varying float vFill;
varying float vPick;
void main() {
  float order = aMore.z;
  // the stack opens from the bottom: the top levels start last
  float g = clamp(uGrow * 1.5 - 0.5 * order / max(uCount - 1.0, 1.0), 0.0, 1.0);
  g = 1.0 - (1.0 - g) * (1.0 - g) * (1.0 - g);
  float k = clamp(uRise - order, 0.0, 1.0);
  k = 1.0 - (1.0 - k) * (1.0 - k) * (1.0 - k);
  if (k * g <= 0.003) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    vNormal = vec3(0.0, 1.0, 0.0); vUv = vec2(0.0); vFace = vec2(1.0); vFill = 0.0; vPick = 0.0;
    return;
  }
  vec3 size = aSize * vec3(1.0, k * mix(0.3, 1.0, g), 1.0);
  vec3 p = position * size;
  float c = cos(aMore.x), s = sin(aMore.x);
  p = vec3(p.x * c + p.z * s, p.y, -p.x * s + p.z * c);
  p += vec3(aAt.x, aAt.y * g, aAt.z);
  vec3 n = vec3(normal.x * c + normal.z * s, normal.y, -normal.x * s + normal.z * c);
  vNormal = normalize(mat3(modelMatrix) * n);
  vFace = abs(normal.x) > 0.5 ? size.zy : abs(normal.y) > 0.5 ? size.xz : size.xy;
  vUv = uv * vFace;
  vFill = max(aMore.y, step(order + 0.5, uLit));
  vPick = (1.0 - min(1.0, abs(order - uPick.x))) * uPick.y;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
}
`;

const FRAG = /* glsl */ `
uniform vec3 uPaper;
uniform vec3 uShade;
uniform vec3 uInk;
uniform vec3 uLine;
uniform vec3 uLight;
uniform vec2 uPick;
uniform float uEdge;
varying vec3 vNormal;
varying vec2 vUv;
varying vec2 vFace;
varying float vFill;
varying float vPick;
void main() {
  vec3 n = normalize(vNormal);
  float lit = step(0.02, dot(n, uLight));
  vec3 colour = mix(uShade, uPaper, lit);
  colour = mix(colour, mix(uLine, uShade, (1.0 - lit) * 0.45), vFill);
  // the one picked out is inked; the rest step back toward the ground while it is
  colour = mix(colour, uInk, vPick);
  colour = mix(colour, uPaper, uPick.y * (1.0 - step(0.5, vPick)) * 0.45 * (1.0 - lit));
  // an ink line along every edge of every face, a constant width on the screen
  vec2 fw = max(fwidth(vUv), vec2(1e-6));
  vec2 d = min(vUv, vFace - vUv) / fw;
  float e = min(d.x, d.y);
  float edge = 1.0 - smoothstep(uEdge - 0.5, uEdge + 0.5, e);
  vec3 line = mix(uInk, uPaper, step(0.5, vPick));
  gl_FragColor = vec4(mix(colour, line, edge), 1.0);
}
`;

/** A unit box standing on y = 0, its faces unshared so each carries its own normal and its own 0..1 square. */
function unitBox(): { position: number[]; normal: number[]; uv: number[]; index: number[] } {
  const position: number[] = [], normal: number[] = [], uv: number[] = [], index: number[] = [];
  // each face: its normal, and the two axes its square runs along
  const faces: [number[], number[], number[]][] = [
    [[1, 0, 0], [0, 0, -1], [0, 1, 0]],
    [[-1, 0, 0], [0, 0, 1], [0, 1, 0]],
    [[0, 1, 0], [1, 0, 0], [0, 0, -1]],
    [[0, -1, 0], [1, 0, 0], [0, 0, 1]],
    [[0, 0, 1], [1, 0, 0], [0, 1, 0]],
    [[0, 0, -1], [-1, 0, 0], [0, 1, 0]],
  ];
  faces.forEach(([n, a, b], f) => {
    for (const [s, t] of [[0, 0], [1, 0], [1, 1], [0, 1]] as const) {
      const x = n[0]! * 0.5 + a[0]! * (s - 0.5) + b[0]! * (t - 0.5);
      const y = n[1]! * 0.5 + a[1]! * (s - 0.5) + b[1]! * (t - 0.5);
      const z = n[2]! * 0.5 + a[2]! * (s - 0.5) + b[2]! * (t - 0.5);
      position.push(x, y + 0.5, z);
      normal.push(n[0]!, n[1]!, n[2]!);
      uv.push(s, t);
    }
    index.push(f * 4, f * 4 + 1, f * 4 + 2, f * 4, f * 4 + 2, f * 4 + 3);
  });
  return { position, normal, uv, index };
}

/** A set of blocks as one mesh. Position `mesh` where the set stands (its y is the level the blocks stand on). */
export function createBlocks(world: World, specs: BlockSpec[], options: { edge?: number } = {}): Blocks {
  const n = specs.length;
  const at = new Float32Array(n * 3);
  const size = new Float32Array(n * 3);
  const more = new Float32Array(n * 3);
  specs.forEach((b, i) => {
    at.set([b.x, b.y, b.z], i * 3);
    size.set([b.w, b.h, b.d], i * 3);
    more.set([b.yaw ?? 0, b.kind ?? 0, b.order ?? i], i * 3);
  });
  const box = unitBox();
  const geometry = new InstancedBufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(box.position, 3));
  geometry.setAttribute("normal", new Float32BufferAttribute(box.normal, 3));
  geometry.setAttribute("uv", new Float32BufferAttribute(box.uv, 2));
  geometry.setIndex(box.index);
  geometry.setAttribute("aAt", new InstancedBufferAttribute(at, 3));
  geometry.setAttribute("aSize", new InstancedBufferAttribute(size, 3));
  geometry.setAttribute("aMore", new InstancedBufferAttribute(more, 3));
  geometry.instanceCount = n;
  const u = world.uniforms;
  const uniforms = {
    uPaper: u.uPaper,
    uShade: u.uShade,
    uInk: u.uInk,
    uLine: u.uLine,
    uLight: u.uLight,
    uGrow: { value: 1 },
    uRise: { value: n + 1 },
    uLit: { value: 0 },
    uCount: { value: n },
    uPick: { value: new Vector2(-1, 0) },
    uEdge: { value: options.edge ?? 0.7 },
  };
  const material = new ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, uniforms });
  const mesh = new Mesh(geometry, material);
  mesh.frustumCulled = false;
  mesh.renderOrder = 2;
  const set = (uniform: { value: number }, value: number): void => {
    if (uniform.value !== value) {
      uniform.value = value;
      world.invalidate();
    }
  };
  return {
    mesh,
    count: n,
    setGrow: amount => set(uniforms.uGrow, amount),
    setRise: count => set(uniforms.uRise, count),
    setLit: count => set(uniforms.uLit, count),
    setPick(order, amount) {
      const v = uniforms.uPick.value;
      if (v.x !== order || v.y !== amount) {
        v.set(order, amount);
        world.invalidate();
      }
    },
  };
}
