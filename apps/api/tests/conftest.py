from __future__ import annotations

import datetime as dt
import json
import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("ENV", "test")
os.environ.setdefault("GIT_SHA", "test-sha")
os.environ.setdefault("WEB_VERIFY_ENABLED", "false")
# a real key in apps/api/.env must never make the test run export spans (env beats the .env file)
os.environ["NEATLOGS_API_KEY"] = ""

from app.core.config import settings  # env must be set first


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests never touch the network: link checking off, Supabase/Stripe unset."""
    monkeypatch.setattr(settings, "WEB_VERIFY_ENABLED", False)
    monkeypatch.setattr(settings, "SUPABASE_URL", None)
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", None)
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", "test-jwt-secret-with-enough-length-0123456789")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)
    yield


TODAY = dt.date(2026, 10, 21)


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for frame in body.split("\n\n"):
        name = None
        data_lines = []
        for line in frame.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if name and data_lines:
            events.append((name, json.loads("\n".join(data_lines))))
    return events


# ---- hearing PDFs not shipped in the public repository ---------------------------------------------------------
# The real Planning Commission motion and minutes PDFs these tests read name private project sponsors,
# property owners and public-comment speakers, so they are not in the public repository. The tests are
# skipped while the files are absent; put the public PDFs back in _HEARING_PDF_DIR to run them.
_HEARING_PDF_DIR = os.path.join(
    os.path.dirname(__file__), "../../packages/precedent/tests/fixtures/sf_planning_hearings"
)
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
    "test_full_conditions_older.py::test_extract_gates_on_case_decided_at_not_the_motion_date",
    "test_full_conditions_older.py::test_parse_conditions_reads_older_motions_the_older_way",
    "test_full_conditions_older.py::test_conditions_section_cuts_exhibit_c_for_older_motions_only",
    "test_full_conditions_older.py::test_extract_reads_an_older_motion_again_with_pdftotext_when_its_text_ends_early",
    "test_full_conditions_older.py::test_extract_refuses_a_motion_for_a_later_decision",
    "test_full_conditions_older.py::test_reparse_marks_a_motion_for_a_later_decision_not_found",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    missing = [p for p in _HEARING_PDFS if not os.path.exists(os.path.join(_HEARING_PDF_DIR, p))]
    if not missing:
        return
    skip = pytest.mark.skip(reason=f"needs the hearing PDF fixtures, not shipped ({len(missing)} missing)")
    for item in items:
        if item.nodeid.split("/")[-1].split("[")[0] in _NEEDS_HEARING_PDFS:
            item.add_marker(skip)
