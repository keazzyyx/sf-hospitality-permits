// The world's public face. See README.md. Everything exported from here that draws needs three.js, so import this
// module from a lazy chunk; the modules without three.js (projection, data, graph) can be imported directly by a
// page's first script.

export { createWorld, MAX_RELIEF, RELIEF_PARS } from "./world";
export type { PaletteKey, Relief, ScreenPoint, SharedUniforms, World, WorldOptions } from "./world";
export { setPose } from "./rig";
export type { Pose } from "./rig";
export { createSegments, FULL } from "./lines";
export type { Segments, SegmentsOptions } from "./lines";
export { createStreets } from "./streets";
export type { StreetLines, StreetsOptions } from "./streets";
export { createPins } from "./pins";
export type { Pin, Pins } from "./pins";
export { inkEdges, printMaterial, printObject } from "./print";
export type { PrintObject, PrintOptions } from "./print";
export { loadMotions, loadStreets, motionPosition, streetsPath } from "./data";
export type { MotionPoint, Motions, Streets } from "./data";
export { mergeDual } from "./dual";
export { makeRoute, streetGraph } from "./graph";
export type { Route, StreetGraph } from "./graph";
export { BOUNDS, formatLatLon, formatLength, fromGrid, niceLength, project, PROJECTION, unproject } from "./projection";
export type { Ground } from "./projection";
export { reliefHeight } from "./relief";
