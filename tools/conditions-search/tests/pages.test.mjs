// Page links on the real data (data/conditions.json): an untitled older condition, stored as "Condition: text"
// under the generic title "Condition" that the motion does not print, links to its page as exact ("at page"), not
// "near page", when its opening words are on that page. Run: node --test tools/conditions-search/tests/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const data = JSON.parse(readFileSync(join(here, "..", "data", "conditions.json"), "utf8"));
const html = readFileSync(join(here, "..", "index.html"), "utf8");
const all = data.conditions;
const find = (record, number) => all.find(c => c.record === record && c.number === number);

test("2009.0773C #14, an untitled condition on page 14 of its motion, links to page 14 as exact", () => {
  const c = find("2009.0773C", "14");
  assert.ok(c, "2009.0773C #14 not in the data");
  assert.equal(c.title, "Condition");
  assert.match(c.text, /^Condition: Notices shall be well/);
  assert.equal(c.page, 14);
  assert.equal(c.page_exact, true);
  // the card says "at page 14", not "near page 14"
  assert.ok(html.includes('c.page_exact ? " at page " : " near page "'));
});

test("untitled older conditions are found by their own opening words, not the generic title: nearly all exact", () => {
  const untitled = all.filter(c => c.title === "Condition" && /^Condition:/.test(c.text) && c.decided < "2019" && c.page);
  assert.ok(untitled.length >= 500, `only ${untitled.length} untitled older conditions with a page`);
  const exact = untitled.filter(c => c.page_exact).length;
  // the rest are near for a reason of their own (opening words not on any page, or moved back into order)
  assert.ok(exact / untitled.length >= 0.9, `${exact} of ${untitled.length} exact`);
});
