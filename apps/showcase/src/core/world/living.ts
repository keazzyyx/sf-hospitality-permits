// The living grid: an opt-in set of materials that share one set of "living" uniforms, so the ground can rise in
// a dome under a pointer (or sink in a dent), rings can run through the city, and everything planted on the
// ground (lines, stacks, their dots) moves with it. Static buffers; every movement is in the vertex shader.
// Built for /c/ (the front page). Nothing here changes lines.ts, streets.ts or pins.ts.
//
//   const living = createLiving(world);
//   const streets = createLivingStreets(world, living, streetData);      // one draw call for the whole city
//   const stacks = createStacks(world, living, [{ x, z, n }, …]);        // one instanced mesh + one point cloud
//   living.setPointer(x, z, 420); living.setBulge(140);                  // a dome 140 m high, sigma 420 m
//   living.setRing(0, x, z, radius, strength, width, glow);              // two rings at once (0 and 1)
//
// The caller owns the clock: set `living.uniforms.uTime.value` (seconds) each frame something is in motion.

import {
  BufferAttribute,
  BufferGeometry,
  DoubleSide,
  Float32BufferAttribute,
  InstancedBufferAttribute,
  InstancedBufferGeometry,
  Mesh,
  Points,
  ShaderMaterial,
  Vector2,
  Vector3,
  Vector4,
  type Color,
} from "three";
import type { Streets } from "./data";
import { RELIEF_PARS, type PaletteKey, type World } from "./world";

export interface LivingUniforms {
  /** x, z of the pointer's ground point, and the dome's sigma in metres. */
  uPointer: { value: Vector3 };
  /** Height of the dome in metres; negative is a dent. */
  uBulge: { value: number };
  /** How much the dome brightens what is in it (0 to 1). */
  uPointerGlow: { value: number };
  /** Two rings: x, z of the origin, radius and height in metres. */
  uRings: { value: Vector4[] };
  /** Width of each ring's crest in metres, and how much it brightens what it passes. */
  uRingShape: { value: Vector2[] };
  /** Seconds, on the caller's clock: per-instance tweens of the stacks run on it. */
  uTime: { value: number };
}

export interface Living {
  uniforms: LivingUniforms;
  setPointer(x: number, z: number, sigma: number): void;
  setBulge(height: number, glow?: number): void;
  setRing(index: 0 | 1, x: number, z: number, radius: number, strength: number, width: number, glow?: number): void;
  /** The same arithmetic as the shader: how high the ground is lifted at a point, in metres (without the relief). */
  liftAt(x: number, z: number): number;
}

/** GLSL: `float living(vec2 xz, out float glow)`: the height of the living ground at a point. */
export const LIVING_PARS = /* glsl */ `
${RELIEF_PARS}
uniform vec3 uPointer;
uniform float uBulge;
uniform float uPointerGlow;
uniform vec4 uRings[2];
uniform vec2 uRingShape[2];
float living(vec2 p, out float glow) {
  float h = relief(p);
  vec2 d = p - uPointer.xy;
  float g = exp(-dot(d, d) / (2.0 * uPointer.z * uPointer.z));
  h += uBulge * g;
  glow = g * uPointerGlow;
  for (int i = 0; i < 2; i++) {
    float x = (length(p - uRings[i].xy) - uRings[i].z) / uRingShape[i].x;
    float crest = exp(-x * x);
    // a crest with a shallow trough behind it
    h += uRings[i].w * (crest - 0.28 * exp(-(x + 1.8) * (x + 1.8)));
    glow += crest * uRingShape[i].y;
  }
  return h;
}
`;

export function createLiving(world: World): Living {
  const uniforms: LivingUniforms = {
    uPointer: { value: new Vector3(0, 0, 400) },
    uBulge: { value: 0 },
    uPointerGlow: { value: 0 },
    uRings: { value: [new Vector4(0, 0, -1e6, 0), new Vector4(0, 0, -1e6, 0)] },
    uRingShape: { value: [new Vector2(300, 0), new Vector2(300, 0)] },
    uTime: { value: 0 },
  };
  return {
    uniforms,
    setPointer(x, z, sigma) {
      const p = uniforms.uPointer.value;
      if (p.x !== x || p.y !== z || p.z !== sigma) {
        p.set(x, z, sigma);
        if (uniforms.uBulge.value !== 0 || uniforms.uPointerGlow.value !== 0) world.invalidate();
      }
    },
    setBulge(height, glow = uniforms.uPointerGlow.value) {
      if (uniforms.uBulge.value !== height || uniforms.uPointerGlow.value !== glow) {
        uniforms.uBulge.value = height;
        uniforms.uPointerGlow.value = glow;
        world.invalidate();
      }
    },
    setRing(index, x, z, radius, strength, width, glow = 0) {
      const r = uniforms.uRings.value[index]!;
      const sh = uniforms.uRingShape.value[index]!;
      const wd = Math.max(1, width);
      if (r.x === x && r.y === z && r.z === radius && r.w === strength && sh.x === wd && sh.y === glow) return;
      r.set(x, z, radius, strength);
      sh.set(wd, glow);
      world.invalidate();
    },
    liftAt(x, z) {
      const p = uniforms.uPointer.value;
      const dx = x - p.x, dz = z - p.y;
      let h = uniforms.uBulge.value * Math.exp(-(dx * dx + dz * dz) / (2 * p.z * p.z));
      for (let i = 0; i < 2; i++) {
        const r = uniforms.uRings.value[i]!;
        const s = uniforms.uRingShape.value[i]!;
        const t = (Math.hypot(x - r.x, z - r.y) - r.z) / s.x;
        h += r.w * (Math.exp(-t * t) - 0.28 * Math.exp(-(t + 1.8) * (t + 1.8)));
      }
      return h;
    },
  };
}

const colourOf = (world: World, key: PaletteKey): { value: Color } =>
  ({ paper: world.uniforms.uPaper, paper2: world.uniforms.uPaper2, ink: world.uniforms.uInk, ink2: world.uniforms.uInk2, line: world.uniforms.uLine, stamp: world.uniforms.uStamp, shade: world.uniforms.uShade })[key];

// ---- lines ------------------------------------------------------------------------------------------------------

const LINE_VERT = /* glsl */ `
attribute vec4 aSeg;
attribute float aKind;
attribute float aOrder;
uniform vec2 uViewport;
uniform float uPixelRatio;
uniform vec2 uWidths;
uniform vec2 uFade;
uniform vec4 uReveal;
uniform vec4 uSpot;
uniform float uDraw;
uniform float uFeather;
uniform float uGlowWidth;
varying float vKind;
varying float vFade;
varying float vSide;
varying float vGlow;
varying float vHalf;
${LIVING_PARS}
void main() {
  float r = clamp((uDraw - aOrder) / max(uFeather, 1e-4), 0.0, 1.0);
  vec2 pa = aSeg.xy;
  vec2 pb = mix(aSeg.xy, aSeg.zw, r);
  float ga, gb;
  vec3 a = vec3(pa.x, living(pa, ga), pa.y);
  vec3 b = vec3(pb.x, living(pb, gb), pb.y);
  vec4 va = modelViewMatrix * vec4(a, 1.0);
  vec4 vb = modelViewMatrix * vec4(b, 1.0);
  float near = projectionMatrix[3][2] / (projectionMatrix[2][2] - 1.0);
  float limit = -near * 1.02;
  bool aBehind = va.z > limit;
  bool bBehind = vb.z > limit;
  if ((aBehind && bBehind) || r <= 0.0) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    vKind = 0.0; vFade = 0.0; vSide = 0.0; vGlow = 0.0; vHalf = 1.0;
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
  vec2 pm = mix(pa, pb, position.x);
  float glow = mix(ga, gb, position.x);
  // a place picked out (an address): the lines round it brighten
  vec2 ds = pm - uSpot.xy;
  glow += uSpot.w * exp(-dot(ds, ds) / (2.0 * uSpot.z * uSpot.z));
  // the city draws on outward from a point: nothing beyond the radius, a bright front at it
  float dist = length(pm - uReveal.xy);
  float shown = 1.0 - smoothstep(uReveal.z - uReveal.w, uReveal.z, dist);
  float front = shown * smoothstep(uReveal.z - uReveal.w * 3.0, uReveal.z - uReveal.w, dist) * step(uReveal.z, 9.0e5);
  glow = min(1.5, glow + front * 0.8);
  float width = mix(uWidths.x, uWidths.y, aKind) * (1.0 + uGlowWidth * min(1.0, glow));
  float aa = 1.0 / uPixelRatio;
  float w = max(aa, width);
  float halfWidth = (w + aa) * 0.5;
  vec4 c = mix(ca, cb, position.x);
  vec2 offset = (nrm * position.y * halfWidth + dir * (position.x * 2.0 - 1.0) * aa * 0.5) * 2.0 / uViewport;
  c.xy += offset * c.w;
  gl_Position = c;
  vKind = aKind;
  vSide = position.y * halfWidth;
  vHalf = halfWidth;
  vGlow = glow;
  float depth = -mix(va.z, vb.z, position.x);
  vFade = uFade.y > 0.0 ? 1.0 - smoothstep(uFade.x, uFade.y, depth) : 1.0;
  vFade *= min(1.0, width / aa) * shown;
}
`;

const LINE_FRAG = /* glsl */ `
uniform vec3 uColor;
uniform vec3 uHi;
uniform vec2 uOpacities;
uniform float uGlowOpacity;
uniform float uDim;
uniform float uPixelRatio;
varying float vKind;
varying float vFade;
varying float vSide;
varying float vGlow;
varying float vHalf;
void main() {
  float aa = 1.0 / uPixelRatio;
  float edge = clamp((vHalf - abs(vSide)) / aa, 0.0, 1.0);
  float g = min(1.0, vGlow);
  float base = mix(uOpacities.x, uOpacities.y, vKind) * (1.0 - uDim);
  float alpha = min(1.0, base + g * uGlowOpacity) * vFade * edge;
  if (alpha < 0.004) discard;
  gl_FragColor = vec4(mix(uColor, uHi, g * 0.85), alpha);
}
`;

export interface LivingLinesOptions {
  /** x1, z1, x2, z2 per segment (world metres). */
  segs: Float32Array;
  /** 0 or 1 per segment: which of the two widths and opacities it takes. Default: all 0. */
  kinds?: Float32Array;
  /** 0 to 1 per segment: when it draws on (see setDraw). Default: all 0. */
  order?: Float32Array;
  /** Widths in CSS pixels for kind 0 and kind 1. */
  widths: [number, number];
  opacities: [number, number];
  color: PaletteKey;
  /** The colour a line goes towards where the ground glows (a dome, a ring's crest, a spot). Default "ink". */
  highlight?: PaletteKey;
  depthTest?: boolean;
  renderOrder?: number;
}

export interface LivingLines {
  mesh: Mesh;
  count: number;
  setOpacities(minor: number, major: number): void;
  setWidths(minor: number, major: number): void;
  /** How much opacity and width a glowing line gains (opacity 0 to 1; width as a factor, 0.5 = half as wide again). */
  setGlow(opacity: number, width: number): void;
  /** Hold every line back (0 to 1): the search's panel is in front. */
  setDim(amount: number): void;
  /** Fade with distance from the camera (far 0: no fade). */
  setFade(near: number, far: number): void;
  /** Draw on outward from a point: nothing shows beyond `radius` metres (Infinity: everything). */
  setReveal(x: number, z: number, radius: number, feather?: number): void;
  /** Brighten the lines round a point (amount 0 to 1). */
  setSpot(x: number, z: number, sigma: number, amount: number): void;
  /** Sweep through each segment's `order`: 0 nothing, 2 everything. */
  setDraw(value: number, feather?: number): void;
}

/** A set of living line segments as one mesh (one draw call). Add `mesh` to the scene. */
export function createLivingLines(world: World, living: Living, options: LivingLinesOptions): LivingLines {
  const count = options.segs.length / 4;
  const geometry = new InstancedBufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute([0, -1, 0, 1, -1, 0, 1, 1, 0, 0, 1, 0], 3));
  geometry.setIndex([0, 1, 2, 0, 2, 3]);
  geometry.setAttribute("aSeg", new InstancedBufferAttribute(options.segs, 4));
  geometry.setAttribute("aKind", new InstancedBufferAttribute(options.kinds ?? new Float32Array(count), 1));
  geometry.setAttribute("aOrder", new InstancedBufferAttribute(options.order ?? new Float32Array(count), 1));
  geometry.instanceCount = count;
  const u = world.uniforms;
  const l = living.uniforms;
  const material = new ShaderMaterial({
    vertexShader: LINE_VERT,
    fragmentShader: LINE_FRAG,
    transparent: true,
    depthTest: options.depthTest ?? false,
    depthWrite: false,
    uniforms: {
      uViewport: u.uViewport,
      uPixelRatio: u.uPixelRatio,
      uRelief: u.uRelief,
      uReliefAmount: u.uReliefAmount,
      uPointer: l.uPointer,
      uBulge: l.uBulge,
      uPointerGlow: l.uPointerGlow,
      uRings: l.uRings,
      uRingShape: l.uRingShape,
      uColor: colourOf(world, options.color),
      uHi: colourOf(world, options.highlight ?? "ink"),
      uWidths: { value: new Vector2(options.widths[0], options.widths[1]) },
      uOpacities: { value: new Vector2(options.opacities[0], options.opacities[1]) },
      uGlowOpacity: { value: 0.5 },
      uGlowWidth: { value: 0.6 },
      uDim: { value: 0 },
      uFade: { value: new Vector2(0, 0) },
      uReveal: { value: new Vector4(0, 0, 1e6, 600) },
      uSpot: { value: new Vector4(0, 0, 100, 0) },
      uDraw: { value: 2 },
      uFeather: { value: 0.08 },
    },
  });
  const mesh = new Mesh(geometry, material);
  mesh.frustumCulled = false;
  mesh.renderOrder = options.renderOrder ?? 0;
  const un = material.uniforms as Record<string, { value: unknown }>;
  const num = (name: string, value: number): void => {
    if (un[name]!.value !== value) {
      un[name]!.value = value;
      world.invalidate();
    }
  };
  return {
    mesh,
    count,
    setOpacities(minor, major) {
      const v = un.uOpacities!.value as Vector2;
      if (v.x !== minor || v.y !== major) {
        v.set(minor, major);
        world.invalidate();
      }
    },
    setWidths(minor, major) {
      const v = un.uWidths!.value as Vector2;
      if (v.x !== minor || v.y !== major) {
        v.set(minor, major);
        world.invalidate();
      }
    },
    setGlow(opacity, width) {
      num("uGlowOpacity", opacity);
      num("uGlowWidth", width);
    },
    setDim: amount => num("uDim", amount),
    setFade(near, far) {
      const v = un.uFade!.value as Vector2;
      if (v.x !== near || v.y !== far) {
        v.set(near, far);
        world.invalidate();
      }
    },
    setReveal(x, z, radius, feather = 600) {
      const v = un.uReveal!.value as Vector4;
      const r = Number.isFinite(radius) ? radius : 1e6;
      if (v.x !== x || v.y !== z || v.z !== r || v.w !== feather) {
        v.set(x, z, r, feather);
        world.invalidate();
      }
    },
    setSpot(x, z, sigma, amount) {
      const v = un.uSpot!.value as Vector4;
      if (v.x !== x || v.y !== z || v.z !== sigma || v.w !== amount) {
        v.set(x, z, Math.max(1, sigma), amount);
        world.invalidate();
      }
    },
    setDraw(value, feather) {
      num("uDraw", value);
      if (feather !== undefined) num("uFeather", feather);
    },
  };
}

/** The whole city's streets as one living mesh: minor streets are kind 0, major streets kind 1. */
export function createLivingStreets(
  world: World,
  living: Living,
  streets: Streets,
  options: Partial<Omit<LivingLinesOptions, "segs" | "kinds" | "order">> = {},
): LivingLines {
  const { xy, count, minor } = streets;
  const segs = new Float32Array(count * 4);
  const kinds = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    segs[i * 4] = xy[i * 4]!;
    segs[i * 4 + 1] = -xy[i * 4 + 1]!;
    segs[i * 4 + 2] = xy[i * 4 + 2]!;
    segs[i * 4 + 3] = -xy[i * 4 + 3]!;
    kinds[i] = i < minor ? 0 : 1;
  }
  return createLivingLines(world, living, {
    segs,
    kinds,
    widths: options.widths ?? [0.9, 1.5],
    opacities: options.opacities ?? [0.3, 0.7],
    color: options.color ?? "line",
    highlight: options.highlight ?? "ink",
    depthTest: options.depthTest ?? false,
    renderOrder: options.renderOrder ?? 0,
  });
}

// ---- stacks -----------------------------------------------------------------------------------------------------

export interface StackSpec {
  x: number;
  z: number;
  /** How many lines the stack holds (a motion's conditions). */
  n: number;
  /** 0 to 1: when it rises in a wave (see setWave). Default 0. */
  order?: number;
}

export interface Stacks {
  mesh: Mesh;
  dots: Points;
  count: number;
  /** Set where each stack is going: `grow` (0 flat … 1 full height, may pass 1) and `tone` (-1 held back, 0 as
   *  drawn, 1 lit), one value per stack; each starts `delay[i]` seconds from now (default 0) and takes
   *  `duration` seconds. Buffers are uploaded once per call, not per frame. Returns when the last one ends, on
   *  the living clock (seconds). */
  setTargets(grow: Float32Array | null, tone: Float32Array | null, options?: { delay?: Float32Array; duration?: number }): number;
  /** One stack's values at once (a hover): returns when it ends. */
  setOne(index: number, grow: number | null, tone: number | null, duration?: number): number;
  /** The values now, by the same arithmetic as the shader. */
  growOf(index: number): number;
  toneOf(index: number): number;
  /** The height of a stack now, in metres above its base. */
  heightOf(index: number): number;
  /** Metres per line, and metres every stack floats above the ground. */
  setScale(perLine: number, lift: number): void;
  /** Width of a stack in CSS pixels, as drawn and when lit; size of its dot. */
  setSizes(width: number, litWidth: number, dot: number, litDot: number): void;
  /** One stack is the hero: its own width (CSS px), metres per line, how far it has turned to the stamp colour
   *  (0 to 1), one of its lines picked out (index from the bottom, amount 0 to 1), and `pin` (0 to 1): drawn as
   *  one unbroken line in the stamp's colour, a pin with the dot for its head. Nothing is invalidated when no
   *  value has changed, so it may be called every frame. */
  setHero(index: number, options: { width?: number; perLine?: number; red?: number; line?: number; lineAmount?: number; ring?: number; pin?: number }): void;
  /** Hold everything back (0 to 1). */
  setOpacity(amount: number): void;
  /** The stacks rise in a wave, in their `order`: 0 none has risen (dots only), 1 all have. `length` is how much
   *  of the order the wave spans. The hero does not wait for the wave: `heroGrow` (0 to 1) is its own. */
  setWave(amount: number, heroGrow?: number, length?: number): void;
}

const TWEEN = /* glsl */ `
uniform float uTime;
uniform vec3 uWave;
float tween(vec4 v) {
  float k = clamp((uTime - v.z) / max(v.w, 1e-3), 0.0, 1.0);
  k = k * k * (3.0 - 2.0 * k);
  return mix(v.x, v.y, k);
}
// the stacks rise in a wave, in their order: uWave.x how far the wave has got (0 to 1), uWave.y its length
float wave(float order) {
  float k = clamp((uWave.x * (1.0 + uWave.y) - order) / max(uWave.y, 1e-3), 0.0, 1.0);
  return k * k * (3.0 - 2.0 * k);
}
`;

const STACK_VERT = /* glsl */ `
attribute vec2 aBase;
attribute float aN;
attribute float aHero;
attribute vec4 aGrow;
attribute vec4 aTone;
attribute float aOrder;
uniform vec2 uViewport;
uniform float uPixelRatio;
uniform vec2 uScale;
uniform vec2 uWidth;
uniform vec4 uHero;
varying float vAlong;
varying float vAcross;
varying float vTone;
varying float vHero;
varying float vGlow;
varying float vHalf;
${TWEEN}
${LIVING_PARS}
void main() {
  float grow = tween(aGrow) * mix(wave(aOrder), uWave.z, aHero);
  float tone = tween(aTone);
  float glow;
  float ground = living(aBase, glow);
  float per = mix(uScale.x, uHero.y, aHero);
  float h = aN * per * grow;
  vec3 a = vec3(aBase.x, ground + uScale.y, aBase.y);
  vec3 b = a + vec3(0.0, h, 0.0);
  vec4 ca = projectionMatrix * modelViewMatrix * vec4(a, 1.0);
  vec4 cb = projectionMatrix * modelViewMatrix * vec4(b, 1.0);
  if (ca.w <= 0.0 || cb.w <= 0.0 || h <= 0.01) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    vAlong = 0.0; vAcross = 0.0; vTone = 0.0; vHero = 0.0; vGlow = 0.0; vHalf = 1.0;
    return;
  }
  vec2 sa = ca.xy / ca.w * uViewport;
  vec2 sb = cb.xy / cb.w * uViewport;
  vec2 d = sb - sa;
  float len = length(d);
  vec2 dir = len > 1e-5 ? d / len : vec2(0.0, 1.0);
  vec2 nrm = vec2(-dir.y, dir.x);
  float width = mix(mix(uWidth.x, uWidth.y, max(tone, 0.0)), uHero.x, aHero);
  float halfWidth = width * 0.5 + 0.5 / uPixelRatio;
  vec4 c = mix(ca, cb, position.y);
  c.xy += nrm * position.x * halfWidth * 2.0 / uViewport * c.w;
  gl_Position = c;
  vAlong = position.y * aN * grow;
  vAcross = position.x * halfWidth;
  vHalf = halfWidth;
  vTone = tone;
  vHero = aHero;
  vGlow = glow;
}
`;

const STACK_FRAG = /* glsl */ `
uniform vec3 uColor;
uniform vec3 uHi;
uniform vec2 uHeroLine;
uniform vec3 uStampColor;
uniform vec4 uHero;
uniform float uHeroPin;
uniform float uOpacity;
uniform float uPixelRatio;
varying float vAlong;
varying float vAcross;
varying float vTone;
varying float vHero;
varying float vGlow;
varying float vHalf;
void main() {
  float aa = 1.0 / uPixelRatio;
  float edge = clamp((vHalf - abs(vAcross)) / aa, 0.0, 1.0);
  // one stripe per line of the stack; where the stripes are too fine to draw, an even tone instead
  float period = max(fwidth(vAlong), 1e-5);
  float f = fract(vAlong);
  float duty = mix(0.56, 0.3, vHero);
  float stripe = smoothstep(0.0, period, f) * (1.0 - smoothstep(duty, duty + period, f));
  float fine = smoothstep(0.22, 0.6, period);
  float cover = mix(stripe, duty + 0.2, fine);
  float lit = max(vTone, 0.0);
  float dim = max(-vTone, 0.0);
  vec3 colour = mix(uColor, uHi, max(lit, min(1.0, vGlow)));
  float alpha = mix(0.86, 1.0, lit) * (1.0 - dim * 0.78);
  if (vHero > 0.5) {
    // the hero's lines: one of them picked out, the rest held back while it is
    float mine = 1.0 - min(1.0, abs(floor(vAlong) - uHeroLine.x));
    float picked = mine * uHeroLine.y;
    colour = mix(colour, uHi, picked);
    alpha *= mix(1.0, 0.42, uHeroLine.y * (1.0 - mine));
    // as a pin: one unbroken line in the stamp's colour, from the ground to the dot
    colour = mix(colour, uStampColor, uHero.z * uHeroPin);
    cover = mix(cover, 1.0, uHeroPin);
    alpha = mix(alpha, 1.0, uHeroPin);
  }
  alpha *= cover * edge * uOpacity;
  if (alpha < 0.004) discard;
  gl_FragColor = vec4(colour, alpha);
}
`;

const DOT_VERT = /* glsl */ `
attribute float aN;
attribute float aHero;
attribute vec4 aGrow;
attribute vec4 aTone;
attribute float aOrder;
uniform float uPixelRatio;
uniform vec2 uScale;
uniform vec2 uDot;
uniform vec4 uHero;
uniform float uHeroRing;
varying float vTone;
varying float vHero;
varying float vGlow;
varying float vSize;
${TWEEN}
${LIVING_PARS}
void main() {
  float grow = tween(aGrow) * mix(wave(aOrder), uWave.z, aHero);
  float tone = tween(aTone);
  float glow;
  float ground = living(position.xz, glow);
  float per = mix(uScale.x, uHero.y, aHero);
  vec3 p = vec3(position.x, ground + uScale.y + aN * per * grow, position.z);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  float size = mix(uDot.x, uDot.y, max(max(tone, 0.0), min(1.0, glow)));
  size *= 1.0 - max(-tone, 0.0) * 0.4;
  size = mix(size, max(size, uDot.y) * (1.0 + uHeroRing * 2.6), aHero * step(0.001, uHero.z));
  vSize = size * uPixelRatio;
  gl_PointSize = vSize + 2.0;
  vTone = tone;
  vHero = aHero;
  vGlow = glow;
}
`;

const DOT_FRAG = /* glsl */ `
uniform vec3 uColor;
uniform vec3 uHi;
uniform vec3 uStampColor;
uniform vec4 uHero;
uniform float uHeroRing;
uniform float uOpacity;
varying float vTone;
varying float vHero;
varying float vGlow;
varying float vSize;
void main() {
  float r = length(gl_PointCoord - 0.5) * (vSize + 2.0);
  float disc = clamp(vSize * 0.5 - r + 0.5, 0.0, 1.0);
  float lit = max(vTone, 0.0);
  float dim = max(-vTone, 0.0);
  vec3 colour = mix(uColor, uHi, max(lit, min(1.0, vGlow)));
  float alpha = (1.0 - dim * 0.7) * uOpacity;
  float red = vHero * uHero.z;
  if (red > 0.0) {
    colour = mix(colour, uStampColor, red);
    alpha = mix(alpha, 1.0, red);
    // while its ring runs, the hero's dot is a small disc inside a ring that widens and thins
    float inner = vSize * 0.5 / (1.0 + uHeroRing * 2.6);
    float core = clamp(inner - r + 0.5, 0.0, 1.0);
    float band = clamp(1.25 - abs(r - (vSize * 0.5 - 1.25)), 0.0, 1.0) * (1.0 - uHeroRing);
    disc = mix(disc, max(core, band), step(0.001, uHeroRing));
  }
  alpha *= disc;
  if (alpha < 0.01) discard;
  gl_FragColor = vec4(colour, alpha);
}
`;

/** The motions as stacks of lines standing on the living ground, with a dot at the top of each. */
export function createStacks(world: World, living: Living, specs: StackSpec[], options: { depthTest?: boolean } = {}): Stacks {
  const n = specs.length;
  const base = new Float32Array(n * 2);
  const pos = new Float32Array(n * 3);
  const counts = new Float32Array(n);
  const hero = new Float32Array(n);
  const order = new Float32Array(n);
  // from, to, start (seconds), duration (seconds)
  const grow = new Float32Array(n * 4);
  const tone = new Float32Array(n * 4);
  specs.forEach((s, i) => {
    base[i * 2] = s.x;
    base[i * 2 + 1] = s.z;
    pos[i * 3] = s.x;
    pos[i * 3 + 2] = s.z;
    counts[i] = s.n;
    order[i] = s.order ?? 0;
    grow[i * 4] = 1;
    grow[i * 4 + 1] = 1;
    grow[i * 4 + 3] = 1;
    tone[i * 4 + 3] = 1;
  });

  const u = world.uniforms;
  const l = living.uniforms;
  const shared = {
    uViewport: u.uViewport,
    uPixelRatio: u.uPixelRatio,
    uRelief: u.uRelief,
    uReliefAmount: u.uReliefAmount,
    uPointer: l.uPointer,
    uBulge: l.uBulge,
    uPointerGlow: l.uPointerGlow,
    uRings: l.uRings,
    uRingShape: l.uRingShape,
    uTime: l.uTime,
    uColor: u.uLine,
    uHi: u.uInk,
    uStampColor: u.uStamp,
    uScale: { value: new Vector2(30, 40) },
    uHero: { value: new Vector4(6, 30, 0, 0) },
    uHeroLine: { value: new Vector2(-1, 0) },
    uHeroRing: { value: 0 },
    uHeroPin: { value: 0 },
    uWave: { value: new Vector3(1, 0.25, 1) },
    uOpacity: { value: 1 },
  };

  const geometry = new InstancedBufferGeometry();
  // a quad: x across (-1, 1), y along (0 base, 1 top)
  geometry.setAttribute("position", new Float32BufferAttribute([-1, 0, 0, 1, 0, 0, 1, 1, 0, -1, 1, 0], 3));
  geometry.setIndex([0, 1, 2, 0, 2, 3]);
  const growA = new InstancedBufferAttribute(grow, 4);
  const toneA = new InstancedBufferAttribute(tone, 4);
  const heroA = new InstancedBufferAttribute(hero, 1);
  geometry.setAttribute("aBase", new InstancedBufferAttribute(base, 2));
  geometry.setAttribute("aN", new InstancedBufferAttribute(counts, 1));
  geometry.setAttribute("aHero", heroA);
  geometry.setAttribute("aGrow", growA);
  geometry.setAttribute("aTone", toneA);
  geometry.setAttribute("aOrder", new InstancedBufferAttribute(order, 1));
  geometry.instanceCount = n;
  const material = new ShaderMaterial({
    vertexShader: STACK_VERT,
    fragmentShader: STACK_FRAG,
    // a stack's quad is laid out on the screen, so which way it winds depends on the view
    side: DoubleSide,
    transparent: true,
    depthTest: options.depthTest ?? false,
    depthWrite: false,
    uniforms: { ...shared, uWidth: { value: new Vector2(5, 8) } },
  });
  const mesh = new Mesh(geometry, material);
  mesh.frustumCulled = false;
  mesh.renderOrder = 4;

  const dotGeometry = new BufferGeometry();
  // the dots share the stacks' own arrays (a BufferAttribute does not copy what it is given)
  const growD = new BufferAttribute(grow, 4);
  const toneD = new BufferAttribute(tone, 4);
  const heroD = new BufferAttribute(hero, 1);
  dotGeometry.setAttribute("position", new Float32BufferAttribute(pos, 3));
  dotGeometry.setAttribute("aN", new Float32BufferAttribute(counts, 1));
  dotGeometry.setAttribute("aHero", heroD);
  dotGeometry.setAttribute("aGrow", growD);
  dotGeometry.setAttribute("aTone", toneD);
  dotGeometry.setAttribute("aOrder", new Float32BufferAttribute(order, 1));
  const dotMaterial = new ShaderMaterial({
    vertexShader: DOT_VERT,
    fragmentShader: DOT_FRAG,
    transparent: true,
    depthTest: options.depthTest ?? false,
    depthWrite: false,
    uniforms: { ...shared, uDot: { value: new Vector2(3.4, 6) } },
  });
  const dots = new Points(dotGeometry, dotMaterial);
  dots.frustumCulled = false;
  dots.renderOrder = 5;

  const now = (): number => l.uTime.value;
  const valueOf = (arr: Float32Array, i: number): number => {
    const from = arr[i * 4]!, to = arr[i * 4 + 1]!, t0 = arr[i * 4 + 2]!, dur = arr[i * 4 + 3]!;
    let k = Math.min(1, Math.max(0, (now() - t0) / Math.max(dur, 1e-3)));
    k = k * k * (3 - 2 * k);
    return from + (to - from) * k;
  };
  const retarget = (arr: Float32Array, i: number, to: number, start: number, duration: number): void => {
    arr[i * 4] = valueOf(arr, i);
    arr[i * 4 + 1] = to;
    arr[i * 4 + 2] = start;
    arr[i * 4 + 3] = duration;
  };
  const upload = (growChanged: boolean, toneChanged: boolean): void => {
    if (growChanged) {
      growA.needsUpdate = true;
      growD.needsUpdate = true;
    }
    if (toneChanged) {
      toneA.needsUpdate = true;
      toneD.needsUpdate = true;
    }
    world.invalidate();
  };
  let heroIndex = -1;
  const su = shared;
  return {
    mesh,
    dots,
    count: n,
    setTargets(g, t, { delay, duration = 0.6 } = {}) {
      const t0 = now();
      let end = t0;
      for (let i = 0; i < n; i++) {
        const start = t0 + (delay ? delay[i]! : 0);
        if (g && g[i] !== grow[i * 4 + 1]) retarget(grow, i, g[i]!, start, duration);
        if (t && t[i] !== tone[i * 4 + 1]) retarget(tone, i, t[i]!, start, Math.min(duration, 0.4));
        if (start + duration > end) end = start + duration;
      }
      upload(Boolean(g), Boolean(t));
      return end;
    },
    setOne(i, g, t, duration = 0.3) {
      const t0 = now();
      if (g !== null && g !== grow[i * 4 + 1]) retarget(grow, i, g, t0, duration);
      if (t !== null && t !== tone[i * 4 + 1]) retarget(tone, i, t, t0, Math.min(duration, 0.25));
      upload(g !== null, t !== null);
      return t0 + duration;
    },
    growOf: i => valueOf(grow, i),
    toneOf: i => valueOf(tone, i),
    heightOf(i) {
      const w = su.uWave.value;
      if (i === heroIndex) return counts[i]! * su.uHero.value.y * valueOf(grow, i) * w.z;
      let k = Math.min(1, Math.max(0, (w.x * (1 + w.y) - order[i]!) / Math.max(w.y, 1e-3)));
      k = k * k * (3 - 2 * k);
      return counts[i]! * su.uScale.value.x * valueOf(grow, i) * k;
    },
    setScale(perLine, lift) {
      const v = su.uScale.value;
      if (v.x !== perLine || v.y !== lift) {
        v.set(perLine, lift);
        world.invalidate();
      }
    },
    setSizes(width, litWidth, dot, litDot) {
      const a = material.uniforms.uWidth!.value as Vector2;
      const b = dotMaterial.uniforms.uDot!.value as Vector2;
      if (a.x === width && a.y === litWidth && b.x === dot && b.y === litDot) return;
      a.set(width, litWidth);
      b.set(dot, litDot);
      world.invalidate();
    },
    setHero(index, o) {
      let changed = false;
      if (index !== heroIndex) {
        if (heroIndex >= 0) hero[heroIndex] = 0;
        heroIndex = index;
        if (index >= 0) hero[index] = 1;
        heroA.needsUpdate = true;
        heroD.needsUpdate = true;
        changed = true;
      }
      const h = su.uHero.value;
      if (o.width !== undefined && h.x !== o.width) {
        h.x = o.width;
        changed = true;
      }
      if (o.perLine !== undefined && h.y !== o.perLine) {
        h.y = o.perLine;
        changed = true;
      }
      if (o.red !== undefined && h.z !== o.red) {
        h.z = o.red;
        changed = true;
      }
      if (o.line !== undefined && su.uHeroLine.value.x !== o.line) {
        su.uHeroLine.value.x = o.line;
        changed = true;
      }
      if (o.lineAmount !== undefined && su.uHeroLine.value.y !== o.lineAmount) {
        su.uHeroLine.value.y = o.lineAmount;
        changed = true;
      }
      if (o.ring !== undefined && su.uHeroRing.value !== o.ring) {
        su.uHeroRing.value = o.ring;
        changed = true;
      }
      if (o.pin !== undefined && su.uHeroPin.value !== o.pin) {
        su.uHeroPin.value = o.pin;
        changed = true;
      }
      if (changed) world.invalidate();
    },
    setOpacity(amount) {
      if (su.uOpacity.value !== amount) {
        su.uOpacity.value = amount;
        world.invalidate();
      }
    },
    setWave(amount, heroGrow, length) {
      const w = su.uWave.value;
      const hg = heroGrow ?? w.z;
      const len = length ?? w.y;
      if (w.x !== amount || w.z !== hg || w.y !== len) {
        w.set(amount, len, hg);
        world.invalidate();
      }
    },
  };
}
