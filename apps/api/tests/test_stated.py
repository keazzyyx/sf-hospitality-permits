"""The stated-facts check (app.memo.stated): the intake model may only record facts the user's text states.

User decision of 2026-11-12: anything the model would infer becomes unknown and is named in the report. Tested here:
the quote check (kept, cleared, normalisation), D22's text (a mezzanine never becomes a second story; ground-floor
gives the first story), and that every cleared field is named as a missing input the scorer can map. No database,
no network, no model.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, get_args

import pytest

from app.agents.memo_runner import required_areas
from app.backtest.score import phrase_key
from app.memo import tracts
from app.memo.facts import MISSING_PHRASES, concept_facts, profile_from_facts
from app.memo.intake import IntakeAnswers, apply_intake_answers
from app.memo.pathway import NOT_STATED_QUESTION, determine
from app.memo.report import site_records
from app.memo.stated import (
    FACT_OF_FIELD,
    QUOTE_GROUPS,
    UNSET,
    VALUE_WORDS,
    StatedCheck,
    check_stated,
    cleared_fact_names,
    normalise,
    quote_found,
    record_cleared,
    stated_text,
    times_in,
    value_stated,
)
from app.models.memo import Determinations
from app.models.profile import (
    MODEL_MAY_NOT_SET,
    QUOTED_FIELDS,
    BusinessProfile,
    FactQuote,
    IntakeResult,
    MemoIntakeResult,
    QuotedField,
    Story,
)
from tests.test_pathway_cases import CASES, RULES_DATE, licence_rows, site_of_case, store_lookup

REPO = Path(__file__).resolve().parents[3]
INPUTS = REPO / "backtest" / "inputs.json"
D22_RESULT = REPO / "backtest" / "results" / "D22" / "e2e" / "profile.json"


# INTAKE as it was before the memo's stated-facts check (commit ef93f7a): the checklist (/v1/plans) keeps it.
CHECKLIST_INTAKE_SHA256 = "46f83c74e07dcf633f5df380d029ca25d384b8dfc15aaa82ca30fe8386ed9234"


def q(field: str, quote: str) -> FactQuote:
    return FactQuote.model_validate({"field": field, "quote": quote})


def check(profile: dict[str, Any], quotes: list[FactQuote], text: str) -> StatedCheck:
    return check_stated(BusinessProfile.model_validate({"business_type": "other", **profile}), quotes, text)


def d22() -> dict[str, Any]:
    case: dict[str, Any] = json.loads(INPUTS.read_text())["cases"]["D22"]
    return case


# ---- the tables -------------------------------------------------------------------------------------------------
def test_the_tables_cover_every_quoted_field() -> None:
    assert tuple(get_args(QuotedField)) == QUOTED_FIELDS
    assert set(UNSET) == set(QUOTED_FIELDS) == set(FACT_OF_FIELD)
    for field in QUOTED_FIELDS:
        assert field in BusinessProfile.model_fields, field
        # the "not stated" value is the field's own default, so a cleared field reads as an untouched one
        assert UNSET[field] == BusinessProfile.model_fields[field].get_default(call_default_factory=True) or (
            field == "business_type" and UNSET[field] == "other"
        ), field
        assert field not in MODEL_MAY_NOT_SET, field
    assert set(QUOTE_GROUPS) <= set(QUOTED_FIELDS)
    assert all(set(group) <= set(QUOTED_FIELDS) for group in QUOTE_GROUPS.values())
    # every fact a cleared field leaves not known has a fixed phrase, and the scorer maps the phrase back to it
    for fact in FACT_OF_FIELD.values():
        assert phrase_key(MISSING_PHRASES[fact]) == fact, fact


def test_the_memo_model_is_asked_for_quotes_and_cannot_set_the_record_of_what_was_cleared() -> None:
    from app.agents.memo_runner import SUBMIT_MEMO_INTAKE, MemoRunner
    from app.agents.prompts import MEMO_INTAKE

    schema = json.dumps(SUBMIT_MEMO_INTAKE.to_anthropic()["input_schema"])
    assert '"quotes"' in schema and '"intake_cleared"' not in schema
    assert (MemoRunner.intake_prompt, MemoRunner.intake_submit) == (MEMO_INTAKE, SUBMIT_MEMO_INTAKE)
    assert "intake_cleared" in MODEL_MAY_NOT_SET
    for field in QUOTED_FIELDS:
        assert field in MEMO_INTAKE, field
    # the checklist's defaults that fill a rule-read field with a likely value are not in the memo's prompt
    assert "everything else with a kitchen" not in MEMO_INTAKE
    assert '"Maybe live music" → live_entertainment true' not in MEMO_INTAKE
    assert "can assume (seats" not in MEMO_INTAKE
    assert '"Maybe live music" is not a statement' in MEMO_INTAKE
    # a result without quotes still validates (and then every value it set is cleared)
    assert (
        MemoIntakeResult.model_validate(
            {"profile": {"business_type": "bar"}, "needs_clarification": False, "reasoning_summary": "A bar."}
        ).quotes
        == []
    )


def test_the_checklist_intake_is_unchanged() -> None:
    """/v1/plans runs no stated-facts check, so its intake keeps its prompt and its tool: no quotes rule, no quotes
    field (the prompt is byte for byte the one before the memo's check was added)."""
    from app.agents.prompts import INTAKE
    from app.agents.runner import SUBMIT_INTAKE, AgentRunner

    assert (AgentRunner.intake_prompt, AgentRunner.intake_submit) == (INTAKE, SUBMIT_INTAKE)
    schema = SUBMIT_INTAKE.to_anthropic()["input_schema"]
    assert "quotes" not in schema["properties"] and "intake_cleared" not in json.dumps(schema)
    assert "quotes" not in IntakeResult.model_fields
    assert "Quotes (`quotes`)" not in INTAKE and "everything else with a kitchen" in INTAKE
    assert hashlib.sha256(INTAKE.encode()).hexdigest() == CHECKLIST_INTAKE_SHA256


# ---- normalisation and finding a quote -------------------------------------------------------------------------
def test_normalise() -> None:
    assert normalise("Two GROUND-FLOOR units, 3,953 sq. ft.") == "two ground floor units 3953 sq ft"
    assert normalise("Café “Rosa’s”") == "cafe rosa s"
    assert normalise("  open\nuntil   1:30 a.m.") == "open until 1 30 a m"


@pytest.mark.parametrize(
    ("quote", "found"),
    [
        ("two ground-floor commercial units", True),
        ("Two Ground Floor Commercial Units", True),  # case and punctuation do not matter
        ("about 3953 square feet", True),  # a thousands comma does not matter
        ("ground-floor ... a mezzanine", True),  # each part of an elided quote is in the text
        ("ground-floor ... a basement", False),  # one part is not
        ("a second-story dining room", False),  # not in the text
        ("ground-flo", False),  # not on a word boundary
        ("a", False),  # too short to state anything
        ("", False),
    ],
)
def test_a_quote_counts_only_when_it_is_in_the_text(quote: str, found: bool) -> None:
    text = "Two ground-floor commercial units of about 3,953 square feet, one with a mezzanine."
    assert quote_found(quote, text) is found


def test_times_in_a_quote() -> None:
    assert times_in("open until 1am") == {60}
    assert times_in("from 11:00 am to 2:00 am") == {660, 120}
    assert times_in("until 1:30 a.m.") == {90}
    assert times_in("closes at midnight") == {0}
    assert times_in("closing 11pm") == {23 * 60}
    assert times_in("vacant since 2017, 40 seats, 3 units") == set()  # numbers that are not times


# ---- kept and cleared -----------------------------------------------------------------------------------------
TEXT = "A 40-seat wine bar on the ground floor, open until 1:30 am, with live music."


def test_a_value_its_quote_states_is_kept() -> None:
    profile = {
        "business_type": "bar",
        "serves_alcohol": True,
        "alcohol_type": "beer_wine",
        "seats": 40,
        "stories": ["first"],
        "closing_hour": "01:30",
        "closes_after_midnight": True,
        "live_entertainment": True,
    }
    quotes = [
        q("business_type", "wine bar"),
        q("alcohol_type", "wine bar"),  # also states that alcohol is served (pooled with serves_alcohol)
        q("seats", "40-seat"),
        q("stories", "on the ground floor"),
        q("closing_hour", "open until 1:30 am"),  # also states the close after midnight (pooled)
        q("live_entertainment", "with live music"),
    ]
    result = check(profile, quotes, TEXT)
    assert result.cleared == {}
    assert result.profile == BusinessProfile.model_validate(profile)


def test_a_value_without_a_quote_or_with_a_quote_not_in_the_text_is_cleared() -> None:
    profile = {"business_type": "bar", "seats": 40, "closing_hour": "01:30", "square_feet": 1400}
    quotes = [
        q("business_type", "wine bar"),
        q("seats", "a 40-seat room"),  # not in the text
        q("square_feet", "1,400 square feet"),  # not in the text
    ]  # no quote at all for the closing time
    result = check(profile, quotes, TEXT)
    assert result.cleared == {"seats": 40, "closing_hour": "01:30", "square_feet": 1400}
    assert (result.profile.seats, result.profile.closing_hour, result.profile.square_feet) == (
        None,
        None,
        None,
    )
    assert result.profile.business_type == "bar"


@pytest.mark.parametrize(
    ("field", "value", "quote"),
    [
        ("closing_hour", "02:00", "open until 1:30 am"),  # a closing time the quote does not give
        ("seats", 60, "40-seat"),  # another number
        ("square_feet", 40, "40-seat"),  # the number, but not a floor area
        ("alcohol_type", "full_liquor", "wine bar"),  # a wine bar does not state spirits
        ("amplified_sound", True, "with live music"),  # live music does not state amplified sound
        ("closes_after_2am", True, "open until 1:30 am"),  # 1:30 am is not after 2 am
        ("business_type", "restaurant", "wine bar"),
    ],
)
def test_a_quote_that_does_not_state_the_value_clears_it(field: str, value: Any, quote: str) -> None:
    result = check(
        {"business_type": "bar", field: value}, [q(field, quote), q("business_type", "wine bar")], TEXT
    )
    assert result.cleared == {field: value}
    assert getattr(result.profile, field) == UNSET[field] or (field == "business_type")


def test_a_restaurant_does_not_state_that_it_serves_alcohol() -> None:
    text = "Rosa's Taqueria, a family restaurant."
    result = check(
        {"business_type": "restaurant", "serves_alcohol": True, "alcohol_type": "beer_wine"},
        [q("business_type", "Rosa's Taqueria"), q("serves_alcohol", "a family restaurant")],
        text,
    )
    assert result.cleared == {"serves_alcohol": True, "alcohol_type": "beer_wine"}
    assert (result.profile.serves_alcohol, result.profile.alcohol_type) == (False, "none")
    assert result.profile.business_type == "restaurant"


def test_no_closing_hour_is_assumed() -> None:
    text = "A neighbourhood bar, open late."
    result = check(
        {"business_type": "bar", "closing_hour": "02:00", "closes_after_midnight": True},
        [q("closing_hour", "open late"), q("closes_after_midnight", "open late"), q("business_type", "bar")],
        text,
    )
    assert result.cleared == {"closing_hour": "02:00", "closes_after_midnight": True}


def test_a_no_needs_a_negation() -> None:
    text = "We will merge the two storefronts. There will be no entertainment."
    kept = check(
        {"merges_storefronts": True, "entertainment_kind": "none"},
        [q("merges_storefronts", "merge the two storefronts"), q("entertainment_kind", "no entertainment")],
        text,
    )
    assert kept.cleared == {}
    cleared = check(
        {"merges_storefronts": False}, [q("merges_storefronts", "merge the two storefronts")], text
    )
    assert cleared.cleared == {"merges_storefronts": False}


def test_from_a_list_only_the_values_no_quote_states_are_removed() -> None:
    text = "Taking over the old laundromat, empty for years."
    result = check(
        {"existing_use_stated": ["laundromat", "vacant", "retail"]},
        [q("existing_use_stated", "the old laundromat"), q("existing_use_stated", "empty for years")],
        text,
    )
    assert result.profile.existing_use_stated == ["laundromat", "vacant"]
    assert result.cleared == {"existing_use_stated": ["retail"]}


def test_quotes_may_come_from_a_written_clarification_answer() -> None:
    text = stated_text("A wine bar.", ["We close at 11pm", True, 40, None])
    assert text == "A wine bar.\nWe close at 11pm"
    result = check({"closing_hour": "23:00"}, [q("closing_hour", "close at 11pm")], text)
    assert result.cleared == {}


def test_every_hand_entered_fact_of_the_backtest_texts_can_be_quoted() -> None:
    """The words tables against the 40 neutral texts: with every sentence of the text offered as a quote, every
    fact the two readers coded from it is kept. The one exception is D03's floor area, which the readers added up
    (1,100 + 1,200 square feet): the text never gives 2,300, so the check clears it (the intake answer gives the
    floor area in that case)."""
    cleared: dict[str, dict[str, Any]] = {}
    for cid, case in json.loads(INPUTS.read_text())["cases"].items():
        text = case["concept_input"]
        sentences = [s.strip() for s in text.replace(";", ".").split(". ") if len(s.strip()) > 3]
        quotes = [q(field, s[:300]) for field in QUOTED_FIELDS for s in sentences]
        result = check_stated(profile_from_facts(case["input_facts"]), quotes, text)
        if result.cleared:
            cleared[cid] = result.cleared
    assert cleared == {"D03": {"square_feet": 2300}}


# ---- D22: a mezzanine is not a second story ---------------------------------------------------------------------
def test_a_mezzanine_never_states_a_story() -> None:
    for story in get_args(Story):
        assert not value_stated("stories", story, ["one of about 3,095 square feet with a mezzanine"]), story
        assert not value_stated("stories", story, ["a mezzanine"]), story
    assert value_stated("stories", "first", ["two ground-floor commercial units"])
    assert value_stated("stories", "first", ["on the first and second stories"])
    assert value_stated("stories", "second", ["on the first and second stories"])
    assert value_stated("stories", "basement", ["a 1,200-square-foot basement"])


def test_upstairs_or_an_upper_floor_never_states_a_story() -> None:
    # review of 2026-11-12: an upper floor may be the second story or the third and above, where several district
    # tables differ; only a numbered story states it, as with "top floor"
    for words in (
        "upstairs",
        "a wine bar on the upper floor",
        "the upper level",
        "an upper story",
        "top floor",
    ):
        for story in get_args(Story):
            assert not value_stated("stories", story, [words]), (words, story)
    assert value_stated("stories", "second", ["on the second floor"])
    assert value_stated("stories", "second", ["a 2nd-floor bar"])
    assert value_stated("stories", "third_or_above", ["on the third floor"])


def test_d22_the_mezzanine_is_dropped_and_ground_floor_gives_the_first_story() -> None:
    case = d22()
    text = case["concept_input"]
    # the intake model's profile of the 40-case backtest (stories first and second, 120 seats, a change of use)
    recorded = json.loads(D22_RESULT.read_text())
    model = BusinessProfile.model_validate(
        {k: v for k, v in recorded.items() if k in BusinessProfile.model_fields}
    )
    assert model.stories == ["first", "second"]
    quotes = [
        q("business_type", "Honey Cove Restaurant"),
        q("stories", "two ground-floor commercial units"),
        q("stories", "one of about 3,095 square feet with a mezzanine"),
        q("square_feet", "about 3,953 square feet"),
        q("merges_storefronts", "merged into one"),
        q("existing_use_stated", "Both units are vacant"),
        q("change_of_use", "vacant and have been since 2017"),
        q("seats", "about 3,953 square feet"),
    ]
    result = check_stated(model, quotes, text)
    assert result.profile.stories == ["first"]  # what the readers coded: "story": "first"
    assert case["input_facts"]["story"] == "first"
    assert result.cleared == {"seats": 120, "stories": ["second"], "change_of_use": True}
    assert (result.profile.business_type, result.profile.square_feet) == ("restaurant", 3953)
    assert result.profile.merges_storefronts is True and result.profile.existing_use_stated == ["vacant"]
    # a model that quotes only the mezzanine for the stories states none: the stories are not known
    only = check_stated(model, [q("stories", "with a mezzanine")], text)
    assert only.profile.stories == [] and only.cleared["stories"] == ["first", "second"]


def _determine(case_id: str, profile: BusinessProfile, data_dir: Path) -> Determinations:
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


def test_d22_style_profile_on_mission_street_is_not_a_false_blocker(tmp_path: Path) -> None:
    """The pathway case on Mission Street (NCT-MISSION, D22's district): a Restaurant on a second story is not
    permitted there. The model's unchecked D22 reading (first and second story) makes zoning "Not permitted"; the
    checked one (first story only) does not."""
    text = d22()["concept_input"]
    model = BusinessProfile(
        business_type="restaurant", stories=["first", "second"], seats=120, square_feet=3953
    )
    quotes = [q("business_type", "Honey Cove Restaurant"), q("stories", "ground-floor"),
              q("stories", "with a mezzanine"), q("square_feet", "3,953 square feet")]  # fmt: skip
    unchecked = _determine("mission-st-restaurant", model, tmp_path / "a")
    checked = check_stated(model, quotes, text)
    final = record_cleared(checked.profile, checked)
    after = _determine("mission-st-restaurant", final, tmp_path / "b")
    zoning_before = next(r for r in unchecked.rows if r.area == "zoning_use")
    zoning_after = next(r for r in after.rows if r.area == "zoning_use")
    assert zoning_before.status == "not_permitted"
    assert zoning_after.status != "not_permitted"
    assert all(r.status != "not_permitted" for r in after.rows)
    assert final.stories == ["first"] and final.intake_cleared == {"stories": ["second"], "seats": 120}
    # "ground-floor" states the first story: it is read as stated (a Conditional Use on the first story, and the
    # district's cap on eating and drinking uses), and the story is not named as missing
    t1 = next(t for t in after.pathway.triggers if t.rule_id == "T1")
    assert [line.rule_id for line in t1.lines] == ["T1.cell", "T1.cap", "T1.historic"]
    assert MISSING_PHRASES["stories"] not in t1.missing_inputs
    assert any("on the first story is a conditional use" in line.text for line in t1.lines)
    assert zoning_after.status == "further_review"
    assert MISSING_PHRASES["stories"] not in zoning_after.missing_inputs


# ---- cleared fields are named ------------------------------------------------------------------------------------
def test_every_cleared_field_is_named_as_a_missing_input(tmp_path: Path) -> None:
    """At 995 Valencia St: a model that filled the closing time, the seats, the stories, the floor area, live
    music and amplified sound without the text stating them. Each fact is named in the report: by the row or
    trigger that needs it, else in its own open question; every phrase is one the scorer maps."""
    text = "A wine bar on Valencia Street."
    model = BusinessProfile(
        business_type="bar", serves_alcohol=True, alcohol_type="beer_wine", seats=40, square_feet=1400,
        stories=["first"], closing_hour="02:00", closes_after_midnight=True, live_entertainment=True,
        amplified_sound=True,
    )  # fmt: skip
    quotes = [
        q("business_type", "A wine bar"),
        q("alcohol_type", "wine bar"),
        q("stories", "on Valencia Street"),
    ]
    checked = check_stated(model, quotes, text)
    final = record_cleared(checked.profile.normalized(), checked)
    assert set(final.intake_cleared) == {
        "seats", "square_feet", "stories", "closing_hour", "closes_after_midnight", "live_entertainment",
        "amplified_sound",
    }  # fmt: skip
    facts = concept_facts(final)
    assert facts.cleared_facts == ("floor_area_sqft", "stories", "closing", "entertainment_kind", "seats")
    d = _determine("valencia-wine-bar", final, tmp_path)
    named = {p for r in d.rows for p in r.missing_inputs} | {
        p for t in d.pathway.triggers for p in t.missing_inputs
    }
    asked = " ".join(qu.question for qu in d.open_questions)
    for fact in facts.cleared_facts:
        phrase = MISSING_PHRASES[fact]
        assert phrase in named or NOT_STATED_QUESTION.format(phrase=phrase) in asked, fact
        assert phrase_key(phrase) == fact
    # the zoning row needs the floor area here, so it is named there (a row's missing input), not twice
    assert MISSING_PHRASES["floor_area_sqft"] in named
    assert NOT_STATED_QUESTION.format(phrase=MISSING_PHRASES["floor_area_sqft"]) not in asked
    # facts no rule here reads are asked on their own
    assert NOT_STATED_QUESTION.format(phrase=MISSING_PHRASES["seats"]) in asked


def test_a_fact_an_answer_gives_later_is_not_named() -> None:
    text = "A wine bar."
    model = BusinessProfile(
        business_type="bar", serves_alcohol=True, alcohol_type="beer_wine", square_feet=1400
    )
    checked = check_stated(model, [q("business_type", "A wine bar"), q("alcohol_type", "wine bar")], text)
    assert checked.cleared == {"square_feet": 1400}
    answered = apply_intake_answers(checked.profile, IntakeAnswers(floor_area_sqft=1800))
    final = record_cleared(answered, checked)
    assert final.intake_cleared == {} and final.square_feet == 1800
    assert concept_facts(final).cleared_facts == ()
    skipped = record_cleared(apply_intake_answers(checked.profile, IntakeAnswers()), checked)
    assert skipped.intake_cleared == {"square_feet": 1400}
    assert concept_facts(skipped).cleared_facts == ("floor_area_sqft",)


def test_a_cleared_field_whose_fact_another_field_states_is_not_named() -> None:
    # the closing time is stated; only the "after 2 a.m." flag was a guess
    text = "A bar open from 11:00 am to 2:00 am."
    model = BusinessProfile(
        business_type="bar", closing_hour="02:00", closes_after_midnight=True, closes_after_2am=True
    )
    checked = check_stated(model, [q("business_type", "A bar"), q("closing_hour", "to 2:00 am")], text)
    assert checked.cleared == {"closes_after_2am": True}
    final = record_cleared(checked.profile, checked)
    assert cleared_fact_names(final.intake_cleared) == ("closing",)
    assert concept_facts(final).cleared_facts == ()  # the closing time is stated


def test_the_words_tables_hold_only_patterns_that_compile() -> None:
    import re

    for field, values in VALUE_WORDS.items():
        for value, pattern in values.items():
            re.compile(pattern)
            assert field in QUOTED_FIELDS, (field, value)


# ---- review fixes (2026-11-12) ----------------------------------------------------------------------------------
def _row(d: Determinations, area: str) -> Any:
    return next((r for r in d.rows if r.area == area), None)


def test_a_cleared_yes_is_not_known_and_its_row_is_insufficient_information(tmp_path: Path) -> None:
    """A cafe whose model profile said it serves beer and wine and has live music, with no quote for either. The
    cleared "yes" is not read as "no": the alcohol and entertainment rows are added, each is insufficient
    information and names its fact, and the zoning triggers that read them are not decided."""
    model = BusinessProfile(
        business_type="cafe", serves_alcohol=True, alcohol_type="beer_wine", live_entertainment=True,
        square_feet=900, formula_retail=False,
    )  # fmt: skip
    checked = check_stated(model, [q("business_type", "A cafe")], "A cafe on Valencia Street.")
    final = record_cleared(checked.profile, checked)
    assert (final.serves_alcohol, final.live_entertainment) == (False, False)
    facts = concept_facts(final)
    assert facts.alcohol_not_stated and facts.entertainment_not_stated
    assert facts.alcohol_served.missing
    assert {"alcohol", "entertainment"} <= set(required_areas(final))
    d = _determine("valencia-wine-bar", final, tmp_path)
    alcohol, entertainment = _row(d, "alcohol"), _row(d, "entertainment")
    assert alcohol.status == "insufficient_information"
    assert MISSING_PHRASES["alcohol_served"] in alcohol.missing_inputs
    assert entertainment.status == "insufficient_information"
    assert entertainment.missing_inputs == [MISSING_PHRASES["entertainment_kind"]]
    zoning = _row(d, "zoning_use")
    assert zoning.status == "insufficient_information"
    assert MISSING_PHRASES["entertainment_kind"] in zoning.missing_inputs
    lines = " ".join(line.text for t in d.pathway.triggers for line in t.lines)
    assert "not described as serving alcohol" not in lines and "No entertainment is described" not in lines
    # each is named by its row, so not asked a second time on its own
    asked = [qu.question for qu in d.open_questions]
    assert not any(NOT_STATED_QUESTION.format(phrase=MISSING_PHRASES["alcohol_served"]) in a for a in asked)


def test_a_cleared_outdoor_area_makes_the_outdoor_row_insufficient_information(tmp_path: Path) -> None:
    model = BusinessProfile(business_type="restaurant", outdoor_seating=True, square_feet=900)
    checked = check_stated(model, [q("business_type", "A restaurant")], "A restaurant.")
    final = record_cleared(checked.profile, checked)
    assert "outdoor" in required_areas(final)
    outdoor = _row(_determine("valencia-wine-bar", final, tmp_path), "outdoor")
    assert outdoor.status == "insufficient_information"
    assert outdoor.missing_inputs == [MISSING_PHRASES["outdoor_area"]]


def test_a_cleared_story_is_not_decided_not_read_as_the_first(tmp_path: Path) -> None:
    """A model that quoted only "with a mezzanine" for a second story: the story is not stated. No story is
    assumed (the user's decision of 2026-11-12: "MISSING STORY: always 'Insufficient information', naming it.
    Never default to the first story."): the zoning trigger is not decided and names the story, and the zoning row
    is insufficient information naming it, although the first story would need a Conditional Use."""
    text = "Honey Cove Restaurant, one unit with a mezzanine."
    model = BusinessProfile(business_type="restaurant", stories=["second"], square_feet=3953)
    checked = check_stated(
        model, [q("business_type", "Honey Cove Restaurant"), q("stories", "with a mezzanine")], text
    )
    final = record_cleared(checked.profile, checked)
    assert final.stories == [] and concept_facts(final).stories_not_stated
    d = _determine("mission-st-restaurant", final, tmp_path)
    t1 = next(t for t in d.pathway.triggers if t.rule_id == "T1")
    assert t1.control == "not_decided" and MISSING_PHRASES["stories"] in t1.missing_inputs
    assert any("Which story the business is on is not given" in line.text for line in t1.lines)
    assert not any("first story" in line.text.lower() for line in t1.lines)
    zoning_row = next(r for r in d.rows if r.area == "zoning_use")
    assert zoning_row.status == "insufficient_information"
    assert MISSING_PHRASES["stories"] in zoning_row.missing_inputs
    asked = " ".join(qu.question for qu in d.open_questions)
    assert f"Not known: {MISSING_PHRASES['stories']}. Needed for: zoning and use." in asked
    assert all(r.status != "not_permitted" for r in d.rows)
    # never mentioned at all: the same, no story is assumed
    plain = _determine("mission-st-restaurant", BusinessProfile(business_type="restaurant"), tmp_path / "p")
    t1 = next(t for t in plain.pathway.triggers if t.rule_id == "T1")
    assert t1.control == "not_decided" and MISSING_PHRASES["stories"] in t1.missing_inputs


def test_a_cleared_no_returns_to_not_mentioned() -> None:
    """A removed "no" (entertainment "none", no outdoor area) is the state of a fact never mentioned: no row is
    added for it; it is asked in the open questions (rule 7a)."""
    checked = check_stated(
        BusinessProfile(business_type="restaurant", entertainment_kind="none", outdoor_area="none"),
        [q("business_type", "A restaurant")],
        "A restaurant.",
    )
    final = record_cleared(checked.profile, checked)
    assert final.intake_cleared == {"entertainment_kind": "none", "outdoor_area": "none"}
    facts = concept_facts(final)
    assert facts.cleared_readings == ()
    assert set(facts.cleared_facts) == {"entertainment_kind", "outdoor_area"}
    assert set(required_areas(final)) == {"zoning_use", "health", "building_change_of_use"}


def test_a_no_alcohol_answer_or_an_override_gives_the_fact_whatever_the_value() -> None:
    from app.agents.memo_runner import MemoRunner
    from app.agents.runner import RunInput
    from app.memo.intake import NO_ALCOHOL, answered_fields

    model = BusinessProfile(
        business_type="restaurant", serves_alcohol=True, alcohol_type="beer_wine", seats=30
    )
    checked = check_stated(model, [q("business_type", "A restaurant")], "A restaurant.")
    assert checked.cleared == {"serves_alcohol": True, "alcohol_type": "beer_wine", "seats": 30}
    answers = IntakeAnswers(liquor_licence=NO_ALCOHOL)
    answered = apply_intake_answers(checked.profile, answers)
    # the answer leaves the same values the check left, and it still gives them
    assert (answered.serves_alcohol, answered.alcohol_type) == (False, "none")
    final = record_cleared(answered, checked, answered_fields(answers))
    assert final.intake_cleared == {"seats": 30}
    assert MISSING_PHRASES["alcohol_served"] not in [
        MISSING_PHRASES[n] for n in concept_facts(final).cleared_facts
    ]
    # an operator override equal to the "not stated" value gives the fact too
    inp = RunInput(description="A restaurant.", profile_overrides={"seats": None})
    given = MemoRunner._given_fields(inp, IntakeAnswers())
    assert "seats" in given
    assert record_cleared(checked.profile, checked, given).intake_cleared == {
        "serves_alcohol": True,
        "alcohol_type": "beer_wine",
    }


@pytest.mark.parametrize(
    ("field", "value", "subject"),
    [
        ("entertainment_kind", "none", "no live music"),
        ("changes_existing_business", "none", "no changes to the existing business"),
        ("merges_storefronts", False, "will not merge the storefronts"),
        ("amends_prior_approval", False, "no change to the conditions"),
        ("outdoor_area", "none", "no outdoor seating"),
        ("outdoor_alcohol_service", False, "no alcohol outside"),
    ],
)
def test_a_no_needs_a_negation_of_its_own_subject(field: str, value: Any, subject: str) -> None:
    """A "not" about something else ("not part of a chain") states no "no" for these fields."""
    text = f"A taqueria, not part of a chain, {subject}."
    other = check({field: value}, [q(field, "not part of a chain")], text)
    assert other.cleared == {field: value}
    own = check({field: value}, [q(field, subject)], text)
    assert own.cleared == {}


def test_the_parts_of_an_elided_quote_are_read_on_their_own() -> None:
    text = "Our second restaurant, on the ground floor of a mixed-use building."
    joined = check({"stories": ["second"]}, [q("stories", "second ... floor")], text)
    assert joined.cleared == {"stories": ["second"]}
    kept = check({"stories": ["first"]}, [q("stories", "Our second restaurant ... the ground floor")], text)
    assert kept.cleared == {}
    # a number and its unit must be in the same part
    split = check(
        {"square_feet": 1200},
        [q("square_feet", "1,200 ... square feet")],
        "Unit 1,200, about 900 square feet.",
    )
    assert split.cleared == {"square_feet": 1200}


@pytest.mark.parametrize(
    ("field", "value", "text", "quote"),
    [
        ("business_type", "cafe", "Our team runs a shop.", "our team"),  # "team" is not tea
        ("stories", ["third_or_above"], "A bar with a new roof.", "a new roof"),  # a roof is not a story
        ("square_feet", 2025, "Opening in SF in 2025.", "SF in 2025"),  # SF is San Francisco, not square feet
        ("closing_hour", "05:30", "A bakery open 5:30 a.m. to 3 p.m.", "open 5:30 a.m. to 3 p.m."),  # opening
        ("closes_after_2am", True, "A bakery open 5:30 a.m. to 3 p.m.", "open 5:30 a.m. to 3 p.m."),
        ("live_entertainment", True, "A wine bar, maybe live music.", "maybe live music"),  # a hope
        ("existing_use_stated", ["other"], "A cafe on 24th Street.", "24th Street"),  # says nothing of a use
    ],
)
def test_loose_words_do_not_state_a_value(field: str, value: Any, text: str, quote: str) -> None:
    result = check({field: value}, [q(field, quote)], text)
    assert result.cleared == {field: value}


@pytest.mark.parametrize(
    ("field", "value", "text", "quote"),
    [
        ("business_type", "cafe", "A tea house in the Sunset.", "A tea house"),
        ("stories", ["third_or_above"], "A bar on the third floor.", "on the third floor"),
        ("square_feet", 900, "About 900 sq ft.", "900 sq ft"),
        ("closing_hour", "15:00", "A bakery open 5:30 a.m. to 3 p.m.", "open 5:30 a.m. to 3 p.m."),
        ("closing_hour", "02:00", "Open daily 7am-2am.", "7am-2am"),
        ("closes_after_midnight", True, "Open until 1 a.m.", "until 1 a.m."),
        ("live_entertainment", True, "A wine bar with live music.", "with live music"),
        ("existing_use_stated", ["other"], "In the former bank on 24th Street.", "the former bank"),
    ],
)
def test_the_tightened_words_still_state_what_the_text_says(
    field: str, value: Any, text: str, quote: str
) -> None:
    assert check({field: value}, [q(field, quote)], text).cleared == {}
