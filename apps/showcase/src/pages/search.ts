// /search/: the restyled search on its own.

import { setPageTitle } from "../core/brand";
import { isTouch } from "../core/env";
import { coveragePage } from "../core/paths";
import { mountSearch, type SearchDataDetail } from "../core/search";
import { mountShell } from "../core/shell";

setPageTitle("Conditions of approval");

const shell = mountShell({
  current: "search",
  // the page is the search already: the skip link shows when the keyboard reaches it
  skip: { href: "#search", onActivate: () => search.focus(), quiet: true },
});

const sheet = document.createElement("div");
sheet.className = "sheet";
sheet.id = "search";
shell.main.append(sheet);
// the footer's facts follow the data, on the first load and after a "Try again"
sheet.addEventListener("cs:data", event => shell.setFacts((event as CustomEvent<SearchDataDetail>).detail.data));

// a keyboard starts in the field; a phone does not (the keyboard would cover the page)
const search = mountSearch(sheet, { headingLevel: 1, autofocus: !isTouch(), coverageHref: coveragePage() });

// for the console and the tests: window.showcase.search.setQuery("noise")
Object.assign(window, { showcase: { shell, search, mountSearch } });
