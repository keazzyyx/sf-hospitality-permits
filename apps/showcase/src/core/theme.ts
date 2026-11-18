// Two themes, "paper" (light) and "blueprint" (dark), set by data-theme on <html>. The default follows the
// system; a choice made with the flip button is remembered. The small inline script in each page's <head> applies
// the same rule before first paint, so there is no flash.

export type Theme = "paper" | "blueprint";

const KEY = "showcase:theme";
const DARK = "(prefers-color-scheme: dark)";
const NS = "http://www.w3.org/2000/svg";

const isTheme = (x: unknown): x is Theme => x === "paper" || x === "blueprint";

/** The theme the system asks for. */
export function systemTheme(): Theme {
  try {
    return window.matchMedia(DARK).matches ? "blueprint" : "paper";
  } catch {
    return "paper";
  }
}

/** The remembered choice, or null when the visitor has not made one. */
export function storedTheme(): Theme | null {
  try {
    const t = window.localStorage.getItem(KEY);
    return isTheme(t) ? t : null;
  } catch {
    return null;
  }
}

/** The theme on the page now. */
export function getTheme(): Theme {
  const t = document.documentElement.dataset.theme;
  return isTheme(t) ? t : (storedTheme() ?? systemTheme());
}

/** The ground colour of each theme (--paper in tokens.css), for the browser's own chrome. */
const GROUND: Record<Theme, string> = { paper: "#f2ede1", blueprint: "#0a0f1f" };

function apply(theme: Theme): void {
  const changed = document.documentElement.dataset.theme !== theme;
  document.documentElement.dataset.theme = theme;
  // <meta name="theme-color">: the phone browser's bar takes the ground of the theme in use, not the system's
  for (const meta of document.querySelectorAll('meta[name="theme-color"]')) meta.setAttribute("content", GROUND[theme]);
  if (changed) window.dispatchEvent(new CustomEvent<{ theme: Theme }>("themechange", { detail: { theme } }));
}

/** Set the theme. It is remembered unless `persist` is false. Dispatches "themechange" on window when it changes. */
export function setTheme(theme: Theme, { persist = true }: { persist?: boolean } = {}): void {
  if (persist) {
    try {
      window.localStorage.setItem(KEY, theme);
    } catch {
      // storage blocked: the choice lasts for this page
    }
  }
  apply(theme);
}

/** Flip to the other theme and remember it. Returns the new theme. */
export function toggleTheme(): Theme {
  const next: Theme = getTheme() === "paper" ? "blueprint" : "paper";
  setTheme(next);
  return next;
}

/** Forget the remembered choice and follow the system again. */
export function clearTheme(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // nothing stored
  }
  apply(systemTheme());
}

/** Call `cb` on every theme change. Returns the function that stops it. */
export function onThemeChange(cb: (theme: Theme) => void): () => void {
  const listener = (e: Event): void => cb((e as CustomEvent<{ theme: Theme }>).detail.theme);
  window.addEventListener("themechange", listener);
  return () => window.removeEventListener("themechange", listener);
}

let started = false;

/** Apply the remembered or system theme, and keep following the system while no choice is remembered. */
export function initTheme(): Theme {
  apply(storedTheme() ?? systemTheme());
  if (!started) {
    started = true;
    try {
      window.matchMedia(DARK).addEventListener("change", () => {
        if (!storedTheme()) apply(systemTheme());
      });
    } catch {
      // no matchMedia: the theme stays as set
    }
  }
  return getTheme();
}

/** The flip button: a half-filled circle that turns over. One per page is enough (the shell adds it top right). */
export function createThemeFlip(): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "theme-flip";

  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 20 20");
  svg.setAttribute("width", "20");
  svg.setAttribute("height", "20");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const ring = document.createElementNS(NS, "circle");
  ring.setAttribute("cx", "10");
  ring.setAttribute("cy", "10");
  ring.setAttribute("r", "8.25");
  ring.setAttribute("fill", "none");
  ring.setAttribute("stroke", "currentColor");
  ring.setAttribute("stroke-width", "1.5");
  const half = document.createElementNS(NS, "path");
  half.setAttribute("d", "M10 1.75a8.25 8.25 0 0 0 0 16.5z");
  half.setAttribute("fill", "currentColor");
  svg.append(ring, half);
  button.append(svg);

  const sync = (theme: Theme): void => {
    const other = theme === "paper" ? "blueprint" : "paper";
    button.setAttribute("aria-label", `Switch to the ${other} theme`);
    button.title = `Switch to the ${other} theme`;
    button.dataset.theme = theme;
  };
  sync(getTheme());
  onThemeChange(sync);
  button.addEventListener("click", () => toggleTheme());
  return button;
}
