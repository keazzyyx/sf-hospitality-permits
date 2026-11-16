"""The eleven trigger rules (app.memo.triggers), against the bundled dated control data.

All synthetic except three files read as data: the dated control data itself, and backtest/inputs.json with
backtest/triggers.json (the 40 hand-entered cases). No database, no model, no network, no clock.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import random
import re
import string
from pathlib import Path
from typing import Any

import pytest
from precedent.models import Overlay
from precedent.store.base import ZoningInfo

from app.memo import controls
from app.memo import triggers as tg
from app.memo.facts import (
    MISSING_PHRASES,
    ConceptFacts,
    PriorDecision,
    SiteFacts,
    SiteLicence,
    concept_facts,
    concept_facts_from_facts,
    profile_from_facts,
)
from app.models.memo import TRIGGER_LABELS, PlanningUse, RuleLine, TriggerFinding

D = dt.date
TODAY = D(2026, 11, 10)
NOW = dt.datetime(2026, 11, 10, tzinfo=dt.UTC)
ROOT = Path(__file__).resolve().parents[3]
CHAIN = MISSING_PHRASES["formula_retail"]
LICENCE = MISSING_PHRASES["licence_type"]
POURS = MISSING_PHRASES["alcohol_served"]
LAST_USE = MISSING_PHRASES["existing_use_stated"]
STORY = MISSING_PHRASES["stories"]
NOT_CARRIED = "the rule table does not carry this zoning district"


# ---- builders ---------------------------------------------------------------------------------------------
def facts(**given: Any) -> ConceptFacts:
    """Concept facts from the fact names of backtest/inputs.json; anything not given is not stated."""
    return concept_facts_from_facts(given)


def site(
    on: dt.date,
    *,
    existing_use: PlanningUse | None = None,
    licences: tuple[str, ...] = (),
    conditional_use_on: dt.date | None = None,
) -> SiteFacts:
    lines = (
        (RuleLine(rule_id="zoning.existing_use", text="on file", code_section=None, citations=["app:abc:1"]),)
        if existing_use
        else ()
    )
    prior = (
        (
            PriorDecision(
                record_id="datasf_planning:2019-000111CUA",
                date=conditional_use_on,
                description="Conditional Use for a restaurant",
                permit_type="Conditional Use Authorization",
                conditional_use=True,
                outcome="approved_with_conditions",
                citation="app:datasf_planning:2019-000111CUA",
                source_url="https://example.org/cua",
            ),
        )
        if conditional_use_on
        else ()
    )
    return SiteFacts(
        rules_date=on,
        licences=tuple(
            SiteLicence(f"abc:{i}", t, None, None, f"app:abc:{i}", "https://example.org/abc")
            for i, t in enumerate(licences, 1)
        ),
        existing_use=existing_use,
        existing_use_lines=lines,
        prior_decisions=prior,
    )


def zoning(district: str | None, *, bar: str = "unknown", restaurant: str = "unknown") -> ZoningInfo | None:
    if district is None:
        return None
    return ZoningInfo(
        district=district,
        name=district,
        code_section="Planning Code § 700 (Zoning Control Table)",
        bar_permission=bar,
        restaurant_permission=restaurant,
        rules="",
        source_url=f"https://example.org/zoning/{district}",
    )


def overlay(
    overlay_id: str,
    name: str,
    section: str,
    *,
    kind: str = "special_use_district",
    bar: str = "unknown",
    restaurant: str = "unknown",
) -> Overlay:
    return Overlay.model_validate(
        {
            "id": overlay_id,
            "kind": kind,
            "name": name,
            "rules": "",
            "code_section": section,
            "bar_permission": bar,
            "restaurant_permission": restaurant,
            "source": "static",
            "source_url": f"https://example.org/overlay/{overlay_id}",
            "fetched_at": NOW,
        }
    )


# The overlays as the store holds them (names and sections read from the local overlays table).
MISSION = overlay(
    "datasf_sud:mission_alcohol_restrict",
    "Mission Alcoholic Beverage Special Use District",
    "Planning Code § 249.60 (§ 781.8 cross-references it)",
    kind="alcohol_sud",
    bar="conditional",
)
HAIGHT = overlay(
    "datasf_sud:haight_street_alcohol_restricted_use",
    "Haight Street Alcohol Restricted Use Subdistrict",
    "Planning Code § 781.9",
    kind="alcohol_sud",
)
LOWER_HAIGHT = overlay(
    "datasf_sud:lower_haight_alcohol_restrict",
    "Lower Haight Street Alcohol Restricted Use District",
    "Planning Code § 784",
    kind="alcohol_sud",
)
THIRD = overlay(
    "datasf_sud:3rd_st_alcohol_restrict",
    "Third Street Alcohol Restricted Use District",
    "Planning Code § 249.62 (§ 782 cross-references it)",
    kind="alcohol_sud",
    bar="prohibited",
)
SOMA = overlay("datasf_sud:youth_and_family_zone", "Youth and Family Zone", "Planning Code § 249.38")
CALLE24 = overlay("datasf_sud:calle_24_sud", "Calle 24 Special Use District", "Planning Code § 249.59")
CENTRAL_SOMA = overlay("datasf_sud:central_soma", "Central SoMa", "Planning Code § 249.78")
FRINGE = overlay(
    "datasf_sud:fringe", "Fringe Financial Service RUD", "Planning Code § 249.35 (via § 781.9(d))"
)


def run(
    district: str | None,
    on: dt.date,
    *overlays: Overlay,
    today: dt.date = TODAY,
    at: SiteFacts | None = None,
    zone: ZoningInfo | None = None,
    **given: Any,
) -> dict[str, TriggerFinding]:
    found = tg.evaluate(
        facts(**given),
        at or site(on),
        zone or zoning(district),
        list(overlays),
        rules_date=on,
        today=today,
    )
    assert [f.rule_id for f in found] == list(tg.ORDER)
    return {f.rule_id: f for f in found}


def text_of(finding: TriggerFinding) -> str:
    return " ".join(line.text for line in finding.lines)


def ids(finding: TriggerFinding) -> list[str]:
    return [line.rule_id for line in finding.lines]


@pytest.fixture(scope="module")
def raw() -> dict[str, Any]:
    return json.loads(controls.DATA_PATH.read_text(encoding="utf-8"))


# ---- the shape of the answer ----------------------------------------------------------------------------------
def test_always_eleven_findings_in_order_each_with_a_line_and_its_label() -> None:
    for given in ({}, {"business_type": "bar", "planning_use": "bar"}, {"business_type": "hotel"}):
        for district in ("NCD-POLK", "NO-SUCH-DISTRICT", None):
            found = run(district, D(2024, 6, 1), **given)
            assert list(found) == list(tg.ORDER)
            for rule_id, f in found.items():
                assert f.family == tg.FAMILIES[rule_id]
                assert f.label == TRIGGER_LABELS[f.family]
                assert f.lines, rule_id
                for line in f.lines:
                    assert line.rule_id and line.text.strip()
                    assert line.text[0] == line.text[0].upper()
                    assert "{" not in line.text and "None" not in line.text, line.text
                if f.control == "not_decided":
                    assert f.missing_inputs, rule_id
                if f.control == "does_not_apply":
                    assert not f.missing_inputs


def test_a_row_line_takes_its_section_url_and_citation_from_the_data_entry() -> None:
    found = run("NCD-POLK", D(2023, 2, 1), business_type="bar", planning_use="bar", story="first")
    cell = found["T1"].lines[0]
    source = controls.use_control("NCD-POLK", "bar", "first", D(2023, 2, 1)).source
    assert cell.rule_id == "T1.cell"
    assert cell.code_section == source.section == "Planning Code § 723"
    assert cell.source_url == source.source_url
    assert cell.citations == ["zoning:NCD-POLK"]
    assert source.in_force_text in cell.text


# ---- T1: new use control ------------------------------------------------------------------------------------------
def test_t1_every_control_of_a_cell() -> None:
    on = D(2024, 6, 1)
    assert run("NCD-POLK", on, planning_use="restaurant", story="first")["T1"].control == "principal"
    assert run("NCD-POLK", on, planning_use="bar", story="first")["T1"].control == "conditional"
    assert run("NCD-POLK", on, planning_use="bar", story="second")["T1"].control == "not_permitted"
    # several stories: the most severe cell
    both = run("NCD-POLK", on, planning_use="bar", story=["first", "second"])["T1"]
    assert both.control == "not_permitted"
    assert ids(both).count("T1.cell") == 2


# the user's decision of 2026-11-12: "MISSING STORY: always 'Insufficient information', naming it. Never default to
# the first story."
NO_STORY_LINE = (
    "Zoning district NCD-POLK: the table sets a different control for a Bar on different stories. Which story the "
    "business is on is not given, so no story is assumed and this is not decided until it is"
)


def test_t1_no_story_given_is_not_decided_and_names_the_story() -> None:
    # NCD-POLK, 2024-06-01: a Bar is conditional on the first story and not permitted on the second; neither is
    # assumed
    found = run("NCD-POLK", D(2024, 6, 1), planning_use="bar")["T1"]
    assert found.control == "not_decided"
    assert found.missing_inputs == [STORY]
    assert ids(found) == ["T1.story"]
    assert text_of(found).startswith(NO_STORY_LINE)
    assert "first story" not in text_of(found).lower()
    assert found.lines[0].code_section and found.lines[0].citations == ["zoning:NCD-POLK"]
    # the first story would already need a Conditional Use; with no story it is still not decided
    restaurant = run("NCD-POLK", D(2024, 6, 1), planning_use="restaurant")["T1"]
    assert restaurant.control == "not_decided" and restaurant.missing_inputs == [STORY]


def test_t1_no_story_given_and_the_table_reads_the_same_on_every_story() -> None:
    # every column is read: when they all read the same the story does not change the answer, and no story is
    # assumed to say so
    every = "The table reads the same for {} on every story, so the story does not change this."
    pacific = run("NCD-PACIFIC", D(2026, 11, 10), planning_use="bar")["T1"]
    assert pacific.control == "not_permitted" and pacific.missing_inputs == []
    assert ids(pacific) == ["T1.cell", "T1.cell", "T1.cell", "T1.story", "T1.historic"]
    assert every.format("a Bar") in text_of(pacific)
    for story in ("first story", "second story", "third story or above"):
        assert f"a Bar on the {story} is not permitted" in text_of(pacific)
    # RH-2: every story reads the same and leaves the same rows of the table open; the story is not named
    rh2 = run("RH-2", D(2026, 11, 10), planning_use="restaurant")["T1"]
    assert rh2.control == "not_decided" and STORY not in rh2.missing_inputs and len(rh2.missing_inputs) == 1
    assert every.format("a Restaurant") in text_of(rh2)
    c3 = run("C-3-G", D(2026, 11, 10), planning_use="bar")["T1"]
    assert c3.control == "principal" and c3.missing_inputs == []
    assert every.format("a Bar") in text_of(c3)
    # Nighttime Entertainment is a conditional use on every story in RH DTR: conditional, the story not named
    club = run("RH DTR", D(2026, 11, 10), planning_use="nighttime_entertainment")["T6"]
    assert club.control == "conditional" and STORY not in club.missing_inputs
    # the third story differs (NCT-3: a Restaurant is principal on the first two, not permitted above): not decided
    nct3 = run("NCT-3", D(2026, 11, 10), planning_use="restaurant")["T1"]
    assert nct3.control == "not_decided" and nct3.missing_inputs == [STORY]


def test_t1_a_stated_first_story_is_read_as_before() -> None:
    stated = run("NCD-POLK", D(2024, 6, 1), planning_use="bar", story="first")["T1"]
    assert stated.control == "conditional" and stated.missing_inputs == []
    assert ids(stated) == ["T1.cell"]
    assert text_of(stated).startswith(
        "Zoning district NCD-POLK: a Bar on the first story is a conditional use"
    )
    assert "T1.story" not in ids(stated)


def test_no_story_given_t3_t6_and_the_first_story_rules_are_not_decided_naming_it() -> None:
    on = D(2024, 6, 1)
    # T3: a Bar that stays and is intensified, read as new on no story given
    t3 = run(
        "NCD-POLK", on, planning_use="bar", existing_use_stated="bar", changes_existing_business="intensify"
    )
    assert t3["T3"].control == "not_decided" and STORY in t3["T3"].missing_inputs
    # T6: Nighttime Entertainment, and entertainment of no stated kind (the kind and the story are both named)
    club = run("NCD-POLK", on, planning_use="nighttime_entertainment")["T6"]
    assert club.control == "not_decided" and club.missing_inputs == [STORY]
    live = run("NCD-POLK", on, planning_use="bar", live_entertainment=True)["T6"]
    assert live.control == "not_decided"
    assert live.missing_inputs == [MISSING_PHRASES["entertainment_kind"], STORY]
    # T2: North Beach's prior-use rule is for the First Story only
    nb = run("NCD-NORTH BEACH", D(2024, 6, 1), planning_use="restaurant", existing_use_stated="bar")["T2"]
    assert nb.control == "not_decided" and STORY in nb.missing_inputs
    assert any(i.endswith("north_beach.prior_use.restaurant") for i in ids(nb))
    assert "The rule is for the First Story. Which story the business is on is not given" in text_of(nb)
    # stated on the second story the rule does not reach, as before
    second = run(
        "NCD-NORTH BEACH", D(2024, 6, 1), planning_use="restaurant", existing_use_stated="bar", story="second"
    )["T2"]
    assert second.control == "does_not_apply"


def test_t1_basement_is_read_as_the_first_story_and_says_so() -> None:
    found = run("NCD-POLK", D(2024, 6, 1), planning_use="bar", story="basement")["T1"]
    assert found.control == "conditional"
    assert "T1.basement" in ids(found)


def test_t1_a_governed_row_names_the_row_that_governs() -> None:
    found = run("C-2", D(2024, 6, 1), planning_use="restaurant", story="first")["T1"]
    assert found.control == "principal"
    assert 'the row "Retail Sales and Service Uses*" governs' in text_of(found)


def test_t1_no_use_known_is_not_decided() -> None:
    unknown = run("NCD-POLK", D(2024, 6, 1))["T1"]
    assert unknown.control == "not_decided"
    assert unknown.missing_inputs == [MISSING_PHRASES["planning_uses"]]
    hotel = run("NCD-POLK", D(2024, 6, 1), business_type="hotel")["T1"]
    assert hotel.control == "not_decided"
    assert hotel.missing_inputs == [tg.NOT_KNOWN["use_not_covered"]]


def test_t1_leaves_nighttime_entertainment_to_t6() -> None:
    found = run("NCD-POLK", D(2023, 2, 1), planning_use="nighttime_entertainment", story="first")
    assert found["T1"].control == "does_not_apply"
    assert ids(found["T1"]) == ["T1.entertainment"]
    assert found["T6"].control == "conditional"


@pytest.mark.parametrize("district", ["CVR", "CCB", "CRNC"])
def test_t1_chinatown_restaurant_either_side_of_2024_01_14(district: str) -> None:
    before = run(district, D(2024, 1, 13), planning_use="restaurant", story="first")["T1"]
    assert before.control == "conditional"
    assert before.differs_today
    assert before.in_force_from is None and before.ordinance is None
    assert (
        "This control changed on 2024-01-14 (Ord. 249-23, File No. 230701); today it reads principally "
        "permitted." in text_of(before)
    )
    after = run(district, D(2024, 1, 14), planning_use="restaurant", story="first")["T1"]
    assert after.control == "principal"
    assert not after.differs_today
    assert after.in_force_from == "2024-01-14"
    assert after.ordinance == "Ord. 249-23, File No. 230701"
    assert "T1.differs" not in ids(after)


def test_t1_haight_bar_not_permitted_then_conditional() -> None:
    before = run("NCD-HAIGHT", D(2024, 1, 13), planning_use="bar", story="first")["T1"]
    after = run("NCD-HAIGHT", D(2024, 1, 14), planning_use="bar", story="first")["T1"]
    assert (before.control, after.control) == ("not_permitted", "conditional")
    assert before.differs_today and not after.differs_today


def test_t1_differs_today_compares_with_the_date_passed_in() -> None:
    same_day = run("CVR", D(2023, 6, 1), planning_use="restaurant", story="first", today=D(2023, 6, 1))["T1"]
    assert same_day.control == "conditional" and not same_day.differs_today
    earlier = run("CVR", D(2023, 6, 1), planning_use="restaurant", story="first", today=D(2024, 1, 13))["T1"]
    assert not earlier.differs_today


def test_t1_a_use_that_exists_and_continues_is_t3s_ground() -> None:
    stays = run(
        "NCD-POLK",
        D(2024, 6, 1),
        planning_use="bar",
        existing_use_stated="bar",
        changes_existing_business="none",
        story="first",
    )
    assert stays["T1"].control == "does_not_apply"
    assert ids(stays["T1"]) == ["T1.continues"]
    # shown by records and the same use proposed
    shown = run(
        "NCD-POLK",
        D(2024, 6, 1),
        planning_use="bar",
        story="first",
        at=site(D(2024, 6, 1), existing_use="bar"),
    )
    assert shown["T1"].control == "does_not_apply"
    # a stated last use alone does not make the use continue, and does not make it new either: whether that
    # business stays is the missing input (corrected expectation: this read "conditional" before the review)
    new = run("NCD-POLK", D(2024, 6, 1), planning_use="bar", existing_use_stated="bar", story="first")
    assert new["T1"].control == "not_decided"
    assert new["T1"].missing_inputs == [MISSING_PHRASES["changes_existing_business"]]
    assert ids(new["T1"]) == ["T1.maybe_continues"]
    other = run("NCD-POLK", D(2024, 6, 1), planning_use="bar", existing_use_stated="retail", story="first")
    assert other["T1"].control == "conditional"


def test_t1_bayview_bar_licence_exception_and_its_dates() -> None:
    bar = {
        "business_type": "bar",
        "planning_use": "bar",
        "story": "first",
        "alcohol_transaction": "new_licence",
    }
    # until 2025-04-06 the cell is P and the Third Street district's rule is read by T4
    early = run("NCD-BAYVIEW", D(2025, 4, 6), THIRD, **bar, licence_type="42")
    assert early["T1"].control == "principal"
    assert "T1.override" in ids(early["T1"])
    assert early["T4"].control == "not_permitted"
    # ... and without the overlay the rules cannot place the address in that district
    unplaced = run("NCD-BAYVIEW", D(2025, 4, 6), **bar, licence_type="42")["T1"]
    assert unplaced.control == "not_decided"
    assert unplaced.missing_inputs == [tg.NOT_KNOWN["third_street"]]
    # from 2025-04-07 the cell is NP, conditional with Type 42
    with_42 = run("NCD-BAYVIEW", D(2025, 4, 7), THIRD, **bar, licence_type="42")["T1"]
    assert with_42.control == "conditional"
    assert with_42.in_force_from == "2025-04-07" and with_42.ordinance == "Ord. 21-25, File No. 240932"
    assert "a Bar with an ABC Type 42 licence is a conditional use" in text_of(with_42)
    with_48 = run("NCD-BAYVIEW", D(2025, 4, 7), THIRD, **bar, licence_type="48")["T1"]
    assert with_48.control == "not_permitted"
    # a Bar that serves alcohol without saying what: the exception turns on the type, and what is poured is
    # named (never read as Type 42, nor as no alcohol)
    no_type = run("NCD-BAYVIEW", D(2025, 4, 7), THIRD, **bar, serves_alcohol=True)["T1"]
    assert no_type.control == "not_decided" and no_type.missing_inputs == [POURS]
    # the exception reaches the first and second story only
    third_story = run(
        "NCD-BAYVIEW", D(2025, 4, 7), THIRD, **{**bar, "story": "third_or_above"}, licence_type="42"
    )
    assert third_story["T1"].control == "not_permitted"


def test_t1_bayview_exceptions_for_an_establishment_that_already_existed() -> None:
    bar = {"business_type": "bar", "planning_use": "bar", "story": "first", "licence_type": "48"}
    new = run("NCD-BAYVIEW", D(2026, 9, 1), THIRD, **bar, alcohol_transaction="new_licence")["T1"]
    assert new.control == "not_permitted"  # a new licence is not an establishment that already existed
    moved = run("NCD-BAYVIEW", D(2026, 9, 1), THIRD, **bar, alcohol_transaction="premises_transfer")["T1"]
    assert moved.control == "not_decided"
    assert moved.missing_inputs == [tg.NOT_KNOWN["pre_existing_bar"]]
    before = run("NCD-BAYVIEW", D(2026, 8, 22), THIRD, **bar, alcohol_transaction="premises_transfer")["T1"]
    assert before.control == "not_permitted"


def test_t1_a_control_for_part_of_a_district_is_not_decided_and_named() -> None:
    bar = run("NC-1", D(2024, 6, 1), planning_use="bar", story="first")["T1"]
    assert bar.control == "not_decided"
    assert bar.missing_inputs == [
        "whether the address is in this part of the district: the area bounded by the Pacific Ocean "
        "shoreline, Lincoln Way, 17th Avenue, Judah Street, 19th Avenue and Sloat Boulevard (the note gives "
        "the full bounds)"
    ]
    assert "Table 710, Note 6" in text_of(bar)
    # the sub-area control is for the first story: the second-story cell stands as printed
    assert run("NC-1", D(2024, 6, 1), planning_use="bar", story="second")["T1"].control == "not_permitted"
    # Taraval Street Restaurant Subdistrict: conditional there until 2024-01-13, struck from the note after
    # (corrected: without an overlay at the point the address is outside it; the overlay places it, § 781.1)
    from tests.test_triggers_review import TARAVAL

    before = run("NC-2", D(2024, 1, 13), TARAVAL, planning_use="restaurant", story="first")["T1"]
    after = run("NC-2", D(2024, 1, 14), TARAVAL, planning_use="restaurant", story="first")["T1"]
    assert (before.control, after.control) == ("conditional", "principal")
    assert before.differs_today
    assert "This control changed on 2024-01-14 (Ord. 249-23, File No. 230701)" in text_of(before)
    outside = run("NC-2", D(2024, 1, 13), planning_use="restaurant", story="first")["T1"]
    assert outside.control == "principal"


def test_t1_other_rows_of_the_table_that_could_govern() -> None:
    found = run("RM-3", D(2024, 6, 1), planning_use="restaurant", story="first")["T1"]
    assert found.control == "not_decided"
    assert found.missing_inputs == [
        "whether the use falls under one of these rows of the table: Limited Corner Commercial Uses (§ 231) "
        "and Limited Commercial Uses (§§ 186, 186.3)"
    ]
    # RH-2: the § 186 row on every date, and the § 231 row from 2024-01-14 (corrected expectation: this read
    # "not_permitted" before the review; the data's note records both rows)
    rh2 = run("RH-2", D(2024, 6, 1), planning_use="restaurant", story="first")["T1"]
    assert rh2.control == "not_decided"
    assert rh2.missing_inputs == [
        "whether the use falls under one of these rows of the table: Limited Corner Commercial Uses (§ 231) "
        "and Limited Commercial Uses (§ 186)"
    ]


# ---- T2: special district use control --------------------------------------------------------------------------------
def test_t2_no_special_district_does_not_apply() -> None:
    found = run("NCD-POLK", D(2024, 6, 1), planning_use="restaurant")["T2"]
    assert found.control == "does_not_apply" and ids(found) == ["T2.none"]


@pytest.mark.parametrize("district", ["NCT-MISSION", "NCT-24TH-MISSION"])
def test_t2_mission_restaurant_inside_the_sub_area(district: str) -> None:
    found = run(district, D(2023, 6, 1), MISSION, planning_use="restaurant", story="first")["T2"]
    assert found.control == "conditional"
    line = next(line for line in found.lines if line.rule_id == "T2:mission.restaurant_cu_sub_area")
    assert line.code_section == "Planning Code § 249.60(f)(1)"
    assert line.citations == [f"overlay:{MISSION.id}"]
    assert line.source_url and "249.60" in line.source_url
    assert f"Zoning district {district} lies inside that sub-area" in line.text


def test_t2_mission_restaurant_elsewhere_in_the_district_code_and_practice_differ() -> None:
    found = run("NCT-VALENCIA", D(2023, 6, 1), MISSION, planning_use="restaurant", story="first")
    assert found["T2"].control == "code_and_practice_differ"
    assert not found["T2"].missing_inputs
    assert "the Code and Planning practice differ here" in text_of(found["T2"])
    assert found["T1"].control == "principal"
    outcome = tg.zoning_outcome([found["T1"], found["T2"]])
    assert (outcome.status, outcome.status_note) == ("further_review", "Code and Planning practice differ")
    # without alcohol too: (f)(1) reaches every Restaurant
    assert "T2:mission.restaurant_cu_sub_area" in ids(found["T2"])


def test_t2_mission_new_bar_and_limited_restaurant() -> None:
    bar = run("NCT-VALENCIA", D(2023, 6, 1), MISSION, planning_use="bar", story="first")["T2"]
    assert bar.control == "conditional"
    assert ids(bar) == ["T2:mission.new_or_relocated_bar"]
    cafe = run("NCT-MISSION", D(2023, 6, 1), MISSION, planning_use="limited_restaurant")["T2"]
    assert cafe.control == "does_not_apply" and ids(cafe) == ["T2.no_rule"]


def test_t2_is_not_applied_to_a_use_that_continues() -> None:
    found = run(
        "NCT-MISSION",
        D(2023, 6, 1),
        MISSION,
        planning_use="restaurant",
        existing_use_stated="restaurant",
        changes_existing_business="none",
    )["T2"]
    assert found.control == "does_not_apply"
    assert "already exists at this address and continues" in text_of(found)


def test_t2_soma_youth_and_family_either_side_of_the_renumbering() -> None:
    before = run("MUR", D(2023, 6, 2), SOMA, planning_use="restaurant", story="first")["T2"]
    after = run("MUR", D(2023, 6, 3), SOMA, planning_use="restaurant", story="first")["T2"]
    assert before.control == after.control == "conditional"
    assert before.lines[0].code_section == "Planning Code § 249.40A(c)(1)(A)(v)"
    assert after.lines[0].code_section == "Planning Code § 249.38(c)(1)(A)(v)"
    assert after.in_force_from == "2023-06-03" and after.ordinance == "Ord. 70-23, File No. 220340"
    assert not before.differs_today
    assert run("MUR", D(2024, 6, 1), SOMA, planning_use="bar")["T2"].control == "conditional"
    assert (
        run("MUR", D(2024, 6, 1), SOMA, planning_use="nighttime_entertainment")["T2"].control == "conditional"
    )
    cafe = run("MUR", D(2024, 6, 1), SOMA, planning_use="limited_restaurant")["T2"]
    assert cafe.control == "principal"
    assert "This rule asks for nothing here" in text_of(cafe)


def test_t2_north_beach_prior_use_rule() -> None:
    restaurant = {"planning_use": "restaurant", "story": "first"}
    on = D(2024, 6, 1)
    # a Bar space qualifies for a Restaurant (corrected: the case read a former Restaurant before the review;
    # the same use is now the proviso of the rule, see the review tests)
    qualifies = run("NCD-NORTH BEACH", on, **restaurant, existing_use_stated=["bar", "vacant"])["T2"]
    assert qualifies.control == "conditional"
    assert qualifies.lines[0].citations == ["zoning:NCD-NORTH BEACH"]
    assert qualifies.lines[0].code_section == "Planning Code § 780.3(c)(1), (c)(1)(B)"
    retail = run("NCD-NORTH BEACH", on, **restaurant, existing_use_stated="retail")["T2"]
    assert retail.control == "not_permitted"
    assert "a retail use, which does not qualify" in text_of(retail)
    unknown = run("NCD-NORTH BEACH", on, **restaurant, existing_use_stated="vacant")["T2"]
    assert unknown.control == "not_decided" and unknown.missing_inputs == [LAST_USE]
    # the records can show the last use
    shown = run(
        "NCD-NORTH BEACH", on, planning_use="restaurant", story="first", at=site(on, existing_use="bar")
    )["T2"]
    assert shown.control == "conditional"
    # a Bar only in a space last occupied by a Bar
    bar = run("NCD-NORTH BEACH", on, planning_use="bar", story="first", existing_use_stated="restaurant")[
        "T2"
    ]
    assert bar.control == "not_permitted"
    # the rule is for the First Story
    upstairs = run(
        "NCD-NORTH BEACH", on, planning_use="restaurant", story="second", existing_use_stated="bar"
    )
    assert upstairs["T2"].control == "does_not_apply"
    assert upstairs["T1"].control == "not_permitted"


def test_t2_north_beach_prior_use_rule_either_side_of_2025_12_15() -> None:
    # a former Limited Restaurant space qualifies for a Restaurant only from 2025-12-15
    given = {"planning_use": "restaurant", "story": "first", "existing_use_stated": "limited_restaurant"}
    before = run("NCD-NORTH BEACH", D(2025, 12, 14), **given)["T2"]
    after = run("NCD-NORTH BEACH", D(2025, 12, 15), **given)["T2"]
    assert (before.control, after.control) == ("not_permitted", "conditional")
    assert before.differs_today
    assert "This control changed on 2025-12-15 (Ord. 217-25, File No. 250682)" in text_of(before)
    assert after.lines[0].code_section == "Planning Code § 722, Zoning Control Table Note (5)"
    # a Limited Restaurant: conditional in a qualifying space until 2025-12-14, nothing asked from 2025-12-15
    cafe = {"planning_use": "limited_restaurant", "story": "first", "existing_use_stated": "bar"}
    assert run("NCD-NORTH BEACH", D(2025, 12, 14), **cafe)["T2"].control == "conditional"
    assert run("NCD-NORTH BEACH", D(2025, 12, 15), **cafe)["T2"].control == "principal"


def test_t2_calle_24_frontage_rule_and_its_exemption() -> None:
    found = run("NCT-24TH-MISSION", D(2025, 6, 1), CALLE24, planning_use="bar", story="first")["T2"]
    assert found.control == "not_decided"
    assert found.missing_inputs == [tg.NOT_KNOWN["frontage"]]
    exempt = run(
        "NCT-24TH-MISSION",
        D(2025, 6, 1),
        CALLE24,
        planning_use="restaurant",
        existing_use_stated="limited_restaurant",
        story="first",
    )["T2"]
    assert exempt.control == "principal"
    assert "T2:calle24.frontage_35_percent_exemptions" in ids(exempt)
    # an existing use that expands is reached too
    grows = run(
        "NCT-24TH-MISSION",
        D(2025, 6, 1),
        CALLE24,
        planning_use="bar",
        existing_use_stated="bar",
        changes_existing_business="enlarge",
    )["T2"]
    assert grows.control == "not_decided"
    # with the Mission rule the trigger is conditional, and still names what is not known
    both = run("NCT-24TH-MISSION", D(2025, 6, 1), CALLE24, MISSION, planning_use="restaurant", story="first")[
        "T2"
    ]
    assert both.control == "conditional"
    assert both.missing_inputs == [tg.NOT_KNOWN["frontage"]]


# ---- T3: enlarging or intensifying an existing use --------------------------------------------------------------------
def test_t3_no_business_stays_does_not_apply() -> None:
    assert run("NCD-POLK", D(2024, 6, 1), planning_use="bar")["T3"].control == "does_not_apply"
    other = run(
        "NCD-POLK",
        D(2024, 6, 1),
        planning_use="bar",
        existing_use_stated="other",
        changes_existing_business="intensify",
    )
    assert other["T3"].control == "does_not_apply" and ids(other["T3"]) == ["T3.no_use"]
    assert other["T1"].control == "not_decided"  # the Bar is read as a new use, on no story given
    assert other["T1"].missing_inputs == [STORY]


def test_t3_conditional_use_enlarged_or_intensified() -> None:
    for change in ("enlarge", "intensify", "enlarge_and_intensify"):
        found = run(
            "NCD-POLK",
            D(2024, 6, 1),
            planning_use="bar",
            existing_use_stated="bar",
            changes_existing_business=change,
            story="first",
        )["T3"]
        assert found.control == "conditional", change
        last = found.lines[-1]
        assert last.rule_id == "T3.conditional_use"
        assert last.code_section and last.code_section.startswith("Planning Code §§ 178(a)")
        assert tg.CHANGE_WORDS[change] in last.text
    # dated by the run of versions in which the Conditional Use requirement reads the same (corrected: the
    # version of 2023-06-03 changed only § 181(f)(3))
    assert found.in_force_from is None and found.ordinance is None
    assert "this text in force since before 2022-01-01)" in last.text


def test_t3_no_change_and_a_principal_use_ask_for_nothing() -> None:
    none = run(
        "NCD-POLK",
        D(2024, 6, 1),
        planning_use="bar",
        existing_use_stated="bar",
        changes_existing_business="none",
    )["T3"]
    assert none.control == "principal" and ids(none) == ["T3.no_change"]
    principal = run(
        "NCD-POLK",
        D(2024, 6, 1),
        planning_use="restaurant",
        existing_use_stated="restaurant",
        changes_existing_business="enlarge",
        story="first",
    )["T3"]
    assert principal.control == "principal"


def test_t3_nonconforming_use_in_and_outside_a_neighborhood_commercial_district() -> None:
    given = {"planning_use": "bar", "existing_use_stated": "bar", "changes_existing_business": "enlarge"}
    inside = run("NCD-HAIGHT", D(2023, 6, 1), **given, story="first")["T3"]
    assert inside.control == "conditional"
    assert inside.lines[-1].rule_id == "T3.nonconforming_nc"
    # outside the Neighborhood Commercial districts (CRNC: Nighttime Entertainment is NP; RH-2, used here
    # before, now has rows of the table that could govern, so its standing as new is not decided)
    club = {
        "planning_use": "nighttime_entertainment",
        "existing_use_stated": "nighttime_entertainment",
        "changes_existing_business": "enlarge",
    }
    outside = run("CRNC", D(2024, 6, 1), **club, story="first")["T3"]
    assert outside.control == "not_decided"
    assert outside.missing_inputs == [tg.NOT_KNOWN["exceptions_181"]]
    assert outside.lines[-1].rule_id == "T3.nonconforming_other"


def test_t3_existing_use_from_records_with_the_change_not_stated() -> None:
    on = D(2024, 6, 1)
    found = run("NCD-POLK", on, planning_use="bar", story="first", at=site(on, existing_use="bar"))["T3"]
    assert found.control == "not_decided"
    assert found.missing_inputs == [MISSING_PHRASES["changes_existing_business"]]
    # matters here: where a new Restaurant is principal the missing change decides nothing
    easy = run(
        "NCD-POLK", on, planning_use="restaurant", story="first", at=site(on, existing_use="restaurant")
    )
    assert easy["T3"].control == "principal" and not easy["T3"].missing_inputs


def test_t3_reads_the_special_district_control_for_a_new_use() -> None:
    found = run(
        "MUR",
        D(2024, 6, 1),
        SOMA,
        planning_use="restaurant",
        existing_use_stated="restaurant",
        changes_existing_business="enlarge",
        story="first",
    )
    assert found["T3"].control == "conditional"
    assert "T2:soma_yf.restaurant" in ids(found["T3"])
    assert found["T2"].control == "does_not_apply"


# ---- T4: liquor licence in a restricted district ----------------------------------------------------------------------
RESTAURANT_47 = {
    "business_type": "restaurant",
    "planning_use": "restaurant",
    "serves_alcohol": True,
    "licence_type": "47",
    "story": "first",
}
BAR_48 = {
    "business_type": "bar",
    "planning_use": "bar",
    "serves_alcohol": True,
    "licence_type": "48",
    "story": "first",
}


def test_t4_no_restricted_district_or_no_alcohol_does_not_apply() -> None:
    assert run("NCD-POLK", D(2024, 6, 1), **RESTAURANT_47)["T4"].control == "does_not_apply"
    dry = run("NCD-NORTH BEACH", D(2024, 6, 1), planning_use="restaurant")["T4"]
    assert dry.control == "does_not_apply" and ids(dry) == ["T4.no_alcohol"]
    # a special district without licence rules
    assert run("MUR", D(2024, 6, 1), SOMA, **RESTAURANT_47)["T4"].control == "does_not_apply"


def test_t4_north_beach_licence_rule_either_side_of_its_end() -> None:
    before = run("NCD-NORTH BEACH", D(2025, 12, 14), **RESTAURANT_47, alcohol_transaction="new_licence")["T4"]
    assert before.control == "conditional"
    assert before.differs_today
    assert (
        "This control changed on 2025-12-15 (Ord. 217-25, File No. 250682); today it reads principally"
        in text_of(before)
    )
    assert before.lines[0].rule_id == "T4:north_beach.restaurant_liquor_licence"
    assert before.lines[0].code_section == "Planning Code § 780.3(c)(2)(A)"
    assert before.lines[0].citations == ["zoning:NCD-NORTH BEACH"]
    after = run("NCD-NORTH BEACH", D(2025, 12, 15), **RESTAURANT_47, alcohol_transaction="new_licence")["T4"]
    assert after.control == "principal"
    assert not after.differs_today
    assert after.in_force_from == "2025-12-15"


def test_t4_north_beach_records_requirement_changes_on_2024_01_14() -> None:
    old = run("NCD-NORTH BEACH", D(2024, 1, 13), **RESTAURANT_47, alcohol_transaction="new_licence")["T4"]
    new = run("NCD-NORTH BEACH", D(2024, 1, 14), **RESTAURANT_47, alcohol_transaction="new_licence")["T4"]
    assert old.control == new.control == "conditional"
    assert "at least 51% of its gross receipts" in text_of(old)
    assert "51% food-receipts test is gone" in text_of(new)
    assert [line.rule_id for line in tg.requirements([new])] == [
        "T4:north_beach.restaurant_liquor_licence_records"
    ]
    assert tg.blocking_requirements([new]) == []


def test_t4_north_beach_what_decides_whether_a_licence_is_added() -> None:
    on = D(2024, 6, 1)
    existing = {**RESTAURANT_47, "existing_use_stated": "restaurant", "changes_existing_business": "none"}
    adds = run("NCD-NORTH BEACH", on, **existing, licences_already_held="41")["T4"]
    assert adds.control == "conditional"
    held = run("NCD-NORTH BEACH", on, **existing, licences_already_held="47")["T4"]
    assert held.control == "principal"
    stated = run("NCD-NORTH BEACH", on, **existing, alcohol_transaction="licence_already_held")["T4"]
    assert stated.control == "principal"
    on_file = run("NCD-NORTH BEACH", on, **existing, at=site(on, licences=("47",)))["T4"]
    assert on_file.control == "principal"
    assert "app:abc:1" in on_file.lines[0].citations
    unknown = run("NCD-NORTH BEACH", on, **existing)["T4"]
    assert unknown.control == "not_decided"
    assert unknown.missing_inputs == [
        MISSING_PHRASES["licences_held"],
        MISSING_PHRASES["alcohol_transaction"],
    ]
    # a new restaurant holds nothing at the address
    assert run("NCD-NORTH BEACH", on, **RESTAURANT_47)["T4"].control == "conditional"
    # the licence type decides it
    no_type = run("NCD-NORTH BEACH", on, planning_use="restaurant", serves_alcohol=True, story="first")["T4"]
    assert no_type.control == "not_decided" and no_type.missing_inputs == [LICENCE]
    type_90 = run("NCD-NORTH BEACH", on, **{**RESTAURANT_47, "licence_type": "90"})["T4"]
    assert type_90.control == "principal"
    assert "T4:north_beach.music_venue_type_90" in ids(type_90)
    # the rule is for the First Story
    upstairs = run("NCD-NORTH BEACH", on, **{**RESTAURANT_47, "story": "second"})["T4"]
    assert upstairs.control == "does_not_apply"


# review of 2026-11-12: with no story given, a rule for the First Story only is read for the First Story (on any
# other story it does not apply). The story is named only where that reading asks for something or is itself not
# decided; a rule that asks for nothing there is not made "not decided" by the missing story
NOT_AMONG_STATED = "which is not among the stories stated"


def test_t4_north_beach_licence_rule_with_no_story_given() -> None:
    on = D(2024, 6, 1)
    unplaced = {k: v for k, v in RESTAURANT_47.items() if k != "story"}
    # Type 40 is not among the types the rule reaches: principal on the First Story, so the story is not named
    not_reached = run("NCD-NORTH BEACH", on, **{**unplaced, "licence_type": "40"})["T4"]
    assert not_reached.control == "principal" and STORY not in not_reached.missing_inputs
    assert NOT_AMONG_STATED not in text_of(not_reached)
    # Type 47 is reached: conditional on the First Story, nothing elsewhere, so the story decides it
    reached = run("NCD-NORTH BEACH", on, **unplaced)["T4"]
    assert reached.control == "not_decided" and reached.missing_inputs == [STORY]
    assert "The rule is for the First Story. Which story the business is on is not given" in text_of(reached)
    # no licence type and no story: both are named
    no_type = run("NCD-NORTH BEACH", on, planning_use="restaurant", serves_alcohol=True)["T4"]
    assert no_type.control == "not_decided" and no_type.missing_inputs == [LICENCE, STORY]
    assert "Which story the business is on is not given either" in text_of(no_type)
    # after 2025-12-14 the rule asks for nothing: principal, and never "not among the stories stated"
    after = run("NCD-NORTH BEACH", D(2026, 11, 10), **{**unplaced, "licence_type": "41"})["T4"]
    assert after.control == "principal" and after.missing_inputs == []
    assert NOT_AMONG_STATED not in text_of(after) and "This rule asks for nothing here" in text_of(after)


def test_t2_north_beach_prior_use_rule_with_no_story_given() -> None:
    on = D(2024, 6, 1)
    # from 2025-12-15 a Limited Restaurant is principally permitted on the First Story and the rule does not apply
    # on any other, so the story does not change it
    cafe = {"planning_use": "limited_restaurant", "existing_use_stated": "retail"}
    for story in (None, "first"):
        given = {**cafe, "story": story} if story else cafe
        found = run("NCD-NORTH BEACH", D(2026, 11, 10), **given)["T2"]
        assert found.control == "principal" and STORY not in found.missing_inputs, story
        assert NOT_AMONG_STATED not in text_of(found), story
    second = run("NCD-NORTH BEACH", D(2026, 11, 10), **cafe, story="second")["T2"]
    assert second.control == "does_not_apply"
    # the last use is not known: not decided on the First Story, so the last use and the story are both named
    unknown = run("NCD-NORTH BEACH", on, planning_use="restaurant")["T2"]
    assert unknown.control == "not_decided"
    assert unknown.missing_inputs == [LAST_USE, STORY]
    assert "Which story the business is on is not given either" in text_of(unknown)


def test_t4_haight_new_establishment_either_side_of_2024_01_14() -> None:
    new = {**RESTAURANT_47, "existing_use_stated": "retail"}
    before = run("NCD-HAIGHT", D(2024, 1, 13), **new)["T4"]
    # a Type 47 Restaurant on the ground level could fall within the quota the data records as C (corrected:
    # this read "not_permitted" with the exception printed and not applied)
    assert before.control == "not_decided"
    assert before.differs_today
    assert before.missing_inputs == [tg.NOT_KNOWN["haight_restaurant_quota"]]
    assert "T4:haight.restaurant_quota_exception" in ids(before)
    assert "the rules cannot count the Restaurants already approved" in text_of(before)
    # a Bar and the other on-sale types stay not permitted
    bar = run("NCD-HAIGHT", D(2024, 1, 13), **{**BAR_48, "existing_use_stated": "retail"})["T4"]
    assert bar.control == "not_permitted"
    after = run("NCD-HAIGHT", D(2024, 1, 14), **new)["T4"]
    assert after.control == "conditional"
    assert after.in_force_from == "2024-01-14" and after.ordinance == "Ord. 249-23, File No. 230701"
    assert "T4:haight.restaurant_quota_exception" not in ids(after)
    assert after.lines[0].citations == ["zoning:NCD-HAIGHT"]
    # found through the overlay as well: the overlay is cited
    via_overlay = run("NCD-HAIGHT", D(2024, 1, 14), HAIGHT, **new)["T4"]
    assert via_overlay.lines[0].citations == [f"overlay:{HAIGHT.id}"]


def test_t4_haight_licence_types_and_what_is_missing() -> None:
    on = D(2024, 6, 1)
    type_75 = run("NCD-HAIGHT", on, **{**RESTAURANT_47, "licence_type": "75"}, existing_use_stated="retail")[
        "T4"
    ]
    assert type_75.control == "principal"
    assert "T4:haight.licence_types_excluded_from_on_sale" in ids(type_75)
    # Type 90 is outside the rule only from 2024-01-14
    venue = {**BAR_48, "licence_type": "90", "existing_use_stated": "retail"}
    assert "T4:haight.licence_types_excluded_from_on_sale" in ids(run("NCD-HAIGHT", on, **venue)["T4"])
    assert "T4:haight.licence_types_excluded_from_on_sale" not in ids(
        run("NCD-HAIGHT", D(2024, 1, 13), **venue)["T4"]
    )
    no_type = run(
        "NCD-HAIGHT", on, planning_use="restaurant", serves_alcohol=True, existing_use_stated="retail"
    )
    assert no_type["T4"].control == "not_decided" and no_type["T4"].missing_inputs == [LICENCE]
    not_said = run("NCD-HAIGHT", on, **RESTAURANT_47)["T4"]
    assert not_said.control == "not_decided"
    assert not_said.missing_inputs == [MISSING_PHRASES["alcohol_transaction"], LAST_USE]
    assert (
        run("NCD-HAIGHT", on, **RESTAURANT_47, alcohol_transaction="new_licence")["T4"].control
        == "conditional"
    )


def test_t4_haight_existing_establishment_continues_only_with_the_same_licence_type() -> None:
    on = D(2024, 6, 1)
    existing = {**RESTAURANT_47, "existing_use_stated": "restaurant", "changes_existing_business": "none"}
    same = run("NCD-HAIGHT", on, **existing, licences_already_held="47")["T4"]
    assert same.control == "principal"
    assert [line.rule_id for line in tg.requirements([same])] == [
        "T4:haight.existing_establishment_continuation"
    ]
    changes = run("NCD-HAIGHT", on, **existing, licences_already_held="41")["T4"]
    assert changes.control == "conditional"
    assert "holds ABC Type 41 and the concept needs Type 47" in text_of(changes)
    on_file = run("NCD-HAIGHT", on, **existing, at=site(on, licences=("41",)))["T4"]
    assert on_file.control == "conditional"
    unknown = run("NCD-HAIGHT", on, **existing)["T4"]
    assert unknown.control == "not_decided"
    assert unknown.missing_inputs == [MISSING_PHRASES["licences_held"]]


def test_t4_a_change_of_licence_that_keeps_an_existing_establishments_standing() -> None:
    existing = {
        "existing_use_stated": "bar",
        "changes_existing_business": "none",
        "licences_already_held": "48",
    }
    venue = {**BAR_48, "licence_type": "90", **existing}
    rule = "T4:haight.existing_establishment_licence_change"
    after = run("NCD-HAIGHT", D(2024, 1, 14), **venue)["T4"]  # to Type 64 or 90: from 2024-01-14
    assert after.control == "principal" and rule in ids(after)
    assert "holds ABC Type 48 and the concept needs Type 90, a change this rule allows" in text_of(after)
    before = run("NCD-HAIGHT", D(2024, 1, 13), **venue)["T4"]
    assert rule not in ids(before)
    to_41 = {**RESTAURANT_47, "licence_type": "41", **{**existing, "existing_use_stated": "restaurant"}}
    third = run("NC-3", D(2024, 6, 1), THIRD, **to_41)["T4"]
    assert third.control == "principal" and "T4:third.change_to_type_41" in ids(third)
    # not printed for a business that keeps its licence, or for a new one
    assert rule not in ids(run("NCD-HAIGHT", D(2024, 6, 1), **{**venue, "licences_already_held": "90"})["T4"])
    assert rule not in ids(run("NCD-HAIGHT", D(2024, 6, 1), **{**BAR_48, "licence_type": "90"})["T4"])
    # the types a change may go to are never ones the district's rule for a new establishment reaches
    for prefix in ("haight", "third"):
        reached = {
            t
            for b in tg.BINDINGS
            if b.kind == "new_establishment" and b.rule_id.startswith(prefix)
            for t in b.types
        }
        allowed = {
            t
            for b in tg.BINDINGS
            if b.kind == "licence_change" and b.rule_id.startswith(prefix)
            for types in (b.types_by_start or {None: b.types}).values()
            for t in types
        }
        assert allowed and not reached & allowed, prefix


def test_t4_type_90_venue_rules_begin_on_2024_01_14() -> None:
    venue = {**BAR_48, "licence_type": "90", "existing_use_stated": "retail"}
    for district, rows, rule in (
        ("NCT-VALENCIA", [MISSION], "T4:mission.music_venue_type_90"),
        ("NCD-NORTH BEACH", [], "T4:north_beach.music_venue_type_90"),
    ):
        assert rule not in ids(run(district, D(2024, 1, 13), *rows, **venue)["T4"]), district
        after = run(district, D(2024, 1, 14), *rows, **venue)["T4"]
        assert rule in ids(after) and after.control == "principal", district
    # the North Beach one ended with the repeal
    assert "T4:north_beach.music_venue_type_90" not in ids(
        run("NCD-NORTH BEACH", D(2025, 12, 15), **venue)["T4"]
    )


def test_t4_third_street_rules_and_the_type_42_date() -> None:
    new_bar = {**BAR_48, "existing_use_stated": "retail"}
    assert run("NCD-BAYVIEW", D(2025, 6, 1), THIRD, **new_bar)["T4"].control == "not_permitted"
    type_42 = {**new_bar, "licence_type": "42"}
    before = run("NCD-BAYVIEW", D(2025, 4, 6), THIRD, **type_42)["T4"]
    after = run("NCD-BAYVIEW", D(2025, 4, 7), THIRD, **type_42)["T4"]
    assert (before.control, after.control) == ("not_permitted", "conditional")
    assert before.differs_today
    assert "This control changed on 2025-04-07 (Ord. 21-25, File No. 240932)" in text_of(before)
    assert after.in_force_from == "2025-04-07"
    assert after.lines[0].rule_id == "T4:third.type_42_bayview_ncd"
    assert after.lines[0].citations == [f"overlay:{THIRD.id}"]
    # elsewhere in the district a new Type 42 establishment stays not permitted
    elsewhere = run("NC-3", D(2025, 6, 1), THIRD, **type_42)["T4"]
    assert elsewhere.control == "not_permitted"
    assert elsewhere.lines[0].rule_id == "T4:third.new_on_sale_establishment"
    # a Restaurant's licence types are outside the rule, with or without the type stated
    assert run("NCD-BAYVIEW", D(2025, 6, 1), THIRD, **RESTAURANT_47)["T4"].control == "principal"
    restaurant = run("NCD-BAYVIEW", D(2025, 6, 1), THIRD, planning_use="restaurant", serves_alcohol=True)[
        "T4"
    ]
    assert restaurant.control == "principal" and not restaurant.missing_inputs
    bar = run("NCD-BAYVIEW", D(2025, 6, 1), THIRD, planning_use="bar", serves_alcohol=True)["T4"]
    assert bar.control == "not_decided" and bar.missing_inputs == [LICENCE]


def test_t4_unknown_pours_are_missing_never_no_alcohol_nor_a_type() -> None:
    """Decision 1: a Bar or a Restaurant that serves alcohol without saying what (alcohol_type "unknown") has no
    licence type. A licence rule that turns on the type is not decided and names what alcohol will be served;
    it is never read as "no alcohol" (does_not_apply) nor as a type. A stated type still decides it."""
    on = D(2025, 6, 1)
    # a Bar in the Bayview NCD (the Third Street district's rule for a new on-sale establishment)
    bar = run("NCD-BAYVIEW", on, THIRD, business_type="bar", serves_alcohol=True, story="first")["T4"]
    assert bar.control == "not_decided" and bar.missing_inputs == [POURS]
    assert "T4.no_alcohol" not in ids(bar)
    assert "does not say what alcohol will be served (beer and wine, or spirits too)" in text_of(bar)
    # a Restaurant in North Beach (its licence rule reaches Types 41 and 47 alike, but turns on the type)
    beach = run(
        "NCD-NORTH BEACH", D(2024, 6, 1), business_type="restaurant", serves_alcohol=True, story="first"
    )["T4"]
    assert beach.control == "not_decided" and beach.missing_inputs == [POURS]
    assert ids(beach)[0] == "T4:north_beach.restaurant_liquor_licence"
    stated = run(
        "NCD-BAYVIEW", on, THIRD, business_type="bar", serves_alcohol=True, story="first", licence_type="42"
    )["T4"]
    assert POURS not in stated.missing_inputs and LICENCE not in stated.missing_inputs


def test_t4_mission_new_bar_requirement_is_exposed_for_the_alcohol_row() -> None:
    found = run("NCT-VALENCIA", D(2024, 6, 1), MISSION, **BAR_48)
    t4 = found["T4"]
    assert t4.control == "principal"  # a requirement is a condition, not a control
    blocking = tg.blocking_requirements(found.values())
    assert [line.rule_id for line in blocking] == ["T4:mission.new_bar_licence_from_bar_in_district"]
    assert blocking[0].code_section == "Planning Code § 249.60(b)(2)(C)"
    assert (
        "must use a liquor licence transferred from another Bar located inside the district"
        in blocking[0].text
    )
    assert "This is a requirement, not a control" in blocking[0].text
    assert found["T2"].control == "conditional"
    # not for a Bar that continues, and not for a Restaurant
    stays = run(
        "NCT-VALENCIA",
        D(2024, 6, 1),
        MISSION,
        **BAR_48,
        existing_use_stated="bar",
        changes_existing_business="none",
    )
    assert tg.blocking_requirements(stays.values()) == []
    assert (
        tg.blocking_requirements(run("NCT-VALENCIA", D(2024, 6, 1), MISSION, **RESTAURANT_47).values()) == []
    )


def test_t4_mission_expansion_of_an_existing_licensed_business() -> None:
    on = D(2023, 3, 1)
    existing = {
        **RESTAURANT_47,
        "existing_use_stated": "restaurant",
        "alcohol_transaction": "licence_already_held",
    }
    grows = run("NCT-MISSION", on, MISSION, **existing, changes_existing_business="enlarge")["T4"]
    assert grows.control == "conditional"
    assert "T4:mission.existing_liquor_establishment_expansion" in ids(grows)
    assert "T4.definition_note" in ids(grows)  # the definition leaves out a Bona Fide Eating Place
    same = run("NCT-MISSION", on, MISSION, **existing, changes_existing_business="intensify")["T4"]
    assert same.control == "principal"
    bar = {**BAR_48, "existing_use_stated": "bar", "licences_already_held": "48"}
    bar_grows = run("NCT-MISSION", on, MISSION, **bar, changes_existing_business="enlarge_and_intensify")[
        "T4"
    ]
    # § 249.60(c) leaves out a Bar as well (corrected: the note was printed for a Restaurant only)
    assert bar_grows.control == "conditional" and "T4.definition_note" in ids(bar_grows)
    assert "and a Bar (the uses listed in § 249.60(b)(1)-(2))" in text_of(bar_grows)
    # a licence of these premises changing hands is an existing licensed business; a new licence is not
    bought = {**BAR_48, "existing_use_stated": "bar", "changes_existing_business": "enlarge"}
    taken_over = run("NCT-MISSION", on, MISSION, **bought, alcohol_transaction="person_to_person_transfer")
    assert taken_over["T4"].control == "conditional"
    newly = run("NCT-MISSION", on, MISSION, **bought, alcohol_transaction="new_licence")["T4"]
    assert "T4:mission.existing_liquor_establishment_expansion" not in ids(newly)
    unknown = run("NCT-MISSION", on, MISSION, **bought)["T4"]
    assert unknown.control == "not_decided" and unknown.missing_inputs == [MISSING_PHRASES["licences_held"]]
    # shown by records, change not stated
    shown = run("NCT-MISSION", on, MISSION, **BAR_48, at=site(on, existing_use="bar", licences=("48",)))["T4"]
    assert shown.control == "not_decided"
    assert shown.missing_inputs == [MISSING_PHRASES["changes_existing_business"]]


def test_t4_mission_type_75_in_and_outside_the_sub_area() -> None:
    brewpub = {**RESTAURANT_47, "licence_type": "75", "existing_use_stated": "retail"}
    inside = run("NCT-MISSION", D(2024, 6, 1), MISSION, **brewpub)["T4"]
    assert inside.control == "not_permitted"
    outside = run("NCT-VALENCIA", D(2024, 6, 1), MISSION, **brewpub)["T4"]
    assert outside.control == "not_decided"
    assert outside.missing_inputs == [tg.NOT_KNOWN["mission_subarea"]]
    # the licence type not stated: a new Restaurant could hold Type 75; one that already exists is not new
    untyped = {"planning_use": "restaurant", "serves_alcohol": True, "story": "first"}
    new = run("NCT-MISSION", D(2024, 6, 1), MISSION, **untyped, existing_use_stated="retail")["T4"]
    assert new.control == "not_decided" and new.missing_inputs == [LICENCE]
    stays = run(
        "NCT-MISSION",
        D(2024, 6, 1),
        MISSION,
        **untyped,
        existing_use_stated="restaurant",
        changes_existing_business="none",
    )["T4"]
    assert stays.control == "principal" and not stays.missing_inputs
    # a Bar cannot hold Type 75 (Planning Code § 102), so the rule does not reach it
    bar = run("NCT-MISSION", D(2024, 6, 1), MISSION, planning_use="bar", serves_alcohol=True)["T4"]
    assert bar.control == "principal" and not bar.missing_inputs


# ---- T5: formula retail ---------------------------------------------------------------------------------------------------
def test_t5_true_false_and_missing() -> None:
    on = D(2024, 6, 1)
    yes = run("NCD-POLK", on, planning_use="restaurant", formula_retail=True)["T5"]
    assert yes.control == "conditional"
    assert yes.lines[0].code_section == "Planning Code § 723"
    assert run("NCD-POLK", on, planning_use="restaurant", formula_retail=False)["T5"].control == "principal"
    missing = run("NCD-POLK", on, planning_use="restaurant")["T5"]
    assert missing.control == "not_decided" and missing.missing_inputs == [CHAIN]
    assert (
        run("NCD-NORTH BEACH", on, planning_use="bar", formula_retail=True)["T5"].control == "not_permitted"
    )
    assert run("C-2", on, planning_use="bar", formula_retail=True)["T5"].control == "principal"
    assert run("NCD-POLK", on, planning_use="nighttime_entertainment", formula_retail=True)["T5"].control == (
        "does_not_apply"
    )


def test_t5_a_missing_answer_matters_only_where_a_control_is_conditional_or_not_permitted() -> None:
    found = run("C-2", D(2024, 6, 1), planning_use="restaurant")["T5"]
    assert found.control == "principal" and not found.missing_inputs
    assert "whatever the answer" in text_of(found)
    assert not tg.matters(found)


def test_t5_uses_the_district_bars_formula_retail_for() -> None:
    cafe = run("NCD-IRVING", D(2024, 7, 30), planning_use="limited_restaurant", formula_retail=True)["T5"]
    assert cafe.control == "not_permitted"
    assert "formula retail is not permitted for Limited Restaurant" in text_of(cafe)
    assert (
        run("NCD-IRVING", D(2024, 7, 30), planning_use="bar", formula_retail=True)["T5"].control
        == "conditional"
    )


def test_t5_prints_the_change_of_operator_note_with_its_dates() -> None:
    before = run("NCD-POLK", D(2025, 5, 31), planning_use="restaurant", formula_retail=True)["T5"]
    after = run("NCD-POLK", D(2025, 6, 1), planning_use="restaurant", formula_retail=True)["T5"]
    assert "limbs A, B, C, D and E" in text_of(before)
    assert "limbs A, B, C and D;" in text_of(after)
    note = next(line for line in after.lines if line.rule_id == "T5.operator")
    assert note.text.startswith("Note, not evaluated by the rules:")
    assert note.code_section and "178(c)(3)" in note.code_section
    assert before.control == after.control == "conditional"


def test_t5_a_bar_on_formula_retail_in_part_of_a_district() -> None:
    restaurant = {"planning_use": "restaurant", "formula_retail": True}
    # the Taraval Street Restaurant Subdistrict is placed by its overlay (§ 781.1); with none at the point the
    # address is outside it (corrected: this read "not_decided" before the review)
    before = run("NC-2", D(2026, 3, 15), **restaurant)["T5"]
    assert before.control == "conditional"
    from tests.test_triggers_review import TARAVAL

    inside = run("NC-2", D(2026, 3, 15), TARAVAL, **restaurant)["T5"]
    assert inside.control == "not_permitted"
    after = run("NC-2", D(2026, 3, 16), **restaurant)["T5"]
    assert after.control == "conditional"
    # a Bar is not one of the uses the sub-area rule names
    assert run("NC-2", D(2026, 3, 15), planning_use="bar", formula_retail=True)["T5"].control == "conditional"
    # Mission Street Formula Retail Restaurant Subdistrict, until 2024-01-13
    old = run("NCT-MISSION", D(2024, 1, 13), **restaurant)["T5"]
    assert old.control == "not_decided"
    assert old.missing_inputs == [tg.NOT_KNOWN["mission_fr_subdistrict"]]
    sub_rule = next(line for line in old.lines if line.rule_id == "T5.subarea")
    assert sub_rule.code_section == "Planning Code § 781.5(b)(1)"
    assert run("NCT-MISSION", D(2024, 1, 14), **restaurant)["T5"].control == "conditional"
    # an exception that makes it principal on some lots
    assert run("RC-4", D(2025, 5, 31), **restaurant)["T5"].control == "conditional"
    van_ness = run("RC-4", D(2025, 6, 1), **restaurant)["T5"]
    assert van_ness.control == "not_decided"
    assert "front Van Ness Avenue" in van_ness.missing_inputs[0]
    # conditional on some frontages
    market = run("C-3-G", D(2023, 6, 1), **restaurant)["T5"]
    assert market.control == "not_decided" and "frontage on Market Street" in market.missing_inputs[0]
    assert run("C-3-G", D(2025, 6, 1), **restaurant)["T5"].control == "principal"
    # with the answer missing, the possible conditional control still matters
    assert run("C-3-G", D(2023, 6, 1), planning_use="restaurant")["T5"].missing_inputs == [CHAIN]


def test_t5_central_soma_is_placed_by_its_overlay() -> None:
    restaurant = {"planning_use": "restaurant", "formula_retail": True}
    assert run("MUR", D(2024, 6, 1), **restaurant)["T5"].control == "principal"
    inside = run("MUR", D(2024, 6, 1), CENTRAL_SOMA, **restaurant)["T5"]
    assert inside.control == "not_permitted"
    assert f"overlay:{CENTRAL_SOMA.id}" in inside.lines[-2].citations


def test_t5_a_row_that_reaches_only_some_uses() -> None:
    found = run("RM-3", D(2024, 3, 1), planning_use="restaurant", formula_retail=True)["T5"]
    assert found.control == "not_decided"
    assert found.missing_inputs[0] == (
        "whether the use is one the formula retail row reaches: Limited Corner Commercial Uses"
    )
    assert (
        run("RM-3", D(2024, 6, 1), planning_use="restaurant", formula_retail=True)["T5"].control
        == "not_permitted"
    )


# ---- T6: nighttime entertainment ----------------------------------------------------------------------------------------
def test_t6_by_story_and_the_polk_date() -> None:
    club = {"planning_use": "nighttime_entertainment", "entertainment_kind": "place_of_entertainment"}
    before = run("NCD-POLK", D(2024, 5, 26), **club, story="first")["T6"]
    after = run("NCD-POLK", D(2024, 5, 27), **club, story="first")["T6"]
    assert (before.control, after.control) == ("conditional", "principal")
    assert before.differs_today and not after.differs_today
    assert (
        "This control changed on 2024-05-27 (Ord. 85-24, File No. 231221); today it reads principally"
        in text_of(before)
    )
    assert after.in_force_from == "2024-05-27"
    assert run("NCD-POLK", D(2024, 5, 26), **club, story="second")["T6"].control == "not_permitted"
    assert run("NCD-POLK", D(2024, 5, 27), **club, story="second")["T6"].control == "conditional"
    assert run("NCD-POLK", D(2024, 5, 27), **club, story="third_or_above")["T6"].control == "not_permitted"
    # derived from the kind of entertainment alone
    derived = run(
        "NCD-POLK",
        D(2024, 5, 26),
        business_type="bar",
        entertainment_kind="place_of_entertainment",
        story="first",
    )
    assert derived["T6"].control == "conditional"


def test_t6_no_entertainment_or_a_limited_live_performance_does_not_apply() -> None:
    on = D(2024, 6, 1)
    assert run("NCD-HAIGHT", on, planning_use="bar")["T6"].control == "does_not_apply"
    assert (
        run("NCD-HAIGHT", on, planning_use="bar", entertainment_kind="none")["T6"].control == "does_not_apply"
    )
    limited = run("NCD-HAIGHT", on, planning_use="bar", entertainment_kind="limited_live_performance")["T6"]
    assert limited.control == "does_not_apply" and ids(limited) == ["T6.limited_live"]
    assert limited.lines[0].code_section and limited.lines[0].code_section.startswith("Planning Code § 102")


def test_t6_entertainment_described_without_its_kind() -> None:
    on = D(2024, 6, 1)
    matters = run("NCD-HAIGHT", on, planning_use="bar", live_entertainment=True, story="first")["T6"]
    assert matters.control == "not_decided"
    assert matters.missing_inputs == [MISSING_PHRASES["entertainment_kind"]]
    # matters here: where Nighttime Entertainment is principal the missing kind decides nothing
    easy = run("NCD-BROADWAY", on, planning_use="bar", live_entertainment=True, story="first")["T6"]
    assert easy.control == "principal" and not easy.missing_inputs


def test_t6_is_not_applied_to_nighttime_entertainment_that_continues() -> None:
    found = run(
        "NCD-HAIGHT",
        D(2025, 6, 4),
        planning_use=["bar", "nighttime_entertainment"],
        existing_use_stated=["bar", "nighttime_entertainment"],
        changes_existing_business="intensify",
        story="first",
    )
    assert found["T6"].control == "does_not_apply" and ids(found["T6"]) == ["T6.continues"]
    assert found["T3"].control == "conditional"
    # added to an existing Bar it is a new use
    added = run(
        "NCD-HAIGHT",
        D(2025, 6, 4),
        planning_use=["bar", "nighttime_entertainment"],
        existing_use_stated="bar",
        changes_existing_business="intensify",
        story="first",
    )
    assert added["T6"].control == "conditional"


def test_t6_mur_controls_for_part_of_the_district() -> None:
    club = {"planning_use": "nighttime_entertainment", "story": "first"}
    # until 2023-06-02: not permitted, principal inside the Central SoMa SUD
    assert run("MUR", D(2023, 6, 2), **club)["T6"].control == "not_permitted"
    inside = run("MUR", D(2023, 6, 2), CENTRAL_SOMA, **club)["T6"]
    assert inside.control == "principal"
    assert f"overlay:{CENTRAL_SOMA.id}" in inside.lines[1].citations
    # from 2023-06-03: exceptions by area, by building and (from 2025-06-09) by lot
    later = run("MUR", D(2024, 6, 1), **club)["T6"]
    assert later.control == "not_decided"
    assert later.missing_inputs == [
        tg.NOT_KNOWN["historic_803_9"]
    ]  # outside Central SoMa the area cannot apply
    with_overlay = run("MUR", D(2024, 6, 1), CENTRAL_SOMA, **club)["T6"]
    assert with_overlay.missing_inputs == [tg.NOT_KNOWN["central_soma_area"], tg.NOT_KNOWN["historic_803_9"]]
    lot = run("MUR", D(2025, 6, 9), **club)["T6"]
    assert lot.control == "not_decided" and lot.missing_inputs == [tg.NOT_KNOWN["lot_3750_050"]]


def test_t6_the_data_says_a_limited_live_performance_venue_is_not_nighttime_entertainment(
    raw: dict[str, Any],
) -> None:
    """What the fixed sentence T6.limited_live rests on, at every version on file."""
    for version in raw["citywide"]["nighttime_entertainment_definition"]:
        assert version["facts"]["limited_live_performance_only_venue_is_nighttime_entertainment"] is False


# ---- T7: use size -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("district", "area", "before", "after"),
    [
        ("NCD-POLK", 1999, "principal", "principal"),
        ("NCD-POLK", 2000, "conditional", "principal"),  # "of the same size or larger" became "larger than"
        ("NCD-POLK", 2001, "conditional", "conditional"),
        ("NCD-POLK", 4000, "not_permitted", "conditional"),  # the cap went on 2025-10-06
        ("NCD-PACIFIC", 4001, "not_permitted", "conditional"),
        ("NCD-INNER SUNSET", 2500, "conditional", "principal"),
        ("NCD-CASTRO", 4000, "not_permitted", "conditional"),
        ("NCD-CASTRO", 4001, "not_permitted", "not_permitted"),
        ("NCT-MISSION", 6000, "conditional", "principal"),
    ],
)
def test_t7_thresholds_either_side_of_2025_10_06(district: str, area: int, before: str, after: str) -> None:
    given = {"planning_use": "restaurant", "floor_area_sqft": area}
    then = run(district, D(2025, 10, 5), **given, today=D(2025, 10, 6))["T7"]
    now = run(district, D(2025, 10, 6), **given, today=D(2025, 10, 6))["T7"]
    assert (then.control, now.control) == (before, after)
    assert then.differs_today == (before != after)
    if before != after:
        assert "This control changed on 2025-10-06 (Ord. 173-25, File No. 250634)" in text_of(then)
        assert now.in_force_from == "2025-10-06"


def test_t7_floor_area_missing_where_a_threshold_exists() -> None:
    found = run("NCD-POLK", D(2024, 6, 1), planning_use="restaurant")["T7"]
    assert found.control == "not_decided"
    assert found.missing_inputs == [MISSING_PHRASES["floor_area_sqft"]]
    none = run("MUR", D(2024, 6, 1), planning_use="restaurant")["T7"]
    assert none.control == "does_not_apply" and ids(none) == [
        "T7.none"
    ]  # matters here: no threshold, nothing asked


def test_t7_applies_to_a_use_that_is_new_merged_or_enlarged() -> None:
    big = {"planning_use": "restaurant", "floor_area_sqft": 3500, "existing_use_stated": "restaurant"}
    on = D(2024, 6, 1)
    # a new operator's use in a space last used as a Restaurant: whether the floor area grows decides whether the
    # threshold is read (corrected: this read "conditional" before the review)
    takes_over = run("NCD-POLK", on, **big)["T7"]
    assert takes_over.control == "not_decided"
    assert takes_over.missing_inputs == [
        MISSING_PHRASES["floor_area_before_sqft"],
        MISSING_PHRASES["merges_storefronts"],
    ]
    assert run("NCD-POLK", on, **{**big, "existing_use_stated": "vacant"})["T7"].control == "conditional"
    unchanged = run("NCD-POLK", on, **big, changes_existing_business="intensify")["T7"]
    assert unchanged.control == "does_not_apply" and ids(unchanged) == ["T7.not_new"]
    assert run("NCD-POLK", on, **big, changes_existing_business="enlarge")["T7"].control == "conditional"
    merged = run("NCD-POLK", on, **big, changes_existing_business="none", merges_storefronts=True)["T7"]
    assert merged.control == "conditional"
    # an existing use from records, change not stated
    shown = run(
        "NCD-POLK",
        on,
        planning_use="restaurant",
        floor_area_sqft=3500,
        at=site(on, existing_use="restaurant"),
    )
    assert shown["T7"].control == "not_decided"
    assert shown["T7"].missing_inputs == [MISSING_PHRASES["changes_existing_business"]]
    small = run(
        "NCD-POLK", on, planning_use="restaurant", floor_area_sqft=900, at=site(on, existing_use="restaurant")
    )
    assert small["T7"].control == "principal"


def test_t7_prints_the_exemption_and_does_not_apply_it() -> None:
    # the Restaurant part of Table 811 Note 1 is applied now (see the review tests); a Bar keeps the row's control
    # and the exemption is printed (corrected: the case read a Restaurant before the review)
    found = run("CVR", D(2024, 6, 1), planning_use="bar", floor_area_sqft=3000)["T7"]
    assert found.control == "conditional"
    assert ids(found) == ["T7.conditional", "T7.exemption"]
    assert "C for Use Size is not required for Restaurants larger than 2,500 sq. ft." in text_of(found)
    assert "T7.exemption" not in ids(
        run("CVR", D(2024, 6, 1), planning_use="restaurant", floor_area_sqft=900)["T7"]
    )


def test_t7_caps_for_part_of_the_uses_of_a_district() -> None:
    corner = run("RM-3", D(2024, 6, 1), planning_use="restaurant", floor_area_sqft=3000)["T7"]
    assert corner.control == "not_decided"
    assert corner.missing_inputs == [tg.NOT_KNOWN["limited_corner_commercial"]]
    assert (
        run("RM-3", D(2024, 6, 1), planning_use="restaurant", floor_area_sqft=2000)["T7"].control
        == "does_not_apply"
    )
    assert run("RM-3", D(2024, 6, 1), planning_use="restaurant")["T7"].missing_inputs == [
        MISSING_PHRASES["floor_area_sqft"]
    ]
    # before 2023-08-05 § 121.6 and the row agree (from that date the two texts differ: see the review tests)
    grocery = run("C-3-G", D(2023, 6, 1), planning_use="restaurant", floor_area_sqft=130_000)["T7"]
    assert grocery.control == "not_decided" and grocery.missing_inputs == [tg.NOT_KNOWN["large_grocery"]]
    assert (
        run("C-3-G", D(2023, 6, 1), planning_use="restaurant", floor_area_sqft=95_000)["T7"].control
        == "conditional"
    )


# ---- T8: laundromat removal -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("on", "control"),
    [
        (D(2021, 12, 19), "does_not_apply"),
        (D(2021, 12, 20), "conditional"),
        (D(2023, 6, 1), "conditional"),
        (D(2024, 12, 20), "conditional"),
        (D(2024, 12, 21), "does_not_apply"),
        (D(2026, 3, 16), "does_not_apply"),
    ],
)
def test_t8_window(on: dt.date, control: str) -> None:
    found = run("RC-4", on, planning_use="bar", existing_use_stated=["laundromat", "vacant"])["T8"]
    assert found.control == control
    assert "2021-12-20 to 2024-12-20" in text_of(found)
    assert found.differs_today == (control == "conditional")
    if control == "conditional":
        assert "This control changed on 2024-12-21; today it reads does not apply." in text_of(found)
        assert found.lines[0].code_section == "Planning Code §§ 202.12; 102 (Laundromat)"
    else:
        assert on.isoformat() in found.lines[0].text


def test_t8_last_use_not_a_laundromat_or_not_stated() -> None:
    on = D(2023, 6, 1)
    other = run("RC-4", on, planning_use="bar", existing_use_stated="retail")["T8"]
    assert other.control == "principal" and not other.differs_today
    missing = run("RC-4", on, planning_use="bar")["T8"]
    assert missing.control == "not_decided" and missing.missing_inputs == [LAST_USE]
    assert missing.differs_today
    vacant = run("RC-4", on, planning_use="bar", existing_use_stated="vacant")["T8"]
    assert vacant.control == "not_decided"
    shown = run("RC-4", on, planning_use="bar", at=site(on, existing_use="restaurant"))["T8"]
    assert shown.control == "principal" and shown.lines[0].citations == ["app:abc:1"]
    # outside the window a missing last use decides nothing
    later = run("RC-4", D(2025, 1, 1), planning_use="bar")["T8"]
    assert later.control == "does_not_apply" and not later.missing_inputs


# ---- T9: outdoor activity area --------------------------------------------------------------------------------------------
def test_t9_none_and_the_sidewalk_do_not_apply() -> None:
    on = D(2024, 6, 1)
    assert run("NCD-POLK", on, planning_use="restaurant")["T9"].control == "does_not_apply"
    assert (
        run("NCD-POLK", on, planning_use="restaurant", outdoor_area="none")["T9"].control == "does_not_apply"
    )
    walk = run("NCD-POLK", on, planning_use="restaurant", outdoor_area="sidewalk")["T9"]
    assert walk.control == "does_not_apply" and ids(walk) == ["T9.sidewalk"]


def test_t9_by_place() -> None:
    on = D(2024, 6, 1)
    restaurant = {"planning_use": "restaurant"}
    assert run("NCD-POLK", on, **restaurant, outdoor_area="front")["T9"].control == "principal"
    # elsewhere: conditional where neither the row nor § 202.2(a)(7) gives the route (corrected: NCT-MISSION was
    # used here; § 202.2(a)(7) itself reaches every NCT district, see the review tests)
    for place in ("rear_or_side", "parking_lot"):
        assert run("CRNC", on, **restaurant, outdoor_area=place)["T9"].control == "conditional", place
    assert run("NCT-MISSION", on, **restaurant, outdoor_area="rooftop")["T9"].control == "conditional"
    assert run("C-2", on, **restaurant, outdoor_area="rooftop")["T9"].control == "principal"
    assert run("RH-2", on, **restaurant, outdoor_area="rear_or_side")["T9"].control == "not_permitted"
    assert run("RH-2", on, **restaurant, outdoor_area="front")["T9"].control == "principal"
    # before 2024-05-27 the district had no row
    early = run("RH-2", D(2024, 5, 26), **restaurant, outdoor_area="front")["T9"]
    assert early.control == "not_decided" and early.missing_inputs == [tg.NOT_KNOWN["outdoor_control"]]


def test_t9_elsewhere_within_the_limits_of_202_2_a_7() -> None:
    on = D(2025, 2, 3)
    found = run("NCD-HAIGHT", on, planning_use="restaurant", outdoor_area="rear_or_side")["T9"]
    assert found.control == "not_decided"
    assert found.missing_inputs == [
        "whether the outdoor area meets every limit of Planning Code § 202.2(a)(7): on the ground level; in "
        "operation only between 9:00 a.m. and 10:00 p.m.; not operated in association with a Bar use; with a "
        "Limited Restaurant or Restaurant: seated areas only, no standing; alcohol dispensed only inside the "
        "premises or by wait staff at the patron's outdoor seat"
    ]
    # the input can show a limit is not met
    bar = run("NCD-HAIGHT", on, planning_use="bar", outdoor_area="rear_or_side")["T9"]
    assert bar.control == "conditional" and ids(bar) == ["T9.limits"]
    roof = run("NCD-HAIGHT", on, planning_use="restaurant", outdoor_area="rooftop")["T9"]
    assert roof.control == "conditional"


def test_t9_an_outdoor_area_described_without_its_place() -> None:
    on = D(2024, 6, 1)
    # backtest/inputs.json has no key for "an outdoor area is described": build it from the profile's flag
    profile = profile_from_facts({"planning_use": "restaurant"}).model_copy(update={"outdoor_seating": True})
    concept = concept_facts(profile, stated_uses=("restaurant",))

    def t9(district: str) -> TriggerFinding:
        return tg.by_id(
            tg.evaluate(concept, site(on), zoning(district), [], rules_date=on, today=TODAY), "T9"
        )

    matters = t9("NCD-POLK")
    assert matters.control == "not_decided"
    assert matters.missing_inputs == [MISSING_PHRASES["outdoor_area"]]
    easy = t9("C-2")  # matters here: principal in front and elsewhere
    assert easy.control == "principal" and not easy.missing_inputs


# ---- T10: amending an earlier approval --------------------------------------------------------------------------------------
def test_t10_every_answer() -> None:
    on = D(2024, 6, 1)
    yes = run("NCD-POLK", on, planning_use="bar", amends_prior_approval=True)["T10"]
    assert yes.control == "conditional"
    assert yes.lines[0].code_section == "Planning Code §§ 303(e); 174"
    assert yes.lines[0].source_url and "sec.-303" in yes.lines[0].source_url
    no = run("NCD-POLK", on, planning_use="bar", amends_prior_approval=False)["T10"]
    assert no.control == "does_not_apply" and ids(no) == ["T10.no"]
    assert run("NCD-POLK", on, planning_use="bar")["T10"].control == "does_not_apply"
    earlier = site(on, conditional_use_on=D(2019, 5, 1))
    stays = run(
        "NCD-POLK",
        on,
        planning_use="bar",
        existing_use_stated="bar",
        changes_existing_business="intensify",
        at=earlier,
    )["T10"]
    assert stays.control == "not_decided"
    assert stays.missing_inputs == [MISSING_PHRASES["amends_prior_approval"]]
    assert stays.lines[0].citations == ["app:datasf_planning:2019-000111CUA"]
    assert "datasf_planning:2019-000111CUA, 2019-05-01" in stays.lines[0].text
    # an earlier decision without a business that stays decides nothing
    assert run("NCD-POLK", on, planning_use="bar", at=earlier)["T10"].control == "does_not_apply"


# ---- T11: hours of operation ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("district", "closing", "control"),
    [
        ("NCD-POLK", "02:00", "principal"),  # read at its last open minute, 1:59 a.m.
        ("NCD-POLK", "02:30", "conditional"),
        ("NCD-NORTH BEACH", "03:00", "not_permitted"),
        ("NCD-NORTH BEACH", "01:30", "principal"),
        ("CRNC", "23:00", "principal"),
        ("CRNC", "23:30", "conditional"),
        ("NCD-PACIFIC", "22:30", "conditional"),
        ("NCD-PACIFIC", "03:00", "not_permitted"),
        ("NCD-LAKESIDE VILLAGE", "03:00", "not_decided"),  # the row says nothing about 2 a.m. to 6 a.m.
        ("NC-1", "03:00", "not_permitted"),  # a window the row does not print
        ("NCT-MISSION", "04:00", "does_not_apply"),  # no hours control
    ],
)
def test_t11_closing_time_against_the_windows(district: str, closing: str, control: str) -> None:
    found = run(district, D(2024, 6, 1), planning_use="bar", closing_hour=closing)["T11"]
    assert found.control == control
    if control == "not_decided":
        assert found.missing_inputs == [tg.NOT_KNOWN["hours_not_covered"]]
    if control not in ("does_not_apply",):
        assert controls.hours(district, D(2024, 6, 1)).text in found.lines[0].text


def test_t11_closing_time_not_stated() -> None:
    on = D(2024, 6, 1)
    early = run("CRNC", on, planning_use="bar")["T11"]  # C from 11 p.m.
    assert early.control == "not_decided" and early.missing_inputs == [MISSING_PHRASES["closing"]]
    late = run("NCD-POLK", on, planning_use="bar")["T11"]  # C from 2 a.m.: matters here says no
    assert late.control == "principal" and not late.missing_inputs
    assert "the rules did not check a closing time after 2 a.m." in text_of(late)
    assert run("NCT-MISSION", on, planning_use="bar")["T11"].control == "does_not_apply"


def test_t11_a_closing_time_derived_from_the_profile_flags() -> None:
    profile = profile_from_facts({"planning_use": "bar"}).model_copy(update={"closes_after_2am": True})
    concept = concept_facts(profile, stated_uses=("bar",))
    on = D(2024, 6, 1)
    found = tg.by_id(
        tg.evaluate(concept, site(on), zoning("NCD-POLK"), [], rules_date=on, today=TODAY), "T11"
    )
    assert found.control == "conditional"
    assert "closing after 2 a.m. (read at 3 a.m.)" in text_of(found)


def test_t11_an_existing_business_keeping_its_hours_is_not_decided_by_the_rules() -> None:
    found = run(
        "NCD-POLK",
        D(2024, 6, 1),
        planning_use="bar",
        closing_hour="03:00",
        existing_use_stated="bar",
        changes_existing_business="none",
    )["T11"]
    # spec 1a T11 (corrected: this read "conditional" with the line saying the rules do not decide it)
    assert found.control == "not_decided"
    assert found.missing_inputs == [tg.NOT_KNOWN["existing_hours"]]
    assert found.lines[-1].rule_id == "T11.existing"
    new = run("NCD-POLK", D(2024, 6, 1), planning_use="bar", closing_hour="03:00")["T11"]
    assert "T11.existing" not in ids(new)


def test_t11_windows_for_a_limited_commercial_use() -> None:
    # RM-3 until 2024-05-26: NP from 10 p.m.; C from 10 p.m. to midnight for a § 186 use
    then = run("RM-3", D(2024, 5, 26), planning_use="restaurant", closing_hour="23:00")["T11"]
    assert then.control == "not_decided"
    assert then.missing_inputs == [tg.NOT_KNOWN["limited_commercial"]]
    now = run("RM-3", D(2024, 5, 27), planning_use="restaurant", closing_hour="23:00")["T11"]
    assert now.control == "not_permitted"
    assert (
        run("RM-3", D(2024, 5, 26), planning_use="restaurant", closing_hour="21:00")["T11"].control
        == "principal"
    )


# ---- a district the dated data does not carry -----------------------------------------------------------------------------
def test_district_outside_the_data_t1_reads_the_table_on_file() -> None:
    zone = zoning("NCD-UPPER FILLMORE", bar="conditional", restaurant="principal")
    on = D(2024, 6, 1)
    bar = run(None, on, zone=zone, planning_use="bar", story="first")["T1"]
    assert bar.control == "conditional"
    assert ids(bar) == ["zoning.use_control", "T1.not_carried"]
    assert "The dated rule table does not carry NCD-UPPER FILLMORE." in text_of(bar)
    assert bar.lines[0].citations == ["zoning:NCD-UPPER FILLMORE"]
    assert not bar.differs_today and bar.in_force_from is None
    assert run(None, on, zone=zone, planning_use="restaurant", story="first")["T1"].control == "principal"
    prohibited = zoning("RH-3", bar="prohibited", restaurant="prohibited")
    assert run(None, on, zone=prohibited, planning_use="bar", story="first")["T1"].control == "not_permitted"
    cafe = run(None, on, zone=zone, planning_use="limited_restaurant")["T1"]
    assert cafe.control == "not_decided" and cafe.missing_inputs == [NOT_CARRIED]
    unknown = run(None, on, zone=zoning("PDR-1-G"), planning_use="bar")["T1"]
    assert unknown.control == "not_decided" and unknown.missing_inputs == [NOT_CARRIED]


def test_district_outside_the_data_t1_counts_the_overlays_as_v1_does() -> None:
    zone = zoning("NCD-UPPER FILLMORE", bar="principal", restaurant="principal")
    on = D(2024, 6, 1)
    wet = run(None, on, THIRD, zone=zone, planning_use="bar", serves_alcohol=True, story="first")["T1"]
    assert wet.control == "not_permitted"
    assert "zoning.sud_control" in ids(wet)
    dry = run(None, on, THIRD, zone=zone, planning_use="bar", story="first")["T1"]
    assert dry.control == "principal"
    assert "not applied, because the concept serves no alcohol" in text_of(dry)


def test_district_outside_the_data_the_other_district_triggers() -> None:
    zone = zoning("NCD-UPPER FILLMORE", bar="conditional", restaurant="principal")
    on = D(2024, 6, 1)
    touched = run(
        None,
        on,
        zone=zone,
        planning_use=["restaurant", "nighttime_entertainment"],
        formula_retail=True,
        floor_area_sqft=3000,
        outdoor_area="rear_or_side",
        closing_hour="01:00",
    )
    for rule_id in ("T5", "T6", "T7", "T9", "T11"):
        assert touched[rule_id].control == "not_decided", rule_id
        assert touched[rule_id].missing_inputs == [NOT_CARRIED], rule_id
        assert "The dated rule table does not carry NCD-UPPER FILLMORE" in text_of(touched[rule_id])
    untouched = run(
        None, on, zone=zone, planning_use="restaurant", formula_retail=False, existing_use_stated="retail"
    )
    assert untouched["T5"].control == "principal"
    for rule_id in ("T6", "T9"):
        assert untouched[rule_id].control == "does_not_apply", rule_id
    assert untouched["T8"].control == "principal"  # not a district control
    assert untouched["T7"].missing_inputs == [MISSING_PHRASES["floor_area_sqft"], NOT_CARRIED]
    assert untouched["T11"].missing_inputs == [MISSING_PHRASES["closing"], NOT_CARRIED]
    # T3 reads the same table on file
    stays = run(
        None,
        on,
        zone=zone,
        planning_use="bar",
        existing_use_stated="bar",
        changes_existing_business="enlarge",
        story="first",
    )["T3"]
    assert stays.control == "conditional"
    unplaced = run(
        None,
        on,
        zone=zone,
        planning_use="bar",
        existing_use_stated="bar",
        changes_existing_business="enlarge",
    )["T3"]
    assert unplaced.control == "not_decided" and STORY in unplaced.missing_inputs


# review of 2026-11-12: the zoning control table on file gives one control and does not read it by story, so with
# no story given a district the dated data does not carry is not decided and names the story, whatever the table
# on file reads (a Conditional Use or not permitted included)
NOT_CARRIED_STORY = (
    "The dated rule table does not carry NCD-JAPANTOWN. The control above was read from the zoning control table "
    "on file, which gives today's control only and does not read it by story; the Planning Code may set a "
    "different control on another story. Which story the business is on is not given, so no story is assumed and "
    "this is not decided until it is."
)


def test_district_outside_the_data_with_no_story_given_is_not_decided_naming_the_story() -> None:
    on = D(2024, 6, 1)
    for bar in ("principal", "conditional", "prohibited"):
        zone = zoning("NCD-JAPANTOWN", bar=bar, restaurant="principal")
        found = run(None, on, zone=zone, planning_use="bar")["T1"]
        assert found.control == "not_decided", bar
        assert found.missing_inputs == [STORY], bar
        assert ids(found) == ["zoning.use_control", "T1.not_carried"], bar
        assert text_of(found).endswith(NOT_CARRIED_STORY), bar
        assert "first story" not in text_of(found).lower(), bar
    # a stated story is read as before
    zone = zoning("NCD-JAPANTOWN", bar="conditional", restaurant="principal")
    stated = run(None, on, zone=zone, planning_use="bar", story="first")["T1"]
    assert stated.control == "conditional" and stated.missing_inputs == []
    assert NOT_CARRIED_STORY not in text_of(stated)


def test_district_outside_the_data_whose_table_has_no_story_columns_needs_no_story() -> None:
    # RH-1 (Table 209.1, no story columns): the one control holds on every story, so no story is needed
    found = run(
        None,
        D(2024, 6, 1),
        zone=zoning("RH-1", bar="prohibited", restaurant="prohibited"),
        planning_use="bar",
    )
    assert found["T1"].control == "not_permitted" and found["T1"].missing_inputs == []
    assert ids(found["T1"]) == ["zoning.use_control", "T1.not_carried", "T1.story"]
    assert text_of(found["T1"]).endswith(
        "Which story the business is on is not given. The district's zoning control table has no story columns: "
        "it sets one control for a Bar on every story, so the story does not change this."
    )
    # an overlay's own control is read for the first story only: the story is named again
    zone = zoning("RH-1", bar="principal", restaurant="principal")
    wet = run(None, D(2024, 6, 1), THIRD, zone=zone, planning_use="bar", serves_alcohol=True)["T1"]
    assert wet.control == "not_decided" and wet.missing_inputs == [STORY]


def test_no_zoning_district_on_file() -> None:
    found = run(None, D(2024, 6, 1), planning_use="bar", closing_hour="01:00")
    assert found["T1"].control == "not_decided"
    assert found["T1"].missing_inputs == [tg.NOT_KNOWN["no_district"]]
    assert found["T11"].missing_inputs == [tg.NOT_KNOWN["no_district"]]
    assert found["T10"].control == "does_not_apply"


# ---- dates ----------------------------------------------------------------------------------------------------------------
def test_a_rules_date_before_the_data_starts_says_so() -> None:
    found = run("NCD-POLK", D(2021, 6, 1), planning_use="bar", story="first")
    assert found["T1"].control == "conditional"
    assert found["T1"].lines[-1].rule_id == "T1.before_start"
    assert found["T1"].lines[-1].text == (
        "The rule table starts on 2022-01-01. The data does not go back to 2021-06-01: the rules read the "
        "controls as they stood on 2022-01-01."
    )
    assert "T2.before_start" not in ids(found["T2"])  # nothing dated was read
    later = run("NCD-POLK", D(2022, 1, 1), planning_use="bar", story="first")
    assert all(not line.rule_id.endswith(".before_start") for f in later.values() for line in f.lines)


def test_historic_buildings_are_never_evaluated_and_the_line_says_so() -> None:
    given = {"planning_use": "bar", "story": "first"}
    before = run("NCT-MISSION", D(2026, 4, 10), **given)["T1"]
    after = run("NCT-MISSION", D(2026, 4, 11), **given)["T1"]
    # not decided on both days: the Table 754 Note 7 cap (corrected from "conditional")
    assert before.control == after.control == "not_decided"
    assert "T1.historic" not in ids(before)
    line = next(line for line in after.lines if line.rule_id == "T1.historic")
    assert line.code_section == "Planning Code § 202.11"
    assert line.text == (
        "From 2026-04-11 a qualifying Historic Building may read differently (Planning Code § 202.11). The "
        "Planning Director decides whether a building qualifies; the rules do not evaluate it."
    )
    assert controls.use_control("NCT-MISSION", "bar", "first", D(2026, 4, 11)).historic_buildings
    # the same line under T6 and T3, where they read a cell
    club = run("NCT-MISSION", D(2026, 6, 1), planning_use="nighttime_entertainment", story="first")["T6"]
    assert ("T6.historic" in ids(club)) == bool(
        controls.use_control(
            "NCT-MISSION", "nighttime_entertainment", "first", D(2026, 6, 1)
        ).historic_buildings
    )


def test_evaluate_reads_no_clock_and_accepts_a_datetime() -> None:
    concept = facts(planning_use="restaurant", story="first")
    a = tg.evaluate(concept, site(D(2023, 6, 1)), zoning("CVR"), [], rules_date=D(2023, 6, 1), today=TODAY)
    b = tg.evaluate(
        concept,
        site(D(2023, 6, 1)),
        zoning("CVR"),
        [],
        rules_date=dt.datetime(2023, 6, 1, 15, 30),
        today=dt.datetime(2026, 11, 10, 9, 0),
    )
    assert [f.model_dump_json() for f in a] == [f.model_dump_json() for f in b]


# ---- determinism ----------------------------------------------------------------------------------------------------------
def test_same_inputs_in_any_order_give_byte_identical_output() -> None:
    concept = facts(
        business_type="restaurant",
        planning_use=["restaurant", "nighttime_entertainment"],
        serves_alcohol=True,
        licence_type="41",
        formula_retail=True,
        floor_area_sqft=2600,
        story=["first", "second"],
        closing_hour="01:30",
        outdoor_area="rear_or_side",
        existing_use_stated=["retail", "vacant"],
    )
    rows = [MISSION, CALLE24, CENTRAL_SOMA, FRINGE, LOWER_HAIGHT, SOMA, MISSION]
    on = D(2025, 4, 15)

    def dump(overlays: list[Overlay]) -> str:
        found = tg.evaluate(
            concept, site(on), zoning("NCT-24TH-MISSION"), overlays, rules_date=on, today=TODAY
        )
        return json.dumps([f.model_dump() for f in found], sort_keys=False, ensure_ascii=False)

    first = dump(rows)
    rng = random.Random(7)
    for _ in range(12):
        shuffled = rows[:]
        rng.shuffle(shuffled)
        assert dump(shuffled) == first
    for order in itertools.permutations([MISSION, CALLE24, SOMA]):
        assert tg.special_district_keys(zoning("NCT-24TH-MISSION"), list(order)) == (
            "mission_alcohol_sud",
            "soma_youth_family_sud",
            "calle_24_sud",
        )
    assert dump(rows) == first  # and again: nothing is remembered between calls


_SWEEP: dict[str, list[Any]] = {
    "business_type": ["bar", "restaurant", "cafe", "hotel", "other"],
    "planning_use": [
        "bar",
        "restaurant",
        "limited_restaurant",
        "nighttime_entertainment",
        ["bar", "nighttime_entertainment"],
        ["restaurant", "bar"],
    ],
    "serves_alcohol": [True],
    "licence_type": ["41", "47", "42", "48", "75", "90", "40", "23"],
    "licences_already_held": ["41", "47", "48", ["41", "47"]],
    "alcohol_transaction": [
        "new_licence",
        "person_to_person_transfer",
        "premises_transfer",
        "licence_already_held",
    ],
    "formula_retail": [True, False],
    "floor_area_sqft": [900, 2500, 4000, 7000, 130000],
    "existing_use_stated": [
        "bar",
        "restaurant",
        "limited_restaurant",
        "retail",
        "laundromat",
        "vacant",
        "other",
        ["bar", "nighttime_entertainment"],
        ["restaurant", "vacant"],
    ],
    "changes_existing_business": ["none", "enlarge", "intensify", "enlarge_and_intensify"],
    "merges_storefronts": [True, False],
    "story": ["first", "second", "third_or_above", "basement", ["first", "second"]],
    "closing_hour": ["22:00", "23:30", "00:00", "01:30", "02:00", "03:00"],
    "entertainment_kind": ["none", "limited_live_performance", "place_of_entertainment"],
    "live_entertainment": [True],
    "outdoor_area": ["none", "front", "rear_or_side", "rooftop", "parking_lot", "sidewalk"],
    "amends_prior_approval": [True, False],
}
_SWEEP_DATES = [
    D(2021, 6, 1),
    D(2022, 1, 1),
    D(2023, 6, 2),
    D(2024, 1, 13),
    D(2024, 1, 14),
    D(2024, 5, 27),
    D(2025, 4, 7),
    D(2025, 10, 6),
    D(2025, 12, 15),
    D(2026, 4, 11),
    D(2026, 9, 1),
]


def test_a_sweep_of_facts_districts_dates_and_overlays_never_fails_and_keeps_the_invariants() -> None:
    """1,500 seeded combinations: evaluate answers every one, and every finding keeps its shape."""
    rng = random.Random(11)
    rows = [MISSION, HAIGHT, THIRD, SOMA, CALLE24, CENTRAL_SOMA, LOWER_HAIGHT, FRINGE]
    districts: list[str | None] = [*controls.districts(), "NCD-UPPER FILLMORE", None]
    emitted: set[str] = set()
    for _ in range(1500):
        given = {key: rng.choice(values) for key, values in _SWEEP.items() if rng.random() < 0.4}
        district, on = rng.choice(districts), rng.choice(_SWEEP_DATES)
        overlays = rng.sample(rows, rng.randint(0, 3))
        at = site(
            on,
            existing_use=rng.choice([None, None, "bar", "restaurant"]),
            licences=rng.choice([(), (), ("41",), ("48",)]),
            conditional_use_on=rng.choice([None, D(2019, 1, 1)]),
        )
        zone = zoning(
            district, bar=rng.choice(["unknown", "conditional", "prohibited"]), restaurant="principal"
        )
        found = tg.evaluate(facts(**given), at, zone, overlays, rules_date=on, today=TODAY)
        where = (district, on, given)
        assert [f.rule_id for f in found] == list(tg.ORDER), where
        for f in found:
            assert f.lines, where
            assert (f.control == "not_decided") <= bool(f.missing_inputs), (f.rule_id, where)
            assert f.control != "does_not_apply" or not f.missing_inputs, (f.rule_id, where)
            assert f.differs_today == (f"{f.rule_id}.differs" in ids(f)), (f.rule_id, where)
            assert len(set(f.missing_inputs)) == len(f.missing_inputs)
            for line in f.lines:
                assert "{" not in line.text and "None" not in line.text, line.text
                assert line.citations == sorted(set(line.citations))
                if ":" in line.rule_id:
                    emitted.add(line.rule_id.split(":", 1)[1])
        again = tg.evaluate(facts(**given), at, zone, overlays[::-1], rules_date=on, today=TODAY)
        assert [f.model_dump() for f in again] == [f.model_dump() for f in found], where
    # a line built around a special district rule always names a bound rule, and the sweep reaches most of them
    assert emitted <= set(tg.BOUND)
    assert len(emitted) >= len(tg.BOUND) - 4


# ---- which special districts cover an address -----------------------------------------------------------------------------
def test_special_district_keys_from_overlays_and_zoning() -> None:
    assert tg.special_district_keys(zoning("NCD-POLK"), []) == ()
    assert tg.special_district_keys(None, [MISSION]) == ("mission_alcohol_sud",)
    assert tg.special_district_keys(zoning("NCT-VALENCIA"), [MISSION, CALLE24]) == (
        "mission_alcohol_sud",
        "calle_24_sud",
    )
    assert tg.special_district_keys(zoning("NC-3"), [THIRD]) == ("third_street_alcohol_rud",)
    assert tg.special_district_keys(zoning("MUR"), [SOMA]) == ("soma_youth_family_sud",)
    old_soma = overlay("x:1", "SoMa Youth and Family Special Use District", "Planning Code § 249.40A")
    assert tg.special_district_keys(zoning("MUR"), [old_soma]) == ("soma_youth_family_sud",)
    assert tg.special_district_keys(zoning("NC-3"), [HAIGHT]) == ("haight_alcohol_rusd",)
    # coterminous with a zoning district, as the data's overlay_hint says
    assert tg.special_district_keys(zoning("NCD-HAIGHT"), []) == ("haight_alcohol_rusd",)
    assert tg.special_district_keys(zoning("NCD-NORTH BEACH"), []) == ("north_beach_sud",)
    # not coterminous: the zoning district alone shows nothing
    assert tg.special_district_keys(zoning("NCD-BAYVIEW"), []) == ()
    assert tg.special_district_keys(zoning("NCT-MISSION"), []) == ()


def test_special_district_keys_needs_the_section_and_the_name() -> None:
    assert tg.special_district_keys(zoning("NC-3"), [LOWER_HAIGHT, FRINGE, CENTRAL_SOMA]) == ()
    other_section = overlay("x:2", "Mission Alcoholic Beverage Special Use District", "Planning Code § 249.6")
    assert tg.special_district_keys(zoning("NC-3"), [other_section]) == ()
    other_name = overlay(
        "x:3", "Mission Street Formula Retail Restaurant Subdistrict", "Planning Code § 249.60"
    )
    assert tg.special_district_keys(zoning("NC-3"), [other_name]) == ()
    lower = overlay("x:4", "Lower Haight Street Alcohol Restricted Use District", "Planning Code § 781.9")
    assert tg.special_district_keys(zoning("NC-3"), [lower]) == ()
    north_beach = overlay("x:5", "North Beach Special Use District", "Planning Code § 780.3")
    assert tg.special_district_keys(zoning("NC-3"), [north_beach]) == ()  # keyed on the zoning district alone


def test_every_special_district_of_the_data_is_matched_or_left_out_for_a_reason(raw: dict[str, Any]) -> None:
    matched = [m.key for m in tg.MATCHES]
    assert matched == [k for k in raw["special_districts"] if k not in tg.NOT_MATCHED]
    assert set(matched) | set(tg.NOT_MATCHED) == set(raw["special_districts"])
    assert set(tg._RULE_PREFIX) == set(matched)
    for match in tg.MATCHES:
        assert match.why
        hint = raw["special_districts"][match.key]["overlay_hint"]
        for district in match.districts:
            assert district in hint and "coterminous" in hint
    assert raw["special_districts"]["lower_haight_alcohol_rud"]["reaches_bars_or_restaurants"] is False


# ---- the binding table against the data -------------------------------------------------------------------------------------
def test_every_rule_of_a_matched_special_district_is_bound_or_unbound_for_a_reason(
    raw: dict[str, Any],
) -> None:
    in_data = {
        rule["rule_id"]
        for key, special in raw["special_districts"].items()
        if key not in tg.NOT_MATCHED
        for rule in special["rules"]
    }
    assert set(tg.BOUND) | set(tg.UNBOUND) == in_data
    assert not set(tg.BOUND) & set(tg.UNBOUND)
    assert len(tg.BOUND) == len(tg.BINDINGS)
    for binding in tg.BINDINGS:
        assert binding.why
        prefix = binding.rule_id.split(".", 1)[0]
        assert prefix in tg._RULE_PREFIX.values()
    assert all(tg.UNBOUND.values())


def test_bindings_agree_with_the_data(raw: dict[str, Any]) -> None:
    versions: dict[str, list[dict[str, Any]]] = {}
    for special in raw["special_districts"].values():
        for rule in special["rules"]:
            versions.setdefault(rule["rule_id"], []).append(rule)
    for binding in tg.BINDINGS:
        for version in versions[binding.rule_id]:
            # a requirement in the data is bound as one, and nothing else is
            assert binding.requirement == (version["control"] == "requirement"), binding.rule_id
            start = version["from"]
            types = binding.types if binding.types_by_start is None else binding.types_by_start[start]
            if binding.kind == "adds_licence" and version["control"] == "P":
                types = frozenset()  # the version after the repeal: no control left, so it names no type
            words = version["applies_to"] + " " + version["rule"]
            for number in types:
                assert re.search(rf"\b0?{int(number)}\b", words), (binding.rule_id, number)
            if binding.prior_use is not None:
                assert start in binding.prior_use, binding.rule_id
                for use in binding.prior_use[start]:
                    assert tg.USE_LABELS[use] in version["rule"], (binding.rule_id, use)
            if binding.first_story and version["control"] != "P":
                assert "First Story" in words or "ground level" in words, binding.rule_id
        if binding.with_rule or binding.overrides:
            assert (binding.with_rule or binding.overrides) in tg.BOUND
    # the on-sale types are the ones the districts' own definitions list
    for definition, rule_id in (
        ("haight.on_sale_definition", "haight.new_on_sale_establishment"),
        ("third.on_sale_definition", "third.new_on_sale_establishment"),
    ):
        listed = set(re.findall(r"\b\d{2}\b", versions[definition][0]["applies_to"]))
        assert listed == set(tg.BOUND[rule_id].types)
    assert tg.BOUND["mission.new_bar_licence_from_bar_in_district"].could_stop
    assert [b.rule_id for b in tg.BINDINGS if b.could_stop] == [
        "mission.new_bar_licence_from_bar_in_district"
    ]


def test_north_beach_hours_rule_is_the_districts_own_hours_row(raw: dict[str, Any]) -> None:
    """Why north_beach.hours is unbound: T11 reads the same windows from the district row."""
    for rule in raw["special_districts"]["north_beach_sud"]["rules"]:
        if rule["rule_id"] != "north_beach.hours":
            continue
        for day in (rule["from"], rule["to"]):
            on = D.fromisoformat(day) if day else None
            row = controls.hours("NCD-NORTH BEACH", on)
            not_permitted = [
                [w.permission, w.start, w.end] for w in row.windows if w.permission == "not_permitted"
            ]
            assert not_permitted == [["not_permitted", 120, 360]]
        assert [list(w) for w in rule["windows"] if w[0] == "NP"] == [["NP", "02:00", "06:00"]]


def test_every_extra_field_of_a_district_row_is_read_or_is_bookkeeping(raw: dict[str, Any]) -> None:
    typed = {
        "use": {"first", "second", "third"},
        "formula_retail": {"control", "applies_to", "not_permitted_for"},
        "use_size": {
            "principal_below_sqft",
            "not_permitted_from_sqft",
            "exemption",
            "division_of_large_uses",
        },
        "outdoor_activity_area": {"in_front", "elsewhere", "elsewhere_principal_if_202_2_a_7"},
        "hours": {"windows"},
    }
    provenance = {"from", "to", "note", "ordinance", "quote", "url", "read_on"}
    seen: dict[str, set[str]] = {kind: set() for kind in typed}
    exceptions: set[str] = set()
    for district in raw["districts"].values():
        for row, row_versions in district["rows"].items():
            kind = "use" if row in controls.USES else row
            for version in row_versions:
                seen[kind] |= set(version) - typed[kind] - provenance
                if kind == "use":
                    exceptions |= set(version.get("exceptions") or {})
    for kind, keys in seen.items():
        unread = keys - tg.EXTRA_KEYS_READ[kind] - tg.EXTRA_KEYS_BOOKKEEPING
        assert not unread, f"{kind}: no trigger reads {sorted(unread)}"
        assert tg.EXTRA_KEYS_READ[kind] <= keys, kind
    assert exceptions == set(tg.TABLE_EXCEPTIONS)
    assert set(tg.OVERRIDE_DISTRICTS) == {
        name
        for name, district in raw["districts"].items()
        for row in controls.USES
        for version in district["rows"][row]
        if version.get("special_district_override")
    }
    only_if = raw["districts"]["C-3-G"]["rows"]["use_size"][0]["not_permitted_only_if"]
    assert f"over {tg.ONLY_IF_OVER_SQFT:,} gross sq ft" in only_if
    bayview = raw["districts"]["NCD-BAYVIEW"]["rows"]["bar"][1]["exceptions"]
    assert bayview["bar_with_abc_licence_type_42"] == "C (first and second story)"
    assert tg.TABLE_EXCEPTIONS["bar_with_abc_licence_type_42"].columns == ("first", "second")


def test_the_fixed_tables_are_whole() -> None:
    for key, fixed in tg.TEXT.items():
        assert fixed.text.strip() == fixed.text and fixed.text[-1] in ".:)}", key
        assert not re.search(r"\blicenses?\b", fixed.text.lower()), key  # the noun is spelt "licence"
        for _, field, _, _ in string.Formatter().parse(fixed.text):
            assert field is None or field.isidentifier(), key
    for key, phrase in tg.NOT_KNOWN.items():
        assert phrase and phrase[0] == phrase[0].lower() and not phrase.endswith("."), key
    assert tg.NOT_KNOWN["district_not_carried"] == NOT_CARRIED
    assert set(tg.FAMILIES) == set(tg.ORDER)
    assert [tg.FAMILIES[t] for t in tg.ORDER] == list(TRIGGER_LABELS)
    for sub in tg.SUBAREAS.values():
        assert sub.not_known in tg.NOT_KNOWN and all(controls.covers(d) for d in sub.districts)
    for known in tg.TABLE_EXCEPTIONS.values():
        assert known.not_known in tg.NOT_KNOWN


# ---- what the row rules read (spec section 4) ---------------------------------------------------------------------------------
def _finding(rule_id: str, control: str, *missing: str) -> TriggerFinding:
    family = tg.FAMILIES[rule_id]
    return TriggerFinding(
        rule_id=rule_id,
        family=family,
        label=TRIGGER_LABELS[family],
        control=control,  # type: ignore[arg-type]
        missing_inputs=list(missing),
        lines=[RuleLine(rule_id=f"{rule_id}.x", text="A line.", code_section=None)],
    )


def test_matters_and_the_small_helpers() -> None:
    found = [
        _finding("T1", "principal"),
        _finding("T2", "code_and_practice_differ"),
        _finding("T5", "not_decided", "the chain", "the floor area"),
        _finding("T7", "not_decided", "the floor area"),
        _finding("T8", "does_not_apply"),
        _finding("T9", "conditional", "an input named although the trigger is decided"),
        _finding("T11", "not_permitted"),
    ]
    assert [f.rule_id for f in found if tg.matters(f)] == ["T2", "T5", "T7", "T9", "T11"]
    assert [f.rule_id for f in tg.not_permitted(found)] == ["T11"]
    assert [f.rule_id for f in tg.conditional(found)] == ["T9"]
    assert [f.rule_id for f in tg.not_decided(found)] == ["T5", "T7"]
    assert [f.rule_id for f in tg.practice_differs(found)] == ["T2"]
    assert tg.missing_inputs(found) == ("the chain", "the floor area")
    assert tg.by_id(found, "T7").control == "not_decided"


def test_zoning_outcome_follows_the_order_of_spec_section_4() -> None:
    np_, c, nd, differ, p = (
        _finding("T11", "not_permitted"),
        _finding("T1", "conditional"),
        _finding("T5", "not_decided", "the chain"),
        _finding("T2", "code_and_practice_differ"),
        _finding("T7", "principal"),
    )
    everything = tg.zoning_outcome([p, differ, nd, c, np_])
    assert (everything.status, everything.status_note, everything.deciding) == ("not_permitted", None, (np_,))
    assert tg.zoning_outcome([p, differ, nd, c]).status == "further_review"
    assert tg.zoning_outcome([p, differ, nd, c]).deciding == (c,)
    missing = tg.zoning_outcome([p, differ, nd])
    assert (missing.status, missing.missing_inputs) == ("insufficient_information", ("the chain",))
    practice = tg.zoning_outcome([p, differ])
    assert (practice.status, practice.status_note) == ("further_review", tg.PRACTICE_DIFFERS_NOTE)
    allowed = tg.zoning_outcome([p, _finding("T8", "does_not_apply")])
    assert (allowed.status, allowed.deciding, allowed.missing_inputs) == ("allowed", (), ())


# ---- the 40 backtest cases --------------------------------------------------------------------------------------------------
INPUTS = json.loads((ROOT / "backtest" / "inputs.json").read_text(encoding="utf-8"))["cases"]
INVENTORY = {
    c["id"]: c for c in json.loads((ROOT / "backtest" / "triggers.json").read_text(encoding="utf-8"))["cases"]
}
_SECTION = re.compile(r"§\s*([0-9]+(?:\.[0-9]+)?[A-Z]?)")


def district_code(at_filing: str) -> str:
    """'NCD-POLK (Polk Street NCD, § 723)' -> 'NCD-POLK': the longest district code of the data it starts with."""
    for code in sorted(controls.districts(), key=len, reverse=True):
        if at_filing.startswith(code):
            return code
    raise AssertionError(f"no district of the data in {at_filing!r}")


def case_overlays(case_id: str, special_districts: list[str]) -> list[Overlay]:
    """One overlay for each special district the inventory names, with the sections its text gives."""
    return [
        overlay(
            f"case:{case_id}:{i}",
            name,
            "Planning Code " + ", ".join(f"§ {section}" for section in _SECTION.findall(name)),
            kind="alcohol_sud" if "alcohol" in name.lower() else "special_use_district",
        )
        for i, name in enumerate(special_districts)
    ]


def test_the_backtest_has_40_cases_in_districts_the_data_carries() -> None:
    assert len(INPUTS) == 40 and set(INPUTS) == set(INVENTORY)
    assert {district_code(c["zoning_district_at_filing"]) for c in INVENTORY.values()} <= set(
        controls.districts()
    )


@pytest.mark.parametrize("case_id", sorted(INPUTS))
def test_every_backtest_case_returns_eleven_findings(case_id: str) -> None:
    case, inventory = INPUTS[case_id], INVENTORY[case_id]
    on = D.fromisoformat(case["rules_date"])
    assert on == D.fromisoformat(case["filed"]) - dt.timedelta(days=1)
    found = tg.evaluate(
        concept_facts_from_facts(case["record_facts"]),
        site(on),
        zoning(district_code(inventory["zoning_district_at_filing"])),
        case_overlays(case_id, inventory["special_districts"]),
        rules_date=on,
        today=TODAY,
    )
    assert [f.rule_id for f in found] == list(tg.ORDER)
    for f in found:
        assert f.lines and all(line.text for line in f.lines)
        assert (f.control == "not_decided") <= bool(f.missing_inputs)
        assert f.differs_today == any(line.rule_id == f"{f.rule_id}.differs" for line in f.lines)
        TriggerFinding.model_validate(f.model_dump())
    tg.zoning_outcome(found)
    # and from the neutral description's facts, which state less
    again = tg.evaluate(
        concept_facts_from_facts(case["input_facts"]),
        site(on),
        zoning(district_code(inventory["zoning_district_at_filing"])),
        case_overlays(case_id, inventory["special_districts"]),
        rules_date=on,
        today=TODAY,
    )
    assert [f.rule_id for f in again] == list(tg.ORDER)
