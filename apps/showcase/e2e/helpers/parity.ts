// The comparison the parity tests run: the same URL hash on the current site's page and on a showcase page must
// show the same conditions, in the same order, with the same count sentence.
//
// To hold another page to it, add its path to PATHS in parity.spec.ts, or call
// expectParity(context, hash, { path: "/c/", enter }) with an `enter` step that gets past the page's opening (for
// example, clicking the "Skip to search" link).

import { expect, type BrowserContext, type Page } from "@playwright/test";
import { CURRENT, SHOWCASE } from "../../playwright.config";
import { readFileSync } from "node:fs";

const SECTION_PAGES = JSON.parse(readFileSync(new URL("../../src/core/search/section-pages.json", import.meta.url), "utf8")) as { pages: Record<string, { page: number } | undefined> };

/** A motion link of the current site with no page (a condition read with no page number opens page 1 there) as the
 *  showcase writes it: at the page where that motion's conditions begin (src/core/search/section-pages.json). Every
 *  other link is held to be the same. */
export function atSection(href: string): string {
  const record = /\/motions\/([^/#]+)\.pdf$/.exec(href)?.[1];
  const section = record ? SECTION_PAGES.pages[decodeURIComponent(record)] : undefined;
  return section ? `${href}#page=${section.page}` : href;
}

export interface Snapshot {
  /** The count sentence, as the page shows it (its rendered text, whitespace collapsed). */
  count: string;
  /** Every card once all are shown, in order: "<case number> #<condition number>". */
  cards: string[];
  /** The card the hash points at (marked and scrolled to), or null. */
  target: string | null;
  /** The hash the page wrote back. */
  hash: string;
  /** How many "show more" clicks it took to show everything. */
  clicks: number;
  /** Every card's motion link (the PDF at the condition's page), in order; "" for a card without one. */
  pdfs: string[];
}

export interface ParityOptions {
  /** The showcase page to compare. Default "/search/". */
  path?: string;
  /** A step that gets the showcase page to its search (past a gate or a story). */
  enter?: (page: Page) => Promise<void>;
  /** Where the current site is served (default CURRENT, tools/conditions-search) and the page on it. */
  current?: string;
  currentPath?: string;
  /** Where the showcase is served (default SHOWCASE). */
  showcase?: string;
  /** Also compare the motion links (default false: the local page links its local PDF copies). */
  pdfs?: boolean;
}

/** A URL hash from fields, written the way the pages write it: hash({ q: "outdoor seating", kind: "all" }). */
export function hash(fields: Record<string, string>): string {
  const p = new URLSearchParams(fields).toString();
  return p ? `#${p}` : "";
}

/** The current site's page (tools/conditions-search/index.html, served unchanged) at `urlHash`, fully shown. */
export async function readCurrent(page: Page, urlHash: string, options: ParityOptions = {}): Promise<Snapshot> {
  await page.goto(`${options.current ?? CURRENT}${options.currentPath ?? "/index.html"}${urlHash}`);
  await page.waitForFunction(() => {
    const text = document.querySelector("#count")?.textContent ?? "";
    return text !== "" && !text.startsWith("Loading");
  });
  return page.evaluate(() => {
    const id = (card: Element | null): string | null =>
      card
        ? `${card.querySelector(".meta b")?.textContent?.trim()} #${(card.querySelector(".num")?.textContent ?? "").trim().replace(/\.$/, "")}`
        : null;
    const target = id(document.querySelector("#results .card.target"));
    let clicks = 0;
    for (let more; (more = document.querySelector<HTMLButtonElement>("#more")); ) {
      more.click();
      if (++clicks > 400) throw new Error("the current page never ran out of 'show more'");
    }
    return {
      count: (document.querySelector<HTMLElement>("#count")?.innerText ?? "").replace(/\s+/g, " ").trim(),
      cards: [...document.querySelectorAll("#results .card")].map(card => id(card) ?? ""),
      target,
      hash: location.hash,
      clicks,
      pdfs: [...document.querySelectorAll("#results .card")].map(card => card.querySelector<HTMLAnchorElement>(".links a[href*=\"/motions/\"]")?.href ?? ""),
    };
  });
}

/** A showcase page at `urlHash`, fully shown. Reads what the page displays, not its data attributes. */
export async function readShowcase(page: Page, urlHash: string, options: ParityOptions = {}): Promise<Snapshot> {
  await page.goto(`${options.showcase ?? SHOWCASE}${options.path ?? "/search/"}${urlHash}`);
  if (options.enter) await options.enter(page);
  await page.locator('.cs[data-cs-state="ready"]').waitFor();
  return page.evaluate(() => {
    const id = (card: Element | null): string | null =>
      card
        ? `${card.querySelector("[data-cs-record]")?.textContent?.trim()} #${card.querySelector("[data-cs-num]")?.textContent?.trim()}`
        : null;
    const target = id(document.querySelector("[data-cs-card].is-target"));
    let clicks = 0;
    for (let more; (more = document.querySelector<HTMLButtonElement>("[data-cs-more]")); ) {
      more.click();
      if (++clicks > 400) throw new Error("the showcase page never ran out of 'show more'");
    }
    return {
      count: (document.querySelector<HTMLElement>("[data-cs-count]")?.innerText ?? "").replace(/\s+/g, " ").trim(),
      cards: [...document.querySelectorAll("[data-cs-card]")].map(card => id(card) ?? ""),
      target,
      hash: location.hash,
      clicks,
      pdfs: [...document.querySelectorAll("[data-cs-card]")].map(card => card.querySelector<HTMLAnchorElement>("[data-cs-pdf]")?.href ?? ""),
    };
  });
}

/** Load `urlHash` on both pages, show everything on both, and hold the showcase page to the current one. */
export async function expectParity(
  context: BrowserContext,
  urlHash: string,
  options: ParityOptions = {},
): Promise<{ current: Snapshot; showcase: Snapshot }> {
  const [a, b] = [await context.newPage(), await context.newPage()];
  const [current, showcase] = await Promise.all([readCurrent(a, urlHash, options), readShowcase(b, urlHash, options)]);
  await Promise.all([a.close(), b.close()]);
  expect(showcase.count, "the count sentence").toBe(current.count);
  expect(showcase.cards.length, "how many conditions are shown").toBe(current.cards.length);
  expect(showcase.cards, "the conditions, in order").toEqual(current.cards);
  expect(showcase.target, "the card the link points at").toBe(current.target);
  expect(showcase.hash, "the hash written back").toBe(current.hash);
  expect(showcase.clicks, "'show more' clicks to show everything").toBe(current.clicks);
  if (options.pdfs) expect(showcase.pdfs, "the motion links, at their pages").toEqual(current.pdfs.map(atSection));
  return { current, showcase };
}

/** The filter menus (value and label of every option) of a page, by field. */
export async function readFilters(page: Page, kind: "current" | "showcase"): Promise<Record<string, string[]>> {
  return page.evaluate(which => {
    const keys = ["business", "category", "zoning", "year", "kind"];
    const select = (key: string): HTMLSelectElement | null =>
      which === "current"
        ? document.querySelector<HTMLSelectElement>(`#${key}`)
        : document.querySelector<HTMLSelectElement>(`[data-cs-field="${key}"]`);
    return Object.fromEntries(
      keys.map(key => [key, [...(select(key)?.options ?? [])].map(o => `${o.value}|${o.textContent}`)]),
    );
  }, kind);
}
