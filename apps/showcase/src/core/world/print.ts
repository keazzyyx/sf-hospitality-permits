// Objects drawn like a two-colour print: paper-colour faces, the shade colour for faces turned away from the
// light (a two-step threshold, no other lighting), and ink outlines along silhouettes and creases.
//
//   const tower = printObject(world, new CylinderGeometry(7, 7, 60, 16), { crease: 30 });
//   tower.group.position.set(x, 0, z);
//   scene.add(tower.group);
//   tower.setFill(1);   // a face filled with the line colour (a lit seat)
//
// The faces write depth and are pushed back a little so the outlines sit cleanly on them.

import {
  BackSide,
  DoubleSide,
  EdgesGeometry,
  FrontSide,
  Group,
  Mesh,
  ShaderMaterial,
  type BufferGeometry,
  type Side,
} from "three";
import { createSegments, type Segments } from "./lines";
import { RELIEF_PARS, type PaletteKey, type World } from "./world";

const VERT = /* glsl */ `
varying vec3 vNormal;
void main() {
  vNormal = normalize(mat3(modelMatrix) * normal);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const FRAG = /* glsl */ `
uniform vec3 uPaper;
uniform vec3 uShade;
uniform vec3 uFillColor;
uniform vec3 uLight;
uniform float uFill;
uniform float uFlat;
varying vec3 vNormal;
void main() {
  vec3 n = normalize(vNormal);
  if (!gl_FrontFacing) n = -n;
  float lit = step(0.02, dot(n, uLight));
  vec3 colour = mix(uShade, uPaper, max(lit, uFlat));
  gl_FragColor = vec4(mix(colour, uFillColor, uFill), 1.0);
}
`;

// The profile: the object's back faces, pushed out along their normals by a width in pixels and drawn in ink, so
// a round thing has an outline where it turns away, and every silhouette is a little heavier than a crease.
const HULL_VERT = /* glsl */ `
uniform vec2 uViewport;
uniform float uWidth;
void main() {
  vec4 clip = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  vec3 n = normalMatrix * normal;
  vec2 dir = dot(n.xy, n.xy) > 1e-8 ? normalize(n.xy) : vec2(0.0);
  clip.xy += dir * uWidth * 2.0 / uViewport * clip.w;
  gl_Position = clip;
}
`;
const HULL_FRAG = /* glsl */ `
uniform vec3 uInk;
void main() {
  gl_FragColor = vec4(uInk, 1.0);
}
`;

// The cast shadow: the same geometry laid flat on the ground the object stands on, along the light, in the shade
// colour. The object's own origin is taken as ground level.
const SHADOW_VERT = /* glsl */ `
uniform vec3 uLight;
uniform float uOnRelief;
${RELIEF_PARS}
void main() {
  vec4 w = modelMatrix * vec4(position, 1.0);
  float ground = modelMatrix[3].y;
  float t = max(0.0, w.y - ground) / uLight.y;
  w.xyz -= uLight * t;
  // the shadow lies on the level the object stands on, or on the ground as the street lines know it (a rise)
  w.y = mix(ground, max(relief(w.xz), 0.0), uOnRelief) + 0.08;
  gl_Position = projectionMatrix * viewMatrix * w;
}
`;
const SHADOW_FRAG = /* glsl */ `
uniform vec3 uShade;
void main() {
  gl_FragColor = vec4(uShade, 1.0);
}
`;

export interface PrintOptions {
  /** Outline every edge where two faces meet at more than this many degrees (default 20). */
  crease?: number;
  /** Outline width in CSS pixels (default 1.1). */
  outline?: number;
  /** The outline's colour (default ink). */
  outlineColor?: PaletteKey;
  /** The colour a face takes when filled (default the line colour). */
  fillColor?: PaletteKey;
  /** No shading: every face paper (a sheet, a label). */
  flat?: boolean;
  side?: Side;
  /** No outline at all. */
  bare?: boolean;
  /** Width of the heavier profile line in CSS pixels (default 1.2; 0 for none). */
  profile?: number;
  /** Cast a flat shadow (default false): on the level the object's origin stands on, or, with "relief", on the
   *  ground as the street lines know it, following any rise. */
  shadow?: boolean | "relief";
}

export interface PrintObject {
  /** Faces and outline together: position, rotate and scale this. */
  group: Group;
  faces: Mesh;
  outline: Segments | null;
  /** 0 to 1: how far the faces are filled with the fill colour. */
  setFill(amount: number): void;
}

const key = (world: World, k: PaletteKey) =>
  ({ paper: world.uniforms.uPaper, paper2: world.uniforms.uPaper2, ink: world.uniforms.uInk, ink2: world.uniforms.uInk2, line: world.uniforms.uLine, stamp: world.uniforms.uStamp, shade: world.uniforms.uShade })[k];

/** The faces' material on its own (for a mesh that needs no outline, or shares one). */
export function printMaterial(world: World, options: PrintOptions = {}): ShaderMaterial {
  const u = world.uniforms;
  return new ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    side: options.side ?? FrontSide,
    polygonOffset: true,
    polygonOffsetFactor: 1,
    polygonOffsetUnits: 1,
    uniforms: {
      uPaper: u.uPaper,
      uShade: u.uShade,
      uLight: u.uLight,
      uFillColor: key(world, options.fillColor ?? "line"),
      uFill: { value: 0 },
      uFlat: { value: options.flat ? 1 : 0 },
    },
  });
}

/** The ink outline of a geometry: its edges, as lines with a width in pixels. */
export function inkEdges(world: World, geometry: BufferGeometry, options: PrintOptions = {}): Segments {
  const edges = new EdgesGeometry(geometry, options.crease ?? 20);
  const pos = edges.getAttribute("position").array as Float32Array;
  const n = pos.length / 6;
  const starts = new Float32Array(n * 3);
  const ends = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    starts.set(pos.subarray(i * 6, i * 6 + 3), i * 3);
    ends.set(pos.subarray(i * 6 + 3, i * 6 + 6), i * 3);
  }
  edges.dispose();
  return createSegments(world, {
    starts,
    ends,
    width: options.outline ?? 1.1,
    color: options.outlineColor ?? "ink",
    depthTest: true,
    relief: false,
    renderOrder: 3,
  });
}

/** A geometry as a printed object: shaded faces and an ink outline, in one group. */
export function printObject(world: World, geometry: BufferGeometry, options: PrintOptions = {}): PrintObject {
  const material = printMaterial(world, options);
  const faces = new Mesh(geometry, material);
  faces.renderOrder = 2;
  const group = new Group();
  group.add(faces);
  const outline = options.bare ? null : inkEdges(world, geometry, options);
  if (outline) group.add(outline.mesh);
  const u = world.uniforms;
  const profile = options.bare ? 0 : (options.profile ?? 1.2);
  if (profile > 0 && options.side !== DoubleSide) {
    const hull = new Mesh(
      geometry,
      new ShaderMaterial({
        vertexShader: HULL_VERT,
        fragmentShader: HULL_FRAG,
        side: BackSide,
        uniforms: { uViewport: u.uViewport, uInk: key(world, options.outlineColor ?? "ink"), uWidth: { value: profile } },
      }),
    );
    hull.renderOrder = 2;
    group.add(hull);
  }
  if (options.shadow) {
    const shadow = new Mesh(
      geometry,
      new ShaderMaterial({
        vertexShader: SHADOW_VERT,
        fragmentShader: SHADOW_FRAG,
        side: DoubleSide,
        depthWrite: false,
        uniforms: { uLight: u.uLight, uShade: u.uShade, uRelief: u.uRelief, uReliefAmount: u.uReliefAmount, uOnRelief: { value: options.shadow === "relief" ? 1 : 0 } },
      }),
    );
    shadow.renderOrder = 1;
    shadow.frustumCulled = false;
    group.add(shadow);
  }
  const fill = material.uniforms.uFill as { value: number };
  return {
    group,
    faces,
    outline,
    setFill(amount) {
      if (fill.value !== amount) {
        fill.value = amount;
        world.invalidate();
      }
    },
  };
}
