// Typing must not jank: the time from a keystroke to the results being on the page, for common queries.
// Two numbers per keystroke: the search-and-render cost inside the input handler, and the time from the key event
// to the first frame after it (what the visitor sees). Budget: 50 ms.

import { expect, test } from "@playwright/test";

const QUERIES = ["outdoor seating", "noise", "security guard", "10 pm", "live music", "Valencia St", "2015-009955CUA", "odor", "garbage", "1408 California St"];
// A shared CI runner (two slow cores, other tests running beside it) is not the machine the budget is for: there
// the numbers are printed and only a gross regression fails (500 ms), and the four-times-slower run is left out.
const CI = Boolean(process.env.CI);
const BUDGET_MS = CI ? 500 : 50;

test.describe.configure({ mode: "serial" });

test("input to render stays under 50 ms for common queries", async ({ page }) => {
  await page.goto("/search/");
  await page.locator('.cs[data-cs-state="ready"]').waitFor();
  await page.locator(".cs[data-cs-warm]").waitFor(); // the search keys are built in idle time after the first paint

  await page.evaluate(() => {
    const w = window as unknown as { samples: { key: string; q: string; cost: number; frame: number }[] };
    w.samples = [];
    const input = document.querySelector<HTMLInputElement>('[data-cs-field="q"]');
    const wrap = document.querySelector<HTMLElement>(".cs");
    if (!input || !wrap) throw new Error("no search field");
    let down = 0;
    let typed = false;
    input.addEventListener("keydown", e => { down = performance.now(); typed = e.key.length === 1; }, { capture: true });
    // "cs:results" fires when a search has been drawn (at once while typing is cheap, after a short pause if not)
    document.addEventListener("cs:results", () => {
      if (!typed) return;
      typed = false;
      const start = down;
      const q = input.value;
      const cost = Number(wrap.dataset.csRenderMs); // what the search and the drawing just took
      requestAnimationFrame(() => {
        // the frame that paints the new results has begun; one task later it is on the screen
        const channel = new MessageChannel();
        channel.port1.onmessage = () => w.samples.push({ key: q.slice(-1), q, cost, frame: performance.now() - start });
        channel.port2.postMessage(0);
      });
    });
  });

  const field = page.locator('[data-cs-field="q"]');
  for (const q of QUERIES) {
    await field.focus();
    await page.keyboard.type(q, { delay: 45 });
    await page.waitForTimeout(120);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(80);
  }

  const samples = await page.evaluate(() => (window as unknown as { samples: { q: string; cost: number; frame: number }[] }).samples);
  expect(samples.length).toBeGreaterThan(80);
  const stats = (xs: number[]) => {
    const s = [...xs].sort((a, b) => a - b);
    const at = (p: number): number => s[Math.min(s.length - 1, Math.floor(p * s.length))] ?? 0;
    return { median: at(0.5), p95: at(0.95), max: s[s.length - 1] ?? 0 };
  };
  const cost = stats(samples.map(s => s.cost));
  const frame = stats(samples.map(s => s.frame));
  const worst = [...samples].sort((a, b) => b.frame - a.frame)[0];
  const line =
    `input-to-render over ${samples.length} keystrokes: ` +
    `search+render median ${cost.median.toFixed(1)} ms, p95 ${cost.p95.toFixed(1)} ms, max ${cost.max.toFixed(1)} ms; ` +
    `key-to-frame median ${frame.median.toFixed(1)} ms, p95 ${frame.p95.toFixed(1)} ms, max ${frame.max.toFixed(1)} ms ` +
    `(worst at "${worst?.q}")`;
  console.log(line);
  test.info().annotations.push({ type: "timing", description: line });

  expect(cost.max, "search and render inside the input handler").toBeLessThan(BUDGET_MS);
  expect(frame.p95, "keystroke to the next frame, 95th percentile").toBeLessThan(BUDGET_MS);
  expect(frame.median, "keystroke to the next frame, median").toBeLessThan(BUDGET_MS);
});

// The same typing on a machine four times slower (Chrome's CPU throttle): the keystrokes that draw a full page of
// cards are the ones that go over, so this is where the budget is held. A fast machine hides them.
test("typing stays within the budget on a machine four times slower", async ({ page }) => {
  test.skip(CI, "a CI runner slowed four times more says nothing about a visitor's machine");
  await page.goto("/search/");
  await page.locator('.cs[data-cs-state="ready"]').waitFor();
  await page.locator(".cs[data-cs-warm]").waitFor();
  await page.evaluate(() => {
    const w = window as unknown as { frames: number[] };
    w.frames = [];
    const input = document.querySelector<HTMLInputElement>('[data-cs-field="q"]');
    if (!input) throw new Error("no search field");
    let down = 0;
    let typed = false;
    input.addEventListener("keydown", e => { down = performance.now(); typed = e.key.length === 1; }, { capture: true });
    document.addEventListener("cs:results", () => {
      if (!typed) return;
      typed = false;
      const start = down;
      requestAnimationFrame(() => {
        const channel = new MessageChannel();
        channel.port1.onmessage = () => w.frames.push(performance.now() - start);
        channel.port2.postMessage(0);
      });
    });
  });
  const session = await page.context().newCDPSession(page);
  await session.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  const field = page.locator('[data-cs-field="q"]');
  for (const q of ["outdoor seating", "noise", "odor", "garbage", "live music"]) {
    await field.focus();
    await page.keyboard.type(q, { delay: 120 });
    await page.waitForTimeout(300);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
  }
  await session.send("Emulation.setCPUThrottlingRate", { rate: 1 });
  const frames = await page.evaluate(() => (window as unknown as { frames: number[] }).frames);
  expect(frames.length).toBeGreaterThan(30);
  const sorted = [...frames].sort((a, b) => a - b);
  const at = (p: number): number => sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))] ?? 0;
  const line = `4x slower, ${frames.length} keystrokes: key-to-frame median ${at(0.5).toFixed(1)} ms, p95 ${at(0.95).toFixed(1)} ms, max ${at(1).toFixed(1)} ms`;
  console.log(line);
  test.info().annotations.push({ type: "timing", description: line });
  expect(at(0.5), "median, four times slower").toBeLessThan(BUDGET_MS);
  // the 95th percentile has room for the test machine's other work (the suite runs in parallel): before the cards
  // were given content-visibility it measured 70 to 84 ms here on an idle machine, after it 38
  expect(at(0.95), "95th percentile, four times slower").toBeLessThan(80);
});

test("the first 50 results are on the page as soon as the data is", async ({ page }) => {
  await page.goto("/search/");
  await page.locator('.cs[data-cs-state="ready"]').waitFor();
  const first = await page.evaluate(() => Number(document.querySelector<HTMLElement>(".cs")?.dataset.csRenderMs));
  await expect(page.locator("[data-cs-card]")).toHaveCount(50);
  console.log(`first render (3,130 matches sorted, 50 cards drawn): ${first.toFixed(1)} ms`);
  expect(first).toBeLessThan(CI ? 1200 : 400);
});
