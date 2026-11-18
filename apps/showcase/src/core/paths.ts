// The local pages are built with relative paths (vite base "./"), so each page says where the site root is from
// where it sits: <html data-root="../"> on /c/, /search/ and /coverage/, "./" on the contents page. The public site
// (src/core/site.ts) loads its content-named files by their own root-relative URLs.

import { SITE } from "./site";

/** The site root relative to the current page: "./" or "../" ("/" on the public site). */
export function siteRoot(): string {
  const root = document.documentElement.dataset.root ?? "./";
  return root.endsWith("/") ? root : root + "/";
}

/** A path from the site root, as a URL the current page can use: sitePath("data/conditions.json"). */
export function sitePath(path: string): string {
  return siteRoot() + path.replace(/^\/+/, "");
}

/** Where the search data is served: /data/conditions.json (see vite.config.ts), or the site's content-named copy. */
export function dataUrl(): string {
  return SITE?.files.conditions ?? sitePath("data/conditions.json");
}

/** The map's two files: the streets and the motions. */
export function streetsUrl(): string {
  return SITE?.files.streets ?? sitePath("data/sf-streets.bin");
}
export function motionsUrl(): string {
  return SITE?.files.motions ?? sitePath("data/motions.json");
}

/** The page with the search on it, and the coverage page. */
export function searchPage(): string {
  return SITE?.pages.search ?? sitePath("search/");
}
export function coveragePage(): string {
  return SITE?.pages.coverage ?? sitePath("coverage/");
}

/** The contents page (the mark links to it): the front page on the public site. */
export function homePage(): string {
  return SITE?.pages.search ?? sitePath("");
}
