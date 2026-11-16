import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { expect, test } from "@playwright/test";

// The site's fonts live in the repo (src/app/fonts.ts loads them with next/font/local from src/app/fonts/), so a build
// never fetches anything from Google: a CI build once failed because it could not reach Google Fonts. These checks
// fail if next/font/google comes back, if a font file the app names is missing, or if the page asks Google for a font.

const APP = resolve(__dirname, "..");
const FONTS_MODULE = join(APP, "src/app/fonts.ts");
const FONTS_DIR = join(APP, "src/app/fonts");
const GOOGLE_FONT_HOSTS = /^https?:\/\/fonts\.(googleapis|gstatic)\.com\//i;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(tsx?|jsx?|mjs|cjs|css)$/.test(name) ? [path] : [];
  });
}

/** The font files src/app/fonts.ts names, as paths relative to it. */
function namedFontFiles(): string[] {
  const source = readFileSync(FONTS_MODULE, "utf8");
  return [...new Set([...source.matchAll(/path:\s*"(\.\/fonts\/[^"]+)"/g)].map((m) => m[1]))];
}

test.describe("self-hosted fonts", () => {
  test("nothing in the app imports next/font/google", () => {
    const offenders = [...sourceFiles(join(APP, "src")), join(APP, "next.config.ts")].filter((file) =>
      // an import or require of next/font/google, or a stylesheet or font URL on Google's hosts
      /["']next\/font\/google["']|https?:\/\/fonts\.(googleapis|gstatic)\.com/.test(readFileSync(file, "utf8")),
    );
    expect(offenders).toEqual([]);
  });

  test("every font file the app names is in the repo, is a woff2 file, and every stored font file is used", () => {
    const named = namedFontFiles();
    // Sora 2 subsets, IBM Plex Sans 6 (both variable: one file per subset), IBM Plex Mono 6 subsets x 2 weights
    expect(named).toHaveLength(20);
    for (const rel of named) {
      const bytes = readFileSync(join(APP, "src/app", rel));
      expect(bytes.length, rel).toBeGreaterThan(1000);
      expect(bytes.subarray(0, 4).toString("latin1"), `${rel} is not a woff2 file`).toBe("wOF2");
    }
    const stored = readdirSync(FONTS_DIR).filter((f) => f.endsWith(".woff2")).map((f) => `./fonts/${f}`);
    expect(stored.sort()).toEqual([...named].sort());
    // the fonts are SIL Open Font License 1.1; the licence travels with them
    for (const licence of ["OFL-Sora.txt", "OFL-IBM-Plex.txt"]) {
      expect(readFileSync(join(FONTS_DIR, licence), "utf8")).toContain("SIL Open Font License, Version 1.1");
    }
  });

  test("the page renders in the self-hosted faces and asks no Google host for anything", async ({ page, baseURL }) => {
    const googleRequests: string[] = [];
    const fontResponses: string[] = [];
    page.on("request", (req) => {
      if (GOOGLE_FONT_HOSTS.test(req.url())) googleRequests.push(req.url());
    });
    page.on("response", (res) => {
      if (res.request().resourceType() === "font" && res.ok()) fontResponses.push(res.url());
    });
    await page.route(GOOGLE_FONT_HOSTS, (route) => route.abort());

    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.evaluate(() => document.fonts.ready);

    const computed = await page.evaluate(() => {
      const family = (el: Element | null) => (el ? getComputedStyle(el).fontFamily : null);
      return {
        body: family(document.body),
        heading: family(document.querySelector("h1")),
        mono: family(document.querySelector(".font-mono")),
      };
    });
    expect(computed.body).toMatch(/^"?IBM Plex Sans"?, "?IBM Plex Sans Fallback"?/);
    expect(computed.heading).toMatch(/^"?Sora"?, "?Sora Fallback"?/);
    expect(computed.mono).toMatch(/^"?IBM Plex Mono"?, "?IBM Plex Mono Fallback"?/);

    // The faces the page actually drew with are loaded, from this site.
    const loaded = await page.evaluate(() =>
      [...document.fonts].filter((f) => f.status === "loaded").map((f) => `${f.family.replace(/"/g, "")} ${f.weight}`),
    );
    expect(loaded).toEqual(expect.arrayContaining(["Sora 600", "IBM Plex Sans 400", "IBM Plex Mono 400"]));

    // A character outside basic Latin loads its own subset of the same face (here the Vietnamese one), as Google's did.
    const vietnamese = await page.evaluate(async () =>
      (await document.fonts.load('400 16px "IBM Plex Sans"', "Phở")).map((f) => f.unicodeRange),
    );
    expect(vietnamese.some((range) => /U\+1EA0-1EF9/i.test(range))).toBe(true);

    expect(fontResponses.length).toBeGreaterThanOrEqual(3);
    for (const url of fontResponses) {
      expect(url.startsWith(`${baseURL}/_next/static/media/`), url).toBe(true);
    }
    expect(googleRequests).toEqual([]);
  });
});
