from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
NOW = dt.datetime(2026, 10, 21, tzinfo=dt.UTC)


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def tmp_store(tmp_path: Path):  # type: ignore[no-untyped-def]
    from precedent.store.local import LocalStore

    return LocalStore(tmp_path / "data")


def pg_url() -> str | None:
    return os.environ.get("PRECEDENT_TEST_DATABASE_URL")


requires_postgis = pytest.mark.skipif(
    pg_url() is None, reason="set PRECEDENT_TEST_DATABASE_URL to a PostGIS database"
)


# ---- hearing PDFs not shipped in the public repository ---------------------------------------------------------
# The real Planning Commission motion and minutes PDFs these tests read name private project sponsors,
# property owners and public-comment speakers, so they are not in the public repository. The tests are
# skipped while the files are absent; put the public PDFs back in _HEARING_PDF_DIR to run them.
_HEARING_PDF_DIR = os.path.join(os.path.dirname(__file__), "tests/fixtures/sf_planning_hearings")
_HEARING_PDFS = (
    "older/2009.1001C.pdf",
    "older/2011.0571C.pdf",
    "older/2012.0370C.pdf",
    "older/2012.0638C.pdf",
    "pdf/5714b666a850d80e05a43709.pdf",
    "pdf/688d3ede20f33f3249f3f85b.pdf",
    "pdf/6c49eb778dc870cacbc5bb9e.pdf",
    "pdf/876deb281e43f0c86989fd55.pdf",
)
_NEEDS_HEARING_PDFS = {
    "test_hearings.py::test_motion_hours_condition_bar",
    "test_hearings.py::test_motion_conditioned_approval_with_opposition",
    "test_hearings.py::test_motion_denial",
    "test_hearings.py::test_motion_takes_hearing_opposition_from_minutes",
    "test_hearings.py::test_minutes_rows_are_decisive_cua_items_only",
    "test_hearings.py::test_minutes_skip_records_already_covered_by_a_motion",
    "test_hearings.py::test_minutes_item_parser_handles_continuances_and_same_as_speakers",
    "test_hearings.py::test_scanned_or_broken_pdf_is_low_confidence",
    "test_hearings.py::test_missing_pdf_yields_empty_batch",
    "test_hearings.py::test_extract_text_is_tolerant",
    "test_hearings.py::test_fetch_minutes_then_motions_with_cache_and_cap",
    "test_hearings.py::test_fetch_respects_document_cap",
    "test_hearings_older.py::test_untitled_numbered_paragraphs_2009",
    "test_hearings_older.py::test_non_breaking_spaces_2011",
    "test_hearings_older.py::test_titled_paragraphs_without_numbers_2012",
    "test_hearings_older.py::test_numbered_list_inside_a_condition_is_not_the_conditions_2012",
    "test_hearings_older.py::test_compliance_contact_lines_removed_whatever_the_spacing_2011",
    "test_hearings_older.py::test_read_pdf_poppler",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    missing = [p for p in _HEARING_PDFS if not os.path.exists(os.path.join(_HEARING_PDF_DIR, p))]
    if not missing:
        return
    skip = pytest.mark.skip(reason=f"needs the hearing PDF fixtures, not shipped ({len(missing)} missing)")
    for item in items:
        if item.nodeid.split("/")[-1].split("[")[0] in _NEEDS_HEARING_PDFS:
            item.add_marker(skip)
