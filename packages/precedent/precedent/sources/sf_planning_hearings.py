"""San Francisco Planning Commission decisions for Conditional Use Authorization (CUA) cases, from PDFs.

This source ENRICHES the Planning dataset rows (`datasf_planning:<record number>`): it emits Applications
with the *same id* (source="sf_planning_hearings", source_url/extra["motion_url"] = the decision PDF) so the
store's upsert fills conditions, opposition, decision summary and extraction confidence on the planning row
(see store/postgres.py `upsert_applications`). Address / parcel / zoning / filed and decided dates are
re-extracted from the motion so the merge loses as little as possible; lat/lng cannot be (no geocoding here).

Document path (researched 2026-10, all public, no auth)
--------------------------------------------------------
1. Adopted motions (primary, source_kind="motion"). The SF Property Information Map's "Related Documents"
   panel is backed by an M-Files search service keyed by record number:
       https://sfplanninggis.org/PlanningDocsMFiles/?search=<record number>&isPRJ=&kids=
   It returns JSON (served as text/html) listing every document filed on the record with ClassName and a
   docGroup; `ClassName == "CPC Motions and Resolutions"` + docGroup `PLN_DECISION_PUBLISHED` is the signed,
   adopted Planning Commission motion (file name `M-<motion no>.pdf`), downloadable from
   https://citypln-m-extnl.sfgov.org/External/link.ashx?Action=Download&...  This is the most reliable path:
   one lookup per record, it is the document the Commission secretary certifies (DECISION, vote, Exhibit A
   conditions of approval); verified on CUAs decided 2021–2026 (older years untested). Draft motions inside the hearing
   packets ("Motion No. XXXXXX") are NOT used: conditions are often amended at the hearing.
2. Adopted hearing minutes (discovery + fallback, source_kind="minutes"). Hearing dates come from the
   Planning Commission calendar (https://sfplanning.org/hearings-cpc-list, "Previous Hearings", newest
   first) and each hearing's minutes live at a predictable URL:
       https://citypln-m-extnl.sfgov.org/Commissions/Agenda_or_Minutes/<YYYYMMDD>_cpc_min.pdf   (2023+)
       https://citypln-m-extnl.sfgov.org/Commissions/Agenda_or_Minutes/<YYYYMMDD>_cal_min.pdf   (older)
   Minutes list every item with record number, ACTION, AYES/NAYS, MOTION number and a SPEAKERS list where
   "+" / "-" / "=" mark support / opposition / neutral speakers. They give (a) the CUA record numbers to look
   up when no Planning dataset raw pages are available and (b) hearing-level opposition. Only decisive
   actions (approved / disapproved / withdrawn) become rows — continuances are skipped so an older minutes
   file processed later can never regress a decided case back to "pending".
   Record numbers are also read from previously saved Planning dataset raw pages under
   raw_dir/datasf_planning/ when present (that module is not imported).
   (Legistar is the Board of Supervisors' system and does not hold Planning Commission motions.)

Politeness / caching
--------------------
* Every HTTP request goes through one `RateLimiter(0.5)` → request starts are at least 2 s apart, with the
  shared USER_AGENT from base.py (make_client); requests are sequential, never concurrent.
* Raw PDFs are cached under raw_dir/sf_planning_hearings/pdf/<sha256(url)[:24]>.pdf and never re-downloaded
  when present. M-Files lookup responses and minutes probes are saved under lookups/ (negative results are
  re-checked after 7 days for recent decisions, 60 days otherwise).
* Each document gets a sidecar envelope raw_dir/sf_planning_hearings/<stamp>-<label>.json
  (meta: url, record_number, hearing_date, fetched_at, source_kind, pdf, ...). `fetch` returns the sidecar
  paths; `parse(sidecar)` is pure (reads only the sidecar and its cached PDF).

Volume per nightly run
----------------------
Window: `since` or the last 5 years. One run downloads at most PLANNING_HEARINGS_MAX_DOCS new PDFs
(default 150; about a third reserved for minutes) and makes at most PLANNING_HEARINGS_MAX_REQUESTS HTTP
requests (default 450 ≈ 15 min at 0.5 req/s), newest first. Records / hearings already cached are skipped
without a request, so the nightly job walks back through the backlog over successive nights (~250 hearings
and several hundred CUA motions in 5 years → roughly a week to catch up, then a handful of documents/night).

Only sidecars written by this run are returned (cached documents were ingested on earlier nights); set
PLANNING_HEARINGS_REEMIT=1 to return every cached sidecar, e.g. to rebuild a fresh store without network.

Ordering: `fetch` returns minutes sidecars (oldest hearing first) before motion sidecars, so within a run
the richer motion row is upserted last. Minutes sidecars carry `skip_records` (records that already had a
motion when the minutes were fetched) so later runs never overwrite a motion row with a minutes row.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import re
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

import httpx

from precedent.models import Application, Confidence, Outcome, Source, SourceBatch
from precedent.pdftext import SECTION_SPECS, find_sections, read_pdf, squash, strip_running_headers
from precedent.sources.base import RateLimiter, SourceSpec, fetched_at_from, raw_path, read_raw, write_raw
from precedent.textparse import classify_use_types, detect_opposition, extract_conditions, is_late_night

log = logging.getLogger(__name__)

NAME: Source = "sf_planning_hearings"
RATE_LIMIT = 0.5  # requests per second → one request every 2 s
DEFAULT_MAX_DOCS = 150
DEFAULT_MAX_REQUESTS = 450
DEFAULT_WINDOW_YEARS = 5
MAX_PDF_BYTES = 60_000_000
MOTION_MAX_PAGES = 45  # motion text + Exhibit A precede the plan sheets (Exhibit B)
MINUTES_MAX_PAGES = 80

MFILES_URL = "https://sfplanninggis.org/PlanningDocsMFiles/"
CPC_LIST_URL = "https://sfplanning.org/hearings-cpc-list"
MINUTES_URLS = (
    "https://citypln-m-extnl.sfgov.org/Commissions/Agenda_or_Minutes/{ymd}_cpc_min.pdf",
    "https://citypln-m-extnl.sfgov.org/Commissions/Agenda_or_Minutes/{ymd}_cal_min.pdf",
)
PIM_URL = "https://sfplanninggis.org/pim/?search={record}"
MOTION_CLASS = "CPC Motions and Resolutions"
PERMIT_TYPE = "Conditional Use Authorization"

RECORD_RE = re.compile(r"\b(\d{4}[-.]\d{3,6}[A-Z][A-Z0-9]*(?:-\d{1,3})?)\b")
DECISIVE: frozenset[Outcome] = frozenset({"approved", "approved_with_conditions", "denied", "withdrawn"})


# =================================================================================================
# small parsing helpers (pure)
# =================================================================================================

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1
    )
}
DATE_RE = r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*,\s*(\d{4})"


def parse_long_date(text: str | None) -> dt.date | None:
    """'September 19, 2024' / 'SEPTEMBER 19, 2024' / 'February 4 , 2021' → date."""
    if not text:
        return None
    m = re.search(DATE_RE, text)
    if not m:
        return None
    month = _MONTHS.get(m.group(1)[:3].lower())
    if month is None:
        return None
    try:
        return dt.date(int(m.group(3)), month, int(m.group(2)))
    except ValueError:
        return None


def date_from_match(m: re.Match[str] | None, first_group: int = 1) -> dt.date | None:
    """Date from three consecutive (month, day, year) groups of a DATE_RE-based match."""
    if m is None:
        return None
    groups = m.groups()[first_group - 1 :]
    for i in range(0, len(groups) - 2, 3):
        mon, day, year = groups[i : i + 3]
        if mon and day and year:
            return parse_long_date(f"{mon} {day}, {year}")
    return None


def fmt_date(d: dt.date | None) -> str:
    return f"{d:%B} {d.day}, {d.year}" if d else "unknown date"


def normalize_record(rec: str) -> str:
    return re.sub(r"\s+", "", rec).upper()


def record_digits(rec: str) -> str:
    """Year + sequence digits of a record number, ignoring the type suffix ('2024-001579CUA' → '2024001579')."""
    m = re.match(r"\s*(\d{4})\s*[-.]\s*(\d{3,6})", rec)
    return f"{m.group(1)}{m.group(2)}" if m else rec


def _iso(d: dt.date | None) -> str | None:
    return d.isoformat() if d else None


def _date_from_iso(value: Any) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# ---- hours --------------------------------------------------------------------------------------

_TIME_RE = re.compile(
    r"(?<![\d:])(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s?m\b\.?|\b(noon)\b|\b(midnight)\b", re.I
)
_JOIN_RE = re.compile(r"^\s*(?:and|to|until|till|through|-|–|—)\s*$", re.I)
_PROHIBIT_RE = re.compile(r"\b(?:not|no|closed?|prohibited|except)\b[^.;]{0,60}\b(?:between|from)\s*$", re.I)
_UNTIL_RE = re.compile(
    r"(?:\buntil|\btill|\blimited to|\bclose[sd]?\s+(?:at|by)|\bclosing(?:\s+time)?(?:\s+(?:of|at))?|\bno later than|\bnot\s+(?:operate|be open|remain open)\s+(?:past|after|later than)|\bnot operate past|\bpast)\s*$",
    re.I,
)


def _hhmm(m: re.Match[str]) -> str:
    if m.group(4):
        return "12:00"
    if m.group(5):
        return "00:00"
    hour, minute = int(m.group(1)) % 12, int(m.group(2) or 0)
    if m.group(3).lower() == "p":
        hour += 12
    return f"{hour:02d}:{minute:02d}"


def _latest_key(hhmm: str) -> int:
    h, mm = map(int, hhmm.split(":"))
    return (h + 24 if h < 6 else h) * 60 + mm  # 00:00–05:59 count as "after midnight"


def closing_hour(texts: Iterable[str]) -> str | None:
    """Latest closing time implied by hour language, as 24h 'HH:MM'.

    'limited to 6 a.m. to 2 a.m.' → 02:00 (end of the operating window);
    'shall not operate between 2 a.m. and 6 a.m.' → 02:00 (start of the prohibited window);
    'until 1:30 am', 'no later than 10 p.m.' → the time itself.
    """
    candidates: list[str] = []
    for text in texts:
        s = squash(text)
        tokens = list(_TIME_RE.finditer(s))
        used: set[int] = set()
        for i in range(len(tokens) - 1):
            a, b = tokens[i], tokens[i + 1]
            if i in used or not _JOIN_RE.match(s[a.end() : b.start()]):
                continue
            used.update({i, i + 1})
            before = s[max(0, a.start() - 80) : a.start()]
            candidates.append(_hhmm(a) if _PROHIBIT_RE.search(before) else _hhmm(b))
        for i, tok in enumerate(tokens):
            if i not in used and _UNTIL_RE.search(s[max(0, tok.start() - 40) : tok.start()]):
                candidates.append(_hhmm(tok))
    return max(candidates, key=_latest_key) if candidates else None


# ---- conditions ---------------------------------------------------------------------------------

_COND_ITEM_RE = re.compile(r"(?m)^[ \t]*(\d{1,2})\.[ \t]*([A-Z][A-Za-z0-9’'&/,()\- ]{2,90}?)\.[ \t]+")
# lettered sub-items are written "A. text" or "(A) text"
_SUB_ITEM_RE = re.compile(r"(?m)^[ \t]*(?:([A-H])\.|\(([A-H])\))[ \t]+")
_COMPLIANCE_RE = re.compile(r"\bFor (?:further )?information about compliance\b.*", re.I | re.S)
# the same, whatever the spacing between the words: 2009-2011 text layers join words with a non-breaking space next to
# an ordinary one, which reads as two spaces once the non-breaking one is made a space. Used for older motions only
# (older_formats): 32 cached 2019+ conditions keep contact text the strict pattern does not take, and stay as they are.
# OCR misreadings are taken too ("Far information", "For .information", "abouf"), and a page footer that fell between
# "For" and "information" ("For SAN FRANCISCO 14 PLANNING DEPARTMENT information about compliance").
# A lower-case "for information about compliance." that ends a sentence of the condition itself is kept (group
# "keep"), and only what follows it is removed: the Monitoring template ("... and work with the Planning Department
# for information about compliance.") had been cut to "... work with the Planning Department" (2009.0342C #5,
# 2011.0026C #8, 2011.0208C #3). What follows it is the contact line, or what is left of one that
# strip_running_headers removed as a repeated line (2015-005788CUA: the bare "www.sf-planning.org"). A contact line
# itself is "For information about compliance, contact ..." and never ends at "compliance.".
_COMPLIANCE_LOOSE_RE = re.compile(
    r"\b(?:(?P<keep>(?-i:for)\s+information\s+about\s+compliance\s*\.)(?=\s|$)"
    r"|F[oa]r\s+(?:SAN\s+F[^\n]{0,60}?DEP[A-Za-z]*\s+)?[.,]?(?:further\s+)?information\s+abou[tf]\s+compliance\b).*",
    re.I | re.S,
)


def _compliance_kept(m: re.Match[str]) -> str:
    """What a compliance pattern's match is replaced with: its "keep" group (_COMPLIANCE_LOOSE_RE), else nothing."""
    return m.groupdict().get("keep") or ""
_EXCLUDE_TITLE_RE = re.compile(
    r"^(?:validity|expiration|diligent pursuit|extension|conformity|enforcement|revocation|monitoring|severability"
    r"|recordation|changes and modifications|final materials|managing traffic"
    r"|sidewalk maintenance|printing|bird|street trees|transportation demand|first source|inclusionary|affordable"
    r"|mitigation|improvement measure|landscap|bicycle|parking|car share|loading|power|anti-discriminatory"
    r"|art|childcare|development impact|fees?\b|jobs housing|eastern neighborhoods|transit|construction|notices? of special"
    r"|screening|wireless|wts\b|antenna|radio|rf\b|emissions|implementation and monitoring|project sponsor)",
    re.I,
)
_OPERATIONAL: list[tuple[str, re.Pattern[str]]] = [
    (
        "hours",
        re.compile(
            r"hours? of (?:operation|entertainment)|operating hours|operational hours|\d\s*(?:a\.?m\b|p\.?m\b)|\bnoon\b|\bmidnight\b|shall (?:not )?(?:close|be closed|operate) (?:between|after|past)",
            re.I,
        ),
    ),
    (
        "entertainment",
        re.compile(
            r"\b(?:dancing|dj\b|disc jockey|amplified|live (?:music|entertainment|performance)|entertainment)",
            re.I,
        ),
    ),
    ("security", re.compile(r"\bsecurity\b", re.I)),
    ("good_neighbor", re.compile(r"good neighbor|notices? (?:posted|urging patrons)|patrons to leave", re.I)),
    ("noise", re.compile(r"sound ?proof|\bnoise\b|sound attenuat|vibration|\bbass\b", re.I)),
    ("alcohol", re.compile(r"\babc\b|\bliquor\b|\balcohol|\btype \d{2}\b|on-sale|off-sale", re.I)),
    (
        "outdoor",
        re.compile(
            r"outdoor (?:activity|seating|dining)|sidewalk (?:seating|caf)|parklet|patio|rooftop (?:bar|deck|seating|dining|terrace)",
            re.I,
        ),
    ),
    ("community_liaison", re.compile(r"community liaison", re.I)),
    # routine for restaurants and bars, and skipped until 2026-11 (validation found 42 in 30 motions)
    ("odor", re.compile(r"\bodou?r|\bodou?rs\b|exhaust|ventilation|smoke", re.I)),
    ("garbage", re.compile(r"\bgarbage|\brefuse\b|\brecycling|\bcompost|\btrash\b|\blitter", re.I)),
    ("lighting", re.compile(r"\blighting\b|\blights?\b|\billuminat", re.I)),
    ("signage", re.compile(r"\bsignage\b|\bsigns?\b", re.I)),
]


@dataclass(frozen=True)
class Condition:
    number: str
    title: str
    text: str  # short clause ≤ 300 chars
    categories: tuple[str, ...]


def _clip(text: str, limit: int = 300) -> str:
    text = squash(text)
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    sentence_end = cut.rfind(". ")
    if sentence_end >= limit * 0.5:
        return cut[: sentence_end + 1]
    return cut[: cut.rfind(" ")].rstrip(",;:") + "…"


def _categories(text: str) -> tuple[str, ...]:
    return tuple(name for name, pat in _OPERATIONAL if pat.search(text))


def _split_condition(
    number: str, title: str, body: str, compliance: re.Pattern[str] = _COMPLIANCE_RE
) -> list[tuple[str, str, str]]:
    """(number, title, text) units for one numbered condition: one per lettered sub-item when there are two or
    more, otherwise the condition itself. Sub-items are split BEFORE the "For information about compliance…"
    contact lines are removed: that pattern runs to the end of the text it is given, so applying it to the whole
    condition first deleted every sub-item after the first contact line (odour and garbage, usually)."""
    subs = list(_SUB_ITEM_RE.finditer(body))
    if len(subs) < 2:
        return [(number, title, compliance.sub(_compliance_kept, body))]
    parts = []
    for j, s in enumerate(subs):
        letter = s.group(1) or s.group(2)
        sub_body = body[s.end() : subs[j + 1].start() if j + 1 < len(subs) else len(body)]
        parts.append((f"{number}{letter}", f"{title} ({letter})", compliance.sub(_compliance_kept, sub_body)))
    return parts


def _condition_body(section: str, items: list[re.Match[str]], i: int) -> str:
    return section[items[i].end() : items[i + 1].start() if i + 1 < len(items) else len(section)]


# ---- older motion formats (2009-2018), used by all_conditions only --------------------------------------------

# the number delimiters older motions use: "12.", "12)" (2016-2017), and "10.." (a stray second period)
_OLDER_DELIM = r"(?:\.\.?|\))"
# a titled condition in an older motion: _COND_ITEM_RE with those delimiters, and a title that may open with a
# quotation mark and carry curly quotes or Unicode dashes (2011.0701C: "14. ‘Bar Use’ ‐ Hours of Operation.", whose
# U+2010 hyphen and opening quote kept it from being a condition, so it ran on inside #13; 2010.1080C opens its
# quote with a ’)
_COND_ITEM_OLDER_RE = re.compile(
    rf"(?m)^[ \t]*(\d{{1,2}}){_OLDER_DELIM}[ \t]*([‘’“\"']?[A-Z][A-Za-z0-9’‘“”\"'&/,()\-‐‑–— ]{{2,90}}?)\.[ \t]+"
)
# any numbered paragraph, titled or not ("12. An enclosed garbage area shall be provided ...")
_NUMBERED_LINE_RE = re.compile(rf"(?m)^[ \t]*(\d{{1,2}}){_OLDER_DELIM}[ \t]+(?=\S)")
# a titled paragraph whose number the text layer lost (OCR, or Word list numbering not in the text): "Extension. This
# authorization ...", optionally behind an OCR'd "1" ("L Validity. ...")
_UNNUMBERED_TITLE_RE = re.compile(
    r"(?m)^[ \t]*(?:[LlI|][ \t]+)?([A-Z][A-Za-z’'&/,()\- ]{2,90}?)\.[ \t]+(?=\S)"
)
# where a paragraph can start: after a blank line, a sentence end, an all-capitals heading or a URL / footer line
# ... or a compliance-contact line, which can end in a comma after the phone number ("... at 415-558-8728,")
_PARA_END_RE = re.compile(
    r"(?:^\s*$|[.)\]:]\s*$|www|http|\.org|\.gov|planning\.or|information\s+abou[tf]\s+compliance|\d{3}\W\d{4}\s*,\s*$)",
    re.I,
)
_LENIENT_TITLE_RE = re.compile(r"([A-Z][^.\n]{1,89}?)\.(?=\s)")
# a title ended by a colon ("19. Temporary Liquor Service: Per Planning Code Section 205.3, ..."), on the gap-fill path
_COLON_TITLE_RE = re.compile(r"([A-Z][^.:\n]{1,89}?):(?=\s)")
_MAX_GAP = 6


def _title_ok(title: str) -> bool:
    return (
        len(title.split()) <= 10
        and not re.search(r"\d", title)
        and not re.match(r"for (?:further )?information\b", title, re.I)
    )


# a short Title Case heading line ("Parking & Traffic", 2009.1103C)
_TITLE_HEADING_RE = re.compile(r"^[ \t]*[A-Z][a-z]*(?:[ \t]+(?:[A-Z][a-z]*|&|and|of|the))*[ \t]*$")


def _starts_para(section: str, pos: int) -> bool:
    """Whether the line at pos opens a paragraph: the line before it is blank, ends a sentence, is an
    all-capitals or short Title Case heading or a URL / footer line."""
    prev = section[section.rfind("\n", 0, max(pos - 1, 0)) + 1 : max(pos - 1, 0)]
    heading = bool(_TITLE_HEADING_RE.match(prev)) and len(prev.split()) <= 5
    return pos == 0 or heading or bool(_PARA_END_RE.search(prev)) or not re.search(r"[a-z]", prev)


def _paragraph_titles(section: str, lo: int, hi: int) -> list[tuple[str, int, int]]:
    """(title, start, end) for each line in section[lo:hi] that opens a titled, unnumbered paragraph. A running
    header is not one ("Motion No. 19659 CASE NO. 2016-000455CUA": its "title" is followed by a number)."""
    out = []
    for m in _UNNUMBERED_TITLE_RE.finditer(section, lo, hi):
        title = squash(m.group(1))
        eol = section.find("\n", m.start())
        line = section[m.start() : eol if eol >= 0 else len(section)]
        if section[m.end() : m.end() + 1].isdigit() or _RUNNING_HEADER_RE.search(line):
            continue
        if _starts_para(section, m.start()) and _title_ok(title):
            out.append((title, m.start(), m.end()))
    return out


def _gap_title(section: str, pos: int, hi: int) -> re.Match[str] | None:
    """The title opening a numbered line whose title the strict pattern rejected: up to the first period, or up to
    a colon when that comes first ("Temporary Liquor Service: Per ...")."""
    found = [
        m for m in (_LENIENT_TITLE_RE.match(section, pos, hi), _COLON_TITLE_RE.match(section, pos, hi)) if m
    ]
    return min(found, key=lambda m: m.end()) if found else None


def _number_re(k: int, missing: list[int]) -> re.Pattern[str]:
    """A line opening condition k. OCR reads an 8 as "S" or "$" ("S. Enforcement."): taken as the 8 only when the
    8 is the one number missing (7 then 9)."""
    num = r"(?:8|S|\$)" if missing == [8] else str(k)
    return re.compile(rf"(?m)^[ \t]*{num}{_OLDER_DELIM}[ \t]+(?=\S)")


def _fill_gaps(section: str, items: list[tuple[str, str, int, int]]) -> list[tuple[str, str, int, int]]:
    """Add the conditions a numbered run skips (5, 7 → 6), whose number the PDF text lost or garbled.

    First a line with the missing number whose title the strict pattern rejected ("4. E~ctension. All ...",
    "9. Design Considerations." at a line end). Then, for numbers still missing, unnumbered titled paragraphs in
    the gap: one per missing number, in order, when there are as many; when there are fewer, they take the first
    missing numbers and the rest stay missing. A leading gap (the run starts at 3) is filled the same way from the
    start of the section; numbered lines after the last condition are _extend_tail's. A list
    that restarts its numbering under a heading (2012.0262CUA: "6. Conformity ..." then "DESIGN", an unnumbered
    "Garbage, composting and recycling storage." and "2. Signage.") gets its leading gap filled from the titled
    paragraphs between the two lists, again only when there are exactly as many as numbers missing."""
    out: list[tuple[str, str, int, int]] = []
    prev_num, prev_end = 0, 0
    for item in items:
        restarted = prev_num and 1 < int(item[0]) <= min(prev_num, 1 + _MAX_GAP)
        if restarted:  # a list that restarts its numbering and is missing its start
            want = list(range(1, int(item[0])))
            paras = _paragraph_titles(section, prev_end, item[2])
            if len(paras) == len(want):
                out += [(str(n), t, st, en) for n, (t, st, en) in zip(want, paras, strict=True)]
            out.append(item)
            prev_num, prev_end = int(item[0]), item[3]
            continue
        # no gap, or a jump of more than _MAX_GAP (a different list or a misread number, not lost conditions)
        if not prev_num + 1 < int(item[0]) <= prev_num + 1 + _MAX_GAP:
            out.append(item)
            prev_num, prev_end = int(item[0]), item[3]
            continue
        hi, missing, found = item[2], list(range(prev_num + 1, int(item[0]))), []
        pos = prev_end
        for k in missing:
            m = _number_re(k, missing).search(section, pos, hi)
            if m is None:
                continue
            t = _gap_title(section, m.end(), hi)
            title = squash(t.group(1)) if t and len(t.group(1).split()) <= 10 else "Condition"
            found.append((str(k), title, m.start(), t.end() if t and title != "Condition" else m.end()))
            pos = found[-1][3]
        # unnumbered titled paragraphs between the anchors found so far
        anchors = [(prev_num, prev_end), *[(int(f[0]), f[3]) for f in found], (int(item[0]), hi)]
        for (a_num, a_end), (b_num, _b) in pairwise(anchors):
            want = [n for n in range(a_num + 1, b_num) if str(n) not in {f[0] for f in found}]
            b_start = next((f[2] for f in found if int(f[0]) == b_num), hi)
            if not want:
                continue
            paras = _paragraph_titles(section, a_end, b_start)
            if len(paras) <= len(want):
                # as many titled paragraphs as numbers missing: one each, in order. Fewer (2016-002786CUA: 5, an
                # unnumbered "Enforcement." paragraph, 8; the motion lost 7 altogether): the paragraphs take the
                # first missing numbers, so the condition is kept rather than run on inside the one before it
                found += [(str(n), t, st, en) for n, (t, st, en) in zip(want, paras, strict=False)]
        out += sorted(found, key=lambda f: f[2])
        out.append(item)
        prev_num, prev_end = int(item[0]), item[3]
    return out


def _condition_items(section: str, older_formats: bool) -> list[tuple[str, str, int, int]]:
    """(number, title, start, end of heading) for each condition in an Exhibit A conditions section."""
    if not older_formats:
        return [(m.group(1), squash(m.group(2)), m.start(), m.end()) for m in _COND_ITEM_RE.finditer(section)]
    # older motions also number "12)" and slip a second period in ("10.. Odor Control.")
    items = [
        (m.group(1), squash(m.group(2)), m.start(), m.end()) for m in _COND_ITEM_OLDER_RE.finditer(section)
    ]
    # untitled numbered paragraphs (2009-2010 motions): a run 1, 2, 3, ... of paragraph openings that the titled
    # pattern mostly misses. Each item must open a paragraph, and titled paragraphs win when there are at least as
    # many of them: a numbered list INSIDE one condition (2012.0370C's transformer vault preference schedule,
    # 1-7 joined by semicolons) is not the conditions.
    # A number printed twice (2010.0514C: 1-5, a second "5. The ground level storefront ...", then 6-13) is kept
    # when the numbering goes on after it; _unique_numbers numbers the second one "2.5".
    run: list[re.Match[str]] = []
    for m in _NUMBERED_LINE_RE.finditer(section):
        n, last = int(m.group(1)), int(run[-1].group(1)) if run else 0
        repeat = n == last and len(run) >= 2 and int(run[-2].group(1)) != last
        if (n == last + 1 or repeat) and _starts_para(section, m.start()):
            run.append(m)
    if len(run) >= 2 and run[-1].group(1) == run[-2].group(1):
        run.pop()  # a repeated number the numbering does not go on after
    paras = _paragraph_titles(section, 0, len(section))
    if len(run) >= 3 and len(items) * 2 < len(run) and len(paras) < len(run):
        return _unique_numbers([(m.group(1), "Condition", m.start(), m.end()) for m in run])
    if not items:
        # titled paragraphs with no numbers at all in the text layer (2012 motions): number them in order
        return [(str(i + 1), t, st, en) for i, (t, st, en) in enumerate(paras)] if len(paras) >= 3 else []
    return _unique_numbers(_extend_tail(section, _fill_gaps(section, items)))


def _extend_tail(section: str, items: list[tuple[str, str, int, int]]) -> list[tuple[str, str, int, int]]:
    """Untitled numbered paragraphs that go on from the last titled condition (2010.1162C: 29 "Hours of Operation."
    then "30. The Planning Department will conduct ...", 31-33; 2011.0126C: 24; 2013.0224C: "23. All required
    permits shall be obtained."). Nothing took them, so they ran on inside the last condition, and its text is cut
    at 600 characters (all_conditions' _clip), which dropped every condition after the first few hundred
    characters. Each must be the next number and open a paragraph. Its title is the words up to the first period
    (or colon) when they read as a title, in title case ("11. Security." at a line end, 2017-007658CUA); otherwise
    "Condition" ("23. All required permits shall be obtained." is a sentence, not a title)."""
    if not items:
        return items
    out = list(items)
    n, pos = int(out[-1][0]), out[-1][3]
    while (m := _number_re(n + 1, []).search(section, pos)) and _starts_para(section, m.start()):
        t = _gap_title(section, m.end(), len(section))
        title = squash(t.group(1)) if t else ""
        if t and _title_ok(title) and _title_case(title):
            out.append((str(n + 1), title, m.start(), t.end()))
        else:
            out.append((str(n + 1), "Condition", m.start(), m.end()))
        n, pos = n + 1, out[-1][3]
    return out


_SMALL_WORDS = frozenset(
    ["a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "per", "the", "to", "with"]
)


def _title_case(title: str) -> bool:
    """Every word but the small ones opens with a capital (or a quotation mark): "Interior Floor Plan", not "All
    required permits shall be obtained"."""
    return all(not w[:1].islower() or w.lower() in _SMALL_WORDS for w in title.split())


def _unique_numbers(items: list[tuple[str, str, int, int]]) -> list[tuple[str, str, int, int]]:
    """Condition numbers made unique within a motion, for motions that restart their numbering under each heading
    (2012.0262CUA: PERFORMANCE 1-6, then DESIGN 1-2, MONITORING 3, OPERATION 4-6). case_conditions is keyed by
    (motion, number), so a repeated number would drop the later condition.

    Scheme: the conditions are cut into lists where the number does not go up. The first list keeps its numbers;
    a later list whose numbers repeat one already used gets its list's position as a prefix with a dot: "2.3" is
    condition 3 of the motion's second list, and its lettered parts are "2.3A", "2.3B". A plain number ("3") or a
    lettered part ("8A") never has a dot, so the two cannot collide. A later list that repeats no number keeps
    its numbers as printed.

    A number printed twice with the numbering going on after it (2010.0514C: 1-5, 5, 6-13) is a printing slip, not
    a restart: the repeated one is a list of its own ("2.5", condition 5 of the second list) and the numbers after
    it (6-13) stay in the list before, as printed."""
    lists: list[list[int]] = []  # item indexes, in the order the lists start
    current: list[int] | None = None
    for i, item in enumerate(items):
        n = int(item[0])
        repeat = (
            current is not None and n == int(items[current[-1]][0])
            and i + 1 < len(items) and int(items[i + 1][0]) == n + 1
        )  # fmt: skip
        if repeat:
            lists.append([i])
            continue
        if current is None or n <= int(items[current[-1]][0]):
            current = []
            lists.append(current)
        current.append(i)
    seen: set[str] = set()
    number = [item[0] for item in items]
    for k, lst in enumerate(lists, 1):
        numbers = {items[i][0] for i in lst}
        if numbers & seen:
            for i in lst:
                number[i] = f"{k}.{items[i][0]}"
        seen |= numbers
    return [(number[i], *item[1:]) for i, item in enumerate(items)]


def all_conditions(section: str, *, older_formats: bool = False) -> list[Condition]:
    """Every numbered Exhibit A condition (and lettered sub-item), whatever its subject. Conditions that match
    no operating category get the category ``other``. Used for the full-conditions validation pass.

    ``older_formats`` (full_conditions.py sets it for motions decided before 2019) also reads the 2009-2018
    layouts: non-breaking spaces (2009-2011 text layers) count as spaces, untitled numbered paragraphs get the
    title "Condition", titled paragraphs with no numbers at all are numbered in order, numbers the text layer
    lost are restored (_fill_gaps), untitled numbered paragraphs after the last titled condition are conditions
    (_extend_tail), numbering that restarts under each heading or a number printed twice is made unique
    (_unique_numbers), and "For information about compliance" contact lines are removed whatever their spacing. It is off by default so the published 2019+ conditions stay exactly as they
    are: restoring lost numbers would also add conditions to 23 of the 197 cached 2019+ motions."""
    if older_formats:
        section = section.replace("\xa0", " ")  # same length, so match offsets still index the section
    items = _condition_items(section, older_formats)
    compliance = _COMPLIANCE_LOOSE_RE if older_formats else _COMPLIANCE_RE
    out: list[Condition] = []
    for i, (number, title, _start, end) in enumerate(items):
        body = section[end : items[i + 1][2] if i + 1 < len(items) else len(section)]
        for num, ttl, txt in _split_condition(number, title, body, compliance):
            cats = _categories(f"{ttl}. {txt}") or ("other",)
            out.append(Condition(num, ttl, _clip(f"{ttl}: {squash(txt)}", 600), cats))
    return out


def operational_conditions(section: str) -> list[Condition]:
    """Numbered Exhibit A conditions that constrain operations (hours, entertainment, security, noise, ...)."""
    items = list(_COND_ITEM_RE.finditer(section))
    out: list[Condition] = []
    for i, m in enumerate(items):
        number, title = m.group(1), squash(m.group(2))
        if _EXCLUDE_TITLE_RE.match(title):
            continue
        for num, ttl, txt in _split_condition(number, title, _condition_body(section, items, i)):
            cats = _categories(f"{ttl}. {txt}")
            if not cats:
                continue
            out.append(Condition(num, ttl, _clip(f"{ttl}: {squash(txt)}"), cats))
    return out


# ---- opposition ---------------------------------------------------------------------------------

_NUM = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|twenty|several|multiple|many|numerous|a number of|at least \w+)"
_OPPOSED_RE = re.compile(
    rf"\b{_NUM}\s+(?:\w+\s+){{0,3}}(?:letters?|emails?|e-mails?|comments?|messages?|calls?|correspondence|members of the public|petitions?|signatures?)\s+(?:\w+\s+){{0,4}}(?:in\s+)?opposition"
    rf"|\b(?:letters?|emails?|comments?|correspondence)\s+(?:\w+\s+){{0,3}}(?:in\s+)?opposition\b"
    r"|\bopposition (?:to the project )?(?:came|was received|from)\b"
    r"|\b(?:association|neighbors?|residents|merchants)\b[^.]{0,80}\b(?:oppose[sd]?|opposition)\b"
    r"|\bdiscretionary review (?:request|application)s? (?:was|were|has been) filed|\bDR request\b"
    r"|\bappealed\b|\bappeal (?:was|has been) filed",
    re.I,
)
_NONE_RE = re.compile(
    r"\b(?:no|zero|not received any|has not received any|have not received any|did not receive any|received no)\s+"
    r"(?:\w+\s+){0,2}(?:public comments?|comments?|correspondence|opposition|letters?|objections?)\b|\bunopposed\b",
    re.I,
)


def opposition_from_comment(section: str | None) -> bool | None:
    """True when the comment section records opposition, False when it records none, else None."""
    if not section:
        return None
    s = squash(section)
    if re.search(r"\b(?:no|zero|0)\s+(?:\w+\s+){0,3}(?:in\s+)?opposition\b", s, re.I):
        return False
    if _OPPOSED_RE.search(s):
        return True
    if re.search(
        r"\ball (?:\w+ ){0,2}(?:were|are|was) (?:\w+ ){0,2}(?:of|in) support\b|\bonly (?:\w+ ){0,2}(?:of|in) support\b",
        s,
        re.I,
    ):
        return False
    if _NONE_RE.search(s):
        return False
    return detect_opposition(s)


# ---- votes --------------------------------------------------------------------------------------


def _spaced(word: str) -> str:
    return r"\s?".join(word)


_VOTE_RE = re.compile(
    rf"{_spaced('AYES')}\s*:\s*(?P<ayes>.*?)\s*{_spaced('NAYS')}\s*:\s*(?P<nays>.*?)\s*"
    rf"(?:(?:{_spaced('ABSENT')}|{_spaced('RECUSED')}|{_spaced('EXCUSED')})\s*:\s*(?P<absent>.*?)\s*)?"
    rf"(?=(?:{_spaced('ADOPTED')}|{_spaced('RECUSED')}|{_spaced('MOTION')})\s*:|APPEAL AND|Jonas|Commission Secretary|$)",
    re.S,
)


def _names(raw: str | None) -> list[str]:
    if not raw:
        return []
    raw = squash(raw)
    if re.match(r"^(?:none|n/a)\b", raw, re.I):
        return []
    names = [n.strip(" .") for n in re.split(r",|\band\b", raw) if n.strip(" .")]
    return [n for n in names if 1 < len(n) <= 30 and not n.lower().startswith("none")][:12]


def parse_vote(text: str) -> tuple[list[str], list[str], str | None]:
    m = _VOTE_RE.search(squash(text))
    if not m:
        return [], [], None
    ayes, nays = _names(m.group("ayes")), _names(m.group("nays"))
    if not ayes:
        return [], nays, None
    return ayes, nays, f"{len(ayes)}-{len(nays)}"


# =================================================================================================
# motion parsing
# =================================================================================================

_MOTION_NO_RE = re.compile(r"Motion\s+No\.?\s*:?\s*(\d{5})\b", re.I)
_HEARING_DATE_RE = re.compile(r"HEARING\s*D\s?A\s?TE\s*:\s*" + DATE_RE, re.I)
_ADOPTED_LABEL_RE = re.compile(r"ADOPTED\s*:\s*" + DATE_RE, re.I)
_ADOPTED_CERT_RE = re.compile(r"ADOPTED the foregoing Motion on\s+" + DATE_RE, re.I)
_FILED_RE = re.compile(r"\bOn\s+" + DATE_RE + r",[^.]{0,250}?\bfiled\b", re.I)
_RECORD_LINE_RE = re.compile(
    r"(?:Record|Case)\s+No\.?\s*:?\s*(\d{4}\s*[-.]\s*\d{3,6}\s*[A-Z][A-Z0-9]*(?:-\d{1,3})?)", re.I
)
_ADDRESS_RE = re.compile(r"Project Address\s*:\s*([^\n]+)", re.I)
_ZONING_RE = re.compile(r"^\s*Zoning\s*:\s*([^\n]+)", re.I | re.M)
_PARCEL_RE = re.compile(r"Block\s*/\s*Lot\s*:?\s*(\d{4}[A-Z]?)\s*/\s*(\d{3}[A-Z]?)", re.I)
# PDF text sometimes splits the operative verb ("hereby AP PROVES"); allow one space between its letters there.
_SPACED = {v: r"\s?".join(v) for v in ("DISAPPROVES", "DENIES", "APPROVES")}
_VERB_RE = re.compile(
    rf"hereby\s+({_SPACED['DISAPPROVES']}|{_SPACED['DENIES']}|{_SPACED['APPROVES']})\b"
    r"|\b(DISAPPROVES|DENIES|APPROVES)\b",
    re.I,
)


def _verb_outcome(text: str, *, caps_only: bool, has_conditions: bool) -> Outcome | None:
    for m in _VERB_RE.finditer(text):
        verb = re.sub(r"\s", "", m.group(1) or m.group(2) or "")
        if caps_only and m.group(2) and verb != verb.upper():
            continue  # in running prose only trust the all-caps operative verb
        if verb.upper() in {"DISAPPROVES", "DENIES"}:
            return "denied"
        if verb.upper() == "APPROVES":
            return "approved_with_conditions" if has_conditions or "condition" in text.lower() else "approved"
    return None


def _outcome_from_decision(decision: str, whole: str, has_conditions: bool) -> Outcome:
    dec, full = squash(decision), squash(whole)
    if re.search(r"intent to (?:disapprove|deny|approve)", dec or full, re.I):
        return "pending"
    if dec:
        found = _verb_outcome(dec, caps_only=False, has_conditions=has_conditions)
        if found:
            return found
        if re.search(r"\bwithdr[ae]wn?\b", dec, re.I):
            return "withdrawn"
        if re.search(r"\bcontinued?\b", dec, re.I):
            return "pending"
    found = _verb_outcome(full, caps_only=True, has_conditions=has_conditions)
    if found:
        return found
    if re.search(r"MOVED,?\s+that the Commission hereby authorizes the Conditional Use", full, re.I):
        return "approved_with_conditions"
    return "unknown"


_VERB_TEXT = {
    "approved_with_conditions": "approved with conditions",
    "approved": "approved",
    "denied": "disapproved",
    "withdrawn": "recorded the withdrawal of",
    "pending": "continued",
    "unknown": "acted on",
}


def _zoning(raw: str | None) -> str | None:
    if not raw:
        return None
    z = re.sub(r"\s*Zoning District\s*$", "", squash(raw), flags=re.I)
    return z[:80] or None


_SUMMARY_FIRST = {
    "hours",
    "entertainment",
    "security",
    "good_neighbor",
    "noise",
    "alcohol",
    "outdoor",
    "community_liaison",
}


def _summary_conditions(conds: list[Condition]) -> str:
    """Up to four condition titles, operating conditions (hours, sound, security …) before odour, garbage,
    lighting and signage, which nearly every food and drink approval carries."""
    titles: list[str] = []
    ordered = sorted(conds, key=lambda c: 0 if _SUMMARY_FIRST & set(c.categories) else 1)
    for c in ordered:
        t = re.sub(r"\s*\([A-H]\)$", "", c.title)
        if "hours" in c.categories:
            t = c.text.split(": ", 1)[-1] if len(c.text) < 140 else t
        t = t.rstrip(". ")
        if t not in titles:
            titles.append(t)
    return "; ".join(titles[:4])


_RUNNING_HEADER_RE = re.compile(r"Motion\s+No\.?\s*\d{5}|RECORD\s+NO\.?|Resolution\s+No\.?\s*\d{4,5}", re.I)
_PLAN_SHEET_RE = re.compile(
    r"\bSCALE\s*:|\bDRAWN\s*:|\bSHEET\b|\d+/\d+\"\s*=\s*1'|\bARCHITECT\b|\bFLOOR PLAN\b|\bELEVATION\b"
)


def is_plan_page(index: int, page: str) -> bool:
    """A page after page 1 with no motion running header that reads like a drawing (Exhibit B plan sheet):
    mostly capitals, sheet labels, or very little prose."""
    if index == 0 or _RUNNING_HEADER_RE.search(page[:400]):
        return False
    letters = [ch for ch in page if ch.isalpha()]
    upper = sum(ch.isupper() for ch in letters) / len(letters) if letters else 1.0
    return len(letters) < 400 or upper > 0.6 or len(_PLAN_SHEET_RE.findall(page)) >= 2


# an older motion's page header that _RUNNING_HEADER_RE misses: "Motion 18420", "Motion No. M-18398", "Final Motion
# ... CASE NO. 2012.1225C"
_OLDER_PAGE_HEADER_RE = re.compile(r"\bCASE\s+NO\b|\bMotion\s+(?:No\.?\s*)?(?:M-)?\d{5}\b", re.I)


def is_plan_page_older(index: int, page: str) -> bool:
    """is_plan_page for the second reading of an older motion (full_conditions.extract): a short page that carries
    the motion's page header (the last findings page, "11. The Commission hereby finds ...", or the vote page) or
    a blank page is not a plan sheet. is_plan_page took them for one and the text ended before Exhibit A."""
    return (
        is_plan_page(index, page)
        and any(ch.isalpha() for ch in page)
        and not _OLDER_PAGE_HEADER_RE.search(page[:400])
    )


_NUMBER_ALONE_RE = re.compile(r"(?m)^([ \t]*\d{1,2}[.)])[ \t]*\n\s*(?=[A-Z])")


def join_number_lines(text: str) -> str:
    """pdftotext (no layout) puts a condition's number on a line of its own ("1.", blank line, "Validity and
    Expiration. The ..."): join them back ("1. Validity and Expiration. The ...") as pypdf reads them."""
    return _NUMBER_ALONE_RE.sub(r"\1 ", text)


def motion_body(text: str, stop: Callable[[int, str], bool] | None = None) -> str:
    """Drop the appended plan sheets (Exhibit B) from extracted motion text: from the first page ``stop`` (by default
    is_plan_page) says is one."""
    stop = stop or is_plan_page
    pages = text.split("\f")
    for i, page in enumerate(pages):
        if stop(i, page):
            return "\f".join(pages[:i])
    return text


# The Mitigation Monitoring and Reporting Program (Exhibit C) that some older motions append right after their
# conditions (2012.0370C). Its heading repeats on every page, so strip_running_headers removes it and the program's
# table ran on into the last condition, its rows read as conditions 20-23.
# (spaces may be non-breaking: [^\S\n])
_OLDER_CONDITIONS_END_RE = re.compile(
    r"(?m)^[^\S\n]*(?:EXHIBIT[^\S\n]+C\b|MITIGATION[^\S\n]+MONITORING[^\S\n]+AND[^\S\n]+REPORTING"
    r"|MEASURES[^\S\n]+ADOPTED[^\S\n]+AS[^\S\n]+CONDITIONS[^\S\n]+OF[^\S\n]+APPROVAL)"
)


def cut_older_exhibits(body: str) -> str:
    """An older motion's text (motion_body, before strip_running_headers) cut at the first Exhibit C / mitigation
    monitoring heading that follows its conditions heading (the heading find_sections takes: Conditions of Approval,
    else Exhibit A). Used for motions read with all_conditions(older_formats=True) only."""
    specs = {s.name: s.start for s in SECTION_SPECS}
    start = specs["conditions"].search(body) or specs["exhibit_a"].search(body)
    if start is None:
        return body
    end = _OLDER_CONDITIONS_END_RE.search(body, start.end())
    return body[: end.start()] if end else body


def parse_motion(text: str, meta: dict[str, Any], *, pages: int, sidecar: Path) -> Application:
    record = normalize_record(str(meta["record_number"]))
    url = str(meta.get("url") or PIM_URL.format(record=record))
    clean = strip_running_headers(motion_body(text))
    sections = find_sections(clean)
    extra: dict[str, Any] = {
        "source_kind": "motion",
        "pdf_pages": pages,
        "motion_url": url,
        "doc_name": meta.get("doc_name"),
    }
    hearing_meta = _date_from_iso(meta.get("hearing_date"))

    if not clean.strip():
        extra.update(
            {
                "motion_number": _motion_from_name(meta.get("doc_name")),
                "vote": None,
                "hearing_date": _iso(hearing_meta),
            }
        )
        return Application(
            id=f"datasf_planning:{record}",
            source=NAME,
            source_id=record,
            source_url=url,
            fetched_at=fetched_at_from(meta),
            raw_ref=str(sidecar),
            kind="cua",
            permit_type=PERMIT_TYPE,
            decided_at=hearing_meta,
            status="Planning Commission motion (no text layer)",
            decision_summary=None,
            extraction_confidence="low",
            extra=extra,
        )

    motion_no = (m.group(1) if (m := _MOTION_NO_RE.search(clean)) else None) or _motion_from_name(
        meta.get("doc_name")
    )
    hearing = date_from_match(_HEARING_DATE_RE.search(clean))
    flat = squash(clean)
    # the certification line, the ADOPTED: label and the hearing date occasionally disagree (typos):
    # take the date most of them agree on, preferring the ADOPTED: label, then the hearing date
    votes = [
        d
        for d in (
            date_from_match(_ADOPTED_LABEL_RE.search(flat)),
            hearing,
            date_from_match(_ADOPTED_CERT_RE.search(flat)),
        )
        if d
    ]
    adopted = max(votes, key=lambda d: (votes.count(d), -votes.index(d))) if votes else None
    filed = date_from_match(_FILED_RE.search(squash(clean)))
    decided = adopted or hearing or hearing_meta
    address = squash(m.group(1)) if (m := _ADDRESS_RE.search(clean)) else None
    parcel = f"{m.group(1)}/{m.group(2)}" if (m := _PARCEL_RE.search(clean)) else None
    zoning = _zoning(m.group(1)) if (m := _ZONING_RE.search(clean)) else None
    text_record = normalize_record(m.group(1)) if (m := _RECORD_LINE_RE.search(clean)) else None

    cond_section = sections.get("conditions", "")
    conds = operational_conditions(cond_section) if cond_section else []
    if cond_section and not _COND_ITEM_RE.search(cond_section):  # un-numbered conditions: sentence heuristics
        conds = [
            Condition(str(i + 1), "Condition", _clip(c), _categories(c) or ("other",))
            for i, c in enumerate(extract_conditions(squash(cond_section)))
        ]
    outcome = _outcome_from_decision(sections.get("decision", ""), clean, bool(cond_section))

    description = squash(sections.get("project_description", ""))
    description = re.sub(r"^[.:\s]+", "", description)[:1500]
    hour_texts = [c.text for c in conds if "hours" in c.categories]
    hours_close = closing_hour(hour_texts)
    mentioned = closing_hour(
        s
        for s in re.split(
            r"(?<=[.;])\s+(?=[A-Z0-9(])", squash(f"{description} {sections.get('findings', '')}")
        )
        if re.search(r"\bhours?\b|\boperat|\bopen\b|\bclos", s, re.I)
    )
    if hours_close is None:
        hours_close = mentioned
    elif mentioned and mentioned != hours_close:
        extra["hours_close_mentioned"] = mentioned

    opposition = opposition_from_comment(sections.get("public_comment"))
    minutes_item = meta.get("minutes_item") or {}
    if minutes_item.get("opposition") is True:
        opposition = True
        extra["hearing_speakers_opposed"] = minutes_item.get("oppose")
    elif opposition is None and minutes_item.get("opposition") is False:
        opposition = False

    ayes, nays, vote = parse_vote(sections.get("vote") or clean)
    use_types = classify_use_types(f"{description} {sections.get('exhibit_a', '')[:1200]}")

    confidence: Confidence
    if outcome == "unknown":
        confidence = "low"
    elif "decision" in sections and (cond_section or outcome == "denied") and motion_no:
        confidence = "high"
    else:
        confidence = "medium"
    if text_record and record_digits(text_record) != record_digits(record):
        extra["record_mismatch"] = text_record
        confidence = "low"

    sentence1 = (
        f"Planning Commission Motion No. {motion_no or 'unnumbered'} ({fmt_date(decided)}) "
        f"{_VERB_TEXT[outcome]} Conditional Use Authorization {record}"
        f"{' at ' + address if address else ''}" + (f" by a {vote} vote." if vote else ".")
    )
    summary = [sentence1]
    if conds:
        summary.append(f"Key operating conditions: {_summary_conditions(conds)}.")
    # No opposition sentence: the extracted flag failed validation (13 of 30 right), so it stays in `extra` and
    # `opposition_noted` only, never in text a report could quote.
    extra.update(
        {
            "motion_number": motion_no,
            "vote": vote,
            "ayes": ayes,
            "nays": nays,
            "hearing_date": _iso(hearing or hearing_meta),
            "zoning_text": zoning,
            "condition_categories": sorted({c for cond in conds for c in cond.categories}),
        }
    )
    if minutes_item:
        extra["minutes_url"] = minutes_item.get("minutes_url")
    status = (
        f"CPC Motion {motion_no}: {_VERB_TEXT[outcome]}"
        if motion_no
        else f"CPC motion: {_VERB_TEXT[outcome]}"
    )
    return Application(
        id=f"datasf_planning:{record}",
        source=NAME,
        source_id=record,
        source_url=url,
        fetched_at=fetched_at_from(meta),
        raw_ref=str(sidecar),
        kind="cua",
        permit_type=PERMIT_TYPE,
        use_types=use_types,
        description=description,
        address=address,
        parcel=parcel,
        zoning_district=zoning,
        status=status,
        outcome=outcome,
        filed_at=filed,
        decided_at=decided,
        hours_close=hours_close,
        late_night=is_late_night(hours_close),
        conditions=[c.text for c in conds],
        opposition_noted=opposition,
        decision_summary=" ".join(summary)[:1000],
        extraction_confidence=confidence,
        extra=extra,
    )


def _motion_from_name(name: Any) -> str | None:
    m = re.search(r"M-?\s?(\d{5})", str(name or ""))
    return m.group(1) if m else None


# =================================================================================================
# minutes parsing
# =================================================================================================

_REC = r"\d{4}[.-]\d{3,6}[A-Z][A-Z0-9]*(?:-\d{1,3})?"
_ITEM_RE = re.compile(rf"(?m)^[ \t]*(\d{{1,2}}[a-z]?)\.[ \t]+((?:{_REC})(?:[ \t]*(?:,|&|and)[ \t]*{_REC})*)")
_MINUTES_DATE_RE = re.compile(r"(?:Monday|Tuesday|Wednesday|Thursday|Friday),?\s+" + DATE_RE)
_SPEAKER_RE = re.compile(r"(?m)^[ \t]*(?:SPEAKERS:[ \t]*)?([+\-=])[ \t]+\S")
_PARCEL_MIN_RE = re.compile(
    r"Lots?\s+(\d{3}[A-Z]?)\s+(?:in|of)\s+Assessor[’'`]?s\s+Block\s+(\d{4}[A-Z]?)", re.I
)


@dataclass
class MinutesItem:
    item: str
    records: list[str]
    description: str
    address: str | None
    parcel: str | None
    speakers: str
    action: str
    outcome: Outcome
    ayes: list[str] = field(default_factory=list)
    nays: list[str] = field(default_factory=list)
    vote: str | None = None
    motion_number: str | None = None
    support: int = 0
    oppose: int = 0
    opposition: bool | None = None


def rejoin_split_words(text: str) -> str:
    """Undo pypdf's split capitals ('A pproved with Conditions' → 'Approved with Conditions')."""
    return re.sub(
        r"\b([ACDUW]) (?=(?:pproved|dopted|ontinued|isapproved|ithdrawn|pheld|ertified|ccepted)\b)",
        r"\1",
        text,
    )


def _minutes_outcome(action: str) -> Outcome:
    a = action.lower()
    if not a:
        return "unknown"
    if re.search(r"\bwithdr[ae]w", a):
        return "withdrawn"
    if re.search(r"intent to", a):
        return "pending"
    if re.search(r"\bdisapprov|\bden(?:ied|y)\b", a):
        return "denied"
    if re.search(r"\bapprov", a):
        return "approved_with_conditions"
    if re.search(r"\bcontinu|\btabled\b|\bno action\b", a):
        return "pending"
    return "unknown"


def parse_minutes_items(text: str) -> list[MinutesItem]:
    clean = strip_running_headers(text)
    heads = list(_ITEM_RE.finditer(clean))
    items: list[MinutesItem] = []
    by_no: dict[str, str] = {}
    for i, h in enumerate(heads):
        block = clean[h.end() : heads[i + 1].start() if i + 1 < len(heads) else len(clean)]
        item_no = h.group(1)
        records = [normalize_record(r) for r in re.findall(_REC, h.group(2))]
        head_end = re.search(r"Preliminary Recommendation|SPEAKERS:|ACTION:", block)
        desc_raw = block[: head_end.start()] if head_end else block[:1200]
        desc_raw = re.sub(
            r"^\s*\((?:[^()]|\([^()]*\))*\)", "", desc_raw.strip()
        )  # "(J. HORN: (628) 652-7366)"
        description = squash(desc_raw)[:1200]
        address = None
        if m := re.match(r"\s*([0-9][^–]{2,80}?)\s+[–-]\s", description):
            address = m.group(1).strip()
        parcel = f"{m.group(2)}/{m.group(1)}" if (m := _PARCEL_MIN_RE.search(description)) else None
        sm = re.search(r"SPEAKERS:(.*?)(?=^\s*ACTION:|\Z)", block, re.S | re.M)
        speakers = sm.group(0) if sm else ""
        if ref := re.search(r"Same as item\s+(\d{1,2}[a-z]?)", speakers, re.I):
            speakers = by_no.get(ref.group(1), speakers)
        by_no[item_no] = speakers
        am = re.search(
            r"ACTION:\s*(.*?)(?=^\s*(?:AYES|NAYS|ABSENT|RECUSED|MOTION|SPEAKERS)\s*:|^\s*\d{1,2}[a-z]?\.\s|\n\s*\n|\Z)",
            block,
            re.S | re.M,
        )
        action = rejoin_split_words(squash(am.group(1))) if am else ""
        vm = re.search(r"AYES\s*:.*?(?=^\s*MOTION\s*:|^\s*\d{1,2}[a-z]?\.\s|\n\s*\n|\Z)", block, re.S | re.M)
        ayes, nays, vote = parse_vote(vm.group(0)) if vm else ([], [], None)
        motion = m.group(1) if (m := re.search(r"MOTION\s*:\s*(\d{5})", block)) else None
        marks = [s.group(1) for s in _SPEAKER_RE.finditer(speakers)]
        support, oppose = marks.count("+"), marks.count("-")
        if oppose:
            opposition: bool | None = True
        elif re.search(r"SPEAKERS:\s*None\b", speakers, re.I) or marks:
            opposition = False
        else:
            opposition = None
        items.append(
            MinutesItem(
                item_no,
                records,
                description,
                address,
                parcel,
                speakers,
                action,
                _minutes_outcome(action),
                ayes,
                nays,
                vote,
                motion,
                support,
                oppose,
                opposition,
            )
        )
    return items


def minutes_hearing_date(text: str) -> dt.date | None:
    m = _MINUTES_DATE_RE.search(text[:3000])
    return date_from_match(m)


def parse_minutes(text: str, meta: dict[str, Any], *, pages: int, sidecar: Path) -> list[Application]:
    hearing = _date_from_iso(meta.get("hearing_date")) or minutes_hearing_date(text)
    url = str(meta.get("url"))
    skip = {normalize_record(r) for r in meta.get("skip_records", [])}
    out: list[Application] = []
    for it in parse_minutes_items(text):
        if it.outcome not in DECISIVE:
            continue
        for record in it.records:
            if "CUA" not in record or record in skip:
                continue
            confidence: Confidence = "medium" if it.action and it.vote else "low"
            vote_txt = f", vote {it.vote}" if it.vote else ""
            motion_txt = f", Motion No. {it.motion_number}" if it.motion_number else ""
            summary = (
                f"Planning Commission minutes ({fmt_date(hearing)}), item {it.item}: {record}"
                f"{' at ' + it.address if it.address else ''} — {it.action}{vote_txt}{motion_txt}."
            )
            hours = closing_hour([it.action])
            out.append(
                Application(
                    id=f"datasf_planning:{record}",
                    source=NAME,
                    source_id=record,
                    source_url=url,
                    fetched_at=fetched_at_from(meta),
                    raw_ref=str(sidecar),
                    kind="cua",
                    permit_type=PERMIT_TYPE,
                    use_types=classify_use_types(it.description),
                    description=it.description,
                    address=it.address,
                    parcel=it.parcel,
                    status=f"CPC hearing {_iso(hearing)}: {it.action}"[:200],
                    outcome=it.outcome,
                    decided_at=hearing,
                    hours_close=hours,
                    late_night=is_late_night(hours),
                    conditions=[_clip(c) for c in extract_conditions(it.action)],
                    opposition_noted=it.opposition,
                    decision_summary=summary[:1000],
                    extraction_confidence=confidence,
                    extra={
                        "source_kind": "minutes",
                        "motion_number": it.motion_number,
                        "vote": it.vote,
                        "hearing_date": _iso(hearing),
                        "pdf_pages": pages,
                        "item": it.item,
                        "minutes_url": url,
                        "speakers_support": it.support,
                        "speakers_oppose": it.oppose,
                    },
                )
            )
    return out


# =================================================================================================
# parse (pure: sidecar + cached PDF → SourceBatch)
# =================================================================================================


def parse(path: Path) -> SourceBatch:
    meta, data = read_raw(path)
    rel = (data or {}).get("pdf") or meta.get("pdf")
    pdf_file = path.parent / str(rel) if rel else None
    if pdf_file is None or not pdf_file.exists():
        log.warning("%s: cached PDF %s missing; nothing to parse", path.name, rel)
        return SourceBatch()
    kind = meta.get("source_kind", "motion")
    if kind == "minutes":
        doc = read_pdf(pdf_file.read_bytes(), max_pages=MINUTES_MAX_PAGES)
    else:
        doc = read_pdf(pdf_file.read_bytes(), max_pages=MOTION_MAX_PAGES, stop=is_plan_page)
    if kind == "minutes":
        return SourceBatch(applications=parse_minutes(doc.text, meta, pages=doc.pages, sidecar=path))
    return SourceBatch(applications=[parse_motion(doc.text, meta, pages=doc.pages, sidecar=path)])


# =================================================================================================
# fetch
# =================================================================================================


class BudgetExhaustedError(Exception):
    pass


@dataclass
class Budget:
    max_docs: int
    max_requests: int
    docs: int = 0
    requests: int = 0

    def take_request(self) -> None:
        if self.requests >= self.max_requests:
            raise BudgetExhaustedError("request budget")
        self.requests += 1

    @property
    def docs_left(self) -> int:
        return self.max_docs - self.docs


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, default)))
    except ValueError:
        return default


def _url_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:24]


class Fetcher:
    def __init__(self, client: httpx.AsyncClient, raw_dir: Path, since: dt.date) -> None:
        self.client = client
        self.raw_dir = raw_dir
        self.folder = raw_dir / NAME
        self.pdf_dir = self.folder / "pdf"
        self.lookup_dir = self.folder / "lookups"
        for d in (self.folder, self.pdf_dir, self.lookup_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.since = since
        self.today = dt.date.today()
        self.limiter = RateLimiter(RATE_LIMIT)
        self.budget = Budget(
            _env_int("PLANNING_HEARINGS_MAX_DOCS", DEFAULT_MAX_DOCS),
            _env_int("PLANNING_HEARINGS_MAX_REQUESTS", DEFAULT_MAX_REQUESTS),
        )
        self.stats: dict[str, int] = {
            "list_pages": 0,
            "minutes_new": 0,
            "minutes_missing": 0,
            "lookups": 0,
            "motions_new": 0,
            "no_motion": 0,
            "pdf_cache_hits": 0,
            "errors": 0,
        }
        self._load_existing()

    # ---- state derived from immutable raw files -------------------------------------------------
    def _load_existing(self) -> None:
        self.motion_records: set[str] = set()
        self.minutes_by_date: dict[str, Path] = {}
        self.minutes_items: dict[str, dict[str, Any]] = {}  # record → latest decisive minutes item
        for p in sorted(self.folder.glob("*.json")):
            try:
                meta, data = read_raw(p)
            except (OSError, ValueError, KeyError):
                continue
            if meta.get("source_kind") == "motion" and meta.get("record_number"):
                self.motion_records.add(normalize_record(meta["record_number"]))
            elif meta.get("source_kind") == "minutes" and meta.get("hearing_date"):
                self.minutes_by_date[meta["hearing_date"]] = p
                for item in (data or {}).get("items", []):
                    self._remember_item(item)
        self.negative: dict[str, dt.datetime] = {}
        for p in self.lookup_dir.glob("*.json"):
            try:
                meta, _ = read_raw(p)
            except (OSError, ValueError, KeyError):
                continue
            if meta.get("found") is False and meta.get("key"):
                when = fetched_at_from(meta)
                if meta["key"] not in self.negative or when > self.negative[meta["key"]]:
                    self.negative[meta["key"]] = when

    def _remember_item(self, item: dict[str, Any]) -> None:
        for rec in item.get("records", []):
            if "CUA" in rec and item.get("outcome") in DECISIVE:
                prev = self.minutes_items.get(rec)
                if prev is None or str(item.get("hearing_date")) >= str(prev.get("hearing_date")):
                    self.minutes_items[rec] = item

    def _recently_negative(self, key: str, decided: dt.date | None) -> bool:
        when = self.negative.get(key)
        if when is None:
            return False
        recent_case = decided is not None and (self.today - decided).days < 90
        return (dt.datetime.now(dt.UTC) - when).days < (7 if recent_case else 60)

    def _save_lookup(self, key: str, url: str, found: bool, payload: Any, **meta: Any) -> None:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", key)
        write_raw(
            raw_path(self.folder, "lookups", safe), payload, {"url": url, "key": key, "found": found, **meta}
        )
        if not found:
            self.negative[key] = dt.datetime.now(dt.UTC)

    # ---- HTTP -----------------------------------------------------------------------------------
    async def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        self.budget.take_request()
        await self.limiter.wait()
        return await self.client.get(url, params=params)

    async def _download_pdf(self, url: str) -> tuple[Path, bool] | None:
        """Cached PDF for url (downloading when absent). Returns (path, downloaded_now) or None."""
        path = self.pdf_dir / f"{_url_key(url)}.pdf"
        if path.exists() and path.stat().st_size > 0:
            self.stats["pdf_cache_hits"] += 1
            return path, False
        if self.budget.docs_left <= 0:
            raise BudgetExhaustedError("document budget")
        resp = await self._get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        body = resp.content
        if not body.startswith(b"%PDF"):
            log.warning("not a PDF at %s (%s, %d bytes)", url, resp.headers.get("content-type"), len(body))
            return None
        if len(body) > MAX_PDF_BYTES:
            log.warning("skipping oversized PDF %s (%d bytes)", url, len(body))
            return None
        tmp = path.with_suffix(".part")
        tmp.write_bytes(body)
        tmp.replace(path)
        self.budget.docs += 1
        return path, True

    # ---- minutes sweep (calendar → minutes PDFs) --------------------------------------------------
    async def _hearing_dates(self) -> AsyncIterator[dt.date]:
        """Yield regular Planning Commission hearing dates, newest first, back to `since`."""
        pat = re.compile(
            r"<h3>\s*(?P<mon>[A-Z][a-z]+)\s+(?P<year>\d{4})\s*</h3>"
            r'|about="(?P<slug>/event/[^"]+)"[\s\S]*?<div class="month">(?P<m>[A-Za-z]+)</div>\s*<div class="day">(?P<d>\d{1,2})</div>'
        )
        for page in range(60):
            resp = await self._get(
                CPC_LIST_URL,
                params={
                    "field_date_range_value": 2,
                    "field_date_range_value_8": "All",
                    "sort_by": "field_date_range_value",
                    "sort_order": "DESC",
                    "page": page,
                },
            )
            self.stats["list_pages"] += 1
            resp.raise_for_status()
            year: int | None = None
            found = 0
            for m in pat.finditer(resp.text):
                if m.group("year"):
                    year = int(m.group("year"))
                    continue
                slug = m.group("slug")
                month = _MONTHS.get(m.group("m")[:3].lower())
                if year is None or month is None:
                    continue
                found += 1
                if not re.fullmatch(r"/event/planning-commission(?:-\d+)?", slug) or "cancel" in slug:
                    continue
                try:
                    day = dt.date(year, month, int(m.group("d")))
                except ValueError:
                    continue
                if day < self.since:
                    return
                yield day
            if not found:
                return

    async def sweep_minutes(self, max_new: int) -> list[Path]:
        out: list[Path] = []
        new = 0
        async for day in self._hearing_dates():
            if new >= max_new:
                break
            ymd = day.strftime("%Y%m%d")
            if day.isoformat() in self.minutes_by_date or (self.today - day).days < 10:
                continue
            key = f"minutes-{ymd}"
            if self._recently_negative(key, day):
                continue
            got = None
            for tmpl in MINUTES_URLS:
                url = tmpl.format(ymd=ymd)
                got = await self._download_pdf(url)
                if got:
                    break
            if not got:
                self.stats["minutes_missing"] += 1
                self._save_lookup(
                    key, MINUTES_URLS[0].format(ymd=ymd), False, None, hearing_date=day.isoformat()
                )
                continue
            pdf, downloaded = got
            new += int(downloaded)
            self.stats["minutes_new"] += int(downloaded)
            out.append(self._write_minutes_sidecar(url, pdf, day))
        return out

    def _write_minutes_sidecar(self, url: str, pdf: Path, day: dt.date) -> Path:
        doc = read_pdf(pdf.read_bytes(), max_pages=MINUTES_MAX_PAGES)
        items: list[dict[str, Any]] = []
        for it in parse_minutes_items(doc.text):
            row: dict[str, Any] = {
                "item": it.item,
                "records": it.records,
                "outcome": it.outcome,
                "action": it.action[:300],
                "vote": it.vote,
                "motion_number": it.motion_number,
                "hearing_date": day.isoformat(),
                "opposition": it.opposition,
                "oppose": it.oppose,
                "support": it.support,
                "minutes_url": url,
            }
            items.append(row)
            self._remember_item(row)
        skip = sorted(
            {r for it in parse_minutes_items(doc.text) for r in it.records if r in self.motion_records}
        )
        path = raw_path(self.raw_dir, NAME, f"minutes-{day:%Y%m%d}")
        write_raw(
            path,
            {"pdf": f"pdf/{pdf.name}", "items": items},
            {
                "url": url,
                "source_kind": "minutes",
                "hearing_date": day.isoformat(),
                "record_number": None,
                "pdf": f"pdf/{pdf.name}",
                "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                "pdf_pages": doc.pages,
                "skip_records": skip,
            },
        )
        self.minutes_by_date[day.isoformat()] = path
        return path

    # ---- candidates -------------------------------------------------------------------------------
    def planning_candidates(self) -> dict[str, dt.date]:
        """CUA record numbers with decision dates from saved Planning dataset raw pages (when present)."""
        folder = self.raw_dir / "datasf_planning"
        out: dict[str, dt.date] = {}
        if not folder.is_dir():
            return out
        for p in sorted(folder.rglob("*.json")):
            try:
                _, data = read_raw(p)
            except (OSError, ValueError, KeyError):
                continue
            rows = (
                data
                if isinstance(data, list)
                else (data or {}).get("rows", [])
                if isinstance(data, dict)
                else []
            )
            for row in rows:
                if not isinstance(row, dict):
                    continue
                rec = (
                    row.get("record_id")
                    or row.get("record_number")
                    or row.get("record_no")
                    or row.get("case_no")
                )
                if not isinstance(rec, str) or "CUA" not in rec.upper():
                    continue
                status = str(row.get("record_status") or row.get("status") or "").lower()
                if any(w in status for w in ("withdraw", "cancel", "under review", "accepted", "open")):
                    continue
                decided = None
                for k in ("close_date", "date_closed", "closed_date", "decision_date", "approved_date"):
                    decided = decided or _date_from_iso(row.get(k))
                if decided and decided >= self.since:
                    rec = normalize_record(rec)
                    out[rec] = max(decided, out.get(rec, decided))
        return out

    def candidates(self) -> list[tuple[str, dt.date | None]]:
        merged: dict[str, dt.date | None] = dict(self.planning_candidates())
        for rec, item in self.minutes_items.items():
            d = _date_from_iso(item.get("hearing_date"))
            if (
                d
                and d >= self.since
                and item.get("outcome") in {"approved_with_conditions", "approved", "denied"}
            ):
                merged[rec] = max(d, merged.get(rec) or d)
        todo = [(r, d) for r, d in merged.items() if r not in self.motion_records]
        todo.sort(key=lambda t: (t[1] or dt.date.min, t[0]), reverse=True)
        return todo

    # ---- motions ----------------------------------------------------------------------------------
    @staticmethod
    def pick_motion(listing: Any) -> dict[str, Any] | None:
        if not isinstance(listing, dict):
            return None
        docs = [d for d in listing.values() if isinstance(d, dict)]
        motions = [
            d
            for d in docs
            if d.get("ClassName") == MOTION_CLASS
            and str(d.get("Name", "")).lower().endswith(".pdf")
            and d.get("docLink")
            and "draft" not in str(d.get("Name", "")).lower()
        ]
        if not motions:
            # Older motions moved in the July 2016 migration are sometimes filed under another class (e.g.
            # "Application") with the motion number as the file name ("19183.pdf.pdf"); take one of those.
            motions = [
                d
                for d in docs
                if re.match(r"^M?-?\s?\d{5}\.pdf(\.pdf)?$", str(d.get("Name", "")).strip(), re.IGNORECASE)
                and d.get("docLink")
            ]
        if not motions:
            return None
        motions.sort(
            key=lambda d: (
                bool(re.match(r"^M-?\s?\d{5}", str(d.get("Name", "")))),
                str(d.get("LastModified", "")),
            )
        )
        return motions[-1]

    async def fetch_motion(self, record: str, decided: dt.date | None) -> Path | None:
        key = f"mfiles-{record}"
        if self._recently_negative(key, decided):
            return None
        resp = await self._get(MFILES_URL, params={"search": record, "isPRJ": "", "kids": ""})
        self.stats["lookups"] += 1
        resp.raise_for_status()
        try:
            listing = json.loads(resp.text) if resp.text.strip() else {}
        except json.JSONDecodeError:
            listing = None
        doc = self.pick_motion(listing)
        if doc is None:
            self.stats["no_motion"] += 1
            self._save_lookup(
                key,
                str(resp.url),
                False,
                listing if listing is not None else resp.text[:5000],
                record_number=record,
            )
            return None
        self._save_lookup(key, str(resp.url), True, listing, record_number=record)
        url = str(doc["docLink"])
        got = await self._download_pdf(url)
        if not got:
            return None
        pdf, downloaded = got
        self.stats["motions_new"] += int(downloaded)
        item = self.minutes_items.get(record)
        hearing = (item or {}).get("hearing_date") or _iso(decided)
        path = raw_path(self.raw_dir, NAME, f"{re.sub(r'[^A-Za-z0-9.-]', '_', record)}-motion")
        write_raw(
            path,
            {"pdf": f"pdf/{pdf.name}"},
            {
                "url": url,
                "record_number": record,
                "hearing_date": hearing,
                "source_kind": "motion",
                "doc_name": doc.get("Name"),
                "doc_class": doc.get("ClassName"),
                "doc_modified": doc.get("LastModified"),
                "lookup_url": str(resp.url),
                "pim_url": PIM_URL.format(record=record),
                "pdf": f"pdf/{pdf.name}",
                "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                "minutes_item": item,
            },
        )
        self.motion_records.add(record)
        return path

    # ---- orchestration ----------------------------------------------------------------------------
    async def run(self) -> list[Path]:
        minutes: list[Path] = []
        motions: list[Path] = []
        try:
            share = max(1, self.budget.max_docs // 3) if self.budget.max_docs else 0
            try:
                minutes = await self.sweep_minutes(share)
            except (httpx.HTTPError, BudgetExhaustedError) as exc:
                if isinstance(exc, httpx.HTTPError):
                    self.stats["errors"] += 1
                    log.warning("minutes sweep stopped: %s", exc)
                else:
                    raise
            for record, decided in self.candidates():
                if self.budget.docs_left <= 0:
                    break
                try:
                    p = await self.fetch_motion(record, decided)
                except httpx.HTTPError as exc:
                    self.stats["errors"] += 1
                    log.warning("motion lookup failed for %s: %s", record, exc)
                    continue
                if p:
                    motions.append(p)
        except BudgetExhaustedError as exc:
            log.info("sf_planning_hearings: %s exhausted; the next nightly run continues the backlog", exc)
        if os.environ.get("PLANNING_HEARINGS_REEMIT") == "1":  # rebuild a store from every cached sidecar
            for p in sorted(self.folder.glob("*.json")):
                kind = read_raw(p)[0].get("source_kind")
                if p not in minutes and p not in motions:
                    (minutes if kind == "minutes" else motions).append(p)
        minutes.sort(key=lambda p: str(read_raw(p)[0].get("hearing_date")))
        log.info(
            "sf_planning_hearings fetch: %s, docs=%d/%d requests=%d/%d, since=%s",
            self.stats,
            self.budget.docs,
            self.budget.max_docs,
            self.budget.requests,
            self.budget.max_requests,
            self.since,
        )
        return minutes + motions


async def fetch(client: httpx.AsyncClient, raw_dir: Path, since: dt.date | None) -> list[Path]:
    today = dt.date.today()
    start = since or today.replace(year=today.year - DEFAULT_WINDOW_YEARS)
    return await Fetcher(client, raw_dir, start).run()


SOURCE = SourceSpec(
    name=NAME,
    description="Planning Commission CUA motions (PIM/M-Files decision documents) + hearing minutes, PDF-extracted",
    fetch=fetch,
    parse=parse,
    rate_limit_per_second=RATE_LIMIT,
    source_home="https://sfplanning.org/hearings-cpc-grid",
)

__all__ = [
    "SOURCE",
    "closing_hour",
    "operational_conditions",
    "opposition_from_comment",
    "parse",
    "parse_minutes_items",
    "parse_vote",
]
