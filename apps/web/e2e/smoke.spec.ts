import { expect, test, type Locator, type Route } from "@playwright/test";
import EVIDENCE from "../src/lib/fixtures/evidence-995-valencia.json";
import RULE_SET from "../src/lib/fixtures/determinations-995-valencia.json";
import { formatDate } from "../src/lib/format";
import { INTAKE_QUESTIONS } from "../src/lib/intake";
import {
  changeGroups,
  decisionTimeLines,
  groupRuleLines,
  HEADLINE_CONTINGENT,
  HEADLINE_DEFINITE,
  HEADLINE_HEADING,
  HEADLINE_HINT,
  LEGACY_PAID_NOTE,
  LEGACY_RERUN_USED_NOTE,
  rowRuleGroups,
  rulesDateLine,
  shownTriggers,
  statusNoteLine,
  timingCell,
  TRIGGER_CONTROL_LABELS,
  triggerGroups,
} from "../src/lib/memo";
import { SITE_CLAIM } from "../src/lib/site-copy";
import type { ApprovalArea, ComparableCase, CountedDecision, HeadlineFinding, MemoApprovalRow, MemoFact, OpenQuestion, Pathway, RuleLine } from "../src/lib/api-types";

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "authorization, content-type, accept",
  "access-control-allow-methods": "GET, POST, PATCH, DELETE, OPTIONS",
};

// What the API's rules (rule table v2) return for a 40-seat wine bar at 995 Valencia St, read from the file a
// test in the API generates and pins (src/lib/fixtures/determinations-995-valencia.json). The memo fixture takes
// every rule-set value from the same file, so the page must show these strings; none of them is typed here.
// The suite types only what the page itself adds (headings, the labels of a control or an answer) and the few
// facts about the example that the page must get right: each row's status and the input the alcohol row names.
interface RuleSet {
  pathway: Pathway;
  rows: Pick<MemoApprovalRow, "area" | "approval" | "agency" | "status" | "status_note" | "basis" | "referral_steps" | "missing_inputs">[];
  overall_status: string;
  overall_line: string;
  entitlement_path: string;
  open_questions: OpenQuestion[];
  headline_findings: HeadlineFinding[];
  facts: MemoFact[];
  row_facts: Partial<Record<ApprovalArea, MemoFact[]>>;
}
/** The records as they are: an active Type 41 licence at the address. */
const RULES = RULE_SET.with_licence as unknown as RuleSet;
/** The same address with no licence on file. */
const RULES_NO_LICENCE = RULE_SET.no_licence as unknown as RuleSet;
/** A wine bar at 1448 Pacific Ave, where the district's table does not permit a Bar. */
const RULES_NOT_PERMITTED = RULE_SET.not_permitted.determinations as unknown as RuleSet;

function ruleRow(rules: RuleSet, area: ApprovalArea) {
  const row = rules.rows.find((r) => r.area === area);
  if (!row) throw new Error(`the generated rule set has no ${area} row`);
  return row;
}
const texts = (lines: RuleLine[] | undefined) => (lines ?? []).map((l) => l.text);
/** The code sections a list of rule lines prints, one for each line that has one. */
const sections = (lines: RuleLine[]) => lines.flatMap((l) => (l.code_section ? [l.code_section] : []));
/** The lines the page prints under "Rules applied" for a row, in page order (the grouping keeps the API's order). */
function shownRuleLines(rules: RuleSet, area: ApprovalArea): RuleLine[] {
  return groupRuleLines(ruleRow(rules, area).basis, rowRuleGroups(area, rules.pathway)).flatMap((item) => (item.group ? item.group.lines : [item.line]));
}
const approvalRow = (scope: { locator: (selector: string) => Locator }, area: ApprovalArea) => scope.locator(`[data-testid="approval-row"][data-area="${area}"]`);

const OVERALL_LINE = RULES.overall_line;
// The entitlement path the rules write for the same case: the approvals to file, joined with "; ". A row that is
// Insufficient information adds no approval, so the ABC licence is not in it.
const ENTITLEMENT_PATH = RULES.entitlement_path;
// The statuses the rules give the five rows, in report order, and the one input the alcohol row names. The
// description gives no story and the rules assume none (decision of 2026-11-12), so the zoning row is Insufficient
// information and names the story.
const ROW_STATUSES = ["Insufficient information", "Insufficient information", "Further review", "Allowed", "Further review"];
const STORY_INPUT = "which stories the business occupies";
const LICENCE_INPUT = "how the liquor licence will be obtained (new, or a transfer from another owner or another location)";
// The page's own fixed words (src/lib/memo.ts).
const STEPS_HEADING = "Steps inside this approval";
const STEPS_NOTE =
  "These are review steps inside the approval, where one agency sends the application to another. They are not separate approvals.";
const CHANGE_QUESTIONS = ["Planning Code change of use", "Building Code change of occupancy", "Neighbourhood notification"];
// RECORDS_LIMITS in apps/api/app/models/memo.py: the one fixed line on every report.
const RECORDS_LIMITS =
  "Physical and cost issues are outside what public records can show: ventilation and kitchen exhaust, exits and occupant load, accessibility, the condition of the space, and the landlord's consent.";
// The comparable cases and the decisions counted, as the runner read them for the same case (evidence-995-valencia.json).
const COMPARABLES = EVIDENCE.comparable_cases as ComparableCase[];
const COUNTED = EVIDENCE.counted as CountedDecision[];
// The records date of the sample: a pending case is aged to it.
const DATA_AS_OF = "2026-11-09";
// What the full report must never show again: the writer's text and the marks of its citation check.
const WRITER_TEST_IDS = ["next-step", "citation-check", "approval-summary", "summary-note", "finding", "evidence-label", "trimmed-note", "downgrade-note", "verification-note", "expected-conditions", "playbook", "timeline-cost", "density-base-rate", "confidence-definition"];

const STAGE_MESSAGE = "Checking San Francisco Department of Public Health requirements…";
const PERMITS = [
  { id: "sf.health_permit", name: "Health Permit to Operate", category: "health", agency: "SF Department of Public Health", confidence: "verified" },
  { id: "ca.abc_type_42", name: "ABC Type 42 On-Sale Beer & Wine License", category: "alcohol", agency: "California ABC", confidence: "estimated" },
  { id: "sf.business_registration", name: "Business Registration Certificate", category: "business_registration", agency: "SF Office of the Treasurer & Tax Collector", confidence: "verified" },
] as const;

function sse(event: string, data: unknown): string {
  // Multi-line data on purpose: the client must join `data:` lines.
  const json = JSON.stringify(data, null, 1).split("\n");
  return `event: ${event}\n${json.map((l) => `data: ${l}`).join("\n")}\n\n`;
}

// Two licences the catalog leaves undetermined when the description does not say what is served (the API lists
// them after the permits that apply; `permit_count` counts the first kind only).
const NOT_DETERMINED = [
  { id: "ca.abc_type_42", name: "ABC Type 42 On-Sale Beer & Wine (Public Premises)", condition: "only beer and wine are served" },
  { id: "ca.abc_type_48", name: "ABC Type 48 On-Sale General (Public Premises)", condition: "spirits are served too" },
].map((p) => ({
  id: p.id,
  name: p.name,
  category: "alcohol",
  issuing_agency: "California Department of Alcoholic Beverage Control",
  jurisdiction_level: "state",
  confidence: "verified",
  typical_timeline_days: { min: 45, max: 90 },
  fee_range_usd: { min: 900, max: 15000 },
  why_required: `Not determined: applies if ${p.condition}. The description does not say what alcohol will be served: beer and wine, or spirits too.`,
}));

function previewBody(notDetermined: typeof NOT_DETERMINED = []): string {
  const profile = {
    business_type: "bar",
    business_name: null,
    city_name: "San Francisco",
    city_slug: "san_francisco",
    state: "CA",
    neighborhood: "Mission",
    seats: 40,
    square_feet: null,
    employees: null,
    hotel_rooms: null,
    serves_food: true,
    has_kitchen: true,
    cooking_type: "limited",
    serves_alcohol: true,
    alcohol_type: "beer_wine",
    closes_after_midnight: true,
    closes_after_2am: false,
    live_entertainment: true,
    amplified_sound: true,
    dancing: false,
    outdoor_seating: false,
    sidewalk_or_parklet: false,
    change_of_use: false,
    tenant_improvements: true,
    new_construction: false,
    exterior_signage: true,
    plays_recorded_music: true,
    mobile_vending: false,
    uses_commissary: false,
    sells_packaged_goods: false,
    target_open_date: null,
    assumptions: ["Assumed beer and wine only (no spirits) because you said wine bar."],
  };
  const permits = PERMITS.map((p) => ({
    id: p.id,
    name: p.name,
    category: p.category,
    issuing_agency: p.agency,
    jurisdiction_level: p.id.startsWith("ca.") ? "state" : "city",
    confidence: p.confidence,
    typical_timeline_days: { min: 14, max: 60 },
    fee_range_usd: { min: 250, max: 1200 },
    why_required: `Required because of the ${p.category.replace(/_/g, " ")} profile of a 40-seat wine bar.`,
  }));
  return [
    ": keep-alive comment that must be ignored\n\n",
    sse("stage", { stage: "triage", status: "completed", message: "Confirmed: a bar in San Francisco, CA", elapsed_ms: 420 }),
    sse("stage", { stage: "requirements", status: "started", message: STAGE_MESSAGE }),
    sse("tool", { stage: "requirements", tool: "lookup_permit_catalog", status: "completed", message: "Matched 3 catalog entries" }),
    sse("stage", { stage: "requirements", status: "completed", message: STAGE_MESSAGE, elapsed_ms: 1800 }),
    sse("preview", {
      preview_id: "prev_e2e_123",
      profile,
      city_supported: true,
      unsupported_city_note: null,
      permits: [...permits, ...notDetermined],
      permit_count: permits.length,
      estimated_total_days: { min: 45, max: 120 },
    }),
  ].join("");
}

async function fulfilPreview(route: Route, notDetermined: typeof NOT_DETERMINED = []) {
  const req = route.request();
  if (req.method() === "OPTIONS") {
    await route.fulfill({ status: 204, headers: CORS });
    return;
  }
  expect(req.method()).toBe("POST");
  expect(req.postDataJSON()).toMatchObject({ description: expect.stringContaining("wine bar") });
  await route.fulfill({
    status: 200,
    headers: { ...CORS, "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-cache" },
    body: previewBody(notDetermined),
  });
}

const GEOCODE_SUGGESTIONS = [
  { address: "2500 Mission St, San Francisco, CA 94110", normalized_address: "2500 MISSION ST", lat: 37.7565, lng: -122.4189, parcel: "3637/012", zip_code: "94110", confidence: 0.98 },
  { address: "2500 Mission St #2, San Francisco, CA 94110", normalized_address: "2500 MISSION ST 2", lat: 37.7565, lng: -122.4189, parcel: "3637/013", zip_code: "94110", confidence: 0.71 },
];

async function fulfilJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, headers: { ...CORS, "content-type": "application/json" }, body: JSON.stringify(body) });
}

test.describe("Permit Memo smoke — free permit checklist (/checklist)", () => {
  test("checklist page renders the hero and the description textarea", async ({ page }) => {
    await page.goto("/checklist");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Every permit, in the right order");
    await expect(page.getByRole("textbox", { name: "Describe your business" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Build my plan" })).toBeVisible();
    await expect(page.getByText("San Francisco", { exact: true }).first()).toBeVisible();
  });

  test("building a plan streams the preview and shows the auth gate", async ({ page }) => {
    let previewCalls = 0;
    await page.route("**/v1/preview", async (route) => {
      if (route.request().method() === "POST") previewCalls += 1;
      await fulfilPreview(route);
    });

    await page.goto("/checklist");
    await page.getByRole("textbox", { name: "Describe your business" }).fill("Opening a 40-seat wine bar in SF Mission, small kitchen, serve until 1am, maybe live music");
    await page.getByRole("button", { name: "Build my plan" }).click();

    const panel = page.getByTestId("preview-panel");
    await expect(panel).toBeVisible();
    await expect(panel.getByText(STAGE_MESSAGE).first()).toBeVisible();

    const results = page.getByTestId("preview-results");
    await expect(results).toBeVisible();
    for (const p of PERMITS) await expect(results.getByText(p.name, { exact: true })).toBeVisible();
    await expect(results.getByTestId("preview-permit")).toHaveCount(3);
    await expect(results.getByText("Verified", { exact: true })).toHaveCount(2);
    await expect(results.getByText("Estimated", { exact: true })).toHaveCount(1);

    const gate = page.getByTestId("auth-gate");
    await expect(gate).toBeVisible();
    await expect(gate.getByRole("link", { name: /Create a free account/ })).toHaveAttribute("href", /\/login\?next=/);

    expect(previewCalls).toBe(1);
    const pending = await page.evaluate(() => window.localStorage.getItem("pp_pending_preview"));
    expect(pending).toContain("prev_e2e_123");
    await expect(results.getByTestId("preview-not-determined")).toHaveCount(0);
  });

  test("a licence that depends on what is served is listed as not determined, apart from the permits", async ({ page }) => {
    await page.route("**/v1/preview", (route) => fulfilPreview(route, NOT_DETERMINED));
    await page.goto("/checklist");
    await page.getByRole("textbox", { name: "Describe your business" }).fill("Opening a 40-seat wine bar in SF Mission with drinks");
    await page.getByRole("button", { name: "Build my plan" }).click();
    const results = page.getByTestId("preview-results");
    await expect(results).toBeVisible();
    // the permits that apply are counted and listed as before; neither licence is picked
    await expect(results.getByTestId("preview-permit")).toHaveCount(3);
    await expect(results.getByText("Verified", { exact: true })).toHaveCount(2);
    const box = results.getByTestId("preview-not-determined");
    await expect(box).toContainText("Not determined yet");
    for (const p of NOT_DETERMINED) {
      await expect(box).toContainText(p.name);
      await expect(box).toContainText(p.why_required);
    }
    await expect(box).toContainText("what alcohol will be served: beer and wine, or spirits too");
  });

  test("visiting /app unauthenticated redirects to /login", async ({ page }) => {
    await page.goto("/app");
    await expect(page).toHaveURL(/\/login\?next=%2Fapp/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });
});

test.describe("Permit Memo smoke — Location Risk Memo", () => {
  test("landing shows the address hero and the autocomplete renders geocode suggestions", async ({ page }) => {
    const queries: string[] = [];
    await page.route("**/v1/geocode**", async (route) => {
      const req = route.request();
      if (req.method() === "OPTIONS") {
        await route.fulfill({ status: 204, headers: CORS });
        return;
      }
      expect(req.method()).toBe("GET");
      queries.push(new URL(req.url()).searchParams.get("q") ?? "");
      await fulfilJson(route, { suggestions: GEOCODE_SUGGESTIONS });
    });

    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(SITE_CLAIM);
    await expect(page.getByTestId("checklist-cta")).toHaveAttribute("href", "/checklist");
    await expect(page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Free permit checklist" })).toHaveAttribute("href", "/checklist");
    await expect(page.getByTestId("pricing")).toContainText("$499");
    await expect(page.getByTestId("pricing")).toContainText("$299");

    const address = page.getByRole("combobox", { name: "The address you are considering" });
    await expect(address).toBeVisible();
    await address.fill("2500 Mission");

    const list = page.getByTestId("address-suggestions");
    await expect(list).toBeVisible();
    await expect(list.getByRole("option")).toHaveCount(2);
    await expect(list.getByText("2500 Mission St, San Francisco, CA 94110", { exact: true })).toBeVisible();
    await expect(list.getByText("Parcel 3637/012", { exact: true })).toBeVisible();
    expect(queries.some((q) => q.includes("2500 Mission"))).toBe(true);

    // Keyboard: ArrowDown to the second option, Enter picks it.
    await address.press("ArrowDown");
    await address.press("Enter");
    await expect(address).toHaveValue("2500 Mission St #2, San Francisco, CA 94110");
    await expect(page.getByTestId("address-selected")).toContainText("Parcel 3637/013");
    await expect(list).toBeHidden();

    // Signed out: the input is kept and the visitor is sent to sign in for /memo.
    await page.getByRole("textbox", { name: "The concept" }).fill("40-seat wine bar, small kitchen, open until 1am, occasional live music");
    await page.getByTestId("hero-submit").click();
    await expect(page).toHaveURL(/\/login\?next=%2Fmemo/);
    const pending = await page.evaluate(() => window.localStorage.getItem("pp_pending_memo"));
    expect(pending).toContain("2500 Mission St #2");
    expect(pending).toContain("wine bar");
  });

  test("landing describes per-approval statuses, not a single verdict", async ({ page }) => {
    await page.goto("/");
    const memoSection = page.locator("#memo");
    await expect(memoSection).toContainText("Allowed, Further review, Potential blocker, Not permitted or Insufficient information");
    await expect(page.locator("main")).not.toContainText("Likely, Conditional or Unlikely");
    const sample = page.getByTestId("sample-memo");
    // The sample is the same example: its overall status and its first three rows, as the rules set them.
    await expect(sample.getByTestId("status-pill")).toHaveText(["Further review", ...ROW_STATUSES.slice(0, 3)]);
    await expect(sample).toContainText(OVERALL_LINE);
    await expect(sample).toContainText("Approvals this concept needs");
    await expect(sample).toContainText("N = 3");
    await expect(sample).not.toContainText("approval rate");

    // The sample shows the facts the rules read, each with the words that state it; no writer's text.
    await expect(sample).toContainText("Facts the rules read");
    await expect(sample).toContainText("Kind of business (Planning Code use): Bar");
    await expect(sample).toContainText("from your words “wine bar”");
    await expect(sample).not.toContainText("Expected conditions");
    await expect(sample).not.toContainText("days to approval");

    // The copy promises what format 3 delivers: rules with their code sections, facts with their source, no
    // sentence written by a model, and outcome counts with a rate only when the sample allows one.
    const main = page.locator("main");
    await expect(main).toContainText("No sentence in the report is written by an AI model.");
    await expect(main).toContainText("What your description does not say is listed as not known, never guessed.");
    await expect(main).toContainText("a rate appears only when the sample is 10 or more");
    for (const gone of ["Verified and Likely applicable", "filing playbook", "what to say", "Expected conditions", "evidence label"]) {
      await expect(main).not.toContainText(gone);
    }
    await expect(main).not.toContainText(/approval rate/i);
    await expect(page.locator('meta[property="og:description"]')).toHaveAttribute("content", new RegExp(`^${SITE_CLAIM.replace(/[.?]/g, "\\$&")} `));
  });

  test("landing, pricing and metadata make no approval prediction: the claim is the approvals, the rules and records, and what is unknown", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(SITE_CLAIM);
    await expect(page).toHaveTitle("Permit Memo — every approval your concept needs at an address");
    await expect(page.locator('meta[name="description"]')).toHaveAttribute("content", SITE_CLAIM);
    await expect(page.locator('meta[property="og:title"]')).toHaveAttribute("content", "Permit Memo — every approval your concept needs at an address");
    await expect(page.locator('meta[name="twitter:description"]')).toHaveAttribute("content", SITE_CLAIM);
    const body = page.locator("body");
    for (const gone of [
      /will (this address )?get approved/i,
      /before you sign the lease/i,
      /approval odds/i,
      /likely to be approved/i,
      /conditions to expect/i,
      /what to file/i,
      /verdict/i,
      /predict/i,
      /wrong lease/i,
      /would give you, with the receipts/i,
    ]) {
      await expect(body).not.toContainText(gone);
    }
    await expect(page.getByTestId("pricing")).toContainText("what is still unknown");
    // the free tier's teaser is the overall status, its reason and counts: no status per approval
    await expect(page.getByTestId("pricing")).toContainText("Memo teaser: the overall status, its one-line reason, and how many approvals, blockers and comparable cases");
    await expect(page.getByTestId("pricing")).not.toContainText(/status of each approval/i);
    // the free checklist page points to the memo with the same claim, not a prediction
    await page.goto("/checklist");
    await expect(page.locator("main")).toContainText("every approval your concept needs at that address, with the rules and records behind each, and what's still unknown.");
    await expect(page.locator("main")).not.toContainText(/whether it will be approved/i);
  });

  test("every report, teaser, full or earlier format, says near the top that it missed important issues in testing", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    for (const access of ["teaser", "full", "legacy"]) {
      await page.goto(`/dev/memo-preview?access=${access}`);
      const notice = page.getByTestId("testing-notice");
      await expect(notice).toHaveCount(1);
      await expect(notice).toHaveText(
        "In testing: checked against past cases, this report missed important issues in more than half of new cases. Use it as a starting point, not a conclusion.",
      );
      await expect(notice).toBeVisible();
      // above the overall status, where it is read before the report
      const box = await notice.boundingBox();
      const overall = page.getByTestId("overall-card");
      if (access !== "legacy") {
        const obox = await overall.boundingBox();
        expect(box!.y).toBeLessThan(obox!.y);
      }
    }
  });

  test("memo page (teaser) shows the overall status pill, the counts, the unlock card and no report body", async ({ page }) => {
    await page.goto("/dev/memo-preview?access=teaser");
    const view = page.getByTestId("memo-view");
    await expect(view).toHaveAttribute("data-access", "teaser");
    await expect(page.getByTestId("memo-address")).toHaveText("995 Valencia St, San Francisco, CA 94110");

    const pill = page.getByTestId("overall-card").getByTestId("status-pill");
    await expect(pill).toBeVisible();
    await expect(pill).toHaveText("Further review");
    // Shown as written, not in capitals (toHaveText reads the DOM text and would not see a CSS transform).
    await expect(pill).toHaveCSS("text-transform", "none");
    await expect(pill).toHaveAttribute("data-status", RULES.overall_status);
    await expect(pill).toHaveAttribute("data-status", "further_review");
    // The overall line is computed by rule: it names each row's status.
    await expect(page.getByTestId("overall-line")).toHaveText(OVERALL_LINE);
    await expect(page.getByTestId("teaser-counts")).toHaveText("10 comparable cases found · 5 approvals needed · 0 marked Potential blocker or Not permitted");

    const unlock = page.getByTestId("unlock-card");
    await expect(unlock).toBeVisible();
    await expect(unlock).toContainText("Unlock the full memo — $499 one-time or Pro $299/mo");
    // The teaser's overall line already names each row's status; the full memo adds the rules and the evidence.
    await expect(unlock).toContainText("the full memo adds the rules applied to each of the 5 approvals the concept needs, the facts the rules read and where each came from");
    await expect(unlock).not.toContainText("playbook");
    await expect(unlock).not.toContainText("conditions to expect");
    await expect(unlock).not.toContainText("adds the status");
    await expect(unlock.getByTestId("offer-memo")).toBeVisible();
    await expect(unlock.getByTestId("offer-pro")).toBeVisible();
    await expect(page.getByTestId("teaser-preview")).toBeVisible();

    // Everything past the overall line stays locked.
    await expect(page.getByTestId("entitlement-path")).toHaveCount(0);
    await expect(page.getByTestId("row-facts")).toHaveCount(0);
    await expect(page.getByTestId("facts")).toHaveCount(0);
    await expect(page.getByTestId("approval-row")).toHaveCount(0);
    await expect(page.getByTestId("missing-inputs")).toHaveCount(0);
    await expect(page.getByTestId("referral-steps")).toHaveCount(0);
    await expect(page.getByTestId("trigger")).toHaveCount(0);
    await expect(page.getByTestId("could-not-establish")).toHaveCount(0);
    await expect(page.getByTestId("records-limits")).toHaveCount(0);
    await expect(page.getByTestId("rules-date")).toHaveCount(0);
    await expect(page.getByTestId("site-history")).toHaveCount(0);
    await expect(page.getByTestId("site-history-row")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Site history", exact: true })).toHaveCount(0);
    await expect(page.getByTestId("comparables-table")).toHaveCount(0);
    await expect(page.getByTestId("comparable-row")).toHaveCount(0);
    await expect(page.getByTestId("citation-footnote")).toHaveCount(0);
    await expect(page.getByTestId("export-pdf")).toHaveCount(0);
    await expect(page.getByTestId("legacy-card")).toHaveCount(0);
  });

  test("memo page (teaser) shows nothing from a memo that arrives attached to a teaser record", async ({ page }) => {
    await page.goto("/dev/memo-preview?access=teaser&variant=memo-attached");
    await expect(page.getByTestId("memo-view")).toHaveAttribute("data-access", "teaser");
    await expect(page.getByTestId("access-badge")).toHaveText("Teaser");
    await expect(page.getByTestId("overall-line")).toHaveText(OVERALL_LINE);
    await expect(page.getByTestId("unlock-card")).toBeVisible();

    await expect(page.getByTestId("entitlement-path")).toHaveCount(0);
    await expect(page.getByTestId("facts")).toHaveCount(0);
    await expect(page.getByTestId("citation-refs")).toHaveCount(0);
    await expect(page.getByTestId("approval-row")).toHaveCount(0);
    await expect(page.getByTestId("referral-steps")).toHaveCount(0);
    await expect(page.getByTestId("records-limits")).toHaveCount(0);
    await expect(page.getByTestId("site-history")).toHaveCount(0);
    await expect(page.getByTestId("citation-footnote")).toHaveCount(0);
    await expect(page.getByTestId("export-pdf")).toHaveCount(0);
  });

  test("memo page (teaser, credit on account) offers an instant unlock", async ({ page }) => {
    await page.goto("/dev/memo-preview?access=teaser&me=credit");
    await expect(page.getByTestId("unlock-now")).toContainText("uses 1 of 1 memo credit");
    await expect(page.getByTestId("offer-memo")).toHaveCount(0);
  });

  test("memo page (full) renders the overall line, the approval rows with their rules and the facts they read, and what could not be established", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    await page.goto("/dev/memo-preview?access=full");

    await expect(page.getByTestId("memo-view")).toHaveAttribute("data-access", "full");
    await expect(page.getByTestId("memo-view")).toHaveAttribute("data-format", "3");
    await expect(page.getByTestId("access-badge")).toHaveText("Full memo");
    await expect(page.getByTestId("memo-address")).toHaveText("995 Valencia St, San Francisco, CA 94110");

    // The applicant's own words, quoted as sent: the report writes no summary of its own.
    await expect(page.getByTestId("memo-concept")).toHaveText("Your description: “40-seat wine bar, small kitchen, open until 1am, occasional live music”");
    // Overall: status pill, the computed line, and the approvals to file in order (set by rule). No next step
    // and no citation-check line: no model wrote anything to check.
    const overall = page.getByTestId("overall-card");
    await expect(overall.getByTestId("status-pill")).toHaveText("Further review");
    await expect(overall.getByTestId("overall-line")).toContainText(OVERALL_LINE);
    await expect(overall.getByTestId("entitlement-path")).toContainText("Approvals to file, in order");
    await expect(overall.getByTestId("entitlement-path")).toContainText(ENTITLEMENT_PATH);
    await expect(overall.getByTestId("entitlement-path")).not.toContainText("ABC licence, Type 42");
    for (const testId of WRITER_TEST_IDS) await expect(page.getByTestId(testId)).toHaveCount(0);
    await expect(page.getByTestId("memo-view")).not.toContainText("Recommended next step");
    // A full memo's header keeps the counts line (the API sends the teaser with every ready memo).
    await expect(overall.getByTestId("teaser-counts")).toHaveText("10 comparable cases found · 5 approvals needed · 0 marked Potential blocker or Not permitted");
    // There is no prose narrative any more.
    await expect(page.getByTestId("memo-narrative")).toHaveCount(0);
    await expect(page.getByTestId("blocking-issues")).toHaveCount(0);

    // One block per approval, in the API's order, with the status the rules set.
    const rows = page.getByTestId("approvals").getByTestId("approval-row");
    await expect(rows).toHaveCount(5);
    await expect(rows.getByTestId("status-pill")).toHaveText(ROW_STATUSES);
    // Every row lists the rules that set its status, and the page shows the approval and the agency the rules name.
    await expect(page.getByTestId("rules-applied")).toHaveCount(5);
    await expect(rows.getByTestId("approval-name")).toHaveText(RULES.rows.map((r) => r.approval));
    await expect(rows.getByTestId("approval-agency")).toHaveText(RULES.rows.map((r) => r.agency));
    for (const r of RULES.rows) await expect(approvalRow(page, r.area)).toHaveAttribute("data-status", r.status);

    // Zoning: the description gives no story. A Bar is a conditional use on the first story and not permitted
    // above it, and no story is assumed, so the row is Insufficient information and names the story first.
    const zoning = approvalRow(page, "zoning_use");
    await expect(zoning).toHaveAttribute("data-status", "insufficient_information");
    await expect(zoning.getByTestId("approval-name")).toHaveText("Use authorization (not decided: an input is missing)");
    await expect(zoning.getByTestId("approval-agency")).toHaveText("San Francisco Planning");
    const zoningRules = zoning.getByTestId("rules-applied");
    await expect(zoningRules).toContainText("Rules applied");
    // Every rule line of the row is printed once, in the API's order: the use, then each trigger's lines, then the
    // existing use and the change of use, then the line that sets the row's status.
    const zoningBasis = ruleRow(RULES, "zoning_use").basis;
    const zoningLines = zoningRules.getByTestId("rule-line");
    // every basis line, and the lines of the triggers listed that have none in the basis (those that do not apply)
    const listedOnly = shownTriggers(RULES.pathway)
      .filter((t) => !t.lines.some((l) => zoningBasis.some((b) => b.rule_id === l.rule_id && b.text === l.text)))
      .flatMap((t) => t.lines);
    await expect(zoningLines).toHaveCount(zoningBasis.length + listedOnly.length);
    await expect(zoningLines).toContainText(texts(zoningBasis));
    await expect(zoningLines.first()).toHaveText("The concept is looked up as a Bar (Planning Code § 102).");
    await expect(zoningLines.last()).toContainText("No story is assumed");
    await expect(zoningLines.last()).toContainText("already asks for a Conditional Use Authorization: insufficient information.");

    // Under the zoning row every trigger is named with its control, as the PDF lists them, and each that applies
    // holds its own lines. A trigger that does not apply shows "Does not apply".
    const shown = shownTriggers(RULES.pathway);
    expect(shown.map((t) => t.rule_id)).toEqual(["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11"]);
    const triggers = zoningRules.getByTestId("trigger");
    await expect(triggers).toHaveCount(shown.length);
    await expect(triggers.getByTestId("trigger-label")).toHaveText(shown.map((t) => t.label));
    await expect(triggers.getByTestId("trigger-label").first()).toHaveText("Use control of the zoning district");
    await expect(triggers.getByTestId("trigger-value")).toHaveText(shown.map((t) => TRIGGER_CONTROL_LABELS[t.control]));
    expect(shown.map((t) => TRIGGER_CONTROL_LABELS[t.control])).toContain("Asks for nothing");
    expect(shown.map((t) => TRIGGER_CONTROL_LABELS[t.control])).toContain("Does not apply");
    for (const t of shown) {
      const block = zoningRules.locator(`[data-testid="trigger"][data-key="${t.rule_id}"]`);
      await expect(block).toHaveAttribute("data-value", t.control);
    }
    // A trigger that is not decided says which input the description does not give.
    await expect(zoningRules.locator('[data-testid="trigger"][data-key="T5"]')).toContainText("The description does not say whether the business is part of a chain, so this is not decided.");
    // The zoning row is not decided, so it has a "Not given" list, the story first; it has no referral steps and
    // no status note.
    await expect(zoning.getByTestId("missing-input")).toHaveText(ruleRow(RULES, "zoning_use").missing_inputs ?? []);
    await expect(zoning.getByTestId("missing-input").first()).toHaveText(STORY_INPUT);
    await expect(zoning.getByTestId("referral-steps")).toHaveCount(0);
    await expect(zoning.getByTestId("status-note")).toHaveCount(0);
    // The three change-of-use answers belong to the building row; here the change-of-use lines stay plain lines.
    await expect(zoning.getByTestId("change-answer")).toHaveCount(0);

    // Each rule line names the code section it rests on once, linked where the API gives a URL, and cites its
    // records. A sentence that already names its section does not print the section a second time: the words in
    // the sentence carry the link (the PDF leaves the repeat off too).
    await expect(zoningRules.getByTestId("rule-section")).toHaveText(sections(shownRuleLines(RULES, "zoning_use")));
    const cell = zoningRules.locator('[data-testid="rule-line"][data-rule="T1.story"]');
    await expect(cell).toContainText(
      "Zoning district NCT-VALENCIA: the table sets a different control for a Bar on different stories. Which story the business is on is not given, so no story is assumed and this is not decided until it is (Planning Code § 762",
    );
    await expect(zoningRules).not.toContainText(/first story/i);
    await expect(cell.getByTestId("rule-section")).toHaveCount(1);
    await expect(cell).not.toContainText(/§ 762.*§ 762/);
    await expect(cell.getByTestId("rule-section").getByRole("link")).toHaveAttribute("href", zoningBasis.find((l) => l.rule_id === "T1.story")?.source_url ?? "missing");
    await expect(cell.getByTestId("citation-refs")).toHaveCount(1);
    await expect(zoningLines.first().getByTestId("rule-section")).toHaveCount(1);
    await expect(zoningLines.first()).not.toContainText(/§ 102.*§ 102/);
    await expect(zoningLines.first().getByTestId("rule-section").getByRole("link")).toHaveCount(0);
    await expect(zoningLines.first().getByTestId("citation-refs")).toHaveCount(0);
    // the status line that names what is missing rests on no one section and prints none
    await expect(zoningLines.last().getByTestId("rule-section")).toHaveCount(0);
    // After the rules, the facts they read: each with its value and where it came from. The applicant's words
    // that state a fact are quoted; a fact from a record cites it.
    const zoningFacts = zoning.getByTestId("row-facts");
    await expect(zoningFacts).toContainText("Facts the rules read");
    await expect(zoning.locator('[data-testid="rules-applied"] ~ [data-testid="row-facts"]')).toHaveCount(1);
    const wantFacts = RULES.row_facts.zoning_use ?? [];
    expect(wantFacts.length).toBeGreaterThan(0);
    await expect(zoningFacts.getByTestId("row-fact")).toHaveCount(wantFacts.length);
    await expect(zoningFacts.getByTestId("fact-value")).toHaveText(wantFacts.map((f) => f.value ?? "Not known"));
    const closing = zoningFacts.locator('[data-fact="closing"]');
    await expect(closing.getByTestId("fact-value")).toHaveText("After midnight");
    await expect(closing.getByTestId("fact-origin")).toHaveText("Worked out by the rules from your description: open until 1am");
    await expect(closing.getByTestId("fact-quote")).toHaveText("open until 1am");
    const existing = zoningFacts.locator('[data-fact="existing_use_records"]');
    await expect(existing).toHaveAttribute("data-origin", "record");
    await expect(existing.getByTestId("fact-value")).toHaveText("Restaurant");
    await expect(existing.getByTestId("fact-origin")).toHaveText("Records on file at this address");
    await expect(existing.getByTestId("citation-refs")).toHaveCount(1);
    await expect(zoning.getByTestId("status-pill")).toHaveCount(1);

    // Alcohol: the description does not say how the licence is to be obtained, so the row is Insufficient
    // information and names that input. Nothing is assumed in its place.
    const alcohol = approvalRow(page, "alcohol");
    const alcoholRules = ruleRow(RULES, "alcohol");
    await expect(alcohol).toHaveAttribute("data-status", "insufficient_information");
    await expect(alcohol.getByTestId("status-pill")).toHaveText("Insufficient information");
    await expect(alcohol.getByTestId("approval-area")).toHaveText("Alcohol licence");
    await expect(alcohol.getByTestId("approval-name")).toHaveText("ABC licence, Type 42 (on-sale beer and wine, public premises)");
    await expect(alcohol.getByTestId("approval-agency")).toHaveText("California Department of Alcoholic Beverage Control");
    const notGiven = alcohol.getByTestId("missing-inputs");
    await expect(notGiven).toContainText("Not given");
    expect(alcoholRules.missing_inputs).toEqual([LICENCE_INPUT]);
    await expect(notGiven.getByTestId("missing-input")).toHaveText([LICENCE_INPUT]);
    // The list sits between the status and the rules.
    await expect(alcohol.locator('[data-testid="missing-inputs"] ~ [data-testid="rules-applied"]')).toHaveCount(1);
    // "Not given" is printed only on the rows that lack an input: zoning and alcohol.
    await expect(page.getByTestId("missing-inputs")).toHaveCount(2);
    const alcoholLines = alcohol.getByTestId("rules-applied").getByTestId("rule-line");
    await expect(alcoholLines).toHaveCount(alcoholRules.basis.length);
    await expect(alcoholLines).toContainText(texts(alcoholRules.basis));
    await expect(alcoholLines.last()).toContainText(`The description does not give ${LICENCE_INPUT}, so the rules cannot say which licence rules apply: insufficient information.`);
    // The district's licence requirement and the census-tract count are still printed.
    await expect(alcohol.getByTestId("rules-applied")).toContainText("A new Bar must use a liquor licence transferred from another Bar located inside the district.");
    await expect(alcohol.getByTestId("rules-applied")).toContainText("Census tract 208.01");
    await expect(alcohol.getByTestId("rules-applied").getByTestId("rule-section")).toHaveText(sections(alcoholRules.basis));
    // A rule line without a code section shows none.
    await expect(alcoholLines.last().getByTestId("rule-section")).toHaveCount(0);
    // Triggers are listed under the zoning row only.
    await expect(alcohol.getByTestId("trigger")).toHaveCount(0);
    // The referral steps inside the approval: a heading, one line saying what they are, and the steps. They are
    // not rule lines of the basis, and they come after the facts the rules read.
    const alcoholSteps = alcohol.getByTestId("referral-steps");
    await expect(alcoholSteps).toContainText(STEPS_HEADING);
    await expect(alcoholSteps.getByTestId("referral-steps-note")).toHaveText(STEPS_NOTE);
    await expect(alcoholSteps.getByTestId("referral-step")).toHaveCount(2);
    await expect(alcoholSteps.getByTestId("referral-step")).toContainText(texts(alcoholRules.referral_steps));
    await expect(alcoholSteps.getByTestId("referral-step").first()).toContainText("this application is sent to the Police Department (ABC Liaison Unit) for review");
    await expect(alcoholSteps.getByTestId("rule-line")).toHaveCount(0);
    await expect(alcohol.getByTestId("rules-applied").getByTestId("referral-step")).toHaveCount(0);
    await expect(alcohol.locator('[data-testid="row-facts"] ~ [data-testid="referral-steps"]')).toHaveCount(1);
    // The facts the alcohol rules read: what is poured, the licence type it gives, and the licence on file here.
    await expect(alcohol.getByTestId("row-fact").getByTestId("fact-value")).toHaveText((RULES.row_facts.alcohol ?? []).map((f) => f.value ?? "Not known"));
    await expect(alcohol.locator('[data-testid="row-fact"][data-fact="alcohol_served"]')).toContainText("Your description: wine bar");
    await expect(alcohol.locator('[data-testid="row-fact"][data-fact="active_licences"]').getByTestId("citation-refs")).toHaveCount(1);
    // What the description does not give is not a fact of the row: it is the row's "Not given" list.
    await expect(alcohol.locator('[data-testid="row-fact"][data-fact="alcohol_transaction"]')).toHaveCount(0);
    await expect(alcohol.getByTestId("history-note")).toHaveText("No outcome history for this pathway yet.");
    // Only the alcohol and entertainment rows carry the history note.
    await expect(page.getByTestId("history-note")).toHaveCount(2);

    // Entertainment: an explanation the records do not support at all is replaced by the API's line; the note says why.
    const entertainment = approvalRow(page, "entertainment");
    const entertainmentRules = ruleRow(RULES, "entertainment");
    await expect(entertainment).toHaveAttribute("data-status", "further_review");
    await expect(entertainment.getByTestId("approval-name")).toHaveText("Place of Entertainment, Limited Live Performance or Fixed Place Outdoor Amplified Sound permit");
    await expect(entertainment.getByTestId("rule-line")).toHaveCount(1);
    await expect(entertainment.getByTestId("rule-line")).toContainText("Where a permit is needed: further review.");
    await expect(entertainment.getByTestId("rules-applied").getByTestId("rule-section")).toHaveText("San Francisco Police Code § 1060 et seq. (Place of Entertainment; Limited Live Performance; Fixed Place Outdoor Amplified Sound)");
    await expect(entertainment.locator('[data-testid="row-fact"][data-fact="entertainment_described"]')).toContainText("Live music or performance");
    await expect(entertainment.locator('[data-testid="row-fact"][data-fact="entertainment_described"]').getByTestId("fact-quote")).toHaveText("occasional live music");
    // Ten referral steps, among them steps that have ended. A step that ended does not remove the permit: the
    // row is still Further review and the step's own sentence says the permit is still required.
    const entertainmentSteps = entertainment.getByTestId("referral-step");
    await expect(entertainmentSteps).toHaveCount(10);
    await expect(entertainmentSteps).toContainText(texts(entertainmentRules.referral_steps));
    await expect(entertainmentSteps.filter({ hasText: "That step has ended. The permit is still required." })).toHaveCount(texts(entertainmentRules.referral_steps).filter((t) => t.includes("That step has ended.")).length);
    await expect(entertainmentSteps.filter({ hasText: "until 16 August 2025 this application was also sent to the Department of Building Inspection" })).toHaveCount(1);
    await expect(entertainment.getByTestId("referral-steps-note")).toHaveText(STEPS_NOTE);
    // A step names its code section once, as a link to where it was read.
    await expect(entertainmentSteps.first().getByTestId("rule-section")).toHaveText("Police Code § 1060.2(b)(1); § 1060.5(a)");
    await expect(entertainmentSteps.first().getByTestId("rule-section").getByRole("link")).toHaveAttribute("href", entertainmentRules.referral_steps?.[0]?.source_url ?? "missing");

    // Health: Allowed, with one rule line, one referral step and no marks.
    const health = approvalRow(page, "health");
    await expect(health).toHaveAttribute("data-status", "allowed");
    await expect(health.getByTestId("approval-name")).toHaveText("Health permit to operate");
    await expect(health.getByTestId("rule-line")).toHaveCount(1);
    await expect(health.getByTestId("rule-line")).toContainText("issued after plan check and inspection without a hearing: allowed.");
    await expect(health.getByTestId("referral-step")).toHaveCount(1);
    await expect(health.getByTestId("referral-step")).toContainText(texts(ruleRow(RULES, "health").referral_steps));
    await expect(health.getByTestId("row-fact")).toHaveCount((RULES.row_facts.health ?? []).length);

    // Building: Further review because Restaurant to Bar is a change of use. Change of use is three separate
    // answers, each on its own line with its own rule lines, in a fixed order.
    const building = approvalRow(page, "building_change_of_use");
    const changes = RULES.pathway.changes;
    if (!changes) throw new Error("the generated pathway has no change-of-use answers");
    await expect(building).toHaveAttribute("data-status", "further_review");
    await expect(building.getByTestId("approval-name")).toHaveText("Building permit with change of use");
    await expect(building.getByTestId("approval-agency")).toHaveText("San Francisco Department of Building Inspection");
    const answers = building.getByTestId("rules-applied").getByTestId("change-answer");
    await expect(answers).toHaveCount(3);
    await expect(answers.getByTestId("change-answer-label")).toHaveText(CHANGE_QUESTIONS);
    await expect(answers.getByTestId("change-answer-value")).toHaveText(["Yes", "Not established", "Not required"]);
    await expect(answers.nth(0)).toHaveAttribute("data-value", changes.planning_use);
    await expect(answers.nth(1)).toHaveAttribute("data-value", changes.building_occupancy);
    await expect(answers.nth(2)).toHaveAttribute("data-value", changes.neighbourhood_notice);
    await expect(answers.nth(0).getByTestId("rule-line")).toContainText(texts(changes.planning_use_lines));
    await expect(answers.nth(1).getByTestId("rule-line")).toContainText(texts(changes.building_occupancy_lines));
    await expect(answers.nth(2).getByTestId("rule-line")).toContainText(texts(changes.neighbourhood_notice_lines));
    await expect(answers.nth(0)).toContainText("Restaurant to Bar is a change of use.");
    await expect(answers.nth(1)).toContainText("A change of occupancy is not established.");
    // The row's own rule lines are all there, once each, and the line that sets the status comes last.
    const buildingLines = building.getByTestId("rules-applied").getByTestId("rule-line");
    const buildingShown = shownRuleLines(RULES, "building_change_of_use");
    await expect(buildingLines).toHaveCount(buildingShown.length);
    await expect(buildingLines).toContainText(texts(buildingShown));
    expect(buildingShown.length).toBe(ruleRow(RULES, "building_change_of_use").basis.length + changes.neighbourhood_notice_lines.length);
    await expect(buildingLines.last()).toContainText("A change of use needs a building permit, and the permit must conform to the Planning Code before it is issued: further review.");
    await expect(building.getByTestId("referral-step")).toHaveCount(1);
    await expect(building.getByTestId("referral-step")).toContainText("this application is sent to the Planning Department for review (Planning Code § 175(a)).");
    await expect(building.locator('[data-testid="row-fact"][data-fact="seats"]')).toContainText("40");

    // The referral steps on the page are the generated ones, row by row, and none of them is counted as an approval.
    await expect(page.getByTestId("referral-steps")).toHaveCount(RULES.rows.filter((r) => (r.referral_steps ?? []).length > 0).length);
    await expect(page.getByTestId("referral-step")).toHaveCount(RULES.rows.reduce((n, r) => n + (r.referral_steps ?? []).length, 0));
    await expect(rows).toHaveCount(5);

    // Every row lists the facts its rules read, and nothing on the page says a status was changed.
    await expect(page.getByTestId("row-facts")).toHaveCount(5);
    await expect(page.getByTestId("status-reset-note")).toHaveCount(0);
    // No row of this report carries a status note; the rules date is printed, as the PDF prints it.
    expect(RULES.rows.filter((r) => r.status_note)).toHaveLength(0);
    await expect(page.getByTestId("status-note")).toHaveCount(0);
    await expect(page.getByTestId("rules-date")).toHaveCount(1);

    // Could not establish: the rules' own questions only, one for each input the description does not give,
    // grouped by what would settle it. No question a model wrote.
    const unknowns = page.getByTestId("could-not-establish");
    const needs = Array.from(new Set(RULES.open_questions.map((q) => q.needs)));
    await expect(unknowns.getByTestId("open-question-group")).toHaveCount(needs.length);
    await expect(unknowns.getByTestId("open-question")).toHaveCount(RULES.open_questions.length);
    for (const q of RULES.open_questions) await expect(unknowns).toContainText(q.question);
    await expect(unknowns).toContainText(`Not known: ${LICENCE_INPUT}. Needed for: alcohol licence.`);
    await expect(unknowns).not.toContainText("ABC San Francisco district office");
    // One fixed line on what public records cannot show, in the same section.
    await expect(unknowns.getByTestId("records-limits")).toHaveText(RECORDS_LIMITS);
    await expect(page.getByTestId("records-limits")).toHaveCount(1);

    // What the rules read: every fact, the known ones first with where each came from, then the ones nothing gave.
    const facts = page.getByTestId("facts");
    await expect(page.getByRole("heading", { level: 2, name: "What the rules read", exact: true })).toBeVisible();
    await expect(facts.getByTestId("facts-description")).toContainText("40-seat wine bar, small kitchen, open until 1am, occasional live music");
    const known = RULES.facts.filter((f) => f.value !== null);
    const notKnown = RULES.facts.filter((f) => f.value === null);
    expect(notKnown.length).toBeGreaterThan(0);
    await expect(facts.getByTestId("facts-known").getByTestId("fact")).toHaveCount(known.length);
    await expect(facts.getByTestId("facts-unknown").getByTestId("fact")).toHaveCount(notKnown.length);
    await expect(facts.getByTestId("facts-unknown").getByTestId("fact-value")).toHaveText(notKnown.map(() => "Not known"));
    await expect(facts.locator('[data-fact="seats"]').getByTestId("fact-origin")).toHaveText("Your description: 40-seat");
    await expect(facts.locator('[data-fact="alcohol_transaction"]')).toHaveAttribute("data-origin", "not_known");
    await expect(facts.locator('[data-fact="alcohol_transaction"]').getByTestId("fact-origin")).toHaveCount(0);

    // How to read this report: the status definitions come from the memo itself. There are no evidence labels.
    const howTo = page.getByTestId("how-to-read");
    await expect(howTo.getByTestId("status-definition")).toHaveCount(5);
    await expect(howTo.getByTestId("status-definition").getByTestId("status-pill")).toHaveText(["Allowed", "Further review", "Potential blocker", "Not permitted", "Insufficient information"]);
    await expect(howTo).toContainText("available as of right");
    await expect(howTo).not.toContainText("Verified");

    // A [n] superscript on the overall line resolves to a footnote and scrolls to it.
    const footnotes = page.getByTestId("citation-footnote");
    expect(await footnotes.count()).toBeGreaterThanOrEqual(1);
    await expect(footnotes.first()).toContainText("[1]");
    const firstRef = page.getByTestId("overall-line").getByTestId("citation-refs").getByRole("link").first();
    await expect(firstRef).toHaveAttribute("href", /#cite-\d+/);
    await firstRef.click();
    await expect(page).toHaveURL(/#cite-\d+$/);

    await expect(page.getByTestId("export-pdf")).toBeVisible();
    await expect(page.getByTestId("unlock-card")).toHaveCount(0);
    await expect(page.getByTestId("legacy-card")).toHaveCount(0);
  });

  test("memo page (full) prints the rules date whenever the pathway carries one, whatever day the report was generated", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    // The same report generated two days after its rules date, as a backtest report is.
    await page.goto("/dev/memo-preview?access=full&variant=rules-date");
    const rulesDate = RULES.pathway.rules_date;
    if (!rulesDate) throw new Error("the generated pathway has no rules date");
    await expect(page.getByTestId("rules-date")).toHaveCount(1);
    await expect(page.getByTestId("rules-date")).toHaveText(`Rules applied as of ${formatDate(rulesDate)}`);
    await expect(page.getByTestId("rules-date")).toHaveText(/^Rules applied as of [A-Z][a-z]{2} \d{1,2}, \d{4}$/);
    // Nothing else changes: the statuses are the rules' own.
    await expect(page.getByTestId("approvals").getByTestId("approval-row").getByTestId("status-pill")).toHaveText(ROW_STATUSES);

    // Generated on the rules date: the same line (the two dates are on different clocks and are not compared).
    await page.goto("/dev/memo-preview?access=full");
    await expect(page.getByTestId("memo-view")).toHaveAttribute("data-access", "full");
    await expect(page.getByTestId("rules-date")).toHaveText(`Rules applied as of ${formatDate(rulesDate)}`);
  });

  test("memo page (full) prints a status note after the status, and the note does not change the status", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    // No generated case carries a status note, so this note is typed in the URL to check how one is drawn. It is
    // the contract's own example (MemoApprovalRow.status_note); the preview's banner says it is not rule output.
    const note = "Code and Planning practice differ";
    await page.goto(`/dev/memo-preview?access=full&status_note=${encodeURIComponent(note)}`);
    await expect(page.getByTestId("dev-banner")).toContainText("it is not rule output");
    const zoning = approvalRow(page, "zoning_use");
    await expect(zoning.getByTestId("status-note")).toHaveText(`Insufficient information: ${note}`);
    await expect(zoning.getByTestId("status-note")).toBeVisible();
    // The pill and the row's status are unchanged, and the note comes after the pill.
    await expect(zoning.getByTestId("status-pill")).toHaveText("Insufficient information");
    await expect(zoning).toHaveAttribute("data-status", "insufficient_information");
    await expect(zoning.locator('[data-testid="status-pill"] + [data-testid="status-note"]')).toHaveCount(1);
    await expect(page.getByTestId("approvals").getByTestId("approval-row").getByTestId("status-pill")).toHaveText(ROW_STATUSES);
    await expect(page.getByTestId("overall-card").getByTestId("status-pill")).toHaveText("Further review");
    // Only that row has one.
    await expect(page.getByTestId("status-note")).toHaveCount(1);
  });

  test("memo page (full) for a report stored before rule table v2 prints its rule lines as they are and none of the new blocks", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    await page.goto("/dev/memo-preview?access=full&variant=before-v2");

    const rows = page.getByTestId("approvals").getByTestId("approval-row");
    await expect(rows).toHaveCount(5);
    await expect(rows.getByTestId("status-pill")).toHaveText(ROW_STATUSES);
    await expect(page.getByTestId("rules-applied")).toHaveCount(5);
    // With no triggers and no change-of-use answers on the pathway, each row's rule lines are a plain list in
    // the API's order: nothing is dropped and nothing is grouped.
    for (const r of RULES.rows) {
      const lines = approvalRow(page, r.area).getByTestId("rule-line");
      await expect(lines).toHaveCount(r.basis.length);
      await expect(lines).toContainText(texts(r.basis));
    }
    for (const testId of ["trigger", "change-answer", "missing-inputs", "referral-steps", "status-note", "records-limits", "rules-date"]) {
      await expect(page.getByTestId(testId)).toHaveCount(0);
    }
    await expect(page.getByTestId("memo-view")).not.toContainText(STEPS_HEADING);
    await expect(page.getByTestId("memo-view")).not.toContainText("Rules applied as of");
    // The rest of the report is unchanged.
    await expect(page.getByTestId("pathway").getByTestId("pathway-fact")).toHaveCount(5);
    await expect(page.getByTestId("could-not-establish").getByTestId("open-question")).toHaveCount(RULES.open_questions.length);
    await expect(page.getByTestId("row-facts")).toHaveCount(5);
  });

  test("memo page (full) shows the pathway the rules looked up, and the building row agrees with it", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    await page.goto("/dev/memo-preview?access=full");

    const panel = page.getByTestId("zoning-panel");
    const pathway = panel.getByTestId("pathway");
    await expect(pathway).toContainText("Pathway for this concept");
    await expect(pathway.getByTestId("pathway-fact")).toHaveCount(5);
    const fact = (key: string) => pathway.locator(`[data-fact="${key}"]`);
    await expect(fact("use").locator("dt")).toHaveText("Proposed use");
    await expect(fact("use").locator("dd")).toHaveText("Bar");
    await expect(fact("district").locator("dd")).toHaveText("NCT-VALENCIA");
    await expect(fact("permission").locator("dt")).toHaveText("Control on a new use");
    // No story is given and none is assumed, so the control on a new use is not decided.
    await expect(fact("permission").locator("dd")).toHaveText("Not decided by the rules");
    await expect(fact("existing_use").locator("dd")).toHaveText("Restaurant");
    await expect(fact("change_of_use").locator("dd")).toHaveText("Change of use");
    await expect(pathway).toHaveAttribute("data-permission", "not_covered");
    await expect(pathway).toHaveAttribute("data-change-of-use", "yes");
    // The same facts as the generated pathway carries them.
    await expect(fact("use").locator("dd")).toHaveText(RULES.pathway.use_label);
    await expect(fact("district").locator("dd")).toHaveText(RULES.pathway.district ?? "missing");
    await expect(fact("permission").locator("dd")).toHaveText(RULES.pathway.permission_label);
    await expect(fact("change_of_use").locator("dd")).toHaveText(RULES.pathway.change_of_use_label);

    // The notes on file that the rules do not evaluate, each with its code section and citation.
    const notes = pathway.getByTestId("pathway-notes");
    await expect(notes).toContainText("Notes on file, not evaluated by the rules");
    await expect(notes.getByTestId("rule-line")).toHaveCount(2);
    // The API starts every note with "Note on file, not evaluated by the rules:". The heading already says so,
    // so the lines under it start with the record's own text.
    await expect(notes.getByTestId("rule-line").first()).toContainText("Bar requires Conditional Use Authorization; Restaurant principally permitted (First and Second Story).");
    await expect(notes.getByTestId("rule-line").nth(1)).toContainText("No new Liquor Stores.");
    await expect(notes.getByTestId("rule-line").first()).not.toContainText("Note on file");
    await expect(notes.getByTestId("rule-line").nth(1)).not.toContainText("Note on file");
    await expect(notes.getByTestId("rule-section")).toHaveText(["Planning Code § 762", "Planning Code § 249.60"]);
    await expect(notes.getByTestId("citation-refs")).toHaveCount(2);

    // One answer, two places: the pathway says change of use, so the building row is Further review and its
    // first change-of-use answer is Yes, and the zoning row's status follows the control on a new use (not
    // decided: the story is not given).
    await expect(page.locator('[data-testid="approval-row"][data-area="building_change_of_use"]')).toHaveAttribute("data-status", "further_review");
    await expect(page.locator('[data-testid="approval-row"][data-area="building_change_of_use"]').locator('[data-testid="change-answer"][data-key="planning_use"]')).toHaveAttribute("data-value", "yes");
    await expect(page.locator('[data-testid="approval-row"][data-area="zoning_use"]')).toHaveAttribute("data-status", "insufficient_information");

    // The district block under it shows the control table as the API sends it ("conditional", "principal").
    await expect(panel).toContainText("Valencia Street Neighborhood Commercial Transit District");
    await expect(panel).toContainText("Bar Conditional use");
    await expect(panel).toContainText("Restaurant Permitted");
    await expect(panel).toContainText("Planning Code § 762 (Zoning Control Table 762); § 102 (Bar, Restaurant) · Parcel 3609/026");
    await expect(panel).not.toContainText("Planning Code Planning Code");
    await expect(panel).toContainText("Mission Alcoholic Beverage Special Use District");
  });

  test("memo page (full) renders the comparables of the fixed ranking with their recorded facts, source notes, counts with each decision counted, and the map", async ({ page }) => {
    // Keep the suite offline: OSM tiles are not needed for the container to render.
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    await page.goto("/dev/memo-preview?access=full");

    // How the cases were chosen is the API's own fixed line: a fixed score, no model.
    const section = page.locator('section[aria-labelledby="sec-comparables"]');
    await expect(section).toContainText("ranked by a fixed score");
    await expect(section).toContainText("No model picks them.");

    const table = page.getByTestId("comparables-table");
    await expect(table).toBeVisible();
    await expect(table.getByRole("columnheader", { name: "Days from filing" })).toBeVisible();
    await expect(table.getByRole("columnheader", { name: "Source" })).toBeVisible();
    await expect(table.getByRole("columnheader", { name: "Conditions" })).toBeVisible();
    // The opposition column stays hidden while the API withholds the flag.
    await expect(table.getByRole("columnheader", { name: "Opposition" })).toHaveCount(0);
    await expect(table.getByTestId("comparable-row")).toHaveCount(COMPARABLES.length);
    expect(COMPARABLES).toHaveLength(10);
    await expect(table.getByTestId("comparable-days")).toHaveText(COMPARABLES.map((c) => timingCell(c, DATA_AS_OF)));
    await expect(table.getByTestId("comparable-source")).toHaveText(COMPARABLES.map((c) => c.source_label));
    // Each comparable links to its record; nothing a model wrote about it is shown.
    await expect(table.getByRole("link", { name: /datasf_planning:2026-005475MIS/ })).toHaveAttribute("href", "https://sfplanninggis.org/pim?search=2026-005475MIS");
    for (const gone of ["Why comparable", "Takeaway"]) await expect(table).not.toContainText(gone);
    await expect(page.getByTestId("data-gaps")).toHaveCount(0);
    // The conditions on file are listed as the record states them, behind a disclosure; a dash where the source has none.
    const withConditions = COMPARABLES.filter((c) => c.conditions.length > 0);
    expect(withConditions).toHaveLength(1);
    const conditions = table.getByTestId("record-conditions");
    await expect(conditions).toHaveCount(1);
    await expect(conditions.locator("summary")).toHaveText("1 condition on file");
    await conditions.locator("summary").click();
    await expect(conditions.getByRole("listitem")).toHaveText(withConditions[0].conditions);
    await expect(table.getByTestId("comparable-conditions").filter({ hasText: "–" })).toHaveCount(COMPARABLES.length - 1);
    // Each comparable says what kind of record it is, under its source, for the two pathway kinds only.
    await expect(table.getByTestId("comparable-kind")).toHaveCount(COMPARABLES.filter((c) => c.record_kind === "use_decision" || c.record_kind === "agency_referral").length);
    // Under the table, the figures by outcome: never one figure across outcomes, never an average.
    const times = page.getByTestId("decision-times");
    await expect(times).toContainText("Days from filing, by outcome");
    await expect(times.getByRole("listitem")).toHaveText(decisionTimeLines(COMPARABLES, DATA_AS_OF));

    const notes = page.getByTestId("source-notes");
    await expect(notes).toContainText("What each source leaves out");
    await expect(notes.getByTestId("source-note")).toHaveCount(4);
    await expect(notes).toContainText("Entertainment Commission permit list (DataSF)");
    await expect(notes).toContainText("cannot show that an application failed");

    // rate_shown is false in the fixture: counts with N, and no percentage anywhere in the block. No density tiles.
    const counts = page.getByTestId("outcome-counts");
    await expect(page.getByTestId("density-base-rate")).toHaveCount(0);
    await expect(counts).not.toContainText("within 500 ft");
    await expect(counts).toContainText("Withdrawn or cancelled 2");
    await expect(counts.getByTestId("base-rate")).toHaveAttribute("data-rate-shown", "false");
    await expect(counts.getByTestId("base-rate-n")).toHaveText("N = 3");
    // Records that are not use decisions are listed with the other counts left out, in the API's order. Nothing
    // here is undated, so that count is not listed.
    await expect(counts.getByTestId("base-rate-excluded")).toHaveText(
      "Not counted: 74 grant-only records (Entertainment Commission permits, ABC licences); 321 not use decisions (referrals, building work and other records).",
    );
    // The API's scope ends with "; left out: 74 permits and licences, 321 records that are not use decisions for
    // this kind of business". The heading drops that tail, so the counts are printed once, on the "Not counted" line.
    await expect(counts.getByTestId("base-rate-scope")).toContainText("Outcome counts · N = 3 dated decisions within 1,000 ft, last 10 years (fewer than 5 in the last 5); too few for a rate");
    await expect(counts.getByTestId("base-rate-scope")).not.toContainText("left out");
    // Each decision counted, with its link: N of them.
    const counted = counts.getByTestId("counted-decisions");
    await expect(counted.locator("summary")).toHaveText("The decisions counted (3)");
    await counted.locator("summary").click();
    await expect(counted.getByTestId("counted-decision")).toHaveCount(COUNTED.length);
    await expect(counted.getByTestId("counted-decision").getByRole("link")).toHaveText(COUNTED.map((d) => d.application_id));
    await expect(counted.getByTestId("counted-decision").first()).toContainText("2575 MISSION ST 94110");
    await expect(counted.getByTestId("counted-decision").first()).toContainText("Cancelled");
    // The citation keeps the API's full text.
    await expect(page.getByTestId("citation-footnote").filter({ hasText: "stat:base_rate" })).toContainText("left out: 74 permits and licences, 321 records that are not use decisions for this kind of business");
    await expect(counts).not.toContainText("%");
    await expect(counts).not.toContainText("Approval rate");

    await expect(page.getByTestId("comparables-map")).toBeVisible();
    await expect(page.getByTestId("comparables-map").locator(".leaflet-container")).toBeVisible();
    // The alcohol overlay is drawn in its own colour, read from `overlay_kind` (every overlay's `kind` is "overlay").
    await expect(page.getByTestId("comparables-map").locator('path[stroke="#e4572e"][stroke-dasharray="4 3"]')).toHaveCount(1);
    await expect(page.getByTestId("zoning-panel")).toContainText("NCT-VALENCIA");
  });

  test("memo page (full) shows a rate when the sample allows one; the statuses do not change", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    await page.goto("/dev/memo-preview?access=full&variant=rate");

    const overall = page.getByTestId("overall-card");
    await expect(overall.getByTestId("status-pill")).toHaveText("Further review");
    await expect(overall.getByTestId("overall-line")).toContainText(OVERALL_LINE);
    await expect(page.getByTestId("approvals").getByTestId("approval-row").getByTestId("status-pill")).toHaveText(ROW_STATUSES);
    await expect(page.getByTestId("status-reset-note")).toHaveCount(0);

    // N = 12, so the API sets rate_shown and the block prints the percentage.
    const counts = page.getByTestId("outcome-counts");
    await expect(counts.getByTestId("base-rate")).toHaveAttribute("data-rate-shown", "true");
    await expect(counts.getByTestId("base-rate-n")).toHaveText("75% approved · N = 12");
    await expect(counts.getByTestId("base-rate-scope")).toContainText("N = 12 dated decisions within 1,000 ft, last 5 years");
    await expect(counts.getByTestId("base-rate-scope")).not.toContainText("left out");
    // The variant's counts are made up, so it lists no decision under them.
    await expect(counts.getByTestId("counted-decisions")).toHaveCount(0);
    await expect(counts.getByTestId("base-rate-excluded")).toHaveText(
      "Not counted: 74 grant-only records (Entertainment Commission permits, ABC licences); 321 not use decisions (referrals, building work and other records); 3 undated records.",
    );
  });

  test("memo page (full) lists the site history with each record's kind, outcome, link and citation", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    await page.goto("/dev/memo-preview?access=full");

    await expect(page.getByRole("heading", { level: 2, name: "Site history", exact: true })).toBeVisible();
    const history = page.getByTestId("site-history");
    // Records are matched by parcel or address, so other units on the lot are listed too.
    await expect(history.getByTestId("site-history-count")).toHaveText("9 records on file at this address or parcel");
    // The note is the API's sentence; how the records were matched follows in muted text, as the PDF prints it.
    await expect(history.getByTestId("site-history-note")).toHaveText("Records on file at this address or parcel, newest first. Building work is listed here and is not counted in the outcome counts.");
    await expect(history.getByTestId("site-history-matched-by")).toHaveText("Matched by: Parcel 3609/026 or the address 995 Valencia St.");
    // The page adds no rule of its own about what counts: a use decision at the site can also be a comparable and
    // sit in the outcome counts. The only sentence on counting in the section is the API's note.
    const section = page.locator('section[aria-labelledby="sec-site-history"]');
    await expect(section).toContainText("Records at this address or parcel");
    await expect(section).not.toContainText("not comparable cases");
    await expect(section).not.toContainText("do not count");
    await expect(section).not.toContainText("this space");
    expect(((await section.textContent()) ?? "").match(/not counted|do not count|never count/gi)).toHaveLength(1);
    await expect(history.getByTestId("site-history-kinds").locator('[data-kind="agency_referral"]').first()).toHaveText("Agency referral5");
    // Every record is listed, so there is no "Showing…" line.
    await expect(history.getByTestId("site-history-shown")).toHaveCount(0);

    const table = history.getByTestId("site-history-table");
    await expect(table.getByRole("columnheader")).toHaveText(["Date", "Kind", "What", "Outcome", "Source"]);
    const rows = table.getByTestId("site-history-row");
    await expect(rows).toHaveCount(9);
    // Newest first, in the API's order, each with its record kind.
    await expect(rows.getByTestId("record-kind")).toHaveText([
      "ABC licence",
      "ABC licence",
      "Use decision",
      "Agency referral",
      "Use decision",
      "Agency referral",
      "Agency referral",
      "Agency referral",
      "Agency referral",
    ]);

    // The health referral is an agency referral: decided date, permit type, description, outcome, link and citation.
    const referral = rows.filter({ hasText: "DPH referral" });
    await expect(referral).toHaveCount(1);
    await expect(referral).toHaveAttribute("data-kind", "agency_referral");
    await expect(referral.getByTestId("site-history-date")).toContainText("Jan 20, 2021");
    await expect(referral.getByTestId("site-history-date")).toContainText("decided");
    await expect(referral).toContainText("Miscellaneous Permit");
    await expect(referral.getByTestId("outcome-badge")).toHaveText("Approved");
    await expect(referral.getByTestId("site-history-link")).toHaveAttribute("href", "https://sfplanninggis.org/pim?search=2020-012158MIS");
    await expect(referral.getByTestId("site-history-link")).toContainText("datasf_planning:2020-012158MIS");
    await expect(referral).toContainText("Planning case list (DataSF)");
    // A Planning record whose Commission motion was read names the motion as its source, and shows what the
    // record carries: its use, its closing hour and the conditions on file, listed in full behind a disclosure.
    const motion = rows.filter({ hasText: "2023-002340CUA" });
    await expect(motion).toContainText("Planning Commission motion");
    await expect(motion.getByTestId("recorded-facts")).toContainText("Use: retail alcohol");
    await expect(motion.getByTestId("recorded-facts")).toContainText("Closes: 21:00");
    await expect(motion.getByTestId("record-conditions").locator("summary")).toHaveText("10 conditions on file");
    await motion.getByTestId("record-conditions").locator("summary").click();
    await expect(motion.getByTestId("record-conditions").getByRole("listitem")).toHaveCount(10);
    await expect(motion.getByTestId("record-conditions").getByRole("listitem").first()).toContainText("Additional Project Authorization");
    // The API sends a citation for every listed record, an ABC licence included, so every row has its [n] link.
    await expect(referral.getByTestId("citation-refs").getByRole("link")).toHaveAttribute("href", /#cite-\d+/);
    await expect(rows.getByTestId("citation-refs")).toHaveCount(9);
    await expect(rows.filter({ has: page.locator('[data-testid="record-kind"][data-kind="licence"]') })).toHaveCount(2);
    // The licence at the report's own street address is the record the rules read for the existing use.
    const eatingPlace = rows.filter({ hasText: "Type 41 – On-Sale Beer & Wine - Eating Place (ACTIVE)" });
    await expect(eatingPlace).toHaveCount(1);
    await expect(eatingPlace.getByTestId("citation-refs").getByRole("link")).toHaveAttribute("href", /#cite-\d+/);
    // The citation is in the form the API writes: permit type · address · outcome (year), with id app:<record id>.
    const licenceCitation = page.getByTestId("citation-footnote").filter({ hasText: "app:abc:651564" });
    await expect(licenceCitation).toContainText("Type 41 – On-Sale Beer & Wine - Eating Place · 995 VALENCIA ST, SAN FRANCISCO, CA 94110 · approved (2023)");
    // 7 citations from the rest of the report (the district's own zoning row, which the rule lines cite, is one
    // of them), one for each of the 10 comparables and one for each of the 9 site records.
    await expect(page.getByTestId("citation-footnote")).toHaveCount(26);
    await expect(page.getByRole("heading", { level: 2, name: "26 public records behind this memo" })).toBeVisible();
    // The licence was granted and is active: the outcome, then the source's own status.
    await expect(eatingPlace.getByTestId("outcome-badge")).toHaveText("Approved");
    await expect(eatingPlace).toContainText("ACTIVE");
    await expect(eatingPlace.getByTestId("site-history-date")).toContainText("Nov 3, 2023");

    // The site's own records are not repeated among the comparables, and no building work is there either.
    const comparables = page.getByTestId("comparables-table");
    await expect(comparables.getByTestId("comparable-row")).toHaveCount(10);
    await expect(comparables).not.toContainText("Building work");
    await expect(comparables).not.toContainText("2020-012158MIS");
    await expect(comparables.locator('[data-kind="building_work"]')).toHaveCount(0);

    // The section sits after the approvals and the open questions, and before the comparables.
    const top = async (testId: string) => (await page.getByTestId(testId).boundingBox())?.y ?? Number.NaN;
    const [approvalsY, factsY, unknownsY, historyY, comparablesY] = [await top("approvals"), await top("facts"), await top("could-not-establish"), await top("site-history"), await top("comparables-table")];
    expect(approvalsY).toBeLessThan(factsY);
    expect(factsY).toBeLessThan(unknownsY);
    expect(approvalsY).toBeLessThan(unknownsY);
    expect(unknownsY).toBeLessThan(historyY);
    expect(historyY).toBeLessThan(comparablesY);
  });

  test("memo page (full) says how many site records are listed when the list is cut short, building work included", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    await page.goto("/dev/memo-preview?access=full&variant=history-long");

    const history = page.getByTestId("site-history");
    await expect(history.getByTestId("site-history-count")).toHaveText("37 records on file at this address or parcel");
    const rows = history.getByTestId("site-history-row");
    await expect(rows).toHaveCount(20);
    // The API's note already says "newest first"; the line under the table gives only the numbers, as the PDF does.
    await expect(history.getByTestId("site-history-shown")).toHaveText("Showing 20 of 37");
    expect(((await history.textContent()) ?? "").match(/newest first/g)).toHaveLength(1);
    // Every listed record has its citation link.
    await expect(rows.getByTestId("citation-refs")).toHaveCount(20);
    await expect(history.getByTestId("site-history-date").first()).toContainText("Apr 9, 2025");
    await expect(history.getByTestId("site-history-date").last()).toContainText("Aug 11, 2010");
    // The counts by kind cover all 37 records, not only the 20 listed.
    await expect(history.getByTestId("site-history-kinds").locator('[data-kind="building_work"]').first()).toHaveText("Building work22");
    await expect(history.locator('[data-testid="site-history-row"][data-kind="building_work"]')).toHaveCount(10);

    // A kitchen hood permit is building work: decided date, permit type, outcome.
    const hood = rows.filter({ hasText: "kitchen exhaust hood" });
    await expect(hood).toHaveCount(1);
    await expect(hood).toHaveAttribute("data-kind", "building_work");
    await expect(hood.getByTestId("site-history-date")).toContainText("Oct 24, 2016");
    await expect(hood.getByTestId("site-history-date")).toContainText("decided");
    await expect(hood).toContainText("Project Profile Lite");
    await expect(hood.getByTestId("outcome-badge")).toHaveText("Approved");
    // No decision date: the filing date. No known outcome: the source's status, without a badge.
    const meeting = rows.filter({ hasText: "Project review meeting" });
    await expect(meeting).toHaveCount(1);
    await expect(meeting.getByTestId("site-history-date")).toContainText("Mar 28, 2022");
    await expect(meeting.getByTestId("site-history-date")).toContainText("filed");
    await expect(meeting.getByTestId("outcome-badge")).toHaveCount(0);
    await expect(meeting).toContainText("Closed");

    // Building work is listed at the site and is not a comparable: none of it is in the comparables table.
    const comparables = page.getByTestId("comparables-table");
    await expect(comparables).not.toContainText("Building work");
    await expect(comparables).not.toContainText("kitchen exhaust hood");
    await expect(comparables.locator('[data-kind="building_work"]')).toHaveCount(0);
  });

  test("memo page (full) says so when nothing is on file at the address, and the change of use is not established", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    await page.goto("/dev/memo-preview?access=full&variant=history-empty");

    await expect(page.getByRole("heading", { level: 2, name: "Site history", exact: true })).toBeVisible();
    const history = page.getByTestId("site-history");
    await expect(history.getByTestId("site-history-count")).toHaveText("No records on file at this address or parcel");
    await expect(history.getByTestId("site-history-note")).toHaveText("No records at this address or parcel in the data. That does not mean nothing was ever filed here.");
    await expect(history.getByTestId("site-history-matched-by")).toHaveText("Matched by: Parcel 3609/026 or the address 995 Valencia St.");
    await expect(history.getByTestId("site-history-table")).toHaveCount(0);
    await expect(history.getByTestId("site-history-row")).toHaveCount(0);
    await expect(history.getByTestId("site-history-kinds")).toHaveCount(0);
    await expect(history.getByTestId("site-history-shown")).toHaveCount(0);
    await expect(page.getByTestId("comparables-table").getByTestId("comparable-row")).toHaveCount(10);

    // With no record of what the space is used as now, the pathway says so and the building row follows it:
    // Insufficient information, naming what is missing, with an open question for each input. The zoning row
    // does not move.
    const pathway = page.getByTestId("pathway");
    await expect(pathway).toHaveAttribute("data-change-of-use", "not_established");
    await expect(pathway.locator('[data-fact="existing_use"] dd')).toHaveText("Not shown by the records");
    await expect(pathway.locator('[data-fact="change_of_use"] dd')).toHaveText("Change of use not established");
    await expect(pathway.locator('[data-fact="permission"] dd')).toHaveText("Not decided by the rules");
    const building = approvalRow(page, "building_change_of_use");
    const buildingRules = ruleRow(RULES_NO_LICENCE, "building_change_of_use");
    await expect(building).toHaveAttribute("data-status", "insufficient_information");
    await expect(building.getByTestId("approval-name")).toHaveText("Building permit");
    // The inputs the row lacks, as the rules name them.
    expect(buildingRules.missing_inputs).toHaveLength(3);
    await expect(building.getByTestId("missing-inputs")).toContainText("Not given");
    await expect(building.getByTestId("missing-input")).toHaveText(buildingRules.missing_inputs ?? []);
    await expect(building.getByTestId("missing-input").first()).toHaveText("what the space was last used as");
    // The first two change-of-use answers are not established; the notification answer does not depend on them.
    await expect(building.getByTestId("change-answer").getByTestId("change-answer-label")).toHaveText(CHANGE_QUESTIONS);
    await expect(building.getByTestId("change-answer").getByTestId("change-answer-value")).toHaveText(["Not established", "Not established", "Not required"]);
    const buildingShown = shownRuleLines(RULES_NO_LICENCE, "building_change_of_use");
    await expect(building.getByTestId("rule-line")).toHaveCount(buildingShown.length);
    await expect(building.getByTestId("rule-line")).toContainText(texts(buildingShown));
    await expect(building.getByTestId("rule-line").last()).toContainText("the rules cannot say whether this is a change");
    await expect(building.getByTestId("rule-line").last()).toContainText(": insufficient information.");
    // The records fact the row reads says the records show no use here.
    const recordFact = building.locator('[data-testid="row-fact"][data-origin="record"]');
    await expect(recordFact).toHaveCount(1);
    await expect(recordFact.getByTestId("fact-value")).toHaveText("Not shown by the records");
    const zoning = approvalRow(page, "zoning_use");
    await expect(zoning.locator('[data-testid="rule-line"][data-rule="zoning.existing_use"]')).toContainText(
      "No active ABC licence of a type the rules read (Types 41, 42, 47, 48, 61, 75) is on file at 995 Valencia St",
    );
    // the zoning row names the story, which the description does not give (no story is assumed)
    await expect(zoning).toHaveAttribute("data-status", "insufficient_information");
    await expect(zoning.getByTestId("missing-input").first()).toHaveText(STORY_INPUT);
    await expect(zoning.getByTestId("rule-line")).toContainText(texts(ruleRow(RULES_NO_LICENCE, "zoning_use").basis));
    await expect(page.getByTestId("approvals").getByTestId("approval-row").getByTestId("status-pill")).toHaveText(["Insufficient information", "Insufficient information", "Further review", "Allowed", "Insufficient information"]);
    // Three rows lack an input, and each names its own.
    await expect(page.getByTestId("missing-inputs")).toHaveCount(3);
    await expect(approvalRow(page, "alcohol").getByTestId("missing-input")).toHaveText([LICENCE_INPUT]);
    await expect(page.getByTestId("overall-line")).toContainText(RULES_NO_LICENCE.overall_line);
    await expect(page.getByTestId("overall-line")).toContainText("3 insufficient information (zoning and use, alcohol licence, building permit and change of use)");
    await expect(page.getByTestId("overall-card").getByTestId("status-pill")).toHaveText("Further review");
    // The rules ask a question for each missing input, and say who answers it.
    const unknowns = page.getByTestId("could-not-establish");
    for (const q of RULES_NO_LICENCE.open_questions) {
      await expect(unknowns).toContainText(q.question);
      if (q.ask) await expect(unknowns).toContainText(q.ask);
    }
    await expect(unknowns).toContainText("Not known: what the space was last used as. Needed for: building permit and change of use.");
    await expect(unknowns).toContainText("The applicant, or Planning's Property Information Map");
    await expect(unknowns.getByTestId("open-question")).toHaveCount(RULES_NO_LICENCE.open_questions.length);
    // The facts list says the same: what the space was last used as is not known.
    await expect(page.getByTestId("facts-unknown")).toContainText("Last use of the space, as described");
  });

  test("memo page (full) for a use the district does not permit: every later row follows the zoning row and there is no approval path", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    await page.goto("/dev/memo-preview?access=full&variant=not-permitted");

    await expect(page.getByTestId("memo-address")).toHaveText("1448 PACIFIC AVE, San Francisco, CA 94109");
    const overall = page.getByTestId("overall-card");
    await expect(overall.getByTestId("status-pill")).toHaveText("Not permitted");
    await expect(overall.getByTestId("overall-line")).toContainText(RULES_NOT_PERMITTED.overall_line);
    await expect(overall.getByTestId("overall-line")).toContainText("4 not permitted (zoning and use, alcohol licence, health permit, building permit and change of use).");
    // The zoning row is not permitted, and every later row follows it: no agency may issue a licence or permit for
    // a use the Planning Code prohibits (Planning Code § 175(a); the decision of 2026-11-12).
    const rows = page.getByTestId("approvals").getByTestId("approval-row");
    await expect(rows.getByTestId("status-pill")).toHaveText(["Not permitted", "Not permitted", "Not permitted", "Not permitted"]);
    const zoning = approvalRow(page, "zoning_use");
    await expect(zoning.getByTestId("approval-name")).toHaveText("Not permitted at this address");
    await expect(zoning.getByTestId("rule-line")).toContainText(texts(ruleRow(RULES_NOT_PERMITTED, "zoning_use").basis));
    await expect(zoning.getByTestId("rule-line").last()).toContainText("Zoning does not permit the concept as described at this address.");
    await expect(zoning.getByTestId("rule-line").last()).toContainText(": not permitted.");
    // The trigger that bars the use is named first; every other trigger is still listed with its control.
    const barred = shownTriggers(RULES_NOT_PERMITTED.pathway);
    await expect(zoning.getByTestId("trigger").getByTestId("trigger-label")).toHaveText(barred.map((t) => t.label));
    await expect(zoning.getByTestId("trigger").getByTestId("trigger-value")).toHaveText(barred.map((t) => TRIGGER_CONTROL_LABELS[t.control]));
    expect(barred[0].control).toBe("not_permitted");
    await expect(zoning.locator('[data-testid="trigger"][data-key="T1"]')).toContainText("Zoning district NCD-PACIFIC: a Bar on the first story is not permitted");
    const health = approvalRow(page, "health");
    await expect(health.getByTestId("rule-line")).toContainText(
      "Zoning does not permit a new Bar at this address, and no City department may issue a permit or licence that would authorize a use the Planning Code prohibits: not permitted.",
    );
    await expect(health.getByTestId("rule-section")).toHaveText("Planning Code § 175(a)");
    const alcohol = approvalRow(page, "alcohol");
    await expect(alcohol.getByTestId("rule-line")).toContainText(texts(ruleRow(RULES_NOT_PERMITTED, "alcohol").basis));
    await expect(alcohol.getByTestId("rule-line").last().getByTestId("rule-section")).toHaveText("California Business and Professions Code § 23790");
    // A row the zoning bars is decided, so it names no missing input; and no referral step is listed for an
    // approval that cannot be issued.
    await expect(alcohol.getByTestId("missing-inputs")).toHaveCount(0);
    await expect(alcohol.getByTestId("referral-steps")).toHaveCount(0);
    await expect(health.getByTestId("referral-steps")).toHaveCount(0);
    await expect(page.getByTestId("referral-step")).toHaveCount(RULES_NOT_PERMITTED.rows.reduce((n, r) => n + (r.referral_steps ?? []).length, 0));
    await expect(approvalRow(page, "building_change_of_use").getByTestId("missing-input")).toHaveCount(0);
    await expect(approvalRow(page, "building_change_of_use").getByTestId("rule-line").last()).toContainText(
      "Zoning does not permit a new Bar at this address, and no City department may issue a permit or licence that would authorize a use the Planning Code prohibits: not permitted.",
    );
    await expect(page.getByTestId("pathway")).toHaveAttribute("data-permission", "not_permitted");
    await expect(page.getByTestId("pathway").locator('[data-fact="permission"] dd')).toHaveText("Not permitted");

    // The entitlement path says there is none. No day or cost figure is printed anywhere.
    const path = overall.getByTestId("entitlement-path");
    await expect(path).toContainText("No approval path: zoning does not permit the concept as described at this address.");
    await expect(path).not.toContainText("$");
    await expect(page.getByTestId("timeline-cost")).toHaveCount(0);
    // The comparables section says no record matched, in the API's words.
    await expect(page.locator('section[aria-labelledby="sec-comparables"]')).toContainText("No Planning or Entertainment Commission record within 1,000 ft matched this kind of business.");
    // No row asks for an input (no answer changes a row zoning bars), and the fixed line on what records cannot
    // show is printed.
    expect(RULES_NOT_PERMITTED.open_questions).toHaveLength(0);
    await expect(page.getByTestId("could-not-establish")).not.toContainText("Not known: what the space was last used as.");
    await expect(page.getByTestId("records-limits")).toHaveText(RECORDS_LIMITS);
  });

  test("memo page (full) uses the singular for one site record and one record left out", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    await page.goto("/dev/memo-preview?access=full&variant=history-one");

    const history = page.getByTestId("site-history");
    await expect(history.getByTestId("site-history-count")).toHaveText("1 record on file at this address or parcel");
    const row = history.getByTestId("site-history-row");
    await expect(row).toHaveCount(1);
    await expect(history.getByTestId("site-history-kinds").locator('[data-kind="entertainment_permit"]').first()).toHaveText("Entertainment permit1");
    await expect(history.getByTestId("site-history-shown")).toHaveCount(0);
    // No date, no known outcome and no status: the same two words the PDF prints.
    await expect(row.getByTestId("site-history-date")).toHaveText("undated");
    await expect(row.getByTestId("site-history-outcome")).toHaveText("not stated");
    await expect(row.getByTestId("outcome-badge")).toHaveCount(0);
    await expect(row.getByTestId("citation-refs")).toHaveCount(1);
    await expect(page.getByTestId("base-rate-excluded")).toHaveText(
      "Not counted: 74 grant-only records (Entertainment Commission permits, ABC licences); 1 not a use decision (referrals, building work and other records).",
    );
    await expect(page.getByTestId("base-rate-scope")).not.toContainText("left out");
    // An entertainment permit does not show what the space is used as, so the change of use is not established.
    await expect(page.getByTestId("pathway")).toHaveAttribute("data-change-of-use", "not_established");
    await expect(page.locator('[data-testid="approval-row"][data-area="building_change_of_use"]')).toHaveAttribute("data-status", "insufficient_information");
  });

  test("memo page (full) falls back when the records carry no kind labels", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    await page.goto("/dev/memo-preview?access=full&variant=unlabelled");

    // Comparables look as they did before the labels: a source, and no kind under it. That holds for the
    // Entertainment Commission permit too, which the API marks as an entertainment permit with or without labels.
    const comparables = page.getByTestId("comparables-table");
    await expect(comparables.getByTestId("comparable-source")).toHaveCount(10);
    await expect(comparables.locator('[data-testid="comparable-source"][data-source="datasf_entertainment"]')).toHaveText(Array(3).fill("Entertainment Commission permit list (DataSF)"));
    await expect(comparables.getByTestId("comparable-kind")).toHaveCount(0);
    await expect(comparables).not.toContainText("Not labelled");
    await expect(comparables.locator('[data-kind="entertainment_permit"]')).toHaveCount(0);
    await expect(comparables.getByTestId("record-kind")).toHaveCount(0);
    // The permit list has no dates, so those rows have no day count; the rows keep the order of the ranking.
    await expect(comparables.getByTestId("comparable-days")).toHaveText(COMPARABLES.map((c) => timingCell(c, DATA_AS_OF)));
    await expect(comparables.getByTestId("comparable-days").filter({ hasText: "–" })).toHaveCount(4);
    // Nothing was left out for not being a use decision, so the count is not shown and the scope has no tail.
    await expect(page.getByTestId("base-rate-excluded")).toHaveText("Not counted: 74 grant-only records (Entertainment Commission permits, ABC licences).");
    await expect(page.getByTestId("base-rate-scope")).toContainText("too few for a rate");
    await expect(page.getByTestId("base-rate-scope")).not.toContainText("left out");
    // The site history still lists every record, with the kind the API sent.
    const rows = page.getByTestId("site-history").getByTestId("site-history-row");
    await expect(rows.getByTestId("record-kind")).toHaveText(["ABC licence", "ABC licence", "Not labelled", "Not labelled", "Not labelled", "Not labelled", "Not labelled", "Not labelled", "Not labelled"]);
  });

  test("memo page (full) on a phone: the site history table scrolls inside its box, not the page", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    await page.goto("/dev/memo-preview?access=full&variant=history-long");

    const table = page.getByTestId("site-history-table");
    await expect(table).toBeVisible();
    const page_ = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    expect(page_.scroll).toBeLessThanOrEqual(page_.client);
    const box = await table.evaluate((el) => {
      const wrap = el.parentElement as HTMLElement;
      return { scroll: wrap.scrollWidth, client: wrap.clientWidth, overflowX: getComputedStyle(wrap).overflowX };
    });
    expect(box.overflowX).toBe("auto");
    expect(box.scroll).toBeGreaterThan(box.client);
    await expect(page.getByTestId("site-history-count")).toBeVisible();
    await expect(page.getByTestId("site-history-shown")).toBeVisible();
    // The comparables are cards on a phone, with the same facts and links; the wide table is not shown.
    await expect(page.getByTestId("comparables-table")).toBeHidden();
    const cards = page.getByTestId("comparable-card");
    await expect(cards).toHaveCount(10);
    await expect(cards.first()).toBeVisible();
    await expect(cards.first().getByRole("link", { name: /datasf_planning:2026-005475MIS/ })).toBeVisible();
    // The facts of a row stack on a phone: none of them widens the page.
    await expect(page.getByTestId("row-facts").first()).toBeVisible();
    const after = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    expect(after.scroll).toBeLessThanOrEqual(after.client);
  });

  test("memo page (earlier format) shows the re-run card instead of a report", async ({ page }) => {
    await page.goto("/dev/memo-preview?access=legacy");
    const view = page.getByTestId("memo-view");
    await expect(view).toHaveAttribute("data-format", "legacy");
    await expect(page.getByTestId("memo-address")).toHaveText("995 Valencia St, San Francisco, CA 94110");
    await expect(page.getByTestId("access-badge")).toHaveText("Earlier format");

    const card = page.getByTestId("legacy-card");
    await expect(card).toBeVisible();
    await expect(card).toContainText("This memo was generated in an earlier report format. Re-run it to get the current report.");
    // this one was unlocked and its free re-run is unused: the card says the re-run is free
    await expect(card.getByTestId("legacy-paid-note")).toHaveText(LEGACY_PAID_NOTE);
    await expect(card.getByTestId("legacy-paid-note")).toHaveAttribute("data-rerun-free", "true");
    // both Re-run links name the earlier memo, so the API can make the re-run free
    await expect(card.getByTestId("legacy-rerun-link")).toHaveAttribute("href", /^\/app\/memo\?.*address=995.*&rerun_of=memo_fixture_legacy$/);
    await expect(page.getByTestId("rerun-link")).toHaveAttribute("href", /^\/app\/memo\?.*&rerun_of=memo_fixture_legacy$/);

    await expect(page.getByTestId("status-pill")).toHaveCount(0);
    await expect(page.getByTestId("overall-card")).toHaveCount(0);
    await expect(page.getByTestId("unlock-card")).toHaveCount(0);
    await expect(page.getByTestId("approval-row")).toHaveCount(0);
    await expect(page.getByTestId("rules-date")).toHaveCount(0);
    await expect(page.getByTestId("records-limits")).toHaveCount(0);
    await expect(page.getByTestId("referral-steps")).toHaveCount(0);
    await expect(page.getByTestId("export-pdf")).toHaveCount(0);
  });

  test("memo page (earlier format, never unlocked) shows the re-run card without the note on a paid memo", async ({ page }) => {
    await page.goto("/dev/memo-preview?access=legacy&variant=locked");
    await expect(page.getByTestId("memo-view")).toHaveAttribute("data-format", "legacy");
    await expect(page.getByTestId("legacy-card")).toBeVisible();
    await expect(page.getByTestId("legacy-paid-note")).toHaveCount(0);
    // the re-run still names the earlier memo; the API charges it like any new memo
    await expect(page.getByTestId("legacy-rerun-link")).toHaveAttribute("href", /&rerun_of=memo_fixture_legacy_locked$/);
  });

  test("memo page (earlier format, unlocked, free re-run used) says another re-run is charged", async ({ page }) => {
    await page.goto("/dev/memo-preview?access=legacy&variant=rerun-used");
    const note = page.getByTestId("legacy-paid-note");
    await expect(note).toHaveText(LEGACY_RERUN_USED_NOTE);
    await expect(note).toHaveAttribute("data-rerun-free", "false");
    await expect(page.getByTestId("legacy-rerun-link")).toHaveAttribute("href", /&rerun_of=memo_fixture_legacy_rerun_used$/);
  });

  test("memo page (full) offers the questions that would settle what it could not, and links to the form to answer them", async ({ page }) => {
    await page.goto("/dev/memo-preview?access=full");
    const unknowns = page.getByTestId("could-not-establish");
    // every open question an intake question answers names that question, in the API's own words
    const answerable = RULES.open_questions.filter((q) => q.intake_question);
    expect(answerable.length).toBeGreaterThan(0);
    await expect(unknowns.getByTestId("open-question-intake")).toHaveCount(answerable.length);
    for (const q of answerable) {
      await expect(unknowns.locator(`[data-testid="open-question-intake"][data-question="${q.intake_question}"]`).first()).toContainText(INTAKE_QUESTIONS[q.intake_question!].question);
    }
    // one link opens the form with the same input and waits for those answers: answer=1, and each question once
    const ids = [...new Set(answerable.map((q) => q.intake_question))];
    const href = await unknowns.getByTestId("answer-questions-link").getAttribute("href");
    const query = new URLSearchParams((href ?? "").split("?")[1]);
    expect(href).toMatch(/^\/app\/memo\?/);
    expect(query.get("answer")).toBe("1");
    expect(query.get("ask")).toBe(ids.join(","));
    expect(query.get("rerun_of")).toBeNull();
  });

  test("memo page (full) leads with the headline findings, above the overall card, in the API's own words", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    await page.goto("/dev/memo-preview?access=full");
    const block = page.getByTestId("headline-findings");
    await expect(block).toBeVisible();
    await expect(block.getByRole("heading", { name: HEADLINE_HEADING })).toBeVisible();
    await expect(block).toContainText(HEADLINE_HINT);
    // one item per finding the rules return, in their order, each with its status, how sure it is, its sentence
    // and the trigger line it rests on
    expect(RULES.headline_findings.length).toBeGreaterThan(0);
    const items = block.getByTestId("headline-finding");
    await expect(items).toHaveCount(RULES.headline_findings.length);
    for (const [i, h] of RULES.headline_findings.entries()) {
      const item = items.nth(i);
      await expect(item).toHaveAttribute("data-kind", h.kind);
      await expect(item).toHaveAttribute("data-definite", h.definite ? "true" : "false");
      await expect(item.getByTestId("headline-sentence")).toContainText(h.sentence);
      await expect(item.getByTestId("headline-how")).toHaveText(h.definite ? HEADLINE_DEFINITE : HEADLINE_CONTINGENT);
      await expect(item.getByTestId("headline-rule-line")).toHaveCount(h.basis.length);
    }
    // no story is given: the Mission district's rule asks for a Conditional Use whatever the story (definite); the
    // district's table would on the first story and bar the use above it, formula retail would for a chain of
    // eleven or more, and the use size control would if the floor area is at or over its threshold and grows or
    // storefronts are merged (each depends on an answer not given)
    expect(RULES.headline_findings.map((h) => [h.kind, h.trigger])).toEqual([
      ["conditional", "T2"],
      ["conditional_if", "T1"],
      ["not_permitted_if", "T1"],
      ["conditional_if", "T5"],
      ["conditional_if", "T7"],
    ]);
    // first on the page: the block comes before the overall card
    const headBox = await block.boundingBox();
    const overallBox = await page.getByTestId("overall-card").boundingBox();
    expect(headBox && overallBox && headBox.y < overallBox.y).toBeTruthy();
    // and the overall line opens with it
    await expect(page.getByTestId("overall-line")).toContainText(RULES.overall_line);
    await expect(page.getByTestId("overall-line")).toContainText("A Conditional Use Authorization is needed (use control of a special use district). A Conditional Use Authorization is needed if the business occupies no story other than the first story or the basement (use control of the zoning district).");
    await expect(page.getByTestId("overall-line")).toContainText("A Conditional Use Authorization is needed if the floor area is 3,001 square feet or more and either the floor area grows or storefronts are merged (use size).");
  });

  test("memo page (earlier format of the report) shows no headline block when the memo carries none", async ({ page }) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());
    await page.goto("/dev/memo-preview?access=full&variant=before-v2");
    await expect(page.getByTestId("memo-view")).toBeVisible();
    await expect(page.getByTestId("headline-findings")).toHaveCount(0);
  });

  test("a current-format memo's Re-run link carries no rerun_of", async ({ page }) => {
    await page.goto("/dev/memo-preview?access=full");
    await expect(page.getByTestId("rerun-link")).toHaveAttribute("href", /^\/app\/memo\?/);
    await expect(page.getByTestId("rerun-link")).not.toHaveAttribute("href", /rerun_of/);
  });

  test("a failed free re-run's Re-run link names the earlier memo, so the retry stays free", async ({ page }) => {
    await page.goto("/dev/memo-preview?access=failed&variant=free-rerun");
    await expect(page.getByRole("alert").filter({ hasText: "Generation failed" })).toBeVisible();
    await expect(page.getByTestId("rerun-link")).toHaveAttribute("href", /^\/app\/memo\?.*address=995.*&rerun_of=memo_fixture_legacy$/);
    // a failed memo that was not a free re-run re-runs like any new memo
    await page.goto("/dev/memo-preview?access=failed");
    await expect(page.getByRole("alert").filter({ hasText: "Generation failed" })).toBeVisible();
    await expect(page.getByTestId("rerun-link")).not.toHaveAttribute("href", /rerun_of/);
  });

  test("memo cards show the overall status pill, or an Earlier format tag for memos stored before format 3", async ({ page }) => {
    await page.goto("/dev/memo-preview?view=list");
    const cards = page.getByTestId("memo-card");
    await expect(cards).toHaveCount(3);
    await expect(cards.nth(0).getByTestId("status-pill")).toHaveText("Further review");
    await expect(cards.nth(1).getByTestId("status-pill")).toHaveText("Not permitted");
    await expect(cards.nth(2).getByTestId("earlier-format-tag")).toHaveText("Earlier format");
    await expect(cards.nth(2).getByTestId("status-pill")).toHaveCount(0);
  });

  test("feedback page submits an outcome and shows the thank-you state", async ({ page }) => {
    let posted: Record<string, unknown> | null = null;
    await page.route("**/v1/feedback/abc", async (route) => {
      const req = route.request();
      if (req.method() === "OPTIONS") {
        await route.fulfill({ status: 204, headers: CORS });
        return;
      }
      if (req.method() === "GET") {
        await fulfilJson(route, { memo_id: "memo_e2e", address: "598 Haight St, San Francisco, CA 94117", concept_type: "cocktail_bar", already_answered: false });
        return;
      }
      expect(req.method()).toBe("POST");
      posted = req.postDataJSON() as Record<string, unknown>;
      await fulfilJson(route, { ok: true }, 201);
    });

    await page.goto("/feedback/abc");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("How did it go?");
    await expect(page.getByTestId("feedback-address")).toHaveText("598 Haight St, San Francisco, CA 94117");
    await expect(page.getByTestId("feedback-concept")).toHaveText("cocktail bar");
    await expect(page.getByRole("radio")).toHaveCount(5);

    const submit = page.getByTestId("feedback-submit");
    await expect(submit).toBeDisabled();
    await page.getByTestId("outcome-approved_with_conditions").click();
    await page.getByRole("textbox", { name: /Anything worth passing on/ }).fill("Hearing took four months; 1am last call imposed.");
    await submit.click();

    await expect(page.getByTestId("feedback-thanks")).toBeVisible();
    await expect(page.getByTestId("feedback-thanks")).toContainText("Thank you");
    expect(posted).toMatchObject({ outcome: "approved_with_conditions", notes: expect.stringContaining("four months") });
  });

  test("feedback page shows the already-answered state", async ({ page }) => {
    await page.route("**/v1/feedback/done", async (route) => {
      if (route.request().method() === "OPTIONS") {
        await route.fulfill({ status: 204, headers: CORS });
        return;
      }
      await fulfilJson(route, { memo_id: "memo_e2e", address: "1 Ferry Building, San Francisco, CA 94111", concept_type: "cafe", already_answered: true });
    });
    await page.goto("/feedback/done");
    await expect(page.getByTestId("feedback-already")).toContainText("Already answered");
    await expect(page.getByTestId("feedback-form")).toHaveCount(0);
  });
});

test.describe("rule table v2 on the page: the helpers in src/lib/memo.ts", () => {
  const line = (rule_id: string, text: string): RuleLine => ({ rule_id, text, code_section: null, source_url: null, citations: [] });

  test("a status note reads after the status and never replaces it", () => {
    expect(statusNoteLine("further_review", "Code and Planning practice differ")).toBe("Further review: Code and Planning practice differ");
    expect(statusNoteLine("further_review", "public convenience or necessity finding likely required")).toBe("Further review: public convenience or necessity finding likely required");
    expect(statusNoteLine("further_review", null)).toBeNull();
    expect(statusNoteLine("allowed", undefined)).toBeNull();
    expect(statusNoteLine("allowed", "  ")).toBeNull();
  });

  test("the rules date is printed whenever the pathway carries one (no comparison with generated_at)", () => {
    expect(rulesDateLine("2026-11-10")).toBe("Rules applied as of Nov 10, 2026");
    expect(rulesDateLine("2025-03-04")).toBe("Rules applied as of Mar 4, 2025");
    // A report made before rule table v2 has no rules date: nothing is printed, and nothing is assumed.
    expect(rulesDateLine(null)).toBeNull();
    expect(rulesDateLine(undefined)).toBeNull();
  });

  test("each comparable's figure names its outcome, and a pending case is aged to the records date", () => {
    expect(timingCell({ outcome: "approved", filed_at: "2025-01-01", decided_at: "2025-02-04" }, "2026-11-09")).toBe("34 days to approval");
    expect(timingCell({ outcome: "cancelled", filed_at: "2025-01-01", decided_at: "2025-01-11" }, "2026-11-09")).toBe("10 days to cancellation");
    expect(timingCell({ outcome: "pending", filed_at: "2026-11-01", decided_at: null }, "2026-11-09")).toBe("pending 8 days so far");
    expect(timingCell({ outcome: "approved", filed_at: null, decided_at: "2025-02-04" }, "2026-11-09")).toBe("–");
    expect(
      decisionTimeLines(
        [
          { outcome: "pending", filed_at: "2026-11-01", decided_at: null },
          { outcome: "denied", filed_at: "2025-01-01", decided_at: "2025-01-31" },
        ],
        "2026-11-09",
      ),
    ).toEqual(["Denied: 1 case, 30 days from filing to denial.", "Still pending: 1 case, 8 days since filing (age so far as of 2026-11-09, not a time to a decision)."]);
  });

  test("every trigger is listed with its control, in every generated case, as the PDF lists them", () => {
    for (const rules of [RULES, RULES_NO_LICENCE, RULES_NOT_PERMITTED]) {
      const all = rules.pathway.triggers ?? [];
      expect(all.map((t) => t.rule_id)).toEqual(["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11"]);
      const shown = shownTriggers(rules.pathway);
      expect(shown).toEqual(all);
      expect(triggerGroups(rules.pathway).map((g) => [g.key, g.label, g.value])).toEqual(shown.map((t) => [t.rule_id, t.label, t.control]));
    }
    expect(shownTriggers(null)).toEqual([]);
    expect(shownTriggers({ triggers: undefined })).toEqual([]);
  });

  test("grouping a row's rule lines drops none, repeats none and keeps the API's order", () => {
    for (const rules of [RULES, RULES_NO_LICENCE, RULES_NOT_PERMITTED]) {
      for (const row of rules.rows) {
        const groups = rowRuleGroups(row.area, rules.pathway);
        const items = groupRuleLines(row.basis, groups);
        const printed = items.flatMap((item) => (item.group ? item.group.lines : [item.line]));
        // Every basis line is printed, in order.
        const key = (l: RuleLine) => `${l.rule_id}|${l.text}`;
        const basisKeys = row.basis.map(key);
        expect(printed.map(key).filter((k) => basisKeys.includes(k))).toEqual(basisKeys);
        // Each group is printed once, and only the zoning and building rows have groups.
        const placed = items.flatMap((item) => (item.group ? [item.group.key] : []));
        expect(placed).toEqual(groups.map((g) => g.key));
        if (row.area !== "zoning_use" && row.area !== "building_change_of_use") expect(groups).toEqual([]);
        // The line that states the row's status stays last.
        expect(items[items.length - 1]?.line).toEqual(row.basis[row.basis.length - 1]);
      }
      // The three change-of-use answers, in their fixed order, with the answers the rules gave.
      const changes = rules.pathway.changes;
      expect(changeGroups(rules.pathway).map((g) => [g.key, g.value])).toEqual([
        ["planning_use", changes?.planning_use],
        ["building_occupancy", changes?.building_occupancy],
        ["neighbourhood_notice", changes?.neighbourhood_notice],
      ]);
    }
  });

  test("grouping places a group with no line in the basis after the last group that has one, and leaves a report without groups as it is", () => {
    const basis = [line("a", "first"), line("g1.x", "one"), line("g1.y", "two"), line("b", "middle"), line("row.status", "last")];
    const group = (key: string, lines: RuleLine[]) => ({ testId: "change-answer" as const, key, label: key, value: "yes", valueLabel: "Yes", valueClass: "", lines });
    const g1 = group("g1", [line("g1.x", "one"), line("g1.y", "two")]);
    const g2 = group("g2", [line("g2.x", "not in the basis")]);
    const order = (items: ReturnType<typeof groupRuleLines>) => items.map((item) => (item.group ? `[${item.group.key}]` : item.line.rule_id));
    expect(order(groupRuleLines(basis, [g1, g2]))).toEqual(["a", "[g1]", "[g2]", "b", "row.status"]);
    // No group has a line in the basis: the groups go before the final line, which states the status.
    expect(order(groupRuleLines([line("a", "first"), line("row.status", "last")], [g2]))).toEqual(["a", "[g2]", "row.status"]);
    // A report made before rule table v2 has no triggers and no change answers: the lines are printed as they are.
    expect(order(groupRuleLines(basis, []))).toEqual(["a", "g1.x", "g1.y", "b", "row.status"]);
    expect(rowRuleGroups("zoning_use", { ...RULES.pathway, triggers: undefined, changes: undefined })).toEqual([]);
    expect(rowRuleGroups("building_change_of_use", { ...RULES.pathway, triggers: [], changes: null })).toEqual([]);
    // A line with the same rule id but another text is not taken for a group's line.
    expect(order(groupRuleLines([line("g1.x", "another sentence"), line("row.status", "last")], [g1]))).toEqual(["g1.x", "[g1]", "row.status"]);
  });
});

test.describe("auth callback", () => {
  test("a bare callback forwards to /auth/complete so fragment sessions can be read", async ({ page }) => {
    await page.goto("/auth/callback?next=%2Fapp%2Fmemo");
    // Unconfigured Supabase: the complete page gives up and sends people back to /login with the next intact.
    await expect(page).toHaveURL(/\/login\?error=.*&next=%2Fapp%2Fmemo/);
  });

  test("a token-hash link is verified server-side and failures explain themselves", async ({ page }) => {
    await page.goto("/auth/callback?token_hash=abc&type=email&next=%2Fapp%2Fmemo");
    await expect(page).toHaveURL(/\/login\?error=Authentication\+is\+not\+configured.*&next=%2Fapp%2Fmemo/);
  });

  test("provider errors keep the destination from redirect_to and read like a sentence", async ({ page }) => {
    const redirectTo = encodeURIComponent("http://localhost:3100/auth/callback?next=%2Fmemo");
    await page.goto(
      `/auth/callback?error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired&redirect_to=${redirectTo}`,
    );
    await expect(page).toHaveURL(/\/login\?error=That\+sign-in\+link\+has\+expired\+or\+was\+already\+used.*&next=%2Fmemo/);
  });
});
