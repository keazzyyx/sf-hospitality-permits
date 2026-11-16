"""Second review of the intake answers (change of 2026-11-15, approved with the release of 2026-11-16). No database, no
network, no model.

1. "Alcohol served outdoors: yes" says there is an outdoor area: the outdoor row is there, and where the area is
   stays not known until it is given (it is never assumed).
2. "Fewer than 50 people: yes" against 120 seats is asked as the conflict it is, not as an unanswered question.
3. A rule line whose fact came from an intake answer says "You answered ...", never "The description says ...".
5. "The licence type", when the check cleared it, points at the answer that settles why it is not known.
(Problem 4, the fields only code sets refused in `profile_overrides`, is tested through the API in
tests/test_memo_api.py.)
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import replace
from typing import Any

import pytest
from precedent.models import Overlay
from precedent.store.base import ZoningInfo

from app.agents.memo_runner import required_areas
from app.memo import triggers as tg
from app.memo.facts import MISSING_PHRASES, concept_facts
from app.memo.intake import IntakeAnswers, answered_fields, apply_intake_answers
from app.memo.pathway import _intake_question, determine
from app.memo.report import Site, SiteRecord
from app.memo.stated import check_stated, record_cleared
from app.models.memo import Determinations, RowDetermination, RuleLine
from app.models.profile import BusinessProfile, FactQuote
from tests.test_all_rows_decided import (
    IN_A_FORMER_SHOP,
    INSUFFICIENT,
    NC_2,
    RULES_DATE,
    SITE,
    TAKING_OVER_A_RESTAURANT,
    chestnut,
    report,
    with_answers,
)
from tests.test_pathway import MISSION as NCT_MISSION
from tests.test_pathway import NCT3, SITE_995, VALENCIA_OVERLAYS
from tests.test_triggers import CALLE24, MISSION, site, zoning

D = dt.date


def row(d: Determinations, area: str) -> RowDetermination:
    return next(r for r in d.rows if r.area == area)


def through_the_runner(
    model: dict[str, Any], quotes: list[tuple[str, str]], text: str, answers: IntakeAnswers
) -> tuple[BusinessProfile, Determinations]:
    """The runner's own order (MemoRunner.run_memo): the stated-facts check, the answers, what stays cleared, then
    the rules."""
    checked = check_stated(
        BusinessProfile.model_validate(model),
        [FactQuote.model_validate({"field": f, "quote": q}) for f, q in quotes],
        text,
    )
    merged = apply_intake_answers(checked.profile, answers)
    profile = record_cleared(merged, checked, answered_fields(answers)).normalized()
    return profile, report(profile)


# ---- 1. alcohol served outdoors says there is an outdoor area -------------------------------------------------------
DRY_TEXT = "Indian restaurant, open until 10 pm"
DRY_MODEL: dict[str, Any] = {"business_type": "restaurant", "closing_hour": "22:00"}
DRY_QUOTES = [("business_type", "Indian restaurant"), ("closing_hour", "open until 10 pm")]


def test_alcohol_served_outdoors_gives_an_outdoor_row_whose_place_is_not_known() -> None:
    """Review round 2, #1: the alcohol row said "You answered that alcohol will be served in the outdoor area",
    and there was no outdoor row. The answer says there is an outdoor area: the row is there, its place is not
    known, so it is insufficient information and points at the outdoor-area question."""
    profile, d = through_the_runner(
        DRY_MODEL, DRY_QUOTES, DRY_TEXT, IntakeAnswers(outdoor_alcohol_service=True, stories=["first"])
    )
    assert "outdoor" in required_areas(profile)
    assert profile.outdoor_seating is True and profile.outdoor_area is None  # where it is: never assumed
    outdoor = row(d, "outdoor")
    assert outdoor.status == INSUFFICIENT
    assert outdoor.missing_inputs == [MISSING_PHRASES["outdoor_area"]]
    assert "outdoor_area" in [q.intake_question for q in d.open_questions]
    # its line says where the outdoor area came from
    assert outdoor.basis[0].text.startswith(
        "You answered that alcohol will be served in an outdoor area, but not where the area is."
    )
    assert not [line for line in outdoor.basis if "An outdoor area is described" in line.text]
    alcohol = row(d, "alcohol")
    assert alcohol.basis[0].rule_id == "alcohol.outdoor_answer"

    # answering where it is decides the row: in front, on the lot, is principally permitted in NC-2
    _, placed = through_the_runner(
        DRY_MODEL,
        DRY_QUOTES,
        DRY_TEXT,
        IntakeAnswers(outdoor_alcohol_service=True, outdoor_area="front", stories=["first"]),
    )
    assert row(placed, "outdoor").status == "allowed"
    assert "outdoor_area" not in [q.intake_question for q in placed.open_questions]


def test_alcohol_served_outdoors_overrules_a_description_that_says_there_is_no_outdoor_area() -> None:
    """An answer wins over the description: the description's "no outdoor area" is overruled, and where the area
    is is not known (the safe direction), never read as the description's "none"."""
    none_outdoors = BusinessProfile(business_type="restaurant", stories=["first"], outdoor_area="none")
    profile = apply_intake_answers(none_outdoors, IntakeAnswers(outdoor_alcohol_service=True)).normalized()
    assert profile.outdoor_area is None and profile.outdoor_seating is True
    assert "outdoor_seating" in profile.intake_answered and "outdoor_area" not in profile.intake_answered
    outdoor = row(report(profile), "outdoor")
    assert outdoor.status == INSUFFICIENT and outdoor.missing_inputs == [MISSING_PHRASES["outdoor_area"]]
    # "no" to alcohol outdoors says nothing about whether there is an outdoor area
    dry = apply_intake_answers(
        BusinessProfile(business_type="restaurant"), IntakeAnswers(outdoor_alcohol_service=False)
    )
    assert dry.outdoor_seating is False and "outdoor" not in required_areas(dry.normalized())
    assert "outdoor_seating" not in answered_fields(IntakeAnswers(outdoor_alcohol_service=False))


# ---- 2. the fewer-than-50 conflict is asked as a conflict ---------------------------------------------------------
def test_fewer_than_50_people_against_120_seats_is_asked_as_the_conflict() -> None:
    """Review round 2, #2: the open question read "Not known: whether the space is for fewer than 50 people", as
    if it had not been answered. It names the conflict in plain words and still points at the question."""
    answers = IntakeAnswers(
        last_use="restaurant",
        existing_business_change="none",
        existing_occupancy_group="B",
        liquor_licence="none",
        outdoor_area="none",
        stories=["first"],
        fewer_than_50_people=True,
    )
    big = BusinessProfile(business_type="restaurant", seats=120)
    d = report(apply_intake_answers(big, answers).normalized())
    asked = [q for q in d.open_questions if q.intake_question == "fewer_than_50_people"]
    assert [q.question for q in asked] == [
        "Your answer says the space is for fewer than 50 people, but the description gives 120 seats. Which is "
        "right? Needed for: building permit and change of use."
    ]
    assert not [q for q in d.open_questions if q.question.startswith("Not known: whether the space is for")]
    assert row(d, "building_change_of_use").missing_inputs == [MISSING_PHRASES["occupants_under_50"]]

    # where the description itself says both (a profile built from the description's facts)
    described = BusinessProfile(
        business_type="restaurant", seats=120, occupants_under_50=True, stories=["first"]
    )
    questions = [q for q in report(described).open_questions if q.intake_question == "fewer_than_50_people"]
    assert [q.question for q in questions] == [
        "The description says the space is for fewer than 50 people, but it also gives 120 seats. Which is right? "
        "Needed for: building permit and change of use."
    ]
    # no conflict: the question is the plain one
    small = report(BusinessProfile(business_type="restaurant", seats=40, stories=["first"]))
    plain = [q for q in small.open_questions if q.intake_question == "fewer_than_50_people"]
    assert [q.question for q in plain] == [
        "Not known: whether the space is for fewer than 50 people. Needed for: building permit and change of use."
    ]


# ---- 3. a line whose fact came from an answer says "You answered" ---------------------------------------------------
# A line that says what the description says, gives or describes (a positive claim about the description). "The
# concept as described" is the whole concept, as given; a line that says the description does NOT give something is
# true of the description whatever the answers say.
DESCRIPTION_CLAIM = re.compile(
    r"\bdescription (says|gives|states)\b(?! no\b)"
    r"|\b(is|are) described\b"
    r"|\bdescribed as\b"
    r"|\bentertainment described\b"
    r"|(?<!concept )\bas described\b"
    r"|\bstated (not )?to be\b"
    r"|\bstories stated\b"
)


def every_line(d: Determinations) -> list[RuleLine]:
    changes = d.pathway.changes
    return [
        *d.pathway.lines,
        *(line for f in d.pathway.triggers for line in f.lines),
        *(line for r in d.rows for line in (*r.basis, *r.referral_steps)),
        *changes.planning_use_lines,
        *changes.building_occupancy_lines,
        *changes.neighbourhood_notice_lines,
    ]


Place = tuple[ZoningInfo, list[Overlay], list[SiteRecord], Site, dt.date]
AT_CHESTNUT: Place = (NC_2, [], [], SITE, RULES_DATE)
ON_VALENCIA: Place = (NCT_MISSION, VALENCIA_OVERLAYS, [], SITE_995, RULES_DATE)
EVERY_ANSWER = IntakeAnswers(
    part_of_chain=False,
    floor_area_sqft=1800,
    liquor_licence="none",
    stories=["second"],
    closing_time="08:00",
    last_use="limited_restaurant",
    fewer_than_50_people=True,
    outdoor_area="none",
    existing_business_change="none",
    floor_area_before_sqft=1800,
    merges_storefronts=False,
    amends_prior_approval=True,
    entertainment="none",
    existing_occupancy_group="B",
)
LIVE_MUSIC_AND_A_PATIO = {"business_type": "restaurant", "live_entertainment": True, "outdoor_seating": True}
ANSWERED_REPORTS: dict[str, tuple[dict[str, Any], IntakeAnswers, Place]] = {
    # the input of the review
    "taking over a restaurant": (
        {},
        with_answers(
            TAKING_OVER_A_RESTAURANT, closing_time="23:00", entertainment="none", amends_prior_approval=False
        ),
        AT_CHESTNUT,
    ),
    "a former shop, a morning close, live performance": (
        {},
        with_answers(
            IN_A_FORMER_SHOP,
            closing_time="08:00",
            entertainment="limited_live_performance",
            amends_prior_approval=True,
        ),
        AT_CHESTNUT,
    ),
    "alcohol served outdoors, place not given": (
        {"business_type": "restaurant", "closing_hour": "22:00"},
        IntakeAnswers(outdoor_alcohol_service=True, stories=["first"]),
        AT_CHESTNUT,
    ),
    "every answer, in the Mission SUD": (LIVE_MUSIC_AND_A_PATIO, EVERY_ANSWER, ON_VALENCIA),
    "a bar that stays, in the Mission SUD": (
        {**LIVE_MUSIC_AND_A_PATIO, "business_type": "bar"},
        with_answers(EVERY_ANSWER, liquor_licence="already_held", alcohol_served="beer_wine", last_use="bar"),
        ON_VALENCIA,
    ),
    "a restaurant that stays, rear patio, in the Mission SUD": (
        LIVE_MUSIC_AND_A_PATIO,
        with_answers(
            EVERY_ANSWER,
            liquor_licence="already_held",
            alcohol_served="full_liquor",
            last_use="restaurant",
            outdoor_area="rear_or_side",
            existing_business_change="intensify",
            amends_prior_approval=False,
            stories=["first"],
        ),
        ON_VALENCIA,
    ),
}


def _report_at(profile: BusinessProfile, place: Place) -> Determinations:
    zone, overlays, records, at, on = place
    return determine(profile, zone, overlays, records, at, required_areas(profile), today=on)


@pytest.mark.parametrize("name", list(ANSWERED_REPORTS), ids=list(ANSWERED_REPORTS))
def test_no_line_says_the_description_gives_what_only_an_answer_gave(name: str) -> None:
    """Review round 2, #3: walk every rule line of an answered report. A line that says what the description says
    (gives, describes, states) must rest on the description: the same report with no answer prints it too. A line
    the description alone does not print rests on an answer, and says "You answered ..." instead."""
    given, answers, place = ANSWERED_REPORTS[name]
    base = BusinessProfile.model_validate(given) if given else chestnut(IntakeAnswers())
    answered = _report_at(apply_intake_answers(base, answers).normalized(), place)
    description_only = {line.text for line in every_line(_report_at(base.normalized(), place))}
    resting_on_an_answer = [
        f"{line.rule_id}: {line.text}"
        for line in every_line(answered)
        if DESCRIPTION_CLAIM.search(line.text)
        and "you answered" not in line.text.lower()
        and line.text not in description_only
    ]
    assert resting_on_an_answer == []
    # the walk reads lines that say "You answered": the answers reached the rules
    assert any("you answered" in line.text.lower() for line in every_line(answered))


# One trigger line per case: the profile that reaches it, where, and the field the line rests on. Without the
# answer the line says what the description says; with it, "You answered ...".
@pytest.mark.parametrize(
    ("given", "district", "on", "overlays", "as_new", "field", "described", "answered"),
    [
        (
            {
                "existing_use_stated": ["restaurant"],
                "changes_existing_business": "none",
                "stories": ["first"],
            },
            "NC-2",
            RULES_DATE,
            [],
            False,
            "changes_existing_business",
            "and the description says it is not to be enlarged or intensified",
            "A Restaurant continues at this address, and you answered that it is not to be enlarged or intensified.",
        ),
        (
            {"amends_prior_approval": False, "stories": ["first"]},
            "NC-2",
            RULES_DATE,
            [],
            False,
            "amends_prior_approval",
            "The description says no condition of an earlier approval is to be changed",
            "You answered that no condition of an earlier approval is to be changed, so this trigger does not "
            "apply.",
        ),
        (
            {"amends_prior_approval": True, "stories": ["first"]},
            "NC-2",
            RULES_DATE,
            [],
            False,
            "amends_prior_approval",
            "The description says the conditions of an earlier approval are to be changed",
            "You answered that the conditions of an earlier approval are to be changed.",
        ),
        (
            {"entertainment_kind": "none", "stories": ["first"]},
            "NC-2",
            RULES_DATE,
            [],
            False,
            "entertainment_kind",
            "No entertainment is described",
            "You answered that there is no entertainment, so this trigger does not apply.",
        ),
        (
            {"entertainment_kind": "limited_live_performance", "stories": ["first"]},
            "NC-2",
            RULES_DATE,
            [],
            False,
            "entertainment_kind",
            "The entertainment described is a Limited Live Performance",
            "You answered that the entertainment is a Limited Live Performance.",
        ),
        (
            {"outdoor_area": "none", "stories": ["first"]},
            "NC-2",
            RULES_DATE,
            [],
            False,
            "outdoor_area",
            "No outdoor area is described",
            "You answered that there is no outdoor area, so this trigger does not apply.",
        ),
        (
            {"outdoor_seating": True, "stories": ["first"]},
            "NC-2",
            RULES_DATE,
            [],
            False,
            "outdoor_seating",
            "An outdoor area is described, but not where it is",
            "You answered that alcohol will be served in an outdoor area, but not where the area is.",
        ),
        (
            {"formula_retail": False, "stories": ["first"]},
            "NC-2",
            RULES_DATE,
            [],
            False,
            "formula_retail",
            "The business is stated not to be part of a chain",
            "You answered that the business is not part of a chain, so the formula retail control asks for "
            "nothing.",
        ),
        (
            {"closing_hour": "08:00", "stories": ["first"]},
            "NC-2",
            RULES_DATE,
            [],
            False,
            "closing_hour",
            "is a morning close, and the description does not say whether the business is open through the night",
            "Hours: you answered a closing time of 8 a.m., a morning close, and not whether the business is open "
            "through the night until then",
        ),
        (
            {"stories": ["first"]},
            "NCT-MISSION",
            D(2023, 3, 1),
            [MISSION],
            False,
            "serves_alcohol",
            "The concept is not described as serving alcohol",
            "You answered that no alcohol will be served, so the liquor licence rules of",
        ),
        (
            {
                "serves_alcohol": True,
                "licence_type": "47",
                "stories": ["first"],
                "existing_use_stated": ["restaurant"],
                "alcohol_transaction": "licence_already_held",
                "changes_existing_business": "intensify",
            },
            "NCT-MISSION",
            D(2023, 3, 1),
            [MISSION],
            False,
            "changes_existing_business",
            "The description says the business is not to be enlarged",
            "You answered that the business is not to be enlarged, so it was not applied",
        ),
        (
            {"stories": ["second"], "existing_use_stated": ["bar"]},
            "NCD-NORTH BEACH",
            D(2024, 6, 1),
            [],
            False,
            "stories",
            "which is not among the stories stated",
            "which is not among the stories you answered",
        ),
        (
            {
                "stories": ["first"],
                "existing_use_stated": ["restaurant"],
                "changes_existing_business": "none",
            },
            "NCD-NORTH BEACH",
            D(2024, 6, 1),
            [],
            True,
            "changes_existing_business",
            "the same use, and the description says it is not enlarged or intensified",
            "the same use, and you answered that it is not enlarged or intensified",
        ),
        (
            {"stories": ["first"], "existing_use_stated": ["limited_restaurant"]},
            "NCT-24TH-MISSION",
            D(2025, 6, 1),
            [CALLE24],
            False,
            "existing_use_stated",
            "The space is stated to be a Limited Restaurant",
            "You answered that the space was last a Limited Restaurant, and the concept is a Restaurant",
        ),
    ],
    ids=[
        "T3 no change",
        "T10 no",
        "T10 amends",
        "T6 none",
        "T6 limited live",
        "T9 none",
        "T9 not placed",
        "T5 no",
        "T11 morning",
        "T4 no alcohol",
        "T4 no expansion",
        "T2 and T4 story",
        "T2 same use",
        "T2 frontage exemption",
    ],
)
def test_a_trigger_line_says_you_answered_for_a_fact_an_answer_gave(
    given: dict[str, Any],
    district: str,
    on: dt.date,
    overlays: list[Overlay],
    as_new: bool,
    field: str,
    described: str,
    answered: str,
) -> None:
    concept = concept_facts(BusinessProfile.model_validate({"business_type": "restaurant", **given}))

    def text(answered_fields: frozenset[str]) -> str:
        found = tg.evaluate(
            replace(concept, answered=answered_fields),
            site(on),
            zoning(district),
            overlays,
            rules_date=on,
            today=on,
            as_new=as_new,
        )
        return " ".join(line.text for f in found for line in f.lines)

    by_description = text(frozenset())
    assert described in by_description and answered not in by_description
    by_answer = text(frozenset({field}))
    assert answered in by_answer and described not in by_answer
    # the other answers change nothing in it
    assert text(frozenset({"seats", "square_feet"} - {field})) == by_description


def test_the_rows_say_you_answered_for_what_is_poured_and_where_the_outdoor_area_is() -> None:
    """The alcohol row's derived licence type, the outdoor row's status and the formula retail notice line."""
    shop = report(chestnut(IN_A_FORMER_SHOP))
    assert (
        "The description does not state a licence type. The rules derived ABC Type 47 (on-sale general, eating "
        "place) from the kind of business and what you answered it pours."
    ) in [line.text for line in row(shop, "alcohol").basis]
    assert (
        "The outdoor activity area, where you answered it is, is principally permitted here, so it needs no "
        "Conditional Use Authorization: allowed."
    ) in [line.text for line in row(shop, "outdoor").basis]
    described = BusinessProfile(
        business_type="restaurant",
        serves_alcohol=True,
        alcohol_type="full_liquor",
        stories=["first"],
        outdoor_seating=True,
        outdoor_area="front",
    )
    d = report(described)
    assert any(
        line.text.endswith("from the kind of business and what it pours.") for line in row(d, "alcohol").basis
    )
    assert (
        row(d, "outdoor").basis[-1].text.startswith("The outdoor activity area as described is principally")
    )

    # neighbourhood notice for a chain before 2024-01-14 (NCT-3: a district class § 311 lists)
    chain = BusinessProfile(business_type="restaurant", stories=["first"], formula_retail=True)
    for profile, words in (
        (chain, "the business is stated to be part of a chain"),
        (
            chain.model_copy(update={"intake_answered": ["formula_retail"]}),
            "you answered that the business is part of a chain with eleven or more other locations",
        ),
    ):
        d = determine(profile, NCT3, [], [], SITE_995, required_areas(profile), today=D(2023, 6, 1))
        assert any(words in line.text for line in d.pathway.changes.neighbourhood_notice_lines), words


# ---- the Formula Retail notice line names what is not known, as T5 does (change of 2026-11-16) ------------------------
NOTICE_SILENT = (
    "On 1 June 2023 establishing a Formula Retail use in an NCT district needed neighbourhood "
    "notice, whether or not the use changed. The description does not say whether the business is part of a chain, "
    "so whether notice was needed is not established."
)
NOTICE_COUNT_MISSING = (
    "On 1 June 2023 establishing a Formula Retail use in an NCT district needed neighbourhood "
    "notice, whether or not the use changed. You answered that the business is part of a chain but not how many "
    "other locations it has. Planning Code § 303.1 counts a business as formula retail from eleven other "
    "locations, so whether notice was needed is not established."
)
# the same case where no intake answer gave the chain (an operator override): T5's own words, "The applicant says"
NOTICE_COUNT_MISSING_NOT_ANSWERED = (
    "On 1 June 2023 establishing a Formula Retail use in an NCT district needed neighbourhood "
    "notice, whether or not the use changed. The applicant says the business is part of a chain but not how many "
    "other locations it has. Planning Code § 303.1 counts a business as formula retail from eleven other "
    "locations, so whether notice was needed is not established."
)


def _notice(profile: BusinessProfile) -> tuple[str, list[str]]:
    d = determine(profile, NCT3, [], [], SITE_995, required_areas(profile), today=D(2023, 6, 1))
    changes = d.pathway.changes
    assert changes is not None
    return changes.neighbourhood_notice, [line.text for line in changes.neighbourhood_notice_lines]


def test_the_formula_retail_notice_line_when_the_description_is_silent_on_a_chain() -> None:
    answer, lines = _notice(BusinessProfile(business_type="restaurant", stories=["first"]))
    assert answer == "not_established"
    assert lines[-1] == NOTICE_SILENT


def test_the_formula_retail_notice_line_when_the_chain_answer_gives_no_count() -> None:
    """The applicant answered that the business is part of a chain, without the count: the line no longer says the
    description does not say whether it is a chain; it names the count, and § 303.1's eleven, as T5 does."""
    base = BusinessProfile(business_type="restaurant", stories=["first"])
    chain = apply_intake_answers(base, IntakeAnswers(part_of_chain=True)).normalized()
    assert concept_facts(chain).chain_count_missing
    answer, lines = _notice(chain)
    assert answer == "not_established"
    assert lines[-1] == NOTICE_COUNT_MISSING
    assert not any("does not say whether the business is part of a chain" in text for text in lines)
    # T5 words the same case the same way
    d = determine(chain, NCT3, [], [], SITE_995, required_areas(chain), today=D(2023, 6, 1))
    t5 = tg.by_id(d.pathway.triggers, "T5")
    assert any(line.rule_id == "T5.count_missing" for line in t5.lines)


def test_the_formula_retail_notice_line_for_a_chain_not_given_by_an_answer_says_the_applicant_says() -> None:
    """part_of_chain set without an intake answer (an operator override): the line never says "You answered", and
    uses T5's own words for the same case."""
    chain = BusinessProfile(business_type="restaurant", stories=["first"], part_of_chain=True)
    assert chain.intake_answered == [] and concept_facts(chain).chain_count_missing
    answer, lines = _notice(chain)
    assert answer == "not_established"
    assert lines[-1] == NOTICE_COUNT_MISSING_NOT_ANSWERED
    assert not any("You answered" in text for text in lines)
    d = determine(chain, NCT3, [], [], SITE_995, required_areas(chain), today=D(2023, 6, 1))
    t5 = tg.by_id(d.pathway.triggers, "T5")
    (count_line,) = [line for line in t5.lines if line.rule_id == "T5.count_missing"]
    assert count_line.text.startswith(
        "The applicant says the business is part of a chain but not how many other locations it has."
    )
    assert lines[-1].split(". ", 1)[1].startswith(count_line.text.split(". Planning")[0])


def test_the_formula_retail_notice_line_when_the_chain_answer_gives_a_count() -> None:
    base = BusinessProfile(business_type="restaurant", stories=["first"])
    eleven = apply_intake_answers(base, IntakeAnswers(part_of_chain=True, other_locations=11)).normalized()
    answer, lines = _notice(eleven)
    assert answer == "required"
    assert lines[-1].endswith(
        "you answered that the business is part of a chain with eleven or more other locations, so notice was "
        "required."
    )
    # ten other locations: not formula retail, so the notice turns on the use alone
    ten = apply_intake_answers(base, IntakeAnswers(part_of_chain=True, other_locations=10)).normalized()
    _, lines = _notice(ten)
    assert not any("Formula Retail" in text for text in lines)


# ---- 5. a cleared licence type points at the answer that settles it ---------------------------------------------------
NO_ALCOHOL_TEXT = "A restaurant, open until 10 pm"
NO_ALCOHOL_MODEL: dict[str, Any] = {
    "business_type": "restaurant",
    "serves_alcohol": False,
    "licence_type": "41",
    "closing_hour": "22:00",
}
NO_ALCOHOL_QUOTES = [("business_type", "A restaurant"), ("closing_hour", "open until 10 pm")]


def licence_type_questions(d: Determinations) -> list[tuple[str, str | None]]:
    """The open questions that name the licence type, or what is poured in its place."""
    names = (MISSING_PHRASES["licence_type"], MISSING_PHRASES["alcohol_served"])
    return [(q.question, q.intake_question) for q in d.open_questions if any(n in q.question for n in names)]


def test_a_cleared_licence_type_with_alcohol_not_established_points_at_the_liquor_licence_question() -> None:
    """Review round 2, #5: the model read Type 41 with no quote and no alcohol. The report asked "Not known: the
    licence type" with no question, though the liquor licence answer settles it."""
    profile, d = through_the_runner(
        NO_ALCOHOL_MODEL, NO_ALCOHOL_QUOTES, NO_ALCOHOL_TEXT, IntakeAnswers(stories=["first"])
    )
    assert profile.intake_cleared == {"licence_type": "41"} and not concept_facts(profile).serves_alcohol
    assert licence_type_questions(d) == [
        (
            "Not known: the licence type. The description does not state it, so the report does not assume it.",
            "liquor_licence",
        )
    ]
    # "No alcohol" settles it: nothing is asked about the licence type
    _, settled = through_the_runner(
        NO_ALCOHOL_MODEL,
        NO_ALCOHOL_QUOTES,
        NO_ALCOHOL_TEXT,
        IntakeAnswers(stories=["first"], liquor_licence="none"),
    )
    assert licence_type_questions(settled) == []
    # a licence: what is poured is then what the type turns on, and it is asked
    _, poured = through_the_runner(
        NO_ALCOHOL_MODEL,
        NO_ALCOHOL_QUOTES,
        NO_ALCOHOL_TEXT,
        IntakeAnswers(stories=["first"], liquor_licence="new"),
    )
    assert [asked for _, asked in licence_type_questions(poured)] == ["alcohol_served"]


def test_a_cleared_licence_type_with_alcohol_established_points_at_what_is_poured() -> None:
    """Alcohol is established and what is poured decides the type: the question on what is poured."""
    text = "Indian restaurant with an alcohol license, open until 10 pm"
    model = {**NO_ALCOHOL_MODEL, "serves_alcohol": True, "alcohol_type": "unknown"}
    quotes = [
        ("business_type", "Indian restaurant"),
        ("serves_alcohol", "alcohol license"),
        ("closing_hour", "open until 10 pm"),
    ]
    profile, d = through_the_runner(model, quotes, text, IntakeAnswers(stories=["first"]))
    concept = concept_facts(profile)
    assert profile.intake_cleared.get("licence_type") == "41" and concept.serves_alcohol
    assert [asked for _, asked in licence_type_questions(d)] == ["alcohol_served"]
    # the licence type itself, named for this concept, points at the same question
    assert _intake_question(MISSING_PHRASES["licence_type"], concept) == "alcohol_served"


def test_a_licence_type_no_answer_settles_points_at_no_question() -> None:
    """A hotel that pours spirits: what is poured does not decide its type, so no answer settles it and the
    question points at none (the first review's behaviour, kept); with the type cleared, the same."""
    hotel = BusinessProfile(
        business_type="hotel",
        serves_alcohol=True,
        alcohol_type="full_liquor",
        stories=["first"],
        intake_cleared={"licence_type": "47"},
    )
    d = report(hotel)
    assert [asked for _, asked in licence_type_questions(d)] == [None]
    assert "the licence type" in licence_type_questions(d)[0][0]
    assert _intake_question(MISSING_PHRASES["licence_type"], concept_facts(hotel)) is None
    # any other phrase reads as before, whatever the concept
    assert _intake_question(MISSING_PHRASES["stories"], concept_facts(hotel)) == "stories"


def test_an_answered_no_alcohol_is_never_asked_again_for_the_licence_type() -> None:
    """Third pass: a zero-proof bar that answered "No alcohol" was sent back to the liquor licence question, the
    one it had answered, for "Not known: the licence type". That pass only took the question off the open
    question (it still asked for the licence type, pointing at nothing), because the rules read every bar as a
    Bar. Full intent, since 2026-11-16 (pathway rule 1b): a business that serves no alcohol is not a Bar (Planning
    Code § 102), so there is no alcohol row and nothing about a licence is asked; the report asks what kind of
    food or drink service it is instead, and assumes none."""
    profile, d = through_the_runner(
        {"business_type": "bar", "stories": ["first"]},
        [("business_type", "zero-proof cocktail bar"), ("stories", "ground floor")],
        "A zero-proof cocktail bar on the ground floor",
        IntakeAnswers(liquor_licence="none"),
    )
    concept = concept_facts(profile)
    assert not concept.serves_alcohol
    # nothing about the licence is asked, by any question or none
    assert licence_type_questions(d) == []
    assert not [q for q in d.open_questions if q.intake_question == "liquor_licence"]
    # no alcohol row, and the business is not read as a Bar, nor as anything else
    assert "alcohol" not in {r.area for r in d.rows}
    assert concept.planning_uses.value == () and d.pathway.use == "not_covered"
    assert "Bar" not in d.pathway.use_label
    # the report asks what kind of food or drink service it is, by the categories the rules know
    food = MISSING_PHRASES["food_service"]
    assert "a Restaurant" in food and "a Limited Restaurant" in food and "another use" in food
    asked = [q for q in d.open_questions if food in q.question]
    assert len(asked) == 1 and asked[0].question.startswith(f"Not known: {food}. Needed for: zoning and use")
    assert row(d, "zoning_use").status == INSUFFICIENT and food in row(d, "zoning_use").missing_inputs
    t1 = tg.by_id(d.pathway.triggers, "T1")
    assert (t1.control, t1.missing_inputs) == ("not_decided", [food])
    assert t1.lines[0].code_section == "Planning Code § 102 (Bar)"
    assert "you answered that it serves no alcohol" in t1.lines[0].text


def test_a_description_that_says_the_bar_serves_no_alcohol_is_not_a_bar() -> None:
    """The same with no answer: the description's own words say no alcohol ("zero-proof"). The model's reading
    that a "zero-proof cocktail bar" serves alcohol is not stated (the words "zero-proof" modify are not alcohol
    served), and the cleared reading is not "not stated" either: the text states the "no"."""
    model = {"business_type": "bar", "stories": ["first"], "serves_alcohol": True}
    quotes = [
        ("business_type", "zero-proof cocktail bar"),
        ("serves_alcohol", "zero-proof cocktail bar"),
        ("stories", "ground floor"),
    ]
    profile, d = through_the_runner(
        model, quotes, "A zero-proof cocktail bar on the ground floor", IntakeAnswers()
    )
    assert profile.no_alcohol_stated and not profile.serves_alcohol
    assert "serves_alcohol" not in profile.intake_cleared
    assert "alcohol" not in {r.area for r in d.rows}
    assert d.pathway.use == "not_covered"
    t1 = tg.by_id(d.pathway.triggers, "T1")
    assert t1.lines[0].text.startswith("The business is described as a bar that serves no alcohol.")
    assert t1.missing_inputs == [MISSING_PHRASES["food_service"]]


@pytest.mark.parametrize(
    "text",
    [
        "An alcohol-free bar on the ground floor",
        "A non-alcoholic cocktail bar on the ground floor",
        "A sober bar on the ground floor",
        "A bar with no alcohol on the ground floor",
    ],
)
def test_other_words_for_no_alcohol_say_the_same(text: str) -> None:
    words = text.removeprefix("An ").removeprefix("A ").removesuffix(" on the ground floor")
    profile, d = through_the_runner(
        {"business_type": "bar", "stories": ["first"]},
        [("business_type", words), ("stories", "ground floor")],
        text,
        IntakeAnswers(),
    )
    assert profile.no_alcohol_stated, text
    assert "alcohol" not in {r.area for r in d.rows}, text


@pytest.mark.parametrize(
    "text",
    [
        "A non-alcoholic beer and wine bar on the ground floor",
        "A zero-proof craft beer bar on the ground floor",
        "An alcohol-free wine and cocktail lounge on the ground floor",
    ],
)
def test_the_whole_phrase_a_no_alcohol_word_modifies_states_no_alcohol(text: str) -> None:
    """Review of 2026-11-16: "a non-alcoholic beer and wine bar" was read as a Bar pouring beer and wine (only two
    words after "non-alcoholic" were left out, so "wine bar" stayed). The model's reading of alcohol served, and of
    beer and wine poured, quoted from those words, is not stated: the whole phrase the words modify, up to the
    business noun, serves no alcohol."""
    words = text.removeprefix("An ").removeprefix("A ").removesuffix(" on the ground floor")
    model = {
        "business_type": "bar",
        "stories": ["first"],
        "serves_alcohol": True,
        "alcohol_type": "beer_wine",
    }
    quotes = [
        ("business_type", words),
        ("serves_alcohol", words),
        ("alcohol_type", words),
        ("stories", "ground floor"),
    ]
    profile, d = through_the_runner(model, quotes, text, IntakeAnswers())
    assert profile.no_alcohol_stated and not profile.serves_alcohol, text
    assert profile.alcohol_type == "none", text
    assert "alcohol" not in {r.area for r in d.rows}, text
    assert d.pathway.use == "not_covered", text
    assert not [q for q in d.open_questions if q.intake_question == "liquor_licence"], text
    assert MISSING_PHRASES["food_service"] in tg.by_id(d.pathway.triggers, "T1").missing_inputs, text


def test_a_mocktail_bar_that_answered_no_alcohol_is_not_a_bar() -> None:
    profile, d = through_the_runner(
        {"business_type": "bar", "stories": ["first"]},
        [("business_type", "mocktail bar"), ("stories", "ground floor")],
        "A mocktail bar on the ground floor",
        IntakeAnswers(liquor_licence="none"),
    )
    assert not profile.no_alcohol_stated  # the description does not state it; the answer does
    assert "alcohol" not in {r.area for r in d.rows}
    assert d.pathway.use == "not_covered"


@pytest.mark.parametrize(
    ("text", "quotes", "answers"),
    [
        # silent on alcohol: a Bar sells alcohol by its definition, so silence is never "no alcohol"
        ("A cocktail bar on the ground floor", [("business_type", "cocktail bar")], IntakeAnswers()),
        # "no bar" is not "no alcohol"
        (
            "A cocktail bar, no bar stools, on the ground floor",
            [("business_type", "cocktail bar")],
            IntakeAnswers(),
        ),
        # the text says zero-proof but also pours wine: alcohol is served, and it is a Bar
        (
            "A zero-proof bar that also serves wine, on the ground floor",
            [("business_type", "zero-proof bar"), ("serves_alcohol", "serves wine")],
            IntakeAnswers(),
        ),
        # an answer that alcohol is served wins over the description's "zero-proof"
        (
            "A zero-proof cocktail bar on the ground floor",
            [("business_type", "zero-proof cocktail bar")],
            IntakeAnswers(liquor_licence="new"),
        ),
        # "sober-curious" does not say no alcohol is served (such bars often pour low-alcohol drinks)
        (
            "A sober-curious bar on the ground floor",
            [("business_type", "sober-curious bar"), ("serves_alcohol", "sober-curious bar")],
            IntakeAnswers(),
        ),
        # zero-proof and low-ABV: the low-alcohol drinks are alcohol served
        (
            "A zero-proof and low-ABV cocktail bar on the ground floor",
            [
                ("business_type", "zero-proof and low-ABV cocktail bar"),
                ("serves_alcohol", "zero-proof and low-ABV cocktail bar"),
            ],
            IntakeAnswers(),
        ),
        # what follows the phrase the no-alcohol words modify is still read: real cocktails are alcohol
        (
            "A bar with non-alcoholic beer and wine and real cocktails, on the ground floor",
            [("business_type", "bar"), ("serves_alcohol", "non-alcoholic beer and wine and real cocktails")],
            IntakeAnswers(),
        ),
        # decided 2026-11-16: "mocktail" names a drink served, not that the business serves no alcohol, so a
        # mocktail bar that answered nothing is still a Bar (the "No alcohol" answer settles it: see below)
        ("A mocktail bar on the ground floor", [("business_type", "mocktail bar")], IntakeAnswers()),
    ],
)
def test_a_bar_that_may_serve_alcohol_is_still_a_bar(
    text: str, quotes: list[tuple[str, str]], answers: IntakeAnswers
) -> None:
    model: dict[str, Any] = {"business_type": "bar", "stories": ["first"]}
    if any(field == "serves_alcohol" for field, _ in quotes):
        model["serves_alcohol"] = True
    _, d = through_the_runner(model, [*quotes, ("stories", "ground floor")], text, answers)
    assert d.pathway.use == "bar", text
    assert "alcohol" in {r.area for r in d.rows}, text
    assert MISSING_PHRASES["food_service"] not in " ".join(q.question for q in d.open_questions)
