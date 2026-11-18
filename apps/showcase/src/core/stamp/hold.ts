// Press and hold, as one progress value. A pointer held anywhere on the target, or Space / Enter held on the
// button, charges from 0 to 1 over `duration`. Letting go early cancels (pressing again within `resume` ms picks
// up most of the progress). Holding is never the only way: a single key press on the button, a quick click on
// it, or a click that came from no pointer at all (a screen reader, a script) is a "tap", for the caller to treat
// as the whole act. A key that is still down when the hold completes is swallowed until it comes up, so its
// repeats never reach whatever takes the focus next.

export type HoldSource = "pointer" | "key";

/** A point in client (viewport) coordinates. */
export interface HoldPoint {
  x: number;
  y: number;
}

export interface HoldStart {
  source: HoldSource;
  /** Where the pointer went down; null for a key. */
  point: HoldPoint | null;
  /** The progress the hold starts from (more than 0 when it resumes an abandoned one). */
  progress: number;
}

export interface HoldCancel {
  source: HoldSource;
  /** How far the hold had got, 0 to 1. */
  progress: number;
  /** How many holds have been abandoned so far, this one included. */
  count: number;
}

export interface HoldOptions {
  /** Milliseconds from nothing to complete. Default 1200. */
  duration?: number;
  /** A press within this many milliseconds of letting go resumes; the kept progress drains over it. Default 500. */
  resume?: number;
  /** A press on the button shorter than this is a tap. Default 250 ms. */
  tap?: number;
  /** The real <button>: keys held on it charge, and a tap or a click on it is reported by onTap. */
  button?: HTMLElement | null;
  /** Also charge while Space is held with nothing focused that would use the key. Default false. */
  globalSpace?: boolean;
  /** A selector for things inside the target a press must leave alone (links, other buttons). */
  ignore?: string;
  /** Asked before every start: return false to refuse (while something else is playing). */
  enabled?: () => boolean;
  onStart?: (e: HoldStart) => void;
  /** Called on every animation frame of a hold with the progress, 0 to 1. */
  onProgress?: (progress: number) => void;
  /** The hold reached 1 (the press may still be down). */
  onComplete?: (e: { source: HoldSource; point: HoldPoint | null }) => void;
  /** Let go early. */
  onCancel?: (e: HoldCancel) => void;
  /** A single press that was never a hold: do the whole act at once. */
  onTap?: (e: { source: HoldSource }) => void;
}

export interface Hold {
  /** The progress now, 0 to 1. */
  readonly progress: number;
  /** True while a press is charging. */
  readonly active: boolean;
  /** True while the key that completed a hold is still down (its repeats are being swallowed). */
  readonly keyHeld: boolean;
  /** Abandon the hold in progress, if any, without the cancel callback. */
  abort(): void;
  /** Make it usable again after it completed or was tapped (for a replay). */
  reset(): void;
  /** Remove every listener. */
  destroy(): void;
}

const TYPING = /^(INPUT|TEXTAREA|SELECT|BUTTON|A|SUMMARY)$/;

export function createHold(target: HTMLElement, options: HoldOptions = {}): Hold {
  const duration = options.duration ?? 1200;
  const resume = options.resume ?? 500;
  const tapMs = options.tap ?? 250;
  const button = options.button ?? null;
  const abort = new AbortController();
  const { signal } = abort;

  let active = false;
  let done = false;
  let source: HoldSource = "pointer";
  let point: HoldPoint | null = null;
  let viaButton = false;
  let startedAt = 0;
  /** When the key that started a press on the button went down, by the event's own clock (0: not a key press). A
   *  tap is told from a hold by the time between the key's events, not by when they were handled: on a busy page
   *  a quick press can be handled late, and must not read as a hold let go early. */
  let pressedAt = 0;
  let base = 0;
  let progress = 0;
  let frame = 0;
  let releasedAt = -Infinity;
  let releasedProgress = 0;
  let cancels = 0;
  let pointerId = -1;
  let key: string | null = null;
  /** The key itself (" " or "Enter") that started the hold in progress. */
  let downKey = " ";
  /** The click the browser sends after a pointer press on the button: already dealt with. */
  let swallowClick = 0;
  /** The key (" " or "Enter") that completed a hold and has not come up yet. */
  let held: string | null = null;

  // A hold completed by a key usually ends with the focus going somewhere else (a search field) while the key is
  // still down. Until it comes up, its repeats (and the other hold key) are swallowed before anything sees them.
  const swallow = (event: KeyboardEvent): void => {
    if (held === null) return;
    if (event.key !== " " && event.key !== "Enter") return;
    event.preventDefault();
    event.stopImmediatePropagation();
  };
  const unguard = (event?: KeyboardEvent): void => {
    if (held === null) return;
    if (event && event.key !== held) {
      // the other hold key coming up is swallowed too; the guard stays until the held one is released
      if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
      return;
    }
    if (event) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
    held = null;
    key = null;
    window.removeEventListener("keydown", swallow, true);
    window.removeEventListener("keypress", swallow, true);
    window.removeEventListener("keyup", unguard, true);
    window.removeEventListener("blur", onGuardBlur);
  };
  const onGuardBlur = (): void => unguard();
  const guard = (which: string): void => {
    if (held !== null) return;
    held = which;
    window.addEventListener("keydown", swallow, true);
    window.addEventListener("keypress", swallow, true);
    window.addEventListener("keyup", unguard, true);
    window.addEventListener("blur", onGuardBlur);
  };

  function begin(from: HoldSource, at: HoldPoint | null, onButton: boolean): boolean {
    if (active || done || options.enabled?.() === false) return false;
    const now = performance.now();
    const since = now - releasedAt;
    base = since >= 0 && since < resume ? releasedProgress * (1 - since / resume) : 0;
    releasedAt = -Infinity;
    active = true;
    source = from;
    point = at;
    viaButton = onButton;
    startedAt = now;
    pressedAt = 0;
    progress = base;
    options.onStart?.({ source, point, progress });
    frame = requestAnimationFrame(tick);
    return true;
  }

  function tick(now: number): void {
    if (!active) return;
    progress = Math.min(1, base + (now - startedAt) / duration);
    options.onProgress?.(progress);
    if (progress >= 1) {
      active = false;
      done = true;
      letGoOfPointer();
      // the key is still down: nothing else gets to see it until it comes up
      if (source === "key" && key !== null) guard(downKey);
      options.onComplete?.({ source, point });
      return;
    }
    frame = requestAnimationFrame(tick);
  }

  function letGoOfPointer(): void {
    if (pointerId < 0) return;
    try {
      target.releasePointerCapture(pointerId);
    } catch {
      // already released
    }
    pointerId = -1;
  }

  /** The press ended before the hold was complete. */
  function end(tapAllowed: boolean, upAt?: number): void {
    if (!active) return;
    active = false;
    cancelAnimationFrame(frame);
    const now = performance.now();
    const held = upAt !== undefined && pressedAt > 0 ? upAt - pressedAt : now - startedAt;
    if (tapAllowed && viaButton && held < tapMs) {
      done = true;
      progress = 0;
      options.onTap?.({ source });
      return;
    }
    releasedAt = now;
    releasedProgress = progress;
    cancels += 1;
    const at = progress;
    progress = 0;
    options.onCancel?.({ source, progress: at, count: cancels });
  }

  // ---- pointer -------------------------------------------------------------------------------------------------
  target.addEventListener(
    "pointerdown",
    event => {
      if (!event.isPrimary) {
        // a second finger: the visitor is pinching, not pressing. The hold is let go, and the browser has the gesture
        if (active && source === "pointer") {
          letGoOfPointer();
          end(false);
        }
        return;
      }
      if (event.pointerType === "mouse" && event.button !== 0) return;
      const el = event.target as Element | null;
      const onButton = Boolean(button && el && button.contains(el));
      if (!onButton && options.ignore && el?.closest(options.ignore)) return;
      // a press on the desk must not select text or start a drag; the button keeps its focus
      if (!onButton) event.preventDefault();
      if (!begin("pointer", { x: event.clientX, y: event.clientY }, onButton)) return;
      pointerId = event.pointerId;
      try {
        target.setPointerCapture(pointerId);
      } catch {
        // a pointer that cannot be captured still ends with pointerup on the window
      }
    },
    { signal },
  );
  const onPointerEnd = (event: PointerEvent, cancelled: boolean): void => {
    if (event.pointerId !== pointerId) return;
    const wasButton = viaButton;
    letGoOfPointer();
    if (!active) {
      // the hold completed while the press was down: the click that follows on the button is not a tap
      if (wasButton && !cancelled) swallowClick = performance.now();
      return;
    }
    if (wasButton && !cancelled) swallowClick = performance.now();
    end(!cancelled);
  };
  target.addEventListener("pointerup", event => onPointerEnd(event, false), { signal });
  target.addEventListener("pointercancel", event => onPointerEnd(event, true), { signal });
  window.addEventListener("pointerup", event => onPointerEnd(event, false), { signal });
  // a long press on a touch screen must not open the menu in the middle of a hold
  target.addEventListener(
    "contextmenu",
    event => {
      if (active && source === "pointer") event.preventDefault();
    },
    { signal },
  );

  // ---- the button: keys, and clicks that came from no pointer ----------------------------------------------------
  const isHoldKey = (event: KeyboardEvent): boolean =>
    (event.key === " " || event.key === "Enter") && !event.metaKey && !event.ctrlKey && !event.altKey;

  if (button) {
    button.addEventListener(
      "keydown",
      event => {
        if (!isHoldKey(event)) return;
        // the key is ours: no click on keydown (Enter) or keyup (Space), no page scroll
        event.preventDefault();
        if (event.repeat || key !== null) return;
        if (begin("key", null, true)) {
          key = event.key;
          downKey = event.key;
          pressedAt = event.timeStamp;
        }
      },
      { signal },
    );
    button.addEventListener(
      "keyup",
      event => {
        if (!isHoldKey(event)) return;
        event.preventDefault();
        if (event.key !== key) return;
        key = null;
        end(true, event.timeStamp);
      },
      { signal },
    );
    button.addEventListener(
      "blur",
      () => {
        if (key === null) return;
        key = null;
        end(false);
      },
      { signal },
    );
    button.addEventListener(
      "click",
      event => {
        if (performance.now() - swallowClick < 400) {
          swallowClick = 0;
          return;
        }
        if (active || done || options.enabled?.() === false) return;
        // a click with no press before it: a screen reader's activation, or a script
        event.preventDefault();
        done = true;
        options.onTap?.({ source: "key" });
      },
      { signal },
    );
  }

  if (options.globalSpace) {
    document.addEventListener(
      "keydown",
      event => {
        if (event.key !== " " || event.metaKey || event.ctrlKey || event.altKey || event.defaultPrevented) return;
        const el = event.target as HTMLElement | null;
        if (el && (el.isContentEditable || TYPING.test(el.tagName))) return;
        if (options.enabled?.() === false && !active) return;
        event.preventDefault();
        if (event.repeat || key !== null) return;
        if (begin("key", null, false)) {
          key = "global";
          downKey = " ";
        }
      },
      { signal },
    );
    document.addEventListener(
      "keyup",
      event => {
        if (event.key !== " " || key !== "global") return;
        key = null;
        end(false);
      },
      { signal },
    );
  }

  // leaving the page in the middle of a hold lets go of it
  const drop = (): void => {
    key = null;
    letGoOfPointer();
    end(false);
  };
  window.addEventListener("blur", drop, { signal });
  document.addEventListener("visibilitychange", () => document.hidden && drop(), { signal });

  return {
    get progress() {
      return progress;
    },
    get active() {
      return active;
    },
    get keyHeld() {
      return held !== null;
    },
    abort() {
      if (!active) return;
      active = false;
      cancelAnimationFrame(frame);
      letGoOfPointer();
      key = null;
      progress = 0;
      releasedAt = -Infinity;
    },
    reset() {
      done = false;
      progress = 0;
      releasedAt = -Infinity;
      cancels = 0;
    },
    destroy() {
      active = false;
      cancelAnimationFrame(frame);
      letGoOfPointer();
      abort.abort();
      // a key that is still down stays swallowed until it comes up, even after the hold has gone
    },
  };
}
