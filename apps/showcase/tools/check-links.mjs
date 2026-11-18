// The public site's build, opened in a browser before it is written: no link and no feedback e-mail on its cards
// may open a motion PDF without a page of 2 or more (page 1 prints the project sponsor's name and address). The
// links of a card are only written as the page runs (the feedback e-mail's body among them), so the build's own
// guard (scripts/validation/build_public_conditions_site.py, check_site) asks this script to read them.
//
//   node tools/check-links.mjs <site folder> <hash> [<hash> ...]
//
// Each hash (for example "#q=2011.0186C&kind=all") is opened on the site's front page, served from the folder by
// Playwright's own routing (no port, no network: any other address is refused); every "show more" is pressed, then
// every href on the page and the subject and body of every mailto: link (decoded) are read. Prints one JSON object:
// {"problems": [...]} (empty when every link is at a page of 2 or more). Exits 2 when it cannot run at all.

import { readFileSync, statSync } from "node:fs";
import { extname, join, normalize, resolve, sep } from "node:path";

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".bin": "application/octet-stream",
};
const ORIGIN = "http://site.invalid";

const [dir, ...hashes] = process.argv.slice(2);
if (!dir || hashes.length === 0) {
  console.error("usage: node tools/check-links.mjs <site folder> <hash> [<hash> ...]");
  process.exit(2);
}
const root = resolve(dir);

let chromium;
try {
  ({ chromium } = await import("@playwright/test"));
} catch (error) {
  console.error(`check-links: Playwright is not installed here (pnpm install): ${error.message}`);
  process.exit(2);
}

let browser;
try {
  browser = await chromium.launch();
} catch (error) {
  console.error(`check-links: no browser to open the site in (pnpm --filter showcase exec playwright install chromium): ${error.message.split("\n")[0]}`);
  process.exit(2);
}

const problems = [];
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.route("**/*", route => {
    const url = new URL(route.request().url());
    if (url.origin !== ORIGIN) return route.abort();
    // Vercel serves its analytics script itself: here it is an empty one
    if (url.pathname === "/_vercel/insights/script.js") return route.fulfill({ status: 200, contentType: TYPES[".js"], body: "" });
    const rel = url.pathname === "/" ? "index.html" : decodeURIComponent(url.pathname.slice(1));
    const file = normalize(join(root, rel));
    try {
      if (!file.startsWith(root + sep) || !statSync(file).isFile()) throw new Error("not a file");
      return route.fulfill({ status: 200, contentType: TYPES[extname(file)] ?? "application/octet-stream", body: readFileSync(file) });
    } catch {
      return route.fulfill({ status: 404, body: "" });
    }
  });
  for (const hash of hashes) {
    const page = await context.newPage();
    try {
      await page.goto(`${ORIGIN}/${hash}`);
      await page.locator('.cs[data-cs-state="ready"]').waitFor({ timeout: 60_000 });
      for (let clicks = 0; clicks < 40 && (await page.locator("[data-cs-more]").count()); clicks++) await page.locator("[data-cs-more]").click();
      const cards = await page.locator("[data-cs-card]").count();
      if (cards === 0) problems.push(`${hash}: no card was shown, so its links could not be read`);
      const bad = await page.evaluate(() => {
        const found = [];
        const scan = (text, where) => {
          for (const m of text.matchAll(/[^\s"'<>]*\.pdf(?:#page=(\d+))?/gi)) if (!m[1] || Number(m[1]) < 2) found.push(`${where}: ${m[0]}`);
        };
        for (const el of document.querySelectorAll("[href]")) {
          const href = el.getAttribute("href") ?? "";
          if (href.startsWith("mailto:")) {
            let text = href;
            try {
              text = decodeURIComponent(href);
            } catch {
              // not decodable: read it as it is
            }
            scan(text, "a feedback e-mail");
          } else scan(href, "a link");
        }
        return found;
      });
      for (const b of [...new Set(bad)]) problems.push(`${hash}: ${b} (opens the motion without a page of 2 or more)`);
    } catch (error) {
      problems.push(`${hash}: the page could not be read: ${error.message.split("\n")[0]}`);
    } finally {
      await page.close();
    }
  }
} finally {
  await browser.close();
}
console.log(JSON.stringify({ problems }));
