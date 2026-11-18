// What a renderer needs to draw the stamp at one instant, and what a renderer is.

/** The stamp at one instant, in the stage's CSS pixels. */
export interface StampPose {
  /** Where the centre of the die would touch the page. */
  x: number;
  y: number;
  /** Height of the die's face above the page. */
  h: number;
  /** Lean toward the right of the page, in radians (the top goes right). */
  leanX: number;
  /** Lean toward the viewer, in radians (the top comes down the screen). */
  leanZ: number;
  /** How far the stamp is squashed, 0 to about 0.25 (shorter and wider). */
  squash: number;
  /** 0 standing, 1 lying on its back with the inked face showing. */
  lying: number;
  /** Opacity of the whole stamp, 0 to 1. */
  alpha: number;
  /** How much nearer the viewer it has come (after a stamping it is lifted clear of the mark): 0 to about 0.06,
   *  drawn as that much larger. */
  zoom: number;
}

export interface StampRenderer {
  /** The element to put on the stage (it fills the stage and takes no pointer events). */
  readonly el: HTMLElement;
  /** The stage changed size, or the die did. */
  resize(stageWidth: number, stageHeight: number, dieWidth: number): void;
  draw(pose: StampPose): void;
  /** The theme changed: take the new colours (the three.js renderer eases to them). Returns true while easing. */
  setPalette(): void;
  /** True while the renderer has something of its own still moving (a palette ease). */
  busy(): boolean;
  destroy(): void;
}

/** A colour as the page computes it, as [r, g, b] in 0 to 1 (sRGB). */
export function cssColor(scope: Element, value: string): [number, number, number] {
  const probe = document.createElement("span");
  probe.style.cssText = `position:absolute;visibility:hidden;pointer-events:none;color:${value}`;
  scope.append(probe);
  const text = getComputedStyle(probe).color;
  probe.remove();
  const nums = (text.match(/-?[\d.]+(e-?\d+)?%?/g) ?? []).map(Number);
  if (text.startsWith("color(")) return [nums[0] ?? 0, nums[1] ?? 0, nums[2] ?? 0];
  return [(nums[0] ?? 0) / 255, (nums[1] ?? 0) / 255, (nums[2] ?? 0) / 255];
}
