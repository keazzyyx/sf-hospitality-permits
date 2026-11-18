// Types for the two modules imported, unchanged, from the current site (tools/conditions-search/search.js and
// coverage.js) through the Vite aliases in vite.config.ts. Only what this app uses is declared.

declare module "@conditions/search" {
  export type StateKey = "q" | "business" | "category" | "zoning" | "year" | "kind";
  export type FilterState = Record<StateKey, string>;

  /** One condition of approval, as data/conditions.json holds it. */
  export interface Condition {
    record: string;
    address: string;
    zoning: string;
    business: string;
    decided: string | null;
    year: string;
    number: string;
    title: string;
    text: string;
    categories: string[];
    standard: boolean;
    kind: string;
    template: boolean;
    split_from: string | null;
    motion_url: string | null;
    pdf: string | null;
    page: number | null;
    page_exact: boolean;
    text_source: string;
    readable: boolean;
    raw_text?: string | null;
  }

  export interface MotionWithout {
    record: string;
    address: string;
    decided?: string | null;
    outcome?: string | null;
    why?: string | null;
  }

  export interface RemovedMotion {
    record: string;
    address: string;
    what?: string | null;
    left_out_by?: string | null;
  }

  /** One correction the review made to the classifier's pick of motions. */
  export interface ReviewDecision {
    record: string;
    address?: string | null;
    what?: string | null;
    decision?: string | null;
    business?: string | null;
    reason?: string | null;
  }

  export interface ConditionsData {
    count: number;
    motions: number;
    motions_with_conditions: number;
    motions_without_conditions: MotionWithout[];
    removed_motions: RemovedMotion[];
    review?: { decisions?: ReviewDecision[]; added_back?: unknown[]; removed?: unknown[]; reviewed_on?: string | null };
    boilerplate_titles: string[];
    coverage?: Record<string, unknown>;
    text_quality?: Record<string, number>;
    conditions: Condition[];
  }

  /** A parsed query term (opaque to this app: passed back to the matcher and the highlighter). */
  export interface Term {
    text: string;
    alts: Set<string>;
    pattern: RegExp | null;
    record?: string;
    recordPart?: string;
    address?: string;
    street?: string;
  }

  export interface CardTarget {
    record: string;
    number: string;
  }

  export const KINDS: [string, string][];
  export const STATE_KEYS: StateKey[];
  export const CARD_KEY: string;
  export function search(all: Condition[], f: Partial<FilterState>): Condition[];
  export function parseQuery(q: string, all?: Condition[]): Term[];
  export function highlight(text: string, q: string | Term[], esc: (s: unknown) => string): string;
  export function noMatchNote(all: Condition[], q: string): string;
  export function recordMatches(c: Condition, terms: Term[]): boolean;
  export function addressMatches(c: Condition, terms: Term[]): boolean;
  export function synonymLines(): string[];
  export function stateFromHash(hash: string): FilterState;
  export function hashFromState(state: Partial<FilterState>): string;
  export function placeholderExamples(placeholder: string): string[];
  export function cardLink(c: Pick<Condition, "record" | "number">, base: string): string;
  export function cardTarget(hash: string): CardTarget | null;
  export function cardIndex(hits: Condition[], target: CardTarget | null): number;
  export function shownFor(index: number, shown: number, page: number): number;
  export function feedbackLink(c: Condition, opts: { to: string; base?: string }, esc: (s: unknown) => string): string;
  export function prepare(c: Condition): Condition;
  export function searchIndex(all: Condition[]): unknown;
}

declare module "@conditions/coverage" {
  import type { ConditionsData } from "@conditions/search";

  export interface CoverageFacts {
    conditions: number;
    motionsWithConditions: number;
    motionsKept: number;
    withoutConditions: number;
    removed: number;
    reviewed: boolean;
    reviewedOn: string | null;
    decidedFrom: string | undefined;
    decidedTo: string | undefined;
    unreadable: number;
    recordsCopiedOn: string | undefined;
    lookedUpOn: string | undefined;
    builtOn: string | undefined;
    classifierKept: number;
    classifierRemoved: number;
    addedByReview: number;
    removedByReview: number;
    businessSetByReview: number;
    since: string | undefined;
    casesLookedUp: number | undefined;
    motionsFound: number | undefined;
    notFound: number;
    nearPage: number;
    noPage: number;
    byOcr: number;
  }

  /** "2019-01-16" -> "16 Jan 2019". */
  export function day(iso: string | null | undefined): string;
  export function coverageFacts(data: ConditionsData): CoverageFacts;
  export function coverageSentences(data: ConditionsData): string[];
  /** Markdown to HTML for what the current site's README uses (escaped; only safe links kept). */
  export function renderMarkdown(md: string): string;
  /** The body of the "## heading" section of a markdown text ("" when there is none). */
  export function markdownSection(md: string, heading: string): string;
}

// The sections of the current site's README that its coverage.html shows, cut out at build time (vite.config.ts).
declare module "virtual:coverage-sections" {
  const sections: { heading: string; body: string }[];
  export default sections;
}

declare module "virtual:story-facts" {
  /** The part of src/data/story.json the story shows (tools/story-facts.mjs). */
  const facts: unknown;
  export default facts;
}
