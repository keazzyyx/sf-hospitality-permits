// The scroll engine: a tall parent with a sticky stage; scroll position maps linearly to one timeline position;
// everything else is a function of that position. Fully reversible. Wheel input is smoothed with Lenis when motion
// is allowed; with reduced motion there is no smoothing and no scrubbing: each chapter (or step) is a still.
//
//   const story = createStory({ root, stage, chapters, onUpdate(state) { … }, onFrame(now) { … } });
//   story.goTo(3);          // the rail and the arrow keys use this
//   story.toEnd();          // "Skip to search"
//
// The engine owns the page's one requestAnimationFrame loop while it lives: `onUpdate` is called when the position
// changes (or after refresh()), `onFrame` on every frame, after it, for anything that must tick (a renderer).

import Lenis from "lenis";
import { buildTimeline, type ChapterSpec, type Edges, type Stop, type Timeline } from "./timeline";

export type StoryMode = "scrub" | "stills";

export interface StoryState {
  /** The timeline position in screens. In "stills" mode this is the position of the still being shown. */
  pos: number;
  /** 0 to 1 through the whole story. */
  progress: number;
  /** The chapter travelled to or held on. */
  chapter: number;
  phase: "travel" | "hold";
  /** The step of a stepped chapter, or -1. */
  step: number;
  /** True in "stills" mode: show every drawing complete, cut instead of moving. */
  still: boolean;
  /** True once the end of the story has been reached (the stage is about to let go). */
  ended: boolean;
  timeline: Timeline;
  /** How many pixels of scroll one screen of the timeline is. */
  unit: number;
  /** The raw scroll position in screens (not snapped, even in "stills" mode). */
  scroll: number;
}

export interface StoryOptions {
  /** The tall parent. The engine sets its height. */
  root: HTMLElement;
  /** The sticky stage inside it. */
  stage: HTMLElement;
  chapters: ChapterSpec[];
  edges?: Edges;
  /** Pixels of scroll per screen of the timeline, given the stage's height. Default: the stage's height. */
  unit?: (stageHeight: number) => number;
  /** "stills" for reduced motion (default: "scrub"). */
  mode?: StoryMode;
  /** Arrow keys, Page Up and Page Down step between stops (default true). */
  keyboard?: boolean;
  /** How much of the remaining way a wheel scroll covers each frame at 60 Hz (Lenis's lerp; default 0.11).
   *  Lower is smoother and slower to settle. */
  lerp?: number;
  /** The same for scrolling the page below the story (default: the same as `lerp`). A value near 1 leaves the
   *  page below at its native feel. */
  lerpAfter?: number;
  /** The End key goes to the story's end, where the page below begins (default false: the browser's own End). */
  endKey?: boolean;
  /** Do not call onUpdate while the visitor scrolls the page below the story: past the end nothing in the story
   *  changes (default false: onUpdate runs on every scroll change, with `state.scroll` still counting). */
  quietPastEnd?: boolean;
  /** Let the engine's frame loop sleep when nothing is moving (default false: it runs for the life of the page).
   *  It wakes on scroll, wheel, touch, keys, a resize, the tab coming back, any programmatic move and `wake()`.
   *  While something of the page's own is still moving, return true from `onFrame` to keep it awake. */
  sleep?: boolean;
  onUpdate(state: StoryState): void;
  /** Every frame, after onUpdate. With `sleep`, return true while something is still moving. */
  onFrame?(now: number): boolean | void;
}

export interface Story {
  readonly timeline: Timeline;
  readonly state: StoryState;
  /** Scroll to a chapter's resting position (its first step, for a stepped chapter). */
  goTo(chapter: number, options?: { instant?: boolean }): void;
  /** Scroll to a stop. */
  goToStop(stop: Stop, options?: { instant?: boolean }): void;
  next(): void;
  prev(): void;
  /** Jump to the end of the story (where the page below it begins). Instant unless `smooth`. */
  toEnd(options?: { smooth?: boolean }): void;
  /** The document scroll position (pixels) of a timeline position. */
  scrollOf(pos: number): number;
  /** Change the chapters (their lengths may depend on the layout) and measure again. */
  configure(options: { chapters?: ChapterSpec[]; unit?: (stageHeight: number) => number }): void;
  /** Measure again and call onUpdate (after a resize or a layout change). */
  refresh(): void;
  /** Start the frame loop again if it is asleep (see `sleep`): call it when something of the page's own starts
   *  to move without a scroll. Harmless when the loop is running. */
  wake(): void;
  setMode(mode: StoryMode): void;
  readonly mode: StoryMode;
  /** Put the story away (the page hides its root) or bring it back. While it is away the state stays at the end
   *  (`ended`), the keys are the page's own, and every scroll target is the top of the page: what follows the
   *  story is the page. Bringing it back measures again. */
  setCollapsed(collapsed: boolean): void;
  readonly collapsed: boolean;
  destroy(): void;
}

const EDITABLE = "input, textarea, select, [contenteditable]";

export function createStory(options: StoryOptions): Story {
  const { root, stage } = options;
  let chapters = options.chapters;
  let unitOf = options.unit ?? ((h: number) => h);
  let timeline = buildTimeline(chapters, options.edges);
  let mode: StoryMode = options.mode ?? "scrub";
  let unit = 1;
  let startY = 0; // document scroll at which the stage sticks
  let lastScroll = NaN;
  let lastStill = -1;
  let force = true;
  let raf = 0;
  let destroyed = false;
  let lenis: Lenis | null = null;
  const lerp = options.lerp ?? 0.11;
  const lerpAfter = options.lerpAfter ?? lerp;
  // a glide started by a key, the rail or goTo(): the stop it is heading for and when it should have arrived.
  // A wheel or a touch takes over and ends it.
  let flight: { stop: number; until: number } | null = null;
  // the stop a change of layout landed on in this frame (a second configure() in the same frame keeps it)
  let landing = -1;
  let lastRaw = NaN;
  let quiet = 0; // frames in a row in which nothing changed (for `sleep`)
  let asleep = false;
  let collapsed = false;

  const state: StoryState = {
    pos: 0,
    progress: 0,
    chapter: 0,
    phase: "hold",
    step: -1,
    still: mode === "stills",
    ended: false,
    timeline,
    unit: 1,
    scroll: 0,
  };

  const stickyTop = (): number => parseFloat(getComputedStyle(stage).top) || 0;

  const measure = (): void => {
    if (collapsed) {
      unit = 1;
      startY = 0;
      // (the root keeps no height of its own: what it holds is laid out as the page, or not at all)
      root.style.height = "";
      state.unit = unit;
      state.timeline = timeline;
      lenis?.resize();
      force = true;
      return;
    }
    const stageHeight = stage.offsetHeight;
    unit = Math.max(1, unitOf(stageHeight));
    root.style.height = `${Math.round(stageHeight + timeline.length * unit)}px`;
    startY = root.getBoundingClientRect().top + window.scrollY - stickyTop();
    state.unit = unit;
    state.timeline = timeline;
    lenis?.resize();
    force = true;
  };

  const startLenis = (): void => {
    if (lenis || mode !== "scrub") return;
    // (a box of text that can still scroll the way the wheel turns scrolls first: a chapter longer than its panel)
    lenis = new Lenis({ lerp, smoothWheel: true, autoRaf: false, allowNestedScroll: true });
  };
  const stopLenis = (): void => {
    lenis?.destroy();
    lenis = null;
  };

  const compute = (): void => {
    if (collapsed) {
      // put away: the story is over, whatever the page's scroll
      const end = timeline.locate(timeline.length);
      state.scroll = timeline.length + 1 + window.scrollY;
      state.pos = timeline.length;
      state.progress = 1;
      state.chapter = end.chapter;
      state.phase = end.phase;
      state.step = -1;
      state.still = mode === "stills";
      state.ended = true;
      return;
    }
    const y = window.scrollY;
    const scroll = (y - startY) / unit;
    state.scroll = scroll;
    let pos = Math.min(timeline.length, Math.max(0, scroll));
    let stillStep = -1;
    if (mode === "stills") {
      const stop = timeline.nearestStop(pos);
      pos = stop.pos;
      stillStep = stop.step;
    }
    const where = timeline.locate(pos);
    state.pos = pos;
    state.progress = timeline.length > 0 ? pos / timeline.length : 0;
    state.chapter = where.chapter;
    state.phase = where.phase;
    state.step = mode === "stills" ? stillStep : timeline.stepAt(where.chapter, pos).index;
    state.still = mode === "stills";
    state.ended = scroll >= timeline.length - 0.002;
  };

  const frame = (now: number): void => {
    if (destroyed) return;
    raf = 0;
    landing = -1;
    if (flight && now > flight.until) flight = null;
    lenis?.raf(now);
    const y = window.scrollY;
    let changed = false;
    if (force || y !== lastScroll) {
      lastScroll = y;
      changed = true;
      const before = lastRaw;
      compute();
      lastRaw = state.scroll;
      // the page below the story keeps the browser's own feel (when asked to)
      if (lenis && lerpAfter !== lerp) lenis.options.lerp = state.scroll > timeline.length + 0.01 ? lerpAfter : lerp;
      // past the end nothing in the story changes (when asked to stay quiet there)
      const past = options.quietPastEnd === true && !force && before > timeline.length && state.scroll > timeline.length;
      // in stills mode only a change of still is a change
      if (!past && (force || mode !== "stills" || state.pos !== lastStill)) {
        lastStill = state.pos;
        force = false;
        options.onUpdate(state);
      }
    }
    const busy = options.onFrame?.(now) === true;
    if (options.sleep) {
      const gliding = Boolean(lenis && (lenis.isScrolling || Math.abs(lenis.velocity) > 0.001)) || flight !== null;
      quiet = changed || busy || gliding || force ? 0 : quiet + 1;
      if (quiet > 30 || document.hidden) {
        asleep = true;
        return;
      }
    }
    raf = requestAnimationFrame(frame);
  };
  const wake = (): void => {
    quiet = 0;
    if (destroyed || !asleep) return;
    asleep = false;
    if (!raf) raf = requestAnimationFrame(frame);
  };

  const scrollOf = (pos: number): number => (collapsed ? 0 : Math.round(startY + pos * unit));

  /** Scroll to a document position. `stop` is the index of the stop being glided to (for a held key and for a
   *  change of layout in mid-glide), or -1. */
  const scrollTo = (y: number, instant: boolean, stop = -1): void => {
    wake();
    if (instant || mode === "stills" || !lenis) {
      flight = null;
      if (lenis) lenis.scrollTo(y, { immediate: true, force: true });
      else window.scrollTo({ top: y, behavior: "instant" as ScrollBehavior });
      force = true;
      return;
    }
    const screens = Math.abs(y - window.scrollY) / unit;
    const duration = Math.min(2.4, Math.max(0.9, 0.7 + screens * 0.55));
    flight = stop >= 0 ? { stop, until: performance.now() + duration * 1000 + 120 } : null;
    lenis.scrollTo(y, {
      duration,
      easing: t => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2),
      force: true,
      onComplete: () => {
        flight = null;
      },
    });
  };
  /** Glide to a stop by its index. A glide already heading there is left alone (it is not started again). */
  const glideTo = (index: number): void => {
    const stop = timeline.stops[index];
    if (!stop) return;
    if (flight && flight.stop === index) return;
    scrollTo(scrollOf(stop.pos), false, index);
  };

  const currentStopIndex = (): number => {
    // the last stop at or before where we are (with a little slack, so "next" from a stop moves on)
    const pos = mode === "stills" ? state.pos : Math.min(timeline.length, Math.max(0, (window.scrollY - startY) / unit));
    let i = 0;
    timeline.stops.forEach((s, k) => {
      if (s.pos <= pos + 0.04) i = k;
    });
    return i;
  };

  const story: Story = {
    get timeline() {
      return timeline;
    },
    state,
    get mode() {
      return mode;
    },
    goTo(chapter, { instant = false } = {}) {
      const stop = timeline.stops.find(s => s.chapter === chapter);
      if (stop) story.goToStop(stop, { instant });
    },
    goToStop(stop, { instant = false } = {}) {
      scrollTo(scrollOf(stop.pos), instant, timeline.stops.indexOf(stop));
    },
    next() {
      // in mid-glide, "next" means the stop after the one being glided to: presses queue, they do not start
      // the same glide over
      if (flight) {
        if (flight.stop + 1 < timeline.stops.length) glideTo(flight.stop + 1);
        else story.toEnd({ smooth: true });
        return;
      }
      const pos = (window.scrollY - startY) / unit;
      const i = currentStopIndex();
      const here = timeline.stops[i];
      // from between two stops, "next" goes to the one ahead; from a stop, to the one after it
      const ahead = here && here.pos > pos + 0.04 ? i : i + 1;
      if (ahead < timeline.stops.length) glideTo(ahead);
      else story.toEnd({ smooth: true });
    },
    prev() {
      if (flight) {
        if (flight.stop > 0) glideTo(flight.stop - 1);
        return;
      }
      const pos = (window.scrollY - startY) / unit;
      const i = currentStopIndex();
      const here = timeline.stops[i];
      const behind = here && here.pos < pos - 0.04 ? i : i - 1;
      if (behind >= 0) glideTo(behind);
    },
    toEnd({ smooth = false } = {}) {
      scrollTo(scrollOf(timeline.length), !smooth);
    },
    scrollOf,
    configure(next) {
      if (next.chapters) chapters = next.chapters;
      if (next.unit) unitOf = next.unit;
      // keep the visitor at the same place in the story across the change
      const stop = { chapter: state.chapter, phase: state.phase, hold: timeline.holdAt(state.chapter, state.pos), travel: timeline.travelAt(state.chapter, state.pos) };
      const inStory = state.scroll > 0 && state.scroll < timeline.length;
      const ended = state.scroll >= timeline.length;
      const past = Math.max(0, window.scrollY - scrollOf(timeline.length));
      // a glide in flight is heading for a pixel position of the old layout: stop it, and finish at the stop it
      // was heading for, in the new layout
      const heading = flight ? flight.stop : landing;
      landing = heading;
      if (flight && lenis) lenis.scrollTo(window.scrollY, { immediate: true, force: true });
      flight = null;
      timeline = buildTimeline(chapters, options.edges);
      measure();
      const c = timeline.chapters[stop.chapter];
      const jump = (top: number): void => {
        if (lenis) lenis.scrollTo(top, { immediate: true, force: true });
        else window.scrollTo({ top, behavior: "instant" as ScrollBehavior });
      };
      const target = heading >= 0 ? timeline.stops[heading] : undefined;
      if (target) jump(scrollOf(target.pos));
      else if (ended) jump(scrollOf(timeline.length) + past);
      else if (inStory && c) jump(scrollOf(stop.phase === "hold" ? c.holdStart + c.hold * stop.hold : c.start + c.travel * stop.travel));
      force = true;
      wake();
    },
    refresh() {
      measure();
      wake();
    },
    wake,
    setMode(next) {
      if (next === mode) return;
      mode = next;
      if (mode === "scrub") startLenis();
      else stopLenis();
      flight = null;
      force = true;
      wake();
    },
    get collapsed() {
      return collapsed;
    },
    setCollapsed(next) {
      if (next === collapsed) return;
      collapsed = next;
      flight = null;
      measure();
      wake();
    },
    destroy() {
      destroyed = true;
      cancelAnimationFrame(raf);
      stopLenis();
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", wake);
      window.removeEventListener("wheel", onInput);
      window.removeEventListener("touchstart", onInput);
      window.removeEventListener("touchmove", wake);
      document.removeEventListener("visibilitychange", wake);
      root.style.height = "";
    },
  };

  /** A field the visitor is typing in keeps its keys, unless it is a field left behind off screen (the focus
   *  stayed in it while the page scrolled away): the keys then belong to the story. */
  const editing = (target: Element | null): boolean => {
    const field = target?.closest?.(EDITABLE);
    if (!field) return false;
    const rect = field.getBoundingClientRect();
    return rect.bottom > 0 && rect.top < window.innerHeight;
  };
  /** A box of text the keys are in that can still scroll that way (`data-story-scroll`: a chapter longer than its
   *  panel) keeps the arrow and page keys until it reaches its end. */
  const scrolling = (target: Element | null, down: boolean): boolean => {
    const box = target?.closest?.<HTMLElement>("[data-story-scroll]");
    if (!box || box.scrollHeight - box.clientHeight < 2) return false;
    return down ? box.scrollTop + box.clientHeight < box.scrollHeight - 1 : box.scrollTop > 0;
  };
  const onKey = (event: KeyboardEvent): void => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    wake();
    if (collapsed || editing(event.target as Element | null)) return;
    const key = event.key;
    if ((key === "ArrowDown" || key === "PageDown" || key === "ArrowUp" || key === "PageUp") && scrolling(event.target as Element | null, key === "ArrowDown" || key === "PageDown")) return;
    // only while the story is on screen: past its end the keys scroll the page as they always do
    const pos = (window.scrollY - startY) / unit;
    if (pos > timeline.length + 0.02 || pos < -0.5) return;
    const atEnd = pos >= timeline.length - 0.02;
    switch (event.key) {
      case "ArrowDown":
      case "ArrowRight":
      case "PageDown":
        if (atEnd) return;
        event.preventDefault();
        // a key held down repeats: one stop at a time, each glide left to finish
        if (event.repeat && flight) return;
        story.next();
        break;
      case "ArrowUp":
      case "ArrowLeft":
      case "PageUp":
        event.preventDefault();
        if (event.repeat && flight) return;
        story.prev();
        break;
      case "Home":
        event.preventDefault();
        story.goTo(0);
        break;
      case "End":
        if (!options.endKey || atEnd) return;
        event.preventDefault();
        story.toEnd();
        break;
      default:
    }
  };
  // a wheel or a finger takes the scroll over from a glide
  const onInput = (): void => {
    flight = null;
    wake();
  };
  let resizeWidth = window.innerWidth;
  let resizeHeight = window.innerHeight;
  const onResize = (): void => {
    // a phone's toolbars change the height as the page scrolls: only a real change of size is a new layout
    const w = window.innerWidth, h = window.innerHeight;
    if (w === resizeWidth && Math.abs(h - resizeHeight) < 120) return;
    resizeWidth = w;
    resizeHeight = h;
    const hold = { chapter: state.chapter };
    void hold;
    story.configure({});
  };

  if (options.keyboard !== false) window.addEventListener("keydown", onKey);
  window.addEventListener("resize", onResize);
  window.addEventListener("scroll", wake, { passive: true });
  window.addEventListener("wheel", onInput, { passive: true });
  window.addEventListener("touchstart", onInput, { passive: true });
  window.addEventListener("touchmove", wake, { passive: true });
  document.addEventListener("visibilitychange", wake);
  measure();
  if (mode === "scrub") startLenis();
  compute();
  raf = requestAnimationFrame(frame);
  return story;
}
