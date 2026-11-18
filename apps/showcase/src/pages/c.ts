// The front page ("the living grid"; the public site's index.html). San Francisco's street grid is the ground of
// the whole page: the stamp gate opens on it, the story is flown over it, and the search sits beside it. This entry
// paints the shell, the gate's sheet, the story's bones and the search as plain DOM, then loads the 3D scene and the
// gate. One state at a time owns the camera: gate, then story, then search; "Skip to search" goes straight to the
// search from any of them. A returning visit or a link that carries a search opens on the search alone: the story
// is put away (not scrolled past), and the seal or "See the story of one motion" brings the gate and the story back.

import "../core/stamp/stamp.css";
import "../c/c.css";
import { STATE_KEYS, cardTarget, hashFromState, stateFromHash } from "@conditions/search";
import { setPageTitle } from "../core/brand";
import { isTouch, onReducedMotionChange, reducedMotion } from "../core/env";
import { coveragePage, dataUrl, motionsUrl, streetsUrl } from "../core/paths";
import { SITE } from "../core/site";
import { loadConditions, mountSearch, type SearchDataDetail } from "../core/search";
import { mountShell } from "../core/shell";
import { renderMark } from "../core/stamp/mark";
import { onThemeChange, setTheme, storedTheme } from "../core/theme";
import { hasVisited, markVisited } from "../core/visitor";
import { loadMotions, loadStreets } from "../core/world/data";
import { unproject } from "../core/world/projection";
import { TOTALS } from "../c/content";
import { installFlip } from "../c/flip";
import { webglKind } from "../c/gpu";
import type { Gate } from "../c/gate";
import { createHud } from "../c/hud";
import { cityOutline, gatePose, measureView, SHEET_H, SHEET_W, sheetCorners, sheetWidthPx, type View } from "../c/poses";
import { matrix3d, projector, quadHomography, type Homography } from "../c/project";
import type { Scene } from "../c/scene";
import { buildGate, sheetHomography, type GateDom } from "../c/sheet";
import { BAND_CAPTION, mountStory, type Eye } from "../c/story";
import type { Flat } from "../c/flat";

setPageTitle("Conditions of approval");
document.body.classList.add("page-c");
try {
  history.scrollRestoration = "manual";
} catch {
  // an old browser: the page still opens where the state says
}

const params = new URLSearchParams(location.search);
/** ?gate=1 always shows the gate; ?nowebgl=1 draws the map without WebGL; ?webgl=1 uses WebGL even where it is
 *  drawn in software (a machine with no graphics card: the living grid would be a slide show there, so the drawn
 *  map stands in unless asked). */
const forced = params.get("gate") === "1";
/** Asked once, after the first paint (the probe makes a WebGL context of its own). */
let webglAnswer: boolean | undefined;
const webgl = (): boolean => {
  if (webglAnswer === undefined) {
    const kind = params.get("nowebgl") === "1" ? null : webglKind();
    webglAnswer = kind === "hardware" || (kind === "software" && params.get("webgl") === "1");
  }
  return webglAnswer;
};
const reduced = reducedMotion();
const touch = isTouch();
/** The system's setting for motion, as it is now (it can change while the page is open). */
let reducedNow = reduced;
/** The visitor paused the page's motion (the button by the theme flip; remembered in this browser). */
const MOTION_KEY = "showcase:c-motion";
let paused = ((): boolean => {
  try {
    return localStorage.getItem(MOTION_KEY) === "paused";
  } catch {
    return false;
  }
})();
/** No motion of the page's own: the system asks for less, or the visitor paused it. */
const still = (): boolean => reducedNow || paused;
/** This page's own gate: stamping A's gate does not skip this one. */
const VISIT = "c-gate";

/** A link that carries a search (any of the search's own keys, or a card) goes straight to it; so does the skip
 *  link's own address (#search: a middle click on it opens that). */
function carriesSearch(hash: string): boolean {
  if (hash === "#search") return true;
  const state = stateFromHash(hash);
  return STATE_KEYS.some(key => state[key] !== "") || cardTarget(hash) !== null;
}

const shell = mountShell({ current: "c", skip: { href: "#search", onActivate: () => enterSearch(true) } });
// blueprint is this page's own ground, until the visitor chooses otherwise
if (!storedTheme()) setTheme("blueprint", { persist: false });
const skip = shell.header.querySelector<HTMLElement>(".shell-skip");
const root = document.documentElement;
// the skip link's own address has done its work once the page is open: the search state is the hash's to carry
const openedOnSkip = location.hash === "#search";
if (openedOnSkip) {
  try {
    history.replaceState(history.state, "", location.pathname + location.search);
  } catch {
    // a sandboxed page: the hash stays, harmlessly
  }
}

/** The page's one status line for a screen reader: it outlives the gate (whose last words would go with it). */
const status = document.createElement("p");
status.className = "vh c-status";
status.setAttribute("role", "status");
status.setAttribute("aria-live", "polite");
document.body.append(status);

let view: View = measureView(shell.header.offsetHeight);
root.style.setProperty("--c-head", `${view.top}px`);
/** Below this many CSS pixels under the header the scrolled story cannot hold its text (a page zoomed to 200% or
 *  more, a phone on its side): its chapters are laid out as plain sections, and the map shows only at the gate. */
const FLOW_H = 480;
const isShort = (v: View): boolean => v.h - v.top < FLOW_H;

// ---- the world's canvas and what is written over it ------------------------------------------------------------------
const canvas = document.createElement("canvas");
canvas.className = "c-world";
canvas.setAttribute("aria-hidden", "true");
const hud = createHud();
document.body.prepend(canvas, hud.root);

// the data: the search's, and the map's two small files. A visitor who opens straight on the search (a link, a
// return) waits for none of the map: its files are asked for once the search's own data is in.
const data = loadConditions(dataUrl());
let startMapData: () => void = () => {};
const mapWanted = new Promise<void>(resolve => (startMapData = resolve));
const streets = mapWanted.then(() => loadStreets(streetsUrl()));
const motions = mapWanted.then(() => loadMotions(motionsUrl()));
// (a failure is shown by whatever draws the map; nothing is left unhandled)
streets.catch(() => {});
motions.catch(() => {});

let scene: Scene | null = null;
let flat: Flat | null = null;
/** Whatever draws the map, as the story's labels see it. */
let eye: Eye | null = null;
let gateDom: GateDom | null = null;
let gate: Gate | null = null;
let corners: { x: number; z: number }[] = [];
let homography: Homography | null = null;
/** Bumped every time the gate goes up or comes down, so a chunk that arrives late knows it is not wanted. */
let round = 0;
let mode: "gate" | "story" | "search" = "story";
/** True while the story is put away. */
let away = false;
/** No map at all: a phone opened on the search alone shows the search first and loads no map. */
let mapless = false;
/** The story laid out as plain sections (a short window: isShort). */
let flow = false;
/** The map's files could not be had: the page reads without a map (and says so once, quietly). */
let mapFailed = false;
let stamped = hasVisited(VISIT);
let lit: ReadonlySet<string> | null = null;
let pointer: { x: number; y: number; free: boolean } | null = null;
let hoverCard: HTMLElement | null = null;
let hoverIndex = -1;
let cursorIsPointer = false;
/** The route along the streets, once the story has worked it out (the drawn map may arrive after it). */
let routePoints: Float32Array | null = null;
/** Where the visitor was when the seal replayed the gate (Escape takes them back), or null. */
let returnTo: number | null = null;  // -1: the search alone
/** The search panel's right edge, where a card's hairline starts: measured when the layout changes. */
let cardEdge = 0;
/** The motion the label under the pointer names, and where the pointer was: a click there searches that one. */
let named: { record: string; x: number; y: number } | null = null;

// the page's one h1, first in the main region: the site's name (the wordmark on the screen waits for the name)
const pageHeading = document.createElement("h1");
pageHeading.className = "vh";
pageHeading.textContent = SITE?.name ?? "SF Conditions Search";
shell.main.prepend(pageHeading);

// ---- the story, then the search under it ------------------------------------------------------------------------------
const story = mountStory({
  main: shell.main,
  view: () => view,
  reduced: still(),
  eye: () => eye,
  onRoute: points => {
    routePoints = points;
    flat?.setRoute(points);
  },
  streets,
  stamped: () => stamped,
  onEnded(ended) {
    if (mode === "gate") return;
    setMode(ended ? "search" : "story");
  },
  onRailLeft() {
    focusField();
  },
  onFocusLeft() {
    // After a touch, focus the search panel, not its field: a field focused without a tap would raise a phone's keyboard.
    if (lastInputWasTouch) {
      searchRoot.tabIndex = -1;
      searchRoot.focus({ preventScroll: true });
    } else focusField();
  },
  onChapter(chapter, phase, pose) {
    // the drawn map (no WebGL) is redrawn where each chapter rests
    if (flat && (phase === "hold" || chapter === 8)) {
      flat.draw({ ...pose }, chapter >= 7, chapter === 3 ? 1 : 0, chapter >= 4 && chapter <= 6);
      story.place();
      afterFlat();
    }
  },
});

const section = document.createElement("section");
section.className = "c-search";
section.setAttribute("aria-label", "The search");
const panel = document.createElement("div");
panel.className = "c-search__panel c-opaque";
// with the story put away (a returning visit, a link), one line says it is there and brings it back
const replay = document.createElement("p");
replay.className = "c-replay data";
const replayButton = document.createElement("button");
replayButton.type = "button";
replayButton.className = "c-replay__button";
replayButton.textContent = "See the story of one motion, from the stamp";
replay.append(replayButton);
const searchRoot = document.createElement("div");
searchRoot.id = "search";
panel.append(replay, searchRoot);
section.append(panel);
shell.main.append(section);

searchRoot.addEventListener("cs:data", event => shell.setFacts((event as CustomEvent<SearchDataDetail>).detail.data));
// a search that arrives in the address while the gate or the story is showing (a link opened in this tab, the back
// button) opens the search. Registered before the search's own listener, so the search then applies the state and
// scrolls to a linked card in the page as it will be.
window.addEventListener("hashchange", () => {
  if (carriesSearch(location.hash) && (gateDom || mode !== "search")) enterSearch(false);
});
const search = mountSearch(searchRoot, {
  data,
  // (the page's own h1 names the site, before the story: the search's heading is the next level down)
  headingLevel: 2,
  // the public site's data carries its motion links as the build wrote them; the local pages link the public store
  ...(SITE ? { pdfBase: "" } : {}),
  // no single-key shortcut on this page (WCAG 2.1.4): "Skip to search" is the way there
  slashKey: false,
  coverageHref: coveragePage(),
  // the public site: every card's "Wrong or missing? Tell me" emails the site's contact address
  feedbackTo: SITE?.contact ?? "",
  onResults(hits, state) {
    // a search in use lights the motions it matches; no search lights none in particular (the kind of condition
    // shown counts: the map says what the count line says)
    const inUse = STATE_KEYS.some(key => state[key] !== "");
    if (!inUse) {
      lit = null;
      if (!mapFailed) hud.setCaption(`<b>${TOTALS.motions}</b> motions · taller means more conditions`);
    } else {
      const records = new Set<string>();
      for (const hit of hits) records.add(hit.record);
      lit = records;
      // (no map, no caption over it: what failed to load is not written over by a count)
      if (!mapFailed) hud.setCaption(`<b>${records.size}</b> of ${TOTALS.motions} motions match`);
    }
    // the map follows at the next animation frame: typing never waits for it
    scene?.setLit(lit);
    flat?.setLit(lit);
  },
});
/** Whether the visitor's last input was a touch (pointer or touch event), not a key, mouse or pen. */
let lastInputWasTouch = false;
addEventListener("pointerdown", e => (lastInputWasTouch = e.pointerType === "touch"), { capture: true, passive: true });
addEventListener("touchstart", () => (lastInputWasTouch = true), { capture: true, passive: true });
addEventListener("keydown", () => (lastInputWasTouch = false), { capture: true });
const focusField = (): void => {
  const input = searchRoot.querySelector<HTMLInputElement>('[data-cs-field="q"]');
  input?.focus({ preventScroll: true });
};
/** While the gate is up the search under it is not the visitor's business: its live regions keep quiet. */
function hushSearch(hush: boolean): void {
  for (const el of searchRoot.querySelectorAll<HTMLElement>('[role="status"], [aria-live]')) {
    if (hush) {
      if (el.dataset.cLive === undefined) el.dataset.cLive = el.getAttribute("aria-live") ?? "";
      el.setAttribute("aria-live", "off");
    } else if (el.dataset.cLive !== undefined) {
      if (el.dataset.cLive) el.setAttribute("aria-live", el.dataset.cLive);
      else el.removeAttribute("aria-live");
      delete el.dataset.cLive;
    }
  }
}

function layout(): void {
  cardEdge = panel.getBoundingClientRect().right;
  const lay = story.lay();
  root.style.setProperty("--c-head", `${view.top}px`);
  root.style.setProperty("--c-overlap", `${lay.overlap}px`);
  root.style.setProperty("--c-search-w", `${(mapFailed ? 0 : lay.searchFree.x) || view.w}px`);
  root.style.setProperty("--c-band", `${lay.searchFree.h}px`);
  placeHud();
  placeBand();
}
/** On a narrow window the map is a band over the search. It scrolls away with the page, as if it stood at the top
 *  of the search, and comes back with it: it never covers a line of the results (nor a focused link). */
let bandShift = -1;
let bandGone = false;
function placeBand(): void {
  const band = mode === "search" && !view.wide && !flow && !mapless && !mapFailed;
  const height = story.lay().searchFree.h + BAND_CAPTION;
  const rest = band ? story.story.scrollOf(story.story.timeline.length) : 0;
  const shift = band ? Math.round(Math.min(height, Math.max(0, window.scrollY - rest))) : 0;
  if (shift !== bandShift) {
    bandShift = shift;
    root.style.setProperty("--c-band-shift", `${shift}px`);
  }
  const gone = band && shift >= height;
  if (gone !== bandGone) {
    bandGone = gone;
    root.classList.toggle("c-band-gone", gone);
    syncVisible();
  }
}
window.addEventListener("scroll", placeBand, { passive: true });
/** The canvas is in the window (the scene's observer) and not scrolled away as a band: frames are drawn. */
let canvasInView = true;
function syncVisible(): void {
  scene?.setVisible(canvasInView && !bandGone);
}

function placeHud(): void {
  const lay = story.lay();
  const full = { x: 0, y: view.top, w: view.w, h: view.h - view.top };
  hud.setWindow(mode === "search" ? lay.searchFree : mode === "gate" ? full : lay.free, view.top, view.wide);
}
layout();
story.story.refresh();

// ---- the seal: a small copy of the mark by the wordmark, once the gate is down. Pressing it replays the opening ------
const seal = document.createElement("button");
seal.type = "button";
seal.className = "c-seal";
seal.hidden = true;
seal.setAttribute("aria-label", "Approved with conditions: stamp the motion again (replays the opening)");
seal.title = "Stamp the motion again";
renderMark(seal, { width: 66, wear: "light", seed: 7, label: "" });
seal.addEventListener("click", () => raise(true));
replayButton.addEventListener("click", () => raise(true));

// ---- the story put away: the page is the search alone (a returning visit, a link that carries a search) ----------------
function putAway(on: boolean): void {
  if (on === away) return;
  away = on;
  root.classList.toggle("c-direct", on);
  story.story.setCollapsed(away || flow);
  layout();
}
/** Into the plain layout or out of it, keeping the visitor's place: the chapter they were reading, or the search. */
function setFlow(on: boolean): void {
  if (on === flow) return;
  // where the visitor is: in the plain layout, by what is at the top of the window
  let inSearch = mode === "search";
  let chapter = story.state.chapter;
  if (flow) {
    inSearch = section.getBoundingClientRect().top < window.innerHeight / 2;
    chapter = 0;
    for (let i = 1; i < story.story.timeline.chapters.length - 1; i++) if (story.flowTop(i) <= window.scrollY + view.top + 8) chapter = i;
  }
  flow = on;
  root.classList.toggle("c-flow", on);
  story.setFlow(on);
  story.story.setCollapsed(away || flow);
  layout();
  if (gateDom) return;
  if (on) {
    if (inSearch) section.scrollIntoView({ block: "start" });
    else window.scrollTo({ top: Math.max(0, story.flowTop(chapter) - view.top), behavior: "instant" as ScrollBehavior });
    setMode("search");
  } else if (inSearch && !away) story.story.toEnd();
  else if (!away) story.story.goTo(Math.min(chapter, story.story.timeline.chapters.length - 1), { instant: true });
}
function setMapless(on: boolean): void {
  mapless = on;
  root.classList.toggle("c-mapless", on);
  if (!on) startMapData();
  placeBand();
}
shell.header.querySelector(".mark-link")?.after(seal);

// ---- the three states -------------------------------------------------------------------------------------------------
const FULL = { drift: 1, tilt: 1, bulge: 1, rings: 1 };
/** At the gate the stamp hangs over the middle of the dome: the dome is wide enough to show round it. */
const GATE_DOME = 2.7;

function setMode(next: "gate" | "story" | "search"): void {
  mode = next;
  hud.setMode(next);
  root.dataset.cMode = next;
  const band = next === "search" && !view.wide;
  canvas.classList.toggle("is-band", band);
  flat?.el.classList.toggle("is-band", band);
  hud.root.classList.toggle("is-band", band);
  // (in the plain layout the search is still below the story: the link to it stays in sight)
  skip?.classList.toggle("shell-skip--quiet", next === "search" && !flow);
  placeBand();
  // the search's map rests: no ring runs of itself there; one leaves from the matches when they change
  scene?.setSearch(next === "search");
  placeHud();
}

/** Lay the sheet's plane where the camera now sees its rectangle of ground. */
const quad = [{ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }];
const corner = { x: 0, y: 0, behind: false };
let laid = "";
function laySheet(): void {
  if (!gateDom) return;
  if (corners.length === 0) corners = sheetCorners(gatePose(view), view, sheetWidthPx(view));
  const live = scene;
  if (live) {
    // the sheet lies on the living ground: its corners ride whatever lifts or sinks it (no allocation per frame
    // beyond the matrix, and the style is written only when it has changed)
    for (let i = 0; i < 4; i++) {
      const c = corners[i]!;
      live.project(c.x, live.liftAt(c.x, c.z), c.z, corner);
      quad[i]!.x = Math.round(corner.x * 64) / 64;
      quad[i]!.y = Math.round(corner.y * 64) / 64;
    }
    homography = quadHomography(SHEET_W, SHEET_H, quad);
  } else homography = sheetHomography(view, corners, projector(gatePose(view), view.w, view.h));
  const next = matrix3d(homography);
  if (next !== laid) {
    laid = next;
    gateDom.plane.style.transform = next;
  }
}

/** Put the gate up (a first visit, ?gate=1, or the seal asking for a replay). */
function toTop(): void {
  // through the scroll engine, which tells its smoothing: a glide still running would write its own place back
  story.story.goToStop({ pos: 0, chapter: 0, step: -1 }, { instant: true });
  if (window.scrollY !== 0) window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
}

/** What the keyboard was on when the seal (or the line over the search) brought the gate back: Escape returns there. */
let opener: HTMLElement | null = null;
function raise(replay: boolean): void {
  if (gateDom) return;
  const mine = ++round;
  opener = replay && document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : null;
  // (-1: back to the search alone, where the visitor was)
  returnTo = replay ? (away ? -1 : window.scrollY) : null;
  putAway(false);
  setMapless(false);
  toTop();
  root.classList.add("c-gate-on");
  seal.hidden = true;
  story.setWaiting(true);
  // nothing behind the gate can take the focus (Shift+Tab would scroll the page to the footer under it; Tab past
  // the stamp would land in the search and take the gate down): the skip link is the one way past it
  shell.footer.inert = true;
  section.inert = true;
  hushSearch(true);
  setMode("gate");
  gateDom = buildGate(reducedNow, status);
  // before the map has arrived, the city's outline says where the ground is; the streets draw on inside it
  if (!scene && !flat) {
    gateDom.outline.setAttribute("viewBox", `0 0 ${view.w} ${view.h}`);
    gateDom.outline.firstElementChild?.setAttribute("d", cityOutline(gatePose(view), view));
  } else gateDom.outline.remove();
  shell.main.prepend(gateDom.root);
  corners = [];
  laid = "";
  laySheet();
  if (replay) gateDom.button.focus({ preventScroll: true });
  scene?.setTarget(gatePose(view), replay ? 1.1 : 0);
  scene?.setAlive(FULL);
  scene?.setDome(GATE_DOME);
  scene?.setHero(false, { instant: true });
  scene?.setWave(0, replay ? 0.5 : 0);
  scene?.setDim(0);
  // at the gate the map shows every motion alike, whatever the search holds
  scene?.setLit(null);
  flat?.setLit(null);
  flat?.setHero(false);
  if (flat) {
    flat.draw(gatePose(view), false, 0);
    afterFlat();
  }
  const dom = gateDom;
  // a press made before the gate's own script has arrived is kept, and the stamp does it on arrival
  let early = false;
  const keep = (event: Event): void => {
    if (event.type === "keydown" && !["Enter", " "].includes((event as KeyboardEvent).key)) return;
    early = true;
    dom.button.classList.add("is-pressed");
  };
  dom.button.addEventListener("click", keep);
  dom.button.addEventListener("keydown", keep);
  void import("../c/gate").then(module => {
    dom.button.removeEventListener("click", keep);
    dom.button.removeEventListener("keydown", keep);
    if (mine !== round || gateDom !== dom) return;
    gate = module.startGate({
      dom,
      top: () => view.top,
      homography: () => homography ?? [1, 0, 0, 0, 1, 0, 0, 0, 1],
      sheetRadius: () => (corners.length === 4 ? Math.hypot(corners[2]!.x - corners[0]!.x, corners[2]!.z - corners[0]!.z) / 2 : 3000),
      scene: () => scene,
      reduced: reducedNow,
      still,
      rest(resting) {
        // (only the map's own life rests: the lean and the dome under the pointer stay as they are)
        setResting(resting);
      },
      // (forced colours: the drawn stamp follows the system's colours; the 3D one cannot)
      webgl: webgl() && !matchMedia("(forced-colors: active)").matches,
      done() {
        stamped = true;
        lower(true);
      },
    });
    Object.assign(showcase, { gate });
    if (early) {
      dom.button.classList.remove("is-pressed");
      gate.stampNow();
    }
  }).catch(() => {
    // the gate's script could not be had: the story opens without it
    if (mine === round && gateDom === dom) lower(false);
  });
}

/** The gate comes down: the story owns the camera from here. */
function lower(byStamp: boolean): void {
  if (!gateDom) return;
  round += 1;
  const active = document.activeElement;
  // (the keyboard was on the gate's button: a pointer that stamped leaves nothing focused, and nothing is moved)
  const hadFocus = active !== null && gateDom.root.contains(active);
  gate?.destroy();
  gate = null;
  gateDom.root.remove();
  gateDom = null;
  root.classList.remove("c-gate-on");
  shell.footer.inert = false;
  section.inert = false;
  hushSearch(false);
  markVisited(VISIT);
  seal.hidden = false;
  // a stamp always opens the story at its start, wherever anything else left the page
  if (byStamp) toTop();
  // (in the plain layout the story is already over as far as the camera knows: the map's band is the search's)
  setMode(flow ? "search" : "story");
  scene?.setDome(1);
  if (byStamp && !still()) {
    story.root.classList.add("is-arriving");
    window.setTimeout(() => story.root.classList.remove("is-arriving"), 700);
  }
  story.setWaiting(false);
  scene?.setHero(true, { instant: !byStamp });
  scene?.setLit(lit);
  flat?.setLit(lit);
  flat?.setHero(true);
  scene?.setTarget(story.pose, byStamp ? 0.9 : 1.2);
  // the keyboard's place: the heading of the chapter now on screen (the button it was on has gone)
  if (byStamp && hadFocus) story.focusChapter();
}

/** Go to the search now, whatever is on screen (the skip link, a point clicked on the map). */
function enterSearch(focus: boolean): void {
  if (gateDom) lower(false);
  returnTo = null;
  story.story.toEnd();
  // (in the plain layout the search is the page below the story's sections: its top, and its field, come into view)
  if (flow && !away) {
    section.scrollIntoView({ block: "start" });
    searchRoot.querySelector('[data-cs-field="q"]')?.scrollIntoView({ block: "nearest" });
  }
  if (focus) focusField();
  // a browser that brings a focused field into view does so after this: the end of the story wins
  requestAnimationFrame(() => {
    if (mode !== "search") story.story.toEnd();
  });
}

// while the gate is up the page under it stays where it is: the wheel and the keys that would move the story
// (the scroll engine listens on the window) stop here
const MOVES = new Set(["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight", "PageDown", "PageUp", "Home", "End"]);
window.addEventListener(
  "keydown",
  event => {
    const inField = Boolean((event.target as Element | null)?.closest?.("input, select, textarea, [contenteditable]"));
    if (gateDom && MOVES.has(event.key) && !inField) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
    // Escape puts away a gate the seal brought back, and the visitor is where they were
    if (event.key === "Escape" && gateDom && returnTo !== null && (!gate || gate.state === "idle")) {
      event.preventDefault();
      const to = returnTo;
      const back = opener;
      opener = null;
      lower(false);
      // the keyboard goes back to what brought the gate up (the seal, or the line over the search)
      const refocus = (): void => {
        const shown = (el: HTMLElement | null): el is HTMLElement => el !== null && el.isConnected && !el.closest("[inert]") && el.getClientRects().length > 0;
        const target = [back, seal].find(shown);
        if (target) target.focus({ preventScroll: true });
        else story.focusChapter();
      };
      if (to === -1) {
        putAway(true);
        setMode("search");
        refocus();
        return;
      }
      if (to >= story.story.scrollOf(story.story.timeline.length) - 2) enterSearch(false);
      window.setTimeout(() => {
        window.scrollTo({ top: to, behavior: "instant" as ScrollBehavior });
        refocus();
      }, 0);
    }
  },
  { capture: true },
);
// a Space held down on the gate and carried into the search (Tab while holding) is not typed into the field
let spaceFromGate = false;
window.addEventListener(
  "keydown",
  event => {
    if (event.key !== " ") return;
    const inField = Boolean((event.target as Element | null)?.closest?.("input, textarea, [contenteditable]"));
    if (gateDom && !inField) spaceFromGate = true;
    else if (spaceFromGate && inField) event.preventDefault();
  },
  { capture: true },
);
window.addEventListener("keyup", event => {
  if (event.key === " ") spaceFromGate = false;
});
window.addEventListener("blur", () => (spaceFromGate = false));

// the page under the gate stays at its top, whatever tries to scroll it (a focused element brought into view)
window.addEventListener(
  "scroll",
  () => {
    if (gateDom && window.scrollY !== 0) toTop();
  },
  { passive: true },
);
window.addEventListener(
  "wheel",
  event => {
    if (gateDom) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  },
  { capture: true, passive: false },
);

// focus that reaches the search before it is open (Tab past the stamp or the rail, a screen reader) opens it
searchRoot.addEventListener("focusin", () => {
  if (gateDom || mode !== "search") enterSearch(false);
});

// ---- the pointer: the map answers it wherever nothing opaque is in the way ---------------------------------------------
const OPAQUE = ".c-opaque, .shell-head, .shell-foot";
const track = (event: PointerEvent): void => {
  const target = event.target as Element | null;
  const free = mode === "gate" || !target?.closest?.(OPAQUE);
  pointer = { x: event.clientX, y: event.clientY, free };
  scene?.setPointer(event.clientX, event.clientY, free);
  if (flat) afterFlat();
};
window.addEventListener("pointermove", track, { passive: true });
window.addEventListener("pointerdown", track, { passive: true });
const untrack = (event: PointerEvent): void => {
  if (event.pointerType !== "touch") return;
  pointer = null;
  scene?.setPointer(null);
};
window.addEventListener("pointerup", untrack, { passive: true });
window.addEventListener("pointercancel", untrack, { passive: true });
root.addEventListener("mouseleave", () => {
  pointer = null;
  scene?.setPointer(null);
});

// a point or a stack clicked on the map sets the search to that case number
window.addEventListener("click", event => {
  if (mode === "gate") return;
  const target = event.target as Element | null;
  if (target?.closest?.(`${OPAQUE}, a, button, input, select, label`)) return;
  const reach = touch ? 24 : 14;
  let record: string | null | undefined = null;
  // what the label says is what a click searches (the view may have leaned a hair since it was drawn)
  if (named && Math.hypot(named.x - event.clientX, named.y - event.clientY) < 3) record = named.record;
  else if (scene) {
    const index = scene.pick(event.clientX, event.clientY, reach);
    record = index >= 0 ? scene.motions[index]?.record : null;
  } else if (flat) record = flat.pick(event.clientX, event.clientY, reach);
  if (!record) return;
  // the case alone: filters set before would hide it ("0 conditions"); the hash carries the new state to the search
  location.hash = hashFromState({ q: record });
  if (mode !== "search") enterSearch(false);
});

// a result card under the pointer (or holding the focus) raises its motion's stack, and a hairline runs to it
function setHover(card: HTMLElement | null): void {
  if (card === hoverCard) return;
  hoverCard = card;
  const record = card?.dataset.record ?? "";
  hoverIndex = card && scene ? scene.motions.findIndex(m => m.record === record) : -1;
  scene?.hover(hoverIndex);
  flat?.hover(card ? record : null);
  if (hoverIndex < 0) hud.setWire(null);
  if (flat) afterFlat();
  else scene?.renderNow();
}

/** The drawn map does not move: what is tied to it is placed when it is drawn, and when the pointer or a card asks. */
function afterFlat(): void {
  if (!flat) return;
  const to = { x: 0, y: 0 };
  const record = hoverCard?.dataset.record ?? "";
  if (hoverCard && view.wide && hoverCard.isConnected && flat.topOf(record, to)) {
    const box = hoverCard.getBoundingClientRect();
    hud.setWire({ x: cardEdge, y: Math.min(view.h - 12, Math.max(view.top + 12, box.top + 30)) }, to, record);
  } else hud.setWire(null);
  const picked = mode !== "gate" && pointer !== null && pointer.free ? flat.pick(pointer.x, pointer.y, touch ? 24 : 14) : null;
  if (picked && !hoverCard && flat.topOf(picked, to) && pointer) {
    hud.setTag(picked, to.x, to.y);
    named = { record: picked, x: pointer.x, y: pointer.y };
  } else {
    hud.setTag(null);
    named = null;
  }
  setCursor(picked !== null);
}
function setCursor(want: boolean): void {
  if (want !== cursorIsPointer) {
    cursorIsPointer = want;
    root.style.cursor = want ? "pointer" : "";
  }
}
const cardOf = (target: EventTarget | null): HTMLElement | null => (target as Element | null)?.closest?.<HTMLElement>("[data-cs-card]") ?? null;
searchRoot.addEventListener("pointerover", event => {
  if (event.pointerType !== "touch") setHover(cardOf(event.target));
});
searchRoot.addEventListener("pointerleave", () => setHover(null));
searchRoot.addEventListener("focusin", event => setHover(cardOf(event.target)));
searchRoot.addEventListener("focusout", () => setHover(null));

// ---- after every frame of the scene: what is tied to the camera ---------------------------------------------------------
const spot = { x: 0, y: 0, behind: false };
function afterRender(): void {
  if (!scene) return;
  if (gateDom) {
    laySheet();
  }
  // the legend: north as the camera turns, the scale, and the place under the pointer while it is on the map
  const g = pointer && pointer.free && mode !== "gate" ? scene.groundAt(pointer.x, pointer.y) : null;
  if (g) {
    const ll = unproject(g.x, g.z);
    hud.setReadout(ll.lat, ll.lon);
  } else hud.setReadout(null, null);
  hud.setNorth(scene.pose.heading);
  hud.setScale(scene.metresPerPixel);
  // the hairline from a card to its stack, ending in a ring at the stack's top with its case number
  if (hoverCard && hoverIndex >= 0 && view.wide && hoverCard.isConnected) {
    const box = hoverCard.getBoundingClientRect();
    scene.topOf(hoverIndex, spot);
    const m = scene.motions[hoverIndex]!;
    hud.setWire({ x: cardEdge, y: Math.min(view.h - 12, Math.max(view.top + 12, box.top + 30)) }, spot, `${m.record} · ${m.year}`);
    hud.setTag(null);
    setCursor(false);
  } else {
    if (hoverCard && !hoverCard.isConnected) setHover(null);
    // the motion under the pointer, named: the very answer a click gets (not at the gate: the stamp is there)
    const under = mode !== "gate" && pointer !== null && pointer.free ? scene.pick(pointer.x, pointer.y, touch ? 24 : 14) : -1;
    if (under >= 0 && pointer) {
      const m = scene.motions[under]!;
      scene.topOf(under, spot);
      hud.setTag(`${m.record} · ${m.year}`, spot.x, spot.y);
      named = { record: m.record, x: pointer.x, y: pointer.y };
    } else {
      hud.setTag(null);
      named = null;
    }
    setCursor(under >= 0);
  }
  // a few matches are each named where they stand
  let k = 0;
  if (mode === "search" && lit && lit.size > 0 && lit.size <= 5 && !hoverCard) {
    for (const record of lit) {
      const i = scene.indexOf(record);
      if (i < 0) continue;
      scene.topOf(i, spot);
      if (!spot.behind) hud.setMark(k++, record, spot.x, spot.y);
    }
  }
  for (; k < 5; k++) hud.setMark(k, null);
  story.place();
}

// ---- the theme: the mark flips it, and the flip travels -----------------------------------------------------------------
const flipButton = shell.header.querySelector<HTMLElement>(".theme-flip");
if (flipButton) {
  installFlip({
    button: flipButton,
    onTheme(_theme, instant) {
      scene?.setTheme(instant);
      if (instant) scene?.renderNow();
    },
  });
}
// ---- left alone: after a while with no move, key, scroll or touch, the map's own life rests (the drift and the rings
// of the gate and of the two views of the whole city), and no frame is drawn until the visitor is back ------------------
const REST_MS = 25_000;
let lastInput = performance.now();
let restTimer = 0;
let restArmed = false;
let resting = false;
function setResting(on: boolean): void {
  resting = on;
  scene?.setResting(on);
}
function armRest(delay: number): void {
  restArmed = true;
  window.clearTimeout(restTimer);
  restTimer = window.setTimeout(() => {
    restArmed = false;
    const idle = performance.now() - lastInput;
    if (idle >= REST_MS - 50) setResting(true);
    else armRest(REST_MS - idle);
  }, delay);
}
const onInput = (): void => {
  lastInput = performance.now();
  if (resting) setResting(false);
  if (!restArmed) armRest(REST_MS);
};
for (const type of ["pointermove", "pointerdown", "keydown", "wheel", "touchstart", "scroll"]) window.addEventListener(type, onInput, { passive: true, capture: true });
armRest(REST_MS);

// ---- motion: the system's setting, or the visitor's own pause (WCAG 2.2.2: what moves of itself can be stopped) -----
const motionButton = document.createElement("button");
motionButton.type = "button";
motionButton.className = "c-pause";
motionButton.setAttribute("aria-label", "Pause motion");
motionButton.title = "Pause the map's motion";
{
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  // two bars while it moves (press to pause); a triangle while it is paused (press to let it move)
  const bars = document.createElementNS(NS, "path");
  bars.setAttribute("class", "c-pause__bars");
  bars.setAttribute("d", "M4.5 3v10M11.5 3v10");
  const play = document.createElementNS(NS, "path");
  play.setAttribute("class", "c-pause__play");
  play.setAttribute("d", "M5 3.2v9.6l8-4.8z");
  svg.append(bars, play);
  motionButton.append(svg);
}
(flipButton ?? shell.header.querySelector(".shell-head__inner")?.lastElementChild)?.before(motionButton);
function applyMotion(): void {
  const s = still();
  root.classList.toggle("c-still", s);
  motionButton.setAttribute("aria-pressed", String(paused));
  // (the system's own setting already holds everything still: the button has nothing to do then)
  motionButton.hidden = reducedNow;
  story.story.setMode(s ? "stills" : "scrub");
  scene?.setStill(s);
  // (a gate up now holds its stamp still too: drawn once on a change, its loop asleep)
  gate?.setStill();
}
motionButton.addEventListener("click", () => {
  paused = !paused;
  try {
    if (paused) localStorage.setItem(MOTION_KEY, "paused");
    else localStorage.removeItem(MOTION_KEY);
  } catch {
    // storage refused: the choice holds for this visit
  }
  applyMotion();
});
applyMotion();
// the system's setting for motion can change while the page is open: the story follows (stills, or scrubbed)
onReducedMotionChange(less => {
  reducedNow = less;
  applyMotion();
});
// a change from anywhere else (the system's setting) eases the canvas over
onThemeChange(() => scene?.setTheme(false));

// ---- size --------------------------------------------------------------------------------------------------------------
let sizeW = window.innerWidth, sizeH = window.innerHeight;
window.addEventListener("resize", () => {
  const w = window.innerWidth, h = window.innerHeight;
  if (w === sizeW && h === sizeH) return;
  // a phone's toolbars come and go: only a real change of size lays the page out again
  if (w === sizeW && Math.abs(h - sizeH) < 120 && touch) return;
  sizeW = w;
  sizeH = h;
  view = measureView(shell.header.offsetHeight);
  // a phone turned on its side has room for the map beside the search
  if (mapless && view.wide) setMapless(false);
  scene?.resize(view);
  flat?.resize(view);
  story.relayout();
  if (flat) afterFlat();
  layout();
  // a zoom in or out (it is a resize) can make the window too short for the scrolled story, or tall enough again
  setFlow(isShort(view));
  setMode(mode);
  if (gateDom) {
    corners = [];
    scene?.setTarget(gatePose(view));
    laySheet();
    gate?.relay();
    if (gateDom.outline.isConnected) {
      gateDom.outline.setAttribute("viewBox", `0 0 ${view.w} ${view.h}`);
      gateDom.outline.firstElementChild?.setAttribute("d", cityOutline(gatePose(view), view));
    }
  }
});

// for the console and the tests: window.showcase.search.setQuery("noise"), window.showcase.story.goTo(3)
const showcase: Record<string, unknown> = { shell, search, mountSearch, story: story.story, enterSearch, raise };
Object.assign(window, { showcase, __story: story.story });

// ---- where the page opens ---------------------------------------------------------------------------------------------
if (isShort(view)) setFlow(true);
const direct = !forced && (openedOnSkip || carriesSearch(location.hash) || hasVisited(VISIT));
if (direct) {
  putAway(true);
  story.setWaiting(false);
  seal.hidden = false;
  setMode("search");
  story.story.toEnd();
  // a phone opens on the search alone, with no map over it: the seal (or the line above the search) brings the
  // story and its map back
  if (!view.wide) setMapless(true);
  // the map waits for the search's data: on a slow link the search comes first
  const later = (): void => {
    const idle = (window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number }).requestIdleCallback;
    if (idle) idle(() => startMapData(), { timeout: 600 });
    else window.setTimeout(startMapData, 60);
  };
  if (!mapless) search.ready.then(later, later);
} else {
  raise(false);
  startMapData();
}

// ---- the map: after the first paint, as its own chunk -------------------------------------------------------------------
function startFlat(): void {
  void Promise.all([import("../c/flat"), streets, motions]).then(([module, streetData, motionData]) => {
    const made = module.mountFlat({ streets: streetData, motions: motionData, view });
    flat = made;
    eye = made.eye;
    if (routePoints) made.setRoute(routePoints);
    document.body.prepend(made.el);
    const c = story.state.chapter;
    if (mode !== "gate") made.draw({ ...story.pose }, c >= 7, c === 3 ? 1 : 0, c >= 4 && c <= 6);
    story.redraw();
    story.place();
    hud.root.classList.add("is-on", "c-hud--flat");
    Object.assign(showcase, { flat: made });
    flat.setLit(lit);
    flat.setHero(mode !== "gate");
    flat.el.classList.toggle("is-band", mode === "search" && !view.wide);
    requestAnimationFrame(() => flat?.el.classList.add("is-on"));
    gateDom?.outline.classList.add("is-gone");
  }).catch(() => {
    // not even the drawing could be had (the map's files did not arrive): the page reads without a map. No empty
    // panel is kept for it: the search takes the width (no band over it on a phone), and the story says, once, in
    // the place the map would have had, that it reads without one
    mapFailed = true;
    root.classList.add("c-map-failed");
    const note = document.createElement("p");
    note.className = "c-mapnote data";
    note.textContent = "The map could not be loaded. The story and the search read without it.";
    story.stage.append(note);
    gateDom?.outline.classList.add("is-gone");
    layout();
    setMode(mode);
  });
}
function startScene(): void {
  void Promise.all([import("../c/scene"), streets, motions])
    .then(([module, streetData, motionData]) => {
      const made = module.createScene({ canvas, streets: streetData, motions: motionData, view, reduced: still() });
      scene = made;
      eye = made;
      made.onRender(afterRender);
      // while the graphics card has taken the drawing away, nothing is written over an empty map
      canvas.addEventListener("webglcontextlost", () => root.classList.add("c-gl-lost"));
      canvas.addEventListener("webglcontextrestored", () => root.classList.remove("c-gl-lost"));
      if (mode === "gate") {
        made.setTarget(gatePose(view));
        made.setAlive(FULL);
        made.setDome(GATE_DOME);
        made.setWave(0);
      } else made.setHero(true, { instant: true });
      story.attach(made);
      if (mode !== "gate") made.setTarget(story.pose);
      made.setLit(lit);
      made.setSearch(mode === "search");
      if (pointer) made.setPointer(pointer.x, pointer.y, pointer.free);
      made.intro(true);
      made.setResting(resting);
      gateDom?.outline.classList.add("is-gone");
      canvas.classList.add("is-on");
      hud.root.classList.add("is-on");
      Object.assign(showcase, { scene: made });
      new IntersectionObserver(entries => {
        canvasInView = entries.some(e => e.isIntersecting);
        syncVisible();
      }).observe(canvas);
    })
    .catch(() => {
      // the map could not be drawn (no context, a failed download): the page still reads, on the drawn map
      canvas.remove();
      startFlat();
    });
}
// three.js is asked for once the first paint is on the screen (two frames on), and only once the map is wanted
void mapWanted.then(() =>
  requestAnimationFrame(() =>
    requestAnimationFrame(() =>
      setTimeout(() => {
        if (webgl()) startScene();
        else {
          canvas.remove();
          startFlat();
        }
      }, 0),
    ),
  ),
);
