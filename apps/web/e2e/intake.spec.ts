import { expect, test, type Page } from "@playwright/test";
import { INTAKE_QUESTIONS, INTAKE_SKIP_NOTE } from "../src/lib/intake";

// The optional intake questions on the new-memo form (src/components/memo/intake-questions.tsx), on the real form
// rendered by the development route /dev/new-memo. Every API call is answered here; the create request is read.

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "authorization, content-type, accept",
  "access-control-allow-methods": "GET, POST, PATCH, DELETE, OPTIONS",
};
const ADDRESS = "995 Valencia St, San Francisco, CA 94110";
const DESCRIPTION = "40-seat wine bar, small kitchen, open until 1am, occasional live music";

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** Answer every API call; return the bodies of the create requests, in order. */
async function routeApi(page: Page): Promise<Record<string, unknown>[]> {
  const posted: Record<string, unknown>[] = [];
  await page.route("**/v1/**", async (route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: CORS });
      return;
    }
    const path = new URL(req.url()).pathname;
    if (path === "/v1/memos" && req.method() === "POST") {
      posted.push(req.postDataJSON() as Record<string, unknown>);
      await route.fulfill({
        status: 200,
        headers: { ...CORS, "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-cache" },
        body: sse("memo_created", { memo_id: "memo_e2e" }) + sse("error", { code: "generation_failed", message: "Stopped by the test." }),
      });
      return;
    }
    if (path === "/v1/geocode") {
      await route.fulfill({ status: 200, headers: { ...CORS, "content-type": "application/json" }, body: JSON.stringify({ suggestions: [] }) });
      return;
    }
    await route.fulfill({ status: 404, headers: { ...CORS, "content-type": "application/json" }, body: JSON.stringify({ code: "not_found", message: "Not found" }) });
  });
  return posted;
}

async function fillAddressAndConcept(page: Page) {
  await page.locator("#memo-address").fill(ADDRESS);
  await page.locator("#memo-description").fill(DESCRIPTION);
}

test.describe("new memo: the optional intake questions", () => {
  test("the main questions sit under the concept, each marked optional with the skip line", async ({ page }) => {
    await routeApi(page);
    await page.goto("/dev/new-memo");
    const block = page.getByTestId("intake-questions");
    await expect(block).toBeVisible();
    for (const id of ["part_of_chain", "floor_area_sqft", "liquor_licence", "alcohol_served", "stories", "closing_time", "last_use", "fewer_than_50_people", "outdoor_area"] as const) {
      const q = block.getByTestId(`intake-question-${id}`);
      await expect(q).toContainText(INTAKE_QUESTIONS[id].question);
      await expect(q).toContainText("Optional");
      await expect(q.getByTestId("intake-skip-note")).toHaveText(INTAKE_SKIP_NOTE);
    }
    // the chain question: yes / no / skip, skip chosen; the count is asked only after a yes
    await expect(page.getByRole("radiogroup", { name: INTAKE_QUESTIONS.part_of_chain.question }).getByRole("radio")).toHaveText(["Yes", "No", "Skip"]);
    await expect(page.getByTestId("intake-chain-skip")).toHaveAttribute("aria-checked", "true");
    await expect(page.getByTestId("intake-other-locations")).toHaveCount(0);
    await page.getByTestId("intake-chain-yes").click();
    await expect(page.getByLabel(INTAKE_QUESTIONS.other_locations.question)).toBeVisible();
    // the licence question: the five answers, then skip ("already held" is its own answer, and "No alcohol" is no
    // alcohol only)
    await expect(page.getByRole("radiogroup", { name: INTAKE_QUESTIONS.liquor_licence.question }).getByRole("radio")).toHaveText([
      "New licence",
      "Transfer from another owner",
      "Transfer from another location",
      "Already hold a licence at this address",
      "No alcohol",
      "Skip",
    ]);
  });

  test("the questions only some reports ask for sit under More details, closed until opened", async ({ page }) => {
    await routeApi(page);
    await page.goto("/dev/new-memo");
    const more = page.getByTestId("intake-more");
    await expect(more).not.toHaveAttribute("open", "");
    await expect(more.getByTestId("intake-question-existing_occupancy_group")).not.toBeVisible();
    await more.locator("summary").click();
    for (const id of ["existing_business_change", "floor_area_before_sqft", "merges_storefronts", "amends_prior_approval", "entertainment", "existing_occupancy_group"] as const) {
      await expect(more.getByTestId(`intake-question-${id}`)).toContainText(INTAKE_QUESTIONS[id].question);
    }
  });

  test("the answers that decide the rows are sent: stories, what is poured, the closing time, the last use, the people and the patio", async ({ page }) => {
    const posted = await routeApi(page);
    await page.goto("/dev/new-memo");
    await fillAddressAndConcept(page);
    await page.getByTestId("intake-licence-new").click();
    await page.getByTestId("intake-pours-full_liquor").click();
    // ticked out of order: sent in the API's order, each once
    await page.getByTestId("intake-story-second").click();
    await page.getByTestId("intake-story-first").click();
    await page.getByTestId("intake-closing-time").fill("02:00");
    await page.getByTestId("intake-last-use-retail").click();
    await page.getByTestId("intake-under-50-yes").click();
    await page.getByTestId("intake-outdoor-rear_or_side").click();
    await page.getByTestId("intake-outdoor-alcohol-no").click();
    await page.getByTestId("intake-more").locator("summary").click();
    await page.getByTestId("intake-occupancy-group-A-2").click();
    await page.getByTestId("intake-floor-area-before").fill("1200");
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].intake).toEqual({
      liquor_licence: "new",
      stories: ["first", "second"],
      alcohol_served: "full_liquor",
      closing_time: "02:00",
      last_use: "retail",
      fewer_than_50_people: true,
      outdoor_area: "rear_or_side",
      outdoor_alcohol_service: false,
      floor_area_before_sqft: 1200,
      existing_occupancy_group: "A-2",
    });
  });

  test("no alcohol takes the alcohol follow-ups away, and no outdoor area the outdoor one", async ({ page }) => {
    const posted = await routeApi(page);
    await page.goto("/dev/new-memo");
    await fillAddressAndConcept(page);
    await page.getByTestId("intake-pours-beer_wine").click();
    await page.getByTestId("intake-outdoor-front").click();
    await page.getByTestId("intake-outdoor-alcohol-yes").click();
    // "No alcohol": what is poured and alcohol outdoors are no longer asked, and the answers given to them are not sent
    await page.getByTestId("intake-licence-none").click();
    await expect(page.getByTestId("intake-question-alcohol_served")).toHaveCount(0);
    await expect(page.getByTestId("intake-question-outdoor_alcohol_service")).toHaveCount(0);
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].intake).toEqual({ liquor_licence: "none", outdoor_area: "front" });
    // "No outdoor area" is an answer of its own, with no follow-up
    await page.getByTestId("intake-licence-skip").click();
    await page.getByTestId("intake-outdoor-none").click();
    await expect(page.getByTestId("intake-question-outdoor_alcohol_service")).toHaveCount(0);
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(2);
    expect(posted[1].intake).toEqual({ alcohol_served: "beer_wine", outdoor_area: "none" });
  });

  test("no alcohol asks what kind of food or drink service it is, and an answer that alcohol is served takes it away", async ({ page }) => {
    const posted = await routeApi(page);
    await page.goto("/dev/new-memo");
    await fillAddressAndConcept(page);
    await expect(page.getByTestId("intake-question-food_service")).toHaveCount(0);
    await page.getByTestId("intake-licence-none").click();
    const q = page.getByTestId("intake-question-food_service");
    await expect(q).toContainText(INTAKE_QUESTIONS.food_service.question);
    await expect(q).toContainText("Optional");
    // the three answers, worded as Planning Code § 102 words the uses, then skip, with skip chosen
    await expect(page.getByRole("radiogroup", { name: INTAKE_QUESTIONS.food_service.question }).getByRole("radio")).toHaveText([
      ...INTAKE_QUESTIONS.food_service.answers.map((a) => a.label),
      "Skip",
    ]);
    await expect(page.getByTestId("intake-food-service-skip")).toHaveAttribute("aria-checked", "true");
    await page.getByTestId("intake-food-service-limited_restaurant").click();
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].intake).toEqual({ liquor_licence: "none", food_service: "limited_restaurant" });
    // a licence after all: the question goes, and its answer is not sent (the API refuses the two together)
    await page.getByTestId("intake-licence-new").click();
    await expect(page.getByTestId("intake-question-food_service")).toHaveCount(0);
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(2);
    expect(posted[1].intake).toEqual({ liquor_licence: "new" });
  });

  test("the kind of food or drink service the report asked for is shown with the licence question skipped", async ({ page }) => {
    const posted = await routeApi(page);
    // the description said the bar serves no alcohol, so the form has no licence answer; the report asked the kind of service
    const q = new URLSearchParams({ address: ADDRESS, description: "A zero-proof cocktail bar on the ground floor", answer: "1", ask: "food_service" });
    await page.goto(`/dev/new-memo?${q.toString()}`);
    await expect(page.getByTestId("intake-licence-skip")).toHaveAttribute("aria-checked", "true");
    await expect(page.getByTestId("intake-question-liquor_licence")).toHaveAttribute("data-asked", "true");
    await page.getByTestId("intake-food-service-restaurant").click();
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].intake).toEqual({ food_service: "restaurant" });
  });

  test("an answer-these link opens the form filled in, marks what the report asked for, and waits", async ({ page }) => {
    const posted = await routeApi(page);
    const q = new URLSearchParams({ address: ADDRESS, description: DESCRIPTION, liquor_licence: "new", answer: "1", ask: "stories,alcohol_served,existing_occupancy_group,not_a_question" });
    await page.goto(`/dev/new-memo?${q.toString()}`);
    await expect(page.getByTestId("intake-asked-note")).toContainText("could not decide 3 things");
    await expect(page.locator("#memo-address")).toHaveValue(ADDRESS);
    await expect(page.getByTestId("intake-licence-new")).toHaveAttribute("aria-checked", "true");
    for (const id of ["stories", "alcohol_served", "existing_occupancy_group"] as const) {
      await expect(page.getByTestId(`intake-question-${id}`)).toHaveAttribute("data-asked", "true");
    }
    await expect(page.getByTestId("intake-question-last_use")).toHaveAttribute("data-asked", "false");
    // a question under More details was asked for, so it is open
    await expect(page.getByTestId("intake-question-existing_occupancy_group")).toBeVisible();
    // nothing is started until the answers are sent
    expect(posted).toHaveLength(0);
    await page.getByTestId("intake-story-first").click();
    await page.getByTestId("intake-pours-full_liquor").click();
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toEqual({ address: ADDRESS, description: DESCRIPTION, intake: { liquor_licence: "new", stories: ["first"], alcohol_served: "full_liquor" } });
  });

  test("a follow-up the report asked for is shown even when its parent question was answered in the description", async ({ page }) => {
    const posted = await routeApi(page);
    // the description said where the patio is, so the form has no answer for the place; the report asked about alcohol there
    const q = new URLSearchParams({ address: ADDRESS, description: `${DESCRIPTION}, rear patio`, answer: "1", ask: "outdoor_alcohol_service" });
    await page.goto(`/dev/new-memo?${q.toString()}`);
    await expect(page.getByTestId("intake-outdoor-skip")).toHaveAttribute("aria-checked", "true");
    await expect(page.getByTestId("intake-question-outdoor_area")).toHaveAttribute("data-asked", "true");
    await page.getByTestId("intake-outdoor-alcohol-yes").click();
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].intake).toEqual({ outdoor_alcohol_service: true });
    // a place chosen and taken back: the question the report asked for and its answer stay
    await page.getByTestId("intake-outdoor-front").click();
    await page.getByTestId("intake-outdoor-skip").click();
    await expect(page.getByTestId("intake-outdoor-alcohol-yes")).toHaveAttribute("aria-checked", "true");
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(2);
    expect(posted[1].intake).toEqual({ outdoor_alcohol_service: true });
  });

  test("the outdoor area set back to Skip takes the alcohol outdoors answer away, and it is not sent", async ({ page }) => {
    const posted = await routeApi(page);
    await page.goto("/dev/new-memo");
    await fillAddressAndConcept(page);
    await page.getByTestId("intake-outdoor-front").click();
    await page.getByTestId("intake-outdoor-alcohol-yes").click();
    await page.getByTestId("intake-outdoor-skip").click();
    await expect(page.getByTestId("intake-question-outdoor_alcohol_service")).toHaveCount(0);
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toEqual({ address: ADDRESS, description: DESCRIPTION });
    // choosing a place again asks again, with no answer kept from before
    await page.getByTestId("intake-outdoor-rear_or_side").click();
    await expect(page.getByTestId("intake-outdoor-alcohol-skip")).toHaveAttribute("aria-checked", "true");
  });

  test("an alcohol outdoors answer carried by an answer-these link is shown, and sent only while shown", async ({ page }) => {
    const posted = await routeApi(page);
    // an earlier answer with no place (the description gave it); this report asked about something else
    const q = new URLSearchParams({ address: ADDRESS, description: `${DESCRIPTION}, rear patio`, outdoor_alcohol_service: "yes", answer: "1", ask: "stories" });
    await page.goto(`/dev/new-memo?${q.toString()}`);
    await expect(page.getByTestId("intake-outdoor-alcohol-yes")).toHaveAttribute("aria-checked", "true");
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].intake).toEqual({ outdoor_alcohol_service: true });
    // "No outdoor area": the follow-up and its answer go
    await page.getByTestId("intake-outdoor-none").click();
    await expect(page.getByTestId("intake-question-outdoor_alcohol_service")).toHaveCount(0);
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(2);
    expect(posted[1].intake).toEqual({ outdoor_area: "none" });
  });

  test("already holding a licence at this address is sent as its own answer", async ({ page }) => {
    const posted = await routeApi(page);
    await page.goto("/dev/new-memo");
    await fillAddressAndConcept(page);
    await page.getByTestId("intake-licence-already_held").click();
    await expect(page.getByTestId("intake-licence-already_held")).toHaveAttribute("aria-checked", "true");
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].intake).toEqual({ liquor_licence: "already_held" });
  });

  test("a re-run link with a licence already held keeps that answer", async ({ page }) => {
    const posted = await routeApi(page);
    const q = new URLSearchParams({ address: ADDRESS, description: DESCRIPTION, liquor_licence: "already_held" });
    await page.goto(`/dev/new-memo?${q.toString()}`);
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toEqual({ address: ADDRESS, description: DESCRIPTION, intake: { liquor_licence: "already_held" } });
  });

  test("the form sends the answers given", async ({ page }) => {
    const posted = await routeApi(page);
    await page.goto("/dev/new-memo");
    await fillAddressAndConcept(page);
    await page.getByTestId("intake-chain-yes").click();
    await page.getByTestId("intake-other-locations").fill("14");
    await page.getByTestId("intake-floor-area").fill("1800");
    await page.getByTestId("intake-licence-transfer_from_another_owner").click();
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toEqual({
      address: ADDRESS,
      description: DESCRIPTION,
      intake: { part_of_chain: true, other_locations: 14, floor_area_sqft: 1800, liquor_licence: "transfer_from_another_owner" },
    });
  });

  test("a chain answered no sends no count, and a skipped question is left out", async ({ page }) => {
    const posted = await routeApi(page);
    await page.goto("/dev/new-memo");
    await fillAddressAndConcept(page);
    await page.getByTestId("intake-chain-yes").click();
    await page.getByTestId("intake-other-locations").fill("5");
    await page.getByTestId("intake-chain-no").click();
    await page.getByTestId("intake-licence-none").click();
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].intake).toEqual({ part_of_chain: false, liquor_licence: "none" });
  });

  test("a skipped form sends no intake answers", async ({ page }) => {
    const posted = await routeApi(page);
    await page.goto("/dev/new-memo");
    await fillAddressAndConcept(page);
    // answer, then take the answer back: skipping is always possible
    await page.getByTestId("intake-licence-new").click();
    await page.getByTestId("intake-licence-skip").click();
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toEqual({ address: ADDRESS, description: DESCRIPTION });
    expect(Object.keys(posted[0])).not.toContain("intake");
  });

  test("a floor area that is not a whole number is refused before anything is sent", async ({ page }) => {
    const posted = await routeApi(page);
    await page.goto("/dev/new-memo");
    await fillAddressAndConcept(page);
    await page.getByTestId("intake-floor-area").fill("0");
    await page.getByTestId("memo-submit").click();
    await expect(page.getByTestId("memo-error")).toContainText("Enter the floor area as a whole number of square feet, or leave it blank.");
    expect(posted).toHaveLength(0);
  });

  test("a re-run link carries the answers and the memo starts with them", async ({ page }) => {
    const posted = await routeApi(page);
    const q = new URLSearchParams({ address: ADDRESS, description: DESCRIPTION, part_of_chain: "yes", floor_area_sqft: "1800", liquor_licence: "new" });
    await page.goto(`/dev/new-memo?${q.toString()}`);
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toEqual({ address: ADDRESS, description: DESCRIPTION, intake: { part_of_chain: true, floor_area_sqft: 1800, liquor_licence: "new" } });
  });

  test("a re-run link carries every kind of answer, and drops what is not one", async ({ page }) => {
    const posted = await routeApi(page);
    const q = new URLSearchParams({
      address: ADDRESS,
      description: DESCRIPTION,
      stories: "second,first,attic",
      alcohol_served: "beer_wine",
      closing_time: "01:30",
      last_use: "vacant", // not an answer: an empty space is asked what it was last used as
      fewer_than_50_people: "no",
      outdoor_area: "sidewalk",
      outdoor_alcohol_service: "yes",
      existing_business_change: "none",
      merges_storefronts: "no",
      amends_prior_approval: "maybe",
      entertainment: "limited_live_performance",
      existing_occupancy_group: "B",
    });
    await page.goto(`/dev/new-memo?${q.toString()}`);
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].intake).toEqual({
      stories: ["first", "second"],
      alcohol_served: "beer_wine",
      closing_time: "01:30",
      fewer_than_50_people: false,
      outdoor_area: "sidewalk",
      outdoor_alcohol_service: true,
      existing_business_change: "none",
      merges_storefronts: false,
      entertainment: "limited_live_performance",
      existing_occupancy_group: "B",
    });
  });

  test("a re-run link of an earlier-format memo sends rerun_of, and only while the address and concept are unchanged", async ({ page }) => {
    const posted = await routeApi(page);
    const LEGACY_ID = "aaaaaaaa-0000-4000-8000-0000000000a1";
    const q = new URLSearchParams({ address: ADDRESS, description: DESCRIPTION, rerun_of: LEGACY_ID });
    await page.goto(`/dev/new-memo?${q.toString()}`);
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toEqual({ address: ADDRESS, description: DESCRIPTION, rerun_of: LEGACY_ID });
    // the test stops the run; the form comes back with the same input, and sending it again is still the re-run
    await expect(page.getByTestId("memo-submit")).toBeVisible();
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(2);
    expect(posted[1]).toEqual({ address: ADDRESS, description: DESCRIPTION, rerun_of: LEGACY_ID });
    // a changed concept is a new memo: the API would run the earlier memo's own words, so rerun_of is not sent
    await page.locator("#memo-description").fill(`${DESCRIPTION}, sidewalk tables`);
    await page.getByTestId("memo-submit").click();
    await expect.poll(() => posted.length).toBe(3);
    expect(posted[2]).toEqual({ address: ADDRESS, description: `${DESCRIPTION}, sidewalk tables` });
  });
});
