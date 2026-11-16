"""Every row can be decided: each input the rules name as missing has a question the applicant can answer
(app.memo.intake, change of 2026-11-15, approved with the release of 2026-11-16). No database, no network; the API test uses the scripted model.

The case is the report of 2026-11-15 for 2301 Chestnut St (zoning district NC-2): "Indian food restaurant with
alochol license, open till 2 am and 40 people sitting with a outside ppatio", with the three intake answers that
existed then (not a chain, 6,000 square feet, a new licence). Four of its five rows were "Insufficient information".
The rules are unchanged: they still never fill a missing input with an assumption. What changed is that the
applicant can now give every input a row named.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from precedent.store.base import ZoningInfo

from app.agents.memo_runner import MemoRunner, required_areas
from app.catalog.loader import get_catalog
from app.core.config import settings
from app.deps import get_db, get_memo_runner, get_memo_service, get_plan_service, get_runner
from app.main import app
from app.memo import facts, rows
from app.memo.facts import concept_facts
from app.memo.intake import (
    EXISTING_OCCUPANCY_GROUP_FACT,
    EXISTING_OCCUPANCY_GROUP_PHRASE,
    QUESTION_BY_ID,
    QUESTIONS,
    IntakeAnswers,
    answered_fields,
    apply_intake_answers,
    question_for_fact,
)
from app.memo.pathway import determine, intake_question_for
from app.memo.report import site_of
from app.memo.stated import check_stated, record_cleared
from app.models.memo import Determinations
from app.models.profile import BusinessProfile, FactQuote
from app.services.db import MemoryDatabase
from app.services.memos import MemoService
from app.services.plans import PlanService
from tests.conftest import TODAY, parse_sse
from tests.fakes import BASE_PROFILE, FakeAnthropic
from tests.memo_fakes import FakeGeocoder, MemoScript, seed_store
from tests.test_api import auth
from tests.test_spelling import CHESTNUT, CHESTNUT_PROFILE, CORRECTED

RULES_DATE = dt.date(2026, 11, 15)
SITE = site_of("2301 Chestnut St, San Francisco, CA 94123", "2301 CHESTNUT ST", "0936/001")
NC_2 = ZoningInfo(
    district="NC-2",
    name="Small-Scale Neighborhood Commercial District",
    code_section="Planning Code § 711",
    bar_permission="principal",
    restaurant_permission="principal",
    rules="Hours of operation: P 6 a.m.–2 a.m.; C 2 a.m.–6 a.m.",
    source_url="https://codelibrary.amlegal.com/codes/san_francisco/latest/sf_planning/0-0-0-25360",
)
# the three answers the form asked for on 2026-11-15
THEN = IntakeAnswers(part_of_chain=False, floor_area_sqft=6000, liquor_licence="new")
INSUFFICIENT = "insufficient_information"


def chestnut(answers: IntakeAnswers) -> BusinessProfile:
    """The profile the rules read for the Chestnut description, with the applicant's answers on it."""
    base = BusinessProfile.model_validate(CHESTNUT_PROFILE)
    return apply_intake_answers(base, answers).normalized()


def report(profile: BusinessProfile) -> Determinations:
    return determine(profile, NC_2, [], [], SITE, required_areas(profile), today=RULES_DATE)


def statuses(d: Determinations) -> dict[str, str]:
    return {r.area: r.status for r in d.rows}


def with_answers(answers: IntakeAnswers, **more: Any) -> IntakeAnswers:
    return IntakeAnswers.model_validate({**answers.model_dump(exclude_none=True), **more})


# ---- the report of 2026-11-15, reproduced ------------------------------------------------------------------------
def test_the_report_of_2026_11_15_left_four_of_five_rows_undecided() -> None:
    d = report(chestnut(THEN))
    assert statuses(d) == {
        "zoning_use": INSUFFICIENT,
        "alcohol": INSUFFICIENT,
        "health": "allowed",
        "building_change_of_use": INSUFFICIENT,
        "outdoor": INSUFFICIENT,
    }
    # Since 2026-11-16 the report leads with what changes the plans (pathway rule 9). 6,000 square feet is over
    # NC-2's use size threshold, and T7 reads the use as new, so it asks for a Conditional Use; but the space's
    # last use is not given, and a former bar, restaurant or shop would make it turn on whether the floor area
    # grows (Interpretation 121.2), so the finding is worded with that condition and the overall status is the
    # rows' own. A Restaurant on the third story or above is not permitted in NC-2, and no story is given.
    new_space = (
        "the space was last used as another use (not a Bar, a Restaurant, a Limited Restaurant, Nighttime "
        "Entertainment, a retail use or a laundromat), or the floor area grows, or storefronts are merged"
    )
    assert d.overall_line == (
        "Zoning does not permit the concept if the business occupies the third story or above (use control of the "
        f"zoning district). A Conditional Use Authorization is needed if {new_space} (use size). Of the 5 "
        "approvals this concept needs: 4 insufficient information (zoning and use, alcohol licence, building "
        "permit and change of use, outdoor seating or activity area), 1 allowed (health permit)."
    )
    assert d.overall_status == INSUFFICIENT
    assert [(h.kind, h.trigger, h.status, h.condition) for h in d.headline_findings] == [
        ("not_permitted_if", "T1", INSUFFICIENT, "the business occupies the third story or above"),
        ("conditional_if", "T7", INSUFFICIENT, new_space),
    ]
    by_area = {r.area: r.missing_inputs for r in d.rows}
    assert by_area["zoning_use"] == [facts.MISSING_PHRASES["stories"], facts.MISSING_PHRASES["outdoor_area"]]
    assert by_area["alcohol"] == [facts.MISSING_PHRASES["alcohol_served"]]
    assert by_area["building_change_of_use"] == [
        facts.MISSING_PHRASES["existing_use_stated"],
        facts.MISSING_PHRASES["occupants_under_50"],
        rows.EXISTING_GROUP_PHRASE,
    ]
    assert by_area["outdoor"] == [facts.MISSING_PHRASES["outdoor_area"]]


def test_every_open_question_of_that_report_names_the_intake_question_that_settles_it() -> None:
    d = report(chestnut(THEN))
    asked = [q.intake_question for q in d.open_questions]
    assert asked == [
        "stories",
        "outdoor_area",
        "alcohol_served",
        "last_use",
        "fewer_than_50_people",
        "existing_occupancy_group",
    ]
    for q in d.open_questions:
        assert q.intake_question in QUESTION_BY_ID
        # the question's fact is the one the open question names
        fact = QUESTION_BY_ID[q.intake_question].fact
        phrase = (
            EXISTING_OCCUPANCY_GROUP_PHRASE
            if fact == EXISTING_OCCUPANCY_GROUP_FACT
            else facts.MISSING_PHRASES[fact]
        )
        assert phrase in q.question


# ---- the same concept with the questions answered: five of five ---------------------------------------------------
# what an applicant in a former shop answers
IN_A_FORMER_SHOP = with_answers(
    THEN,
    stories=["first"],
    alcohol_served="full_liquor",
    last_use="retail",
    fewer_than_50_people=True,
    outdoor_area="front",
)
# what an applicant taking over a restaurant answers; the size rules then ask three more things
TAKING_OVER_A_RESTAURANT = with_answers(
    THEN,
    stories=["first"],
    alcohol_served="beer_wine",
    last_use="restaurant",
    fewer_than_50_people=True,
    outdoor_area="front",
    existing_business_change="none",
    floor_area_before_sqft=6000,
    merges_storefronts=False,
)


def test_in_a_former_shop_the_main_answers_decide_every_row_but_the_size_rules() -> None:
    d = report(chestnut(IN_A_FORMER_SHOP))
    got = statuses(d)
    assert got["alcohol"] == "further_review"  # a new Type 47: investigation, notice, referral
    assert got["health"] == "allowed"
    assert got["building_change_of_use"] == "further_review"  # retail to restaurant is a change of use
    assert got["outdoor"] == "allowed"  # in front, on the lot
    alcohol = next(r for r in d.rows if r.area == "alcohol")
    assert "Type 47" in alcohol.approval
    # 6,000 square feet is over the district's size, and the size rules read the size before and a merger
    zoning = next(r for r in d.rows if r.area == "zoning_use")
    assert zoning.status == INSUFFICIENT
    assert zoning.missing_inputs == [
        facts.MISSING_PHRASES["floor_area_before_sqft"],
        facts.MISSING_PHRASES["merges_storefronts"],
    ]
    assert [q.intake_question for q in d.open_questions] == ["floor_area_before_sqft", "merges_storefronts"]
    # those two are under "More details"
    assert {QUESTION_BY_ID[q.intake_question or ""].group for q in d.open_questions} == {"more"}


def test_in_a_former_shop_with_the_two_follow_ups_all_five_rows_are_decided() -> None:
    """The shop was 3,000 square feet and the restaurant takes 6,000: over the district's size, so a Conditional
    Use."""
    answers = with_answers(IN_A_FORMER_SHOP, floor_area_before_sqft=3000, merges_storefronts=False)
    d = report(chestnut(answers))
    got = statuses(d)
    assert INSUFFICIENT not in got.values(), got
    assert got == {
        "zoning_use": "further_review",
        "alcohol": "further_review",
        "health": "allowed",
        "building_change_of_use": "further_review",
        "outdoor": "allowed",
    }
    assert d.overall_status == "further_review"
    assert d.overall_line == (
        "A Conditional Use Authorization is needed (use size). Of the 5 approvals this concept needs: 3 further "
        "review (zoning and use, alcohol licence, building permit and change of use), 2 allowed (health permit, "
        "outdoor seating or activity area)."
    )
    assert not [q for q in d.open_questions if q.intake_question]
    zoning = next(r for r in d.rows if r.area == "zoning_use")
    assert "Conditional Use" in zoning.approval


def test_a_space_that_was_already_that_size_takes_no_conditional_use_for_its_size() -> None:
    """The same answers with the floor area unchanged and no storefronts merged: the size control does not apply
    (trigger T7), and every row is decided."""
    answers = with_answers(IN_A_FORMER_SHOP, floor_area_before_sqft=6000, merges_storefronts=False)
    d = report(chestnut(answers))
    got = statuses(d)
    assert INSUFFICIENT not in got.values(), got
    assert got["zoning_use"] == "allowed"
    assert next(t for t in d.pathway.triggers if t.rule_id == "T7").control == "does_not_apply"
    assert not [q for q in d.open_questions if q.intake_question]


def test_taking_over_a_restaurant_all_five_rows_are_decided() -> None:
    d = report(chestnut(TAKING_OVER_A_RESTAURANT))
    got = statuses(d)
    assert INSUFFICIENT not in got.values(), got
    assert got["building_change_of_use"] == "allowed"  # the same use, unchanged, for fewer than 50 people
    assert got["alcohol"] == "further_review" and got["health"] == "allowed" and got["outdoor"] == "allowed"
    assert not [q for q in d.open_questions if q.intake_question]
    alcohol = next(r for r in d.rows if r.area == "alcohol")
    assert "Type 41" in alcohol.approval


def test_the_existing_occupancy_group_is_read_when_the_applicant_gives_it() -> None:
    """A restaurant taken over and enlarged: whether the occupancy changes turns on the existing group, which no
    public record shows. With the answer the row is decided; without it the row names the group."""
    enlarged = with_answers(
        TAKING_OVER_A_RESTAURANT, existing_business_change="enlarge", floor_area_before_sqft=3000
    )
    without = report(chestnut(enlarged))
    building = next(r for r in without.rows if r.area == "building_change_of_use")
    assert building.status == INSUFFICIENT and building.missing_inputs == [rows.EXISTING_GROUP_PHRASE]
    assert [q.intake_question for q in without.open_questions if q.needs == "plans"] == [
        "existing_occupancy_group"
    ]

    same = report(chestnut(with_answers(enlarged, existing_occupancy_group="B")))
    building = next(r for r in same.rows if r.area == "building_change_of_use")
    assert building.status == "allowed" and building.missing_inputs == []
    assert same.pathway.changes.building_occupancy == "no"

    differs = report(chestnut(with_answers(enlarged, existing_occupancy_group="A-2")))
    building = next(r for r in differs.rows if r.area == "building_change_of_use")
    assert building.status == "further_review"
    assert differs.pathway.changes.building_occupancy == "yes"


def test_a_skipped_question_is_still_never_read_as_an_answer() -> None:
    """The rules did not change: one question skipped leaves its row undecided, naming it."""
    answers = IN_A_FORMER_SHOP.model_dump(exclude_none=True)
    for skipped, area in (
        ("stories", "zoning_use"),
        ("alcohol_served", "alcohol"),
        ("last_use", "building_change_of_use"),
        ("outdoor_area", "outdoor"),
    ):
        partial = IntakeAnswers.model_validate({k: v for k, v in answers.items() if k != skipped})
        d = report(chestnut(partial))
        row = next(r for r in d.rows if r.area == area)
        assert row.status == INSUFFICIENT, skipped
        assert skipped in [q.intake_question for q in d.open_questions], skipped


# ---- whatever the concept: answering what is asked ends with nothing left to ask ---------------------------------------
# One answer per question, as an applicant who knows the space gives them.
KNOWN: dict[str, Any] = {
    "part_of_chain": False,
    "floor_area_sqft": 1800,
    "liquor_licence": "new",
    "stories": ["first"],
    "alcohol_served": "beer_wine",
    "closing_time": "23:00",
    "last_use": "retail",
    "fewer_than_50_people": True,
    "outdoor_area": "front",
    "outdoor_alcohol_service": False,
    "existing_business_change": "none",
    "floor_area_before_sqft": 1800,
    "merges_storefronts": False,
    "amends_prior_approval": False,
    "entertainment": "limited_live_performance",
    "existing_occupancy_group": "B",
}
CONCEPTS: dict[str, dict[str, Any]] = {
    "a restaurant, nothing else said": {"business_type": "restaurant"},
    "a bar, nothing else said": {"business_type": "bar"},
    "a cafe with a patio": {"business_type": "cafe", "outdoor_seating": True},
    "a restaurant with drinks and live music": {
        "business_type": "restaurant",
        "serves_alcohol": True,
        "alcohol_type": "unknown",
        "live_entertainment": True,
    },
    "the Chestnut description": CHESTNUT_PROFILE,
    "a large bar open late": {"business_type": "bar", "square_feet": 9000, "closes_after_2am": True},
}


@pytest.mark.parametrize("concept", list(CONCEPTS), ids=list(CONCEPTS))
@pytest.mark.parametrize("last_use", ["retail", "restaurant", "bar"])
def test_answering_every_question_the_report_asks_leaves_none_to_ask(concept: str, last_use: str) -> None:
    """Start from the description alone; answer exactly the questions the report asks, round after round. It ends,
    and at the end no row is undecided for want of an answer the applicant could give."""
    known = {**KNOWN, "last_use": last_use}
    answers: dict[str, Any] = {}
    base = BusinessProfile.model_validate(CONCEPTS[concept])
    for _round in range(len(QUESTIONS) + 1):
        profile = apply_intake_answers(base, IntakeAnswers.model_validate(answers)).normalized()
        d = report(profile)
        asked = [q.intake_question for q in d.open_questions if q.intake_question]
        new = [q for q in asked if q not in answers]
        if not new:
            break
        for question in new:
            answers[question] = known[question]
    else:
        pytest.fail(f"still asking after every question was answered: {asked}")
    assert not asked, f"asked again for what was answered: {asked}"
    # what is still undecided, if anything, is undecided for a reason no applicant's answer settles
    for row in d.rows:
        for phrase in row.missing_inputs:
            assert intake_question_for(phrase) is None, (row.area, phrase)
        if row.status == INSUFFICIENT:
            assert row.missing_inputs, row.area


# ---- which inputs have a question ---------------------------------------------------------------------------------
def test_which_missing_inputs_have_a_question() -> None:
    without = sorted(name for name in facts.MISSING_PHRASES if question_for_fact(name) is None)
    # The kind of business is the description itself; the seat count decides nothing the "fewer than 50 people"
    # question does not; the licences already held are read only for an existing business in a district that
    # restricts licences, with the transaction missing, and the liquor licence question answers that. "The
    # licence type" is named only where what is poured would not decide it (else "alcohol_served" is named), so
    # no answer settles it and it points at no question. The kind of food or drink service, named in place of the
    # kind of business for a bar that serves no alcohol (pathway rule 1b, 2026-11-16), has its own question since
    # the owner decision of that day ("ask what kind of food or drink service it is; don't assume").
    assert without == ["licence_type", "licences_held", "planning_uses", "seats"]
    assert question_for_fact("food_service") is QUESTION_BY_ID["food_service"]
    assert question_for_fact("licence_type") is None
    assert question_for_fact("other_locations") is QUESTION_BY_ID["other_locations"]
    assert question_for_fact(EXISTING_OCCUPANCY_GROUP_FACT) is QUESTION_BY_ID["existing_occupancy_group"]
    assert EXISTING_OCCUPANCY_GROUP_PHRASE == rows.EXISTING_GROUP_PHRASE
    for name, phrase in facts.MISSING_PHRASES.items():
        question = question_for_fact(name)
        assert intake_question_for(phrase) == (question.id if question else None)
    # a phrase only Planning can settle has none
    assert (
        intake_question_for("whether the outdoor area meets every limit of Planning Code § 202.2(a)(7)")
        is None
    )


# ---- review of 2026-11-15: answers the report could not settle, conflicts, and where a line's fact came from -------
# A description with no spelling mistake, so these tests do not turn on app.memo.spelling.
PATIO_TEXT = "Indian restaurant with an alcohol license and a patio, open until 10 pm"
# what an intake model reads from it, with two values the text does not state: the licence type (the quote has
# no number in it) and alcohol in the outdoor area (no quote at all)
PATIO_MODEL: dict[str, Any] = {
    "business_type": "restaurant",
    "serves_alcohol": True,
    "alcohol_type": "unknown",
    "licence_type": "47",
    "outdoor_seating": True,
    "outdoor_alcohol_service": True,
    "closing_hour": "22:00",
}
PATIO_QUOTES = [
    ("business_type", "Indian restaurant"),
    ("serves_alcohol", "alcohol license"),
    ("licence_type", "alcohol license"),
    ("outdoor_seating", "a patio"),
    ("closing_hour", "open until 10 pm"),
]


def through_the_runner(answers: IntakeAnswers) -> tuple[BusinessProfile, Determinations]:
    """The runner's own order (MemoRunner.run): the stated-facts check, the answers, what stays cleared, then the
    rules."""
    checked = check_stated(
        BusinessProfile.model_validate(PATIO_MODEL),
        [FactQuote.model_validate({"field": f, "quote": q}) for f, q in PATIO_QUOTES],
        PATIO_TEXT,
    )
    merged = apply_intake_answers(checked.profile, answers)
    profile = record_cleared(merged, checked, answered_fields(answers)).normalized()
    return profile, report(profile)


def test_a_cleared_licence_type_is_settled_by_the_answer_on_what_is_poured() -> None:
    """Review #9: the check cleared the model's Type 47 (its quote has no number). Before the answer the report
    asks what alcohol will be served, once; after it the rules derive the type, and nothing points at the
    question already answered."""
    before, d = through_the_runner(IntakeAnswers(liquor_licence="new", stories=["first"]))
    assert before.intake_cleared["licence_type"] == "47"
    asked = [q.intake_question for q in d.open_questions]
    assert asked.count("alcohol_served") == 1
    assert not [q for q in d.open_questions if "the licence type" in q.question]

    after, d = through_the_runner(
        IntakeAnswers(liquor_licence="new", alcohol_served="full_liquor", stories=["first"])
    )
    alcohol = next(r for r in d.rows if r.area == "alcohol")
    assert alcohol.status == "further_review" and "Type 47" in alcohol.approval
    assert "licence_type" not in concept_facts(after).cleared_facts
    assert not [q for q in d.open_questions if "licence type" in q.question]
    assert "alcohol_served" not in [q.intake_question for q in d.open_questions]


def test_the_licence_type_points_at_no_question_when_what_is_poured_would_not_decide_it() -> None:
    """Review #17: a hotel that pours spirits still has no licence type the rules can derive. The report names the
    licence type, and offers no question: answering what is poured again would settle nothing."""
    hotel = apply_intake_answers(
        BusinessProfile(business_type="hotel", stories=["first"]),
        IntakeAnswers(liquor_licence="new", alcohol_served="full_liquor"),
    ).normalized()
    d = report(hotel)
    licence = [q for q in d.open_questions if "the licence type" in q.question]
    assert len(licence) == 1 and licence[0].intake_question is None
    assert intake_question_for(facts.MISSING_PHRASES["licence_type"]) is None
    # where what is poured would decide it, the report names that and points at its question
    drinks = report(chestnut(THEN))
    assert [q.intake_question for q in drinks.open_questions if "alcohol will be served" in q.question] == [
        "alcohol_served"
    ]


def test_no_outdoor_area_settles_alcohol_in_the_outdoor_area() -> None:
    """Review #10: the check cleared the model's "alcohol served outdoors" (no quote). Answering "No outdoor area"
    settles it: no open question points at the follow-up the form hides and the API refuses with that answer."""
    profile, d = through_the_runner(
        IntakeAnswers(
            liquor_licence="new", alcohol_served="beer_wine", stories=["first"], outdoor_area="none"
        )
    )
    assert profile.outdoor_alcohol_service is False
    assert "outdoor_alcohol_service" not in profile.intake_cleared
    assert "outdoor_alcohol_service" not in [q.intake_question for q in d.open_questions]
    assert not [q for q in d.open_questions if "outdoor area" in q.question]
    assert "outdoor" not in statuses(d)


def test_alcohol_served_outdoors_is_alcohol_served_and_the_row_names_the_disagreement() -> None:
    """Review #11: "alcohol served outdoors: yes" on a description that does not say alcohol is served (or says
    none is). The answer is read, the safe reading: the alcohol row is there, is not decided without the type and
    the transaction, and its first line says the description and the answer disagree."""
    dry = BusinessProfile(business_type="restaurant", stories=["first"], outdoor_seating=True)
    profile = apply_intake_answers(
        dry, IntakeAnswers(outdoor_area="front", outdoor_alcohol_service=True)
    ).normalized()
    assert profile.serves_alcohol is True and "alcohol" in required_areas(profile)
    d = report(profile)
    alcohol = next(r for r in d.rows if r.area == "alcohol")
    assert alcohol.status == INSUFFICIENT
    assert alcohol.basis[0].rule_id == "alcohol.outdoor_answer"
    assert alcohol.basis[0].text.startswith("You answered that alcohol will be served in the outdoor area")
    assert "The two disagree" in alcohol.basis[0].text
    # a description that serves alcohol, or another alcohol answer, gives no such line
    for described, answers in (
        (dry.model_copy(update={"serves_alcohol": True}), IntakeAnswers(outdoor_area="front")),
        (dry, IntakeAnswers(outdoor_area="front", liquor_licence="new")),
    ):
        p = apply_intake_answers(
            described,
            IntakeAnswers.model_validate(
                {**answers.model_dump(exclude_none=True), "outdoor_alcohol_service": True}
            ),
        ).normalized()
        row = next(r for r in report(p).rows if r.area == "alcohol")
        assert "alcohol.outdoor_answer" not in [line.rule_id for line in row.basis]


def test_fewer_than_50_people_against_120_seats_is_not_decided() -> None:
    """Review #12: "fewer than 50 people: yes" with a description that gives 120 seats. Neither is read over the
    other: the proposed occupancy group is not established and the building row names it."""
    answers = IntakeAnswers(
        last_use="restaurant",
        existing_business_change="none",
        existing_occupancy_group="B",
        liquor_licence="none",
        outdoor_area="none",
        stories=["first"],
    )
    big = BusinessProfile(business_type="restaurant", seats=120)
    skipped = report(apply_intake_answers(big, answers).normalized())
    assert statuses(skipped)["building_change_of_use"] == "further_review"  # 120 seats: Group A-2, from B
    d = report(apply_intake_answers(big, with_answers(answers, fewer_than_50_people=True)).normalized())
    building = next(r for r in d.rows if r.area == "building_change_of_use")
    assert building.status == INSUFFICIENT
    assert building.missing_inputs == [facts.MISSING_PHRASES["occupants_under_50"]]
    assert d.pathway.changes.building_occupancy == "not_established"
    texts = [line.text for line in building.basis]
    assert (
        "You answered that the space is for fewer than 50 people, but the description gives 120 seats, which "
        "means at least 50 people. The two disagree, so the proposed occupancy group is not established."
    ) in texts
    assert not [t for t in texts if "proposed occupancy is Group B" in t]


def test_a_line_says_you_answered_for_a_fact_an_answer_gave() -> None:
    """Reviews #15 and #21: the building and change-of-use lines name where their fact came from. An answer is
    "You answered ..."; the description is "The description says ..." (a backtest profile, built from the
    description's facts)."""
    d = report(chestnut(IN_A_FORMER_SHOP))
    texts = [line.text for r in d.rows for line in r.basis]
    assert (
        "You answered that the space is for fewer than 50 people, so the proposed occupancy is Group B."
        in texts
    )
    assert "Retail to Restaurant is a change of use, with the last use of the space as you answered." in texts
    assert not [t for t in texts if t.startswith("The description says the space is for")]
    assert not [t for t in texts if "last use of the space as described" in t]

    taken_over = report(chestnut(TAKING_OVER_A_RESTAURANT))
    texts = [line.text for r in taken_over.rows for line in r.basis]
    assert any(t.startswith("The last use of the space, as you answered, is Restaurant.") for t in texts)
    assert any(
        t.startswith("The same use continues and you answered that the business stays as it is")
        for t in texts
    )

    shows = report(chestnut(with_answers(IN_A_FORMER_SHOP, entertainment="limited_live_performance")))
    entertainment = next(r for r in shows.rows if r.area == "entertainment")
    assert any(line.text.startswith("You answered the kind of entertainment") for line in entertainment.basis)

    described = BusinessProfile.model_validate(
        {
            **CHESTNUT_PROFILE,
            "stories": ["first"],
            "occupants_under_50": True,
            "existing_use_stated": ["retail"],
        }
    ).normalized()
    texts = [line.text for r in report(described).rows for line in r.basis]
    assert (
        "The description says the space is for fewer than 50 people, so the proposed occupancy is Group B."
        in texts
    )
    assert "Retail to Restaurant is a change of use, with the last use of the space as described." in texts
    assert not [t for t in texts if t.startswith("You answered")]


def test_the_patch_of_2026_11_15_is_labelled_with_its_release() -> None:
    """Review #22: no owner decision of 2026-11-15 is recorded; the patch's choices are labelled as the change of
    2026-11-15, approved with the release of 2026-11-16."""
    repo = Path(__file__).resolve().parents[3]
    for path in (
        "apps/api/app/memo/intake.py",
        "apps/api/app/memo/pathway.py",
        "docs/api-contract-memo.md",
    ):
        text = (repo / path).read_text()
        assert "decision of 2026-11-15" not in text, path
        assert "decisions of 2026-11-15" not in text, path
    assert (
        "change of 2026-11-15, approved with the release of 2026-11-16"
        in (repo / "apps/api/app/memo/intake.py").read_text()
    )


# ---- through the API: the misspelt description, the corrected quotes, the answers ---------------------------------------
DESCRIPTION = CHESTNUT
SCRIPT_PROFILE = {**BASE_PROFILE, "business_name": None, "square_feet": None, **CHESTNUT_PROFILE}
SCRIPT_PROFILE |= {"live_entertainment": False, "amplified_sound": False}


@pytest.fixture
def db() -> MemoryDatabase:
    return MemoryDatabase()


@pytest.fixture
def client(db: MemoryDatabase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """The API with a scripted intake model that reads the Chestnut description and, like a real model, quotes the
    applicant's misspelt words with the spelling put right."""
    import app.memo.context as ctx
    import app.routes.memos as memo_routes
    import app.routes.public_memo as public_routes
    import app.tools.precedent_tools as pt

    store = seed_store(tmp_path / "data")
    geocoder = FakeGeocoder()
    for mod in (ctx, pt, memo_routes, public_routes):
        if hasattr(mod, "get_store"):
            monkeypatch.setattr(mod, "get_store", lambda: store)
        if hasattr(mod, "get_geocoder"):
            monkeypatch.setattr(mod, "get_geocoder", lambda: geocoder)
    monkeypatch.setattr(settings, "ADMIN_EMAILS", ["Owner@Example.com "])  # the memo comes back in full
    script = MemoScript(
        profile=SCRIPT_PROFILE, intake_quotes=[{"field": f, "quote": q} for f, q in CORRECTED]
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_plan_service] = lambda: PlanService(db, settings)
    app.dependency_overrides[get_memo_service] = lambda: MemoService(db, settings)
    app.dependency_overrides[get_runner] = lambda: None
    app.dependency_overrides[get_memo_runner] = lambda: MemoRunner(
        FakeAnthropic(script), get_catalog(), settings, store, geocoder, today=TODAY
    )  # type: ignore[arg-type]
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def create(client: TestClient, intake: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"address": "995 Valencia St", "description": DESCRIPTION}
    if intake:
        payload["intake"] = intake
    with client.stream("POST", "/v1/memos", json=payload, headers=auth()) as r:
        assert r.status_code == 200
        events = parse_sse("".join(r.iter_text()))
    assert events[-1][0] == "memo", events[-1]
    record: dict[str, Any] = events[-1][1]
    return record


def test_the_misspelt_description_reaches_the_report_with_its_facts_and_the_applicants_own_words(
    client: TestClient,
) -> None:
    memo = create(client)["memo"]
    known = {f["fact"]: f for f in memo["facts"] if f["origin"] != "not_known"}
    # the outdoor area and the seats are read, each with the applicant's words as written
    assert known["seats"]["value"] == "40" and known["seats"]["quotes"] == ["40 people sitting"]
    assert known["closing"]["quotes"] == ["open till 2 am"]
    outdoor = next(r for r in memo["approvals"] if r["area"] == "outdoor")
    # the row no longer says the description does not state an outdoor area: it names where the area is
    assert all(
        "does not state whether there will be an outdoor area" not in line["text"]
        for line in outdoor["basis"]
    )
    assert facts.MISSING_PHRASES["outdoor_area"] in outdoor["missing_inputs"]
    assert "alcohol" in [r["area"] for r in memo["approvals"]]
    # every open question the applicant can answer names its intake question
    asked = [q["intake_question"] for q in memo["could_not_establish"] if q["intake_question"]]
    assert {"stories", "alcohol_served", "outdoor_area", "liquor_licence"} <= set(asked)


def test_with_the_questions_answered_nothing_the_applicant_can_answer_is_left_open(
    client: TestClient,
) -> None:
    """Round after round through the API: the report names the questions, the applicant answers them, and the
    next report reads the answers. (The district of this test store is one the rule table does not carry, so two
    rows stay undecided for a reason only Planning settles; in a district it carries every row is decided, as the
    tests above show for NC-2.)"""
    first = create(client)["memo"]
    undecided = [r["area"] for r in first["approvals"] if r["status"] == INSUFFICIENT]
    assert len(undecided) >= 3
    answers: dict[str, Any] = {}
    known = {**KNOWN, "alcohol_served": "full_liquor"}
    memo = first
    for _round in range(len(QUESTIONS) + 1):
        new = [q["intake_question"] for q in memo["could_not_establish"] if q["intake_question"]]
        new = [q for q in dict.fromkeys(new) if q not in answers]
        if not new:
            break
        answers |= {q: known[q] for q in new}
        record = create(client, intake=answers)
        memo = record["memo"]
        assert record["intake"] == {**dict.fromkeys(IntakeAnswers.model_fields), **answers}
    assert not [q for q in memo["could_not_establish"] if q["intake_question"]]
    still = {r["area"]: r["missing_inputs"] for r in memo["approvals"] if r["status"] == INSUFFICIENT}
    assert len(still) < len(undecided)
    for area, missing in still.items():
        assert missing and all(intake_question_for(phrase) is None for phrase in missing), (area, missing)
    by_area = {r["area"]: r["status"] for r in memo["approvals"]}
    assert by_area["alcohol"] == "further_review" and by_area["building_change_of_use"] == "further_review"
    # each answer is shown as the applicant's answer to an intake question
    by_fact = {f["fact"]: f for f in memo["facts"]}
    for fact in ("stories", "alcohol_served", "existing_use_stated", "outdoor_area"):
        assert by_fact[fact]["origin"] == "intake_answer", fact
        assert by_fact[fact]["origin_label"] == "Your answer to an intake question"
