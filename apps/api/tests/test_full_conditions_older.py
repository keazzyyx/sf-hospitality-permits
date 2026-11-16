"""scripts/validation/full_conditions.py and build_conditions_index.py with the 2010-2018 motions: which reading a
motion gets (by case_motions.decided_at), the second readings, and the standard rule. No network, no database
(the standard() test records the SQL against a fake connection)."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
VALIDATION = REPO / "scripts" / "validation"
OLDER = REPO / "packages" / "precedent" / "tests" / "fixtures" / "sf_planning_hearings" / "older"


def load(name: str) -> ModuleType:
    if str(VALIDATION) not in sys.path:
        sys.path.insert(0, str(VALIDATION))  # build_conditions_index imports its siblings
    spec = importlib.util.spec_from_file_location(name, VALIDATION / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fc() -> ModuleType:
    return load("full_conditions")


@pytest.fixture(scope="module")
def bci() -> ModuleType:
    return load("build_conditions_index")


def sidecar(tmp_path: Path, record: str, pdf: str, hearing_date: str) -> Path:
    shutil.copy(OLDER / pdf, tmp_path / pdf)
    path = tmp_path / f"20261113T000000Z-{record}-motion.json"
    meta = {"fetched_at": "2026-11-13T00:00:00+00:00", "record_number": record, "hearing_date": hearing_date,
            "source_kind": "motion", "pdf": pdf}  # fmt: skip
    path.write_text(json.dumps({"meta": meta, "data": {"pdf": pdf}}))
    return path


def test_older_formats_by_decided_at(fc: ModuleType) -> None:
    assert fc.older_formats(dt.date(2018, 12, 31))
    assert fc.older_formats("2011-10-06")
    assert not fc.older_formats(dt.date(2019, 1, 1))
    assert not fc.older_formats("2019-01-16")
    assert not fc.older_formats(None)


def test_extract_gates_on_case_decided_at_not_the_motion_date(fc: ModuleType, tmp_path: Path) -> None:
    """2016-000378CUA, 2018-005694CUA and 2018-010482CUA were decided (case_motions.decided_at) in January 2019 on
    a 2018 motion date; the site counts them as 2019, so they must get the 2019+ reading. Here the 2011.0571C motion
    (non-breaking spaces, read only by the older formats) stands in for such a motion."""
    path = sidecar(tmp_path, "2011.0571C", "2011.0571C.pdf", "2011-10-06")
    _meta, parsed, conds, numbered, has_section = fc.extract(path, dt.date(2011, 10, 6))
    assert parsed.decided_at is not None and parsed.decided_at.year == 2011
    assert has_section and numbered
    assert [c.number for c in conds] == [str(n) for n in range(1, 10)]
    # same motion, case decided in 2019: the 2019+ reading (nothing numbered, so the sentence fallback)
    _meta, parsed, conds, numbered, has_section = fc.extract(path, dt.date(2019, 1, 16))
    assert (
        parsed.decided_at is not None and parsed.decided_at.year == 2011
    )  # the motion's own date is ignored
    assert has_section and not numbered
    assert {c.title for c in conds} == {"Condition"}


def test_parse_conditions_reads_older_motions_the_older_way(bci: ModuleType) -> None:
    from precedent.pdftext import read_pdf
    from precedent.sources import sf_planning_hearings as H  # noqa: N812

    doc = read_pdf((OLDER / "2011.0571C.pdf").read_bytes(), max_pages=H.MOTION_MAX_PAGES, stop=H.is_plan_page)
    older = bci.parse_conditions(doc.text, older_formats=True)
    assert list(older) == [str(n) for n in range(1, 10)]
    assert older["9"][0] == "Noise Control"
    assert "1" not in bci.parse_conditions(
        doc.text
    )  # the 2019+ reading: non-breaking spaces, no titled conditions


def test_reread_passes_older_formats_by_decided_at(bci: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, bool]] = []

    def fake_parse(text: str, older_formats: bool = False) -> dict:
        seen.append((text, older_formats))
        return {}

    monkeypatch.setattr(bci, "parse_conditions", fake_parse)
    monkeypatch.setattr(bci, "pdf_for", lambda record: Path(f"/nonexistent/{record}.pdf"))
    monkeypatch.setattr(bci, "text_layer", lambda pdf: f"text of {pdf.stem}")
    monkeypatch.setattr(bci.shutil, "which", lambda name: None)  # no OCR
    entries = [
        {"record": "2012.0370C", "decided": "2012-10-25", "number": "1", "title": "Validity", "text": "Validity: x",
         "_bad": ["x"], "_cut": True, "page": 1},
        {"record": "2018-005694CUA", "decided": "2019-01-16", "number": "1", "title": "Validity",
         "text": "Validity: x", "_bad": ["x"], "_cut": True, "page": 1},
    ]  # fmt: skip
    bci.reread(entries, vocab=None)
    assert sorted(seen) == [("text of 2012.0370C", True), ("text of 2018-005694CUA", False)]


def test_condition_order_with_restarted_lists(bci: ModuleType) -> None:
    """build_conditions_index orders a motion's conditions by number before checking pages; "2.3" (second list)
    follows the whole first list."""
    conds = [{"id": "m", "number": n, "text": "T: x"} for n in ("1", "6", "2.2", "2.3")]
    out = bci.split_run_ons(conds)
    assert [c["number"] for c in out] == ["1", "6", "2.2", "2.3"]


NOTICES = ("Notices shall be well-lit and prominently displayed at all entrances to and exits from the establishment "
           "urging patrons to leave the establishment and neighborhood in a quiet, peaceful, and orderly fashion")  # fmt: skip


def test_page_of_an_untitled_older_condition_is_exact_on_its_page(bci: ModuleType) -> None:
    """2009.0773C #14: an untitled condition is stored as "Condition: Notices shall be..." under the generic title
    "Condition", which the motion does not print. Its opening words are on page 14, so the page is exact, not
    "near page 14"."""
    pages = [
        "Motion No. 18030",
        "findings",
        "CONDITIONS OF APPROVAL\n13. Hours shall be...",
        f"14. {NOTICES[:40]}\n{NOTICES[40:]} and to please not litter.",
    ]
    cond = {"title": "Condition", "text": f"Condition: {NOTICES}"}
    assert bci.page_of(pages, cond) == (4, True)
    # across a page break: the two pages joined
    split = ["x", f"14. {NOTICES[:20]}", f"{NOTICES[20:]}."]
    assert bci.page_of(split, {"title": "Condition", "text": f"Condition: {NOTICES[:60]}"}) == (2, True)
    # a titled condition printed differently (title on its own line, no colon) stays approximate, as before
    titled = {"title": "Good Neighbor", "text": f"Good Neighbor: {NOTICES}"}
    assert bci.page_of(pages, titled) == (4, False)
    # a titled condition whose title is printed is exact, as before
    printed = ["x", f"Good Neighbor. {NOTICES}"]
    assert bci.page_of(printed, titled) == (2, True)
    # opening words not on any page: approximate from a window further in, never exact
    late = ["x", f"something else entirely {NOTICES[60:]}"]
    page, exact = bci.page_of(late, cond)
    assert page == 2 and not exact


class FakeConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def __enter__(self) -> FakeConn:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> FakeConn:
        self.calls.append((sql, params))
        self._last = sql
        return self

    def fetchall(self) -> list:
        if "group by 1" in self._last and "case_motions" in self._last:
            return [("restaurant_or_cafe", 20), ("bar", 3)]
        return []


def test_standard_title_rule_leaves_out_the_generic_title(
    fc: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Untitled 2009-2010 conditions all have the title "Condition"; the title rule (a title on half the approved
    motions) must not call them standard. The wording rule is unchanged."""
    conn = FakeConn()
    monkeypatch.setattr(fc.psycopg, "connect", lambda *a, **k: conn)
    fc.standard()
    title_rule = [(sql, p) for sql, p in conn.calls if "with approved as" in sql]
    assert len(title_rule) == 2
    for sql, params in title_rule:
        assert "c.norm_title <> %(generic)s" in sql
        assert params["generic"] == "condition"
    assert fc.norm_title("Condition (B)") == "condition"  # sub-items of untitled conditions too
    wording_rule = [sql for sql, _ in conn.calls if "wording_key in" in sql]
    assert len(wording_rule) == 1 and "generic" not in wording_rule[0]


def test_conditions_section_cuts_exhibit_c_for_older_motions_only(fc: ModuleType) -> None:
    """2012.0370C: the Mitigation Monitoring and Reporting Program after the conditions was read as conditions 20-23
    (its heading repeats on every page, so it was stripped as a running header). Cut for older motions only."""
    from precedent.pdftext import read_pdf
    from precedent.sources import sf_planning_hearings as H  # noqa: N812

    doc = read_pdf((OLDER / "2012.0370C.pdf").read_bytes(), max_pages=H.MOTION_MAX_PAGES, stop=H.is_plan_page)
    older = H.all_conditions(fc.conditions_section(doc.text, True), older_formats=True)
    assert [c.number for c in older] == [str(n) for n in range(1, 20)]
    assert older[-1].title == "Community Liaison" and older[-1].categories == ("community_liaison",)
    # the 2019+ reading of the same text is not cut
    assert "Mitigation Measure M" in fc.conditions_section(doc.text, False).replace("\xa0", " ")


def test_extract_reads_an_older_motion_again_with_pdftotext_when_its_text_ends_early(
    fc: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2011.0026C: pypdf's text ended at a short findings page taken for a plan sheet, before Exhibit A. An older
    motion with no conditions section is read again with pdftotext; a 2019+ motion never is."""
    from precedent.pdftext import PdfText

    path = sidecar(tmp_path, "2011.0571C", "2011.0571C.pdf", "2011-10-06")
    first = "Motion No. 18420\nFINDINGS\n1. The Commission finds the project desirable.\n"
    findings_end = (
        "Motion 18420\nAugust 4, 2011\n\nCASE NO. 2011.0026 C\n11. The Commission finds approval desirable.\n"
    )
    exhibit = (
        "Motion 18420\nCASE NO. 2011.0026 C\nEXHIBIT A\nCONDITIONS OF APPROVAL\nPERFORMANCE\n"
        "1.\n\nValidity and Expiration. The authorization is valid for three years from the effective date.\n\n"
        "2.\n\nExtension. This authorization may be extended at the discretion of the Zoning Administrator.\n\n"
        "3.\n\nNoise Control. The premises shall be adequately soundproofed or insulated for noise.\n"
    )
    calls: list[str] = []

    def poppler(pdf: Path, max_pages: int | None = None, stop: Any = None) -> PdfText:
        calls.append(stop.__name__)
        pages = [first, findings_end, exhibit]
        kept = [p for i, p in enumerate(pages) if not stop(i, p)]
        assert kept == pages  # the short findings page does not end the second reading
        return PdfText("\n\f\n".join(kept), 3)

    monkeypatch.setattr(fc, "read_pdf", lambda *a, **k: PdfText(first, 3))
    monkeypatch.setattr(fc, "read_pdf_poppler", poppler)
    _meta, _parsed, conds, numbered, has_section = fc.extract(path, "2011-08-04")
    assert calls == ["is_plan_page_older"]
    assert has_section and numbered
    assert [(c.number, c.title) for c in conds] == [
        ("1", "Validity and Expiration"),
        ("2", "Extension"),
        ("3", "Noise Control"),
    ]
    calls.clear()
    _meta, _parsed, conds, _numbered, has_section = fc.extract(path, "2019-01-16")
    assert calls == [] and not has_section and conds == []


def test_later_motion(fc: ModuleType) -> None:
    """A motion dated more than a year after the case's decision is for a later decision (2015-002658CUA, decided
    2015-12-11, got Motion No. 21682 of 2025-02-13, the motion of 2015-002658CUA-02). Older-formats cases only: the
    published 2019+ motions stay as they are (2019-004110CUA, decided 2020-07-17, carries a 2024 motion)."""
    from types import SimpleNamespace

    later = SimpleNamespace(decided_at=dt.date(2025, 2, 13))
    assert fc.later_motion(later, {}, dt.date(2015, 12, 11))
    assert fc.later_motion(later, {}, "2015-12-11")
    assert not fc.later_motion(SimpleNamespace(decided_at=dt.date(2016, 12, 1)), {}, dt.date(2015, 12, 11))
    assert not fc.later_motion(SimpleNamespace(decided_at=dt.date(2007, 8, 9)), {}, dt.date(2015, 3, 19))
    assert not fc.later_motion(SimpleNamespace(decided_at=dt.date(2024, 3, 7)), {}, dt.date(2020, 7, 17))
    # no date in the motion's text: the sidecar's hearing date
    assert fc.later_motion(SimpleNamespace(decided_at=None), {"hearing_date": "2025-02-13"}, "2015-12-11")
    assert not fc.later_motion(SimpleNamespace(decided_at=None), {}, "2015-12-11")


def test_extract_refuses_a_motion_for_a_later_decision(fc: ModuleType, tmp_path: Path) -> None:
    """The 2011.0571C motion (adopted 2011-10-06) attached to a case decided in 2010 gives no conditions; the same
    motion for its own decision is read as usual."""
    path = sidecar(tmp_path, "2011.0571C", "2011.0571C.pdf", "2011-10-06")
    _meta, parsed, conds, numbered, has_section = fc.extract(path, "2010-06-01")
    assert parsed.decided_at == dt.date(2011, 10, 6)
    assert conds == [] and not numbered and not has_section
    _meta, _parsed, conds, numbered, has_section = fc.extract(path, "2011-10-06")
    assert has_section and numbered and len(conds) == 9


class ReparseConn(FakeConn):
    def __init__(self, rows: list[tuple]) -> None:
        super().__init__()
        self.rows = rows
        self.stored: list[tuple] = []

    def fetchall(self) -> list:
        return self.rows if "from case_motions where found" in self._last else []

    def cursor(self) -> ReparseConn:
        return self

    def executemany(self, sql: str, params: list) -> None:
        self.stored.extend(params)


def test_reparse_marks_a_motion_for_a_later_decision_not_found(
    fc: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "raw"
    (raw / fc.H.NAME).mkdir(parents=True)
    sidecar(raw / fc.H.NAME, "2011.0571C", "2011.0571C.pdf", "2011-10-06")
    conn = ReparseConn([("datasf_planning:2011.0571C", "2011.0571C", dt.date(2010, 6, 1))])
    monkeypatch.setattr(fc, "RAW", raw)
    monkeypatch.setattr(fc.psycopg, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(fc, "standard", lambda: None)
    assert fc.reparse() == 0
    updates = [(sql, p) for sql, p in conn.calls if sql.startswith("update case_motions")]
    assert len(updates) == 1
    sql, params = updates[0]
    assert "found=false" in sql and params == (fc.LATER_NOTE, "datasf_planning:2011.0571C")
    assert fc.LATER_NOTE == "motion found is for a later decision"
    assert ("delete from case_conditions where id = %s", ("datasf_planning:2011.0571C",)) in conn.calls
    assert conn.stored == []
    # the motion for its own decision: conditions stored, still found
    conn.rows = [("datasf_planning:2011.0571C", "2011.0571C", dt.date(2011, 10, 6))]
    conn.calls.clear()
    fc.reparse()
    sql, params = next((s, p) for s, p in conn.calls if s.startswith("update case_motions"))
    assert "found" not in sql and params[1] == 9
    assert len(conn.stored) == 9


def test_attested_title_reads_ocr_misreadings_of_a_common_title_again(bci: ModuleType) -> None:
    def cond(title: str, decided: str = "2016-06-21", text: str | None = None) -> dict[str, Any]:
        return {"title": title, "decided": decided, "text": text or f"{title}: Should implementation of ..."}

    common = ["Revocation due to Violation of Conditions", "Garbage, composting and recycling storage",
              "Notices Posted at Bars and Entertainment Venues", "Eating and Drinking Uses (A)", "Lighting"]  # fmt: skip
    attested = bci.attested_titles(
        [cond(t) for t in common for _ in range(bci.ATTESTED_MIN)] + [cond("Rare")]
    )
    assert set(attested.values()) == set(common)
    assert bci.attested_title(cond("Revocation dne to Violation of Conditions"), attested) == (
        "Revocation due to Violation of Conditions", "attested")  # fmt: skip
    assert bci.attested_title(cond("Notices Posted at Bars and Entertainmen# Venues"), attested) == (
        "Notices Posted at Bars and Entertainment Venues", "attested")  # fmt: skip
    # the kept reading's own heading, when it is an attested title
    gaz = cond("Gazbage, composting and recycling storage", "2017-07-21",
               "Garbage, composting and recycling storage: Space for the collection ...")  # fmt: skip
    assert bci.attested_title(gaz, attested) == ("Garbage, composting and recycling storage", "heading")
    # never on 2019+ motions; never a title that is itself attested
    assert (
        bci.attested_title(cond("Revocation dne to Violation of Conditions", "2019-01-01"), attested) is None
    )
    assert (
        bci.attested_title(cond("Diligent pursuit"), attested | {"diligentpursuit": "Diligent Pursuit"})
        is None
    )
    # not another lettered part, not a short title one letter off, not a word added or lost
    assert bci.attested_title(cond("Eating and Drinking Uses (E)"), attested) is None
    assert bci.attested_title(cond("Sighting"), attested) is None
    assert bci.attested_title(cond("Revocation due to Violation of Condition"), attested) is None
    assert bci.ocr_swaps("Gazbage", "Garbage") == 1
    assert bci.ocr_swaps("Chapter 117", "Chapter 116") is None  # a digit for a digit is another number
    assert bci.ocr_swaps("Viola tion", "Violation") is None


def test_standard_by_rules_counts_the_new_title(bci: ModuleType) -> None:
    fc = load("full_conditions")
    motions = [{"id": f"m{i}", "label": "bar", "doc_outcome": "approved_with_conditions"} for i in range(8)]
    body = "Notices urging patrons to leave the establishment quietly."
    conds = [{"id": f"m{i}", "norm_title": "noticespostedatbarsandentertainmentvenues",
              "wording_key": fc.wording_key("Notices Posted at Bars and Entertainment Venues", f"x: {body} {i}")}
             for i in range(1, 4)]  # fmt: skip
    ctx = bci.standard_context(conds, motions)
    title = "Notices Posted at Bars and Entertainment Venues"
    assert not bci.standard_by_rules("m0", title, f"{title}: {body}", [], ctx)  # the title on 3 of 8 motions
    ctx["titles"]["noticespostedatbarsandentertainmentvenues"].add("m0")
    assert bci.standard_by_rules("m0", title, f"{title}: {body}", [], ctx)  # 4 of 8: half
    assert not bci.standard_by_rules("m0", title, f"{title}: {body}", ["hours"], ctx)


def test_clean_finds_split_and_interleaved_contact_lines_on_older_motions_only() -> None:
    from condition_text import clean

    split = ("Sidewalk Maintenance: The Project Sponsor shall maintain all sidewalks in compliance with the Department "
             "of Public Works Streets and Sidewalk Maintenance Standards. For information about c ompliance, contact "
             "Bureau of Street Use and Mapping, Department of Public Works, 415-695-2017, http://sfdpw.org")  # fmt: skip
    interleaved = ("Sidewalk Maintenance: The Project Sponsor shall maintain all sidewalks in compliance with the For "
                   "information about Department of Public Works Streets and Sidewalk Maintenance Standards. "
                   "compliance, contact Bureau of Street Use and Mapping, Department of Public Works, 415-695-2017, "
                   ".http:Ilsfdpw.org/")  # fmt: skip
    whole = ("Sidewalk Maintenance: The Project Sponsor shall maintain all sidewalks in compliance with the Department "
             "of Public Works Streets and Sidewalk Maintenance Standards.")  # fmt: skip
    assert clean(split, older=True) == whole
    assert clean(interleaved, older=True) == whole
    # 2019+ motions are cleaned as before
    assert "c ompliance" in clean(split) and "For information about" in clean(interleaved)
