// The living grid: San Francisco's streets as one field of lines, the motions as points and stacks on it, one
// camera that something always owns (the gate, the story, the search), and the things that keep it alive (a slow
// drift, a ring every few seconds, a tilt toward the pointer, a dome under it). Loaded as a lazy chunk after the
// first paint: this is the only module of /c/ that needs three.js.

import { Vector3 } from "three";
import { createWorld, setPose, type Motions, type Pose, type Streets, type World } from "../core/world";
import { createLiving, createLivingLines, createLivingStreets, createStacks, type LivingLines } from "../core/world/living";
import { createCastle } from "../core/props/castle";
import { createCityHall } from "../core/props/cityhall";
import { getTheme } from "../core/theme";
import { createBlocks, type BlockSpec } from "./blocks";
import { CASTLE, CASTLE_LEVEL, CASTLE_ORIGIN, CASTLE_SCALE, CIVIC_GRID_DEG, HALL, HILL, HILL_GRID_DEG, hillAt, LETTER_ROWS, offset, RECORD, SEATS, SLABS } from "./places";
import { mixPose, type View } from "./poses";

export interface MotionInfo {
  record: string;
  year: number;
  n: number;
  x: number;
  z: number;
}

/** How much of each kind of life the scene has (0 to 1 each): set by whoever owns the camera. */
export interface Alive {
  drift: number;
  tilt: number;
  bulge: number;
  rings: number;
}

export interface Scene {
  world: World;
  /** The motions that have a place, in the stacks' order. */
  motions: MotionInfo[];
  /** The index of the story's own motion. */
  hero: number;
  /** The index of a motion by its case number, or -1. */
  indexOf(record: string): number;
  /** Height of the ground at a point, in metres (the hill as it has risen). */
  heightAt(x: number, z: number): number;
  resize(view: View): void;
  /** Where the camera should be. With `blend` (seconds) it eases there from where it is; without, it is there. */
  setTarget(pose: Pose, blend?: number): void;
  setAlive(alive: Partial<Alive>): void;
  /** The pointer, in CSS pixels of the window; null when there is none (it left, a finger lifted). `free` is
   *  false when it is over something opaque: the map does not answer then. */
  setPointer(x: number | null, y?: number, free?: boolean): void;
  /** Called after every frame that is drawn, with the camera where it now is. Returns the remover. */
  onRender(cb: () => void): () => void;
  project(x: number, y: number, z: number, out: { x: number; y: number; behind: boolean }): { x: number; y: number; behind: boolean };
  /** The ground point under a pixel of the window, or null. */
  groundAt(px: number, py: number): { x: number; z: number } | null;
  /** Where the camera is now (its resting pose with the drift and tilt added). */
  pose: Pose;
  /** Metres per line of a stack at this zoom. */
  readonly perLine: number;
  /** Metres per CSS pixel across the view at the point looked at. */
  readonly metresPerPixel: number;
  /** The motion whose point or stack is under a pixel, or -1. The one answer to "which motion is this": the label
   *  under the pointer, the hand cursor and a click all ask here. */
  pick(px: number, py: number, reach?: number): number;
  /** Where the top of a motion's stack (its dot) is on the screen. */
  topOf(index: number, out: { x: number; y: number; behind: boolean }): { x: number; y: number; behind: boolean };
  /** The streets draw on outward from the castle (about 1.5 s); `false` shows them complete. */
  intro(play: boolean): void;
  /** A press building over a ground point: 0 nothing, 1 full. The dome turns into a dent there, `radius` metres
   *  wide at full pressure (the thing being pressed covers the middle of it). */
  dent(amount: number, x?: number, z?: number, radius?: number): void;
  /** How many times its usual width the dome under the pointer is (the gate: the stamp hangs over the middle). */
  setDome(scale: number): void;
  /** How far the living ground is lifted at a point now, in metres (the dome, the dent, the rings). */
  liftAt(x: number, z: number): number;
  /** A ring through the whole city from a point (power 1: the slam). */
  ring(x: number, z: number, power?: number): void;
  /** Jolt the view (the slam): pixels per second, down. */
  kick(velocity: number): void;
  /** Hit-stop: nothing moves for this long. */
  freeze(ms: number): void;
  /** The story's motion turns to the stamp's colour (the only red point on the map), and keeps a slow pulse. */
  setHero(red: boolean, options?: { instant?: boolean; pulse?: boolean }): void;
  /** The motions a search matches, or null for "no search": matching stacks stand and light, the rest sink. */
  setLit(records: ReadonlySet<string> | null): void;
  /** Raise and light one motion's stack (a card under the pointer), or none. */
  hover(index: number): void;
  /** The stacks rise in a wave from Telegraph Hill outward: 0 none, 1 all. With `seconds` it eases there. */
  setWave(amount: number, seconds?: number): void;
  // ---- the story's own drawing: each a function of the scroll ----
  setHill(amount: number): void;
  setSpot(amount: number): void;
  setDim(amount: number): void;
  /** The route line along real streets: give it once, then draw 0 to 1 of it. */
  setRoute(points: Float32Array | null, draw?: number): void;
  /** The story's own conditions as a stack of slabs standing by the address: how far it has risen (0 to 1), and
   *  one slab picked out (its index from the bottom, amount 0 to 1). */
  setSlabs(grow: number, line: number, lineAmount: number): void;
  /** Where slab `i` (0 at the bottom) of that stack is: the middle of its end, as a world point. */
  heroLine(i: number): { x: number; y: number; z: number };
  /** The head of the story's own pin (or the top of its stack), as a world point. */
  heroTop(out: { x: number; y: number; z: number }): { x: number; y: number; z: number };
  /** The drawn castle at the address: how far it has come onto the map (0 to 1) and how far it has folded up. */
  setCastle(onMap: number, fold: number): void;
  /** The drawn hall at the end of the route, the same way. */
  setHall(onMap: number, fold: number): void;
  /** The letters: how many cards stand in each of the two rows (a fraction stands the next part of the way). */
  setLetters(support: number, opposition: number): void;
  /** The seven seats: how many stand, and how many of them are filled (have voted). */
  setSeats(standing: number, voted: number): void;
  /** 0: the light of the hill; 1: the light of the hall (each lights its own drawing's front). */
  setLight(civic: number): void;
  /** In the search: no ring runs of itself; one leaves from the matching motions whenever the results change. */
  setSearch(on: boolean): void;
  /** Hold every motion of the map's own still (the visitor paused it, or the system asks for less motion): no
   *  drift, ring, lean, dome or pulse; what the visitor does (the stamp, a search) still shows. */
  setStill(still: boolean): void;
  /** Left alone a long while (no move, key, scroll or touch): the drift and the rings rest, and the loop with them,
   *  until the visitor is back. The lean and the dome still answer the pointer. */
  setResting(resting: boolean): void;
  setTheme(instant?: boolean): void;
  /** Draw a frame now (the flip takes its picture straight after the theme has changed). */
  renderNow(): void;
  /** Whether anything shows the map (frames are skipped when it is covered or off screen). */
  setVisible(visible: boolean): void;
  dispose(): void;
}

export interface SceneOptions {
  canvas: HTMLCanvasElement;
  streets: Streets;
  motions: Motions;
  view: View;
  reduced: boolean;
}

const TAU = Math.PI * 2;
const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));
const smooth = (k: number): number => k * k * (3 - 2 * k);
/** Move `current` toward `target` with a time constant (seconds): the same lag at any frame rate. */
const follow = (current: number, target: number, dt: number, tau: number): number => current + (target - current) * (1 - Math.exp(-dt / tau));

export function createScene(options: SceneOptions): Scene {
  const { canvas, streets } = options;
  /** The system asks for less motion (it can change while the page is open: setStill). */
  let reduced = options.reduced;
  let view = options.view;
  const world = createWorld(canvas, { relief: [HILL] });
  world.setSize(view.w, view.h);
  const living = createLiving(world);

  // ---- the city ----------------------------------------------------------------------------------------------------
  // (lines test depth, so a drawn object hides the streets behind it; they never write it)
  const lines = createLivingStreets(world, living, streets, { depthTest: true });
  world.scene.add(lines.mesh);

  // ---- the motions ------------------------------------------------------------------------------------------------
  const motions: MotionInfo[] = [];
  for (const p of options.motions.points) {
    const gx = p.sx ?? p.x, gy = p.sy ?? p.y;
    if (gx === null || gy === null) continue;
    motions.push({ record: p.record, year: p.year, n: p.n, x: gx, z: -gy });
  }
  const hero = motions.findIndex(m => m.record === RECORD);
  const byRecord = new Map(motions.map((m, i) => [m.record, i]));
  if (hero >= 0) {
    // the story's motion stands on the castle's own point
    motions[hero]!.x = CASTLE.x;
    motions[hero]!.z = CASTLE.z;
  }
  let far = 1;
  for (const m of motions) far = Math.max(far, Math.hypot(m.x - CASTLE.x, m.z - CASTLE.z));
  const stacks = createStacks(world, living, motions.map(m => ({ x: m.x, z: m.z, n: m.n, order: Math.hypot(m.x - CASTLE.x, m.z - CASTLE.z) / far })), { depthTest: true });
  stacks.setWave(0, 0);
  if (hero >= 0) stacks.setHero(hero, { width: 4, perLine: 32, red: 0, pin: 0 });
  world.scene.add(stacks.mesh, stacks.dots);

  let route: LivingLines | null = null;
  let routeDrawn = 0;

  // ---- the drawn objects of the story: made when the story first asks for them, hidden whenever it does not -------
  const RAD = Math.PI / 180;
  const HILL_LIGHT = new Vector3(-0.36, 0.72, 0.5).normalize();
  const CIVIC_LIGHT = new Vector3(0.36, 0.7, 0.58).normalize();
  world.uniforms.uLight.value.copy(HILL_LIGHT);
  let relief = 0;
  type Prop = { group: { visible: boolean; position: { y: number; set(x: number, y: number, z: number): void }; rotation: { y: number }; scale: { setScalar(s: number): void } }; fold(amount: number): void; setBase(y: number): void };
  let castle: Prop | null = null;
  let hall: Prop | null = null;
  let castleOn = 0, castleFold = 0, hallOn = 0, hallFold = 0;
  const placeCastle = (): void => {
    if (!castle) return;
    const on = castleOn > 0.001;
    if (castle.group.visible !== on) {
      castle.group.visible = on;
      world.invalidate();
    }
    if (!on) return;
    castle.group.scale.setScalar(Math.max(0.001, castleOn) * CASTLE_SCALE);
    castle.group.position.y = CASTLE_LEVEL * relief;
    castle.setBase(castle.group.position.y);
    castle.fold(castleFold);
    world.invalidate();
  };
  const placeHall = (): void => {
    if (!hall) return;
    const on = hallOn > 0.001;
    if (hall.group.visible !== on) {
      hall.group.visible = on;
      world.invalidate();
    }
    if (!on) return;
    hall.group.scale.setScalar(Math.max(0.001, hallOn));
    hall.fold(hallFold);
    world.invalidate();
  };

  // the 22 conditions: slabs standing in a stack by the address
  const heroN = hero >= 0 ? motions[hero]!.n : 22;
  const slabs = createBlocks(world, Array.from({ length: heroN }, (_, i): BlockSpec => ({ x: 0, y: i * SLABS.pitch, z: 0, w: SLABS.w, h: SLABS.thick, d: SLABS.d })), { edge: 0.75 });
  slabs.mesh.position.set(SLABS.at.x, 0, SLABS.at.z);
  slabs.mesh.rotation.y = HILL_GRID_DEG * RAD;
  slabs.mesh.visible = false;
  slabs.setGrow(0);
  world.scene.add(slabs.mesh);
  const slabLevel = hillAt(SLABS.at);

  // the letters: two rows of cards along the street; each stands on the ground where it is
  const cards = (from: { x: number; z: number }, count: number, kind: 0 | 1): BlockSpec[] =>
    Array.from({ length: count }, (_, i) => {
      const at = offset(from, HILL_GRID_DEG, i * LETTER_ROWS.gap, 0);
      return { x: at.x, y: hillAt(at), z: at.z, ...LETTER_ROWS.card, yaw: HILL_GRID_DEG * RAD, kind };
    });
  let lettersFor: [number, number] = [0, 0];
  let support: ReturnType<typeof createBlocks> | null = null;
  let opposition: ReturnType<typeof createBlocks> | null = null;
  // the seven seats
  const seats = createBlocks(world, SEATS.map((at): BlockSpec => ({ x: at.x, y: 0, z: at.z, w: 6, h: 9, d: 6, yaw: CIVIC_GRID_DEG * RAD })), { edge: 0.8 });
  seats.mesh.visible = false;
  seats.setRise(0);
  world.scene.add(seats.mesh);

  // ---- the camera ----------------------------------------------------------------------------------------------------
  const target: Pose = { tx: 0, ty: 0, tz: 0, distance: 20000, heading: 0, pitch: 50, fov: 30, shiftX: 0, shiftY: 0 };
  const from: Pose = { ...target };
  const base: Pose = { ...target };
  const shown: Pose = { ...target };
  const applied: Pose = { ...target, distance: -1 };
  let blendStart = -1, blendLength = 0;
  const alive: Alive = { drift: 0, tilt: 0, bulge: 0, rings: 0 };
  const aliveGoal: Alive = { drift: 0, tilt: 0, bulge: 0, rings: 0 };
  /** What the owner of the camera asked for; the goal is that, or nothing while the map is held still. */
  const asked: Alive = { drift: 0, tilt: 0, bulge: 0, rings: 0 };
  let resting = false;
  const aimAlive = (): void => {
    for (const k of ["drift", "tilt", "bulge", "rings"] as const) aliveGoal[k] = reduced || (resting && (k === "drift" || k === "rings")) ? 0 : asked[k];
    wake();
  };

  // ---- the pointer -------------------------------------------------------------------------------------------------
  let hasPointer = false, pointerFree = true;
  let px = 0, py = 0;
  let movedAt = -10;
  let gx = CASTLE.x, gz = CASTLE.z;
  let groundKnown = false;
  /** The dome has caught up with the ground under the pointer. */
  let groundSettled = true;
  let tiltH = 0, tiltP = 0;
  let dome = 0;
  let dentAmount = 0, dentX = CASTLE.x, dentZ = CASTLE.z, dentRadius = 1500;
  let domeScale = 1, domeScaleGoal = 1;
  /** The pointer moved since the page was last told: what is tied to it is placed again even when no frame is drawn. */
  let pointerNews = false;
  /** In the search no ring runs of itself; one leaves from the matches when the results change. */
  let searching = false;

  // ---- time --------------------------------------------------------------------------------------------------------
  let t = 0;
  let last = 0;
  let raf = 0;
  let parity = false;
  let visible = true;
  let frozenUntil = 0;
  let disposed = false;
  /** Seconds until which something time-based is running and frames are wanted at full rate. */
  let busyUntil = 0;
  /** The loop sleeps once nothing has moved for a few frames (a map at rest asks for no frames at all); anything
   *  that changes what is drawn wakes it. */
  let asleep = false;
  let restFrames = 0;
  const wake = (): void => {
    restFrames = 0;
    if (!asleep || disposed) return;
    asleep = false;
    last = 0;
    raf = requestAnimationFrame(frame);
  };
  const busy = (seconds: number): void => {
    busyUntil = Math.max(busyUntil, t + seconds);
    wake();
  };

  // rings: 0 is the idle ring, 1 the slam
  const idle = { on: false, t0: 0, x: 0, z: 0, power: 1 };
  const slam = { on: false, t0: 0, x: 0, z: 0, power: 1 };
  let nextRing = 2.4;
  let ringTurn = 0;
  // the view's jolt: a spring on the picture's vertical place
  let kickY = 0, kickV = 0;
  // the hero's colour and pulse
  let red = 0, redGoal = 0, pulse = false, pulseStart = 0;
  // the streets draw on
  let revealStart = -1;
  const REVEAL_S = 1.6, REVEAL_R = 19500;
  // the wave, when it is run by the clock
  let wave = 0, waveFrom = 0, waveTo = 0, waveStart = -1, waveLength = 0;
  /** The wave as last given to the stacks, and what the hero's own stack (its pin) was given. */
  let pinSent = -1;
  let ringSent = 0;
  // the search's state, applied at the next frame
  let pendingLit: ReadonlySet<string> | null | undefined;
  let lit: ReadonlySet<string> | null = null;
  const growGoal = new Float32Array(motions.length).fill(1);
  const toneGoal = new Float32Array(motions.length);
  let hovered = -1;

  const listeners = new Set<() => void>();
  const tmp = { x: 0, y: 0, behind: false };
  const tmp2 = { x: 0, y: 0, behind: false };

  // ---- the theme: line strength is tuned for each ground, not inverted ------------------------------------------------
  let dim = 0;
  let spotAmount = -1;
  /** 0 from far away (the whole city), 1 close to the ground: lines and points are drawn heavier close up. */
  let nearness = 0;
  const applyTheme = (): void => {
    const dark = getTheme() === "blueprint";
    const k = nearness;
    lines.setOpacities((dark ? 0.2 : 0.21) + k * 0.2, (dark ? 0.5 : 0.52) + k * 0.25);
    lines.setWidths((dark ? 0.9 : 0.85) + k * 0.45, (dark ? 1.4 : 1.35) + k * 0.9);
    lines.setGlow(dark ? 0.62 : 0.55, 0.7);
    stacks.setSizes(4, 6.5, (dark ? 3.6 : 3.8) + k * 3.4, 6.5 + k * 3);
  };
  applyTheme();

  const sigmaOf = (): number => clamp(shown.distance * 0.027, 45, 1600);
  /** Metres per CSS pixel across the view at the point looked at. */
  const mppOf = (): number => (2 * shown.distance * Math.tan((shown.fov * Math.PI) / 360)) / Math.max(1, view.h);
  /** The story's motion is a pin: a thin line in the stamp's colour, taller than the stacks round it, the point
   *  at its head. Before it is stamped it is a point like the others. */
  const heroSet = { red: 0, pin: 0, width: 4, perLine: 32 };
  const applyHero = (): void => {
    if (hero < 0) return;
    const pinMetres = Math.max(66, 104 * mppOf());
    const per = perLineOf();
    heroSet.red = red;
    heroSet.pin = red;
    heroSet.width = 4 + (1.7 - 4) * red;
    heroSet.perLine = per + (pinMetres / heroN - per) * red;
    stacks.setHero(hero, heroSet);
    // (its own rise: with the wave like the others until it is stamped, then the pin's)
    const own = Math.max(red, Math.min(1, wave * 6));
    if (own !== pinSent) {
      pinSent = own;
      stacks.setWave(wave, own);
    }
  };
  /** Metres per line of a stack: more from far away, so a stack is about as tall on the screen at any zoom. */
  const perLineOf = (): number => clamp(shown.distance * 0.0015, 3, 90);

  const startRing = (): void => {
    // a different motion each time, from those in the window
    for (let tries = 0; tries < 12; tries++) {
      ringTurn = (ringTurn * 73 + 41) % motions.length;
      const m = motions[ringTurn]!;
      world.toScreen(m.x, 0, m.z, tmp);
      if (!tmp.behind && tmp.x > view.w * 0.08 && tmp.x < view.w * 0.92 && tmp.y > view.h * 0.12 && tmp.y < view.h * 0.9) {
        idle.on = true;
        idle.t0 = t;
        idle.x = m.x;
        idle.z = m.z;
        idle.power = alive.rings;
        return;
      }
    }
  };

  /** Where every stack is going: the search's matches stand and light, the rest sink; while a card is under the
   *  pointer its stack is drawn at full strength and the other matches step down. */
  const aimStacks = (): void => {
    for (let i = 0; i < motions.length; i++) {
      const match = !lit || lit.has(motions[i]!.record);
      growGoal[i] = match ? 1 : 0.1;
      toneGoal[i] = !lit ? (hovered >= 0 ? -0.55 : 0) : match ? (hovered >= 0 ? -0.3 : 0.75) : -1;
    }
    if (hovered >= 0) {
      growGoal[hovered] = 1.3;
      toneGoal[hovered] = 1;
    }
  };
  const applyLit = (records: ReadonlySet<string> | null): void => {
    const changed = records !== lit;
    lit = records;
    aimStacks();
    const end = stacks.setTargets(growGoal, toneGoal, { duration: reduced ? 0.01 : 0.38 });
    busy(end - t + 0.05);
    // in the search: one ring from the middle of the matches says where they are, and then the map rests
    if (searching && changed && records && records.size > 0 && !reduced) {
      let sx = 0, sz = 0, k = 0;
      for (const m of motions) {
        if (!records.has(m.record)) continue;
        sx += m.x;
        sz += m.z;
        k += 1;
      }
      if (k > 0) {
        idle.on = true;
        idle.t0 = t;
        idle.x = sx / k;
        idle.z = sz / k;
        idle.power = 1;
      }
    }
  };

  const frame = (now: number): void => {
    if (disposed) return;
    raf = 0;
    // nothing shows the map (it is covered or off screen, or the tab is hidden): no frames until it shows again
    if (!visible || document.hidden) {
      asleep = true;
      return;
    }
    raf = requestAnimationFrame(frame);
    if (!last) last = now;
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    if (now < frozenUntil) return;

    // what only drifts may run at half rate; anything else wants every frame
    const settling = blendStart >= 0 || t < busyUntil || slam.on || idle.on && searching || kickY !== 0 || kickV !== 0 || revealStart >= 0 || waveStart >= 0 || t - movedAt < 0.9 || dentAmount > 0;
    parity = !parity;
    if (!settling && parity && !pendingLit) {
      t += dt;
      return;
    }
    t += dt;
    living.uniforms.uTime.value = t;

    // how alive: ease toward what the owner asked for
    alive.drift = follow(alive.drift, aliveGoal.drift, dt, 0.6);
    alive.tilt = follow(alive.tilt, aliveGoal.tilt, dt, 0.4);
    alive.bulge = follow(alive.bulge, aliveGoal.bulge, dt, 0.3);
    if (Math.abs(alive.drift - aliveGoal.drift) < 0.01) alive.drift = aliveGoal.drift;
    if (Math.abs(alive.tilt - aliveGoal.tilt) < 0.01) alive.tilt = aliveGoal.tilt;
    if (Math.abs(alive.bulge - aliveGoal.bulge) < 1e-3) alive.bulge = aliveGoal.bulge;
    alive.rings = aliveGoal.rings;

    // ---- the camera: where it rests, then the drift, the tilt toward the pointer, the jolt --------------------
    if (blendStart >= 0) {
      const k = clamp((t - blendStart) / blendLength, 0, 1);
      mixPose(from, target, k < 0.5 ? 4 * k * k * k : 1 - (-2 * k + 2) ** 3 / 2, base);
      if (k >= 1) blendStart = -1;
    } else mixPose(target, target, 1, base);
    // (a pointer over a panel of text is not pointing at the map: the view does not lean toward it)
    const leaning = hasPointer && pointerFree;
    const nx = leaning ? clamp((px / view.w) * 2 - 1, -1, 1) : 0;
    const ny = leaning ? clamp((py / view.h) * 2 - 1, -1, 1) : 0;
    const frozenTilt = dentAmount > 0;
    if (!frozenTilt) {
      tiltH = follow(tiltH, -nx * 2.6 * alive.tilt, dt, 0.25);
      tiltP = follow(tiltP, ny * 1.5 * alive.tilt, dt, 0.25);
      // (a lag that has run out stops: a view at rest is not drawn again)
      // (a few thousandths of a degree is less than a pixel's move anywhere on the screen)
      if (Math.abs(tiltH + nx * 2.6 * alive.tilt) < 3e-3) tiltH = -nx * 2.6 * alive.tilt;
      if (Math.abs(tiltP - ny * 1.5 * alive.tilt) < 3e-3) tiltP = ny * 1.5 * alive.tilt;
    }
    if (alive.drift < 0.002 && aliveGoal.drift === 0) alive.drift = 0;
    if (alive.tilt < 0.002 && aliveGoal.tilt === 0) alive.tilt = 0;
    const driftH = alive.drift * 2.3 * Math.sin((t * TAU) / 61);
    const driftP = alive.drift * 0.7 * Math.sin((t * TAU) / 43 + 1.1);
    if (kickY !== 0 || kickV !== 0) {
      // stiffness 520, damping 16: gone in about 400 ms
      kickV += (-520 * kickY - 16 * kickV) * dt;
      kickY += kickV * dt;
      if (Math.abs(kickY) < 0.05 && Math.abs(kickV) < 2) kickY = kickV = 0;
    }
    mixPose(base, base, 1, shown);
    shown.heading += driftH + tiltH;
    shown.pitch += driftP + tiltP;
    shown.shiftY += kickY / view.h;
    if (
      shown.tx !== applied.tx || shown.tz !== applied.tz || shown.ty !== applied.ty || shown.distance !== applied.distance ||
      Math.abs(shown.heading - applied.heading) > 1e-4 || Math.abs(shown.pitch - applied.pitch) > 1e-4 || shown.fov !== applied.fov ||
      shown.shiftX !== applied.shiftX || shown.shiftY !== applied.shiftY
    ) {
      setPose(world, shown);
      mixPose(shown, shown, 1, applied);
      // stacks float a little above the ground: more from far away, so the points slide against the lines
      stacks.setScale(perLineOf(), clamp(shown.distance * 0.0022, 3, 46));
      applyHero();
      lines.setFade(shown.distance * 1.05, shown.distance * 2.5);
      const k = 1 - smooth(clamp((shown.distance - 1200) / 9000, 0, 1));
      if (Math.abs(k - nearness) > 0.004) {
        nearness = k;
        applyTheme();
      }
      world.invalidate();
    }

    // ---- the pointer on the ground: the dome follows it with a short lag ----------------------------------------
    domeScale = follow(domeScale, domeScaleGoal, dt, 0.35);
    // (a lag that has all but arrived has arrived: a scene at rest is not drawn again)
    if (Math.abs(domeScale - domeScaleGoal) < 1e-3) domeScale = domeScaleGoal;
    const sigma = sigmaOf() * domeScale;
    if (dentAmount > 0) {
      // the weight comes down: the ground sinks under it, wider and deeper as the press builds, and the lines
      // round it draw tight
      const s = sigma + (Math.max(sigma, dentRadius) - sigma) * Math.min(1, dentAmount * 1.6);
      living.setPointer(dentX, dentZ, s);
      living.setBulge(-s * 0.2 * dentAmount, 0.25 + 0.6 * dentAmount);
      dome = 0;
      gx = dentX;
      gz = dentZ;
    } else {
      const want = hasPointer && pointerFree && alive.bulge > 0.01;
      groundSettled = true;
      if (want) {
        const g = world.groundAt(px, py);
        if (g) {
          if (!groundKnown) {
            gx = g.x;
            gz = g.z;
            groundKnown = true;
          }
          gx = follow(gx, g.x, dt, 0.075);
          gz = follow(gz, g.z, dt, 0.075);
          if (Math.abs(gx - g.x) < 0.05 * mppOf() && Math.abs(gz - g.z) < 0.05 * mppOf()) {
            gx = g.x;
            gz = g.z;
          } else groundSettled = false;
        }
      }
      const domeGoal = want ? alive.bulge : 0;
      dome = follow(dome, domeGoal, dt, want ? 0.12 : 0.3);
      if (Math.abs(dome - domeGoal) < 0.002) dome = domeGoal;
      living.setPointer(gx, gz, sigma);
      living.setBulge((sigma * 0.46 * dome) / Math.sqrt(domeScale), 0.7 * dome);
    }

    // ---- rings -----------------------------------------------------------------------------------------------------
    if (alive.rings > 0 && !idle.on && t >= nextRing && !slam.on) {
      startRing();
      nextRing = t + 5.2;
    }
    if (idle.on) {
      const k = (t - idle.t0) / 3.4;
      if (k >= 1) {
        idle.on = false;
        living.setRing(0, 0, 0, -1e6, 0, 300, 0);
      } else {
        const d = shown.distance;
        const e = 1 - (1 - k) ** 2;
        living.setRing(0, idle.x, idle.z, d * 0.21 * e, d * 0.0135 * (1 - k) ** 1.2 * Math.min(1, k * 9) * idle.power, d * 0.02, 0.8 * (1 - k) ** 0.8 * idle.power);
      }
    }
    if (slam.on) {
      const length = 2.7;
      const k = (t - slam.t0) / length;
      if (k >= 1) {
        slam.on = false;
        living.setRing(1, 0, 0, -1e6, 0, 300, 0);
      } else {
        const d = Math.max(shown.distance, 6000);
        const e = 1 - (1 - k) ** 2.4;
        living.setRing(1, slam.x, slam.z, 21000 * e * (0.4 + 0.6 * slam.power), d * 0.03 * slam.power * (1 - k) ** 1.25, d * 0.03, Math.min(1, slam.power) * (1 - k) ** 0.8);
      }
    }

    // ---- the hero's colour and pulse ---------------------------------------------------------------------------------
    if (red !== redGoal) {
      red = follow(red, redGoal, dt, 0.12);
      if (Math.abs(red - redGoal) < 0.01) red = redGoal;
    }
    if (hero >= 0) {
      // the slow pulse belongs to the living views: where the rings rest (a chapter's close view, the search), so does it
      let ring = 0;
      if (pulse && red > 0.5 && !reduced && alive.rings > 0) {
        const phase = ((t - pulseStart) % 2.9) / 1.2;
        ring = phase < 1 ? Math.max(0.002, 1 - (1 - phase) ** 2) : 0;
      }
      if (ring !== ringSent) {
        ringSent = ring;
        stacks.setHero(hero, { ring });
      }
      if (red !== heroSet.red) applyHero();
    }

    // ---- the streets drawing on -------------------------------------------------------------------------------------------
    if (revealStart >= 0) {
      const k = clamp((t - revealStart) / REVEAL_S, 0, 1);
      const e = 1 - (1 - k) ** 2.2;
      if (k >= 1) {
        revealStart = -1;
        lines.setReveal(CASTLE.x, CASTLE.z, Infinity);
        stacks.setOpacity(1);
      } else {
        lines.setReveal(CASTLE.x, CASTLE.z, 400 + REVEAL_R * e, 1400);
        stacks.setOpacity(smooth(clamp(k * 1.5 - 0.3, 0, 1)));
      }
    }

    // ---- the wave on the clock -----------------------------------------------------------------------------------------------
    if (waveStart >= 0) {
      const k = clamp((t - waveStart) / waveLength, 0, 1);
      wave = waveFrom + (waveTo - waveFrom) * smooth(k);
      if (k >= 1) waveStart = -1;
      pinSent = -1;
      applyHero();
    }

    if (pendingLit !== undefined) {
      applyLit(pendingLit);
      pendingLit = undefined;
    }

    const drew = world.update(now);
    if (drew) {
      world.render();
      pointerNews = false;
      for (const cb of listeners) cb();
    } else if (pointerNews) {
      // nothing to draw, but the pointer is somewhere else: what is tied to it (the readout, the label) follows
      pointerNews = false;
      for (const cb of listeners) cb();
    }

    // ---- at rest? Nothing on the clock, every lag arrived, nothing alive: the loop sleeps until it is woken ---------
    const lagging =
      alive.drift !== aliveGoal.drift || alive.tilt !== aliveGoal.tilt || alive.bulge !== aliveGoal.bulge || alive.drift > 0 || alive.rings > 0 ||
      tiltH !== -nx * 2.6 * alive.tilt || tiltP !== ny * 1.5 * alive.tilt || dome !== (hasPointer && pointerFree && alive.bulge > 0.01 ? alive.bulge : 0) ||
      domeScale !== domeScaleGoal || red !== redGoal;
    const following = hasPointer && pointerFree && alive.bulge > 0.01 && dentAmount <= 0 && !groundSettled;
    if (settling || lagging || following || idle.on || slam.on || pendingLit !== undefined || drew || pointerNews) restFrames = 0;
    else if (++restFrames > 8) {
      asleep = true;
      cancelAnimationFrame(raf);
      raf = 0;
    }
  };

  const scene: Scene = {
    world,
    motions,
    hero,
    indexOf: record => byRecord.get(record) ?? -1,
    heightAt: (x, z) => world.heightAt(x, z),
    pose: shown,
    get perLine() {
      return perLineOf();
    },
    get metresPerPixel() {
      return mppOf();
    },
    resize(next) {
      wake();
      view = next;
      world.setSize(view.w, view.h);
      applied.distance = -1;
    },
    setTarget(pose, blend = 0) {
      wake();
      if (blend > 0 && !reduced) {
        mixPose(base, base, 1, from);
        blendStart = t;
        blendLength = blend;
      }
      // a camera that is being moved (a scroll, a key) is drawn at every frame, not at the idle rate
      if (
        pose.tx !== target.tx || pose.tz !== target.tz || pose.ty !== target.ty || pose.distance !== target.distance || pose.heading !== target.heading ||
        pose.pitch !== target.pitch || pose.shiftX !== target.shiftX || pose.shiftY !== target.shiftY || pose.fov !== target.fov
      ) busy(0.25);
      mixPose(pose, pose, 1, target);
    },
    setAlive(next) {
      Object.assign(asked, next);
      aimAlive();
    },
    setPointer(x, y = 0, free = true) {
      wake();
      if (x === null) {
        hasPointer = false;
        groundKnown = false;
      } else {
        hasPointer = true;
        px = x;
        py = y;
        pointerFree = free;
      }
      pointerNews = true;
      movedAt = t;
    },
    onRender(cb) {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    project: (x, y, z, out) => world.toScreen(x, y, z, out),
    groundAt: (x, y) => world.groundAt(x, y),
    pick(x, y, reach = 14) {
      let best = -1;
      let bestD = reach + 30;
      const lift = clamp(shown.distance * 0.0022, 3, 46);
      for (let i = 0; i < motions.length; i++) {
        const m = motions[i]!;
        const ground = world.heightAt(m.x, m.z) + living.liftAt(m.x, m.z) + lift;
        world.toScreen(m.x, ground, m.z, tmp);
        if (tmp.behind) continue;
        world.toScreen(m.x, ground + stacks.heightOf(i), m.z, tmp2);
        // distance from the pixel to the stack's line on the screen
        const vx = tmp2.x - tmp.x, vy = tmp2.y - tmp.y;
        const l2 = vx * vx + vy * vy;
        const k = l2 > 0 ? clamp(((x - tmp.x) * vx + (y - tmp.y) * vy) / l2, 0, 1) : 0;
        const d = Math.hypot(x - (tmp.x + vx * k), y - (tmp.y + vy * k));
        if (d > reach) continue;
        // held-back stacks are harder to hit than standing ones; where several cross under the pointer, the one
        // whose point (its top) is nearest wins
        const handicap = (stacks.toneOf(i) < -0.5 ? 5 : 0) + Math.hypot(x - tmp2.x, y - tmp2.y) * 0.05;
        if (d + handicap < bestD) {
          bestD = d + handicap;
          best = i;
        }
      }
      return best;
    },
    topOf(i, out) {
      const m = motions[i]!;
      const lift = clamp(shown.distance * 0.0022, 3, 46);
      return world.toScreen(m.x, world.heightAt(m.x, m.z) + living.liftAt(m.x, m.z) + lift + stacks.heightOf(i), m.z, out);
    },
    intro(play) {
      wake();
      if (play && !reduced) {
        revealStart = t;
        lines.setReveal(CASTLE.x, CASTLE.z, 400, 1400);
        stacks.setOpacity(0);
      } else {
        revealStart = -1;
        lines.setReveal(CASTLE.x, CASTLE.z, Infinity);
        stacks.setOpacity(1);
      }
    },
    setDome(scale) {
      wake();
      domeScaleGoal = scale;
    },
    liftAt: (x, z) => living.liftAt(x, z),
    dent(amount, x = dentX, z = dentZ, radius = dentRadius) {
      wake();
      dentAmount = reduced ? 0 : amount;
      dentX = x;
      dentZ = z;
      dentRadius = radius;
      if (amount <= 0) {
        // the dome comes back from flat
        living.setBulge(0, 0);
        groundKnown = false;
      }
      world.invalidate();
    },
    ring(x, z, power = 1) {
      wake();
      if (reduced) return;
      slam.on = true;
      slam.t0 = t;
      slam.x = x;
      slam.z = z;
      slam.power = power;
      nextRing = t + 6;
    },
    kick(velocity) {
      wake();
      if (!reduced) kickV += velocity;
    },
    freeze(ms) {
      wake();
      frozenUntil = performance.now() + ms;
    },
    setHero(on, { instant = false, pulse: wantPulse = on } = {}) {
      redGoal = on ? 1 : 0;
      if (instant || reduced) red = redGoal;
      if (wantPulse && !pulse) pulseStart = t;
      pulse = wantPulse;
      applyHero();
      busy(0.9);
    },
    setLit(records) {
      wake();
      pendingLit = records;
    },
    hover(index) {
      if (index === hovered) return;
      hovered = index;
      aimStacks();
      const end = stacks.setTargets(growGoal, toneGoal, { duration: reduced ? 0.01 : 0.24 });
      busy(end - t + 0.05);
    },
    setWave(amount, seconds = 0) {
      wake();
      if (seconds > 0 && !reduced) {
        waveFrom = wave;
        waveTo = amount;
        waveStart = t;
        waveLength = seconds;
      } else {
        waveStart = -1;
        if (amount !== wave) {
          wave = amount;
          pinSent = -1;
          applyHero();
          busy(0.25);
        }
      }
    },
    setHill(amount) {
      if (amount === relief) return;
      relief = amount;
      world.setRelief(amount);
      slabs.mesh.position.y = slabLevel * amount;
      placeCastle();
      busy(0.25);
    },
    setSpot(amount) {
      if (amount === spotAmount) return;
      spotAmount = amount;
      lines.setSpot(CASTLE.x, CASTLE.z, 150, amount);
      busy(0.25);
    },
    setDim(amount) {
      if (amount !== dim) {
        dim = amount;
        lines.setDim(amount);
        busy(0.25);
      }
    },
    setCastle(onMap, fold) {
      if (onMap === castleOn && fold === castleFold) return;
      castleOn = onMap;
      castleFold = fold;
      if (!castle && onMap > 0.001) {
        const made = createCastle(world);
        made.group.position.set(CASTLE_ORIGIN.x, 0, CASTLE_ORIGIN.z);
        made.group.rotation.y = HILL_GRID_DEG * RAD;
        world.scene.add(made.group);
        castle = made;
      }
      placeCastle();
      busy(0.25);
    },
    setHall(onMap, fold) {
      if (onMap === hallOn && fold === hallFold) return;
      hallOn = onMap;
      hallFold = fold;
      if (!hall && onMap > 0.001) {
        const made = createCityHall(world);
        made.group.position.set(HALL.x, 0, HALL.z);
        made.group.rotation.y = (90 + CIVIC_GRID_DEG) * RAD;
        made.setBase(0);
        world.scene.add(made.group);
        hall = made;
      }
      placeHall();
      busy(0.25);
    },
    setLetters(a, b) {
      if (a === lettersFor[0] && b === lettersFor[1]) return;
      lettersFor = [a, b];
      const on = a > 0 || b > 0;
      if (on && !support) {
        // (made when first wanted: how many there are is the story's to say)
        support = createBlocks(world, cards(LETTER_ROWS.support, Math.max(1, Math.ceil(a)), 1), { edge: 0.7 });
        world.scene.add(support.mesh);
      }
      if (on && !opposition) {
        opposition = createBlocks(world, cards(LETTER_ROWS.opposition, Math.max(1, Math.ceil(b)), 0), { edge: 0.7 });
        world.scene.add(opposition.mesh);
      }
      if (support) {
        support.mesh.visible = a > 0;
        support.setRise(a);
      }
      if (opposition) {
        opposition.mesh.visible = b > 0;
        opposition.setRise(b);
      }
      world.invalidate();
      busy(0.25);
    },
    setSeats(standing, voted) {
      seats.mesh.visible = standing > 0;
      seats.setRise(standing);
      seats.setLit(voted);
      busy(0.25);
    },
    setLight(civic) {
      const light = world.uniforms.uLight.value;
      const x = HILL_LIGHT.x + (CIVIC_LIGHT.x - HILL_LIGHT.x) * civic;
      if (Math.abs(light.x - x) < 1e-5) return;
      light.copy(HILL_LIGHT).lerp(CIVIC_LIGHT, civic).normalize();
      world.invalidate();
      busy(0.25);
    },
    setSearch(on) {
      searching = on;
      wake();
    },
    setRoute(points, draw = 0) {
      wake();
      if (points && !route) {
        const n = points.length / 2 - 1;
        const segs = new Float32Array(n * 4);
        const order = new Float32Array(n);
        let total = 0;
        const along = new Float32Array(n);
        for (let i = 0; i < n; i++) {
          segs[i * 4] = points[i * 2]!;
          segs[i * 4 + 1] = points[i * 2 + 1]!;
          segs[i * 4 + 2] = points[i * 2 + 2]!;
          segs[i * 4 + 3] = points[i * 2 + 3]!;
          along[i] = total;
          total += Math.hypot(segs[i * 4 + 2]! - segs[i * 4]!, segs[i * 4 + 3]! - segs[i * 4 + 1]!);
        }
        for (let i = 0; i < n; i++) order[i] = along[i]! / (total || 1);
        route = createLivingLines(world, living, { segs, order, widths: [2.6, 2.6], opacities: [1, 1], color: "ink", highlight: "ink", renderOrder: 2, depthTest: true });
        route.setDraw(0, 1 / n);
        world.scene.add(route.mesh);
      }
      route?.setDraw(draw >= 1 ? 2 : draw * 1.02);
      if (draw !== routeDrawn) {
        routeDrawn = draw;
        busy(0.25);
      }
    },
    setSlabs(grow, line, lineAmount) {
      const on = grow > 0.001;
      if (slabs.mesh.visible !== on) {
        slabs.mesh.visible = on;
        world.invalidate();
      }
      slabs.setGrow(grow);
      slabs.setPick(line, lineAmount);
      busy(0.25);
    },
    heroLine(i) {
      // the middle of the slab's east end, as it stands now
      const end = offset(SLABS.at, HILL_GRID_DEG, SLABS.w / 2, 0);
      return { x: end.x, y: slabs.mesh.position.y + i * SLABS.pitch + SLABS.thick / 2, z: end.z };
    },
    heroTop(out) {
      out.x = CASTLE.x;
      out.z = CASTLE.z;
      out.y = hero >= 0 ? world.heightAt(CASTLE.x, CASTLE.z) + living.liftAt(CASTLE.x, CASTLE.z) + clamp(shown.distance * 0.0022, 3, 46) + stacks.heightOf(hero) : 0;
      return out;
    },
    setTheme(instant = false) {
      world.setTheme({ instant });
      applyTheme();
      busy(0.4);
    },
    renderNow() {
      world.update(performance.now());
      world.render();
      for (const cb of listeners) cb();
    },
    setVisible(v) {
      visible = v;
      if (v) {
        world.invalidate();
        wake();
      }
    },
    setResting(next) {
      if (next === resting) return;
      resting = next;
      aimAlive();
    },
    setStill(still) {
      if (still === reduced) return;
      reduced = still;
      aimAlive();
      busy(0.4);
    },
    dispose() {
      disposed = true;
      cancelAnimationFrame(raf);
      world.dispose();
    },
  };
  // the graphics card gave the drawing back: draw it again (the world marks itself to be drawn)
  canvas.addEventListener("webglcontextrestored", () => wake());
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) wake();
  });
  raf = requestAnimationFrame(frame);
  return scene;
}
