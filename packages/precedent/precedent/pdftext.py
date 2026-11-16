"""PDF → text helpers for hearing documents (Planning Commission motions and minutes).

`extract_text` never raises: a scanned (image-only), encrypted or corrupt PDF returns "" and the caller
marks the extraction confidence "low". `find_sections` locates the blocks a motion / minutes document is
organised around (DECISION, FINDINGS, CONDITIONS OF APPROVAL, PUBLIC COMMENT / SPEAKERS, ...).
"""

from __future__ import annotations

import io
import logging
import re
import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

log = logging.getLogger(__name__)

PAGE_BREAK = "\n\f\n"

# Below this many letters a document is treated as having no usable text layer (scanned / image-only).
MIN_TEXT_LETTERS = 200


@dataclass(frozen=True)
class PdfText:
    text: str
    pages: int  # total pages in the document (not just the ones extracted)


def read_pdf(
    pdf_bytes: bytes, max_pages: int | None = None, stop: Callable[[int, str], bool] | None = None
) -> PdfText:
    """Text of the first `max_pages` pages (all when None) plus the document's page count.

    `stop(index, page_text)` returning True drops that page and ends extraction (e.g. at the first plan
    sheet appended to a motion — drawing pages are the slowest to extract and carry no decision text).
    Pages are joined with PAGE_BREAK. Any pypdf failure yields empty text rather than an exception.
    """
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            reader.decrypt("")
        n_pages = len(reader.pages)
    except Exception as exc:  # corrupt / truncated / not a PDF
        log.warning("unreadable PDF (%s): %s", type(exc).__name__, exc)
        return PdfText(text="", pages=0)
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        if max_pages is not None and i >= max_pages:
            break
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:  # one bad page must not lose the rest
            log.warning("page %d text extraction failed (%s)", i + 1, type(exc).__name__)
            page_text = ""
        if stop is not None and stop(i, page_text):
            break
        parts.append(page_text)
    text = PAGE_BREAK.join(parts)
    if sum(ch.isalpha() for ch in text) < MIN_TEXT_LETTERS:
        return PdfText(text="", pages=n_pages)
    return PdfText(text=text, pages=n_pages)


def read_pdf_poppler(
    pdf_path: Path, max_pages: int | None = None, stop: Callable[[int, str], bool] | None = None
) -> PdfText:
    """read_pdf through poppler's pdftotext (reading order, no layout) instead of pypdf: a second reader for a
    motion whose pypdf text ends early (2011.0026C: pypdf stops at page 9, pdftotext reads Exhibit A on page 12).
    Same contract: pages joined with PAGE_BREAK, `stop` drops a page and ends the reading, "" when there is no
    usable text or pdftotext is missing or fails. `pages` counts the pages read, not the document's."""
    args = ["pdftotext", "-enc", "UTF-8", *(["-l", str(max_pages)] if max_pages else []), str(pdf_path), "-"]
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=120, check=False).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("pdftotext failed (%s)", type(exc).__name__)
        return PdfText(text="", pages=0)
    pages = out.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()  # pdftotext ends every page, the last one included, with a form feed
    parts: list[str] = []
    for i, page_text in enumerate(pages):
        if stop is not None and stop(i, page_text):
            break
        parts.append(page_text)
    text = PAGE_BREAK.join(parts)
    if sum(ch.isalpha() for ch in text) < MIN_TEXT_LETTERS:
        return PdfText(text="", pages=len(pages))
    return PdfText(text=text, pages=len(pages))


def extract_text(pdf_bytes: bytes, max_pages: int | None = None) -> str:
    """Plain text of a PDF; "" when it has no usable text layer (scanned) or cannot be read."""
    return read_pdf(pdf_bytes, max_pages=max_pages).text


# ---- cleanup ------------------------------------------------------------------------------------

_HEADERISH = re.compile(
    r"(motion\s+no\.?|record\s+no\.?|resolution\s+no\.?|meeting minutes|page \d+ of \d+|www\.|for information about compliance"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2}, \d{4})",
    re.I,
)
_PAGE_NUMBER = re.compile(r"^\s*(?:page\s+)?\d{1,3}\s*$", re.I)
# structural lines that legitimately repeat (votes, speaker lists, actions) and must never be dropped
_KEEP = re.compile(
    r"^\s*(?:[+=\-]\s|(?:ayes|nays|absent|recused|excused|speakers|action|motion|adopted|resolution)\s*:)",
    re.I,
)


def _norm_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip().lower()


def strip_running_headers(text: str) -> str:
    """Drop page numbers and running headers / footers that repeat across pages.

    A line is dropped when it is a bare page number, appears on 3+ pages, or appears on 2+ pages and
    looks like a header (motion / record number, a date, a compliance-contact footer).
    """
    if not text:
        return text
    pages = text.split("\f")
    seen: Counter[str] = Counter()
    for page in pages:
        for key in {_norm_line(ln) for ln in page.splitlines() if ln.strip()}:
            seen[key] += 1
    out: list[str] = []
    for line in text.splitlines():
        key = _norm_line(line)
        if not key:
            out.append("")
            continue
        if _PAGE_NUMBER.match(line):
            continue
        if _KEEP.match(line):
            out.append(line.rstrip())
            continue
        n = seen[key]
        if n >= 3 or (n >= 2 and _HEADERISH.search(key)):
            continue
        out.append(line.rstrip())
    return "\n".join(out)


def squash(text: str) -> str:
    """Collapse whitespace (including line breaks) to single spaces."""
    return re.sub(r"\s+", " ", text or "").strip()


# ---- sections -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionSpec:
    name: str
    start: re.Pattern[str]
    end: re.Pattern[str] | None = None  # section-specific terminator (searched after the heading)
    max_chars: int = 20000


_ML = re.I | re.M

SECTION_SPECS: tuple[SectionSpec, ...] = (
    SectionSpec(
        "project_description",
        re.compile(r"^[ \t]*(?:\d{1,2}\.[ \t]*)?project description\b\.?[ \t]*:?", _ML),
        re.compile(
            r"^[ \t]*(?:\d{1,2}\.[ \t]+[A-Z]|required commission action|environmental review|decision\s*$)",
            _ML,
        ),
        3000,
    ),
    SectionSpec("findings", re.compile(r"^[ \t]*findings[ \t]*$", _ML)),
    SectionSpec(
        "public_comment",
        re.compile(
            r"^[ \t]*(?:\d{1,2}\.[ \t]*)?(?:public (?:outreach and )?comments?\b|number and nature of public comments?|public comment/community outreach)",
            _ML,
        ),
        re.compile(
            r"^[ \t]*(?:\d{1,2}\.[ \t]+[A-Z]|outreach\s*$|generalized basis|[A-Z]\.[ \t]+at the request)", _ML
        ),
        4000,
    ),
    SectionSpec(
        "decision",
        re.compile(r"^[ \t]*decision[ \t]*$", _ML),
        re.compile(r"^[ \t]*(?:appeal and effective date|protest of fee|additional information)", _ML),
        4000,
    ),
    SectionSpec("vote", re.compile(r"^[ \t]*I hereby certify that the Planning Commission", _ML), None, 1500),
    SectionSpec(
        "exhibit_a",
        re.compile(r"^[ \t]*exhibit a[ \t]*$", _ML),
        re.compile(r"^[ \t]*exhibit b[ \t]*$", _ML),
        60000,
    ),
    SectionSpec(
        "conditions",
        re.compile(
            r"^[ \t]*conditions of approval(?:,?[ \t]*compliance,?(?:[ \t]*monitoring,?[ \t]*and[ \t]*reporting)?)?[ \t]*,?[ \t]*$",
            _ML,
        ),
        re.compile(r"^[ \t]*exhibit b[ \t]*$", _ML),
        60000,
    ),
    SectionSpec(
        "speakers", re.compile(r"^[ \t]*speakers:", _ML), re.compile(r"^[ \t]*(?:action|motion):", _ML), 6000
    ),
)


def find_sections(text: str, specs: tuple[SectionSpec, ...] = SECTION_SPECS) -> dict[str, str]:
    """Locate named blocks in a hearing document. Returns {name: body text} for the headings found.

    A section runs from the end of its (first) heading to the earliest of: its own terminator, the next
    heading of a *different* section, or `max_chars`. Headings that only appear inline in prose (e.g.
    'conditions contained in the attached "EXHIBIT A"') are ignored because headings are line-anchored.
    "conditions" falls back to "exhibit_a" when no explicit Conditions of Approval heading exists.
    """
    if not text:
        return {}
    starts: list[tuple[int, int, SectionSpec]] = []
    for spec in specs:
        m = spec.start.search(text)
        if m:
            starts.append((m.start(), m.end(), spec))
    starts.sort(key=lambda t: t[0])
    out: dict[str, str] = {}
    for i, (_, body_start, spec) in enumerate(starts):
        limit = min(len(text), body_start + spec.max_chars)
        # containers (exhibit_a ⊃ conditions, findings ⊃ public_comment/project_description) are not cut
        # short by the headings nested inside them
        nested = {"exhibit_a": {"conditions"}, "findings": {"public_comment", "project_description"}}.get(
            spec.name, set()
        )
        for start, _, other in starts[i + 1 :]:
            if other.name != spec.name and other.name not in nested and start > body_start:
                limit = min(limit, start)
                break
        if spec.end is not None:
            m = spec.end.search(text, body_start, limit)
            if m:
                limit = m.start()
        body = text[body_start:limit].strip()
        if body:
            out[spec.name] = body
    if "conditions" not in out and "exhibit_a" in out:
        out["conditions"] = out["exhibit_a"]
    if "conditions" not in out and specs is SECTION_SPECS and _CONDITIONS_LOOSE.start.search(text):
        # an OCR'd motion whose "EXHIBIT A" heading is garbled and whose conditions heading carries a stray mark
        # ("Conditions of Approval, Compliance, Monitoring, and Reporting —"); only tried when nothing else was found
        return find_sections(text, _SPECS_LOOSE)
    return out


_CONDITIONS_LOOSE = SectionSpec(
    "conditions",
    re.compile(
        r"^[ \t]*conditions of approval,?[ \t]*compliance,?[ \t]*monitoring,?[ \t]*and[ \t]*reporting[ \t]*[^\w\n]{0,6}[ \t]*$",
        _ML,
    ),
    re.compile(r"^[ \t]*exhibit b[ \t]*$", _ML),
    60000,
)
_SPECS_LOOSE = tuple(_CONDITIONS_LOOSE if s.name == "conditions" else s for s in SECTION_SPECS)
