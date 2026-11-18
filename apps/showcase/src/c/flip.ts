// The flip: activating the mark (the half-filled circle top right, or the T key) turns blueprint to paper and
// back, and the new theme spreads as a circle from the mark across the page. One radius drives it: the page is
// handed to a view transition whose new picture (the DOM and the canvas together, already in the new theme) is
// revealed through a growing circle, so the two can never be out of step. Where there is no view transition,
// or the visitor asks for less motion, it is a cut.

import { reducedMotion } from "../core/env";
import { getTheme, setTheme, type Theme } from "../core/theme";

const FLIP_MS = 620;

export interface FlipOptions {
  /** The shell's flip button. */
  button: HTMLElement;
  /** Called inside the transition, after the page's theme has changed: bring the canvas to the new theme at once
   *  and draw it (`instant`), or let it ease there (`instant` false: there is no transition to carry it). */
  onTheme(theme: Theme, instant: boolean): void;
}

type Transition = { ready: Promise<void>; finished: Promise<void> };

export function installFlip({ button, onTheme }: FlipOptions): void {
  let running = false;
  /** A flip asked for while one runs follows when it ends; a third press takes that back (the theme the presses
   *  add up to is the one the page ends on). */
  let queued = 0;
  const flip = (): void => {
    if (running) {
      queued = queued ? 0 : 1;
      return;
    }
    const next: Theme = getTheme() === "paper" ? "blueprint" : "paper";
    const doc = document as Document & { startViewTransition?: (update: () => void) => Transition };
    if (reducedMotion() || typeof doc.startViewTransition !== "function") {
      setTheme(next);
      onTheme(next, reducedMotion());
      return;
    }
    const box = button.getBoundingClientRect();
    const x = box.left + box.width / 2;
    const y = box.top + box.height / 2;
    const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y)) + 4;
    const root = document.documentElement;
    running = true;
    root.classList.add("c-flip");
    const transition = doc.startViewTransition(() => {
      setTheme(next);
      onTheme(next, true);
    });
    transition.ready
      .then(() => {
        root.animate(
          { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
          { duration: FLIP_MS, easing: "cubic-bezier(0.45, 0, 0.2, 1)", pseudoElement: "::view-transition-new(root)", fill: "both" },
        );
      })
      .catch(() => {});
    void transition.finished
      .catch(() => {})
      .then(() => {
        root.classList.remove("c-flip");
        running = false;
        if (queued > 0) {
          queued -= 1;
          flip();
        }
      });
  };

  // the shell's own listener flips at once: this one runs first and takes the click
  button.addEventListener(
    "click",
    event => {
      event.stopImmediatePropagation();
      event.preventDefault();
      flip();
    },
    { capture: true },
  );
  window.addEventListener("keydown", event => {
    if (event.key !== "t" && event.key !== "T") return;
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.repeat) return;
    const target = event.target as Element | null;
    if (target?.closest?.("input, textarea, select, [contenteditable]")) return;
    flip();
  });
}
