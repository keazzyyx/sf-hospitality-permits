# Street-grid data for the 3D world

Two scripts, no dependencies beyond Node 20 or later. They produce everything the three.js street-grid
prototype draws: San Francisco's real street centrelines as line segments, and one point per Planning
Commission motion on the same grid.

| File | What it is | Size | Gzipped |
| --- | --- | --- | --- |
| `public/data/sf-streets.bin` | 19,841 line segments (2,709 major), Int16 | 178,585 bytes | 83,077 bytes |
| `public/data/sf-streets.json` | projection, units, bounds, byte layout, source, licence | 3.4 KB | 1.4 KB |
| `public/data/motions.json` | 352 motions, 350 with a coordinate | 85 KB | 15 KB |
| `docs/ui/media/sf-grid-preview.png` | picture drawn from the three files above, to check them by eye | 380 KB | |

## Rebuild

```sh
# from the repo root; raw downloads are cached outside the repo
node apps/showcase/scripts/build-grid.mjs --raw /some/scratch/dir      # add --refresh to download again
node apps/showcase/scripts/preview-grid.mjs                            # writes docs/ui/media/sf-grid-preview.png
```

`--raw` defaults to `$GRID_RAW_DIR`, else `<tmp>/sf-grid-raw`. The first run makes about ten requests to
DataSF (four pages of streets, four of addresses, one metadata call), at most two a second, with the
User-Agent `sf-conditions-search research`. Later runs read the cache and make none. Other options:
`--unit <metres per unit>` (default 1) and `--tolerance <metres>` (default 6). Look at the preview after any
rebuild: north is up, Market Street is the heavy diagonal, Golden Gate Park is the long gap in the west.

## Source and licence

- Streets: DataSF, "Streets – Active and Retired", dataset `3psu-pn9h`
  (<https://data.sf.gov/d/3psu-pn9h>; `data.sfgov.org` now redirects to `data.sf.gov`). Active segments only,
  data as of 2026-11-16.
- Addresses, used to place the motions: DataSF, "San Francisco Addresses – Enterprise Addressing System",
  dataset `3mea-di5p`.
- Both are published by the City and County of San Francisco under the Open Data Commons Public Domain
  Dedication and License (PDDL 1.0), <https://opendatacommons.org/licenses/pddl/1-0/>. No attribution is
  required; naming DataSF as the source is good practice.
- Motions: `tools/conditions-search/data/conditions.json` in this repo (one point per `record`).

## What the build does to the streets

1. Keeps real ground on the mainland: layers `STREETS`, `STREETS_PEDESTRI`, `STREETS_HUNTERSP`, `PARKS`,
   `PARKS_NPS_PRESIDIO`, `PARKS_NPS_FTMASON`, `PRIVATE`, `UPROW`.
2. Leaves out freeways and ramps (classcode 1 and 6: they cut across the grid and hide it), paper streets
   (never built, some under the Bay), addressing helpers, parking lots, and Treasure Island and Yerba Buena
   Island.
3. Projects longitude and latitude to metres: equirectangular about lon -122.4376, lat 37.7577.
   `x = (lon + 122.4376) * 87,911.6`, `y = (lat - 37.7577) * 111,195.1`. x grows east, y grows north.
4. Simplifies each centreline with Douglas-Peucker at 6 m. End points are kept, so streets still meet.
5. Rounds to whole metres (1 unit = 1 m, the city spans about -6,700 to +6,400, well inside Int16).
6. Splits into independent segments, drops duplicates, and writes minor streets first, then major.
   Major = classcode 2 (major street) or 3 (arterial), plus all of Market Street, which the city codes as a
   collector east of Van Ness.

## Binary layout of `sf-streets.bin` (little-endian)

| Offset | Bytes | Type | Field |
| --- | --- | --- | --- |
| 0 | 4 | ASCII | magic `SFG1` |
| 4 | 2 | Uint16 | version, 1 |
| 6 | 2 | Uint16 | centimetres per unit, 100 |
| 8 | 4 | Uint32 | `segments`, N |
| 12 | 4 | Uint32 | `majorSegments`, M |
| 16 | 8 × N | Int16 | `x1, y1, x2, y2` per segment |
| 16 + 8N | N | Uint8 | class per segment: 0 minor, 1 major |

Segments `[0, N - M)` are minor and `[N - M, N)` are major, so two draw ranges are enough and the class
bytes are only needed if you reorder.

## Loader (three.js)

```js
const buf = await (await fetch('/data/sf-streets.bin')).arrayBuffer()
const head = new DataView(buf)
const n = head.getUint32(8, true), major = head.getUint32(12, true)
const xy = new Int16Array(buf, 16, n * 4) // x1,y1,x2,y2 in metres; x east, y north
const pos = new Float32Array(n * 6) // lay it on the ground: (x, 0, -y), so north points away from the camera
for (let i = 0; i < n * 2; i++) { pos[i * 3] = xy[i * 2]; pos[i * 3 + 2] = -xy[i * 2 + 1] }
const geo = new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(pos, 3))
geo.addGroup(0, (n - major) * 2, 0) // minor streets
geo.addGroup((n - major) * 2, major * 2, 1) // major streets
scene.add(new THREE.LineSegments(geo, [minorMaterial, majorMaterial]))
```

The Int16 pairs can also go straight into a two-component `BufferAttribute`, but three.js then works out the
bounding sphere wrongly, so set it yourself from `bounds` in `sf-streets.json` or turn off frustum culling.

## `motions.json`

```json
{ "projection": { "...": "same as sf-streets.json" }, "count": 352, "located": 350, "methods": { "eas": 349, "eas-near": 1, "none": 2 },
  "points": [ { "record": "2009.1056C", "address": "1408 - 1414 California St, San Francisco, Ca 94109", "business": "Restaurant or cafe",
                "zoning": "NCD-POLK", "decided": "2010-01-14", "year": 2010, "n": 14, "x": 1749, "y": 3722, "sx": 1753, "sy": 3696,
                "via": "eas", "offStreetM": 25.8 } ] }
```

- `x, y`: the address point, in the same units and axes as the streets. `null` when not located.
- `sx, sy`: the nearest point on the drawn street network, on the address's own street where that could be
  matched. Use these to plant a pin on the line; `offStreetM` is the distance between the two (median 24 m).
- `n`: number of conditions in the motion. `via`: how the coordinate was found. `note`: only when something
  was approximate or missing.
- Several motions share an address (315 distinct positions for 350 located motions; up to four on one spot),
  so the renderer has to stack or fan them.

How each coordinate is found, in order:

1. `postgis`: the Planning record's own point in the local PostGIS copy
   (`postgresql://postgres@localhost:55433/sfhp_local`, `public.applications`, source
   `datasf_planning`), read with `psql`. Override with `LOCAL_DATABASE_URL`. Skipped when the database is
   not running.
2. `eas`: the address matched in the DataSF address list (exact house number, or a number inside the
   record's range). `eas-near`: number not listed, nearest listed number on the same block and side.
3. `centreline`: interpolated along the street's address range in the streets dataset.
4. Otherwise `null` with a note.

The files in this repo were built with the local database switched off, so every located point came from
step 2. Two records have no usable street address and are left without a coordinate: `2011.0966C`
("0 Lakeshore Plaza") and `2011.0951C` ("371 Situs To Be Assigned St").
