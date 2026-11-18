// The public site's build (scripts/validation/build_public_conditions_site.py --front c), served as Vercel serves it
// (tools/serve-site.mjs applies its vercel.json: the CSP, the cache headers), held to the live site as it was
// before the C front end, served the same way:
// - the same results: the parity cases of e2e/parity.spec.ts and the owner's own checks ("security guard", a case
//   number, "Valencia St", "2740 Mission", a range address as its card shows it, card links), each with the same
//   count, order, conditions and motion links (the store's copy at #page=N);
// - the same headers and CSP, and no CSP violation and no console error the whole way: the gate, the stamp, the
//   story, the search, the flip, the coverage page, with the drawn map and with the 3D scene;
// - Vercel Web Analytics: one view per page, the search taken off the address;
// - the feedback link on every card, the contact line, the coverage page's numbers and sections.
// Local only (config: playwright.site.config.ts). Skips when either folder is missing.

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { BASELINE, BASELINE_DIR, SITE, SITE_DIR } from "../playwright.site.config";
import { CASES, type Case } from "../e2e/helpers/cases";
import { expectParity, hash } from "../e2e/helpers/parity";
import { feedbackMails, pagelessPdfLinks } from "../e2e/helpers/links";

const built = existsSync(resolve(SITE_DIR, "index.html")) && existsSync(resolve(SITE_DIR, "vercel.json"));
const baseline = existsSync(resolve(BASELINE_DIR, "index.html"));
test.skip(!built, `no built site in ${SITE_DIR}: run scripts/validation/build_public_conditions_site.py --front c (SITE_DIR=...)`);

const READY = '.cs[data-cs-state="ready"]';

/** The contact address and the motion store, read off the live site's own files (SITE_CONTACT and SITE_STORE
 *  override them): the address of its contact line, and where its data points the motion links. Nothing of either
 *  is written in this file. */
function liveFacts(): { contact: string; store: string } {
  let contact = process.env.SITE_CONTACT ?? "";
  let store = process.env.SITE_STORE ?? "";
  for (const dir of [BASELINE_DIR, SITE_DIR]) {
    try {
      if (!contact) contact = /href="mailto:([^"?]+)"/.exec(readFileSync(resolve(dir, "index.html"), "utf8"))?.[1] ?? "";
      if (!store) {
        const name = readdirSync(resolve(dir, "assets")).find(f => /^conditions\.[0-9a-f]{12}\.json$/.test(f));
        const data = name ? (JSON.parse(readFileSync(resolve(dir, "assets", name), "utf8")) as { conditions: { pdf?: string | null }[] }) : null;
        store = data?.conditions.find(c => c.pdf)?.pdf?.replace(/[^/]+$/, "") ?? "";
      }
    } catch {
      // a folder that is not there: the other one, or the variables, say it
    }
  }
  return { contact, store };
}
const { contact: CONTACT, store: STORE } = liveFacts();

/** The owner's own checks, beside the parity cases. */
const MORE: Case[] = [
  { name: "the owner's check: security guard", hash: hash({ q: "security guard" }), min: 1 },
  { name: "the owner's check: a case number", hash: hash({ q: "2016-001273CUA" }), min: 1 },
  { name: "the owner's check: Valencia St", hash: hash({ q: "Valencia St" }), min: 50 },
  { name: "the owner's check: 2740 Mission", hash: hash({ q: "2740 Mission" }), min: 1 },
  { name: "the owner's check: a range address as its card shows it", hash: hash({ q: "2740 - 2744 Mission St" }), min: 1 },
  { name: "the owner's check: a card link", hash: "#q=2740+Mission&card=1", min: 1 },
  // the one motion whose conditions were read with no page: its links open where the conditions begin, not page 1
  { name: "a motion read with no page numbers opens at its conditions", hash: hash({ q: "2011.0186C", kind: "all" }), exact: 12 },
];

/** Every page of a context reports CSP violations into window.__csp. */
async function watchCsp(context: BrowserContext): Promise<void> {
  await context.addInitScript(() => {
    const w = window as unknown as { __csp: string[] };
    w.__csp = [];
    document.addEventListener("securitypolicyviolation", e => w.__csp.push(`${e.violatedDirective} ${e.blockedURI} ${e.sourceFile}:${e.lineNumber}`));
  });
}
const cspOf = (page: Page): Promise<string[]> => page.evaluate(() => (window as unknown as { __csp?: string[] }).__csp ?? []);

/** Console errors and warnings, page errors, failed requests and HTTP errors of a page. */
function problemsOf(page: Page): string[] {
  const problems: string[] = [];
  page.on("console", m => {
    // headless Chromium draws WebGL in software and says so ("GL Driver Message … GPU stall due to ReadPixels"):
    // the browser's note about itself, not the page's
    if (/GL Driver Message/.test(m.text())) return;
    if (m.type() === "error" || m.type() === "warning") problems.push(`${m.type()}: ${m.text()}`);
  });
  page.on("pageerror", e => problems.push(`pageerror: ${e.message}`));
  page.on("requestfailed", r => problems.push(`failed: ${r.url()} ${r.failure()?.errorText ?? ""}`));
  page.on("response", r => {
    if (r.status() >= 400) problems.push(`${r.status()}: ${r.url()}`);
  });
  return problems;
}

test.describe("the same results as the live site", () => {
  test.skip(!baseline, `no baseline in ${BASELINE_DIR}`);
  for (const c of [...CASES, ...MORE]) {
    test(c.name, async ({ context }) => {
      const { current, showcase } = await expectParity(context, c.hash, {
        current: BASELINE,
        currentPath: "/index.html",
        showcase: SITE,
        path: "/",
        pdfs: true,
      });
      if (c.exact !== undefined) expect(current.cards.length).toBe(c.exact);
      if (c.min !== undefined) expect(current.cards.length).toBeGreaterThanOrEqual(c.min);
      if (c.hash.includes("card=7A")) expect(showcase.target).toBe("2015-009955CUA #7A");
      // every motion link is the store's copy at a page, never page 1 (and never without a page: that is page 1)
      for (const href of showcase.pdfs.filter(Boolean)) {
        expect(href.startsWith(STORE)).toBe(true);
        expect(href).toMatch(/#page=([2-9]|\d\d+)$/);
      }
    });
  }

  test("a link to /index.html with a search, as links to the live site are written, gives the same", async ({ context }) => {
    await expectParity(context, "#q=noise&kind=all", { current: BASELINE, showcase: SITE, path: "/index.html", pdfs: true });
  });
});

test.describe("served as Vercel serves it", () => {
  test("the same headers and CSP as the live site; pages revalidated, files named by content and kept", async ({ request }) => {
    const live = JSON.parse(readFileSync(resolve(BASELINE_DIR, "vercel.json"), "utf8"));
    const ours = JSON.parse(readFileSync(resolve(SITE_DIR, "vercel.json"), "utf8"));
    expect(ours).toEqual(live);
    for (const path of ["/", "/index.html", "/coverage.html"]) {
      const res = await request.get(`${SITE}${path}`);
      expect(res.status(), path).toBe(200);
      expect(res.headers()["cache-control"]).toBe("no-cache");
      expect(res.headers()["content-security-policy"]).toContain("default-src 'self'");
      expect(res.headers()["x-frame-options"]).toBe("DENY");
    }
    const html = await (await request.get(`${SITE}/`)).text();
    const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map(m => m[1]!);
    expect(assets.length).toBeGreaterThan(4);
    for (const a of assets) {
      const res = await request.get(`${SITE}${a}`);
      expect(res.status(), a).toBe(200);
      expect(res.headers()["cache-control"]).toBe("public, max-age=31536000, immutable");
    }
  });
});

test.describe("no CSP violation, no console error, the whole way", () => {
  for (const variant of [
    { name: "with the drawn map", query: "" },
    { name: "with the 3D scene (drawn in software here)", query: "?webgl=1" },
  ]) {
    test(variant.name, async ({ browser }) => {
      test.slow();
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      await watchCsp(context);
      const page = await context.newPage();
      const problems = problemsOf(page);
      const external: string[] = [];
      page.on("request", r => {
        if (!r.url().startsWith(`${SITE}/`) && !r.url().startsWith("data:")) external.push(r.url());
      });
      await page.goto(`${SITE}/${variant.query}`);
      // the gate (a first visit), stamped from the keyboard
      await expect(page.locator(".c-gate")).toBeVisible();
      await page.locator(READY).waitFor();
      await page.waitForFunction(() => Boolean((window as unknown as { showcase?: { gate?: unknown } }).showcase?.gate));
      if (variant.query) {
        // (software-drawn 3D keeps the page's thread so busy that a test's key press arrives with its key-up a
        // quarter of a second late, which reads as a hold let go: the button is activated as a screen reader does)
        await page.locator(".c-gate__button").evaluate(b => (b as HTMLButtonElement).click());
      } else {
        await page.locator(".c-gate__button").focus();
        await page.keyboard.press("Enter");
      }
      // (software-drawn 3D on a machine busy with the other tests can take a while over the crack)
      await expect(page.locator(".c-gate")).toHaveCount(0, { timeout: 120_000 });
      // the whole story, chapter by chapter
      for (let i = 0; i < 8; i++) {
        await page.evaluate(k => (window as unknown as { showcase: { story: { goTo(i: number, o?: { instant?: boolean }): void } } }).showcase.story.goTo(k, { instant: true }), i);
        await expect(page.locator(`.c-chapter[data-chapter="${i}"]`)).toBeVisible();
        await page.waitForTimeout(250);
      }
      // the search
      await page.locator(".shell-skip").click();
      await page.locator('[data-cs-field="q"]').fill("security guard");
      await expect(page.locator("[data-cs-card]").first()).toBeVisible();
      // every card: its feedback link emails the contact address; the contact line is under the search (a site built
      // without CONTACT_EMAIL has no address: no card link, no mailto, and the contact line says the rest)
      if (CONTACT) {
        const cards = await page.locator("[data-cs-card]").count();
        const mails = await page.locator(`[data-cs-card] a[href^="mailto:${CONTACT}?"]`).count();
        expect(mails).toBe(cards);
        await expect(page.locator(".shell-contact")).toContainText(`Questions or corrections: ${CONTACT}.`);
      } else {
        await expect(page.locator('a[href^="mailto:"]')).toHaveCount(0);
        await expect(page.locator(".shell-contact")).not.toContainText("Questions or corrections");
      }
      await expect(page.locator(".shell-contact")).toContainText("Page views are counted by Vercel Web Analytics, without cookies.");
      // the footer offers the source code and its licence (what the AGPL asks of a network service)
      const source = page.getByRole("navigation", { name: "Source code" });
      await expect(source.getByRole("link", { name: "Source code" })).toHaveAttribute("href", "https://github.com/keazzyyx/sf-hospitality-permits");
      await expect(source.getByRole("link", { name: "AGPL-3.0 licence" })).toHaveAttribute("rel", "license noopener");
      // the flip
      await page.locator(".theme-flip").click();
      await expect(page.locator("html")).not.toHaveClass(/c-flip/, { timeout: 10_000 });
      expect(await cspOf(page)).toEqual([]);
      // the coverage page
      await page.locator(".shell-foot__nav").getByRole("link", { name: "Coverage" }).click();
      await expect(page).toHaveURL(`${SITE}/coverage.html`);
      await expect(page.locator("[data-coverage-facts] tr").first()).toBeVisible();
      await expect(page.getByRole("heading", { level: 2, name: "Text quality" })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      expect(await cspOf(page)).toEqual([]);
      expect(problems).toEqual([]);
      expect(external).toEqual([]);
      await context.close();
    });
  }

  test("a returning visitor and a phone get the search alone, with no violation either", async ({ browser }) => {
    for (const size of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      const context = await browser.newContext({ viewport: size, hasTouch: size.width < 500, isMobile: size.width < 500 });
      await watchCsp(context);
      await context.addInitScript(() => localStorage.setItem("showcase:visited:c-gate", "x"));
      const page = await context.newPage();
      const problems = problemsOf(page);
      await page.goto(`${SITE}/`);
      await page.locator(READY).waitFor();
      await expect(page.locator("html")).toHaveClass(/c-direct/);
      await expect(page.locator('[data-cs-field="q"]')).toBeInViewport();
      await page.waitForTimeout(2500);
      expect(await cspOf(page)).toEqual([]);
      expect(problems).toEqual([]);
      await context.close();
    }
  });
});

test.describe("the page, as published", () => {
  test("no link and no feedback e-mail anywhere opens a motion at page 1 or with no page", async ({ page }) => {
    // 2011.0186C: read with no page numbers, every card and every e-mail opens it where its conditions begin
    await page.goto(`${SITE}/${hash({ q: "2011.0186C", kind: "all" })}`);
    await page.locator(READY).waitFor();
    await expect(page.locator("[data-cs-card]")).toHaveCount(12);
    const mails = await feedbackMails(page);
    expect(mails).toHaveLength(CONTACT ? 12 : 0);
    for (const mail of mails) expect(mail).toMatch(/Motion page: \S+\/2011\.0186C\.pdf#page=11\r\n/);
    expect(await pagelessPdfLinks(page)).toEqual([]);
    // the owner's checks and a long list (every card shown): the same holds for every link and e-mail on the page
    for (const [i, h] of [...MORE.map(c => c.hash), hash({ q: "noise", kind: "all" })].entries()) {
      // (a new load each time, not a change of hash in the page that is open)
      await page.goto(`${SITE}/?links=${i}${h}`);
      await page.locator(READY).waitFor();
      for (let clicks = 0; clicks < 40 && (await page.locator("[data-cs-more]").count()); clicks++) await page.locator("[data-cs-more]").click();
      expect(await pagelessPdfLinks(page), h).toEqual([]);
    }
  });

  test("titles, the wordmark, no prototype words, analytics once per page", async ({ page }) => {
    await page.goto(`${SITE}/#q=noise`);
    await page.locator(READY).waitFor();
    await expect(page).toHaveTitle("SF Conditions Search");
    await expect(page.locator(".mark-link")).toHaveAttribute("aria-label", /^Working Title/);
    const text = await page.locator("body").innerText();
    expect(text).not.toMatch(/prototype|permit\s*memo|local only|not published/i);
    for (const path of ["/", "/coverage.html"]) {
      const html = readFileSync(resolve(SITE_DIR, path === "/" ? "index.html" : "coverage.html"), "utf8");
      expect(html.split('<script defer src="/_vercel/insights/script.js"></script>')).toHaveLength(2);
      expect(html).not.toContain('name="robots"');
    }
    await page.goto(`${SITE}/coverage.html`);
    await expect(page).toHaveTitle("Coverage · SF Conditions Search");
  });

  test("Vercel Web Analytics counts each page once, without the search in the address", async ({ browser, request }) => {
    const before = (await (await request.get(`${SITE}/__views`)).json()) as { url: string }[];
    const context = await browser.newContext();
    const page = await context.newPage();
    const marker = `analytics-${Date.now()}`;
    await page.goto(`${SITE}/?${marker}#q=noise`);
    await page.locator(READY).waitFor();
    await page.goto(`${SITE}/coverage.html?${marker}`);
    await expect(page.locator("[data-coverage-facts] tr").first()).toBeVisible();
    await expect
      .poll(async () => ((await (await request.get(`${SITE}/__views`)).json()) as { url: string }[]).filter(v => v.url.includes(marker)).length)
      .toBe(2);
    const views = ((await (await request.get(`${SITE}/__views`)).json()) as { url: string }[]).slice(before.length).filter(v => v.url.includes(marker));
    for (const v of views) expect(v.url).not.toContain("#");
    expect(views.map(v => new URL(v.url).pathname).sort()).toEqual(["/", "/coverage.html"]);
    await context.close();
  });

  test("the coverage page shows what the live one shows", async ({ context }) => {
    test.skip(!baseline, `no baseline in ${BASELINE_DIR}`);
    const [a, b] = [await context.newPage(), await context.newPage()];
    await a.goto(`${BASELINE}/coverage.html`);
    await b.goto(`${SITE}/coverage.html`);
    await a.locator("#facts table td").first().waitFor();
    await a.locator("#detail h2").first().waitFor();
    await b.locator("[data-coverage-facts] tr").first().waitFor();
    await b.locator("[data-coverage-detail] h2").first().waitFor();
    const squash = (s: string): string => s.replace(/\s+/g, " ").trim();
    // the numbers: the same values in the same order
    const liveValues = (await a.locator("#facts table td.n").allTextContents()).map(squash);
    const ourValues = (await b.locator("[data-coverage-facts] td").allTextContents()).map(squash);
    expect(ourValues).toEqual(liveValues);
    expect(squash((await b.locator(".cov-lead").textContent()) ?? "")).toBe(squash((await a.locator("#facts > p").first().textContent()) ?? ""));
    // the reviewed list: the same rows
    expect(await b.locator("[data-coverage-review] tbody tr").count()).toBe(await a.locator("#review tbody tr").count());
    // the detail: the same sections, the same words
    expect(await b.locator("[data-coverage-detail] h2").allTextContents()).toEqual(await a.locator("#detail h2").allTextContents());
    const words = async (p: Page, sel: string): Promise<string> => squash((await p.locator(sel).innerText()).replace(/[“”]/g, '"'));
    expect(await words(b, "[data-coverage-detail]")).toBe(await words(a, "#detail"));
  });
});
