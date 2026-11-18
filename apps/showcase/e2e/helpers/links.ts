// A motion PDF opened at page 1 prints the project sponsor's name and address: no link on the page may open one
// there, and no feedback e-mail may carry such a link either. Used by e2e/c.spec.ts (the local build) and
// e2e-site/site.spec.ts (the public site's build).

import type { Page } from "@playwright/test";

/** Every PDF link on the page that opens without a page of 2 or more: in any element's href, and in the subject or
 *  body of every mailto: link (decoded, as the mail program reads it). "where: link" for each; empty when none. */
export function pagelessPdfLinks(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const bad: string[] = [];
    const scan = (text: string, where: string): void => {
      for (const m of text.matchAll(/[^\s"'<>]*\.pdf(?:#page=(\d+))?/gi)) {
        if (!m[1] || Number(m[1]) < 2) bad.push(`${where}: ${m[0]}`);
      }
    };
    for (const el of document.querySelectorAll<HTMLElement>("[href]")) {
      const href = el.getAttribute("href") ?? "";
      if (href.startsWith("mailto:")) {
        let text = href;
        try {
          text = decodeURIComponent(href);
        } catch {
          // not decodable: read it as it is
        }
        scan(text, "mailto");
      } else scan(href, "href");
    }
    return bad;
  });
}

/** The decoded mailto: hrefs of the cards' feedback links, in order. */
export function feedbackMails(page: Page): Promise<string[]> {
  return page.locator("[data-cs-card] a.feedback").evaluateAll(as => as.map(a => decodeURIComponent(a.getAttribute("href") ?? "")));
}
