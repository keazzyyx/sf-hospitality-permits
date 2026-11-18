// The part of src/data/story.json that the front page's story shows, and nothing else.
//
// Why: story.json is the fact sheet for the whole case, including things the story must not say (open questions,
// the notes about page 1, Planning's whole-PDF download link, how the facts were checked). Importing it whole would
// ship all of that to every visitor inside the JavaScript. vite.config.ts serves this subset as the module
// "virtual:story-facts" (src/c/content.ts imports it); the public site's build checks that none of the left-out
// text is in its output.
//
//   node tools/story-facts.mjs           print the subset
//   node tools/story-facts.mjs --dropped print the top-level fields left out

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
export const SOURCE = resolve(here, "../src/data/story.json");

/** The facts the story reads, by name. */
const FACTS = ["Where it stands", "Years as a restaurant", "Letters", "Petitions", "What opponents were worried about"];
/** The two rows of the planning record's timeline the story reads (their events). */
const TIMELINE = [/Closed - Approved/, /Appeal Denied/];

export function subset(story) {
  const page = story.pdf.suggested_page_to_show;
  return {
    record: story.record,
    motion_number: story.motion_number,
    business_name: story.business_name,
    address: story.address,
    zoning: { code: story.zoning.code, name: story.zoning.name, also: story.zoning.also },
    landmark: story.landmark,
    block_lot: story.block_lot,
    location: { lat: story.location.lat, lon: story.location.lon },
    what_was_asked: story.what_was_asked,
    filed_date: story.filed_date,
    hearing_dates: story.hearing_dates,
    adopted_date: story.adopted_date,
    vote: { ayes: story.vote.ayes, nayes: story.vote.nayes, absent: story.vote.absent, page: story.vote.page },
    pdf: { pages: story.pdf.pages, suggested_page_to_show: page },
    timeline: story.timeline.filter(t => TIMELINE.some(re => re.test(t.event))).map(t => ({ date: t.date, event: t.event })),
    story_facts: story.story_facts.filter(f => FACTS.includes(f.fact)).map(f => ({ fact: f.fact, value: f.value })),
    findings_highlights: story.findings_highlights.map(f => ({ quote: f.quote, page: f.page })),
    // every condition's number, title and page; the text only of those printed on the page the story opens
    conditions: story.conditions.map(c => ({
      number: c.number,
      title: c.title,
      page: c.page,
      ...(c.page === page ? { text: c.text, ...(c.text_display ? { text_display: c.text_display } : {}) } : { text: "" }),
    })),
    featured_conditions: story.featured_conditions.map(f => ({ number: f.number, gloss: f.gloss })),
    totals: Object.fromEntries(Object.entries(story.totals).filter(([k]) => k !== "note")),
  };
}

export function readSubset() {
  return subset(JSON.parse(readFileSync(SOURCE, "utf8")));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const story = JSON.parse(readFileSync(SOURCE, "utf8"));
  const kept = subset(story);
  if (process.argv.includes("--dropped")) console.log(Object.keys(story).filter(k => !(k in kept)).join("\n"));
  else console.log(JSON.stringify(kept, null, 2));
}
