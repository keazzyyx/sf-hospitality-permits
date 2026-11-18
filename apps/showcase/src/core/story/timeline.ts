// The story's one timeline. Chapters declare how long the camera travels to them and how long it then holds;
// the timeline lays them end to end, in "screens" of scroll, and answers "where are we" for any position.
// Pure arithmetic: no DOM, no three.js.

export interface ChapterSpec {
  id: string;
  title: string;
  /** Screens of scroll while the camera travels to this chapter. No text is on screen. 0 for the first. */
  travel: number;
  /** Screens of scroll while the camera holds, the text is on screen and the drawing changes. */
  hold: number;
  /** The hold is a run of this many discrete steps (one condition, one highlight at a time). */
  steps?: number;
  /** For a stepped chapter: "each" (the default) puts a stop on every step; "one" puts a single stop on the
   *  chapter (at REST of its hold), so the arrow keys pass it in one press while the scroll still scrubs its steps. */
  stops?: "each" | "one";
}

export interface Chapter extends ChapterSpec {
  index: number;
  /** Where its travel starts (equals holdStart when there is none). */
  start: number;
  /** Where its hold starts. */
  holdStart: number;
  /** Where its hold ends. */
  end: number;
}

/** How the text and the frame come and go at the two ends of a hold, in screens. */
export interface Edges {
  /** The frame moves aside over this much at the start of a hold… */
  frameIn: number;
  /** …and the text follows, starting this late and taking this long. */
  textDelay: number;
  textIn: number;
  /** At the end the text leaves over this much, ending this long before the hold ends… */
  textOut: number;
  textLead: number;
  /** …and the frame returns over the last of the hold. */
  frameOut: number;
}

export const EDGES: Edges = { frameIn: 0.2, textDelay: 0.06, textIn: 0.16, textOut: 0.12, textLead: 0.08, frameOut: 0.16 };

/** The part of a stepped hold the steps share, as fractions of the hold. */
export const STEP_RANGE = { from: 0.14, to: 0.9 } as const;
/** Where in a hold (or in a step) a visitor is put by the rail and the arrow keys: the drawing is complete, the
 *  text is fully in. A chapter's drawing must be done by this point. */
export const REST = 0.72;

export interface Located {
  /** The chapter being travelled to or held on. */
  chapter: number;
  phase: "travel" | "hold";
  /** 0 to 1 through the travel (1 during the hold). */
  travel: number;
  /** 0 to 1 through the hold (0 during the travel). */
  hold: number;
}

export interface Timeline {
  chapters: Chapter[];
  /** Total length in screens. */
  length: number;
  locate(pos: number): Located;
  /** 0 to 1 through chapter i's hold at a position: 0 before it, 1 after it. */
  holdAt(i: number, pos: number): number;
  /** 0 to 1 through chapter i's travel at a position. */
  travelAt(i: number, pos: number): number;
  /** 0 to 1: how much of chapter i's text shows at a position. */
  textAt(i: number, pos: number): number;
  /** 0 to 1: how far the frame has moved aside for chapter i's text at a position. */
  frameAt(i: number, pos: number): number;
  /** The step of a stepped chapter at a position: its index (-1 before the first) and 0 to 1 through it. */
  stepAt(i: number, pos: number): { index: number; t: number };
  /** The positions a visitor is put at by the rail and the arrow keys, in order. One per chapter, or one per
   *  step of a stepped chapter. */
  stops: Stop[];
  /** The stop nearest a position. */
  nearestStop(pos: number): Stop;
}

export interface Stop {
  pos: number;
  chapter: number;
  /** The step this stop shows, or -1. */
  step: number;
}

const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v);
const ramp = (pos: number, from: number, length: number): number => (length <= 0 ? (pos >= from ? 1 : 0) : clamp01((pos - from) / length));

/** Lay the chapters end to end. */
export function buildTimeline(specs: ChapterSpec[], edges: Edges = EDGES): Timeline {
  const chapters: Chapter[] = [];
  let at = 0;
  specs.forEach((spec, index) => {
    const start = at;
    const holdStart = start + spec.travel;
    const end = holdStart + spec.hold;
    chapters.push({ ...spec, index, start, holdStart, end });
    at = end;
  });
  const length = at;
  const last = chapters.length - 1;

  const holdAt = (i: number, pos: number): number => {
    const c = chapters[i];
    if (!c) return 0;
    return c.hold > 0 ? clamp01((pos - c.holdStart) / c.hold) : pos >= c.holdStart ? 1 : 0;
  };
  const travelAt = (i: number, pos: number): number => {
    const c = chapters[i];
    if (!c) return 0;
    return c.travel > 0 ? clamp01((pos - c.start) / c.travel) : pos >= c.start ? 1 : 0;
  };
  // the first chapter is already in at position 0; a chapter with no hold has no text
  const come = (c: Chapter, pos: number, delay: number, length_: number): number =>
    c.index === 0 ? 1 : ramp(pos, c.holdStart + delay, length_);
  const go = (c: Chapter, pos: number, lead: number, length_: number): number =>
    1 - ramp(pos, c.end - lead - length_, length_);
  const textAt = (i: number, pos: number): number => {
    const c = chapters[i];
    if (!c || c.hold <= 0) return 0;
    if (pos < c.holdStart && c.index !== 0) return 0;
    return Math.min(come(c, pos, edges.textDelay, edges.textIn), go(c, pos, edges.textLead, edges.textOut));
  };
  const frameAt = (i: number, pos: number): number => {
    const c = chapters[i];
    if (!c || c.hold <= 0) return 0;
    if (pos < c.holdStart && c.index !== 0) return 0;
    return Math.min(come(c, pos, 0, edges.frameIn), go(c, pos, 0, edges.frameOut));
  };
  const stepAt = (i: number, pos: number): { index: number; t: number } => {
    const c = chapters[i];
    const n = c?.steps ?? 0;
    if (!c || n <= 0) return { index: -1, t: 0 };
    const h = holdAt(i, pos);
    const k = ((h - STEP_RANGE.from) / (STEP_RANGE.to - STEP_RANGE.from)) * n;
    if (k < 0) return { index: -1, t: 0 };
    const index = Math.min(n - 1, Math.floor(k));
    return { index, t: clamp01(k - index) };
  };

  const stops: Stop[] = [];
  for (const c of chapters) {
    // a stop never sits inside the text's way out: a visitor put there by a key would be left on a greyed panel
    const latest = Math.max(c.holdStart, c.end - edges.textLead - edges.textOut - 0.02);
    if (c.index === 0) stops.push({ pos: 0, chapter: 0, step: -1 });
    else if (c.hold <= 0) stops.push({ pos: c.end, chapter: c.index, step: -1 });
    else if (c.steps && c.steps > 0 && c.stops !== "one") {
      const span = (STEP_RANGE.to - STEP_RANGE.from) / c.steps;
      for (let k = 0; k < c.steps; k++) stops.push({ pos: Math.min(latest, c.holdStart + c.hold * (STEP_RANGE.from + span * (k + REST))), chapter: c.index, step: k });
    } else {
      const pos = Math.min(latest, c.holdStart + c.hold * REST);
      stops.push({ pos, chapter: c.index, step: c.steps && c.steps > 0 ? stepAt(c.index, pos).index : -1 });
    }
  }

  return {
    chapters,
    length,
    locate(pos) {
      const p = Math.min(length, Math.max(0, pos));
      let i = 0;
      while (i < last && p >= chapters[i]!.end) i++;
      const c = chapters[i]!;
      const inHold = p >= c.holdStart;
      return { chapter: i, phase: inHold ? "hold" : "travel", travel: travelAt(i, p), hold: inHold ? holdAt(i, p) : 0 };
    },
    holdAt,
    travelAt,
    textAt,
    frameAt,
    stepAt,
    stops,
    nearestStop(pos) {
      let best = stops[0]!;
      for (const s of stops) if (Math.abs(s.pos - pos) < Math.abs(best.pos - pos)) best = s;
      return best;
    },
  };
}

/** v mapped from [a, b] to [0, 1], clamped: for a drawing change that takes part of a hold. */
export function range(v: number, a: number, b: number): number {
  return clamp01((v - a) / (b - a));
}

export const ease = {
  inOut: (t: number): number => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2),
  out: (t: number): number => 1 - (1 - t) ** 3,
  in: (t: number): number => t * t * t,
  /** Past the end and back: for things that pop up. */
  back: (t: number): number => 1 + 2.2 * (t - 1) ** 3 + 1.2 * (t - 1) ** 2,
  /** The frame's slide: quick away, long settle. */
  slide: (t: number): number => 1 - (1 - t) ** 4,
};
