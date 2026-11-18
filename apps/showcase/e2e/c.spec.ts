// The front page, the living grid: nobody gets stuck at the gate (skip link, keyboard, returning visitor, a link
// that carries a search, reduced motion, no WebGL, a phone), the stamp hands over to the story, the story reads
// from the fact sheet and ends in the search, the map and the search answer each other, and the theme flips.
// A returning visitor and a link that carries a search open on the search alone, the story put away.
// Runs against the built app. Plain headless Chromium draws WebGL in software, where the page uses its drawn
// map (SVG) instead of the 3D scene: most tests here run on that. The last group forces the scene (?webgl=1).

import { expect, test, type Page } from "@playwright/test";
import { feedbackMails, pagelessPdfLinks } from "./helpers/links";

const RECORD = "2016-001273CUA";
const READY = '.cs[data-cs-state="ready"]';
const VISIT = "showcase:visited:c-gate";
const gate = (page: Page) => page.locator(".c-gate");
const field = (page: Page) => page.locator('[data-cs-field="q"]');
const count = (page: Page) => page.locator("[data-cs-count-text]");
const button = (page: Page) => page.locator(".c-gate__button");
const mark = (page: Page) => page.locator(".c-stack > .stamp-mark:not(.is-ghost)");
const seal = (page: Page) => page.locator(".c-seal");
const chapter = (page: Page, i: number) => page.locator(`.c-chapter[data-chapter="${i}"]`);

type Showcase = {
  gate?: { state: string };
  scene?: { motions: { record: string }[]; topOf(i: number, out: { x: number; y: number; behind: boolean }): { x: number; y: number }; pose: { distance: number } };
  flat?: { topOf(record: string, out: { x: number; y: number }): boolean };
  story: { goTo(i: number, o?: { instant?: boolean }): void; timeline: { stops: { chapter: number; step: number }[] }; goToStop(s: unknown, o?: { instant?: boolean }): void; state: { chapter: number; ended: boolean } };
};
/** Open /c/ as a first-time visitor and wait until the gate is live (its chunk loaded) and the data is in. */
async function openGate(page: Page, url = "/c/"): Promise<void> {
  await page.goto(url);
  await page.locator(READY).waitFor();
  await page.waitForFunction(() => Boolean((window as unknown as { showcase?: Showcase }).showcase?.gate));
}

/** Open /c/ with the story in the page: the gate (?gate=1), then the skip link, which ends at the search with the
 *  story above it (a returning visit would put the story away). */
async function openInStory(page: Page): Promise<void> {
  await page.goto("/c/?gate=1");
  await page.locator(READY).waitFor();
  await page.locator(".shell-skip").click();
  await expect(gate(page)).toHaveCount(0);
  await expect(page.locator("html")).toHaveAttribute("data-c-mode", "search");
  // (the skip link put the cursor in the search field: a test that types "/" or arrows means the page's keys)
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
}

/** Open /c/ as someone who has been through the gate: straight at the search, the story put away. */
async function openReturning(page: Page, url = "/c/"): Promise<void> {
  await page.addInitScript(key => localStorage.setItem(key, "x"), VISIT);
  await page.goto(url);
  await page.locator(READY).waitFor();
}

async function goToChapter(page: Page, i: number): Promise<void> {
  await page.evaluate(k => (window as unknown as { showcase: Showcase }).showcase.story.goTo(k, { instant: true }), i);
  await expect(chapter(page, i)).toBeVisible();
}

/** What the gate hands over to: the story's first chapter, the page free to scroll, the seal by the wordmark. */
async function expectStory(page: Page, { narrow = false } = {}): Promise<void> {
  await expect(gate(page)).toHaveCount(0, { timeout: 20_000 });
  await expect(chapter(page, 0)).toBeVisible();
  await expect(chapter(page, 0)).toContainText("One address, twenty-two conditions.");
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).overflowY)).not.toBe("hidden");
  // (a phone has no room for the seal beside "Skip to search": it shows it once the search is open)
  if (!narrow) await expect(seal(page)).toBeVisible();
  await expect(page.locator(".stamp-pieces")).toHaveCount(0);
  expect(await page.evaluate(key => localStorage.getItem(key) !== null, VISIT)).toBe(true);
}

test.describe("the first frame", () => {
  test("the motion sheet lies on the grid, set from the public record, with the button and the skip link", async ({ page }) => {
    await page.goto("/c/");
    await expect(gate(page)).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "blueprint");
    const sheet = page.getByRole("article", { name: /Planning Commission Motion No\. 19958.*not a scan/ });
    await expect(sheet).toBeVisible();
    // (set as on the page, not as a heading: the page's own h1 comes first)
    await expect(sheet.getByText("Planning Commission Motion No. 19958")).toBeVisible();
    await expect(sheet).toContainText("HEARING DATE: JULY 6, 2017");
    await expect(sheet).toContainText(RECORD);
    await expect(sheet).toContainText("302 Greenwich Street / 1531 Montgomery Street");
    await expect(sheet).toContainText("City Landmark No. 121");
    // no sponsor line, no staff contact, nothing that names a private person
    await expect(sheet).not.toContainText(/sponsor|staff contact|@|\(415\)/i);
    await expect(button(page)).toHaveText(/Press and hold to stamp/i);
    await expect(page.locator(".shell-skip")).toBeVisible();
    // the sheet is laid on the ground plane before any 3D has loaded: a perspective transform, inside the window
    const plane = page.locator(".c-plane");
    expect(await plane.evaluate(el => getComputedStyle(el).transform)).toMatch(/^matrix3d\(/);
    const box = await page.locator(".c-motion").boundingBox();
    expect(box && box.x >= 0 && box.y >= 60 && box.x + box.width <= 1280 && box.y + box.height <= 720).toBe(true);
    // the page does not scroll under the gate, and the search is in the page from the start
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).overflowY)).toBe("hidden");
    await page.locator(READY).waitFor();
  });

  test("the tab order is: skip link, wordmark, pause, theme, the stamp button; nothing behind the gate is reached", async ({ page }) => {
    await openGate(page);
    const stops: string[] = [];
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press("Tab");
      stops.push(await page.evaluate(() => document.activeElement?.className ?? ""));
    }
    expect(stops).toEqual(["shell-skip", "mark-link", "c-pause", "theme-flip", "c-gate__button"]);
    await expect(seal(page)).toBeHidden();
    expect(await page.locator(".c-story").evaluate(el => (el as HTMLElement).inert)).toBe(true);
    // Tab past the stamp does not land in the search (it would take the gate down unasked): the skip link is the way
    expect(await page.locator(".c-search").evaluate(el => (el as HTMLElement).inert)).toBe(true);
    await page.keyboard.press("Tab");
    await expect(gate(page)).toBeVisible();
    expect(await page.evaluate(() => Boolean(document.activeElement?.closest(".c-search")))).toBe(false);
  });
});

test.describe("nobody gets stuck", () => {
  test("the skip link ends the gate, goes to the search, focuses the field and is remembered", async ({ page }) => {
    await openGate(page);
    await page.locator(".shell-skip").click();
    await expect(gate(page)).toHaveCount(0);
    await expect(field(page)).toBeFocused();
    await expect(field(page)).toHaveValue("");
    await expect(field(page)).toBeInViewport();
    expect(new URL(page.url()).hash).toBe("");
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).overflowY)).not.toBe("hidden");
    await expect(seal(page)).toBeVisible();
    // a returning visitor goes straight to the search
    await page.reload();
    await page.locator(READY).waitFor();
    await expect(gate(page)).toHaveCount(0);
    await expect(seal(page)).toBeVisible();
    await expect(field(page)).toBeInViewport();
    await expect(page.locator("[data-cs-card]").first()).toBeVisible();
  });

  test("the skip link works before the gate's own script has arrived", async ({ page }) => {
    await page.route(/gate-[\w-]+\.js$/, async route => {
      await new Promise(done => setTimeout(done, 1500));
      await route.continue();
    });
    await page.goto("/c/");
    await page.locator(".shell-skip").click();
    await expect(gate(page)).toHaveCount(0);
    await expect(field(page)).toBeFocused();
    await page.waitForTimeout(1800);
    await expect(gate(page)).toHaveCount(0);
  });

  test("no single-key shortcut: \"/\" leaves the gate where it is (WCAG 2.1.4); the skip link is the way", async ({ page }) => {
    await openGate(page);
    await page.keyboard.press("/");
    await page.waitForTimeout(300);
    await expect(gate(page)).toBeVisible();
    await expect(page.locator(".cs-key")).toHaveCount(0);
    await expect(page.locator(".cs-hint__keys")).not.toContainText("/");
    await page.locator(".shell-skip").focus();
    await page.keyboard.press("Enter");
    await expect(gate(page)).toHaveCount(0);
    await expect(field(page)).toBeFocused();
  });

  test("a link that carries a search goes straight to it, gate or no gate", async ({ page }) => {
    await page.goto("/c/#q=outdoor+seating");
    await page.locator(READY).waitFor();
    await expect(gate(page)).toHaveCount(0);
    await expect(field(page)).toHaveValue("outdoor seating");
    await expect(count(page)).toContainText("of 352 motions");
    await expect(page.locator("[data-cs-card]").first()).toBeInViewport();
    // and a link to one card lands on that card, clear of the header
    await page.goto("about:blank");
    await page.goto("/c/#q=2015-009955CUA&kind=all&card=7A");
    await page.locator(READY).waitFor();
    const target = page.locator("[data-cs-card].is-target");
    await expect(target).toBeInViewport();
    const top = (await target.boundingBox())?.y ?? 0;
    expect(top).toBeGreaterThanOrEqual(64);
  });

  test("a search that arrives in the address while the gate is up opens it; so does the skip link's own address", async ({ page }) => {
    await openGate(page);
    await page.evaluate(() => (location.hash = "#q=noise"));
    await expect(gate(page)).toHaveCount(0);
    await expect(page.locator("html")).toHaveAttribute("data-c-mode", "search");
    await expect(field(page)).toHaveValue("noise");
    await page.goto("about:blank");
    await page.addInitScript(() => localStorage.clear());
    await page.goto("/c/#search");
    await page.locator(READY).waitFor();
    await expect(gate(page)).toHaveCount(0);
    await expect(page.locator("html")).toHaveAttribute("data-c-mode", "search");
  });

  test("the seal brings the gate up at the top of the page, even straight after a scroll; Escape puts it away", async ({ page }) => {
    await openInStory(page);
    await goToChapter(page, 3);
    await page.mouse.move(700, 500);
    await page.mouse.wheel(0, 1200);
    await page.waitForTimeout(120);
    await seal(page).click();
    await expect(gate(page)).toBeVisible();
    await page.waitForTimeout(900);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    await page.keyboard.press("Escape");
    await expect(gate(page)).toHaveCount(0);
    // (the page is put back where it was once the gate has gone: a slow machine takes a few frames)
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(1000);
  });

  test("a returning visitor gets the search alone, with one line and the seal to bring the story back", async ({ page }) => {
    await openReturning(page);
    await expect(page.locator("html")).toHaveClass(/c-direct/);
    await expect(page.locator("html")).toHaveAttribute("data-c-mode", "search");
    // no long page with the story scrolled past above: the story is not in the page, the search starts at the top
    await expect(page.locator(".c-story")).toBeHidden();
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    await expect(field(page)).toBeInViewport();
    const replay = page.getByRole("button", { name: "See the story of one motion, from the stamp" });
    await expect(replay).toBeVisible();
    await expect(seal(page)).toBeVisible();
    // the line brings the gate (and the story) back; Escape puts it away again, the search as it was
    await field(page).fill("noise");
    await replay.click();
    await expect(gate(page)).toBeVisible();
    await expect(page.locator("html")).not.toHaveClass(/c-direct/);
    await page.keyboard.press("Escape");
    await expect(gate(page)).toHaveCount(0);
    await expect(page.locator("html")).toHaveClass(/c-direct/);
    await expect(page.locator(".c-story")).toBeHidden();
    await expect(field(page)).toHaveValue("noise");
    // stamping from the replay tells the story from its start
    await replay.click();
    await button(page).focus();
    await page.keyboard.press("Enter");
    await expectStory(page);
    await expect(page.locator("html")).not.toHaveClass(/c-direct/);
  });

  test("a link that carries a search opens on the search alone; the skip link stays there", async ({ page }) => {
    await page.goto("/c/#q=security+guard");
    await page.locator(READY).waitFor();
    await expect(page.locator("html")).toHaveClass(/c-direct/);
    await expect(page.locator(".c-story")).toBeHidden();
    await expect(page.locator("[data-cs-card]").first()).toBeInViewport();
    await page.mouse.wheel(0, 1500);
    await page.waitForTimeout(300);
    await page.locator(".shell-skip").focus();
    await page.keyboard.press("Enter");
    await expect(field(page)).toBeFocused();
    await expect(field(page)).toBeInViewport();
    await expect(page.locator("html")).toHaveAttribute("data-c-mode", "search");
  });

  test("the skip link from inside the story goes the whole way to the search", async ({ page }) => {
    await openInStory(page);
    await goToChapter(page, 3);
    await page.locator(".shell-skip").click();
    await expect(field(page)).toBeFocused();
    await expect(page.locator("html")).toHaveAttribute("data-c-mode", "search");
  });

  test("?gate=1 shows the gate to a returning visitor, and the seal replays it", async ({ page }) => {
    await openReturning(page, "/c/?gate=1");
    await expect(gate(page)).toBeVisible();
    await page.locator(".shell-skip").click();
    await expect(gate(page)).toHaveCount(0);
    await seal(page).click();
    await expect(gate(page)).toBeVisible();
    await expect(button(page)).toBeFocused();
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  });
});

test.describe("the stamp", () => {
  test("one press of Enter on the button stamps at once, and the story begins", async ({ page }) => {
    await openGate(page);
    await button(page).focus();
    await page.keyboard.press("Enter");
    await expect(mark(page)).toHaveCount(1, { timeout: 10_000 });
    await expect(page.locator(".c-status")).toContainText(/approved with conditions/i);
    await expectStory(page);
    // the note by the point says what the visitor did
    await expect(page.locator(".c-chapter[data-chapter='0'] .c-cue")).toBeVisible();
    // the keyboard's place is the first chapter's heading (the button it was on has gone); the stamp was said once,
    // and the heading itself says how to go on (no second message over the focus move)
    await expect(chapter(page, 0).locator("h2")).toBeFocused();
    await expect(page.locator(".c-status")).toHaveText("Stamped: approved with conditions.");
    await expect(chapter(page, 0).locator("h2")).toHaveAccessibleDescription(/Scroll for the story.*skip to the search/);
  });

  test("holding Space charges it; letting go early heals, and the pencil says so", async ({ page }) => {
    await openGate(page);
    await button(page).focus();
    await page.keyboard.down("Space");
    await page.waitForTimeout(600);
    await expect(gate(page)).toHaveAttribute("data-gate", "charging");
    await page.keyboard.up("Space");
    await expect(gate(page)).toHaveAttribute("data-gate", "idle");
    await expect(page.locator(".c-gate__note")).toHaveText("Hold it down.");
    await expect(mark(page)).toHaveCount(0);
    // and a full hold lands
    await page.keyboard.down("Space");
    await expect(mark(page)).toHaveCount(1, { timeout: 10_000 });
    await page.keyboard.up("Space");
    await expectStory(page);
  });

  test("a pointer held on the sheet stamps where it points", async ({ page }) => {
    await openGate(page);
    const sheet = await page.locator(".c-motion").boundingBox();
    if (!sheet) throw new Error("no sheet");
    const x = sheet.x + sheet.width * 0.42, y = sheet.y + sheet.height * 0.5;
    await page.mouse.move(x, y, { steps: 6 });
    await page.mouse.down();
    await expect(mark(page)).toHaveCount(1, { timeout: 10_000 });
    await page.mouse.up();
    const m = await mark(page).boundingBox();
    expect(m && Math.abs(m.x + m.width / 2 - x) < 60 && Math.abs(m.y + m.height / 2 - y) < 60).toBe(true);
    await expectStory(page);
  });
});

test.describe("the story", () => {
  test("nine chapters from the fact sheet, by the rail and the arrow keys", async ({ page }) => {
    await openInStory(page);
    await goToChapter(page, 0);
    const rail = page.getByRole("navigation", { name: "Chapters of the story" });
    await expect(rail.getByRole("button")).toHaveCount(9);
    await page.keyboard.press("ArrowDown");
    await expect(chapter(page, 1)).toBeVisible({ timeout: 10_000 });
    await expect(chapter(page, 1)).toContainText("302 Greenwich Street");
    await expect(chapter(page, 1)).toContainText("City Landmark No. 121");
    await goToChapter(page, 2);
    await expect(chapter(page, 2)).toContainText("23 February 2017");
    await expect(chapter(page, 2)).toContainText("23 letters in support and 11 in opposition");
    await goToChapter(page, 3);
    await expect(chapter(page, 3)).toContainText("6 July 2017");
    const vote = chapter(page, 3).locator(".c-vote");
    await expect(vote.locator("dt")).toHaveText(["Ayes", "Nays", "Absent"]);
    await expect(vote.locator("dd").first()).toContainText("Hillis, Richards, Fong, Melgar, Moore, Koppel, Johnson");
    await goToChapter(page, 4);
    await expect(chapter(page, 4)).toContainText("Motion No. 19958");
    await expect(chapter(page, 4)).toContainText("Approved, with 22 conditions.");
    // the two dates are told apart, and the appeal appears only as the record states it
    await expect(chapter(page, 4)).toContainText("An appeal was filed and denied");
    await expect(chapter(page, 4)).toContainText("19 July 2017: the day the planning record closed, not the day of the vote");
    await goToChapter(page, 7);
    await expect(chapter(page, 7)).toContainText("There are 5,048 more.");
    // the sum a reader can check: one condition read, 5,048 more, 5,049 in all
    await expect(chapter(page, 7)).toContainText("More than the one you just read: 5,049 conditions in all, from 352 motions.");
    // the whole page never says what it must not
    const text = await page.locator(".c-story").innerText();
    expect(text).not.toMatch(/unpermitted|encroach|reopen|full condition/i);
  });

  test("the conditions step one at a time, each with its page link, and no link goes to page 1", async ({ page }) => {
    await openInStory(page);
    const stops = await page.evaluate(() => (window as unknown as { showcase: Showcase }).showcase.story.timeline.stops.map(s => s.chapter));
    const first = stops.indexOf(5);
    expect(stops.filter(c => c === 5)).toHaveLength(8);
    for (const k of [0, 7]) {
      await page.evaluate(i => {
        const s = (window as unknown as { showcase: Showcase }).showcase.story;
        s.goToStop(s.timeline.stops[i], { instant: true });
      }, first + k);
      const current = page.locator(".c-step.is-current");
      await expect(current).toHaveCount(1);
      await expect(current.locator("a")).toHaveAttribute("href", /\/motions\/2016-001273CUA\.pdf#page=1[2-5]$/);
    }
    await expect(page.locator(".c-step.is-current")).toContainText("Delivery Hours");
    const links = await page.locator(".c-story a[href*='.pdf']").evaluateAll(as => as.map(a => (a as HTMLAnchorElement).href));
    expect(links.length).toBeGreaterThanOrEqual(10);
    for (const href of links) expect(href).toMatch(/#page=1[2-5]$/);
    // the page chapter shows page 15 as type, says they are excerpts, and links the scan
    await goToChapter(page, 6);
    const facsimile = page.locator(".c-page");
    await expect(facsimile).toBeVisible();
    await expect(facsimile).toContainText("page 15 of 16");
    await expect(facsimile.locator(".c-page__item")).toHaveCount(6);
    await expect(facsimile.getByRole("link", { name: /Excerpts\. Read page 15/ })).toHaveAttribute("href", /#page=15$/);
  });

  test("it ends in the search: scrolling past the last chapter opens it, and the skip link gets there from anywhere", async ({ page }) => {
    await openInStory(page);
    await goToChapter(page, 3);
    await expect(page.locator("html")).toHaveAttribute("data-c-mode", "story");
    await page.locator(".shell-skip").click();
    await expect(page.locator("html")).toHaveAttribute("data-c-mode", "search");
    await expect(field(page)).toBeFocused();
    await expect(field(page)).toBeInViewport();
  });
});

test.describe("the search in the world", () => {
  test("the panel leaves the map beside it, and a search is counted on the map", async ({ page }) => {
    await openReturning(page);
    const panel = await page.locator(".c-search__panel").boundingBox();
    expect(panel && panel.width >= 720 && panel.width <= 1280 * 0.72).toBe(true);
    const caption = page.locator(".c-caption");
    await expect(caption).toHaveText(/352 motions · taller means more conditions/i);
    await field(page).fill("outdoor seating");
    await expect(caption).toHaveText(/^\d+ of 352 motions match$/i);
    await expect(count(page)).toContainText("of 352 motions");
    // typing is never held up by the map: the count follows each key
    await field(page).fill("");
    await field(page).pressSequentially("noise", { delay: 30 });
    await expect(caption).toHaveText(/of 352 motions match/i);
  });

  test("a card under the pointer is tied to its motion; a stack clicked on the map sets the search", async ({ page }) => {
    await openReturning(page, "/c/#q=noise");
    await page.waitForFunction(() => Boolean((window as unknown as { showcase?: Showcase }).showcase?.flat));
    const card = page.locator("[data-cs-card]").first();
    await card.hover({ position: { x: 200, y: 30 } });
    await expect(page.locator(".c-wire")).toHaveClass(/is-on/, { timeout: 10_000 });
    await page.mouse.move(1200, 600);
    await expect(page.locator(".c-wire")).not.toHaveClass(/is-on/);
    // click the stack of another motion
    const at = await page.evaluate(() => {
      const o = { x: 0, y: 0 };
      (window as unknown as { showcase: Showcase }).showcase.flat!.topOf("2015-009955CUA", o);
      return o;
    });
    await page.mouse.click(at.x, at.y);
    await expect(field(page)).toHaveValue("2015-009955CUA");
    await expect(count(page)).toContainText("from 1 of 352 motions");
  });
});

test.describe("the flip", () => {
  test("the mark and the T key flip the theme, and the choice is remembered", async ({ page }) => {
    await openReturning(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "blueprint");
    await page.locator(".theme-flip").click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "paper");
    await expect(page.locator("html")).not.toHaveClass(/c-flip/, { timeout: 10_000 });
    expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe("rgb(242, 237, 225)");
    expect(await page.evaluate(() => localStorage.getItem("showcase:theme"))).toBe("paper");
    await page.locator(".mark-link").focus();
    await page.keyboard.press("t");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "blueprint");
    // typing a t in the search field is typing
    await expect(page.locator("html")).not.toHaveClass(/c-flip/, { timeout: 10_000 });
    await field(page).fill("");
    await field(page).pressSequentially("t");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "blueprint");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "blueprint");
  });
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("one press stamps, a short fade, the story as stills, and nothing drifts", async ({ page }) => {
    await openGate(page);
    await expect(button(page)).toHaveText("Stamp it");
    await button(page).click();
    await expect(mark(page)).toHaveCount(1);
    await expectStory(page);
    // stills: a key press cuts to the next chapter
    await page.keyboard.press("ArrowDown");
    await expect(chapter(page, 1)).toBeVisible();
    // the flip is a cut
    await page.locator(".theme-flip").click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "paper");
    await expect(page.locator("html")).not.toHaveClass(/c-flip/);
  });

  test("with the 3D scene, the camera does not move by itself", async ({ page }) => {
    test.slow();
    await openReturning(page, "/c/?webgl=1");
    await page.waitForFunction(() => Boolean((window as unknown as { showcase?: Showcase }).showcase?.scene), null, { timeout: 60_000 });
    const read = () => page.evaluate(() => JSON.stringify((window as unknown as { showcase: Showcase }).showcase.scene!.pose));
    await page.mouse.move(900, 300, { steps: 4 });
    await page.waitForTimeout(600);
    const a = await read();
    await page.mouse.move(1100, 500, { steps: 4 });
    await page.waitForTimeout(900);
    expect(await read()).toBe(a);
  });
});

test.describe("with the 3D scene forced (drawn in software here)", () => {
  test("the scene arrives over the first paint, and a stack clicked on the map sets the search", async ({ page }) => {
    test.slow();
    await openReturning(page, "/c/?webgl=1#q=noise");
    await page.waitForFunction(() => Boolean((window as unknown as { showcase?: Showcase }).showcase?.scene), null, { timeout: 60_000 });
    await expect(page.locator("canvas.c-world")).toHaveClass(/is-on/);
    await expect(page.locator("svg.c-flat")).toHaveCount(0);
    await page.waitForTimeout(2500);
    const at = await page.evaluate(() => {
      const s = (window as unknown as { showcase: Showcase }).showcase.scene!;
      const i = s.motions.findIndex(m => m.record === "2015-009955CUA");
      const o = s.topOf(i, { x: 0, y: 0, behind: false });
      return { x: o.x, y: o.y };
    });
    await page.mouse.click(at.x, at.y + 2);
    await expect(field(page)).toHaveValue("2015-009955CUA", { timeout: 30_000 });
    await expect(page.locator(".c-caption")).toHaveText(/^1 of 352 motions match$/i);
  });

  test("the label under the pointer names the very motion a click there searches", async ({ page }) => {
    test.slow();
    await openReturning(page, "/c/?webgl=1");
    await page.waitForFunction(() => Boolean((window as unknown as { showcase?: Showcase }).showcase?.scene), null, { timeout: 60_000 });
    await page.waitForTimeout(3000);
    // stacks spread over the map, aimed a little below their tops (on the stack, not its dot)
    const aims = await page.evaluate(() => {
      const s = (window as unknown as { showcase: Showcase }).showcase.scene!;
      const out: { x: number; y: number }[] = [];
      for (let i = 0; i < s.motions.length && out.length < 4; i += 37) {
        const o = s.topOf(i, { x: 0, y: 0, behind: false });
        if (o.x > innerWidth * 0.7 && o.x < innerWidth - 40 && o.y > 140 && o.y < innerHeight - 90) out.push({ x: o.x, y: o.y + 6 });
      }
      return out;
    });
    expect(aims.length).toBeGreaterThan(2);
    for (const at of aims) {
      await page.mouse.move(at.x, at.y, { steps: 3 });
      const tag = page.locator(".c-tag:not(.c-tag--mark):not(.c-tag--wire)");
      await expect(tag).toHaveClass(/is-on/, { timeout: 15_000 });
      // (the view leans toward the pointer for a moment, and in software it takes its time: read the label once it
      // has stopped changing, as a visitor would before clicking)
      let named = "";
      await page.waitForTimeout(5000);
      for (let k = 0, last = "x"; k < 12; k++) {
        await page.waitForTimeout(1500);
        named = ((await tag.textContent()) ?? "").split(" · ")[0]!.trim();
        if (named === last) break;
        last = named;
      }
      await page.mouse.click(at.x, at.y);
      await expect(field(page)).toHaveValue(named, { timeout: 30_000 });
      // back to no search before the next (the stacks stand again)
      await page.evaluate(() => (location.hash = ""));
      await field(page).fill("");
      await page.mouse.move(10, 300);
      await page.waitForTimeout(1500);
    }
  });

  test("the gate's sheet stays where the first paint put it when the scene takes over", async ({ page }) => {
    test.slow();
    await page.goto("/c/?webgl=1");
    const plane = page.locator(".c-plane");
    const before = await page.locator(".c-motion").boundingBox();
    await page.waitForFunction(() => Boolean((window as unknown as { showcase?: Showcase }).showcase?.scene), null, { timeout: 60_000 });
    await expect(plane).toBeVisible();
    await page.waitForTimeout(400);
    const after = await page.locator(".c-motion").boundingBox();
    // the same place to within the slow drift of the first moments
    expect(before && after && Math.abs(before.x - after.x) < 12 && Math.abs(before.y - after.y) < 12 && Math.abs(before.width - after.width) < 16).toBe(true);
  });
});

test.describe("without WebGL", () => {
  test("the drawn map stands behind the same gate, story and search", async ({ page }) => {
    await openGate(page, "/c/?nowebgl=1");
    await expect(page.locator("svg.c-flat")).toBeVisible();
    await expect(page.locator("canvas.c-world")).toHaveCount(0);
    expect(await page.locator("svg.c-flat .c-flat__dots circle").count()).toBe(350);
    await button(page).focus();
    await page.keyboard.press("Enter");
    await expectStory(page);
    await expect(page.locator("svg.c-flat circle.is-hero")).toHaveCount(1);
    await page.locator(".shell-skip").click();
    await field(page).fill("outdoor seating");
    await expect(page.locator(".c-caption")).toHaveText(/of 352 motions match/i);
    expect(await page.locator("svg.c-flat circle.is-lit").count()).toBeGreaterThan(0);
  });
});

test.describe("short windows", () => {
  for (const size of [
    { width: 375, height: 667 },
    { width: 844, height: 390 },
    { width: 720, height: 450 },
  ]) {
    test(`every chapter can be read to its end at ${size.width} by ${size.height}`, async ({ page }) => {
      await page.setViewportSize(size);
      await openInStory(page);
      for (let i = 0; i < 8; i++) {
        await goToChapter(page, i);
        const cut = await chapter(page, i).evaluate(article => {
          const el = article as HTMLElement;
          el.scrollTop = el.scrollHeight;
          const box = el.getBoundingClientRect();
          // (the last part that is laid out: in the plain layout of a short window the scroll cue is not shown)
          const shown = [...el.children].filter(child => child.getClientRects().length > 0);
          const last = shown[shown.length - 1]!.getBoundingClientRect();
          return Math.round(last.bottom - box.bottom);
        });
        expect(cut, `chapter ${i + 1}`).toBeLessThanOrEqual(1);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    });
  }
});

test.describe("a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("the gate fits, a tap stamps, the story sits under the map, and the search keeps a band of it", async ({ page }) => {
    await openGate(page);
    const overflow = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
      wide: [...document.querySelectorAll<HTMLElement>("body *")]
        .filter(el => el.getBoundingClientRect().right > document.documentElement.clientWidth + 0.5 && !el.closest(".cs-table__scroll, .cov-scroll, .vh, .cs-list--one-case .cs-meta"))
        .slice(0, 5)
        .map(el => el.className || el.tagName),
    }));
    expect(overflow.wide).toEqual([]);
    expect(overflow.scroll).toBeLessThanOrEqual(overflow.client);
    const b = await button(page).boundingBox();
    expect(b && b.height >= 44).toBe(true);
    const skip = await page.locator(".shell-skip").boundingBox();
    expect(skip && skip.height >= 24).toBe(true);
    await button(page).tap();
    await expect(mark(page)).toHaveCount(1, { timeout: 10_000 });
    await expectStory(page, { narrow: true });
    // the text is a band under the map
    const panel = await page.locator(".c-panel").boundingBox();
    expect(panel && panel.y > 300 && Math.round(panel.width) === 390).toBe(true);
    // the previous / next pair is the rail here, 44 px each (one stop at a time: "Next", not "Next chapter")
    const next = page.getByRole("button", { name: "Next", exact: true });
    await expect(next).toBeVisible();
    expect((await next.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    await next.tap();
    await expect(chapter(page, 1)).toBeVisible({ timeout: 10_000 });
    // the search: the map is a band at the top, the list is under it
    await page.locator(".shell-skip").tap();
    await expect(page.locator(".c-flat, .c-world")).toHaveClass(/is-band/);
    await expect(seal(page)).toBeVisible();
    await expect(page.locator("[data-cs-card]").first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  });
});

test.describe("a phone, coming back", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("the search is the first thing on the screen, with no map loaded over it", async ({ page }) => {
    const asked: string[] = [];
    page.on("request", request => asked.push(new URL(request.url()).pathname));
    await openReturning(page);
    await expect(page.locator("html")).toHaveClass(/c-mapless/);
    const box = await field(page).boundingBox();
    expect(box && box.y < 400).toBe(true);
    await expect(page.locator("[data-cs-card]").first()).toBeInViewport();
    await page.waitForTimeout(1500);
    expect(asked.filter(p => /sf-streets|motions\.json|three|scene/.test(p))).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    // the seal brings the story, and its map, back
    await seal(page).tap();
    await expect(gate(page)).toBeVisible();
    await expect(page.locator("html")).not.toHaveClass(/c-mapless/);
  });
});

test.describe("clean console", () => {
  test("the whole way through: gate, stamp, story, search, flip", async ({ page, baseURL }) => {
    const problems: string[] = [];
    page.on("console", message => {
      // headless Chromium draws WebGL in software and says so ("GL Driver Message … GPU stall due to ReadPixels")
      if (/GL Driver Message/.test(message.text())) return;
      if (message.type() === "error" || message.type() === "warning") problems.push(`${message.type()}: ${message.text()}`);
    });
    page.on("pageerror", error => problems.push(`pageerror: ${error.message}`));
    page.on("requestfailed", request => problems.push(`failed: ${request.url()}`));
    const external: string[] = [];
    page.on("request", request => {
      if (!request.url().startsWith(`${baseURL}/`) && !request.url().startsWith("data:")) external.push(request.url());
    });
    await openGate(page);
    await page.mouse.move(400, 300, { steps: 5 });
    await button(page).focus();
    await page.keyboard.press("Enter");
    await expectStory(page);
    for (const i of [1, 3, 5, 6, 7]) await goToChapter(page, i);
    await page.locator(".shell-skip").click();
    await field(page).fill("noise 10 pm");
    await expect(page.locator("[data-cs-card]").first()).toBeVisible();
    await page.locator(".theme-flip").click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "paper");
    await expect(page.locator("html")).not.toHaveClass(/c-flip/, { timeout: 10_000 });
    await page.evaluate(() => document.fonts.ready);
    expect(problems).toEqual([]);
    expect(external).toEqual([]);
  });
});

test.describe("after the production review", () => {
  test("a page at rest asks for no frames: the search, and a gate left alone", async ({ page }) => {
    test.setTimeout(100_000);
    await page.addInitScript(() => {
      const real = window.requestAnimationFrame.bind(window);
      const w = window as unknown as { __raf: number };
      w.__raf = 0;
      window.requestAnimationFrame = cb => real(t => {
        w.__raf++;
        cb(t);
      });
    });
    const frames = async (ms: number): Promise<number> => {
      const a = await page.evaluate(() => (window as unknown as { __raf: number }).__raf);
      await page.waitForTimeout(ms);
      return (await page.evaluate(() => (window as unknown as { __raf: number }).__raf)) - a;
    };
    await openGate(page, "/c/?gate=1");
    // a gate left alone rests after 25 s (the stamp lies down on the page, the map stops drifting)
    await page.waitForTimeout(42_000);
    expect(await frames(2000), "frames asked for by a gate at rest").toBeLessThanOrEqual(2);
    // and wakes on the next move
    await page.mouse.move(500, 400);
    await page.mouse.move(520, 420);
    expect(await frames(500), "frames asked for once the pointer is back").toBeGreaterThan(0);
    await page.locator(".shell-skip").click();
    await expect(page.locator("html")).toHaveAttribute("data-c-mode", "search");
    await page.waitForTimeout(3000);
    expect(await frames(2000), "frames asked for by the search at rest").toBeLessThanOrEqual(2);
    // no animation runs on anything hidden (the cue's arrow paints only while the first chapter is read)
    expect(await page.evaluate(() => document.getAnimations().filter(a => a.playState === "running").length)).toBe(0);
  });

  test("the pause button holds the map still, as the system's setting does, and is remembered", async ({ page }) => {
    await openGate(page);
    const pause = page.getByRole("button", { name: "Pause motion" });
    await expect(pause).toHaveAttribute("aria-pressed", "false");
    await pause.click();
    await expect(pause).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("html")).toHaveClass(/c-still/);
    expect(await page.evaluate(() => (window as unknown as { __story: { mode: string } }).__story.mode)).toBe("stills");
    await page.reload();
    await expect(page.getByRole("button", { name: "Pause motion" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("html")).toHaveClass(/c-still/);
    await page.getByRole("button", { name: "Pause motion" }).click();
    await expect(page.locator("html")).not.toHaveClass(/c-still/);
    expect(await page.evaluate(() => (window as unknown as { __story: { mode: string } }).__story.mode)).toBe("scrub");
  });

  test("the keyboard never falls to the page: arrow keys, the rail's last tick, Escape after a replay", async ({ page }) => {
    await openGate(page);
    await button(page).focus();
    await page.keyboard.press("Enter");
    await expectStory(page);
    await expect(chapter(page, 0).locator("h2")).toBeFocused();
    for (let i = 0; i < 2; i++) {
      await page.keyboard.press("ArrowDown");
      await page.waitForTimeout(1600);
    }
    expect(await page.evaluate(() => document.activeElement?.tagName)).toBe("H2");
    const at = await page.evaluate(() => (window as unknown as { __story: { state: { chapter: number } } }).__story.state.chapter);
    await expect(chapter(page, at).locator("h2")).toBeFocused();
    // a rail tick: its chapter's heading takes the focus once it is there
    await page.locator(".story-rail__tick").nth(4).focus();
    await page.keyboard.press("Enter");
    await expect(chapter(page, 4).locator("h2")).toBeFocused({ timeout: 10_000 });
    // the last tick ends the story: the keyboard goes on to the search field
    await page.locator(".story-rail__tick").last().focus();
    await page.keyboard.press("Enter");
    await expect(field(page)).toBeFocused({ timeout: 10_000 });
    // the seal replays the gate; Escape puts it away and the keyboard is back on the seal
    await seal(page).focus();
    await page.keyboard.press("Enter");
    await expect(gate(page)).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(gate(page)).toHaveCount(0);
    await expect(seal(page)).toBeFocused();
  });

  test("a window too short for the scrolled story reads it as plain sections, and the search follows", async ({ page }) => {
    await page.setViewportSize({ width: 640, height: 450 });
    await openGate(page);
    await button(page).focus();
    await page.keyboard.press("Enter");
    await expect(gate(page)).toHaveCount(0, { timeout: 20_000 });
    await expect(page.locator("html")).toHaveClass(/c-flow/);
    await expect(chapter(page, 0).locator("h2")).toBeFocused();
    for (let i = 0; i < 8; i++) {
      const c = chapter(page, i);
      expect(await c.evaluate(el => [getComputedStyle(el).position, getComputedStyle(el).visibility, (el as HTMLElement).inert])).toEqual(["static", "visible", false]);
    }
    // every condition of the stepped chapter is there to read, with its link
    await expect(page.locator(".c-step")).toHaveCount(8);
    for (const step of await page.locator(".c-step").all()) await expect(step).toBeVisible();
    // no map after the gate: every line of the window is the text's
    await expect(page.locator(".c-world, .c-flat").first()).toBeHidden();
    await page.locator(".shell-skip").click();
    await expect(field(page)).toBeFocused();
    await expect(field(page)).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  });

  test("a condition read with no page opens its motion where the conditions begin, never at page 1", async ({ page }) => {
    await openReturning(page, "/c/#q=2011.0186C&kind=all");
    const link = page.locator("[data-cs-card] [data-cs-pdf]").first();
    await expect(link).toHaveAttribute("href", /2011\.0186C\.pdf#page=11$/);
    await expect(link).toContainText("Exhibit A, p.");
    expect(await page.locator("[data-cs-card] [data-cs-pdf]").evaluateAll(as => as.filter(a => !/#page=\d+$/.test((a as HTMLAnchorElement).href)).length)).toBe(0);
  });

  test("the page's one h1 names the site and comes first; the search is an h2", async ({ page }) => {
    await openReturning(page);
    const headings = await page.locator("h1, h2").evaluateAll(hs => hs.slice(0, 3).map(h => `${h.tagName} ${(h.textContent ?? "").trim()}`));
    expect(headings[0]).toBe("H1 SF Conditions Search");
    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.getByRole("heading", { level: 2, name: "Conditions of approval" })).toHaveCount(1);
  });

  test("a map that cannot be loaded leaves no empty panel, and its notice is not written over", async ({ page }) => {
    await page.route(/sf-streets\./, route => route.abort());
    await openGate(page);
    await page.locator(".shell-skip").click();
    await expect(page.locator("html")).toHaveClass(/c-map-failed/);
    const panel = await page.locator(".c-search__panel").boundingBox();
    // The full width, not the two-thirds it takes beside a working map. Allow for a classic scrollbar (15 px on
    // Linux, where Chromium draws one; macOS overlays it).
    const full = await page.evaluate(() => document.documentElement.clientWidth);
    expect(Math.round(panel?.width ?? 0)).toBeGreaterThanOrEqual(full - 20);
    expect(Math.round(panel?.width ?? 0)).toBeLessThanOrEqual(full);
    await field(page).fill("noise");
    await expect(count(page)).not.toHaveText("");
    await expect(page.locator(".c-caption")).not.toContainText("motions match");
  });
});

test.describe("a phone, after the review", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("the map's band over the search scrolls away with the page and never covers a card", async ({ page }) => {
    await openGate(page, "/c/?gate=1");
    await page.locator(".shell-skip").tap();
    await expect(page.locator(".c-flat, .c-world").first()).toHaveClass(/is-band/);
    await expect(page.locator("html")).not.toHaveClass(/c-band-gone/);
    /** How far the band's foot reaches below the top of the search (negative: it is above it, as it must be). */
    const overlap = (): Promise<number> =>
      page.evaluate(() => {
        const s = getComputedStyle(document.documentElement);
        const px = (name: string): number => parseFloat(s.getPropertyValue(name)) || 0;
        const foot = px("--c-head") + px("--c-band") + 30 - px("--c-band-shift");
        return foot - document.getElementById("search")!.getBoundingClientRect().top;
      });
    await expect.poll(overlap).toBeLessThanOrEqual(1);
    await page.evaluate(() => window.scrollBy(0, 120));
    // (the band follows the scroll event, which comes with the next frame)
    await expect.poll(overlap, { message: "part way: the band has moved up with the search" }).toBeLessThanOrEqual(1);
    await page.evaluate(() => window.scrollBy(0, 900));
    await expect(page.locator("html")).toHaveClass(/c-band-gone/);
    await page.evaluate(() => window.scrollBy(0, -1020));
    await expect(page.locator("html")).not.toHaveClass(/c-band-gone/);
    await expect.poll(overlap).toBeLessThanOrEqual(1);
  });
});

test.describe("after the second verification", () => {
  test("no link and no feedback e-mail opens a motion at page 1 or with no page (2011.0186C: its conditions' page)", async ({ page }) => {
    await openReturning(page, "/c/#q=2011.0186C&kind=all");
    // the local page has no contact address: mount the search as the public site does, with one to write to
    await page.evaluate(async () => {
      type Handle = { ready: Promise<void> };
      const w = window as unknown as { showcase: { mountSearch(root: HTMLElement, o?: object): Handle } };
      await w.showcase.mountSearch(document.getElementById("search")!, { headingLevel: 2, feedbackTo: "corrections@example.org" }).ready;
    });
    await expect(page.locator("[data-cs-card]")).toHaveCount(12);
    const mails = await feedbackMails(page);
    expect(mails).toHaveLength(12);
    // each e-mail names the motion at the page its card's button opens: where its conditions begin, page 11
    for (const mail of mails) expect(mail).toMatch(/Motion page: \S+\/2011\.0186C\.pdf#page=11\r\n/);
    expect(await pagelessPdfLinks(page)).toEqual([]);
    // and a search of conditions read with their pages: every link and e-mail at the condition's own page
    await page.evaluate(() => { location.hash = "#q=noise&kind=all"; });
    await expect(page.locator("[data-cs-card]").first()).toBeVisible();
    await expect.poll(async () => (await feedbackMails(page)).length).toBeGreaterThan(20);
    expect(await pagelessPdfLinks(page)).toEqual([]);
  });

  for (const size of [{ width: 360, height: 225 }, { width: 320, height: 256 }]) {
    test(`at ${size.width} by ${size.height} (a window zoomed to 400%) the header fits: nothing overlaps or scrolls sideways`, async ({ page }) => {
      await page.setViewportSize(size);
      /** The header's items as they are drawn (the seal by its mark, which is wider than its button). */
      const expectHeaderFits = async (when: string): Promise<void> => {
        const seen = await page.evaluate(() => {
          const shown = (el: Element | null): el is HTMLElement => {
            if (!(el instanceof HTMLElement) && !(el instanceof SVGElement)) return false;
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden" && !el.closest("[hidden]");
          };
          const items: [string, DOMRect][] = [];
          for (const [name, selector] of [["wordmark", ".mark-link .mark"], ["seal", ".c-seal .stamp-mark"], ["skip", ".shell-skip"], ["pause", ".c-pause"], ["theme", ".theme-flip"]] as const) {
            const el = document.querySelector(selector);
            // (on the search the quiet skip link waits off screen until the keyboard reaches it)
            if (shown(el) && !el.closest(".shell-skip--quiet:not(:focus)")) items.push([name, el.getBoundingClientRect()]);
          }
          const overlaps: string[] = [];
          for (let i = 0; i < items.length; i++)
            for (let j = i + 1; j < items.length; j++) {
              const [a, ra] = items[i]!, [b, rb] = items[j]!;
              if (ra.left < rb.right - 0.5 && rb.left < ra.right - 0.5 && ra.top < rb.bottom - 0.5 && rb.top < ra.bottom - 0.5) overlaps.push(`${a}/${b}`);
            }
          const theme = document.querySelector(".theme-flip")!.getBoundingClientRect();
          return {
            names: items.map(([name]) => name),
            overlaps,
            sideways: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            themeOnScreen: theme.left >= 0 && theme.top >= 0 && theme.right <= window.innerWidth && theme.bottom <= window.innerHeight,
            themeSize: [Math.round(theme.width), Math.round(theme.height)],
            offScreen: items.filter(([, r]) => r.left < 0 || r.right > window.innerWidth).map(([name]) => name),
          };
        });
        expect(seen.overlaps, `${when}: overlapping in the header`).toEqual([]);
        expect(seen.sideways, `${when}: the page scrolls sideways`).toBeLessThanOrEqual(0);
        expect(seen.themeOnScreen, `${when}: the theme button is on screen`).toBe(true);
        expect(Math.min(...seen.themeSize), `${when}: the theme button keeps its size`).toBeGreaterThanOrEqual(24);
        expect(seen.offScreen, `${when}: off screen`).toEqual([]);
        expect(seen.names).toEqual(expect.arrayContaining(["wordmark", "skip", "theme"]));
        // the skip link: in sight, named in words, and the way to the search
        const skip = page.getByRole("link", { name: "Skip to search" });
        await expect(skip).toBeVisible();
        await expect(skip).toBeInViewport({ ratio: 1 });
      };
      await openGate(page);
      await expect(page.locator("html")).toHaveClass(/c-flow/);
      await expectHeaderFits("at the gate");
      // the first Tab reaches it
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "Skip to search" })).toBeFocused();
      await button(page).focus();
      await page.keyboard.press("Enter");
      await expect(gate(page)).toHaveCount(0, { timeout: 20_000 });
      await expectHeaderFits("after the gate (the story as sections, the search under it)");
      await page.getByRole("link", { name: "Skip to search" }).click();
      await expect(field(page)).toBeFocused();
      await expectHeaderFits("in the search");
    });
  }

  test("an arrow key from the last chapter goes on to the search field, never to the page", async ({ page }) => {
    await openGate(page);
    await button(page).focus();
    await page.keyboard.press("Enter");
    await expectStory(page);
    await goToChapter(page, 7);
    await expect(chapter(page, 7)).toContainText("There are");
    await chapter(page, 7).locator("h2").focus();
    // (a chapter longer than its panel takes the arrow keys first: a few presses, never the page in between)
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press("ArrowDown");
      await page.waitForTimeout(900);
      if (await field(page).evaluate(f => f === document.activeElement)) break;
      expect(await page.evaluate(() => document.activeElement?.tagName), "the focus fell to the page").not.toBe("BODY");
    }
    await expect(field(page)).toBeFocused({ timeout: 10_000 });
    await expect(page.locator("html")).toHaveAttribute("data-c-mode", "search");
  });

  test("scrolling on from the last chapter with the focus in it hands the focus to the search field", async ({ page }) => {
    await openGate(page);
    await button(page).focus();
    await page.keyboard.press("Enter");
    await expectStory(page);
    await goToChapter(page, 7);
    await chapter(page, 7).locator("h2").focus();
    // the wheel over the map (not over the chapter's own text)
    await page.mouse.move(page.viewportSize()!.width - 80, page.viewportSize()!.height / 2);
    for (let i = 0; i < 12 && (await page.locator("html").getAttribute("data-c-mode")) !== "search"; i++) {
      await page.mouse.wheel(0, 400);
      await page.waitForTimeout(250);
    }
    await expect(page.locator("html")).toHaveAttribute("data-c-mode", "search");
    await expect(field(page)).toBeFocused({ timeout: 10_000 });
  });

  test("after a touch, the end of the story focuses the search panel, not its field (no phone keyboard)", async ({ page }) => {
    await openGate(page);
    await button(page).focus();
    await page.keyboard.press("Enter");
    await expectStory(page);
    await goToChapter(page, 7);
    await chapter(page, 7).locator("h2").focus();
    await page.evaluate(() => dispatchEvent(new PointerEvent("pointerdown", { pointerType: "touch" })));
    await page.mouse.move(page.viewportSize()!.width - 80, page.viewportSize()!.height / 2);
    for (let i = 0; i < 12 && (await page.locator("html").getAttribute("data-c-mode")) !== "search"; i++) {
      await page.mouse.wheel(0, 400);
      await page.waitForTimeout(250);
    }
    await expect(page.locator("html")).toHaveAttribute("data-c-mode", "search");
    await expect(page.locator("#search")).toBeFocused({ timeout: 10_000 });
    await expect(field(page)).not.toBeFocused();
  });

  test("the story does not take the focus when it was not in the story", async ({ page }) => {
    await openGate(page);
    await button(page).focus();
    await page.keyboard.press("Enter");
    await expectStory(page);
    await goToChapter(page, 7);
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    for (let i = 0; i < 6 && (await page.locator("html").getAttribute("data-c-mode")) !== "search"; i++) {
      await page.keyboard.press("ArrowDown");
      await page.waitForTimeout(900);
    }
    await expect(page.locator("html")).toHaveAttribute("data-c-mode", "search");
    await page.waitForTimeout(400);
    expect(await page.evaluate(() => document.activeElement?.tagName)).toBe("BODY");
  });

  for (const how of ["the system's reduced motion", "the system's setting turned on while it is up", "the pause button"] as const) {
    test(`a gate held still by ${how} asks for no frames once it is drawn, and still says its notes`, async ({ page }) => {
      if (how === "the system's reduced motion") await page.emulateMedia({ reducedMotion: "reduce" });
      if (how === "the pause button") await page.addInitScript(() => localStorage.setItem("showcase:c-motion", "paused"));
      await page.addInitScript(() => {
        const real = window.requestAnimationFrame.bind(window);
        const w = window as unknown as { __raf: number };
        w.__raf = 0;
        window.requestAnimationFrame = cb => real(t => {
          w.__raf++;
          cb(t);
        });
      });
      const frames = async (ms: number): Promise<number> => {
        const a = await page.evaluate(() => (window as unknown as { __raf: number }).__raf);
        await page.waitForTimeout(ms);
        return (await page.evaluate(() => (window as unknown as { __raf: number }).__raf)) - a;
      };
      await openGate(page, "/c/?gate=1");
      // (the gate came up moving: the system's setting changes under it)
      if (how === "the system's setting turned on while it is up") await page.emulateMedia({ reducedMotion: "reduce" });
      await expect(page.locator("html")).toHaveClass(/c-still/);
      // (a few frames after the load: the map and the stamp are drawn, once)
      await page.waitForTimeout(1500);
      expect(await frames(2000), "frames asked for by a gate held still").toBeLessThanOrEqual(3);
      // a move wakes it (the stamp follows the pointer, unless it stands on the page), then it sleeps again
      await page.mouse.move(600, 420);
      await page.mouse.move(640, 440, { steps: 4 });
      await page.waitForTimeout(1200);
      expect(await frames(2000), "frames asked for once the pointer has stopped").toBeLessThanOrEqual(3);
      if (how !== "the system's reduced motion") {
        // the gate's notes come on their clock, with the loop asleep in between
        await expect(page.locator(".c-gate__note")).toContainText("Go on.", { timeout: 12_000 });
        expect(await frames(2000), "frames asked for after the note").toBeLessThanOrEqual(3);
      }
      // the stamp is still there to press
      await button(page).focus();
      await page.keyboard.press("Enter");
      await expect(gate(page)).toHaveCount(0, { timeout: 20_000 });
    });
  }
});
