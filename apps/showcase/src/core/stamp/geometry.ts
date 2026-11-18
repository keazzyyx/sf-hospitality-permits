// Where an element's own pixels are on the screen, whatever turns or shifts it or its ancestors (rotation, a
// parallax shift, a shake): measured from two probes at its corners, so no transform has to be parsed.

export interface Point {
  x: number;
  y: number;
}

export interface Frame {
  /** The element's own width and height (before any transform). */
  width: number;
  height: number;
  /** Rotation on the screen, in radians. */
  angle: number;
  /** Size on the screen over its own size. */
  scale: number;
  /** A point of the element (pixels from its top left corner) as a point of the viewport. */
  toClient(x: number, y: number): Point;
  /** A point of the viewport as a point of the element. */
  toLocal(clientX: number, clientY: number): Point;
}

/** Measure `el` now. It must be able to hold absolutely positioned children (anything but position: static). */
export function frameOf(el: HTMLElement): Frame {
  const width = el.offsetWidth;
  const height = el.offsetHeight;
  const probe = (left: string): Point => {
    const p = document.createElement("i");
    p.style.cssText = `position:absolute;left:${left};top:0;width:0;height:0;pointer-events:none`;
    el.append(p);
    const r = p.getBoundingClientRect();
    p.remove();
    return { x: r.left, y: r.top };
  };
  // the probes sit on the padding box: step back over the border to the element's corner
  const style = getComputedStyle(el);
  const bl = parseFloat(style.borderLeftWidth) || 0;
  const bt = parseFloat(style.borderTopWidth) || 0;
  const o = probe("0");
  const e = probe("100%");
  const inner = el.clientWidth || 1;
  const ux = (e.x - o.x) / inner;
  const uy = (e.y - o.y) / inner;
  const origin = { x: o.x - ux * bl + uy * bt, y: o.y - uy * bl - ux * bt };
  const scale = Math.hypot(ux, uy) || 1;
  const angle = Math.atan2(uy, ux);
  return {
    width,
    height,
    angle,
    scale,
    toClient: (x, y) => ({ x: origin.x + ux * x - uy * y, y: origin.y + uy * x + ux * y }),
    toLocal: (cx, cy) => {
      const dx = cx - origin.x;
      const dy = cy - origin.y;
      const s2 = scale * scale;
      return { x: (dx * ux + dy * uy) / s2, y: (-dx * uy + dy * ux) / s2 };
    },
  };
}
