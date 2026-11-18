/** Set by vite.config.ts from the data file when the dev server or the build starts. */
declare const __DATA_FACTS__: { conditions: number; motions: number; bytes: number };

/** The public site's settings, set by vite.config.ts in the site build (`vite build --mode site`); null on the local
 *  pages. Read it through src/core/site.ts. */
declare const __SITE__: {
  name: string;
  /** The address of the contact line and of every card's "Wrong or missing? Tell me". Empty: no contact line and
   *  no card link (a copy of the site built without an address). */
  contact: string;
  /** Where the motion PDFs are (<pdfBase><record>.pdf): the store the build pointed the data at. */
  pdfBase: string;
  /** The content-named files the pages load, root-relative. */
  files: { conditions: string; motions: string; streets: string; coverage: string };
  /** The two pages. */
  pages: { search: string; coverage: string };
} | null;
