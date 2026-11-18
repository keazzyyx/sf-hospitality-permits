// The city's streets as two sets of lines (minor and major), drawn on from a point outward.

import { Group } from "three";
import type { Streets } from "./data";
import { createSegments, FULL, type Segments } from "./lines";
import type { Ground } from "./projection";
import type { World } from "./world";

export interface StreetsOptions {
  /** Where the drawing starts: the streets draw on outward from here. Default: the centre of the data. */
  origin?: Ground;
  /** Line widths in CSS pixels. */
  minorWidth?: number;
  majorWidth?: number;
  minorOpacity?: number;
  majorOpacity?: number;
}

export interface StreetLines {
  group: Group;
  minor: Segments;
  major: Segments;
  /** 0 to 1: how much of the city is drawn (major streets lead, minor streets follow). 1 is everything. */
  setDraw(amount: number): void;
  /** Fade the minor streets with distance from the camera (metres); far 0 for no fade. */
  setFade(near: number, far: number): void;
  /** Hold the whole map back (0 to 1, 1 is full strength), so what stands on it reads first. */
  setStrength(amount: number): void;
}

/** Build the street lines. Add `group` to the scene. */
export function createStreets(world: World, streets: Streets, options: StreetsOptions = {}): StreetLines {
  const origin = options.origin ?? { x: 0, z: 0 };
  const { xy, count, minor } = streets;
  const build = (from: number, to: number): { starts: Float32Array; ends: Float32Array; order: Float32Array } => {
    const n = to - from;
    const starts = new Float32Array(n * 3);
    const ends = new Float32Array(n * 3);
    const order = new Float32Array(n);
    let far = 1;
    for (let i = 0; i < n; i++) {
      const s = (from + i) * 4;
      let x1 = xy[s]!, z1 = -xy[s + 1]!, x2 = xy[s + 2]!, z2 = -xy[s + 3]!;
      let d1 = Math.hypot(x1 - origin.x, z1 - origin.z);
      const d2 = Math.hypot(x2 - origin.x, z2 - origin.z);
      // each segment grows away from the origin
      if (d2 < d1) {
        [x1, z1, x2, z2] = [x2, z2, x1, z1];
        d1 = d2;
      }
      starts[i * 3] = x1;
      starts[i * 3 + 2] = z1;
      ends[i * 3] = x2;
      ends[i * 3 + 2] = z2;
      order[i] = d1;
      if (d1 > far) far = d1;
    }
    for (let i = 0; i < n; i++) order[i] = order[i]! / far;
    return { starts, ends, order };
  };
  const minorOpacity = options.minorOpacity ?? 0.42;
  const majorOpacity = options.majorOpacity ?? 0.88;
  const minorLines = createSegments(world, {
    ...build(0, minor),
    width: options.minorWidth ?? 0.9,
    color: "ink",
    opacity: minorOpacity,
    depthTest: true,
    renderOrder: 0,
  });
  const majorLines = createSegments(world, {
    ...build(minor, count),
    width: options.majorWidth ?? 1.5,
    color: "ink",
    opacity: majorOpacity,
    depthTest: true,
    renderOrder: 1,
  });
  minorLines.setFeather(0.05);
  majorLines.setFeather(0.05);
  const group = new Group();
  group.add(minorLines.mesh, majorLines.mesh);
  const api: StreetLines = {
    group,
    minor: minorLines,
    major: majorLines,
    setDraw(amount) {
      if (amount >= 1) {
        minorLines.setDraw(FULL);
        majorLines.setDraw(FULL);
        return;
      }
      // the major streets run ahead: done at 0.6; the minor streets start at 0.25 and finish at 1
      majorLines.setDraw((amount / 0.6) * 1.05);
      minorLines.setDraw(((amount - 0.25) / 0.75) * 1.05);
    },
    setFade(near, far) {
      minorLines.setFade(near, far);
    },
    setStrength(amount) {
      minorLines.setOpacity(minorOpacity * amount);
      majorLines.setOpacity(majorOpacity * amount);
    },
  };
  api.setDraw(0);
  return api;
}
