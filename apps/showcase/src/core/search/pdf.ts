// Motion PDF links, built the way the public site's build does it
// (scripts/validation/build_public_conditions_site.py: PDF_BASE_URL, pdf_url, public_pdf).

/** The public store that holds a copy of every adopted motion: <base><record>.pdf. */
export const PDF_BASE_URL = "https://example.public.blob.vercel-storage.com/motions/";

/** Python's urllib.parse.quote(s, safe=""): everything but letters, digits and "_.-~" is percent-encoded. */
function quote(s: string): string {
  return encodeURIComponent(s).replace(/[!'()*]/g, ch => "%" + ch.charCodeAt(0).toString(16).toUpperCase());
}

/** The public URL of a motion's copy: base + <record>.pdf, the record quoted for a URL. */
export function pdfUrl(base: string, record: string): string {
  return base + quote(`${record}.pdf`);
}

/** Planning's own download link with showopendialog=0. Browsers still download it, so it is only the second,
 *  smaller link. */
export function publicPdf(url: string | null | undefined): string | null {
  return url ? url.replace("showopendialog=1", "showopendialog=0") : null;
}

/** A motion link at the condition's page: "#page=N" when the page is known. */
export function atPage(pdf: string, page: number | null | undefined): string {
  return pdf + (page ? `#page=${page}` : "");
}
