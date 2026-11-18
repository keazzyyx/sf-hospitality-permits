// Drawn objects for the map of core/world: paper pop-ups in the print language. See README.md.
// Needs three.js: import from a page's 3D chunk.

export * from "./build";
export { CASTLE_PLAN, CITY_HALL_PLAN, TOWER_PLAN } from "./plans";
export { createCastle } from "./castle";
export type { Castle } from "./castle";
export { createTower } from "./tower";
export type { Tower } from "./tower";
export { createCityHall } from "./cityhall";
export { createGround, createHachures, createRoads, createTrees } from "./terrain";
export type { Ground3D, Hachures, Roads, Trees } from "./terrain";
export type { CityHall } from "./cityhall";
