// The world: one renderer, one scene, one camera, the theme as shared uniforms, and render on demand.
//
//   const world = createWorld(canvas, { relief: [{ x, z, radius, height }] });
//   world.scene.add(createStreets(world, streets).group);
//   setPose(world, pose);            // see rig.ts
//   world.invalidate();              // something changed
//   // in the page's one animation frame:
//   if (world.update(now)) world.render();
//
// Nothing here knows about any page. Colours come from the CSS tokens (--paper, --ink, --line, --stamp), so a
// scene follows the theme; a theme change tweens the shared colour uniforms (about 300 ms) and never rebuilds
// anything. The canvas is transparent: the paper is the page's own background.

import { Color, LinearSRGBColorSpace, PerspectiveCamera, Scene, Vector2, Vector3, Vector4, WebGLRenderer } from "three";
import { lowPower } from "../env";
import type { Ground } from "./projection";
import { reliefHeight, type Relief } from "./relief";

export type { Relief } from "./relief";

export const MAX_RELIEF = 4;

export type PaletteKey = "paper" | "paper2" | "ink" | "ink2" | "line" | "stamp" | "shade";

/** Uniform objects shared by every material in a world: change a value once and every material follows. */
export interface SharedUniforms {
  uPaper: { value: Color };
  uPaper2: { value: Color };
  uInk: { value: Color };
  uInk2: { value: Color };
  uLine: { value: Color };
  uStamp: { value: Color };
  /** The colour of faces turned away from the light. */
  uShade: { value: Color };
  /** Size of the drawing buffer in CSS pixels. */
  uViewport: { value: Vector2 };
  /** Device pixels per CSS pixel in use. */
  uPixelRatio: { value: number };
  /** x, z, radius, height of each rise in the ground. */
  uRelief: { value: Vector4[] };
  /** 0 to 1: how far the ground has risen. */
  uReliefAmount: { value: number };
  /** Direction to the light, for the two-step shading of faces. */
  uLight: { value: Vector3 };
}

export interface WorldOptions {
  relief?: Relief[];
  /** Cap on the device pixel ratio. Default 2, or 1.5 when lowPower(). */
  maxPixelRatio?: number;
  /** Where the tokens are read from. Default <html>. */
  tokens?: Element;
}

export interface World {
  canvas: HTMLCanvasElement;
  renderer: WebGLRenderer;
  scene: Scene;
  camera: PerspectiveCamera;
  uniforms: SharedUniforms;
  /** Size in CSS pixels. */
  width: number;
  height: number;
  /** Set the size of the drawing in CSS pixels (the canvas's CSS size is the page's business). */
  setSize(width: number, height: number): void;
  /** Read the colours again from the tokens and tween to them. `instant` skips the tween. */
  setTheme(options?: { instant?: boolean }): void;
  /** How far the ground has risen, 0 to 1 (the lines follow in the vertex shader). */
  setRelief(amount: number): void;
  /** Height of the ground at a point, in metres, at the current relief amount (or at `amount`). */
  heightAt(x: number, z: number, amount?: number): number;
  /** Say that something changed and a frame is due. */
  invalidate(): void;
  /** Advance the world's own tweens (the theme). Returns true when a frame should be drawn. */
  update(now: number): boolean;
  /** Draw a frame now. */
  render(): void;
  /** The point on the ground (y = 0) under a point of the canvas given in CSS pixels from its top left, or null
   *  when the ray misses the ground. */
  groundAt(px: number, py: number, out?: Ground): Ground | null;
  /** Where a world point lands on the canvas, in CSS pixels from its top left. `behind` is true when the point is
   *  behind the camera. */
  toScreen(x: number, y: number, z: number, out?: ScreenPoint): ScreenPoint;
  /** Metres on the ground per CSS pixel, measured across the view at a point on the ground. */
  metresPerPixel(x: number, z: number): number;
  /** Listeners for a lost and restored GL context are set here; call to free everything. */
  dispose(): void;
}

export interface ScreenPoint {
  x: number;
  y: number;
  behind: boolean;
}

const THEME_MS = 300;

function readToken(el: Element, name: string, into: Color): Color {
  const raw = getComputedStyle(el).getPropertyValue(name).trim();
  try {
    // the shaders write these values straight to the screen, so they are kept as the CSS gives them (no conversion)
    if (raw) into.setStyle(raw, LinearSRGBColorSpace);
  } catch {
    // an unreadable token keeps the colour it had
  }
  return into;
}

/** Make a world on a canvas. Throws when a WebGL context cannot be made (check hasWebGL() first). */
export function createWorld(canvas: HTMLCanvasElement, options: WorldOptions = {}): World {
  const tokens = options.tokens ?? document.documentElement;
  const maxRatio = options.maxPixelRatio ?? (lowPower() ? 1.5 : 2);
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  // (checking every shader's compile log makes the first frame of each wait on the compiler: the dev server only)
  renderer.debug.checkShaderErrors = import.meta.env.DEV;
  renderer.setClearColor(0x000000, 0);
  const scene = new Scene();
  const camera = new PerspectiveCamera(30, 1, 10, 60000);

  const relief = (options.relief ?? []).slice(0, MAX_RELIEF);
  const uniforms: SharedUniforms = {
    uPaper: { value: new Color() },
    uPaper2: { value: new Color() },
    uInk: { value: new Color() },
    uInk2: { value: new Color() },
    uLine: { value: new Color() },
    uStamp: { value: new Color() },
    uShade: { value: new Color() },
    uViewport: { value: new Vector2(1, 1) },
    uPixelRatio: { value: 1 },
    uRelief: { value: Array.from({ length: MAX_RELIEF }, (_, i) => {
      const r = relief[i];
      return r ? new Vector4(r.x, r.z, r.radius, r.height) : new Vector4(0, 0, 1, 0);
    }) },
    uReliefAmount: { value: 0 },
    uLight: { value: new Vector3(-0.36, 0.84, 0.4).normalize() },
  };

  // ---- the theme: read the tokens, tween the shared colours ----------------------------------------------------
  const keys = ["uPaper", "uPaper2", "uInk", "uInk2", "uLine", "uStamp", "uShade"] as const;
  const from = keys.map(() => new Color());
  const to = keys.map(() => new Color());
  let themeStart = -1;
  const readTheme = (): void => {
    readToken(tokens, "--paper", to[0]!);
    readToken(tokens, "--paper-2", to[1]!);
    readToken(tokens, "--ink", to[2]!);
    readToken(tokens, "--ink-2", to[3]!);
    readToken(tokens, "--line", to[4]!);
    readToken(tokens, "--stamp", to[5]!);
    // faces in shadow: cobalt on paper; on the dark ground the pale cobalt is held back so a wall does not glare
    const dark = to[0]!.r + to[0]!.g + to[0]!.b < 1.2;
    to[6]!.copy(to[4]!);
    if (dark) to[6]!.lerp(to[0]!, 0.42);
  };
  const applyTheme = (k: number): void => {
    keys.forEach((key, i) => uniforms[key].value.copy(from[i]!).lerp(to[i]!, k));
  };
  readTheme();
  applyTheme(1);

  let dirty = true;
  let disposed = false;
  let width = 1, height = 1;

  const ndc = new Vector3();
  const origin = new Vector3();
  const dir = new Vector3();
  const tmpGround: Ground = { x: 0, z: 0 };
  const tmpScreen: ScreenPoint = { x: 0, y: 0, behind: false };

  const onLost = (event: Event): void => {
    event.preventDefault();
  };
  const onRestored = (): void => {
    dirty = true;
  };
  canvas.addEventListener("webglcontextlost", onLost);
  canvas.addEventListener("webglcontextrestored", onRestored);

  const world: World = {
    canvas,
    renderer,
    scene,
    camera,
    uniforms,
    width,
    height,
    setSize(w, h) {
      width = Math.max(1, Math.round(w));
      height = Math.max(1, Math.round(h));
      world.width = width;
      world.height = height;
      const ratio = Math.min(window.devicePixelRatio || 1, maxRatio);
      renderer.setPixelRatio(ratio);
      renderer.setSize(width, height, false);
      uniforms.uViewport.value.set(width, height);
      uniforms.uPixelRatio.value = ratio;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      dirty = true;
    },
    setTheme({ instant = false } = {}) {
      keys.forEach((key, i) => from[i]!.copy(uniforms[key].value));
      readTheme();
      if (instant) {
        applyTheme(1);
        themeStart = -1;
      } else {
        themeStart = 0; // stamped with the clock on the next update
      }
      dirty = true;
    },
    setRelief(amount) {
      if (uniforms.uReliefAmount.value !== amount) {
        uniforms.uReliefAmount.value = amount;
        dirty = true;
      }
    },
    heightAt(x, z, amount = uniforms.uReliefAmount.value) {
      return reliefHeight(relief, x, z) * amount;
    },
    invalidate() {
      dirty = true;
    },
    update(now) {
      if (themeStart >= 0) {
        if (themeStart === 0) themeStart = now;
        const k = Math.min(1, (now - themeStart) / THEME_MS);
        applyTheme(k * k * (3 - 2 * k));
        if (k >= 1) themeStart = -1;
        dirty = true;
      }
      return dirty;
    },
    render() {
      if (disposed) return;
      dirty = false;
      renderer.render(scene, camera);
    },
    groundAt(px, py, out = tmpGround) {
      camera.updateMatrixWorld();
      ndc.set((px / width) * 2 - 1, -(py / height) * 2 + 1, 0.5).unproject(camera);
      origin.setFromMatrixPosition(camera.matrixWorld);
      dir.copy(ndc).sub(origin).normalize();
      if (dir.y >= -1e-6) return null;
      const t = -origin.y / dir.y;
      out.x = origin.x + dir.x * t;
      out.z = origin.z + dir.z * t;
      return out;
    },
    toScreen(x, y, z, out = tmpScreen) {
      camera.updateMatrixWorld();
      ndc.set(x, y, z).applyMatrix4(camera.matrixWorldInverse);
      out.behind = ndc.z > -camera.near;
      ndc.applyMatrix4(camera.projectionMatrix);
      out.x = (ndc.x * 0.5 + 0.5) * width;
      out.y = (-ndc.y * 0.5 + 0.5) * height;
      return out;
    },
    metresPerPixel(x, z) {
      // a metre across the view (perpendicular to the camera's line of sight, on the ground) at this point
      camera.updateMatrixWorld();
      const e = camera.matrixWorld.elements;
      const rx = e[0]!, rz = e[2]!;
      const len = Math.hypot(rx, rz) || 1;
      const a = world.toScreen(x, 0, z, { x: 0, y: 0, behind: false });
      const b = world.toScreen(x + (rx / len) * 100, 0, z + (rz / len) * 100, { x: 0, y: 0, behind: false });
      const px = Math.hypot(b.x - a.x, b.y - a.y);
      return px > 0 ? 100 / px : Infinity;
    },
    dispose() {
      disposed = true;
      canvas.removeEventListener("webglcontextlost", onLost);
      canvas.removeEventListener("webglcontextrestored", onRestored);
      scene.traverse(object => {
        const o = object as { geometry?: { dispose(): void }; material?: { dispose(): void } | { dispose(): void }[] };
        o.geometry?.dispose();
        if (Array.isArray(o.material)) o.material.forEach(m => m.dispose());
        else o.material?.dispose();
      });
      renderer.dispose();
    },
  };
  return world;
}

/** GLSL: the height of the ground at a point (declare with RELIEF_PARS, call relief(xz)). */
export const RELIEF_PARS = /* glsl */ `
uniform vec4 uRelief[${MAX_RELIEF}];
uniform float uReliefAmount;
float relief(vec2 p) {
  float h = 0.0;
  for (int i = 0; i < ${MAX_RELIEF}; i++) {
    vec2 d = p - uRelief[i].xy;
    h += uRelief[i].w * exp(-dot(d, d) / (0.36 * uRelief[i].z * uRelief[i].z));
  }
  return h * uReliefAmount;
}
`;
