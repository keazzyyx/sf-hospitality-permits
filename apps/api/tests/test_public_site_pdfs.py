"""scripts/validation/build_public_conditions_site.py, the hosted motion PDFs: motions decided 2019 on keep the copies
hosted since 2026-11-12 (same rules, same cache version, cached copies reused), motions decided before 2019 get the
harder copies. No ghostscript, no network, no database: the copy makers are replaced by fakes."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[3]
VALIDATION = REPO / "scripts" / "validation"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_public_conditions_site", VALIDATION / "build_public_conditions_site.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("build_public_conditions_site", module)
    spec.loader.exec_module(module)
    return module


B = load()


def test_harder_by_decided_date() -> None:
    assert B.harder("2018-12-31")
    assert B.harder("2010-01-04")
    assert not B.harder("2019-01-01")
    assert not B.harder("2026-09-03")
    assert not B.harder(None)  # no date: the 2019-on copy
    assert not B.harder("")


def test_2019_on_rules_are_the_ones_hosted_since_2026_11_12() -> None:
    # changing any of these changes the bytes of the 110 hosted 2019-on copies (they would all be made again)
    assert B.PDF_CACHE_VERSION == 4
    assert B.GS_SETTINGS == {
        "ebook": ["-dPDFSETTINGS=/ebook"],
        "100dpi": ["-dPDFSETTINGS=/ebook", "-dDownsampleColorImages=true", "-dColorImageResolution=100",
                   "-dDownsampleGrayImages=true", "-dGrayImageResolution=100", "-dDownsampleMonoImages=true",
                   "-dMonoImageResolution=200"],
        "screen": ["-dPDFSETTINGS=/screen"],
    }  # fmt: skip
    assert (B.HEAVY_PAGE_BYTES, B.RASTER_DPI, B.RASTER_JPEG_QUALITY) == (200_000, 100, 60)
    assert B.OLDER_PDF_CACHE_VERSION != B.PDF_CACHE_VERSION
    # the 2019-on span: first condition's page to two pages after the last one's
    assert B.condition_span([{"page": 5, "text": "x"}, {"page": 7, "text": "y"}, {"text": "z"}]) == (5, 9)
    assert B.condition_span([{"text": "z"}]) is None


def test_older_condition_span_ends_where_the_last_condition_ends() -> None:
    last = "Hours of operation: the business shall close by eleven at night every day of the week."
    texts = [B.letters(t) for t in ("cover", "findings", "Validity: the authorization lasts three years.",
                                    "Hours of operation: the business shall",
                                    "close by eleven at night every day of the week. Exhibit B", "plans", "plans")]  # fmt: skip
    conds = [{"page": 3, "text": "Validity: the authorization lasts three years."}, {"page": 4, "text": last}]
    assert B.older_condition_span(conds, texts) == (3, 5)
    # closing words not found: two pages after the last one's, as for 2019 on
    conds[1]["text"] = last.replace("week", "month and every holiday of the year")
    assert B.older_condition_span(conds, texts) == (3, 6)
    assert B.older_condition_span([{"text": "no page"}], texts) is None


def test_page_plan() -> None:
    assert B.page_plan(6, (2, 3), [6]) == {
        1: "rest",
        2: "text",
        3: "text",
        4: "rest",
        5: "rest",
        6: "picture",
    }
    assert set(B.page_plan(3, (2, 2), whole=True).values()) == {"text"}
    assert set(B.page_plan(3, None).values()) == {
        "text"
    }  # no condition page: every page keeps the gentler setting


def test_raster_dpi_caps_big_sheets() -> None:
    assert B.raster_dpi(None) == B.OLDER_RASTER_DPI
    assert B.raster_dpi((612, 792)) == B.OLDER_RASTER_DPI  # letter
    assert B.raster_dpi((2592, 1728)) == int(B.RASTER_MAX_PIXELS * 72 / 2592)  # 36 x 24 in plan sheet
    assert B.raster_dpi((100_000, 100)) == 24


@pytest.fixture
def fake_pdf_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """compress_pdf with its cache in tmp_path and the copy makers / PDF tools replaced by fakes."""
    calls: dict[str, list[str]] = {"standard": [], "older": []}
    monkeypatch.setattr(B, "PDF_CACHE", tmp_path / "cache")
    monkeypatch.setattr(B, "page_count", lambda pdf: 3)
    monkeypatch.setattr(B, "page_texts", lambda pdf: ["", "", ""])
    monkeypatch.setattr(B, "check_pdf", lambda original, small, conditions: [])

    def maker(kind: str):  # type: ignore[no-untyped-def]
        def make(original: Path, conditions: list[dict], tmp: Path):  # type: ignore[no-untyped-def]
            calls[kind].append(original.name)
            best = B.Best(original, conditions, tmp)
            small = tmp / "small.pdf"
            small.write_bytes(b"%PDF " + kind.encode())
            best.consider(kind, small)
            return best, []

        return make

    monkeypatch.setattr(B, "standard_compress", maker("standard"))
    monkeypatch.setattr(B, "older_compress", maker("older"))
    return calls


def test_compress_pdf_routes_by_decided_and_keeps_2019_on_cache(tmp_path: Path, fake_pdf_tools: dict) -> None:
    original = tmp_path / "motion.pdf"
    original.write_bytes(b"%PDF original motion, longer than any copy")
    conds = [{"number": "1", "page": 2, "text": "Validity: the authorization lasts three years."}]

    out, meta = B.compress_pdf("2021-000001CUA", original, conds, "2021-05-06")
    assert (meta["version"], meta["setting"], out.read_bytes()) == (
        B.PDF_CACHE_VERSION,
        "standard",
        b"%PDF standard",
    )
    out, meta = B.compress_pdf("2015-000001CUA", original, conds, "2015-05-07")
    assert (meta["version"], meta["setting"], out.read_bytes()) == (
        B.OLDER_PDF_CACHE_VERSION,
        "older",
        b"%PDF older",
    )

    # a cached 2019-on copy is reused as it is: not made again
    out, meta = B.compress_pdf("2021-000001CUA", original, conds, "2021-05-06")
    assert out.read_bytes() == b"%PDF standard" and "remade" not in meta
    assert fake_pdf_tools == {"standard": ["motion.pdf"], "older": ["motion.pdf"]}

    # a 2019-on copy (cache version 4) is not taken for a pre-2019 motion, nor the other way round
    out, meta = B.compress_pdf("2021-000001CUA", original, conds, "2018-12-20")
    assert meta["version"] == B.OLDER_PDF_CACHE_VERSION and out.read_bytes() == b"%PDF older"
    cached = json.loads((B.PDF_CACHE / "2021-000001CUA.json").read_text())
    assert cached["version"] == B.OLDER_PDF_CACHE_VERSION
