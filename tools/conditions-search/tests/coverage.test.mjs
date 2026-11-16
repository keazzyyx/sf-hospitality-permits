// Tests for the coverage note (coverage.js), against the real data (data/conditions.json), the real page
// (index.html), the detail page (coverage.html) and the README's Coverage section.
// Run: node --test tools/conditions-search/tests/   (or `make test-conditions`)
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { coverageSentences, day, markdownSection, renderMarkdown } from "../coverage.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const data = JSON.parse(readFileSync(join(root, "data", "conditions.json"), "utf8"));
const html = readFileSync(join(root, "index.html"), "utf8");
const readme = readFileSync(join(root, "README.md"), "utf8");
const coverageHtml = readFileSync(join(root, "coverage.html"), "utf8");
const conds = data.conditions;

// The expected numbers, worked out here from the data file directly (not through coverage.js).
const kept = [...conds.map(c => c.decided), ...data.motions_without_conditions.map(m => m.decided)].sort();
const expected = {
  conditions: conds.length,
  motions: new Set(conds.map(c => c.record)).size,
  looked: data.coverage.cases_looked_up,
  found: data.coverage.motions_found,
  removed: data.removed_motions.length,
  none: data.motions_without_conditions.length,
  unreadable: conds.filter(c => !c.readable).length,
  near: conds.filter(c => c.page && !c.page_exact).length,
};
const dates = {
  from: kept[0],
  to: kept[kept.length - 1],
  since: data.coverage.since,
  copied: data.coverage.records_copied_on,
};
const sentences = coverageSentences(data);
const paragraph = sentences.join(" ");
const DAY = /\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}\b/g;
const numbersIn = s => (s.replace(DAY, "").match(/\d[\d,]*/g) || []).map(x => Number(x.replace(/,/g, "")));

test("the data file has what the note needs, and its counts agree with each other", () => {
  assert.equal(data.count, conds.length);
  assert.equal(data.motions_with_conditions, expected.motions);
  assert.equal(data.motions, expected.motions + expected.none, "kept = with conditions + without");
  assert.equal(expected.found, data.motions + expected.removed, "found = kept + left out");
  assert.equal(expected.looked, expected.found + data.coverage.not_found.length, "looked up = found + not found");
  assert.equal(data.text_quality["still unreadable"], expected.unreadable);
  for (const k of ["since", "records_copied_on", "motions_looked_up_on", "built_on", "decided_from", "decided_to"]) {
    assert.match(data.coverage[k] || "", /^\d{4}-\d\d-\d\d$/, k);
  }
  assert.equal(data.coverage.decided_from, dates.from);
  assert.equal(data.coverage.decided_to, dates.to);
  const byBusiness = Object.values(data.coverage.motions_by_business).reduce((a, b) => a + b, 0);
  assert.equal(byBusiness, data.motions);
});

test("the coverage note is one short paragraph: 3 plain sentences, 70 words or fewer", () => {
  assert.equal(sentences.length, 3, `${sentences.length} sentences`);
  for (const s of sentences) {
    assert.match(s, /^[A-Z][^;]*\.$/, `one plain sentence, no semicolons: ${s}`);
    assert.ok(s.split(/\s+/).length <= 32, `too long: ${s}`);
  }
  const words = paragraph.split(/\s+/).length;
  assert.ok(words <= 70, `the note is ${words} words; keep it to 70 or fewer and put detail on coverage.html`);
  assert.ok(!/undefined|NaN|null|unknown date|the last build/.test(paragraph), paragraph);
});

test("every number in the coverage note matches data/conditions.json", () => {
  const [what, notHere, gaps] = sentences;
  assert.deepEqual(numbersIn(what), [expected.removed]); // the header above the note gives the other counts
  assert.ok(what.includes(`decided ${day(dates.from)} to ${day(dates.to)}`), what);
  assert.ok(what.includes(`(${expected.removed.toLocaleString("en-US")} left out, listed below)`), what);
  if (data.review?.decisions?.length) assert.ok(what.includes("then checked"), what);
  assert.deepEqual(numbersIn(notHere), []);
  assert.deepEqual(numbersIn(gaps), [expected.unreadable]);
  assert.ok(gaps.includes(`nothing after ${day(dates.copied)}`), gaps);
  // and the formatted forms, so a thousands separator or a date format cannot drift
  for (const s of [day(dates.from), day(dates.to), day(dates.copied)]) assert.ok(paragraph.includes(s), s);
});

test("the note names what is left out, in plain words", () => {
  for (const w of ["Conditional Use", "food, drink or entertainment", "classifier", "Entertainment Commission",
    "Board of Appeals", "state alcohol licence (ABC)", "building permits", "without a motion"]) {
    assert.ok(paragraph.includes(w), w);
  }
});

test("the page shows the note near the top and links to the detail page", () => {
  const note = html.indexOf('id="coverage"');
  assert.ok(note > 0 && note < html.indexOf('class="filters"'), "the note sits above the filters");
  assert.match(html, /id="coverage"[\s\S]{0,300}href="coverage.html"/);
  assert.match(html, /coverageSentences\(d\)/);
  assert.ok(existsSync(join(root, "coverage.html")));
  assert.match(readFileSync(join(root, "coverage.html"), "utf8"), /markdownSection\(md, h\)/);
});

test("a link to a section of the detail page (coverage.html#reviewed-list) lands on it once the data has loaded", () => {
  assert.match(html, /href="coverage\.html#reviewed-list"/);
  assert.match(coverageHtml, /<h2 id="reviewed-list">/);
  // the tables above the heading are filled in after the page loads, so the page jumps to the target again then
  assert.match(coverageHtml, /const factsLoaded = fetch\("data\/conditions\.json"\)/);
  assert.match(coverageHtml, /const detailLoaded = fetch\("README\.md"\)/);
  assert.match(coverageHtml, /Promise\.allSettled\(\[factsLoaded, detailLoaded\]\)\.then\(\(\) => \{[\s\S]{0,200}scrollIntoView\(\)/);
});

test("the README's Coverage section exists, renders, and its numbers match the data", () => {
  const section = markdownSection(readme, "Coverage");
  assert.ok(section.length > 500, "README has a ## Coverage section");
  assert.match(section, /Entertainment Commission data, when it arrives, is a separate dataset\. It will not be merged/);
  const out = renderMarkdown(section);
  assert.match(out, /<h3 id="what-is-included">/);
  assert.match(out, /<ol>/);
  assert.match(out, /<a href="#reviewed-list">/);
  // the anchors it links to exist on coverage.html: in the README sections it renders (SECTIONS), or on the page
  // itself (the reviewed list, built from the data)
  const sections = JSON.parse(coverageHtml.match(/const SECTIONS = (\[[^\]]*\]);/)[1]);
  const all = coverageHtml + sections
    .map(h => `<h2 id="${h.toLowerCase().replace(/[^a-z0-9]+/g, "-")}">` + renderMarkdown(markdownSection(readme, h))).join("");
  for (const [, id] of out.matchAll(/href="#([^"]+)"/g)) assert.ok(all.includes(`id="${id}"`), `#${id}`);
  // The section gives no counts or build dates (those are on coverage.html, worked out from the data), so a rebuild
  // cannot make it go out of date. The one date it gives is the look-up's start, a constant in full_conditions.py.
  assert.ok(section.includes(`on or after ${day(dates.since)}`), "README start date matches full_conditions.SINCE");
  const left = section.replace(DAY, "").replace(/-02\b/g, "").replace(/^\s*\d+\. /gm, "").replace(/\bStep \d\b/g, "");
  assert.deepEqual(left.match(/\b\d[\d,]*\b/g) || [], [],
    "the README Coverage section should not pin counts that change with each build; they belong on coverage.html");
});
