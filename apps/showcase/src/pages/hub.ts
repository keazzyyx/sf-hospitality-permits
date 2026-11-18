// /: the contents page of the local build. The public site has no such page: its front page is /c/'s (see
// vite.config.ts, "--mode site").

import { setPageTitle } from "../core/brand";
import { mountShell } from "../core/shell";
import { coveragePage, sitePath } from "../core/paths";
import "./hub.css";

setPageTitle("Contents");

const shell = mountShell({ current: "hub", skip: { href: sitePath("search/"), label: "Skip to search" } });

const num = (k: number): string => k.toLocaleString("en-US");
const esc = (s: string): string =>
  s.replace(/[&<>"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch] ?? ch);

const ROWS: { key: string; href: string; path: string; name: string; what: string }[] = [
  {
    key: "1",
    href: sitePath("c/"),
    path: "c/",
    name: "The front page",
    what: "The stamp gate, the story of one motion flown over the city's street grid, and the search beside the map. The public site's index.html.",
  },
  {
    key: "2",
    href: sitePath("search/"),
    path: "search/",
    name: "The search",
    what: "The search on its own: every condition, searchable by word, case number or address.",
  },
  {
    key: "3",
    href: coveragePage(),
    path: "coverage/",
    name: "Coverage",
    what: "What the search covers: the numbers, the reviewed list, the detail. The public site's coverage.html.",
  },
];

const sheet = document.createElement("div");
sheet.className = "sheet hub";
sheet.innerHTML = `
  <header class="hub__head">
    <p class="label hub__eyebrow">Local pages · not published</p>
    <h1 class="hub__title">Conditions of approval, <em>the local build.</em></h1>
    <p class="hub__lead">A public search of the conditions San Francisco's Planning Commission attached to
      restaurants, bars and venues: <b>${num(__DATA_FACTS__.conditions)}</b> conditions from
      <b>${num(__DATA_FACTS__.motions)}</b> motions. The public site is built from these pages by
      <code>vite build --mode site</code>.</p>
  </header>
  <ol class="hub__list">
    ${ROWS.map(
      r => `<li class="hub__row"><a class="hub__link" href="${esc(r.href)}">
        <span class="hub__key" aria-hidden="true">${esc(r.key)}</span>
        <span class="hub__name">${esc(r.name)}</span>
        <span class="hub__what">${esc(r.what)}</span>
        <span class="hub__path">/${esc(r.path)}</span>
      </a></li>`,
    ).join("")}
  </ol>`;
shell.main.append(sheet);
