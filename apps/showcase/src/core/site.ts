// The public site (SF Conditions Search) or the local pages: one build of the same code each. The site build
// (`vite build --mode site`, run by scripts/validation/build_public_conditions_site.py) fills SITE in; on the local
// pages it is null.

export const SITE = __SITE__;

export { SOURCE } from "./source";

/** The site's contact line, in the live site's words: one address for questions, corrections and the card links. */
export function contactLine(address: string): HTMLParagraphElement {
  const p = document.createElement("p");
  p.className = "shell-contact";
  const rest = "Built from public San Francisco Planning records. Not legal advice. Page views are counted by Vercel Web Analytics, without cookies.";
  // (a copy of the site built without an address says the rest)
  if (!address) {
    p.append(rest);
    return p;
  }
  const a = document.createElement("a");
  a.href = `mailto:${address}`;
  a.textContent = address;
  p.append("Questions or corrections: ", a, `. ${rest}`);
  return p;
}
