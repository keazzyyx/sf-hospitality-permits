// The search, as a function any page can mount. The search rules, the sort, the hash state and the wording of
// the notes all come from the current site's own modules (search.js, coverage.js), imported unchanged; the page
// behaviour below is a port of the inline script of tools/conditions-search/index.html, so the same hash shows
// the same conditions in the same order with the same counts (e2e/parity.spec.ts holds it to that).

import {
  KINDS,
  STATE_KEYS,
  addressMatches,
  cardIndex,
  cardLink,
  cardTarget,
  feedbackLink,
  hashFromState,
  highlight,
  noMatchNote,
  parseQuery,
  placeholderExamples,
  prepare,
  recordMatches,
  search,
  searchIndex,
  shownFor,
  stateFromHash,
  synonymLines,
} from "@conditions/search";
import type { CardTarget, Condition, ConditionsData, FilterState, StateKey, Term } from "@conditions/search";
import { coverageSentences, day } from "@conditions/coverage";
import { onReducedMotionChange, reducedMotion } from "../env";
import { dataUrl as defaultDataUrl } from "../paths";
import { hasProgress, loadConditions, type DataHandle, type LoadProgress } from "./load";
import { PDF_BASE_URL, atPage, pdfUrl, publicPdf } from "./pdf";
import SECTION_PAGES from "./section-pages.json";
import "./search.css";

export type { Condition, ConditionsData, FilterState, StateKey, Term } from "@conditions/search";
export { loadConditions } from "./load";
export { PDF_BASE_URL, pdfUrl } from "./pdf";

/** The search box and filters, plus what the last search found. */
export interface SearchState extends FilterState {
  /** Conditions that match. */
  total: number;
  /** Motions those conditions come from. */
  motions: number;
  /** Approval-boilerplate conditions that match but are hidden (only when "Which conditions" is on its default). */
  hidden: number;
  /** How many of the matches are on the page now. */
  shown: number;
  /** False until the data has loaded and the first search has been drawn. */
  ready: boolean;
}

/** The detail of the "cs:results" event the search's root element dispatches after every search (it bubbles). */
export interface SearchResultsDetail {
  hits: Condition[];
  state: SearchState;
}

/** The detail of the "cs:data" event the root dispatches each time the data has loaded (also after "Try again"). */
export interface SearchDataDetail {
  data: ConditionsData;
}

export interface MountSearchOptions {
  /** Where the data is. Default: data/conditions.json under the site root. */
  dataUrl?: string;
  /** Where the motion PDFs are: <pdfBase><record>.pdf. Default: the public store. "" keeps the data's own links. */
  pdfBase?: string;
  /** The data, when the page has already started loading it (loadConditions() gives progress as well). */
  data?: Promise<ConditionsData>;
  /** Called after every search with all the matching conditions, in display order, and the state. */
  onResults?(hits: Condition[], state: SearchState): void;
  /** Put the cursor in the search field once mounted. */
  autofocus?: boolean;
  /** The address the "Wrong or missing? Tell me" link on each card emails. Empty (the default): no link. */
  feedbackTo?: string;
  /** Keep the state in the URL hash (default true). Turn off when the page uses the hash for something else. */
  hash?: boolean;
  /** Heading level of "Conditions of approval": 1 on a page of its own, 2 (the default) inside a prototype. */
  headingLevel?: 1 | 2;
  /** A page with the coverage detail, if there is one: the coverage links only show when this is set. */
  coverageHref?: string;
  /** "/" puts the cursor in the field from anywhere on the page (default true). A page that cannot offer a
   *  single-key shortcut (it could not be turned off: WCAG 2.1.4) turns it off, and the hint with it. */
  slashKey?: boolean;
}

export interface SearchHandle {
  /** Type a query for the visitor: fills the field and runs the search. */
  setQuery(q: string): void;
  getState(): SearchState;
  /** Put the cursor in the search field and bring it into view. */
  focus(): void;
  /** Remove the search and everything it listens to. */
  destroy(): void;
  /** Resolves when the data has loaded and the first search has been drawn; rejects if the first load fails (the
   *  page then says so and offers "Try again": listen for "cs:data" to hear of a later success). */
  ready: Promise<void>;
  /** The data of the first load (for a footer, a map, a count). */
  data: Promise<ConditionsData>;
}

// ---- the page's own constants, as on the current site ------------------------------------------------------------

const CATEGORY: Record<string, string> = {
  garbage: "Garbage and recycling",
  community_liaison: "Community liaison",
  noise: "Noise",
  odor: "Odor",
  lighting: "Lighting",
  entertainment: "Entertainment",
  hours: "Hours",
  signage: "Signage",
  security: "Security",
  good_neighbor: "Good neighbor",
  alcohol: "Alcohol",
  outdoor: "Outdoor area",
  other: "Other",
};
const KIND_LABEL: Record<string, string> = {
  specific: "Case-specific",
  standard: "Standard",
  boilerplate: "Approval boilerplate",
};
const PAGE = 50;
/** While typing, this many cards are written with the keystroke, the rest of the page a frame later. */
const FIRST_CARDS = 12;
const PLACEHOLDER = "e.g. odor, amplified music, 10 p.m., outdoor seating, patrons, 2351 Mission";
const LABELS: Record<StateKey, string> = {
  q: "Search the conditions, a case number or an address",
  business: "Business type",
  category: "Condition category",
  zoning: "Zoning district",
  year: "Year decided",
  kind: "Which conditions",
};
/** The field's label as a narrow page shows it (the full one stays the field's name). */
const SHORT_LABEL = "Search conditions, case no. or address";
const FILTER_KEYS = STATE_KEYS.filter(k => k !== "q");
/** Typing writes the hash once it pauses for this long (every other change writes it at once). */
const HASH_PAUSE_MS = 150;
/** The count is read out this long after the last keystroke, so half-typed words are not announced. */
const ANNOUNCE_PAUSE_MS = 500;

const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch] ?? ch);
const catLabel = (c: string): string => CATEGORY[c] ?? c.replace(/_/g, " ");
// counts come from the data file: anything that is not a number is shown as one, never as markup
const n = (x: unknown): string => Number(x).toLocaleString();
const plural = (k: number, word: string): string => `${n(k)} ${word}${k === 1 ? "" : "s"}`;
const megabytes = (bytes: number): string => (bytes / 1_000_000).toFixed(1);
/** A link from the data file is only used when it is a web address (never "javascript:" or the like). */
const webLink = (url: string | null | undefined): string | null => (url && /^https?:\/\//i.test(url.trim()) ? url : null);
/** A motion link: a web address, or a path on this site (the local copies), never another scheme. */
const safeLink = (url: string | null | undefined): string | null =>
  url && (/^https?:\/\//i.test(url.trim()) || !/^[\s\u0000-\u001f]*[a-z][a-z0-9+.-]*:/i.test(url)) ? url : null;

// drawn in code: the faces' latin subsets have no diagonal arrow
const ARROW =
  '<svg class="cs-arrow" viewBox="0 0 10 10" width="10" height="10" aria-hidden="true" focusable="false">' +
  '<path d="M2 8 8.25 1.75M3.25 1.5h5.25v5.25" fill="none" stroke="currentColor" stroke-width="1.25"/></svg>';

const CHEVRON =
  '<svg class="cs-chevron" viewBox="0 0 12 8" width="12" height="8" aria-hidden="true" focusable="false">' +
  '<path d="M1 1.5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="1.25"/></svg>';

/** The sentence under the title. The counts are known when the app is built, so it is the same before and after
 *  the data arrives and nothing below it moves. */
const subLine = (conditions: unknown, motions: unknown): string =>
  `${n(conditions)} conditions of approval from ${n(motions)} San Francisco Planning Commission motions on food, drink and entertainment premises.`;

const LOADING = `
    <div class="cs-loading" data-cs-loading role="status">
      <p class="cs-loading__line">Reading ${n(__DATA_FACTS__.motions)} motions…</p>
      <div class="cs-progress" data-cs-progress role="progressbar" aria-label="Reading the motions" aria-valuemin="0" aria-valuemax="100"><span></span></div>
      <p class="cs-loading__bytes data" data-cs-bytes aria-hidden="true">&nbsp;</p>
    </div>`;

/** The data is usable when it has the lists the page reads and every condition has the fields the search reads. */
/** A breath between two pieces of work: the browser draws and answers a key or a tap in it. */
function breathe(): Promise<void> {
  const scheduler = (globalThis as { scheduler?: { yield?: () => Promise<void> } }).scheduler;
  if (typeof scheduler?.yield === "function") return scheduler.yield().catch(() => {});
  return new Promise(resolve => window.setTimeout(resolve, 0));
}

function usable(d: unknown): d is ConditionsData {
  const x = d as Partial<ConditionsData> | null;
  if (!x || typeof x !== "object") return false;
  if (!Array.isArray(x.conditions) || !x.conditions.length) return false;
  if (!Array.isArray(x.motions_without_conditions) || !Array.isArray(x.removed_motions) || !Array.isArray(x.boilerplate_titles)) return false;
  return x.conditions.every(
    c => c && typeof c.record === "string" && typeof c.title === "string" && typeof c.text === "string" && Array.isArray(c.categories),
  );
}

/**
 * Wrap the first `length` characters of the text shown by `html` (the highlighter's output: text, entities and
 * <mark> tags) in a span, leaving the markup as it is. Returns `html` unchanged if that point falls inside a mark.
 */
function leadIn(html: string, length: number): string {
  let seen = 0;
  let depth = 0;
  let i = 0;
  while (i < html.length && seen < length) {
    const ch = html[i];
    if (ch === "<") {
      const end = html.indexOf(">", i);
      if (end < 0) return html;
      depth += html[i + 1] === "/" ? -1 : 1;
      i = end + 1;
    } else if (ch === "&") {
      const end = html.indexOf(";", i);
      if (end < 0) return html;
      seen += 1;
      i = end + 1;
    } else {
      seen += 1;
      i += 1;
    }
  }
  // a mark that closes right here belongs to the lead
  while (html.startsWith("</", i)) {
    depth -= 1;
    i = html.indexOf(">", i) + 1;
  }
  if (seen < length || depth !== 0) return html;
  return `<span class="cs-text__lead">${html.slice(0, i)}</span>${html.slice(i)}`;
}

let mounts = 0;
/** The search mounted in each element, so a second mount on the same element replaces the first. */
const mounted = new WeakMap<HTMLElement, SearchHandle>();

function template(uid: string, level: 1 | 2, slash = true): string {
  const select = (key: StateKey): string => `
        <div class="cs-select cs-select--${key}">
          <label class="label" for="${uid}-${key}">${esc(LABELS[key])}</label>
          <div class="cs-select__box"><select id="${uid}-${key}" name="${key}" data-cs-field="${key}" disabled><option value="">${key === "kind" ? esc(KINDS[0]?.[1]) : "All"}</option></select></div>
        </div>`;
  return `
<div class="cs" data-cs-state="loading">
  <header class="cs-head">
    <h${level} class="cs-title">Conditions of approval</h${level}>
    <p class="cs-sub" data-cs-sub>${esc(subLine(__DATA_FACTS__.conditions, __DATA_FACTS__.motions))}</p>
  </header>

  <form class="cs-form" role="search" aria-label="Conditions of approval" novalidate>
    <div class="cs-query">
      <label class="label cs-query__label" for="${uid}-q"><span class="cs-query__full">${esc(LABELS.q)}</span><span class="cs-query__short" aria-hidden="true">${esc(SHORT_LABEL)}</span></label>
      <div class="cs-field">
        <input class="cs-input" type="search" id="${uid}-q" name="q" data-cs-field="q" autocomplete="off"
          autocapitalize="off" autocorrect="off" spellcheck="false" enterkeyhint="search"
          aria-describedby="${uid}-hint" aria-controls="${uid}-results">
        <button class="cs-clear text-button" type="button" data-cs-clear hidden>Clear<span class="vh"> the search</span></button>
        ${slash ? `<kbd class="cs-key" aria-hidden="true" title="Press / to search">/</kbd>` : ""}
      </div>
      <div class="cs-under">
        <p class="cs-hint" id="${uid}-hint">All words, in any order. <span class="cs-hint__keys">${slash ? "Press <kbd>/</kbd> to search, <kbd>Esc</kbd> to clear." : "Press <kbd>Esc</kbd> to clear."}</span></p>
        <button class="cs-more-about cs-more-about--coverage text-button" type="button" aria-expanded="false" aria-controls="${uid}-coverage" data-cs-fold>Coverage</button>
        <button class="cs-more-about text-button" type="button" aria-expanded="false" aria-controls="${uid}-tips" data-cs-fold data-cs-tips>Search tips</button>
      </div>
      <div class="cs-tips__body cs-fold__body" id="${uid}-tips" role="region" aria-label="Search tips">
        <p>Every word must appear, in any order, in the condition, its motion's case number or its address: a case
        number (2023-005418CUA) or an address (2351 Mission) finds that motion's conditions, and adding words narrows
        them (2351 Mission noise). A street (Valencia St, 24th St) finds every motion on it, and the conditions that
        name it; with its type (St, Ave) it is that street only, so 19th St is not 19th Ave. Word endings do not matter
        (guard, guards, guarding). Times match however they are written (10 p.m., 10pm, 10:00 PM). These count as the
        same word:</p>
        <ul data-cs-synonyms></ul>
      </div>
    </div>

    <div class="cs-filters">
      <div class="cs-folds">
        <button class="cs-fold cs-fold--filters" type="button" aria-expanded="false" aria-controls="${uid}-filters" data-cs-fold data-cs-fold-filters>
          <span class="label">Filters</span><span class="cs-fold__note data" data-cs-set></span>
          ${CHEVRON}
        </button>
        <button class="cs-fold cs-fold--coverage" type="button" aria-expanded="false" aria-controls="${uid}-coverage" data-cs-fold>
          <span class="label">Coverage</span>
          ${CHEVRON}
        </button>
      </div>
      <div class="cs-filters__body cs-fold__body" id="${uid}-filters" role="group" aria-label="Filters">${FILTER_KEYS.map(select).join("")}
      </div>
    </div>
  </form>

  <aside class="cs-coverage" aria-label="Coverage">
    <div class="cs-coverage__body cs-fold__body" id="${uid}-coverage">
      <h${level + 1} class="label cs-coverage__label">Coverage</h${level + 1}>
      <div class="cs-coverage__text" data-cs-coverage><p>Not known until the data loads.</p></div>
    </div>
  </aside>

  <div class="cs-bar">
    <p class="cs-count data" data-cs-count><span class="cs-count__found" data-cs-count-text></span></p>
    <button class="text-button cs-reset" type="button" data-cs-reset hidden>Clear all</button>
  </div>
  <p class="vh" data-cs-live role="status" aria-live="polite" aria-atomic="true"></p>

  <section class="cs-results" id="${uid}-results" aria-label="Conditions found" data-cs-results>${LOADING}
  </section>

  <footer class="cs-notes" data-cs-notes aria-label="About these conditions"></footer>
</div>`;
}

/**
 * Mount the search into `root`. It behaves as the current site's page does: the same query rules, filters, sort,
 * count sentence, "show more" paging, hidden approval-boilerplate toggle, card links, hash state, highlight,
 * no-match notes, search tips and coverage notes. Mounting again on the same element replaces the earlier search.
 */
export function mountSearch(root: HTMLElement, opts: MountSearchOptions = {}): SearchHandle {
  mounted.get(root)?.destroy();

  const uid = `cs${++mounts}`;
  const useHash = opts.hash !== false;
  const feedbackTo = opts.feedbackTo ?? "";
  const pdfBase = opts.pdfBase ?? PDF_BASE_URL;
  const level = opts.headingLevel ?? 2;
  const url = opts.dataUrl ?? defaultDataUrl();
  const abort = new AbortController();
  const { signal } = abort;

  root.classList.add("cs-root");
  root.innerHTML = template(uid, level, opts.slashKey !== false);

  const find = <T extends Element>(selector: string): T => {
    const node = root.querySelector<T>(selector);
    if (!node) throw new Error(`mountSearch: missing ${selector}`);
    return node;
  };
  const wrap = find<HTMLElement>(".cs");
  const input = find<HTMLInputElement>('[data-cs-field="q"]');
  const fields = Object.fromEntries(
    STATE_KEYS.map(k => [k, find<HTMLInputElement | HTMLSelectElement>(`[data-cs-field="${k}"]`)]),
  ) as Record<StateKey, HTMLInputElement | HTMLSelectElement>;
  const clearButton = find<HTMLButtonElement>("[data-cs-clear]");
  const setCount = find<HTMLElement>("[data-cs-set]");
  const countText = find<HTMLElement>("[data-cs-count-text]");
  const countLine = find<HTMLElement>("[data-cs-count]");
  const live = find<HTMLElement>("[data-cs-live]");
  const sub = find<HTMLElement>("[data-cs-sub]");
  const coverageText = find<HTMLElement>("[data-cs-coverage]");
  // the second half of the count sentence, in the page only while approval boilerplate is hidden:
  // " · 1,919 approval-boilerplate conditions hidden [show them]"
  const hiddenLine = document.createElement("span");
  hiddenLine.className = "cs-count__hidden";
  hiddenLine.dataset.csHidden = "";
  const hiddenText = document.createElement("span");
  const showAll = document.createElement("button");
  showAll.type = "button";
  showAll.className = "text-button cs-showall";
  showAll.dataset.csShowall = "";
  showAll.textContent = "show them";
  hiddenLine.append(hiddenText, showAll);
  const reset = find<HTMLButtonElement>("[data-cs-reset]");
  const results = find<HTMLElement>("[data-cs-results]");
  const notes = find<HTMLElement>("[data-cs-notes]");
  const folds = [...root.querySelectorAll<HTMLButtonElement>("[data-cs-fold]")];

  let data: ConditionsData | null = null;
  let all: Condition[] = [];
  let shown = PAGE;
  // the card the applied hash points at: shown, marked and scrolled to by the next render, then forgotten
  let target: CardTarget | null = null;
  let hits: Condition[] = [];
  let terms: Term[] = [];
  let found = { total: 0, motions: 0, hidden: 0 };
  let ready = false;
  let destroyed = false;
  let pendingQuery: string | null = null;
  // the visitor changed the field before the data arrived: their text is kept, whatever the hash says
  let edited = false;
  // what the last typed search cost: typing renders at once while this stays small
  let typingCost = 0;
  let timer = 0;
  let hashTimer = 0;
  let liveTimer = 0;
  /** The rest of a typed page of cards, written a frame after its first few (cancel(): a newer search replaces it). */
  let rest: { frame: number; timer: number; run: () => void } | null = null;
  const cancelRest = (): void => {
    if (!rest) return;
    cancelAnimationFrame(rest.frame);
    window.clearTimeout(rest.timer);
    rest = null;
  };
  /** Write the rest now (before "show more" adds the next page under it). */
  const flushRest = (): void => {
    const pending = rest;
    cancelRest();
    pending?.run();
  };
  // the last few searches, kept so that going back to one (clearing the field, backspacing) costs nothing.
  // The arrays are shared with onResults: read them, do not change them.
  const memo = new Map<string, Condition[]>();
  const lookup = (f: Partial<FilterState>): Condition[] => {
    const key = STATE_KEYS.map(k => f[k] ?? "").join("\u0001");
    const kept = memo.get(key);
    if (kept) {
      memo.delete(key);
      memo.set(key, kept);
      return kept;
    }
    const fresh = search(all, f);
    memo.set(key, fresh);
    if (memo.size > 32) memo.delete(memo.keys().next().value as string);
    return fresh;
  };

  const read = (): FilterState => Object.fromEntries(STATE_KEYS.map(k => [k, fields[k].value])) as FilterState;
  const getState = (): SearchState => ({ ...read(), ...found, shown: Math.min(shown, found.total), ready });
  const base = (): string => location.origin + location.pathname;

  // ---- hash state: a link shares a search --------------------------------------------------------------------
  // readState applies the hash (every field the hash leaves out is cleared, and the card it names, if any, becomes
  // the target); writeState puts the current fields in it without a history entry.
  function readState(): void {
    const state = stateFromHash(location.hash);
    for (const k of STATE_KEYS) fields[k].value = state[k];
    target = cardTarget(location.hash);
  }
  /** While typing the hash is written once the typing pauses: browsers ration history.replaceState (WebKit refuses
   *  more than 100 calls in 10 seconds), and a refused write must never stop a search. */
  function writeState(state: FilterState, later = false): void {
    window.clearTimeout(hashTimer);
    const write = (): void => {
      const hash = hashFromState(state);
      if (hash === (location.hash || "#")) return;
      try {
        history.replaceState(history.state, "", hash);
      } catch {
        // refused (too many writes): the next one carries the state
      }
    };
    if (later) hashTimer = window.setTimeout(write, HASH_PAUSE_MS);
    else write();
  }

  // ---- cards ---------------------------------------------------------------------------------------------------
  /** Case number, address, business, decision date, zoning: on each card, or once above a list from one motion. */
  function facts(c: Condition): string {
    const record = recordMatches(c, terms) ? `<mark>${esc(c.record)}</mark>` : esc(c.record);
    const address = addressMatches(c, terms) ? `<mark>${esc(c.address)}</mark>` : esc(c.address);
    const decided = c.decided ? `Decided&nbsp;<time datetime="${esc(c.decided)}">${esc(day(c.decided))}</time>` : "Decided: date not on file";
    // one space between the parts (where a line may break); the dots after them are drawn by the stylesheet
    return (
      `<dl class="cs-meta data">` +
      `<div class="cs-meta__record"><dt class="vh">Case number</dt><dd data-cs-record>${record}</dd></div> ` +
      `<div class="cs-meta__address"><dt class="vh">Address</dt><dd>${address}</dd></div> ` +
      `<div class="cs-meta__second"><dt class="vh">Business type</dt><dd>${esc(c.business)}</dd></div> ` +
      `<div><dt class="vh">Decision</dt><dd>${decided}</dd></div>` +
      (c.zoning ? ` <div><dt class="vh">Zoning district</dt><dd>${esc(c.zoning)}</dd></div>` : "") +
      `</dl>`
    );
  }

  /** The condition as the feedback e-mail tells of it: its motion link at the page the card's own button opens
   *  (where the motion's conditions begin, for a condition read with no page), never at page 1, which prints the
   *  project sponsor's name and address. A condition with no page and no section page gives no motion link at all. */
  function feedbackCondition(c: Condition, section: { page: number } | undefined): Condition {
    if (c.page || !c.pdf) return c;
    return section ? { ...c, page: section.page } : { ...c, pdf: null };
  }

  function card(c: Condition, isTarget: boolean): string {
    const pdf = safeLink(c.pdf);
    // a condition read with no page opens its motion where the conditions begin, never at page 1
    const section = c.page ? undefined : (SECTION_PAGES.pages as Record<string, { page: number; label: string } | undefined>)[c.record];
    const at = pdf ? esc(atPage(pdf, c.page ?? section?.page)) : "";
    const pageText = c.page
      ? `${c.page_exact ? "" : "near "}p.&nbsp;${esc(c.page)}`
      : section
        ? `${esc(section.label)}, p.&nbsp;${esc(section.page)}`
        : "";
    const page = pdf
      ? `<a class="cs-pdf ruled-button" href="${at}" target="_blank" rel="noopener" data-cs-pdf>${
          pageText ? `<span class="cs-pdf__page">${pageText}</span><span class="cs-pdf__dot" aria-hidden="true"> · </span>` : ""
        }<span>open the motion</span>${ARROW}<span class="vh"> (PDF, opens in a new tab)</span></a>`
      : "";
    const planning = webLink(c.motion_url);
    const src = planning
      ? `<span class="cs-alt"><a href="${esc(planning)}" target="_blank" rel="noopener" data-cs-planning>Planning's copy</a> (downloads the PDF)</span>`
      : "";
    const link = useHash
      ? `<a class="cs-permalink" href="${esc(cardLink(c, base()))}" data-cs-permalink>Link to this condition</a>`
      : "";
    // every condition's text opens with its title and a colon: that run is set quieter, since the heading says it
    const lead = c.text.startsWith(`${c.title}:`) ? c.title.length + 1 : 0;
    const text = highlight(c.text, terms, esc);
    const body = c.readable
      ? `<div class="cs-text">${lead ? leadIn(text, lead) : text}</div>`
      : `<div class="cs-unreadable"><p>The text of this condition could not be read cleanly. ${
          pdf
            ? `<a href="${at}" target="_blank" rel="noopener">Open the motion page${c.page ? ` (${esc(c.page)})` : ""}</a> to read it.`
            : "Open Planning's copy of the motion to read it."
        }</p><details><summary>Show the text as extracted anyway</summary><div class="cs-text">${esc(c.raw_text || c.text)}</div></details></div>`;
    const kind = KIND_LABEL[c.kind] ?? "Not classified";
    const cats = c.categories.map(x => `<span class="cs-cat">${esc(catLabel(x))}</span>`).join("");
    return `<article class="cs-card${isTarget ? " is-target" : ""}" data-cs-card data-record="${esc(c.record)}" data-number="${esc(c.number)}"${isTarget ? ' tabindex="-1"' : ""}>
  <h${level + 1} class="cs-card__title"><span class="cs-card__num"><span data-cs-num aria-hidden="true">${esc(c.number)}</span><span class="vh">Condition ${esc(c.number)}: </span></span><span class="cs-card__name">${highlight(c.title, terms, esc)}</span></h${level + 1}>
  <p class="cs-kicker label"><span class="cs-kind cs-kind--${esc(c.kind)}">${esc(kind)}</span>${cats}</p>
  ${facts(c)}
  ${body}
  <p class="cs-links">${page}${src}${link}${feedbackLink(feedbackCondition(c, section), { to: feedbackTo, base: base() }, esc)}</p>
</article>`;
  }

  function moreControl(): string {
    const left = hits.length - shown;
    const status = `<span class="cs-more__status data">${n(Math.min(shown, hits.length))} of ${n(hits.length)} shown</span>`;
    return left > 0
      ? `<div class="cs-more" data-cs-more-row><button class="ruled-button" type="button" data-cs-more>Show ${Math.min(PAGE, left)} more</button>${status}</div>`
      : `<div class="cs-more cs-more--end" data-cs-more-row><span class="label">End of the list</span>${status}</div>`;
  }

  /** Nothing found: say what was looked for, why nothing has it (the current site's note), and offer a way on. */
  function nothing(f: FilterState, note: string): string {
    const filtered = FILTER_KEYS.some(k => f[k] !== "");
    const q = f.q.trim();
    const shownQuery = q.length > 80 ? `${q.slice(0, 80)}…` : q;
    const line = q
      ? `No condition matches “${esc(shownQuery)}”${filtered ? " with these filters" : ""}.`
      : "No condition matches these filters.";
    const examples = filtered
      ? ""
      : `<span class="cs-empty__try">or try ${examples3()
          .map(x => `<button class="text-button" type="button" data-cs-example="${esc(x)}">${esc(x)}</button>`)
          .join(", ")}</span>`;
    const way = filtered
      ? `<button class="ruled-button" type="button" data-cs-clear-filters>Clear the filters</button>`
      : `<button class="ruled-button" type="button" data-cs-clear-query>Clear the search</button>`;
    return `<div class="cs-empty" data-cs-empty><p class="cs-empty__line">${line}</p>${
      note ? `<p class="cs-empty__note" data-cs-empty-note>${esc(note)}</p>` : ""
    }<div class="cs-empty__ways">${way}${examples}</div></div>`;
  }

  // ---- the search --------------------------------------------------------------------------------------------
  function render(typed = false): void {
    if (!data || destroyed) return;
    const started = performance.now();
    window.clearTimeout(timer);
    cancelRest();
    const f = read();
    if (useHash) writeState(f, typed);
    terms = parseQuery(f.q, all);
    hits = lookup(f);
    const at = cardIndex(hits, target);
    target = null;
    const motions = new Set(hits.map(c => c.record)).size;
    const text = `${plural(hits.length, "condition")} from ${n(motions)} of ${n(data.motions_with_conditions)} motions`;
    const hidden = f.kind === "" ? lookup({ ...f, kind: "boilerplate" }).length : 0;
    countText.textContent = text;
    if (hidden) {
      // the same sentence as the current site's, in parts a narrow page can set on a line of its own
      hiddenText.innerHTML = `<span class="cs-count__word"> · </span>${n(hidden)} <span class="cs-count__word">approval-</span>boilerplate<span class="cs-count__word"> condition${hidden === 1 ? "" : "s"}</span> hidden `;
      countLine.append(hiddenLine);
    } else hiddenLine.remove();
    found = { total: hits.length, motions, hidden };
    syncControls(f);

    let said = text + (hidden ? `, ${plural(hidden, "approval-boilerplate condition")} hidden` : "");
    if (!hits.length) {
      const note = f.q ? noMatchNote(all, f.q) : "";
      results.innerHTML = nothing(f, note);
      said = `${text}. ${note || "No condition matches these filters."}`;
    } else {
      if (at >= 0) shown = shownFor(at, shown, PAGE);
      // a list from one motion says which motion once, above the list (each card still carries it for a screen
      // reader, and the card a link points at shows its own)
      const one = hits.length > 1 && motions === 1 ? (hits[0] as Condition) : null;
      // while typing, the first few cards are written at once and the rest of the page a frame later: a keystroke
      // never waits for fifty cards (a link, a click and "show more" write the whole page at once)
      const upTo = Math.min(shown, hits.length);
      const first = typed && at < 0 && upTo > FIRST_CARDS ? FIRST_CARDS : upTo;
      results.innerHTML =
        (one ? `<header class="cs-case" data-cs-case><p class="label cs-case__label">All from one motion</p>${facts(one)}</header>` : "") +
        // a list drawn for a linked card is laid out in full, so the jump to the card lands on it exactly
        `<div class="cs-list${one ? " cs-list--one-case" : ""}${at >= 0 ? " cs-list--laid-out" : ""}" data-cs-list>${hits.slice(0, first).map((c, i) => card(c, i === at)).join("")}</div>` +
        moreControl();
      if (first < upTo) {
        const list = results.querySelector<HTMLElement>("[data-cs-list]");
        const page = hits;
        const run = (): void => {
          rest = null;
          if (destroyed || hits !== page || !list?.isConnected) return;
          list.insertAdjacentHTML("beforeend", page.slice(first, upTo).map(c => card(c, false)).join(""));
        };
        const frame = requestAnimationFrame(() => {
          if (rest) rest.timer = window.setTimeout(run, 0);
        });
        rest = { frame, timer: 0, run };
      }
      if (at >= 0) {
        const el = results.querySelector<HTMLElement>(".cs-card.is-target");
        if (el) {
          el.scrollIntoView({ block: "start" });
          el.focus({ preventScroll: true });
        }
      }
    }
    say(said, typed);
    const cost = performance.now() - started;
    if (typed) typingCost = cost;
    wrap.dataset.csRenderMs = cost.toFixed(1);
    announce();
  }

  /** Read the count out (a polite live region, apart from the count on the screen): at once after a click or a
   *  link, and only once typing has stopped. */
  function say(text: string, typed: boolean): void {
    window.clearTimeout(liveTimer);
    const speak = (): void => {
      if (!destroyed && live.textContent !== text) live.textContent = text;
    };
    if (typed) liveTimer = window.setTimeout(speak, ANNOUNCE_PAUSE_MS);
    else speak();
  }

  /** Tell the page what the search found: the onResults option, and a "cs:results" event on the root. */
  function announce(): void {
    const state = getState();
    opts.onResults?.(hits, state);
    root.dispatchEvent(new CustomEvent<SearchResultsDetail>("cs:results", { detail: { hits, state }, bubbles: true }));
  }

  /** "Show N more": the next page of cards is added below the ones already there. */
  function showMore(): void {
    flushRest();
    const from = shown;
    shown += PAGE;
    const list = results.querySelector<HTMLElement>("[data-cs-list]");
    const row = results.querySelector<HTMLElement>("[data-cs-more-row]");
    if (!list || !row) {
      render();
      return;
    }
    const hadFocus = row.contains(document.activeElement);
    list.insertAdjacentHTML("beforeend", hits.slice(from, shown).map(c => card(c, false)).join(""));
    row.outerHTML = moreControl();
    if (hadFocus) {
      // the keyboard carries on from the first new card
      const first = list.children[from] as HTMLElement | undefined;
      if (first) {
        first.tabIndex = -1;
        first.focus({ preventScroll: true });
      }
    }
    announce();
  }

  function syncControls(f: FilterState): void {
    clearButton.hidden = f.q === "";
    const set = FILTER_KEYS.filter(k => f[k] !== "").length;
    setCount.textContent = set ? `${set} set` : "";
    for (const k of FILTER_KEYS) fields[k].closest(".cs-select")?.classList.toggle("is-set", f[k] !== "");
    reset.hidden = STATE_KEYS.every(k => f[k] === "");
  }

  /** Typing renders at once while a search costs little; a slow one waits for a pause, never more than 80 ms. */
  function onInput(): void {
    shown = PAGE;
    clearButton.hidden = input.value === "";
    if (!ready) {
      // typed while the data is still coming: kept for when it arrives
      edited = true;
      return;
    }
    window.clearTimeout(timer);
    if (typingCost <= 32) render(true);
    else timer = window.setTimeout(() => render(true), Math.min(80, Math.round(typingCost)));
  }

  /** Empty the field (the Clear button, Escape): at once when the search is running, else kept for when it is. */
  function clearQuery(): void {
    input.value = "";
    shown = PAGE;
    clearButton.hidden = true;
    if (ready) render();
    else edited = true;
  }

  // ---- the notes under the results (the current page's footer) ---------------------------------------------
  function drawNotes(d: ConditionsData): void {
    const none = d.motions_without_conditions;
    const removed = d.removed_motions;
    const review = { decisions: d.review?.decisions ?? [], added_back: d.review?.added_back ?? [], removed: d.review?.removed ?? [] };
    const unreadable = all.filter(c => !c.readable).length;
    const split = all.filter(c => c.split_from).length;
    const link = (label: string, hash = ""): string =>
      opts.coverageHref ? `<a href="${esc(opts.coverageHref + hash)}">${label}</a>` : "";
    const note = (head: string, body: string, extra = ""): string =>
      `<div class="cs-note"><h${level + 1} class="label cs-note__head">${head}</h${level + 1}><div class="cs-note__body"><p>${body}</p>${extra}</div></div>`;
    const table = (cls: string, summary: string, label: string, head: string[], rows: string[]): string =>
      `<details class="cs-table ${cls}"><summary>${summary}</summary>
        <div class="cs-table__scroll" tabindex="0" role="region" aria-label="${label}"><table>
          <thead><tr>${head.map(h => `<th scope="col">${h}</th>`).join("")}</tr></thead>
          <tbody>${rows.join("")}</tbody>
        </table></div>
      </details>`;
    notes.innerHTML =
      note(
        "Which conditions",
        `The list shows case-specific conditions first, then standard ones, newest decision first.
        “Approval boilerplate” is hidden unless you pick it under “Which conditions”: the conditions about the approval itself,
        worded the same on every motion. They are the conditions titled ${d.boilerplate_titles.map(t => `“${esc(t)}”`).join(", ")}.
        “Standard” means the same wording opens the same-titled condition on at least five motions, or the title is on at least
        half of the approved motions for that kind of use, or it is a lettered part of a template set (such as “Liquor Stores (B)”)
        worded the same on at least two motions; otherwise “case-specific”.`,
      ) +
      note(
        "Counts",
        `${esc(n(d.motions))} motions on food, drink and entertainment premises were found.
        ${esc(n(d.motions_with_conditions))} of them have conditions, and every count on this page is out of those.`,
        // the motions with nothing to list: a table, where the current site runs them on in the sentence
        none.length
          ? table(
              "cs-none",
              `${plural(none.length, "motion")} had none to list`,
              "Motions with no conditions to list",
              ["Case number", "Address", "Outcome"],
              none.map(
                m =>
                  `<tr><td class="data">${esc(m.record)}</td><td>${esc(m.address)}</td><td>${esc(String(m.outcome || m.why || "").replace(/_/g, " "))}</td></tr>`,
              ),
            )
          : "",
      ) +
      note(
        "Text",
        `Each condition is shown as extracted from the motion, with page furniture removed (the “For information
        about compliance” contact line, page footers, section headings). Scanned motions were re-read from the PDF text layer or
        by OCR where the first reading was garbled; a second reading is only used when it is the same text, word for word, read
        better. ${unreadable ? `${plural(unreadable, "condition")} still could not be read cleanly; ${unreadable === 1 ? "it links" : "they link"} to the motion page instead.` : ""}
        ${split ? `${plural(split, "condition")} had run on into the condition before ${split === 1 ? "it" : "them"} (a missed heading) and ${split === 1 ? "is" : "are"} shown on ${split === 1 ? "its" : "their"} own.` : ""}
        ${
          pdfBase
            ? "Page links open a copy of the adopted motion, stored with this site's files, at the page where the condition starts. The smaller link goes to Planning's own copy, which downloads the PDF instead of opening it at the page."
            : "Page links open the local copy of the motion at the page where the condition starts."
        }${opts.coverageHref ? ` ${link("What this page covers, and what it does not")}.` : ""}`,
      ) +
      (review.decisions.length
        ? note(
            "Reviewed",
            `An AI classifier picked the food and drink motions; an AI review of every
            motion then added back ${plural(review.added_back.length, "motion")} it had left out and removed
            ${plural(review.removed.length, "motion")} it had kept.${
              opts.coverageHref ? ` ${link("The reviewed list", "#reviewed-list")} gives each change and its reason.` : ""
            }`,
          )
        : "") +
      table(
        "cs-removed",
        `${plural(removed.length, "motion")} left out: not food or drink`,
        "Motions left out",
        ["Case number", "Address", "What it is", "Left out by"],
        removed.map(
          m =>
            `<tr><td class="data">${esc(m.record)}</td><td>${esc(m.address)}</td><td>${esc(m.what)}</td><td>${m.left_out_by === "review" ? "removed by the review" : "left out by the classifier"}</td></tr>`,
        ),
      );
  }

  function fill(key: StateKey, values: string[], label: (v: string) => string = v => v, allText: string | null = "All"): void {
    fields[key].innerHTML =
      (allText === null ? "" : `<option value="">${allText}</option>`) +
      values.map(v => `<option value="${esc(v)}">${esc(label(v))}</option>`).join("");
    fields[key].disabled = false;
  }
  const unique = (f: (c: Condition) => string[]): string[] =>
    [...new Set(all.flatMap(f))].filter(v => v !== "" && v != null);

  // ---- loading -----------------------------------------------------------------------------------------------
  function onProgress(p: LoadProgress): void {
    if (ready || destroyed) return;
    const progress = results.querySelector<HTMLElement>("[data-cs-progress]");
    const bytes = results.querySelector<HTMLElement>("[data-cs-bytes]");
    if (!progress || !bytes) return;
    if (p.ratio === null) {
      progress.classList.add("is-open-ended");
      progress.removeAttribute("aria-valuenow");
      if (p.loaded) bytes.textContent = `${megabytes(p.loaded)} MB`;
      return;
    }
    progress.classList.remove("is-open-ended");
    progress.style.setProperty("--cs-progress", String(p.ratio));
    progress.setAttribute("aria-valuenow", String(Math.round(p.ratio * 100)));
    if (p.total && p.loaded) bytes.textContent = `${megabytes(p.loaded)} of ${megabytes(p.total)} MB`;
  }

  /** The data has arrived: fill the page from it and run the first search, in a few tasks with a breath between
   *  them (on a slow phone one task of it all would hold a tap or a key for half a second). Rejects if the data cannot
   *  be used; does nothing if another download has taken its place meanwhile. */
  async function onData(d: ConditionsData, source: Promise<ConditionsData>): Promise<void> {
    if (!usable(d)) throw new Error("The data file is not in the expected shape.");
    const stale = (): boolean => destroyed || current !== source;
    // the motion links, as the public site's build writes them: the hosted copy, and Planning's own as the
    // second link. Copies, so a page that shares the data with this search keeps its own untouched.
    const list = d.conditions.map(c => ({
      ...c,
      pdf: c.pdf && pdfBase ? pdfUrl(pdfBase, c.record) : c.pdf,
      motion_url: publicPdf(c.motion_url),
    }));
    await breathe();
    if (stale()) return;
    // what the query parser knows of the data (built once per list, and the first search needs it)
    searchIndex(list);
    await breathe();
    if (stale()) return;
    // a link that carries a search: every condition's keys are made before the first search, a slice at a time
    const firstQuery = pendingQuery ?? (edited ? input.value : useHash ? stateFromHash(location.hash).q : input.value);
    if (firstQuery.trim()) {
      for (let i = 0; i < list.length; ) {
        const until = performance.now() + 8;
        while (i < list.length && performance.now() < until) prepare(list[i++] as Condition);
        await breathe();
        if (stale()) return;
      }
    }
    data = d;
    memo.clear();
    all = list;
    coverageText.innerHTML =
      coverageSentences(d)
        .map(sentence => {
          const colon = sentence.indexOf(": ");
          return colon < 0
            ? `<p>${esc(sentence)}</p>`
            : `<p><b>${esc(sentence.slice(0, colon + 1))}</b> ${esc(sentence.slice(colon + 2))}</p>`;
        })
        .join("") + (opts.coverageHref ? `<p class="cs-coverage__more"><a href="${esc(opts.coverageHref)}">Coverage details</a></p>` : "");
    sub.textContent = subLine(d.count, d.motions_with_conditions);
    fill("business", unique(c => [c.business]).sort());
    fill("category", unique(c => c.categories).sort((a, b) => catLabel(a).localeCompare(catLabel(b))), catLabel);
    fill("zoning", unique(c => [c.zoning]).sort());
    fill("year", unique(c => [c.year]).sort().reverse());
    const kinds = Object.fromEntries(KINDS);
    fill("kind", KINDS.map(([v]) => v), v => kinds[v] ?? v, null);
    find<HTMLElement>("[data-cs-synonyms]").innerHTML = synonymLines().map(l => `<li>${esc(l)}</li>`).join("");
    // what is in the field wins over the hash when the visitor (or setQuery) put it there during the download
    const typed = edited ? input.value : null;
    if (useHash) readState();
    if (pendingQuery !== null) input.value = pendingQuery;
    else if (typed !== null) input.value = typed;
    pendingQuery = null;
    edited = false;
    drawNotes(d);
    wrap.dataset.csState = "ready";
    input.readOnly = false;
    ready = true;
    shown = PAGE;
    render();
    warm();
    root.dispatchEvent(new CustomEvent<SearchDataDetail>("cs:data", { detail: { data: d }, bubbles: true }));
  }

  /** The data could not be loaded, or is not the data: say so, offer another try, and leave nothing half-drawn. */
  function onError(): void {
    data = null;
    all = [];
    hits = [];
    terms = [];
    memo.clear();
    found = { total: 0, motions: 0, hidden: 0 };
    ready = false;
    window.clearTimeout(timer);
    window.clearTimeout(hashTimer);
    window.clearTimeout(liveTimer);
    wrap.dataset.csState = "error";
    // the field keeps its text (a link's search, or what was typed) but cannot be used until the data is here
    input.readOnly = true;
    for (const k of FILTER_KEYS) fields[k].disabled = true;
    countText.textContent = "";
    hiddenLine.remove();
    reset.hidden = true;
    live.textContent = "";
    notes.innerHTML = "";
    sub.textContent = subLine(__DATA_FACTS__.conditions, __DATA_FACTS__.motions);
    coverageText.innerHTML = "<p>Not known until the data loads.</p>";
    results.innerHTML = `<div class="cs-empty cs-empty--error" role="alert"><p class="cs-empty__line">Could not load the data.</p><p class="cs-empty__note">The conditions could not be read. Check the connection and try again.</p><div class="cs-empty__ways"><button class="ruled-button" type="button" data-cs-retry>Try again</button></div></div>`;
  }

  let stopProgress = (): void => {};
  /** The download this search started itself (not one the page handed it): destroy() lets go of it. */
  let own: DataHandle | null = null;
  let current: Promise<ConditionsData> | null = null;

  /** Wait for `source`, then draw the page from it or say it could not be loaded. */
  function load(source: Promise<ConditionsData>): Promise<void> {
    current = source;
    stopProgress();
    if (hasProgress(source)) stopProgress = source.onProgress(onProgress);
    else {
      stopProgress = () => {};
      results.querySelector("[data-cs-progress]")?.classList.add("is-open-ended");
    }
    return Promise.resolve(source)
      .then(d => {
        if (destroyed || current !== source) return;
        stopProgress();
        return onData(d, source);
      })
      .catch((error: unknown) => {
        if (destroyed || current !== source) return;
        stopProgress();
        onError();
        throw error;
      });
  }

  /** "Try again": fetch the data afresh and start over. */
  function retry(): void {
    if (destroyed || ready) return;
    own?.release();
    own = loadConditions(url, __DATA_FACTS__.bytes, { fresh: true });
    wrap.dataset.csState = "loading";
    results.innerHTML = LOADING;
    input.readOnly = false;
    input.focus({ preventScroll: true });
    load(own).catch(() => {});
  }

  if (!opts.data) own = loadConditions(url, __DATA_FACTS__.bytes);
  const first: Promise<ConditionsData> = opts.data ?? (own as DataHandle);
  const dataPromise = Promise.resolve(first);
  // a link's search is in the field from the first paint, not only once the data is here
  if (useHash) {
    input.value = stateFromHash(location.hash).q;
    clearButton.hidden = input.value === "";
  }
  const readyPromise = load(first);
  // a caller that does not await `ready` should not see an unhandled rejection: the page already says what happened
  readyPromise.catch(() => {});

  /** Build the search keys of every condition while the page is idle, so the first keystroke is as quick as the rest. */
  function warm(): void {
    let i = 0;
    const list = all;
    searchIndex(list);
    const idle: (cb: (deadline?: IdleDeadline) => void) => void =
      typeof window.requestIdleCallback === "function"
        ? cb => window.requestIdleCallback(cb, { timeout: 250 })
        : cb => window.setTimeout(cb, 16);
    const step = (deadline?: IdleDeadline): void => {
      if (destroyed || list !== all) return;
      const until = performance.now() + Math.max(4, Math.min(12, deadline?.timeRemaining() ?? 8));
      while (i < list.length && performance.now() < until) prepare(list[i++] as Condition);
      if (i < list.length) idle(step);
      else wrap.dataset.csWarm = "";
    };
    idle(step);
  }

  // ---- the field's examples: one at a time in the placeholder -------------------------------------------------
  const examples = placeholderExamples(PLACEHOLDER);
  /** Three searches that find something, offered when a search finds nothing. */
  const examples3 = (): string[] => examples.filter(x => !/^\d/.test(x)).slice(0, 3);
  let example = 0;
  let cycle = 0;
  const showExample = (): void => {
    input.placeholder = `e.g. ${examples[example % examples.length] ?? ""}`;
  };
  const startCycle = (): void => {
    window.clearInterval(cycle);
    if (reducedMotion() || examples.length < 2) return;
    cycle = window.setInterval(() => {
      // not under the visitor's text, in a hidden tab, or while the field cannot be used
      if (input.value !== "" || document.hidden || input.readOnly) return;
      input.classList.add("is-swapping");
      window.setTimeout(() => {
        example += 1;
        showExample();
        input.classList.remove("is-swapping");
      }, 180);
    }, 3200);
  };
  showExample();
  startCycle();
  const stopWatchingMotion = onReducedMotionChange(startCycle);

  // ---- folds: "Filters" and "Coverage" on a narrow page, "Search tips" everywhere ------------------------------
  function setFold(id: string, open: boolean): void {
    for (const fold of folds) if (fold.getAttribute("aria-controls") === id) fold.setAttribute("aria-expanded", String(open));
    document.getElementById(id)?.toggleAttribute("data-open", open);
  }

  // ---- events ------------------------------------------------------------------------------------------------
  input.addEventListener("input", onInput, { signal });
  input.addEventListener(
    "keydown",
    event => {
      if (input.readOnly) return;
      if (event.key === "Escape" && input.value !== "") {
        event.preventDefault();
        clearQuery();
      } else if (event.key === "Enter") {
        event.preventDefault();
        render();
      }
    },
    { signal },
  );
  find<HTMLFormElement>(".cs-form").addEventListener("submit", event => event.preventDefault(), { signal });
  for (const k of FILTER_KEYS) {
    fields[k].addEventListener("change", () => { shown = PAGE; render(); }, { signal });
  }
  clearButton.addEventListener(
    "click",
    () => {
      if (input.readOnly) return;
      clearQuery();
      input.focus();
    },
    { signal },
  );
  reset.addEventListener(
    "click",
    () => { for (const k of STATE_KEYS) fields[k].value = ""; shown = PAGE; render(); input.focus({ preventScroll: true }); },
    { signal },
  );
  showAll.addEventListener(
    "click",
    () => {
      fields.kind.value = "all";
      shown = PAGE;
      render();
      // the button has gone: the keyboard carries on from the menu it changed, which a narrow page keeps folded away
      if (fields.kind.offsetParent === null) setFold(fields.kind.closest(".cs-fold__body")?.id ?? "", true);
      fields.kind.focus({ preventScroll: true });
      fields.kind.scrollIntoView({ block: "nearest" });
    },
    { signal },
  );
  for (const fold of folds) {
    fold.addEventListener(
      "click",
      () => setFold(fold.getAttribute("aria-controls") ?? "", fold.getAttribute("aria-expanded") !== "true"),
      { signal },
    );
  }
  results.addEventListener(
    "click",
    event => {
      const el = event.target as Element | null;
      if (el?.closest("[data-cs-more]")) showMore();
      else if (el?.closest("[data-cs-retry]")) retry();
      else if (el?.closest("[data-cs-clear-query]")) {
        clearQuery();
        input.focus({ preventScroll: true });
      } else if (el?.closest("[data-cs-clear-filters]")) {
        for (const k of FILTER_KEYS) fields[k].value = "";
        shown = PAGE;
        render();
        input.focus({ preventScroll: true });
      } else {
        const example = el?.closest<HTMLElement>("[data-cs-example]")?.dataset.csExample;
        if (example) {
          input.value = example;
          shown = PAGE;
          render();
          input.focus({ preventScroll: true });
        }
      }
    },
    { signal },
  );
  if (useHash) {
    // a changed hash (a shared link opened in this tab, the back button, an edit in the address bar) runs its search
    window.addEventListener(
      "hashchange",
      () => {
        if (!ready) {
          if (!edited) {
            input.value = stateFromHash(location.hash).q;
            clearButton.hidden = input.value === "";
          }
          return;
        }
        readState();
        shown = PAGE;
        render();
      },
      { signal },
    );
    // a search typed a moment before leaving is still in the address when the page is left
    window.addEventListener("pagehide", () => { if (ready) writeState(read()); }, { signal });
  }
  // "/" puts the cursor in the field from anywhere on the page (unless something is being typed into)
  document.addEventListener(
    "keydown",
    event => {
      if (opts.slashKey === false) return;
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey || event.defaultPrevented) return;
      const el = event.target as HTMLElement | null;
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
      event.preventDefault();
      focus();
    },
    { signal },
  );

  function focus(): void {
    input.focus({ preventScroll: true });
    input.select();
    input.scrollIntoView({ block: "center", behavior: reducedMotion() ? "auto" : "smooth" });
  }

  if (opts.autofocus) input.focus({ preventScroll: true });

  const handle: SearchHandle = {
    setQuery(q) {
      if (!ready) {
        pendingQuery = q;
        input.value = q;
        clearButton.hidden = q === "";
        return;
      }
      input.value = q;
      shown = PAGE;
      render();
    },
    getState,
    focus,
    destroy() {
      if (destroyed) return;
      destroyed = true;
      cancelRest();
      abort.abort();
      stopProgress();
      // a download this search started and nobody else is waiting for is cancelled
      own?.release();
      stopWatchingMotion();
      window.clearTimeout(timer);
      window.clearTimeout(hashTimer);
      window.clearTimeout(liveTimer);
      window.clearInterval(cycle);
      root.innerHTML = "";
      root.classList.remove("cs-root");
      if (mounted.get(root) === handle) mounted.delete(root);
    },
    ready: readyPromise,
    data: dataPromise,
  };
  mounted.set(root, handle);
  return handle;
}
