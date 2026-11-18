// The stamp in three.js: lathe handle, bevelled mount, rubber die; two-step toon shading (paper where the light
// falls, cobalt in shadow, the die vermilion); ink outlines (an inverted hull for the two boxes; for the handle,
// which is concave, an expanded copy drawn only where the handle itself is not: its silhouette and nothing
// inside it); a flat hatched shadow on the page plane. This module is loaded lazily (it carries three.js). One
// renderer, one small canvas that follows the stamp, a frame only when the pose changes; a theme change eases
// the colours in the shaders.

import {
  AlwaysStencilFunc,
  BackSide,
  BufferAttribute,
  BufferGeometry,
  CanvasTexture,
  CircleGeometry,
  EdgesGeometry,
  Group,
  KeepStencilOp,
  LatheGeometry,
  LineBasicMaterial,
  LineSegments,
  LinearFilter,
  Mesh,
  NotEqualStencilFunc,
  OrthographicCamera,
  PlaneGeometry,
  ReplaceStencilOp,
  RingGeometry,
  Scene,
  ShaderMaterial,
  Vector2,
  WebGLRenderer,
} from "three";
import { lowPower } from "../env";
import { MARK_TYPE } from "./mark";
import { cssColor, type StampPose, type StampRenderer } from "./pose";
import { DIE, ELEVATION, FORESHORTEN, GROOVES, GROOVES_FINE, HANDLE, LIGHT, MOUNT, MOUNT_TOP, SCREWS, STAMP_HEIGHT, TONE_THRESHOLD } from "./shape";

type RGB = [number, number, number];

const TONE_VERTEX = /* glsl */ `
  varying vec3 vNormal;
  varying float vHeight;
  varying vec2 vUv;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    vHeight = position.y;
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;
const TONE_FRAGMENT = /* glsl */ `
  uniform vec3 uLit;
  uniform vec3 uShade;
  uniform vec3 uInk;
  uniform vec3 uLight;
  uniform float uThreshold;
  uniform vec3 uGrooves; // two heights and the half width of a groove (0: none)
  uniform vec3 uFine;    // three finer grooves (heights); drawn at 0.55 of the width
  uniform sampler2D uLabel; // the paper label on the mount's front: red is paper, green is ink
  uniform float uLabelled;
  varying vec3 vNormal;
  varying float vHeight;
  varying vec2 vUv;
  void main() {
    float d = dot(normalize(vNormal), uLight) - uThreshold;
    float w = fwidth(d) * 0.75 + 0.0001;
    vec3 c = mix(uShade, uLit, smoothstep(-w, w, d));
    if (uGrooves.z > 0.0) {
      float g = min(abs(vHeight - uGrooves.x), abs(vHeight - uGrooves.y));
      float gw = fwidth(vHeight);
      c = mix(uInk, c, smoothstep(uGrooves.z - gw, uGrooves.z + gw, g));
      float f = min(min(abs(vHeight - uFine.x), abs(vHeight - uFine.y)), abs(vHeight - uFine.z));
      c = mix(uInk, c, smoothstep(uGrooves.z * 0.55 - gw, uGrooves.z * 0.55 + gw, f));
    }
    if (uLabelled > 0.5 && vUv.x >= 0.0) {
      vec4 label = texture2D(uLabel, vUv);
      c = mix(c, uLit, label.r);
      c = mix(c, uInk, label.g);
    }
    gl_FragColor = vec4(c, 1.0);
  }
`;
// the die's face: the relief (frame and mirrored letters) stands proud and holds the ink
const FACE_FRAGMENT = /* glsl */ `
  uniform vec3 uLit;
  uniform vec3 uShade;
  uniform sampler2D uMap;
  varying vec2 vUv;
  void main() {
    float relief = texture2D(uMap, vUv).r;
    gl_FragColor = vec4(mix(uShade, uLit, relief), 1.0);
  }
`;
const HULL_VERTEX = /* glsl */ `
  attribute vec3 aSmooth;
  uniform float uWidth;
  uniform float uPull; // toward the viewer, in view units (0 for an inverted hull)
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vec3 n = normalize(normalMatrix * aSmooth);
    // a normal that points at the viewer still has to push the outline out by its full width
    vec2 out2 = n.xy / max(length(n.xy), 0.35);
    mv.xy += mix(n.xy, out2, step(0.5, uPull)) * uWidth;
    mv.z += uPull;
    gl_Position = projectionMatrix * mv;
  }
`;
// flat colour, for the small things drawn on the mount's top (screw heads)
const FLAT_VERTEX = /* glsl */ `
  void main() {
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;
const HULL_FRAGMENT = /* glsl */ `
  uniform vec3 uInk;
  void main() {
    gl_FragColor = vec4(uInk, 1.0);
  }
`;
const SHADOW_VERTEX = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;
// the shadow is drawn, not shaded: a flat shape with a hard edge, hatched in the line colour. The hatching opens
// up as the stamp rises (uGap), so the height reads from the shadow's offset, its size and its density.
const SHADOW_FRAGMENT = /* glsl */ `
  uniform vec3 uColor;
  uniform float uAlpha;
  uniform vec2 uSize;  // the shape's width and depth, in the stamp's units
  uniform float uGap;  // distance between hatch lines
  uniform float uLine; // width of a hatch line
  varying vec2 vUv;
  void main() {
    vec2 q = (vUv - 0.5) * uSize;
    // a rectangle with slightly rounded corners, cut hard
    vec2 d2 = abs(q) - (uSize * 0.5 - 5.0);
    float edge = length(max(d2, 0.0)) - 5.0;
    float inside = 1.0 - smoothstep(-fwidth(edge), 0.0, edge);
    // hatching at 45 degrees
    float t = (q.x + q.y) * 0.70710678;
    float nearest = abs(fract(t / uGap + 0.5) - 0.5) * uGap;
    float aa = fwidth(t);
    float ink = 1.0 - smoothstep(uLine * 0.5 - aa, uLine * 0.5 + aa, nearest);
    gl_FragColor = vec4(uColor, ink * inside * uAlpha);
  }
`;

/** A box with its top edge cut back by `bevel` (0: a plain box), flat shaded, y from y0 to y1. */
function bevelBox(w: number, d: number, y0: number, y1: number, bevel: number): BufferGeometry {
  const hw = w / 2;
  const hd = d / 2;
  const ys = y1 - bevel;
  const tw = hw - bevel;
  const td = hd - bevel;
  const quads: number[][] = [
    // bottom
    [-hw, y0, -hd, hw, y0, -hd, hw, y0, hd, -hw, y0, hd],
    // sides: front (+z), back, right, left
    [-hw, y0, hd, hw, y0, hd, hw, ys, hd, -hw, ys, hd],
    [hw, y0, -hd, -hw, y0, -hd, -hw, ys, -hd, hw, ys, -hd],
    [hw, y0, hd, hw, y0, -hd, hw, ys, -hd, hw, ys, hd],
    [-hw, y0, -hd, -hw, y0, hd, -hw, ys, hd, -hw, ys, -hd],
    // top
    [-tw, y1, td, tw, y1, td, tw, y1, -td, -tw, y1, -td],
  ];
  if (bevel > 0) {
    quads.push(
      [-hw, ys, hd, hw, ys, hd, tw, y1, td, -tw, y1, td],
      [hw, ys, -hd, -hw, ys, -hd, -tw, y1, -td, tw, y1, -td],
      [hw, ys, hd, hw, ys, -hd, tw, y1, -td, tw, y1, td],
      [-hw, ys, -hd, -hw, ys, hd, -tw, y1, td, -tw, y1, -td],
    );
  }
  const position: number[] = [];
  for (const q of quads) {
    const v = (i: number): number[] => q.slice(i * 3, i * 3 + 3);
    position.push(...v(0), ...v(1), ...v(2), ...v(0), ...v(2), ...v(3));
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(new Float32Array(position), 3));
  // only the front face is mapped (for the label); everywhere else the uv says "no label here"
  const uv = new Float32Array((position.length / 3) * 2).fill(-1);
  uv.set([0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1], 6 * 2);
  geometry.setAttribute("uv", new BufferAttribute(uv, 2));
  geometry.computeVertexNormals();
  return geometry;
}

/** Add `aSmooth`: for every vertex, the mean of the normals of all vertices at the same place, so an inverted
 *  hull stays closed at hard edges. */
function addSmoothNormals(geometry: BufferGeometry): BufferGeometry {
  const position = geometry.getAttribute("position");
  const normal = geometry.getAttribute("normal");
  const sums = new Map<string, [number, number, number]>();
  const key = (i: number): string => `${Math.round(position.getX(i) * 100)},${Math.round(position.getY(i) * 100)},${Math.round(position.getZ(i) * 100)}`;
  const seen = new Map<string, Set<string>>();
  for (let i = 0; i < position.count; i++) {
    const k = key(i);
    const n: [number, number, number] = [normal.getX(i), normal.getY(i), normal.getZ(i)];
    // count each distinct face direction once, so a face split in two triangles does not weigh double
    const tag = n.map(x => Math.round(x * 50)).join(",");
    const had = seen.get(k) ?? new Set<string>();
    if (had.has(tag)) continue;
    had.add(tag);
    seen.set(k, had);
    const s = sums.get(k) ?? [0, 0, 0];
    s[0] += n[0];
    s[1] += n[1];
    s[2] += n[2];
    sums.set(k, s);
  }
  const smooth = new Float32Array(position.count * 3);
  for (let i = 0; i < position.count; i++) {
    const s = sums.get(key(i)) ?? [0, 1, 0];
    const l = Math.hypot(s[0], s[1], s[2]) || 1;
    // a corner where three faces meet is pushed out further, so the outline keeps its width along each face
    const stretch = Math.min(1.8, 1 / Math.max(0.55, l / (seen.get(key(i))?.size ?? 1)));
    smooth[i * 3] = (s[0] / l) * stretch;
    smooth[i * 3 + 1] = (s[1] / l) * stretch;
    smooth[i * 3 + 2] = (s[2] / l) * stretch;
  }
  geometry.setAttribute("aSmooth", new BufferAttribute(smooth, 3));
  return geometry;
}

/** The die's face as a texture, drawn here: the frame and the words in relief, mirrored as on a real die. */
function faceTexture(lines: readonly [string, string?]): CanvasTexture {
  const canvas = document.createElement("canvas");
  const k = 2;
  canvas.width = DIE.width * k;
  canvas.height = DIE.depth * k;
  const texture = new CanvasTexture(canvas);
  texture.minFilter = LinearFilter;
  texture.magFilter = LinearFilter;
  texture.generateMipmaps = false;
  const paint = (): void => {
    const g = canvas.getContext("2d");
    if (!g) return;
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.fillStyle = "#000";
    g.fillRect(0, 0, canvas.width, canvas.height);
    // mirrored: the die reads backwards
    g.setTransform(-k, 0, 0, k, DIE.width * k, 0);
    g.strokeStyle = "#fff";
    g.fillStyle = "#fff";
    g.lineWidth = 6.5;
    g.strokeRect(6.25, 6.25, DIE.width - 12.5, DIE.depth - 12.5);
    g.lineWidth = 2;
    g.strokeRect(15, 15, DIE.width - 30, DIE.depth - 30);
    g.textAlign = "center";
    const set = lines[1] ? MARK_TYPE.first : MARK_TYPE.alone;
    g.font = STAMP_FACE.replace("10px", `${set.size}px`);
    g.fillText(lines[0], DIE.width / 2, set.y, set.length);
    if (lines[1]) {
      g.font = STAMP_FACE.replace("10px", `${MARK_TYPE.second.size}px`);
      try {
        (g as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing = "2.4px";
      } catch {
        // an older canvas: the words sit closer
      }
      g.fillText(lines[1], DIE.width / 2 + 1.2, MARK_TYPE.second.y, MARK_TYPE.second.length);
      try {
        (g as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing = "0px";
      } catch {
        // nothing to undo
      }
    }
    texture.needsUpdate = true;
  };
  paint();
  texture.userData.paint = paint;
  return texture;
}

const STAMP_FACE = '800 10px "Big Shoulders Display", "Arial Narrow", sans-serif';

/** The paper label on the front of the mount, which says what the stamp stamps: red channel paper, green ink. */
function labelTexture(text: string): CanvasTexture {
  const canvas = document.createElement("canvas");
  const k = 4;
  const w = MOUNT.width;
  const h = MOUNT.height - MOUNT.bevel;
  canvas.width = w * k;
  canvas.height = h * k;
  const texture = new CanvasTexture(canvas);
  texture.minFilter = LinearFilter;
  texture.magFilter = LinearFilter;
  texture.generateMipmaps = false;
  const paint = (): void => {
    const g = canvas.getContext("2d");
    if (!g) return;
    g.setTransform(k, 0, 0, k, 0, 0);
    g.fillStyle = "#000";
    g.fillRect(0, 0, w, h);
    g.fillStyle = "#f00";
    g.fillRect(w * 0.2, h * 0.17, w * 0.6, h * 0.66);
    g.fillStyle = "#0f0";
    g.textAlign = "center";
    g.textBaseline = "alphabetic";
    g.font = STAMP_FACE.replace("10px", `${h * 0.46}px`);
    try {
      (g as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing = "1.6px";
    } catch {
      // an older canvas: the words sit closer
    }
    g.fillText(text, w / 2 + 0.8, h * 0.5 + h * 0.46 * 0.36, w * 0.55);
    texture.needsUpdate = true;
  };
  paint();
  texture.userData.paint = paint;
  return texture;
}

interface Palette {
  lit: RGB;
  shade: RGB;
  ink: RGB;
  detail: RGB;
  rubber: RGB;
  rubberShade: RGB;
  relief: RGB;
  shadow: RGB;
  shadowAlpha: number;
}

function readPalette(scope: Element): Palette {
  const alpha = Number(getComputedStyle(scope).getPropertyValue("--stamp-shadow-alpha")) || 0.3;
  return {
    lit: cssColor(scope, "var(--stamp-lit)"),
    shade: cssColor(scope, "var(--stamp-shade)"),
    ink: cssColor(scope, "var(--stamp-outline)"),
    detail: cssColor(scope, "var(--stamp-detail)"),
    rubber: cssColor(scope, "var(--stamp-rubber)"),
    rubberShade: cssColor(scope, "var(--stamp-rubber-shade)"),
    relief: cssColor(scope, "var(--stamp-relief)"),
    shadow: cssColor(scope, "var(--stamp-shadow)"),
    shadowAlpha: alpha,
  };
}

export interface Stamp3DOptions {
  tilt: number;
  lines?: readonly [string, string?];
  /** The graphics card took the WebGL context away: nothing more can be drawn here. */
  onLost?: () => void;
}

/** Build the three.js stamp. Throws if a WebGL context cannot be made. */
export function createStamp3D(scope: HTMLElement, options: Stamp3DOptions): StampRenderer {
  const yaw = (options.tilt * Math.PI) / 180;
  const root = document.createElement("div");
  root.className = "stamp-layer stamp3d";
  root.setAttribute("aria-hidden", "true");
  const canvas = document.createElement("canvas");
  canvas.className = "stamp3d__canvas";
  root.append(canvas);

  // a stencil buffer for the handle's outline; the default GPU (about 1,900 triangles do not need the fast one)
  const renderer = new WebGLRenderer({ canvas, alpha: true, antialias: true, premultipliedAlpha: true, stencil: true, powerPreference: "default" });
  // (no synchronous check of each shader's compile log outside the dev server: the slam's first frame waits on none)
  renderer.debug.checkShaderErrors = import.meta.env.DEV;
  let contextLost = false;
  canvas.addEventListener("webglcontextlost", event => {
    event.preventDefault();
    contextLost = true;
    options.onLost?.();
  });
  renderer.setClearColor(0x000000, 0);
  const pixelRatio = Math.min(window.devicePixelRatio || 1, lowPower() ? 1.5 : 2);
  renderer.setPixelRatio(pixelRatio);

  const scene = new Scene();
  const camera = new OrthographicCamera(-1, 1, 1, -1, -6000, 6000);

  let palette = readPalette(scope);
  const from: Palette = { ...palette };
  const to: Palette = { ...palette };
  let easing = 1; // 0 to 1 over the palette ease
  let easedAt = 0;

  const v3 = (c: RGB): { value: RGB } => ({ value: [...c] as RGB });
  const words = options.lines ?? (["APPROVED", "WITH CONDITIONS"] as const);
  const label = labelTexture(words.filter(Boolean).join(" "));
  const tone = (lit: RGB, shade: RGB, grooves: [number, number, number] = [0, 0, 0], labelled = false): ShaderMaterial =>
    new ShaderMaterial({
      vertexShader: TONE_VERTEX,
      fragmentShader: TONE_FRAGMENT,
      uniforms: {
        uLit: v3(lit),
        uShade: v3(shade),
        uInk: v3(palette.detail),
        uLight: { value: [...LIGHT] },
        uThreshold: { value: TONE_THRESHOLD },
        uGrooves: { value: grooves },
        uFine: { value: [MOUNT_TOP + GROOVES_FINE[0], MOUNT_TOP + GROOVES_FINE[1], MOUNT_TOP + GROOVES_FINE[2]] },
        uLabel: { value: label },
        uLabelled: { value: labelled ? 1 : 0 },
      },
      // the mount's faces sit a hair back, so its crease lines draw cleanly on top
      polygonOffset: labelled,
      polygonOffsetFactor: 1,
      polygonOffsetUnits: 1,
    });
  const wood = tone(palette.lit, palette.shade, [MOUNT_TOP + GROOVES[0], MOUNT_TOP + GROOVES[1], 1.1]);
  const block = tone(palette.lit, palette.shade, [0, 0, 0], true);
  const rubber = tone(palette.rubber, palette.rubberShade);
  const face = new ShaderMaterial({
    vertexShader: TONE_VERTEX,
    fragmentShader: FACE_FRAGMENT,
    uniforms: { uLit: v3(palette.rubber), uShade: v3(palette.relief), uMap: { value: faceTexture(words) } },
  });
  const hull = new ShaderMaterial({
    vertexShader: HULL_VERTEX,
    fragmentShader: HULL_FRAGMENT,
    uniforms: { uInk: v3(palette.ink), uWidth: { value: 1.6 }, uPull: { value: 0 } },
    side: BackSide,
  });
  // The handle is concave (a waist between the foot and the knob), and an inverted hull leaves gaps and stray
  // slivers there. Its outline is drawn another way: the handle itself marks the stencil where it shows; then an
  // expanded copy, pulled a hair toward the viewer, is inked wherever the handle is not. That is the handle's
  // silhouette against everything behind it (the mount's top included) and nothing inside it.
  wood.stencilWrite = true;
  wood.stencilFunc = AlwaysStencilFunc;
  wood.stencilRef = 1;
  wood.stencilZPass = ReplaceStencilOp;
  const rim = new ShaderMaterial({
    vertexShader: HULL_VERTEX,
    fragmentShader: HULL_FRAGMENT,
    uniforms: { uInk: v3(palette.ink), uWidth: { value: 1.6 }, uPull: { value: 3 } },
    stencilWrite: true,
    stencilFunc: NotEqualStencilFunc,
    stencilRef: 1,
    stencilFail: KeepStencilOp,
    stencilZFail: KeepStencilOp,
    stencilZPass: KeepStencilOp,
  });
  // flat ink and flat paper, for the screw heads on the mount's top
  const flat = (c: RGB): ShaderMaterial => new ShaderMaterial({ vertexShader: FLAT_VERTEX, fragmentShader: HULL_FRAGMENT, uniforms: { uInk: v3(c) } });
  const flatInk = flat(palette.detail);
  const flatLit = flat(palette.lit);
  const crease = new LineBasicMaterial({ color: 0xffffff });
  const shadowMaterial = new ShaderMaterial({
    vertexShader: SHADOW_VERTEX,
    fragmentShader: SHADOW_FRAGMENT,
    uniforms: { uColor: v3(palette.shadow), uAlpha: { value: 0.3 }, uSize: { value: [DIE.width, DIE.depth] }, uGap: { value: 4 }, uLine: { value: 1.5 } },
    transparent: true,
    depthWrite: false,
  });

  function applyPalette(p: Palette): void {
    const set = (m: ShaderMaterial, name: string, c: RGB): void => {
      const u = m.uniforms[name];
      if (u) u.value = c;
    };
    set(wood, "uLit", p.lit);
    set(wood, "uShade", p.shade);
    set(wood, "uInk", p.detail);
    set(block, "uLit", p.lit);
    set(block, "uShade", p.shade);
    set(block, "uInk", p.detail);
    set(rubber, "uLit", p.rubber);
    set(rubber, "uShade", p.rubberShade);
    set(face, "uLit", p.rubber);
    set(face, "uShade", p.relief);
    set(hull, "uInk", p.ink);
    set(rim, "uInk", p.ink);
    set(flatInk, "uInk", p.detail);
    set(flatLit, "uInk", p.lit);
    set(shadowMaterial, "uColor", p.shadow);
    crease.color.setRGB(p.detail[0], p.detail[1], p.detail[2]);
    palette = p;
  }
  // the crease colour is written as it should appear: no conversion on the way out
  crease.toneMapped = false;
  applyPalette(palette);

  // ---- the stamp: stage -> tilt (the view from above) -> lean -> yaw -> parts ---------------------------------
  const stage = new Group();
  const tilt = new Group();
  tilt.rotation.x = ELEVATION;
  const lean = new Group();
  lean.rotation.order = "ZXY";
  const body = new Group();
  body.rotation.y = -yaw;
  stage.add(tilt);
  tilt.add(lean);
  lean.add(body);
  scene.add(stage);

  const add = (geometry: BufferGeometry, material: ShaderMaterial, outline = true): void => {
    body.add(new Mesh(geometry, material));
    if (outline) body.add(new Mesh(addSmoothNormals(geometry), hull));
  };
  const dieGeometry = bevelBox(DIE.width, DIE.depth, 0, DIE.height, 0);
  add(dieGeometry, rubber);
  const mountGeometry = bevelBox(MOUNT.width, MOUNT.depth, DIE.height, MOUNT_TOP, MOUNT.bevel);
  add(mountGeometry, block);
  const lines = new LineSegments(new EdgesGeometry(mountGeometry, 20), crease);
  body.add(lines);
  const handleGeometry = new LatheGeometry(
    HANDLE.map(([r, y]) => new Vector2(Math.max(r, 0.001), MOUNT_TOP + y)),
    24,
  );
  // the handle first (it marks the stencil), then its rim where it is not
  const handleMesh = new Mesh(handleGeometry, wood);
  handleMesh.renderOrder = 1;
  const rimMesh = new Mesh(addSmoothNormals(handleGeometry), rim);
  rimMesh.renderOrder = 2;
  body.add(handleMesh, rimMesh);
  // two screw heads on the mount's top, either side of the handle: an ink ring, a paper face, a slot
  const screwRing = new RingGeometry(SCREWS.radius - 0.7, SCREWS.radius + 0.7, 20);
  screwRing.rotateX(-Math.PI / 2);
  const screwFace = new CircleGeometry(SCREWS.radius - 0.7, 20);
  screwFace.rotateX(-Math.PI / 2);
  const screwSlot = new PlaneGeometry(SCREWS.radius * 1.56, 1.3);
  screwSlot.rotateX(-Math.PI / 2);
  screwSlot.rotateY((-SCREWS.slot * Math.PI) / 180);
  for (const [sx, sz] of SCREWS.at) {
    for (const [geometry, material, lift] of [
      [screwFace, flatLit, 0.12],
      [screwRing, flatInk, 0.16],
      [screwSlot, flatInk, 0.2],
    ] as const) {
      const part = new Mesh(geometry, material);
      part.position.set(sx, MOUNT_TOP + lift, sz);
      body.add(part);
    }
  }
  // the inked face, seen only when the stamp lies on its back
  const faceGeometry = new PlaneGeometry(DIE.width, DIE.depth);
  faceGeometry.rotateX(Math.PI / 2);
  const faceMesh = new Mesh(faceGeometry, face);
  faceMesh.position.y = -0.05;
  body.add(faceMesh);

  const shadow = new Mesh(new PlaneGeometry(1, 1), shadowMaterial);
  shadow.renderOrder = -1;
  shadow.rotation.z = -Math.atan(Math.tan(yaw) * FORESHORTEN.depth);
  stage.add(shadow);

  // ---- the canvas: a box big enough for the stamp in any pose, moved to follow it -------------------------------
  let scale = 1;
  let stageW = 0;
  let stageH = 0;
  let boxW = 0;
  let boxH = 0;
  /** Where the ground point sits inside the box when the box is free to move. */
  let anchorX = 0;
  let anchorY = 0;
  let boxX = NaN;
  let boxY = NaN;
  let drawn = "";

  function resize(w: number, h: number, dieWidth: number): void {
    stageW = w;
    stageH = h;
    scale = dieWidth / DIE.width;
    stage.scale.setScalar(scale);
    const reach = (STAMP_HEIGHT * 0.72 + DIE.width * 0.5) * scale; // lying down, leaning, the shadow thrown aside
    const up = (STAMP_HEIGHT * FORESHORTEN.up + DIE.width * 0.42) * scale + 90;
    const down = (DIE.depth * 0.9 + 40) * scale + 30;
    boxW = Math.min(w, Math.ceil(reach * 2 + 80));
    boxH = Math.min(h, Math.ceil(up + down));
    anchorX = boxW / 2;
    anchorY = Math.min(boxH - down, up);
    renderer.setSize(boxW, boxH, false);
    canvas.style.width = `${boxW}px`;
    canvas.style.height = `${boxH}px`;
    const outline = Math.max(1.1, 1.7 * Math.min(1, scale + 0.15));
    hull.uniforms.uWidth!.value = outline;
    rim.uniforms.uWidth!.value = outline;
    drawn = "";
    boxX = NaN;
  }

  function draw(p: StampPose): void {
    // the box follows the ground point on whole device pixels, and stays inside the stage
    const snap = (v: number): number => Math.round(v * pixelRatio) / pixelRatio;
    const bx = snap(Math.max(0, Math.min(stageW - boxW, p.x - anchorX)));
    const by = snap(Math.max(0, Math.min(stageH - boxH, p.y - anchorY)));
    if (bx !== boxX || by !== boxY) {
      boxX = bx;
      boxY = by;
      canvas.style.transform = `translate3d(${bx}px, ${by}px, 0)`;
    }
    const gx = p.x - bx;
    const gy = p.y - by;
    if (contextLost) return;
    const key = `${gx.toFixed(2)},${gy.toFixed(2)},${p.h.toFixed(2)},${p.leanX.toFixed(4)},${p.leanZ.toFixed(4)},${p.squash.toFixed(4)},${p.lying.toFixed(4)},${p.alpha.toFixed(3)},${(p.zoom || 0).toFixed(4)},${easing.toFixed(3)}`;
    if (key === drawn) return;
    drawn = key;
    canvas.style.opacity = p.alpha >= 0.999 ? "" : String(p.alpha);

    camera.left = -gx;
    camera.right = boxW - gx;
    camera.top = gy;
    camera.bottom = gy - boxH;
    camera.updateProjectionMatrix();

    // lying on its back: turned a quarter away from the viewer, resting on the back of the mount
    const lie = p.lying;
    lean.rotation.z = -p.leanX;
    lean.rotation.x = p.leanZ - lie * (Math.PI / 2 + 0.02);
    lean.position.y = p.h / scale + lie * (MOUNT.depth / 2);
    lean.position.z = lie * (MOUNT_TOP * 0.5);
    const s = p.squash;
    body.scale.set(1 + s * 0.42, 1 - s, 1 + s * 0.42);
    // lifted clear of the page, it comes a little nearer the viewer
    tilt.scale.setScalar(1 + (p.zoom || 0));

    const hn = p.h / scale;
    // the higher the stamp, the further its shadow is thrown, the larger it is and the wider its hatching opens
    const grow = 1 + hn * 0.0012;
    const sw = (DIE.width + 10 + lie * 10) * grow;
    const sd = ((DIE.depth + 10) * FORESHORTEN.depth + lie * STAMP_HEIGHT * 0.34) * grow;
    shadow.scale.set(sw, sd, 1);
    // far behind everything, so the stamp always hides the part of its shadow it stands in front of
    shadow.position.set(hn * 0.34 + lie * 14, -hn * 0.2 + lie * STAMP_HEIGHT * 0.2, -3000);
    const size = shadowMaterial.uniforms.uSize!.value as number[];
    size[0] = sw;
    size[1] = sd;
    shadowMaterial.uniforms.uGap!.value = 3.6 + hn * 0.03;
    // (standing on something, it throws no shadow that can be seen: the die covers it)
    shadowMaterial.uniforms.uAlpha!.value = palette.shadowAlpha * (1 - Math.min(0.8, hn * 0.0036)) * (1 - lie * 0.3) * Math.min(1, hn / 10 + lie);
    renderer.render(scene, camera);
  }

  // the label and the die's face are lettered in the stamp face: paint them again once it has loaded
  let stale = false;
  try {
    // (a face that cannot be had leaves the fallback: not an error)
    document.fonts
      .load(STAMP_FACE, words.join(" "))
      .then(() => {
        (label.userData.paint as (() => void) | undefined)?.();
        const map = face.uniforms.uMap?.value as CanvasTexture | undefined;
        (map?.userData.paint as (() => void) | undefined)?.();
        stale = true;
        drawn = "";
      })
      .catch(() => {});
  } catch {
    // no Font Loading API: the fallback face stays
  }

  const mixRGB = (a: RGB, b: RGB, t: number): RGB => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];

  return {
    el: root,
    resize,
    draw(p) {
      if (easing < 1) {
        easing = Math.min(1, (performance.now() - easedAt) / 300);
        const t = easing * easing * (3 - 2 * easing);
        applyPalette({
          lit: mixRGB(from.lit, to.lit, t),
          shade: mixRGB(from.shade, to.shade, t),
          ink: mixRGB(from.ink, to.ink, t),
          detail: mixRGB(from.detail, to.detail, t),
          rubber: mixRGB(from.rubber, to.rubber, t),
          rubberShade: mixRGB(from.rubberShade, to.rubberShade, t),
          relief: mixRGB(from.relief, to.relief, t),
          shadow: mixRGB(from.shadow, to.shadow, t),
          shadowAlpha: from.shadowAlpha + (to.shadowAlpha - from.shadowAlpha) * t,
        });
      }
      draw(p);
    },
    setPalette() {
      Object.assign(from, palette);
      Object.assign(to, readPalette(scope));
      easing = 0;
      easedAt = performance.now();
    },
    busy: () => {
      const was = stale;
      stale = false;
      return easing < 1 || was;
    },
    destroy() {
      root.remove();
      for (const child of [...body.children, shadow]) {
        const mesh = child as Mesh | LineSegments;
        mesh.geometry.dispose();
      }
      for (const m of [wood, block, rubber, face, hull, rim, flatInk, flatLit, shadowMaterial, crease]) m.dispose();
      (face.uniforms.uMap?.value as CanvasTexture | undefined)?.dispose();
      label.dispose();
      renderer.dispose();
      // a context that is already lost cannot be lost again (three.js warns if asked)
      if (!contextLost) renderer.forceContextLoss();
    },
  };
}
