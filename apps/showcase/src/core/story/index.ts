// The story engine's public face. See README.md. No three.js in here.

export { createStory } from "./engine";
export type { Story, StoryMode, StoryOptions, StoryState } from "./engine";
export { buildTimeline, ease, EDGES, range, REST, STEP_RANGE } from "./timeline";
export type { Chapter, ChapterSpec, Edges, Located, Stop, Timeline } from "./timeline";
export { copyPose, emptyPose, poseAt } from "./camera";
export type { CameraKey } from "./camera";
export { createRail } from "./rail";
export type { Rail } from "./rail";
