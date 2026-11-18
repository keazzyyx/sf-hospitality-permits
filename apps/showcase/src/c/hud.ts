// What is written over the map, each on its own plate of paper so no line of the map runs through it: a legend
// (a north arrow that turns with the camera, a scale bar true to it, and the latitude and longitude under the
// pointer while the pointer is on the map), the case number of the motion under the pointer, a caption for the
// search's state, a few matches named where they stand, and the hairline from a result card to its motion, ending
// in a ring at the top of its stack. Plain DOM over the canvas; nothing here takes a click.

import { formatLatLon, formatLength, niceLength } from "../core/world/projection";

const NS = "http://www.w3.org/2000/svg";

export interface Hud {
  root: HTMLElement;
  setMode(mode: string): void;
  /** The place under the pointer; null when the pointer is not on the map (the line is then left out). */
  setReadout(lat: number | null, lon: number | null): void;
  /** The camera's heading (degrees clockwise from north): the arrow points north on the screen. */
  setNorth(heading: number): void;
  /** Metres per CSS pixel at the middle of the view. */
  setScale(metresPerPixel: number): void;
  /** The label of the motion under the pointer, at a point of the window; null hides it. */
  setTag(text: string | null, x?: number, y?: number): void;
  /** One of up to five matches named where it stands (a search with few matches); null takes it away. */
  setMark(index: number, text: string | null, x?: number, y?: number): void;
  setCaption(html: string): void;
  /** A hairline from a point of the window to a stack's top, ending in a small ring and the stack's case number;
   *  null takes it away. */
  setWire(from: { x: number; y: number } | null, to?: { x: number; y: number }, label?: string): void;
  /** The part of the window the map is seen in (window pixels): labels keep inside it. */
  setWindow(box: { x: number; y: number; w: number; h: number }, top: number, wide: boolean): void;
}

/** A small plate that names a point: hung to the right of it, or to its left where the right is too near the
 *  edge of the map's window; kept inside that window. */
function plate(className: string): { el: HTMLElement; set(text: string | null, x: number, y: number, box: Box): void } {
  const el = document.createElement("p");
  el.className = className;
  const leader = document.createElement("i");
  const words = document.createElement("span");
  el.append(leader, words);
  let last = "";
  let w = 0;
  let side = "";
  return {
    el,
    set(text, x, y, box) {
      if (text === null) {
        if (last !== "") {
          last = "";
          el.classList.remove("is-on");
        }
        return;
      }
      if (text !== last) {
        last = text;
        words.textContent = text;
        el.classList.add("is-on");
        w = el.offsetWidth;
      }
      // its own place: up and to the right of the point, on a short leader
      let left = x + 12;
      let flip = false;
      if (left + w > box.x + box.w - 12) {
        left = x - 12 - w;
        flip = true;
      }
      left = Math.max(box.x + 12, Math.min(left, box.x + box.w - 12 - w));
      const top = Math.max(box.y - box.top + 6, Math.min(y - box.top - 26, box.y - box.top + box.h - 28));
      const s = flip ? "left" : "right";
      if (s !== side) {
        side = s;
        el.dataset.side = s;
      }
      el.style.transform = `translate3d(${Math.round(left)}px, ${Math.round(top)}px, 0)`;
    },
  };
}

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
  top: number;
}

export function createHud(): Hud {
  const root = document.createElement("div");
  root.className = "c-hud";
  root.setAttribute("aria-hidden", "true");
  root.dataset.mode = "gate";

  // ---- the legend ----
  const legend = document.createElement("div");
  legend.className = "c-readout";
  const row = document.createElement("div");
  row.className = "c-readout__row";
  const north = document.createElementNS(NS, "svg");
  north.setAttribute("class", "c-north");
  north.setAttribute("viewBox", "-12 -12 24 24");
  north.setAttribute("width", "24");
  north.setAttribute("height", "24");
  const arrow = document.createElementNS(NS, "g");
  const needle = document.createElementNS(NS, "path");
  needle.setAttribute("d", "M0 -9 L3.6 5 L0 2.6 L-3.6 5 Z");
  arrow.append(needle);
  north.append(arrow);
  const scale = document.createElement("div");
  scale.className = "c-scale";
  const bar = document.createElement("i");
  const scaleText = document.createElement("span");
  scale.append(bar, scaleText);
  row.append(north, scale);
  const where = document.createElement("div");
  where.className = "c-readout__where";
  const value = document.createElement("b");
  where.append(value);
  legend.append(row, where);

  const caption = document.createElement("p");
  caption.className = "c-caption";
  const tag = plate("c-tag");
  const marks = Array.from({ length: 5 }, () => plate("c-tag c-tag--mark"));
  const wireLabel = plate("c-tag c-tag--wire");
  const wire = document.createElementNS(NS, "svg");
  wire.setAttribute("class", "c-wire");
  const line = document.createElementNS(NS, "line");
  const ring = document.createElementNS(NS, "circle");
  ring.setAttribute("r", "5.5");
  wire.append(line, ring);
  root.append(wire, legend, caption, ...marks.map(m => m.el), wireLabel.el, tag.el);

  const box: Box = { x: 0, y: 64, w: 1, h: 1, top: 64 };
  let lastReadout = "", lastScale = -1, lastNorth = NaN;
  return {
    root,
    setMode(mode) {
      root.dataset.mode = mode;
    },
    setReadout(lat, lon) {
      const text = lat === null || lon === null ? "" : formatLatLon(lat, lon);
      if (text !== lastReadout) {
        lastReadout = text;
        value.textContent = text;
        where.classList.toggle("is-on", text !== "");
      }
    },
    setNorth(heading) {
      const deg = Math.round(-heading * 2) / 2;
      if (deg === lastNorth) return;
      lastNorth = deg;
      arrow.setAttribute("transform", `rotate(${deg})`);
    },
    setScale(metresPerPixel) {
      if (!Number.isFinite(metresPerPixel) || metresPerPixel <= 0) return;
      const length = niceLength(metresPerPixel * 110);
      const px = Math.round(length / metresPerPixel);
      const key = length * 1000 + px;
      if (key === lastScale) return;
      lastScale = key;
      bar.style.width = `${px}px`;
      scaleText.textContent = formatLength(length);
    },
    setTag(text, x = 0, y = 0) {
      tag.set(text, x, y, box);
    },
    setMark(index, text, x = 0, y = 0) {
      marks[index]?.set(text, x, y, box);
    },
    setCaption(html) {
      if (caption.innerHTML !== html) caption.innerHTML = html;
    },
    setWire(from, to, label) {
      if (!from || !to) {
        wire.classList.remove("is-on");
        wireLabel.set(null, 0, 0, box);
        return;
      }
      // the line stops at the ring: the ring is round the stack's top, not on it
      const x2 = to.x, y2 = to.y - box.top;
      const x1 = from.x, y1 = from.y - box.top;
      const len = Math.hypot(x2 - x1, y2 - y1) || 1;
      const k = Math.max(0, (len - 6.5) / len);
      line.setAttribute("x1", x1.toFixed(1));
      line.setAttribute("y1", y1.toFixed(1));
      line.setAttribute("x2", (x1 + (x2 - x1) * k).toFixed(1));
      line.setAttribute("y2", (y1 + (y2 - y1) * k).toFixed(1));
      ring.setAttribute("cx", x2.toFixed(1));
      ring.setAttribute("cy", y2.toFixed(1));
      wire.classList.add("is-on");
      wireLabel.set(label ?? null, to.x, to.y, box);
    },
    setWindow(next, headerHeight, wide) {
      box.x = next.x;
      box.y = next.y;
      box.w = next.w;
      box.h = next.h;
      box.top = headerHeight;
      root.classList.toggle("is-wide", wide);
      // the legend keeps one right-hand edge in every state: the page's gutter, under the theme button
      legend.style.bottom = `${Math.max(12, window.innerHeight - (next.y + next.h) + 18)}px`;
      caption.style.left = `${next.x + (wide ? 24 : 12)}px`;
      caption.style.top = `${next.y - headerHeight + (wide ? 18 : 0)}px`;
    },
  };
}
