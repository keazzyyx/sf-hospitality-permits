import { expect, test } from "@playwright/test";

// A memo run goes on on the server when its stream drops (apps/api/app/routes/memos.py `_detached`). The new-memo
// page must then open the memo's own page, which follows the run until it is ready, and must not offer a retry that
// would start, and charge, a second memo.

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "authorization, content-type, accept",
  "access-control-allow-methods": "GET, POST, PATCH, DELETE, OPTIONS",
};

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

test("a stream that drops after the memo was created opens the memo's page instead of offering a retry", async ({ page }) => {
  let creates = 0;
  await page.route("**/v1/**", async (route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: CORS });
      return;
    }
    const path = new URL(req.url()).pathname;
    if (path === "/v1/memos" && req.method() === "POST") {
      creates += 1;
      // the stream ends after a stage event with no memo and no error: the connection dropped mid-run
      await route.fulfill({
        status: 200,
        headers: { ...CORS, "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-cache" },
        body: sse("memo_created", { memo_id: "memo_dropped" }) + sse("stage", { stage: "intake", status: "started", label: "Reading your concept…" }),
      });
      return;
    }
    if (path === "/v1/geocode") {
      await route.fulfill({ status: 200, headers: { ...CORS, "content-type": "application/json" }, body: JSON.stringify({ suggestions: [] }) });
      return;
    }
    await route.fulfill({ status: 404, headers: { ...CORS, "content-type": "application/json" }, body: JSON.stringify({ code: "not_found", message: "Not found" }) });
  });
  await page.goto("/dev/new-memo");
  await page.locator("#memo-address").fill("995 Valencia St, San Francisco, CA 94110");
  await page.locator("#memo-description").fill("40-seat wine bar, small kitchen, open until 1am, occasional live music");
  await page.getByTestId("memo-submit").click();
  // the page leaves for the memo's own page (behind sign-in in this dev setup), and never shows a retry error
  await page.waitForURL((url) => url.pathname.startsWith("/app/memos/memo_dropped") || url.searchParams.get("next") === "/app/memos/memo_dropped");
  expect(creates).toBe(1);
});
