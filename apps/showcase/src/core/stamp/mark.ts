// The mark a rubber stamp leaves: two lines of capitals in the stamp face inside a double-ruled rectangle, in
// vermilion, with worn and uneven ink (a wobbling edge, a thin bleed, grain, a few missing patches, heavier at
// one end; the small line is worn less, so it stays legible). One inline SVG, drawn in code; the seed decides the
// wear, so two stampings never look the same.

import { between, rng } from "./rng";

const NS = "http://www.w3.org/2000/svg";

/** The mark's own drawing size; it scales to any width. */
export const MARK_BOX = { width: 320, height: 124 } as const;
/** Height over width. */
export const MARK_RATIO = MARK_BOX.height / MARK_BOX.width;
/** The tilt of every stamping, in degrees (negative: rising to the right). */
export const MARK_TILT = -7;
/** How the words are set inside the frame (the die's face is lettered the same way): font size, baseline, and
 *  the length each line is spread to. */
export const MARK_TYPE = {
  first: { size: 62, y: 69, length: MARK_BOX.width - 62 },
  second: { size: 30.5, y: 102.5, length: MARK_BOX.width - 74 },
  alone: { size: 74, y: 84, length: MARK_BOX.width - 62 },
} as const;

export interface MarkOptions {
  /** The words: a large first line and a smaller second one. Default APPROVED / WITH CONDITIONS. */
  lines?: readonly [string, string?];
  /** Decides the wear. The same seed gives the same mark. Default 1. */
  seed?: number;
  /** Width in CSS pixels (the height follows). Default 320. */
  width?: number;
  /** Degrees. Default MARK_TILT. */
  tilt?: number;
  /** How worn the ink is: "full" for a stamping, "light" for a small copy where grain would only be noise,
   *  "none" for flat ink. Default "full". */
  wear?: "full" | "light" | "none";
  /** What a screen reader calls it. Default: "Stamped: " and the words. An empty string hides it from them. */
  label?: string;
}

export interface Mark {
  el: SVGSVGElement;
  width: number;
  height: number;
  /** The words on it, as one string. */
  text: string;
}

let marks = 0;

function node<K extends keyof SVGElementTagNameMap>(name: K, attrs: Record<string, string | number>): SVGElementTagNameMap[K] {
  const el = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  return el;
}

/**
 * Draw a mark. It is appended to `host` when one is given; the caller places it (the class `stamp-mark` centres
 * it on its left/top and turns it by its tilt; see stamp.css).
 */
export function renderMark(host: Element | null, options: MarkOptions = {}): Mark {
  const lines = options.lines ?? (["APPROVED", "WITH CONDITIONS"] as const);
  const seed = options.seed ?? 1;
  const width = options.width ?? MARK_BOX.width;
  const tilt = options.tilt ?? MARK_TILT;
  const wear = options.wear ?? "full";
  const text = lines.filter(Boolean).join(" ");
  const label = options.label ?? `Stamped: ${text}`;
  const r = rng(seed);
  const id = `stamp-mark-${++marks}`;
  const W = MARK_BOX.width;
  const H = MARK_BOX.height;

  const svg = node("svg", { viewBox: `0 0 ${W} ${H}`, width, height: Math.round(width * MARK_RATIO * 100) / 100, class: "stamp-mark", focusable: "false" });
  if (label) {
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label);
  } else svg.setAttribute("aria-hidden", "true");
  svg.style.setProperty("--mark-tilt", `${tilt}deg`);
  svg.dataset.seed = String(seed);

  const defs = node("defs", {});
  // the frame and the large word wear as one; the small line is inked through its own, kinder filter, so it can
  // still be read where the die came down light
  const group = node("g", { fill: "currentColor", stroke: "none" });
  const small = node("g", { fill: "currentColor", stroke: "none" });

  if (wear !== "none") {
    const s = Math.floor(between(r, 1, 900));
    const edge = wear === "full" ? 2.4 : 1.6;
    const filter = node("filter", { id: `${id}-ink`, x: "-4%", y: "-10%", width: "108%", height: "120%", "color-interpolation-filters": "sRGB" });
    // the edge wobbles, as rubber on paper does
    filter.append(
      node("feTurbulence", { type: "fractalNoise", baseFrequency: "0.04 0.06", numOctaves: 2, seed: s, result: "warp" }),
      node("feDisplacementMap", { in: "SourceGraphic", in2: "warp", scale: edge, xChannelSelector: "R", yChannelSelector: "G", result: "inked" }),
    );
    if (wear === "full") {
      // a thin bleed under the edge: the roughness comes from the wobble, not from softness
      const bleed = node("feComponentTransfer", { in: "blurred", result: "bleed" });
      bleed.append(node("feFuncA", { type: "linear", slope: 0.42 }));
      // grain: fine noise bites small holes out of the ink
      const grain = node("feColorMatrix", { in: "grainNoise", type: "matrix", values: `0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  ${(-3.4).toFixed(2)} 0 0 0 ${between(r, 2.42, 2.56).toFixed(2)}`, result: "grain" });
      // patches where the die never touched: slow noise, cut hard
      const patches = node("feColorMatrix", { in: "patchNoise", type: "matrix", values: `0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -14 0 0 0 ${between(r, 8.5, 9.1).toFixed(2)}`, result: "patches" });
      const merge = node("feMerge", {});
      merge.append(node("feMergeNode", { in: "bleed" }), node("feMergeNode", { in: "worn" }));
      filter.append(
        node("feGaussianBlur", { in: "inked", stdDeviation: 0.6, result: "blurred" }),
        bleed,
        node("feTurbulence", { type: "fractalNoise", baseFrequency: 0.85, numOctaves: 2, seed: s + 7, result: "grainNoise" }),
        grain,
        node("feTurbulence", { type: "fractalNoise", baseFrequency: "0.016 0.034", numOctaves: 2, seed: s + 13, result: "patchNoise" }),
        patches,
        node("feComposite", { in: "inked", in2: "grain", operator: "in", result: "grained" }),
        node("feComposite", { in: "grained", in2: "patches", operator: "in", result: "worn" }),
        merge,
      );
      // the small line: the same wobbling edge and a lighter grain, and no patches
      const filter2 = node("filter", { id: `${id}-ink2`, x: "-4%", y: "-20%", width: "108%", height: "140%", "color-interpolation-filters": "sRGB" });
      filter2.append(
        node("feTurbulence", { type: "fractalNoise", baseFrequency: "0.04 0.06", numOctaves: 2, seed: s, result: "warp" }),
        node("feDisplacementMap", { in: "SourceGraphic", in2: "warp", scale: 1.5, xChannelSelector: "R", yChannelSelector: "G", result: "inked" }),
        node("feTurbulence", { type: "fractalNoise", baseFrequency: 0.85, numOctaves: 2, seed: s + 7, result: "grainNoise" }),
        node("feColorMatrix", { in: "grainNoise", type: "matrix", values: "0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -3.4 0 0 0 2.72", result: "grain" }),
        node("feComposite", { in: "inked", in2: "grain", operator: "in" }),
      );
      // heavier at one end: the hand never comes down flat
      const heavyLeft = r() < 0.5;
      const light = between(r, 0.62, 0.74);
      const press = node("linearGradient", { id: `${id}-press`, x1: 0, y1: 0, x2: 1, y2: between(r, -0.15, 0.15).toFixed(2) });
      press.append(
        node("stop", { offset: 0, "stop-color": "#fff", "stop-opacity": heavyLeft ? 1 : light }),
        node("stop", { offset: between(r, 0.4, 0.6).toFixed(2), "stop-color": "#fff", "stop-opacity": heavyLeft ? 0.96 : 0.9 }),
        node("stop", { offset: 1, "stop-color": "#fff", "stop-opacity": heavyLeft ? light : 1 }),
      );
      const mask = node("mask", { id: `${id}-mask`, maskUnits: "userSpaceOnUse", x: -10, y: -10, width: W + 20, height: H + 20 });
      mask.append(node("rect", { x: -10, y: -10, width: W + 20, height: H + 20, fill: `url(#${id}-press)` }));
      // the small line is never lighter than about four fifths
      const press2 = node("linearGradient", { id: `${id}-press2`, x1: 0, y1: 0, x2: 1, y2: 0 });
      press2.append(
        node("stop", { offset: 0, "stop-color": "#fff", "stop-opacity": heavyLeft ? 1 : 0.84 }),
        node("stop", { offset: 1, "stop-color": "#fff", "stop-opacity": heavyLeft ? 0.84 : 1 }),
      );
      const mask2 = node("mask", { id: `${id}-mask2`, maskUnits: "userSpaceOnUse", x: -10, y: -10, width: W + 20, height: H + 20 });
      mask2.append(node("rect", { x: -10, y: -10, width: W + 20, height: H + 20, fill: `url(#${id}-press2)` }));
      defs.append(press, mask, press2, mask2, filter2);
      group.setAttribute("mask", `url(#${id}-mask)`);
      small.setAttribute("mask", `url(#${id}-mask2)`);
      small.setAttribute("filter", `url(#${id}-ink2)`);
    } else small.setAttribute("filter", `url(#${id}-ink)`);
    defs.append(filter);
    group.setAttribute("filter", `url(#${id}-ink)`);
  }

  // the double rule: a heavy frame and a hairline inside it, cut from one shape so the ink is one layer
  const frame = node("path", {
    "fill-rule": "evenodd",
    d:
      `M3 5a2 2 0 0 1 2-2h${W - 10}a2 2 0 0 1 2 2v${H - 10}a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z` +
      `M9.5 9.5v${H - 19}h${W - 19}V9.5z` +
      `M14 14h${W - 28}v${H - 28}H14z` +
      `M16 16v${H - 32}h${W - 32}V16z`,
  });
  const set = lines[1] ? MARK_TYPE.first : MARK_TYPE.alone;
  const first = node("text", { x: W / 2, y: set.y, "text-anchor": "middle", "font-size": set.size, "font-weight": 800, textLength: set.length, lengthAdjust: "spacingAndGlyphs" });
  first.textContent = lines[0];
  first.style.fontFamily = "var(--font-stamp)";
  group.append(frame, first);
  if (lines[1]) {
    const second = node("text", { x: W / 2, y: MARK_TYPE.second.y, "text-anchor": "middle", "font-size": MARK_TYPE.second.size, "font-weight": 800, textLength: MARK_TYPE.second.length, lengthAdjust: "spacing" });
    second.textContent = lines[1];
    second.style.fontFamily = "var(--font-stamp)";
    small.append(second);
  }

  svg.append(defs, group);
  if (lines[1]) svg.append(small);
  host?.append(svg);
  return { el: svg, width, height: width * MARK_RATIO, text };
}
