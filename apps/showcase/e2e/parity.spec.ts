// Same results, same order, same counts: every case below is loaded by its URL hash on the current site's page
// (served unchanged on :4312) and on the showcase (:4311), "show more" is clicked until everything is shown on
// both, and the ordered list of (case number, condition number), the count sentence, the linked card and the
// hash written back must be identical.

import { expect, test } from "@playwright/test";
import { CURRENT, SHOWCASE } from "../playwright.config";
import { CASES } from "./helpers/cases";
import { expectParity, hash, readFilters } from "./helpers/parity";

/** The showcase pages held to parity (see helpers/parity.ts). The public site's own build is held to the live site
 *  by e2e-site/site.spec.ts. */
const PATHS = (process.env.PARITY_PATHS ?? "/search/,/c/").split(",").map(p => p.trim()).filter(Boolean);

for (const path of PATHS) {
  test.describe(`parity with the current site: ${path}`, () => {
    for (const c of CASES) {
      test(c.name, async ({ context }) => {
        const { current, showcase } = await expectParity(context, c.hash, { path });
        // the case must be a real one: the current site itself has to find what the case is about
        if (c.exact !== undefined) expect(current.cards.length).toBe(c.exact);
        if (c.min !== undefined) expect(current.cards.length).toBeGreaterThanOrEqual(c.min);
        if (c.hash.includes("card=7A")) expect(showcase.target).toBe("2015-009955CUA #7A");
        if (c.hash.includes("card=30")) expect(showcase.target).toBe("2015-009955CUA #30");
        if (c.hash.includes("card=99")) expect(showcase.target).toBeNull();
        test.info().annotations.push({ type: "result", description: `${showcase.cards.length} conditions · ${showcase.count}` });
      });
    }

    // The headline differs on purpose (the current page says "No condition matches these filters." even when no
    // filter is set; the showcase names what was searched for). The note that explains why is the current site's.
    test("the no-match note reads the same", async ({ context }) => {
      for (const q of ["xylophone", "noise xylophone", "2099-123456CUA"]) {
        const [a, b] = [await context.newPage(), await context.newPage()];
        await a.goto(`${CURRENT}/index.html${hash({ q })}`);
        await b.goto(`${SHOWCASE}${path}${hash({ q })}`);
        const old = (await a.locator("#results .empty").textContent())?.replace(/\s+/g, " ").trim() ?? "";
        expect(old.startsWith("No condition matches these filters. ")).toBe(true);
        const now = ((await b.locator("[data-cs-empty-note]").textContent()) ?? "").replace(/\s+/g, " ").trim();
        expect(now).toBe(old.replace("No condition matches these filters. ", ""));
        await expect(b.locator(".cs-empty__line")).toHaveText(`No condition matches “${q}”.`);
        await Promise.all([a.close(), b.close()]);
      }
    });

    test("the filter menus hold the same options in the same order", async ({ context }) => {
      const [a, b] = [await context.newPage(), await context.newPage()];
      await a.goto(`${CURRENT}/index.html`);
      await a.locator("#results .card").first().waitFor();
      await b.goto(`${SHOWCASE}${path}`);
      await b.locator("[data-cs-card]").first().waitFor();
      const [old, now] = [await readFilters(a, "current"), await readFilters(b, "showcase")];
      expect(now).toEqual(old);
      expect(now.zoning?.length).toBeGreaterThan(20);
    });

    test("the coverage sentences and the search tips read the same", async ({ context }) => {
      const [a, b] = [await context.newPage(), await context.newPage()];
      await a.goto(`${CURRENT}/index.html`);
      await a.locator("#results .card").first().waitFor();
      await b.goto(`${SHOWCASE}${path}`);
      await b.locator("[data-cs-card]").first().waitFor();
      const squash = (s: string | null): string => (s ?? "").replace(/\s+/g, " ").trim();
      expect(squash(await b.locator("[data-cs-coverage]").evaluate(el => [...el.querySelectorAll("p:not(.cs-coverage__more)")].map(p => p.textContent).join(" ")))).toBe(
        squash(await a.locator("#coverage-text").textContent()),
      );
      expect(await b.locator("[data-cs-synonyms] li").allTextContents()).toEqual(await a.locator("#synonyms li").allTextContents());
      expect(squash(await b.locator("[data-cs-sub]").textContent())).toBe(squash(await a.locator("#sub").textContent()));
    });
  });
}
