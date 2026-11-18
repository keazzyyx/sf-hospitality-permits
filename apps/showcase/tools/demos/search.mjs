// The plain search page, as a baseline for the recorder: type a query, scroll the results.
export const path = "/search/";
export const viewport = { width: 1280, height: 800 };

export async function run(page) {
  const field = page.locator('[data-cs-field="q"]');
  await field.click();
  await page.keyboard.type("outdoor seating", { delay: 90 });
  await page.waitForTimeout(900);
  for (let i = 0; i < 20; i++) {
    await page.mouse.wheel(0, 90);
    await page.waitForTimeout(60);
  }
  await page.waitForTimeout(600);
  await field.fill("");
  await page.keyboard.type("noise 10 pm", { delay: 90 });
  await page.waitForTimeout(1500);
}

export async function phone(page) {
  await page.locator('[data-cs-field="q"]').fill("outdoor seating");
}
