// Screenshots for docs/ui/media (both themes, desktop, tablet and phone, with a query and without, and the states).
// Not part of the test run: `pnpm shots` (SHOTS=1) writes them.

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";

const media = resolve(dirname(fileURLToPath(import.meta.url)), "../../../docs/ui/media");
const shot = (name: string): string => resolve(media, `foundation-${name}.png`);

const SIZES = [
  { name: "1440", width: 1440, height: 900 },
  { name: "390", width: 390, height: 844 },
] as const;
const THEMES = ["paper", "blueprint"] as const;
const STATES = [
  { name: "outdoor-seating", hash: "#q=outdoor+seating" },
  { name: "empty", hash: "" },
] as const;

async function context(browser: Browser, width: number, height: number, theme: "paper" | "blueprint" = "paper"): Promise<BrowserContext> {
  return browser.newContext({
    viewport: { width, height },
    deviceScaleFactor: 2,
    colorScheme: theme === "paper" ? "light" : "dark",
    reducedMotion: "reduce", // a still page: the placeholder does not change mid-shot
    hasTouch: width < 600,
    isMobile: width < 600,
  });
}

/** Open `url` as a new document: a change of hash alone keeps the page, with whatever panels were open. */
async function fresh(page: Page, url: string): Promise<void> {
  await page.goto("about:blank");
  await page.goto(url);
}

async function settle(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(250);
}

test.describe("screenshots", () => {
  test.skip(!process.env.SHOTS, "set SHOTS=1 (pnpm shots) to write the screenshots");

  for (const size of SIZES) {
    for (const theme of THEMES) {
      for (const state of STATES) {
        test(`search ${state.name} ${theme} ${size.name}`, async ({ browser }) => {
          const ctx = await context(browser, size.width, size.height, theme);
          const page = await ctx.newPage();
          await page.goto(`/search/${state.hash}`);
          await expect(page.locator("[data-cs-card]").first()).toBeVisible();
          await settle(page);
          await page.screenshot({ path: shot(`search-${state.name}-${theme}-${size.name}`) });
          if (state.name === "outdoor-seating") {
            await page.screenshot({ path: shot(`search-${state.name}-${theme}-${size.name}-full`), fullPage: true });
            if (size.width < 600) {
              // the first result as a phone shows it
              await page.locator("[data-cs-count]").evaluate(el => el.scrollIntoView({ block: "start" }));
              await page.screenshot({ path: shot(`search-${state.name}-${theme}-${size.name}-results`) });
            } else {
              // the end of the page: the notes, with the coverage notice still in the margin beside them
              await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
              await page.waitForTimeout(150);
              await page.screenshot({ path: shot(`search-${state.name}-${theme}-${size.name}-notes`) });
            }
          }
          await ctx.close();
        });
      }
    }
  }

  test("search states paper", async ({ browser }) => {
    const ctx = await context(browser, 1440, 900);
    const page = await ctx.newPage();
    // nothing found, with the page's own note and a way on
    await fresh(page, "/search/#q=security+guard+xylophone");
    await expect(page.locator("[data-cs-empty]")).toBeVisible();
    await settle(page);
    await page.screenshot({ path: shot("search-no-match-paper-1440") });
    // filters set, search tips open
    await fresh(page, "/search/#q=noise&business=Bar&year=2019&kind=all");
    await expect(page.locator("[data-cs-card]").first()).toBeVisible();
    await page.locator("[data-cs-tips]").click();
    await page.screenshot({ path: shot("search-filters-tips-paper-1440") });
    // a list from one motion: the motion is named once, above the list
    await fresh(page, "/search/#q=2015-009955CUA");
    await expect(page.locator("[data-cs-case]")).toBeVisible();
    await settle(page);
    await page.screenshot({ path: shot("search-one-motion-paper-1440") });
    // a link to one card: marked, scrolled to and focused
    await fresh(page, "/search/#q=2015-009955CUA&kind=all&card=30");
    await expect(page.locator("[data-cs-card].is-target")).toBeFocused();
    await page.waitForTimeout(150);
    await page.screenshot({ path: shot("search-card-link-paper-1440") });
    // keyboard focus on a motion link, hover on the next
    await fresh(page, "/search/#q=outdoor+seating");
    await expect(page.locator("[data-cs-card]").first()).toBeVisible();
    await page.locator("[data-cs-pdf]").first().focus();
    await page.locator('[data-cs-field="zoning"]').hover();
    await page.screenshot({ path: shot("search-focus-paper-1440") });
    // the loading line, held open, with a link's search already in the field
    let release: () => void = () => {};
    const gate = new Promise<void>(done => { release = done; });
    let mode: "hold" | "fail" = "hold";
    await page.route("**/data/conditions.json", async route => {
      if (mode === "fail") return route.fulfill({ status: 404, body: "not found" });
      await gate;
      return route.abort().catch(() => {});
    });
    await fresh(page, "/search/#q=outdoor+seating");
    await expect(page.locator("[data-cs-loading]")).toBeVisible();
    await settle(page);
    await page.screenshot({ path: shot("search-loading-paper-1440") });
    // the data could not be loaded
    mode = "fail";
    await page.goto("about:blank");
    release();
    await page.goto("/search/#q=outdoor+seating");
    await expect(page.getByRole("alert")).toBeVisible();
    await settle(page);
    await page.screenshot({ path: shot("search-error-paper-1440") });
    await ctx.close();

    const phone = await context(browser, 390, 844);
    const small = await phone.newPage();
    await fresh(small, "/search/#q=noise&business=Bar");
    await expect(small.locator("[data-cs-card]").first()).toBeVisible();
    await small.getByRole("button", { name: /^Filters/ }).click();
    await settle(small);
    await small.screenshot({ path: shot("search-filters-open-paper-390") });
    // a list from one motion on a phone, in blueprint: the two-line count
    await small.emulateMedia({ colorScheme: "dark" });
    await fresh(small, "/search/#q=2015-009955CUA");
    await expect(small.locator("[data-cs-case]")).toBeVisible();
    await settle(small);
    await small.screenshot({ path: shot("search-one-motion-blueprint-390") });
    await small.locator("[data-cs-count]").evaluate(el => el.scrollIntoView({ block: "start" }));
    await small.screenshot({ path: shot("search-one-motion-blueprint-390-results") });
    await small.emulateMedia({ colorScheme: "light" });
    // a link to one card on a phone
    await fresh(small, "/search/#q=2015-009955CUA&kind=all&card=30");
    await expect(small.locator("[data-cs-card].is-target")).toBeFocused();
    await small.waitForTimeout(150);
    await small.screenshot({ path: shot("search-card-link-paper-390") });
    // the end of the page on a phone
    await fresh(small, "/search/#q=outdoor+seating");
    await expect(small.locator("[data-cs-card]").first()).toBeVisible();
    await small.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await small.waitForTimeout(150);
    await small.screenshot({ path: shot("search-outdoor-seating-paper-390-notes") });
    await phone.close();

    // the narrowest phone
    const tiny = await context(browser, 320, 640);
    const narrow = await tiny.newPage();
    await fresh(narrow, "/c/#q=2015-009955CUA");
    await expect(narrow.locator("[data-cs-card]").first()).toBeVisible();
    await settle(narrow);
    await narrow.screenshot({ path: shot("front-gate-paper-320") });
    await tiny.close();
  });

  test("prototype page and tablet widths", async ({ browser }) => {
    const ctx = await context(browser, 1440, 900);
    const page = await ctx.newPage();
    await page.goto("/c/?gate=1");
    await expect(page.locator("[data-cs-card]").first()).toBeVisible();
    await settle(page);
    await page.screenshot({ path: shot("front-gate-paper-1440") });
    await page.setViewportSize({ width: 820, height: 1100 });
    await page.goto("/search/#q=live+music");
    await expect(page.locator("[data-cs-card]").first()).toBeVisible();
    await page.screenshot({ path: shot("search-live-music-paper-820") });
    // a small laptop or a tablet on its side
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/search/#q=outdoor+seating");
    await expect(page.locator("[data-cs-card]").first()).toBeVisible();
    await settle(page);
    await page.screenshot({ path: shot("search-outdoor-seating-paper-1024") });
    await page.locator(".cs-more-about--coverage").click();
    await page.screenshot({ path: shot("search-coverage-open-paper-1024") });
    await ctx.close();
  });

  test("hub and coverage", async ({ browser }) => {
    const ctx = await context(browser, 1440, 900);
    const page = await ctx.newPage();
    await page.goto("/");
    await expect(page.locator(".hub__list")).toBeVisible();
    await settle(page);
    await page.screenshot({ path: shot("hub-paper-1440") });
    await page.goto("/coverage/");
    await expect(page.locator("[data-coverage-review] tbody tr").first()).toBeVisible();
    await settle(page);
    await page.screenshot({ path: shot("coverage-paper-1440") });
    await page.goto("/coverage/#reviewed-list");
    await expect(page.locator("#reviewed-list")).toBeInViewport();
    await page.waitForTimeout(150);
    await page.screenshot({ path: shot("coverage-reviewed-list-paper-1440") });
    await ctx.close();

    const phone = await context(browser, 390, 844, "blueprint");
    const small = await phone.newPage();
    await small.goto("/coverage/");
    await expect(small.locator("[data-coverage-review] tbody tr").first()).toBeVisible();
    await settle(small);
    await small.screenshot({ path: shot("coverage-blueprint-390") });
    await phone.close();
  });
});
