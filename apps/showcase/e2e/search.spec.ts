// The search as a visitor uses it: keyboard, hash, motion links, phone width, themes, reduced motion, and a clean
// console. Runs against the built app (vite preview on :4311).

import { expect, test, type Page } from "@playwright/test";
import { hash } from "./helpers/parity";

const PDF_BASE = "https://example.public.blob.vercel-storage.com/motions/";
const READY = '.cs[data-cs-state="ready"]';
const field = (page: Page) => page.locator('[data-cs-field="q"]');
const count = (page: Page) => page.locator("[data-cs-count]");
const cards = (page: Page) => page.locator("[data-cs-card]");

async function open(page: Page, path = "/search/", urlHash = ""): Promise<void> {
  await page.goto(`${path}${urlHash}`);
  await page.locator(READY).waitFor();
}

interface Condition {
  record: string;
  number: string;
  page: number | null;
  page_exact: boolean;
  motion_url: string | null;
}

test.describe("keyboard", () => {
  test("the skip link is the first stop and puts the cursor in the search field", async ({ page }) => {
    await open(page, "/c/?gate=1");
    const skip = page.locator(".shell-skip");
    // a page with an opening to skip shows the link all the time
    await expect(skip).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(skip).toBeFocused();
    await expect(skip).toHaveText(/Skip to search/);
    await page.keyboard.press("Enter");
    await expect(field(page)).toBeFocused();
    // the jump leaves the hash alone: the search keeps its state there
    expect(new URL(page.url()).hash).toBe("");
  });

  test("on the search's own page the skip link is off the screen until the keyboard reaches it", async ({ page }) => {
    await open(page);
    const skip = page.locator(".shell-skip");
    const size = async (): Promise<number> => skip.evaluate(el => el.getBoundingClientRect().width);
    expect(await size()).toBeLessThanOrEqual(1);
    // it is the first stop of the page: three back from the field (the theme flip, the wordmark, the skip link)
    await expect(field(page)).toBeFocused();
    for (let i = 0; i < 3; i++) await page.keyboard.press("Shift+Tab");
    await expect(skip).toBeFocused();
    expect(await page.evaluate(() => document.querySelector("a, button, input, select") === document.activeElement)).toBe(true);
    expect(await size()).toBeGreaterThan(80);
    await expect(skip).toBeInViewport();
    await page.keyboard.press("Enter");
    await expect(field(page)).toBeFocused();
  });

  test('"/" focuses the field, typing searches, Escape clears', async ({ page }) => {
    await open(page);
    await expect(field(page)).toBeFocused(); // a page of its own starts in the field
    const all = await count(page).textContent();
    await field(page).blur();
    await page.keyboard.press("/");
    await expect(field(page)).toBeFocused();
    await expect(field(page)).toHaveValue(""); // the slash is not typed
    await page.keyboard.type("odor");
    await expect(cards(page).first()).toBeVisible();
    await expect(count(page)).toContainText(/^\d+ conditions from \d+ of 352 motions/);
    await expect(count(page)).not.toHaveText(all ?? "");
    await expect(page.locator("[data-cs-card] mark").first()).toBeVisible();
    // the hash follows once the typing pauses (browsers ration writes to the address)
    await expect(page).toHaveURL(/#q=odor$/);
    // a slash typed in the field is text, not the shortcut
    await page.keyboard.type(" a/b");
    await expect(field(page)).toHaveValue("odor a/b");
    await page.keyboard.press("Escape");
    await expect(field(page)).toHaveValue("");
    await expect(field(page)).toBeFocused();
    await expect(count(page)).toHaveText(all ?? "");
    expect(new URL(page.url()).hash).toBe("");
  });

  test("the results are reachable by Tab and labelled for a screen reader", async ({ page }) => {
    await open(page, "/search/", hash({ q: "outdoor seating" }));
    // landmarks and labels
    await expect(page.getByRole("banner")).toBeVisible();
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByRole("contentinfo").first()).toBeVisible();
    await expect(page.getByRole("search")).toBeVisible();
    await expect(page.getByRole("searchbox", { name: "Search the conditions, a case number or an address" })).toBeVisible();
    for (const name of ["Business type", "Condition category", "Zoning district", "Year decided", "Which conditions"]) {
      await expect(page.getByRole("combobox", { name })).toBeVisible();
    }
    await expect(page.getByRole("region", { name: "Conditions found" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: "Conditions of approval" })).toBeVisible();
    // the count is on the screen, and announced from a live region of its own
    await expect(page.locator("[data-cs-count-text]")).toHaveText("4 conditions from 4 of 352 motions");
    const live = page.locator("[data-cs-live]");
    await expect(live).toHaveAttribute("role", "status");
    await expect(live).toHaveAttribute("aria-live", "polite");
    await expect(live).toHaveText("4 conditions from 4 of 352 motions");
    // every card is an article with a heading that says which condition it is
    await expect(page.getByRole("article")).toHaveCount(4);
    await expect(page.getByRole("heading", { level: 2, name: /^Condition 13: Hours of Operation/ })).toBeVisible();
    // Tab walks from the field to the first motion link, with a visible focus ring in the line colour
    await field(page).focus();
    const pdf = page.locator("[data-cs-pdf]").first();
    for (let i = 0; i < 20 && !(await pdf.evaluate(el => el === document.activeElement)); i++) await page.keyboard.press("Tab");
    await expect(pdf).toBeFocused();
    const ring = await pdf.evaluate(el => {
      const cs = getComputedStyle(el);
      const probe = document.createElement("i");
      probe.style.color = "var(--line)";
      document.body.append(probe);
      const line = getComputedStyle(probe).color;
      probe.remove();
      return { style: cs.outlineStyle, width: cs.outlineWidth, colour: cs.outlineColor, line };
    });
    expect(ring.style).toBe("solid");
    expect(ring.width).toBe("2px");
    expect(ring.colour).toBe(ring.line);
  });

  test('"show more" adds the next 50 and moves the keyboard to the first new card', async ({ page }) => {
    await open(page);
    await expect(cards(page)).toHaveCount(50);
    await expect(count(page)).toHaveText("3,130 conditions from 349 of 352 motions · 1,919 approval-boilerplate conditions hidden show them");
    const more = page.locator("[data-cs-more]");
    await expect(more).toHaveText("Show 50 more");
    await more.focus();
    await page.keyboard.press("Enter");
    await expect(cards(page)).toHaveCount(100);
    await expect(cards(page).nth(50)).toBeFocused();
    await expect(page.locator(".cs-more__status")).toHaveText("100 of 3,130 shown");
    // the hidden approval boilerplate comes back with "show them"
    await page.locator("[data-cs-showall]").click();
    await expect(page.locator('[data-cs-field="kind"]')).toHaveValue("all");
    await expect(count(page)).toHaveText("5,049 conditions from 352 of 352 motions");
    await expect(cards(page)).toHaveCount(50);
    // "Clear all" puts everything back
    await page.locator("[data-cs-reset]").click();
    await expect(page.locator('[data-cs-field="kind"]')).toHaveValue("");
    await expect(cards(page)).toHaveCount(50);
    expect(new URL(page.url()).hash).toBe("");
  });
});

test.describe("hash state", () => {
  test("a hash fills the fields, a change writes the hash, a reload keeps the search", async ({ page }) => {
    await open(page, "/search/", hash({ q: "noise", business: "Bar", kind: "all" }));
    await expect(field(page)).toHaveValue("noise");
    await expect(page.locator('[data-cs-field="business"]')).toHaveValue("Bar");
    await expect(page.locator('[data-cs-field="kind"]')).toHaveValue("all");
    await expect(page.locator('[data-cs-field="category"]')).toHaveValue("");
    const before = await count(page).textContent();

    await page.locator('[data-cs-field="category"]').selectOption("noise");
    expect(new URL(page.url()).hash).toBe("#q=noise&business=Bar&category=noise&kind=all");
    const narrowed = await count(page).textContent();
    expect(narrowed).not.toBe(before);

    await page.reload();
    await page.locator(READY).waitFor();
    await expect(count(page)).toHaveText(narrowed ?? "");
    await expect(page.locator('[data-cs-field="category"]')).toHaveValue("noise");

    // a hash changed in place (a pasted link, the back button) runs its search and clears what it leaves out
    await page.evaluate(() => { location.hash = "#q=outdoor+seating"; });
    await expect(count(page)).toHaveText("4 conditions from 4 of 352 motions");
    await expect(page.locator('[data-cs-field="business"]')).toHaveValue("");
    await expect(field(page)).toHaveValue("outdoor seating");
  });

  test("a card link shows, marks and focuses its card, and the link on a card leads back to it", async ({ page }) => {
    await open(page, "/search/", "#q=2015-009955CUA&kind=all&card=30");
    const target = page.locator("[data-cs-card].is-target");
    await expect(target).toHaveCount(1);
    await expect(target).toHaveAttribute("data-number", "30");
    await expect(target).toBeFocused();
    await expect(target).toBeInViewport();
    await expect(cards(page)).toHaveCount(51); // the 51st card: the second page was opened for it
    expect(new URL(page.url()).hash).toBe("#q=2015-009955CUA&kind=all"); // the card key is not kept

    const link = cards(page).nth(3).locator("[data-cs-permalink]");
    const number = await cards(page).nth(3).getAttribute("data-number");
    expect(await link.getAttribute("href")).toBe(
      `${new URL(page.url()).origin}/search/#q=2015-009955CUA&kind=all&card=${encodeURIComponent(number ?? "")}`,
    );
    await link.click();
    await expect(page.locator("[data-cs-card].is-target")).toHaveAttribute("data-number", number ?? "");
  });
});

test.describe("motion links", () => {
  test("the page link is the public copy at the condition's page, and Planning's copy is the second link", async ({ page, request }) => {
    const data = (await (await request.get("/data/conditions.json")).json()) as { conditions: Condition[] };
    const find = (record: string, number: string): Condition => {
      const c = data.conditions.find(x => x.record === record && String(x.number) === number);
      if (!c) throw new Error(`no condition ${record} #${number}`);
      return c;
    };
    for (const record of ["2015-009955CUA", "2010.1070C_3", "2011.1216C"]) {
      await open(page, "/search/", hash({ q: record, kind: "all" }));
      const n = await cards(page).count();
      expect(n).toBeGreaterThan(0);
      for (let i = 0; i < n; i++) {
        const card = cards(page).nth(i);
        const c = find(record, (await card.getAttribute("data-number")) ?? "");
        const pdf = card.locator("[data-cs-pdf]");
        const expected = `${PDF_BASE}${record}.pdf${c.page ? `#page=${c.page}` : ""}`;
        await expect(pdf).toHaveAttribute("href", expected);
        await expect(pdf).toHaveAttribute("target", "_blank");
        await expect(pdf).toHaveAttribute("rel", "noopener");
        await expect(pdf).toContainText(c.page ? `${c.page_exact ? "" : "near "}p. ${c.page} · open the motion` : "open the motion");
        if (c.motion_url) {
          const href = await card.locator("[data-cs-planning]").getAttribute("href");
          expect(href).toBe(c.motion_url.replace("showopendialog=1", "showopendialog=0"));
          expect(href).toContain("showopendialog=0");
        }
      }
    }
    // no feedback address is configured here, so no card has the "Wrong or missing? Tell me" link
    await expect(page.locator("a.feedback")).toHaveCount(0);
    await expect(page.getByText("Wrong or missing?")).toHaveCount(0);
  });
});

test.describe("phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  const overflow = (page: Page) =>
    page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
      wide: [...document.querySelectorAll<HTMLElement>("body *")]
        .filter(el => el.getBoundingClientRect().right > document.documentElement.clientWidth + 0.5 && !el.closest(".cs-table__scroll, .cov-scroll, .vh, .cs-list--one-case .cs-meta"))
        .slice(0, 5)
        .map(el => el.className || el.tagName),
    }));

  test("no horizontal scroll at 390 px, with filters folded away", async ({ page }) => {
    for (const urlHash of ["", hash({ q: "outdoor seating" }), hash({ q: "2015-009955CUA", kind: "all" }), hash({ q: "xylophone" })]) {
      await open(page, "/search/", urlHash);
      const o = await overflow(page);
      expect(o.wide, `elements wider than the screen at ${urlHash || "(empty)"}`).toEqual([]);
      expect(o.scroll).toBeLessThanOrEqual(o.client);
    }
    // filters are a disclosure here: closed, then open, and still nothing runs off the side
    const filters = page.getByRole("button", { name: /^Filters/ });
    await expect(filters).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator('[data-cs-field="business"]')).toBeHidden();
    await filters.click();
    await expect(filters).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator('[data-cs-field="business"]')).toBeVisible();
    await page.getByRole("button", { name: /^Coverage/ }).click();
    await expect(page.locator("[data-cs-coverage]")).toBeVisible();
    await page.locator("[data-cs-tips]").click();
    await expect(page.locator(".cs-tips__body")).toBeVisible();
    await page.locator(".cs-removed summary").click();
    await page.locator(".cs-none summary").click();
    const o = await overflow(page);
    expect(o.wide).toEqual([]);
    expect(o.scroll).toBeLessThanOrEqual(o.client);
    // the field stays large
    const size = await field(page).evaluate(el => parseFloat(getComputedStyle(el).fontSize));
    expect(size).toBeGreaterThanOrEqual(32);
    // a filter set from the folded row is counted on it
    await page.locator('[data-cs-field="business"]').selectOption("Bar");
    await expect(filters).toContainText("1 set");
  });

  test("the contents page and the front page fit too", async ({ page }) => {
    for (const path of ["/", "/c/", "/coverage/"]) {
      await page.goto(path);
      await page.locator(path === "/" ? ".hub__list" : path === "/coverage/" ? "[data-coverage-review] tbody tr" : READY).first().waitFor();
      const o = await overflow(page);
      expect(o.wide, `elements wider than the screen on ${path}`).toEqual([]);
      expect(o.scroll).toBeLessThanOrEqual(o.client);
    }
  });
});

test.describe("theme", () => {
  const ground = (page: Page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);

  test("follows the system, flips, and remembers the flip", async ({ browser }) => {
    const context = await browser.newContext({ colorScheme: "light" });
    const page = await context.newPage();
    await open(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "paper");
    expect(await ground(page)).toBe("rgb(242, 237, 225)");

    await page.evaluate(() => {
      (window as unknown as { seen: string[] }).seen = [];
      window.addEventListener("themechange", e => (window as unknown as { seen: string[] }).seen.push((e as CustomEvent<{ theme: string }>).detail.theme));
    });
    const flip = page.getByRole("button", { name: "Switch to the blueprint theme" });
    await flip.click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "blueprint");
    expect(await ground(page)).toBe("rgb(10, 15, 31)");
    expect(await page.evaluate(() => (window as unknown as { seen: string[] }).seen)).toEqual(["blueprint"]);
    // the browser's own chrome (a phone's address bar) takes the ground of the theme in use
    const chrome = (): Promise<string[]> =>
      page.evaluate(() => [...document.querySelectorAll('meta[name="theme-color"]')].map(m => m.getAttribute("content") ?? ""));
    expect(await chrome()).toEqual(["#0a0f1f", "#0a0f1f"]);
    await expect(page.getByRole("button", { name: "Switch to the paper theme" })).toBeVisible();

    // remembered across a reload and on another page, against the system setting
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "blueprint");
    expect(await chrome()).toEqual(["#0a0f1f", "#0a0f1f"]); // set before first paint, by the script in the head
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "blueprint");
    expect(await ground(page)).toBe("rgb(10, 15, 31)");
    await page.getByRole("button", { name: "Switch to the paper theme" }).click();
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "paper");
    await context.close();
  });

  test("a dark system starts in blueprint, and follows the system until a choice is made", async ({ browser }) => {
    const context = await browser.newContext({ colorScheme: "dark" });
    const page = await context.newPage();
    await open(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "blueprint");
    await page.emulateMedia({ colorScheme: "light" });
    await expect(page.locator("html")).toHaveAttribute("data-theme", "paper");
    await context.close();
  });
});

test.describe("reduced motion", () => {
  const placeholder = (page: Page) => field(page).getAttribute("placeholder");

  test("with reduced motion nothing cycles or animates", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await open(page);
    const first = await placeholder(page);
    expect(first).toBe("e.g. odor");
    const durations = await page.evaluate(() => ({
      flip: getComputedStyle(document.querySelector(".theme-flip svg") as Element).transitionDuration,
      token: getComputedStyle(document.documentElement).getPropertyValue("--dur-2").trim(),
    }));
    expect(parseFloat(durations.flip)).toBeLessThan(0.001);
    expect(parseFloat(durations.token)).toBeLessThanOrEqual(0.01);
    await page.waitForTimeout(4200);
    expect(await placeholder(page)).toBe(first);
    await context.close();
  });

  test("without it the placeholder cycles through the examples", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "no-preference" });
    const page = await context.newPage();
    await open(page);
    expect(await placeholder(page)).toBe("e.g. odor");
    await expect(field(page)).toHaveAttribute("placeholder", "e.g. amplified music", { timeout: 6000 });
    await context.close();
  });
});

test.describe("the handle a prototype gets", () => {
  test("setQuery, getState, the results event and destroy", async ({ page }) => {
    await open(page);
    const result = await page.evaluate(async () => {
      type Handle = { setQuery(q: string): void; getState(): Record<string, unknown>; destroy(): void };
      const { search } = (window as unknown as { showcase: { search: Handle } }).showcase;
      const seen: { n: number; first: string; total: unknown }[] = [];
      document.addEventListener("cs:results", e => {
        const d = (e as CustomEvent<{ hits: { record: string }[]; state: { total: number } }>).detail;
        seen.push({ n: d.hits.length, first: d.hits[0]?.record ?? "", total: d.state.total });
      });
      search.setQuery("outdoor seating");
      const state = search.getState();
      search.destroy();
      return { seen, state, left: document.querySelector("#search")?.childElementCount };
    });
    expect(result.seen).toEqual([{ n: 4, first: "2019-012888CUA", total: 4 }]);
    expect(result.state).toMatchObject({ q: "outdoor seating", business: "", kind: "", total: 4, motions: 4, hidden: 0, shown: 4, ready: true });
    expect(result.left).toBe(0);
    // destroyed: the shortcut no longer reaches for a field that is gone
    await page.keyboard.press("/");
    await expect(page.locator('[data-cs-field="q"]')).toHaveCount(0);
  });
});

test.describe("loading", () => {
  test('shows "Reading 352 motions…" with a real progress rule, never a spinner', async ({ page }) => {
    let release: () => void = () => {};
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route("**/data/conditions.json", async route => {
      await gate;
      await route.continue();
    });
    await page.goto("/search/");
    await expect(page.locator("[data-cs-loading]")).toContainText("Reading 352 motions…");
    await expect(page.locator("[data-cs-progress]")).toHaveAttribute("role", "progressbar");
    await expect(page.locator('.cs[data-cs-state="loading"]')).toBeVisible();
    release();
    await page.locator(READY).waitFor();
    await expect(page.locator("[data-cs-loading]")).toHaveCount(0);
    await expect(cards(page)).toHaveCount(50);
  });

  test("says so when the data cannot be loaded", async ({ page }) => {
    await page.route("**/data/conditions.json", route => route.fulfill({ status: 404, body: "not found" }));
    await page.goto("/search/");
    await expect(page.locator(".cs-empty--error")).toContainText("Could not load the data.");
    await expect(page.locator(".cs-empty--error")).toContainText("try again");
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  });

  test("the progress total comes from Content-Length", async ({ page }) => {
    await page.goto("/");
    const head = await page.evaluate(async () => {
      const response = await fetch("data/conditions.json", { method: "HEAD" });
      return { length: Number(response.headers.get("content-length")), encoding: response.headers.get("content-encoding") };
    });
    expect(head.length).toBeGreaterThan(5_000_000);
    expect(head.encoding).toBeNull();
  });
});

test.describe("clean console", () => {
  for (const path of ["/", "/c/", "/search/", "/coverage/"]) {
    test(`no console errors or failed requests on ${path}`, async ({ page, baseURL }) => {
      const problems: string[] = [];
      page.on("console", message => {
        // headless Chromium draws WebGL in software and says so four times ("GL Driver Message … GPU stall due to
        // ReadPixels"): the browser's note about itself, not the page's (a window with a GPU never prints it)
        if (/GL Driver Message/.test(message.text())) return;
        if (message.type() === "error" || message.type() === "warning") problems.push(`${message.type()}: ${message.text()}`);
      });
      page.on("pageerror", error => problems.push(`pageerror: ${error.message}`));
      page.on("requestfailed", request => problems.push(`failed: ${request.url()}`));
      page.on("response", response => {
        if (response.status() >= 400) problems.push(`${response.status()}: ${response.url()}`);
      });
      const external: string[] = [];
      page.on("request", request => {
        if (!request.url().startsWith(`${baseURL}/`) && !request.url().startsWith("data:")) external.push(request.url());
      });
      await page.goto(path);
      if (path === "/") await page.locator(".hub__list").waitFor();
      else if (path === "/coverage/") await page.locator("[data-coverage-review] tbody tr").first().waitFor();
      else {
        await page.locator(READY).waitFor();
        await page.locator('[data-cs-field="q"]').fill("noise 10 pm");
        await expect(cards(page).first()).toBeVisible();
        await page.locator('[data-cs-field="kind"]').selectOption("all");
        await page.locator(".cs[data-cs-warm]").waitFor();
      }
      await page.evaluate(() => document.fonts.ready);
      expect(problems).toEqual([]);
      // nothing is fetched from anywhere else at runtime (the motion PDFs are links, not requests)
      expect(external).toEqual([]);
      // every page has the icon (drawn in code, served with the site) and a colour for the browser's chrome
      const icon = await page.locator('link[rel="icon"]').getAttribute("href");
      expect(icon).toMatch(/favicon[\w-]*\.svg$/);
      expect((await page.request.get(new URL(icon ?? "", page.url()).href)).headers()["content-type"]).toContain("image/svg+xml");
      await expect(page.locator('meta[name="theme-color"]')).toHaveCount(2);
      // the wordmark is the only product name on the page, and it comes from brand.ts
      await expect(page.locator(".mark-link")).toHaveAttribute("aria-label", /^Working Title/);
    });
  }
});
