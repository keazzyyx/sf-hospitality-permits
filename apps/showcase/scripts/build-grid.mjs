#!/usr/bin/env node
// Builds the data for the 3D street-grid world:
//   public/data/sf-streets.bin   San Francisco street centrelines as independent line segments (Int16)
//   public/data/sf-streets.json  meta: projection, units, bounds, byte layout, source, licence
//   public/data/motions.json     one point per Planning Commission motion, in the same units
//
// Source: DataSF open data (Public Domain Dedication and License). No dependencies beyond Node >= 20.
// Raw downloads are cached OUTSIDE the repo (--raw <dir>, default $GRID_RAW_DIR or <tmp>/sf-grid-raw).
//
//   node apps/showcase/scripts/build-grid.mjs [--raw <dir>] [--refresh] [--unit <metres>] [--tolerance <metres>]
//
// See README.md in this folder for the binary layout and a loader example.

import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import zlib from 'node:zlib'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const REPO = path.resolve(HERE, '../../..')
const OUT = path.resolve(HERE, '../public/data')
const CONDITIONS = path.join(REPO, 'tools/conditions-search/data/conditions.json')

const args = process.argv.slice(2)
const flag = (name) => args.includes(`--${name}`)
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`)
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback
}

const RAW = path.resolve(opt('raw', process.env.GRID_RAW_DIR || path.join(os.tmpdir(), 'sf-grid-raw')))
const REFRESH = flag('refresh')
const UNIT_M = Number(opt('unit', '1')) // metres per integer unit
const TOLERANCE_M = Number(opt('tolerance', '6')) // Douglas-Peucker tolerance
const LOCAL_DB = process.env.LOCAL_DATABASE_URL || 'postgresql://postgres@localhost:55433/sfhp_local'

// ---- sources -------------------------------------------------------------------------------------------
const HOST = 'https://data.sf.gov' // data.sfgov.org redirects here
const UA = 'sf-conditions-search research'
const STREETS_ID = '3psu-pn9h' // Streets - Active and Retired
const EAS_ID = '3mea-di5p' // San Francisco Addresses - Enterprise Addressing System
const LICENCE = {
  name: 'Open Data Commons Public Domain Dedication and License (PDDL) 1.0',
  url: 'https://opendatacommons.org/licenses/pddl/1-0/',
}

// ---- projection ----------------------------------------------------------------------------------------
// Equirectangular about a fixed centre. x grows east, y grows north, both in metres before quantising.
const ORIGIN = { lon: -122.4376, lat: 37.7577 }
const EARTH_R = 6371008.8
const M_PER_DEG_LAT = (Math.PI / 180) * EARTH_R
const M_PER_DEG_LON = M_PER_DEG_LAT * Math.cos((ORIGIN.lat * Math.PI) / 180)
const project = (lon, lat) => [(lon - ORIGIN.lon) * M_PER_DEG_LON, (lat - ORIGIN.lat) * M_PER_DEG_LAT]
const q = (m) => Math.round(m / UNIT_M)
const PROJECTION = {
  type: 'equirectangular',
  origin: ORIGIN,
  earthRadiusM: EARTH_R,
  metresPerDegLon: +M_PER_DEG_LON.toFixed(3),
  metresPerDegLat: +M_PER_DEG_LAT.toFixed(3),
  metresPerUnit: UNIT_M,
  axes: 'x east, y north (map north is +y; in three.js use (x, 0, -y) for a y-up world)',
  formula:
    'x = round((lon - origin.lon) * metresPerDegLon / metresPerUnit); y = round((lat - origin.lat) * metresPerDegLat / metresPerUnit)',
}

// ---- polite fetching -----------------------------------------------------------------------------------
let lastRequest = 0
async function getJson(url) {
  const wait = lastRequest + 600 - Date.now() // at most 2 requests a second, with margin
  if (wait > 0) await new Promise((r) => setTimeout(r, wait))
  lastRequest = Date.now()
  const res = await fetch(url, { headers: { 'User-Agent': UA, Accept: 'application/json' } })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`)
  return res.json()
}
const soql = (id, ext, params) =>
  `${HOST}/resource/${id}.${ext}?` +
  Object.entries(params)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&')

async function cached(name, build) {
  const file = path.join(RAW, name)
  if (!REFRESH && fs.existsSync(file)) return JSON.parse(fs.readFileSync(file, 'utf8'))
  const data = await build()
  fs.mkdirSync(RAW, { recursive: true })
  fs.writeFileSync(file, JSON.stringify(data))
  return data
}

// ---- 1. streets ----------------------------------------------------------------------------------------
async function loadStreets() {
  const meta = await cached('streets-meta.json', () => getJson(`${HOST}/api/views/${STREETS_ID}.json`))
  const features = []
  const PAGE = 5000
  for (let page = 0; ; page++) {
    const fc = await cached(`streets_${page}.geojson`, () =>
      getJson(soql(STREETS_ID, 'geojson', { $where: 'active=true', $order: 'cnn', $limit: PAGE, $offset: page * PAGE })),
    )
    features.push(...fc.features)
    if (fc.features.length < PAGE) break
  }
  return { meta, features }
}

// Layers (from the dataset's `layer` field) that are real, drivable or walkable ground on the mainland.
// Left out: FREEWAYS (elevated, they cut across the grid), PAPER* (map-only, not built, some under the Bay),
// PSEUDO (addressing helpers), PRIVATE_PARKING, STREETS_TI / STREETS_YBI (Treasure and Yerba Buena islands).
const KEEP_LAYERS = new Set([
  'STREETS',
  'STREETS_PEDESTRI',
  'STREETS_HUNTERSP',
  'PARKS',
  'PARKS_NPS_PRESIDIO',
  'PARKS_NPS_FTMASON',
  'PRIVATE',
  'UPROW',
])
// classcode: 1 freeway, 2 major street/highway, 3 arterial, 4 collector, 5 residential, 6 freeway ramp, 0 other
const DROP_CLASSCODES = new Set(['1', '6'])
const MAJOR_CLASSCODES = new Set(['2', '3'])
// Market Street east of Van Ness is coded as a collector (4) because private cars are kept off it, but it is
// the diagonal everyone reads the city by, so the whole street is drawn as major.
const MAJOR_BY_NAME = new Set(['MARKET ST'])

function simplify(points, tolerance) {
  // Douglas-Peucker, iterative. Endpoints are always kept, so streets still meet at intersections.
  if (points.length < 3) return points
  const keep = new Uint8Array(points.length)
  keep[0] = keep[points.length - 1] = 1
  const stack = [[0, points.length - 1]]
  while (stack.length) {
    const [a, b] = stack.pop()
    const [ax, ay] = points[a]
    const [bx, by] = points[b]
    const dx = bx - ax
    const dy = by - ay
    const len2 = dx * dx + dy * dy
    let worst = -1
    let worstD = tolerance * tolerance
    for (let i = a + 1; i < b; i++) {
      const [px, py] = points[i]
      let d
      if (len2 === 0) d = (px - ax) ** 2 + (py - ay) ** 2
      else {
        const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2))
        d = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
      }
      if (d > worstD) {
        worstD = d
        worst = i
      }
    }
    if (worst > 0) {
      keep[worst] = 1
      stack.push([a, worst], [worst, b])
    }
  }
  return points.filter((_, i) => keep[i])
}

function buildStreets(features) {
  const stats = { featuresIn: features.length, droppedByLayer: {}, droppedFreeway: 0, droppedIsland: 0, kept: 0 }
  const lines = []
  let verticesIn = 0
  for (const f of features) {
    const p = f.properties
    if (!f.geometry) continue
    if (DROP_CLASSCODES.has(p.classcode)) {
      stats.droppedFreeway++
      continue
    }
    if (!KEEP_LAYERS.has(p.layer)) {
      stats.droppedByLayer[p.layer] = (stats.droppedByLayer[p.layer] || 0) + 1
      continue
    }
    const parts = f.geometry.type === 'MultiLineString' ? f.geometry.coordinates : [f.geometry.coordinates]
    for (const coords of parts) {
      verticesIn += coords.length
      const pts = simplify(
        coords.map(([lon, lat]) => project(lon, lat)),
        TOLERANCE_M,
      ).map(([x, y]) => [q(x), q(y)])
      lines.push({ pts, major: MAJOR_CLASSCODES.has(p.classcode) || MAJOR_BY_NAME.has(p.streetname) ? 1 : 0, name: p.streetname || '', street: `${p.street || ''}|${p.st_type || ''}`, cnn: p.cnn })
    }
  }

  // Clip to the mainland: join lines that share an endpoint, and drop any connected group that sits wholly
  // out in the Bay east/north of the shoreline (island streets that slipped through the layer filter).
  const parent = new Map()
  const find = (k) => {
    let r = k
    while (parent.get(r) !== r) r = parent.get(r)
    while (parent.get(k) !== r) {
      const n = parent.get(k)
      parent.set(k, r)
      k = n
    }
    return r
  }
  const key = ([x, y]) => x * 100003 + y
  for (const l of lines) {
    const ks = l.pts.map(key)
    for (const k of ks) if (!parent.has(k)) parent.set(k, k)
    for (let i = 1; i < ks.length; i++) parent.set(find(ks[i]), find(ks[0]))
  }
  const groups = new Map()
  for (const l of lines) {
    const g = find(key(l.pts[0]))
    if (!groups.has(g)) groups.set(g, [])
    groups.get(g).push(l)
  }
  const ISLAND = { minLon: -122.3805, minLat: 37.8035 } // Treasure Island / Yerba Buena box (north-east corner)
  const [islandX, islandY] = project(ISLAND.minLon, ISLAND.minLat).map(q)
  const kept = []
  for (const group of groups.values()) {
    const all = group.flatMap((l) => l.pts)
    const island = all.every(([x, y]) => x > islandX && y > islandY)
    if (island) stats.droppedIsland += group.length
    else kept.push(...group)
  }

  // Independent segments, deduplicated; minor streets first, then major, each in a stable street order
  // (name, then centreline id) so neighbouring segments sit together and the file compresses well.
  kept.sort((a, b) => a.major - b.major || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0) || a.cnn - b.cnn)
  const seen = new Set()
  const segs = []
  for (const l of kept) {
    for (let i = 1; i < l.pts.length; i++) {
      const [x1, y1] = l.pts[i - 1]
      const [x2, y2] = l.pts[i]
      if (x1 === x2 && y1 === y2) continue
      const a = `${x1},${y1},${x2},${y2}`
      const b = `${x2},${y2},${x1},${y1}`
      if (seen.has(a) || seen.has(b)) continue
      seen.add(a)
      segs.push([x1, y1, x2, y2, l.major, l.street])
    }
  }
  stats.kept = kept.length
  stats.verticesIn = verticesIn
  return { segs, stats }
}

const HEADER_BYTES = 16
function writeStreets(segs, stats, meta) {
  const n = segs.length
  const major = segs.filter((s) => s[4] === 1).length
  const buf = Buffer.alloc(HEADER_BYTES + n * 8 + n)
  buf.write('SFG1', 0, 'ascii')
  buf.writeUInt16LE(1, 4) // version
  buf.writeUInt16LE(Math.round(UNIT_M * 100), 6) // centimetres per unit
  buf.writeUInt32LE(n, 8)
  buf.writeUInt32LE(major, 12)
  const b = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity }
  segs.forEach(([x1, y1, x2, y2, cls], i) => {
    for (const v of [x1, y1, x2, y2]) if (v < -32768 || v > 32767) throw new Error(`coordinate ${v} does not fit Int16`)
    const o = HEADER_BYTES + i * 8
    buf.writeInt16LE(x1, o)
    buf.writeInt16LE(y1, o + 2)
    buf.writeInt16LE(x2, o + 4)
    buf.writeInt16LE(y2, o + 6)
    buf[HEADER_BYTES + n * 8 + i] = cls
    b.minX = Math.min(b.minX, x1, x2)
    b.maxX = Math.max(b.maxX, x1, x2)
    b.minY = Math.min(b.minY, y1, y2)
    b.maxY = Math.max(b.maxY, y1, y2)
  })
  fs.mkdirSync(OUT, { recursive: true })
  fs.writeFileSync(path.join(OUT, 'sf-streets.bin'), buf)
  const gz = zlib.gzipSync(buf, { level: 9 }).length
  const json = {
    file: 'sf-streets.bin',
    format: 'SFG1',
    version: 1,
    endianness: 'little',
    units: { metresPerUnit: UNIT_M, type: 'Int16' },
    projection: PROJECTION,
    bounds: { ...b, widthM: (b.maxX - b.minX) * UNIT_M, heightM: (b.maxY - b.minY) * UNIT_M },
    segments: n,
    minorSegments: n - major,
    majorSegments: major,
    order: 'minor segments first [0, minorSegments), then major [minorSegments, segments)',
    classes: { 0: 'minor (collector, residential, park, private, pedestrian)', 1: 'major (classcode 2 major street / 3 arterial, plus all of Market Street)' },
    byteLayout: [
      { offset: 0, bytes: 4, type: 'ascii', name: 'magic', value: 'SFG1' },
      { offset: 4, bytes: 2, type: 'Uint16', name: 'version', value: 1 },
      { offset: 6, bytes: 2, type: 'Uint16', name: 'centimetresPerUnit', value: Math.round(UNIT_M * 100) },
      { offset: 8, bytes: 4, type: 'Uint32', name: 'segments', value: n },
      { offset: 12, bytes: 4, type: 'Uint32', name: 'majorSegments', value: major },
      { offset: 16, bytes: n * 8, type: 'Int16[4 * segments]', name: 'positions', note: 'x1,y1,x2,y2 per segment' },
      { offset: 16 + n * 8, bytes: n, type: 'Uint8[segments]', name: 'class', note: '0 minor, 1 major' },
    ],
    bytes: buf.length,
    gzipBytes: gz,
    simplification: { method: 'Douglas-Peucker per centreline', toleranceM: TOLERANCE_M },
    filter: {
      active: true,
      layersKept: [...KEEP_LAYERS],
      classcodesDropped: { 1: 'freeway', 6: 'freeway ramp' },
      islands: 'Treasure Island and Yerba Buena Island left out',
    },
    stats,
    source: {
      publisher: 'City and County of San Francisco (DataSF), Public Works',
      dataset: meta.name,
      id: STREETS_ID,
      url: `${HOST}/d/${STREETS_ID}`,
      api: `${HOST}/resource/${STREETS_ID}.geojson?$where=active=true`,
      dataUpdated: new Date(meta.rowsUpdatedAt * 1000).toISOString().slice(0, 10),
      fetched: fs.statSync(path.join(RAW, 'streets_0.geojson')).mtime.toISOString(),
    },
    licence: LICENCE,
  }
  fs.writeFileSync(path.join(OUT, 'sf-streets.json'), JSON.stringify(json, null, 2) + '\n')
  return json
}

// ---- 2. motion points ----------------------------------------------------------------------------------
function loadMotions() {
  const data = JSON.parse(fs.readFileSync(CONDITIONS, 'utf8'))
  const byRecord = new Map()
  for (const c of data.conditions) {
    let m = byRecord.get(c.record)
    if (!m) {
      m = { record: c.record, address: c.address, business: c.business, zoning: c.zoning, decided: c.decided, year: Number(c.year), n: 0 }
      byRecord.set(c.record, m)
    }
    m.n++
  }
  return [...byRecord.values()]
}

// (a) local PostGIS copy of the Planning records, when it is running
function fromPostgis() {
  try {
    const out = execFileSync(
      'psql',
      [
        LOCAL_DB,
        '-At',
        '-F',
        '\t',
        '-c',
        "select id, source_id, st_x(geom::geometry), st_y(geom::geometry) from public.applications where source = 'datasf_planning' and geom is not null",
      ],
      { env: { ...process.env, PGCONNECT_TIMEOUT: '3' }, encoding: 'utf8', maxBuffer: 256 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'] },
    )
    const map = new Map()
    for (const line of out.split('\n')) {
      const [id, sourceId, lon, lat] = line.split('\t')
      if (!lat) continue
      const pos = [Number(lon), Number(lat)]
      map.set(sourceId, pos)
      map.set(id, pos)
      map.set(id.replace(/^.*:/, ''), pos)
    }
    // (the note goes into public/data/motions.json, which is in the repository: no address of the database in it)
    return { map, note: `${map.size} keys read from the local PostGIS copy` }
  } catch (err) {
    const why = String(err.stderr || err.message).trim().split('\n')[0].replace(/^psql: error: /, '')
    console.warn(`local PostGIS not available: ${why}`)
    return { map: new Map(), note: 'local PostGIS copy not available: points from the address list only' }
  }
}

// (b) DataSF Enterprise Addressing System
const TYPES = {
  ST: 'ST', STREET: 'ST', AV: 'AVE', AVE: 'AVE', AVENUE: 'AVE', BL: 'BLVD', BLVD: 'BLVD', DR: 'DR', WAY: 'WAY', WY: 'WAY',
  RD: 'RD', PL: 'PL', CT: 'CT', LN: 'LN', TER: 'TER', ALY: 'ALY', HWY: 'HWY', PLZ: 'PLZ', PLAZA: 'PLZ', CIR: 'CIR',
}
const NO_TYPE_STREETS = new Set(['BROADWAY'])

export function parseAddress(address) {
  let s = String(address || '').toUpperCase().replace(/,\s*SAN FRANCISCO.*$/, '').replace(/\s+\d{5}$/, '').trim()
  const m = s.match(/^(\d+)(?:\s*-\s*(\d+))?\s+(.*)$/)
  if (!m) return null
  let lo = Number(m[1])
  const hi = m[2] ? Number(m[2]) : lo
  if (lo === 0 && hi > 0) lo = hi // "0 - 2335 Market St": the low end was never filled in
  let tokens = m[3].split(/\s+/)
  if (tokens.length > 2 && /^[A-Z]$/.test(tokens[0])) tokens = tokens.slice(1) // "2200 A Market St"
  let typeAt = -1
  for (let i = tokens.length - 1; i >= 1; i--) if (TYPES[tokens[i]]) { typeAt = i; break }
  let name
  let type = null
  if (typeAt > 0) {
    name = tokens.slice(0, typeAt).join(' ')
    type = TYPES[tokens[typeAt]]
  } else {
    const stop = tokens.findIndex((t, i) => i > 0 && (/^\d/.test(t) || t === 'COMML'))
    name = tokens.slice(0, stop > 0 ? stop : tokens.length).join(' ')
  }
  if (NO_TYPE_STREETS.has(name)) type = null
  return { lo: Math.min(lo, hi), hi: Math.max(lo, hi), name, type }
}

async function loadEas(names) {
  const rows = []
  const list = [...names].sort()
  const PAGE = 50000
  for (let i = 0, part = 0; i < list.length; i += 25, part++) {
    const chunk = list.slice(i, i + 25)
    const where = `street_name in (${chunk.map((n) => `'${n.replace(/'/g, "''")}'`).join(',')})`
    for (let page = 0; ; page++) {
      const got = await cached(`eas_${part}_${page}.json`, () =>
        getJson(
          soql(EAS_ID, 'json', {
            $select: 'address_number,address_number_suffix,street_name,street_type,zip_code,longitude,latitude',
            $where: where,
            $order: 'eas_baseid',
            $limit: PAGE,
            $offset: page * PAGE,
          }),
        ),
      )
      rows.push(...got)
      if (got.length < PAGE) break
    }
  }
  return rows
}

function geocoder(easRows, streetFeatures) {
  const byStreet = new Map()
  for (const r of easRows) {
    if (!r.longitude || !r.latitude) continue
    const k = r.street_name
    if (!byStreet.has(k)) byStreet.set(k, [])
    byStreet.get(k).push({ num: Number(r.address_number), suffix: r.address_number_suffix || '', type: r.street_type || null, zip: r.zip_code, lon: Number(r.longitude), lat: Number(r.latitude) })
  }
  const pick = (cands, target) => {
    cands.sort((a, b) => Math.abs(a.num - target) - Math.abs(b.num - target) || a.suffix.length - b.suffix.length)
    return cands[0]
  }
  return function geocode(address) {
    const a = parseAddress(address)
    if (!a) return { pos: null, note: 'address could not be parsed' }
    const zip = (String(address).match(/(\d{5})\s*$/) || [])[1]
    let rows = (byStreet.get(a.name) || []).filter((r) => a.type === null || r.type === a.type || r.type === null)
    if (zip && new Set(rows.map((r) => r.type)).size > 1) {
      const z = rows.filter((r) => r.zip === zip)
      if (z.length) rows = z
    }
    if (rows.length) {
      const parity = a.lo % 2
      let c = rows.filter((r) => r.num === a.lo)
      if (c.length) return { pos: pick(c, a.lo), via: 'eas' }
      c = rows.filter((r) => r.num >= a.lo && r.num <= a.hi && r.num % 2 === parity)
      if (!c.length) c = rows.filter((r) => r.num >= a.lo && r.num <= a.hi)
      if (c.length) return { pos: pick(c, a.lo), via: 'eas', note: `address range, placed at number ${pick(c, a.lo).num}` }
      c = rows.filter((r) => r.num % 2 === parity && Math.abs(r.num - a.lo) <= 30 && Math.floor(r.num / 100) === Math.floor(a.lo / 100))
      if (c.length) {
        const best = pick(c, a.lo)
        return { pos: best, via: 'eas-near', note: `number not in the address list, placed at nearest number on the block (${best.num})` }
      }
    }
    // (c) last resort: interpolate along the street centreline using its address ranges
    for (const f of streetFeatures) {
      const p = f.properties
      if (p.street !== a.name || !f.geometry) continue
      if (a.type && p.st_type && p.st_type !== a.type) continue
      for (const [from, to] of [[p.lf_fadd, p.lf_toadd], [p.rt_fadd, p.rt_toadd]]) {
        const lo = Math.min(Number(from), Number(to))
        const hi = Math.max(Number(from), Number(to))
        if (!(hi > 0) || a.lo < lo || a.lo > hi || lo % 2 !== a.lo % 2) continue
        const t = hi === lo ? 0.5 : (a.lo - Number(from)) / (Number(to) - Number(from))
        const cs = f.geometry.coordinates
        const lens = cs.slice(1).map((c, i) => Math.hypot(...project(c[0], c[1]).map((v, k) => v - project(cs[i][0], cs[i][1])[k])))
        let d = t * lens.reduce((s, v) => s + v, 0)
        for (let i = 0; i < lens.length; i++) {
          if (d <= lens[i] || i === lens.length - 1) {
            const u = lens[i] ? Math.min(1, d / lens[i]) : 0
            return { pos: { lon: cs[i][0] + u * (cs[i + 1][0] - cs[i][0]), lat: cs[i][1] + u * (cs[i + 1][1] - cs[i][1]) }, via: 'centreline', note: 'placed on the street centreline by address range' }
          }
          d -= lens[i]
        }
      }
    }
    return { pos: null, note: rows.length ? 'street found, but no such house number on it' : `the record carries no usable street address (no street named ${a.name} in the address list)` }
  }
}

// Nearest point on the street network, so a renderer can plant the pin on the line. The address's own street
// is preferred (a corner lot's address point can sit closer to the cross street); any street is the fallback.
function snapper(segs) {
  const CELL = Math.max(1, Math.round(100 / UNIT_M))
  const grid = new Map()
  segs.forEach((s, i) => {
    const x0 = Math.floor(Math.min(s[0], s[2]) / CELL)
    const x1 = Math.floor(Math.max(s[0], s[2]) / CELL)
    const y0 = Math.floor(Math.min(s[1], s[3]) / CELL)
    const y1 = Math.floor(Math.max(s[1], s[3]) / CELL)
    for (let x = x0; x <= x1; x++)
      for (let y = y0; y <= y1; y++) {
        const k = `${x},${y}`
        if (!grid.has(k)) grid.set(k, [])
        grid.get(k).push(i)
      }
  })
  const nearest = (px, py, rings, accept) => {
    const cx = Math.floor(px / CELL)
    const cy = Math.floor(py / CELL)
    let best = null
    for (let ring = 1; ring <= rings && !best; ring++)
      for (let x = cx - ring; x <= cx + ring; x++)
        for (let y = cy - ring; y <= cy + ring; y++)
          for (const i of grid.get(`${x},${y}`) || []) {
            if (!accept(segs[i][5])) continue
            const [x1, y1, x2, y2] = segs[i]
            const dx = x2 - x1
            const dy = y2 - y1
            const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
            const sx = x1 + t * dx
            const sy = y1 + t * dy
            const d = Math.hypot(px - sx, py - sy)
            if (!best || d < best.d) best = { d, sx: Math.round(sx), sy: Math.round(sy) }
          }
    return best
  }
  return (px, py, addr) => {
    if (addr) {
      const own = nearest(px, py, 1, (street) => {
        const [name, type] = street.split('|')
        return name === addr.name && (!addr.type || !type || type === addr.type)
      })
      if (own && own.d * UNIT_M <= 120) return { ...own, own: true }
    }
    return nearest(px, py, 3, () => true)
  }
}

async function buildMotions(streetFeatures, segs) {
  const motions = loadMotions()
  const pg = fromPostgis()
  console.log(`motions: ${motions.length} records; ${pg.note}`)
  const need = motions.filter((m) => !pg.map.has(m.record))
  const names = new Set(need.map((m) => parseAddress(m.address)?.name).filter(Boolean))
  const eas = need.length ? await loadEas(names) : []
  const geocode = geocoder(eas, streetFeatures)
  const snap = snapper(segs)
  const methods = {}
  const points = motions.map((m) => {
    let lon, lat, via, note
    if (pg.map.has(m.record)) {
      ;[lon, lat] = pg.map.get(m.record)
      via = 'postgis'
    } else {
      const g = geocode(m.address)
      if (g.pos) ({ lon, lat } = g.pos)
      via = g.pos ? g.via : null
      note = g.note
    }
    methods[via ?? 'none'] = (methods[via ?? 'none'] || 0) + 1
    const p = { ...m, x: null, y: null, sx: null, sy: null, via }
    if (via) {
      const [mx, my] = project(lon, lat)
      p.x = q(mx)
      p.y = q(my)
      const s = snap(p.x, p.y, parseAddress(m.address))
      if (s) {
        p.sx = s.sx
        p.sy = s.sy
        p.offStreetM = +(s.d * UNIT_M).toFixed(1)
      }
    }
    if (note) p.note = note
    return p
  })
  points.sort((a, b) => (a.decided < b.decided ? -1 : a.decided > b.decided ? 1 : a.record < b.record ? -1 : 1))
  const json = {
    projection: PROJECTION,
    count: points.length,
    located: points.filter((p) => p.via).length,
    methods,
    methodKey: {
      postgis: 'point of the Planning record in the local PostGIS copy (public.applications, source datasf_planning)',
      eas: `address matched in DataSF Enterprise Addressing System (${EAS_ID})`,
      'eas-near': 'house number not listed; nearest listed number on the same block and side',
      centreline: `interpolated along the street centreline address range (${STREETS_ID})`,
      none: 'no coordinate (x, y are null; see note)',
    },
    fields: 'x, y: address point, in street units (null when not located). sx, sy: nearest point on the street network in sf-streets.bin, on the address\'s own street where it could be matched. offStreetM: distance between the two, metres. Several motions can share one address, so positions repeat.',
    sources: {
      motions: 'tools/conditions-search/data/conditions.json (one point per record)',
      addresses: { dataset: 'San Francisco Addresses - Enterprise Addressing System', id: EAS_ID, url: `${HOST}/d/${EAS_ID}`, licence: LICENCE },
      postgis: pg.note,
    },
    points,
  }
  // one point per line: small, and easy to read in a diff
  const { points: _, ...headOnly } = json
  const text = JSON.stringify(headOnly, null, 1).replace(/\n}$/, ',\n "points": [\n' + points.map((p) => '  ' + JSON.stringify(p)).join(',\n') + '\n ]\n}\n')
  fs.writeFileSync(path.join(OUT, 'motions.json'), text)
  return json
}

// ---- run -----------------------------------------------------------------------------------------------
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { meta, features } = await loadStreets()
  const { segs, stats } = buildStreets(features)
  const s = writeStreets(segs, stats, meta)
  console.log(`streets: ${s.segments} segments (${s.majorSegments} major), ${s.bytes} bytes, ${s.gzipBytes} gzipped`)
  console.log(`  bounds ${JSON.stringify(s.bounds)}`)
  console.log(`  stats ${JSON.stringify(stats)}`)
  const m = await buildMotions(features, segs)
  console.log(`motions: ${m.located} of ${m.count} located ${JSON.stringify(m.methods)}`)
  for (const p of m.points.filter((p) => p.note)) console.log(`  ${p.record}  ${p.address}  -> ${p.via ?? 'none'}: ${p.note}`)
}
