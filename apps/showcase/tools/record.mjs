// Proof for the morning report: for one prototype, measured frame times, a GIF of its best 10 to 15 seconds,
// and screenshots at desktop and phone sizes. Everything is made here, in a real GPU-backed Chromium window:
//
//   node tools/record.mjs c                      # reads tools/demos/c.mjs, writes docs/ui/proof/c/
//   node tools/record.mjs c --base http://127.0.0.1:4311 --out ../../docs/ui/proof/c
//
// A demo module exports `path`, `viewport`, `run(page)` and optionally `phone(page)` (see tools/demos/).
// The GIF is encoded in JavaScript (gifenc) from Chromium's own screencast frames; no ffmpeg is needed.

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "@playwright/test";
import gifenc from "gifenc";
import { PNG } from "pngjs";

const { GIFEncoder, quantize, applyPalette } = gifenc;
const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const letter = args[0];
if (!letter) {
  console.error("usage: node tools/record.mjs <a|b|c|name> [--base URL] [--out DIR] [--fps 12] [--width 800]");
  process.exit(2);
}
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i > -1 && args[i + 1] ? args[i + 1] : fallback;
};
const base = opt("base", "http://127.0.0.1:4311").replace(/\/$/, "");
const out = resolve(here, opt("out", `../../../docs/ui/proof/${letter}`));
const fps = Number(opt("fps", 12));
const gifWidth = Number(opt("width", 800));
const demo = await import(pathToFileURL(resolve(here, `demos/${letter}.mjs`)).href);
const viewport = demo.viewport ?? { width: 1280, height: 800 };
const url = base + (demo.path ?? `/${letter}/`);
mkdirSync(out, { recursive: true });

const GPU = ["--use-angle=metal", "--ignore-gpu-blocklist", "--enable-gpu", "--hide-scrollbars"];
const browser = await chromium.launch({ headless: false, args: GPU });

/** Collects requestAnimationFrame intervals from the first frame of the page. */
const FRAME_PROBE = () => {
  const w = window;
  w.__frames = [];
  let last = 0;
  const tick = t => {
    if (last) w.__frames.push(t - last);
    last = t;
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
};

const pct = (sorted, p) => sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))] ?? 0;
const round = n => Math.round(n * 10) / 10;

async function settle(page) {
  await page.waitForLoadState("load");
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(1200);
}

// ---- pass 1: frame times, with nothing else running (no screencast, no video) --------------------------------
async function measure() {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const problems = [];
  page.on("console", m => (m.type() === "error" || m.type() === "warning") && problems.push(`${m.type()}: ${m.text()}`));
  page.on("pageerror", e => problems.push(`pageerror: ${e.message}`));
  await page.addInitScript(FRAME_PROBE);
  const t0 = Date.now();
  await page.goto(url);
  await settle(page);
  const paint = await page.evaluate(() => {
    const fcp = performance.getEntriesByName("first-contentful-paint")[0];
    return fcp ? fcp.startTime : null;
  });
  await page.evaluate(() => (window.__frames.length = 0));
  const started = Date.now();
  await demo.run(page);
  const seconds = (Date.now() - started) / 1000;
  const frames = await page.evaluate(() => window.__frames.slice());
  const sorted = frames.slice().sort((a, b) => a - b);
  const stats = {
    url,
    viewport,
    seconds: round(seconds),
    frames: frames.length,
    fps: round(frames.length / seconds),
    median_ms: round(pct(sorted, 50)),
    p95_ms: round(pct(sorted, 95)),
    p99_ms: round(pct(sorted, 99)),
    worst_ms: round(sorted[sorted.length - 1] ?? 0),
    over_33ms: frames.filter(f => f > 33.4).length,
    first_contentful_paint_ms: paint === null ? null : round(paint),
    load_and_settle_ms: started - t0,
    console_problems: problems,
  };
  await context.close();
  return stats;
}

// ---- pass 2: the GIF ----------------------------------------------------------------------------------------------
async function record() {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(url);
  await settle(page);
  const cdp = await context.newCDPSession(page);
  const shots = [];
  cdp.on("Page.screencastFrame", frame => {
    shots.push({ data: frame.data, t: frame.metadata.timestamp });
    cdp.send("Page.screencastFrameAck", { sessionId: frame.sessionId }).catch(() => {});
  });
  const gifHeight = Math.round((gifWidth * viewport.height) / viewport.width);
  await cdp.send("Page.startScreencast", { format: "png", maxWidth: gifWidth, maxHeight: gifHeight, everyNthFrame: 1 });
  await demo.run(page);
  await page.waitForTimeout(400);
  await cdp.send("Page.stopScreencast");
  await page.screenshot({ path: resolve(out, "desktop-end.png") });
  await context.close();
  if (shots.length < 2) throw new Error("the screencast produced no frames");

  // resample to a steady frame rate (the screencast only sends a frame when the picture changes)
  const start = shots[0].t;
  const end = shots[shots.length - 1].t;
  const step = 1 / fps;
  const picked = [];
  let j = 0;
  for (let t = start; t <= end + 1e-6; t += step) {
    while (j + 1 < shots.length && shots[j + 1].t <= t) j++;
    picked.push(shots[j]);
  }
  const decoded = new Map();
  const decode = shot => {
    if (!decoded.has(shot)) decoded.set(shot, PNG.sync.read(Buffer.from(shot.data, "base64")));
    return decoded.get(shot);
  };
  const first = decode(picked[0]);
  const { width, height } = first;

  // one palette for the whole clip, from a sample of frames (the designs use few colours, so this is faithful)
  const sampleEvery = Math.max(1, Math.floor(picked.length / 12));
  const sample = [];
  for (let i = 0; i < picked.length; i += sampleEvery) sample.push(decode(picked[i]).data);
  const pool = new Uint8Array(sample.reduce((n, d) => n + d.length, 0));
  let offset = 0;
  for (const d of sample) {
    pool.set(d, offset);
    offset += d.length;
  }
  const palette = quantize(pool, 256, { format: "rgb565" });

  const gif = GIFEncoder();
  let previous = null;
  let held = 0;
  const flush = () => {
    if (!previous) return;
    gif.writeFrame(previous, width, height, { palette, delay: Math.round((held * 1000) / fps) });
  };
  for (const shot of picked) {
    const png = decode(shot);
    if (png.width !== width || png.height !== height) continue;
    const index = applyPalette(png.data, palette, "rgb565");
    // identical consecutive frames become one longer frame
    if (previous && index.length === previous.length && index.every((v, i) => v === previous[i])) {
      held++;
      continue;
    }
    flush();
    previous = index;
    held = 1;
  }
  flush();
  gif.finish();
  const bytes = gif.bytes();
  writeFileSync(resolve(out, `${letter}.gif`), bytes);
  return { gif_bytes: bytes.length, gif_size: `${width}x${height}`, gif_seconds: round(end - start), source_frames: shots.length };
}

// ---- screenshots ----------------------------------------------------------------------------------------------------
async function stills() {
  const made = [];
  for (const theme of ["paper", "blueprint"]) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
    await context.addInitScript(t => {
      try {
        localStorage.setItem("showcase:theme", t);
      } catch {}
    }, theme);
    const page = await context.newPage();
    await page.goto(url);
    await settle(page);
    const file = `desktop-start-${theme}.png`;
    await page.screenshot({ path: resolve(out, file) });
    made.push(file);
    await context.close();
  }
  const phone = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  });
  const page = await phone.newPage();
  await page.goto(url);
  await settle(page);
  await page.screenshot({ path: resolve(out, "phone-start.png") });
  made.push("phone-start.png");
  if (typeof demo.phone === "function") {
    await demo.phone(page);
    await page.waitForTimeout(600);
    await page.screenshot({ path: resolve(out, "phone-end.png") });
    made.push("phone-end.png");
  }
  await phone.close();
  return made;
}

try {
  const stats = await measure();
  const clip = await record();
  const shots = await stills();
  const result = { prototype: letter, measured_at: new Date().toISOString(), ...stats, ...clip, screenshots: ["desktop-end.png", ...shots] };
  writeFileSync(resolve(out, "measure.json"), `${JSON.stringify(result, null, 2)}\n`);
  console.log(JSON.stringify(result, null, 2));
} finally {
  await browser.close();
}
