// Vercel Web Analytics on both pages (index.html, coverage.html): the plain-HTML snippet, the window.va queue
// before it, served by the site itself (/_vercel/insights/script.js), and nothing else that tracks. The queue's
// beforeSend takes the part of the address after "#" (the search typed) off every page view.
// Run: node --test tools/conditions-search/tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const read = name => readFileSync(join(here, "..", name), "utf8");
const PAGES = ["index.html", "coverage.html"];
const SCRIPT = '<script defer src="/_vercel/insights/script.js"></script>';
const QUEUE = "window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };";

/** The inline script just before the analytics script tag (the queue), as text. */
function queueScript(html) {
  const at = html.indexOf(SCRIPT);
  const m = html.slice(0, at).match(/<script>([\s\S]*?)<\/script>\s*$/);
  assert.ok(m, "no inline queue script right before the analytics script");
  return m[1];
}

for (const page of PAGES) {
  test(`${page} loads Vercel Web Analytics once, in the head, with the queue before it`, () => {
    const html = read(page);
    assert.equal(html.split(SCRIPT).length, 2, "the analytics script tag must be there exactly once");
    const head = html.slice(0, html.indexOf("</head>"));
    assert.ok(head.includes(SCRIPT), "the analytics script is not in <head>");
    assert.ok(queueScript(html).includes(QUEUE), "the window.va queue stub is missing");
  });

  test(`${page}: no other tracker, no cookies, no storage`, () => {
    const html = read(page);
    // the only script with a src is the analytics one; the rest are inline or the page's own modules
    const srcs = [...html.matchAll(/<script\b[^>]*\bsrc="([^"]*)"/g)].map(m => m[1]);
    assert.deepEqual(srcs, ["/_vercel/insights/script.js"]);
    assert.ok(!/<(img|iframe|link)\b[^>]*\b(src|href)="https?:\/\//i.test(html), "an external image, frame or stylesheet");
    for (const text of [html, read("search.js"), read("coverage.js")]) {
      assert.ok(!/document\.cookie|localStorage|sessionStorage|indexedDB|navigator\.sendBeacon/.test(text));
      assert.ok(!/google-analytics|googletagmanager|gtag\(|plausible|posthog|segment\.|hotjar|clarity\.ms|fbq\(/i.test(text));
    }
  });

  test(`${page}: the queue takes the search (after "#") off the page view before it is sent`, () => {
    const window = {};
    new Function("window", queueScript(read(page)))(window);
    assert.equal(typeof window.va, "function");
    const queued = window.vaq.filter(args => args[0] === "beforeSend");
    assert.equal(queued.length, 1, "one beforeSend on the queue");
    const beforeSend = queued[0][1];
    const event = { type: "pageview", url: "https://sf-conditions-search.vercel.app/#q=2351+Mission&kind=all" };
    assert.deepEqual(beforeSend(event), { type: "pageview", url: "https://sf-conditions-search.vercel.app/" });
    assert.equal(beforeSend({ url: "https://sf-conditions-search.vercel.app/coverage.html#reviewed-list" }).url,
      "https://sf-conditions-search.vercel.app/coverage.html");
    assert.equal(beforeSend({ url: "https://sf-conditions-search.vercel.app/" }).url, "https://sf-conditions-search.vercel.app/");
    // a stub already set (the script loaded first) is kept
    const set = { va() {} };
    const keep = set.va;
    new Function("window", queueScript(read(page)))(set);
    assert.equal(set.va, keep);
  });
}
