// The page as set: nothing overprints, the first result is in view, a finger can hit every control, and nothing
// runs off the side. These are the layout defects a design review found, held as measurements.

import { expect, test, type Page } from "@playwright/test";
import { hash } from "./helpers/parity";

const READY = '.cs[data-cs-state="ready"]';

async function open(page: Page, urlHash = "", path = "/search/"): Promise<void> {
  await page.goto(`${path}${urlHash}`);
  await page.locator(READY).waitFor();
  await page.evaluate(() => document.fonts.ready);
}

test.describe("desktop", () => {
  test("the coverage notice in the margin never sits on top of the notes (1440 px)", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page, hash({ q: "outdoor seating" }));
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    let checked = 0;
    for (let y = 0; y <= height; y += 150) {
      await page.evaluate(top => window.scrollTo(0, top), y);
      const overlap = await page.evaluate(() => {
        const aside = document.querySelector(".cs-coverage")?.getBoundingClientRect();
        if (!aside) throw new Error("no coverage notice");
        let worst = 0;
        for (const el of document.querySelectorAll(".cs-notes p, .cs-notes summary, .cs-notes h2, .cs-notes td, [data-cs-card] .cs-text")) {
          const range = document.createRange();
          range.selectNodeContents(el);
          for (const r of range.getClientRects()) {
            const w = Math.min(r.right, aside.right) - Math.max(r.left, aside.left);
            const h = Math.min(r.bottom, aside.bottom) - Math.max(r.top, aside.top);
            if (w > 0 && h > 0) worst = Math.max(worst, Math.min(w, h));
          }
        }
        return worst;
      });
      expect(overlap, `text under the coverage notice at scroll ${y}`).toBe(0);
      checked += 1;
    }
    expect(checked).toBeGreaterThan(10);
  });

  // where the first result starts, so the heading and the form do not grow back over the results
  for (const [width, height, limit] of [[1440, 900, 500], [1024, 768, 560]] as const) {
    test(`the first result starts in the upper part of a ${width} × ${height} window`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await open(page, hash({ q: "outdoor seating" }));
      const top = await page.locator("[data-cs-card]").first().evaluate(el => el.getBoundingClientRect().top);
      expect(top).toBeLessThanOrEqual(limit);
      // and its text has begun
      const text = await page.locator("[data-cs-card] .cs-text").first().evaluate(el => el.getBoundingClientRect().top);
      expect(text).toBeLessThan(height - 56);
    });
  }

  for (const width of [1440, 1280, 1024, 820]) {
    test(`the "Which conditions" menu shows its whole default at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await open(page);
      const room = await page.locator('[data-cs-field="kind"]').evaluate((select: HTMLSelectElement) => {
        const cs = getComputedStyle(select);
        const canvas = document.createElement("canvas").getContext("2d");
        if (!canvas) throw new Error("no canvas");
        canvas.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
        const text = select.selectedOptions[0]?.textContent ?? "";
        return { text, need: canvas.measureText(text).width, have: select.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) };
      });
      expect(room.text).toBe("Case-specific, then standard (no boilerplate)");
      expect(room.have).toBeGreaterThanOrEqual(room.need);
    });
  }
});

test.describe("phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("every control is at least 44 px tall to a finger", async ({ page }) => {
    await open(page, hash({ q: "2015-009955CUA" }));
    await page.getByRole("button", { name: /^Filters/ }).click();
    const small = await page.evaluate(() => {
      const targets = [
        ".theme-flip", ".mark-link", "[data-cs-clear]", "[data-cs-tips]", ".cs-fold", ".cs-select select", "[data-cs-showall]",
        "[data-cs-reset]", "[data-cs-pdf]", "[data-cs-planning]", "[data-cs-permalink]", ".cs-removed summary",
        ".cs-none summary", ".shell-foot__nav a", '.cs-notes a[href*="coverage"]',
      ];
      const out: string[] = [];
      for (const selector of targets) {
        const found = [...document.querySelectorAll<HTMLElement>(selector)].filter(el => el.getClientRects().length);
        if (!found.length) out.push(`${selector}: not on the page`);
        for (const el of found.slice(0, 6)) {
          const r = el.getBoundingClientRect();
          if (r.height < 43.5 || r.width < 43.5) out.push(`${selector}: ${Math.round(r.width)}x${Math.round(r.height)}`);
        }
      }
      return out;
    });
    expect(small).toEqual([]);
  });

  test("the first result starts in the upper part of the screen, and the count is two tidy lines", async ({ page }) => {
    await open(page, hash({ q: "2015-009955CUA" }));
    // the results begin with the motion they all come from, then the first card
    const top = await page.locator("[data-cs-case]").evaluate(el => el.getBoundingClientRect().top);
    expect(top).toBeLessThanOrEqual(500);
    const card = await page.locator("[data-cs-card]").first().evaluate(el => el.getBoundingClientRect().top);
    expect(card).toBeLessThanOrEqual(620);
    const bar = await page.evaluate(() => {
      // lines of text in an element: boxes whose middles are more than half a line apart
      const lines = (el: Element | null): number => {
        if (!el) return 0;
        const range = document.createRange();
        range.selectNodeContents(el);
        const middles = [...range.getClientRects()].filter(r => r.width > 1).map(r => (r.top + r.bottom) / 2).sort((a, b) => a - b);
        return middles.filter((y, i) => i === 0 || y - (middles[i - 1] as number) > 10).length;
      };
      const middle = (el: Element | null): number => {
        const r = el?.getBoundingClientRect();
        return r ? (r.top + r.bottom) / 2 : -99;
      };
      const hidden = document.querySelector("[data-cs-hidden]");
      return {
        first: lines(document.querySelector("[data-cs-count-text]")),
        hidden: lines(hidden),
        height: document.querySelector(".cs-bar")?.getBoundingClientRect().height ?? 0,
        // "Clear all" ends the last line: it is not on a line of its own
        level: Math.abs(middle(document.querySelector("[data-cs-reset]")) - middle(hidden)),
      };
    });
    expect(bar.first).toBe(1);
    expect(bar.hidden).toBe(1);
    expect(bar.level).toBeLessThan(4);
    expect(bar.height).toBeLessThanOrEqual(73); // two lines of 24, the padding and the rules
    // read aloud or copied, the sentence is the current site's
    const text = (await page.locator("[data-cs-count]").evaluate((el: HTMLElement) => el.innerText)).replace(/\s+/g, " ").trim();
    expect(text).toBe("43 conditions from 1 of 352 motions · 8 approval-boilerplate conditions hidden show them");
  });

  test("a date, a case number or a business type is never broken across two lines", async ({ page }) => {
    for (const q of ["2015-009955CUA", "outdoor seating", "live music"]) {
      await open(page, hash({ q }));
      const seen = await page.evaluate(() => {
        // the facts on the screen (a list from one motion keeps each card's copy for screen readers only)
        const facts = [...document.querySelectorAll(".cs-meta > div:not(.cs-meta__address)")].filter(
          el => !el.closest(".cs-list--one-case .cs-card:not(.is-target)"),
        );
        const broken = facts.filter(el => {
          const range = document.createRange();
          range.selectNodeContents(el.querySelector("dd") as Element);
          const middles = [...range.getClientRects()].map(r => (r.top + r.bottom) / 2);
          return Math.max(...middles) - Math.min(...middles) > 10;
        });
        return { facts: facts.length, broken: broken.map(el => el.textContent) };
      });
      expect(seen.facts).toBeGreaterThan(3);
      expect(seen.broken).toEqual([]);
    }
  });
});

test.describe("a very narrow screen", () => {
  for (const path of ["/search/", "/c/", "/", "/coverage/"]) {
    test(`nothing runs off the side at 320 px on ${path}`, async ({ browser }) => {
      const context = await browser.newContext({ viewport: { width: 320, height: 640 }, hasTouch: true, isMobile: true });
      const page = await context.newPage();
      await page.goto(`${path}${path === "/search/" ? hash({ q: "2015-009955CUA" }) : ""}`);
      await page.locator(path === "/" ? ".hub__list" : path === "/coverage/" ? "[data-coverage-facts] tr" : READY).first().waitFor();
      const o = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
      expect(o.scroll).toBeLessThanOrEqual(o.client);
      const flip = await page.locator(".theme-flip").evaluate(el => el.getBoundingClientRect().right);
      expect(flip).toBeLessThanOrEqual(320);
      await context.close();
    });
  }
});
