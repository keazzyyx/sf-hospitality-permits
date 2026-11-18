// The stamp as an actor on a stage: it follows a target with a short lag, leans into fast moves, hangs at a
// height its shadow shows, lowers under pressure, winds up and drops under gravity, squashes on contact, taps,
// lies down and gets up. One requestAnimationFrame loop, stepped by time; it draws only when the pose changes,
// sleeps when nothing can change, and stops while the tab is hidden. The picture comes from a renderer: three.js
// when it can be had (loaded lazily, after first paint), else SVG.

import { MARK_TILT } from "./mark";
import type { StampPose, StampRenderer } from "./pose";
import { Spring, clamp, follow, lerp } from "./spring";
import { createStamp2D } from "./stamp2d";

export interface StampOptions {
  /** Width of the die, and so of the mark, in CSS pixels. */
  dieWidth: number;
  /** The tilt of the die on the page, in degrees. Default MARK_TILT. */
  tilt?: number;
  /** The words on the die's face. */
  lines?: readonly [string, string?];
  /** Try the three.js stamp (it loads as its own chunk; only where a graphics card draws WebGL). Default true.
   *  False: the drawn stamp only. */
  webgl?: boolean;
  /** Height above the page while it hangs, in CSS pixels. Default 0.3 of the die's width. */
  hover?: number;
  /** Height above the page at full pressure: what is left for it to drop. Default 0.14 of the die's width. */
  pressed?: number;
  /** How long to wait for the three.js stamp before the drawn one shows in its place, in ms. Default 700. Pass 0
   *  to show the drawn stamp at once (the three.js one is cross-faded in when it arrives). */
  patience?: number;
  /** Do not ask for the three.js chunk before this settles (the page's own data, say). It is then fetched in idle
   *  time. Default: asked for at once. */
  after?: Promise<unknown>;
  /** Called whenever the picture on the stage changes: "2d" (the drawn stamp) or "3d" (three.js). */
  onKind?: (kind: "3d" | "2d") => void;
}

export interface Stamp {
  /** Which picture is on the stage: resolves once one is showing. */
  readonly ready: Promise<"3d" | "2d">;
  /** The renderer showing now. */
  readonly kind: "3d" | "2d" | null;
  /** The pose now (read it, do not change it). */
  readonly pose: Readonly<StampPose>;
  /** True between contact and lift. */
  readonly down: boolean;
  /** Put the stamp somewhere at once, with no travel. */
  place(x: number, y: number): void;
  /** Follow this point (stage pixels). `tau` is the lag in seconds; default 0.075. */
  moveTo(x: number, y: number, tau?: number): void;
  /** Resolve when the stamp has reached where it is going (within a few pixels). */
  arrive(): Promise<void>;
  /** Fade in (and out). */
  show(visible?: boolean): void;
  /** Hang in the air (the default), or stand on the page. */
  stand(onPage: boolean): void;
  /** Pressure from 0 to 1 lowers the stamp from its hover height toward the page. */
  press(pressure: number): void;
  /** Let go of the pressure: it springs back up. */
  release(): void;
  /** Wind up (it rises `rise` px, default 0.095 of the die's width, in about 90 ms) and drop the rest of the way
   *  under gravity. `onContact` runs in the frame the die meets the page, before that frame is drawn; the promise
   *  resolves just after. The stamp stays down until lift(). */
  slam(onContact?: () => void, rise?: number): Promise<void>;
  /** A light tap on the page and back up (for drumming, or dabbing an ink pad). Resolves on the touch. */
  tap(onTouch?: () => void): Promise<void>;
  /** Come up off the page after a slam. With `to` (a height in CSS px) it rises straight to that height, a little
   *  nearer the viewer, and hangs there (clear of the mark) until it is next pressed or stood down. */
  lift(to?: number): void;
  /** Stop everything for this long: nothing moves, no frame callbacks run. */
  freeze(ms: number): void;
  /** Lie down on its back, or get up. */
  lie(down: boolean): void;
  /** Called on every frame that advances, with the seconds since the last and the pose, before it is drawn.
   *  A callback that returns `false` says it has nothing moving: when every callback says so and the stamp itself
   *  is at rest, the loop sleeps until the stamp is next told to do something (or wake() is called). */
  onFrame(cb: (dt: number, pose: Readonly<StampPose>, now: number) => void | boolean): () => void;
  /** Start the loop again if it is asleep (call it when something of your own starts moving). */
  wake(): void;
  /** Hold the stamp still (the visitor paused the page's motion, or the system asks for less): no hover bob, and
   *  it lies down or gets up at once. It still follows what it is told; once that has arrived it is drawn once and
   *  the loop sleeps. */
  setStill(still: boolean): void;
  /** The stage or the die changed size. */
  resize(dieWidth?: number): void;
  destroy(): void;
}

type Mode = "hover" | "stand" | "press" | "windup" | "fall" | "down";

let hardware: boolean | null = null;

/**
 * True when WebGL is drawn by a graphics card. A software renderer (SwiftShader, llvmpipe, a basic display driver)
 * can draw the three.js stamp, but slowly, and Chromium warns on every frame it reads back: there the drawn stamp
 * is the better stamp. Asked once, then remembered.
 */
export function hardwareWebGL(): boolean {
  if (hardware !== null) return hardware;
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2");
    if (!gl) return (hardware = false);
    const info = gl.getExtension("WEBGL_debug_renderer_info");
    const renderer = String(gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER) ?? "");
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    hardware = !/swiftshader|llvmpipe|software|basic render/i.test(renderer);
  } catch {
    hardware = false;
  }
  return hardware;
}

const GRAVITY = 8200; // CSS px per second squared: a drop of 72 px takes about 130 ms and lands at 1,090 px/s
const TAP_GRAVITY = 3000;
const WINDUP_MS = 90;
/** The hover bob dies away after this many seconds with nothing asked of the stamp. */
const BOB_REST = 10;

const idle = (run: () => void): void => {
  const w = window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number };
  if (w.requestIdleCallback) w.requestIdleCallback(run, { timeout: 1200 });
  else window.setTimeout(run, 200);
};

/**
 * Put a stamp on `stage` (an element with its own box: the stamp's layers fill it and take no pointer events).
 * It starts hidden: place() it, then show().
 */
export function createStamp(stage: HTMLElement, options: StampOptions): Stamp {
  const tilt = options.tilt ?? MARK_TILT;
  let dieWidth = options.dieWidth;
  let hoverHeight = options.hover ?? dieWidth * 0.3;
  let pressedHeight = options.pressed ?? dieWidth * 0.14;
  /** The height it hangs at: the hover height, or higher after lift(to). */
  let hang = hoverHeight;

  const pose: StampPose = { x: 0, y: 0, h: hoverHeight, leanX: 0, leanZ: 0, squash: 0, lying: 0, alpha: 0, zoom: 0 };
  let tx = 0;
  let ty = 0;
  let tau = 0.075;
  let vx = 0;
  let vy = 0;
  let mode: Mode = "hover";
  let pressure = 0;
  let fallSpeed = 0;
  let fallFloor = 0;
  let fallGravity = GRAVITY;
  let fallSquash = 0.2;
  let onLand: (() => void) | null = null;
  let landed: (() => void) | null = null;
  let stayDown = false;
  let windFrom = 0;
  let windTo = 0;
  let windT = 0;
  let alphaTarget = 0;
  let lieTarget = 0;
  let zoomTarget = 0;
  let frozenUntil = 0;
  let clock = 0;
  /** When something was last asked of the stamp (on the loop's own clock): the bob rests a while after. */
  let stirred = 0;
  let bobAmp = 1;
  /** Held still: no bob, no slow lying down. */
  let held = false;
  let last = 0;
  let frame = 0;
  let running = false;
  let destroyed = false;
  let tick = 0;

  const height = new Spring(hoverHeight, 240, 21);
  const leanX = new Spring(0, 130, 9.5);
  const leanZ = new Spring(0, 130, 9.5);
  const squash = new Spring(0, 620, 21);
  const lying = new Spring(0, 85, 12.5);

  const listeners = new Set<(dt: number, pose: Readonly<StampPose>, now: number) => void | boolean>();
  const arrivals: (() => void)[] = [];

  // ---- renderers ---------------------------------------------------------------------------------------------
  const drawn = createStamp2D(tilt, options.lines);
  drawn.el.classList.add("is-off");
  stage.append(drawn.el);
  let renderers: StampRenderer[] = [];
  let kind: "3d" | "2d" | null = null;
  let announce: (k: "3d" | "2d") => void = () => {};
  const ready = new Promise<"3d" | "2d">(resolve => (announce = resolve));
  let lastKey = "";

  const size = (): void => {
    const w = stage.clientWidth;
    const h = stage.clientHeight;
    for (const r of new Set([drawn, ...renderers])) r.resize(w, h, dieWidth);
    lastKey = "";
  };

  function use2d(): void {
    if (kind || destroyed) return;
    kind = "2d";
    renderers = [drawn];
    drawn.el.classList.remove("is-off");
    lastKey = "";
    announce("2d");
    options.onKind?.("2d");
    wake();
  }

  if (options.webgl === false || !hardwareWebGL()) use2d();
  else {
    const patience = window.setTimeout(use2d, options.patience ?? 700);
    const load = (): void => {
      if (destroyed) return;
      void import("./stamp3d")
        .then(module => {
          if (destroyed) return;
          let three: StampRenderer | null = null;
          /** The graphics card took the context away: the drawn stamp takes the stage back, and keeps it. */
          const lost = (): void => {
            if (destroyed || !three) return;
            const gone = three;
            three = null;
            kind = "2d";
            renderers = [drawn];
            if (!drawn.el.isConnected) stage.append(drawn.el);
            drawn.resize(stage.clientWidth, stage.clientHeight, dieWidth);
            drawn.el.classList.remove("is-off");
            gone.destroy();
            lastKey = "";
            options.onKind?.("2d");
            wake();
          };
          three = module.createStamp3D(stage, { tilt, lines: options.lines, onLost: lost });
          const made = three;
          made.el.classList.add("is-off");
          stage.append(made.el);
          made.resize(stage.clientWidth, stage.clientHeight, dieWidth);
          window.clearTimeout(patience);
          const swap = (): void => {
            if (destroyed || three !== made) return;
            // draw it once before it shows, then cross-fade (about 300 ms, in CSS)
            made.draw(pose);
            const had = kind;
            kind = "3d";
            renderers = had === "2d" ? [drawn, made] : [made];
            lastKey = "";
            wake();
            requestAnimationFrame(() => {
              if (destroyed || three !== made) return;
              made.el.classList.remove("is-off");
              drawn.el.classList.add("is-off");
              window.setTimeout(() => {
                if (destroyed || three !== made) return;
                renderers = [made];
                drawn.el.remove();
              }, 340);
            });
            if (!had) announce("3d");
            options.onKind?.("3d");
          };
          // never swap pictures in the middle of a press or a slam
          const calm = (): void => {
            if (destroyed || three !== made) return;
            if (mode === "hover" || mode === "stand") swap();
            else window.setTimeout(calm, 120);
          };
          calm();
        })
        .catch(() => {
          window.clearTimeout(patience);
          use2d();
        });
    };
    if (options.after) {
      const later = (): void => idle(load);
      options.after.then(later, later);
    } else load();
  }

  // ---- the loop ----------------------------------------------------------------------------------------------
  /** Something was asked of the stamp: the loop runs, and the bob is awake. */
  function stir(): void {
    stirred = clock;
    wake();
  }

  function step(dt: number): void {
    clock += dt;
    // where it is: a short exponential lag behind the target
    const px = pose.x;
    const py = pose.y;
    pose.x = follow(pose.x, tx, dt, tau);
    pose.y = follow(pose.y, ty, dt, tau);
    if (Math.abs(pose.x - tx) < 0.01) pose.x = tx;
    if (Math.abs(pose.y - ty) < 0.01) pose.y = ty;
    const ivx = (pose.x - px) / dt;
    const ivy = (pose.y - py) / dt;
    vx = follow(vx, ivx, dt, 0.05);
    vy = follow(vy, ivy, dt, 0.05);
    if (Math.abs(vx) < 0.05) vx = 0;
    if (Math.abs(vy) < 0.05) vy = 0;
    if (arrivals.length && Math.hypot(pose.x - tx, pose.y - ty) < 3) for (const done of arrivals.splice(0)) done();

    // lean: the top leads into a fast move, and sways back when it stops (nothing leans while it is on the page)
    const grounded = mode === "down" || (mode === "stand" && pose.h < 2);
    const scale = dieWidth / 320;
    leanX.target = grounded ? 0 : clamp((vx / scale) * 0.00016, -0.3, 0.3) * (1 - pose.lying);
    leanZ.target = grounded ? 0 : clamp((vy / scale) * 0.00012, -0.22, 0.22) * (1 - pose.lying);
    leanX.step(dt);
    leanZ.step(dt);
    pose.leanX = leanX.value;
    pose.leanZ = leanZ.value;

    // height
    if (mode === "windup") {
      // the anticipation: up a little, slowing, before the weight comes down
      windT += dt;
      const k = Math.min(1, windT / (WINDUP_MS / 1000));
      pose.h = lerp(windFrom, windTo, 1 - (1 - k) * (1 - k));
      height.value = pose.h;
      height.velocity = 0;
      if (k >= 1) {
        mode = "fall";
        fallSpeed = 0;
      }
    } else if (mode === "fall") {
      fallSpeed += fallGravity * dt;
      pose.h -= fallSpeed * dt;
      if (pose.h <= fallFloor) {
        pose.h = fallFloor;
        squash.value = fallSquash;
        squash.velocity = 0;
        const land = onLand;
        const after = landed;
        onLand = null;
        landed = null;
        if (stayDown) mode = "down";
        else {
          mode = "hover";
          height.value = pose.h;
          height.velocity = fallSpeed * 0.35; // it comes back up off the touch
        }
        land?.();
        if (after) queueMicrotask(after);
      }
    } else if (mode === "press") {
      const eased = pressure * pressure * (3 - 2 * pressure) * 0.35 + pressure * 0.65;
      pose.h = follow(pose.h, lerp(hoverHeight, pressedHeight, eased), dt, 0.04);
      height.value = pose.h;
      height.velocity = 0;
    } else if (mode === "down") {
      pose.h = 0;
      height.value = 0;
      height.velocity = 0;
    } else {
      // hanging (with a slow bob that rests when nothing has been asked for a while) or standing on the page;
      // lying down brings it to the page as well
      bobAmp = held ? 0 : follow(bobAmp, clock - stirred < BOB_REST ? 1 : 0, dt, 0.9);
      if (bobAmp < 0.004) bobAmp = 0;
      const bob = mode === "hover" ? Math.sin(clock * 2.3) * dieWidth * 0.008 * bobAmp : 0;
      height.target = mode === "stand" ? 0 : lerp(hang + bob, 0, lying.value);
      height.step(dt);
      if (height.value < 0) {
        height.value = 0;
        height.velocity = Math.abs(height.velocity) * 0.2;
      }
      pose.h = height.value;
    }

    squash.target = 0;
    squash.step(dt);
    pose.squash = Math.max(-0.06, squash.value);
    lying.target = lieTarget;
    lying.step(dt);
    pose.lying = clamp(lying.value, 0, 1.04);
    pose.alpha = follow(pose.alpha, alphaTarget, dt, 0.09);
    if (Math.abs(pose.alpha - alphaTarget) < 0.004) pose.alpha = alphaTarget;
    pose.zoom = follow(pose.zoom, zoomTarget, dt, 0.07);
    if (Math.abs(pose.zoom - zoomTarget) < 0.0005) pose.zoom = zoomTarget;
  }

  /** True when no number of the pose can change until the stamp is asked to do something. */
  function atRest(): boolean {
    if (mode !== "stand" && mode !== "hover" && mode !== "down") return false;
    // (a stamp lying flat on the page has no bob to show: the loop may rest under it)
    if (mode === "hover" && bobAmp > 0 && !(lieTarget === 1 && lying.value === 1)) return false;
    return (
      pose.x === tx &&
      pose.y === ty &&
      vx === 0 &&
      vy === 0 &&
      height.resting &&
      leanX.resting &&
      leanZ.resting &&
      squash.resting &&
      lying.resting &&
      lying.value === lieTarget &&
      pose.alpha === alphaTarget &&
      pose.zoom === zoomTarget &&
      arrivals.length === 0
    );
  }

  function loop(now: number): void {
    if (destroyed) return;
    frame = requestAnimationFrame(loop);
    if (now < frozenUntil) {
      last = now;
      return;
    }
    const dt = last ? Math.min(0.05, (now - last) / 1000) : 1 / 60;
    last = now;
    if (dt <= 0) return;
    step(dt);
    let wanted = false;
    for (const cb of listeners) if (cb(dt, pose, now) !== false) wanted = true;
    const busy = renderers.some(r => r.busy());
    // hanging still, only the bob moves: a third of the frame rate is plenty
    const still = mode === "hover" && vx === 0 && vy === 0 && leanX.resting && leanZ.resting && squash.resting && pose.alpha === alphaTarget && lying.resting && pose.zoom === zoomTarget;
    tick = (tick + 1) % 3;
    if (!(still && tick !== 0 && !busy)) {
      const key = `${pose.x.toFixed(2)},${pose.y.toFixed(2)},${pose.h.toFixed(2)},${pose.leanX.toFixed(4)},${pose.leanZ.toFixed(4)},${pose.squash.toFixed(4)},${pose.lying.toFixed(4)},${pose.alpha.toFixed(3)},${pose.zoom.toFixed(4)}`;
      if (key !== lastKey || busy) {
        lastKey = key;
        for (const r of renderers) r.draw(pose);
      }
    }
    // nothing can change: stop asking for frames until something does
    if (!wanted && !busy && kind && atRest() && lastKey !== "") {
      cancelAnimationFrame(frame);
      running = false;
      last = 0;
    }
  }

  function wake(): void {
    if (running || destroyed || document.hidden) return;
    running = true;
    last = 0;
    frame = requestAnimationFrame(loop);
  }

  const onVisibility = (): void => {
    cancelAnimationFrame(frame);
    running = false;
    last = 0;
    if (!document.hidden) wake();
  };
  document.addEventListener("visibilitychange", onVisibility);
  const onTheme = (): void => {
    for (const r of new Set([drawn, ...renderers])) r.setPalette();
    lastKey = "";
    wake();
  };
  window.addEventListener("themechange", onTheme);

  size();
  wake();

  function drop(floor: number, gravity: number, squashBy: number, stay: boolean, rise: number, onContact?: () => void): Promise<void> {
    return new Promise(resolve => {
      fallSpeed = 0;
      fallFloor = floor;
      fallGravity = gravity;
      fallSquash = squashBy;
      stayDown = stay;
      onLand = onContact ?? null;
      landed = resolve;
      if (rise > 0) {
        mode = "windup";
        windFrom = pose.h;
        windTo = pose.h + rise;
        windT = 0;
      } else mode = "fall";
      stir();
    });
  }

  return {
    ready,
    get kind() {
      return kind;
    },
    pose,
    get down() {
      return mode === "down";
    },
    place(x, y) {
      pose.x = tx = x;
      pose.y = ty = y;
      vx = vy = 0;
      lastKey = "";
      wake();
    },
    moveTo(x, y, lag = 0.075) {
      if (Math.abs(x - tx) > 0.5 || Math.abs(y - ty) > 0.5) stir();
      tx = x;
      ty = y;
      tau = lag;
    },
    arrive() {
      wake();
      return new Promise(resolve => arrivals.push(resolve));
    },
    show(visible = true) {
      alphaTarget = visible ? 1 : 0;
      wake();
    },
    stand(onPage) {
      if (mode === "hover" || mode === "stand") mode = onPage ? "stand" : "hover";
      if (onPage) {
        hang = hoverHeight;
        zoomTarget = 0;
      }
      stir();
    },
    press(p) {
      if (mode === "windup" || mode === "fall" || mode === "down") return;
      mode = "press";
      hang = hoverHeight;
      zoomTarget = 0;
      pressure = clamp(p, 0, 1);
      stir();
    },
    release() {
      if (mode !== "press") return;
      mode = "hover";
      pressure = 0;
      height.value = pose.h;
      height.velocity = 0;
      stir();
    },
    slam(onContact, rise = dieWidth * 0.095) {
      return drop(0, GRAVITY, 0.2, true, Math.max(0, rise), onContact);
    },
    tap(onTouch) {
      if (mode !== "hover") return Promise.resolve();
      return drop(dieWidth * 0.006, TAP_GRAVITY, 0.07, false, 0, onTouch);
    },
    lift(to) {
      if (mode !== "down") return;
      mode = "hover";
      height.value = 0;
      if (to === undefined) {
        hang = hoverHeight;
        height.velocity = hoverHeight * 5;
      } else {
        // straight up, from rest: the weight comes off the page slowly and then hangs clear of the mark
        hang = Math.max(hoverHeight, to);
        height.velocity = 0;
        zoomTarget = 0.045;
      }
      stir();
    },
    freeze(ms) {
      frozenUntil = performance.now() + ms;
      wake();
    },
    lie(down) {
      lieTarget = down ? 1 : 0;
      if (held) {
        // (held still: it is lying down, or up, in the next frame drawn)
        lying.value = lying.target = lieTarget;
        lying.velocity = 0;
      }
      stir();
    },
    setStill(still) {
      if (still === held) return;
      held = still;
      if (held) bobAmp = 0;
      stir();
    },
    onFrame(cb) {
      listeners.add(cb);
      wake();
      return () => listeners.delete(cb);
    },
    wake,
    resize(next) {
      if (next && next !== dieWidth) {
        const k = next / dieWidth;
        dieWidth = next;
        hoverHeight *= k;
        pressedHeight *= k;
        hang *= k;
      }
      size();
      wake();
    },
    destroy() {
      destroyed = true;
      running = false;
      cancelAnimationFrame(frame);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("themechange", onTheme);
      listeners.clear();
      for (const r of new Set([drawn, ...renderers])) r.destroy();
      renderers = [];
    },
  };
}
