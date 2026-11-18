// /coverage/ (the public site's coverage.html): what the search includes, how the motions were picked, what is left
// out and the known gaps. The live coverage.html, restyled: the same numbers (worked out from the data as the page
// loads, by the current site's coverage.js), the same reviewed list, and the same detail sections. The local page
// cuts them out of tools/conditions-search/README.md when the app is built ("virtual:coverage-sections" in
// vite.config.ts); the public site reads its public coverage text (public/coverage.md plus the builder's "Text
// quality" and "Motions left out" sections) as the page loads, as the live coverage.html does.

import { coverageFacts, coverageSentences, day, markdownSection, renderMarkdown } from "@conditions/coverage";
import localSections from "virtual:coverage-sections";
import { setPageTitle } from "../core/brand";
import { dataUrl, searchPage } from "../core/paths";
import { SITE } from "../core/site";
import { loadConditions } from "../core/search/load";
import type { ConditionsData } from "../core/search/types";
import { mountShell } from "../core/shell";
import "./coverage.css";

setPageTitle("Coverage");

const shell = mountShell({ current: "coverage", skip: { href: `${searchPage()}#search`, label: "Skip to search" } });

const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch] ?? ch);
const n = (k: unknown): string => (k == null ? "not recorded" : Number(k).toLocaleString("en-US"));
const slug = (h: string): string => h.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

const back = `<a class="cov-back data" href="${esc(searchPage())}">Back to the search</a>`;

const sheet = document.createElement("div");
sheet.className = "sheet cov";
sheet.innerHTML = `
  <header class="cov-head">
    <p>${back}</p>
    <h1 class="cov-title">Coverage</h1>
    <p class="cov-sub">What the conditions search includes, how the motions were picked, what is left out, and the known gaps.</p>
  </header>
  <section class="cov-section" aria-labelledby="cov-numbers">
    <h2 class="cov-h2" id="cov-numbers">Numbers from the current data</h2>
    <p class="cov-note">Worked out from the data as this page loads.</p>
    <div data-coverage-facts><p class="cov-loading" role="status">Reading ${n(__DATA_FACTS__.motions)} motions…</p></div>
  </section>
  <div data-coverage-rest hidden>
    <section class="cov-section" aria-labelledby="reviewed-list">
      <h2 class="cov-h2" id="reviewed-list">Reviewed list</h2>
      <div data-coverage-review></div>
    </section>
    <div class="cov-detail" data-coverage-detail></div>
    <p class="cov-foot">${back}</p>
  </div>`;
shell.main.append(sheet);

const find = (selector: string): HTMLElement => {
  const node = sheet.querySelector<HTMLElement>(selector);
  if (!node) throw new Error(`coverage: missing ${selector}`);
  return node;
};
const factsBox = find("[data-coverage-facts]");
const reviewBox = find("[data-coverage-review]");
// everything under the numbers is shown once they are (or cannot be), so it is drawn in its place and never jumps
const rest = find("[data-coverage-rest]");

/** A table that scrolls sideways inside its own box on a narrow page, never the page. */
const scroll = (label: string, table: string): string =>
  `<div class="cov-scroll" tabindex="0" role="region" aria-label="${esc(label)}">${table}</div>`;

function drawFacts(d: ConditionsData): void {
  const f = coverageFacts(d);
  const cov = (d.coverage ?? {}) as {
    motions_by_business?: Record<string, number>;
    not_found?: { record: string; decided?: string | null; food_or_drink_now?: boolean }[];
  };
  const by = Object.entries(cov.motions_by_business ?? {});
  // the rows of coverage.html, in its order
  const rows: [label: string, value: string, sub?: boolean][] = [
    [`Cases looked up (decided since ${day(f.since)}, food or drink under the labels at the time)`, n(f.casesLookedUp)],
    ["Motions found", n(f.motionsFound)],
    ["Cases with no motion found", n(f.notFound)],
    ["Kept by the AI classifier (food or drink)", n(f.classifierKept)],
    ["Left out by the AI classifier", n(f.classifierRemoved)],
    ["Added back by the hand review", n(f.addedByReview)],
    ["Removed by the hand review", n(f.removedByReview)],
    ...(f.businessSetByReview ? [["Kept, business type corrected by the hand review", n(f.businessSetByReview)] as [string, string]] : []),
    ["Motions left out in all", n(f.removed)],
    ["Motions kept", n(f.motionsKept)],
    ...by.map(([k, v]) => [k, n(v), true] as [string, string, boolean]),
    ["Kept motions with no conditions", n(f.withoutConditions)],
    ["Motions with conditions on the page", n(f.motionsWithConditions)],
    ["Conditions on the page", n(f.conditions)],
    ["Decided", `${day(f.decidedFrom)} to ${day(f.decidedTo)}`],
    ["Conditions that could not be read cleanly", n(f.unreadable)],
    ["Conditions read again by OCR (first reading garbled)", n(f.byOcr)],
    ["Page links that point near the condition, not at it", n(f.nearPage)],
    ["Planning's records copied", f.recordsCopiedOn ? day(f.recordsCopiedOn) : "not recorded"],
    ["Motions looked up", f.lookedUpOn ? day(f.lookedUpOn) : "not recorded"],
    ["Data built", f.builtOn ? day(f.builtOn) : "not recorded"],
  ];
  const notFound = cov.not_found ?? [];
  factsBox.innerHTML = `<p class="cov-lead">${esc(coverageSentences(d).join(" "))}</p>
    <table class="cov-facts"><tbody>${rows
      .map(([k, v, sub]) => `<tr${sub ? ' class="is-sub"' : ""}><th scope="row">${esc(k)}</th><td class="data">${esc(v)}</td></tr>`)
      .join("")}</tbody></table>
    ${
      notFound.length
        ? `<p class="cov-note">No motion found for: ${notFound
            .map(m => `${esc(m.record)} (decided ${esc(day(m.decided))}${m.food_or_drink_now ? ", food or drink under the current labels" : ""})`)
            .join("; ")}.</p>`
        : ""
    }`;

  const review = d.review ?? {};
  const decisions = review.decisions ?? [];
  const decision = (r: { decision?: string | null; business?: string | null }): string =>
    r.decision === "include" ? `Include${r.business ? ` as ${r.business.toLowerCase()}` : ""}` : "Exclude";
  reviewBox.innerHTML = decisions.length
    ? `<p class="cov-text">An AI classifier decided which motions are about a food, drink or entertainment business. An AI review then
      read each motion${review.reviewed_on ? ` (reviewed ${esc(day(review.reviewed_on))})` : ""} and corrected the
      classifier where it was wrong: “Include” brings a motion it left out back onto the page, “Exclude” takes off one
      it kept, and an “Include” of a motion it already kept can correct its business type. Grocery stores stay
      out (a General or Specialty Grocery use); a Liquor Store use stays in as other food and drink.
      Motions the classifier got right are not listed.</p>
      ${scroll(
        "The reviewed list",
        `<table class="cov-table"><thead><tr><th scope="col">Record</th><th scope="col">Address</th><th scope="col">What it is</th><th scope="col">Decision</th><th scope="col">Reason</th></tr></thead><tbody>
      ${decisions
        .map(
          r =>
            `<tr><td class="data">${esc(r.record)}</td><td>${esc(r.address)}</td><td>${esc(r.what)}</td><td>${esc(decision(r))}</td><td>${esc(r.reason)}</td></tr>`,
        )
        .join("")}
      </tbody></table>`,
      )}`
    : `<p class="cov-text">No motions have been reviewed yet: the classifier's labels are used as they are.</p>`;
}

function drawError(): void {
  reviewBox.innerHTML = "";
  factsBox.innerHTML = `<div class="cov-error" role="alert"><p class="cov-error__line">Could not load the data.</p><p class="cov-note">The numbers could not be read. Check the connection and try again.</p><p><button class="ruled-button" type="button" data-coverage-retry>Try again</button></p></div>`;
  factsBox.querySelector<HTMLButtonElement>("[data-coverage-retry]")?.addEventListener("click", () => {
    factsBox.innerHTML = `<p class="cov-loading" role="status">Reading ${n(__DATA_FACTS__.motions)} motions…</p>`;
    void load(true).then(goToTarget);
  });
}

/** The headings a link can point at (#reviewed-list, the detail sections) are only far enough down to scroll to
 *  once the tables above them are drawn, so go to the address's target again then. */
function goToTarget(): void {
  if (!location.hash) return;
  let id = location.hash.slice(1);
  try {
    id = decodeURIComponent(id);
  } catch {
    // a malformed escape: use it as written
  }
  document.getElementById(id)?.scrollIntoView();
}

/** The sections of the coverage text the page shows, in the live coverage.html's order. */
const SECTIONS = ["Coverage", "Text quality", "Motions left out: not food or drink", "Motion PDFs on the public site"];

const detailBox = find("[data-coverage-detail]");
/** The detail: the Coverage section, plus the sections it points to (its "Reviewed list" link goes to the list
 *  above). The public site reads its coverage text now; the local page has it from the build. */
function detail(): Promise<void> {
  const draw = (sections: { heading: string; body: string }[]): void => {
    if (!sections.length || sections[0]?.heading !== "Coverage") {
      detailBox.innerHTML = `<p class="cov-text">The coverage detail is missing.</p>`;
      return;
    }
    detailBox.innerHTML = sections
      .map(
        ({ heading, body }) =>
          `<section class="cov-section cov-prose" aria-labelledby="${slug(heading)}"><h2 class="cov-h2" id="${slug(heading)}">${heading === "Coverage" ? "Detail" : esc(heading)}</h2>${renderMarkdown(body)
            .replace(/<table>/g, '<div class="cov-scroll" tabindex="0" role="region" aria-label="Table"><table class="cov-table">')
            .replace(/<\/table>/g, "</table></div>")}</section>`,
      )
      .join("");
  };
  if (!SITE) {
    draw(localSections);
    return Promise.resolve();
  }
  return fetch(SITE.files.coverage)
    .then(response => {
      if (!response.ok) throw new Error(`coverage text: ${response.status}`);
      return response.text();
    })
    .then(md => draw(SECTIONS.map(heading => ({ heading, body: markdownSection(md, heading) })).filter(x => x.body)))
    .catch(() => {
      detailBox.innerHTML = `<p class="cov-text">Could not load the coverage detail. Please reload the page.</p>`;
    });
}

function load(fresh = false): Promise<void> {
  return loadConditions(dataUrl(), __DATA_FACTS__.bytes, { fresh })
    .then(d => {
      drawFacts(d);
      shell.setFacts(d);
    })
    .catch(() => drawError());
}

// everything under the numbers is shown once both parts are in (or cannot be), and the address's target is then
// far enough down to go to
void Promise.all([load(), detail()]).then(() => {
  rest.hidden = false;
  goToTarget();
});
