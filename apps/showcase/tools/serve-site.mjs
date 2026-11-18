// A small static server for a built public site (the folder scripts/validation/build_public_conditions_site.py
// writes), as Vercel serves it: the headers of the folder's vercel.json (Cache-Control, the security headers, the
// Content-Security-Policy), "/" as index.html, no clean URLs, 404 for anything else. For the tests and for looking at
// a build before it is deployed; never for the public.
//
// Vercel Web Analytics is served by Vercel itself, not by the site. Here /_vercel/insights/script.js is a stand-in
// that does what matters to the page: it reads the page's queue (window.vaq), runs its beforeSend, and posts the
// view to /_vercel/insights/view. GET /__views lists the views posted (the tests read it).
//
//   node tools/serve-site.mjs <site folder> <port>
//
// A missing folder is served as an empty site (every page 404), so a test run can start and skip cleanly.

import { createServer } from "node:http";
import { existsSync, readFileSync, statSync } from "node:fs";
import { extname, join, normalize, resolve, sep } from "node:path";

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".bin": "application/octet-stream",
  ".txt": "text/plain; charset=utf-8",
};

const ANALYTICS_STAND_IN = `(function () {
  var queue = window.vaq || [];
  var before = null;
  for (var i = 0; i < queue.length; i++) if (queue[i][0] === "beforeSend") before = queue[i][1];
  var event = { type: "pageview", url: location.href };
  if (before) event = before(event);
  if (event) fetch("/_vercel/insights/view", { method: "POST", body: JSON.stringify({ url: event.url }), keepalive: true });
})();
`;

/** Vercel's "source" patterns as this site uses them: a literal path, or one with "(.*)" in it. */
function matcher(source) {
  const esc = text => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^${source.split("(.*)").map(esc).join("(.*)")}$`);
}

/** The headers of vercel.json for a path, in its order (a later rule's header of the same name wins). */
function headersFor(rules, path) {
  const out = new Map();
  for (const rule of rules) if (rule.test.test(path)) for (const h of rule.headers) out.set(h.key, h.value);
  return out;
}

export function serveSite(dir, port, host = "127.0.0.1") {
  const root = resolve(dir);
  let rules = [];
  const config = join(root, "vercel.json");
  if (existsSync(config)) {
    const parsed = JSON.parse(readFileSync(config, "utf8"));
    rules = (parsed.headers ?? []).map(r => ({ test: matcher(r.source), headers: r.headers }));
  }
  const views = [];
  const server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", `http://${host}:${port}`);
    const path = decodeURIComponent(url.pathname);
    const send = (status, type, body, extra = {}) => {
      res.statusCode = status;
      for (const [k, v] of headersFor(rules, path)) res.setHeader(k, v);
      for (const [k, v] of Object.entries(extra)) res.setHeader(k, v);
      if (type) res.setHeader("Content-Type", type);
      res.end(req.method === "HEAD" ? undefined : body);
    };
    if (path === "/_vercel/insights/script.js") return send(200, TYPES[".js"], ANALYTICS_STAND_IN);
    if (path === "/_vercel/insights/view" && req.method === "POST") {
      let body = "";
      req.on("data", chunk => (body += chunk));
      req.on("end", () => {
        try {
          views.push(JSON.parse(body));
        } catch {
          views.push({ bad: body });
        }
        send(200, TYPES[".json"], "{}");
      });
      return undefined;
    }
    if (path === "/__views") return send(200, TYPES[".json"], JSON.stringify(views), { "Cache-Control": "no-store" });
    const rel = path === "/" ? "index.html" : path.slice(1);
    const file = normalize(join(root, rel));
    if (!file.startsWith(root + sep) || rel.split("/").some(p => p.startsWith(".")) || rel === "vercel.json") {
      return send(404, TYPES[".txt"], "Not found");
    }
    if (!existsSync(file) || !statSync(file).isFile()) return send(404, TYPES[".txt"], "Not found");
    return send(200, TYPES[extname(file)] ?? "application/octet-stream", readFileSync(file));
  });
  return new Promise(done => server.listen(port, host, () => done(server)));
}

if (process.argv[1] && resolve(process.argv[1]) === resolve(new URL(import.meta.url).pathname)) {
  const [dir, port] = process.argv.slice(2);
  if (!dir || !port) {
    console.error("usage: node tools/serve-site.mjs <site folder> <port>");
    process.exit(2);
  }
  await serveSite(dir, Number(port));
  console.log(`serving ${resolve(dir)}${existsSync(dir) ? "" : " (missing: every page is 404)"} on http://127.0.0.1:${port}`);
}
