// The map's projection, and nothing else: no three.js here, so pages can use it before the 3D chunk loads.
//
// The street data (public/data/sf-streets.bin, described in sf-streets.json) is in whole metres on an
// equirectangular grid about lon -122.4376, lat 37.7577: grid x grows east, grid y grows north.
// The world lays that grid on the ground of a y-up scene: world x = grid x (east), world z = -grid y (so north
// points away from a camera that looks down -z), world y = height in metres.

/** The constants of public/data/sf-streets.json ("projection"). */
export const PROJECTION = {
  originLon: -122.4376,
  originLat: 37.7577,
  metresPerDegLon: 87911.641,
  metresPerDegLat: 111195.08,
} as const;

/** The extent of the street data in grid metres (sf-streets.json "bounds"). */
export const BOUNDS = { minX: -6683, minY: -5613, maxX: 6411, maxY: 5924 } as const;

/** A point on the ground of the world, in metres: x east, z south (north is -z). */
export interface Ground {
  x: number;
  z: number;
}

/** Longitude and latitude (degrees) to a point on the ground. */
export function project(lon: number, lat: number): Ground {
  return {
    x: (lon - PROJECTION.originLon) * PROJECTION.metresPerDegLon,
    z: -(lat - PROJECTION.originLat) * PROJECTION.metresPerDegLat,
  };
}

/** A point on the ground back to longitude and latitude (degrees): the inverse of project(). */
export function unproject(x: number, z: number): { lon: number; lat: number } {
  return {
    lon: PROJECTION.originLon + x / PROJECTION.metresPerDegLon,
    lat: PROJECTION.originLat - z / PROJECTION.metresPerDegLat,
  };
}

/** A point in the data's own grid (x east, y north, metres) to the ground. */
export function fromGrid(gx: number, gy: number): Ground {
  return { x: gx, z: -gy };
}

/** "37.8030° N  122.4051° W": fixed width, for a readout in tabular figures. */
export function formatLatLon(lat: number, lon: number, digits = 4): string {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(digits)}° ${ns}  ${Math.abs(lon).toFixed(digits)}° ${ew}`;
}

/** A round length for a scale bar: the largest of 1, 2, 5 × 10^k metres that is at most `maxMetres`. */
export function niceLength(maxMetres: number): number {
  if (!(maxMetres > 0)) return 1;
  const pow = 10 ** Math.floor(Math.log10(maxMetres));
  const lead = maxMetres / pow;
  return (lead >= 5 ? 5 : lead >= 2 ? 2 : 1) * pow;
}

/** "500 m", "2 km", "50 m". */
export function formatLength(metres: number): string {
  return metres >= 1000 ? `${metres / 1000} km` : `${metres} m`;
}
