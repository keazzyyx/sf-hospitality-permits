// The cases the parity tests load on both pages (e2e/parity.spec.ts against the local page, e2e-site/site.spec.ts
// against the live site): each is a URL hash, with what the current site itself must find for it.

import { hash } from "./parity";

export interface Case {
  name: string;
  hash: string;
  /** The current site must show at least this many conditions, or exactly this many. */
  min?: number;
  exact?: number;
}

export const CASES: Case[] = [
  // queries
  { name: "security guard", hash: hash({ q: "security guard" }), min: 1 },
  { name: "case number 2015-009955CUA", hash: hash({ q: "2015-009955CUA" }), exact: 43 },
  { name: "address range 1408-1414 California St", hash: hash({ q: "1408-1414 California St" }), min: 1 },
  { name: "address 1408 California St", hash: hash({ q: "1408 California St" }), min: 1 },
  { name: "street Valencia St", hash: hash({ q: "Valencia St" }), min: 50 },
  { name: "street Mission St", hash: hash({ q: "Mission St" }), min: 50 },
  { name: "old case number 2010.1070C_3", hash: hash({ q: "2010.1070C_3" }), min: 1 },
  { name: "old case number 2011.1216C", hash: hash({ q: "2011.1216C" }), min: 1 },
  { name: "noise", hash: hash({ q: "noise" }), min: 100 },
  { name: "time 10 pm", hash: hash({ q: "10 pm" }), min: 10 },
  { name: "time 10 p.m.", hash: hash({ q: "10 p.m." }), min: 10 },
  { name: "outdoor seating", hash: hash({ q: "outdoor seating" }), min: 1 },
  { name: "live music", hash: hash({ q: "live music" }), min: 1 },
  { name: "liaison", hash: hash({ q: "liaison" }), min: 50 },
  { name: "garbage", hash: hash({ q: "garbage" }), min: 50 },
  { name: "odor", hash: hash({ q: "odor" }), min: 50 },
  { name: "street 24th St", hash: hash({ q: "24th St" }), min: 1 },
  { name: "address plus a word: 2351 Mission noise", hash: hash({ q: "2351 Mission noise" }) },
  { name: "synonyms: midnight", hash: hash({ q: "midnight" }), min: 1 },
  { name: "street with a type: Van Ness Ave", hash: hash({ q: "Van Ness Ave" }) },
  { name: "serial part of a case number: 009955", hash: hash({ q: "009955" }), min: 1 },
  // no query
  { name: "an empty query", hash: "", exact: 3130 },
  { name: "an empty query, everything shown (kind=all)", hash: hash({ kind: "all" }), exact: 5049 },
  // filters, alone and together, through the hash
  { name: "filter: business Bar", hash: hash({ business: "Bar" }), min: 50 },
  { name: "filter: category noise, year 2019", hash: hash({ category: "noise", year: "2019" }), min: 1 },
  { name: "filter: zoning NCT-MISSION, kind all", hash: hash({ zoning: "NCT-MISSION", kind: "all" }), min: 1 },
  { name: "filter: kind boilerplate", hash: hash({ kind: "boilerplate" }), exact: 1919 },
  { name: "filter: kind standard, business Restaurant or cafe", hash: hash({ kind: "standard", business: "Restaurant or cafe" }), min: 100 },
  { name: "filter: kind specific, year 2024", hash: hash({ kind: "specific", year: "2024" }), min: 1 },
  { name: "query + filters: noise, Nighttime entertainment, specific", hash: hash({ q: "noise", business: "Nighttime entertainment", kind: "specific" }), min: 1 },
  { name: "query + filters: patrons, category noise, kind all", hash: hash({ q: "patrons", category: "noise", kind: "all" }), min: 1 },
  { name: "query + every filter", hash: hash({ q: "hours", business: "Restaurant or cafe", category: "hours", zoning: "NC-3", year: "2019", kind: "all" }) },
  { name: "a filter value that is not in the menu", hash: hash({ business: "Nope", q: "odor" }), min: 50 },
  { name: "a hash with a key the page does not know", hash: "#foo=bar&q=odor", min: 50 },
  // nothing found
  { name: "no match: a word no condition uses", hash: hash({ q: "xylophone" }), exact: 0 },
  { name: "no match: one word found, one not", hash: hash({ q: "noise xylophone" }), exact: 0 },
  { name: "no match: a case number not on the page", hash: hash({ q: "2099-123456CUA" }), exact: 0 },
  { name: "no match: filters that exclude everything", hash: hash({ q: "karaoke", year: "2010", business: "Other food and drink" }), exact: 0 },
  // card links
  { name: "a card permalink", hash: "#q=2015-009955CUA&kind=all&card=7A", exact: 51 },
  { name: "a card permalink beyond the first page", hash: "#q=2015-009955CUA&kind=all&card=30", exact: 51 },
  { name: "a card permalink to a card that is not there", hash: "#q=2015-009955CUA&kind=all&card=99", exact: 51 },
];
