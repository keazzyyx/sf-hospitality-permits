// Everything the story says, read from src/data/story.json (the only source of facts about the case), through
// "virtual:story-facts" (tools/story-facts.mjs): only the fields the story shows are in the page's script.
// The chapters, their text and the featured conditions came from the scroll-story prototype; the motion sheet's own
// facts are added at the end. Nothing here is written from memory: each sentence is a fact of the fact sheet,
// reworded plainly.
import facts from "virtual:story-facts";
import { atPage, pdfUrl, PDF_BASE_URL } from "../core/search/pdf";
import { SITE } from "../core/site";
import type { ChapterSpec } from "../core/story";

interface StoryCondition {
  number: string;
  title: string;
  text: string;
  text_display?: string;
  page: number;
}

interface StoryJson {
  address: string;
  zoning: { code: string; name: string; also: string[] };
  block_lot: string;
  hearing_dates: string[];
  findings_highlights: { quote: string; page: number }[];
  record: string;
  motion_number: string | number;
  business_name: string;
  landmark: string;
  location: { lat: number; lon: number };
  what_was_asked: string;
  filed_date: string;
  adopted_date: string;
  vote: { ayes: string[]; nayes: string[]; absent: string[]; page: number };
  pdf: { pages: number; suggested_page_to_show: number };
  timeline: { date: string | number; event: string }[];
  story_facts: { fact: string; value: string; source: string }[];
  conditions: StoryCondition[];
  featured_conditions: { number: string | number; gloss: string }[];
  totals: { conditions_in_this_motion: number; conditions_in_all: number; others: number; motions: number; conditions_in_other_motions: number; other_motions: number };
}

const story = facts as StoryJson;

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
/** "2017-07-06" as "6 July 2017". */
export function day(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[(m ?? 1) - 1]} ${y}`;
}
export const num = (n: number): string => n.toLocaleString("en-US");

const fact = (name: string): string => story.story_facts.find(f => f.fact === name)?.value ?? "";
const condition = (n: string | number): StoryCondition => {
  const c = story.conditions.find(x => String(x.number) === String(n));
  if (!c) throw new Error(`story.json has no condition ${n}`);
  return c;
};
/** The text to show: the corrected display text where the fact sheet has one. */
const shown = (c: StoryCondition): string => c.text_display ?? c.text;
/** A condition's text without its opening title ("Hours of Operation: …"). */
const body = (c: StoryCondition): string => {
  const t = shown(c);
  return t.startsWith(`${c.title}:`) ? t.slice(c.title.length + 1).trim() : t;
};

/** The public copy of the motion at a page (never page 1: it prints a private name and address). */
export function pageLink(page: number): string {
  if (page < 2) throw new Error("the story never links page 1 of the motion");
  // (the public site's own store, as its build set it; the local pages link the public store)
  return atPage(pdfUrl(SITE?.pdfBase || PDF_BASE_URL, story.record), page);
}

export const CASE = {
  record: story.record,
  motion: String(story.motion_number),
  business: story.business_name,
  lat: story.location.lat,
  lon: story.location.lon,
  pages: story.pdf.pages,
};

// the appeal: only as the planning record states it
const appealClosed = story.timeline.find(t => /Appeal Denied/.test(t.event));
// the day the planning record closed: the search's "decided" date for this case
const recordClosed = story.timeline.find(t => /Closed - Approved/.test(t.event));

/** The pencil note beside each featured condition's prop: the brief's own short glosses. */
const PENCIL: Record<string, string> = {
  "20": "closed by 9 pm",
  "21": "no amplified live entertainment",
  "22": "8 am to 5 pm",
  "16": "no pick-up before 6:30 am",
  "11": "parking plan",
  "19": "community liaison",
  "18": "odour control",
  "15": "heard again after six months",
};

/** The featured conditions, in the order the drawing pins them. */
const FEATURED_ORDER = ["20", "21", "22", "16", "11", "19", "18", "15"];

export interface Featured {
  number: string;
  title: string;
  gloss: string;
  pencil: string;
  page: number;
  href: string;
}

export const FEATURED: Featured[] = FEATURED_ORDER.map(n => {
  const c = condition(n);
  const f = story.featured_conditions.find(x => String(x.number) === n);
  if (!f) throw new Error(`story.json does not feature condition ${n}`);
  return { number: n, title: c.title, gloss: f.gloss, pencil: PENCIL[n] ?? "", page: c.page, href: pageLink(c.page) };
});

/** The page the story opens: its number and the conditions printed on it, as the search holds them. */
export const PAGE = {
  number: story.pdf.suggested_page_to_show,
  href: pageLink(story.pdf.suggested_page_to_show),
  conditions: story.conditions
    .filter(c => c.page === story.pdf.suggested_page_to_show)
    .map(c => ({ number: String(c.number), title: c.title, body: body(c) })),
};

export const VOTE = {
  ayes: story.vote.ayes,
  nays: story.vote.nayes,
  absent: story.vote.absent,
  page: story.vote.page,
};

export const TOTALS = story.totals;

const letters = /^(\d+) in support, (\d+) in opposition$/.exec(fact("Letters"));
export const LETTERS = { support: Number(letters?.[1] ?? 0), opposition: Number(letters?.[2] ?? 0) };

export interface ChapterText {
  id: string;
  title: string;
  /** The heading of the text panel. */
  heading: string;
  /** Paragraphs of the panel. */
  body: string[];
  /** A sentence quoted from the motion, set apart. */
  quote?: string;
  /** Small print under the panel: where the facts are printed. */
  source?: string;
  /** Small print: a fact that needs saying but is not part of the beat. */
  aside?: string[];
  /** Small print that a phone has no room for (it stays in the page for a screen reader). */
  more?: string[];
}

const where = fact("Where it stands");
const years = fact("Years as a restaurant"); // "1923 to 2007"
const landmarkNo = /No\. (\d+)/.exec(story.landmark)?.[1] ?? "";
const petitions = fact("Petitions");
const worries = fact("What opponents were worried about");

/** A count up to 99 in words ("twenty-two"). */
function inWordsTo99(n: number): string {
  const small = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"];
  const tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];
  if (n < 20) return small[n] ?? String(n);
  if (n > 99) return String(n);
  return n % 10 ? `${tens[Math.floor(n / 10)]}-${small[n % 10]}` : (tens[Math.floor(n / 10)] ?? String(n));
}

export const TEXT: ChapterText[] = [
  {
    id: "city",
    title: "The city",
    // one address: the motion's own (story.json "address"); twenty-two: its conditions (totals)
    heading: `One address, ${inWordsTo99(story.totals.conditions_in_this_motion)} conditions.`,
    body: [`${story.business_name}, ${story.address.split(" / ")[0]}. Planning Commission Motion No. ${story.motion_number} approved its restaurant, with ${story.totals.conditions_in_this_motion} conditions attached.`],
  },
  {
    id: "address",
    title: "The address",
    heading: "302 Greenwich Street",
    body: [
      `${story.business_name} stands ${where.charAt(0).toLowerCase()}${where.slice(1)}`,
      `It was a restaurant from ${years}, then stood vacant. The building is City Landmark No. ${landmarkNo}.`,
    ],
    source: "Motion No. 19958, pages 1 and 2",
  },
  {
    id: "application",
    title: "The application",
    heading: "Asking to be a restaurant again",
    body: [
      `The application was filed on ${day(story.filed_date)}. The motion puts the request in one sentence:`,
      `Neighbours sent ${LETTERS.support} letters in support and ${LETTERS.opposition} in opposition. Those against were worried about ${worries.charAt(0).toLowerCase()}${worries.slice(1)}`,
    ],
    more: [`There were also three petitions: ${petitions.charAt(0).toLowerCase()}${petitions.slice(1)}.`],
    quote: story.what_was_asked,
    source: "Motion pages 1 and 3",
  },
  {
    id: "hearing",
    title: "The hearing",
    heading: day(story.adopted_date),
    body: ["The Planning Commission heard the case and voted the same day. The motion prints the vote like this:"],
    source: `Motion page ${story.vote.page}`,
  },
  {
    id: "motion",
    title: "The motion",
    heading: `Motion No. ${story.motion_number}`,
    body: [`Approved, with ${story.totals.conditions_in_this_motion} conditions.`],
    aside: [
      ...(appealClosed ? [`An appeal was filed and denied (planning record, ${day(String(appealClosed.date))}).`] : []),
      ...(recordClosed ? [`The search lists this case under ${day(String(recordClosed.date))}: the day the planning record closed, not the day of the vote.`] : []),
    ],
    source: `Motion page ${story.vote.page}`,
  },
  {
    id: "conditions",
    title: "The conditions",
    heading: "Each one governs something you can point at",
    body: [],
  },
  {
    id: "page",
    title: "The exact page",
    heading: "Every condition links to the page it is printed on.",
    body: [`This is page ${PAGE.number} of the motion: conditions ${PAGE.conditions[0]?.number} to ${PAGE.conditions[PAGE.conditions.length - 1]?.number}, as the search holds them. The scan is one click away.`],
  },
  {
    id: "more",
    title: `${num(story.totals.others)} more`,
    heading: `There are ${num(story.totals.others)} more.`,
    // "more" than the one condition the last chapter ends on (story.json totals: others = all - 1)
    body: [`More than the one you just read: ${num(story.totals.conditions_in_all)} conditions in all, from ${story.totals.motions} motions.`],
  },
  {
    id: "search",
    title: "The search",
    heading: "The search",
    body: [],
  },
];

/** How long each chapter travels and holds, in screens. `wide` is false on a phone, where chapters are shorter;
 *  `lastTravel` is how long the search takes to rise over the map (it depends on the layout). */
export function chapterSpecs(wide: boolean, lastTravel: number): ChapterSpec[] {
  const k = wide ? 1 : 0.86;
  const spec = (i: number, travel: number, hold: number, steps?: number): ChapterSpec => ({
    id: TEXT[i]!.id,
    title: TEXT[i]!.title,
    travel: travel * k,
    hold: hold * k,
    steps,
  });
  return [
    // (the travels are kept short: nothing is read while the camera moves)
    spec(0, 0, 1.0),
    spec(1, 0.6, 1.2),
    spec(2, 0.4, 1.2),
    spec(3, 0.8, 1.3),
    spec(4, 0.45, 1.3),
    spec(5, 0.5, 2.5, FEATURED.length),
    spec(6, 0.45, 1.4, PAGE.conditions.length),
    spec(7, 0.7, 1.2),
    { id: TEXT[8]!.id, title: TEXT[8]!.title, travel: lastTravel, hold: 0 },
  ];
}

// ---- the motion sheet at the gate: its first page, in spirit (no sponsor, no staff contact) ----------------------

/** "JULY 6, 2017": how the motion prints its hearing date. */
export function dayAsPrinted(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${(MONTHS[(m ?? 1) - 1] ?? "").toUpperCase()} ${d}, ${y}`;
}

export const SHEET = {
  record: story.record,
  motion: String(story.motion_number),
  /** The street addresses without the city and ZIP code, as the motion's first page prints them. */
  streets: story.address.split(",")[0]?.trim() ?? story.address,
  zoning: story.zoning,
  landmark: story.landmark,
  blockLot: story.block_lot,
  asked: story.what_was_asked,
  hearing: story.hearing_dates[0] ?? story.adopted_date,
  findings: story.findings_highlights,
  count: story.totals.conditions_in_this_motion,
};

/** Whole months from the filing of the application to the adopted motion. */
export const MONTHS_TO_DECIDE = (() => {
  const [ay, am, ad] = story.filed_date.split("-").map(Number);
  const [by, bm, bd] = story.adopted_date.split("-").map(Number);
  return ((by ?? 0) - (ay ?? 0)) * 12 + ((bm ?? 0) - (am ?? 0)) - ((bd ?? 0) < (ad ?? 0) ? 1 : 0);
})();
const WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
/** A small count as a word ("four"). */
export const inWords = (n: number): string => WORDS[n] ?? String(n);

/** All of the motion's conditions, in order: number, title, page, and whether the story features it. */
export const CONDITIONS = story.conditions.map(c => ({
  number: String(c.number),
  title: c.title,
  page: c.page,
  featured: FEATURED_ORDER.includes(String(c.number)),
}));
