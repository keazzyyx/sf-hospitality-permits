// What must not come back: the defects two reviews of the foundation found. Each test is the reviewer's own
// reproduction, held as a test. Runs against the built app (vite preview on :4311).

import { expect, test, type Page, type Route } from "@playwright/test";
import { hash } from "./helpers/parity";

const READY = '.cs[data-cs-state="ready"]';
const DATA = "**/data/conditions.json";
const field = (page: Page) => page.locator('[data-cs-field="q"]');
const count = (page: Page) => page.locator("[data-cs-count]");
const cards = (page: Page) => page.locator("[data-cs-card]");

async function open(page: Page, path = "/search/", urlHash = ""): Promise<void> {
  await page.goto(`${path}${urlHash}`);
  await page.locator(READY).waitFor();
}

/** Everything that would show in the console as a problem. */
function watch(page: Page): string[] {
  const problems: string[] = [];
  page.on("console", message => {
    if (message.type() === "error" || message.type() === "warning") problems.push(`${message.type()}: ${message.text()}`);
  });
  page.on("pageerror", error => problems.push(`pageerror: ${error.message}`));
  return problems;
}

/** Hold the data back until `release()` is called. */
async function holdData(page: Page): Promise<() => void> {
  let release: () => void = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route(DATA, async route => {
    await gate;
    await route.continue();
  });
  return release;
}

test.describe("data that cannot be used", () => {
  for (const body of ["{}", "null", "[]", '{"conditions":[]}', '{"conditions":[{}],"motions_without_conditions":[],"removed_motions":[],"boilerplate_titles":[]}']) {
    test(`a 200 response that is not the data (${body.slice(0, 24)}) is an error the page states, not a hang`, async ({ page }) => {
      const problems = watch(page);
      await page.route(DATA, route => route.fulfill({ status: 200, contentType: "application/json", body }));
      await page.goto("/search/#q=noise");
      await expect(page.locator(".cs")).toHaveAttribute("data-cs-state", "error");
      await expect(page.getByRole("alert")).toContainText("Could not load the data.");
      await expect(page.locator("[data-cs-loading]")).toHaveCount(0);
      // the handle says so too
      const ready = await page.evaluate(() =>
        (window as unknown as { showcase: { search: { ready: Promise<void> } } }).showcase.search.ready.then(() => "resolved", () => "rejected"),
      );
      expect(ready).toBe("rejected");
      // and nothing throws afterwards: the field is not a dead end that raises on every key
      await expect(field(page)).toHaveJSProperty("readOnly", true);
      await page.keyboard.type("noise");
      for (const select of await page.locator(".cs-select select").all()) await expect(select).toBeDisabled();
      expect(problems).toEqual([]);
    });
  }

  test('"Try again" downloads the data again and the search works', async ({ page }) => {
    const problems: string[] = [];
    page.on("pageerror", error => problems.push(error.message));
    let calls = 0;
    await page.route(DATA, (route: Route) => (++calls === 1 ? route.fulfill({ status: 200, contentType: "application/json", body: "{}" }) : route.continue()));
    await page.goto("/search/#q=outdoor+seating");
    await expect(page.locator(".cs")).toHaveAttribute("data-cs-state", "error");
    // the link's search stays in the field while the page cannot run it
    await expect(field(page)).toHaveValue("outdoor seating");
    const again = page.getByRole("button", { name: "Try again" });
    await expect(again).toBeVisible();
    await again.click();
    await page.locator(READY).waitFor();
    await expect(count(page)).toHaveText("4 conditions from 4 of 352 motions");
    await expect(cards(page)).toHaveCount(4);
    await expect(field(page)).toHaveJSProperty("readOnly", false);
    await expect(page.locator("[data-shell-facts]")).toContainText("decided 14 Jan 2010");
    expect(calls).toBe(2);
    expect(problems).toEqual([]);
  });

  test("a failed download (404) can be tried again too", async ({ page }) => {
    let calls = 0;
    await page.route(DATA, (route: Route) => (++calls === 1 ? route.fulfill({ status: 404, body: "not found" }) : route.continue()));
    await page.goto("/search/");
    await page.getByRole("button", { name: "Try again" }).click();
    await page.locator(READY).waitFor();
    await expect(cards(page)).toHaveCount(50);
  });

  test("the data file cannot put markup or a script link on the page", async ({ page }) => {
    const alerts: string[] = [];
    page.on("dialog", dialog => { alerts.push(dialog.message()); void dialog.dismiss(); });
    await page.route(DATA, async route => {
      const response = await route.fetch();
      const data = (await response.json()) as { motions: unknown; motions_with_conditions: unknown; conditions: { motion_url: string; record: string }[] };
      data.motions = '<img src=x onerror="alert(1)" data-injected>';
      data.motions_with_conditions = '<img src=x onerror="alert(2)" data-injected>';
      for (const c of data.conditions) if (c.record === "2019-012888CUA") c.motion_url = "javascript:alert(9)//showopendialog=1";
      await route.fulfill({ response, json: data });
    });
    await page.goto("/search/#q=outdoor+seating");
    await page.locator(READY).waitFor();
    await expect(cards(page)).toHaveCount(4);
    await page.waitForTimeout(200);
    expect(alerts).toEqual([]);
    await expect(page.locator("[data-injected]")).toHaveCount(0);
    expect(await page.locator('a[href^="javascript:" i]').count()).toBe(0);
    // the other cards keep Planning's link; the one with the script URL has none
    await expect(page.locator("[data-cs-planning]")).toHaveCount(3);
  });
});

test.describe("the coverage page", () => {
  test("the three coverage links of the current page are on the search, and lead somewhere", async ({ page }) => {
    await open(page);
    const links = page.locator('.cs a[href*="coverage"]');
    await expect(links).toHaveText(["Coverage details", "What this page covers, and what it does not", "The reviewed list"]);
    await expect(page.locator("[data-cs-notes]")).toContainText("The reviewed list gives each change and its reason.");

    await page.getByRole("link", { name: "The reviewed list" }).click();
    await expect(page).toHaveURL(/\/coverage\/#reviewed-list$/);
    await expect(page.getByRole("heading", { level: 1, name: "Coverage" })).toBeVisible();
    const reviewed = page.locator("#reviewed-list");
    await expect(reviewed).toBeInViewport();
    expect(await page.locator("[data-coverage-review] tbody tr").count()).toBeGreaterThan(50);
    // the numbers, worked out from the data
    await expect(page.locator("[data-coverage-facts]")).toContainText("Motions with conditions on the page");
    await expect(page.locator("[data-coverage-facts]")).toContainText("352");
    await expect(page.locator("[data-coverage-facts]")).toContainText("5,049");
    // the detail sections of the current site's README
    await expect(page.getByRole("heading", { level: 2, name: "Text quality" })).toBeVisible();
    // and back
    await page.getByRole("link", { name: "Back to the search" }).first().click();
    await expect(page).toHaveURL(/\/search\/$/);
    await page.locator(READY).waitFor();
  });

  test("the front page links to it as well", async ({ page }) => {
    await open(page, "/c/?gate=1");
    await expect(page.locator('.cs a[href*="coverage"]')).toHaveCount(3);
    // /c/ opens on its gate: "Skip to search" is the one action that reaches the search
    await page.locator(".shell-skip").click();
    // (in the front page's panel the notice that holds this link is folded under the "Coverage" word)
    const href = await page.locator(".cs a", { hasText: "Coverage details" }).evaluate(a => (a as HTMLAnchorElement).href);
    await page.goto(href);
    await expect(page).toHaveURL(/\/coverage\/$/);
    await expect(page.locator("[data-coverage-facts] tr").first()).toBeVisible();
  });

  test("it says so when the data cannot be loaded", async ({ page }) => {
    await page.route(DATA, route => route.fulfill({ status: 404, body: "not found" }));
    await page.goto("/coverage/");
    await expect(page.getByRole("alert")).toContainText("Could not load the data.");
  });
});

test.describe("keyboard focus", () => {
  for (const size of [{ width: 640, height: 450 }, { width: 375, height: 800 }, { width: 1280, height: 800 }]) {
    test(`"show them" from the keyboard leaves the focus on the menu it changed (${size.width} px)`, async ({ page }) => {
      await page.setViewportSize(size);
      await open(page, "/search/", hash({ q: "noise" }));
      await page.locator("[data-cs-showall]").focus();
      await page.keyboard.press("Enter");
      const kind = page.locator('[data-cs-field="kind"]');
      await expect(kind).toHaveValue("all");
      await expect(kind).toBeVisible();
      await expect(kind).toBeFocused();
    });
  }

  for (const size of [{ width: 1280, height: 720 }, { width: 390, height: 844 }]) {
    test(`a link to a card lands with the card at the top of the window (${size.width} px)`, async ({ page }) => {
      await page.setViewportSize(size);
      // the 51st of 51 cards, and one on the first page: both must be where the window is, not near it
      for (const number of ["30", "7A"]) {
        await page.goto("about:blank");
        await open(page, "/search/", `#q=2015-009955CUA&kind=all&card=${number}`);
        const target = page.locator("[data-cs-card].is-target");
        await expect(target).toHaveAttribute("data-number", number);
        await expect(target).toBeFocused();
        await page.waitForTimeout(300); // long enough for any late layout to have moved it
        const top = await target.evaluate(el => el.getBoundingClientRect().top);
        expect(top).toBeGreaterThanOrEqual(0);
        expect(top).toBeLessThanOrEqual(40);
      }
    });
  }

  test("the focus ring of a linked card does not run over its text on a phone", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await open(page, "/search/", "#q=2015-009955CUA&kind=all&card=30");
    const target = page.locator("[data-cs-card].is-target");
    await expect(target).toBeFocused();
    const gap = await target.evaluate(card => {
      const cs = getComputedStyle(card);
      const box = card.getBoundingClientRect();
      const offset = parseFloat(cs.outlineOffset);
      const width = parseFloat(cs.outlineWidth);
      // the inner edge of the ring, from the left
      const ring = offset >= 0 ? box.left - offset : box.left - offset + width;
      const range = document.createRange();
      range.selectNodeContents(card.querySelector(".cs-text") as Element);
      const text = Math.min(...[...range.getClientRects()].map(r => r.left));
      const num = (card.querySelector("[data-cs-num]") as Element).getBoundingClientRect().left;
      return { text: text - ring, num: num - ring, left: box.left - Math.max(0, offset) - width };
    });
    expect(gap.text).toBeGreaterThanOrEqual(4);
    expect(gap.num).toBeGreaterThanOrEqual(4);
    expect(gap.left).toBeGreaterThanOrEqual(0); // and the ring itself is on the screen
  });
});

test.describe("typing while the data is still coming", () => {
  test("what the visitor types during the download is kept, and searched", async ({ page }) => {
    const release = await holdData(page);
    await page.goto("/search/");
    await expect(page.locator("[data-cs-loading]")).toBeVisible();
    await expect(field(page)).toBeFocused();
    await page.keyboard.type("noise");
    release();
    await page.locator(READY).waitFor();
    await expect(field(page)).toHaveValue("noise");
    await expect(count(page)).toContainText(/^\d+ conditions from \d+ of 352 motions/);
    await expect(count(page)).not.toContainText("3,130");
    await expect(page).toHaveURL(/#q=noise$/);
    await expect(page.locator("[data-cs-clear]")).toBeVisible();
  });

  test("a link's search is in the field from the first paint, and typing over it wins", async ({ page }) => {
    const release = await holdData(page);
    await page.goto("/search/#q=odor&business=Bar");
    await expect(page.locator("[data-cs-loading]")).toBeVisible();
    await expect(field(page)).toHaveValue("odor");
    await expect(page.locator("[data-cs-clear]")).toBeVisible();
    await field(page).fill("noise");
    release();
    await page.locator(READY).waitFor();
    await expect(field(page)).toHaveValue("noise");
    // the rest of the link still applies
    await expect(page.locator('[data-cs-field="business"]')).toHaveValue("Bar");
    await expect(page).toHaveURL(/#q=noise&business=Bar$/);
  });

  test("a link opened and left alone shows the link's search", async ({ page }) => {
    const release = await holdData(page);
    await page.goto("/search/#q=outdoor+seating");
    await expect(field(page)).toHaveValue("outdoor seating");
    release();
    await page.locator(READY).waitFor();
    await expect(field(page)).toHaveValue("outdoor seating");
    await expect(count(page)).toHaveText("4 conditions from 4 of 352 motions");
  });

  test("the line under the title is the same before and after the data arrives", async ({ page }) => {
    const release = await holdData(page);
    await page.goto("/search/");
    await expect(page.locator("[data-cs-loading]")).toBeVisible();
    const before = await page.locator("[data-cs-sub]").textContent();
    expect(before).toBe("5,049 conditions of approval from 352 San Francisco Planning Commission motions on food, drink and entertainment premises.");
    release();
    await page.locator(READY).waitFor();
    expect(await page.locator("[data-cs-sub]").textContent()).toBe(before);
  });
});

test.describe("the handle, used roughly", () => {
  test("mounting twice on one element replaces the first search", async ({ page }) => {
    await open(page, "/search/");
    const seen = await page.evaluate(async () => {
      type Handle = { ready: Promise<void>; destroy(): void };
      const w = window as unknown as { showcase: { search: Handle; mountSearch(root: HTMLElement, o?: object): Handle } };
      const root = document.querySelector<HTMLElement>("#search");
      if (!root) throw new Error("no search root");
      const second = w.showcase.mountSearch(root, { headingLevel: 1 });
      await second.ready;
      let events = 0;
      document.addEventListener("cs:results", () => { events += 1; });
      location.hash = "#q=odor";
      await new Promise(done => setTimeout(done, 300));
      return { events, fields: document.querySelectorAll('[data-cs-field="q"]').length };
    });
    expect(seen).toEqual({ events: 1, fields: 1 });
    // "/" reaches the field that is on the page
    await page.locator("[data-cs-pdf]").first().focus();
    await page.keyboard.press("/");
    await expect(field(page)).toBeFocused();
  });

  test("destroy() during the download cancels it, and a later mount starts again", async ({ page }) => {
    const failed: string[] = [];
    page.on("requestfailed", request => failed.push(request.url()));
    let calls = 0;
    let release: () => void = () => {};
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route(DATA, async route => {
      if (++calls === 1) await gate;
      await route.continue().catch(() => {});
    });
    await page.goto("/search/");
    await expect(page.locator("[data-cs-loading]")).toBeVisible();
    await page.evaluate(() => (window as unknown as { showcase: { search: { destroy(): void } } }).showcase.search.destroy());
    await expect.poll(() => failed.filter(url => url.endsWith("/data/conditions.json")).length).toBe(1);
    release();
    await page.evaluate(() => {
      const w = window as unknown as { showcase: { mountSearch(root: HTMLElement, o?: object): unknown } };
      w.showcase.mountSearch(document.querySelector("#search") as HTMLElement, { headingLevel: 1 });
    });
    await page.locator(READY).waitFor();
    await expect(cards(page)).toHaveCount(50);
    expect(calls).toBe(2);
  });
});

test.describe("for a screen reader", () => {
  test("the count is announced once typing stops, not on every key", async ({ page }) => {
    await open(page);
    const live = page.locator("[data-cs-live]");
    await expect(live).toHaveAttribute("role", "status");
    await expect(live).toHaveAttribute("aria-live", "polite");
    await page.evaluate(() => {
      const w = window as unknown as { said: string[] };
      w.said = [];
      const node = document.querySelector("[data-cs-live]") as Element;
      new MutationObserver(() => w.said.push(node.textContent ?? "")).observe(node, { childList: true, characterData: true, subtree: true });
    });
    await field(page).focus();
    await page.keyboard.type("odor", { delay: 60 });
    // the visible count keeps up with the keys
    await expect(page.locator("[data-cs-count-text]")).toHaveText(/^324 conditions from \d+ of 352 motions$/);
    await expect(live).toHaveText(/^324 conditions from \d+ of 352 motions/);
    const said = await page.evaluate(() => (window as unknown as { said: string[] }).said.filter(Boolean));
    expect(said.length).toBe(1);

    // nothing found: the reason is announced with the count
    await field(page).fill("xylophone");
    await expect(live).toHaveText(/^0 conditions from 0 of 352 motions\. No condition on these motions uses “xylophone”\./);
  });

  test("a card's facts are a list of name and value pairs, one level deep", async ({ page }) => {
    await open(page, "/search/", hash({ q: "outdoor seating" }));
    const shape = await page.locator("[data-cs-card] dl").first().evaluate(dl => ({
      children: [...dl.children].map(el => el.tagName),
      groups: [...dl.children].map(el => [...el.children].map(x => x.tagName).join("+")),
    }));
    expect(new Set(shape.children)).toEqual(new Set(["DIV"]));
    expect(new Set(shape.groups)).toEqual(new Set(["DT+DD"]));
    expect(shape.children.length).toBeGreaterThanOrEqual(4);
  });
});

test.describe("the address bar and the wordmark, as WebKit sees them", () => {
  // WebKit refuses more than 100 history.replaceState calls in 10 seconds and throws; a fast typist got there.
  test("typing writes the hash once it pauses, not on every key", async ({ page }) => {
    await open(page);
    await page.evaluate(() => {
      const w = window as unknown as { writes: number };
      w.writes = 0;
      const original = history.replaceState.bind(history);
      history.replaceState = (...args: Parameters<History["replaceState"]>) => {
        w.writes += 1;
        original(...args);
      };
    });
    await field(page).focus();
    await page.keyboard.type("amplified music after ten at night", { delay: 25 });
    await expect(page).toHaveURL(/#q=amplified\+music\+after\+ten\+at\+night$/);
    expect(await page.evaluate(() => (window as unknown as { writes: number }).writes)).toBeLessThanOrEqual(3);
    // a choice from a menu is written at once
    await page.locator('[data-cs-field="kind"]').selectOption("all");
    expect(new URL(page.url()).hash).toBe("#q=amplified+music+after+ten+at+night&kind=all");
  });

  test("a refused write to the address never stops a search", async ({ page }) => {
    const problems = watch(page);
    await open(page);
    await page.evaluate(() => {
      history.replaceState = () => {
        throw new DOMException("Attempt to use history.replaceState() more than 100 times per 10 seconds", "SecurityError");
      };
    });
    await field(page).focus();
    await page.keyboard.type("odor");
    await expect(count(page)).toContainText(/^324 conditions from \d+ of 352 motions/);
    await page.locator('[data-cs-field="kind"]').selectOption("all");
    await expect(count(page)).not.toContainText("hidden");
    await page.waitForTimeout(250);
    expect(problems).toEqual([]);
  });

  // WebKit logs 'Invalid value for <text> attribute textLength=""' when the attribute is taken off the words.
  test("the wordmark is measured without taking its textLength away", async ({ page }) => {
    await page.addInitScript(() => {
      const w = window as unknown as { removed: string[] };
      w.removed = [];
      const original = Element.prototype.removeAttribute;
      Element.prototype.removeAttribute = function (this: Element, name: string) {
        if (name === "textLength") w.removed.push(this.tagName);
        original.call(this, name);
      };
    });
    for (const path of ["/", "/search/"]) {
      await page.goto(path);
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(200);
      expect(await page.evaluate(() => (window as unknown as { removed: string[] }).removed)).toEqual([]);
      const mark = await page.locator(".mark").evaluate(svg => {
        const words = svg.querySelector("text");
        return { texts: svg.querySelectorAll("text").length, length: Number(words?.getAttribute("textLength")), width: svg.getBoundingClientRect().width };
      });
      expect(mark.texts).toBe(1); // the copy it was measured on is gone
      expect(mark.length).toBeGreaterThan(50);
      expect(mark.width).toBeGreaterThan(mark.length);
    }
  });
});
