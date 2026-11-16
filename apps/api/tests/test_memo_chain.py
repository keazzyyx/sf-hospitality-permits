"""Mocked end-to-end runs of the memo chain: the intake is the one model call, the rules decide the pathway and
every status, and the report is built in code. Also deterministic analytics.

Rule table v2 through the chain: the runner gives the rules the census tract and a rules date; the memo, the
plain-text report and the PDF print the triggers, the change-of-use answers and each row's status note, referral
steps and missing inputs as the rules gave them; and days from filing are printed by outcome."""

from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt
import importlib.util
import io
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pypdf
import pytest
from precedent.models import Application
from precedent.store.base import Nearby

import app.agents.memo_runner as memo_runner
from app.agents.memo_runner import MemoRunInput, MemoRunner
from app.agents.runner import PROFILE_TEMPERATURE, RunnerEvent
from app.catalog.loader import get_catalog
from app.core.config import settings
from app.memo import analytics
from app.memo.report import (
    REPORT_TEXT,
    iso_date,
    report_text,
    rule_citations,
    rule_line_text,
    status_summary_lines,
    timing_cell,
    trigger_differs_texts,
    trigger_headline,
)
from app.memo.tracts import tract_at
from app.models.memo import (
    NO_HISTORY_NOTE,
    RECORDS_LIMITS,
    ComparableCase,
    Determinations,
    Memo,
)
from app.models.profile import BusinessProfile
from app.services.memo_pdf import NO_CONDITIONS_NOTE, NOT_IN_SOURCE, conditions_cell, render_memo_pdf
from tests.fakes import FakeAnthropic
from tests.memo_fakes import (
    VALENCIA,
    FakeGeocoder,
    MemoScript,
    case_determinations,
    seed_store,
    sent_temperature,
)

TODAY = dt.date(2026, 10, 21)
# What the scripted intake model's profile (tests.fakes.BASE_PROFILE) claims, all stated, so the stated-facts check
# (app.memo.stated) keeps every fact the memo's rules read.
DESC = (
    "40-seat wine bar of 1,400 square feet, small kitchen, open until 1am, occasional live music, amplified"
)


async def run_memo(tmp_path: Path, script: MemoScript | None = None, description: str = DESC, **kw):  # type: ignore[no-untyped-def]
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
    return store, script, progress, terminal


@pytest.fixture(autouse=True)
def _wire_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Tools read the store/geocoder through app.deps; point them at the seeded fixtures."""
    import app.memo.context as ctx
    import app.tools.precedent_tools as pt

    store = seed_store(tmp_path / "data")
    for mod in (ctx, pt):
        monkeypatch.setattr(mod, "get_store", lambda: store)
        monkeypatch.setattr(mod, "get_geocoder", lambda: FakeGeocoder())
    yield


def _pdf_text(memo: Memo) -> str:
    reader = pypdf.PdfReader(io.BytesIO(render_memo_pdf(memo)))
    return " ".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)


@pytest.mark.anyio
async def test_history_note_comparable_fields_source_notes_and_teaser(tmp_path: Path) -> None:
    _store, _script, _progress, terminal = await run_memo(tmp_path)
    memo: Memo = terminal[0].data["memo"]
    # "no outcome history" on the alcohol and entertainment rows only
    notes = {r.area: r.history_note for r in memo.approvals}
    assert notes == {
        "zoning_use": None,
        "alcohol": NO_HISTORY_NOTE,
        "entertainment": NO_HISTORY_NOTE,
        "health": None,
        "building_change_of_use": None,
    }
    # comparables are evidence: source, what it is called, and days from filing to decision
    by_id = {c.application_id: c for c in memo.comparable_cases}
    enriched = by_id["datasf_planning:1"]  # its record carries a motion_url
    assert (enriched.source, enriched.source_label) == ("sf_planning_hearings", "Planning Commission motion")
    plain = by_id["datasf_planning:2"]
    assert (plain.source, plain.source_label) == ("datasf_planning", "Planning case list (DataSF)")
    assert all(c.days_to_decision == 120 and c.outcome for c in memo.comparable_cases)
    assert len(enriched.conditions) == 3
    # one note per source among the comparables or the nearby records, in a fixed order
    assert [n.source for n in memo.source_notes] == [
        "datasf_planning",
        "sf_planning_hearings",
        "datasf_entertainment",
        "abc",
    ]
    assert memo.source_notes[0].leaves_out.startswith("Outcome and dates only.")
    assert "cannot show a failure or a processing time" in memo.source_notes[3].leaves_out
    teaser = MemoRunner.teaser(memo)
    assert teaser.model_dump() == {
        "overall_status": "further_review",
        "overall_line": memo.overall.line,
        # the top of the fixed ranking: every seeded record that can be a comparable (fewer than ten)
        "comparable_count": 8,
        "approvals_count": 5,
        # no story is given and none is assumed: the zoning row is insufficient information, so nothing is
        # barred (the user's decision of 2026-11-12)
        "blockers_count": 0,
    }
    assert teaser.overall_line == (
        "A Conditional Use Authorization is needed (use control of a special use district). "
        "Of the 5 approvals this concept needs: 1 further review (entertainment permit), 3 insufficient "
        "information (zoning and use, alcohol licence, building permit and change of use), 1 allowed (health "
        "permit)."
    )


async def _determinations(tmp_path: Path) -> Determinations:
    """What the rules decide for the wine bar at 995 Valencia St from the seeded records, worked out apart
    from any memo run."""
    store = seed_store(tmp_path / "rules")
    runner = MemoRunner(
        FakeAnthropic(MemoScript()), get_catalog(), settings, store, FakeGeocoder(), today=TODAY
    )  # type: ignore[arg-type]

    async def emit(ev: RunnerEvent) -> None:
        return None

    # the profile a memo run reads from the scripted intake: rule table v2 reads the floor area and the closing
    # time, so the rules must be given the same facts the run has
    profile = BusinessProfile.model_validate(MemoScript().profile).normalized()
    bundle = await runner.collect_records(VALENCIA, profile, emit)
    return bundle.determinations


def _assert_memo_is_what_the_rules_decided(memo: Memo, rules: Determinations) -> None:
    assert [(r.area, r.approval, r.agency, r.status, r.basis) for r in memo.approvals] == [
        (r.area, r.approval, r.agency, r.status, r.basis) for r in rules.rows
    ]
    # rule table v2: the status note, the referral steps and the missing inputs are the rules' too
    assert [(r.status_note, r.referral_steps, r.missing_inputs) for r in memo.approvals] == [
        (r.status_note, r.referral_steps, r.missing_inputs) for r in rules.rows
    ]
    assert memo.records_limits == RECORDS_LIMITS
    assert (memo.overall.status, memo.overall.line) == (rules.overall_status, rules.overall_line)
    assert memo.overall.citations == rule_citations(rules.rows)
    assert memo.entitlement_path == rules.entitlement_path
    assert memo.pathway == rules.pathway
    assert memo.could_not_establish == rules.open_questions
    teaser = MemoRunner.teaser(memo)
    assert (teaser.overall_status, teaser.overall_line) == (rules.overall_status, rules.overall_line)


@pytest.mark.anyio
async def test_the_report_takes_every_decision_from_the_rules(tmp_path: Path) -> None:
    rules = await _determinations(tmp_path)
    _store, _script, _progress, terminal = await run_memo(tmp_path)
    memo: Memo = terminal[0].data["memo"]
    _assert_memo_is_what_the_rules_decided(memo, rules)
    # the description gives no story, and the table on file for NCT-2 gives first-story controls: no story is
    # assumed, so the zoning row is insufficient information naming the story (the user's decision of
    # 2026-11-12) and nothing is barred
    assert [(r.area, r.approval, r.agency, r.status) for r in memo.approvals] == [
        (
            "zoning_use",
            "Use authorization (not decided: an input is missing)",
            "San Francisco Planning",
            "insufficient_information",
        ),
        (
            "alcohol",
            "ABC licence, Type 42 (on-sale beer and wine, public premises)",
            "California Department of Alcoholic Beverage Control",
            "insufficient_information",
        ),
        (
            "entertainment",
            "Place of Entertainment, Limited Live Performance or Fixed Place Outdoor Amplified Sound permit",
            "San Francisco Entertainment Commission",
            "further_review",
        ),
        ("health", "Health permit to operate", "San Francisco Department of Public Health", "allowed"),
        (
            "building_change_of_use",
            "Building permit",
            "San Francisco Department of Building Inspection",
            "insufficient_information",
        ),
    ]
    assert memo.approvals[0].missing_inputs[0] == "which stories the business occupies"
    assert (memo.pathway.use, memo.pathway.district, memo.pathway.permission) == (
        "bar",
        "NCT-2",
        "not_covered",
    )
    # with the first story stated, the table on file is read: the district prohibits a new Bar, and every later
    # row follows the zoning row (Planning Code § 175(a))
    first = await _determinations_for(tmp_path / "first", {"stories": ["first"]})
    assert [r.status for r in first.rows] == ["not_permitted"] * 5
    # a row is not permitted, so the path lists no approval to file: it says there is none
    assert first.entitlement_path == (
        "No approval path: zoning does not permit the concept as described at this address."
    )
    # the entertainment and health rows give the City's own bar on a permit for a prohibited use
    for area in (2, 3):
        (line,) = first.rows[area].basis
        assert line.text == (
            "Zoning does not permit a new Bar at this address, and no City department may issue a permit or "
            "licence that would authorize a use the Planning Code prohibits: not permitted."
        )
        assert line.code_section == "Planning Code § 175(a)"
        # the records behind the trigger that bars the use: the district's rows and the alcohol district's
        assert line.citations == [
            "overlay:datasf_zoning:NCT-2",
            "overlay:static:sf:mission_alcoholic_beverage_sud",
            "zoning:NCT-2",
        ]
    p = first.pathway
    assert (p.use, p.district, p.permission, p.existing_use, p.change_of_use) == (
        "bar",
        "NCT-2",
        "not_permitted",
        None,
        "not_established",
    )


@pytest.mark.anyio
async def test_the_building_row_takes_its_change_of_use_answer_from_the_zoning_row(tmp_path: Path) -> None:
    """One answer, read twice: the building row's change-of-use line is the zoning row's, word for word, with
    the same records behind it, and the pathway carries the same answer. (Rule table v2: both rows print the
    pathway's own line; the building row no longer copies it under "Taken from the zoning row".)"""
    _store, _script, _progress, terminal = await run_memo(tmp_path)
    memo: Memo = terminal[0].data["memo"]
    by_area = {r.area: r for r in memo.approvals}
    (answer,) = [line for line in by_area["zoning_use"].basis if line.rule_id == "change.planning_use"]
    (taken,) = [
        line for line in by_area["building_change_of_use"].basis if line.rule_id == "change.planning_use"
    ]
    assert answer == memo.pathway.lines[-1]
    assert taken == answer
    assert memo.pathway.changes is not None and memo.pathway.changes.planning_use_lines[-1] == answer
    assert answer.text == (
        "The records do not show what the space is used as, and the description does not say what it was last "
        "used as, so whether the proposed use (Bar) is a change of use is not established."
    )
    # the change of use is not established, and with no story given the zoning row is not decided (no story is
    # assumed): the building row names what it needs
    assert memo.pathway.change_of_use == "not_established"
    assert by_area["zoning_use"].status == "insufficient_information"
    assert by_area["building_change_of_use"].status == "insufficient_information"
    assert "what the space was last used as" in by_area["building_change_of_use"].missing_inputs
    # with an active Type 41 licence on file at the address, the same answer is "Restaurant to Bar is a change
    # of use" in both rows
    store = seed_store(tmp_path / "licensed")
    licence = (await store.application("abc:24")).model_copy(  # type: ignore[union-attr]
        update={
            "id": "abc:995",
            "source_id": "995",
            "address": "995 Valencia St",
            "lat": VALENCIA.lat,
            "lng": VALENCIA.lng,
        }
    )
    store.applications[licence.id] = licence
    store._flush("applications")
    runner = MemoRunner(
        FakeAnthropic(MemoScript()), get_catalog(), settings, store, FakeGeocoder(), today=TODAY
    )  # type: ignore[arg-type]

    async def emit(ev: RunnerEvent) -> None:
        return None

    # on the first story the district bars a new Bar (the table on file is a first-story table)
    bundle = await runner.collect_records(VALENCIA, WINE_BAR.model_copy(update={"stories": ["first"]}), emit)
    rules = bundle.determinations
    by_area_rules = {r.area: r for r in rules.rows}
    (answer,) = [line for line in by_area_rules["zoning_use"].basis if line.rule_id == "zoning.change_of_use"]
    (taken,) = [
        line
        for line in by_area_rules["building_change_of_use"].basis
        if line.rule_id == "zoning.change_of_use"
    ]
    assert answer.text == "Restaurant to Bar is a change of use."
    assert taken == answer == rules.pathway.lines[-1]
    assert taken.citations == answer.citations == ["app:abc:995"]
    assert (rules.pathway.existing_use, rules.pathway.change_of_use) == ("restaurant", "yes")
    # the district prohibits a new Bar, so the change-of-use permit cannot be issued either (rule B0)
    building = by_area_rules["building_change_of_use"]
    assert by_area_rules["zoning_use"].status == "not_permitted"
    assert (building.status, building.approval) == ("not_permitted", "Building permit with change of use")
    assert [line.rule_id for line in building.basis] == [
        "zoning.existing_use",
        "zoning.change_of_use",
        "building.status",
    ]
    assert building.basis[-1].code_section == "Planning Code § 175(a)"
    assert building.basis[-1].text.startswith(
        "Zoning does not permit a new Bar at this address, and no City "
    )
    # the licence record the rule line cites is in the citation list, so the report can resolve it
    assert "app:abc:995" in bundle.citations


def _stage_of(call: dict) -> str:  # type: ignore[type-arg]
    name = next(t["name"] for t in call["tools"] if t["name"].startswith("submit_"))
    return str(name.removeprefix("submit_").removesuffix("_result"))


@pytest.mark.anyio
async def test_intake_runs_at_temperature_zero_and_is_the_only_model_call(tmp_path: Path) -> None:
    """The profile feeds the rules, so the stage that writes it is sampled at temperature 0. No other stage of
    the memo calls a model."""
    _store, script, _progress, terminal = await run_memo(tmp_path)
    assert [e.type for e in terminal] == ["memo"]
    by_stage: dict[str, list[dict]] = {}  # type: ignore[type-arg]
    for call in script.calls:
        by_stage.setdefault(_stage_of(call), []).append(call)
    assert set(by_stage) == {"intake"}
    assert by_stage["intake"] and [sent_temperature(c) for c in by_stage["intake"]] == [
        PROFILE_TEMPERATURE
    ] * len(by_stage["intake"])
    assert PROFILE_TEMPERATURE == 0.0


@pytest.mark.anyio
async def test_the_intake_model_records_only_what_the_text_states(tmp_path: Path) -> None:
    """User decision of 2026-11-12 (app.memo.stated): a profile field the rules read that no quote from the text
    states is cleared before the rules read it, recorded on the profile, and named in the report. Here the scripted
    model reads "a mezzanine" as a second story and invents 120 seats and a 2 a.m. close."""
    from app.memo.facts import MISSING_PHRASES
    from app.memo.pathway import NOT_STATED_QUESTION

    script = MemoScript()
    script.profile = {**script.profile, "stories": ["first", "second"], "seats": 120, "closing_hour": "02:00"}
    script.intake_quotes = [
        {"field": "business_type", "quote": "wine bar"},
        {"field": "alcohol_type", "quote": "wine bar"},
        {"field": "square_feet", "quote": "1,400 square feet"},
        {"field": "stories", "quote": "with a mezzanine"},
        {"field": "seats", "quote": "1,400 square feet"},
        {"field": "closes_after_midnight", "quote": "open until 1am"},
        {"field": "live_entertainment", "quote": "occasional live music"},
        {"field": "amplified_sound", "quote": "amplified"},
    ]  # no quote for the closing time
    desc = "Wine bar of 1,400 square feet with a mezzanine, small kitchen, open until 1am, occasional live music, amplified"
    _store, script, _progress, terminal = await run_memo(tmp_path, script, description=desc)
    profile: BusinessProfile = terminal[0].data["profile"]
    assert profile.stories == [] and profile.seats is None and profile.closing_hour is None
    assert profile.intake_cleared == {"seats": 120, "stories": ["first", "second"], "closing_hour": "02:00"}
    assert (profile.square_feet, profile.business_type, profile.live_entertainment) == (1400, "bar", True)
    memo: Memo = terminal[0].data["memo"]
    asked = [q.question for q in memo.could_not_establish]
    named = {p for r in memo.approvals for p in r.missing_inputs}
    for fact in ("stories", "seats", "closing"):
        phrase = MISSING_PHRASES[fact]
        assert (
            phrase in named
            or NOT_STATED_QUESTION.format(phrase=phrase) in asked
            or any(a.startswith(f"Not known: {phrase}.") for a in asked)
        ), fact
    # no story is assumed, so the zoning row names the stories; no row asks for the seats, so they are asked on
    # their own
    assert MISSING_PHRASES["stories"] in {p for p in memo.approvals[0].missing_inputs}
    assert NOT_STATED_QUESTION.format(phrase=MISSING_PHRASES["seats"]) in asked


async def _determinations_for(tmp_path: Path, profile_fields: dict[str, Any]) -> Determinations:
    """What the rules decide at 995 Valencia St for the scripted profile with `profile_fields` changed."""
    store = seed_store(tmp_path / "rules")
    runner = MemoRunner(
        FakeAnthropic(MemoScript()), get_catalog(), settings, store, FakeGeocoder(), today=TODAY
    )  # type: ignore[arg-type]

    async def emit(ev: RunnerEvent) -> None:
        return None

    profile = BusinessProfile.model_validate({**MemoScript().profile, **profile_fields}).normalized()
    bundle = await runner.collect_records(VALENCIA, profile, emit)
    return bundle.determinations


# ---- the local validation scripts ---------------------------------------------------------------------
SCRIPTS = Path(__file__).resolve().parents[3] / "scripts" / "validation"


def _load_script(name: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import a validation script as a module. Both scripts set environment variables when they are imported;
    the variables are put back as soon as the import is done, so nothing in the test reads them."""
    spec = importlib.util.spec_from_file_location(f"validation_{name}", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as env:
        for key in ("PRECEDENT_DATABASE_URL", "NEATLOGS_API_KEY", "LOCAL_DATABASE_URL"):
            env.setenv(key, os.environ.get(key, ""))
        env.delenv("LOCAL_DATABASE_URL")  # the script then takes its own default, the local database
        spec.loader.exec_module(module)
    return module


@pytest.mark.anyio
async def test_address_not_found(tmp_path: Path) -> None:
    _, _, _, terminal = await run_memo(tmp_path, address_override=None) if False else await run_memo(tmp_path)
    assert terminal[0].type == "memo"
    store = seed_store(tmp_path / "d2")
    runner = MemoRunner(
        FakeAnthropic(MemoScript()), get_catalog(), settings, store, FakeGeocoder(hit=None), today=TODAY
    )  # type: ignore[arg-type]
    import app.memo.context as ctx
    import app.tools.precedent_tools as pt

    pt.get_geocoder = lambda: FakeGeocoder(hit=None)  # type: ignore[assignment]
    ctx.get_geocoder = lambda: FakeGeocoder(hit=None)  # type: ignore[assignment]

    async def emit(ev: RunnerEvent) -> None:
        return None

    out = [ev async for ev in runner.run_memo(MemoRunInput(address="1 Nowhere Rd", description=DESC), emit)]
    assert out[0].type == "error" and out[0].data["code"] == "address_not_found"


def test_analytics_similarity_base_rate_density(tmp_path: Path) -> None:
    store = seed_store(tmp_path / "data")

    profile = BusinessProfile(
        business_type="bar",
        seats=40,
        serves_alcohol=True,
        alcohol_type="beer_wine",
        closes_after_midnight=True,
        live_entertainment=True,
    ).normalized()
    apps = asyncio.run(store.nearby_applications(VALENCIA.lat, VALENCIA.lng, analytics.FT_1000_M))
    ranked = analytics.rank_candidates(apps, profile, TODAY)
    assert ranked and ranked[0].app.use_types[0] in {"bar", "nightclub", "live_entertainment"}
    assert ranked[0].score >= ranked[-1].score
    rate = analytics.base_rate(apps, profile, TODAY, zoning_district="NCT-2")
    # bar cases 1, 2, 3, 6: four in five years → widened to ten; still four, so no district scope and no rate
    assert rate.total == 4 and rate.window_years == 10 and rate.approval_rate_pct is None
    assert rate.scope == (
        "N = 4 dated decisions within 1,000 ft, last 10 years (fewer than 5 in the last 5); too few for a rate"
    )
    assert rate.excluded_grant_only == 6  # the Entertainment Commission permit and five ABC licences
    restaurant = BusinessProfile(business_type="restaurant", seats=40).normalized()
    rate_r = analytics.base_rate(apps, restaurant, TODAY, zoning_district="NCT-2")
    # only 2 restaurant cases in 5 years (apps 4 and 5) → widened to 10 years, picking up app 9 (8 years old)
    assert rate_r.total == 3 and rate_r.approval_rate_pct is None and rate_r.window_years == 10
    assert rate_r.scope == (
        "N = 3 dated decisions within 1,000 ft, last 10 years (fewer than 5 in the last 5); too few for a rate"
    )
    explicit = analytics.base_rate(apps, restaurant, TODAY, zoning_district="NCT-2", window_years=10)
    assert explicit == dataclasses.replace(  # no fallback claimed
        rate_r, scope="N = 3 dated decisions within 1,000 ft, last 10 years; too few for a rate"
    )
    lic = asyncio.run(
        store.nearby_applications(VALENCIA.lat, VALENCIA.lng, analytics.FT_1000_M, kinds=["abc_license"])
    )
    biz = asyncio.run(store.nearby_businesses(VALENCIA.lat, VALENCIA.lng, analytics.FT_500_M))
    dens = analytics.density(biz, [n for n in lic if n.distance_m <= analytics.FT_500_M], lic)
    assert (dens.food_or_drink_businesses, dens.bars) == (4, 2)  # businesses 5 and 6 sit just outside 500 ft
    # the old rule-of-thumb status is gone: the rules in app.memo.pathway are the only thing that sets a status
    assert not hasattr(analytics, "prior_status")


def _nearby(app_id: str, **kw) -> Nearby[Application]:  # type: ignore[no-untyped-def]
    base = {
        "id": f"datasf_planning:{app_id}",
        "source": "datasf_planning",
        "source_id": app_id,
        "source_url": f"https://example.org/{app_id}",
        "fetched_at": dt.datetime(2026, 10, 21, tzinfo=dt.UTC),
        "kind": "planning_other",
        "permit_type": "x",
        "zoning_district": "NCT-2",
    }
    return Nearby(Application.model_validate({**base, **kw}), 100.0)


def _years_ago(years: float) -> dt.date:
    return TODAY - dt.timedelta(days=int(365 * years))


def _decided(app_id: str, outcome: str, *, years: float = 1.0, use: str = "bar", **kw) -> Nearby[Application]:  # type: ignore[no-untyped-def]
    """A dated Planning decision: filed 150 days before it was decided `years` ago."""
    decided = _years_ago(years)
    return _nearby(
        app_id,
        kind="cua",
        use_types=[use],
        filed_at=decided - dt.timedelta(days=150),
        decided_at=decided,
        outcome=outcome,
        **kw,
    )


WINE_BAR = BusinessProfile(
    business_type="bar", seats=40, serves_alcohol=True, alcohol_type="beer_wine", live_entertainment=True
).normalized()


def test_base_rate_shows_no_rate_under_ten_cases_and_always_prints_n() -> None:
    seven = [_decided(f"a{i}", "approved") for i in range(5)] + [
        _decided("d1", "denied"),
        _decided("w1", "withdrawn"),
    ]
    rate = analytics.base_rate(seven, WINE_BAR, TODAY, zoning_district=None)
    assert rate.total == 7 and rate.rate_shown is False and rate.approval_rate_pct is None
    assert rate.scope == "N = 7 dated decisions within 1,000 ft, last 5 years; too few for a rate"
    nine = [*seven, _decided("a8", "approved"), _decided("a9", "approved_with_conditions")]
    assert analytics.base_rate(nine, WINE_BAR, TODAY, zoning_district=None).approval_rate_pct is None
    # ten is the first N that carries a rate; withdrawals count against it
    ten = [*nine, _decided("a10", "approved")]
    r10 = analytics.base_rate(ten, WINE_BAR, TODAY, zoning_district=None)
    assert r10.total == 10 and r10.rate_shown is True and r10.approval_rate_pct == 80.0
    assert r10.scope == "N = 10 dated decisions within 1,000 ft, last 5 years"
    many = (
        [_decided(f"a{i}", "approved") for i in range(15)]
        + [_decided(f"c{i}", "approved_with_conditions") for i in range(3)]
        + [_decided(f"d{i}", "denied") for i in range(3)]
        + [_decided(f"w{i}", "withdrawn") for i in range(2)]
    )
    r23 = analytics.base_rate(many, WINE_BAR, TODAY, zoning_district=None)
    assert r23.scope == "N = 23 dated decisions within 1,000 ft, last 5 years"
    assert (r23.approved, r23.approved_with_conditions, r23.denied, r23.withdrawn) == (15, 3, 3, 2)
    assert r23.rate_shown is True and r23.approval_rate_pct == 78.3
    # deterministic and order-independent
    assert analytics.base_rate(list(reversed(many)), WINE_BAR, TODAY, zoning_district=None) == r23
    # same district with five or more cases narrows the scope and says so
    in_district = analytics.base_rate(many, WINE_BAR, TODAY, zoning_district="NCT-2")
    assert (
        in_district.scope == "N = 23 dated decisions in zoning district NCT-2 (within 1,000 ft), last 5 years"
    )
    one = analytics.base_rate(
        [_decided("only", "denied")], WINE_BAR, TODAY, zoning_district=None, window_years=10
    )
    assert one.scope == "N = 1 dated decision within 1,000 ft, last 10 years; too few for a rate"


def test_base_rate_excludes_grant_only_sources_and_undated_rows_and_counts_them() -> None:
    restaurant = BusinessProfile(business_type="restaurant", seats=40).normalized()
    planning = [_decided(f"a{i}", "approved") for i in range(9)] + [_decided("d1", "denied")]
    grant_only = [
        # Entertainment Commission permits: a list of grants, dated or not, never in the pool
        _nearby(
            f"poe-{i}",
            id=f"datasf_entertainment:poe-{i}",
            source="datasf_entertainment",
            kind="entertainment_poe",
            use_types=["live_entertainment", "bar"],
            status="Active",
            filed_at=_years_ago(2),
            decided_at=_years_ago(1),
            outcome="approved",
        )
        for i in range(4)
    ] + [
        _nearby(
            "llp",
            id="datasf_entertainment:llp",
            source="datasf_entertainment",
            kind="entertainment_llp",
            use_types=["live_entertainment"],
            status="Active",
            outcome="approved",
        ),
        # ABC licences: active or pending today, no filing date
        _nearby(
            "abc-1",
            id="abc:1",
            source="abc",
            kind="abc_license",
            use_types=["bar"],
            decided_at=_years_ago(1),
            outcome="approved",
        ),
        _nearby("abc-2", id="abc:2", source="abc", kind="abc_license", use_types=["bar"], outcome="pending"),
    ]
    undated = [
        _nearby("no-dates", kind="cua", use_types=["bar"], outcome="approved"),
        _nearby("no-filed", kind="cua", use_types=["bar"], decided_at=_years_ago(1), outcome="denied"),
        _nearby("no-decided", kind="cua", use_types=["bar"], filed_at=_years_ago(2), outcome="withdrawn"),
    ]
    ignored = [
        # still pending: no outcome to count, and not "undated" either
        _nearby("pending", kind="cua", use_types=["bar"], filed_at=_years_ago(1), outcome="pending"),
        # decided, dated, but another use entirely
        _decided("hotel", "approved", use="hotel"),
        # decided twelve years ago: outside every window
        _decided("ancient", "approved", years=12),
    ]
    rows = [*planning, *grant_only, *undated, *ignored]
    rate = analytics.base_rate(rows, WINE_BAR, TODAY, zoning_district=None)
    assert rate.total == 10 and (rate.approved, rate.denied, rate.withdrawn) == (9, 1, 0)
    assert rate.excluded_grant_only == 7 and rate.excluded_undated == 3
    assert rate.rate_shown is True and rate.approval_rate_pct == 90.0
    pool = analytics.base_rate_pool(rows, WINE_BAR, TODAY, 5)
    assert all(a.source == "datasf_planning" and a.filed_at and a.decided_at for a in pool)
    assert {a.source_id for a in pool} == {a.item.source_id for a in planning}
    # however many grants sit nearby, they never produce a rate on their own
    only_grants = analytics.base_rate(grant_only, WINE_BAR, TODAY, zoning_district=None)
    assert (
        only_grants.total == 0 and only_grants.rate_shown is False and only_grants.approval_rate_pct is None
    )
    assert only_grants.excluded_grant_only == 7
    assert only_grants.scope == (
        "N = 0 dated decisions within 1,000 ft, last 10 years (fewer than 5 in the last 5); too few for a rate"
    )
    # a restaurant shares no use type with the bar cases: nothing in the pool, nothing "undated"
    r = analytics.base_rate(rows, restaurant, TODAY, zoning_district=None)
    assert r.total == 0 and r.excluded_undated == 0 and r.excluded_grant_only == 7
    # a Planning row enriched by a Commission motion is still a Planning case
    enriched = _decided("m1", "approved_with_conditions", extra={"motion_url": "https://example.org/m.pdf"})
    assert analytics.base_rate_pool([enriched], WINE_BAR, TODAY, 5)


def test_base_rate_does_not_count_a_row_decided_before_it_was_filed() -> None:
    """`days_to_decision` treats such a row as undated; the pool must too, or it can carry N from 9 to 10
    and switch the rate on."""
    nine = [_decided(f"a{i}", "approved") for i in range(9)]
    backwards = _nearby(
        "backwards",
        kind="cua",
        use_types=["bar"],
        filed_at=_years_ago(1),
        decided_at=_years_ago(2),
        outcome="approved",
    )
    rate = analytics.base_rate([*nine, backwards], WINE_BAR, TODAY, zoning_district=None)
    assert rate.total == 9 and rate.rate_shown is False and rate.approval_rate_pct is None
    assert rate.excluded_undated == 1
    assert "backwards" not in {
        a.source_id for a in analytics.base_rate_pool([*nine, backwards], WINE_BAR, TODAY, 5)
    }
    # decided on the day it was filed is in order, and counts
    same_day = _nearby(
        "same-day",
        kind="cua",
        use_types=["bar"],
        filed_at=_years_ago(1),
        decided_at=_years_ago(1),
        outcome="approved",
    )
    ten = analytics.base_rate([*nine, same_day], WINE_BAR, TODAY, zoning_district=None)
    assert ten.total == 10 and ten.rate_shown is True and ten.excluded_undated == 0


def test_base_rate_window_fallback_follows_the_same_rule() -> None:
    rows = [
        _decided("r1", "approved", years=1),
        _decided("r2", "denied", years=3),
        _decided("old-1", "approved", years=6),
        _decided("old-2", "withdrawn", years=9),
        # filed seven years ago, decided four years ago: the decision date places it in the 5-year window
        _nearby(
            "long",
            kind="cua",
            use_types=["bar"],
            filed_at=_years_ago(7),
            decided_at=_years_ago(4),
            outcome="denied",
        ),
    ]
    rate = analytics.base_rate(rows, WINE_BAR, TODAY, zoning_district="NCT-2")
    # 3 in five years → widen to ten: 5 cases, all in NCT-2
    assert rate.window_years == 10 and rate.total == 5
    assert rate.scope == (
        "N = 5 dated decisions in zoning district NCT-2 (within 1,000 ft), last 10 years "
        "(fewer than 5 in the last 5); too few for a rate"
    )
    assert rate.approval_rate_pct is None


@pytest.mark.anyio
async def test_base_rate_tool_reports_counts_and_no_rate(tmp_path: Path) -> None:
    from app.tools.precedent_tools import BASE_RATE, BaseRateInput, _base_rate

    out = await _base_rate(
        BaseRateInput(lat=VALENCIA.lat, lng=VALENCIA.lng, profile=WINE_BAR, zoning_district="NCT-2")
    )
    data = out.model_dump()
    assert data["total"] == 4 and data["rate_shown"] is False and data["approval_rate_pct"] is None
    assert data["excluded_grant_only"] == 6 and data["excluded_undated"] == 0
    assert data["excluded_not_use_decision"] == 0
    assert data["scope"].startswith("N = 4 dated decisions") and data["scope"].endswith("too few for a rate")
    assert "10 or more" in BASE_RATE.description


@pytest.mark.anyio
async def test_runner_base_rate_reads_past_the_200_nearest_records(tmp_path: Path) -> None:
    """A dense corridor has 400+ records within 1,000 ft; the comparables list keeps the 200 nearest, but the
    base rate must still see every eligible case (the 4 seeded bar cases sit behind 210 closer filler rows)."""
    from precedent.store.local import LocalStore

    from tests.memo_fakes import VALENCIA

    filler = LocalStore(tmp_path / "data")
    rows = [
        Application(
            id=f"datasf_planning:{9000 + i}",
            source="datasf_planning",
            source_id=str(9000 + i),
            source_url="https://example.org/fill",
            fetched_at=dt.datetime(2026, 10, 21, tzinfo=dt.UTC),
            kind="planning_other",
            permit_type="Building permit referral",
            use_types=["other"],
            lat=VALENCIA.lat + 0.000001 * (i % 7),
            lng=VALENCIA.lng + 0.000001 * (i // 7),
            filed_at=dt.date(2010, 1, 1),
            outcome="approved",
        )
        for i in range(210)
    ]
    await filler.upsert_applications(rows)
    _store, _script, _progress, terminal = await run_memo(tmp_path)
    assert terminal[0].type == "memo"
    memo: Memo = terminal[0].data["memo"]
    assert memo.base_rate.total == 4 and memo.base_rate.approval_rate_pct is None
    assert memo.base_rate.excluded_grant_only == 6


@pytest.mark.anyio
async def test_base_rate_pool_is_not_crowded_out_by_grant_only_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1,000 ABC licences at the address are nearer than every Planning decision. They are only counted as
    left out, so they must not use up the read limit of the pool (N would fall from 4 to 0)."""
    from precedent.store.local import LocalStore

    import app.tools.precedent_tools as pt
    from app.tools.precedent_tools import BaseRateInput, _base_rate

    assert analytics.BASE_RATE_LIMIT == 1000
    filler = LocalStore(tmp_path / "data")
    await filler.upsert_applications(
        [
            Application(
                id=f"abc:{7000 + i}",
                source="abc",
                source_id=str(7000 + i),
                source_url="https://example.org/abc",
                fetched_at=dt.datetime(2026, 10, 21, tzinfo=dt.UTC),
                kind="abc_license",
                permit_type="Type 41",
                use_types=["restaurant"],
                lat=VALENCIA.lat,
                lng=VALENCIA.lng,
                status="Active",
                outcome="approved",
                license_type="41",
            )
            for i in range(1000)
        ]
    )
    store, _script, _progress, terminal = await run_memo(tmp_path)
    memo: Memo = terminal[0].data["memo"]
    assert memo.base_rate.total == 4 and memo.base_rate.scope.startswith("N = 4 dated decisions")
    assert memo.base_rate.excluded_grant_only == 1000  # the grant-only read has its own limit
    # the base_rate tool reads the same way
    monkeypatch.setattr(pt, "get_store", lambda: store)
    out = await _base_rate(
        BaseRateInput(lat=VALENCIA.lat, lng=VALENCIA.lng, profile=WINE_BAR, zoning_district="NCT-2")
    )
    assert out.model_dump()["total"] == 4


async def test_opposition_flag_is_withheld_until_validated(tmp_path: Path) -> None:
    """The fixture store marks two comparables as opposed; with REPORT_OPPOSITION_FLAG off (the default)
    neither the model's inputs nor the finished memo may carry the flag."""
    from app.core.config import get_settings

    assert get_settings().REPORT_OPPOSITION_FLAG is False
    _store, script, _progress, terminal = await run_memo(tmp_path)
    memo: Memo = terminal[0].data["memo"]
    assert memo.comparable_cases and all(c.opposition_noted is None for c in memo.comparable_cases)
    sent = json.dumps(script.calls, default=str)
    assert script.calls and '"opposition_noted": true' not in sent and '"opposition_noted": false' not in sent


def test_stored_opposition_sentences_are_scrubbed_from_summaries() -> None:
    from app.tools.precedent_tools import scrub_summary

    stored = (
        "Planning Commission Motion No. 21497 (January 25, 2024) approved with conditions Conditional Use "
        "Authorization 2022-008254CUA. Key operating conditions: Hours; Community Liaison. Opposition was recorded "
        "in public comment."
    )
    assert scrub_summary(stored).endswith("Community Liaison.")
    assert scrub_summary("Minutes item 7 — approved. 3 speaker(s) spoke in opposition at the hearing.") == (
        "Minutes item 7 — approved."
    )
    assert scrub_summary(None) is None


def _comparable(memo: Memo, **changes) -> ComparableCase:  # type: ignore[no-untyped-def]
    return memo.comparable_cases[0].model_copy(update=changes)


@pytest.mark.anyio
async def test_pdf_does_not_print_zero_conditions_for_list_only_cases(
    tmp_path: Path,
) -> None:
    _store, _script, _progress, terminal = await run_memo(tmp_path)
    memo: Memo = terminal[0].data["memo"]
    # a case known only from the DataSF list has no conditions in its source: a dash, never "0"
    assert conditions_cell(_comparable(memo, source="datasf_planning", conditions=[])) == NOT_IN_SOURCE == "–"
    assert conditions_cell(_comparable(memo, source="sf_planning_minutes", conditions=[])) == NOT_IN_SOURCE
    assert conditions_cell(_comparable(memo, source="datasf_planning", conditions=["Close by 1 a.m."])) == "1"
    # a motion was read and adopted no conditions: that is a real zero
    assert conditions_cell(_comparable(memo, source="sf_planning_hearings", conditions=[])) == "0"
    assert (
        conditions_cell(_comparable(memo, source="sf_planning_hearings", conditions=["a", "b", "c"])) == "3"
    )
    list_only = [c for c in memo.comparable_cases if c.source == "datasf_planning" and not c.conditions]
    assert list_only, "the sample memo should include a list-only comparable"
    text = _pdf_text(memo)
    assert NO_CONDITIONS_NOTE in text and "agent-written" not in text and "Takeaway" not in text
    table = text.split("Comparable cases", 1)[1].split("What each source leaves out", 1)[0]
    # the days cell names the outcome its figure is for; the conditions cell after it is the dash
    days = timing_cell(list_only[0], iso_date(memo.data_as_of))
    assert list_only[0].outcome == "denied" and days == f"{list_only[0].days_to_decision} days to denial"
    assert f"{days} – Planning case list (DataSF)" in table
    assert f"{days} 0 Planning case list (DataSF)" not in table


# ---- rule table v2 through the chain -----------------------------------------------------------------------
PRACTICE_NOTE = "Code and Planning practice differ"
PCN_NOTE = "public convenience or necessity finding likely required"
HOW_OBTAINED = (
    "how the liquor licence will be obtained (new, or a transfer from another owner or another location)"
)
STEPS_SENTENCE = (
    "These are review steps inside the approval, where one agency sends the application to another. They are "
    "not separate approvals."
)


def _use_rules(monkeypatch: pytest.MonkeyPatch, rules: Determinations) -> None:
    """Make the runner's rules return `rules`: real rule table v2 output for a district the dated control data
    carries (the seeded store's own district is a made-up one the data does not carry)."""
    monkeypatch.setattr(memo_runner, "determine", lambda *args, **kwargs: rules)


@pytest.mark.anyio
async def test_the_runner_gives_the_rules_the_census_tract_and_the_rules_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, Any]] = []
    real = memo_runner.determine

    def spy(*args: Any, **kwargs: Any) -> Determinations:
        seen.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(memo_runner, "determine", spy)
    # a live report: no rules date is given, so the rules read today's rules; `today` is the runner's own date
    _store, _live_script, _progress, terminal = await run_memo(tmp_path)
    live: Memo = terminal[0].data["memo"]
    tract = tract_at(VALENCIA.lat, VALENCIA.lng)
    assert tract is not None and tract.replace(".", "").isdigit()
    assert seen[0] == {"today": TODAY, "rules_date": None, "tract": tract}
    assert live.pathway.rules_date == TODAY.isoformat() == "2026-10-21"
    # a report for a past rules date carries that date, in the memo, the text report, the PDF and the summary
    past_day = dt.date(2024, 1, 13)
    _store, _script, _progress, terminal = await run_memo(tmp_path, rules_date=past_day)
    past: Memo = terminal[0].data["memo"]
    assert seen[1] == {"today": TODAY, "rules_date": past_day, "tract": tract}
    assert past.pathway.rules_date == "2024-01-13"
    assert "  Rules applied as of 2024-01-13" in report_text(past).splitlines()
    assert "Rules applied as of 2024-01-13" in _pdf_text(past)
    assert status_summary_lines(past)[:2] == ["ROWS", "  Rules applied as of 2024-01-13"]
    assert "read for the rules in force on 2024-01-13" in report_text(past)
    # only the rules read the date: the records, the comparables and the counts are the same in both reports
    assert past.comparable_cases == live.comparable_cases and past.base_rate == live.base_rate
    assert past.site_history == live.site_history
    assert past.data_as_of == live.data_as_of
    # the stored memo round-trips with the date
    assert Memo.model_validate(past.model_dump()).pathway.rules_date == "2024-01-13"


@pytest.mark.anyio
async def test_a_status_note_reaches_the_memo_the_pdf_and_the_text_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each row's status note is the rules', word for word, in the memo, the plain-text report and the PDF."""
    rules = case_determinations("mission-east-restaurant", tmp_path / "case", in_full=True)
    notes = {r.area: r.status_note for r in rules.rows}
    assert notes == {
        "zoning_use": PRACTICE_NOTE,
        "alcohol": PCN_NOTE,
        "health": None,
        "building_change_of_use": None,
    }
    _use_rules(monkeypatch, rules)
    _store, _script, _progress, terminal = await run_memo(tmp_path)
    memo: Memo = terminal[0].data["memo"]
    _assert_memo_is_what_the_rules_decided(memo, rules)
    assert {r.area: (r.status, r.status_note) for r in memo.approvals} == {
        "zoning_use": ("further_review", PRACTICE_NOTE),
        "alcohol": ("further_review", PCN_NOTE),
        "health": ("allowed", None),
        "building_change_of_use": ("insufficient_information", None),
    }
    # the plain-text report: the status with its note, then the approval and the agency
    lines = report_text(memo).splitlines()
    zoning, alcohol = memo.approvals[0], memo.approvals[1]
    assert f"  Zoning and use: Further review: {PRACTICE_NOTE} — {zoning.approval} · {zoning.agency}" in lines
    assert f"  Alcohol licence: Further review: {PCN_NOTE} — {alcohol.approval} · {alcohol.agency}" in lines
    assert (
        "  Health permit: Allowed — Health permit to operate · San Francisco Department of Public Health"
        in lines
    )
    assert status_summary_lines(memo)[2:4] == [
        "  Zoning and use: Further review: Code and Planning practice differ",
        "  Alcohol licence: Further review: public convenience or necessity finding likely required",
    ]
    # the PDF: in the approvals table and at the head of each row's block
    text = _pdf_text(memo)
    assert text.count(f"Further review: {PRACTICE_NOTE}") >= 2
    assert text.count(f"Further review: {PCN_NOTE}") == 2
    assert f"Zoning and use · Further review: {PRACTICE_NOTE} Rules applied" in text
    assert f"Alcohol licence · Further review: {PCN_NOTE} Rules applied" in text
    assert "Health permit · Allowed Rules applied" in text
    # the note changes no status: the overall status is the rows' most severe, as the rules computed it
    assert (memo.overall.status, memo.overall.line) == (rules.overall_status, rules.overall_line)


@pytest.mark.anyio
async def test_the_report_prints_steps_missing_inputs_change_answers_triggers_and_the_records_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = case_determinations("valencia-wine-bar", tmp_path / "case")
    assert rules.pathway.changes is not None
    _use_rules(monkeypatch, rules)
    _store, _script, _progress, terminal = await run_memo(tmp_path)
    memo: Memo = terminal[0].data["memo"]
    rows = {r.area: r for r in memo.approvals}
    steps = [step for row in memo.approvals for step in row.referral_steps]
    assert len(steps) == 14
    # referral steps are never among the approvals or in the entitlement path
    assert len(memo.approvals) == 5 == MemoRunner.teaser(memo).approvals_count
    path = memo.entitlement_path
    assert path == rules.entitlement_path
    assert set(path.split("; ")) <= {r.approval for r in memo.approvals}
    for step in steps:
        assert step.text not in path and all(step.text != r.approval for r in memo.approvals)
    # the headline findings lead (pathway rule 9), then the rows are counted
    assert memo.overall.line.startswith("A Conditional Use Authorization is needed (use control of a special")
    assert " Of the 5 approvals this concept needs:" in memo.overall.line

    # ---- the plain-text report
    text = report_text(memo)
    lines = text.splitlines()
    assert lines.count(f"    Steps inside this approval. {STEPS_SENTENCE}") == 4  # every row but zoning
    for step in steps:
        assert f"      step {rule_line_text(step)}" in lines
    assert f"    Not given: {HOW_OBTAINED}" in lines
    at = lines.index("    Change of use: three separate answers")
    assert lines[at + 1 : at + 4] == [
        "      Planning Code change of use: Yes",
        "      Building Code change of occupancy: Not established",
        "      Neighbourhood notification: Not required",
    ]
    assert lines.count("    Change of use: three separate answers") == 1
    assert lines[at - 1] == f"      step {rule_line_text(rows['building_change_of_use'].referral_steps[0])}"
    # the zoning section: every trigger with its control
    start = lines.index(
        "TRIGGERS: Each reason the Planning Code can require a hearing, read for the rules in force on 2026-11-10."
    )
    assert lines[start + 1 : start + 12] == [f"  {trigger_headline(f)}" for f in rules.pathway.triggers]
    # no story is given and none is assumed (decision of 2026-11-12): T1 is not decided and names the story
    assert (
        "  T1 Use control of the zoning district: Not decided. Not given: which stories the business occupies"
        in lines
    )
    assert "  T2 Use control of a special use district: Conditional use" in lines
    assert (
        "  T5 Formula retail: Not decided. Not given: whether the business is part of a chain that shares its name, look or menu with other locations"
        in lines
    )
    assert (
        "  T7 Use size: Not decided (control in force from 2025-10-06, Ord. 173-25, File No. 250634). "
        "Not given: the floor area of the business, in square feet"
    ) in lines
    assert "  Rules applied as of 2026-11-10" in lines
    # the fixed line on what public records cannot show closes the could-not-establish section
    section = text.split("\nCOULD NOT ESTABLISH\n", 1)[1].split("\n\nSITE HISTORY", 1)[0].splitlines()
    assert section[-1] == f"  {RECORDS_LIMITS}" == f"  {memo.records_limits}"
    assert section[0].startswith(
        "  - (applicant_history) Not known: which stories the business occupies. Needed for: zoning and use."
    )
    assert section[1].startswith(
        "  - (applicant_history) Not known: whether the business is part of a chain that shares its name, look or menu with other locations."
    )
    # the list is the rules' questions, in their order
    asked = [q.question for q in memo.could_not_establish]
    assert asked == [q.question for q in rules.open_questions] and len(asked) == 5
    # each row's status with its missing inputs, as a local run prints it
    assert status_summary_lines(memo) == [
        "ROWS",
        "  Rules applied as of 2026-11-10",
        "  Zoning and use: Insufficient information. Not given: which stories the business occupies; whether the "
        "business is part of a chain that shares its name, look or menu with other locations; whether there is "
        "entertainment, and what kind; the floor area of the business, in square feet",
        f"  Alcohol licence: Insufficient information. Not given: {HOW_OBTAINED}",
        "  Entertainment permit: Further review",
        "  Health permit: Allowed",
        "  Building permit and change of use: Further review",
    ]

    # ---- the PDF
    pdf = _pdf_text(memo)
    blocks = pdf.split("Approvals this concept needs", 1)[1].split("What the records could not establish", 1)[
        0
    ]
    assert blocks.count("Steps inside this approval") == 4 and blocks.count(STEPS_SENTENCE) == 4
    for step in steps:
        assert step.text in blocks
    at = 0
    for part in (  # the alcohol row, in print order
        "Alcohol licence · Insufficient information Rules applied",
        rows["alcohol"].basis[-1].text,
        "Steps inside this approval",
        STEPS_SENTENCE,
        rows["alcohol"].referral_steps[0].text,
        rows["alcohol"].referral_steps[1].text,
        "Not given",
        HOW_OBTAINED,
        "Facts the rules read",
    ):
        found = blocks.find(part, at)
        assert found >= 0, part
        at = found + len(part)
    assert blocks.count("Change of use: three separate answers") == 1
    at = blocks.index("Building permit and change of use · Further review Rules applied")
    for part in (
        "Change of use: three separate answers",
        "Planning Code change of use: Yes",
        "Building Code change of occupancy: Not established",
        "Neighbourhood notification: Not required",
        rules.pathway.changes.neighbourhood_notice_lines[0].text,
        "Facts the rules read",
    ):
        found = blocks.find(part, at)
        assert found >= 0, part
        at = found + len(part)
    glance = pdf.split("At a glance", 1)[1].split("Comparable cases", 1)[0]
    assert (
        "Triggers Each reason the Planning Code can require a hearing, read for the rules in force on 2026-11-10."
        in glance
    )
    for finding in rules.pathway.triggers:
        assert trigger_headline(finding) in glance, finding.rule_id
    assert "Rules applied as of 2026-11-10" in glance
    could_not = pdf.split("What the records could not establish", 1)[1].split("Site history", 1)[0]
    assert could_not.strip().endswith(RECORDS_LIMITS)
    # every record a printed line cites is in the report's citation list or was not among the seeded records
    assert memo.pathway == rules.pathway


@pytest.mark.anyio
async def test_a_control_that_is_not_todays_is_printed_with_the_sentence_that_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = case_determinations(
        "haight-restaurant-alcohol", tmp_path / "case", in_full=True, rules_date=dt.date(2024, 1, 13)
    )
    t4 = next(f for f in rules.pathway.triggers if f.rule_id == "T4")
    (sentence,) = trigger_differs_texts(t4)
    assert t4.differs_today and "2024-01-14" in sentence
    _use_rules(monkeypatch, rules)
    _store, _script, _progress, terminal = await run_memo(tmp_path)
    memo: Memo = terminal[0].data["memo"]
    assert memo.pathway.rules_date == "2024-01-13"
    lines = report_text(memo).splitlines()
    at = lines.index(f"  {trigger_headline(t4)}")
    assert lines[at + 1] == f"    {sentence}"
    assert "  Rules applied as of 2024-01-13" in lines
    pdf = _pdf_text(memo)
    glance = pdf.split("At a glance", 1)[1].split("Comparable cases", 1)[0]
    found = glance.index(trigger_headline(t4))
    assert glance.index(sentence, found) > found
    assert "read for the rules in force on 2024-01-13" in glance


@pytest.mark.anyio
async def test_a_memo_stored_before_rule_table_v2_still_reads_and_prints(tmp_path: Path) -> None:
    """Every field rule table v2 added is optional. A stored memo without them validates, and the plain-text
    report and the PDF print it without the parts it does not have."""
    _store, _script, _progress, terminal = await run_memo(tmp_path)
    stored = terminal[0].data["memo"].model_dump()
    del stored["records_limits"]
    for key in ("rules_date", "triggers", "changes"):
        del stored["pathway"][key]
    for row in stored["approvals"]:
        for key in ("status_note", "referral_steps", "missing_inputs"):
            del row[key]
    old = Memo.model_validate(stored)
    assert (old.pathway.rules_date, old.pathway.triggers, old.pathway.changes) == (None, [], None)
    assert all((r.status_note, r.referral_steps, r.missing_inputs) == (None, [], []) for r in old.approvals)
    assert old.records_limits == RECORDS_LIMITS  # the fixed line is on every report
    text = report_text(old)
    for absent in (
        "Rules applied as of",
        "TRIGGERS:",
        "Steps inside this approval",
        "Not given:",
        "three separate",
    ):
        assert absent not in text, absent
    assert f"  {RECORDS_LIMITS}" in text.splitlines()
    pdf = _pdf_text(old)
    for absent in (
        "Rules applied as of",
        "Triggers",
        "Steps inside this approval",
        "Not given",
        "three separate",
    ):
        assert absent not in pdf, absent
    assert RECORDS_LIMITS in pdf and "Rules applied" in pdf
    assert status_summary_lines(old)[:2] == ["ROWS", "  Zoning and use: Insufficient information"]


async def _run_on_store(store: Any, script: MemoScript | None = None) -> tuple[MemoScript, Memo]:
    script = script or MemoScript()
    runner = MemoRunner(FakeAnthropic(script), get_catalog(), settings, store, FakeGeocoder(), today=TODAY)  # type: ignore[arg-type]

    async def emit(ev: RunnerEvent) -> None:
        return None

    run = runner.run_memo(MemoRunInput(address="995 Valencia St", description=DESC), emit)
    terminal = [ev async for ev in run]
    assert [e.type for e in terminal] == ["memo"], terminal
    memo: Memo = terminal[0].data["memo"]
    return script, memo


@pytest.mark.anyio
async def test_days_from_filing_are_printed_by_outcome_and_never_as_one_figure(tmp_path: Path) -> None:
    """The comparables of the seeded store: approvals, a denial, a case Planning cancelled (stored as
    withdrawn, with the status 'Closed - Cancelled') and a case still pending."""
    store = seed_store(tmp_path / "timing")
    cancelled = store.applications["datasf_planning:6"]
    assert cancelled.outcome == "withdrawn"
    store.applications[cancelled.id] = cancelled.model_copy(update={"status": "Closed - Cancelled"})
    open_case = store.applications["datasf_planning:2"]
    store.applications[open_case.id] = open_case.model_copy(
        update={"outcome": "pending", "status": "Under Review", "decided_at": None}
    )
    _script, memo = await _run_on_store(store)
    by_id = {c.application_id: c for c in memo.comparable_cases}
    assert sorted(c.outcome for c in memo.comparable_cases) == [
        *["approved"] * 4,
        "approved_with_conditions",
        "cancelled",
        "denied",
        "pending",
    ]
    # the cancelled case is named as cancelled, in the table and in the citation list
    assert by_id["datasf_planning:6"].outcome == "cancelled"
    label = next(c.label for c in memo.citations if c.id == "app:datasf_planning:6")
    assert " · cancelled (" in label and "withdrawn" not in label
    as_of = iso_date(memo.data_as_of)
    assert as_of == dt.date(2026, 10, 21)
    pending = by_id["datasf_planning:2"]
    assert pending.days_to_decision is None and pending.filed_at is not None
    age = (as_of - dt.date.fromisoformat(pending.filed_at)).days
    cells = {c.application_id: timing_cell(c, as_of) for c in memo.comparable_cases}
    assert cells == {
        "datasf_planning:1": "120 days to approval",
        "datasf_entertainment:7": "120 days to approval",
        "datasf_planning:2": f"pending {age} days so far",
        "datasf_planning:3": "120 days to denial",
        "datasf_planning:4": "120 days to approval",
        "datasf_planning:5": "120 days to approval",
        "datasf_planning:6": "120 days to cancellation",
        "datasf_planning:9": "120 days to approval",
    }
    wanted = [
        "Approved: 5 cases, 120 days from filing to approval.",
        "Denied: 1 case, 120 days from filing to denial.",
        "Cancelled: 1 case, 120 days from filing to cancellation.",
        f"Still pending: 1 case, {age} days since filing (age so far as of 2026-10-21, not a time to a decision).",
    ]
    # the plain-text report: one line per outcome under its heading
    lines = report_text(memo).splitlines()
    at = lines.index(f"DAYS FROM FILING, BY OUTCOME: {REPORT_TEXT['timing_hint']}")
    assert lines[at + 1 : at + 5] == [f"  {line}" for line in wanted]
    assert lines[at + 5].startswith("ENTITLEMENT PATH (set by rule): ")
    # the PDF: each case's figure names its outcome, and the same lines follow the table
    pdf = _pdf_text(memo)
    table = pdf.split("Comparable cases", 1)[1].split("What each source leaves out", 1)[0]
    assert "Days from filing" in table and "Days to decision" not in pdf
    for cell in cells.values():
        assert cell in table
    assert "Days from filing, by outcome" in table and REPORT_TEXT["timing_hint"] in table
    for line in wanted:
        assert line in table
    assert "Withdrawn:" not in table  # no withdrawn case is left: the cancelled one is not counted as one
    # no figure anywhere is taken across outcomes: no mean, median or overall range of the comparables
    figures = [120] * 7 + [age]
    blended = {f"{round(sum(figures) / len(figures)):,} days", f"120 to {age} days"}
    assert not any(value in pdf or value in report_text(memo) for value in blended)
    for word in ("average", "median"):
        assert word not in table.lower().replace("no average is given", "")


# ---- the command-line runs --------------------------------------------------------------------------------
def test_the_local_run_script_takes_a_rules_date(monkeypatch: pytest.MonkeyPatch) -> None:
    local = _load_script("run_report_local", monkeypatch)
    parser = local.build_parser()
    assert parser.parse_args(["995 Valencia St", DESC]).rules_date is None  # today's rules
    args = parser.parse_args(["995 Valencia St", DESC, "--rules-date", "2024-01-13"])
    assert args.rules_date == dt.date(2024, 1, 13)
    assert local.rules_date_arg("2025-08-17") == dt.date(2025, 8, 17)
    for bad in ("2024-13-01", "13 January 2024", "yesterday", ""):
        with pytest.raises(SystemExit):
            parser.parse_args(["995 Valencia St", DESC, "--rules-date", bad])
    # the date reaches the run; no model is called: the run itself is a stub
    seen: dict[str, Any] = {}

    async def generate(address: str, description: str, **kwargs: Any) -> int:
        seen.update(address=address, description=description, **kwargs)
        return 0

    stub = ModuleType("app.scripts.memo_demo")
    stub.generate = generate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.scripts.memo_demo", stub)
    monkeypatch.setattr(local, "install_usage_meter", lambda: None)
    monkeypatch.setattr(
        settings, "PRECEDENT_DATABASE_URL", "postgresql://postgres@localhost:55433/sfhp_local"
    )
    monkeypatch.setattr(
        sys, "argv", ["run_report_local.py", "995 Valencia St", DESC, "--rules-date", "2024-01-13"]
    )
    assert local.main() == 0
    assert (seen["address"], seen["description"], seen["rules_date"]) == (
        "995 Valencia St",
        DESC,
        dt.date(2024, 1, 13),
    )
    monkeypatch.setattr(sys, "argv", ["run_report_local.py", "995 Valencia St", DESC])
    assert local.main() == 0 and seen["rules_date"] is None


@pytest.mark.anyio
async def test_the_command_line_run_prints_each_rows_status_with_its_note_and_missing_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`memo_demo.generate`, which the local run script calls: the summary it prints ends with the rules date
    and one line per row. The scripted model stands in for the real one; tracing is not started."""
    import neatlogs

    monkeypatch.setattr(neatlogs, "init", lambda **kwargs: None)
    demo = importlib.import_module("app.scripts.memo_demo")
    rules = case_determinations("mission-east-restaurant", tmp_path / "case", in_full=True)
    seen: list[dict[str, Any]] = []

    def determine(*args: Any, **kwargs: Any) -> Determinations:
        seen.append(kwargs)
        return rules

    monkeypatch.setattr(memo_runner, "determine", determine)
    store = seed_store(tmp_path / "demo")
    runner = MemoRunner(
        FakeAnthropic(MemoScript()), get_catalog(), settings, store, FakeGeocoder(), today=TODAY
    )  # type: ignore[arg-type]
    monkeypatch.setattr(demo, "get_memo_runner", lambda: runner)
    out_json = tmp_path / "memo.json"
    code = await demo.generate(
        "995 Valencia St", DESC, pdf=None, out_json=out_json, quiet=True, rules_date=dt.date(2024, 1, 13)
    )
    assert code == 0
    assert seen[0]["rules_date"] == dt.date(2024, 1, 13)
    printed = capsys.readouterr().err
    missing = "; ".join(rules.rows[-1].missing_inputs)
    assert (
        "ROWS\n"
        f"  Rules applied as of {rules.pathway.rules_date}\n"
        "  Zoning and use: Further review: Code and Planning practice differ\n"
        "  Alcohol licence: Further review: public convenience or necessity finding likely required\n"
        "  Health permit: Allowed\n"
        f"  Building permit and change of use: Insufficient information. Not given: {missing}\n"
    ) in printed
    assert json.loads(out_json.read_text())["approvals"][0]["status_note"] == PRACTICE_NOTE
    args = demo.build_parser().parse_args(["995 Valencia St", DESC, "--rules-date", "2024-01-13"])
    assert args.rules_date == dt.date(2024, 1, 13)
    assert demo.build_parser().parse_args(["995 Valencia St", DESC]).rules_date is None


@pytest.mark.anyio
async def test_the_rules_read_what_intake_gave_not_the_beer_and_wine_default(tmp_path: Path) -> None:
    """Decision 1: `BusinessProfile.normalized()` no longer fills "beer_wine" for a concept that serves alcohol
    without saying what it pours: it sets "unknown", and the rules read the normalised profile itself (the
    runner's workaround that undid the default is gone), so no licence type is derived from a guess. (Zoning
    bars the Bar at the seeded address, so the row is not permitted; it names no type.)"""
    script = MemoScript()
    script.profile = {**script.profile, "serves_alcohol": True, "alcohol_type": "none"}
    assert BusinessProfile.model_validate(script.profile).normalized().alcohol_type == "unknown"
    _store, _script, _progress, terminal = await run_memo(tmp_path, script)
    memo: Memo = terminal[0].data["memo"]
    alcohol = next(r for r in memo.approvals if r.area == "alcohol")
    # no licence type is derived from the default: the approval names no type (it read "ABC licence, Type 42")
    assert alcohol.approval == "ABC licence"
    assert not any("derived ABC Type" in line.text for line in alcohol.basis)
    t4 = next(f for f in memo.pathway.triggers if f.rule_id == "T4")
    assert "Type 42" not in " ".join(line.text for line in t4.lines)
