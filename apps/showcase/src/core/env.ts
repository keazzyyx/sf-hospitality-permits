// What the device can do and what the visitor has asked for. Every answer is cheap, cached where it cannot change,
// and safe to call on any page.

const REDUCED = "(prefers-reduced-motion: reduce)";

let webgl: boolean | null = null;

/** True when the browser can make a WebGL context (asked once, then remembered). */
export function hasWebGL(): boolean {
  if (webgl !== null) return webgl;
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    webgl = Boolean(gl);
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
  } catch {
    webgl = false;
  }
  return webgl;
}

/** True when the visitor asks for less motion. Read at the time of the call. */
export function reducedMotion(): boolean {
  try {
    return window.matchMedia(REDUCED).matches;
  } catch {
    return false;
  }
}

/** Call `cb` whenever the reduced-motion setting changes. Returns the function that stops it. */
export function onReducedMotionChange(cb: (reduced: boolean) => void): () => void {
  let mq: MediaQueryList;
  try {
    mq = window.matchMedia(REDUCED);
  } catch {
    return () => {};
  }
  const listener = (e: MediaQueryListEvent): void => cb(e.matches);
  mq.addEventListener("change", listener);
  return () => mq.removeEventListener("change", listener);
}

/** True when the main pointer is a finger (no hover, coarse aim). */
export function isTouch(): boolean {
  try {
    if (window.matchMedia("(hover: none) and (pointer: coarse)").matches) return true;
    return navigator.maxTouchPoints > 0 && !window.matchMedia("(any-pointer: fine)").matches;
  } catch {
    return false;
  }
}

export interface PowerHints {
  cores: number | null;
  memoryGb: number | null;
  saveData: boolean;
  reducedMotion: boolean;
  touch: boolean;
  webgl: boolean;
}

/** The signals behind lowPower(), for a prototype that wants to decide for itself. */
export function powerHints(): PowerHints {
  const nav = navigator as Navigator & { deviceMemory?: number; connection?: { saveData?: boolean } };
  return {
    cores: typeof nav.hardwareConcurrency === "number" ? nav.hardwareConcurrency : null,
    memoryGb: typeof nav.deviceMemory === "number" ? nav.deviceMemory : null,
    saveData: Boolean(nav.connection?.saveData),
    reducedMotion: reducedMotion(),
    touch: isTouch(),
    webgl: hasWebGL(),
  };
}

/**
 * A guess that heavy scenes should be dialled down: no WebGL, data saver on, four cores or fewer, 4 GB of memory
 * or less, or a phone with six cores or fewer. A heuristic, not a measurement: a prototype should still watch its
 * own frame times.
 */
export function lowPower(): boolean {
  const h = powerHints();
  if (!h.webgl || h.saveData) return true;
  if (h.cores !== null && h.cores <= 4) return true;
  if (h.memoryGb !== null && h.memoryGb <= 4) return true;
  return h.touch && h.cores !== null && h.cores <= 6;
}
