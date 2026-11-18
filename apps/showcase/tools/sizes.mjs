// Per-page transfer sizes of the built app: for each HTML page in dist/, the JS and CSS it loads (its module
// script, the chunks it preloads, its stylesheets) and the fonts it preloads, raw and gzipped.
// Run after a build: `pnpm sizes`.

import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const dist = resolve(dirname(fileURLToPath(import.meta.url)), "..", process.env.SHOWCASE_OUT ?? "dist");
if (!existsSync(dist)) {
  console.error("No dist/ folder: run `pnpm build` first.");
  process.exit(1);
}

const pages = ["index.html", "c/index.html", "search/index.html", "coverage/index.html"];
const kb = n => (n / 1024).toFixed(1).padStart(6) + " kB";
const size = file => {
  const raw = readFileSync(file);
  return { raw: raw.byteLength, gzip: gzipSync(raw, { level: 9 }).byteLength };
};
const sum = files => files.map(size).reduce((a, b) => ({ raw: a.raw + b.raw, gzip: a.gzip + b.gzip }), { raw: 0, gzip: 0 });

console.log("page".padEnd(20), "JS raw".padStart(9), "JS gzip".padStart(9), "CSS raw".padStart(9), "CSS gzip".padStart(9), "fonts preloaded".padStart(16), "HTML gzip".padStart(10));
for (const page of pages) {
  const file = resolve(dist, page);
  const html = readFileSync(file, "utf8");
  const refs = re => [...html.matchAll(re)].map(m => resolve(dirname(file), m[1]));
  const js = [...new Set([...refs(/<script[^>]+src="([^"]+\.js)"/g), ...refs(/<link rel="modulepreload"[^>]+href="([^"]+\.js)"/g)])];
  const css = refs(/<link rel="stylesheet"[^>]+href="([^"]+\.css)"/g);
  const fonts = refs(/<link rel="preload" as="font"[^>]+href="([^"]+\.woff2)"/g);
  const j = sum(js), c = sum(css), f = sum(fonts);
  console.log(("/" + page.replace("index.html", "")).padEnd(20), kb(j.raw), kb(j.gzip), kb(c.raw), kb(c.gzip), (kb(f.raw) + ` (${fonts.length})`).padStart(16), kb(size(file).gzip));
}
const data = resolve(dist, "data/conditions.json");
if (existsSync(data)) {
  const d = size(data);
  console.log(`\ndata/conditions.json: ${kb(d.raw).trim()} raw, ${kb(d.gzip).trim()} gzipped (loaded once, by the search)`);
}
