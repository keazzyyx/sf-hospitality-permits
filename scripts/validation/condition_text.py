"""Text clean-up and an OCR-quality check for the conditions search page (used by build_conditions_index.py).

Many older motions are scanned. Their text comes from OCR, and some of it is junk ("tvzvzv_s~" for
www.sf-planning.org). Newer motions have a real text layer, but the PDF reader sometimes splits words
("comme ncing"). This module:

- clean():   removes page furniture that leaked into a condition (the "For information about compliance,
             contact ..." line, the "SAN FRANCISCO PLANNING DEPARTMENT" page footer, section headings in
             capitals) and joins words split by a stray space;
- Vocabulary.bad_tokens(): lists the words that do not read as English or as a word used in other motions;
- hard_tokens(): stray symbols, letters mixed with digits and furniture left behind; one is enough to flag;
- garbled(): True when a condition has a hard piece, or too many unreadable words to read cleanly.

No model, no network. The word list is /usr/share/dict/words when it exists, plus every word that appears in
at least three different motions.
"""

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from collections.abc import Collection, Iterable
from pathlib import Path

DICT = Path("/usr/share/dict/words")

# a condition is "garbled" at this many unreadable words (or this share of its words)
GARBLED_MIN_BAD = 2
GARBLED_SHARE = 0.08

_WORD = re.compile(r"[A-Za-z]+")
_TOKEN = re.compile(r"\S+")
_ODD = re.compile(r"[~_|\\{}^`•«»¬►]")
# letters and digits mixed inside one word: "Plar2rtirtg", "10:OOam", "9Q87"
_MIX = re.compile(
    r"[A-Za-z][0-9]+[A-Za-z]|[0-9][A-NP-Za-z][0-9]|\d:?[O]{1,2}(?:am|pm)?\b|[0-9][Oo][0-9]", re.I
)
_PUNCT = ".,;:()[]\"'’‘“”-—–!?*"
_SUFFIXES = (
    ("ies", "y"), ("es", ""), ("s", ""), ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e"), ("ly", ""),
    ("er", ""), ("ers", ""), ("ment", ""), ("ments", ""), ("ation", "e"), ("ations", "e"), ("ion", ""),
    ("ions", ""), ("al", ""), ("ity", ""), ("ive", "e"), ("ability", "able"),
)  # fmt: skip

# "For information about compliance, contact Code Enforcement, Planning Department at 415-575-6863,
# www.sf-planning.org" closes most conditions. The reader already drops the clean copies; what is left are
# OCR variants ("For informatiofi about compliance, contact Code Efiforcement, ..."). The pattern is loose
# on spelling and runs to the end of the condition, but only when what follows is short (a contact line).
_CONTACT = re.compile(
    r"\s*\bF\S{1,3}\s+(?:further\s+)?(?:\S{4,14}|i\s?n\s?f\s?o\s?r\s?m\s?a\s?t\s?i\s?o\s?n)\s+\S{3,7}\s+"
    r"(?:\S{0,4}ompl|\S{0,3}o\s?m\s?p\s?l).*$",
    re.I | re.S,
)  # "info rmation", "comp liance": the PDF reader sometimes splits a word
# Motions decided before 2019 (older=True in clean()): "about" split too ("abou t", "a bout"). Vocabulary.rejoin
# joins the split only after the contact line is looked for, so the line was missed, the trims at the end took off
# only its phone number and web address, and its opening ("For information about compliance, contact") was left as
# furniture (2012.0764C 4, flagged unreadable; 2012.0926C 2 and others shown with it). Not used on 2019+ motions,
# so their published conditions do not change.
# Also "c ompliance" (a space after its first letter: 2012.0525C 4, 2013.0290C 7), which neither "\S{0,4}ompl" nor
# "\S{0,3}o\s?m\s?p\s?l" reaches.
_CONTACT_OLDER = re.compile(
    _CONTACT.pattern.replace(r"\s+\S{3,7}\s+", r"\s+(?:\S{3,7}|a\s?b\s?o\s?u\s?t)\s+", 1).replace(
        r"(?:\S{0,4}ompl|", r"(?:c\s+ompl|\S{0,4}ompl|", 1
    ),
    _CONTACT.flags,
)
assert _CONTACT_OLDER.pattern != _CONTACT.pattern and r"c\s+ompl" in _CONTACT_OLDER.pattern
# Motions decided before 2019: a contact line laid out in a column beside the condition's last lines, which the
# reader interleaved with them: "... in compliance with the For information about Department of Public Works Streets
# and Sidewalk Maintenance Standards. compliance, contact Bureau of Street Use and Mapping, ..." (2010.0912C 18).
# Only the exact opening "For information about" followed (within 200 characters) by "compliance, contact" and a
# short tail; the condition's own words between the two are kept.
_CONTACT_SPLIT_OLDER = re.compile(
    r"\s*\bFor\s+information\s+about\s+(?!c\s?o\s?m\s?p)(\S.{0,200}?)\s+compliance,\s+contact\b.*$", re.S
)
_CONTACT_MAX = 300
# the end of a contact line whose start the reader dropped: "Works at 628.271.2000, www.sfpublicworks.org"
_CONTACT_TAIL = re.compile(
    r"\s+(?:or\s+the\s+)?(?:[A-Z][\w&’'-]*,?\s+|(?:of|and|the)\s+){0,10}at\s+[\d(][\d().\-\s]{9,16},?\s*$"
)
# the running header "Motion No. 20380 RECORD NO. 2018-013462CUA February 14, 2019 3995 Alemany Boulevard"
_RUNNING = re.compile(
    r"\s*Motion\s+No\.?\s*\d{4,5}\s+RECORD\s+NO\.?\s*[\w.\-]+\s+[A-Z][a-z]+\.?\s+\d{1,2},\s*\d{4}(?:\s+[^.]{0,40}$)?",
    re.I,
)
# a two-part section heading inside a condition: the reader missed the next condition's number, so what follows
# the heading belongs to another condition and is cut off
_MID_HEADING = re.compile(
    r"\s+[^\w\s]*\s*(?:MONITORING\s*[-•–]?\s*[-•–]?AFTER\s+ENTITLEMENT|DESIGN\s*[-–—]*\s*COMPLIANCE\s+AT\s+PLAN\s+STAGE)"
    r"\b.*$",
    re.S,
)
# a street address as the running header prints it: "4018 24th Street", "447 Broadway"
_ADDR = r"\d{1,5}\s+(?:\S{1,12}\s+)?(?:Street|STREET|Avenue|AVENUE|Boulevard|BOULEVARD|Broadway|BROADWAY)\b"
# the page footer "SAN FRANCISCO PLANNING DEPARTMENT" (with or without the page number), as OCR prints it
_FOOTER = re.compile(
    r"\s*(?:SAN\s*FRAN\S*\s*(?:~\s*)?\d{0,3}\s*)?\bP\s?L[A-Z0-9~ ]{2,8}\s+DEP[A-Za-z0-9~]{2,9}(?:\s+\d{1,3}\b)?"
    # "SAN FRANCISCO 13P LANNING DEPANTMENT": the page number runs into the "P"
    r"|\s*\bSAN\s*[fF][A-Za-z~]{4,10}\s*~?\s*\d{0,3}\s*P\s?L[A4]NNING(?:\s+DEP[A-Za-z0-9~]{2,9})?(?:\s+\d{1,3}\b)?"
    # "SAN FRANCISCO 5 January 24, 2019 4018 24th Street", "SAN fRANCISC~ 6": the footer's page number, then the
    # running header's date and address when the reader kept them
    r"|\s*\bS[A-Za-z]N\s*[fF][A-Za-z~]{4,10}\s*~?(?:\s+\d{1,3}\b(?:\s+[A-Z][a-z]+\.?\s+\d{1,2},\s*\d{4})?(?:\s+"
    + _ADDR
    + ")?"
    r"|\s+" + _ADDR + ")"
    r"|\s*\bS[A-Za-z]N\s*FRAN[A-Z]*(?:\s+\d{1,3}\b)?(?=\s*(?:$|P\s?L|[~'`]|[a-z]))"
    r"|\s*\bSAN\s*[fF][A-Za-z~]*[~fF][A-Za-z~]*(?=\s*$)"  # an OCR'd "SAN ffiANCISCO" left at the very end
    r"|\s*\S{0,3}P\s?L[A4]NNING(?:\s+DEP[A-Za-z0-9~]{2,9})?(?:\s+\d{1,3}\b)?(?=\s*$)"  # "~ gP LANNING" at the end
)  # capitals only: "Planning Department" in a sentence is real text
# A mangled web address at the very end of a condition, ending in ".or", ". org" or "orQ" ("www.s - Tannin .or ,",
# "unow. L a n n i ng. org", "d, w.or ."): at most nine short pieces, starting after a full stop or comma.
# A piece of a mangled web address: short, dotted, or "...lanning"-like; never a number, "to" or "a.m."/"p.m."
_NOT_TEXT = r"(?![AaPp]\.\s?[Mm]\.)(?!\d+\b)(?!to\b)"
_JUNK_PIECE = rf"{_NOT_TEXT}(?:[^\s]{{1,3}}|\S*[.~\-/:„]\S*|\S*(?:lann|ann|nin)\S*)"
# the first piece must look like the start of a web address ("www.s", "sf-planning.", "unow.", "-", "ing.", "d,")
_URL_START = (
    rf"{_NOT_TEXT}(?:\S{{1,2}}[.,]?|w\S*|z\S*|sf\S*|s\S{{0,2}}f\S*|unow\S*|mah\S*|\S*lann\S*|\S*ing\.)"
)
_URL_END = re.compile(
    rf"(?<=[.,])\s+{_URL_START}(?:\s+{_JUNK_PIECE}){{0,8}}?(?:\.\s?|\s\.)o\s?r[gQ~s]?\b[\s.,]*$"
    rf"|(?<=[.,])\s+{_URL_START}(?:\s+{_JUNK_PIECE}){{0,8}}?\s*\S*\bor[Q~][\s.,]*$"
    r"|(?<=\.)\s+o\s?r[gQ~]?\.?\s*$"  # "approved. org"
    r"|(?<=[.,])\s+www\S*(?:\s+\S{1,10}){0,2}\s+org\.?\s*$"  # "www.sf planning org"
    r"|(?<=\.)\s+For(?:\s+inf\S*(?:\s+about)?)?\s*$"  # the opening of a contact line cut off by the page
)
# a mangled web address inside a condition, from its mangled start to its ".or"/".org" end, at most four tokens:
# "wzuzu.s -moh.or .", "mah://s d w.or ."
_URL_MID = re.compile(r"\s*\b(?:w[zuv]{3,}\w*|unow|mah:)\S*(?:\s+\S{1,12}){0,3}?\s*\S*\.\s?or[gQ~]?\b\s*\.?")
# the running header's address left at the very end, after a web address or stray symbols: "~ O 3372 19"' Street"
_ADDR_TAIL = re.compile(
    r"(?<=[.~O])\s+\d{1,5}\s+(?:\S{1,12}\s+)?(?:Street|STREET|Avenue|AVENUE|Boulevard|BOULEVARD|Broadway|BROADWAY)\s*$"
)
# leftovers that are never real condition text: page-footer words, web-address pieces, the contact line's opening
_HARD_FURNITURE = re.compile(
    r"\bP\s?L[A4]NNING\b|\bLANNING\b|\bDEPA\S*TMENT\b|\bSAN\s*F\S*\s+\d{1,3}\b|\bSAN\s*[fF]\S*[~]"
    r"|\b(?:w[zuv]{3,}\w*|unow|mah:)\S*|\bwww\.\S*\s+-\s|\S\.or\b|\s\.or\b|\bor[Q~]"
    r"|\bFor\s+\S+\s+\S*bout\s+\S*ompl\S*,?\s*cont\S*\s*$"
)
# Exhibit A section headings in capitals that belong to the next block, left at the end of a condition, with
# the next condition's title when the reader missed its number ("MONITORING - AFTER ENTITLEMENT Enforcement.")
_HEADING = re.compile(
    r"\s+(?:[^\w\s.]*\s*)?(?:MONITORING\s*[-•–]?\s*[-•–]?AFTER\s+ENTITLEMENT"
    r"|DESIGN\s*[-–—]*\s*COMPLIANCE\s+AT\s+PLAN\s+STAGE"
    r"|OPERATION|PERFORMANCE|PARKING\s+AND\s+TRAFFIC|PROVISIONS|AUTHORIZATION|RECORDATION\s+OF\s+CONDITIONS"
    r"[A-Z ]*|SEVERABILITY|CHANGES\s+AND\s+MODIFICATIONS|PRINTING\s+OF\s+CONDITIONS[A-Z ]*|DESIGN)"
    r"(?:\s+\d{0,2}\.?\s*[A-Z][a-z]+(?:\s+[A-Za-z][a-z]+){0,4}\.)?[\W\d_]*$"
)
# a web address mangled by OCR: "wzvw.s~planning.org", "zuzuzu_s~_", "s~plann", "or~"
_URLISH = re.compile(
    r"www|wzv|zuz|wwz|zvz|zuw|zoz|s~|s,~|\.or|or~|\.org|http|htt~|lann|plan|moh\.|\.sf", re.I
)
# any web address, clean or not (only removed at the very end of a condition, where it is a contact line)
_WEB = re.compile(r"www|\.org|\.o\S?g\b|\.gov|\.com|ing\.o|^\W*[wzuvnito]{3,6}\.s", re.I)
_TAIL_WORDS = {"SAN", "FRANCISCO", "DESIGN", "PLANNING", "DEPARTMENT", "MONITORING", "OPERATION"}


def _url_junk(token: str) -> bool:
    """A web address that OCR mangled: web-address letters plus a stray symbol, or a "www."-style stub."""
    return bool(_URLISH.search(token)) and (
        bool(_ODD.search(token)) or bool(re.fullmatch(r"\W*[wzuvn]{3,6}[.,]\W*", token))
    )


def _junk_tail(token: str) -> bool:
    """A trailing token that cannot be the real last word: stray symbols, a lone letter, a bare page number,
    a web address (the end of a contact line) or a running-footer word."""
    core = _core(token)
    if len(token) == 1 and token.isalpha():
        return True
    if re.fullmatch(r"[\W\d_]{1,6}", token):
        return not re.fullmatch(r"[\d.,;:)]+", token) or bool(re.fullmatch(r"\d{1,3}", token))
    if _WEB.search(token) or _url_junk(token) or core in _TAIL_WORDS:
        return True
    odd = len(_ODD.findall(token))
    n_letters = sum(ch.isalpha() for ch in token)
    return bool(odd and (n_letters <= 3 or odd >= 2)) or bool(
        len(core) <= 3 and re.search(r"[A-Za-z]\d|\d[A-Za-z]", core)
    )


def _fix_times(text: str) -> str:
    """OCR reads the zeros in "7:00AM" as the letter O: "7:OOAM"."""
    return re.sub(
        r"(?<=\d)(:?)[O0]{2}(?=\s*(?:[ap]\.?\s?m\b|[-–]|\s|$))", lambda m: m.group(1) + "00", text, flags=re.I
    )


def _core(token: str) -> str:
    return token.strip(_PUNCT)


class Vocabulary:
    """Words that count as readable: the system word list (with common endings removed) plus every word used in
    at least three motions."""

    def __init__(self, texts_by_motion: Iterable[tuple[str, str]]):
        self.words: set[str] = set()
        if DICT.exists():
            self.words = {
                w.strip().lower() for w in DICT.read_text(errors="ignore").splitlines() if w.strip()
            }
        seen: dict[str, set[str]] = defaultdict(set)
        for motion, text in texts_by_motion:
            for w in {x.lower() for x in _WORD.findall(text)}:
                seen[w].add(motion)
        # a word OCR or the reader cut short ("plannin", "departmen") also repeats across motions: it does not
        # count when adding one or two letters gives a word used in more motions
        self.common = {
            w for w, motions in seen.items()
            if len(motions) >= 3 and (w in self.words or not any(
                len(seen.get(longer, ())) > len(motions)
                for longer in (k for k in seen if len(k) in (len(w) + 1, len(w) + 2) and k.startswith(w))
            ))
        }  # fmt: skip

    def known(self, word: str) -> bool:
        w = word.lower()
        if w in self.words or w in self.common:
            return True
        return any(
            w.endswith(s) and len(w) > len(s) + 2 and w[: -len(s)] + r in self.words for s, r in _SUFFIXES
        )

    def bad_tokens(self, text: str) -> list[str]:
        """Tokens that do not read: stray symbols, letters mixed with digits, or a lower-case word of four or
        more letters that is neither in the word list nor used in other motions. Capitalised words are skipped
        (street and business names); so are short words."""
        bad = []
        tokens = _TOKEN.findall(text)
        caps = [t for t in tokens if re.fullmatch(r"[A-Z]{3,}", _core(t))]
        if len(caps) >= 10 and len(caps) / max(1, len(tokens)) > 0.25:  # plan-sheet labels, not prose
            bad.extend(caps)
        for token in tokens:
            core = _core(token)
            if not core:
                continue
            if _ODD.search(core) or _MIX.search(core):
                bad.append(token)
                continue
            if re.fullmatch(r"[A-Za-z]+(?:[-’'][A-Za-z]+)*", core):
                for part in re.split(r"[-’']", core):
                    if len(part) >= 4 and part[0].islower() and not self.known(part):
                        bad.append(token)
                        break
                    # a capitalised word with an upper-case letter inside it ("DEPAiiTMENT", "FRaNascoP")
                    if len(part) >= 4 and re.search(r"[a-z][A-Z]|[A-Z]{2}[a-z]+[A-Z]", part):
                        bad.append(token)
                        break
        return bad

    def rejoin(self, text: str) -> str:
        """Join a word the PDF reader split with a space ("comme ncing" -> "commencing") when the halves do not
        read on their own and the joined word does."""
        tokens = text.split(" ")
        out: list[str] = []
        i = 0
        while i < len(tokens):
            a = tokens[i]
            if i + 1 < len(tokens):
                b = tokens[i + 1]
                ca, cb = a.lstrip(_PUNCT), b.rstrip(_PUNCT)
                if (
                    ca.isalpha() and cb.isalpha() and cb.islower() and a == a.rstrip(_PUNCT)
                    and (not self.known(ca) or not self.known(cb) or len(cb) == 1)
                    and self.known(ca + cb) and len(ca + cb) >= 5
                    and not (self.known(ca) and len(ca) >= 4 and self.known(cb) and len(cb) >= 3)
                ):  # fmt: skip
                    out.append(a + b)
                    i += 2
                    continue
            out.append(a)
            i += 1
        return " ".join(out)


# what follows a missed heading when it is the next condition: its number (or an OCR'd stub such as "c~."), its
# title, then its text ("~7. Enforcement. Violation of any ...")
_NEXT = re.compile(
    r"^[^\w]*(?:(\d{1,2}[A-Z]?)\.|[a-z~]{1,2}[~.]+)?\s*([A-Z][A-Za-z ,'’/-]{2,70}?)[.:](?:\s+(.*))?$", re.S
)


def split_after_heading(text: str) -> tuple[str, tuple[str | None, str, str] | None]:
    """Split off a condition that ran on after a missed section heading ("... MONITORING - AFTER ENTITLEMENT
    7. Enforcement. Violation of ..."). Returns the text up to the heading, and (number or None, title, text) of the
    next condition when one follows; clean() would otherwise drop it with the heading."""
    m = _MID_HEADING.search(text)
    if not m:
        return text, None
    after = re.sub(
        r"^\s+[^\w\s]*\s*(?:MONITORING\s*[-•–]?\s*[-•–]?AFTER\s+ENTITLEMENT|DESIGN\s*[-–—]*\s*COMPLIANCE\s+AT\s+PLAN\s+STAGE)",
        "",
        m.group(0),
    ).strip()
    nxt = _NEXT.match(after)
    # nothing follows, or another heading in capitals
    if not nxt or nxt.group(2).strip().upper() == nxt.group(2).strip():
        return text, None
    return text[: m.start()], (nxt.group(1), nxt.group(2).strip(), (nxt.group(3) or "").strip())


# Text from a page that is not a condition, run on into the end of the last condition on the page before it
# (2026-11-13). Two kinds:
# - "drawing sheet": a plan sheet bound in after the conditions (2018-015652CUA #28 ended "... between midnight and
#   6 a.m. DRAFTING HOMES DraftingHomes.com Drawn by Job 9005 Date - Description - Revision 3/29/19 - Initial - 0
#   ... 68.75 88.75 37.75 137.50 ... Powell St."): title-block words, a drafting firm's web address, a scale,
#   dimension runs, room labels in capitals;
# - "page header": the motion's running header "Motion No. 20113 Case Number 2017-015083CUA February 22, 2018 721
#   Lincoln Way" in the forms _RUNNING misses ("CASE NO.", "Case Number", "2017-010011 CUA"), with the page footer
#   pieces before it ("Page 2 of 5SAN FRANCISCO", "planning.org").
# A signature only counts when everything from it to the end of the condition reads as labels and numbers, not
# prose (_prose_share below 0.3), and the cut is made at the last sentence end before it, so a condition that
# mentions plans "drawn by the architect" or a scale is never cut.
_SHEET_SIGNS = (
    r"\bDrawn\s+by\b|\bChecked\s+by\b|\bJob\s+(?:No\.?\s*|#\s*)?\d{3,}\b|\bSheet\s+(?:No\.?|Title|Number)\b"
    r"|\bProject\s+No\.?\s*\d|\bScale\s*:\s*(?:\d|N\.?T\.?S)|\d/\d{1,2}\"\s*=\s*1'|\bDate\s*-\s*Description\b"
    r"|\bDRAFTING\b|(?<![@\w.])[A-Z][A-Za-z]+\.com\b|\bFloor\s+Plan,|\b(?:FLOOR|SITE)\s+PLAN\b"
    r"|(?:(?<!\S)\d{1,4}\.\d{2}(?!\S)\s+){3,}\d{1,4}\.\d{2}(?!\S)"  # four dimensions or more: "68.75 88.75 37.75 137.50"
    r"|(?:\d+'\s*-\s*\d+\"\s*\S*\s+){1,3}\d+'\s*-\s*\d+\""  # feet-inch dimensions: 12'-6" 8'-0"
    # seven room labels or numbers in a row: "OFFICE STRG MEN WOM OFFICE RECEP"; a section heading in capitals
    # ("PRINTING OF CONDITIONS OF APPROVAL ON PLANS") has small words in it and is not one
    r"|(?:(?<!\S)(?:(?!(?:OF|AND|THE|ON|TO|FOR|IN|OR|AT|WITH|BY|AN?)(?!\S))[A-Z]{2,}|\d{3,4})(?!\S)(?:\s+|$)){7,}"
)
_HEADER_SIGNS = (
    r"\bMotion\s+No\.?\s*\d{4,5}\s+(?:CASE|Case|RECORD|Record)\s+"
    r"(?:NO\.?|No\.?|Number)\s*\d{4}[\w.\-]*(?:\s?CUA)?\b"
)
_LEAK_SIGN = re.compile(rf"(?P<sheet>{_SHEET_SIGNS})|(?P<header>{_HEADER_SIGNS})")
# where a sentence of the condition can end: after ".", ")", ";" or "!" followed by a space, but not "No." before a
# number ("under Motion No. 18337.")
_SENTENCE_END = re.compile(r"(?<=[.);!?])(?<!\bNo\.)(?<!\bNos\.)(?<!\bNO\.)\s")
LEAK_KINDS = {"sheet": "drawing sheet", "header": "page header"}


def _prose_share(text: str) -> float:
    """The share of tokens that are lower-case words ("shall", "the", "between"): high in a sentence, low in a title
    block, a header or a run of dimensions."""
    tokens = text.split()
    return sum(bool(re.fullmatch(r"[a-z]{2,}[,.;:]?", t)) for t in tokens) / max(1, len(tokens))


def leak_cut(body: str) -> tuple[int, str] | None:
    """Where a condition ends when a drawing sheet or a page header ran on into it: (offset to cut at, kind), or
    None. The cut is at the last sentence end before the first signature whose rest is not prose; it goes back over
    earlier pieces that are not prose either ("Code Information 2016 Calif."), never over a sentence."""
    for m in _LEAK_SIGN.finditer(body):
        if _prose_share(body[m.start() :]) >= 0.3:
            continue
        ends = [e.start() for e in _SENTENCE_END.finditer(body, 0, m.start() + 1)]
        if not ends:
            return None  # no sentence end before it: where the condition ends is not known
        cut = ends[-1]
        for prev in reversed(ends[:-1]):
            piece = body[prev:cut]
            if (
                _prose_share(piece) >= 0.3
                or re.search(r"(?<![A-Za-z])[a-z]{4,}\b", piece)
                or not re.search(r"[A-Za-z]", piece)  # a number alone ("18337.") ends the sentence before it
            ):
                break
            cut = prev
        if len(body[:cut].strip()) < 20:
            return None
        return cut, LEAK_KINDS[m.lastgroup or "sheet"]
    return None


def leak_signatures(text: str) -> list[str]:
    """Signatures of a drawing sheet or a page header in a condition's text whose rest is not prose (what leak_cut
    looks for); empty for a clean condition. The tests run it over the built data."""
    return [m.group(0) for m in _LEAK_SIGN.finditer(text) if _prose_share(text[m.start() :]) < 0.3]


# Text after a condition's last sentence that is not the condition (2026-11-13, second pass), cut off by tail_cut:
# - "page header": the page footer "SAN FRANCISCO PLANNING DEPARTMENT", its page number and "Page 3 of 5", and the
#   running header's "CASE NO. 2017-000519CUA" / "Motion No.", in the forms OCR made of them ("SAN FRANCISCO 13P
#   L/tNNiNG", "saw FRnNcisco 15P LARIMW6 DBPARTNlEMT", "P LANNING D£PAR7MENT Page 7 of", "SAN PRANCtSCO"): a word
#   counts when its letters are close to FRANCISCO, PLANNING or DEPARTMENT (difflib) and it is not written as a
#   word in a sentence ("Planning", "planning"), or when it follows the "13P" of "13P LANNING";
# - "section heading": the heading of the next group of conditions (SECTION_HEADINGS, the headings that start the
#   groups in the motions' Exhibit A), in capitals, in title case ("Monitoring - After Entitlement") or spaced by
#   OCR ("O PERATION", "D ESIGN", "ITORING - AFTER ENTITLEMENT"), with the next condition's title when it follows;
# - "file path": the word-processor file name printed under the motion ("U:\DVu\...\Final Motion.doc"), or the
#   typist's initials left of it ("ESJ:");
# - "drawing sheet": the cover title of the plan set bound in after the conditions ("EXHIBIT B: Plans & Renderings");
# - "drawing sheet / image-page OCR noise": what OCR made of a picture page bound in after the conditions (a map or a
#   plan scanned as an image): a run of symbols and letters that are not words (":r~' ~ Yrsf~ ~:~"a ~ ..."), after the
#   last sentence (_noise_cut);
# - "next condition's title": the title of the next condition, whose number and text the first reading lost (an
#   unnumbered paragraph such as "Sidewalk Maintenance." or "Rooftop Mechanical Equipment."): a short phrase in title
#   case, the whole of the last sentence, that is a title used on 10 or more conditions (the build passes those
#   titles), after the last sentence or after a contact line's phone number, which stays (_title_cut).
# Pieces are taken off the end one by one; the cut is kept only when what is left ends where a sentence ends, or at
# the end of a contact line (its phone number or web address, which are left as they are: the contact lines are a
# separate decision). So a condition is never cut inside its own text. A piece of a web address left between the
# last sentence and the furniture, with no contact line before it ("authorization. org SAN FRANCISCO"), goes too.
SECTION_HEADINGS = (
    "PERFORMANCE",
    "OPERATION",
    "MONITORING - AFTER ENTITLEMENT",
    "MONITORING PROGRAM",
    "MONITORING & VIOLATION",
    "MONITORING",
    "DESIGN - COMPLIANCE AT PLAN STAGE",
    "DESIGN",
    "PARKING AND TRAFFIC",
    "PARKING & TRAFFIC",
    "PROVISIONS",
    "ENTERTAINMENT COMMISSION - NOISE ATTENUATION CONDITIONS",
    "STANDARD CONDITIONS",
    "ADDITIONAL CONDITIONS",
    "MAXIMUM OCCUPANCY AND EVENTS",
    "MITIGATION MEASURES",
    "CONDITIONS OF APPROVAL, COMPLIANCE, MONITORING, AND REPORTING",
    "LOADING",
)


def _heading_pattern(heading: str) -> str:
    """A heading as OCR and the PDF reader print it: any case, one stray space inside a word ("O PERATION"), any
    dash between its parts; "MONITORING" may lose its first letters ("ITORING - AFTER ENTITLEMENT")."""
    words = []
    for i, word in enumerate(re.findall(r"[A-Z]+|&", heading)):
        w = r"\s?".join(word) if word != "&" else "&"
        if i == 0 and word == "MONITORING" and " - " in heading:
            w = r"(?:M\s?O\s?N\s?)?" + r"\s?".join("ITORING")
        words.append(w)
    return r"\s*[-–—•,]*\s*".join(words)


_HEADING_TAIL = re.compile(
    r"(?<!\S)(?=[A-Z])(?i:"
    + "|".join(_heading_pattern(h) for h in SECTION_HEADINGS)
    + r")(?:\s+(?:\d{1,2}\.\s*)?[A-Z][a-z]+(?:\s+[A-Za-z0-9][a-z0-9]*){0,4}\.)?[\s\W]*$"
)
# a piece of a contact line's web address ("planning.org", "zvww.", "orb", "sf.gov/entertainmentcommission")
_URL_WORD = re.compile(
    r"\S*(?:\.or[gbQ~]?|www|http|\.gov|\.com|lann|Tannin)\S*|or[gbQ~]\.?|[wz][wzuvZ]{2,}\S*"
)
# OCR splits one into several tokens: "zvww. s f-p lann ing. orb", "wwZas -Tannin orb"
_URL_BIT = re.compile(rf"{_URL_WORD.pattern}|-[A-Za-z]\S*|\S{{1,3}}[.,]?")
_PHONE_END = re.compile(r"\d{3}\s?[.\-‐]\s?\d{4}\s*,?$")
_STOP = re.compile(r"[.;!?)][\"”’']?$")
_FOOTER_WORDS = ("FRANCISCO", "PLANNING", "LANNING", "DEPARTMENT")


def _prose_word(token: str) -> bool:
    """A word as a sentence writes it ("Planning", "planning", "Francisco"), not furniture."""
    return bool(re.fullmatch(r"[A-Z]?[a-z]+[,.;:]?", token))


def _footer_word(token: str, words: tuple[str, ...] = _FOOTER_WORDS) -> bool:
    """A page-footer word as OCR printed it: letters close to one of `words`, not written as prose; or a piece of
    one in capitals ("ENT" of "DEP4RTM ENT")."""
    core = token.strip(_PUNCT + "~'`#")
    letters = re.sub(r"[^A-Za-z]", "", core).upper()
    if len(letters) < 3 or _prose_word(core):
        return False
    if core.isalpha() and core.isupper() and len(core) < 5:
        return any(core in w for w in words)
    return any(difflib.SequenceMatcher(None, letters, w).ratio() >= 0.7 for w in words)


def _shape_not_prose(token: str) -> bool:
    """Capitals, or letters mixed with digits and symbols ("LARIMW6", "~lPApTM"): not a word of a sentence."""
    letters = re.sub(r"[^A-Za-z]", "", token)
    return (
        len(letters) >= 3
        and not _prose_word(token)
        and (sum(ch.isupper() for ch in letters) >= 2 or bool(re.search(r"[^A-Za-z]", token)))
    )


# the pieces taken off the end, each anchored there: (kind, pattern, check on the named group "w" or None).
# "filler" pieces (a page number, stray symbols) are taken too but do not count as furniture on their own.
_TAIL_PIECES: tuple[tuple[str, re.Pattern[str], object], ...] = (
    ("file path", re.compile(r"(?<!\S)(?:[A-Z]{2,4}:\s*)?\S*[A-Z]:\\.*\.docx?\s*$"), None),
    # the typist's initials before a file path the clean-up already took off ("ESJ: G:\DOCUMENTS\...\18225.doc")
    ("file path", re.compile(r"(?<!\S)[A-Z]{2,4}:\s*$"), None),
    ("drawing sheet", re.compile(
        r"(?<!\S)EXHIBIT\s+[BC]\s*:?\s*(?:Plans|Drawings|Renderings)(?:\s*(?:&|and)\s*(?:Plans|Drawings|Renderings))?"
        r"[\s\W]*$"
    ), None),
    ("page header", re.compile(r"(?<!\S)Page\s+\d{1,3}\s+(?:of|0#)(?:\s+\d{1,3}(?:SAN)?)?\s*$"), None),
    ("page header", re.compile(r"(?<!\S)[CG]\S?SE\s+N[O0o]\.?(?:\s*\d{4}[\w.\-]{3,16})?\s*$"), None),
    ("page header", re.compile(r"(?<!\S)Motion\s+(?:No|NO|N0|IVo)\.?(?:\s*\d{4,5})?\s*$"), None),
    ("section heading", _HEADING_TAIL, None),
    # "13P L/tNNiNG", "15P LARIMW6 DBPARTNlEMT", "8 P LANNINQi": the page number run into the "P" of PLANNING
    ("page header", re.compile(r"(?<!\S)(?P<n>\d{1,3}\s?)?P(?P<s>\s?)(?P<w>\S{3,10})(?:\s+(?P<x>\S{4,12}))?\s*$"), "P"),
    # "SAN FRANCISCO", "saw FRnNcisco", "SAN PRANCtSCO", "SAN FRANCISC6"
    ("page header", re.compile(r"(?<!\S)(?:[Ss5][A-Za-z][NnWw]\s+)?(?P<w>\S{6,12})\s*$"), "FRANCISCO"),
    ("page header", re.compile(r"(?<!\S)(?P<w>\S{3,12})\s*$"), "FOOTER"),
    ("filler", re.compile(r"(?<!\S)(?:[\W\d_]{1,4}|[O0])\s*$"), None),
)  # fmt: skip


def _tail_piece(body: str) -> tuple[str, int] | None:
    """The piece of furniture at the very end of body: (kind, where it starts), or None."""
    for kind, pattern, check in _TAIL_PIECES:
        m = pattern.search(body)
        if not m:
            continue
        if check == "P":
            w, x = m.group("w"), m.group("x")
            # "PROVISIONS" is not "P ROVISIONS": with no page number or space before it, the word must be PLANNING
            loose = bool(m.group("n") or m.group("s")) and _shape_not_prose(w)
            if not (loose or _footer_word(w, ("LANNING",))) or (x is not None and not _shape_not_prose(x)):
                continue
        elif check == "FRANCISCO":
            if not _footer_word(m.group("w"), ("FRANCISCO",)):
                continue
        elif check == "FOOTER":
            if not _footer_word(m.group("w")):
                continue
        return kind, m.start()
    return None


def _stops(text: str) -> bool:
    """text ends where a condition can end: at the end of a sentence, or at the end of a contact line (its phone
    number, or a piece of its web address after a sentence end or a phone number)."""
    text = text.rstrip()
    if _STOP.search(text) or _PHONE_END.search(text):
        return True
    if text.split() and _URL_WORD.fullmatch(text.split()[-1]):
        before = " ".join(text.split()[-7:-1])
        return bool(re.search(r"[.;)]\s|[.;)]$|\d{3}\s?[.\-‐]\s?\d{4}", before))
    return False


def _furniture_cut(body: str) -> tuple[int, str] | None:
    """Where a condition ends when page furniture, the next section's heading, a file path or the plan set's title
    follows its last sentence: (offset to cut at, kind of the first piece cut), or None. Pieces are taken off the
    end while they read as furniture; the cut is kept only where what is left can end a condition (_stops). A page
    header of two pieces or more ("DEP/fRTMENT Motion IVo.") is also cut where the first reading had already lost
    the rest of the sentence before it (it ends in a lower-case word), since nothing of the condition follows it."""
    end, kinds = len(body), []
    while (piece := _tail_piece(body[:end])) is not None:
        kind, start = piece
        kinds.append(kind)
        end = start
        while end and body[end - 1].isspace():
            end -= 1
        if _stops(body[:end]) and kind != "filler":
            break
    strong = [k for k in kinds if k != "filler"]
    if not strong or len(body[:end].strip()) < 20:
        return None
    # a piece of a web address right after the last sentence, with no contact line before it ("authorization. org
    # SAN FRANCISCO 13P UNNING"): what the clean-up left of a contact line it took off; it goes with the furniture,
    # as the clean-up takes such a piece off the very end of any condition. One after a phone number ends a
    # contact line and stays.
    rest, url = body[:end], False
    for _ in range(6):
        last = re.search(r"\s+(\S+)$", rest)
        if not last or not _URL_BIT.fullmatch(last.group(1)):
            break
        url = url or bool(_URL_WORD.fullmatch(last.group(1)))
        rest = rest[: last.start()]
        contact = re.search(r"\d{3}\s?[.\-‐]\s?\d{4}|\bcontact\b", " ".join(rest.split()[-4:]))
        if url and _STOP.search(rest) and not contact and not _URL_BIT.fullmatch(rest.split()[-1]):
            end = len(rest)
            break
    if not _stops(body[:end]):
        mid = strong.count("page header") >= 2 and re.search(r"\b[a-z]{2,}$", body[:end].rstrip())
        if not mid:
            return None
    return end, strong[-1]


NOISE_KIND = "drawing sheet / image-page OCR noise"
TITLE_KIND = "next condition's title"
# an image page's OCR: at least this many tokens and characters, at most this share of words, at least this share of
# symbols among its characters, and never three words in a row (a sentence)
_NOISE_MIN_TOKENS = 5
_NOISE_MIN_CHARS = 30
_NOISE_MAX_WORDS = 0.3
_NOISE_MIN_SYMBOLS = 0.25
_LAST_SENTENCE = re.compile(r"[.;!?)][\"”’']?\s+")
# a title as the motions print it: capitalised words, with the small words in lower case ("Hours of Operation")
_TITLE_TAIL = re.compile(
    r"(?<=\s)(?P<t>[A-Z][A-Za-z’'&/-]*(?:\s+(?:[A-Z][A-Za-z’'&/-]*|of|and|or|to|the|for|due|in|on|at|with|a|an)){0,7})"
    r"\.\s*$"
)


def _word(token: str, vocab: Vocabulary | None) -> bool:
    """A token that reads as a word: letters only (a hyphen or apostrophe inside), two or more, and known to the
    vocabulary when there is one (else lower case or capitalised, with a vowel)."""
    core = token.strip(_PUNCT)
    if not re.fullmatch(r"[A-Za-z]{2,}(?:[-’'][A-Za-z]+)*", core):
        return False
    if vocab is not None:
        return all(vocab.known(part) for part in re.split(r"[-’']", core) if len(part) >= 2)
    return bool(re.fullmatch(r"[A-Z]?[a-z]+(?:[-’'][a-z]+)*", core)) and bool(
        re.search(r"[aeiouy]", core, re.I)
    )


def _noise(tail: str, vocab: Vocabulary | None) -> bool:
    """tail is OCR noise, not text: long enough, mostly symbols and non-words, no sentence in it, and it does not
    start with a word or a number (so "to 11 p.m." after "6 a.m." is never taken)."""
    tokens = tail.split()
    chars = "".join(tokens)
    if len(tokens) < _NOISE_MIN_TOKENS or len(chars) < _NOISE_MIN_CHARS:
        return False
    words = [_word(t, vocab) for t in tokens]
    first = tokens[0].strip(_PUNCT)
    # what starts the tail is judged by its shape, not by the word list (which differs between machines: the
    # system dictionary is missing on CI), so "to 11 p.m." is never noise anywhere
    if (
        words[0]
        or re.fullmatch(r"[A-Za-z]{2,}", first)
        or re.fullmatch(r"\d+[A-Za-z]?", first)
        or re.fullmatch(r"[ap]\.?m", first, re.I)
    ):
        return False
    if any(all(words[i : i + 3]) for i in range(len(words) - 2)):
        return False
    symbols = sum(not ch.isalnum() for ch in chars) / len(chars)
    return sum(words) / len(words) <= _NOISE_MAX_WORDS and symbols >= _NOISE_MIN_SYMBOLS


def _after_footer(tail: str) -> str:
    """tail without the page footer it may open with ("SAN FRANCISCO 17P LANNING DEPARTMENT", OCR forms too): the
    words before an image page's noise. Only skipped when at least one footer word is there; prose is never skipped."""
    tokens = tail.split()
    i = footer = 0
    while i < len(tokens):
        core = tokens[i].strip(_PUNCT + "~'`#")
        if _footer_word(core):
            footer += 1
        elif not (
            (re.fullmatch(r"(?i)s[a4@]n|saw|sam", core) and not _prose_word(core))
            or re.fullmatch(r"\d{1,3}[A-Za-z]?", core)
            or core.lower() in ("page", "of")
        ):
            break
        i += 1
    return " ".join(tokens[i:]) if footer else tail


def _noise_cut(body: str, vocab: Vocabulary | None) -> int | None:
    """Where a condition ends when an image page's OCR noise follows its last sentence (with or without the page
    footer between them): the first sentence end after which everything is noise (_noise), or None."""
    for m in _LAST_SENTENCE.finditer(body):
        if _noise(_after_footer(body[m.end() :]), vocab) and _stops(body[: m.end()]):
            return len(body[: m.end()].rstrip())
    return None


def _title_cut(body: str, titles: Collection[str] | None) -> int | None:
    """Where a condition ends when the next condition's title follows its last sentence or its contact line's phone
    number ("... Historic Properties. Rooftop Mechanical Equipment."): the start of that title, or None. `titles` are
    the attested titles as letters only (lower case, no spaces)."""
    if not titles or not (m := _TITLE_TAIL.search(body)):
        return None
    before = body[: m.start()].rstrip()
    # a phone number as OCR printed it, with two marks in it ("415-554-.5810,"), ends a contact line too
    phone = re.search(r"\d{3}\s?[.\-‐]{1,2}\s?\d{4}\s*,?$", before)
    if re.sub(r"[^a-z]", "", m.group("t").lower()) not in titles or not (_stops(before) or phone):
        return None
    return len(before)


def tail_cut(
    body: str, vocab: Vocabulary | None = None, titles: Collection[str] | None = None
) -> tuple[int, str] | None:
    """Where a condition ends when something that is not the condition follows its last sentence: page furniture,
    the next section's heading, a file path or the plan set's title (_furniture_cut), then an image page's OCR noise
    (_noise_cut, with `vocab` to tell words) and the next condition's title (_title_cut, with `titles`, the attested
    titles as letters only): (offset to cut at, kind of the piece cut nearest the condition's text), or None."""
    end, kind = len(body), None
    if (cut := _furniture_cut(body)) is not None:
        end, kind = cut
    for found, k in (
        (_noise_cut(body[:end], vocab), NOISE_KIND),
        (_title_cut(body[:end], titles), TITLE_KIND),
    ):
        if found is not None and len(body[:found].strip()) >= 20:
            end, kind = found, k
    return None if kind is None else (end, kind)


# Furniture inside a condition, between two words of its sentence: the page footer ("SAN FRANCISCO 15P LANNINti
# DEPARTMENT", "P UINNING DEPARTMENT 11") or the running header's case number ("the Zoning CASE NO.2015-005989CUA
# Administrator"), where the page broke; or the footer between the last sentence and the contact line ("Standards.
# SAN PRAFlCISCO 1 O Works, 415-695-2017,"). Only these exact shapes are taken out; the words around them stay.
_INSIDE = re.compile(
    r"(?<=[a-z,])\s+(?:S[A-Z]N\s+(?P<a>[A-Z]\S{5,10})\s+)?\d{0,3}\s?P\s?(?P<b>[A-Z/\\]\S{3,8})\s+(?P<c>D\S{6,10})"
    r"(?:\s+\d{1,3})?(?=\s+[a-z])"
    r"|(?<=[a-z])\s+CASE\s+NO\.?\s*\d{4}[-.]\d{3,6}[A-Z]{1,4}(?=\s+[A-Z][a-z])"
    r"|(?<=[.;])\s+S[A-Z]N\s+(?P<d>[A-Z]\S{5,10})\s+\d{1,2}(?:\s?[O0])?(?=\s+[A-Z][a-z]+,\s+\d{3}[-.‐])"
    # the same footer as OCR garbled it: "SAN fRANCI$CO 1 7", "sam FRa~rcisco ~2"; what is left of it, a page number
    # after a tilde ("~ 2", "'~ O", "~ O PLANNING D<PARTMtNT"); or DEPARTMENT alone in capitals ("DBPARTMENT")
    r"|(?<=[a-z])\s+[Ss][A-Za-z][NnMmWw]\s+(?P<e>[A-Za-z]\S{5,10})\s+(?:~?\d{1,2}|\d\s\d)(?=\s+[A-Za-z][a-z])"
    r"|(?<=[a-z])\s+'?~\s?(?:[O0]|\d{1,2})(?:\s+P\s?LANNING\s+(?P<g>D\S{6,10}))?(?=\s+[a-z])"
    r"|(?<=[a-z])\s+(?P<h>[A-Z][A-Z<$£]{8,11})(?=\s+[a-z])"
)


def inside_cut(body: str) -> tuple[str, list[str]]:
    """body with the page furniture between two words of a sentence taken out (_INSIDE), and the pieces taken."""
    taken: list[str] = []

    def take(m: re.Match[str]) -> str:
        a, b, c, d, e, g, h = m.group("a", "b", "c", "d", "e", "g", "h")
        ok = (
            (a is None or _footer_word(a, ("FRANCISCO",)))
            and (b is None or _footer_word(b, ("PLANNING", "LANNING")) or _shape_not_prose(b))
            and (c is None or _footer_word(c, ("DEPARTMENT",)))
            and (d is None or _footer_word(d, ("FRANCISCO",)))
            and (e is None or _footer_word(e, ("FRANCISCO",)))
            and (g is None or _footer_word(g, ("DEPARTMENT",)))
            and (h is None or _footer_word(h, ("DEPARTMENT",)))
        )
        if not ok:
            return m.group(0)
        taken.append(m.group(0).strip())
        return ""

    return _INSIDE.sub(take, body), taken


def clean(
    text: str,
    vocab: Vocabulary | None = None,
    older: bool = False,
    leaks: list[tuple[str, str]] | None = None,
    cut_leaks: bool = True,
    cut_tails: bool = True,
    titles: Collection[str] | None = None,
) -> str:
    """Remove page furniture that leaked into a condition and join split words. Never touches the title.
    `older`: a motion decided before 2019, whose contact line is also found with "about" or "compliance" split
    (_CONTACT_OLDER) or interleaved with the condition's last line (_CONTACT_SPLIT_OLDER).
    `leaks`: when given, each piece cut by leak_cut, inside_cut or tail_cut (a drawing sheet, page header, section
    heading or file path that is not part of the condition) is added as (kind, text cut).
    `cut_leaks=False`: leave them all (the build uses it to see the text as it was cleaned before those cuts).
    `cut_tails=False`: make only leak_cut's cut, not inside_cut's or tail_cut's (the build picks the reading of a
    condition it shows on that text, as before those two cuts, then cuts the reading it picked).
    `titles`: the attested condition titles, as letters only, for tail_cut's "next condition's title"."""
    contact = _CONTACT_OLDER if older else _CONTACT
    title, sep, body = text.partition(": ") if ": " in text[:140] else ("", "", text)
    # web addresses mangled by OCR, anywhere in the text (a clean one is real text and stays)
    body = _URL_MID.sub(" ", body)
    body = " ".join(t for t in body.split() if not _url_junk(t))
    m = contact.search(body)
    if m and len(body) - m.start() <= _CONTACT_MAX:
        body = body[: m.start()]
    elif older and (m := _CONTACT_SPLIT_OLDER.search(body)) and len(body) - m.start() <= _CONTACT_MAX:
        body = body[: m.start()] + " " + m.group(1)
    body = _FOOTER.sub(" ", body)
    body = _RUNNING.sub(" ", body)
    body = _MID_HEADING.sub("", body)
    if cut_leaks and (cut := leak_cut(body)) is not None:
        if leaks is not None:
            leaks.append((cut[1], body[cut[0] :].strip()))
        body = body[: cut[0]]
    if cut_leaks and cut_tails:
        body, taken = inside_cut(body)
        if leaks is not None:
            leaks.extend(("mid-condition page header", t) for t in taken)
    prev = None
    while prev != body:  # headings, contact-line ends and stray symbols at the very end, possibly several
        prev = body
        body = _CONTACT_TAIL.sub("", _HEADING.sub("", body)).rstrip()
        body = _ADDR_TAIL.sub("", _URL_END.sub("", _FOOTER.sub(" ", body))).rstrip()
        m = contact.search(body)  # a contact line the trim above has just reached
        if m and len(body) - m.start() <= _CONTACT_MAX:
            body = body[: m.start()].rstrip()
        words = body.split()
        n = 0
        while n < min(6, len(words) - 1) and _junk_tail(words[-1 - n]):
            n += 1
        if n:
            body = " ".join(words[:-n])
    if cut_leaks and cut_tails and (cut := tail_cut(body, vocab, titles)) is not None:
        if leaks is not None:
            leaks.append((cut[1], body[cut[0] :].strip()))
        body = body[: cut[0]]
    body = re.sub(r"(?<=\.)\s+\d{1,2}\.$", "", body)  # the next condition's number, left behind
    body = _fix_times(body)
    body = re.sub(r"\s+", " ", body).strip()
    if vocab is not None:
        body = vocab.rejoin(body)
    return f"{title}{sep}{body}" if sep else body


def hard_tokens(text: str) -> list[str]:
    """Pieces that are never real condition text, so one is enough to re-read (or flag) a condition: a word with a
    stray symbol ("commu~~ity", "rtt~\"fir"), letters mixed with digits ("Tl1e", "Apri120th"), and page furniture
    or web-address pieces left behind ("13P LANNING", "www.s", ".or", a dangling "For information about
    compliance, contact"). A lone unknown word ("peacefizl") is not hard: real words such as "graffiti" or "online"
    are missing from the word list too."""
    hard = [
        t for t in _TOKEN.findall(text) if (core := _core(t)) and (_ODD.search(core) or _MIX.search(core))
    ]
    hard.extend(m.group(0).strip() for m in _HARD_FURNITURE.finditer(text))
    return hard


def garbled(bad: list[str], text: str) -> bool:
    """Too damaged to show: any hard piece (see hard_tokens), or at least GARBLED_MIN_BAD unreadable words, or
    GARBLED_SHARE of the words."""
    words = max(1, len(_TOKEN.findall(text)))
    return bool(hard_tokens(text)) or len(bad) >= GARBLED_MIN_BAD or len(bad) / words >= GARBLED_SHARE
