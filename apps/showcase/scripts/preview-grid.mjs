#!/usr/bin/env node
// Draws public/data/sf-streets.bin and public/data/motions.json to a PNG, to check the data by eye.
// No dependencies: a small line rasteriser and a PNG encoder on top of node:zlib.
//
//   node apps/showcase/scripts/preview-grid.mjs [--out <file.png>] [--width 1800] [--snapped]

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import zlib from 'node:zlib'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const DATA = path.resolve(HERE, '../public/data')
const args = process.argv.slice(2)
const opt = (name, fallback) => (args.includes(`--${name}`) ? args[args.indexOf(`--${name}`) + 1] : fallback)
const OUT = path.resolve(opt('out', path.resolve(HERE, '../../../docs/ui/media/sf-grid-preview.png')))
const WIDTH = Number(opt('width', '1800'))
const SNAPPED = args.includes('--snapped')

// ---- load (the same steps a browser loader takes) ----
const file = fs.readFileSync(path.join(DATA, 'sf-streets.bin'))
const buf = file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength)
const head = new DataView(buf)
if (String.fromCharCode(...new Uint8Array(buf, 0, 4)) !== 'SFG1') throw new Error('not an SFG1 file')
const n = head.getUint32(8, true)
const positions = new Int16Array(buf, 16, n * 4)
const classes = new Uint8Array(buf, 16 + n * 8, n)
const motions = JSON.parse(fs.readFileSync(path.join(DATA, 'motions.json'), 'utf8')).points

// ---- canvas, 2x supersampled ----
const SS = 2
let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
for (let i = 0; i < positions.length; i += 2) {
  minX = Math.min(minX, positions[i]); maxX = Math.max(maxX, positions[i])
  minY = Math.min(minY, positions[i + 1]); maxY = Math.max(maxY, positions[i + 1])
}
const PAD = 40
const scale = (WIDTH - 2 * PAD) / (maxX - minX)
const HEIGHT = Math.ceil((maxY - minY) * scale + 2 * PAD)
const W = WIDTH * SS, H = HEIGHT * SS
const px = new Float32Array(W * H * 3)
const BG = [0.965, 0.955, 0.93]
for (let i = 0; i < W * H; i++) px.set(BG, i * 3)
const sx = (x) => (PAD + (x - minX) * scale) * SS
const sy = (y) => (PAD + (maxY - y) * scale) * SS // north up

function blend(x, y, c, a) {
  if (x < 0 || y < 0 || x >= W || y >= H) return
  const i = (y * W + x) * 3
  px[i] += (c[0] - px[i]) * a; px[i + 1] += (c[1] - px[i + 1]) * a; px[i + 2] += (c[2] - px[i + 2]) * a
}
function disc(cx, cy, r, c, a = 1) {
  for (let y = Math.floor(cy - r); y <= Math.ceil(cy + r); y++)
    for (let x = Math.floor(cx - r); x <= Math.ceil(cx + r); x++) {
      const d = Math.hypot(x + 0.5 - cx, y + 0.5 - cy)
      if (d <= r + 0.5) blend(x, y, c, a * Math.min(1, r + 0.5 - d))
    }
}
function line(x1, y1, x2, y2, w, c, a = 1) {
  const len = Math.hypot(x2 - x1, y2 - y1)
  const steps = Math.max(1, Math.ceil(len * 1.5))
  const r = w / 2
  let last = -1
  for (let s = 0; s <= steps; s++) {
    const x = x1 + ((x2 - x1) * s) / steps, y = y1 + ((y2 - y1) * s) / steps
    for (let yy = Math.floor(y - r); yy <= Math.floor(y + r); yy++)
      for (let xx = Math.floor(x - r); xx <= Math.floor(x + r); xx++) {
        const id = yy * W + xx
        if (id === last) continue
        if (Math.hypot(xx + 0.5 - x, yy + 0.5 - y) <= r + 0.2 && !mark.has(id)) { mark.add(id); blend(xx, yy, c, a) }
        last = id
      }
  }
}
let mark = new Set()
for (const cls of [0, 1])
  for (let i = 0; i < n; i++) {
    if (classes[i] !== cls) continue
    mark = new Set()
    const o = i * 4
    line(sx(positions[o]), sy(positions[o + 1]), sx(positions[o + 2]), sy(positions[o + 3]), cls ? 2.6 * SS * 0.5 : 1.1 * SS * 0.5 + 0.4, cls ? [0.12, 0.14, 0.2] : [0.45, 0.47, 0.52], cls ? 1 : 0.85)
  }
for (const m of motions) {
  const x = SNAPPED ? m.sx : m.x, y = SNAPPED ? m.sy : m.y
  if (x === null || y === null) continue
  disc(sx(x), sy(y), 4.2 * SS, [1, 1, 1], 0.9)
  disc(sx(x), sy(y), 3.2 * SS, [0.86, 0.16, 0.12], 0.9)
}
// north arrow, top left: a plain "N" with a stem pointing up
const ax = 60 * SS, ay = 110 * SS, ink = [0.1, 0.1, 0.1]
mark = new Set(); line(ax, ay, ax, ay - 60 * SS, 3 * SS, ink)
mark = new Set(); line(ax, ay - 60 * SS, ax - 9 * SS, ay - 44 * SS, 3 * SS, ink)
mark = new Set(); line(ax, ay - 60 * SS, ax + 9 * SS, ay - 44 * SS, 3 * SS, ink)
for (const [a, b, c2, d] of [[-8, 34, -8, 12], [-8, 12, 8, 34], [8, 34, 8, 12]]) { mark = new Set(); line(ax + a * SS, ay + b * SS, ax + c2 * SS, ay + d * SS, 2.4 * SS, ink) }

// ---- downsample and encode ----
const raw = Buffer.alloc((WIDTH * 3 + 1) * HEIGHT)
for (let y = 0; y < HEIGHT; y++) {
  raw[y * (WIDTH * 3 + 1)] = 0
  for (let x = 0; x < WIDTH; x++)
    for (let k = 0; k < 3; k++) {
      let s = 0
      for (let dy = 0; dy < SS; dy++) for (let dx = 0; dx < SS; dx++) s += px[((y * SS + dy) * W + x * SS + dx) * 3 + k]
      raw[y * (WIDTH * 3 + 1) + 1 + x * 3 + k] = Math.max(0, Math.min(255, Math.round((s / (SS * SS)) * 255)))
    }
}
const crcTable = Array.from({ length: 256 }, (_, i) => { let c = i; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0 })
const crc = (b) => { let c = 0xffffffff; for (const v of b) c = crcTable[(c ^ v) & 255] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0 }
const chunk = (type, data) => {
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const out = Buffer.alloc(body.length + 8)
  out.writeUInt32BE(data.length, 0); body.copy(out, 4); out.writeUInt32BE(crc(body), body.length + 4)
  return out
}
const ihdr = Buffer.alloc(13)
ihdr.writeUInt32BE(WIDTH, 0); ihdr.writeUInt32BE(HEIGHT, 4); ihdr[8] = 8; ihdr[9] = 2
fs.mkdirSync(path.dirname(OUT), { recursive: true })
fs.writeFileSync(OUT, Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw, { level: 9 })), chunk('IEND', Buffer.alloc(0))]))
console.log(`${OUT}: ${WIDTH}x${HEIGHT}, ${n} segments, ${motions.filter((m) => m.x !== null).length} motion dots${SNAPPED ? ' (snapped to streets)' : ''}`)
