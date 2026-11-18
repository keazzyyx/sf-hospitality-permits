// The gate as plain DOM, on the first paint: the motion sheet (a facsimile set in type from the public record,
// never a scan) lying on the ground plane, the button, the place for a pencil note. Nothing here moves: gate.ts
// brings it to life once its chunk has loaded, and the scene lays the plane on the grid frame by frame.

import { dayAsPrinted, SHEET } from "./content";
import { gatePose, SHEET_H, SHEET_W, sheetCorners, sheetWidthPx, type View } from "./poses";
import { matrix3d, projector, quadHomography, type Homography } from "./project";

export interface GateDom {
  /** The whole gate: a fixed layer under the header. A press anywhere on it charges the stamp. */
  root: HTMLElement;
  /** The city's outline, drawn in the first paint under the sheet until the streets arrive. */
  outline: SVGSVGElement;
  /** Everything that shakes together: the sheet and the stamp over it. */
  stage: HTMLElement;
  /** The ground plane as the camera sees it: its transform is the homography. */
  plane: HTMLElement;
  /** The motion as it lies there (first page and the edges of the pages under it): the mark goes on this, and
   *  this is what cracks. */
  stack: HTMLElement;
  note: HTMLElement;
  button: HTMLButtonElement;
  live: HTMLElement;
}

function tag<K extends keyof HTMLElementTagNameMap>(name: K, className = "", text = ""): HTMLElementTagNameMap[K] {
  const el = document.createElement(name);
  if (className) el.className = className;
  if (text) el.textContent = text;
  return el;
}

/** Ruled lines standing for a paragraph of body text. */
function ruled(n: number, last: number): HTMLElement {
  const block = tag("div", "c-motion__ruled");
  block.setAttribute("aria-hidden", "true");
  for (let i = 0; i < n; i++) {
    const line = tag("i");
    if (i === n - 1) line.style.width = `${last}%`;
    block.append(line);
  }
  return block;
}

function buildSheet(): HTMLElement {
  const sheet = tag("article", "c-motion");
  sheet.setAttribute("aria-label", `Planning Commission Motion No. ${SHEET.motion}, set in type from the public record. A facsimile of its first page, not a scan.`);
  const staple = tag("span", "c-motion__staple");
  staple.setAttribute("aria-hidden", "true");
  const head = tag("header", "c-motion__head");
  head.append(tag("p", "c-motion__title", `Planning Commission Motion No. ${SHEET.motion}`), tag("p", "c-motion__hearing", `HEARING DATE: ${dayAsPrinted(SHEET.hearing)}`));
  const fields = tag("dl", "c-motion__fields");
  const field = (label: string, lines: string[]): void => {
    const dd = tag("dd");
    lines.forEach((line, i) => {
      if (i) dd.append(tag("br"));
      dd.append(line);
    });
    fields.append(tag("dt", "", label), dd);
  };
  field("Case No.:", [SHEET.record]);
  field("Project Address:", [SHEET.streets]);
  field("Zoning:", [`${SHEET.zoning.code} (${SHEET.zoning.name})`, ...SHEET.zoning.also]);
  field("Landmark:", [SHEET.landmark]);
  field("Block/Lot:", [SHEET.blockLot]);
  const quote = (i: number): HTMLElement => tag("p", "c-motion__line", SHEET.findings[i]?.quote ?? "");
  const foot = tag("footer", "c-motion__foot");
  foot.append(tag("span", "", `Motion No. ${SHEET.motion}`), tag("span", "", `Case No. ${SHEET.record}`));
  sheet.append(
    staple,
    head,
    fields,
    tag("p", "c-motion__asked", SHEET.asked),
    tag("p", "c-motion__section", "Preamble"),
    ruled(3, 62),
    tag("p", "c-motion__section", "Findings"),
    ruled(2, 100),
    quote(0),
    ruled(2, 44),
    quote(2),
    ruled(3, 78),
    quote(4),
    ruled(2, 55),
    foot,
  );
  return sheet;
}

/** `live` is the page's own status line (it outlives the gate, so the gate's last words are heard). */
export function buildGate(reduced: boolean, live: HTMLElement): GateDom {
  const root = tag("div", "c-gate");
  root.setAttribute("role", "region");
  root.setAttribute("aria-label", "The opening: stamp the motion to begin");
  root.dataset.gate = "idle";
  if (reduced) root.classList.add("c-gate--still");
  const outline = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  outline.setAttribute("class", "c-outline");
  outline.setAttribute("aria-hidden", "true");
  outline.setAttribute("focusable", "false");
  outline.append(document.createElementNS("http://www.w3.org/2000/svg", "path"));
  const stage = tag("div", "c-gate__stage");
  const plane = tag("div", "c-plane");
  const stack = tag("div", "c-stack");
  const under = tag("div", "c-under");
  under.setAttribute("aria-hidden", "true");
  stack.append(under, buildSheet());
  plane.append(stack);
  stage.append(plane);

  const prompt = tag("p", "c-gate__prompt");
  const button = tag("button", "c-gate__button");
  button.type = "button";
  button.append(tag("span", "", reduced ? "Stamp it" : "Press and hold to stamp"));
  if (!reduced) {
    const key = tag("kbd", "c-gate__key", "Space");
    key.setAttribute("aria-hidden", "true");
    button.append(key, tag("span", "vh", " Hold Space or Enter, or press Enter once to stamp at once."));
  }
  prompt.append(button);
  const note = tag("p", "c-gate__note");
  note.setAttribute("aria-hidden", "true");
  root.append(outline, stage, prompt, note);
  return { root, outline, stage, plane, stack, note, button, live };
}

/** The sheet's place on the screen for a camera: the homography of its plane. `project` is the scene's own
 *  projection once there is one; before that (the first paint) the gate's resting pose is worked out here. */
export function sheetHomography(
  _view: View,
  corners: readonly { x: number; z: number }[],
  project: (x: number, y: number, z: number, out: { x: number; y: number; behind: boolean }) => { x: number; y: number; behind: boolean },
): Homography {
  const quad = corners.map(c => {
    const p = project(c.x, 0, c.z, { x: 0, y: 0, behind: false });
    return { x: p.x, y: p.y };
  });
  return quadHomography(SHEET_W, SHEET_H, quad);
}

/** Lay the plane for the first paint, from the gate's resting pose. Returns the corners on the ground. */
export function layFirst(dom: GateDom, view: View): { x: number; z: number }[] {
  const pose = gatePose(view);
  const corners = sheetCorners(pose, view, sheetWidthPx(view));
  dom.plane.style.transform = matrix3d(sheetHomography(view, corners, projector(pose, view.w, view.h)));
  return corners;
}
