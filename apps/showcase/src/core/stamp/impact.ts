// What a heavy thing does to the page it lands on: the stage kicks and settles (an underdamped spring), a ring
// runs out through the lines of the ground, and ink flecks land around the mark. Also the low rumble that builds
// under a hold. Everything is stepped by time and seeded.

import { between, rng } from "./rng";
import { Spring } from "./spring";

const NS = "http://www.w3.org/2000/svg";

export interface Shaker {
  /** Give the element a shove, in CSS pixels per second (and degrees per second). It rings down by itself. */
  kick(vx: number, vy: number, vr?: number): void;
  /** A steady tremble of up to `amount` pixels (0 stops it). */
  rumble(amount: number): void;
  /** Advance by `dt` seconds and write the transform. Returns true while it is still moving. */
  step(dt: number, now: number): boolean;
  /** Back to rest at once. */
  reset(): void;
}

/**
 * Shake `el` (an element with no transform of its own). The spring is the one a dropped weight leaves in a table:
 * stiffness 500, damping 12, so a kick is gone in about 400 ms.
 */
export function createShaker(el: HTMLElement, stiffness = 500, damping = 12): Shaker {
  const x = new Spring(0, stiffness, damping);
  const y = new Spring(0, stiffness, damping);
  const r = new Spring(0, stiffness * 0.8, damping);
  let tremble = 0;
  let written = "";
  return {
    kick(vx, vy, vr = 0) {
      x.velocity += vx;
      y.velocity += vy;
      r.velocity += vr;
    },
    rumble(amount) {
      tremble = amount;
    },
    step(dt, now) {
      const moving = [x.step(dt), y.step(dt), r.step(dt)].some(Boolean);
      let dx = x.value;
      let dy = y.value;
      if (tremble > 0) {
        // two sines that never line up: a tremble, not a wobble
        dx += Math.sin(now * 0.071) * Math.sin(now * 0.0293 + 1.7) * tremble;
        dy += Math.sin(now * 0.083 + 0.6) * Math.sin(now * 0.0371) * tremble;
      }
      const next = Math.abs(dx) < 0.01 && Math.abs(dy) < 0.01 && Math.abs(r.value) < 0.001 ? "" : `translate3d(${dx.toFixed(2)}px, ${dy.toFixed(2)}px, 0) rotate(${r.value.toFixed(3)}deg)`;
      if (next !== written) {
        written = next;
        el.style.transform = next;
      }
      return moving || tremble > 0;
    },
    reset() {
      x.set(0);
      y.set(0);
      r.set(0);
      tremble = 0;
      written = "";
      el.style.transform = "";
    },
  };
}

export interface RippleOptions {
  /** How far the ring runs, in CSS pixels. Default 560. */
  radius?: number;
  /** Milliseconds. Default 620. */
  duration?: number;
  /** Width of the ring. Default 34. */
  width?: number;
}

/**
 * Run a ring out from (x, y) across `layer`: an element laid over the ground that carries the ground's own lines
 * (the class `stamp-ripple` masks it to a ring and pushes it a little outward, so the lines inside the ring look
 * displaced). Resolves when the ring has died away.
 */
export function ripple(layer: HTMLElement, x: number, y: number, options: RippleOptions = {}): Promise<void> {
  const radius = options.radius ?? 560;
  const duration = options.duration ?? 620;
  const width = options.width ?? 34;
  layer.classList.add("stamp-ripple");
  layer.style.setProperty("--ripple-x", `${x.toFixed(1)}px`);
  layer.style.setProperty("--ripple-y", `${y.toFixed(1)}px`);
  layer.style.setProperty("--ripple-w", `${width}px`);
  return new Promise(resolve => {
    const start = performance.now();
    const frame = (now: number): void => {
      const t = Math.min(1, (now - start) / duration);
      // fast out of the impact, slowing as it spreads
      const eased = 1 - (1 - t) ** 2.4;
      layer.style.setProperty("--ripple-r", `${(24 + eased * radius).toFixed(1)}px`);
      layer.style.setProperty("--ripple-o", (1 - t) ** 1.5 * 1 + "");
      if (t < 1) requestAnimationFrame(frame);
      else {
        layer.style.setProperty("--ripple-o", "0");
        resolve();
      }
    };
    requestAnimationFrame(frame);
  });
}

export interface FleckOptions {
  seed?: number;
  /** How many. Default 16. */
  count?: number;
  /** Width and height of the mark they surround, in CSS pixels. */
  width: number;
  height: number;
  /** The mark's tilt in degrees. */
  tilt?: number;
  /** How far the furthest lands from the mark's edge. Default 0.2 of the width. */
  reach?: number;
}

/**
 * Ink flecks around a mark centred on (x, y) of `host` (the element the mark is on). They are drawn at once, a
 * little way in from where they land, and fly out the rest (CSS, `stamp-flecks`; none of it under reduced motion).
 */
export function flecks(host: Element, x: number, y: number, options: FleckOptions): SVGSVGElement {
  const r = rng(options.seed ?? 1);
  const count = options.count ?? 16;
  const reach = options.reach ?? options.width * 0.2;
  const hw = options.width / 2;
  const hh = options.height / 2;
  const size = (Math.max(hw, hh) + reach + 12) * 2;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "stamp-flecks");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("viewBox", `${-size / 2} ${-size / 2} ${size} ${size}`);
  svg.style.left = `${x}px`;
  svg.style.top = `${y}px`;
  svg.style.setProperty("--mark-tilt", `${options.tilt ?? 0}deg`);
  for (let i = 0; i < count; i++) {
    // a point on the mark's edge, then out along the way it was thrown
    const a = between(r, 0, Math.PI * 2);
    const ex = Math.cos(a);
    const ey = Math.sin(a);
    const k = 1 / Math.max(Math.abs(ex) / hw, Math.abs(ey) / hh);
    const out = reach * between(r, 0.08, 1) ** 1.9 + 3;
    const px = ex * k + ex * out;
    const py = ey * k + ey * out;
    const big = r() < 0.22;
    const rad = big ? between(r, 1.6, 3.1) : between(r, 0.5, 1.4);
    const long = 1 + between(r, 0, 1.2) * (out / reach);
    const fleck = document.createElementNS(NS, "ellipse");
    fleck.setAttribute("cx", px.toFixed(1));
    fleck.setAttribute("cy", py.toFixed(1));
    fleck.setAttribute("rx", (rad * long).toFixed(2));
    fleck.setAttribute("ry", rad.toFixed(2));
    fleck.setAttribute("transform", `rotate(${((Math.atan2(ey, ex) * 180) / Math.PI).toFixed(1)} ${px.toFixed(1)} ${py.toFixed(1)})`);
    fleck.style.setProperty("--fly-x", `${(-ex * out * 0.8).toFixed(1)}px`);
    fleck.style.setProperty("--fly-y", `${(-ey * out * 0.8).toFixed(1)}px`);
    fleck.style.animationDelay = `${Math.round(between(r, 0, 36))}ms`;
    svg.append(fleck);
  }
  host.append(svg);
  return svg;
}
