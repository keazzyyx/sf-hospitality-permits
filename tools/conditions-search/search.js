// Search, filter and sort for the conditions page. Plain ES module: the page imports it, and so does the test
// (tests/search.test.mjs, run with `node --test`).
//
// Search rules
// - Every word typed must appear in the condition (title or text), in any order.
// - Simple word endings do not matter: guard / guards / guarded / guarding, odor / odors, close / closing.
//   A few words are their own word and keep their ending (KEEP_ENDING): parking is not park, news is not new.
// - Single letters are ignored, except "a.m." / "p.m." on their own, which find any morning / evening time.
// - Times match however they are written: "10 p.m.", "10pm", "10 PM", "10:00 p.m." and "10:00PM" are the same.
//   A bare number matches that hour too ("10" finds "10:00 p.m.").
// - A short synonym list, SYNONYM_GROUPS below, covers a few things the motions say in different words. The page
//   shows the list under "Search tips".
// - A case number finds its motion's conditions: "2023-005418CUA", "2023-005418", "005418", "2015-002658CUA-02",
//   "2011.0097CUA-02", "2010.1070C_3". A house number followed by its street finds the conditions at that address:
//   "2351 Mission", "2351 Mission Street". Other words narrow either: "2351 Mission noise".
// - A street name with no house number finds every motion on that street, and the conditions whose text names it:
//   "Valencia St", "Mission", "24th St", "9th Avenue", "Broadway", "Van Ness Ave". It counts as a street only when
//   a motion on the page is on it; a number, a street type or a zip code on its own ("2022", "500 feet", "street",
//   "st", "94110") stays an ordinary search word and searches the condition text only.

// Synonym groups. Within a group every entry counts as every other: a query word (or two-word phrase) that is in a
// group also finds conditions that use any other entry of the group. Entries are written as you would type them
// and go through the same rules as the search (endings and time forms do not matter: "guard" also covers "guards",
// "12 a.m." covers "12:00 AM"). A two-word entry ("security personnel") matches those words side by side, in that
// order. Keep the list short and literal: each group widens every search that uses one of its words.
// "security staff", not "staff" alone: on these motions "staff" is always Planning Department staff ("subject to
// Department staff review"), so a bare "staff" would make "guard" find those.
export const SYNONYM_GROUPS = [
  ["guard", "security guard", "security personnel", "security staff", "security officer", "bouncer", "doorman", "door staff"],
  ["hours", "closing time", "opening hours"],
  ["noise", "sound", "amplified", "loud"],
  ["live music", "live entertainment", "live performance"],
  ["midnight", "12 a.m."],
  ["odor", "odour"],
  ["liquor", "alcohol", "alcoholic"],
];

// Said when a search finds nothing because none of a group's words is on any motion. Keyed by the group's first
// entry. Security staffing is set in the Entertainment Commission permit (its security plan) or the ABC licence, which
// this page does not include; the closest Planning condition is the notice asking patrons to leave quietly.
// noMatchNote adds it only for a word no condition on the page uses, so the wording holds whenever it shows. Today
// four conditions on 2010-2018 motions use the guard group, so it does not show (the tests check it on data
// without them).
export const GROUP_NOTES = {
  guard: "Planning's motions here set no security guard or security staff condition: security staffing is usually " +
    "a condition of the Entertainment Commission permit or the state (ABC) liquor licence, which this page does not " +
    "include. For the related Planning condition, the notice asking patrons to leave quietly, search “patrons”.",
};

// Filter values for "Which conditions". The default ("") hides approval boilerplate.
export const KINDS = [
  ["", "Case-specific, then standard (no boilerplate)"],
  ["specific", "Case-specific only"],
  ["standard", "Standard only"],
  ["boilerplate", "Approval boilerplate only"],
  ["all", "Everything, including boilerplate"],
];
const KIND_ORDER = { specific: 0, standard: 1, boilerplate: 2 };

// "10:00 p.m.", "10pm", "10 P.M", "7:OOam" (OCR), "10.30 pm"
const TIME = /\b(\d{1,2})(?:[:.]([0-5]\d|[oO]{2}))?\s?([ap])\.?\s?m\b\.?/gi;
const WORD = /[a-z0-9]+(?:['’][a-z]+)?/gi;

// Words whose ending is part of the word: they are not the plural or -ing form of a shorter word. Plurals of these
// still meet them ("buildings" -> "building").
export const KEEP_ENDING = new Set([
  "parking", "building", "housing", "planning", "morning", "evening", "ceiling", "clothing", "dwelling", "meeting",
  "wedding", "during", "nothing", "something", "anything", "everything", "string", "news", "always", "perhaps",
  "series", "whereas",
]);

/** A light English stemmer: enough that plural/singular and -ing/-ed forms meet. */
export function stem(word) {
  let w = word.toLowerCase().replace(/['’]s$/, "");
  if (/^\d/.test(w) || w.length <= 3 || KEEP_ENDING.has(w)) return w;
  if (KEEP_ENDING.has(w.slice(0, -1)) && w.endsWith("s")) return w.slice(0, -1);
  if (w.endsWith("ies") && w.length > 4) w = w.slice(0, -3) + "y";
  else if (/(?:ss|us|is)$/.test(w)) { /* glass, bus, this: not plurals */ }
  else if (/(?:ches|shes|sses|xes|zes)$/.test(w)) w = w.slice(0, -2);
  else if (w.endsWith("s")) w = w.slice(0, -1);
  if (w.endsWith("ied") && w.length > 4) w = w.slice(0, -3) + "y";
  else if (w.endsWith("ing") && w.length > 5 && /[aeiouy]/.test(w.slice(0, -3))) w = w.slice(0, -3);
  else if (/[^e]ed$/.test(w) && w.length > 4) w = w.slice(0, -2);
  if (/([b-df-hj-np-tv-xz])\1$/.test(w) && !/(?:ll|ss|zz|ff)$/.test(w)) w = w.slice(0, -1);
  if (w.endsWith("e") && w.length > 3) w = w.slice(0, -1);
  return w;
}

function timeKey(hour, minutes, ap) {
  const h = String(Number(hour));
  const m = minutes && !/^(00|oo)$/i.test(minutes) ? ":" + minutes : "";
  return `${h}${m}${ap.toLowerCase()}m`;
}

/** Words of a text with their positions and match keys. Times come out as one token ("10pm"). */
export function tokenize(text) {
  const s = String(text ?? "");
  const out = [];
  const taken = [];
  for (const m of s.matchAll(TIME)) {
    out.push({ start: m.index, end: m.index + m[0].length, key: timeKey(m[1], m[2], m[3]) });
    taken.push([m.index, m.index + m[0].length]);
  }
  for (const m of s.matchAll(WORD)) {
    const start = m.index, end = start + m[0].length;
    if (taken.some(([a, b]) => start < b && end > a)) continue;
    out.push({ start, end, key: stem(m[0]) });
  }
  return out.sort((a, b) => a.start - b.start);
}

// Each group entry as its match keys joined by a space: "security personnel" -> "security personnel",
// "hours" -> "hour", "12 a.m." -> "12am".
const phraseKey = text => tokenize(text).map(t => t.key).join(" ");
const GROUP_KEYS = SYNONYM_GROUPS.map(group => group.map(phraseKey));
/** The synonym group a word or phrase (as match keys, "security personnel") belongs to, or null. */
function groupOf(key) {
  return GROUP_KEYS.find(keys => keys.includes(key)) || null;
}
const MAX_PHRASE = Math.max(...GROUP_KEYS.flat().map(k => k.split(" ").length));

// ---- addresses and case numbers --------------------------------------------------------------------------------
// An address is a house number followed by its street, as on the motion: "2351 Mission", "2351 Mission St",
// "2351 Mission Street", "2505 3rd Street" (Planning writes "2505 03Rd St"). It is recognised only when those
// words begin an address that is on the page (searchIndex), so a number on its own ("500 feet", "2022", a zip
// code) stays an ordinary search word and never matches an address. A street name on its own is a street term
// (see STREETS below). Street types go to the short form on both sides, and ordinals lose their leading zero.
const STREET_TYPES = [["street", "st"], ["avenue", "ave"], ["av", "ave"], ["boulevard", "blvd"], ["bl", "blvd"],
  ["place", "pl"], ["drive", "dr"], ["terrace", "ter"], ["road", "rd"], ["lane", "ln"], ["court", "ct"],
  ["plaza", "plz"], ["way", "way"]];
const STREET_KEY = new Map([
  ...STREET_TYPES.map(([long, short]) => [stem(long), stem(short)]),
  ["w", "west"], ["e", "east"], ["n", "north"], ["s", "south"],
]);
const SHORT_TYPES = new Set(STREET_TYPES.map(([, short]) => stem(short)));
const addressKey = key => STREET_KEY.get(key) || key.replace(/^0+(?=\d+(?:st|nd|rd|th)$)/, "");
/** An address as its match keys: "2505 03Rd St 94107" -> ["2505", "3rd", "st", "94107"]. */
export const addressKeys = address => tokenize(address).map(t => addressKey(t.key));
// Planning writes many addresses as a range of house numbers: "2740 - 2744 Mission St". Such an address answers to
// each number in the range on the same side of the street (2740, 2742, 2744), as a single address does; a range wider
// than RANGE_MAX_SPAN answers to its two ends only.
const RANGE = /^\s*(\d+)[a-z]?\s*[-\u2010-\u2015]\s*(\d+)[a-z]?\s+(.*)$/i;
const RANGE_MAX_SPAN = 100;
function houseNumbers(a, b) {
  const [from, to] = a <= b ? [a, b] : [b, a];
  if (to < from || to - from > RANGE_MAX_SPAN) return to > from ? [from, to] : [from];
  const out = [];
  for (let n = from; n <= to; n += (to - from) % 2 === 0 ? 2 : 1) out.push(n);
  if (out[out.length - 1] !== to) out.push(to);
  return out;
}
/** The ways an address may be typed, as match keys: as written, without its street type ("2351 mission
 * 94110"), and for a range of house numbers each number in it (see RANGE). */
function addressVariants(address) {
  const m = RANGE.exec(String(address ?? ""));
  // the address as written first (so "2740 - 2744 Mission St", typed or pasted as the card shows it, still finds it),
  // then one address per house number in the range
  const singles = [String(address ?? ""), ...(m ? houseNumbers(Number(m[1]), Number(m[2])).map(n => `${n} ${m[3]}`) : [])];
  const out = [];
  for (const one of singles) {
    const k = addressKeys(one);
    const bare = k.filter((x, i) => i < 2 || !SHORT_TYPES.has(x));
    out.push(k);
    if (bare.length !== k.length) out.push(bare);
  }
  return out;
}

// A case number as typed or as shown: "2023-005418CUA", "2023-005418", "2023-005418 CUA", "2023005418cua",
// "2015-002658CUA-02", "2011.0097CUA-02", "2011.0097", and "2010.1070C_3", the one case number on the page with an
// underscore and a number after its suffix, as Planning's data lists it (the underscore is read as the hyphen of
// "-02" is). Compared without punctuation, as the start of the motion's case number. It is a case-number term only
// when it starts a case number on the page; one that does not (an earlier case quoted in a condition,
// "2013.0023C") is searched in the condition text as one phrase. Year ranges ("2019-2020"), phone numbers and
// other plain numbers do not have this shape and stay ordinary words.
const RECORD = /\b\d{4}(?:-\d{6}|\.\d{4}|\d{6}(?=[a-z]))(?:([\s-]?)[a-z]{1,8}(?:\b|(?=_\d)))?(?:[-_]\d{1,2}\b)?/gi;
// The serial part with its suffix and amendment: "002658CUA-02", "0097CUA-02", "1070C_3".
const SERIAL = /\b\d{4,6}[a-z]{1,8}[-_]\d{1,2}\b/gi;
const compactRecord = r => String(r ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
// The serial part of a case number on its own ("005418", "005418CUA", "0097CUA") also finds the motion, when it is
// six digits or starts with a zero, so a plain number such as "2022" or "1036" is never read as one.
function recordParts(record) {
  const m = /^\d{4}[-.]?(\d{4,6})([a-z]*)(?:[-_](\d{1,2}))?$/i.exec(String(record ?? "").trim());
  if (!m) return [];
  const [, num, suffix = "", amend = ""] = m;
  const sfx = suffix.toLowerCase();
  const out = [];
  if (sfx) out.push(num + sfx, num + sfx + amend);
  if (num.length === 6 || num.startsWith("0")) out.push(num);
  return out;
}

// ---- streets ------------------------------------------------------------------------------------------------------
// The street of an address is the words after the house number (or range of house numbers) up to and including
// the street type, if it has one: "2740 - 2744 Mission St, San Francisco" -> mission / st, "1210 09Th Ave 94122" ->
// 9th / ave, "1000 Van Ness Ave Comml" -> van ness / ave, "412 Broadway 94133" -> broadway / no type,
// "2200 A Market St" -> market / st (a unit letter after the house number is not part of the street).
// A street name is compared word for word as written, not by its stem, so "posted" is not Post St and "pins" is not
// Pine St; directions ("W" -> west) and ordinals ("09Th" -> 9th) are normalised as in addresses. A query word that
// is a street name, optionally followed by a street type, finds every motion on that street (the type, when typed,
// must be the street's own: "19th St" is not 19th Ave) or a condition whose text has those words, as before streets
// were searched (anywhere in the condition; the type in any of its forms, so "Valencia St" counts "Valencia" with
// "St" or "Street"). An ordinal street may be typed without its
// suffix when its type follows: "24 St" is 24th St. A bare number ("24") stays a number. A street named with a
// direction answers to its name without it when no other street has that name: "Portal" is West Portal Ave, but
// "Van Ness" is Van Ness Ave only (South Van Ness Ave is another street).
const DIRECTIONS = new Map([["w", "west"], ["e", "east"], ["n", "north"], ["s", "south"]]);
/** A word as a street-name word: lower case, as written, direction letters spelled out, ordinals without zeros. */
const nameWord = raw => {
  const w = String(raw).toLowerCase().replace(/['’]s$/, "");
  return DIRECTIONS.get(w) || w.replace(/^0+(?=\d+(?:st|nd|rd|th)$)/, "");
};
/** The street type a word stands for ("street" -> "st", "Av" -> "ave"), or null. */
const typeOf = raw => {
  const k = addressKey(stem(String(raw)));
  return SHORT_TYPES.has(k) ? k : null;
};
// Every way a street type is written, as match keys: "st" -> ["st", "street"], "ave" -> ["ave", "avenu", "av"].
const TYPE_FORMS = new Map();
for (const [long, short] of STREET_TYPES) {
  const k = stem(short);
  if (!TYPE_FORMS.has(k)) TYPE_FORMS.set(k, [k]);
  if (!TYPE_FORMS.get(k).includes(stem(long))) TYPE_FORMS.get(k).push(stem(long));
}
const ordinal = n => {
  const v = Number(n), t = v % 100;
  return `${v}${t >= 11 && t <= 13 ? "th" : ["th", "st", "nd", "rd"][v % 10] || "th"}`;
};
const HOUSE = /^\s*\d+[a-z]?(?:\s*[-\u2010-\u2015]\s*\d+[a-z]?)?\s+/i;
/** The street an address is on: { name: "van ness", type: "ave" | "" }, or null when it has none. */
export function streetOf(address) {
  const head = String(address ?? "").split(",")[0].replace(HOUSE, "");
  const words = [...head.matchAll(WORD)].map(m => m[0]);
  while (words.length && /^[a-z]$/i.test(words[0]) && !DIRECTIONS.has(words[0].toLowerCase())) words.shift();
  const name = [];
  let type = "";
  for (const w of words) {
    const t = name.length ? typeOf(w) : null;
    if (t) { type = t; break; }
    if (/^\d+$/.test(w)) break; // a zip code or unit number ends a street with no type
    name.push(nameWord(w));
  }
  return name.length ? { name: name.join(" "), type } : null;
}

const INDEX = new WeakMap();
/** What the query parser needs to know about the data: every address start of two or more words ("2351 mission",
 * "2351 mission st", ...), every serial part of a case number, and every street a motion is on (name -> its
 * types, "" for none). Cached per data array. */
export function searchIndex(all) {
  if (!all) return null;
  let ix = INDEX.get(all);
  if (!ix) {
    const prefixes = new Set(), parts = new Set(), records = new Set(), streets = new Map();
    for (const c of all) {
      const st = streetOf(c.address);
      if (st) {
        if (!streets.has(st.name)) streets.set(st.name, new Set());
        streets.get(st.name).add(st.type);
      }
      for (const k of addressVariants(c.address)) {
        if (/^\d/.test(k[0] || "")) for (let n = 2; n <= k.length; n++) prefixes.add(k.slice(0, n).join(" "));
      }
      for (const part of recordParts(c.record)) parts.add(part);
      records.add(compactRecord(c.record));
    }
    // a street named with a direction also answers to its name without it ("Portal" is West Portal Ave), unless that
    // is another street's name ("Van Ness" is Van Ness Ave, not South Van Ness Ave)
    const streetAlias = new Map();
    for (const name of streets.keys()) {
      const [first, ...rest] = name.split(" ");
      if (rest.length && [...DIRECTIONS.values()].includes(first) && !streets.has(rest.join(" "))) {
        streetAlias.set(rest.join(" "), name);
      }
    }
    ix = { prefixes, parts, records: [...records], streets, streetAlias,
      maxAddress: Math.max(2, ...[...prefixes].map(x => x.split(" ").length)),
      maxStreet: Math.max(1, ...[...streets.keys()].map(x => x.split(" ").length)) };
    INDEX.set(all, ix);
  }
  return ix;
}

const TIME_KEY = /^\d{1,2}(?::\d\d)?[ap]m$/;

/** The query as a list of terms. Each term has the set of keys that satisfy it (alts: a single word's key, or a
 * phrase's keys joined by a space), and for a bare hour ("10") or a bare "a.m."/"p.m." a pattern that time keys
 * must match. `text` is the word or phrase as typed. Two query words that make up a synonym-group phrase
 * ("closing time") are one term. With the data (`all`), a case number is one term (`record`), as is its serial part
 * (`recordPart`), a house number followed by its street is one term (`address`), and a street name on its own,
 * with or without its type, is one term (`street`, `streetType`); without it (highlighting a string) only full
 * case numbers are recognised. */
export function parseQuery(q, all) {
  const ix = searchIndex(all);
  const s = String(q ?? "");
  const terms = [];
  // case numbers first, as one term each; their characters are blanked, and no phrase runs across one
  const spans = [];
  const onPage = compact => !ix || ix.records.some(r => r.startsWith(compact));
  for (const m of s.matchAll(RECORD)) {
    // "2023-005418 CUA" is the case number with its suffix; "2023-005418 odor" is the case number and a word
    let text = m[0];
    if (m[1] && /\s/.test(m[1]) && !onPage(compactRecord(text))) text = text.slice(0, text.search(/\s/));
    const compact = compactRecord(text);
    if (onPage(compact)) {
      terms.push({ key: compact, text, alts: new Set(), pattern: null, record: compact });
    } else {
      // not a case number on the page: the same characters in a condition's text
      const key = tokenize(text).map(t => t.key).join(" ");
      terms.push({ key, text, alts: new Set([key]), pattern: null, caseText: true });
    }
    spans.push([m.index, m.index + text.length]);
  }
  if (ix) {
    for (const m of s.matchAll(SERIAL)) {
      if (spans.some(([a, b]) => m.index < b && m.index + m[0].length > a) || !ix.parts.has(compactRecord(m[0]))) continue;
      terms.push({ key: compactRecord(m[0]), text: m[0], alts: new Set(), pattern: null, recordPart: compactRecord(m[0]) });
      spans.push([m.index, m.index + m[0].length]);
    }
  }
  let blanked = s;
  for (const [a, b] of spans) blanked = blanked.slice(0, a) + " ".repeat(b - a) + blanked.slice(b);
  const toks = tokenize(blanked);
  const joined = (i, n) => {
    const run = toks.slice(i, i + n);
    if (run.length < n) return false;
    for (let j = 1; j < run.length; j++) if (spans.some(([a, b]) => a >= run[j - 1].end && b <= run[j].start)) return false;
    return true;
  };
  for (let i = 0; i < toks.length; i++) {
    const t = toks[i], next = toks[i + 1];
    // a house number followed by its street, longest first
    if (ix && /^\d/.test(t.key) && !TIME_KEY.test(t.key)) {
      let found = 0;
      for (let n = Math.min(ix.maxAddress, toks.length - i); n >= 2 && !found; n--) {
        if (joined(i, n) && ix.prefixes.has(toks.slice(i, i + n).map(x => addressKey(x.key)).join(" "))) found = n;
      }
      if (found) {
        const key = toks.slice(i, i + found).map(x => addressKey(x.key)).join(" ");
        terms.push({ key, text: s.slice(t.start, toks[i + found - 1].end), alts: new Set(), pattern: null, address: key });
        i += found - 1;
        continue;
      }
    }
    // the serial part of a case number
    if (ix && ix.parts.has(t.key)) {
      terms.push({ key: t.key, text: s.slice(t.start, t.end), alts: new Set(), pattern: null, recordPart: t.key });
      continue;
    }
    // a street name, longest first, with its type if one follows ("Valencia St", "Van Ness Avenue", "24th St");
    // an ordinal street may be typed without its suffix when its type follows ("24 St")
    if (ix) {
      const raw = j => nameWord(s.slice(toks[j].start, toks[j].end));
      let street = null;
      for (let n = Math.min(ix.maxStreet, toks.length - i); n >= 1 && !street; n--) {
        if (!joined(i, n)) continue;
        const name = toks.slice(i, i + n).map((_, j) => raw(i + j)).join(" ");
        if (ix.streets.has(name) || ix.streetAlias.has(name)) street = { name, n, is: ix.streetAlias.get(name) || name };
      }
      if (!street && /^\d{1,3}$/.test(t.key) && next && joined(i, 2) && typeOf(s.slice(next.start, next.end))
        && ix.streets.has(ordinal(t.key))) street = { name: ordinal(t.key), n: 1, is: ordinal(t.key) };
      if (street) {
        const after = toks[i + street.n];
        const type = after && joined(i, street.n + 1) ? typeOf(s.slice(after.start, after.end)) : null;
        const n = street.n + (type ? 1 : 0);
        const last = toks[i + n - 1];
        // the text side, as the words were searched before streets were: every word of the name, and the type in
        // any of its forms, anywhere in the condition (`textWords`, one set of alternatives per word). `alts` is
        // what the highlighter marks: the name with its type side by side first, then each word.
        const words = tokenize(street.name).map(x => x.key);
        const forms = type ? TYPE_FORMS.get(type) : [];
        const textWords = [...words.map(w => [w]), ...(type ? [forms] : [])];
        const alts = new Set([...(type ? forms.map(f => `${words.join(" ")} ${f}`) : [words.join(" ")]), ...words, ...forms]);
        terms.push({ key: type ? `${street.is} ${type}` : street.is, text: s.slice(t.start, last.end), alts,
          pattern: null, street: street.is, streetType: type || "", textWords });
        i += n - 1;
        continue;
      }
    }
    // a phrase from a synonym group, longest first
    let phrase = null;
    for (let n = Math.min(MAX_PHRASE, toks.length - i); n >= 2 && !phrase; n--) {
      const key = toks.slice(i, i + n).map(x => x.key).join(" ");
      if (joined(i, n) && groupOf(key)) phrase = { key, n };
    }
    if (phrase) {
      const last = toks[i + phrase.n - 1];
      terms.push({ key: phrase.key, text: s.slice(t.start, last.end), alts: new Set(groupOf(phrase.key)), pattern: null });
      i += phrase.n - 1;
      continue;
    }
    // "p.m." or "pm" on its own: any time in the evening
    let ap = /^[ap]m$/.test(t.key) ? t.key[0] : null;
    if (!ap && /^[ap]$/.test(t.key) && next?.key === "m" && next.start - t.end <= 2) { ap = t.key; i++; }
    if (ap) {
      terms.push({ key: `${ap}m`, text: `${ap}.m.`, alts: new Set(), pattern: new RegExp(`^\\d{1,2}(?::\\d\\d)?${ap}m$`) });
      continue;
    }
    const alts = new Set([t.key, ...(groupOf(t.key) || [])]);
    // a bare number also finds that hour: "10" -> "10pm", "10:30pm"
    const pattern = /^\d{1,2}$/.test(t.key) ? new RegExp(`^${t.key}(?::\\d\\d)?[ap]m$`) : null;
    terms.push({ key: t.key, text: s.slice(t.start, t.end), alts, pattern });
  }
  const isMeta = t => t.record || t.recordPart || t.address || t.street;
  const words = terms.filter(t => isMeta(t) || !/^[a-z]$/.test(t.key));
  return words.length ? words : terms; // single letters are noise, unless they are all there is
}

/** Cache the match keys of a condition (title + text): the set of single keys, and all keys in order as one
 * string (" k1 k2 k3 ") for phrases; and its motion's address and case number as the matcher compares them. */
export function prepare(c) {
  if (!c._keys) {
    const keys = tokenize(`${c.title} ${c.text}`).map(t => t.key);
    c._keys = new Set(keys);
    c._seq = ` ${keys.join(" ")} `;
    c._addrs = addressVariants(c.address).map(k => ` ${k.join(" ")} `);
    c._record = compactRecord(c.record);
    c._recParts = new Set(recordParts(c.record));
    c._street = streetOf(c.address);
  }
  return c;
}

function metaMatches(c, term) {
  if (term.record) return c._record.startsWith(term.record);
  if (term.recordPart) return c._recParts.has(term.recordPart);
  if (term.address) return c._addrs.some(a => a.startsWith(` ${term.address} `));
  if (term.street) {
    const st = c._street;
    return Boolean(st) && st.name === term.street && (!term.streetType || !st.type || st.type === term.streetType);
  }
  return false;
}

/** True when a case-number term of `terms` names this condition's motion. */
export function recordMatches(c, terms) {
  prepare(c);
  return terms.some(term => (term.record || term.recordPart) && metaMatches(c, term));
}

/** True when an address term of `terms` is this condition's motion's address, or a street term is its street. */
export function addressMatches(c, terms) {
  prepare(c);
  return terms.some(term => (term.address || term.street) && metaMatches(c, term));
}

function hasAlt(c, alt) {
  return alt.includes(" ") ? c._seq.includes(` ${alt} `) : c._keys.has(alt);
}

function termMatches(c, term) {
  if (term.record || term.recordPart || term.address) return metaMatches(c, term);
  if (term.street) return metaMatches(c, term) || term.textWords.every(forms => forms.some(k => c._keys.has(k)));
  return [...term.alts].some(alt => hasAlt(c, alt))
    || (term.pattern !== null && [...c._keys].some(k => term.pattern.test(k)));
}

export function matchesQuery(c, terms) {
  if (!terms.length) return true;
  prepare(c);
  return terms.every(term => termMatches(c, term));
}

/** The words of query q that no condition in `all` uses (whatever the filters): shown when a search finds nothing,
 * so "security guard" says that no condition mentions a guard. */
export function missingWords(all, q) {
  return parseQuery(q, all).filter(term => !all.some(c => matchesQuery(c, [term]))).map(term => term.text);
}

/** The sentence shown when a search finds nothing and some of its terms are on no motion ("" when every term is
 * found somewhere). Words and case numbers are named apart. It suggests the other words alone only when there are
 * other search terms: a two-word synonym phrase such as "security personnel" is one term, so a search of just that
 * phrase gets no such advice. A missing word of a group with a note (GROUP_NOTES) adds the note. */
export function noMatchNote(all, q) {
  const terms = parseQuery(q, all);
  const missing = terms.filter(term => !all.some(c => matchesQuery(c, [term])));
  if (!missing.length) return "";
  const quote = list => list.map(t => `“${t.text}”`).join(" or ");
  const records = missing.filter(t => t.record || t.caseText), words = missing.filter(t => !t.record && !t.caseText);
  const parts = [];
  if (words.length) parts.push(`no condition on these motions uses ${quote(words)}`);
  if (records.length) {
    parts.push(`no motion on this page has the case number ${quote(records)}${records.some(t => t.caseText) ? " and no condition mentions it" : ""}`);
  }
  let sentence = parts.join(", and ");
  sentence = sentence[0].toUpperCase() + sentence.slice(1);
  const others = terms.length > missing.length;
  const notes = [...new Set(words.map(term => {
    const i = GROUP_KEYS.findIndex(keys => [...term.alts].some(a => keys.includes(a)));
    return i >= 0 ? GROUP_NOTES[SYNONYM_GROUPS[i][0]] : null;
  }).filter(Boolean))];
  return `${sentence}${others ? "; try the other words alone" : ""}.${notes.map(n => " " + n).join("")}`;
}

export function matchesFilters(c, f) {
  if (f.business && c.business !== f.business) return false;
  if (f.category && !c.categories.includes(f.category)) return false;
  if (f.zoning && c.zoning !== f.zoning) return false;
  if (f.year && c.year !== f.year) return false;
  const kind = f.kind || "";
  if (kind === "" && c.kind === "boilerplate") return false;
  if (kind !== "" && kind !== "all" && c.kind !== kind) return false;
  return true;
}

/** [list, number, letter] of a condition number: "12A" is [1, 12, "A"]; "2.3" (condition 3 of the second list
 * of an older motion that restarts its numbering under each heading) is [2, 3, ""]. */
export function numberOrder(n) {
  const m = /^(?:(\d+)\.)?(\d+)([A-Za-z]?)/.exec(String(n));
  return m ? [Number(m[1] || 1), Number(m[2]), m[3]] : [0, 0, ""];
}

/** Case-specific first, then standard, then boilerplate; newest decision first within each; then by record and
 * condition number. */
export function compare(a, b) {
  return (KIND_ORDER[a.kind] - KIND_ORDER[b.kind])
    || String(b.decided || "").localeCompare(String(a.decided || ""))
    || a.record.localeCompare(b.record)
    || numberOrder(a.number)[0] - numberOrder(b.number)[0]
    || numberOrder(a.number)[1] - numberOrder(b.number)[1]
    || numberOrder(a.number)[2].localeCompare(numberOrder(b.number)[2]);
}

/** The conditions to show for filters f ({business, category, zoning, year, kind, q}), in display order. */
export function search(all, f) {
  const terms = parseQuery(f.q || "", all);
  return all.filter(c => matchesFilters(c, f) && matchesQuery(c, terms)).sort(compare);
}

/** HTML of text with the matched words (and synonym phrases) marked. `esc` escapes plain text for HTML. */
export function highlight(text, q, esc) {
  const terms = typeof q === "string" ? parseQuery(q) : q;
  const s = String(text ?? "");
  if (!terms.length) return esc(s);
  const toks = tokenize(s);
  const alts = terms.flatMap(term => [...term.alts]);
  const phrases = alts.filter(a => a.includes(" ")).map(a => a.split(" "));
  let out = "", at = 0;
  for (let i = 0; i < toks.length; i++) {
    // the longest phrase starting here, else the word itself
    let n = 0;
    for (const p of phrases) {
      if (p.length > n && p.every((k, j) => toks[i + j]?.key === k)) n = p.length;
    }
    if (!n && terms.some(term => term.alts.has(toks[i].key) || (term.pattern !== null && term.pattern.test(toks[i].key)))) n = 1;
    if (!n) continue;
    const start = toks[i].start, end = toks[i + n - 1].end;
    out += esc(s.slice(at, start)) + "<mark>" + esc(s.slice(start, end)) + "</mark>";
    at = end;
    i += n - 1;
  }
  return out + esc(s.slice(at));
}

/** The synonym list as the page shows it: one line per group, "guard, security personnel, security staff". */
export function synonymLines() {
  return SYNONYM_GROUPS.map(group => group.join(", "));
}

// ---- the page's state in the URL hash ---------------------------------------------------------------------------

/** The page's search box and filters, in the order they appear: the keys of the state kept in the URL hash. */
export const STATE_KEYS = ["q", "business", "category", "zoning", "year", "kind"];

/** The state a URL hash describes ("#q=security+guard&kind=all"): every key in STATE_KEYS, "" when the hash does
 * not set it. Unknown keys are ignored. The page applies this on load and whenever the hash changes, so a shared
 * link always shows its own results. */
export function stateFromHash(hash) {
  const p = new URLSearchParams(String(hash ?? "").replace(/^#/, ""));
  return Object.fromEntries(STATE_KEYS.map(k => [k, p.get(k) ?? ""]));
}

/** The URL hash for a state: only the keys that are set, in STATE_KEYS order. stateFromHash(hashFromState(s))
 * gives s back. */
export function hashFromState(state) {
  const p = new URLSearchParams();
  for (const k of STATE_KEYS) if (state[k]) p.set(k, state[k]);
  return "#" + p.toString();
}

/** The examples in the search box's placeholder: "e.g. odor, outdoor seating, 10 p.m." -> ["odor", ...]. */
export function placeholderExamples(placeholder) {
  return String(placeholder).replace(/^\s*e\.g\.\s*/i, "").split(/,\s*/).map(s => s.trim()).filter(Boolean);
}

// ---- the "Wrong or missing? Tell me" link on every card ---------------------------------------------------------
//
// Each card ends with a link that opens an email to the site's contact address with the case number and the
// condition number filled in (and the title, the address, a link to the card and the motion page), so a reader can
// report a wrong or missing condition without retyping them. The address is not in this file: the page passes it
// in (index.html's FEEDBACK_TO, which the public build fills with its CONTACT address; the local page leaves it
// empty and shows no link). Every fixed piece of wording is in FEEDBACK. The subject and body are encoded with
// encodeURIComponent, so "&", "#", "?", "+" and line breaks in a title or an address stay in the email and cannot
// end the subject or start a fragment. Lines are joined with CRLF, as a mailto link writes a line break (RFC 6068).

/** The fixed wording of the feedback link and of the email it opens ({record}, {number}: the condition's). */
export const FEEDBACK = {
  text: "Wrong or missing? Tell me",
  label: "Wrong or missing? Tell me about condition {number} of {record}",
  subject: "Wrong or missing: {record}, condition {number}",
  intro: "About this condition:",
  record: "Case number: ",
  number: "Condition number: ",
  title: "Condition title: ",
  address: "Address: ",
  link: "Link to its card: ",
  pdf: "Motion page: ",
  ask: "What is wrong or missing:",
};

// (replacement functions, so a "$" in a case number or title is kept as it is)
const fillIn = (s, c) => s.replace("{record}", () => String(c.record ?? "")).replace("{number}", () => String(c.number ?? ""));
// one plain address: no spaces, and none of the characters that would start a header or a fragment in a mailto link
const MAILBOX = /^[^\s@?&#%<>"]+@[^\s@?&#%<>"]+\.[^\s@?&#%<>"]+$/;

// The hash key that names the card a link points at (its condition number). It is not one of the page's fields
// (STATE_KEYS): the page reads it when it applies a hash, shows enough cards to include that one, marks it and
// scrolls to it, and the hash it writes back leaves it out.
export const CARD_KEY = "card";

/** The page that shows a condition's card: the search for its case number with every kind of condition shown,
 * and the card itself named under CARD_KEY (`base`: the page's address without the hash, as location.origin +
 * location.pathname gives it). */
export function cardLink(c, base) {
  const card = new URLSearchParams({ [CARD_KEY]: String(c.number ?? "") }).toString();
  return base + hashFromState({ q: String(c.record ?? ""), kind: "all" }) + "&" + card;
}

/** The card a URL hash points at: { record, number } (the record is the hash's search, as cardLink writes it), or
 * null when the hash names no card. */
export function cardTarget(hash) {
  const p = new URLSearchParams(String(hash ?? "").replace(/^#/, ""));
  const number = p.get(CARD_KEY);
  return number ? { record: (p.get("q") ?? "").trim(), number } : null;
}

/** Where the card `target` (cardTarget) is in the results `hits`: its index, or -1 when it is not among them. */
export function cardIndex(hits, target) {
  if (!target) return -1;
  return hits.findIndex(c => c.record === target.record && String(c.number) === target.number);
}

/** How many cards to show so that the card at `index` is shown: `shown` (the page's count so far), raised to the
 * next multiple of `page` that includes it. */
export function shownFor(index, shown, page) {
  return index < shown ? shown : Math.ceil((index + 1) / page) * page;
}

/** The subject and body of the feedback email for condition `c`. `base` (optional): the page's address without
 * the hash, for the link to the card and to resolve a relative motion link; without it a relative motion link is
 * left out. */
export function feedbackMessage(c, base = "") {
  const lines = [FEEDBACK.intro, FEEDBACK.record + (c.record ?? ""), FEEDBACK.number + (c.number ?? "")];
  if (c.title) lines.push(FEEDBACK.title + c.title);
  if (c.address) lines.push(FEEDBACK.address + c.address);
  if (base) lines.push(FEEDBACK.link + cardLink(c, base));
  if (c.pdf) {
    const at = c.pdf + (c.page ? "#page=" + c.page : "");
    let pdf = "";
    try { pdf = new URL(at, base || undefined).href; } catch { pdf = ""; }
    if (pdf) lines.push(FEEDBACK.pdf + pdf);
  }
  lines.push("", FEEDBACK.ask, "", "");
  return { subject: fillIn(FEEDBACK.subject, c), body: lines.join("\r\n") };
}

/** The mailto: link of the feedback email for condition `c` to the address `to`; null when `to` is not one plain
 * email address (the local page passes none). */
export function feedbackHref(c, { to, base = "" } = {}) {
  if (!to || !MAILBOX.test(to)) return null;
  const { subject, body } = feedbackMessage(c, base);
  return `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

/** The card's feedback link as HTML (`esc` escapes text for HTML), or "" when there is no address to send to: a
 * real link whose visible text is FEEDBACK.text. Its accessible name starts with that text and adds which
 * condition it is about, since every card has one. */
export function feedbackLink(c, opts, esc) {
  const href = feedbackHref(c, opts);
  if (!href) return "";
  return `<a class="feedback" href="${esc(href)}" aria-label="${esc(fillIn(FEEDBACK.label, c))}">${esc(FEEDBACK.text)}</a>`;
}
