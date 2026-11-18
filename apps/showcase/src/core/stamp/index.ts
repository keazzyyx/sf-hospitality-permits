// The rubber stamp, for any page: the stamp itself (createStamp), the press-and-hold that drives it (createHold),
// the mark it leaves (renderMark), the crack through what it stamped (crackThrough), and what the impact does to
// the page (createShaker, ripple, flecks). See README.md in this folder.

import "./stamp.css";

export { createStamp, hardwareWebGL, type Stamp, type StampOptions } from "./stamp";
export { createHold, type Hold, type HoldCancel, type HoldOptions, type HoldPoint, type HoldSource, type HoldStart } from "./hold";
export { renderMark, MARK_BOX, MARK_RATIO, MARK_TILT, type Mark, type MarkOptions } from "./mark";
export { crackThrough, crackLine, type Crack, type CrackOptions, type OpenOptions } from "./crack";
export { createShaker, flecks, ripple, type FleckOptions, type RippleOptions, type Shaker } from "./impact";
export { frameOf, type Frame, type Point } from "./geometry";
export { rng, between, freshSeed, type Rng } from "./rng";
export { Spring, clamp, follow, lerp, smoothstep } from "./spring";
export type { StampPose } from "./pose";
