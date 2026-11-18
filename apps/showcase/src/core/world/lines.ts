// Lines with a width in screen pixels, drawn as instanced quads: one mesh per set of segments, static buffers,
// everything that moves done in the vertex shader. The streets, a route, the pins' stems and the ink outlines of
// objects are all this one material.
//
// Each segment has a start, an end and an `order` (0 to 1). The uniform uDraw sweeps through the orders: a segment
// is absent while uDraw < order, grows from its start as uDraw passes it (over uFeather), and is whole after.
// Set uDraw to 1 + uFeather (FULL) for "all drawn". `tone` (0 to 1 per segment, optional, may be updated) mixes
// the line between its base colour and a second colour, alpha and length.

import {
  Float32BufferAttribute,
  InstancedBufferAttribute,
  InstancedBufferGeometry,
  Mesh,
  ShaderMaterial,
  type Color,
} from "three";
import { RELIEF_PARS, type PaletteKey, type World } from "./world";

/** uDraw at which every segment is whole, whatever the feather. */
export const FULL = 2;

export interface SegmentsOptions {
  /** x, y, z of each start. */
  starts: Float32Array;
  /** x, y, z of each end. */
  ends: Float32Array;
  /** 0 to 1 per segment: when it draws on. Default: all at 0. */
  order?: Float32Array;
  /** 0 to 1 per segment: how far towards the second colour, alpha and length. Default: none. */
  tone?: Float32Array;
  /** Width in CSS pixels. */
  width: number;
  /** Colour by palette key. */
  color: PaletteKey;
  opacity?: number;
  /** The colour, opacity, width and length factor a segment takes at tone 1. */
  toneColor?: PaletteKey;
  toneOpacity?: number;
  toneWidth?: number;
  toneLength?: number;
  /** The length factor at tone 0 (default 1). */
  baseLength?: number;
  /** Test against the depth buffer, so objects hide the lines behind them (default false). Lines never write
   *  depth: among themselves they are drawn in renderOrder. */
  depthTest?: boolean;
  /** Follow the rise of the ground (default true). Outlines of objects pass false. */
  relief?: boolean;
  /** Fade with distance from the camera: gone at this many metres (0, the default: no fade). */
  fadeFar?: number;
  renderOrder?: number;
}

export interface Segments {
  mesh: Mesh;
  count: number;
  /** Sweep the draw-on: 0 nothing, FULL everything. */
  setDraw(value: number): void;
  /** How long each segment takes to grow, in the units of `order` (default 0.08). */
  setFeather(value: number): void;
  setOpacity(value: number): void;
  setWidth(value: number): void;
  /** Lines further than `far` metres from the camera fade out, starting at `near` (far 0: no fade). */
  setFade(near: number, far: number): void;
  /** Replace the tones (same length as the count). */
  setTone(tone: Float32Array): void;
  /** Scale every tone (0 to 1): for bringing the second state in and out. */
  setToneAmount(value: number): void;
}

const VERT = /* glsl */ `
attribute vec3 aStart;
attribute vec3 aEnd;
attribute float aOrder;
attribute float aTone;
uniform vec2 uViewport;
uniform float uWidth;
uniform float uToneWidth;
uniform float uDraw;
uniform float uFeather;
uniform float uBaseLength;
uniform float uToneLength;
uniform float uToneAmount;
uniform float uUseRelief;
uniform float uPixelRatio;
uniform vec2 uFade;
varying float vTone;
varying float vFade;
varying float vSide;
${RELIEF_PARS}
void main() {
  float tone = aTone * uToneAmount;
  float r = clamp((uDraw - aOrder) / max(uFeather, 1e-4), 0.0, 1.0);
  r *= mix(uBaseLength, uToneLength, tone);
  vec3 a = aStart;
  vec3 b = mix(aStart, aEnd, r);
  if (uUseRelief > 0.5) {
    a.y += relief(a.xz);
    b.y += relief(b.xz);
  }
  vec4 va = modelViewMatrix * vec4(a, 1.0);
  vec4 vb = modelViewMatrix * vec4(b, 1.0);
  // keep both ends in front of the camera: a segment that crosses the near plane is cut there
  float near = projectionMatrix[3][2] / (projectionMatrix[2][2] - 1.0);
  float limit = -near * 1.02;
  bool aBehind = va.z > limit;
  bool bBehind = vb.z > limit;
  if ((aBehind && bBehind) || r <= 0.0) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    vTone = 0.0; vFade = 0.0; vSide = 0.0;
    return;
  }
  if (aBehind) va = mix(va, vb, (limit - va.z) / (vb.z - va.z));
  if (bBehind) vb = mix(vb, va, (limit - vb.z) / (va.z - vb.z));
  vec4 ca = projectionMatrix * va;
  vec4 cb = projectionMatrix * vb;
  vec2 sa = ca.xy / ca.w * uViewport;
  vec2 sb = cb.xy / cb.w * uViewport;
  vec2 d = sb - sa;
  float len = length(d);
  vec2 dir = len > 1e-5 ? d / len : vec2(1.0, 0.0);
  vec2 nrm = vec2(-dir.y, dir.x);
  float width = mix(uWidth, uToneWidth, tone);
  float aa = 1.0 / uPixelRatio;        // one device pixel, in CSS pixels
  float w = max(aa, width);            // never thinner than a device pixel: a thinner line fades instead
  float halfWidth = (w + aa) * 0.5;    // from the centre line to the outside of the soft border
  vec4 c = mix(ca, cb, position.x);
  vec2 offset = (nrm * position.y * halfWidth + dir * (position.x * 2.0 - 1.0) * aa * 0.5) * 2.0 / uViewport;
  c.xy += offset * c.w;
  gl_Position = c;
  vTone = tone;
  vSide = position.y * halfWidth;
  float depth = -mix(va.z, vb.z, position.x);
  vFade = uFade.y > 0.0 ? 1.0 - smoothstep(uFade.x, uFade.y, depth) : 1.0;
  vFade *= min(1.0, width / aa);
}
`;

const FRAG = /* glsl */ `
uniform vec3 uColor;
uniform vec3 uToneColor;
uniform float uOpacity;
uniform float uToneOpacity;
uniform float uWidth;
uniform float uToneWidth;
uniform float uPixelRatio;
varying float vTone;
varying float vFade;
varying float vSide;
void main() {
  float aa = 1.0 / uPixelRatio;
  float w = max(aa, mix(uWidth, uToneWidth, vTone));
  // a soft edge one device pixel wide: lines stay even where the hardware's own smoothing gives out
  float edge = clamp(((w + aa) * 0.5 - abs(vSide)) / aa, 0.0, 1.0);
  float alpha = mix(uOpacity, uToneOpacity, vTone) * vFade * edge;
  if (alpha < 0.004) discard;
  gl_FragColor = vec4(mix(uColor, uToneColor, vTone), alpha);
}
`;

const colourOf = (world: World, key: PaletteKey): { value: Color } =>
  ({ paper: world.uniforms.uPaper, paper2: world.uniforms.uPaper2, ink: world.uniforms.uInk, ink2: world.uniforms.uInk2, line: world.uniforms.uLine, stamp: world.uniforms.uStamp, shade: world.uniforms.uShade })[key];

/** A set of line segments as one mesh. Add `mesh` to the scene. */
export function createSegments(world: World, options: SegmentsOptions): Segments {
  const count = options.starts.length / 3;
  const geometry = new InstancedBufferGeometry();
  // a quad: x along the segment (0 start, 1 end), y across it (-1, 1)
  geometry.setAttribute("position", new Float32BufferAttribute([0, -1, 0, 1, -1, 0, 1, 1, 0, 0, 1, 0], 3));
  geometry.setIndex([0, 1, 2, 0, 2, 3]);
  geometry.setAttribute("aStart", new InstancedBufferAttribute(options.starts, 3));
  geometry.setAttribute("aEnd", new InstancedBufferAttribute(options.ends, 3));
  geometry.setAttribute("aOrder", new InstancedBufferAttribute(options.order ?? new Float32Array(count), 1));
  const tone = new InstancedBufferAttribute(options.tone ?? new Float32Array(count), 1);
  geometry.setAttribute("aTone", tone);
  geometry.instanceCount = count;

  const u = world.uniforms;
  const material = new ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: true,
    depthTest: options.depthTest ?? false,
    depthWrite: false,
    uniforms: {
      uViewport: u.uViewport,
      uPixelRatio: u.uPixelRatio,
      uRelief: u.uRelief,
      uReliefAmount: u.uReliefAmount,
      uColor: colourOf(world, options.color),
      uToneColor: colourOf(world, options.toneColor ?? options.color),
      uWidth: { value: options.width },
      uToneWidth: { value: options.toneWidth ?? options.width },
      uOpacity: { value: options.opacity ?? 1 },
      uToneOpacity: { value: options.toneOpacity ?? options.opacity ?? 1 },
      uBaseLength: { value: options.baseLength ?? 1 },
      uToneLength: { value: options.toneLength ?? options.baseLength ?? 1 },
      uToneAmount: { value: 1 },
      uDraw: { value: FULL },
      uFeather: { value: 0.08 },
      uUseRelief: { value: options.relief === false ? 0 : 1 },
      uFade: { value: [0, options.fadeFar ?? 0] },
    },
  });
  const mesh = new Mesh(geometry, material);
  mesh.frustumCulled = false;
  mesh.renderOrder = options.renderOrder ?? 0;
  const un = material.uniforms as Record<string, { value: number | number[] }>;
  const set = (name: string, value: number): void => {
    if (un[name]!.value !== value) {
      un[name]!.value = value;
      world.invalidate();
    }
  };
  return {
    mesh,
    count,
    setDraw: value => set("uDraw", value),
    setFeather: value => set("uFeather", value),
    setOpacity: value => set("uOpacity", value),
    setWidth: value => set("uWidth", value),
    setFade(near, far) {
      const fade = un.uFade!.value as number[];
      if (fade[0] !== near || fade[1] !== far) {
        fade[0] = near;
        fade[1] = far;
        world.invalidate();
      }
    },
    setTone(values) {
      (tone.array as Float32Array).set(values);
      tone.needsUpdate = true;
      world.invalidate();
    },
    setToneAmount: value => set("uToneAmount", value),
  };
}
