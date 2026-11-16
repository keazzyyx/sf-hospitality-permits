// The coverage note: what the page includes, how the motions were picked, what is left out and the known gaps.
// Every number and date comes from data/conditions.json (written by scripts/validation/build_conditions_index.py),
// so the note changes with the data. The page (index.html), the detail page (coverage.html) and the test
// (tests/coverage.test.mjs) all load this module.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2019-01-16" -> "16 Jan 2019". Fixed format, so it does not depend on the browser's language. */
export function day(iso) {
  const m = /^(\d{4})-(\d\d)-(\d\d)/.exec(iso || "");
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : "an unknown date";
}

const num = k => k.toLocaleString("en-US");
const count = (k, one, many = one + "s") => `${num(k)} ${k === 1 ? one : many}`;

/** The facts the note states, worked out from the data file. */
export function coverageFacts(data) {
  const conds = data.conditions;
  const cov = data.coverage || {};
  const review = data.review || {};
  const dates = [...conds.map(c => c.decided), ...data.motions_without_conditions.map(m => m.decided)]
    .filter(Boolean).sort();
  return {
    conditions: conds.length,
    motionsWithConditions: new Set(conds.map(c => c.record)).size,
    motionsKept: data.motions,
    withoutConditions: data.motions_without_conditions.length,
    removed: data.removed_motions.length,
    classifierKept: review.classifier_kept ?? data.motions,
    classifierRemoved: review.classifier_removed ?? data.removed_motions.length,
    addedByReview: (review.added_back || []).length,
    removedByReview: (review.removed || []).length,
    businessSetByReview: (review.business_set || []).length,
    reviewed: (review.decisions || []).length > 0,
    reviewedOn: review.reviewed_on || null,
    decidedFrom: dates[0],
    decidedTo: dates[dates.length - 1],
    since: cov.since,
    casesLookedUp: cov.cases_looked_up,
    motionsFound: cov.motions_found,
    notFound: (cov.not_found || []).length,
    unreadable: conds.filter(c => !c.readable).length,
    nearPage: conds.filter(c => c.page && !c.page_exact).length,
    noPage: conds.filter(c => !c.page).length,
    byOcr: (data.text_quality || {})["fixed by ocr"] || 0,
    recordsCopiedOn: cov.records_copied_on,
    lookedUpOn: cov.motions_looked_up_on,
    builtOn: cov.built_on,
  };
}

/** The note as three short, plain sentences for the top of the search page (70 words or fewer in all). The page
 *  header above it gives the number of conditions and motions, and coverage.html gives the look-up counts, the
 *  OCR and page-link details, so the note leaves them out. */
export function coverageSentences(data) {
  const f = coverageFacts(data);
  const others = f.removed ? ` (${num(f.removed)} left out, listed below)` : "";
  const after = f.recordsCopiedOn ? day(f.recordsCopiedOn) : "the last build";
  const picked = f.reviewed ? "picked by an AI classifier, then checked" : "as an AI classifier marks them";
  return [
    `Included: Conditional Use motions decided ${day(f.decidedFrom)} to ${day(f.decidedTo)} ` +
      `for food, drink or entertainment premises, ${picked}${others}.`,
    "Not included: Entertainment Commission permits, Board of Appeals decisions, state alcohol licence (ABC) " +
      "conditions, building permits, approvals without a motion.",
    `Known gaps: the ${f.reviewed ? "review" : "classifier"} can be wrong, ${count(f.unreadable, "condition")} ` +
      `${f.unreadable === 1 ? "is" : "are"} unreadable, and nothing after ${after} is here.`,
  ];
}

// ---- a small Markdown reader for the README's Coverage section (coverage.html) ----------------------------------

/** The text of one "## Heading" section of a Markdown file, up to the next "## " heading. */
export function markdownSection(md, heading) {
  const lines = md.split("\n");
  const start = lines.findIndex(l => l.trim() === `## ${heading}`);
  if (start < 0) return "";
  const end = lines.findIndex((l, i) => i > start && /^## /.test(l));
  return lines.slice(start + 1, end < 0 ? undefined : end).join("\n").trim();
}

const escHtml = s => s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function inline(text) {
  return escHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, href) =>
      /^(https?:|#|\.\/|[\w-]+\.html)/.test(href) ? `<a href="${href}">${label}</a>` : label);
}

/** Markdown to HTML for what the README uses: ### headings, paragraphs, - and 1. lists (with continuation
 *  lines), | tables |, **bold**, `code` and [links](...). Anything else is shown as plain text. */
export function renderMarkdown(md) {
  const blocks = md.split(/\n\s*\n/);
  return blocks.map(block => {
    const lines = block.split("\n");
    const h = /^(#{3,4})\s+(.*)$/.exec(lines[0]);
    if (h && lines.length === 1) {
      const id = h[2].toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      return `<h${h[1].length} id="${id}">${inline(h[2])}</h${h[1].length}>`;
    }
    if (lines.every(l => l.trim().startsWith("|"))) {
      const cells = l => l.trim().replace(/^\||\|$/g, "").split("|").map(c => inline(c.trim()));
      const body = lines.filter((l, i) => i !== 1 || !/^[\s|:-]+$/.test(l));
      const [head, ...rest] = body.map(cells);
      return `<table><thead><tr>${head.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>`
        + rest.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("") + "</tbody></table>";
    }
    const item = /^(\s*)(-|\d+\.)\s+/;
    if (item.test(lines[0])) {
      const ordered = /\d/.test(item.exec(lines[0])[2]);
      const items = [];
      for (const l of lines) {
        if (item.test(l)) items.push(l.replace(item, ""));
        else items[items.length - 1] += " " + l.trim();
      }
      const tag = ordered ? "ol" : "ul";
      return `<${tag}>${items.map(i => `<li>${inline(i)}</li>`).join("")}</${tag}>`;
    }
    return `<p>${inline(lines.map(l => l.trim()).join(" "))}</p>`;
  }).join("\n");
}
