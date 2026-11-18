// Page chrome shared by every page: the wordmark top left, a "skip to search" link that is first in the tab order
// (always visible on a page with an opening to skip; shown on focus on a page that is the search already), the
// theme flip top right, and a slim footer with the coverage facts, the pages, and the source code and its licence.

import { coverageFacts, day } from "@conditions/coverage";
import { createMarkLink } from "./brand";
import { coveragePage, homePage, sitePath } from "./paths";
import { contactLine, SITE, SOURCE } from "./site";
import { createThemeFlip, initTheme } from "./theme";
import type { ConditionsData } from "./search/types";

export type PageId = "hub" | "c" | "search" | "coverage";

export interface ShellOptions {
  /** Which page this is (marks it in the footer's list). */
  current: PageId;
  /** The skip link. `href` is where it goes without a handler; `onActivate` replaces the jump (a prototype uses it
   *  to end its opening and put the cursor in the search field). */
  skip?: {
    label?: string;
    href?: string;
    onActivate?: (event: MouseEvent) => void;
    /** Keep the link off the screen until the keyboard reaches it: for a page that is the search already, with no
     *  opening to skip. It stays first in the tab order. Default false (always visible). */
    quiet?: boolean;
  };
}

export interface Shell {
  header: HTMLElement;
  /** The page's <main id="main">: a prototype builds inside it. */
  main: HTMLElement;
  footer: HTMLElement;
  /** Fill the footer's facts from the loaded data. */
  setFacts(data: ConditionsData): void;
}

const NS = "http://www.w3.org/2000/svg";
const num = (k: number): string => k.toLocaleString("en-US");

/** The footer's list of pages: the local pages, or the public site's two. */
function pages(): { id: PageId; href: string; label: string }[] {
  if (SITE) {
    return [
      { id: "c", href: SITE.pages.search, label: "Search" },
      { id: "coverage", href: SITE.pages.coverage, label: "Coverage" },
    ];
  }
  return [
    { id: "hub", href: sitePath(""), label: "Contents" },
    { id: "c", href: sitePath("c/"), label: "The front page" },
    { id: "search", href: sitePath("search/"), label: "The search" },
    { id: "coverage", href: coveragePage(), label: "Coverage" },
  ];
}

function downArrow(): SVGSVGElement {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 10 12");
  svg.setAttribute("width", "10");
  svg.setAttribute("height", "12");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const path = document.createElementNS(NS, "path");
  path.setAttribute("d", "M5 0.5v10M1 6.75l4 4 4-4");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.25");
  svg.append(path);
  return svg;
}

/** Build the chrome into <body> and return the regions. Call once per page, before anything else is drawn. */
export function mountShell(options: ShellOptions): Shell {
  initTheme();
  const body = document.body;

  const header = document.createElement("header");
  header.className = "shell-head";
  const inner = document.createElement("div");
  inner.className = "sheet shell-head__inner";

  const skip = document.createElement("a");
  skip.className = options.skip?.quiet ? "shell-skip shell-skip--quiet" : "shell-skip";
  skip.href = options.skip?.href ?? "#main";
  const skipLabel = document.createElement("span");
  skipLabel.textContent = options.skip?.label ?? "Skip to search";
  skip.append(skipLabel, downArrow());
  const onActivate = options.skip?.onActivate;
  if (onActivate) {
    skip.addEventListener("click", event => {
      // no hash jump: the search keeps its state in the hash
      event.preventDefault();
      onActivate(event);
    });
  }

  inner.append(skip, createMarkLink(homePage()), createThemeFlip());
  header.append(inner);

  const main = document.createElement("main");
  main.id = "main";
  main.className = "shell-main";
  main.tabIndex = -1;

  const footer = document.createElement("footer");
  footer.className = "shell-foot";
  const foot = document.createElement("div");
  foot.className = "sheet shell-foot__inner";
  const facts = document.createElement("p");
  facts.dataset.shellFacts = "";
  facts.textContent = `${num(__DATA_FACTS__.conditions)} conditions · ${num(__DATA_FACTS__.motions)} motions`;
  const nav = document.createElement("nav");
  nav.className = "shell-foot__nav";
  nav.setAttribute("aria-label", SITE ? "Pages" : "Local pages");
  for (const page of pages()) {
    const a = document.createElement("a");
    a.href = page.href;
    a.textContent = page.label;
    if (page.id === options.current) a.setAttribute("aria-current", "page");
    nav.append(a);
  }
  // the code and its licence (external: the repository on GitHub)
  const source = document.createElement("nav");
  source.className = "shell-foot__nav shell-foot__source";
  source.setAttribute("aria-label", "Source code");
  for (const link of [
    { href: SOURCE.repo, label: "Source code", rel: "noopener" },
    { href: SOURCE.licence, label: `${SOURCE.licenceName} licence`, rel: "license noopener" },
  ]) {
    const a = document.createElement("a");
    a.href = link.href;
    a.textContent = link.label;
    a.rel = link.rel;
    source.append(a);
  }
  // the public site: its contact line, in the live site's words (one address, also on every card)
  let small: HTMLParagraphElement;
  if (SITE) small = contactLine(SITE.contact);
  else {
    small = document.createElement("p");
    small.textContent = "Local pages, not published. Built from public San Francisco Planning records. Not legal advice.";
  }
  foot.append(facts, nav, source, small);
  footer.append(foot);

  body.append(header, main, footer);

  return {
    header,
    main,
    footer,
    setFacts(data) {
      const f = coverageFacts(data);
      const parts = [
        `${num(f.conditions)} conditions`,
        `${num(f.motionsWithConditions)} motions`,
        `decided ${day(f.decidedFrom)} to ${day(f.decidedTo)}`,
      ];
      if (f.recordsCopiedOn) parts.push(`records copied ${day(f.recordsCopiedOn)}`);
      facts.textContent = parts.join(" · ");
    },
  };
}
