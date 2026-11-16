// Tests for the conditions search page, against the real data (data/conditions.json) and the real page
// (index.html). Run: node --test tools/conditions-search/tests/*.test.mjs   (or `make test-conditions`)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { search, stem, tokenize, parseQuery, highlight, placeholderExamples, compare, missingWords, noMatchNote, SYNONYM_GROUPS, GROUP_NOTES, recordMatches, addressMatches,
  synonymLines, stateFromHash, hashFromState, STATE_KEYS, numberOrder, streetOf } from "../search.js";

const here = dirname(fileURLToPath(import.meta.url));
const data = JSON.parse(readFileSync(join(here, "..", "data", "conditions.json"), "utf8"));
const html = readFileSync(join(here, "..", "index.html"), "utf8");
const all = data.conditions;
const ids = q => search(all, { q }).map(c => `${c.record}#${c.number}`);
const esc = s => s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

test("every example in the search box's placeholder finds at least one condition in the default view", () => {
  const placeholder = /id="q"[^>]*placeholder="([^"]+)"/.exec(html)?.[1];
  assert.ok(placeholder, "placeholder not found in index.html");
  const examples = placeholderExamples(placeholder);
  assert.ok(examples.length >= 3, `too few examples: ${examples}`);
  for (const q of examples) assert.ok(search(all, { q }).length >= 1, `"${q}" finds nothing`);
});

test("all words must match, in any order", () => {
  const ab = ids("amplified music"), ba = ids("music amplified");
  assert.ok(ab.length >= 1);
  assert.deepEqual(ab, ba);
  // "amplified" is in a synonym group with noise and sound, so each hit has music and one of the three
  for (const c of search(all, { q: "amplified music" })) {
    const keys = new Set(tokenize(`${c.title} ${c.text}`).map(t => t.key));
    assert.ok(keys.has("music") && ["amplify", stem("noise"), "sound"].some(k => keys.has(k)), `${c.record}#${c.number} lacks a word`);
  }
  // without synonyms in play, every word is required as typed
  for (const c of search(all, { q: "outdoor seating" })) {
    const keys = new Set(tokenize(`${c.title} ${c.text}`).map(t => t.key));
    assert.ok(keys.has("outdoor") && keys.has("seat"), `${c.record}#${c.number} lacks a word`);
  }
  assert.equal(search(all, { q: "odor zzzzqqq" }).length, 0);
});

test("simple word endings do not matter", () => {
  for (const [a, b] of [["guard", "guards"], ["guard", "guarded"], ["guard", "guarding"], ["odor", "odors"],
    ["close", "closing"], ["close", "closed"], ["patron", "patrons"], ["light", "lighting"], ["seat", "seating"],
    ["amplify", "amplified"], ["activity", "activities"], ["plan", "plans"]]) {
    assert.equal(stem(a), stem(b), `${a} / ${b}`);
  }
  assert.notEqual(stem("guard"), stem("guardians"));
  // words whose ending is part of the word stay apart from the shorter word
  for (const [a, b] of [["park", "parking"], ["new", "news"], ["plan", "planning"], ["build", "building"]]) {
    assert.notEqual(stem(a), stem(b), `${a} / ${b}`);
  }
  assert.equal(stem("buildings"), stem("building"));
  assert.deepEqual(ids("patron"), ids("patrons"));
  assert.deepEqual(ids("odors"), ids("odor"));
});

test("times match however they are written", () => {
  const forms = ["10 p.m.", "10pm", "10 PM", "10:00 p.m.", "10:00PM", "10 p.m"];
  const base = ids(forms[0]);
  assert.ok(base.length >= 1);
  for (const q of forms) assert.deepEqual(ids(q), base, q);
  assert.equal(tokenize("7:OOam")[0].key, "7am"); // OCR zeros
  assert.equal(tokenize("10:30 p.m.")[0].key, "10:30pm");
  assert.equal(tokenize("2 a merged")[0].key, "2"); // not a time
  // a bare hour finds the times at that hour
  assert.ok(ids("10").length >= base.length);
  assert.deepEqual(ids("midnight").length >= 1, true);
  assert.deepEqual(ids("12 a.m."), ids("midnight"));
  // "p.m." on its own finds evening times, not stray single letters
  assert.deepEqual(ids("p.m."), ids("pm"));
  assert.ok(ids("p.m.").length >= base.length);
  for (const c of search(all, { q: "p.m." })) {
    assert.ok(tokenize(`${c.title} ${c.text}`).some(t => /^\d{1,2}(?::\d\d)?pm$/.test(t.key)), `${c.record}#${c.number}`);
  }
  assert.deepEqual(parseQuery("Section 3 a").map(t => t.key), ["section", "3"]);
});

// Made-up conditions for the synonym rules, so they are tested whatever the data holds.
const FIXTURE = [
  ["S1", "Security", "Sales staff or security personnel of the operator shall inform each customer."],
  ["S2", "Security Staff", "Security staff shall be on site from 9 p.m. until closing."],
  ["S3", "Monitoring", "Subject to Department staff review and approval."],
  ["S4", "Hours of Operation", "The business may be open from 7 a.m. to 10 p.m. daily."],
  ["S5", "Closing", "Patrons shall leave by closing time."],
  ["S6", "Noise", "No noise audible beyond the premises."],
  ["S7", "Sound", "Sound levels shall not exceed 70 dBA."],
  ["S8", "Music", "No amplified music outdoors."],
  ["S9", "Signage", "Signs shall be maintained so that law enforcement personnel have a clear view."],
].map(([number, title, text]) => ({ record: "FIXTURE", number, title, text, kind: "specific", decided: "2026-01-01", categories: [] }));
const fx = q => search(FIXTURE, { q }).map(c => c.number).sort();

test('"security guard" finds security personnel and security staff (synonym group guard / security personnel / security staff)', () => {
  assert.deepEqual(fx("security guard"), ["S1", "S2"]);
  assert.deepEqual(fx("guard"), ["S1", "S2"]); // not Department staff (S3), not law enforcement personnel (S9)
  assert.deepEqual(fx("security personnel"), ["S1", "S2"]);
  assert.deepEqual(fx("security staff"), ["S1", "S2"]);
  // "security guard" is itself an entry of the group: one search term, not "security" plus "guard"
  assert.deepEqual(parseQuery("security guard").map(t => t.text), ["security guard"]);
  for (const q of ["security officer", "bouncer", "doorman", "door staff", "security guards"]) assert.deepEqual(fx(q), ["S1", "S2"], q);
  // In the real data only older motions (2010-2018) have a condition about security staff; no 2019+ condition left
  // after the review mentions a guard, security personnel, security staff, a security officer, a bouncer or door
  // staff (the one that did, 2021-010728CUA, is a cannabis store the review removed). Every hit must use a word of
  // the group; were there none, the page would say why and where security staffing is set.
  const hits = search(all, { q: "security guard", kind: "all" });
  for (const c of hits) assert.match(`${c.title} ${c.text}`, /\bsecurity (personnel|staff|officers?|guards?)\b|\bguards?\b|\bbouncers?\b|\bdoor staff\b/i, `${c.record}#${c.number}`);
  if (!hits.length) {
    assert.deepEqual(missingWords(all, "security guard"), ["security guard"]);
    assert.equal(noMatchNote(all, "security guard"), `No condition on these motions uses “security guard”. ${GROUP_NOTES.guard}`);
    // the condition the note points to is there
    assert.ok(search(all, { q: "patrons" }).some(c => /leave the establishment and neighborhood in a quiet/i.test(c.text)));
  }
  assert.deepEqual(missingWords(all, "odor zzzzqqq"), ["zzzzqqq"]);
});

test("a search that finds nothing names the missing words, and suggests the others only when there are others", () => {
  // a two-word synonym phrase is one search term, so a search of just that phrase has no other words to try
  assert.equal(noMatchNote(FIXTURE, "zzzzqqq personnel"), "No condition on these motions uses “zzzzqqq”; try the other words alone.");
  assert.equal(noMatchNote(all, "zzzzqqq"), "No condition on these motions uses “zzzzqqq”.");
  assert.equal(noMatchNote(FIXTURE, "security personnel zzzzqqq").endsWith("; try the other words alone."), true);
  const none = all.filter(c => !/\bsecurity (personnel|staff)\b|\bguards?\b/i.test(`${c.title} ${c.text}`));
  for (const q of ["security personnel", "security staff", "guard"]) {
    assert.equal(noMatchNote(none, q), `No condition on these motions uses “${q}”. ${GROUP_NOTES.guard}`, q);
  }
  assert.equal(noMatchNote(all, "odor"), "");
  assert.match(html, /const note = f\.q \? noMatchNote\(all, f\.q\) : "";/);
});

test("each synonym group: a word finds the conditions that use any other word of its group", () => {
  const hitsOf = q => new Set(ids(q));
  for (const group of SYNONYM_GROUPS) {
    const union = new Set(group.flatMap(w => {
      // the conditions with this entry itself (a phrase as words side by side), found without the synonym rule
      const keys = tokenize(w).map(t => t.key).join(" ");
      return search(all, {}).filter(c => ` ${tokenize(`${c.title} ${c.text}`).map(t => t.key).join(" ")} `.includes(` ${keys} `))
        .map(c => `${c.record}#${c.number}`);
    }));
    for (const w of group) assert.deepEqual([...hitsOf(w)].sort(), [...union].sort(), `"${w}" in [${group}]`);
  }
  // the groups the owner asked for, on the made-up conditions
  assert.deepEqual(fx("hours"), ["S4", "S5"]);
  assert.deepEqual(fx("closing time"), ["S4", "S5"]);
  assert.deepEqual(fx("closing"), ["S2", "S5"]); // "closing" alone is just the word
  for (const q of ["noise", "sound", "amplified"]) assert.deepEqual(fx(q), ["S6", "S7", "S8"], q);
  assert.deepEqual(fx("amplified music"), ["S8"]);
  // and on the real data: hours and closing time reach each other, noise / sound / amplified too
  const has = (q, re) => search(all, { q, kind: "all" }).some(c => re.test(`${c.title} ${c.text}`));
  assert.ok(has("closing time", /\bhours\b/i) && has("hours", /closing time/i));
  assert.ok(has("noise", /\bsound/i) && has("sound", /\bamplified\b/i) && has("amplified", /\bnoise\b/i));
  // a phrase is two words side by side, as one term: "closing time" is not "closing" plus "time" anywhere
  assert.deepEqual(parseQuery("closing time").map(t => t.text), ["closing time"]);
  assert.deepEqual(parseQuery("security personnel 10pm").map(t => t.text), ["security personnel", "10pm"]);
  assert.equal(highlight("Department staff; security staff or security personnel", "guard", esc),
    "Department staff; <mark>security staff</mark> or <mark>security personnel</mark>");
  assert.equal(highlight("Closing time: 10 p.m. Hours posted.", "hours", esc), "<mark>Closing time</mark>: 10 p.m. <mark>Hours</mark> posted.");
});

test("the page shows the synonym list from search.js under Search tips", () => {
  assert.match(html, /<details class="tips"[\s\S]*Search tips[\s\S]*id="synonyms"/);
  assert.match(html, /\$\("synonyms"\)\.innerHTML = synonymLines\(\)/);
  assert.deepEqual(synonymLines().slice(0, 4), [
    "guard, security guard, security personnel, security staff, security officer, bouncer, doorman, door staff",
    "hours, closing time, opening hours",
    "noise, sound, amplified, loud",
    "live music, live entertainment, live performance",
  ]);
});

test("the URL hash holds the search: state from a hash, hash from a state, and the page re-runs on hashchange", () => {
  assert.deepEqual(stateFromHash("#q=security+guard&kind=all"),
    { q: "security guard", business: "", category: "", zoning: "", year: "", kind: "all" });
  assert.deepEqual(stateFromHash(""), Object.fromEntries(STATE_KEYS.map(k => [k, ""])));
  assert.deepEqual(stateFromHash("q=odor&unknown=1&year=2024"), { ...stateFromHash(""), q: "odor", year: "2024" });
  assert.equal(stateFromHash("#q=10%20p.m.").q, "10 p.m.");
  const s = { q: "amplified music", business: "Bar", category: "", zoning: "", year: "2023", kind: "" };
  assert.equal(hashFromState(s), "#q=amplified+music&business=Bar&year=2023");
  assert.deepEqual(stateFromHash(hashFromState(s)), s);
  assert.equal(hashFromState(stateFromHash("")), "#");
  // the page applies the hash on load and whenever it changes, clearing fields the new hash leaves out
  assert.match(html, /addEventListener\("hashchange", \(\) => \{ readState\(\);[^}]*render\(\); \}\)/);
  assert.match(html, /const state = stateFromHash\(location\.hash\);\s*for \(const id of IDS\) \$\(id\)\.value = state\[id\];/);
});

test("highlighting marks the matched words, including time variants", () => {
  const out = highlight("Open until 10:00 p.m. on weekdays; guards on duty.", "10pm guard", esc);
  assert.equal(out, "Open until <mark>10:00 p.m.</mark> on weekdays; <mark>guards</mark> on duty.");
  assert.equal(highlight("a < b", parseQuery(""), esc), "a &lt; b");
});

test("default view: no boilerplate; case-specific first, newest first", () => {
  const shown = search(all, {});
  assert.ok(shown.length > 0);
  assert.ok(shown.every(c => c.kind !== "boilerplate"));
  const firstStandard = shown.findIndex(c => c.kind === "standard");
  assert.ok(firstStandard > 0, "case-specific conditions come first");
  assert.ok(shown.slice(0, firstStandard).every(c => c.kind === "specific"));
  assert.ok(shown.slice(firstStandard).every(c => c.kind === "standard"));
  for (let i = 1; i < shown.length; i++) assert.ok(compare(shown[i - 1], shown[i]) <= 0);
  const dates = shown.slice(0, firstStandard).map(c => c.decided);
  assert.deepEqual(dates, [...dates].sort().reverse());
});

test("boilerplate shows only when the filter asks for it", () => {
  const titles = new Set(data.boilerplate_titles);
  const boiler = search(all, { kind: "boilerplate" });
  assert.ok(boiler.length > 0 && boiler.every(c => c.kind === "boilerplate"));
  for (const t of ["Validity", "Expiration and Renewal", "Diligent Pursuit", "Enforcement"]) assert.ok(titles.has(t), t);
  assert.equal(search(all, { kind: "all" }).length, all.length);
  assert.equal(search(all, {}).length + boiler.length, all.length);
});

test("header and list counts agree", () => {
  assert.equal(data.count, all.length);
  const records = new Set(all.map(c => c.record));
  assert.equal(data.motions_with_conditions, records.size);
  assert.equal(data.motions, data.motions_with_conditions + data.motions_without_conditions.length);
  for (const m of data.motions_without_conditions) assert.ok(!records.has(m.record), m.record);
  assert.equal(new Set(search(all, { kind: "all" }).map(c => c.record)).size, data.motions_with_conditions);
});

test("non-hospitality motions are left out and listed", () => {
  const removed = new Set(data.removed_motions.map(m => m.record));
  assert.ok(removed.has("2019-020831CUA"), "the massage business at 1117 Irving is removed");
  assert.ok(all.every(c => !removed.has(c.record)));
  assert.ok(data.removed_motions.every(m => m.record && m.what !== undefined && m.classifier
    && ["classifier", "review"].includes(m.left_out_by)));
});

test("the reviewed list overrides the classifier both ways, and every change is recorded with its reason", () => {
  const r = data.review;
  const shown = new Set(all.map(c => c.record));
  const removed = new Map(data.removed_motions.map(m => [m.record, m]));
  assert.equal(r.classifier_kept + r.classifier_removed, data.motions + data.removed_motions.length, "found = kept + left out");
  assert.equal(data.motions, r.classifier_kept + r.added_back.length - r.removed.length);
  assert.equal(data.removed_motions.length, r.classifier_removed - r.added_back.length + r.removed.length);
  for (const m of r.added_back) {
    assert.ok(m.what && m.reason && m.business, m.record);
    assert.ok(shown.has(m.record) || data.motions_without_conditions.some(x => x.record === m.record), `${m.record} is on the page`);
    assert.ok(all.filter(c => c.record === m.record).every(c => c.business === m.business), m.record);
  }
  for (const m of r.removed) {
    assert.ok(m.what && m.reason, m.record);
    assert.ok(!shown.has(m.record), `${m.record} is off the page`);
    assert.equal(removed.get(m.record)?.left_out_by, "review", m.record);
  }
  const decided = new Map(r.decisions.map(d => [d.record, d]));
  for (const m of r.added_back) assert.equal(decided.get(m.record)?.decision, "include");
  for (const m of r.removed) assert.equal(decided.get(m.record)?.decision, "exclude");
  for (const d of r.decisions) assert.ok(d.applied, `${d.record}: how the decision was applied`);
  if (r.decisions.length) {
    // the owner's examples: SusieCakes and the take-out pizza shop come back; grocery stores stay out
    for (const rec of ["2018-010482CUA", "2021-008851CUA"]) assert.ok(shown.has(rec), rec);
    // grocery stores stay out (REVIEWED.md, the grocery rule): a shown motion whose description names a grocery is
    // a market Planning approved as a Liquor Store use (rule 2, other food and drink), or a motion that approves a
    // food or drink use of its own inside the store (rule 3, shown as that use). The rule-3 motions, by name:
    const FOOD_USE_INSIDE_GROCERY = new Map([
      ["2012.1031C", "Restaurant or cafe"], // Sushi Avenue, a limited restaurant inside the Lucky grocery store
    ]);
    for (const rec of shown) {
      const d = decided.get(rec);
      if (!/grocery|supermarket/i.test(d?.what || "")) continue;
      assert.equal(d.business, FOOD_USE_INSIDE_GROCERY.get(rec) ?? "Other food and drink", rec);
      if (FOOD_USE_INSIDE_GROCERY.has(rec)) assert.match(d.reason, /approves a .*(restaurant|bar)/i, rec);
    }
    // an "include" of a motion the classifier kept can set its business type, and the page shows that type
    for (const m of r.business_set || []) {
      assert.equal(decided.get(m.record)?.business, m.business, m.record);
      assert.ok(all.filter(c => c.record === m.record).every(c => c.business === m.business), m.record);
    }
  }
});

// The build's check for pieces that are never real condition text (scripts/validation/condition_text.py,
// hard_tokens): a word with a stray symbol, letters mixed with digits, page furniture or web-address pieces. Kept in
// step with the Python by hand; this test runs it over every condition the page shows as readable.
const ODD = /[~_|\\{}^`•«»¬►]/;
// In a title "#" is junk too ("Entertainmen# Venues"); in condition text it is often real ("Unit #2", "(#310)").
const TITLE_ODD = /[#~_|\\{}^`•«»¬►]/;
const MIX = /[A-Za-z][0-9]+[A-Za-z]|[0-9][A-NP-Za-z][0-9]|\d:?[O]{1,2}(?:am|pm)?\b|[0-9][Oo][0-9]/i;
const FURNITURE = new RegExp([
  String.raw`\bP\s?L[A4]NNING\b`, String.raw`\bLANNING\b`, String.raw`\bDEPA\S*TMENT\b`, String.raw`\bSAN\s*F\S*\s+\d{1,3}\b`,
  String.raw`\bSAN\s*[fF]\S*[~]`, String.raw`\b(?:w[zuv]{3,}\w*|unow|mah:)\S*`, String.raw`\bwww\.\S*\s+-\s`,
  String.raw`\S\.or\b`, String.raw`\s\.or\b`, String.raw`\bor[Q~]`,
  String.raw`\bFor\s+\S+\s+\S*bout\s+\S*ompl\S*,?\s*cont\S*\s*$`,
].join("|"));
const PUNCT = /^[.,;:()[\]"'’‘“”\-—–!?*]+|[.,;:()[\]"'’‘“”\-—–!?*]+$/g;
function hardPieces(text) {
  const out = text.split(/\s+/).filter(t => { const core = t.replace(PUNCT, ""); return core && (ODD.test(core) || MIX.test(core)); });
  const m = FURNITURE.exec(text);
  return m ? [...out, m[0]] : out;
}
// Readable conditions allowed to keep a hard piece, with the reason. Empty today; add here only after looking.
const ALLOWED = new Map([]);

test("no OCR junk or page furniture is shown as condition text", () => {
  assert.ok(hardPieces("the commu~~ity liaison").length === 1 && hardPieces("Section 3~1").length === 1);
  assert.ok(hardPieces("SAN FRANCISCO 13P LANNING DEPANTMENT").length >= 1);
  assert.ok(hardPieces("caused delay. For information about compliance, contact").length === 1);
  assert.equal(hardPieces("Open 7:00 a.m. to 10:00 p.m., Section 145.1(c)(6), www.sf-planning.org").length, 0);
  const shown = all.filter(c => c.readable && !ALLOWED.has(`${c.record}#${c.number}`));
  const junk = shown.map(c => [`${c.record}#${c.number}`, hardPieces(`${c.title} ${c.text}`)]).filter(([, h]) => h.length);
  assert.deepEqual(junk, []);
  for (const junkWord of ["tvzvzv", "informatiofi", "Efiforcement"]) assert.ok(!shown.some(c => c.text.includes(junkWord)), junkWord);
  for (const c of all.filter(c => !c.readable)) assert.ok(c.raw_text, `${c.record}#${c.number} keeps its raw text`);
  assert.equal(data.text_quality["still unreadable"] ?? 0, all.filter(c => !c.readable).length);
});

test("no title shows OCR junk, on readable and unreadable conditions alike", () => {
  // the card shows the title even when it hides an unreadable text, so every title is checked, with "#" as junk
  assert.ok(TITLE_ODD.test("Notices Posted at Bars and Entertainmen# Venues") && !TITLE_ODD.test("Notices Posted at Bars and Entertainment Venues"));
  const junk = all.map(c => [`${c.record}#${c.number}`, c.title,
    [...c.title.split(/\s+/).filter(t => { const core = t.replace(PUNCT, ""); return core && (TITLE_ODD.test(core) || MIX.test(core)); }),
     ...(FURNITURE.exec(c.title) || [])]]).filter(([, , h]) => h.length);
  assert.deepEqual(junk, []);
  // the OCR misreadings of a title used on many conditions are read again as that title (build_conditions_index.py,
  // attested_title), so they join its group: boilerplate for revocation, standard for the rest
  const titleOf = (record, number) => all.find(c => c.record === record && c.number === number);
  for (const [record, number, title, kind] of [
    ["2017-015181CUA", "13", "Notices Posted at Bars and Entertainment Venues", "standard"],
    ["2017-000519CUA", "6", "Garbage, composting and recycling storage", "standard"],
    ["2016-000455CUA", "11", "Revocation due to Violation of Conditions", "boilerplate"],
    ["2016-000332CUA", "7", "Revocation due to Violation of Conditions", "boilerplate"],
  ]) {
    const c = titleOf(record, number);
    assert.ok(c, `${record}#${number} missing`);
    assert.equal(c.title, title, `${record}#${number}`);
    assert.equal(c.kind, kind, `${record}#${number}`);
    assert.ok(c.text.startsWith(`${title}:`), `${record}#${number} text heading`);
  }
  for (const word of ["Gazbage", "Revocation dne", "Entertainmen#"]) assert.ok(!all.some(c => c.title.includes(word)), word);
});

test("a condition that ran on after a missed heading is split out, not lost", () => {
  for (const [record, number] of [["2019-006951CUA", "7"], ["2018-016600CUA", "6"], ["2019-020852CUA", "6"]]) {
    const c = all.find(x => x.record === record && x.number === number);
    assert.ok(c, `${record}#${number} missing`);
    assert.equal(c.title, "Enforcement");
    assert.equal(c.kind, "boilerplate");
    assert.ok(c.split_from && c.readable && c.text.length > 100, `${record}#${number}`);
  }
});

test("lettered template parts worded the same on two or more motions are standard, not case-specific", () => {
  for (const title of ["Liquor Stores (A)", "Liquor Stores (B)", "Liquor Stores (C)", "Chapter 116 Residential Projects (A)"]) {
    const cs = all.filter(c => c.title === title);
    assert.ok(cs.length >= 2 && cs.every(c => c.kind === "standard" && c.template), title);
  }
  // one motion only: stays case-specific
  assert.ok(all.filter(c => c.title.startsWith("Good Neighbor Policies (")).every(c => c.kind === "specific"));
});

test("the owner's three searches on the real data: security guard, closing time and loud music find conditions", () => {
  // Since the page reached back to 2010, "security guard" finds the four conditions that require security staff,
  // all on older motions: a guard on duty in the evening (2017-006766CUA), security personnel directing garage
  // traffic at large events and the venue's own security personnel on problem events (Nob Hill Masonic Center,
  // 2013.0834C), and hired security guards at every entrance (Trigger, 2010.0970C). Something is found, so the page
  // shows no "finds nothing" note and none of GROUP_NOTES.guard (which is checked on data without them, above).
  const guard = search(all, { q: "security guard" });
  assert.deepEqual(guard.map(c => `${c.record}#${c.number}`).sort(),
    ["2010.0970C#22", "2013.0834C#15", "2013.0834C#45", "2017-006766CUA#27"]);
  for (const c of guard) assert.match(`${c.title} ${c.text}`, /\bsecurity (?:guards?|personnel)\b/i, `${c.record}#${c.number}`);
  assert.deepEqual(search(all, { q: "security guard", kind: "all" }).map(c => c.record).sort(), guard.map(c => c.record).sort());
  assert.equal(noMatchNote(all, "security guard"), "");
  // on data without them, the note says where security staffing is set
  const noGuards = all.filter(c => !/\bsecurity (personnel|staff|officers?|guards?)\b|\bguards?\b|\bbouncers?\b|\bdoor ?(staff|man|men)\b/i.test(`${c.title} ${c.text}`));
  assert.ok(noGuards.length < all.length && guard.every(c => !noGuards.includes(c)));
  assert.match(noMatchNote(noGuards, "security guard"), /Entertainment Commission permit/);
  const closing = search(all, { q: "closing time" });
  assert.ok(closing.length > 50 && closing.some(c => /hours of operation/i.test(`${c.title} ${c.text}`)));
  // no condition says "loud": "loud music" finds the music conditions that speak of noise, sound or amplification
  const loud = search(all, { q: "loud music", kind: "all" });
  assert.ok(loud.length >= 3, String(loud.length));
  for (const c of loud) {
    const t = `${c.title} ${c.text}`;
    assert.match(t, /\bmusic/i); assert.match(t, /\bnois|\bsound|\bamplif|\bloud/i);
  }
  assert.ok(loud.some(c => /amplified music/i.test(`${c.title} ${c.text}`)));
  assert.equal(highlight("Amplified Music: no loud noise", "loud music", esc), "<mark>Amplified</mark> <mark>Music</mark>: no <mark>loud</mark> <mark>noise</mark>");
});

test("a case number finds that motion's conditions, written with or without the hyphen or the suffix", () => {
  const motion = all.filter(c => c.record === "2023-005418CUA");
  assert.ok(motion.length > 5);
  const want = search(all, { kind: "all" }).filter(c => c.record === "2023-005418CUA").map(c => `${c.record}#${c.number}`);
  for (const q of ["2023-005418CUA", "2023-005418cua", "2023-005418", "2023005418CUA", "005418", "005418CUA", " 2023-005418CUA "]) {
    assert.deepEqual(search(all, { q, kind: "all" }).map(c => `${c.record}#${c.number}`), want, q);
  }
  // a case number and words: that motion's conditions with the words
  const narrowed = search(all, { q: "2023-005418CUA hours", kind: "all" });
  assert.ok(narrowed.length >= 1 && narrowed.length < want.length, String(narrowed.length));
  assert.ok(narrowed.every(c => c.record === "2023-005418CUA" && /\bhours?\b|closing time/i.test(`${c.title} ${c.text}`)));
  // amendments ("-02") and the old dotted case numbers, as the card shows them, and by their serial part
  // "2011.0097" is the case number without its suffix, so it finds every motion of that case: the first approval
  // (2011.0097C, on the page since it reached back to 2010) and its amendment (2011.0097CUA-02)
  for (const [q, records] of [["2015-002658CUA-02", ["2015-002658CUA-02"]], ["2011.0097CUA-02", ["2011.0097CUA-02"]],
    ["2013.0530CUA-02", ["2013.0530CUA-02"]], ["2011.0097", ["2011.0097C", "2011.0097CUA-02"]],
    ["0097CUA", ["2011.0097CUA-02"]], ["002658", null]]) {
    const hits = search(all, { q, kind: "all" });
    assert.ok(hits.length >= 1, q);
    if (records) assert.deepEqual([...new Set(hits.map(c => c.record))].sort(), records, q);
    else assert.ok(hits.every(c => c.record.startsWith("2015-002658CUA")), q);
  }
  // the suffix may follow a space or a hyphen, as the motions print it; a word after the number stays a word
  for (const q of ["2023-005418 CUA", "2023-005418-CUA"]) {
    assert.deepEqual(search(all, { q, kind: "all" }).map(c => `${c.record}#${c.number}`), want, q);
  }
  assert.deepEqual(parseQuery("2023-005418 hours", all).map(t => t.text), ["2023-005418", "hours"]);
  // the serial part with its amendment
  for (const [q, record] of [["002658CUA-02", "2015-002658CUA-02"], ["0097CUA-02", "2011.0097CUA-02"]]) {
    const hits = search(all, { q, kind: "all" });
    assert.ok(hits.length >= 1 && hits.every(c => c.record === record), q);
  }
  // an earlier case number quoted in a condition is still found in the text
  for (const [q, record] of [["2013.0023C", "2019-012888CUA"], ["2024-002799COA", "2024-002799CUA"]]) {
    const hits = search(all, { q, kind: "all" });
    assert.ok(hits.length >= 1 && hits.every(c => c.record === record), q);
  }
  assert.equal(noMatchNote(all, "2099-123456CUA"), "No motion on this page has the case number “2099-123456CUA” and no condition mentions it.");
  // a case number does not glue the words on either side into a synonym phrase
  assert.deepEqual(parseQuery("security 2023-005418CUA guard", all).map(t => t.text).sort(), ["2023-005418CUA", "guard", "security"]);
  // a missing word and a missing case number are named apart
  assert.equal(noMatchNote(all, "zzzzqqq 2099-123456CUA"),
    "No condition on these motions uses “zzzzqqq”, and no motion on this page has the case number “2099-123456CUA” and no condition mentions it.");
  // the year alone is not every case filed that year
  assert.ok(search(all, { q: "2023", kind: "all" }).every(c => /\b2023\b/.test(`${c.title} ${c.text}`)));
  // an unknown case number says so
  assert.equal(search(all, { q: "2023-999999CUA" }).length, 0);
  assert.equal(noMatchNote(all, "2023-999999CUA"), "No motion on this page has the case number “2023-999999CUA” and no condition mentions it.");
  assert.ok(recordMatches(motion[0], parseQuery("2023-005418", all)));
  assert.ok(recordMatches(motion[0], parseQuery("005418", all)));
  assert.ok(!recordMatches(motion[0], parseQuery("odor", all)));
  assert.match(html, /recordMatches\(c, terms\) \? `<mark>\$\{esc\(c\.record\)\}<\/mark>`/);
});

test("the case number with an underscore, 2010.1070C_3, finds its motion as the card shows it, and shorter", () => {
  const want = search(all, { kind: "all" }).filter(c => c.record === "2010.1070C_3").map(c => `${c.record}#${c.number}`);
  assert.equal(want.length, 10);
  for (const q of ["2010.1070C_3", "2010.1070c_3", " 2010.1070C_3 ", "2010.1070C", "2010.1070", "1070C_3"]) {
    assert.deepEqual(search(all, { q, kind: "all" }).map(c => `${c.record}#${c.number}`), want, q);
  }
  // one case-number term, nothing left over as a word ("3" would ask for the number 3 in the text)
  assert.deepEqual(parseQuery("2010.1070C_3", all).map(t => [t.text, Boolean(t.record)]), [["2010.1070C_3", true]]);
  // words narrow it, and the card marks the case number
  const narrowed = search(all, { q: "2010.1070C_3 noise", kind: "all" });
  assert.ok(narrowed.length >= 1 && narrowed.length < want.length, String(narrowed.length));
  const c = all.find(x => x.record === "2010.1070C_3");
  assert.ok(recordMatches(c, parseQuery("2010.1070C_3", all)));
  // the hyphen and amendment forms are unchanged, and an underscore after a plain word is not a case number
  assert.deepEqual(parseQuery("2015-002658CUA-02", all).map(t => t.text), ["2015-002658CUA-02"]);
  assert.equal(search(all, { q: "2099.1070C_3", kind: "all" }).length, 0);
});

test("an address finds the conditions at it; the street type may be written out; words narrow it", () => {
  const at = all.filter(c => /^2351 Mission St\b/.test(c.address));
  assert.ok(at.length > 5);
  const want = search(all, { kind: "all" }).filter(c => /^2351 Mission St\b/.test(c.address)).map(c => `${c.record}#${c.number}`);
  for (const q of ["2351 Mission", "2351 mission st", "2351 Mission Street", "2351 MISSION ST."]) {
    assert.deepEqual(search(all, { q, kind: "all" }).map(c => `${c.record}#${c.number}`), want, q);
  }
  const noise = search(all, { q: "2351 Mission noise", kind: "all" });
  assert.ok(noise.length >= 1 && noise.every(c => c.address.startsWith("2351 Mission") && /nois|sound|amplif|loud/i.test(`${c.title} ${c.text}`)));
  // an avenue: "Ave" in the records, "Avenue" typed
  const ave = all.find(c => /^\d+ \w+ Ave\b/.test(c.address));
  const [num, street] = ave.address.split(" ");
  assert.ok(search(all, { q: `${num} ${street} Avenue`, kind: "all" }).some(c => c.address === ave.address));
  // ordinals: Planning writes "03Rd St" and "09Th Ave"
  const third = search(all, { q: "2505 3rd street", kind: "all" });
  assert.ok(third.length >= 1 && third.every(c => c.address.startsWith("2505 03Rd St")));
  // "W" for West, and the zip code without the street type
  const portal = search(all, { q: "36 W Portal Ave", kind: "all" });
  assert.ok(portal.length >= 1 && portal.every(c => c.address.startsWith("36 West Portal Ave")));
  assert.deepEqual(search(all, { q: "2351 Mission 94110", kind: "all" }).map(c => `${c.record}#${c.number}`), want);
  assert.ok(search(all, { q: "1210 9th avenue", kind: "all" }).length >= 1);
  // the card marks a matched address
  assert.ok(addressMatches(at[0], parseQuery("2351 Mission Street", all)));
  // a street name alone marks the address too (it finds every motion on the street); a plain word does not
  assert.ok(addressMatches(at[0], parseQuery("mission", all)));
  assert.ok(!addressMatches(at[0], parseQuery("noise", all)));
  assert.ok(!addressMatches(at[0], parseQuery("valencia", all)));
  assert.match(html, /addressMatches\(c, terms\) \? `<mark>\$\{esc\(c\.address\)\}<\/mark>`/);
  assert.match(html, /const terms = parseQuery\(f\.q, all\);/);
  // the label and tips say the search covers case numbers and addresses
  assert.match(html, /Search the conditions, a case number or an address/);
  assert.match(html, /a case\s+number \(2023-005418CUA\) or an address \(2351 Mission\)/);
});

test("a number, a street type or a zip code on its own searches the condition text only, never the address or the case number", () => {
  // the condition text alone, as before addresses and case numbers were searched
  const textOnly = q => all.filter(c => matchesTextOnly(c, q)).length;
  function matchesTextOnly(c, q) {
    const keys = new Set(tokenize(`${c.title} ${c.text}`).map(t => t.key));
    return tokenize(q).every(t => keys.has(t.key) || (/^\d{1,2}$/.test(t.key) && [...keys].some(k => new RegExp(`^${t.key}(?::\\d\\d)?[ap]m$`).test(k))));
  }
  // street types, numbers, zip codes and words that are not a street on the page (San Francisco is the city; "posted"
  // is not Post St, "pins" is not Pine St: street names are compared as written, not by their stem)
  for (const q of ["street", "st", "avenue", "ave", "place", "way", "2022", "500", "367", "94110", "cua", "san francisco",
    "street parking", "noise street", "posted", "pins", "24", "1st"]) {
    assert.equal(search(all, { q, kind: "all" }).length, textOnly(q), q);
    assert.ok(parseQuery(q, all).every(t => !t.street && !t.address), q);
  }
  // so "500 feet" is not the conditions at 500 Castro St that say feet: no address term, two words
  assert.deepEqual(parseQuery("500 feet", all).map(t => [t.text, Boolean(t.address)]), [["500", false], ["feet", false]]);
  // year ranges, number ranges and phone numbers are words, not case numbers
  for (const q of ["2019-2020", "1000-1500", "4155586378", "Ordinance 2019-0123"]) {
    assert.ok(parseQuery(q, all).every(t => !t.record && !t.caseText), q);
    assert.doesNotMatch(noMatchNote(all, q), /case number/, q);
  }
});

// The streets of the motions on the page, independently of search.js's index: street -> the motions on it.
const motionAddress = new Map(all.map(c => [c.record, c.address]));
const streets = new Map();
for (const [record, address] of motionAddress) {
  const st = streetOf(address);
  assert.ok(st, `${record}: no street in ${address}`);
  const key = `${st.name}|${st.type}`;
  if (!streets.has(key)) streets.set(key, { ...st, records: new Set() });
  streets.get(key).records.add(record);
}
const LONG = { st: ["Street"], ave: ["Avenue", "Av"], blvd: ["Boulevard", "Bl"], pl: ["Place"], plz: ["Plaza"], way: [] };
const SHORT = { st: "St", ave: "Ave", blvd: "Blvd", pl: "Pl", plz: "Plaza", way: "Way" };
const recordsOf = (q, kind = "all") => new Set(search(all, { q, kind }).map(c => c.record));
// the motions on a street (any type when none is given) and the motions with a condition whose text names it
const onStreet = (name, type) => new Set([...streets.values()].filter(s => s.name === name && (!type || !s.type || s.type === type))
  .flatMap(s => [...s.records]));
// (as words were searched before streets: every word of the name, and the type in any form, anywhere in it)
const namedInText = (name, type) => {
  const words = tokenize(name).map(t => t.key);
  const forms = type ? [type, ...LONG[type]].map(f => tokenize(f)[0].key) : [];
  return new Set(all.filter(c => {
    const keys = new Set(tokenize(`${c.title} ${c.text}`).map(t => t.key));
    return words.every(w => keys.has(w)) && (!forms.length || forms.some(f => keys.has(f)));
  }).map(c => c.record));
};

test("streets are read from the addresses: house numbers, ranges, unit letters, ordinals and street types", () => {
  for (const [address, name, type] of [
    ["2740 - 2744 Mission St, San Francisco, Ca 94110", "mission", "st"],
    ["1210 09Th Ave 94122", "9th", "ave"],
    ["101 - 115 06Th St, San Francisco, Ca", "6th", "st"],
    ["1000 Van Ness Ave Comml 94109", "van ness", "ave"],
    ["1096 South Van Ness Av, San Francisco, Ca", "south van ness", "ave"],
    ["412 Broadway 94133", "broadway", ""],
    ["401 - 407 Broadway, San Francisco, Ca 94133", "broadway", ""],
    ["2200 A Market St 94114", "market", "st"],
    ["2675 Geary Bl, San Francisco, Ca 94118", "geary", "blvd"],
    ["16 West Portal Av, San Francisco, Ca 94127", "west portal", "ave"],
    ["721 Lincoln Way 94122", "lincoln", "way"],
    ["0 Lakeshore Plaza, San Francisco, Ca 94132", "lakeshore", "plz"],
    ["1737 Post St 367 94115", "post", "st"],
  ]) assert.deepEqual(streetOf(address), { name, type }, address);
  assert.ok(streets.size >= 80, String(streets.size));
});

test("every street on the page: its name, alone or with its type short or long, finds every motion on it, plus the conditions that name it", () => {
  let checked = 0;
  for (const s of streets.values()) {
    const name = s.name.replace(/\b\w/g, ch => ch.toUpperCase());
    const queries = [[name, ""], ...(s.type ? [[`${name} ${SHORT[s.type]}`, s.type], ...LONG[s.type].map(l => [`${name} ${l}`, s.type])] : [])];
    for (const [q, type] of queries) {
      const got = recordsOf(q);
      const want = onStreet(s.name, type);
      for (const r of s.records) assert.ok(got.has(r), `"${q}" misses ${r} (${motionAddress.get(r)})`);
      // nothing else: the motions on the street and the motions with a condition naming it
      const expected = new Set([...want, ...namedInText(s.name, type)]);
      assert.deepEqual([...got].sort(), [...expected].sort(), q);
      // the query is one street term, and each card on the street marks its address
      const terms = parseQuery(q, all);
      assert.equal(terms.length, 1, q);
      assert.equal(terms[0].street, s.name, q);
      for (const c of search(all, { q, kind: "all" })) assert.equal(addressMatches(c, terms), want.has(c.record), `${q} ${c.record}`);
      checked++;
    }
  }
  assert.ok(checked >= 200, String(checked));
});

test("the owner's four streets: Valencia St, Mission, 24th St and Broadway return all their motions", () => {
  // motions with conditions on each street, per the address list; each is found, in every way of writing it
  const cases = [
    ["valencia", "st", ["Valencia St", "Valencia Street", "valencia", "VALENCIA ST."], 12],
    ["mission", "", ["Mission", "Mission St", "Mission Street", "mission st"], 18],
    ["24th", "st", ["24th St", "24Th St", "24th Street", "24 St", "24th"], 16],
    ["broadway", "", ["Broadway", "broadway"], 8],
  ];
  for (const [name, type, queries, count] of cases) {
    const want = onStreet(name, type);
    assert.equal(want.size, count, name);
    for (const q of queries) {
      const got = recordsOf(q);
      for (const r of want) assert.ok(got.has(r), `"${q}" misses ${r}`);
    }
  }
  // "Valencia St" used to find nothing and "Valencia" one motion, by its text
  assert.equal(recordsOf("Valencia St").size, 12);
  // a name with its type is that street only: 19th St is not 19th Ave, Geary St is not Geary Blvd
  assert.deepEqual([...recordsOf("19th St")].sort(), [...new Set([...onStreet("19th", "st"), ...namedInText("19th", "st")])].sort());
  assert.ok([...onStreet("19th", "ave")].every(r => !recordsOf("19th St").has(r) || namedInText("19th", "st").has(r)));
  assert.ok([...onStreet("19th", "ave"), ...onStreet("19th", "st")].every(r => recordsOf("19th").has(r)));
  // ordinals as Planning writes them, and typed: 09Th Ave
  for (const q of ["9th Ave", "9th Avenue", "09Th Ave", "9th Av", "9 Ave", "9th"]) {
    for (const r of onStreet("9th", "ave")) assert.ok(recordsOf(q).has(r), `${q} ${r}`);
  }
  // a direction may be a letter; a street named with one answers to its name without it unless another street has it
  assert.deepEqual(recordsOf("W Portal Ave"), recordsOf("West Portal Avenue"));
  assert.equal(parseQuery("Portal", all)[0].street, "west portal");
  assert.equal(parseQuery("Van Ness", all)[0].street, "van ness");
  assert.ok([...onStreet("south van ness", "")].every(r => !recordsOf("Van Ness Ave").has(r) || namedInText("van ness", "ave").has(r)));
  // other words narrow a street: "Mission noise" is the Mission St motions (or a condition naming Mission) with noise
  const noise = search(all, { q: "Mission noise", kind: "all" });
  assert.ok(noise.length >= 5);
  for (const c of noise) {
    assert.ok(onStreet("mission", "").has(c.record) || /\bmission\b/i.test(`${c.title} ${c.text}`), c.record);
    assert.match(`${c.title} ${c.text}`, /nois|sound|amplif|loud/i, c.record);
  }
  // a house number before the street stays an address
  assert.ok(parseQuery("2351 Mission", all)[0].address);
  // a type the street does not have finds no motion by its address: "Mission Ave"
  assert.ok([...recordsOf("Mission Ave")].every(r => namedInText("mission", "ave").has(r)));
  // the text of a matched condition marks the street words
  assert.equal(highlight("Along Valencia Street, near Mission", parseQuery("Valencia St", all), esc), "Along <mark>Valencia Street</mark>, near Mission");
  // the tips say a street finds its motions
  assert.match(html, /A street \(Valencia St, 24th St\) finds every motion on it/);
});

test("condition numbers sort by list, number, then lettered part", () => {
  // "2.3" is condition 3 of an older motion's second list (numbering restarted under a heading); it comes after
  // the whole first list, and a plain number or lettered part ("8A") never has a dot
  assert.deepEqual(numberOrder("12A"), [1, 12, "A"]);
  assert.deepEqual(numberOrder("2.3"), [2, 3, ""]);
  assert.deepEqual(numberOrder("2.10B"), [2, 10, "B"]);
  const base = { kind: "specific", decided: "2012-01-01", record: "2012.0262CUA" };
  const numbers = ["2.10", "2.3", "6", "1", "8B", "8A", "2.2", "10"];
  const sorted = numbers.map(number => ({ ...base, number })).sort(compare).map(c => c.number);
  assert.deepEqual(sorted, ["1", "6", "8A", "8B", "10", "2.2", "2.3", "2.10"]);
});

test("an address written as a range of house numbers answers to each number in it on the same side", () => {
  const recordsFor = q => [...new Set(search(all, { q, kind: "all" }).map(c => c.record))].sort();
  // "2740 - 2744 Mission St" (2010.0628C): 2740, 2742 and 2744, with or without the street type
  for (const q of ["2740 Mission", "2742 Mission St", "2744 Mission Street", "2740 mission st"]) {
    assert.ok(recordsFor(q).includes("2010.0628C"), q);
  }
  // 2744 Mission is also a 2019+ motion's own address: both are found
  assert.ok(recordsFor("2744 Mission Street").includes("2024-007818CUA"));
  // a number outside the range, or on the other side of the street, is not
  assert.ok(!recordsFor("2746 Mission").includes("2010.0628C"));
  assert.ok(!recordsFor("2741 Mission").includes("2010.0628C"));
  // "475 - 479 Broadway" (2010.0513C) and "1408 - 1414 California St" (2009.1056C)
  assert.ok(recordsFor("475 Broadway").includes("2010.0513C"));
  assert.ok(recordsFor("477 Broadway").includes("2010.0513C"));
  assert.ok(recordsFor("1410 California Street").includes("2009.1056C"));
  // every range address on the page answers to both of its ends
  const ranges = [...new Set(all.map(c => c.address))].filter(a => /^\d+\w?\s*-\s*\d+/.test(a));
  assert.ok(ranges.length >= 50, String(ranges.length));
  for (const a of ranges) {
    const [, lo, hi, street] = /^(\d+)\w?\s*-\s*(\d+)\w?\s+([^\s,]+(?:\s+[^\s,]+)?)/.exec(a);
    for (const n of [lo, hi]) {
      const words = street.split(/\s+/)[0];
      assert.ok(search(all, { q: `${n} ${words}`, kind: "all" }).some(c => c.address === a), `${n} ${words} -> ${a}`);
    }
  }
  // the range as the card shows it, whole or in part, still finds it
  for (const q of ["2740 - 2744 Mission St, San Francisco, Ca 94110", "2740 - 2744 Mission St", "2740-2744 Mission St", "2740 - 2744 Mission"]) {
    assert.deepEqual(search(all, { q, kind: "all" }).map(c => c.record).filter((r, i, a) => a.indexOf(r) === i), ["2010.0628C"], q);
  }
  // a range over 60 but within RANGE_MAX_SPAN: "1111 - 1175 California St"
  assert.ok(search(all, { q: "1141 California", kind: "all" }).some(c => /^1111 - 1175 California/.test(c.address)));
  // a plain address still works
  assert.ok(recordsFor("210 Church St").includes("2009.0773C"));
});

test("an older untitled condition is on its own page, marked exact, even when a finding repeats its opening words", () => {
  const find = (record, number) => all.find(c => c.record === record && String(c.number) === number);
  // the PDF does not print the generic title "Condition": matched on the words after it, the page is exact
  assert.deepEqual([find("2009.0773C", "14").page, find("2009.0773C", "14").page_exact], [14, true]);
  // the opening words are also in finding 2 (page 2); a longer passage is only on page 10, where the condition is
  assert.deepEqual([find("2010.0255C", "1").page, find("2010.0255C", "1").page_exact], [10, true]);
  // opening words on pages 5, 9 and 19; the longer passage only on 19
  assert.deepEqual([find("2010.1162C", "33").page, find("2010.1162C", "33").page_exact], [19, true]);
});
