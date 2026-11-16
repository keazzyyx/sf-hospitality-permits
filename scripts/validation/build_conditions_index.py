"""Build the data for the local conditions search page (tools/conditions-search/).

Reads the conditions of approval already extracted from Planning Commission motions (local tables case_conditions
and case_motions, built by full_conditions.py), the premises labels (local table record_labels, built by
classify_records.py) and the motion PDFs cached under $LOCAL_DATA_DIR/raw. No model, no network.

What it does, in order:

1. Keeps only food-and-drink motions. A motion stays when the premises classifier says its record is about a
   food-or-drink premises (record_labels.premises) AND gives it a food-or-drink use (use_class is not "none").
   Then the reviewed list, tools/conditions-search/reviewed-labels.json, overrides the classifier in both
   directions: an "include" brings a left-out motion back with the business type it gives, an "exclude" removes a
   kept one (apply_review). Every motion left out is listed in the output and in the build log, with what it is
   and who left it out (the classifier or the review); every change the review made is listed with its reason.
2. Marks each condition "boilerplate", "standard" or "case-specific". Boilerplate is the fixed set of
   approval-procedure titles in BOILERPLATE_TITLES (validity, expiration, diligent pursuit, extension, ...).
   The page hides them unless the filter asks for them. "Standard" and "case-specific" come from
   full_conditions.py (case_conditions.standard), plus one rule here: a lettered part of a set ("Liquor Stores
   (B)") worded the same on at least two motions is standard (see template_parts).
   A condition that ran on into the next one after a missed section heading is split in two
   (condition_text.split_after_heading), so the next condition is not lost.
3. Cleans the text (condition_text.clean: page furniture that leaked in, words split by a stray space; a drawing
   sheet or running page header that ran on into a condition's end is cut off at its last sentence, leak_cut; page
   furniture, the next section's heading, a word-processor file path or the plan set's "EXHIBIT B: Plans" title
   after its last sentence is cut off too, tail_cut, and so are an image page's OCR noise (symbols and non-words)
   and the next condition's title when its text was lost (a title used on 10+ conditions, as the whole last
   sentence); page furniture between two words of a sentence is taken out,
   inside_cut; each is counted in text_quality as "<kind> text cut off") and checks
   it reads. A condition that still reads badly is re-read from the PDF: first the text layer
   (pdftotext -layout), then OCR of its pages (pdftoppm + tesseract, cached under
   $LOCAL_DATA_DIR/conditions_ocr/). The reading with the fewest unreadable words wins. One that is still
   garbled is marked "unreadable"; the page shows a link to the motion page instead of the junk. One stray
   symbol, letters mixed with digits or a piece of page furniture is enough (condition_text.hard_tokens).
   On motions decided before 2019 only: the contact line is also found with "about" or "compliance" split ("abou t",
   "c ompliance") or interleaved with the condition's last line, and a title OCR misread is read again
   (retitle; the kind and standard flag are worked out again under the new title):
   - a title with a stray symbol ("E~ctension") is taken from the kept second reading's own heading ("Extension:";
     reread_title);
   - a title used nowhere else that is one OCR swap or two away from a title used on 10 or more conditions
     ("Revocation dne to Violation of Conditions", "Entertainmen# Venues") takes that title, or the kept reading's
     own heading when that is one (attested_title).
4. Finds the page of the motion where each condition starts, so the page can link to it.
5. Records what the data covers ("coverage"): the look-up's start date (full_conditions.SINCE), how many cases
   were looked up and which motions were not found, the decision dates of the kept motions, the dates Planning's
   records were copied and the motions looked up, and the build date. The page's coverage note is made from it.

Writes
  tools/conditions-search/data/conditions.json   conditions plus: removed motions, motions without conditions,
                                                 the boilerplate titles, the build counts and the coverage
  tools/conditions-search/pdf/<record>.pdf       links to the cached motion PDFs (local only; not committed)

    apps/api/.venv/bin/python scripts/validation/build_conditions_index.py
"""

from __future__ import annotations

import datetime as dt
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from condition_text import Vocabulary, clean, garbled, hard_tokens, split_after_heading
from private_contacts import withhold_private_contacts

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tools" / "conditions-search"
RAW = Path(os.environ.get("LOCAL_DATA_DIR", "~/sfhp-local")).expanduser() / "raw" / "sf_planning_hearings"
OCR_CACHE = Path(os.environ.get("LOCAL_DATA_DIR", "~/sfhp-local")).expanduser() / "conditions_ocr"
PAGES_CACHE = Path(os.environ.get("LOCAL_DATA_DIR", "~/sfhp-local")).expanduser() / "conditions_pages"
PSQL = ["psql", "-h", "localhost", "-p", "55433", "-U", "postgres", "sfhp_local", "-At", "-c"]
REVIEWED = OUT / "reviewed-labels.json"
OCR_DPI = 300
OCR_WORKERS = 4

BUSINESS = {
    "restaurant_or_cafe": "Restaurant or cafe",
    "bar": "Bar",
    "nighttime_entertainment": "Nighttime entertainment",
    "other_food_drink": "Other food and drink",
}

# Approval boilerplate: conditions about the approval itself (how long it lasts, how it is renewed, extended,
# enforced and revoked), worded the same on every motion. Matched on the letters-only title
# (case_conditions.norm_title), including OCR misreadings seen in the data. Operating conditions that many
# motions share (community liaison, sidewalk maintenance, garbage, odor, notices posted at bars) are NOT
# boilerplate: they say how the business must run, so they stay in the default view as "standard".
BOILERPLATE_TITLES = {
    "validity": "Validity",
    "validityandexpiration": "Validity and Expiration",  # older motions (before about 2015) join the two
    "expirationandrenewal": "Expiration and Renewal",
    "eacpirationandrenewal": "Expiration and Renewal",  # OCR
    "diligentpursuit": "Diligent Pursuit",
    "extension": "Extension",
    "conformitywithcurrentlaw": "Conformity with Current Law",
    "enforcement": "Enforcement",
    "revocationduetoviolationofconditions": "Revocation due to Violation of Conditions",
    "monitoring": "Monitoring",
    "severability": "Severability",  # none in the data today; part of the same block on older motions
}


BUSINESS_KEY = {label: key for key, label in BUSINESS.items()}
REVIEW_DECISIONS = ("include", "exclude")


def load_review(path: Path = REVIEWED) -> dict:
    """The reviewed list, or an empty one when the file does not exist yet. Stops on a malformed decision."""
    if not path.exists():
        return {"reviewed_on": None, "decisions": []}
    review = json.loads(path.read_text())
    seen: set[str] = set()
    for d in review.get("decisions", []):
        if d.get("decision") not in REVIEW_DECISIONS:
            sys.exit(f"{path.name}: {d.get('record')}: decision must be one of {REVIEW_DECISIONS}")
        if d.get("business") is not None and d["business"] not in BUSINESS_KEY:
            sys.exit(f"{path.name}: {d.get('record')}: business must be one of {sorted(BUSINESS_KEY)} or null")
        if d.get("record") in seen:
            sys.exit(f"{path.name}: {d.get('record')} is listed twice")
        seen.add(d.get("record"))
    return review


def apply_review(kept: list[dict], removed: list[dict], review: dict) -> dict:
    """Apply the reviewed list to the classifier's split. Changes `kept` and `removed` in place (each motion row
    needs "record" and "use_class") and returns what happened:

    - "include" of a left-out motion moves it to kept, with use_class from the decision's business (or the
      classifier's own use when the decision gives none and the classifier has one, else other food and drink);
    - "include" of a kept motion with a different business sets that business;
    - "exclude" of a kept motion moves it to removed;
    - anything else (already where the review wants it, or a record that is not among the motions found) changes
      nothing and is reported.

    Every motion moved gets "_review" (the decision), so the output can say why."""
    by_record = {m["record"]: m for m in kept + removed}
    out: dict[str, list] = {"added": [], "removed": [], "business_set": [], "no_change": [], "not_found": []}
    for d in review.get("decisions", []):
        m = by_record.get(d["record"])
        if m is None:
            out["not_found"].append(d)
            continue
        business = BUSINESS_KEY.get(d.get("business") or "")
        if d["decision"] == "include":
            if m in removed:
                removed.remove(m)
                kept.append(m)
                m["_classifier_use"] = m["use_class"]
                if business is None and (m["use_class"] or "none") == "none":
                    business = "other_food_drink"
                    print(f"review: {d['record']} included with no business type; shown as other food and drink")
                m["use_class"] = business or m["use_class"]
                m["_review"] = d
                out["added"].append(m)
            elif business and business != m["use_class"]:
                m["_classifier_use"] = m["use_class"]
                m["use_class"] = business
                m["_review"] = d
                out["business_set"].append(m)
            else:
                out["no_change"].append(d)
        elif m in kept:
            kept.remove(m)
            removed.append(m)
            m["_review"] = d
            out["removed"].append(m)
        else:
            out["no_change"].append(d)
    return out


def rows(sql: str) -> list[dict]:
    out = subprocess.run([*PSQL, f"select coalesce(json_agg(t), '[]') from ({sql}) t"], capture_output=True,
                         text=True, check=True).stdout  # fmt: skip
    return json.loads(out)


def letters(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def pdf_for(record: str) -> Path | None:
    for f in sorted(RAW.glob(f"*-{record}-motion.json")):
        pdf = (json.loads(f.read_text()).get("data") or {}).get("pdf")
        if pdf and (RAW / pdf).exists():
            return RAW / pdf
    return None


def pdf_pages(pdf: Path, read_pdf, page_break: str) -> list[str]:  # type: ignore[no-untyped-def]
    """The motion's page texts as the first pass read them (pypdf), cached by file size and time: reading every
    PDF again takes minutes."""
    st = pdf.stat()
    hit = PAGES_CACHE / f"{pdf.stem}-{st.st_size}-{int(st.st_mtime)}.json"
    if hit.exists():
        return json.loads(hit.read_text())
    pages = read_pdf(pdf.read_bytes()).text.split(page_break)
    PAGES_CACHE.mkdir(parents=True, exist_ok=True)
    hit.write_text(json.dumps(pages))
    return pages


def what_it_is(description: str | None) -> str:
    """The record's description, first sentence, at most 160 characters."""
    d = re.sub(r"\s+", " ", description or "").strip()
    first = d
    for m in re.finditer(r"\.\s+(?=[A-Z(])", d):  # the first full stop that is not an abbreviation
        word = d[: m.start()].rsplit(" ", 1)[-1].lower()
        if "." not in word and word not in {"dba", "sq", "ft", "st", "ave", "no", "blvd", "inc", "co"}:
            first = d[: m.start() + 1]
            break
    return first if len(first) <= 160 else first[:157].rsplit(" ", 1)[0] + "…"


def page_of(pages: list[str], cond: dict) -> tuple[int | None, bool]:
    """The 1-based page where the condition's text starts: its title and opening words matched on letters only,
    so line breaks, hyphenation and spacing in the PDF text do not matter."""
    body = letters(cond["text"])
    after_title = letters(cond["text"].split(":", 1)[1]) if ":" in cond["text"][:120] else ""
    # an untitled condition (older motions) is stored as "Condition: text" under the generic title "Condition",
    # which the PDF does not print: its opening words are the ones after that title
    generic = letters(cond.get("title") or "") == "condition" and body.startswith("condition") and after_title
    opening = after_title if generic else body
    flat = [letters(page) for page in pages]
    # the opening words first; then the words after the title (stored as "Title: text", printed differently);
    # then windows further in (a heading or a table broken up by the PDF's layout)
    probes = [opening[:80], opening[:50], opening[:30], after_title[:60], after_title[:35],
              *(body[k : k + 40] for k in (40, 80, 120, 200))]  # fmt: skip
    for k, probe in enumerate(probes):
        if len(probe) < 25:
            continue
        for i, page in enumerate(flat):
            if probe in page:
                if generic and k < 3 and sum(probe in p for p in flat) > 1:
                    # an untitled condition whose opening words are also printed elsewhere (a finding that quotes
                    # the authorization, e.g. 2010.0255C #1): a longer passage decides; if it cannot, the page is
                    # only near
                    for size in (150, 250, 400):
                        hits = [j for j, p in enumerate(flat) if opening[:size] in p] if len(opening) >= size else []
                        if len(hits) == 1:
                            return hits[0] + 1, True
                    return i + 1, False
                return i + 1, k < 3  # exact when the opening words matched
    # a condition that runs across a page break: try the two pages joined
    probe = opening[:40]
    for i in range(len(pages) - 1):
        if probe and probe in letters(pages[i] + pages[i + 1]):
            return i + 1, True
    return None, False


def number_order(number: str) -> tuple[int, int, str]:
    """Sort key of a condition number: (list, number, letter). "2.3A" is list 2 (older motions that restart their
    numbering, see all_conditions), condition 3, part A; "3" and "8A" are in list 1. "10" sorts after "9"."""
    m = re.match(r"(?:(\d+)\.)?(\d+)([A-Za-z]?)", number or "")
    return (int(m.group(1) or 1), int(m.group(2)), m.group(3)) if m else (0, 0, "")


# ---- second readings of a motion -------------------------------------------------------------------------------


def parse_conditions(text: str, older_formats: bool = False) -> dict[str, tuple[str, str]]:
    """{number: (title, "Title: text")} for every numbered condition in one reading of a motion, parsed the way
    full_conditions.py parses the first reading: ``older_formats`` as full_conditions.older_formats(decided_at)
    says for the motion (True before 2019)."""
    from precedent.pdftext import PAGE_BREAK, find_sections, strip_running_headers
    from precedent.sources import sf_planning_hearings as H  # noqa: N812

    body = H.motion_body(re.sub(r"\n*\f\n*", PAGE_BREAK, text))
    if older_formats:  # cut at an Exhibit C after the conditions, as full_conditions.conditions_section does
        body = H.cut_older_exhibits(body)
    body = strip_running_headers(body)
    section = find_sections(body).get("conditions", "")
    if not H.all_conditions(section, older_formats=older_formats):  # no heading found (a partial reading)
        section = body  # parse what there is
    return {c.number: (c.title, c.text) for c in H.all_conditions(section, older_formats=older_formats)}


def text_layer(pdf: Path) -> str:
    """The PDF's own text layer through pdftotext (a different reader from the first pass), layout kept."""
    from precedent.sources import sf_planning_hearings as H  # noqa: N812

    return subprocess.run(["pdftotext", "-layout", "-l", str(H.MOTION_MAX_PAGES), str(pdf), "-"],
                          capture_output=True, text=True, check=False).stdout  # fmt: skip


EXCERPT_SIMILARITY = 0.85


def excerpt(reading: str, entry: dict) -> str | None:
    """The condition found in a second reading by its title and opening words, when that reading lost the
    condition's number: as many words as the first reading has, starting at the title. Only kept when its letters
    match the first reading closely (EXCERPT_SIMILARITY), so it is the same text read better, never another
    passage."""
    words = reading.split()
    title = entry["title"].split()
    first_text = clean(entry["_raw"], cut_tails=False)
    first = letters(first_text)
    n = len(first_text.split()) - len(title)  # words after the title
    if not title or len(first) < 60:
        return None
    lead = letters(" ".join(title))
    best, best_ratio = None, 0.0
    for i in range(len(words) - len(title)):
        if letters(" ".join(words[i : i + len(title)])) != lead:
            continue
        # the length that matches the first reading best: no words of the next condition
        for size in range(max(5, n - 8), n + 4):
            rest = " ".join(words[i + len(title) : i + len(title) + size]).lstrip(".: ")
            text = f"{entry['title']}: {rest}"
            again = letters(clean(text, cut_tails=False))
            ratio = difflib.SequenceMatcher(None, first, again, autojunk=False).ratio()
            if ratio > best_ratio:
                best, best_ratio = text, ratio
    return best if best_ratio >= EXCERPT_SIMILARITY else None


def alnum(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


PLAIN_PUNCT = set(".,;:()[]'\"’‘“”-–—/&")


def faithful(first: str, second: str, vocab: Vocabulary) -> bool:
    """A second reading is the same text read better, word for word: it adds no words (a running header, the next
    condition's opening), loses no readable words except junk or furniture at the very end, and brings in no new
    symbols ("April 20%" for "Apri120th"). Words are compared in order."""
    a, b = first.split(), second.split()
    junk = set(vocab.bad_tokens(first)) | set(hard_tokens(first))
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        new = [alnum(w) for w in b[j1:j2]]
        # a readable word is lost when nothing in its place resembles it ("2020." replaced by "April")
        lost = [w for w in a[i1:i2] if w not in junk
                and not any(difflib.SequenceMatcher(None, alnum(w), x).ratio() >= 0.6 for x in new)]  # fmt: skip
        at_end = op == "delete" and i2 == len(a)
        if (j2 - j1) - (i2 - i1) > 1 or len(lost) > (4 if at_end else 0):
            return False
    symbols = {ch for ch in second if not ch.isalnum() and not ch.isspace()}
    return symbols <= {ch for ch in first if not ch.isalnum() and not ch.isspace()} | PLAIN_PUNCT


def ocr_pages(record: str, pdf: Path, pages: list[int]) -> list[str]:
    """OCR text of the given 1-based pages, from the cache or tesseract (300 dpi, grey)."""
    cache = OCR_CACHE / record
    cache.mkdir(parents=True, exist_ok=True)

    def one(page: int) -> str:
        hit = cache / f"p{page:03d}.txt"
        if hit.exists():
            return hit.read_text()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "page"
            subprocess.run(["pdftoppm", "-r", str(OCR_DPI), "-gray", "-png", "-f", str(page), "-l", str(page),
                            "-singlefile", str(pdf), str(base)], check=True, capture_output=True)  # fmt: skip
            res = subprocess.run(["tesseract", f"{base}.png", "stdout"], capture_output=True, text=True,
                                 check=True, env={**os.environ, "OMP_THREAD_LIMIT": "1"})  # fmt: skip
        hit.write_text(res.stdout)
        return res.stdout

    with ThreadPoolExecutor(OCR_WORKERS) as pool:
        return list(pool.map(one, pages))


def same_condition(entry: dict, title: str, text: str) -> bool:
    """A second reading's condition is the same one when its title and text are close on letters."""
    t = difflib.SequenceMatcher(None, letters(entry["title"]), letters(title), autojunk=False).ratio()
    b = difflib.SequenceMatcher(
        None, letters(entry["text"])[:400], letters(text)[:400], autojunk=False
    ).ratio()
    size = len(letters(text)) / max(1, len(letters(clean(entry["_raw"], cut_tails=False))))
    # a second reading that ran on into the next condition (its number missed) is longer: not the same unit; but a
    # condition whose first reading was cut off after its title can only get longer
    if entry.get("_cut"):
        return t >= 0.6
    return t >= 0.6 and b >= 0.5 and 0.6 <= size <= 1.2


def reread(entries: list[dict], vocab: Vocabulary, vocab_recent: Vocabulary | None = None) -> None:
    """For every condition that does not read cleanly: try the text layer, then OCR; keep the best reading.
    Conditions of motions decided RECENT_FROM on are judged with `vocab_recent` when it is given."""
    from full_conditions import older_formats

    todo: dict[str, list[dict]] = {}
    for e in entries:
        if e["_bad"] or e["_cut"] or e["_ocr_anyway"]:
            todo.setdefault(e["record"], []).append(e)
    for record, es in sorted(todo.items()):
        pdf = pdf_for(record)
        if pdf is None:
            continue
        readings = {"text layer": text_layer(pdf)}
        # "_ocr_anyway": a condition that was garbled before its drawing sheet or page header was cut off still
        # has its pages OCR'd, as before the cut, so the other conditions on those pages keep their readings
        if any(garbled(e["_bad"], e["text"]) or e["_cut"] or e["_ocr_anyway"] for e in es) and shutil.which(
            "tesseract"
        ):
            # the pages the conditions are on, one either side (a condition can start on the page before)
            known = [e["page"] for e in es if e["page"]] or [1]
            n_pages = int(subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
                          .split("Pages:")[1].split()[0])  # fmt: skip
            pages = list(range(max(1, min(known) - 1), min(n_pages, max(known) + 2) + 1))
            readings["ocr"] = "\n\f\n".join(ocr_pages(record, pdf, pages))
        older = older_formats(es[0]["decided"])  # case_motions.decided_at, as the first reading
        parsed = {source: parse_conditions(text, older) if text.strip() else {} for source, text in readings.items()}
        for e in es:
            for source, conds in parsed.items():
                candidates = []
                alt = conds.get(e["number"])
                if alt and same_condition(e, *alt):
                    candidates.append(alt[1])
                elif not e["_cut"] and (found := excerpt(readings[source], e)):
                    candidates.append(found)  # the reading lost the number: find the condition by its title
                v = vocab_recent if vocab_recent is not None and (e["decided"] or "") >= RECENT_FROM else vocab
                for candidate in candidates:
                    keep_if_better(e, candidate, source, v)


def keep_if_better(e: dict, candidate: str, source: str, vocab: Vocabulary) -> None:
    """Keep a second reading of condition e when it has fewer unreadable pieces (or restores cut-off text)."""
    older = (e["decided"] or "") < RECENT_FROM
    # the reading is picked on its text as before tail_cut and inside_cut (see main)
    text = clean(candidate, vocab, older, cut_tails=False)
    bad = badness(vocab, text)
    cut_fixed = e["_cut"] and len(letters(text)) > len(letters(e["title"])) + 40
    if not cut_fixed and not faithful(clean(e["_raw"], vocab, older, cut_tails=False), text, vocab):
        return
    if len(bad) < len(e["_bad"]) or (cut_fixed and len(bad) <= len(e["_bad"])):
        e["text"], e["_bad"], e["text_source"], e["_reading"] = text, bad, source, candidate
        e["_cut"] = e["_cut"] and not cut_fixed


def reread_title(e: dict) -> str | None:
    """The title of a condition on a motion decided before 2019 that OCR garbled ("E~ctension", 2016-005799CUA 4),
    as its kept second reading prints it ("Extension: All time limits ..."): only when the title has a hard piece,
    the text's heading has none, and the two are the same word on letters. Else None (the title stays). Titles of
    2019+ motions are never changed."""
    if (e["decided"] or "") >= RECENT_FROM or not hard_tokens(e["title"]):
        return None
    head, sep, _ = e["text"].partition(": ")
    if not sep or len(head) > 140 or hard_tokens(head) or head == e["title"]:
        return None
    same = difflib.SequenceMatcher(None, letters(e["title"]), letters(head), autojunk=False).ratio()
    return head if same >= 0.8 else None


# A title used on at least this many conditions is "attested": Planning's own wording, not an OCR misreading.
ATTESTED_MIN = 10
ATTESTED_SIMILARITY = 0.93  # on letters only
# symbols that are never part of a title (condition_text's stray symbols plus "#", "Entertainmen# Venues")
TITLE_ODD = re.compile(r"[#~_|\\{}^`•«»¬►]")


def attested_titles(entries: list[dict]) -> dict[str, str]:
    """{letters of a title: the title} for every title on at least ATTESTED_MIN conditions, counted on letters only
    (so "Diligent pursuit" and "Diligent Pursuit" are one title), each as it is most often printed."""
    by_letters: dict[str, Counter[str]] = {}
    for e in entries:
        by_letters.setdefault(letters(e["title"]), Counter())[e["title"]] += 1
    return {k: n.most_common(1)[0][0] for k, n in by_letters.items() if sum(n.values()) >= ATTESTED_MIN}


def ocr_swaps(misread: str, title: str) -> int | None:
    """How many characters differ when `misread` is `title` with only OCR-like swaps: one or two characters at a
    time read as others ("Gazbage", "dne", "Entertainmen#"), nothing added or lost, no space moved and no digit read
    as another digit (a different number). None when the two differ in any other way. Case is ignored."""
    a, b = re.sub(r"\s+", " ", misread.lower()), re.sub(r"\s+", " ", title.lower())
    n = 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        x, y = a[i1:i2], b[j1:j2]
        if op != "replace" or len(x) != len(y) or len(x) > 2 or any(ch.isspace() for ch in x + y):
            return None
        if any(p.isdigit() and q.isdigit() for p, q in zip(x, y, strict=True)):
            return None
        n += len(x)
    return n


def attested_title(e: dict, attested: dict[str, str]) -> tuple[str, str] | None:
    """The title of a condition on a motion decided before 2019 whose title OCR misread into one used nowhere else,
    keeping it out of its standard or boilerplate group ("Revocation dne to Violation of Conditions"), and why:

    - "heading": the kept reading's own heading ("Garbage, composting and recycling storage: Space for ...") differs
      from the title, is an attested title, has no stray symbol and is the same title on letters (>= 0.8);
    - "attested": else the one attested title it matches on letters (>= ATTESTED_SIMILARITY) with only OCR-like
      swaps (ocr_swaps), and the same lettered part ("(A)") if any.

    None when the title is itself attested, or nothing matches. Titles of 2019+ motions are never changed."""
    title = e["title"]
    if (e["decided"] or "") >= RECENT_FROM or letters(title) in attested:
        return None
    head, sep, _ = e["text"].partition(": ")
    if (sep and head != title and letters(head) in attested and not TITLE_ODD.search(head) and not hard_tokens(head)
            and difflib.SequenceMatcher(None, letters(title), letters(head), autojunk=False).ratio() >= 0.8):  # fmt: skip
        return head, "heading"
    def part(t: str) -> str | None:  # the lettered part, "A" of "Eating and Drinking Uses (A)"
        m = LETTERED.search(t)
        return m.group(1) if m else None

    matches = [
        t for k, t in attested.items()
        if difflib.SequenceMatcher(None, letters(title), k, autojunk=False).ratio() >= ATTESTED_SIMILARITY
        and ocr_swaps(title, t) and part(t) == part(title)
    ]  # fmt: skip
    return (matches[0], "attested") if len(matches) == 1 else None


def standard_by_rules(motion_id: str, title: str, raw_text: str, categories: list[str], ctx: dict) -> bool:
    """Whether a condition is standard under full_conditions.standard()'s two rules, worked out here for a title the
    build changed (case_conditions still has the misread title): (1) its opening wording under this title is on at
    least WORDING_MIN motions, or (2) the title is on at least half of the approved motions of its motion's use
    (small groups pooled), not an hours condition and not the generic title. `ctx` (standard_context) counts the
    changed titles under their new title."""
    from full_conditions import (
        GENERIC_TITLE,
        MIN_GROUP,
        WORDING_MIN,
        norm_title,
        wording_key,
    )

    if len(ctx["wording"].get(wording_key(title, raw_text), set()) | {motion_id}) >= WORDING_MIN:
        return True
    label = ctx["label"].get(motion_id)
    group = ctx["approved_by_label"].get(label)
    if not group:
        return False
    scope = group if len(group) >= MIN_GROUP else ctx["approved"]
    share = len(ctx["titles"].get(norm_title(title), set()) & scope) / len(scope)
    return share >= 0.5 and "hours" not in (categories or []) and norm_title(title) != norm_title(GENERIC_TITLE)


def standard_context(conds: list[dict], motions: list[dict]) -> dict:
    """What standard_by_rules counts: motions by opening wording and by title (case_conditions), and the approved
    motions by use (case_motions.label), as full_conditions.standard() does."""
    approved_outcomes = ("approved", "approved_with_conditions")
    approved = {m["id"] for m in motions if m["doc_outcome"] in approved_outcomes}
    ctx: dict = {"wording": {}, "titles": {}, "label": {m["id"]: m["label"] for m in motions}, "approved": approved,
                 "approved_by_label": {}}  # fmt: skip
    for m in motions:
        if m["id"] in approved:
            ctx["approved_by_label"].setdefault(m["label"], set()).add(m["id"])
    for c in conds:
        if c.get("wording_key"):
            ctx["wording"].setdefault(c["wording_key"], set()).add(c["id"])
        ctx["titles"].setdefault(c["norm_title"], set()).add(c["id"])
    return ctx


def retitle(e: dict, title: str, ctx: dict) -> None:
    """Give condition e a new title: its text's heading too when it printed the old one, and its standard flag and
    kind worked out again under the new title (boilerplate by BOILERPLATE_TITLES; standard by full_conditions'
    rules, standard_by_rules, or a lettered template part)."""
    from full_conditions import norm_title

    old = e["title"]
    e["title"] = title
    if e["text"].startswith(old + ":"):
        e["text"] = title + e["text"][len(old) :]
    ctx["titles"].setdefault(norm_title(title), set()).add(e["_id"])
    e["standard"] = standard_by_rules(e["_id"], title, e["_raw"], e["categories"], ctx)
    if norm_title(title) in BOILERPLATE_TITLES:
        e["kind"] = "boilerplate"
    else:
        e["kind"] = "standard" if e["standard"] or e["template"] else "specific"


# ---- build ------------------------------------------------------------------------------------------------------

# Motions decided on or after this date were the whole page until 2026-11-13 (see the clean-up vocabulary in main).
RECENT_FROM = "2019-01-01"
LETTERED = re.compile(r"\(([A-Z])\)\s*$")
TEMPLATE_MIN_MOTIONS = 2
TEMPLATE_SIMILARITY = 0.9


def template_parts(conds: list[dict]) -> set[tuple[str, str]]:
    """(motion id, number) of lettered parts of a set ("Liquor Stores (A)", "Chapter 116 Residential Projects (C)")
    whose wording (first 300 letters after the title) matches the same part on at least one other motion. These
    are Planning's template conditions: full_conditions.py needs five motions to call wording standard, and these
    sets are on two to four."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for c in conds:
        m = LETTERED.search(c["title"] or "")
        if m and not c["standard"]:
            groups.setdefault((c["norm_title"], m.group(1)), []).append(c)
    out: set[tuple[str, str]] = set()
    for group in groups.values():
        if len({c["id"] for c in group}) < TEMPLATE_MIN_MOTIONS:
            continue
        body = {id(c): letters(c["text"].split(":", 1)[-1])[:300] for c in group}
        for a in group:
            if any(
                b["id"] != a["id"]
                and difflib.SequenceMatcher(None, body[id(a)], body[id(b)], autojunk=False).ratio()
                >= TEMPLATE_SIMILARITY
                for b in group
            ):
                out.add((a["id"], a["number"]))
    return out


def split_run_ons(conds: list[dict]) -> list[dict]:
    """Conditions with the next condition run on after a missed heading, split in two. The new condition takes the
    number printed before its title, or the next number up; it is only added when the motion has no condition with
    that number."""
    numbers: dict[str, set[str]] = {}
    for c in conds:
        numbers.setdefault(c["id"], set()).add(c["number"])
    out = []
    for c in conds:
        head, nxt = split_after_heading(c["text"])
        if nxt is None:
            out.append(c)
            continue
        number, title, text = nxt
        if number is None:
            m = re.match(r"((?:\d+\.)?)(\d+)", c["number"])  # "2.3" (a restarted list, older motions) -> "2.4"
            number = f"{m.group(1)}{int(m.group(2)) + 1}" if m else ""
        if not number or number in numbers[c["id"]]:
            out.append(c)
            continue
        numbers[c["id"]].add(number)
        out.append({**c, "text": head})
        out.append({**c, "number": number, "title": title, "text": f"{title}: {text}" if text else f"{title}:",
                    "categories": [], "standard": False, "norm_title": letters(title),
                    "_split_from": c["number"]})  # fmt: skip
    return out


def badness(vocab: Vocabulary, text: str) -> list[str]:
    """Everything that does not read: unreadable words plus hard pieces (stray symbols, furniture)."""
    bad = vocab.bad_tokens(text)
    return bad + [h for h in hard_tokens(text) if h not in bad]


def coverage_facts(kept: list[dict], found: list[dict]) -> dict:
    """What the data covers, for the page's coverage note: the look-up's start date and counts (from
    full_conditions.py's table case_motions), the motions not found, the decision dates of the kept motions, and
    the dates Planning's records were copied, the motions were looked up and this build ran."""
    # the look-up's start date: the one rule, not a copy of it
    from full_conditions import SINCE

    lookups = rows(
        "select m.record, m.decided_at, m.found, m.note, r.premises, r.use_class from case_motions m "
        "left join record_labels r using (id) order by m.decided_at, m.record"
    )
    dates = rows(
        "select (select max(fetched_at)::date from applications where source = 'datasf_planning') as copied, "
        "(select max(checked_at)::date from case_motions) as looked_up"
    )[0]
    decided = sorted(m["decided_at"] for m in kept if m["decided_at"])
    return {
        "since": SINCE.isoformat(),
        "cases_looked_up": len(lookups),
        "motions_found": len(found),
        "not_found": [
            {
                "record": m["record"],
                "decided": m["decided_at"],
                "why": m["note"] or "",
                "food_or_drink_now": m["premises"] is True and (m["use_class"] or "none") != "none",
            }
            for m in lookups
            if not m["found"]
        ],
        "decided_from": decided[0] if decided else None,
        "decided_to": decided[-1] if decided else None,
        "motions_by_business": dict(Counter(BUSINESS[m["use_class"]] for m in kept).most_common()),
        "records_copied_on": dates["copied"],
        "motions_looked_up_on": dates["looked_up"],
        "built_on": dt.date.today().isoformat(),
    }


def main() -> int:
    sys.path.insert(0, str(ROOT / "packages" / "precedent"))
    from precedent.pdftext import PAGE_BREAK, read_pdf

    motions = rows(
        "select m.id, m.record, m.decided_at, m.label, m.motion_url, m.doc_outcome, m.note, a.address, "
        "a.description, coalesce(a.zoning_district, a.extra->>'zoning') as zoning, r.premises, r.use_class, "
        "r.confidence from case_motions m left join applications a on a.id = m.id "
        "left join record_labels r on r.id = m.id where m.found order by m.decided_at, m.record"
    )
    kept = [m for m in motions if m["premises"] is True and (m["use_class"] or "none") != "none"]
    removed = [m for m in motions if m not in kept]
    classifier_kept, classifier_removed = len(kept), len(removed)
    review = load_review()
    reviewed = apply_review(kept, removed, review)
    kept.sort(key=lambda m: (m["decided_at"] or "", m["record"]))
    removed.sort(key=lambda m: (m["decided_at"] or "", m["record"]))
    conds = rows("select id, number, title, text, categories, standard, norm_title, wording_key from case_conditions")
    vocab = Vocabulary((c["id"], c["text"]) for c in conds)
    # The clean-up vocabulary for motions decided 2019 on is built from those motions only, as it was before the page
    # reached back to 2010 (2026-11-13): the older motions' words must not change how a published 2019+ condition is
    # cleaned up or which reading of it is kept. Older motions use the vocabulary of every motion.
    recent_ids = {m["id"] for m in motions if (m["decided_at"] or "") >= RECENT_FROM}
    vocab_recent = Vocabulary((c["id"], c["text"]) for c in conds if c["id"] in recent_ids)
    standard_ctx = standard_context(conds, motions)  # for titles the build changes (retitle)
    conds = split_run_ons(conds)
    templates = template_parts(conds)
    by_motion: dict[str, list[dict]] = {}
    for c in conds:
        by_motion.setdefault(c["id"], []).append(c)

    (OUT / "data").mkdir(parents=True, exist_ok=True)
    (OUT / "pdf").mkdir(parents=True, exist_ok=True)
    for old in (OUT / "pdf").glob("*.pdf"):  # links for motions no longer listed
        if old.is_symlink():
            old.unlink()
    entries = []
    found: Counter[str] = Counter()
    for m in kept:
        pdf = pdf_for(m["record"])
        pages: list[str] = []
        local = None
        if pdf is not None:
            pages = pdf_pages(pdf, read_pdf, PAGE_BREAK)
            link = OUT / "pdf" / f"{m['record']}.pdf"
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(pdf)
            local = f"pdf/{m['record']}.pdf"
        for c in by_motion.get(m["id"], []):
            page, exact = page_of(pages, c) if pages else (None, False)
            found[
                ("exact page" if exact else "nearby page") if page else ("no page" if pages else "no pdf")
            ] += 1
            boiler = c["norm_title"] in BOILERPLATE_TITLES
            template = (c["id"], c["number"]) in templates
            v = vocab_recent if (m["decided_at"] or "") >= RECENT_FROM else vocab
            raw_bad = badness(v, c["text"])
            leaks: list[tuple[str, str]] = []  # a drawing sheet or page header cut off the end (leak_cut)
            older = (m["decided_at"] or "") < RECENT_FROM
            # the reading to show is picked on the text without tail_cut's and inside_cut's cuts, so they never
            # change which reading is shown; the picked reading is cut after reread (below)
            text = clean(c["text"], v, older, leaks, cut_tails=False)
            uncut = clean(c["text"], v, older, cut_leaks=False) if leaks else text
            # a split-off condition whose text the first reading cut off: only its title is left
            cut = "_split_from" in c and len(letters(text)) <= len(letters(c["title"])) + 40
            entries.append({
                "_id": m["id"],
                "record": m["record"],
                "address": (m["address"] or "").title(),
                "zoning": m["zoning"] or "",
                "business": BUSINESS[m["use_class"]],
                "decided": m["decided_at"],
                "year": (m["decided_at"] or "")[:4],
                "number": c["number"],
                "title": c["title"],
                "text": text,
                "categories": c["categories"] or [],
                "standard": c["standard"],
                "kind": "boilerplate" if boiler else "standard" if c["standard"] or template else "specific",
                "template": template,
                "split_from": c.get("_split_from"),
                "motion_url": m["motion_url"],
                "pdf": local,
                "page": page,
                "page_exact": exact,
                "_raw": c["text"],
                "_raw_garbled": garbled(raw_bad, c["text"]),
                "_bad": badness(v, text),
                "_cut": cut,
                "_reading": c["text"],
                "_ocr_anyway": bool(leaks) and garbled(badness(v, uncut), uncut),
                "text_source": "clean-up" if text != c["text"] else "first reading",
            })  # fmt: skip

    # conditions run in order through a motion: a page before the previous condition's is a wrong match of a
    # passage further in; it is moved to the previous condition's page and marked approximate
    def order(e: dict) -> tuple[int, int, str]:
        return number_order(e["number"])

    by_record: dict[str, list[dict]] = {}
    for e in entries:
        by_record.setdefault(e["record"], []).append(e)
    for es in by_record.values():
        last = 0
        for e in sorted(es, key=order):
            if e["page"] is not None and e["page"] < last:
                e["page"], e["page_exact"] = last, False
                found["moved back into order"] += 1
            last = max(last, e["page"] or 0)

    reread(entries, vocab, vocab_recent)
    quality: Counter[str] = Counter()
    attested = attested_titles(entries)  # before any title is changed
    retitled = []
    leaks_cut = []
    for e in entries:
        # the reading picked, cleaned again with every cut: page furniture, a section heading, a file path, the
        # plan set's title, an image page's OCR noise or the next condition's title (one of the attested titles)
        # after the condition's last sentence (tail_cut) and page furniture inside it (inside_cut)
        v = vocab_recent if (e["decided"] or "") >= RECENT_FROM else vocab
        e["_leaks"] = []
        older = (e["decided"] or "") < RECENT_FROM
        text = clean(e["_reading"], v, older, e["_leaks"], titles=attested.keys())
        if text != e["text"]:
            e["text"], e["_bad"] = text, badness(v, text)
            if e["text_source"] == "first reading":
                e["text_source"] = "clean-up"
        old_title = e["title"]
        if (title := reread_title(e)) is not None:
            retitle(e, title, standard_ctx)
            quality["title read again from its condition's second reading"] += 1
        elif (found_title := attested_title(e, attested)) is not None:
            retitle(e, found_title[0], standard_ctx)
            quality[
                "title read again from its condition's second reading"
                if found_title[1] == "heading"
                else f"title read again: an OCR misreading of a title used on {ATTESTED_MIN}+ conditions"
            ] += 1
        if e["title"] != old_title:
            retitled.append((e["record"], e["number"], old_title, e["title"], e["kind"]))
        still = garbled(e["_bad"], e["text"]) or e["_cut"]
        if e["split_from"]:
            quality["split out of the condition before it"] += 1
            if e["_cut"]:
                quality["split out, text cut off in every reading (flagged)"] += 1
        if e["_raw_garbled"]:
            quality["garbled as extracted"] += 1
            quality["still unreadable" if still else f"fixed by {e['text_source']}"] += 1
        elif still:  # clean before, garbled now: never happens, but the page must not show junk either way
            quality["garbled after clean-up (unexpected)"] += 1
        for kind, cut_text in e["_leaks"]:
            quality[f"{kind} text cut off"] += 1
            leaks_cut.append((e["record"], e["number"], e["decided"], kind, cut_text))
        # a private liaison's name and contact details: "[contact in the motion]" (the PDF link stays)
        e["text"] = withhold_private_contacts(e["text"])
        e["readable"] = not still
        e["raw_text"] = withhold_private_contacts(e["_raw"]) if still else None
        for k in ("_id", "_raw", "_raw_garbled", "_bad", "_cut", "_leaks", "_ocr_anyway", "_reading"):
            e.pop(k)

    entries.sort(key=lambda e: (e["decided"] or "", e["record"], order(e)))
    with_conditions = {e["record"] for e in entries}
    no_conditions = [
        {"record": m["record"], "address": (m["address"] or "").title(), "decided": m["decided_at"],
         "outcome": m["doc_outcome"] or "", "why": m["note"] or "no conditions extracted"}
        for m in kept if m["record"] not in with_conditions
    ]  # fmt: skip
    def classifier_says(m: dict) -> str:
        if m["premises"] is not True:
            return "not a food-or-drink premises"
        if (m.get("_classifier_use", m["use_class"]) or "none") == "none":
            return "premises, but no food-or-drink use"
        return "food or drink (" + BUSINESS[m.get("_classifier_use", m["use_class"])].lower() + ")"

    # a reviewed decision's description and reason also go on a motion the classifier had already left out
    decision_of = {d["record"]: d for d in review.get("decisions", [])}
    gone = [
        {"record": m["record"], "address": (m["address"] or "").title(), "decided": m["decided_at"],
         "what": decision_of.get(m["record"], {}).get("what") or what_it_is(m["description"]),
         "tagged_before": m["label"] or "",
         "classifier": classifier_says(m),
         "left_out_by": "review" if m.get("_review") else "classifier",
         "reason": decision_of.get(m["record"], {}).get("reason") or "",
         "conditions": len(by_motion.get(m["id"], []))}
        for m in removed
    ]  # fmt: skip
    conditions_on_page = Counter(e["record"] for e in entries)

    def changed(m: dict) -> dict:
        d = m["_review"]
        return {"record": m["record"], "address": (m["address"] or "").title() or d.get("address") or "",
                "decided": m["decided_at"], "what": d.get("what") or what_it_is(m["description"]),
                "reason": d.get("reason") or "", "business": BUSINESS[m["use_class"]] if m in kept else None,
                "classifier": classifier_says(m), "conditions": conditions_on_page.get(m["record"], 0)
                if m in kept else len(by_motion.get(m["id"], []))}  # fmt: skip

    applied = {d["record"]: "added back" for d in (m["_review"] for m in reviewed["added"])}
    applied |= {m["record"]: "removed" for m in reviewed["removed"]}
    applied |= {m["record"]: "business type set" for m in reviewed["business_set"]}
    applied |= {d["record"]: "no change: already as decided" for d in reviewed["no_change"]}
    applied |= {d["record"]: "no change: not among the motions found" for d in reviewed["not_found"]}
    review_out = {
        "file": REVIEWED.name if REVIEWED.exists() else None,
        "reviewed_on": review.get("reviewed_on"),
        "classifier_kept": classifier_kept,
        "classifier_removed": classifier_removed,
        "added_back": [changed(m) for m in reviewed["added"]],
        "removed": [changed(m) for m in reviewed["removed"]],
        "business_set": [changed(m) for m in reviewed["business_set"]],
        "decisions": [
            {"record": d["record"], "address": d.get("address") or "", "decision": d["decision"],
             "business": d.get("business"), "what": d.get("what") or "", "reason": d.get("reason") or "",
             "applied": applied.get(d["record"], "")}
            for d in review.get("decisions", [])
        ],
    }  # fmt: skip
    kinds = Counter(e["kind"] for e in entries)
    coverage = coverage_facts(kept, motions)
    (OUT / "data" / "conditions.json").write_text(json.dumps({
        "_doc": "Conditions of approval extracted from San Francisco Planning Commission motions on food, drink "
                "and entertainment premises (local tables case_conditions, case_motions, record_labels). Built "
                "by scripts/validation/build_conditions_index.py.",
        "count": len(entries),
        "motions": len(kept),
        "motions_with_conditions": len(with_conditions),
        "motions_without_conditions": no_conditions,
        "removed_motions": gone,
        "review": review_out,
        "boilerplate_titles": sorted(set(BOILERPLATE_TITLES.values())),
        "kinds": dict(kinds),
        "template_parts_counted_standard": sum(e["template"] for e in entries),
        "text_quality": dict(quality),
        "coverage": coverage,
        "conditions": entries}, indent=0, ensure_ascii=False) + "\n")  # fmt: skip

    print(f"{len(motions)} motions found; the classifier kept {classifier_kept} and left out {classifier_removed}; "
          f"the review ({review_out['file'] or 'no reviewed list yet'}) added back {len(reviewed['added'])}, "
          f"removed {len(reviewed['removed'])}, set the business of {len(reviewed['business_set'])}; "
          f"final: kept {len(kept)}, left out {len(removed)}")  # fmt: skip
    for d in reviewed["not_found"]:
        print(f"review: {d['record']} is not among the motions found; nothing changed")
    print(f"{len(entries)} conditions from {len(with_conditions)} motions; "
          f"{len(no_conditions)} kept motion(s) without conditions: "
          + ", ".join(f"{m['record']} ({m['outcome'] or m['why']})" for m in no_conditions))  # fmt: skip
    print(f"kinds: {dict(kinds)} (lettered template parts counted standard: {sum(e['template'] for e in entries)}; "
          f"{sum(e['split_from'] is not None for e in entries)} split out after a missed heading)")  # fmt: skip
    print(f"pages: {dict(found)}")
    for record, number, old, new, kind in retitled:
        print(f"title: {record} {number}: {old!r} -> {new!r} ({kind})")
    for record, number, decided, kind, cut_text in leaks_cut:
        print(f"cut off ({kind}): {record} {number} ({decided}): {cut_text[:120]!r}")
    print(f"text quality: {dict(quality)}")
    print(f"coverage: {coverage['cases_looked_up']} cases looked up since {coverage['since']}, "
          f"{coverage['motions_found']} motions found, {len(coverage['not_found'])} not found; kept motions decided "
          f"{coverage['decided_from']} to {coverage['decided_to']}; records copied {coverage['records_copied_on']}, "
          f"motions looked up {coverage['motions_looked_up_on']}")  # fmt: skip
    print("\nleft out:")
    for g in gone:
        print(f"  {g['record']:<18} {g['address'][:34]:<34} [{g['left_out_by']}: {g['classifier']}; "
              f"was '{g['tagged_before']}'] {g['what'][:90]}")  # fmt: skip
    for key, label in (("added_back", "added back by review"), ("business_set", "business set by review")):
        for g in review_out[key]:
            print(f"{label}: {g['record']:<18} {g['address'][:34]:<34} as {g['business']}: {g['what'][:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
