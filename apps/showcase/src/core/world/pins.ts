// Points on the map as thin standing pins: a stem (a line from the ground up) and a head (a dot at its top).
// Static buffers; the rise and the dimming are done in the vertex shader.

import { BufferGeometry, Float32BufferAttribute, Group, Points, ShaderMaterial } from "three";
import { createSegments, FULL, type Segments } from "./lines";
import { RELIEF_PARS, type World } from "./world";

export interface Pin {
  x: number;
  z: number;
  /** Height of the pin in metres. */
  height: number;
  /** 0 to 1: when it rises. */
  order: number;
}

export interface Pins {
  group: Group;
  stems: Segments;
  count: number;
  /** 0 to 1: how many of the pins have risen, in their order. 1 is all of them. */
  setRise(amount: number): void;
  /** One value per pin, 0 (standing, in the line colour) to 1 (dimmed and lowered). */
  setDim(values: Float32Array): void;
  setHeadSize(px: number): void;
}

const HEAD_VERT = /* glsl */ `
attribute vec3 aTop;
attribute float aOrder;
attribute float aTone;
uniform float uDraw;
uniform float uFeather;
uniform float uToneLength;
uniform float uSize;
uniform float uPixelRatio;
varying float vTone;
varying float vShow;
${RELIEF_PARS}
void main() {
  float r = clamp((uDraw - aOrder) / max(uFeather, 1e-4), 0.0, 1.0);
  vShow = r;
  r *= mix(1.0, uToneLength, aTone);
  vec3 p = mix(position, aTop, r);
  p.y += relief(p.xz);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  gl_PointSize = uSize * uPixelRatio * mix(1.0, 0.7, aTone);
  vTone = aTone;
}
`;

const HEAD_FRAG = /* glsl */ `
uniform vec3 uColor;
uniform vec3 uToneColor;
uniform float uToneOpacity;
uniform float uSize;
uniform float uPixelRatio;
varying float vTone;
varying float vShow;
void main() {
  float d = length(gl_PointCoord - 0.5) * 2.0;
  float px = uSize * uPixelRatio * 0.5;
  float edge = clamp((1.0 - d) * px, 0.0, 1.0);
  float alpha = edge * mix(1.0, uToneOpacity, vTone) * step(0.001, vShow);
  if (alpha < 0.01) discard;
  gl_FragColor = vec4(mix(uColor, uToneColor, vTone), alpha);
}
`;

/** Build the pins. Add `group` to the scene. */
export function createPins(world: World, pins: Pin[], options: { width?: number; head?: number } = {}): Pins {
  const n = pins.length;
  const starts = new Float32Array(n * 3);
  const ends = new Float32Array(n * 3);
  const order = new Float32Array(n);
  const tone = new Float32Array(n);
  pins.forEach((p, i) => {
    starts[i * 3] = p.x;
    starts[i * 3 + 2] = p.z;
    ends[i * 3] = p.x;
    ends[i * 3 + 1] = p.height;
    ends[i * 3 + 2] = p.z;
    order[i] = p.order;
  });
  const stems = createSegments(world, {
    starts,
    ends,
    order,
    tone,
    width: options.width ?? 1.2,
    color: "line",
    opacity: 0.95,
    toneColor: "ink2",
    toneOpacity: 0.3,
    toneWidth: 1,
    toneLength: 0.3,
    depthTest: true,
    renderOrder: 4,
  });
  stems.setFeather(0.04);

  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(starts, 3));
  geometry.setAttribute("aTop", new Float32BufferAttribute(ends, 3));
  geometry.setAttribute("aOrder", new Float32BufferAttribute(order, 1));
  const headTone = new Float32BufferAttribute(new Float32Array(n), 1);
  geometry.setAttribute("aTone", headTone);
  const u = world.uniforms;
  const material = new ShaderMaterial({
    vertexShader: HEAD_VERT,
    fragmentShader: HEAD_FRAG,
    transparent: true,
    depthTest: true,
    depthWrite: false,
    uniforms: {
      uRelief: u.uRelief,
      uReliefAmount: u.uReliefAmount,
      uPixelRatio: u.uPixelRatio,
      uColor: u.uLine,
      uToneColor: u.uInk2,
      uToneOpacity: { value: 0.35 },
      uToneLength: { value: 0.3 },
      uDraw: { value: FULL },
      uFeather: { value: 0.04 },
      uSize: { value: options.head ?? 4.5 },
    },
  });
  const heads = new Points(geometry, material);
  heads.frustumCulled = false;
  heads.renderOrder = 5;
  const group = new Group();
  group.add(stems.mesh, heads);
  const hu = material.uniforms as Record<string, { value: number }>;

  const api: Pins = {
    group,
    stems,
    count: n,
    setRise(amount) {
      const draw = amount >= 1 ? FULL : amount * 1.04;
      stems.setDraw(draw);
      if (hu.uDraw!.value !== draw) {
        hu.uDraw!.value = draw;
        world.invalidate();
      }
    },
    setDim(values) {
      stems.setTone(values);
      (headTone.array as Float32Array).set(values);
      headTone.needsUpdate = true;
      world.invalidate();
    },
    setHeadSize(px) {
      if (hu.uSize!.value !== px) {
        hu.uSize!.value = px;
        world.invalidate();
      }
    },
  };
  api.setRise(0);
  return api;
}
