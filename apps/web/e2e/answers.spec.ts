import { expect, test, type Page } from "@playwright/test";
import { MEMO_RECORD_FULL_ANSWERABLE, MEMO_RECORD_TEASER_ANSWERABLE } from "../src/lib/fixtures/memo-fixture";
import { ANSWERS_NEW_MEMO_NOTE, answersRoundLabel, earlierVersionLabel } from "../src/lib/memo";
import type { MemoRecord, MemoRevision } from "../src/lib/api-types";

// "Answer and run again" on the memo page (owner decision of 2026-11-16): the form posts the answers to
// POST /v1/memos/{id}/answers and the page stays on the same memo, then shows the round and the earlier version.
// The real memo view and the hook the memo page uses, on the development route /dev/memo-preview; every API call is
// answered here and the requests are read.

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "authorization, content-type, accept",
  "access-control-allow-methods": "GET, POST, PATCH, DELETE, OPTIONS",
};

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

interface Seen {
  answers: { path: string; body: Record<string, unknown> }[];
  creates: number;
  revisions: number;
}

/** Answer every API call: the round streams back `updated`; the revisions list holds the version it replaced. */
async function routeApi(page: Page, before: MemoRecord, updated: MemoRecord): Promise<Seen> {
  const seen: Seen = { answers: [], creates: 0, revisions: 0 };
  const revision: MemoRevision = {
    round: 1,
    replaced_at: "2026-11-16T10:00:00Z",
    generated_at: "2026-11-10T11:21:23Z",
    intake: before.intake ?? null,
    teaser: before.teaser,
    memo: before.access === "full" ? before.memo : null,
    legacy_format: false,
  };
  await page.route("**/v1/**", async (route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: CORS });
      return;
    }
    const path = new URL(req.url()).pathname;
    if (path === `/v1/memos/${before.id}/answers` && req.method() === "POST") {
      seen.answers.push({ path, body: req.postDataJSON() as Record<string, unknown> });
      await route.fulfill({
        status: 200,
        headers: { ...CORS, "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-cache" },
        body:
          sse("answers_round", { memo_id: before.id, round: 1 }) +
          sse("stage", { stage: "intake", status: "started", message: "Applying your answers to the facts read from your description…" }) +
          sse("stage", { stage: "intake", status: "completed", message: "Concept: bar in San Francisco." }) +
          sse("memo", updated),
      });
      return;
    }
    if (path === `/v1/memos/${before.id}/revisions` && req.method() === "GET") {
      seen.revisions += 1;
      await route.fulfill({ status: 200, headers: { ...CORS, "content-type": "application/json" }, body: JSON.stringify({ revisions: [revision] }) });
      return;
    }
    if (path === "/v1/memos" && req.method() === "POST") seen.creates += 1;
    await route.fulfill({ status: 404, headers: { ...CORS, "content-type": "application/json" }, body: JSON.stringify({ detail: { code: "not_found", message: "Not found" } }) });
  });
  return seen;
}

function afterRound(before: MemoRecord): MemoRecord {
  return {
    ...before,
    intake: { floor_area_sqft: 1400, stories: ["first"], last_use: "retail" },
    answers_round: 1,
    answers_rounds_left: 4,
    answers_available: true,
    answered_at: "2026-11-16T10:00:05Z",
    updated_at: "2026-11-16T10:00:05Z",
  };
}

test.describe("memo page: answer and run again on the same memo", () => {
  test("the form posts the answers to the memo's answers route and the page shows the round", async ({ page }) => {
    const before = MEMO_RECORD_FULL_ANSWERABLE;
    const seen = await routeApi(page, before, afterRound(before));
    await page.goto("/dev/memo-preview?access=full&variant=answers");
    const url = page.url();
    await expect(page.getByTestId("answers-round-label")).toHaveCount(0);
    // the button opens the form on this page, filled in with the answers the memo has
    await expect(page.getByTestId("answer-questions-link")).toHaveCount(0);
    await page.getByTestId("answer-questions-button").click();
    const form = page.getByTestId("answer-round-form");
    await expect(form).toBeVisible();
    await expect(form.getByTestId("intake-floor-area")).toHaveValue("1400");
    await expect(form.getByTestId("answer-rounds-left")).toHaveText("5 rounds of answers left on this memo.");
    await form.getByTestId("intake-story-first").click();
    await form.getByTestId("intake-last-use-retail").click();
    await form.getByTestId("answer-round-submit").click();

    await expect.poll(() => seen.answers.length).toBe(1);
    // the answers only: no address, no description, no overrides
    expect(seen.answers[0].body).toEqual({ floor_area_sqft: 1400, stories: ["first"], last_use: "retail" });
    // the same page, the same memo, now labelled with the round, and the earlier version listed
    await expect(page.getByTestId("answers-round-label")).toHaveText(answersRoundLabel(1));
    expect(page.url()).toBe(url);
    await expect(page.getByTestId("memo-address")).toHaveText(before.address);
    await expect(page.getByTestId("answer-round-form")).toHaveCount(0);
    const versions = page.getByTestId("earlier-versions");
    await expect(versions).toBeVisible();
    await expect(versions.getByTestId("earlier-version")).toHaveCount(1);
    await expect(versions.getByTestId("earlier-version").first()).toContainText(earlierVersionLabel(1));
    expect(seen.revisions).toBeGreaterThan(0);
    expect(seen.creates).toBe(0);
  });

  test("the same answers are not sent", async ({ page }) => {
    const before = MEMO_RECORD_FULL_ANSWERABLE;
    const seen = await routeApi(page, before, afterRound(before));
    await page.goto("/dev/memo-preview?access=full&variant=answers");
    await page.getByTestId("answer-questions-button").click();
    await page.getByTestId("answer-round-submit").click();
    await expect(page.getByTestId("answer-round-error")).toHaveText("Change at least one answer first.");
    expect(seen.answers.length).toBe(0);
  });

  test("a teaser's round posts the same way and the memo stays a teaser", async ({ page }) => {
    const before = MEMO_RECORD_TEASER_ANSWERABLE;
    const seen = await routeApi(page, before, afterRound(before));
    await page.goto("/dev/memo-preview?access=teaser&variant=answers");
    const block = page.getByTestId("teaser-answers");
    await block.getByTestId("answer-questions-button").click();
    await block.getByTestId("intake-story-first").click();
    await block.getByTestId("intake-last-use-retail").click();
    await block.getByTestId("answer-round-submit").click();
    await expect.poll(() => seen.answers.length).toBe(1);
    expect(seen.answers[0].path).toBe(`/v1/memos/${before.id}/answers`);
    await expect(page.getByTestId("answers-round-label")).toHaveText(answersRoundLabel(1));
    await expect(page.getByTestId("memo-view")).toHaveAttribute("data-access", "teaser");
    await expect(page.getByTestId("unlock-card")).toBeVisible();
    expect(seen.creates).toBe(0);
  });

  test("a memo made before answers could be added keeps the link to a new memo and says so", async ({ page }) => {
    await routeApi(page, MEMO_RECORD_FULL_ANSWERABLE, afterRound(MEMO_RECORD_FULL_ANSWERABLE));
    await page.goto("/dev/memo-preview?access=full&variant=answers-unavailable");
    await expect(page.getByTestId("answer-questions-button")).toHaveCount(0);
    await expect(page.getByTestId("answer-questions-link")).toHaveAttribute("href", /^\/app\/memo\?/);
    await expect(page.getByTestId("answer-questions-note")).toHaveText(ANSWERS_NEW_MEMO_NOTE);
  });
});
