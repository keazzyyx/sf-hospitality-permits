"""The report: the rules and the evidence only. The intake is the only model call; no field of the report, the teaser or the PDF holds text a
model wrote. Each row shows its status, its rule lines, the facts its rules read (with where each came from),
what is not known, its referral steps and its source links; the comparables are the top of the fixed ranking,
each with its recorded facts; the outcome counts list the decisions they count."""

from __future__ import annotations

import datetime as dt
import io
import json
from pathlib import Path
from typing import Any

import pypdf
import pytest
from fastapi.testclient import TestClient

from app.agents.memo_runner import DISCLAIMERS, MemoRunInput, MemoRunner
from app.agents.runner import RunnerEvent
from app.catalog.loader import get_catalog
from app.core.config import settings
from app.memo.evidence import COMPARABLE_LIMIT, NO_COMPARABLES_NOTE, comparables_note
from app.memo.intake import IntakeAnswers
from app.memo.report import REPORT_TEXT, report_text
from app.models.memo import FACT_ORIGIN_LABELS, Memo
from app.services.db import MemoryDatabase
from app.services.memo_pdf import TESTING_NOTICE, render_memo_pdf
from tests.fakes import FakeAnthropic
from tests.memo_fakes import FakeGeocoder, MemoScript, seed_store
from tests.test_api import auth
from tests.test_memo_api import client, create_memo, db  # noqa: F401 (fixtures)

TODAY = dt.date(2026, 10, 21)
DESC = (
    "40-seat wine bar of 1,400 square feet, small kitchen, open until 1am, occasional live music, amplified"
)
# The fields of the format-2 report a model wrote. None of them is in the report any more.
WRITER_FIELDS = (
    "concept_summary",
    "density",
    "timeline_cost",
    "verification",
    "records_summary",
    "expected_conditions",
    "filing_playbook",
    "data_gaps",
    "confidence_definitions",
)


@pytest.fixture(autouse=True)
def _wire_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    import app.memo.context as ctx
    import app.tools.precedent_tools as pt

    store = seed_store(tmp_path / "data")
    for mod in (ctx, pt):
        monkeypatch.setattr(mod, "get_store", lambda: store)
        monkeypatch.setattr(mod, "get_geocoder", lambda: FakeGeocoder())
    yield


async def run_memo(
    tmp_path: Path, script: MemoScript | None = None, description: str = DESC, **kw: Any
) -> tuple[MemoScript, list[RunnerEvent], list[RunnerEvent]]:
    store = seed_store(tmp_path / "data")
    script = script or MemoScript()
    runner = MemoRunner(FakeAnthropic(script), get_catalog(), settings, store, FakeGeocoder(), today=TODAY)  # type: ignore[arg-type]
    progress: list[RunnerEvent] = []

    async def emit(ev: RunnerEvent) -> None:
        progress.append(ev)

    terminal = [
        ev
        async for ev in runner.run_memo(
            MemoRunInput(address="995 Valencia St", description=description, **kw), emit
        )
    ]
    return script, progress, terminal


def _memo(terminal: list[RunnerEvent]) -> Memo:
    assert [e.type for e in terminal] == ["memo"], terminal
    memo = terminal[0].data["memo"]
    assert isinstance(memo, Memo)
    return memo


def _submit_tools(call: dict[str, Any]) -> set[str]:
    return {t["name"] for t in call.get("tools") or [] if t["name"].startswith("submit_")}


def _pdf_text(memo: Memo) -> str:
    reader = pypdf.PdfReader(io.BytesIO(render_memo_pdf(memo)))
    return " ".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)


@pytest.mark.anyio
async def test_the_intake_is_the_only_model_call(tmp_path: Path) -> None:
    script, progress, terminal = await run_memo(tmp_path)
    memo = _memo(terminal)
    assert script.calls, "the intake model was called"
    assert all(_submit_tools(c) == {"submit_intake_result"} for c in script.calls)
    assert memo.model_versions == {"intake": settings.ANTHROPIC_MODEL_MAIN}
    started = [e.data["stage"] for e in progress if e.type == "stage" and e.data["status"] == "started"]
    assert started == ["intake", "records", "precedent", "finalize"]
    assert not any(e.type == "narrative" for e in progress)


@pytest.mark.anyio
async def test_no_field_holds_text_a_model_wrote(tmp_path: Path) -> None:
    _script, _progress, terminal = await run_memo(tmp_path)
    memo = _memo(terminal)
    assert memo.format_version == 3
    dumped = memo.model_dump()
    assert not set(WRITER_FIELDS) & set(dumped)
    assert "next_step" not in dumped["overall"]
    for row in dumped["approvals"]:
        assert not {"summary", "summary_verification", "summary_note", "findings"} & set(row)
    for comp in dumped["comparable_cases"]:
        assert not {"why_comparable", "key_takeaway"} & set(comp)
    assert Memo.model_validate(dumped) == memo
    # the intake model's own note never reaches the report
    assert "40-seat wine bar in the Mission" not in memo.model_dump_json()
    assert memo.disclaimers == DISCLAIMERS
    assert memo.description == DESC


@pytest.mark.anyio
async def test_each_row_shows_its_rule_lines_and_the_facts_its_rules_read(tmp_path: Path) -> None:
    _script, _progress, terminal = await run_memo(tmp_path)
    memo = _memo(terminal)
    cited = {c.id for c in memo.citations}
    by_area = {row.area: row for row in memo.approvals}
    for row in memo.approvals:
        assert row.basis, row.area  # the rule lines that set the status
        for line in [*row.basis, *row.referral_steps]:
            assert set(line.citations) <= cited, (row.area, line.rule_id)
        for fact in row.facts:
            assert fact.value is not None and fact.origin != "not_known"
            assert set(fact.citations) <= cited
    zoning = {f.fact: f for f in by_area["zoning_use"].facts}
    closing = zoning["closing"]
    # the closing time comes from the applicant's words, with the words that state it; the rules read "after
    # midnight" from the flag the intake set, and say they worked it out
    assert (closing.origin, closing.derived, closing.value) == ("description", True, "After midnight")
    assert closing.origin_label == "Worked out by the rules from your description"
    assert closing.quotes == [DESC]
    seats = zoning.get("seats") or next(f for f in memo.facts if f.fact == "seats")
    assert (seats.value, seats.origin_label) == ("40", FACT_ORIGIN_LABELS["description"])
    # the facts the records give are shown with the records, whatever they show
    assert {"existing_use_records", "prior_approvals"} <= set(zoning)
    assert zoning["existing_use_records"].origin == "record"
    alcohol = {f.fact: f for f in by_area["alcohol"].facts}
    assert alcohol["alcohol_served"].value == "Beer and wine"
    assert "active_licences" in alcohol


@pytest.mark.anyio
async def test_comparables_are_the_top_of_the_fixed_ranking_with_their_recorded_facts(tmp_path: Path) -> None:
    _script, _progress, terminal = await run_memo(tmp_path)
    memo = _memo(terminal)
    comps = memo.comparable_cases
    assert 0 < len(comps) <= COMPARABLE_LIMIT
    scores = [c.similarity_score for c in comps]
    assert scores == sorted(scores, reverse=True)
    assert (
        memo.comparables_note == comparables_note(len(comps))
        and "No model picks them" in memo.comparables_note
    )
    cited = {c.id for c in memo.citations}
    for c in comps:
        assert c.source_url and c.citation_id in cited and c.opposition_noted is None
    assert comparables_note(0) == NO_COMPARABLES_NOTE


@pytest.mark.anyio
async def test_the_outcome_counts_list_each_decision_they_count(tmp_path: Path) -> None:
    _script, _progress, terminal = await run_memo(tmp_path)
    memo = _memo(terminal)
    b = memo.base_rate
    assert len(b.counted) == b.total > 0
    assert all(d.source_url and d.decided_at for d in b.counted)
    decided = [d.decided_at for d in b.counted]
    assert decided == sorted(decided, reverse=True)  # newest first
    outcomes = [d.outcome for d in b.counted]
    assert outcomes.count("denied") == b.denied


@pytest.mark.anyio
async def test_an_intake_answer_is_named_as_the_source_of_its_fact(tmp_path: Path) -> None:
    _script, _progress, terminal = await run_memo(
        tmp_path, intake_answers=IntakeAnswers(floor_area_sqft=2200)
    )
    memo = _memo(terminal)
    floor = next(f for f in memo.facts if f.fact == "floor_area_sqft")
    assert (floor.value, floor.origin, floor.quotes) == ("2,200 sq ft", "intake_answer", [])


@pytest.mark.anyio
async def test_what_the_text_does_not_state_is_not_known_and_asked_by_the_rules(tmp_path: Path) -> None:
    # the intake model quotes nothing: every fact it filled is cleared by the stated-facts check
    _script, _progress, terminal = await run_memo(tmp_path, MemoScript(intake_quotes=[]))
    memo = _memo(terminal)
    unknown = [f for f in memo.facts if f.origin == "not_known"]
    assert unknown and all(f.value is None for f in unknown)
    assert {"closing", "seats"} <= {f.fact for f in unknown}
    assert memo.could_not_establish and all(
        q.question.startswith("Not known:") for q in memo.could_not_establish
    )


@pytest.mark.anyio
async def test_the_models_clarifying_questions_are_not_asked(tmp_path: Path) -> None:
    _script, _progress, terminal = await run_memo(tmp_path, MemoScript(ask_clarification=True))
    memo = _memo(terminal)  # a finished report, not a question
    assert memo.approvals


@pytest.mark.anyio
async def test_the_pdf_and_the_text_report_carry_the_evidence_and_no_writers_text(tmp_path: Path) -> None:
    _script, _progress, terminal = await run_memo(tmp_path)
    memo = _memo(terminal)
    pdf = _pdf_text(memo)
    for heading in (
        REPORT_TEXT["facts_read_heading"],
        REPORT_TEXT["facts_heading"],
        REPORT_TEXT["counted_heading"],
        "Approvals to file, in order",
        "Your description:",
        "Rules applied",
    ):
        assert heading in pdf, heading
    # the testing notice sits under the header, before the overall status
    notice = " ".join(TESTING_NOTICE.split())
    flat = " ".join(pdf.split())
    assert notice in flat
    assert flat.index(notice) < flat.index("Overall:")
    for absent in (
        "Next step",
        "Takeaway",
        "Citation check",
        "Expected conditions",
        "What to file",
        "Concept:",
    ):
        assert absent not in pdf, absent
    text = report_text(memo)
    assert "NEXT STEP" not in text and "Facts the rules read:" in text and "COMPARABLE CASES:" in text
    assert memo.comparables_note in text


def test_the_api_serves_format_3_and_streams_the_live_stages(client: TestClient, db: MemoryDatabase) -> None:  # noqa: F811
    status, events = create_memo(client)
    assert status == 200 and events[-1][0] == "memo"
    started = [d["stage"] for e, d in events if e == "stage" and d["status"] == "started"]
    assert started == ["intake", "records", "precedent", "finalize"]
    rec = events[-1][1]
    assert rec["teaser"]["comparable_count"] == len(
        next(r for r in db.tables["memos"] if r["id"] == rec["id"])["memo"]["comparable_cases"]
    )
    client.get("/v1/me", headers=auth())
    db.tables["profiles"][0]["memo_credits"] = 1
    full = client.post(f"/v1/memos/{rec['id']}/unlock", headers=auth()).json()["memo"]["memo"]
    assert full["format_version"] == 3 and "verification" not in full and "filing_playbook" not in full
    assert all(row["facts"] is not None and "summary" not in row for row in full["approvals"])
    pdf = client.get(f"/v1/memos/{rec['id']}/export.pdf", headers=auth())
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_a_format_2_memo_is_legacy_and_unlocking_it_spends_no_credit(
    client: TestClient,  # noqa: F811
    db: MemoryDatabase,  # noqa: F811
) -> None:
    _status, events = create_memo(client)
    memo_id = events[-1][1]["id"]
    row = next(r for r in db.tables["memos"] if r["id"] == memo_id)
    row["memo"] = {**json.loads(json.dumps(row["memo"])), "format_version": 2}
    rec = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert rec["legacy_format"] is True and rec["memo"] is None and rec["teaser"] is None
    summary = client.get("/v1/memos", headers=auth()).json()["memos"][0]
    assert summary["legacy_format"] is True and summary["overall_status"] is None
    db.tables["profiles"][0]["memo_credits"] = 1
    r = client.post(f"/v1/memos/{memo_id}/unlock", headers=auth())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "legacy_format"
    assert db.tables["profiles"][0]["memo_credits"] == 1


def test_the_record_carries_none_of_the_intake_models_own_text(
    client: TestClient,  # noqa: F811
    db: MemoryDatabase,  # noqa: F811
) -> None:
    """The profile served with a memo has no text the intake model wrote: not its note on what it assumed, nor the
    name and neighbourhood as it copied them. That holds for the stored row, the final event, the record and the
    unlock, and for an older row that stored them."""
    _status, events = create_memo(client)
    rec = events[-1][1]

    def no_model_text(profile: dict[str, Any]) -> None:
        assert (
            profile["assumptions"] == []
            and profile["business_name"] is None
            and profile["neighborhood"] is None
        )

    no_model_text(rec["profile"])
    row = next(r for r in db.tables["memos"] if r["id"] == rec["id"])
    no_model_text(row["profile"])
    no_model_text(client.get(f"/v1/memos/{rec['id']}", headers=auth()).json()["memo"]["profile"])
    client.get("/v1/me", headers=auth())
    db.tables["profiles"][0]["memo_credits"] = 1
    no_model_text(client.post(f"/v1/memos/{rec['id']}/unlock", headers=auth()).json()["memo"]["profile"])
    # an older row that stored the model's text is served without it
    row["profile"] = {
        **row["profile"],
        "assumptions": ["Assumed 8 employees"],
        "business_name": "Rioja Room",
        "neighborhood": "Mission",
    }
    no_model_text(client.get(f"/v1/memos/{rec['id']}", headers=auth()).json()["memo"]["profile"])


def test_a_quote_is_shown_as_the_applicants_own_words_cut_from_their_text() -> None:
    """The quotes under a fact are cut from the applicant's text as written, never the model's own string. A
    quote in parts ("a ... b") is shown as one snippet per part, so words from different places are never shown
    joined as one sentence; a quote not in the text gives nothing."""
    from app.memo.evidence import counted_quotes
    from app.models.profile import FactQuote

    text = "Wine bar, no food after 10pm, occasional live music on weekends, we close at 1am. Café of 3,953 sq ft."
    quotes = [
        FactQuote(field="live_entertainment", quote="no ... live music"),
        FactQuote(field="seats", quote="NO FOOD"),
        FactQuote(field="closing_hour", quote="close at 1AM"),
        FactQuote(field="business_type", quote="cafe"),
        FactQuote(field="square_feet", quote="3953 sq ft"),
        FactQuote(field="dancing", quote="40 seats"),
    ]
    assert counted_quotes(quotes, text) == {
        "live_entertainment": ("no", "live music"),
        "seats": ("no food",),
        "closing_hour": ("close at 1am",),
        "business_type": ("Café",),
        "square_feet": ("3,953 sq ft",),
    }
