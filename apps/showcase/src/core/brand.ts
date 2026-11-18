// The product name will change: it is written here and nowhere else. Change WORDMARK and every page follows.

import { SITE } from "./site";

/** The working name of the product. */
export const WORDMARK = "Working Title";

const NS = "http://www.w3.org/2000/svg";
const STAMP_FACE = '"Big Shoulders Display"';

export interface MarkOptions {
  /** Height of the mark in CSS pixels (the width follows the wordmark). Default 30. */
  height?: number;
  /** The words on the mark. Default WORDMARK. */
  label?: string;
}

/** A rough width for condensed capitals, used until the stamp face has loaded and the text can be measured. */
function estimateWidth(text: string, fontSize: number): number {
  let em = 0;
  for (const ch of text) em += ch === " " ? 0.2 : /[IJ1.,:'-]/.test(ch) ? 0.26 : /[MW]/.test(ch) ? 0.62 : 0.44;
  return (em + text.length * 0.07) * fontSize;
}

/**
 * The mark: a small double-ruled, stamp-like rectangle holding the wordmark in the stamp face. Drawn in code as
 * one SVG, coloured by --stamp, sized to the words: a longer or shorter name needs no other change.
 */
export function createMark({ height = 30, label = WORDMARK }: MarkOptions = {}): SVGSVGElement {
  const text = label.toUpperCase();
  const fontSize = height * 0.6;
  const padX = height * 0.42;

  const svg = document.createElementNS(NS, "svg");
  svg.classList.add("mark");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", label);
  svg.setAttribute("height", String(height));

  const outer = document.createElementNS(NS, "rect");
  const inner = document.createElementNS(NS, "rect");
  for (const r of [outer, inner]) {
    r.setAttribute("fill", "none");
    r.setAttribute("stroke", "currentColor");
  }
  outer.setAttribute("stroke-width", "1.5");
  inner.setAttribute("stroke-width", "0.75");

  const words = document.createElementNS(NS, "text");
  words.textContent = text;
  words.setAttribute("text-anchor", "middle");
  words.setAttribute("fill", "currentColor");
  words.setAttribute("font-size", String(fontSize));
  words.setAttribute("font-weight", "800");
  words.setAttribute("lengthAdjust", "spacing");
  words.setAttribute("aria-hidden", "true");
  words.style.fontFamily = "var(--font-stamp)";
  words.style.letterSpacing = "0.07em";
  // capitals sit centred in the box: baseline = middle + half the cap height (0.72 em in the stamp face)
  words.setAttribute("y", String(height / 2 + fontSize * 0.36));

  svg.append(outer, inner, words);

  const layout = (textWidth: number): void => {
    const width = Math.ceil(textWidth + padX * 2);
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("width", String(width));
    outer.setAttribute("x", "0.75");
    outer.setAttribute("y", "0.75");
    outer.setAttribute("width", String(width - 1.5));
    outer.setAttribute("height", String(height - 1.5));
    inner.setAttribute("x", "3.5");
    inner.setAttribute("y", "3.5");
    inner.setAttribute("width", String(width - 7));
    inner.setAttribute("height", String(height - 7));
    words.setAttribute("x", String(width / 2));
    // the words always fill the measured width, whatever face is showing, so the mark never changes size mid-paint
    words.setAttribute("textLength", String(Math.round(textWidth * 100) / 100));
  };
  layout(estimateWidth(text, fontSize));

  // once the stamp face is in, measure the words as it sets them and settle the width for good
  // (measured on a copy that never had a textLength: taking the attribute off the words themselves makes WebKit
  // log "Invalid value for <text> attribute textLength")
  const settle = (): void => {
    if (!svg.isConnected) return;
    const probe = document.createElementNS(NS, "text");
    probe.textContent = text;
    probe.setAttribute("font-size", String(fontSize));
    probe.setAttribute("font-weight", "800");
    probe.setAttribute("visibility", "hidden");
    probe.setAttribute("aria-hidden", "true");
    probe.style.fontFamily = "var(--font-stamp)";
    probe.style.letterSpacing = "0.07em";
    svg.append(probe);
    const natural = probe.getComputedTextLength();
    probe.remove();
    if (natural > 0) layout(natural);
  };
  try {
    // (a face that cannot be had leaves the estimate: not an error)
    document.fonts
      .load(`800 ${fontSize}px ${STAMP_FACE}`, text)
      .then(() => {
        if (svg.isConnected) settle();
        else requestAnimationFrame(settle);
      })
      .catch(() => {});
  } catch {
    // no Font Loading API: the estimate stands
  }
  return svg;
}

/** The mark as a link home (top left of every page). */
export function createMarkLink(href: string, options?: MarkOptions): HTMLAnchorElement {
  const a = document.createElement("a");
  a.className = "mark-link";
  a.href = href;
  a.setAttribute("aria-label", `${options?.label ?? WORDMARK}: ${SITE ? "front page" : "contents"}`);
  const mark = createMark(options);
  mark.removeAttribute("role");
  mark.removeAttribute("aria-label");
  mark.setAttribute("aria-hidden", "true");
  a.append(mark);
  return a;
}

/** Set the tab's title: "<part> · <wordmark>". The static <title> in each page holds no product name. On the public
 *  site the static title stands ("SF Conditions Search", "Coverage · SF Conditions Search"). */
export function setPageTitle(part: string): void {
  if (SITE) return;
  document.title = part ? `${part} · ${WORDMARK}` : WORDMARK;
}
