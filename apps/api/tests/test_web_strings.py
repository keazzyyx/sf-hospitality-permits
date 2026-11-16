"""The fixed words the web page shares with the PDF and the text report, and the label tables of every PlanningUse.

The web page keeps its own copies of a few sentences (apps/web/src/lib/memo.ts). This test reads that file and
checks each copy is the API's sentence word for word, so the two cannot drift. Skipped where apps/web is absent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import get_args

import pytest

from app.memo import pathway, report, rows, triggers
from app.memo.report import REPORT_TEXT, TIMING_GROUPS, TRIGGER_CONTROL_LABELS
from app.models.memo import PlanningUse
from app.services.memo_pdf import PATHWAY_HINT

MEMO_TS = Path(__file__).resolve().parents[3] / "apps/web/src/lib/memo.ts"


def _ts() -> str:
    if not MEMO_TS.exists():
        pytest.skip("apps/web is not in this checkout")
    return MEMO_TS.read_text(encoding="utf-8")


def _quoted(text: str) -> str:
    """The string as a TypeScript double-quoted literal would hold it."""
    return json.dumps(text, ensure_ascii=False)


def test_every_label_table_covers_every_planning_use() -> None:
    values = set(get_args(PlanningUse))
    for name, table in (
        ("pathway.USE_LABELS", pathway.USE_LABELS),
        ("rows.USE_LABELS", rows.USE_LABELS),
        ("report.USE_LABELS", report.USE_LABELS),
        ("pathway.A_USE", pathway.A_USE),
    ):
        assert values <= set(table), name
    # the triggers' tables cover every use the rule table reads (no "not_covered": no cell is read for it)
    assert values - {"not_covered"} <= set(triggers.USE_LABELS) and values - {"not_covered"} <= set(
        triggers.A_USE
    )
    # the report's pathway facts read the existing use through the full table
    for use in values - {"not_covered"}:
        facts = report.pathway_facts(
            pathway.Pathway.model_construct(  # type: ignore[attr-defined]
                use="bar",
                use_label="Bar",
                district=None,
                permission_label="",
                existing_use=use,
                change_of_use_label="",
            )
        )
        assert facts["existing_use"] == report.USE_LABELS[use]
    web = _ts()
    block = web[web.index("export const PLANNING_USE_LABELS") :]
    block = block[: block.index("};")]
    assert values == set(re.findall(r"^\s+(\w+):", block, re.MULTILINE))


def test_the_web_copies_the_api_words_verbatim() -> None:
    web = _ts()
    for label in TRIGGER_CONTROL_LABELS.values():
        assert _quoted(label) in web, label
    for key in ("steps_hint", "steps_heading", "not_given_heading", "rules_date_label", "timing_column",
                "timing_heading", "timing_hint", "timing_pending_note", "timing_undated", "timing_none",
                "facts_heading", "facts_hint", "facts_read_heading", "counted_heading",
                "headline_heading", "headline_hint", "headline_definite", "headline_contingent"):  # fmt: skip
        assert _quoted(REPORT_TEXT[key]) in web, key
    for group in TIMING_GROUPS:
        for text in (group.label, group.per_case, group.measured):
            assert _quoted(text) in web, text
    assert _quoted(PATHWAY_HINT) in web
    assert 'principal: "Asks for nothing"' in web
    # what a fact that nothing gave shows (app.memo.report.NOT_KNOWN_VALUE)
    assert f"export const NOT_KNOWN = {_quoted(report.NOT_KNOWN_VALUE)};" in web


def test_the_web_fixture_quotes_the_apis_fixed_lines() -> None:
    """The sample memo's comparables note and disclaimers are the API's own sentences."""
    from app.agents.memo_runner import DISCLAIMERS
    from app.memo.evidence import COMPARABLES_NOTE, NO_COMPARABLES_NOTE

    fixture = MEMO_TS.parent / "fixtures" / "memo-fixture.ts"
    if not fixture.exists():
        pytest.skip("apps/web is not in this checkout")
    text = fixture.read_text(encoding="utf-8")
    assert COMPARABLES_NOTE.replace("{n}", "${n}") in text
    assert _quoted(NO_COMPARABLES_NOTE) in text
    for line in DISCLAIMERS:
        assert _quoted(line) in text, line
