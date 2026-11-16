"""The optional intake questions (app.memo.intake): the questions as data, every branch of the mapping onto the
profile, what each skipped question leaves missing for the rules, the backtest's answers, the API and the local
run script. No database, no network, no model (the API tests use the scripted model of the other memo tests).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pydantic import ValidationError

from app.agents.memo_runner import required_areas
from app.core.config import settings
from app.memo import controls, tracts
from app.memo.facts import MISSING_PHRASES, concept_facts, profile_from_facts
from app.memo.intake import (
    ELEVEN_OR_MORE,
    EXISTING_OCCUPANCY_GROUP_FACT,
    FORMULA_RETAIL_OTHER_LOCATIONS,
    QUESTIONS,
    SKIP_LABEL,
    SKIP_NOTE,
    IntakeAnswers,
    apply_intake_answers,
    intake_answers,
    intake_answers_from_case,
)
from app.memo.pathway import determine
from app.memo.report import site_records
from app.models.memo import Determinations
from app.models.profile import BusinessProfile
from tests.test_pathway_cases import CASES, RULES_DATE, licence_rows, site_of_case, store_lookup

REPO = Path(__file__).resolve().parents[3]
WEB_INTAKE = REPO / "apps" / "web" / "src" / "lib" / "intake.ts"
INPUTS = REPO / "backtest" / "inputs.json"
SCRIPTS = REPO / "scripts" / "validation"

CHAIN = MISSING_PHRASES["formula_retail"]
COUNT = MISSING_PHRASES["other_locations"]
FLOOR = MISSING_PHRASES["floor_area_sqft"]
HOW_OBTAINED = MISSING_PHRASES["alcohol_transaction"]
POURS = MISSING_PHRASES["alcohol_served"]
ALL_ANSWERED = IntakeAnswers(part_of_chain=False, floor_area_sqft=1800, liquor_licence="new")


def bar(**fields: Any) -> BusinessProfile:
    """A wine bar as the intake model reads "40-seat wine bar ...": it serves beer and wine."""
    base: dict[str, Any] = {"business_type": "bar", "serves_alcohol": True, "alcohol_type": "beer_wine"}
    return BusinessProfile.model_validate({**base, **fields})


def cafe(**fields: Any) -> BusinessProfile:
    """A coffee shop whose description says nothing about alcohol."""
    return BusinessProfile.model_validate({"business_type": "cafe", **fields})


# ---- the questions, as data ----------------------------------------------------------------------------------
def test_the_questions_are_fixed_and_name_the_fact_each_one_gives() -> None:
    assert [(q.id, q.question) for q in QUESTIONS] == [
        (
            "part_of_chain",
            "Is the business part of a chain that shares its name, look or menu with other locations?",
        ),
        (
            "other_locations",
            "How many other locations does the chain have, open or approved, anywhere in the world?",
        ),
        ("floor_area_sqft", "What is the floor area of the business, in square feet?"),
        ("liquor_licence", "How will the liquor licence be obtained?"),
        ("stories", "Which stories does the business occupy?"),
        ("alcohol_served", "What alcohol will be served: beer and wine, or spirits too?"),
        ("closing_time", "What is the closing time?"),
        ("last_use", "What was the space last used as?"),
        ("fewer_than_50_people", "Is the space for fewer than 50 people?"),
        ("outdoor_area", "Where is the outdoor area?"),
        ("outdoor_alcohol_service", "Will alcohol be served in the outdoor area?"),
        ("food_service", "What kind of food or drink service is it?"),
        ("existing_business_change", "Is an existing business to be enlarged or intensified?"),
        ("floor_area_before_sqft", "What was the floor area before the project, in square feet?"),
        ("merges_storefronts", "Are storefronts to be merged?"),
        ("amends_prior_approval", "Are the conditions of an earlier approval to be changed?"),
        ("entertainment", "Is there entertainment, and what kind?"),
        (
            "existing_occupancy_group",
            "What occupancy group do the plans or the certificate of occupancy of the existing space show?",
        ),
    ]
    by_id = {q.id: q for q in QUESTIONS}
    assert [(a.value, a.label) for a in by_id["liquor_licence"].answers] == [
        ("new", "New licence"),
        ("transfer_from_another_owner", "Transfer from another owner"),
        ("transfer_from_another_location", "Transfer from another location"),
        ("already_held", "Already hold a licence at this address"),
        ("none", "No alcohol"),
    ]
    assert [a.value for a in by_id["part_of_chain"].answers] == ["yes", "no"]
    assert by_id["other_locations"].shown_when == "part_of_chain=yes"
    assert SKIP_NOTE == "Optional. If you skip it, the report will say it could not tell."
    assert SKIP_LABEL == "Skip"
    # the IntakeAnswers keys are the question ids, and every question's fact has a fixed missing phrase
    assert [q.id for q in QUESTIONS] == list(IntakeAnswers.model_fields)
    for q in QUESTIONS:
        # the existing occupancy group is the one input a question gives that is not a concept fact
        assert q.fact in MISSING_PHRASES or q.fact == EXISTING_OCCUPANCY_GROUP_FACT
        assert q.help.strip() and q.question.endswith("?")


def test_the_missing_phrases_use_the_words_of_the_questions() -> None:
    """The applicant recognises the question they skipped in the report's "Not given" list."""
    by_id = {q.id: q.question for q in QUESTIONS}
    assert (
        CHAIN
        == "whether the business is part of a chain that shares its name, look or menu with other locations"
    )
    assert by_id["part_of_chain"] == f"Is the business {CHAIN.removeprefix('whether the business is ')}?"
    assert COUNT == "how many other locations the chain has, open or approved, anywhere in the world"
    assert "open or approved, anywhere in the world" in by_id["other_locations"]
    assert FLOOR == "the floor area of the business, in square feet"
    assert by_id["floor_area_sqft"] == f"What is {FLOOR}?"
    assert HOW_OBTAINED.startswith("how the liquor licence will be obtained")
    assert by_id["liquor_licence"] == "How will the liquor licence be obtained?"
    # "whether the business is part of a chain" and "how many other locations the chain has" are told apart
    assert COUNT != CHAIN and "how many" not in CHAIN and "whether" not in COUNT


def test_the_count_follows_planning_code_section_303_1_in_every_dated_version() -> None:
    doc = json.loads(controls.DATA_PATH.read_text(encoding="utf-8"))
    versions = doc["citywide"]["formula_retail_definition"]
    assert versions
    for v in versions:
        assert v["facts"]["other_establishments_minimum"] == FORMULA_RETAIL_OTHER_LOCATIONS == 11
        assert "eleven or more other retail sales establishments" in v["rule"]
        assert "anywhere in the world" in v["rule"] and "permit entitlements already approved" in v["rule"]


def test_the_web_page_asks_the_same_questions() -> None:
    if not WEB_INTAKE.is_file():
        pytest.skip("apps/web is not in this checkout")
    text = WEB_INTAKE.read_text(encoding="utf-8")
    for q in QUESTIONS:
        assert json.dumps(q.question) in text, q.id
        for a in q.answers:
            assert json.dumps(a.label) in text and json.dumps(a.value) in text, a.value
    assert json.dumps(SKIP_NOTE) in text and json.dumps(SKIP_LABEL) in text


# ---- validation ------------------------------------------------------------------------------------------------
def test_every_answer_is_optional() -> None:
    assert IntakeAnswers().empty and IntakeAnswers().answered() == ()
    assert IntakeAnswers.model_validate({}).empty
    assert IntakeAnswers.model_validate({"part_of_chain": None, "liquor_licence": None}).empty
    full = IntakeAnswers(part_of_chain=True, other_locations=4, floor_area_sqft=900, liquor_licence="none")
    assert full.answered() == ("part_of_chain", "other_locations", "floor_area_sqft", "liquor_licence")


@pytest.mark.parametrize(
    "bad",
    [
        {"other_locations": 3},  # a count without the chain answer
        {"part_of_chain": False, "other_locations": 3},
        {"part_of_chain": True, "other_locations": -1},
        {"part_of_chain": True, "other_locations": 100_001},
        {"part_of_chain": True, "other_locations": "12"},
        {"part_of_chain": True, "other_locations": 12.5},
        {"part_of_chain": True, "other_locations": True},
        {"part_of_chain": "yes"},
        {"floor_area_sqft": 0},
        {"floor_area_sqft": -10},
        {"floor_area_sqft": 1_000_001},
        {"floor_area_sqft": "1800"},
        {"liquor_licence": "transfer"},
        {"liquor_licence": ""},
        {"square_feet": 1800},  # not a question
    ],
)
def test_answers_outside_the_allowed_values_are_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        IntakeAnswers.model_validate(bad)


# ---- the mapping, branch by branch --------------------------------------------------------------------------
def test_no_answer_changes_nothing() -> None:
    p = bar(formula_retail=True, square_feet=900, alcohol_transaction="new_licence")
    assert apply_intake_answers(p, IntakeAnswers()) is p
    # the same facts; only code's record of what was answered is added
    assert apply_intake_answers(p, IntakeAnswers(floor_area_sqft=900)) == p.model_copy(
        update={"intake_answered": ["square_feet"]}
    )


def test_not_a_chain() -> None:
    out = apply_intake_answers(
        bar(formula_retail=True, other_locations=40), IntakeAnswers(part_of_chain=False)
    )
    assert (out.part_of_chain, out.formula_retail, out.other_locations) == (False, False, None)
    assert concept_facts(out).formula_retail.source == "stated"


@pytest.mark.parametrize(
    ("count", "formula_retail"), [(0, False), (1, False), (10, False), (11, True), (12, True), (500, True)]
)
def test_a_chain_is_formula_retail_from_eleven_other_locations(count: int, formula_retail: bool) -> None:
    out = apply_intake_answers(bar(), IntakeAnswers(part_of_chain=True, other_locations=count))
    assert (out.part_of_chain, out.other_locations, out.formula_retail) == (True, count, formula_retail)
    facts = concept_facts(out)
    assert facts.formula_retail.stated and facts.other_locations.stated
    assert facts.missing(["formula_retail"]) == ()


def test_a_chain_with_the_count_skipped_is_not_decided_and_names_the_count() -> None:
    # the answer wins over what the model read from the description ("part of a chain" -> True)
    out = apply_intake_answers(bar(formula_retail=True), IntakeAnswers(part_of_chain=True))
    assert (out.part_of_chain, out.formula_retail, out.other_locations) == (True, None, None)
    facts = concept_facts(out)
    assert facts.formula_retail.missing and facts.chain_count_missing
    assert facts.missing(["formula_retail"]) == (COUNT,)
    assert facts.missing_names(["formula_retail", "floor_area_sqft"]) == (
        "other_locations",
        "floor_area_sqft",
    )
    assert COUNT in facts.missing() and CHAIN not in facts.missing()


def test_the_chain_question_skipped_names_the_chain_question() -> None:
    facts = concept_facts(apply_intake_answers(bar(), IntakeAnswers(floor_area_sqft=1200)))
    assert facts.missing(["formula_retail"]) == (CHAIN,)
    assert CHAIN in facts.missing() and COUNT not in facts.missing()
    assert facts.part_of_chain is None and not facts.chain_count_missing


def test_the_floor_area() -> None:
    out = apply_intake_answers(bar(square_feet=900), IntakeAnswers(floor_area_sqft=2400))
    assert out.square_feet == 2400  # the answer wins over the description
    assert concept_facts(out).floor_area_sqft.source == "stated"
    assert concept_facts(bar()).missing(["floor_area_sqft"]) == (FLOOR,)


@pytest.mark.parametrize(
    ("answer", "transaction"),
    [
        ("new", "new_licence"),
        ("transfer_from_another_owner", "person_to_person_transfer"),
        ("transfer_from_another_location", "premises_transfer"),
        ("already_held", "licence_already_held"),
    ],
)
def test_obtaining_a_licence_serves_alcohol_and_keeps_what_the_description_pours(
    answer: str, transaction: str
) -> None:
    answers = IntakeAnswers.model_validate({"liquor_licence": answer})
    wine = apply_intake_answers(bar(alcohol_transaction="licence_already_held"), answers)
    assert (wine.alcohol_transaction, wine.serves_alcohol, wine.alcohol_type) == (
        transaction,
        True,
        "beer_wine",
    )
    assert concept_facts(wine).alcohol_transaction.source == "stated"
    # a description that says nothing about alcohol: the answer says it serves alcohol, but not what it pours,
    # so no licence type is derived; normalised, what is poured is "unknown" (never a guess), and the rules
    # name what alcohol will be served in place of the licence type
    dry = apply_intake_answers(cafe(), answers)
    assert (dry.alcohol_transaction, dry.serves_alcohol, dry.alcohol_type) == (transaction, True, "none")
    assert dry.normalized().alcohol_type == "unknown"
    assert "alcohol" in required_areas(dry)
    for read in (dry, dry.normalized()):
        assert concept_facts(read).missing(["licence_type", "alcohol_transaction"]) == (POURS,)


def test_already_held_is_only_the_answer_never_the_description() -> None:
    """Decision 2: "already hold a licence at this address" is its own answer. The description never sets it,
    and no other answer does."""
    for answer in ("new", "transfer_from_another_owner", "transfer_from_another_location", "none", None):
        out = apply_intake_answers(bar(), IntakeAnswers.model_validate({"liquor_licence": answer}))
        assert out.alcohol_transaction != "licence_already_held", answer
    held = apply_intake_answers(cafe(), IntakeAnswers(liquor_licence="already_held"))
    assert (held.alcohol_transaction, held.serves_alcohol) == ("licence_already_held", True)
    assert held.no_alcohol_answer_over_description is False


@pytest.mark.parametrize(
    "described",
    [
        {},  # the description says nothing about alcohol
        {"serves_alcohol": True, "alcohol_type": "beer_wine"},
        {"serves_alcohol": True, "alcohol_type": "unknown"},
        {"alcohol_type": "full_liquor"},
        {"serves_alcohol": True, "licence_type": "47", "alcohol_transaction": "premises_transfer"},
        {"outdoor_alcohol_service": True},
    ],
)
def test_no_alcohol_is_no_alcohol_whatever_the_description_said(described: dict[str, Any]) -> None:
    """Decision 2: "No alcohol" -> serves_alcohol False, alcohol_type "none", whatever the description said. The
    applicant's answer wins, and where the description mentioned alcohol the profile says so for the rules."""
    out = apply_intake_answers(cafe(**described), IntakeAnswers(liquor_licence="none"))
    assert (out.serves_alcohol, out.alcohol_type, out.alcohol_transaction, out.licence_type) == (
        False,
        "none",
        None,
        None,
    )
    assert out.outdoor_alcohol_service is not True
    assert out.no_alcohol_answer_over_description is bool(described)
    assert "alcohol" not in required_areas(out)
    assert out.normalized().alcohol_type == "none"


def test_the_answers_do_not_change_the_profile_passed_in() -> None:
    p = bar()
    before = p.model_dump()
    apply_intake_answers(p, IntakeAnswers(part_of_chain=True, other_locations=30, floor_area_sqft=5000))
    assert p.model_dump() == before


def test_the_intake_model_is_not_shown_the_chain_answer() -> None:
    from app.agents.runner import SUBMIT_INTAKE

    schema = json.dumps(SUBMIT_INTAKE.to_anthropic()["input_schema"])
    assert "part_of_chain" not in schema
    assert "no_alcohol_answer_over_description" not in schema  # set only by the "No alcohol" answer
    assert '"unknown"' in schema  # what is served may be left unknown, never guessed
    # given only by the applicant's answers (MODEL_MAY_NOT_SET), so the model is not shown them either
    for key in ("other_locations", "formula_retail", "alcohol_transaction", "occupants_under_50"):
        assert f'"{key}"' not in schema, key


# ---- each skipped question leaves its fact missing for the rules -----------------------------------------------
def _run(case_id: str, profile: BusinessProfile, data_dir: Path) -> Determinations:
    case = next(c for c in CASES if c["id"] == case_id)
    zoning, overlays = store_lookup(case, data_dir)
    site = site_of_case(case)
    return determine(
        profile,
        zoning,
        overlays,
        site_records(licence_rows(case), site),
        site,
        required_areas(profile),
        today=RULES_DATE,
        rules_date=RULES_DATE,
        tract=tracts.tract_at(case["lat"], case["lng"]),
    )


def _wine_bar() -> BusinessProfile:
    """995 Valencia St, "40-seat wine bar, small kitchen, open until 1am, occasional live music", as the
    pathway cases record the intake model's profile."""
    case = next(c for c in CASES if c["id"] == "valencia-wine-bar")
    return BusinessProfile.model_validate(case["profile"])


def _on_first_story(profile: BusinessProfile) -> BusinessProfile:
    """The profile on the first story, stated. The intake asks no story question and the rules never assume one
    (decision of 2026-11-12), so the tests about the intake answers state it."""
    return profile.model_copy(update={"stories": ["first"]})


def _row(d: Determinations, area: str) -> Any:
    return next(r for r in d.rows if r.area == area)


def _trigger(d: Determinations, rule_id: str) -> Any:
    return next(t for t in d.pathway.triggers if t.rule_id == rule_id)


def _asked(d: Determinations) -> list[str]:
    return [q.question for q in d.open_questions]


def test_995_valencia_with_nothing_answered_names_all_three(tmp_path: Path) -> None:
    d = _run(
        "valencia-wine-bar", apply_intake_answers(_on_first_story(_wine_bar()), IntakeAnswers()), tmp_path
    )
    alcohol = _row(d, "alcohol")
    assert (alcohol.status, alcohol.missing_inputs) == ("insufficient_information", [HOW_OBTAINED])
    # the zoning row: the district already makes a Bar conditional, so its status is decided, and the formula
    # retail and use size triggers name what they were not given
    zoning = _row(d, "zoning_use")
    assert (zoning.status, zoning.missing_inputs) == ("further_review", [])
    assert (_trigger(d, "T5").control, _trigger(d, "T5").missing_inputs) == ("not_decided", [CHAIN])
    assert (_trigger(d, "T7").control, _trigger(d, "T7").missing_inputs) == ("not_decided", [FLOOR])
    asked = _asked(d)
    assert f"Not known: {CHAIN}. Needed for: zoning and use." in asked
    assert f"Not known: {FLOOR}. Needed for: zoning and use." in asked
    assert any(q.startswith(f"Not known: {HOW_OBTAINED}") for q in asked)
    # as recorded, with no story: no story is assumed, so the zoning row is insufficient information and names
    # the story first, although the district makes a Bar conditional on the first story
    recorded = _run("valencia-wine-bar", apply_intake_answers(_wine_bar(), IntakeAnswers()), tmp_path / "r")
    zoning = _row(recorded, "zoning_use")
    assert zoning.status == "insufficient_information"
    assert zoning.missing_inputs[0] == MISSING_PHRASES["stories"] and CHAIN in zoning.missing_inputs
    assert f"Not known: {MISSING_PHRASES['stories']}. Needed for: zoning and use." in _asked(recorded)


def test_995_valencia_with_all_three_answered_names_none_of_them(tmp_path: Path) -> None:
    d = _run("valencia-wine-bar", apply_intake_answers(_on_first_story(_wine_bar()), ALL_ANSWERED), tmp_path)
    alcohol = _row(d, "alcohol")
    assert alcohol.status != "insufficient_information" and alcohol.missing_inputs == []
    assert any("as a new licence, as the applicant states" in line.text for line in alcohol.basis)
    zoning = _row(d, "zoning_use")
    assert (zoning.status, zoning.missing_inputs) == ("further_review", [])
    assert (_trigger(d, "T5").control, _trigger(d, "T5").missing_inputs) == ("principal", [])
    assert (_trigger(d, "T7").control, _trigger(d, "T7").missing_inputs) == ("principal", [])
    asked = " ".join(_asked(d))
    for phrase in (CHAIN, COUNT, FLOOR, HOW_OBTAINED):
        assert phrase not in asked
    # the questions the intake does not ask are still named
    assert _trigger(d, "T6").missing_inputs == [MISSING_PHRASES["entertainment_kind"]]


def test_995_valencia_a_chain_with_the_count_skipped_names_the_count(tmp_path: Path) -> None:
    answers = IntakeAnswers(part_of_chain=True, floor_area_sqft=1800, liquor_licence="new")
    d = _run("valencia-wine-bar", apply_intake_answers(_wine_bar(), answers), tmp_path)
    t5 = _trigger(d, "T5")
    assert (t5.control, t5.missing_inputs) == ("not_decided", [COUNT])
    assert [line.rule_id for line in t5.lines][-1] == "T5.count_missing"
    assert "how many other locations it has" in t5.lines[-1].text
    assert f"Not known: {COUNT}. Needed for: zoning and use." in _asked(d)
    assert not any(CHAIN in q for q in _asked(d))


def test_995_valencia_a_chain_of_eleven_or_more_reads_the_formula_retail_control(tmp_path: Path) -> None:
    answers = IntakeAnswers(
        part_of_chain=True, other_locations=11, floor_area_sqft=1800, liquor_licence="new"
    )
    d = _run("valencia-wine-bar", apply_intake_answers(_wine_bar(), answers), tmp_path)
    assert (_trigger(d, "T5").control, _trigger(d, "T5").missing_inputs) == ("conditional", [])
    below = answers.model_copy(update={"other_locations": 10})
    d = _run("valencia-wine-bar", apply_intake_answers(_wine_bar(), below), tmp_path / "below")
    t5 = _trigger(d, "T5")
    assert (t5.control, [line.rule_id for line in t5.lines]) == ("principal", ["T5.under_count"])
    assert t5.lines[0].text == (
        "The applicant says the chain has 10 other locations. Planning Code § 303.1 counts a business as formula "
        "retail from eleven other locations, so the formula retail control asks for nothing."
    )


def test_995_valencia_already_held_is_the_licence_already_held(tmp_path: Path) -> None:
    d = _run(
        "valencia-wine-bar",
        apply_intake_answers(_wine_bar(), IntakeAnswers(liquor_licence="already_held")),
        tmp_path,
    )
    alcohol = _row(d, "alcohol")
    assert HOW_OBTAINED not in alcohol.missing_inputs
    assert any("already holds the licence, as the applicant states" in line.text for line in alcohol.basis)
    assert not any(line.rule_id == "intake.no_alcohol" for line in d.pathway.lines)


def test_995_valencia_no_alcohol_wins_over_the_wine_bar_and_says_so(tmp_path: Path) -> None:
    """The description is a wine bar; the applicant answers "No alcohol". The answer is the one read, and the
    pathway's first line says so. Since 2026-11-16 (pathway rule 1b) a bar that serves no alcohol is not a Bar
    (§ 102: a Bar provides on-site alcohol sales): no use is assumed in its place, there is no alcohol row, and the
    zoning row names the kind of food or drink service. Before, the Bar kept its alcohol row and named the licence
    type, which no answer could give."""
    profile = apply_intake_answers(_wine_bar(), IntakeAnswers(liquor_licence="none")).normalized()
    assert (profile.serves_alcohol, profile.alcohol_type) == (False, "none")
    d = _run("valencia-wine-bar", profile, tmp_path)
    first = d.pathway.lines[0]
    assert first.rule_id == "intake.no_alcohol"
    assert first.text == (
        'The applicant answered "No alcohol" to the liquor licence question. The description mentioned alcohol; '
        "the applicant's answer is the one the rules read, so the concept is read as serving no alcohol."
    )
    assert "alcohol" not in {r.area for r in d.rows}
    assert d.pathway.use == "not_covered"
    zoning = _row(d, "zoning_use")
    assert zoning.status == "insufficient_information"
    assert MISSING_PHRASES["food_service"] in zoning.missing_inputs
    assert not any(MISSING_PHRASES["licence_type"] in q.question for q in d.open_questions)
    # a description without alcohol and the same answer: nothing to say
    dry = apply_intake_answers(cafe(), IntakeAnswers(liquor_licence="none"))
    quiet = _run("cafe-no-alcohol", dry, tmp_path / "dry")
    assert not any(line.rule_id == "intake.no_alcohol" for line in quiet.pathway.lines)


def test_995_valencia_a_bar_with_drinks_names_what_will_be_served(tmp_path: Path) -> None:
    """Decision 1: a bar that serves alcohol without saying what. No licence type is derived; the alcohol row is
    insufficient information and names what alcohol will be served."""
    vague = _wine_bar().model_copy(update={"alcohol_type": "none"}).normalized()
    assert vague.alcohol_type == "unknown"
    d = _run("valencia-wine-bar", vague, tmp_path)
    alcohol = _row(d, "alcohol")
    assert alcohol.status == "insufficient_information"
    assert alcohol.missing_inputs[:2] == [POURS, HOW_OBTAINED]
    assert alcohol.approval == "ABC licence"
    assert MISSING_PHRASES["licence_type"] not in alcohol.missing_inputs
    # a stated licence type still decides it
    typed = _run("valencia-wine-bar", vague.model_copy(update={"licence_type": "42"}), tmp_path / "typed")
    assert POURS not in _row(typed, "alcohol").missing_inputs
    assert _row(typed, "alcohol").approval.startswith("ABC licence, Type 42")


def test_a_zoning_row_that_lacks_the_chain_and_the_floor_area_names_them_until_answered(
    tmp_path: Path,
) -> None:
    """NCT-3, a restaurant with a full bar on the first story: the zoning row itself is insufficient information
    until the chain and floor area questions are answered."""
    case = next(c for c in CASES if c["id"] == "nct3-restaurant")
    profile = _on_first_story(BusinessProfile.model_validate(case["profile"]))
    skipped = _run("nct3-restaurant", profile, tmp_path / "skipped")
    zoning = _row(skipped, "zoning_use")
    assert zoning.status == "insufficient_information"
    assert zoning.missing_inputs == [CHAIN, FLOOR]
    answered = _run(
        "nct3-restaurant",
        apply_intake_answers(profile, IntakeAnswers(part_of_chain=False, floor_area_sqft=1500)),
        tmp_path / "answered",
    )
    zoning = _row(answered, "zoning_use")
    assert zoning.status != "insufficient_information" and zoning.missing_inputs == []
    # a chain with its count skipped: the zoning row names the count, not the chain question
    count_skipped = _run(
        "nct3-restaurant",
        apply_intake_answers(profile, IntakeAnswers(part_of_chain=True, floor_area_sqft=1500)),
        tmp_path / "count",
    )
    zoning = _row(count_skipped, "zoning_use")
    assert (zoning.status, zoning.missing_inputs) == ("insufficient_information", [COUNT])


# ---- the backtest: the same questions, answered where the case file states them --------------------------------
def _cases() -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = json.loads(INPUTS.read_text(encoding="utf-8"))["cases"]
    return cases


def test_every_backtest_case_builds_a_profile_from_its_input_facts_and_intake_answers() -> None:
    cases = _cases()
    assert len(cases) == 40
    empty = 0
    for case_id, case in cases.items():
        assert set(case["intake_answers"]) <= set(IntakeAnswers.model_fields), case_id
        answers = intake_answers_from_case(case)
        before = profile_from_facts(case["input_facts"])
        after = apply_intake_answers(before, answers)
        BusinessProfile.model_validate(after.model_dump())  # still a valid profile
        concept_facts(after)
        if answers.empty:
            empty += 1
            assert after == before, case_id  # no answer: the same profile as before
            continue
        if answers.floor_area_sqft is not None:
            assert after.square_feet == answers.floor_area_sqft, case_id
        if answers.part_of_chain is False:
            assert after.formula_retail is False, case_id
        if answers.liquor_licence in ("new", "transfer_from_another_owner", "transfer_from_another_location"):
            assert after.serves_alcohol is True and after.alcohol_transaction is not None, case_id
    assert empty == sum(1 for c in cases.values() if not c["intake_answers"]) > 0


def test_the_backtest_answers_case_by_case() -> None:
    cases = _cases()

    def after(case_id: str) -> BusinessProfile:
        case = cases[case_id]
        return apply_intake_answers(profile_from_facts(case["input_facts"]), intake_answers_from_case(case))

    # "11_or_more": the record calls the use Formula Retail without giving the count
    assert cases["D04"]["intake_answers"]["other_locations"] == ELEVEN_OR_MORE
    assert intake_answers_from_case(cases["D04"]).other_locations == 11
    assert (after("D04").formula_retail, after("D04").other_locations, after("D04").square_feet) == (
        True,
        11,
        1378,
    )
    assert after("N07").formula_retail is False
    assert after("D03").square_feet == 5478  # the case file's figure wins over the concept text's 2,300
    assert after("N02").alcohol_transaction == "new_licence"
    assert after("D02").alcohol_transaction == "premises_transfer"
    # the three cases whose file says the licence is already held at the address answer "already_held" (they
    # answered "none" before decision 2, which read two of them as serving no alcohol)
    for case_id in ("N11", "D09", "D10"):
        assert cases[case_id]["intake_answers"]["liquor_licence"] == "already_held", case_id
        assert (after(case_id).alcohol_transaction, after(case_id).serves_alcohol) == (
            "licence_already_held",
            True,
        ), case_id
    # no case answers "No alcohol": none of the case files says the business serves none
    assert not [c for c, case in cases.items() if case["intake_answers"].get("liquor_licence") == "none"]


def test_intake_answers_from_data_read_eleven_or_more_and_refuse_unknown_keys() -> None:
    assert intake_answers(None) == IntakeAnswers()
    assert intake_answers({"part_of_chain": True, "other_locations": "11_or_more"}).other_locations == 11
    with pytest.raises(ValidationError):
        intake_answers({"chain": True})
    with pytest.raises(ValidationError):
        intake_answers({"part_of_chain": True, "other_locations": "many"})


# ---- the local run script ----------------------------------------------------------------------------------------
def _load_script(name: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"validation_{name}_intake", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as env:
        for key in ("PRECEDENT_DATABASE_URL", "NEATLOGS_API_KEY", "LOCAL_DATABASE_URL"):
            env.setenv(key, os.environ.get(key, ""))
        env.delenv("LOCAL_DATABASE_URL")
        spec.loader.exec_module(module)
    return module


def test_the_local_run_script_takes_the_answers_as_a_file_or_inline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local = _load_script("run_report_local", monkeypatch)
    parser = local.build_parser()
    desc = "40-seat wine bar, small kitchen, open until 1am, occasional live music"
    assert parser.parse_args(["995 Valencia St", desc]).intake is None
    inline = parser.parse_args(
        ["995 Valencia St", desc, "--intake", '{"part_of_chain": false, "floor_area_sqft": 1800}']
    )
    assert inline.intake == IntakeAnswers(part_of_chain=False, floor_area_sqft=1800)
    answers = tmp_path / "answers.json"
    answers.write_text(
        json.dumps({"part_of_chain": True, "other_locations": "11_or_more", "liquor_licence": "none"})
    )
    from_file = parser.parse_args(["995 Valencia St", desc, "--intake", str(answers)])
    assert from_file.intake == IntakeAnswers(part_of_chain=True, other_locations=11, liquor_licence="none")
    # the fifth answer: a licence already held at this address
    held = parser.parse_args(["995 Valencia St", desc, "--intake", '{"liquor_licence": "already_held"}'])
    assert held.intake == IntakeAnswers(liquor_licence="already_held")
    for bad in ('{"liquor_licence": "maybe"}', "[1, 2]", str(tmp_path / "missing.json"), '{"seats": 4}'):
        with pytest.raises(SystemExit):
            parser.parse_args(["995 Valencia St", desc, "--intake", bad])
    # the answers reach the run; no model is called: the run itself is a stub
    seen: dict[str, Any] = {}

    async def generate(address: str, description: str, **kwargs: Any) -> int:
        seen.update(kwargs)
        return 0

    stub = ModuleType("app.scripts.memo_demo")
    stub.generate = generate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.scripts.memo_demo", stub)
    monkeypatch.setattr(local, "install_usage_meter", lambda: None)
    monkeypatch.setattr(
        settings, "PRECEDENT_DATABASE_URL", "postgresql://postgres@localhost:55433/sfhp_local"
    )
    monkeypatch.setattr(
        sys, "argv", ["run_report_local.py", "995 Valencia St", desc, "--intake", str(answers)]
    )
    assert local.main() == 0
    assert seen["intake_answers"] == IntakeAnswers(
        part_of_chain=True, other_locations=11, liquor_licence="none"
    )


def test_the_intake_model_cannot_set_facts_only_the_applicant_gives() -> None:
    """Five runs of 2026-11-11: the intake model read a wine bar as "not a chain" once, and "40 seats" as fewer than
    50 occupants three times. Those facts come only from the intake answers (or an operator override)."""
    from app.agents.runner import AgentRunner, RunInput
    from app.catalog.loader import get_catalog
    from app.models.profile import MODEL_MAY_NOT_SET, BusinessProfile

    schema = BusinessProfile.model_json_schema()["properties"]
    for key in MODEL_MAY_NOT_SET:
        assert key not in schema, key
    guessed = BusinessProfile(
        business_type="bar",
        city_slug="san_francisco",
        state="CA",
        serves_alcohol=True,
        alcohol_type="beer_wine",
        seats=40,
        formula_retail=False,
        occupants_under_50=True,
        alcohol_transaction="new_licence",
    )
    runner = AgentRunner.__new__(AgentRunner)
    runner.catalog = get_catalog()
    merged = runner._merge_profile(guessed, RunInput(description="40-seat wine bar"))
    assert (
        merged.formula_retail is None
        and merged.occupants_under_50 is None
        and merged.alcohol_transaction is None
    )
    overridden = runner._merge_profile(
        guessed, RunInput(description="40-seat wine bar", profile_overrides={"formula_retail": True})
    )
    assert overridden.formula_retail is True


# ---- the questions added on 2026-11-15: one for every input a row can name ----------------------------------------
def test_the_questions_are_in_two_groups_and_the_follow_ups_say_when_they_are_shown() -> None:
    from app.memo.intake import QUESTION_BY_ID

    main = [q.id for q in QUESTIONS if q.group == "main"]
    more = [q.id for q in QUESTIONS if q.group == "more"]
    assert main == [
        "part_of_chain",
        "other_locations",
        "floor_area_sqft",
        "liquor_licence",
        "stories",
        "alcohol_served",
        "closing_time",
        "last_use",
        "fewer_than_50_people",
        "outdoor_area",
        "outdoor_alcohol_service",
        "food_service",
    ]
    assert more == [
        "existing_business_change",
        "floor_area_before_sqft",
        "merges_storefronts",
        "amends_prior_approval",
        "entertainment",
        "existing_occupancy_group",
    ]
    assert QUESTION_BY_ID["alcohol_served"].shown_when == "liquor_licence!=none"
    assert QUESTION_BY_ID["outdoor_alcohol_service"].shown_when == "outdoor_area!=none"
    assert QUESTION_BY_ID["food_service"].shown_when == "liquor_licence=none"
    assert (QUESTION_BY_ID["stories"].kind, QUESTION_BY_ID["closing_time"].kind) == ("multi_choice", "time")
    # the words of each new question are its missing phrase, so the applicant recognises it in the report
    for question_id, fact in (
        ("stories", "stories"),
        ("alcohol_served", "alcohol_served"),
        ("closing_time", "closing"),
        ("last_use", "existing_use_stated"),
        ("fewer_than_50_people", "occupants_under_50"),
        ("outdoor_area", "outdoor_area"),
        ("existing_business_change", "changes_existing_business"),
        ("merges_storefronts", "merges_storefronts"),
        ("amends_prior_approval", "amends_prior_approval"),
        ("entertainment", "entertainment_kind"),
    ):
        q = QUESTION_BY_ID[question_id]
        assert q.fact == fact
        words = set(MISSING_PHRASES[fact].replace(":", "").replace(",", "").split())
        asked = set(q.question.lower().rstrip("?").replace(":", "").replace(",", "").split())
        # most of the phrase's words are in the question ("which stories the business occupies" /
        # "Which stories does the business occupy?")
        assert len(words & asked) >= len(words) - 3, (question_id, words - asked)


def test_the_web_page_groups_the_questions_as_the_api_does() -> None:
    if not WEB_INTAKE.is_file():
        pytest.skip("apps/web is not in this checkout")
    text = WEB_INTAKE.read_text(encoding="utf-8")
    block = text.split("export const MORE_QUESTION_IDS", 1)[1].split("];", 1)[0]
    listed = [line.strip().strip('",') for line in block.splitlines() if line.strip().startswith('"')]
    assert listed == [q.id for q in QUESTIONS if q.group == "more"]


@pytest.mark.parametrize(
    "bad",
    [
        {"stories": []},  # none ticked is a skipped question: the key is left out
        {"stories": ["attic"]},
        {"stories": ["first", "first"]},
        {"stories": "first"},
        {"alcohol_served": "none"},  # "No alcohol" is the liquor licence question's answer
        {"alcohol_served": "unknown"},
        {"closing_time": "2am"},
        {"closing_time": "24:00"},
        {"closing_time": "2:00"},
        {"closing_time": "02:60"},
        {"last_use": "vacant"},  # an empty space is asked what it was last used as
        {"last_use": "shop"},
        {"fewer_than_50_people": "yes"},
        {"fewer_than_50_people": 1},
        {"outdoor_area": "patio"},
        {"existing_business_change": "bigger"},
        {"floor_area_before_sqft": 0},
        {"floor_area_before_sqft": "1200"},
        {"merges_storefronts": "no"},
        {"amends_prior_approval": 0},
        {"entertainment": "dj"},
        {"existing_occupancy_group": "A-3"},
        {"existing_occupancy_group": "b"},
        # two answers that contradict each other
        {"liquor_licence": "none", "alcohol_served": "beer_wine"},
        {"liquor_licence": "none", "outdoor_alcohol_service": True},
        {"outdoor_area": "none", "outdoor_alcohol_service": False},
        {"outdoor_area": "none", "outdoor_alcohol_service": True},
    ],
)
def test_new_answers_outside_the_allowed_values_are_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        IntakeAnswers.model_validate(bad)


def test_answers_that_agree_are_accepted() -> None:
    IntakeAnswers.model_validate({"liquor_licence": "none", "outdoor_alcohol_service": False})
    IntakeAnswers.model_validate({"liquor_licence": "new", "alcohol_served": "full_liquor"})
    IntakeAnswers.model_validate({"outdoor_area": "front", "outdoor_alcohol_service": True})
    IntakeAnswers.model_validate({"outdoor_alcohol_service": True})  # the description says where the patio is


def test_the_stories_are_stored_in_the_fixed_order_each_once() -> None:
    answers = IntakeAnswers.model_validate({"stories": ["third_or_above", "basement", "first"]})
    assert answers.stories == ["first", "third_or_above", "basement"]  # the order of `Story`
    out = apply_intake_answers(cafe(stories=["second"]), answers)
    assert out.stories == ["first", "third_or_above", "basement"]  # the answer wins over the description
    assert concept_facts(out).stories.value == ("first", "third_or_above", "basement")
    assert not concept_facts(out).story_missing


def test_what_is_poured_decides_the_licence_type() -> None:
    restaurant = BusinessProfile.model_validate({"business_type": "restaurant"})
    for pours, licence in (("beer_wine", "41"), ("full_liquor", "47")):
        out = apply_intake_answers(restaurant, IntakeAnswers.model_validate({"alcohol_served": pours}))
        assert (out.serves_alcohol, out.alcohol_type) == (True, pours)
        facts = concept_facts(out)
        assert (
            facts.alcohol_served.stated and facts.licence_type.value == licence and facts.licence_type.derived
        )
        assert "alcohol" in required_areas(out)
    # with the licence question too, the alcohol row has both of its inputs
    both = IntakeAnswers.model_validate({"liquor_licence": "new", "alcohol_served": "beer_wine"})
    out = apply_intake_answers(bar(alcohol_type="unknown"), both)
    assert concept_facts(out).missing(["licence_type", "alcohol_transaction"]) == ()
    # the answer wins over what the description said was poured
    out = apply_intake_answers(bar(alcohol_type="beer_wine"), IntakeAnswers(alcohol_served="full_liquor"))
    assert out.alcohol_type == "full_liquor" and concept_facts(out).licence_type.value == "48"


@pytest.mark.parametrize(
    ("time", "after_midnight", "after_2am", "bucket"),
    [
        ("22:00", False, False, "by_midnight"),
        ("00:00", False, False, "by_midnight"),
        ("00:30", True, False, "after_midnight"),
        ("02:00", True, False, "after_midnight"),
        ("02:01", True, True, "after_2am"),
        ("04:00", True, True, "after_2am"),
        ("06:00", True, True, "after_2am"),
        ("07:00", False, False, "by_midnight"),  # a morning close of a daytime business
    ],
)
def test_the_closing_time_sets_the_hour_and_the_two_late_flags(
    time: str, after_midnight: bool, after_2am: bool, bucket: str
) -> None:
    out = apply_intake_answers(
        bar(closing_hour="23:00", closes_after_midnight=True), IntakeAnswers(closing_time=time)
    )
    assert (out.closing_hour, out.closes_after_midnight, out.closes_after_2am) == (
        time,
        after_midnight,
        after_2am,
    )
    closing = concept_facts(out).closing
    assert closing.stated and closing.bucket == bucket
    # the same flags a hand-entered closing hour gets
    by_hand = profile_from_facts({"business_type": "bar", "closing_hour": time})
    assert (by_hand.closes_after_midnight, by_hand.closes_after_2am) == (after_midnight, after_2am)


def test_the_last_use_the_people_and_the_occupancy_group() -> None:
    answers = IntakeAnswers.model_validate(
        {"last_use": "laundromat", "fewer_than_50_people": False, "existing_occupancy_group": "A-2"}
    )
    out = apply_intake_answers(cafe(existing_use_stated=["retail"], occupants_under_50=True), answers)
    assert out.existing_use_stated == ["laundromat"]
    assert out.occupants_under_50 is False and out.existing_occupancy_group == "A-2"
    facts = concept_facts(out)
    assert facts.existing_use_stated.value == ("laundromat",) and facts.occupants_under_50.value is False
    assert facts.missing(["existing_use_stated", "occupants_under_50"]) == ()


def test_the_outdoor_area() -> None:
    there = apply_intake_answers(
        cafe(), IntakeAnswers(outdoor_area="rear_or_side", outdoor_alcohol_service=False)
    )
    assert (there.outdoor_area, there.outdoor_seating, there.sidewalk_or_parklet) == (
        "rear_or_side",
        True,
        False,
    )
    assert there.outdoor_alcohol_service is False and "outdoor" in required_areas(there)
    sidewalk = apply_intake_answers(cafe(), IntakeAnswers(outdoor_area="sidewalk"))
    assert (sidewalk.outdoor_seating, sidewalk.sidewalk_or_parklet) == (True, True)
    # "No outdoor area" wins over a description that mentioned one: no outdoor row
    none = apply_intake_answers(
        cafe(outdoor_seating=True, sidewalk_or_parklet=True, outdoor_area="sidewalk"),
        IntakeAnswers(outdoor_area="none"),
    )
    assert (none.outdoor_area, none.outdoor_seating, none.sidewalk_or_parklet) == ("none", False, False)
    assert "outdoor" not in required_areas(none)
    assert not concept_facts(none).outdoor_area_described


def test_the_answers_under_more_details() -> None:
    answers = IntakeAnswers.model_validate(
        {
            "existing_business_change": "enlarge",
            "floor_area_before_sqft": 1200,
            "merges_storefronts": True,
            "amends_prior_approval": False,
            "entertainment": "limited_live_performance",
        }
    )
    out = apply_intake_answers(bar(), answers)
    assert out.changes_existing_business == "enlarge" and out.floor_area_before_sqft == 1200
    assert (out.merges_storefronts, out.amends_prior_approval) == (True, False)
    assert out.entertainment_kind == "limited_live_performance"
    facts = concept_facts(out)
    for name in (
        "changes_existing_business",
        "floor_area_before_sqft",
        "merges_storefronts",
        "amends_prior_approval",
        "entertainment_kind",
    ):
        assert facts.source_of(name) == "stated", name
    assert "entertainment" in required_areas(out)
    # "No entertainment" wins over a description that mentioned some
    quiet = apply_intake_answers(
        bar(live_entertainment=True, amplified_sound=True, dancing=True), IntakeAnswers(entertainment="none")
    )
    assert quiet.entertainment_kind == "none"
    assert (quiet.live_entertainment, quiet.amplified_sound, quiet.dancing) == (False, False, False)


def test_a_skipped_new_question_changes_nothing() -> None:
    before = bar(
        stories=["first"],
        closing_hour="01:00",
        closes_after_midnight=True,
        existing_use_stated=["retail"],
        outdoor_area="front",
        outdoor_seating=True,
        entertainment_kind="none",
    )
    after = apply_intake_answers(before, IntakeAnswers(floor_area_sqft=900))
    assert after == before.model_copy(update={"square_feet": 900, "intake_answered": ["square_feet"]})


def test_the_fields_each_new_answer_gives() -> None:
    from app.memo.intake import answered_fields

    one = {
        "stories": (["first"], {"stories"}),
        "alcohol_served": ("beer_wine", {"serves_alcohol", "alcohol_type"}),
        "closing_time": ("01:00", {"closing_hour", "closes_after_midnight", "closes_after_2am"}),
        "last_use": ("retail", {"existing_use_stated"}),
        "fewer_than_50_people": (True, {"occupants_under_50"}),
        "outdoor_area": ("front", {"outdoor_area", "outdoor_seating", "sidewalk_or_parklet"}),
        "outdoor_alcohol_service": (False, {"outdoor_alcohol_service"}),
        "existing_business_change": ("none", {"changes_existing_business"}),
        "floor_area_before_sqft": (900, {"floor_area_before_sqft"}),
        "merges_storefronts": (False, {"merges_storefronts"}),
        "amends_prior_approval": (False, {"amends_prior_approval"}),
        "entertainment": ("limited_live_performance", {"entertainment_kind"}),
        "existing_occupancy_group": ("B", {"existing_occupancy_group"}),
        "food_service": ("limited_restaurant", {"food_service"}),
    }
    for question, (value, fields) in one.items():
        answers = IntakeAnswers.model_validate({question: value})
        assert answered_fields(answers) == fields, question
        assert answers.answered() == (question,)
        # every field an answer gives is a profile field, and the answer sets it
        out = apply_intake_answers(cafe(), answers)
        assert fields <= set(BusinessProfile.model_fields)
        assert out != cafe(), question
    assert answered_fields(IntakeAnswers(entertainment="none")) == {
        "entertainment_kind",
        "live_entertainment",
        "amplified_sound",
        "dancing",
    }
    assert set(one) | {"part_of_chain", "other_locations", "floor_area_sqft", "liquor_licence"} == set(
        IntakeAnswers.model_fields
    )


def test_the_intake_model_cannot_give_the_existing_occupancy_group() -> None:
    from app.agents.memo_runner import SUBMIT_MEMO_INTAKE
    from app.models.profile import MODEL_MAY_NOT_SET

    assert "existing_occupancy_group" in MODEL_MAY_NOT_SET and "occupants_under_50" in MODEL_MAY_NOT_SET
    shown = json.dumps(SUBMIT_MEMO_INTAKE.to_anthropic()["input_schema"])
    assert '"existing_occupancy_group"' not in shown and '"occupants_under_50"' not in shown


# ---- review of 2026-11-15 ------------------------------------------------------------------------------------
def test_no_outdoor_area_means_no_alcohol_served_in_one() -> None:
    """Review #10: "No outdoor area" sets alcohol in the outdoor area to false, as "No alcohol" does, and the
    answer gives it (so a value the check cleared is no longer left open)."""
    from app.memo.intake import answered_fields

    stated = cafe(outdoor_seating=True, outdoor_area="front", outdoor_alcohol_service=True)
    out = apply_intake_answers(stated, IntakeAnswers(outdoor_area="none"))
    assert out.outdoor_alcohol_service is False
    assert "outdoor_alcohol_service" in answered_fields(IntakeAnswers(outdoor_area="none"))
    assert "outdoor_alcohol_service" not in answered_fields(IntakeAnswers(outdoor_area="front"))


def test_alcohol_served_outdoors_means_the_business_serves_alcohol() -> None:
    """Review #11: the answer "yes" sets serves_alcohol and gives it; "no" says nothing about alcohol inside. The
    flag for the alcohol row's line is set only where this is the one alcohol answer and the description did not
    say alcohol is served."""
    from app.memo.intake import answered_fields

    yes = IntakeAnswers(outdoor_area="front", outdoor_alcohol_service=True)
    out = apply_intake_answers(cafe(), yes)
    assert out.serves_alcohol is True and "alcohol" in required_areas(out.normalized())
    assert out.outdoor_alcohol_answer_over_description is True
    assert "serves_alcohol" in answered_fields(yes)
    no = IntakeAnswers(outdoor_area="front", outdoor_alcohol_service=False)
    assert apply_intake_answers(cafe(), no).serves_alcohol is False
    assert "serves_alcohol" not in answered_fields(no)
    # the description serves alcohol, or another answer says so: no disagreement to name
    assert not apply_intake_answers(bar(), yes).outdoor_alcohol_answer_over_description
    with_licence = IntakeAnswers(outdoor_area="front", outdoor_alcohol_service=True, liquor_licence="new")
    assert not apply_intake_answers(cafe(), with_licence).outdoor_alcohol_answer_over_description


def test_the_profile_records_which_fields_an_answer_set() -> None:
    """Reviews #15 and #21: the rules can tell a fact an answer gave from one the description gave, so a line
    says "You answered ..." for the first. The intake model cannot set the record."""
    from app.memo.intake import answered_fields
    from app.models.profile import MODEL_MAY_NOT_SET

    answers = IntakeAnswers(last_use="retail", fewer_than_50_people=True)
    out = apply_intake_answers(cafe(), answers)
    assert (
        out.intake_answered
        == sorted(answered_fields(answers))
        == ["existing_use_stated", "occupants_under_50"]
    )
    assert concept_facts(out).by_answer("occupants_under_50")
    assert not concept_facts(cafe(existing_use_stated=["retail"])).by_answer("existing_use_stated")
    assert "intake_answered" in MODEL_MAY_NOT_SET
    assert "outdoor_alcohol_answer_over_description" in MODEL_MAY_NOT_SET
    shown = json.dumps(BusinessProfile.model_json_schema())
    assert '"intake_answered"' not in shown and '"outdoor_alcohol_answer_over_description"' not in shown
