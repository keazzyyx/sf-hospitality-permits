/**
 * The product's main claim, in one sentence: what a Location Risk Memo gives (report format 3). It is the landing
 * page headline and opens the site description. A memo does not predict whether an address will be approved; it
 * lists each approval with the rules and records behind its status, and names what is not known.
 */
export const SITE_CLAIM =
  "Every approval your concept needs at an address, with the rules and records behind each, and what's still unknown.";

/**
 * Shown near the top of every report (page and PDF), whatever the memo's format. It states the holdout result of
 * 2026-11-12: on 20 past cases not used to build the rules, the report missed a critical issue in 12. The API's PDF
 * prints the same sentence (`TESTING_NOTICE` in apps/api/app/services/memo_pdf.py); keep the two identical.
 */
export const TESTING_NOTICE =
  "In testing: checked against past cases, this report missed important issues in more than half of new cases. Use it as a starting point, not a conclusion.";
