"""Build "SF Conditions Search": the public, read-only static site of the conditions search.

Two front ends over the same public data (--front):

- "c" (the default since 2026-11-17): the front page of apps/showcase, "the living grid": a stamp gate over San
  Francisco's street grid, the story of one motion flown over it, and the search beside the map (a returning visitor
  or a link that carries a search opens on the search alone), with its coverage page in the same design. The builder
  prepares the public data (below), then runs `pnpm --dir apps/showcase exec vite build --mode site` against it
  (vite_site: SHOWCASE_DATA, SHOWCASE_COVERAGE_MD and SHOWCASE_CONTACT, in a temporary folder), which writes
  index.html, coverage.html and assets/: Vite's scripts, styles, fonts and icon (assets/<name>-<hash>.<ext>), and the
  data files named by their content as below (the search data, the map's streets and motions, the coverage text).
  The search logic is tools/conditions-search/search.js itself, imported unchanged, so the results are the live
  page's; the data file is byte for byte the one the classic front end publishes (same name, same hash).
- "classic": tools/conditions-search's plain page, byte for byte as deployed until 2026-11-17 (kept so that the old
  site can be rebuilt and deployed again). It reads tools/conditions-search/ (index.html, search.js, coverage.js,
  coverage.html) and rewrites them as below.

Both publish the same data, coverage text, vercel.json and PDF manifest. What the build does to the local data and
pages:

- the title reads "SF Conditions Search" (and "Coverage · SF Conditions Search"); the C front end keeps the wordmark
  of apps/showcase/src/core/brand.ts on the page;
- every motion link opens a copy of the adopted motion PDF in the site's file storage (the public Vercel Blob
  store, PDF_BASE_URL<record>.pdf, or --pdf-base-url) at the condition's page (#page=N), with a second, smaller
  link to Planning's own copy. The site itself is only HTML, scripts, styles, fonts and data: the PDFs are not
  copied into it (since 2026-11-13; before, they were served from pdf/ on the site). The builder writes a manifest
  of the copies to upload (PDF manifest, outside the site: record, local file, bytes, sha256, public URL), and
  tools/conditions-search/upload-pdfs.mjs uploads them to the store. Planning's link
  (link.ashx?Action=Download) makes the browser download the PDF, which loses the page jump, and the hearing
  packets on commissions.sfplanning.org hold the staff report and the DRAFT motion (other page numbers, and
  changes made at the hearing are not in them; checked 2026-11-12 on 2018-005694CUA and 2021-003599CUA), so
  neither can carry the page link (a packet at the plain cpcpackets/<record>.pdf address was not found for
  2024-001899CUA and 2025-007559CUA). The hosted copies are the cached adopted motions made smaller with
  ghostscript (compress_pdf): same pages in the same order, text layer kept on every page that holds conditions.
  Motions decided 2019 on keep the copies hosted since 2026-11-12 byte for byte (their cached copies are reused;
  standard_compress, GS_SETTINGS): images at 150 dpi, and plan drawings (pages outside the conditions that weigh
  more than HEAVY_PAGE_BYTES on their own) as 100 dpi pictures of the page. Motions decided before 2019
  (HARDER_BEFORE) are made harder since 2026-11-13 so that the site stays near its size with them
  (older_compress, OLDER_GS_SETTINGS): every page in grayscale, a scan's black-and-white text layer kept at
  150 dpi, other images at 100 dpi (low JPEG quality) on the pages that hold conditions (older_condition_span:
  the first condition's page to the page where the last one ends) and 50 dpi (lowest JPEG quality) on the rest
  ("gray72", harder, only for a copy still over PDF_MAX_BYTES); pages outside the conditions that still weigh
  more than OLDER_HEAVY_PAGE_BYTES on their own (HUGE_PAGE_BYTES in the original: straight away) become grayscale
  pictures of the page at 72 dpi (less for a sheet over RASTER_MAX_PIXELS across), which lose their selectable
  text and small print. A born-digital motion that ghostscript cannot make smaller is hosted as it is. Each copy
  is checked against the original (check_pdf: page count, and each condition's opening words still on its page)
  and cached under $LOCAL_DATA_DIR/conditions_pdf_public/. The bucket serves them as application/pdf with no
  Content-Disposition (inline, so the browser's viewer opens them at #page=N) and a long cache;
- the coverage detail page shows tools/conditions-search/public/coverage.md (plain, public wording) with "Text
  quality" and the list of motions left out, built from the data (public_coverage_md), in place of the local README;
- a contact line is added under the page, and the "Wrong or missing? Tell me" link on every result card emails the
  same CONTACT address (classic: the build sets the page's FEEDBACK_TO; C: the Vite build is given it as
  SHOWCASE_CONTACT and passes it to the search's feedbackTo), so the address comes only from CONTACT_EMAIL at build
  time (the local pages, and a build without CONTACT_EMAIL, leave it empty and show no link);
- both pages load Vercel Web Analytics from the site itself (/_vercel/insights/script.js, the plain-HTML snippet
  with its window.va queue, as tools/conditions-search/index.html carries it; the C build copies it from there):
  cookieless page views, with the part of the address after "#" (the search typed) taken off before a view is
  sent. It is the only tracker. The Content-Security-Policy (CSP) allows it: the script and its requests are
  same-origin ('self'), and the queue is an inline script ('unsafe-inline');
- the data file drops the build notes and the raw first readings of conditions, and withholds private liaison
  contacts ("[contact in the motion]", private_contacts.py);
- the files the pages load are named by their content under /assets/ (served immutable); the pages themselves are
  served "no-cache" (vercel.json), with the same security headers and CSP for both front ends;
- comments are taken out of the classic scripts (the C bundles are minified by Vite, with no source maps).

Before a file is written, check_site reads every text file of the output (the pages, Vite's script and style
bundles, the data, the coverage text) and the build stops on: the product name or an internal path, table or tool
(FORBIDDEN); a "raw_text" field; a link to page 1 of a motion; a withheld private contact (the strings the
withholding takes out, read from the local data, story.json and the data as it was before the withholding began,
from git), a phone number that is not the City's, an e-mail address that is not the City's or CONTACT; a published
condition the withholding would still change; the analytics snippet not exactly once in each page's head; a motion
link outside the file storage; and, for the C front end, a source map, any file outside the expected set
(C_PAGES, vercel.json, C_ASSET), a content name that is not its content's, or a data file missing; and, since a
card's links (its feedback e-mail among them) are only written as the page runs, the built C site is opened in a
headless browser (apps/showcase/tools/check-links.mjs, check_links) on every motion read with no page and on a long
list: any link or feedback e-mail that would open a motion without a page of 2 or more stops the build (so does a
browser that cannot be had: the check is never skipped).
No model, no network. Needs ghostscript (gs) and poppler (pdftotext, pdfinfo); --front c also needs pnpm and the
repository's node_modules (pnpm install).

    python3 scripts/validation/build_public_conditions_site.py [--front c|classic] [--out DIR] [--manifest FILE]
                                                               [--pdf-base-url URL] [--pdf-root DIR]

The default output is $LOCAL_DATA_DIR/sf-conditions-search-site/ (outside the repo, so the deploy uploads
only the site), and the PDF manifest goes next to it: <out's parent>/sf-conditions-search-pdfs/manifest.json
(never inside the site). --pdf-root is where the local data's pdf/<record>.pdf paths are (default
tools/conditions-search; a git worktree has none: pass the main checkout's). Upload the PDFs first (node
tools/conditions-search/upload-pdfs.mjs --apply), then deploy the site, both by hand: vercel deploy
--prod from the site folder. To look at a build first: node apps/showcase/tools/serve-site.mjs DIR PORT
(vercel.json's headers and CSP applied); apps/showcase/e2e-site/site.spec.ts holds it to the live site
(SITE_DIR=DIR pnpm --filter showcase test:site).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlencode

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "tools" / "conditions-search"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from private_contacts import private_contact_strings, withhold_private_contacts  # noqa: E402
from private_contacts import CITY_EMAIL_DOMAINS, CITY_PHONE_PREFIXES, CITY_PHONES, EMAIL, PHONE  # noqa: E402
DEFAULT_OUT = Path(os.environ.get("LOCAL_DATA_DIR", "~/sfhp-local")).expanduser() / "sf-conditions-search-site"
NAME = "SF Conditions Search"
# The contact address printed under the page: set CONTACT_EMAIL when building (for example
# CONTACT_EMAIL=feedback@example.org). Without it the page has no contact address.
CONTACT = os.environ.get("CONTACT_EMAIL", "").strip()
# The page's constant for the address the card feedback links email (index.html); the build fills in CONTACT.
FEEDBACK_TO = 'const FEEDBACK_TO = "";'
# Vercel Web Analytics, as both source pages load it (the build checks it is still there, unchanged).
ANALYTICS_SCRIPT = '<script defer src="/_vercel/insights/script.js"></script>'

# The app's name (also as permit-memo / permit_memo / permit.memo) and internal names. A storage URL
# (https://<store>.public.blob.vercel-storage.com/motions/...) passes: no product name in it.
FORBIDDEN = re.compile(
    r"permit[\s_.-]*memo|localhost|127\.0\.0\.1|~/|scripts/|\.py\b|psql|record_labels|case_conditions|case_motions"
    r"|apps/api|anthropic|claude|haiku|/usr/share|README",
    re.IGNORECASE,
)
DROP_CONDITION_FIELDS = ("raw_text",)
DROP_TOP_FIELDS = ("_doc",)
PDF_CACHE = Path(os.environ.get("LOCAL_DATA_DIR", "~/sfhp-local")).expanduser() / "conditions_pdf_public"
PDF_MAX_BYTES = 20_000_000  # per file: try harder settings above this
# all the motion PDFs together: the owner's target ("under about 250 MB in all"); the build warns above it
PDF_TOTAL_TARGET_BYTES = 250_000_000
PDF_WORKERS = 4
# Where the site links the motion PDFs: a public Vercel Blob store kept apart from the app. Object pathname:
# motions/<record>.pdf, served inline as application/pdf, so #page=N opens the motion at the condition's page.
# Set PDF_BASE_URL to your store's https://<store>.public.blob.vercel-storage.com/motions/ (or pass
# --pdf-base-url); the default below is a placeholder. tools/conditions-search/upload-pdfs.mjs reads the same
# variable.
PDF_STORE_URL = "https://example.public.blob.vercel-storage.com"
PDF_BUCKET = "motions"
PDF_BASE_URL = os.environ.get("PDF_BASE_URL") or f"{PDF_STORE_URL}/{PDF_BUCKET}/"
UPLOAD_LIMIT_BYTES = 50 * 1024 * 1024  # per file: kept as a sanity bound (the largest copy is about 11 MB)
MANIFEST_DIR_NAME = "sf-conditions-search-pdfs"

# Two kinds of hosted copy, by when the motion was decided (the conditions' "decided", case_motions.decided_at):
# - decided HARDER_BEFORE or later (2019 on): the copies hosted since 2026-11-12. Their cached copies
#   (PDF_CACHE_VERSION) are reused as they are, so the site keeps the very same files; the settings below that
#   made them (GS_SETTINGS, HEAVY_PAGE_BYTES, RASTER_DPI, RASTER_JPEG_QUALITY, condition_span) are kept unchanged
#   in case one has to be made again. Changing them, or PDF_CACHE_VERSION, changes those files.
# - decided before HARDER_BEFORE (2010-2018): harder copies (OLDER_*, older_compress) so that the site stays near
#   its 2026-11-12 size with about 290 more motions (the owner, 2026-11-13: "Compress the older PDFs harder so the
#   site stays near today's size").
HARDER_BEFORE = "2019-01-01"

# ---- 2019 on (as hosted since 2026-11-12) ----------------------------------------------------------------------
# ghostscript settings, gentlest first. Each keeps every page and the text; only images are downsampled.
GS_SETTINGS = {
    "ebook": ["-dPDFSETTINGS=/ebook"],  # images at 150 dpi
    "100dpi": ["-dPDFSETTINGS=/ebook", "-dDownsampleColorImages=true", "-dColorImageResolution=100",
               "-dDownsampleGrayImages=true", "-dGrayImageResolution=100", "-dDownsampleMonoImages=true",
               "-dMonoImageResolution=200"],
    "screen": ["-dPDFSETTINGS=/screen"],  # images at 72 dpi
}
# A page outside the conditions that adds more than this to the file on its own (a plan drawing, mostly vector
# lines) is turned into a picture of the page at RASTER_DPI.
HEAVY_PAGE_BYTES = 200_000
RASTER_DPI = 100
RASTER_JPEG_QUALITY = 60
PDF_CACHE_VERSION = 4  # bump when GS_SETTINGS, the raster rule or check_pdf change (it remakes every 2019-on copy)


# ---- before 2019 (harder, since 2026-11-13) --------------------------------------------------------------------
def gs_gray(dpi: int, qfactor: float, mono_dpi: int = 150) -> list[str]:
    """ghostscript pdfwrite arguments: every page in grayscale, colour and gray images downsampled to `dpi` and
    saved as JPEG with this QFactor (Acrobat's scale: 0.76 medium, 1.3 low, 2.4 minimum quality), black-and-white
    images (a scan's text layer, kept as CCITT) to `mono_dpi`. The text, also a scan's invisible OCR text, is kept."""
    jpeg = f"<< /QFactor {qfactor} /Blend 1 /HSamples [2 1 1 2] /VSamples [2 1 1 2] >>"
    return ["-dPDFSETTINGS=/ebook", "-sColorConversionStrategy=Gray", "-dProcessColorModel=/DeviceGray",
            "-dDownsampleColorImages=true", f"-dColorImageResolution={dpi}", "-dColorImageDownsampleThreshold=1.0",
            "-dDownsampleGrayImages=true", f"-dGrayImageResolution={dpi}", "-dGrayImageDownsampleThreshold=1.0",
            "-dDownsampleMonoImages=true", f"-dMonoImageResolution={mono_dpi}", "-dMonoImageDownsampleThreshold=1.0",
            "-dMonoImageDownsampleType=/Subsample",
            "-c", (f"<< /ColorACSImageDict {jpeg} /GrayACSImageDict {jpeg} /ColorImageDict {jpeg} /GrayImageDict {jpeg}"
                   " >> setdistillerparams"), "-f"]  # fmt: skip


# ghostscript settings, gentlest first; harder ones only while a copy is over PDF_MAX_BYTES. Each keeps every page
# and its text; only images are made grayscale and smaller. "text" is for the pages that hold conditions
# (older_condition_span), "rest" for the others: a scanned motion (2015-2018 mostly: a 300 dpi black-and-white
# text layer over two 100 dpi colour layers) keeps its text sharp at 150 dpi on every page, but the colour layers
# of the other pages go down to 50 dpi.
OLDER_GS_SETTINGS = {
    "gray": {"text": gs_gray(100, 1.3), "rest": gs_gray(50, 2.4)},
    "gray72": {"text": gs_gray(72, 2.4), "rest": gs_gray(36, 2.4)},
}
# A page outside the conditions that still adds more than this to the copy on its own (a plan drawing, mostly
# vector lines) is turned into a grayscale picture of the page at OLDER_RASTER_DPI.
OLDER_HEAVY_PAGE_BYTES = 100_000
# A page outside the conditions that adds more than this to the ORIGINAL is made a picture straight away, without
# going through pdfwrite first: a big plan set in grayscale can keep ghostscript busy for over an hour.
HUGE_PAGE_BYTES = 1_000_000
GS_TIMEOUT = 900  # seconds; a longer ghostscript run counts as failed (the copy falls back to the next option)
OLDER_RASTER_DPI = 72
RASTER_MAX_PIXELS = 1600  # a bigger sheet (a 36 x 24 in plan set) is drawn at a lower dpi: this many pixels across
OLDER_RASTER_JPEG_QUALITY = 50
OLDER_PDF_CACHE_VERSION = 5  # bump when OLDER_*, older_condition_span or check_pdf change (remakes pre-2019 copies)


def public_pdf(url: str | None) -> str | None:
    """Planning's download link with showopendialog=0. Browsers still download it (Action=Download), so it is
    only the second link; the page link is the hosted copy."""
    if not url:
        return None
    return url.replace("showopendialog=1", "showopendialog=0")


def letters(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def page_count(pdf: Path) -> int:
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True).stdout
    return int(out.split("Pages:")[1].split()[0])


def page_sizes(pdf: Path) -> dict[int, tuple[float, float]]:
    """{page: (width, height)} in points (pdfinfo)."""
    out = subprocess.run(["pdfinfo", "-f", "1", "-l", str(page_count(pdf)), str(pdf)], capture_output=True,
                         text=True, check=True).stdout  # fmt: skip
    sizes = re.finditer(r"Page\s+(\d+) size:\s+([\d.]+) x ([\d.]+)", out)
    return {int(m[1]): (float(m[2]), float(m[3])) for m in sizes}


def raster_dpi(size: tuple[float, float] | None) -> int:
    """OLDER_RASTER_DPI, lower for a page so big that it would be more than RASTER_MAX_PIXELS across."""
    if not size:
        return OLDER_RASTER_DPI
    return max(24, min(OLDER_RASTER_DPI, int(RASTER_MAX_PIXELS * 72 / max(size))))


def page_texts(pdf: Path) -> list[str]:
    """Letters of each page's text (pdftotext), one entry per page."""
    out = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=False).stdout
    return [letters(t) for t in out.split("\f")]


def check_pdf(original: Path, small: Path, conditions: list[dict]) -> list[str]:
    """Problems with a smaller copy: a different page count, or a condition whose opening words are on its page
    in the original but not in the copy (pdftotext on both; a condition whose opening words pdftotext does not
    find on the original's page is not checked). Empty when the copy is good."""
    if page_count(original) != page_count(small):
        return [f"page count {page_count(original)} -> {page_count(small)}"]
    a, b = page_texts(original), page_texts(small)
    problems = []
    for c in conditions:
        if not c.get("page"):
            continue
        body = letters(c["text"])
        for probe in (body[:40], body[:25]):
            if len(probe) >= 20 and c["page"] <= len(a) and probe in a[c["page"] - 1]:
                if c["page"] > len(b) or probe not in b[c["page"] - 1]:
                    problems.append(f"#{c['number']}: opening words not on page {c['page']} of the copy")
                break
    return problems


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gs(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    """ghostscript; with a `timeout` (seconds), a longer run counts as failed (returncode -1)."""
    cmd = ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", *args]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, -1, "", f"took over {timeout} s")


def gs_pdfwrite(src: Path, dst: Path, args: list[str], pages: str | None = None, timeout: int | None = None
                ) -> str | None:  # fmt: skip
    """ghostscript pdfwrite of src (or of `pages`, "3-7", of it) into dst. The error text, or None when it worked.
    `args` go last, just before src, as they may end in PostScript (-c ... -f), which needs the output set."""
    res = gs(["-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5", "-dDetectDuplicateImages=true",
              *([f"-sPageList={pages}"] if pages else []), f"-sOutputFile={dst}", *args, str(src)],
             timeout)  # fmt: skip
    return None if res.returncode == 0 and dst.exists() else f"ghostscript failed: {res.stderr.strip()[:200]}"


def page_extra_bytes(pdf: Path) -> dict[int, int]:
    """Roughly what each page adds to the file: the size of the page saved on its own (pdfseparate) less the
    smallest such page, which is mostly what every page shares. Empty when the PDF cannot be split."""
    with tempfile.TemporaryDirectory() as tmp:
        res = subprocess.run(["pdfseparate", str(pdf), f"{tmp}/p%d.pdf"], capture_output=True, check=False)
        if res.returncode != 0:
            return {}
        sizes = {int(f.stem[1:]): f.stat().st_size for f in Path(tmp).glob("p*.pdf")}
    base = min(sizes.values(), default=0)
    return {page: size - base for page, size in sizes.items()}


def harder(decided: str | None) -> bool:
    """Whether a motion decided on `decided` (ISO date) gets the harder, pre-2019 copy. No date: the 2019-on one."""
    return bool(decided) and str(decided)[:10] < HARDER_BEFORE


def condition_span(conditions: list[dict]) -> tuple[int, int] | None:
    """(2019 on) The pages that keep their text: from the first condition's page to two pages after the last
    one's. None when no condition has a page."""
    starts = [c["page"] for c in conditions if c.get("page")]
    return (min(starts), max(starts) + 2) if starts else None


def older_condition_span(conditions: list[dict], texts: list[str]) -> tuple[int, int] | None:
    """(before 2019) The pages that hold conditions: from the first condition's page to the page where the last
    one ends, which is the page among the last one's page and the two after it that has its closing words
    (`texts`, the original's page_texts); two pages after the last one's when they are not found. None when no
    condition has a page."""
    starts = [c["page"] for c in conditions if c.get("page")]
    if not starts:
        return None
    first, last = min(starts), max(starts)
    end = last + 2
    ends = []
    for c in conditions:
        if c.get("page") != last:
            continue
        body = letters(c["text"])
        probes = [probe for probe in (body[-40:], body[-25:]) if len(probe) >= 20]
        ends.append(next((p for probe in probes for p in range(last, min(last + 2, len(texts)) + 1)
                          if probe in texts[p - 1]), None))  # fmt: skip
    if ends and all(ends):
        end = max(e for e in ends if e)
    return first, end


def heavy_pages(pdf: Path, span: tuple[int, int] | None, threshold: int) -> list[int]:
    """Pages to turn into pictures: adding more than `threshold` bytes to `pdf` on their own and outside the
    condition span. None when no condition has a page (span None)."""
    if not span:
        return []
    first, last = span
    return sorted(p for p, extra in page_extra_bytes(pdf).items()
                  if extra > threshold and not first <= p <= last)  # fmt: skip


def pages_to_rasterize(pdf: Path, conditions: list[dict]) -> list[int]:
    """(2019 on) Pages to turn into pictures: heavier than HEAVY_PAGE_BYTES on their own and outside
    condition_span."""
    return heavy_pages(pdf, condition_span(conditions), HEAVY_PAGE_BYTES)


def cached_copy_problems(original: Path, copy: Path, meta: dict, conditions: list[dict]) -> list[str]:
    """Why a cached copy no longer fits the current conditions (empty when it still does). The cache is keyed on
    the original PDF only, but the check and the choice of picture pages depend on the conditions and their
    pages, which a later data build can change: so the copy is checked again (check_pdf) on every build, and a
    picture page inside the current condition span (condition_span, or older_condition_span for a pre-2019 copy)
    counts as a problem."""
    problems = check_pdf(original, copy, conditions)
    older = meta.get("version") == OLDER_PDF_CACHE_VERSION
    span = older_condition_span(conditions, page_texts(original)) if older else condition_span(conditions)
    if span:
        problems += [f"page {p} is a picture but holds conditions" for p in meta.get("pictures", [])
                     if span[0] <= p <= span[1]]  # fmt: skip
    return problems


def rasterize_pages(src: Path, raster: list[int], args: list[str], dst: Path, tmp: Path) -> str | None:
    """(2019 on) dst = src with the pages in `raster` as pictures (RASTER_DPI, JPEG) and every other page through
    pdfwrite with `args`, in the original order (runs of pages joined with pdfunite). The error text, or None."""
    n = page_count(src)
    runs: list[tuple[int, int, bool]] = []
    for p in range(1, n + 1):
        heavy = p in raster
        if runs and runs[-1][2] == heavy and runs[-1][1] == p - 1:
            runs[-1] = (runs[-1][0], p, heavy)
        else:
            runs.append((p, p, heavy))
    parts = []
    for i, (a, b, heavy) in enumerate(runs):
        part = tmp / f"part{i:03d}.pdf"
        if heavy:
            res = gs(["-sDEVICE=pdfimage24", f"-r{RASTER_DPI}", "-sCompression=JPEG", f"-dJPEGQ={RASTER_JPEG_QUALITY}",
                      f"-sPageList={a}-{b}", f"-sOutputFile={part}", str(src)])  # fmt: skip
            if res.returncode != 0 or not part.exists():
                return f"ghostscript (pictures) failed: {res.stderr.strip()[:200]}"
        elif error := gs_pdfwrite(src, part, args, f"{a}-{b}"):
            return error
        parts.append(str(part))
    return unite(parts, dst)


def unite(parts: list[str], dst: Path) -> str | None:
    """dst = the PDFs `parts` one after the other (pdfunite; a copy when there is one). The error text, or None."""
    if len(parts) == 1:
        shutil.copyfile(parts[0], dst)
        return None
    res = subprocess.run(["pdfunite", *parts, str(dst)], capture_output=True, text=True, check=False)
    return None if res.returncode == 0 and dst.exists() else f"pdfunite failed: {res.stderr.strip()[:200]}"


def repeated_fonts(pdf: Path) -> bool:
    """Whether the same font is embedded more than once (pdffonts): what joining runs of pages made apart does."""
    out = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True, check=False).stdout
    names = [line.split()[0].split("+")[-1] for line in out.splitlines()[2:] if line.split()[-5:-4] == ["yes"]]
    return len(names) != len(set(names))


def page_plan(n: int, span: tuple[int, int] | None, pictures: list[int] | None = None,
              whole: bool = False) -> dict[int, str]:  # fmt: skip
    """(before 2019) How each of the n pages is made: "picture" for the pages in `pictures`; "text" inside the
    condition span (every page when there is none, or when `whole`); "rest" for the others."""
    return {p: "picture" if p in (pictures or []) else "text" if whole or not span or span[0] <= p <= span[1]
            else "rest" for p in range(1, n + 1)}  # fmt: skip


def make_copy(src: Path, plan: dict[int, str], setting: dict[str, list[str]], dst: Path, tmp: Path) -> str | None:
    """(before 2019) dst = src with each page made as `plan` says: "picture" pages as grayscale pictures
    (raster_dpi, JPEG), the others through pdfwrite with setting["text"] or setting["rest"], in the original order
    (runs of pages joined with pdfunite). The error text, or None."""
    sizes = page_sizes(src) if "picture" in plan.values() else {}
    modes = {p: f"picture@{raster_dpi(sizes.get(p))}" if mode == "picture" else mode for p, mode in plan.items()}
    runs: list[tuple[int, int, str]] = []
    for p in sorted(modes):
        if runs and runs[-1][2] == modes[p] and runs[-1][1] == p - 1:
            runs[-1] = (runs[-1][0], p, modes[p])
        else:
            runs.append((p, p, modes[p]))
    parts = []
    for i, (a, b, mode) in enumerate(runs):
        part = tmp / f"part{i:03d}.pdf"
        if mode.startswith("picture@"):
            dpi = mode.split("@")[1]
            res = gs(["-sDEVICE=pdfimage8", f"-r{dpi}", "-sCompression=JPEG", f"-dJPEGQ={OLDER_RASTER_JPEG_QUALITY}",
                      f"-sPageList={a}-{b}", f"-sOutputFile={part}", str(src)], GS_TIMEOUT)  # fmt: skip
            if res.returncode != 0 or not part.exists():
                return f"ghostscript (pictures) failed: {res.stderr.strip()[:200]}"
        elif error := gs_pdfwrite(src, part, setting[mode], f"{a}-{b}", GS_TIMEOUT):
            return error
        parts.append(str(part))
    return unite(parts, dst)


class Best:
    """The smallest good copy so far (the original to start with), and why the others were refused."""

    def __init__(self, original: Path, conditions: list[dict], tmp: Path) -> None:
        self.original, self.conditions, self.tmp = original, conditions, tmp
        self.path, self.size, self.how, self.rejected = original, original.stat().st_size, "original", {}

    def consider(self, name: str, candidate: Path) -> bool:
        """Keep `candidate` when check_pdf finds nothing and it is smaller. Whether it was kept."""
        problems = check_pdf(self.original, candidate, self.conditions)
        if problems:
            self.rejected[name] = "; ".join(problems[:5])
        elif candidate.stat().st_size < self.size:
            kept = self.tmp / f"best-{name}.pdf"
            candidate.rename(kept)
            self.path, self.size, self.how = kept, kept.stat().st_size, name
            return True
        return False


def standard_compress(original: Path, conditions: list[dict], tmp: Path) -> tuple[Best, list[int]]:
    """(2019 on, as hosted since 2026-11-12) ghostscript with the gentlest GS_SETTINGS first, harder ones only
    while the copy is over PDF_MAX_BYTES; then, when some pages are plan drawings outside the conditions
    (pages_to_rasterize), the same with those pages as pictures. The best copy and its picture pages."""
    best, best_args = Best(original, conditions, tmp), None
    raster: list[int] = []
    for name, args in GS_SETTINGS.items():
        candidate = tmp / f"{name}.pdf"
        if error := gs_pdfwrite(original, candidate, args):
            best.rejected[name] = error
            continue
        if best.consider(name, candidate):
            best_args = args
        if best.size <= PDF_MAX_BYTES:
            break
    heavy = pages_to_rasterize(best.path, conditions)
    if heavy:
        name = f"{best.how}+pictures"
        candidate, work = tmp / "pictures.pdf", tmp / "parts"
        work.mkdir()
        if error := rasterize_pages(best.path, heavy, best_args or GS_SETTINGS["ebook"], candidate, work):
            best.rejected[name] = error
        elif best.consider(name, candidate):
            raster = heavy
    return best, raster


def older_compress(original: Path, conditions: list[dict], tmp: Path) -> tuple[Best, list[int]]:
    """(before 2019) ghostscript with the gentlest OLDER_GS_SETTINGS first (gentler on the pages in
    older_condition_span than on the rest, or on every page when that comes out smaller), harder ones only while
    the copy is over PDF_MAX_BYTES; pages outside the conditions that weigh more than HUGE_PAGE_BYTES in the
    original are pictures from the start. Then, when some pages outside the conditions are still heavy
    (OLDER_HEAVY_PAGE_BYTES in the copy: plan drawings), the same with those pages as pictures too. The best copy
    and its picture pages."""
    best = Best(original, conditions, tmp)
    span = older_condition_span(conditions, page_texts(original))
    n = page_count(original)
    huge = heavy_pages(original, span, HUGE_PAGE_BYTES)
    best_setting, best_whole, raster = next(iter(OLDER_GS_SETTINGS)), False, huge
    # each setting split in runs of pages ("text" and "rest" made apart, joined with pdfunite) and, when that
    # copy has the same font embedded more than once (each run embeds its own copy), also whole (every page
    # "text", one run): a born-digital motion with big fonts (Japanese, say) can come out smaller whole
    for name, setting in OLDER_GS_SETTINGS.items():
        repeats = False
        for whole in (False, True):
            plan = page_plan(n, span, huge, whole=whole)
            if whole and (not repeats or plan == page_plan(n, span, huge)):
                continue
            label = (f"{name}-whole" if whole else name) + ("+pictures" if huge else "")
            candidate, work = tmp / f"{label}.pdf", tmp / f"parts-{label}"
            work.mkdir()
            if error := make_copy(original, plan, setting, candidate, work):
                best.rejected[label] = error
                continue
            repeats = repeats or repeated_fonts(candidate)
            if best.consider(label, candidate):
                best_setting, best_whole = name, whole
        if best.size <= PDF_MAX_BYTES:
            break
    heavy = sorted(set(huge) | set(heavy_pages(best.path, span, OLDER_HEAVY_PAGE_BYTES)))
    if heavy != huge:
        name = f"{best_setting}{'-whole' if best_whole else ''}+pictures"
        candidate, work = tmp / "pictures.pdf", tmp / "parts-pictures"
        work.mkdir()
        if error := make_copy(original, page_plan(n, span, heavy, whole=best_whole), OLDER_GS_SETTINGS[best_setting],
                              candidate, work):  # fmt: skip
            best.rejected[name] = error
        elif best.consider(name, candidate):
            raster = heavy
    return best, raster if "+pictures" in best.how else []


def compress_pdf(record: str, original: Path, conditions: list[dict], decided: str | None = None
                 ) -> tuple[Path, dict]:  # fmt: skip
    """The smallest good copy of a motion PDF for the public site: older_compress for a motion decided before
    HARDER_BEFORE (`decided`), standard_compress otherwise; the original itself when nothing is smaller. A copy is
    good when check_pdf finds nothing. Cached by the original's sha256 (PDF_CACHE/<record>.pdf and .json, with the
    version of the rules that made it: PDF_CACHE_VERSION, or OLDER_PDF_CACHE_VERSION for a pre-2019 copy); a
    cached copy is used only while cached_copy_problems finds nothing, otherwise it is made again."""
    older = harder(decided)
    version = OLDER_PDF_CACHE_VERSION if older else PDF_CACHE_VERSION
    PDF_CACHE.mkdir(parents=True, exist_ok=True)
    out, meta_path = PDF_CACHE / f"{record}.pdf", PDF_CACHE / f"{record}.json"
    digest = sha256(original)
    remade = False
    if out.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if meta.get("source_sha256") == digest and meta.get("version") == version:
            if not cached_copy_problems(original, out, meta, conditions):
                return out, meta
            remade = True
    with tempfile.TemporaryDirectory() as tmp_dir:
        best, raster = (older_compress if older else standard_compress)(original, conditions, Path(tmp_dir))
        shutil.copyfile(best.path, out)
    meta = {
        "version": version,
        "source_sha256": digest,
        "source_bytes": original.stat().st_size,
        "setting": best.how,
        "bytes": best.size,
        "pages": page_count(out),
        "pictures": raster,
        "rejected": best.rejected,
    }
    meta_path.write_text(json.dumps(meta, indent=1) + "\n")
    return out, {**meta, "remade": remade}


def pdf_name(record: str) -> str:
    """The object name of a motion's copy in the bucket (and the last part of its URL)."""
    return f"{record}.pdf"


def pdf_url(base: str, record: str) -> str:
    """The public URL of a motion's copy: base + <record>.pdf (the record quoted for a URL, though case numbers
    hold only letters, digits, "-" and ".")."""
    return base + quote(pdf_name(record), safe="")


def check_pdf_base_url(base: str) -> str:
    """The base URL the motion links start with: https, ending in "/". Exits on anything else."""
    if not base.startswith("https://") or not base.endswith("/") or "?" in base or "#" in base:
        sys.exit(f"build_public_conditions_site: --pdf-base-url must be an https URL ending in '/': {base!r}")
    return base


def bucket_of(base: str) -> str | None:
    """The folder of a Vercel Blob public base URL ("https://<store>.public.blob.vercel-storage.com/<folder>/"),
    else None. The upload script puts each copy at <folder>/<record>.pdf."""
    m = re.fullmatch(r"https://[a-z0-9]+\.public\.blob\.vercel-storage\.com/([^/]+)/", base)
    return m[1] if m else None


# The files the pages load are named by their content: assets/<name>.<first 12 hex of sha256>.<ext>, and the pages
# load them by that name. A deploy that changes one gives it a new name, so a browser holding an older copy cannot
# use it with a newer page (a returning visitor once saw the old data after a deploy until a hard refresh). The
# pages themselves are served "no-cache" (vercel.json), so a normal reload always checks for the latest.
ASSETS = "assets"
PAGES = ("/", "/index.html", "/coverage.html")
FINGERPRINTED = ("search.js", "coverage.js", "coverage.md", "data/conditions.json")


def fingerprinted_name(rel: str, text: str) -> str:
    """"data/conditions.json" -> "assets/conditions.<hash>.json"."""
    digest = hashlib.sha256(text.encode()).hexdigest()[:12]
    stem, ext = rel.rsplit("/", 1)[-1].rsplit(".", 1)
    return f"{ASSETS}/{stem}.{digest}.{ext}"


def fingerprint(files: dict[str, str]) -> dict[str, str]:
    """`files` with the FINGERPRINTED ones renamed by their content and every page's reference to them rewritten
    ("./search.js", fetch("data/conditions.json")). Exits if a page still names an original file."""
    names = {rel: fingerprinted_name(rel, files[rel]) for rel in FINGERPRINTED}
    out: dict[str, str] = {}
    for rel, text in files.items():
        if rel.endswith(".html"):
            for old, new in names.items():
                text = text.replace(f'"./{old}"', f'"./{new}"').replace(f'"{old}"', f'"{new}"')
            left = [old for old in names if f'"./{old}"' in text or f'"{old}"' in text]
            if left:
                sys.exit(f"build_public_conditions_site: {rel} still loads {left} by its plain name")
        out[names.get(rel, rel)] = text
    return out


def default_manifest(out: Path) -> Path:
    """<out's parent>/sf-conditions-search-pdfs/manifest.json: next to the site folder, never inside it."""
    return out.resolve().parent / MANIFEST_DIR_NAME / "manifest.json"


def stage_pdfs(data: dict, sources: dict[str, str], root: Path | None = None) -> dict[str, dict]:
    """Make (or take from the cache) the small copy of every linked motion PDF, without copying it anywhere: the
    copies stay in PDF_CACHE and are uploaded from there. `sources`: the local PDF of each record, as the local
    data has it ("pdf/<record>.pdf", under `root`, by default SRC; the public data links the bucket instead).
    Returns compress_pdf's meta per record, plus the copy's "path"."""
    root = root or SRC
    by_record: dict[str, list[dict]] = {}
    for c in data["conditions"]:
        if c.get("pdf"):
            by_record.setdefault(c["record"], []).append(c)

    def one(item: tuple[str, list[dict]]) -> tuple[str, dict]:
        record, conds = item
        original = (root / sources[record]).resolve()
        if not original.exists():
            sys.exit(f"build_public_conditions_site: no PDF for {record} ({sources[record]})")
        small, meta = compress_pdf(record, original, conds, conds[0].get("decided"))
        return record, {**meta, "path": small}

    with ThreadPoolExecutor(PDF_WORKERS) as pool:
        return dict(pool.map(one, sorted(by_record.items())))


def pdf_manifest(pdfs: dict[str, dict], base: str) -> dict:
    """What the upload step needs: per record, the object name, the local copy, its bytes and sha256 (of the file
    as it is now, so a cache file changed after the build is caught), and the public URL the site links."""
    files = []
    for record, meta in sorted(pdfs.items()):
        path = Path(meta["path"]).resolve()
        files.append({
            "record": record,
            "name": pdf_name(record),
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "public_url": pdf_url(base, record),
        })  # fmt: skip
    return {
        "public_base_url": base,
        "bucket": bucket_of(base),
        "upload_limit_bytes": UPLOAD_LIMIT_BYTES,
        "count": len(files),
        "total_bytes": sum(f["bytes"] for f in files),
        "files": files,
    }


def strip_comments(js: str) -> str:
    """Drop whole-line // comments and /** ... */ blocks (lines starting with /*, * or */). Code lines are kept."""
    out = []
    for line in js.split("\n"):
        s = line.strip()
        if s.startswith(("//", "/*", "* ", "*/")) or s == "*":
            continue
        out.append(line)
    return "\n".join(out)


def sub(text: str, old: str, new: str, what: str) -> str:
    if old not in text:
        sys.exit(f"build_public_conditions_site: the source changed, cannot find {what!r}: {old[:80]!r}")
    return text.replace(old, new)


# ---- the two front ends ------------------------------------------------------------------------------------------
# "c" (the default since 2026-11-17): the front page of apps/showcase ("the living grid": the stamp gate, the story of
# one motion over the city's street grid, the search beside the map) and its coverage page, built by Vite
# (`vite build --mode site`, see apps/showcase/vite.config.ts) against the public data prepared here. "classic": the
# plain page of tools/conditions-search, byte for byte as it was deployed until then (kept so that the old site can
# be rebuilt and deployed again).
FRONTS = ("c", "classic")
DEFAULT_FRONT = "c"
SHOWCASE = ROOT / "apps" / "showcase"
# The files a C build may hold besides the two pages and vercel.json: Vite's (assets/<name>-<8-char hash>.<ext>) and
# the data files named here by their content (assets/<name>.<12 hex>.<ext>). Anything else stops the build.
C_PAGES = ("index.html", "coverage.html")
C_ASSET = re.compile(r"assets/(?:[\w.-]+-[\w-]{8}\.(?:js|css|woff2|svg)|[\w-]+\.[0-9a-f]{12}\.(?:json|bin|md))")
# Where the C front end opens the motion of a condition that has no page (it would otherwise open at page 1, which
# prints the project sponsor's name and address): the page its conditions begin on, by record.
SECTION_PAGES = SHOWCASE / "src" / "core" / "search" / "section-pages.json"
TEXT_SUFFIXES = (".html", ".js", ".css", ".json", ".md", ".svg", ".txt")
# The C build's own data files beside the search data: the map (its streets and motions) and the coverage text.
C_DATA = {"motions": "json", "sf-streets": "bin", "coverage": "md", "conditions": "json"}
# The snippet of Vercel Web Analytics that comes before ANALYTICS_SCRIPT on both live pages (the queue).
ANALYTICS_QUEUE = 'window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };'


def public_data(source: dict, base: str) -> tuple[dict, dict[str, str]]:
    """The public data (as both front ends publish it) and the local PDF of each record: build notes and the raw
    first readings dropped, private liaison contacts withheld, motion links to the file storage and to Planning's
    copy."""
    data = json.loads(json.dumps(source))
    for k in DROP_TOP_FIELDS:
        data.pop(k, None)
    (data.get("review") or {}).pop("file", None)
    sources = {c["record"]: c["pdf"] for c in data["conditions"] if c.get("pdf")}
    for c in data["conditions"]:
        if c.get("pdf"):
            # the copy in the site's file storage (local data: "pdf/<record>.pdf"); the page adds #page=N
            c["pdf"] = pdf_url(base, c["record"])
        c["motion_url"] = public_pdf(c.get("motion_url"))  # the second, smaller link: Planning's own copy
        # a private liaison's name and contact details: "[contact in the motion]" (the PDF link stays)
        for field in ("text", "raw_text"):
            if c.get(field):
                c[field] = withhold_private_contacts(c[field])
        for k in DROP_CONDITION_FIELDS:
            c.pop(k, None)
    return data, sources


def data_text(data: dict) -> str:
    """The data file as published: compact JSON, one line, UTF-8 (the same bytes from either front end)."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"


def public_coverage_md(data: dict) -> str:
    """The coverage text both front ends publish: public/coverage.md, then "Text quality" and the list of motions
    left out, built from the data."""
    left_out = "\n".join(
        f"- {m['record']}, {m['address']}: {m.get('what') or 'not food or drink'}"
        + (" (removed by the hand review)" if m.get("left_out_by") == "review" else "")
        for m in data["removed_motions"]
    )
    review = data.get("review") or {}
    by_review = sum(m.get("left_out_by") == "review" for m in data["removed_motions"])
    return (SRC / "public" / "coverage.md").read_text().rstrip() + (
        "\n\n## Text quality\n\nOlder motions are scanned. Each condition was checked for pieces that do not read "
        "(stray symbols, letters mixed with digits, page footers left in). Page furniture was removed; a condition "
        "that still read badly was read again from the PDF's text layer or by OCR, and the second reading was used "
        "only when it was the same text, read better. Conditions that still could not be read cleanly are marked "
        "and link to the motion page.\n"
        "\n## Motions left out: not food or drink\n\n"
        f"These {len(data['removed_motions'])} motions are not about a food, drink or entertainment premises, so "
        f"they are not on the search page: {len(data['removed_motions']) - by_review} left out by the classifier "
        f"and {by_review} removed by the hand review"
        + (f" (the review also added back {len(review.get('added_back', []))} the classifier had left out)"
           if review.get("added_back") else "")
        + ". The reviewed list above gives the reason for each change the review made.\n\n"
        + left_out
        + "\n"
    )


# The Content-Security-Policy of the site, the same for both front ends (the C front end needs nothing more: its
# scripts, styles, fonts and data are all the site's own files, its WebGL and canvas drawing need no directive,
# its only inline script is the theme set before the first paint, beside the analytics queue that needed
# 'unsafe-inline' already, and its styles are set through element.style, which 'unsafe-inline' in style-src already
# allowed). The motion PDFs are in the bucket, opened by plain links, which the CSP does not restrict; Vercel Web
# Analytics is same-origin (/_vercel/insights/script.js and its requests: script-src and connect-src 'self'); its
# queue is inline ('unsafe-inline'); mailto: links are not restricted by the CSP.
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")  # fmt: skip


def vercel_json() -> str:
    """vercel.json: the pages no-cache, the content-named files immutable, the security headers and the CSP."""
    security = [
        {"key": "X-Content-Type-Options", "value": "nosniff"},
        {"key": "Referrer-Policy", "value": "strict-origin-when-cross-origin"},
    ]
    return json.dumps(
        {
            "cleanUrls": False,
            "headers": [
                # the pages are checked with the server on every load, so a normal reload always gets the
                # latest deploy; the files they load are named by their content (see fingerprint)
                *(
                    {"source": page, "headers": [{"key": "Cache-Control", "value": "no-cache"}]}
                    for page in PAGES
                ),
                {
                    # scripts, styles, fonts, data and the coverage text: a new deploy that changes one gives it a
                    # new name
                    "source": f"/{ASSETS}/(.*)",
                    "headers": [{"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}],
                },
                {
                    # every file (see CSP)
                    "source": "/(.*)",
                    "headers": [
                        *security,
                        {"key": "X-Frame-Options", "value": "DENY"},
                        {"key": "Content-Security-Policy", "value": CSP},
                    ],
                },
            ],
        },
        indent=2,
    ) + "\n"


def classic_files(data: dict, coverage_md: str) -> dict[str, str]:
    """The classic front end's files (before fingerprinting): tools/conditions-search's two pages, rewritten for the
    public, its two scripts without comments, the coverage text, the data and vercel.json."""
    index = (SRC / "index.html").read_text()
    index = sub(
        index,
        "<title>Conditions of Approval</title>",
        f"<title>{NAME}</title>\n<meta name=\"description\" content=\"Search the conditions of approval San Francisco's "
        "Planning Commission set for restaurants, bars and entertainment venues.\">",
        "title",
    )
    index = sub(index, "<h1>Conditions of approval</h1>", f"<h1>{NAME}</h1>", "heading")
    index = sub(
        index,
        "Page links open the local copy of the motion at the page where the condition starts.",
        "Page links open a copy of the adopted motion, stored with this site's files, at the page where the "
        "condition starts. The smaller link goes to Planning's own copy, which downloads the PDF instead of opening "
        "it at the page.",
        "page-link sentence",
    )
    index = sub(
        index,
        '"Could not load data/conditions.json: run scripts/validation/build_conditions_index.py first."',
        '"Could not load the data. Please reload the page."',
        "load error",
    )
    contact = (
        '<p class="contact" style="max-width:1100px;margin:0 auto;padding:0 16px 40px;color:var(--muted);'
        'font-size:12px">'
        + (f'Questions or corrections: <a href="mailto:{CONTACT}">{CONTACT}</a>. ' if CONTACT else "")
        + "Built from public San Francisco Planning records. Not legal advice. "
        "Page views are counted by Vercel Web Analytics, without cookies.</p>"
    )
    index = sub(index, '<footer id="footer"></footer>', f'<footer id="footer"></footer>\n{contact}', "footer")
    index = sub(index, FEEDBACK_TO, f"const FEEDBACK_TO = {json.dumps(CONTACT)};", "feedback address")

    coverage_html = (SRC / "coverage.html").read_text()
    coverage_html = sub(coverage_html, 'fetch("README.md")', 'fetch("coverage.md")', "detail fetch")
    coverage_html = re.sub(r"\s*\+ `<p class=\"note\">From <code>[^<]*</code>\.</p>`", "", coverage_html)
    coverage_html = coverage_html.replace(
        "Could not load data/conditions.json: run scripts/validation/build_conditions_index.py first.",
        "Could not load the data. Please reload the page.",
    )
    coverage_html = coverage_html.replace('"Could not load README.md."', '"Could not load the coverage detail."')
    coverage_html = coverage_html.replace("The README has no Coverage section.", "The coverage detail is missing.")
    coverage_html = re.sub(r"<title>[^<]*</title>", f"<title>Coverage · {NAME}</title>", coverage_html, count=1)
    coverage_html = re.sub(r"Worked out from (<code>)?data/conditions\.json(</code>)? as this page loads\.",
                           "Worked out from the data as this page loads.", coverage_html)
    coverage_html = coverage_html.replace("Worked out from data/conditions.json as this page loads.",
                                          "Worked out from the data as this page loads.")
    coverage_html = re.sub(r"// The README's Coverage section.*?\n(?://.*\n)*", "", coverage_html)

    files = {
        "index.html": index,
        "coverage.html": coverage_html,
        "coverage.md": coverage_md,
        "search.js": strip_comments((SRC / "search.js").read_text()),
        "coverage.js": strip_comments((SRC / "coverage.js").read_text()),
        "data/conditions.json": data_text(data),
        "vercel.json": vercel_json(),
    }
    files = fingerprint(files)
    for page in ("index.html", "coverage.html"):
        if files[page].count(ANALYTICS_SCRIPT) != 1:
            sys.exit(f"build_public_conditions_site: {page} must load the analytics script once: {ANALYTICS_SCRIPT}")
    return files


def vite_site(data: str, coverage_md: str, base: str = PDF_BASE_URL) -> dict[str, bytes]:
    """The C front end: `vite build --mode site` of apps/showcase against this build's public data and coverage text
    (in a temporary folder), with CONTACT as the site's contact address (none when it is empty: no contact line and
    no card link) and `base` as the store the story's own motion links point at. Every file it wrote, by its path."""
    pnpm = shutil.which("pnpm")
    if not pnpm:
        sys.exit("build_public_conditions_site: --front c needs pnpm (and `pnpm install` in the repo)")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        (tmp / "conditions.json").write_bytes(data.encode("utf-8"))
        (tmp / "coverage.md").write_bytes(coverage_md.encode("utf-8"))
        site = tmp / "site"
        env = {k: v for k, v in os.environ.items() if not k.startswith("SHOWCASE_")}
        env.update({
            "SHOWCASE_DATA": str(tmp / "conditions.json"),
            "SHOWCASE_COVERAGE_MD": str(tmp / "coverage.md"),
            "SHOWCASE_CONTACT": CONTACT,
            "SHOWCASE_PDF_BASE": base,
        })  # fmt: skip
        res = subprocess.run(
            [pnpm, "--dir", str(SHOWCASE), "exec", "vite", "build", "--mode", "site", "--outDir", str(site),
             "--emptyOutDir", "--logLevel", "warn"],
            env=env, capture_output=True, text=True, check=False,
        )  # fmt: skip
        if res.returncode != 0:
            sys.exit(f"build_public_conditions_site: the Vite site build failed:\n{res.stdout[-2000:]}\n{res.stderr[-2000:]}")
        return {p.relative_to(site).as_posix(): p.read_bytes() for p in sorted(site.rglob("*")) if p.is_file()}


def c_files(data: dict, coverage_md: str, base: str = PDF_BASE_URL) -> dict[str, bytes]:
    """The C front end's files: the Vite site build and vercel.json. The data and the coverage text in it must be
    this build's own, byte for byte, under the names the classic build gives them."""
    text = data_text(data)
    files = vite_site(text, coverage_md, base)
    for rel, body in (("data/conditions.json", text), ("coverage.md", coverage_md)):
        name = fingerprinted_name(rel, body)
        if files.get(name) != body.encode("utf-8"):
            sys.exit(f"build_public_conditions_site: the C build does not carry {rel} as {name}, byte for byte")
    if "vercel.json" in files:
        sys.exit("build_public_conditions_site: the Vite site build wrote a vercel.json of its own")
    files["vercel.json"] = vercel_json().encode("utf-8")
    return files


# ---- the guards ----------------------------------------------------------------------------------------------------
PRIVATE_CONTACTS = Path(__file__).resolve().parent / "private_contacts.py"
DATA_REL = "tools/conditions-search/data/conditions.json"


def withheld_strings(source: dict) -> tuple[list[str], str]:
    """The private contact strings the published data must never hold (private_contact_strings): those still in the
    local data (every text field, before withholding), in story.json, and in the data as it was before the
    withholding began (the version of DATA_REL before the commit that added private_contacts.py, read from git
    when the history has it; the strings are only held in memory). A history that starts with the withholding in
    place (a fresh clone of this repository, or a shallow one) has no such version: that source is skipped and the
    others are used. Also says where they were read from."""
    texts = [c.get(f) for c in source["conditions"] for f in ("text", "raw_text", "text_display")]
    story = SHOWCASE / "src" / "data" / "story.json"
    if story.exists():
        texts += [c.get(f) for c in json.loads(story.read_text())["conditions"] for f in ("text", "text_display")]
    note = "the local data and story.json"
    try:
        first = subprocess.run(["git", "-C", str(ROOT), "log", "--diff-filter=A", "--format=%H", "--",
                                str(PRIVATE_CONTACTS.relative_to(ROOT))],
                               capture_output=True, text=True, check=True).stdout.split()  # fmt: skip
        parent = f"{first[-1]}^" if first else ""
        if parent and subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "--quiet", parent + "^{commit}"],
                                     capture_output=True, check=False).returncode == 0:  # fmt: skip
            old = subprocess.run(["git", "-C", str(ROOT), "show", f"{parent}:{DATA_REL}"], capture_output=True,
                                 check=True).stdout  # fmt: skip
            texts += [c.get(f) for c in json.loads(old)["conditions"] for f in ("text", "raw_text")]
            note += f", and the data before the withholding (git {first[-1][:7]}^)"
        else:
            note += " (the history here starts after the withholding: the data before it was not read)"
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        note += " (no git history here: the data before the withholding was not read)"
    found = sorted({s for t in texts for s in private_contact_strings(t) if len(s.strip()) >= 4})
    return found, note


CHECK_LINKS = SHOWCASE / "tools" / "check-links.mjs"
# a long list of conditions read with their pages, beside every motion read with none
CHECK_LINKS_ALSO = ("#q=noise&kind=all",)


def check_links(files: dict[str, bytes], hashes: list[str]) -> list[str]:
    """Open the built C site (`files`, written to a temporary folder) in a headless browser at each URL hash and
    read every link on its cards, and the subject and body of every feedback e-mail: what would open a motion PDF
    without a page of 2 or more (page 1 prints the sponsor's name and address). A check that cannot run is a
    problem too (node, Playwright or its Chromium missing)."""
    node = shutil.which("node")
    if not node:
        return ["the links could not be checked in a browser: no node"]
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        for rel, body in files.items():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / rel).write_bytes(body)
        try:
            res = subprocess.run([node, str(CHECK_LINKS), str(tmp), *hashes], cwd=SHOWCASE, capture_output=True,
                                 text=True, check=False, timeout=600)  # fmt: skip
        except subprocess.TimeoutExpired:
            return ["the links could not be checked in a browser: it took over 10 minutes"]
    try:
        return list(json.loads(res.stdout.strip().splitlines()[-1])["problems"]) if res.returncode == 0 else [
            f"the links could not be checked in a browser: {(res.stderr or res.stdout).strip()[-400:]}"]
    except (IndexError, KeyError, ValueError):
        return [f"the links could not be checked in a browser: {(res.stderr or res.stdout).strip()[-400:]}"]


def check_site(files: dict[str, bytes], data: dict, base: str, front: str, withheld: list[str],
               browse: bool = False) -> list[str]:  # fmt: skip
    """What is wrong with a site about to be written (empty when nothing is). Every text file is read: the pages,
    the scripts and styles (also Vite's bundles), the data, the coverage text. With `browse` (the C build), the site
    is also opened in a browser and the links its cards write are read (check_links)."""
    problems = []
    texts: dict[str, str] = {}
    for rel, body in files.items():
        if rel.endswith(".map"):
            problems.append(f"{rel}: a source map")
        if rel.endswith(TEXT_SUFFIXES):
            try:
                texts[rel] = body.decode("utf-8")
            except UnicodeDecodeError:
                problems.append(f"{rel}: not UTF-8 text")
    if front == "c":
        unexpected = [rel for rel in files if rel not in (*C_PAGES, "vercel.json") and not C_ASSET.fullmatch(rel)]
        problems += [f"{rel}: not a file the site is made of" for rel in unexpected]
        for rel in files:
            m = re.fullmatch(r"assets/([\w-]+)\.([0-9a-f]{12})\.(\w+)", rel)
            if m and hashlib.sha256(files[rel]).hexdigest()[:12] != m[2]:
                problems.append(f"{rel}: its name is not its content's")
        for stem, ext in C_DATA.items():
            if not [rel for rel in files if re.fullmatch(rf"assets/{stem}\.[0-9a-f]{{12}}\.{ext}", rel)]:
                problems.append(f"no assets/{stem}.<hash>.{ext}")
    # the product name and internal names
    for rel, text in texts.items():
        for m in FORBIDDEN.finditer(text):
            problems.append(f"{rel}: internal names left in the public site: {text[max(0, m.start() - 40) : m.end() + 40]!r}")
    # Vercel Web Analytics on both pages, once each (its queue, then its script)
    for page in ("index.html", "coverage.html"):
        html = texts.get(page, "")
        if html.count(ANALYTICS_SCRIPT) != 1 or html.count(ANALYTICS_QUEUE) != 1:
            problems.append(f"{page}: must load the analytics queue and script once each")
        elif not html.index(ANALYTICS_QUEUE) < html.index(ANALYTICS_SCRIPT) < html.index("</head>"):
            problems.append(f"{page}: the analytics snippet is not in the head, queue first")
    # no raw first readings: not in the data, not as a key anywhere
    for rel, text in texts.items():
        if '"raw_text"' in text:
            problems.append(f"{rel}: holds a raw_text field")
    if any("raw_text" in c for c in data["conditions"]):
        problems.append("the data still holds raw_text")
    # never a link to page 1 of a motion (it prints private names and addresses)
    for rel, text in texts.items():
        for m in re.finditer(r"#page=1(?!\d)", text):
            problems.append(f"{rel}: a link to page 1: {text[max(0, m.start() - 60) : m.end()]!r}")
    page_one = [f"{c['record']} #{c['number']}" for c in data["conditions"] if c.get("pdf") and c.get("page") == 1]
    problems += [f"a condition linked to page 1: {x}" for x in page_one]
    if front == "c":
        # a condition with no page would open its motion at page 1: the front end needs where its conditions begin
        sections = json.loads(SECTION_PAGES.read_text())["pages"] if SECTION_PAGES.exists() else {}
        pageless = sorted({c["record"] for c in data["conditions"] if c.get("pdf") and not c.get("page")})
        for record in pageless:
            page = (sections.get(record) or {}).get("page")
            if not isinstance(page, int) or page < 2:
                problems.append(f"{record}: conditions with no page and no section page in {SECTION_PAGES.name} (they would open page 1)")
        # the links the page writes as it runs (a card's motion link, its feedback e-mail), read in a browser
        if browse:
            hashes = [f"#{urlencode({'q': record, 'kind': 'all'})}" for record in pageless]
            problems += check_links(files, [*hashes, *CHECK_LINKS_ALSO])
    # no private contact: none of the withheld strings, no phone that is not the City's, no e-mail that is not the
    # City's or CONTACT, in any file; and the published conditions pass through the withholding unchanged
    for rel, text in texts.items():
        low = text.lower()
        problems += [f"{rel}: a withheld private contact ({len(s)} characters)" for s in withheld if s.lower() in low]
        for m in PHONE.finditer(text):
            digits = re.sub(r"\D", "", m.group(0))
            if digits not in CITY_PHONES and not digits.startswith(CITY_PHONE_PREFIXES):
                problems.append(f"{rel}: a phone number that is not the City's ({len(digits)} digits)")
        for m in EMAIL.finditer(text):
            if m.group(0) != CONTACT and not CITY_EMAIL_DOMAINS.search(m.group(0)):
                problems.append(f"{rel}: an e-mail address that is not the City's or the contact address")
    for c in data["conditions"]:
        if withhold_private_contacts(c.get("text")) != c.get("text"):
            problems.append(f"{c['record']} #{c['number']}: a private contact in the published text")
    # every motion link under the file storage
    off_base = sorted({c["record"] for c in data["conditions"] if c.get("pdf") and not c["pdf"].startswith(base)})
    if off_base:
        problems.append(f"motion links not under {base}: {off_base[:10]}")
    return problems


def build(out: Path, pdf_base_url: str = PDF_BASE_URL, manifest: Path | None = None, front: str = "classic",
          pdf_root: Path | None = None) -> dict:  # fmt: skip
    """Build the site into `out` with the `front` end ("c" or "classic"; the command line's default is "c", this
    function's "classic", which its older tests call without saying), stage the motion PDFs (from `pdf_root`, by
    default tools/conditions-search: their "pdf/<record>.pdf") and write the PDF manifest. Stops (SystemExit) on any
    guard (check_site) before a file is written."""
    if front not in FRONTS:
        sys.exit(f"build_public_conditions_site: --front must be one of {FRONTS}: {front!r}")
    base = check_pdf_base_url(pdf_base_url)
    manifest = (manifest or default_manifest(out)).resolve()
    if manifest.is_relative_to(out.resolve()):
        sys.exit(f"build_public_conditions_site: the PDF manifest must be outside the site folder: {manifest}")
    source = json.loads((SRC / "data" / "conditions.json").read_text())
    data, sources = public_data(source, base)
    coverage_md = public_coverage_md(data)

    if front == "classic":
        files = {rel: text.encode() for rel, text in classic_files(data, coverage_md).items()}
    else:
        files = c_files(data, coverage_md, base)
    withheld, withheld_from = withheld_strings(source)
    problems = check_site(files, data, base, front, withheld, browse=front == "c")
    if problems:
        sys.exit("build_public_conditions_site: the site was not written:\n" + "\n".join(problems[:40]))

    if out.exists():
        keep = out / ".vercel"
        for p in out.iterdir():
            if p != keep:
                shutil.rmtree(p) if p.is_dir() else p.unlink()
    for rel, body in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(body)
    pdfs = stage_pdfs(data, sources) if pdf_root is None else stage_pdfs(data, sources, pdf_root)
    listed = pdf_manifest(pdfs, base)
    too_big = [f["record"] for f in listed["files"] if f["bytes"] > UPLOAD_LIMIT_BYTES]
    if too_big:
        sys.exit(f"build_public_conditions_site: over the {UPLOAD_LIMIT_BYTES / 2**20:.0f} MB per-file upload limit"
                 f" of the file storage: {too_big}")  # fmt: skip
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(listed, indent=1) + "\n")
    sizes = sorted(m["bytes"] for m in pdfs.values())
    data_name = fingerprinted_name("data/conditions.json", data_text(data))
    return {
        "front": front,
        "conditions": len(data["conditions"]),
        "files": len(files),
        "site_bytes": sum(len(b) for b in files.values()),
        "data_file": data_name,
        "data_sha256": hashlib.sha256(files[data_name]).hexdigest(),
        "withheld": len(withheld),
        "withheld_from": withheld_from,
        "manifest": str(manifest),
        "pdfs": len(pdfs),
        "pdf_bytes": sum(sizes),
        "pdf_source_bytes": sum(m["source_bytes"] for m in pdfs.values()),
        "pdf_largest": sizes[-1] if sizes else 0,
        "pdf_older": sum(m["version"] == OLDER_PDF_CACHE_VERSION for m in pdfs.values()),
        "pdf_older_bytes": sum(m["bytes"] for m in pdfs.values() if m["version"] == OLDER_PDF_CACHE_VERSION),
        "pdf_remade": sorted(r for r, m in pdfs.items() if m.get("remade")),
        "pdf_over_max": [r for r, m in pdfs.items() if m["bytes"] > PDF_MAX_BYTES],
        "pdf_settings": dict(sorted({m["setting"]: sum(x["setting"] == m["setting"] for x in pdfs.values())
                                     for m in pdfs.values()}.items())),
        "pdf_rejected": {r: m["rejected"] for r, m in pdfs.items() if m["rejected"]},
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--pdf-base-url", default=PDF_BASE_URL,
                   help=f"where the motion links point, ending in '/' (default {PDF_BASE_URL})")  # fmt: skip
    p.add_argument("--manifest", type=Path, default=None,
                   help=f"the PDF manifest for the upload step (default <out's parent>/{MANIFEST_DIR_NAME}/manifest.json)")
    p.add_argument("--front", choices=FRONTS, default=DEFAULT_FRONT,
                   help="the front end: c (the living grid, apps/showcase; default) or classic (the plain page, as "
                        "deployed until 2026-11-17)")  # fmt: skip
    p.add_argument("--pdf-root", type=Path, default=None,
                   help="the folder the local data's pdf/<record>.pdf paths are under (default tools/conditions-search;"
                        " a git worktree has no pdf/ of its own: pass the main checkout's)")  # fmt: skip
    args = p.parse_args()
    counts = build(args.out, args.pdf_base_url, args.manifest, args.front, args.pdf_root)
    print(f"{NAME} ({counts['front']} front end): {counts['conditions']} conditions, {counts['files']} files, "
          f"{counts['site_bytes'] / 1e6:.2f} MB in {args.out} (no PDFs)")
    print(f"data: {counts['data_file']} sha256 {counts['data_sha256']}")
    print(f"private contacts checked absent: {counts['withheld']} strings, from {counts['withheld_from']}")
    print(f"motion PDFs for the file storage ({args.pdf_base_url}): manifest {counts['manifest']}")
    print(f"motion PDFs: {counts['pdfs']}, {counts['pdf_bytes'] / 1e6:.0f} MB (from {counts['pdf_source_bytes'] / 1e6:.0f}"
          f" MB), largest {counts['pdf_largest'] / 1e6:.1f} MB; settings used {counts['pdf_settings']}")  # fmt: skip
    print(f"  decided before 2019 (harder copies): {counts['pdf_older']}, {counts['pdf_older_bytes'] / 1e6:.0f} MB")
    if counts["pdf_bytes"] > PDF_TOTAL_TARGET_BYTES:
        print(f"WARNING: the motion PDFs come to {counts['pdf_bytes'] / 1e6:.1f} MB, over the "
              f"{PDF_TOTAL_TARGET_BYTES / 1e6:.0f} MB target (pre-2019 knobs: OLDER_GS_SETTINGS, "
              "OLDER_HEAVY_PAGE_BYTES)")  # fmt: skip
    if counts["pdf_remade"]:
        print(f"cached copies made again (no longer fit the conditions): {counts['pdf_remade']}")
    if counts["pdf_over_max"]:
        print(f"over {PDF_MAX_BYTES / 1e6:.0f} MB even at the hardest setting: {counts['pdf_over_max']}")
    for record, why in counts["pdf_rejected"].items():
        print(f"  {record}: settings refused: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
