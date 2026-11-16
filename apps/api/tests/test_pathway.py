"""The rule engine in app.memo.pathway (rule table v2): the pathway and every row's status are set by rules,
from the facts and the dated control data.

No database, no model. The zoning and overlay rows are synthetic and mirror the fields of the rows on file for
the districts they name. The controls themselves are not typed here: the rules read them from the dated
control data by the district's code, for the rules date, so these tests use real district codes (and one code
the data does not carry, where the rules fall back on the zoning control table on file).

The trigger rules and the alcohol, building and entertainment rows have their own test files
(tests/test_triggers.py, tests/test_rows.py). This file tests what the entry point adds: the zoning row of spec
section 4, the pathway, the health and outdoor rows, the dates, the open questions, the overall line and the
entitlement path, and that the pieces fit.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import random
import re
from pathlib import Path
from typing import Any, get_args

import precedent
import pytest
from precedent.models import Application, Overlay
from precedent.store.base import ZoningInfo

from app.memo import controls, triggers
from app.memo import pathway as pw
from app.memo import rows as row_rules
from app.memo.facts import concept_facts, site_facts
from app.memo.pathway import (
    LEGAL_BASIS,
    LICENCE_TYPES,
    NO_PATH,
    NOTE_PREFIX,
    NOTHING_TO_FILE,
    HoursControl,
    HoursWindow,
    closing_bucket,
    determine,
    entitlement_path,
    existing_use,
    licence_type,
    overall_line,
    parse_hours,
    planning_use,
)
from app.memo.report import Site, SiteMatch, SiteRecord, site_of
from app.memo.tracts import PCN_STATUS_NOTE
from app.models.memo import (
    APPROVAL_AREA_LABELS,
    CHANGE_OF_USE_LABELS,
    PLANNING_USE_LABELS,
    STATUS_SEVERITY,
    TRIGGER_LABELS,
    USE_PERMISSION_LABELS,
    ApprovalArea,
    Determinations,
    OpenQuestion,
    RowDetermination,
    RuleLine,
    TriggerFinding,
)
from app.models.profile import BusinessProfile, BusinessType

NOW = dt.datetime(2026, 11, 10, tzinfo=dt.UTC)
ALL_AREAS: list[ApprovalArea] = [
    "zoning_use",
    "alcohol",
    "entertainment",
    "health",
    "building_change_of_use",
    "outdoor",
]
SITE_995 = site_of("995 Valencia St, San Francisco, CA 94110", "995 VALENCIA ST", "3609/026")
HOURS_2AM = "Hours of operation: P 6 a.m.–2 a.m.; C 2 a.m.–6 a.m."
HOURS_11PM = "Hours of operation: P 6 a.m.–11 p.m.; C 11 p.m.–2 a.m."
STATIC_RULES = Path(precedent.__file__).parent / "static" / "sf_overlay_rules.json"


# ---- builders ------------------------------------------------------------------------------------------
def profile(business_type: BusinessType = "bar", **kw: Any) -> BusinessProfile:
    return BusinessProfile(business_type=business_type, **kw)


# These four are on the first story, stated: no story is ever assumed (a missing one is not decided), and the
# tests that use them are about other rules. WINE_BAR_NO_STORY is the wine bar with no story given.
WINE_BAR = profile(
    "bar",
    serves_alcohol=True,
    alcohol_type="beer_wine",
    closes_after_midnight=True,
    live_entertainment=True,
    stories=["first"],
)
WINE_BAR_NO_STORY = WINE_BAR.model_copy(update={"stories": []})
COCKTAIL_BAR = profile("bar", serves_alcohol=True, alcohol_type="full_liquor", stories=["first"])
RESTAURANT = profile("restaurant", serves_alcohol=True, alcohol_type="beer_wine", stories=["first"])
DRY_RESTAURANT = profile("restaurant", stories=["first"])


def zoning(
    district: str = "NCT-VALENCIA",
    *,
    bar: str = "conditional",
    restaurant: str = "principal",
    section: str = "Planning Code § 762 (Zoning Control Table 762); § 102 (Bar, Restaurant)",
    rules: str = "Bar requires Conditional Use Authorization; Restaurant principally permitted (First Story).",
    name: str = "Valencia Street Neighborhood Commercial Transit District",
) -> ZoningInfo:
    return ZoningInfo(
        district=district,
        name=name,
        code_section=section,
        bar_permission=bar,
        restaurant_permission=restaurant,
        rules=rules,
        source_url=f"https://example.org/zoning/{district}",
    )


def overlay(
    overlay_id: str,
    kind: str,
    name: str,
    *,
    bar: str = "unknown",
    restaurant: str = "unknown",
    section: str = "",
    rules: str = "",
    hours: str | None = None,
    district_codes: tuple[str, ...] = (),
) -> Overlay:
    return Overlay.model_validate(
        {
            "id": overlay_id,
            "kind": kind,
            "name": name,
            "rules": rules,
            "code_section": section,
            "district_codes": list(district_codes),
            "bar_permission": bar,
            "restaurant_permission": restaurant,
            "late_night_rule": hours,
            "source": "static",
            "source_url": f"https://example.org/overlay/{overlay_id}",
            "fetched_at": NOW,
        }
    )


def district_row(
    district: str = "NCT-VALENCIA",
    *,
    bar: str = "conditional",
    restaurant: str = "principal",
    section: str = "Planning Code § 762 (zoning control table for NCT-VALENCIA)",
    hours: str | None = HOURS_2AM,
) -> Overlay:
    """The district's own zoning_district row, as the store returns it among the overlays."""
    return overlay(
        f"datasf_zoning:{district}",
        "zoning_district",
        district,
        bar=bar,
        restaurant=restaurant,
        section=section,
        rules=f"{district}: first-story controls.",
        hours=hours,
        district_codes=(district,),
    )


MISSION_SUD = overlay(
    "datasf_sud:mission_alcohol_restrict",
    "alcohol_sud",
    "Mission Alcoholic Beverage Special Use District",
    bar="conditional",
    restaurant="principal",
    section="Planning Code § 249.60 (§ 781.8 cross-references it)",
    rules="A new or relocated Bar is considered only as a Conditional Use, and must use a liquor license "
    "transferred from another Bar within the SUD. East of the western boundary of the Mission Street NCT, any "
    "new Restaurant requires CU.",
)
THIRD_ST_RUD = overlay(
    "datasf_sud:3rd_st_alcohol_restrict",
    "alcohol_sud",
    "Third Street Alcohol Restricted Use District",
    bar="prohibited",
    restaurant="principal",
    section="Planning Code § 249.62 (§ 782 cross-references it)",
    rules="No new on-sale liquor establishments.",
)
HAIGHT_RUSD = overlay(
    "datasf_sud:haight_street_alcohol_restricted_use",
    "alcohol_sud",
    "Haight Street Alcohol Restricted Use Subdistrict",
    bar="conditional",
    restaurant="conditional",
    section="Planning Code § 781.9",
    rules="Alcohol service needs Conditional Use.",
)
TARAVAL = overlay(
    "datasf_sud:taraval_street_restaurant_subdistrict",
    "special_use_district",
    "Taraval Street Restaurant Subdistrict",
    restaurant="principal",
    section="Planning Code § 781.1",
    rules="Restaurants and Limited Restaurants are P on the First Story and below.",
)
FRINGE = overlay(
    "datasf_sud:fringe_financial_services_rud",
    "special_use_district",
    "Fringe Financial Services RUD",
    section="Planning Code § 249.35",
    rules="No new fringe financial services.",
)
NC_RULE_VALENCIA = overlay(
    "static:sf:nc_nct_valencia",
    "nc_rule",
    "Valencia Street Neighborhood Commercial Transit District",
    bar="conditional",
    restaurant="principal",
    section="Planning Code § 762 (Zoning Control Table 762); § 102 (Bar, Restaurant)",
    rules="Bar requires Conditional Use Authorization; Restaurant principally permitted (First Story).",
    hours="Hours of operation (Table 762): P 6 a.m.–2 a.m.; C 2 a.m.–6 a.m.",
    district_codes=("NCT-VALENCIA",),
)
VALENCIA_OVERLAYS = [MISSION_SUD, NC_RULE_VALENCIA, FRINGE, district_row()]


def licence(
    source_id: str,
    number: str,
    address: str = "995 VALENCIA ST, SAN FRANCISCO, CA 94110",
    *,
    status: str = "ACTIVE",
    matched: SiteMatch = "address",
    distance_m: float = 0.0,
    label: str | None = None,
    license_type: str | None = "",
) -> SiteRecord:
    """An ABC licence record at the site. `license_type=""` fills the type number in; None leaves it out."""
    app = Application(
        id=f"abc:{source_id}",
        source="abc",
        source_id=source_id,
        source_url=f"https://example.org/abc/{source_id}",
        fetched_at=NOW,
        kind="abc_license",
        permit_type=label or f"Type {number} – On-Sale",
        license_type=number if license_type == "" else license_type,
        status=status,
        address=address,
        parcel="3609/026",
        outcome="approved",
    )
    return SiteRecord(app, distance_m, matched)


TYPE_41_AT_995 = licence("651564", "41", label="Type 41 – On-Sale Beer & Wine - Eating Place")
TYPE_48_AT_995 = licence("700048", "48", label="Type 48 – On-Sale General - Public Premises")
TYPE_42_AT_995 = licence("700042", "42", label="Type 42 – On-Sale Beer & Wine - Public Premises")
TYPE_41_AT_999 = licence("700999", "41", "999 VALENCIA ST, SAN FRANCISCO, CA 94110", matched="parcel")


TODAY = dt.date(2026, 11, 10)


def run(
    prof: BusinessProfile = WINE_BAR,
    *,
    z: ZoningInfo | None = None,
    overlays: list[Overlay] | None = None,
    records: list[SiteRecord] | None = None,
    site: Site = SITE_995,
    areas: list[ApprovalArea] | None = None,
    no_zoning: bool = False,
    today: dt.date = TODAY,
    rules_date: dt.date | None = None,
    tract: str | None = None,
) -> Determinations:
    return determine(
        prof,
        None if no_zoning else (z or zoning()),
        VALENCIA_OVERLAYS if overlays is None else overlays,
        records or [],
        site,
        ALL_AREAS if areas is None else areas,
        today=today,
        rules_date=rules_date,
        tract=tract,
    )


def row(d: Determinations, area: str) -> RowDetermination:
    return next(r for r in d.rows if r.area == area)


def trigger(d: Determinations, rule_id: str) -> TriggerFinding:
    return next(f for f in d.pathway.triggers if f.rule_id == rule_id)


def controls_of(d: Determinations) -> dict[str, str]:
    """The triggers that apply, by id."""
    return {f.rule_id: f.control for f in d.pathway.triggers if f.control != "does_not_apply"}


def texts(lines: list[RuleLine]) -> list[str]:
    return [line.text for line in lines]


def rule_ids(lines: list[RuleLine]) -> list[str]:
    return [line.rule_id for line in lines]


def all_lines(d: Determinations) -> list[RuleLine]:
    return [
        *d.pathway.lines,
        *d.pathway.notes,
        *(line for f in d.pathway.triggers for line in f.lines),
        *(line for r in d.rows for line in (*r.basis, *r.referral_steps)),
    ]


def given(prof: BusinessProfile, **fields: Any) -> BusinessProfile:
    """The profile with more inputs stated."""
    return prof.model_copy(update=fields)


# The inputs rule table v2 reads that a short description leaves out, stated: an independent business of 1,000
# square feet on the first story (no story is ever assumed: a missing one is not decided).
STATED = {"formula_retail": False, "square_feet": 1000, "stories": ["first"]}
TRANSACTION = (
    "how the liquor licence will be obtained (new, or a transfer from another owner or another location)"
)
CHAIN = "whether the business is part of a chain that shares its name, look or menu with other locations"
FLOOR_AREA = "the floor area of the business, in square feet"
CLOSING = "the closing time"
LAST_USE = "what the space was last used as"
UNDER_50 = "whether the space is for fewer than 50 people"
NOT_CARRIED = "the rule table does not carry this zoning district"
PRACTICE_NOTE = "Code and Planning practice differ"
# Real districts the dated control data carries (read for TODAY):
C2 = zoning("C-2", section="Planning Code § 210.1")  # every use P, formula retail P, no hours limit
NCT3 = zoning("NCT-3", section="Planning Code § 752")  # Bar and Restaurant P, formula retail C, size 6,001
PACIFIC = zoning("NCD-PACIFIC", section="Planning Code § 726")  # Bar NP; P 6 a.m. to 10 p.m.; C to 2 a.m.
POLK = zoning("NCD-POLK", section="Planning Code § 723")  # Bar C; Nighttime Entertainment C until 2024-05-26
UMU = zoning("UMU", section="Planning Code § 838")  # Restaurant P
MISSION = zoning("NCT-MISSION", section="Planning Code § 754")  # Restaurant C; outdoor area elsewhere C
RH2 = zoning("RH-2", section="Planning Code § 209.1")  # every use NP
# A code the dated control data does not carry: the rules then read the zoning control table on file.
NCT2_CODE = "NCT-2"


def not_carried(bar: str = "conditional", restaurant: str = "principal") -> ZoningInfo:
    return zoning(NCT2_CODE, bar=bar, restaurant=restaurant, section="Planning Code § 751")


# ---- 995 Valencia St, wine bar: the whole answer ---------------------------------------------------------
def test_995_valencia_wine_bar_lines_statuses_and_overall() -> None:
    # on the first story, stated (as "ground-floor" states it): read exactly as before the decision of 2026-11-12
    d = run(WINE_BAR, records=[TYPE_41_AT_995, TYPE_41_AT_999])
    p = d.pathway
    assert (p.use, p.district, p.permission, p.existing_use, p.change_of_use) == (
        "bar",
        "NCT-VALENCIA",
        "conditional",
        "restaurant",
        "yes",
    )
    assert (p.use_label, p.permission_label, p.change_of_use_label) == (
        "Bar",
        "Conditional use",
        "Change of use",
    )
    assert p.rules_date == "2026-11-10" and [f.rule_id for f in p.triggers] == list(triggers.ORDER)
    assert controls_of(d) == {
        "T1": "conditional",
        "T2": "conditional",
        "T4": "principal",
        "T5": "not_decided",
        "T6": "not_decided",
        "T7": "not_decided",
        "T11": "principal",
    }
    # the pathway's lines: the use, the three triggers that give the control for a new use, the change of use
    assert rule_ids(p.lines) == [
        "zoning.use",
        "T1.cell",
        "T1.historic",
        "T2:mission.new_or_relocated_bar",
        "T4:mission.new_bar_licence_from_bar_in_district",
        "T4:mission.good_neighbor_policies",
        "T11.principal",
        "zoning.existing_use",
        "zoning.change_of_use",
    ]
    assert texts(p.lines)[:2] == [
        "The concept is looked up as a Bar (Planning Code § 102).",
        "Zoning district NCT-VALENCIA: a Bar on the first story is a conditional use (Planning Code § 762, in "
        "force since before 2022-01-01).",
    ]
    assert texts(p.lines)[-2:] == [
        "An active ABC Type 41 licence (on-sale beer and wine, eating place) is on file at 995 Valencia St. "
        "That is a licence type a Restaurant holds (Planning Code § 102), so the rules read the space as a "
        "Restaurant; other uses can hold it too.",
        "Restaurant to Bar is a change of use.",
    ]
    assert p.lines[1].citations == ["zoning:NCT-VALENCIA"]
    assert p.lines[3].citations == ["overlay:datasf_sud:mission_alcohol_restrict"]
    assert p.lines[-1].citations == p.lines[-2].citations == ["app:abc:651564"]
    assert p.lines[-2].source_url == "https://example.org/abc/651564"

    assert [(r.area, r.status, r.status_note) for r in d.rows] == [
        ("zoning_use", "further_review", None),
        ("alcohol", "insufficient_information", None),
        ("entertainment", "further_review", None),
        ("health", "allowed", None),
        ("building_change_of_use", "further_review", None),
        ("outdoor", "further_review", None),
    ]
    zoning_row = row(d, "zoning_use")
    assert zoning_row.approval == "Conditional Use Authorization (Planning Code § 303)"
    assert zoning_row.agency == "San Francisco Planning"
    # the zoning row: the use, every trigger that applies in order, the change of use, the status
    applying = [line for f in p.triggers if f.control != "does_not_apply" for line in f.lines]
    assert zoning_row.basis == [p.lines[0], *applying, *p.lines[-2:], zoning_row.basis[-1]]
    assert zoning_row.basis[-1].text == (
        "The concept as described needs a Conditional Use Authorization here. What asks for one: use control "
        "of the zoning district and use control of a special use district. Not decided as well: formula "
        "retail, nighttime entertainment and use size; the lines above name what is missing: further review."
    )
    assert zoning_row.basis[-1].code_section == "Planning Code § 303"
    assert zoning_row.basis[-1].citations == [
        "overlay:datasf_sud:mission_alcohol_restrict",
        "zoning:NCT-VALENCIA",
    ]
    alcohol = row(d, "alcohol")
    assert alcohol.missing_inputs == [TRANSACTION]
    assert rule_ids(alcohol.basis) == [
        "alcohol.licence",
        "T4:mission.new_bar_licence_from_bar_in_district",
        "alcohol.status",
    ]
    assert alcohol.basis[-1].text == (
        f"The description does not give {TRANSACTION}, so the rules cannot say which licence rules apply: "
        "insufficient information."
    )
    assert d.overall_status == "further_review"
    assert [q.question for q in d.open_questions] == [
        f"Not known: {CHAIN}. Needed for: zoning and use.",
        "Not known: whether there is entertainment, and what kind. Needed for: zoning and use.",
        f"Not known: {FLOOR_AREA}. Needed for: zoning and use.",
        f"Not known: {TRANSACTION}. Needed for: alcohol licence.",
    ]


STORY = "which stories the business occupies"


def test_995_valencia_wine_bar_with_no_story_is_insufficient_information_naming_it() -> None:
    """The user's decision of 2026-11-12: "MISSING STORY: always 'Insufficient information', naming it. Never
    default to the first story." The first story would need a Conditional Use (T1) and the Mission district's
    rule asks for one on any story (T2); with no story given the zoning row is still insufficient information,
    and no first-story line is printed."""
    d = run(WINE_BAR_NO_STORY, records=[TYPE_41_AT_995, TYPE_41_AT_999])
    p = d.pathway
    assert (p.permission, p.permission_label) == ("not_covered", "Not decided by the rules")
    assert controls_of(d) == {
        "T1": "not_decided",
        "T2": "conditional",
        "T4": "principal",
        "T5": "not_decided",
        "T6": "not_decided",
        "T7": "not_decided",
        "T11": "principal",
    }
    t1 = trigger(d, "T1")
    assert t1.missing_inputs == [STORY] and rule_ids(t1.lines) == ["T1.story", "T1.historic"]
    assert t1.lines[0].text == (
        "Zoning district NCT-VALENCIA: the table sets a different control for a Bar on different stories. Which "
        "story the business is on is not given, so no story is assumed and this is not decided until it is "
        "(Planning Code § 762, in force since before 2022-01-01)."
    )
    assert trigger(d, "T6").missing_inputs == ["whether there is entertainment, and what kind", STORY]
    assert not any(
        "first story" in line.text.lower() for line in all_lines(d) if line.rule_id != "zoning.note"
    )
    zoning_row = row(d, "zoning_use")
    assert zoning_row.status == "insufficient_information"
    assert zoning_row.approval == "Use authorization (not decided: an input is missing)"
    assert zoning_row.missing_inputs == [
        STORY,
        CHAIN,
        "whether there is entertainment, and what kind",
        FLOOR_AREA,
    ]
    assert zoning_row.basis[-1].text == (
        "The rules could not decide: use control of the zoning district, formula retail, nighttime entertainment "
        f"and use size. What is missing: {'; '.join(zoning_row.missing_inputs)}. No story is assumed, so until "
        "that is known the rules cannot say what zoning asks of the concept, although use control of a special "
        "use district already asks for a Conditional Use Authorization: insufficient information."
    )
    assert d.open_questions[0].question == f"Not known: {STORY}. Needed for: zoning and use."
    assert "Conditional Use Authorization" not in d.entitlement_path


def test_overall_line_and_entitlement_path_are_computed_from_the_rows() -> None:
    d = run(WINE_BAR, records=[TYPE_41_AT_995], areas=ALL_AREAS[:5])
    # the headline findings first (rule 9): two triggers ask for a Conditional Use; formula retail would if the
    # business is a chain of eleven or more; the use size one would if the floor area is at or over the threshold
    # and, the space being an existing Restaurant (the Type 41), it grows or storefronts are merged
    assert d.overall_line == (
        "A Conditional Use Authorization is needed (use control of the zoning district and use control of a "
        "special use district). A Conditional Use Authorization is needed if the business is part of a chain with "
        "eleven or more other locations (formula retail). A Conditional Use Authorization is needed if the floor "
        "area is 3,001 square feet or more and either the floor area grows or storefronts are merged (use size). "
        "Of the 5 approvals this concept needs: 3 further review (zoning and use, entertainment permit, building "
        "permit and change of use), 1 insufficient information (alcohol licence), 1 allowed (health permit)."
    )
    # the alcohol row is not decided, so the path names no licence
    assert d.entitlement_path == (
        "Conditional Use Authorization (Planning Code § 303); Place of Entertainment, Limited Live Performance "
        "or Fixed Place Outdoor Amplified Sound permit; Health permit to operate; Building permit with change "
        "of use"
    )
    assert d.overall_line == overall_line(d.rows, d.headline_findings)
    assert d.entitlement_path == entitlement_path(d.rows)
    # with the licence stated as new, the Mission requirement makes the row a potential blocker, and it is listed
    blocked = run(
        given(WINE_BAR, alcohol_transaction="new_licence"), records=[TYPE_41_AT_995], areas=ALL_AREAS[:5]
    )
    assert blocked.overall_line.endswith(
        "Of the 5 approvals this concept needs: 1 potential blocker (alcohol licence), 3 further review (zoning "
        "and use, entertainment permit, building permit and change of use), 1 allowed (health permit)."
    )
    assert "ABC licence, Type 42 (on-sale beer and wine, public premises); " in blocked.entitlement_path
    one = run(DRY_RESTAURANT, areas=["health"])
    assert one.overall_line == "Of the 1 approval this concept needs: 1 allowed (health permit)."
    assert one.overall_status == "allowed"
    none = run(DRY_RESTAURANT, areas=[])
    assert (none.rows, none.overall_status) == ([], "insufficient_information")
    assert none.overall_line == "No approval was looked up for this concept."
    assert none.open_questions == []  # no row was asked for, so nothing is asked


def test_entitlement_path_lists_only_approvals_to_file() -> None:
    # not permitted: no path, and no approval that cannot be issued is listed
    banned = run(COCKTAIL_BAR, z=PACIFIC, overlays=[], records=[TYPE_41_AT_995])
    assert (
        banned.entitlement_path
        == NO_PATH
        == ("No approval path: zoning does not permit the concept as described at this address.")
    )
    assert "ABC licence" not in banned.entitlement_path
    # principally permitted: nothing is filed with Planning, so the path starts with the next approval
    principal = run(given(RESTAURANT, alcohol_transaction="new_licence", **STATED), z=C2, overlays=[])
    assert row(principal, "zoning_use").status == "allowed"
    assert principal.entitlement_path.startswith("ABC licence, Type 41")
    assert "Principally permitted" not in principal.entitlement_path
    # an existing use that continues unchanged
    stays = given(COCKTAIL_BAR, alcohol_transaction="licence_already_held", changes_existing_business="none")
    existing = run(given(stays, **STATED), z=C2, overlays=[], records=[TYPE_48_AT_995])
    assert row(existing, "zoning_use").approval == "No new use authorization: the existing use continues"
    # the licence is already held: nothing is filed with ABC (corrected: the path started with the licence
    # before the review)
    assert row(existing, "alcohol").status == "allowed"
    assert "ABC licence" not in existing.entitlement_path
    assert "No new use authorization" not in existing.entitlement_path
    # a row the rules could not decide adds no approval: they do not know which one it is
    undecided = run(RESTAURANT, z=NCT3, overlays=[], areas=ALL_AREAS[:5])
    assert {r.area: r.status for r in undecided.rows} == {
        "zoning_use": "insufficient_information",
        "alcohol": "insufficient_information",
        "entertainment": "further_review",
        "health": "allowed",
        "building_change_of_use": "insufficient_information",
    }
    assert undecided.entitlement_path == (
        "Place of Entertainment, Limited Live Performance or Fixed Place Outdoor Amplified Sound permit; "
        "Health permit to operate"
    )
    # nothing left to list
    assert (
        run(given(DRY_RESTAURANT, **STATED), z=C2, overlays=[], areas=["zoning_use"]).entitlement_path
        == NOTHING_TO_FILE
    )
    assert entitlement_path([]) == NOTHING_TO_FILE == "No approval to file."
    # a Conditional Use stays first
    assert run(WINE_BAR).entitlement_path.startswith("Conditional Use Authorization (Planning Code § 303); ")
    # a principally permitted outdoor area is not filed either
    patio = given(DRY_RESTAURANT, outdoor_seating=True, outdoor_area="front", **STATED)
    front = run(patio, z=C2, overlays=[], areas=["zoning_use", "health", "outdoor"])
    assert row(front, "outdoor").status == "allowed" and front.entitlement_path == "Health permit to operate"


def test_rows_come_back_in_report_order_each_area_once() -> None:
    d = run(WINE_BAR, areas=["outdoor", "health", "zoning_use", "health", "alcohol"])
    assert [r.area for r in d.rows] == ["zoning_use", "alcohol", "health", "outdoor"]
    assert list(APPROVAL_AREA_LABELS) == ALL_AREAS


# ---- rule 1 ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("business_type", "serves_alcohol", "expected"),
    [
        ("bar", True, "bar"),
        ("bar", False, "bar"),
        ("restaurant", True, "restaurant"),
        ("restaurant", False, "restaurant"),
        ("cafe", True, "restaurant"),
        ("cafe", False, "limited_restaurant"),
        ("food_truck", True, "not_covered"),
        ("hotel", True, "not_covered"),
        ("catering", False, "not_covered"),
        ("other", True, "not_covered"),
    ],
)
def test_rule_1_proposed_use(business_type: BusinessType, serves_alcohol: bool, expected: str) -> None:
    prof = profile(
        business_type, serves_alcohol=serves_alcohol, alcohol_type="beer_wine" if serves_alcohol else "none"
    )
    assert planning_use(prof) == expected
    assert run(prof).pathway.use == expected


def test_rule_1_covers_every_business_type() -> None:
    for business_type in get_args(BusinessType):
        use = planning_use(profile(business_type))
        assert use in PLANNING_USE_LABELS
        p = run(profile(business_type)).pathway
        assert p.use == use and p.use_label == PLANNING_USE_LABELS[use]
        if use == "not_covered":
            # no use line: the first trigger says the rule table has no use for the business
            assert p.lines[0].rule_id == "T1.no_use"
            assert (p.permission, p.permission_label) == ("not_covered", "Not covered by the rule table")
        else:
            assert p.lines[0].rule_id == "zoning.use"
    # a cafe counts as serving alcohol on the alcohol type alone, as required_areas does
    assert planning_use(profile("cafe", alcohol_type="beer_wine")) == "restaurant"


def test_a_concept_with_dancing_is_looked_up_as_two_uses() -> None:
    d = run(given(WINE_BAR, dancing=True), z=C2, overlays=[])
    assert d.pathway.use == "bar"
    assert d.pathway.lines[0].text == (
        "The concept is looked up as these uses: Bar and Nighttime Entertainment (Planning Code § 102)."
    )
    assert trigger(d, "T6").control == "principal"
    # an entertainment venue alone: the use is Nighttime Entertainment, and its own trigger gives the control
    venue = profile("other", entertainment_kind="place_of_entertainment", stories=["first"])
    alone = run(venue, z=POLK, overlays=[], rules_date=dt.date(2024, 5, 26))
    assert (alone.pathway.use, alone.pathway.use_label) == (
        "nighttime_entertainment",
        "Nighttime Entertainment",
    )
    assert alone.pathway.lines[0].text == (
        "The concept is looked up as Nighttime Entertainment (Planning Code § 102)."
    )
    assert (trigger(alone, "T1").control, trigger(alone, "T6").control) == ("does_not_apply", "conditional")
    assert alone.pathway.permission == "conditional"


# ---- rule 3: the zoning row, spec section 4, one rule at a time --------------------------------------------
def finding(rule_id: str, control: str, *missing: str, line_id: str | None = None) -> TriggerFinding:
    """A synthetic finding, to read the row rule alone."""
    family = triggers.FAMILIES[rule_id]
    line = RuleLine(
        rule_id=line_id or f"{rule_id}.test",
        text=f"{rule_id} reads {control}.",
        code_section=f"Planning Code § {rule_id[1:]}00",
        citations=[f"zoning:{rule_id}"],
    )
    return TriggerFinding(
        rule_id=rule_id,
        family=family,
        label=TRIGGER_LABELS[family],
        control=control,  # type: ignore[arg-type]
        missing_inputs=list(missing),
        lines=[line],
    )


def eleven(**controls: tuple[str, ...] | str) -> list[TriggerFinding]:
    """All eleven findings: the ones named, and "does_not_apply" for the rest."""
    out = []
    for rule_id in triggers.ORDER:
        value = controls.get(rule_id, "does_not_apply")
        control, *missing = (value,) if isinstance(value, str) else value
        out.append(finding(rule_id, control, *missing))
    return out


CONCEPT = concept_facts(COCKTAIL_BAR)


def zoning_row_of(found: list[TriggerFinding], *, use_continues: bool = False) -> RowDetermination:
    return pw._zoning_row(CONCEPT, found, [], use_continues=use_continues)


@pytest.mark.parametrize(
    ("controls", "status", "note"),
    [
        # Z-NP: any trigger not permitted, whatever else is found
        ({"T1": "not_permitted"}, "not_permitted", None),
        (
            {
                "T7": "not_permitted",
                "T1": "conditional",
                "T5": ("not_decided", CHAIN),
                "T2": "code_and_practice_differ",
            },
            "not_permitted",
            None,
        ),
        # Z-S: else a trigger not decided because no story is given, even where another is conditional
        ({"T1": ("not_decided", STORY), "T11": "conditional"}, "insufficient_information", None),
        ({"T1": ("not_decided", STORY), "T7": "not_permitted"}, "not_permitted", None),
        # Z-C: else any conditional
        ({"T11": "conditional"}, "further_review", None),
        ({"T1": "conditional", "T5": ("not_decided", CHAIN)}, "further_review", None),
        (
            {"T3": "conditional", "T5": ("not_decided", CHAIN), "T2": "code_and_practice_differ"},
            "further_review",
            None,
        ),
        # Z-ND: else a trigger that matters cannot be decided; a missing input comes before "practice differs"
        ({"T5": ("not_decided", CHAIN)}, "insufficient_information", None),
        (
            {"T5": ("not_decided", CHAIN), "T2": "code_and_practice_differ", "T1": "principal"},
            "insufficient_information",
            None,
        ),
        # Z-D: else the Code and Planning practice differ
        ({"T2": "code_and_practice_differ", "T1": "principal"}, "further_review", PRACTICE_NOTE),
        # Z-A: else allowed
        ({"T1": "principal", "T5": "principal"}, "allowed", None),
        ({}, "allowed", None),
    ],
)
def test_zoning_row_status_follows_spec_section_4(
    controls: dict[str, Any], status: str, note: str | None
) -> None:
    got = zoning_row_of(eleven(**controls))
    assert (got.area, got.agency) == ("zoning_use", "San Francisco Planning")
    assert (got.status, got.status_note) == (status, note)
    assert got.basis[-1].rule_id == "zoning.status"
    assert bool(got.missing_inputs) == (status == "insufficient_information")
    assert got.referral_steps == []


def test_z_np_names_what_bars_the_concept() -> None:
    got = zoning_row_of(eleven(T1="not_permitted", T11="not_permitted", T5="conditional"))
    assert got.approval == "Not permitted at this address"
    assert got.basis[-1].text == (
        "Zoning does not permit the concept as described at this address. What bars it: use control of the "
        "zoning district and hours of operation: not permitted."
    )
    # the section and the records are those of the triggers that decided
    assert got.basis[-1].code_section == "Planning Code § 100"
    assert got.basis[-1].citations == ["zoning:T1", "zoning:T11"]


def test_z_c_names_every_trigger_that_asks_for_the_conditional_use() -> None:
    got = zoning_row_of(eleven(T1="conditional", T7="conditional", T9="conditional", T5="principal"))
    assert got.approval == "Conditional Use Authorization (Planning Code § 303)"
    assert got.basis[-1].text == (
        "The concept as described needs a Conditional Use Authorization here. What asks for one: use control "
        "of the zoning district, use size and outdoor activity area: further review."
    )
    assert got.basis[-1].code_section == "Planning Code § 303"
    assert got.basis[-1].citations == ["zoning:T1", "zoning:T7", "zoning:T9"]
    # a trigger still not decided is named too: its answer could add a ground or bar the concept
    more = zoning_row_of(
        eleven(T1="conditional", T6=("not_decided", "whether there is entertainment, and what kind"))
    )
    assert more.status == "further_review" and more.missing_inputs == []
    assert more.basis[-1].text == (
        "The concept as described needs a Conditional Use Authorization here. What asks for one: use control "
        "of the zoning district. Not decided as well: nighttime entertainment; the lines above name what is "
        "missing: further review."
    )


def test_z_nd_names_each_missing_input_once_in_trigger_order() -> None:
    got = zoning_row_of(
        eleven(T11=("not_decided", CLOSING), T5=("not_decided", CHAIN), T7=("not_decided", FLOOR_AREA, CHAIN))
    )
    assert got.status == "insufficient_information"
    assert got.missing_inputs == [CHAIN, FLOOR_AREA, CLOSING]
    assert got.approval == "Use authorization (not decided: an input is missing)"
    assert got.basis[-1].text == (
        "The rules could not decide: formula retail, use size and hours of operation. What is missing: "
        f"{CHAIN}; {FLOOR_AREA}; {CLOSING}. Until that is known the rules cannot say what zoning asks of the "
        "concept: insufficient information."
    )
    # a missing input is never an assumption: one undecided trigger keeps the row from "allowed"
    assert zoning_row_of(eleven(T1="principal", T5=("not_decided", CHAIN))).status != "allowed"


def test_z_d_says_the_code_and_planning_practice_differ() -> None:
    got = zoning_row_of(eleven(T1="principal", T2="code_and_practice_differ"))
    assert (got.status, got.status_note) == ("further_review", "Code and Planning practice differ")
    assert got.status_note == triggers.PRACTICE_DIFFERS_NOTE
    assert got.approval == (
        "Conditional Use Authorization (Planning Code § 303), unless Planning confirms none is needed"
    )
    assert got.basis[-1].text == (
        "The Planning Code text and San Francisco Planning's own records differ here (use control of a "
        "special use district). Ask San Francisco Planning which it applies: further review (Code and "
        "Planning practice differ)."
    )
    assert got.basis[-1].code_section == "Planning Code § 200"


def test_z_a_allowed_and_the_approval_says_why() -> None:
    new = zoning_row_of(eleven(T1="principal", T5="principal", T7="principal"))
    assert new.approval == "Principally permitted use: no Conditional Use Authorization for the use itself"
    assert new.basis[-1].text == (
        "Of the reasons the rules check for a Conditional Use Authorization (the lines above), none applies "
        "here and none bars the concept as described: allowed."
    )
    stays = zoning_row_of(eleven(T3="principal"), use_continues=True)
    assert stays.approval == "No new use authorization: the existing use continues"


def test_zoning_basis_lists_every_trigger_that_applies_and_leaves_out_the_ones_with_nothing_to_read() -> None:
    quiet = sorted(pw.QUIET_LINES)
    by_trigger = {q.split(".")[0]: q for q in quiet if q != "T8.no_data"}
    assert set(by_trigger) == {"T2", "T3", "T4", "T6", "T8", "T9", "T10"}
    found = []
    for rule_id in triggers.ORDER:
        if rule_id in by_trigger:  # nothing in the concept or at the address touches the trigger
            found.append(finding(rule_id, "does_not_apply", line_id=by_trigger[rule_id]))
        elif rule_id == "T1":  # it does not apply, and the reader needs to know why
            found.append(finding(rule_id, "does_not_apply", line_id="T1.continues"))
        else:
            found.append(finding(rule_id, "principal"))
    got = zoning_row_of(found)
    assert rule_ids(got.basis) == [
        "zoning.use",
        "T1.continues",
        "T5.test",
        "T7.test",
        "T11.test",
        "zoning.status",
    ]
    # every fixed "nothing to read" line is one the triggers module really writes
    assert {key.split("/")[0] for key in triggers.TEXT} >= pw.QUIET_LINES
    # the laundromat line is printed when the description says the space was a laundromat
    laundromat = concept_facts(given(COCKTAIL_BAR, existing_use_stated=["laundromat"]))
    shown = pw._zoning_row(laundromat, found, [], use_continues=False)
    assert "T8.outside" in rule_ids(shown.basis)


# ---- the zoning row end to end, on districts the dated data carries ---------------------------------------
def test_not_permitted_where_the_district_table_bars_the_use() -> None:
    d = run(COCKTAIL_BAR, z=PACIFIC, overlays=[district_row("NCD-PACIFIC")])
    zoning_row = row(d, "zoning_use")
    assert controls_of(d)["T1"] == "not_permitted"
    assert (zoning_row.status, zoning_row.approval) == ("not_permitted", "Not permitted at this address")
    assert zoning_row.basis[-1].text == (
        "Zoning does not permit the concept as described at this address. What bars it: use control of the "
        "zoning district: not permitted."
    )
    assert zoning_row.basis[-1].code_section == "Planning Code § 726"
    assert zoning_row.basis[-1].citations == ["zoning:NCD-PACIFIC"]
    assert (d.pathway.permission, d.pathway.permission_label) == ("not_permitted", "Not permitted")
    # nothing else is asked about the zoning row: no answer changes "not permitted"
    assert not any("Needed for: zoning and use" in q.question for q in d.open_questions)


def test_conditional_where_the_closing_hour_falls_in_the_conditional_hours() -> None:
    late = given(DRY_RESTAURANT, closing_hour="23:00", **STATED)
    d = run(late, z=PACIFIC, overlays=[])
    assert controls_of(d) == {"T1": "principal", "T5": "principal", "T7": "principal", "T11": "conditional"}
    zoning_row = row(d, "zoning_use")
    assert zoning_row.status == "further_review"
    assert zoning_row.basis[-1].text == (
        "The concept as described needs a Conditional Use Authorization here. What asks for one: hours of "
        "operation: further review."
    )
    assert d.pathway.permission == "conditional"
    # a 9 p.m. close is inside the principally permitted hours
    early = run(given(late, closing_hour="21:00"), z=PACIFIC, overlays=[])
    assert (row(early, "zoning_use").status, early.pathway.permission) == ("allowed", "principal")
    # no closing time given: not decided, never read as "closes by midnight"
    unsaid = run(given(DRY_RESTAURANT, **STATED), z=PACIFIC, overlays=[])
    assert row(unsaid, "zoning_use").missing_inputs == [CLOSING]
    assert (unsaid.pathway.permission, unsaid.pathway.permission_label) == (
        "not_covered",
        "Not decided by the rules",
    )


def test_insufficient_information_names_the_inputs_the_description_leaves_out() -> None:
    d = run(DRY_RESTAURANT, z=NCT3, overlays=[])
    zoning_row = row(d, "zoning_use")
    assert controls_of(d) == {"T1": "principal", "T5": "not_decided", "T7": "not_decided"}
    assert zoning_row.status == "insufficient_information"
    assert zoning_row.missing_inputs == [CHAIN, FLOOR_AREA]
    assert d.pathway.permission == "principal"  # the use itself is principally permitted
    asked = [(q.question, q.needs, q.ask) for q in d.open_questions[:2]]
    assert asked == [
        (
            f"Not known: {CHAIN}. Needed for: zoning and use.",
            "applicant_history",
            "The applicant: the project description does not say",
        ),
        (
            f"Not known: {FLOOR_AREA}. Needed for: zoning and use.",
            "applicant_history",
            "The applicant: the project description does not say",
        ),
    ]
    # each input given settles its trigger; with both the row is allowed
    assert row(
        run(given(DRY_RESTAURANT, formula_retail=False), z=NCT3, overlays=[]), "zoning_use"
    ).missing_inputs == [FLOOR_AREA]
    assert row(run(given(DRY_RESTAURANT, **STATED), z=NCT3, overlays=[]), "zoning_use").status == "allowed"
    # a chain is a conditional use here; 6,001 square feet is too
    chain = run(given(DRY_RESTAURANT, formula_retail=True, square_feet=1000), z=NCT3, overlays=[])
    assert controls_of(chain)["T5"] == "conditional" and row(chain, "zoning_use").status == "further_review"
    large = run(given(DRY_RESTAURANT, formula_retail=False, square_feet=6001), z=NCT3, overlays=[])
    assert controls_of(large)["T7"] == "conditional"
    assert "What asks for one: use size: further review." in row(large, "zoning_use").basis[-1].text


def test_code_and_planning_practice_differ_for_a_restaurant_in_the_mission_district() -> None:
    """§ 249.60(f)(1) inside the district but outside NCT-MISSION and NCT-24TH-MISSION: the rules cannot place
    the address, and Planning's records treat such restaurants as permitted."""
    prof = given(DRY_RESTAURANT, **STATED)
    d = run(prof, z=UMU, overlays=[MISSION_SUD, district_row("UMU")])
    zoning_row = row(d, "zoning_use")
    assert controls_of(d)["T2"] == "code_and_practice_differ"
    assert (zoning_row.status, zoning_row.status_note) == ("further_review", PRACTICE_NOTE)
    assert zoning_row.missing_inputs == []
    assert (d.pathway.permission, d.pathway.permission_label) == ("not_covered", PRACTICE_NOTE)
    asked = {q.question: q for q in d.open_questions}
    assert (
        asked["Is a Restaurant permitted at 995 Valencia St, and under which approval?"].needs
        == "agency_answer"
    )
    assert zoning_row.approval in d.entitlement_path
    # inside the Mission Street NCT the address is in the area: a plain Conditional Use, no note
    inside = run(prof, z=MISSION, overlays=[MISSION_SUD, district_row("NCT-MISSION")])
    assert controls_of(inside)["T2"] == "conditional"
    assert (row(inside, "zoning_use").status, row(inside, "zoning_use").status_note) == (
        "further_review",
        None,
    )
    # a missing input comes first: without the floor area the row is insufficient information, and the note is
    # not printed beside a status it does not belong to
    unsized = run(
        given(DRY_RESTAURANT, formula_retail=False), z=UMU, overlays=[MISSION_SUD, district_row("UMU")]
    )
    assert (row(unsized, "zoning_use").status, row(unsized, "zoning_use").status_note) == (
        "insufficient_information",
        None,
    )
    assert controls_of(unsized)["T2"] == "code_and_practice_differ"


def test_allowed_where_no_trigger_asks_for_anything() -> None:
    d = run(given(DRY_RESTAURANT, **STATED), z=C2, overlays=[district_row("C-2")])
    zoning_row = row(d, "zoning_use")
    assert set(controls_of(d).values()) == {"principal"}
    assert (zoning_row.status, zoning_row.status_note, zoning_row.missing_inputs) == ("allowed", None, [])
    assert (
        zoning_row.approval
        == "Principally permitted use: no Conditional Use Authorization for the use itself"
    )
    assert (d.pathway.permission, d.pathway.permission_label) == ("principal", "Permitted")
    assert rule_ids(zoning_row.basis)[0] == "zoning.use" and rule_ids(zoning_row.basis)[-1] == "zoning.status"
    # the district has no hours control: the line says so, though the trigger does not apply
    assert "T11.no_limit" in rule_ids(zoning_row.basis)
    assert not any(
        q.question.startswith("Not known") and "zoning and use" in q.question for q in d.open_questions
    )


def test_no_zoning_district_on_file_is_never_allowed() -> None:
    d = run(given(WINE_BAR, **STATED), no_zoning=True, overlays=[])
    zoning_row = row(d, "zoning_use")
    assert d.pathway.district is None
    assert zoning_row.status == "insufficient_information"
    assert "the zoning district of the address" in zoning_row.missing_inputs
    assert (d.pathway.permission, d.pathway.permission_label) == ("not_covered", "Not decided by the rules")
    assert row(d, "health").status == "allowed"


def test_a_business_the_rule_table_does_not_cover() -> None:
    d = run(profile("hotel", serves_alcohol=True, alcohol_type="beer_wine"), records=[TYPE_41_AT_995])
    zoning_row = row(d, "zoning_use")
    assert (d.pathway.use, d.pathway.permission) == ("not_covered", "not_covered")
    assert zoning_row.status == "insufficient_information"
    assert zoning_row.approval == "Use authorization (not covered by the rule table)"
    assert zoning_row.basis[0].text == (
        "The rule table covers bars, restaurants, cafes and nighttime entertainment. It has no use on file for "
        "this kind of business, so no use control was looked up."
    )
    assert (d.pathway.existing_use, d.pathway.change_of_use) == ("restaurant", "not_established")
    assert row(d, "building_change_of_use").status == "insufficient_information"
    # a business whose kind the description does not give names that input
    unknown = run(profile("other"))
    assert "what kind of business it is" in row(unknown, "zoning_use").missing_inputs[0]


# ---- a district the dated data does not carry: the zoning control table on file ---------------------------
def test_a_district_the_dated_data_does_not_carry_is_read_from_the_table_on_file() -> None:
    assert not controls.covers(NCT2_CODE)
    d = run(given(COCKTAIL_BAR, **STATED), z=not_carried(), overlays=[])
    t1 = trigger(d, "T1")
    assert t1.control == "conditional"
    assert texts(t1.lines) == [
        "Zoning district NCT-2: a Bar is a conditional use (Planning Code § 751).",
        "The dated rule table does not carry NCT-2. The control was read from the zoning control table on file, "
        "which gives today's control only.",
    ]
    assert rule_ids(t1.lines) == ["zoning.use_control", "T1.not_carried"]
    assert row(d, "zoning_use").status == "further_review"
    # the hours, at least, were not read there: with a principally permitted use the row is not "allowed"
    restaurant = run(given(DRY_RESTAURANT, **STATED), z=not_carried(), overlays=[])
    assert trigger(restaurant, "T1").control == "principal"
    assert row(restaurant, "zoning_use").status == "insufficient_information"
    assert NOT_CARRIED in row(restaurant, "zoning_use").missing_inputs
    # the table on file bars the use: not permitted, and the City permits follow
    banned = run(given(COCKTAIL_BAR, **STATED), z=not_carried(bar="prohibited"), overlays=[])
    assert [row(banned, a).status for a in ("zoning_use", "alcohol", "health")] == ["not_permitted"] * 3
    # an alcohol district's own control on file counts there, for a concept that serves alcohol
    third = run(given(COCKTAIL_BAR, **STATED), z=not_carried(bar="principal"), overlays=[THIRD_ST_RUD])
    assert trigger(third, "T1").control == "not_permitted"
    assert (
        "Third Street Alcohol Restricted Use District: a Bar is not permitted (Planning Code § 249.62)."
        in (texts(trigger(third, "T1").lines))
    )
    dry = run(given(profile("bar"), **STATED), z=not_carried(bar="principal"), overlays=[THIRD_ST_RUD])
    assert trigger(dry, "T1").control == "principal"
    assert (
        "Third Street Alcohol Restricted Use District: not applied, because the concept serves no alcohol "
        "(Planning Code § 249.62)." in texts(trigger(dry, "T1").lines)
    )
    # no control on file for the use: not decided
    unknown = run(given(COCKTAIL_BAR, **STATED), z=not_carried(bar="unknown"), overlays=[])
    assert trigger(unknown, "T1").control == "not_decided"


# ---- rule 4: the control for a new use --------------------------------------------------------------------
def test_permission_is_the_control_for_a_new_use_even_where_the_use_continues() -> None:
    # an existing Bar at the address: the use triggers do not apply to it ...
    stays = given(
        COCKTAIL_BAR, changes_existing_business="none", alcohol_transaction="licence_already_held", **STATED
    )
    d = run(stays, records=[TYPE_48_AT_995])
    assert (trigger(d, "T1").control, trigger(d, "T2").control) == ("does_not_apply", "does_not_apply")
    assert trigger(d, "T1").lines[0].text == (
        "A Bar already exists at this address and continues, so the control for a new use was not applied. See "
        "enlarging or intensifying an existing use."
    )
    assert row(d, "zoning_use").status == "allowed"
    # ... but the pathway still says what a NEW Bar would be here, with the lines that say so
    assert (d.pathway.permission, d.pathway.permission_label) == ("conditional", "Conditional use")
    assert "T1.cell" in rule_ids(d.pathway.lines) and "T1.continues" not in rule_ids(d.pathway.lines)
    assert "T1.continues" in rule_ids(row(d, "zoning_use").basis)
    # the same Bar where a new one is not permitted: the row is about the existing use, the pathway about a new one
    banned = run(given(stays, closing_hour="21:00"), z=PACIFIC, overlays=[], records=[TYPE_48_AT_995])
    assert banned.pathway.permission == "not_permitted"
    assert row(banned, "zoning_use").status == "allowed"
    assert [row(banned, a).status for a in ("health", "entertainment")] == ["allowed", "further_review"]


def test_permission_reads_the_use_the_special_district_the_licence_rule_and_the_hours() -> None:
    assert pw.PERMISSION_TRIGGERS == ("T1", "T2", "T4", "T11")
    # the district table (T1)
    assert run(given(COCKTAIL_BAR, **STATED), z=C2, overlays=[]).pathway.permission == "principal"
    assert run(COCKTAIL_BAR, z=POLK, overlays=[]).pathway.permission == "conditional"
    assert run(COCKTAIL_BAR, z=PACIFIC, overlays=[]).pathway.permission == "not_permitted"
    # RH-2: the § 186 and § 231 rows could govern instead (corrected from "not_permitted" by the review)
    rh2 = run(COCKTAIL_BAR, z=RH2, overlays=[]).pathway
    assert (rh2.permission, rh2.permission_label) == ("not_covered", "Not decided by the rules")
    # the special district (T2): a new Bar in the Mission district is always a Conditional Use
    in_mission = run(given(COCKTAIL_BAR, **STATED), z=NCT3, overlays=[MISSION_SUD])
    assert controls_of(in_mission)["T1"] == "principal" and controls_of(in_mission)["T2"] == "conditional"
    assert in_mission.pathway.permission == "conditional"
    # the licence rule of a restricted district (T4): a new on-sale establishment in the Haight Street NCD
    haight = zoning("NCD-HAIGHT", section="Planning Code § 719")
    new = given(RESTAURANT, alcohol_transaction="new_licence", **STATED)
    licensed = run(new, z=haight, overlays=[HAIGHT_RUSD])
    assert controls_of(licensed)["T1"] == "principal" and controls_of(licensed)["T4"] == "conditional"
    assert licensed.pathway.permission == "conditional"
    assert (
        run(given(DRY_RESTAURANT, **STATED), z=haight, overlays=[HAIGHT_RUSD]).pathway.permission
        == "principal"
    )
    # formula retail and use size are not the use: they decide the row, not the permission
    chain = run(given(DRY_RESTAURANT, formula_retail=True, square_feet=9000), z=NCT3, overlays=[])
    assert chain.pathway.permission == "principal" and row(chain, "zoning_use").status == "further_review"


# ---- rule 4: the existing use the licence records show -----------------------------------------------------
@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("41", "restaurant"),
        ("47", "restaurant"),
        ("75", "restaurant"),
        ("40", None),  # on-sale beer: § 102 lists it under Bar only alongside another use
        ("42", "bar"),
        ("48", "bar"),
        ("61", "bar"),
        ("20", None),
        ("21", None),
        ("58", None),
        ("86", None),
    ],
)
def test_licence_type_mapping(number: str, expected: str | None) -> None:
    use, lines = existing_use([licence("1", number)], SITE_995)
    assert use == expected
    assert len(lines) == 1
    if expected is None:
        assert number not in LICENCE_TYPES
        assert lines[0].text == (
            "No active ABC licence of a type the rules read (Types 41, 42, 47, 48, 61, 75) is on file at 995 "
            "Valencia St, so the records do not show what the space is used as now."
        )
        assert lines[0].citations == []
    else:
        assert LICENCE_TYPES[number].shows == expected
        label = PLANNING_USE_LABELS[expected]
        assert lines[0].text == (
            f"An active ABC Type {number} licence ({LICENCE_TYPES[number].label}) is on file at 995 Valencia "
            f"St. That is a licence type a {label} holds (Planning Code § 102), so the rules read the space as a "
            f"{label}; other uses can hold it too."
        )
        assert lines[0].citations == ["app:abc:1"]


def test_licence_type_number_is_read_from_the_record() -> None:
    assert licence_type(TYPE_41_AT_995.app) == "41"
    from_label = licence("2", "47", label="Type 47 – On-Sale General - Eating Place", license_type=None)
    assert licence_type(from_label.app) == "47"
    assert licence_type(licence("3", "041").app) == "41"
    assert licence_type(licence("4", "x", label="On-Sale", license_type=None).app) is None
    planning = Application(
        id="datasf_planning:2020-1CUA",
        source="datasf_planning",
        source_id="2020-1CUA",
        source_url="https://example.org/p",
        fetched_at=NOW,
        kind="cua",
        permit_type="Conditional Use Authorization for a Type 48 bar",
        status="ACTIVE",
        address="995 Valencia St",
    )
    assert licence_type(planning) is None
    assert existing_use([SiteRecord(planning, 0.0, "address")], SITE_995)[0] is None
    assert existing_use([from_label], SITE_995)[0] == "restaurant"


@pytest.mark.parametrize(
    "status",
    ["CANCELED", "EXPIRED", "PENDING", "SURRENDERED", "SUSPENDED - (Start Date: 01-OCT-26)", "INACTIVE", ""],
)
def test_only_an_active_licence_counts(status: str) -> None:
    assert existing_use([licence("1", "41", status=status)], SITE_995)[0] is None
    assert existing_use([licence("1", "41", status="active ")], SITE_995)[0] == "restaurant"


def test_999_valencia_on_the_same_parcel_does_not_count_for_995() -> None:
    use, lines = existing_use([TYPE_41_AT_999], SITE_995)
    assert use is None
    assert lines[0].rule_id == "zoning.existing_use" and lines[0].citations == []
    # it counts for 999 Valencia St itself, and 995's licence does not count there
    site_999 = site_of("999 Valencia St, San Francisco, CA 94110", "999 VALENCIA ST", "3609/026")
    assert existing_use([TYPE_41_AT_999], site_999)[0] == "restaurant"
    assert existing_use([TYPE_41_AT_995], site_999)[0] is None
    # whichever rule tied the record to the site, the record's own address decides
    by_parcel = licence("5", "41", "995 VALENCIA ST, SAN FRANCISCO, CA 94110", matched="parcel")
    assert existing_use([by_parcel], SITE_995)[0] == "restaurant"
    by_address_elsewhere = licence("6", "41", "997 Valencia St", matched="address")
    assert existing_use([by_address_elsewhere], SITE_995)[0] is None
    in_range = licence("7", "48", "993-995 Valencia Street, San Francisco, CA 94110", matched="parcel")
    assert existing_use([in_range], SITE_995)[0] == "bar"
    # a street without its suffix matches only when the record is mapped at the report's point
    assert existing_use([licence("8", "41", "995 Valencia", distance_m=5.0)], SITE_995)[0] == "restaurant"
    assert existing_use([licence("8", "41", "995 Valencia", distance_m=400.0)], SITE_995)[0] is None
    d = run(WINE_BAR, records=[TYPE_41_AT_999])
    assert (d.pathway.existing_use, d.pathway.change_of_use) == (None, "not_established")
    assert not any("abc:700999" in c for line in all_lines(d) for c in line.citations)


def test_a_site_without_a_street_address_establishes_nothing() -> None:
    nowhere = site_of("Valencia St & 21st St", None, None)
    use, lines = existing_use([TYPE_41_AT_995], nowhere)
    assert use is None
    assert lines[0].text.startswith("The report's address could not be read as a street address")
    d = run(WINE_BAR, records=[TYPE_41_AT_995], site=nowhere)
    assert (d.pathway.existing_use, d.pathway.change_of_use) == (None, "not_established")
    assert lines[0] in row(d, "zoning_use").basis and lines[0] in row(d, "building_change_of_use").basis


def test_licences_of_both_kinds_do_not_establish_a_use() -> None:
    use, lines = existing_use([TYPE_48_AT_995, TYPE_41_AT_995], SITE_995)
    assert use is None
    assert texts(lines) == [
        "An active ABC Type 41 licence (on-sale beer and wine, eating place) is on file at 995 Valencia St.",
        "An active ABC Type 48 licence (on-sale general, public premises) is on file at 995 Valencia St.",
        "Active licences for both a Restaurant and a Bar are on file at 995 Valencia St, so the records do not "
        "establish one existing use.",
    ]
    assert lines[-1].citations == ["app:abc:651564", "app:abc:700048"]
    d = run(WINE_BAR, records=[TYPE_48_AT_995, TYPE_41_AT_995])
    assert (d.pathway.existing_use, d.pathway.change_of_use) == (None, "not_established")
    assert row(d, "building_change_of_use").status == "insufficient_information"
    # two licences of the same kind do establish it
    assert existing_use([TYPE_48_AT_995, TYPE_42_AT_995], SITE_995)[0] == "bar"


def test_a_type_40_licence_establishes_nothing() -> None:
    """On-sale beer (Type 40) is a Bar under § 102 only alongside another use, so it is not read as a Bar."""
    assert "40" not in LICENCE_TYPES
    d = run(WINE_BAR, records=[licence("700040", "40", label="Type 40 – On-Sale Beer")])
    assert (d.pathway.existing_use, d.pathway.change_of_use) == (None, "not_established")
    assert row(d, "zoning_use").status == "further_review"  # a new Bar: Conditional Use
    assert row(d, "building_change_of_use").status == "insufficient_information"


# ---- rule 0: the rules date --------------------------------------------------------------------------------
def dated(source_id: str, number: str, on: dt.date) -> SiteRecord:
    """An ACTIVE licence at 995 Valencia St whose original issue date is `on`."""
    rec = licence(source_id, number)
    return SiteRecord(rec.app.model_copy(update={"decided_at": on}), rec.distance_m, rec.matched)


def test_a_record_dated_on_or_after_the_rules_date_is_not_read() -> None:
    issued = dt.date(2024, 3, 1)
    bar = dated("900048", "48", issued)
    prof = given(COCKTAIL_BAR, **STATED)
    # the day before the licence was issued, and the day itself: the records show no existing use
    for rules_date in (dt.date(2024, 2, 29), issued):
        d = run(prof, records=[bar], rules_date=rules_date)
        assert (d.pathway.existing_use, d.pathway.change_of_use) == (None, "not_established"), rules_date
        assert trigger(d, "T1").control == "conditional"  # a new Bar: the district's control applies
        assert not any("abc:900048" in c for line in all_lines(d) for c in line.citations)
        assert d.pathway.rules_date == rules_date.isoformat()
    # the day after: the licence is on file, so the Bar continues and the use control is not applied
    after = run(prof, records=[bar], rules_date=dt.date(2024, 3, 2))
    assert (after.pathway.existing_use, after.pathway.change_of_use) == ("bar", "no")
    assert trigger(after, "T1").control == "does_not_apply"
    # a record with no date is read on every date, as before
    assert run(prof, records=[TYPE_48_AT_995], rules_date=dt.date(2022, 6, 1)).pathway.existing_use == "bar"
    # today's report reads the licence
    assert run(prof, records=[bar]).pathway.existing_use == "bar"


def test_the_rules_date_decides_which_version_of_a_control_is_read() -> None:
    """NCD-POLK. Use size: until 2025-10-05 a use of 2,000 square feet or more was conditional and one of 4,000
    or more not permitted; on 2025-10-06 the cap went (Ord. 173-25); from 2025-12-15 the threshold is 3,001
    (Ord. 217-25). Nighttime Entertainment on the first story: conditional until 2024-05-26, principally
    permitted from 2024-05-27 (Ord. 85-24)."""
    capped = controls.use_size("NCD-POLK", dt.date(2025, 10, 5))
    assert (capped.principal_below_sqft, capped.not_permitted_from_sqft) == (2000, 4000)
    assert capped.source.in_force_to == dt.date(2025, 10, 5)
    raised = controls.use_size("NCD-POLK", dt.date(2025, 12, 15))
    assert (raised.principal_below_sqft, raised.source.in_force_from) == (3001, dt.date(2025, 12, 15))

    def restaurant(square_feet: int, on: dt.date) -> Determinations:
        prof = given(DRY_RESTAURANT, formula_retail=False, square_feet=square_feet, closing_hour="22:00")
        return run(prof, z=POLK, overlays=[], rules_date=on)

    # 2,500 square feet: a Conditional Use on the last day of the 2,001 threshold, nothing the day after
    before, after = restaurant(2500, dt.date(2025, 12, 14)), restaurant(2500, dt.date(2025, 12, 15))
    assert (trigger(before, "T7").control, row(before, "zoning_use").status) == (
        "conditional",
        "further_review",
    )
    assert (trigger(after, "T7").control, row(after, "zoning_use").status) == ("principal", "allowed")
    assert (before.pathway.rules_date, after.pathway.rules_date) == ("2025-12-14", "2025-12-15")
    # the finding says the control it read is not today's, when it changed and by which ordinance
    old = trigger(before, "T7")
    assert old.differs_today and not trigger(after, "T7").differs_today
    assert old.lines[-1].rule_id == "T7.differs"
    assert old.lines[-1].text == (
        "This control changed on 2025-12-15 (Ord. 217-25, File No. 250682); today it reads principally permitted."
    )
    assert trigger(after, "T7").in_force_from == "2025-12-15"
    # 4,500 square feet: not permitted while the cap stood, a Conditional Use from the day it went
    capped_out, uncapped = restaurant(4500, dt.date(2025, 10, 5)), restaurant(4500, dt.date(2025, 10, 6))
    assert (trigger(capped_out, "T7").control, row(capped_out, "zoning_use").status) == (
        "not_permitted",
        "not_permitted",
    )
    assert (trigger(uncapped, "T7").control, row(uncapped, "zoning_use").status) == (
        "conditional",
        "further_review",
    )
    # size is not a prohibited use: the health permit does not follow a size cap (the decision of 2026-11-12
    # carries Planning Code § 175(a) only for the use itself and formula retail)
    assert row(capped_out, "health").status == "allowed"
    assert row(uncapped, "health").status == "allowed"

    venue = given(COCKTAIL_BAR, entertainment_kind="place_of_entertainment", closing_hour="01:00", **STATED)
    night_before = run(venue, z=POLK, overlays=[], rules_date=dt.date(2024, 5, 26))
    night_after = run(venue, z=POLK, overlays=[], rules_date=dt.date(2024, 5, 27))
    assert (trigger(night_before, "T6").control, trigger(night_after, "T6").control) == (
        "conditional",
        "principal",
    )
    assert trigger(night_before, "T6").differs_today is True
    # `rules_date` defaults to `today`, and `today` alone never changes which control is read
    assert run(venue, z=POLK, overlays=[]) == run(venue, z=POLK, overlays=[], rules_date=TODAY)
    same_rules = run(venue, z=POLK, overlays=[], rules_date=dt.date(2024, 5, 26), today=dt.date(2024, 5, 26))
    assert trigger(same_rules, "T6").control == "conditional" and not trigger(same_rules, "T6").differs_today


def test_today_defaults_to_the_current_date_and_a_datetime_is_read_as_its_date() -> None:
    now = dt.date.today()
    d = determine(WINE_BAR, zoning(), VALENCIA_OVERLAYS, [], SITE_995, ALL_AREAS)
    assert d.pathway.rules_date in {now.isoformat(), dt.date.today().isoformat()}
    at_noon = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.UTC)
    assert run(WINE_BAR, today=at_noon, rules_date=at_noon) == run(WINE_BAR)


# ---- rule 5: change of use ----------------------------------------------------------------------------------
def test_change_of_use_answers() -> None:
    def answer(prof: BusinessProfile, records: list[SiteRecord]) -> tuple[str, str]:
        p = run(prof, records=records).pathway
        assert p.change_of_use_label == CHANGE_OF_USE_LABELS[p.change_of_use]
        assert p.changes is not None and p.changes.planning_use == p.change_of_use
        assert p.lines[-1] == p.changes.planning_use_lines[-1]
        return p.change_of_use, p.lines[-1].text

    assert answer(WINE_BAR, [TYPE_42_AT_995]) == (
        "no",
        "The rules read the space as a Bar from its licence type. If it is in fact a Bar, a Bar here is not a "
        "change of use.",
    )
    assert answer(WINE_BAR, [TYPE_41_AT_995]) == ("yes", "Restaurant to Bar is a change of use.")
    assert answer(RESTAURANT, [TYPE_48_AT_995]) == ("yes", "Bar to Restaurant is a change of use.")
    assert answer(profile("cafe"), [TYPE_41_AT_995]) == (
        "yes",
        "Restaurant to Limited Restaurant is a change of use.",
    )
    # v1's rule for the applicant's own flags is kept where neither the records nor a stated last use decide
    assert answer(given(WINE_BAR, new_construction=True), []) == (
        "yes",
        "The project is new construction, as described by the applicant, so the use is new to the site: a "
        "change of use.",
    )
    assert answer(given(WINE_BAR, change_of_use=True), []) == (
        "yes",
        "The space was not a food or drink use, as described by the applicant, so a Bar here is a change of use.",
    )
    assert answer(WINE_BAR, []) == (
        "not_established",
        "The records do not show what the space is used as, and the description does not say what it was last "
        "used as, so whether the proposed use (Bar) is a change of use is not established.",
    )
    # the last use as the description states it
    assert answer(given(WINE_BAR, existing_use_stated=["retail"]), []) == (
        "yes",
        "Retail to Bar is a change of use, with the last use of the space as described.",
    )
    assert answer(given(WINE_BAR, existing_use_stated=["bar"]), [])[0] == "no"
    # the records come before the applicant's description, and a stated last use before the flag
    assert answer(given(WINE_BAR, change_of_use=True), [TYPE_42_AT_995])[0] == "no"
    assert answer(given(WINE_BAR, change_of_use=True, existing_use_stated=["bar"]), [])[0] == "no"
    # a use the table does not cover is not compared with the existing use
    assert answer(profile("hotel"), [TYPE_41_AT_995]) == (
        "not_established",
        "The rules have no Planning Code use for the concept, so it was not compared with the last use of the "
        "space and a change of use is not established.",
    )
    assert answer(profile("hotel", change_of_use=True), [TYPE_41_AT_995]) == (
        "yes",
        "The space was not a food or drink use, as described by the applicant, so the proposed use here is a "
        "change of use.",
    )


def test_profile_change_of_use_false_is_never_read_as_no() -> None:
    """Without a licence on file at the address or a stated last use, nothing in the profile makes the answer
    'no'."""
    for business_type, alcohol, flag, new, records in itertools.product(
        get_args(BusinessType), (False, True), (False, True), (False, True), ([], [TYPE_41_AT_999])
    ):
        prof = profile(
            business_type,
            serves_alcohol=alcohol,
            alcohol_type="beer_wine" if alcohol else "none",
            change_of_use=flag,
            new_construction=new,
        )
        p = run(prof, records=records).pathway
        assert p.change_of_use == ("yes" if flag or new else "not_established")
        assert p.change_of_use != "no"


def test_the_three_change_of_use_answers_are_separate() -> None:
    d = run(given(WINE_BAR, seats=40), records=[TYPE_41_AT_995])
    changes = d.pathway.changes
    assert changes is not None
    assert (changes.planning_use, changes.building_occupancy, changes.neighbourhood_notice) == (
        "yes",
        "not_established",
        "not_required",
    )
    assert (
        changes.planning_use_lines and changes.building_occupancy_lines and changes.neighbourhood_notice_lines
    )
    assert {line.rule_id for line in changes.neighbourhood_notice_lines} == {"change.notice"}
    # the notice answer is read for the rules date: before 14 January 2024 a change of use to a conditional
    # use in an NCT district needed neighbourhood notice
    then = run(given(WINE_BAR, seats=40), records=[TYPE_41_AT_995], rules_date=dt.date(2023, 6, 1))
    assert then.pathway.changes is not None
    assert then.pathway.changes.neighbourhood_notice == "required"


# ---- rule 6: the alcohol row ----------------------------------------------------------------------------------
NEW_LICENCE = {"alcohol_transaction": "new_licence"}
# 995 Valencia St is in census tract 208.01, which is over its authorised number of on-sale licences
TRACT_OVER = "208.01"


def test_alcohol_not_permitted_where_the_use_itself_is_prohibited() -> None:
    d = run(given(COCKTAIL_BAR, **NEW_LICENCE), z=PACIFIC, overlays=[])
    alcohol = row(d, "alcohol")
    assert (alcohol.status, alcohol.status_note, alcohol.referral_steps) == ("not_permitted", None, [])
    assert alcohol.approval == "ABC licence, Type 48 (on-sale general, public premises)"
    assert alcohol.basis[-1].text == (
        "Zoning does not permit a new Bar at this address, and ABC may not issue a retail licence where using "
        "the licence would be contrary to zoning: not permitted."
    )
    assert alcohol.basis[-1].code_section == "California Business and Professions Code § 23790"
    # the missing transaction does not soften it: zoning is checked first
    assert row(run(COCKTAIL_BAR, z=PACIFIC, overlays=[]), "alcohol").status == "not_permitted"
    # a business that stays while a different, prohibited use is proposed: the Bar is a new use, so the licence
    # follows the zoning row like every City permit
    converts = given(WINE_BAR, changes_existing_business="enlarge")
    converted = run(converts, z=PACIFIC, overlays=[], records=[TYPE_41_AT_995])
    assert [
        row(converted, a).status for a in ("zoning_use", "alcohol", "health", "building_change_of_use")
    ] == ["not_permitted"] * 4
    # hours that are not permitted make the zoning row not permitted, and the licence cannot issue where using it
    # would be contrary to zoning (spec section 4; corrected: this read further review before the review)
    late = given(RESTAURANT, closing_hour="03:00", **NEW_LICENCE, **STATED)
    hours = run(late, z=PACIFIC, overlays=[])
    assert (trigger(hours, "T11").control, row(hours, "zoning_use").status) == (
        "not_permitted",
        "not_permitted",
    )
    late_alcohol = row(hours, "alcohol")
    assert (late_alcohol.status, late_alcohol.status_note, late_alcohol.referral_steps) == (
        "not_permitted",
        None,
        [],
    )
    assert late_alcohol.basis[-1].text == (
        "Zoning does not permit the concept as described at this address (hours of operation), and ABC may not "
        "issue a retail licence where using the licence would be contrary to zoning: not permitted."
    )
    # hours are not a prohibited use: Planning Code § 175(a) does not reach the City permits (the decision of
    # 2026-11-12 covers the use itself and formula retail only)
    assert row(hours, "health").status == "allowed"
    for area in ("health", "building_change_of_use", "entertainment", "outdoor"):
        assert row(hours, area).status != "not_permitted", area
        assert all(line.code_section != "Planning Code § 175(a)" for line in row(hours, area).basis), area


def test_alcohol_insufficient_information_names_the_licence_type_or_the_transaction() -> None:
    d = run(RESTAURANT, z=C2, overlays=[])
    alcohol = row(d, "alcohol")
    assert (alcohol.status, alcohol.missing_inputs) == ("insufficient_information", [TRANSACTION])
    assert alcohol.approval == "ABC licence, Type 41 (on-sale beer and wine, eating place)"
    assert alcohol.approval not in d.entitlement_path
    assert f"Not known: {TRANSACTION}. Needed for: alcohol licence." in [q.question for q in d.open_questions]
    # the licence type is missing when the description does not say what the concept pours, and the row names
    # what alcohol will be served (decision 1: never a guess; "unknown" reads the same as unsaid)
    pours = "what alcohol will be served: beer and wine, or spirits too"
    for alcohol_type in ("none", "unknown"):
        vague = run(
            profile("restaurant", serves_alcohol=True, alcohol_type=alcohol_type, **NEW_LICENCE),
            z=C2,
            overlays=[],
        )
        assert row(vague, "alcohol").status == "insufficient_information"
        assert row(vague, "alcohol").missing_inputs == [pours]
        assert row(vague, "alcohol").approval == "ABC licence"
        both = run(profile("restaurant", serves_alcohol=True, alcohol_type=alcohol_type), z=C2, overlays=[])
        assert row(both, "alcohol").missing_inputs == [pours, TRANSACTION]
    # a stated licence type still decides it
    typed = run(
        profile("restaurant", serves_alcohol=True, alcohol_type="unknown", licence_type="47", **NEW_LICENCE),
        z=C2,
        overlays=[],
    )
    assert row(typed, "alcohol").missing_inputs == []
    assert row(typed, "alcohol").approval.startswith("ABC licence, Type 47")


def test_alcohol_potential_blocker_for_the_mission_transfer_requirement() -> None:
    d = run(given(WINE_BAR, **NEW_LICENCE, **STATED))
    alcohol = row(d, "alcohol")
    assert (alcohol.status, alcohol.missing_inputs) == ("potential_blocker", [])
    assert rule_ids(alcohol.basis)[-2:] == [
        "T4:mission.new_bar_licence_from_bar_in_district",
        "alcohol.status",
    ]
    assert (
        alcohol.basis[-1].text
        == "The licence can be used here only if that condition is met: potential blocker."
    )
    assert alcohol.basis[-2].code_section == "Planning Code § 249.60(b)(2)(C)"
    assert d.overall_status == "potential_blocker"
    # a restaurant is not caught, nor is a bar outside the district
    assert row(run(given(RESTAURANT, **NEW_LICENCE, **STATED)), "alcohol").status == "further_review"
    assert (
        row(run(given(WINE_BAR, **NEW_LICENCE, **STATED), overlays=[]), "alcohol").status == "further_review"
    )
    # as the description reads (no transaction), the requirement is printed and the row names the input
    unsaid = row(run(WINE_BAR), "alcohol")
    assert unsaid.status == "insufficient_information"
    assert "T4:mission.new_bar_licence_from_bar_in_district" in rule_ids(unsaid.basis)


def test_alcohol_further_review_otherwise_with_the_referral_steps() -> None:
    d = run(given(RESTAURANT, **NEW_LICENCE, **STATED), z=C2, overlays=[])
    alcohol = row(d, "alcohol")
    assert (alcohol.status, alcohol.status_note) == ("further_review", None)
    assert alcohol.basis[-1].text == (
        "ABC investigates every licence application, and the applicant must post public notice, before a "
        "licence is issued: further review."
    )
    assert alcohol.agency == "California Department of Alcoholic Beverage Control"
    assert rule_ids(alcohol.referral_steps) == ["referral.step", "referral.step"]
    assert all("this application is sent to the" in s.text for s in alcohol.referral_steps)
    # a Type 47 or 48 licence: the county limit line comes first
    general = run(given(COCKTAIL_BAR, **NEW_LICENCE, **STATED), z=C2, overlays=[])
    assert "alcohol.county_limit" in rule_ids(row(general, "alcohol").basis)


def test_an_over_concentrated_tract_adds_a_note_and_never_changes_a_status() -> None:
    assert PCN_STATUS_NOTE == "public convenience or necessity finding likely required"
    new = given(RESTAURANT, **NEW_LICENCE, **STATED)
    plain = row(run(new, z=C2, overlays=[]), "alcohol")
    over = row(run(new, z=C2, overlays=[], tract=TRACT_OVER), "alcohol")
    assert (plain.status, plain.status_note) == ("further_review", None)
    assert (over.status, over.status_note) == ("further_review", PCN_STATUS_NOTE)
    assert rule_ids(over.basis).count("alcohol.tract_concentration") == 2
    assert over.basis[-3].text.startswith("Census tract 208.01: ")
    assert over.basis[-3].code_section == "California Business and Professions Code § 23958.4"
    # never a blocker and never "not permitted" on this fact alone, and an unknown tract says nothing
    assert row(run(new, z=C2, overlays=[], tract="9999.99"), "alcohol") == plain
    # a transfer from another person is not tested: no lines, no note
    transfer = given(RESTAURANT, alcohol_transaction="person_to_person_transfer", **STATED)
    assert row(run(transfer, z=C2, overlays=[], tract=TRACT_OVER), "alcohol").status_note is None
    # a status the tract did not set stays, with the lines printed and no note
    blocked = row(run(given(WINE_BAR, **NEW_LICENCE, **STATED), tract=TRACT_OVER), "alcohol")
    assert (blocked.status, blocked.status_note) == ("potential_blocker", None)
    assert "alcohol.tract_concentration" in rule_ids(blocked.basis)
    banned = row(run(given(COCKTAIL_BAR, **NEW_LICENCE), z=PACIFIC, overlays=[], tract=TRACT_OVER), "alcohol")
    assert (banned.status, banned.status_note) == ("not_permitted", None)
    # the transaction missing: the numbers are printed, the row is insufficient information, no note
    unsaid = row(run(RESTAURANT, z=C2, overlays=[], tract=TRACT_OVER), "alcohol")
    assert (unsaid.status, unsaid.status_note) == ("insufficient_information", None)
    assert rule_ids(unsaid.basis).count("alcohol.tract_concentration") == 2


# ---- rule 6: the entertainment row ---------------------------------------------------------------------------
def test_e1_entertainment_is_further_review_with_its_referral_steps() -> None:
    d = run(given(WINE_BAR, **STATED))
    entertainment = row(d, "entertainment")
    assert entertainment.status == "further_review"
    assert entertainment.approval == (
        "Place of Entertainment, Limited Live Performance or Fixed Place Outdoor Amplified Sound permit"
    )
    assert entertainment.agency == "San Francisco Entertainment Commission"
    assert entertainment.basis[0].text.endswith("Where a permit is needed: further review.")
    assert "one performer without amplification" in entertainment.basis[0].text
    # the referral steps are those on the rules date: before 17 August 2025 the Place of Entertainment
    # application also went to Building Inspection; the step ended, the permit did not
    steps_now = " ".join(texts(entertainment.referral_steps))
    assert (
        "until 16 August 2025 this application was also sent to the Department of Building Inspection"
        in steps_now
    )
    then = row(run(given(WINE_BAR, **STATED), rules_date=dt.date(2025, 8, 16)), "entertainment")
    steps_then = " ".join(texts(then.referral_steps))
    assert "this application is sent to the Department of Building Inspection for review" in steps_then
    assert then.status == entertainment.status == "further_review"  # a referral step never sets a status
    # the stated kind names the permit
    named = row(
        run(given(WINE_BAR, entertainment_kind="limited_live_performance", **STATED)), "entertainment"
    )
    assert named.approval == "Limited Live Performance permit"


def test_e2_open_after_2am_needs_an_extended_hours_permit_with_or_without_entertainment() -> None:
    late = given(DRY_RESTAURANT, closes_after_2am=True, **STATED)
    d = run(late, z=C2, overlays=[], areas=["zoning_use", "entertainment"])
    entertainment = row(d, "entertainment")
    assert (entertainment.status, entertainment.approval) == (
        "further_review",
        "Extended-Hours Premises permit",
    )
    assert entertainment.basis[0].text.startswith("Staying open to patrons between 2 a.m. and 6 a.m. needs")


def test_e3_entertainment_after_2am_needs_both_permits() -> None:
    late = given(WINE_BAR, closes_after_2am=True, **STATED)
    entertainment = row(run(late, z=C2, overlays=[]), "entertainment")
    assert entertainment.status == "further_review"
    assert entertainment.approval.endswith("permit, and Extended-Hours Premises permit")
    assert "needs a Place of Entertainment permit, not a Limited Live Performance permit" in (
        entertainment.basis[0].text
    )


def test_a_prohibited_new_use_makes_the_city_permits_not_permitted() -> None:
    """Planning Code § 175(a): E0, H0, B0, and O0z for the outdoor row (the decision of 2026-11-12: a
    prohibited use means no later approval applies)."""
    d = run(WINE_BAR, z=PACIFIC, overlays=[], records=[TYPE_41_AT_995])
    assert [(r.area, r.status) for r in d.rows] == [
        ("zoning_use", "not_permitted"),
        ("alcohol", "not_permitted"),
        ("entertainment", "not_permitted"),
        ("health", "not_permitted"),
        ("building_change_of_use", "not_permitted"),
        ("outdoor", "not_permitted"),
    ]
    outdoor = row(d, "outdoor")
    assert (
        outdoor.basis[-1].text
        == "Zoning does not permit the concept as described at this address (what bars it: use control of the zoning district), and no City department may issue a permit or licence that would authorize a use the Planning Code does not permit: not permitted."
    )
    assert outdoor.basis[-1].code_section == "Planning Code § 175(a)" and outdoor.referral_steps == []
    for area in ("entertainment", "health", "building_change_of_use"):
        last = row(d, area).basis[-1]
        assert last.text == (
            "Zoning does not permit a new Bar at this address, and no City department may issue a permit or "
            "licence that would authorize a use the Planning Code prohibits: not permitted."
        )
        assert last.code_section == "Planning Code § 175(a)"
        assert row(d, area).referral_steps == []
    assert row(d, "health").basis[-1].citations == ["zoning:NCD-PACIFIC"]
    assert d.entitlement_path == NO_PATH
    # without a change of use shown the building row is barred too (it was not decided before the decision of
    # 2026-11-12): a use the use controls bar is new by definition, and no answer would change the row
    unknown = run(WINE_BAR, z=PACIFIC, overlays=[])
    unknown_building = row(unknown, "building_change_of_use")
    assert (unknown_building.status, unknown_building.missing_inputs) == ("not_permitted", [])
    assert unknown_building.approval == "Building permit"
    assert unknown_building.basis[-1].text == row(unknown, "health").basis[-1].text
    # Nighttime Entertainment alone barred (NCD-PACIFIC bars it): the entertainment permit follows with v1's E0
    # sentence; the restaurant's health permit does not (Nighttime Entertainment is not among the prohibited uses
    # of the decision of 2026-11-12)
    venue = given(DRY_RESTAURANT, entertainment_kind="place_of_entertainment", closing_hour="21:00", **STATED)
    night = run(venue, z=PACIFIC, overlays=[])
    assert (trigger(night, "T1").control, trigger(night, "T6").control) == ("principal", "not_permitted")
    assert [row(night, a).status for a in ("zoning_use", "entertainment", "health")] == [
        "not_permitted",
        "not_permitted",
        "allowed",
    ]
    assert (
        row(night, "entertainment")
        .basis[-1]
        .text.startswith("Zoning does not permit a new Nighttime Entertainment at this address")
    )


# ---- rule 6: the health row ---------------------------------------------------------------------------------
def test_h1_health_is_allowed_with_its_referral_step() -> None:
    for prof in (WINE_BAR, RESTAURANT, DRY_RESTAURANT, profile("cafe"), profile("hotel")):
        health = row(run(prof), "health")
        assert (health.status, health.approval) == ("allowed", "Health permit to operate")
        assert health.agency == "San Francisco Department of Public Health"
        assert health.basis[0].text == (
            "A food or drink business needs a health permit to operate, which is issued after plan check and "
            "inspection without a hearing: allowed."
        )
        assert health.basis[0].code_section == (
            "California Retail Food Code §§ 114380–114381; San Francisco Health Code Article 8"
        )
        assert [s.rule_id for s in health.referral_steps] == ["referral.step"]
        assert "sent to the Planning Department for review" in health.referral_steps[0].text


# ---- rule 6: the building row ---------------------------------------------------------------------------------
def test_b1_change_of_use_is_further_review() -> None:
    d = run(WINE_BAR, records=[TYPE_41_AT_995])
    building = row(d, "building_change_of_use")
    assert (building.status, building.approval) == ("further_review", "Building permit with change of use")
    assert building.agency == "San Francisco Department of Building Inspection"
    assert building.basis[-1].text == (
        "A change of use needs a building permit, and the permit must conform to the Planning Code before it "
        "is issued: further review."
    )
    assert building.referral_steps and building.missing_inputs == []


def test_b2_no_change_of_use_is_allowed() -> None:
    # the description says nothing changes (corrected: silence was read as "no change" before the review)
    d = run(given(COCKTAIL_BAR, changes_existing_business="none"), records=[TYPE_48_AT_995])
    building = row(d, "building_change_of_use")
    assert d.pathway.change_of_use == "no"
    assert (building.status, building.approval) == ("allowed", "Building permit")
    assert building.basis[-1].text.startswith("The use does not change, so a building permit is needed only")
    # "no" rests on a licence type alone, so the rules still ask what the last legal use was
    assert d.open_questions[-1].question == "What was the last legal use of the space at 995 Valencia St?"
    assert d.open_questions[-1].needs == "agency_answer"


def test_b3_not_established_is_insufficient_information_and_names_what_is_missing() -> None:
    d = run(given(WINE_BAR, seats=40))
    building = row(d, "building_change_of_use")
    assert d.pathway.change_of_use == "not_established"
    assert (building.status, building.approval) == ("insufficient_information", "Building permit")
    assert building.missing_inputs == [
        LAST_USE,
        UNDER_50,
        "the existing occupancy group of the space, which only plans or an inspection show",
    ]
    asked = {q.question: (q.needs, q.ask) for q in d.open_questions}
    assert asked[f"Not known: {LAST_USE}. Needed for: building permit and change of use."] == (
        "applicant_history",
        "The applicant, or Planning's Property Information Map",
    )
    assert asked[
        "Not known: the existing occupancy group of the space, which only plans or an inspection show. Needed "
        "for: building permit and change of use."
    ] == ("plans", "Plans or a code analysis of the existing space")
    assert building.approval not in d.entitlement_path


# ---- rule 6: the outdoor row ----------------------------------------------------------------------------------
def patio(place: str | None, prof: BusinessProfile = DRY_RESTAURANT, **more: Any) -> BusinessProfile:
    return given(prof, outdoor_seating=True, outdoor_area=place, **STATED, **more)


def test_o1_the_sidewalk_stays_as_before() -> None:
    d = run(given(patio(None), sidewalk_or_parklet=True), z=MISSION, overlays=[])
    outdoor = row(d, "outdoor")
    assert trigger(d, "T9").control == "does_not_apply"
    assert (outdoor.status, outdoor.missing_inputs) == ("further_review", [])
    assert (
        outdoor.approval
        == "Outdoor activity area, sidewalk tables and chairs registration or Shared Spaces permit"
    )
    assert outdoor.agency == "San Francisco Planning, Public Works and the SFMTA"
    assert rule_ids(outdoor.basis) == ["T9.sidewalk", "outdoor.status"]
    assert outdoor.basis[0].text == (
        "The outdoor area is on the sidewalk, which is public right of way and takes a different approval, so "
        "this trigger does not apply."
    )
    assert outdoor.basis[-1].text.endswith("The rules did not check which of these applies: further review.")
    assert "Public Works Code Article 5.2" in (outdoor.basis[-1].code_section or "")
    assert "Shared Spaces" in outdoor.basis[-1].text and "SFMTA" in outdoor.basis[-1].text
    assert row(run(patio("sidewalk"), z=MISSION, overlays=[]), "outdoor").status == "further_review"


def test_outdoor_row_follows_the_outdoor_activity_area_trigger_on_the_lot() -> None:
    # NCT-MISSION: principally permitted in front, a conditional use elsewhere on the lot
    front = run(patio("front"), z=MISSION, overlays=[])
    assert trigger(front, "T9").control == "principal"
    assert (row(front, "outdoor").status, row(front, "outdoor").approval) == (
        "allowed",
        "Outdoor activity area: principally permitted",
    )
    assert row(front, "outdoor").basis[-1].text == (
        "The outdoor activity area as described is principally permitted here, so it needs no Conditional Use "
        "Authorization: allowed."
    )
    # on the rooftop (corrected from the rear: § 202.2(a)(7) itself reaches every NCT district, so an area at the
    # rear could be principal within its limits; a rooftop is outside the ground-level limit)
    rear = run(patio("rooftop"), z=MISSION, overlays=[])
    outdoor = row(rear, "outdoor")
    assert trigger(rear, "T9").control == "conditional"
    assert (outdoor.status, outdoor.approval) == (
        "further_review",
        "Conditional Use Authorization for the outdoor activity area (Planning Code § 303)",
    )
    assert outdoor.basis[:-1] == trigger(rear, "T9").lines
    assert outdoor.basis[-1].text == (
        "The outdoor activity area as described is a conditional use here, so it needs a Conditional Use "
        "Authorization: further review."
    )
    assert outdoor.basis[-1].code_section == "Planning Code § 303"
    # the same trigger is one of the reasons the zoning row asks for a Conditional Use
    assert "outdoor activity area" in row(rear, "zoning_use").basis[-1].text
    # an outdoor area the description does not place: not decided, and the row names the input
    unplaced = run(patio(None), z=MISSION, overlays=[])
    assert trigger(unplaced, "T9").control == "not_decided"
    assert (row(unplaced, "outdoor").status, row(unplaced, "outdoor").missing_inputs) == (
        "insufficient_information",
        ["where the outdoor area is"],
    )
    assert row(unplaced, "outdoor").basis[-1].text == (
        "The rules cannot say whether the outdoor activity area needs a Conditional Use Authorization without "
        "where the outdoor area is: insufficient information."
    )
    assert (
        "Not known: where the outdoor area is. Needed for: zoning and use; outdoor seating or activity area."
        in [q.question for q in unplaced.open_questions]
    )
    # NCT-VALENCIA lets an area elsewhere be principally permitted within the § 202.2(a)(7) limits, which no
    # input shows: not decided, naming those limits
    limits = run(patio("rear_or_side"), overlays=[])
    assert row(limits, "outdoor").status == "insufficient_information"
    assert (
        row(limits, "outdoor")
        .missing_inputs[0]
        .startswith("whether the outdoor area meets every limit of Planning Code § 202.2(a)(7)")
    )
    # RH-2: an area elsewhere on the lot is not permitted
    barred = run(patio("rear_or_side"), z=RH2, overlays=[])
    assert trigger(barred, "T9").control == "not_permitted"
    assert (row(barred, "outdoor").status, row(barred, "outdoor").approval) == (
        "not_permitted",
        "Outdoor activity area: not permitted as described",
    )


# ---- rule 7: what the rules could not establish ---------------------------------------------------------------
def test_one_question_per_missing_input_each_phrase_once_with_the_rows_that_need_it() -> None:
    haight = zoning("NCD-HAIGHT", section="Planning Code § 719")
    d = run(RESTAURANT, z=haight, overlays=[HAIGHT_RUSD], areas=ALL_AREAS[:5])
    questions = [q.question for q in d.open_questions]
    assert len(questions) == len(set(questions))
    # the licence rule of the Haight district needs the same two inputs for the zoning and the alcohol row
    assert f"Not known: {TRANSACTION}. Needed for: zoning and use; alcohol licence." in questions
    assert (
        f"Not known: {LAST_USE}. Needed for: zoning and use; alcohol licence; building permit and change of use."
        in (questions)
    )
    for r in d.rows:
        for phrase in r.missing_inputs:
            assert any(q.startswith(f"Not known: {phrase}.") for q in questions)
    # something the rules cannot place is a question for Planning, not for the applicant
    uncarried = run(given(DRY_RESTAURANT, **STATED), z=not_carried(), overlays=[])
    by_question = {q.question: q for q in uncarried.open_questions}
    planning = by_question[f"Not known: {NOT_CARRIED}. Needed for: zoning and use."]
    assert (planning.needs, planning.ask) == (
        "agency_answer",
        "A written answer from San Francisco Planning, such as a Letter of Determination",
    )


def test_a_missing_input_question_keeps_its_rows_when_the_phrase_is_long() -> None:
    assert pw.missing_input_question(FLOOR_AREA, ["outdoor", "zoning_use"]) == (
        "Not known: the floor area of the business, in square feet. Needed for: zoning and use; outdoor seating or activity area."
    )
    cap = next(
        m.max_length for m in OpenQuestion.model_fields["question"].metadata if hasattr(m, "max_length")
    )
    assert cap == pw.QUESTION_MAX == 300
    long = "whether the outdoor area meets every limit: " + "; ".join(f"limit number {i}" for i in range(40))
    question = pw.missing_input_question(long, ["zoning_use", "outdoor"])
    assert len(question) == cap
    assert question.startswith("Not known: whether the outdoor area meets every limit: limit number 0; ")
    assert question.endswith("…. Needed for: zoning and use; outdoor seating or activity area.")
    # the real case: an outdoor area elsewhere on the lot in NCT-VALENCIA, whose limits the row names in full
    limits = run(patio("rear_or_side"), overlays=[])
    phrase = row(limits, "outdoor").missing_inputs[0]
    asked = [
        q.question for q in limits.open_questions if q.question.startswith("Not known: whether the outdoor")
    ]
    assert asked == [pw.missing_input_question(phrase, ["zoning_use", "outdoor"])]
    assert asked[0].endswith(". Needed for: zoning and use; outdoor seating or activity area.")


# ---- an hours control as the static control table writes it ---------------------------------------------
def _w(permission: str, start: int, end: int) -> HoursWindow:
    return HoursWindow(permission, start, end)  # type: ignore[arg-type]


# Every distinct hours value in the static control table, and what the parser must make of it.
EXPECTED_HOURS: dict[str, HoursControl | None] = {
    "P 6 a.m.–11 p.m.; C 11 p.m.–2 a.m.": HoursControl((_w("P", 360, 1380), _w("C", 1380, 120))),
    "P 6 a.m.–2 a.m.; C 2 a.m.–6 a.m.": HoursControl((_w("P", 360, 120), _w("C", 120, 360))),
    "No limit on hours of operation": HoursControl((), no_limit=True),
    "P 6 a.m.–2 a.m.; NP 2 a.m.–6 a.m.": HoursControl((_w("P", 360, 120), _w("NP", 120, 360))),
    "P 6 a.m.–12 a.m.; C 12 a.m.–6 a.m.": HoursControl((_w("P", 360, 0), _w("C", 0, 360))),
    "P 6 a.m.–10 p.m.; C 10 p.m.–2 a.m.; NP 2 a.m.–6 a.m.": HoursControl(
        (_w("P", 360, 1320), _w("C", 1320, 120), _w("NP", 120, 360))
    ),
    "Limited Corner Commercial / § 186 uses: P 6 a.m.–10 p.m.": HoursControl(
        (_w("P", 360, 1320),), scope="Limited Corner Commercial / § 186 uses"
    ),
    # Table 209.1 (RH districts) as corrected 2026-11-10: the row also carries the hours that are not permitted
    "Limited Corner Commercial / § 186 uses: P 6 a.m.–10 p.m.; NP 10 p.m.–6 a.m.": HoursControl(
        (_w("P", 360, 1320), _w("NP", 1320, 360)), scope="Limited Corner Commercial / § 186 uses"
    ),
    "No restrictions on hours of operation": HoursControl((), no_limit=True),
}
# The one overlay sentence that lists several districts at once: not a control the parser reads.
SEVERAL_DISTRICTS = (
    "Hours of operation: NC-1 and NCT-1 P 6 a.m.–11 p.m., C 11 p.m.–2 a.m.; NC-2, NC-S, NCT-2 P 6 a.m.–2 a.m., "
    "C 2 a.m.–6 a.m.; NC-3 and NCT-3 no limit."
)


def _static_rules() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(STATIC_RULES.read_text())
    return data


def test_hours_parser_reads_every_distinct_string_in_the_static_table() -> None:
    table = _static_rules()["zoning_controls"]
    distinct = {c["hours"] for c in table.values() if c.get("hours")}
    assert distinct == set(EXPECTED_HOURS)  # a new string in the table must be given an expectation here
    for text, expected in EXPECTED_HOURS.items():
        assert parse_hours(text) == expected, text
        # as the stores hand it over: with the opening words and a full stop
        assert parse_hours(f"Hours of operation: {text.rstrip('.')}.") == expected, text


def test_hours_parser_reads_every_overlay_hours_string_in_the_static_table() -> None:
    strings = {o["late_night_rule"] for o in _static_rules()["overlays"] if o.get("late_night_rule")}
    assert SEVERAL_DISTRICTS in strings
    assert len(strings) > 5
    for text in sorted(strings):
        if text == SEVERAL_DISTRICTS:
            assert parse_hours(text) is None
            continue
        body = re.sub(r"^Hours of operation(?: \(Table \d+\))?: ", "", text)
        key = body if body in EXPECTED_HOURS else body.removesuffix(".")  # 'No limit on hours of operation.'
        assert key in EXPECTED_HOURS, text
        assert parse_hours(text) == EXPECTED_HOURS[key], text


@pytest.mark.parametrize(
    "text",
    [None, "", "   ", "Open late", "P 6 a.m.–25 p.m.", "P 6 a.m.–2 a.m.; see note 4", SEVERAL_DISTRICTS],
)
def test_hours_parser_returns_none_for_what_it_cannot_read(text: str | None) -> None:
    assert parse_hours(text) is None


def test_hours_windows_wrap_midnight() -> None:
    control = parse_hours("P 6 a.m.–2 a.m.; C 2 a.m.–6 a.m.")
    assert control is not None
    assert [control.at(m) for m in (0, 60, 119, 120, 180, 359, 360, 720, 1439)] == [
        "P",
        "P",
        "P",
        "C",
        "C",
        "C",
        "P",
        "P",
        "P",
    ]
    assert control.text == "P 6 a.m.–2 a.m.; C 2 a.m.–6 a.m."
    gap = parse_hours(HOURS_11PM)
    assert gap is not None and gap.at(180) is None and gap.at(60) == "C" and gap.at(23 * 60) == "C"
    assert parse_hours("P 6:30 a.m.-10:30 p.m.") == HoursControl((_w("P", 390, 1350),))
    assert (
        pw.format_time(0) == "12 a.m."
        and pw.format_time(720) == "12 p.m."
        and pw.format_time(1350) == "10:30 p.m."
    )


def test_three_closing_buckets() -> None:
    assert closing_bucket(profile("bar")) == "by_midnight"
    assert closing_bucket(profile("bar", closes_after_midnight=True)) == "after_midnight"
    assert closing_bucket(profile("bar", closes_after_2am=True)) == "after_2am"
    assert closing_bucket(profile("bar", closes_after_midnight=True, closes_after_2am=True)) == "after_2am"
    assert pw.READ_AT == {"after_2am": 180, "after_midnight": 60}


def test_a_profile_that_gives_no_hours_is_not_said_to_close_by_midnight() -> None:
    """The profile's two closing flags are False by default. That is not a closing time: where hours that are
    not principally permitted begin before 2 a.m., the hours trigger is not decided and names the input."""
    d = run(given(DRY_RESTAURANT, **STATED), z=PACIFIC, overlays=[])
    hours = trigger(d, "T11")
    assert (hours.control, hours.missing_inputs) == ("not_decided", [CLOSING])
    assert "the description gives no closing time" in hours.lines[0].text
    assert "midnight" not in " ".join(texts(hours.lines))
    # where they begin at 2 a.m. the trigger asks for nothing, and the line says what was not checked
    valencia = trigger(run(given(DRY_RESTAURANT, **STATED), overlays=[]), "T11")
    assert valencia.control == "principal"
    assert valencia.lines[0].text.endswith("the rules did not check a closing time after 2 a.m.")
    # the flags, when set, are read where v1 read them: at 1 a.m. and at 3 a.m.
    after_two = trigger(run(given(DRY_RESTAURANT, closes_after_2am=True, **STATED), overlays=[]), "T11")
    assert after_two.control == "conditional" and "read at 3 a.m." in after_two.lines[0].text


def test_notes_carry_the_text_on_file_and_skip_unrelated_districts() -> None:
    p = run(WINE_BAR, overlays=[*VALENCIA_OVERLAYS, TARAVAL]).pathway
    assert all(n.text.startswith(NOTE_PREFIX + " ") for n in p.notes)
    assert texts(p.notes) == [
        f"{NOTE_PREFIX} {zoning().rules}",  # the district's note; the rule row repeats it and is merged in
        f"{NOTE_PREFIX} {MISSION_SUD.rules}",
        f"{NOTE_PREFIX} {TARAVAL.rules}",
    ]
    assert p.notes[0].citations == ["overlay:static:sf:nc_nct_valencia", "zoning:NCT-VALENCIA"]
    assert p.notes[1].citations == ["overlay:datasf_sud:mission_alcohol_restrict"]
    assert p.notes[1].code_section == "Planning Code § 249.60"
    assert "only as a Conditional Use" in p.notes[1].text
    assert not any("fringe" in n.text.lower() for n in p.notes)
    assert run(WINE_BAR, no_zoning=True, overlays=[FRINGE]).pathway.notes == []
    # an alcohol district's note is left out for a concept that serves no alcohol
    assert MISSION_SUD.rules not in " ".join(texts(run(DRY_RESTAURANT).pathway.notes))


# ---- invariants over a grid of facts ------------------------------------------------------------------------
GRID_OVERLAYS: dict[str, list[Overlay]] = {
    "none": [],
    "mission": [MISSION_SUD, FRINGE],
    "third_street": [THIRD_ST_RUD],
    "haight_taraval": [HAIGHT_RUSD, TARAVAL],
}
GRID_RECORDS: dict[str, list[SiteRecord]] = {
    "none": [],
    "restaurant": [TYPE_41_AT_995],
    "bar": [TYPE_48_AT_995],
    "next_door": [TYPE_41_AT_999],
    "both": [TYPE_41_AT_995, TYPE_48_AT_995, TYPE_41_AT_999],
}
GRID_ZONING: dict[str, ZoningInfo | None] = {
    "principal": C2,
    "conditional": zoning(),
    "prohibited": PACIFIC,
    "restricted": zoning("NCD-HAIGHT", section="Planning Code § 719"),
    "not_carried": not_carried(bar="prohibited"),
    "none": None,
}
# what the description says beyond the kind of business, from nothing to everything the rules read
GRID_STATED: list[dict[str, Any]] = [
    {},
    {"closes_after_midnight": True, "change_of_use": True},
    {"closes_after_2am": True, "new_construction": True, "outdoor_area": "rear_or_side"},
    {
        **STATED,
        "closing_hour": "23:00",
        "alcohol_transaction": "new_licence",
        "existing_use_stated": ["retail"],
    },
    {
        **STATED,
        "closing_hour": "21:00",
        "alcohol_transaction": "person_to_person_transfer",
        "changes_existing_business": "none",
        "entertainment_kind": "limited_live_performance",
        "outdoor_area": "front",
    },
]


def grid() -> list[tuple[BusinessProfile, ZoningInfo | None, list[Overlay], list[SiteRecord]]]:
    cases = []
    for business_type, alcohol, stated, z, overlays, records in itertools.product(
        ("bar", "restaurant", "cafe", "hotel"),
        (False, True),
        GRID_STATED,
        GRID_ZONING.values(),
        GRID_OVERLAYS.values(),
        GRID_RECORDS.values(),
    ):
        fields = dict(stated)
        if not alcohol:
            fields.pop("alcohol_transaction", None)
        prof = profile(
            business_type,  # type: ignore[arg-type]
            serves_alcohol=alcohol,
            alcohol_type="full_liquor" if alcohol else "none",
            live_entertainment=business_type == "bar",
            outdoor_seating=True,
            **fields,
        )
        cases.append((prof, z, overlays, records))
    return cases


GRID = grid()
GRID_RESULTS = [
    (prof, z, overlays, records, determine(prof, z, overlays, records, SITE_995, ALL_AREAS, today=TODAY))
    for prof, z, overlays, records in GRID
]
CITATION_ID = re.compile(r"^(?:zoning:\S.*|overlay:\S.*|app:\S.*)$")
RULE_ID = re.compile(
    r"^(?:zoning|alcohol|entertainment|health|building|outdoor|change|referral)\.[a-z_]+$"
    r"|^T(?:[1-9]|1[01])[.:][A-Za-z0-9_.]+$"
    r"|^(?:not_carried|no_district)$"
)


def test_building_row_always_reads_the_change_of_use_answer_the_pathway_holds() -> None:
    assert len(GRID) == 4 * 2 * 5 * 6 * 4 * 5
    seen: set[str] = set()
    for _prof, _z, _overlays, _records, d in GRID_RESULTS:
        p = d.pathway
        changes = p.changes
        assert changes is not None and p.change_of_use == changes.planning_use
        assert p.change_of_use_label == CHANGE_OF_USE_LABELS[p.change_of_use]
        seen.add(p.change_of_use)
        building, zoning_row = row(d, "building_change_of_use"), row(d, "zoning_use")
        # one answer: the pathway ends with it, the zoning row prints it, the building row opens with it
        answer = changes.planning_use_lines
        assert p.lines[-len(answer) :] == answer
        assert all(line in zoning_row.basis for line in answer)
        assert building.basis[: len(answer)] == answer
        # B0 and B0z: a prohibited use (the use itself, formula retail) bars the building permit (Planning Code
        # § 175(a)); no other trigger does
        b0 = any(f.rule_id in pw.PROHIBITED_USE_TRIGGERS and f.control == "not_permitted" for f in p.triggers)
        if b0:
            want = "not_permitted"
        elif "yes" in (changes.planning_use, changes.building_occupancy):
            want = "further_review"
        elif (changes.planning_use, changes.building_occupancy) == ("no", "no"):
            want = "allowed"
        else:
            want = "insufficient_information"
        assert building.status == want
        assert (building.basis[-1].code_section == "Planning Code § 175(a)") == b0
        assert (building.approval == "Building permit with change of use") == (p.change_of_use == "yes")
        if (
            p.existing_use is not None
            and p.use != "not_covered"
            and not p.changes.planning_use_lines[-1].text.endswith("as described.")
        ):
            assert (p.change_of_use == "no") == (
                p.existing_use == p.use and len(changes.planning_use_lines) > 0
            )
    assert seen == {"yes", "no", "not_established"}


def test_grid_invariants() -> None:
    statuses: set[tuple[str, str]] = set()
    notes: set[str | None] = set()
    for prof, z, _overlays, _records, d in GRID_RESULTS:
        p = d.pathway
        found = {f.rule_id: f for f in p.triggers}
        assert [r.area for r in d.rows] == ALL_AREAS
        assert list(found) == list(triggers.ORDER)
        assert d.overall_status == next(s for s in STATUS_SEVERITY if s in {r.status for r in d.rows})
        statuses |= {(r.area, r.status) for r in d.rows}
        notes |= {r.status_note for r in d.rows}
        rows = {r.area: r for r in d.rows}
        zoning_row, alcohol = rows["zoning_use"], rows["alcohol"]
        # rule 3: the zoning row is the triggers' own outcome
        outcome = triggers.zoning_outcome(p.triggers)
        assert (zoning_row.status, zoning_row.status_note) == (outcome.status, outcome.status_note)
        assert zoning_row.missing_inputs == list(outcome.missing_inputs)
        controls_found = {f.control for f in p.triggers}
        if "not_permitted" in controls_found:
            assert zoning_row.status == "not_permitted"
        elif triggers.story_not_given(p.triggers):  # Z-S: a missing story outranks a Conditional Use
            assert zoning_row.status == "insufficient_information"
            assert "which stories the business occupies" in zoning_row.missing_inputs
        elif "conditional" in controls_found:
            assert (zoning_row.status, zoning_row.status_note) == ("further_review", None)
        elif "not_decided" in controls_found:
            assert zoning_row.status == "insufficient_information"
        elif "code_and_practice_differ" in controls_found:
            assert (zoning_row.status, zoning_row.status_note) == ("further_review", PRACTICE_NOTE)
        else:
            assert zoning_row.status == "allowed"
        # rule 8: the path lists approvals to file, and nothing when a row is not permitted
        assert d.entitlement_path == entitlement_path(d.rows)
        if any(r.status == "not_permitted" for r in d.rows):
            assert d.entitlement_path == NO_PATH
        else:
            filed = [
                r.approval
                for r in d.rows
                if r.status != "insufficient_information"
                and not (r.area in pw.NOTHING_FILED_WHEN_ALLOWED and r.status == "allowed")
            ]
            assert d.entitlement_path == ("; ".join(filed) or NOTHING_TO_FILE)
            assert not d.entitlement_path.startswith(("Principally permitted", "No new use authorization"))
        # rule 6: every licence and City permit follows a prohibited use (the use itself, formula retail), and
        # nothing else makes the health, building or entertainment rows not permitted (Planning Code § 175(a);
        # the decision of 2026-11-12). Other bars (hours, size, Nighttime Entertainment, the outdoor area) do not
        # reach them, except the entertainment row's own E0 for Nighttime Entertainment.
        use_barred = "not_permitted" in (found["T1"].control, found["T2"].control)
        prohibited = any(found[t].control == "not_permitted" for t in pw.PROHIBITED_USE_TRIGGERS)
        night_barred = found["T6"].control == "not_permitted"
        assert not prohibited or zoning_row.status == "not_permitted"
        assert (rows["health"].status == "not_permitted") == prohibited
        assert (rows["building_change_of_use"].status == "not_permitted") == prohibited
        if prohibited:
            assert alcohol.status == "not_permitted"
            for area in ("health", "building_change_of_use", "entertainment", "outdoor"):
                assert rows[area].basis[-1].code_section == "Planning Code § 175(a)" or (
                    area == "outdoor" and found["T9"].control == "not_permitted"
                ), area
        assert (rows["entertainment"].status == "not_permitted") == (prohibited or night_barred)
        if rows["entertainment"].status != "not_permitted":
            assert rows["entertainment"].status == "further_review"
        assert ("Extended-Hours Premises permit" in rows["entertainment"].approval) == (
            prof.closes_after_2am
            or (prof.closing_hour is not None and "02:00" < prof.closing_hour <= "06:00")
        )
        # alcohol: not permitted only through zoning; a missing input names itself; the note never changes a status
        # (A1z, from the review: also where the zoning row is not permitted for the concept as described)
        if alcohol.status == "not_permitted":
            assert (
                use_barred or found["T4"].control == "not_permitted" or zoning_row.status == "not_permitted"
            )
        if alcohol.status == "insufficient_information":
            assert alcohol.missing_inputs
        assert alcohol.status_note is None  # no tract was given
        # outdoor: by the outdoor activity area trigger
        by_t9 = {
            "conditional": "further_review",
            "not_decided": "insufficient_information",
            "principal": "allowed",
            "not_permitted": "not_permitted",
            "does_not_apply": "further_review",
        }
        expected_outdoor = by_t9[found["T9"].control]
        if found["T9"].control == "principal" and concept_facts(prof).outdoor_area.missing:
            expected_outdoor = "insufficient_information"  # O-U (review): the area is not placed
        if prohibited:
            expected_outdoor = "not_permitted"  # O0z, or O-NP when the outdoor area is itself barred
        assert rows["outdoor"].status == expected_outdoor
        for r in d.rows:
            status_line = next(line for line in reversed(r.basis) if line.rule_id.endswith(".status"))
            assert status_line.rule_id == f"{r.area.split('_')[0]}.status"
            assert status_line.text.endswith((f": {r.status.replace('_', ' ')}.", f"({PRACTICE_NOTE})."))
            # the status line closes the row; only the entertainment row may add one line about the closing time
            assert r.basis[-1] == status_line or rule_ids(r.basis[-2:]) == [
                "entertainment.status",
                "entertainment.closing",
            ]
            assert r.agency and r.approval
            assert (
                bool(r.missing_inputs) == (r.status == "insufficient_information")
                or r.area == "building_change_of_use"
            )
            if r.status == "insufficient_information":
                assert r.missing_inputs or r.area == "building_change_of_use"
            if r.status == "not_permitted":
                assert r.referral_steps == []
            assert all(s.rule_id == "referral.step" for s in r.referral_steps)
        if z is None:
            # no district on file: the control for a new use is never "principal" (a special use district at the
            # address can still make it conditional)
            assert p.district is None and p.permission != "principal"
            assert zoning_row.status != "allowed"
        # every missing input is asked once, with the rows that need it
        questions = [q.question for q in d.open_questions]
        assert len(questions) == len(set(questions))
        needed: dict[str, list[str]] = {}
        if zoning_row.status != "not_permitted":
            for phrase in triggers.missing_inputs(p.triggers):
                needed.setdefault(phrase, []).append("zoning_use")
        for r in d.rows:
            for phrase in r.missing_inputs:
                needed.setdefault(phrase, []).append(r.area)
        asked = [pw.missing_input_question(phrase, areas) for phrase, areas in needed.items()]
        assert questions[: len(asked)] == asked
        assert all(not q.startswith("Not known: ") for q in questions[len(asked) :])
    assert {s for a, s in statuses if a == "zoning_use"} == {
        "allowed",
        "further_review",
        "not_permitted",
        "insufficient_information",
    }
    assert {s for a, s in statuses if a == "alcohol"} == {
        "not_permitted",
        "potential_blocker",
        "further_review",
        "insufficient_information",
    }
    assert {s for a, s in statuses if a == "outdoor"} >= {
        "allowed",
        "further_review",
        "insufficient_information",
    }
    assert notes == {None, PRACTICE_NOTE}


def test_every_rule_line_is_a_plain_sentence_with_known_citation_ids() -> None:
    for _prof, z, overlays, records, d in GRID_RESULTS:
        known = {f"overlay:{o.id}" for o in overlays} | {f"app:{r.app.id}" for r in records}
        if z is not None:
            known.add(f"zoning:{z.district}")
        for line in all_lines(d):
            assert RULE_ID.match(line.rule_id), line.rule_id
            if not line.rule_id.endswith("note"):  # a note repeats the text on file, however it is written
                assert line.text[0].isupper() and line.text.rstrip().endswith((".", ").")), line.text
            assert "{" not in line.text and "}" not in line.text and "  " not in line.text, line.text
            assert line.citations == sorted(set(line.citations))
            for cid in line.citations:
                assert CITATION_ID.match(cid), cid
                assert cid in known, cid
        for q in d.open_questions:
            assert q.needs in {"agency_answer", "applicant_history", "plans"} and q.ask
            assert q.question[0].isupper() and q.question.endswith(("?", "."))


def test_same_inputs_in_any_order_give_byte_identical_json() -> None:
    overlays = [*VALENCIA_OVERLAYS, THIRD_ST_RUD, HAIGHT_RUSD, TARAVAL]
    records = [TYPE_41_AT_995, TYPE_48_AT_995, TYPE_41_AT_999, TYPE_42_AT_995]
    dates = {"today": TODAY, "rules_date": dt.date(2025, 3, 1), "tract": TRACT_OVER}
    prof = given(WINE_BAR, alcohol_transaction="new_licence", outdoor_seating=True, outdoor_area="rooftop")
    expected = determine(prof, zoning(), overlays, records, SITE_995, ALL_AREAS, **dates).model_dump_json()
    rng = random.Random(995)  # the test shuffles; the engine itself uses no randomness
    for _ in range(200):
        o, r, areas = list(overlays), list(records), list(ALL_AREAS)
        rng.shuffle(o)
        rng.shuffle(r)
        rng.shuffle(areas)
        got = determine(prof, zoning(), o, r, SITE_995, areas, **dates)
        assert got.model_dump_json() == expected
    # repeated rows and repeated calls change nothing
    doubled = determine(
        prof, zoning(), overlays + overlays, records + records, SITE_995, ALL_AREAS + ALL_AREAS, **dates
    )
    assert doubled.model_dump_json() == expected
    # `today` only says where a control differs from today's: the rows do not move with it
    later = determine(
        prof, zoning(), overlays, records, SITE_995, ALL_AREAS, **{**dates, "today": dt.date(2030, 1, 1)}
    )
    assert [(r.area, r.status, r.status_note, r.missing_inputs) for r in later.rows] == [
        (r.area, r.status, r.status_note, r.missing_inputs)
        for r in determine(prof, zoning(), overlays, records, SITE_995, ALL_AREAS, **dates).rows
    ]
    for grid_prof, z, grid_overlays, grid_records, first in GRID_RESULTS[::97]:
        again = determine(
            grid_prof.model_copy(),
            z,
            list(reversed(grid_overlays)),
            list(reversed(grid_records)),
            SITE_995,
            list(reversed(ALL_AREAS)),
            today=TODAY,
        )
        assert first.model_dump_json() == again.model_dump_json()


def test_the_rows_are_decided_from_the_pathway_the_report_carries() -> None:
    for _prof, _z, _overlays, _records, d in GRID_RESULTS[::53]:
        p = d.pathway
        zoning_row = row(d, "zoning_use")
        # every trigger that applies is in the zoning row, in trigger order, between the use line and the status
        applying = [line for f in p.triggers if f.control != "does_not_apply" for line in f.lines]
        positions = [zoning_row.basis.index(line) for line in pw._merge(applying)]
        assert positions == sorted(positions)
        assert zoning_row.basis[-1].rule_id == "zoning.status"
        if p.use != "not_covered":
            assert zoning_row.basis[0] == p.lines[0] and p.lines[0].rule_id == "zoning.use"


def test_a_seeded_sweep_of_facts_districts_and_dates_holds_the_row_rules() -> None:
    """600 combinations drawn with a fixed seed from every input the rules read, every district the dated data
    carries (and two it does not), five overlay sets, the licences on file and nine rules dates. No combination
    raises, every row follows its rule, and the answer does not depend on the order of the inputs."""
    rng = random.Random(20261110)  # the test draws; the engine itself uses no randomness
    districts = [*controls.districts(), NCT2_CODE, "PDR-1-G", None]
    overlay_sets = [[], [MISSION_SUD], [THIRD_ST_RUD], [HAIGHT_RUSD, TARAVAL], VALENCIA_OVERLAYS]
    record_sets = [[], [TYPE_41_AT_995], [TYPE_48_AT_995], [TYPE_41_AT_995, TYPE_48_AT_995], [TYPE_41_AT_999]]
    dates = [
        dt.date(2021, 6, 1),  # before the dated data starts
        dt.date(2022, 1, 1),
        dt.date(2023, 6, 1),
        dt.date(2024, 1, 13),
        dt.date(2024, 1, 14),
        dt.date(2025, 4, 7),
        dt.date(2025, 12, 14),
        dt.date(2026, 8, 23),
        TODAY,
    ]
    controls_on_file = ["principal", "conditional", "prohibited", "unknown"]
    statuses: set[tuple[str, str]] = set()
    for _ in range(600):
        fields: dict[str, Any] = {
            "business_type": rng.choice(get_args(BusinessType)),
            "serves_alcohol": rng.choice([True, False]),
            "alcohol_type": rng.choice(["none", "beer_wine", "full_liquor"]),
            "closes_after_midnight": rng.choice([True, False]),
            "closes_after_2am": rng.choice([True, False, False]),
            "live_entertainment": rng.choice([True, False]),
            "dancing": rng.choice([True, False, False]),
            "outdoor_seating": rng.choice([True, False]),
            "sidewalk_or_parklet": rng.choice([True, False, False]),
            "change_of_use": rng.choice([True, False]),
            "new_construction": rng.choice([True, False, False]),
            "seats": rng.choice([None, 20, 49, 50, 120]),
            "square_feet": rng.choice([None, 800, 2500, 4500, 7000, 130000]),
            "licence_type": rng.choice([None, None, "41", "42", "47", "48", "75", "90", "20"]),
            "alcohol_transaction": rng.choice(
                [
                    None,
                    "new_licence",
                    "person_to_person_transfer",
                    "premises_transfer",
                    "licence_already_held",
                ]
            ),
            "formula_retail": rng.choice([None, True, False]),
            "floor_area_before_sqft": rng.choice([None, 800, 2500]),
            "existing_use_stated": rng.choice(
                [[], ["bar"], ["restaurant"], ["retail"], ["laundromat"], ["vacant"], ["other"]]
            ),
            "changes_existing_business": rng.choice(
                [None, None, "none", "enlarge", "intensify", "enlarge_and_intensify"]
            ),
            "merges_storefronts": rng.choice([None, True, False]),
            "stories": rng.choice([[], ["first"], ["second"], ["basement"], ["first", "third_or_above"]]),
            "closing_hour": rng.choice([None, "21:00", "23:30", "00:00", "02:00", "03:30", "06:00"]),
            "entertainment_kind": rng.choice(
                [None, "none", "limited_live_performance", "place_of_entertainment"]
            ),
            "outdoor_area": rng.choice(
                [None, "none", "front", "rear_or_side", "rooftop", "parking_lot", "sidewalk"]
            ),
            "amends_prior_approval": rng.choice([None, True, False]),
            "occupants_under_50": rng.choice([None, True, False]),
        }
        prof = BusinessProfile(**fields)
        code = rng.choice(districts)
        z = (
            None
            if code is None
            else zoning(code, bar=rng.choice(controls_on_file), restaurant=rng.choice(controls_on_file))
        )
        overlays, records = rng.choice(overlay_sets), rng.choice(record_sets)
        rules_date = rng.choice(dates)
        dates_and_tract: dict[str, Any] = {
            "today": rng.choice([rules_date, TODAY]),
            "rules_date": rules_date,
            "tract": rng.choice([None, TRACT_OVER, "9999.99"]),
        }
        d = determine(prof, z, overlays, records, SITE_995, ALL_AREAS, **dates_and_tract)
        again = determine(
            prof,
            z,
            list(reversed(overlays)),
            list(reversed(records)),
            SITE_995,
            list(reversed(ALL_AREAS)),
            **dates_and_tract,
        )
        assert again.model_dump_json() == d.model_dump_json()
        p = d.pathway
        assert [f.rule_id for f in p.triggers] == list(
            triggers.ORDER
        ) and p.rules_date == rules_date.isoformat()
        assert p.changes is not None and p.changes.planning_use == p.change_of_use
        outcome = triggers.zoning_outcome(p.triggers)
        zoning_row = row(d, "zoning_use")
        assert (zoning_row.status, zoning_row.status_note, zoning_row.missing_inputs) == (
            outcome.status,
            outcome.status_note,
            list(outcome.missing_inputs),
        )
        for r in d.rows:
            statuses.add((r.area, r.status))
            assert r.basis and r.approval and r.agency
            if r.status != "insufficient_information":
                assert r.missing_inputs == [], r.area
            elif (
                r.area != "building_change_of_use"
            ):  # a business the table does not cover names no input there
                assert r.missing_inputs, r.area
            if r.status == "not_permitted":
                assert r.referral_steps == [] and zoning_row.status == "not_permitted"
            if r.area == "alcohol" and row(d, "health").status == "not_permitted":
                assert r.status == "not_permitted"  # the licence follows a use that is itself prohibited
            if r.status_note is not None:
                assert r.status == "further_review"
                assert r.status_note == (PRACTICE_NOTE if r.area == "zoning_use" else PCN_STATUS_NOTE)
        # rule 8: the most severe row status, never below a definite headline finding (rule 9)
        definite = {h.status for h in d.headline_findings if h.definite}
        assert d.overall_status == next(
            s for s in STATUS_SEVERITY if s in {r.status for r in d.rows} | definite
        )
        assert d.entitlement_path == entitlement_path(d.rows)
        assert d.overall_line == overall_line(d.rows, d.headline_findings)
        # rule 9: a trigger that bars the concept leads alone; else every Conditional Use, then the contingent ones
        found = d.pathway.triggers
        if "zoning_use" not in {r.area for r in d.rows}:
            assert d.headline_findings == []
        elif any(f.control == "not_permitted" and not f.unsettled_by for f in found):
            assert {h.kind for h in d.headline_findings} == {"not_permitted"}
        else:
            # a decided control an input not given could change is never definite (T7 and the last use)
            assert [h.trigger for h in d.headline_findings if h.definite] == [
                f.rule_id for f in found if f.control == "conditional" and not f.unsettled_by
            ]
            assert [(h.trigger, h.condition) for h in d.headline_findings if not h.definite] == [
                (f.rule_id, c.condition)
                for f in found
                if f.control == "not_decided" or f.unsettled_by
                for c in f.contingent
            ]
        for h in d.headline_findings:
            assert h.definite == (h.condition is None) and h.sentence and h.basis
            if not h.definite:
                assert h.sentence.startswith(f"If {h.condition}, ") and h.missing_inputs
                assert h.status == row(d, h.area).status
        for q in d.open_questions:
            assert 15 <= len(q.question) <= pw.QUESTION_MAX and q.question.endswith((".", "?"))
    # the sweep reaches every status of every row that can take it
    assert {s for a, s in statuses if a == "zoning_use"} == {
        "allowed",
        "further_review",
        "not_permitted",
        "insufficient_information",
    }
    assert {s for a, s in statuses if a == "alcohol"} == {
        "allowed",  # a licence already held (review)
        "not_permitted",
        "potential_blocker",
        "further_review",
        "insufficient_information",
    }
    assert {s for a, s in statuses if a == "outdoor"} == {
        "allowed",
        "further_review",
        "not_permitted",
        "insufficient_information",
    }
    assert {s for a, s in statuses if a == "building_change_of_use"} == {
        "allowed",
        "further_review",
        "not_permitted",
        "insufficient_information",
    }
    assert {s for a, s in statuses if a == "health"} == {"allowed", "not_permitted"}
    assert {s for a, s in statuses if a == "entertainment"} == {"further_review", "not_permitted"}


def test_the_two_small_additions_to_the_trigger_and_row_modules() -> None:
    """`triggers.evaluate(as_new=True)` reads every trigger as for a new use, and `rows.change_answers`
    takes the applicant's own description of a change of use where nothing else decides it."""
    concept = concept_facts(given(COCKTAIL_BAR, changes_existing_business="none", **STATED))
    site = site_facts([TYPE_48_AT_995], SITE_995, rules_date=TODAY)
    read = {"rules_date": TODAY, "today": TODAY}
    plain = triggers.evaluate(concept, site, zoning(), VALENCIA_OVERLAYS, **read)
    as_new = triggers.evaluate(concept, site, zoning(), VALENCIA_OVERLAYS, as_new=True, **read)
    assert [f.rule_id for f in as_new] == list(triggers.ORDER)
    by_id = {f.rule_id: (f.control, g.control) for f, g in zip(plain, as_new, strict=True)}
    assert by_id["T1"] == ("does_not_apply", "conditional")
    assert by_id["T2"] == ("does_not_apply", "conditional")
    assert by_id["T3"] == ("principal", "does_not_apply")
    # the default is the plain reading, and reading as new changes nothing where nothing continues
    nothing_on_file = site_facts([], SITE_995, rules_date=TODAY)
    fresh = concept_facts(given(COCKTAIL_BAR, **STATED))
    assert triggers.evaluate(
        fresh, nothing_on_file, zoning(), VALENCIA_OVERLAYS, **read
    ) == triggers.evaluate(fresh, nothing_on_file, zoning(), VALENCIA_OVERLAYS, as_new=True, **read)
    # change_answers: the description decides only where the records and a stated last use do not
    assert row_rules.DESCRIBED_CHANGES == ("new_construction", "applicant")
    undecided = row_rules.change_answers(fresh, nothing_on_file, [], zoning(), rules_date=TODAY)
    described = row_rules.change_answers(
        fresh, nothing_on_file, [], zoning(), rules_date=TODAY, described_change="new_construction"
    )
    assert (undecided.planning_use, described.planning_use) == ("not_established", "yes")
    assert described.planning_use_lines[-1].rule_id == "zoning.change_of_use"
    on_file = row_rules.change_answers(
        fresh, site, [], zoning(), rules_date=TODAY, described_change="applicant"
    )
    assert on_file.planning_use == "no"  # the Bar on file decides it
    with pytest.raises(ValueError, match="described_change"):
        row_rules.change_answers(
            fresh, nothing_on_file, [], zoning(), rules_date=TODAY, described_change="other"
        )


# ---- the fixed text ------------------------------------------------------------------------------------------
def test_fixed_sentences_do_not_speculate_and_every_one_is_reachable() -> None:
    banned = re.compile(
        r"neighbou?r|oppos|protest|objection|communit|complain|controvers|resident", re.IGNORECASE
    )
    for key, basis in LEGAL_BASIS.items():
        assert not banned.search(basis.text), key
        assert "license" not in basis.text, key  # spelled "licence", as the report does
        assert basis.source_url is None or basis.source_url.startswith("https://"), key
    for text in (pw.MISSING_INPUT_QUESTION, *(q for q, _ in pw.OPEN_QUESTIONS.values())):
        assert not banned.search(text) and "license" not in text
    produced: set[tuple[str, str]] = set()
    extra = [
        # H0z, B0z, E0z and O0z: formula retail bars a chain cafe on Irving Street (backtest case N09)
        run(
            given(
                profile("cafe"),
                formula_retail=True,
                existing_use_stated=["limited_restaurant"],
                outdoor_seating=True,
                entertainment_kind="place_of_entertainment",
                closing_hour="21:00",
            ),
            z=zoning("NCD-IRVING", section="Planning Code § 732"),
            overlays=[],
            rules_date=dt.date(2024, 7, 30),
            today=dt.date(2024, 7, 30),
        ),
        # rule 1a: the applicant's "No alcohol" answer over a description that mentioned alcohol
        run(profile("bar", no_alcohol_answer_over_description=True)),
        # rule 1b: the kind of food or drink service answered for a zero-proof bar, and answered for a restaurant
        # (not read)
        run(
            given(
                profile("bar", no_alcohol_stated=True),
                food_service="limited_restaurant",
                intake_answered=["food_service"],
            )
        ),
        run(given(RESTAURANT, food_service="limited_restaurant", intake_answered=["food_service"])),
        # Z-D: the Code and Planning practice differ
        run(given(DRY_RESTAURANT, **STATED), z=UMU, overlays=[MISSION_SUD]),
        # Z-A and the outdoor rows
        run(patio("front"), z=MISSION, overlays=[]),
        run(patio("rear_or_side"), z=MISSION, overlays=[]),
        run(patio("rear_or_side"), z=RH2, overlays=[]),
        # the same, with the place of the area the applicant's intake answer
        *(
            run(given(patio(place), intake_answered=["outdoor_area"]), z=z, overlays=[])
            for place, z in (("front", MISSION), ("rooftop", MISSION), ("rear_or_side", RH2))
        ),
        run(patio(None), z=MISSION, overlays=[]),
        run(given(patio(None), sidewalk_or_parklet=True), z=MISSION, overlays=[]),
        # two uses
        run(given(WINE_BAR, dancing=True), z=C2, overlays=[]),
        # E2 and E3
        run(given(DRY_RESTAURANT, closes_after_2am=True, **STATED), z=C2, overlays=[]),
        run(given(WINE_BAR, closes_after_2am=True, **STATED), z=C2, overlays=[]),
        # a licence rule that bars a concept that serves no alcohol is "not applied" in a district not carried
        run(given(profile("bar"), **STATED), z=not_carried(bar="principal"), overlays=[THIRD_ST_RUD]),
        run(given(COCKTAIL_BAR, **STATED), z=not_carried(bar="principal"), overlays=[THIRD_ST_RUD]),
        # the intake model read alcohol, entertainment or an outdoor area the text does not state (app.memo.stated)
        run(
            given(profile("bar"), intake_cleared={"serves_alcohol": True}, **STATED),
            z=not_carried(bar="principal"),
            overlays=[THIRD_ST_RUD],
        ),
        run(given(DRY_RESTAURANT, intake_cleared={"live_entertainment": True}, **STATED), z=C2, overlays=[]),
        run(given(DRY_RESTAURANT, intake_cleared={"outdoor_seating": True}, **STATED), z=C2, overlays=[]),
        # the Mission requirement (A2), the county limit, a Bar where one is already on file
        run(given(COCKTAIL_BAR, **NEW_LICENCE, **STATED)),
        run(given(COCKTAIL_BAR, **NEW_LICENCE, **STATED), records=[TYPE_48_AT_995, TYPE_41_AT_995]),
        run(COCKTAIL_BAR, records=[TYPE_48_AT_995]),
        run(given(RESTAURANT, **NEW_LICENCE, **STATED), z=C2, overlays=[]),
        # review: an outdoor area not placed where it is principal everywhere on the lot; the dance permit while it
        # was an approval; the existing-use sentences at a past rules date
        run(patio(None), z=C2, overlays=[]),
        run(given(WINE_BAR, dancing=True, **STATED), z=C2, overlays=[], rules_date=dt.date(2025, 6, 1)),
        run(
            given(WINE_BAR, closes_after_2am=True, **STATED),
            z=C2,
            overlays=[],
            rules_date=dt.date(2025, 6, 1),
        ),
        run(
            COCKTAIL_BAR, records=[TYPE_48_AT_995], rules_date=dt.date(2030, 1, 1), today=dt.date(2030, 6, 1)
        ),
        run(
            COCKTAIL_BAR,
            records=[TYPE_48_AT_995, TYPE_41_AT_995],
            rules_date=dt.date(2030, 1, 1),
            today=dt.date(2030, 6, 1),
        ),
        run(COCKTAIL_BAR, rules_date=dt.date(2024, 6, 1)),
        run(WINE_BAR, site=site_of("Valencia St & 21st St", None, None), rules_date=dt.date(2024, 6, 1)),
    ]
    for d in [*(d for *_, d in GRID_RESULTS), *extra]:
        produced |= {(line.rule_id, line.text) for line in all_lines(d)}
    nowhere = site_of("Valencia St & 21st St", None, None)
    produced |= {(line.rule_id, line.text) for line in all_lines(run(WINE_BAR, site=nowhere))}

    def reachable(key: str, template: str) -> bool:
        pattern = re.escape(template)
        pattern = re.sub(r"\\\{[a-z_]+\\\}", ".*", pattern)
        return any(
            rid == key.split("/")[0] and re.fullmatch(pattern, text, re.DOTALL) for rid, text in produced
        )

    unreachable = [key for key, basis in LEGAL_BASIS.items() if not reachable(key, basis.text)]
    assert unreachable == []
    # every approval name and label the engine can print is one of the fixed tables' values
    approvals = {
        r.approval for *_, d in GRID_RESULTS for r in d.rows if r.area in ("zoning_use", "outdoor", "health")
    }
    assert approvals <= {*pw.ZONING_APPROVALS.values(), *pw.APPROVALS.values()}
    labels = {d.pathway.permission_label for *_, d in GRID_RESULTS}
    assert labels <= {*USE_PERMISSION_LABELS.values(), pw.NOT_DECIDED_LABEL, PRACTICE_NOTE}
