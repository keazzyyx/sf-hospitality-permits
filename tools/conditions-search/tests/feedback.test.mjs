// The "Wrong or missing? Tell me" link on every result card: a real mailto: link to the site's contact address,
// with the case number and the condition number (and the title, the address, a link to the card and the motion
// page) in the subject and body, encoded so that "&", "#", "?", "+" and line breaks survive. The cards are made
// by index.html's own card(), run here on every condition of the real data (data/conditions.json). The link to the
// card in the email opens the page on that card: the page script runs here on the real data with the link's hash,
// and the card must be rendered, marked and scrolled to.
// Run: node --test tools/conditions-search/tests/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as searchModule from "../search.js";
import * as coverageModule from "../coverage.js";

const { FEEDBACK, KINDS, feedbackHref, feedbackLink, feedbackMessage, cardLink, cardTarget, cardIndex, stateFromHash,
  search } = searchModule;
const here = dirname(fileURLToPath(import.meta.url));
const data = JSON.parse(readFileSync(join(here, "..", "data", "conditions.json"), "utf8"));
const html = readFileSync(join(here, "..", "index.html"), "utf8");
const all = data.conditions;
const TO = "someone@example.org"; // the test's address; the public build puts its CONTACT in
const BASE = "https://sf-conditions-search.vercel.app/";
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const unesc = s => s.replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");

const PAGE = Number(html.match(/^const PAGE = (\d+);$/m)?.[1]);

/** A stand-in for the few parts of the browser the page script uses. Elements are made on first use and keep what
 * the page puts in them; replaceState writes the hash, as a browser does. */
function fakeBrowser({ hash = "", data = null } = {}) {
  const elements = new Map();
  const listeners = {};
  const scrolled = [];
  const element = id => ({
    id, value: "", innerHTML: "", textContent: "", style: {},
    scrollIntoView(opts) { scrolled.push({ id, opts, marginTop: this.style.scrollMarginTop }); },
    focus() { this.focused = true; },
  });
  const location = { origin: BASE.slice(0, -1), pathname: "/", hash };
  return {
    elements, listeners, scrolled, location,
    globals: {
      document: {
        getElementById: id => elements.get(id) ?? elements.set(id, element(id)).get(id),
        querySelector: sel => (sel === ".filters" ? { offsetHeight: 120 } : null),
      },
      location,
      history: { replaceState(_s, _t, url) { location.hash = url === "#" ? "" : url; } },
      window: { addEventListener(type, fn) { listeners[type] = fn; } },
      // no data: the page waits for ever, and only its functions are wanted
      fetch: () => (data ? Promise.resolve({ json: () => Promise.resolve(data) }) : new Promise(() => {})),
    },
  };
}

/** index.html's page script with its imports given as arguments, the browser stubbed (fakeBrowser), FEEDBACK_TO set
 * to `to` (as the public build sets it). Returns the page's card() function. */
function runPage(to, browser) {
  const m = html.match(/<script type="module">([\s\S]*?)<\/script>/);
  assert.ok(m, "index.html has no module script");
  const placeholder = 'const FEEDBACK_TO = "";';
  assert.equal(m[1].split(placeholder).length, 2, "index.html must declare FEEDBACK_TO once, empty");
  const modules = { "./search.js": searchModule, "./coverage.js": coverageModule };
  const deps = {};
  for (const [, names, from] of m[1].matchAll(/^import \{([^}]*)\} from "([^"]+)";$/gm)) {
    for (const name of names.split(",").map(s => s.trim()).filter(Boolean)) {
      assert.ok(name in modules[from], `${from} has no export ${name}`);
      deps[name] = modules[from][name];
    }
  }
  const body = m[1].replace(/^import .*$/gm, "").replace(placeholder, `const FEEDBACK_TO = ${JSON.stringify(to)};`);
  const { globals } = browser;
  const names = [...Object.keys(deps), ...Object.keys(globals)];
  const run = new Function(...names, `${body}\nreturn card;`);
  return run(...Object.values(deps), ...Object.values(globals));
}

/** The page's card() function, the data never loaded. */
const pageCard = to => runPage(to, fakeBrowser());

/** The page opened at `hash` with the real data, after it has rendered: its browser stand-in. */
async function openPage(hash) {
  const browser = fakeBrowser({ hash, data });
  runPage(TO, browser);
  await new Promise(resolve => setImmediate(resolve));
  return browser;
}

/** The cards in the page's results: [{ html, target }]. */
const renderedCards = browser => (browser.elements.get("results")?.innerHTML ?? "")
  .split(/(?=<article )/).filter(x => x.startsWith("<article "))
  .map(x => ({ html: x, target: x.startsWith('<article class="card target" id="target"') }));

/** The feedback links in a card's HTML: [{ href, label, text }], href and label un-escaped. */
function feedbackAnchors(cardHtml) {
  return [...cardHtml.matchAll(/<a class="feedback" href="([^"]*)" aria-label="([^"]*)">([^<]*)<\/a>/g)]
    .map(([, href, label, text]) => ({ href: unesc(href), label: unesc(label), text }));
}

/** A mailto: link taken apart: recipient, and every header decoded (decodeURIComponent, not form decoding). */
function parseMailto(href) {
  const m = href.match(/^mailto:([^?]*)\?(.*)$/s);
  assert.ok(m, `not a mailto link with headers: ${href.slice(0, 80)}`);
  const headers = Object.fromEntries(m[2].split("&").map(kv => {
    const [k, ...v] = kv.split("=");
    return [k, decodeURIComponent(v.join("="))];
  }));
  return { to: decodeURIComponent(m[1]), headers, rawQuery: m[2] };
}

test("every card on the page has one feedback link, to the address, naming its case and condition number", () => {
  const card = pageCard(TO);
  let checked = 0;
  for (const c of all) {
    const links = feedbackAnchors(card(c, []));
    assert.equal(links.length, 1, `${c.record} #${c.number}: ${links.length} feedback links`);
    const [{ href, label, text }] = links;
    assert.equal(text, "Wrong or missing? Tell me");
    assert.ok(label.startsWith("Wrong or missing? Tell me") && label.includes(c.record) && label.includes(c.number));
    const { to, headers, rawQuery } = parseMailto(href);
    assert.equal(to, TO);
    assert.deepEqual(Object.keys(headers), ["subject", "body"]);
    assert.ok(!/[\s#?]/.test(rawQuery), `${c.record} #${c.number}: unencoded space, # or ? in the link`);
    assert.equal(headers.subject, `Wrong or missing: ${c.record}, condition ${c.number}`);
    const lines = headers.body.split("\r\n");
    assert.ok(lines.includes(`Case number: ${c.record}`), `${c.record} #${c.number}: no case number line`);
    assert.ok(lines.includes(`Condition number: ${c.number}`), `${c.record} #${c.number}: no condition number line`);
    assert.ok(lines.includes(`Address: ${c.address}`), `${c.record} #${c.number}: no address line`);
    assert.ok(lines.includes(`Condition title: ${c.title}`), `${c.record} #${c.number}: no title line`);
    // the link to the card is a search for its case number with every kind shown, which finds this condition
    const link = lines.find(l => l.startsWith("Link to its card: ")).slice("Link to its card: ".length);
    assert.equal(link, BASE + "#q=" + encodeURIComponent(c.record).replace(/%20/g, "+") + "&kind=all&card="
      + encodeURIComponent(c.number));
    assert.deepEqual(stateFromHash(new URL(link).hash), { q: c.record, business: "", category: "", zoning: "", year: "", kind: "all" });
    assert.deepEqual(cardTarget(new URL(link).hash), { record: c.record, number: String(c.number) });
    // the motion page, made absolute against the page (the local data links pdf/<record>.pdf)
    assert.ok(lines.includes(`Motion page: ${new URL(c.pdf + (c.page ? "#page=" + c.page : ""), BASE).href}`));
    // every line break the email adds is CRLF
    assert.equal(lines.join("").includes("\n"), `${c.title}${c.address}`.includes("\n"));
    checked++;
  }
  assert.equal(checked, all.length);
  assert.ok(checked >= 5000, `only ${checked} conditions`);
});

test("the link to a card finds that card: every condition is in its link's search, under its own number", () => {
  // one search per motion (the search is the same for all of a motion's conditions), through the real search
  const byRecord = Map.groupBy(all, c => c.record);
  const notFound = [];
  for (const [record, conditions] of byRecord) {
    const hits = search(all, stateFromHash(new URL(cardLink(conditions[0], BASE)).hash));
    for (const c of conditions) {
      const at = cardIndex(hits, cardTarget(new URL(cardLink(c, BASE)).hash));
      if (at < 0 || hits[at] !== c) notFound.push(`${record} #${c.number}`);
    }
  }
  // every one, 2010.1070C_3 (the case number with an underscore) included
  assert.deepEqual(notFound, []);
  assert.ok(byRecord.size >= 350, `only ${byRecord.size} motions`);
});

test("the link to a card opens the page on that card: shown, marked once and scrolled to, past the first page too", async () => {
  assert.ok(PAGE > 0, "index.html has no PAGE");
  // for each motion, its condition that comes last in the link's search (the one most likely to be past the first
  // page of cards); 2015-009955CUA has 51 conditions, so its last one is card 51 with PAGE = 50
  const byRecord = Map.groupBy(all, c => c.record);
  let pastFirstPage = 0;
  for (const conditions of byRecord.values()) {
    const hits = search(all, stateFromHash(new URL(cardLink(conditions[0], BASE)).hash));
    const c = hits.filter(x => conditions.includes(x)).at(-1);
    const browser = await openPage(new URL(cardLink(c, BASE)).hash);
    const cards = renderedCards(browser);
    const marked = cards.filter(x => x.target);
    assert.equal(marked.length, 1, `${c.record} #${c.number}: ${marked.length} marked cards of ${cards.length}`);
    assert.ok(marked[0].html.includes(`<span class="num">${esc(c.number)}.</span>`), `${c.record} #${c.number}: wrong card marked`);
    assert.ok(marked[0].html.includes(esc(c.record)), `${c.record} #${c.number}: wrong motion marked`);
    assert.equal(cards.indexOf(marked[0]), hits.indexOf(c));
    assert.deepEqual(browser.scrolled.map(x => x.id), ["target"]);
    assert.equal(browser.scrolled[0].marginTop, "130px"); // below the sticky filters (120px here) and 10px more
    assert.ok(browser.elements.get("target").focused);
    // the page writes its fields back to the hash and leaves the card out
    assert.equal(browser.location.hash, "#q=" + encodeURIComponent(c.record).replace(/%20/g, "+") + "&kind=all");
    if (hits.indexOf(c) >= PAGE) pastFirstPage++;
  }
  assert.ok(pastFirstPage >= 1, "no card past the first page was checked");
});

test("the marked card is forgotten after it is shown, and a new link marks its own card", async () => {
  const c = all.find(x => x.record === "2015-009955CUA" && String(x.number) === "30");
  assert.ok(c, "2015-009955CUA #30 is not in the data");
  const browser = await openPage(new URL(cardLink(c, BASE)).hash);
  assert.equal(renderedCards(browser).filter(x => x.target).length, 1);
  // "Clear filters": a new render, no card marked, back to the first page
  browser.elements.get("reset").onclick();
  assert.equal(renderedCards(browser).filter(x => x.target).length, 0);
  assert.equal(renderedCards(browser).length, PAGE);
  // a link to another card opened in the same tab (hashchange)
  const other = all.find(x => x.record === "2010.1070C_3");
  browser.location.hash = new URL(cardLink(other, BASE)).hash;
  browser.listeners.hashchange();
  const marked = renderedCards(browser).filter(x => x.target);
  assert.equal(marked.length, 1);
  assert.ok(marked[0].html.includes(`<span class="num">${esc(other.number)}.</span>`) && marked[0].html.includes(esc(other.record)));
  assert.equal(browser.scrolled.length, 2);
  // a hash that names no card, or a card not in its results, marks nothing
  const otherKind = KINDS.map(([v]) => v).find(v => v && v !== "all" && v !== c.kind);
  for (const hash of ["#q=2010.1070C_3&kind=all", "#q=2010.1070C_3&kind=all&card=999", `#q=2015-009955CUA&card=30&kind=${otherKind}`]) {
    browser.location.hash = hash;
    browser.listeners.hashchange();
    assert.equal(renderedCards(browser).filter(x => x.target).length, 0, hash);
  }
  assert.equal(browser.scrolled.length, 2);
});

test("&, #, ?, +, %, $ and line breaks in a title or an address are encoded and come back unchanged", () => {
  const c = {
    record: "2023-005418CUA", number: "12a", title: "Noise & odor #1? Yes + no, 100% ($&)",
    address: "2351 Mission St #2 & 3\nUnit ?b", pdf: "https://files.example.org/motions/2023-005418CUA.pdf", page: 7,
  };
  const href = feedbackHref(c, { to: TO, base: BASE });
  const { to, headers, rawQuery } = parseMailto(href);
  assert.equal(to, TO);
  // the only "&" and "=" in the link are the two headers' own
  assert.equal(rawQuery.split("&").length, 2);
  assert.ok(!/[\s#?\n]/.test(rawQuery));
  assert.match(rawQuery, /%26/); // &
  assert.match(rawQuery, /%23/); // #
  assert.match(rawQuery, /%3F/); // ?
  assert.match(rawQuery, /%2B/); // + (a form decoder would read a bare + as a space)
  assert.match(rawQuery, /%0D%0A/); // CRLF line breaks
  assert.equal(headers.subject, "Wrong or missing: 2023-005418CUA, condition 12a");
  assert.equal(headers.body, [
    "About this condition:",
    "Case number: 2023-005418CUA",
    "Condition number: 12a",
    "Condition title: Noise & odor #1? Yes + no, 100% ($&)",
    "Address: 2351 Mission St #2 & 3\nUnit ?b",
    "Link to its card: https://sf-conditions-search.vercel.app/#q=2023-005418CUA&kind=all&card=12a",
    "Motion page: https://files.example.org/motions/2023-005418CUA.pdf#page=7",
    "",
    "What is wrong or missing:",
    "",
    "",
  ].join("\r\n"));
  // decoded the way a form decoder would (URLSearchParams), it is the same: no bare "+" stands for a space
  const p = new URLSearchParams(rawQuery);
  assert.equal(p.get("subject"), headers.subject);
  assert.equal(p.get("body"), headers.body);
  // and as HTML: the attribute is escaped, the text is fixed
  const a = feedbackLink(c, { to: TO, base: BASE }, esc);
  assert.ok(a.startsWith('<a class="feedback" href="mailto:someone@example.org?subject=') && a.includes("&amp;body="));
  assert.ok(a.endsWith(">Wrong or missing? Tell me</a>"));
  assert.equal(feedbackAnchors(a)[0].href, href);
});

test("a real title with curly quotes and dashes is encoded as UTF-8 and comes back unchanged", () => {
  const c = all.find(x => /[‘’–‐]/.test(x.title));
  assert.ok(c, "no title with a curly quote or dash in the data");
  const { headers } = parseMailto(feedbackHref(c, { to: TO, base: BASE }));
  assert.ok(headers.body.split("\r\n").includes(`Condition title: ${c.title}`));
});

test("no address, a bad address or no page: no link; without a base the email still names case and condition", () => {
  const c = all[0];
  assert.equal(feedbackHref(c, {}), null);
  assert.equal(feedbackHref(c, { to: "" }), null);
  for (const bad of ["not an address", "a@b", "a@b.org?cc=x@y.org", "a@b.org&body=x", "a b@c.org", "a@b.org#x"]) {
    assert.equal(feedbackHref(c, { to: bad }), null, bad);
  }
  assert.equal(feedbackLink(c, { to: "" }, esc), "");
  // the local page leaves FEEDBACK_TO empty: its cards have no feedback link
  const localCard = pageCard("");
  assert.deepEqual(feedbackAnchors(localCard(c, [])), []);
  assert.ok(!localCard(c, []).includes("Wrong or missing"));
  // no base: no card link, and a relative motion link is left out rather than sent as a bare path
  const { subject, body } = feedbackMessage({ ...c, pdf: "pdf/x.pdf" });
  assert.equal(subject, `Wrong or missing: ${c.record}, condition ${c.number}`);
  assert.ok(body.includes(`Case number: ${c.record}`) && body.includes(`Condition number: ${c.number}`));
  assert.ok(!body.includes("Link to its card") && !body.includes("Motion page"));
  // an absolute motion link (the public data) is kept without a base
  assert.ok(feedbackMessage({ ...c, pdf: "https://files.example.org/m.pdf", page: 3 }).body
    .includes("Motion page: https://files.example.org/m.pdf#page=3"));
});

test("the feedback wording is kept in FEEDBACK, and the address is not written in the page or search.js", () => {
  assert.equal(FEEDBACK.text, "Wrong or missing? Tell me");
  const js = readFileSync(join(here, "..", "search.js"), "utf8");
  for (const text of [html, js]) assert.ok(!/[\w.+-]+@(gmail|example)\.(com|org)/.test(text), "an address is hard-coded");
});
