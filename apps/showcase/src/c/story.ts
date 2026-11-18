// The story, flown over the grid: prototype B's nine chapters and scroll engine (core/story), told in the grid's
// own language. The text sits on a paper panel that slides in beside the map (below it on a phone); the map
// answers with lines, points, a route, a few drawn objects standing on the grid, and labels on paper plates.
// Everything is a function of the scroll position, so it runs backwards as well as forwards. No three.js here:
// whatever draws the map (the 3D scene, or the drawing made without WebGL) is driven through its own interface.

import "../core/stamp/stamp.css";
import { MARK_RATIO, renderMark } from "../core/stamp/mark";
import { createRail, createStory, ease, emptyPose, poseAt, range, type CameraKey, type Rail, type Story, type StoryState } from "../core/story";
import type { Streets } from "../core/world/data";
import { makeRoute, streetGraph, type Route } from "../core/world/graph";
import type { Pose } from "../core/world/rig";
import { CASE, chapterSpecs, CONDITIONS, FEATURED, LETTERS, num, PAGE, TEXT, TOTALS, VOTE } from "./content";
import { CASTLE, CASTLE_CORNER, castleGround, CITY_HALL_DOOR, CIVIC_GRID_DEG, HILL_GRID_DEG, hillAt, LETTER_ROWS, MARK_GROUND, offset, POLK_NORTH, POLK_SOUTH, SEATS, SLABS, STREET_NAMES } from "./places";
import { gatePose, searchPose, type View } from "./poses";
import { matrix3d, quadHomography } from "./project";

const RAD = Math.PI / 180;
const NS = "http://www.w3.org/2000/svg";

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Where things sit, in window pixels. */
export interface Lay {
  view: View;
  /** The story's text panel: its width when it stands beside the map, its height when it lies under it. */
  panelW: number;
  panelH: number;
  /** The strip of paper down the right-hand edge that carries the chapter rail (0 on a phone). */
  railW: number;
  /** The part of the window the map is seen in while a chapter's text is on screen. */
  free: Box;
  /** How far the picture moves aside when the panel comes in, as fractions of the window. */
  asideX: number;
  asideY: number;
  /** The part of the window the map keeps once the search is open. */
  searchFree: Box;
  /** How many pixels the search rises over the end of the story. */
  overlap: number;
}

/** The page's side gutter: the header, the story's text and the search all start here. */
export const GUTTER = 48;
/** Height of the caption's own row over the map's band on a phone. */
export const BAND_CAPTION = 30;

export function measureLay(view: View): Lay {
  const { w, h, top } = view;
  if (view.wide) {
    const panelW = Math.round(Math.min(520, Math.max(384, w * 0.35)));
    const searchW = Math.round(Math.min(w - 300, Math.max(w * 0.64, 736)));
    return {
      view,
      panelW,
      panelH: 0,
      railW: GUTTER,
      free: { x: panelW, y: top, w: w - panelW - GUTTER, h: h - top },
      asideX: (panelW - GUTTER) / (2 * w),
      asideY: 0,
      searchFree: { x: searchW, y: top, w: w - searchW, h: h - top },
      overlap: h - top,
    };
  }
  // a short window (a small phone, a phone on its side, a zoomed page) gives the text more of what there is
  const share = h - top < 520 ? 0.58 : h - top < 640 ? 0.53 : 0.48;
  const panelH = Math.round((h - top) * share);
  const band = Math.max(150, Math.round(h * 0.3));
  return {
    view,
    panelW: w,
    panelH,
    railW: 0,
    free: { x: 0, y: top, w, h: h - top - panelH },
    asideX: 0,
    asideY: -panelH / (2 * h),
    searchFree: { x: 0, y: top + BAND_CAPTION, w, h: band - BAND_CAPTION },
    overlap: h - top - band,
  };
}

/** The nine camera keys. `route` (the castle's corner to the hall) is followed there in chapter 4 and back in 5. */
function cameraKeys(lay: Lay, route: Route | null): CameraKey[] {
  const { view } = lay;
  const wide = view.wide;
  const key = (target: [number, number, number], across: number, heading: number, pitch: number, extra: Partial<CameraKey> = {}): CameraKey => {
    const fov = 28;
    const metresPerPixel = across / lay.free.w;
    return {
      tx: target[0],
      ty: target[1],
      tz: target[2],
      distance: (view.h * metresPerPixel) / 2 / Math.tan((fov * RAD) / 2),
      heading,
      pitch,
      fov,
      // (composed in the middle of the map's own window, between the header and the rail's strip)
      shiftX: wide ? -lay.railW / (2 * view.w) : 0,
      shiftY: view.top / (2 * view.h),
      ...extra,
    };
  };
  const hill = hillAt(CASTLE);
  const there = route ? (t: number) => route.smooth(t, 0.05) : undefined;
  const back = route ? (t: number) => route.smooth(1 - t, 0.05) : undefined;
  const seats = offset(CITY_HALL_DOOR, CIVIC_GRID_DEG, 2, 0);
  const gate = gatePose(view);
  const sky = { x: CASTLE.x + Math.sin(214 * RAD) * 4300, z: CASTLE.z - Math.cos(214 * RAD) * 4300 };
  const city = { ...gate, distance: gate.distance * (wide ? 1.2 : 1.12), shiftX: wide ? -0.015 : 0.06, shiftY: wide ? 0.1 : 0.03 };
  // the close views look from the south-east, as the light falls: the castle's front and its shaded end
  const front = castleGround(4, 16);
  const street = castleGround(4, 26);
  const between = castleGround(-10, 22);
  const stack = { x: SLABS.at.x * 0.8 + CASTLE.x * 0.2, z: SLABS.at.z * 0.8 + CASTLE.z * 0.2 };
  return [
    city,
    key([front.x, hill + 8, front.z], wide ? 250 : 230, 322, 33),
    key([street.x, hill + 4, street.z], wide ? 250 : 190, 334, 31),
    key([seats.x, 18, seats.z], wide ? 330 : 250, 238, 25, { via: there, arc: 0.9, rise: 4, easing: ease.inOut }),
    key([between.x, hill + 30, between.z], wide ? 300 : 230, 326, 25, { via: back, arc: 0.9, rise: 4 }),
    key([stack.x, hill + 36, stack.z], wide ? 220 : 180, 318, 21),
    key([CASTLE.x, hill, CASTLE.z], wide ? 900 : 640, 336, 57),
    { ...gate, tx: sky.x, tz: sky.z, distance: gate.distance * (wide ? 0.94 : 1), pitch: wide ? 35 : 40, shiftX: wide ? -lay.railW / (2 * view.w) : 0, shiftY: view.top / (2 * view.h) + (wide ? 0.04 : 0.02) },
    searchPose(view, lay.searchFree),
  ];
}

/** The eight featured conditions in the order they rise in the stack (by number). */
const RISING = [...FEATURED].sort((a, b) => Number(a.number) - Number(b.number));

/** Which way the mark lies on the ground: the compass bearing its words run along (square to the close views). */
const MARK_BEARING = 58;

/** What the story needs of whatever draws the map (the 3D scene, or the drawing made without WebGL): where a
 *  world point is on the screen, and the drawn objects, each a function of the scroll. */
export interface Eye {
  project(x: number, y: number, z: number, out: { x: number; y: number; behind: boolean }): { x: number; y: number; behind: boolean };
  /** Height of the ground at a point, in metres. */
  heightAt(x: number, z: number): number;
  /** Where slab `i` of the story's own stack is (the middle of its end). */
  heroLine(i: number): { x: number; y: number; z: number };
  /** The head of the pin that marks the story's own motion, as a world point. */
  heroTop(out: { x: number; y: number; z: number }): { x: number; y: number; z: number };
  setCastle(onMap: number, fold: number): void;
  setHall(onMap: number, fold: number): void;
  setLetters(support: number, opposition: number): void;
  setSeats(standing: number, voted: number): void;
  setSlabs(grow: number, line: number, lineAmount: number): void;
}

/** The part of the 3D scene the story drives beyond what every Eye has. */
export interface Flight {
  setTarget(pose: Pose, blend?: number): void;
  setAlive(alive: { drift: number; tilt: number; bulge: number; rings: number }): void;
  setHill(amount: number): void;
  setSpot(amount: number): void;
  setDim(amount: number): void;
  setRoute(points: Float32Array | null, draw?: number): void;
  setWave(amount: number, seconds?: number): void;
  setLight(civic: number): void;
}

export interface StoryHost {
  main: HTMLElement;
  /** Whatever is drawing the map now, for placing labels on it; null when nothing is. */
  eye(): Eye | null;
  /** The route has been worked out (x, z per point). */
  onRoute?(points: Float32Array): void;
  view(): View;
  reduced: boolean;
  streets: Promise<Streets>;
  /** The visitor stamped the motion (the note by the point says so). */
  stamped(): boolean;
  /** The story has reached its end (the search is open) or come back from it. */
  onEnded(ended: boolean): void;
  /** The chapter or its phase changed: the pose the story now rests on (for a map that is redrawn, not flown). */
  onChapter?(chapter: number, phase: "travel" | "hold", pose: Pose): void;
  /** The keyboard was on the rail when the story ended (the rail goes): put it somewhere useful (the search). */
  onRailLeft?(): void;
  /** The keyboard was inside the story when it moved past its last chapter (whose heading goes inert) or ended:
   *  put it somewhere useful (the search field), never on the page itself. */
  onFocusLeft?(): void;
}

export interface StoryHandle {
  root: HTMLElement;
  stage: HTMLElement;
  story: Story;
  lay(): Lay;
  /** The window changed size. */
  relayout(): void;
  /** The scene has loaded: fly the story on it. */
  attach(scene: Flight): void;
  /** Whatever draws the map has changed (it has loaded, or been replaced): draw the story's objects on it. */
  redraw(): void;
  /** Hold the story's panel back (the gate is up) or let it in. */
  setWaiting(waiting: boolean): void;
  /** After every frame the scene draws: put the labels where their points are. */
  place(): void;
  /** Put the keyboard's focus on the heading of the chapter on screen (the gate has just come down). */
  focusChapter(): void;
  /** Lay the chapters out as plain sections the page scrolls through (a short window: a zoomed page, a phone on
   *  its side), or back on the scrolled stage. The page puts the scroll engine away meanwhile. */
  setFlow(flow: boolean): void;
  /** In the plain layout: the document position of a chapter's top (to keep the visitor's place). */
  flowTop(chapter: number): number;
  /** The pose the story wants now. */
  pose: Pose;
  /** How much of the route is drawn now (0 to 1), for a map that is redrawn. */
  readonly routeDrawn: number;
  readonly state: StoryState;
  /** The search will rise over the end of the story: give it this much overlap (CSS pixels). */
  overlap(): number;
}

function tag<K extends keyof HTMLElementTagNameMap>(name: K, className = "", text = ""): HTMLElementTagNameMap[K] {
  const el = document.createElement(name);
  if (className) el.className = className;
  if (text) el.textContent = text;
  return el;
}

/** A link to a page of the motion: it opens the public PDF in a new tab, and says so to a screen reader. */
function pdfLink(className: string, text: string, href: string): HTMLAnchorElement {
  const a = tag("a", className, text);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener";
  a.append(tag("span", "vh", " (PDF, opens in a new tab)"));
  return a;
}

type Point3 = { x: number; y: number; z: number };

interface Label {
  el: HTMLElement;
  /** The world point it is tied to. */
  at: () => Point3;
  /** Which point of its own box sits there: 0 its left (top), 0.5 its middle, 1 its right (bottom). */
  ax: number;
  ay: number;
  /** Moved from there by this many pixels. */
  dx: number;
  dy: number;
  alpha: number;
  /** A leader: a hairline from the label's edge to this world point (default: none). */
  lead?: () => Point3;
  line?: SVGLineElement;
  /** Its size, measured once it is first shown (0: not yet). */
  w: number;
  h: number;
}

export function mountStory(host: StoryHost): StoryHandle {
  let view = host.view();
  let lay = measureLay(view);
  let scene: Flight | null = null;
  let route: Route | null = null;
  let keys = cameraKeys(lay, null);
  const pose = emptyPose();
  let last: StoryState | null = null;
  let lastPos = 0;
  let ended = false;
  let routeDrawn = 0;

  // ---- the page: a tall root, a sticky stage, the panel, the labels ---------------------------------------------------
  const root = tag("div", "story-root c-story is-waiting");
  const stage = tag("div", "story-stage c-stage");
  const labels = tag("div", "c-labels");
  labels.setAttribute("aria-hidden", "true");
  const leaders = document.createElementNS(NS, "svg");
  leaders.setAttribute("class", "c-leaders");
  labels.append(leaders);
  const panel = tag("section", "c-panel c-opaque");
  panel.setAttribute("aria-label", `The story of one motion: ${CASE.business}`);
  // the strip of paper the chapter rail stands on, so the rail never lies over the map
  const strip = tag("div", "c-railstrip c-opaque");
  stage.append(labels, panel, strip);
  root.append(stage);

  const chapters: HTMLElement[] = [];
  const headings: HTMLElement[] = [];
  const total = TEXT.length;
  const voteNames: HTMLElement[] = [];
  let stepItems: HTMLElement[] = [];
  let counter: HTMLElement | null = null;
  TEXT.forEach((text, i) => {
    if (i === total - 1) return; // the last chapter is the search itself
    const article = tag("article", "c-chapter");
    article.dataset.chapter = String(i);
    // (a chapter longer than its panel scrolls inside it: the wheel and the arrow keys scroll it first)
    article.dataset.storyScroll = "";
    article.append(tag("p", "label c-chapter__kicker", `${i + 1} of ${total} · ${text.title}`));
    const title = tag("h2", "c-chapter__title");
    title.tabIndex = -1;
    headings.push(title);
    if (text.id === "more") {
      // "There are 5,048 more.": the number counts up as the stacks rise
      const [before, after] = text.heading.split(num(TOTALS.others));
      counter = tag("span", "c-count", num(TOTALS.others));
      title.append(before ?? "", counter, after ?? "");
    } else {
      // a hyphenated word stays on one line ("twenty-two")
      for (const word of text.heading.split(" ")) {
        if (title.childNodes.length) title.append(" ");
        if (word.includes("-")) title.append(tag("span", "c-nowrap", word));
        else title.append(word);
      }
    }
    article.append(title);
    text.body.forEach((para, k) => {
      article.append(tag("p", "c-chapter__body", para));
      if (k === 0 && text.quote) article.append(tag("blockquote", "c-chapter__quote", text.quote));
    });
    if (text.id === "hearing") {
      const vote = tag("dl", "c-vote");
      const row = (name: string, people: string[]): void => {
        const div = tag("div");
        const dd = tag("dd");
        if (people.length === 0) dd.textContent = "None";
        people.forEach((person, k) => {
          // as the motion prints them: one after another, with commas
          const span = tag("span", "c-vote__name", k < people.length - 1 ? `${person},` : person);
          dd.append(span, " ");
          if (name === "Ayes") voteNames.push(span);
        });
        div.append(tag("dt", "label", name), dd);
        vote.append(div);
      };
      row("Ayes", VOTE.ayes);
      row("Nays", VOTE.nays);
      row("Absent", VOTE.absent);
      article.append(vote);
    }
    if (text.id === "conditions") {
      const list = tag("ol", "c-steps");
      stepItems = RISING.map(f => {
        const li = tag("li", "c-step");
        const stepTitle = tag("h3", "c-step__title", f.title);
        stepTitle.tabIndex = -1;
        li.append(tag("p", "label", `Condition ${f.number} of ${CONDITIONS.length}`), stepTitle, tag("p", "c-step__gloss", f.gloss));
        li.append(pdfLink("c-step__link data", `p. ${f.page} · open the motion`, f.href));
        list.append(li);
        return li;
      });
      article.append(list);
    }
    if (text.id === "page") article.append(pdfLink("c-step__link data", `p. ${PAGE.number} · open the motion`, PAGE.href));
    if (text.source) article.append(tag("p", "c-chapter__source data", text.source));
    for (const line of text.aside ?? []) article.append(tag("p", "c-chapter__aside", line));
    for (const line of text.more ?? []) article.append(tag("p", "c-chapter__aside c-chapter__aside--more", line));
    if (i === 0) {
      const cue = tag("p", "c-cue data");
      cue.id = "c-cue";
      const arrow = tag("span", "c-cue__arrow", "↓");
      arrow.setAttribute("aria-hidden", "true");
      cue.append("Scroll for the story ", arrow, tag("span", "vh", "(or use the arrow keys), or skip to the search."));
      article.append(cue);
      // the heading the keyboard lands on after the stamp says how to go on
      title.setAttribute("aria-describedby", cue.id);
    }
    chapters.push(article);
    panel.append(article);
  });

  // ---- a chapter longer than its panel: its foot fades and says there is more (a click reads on) ------------------
  const more = tag("div", "c-more data");
  more.setAttribute("aria-hidden", "true");
  more.append("More ", tag("span", "c-more__arrow", "↓"));
  more.hidden = true;
  panel.append(more);
  let flow = false;
  const updateMore = (): void => {
    const article = chapters[shownChapter];
    let want = false;
    if (article && !flow) {
      const over = article.scrollHeight - article.clientHeight > 4;
      want = over && article.scrollTop + article.clientHeight < article.scrollHeight - 4 && Number(article.style.opacity || 0) > 0.5;
    }
    for (const a of chapters) a.classList.toggle("is-more", want && a === article);
    if (more.hidden === want) more.hidden = !want;
  };
  more.addEventListener("click", () => {
    const article = chapters[shownChapter];
    article?.scrollBy({ top: article.clientHeight * 0.75, behavior: host.reduced ? "auto" : "smooth" });
  });
  for (const a of chapters) a.addEventListener("scroll", updateMore, { passive: true });
  // the faces arrive after the first layout: a chapter that fitted may no longer
  void document.fonts?.ready.then(updateMore).catch(() => {});

  // the page of the motion the story opens (chapter 7): a facsimile in type of what the search holds, never a scan
  const page = tag("aside", "c-page c-opaque");
  page.setAttribute("aria-label", `Motion No. ${CASE.motion}, page ${PAGE.number}, as the search holds it`);
  page.append(tag("p", "c-page__head data", `Motion No. ${CASE.motion} · page ${PAGE.number} of ${CASE.pages}`));
  const pageItems = PAGE.conditions.map(c => {
    const item = tag("div", "c-page__item");
    item.append(tag("span", "c-page__num data", `${c.number}.`), tag("p", "c-page__text"));
    const p = item.lastElementChild as HTMLElement;
    p.append(tag("b", "", `${c.title}. `), c.body);
    page.append(item);
    return item;
  });
  page.append(pdfLink("c-page__link data", `Excerpts. Read page ${PAGE.number} of the motion`, PAGE.href));
  stage.append(page);

  // ---- labels on the map: each on its own plate of paper, tied to a point, with a hairline to what it names --------
  const all: Label[] = [];
  const add = (el: HTMLElement, at: Label["at"], place: { ax?: number; ay?: number; dx?: number; dy?: number; lead?: Label["lead"] } = {}): Label => {
    const label: Label = { el, at, ax: place.ax ?? 0, ay: place.ay ?? 0.5, dx: place.dx ?? 0, dy: place.dy ?? 0, alpha: 0, lead: place.lead, w: 0, h: 0 };
    el.classList.add("c-plate");
    labels.append(el);
    if (label.lead) {
      label.line = document.createElementNS(NS, "line");
      leaders.append(label.line);
    }
    all.push(label);
    return label;
  };
  const groundY = (x: number, z: number): number => host.eye()?.heightAt(x, z) ?? 0;
  const onGround = (p: { x: number; z: number }, up = 0): (() => Point3) => {
    const out = { x: p.x, y: 0, z: p.z };
    return () => {
      out.y = groundY(p.x, p.z) + up;
      return out;
    };
  };
  const heroTop = { x: CASTLE.x, y: 0, z: CASTLE.z };
  const heroHead = (): Point3 => host.eye()?.heroTop(heroTop) ?? heroTop;
  const heroNote = add(tag("p", "c-note c-note--hero"), heroHead, { ax: 0, ay: 1, dx: 22, dy: -14, lead: heroHead });
  const streetLabels = STREET_NAMES.map(s => add(tag("p", "c-note c-note--street", s.name), onGround(s.at), { ax: 0.5, ay: 0.5, lead: onGround(s.on) }));
  // the letters: two rows of cards on the street, each row named at its end
  // (each row is named at its west end, where both rows start: the two plates stand one over the other, clear of
  // the cards and of the point)
  // (the row behind is named above its point, the row in front below its own: close as the rows stand, the two
  // plates never cover each other)
  const tallyOf = (words: string, from: { x: number; z: number }, ay: number): { label: Label; num: HTMLElement } => {
    const el = tag("p", "c-tally data");
    const n = tag("b", "", "0");
    el.append(n, ` ${words}`);
    return { label: add(el, onGround(offset(from, HILL_GRID_DEG, -4, 0), LETTER_ROWS.card.h / 2), { ax: 1, ay, dx: -10, dy: ay > 0.5 ? 1 : -1 }), num: n };
  };
  const supportTally = tallyOf("letters in support", LETTER_ROWS.support, 1);
  const opposeTally = tallyOf("in opposition", LETTER_ROWS.opposition, 0);
  // the vote: a count over the row of seats, and each seat's name on its own plate as it votes
  const ayesEl = tag("p", "c-place data");
  const ayesNum = tag("b", "", "0");
  ayesEl.append("Ayes ", ayesNum, ` of ${VOTE.ayes.length + VOTE.nays.length + VOTE.absent.length}`);
  const ayes = add(ayesEl, () => ({ x: SEATS[0]!.x, y: 0, z: SEATS[0]!.z }), { ax: 0, ay: 0.5, dx: 34, dy: 4 });
  // (under the seats, where the ground is bare: above them stands the hall)
  const seatLabels = SEATS.map((s, i) => add(tag("p", "c-seat data", VOTE.ayes[i] ?? ""), () => ({ x: s.x, y: 0, z: s.z }), { ax: 0.5, ay: 0, dy: 16 + (i % 2) * 22, lead: () => ({ x: s.x, y: 0, z: s.z }) }));
  // the mark, lying on the ground in front of the address: laid by a matrix, like the sheet at the gate
  const MARK_PX = 220;
  const markBox = { w: MARK_PX + 36, h: MARK_PX * MARK_RATIO + 44 };
  const markEl = tag("div", "c-mark");
  markEl.style.width = `${markBox.w}px`;
  markEl.style.height = `${markBox.h}px`;
  renderMark(markEl, { width: MARK_PX, seed: 19958, wear: "light", label: "" });
  labels.append(markEl);
  let markAlpha = 0;
  const markCorners = ((): { x: number; z: number }[] => {
    const metres = MARK_GROUND.width / MARK_PX;
    const b = MARK_BEARING * RAD;
    const right = { x: Math.sin(b), z: -Math.cos(b) };
    const up = { x: Math.sin(b - Math.PI / 2), z: -Math.cos(b - Math.PI / 2) };
    const hw = (markBox.w * metres) / 2, hh = (markBox.h * metres) / 2;
    const c = MARK_GROUND.at;
    const corner = (sx: number, sy: number): { x: number; z: number } => ({ x: c.x + right.x * hw * sx + up.x * hh * sy, z: c.z + right.z * hw * sx + up.z * hh * sy });
    return [corner(-1, 1), corner(1, 1), corner(1, -1), corner(-1, -1)];
  })();
  const markQuad = [{ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }];
  // a condition's gloss, in pencil, beside its slab
  const lineEl = tag("p", "c-note c-note--line");
  let lineIndex = 0;
  let lineText = "";
  const linePoint = (): Point3 => host.eye()?.heroLine(lineIndex) ?? { x: SLABS.at.x, y: 0, z: SLABS.at.z };
  const lineLabel = add(lineEl, linePoint, { ax: 0, ay: 0.5, dx: 34, lead: linePoint });

  // ---- the route: the shortest way along real streets from the castle's corner to the block of Polk Street ---------
  void host.streets.then(streets => {
    const graph = streetGraph(streets);
    const north = graph.route(CASTLE_CORNER, POLK_NORTH);
    const south = graph.route(CASTLE_CORNER, POLK_SOUTH);
    const best = north && south ? (north.length <= south.length ? north : south) : (north ?? south);
    if (!best) return;
    const pts: { x: number; z: number }[] = [CASTLE_CORNER];
    for (let i = 0; i < best.points.length / 2; i++) pts.push({ x: best.points[i * 2]!, z: best.points[i * 2 + 1]! });
    pts.push(CITY_HALL_DOOR);
    route = makeRoute(pts);
    keys = cameraKeys(lay, route);
    scene?.setRoute(route.points, 0);
    host.onRoute?.(route.points);
    if (last) apply(last, true);
  }).catch(() => {});

  // ---- the story ------------------------------------------------------------------------------------------------------------
  const unitOf = (stageHeight: number): number => stageHeight * (view.wide ? 1 : 0.9);
  const specs = (): ReturnType<typeof chapterSpecs> => chapterSpecs(view.wide, lay.overlap / unitOf(Math.max(1, stage.offsetHeight || view.h - view.top)));

  const sizeStage = (): void => {
    root.style.setProperty("--story-top", `${view.top}px`);
    root.style.setProperty("--c-panel-w", `${lay.panelW}px`);
    root.style.setProperty("--c-panel-h", `${lay.panelH}px`);
    root.style.setProperty("--c-free-x", `${lay.free.x}px`);
    root.style.setProperty("--c-free-w", `${lay.free.w}px`);
    root.style.setProperty("--c-free-h", `${lay.free.h}px`);
    root.style.setProperty("--c-rail-w", `${lay.railW}px`);
    root.classList.toggle("c-story--tall", !view.wide);
    for (const l of all) l.w = 0;
  };
  sizeStage();
  host.main.append(root);

  let rail: Rail | null = null;
  let shownChapter = -2;
  /** The chapter a rail tick asked for (its heading takes the focus on arrival), or -1. */
  let railPick = -1;
  /** Which chapter the "more" cue was last worked out for (and whether its text was in). */
  let moreKey = -1;
  let shownStep = -2;
  let shownPageStep = -2;
  let shownVotes = -1;
  let shownCount = -1;
  let shownTally = -1;
  let shownKey = -1;
  /** True once the story owns the camera (the gate is down). */
  let live = false;
  const setAlpha = (el: HTMLElement, a: number, keep = false): void => {
    const v = a < 0.004 ? "0" : a > 0.996 ? "1" : a.toFixed(3);
    if (el.style.opacity !== v) el.style.opacity = v;
    const want = v === "0" && !keep ? "hidden" : "visible";
    if (el.style.visibility !== want) el.style.visibility = want;
  };

  function apply(state: StoryState, force = false): void {
    last = state;
    const tl = state.timeline;
    const pos = state.pos;
    const c = state.chapter;
    const hold = (i: number): number => tl.holdAt(i, pos);
    const travel = (i: number): number => tl.travelAt(i, pos);
    const jump = Math.abs(pos - lastPos) > 0.45;
    lastPos = pos;

    // ---- the panel and its text --------------------------------------------------------------------------------------
    const frame = c < total - 1 ? ease.slide(tl.frameAt(c, pos)) : 0;
    panel.style.setProperty("--in", frame.toFixed(4));
    panel.style.visibility = frame <= 0.001 ? "hidden" : "";
    if (!flow) {
      chapters.forEach((article, i) => {
        // (the chapter travelled to is never hidden, only faded: the keyboard's focus can go to its heading while its
        // text is still coming in)
        setAlpha(article, i === c ? tl.textAt(i, pos) : 0, i === c);
      });
    }
    if (c !== shownChapter || force) {
      const before = shownChapter;
      shownChapter = c;
      // the keyboard was inside the chapter that goes (an arrow key from its heading or one of its links): it moves
      // to the heading of the chapter that comes, never to the page itself
      const active = document.activeElement;
      const lost = !flow && before !== c && active instanceof HTMLElement && chapters.some((a, i) => i !== c && a.contains(active));
      chapters.forEach((article, i) => {
        if (i === c || flow) {
          article.removeAttribute("aria-hidden");
          article.inert = false;
        } else {
          article.setAttribute("aria-hidden", "true");
          article.inert = true;
        }
      });
      root.dataset.chapter = String(c);
      if (lost) {
        // past the last chapter (the closing view, the search) there is no heading to go to: the search field
        const next = headings[c];
        if (next) next.focus({ preventScroll: true });
        else host.onFocusLeft?.();
      }
      // a chapter asked for from the rail: its heading takes the focus once it is there (a screen reader reads it)
      if (railPick === c) {
        railPick = -1;
        headings[c]?.focus({ preventScroll: true });
      }
    }
    rail?.update(state);

    // ---- chapter 2: the hill, the castle, its streets named ---------------------------------------------------------
    const hillUp = range(travel(1), 0.3, 1);
    const hillDown = range(travel(7), 0, 0.5);
    const hill = Math.min(hillUp, 1 - hillDown);
    // the castle comes onto the map as the camera arrives and folds up while the text comes in; it stays for the
    // close chapters (the camera is away at the hearing) and goes when the view draws back over the whole city
    const castleOn = Math.min(ease.out(range(travel(1), 0.45, 0.9)), 1 - ease.inOut(range(travel(7), 0.02, 0.3)));
    const castleFold = c < 1 ? 0 : c === 1 ? ease.inOut(range(hold(1), 0.04, 0.52)) : 1;
    streetLabels.forEach((s, i) => {
      s.alpha = c === 1 ? range(hold(1), 0.4 + i * 0.1, 0.56 + i * 0.1) : c === 2 ? 1 - range(travel(2), 0, 0.3) : 0;
    });

    // ---- chapter 3: the letters ------------------------------------------------------------------------------------------
    const lettersGone = c === 3 ? range(travel(3), 0, 0.12) : c > 3 ? 1 : 0;
    const support = c < 2 || lettersGone >= 1 ? 0 : range(hold(2), 0.16, 0.5) * LETTERS.support * (1 - lettersGone);
    const oppose = c < 2 || lettersGone >= 1 ? 0 : range(hold(2), 0.42, 0.66) * LETTERS.opposition * (1 - lettersGone);
    supportTally.label.alpha = c === 2 ? range(hold(2), 0.14, 0.24) : c === 3 ? 1 - range(travel(3), 0, 0.1) : 0;
    opposeTally.label.alpha = c === 2 ? range(hold(2), 0.4, 0.5) : c === 3 ? 1 - range(travel(3), 0, 0.1) : 0;
    const tallyKey = Math.round(support) * 100 + Math.round(oppose);
    if (tallyKey !== shownTally) {
      shownTally = tallyKey;
      supportTally.num.textContent = String(Math.round(support));
      opposeTally.num.textContent = String(Math.round(oppose));
    }

    // ---- chapter 4: the hall, the seats, the vote ----------------------------------------------------------------------
    const atHall = c === 3 || (c === 4 && state.phase === "travel");
    const hallGone = range(travel(4), 0.02, 0.22);
    const hallOn = c < 3 || c > 4 ? 0 : Math.min(ease.out(range(travel(3), 0.5, 0.8)), 1 - hallGone);
    const hallFold = c === 3 ? ease.inOut(Math.max(range(travel(3), 0.72, 1) * 0.55, 0.55 + 0.45 * range(hold(3), 0, 0.2))) : c === 4 ? 1 : 0;
    const seatsUp = atHall ? range(hold(3), 0.1, 0.3) * 7 * (1 - hallGone) : 0;
    const votes = c === 3 ? Math.floor(range(hold(3), 0.34, 0.66) * 7 + 1e-6) : c > 3 ? 7 : 0;
    if (votes !== shownVotes) {
      shownVotes = votes;
      voteNames.forEach((el, i) => el.classList.toggle("is-in", i < votes));
      ayesNum.textContent = String(votes);
    }
    seatLabels.forEach((s, i) => {
      s.alpha = atHall && i < votes ? 1 - hallGone : 0;
    });
    ayes.alpha = atHall ? range(hold(3), 0.28, 0.36) * (1 - hallGone) : 0;

    // ---- chapters 5 to 7: the mark on the ground, the stack of slabs, its lines ----------------------------------------
    markAlpha = c < 4 ? 0 : c === 4 ? range(hold(4), 0.04, 0.12) : c <= 6 ? 1 : 1 - range(travel(7), 0, 0.2);
    const slabsUp = c < 4 ? 0 : c === 4 ? range(hold(4), 0.12, 0.66) : c <= 6 ? 1 : 1 - ease.inOut(range(travel(7), 0.02, 0.32));
    let line = -1, lineAmount = 0;
    const step = c === 5 || c === 6 ? tl.stepAt(c, pos) : { index: -1, t: 0 };
    if (c === 5 && step.index >= 0) {
      line = Number(RISING[step.index]!.number) - 1;
      lineAmount = state.still ? 1 : Math.min(range(step.t, 0, 0.3), 1 - range(step.t, 0.9, 1));
    } else if (c === 6 && step.index >= 0) {
      line = Number(PAGE.conditions[step.index]!.number) - 1;
      lineAmount = state.still ? 1 : Math.min(range(step.t, 0, 0.3), 1 - range(step.t, 0.9, 1));
    }
    if (c === 5) {
      const at = step.index;
      if (at !== shownStep || force) {
        shownStep = at;
        // (the keyboard on the link of the condition that goes: on to the heading of the one that comes)
        const active = document.activeElement;
        const lost = active instanceof HTMLElement && stepItems.some((li, i) => i !== at && li.contains(active));
        stepItems.forEach((li, i) => {
          li.classList.toggle("is-current", i === at);
          li.inert = !flow && i !== at;
        });
        if (lost) {
          const title = at >= 0 ? stepItems[at]?.querySelector<HTMLElement>(".c-step__title") : null;
          (title ?? headings[5])?.focus({ preventScroll: true });
        }
        if (at >= 0) {
          lineIndex = line;
          const text = RISING[at]!.pencil;
          if (text !== lineText) {
            lineText = text;
            lineEl.textContent = text;
            lineLabel.w = 0;
          }
        }
      }
      lineLabel.alpha = at >= 0 ? lineAmount : 0;
    } else {
      lineLabel.alpha = 0;
      if (shownStep !== -2 && c !== 5) {
        shownStep = -2;
        stepItems.forEach(li => li.classList.remove("is-current"));
      }
    }
    // the page
    const pageIn = c === 6 ? tl.textAt(6, pos) : 0;
    page.style.setProperty("--in", pageIn.toFixed(3));
    page.style.visibility = pageIn <= 0.004 ? "hidden" : "";
    page.inert = flow || pageIn < 0.5;
    const pageStep = c === 6 ? step.index : -1;
    if (pageStep !== shownPageStep) {
      shownPageStep = pageStep;
      pageItems.forEach((el, i) => el.classList.toggle("is-current", i === pageStep));
    }

    // ---- chapter 8: the skyline and the count --------------------------------------------------------------------------
    const wave = c < 7 ? 0 : c === 7 ? ease.inOut(range(hold(7), 0.06, 0.66)) : 1;
    if (counter) {
      const shown = c < 7 ? 0 : Math.round(TOTALS.others * (c === 7 ? range(hold(7), 0.1, 0.68) : 1));
      if (shown !== shownCount) {
        shownCount = shown;
        counter.textContent = num(shown);
      }
    }

    // ---- the note by the story's own point: in the two views of the whole city ----------------------------------------
    heroNote.alpha = root.classList.contains("is-waiting") ? 0 : c === 0 ? tl.textAt(0, pos) : c === 7 ? tl.textAt(7, pos) : 0;

    // ---- the drawn objects, on whatever draws the map ---------------------------------------------------------------
    const eye = live ? host.eye() : null;
    if (eye) {
      eye.setCastle(castleOn, castleFold);
      eye.setHall(hallOn, hallFold);
      eye.setLetters(support, oppose);
      eye.setSeats(seatsUp, votes);
      eye.setSlabs(slabsUp, line, lineAmount);
    }

    // ---- the camera and the living ground ----------------------------------------------------------------------------
    poseAt(keys, tl, pos, pose);
    pose.shiftX += lay.asideX * frame;
    pose.shiftY += lay.asideY * frame;
    routeDrawn = c < 3 ? 0 : c === 3 ? (state.phase === "travel" ? range(travel(3), 0.02, 0.9) : 1) : c === 4 ? 1 - range(travel(4), 0.06, 0.88) : 0;
    if (scene && live) {
      scene.setTarget(pose, jump && !state.still ? 1.25 : 0);
      scene.setHill(hill);
      const spotA = Math.min(range(travel(1), 0.5, 1), 1 - range(travel(3), 0, 0.3)) * 0.85;
      const spotB = Math.min(range(travel(4), 0.75, 1), 1 - range(travel(7), 0, 0.3)) * 0.5;
      scene.setSpot(Math.max(spotA, spotB));
      scene.setRoute(null, routeDrawn);
      scene.setLight(Math.min(range(travel(3), 0.3, 0.6), 1 - range(travel(4), 0.4, 0.7)));
      scene.setWave(wave, jump && !state.still ? 1.5 : 0);
      scene.setDim(range(travel(8), 0, 0.7) * 0.3);
      const cityView = c === 0 || c >= 7;
      // (the last chapter has no hold: once the story has ended the camera is at rest)
      const moving = state.phase === "travel" && !state.ended;
      // inside a chapter the camera is still: no drift. The two city views answer the pointer (a lean, a dome) and
      // keep their rings; the close views are drawings, and hold still. The search rests: one ring when its
      // results change (the scene's own), and the lean and the dome while the pointer is on the map.
      scene.setAlive({ drift: 0, tilt: moving ? 0 : cityView ? 0.8 : 0, bulge: cityView && !moving ? 1 : 0, rings: cityView && !moving && !state.ended ? 1 : 0 });
    }

    const chapterKey = c * 2 + (state.phase === "hold" ? 1 : 0);
    if (chapterKey !== shownKey || force) {
      shownKey = chapterKey;
      host.onChapter?.(c, state.phase, pose);
    }
    if (state.ended !== ended) {
      ended = state.ended;
      root.classList.toggle("is-ended", ended);
      // past its end the rail is not shown and cannot be reached by the keyboard (a keyboard on it goes on to the
      // search, not to the page)
      const onRail = rail !== null && rail.element.contains(document.activeElement);
      // (and the keyboard anywhere else in the story, as the scroll reaches the search, goes on to it too)
      const inStory = !flow && !onRail && root.contains(document.activeElement);
      if (rail) rail.element.inert = ended || root.classList.contains("is-waiting");
      if (ended && onRail) host.onRailLeft?.();
      else if (ended && inStory) host.onFocusLeft?.();
      host.onEnded(ended);
    }
    const moreAt = c * 2 + (c < total - 1 && tl.textAt(c, pos) > 0.5 ? 1 : 0);
    if (moreAt !== moreKey || force) {
      moreKey = moreAt;
      updateMore();
    }
    place();
  }

  const proj = { x: 0, y: 0, behind: false };
  const proj2 = { x: 0, y: 0, behind: false };
  function place(): void {
    const eye = host.eye();
    if (!eye) {
      for (const l of all) setAlpha(l.el, 0);
      setAlpha(markEl, 0);
      return;
    }
    const top = view.top;
    // the labels keep inside the map's own window, clear of the rail's strip and the panel
    const minX = lay.free.x + 8, maxX = lay.free.x + lay.free.w - 8;
    const minY = 8, maxY = lay.free.h - 8;
    for (const l of all) {
      setAlpha(l.el, l.alpha);
      if (l.line) l.line.style.opacity = l.alpha < 0.004 ? "0" : l.alpha.toFixed(3);
      if (l.alpha <= 0.004) continue;
      if (l.w === 0) {
        l.w = l.el.offsetWidth;
        l.h = l.el.offsetHeight;
      }
      const p = l.at();
      eye.project(p.x, p.y, p.z, proj);
      if (proj.behind) {
        l.el.style.visibility = "hidden";
        if (l.line) l.line.style.opacity = "0";
        continue;
      }
      let x = proj.x + l.dx - l.ax * l.w;
      let y = proj.y - top + l.dy - l.ay * l.h;
      // a plate that would hang off the right of a narrow map is hung to the left of its point instead
      if (x + l.w > maxX && l.ax === 0 && proj.x - l.dx - l.w >= minX) x = proj.x - l.dx - l.w;
      x = Math.min(Math.max(x, minX), Math.max(minX, maxX - l.w));
      y = Math.min(Math.max(y, minY), Math.max(minY, maxY - l.h));
      l.el.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;
      if (l.line && l.lead) {
        const q = l.lead();
        eye.project(q.x, q.y, q.z, proj2);
        const qx = proj2.x, qy = proj2.y - top;
        // from the nearest point of the plate's edge to what it names
        const sx = Math.min(Math.max(qx, x), x + l.w), sy = Math.min(Math.max(qy, y), y + l.h);
        const far = Math.hypot(qx - sx, qy - sy);
        if (proj2.behind || far < 5) l.line.style.opacity = "0";
        else {
          l.line.setAttribute("x1", sx.toFixed(1));
          l.line.setAttribute("y1", sy.toFixed(1));
          l.line.setAttribute("x2", qx.toFixed(1));
          l.line.setAttribute("y2", qy.toFixed(1));
        }
      }
    }
    // the mark lies on the ground: its four corners are where the camera sees them
    setAlpha(markEl, markAlpha);
    if (markAlpha > 0.004) {
      let ok = true;
      for (let i = 0; i < 4; i++) {
        const cnr = markCorners[i]!;
        eye.project(cnr.x, eye.heightAt(cnr.x, cnr.z) + 0.4, cnr.z, proj);
        if (proj.behind) ok = false;
        markQuad[i]!.x = proj.x;
        markQuad[i]!.y = proj.y - top;
      }
      if (ok) markEl.style.transform = matrix3d(quadHomography(markBox.w, markBox.h, markQuad));
      else markEl.style.visibility = "hidden";
    }
  }

  const story = createStory({
    root,
    stage,
    chapters: specs(),
    unit: unitOf,
    mode: host.reduced ? "stills" : "scrub",
    // the search under the story scrolls as the page always does: the wheel is smoothed only inside the story
    lerpAfter: 1,
    // nothing of the story moves of itself: once the scroll has settled the loop sleeps (a page at rest asks for no
    // frames); a scroll, a key, a touch or a move the page asks for wakes it
    sleep: true,
    onUpdate: state => apply(state),
  });
  rail = createRail(story, { label: "Chapters of the story", onPick: chapter => (railPick = chapter) });
  rail.element.classList.add("c-rail");
  rail.element.inert = true;
  if (!view.wide) rail.element.classList.add("story-rail--across");
  stage.append(rail.element);
  story.refresh();

  // ---- between two chapters there is nothing to read: a scroll that stops there is carried on to the nearer one ---
  let armed = false;
  let settle = 0;
  let lastDirection = 1;
  let lastY = window.scrollY;
  const carry = (): void => {
    settle = 0;
    if (!armed) return;
    armed = false;
    const state = story.state;
    if (story.mode !== "scrub" || !live || state.ended) return;
    const tl = story.timeline;
    // stopped inside a chapter while its text is still coming in (or already going): on to where it reads whole
    if (state.phase === "hold") {
      if (tl.textAt(state.chapter, state.pos) < 0.97) story.goToStop(tl.nearestStop(state.pos));
      return;
    }
    if (state.chapter === 0) return;
    const here = tl.chapters[state.chapter]!;
    const before = tl.chapters[state.chapter - 1]!;
    const t = tl.travelAt(state.chapter, state.pos);
    // onward to where the chapter ahead has its text in, or back to where the one behind still has its own:
    // the way the visitor was going, unless they had barely left
    const onward = lastDirection > 0 ? t > 0.12 : t > 0.88;
    if (onward) {
      if (here.hold <= 0) story.toEnd({ smooth: true });
      else story.goToStop({ pos: here.holdStart + Math.min(0.3, here.hold * 0.4), chapter: here.index, step: -1 });
    } else story.goToStop({ pos: before.end - Math.min(0.3, before.hold * 0.4), chapter: before.index, step: -1 });
  };
  const arm = (): void => {
    armed = true;
    window.clearTimeout(settle);
    settle = window.setTimeout(carry, 190);
  };
  window.addEventListener("wheel", arm, { passive: true });
  window.addEventListener("touchmove", arm, { passive: true });
  window.addEventListener("touchend", arm, { passive: true });
  window.addEventListener(
    "scroll",
    () => {
      const y = window.scrollY;
      if (y !== lastY) lastDirection = y > lastY ? 1 : -1;
      lastY = y;
      if (armed) {
        window.clearTimeout(settle);
        settle = window.setTimeout(carry, 190);
      }
    },
    { passive: true },
  );
  // a key or a rail tick moves the story itself: nothing is left to carry
  window.addEventListener("keydown", () => {
    armed = false;
    window.clearTimeout(settle);
  });

  return {
    root,
    stage,
    story,
    lay: () => lay,
    pose,
    get state() {
      return story.state;
    },
    get routeDrawn() {
      return routeDrawn;
    },
    overlap: () => lay.overlap,
    relayout() {
      view = host.view();
      lay = measureLay(view);
      keys = cameraKeys(lay, route);
      sizeStage();
      rail?.element.classList.toggle("story-rail--across", !view.wide);
      story.configure({ chapters: specs(), unit: unitOf });
      if (last) apply(last, true);
    },
    attach(next) {
      scene = next;
      if (route) scene.setRoute(route.points, 0);
      if (last) apply(last, true);
    },
    redraw() {
      if (last) apply(last, true);
    },
    setWaiting(waiting) {
      live = !waiting;
      root.classList.toggle("is-waiting", waiting);
      root.inert = waiting;
      if (rail) rail.element.inert = waiting || ended;
      heroNote.el.textContent = host.stamped() ? "the one you stamped" : "the one we follow";
      heroNote.w = 0;
      if (last) apply(last, true);
    },
    place,
    focusChapter() {
      // (in the plain layout the story starts at its first chapter, at the top of the page)
      headings[flow ? 0 : Math.min(headings.length - 1, story.state.chapter)]?.focus({ preventScroll: true });
    },
    setFlow(next) {
      if (next === flow) return;
      flow = next;
      root.classList.toggle("c-story--flow", flow);
      for (const article of chapters) {
        if (flow) {
          article.style.opacity = "";
          article.style.visibility = "";
          article.removeAttribute("aria-hidden");
          article.inert = false;
          article.scrollTop = 0;
        }
      }
      for (const li of stepItems) li.inert = flow ? false : !li.classList.contains("is-current");
      page.inert = flow || page.inert;
      shownChapter = -2;
      moreKey = -1;
      if (last) apply(last, true);
      updateMore();
    },
    flowTop(chapter) {
      const article = chapters[Math.max(0, Math.min(chapters.length - 1, chapter))];
      return article ? article.getBoundingClientRect().top + window.scrollY : 0;
    },
  };
}
