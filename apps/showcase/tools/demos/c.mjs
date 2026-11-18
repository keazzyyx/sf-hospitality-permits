// Prototype C, the living grid: the grid answers the cursor (it tilts, and swells under the stamp), a hold is let
// go once and then held: the slam sends a ring through the whole city, the sheet cracks and falls into the grid at
// its address, the story's first chapter arrives, a scroll dives to the address, and the mark flips the world to
// paper from the corner. About 13.5 seconds, driven with real pointer moves at a steady pace (nothing is random).
export const path = "/c/?gate=1";
export const viewport = { width: 1280, height: 800 };

/** Move the mouse from one point to another over `ms` (eased, with a little arc). The clock sets the pace, so the
 *  move takes `ms` however long each step takes to send. */
async function glide(page, from, to, ms, bend = 0) {
  const start = Date.now();
  for (;;) {
    const t = Math.min(1, (Date.now() - start) / ms);
    const e = t * t * (3 - 2 * t);
    const lift = Math.sin(t * Math.PI) * bend;
    await page.mouse.move(from.x + (to.x - from.x) * e, from.y + (to.y - from.y) * e - lift);
    if (t >= 1) break;
    await page.waitForTimeout(12);
  }
  return to;
}

export async function run(page) {
  const { width: w, height: h } = viewport;
  // where the sheet lies, so the same script lands the mark on it at any size
  const sheet = await page.locator(".c-motion").boundingBox();
  const at = (fx, fy) => ({ x: sheet.x + sheet.width * fx, y: sheet.y + sheet.height * fy });
  let p = { x: w * 0.86, y: h * 0.3 };
  await page.mouse.move(p.x, p.y);
  await page.waitForTimeout(350);
  // across the city: the view tilts toward the cursor, the ground swells under the stamp
  p = await glide(page, p, { x: w * 0.2, y: h * 0.36 }, 1300, 30);
  p = await glide(page, p, at(0.56, 0.6), 900, -30);
  await page.waitForTimeout(250);
  // a hold let go at about half way: the ground comes back up, "Hold it down."
  await page.mouse.down();
  await page.waitForTimeout(600);
  await page.mouse.up();
  await page.waitForTimeout(900);
  // the real one: 1.2 seconds, then the slam and the ring through the city
  await page.mouse.down();
  await page.waitForTimeout(1500);
  await page.mouse.up();
  // the mark, the crack, the pieces falling into the grid, the red point, the first chapter
  p = await glide(page, p, { x: w * 0.7, y: h * 0.5 }, 900, 20);
  await page.waitForTimeout(2300);
  // scroll: the camera dives to the address, and its streets are named
  for (let i = 0; i < 8; i++) {
    await page.mouse.wheel(0, 205);
    await page.waitForTimeout(40);
  }
  await page.waitForTimeout(1500);
  // the mark flips the world to paper, from the corner
  await page.keyboard.press("t");
  await page.waitForTimeout(1300);
}

export async function phone(page) {
  // a held finger on the sheet: the stamp comes down where it points, and lands
  const sheet = await page.locator(".c-motion").boundingBox();
  const cdp = await page.context().newCDPSession(page);
  const point = { x: Math.round(sheet.x + sheet.width * 0.52), y: Math.round(sheet.y + sheet.height * 0.6) };
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [point] });
  await page.waitForTimeout(1380);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  // the screenshot that follows shows the mark on the sheet and the ring leaving through the city
}
