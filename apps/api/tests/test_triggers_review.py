"""The confirmed review findings on the eleven trigger rules (rule table v2), one test or more per finding.

Synthetic inputs against the bundled dated control data, with the builders of tests/test_triggers.py. No database,
no model, no network, no clock.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import pytest

from app.memo import controls
from app.memo import triggers as tg
from app.memo.facts import MISSING_PHRASES, concept_facts
from app.models.profile import BusinessProfile
from tests.test_triggers import (
    HAIGHT,
    MISSION,
    SOMA,
    THIRD,
    TODAY,
    D,
    ids,
    overlay,
    run,
    site,
    text_of,
    zoning,
)

CHANGE = MISSING_PHRASES["changes_existing_business"]
LICENCE = MISSING_PHRASES["licence_type"]
GEARY = overlay(
    "datasf_sud:geary_blvd_formula_retail_pet_supply_store_and_formula_retail_eating_and_drinking_subdistrict",
    "Geary Boulevard Formula Retail Pet Supply Store and Formula Retail Eating and Drinking Subdistrict",
    "Planning Code § 781.4",
)
TARAVAL = overlay(
    "datasf_sud:taraval_street_restaurant_subdistrict",
    "Taraval Street Restaurant Subdistrict",
    "Planning Code § 781.1",
)


# ---- the typed fields read from quoted code text ------------------------------------------------------------------
# Each field the rules read from a version's quote or note, as the data file carries it: (district, rows, the
# version's "from", field, its value, the words of the quote or note it restates, built from the value). A change
# to the value, or to the words, fails here.
EATING_ROWS = ("bar", "restaurant", "limited_restaurant")
GEARY_NAME = (
    "Geary Boulevard Formula Retail Pet Supply Store and Formula Retail Eating and Drinking Subdistrict"
)
TARAVAL_NAME = "Taraval Street Restaurant Subdistrict"
RH2_ROWS_BY_DATE = [
    {"from": None, "to": "2024-01-13", "rows": ["Limited Commercial Uses (§ 186)"]},
    {
        "from": "2024-01-14",
        "to": None,
        "rows": ["Limited Corner Commercial Uses (§ 231)", "Limited Commercial Uses (§ 186)"],
    },
]


def _exempt(value: dict[str, Any], figure: str) -> list[str]:
    """`figure` is the size as the note prints it ("2,500", "5000")."""
    assert figure.replace(",", "") == str(value["larger_than_sqft"])
    note = value["source"].split(" ", 2)[-1]  # "Note 1"
    return [
        f"{note}: 'C for Use Size is not required for {value['use'].title()}s larger than {figure} sq. ft."
    ]


def _cap(value: dict[str, Any]) -> list[str]:
    return [f"capped at {value['max_uses']}", f"{value['source'].split(' ', 2)[-1]} ("]


def _rh2_rows(value: list[dict[str, Any]]) -> list[str]:
    before, after = value
    return [
        f"Limited Corner Commercial Uses, § 231: none in RH Districts until {before['to']}",
        f"from {after['from']} (Ord. 249-23, File No. 230701",
        "(a) Limited Commercial Uses, § 186",
        *(row.split(" (")[0] for row in after["rows"]),
    ]


QUOTED_FIELDS: list[tuple[str, tuple[str, ...], str | None, str, Any, Any]] = [
    # Table 811 / 810 Note 1
    (
        "CVR",
        ("use_size",),
        None,
        "conditional_not_required_for",
        {"use": "restaurant", "larger_than_sqft": 2500, "source": "Table 811 Note 1"},
        lambda v: _exempt(v, "2,500"),
    ),
    *(
        (
            "CCB",
            ("use_size",),
            start,
            "conditional_not_required_for",
            {"use": "restaurant", "larger_than_sqft": 5000, "source": "Table 810 Note 1"},
            lambda v: _exempt(v, "5000"),
        )
        for start in (None, "2025-01-19")
    ),
    # the use size row against the section it cites
    (
        "CCB",
        ("use_size",),
        None,
        "other_code_text_figures",
        {"section": "Planning Code § 121.4", "principal_below_sqft": 2501, "not_permitted_from_sqft": 5001},
        lambda v: [
            f"Under {v['section'].removeprefix('Planning Code ')} the figures for this period would be "
            f"principal_below_sqft {v['principal_below_sqft']} and not_permitted_from_sqft "
            f"{v['not_permitted_from_sqft']}"
        ],
    ),
    (
        "C-2",
        ("use_size",),
        "2023-08-05",
        "other_code_text_figures",
        {"section": "Planning Code § 121.6", "principal_below_sqft": 50001, "not_permitted_from_sqft": None},
        lambda v: [
            f"struck {v['section'].removeprefix('Planning Code ')}(c), the prohibition over 120,000 gross sq ft",
            f"left only the Conditional Use over {v['principal_below_sqft'] - 1:,} gross sq ft outside C-3",
        ],
    ),
    (
        "C-2",
        ("use_size",),
        "2025-10-06",
        "other_code_text_figures",
        {"section": "Planning Code § 121.6", "principal_below_sqft": 50001, "not_permitted_from_sqft": None},
        lambda v: [
            f"{v['section'].removeprefix('Planning Code ')} today",
            f"has only the Conditional Use over {v['principal_below_sqft'] - 1:,} gross sq ft outside C-3 and "
            "no prohibition",
        ],
    ),
    (
        "C-3-G",
        ("use_size",),
        "2023-08-05",
        "other_code_text_figures",
        {"section": "Planning Code § 121.6", "principal_below_sqft": None, "not_permitted_from_sqft": None},
        lambda v: [
            f"so {v['section'].removeprefix('Planning Code ')} no longer limits retail size in C-3 at all"
        ],
    ),
    (
        "C-3-G",
        ("use_size",),
        "2025-10-06",
        "other_code_text_figures",
        {"section": "Planning Code § 121.6", "principal_below_sqft": None, "not_permitted_from_sqft": None},
        lambda v: [
            f"{v['section'].removeprefix('Planning Code ')} today",
            "exempts the C-3 Zoning Districts",
        ],
    ),
    # Table 754 Note 7
    *(
        (
            "NCT-MISSION",
            (row,),
            start,
            "eating_drinking_cap",
            {
                "max_uses": cap,
                "columns": ["first", "second"] if row == "bar" else ["first"],
                "source": "Table 754 Note 7",
            },
            _cap,
        )
        for row in EATING_ROWS
        for start, cap in ((None, 167), ("2024-01-14", 179))
    ),
    # RH-2: the rows outside the use's own row, and the date § 231 reached RH districts
    ("RH-2", EATING_ROWS, None, "exception_rows_by_date", RH2_ROWS_BY_DATE, _rh2_rows),
    # Table 716 Note 3
    (
        "NCD-INNER CLEMENT",
        ("bar",),
        None,
        "exceptions",
        {"bar_licence_other_than_abc_type_42_note_3": "NP"},
        lambda v: [
            "the establishment maintains only an ABC license type 42",
            "other ABC license types, except those included in the Section 102 definition of a Restaurant, "
            "are not permitted",
        ],
    ),
    # Table 719 Note (4), "NP(3)(4)"
    (
        "NCD-HAIGHT",
        ("restaurant",),
        None,
        "exceptions",
        {"haight_restaurant_quota_note_4": "C"},
        lambda v: [
            f"unless it fell within Note 4's quota, in which case it was {v['haight_restaurant_quota_note_4']}",
            "no more than a total of 3 Restaurants",
        ],
    ),
    # Table 838 Note 1 (UMU): P on one lot
    (
        "UMU",
        ("formula_retail",),
        "2023-08-05",
        "principal_exception",
        {"control": "P", "where": "Assessor's Parcel Block No. 3781, Lot 003", "source": "Table 838 Note 1"},
        lambda v: [
            f"(1) {v['control']} on {v['where'].replace(chr(39), chr(8217))}",
            f"Note 1: {v['control']} on {v['where']}",
        ],
    ),
    # the sub-areas an overlay on file places (the overlay's code section names the section)
    *(
        (
            "NC-3",
            ("formula_retail",),
            start,
            "subarea_overlay_sections",
            {GEARY_NAME: "781.4"},
            lambda v: [*v, *(f"Section {s}" for s in v.values())],
        )
        for start in (None, "2024-01-14")
    ),
    *(
        ("NC-1", (row,), None, "subarea_overlay_sections", {TARAVAL_NAME: "781.1"}, lambda v: [*v])
        for row in ("restaurant", "limited_restaurant", "formula_retail")
    ),
    *(
        ("NC-2", (row,), None, "subarea_overlay_sections", {TARAVAL_NAME: "781.1"}, lambda v: [*v])
        for row in ("restaurant", "limited_restaurant", "formula_retail")
    ),
]


@pytest.mark.parametrize(
    "district, rows, start, field, value, words_of",
    QUOTED_FIELDS,
    ids=[f"{q[0]}/{'+'.join(q[1])}/{q[2]}/{q[3]}" for q in QUOTED_FIELDS],
)
def test_every_typed_field_restates_words_of_its_version(
    district: str, rows: tuple[str, ...], start: str | None, field: str, value: Any, words_of: Any
) -> None:
    raw = json.loads(controls.DATA_PATH.read_text(encoding="utf-8"))
    for row in rows:
        found = [v for v in raw["districts"][district]["rows"][row] if v["from"] == start]
        assert len(found) == 1, (district, row, start)
        version = found[0]
        assert version[field] == value, (district, row, start, field)
        words = version["quote"] + " " + version["note"]
        for phrase in words_of(version[field]):
            assert phrase in words, (district, row, start, phrase)
        if field == "eating_drinking_cap":  # the cells the quote marks with the note are the columns capped
            cells = version["quote"].split(" ... ")[0].split(" | ")[-3:]
            mark = f"({value['source'].rsplit(' ', 1)[-1]})"  # "(7)"
            marked = [c for c, cell in zip(("first", "second", "third"), cells, strict=True) if mark in cell]
            assert marked == value["columns"], (district, row, start, cells)
        if field == "exception_rows_by_date":  # a split inside the version, inside its dates
            start_day = dt.date.fromisoformat(version["from"]) if version["from"] else controls.DATA_START
            end_day = dt.date.fromisoformat(version["to"]) if version["to"] else dt.date.max
            for part in version[field][:-1]:
                assert start_day <= dt.date.fromisoformat(part["to"]) < end_day


def test_the_typed_fields_are_on_no_other_version() -> None:
    """Every version that carries one of these fields is listed above (the RM-3 rows and the Bayview, MUR and
    RC-4 entries were in the data before; they are held by the tests of their own triggers)."""
    raw = json.loads(controls.DATA_PATH.read_text(encoding="utf-8"))
    listed = {(d, row, start, field) for d, rows, start, field, _, _ in QUOTED_FIELDS for row in rows}
    earlier = {"exceptions": {"NCD-BAYVIEW", "MUR"}, "principal_exception": {"RC-4"}}
    found = {
        (district, row, version["from"], field)
        for district, body in raw["districts"].items()
        for row, versions in body["rows"].items()
        for version in versions
        for field in {q[3] for q in QUOTED_FIELDS}
        if field in version and district not in earlier.get(field, set())
    }
    assert found == listed


def test_the_rules_read_the_typed_fields_through_the_controls_results() -> None:
    on = D(2024, 6, 1)
    assert controls.use_size("CVR", on).extra["conditional_not_required_for"]["larger_than_sqft"] == 2500
    assert (
        controls.use_control("NCT-MISSION", "bar", "first", on).extra["eating_drinking_cap"]["max_uses"]
        == 179
    )
    assert controls.formula_retail("NC-3", on).extra["subarea_overlay_sections"] == {GEARY_NAME: "781.4"}
    dated = controls.use_control("RH-2", "bar", "first", on).extra["exception_rows_by_date"]
    found = controls.version_on(dated, on)
    assert found is not None and len(found.version["rows"]) == 2
    found = controls.version_on(dated, D(2024, 1, 13))
    assert found is not None and found.version["rows"] == ("Limited Commercial Uses (§ 186)",)


def test_quote_readings_table_is_gone() -> None:
    for name in ("QUOTE_READINGS", "QuoteReading", "typed_extra", "_quote_fields"):
        assert not hasattr(tg, name), name


# ---- T3: the standing as new of a use that continues ----------------------------------------------------------------
def _existing(use: str, on: dt.date, *licences: str, **given: Any) -> dict[str, Any]:
    return {
        "at": site(on, existing_use=use, licences=licences),  # type: ignore[arg-type]
        "planning_use": use,
        "business_type": use,
        "existing_use_stated": use,
        "story": "first",
        **given,
    }


def test_t3_reads_the_licence_rule_for_a_new_establishment_haight() -> None:
    on = D(2025, 1, 1)
    found = run("NCD-HAIGHT", on, HAIGHT, **_existing("restaurant", on, "41"), changes_existing_business="enlarge",
                floor_area_sqft=1500)["T3"]  # fmt: skip
    assert (
        found.control == "conditional"
    )  # a new Restaurant with Type 41 needs Conditional Use (§ 781.9(c)(2))
    assert "T3:haight.new_on_sale_establishment" in ids(found)
    assert found.lines[-1].rule_id == "T3.conditional_use"


def test_t3_reads_the_licence_rule_for_a_new_establishment_bayview() -> None:
    on = D(2025, 4, 6)
    found = run("NCD-BAYVIEW", on, THIRD, **_existing("bar", on, "48"), changes_existing_business="enlarge")[
        "T3"
    ]
    assert found.control == "conditional"
    assert "T3:third.new_on_sale_establishment" in ids(found)
    assert found.lines[-1].rule_id == "T3.nonconforming_nc"  # § 186.1: a new one would be barred


def test_t3_code_and_practice_differ_when_the_standing_as_new_is_that_split() -> None:
    given = {
        "planning_use": "restaurant",
        "existing_use_stated": "restaurant",
        "story": "first",
    }
    found = run("UMU", D(2023, 1, 1), MISSION, **given, changes_existing_business="enlarge")["T3"]
    assert found.control == "code_and_practice_differ"
    assert found.lines[-1].rule_id == "T3.practice_differs"
    missing = run("UMU", D(2023, 1, 1), MISSION, **given, at=site(D(2023, 1, 1), existing_use="restaurant"))
    assert missing["T3"].control == "not_decided" and missing["T3"].missing_inputs == [CHANGE]


def test_t3_licence_type_missing_for_a_bar_names_it() -> None:
    on = D(2025, 1, 1)
    found = run("NCD-HAIGHT", on, HAIGHT, planning_use="bar", existing_use_stated="bar", story="first",
                changes_existing_business="enlarge")["T3"]  # fmt: skip
    assert found.control == "conditional"  # the Bar cell is C; the licence rule is not decided
    assert "T3.licence_missing" in ids(found)


# ---- T7: Table 811 / 810 Note 1, and the other code text --------------------------------------------------------------
def test_t7_restaurant_exemption_with_its_own_threshold() -> None:
    cvr = run("CVR", D(2024, 6, 1), planning_use="restaurant", floor_area_sqft=3000)["T7"]
    assert cvr.control == "principal" and "T7.restaurant" in ids(cvr)
    assert "T7.exemption" in ids(cvr)  # the § 121.4 Legacy Business part is still printed
    assert run("CVR", D(2024, 6, 1), planning_use="bar", floor_area_sqft=3000)["T7"].control == "conditional"
    # CCB from 2025-01-19: the row is C from 2,501, the note still from 5,000
    assert (
        run("CCB", D(2025, 6, 1), planning_use="restaurant", floor_area_sqft=3000)["T7"].control
        == "conditional"
    )
    # CCB to 2025-01-18: 5,000 is not larger than 5,000
    assert (
        run("CCB", D(2025, 1, 18), planning_use="restaurant", floor_area_sqft=5000)["T7"].control
        == "conditional"
    )
    # 5,500: the row's Note 1 needs no Conditional Use, but § 121.4 (which the row cites and disagrees with on this
    # date) does not permit it, so the two texts decide differently
    big = run("CCB", D(2025, 1, 18), planning_use="restaurant", floor_area_sqft=5500)["T7"]
    assert "T7.restaurant" in ids(big) and "T7.texts_differ" in ids(big)
    assert big.control == "not_decided"


def test_t7_the_row_against_the_section_it_cites() -> None:
    small = run("CCB", D(2025, 1, 18), planning_use="restaurant", floor_area_sqft=3000)["T7"]
    assert small.control == "not_decided"
    assert small.missing_inputs == [
        tg.NOT_KNOWN["code_texts_differ"].format(
            a="the table row (Planning Code § 810)", b="Planning Code § 121.4"
        )
    ]
    assert "T7.texts_differ" in ids(small)
    # from 2025-01-19 the row follows § 121.4
    assert (
        run("CCB", D(2025, 1, 19), planning_use="restaurant", floor_area_sqft=3000)["T7"].control
        == "conditional"
    )
    # C-2 from 2023-08-05: § 121.6 has no prohibition over 120,000 sq ft
    c2 = run("C-2", D(2024, 6, 1), planning_use="restaurant", floor_area_sqft=130_000)["T7"]
    assert c2.control == "not_decided"
    assert run("C-2", D(2023, 6, 1), planning_use="restaurant", floor_area_sqft=130_000)["T7"].control == (
        "not_permitted"
    )
    assert run("C-2", D(2024, 6, 1), planning_use="restaurant", floor_area_sqft=60_000)["T7"].control == (
        "conditional"
    )


def test_t7_a_new_use_taking_over_an_existing_space() -> None:
    on = TODAY
    shown = site(on, existing_use="restaurant", licences=("41",))
    given = {"planning_use": "bar", "business_type": "bar", "floor_area_sqft": 3500, "story": "first"}
    found = run("NCT-VALENCIA", on, at=shown, **given)["T7"]
    assert found.control == "not_decided"
    assert found.missing_inputs == [
        MISSING_PHRASES["floor_area_before_sqft"],
        MISSING_PHRASES["merges_storefronts"],
    ]
    assert "T7.existing_space" in ids(found)
    same = run("NCT-VALENCIA", on, at=shown, **given, floor_area_before_sqft=3500, merges_storefronts=False)[
        "T7"
    ]
    assert same.control == "does_not_apply"
    assert "no storefronts are merged, so the use size control does not apply" in text_of(same)
    grows = run("NCT-VALENCIA", on, at=shown, **given, floor_area_before_sqft=2000, merges_storefronts=False)
    assert grows["T7"].control == "conditional"
    # North Beach until 2025-10-05: a new Conditional Use to change an oversized use
    nb = run("NCD-NORTH BEACH", D(2025, 6, 1), at=site(D(2025, 6, 1), existing_use="restaurant"), **given)[
        "T7"
    ]
    assert nb.control == "conditional"
    assert "a new Conditional Use is needed to change a use over the threshold" in text_of(nb)


def test_named_districts_are_the_data_s_own() -> None:
    for on in (D(2024, 6, 1), TODAY):
        named = controls.citywide_rules("use_size_general", on)[0].extra["facts"][
            "new_conditional_use_to_change_oversized_use"
        ]
        assert set(named) <= set(tg.NAMED_DISTRICTS)
    assert all(controls.covers(code) for code in tg.NAMED_DISTRICTS.values())


# ---- T1: the Mission Street cap, RH-2, Inner Clement, the sub-areas, the Haight quota ----------------------------------
def test_t1_mission_street_cap_on_eating_and_drinking_uses() -> None:
    cafe = {"planning_use": "limited_restaurant", "story": "first", "floor_area_sqft": 1000,
            "formula_retail": False, "closing_hour": "22:00"}  # fmt: skip
    now = run("NCT-MISSION", D(2025, 6, 1), MISSION, **cafe)["T1"]
    assert now.control == "not_decided"
    assert now.missing_inputs == [tg.NOT_KNOWN["eating_drinking_cap"].format(max=179)]
    assert "T1.cap" in ids(now)
    then = run("NCT-MISSION", D(2024, 1, 13), MISSION, **cafe)["T1"]
    assert then.missing_inputs == [tg.NOT_KNOWN["eating_drinking_cap"].format(max=167)]
    upstairs = run("NCT-MISSION", D(2025, 6, 1), MISSION, **{**cafe, "story": "third_or_above"})["T1"]
    assert upstairs.control == "not_permitted" and "T1.cap" not in ids(upstairs)
    # a Bar's second story carries (7) too
    assert "T1.cap" in ids(run("NCT-MISSION", D(2025, 6, 1), planning_use="bar", story="second")["T1"])


def test_t1_rh2_and_rm3_read_alike_from_2024_01_14() -> None:
    for district in ("RH-2", "RM-3"):
        found = run(district, D(2025, 1, 1), planning_use="restaurant", floor_area_sqft=1000, story="first")[
            "T1"
        ]
        assert found.control == "not_decided", district
        assert "Limited Corner Commercial Uses (§ 231)" in found.missing_inputs[0]
    early = run("RH-2", D(2023, 6, 1), planning_use="restaurant", story="first")["T1"]
    assert early.missing_inputs == [tg.NOT_KNOWN["table_rows"].format(rows="Limited Commercial Uses (§ 186)")]


def test_t1_inner_clement_bar_by_licence_type() -> None:
    on = D(2024, 6, 1)
    bar = {"planning_use": "bar", "story": "first"}
    assert run("NCD-INNER CLEMENT", on, **bar, licence_type="42")["T1"].control == "conditional"
    assert run("NCD-INNER CLEMENT", on, **bar, licence_type="48")["T1"].control == "not_permitted"
    assert run("NCD-INNER CLEMENT", on, **bar, licence_type="41")["T1"].control == "conditional"  # § 102
    missing = run("NCD-INNER CLEMENT", on, **bar)["T1"]
    assert missing.control == "not_decided" and missing.missing_inputs == [LICENCE]
    assert run("NCD-INNER CLEMENT", on, **{**bar, "story": "second"}, licence_type="42")["T1"].control == (
        "not_permitted"
    )


def test_a_sub_area_an_overlay_places_is_applied() -> None:
    chain = {"planning_use": "restaurant", "formula_retail": True, "story": "first"}
    inside = run("NC-3", D(2025, 6, 1), GEARY, **chain)["T5"]
    assert inside.control == "not_permitted"
    assert "an overlay on file places the address inside Geary Boulevard" in text_of(inside)
    assert f"overlay:{GEARY.id}" in {c for line in inside.lines for c in line.citations}
    assert run("NC-3", D(2025, 6, 1), **chain)["T5"].control == "conditional"
    taraval = run("NC-1", D(2023, 6, 1), TARAVAL, planning_use="restaurant", story="first")["T1"]
    assert taraval.control == "conditional" and "T1.subarea" in ids(taraval)
    assert run("NC-1", D(2023, 6, 1), planning_use="restaurant", story="first")["T1"].control == "principal"
    assert run("NC-2", D(2023, 6, 1), TARAVAL, planning_use="restaurant", story="first")["T1"].control == (
        "conditional"
    )
    # a sub-area no overlay on file can place stays not decided (NC-1, Note 6)
    assert run("NC-1", D(2024, 6, 1), planning_use="bar", story="first")["T1"].control == "not_decided"


def test_t1_haight_restaurant_quota_before_2024_01_14() -> None:
    for alcohol in ({}, {"serves_alcohol": True, "licence_type": "47"}):
        found = run("NCD-HAIGHT", D(2023, 6, 1), planning_use="restaurant", story="first", **alcohol)["T1"]
        assert found.control == "not_decided"
        assert found.missing_inputs == [tg.NOT_KNOWN["haight_restaurant_quota"]]
    upstairs = run("NCD-HAIGHT", D(2023, 6, 1), planning_use="restaurant", story="second")["T1"]
    assert upstairs.control == "not_permitted"
    assert (
        run("NCD-HAIGHT", D(2023, 6, 1), planning_use="bar", story="first")["T1"].control == "not_permitted"
    )


# ---- the Bayview Note 7 exceptions -------------------------------------------------------------------------------------
def test_bayview_note_7_reaches_the_first_and_second_story_only() -> None:
    bar = {"planning_use": "bar", "licence_type": "48", "alcohol_transaction": "premises_transfer"}
    upstairs = run("NCD-BAYVIEW", D(2026, 9, 1), THIRD, **bar, story="third_or_above")["T1"]
    assert upstairs.control == "not_permitted"
    on = TODAY
    held = run("NCD-BAYVIEW", on, THIRD, **_existing("bar", on, "48"), changes_existing_business="enlarge",
               licence_type="48", alcohol_transaction="licence_already_held")["T3"]  # fmt: skip
    assert held.control == "conditional"
    assert tg.NOT_KNOWN["pre_existing_bar"] not in held.missing_inputs


# ---- North Beach: the prior-use rule's provisos --------------------------------------------------------------------------
def test_north_beach_same_use_proviso_and_the_enlargement_condition() -> None:
    on = D(2025, 6, 1)
    bar = {"planning_use": "bar", "story": "first"}
    same = run("NCD-NORTH BEACH", on, **bar, existing_use_stated="bar")
    for rule_id in ("T1", "T2"):
        assert same[rule_id].control == "not_decided", rule_id
        assert CHANGE in same[rule_id].missing_inputs
    other = run("NCD-NORTH BEACH", on, **bar, existing_use_stated="restaurant")
    assert other["T1"].control == other["T2"].control == "not_permitted"
    assert "T1.prior_use" in ids(other["T1"])
    merged = run("NCD-NORTH BEACH", on, planning_use="restaurant", story="first", existing_use_stated="bar",
                 merges_storefronts=True)  # fmt: skip
    assert merged["T2"].control == "not_permitted" and "T2:north_beach.prior_use.restaurant" in ids(
        merged["T2"]
    )
    # from 2025-12-15 the data does not show the proviso
    later = run("NCD-NORTH BEACH", D(2025, 12, 15), planning_use="restaurant", story="first",
                existing_use_stated="bar")["T2"]  # fmt: skip
    assert later.control == "conditional"


# ---- SoMa Youth and Family: the old list's words are not mapped -----------------------------------------------------------
def test_soma_other_entertainment_before_2023_06_03() -> None:
    club = {"planning_use": "nighttime_entertainment", "story": "first"}
    before = run("MUR", D(2023, 6, 2), SOMA, **club)["T2"]
    assert before.control == "not_decided"
    assert before.missing_inputs == [tg.NOT_KNOWN["soma_other_entertainment"]]
    assert run("MUR", D(2023, 6, 3), SOMA, **club)["T2"].control == "conditional"


# ---- the controls that existed only in a note ----------------------------------------------------------------------------
def test_umu_formula_retail_lot_exception() -> None:
    found = run("UMU", D(2024, 6, 1), planning_use="restaurant", formula_retail=True, story="first")["T5"]
    assert found.control == "not_decided"
    assert "Assessor's Parcel Block No. 3781, Lot 003" in found.missing_inputs[0]
    early = run("UMU", D(2023, 6, 1), planning_use="restaurant", formula_retail=True, story="first")["T5"]
    assert early.control == "conditional"


# ---- dating by the term that changed ----------------------------------------------------------------------------------------
def test_t3_and_the_operator_note_are_dated_by_their_own_term() -> None:
    on = D(2025, 1, 1)
    polk = run("NCD-POLK", on, planning_use="bar", story="first", at=site(on, existing_use="bar"))["T3"]
    assert polk.control == "not_decided" and polk.in_force_from is None
    haight = run("NCD-HAIGHT", D(2024, 1, 13), planning_use="bar", story="first", existing_use_stated="bar",
                 changes_existing_business="enlarge")["T3"]  # fmt: skip
    assert "this text in force since before 2022-01-01)" in haight.lines[-1].text
    chain = run("NCD-POLK", D(2026, 3, 16), planning_use="bar", formula_retail=True, story="first")["T5"]
    operator = next(line for line in chain.lines if line.rule_id == "T5.operator")
    assert "in force from 2025-06-01 (Ord. 62-25" in operator.text
    run_source = controls.citywide_run(
        "formula_retail_definition", D(2026, 3, 16), "change_of_operator_limbs"
    )
    assert run_source is not None and run_source.in_force_to is None


# ---- T4: a Bar that does not say it serves alcohol ---------------------------------------------------------------------------
def test_t4_a_bar_is_never_read_as_serving_no_alcohol() -> None:
    bar = {"planning_use": "bar", "business_type": "bar", "existing_use_stated": "retail",
           "formula_retail": False, "floor_area_sqft": 1000, "story": "first"}  # fmt: skip
    third = run("NC-3", TODAY, THIRD, **bar)["T4"]
    assert third.control == "not_decided" and third.missing_inputs == [LICENCE]
    haight = run("NCD-HAIGHT", D(2023, 6, 1), HAIGHT, **bar)["T4"]
    assert haight.control == "not_decided" and LICENCE in haight.missing_inputs
    mission = run("NCT-VALENCIA", TODAY, MISSION, **bar)["T4"]
    assert "T4:mission.new_bar_licence_from_bar_in_district" in ids(mission)
    # a Restaurant that does not say it serves alcohol is still read as serving none
    dry = run("NC-3", TODAY, THIRD, **{**bar, "planning_use": "restaurant", "business_type": "restaurant"})[
        "T4"
    ]
    assert dry.control == "does_not_apply" and ids(dry) == ["T4.no_alcohol"]


# ---- T11: an existing business, and a morning close ----------------------------------------------------------------------------
def test_t11_existing_business_not_decided_unless_intensified() -> None:
    given = {"planning_use": "bar", "closing_hour": "03:00", "existing_use_stated": "bar", "story": "first"}
    for change in ("none", "enlarge"):
        found = run("NCD-POLK", D(2024, 6, 1), **given, changes_existing_business=change)["T11"]
        assert found.control == "not_decided", change
        assert found.missing_inputs == [tg.NOT_KNOWN["existing_hours"]]
    longer = run("NCD-POLK", D(2024, 6, 1), **given, changes_existing_business="intensify")["T11"]
    assert longer.control == "conditional" and "T11.existing" in ids(longer)
    shown = run("NCD-POLK", D(2024, 6, 1), planning_use="bar", closing_hour="03:00",
                at=site(D(2024, 6, 1), existing_use="bar"))["T11"]  # fmt: skip
    assert shown.missing_inputs == [tg.NOT_KNOWN["existing_hours"], CHANGE]


@pytest.mark.parametrize(
    ("closing", "flags", "bucket", "overnight"),
    [
        ("06:00", {}, "after_2am", False),
        ("06:01", {}, "by_midnight", None),
        ("07:00", {}, "by_midnight", None),
        ("11:59", {}, "by_midnight", None),
        ("12:00", {}, "by_midnight", False),
        ("06:01", {"closes_after_2am": True}, "after_2am", True),
        ("07:00", {"closes_after_2am": True}, "after_2am", True),
        ("11:59", {"closes_after_midnight": True}, "after_2am", True),
    ],
)
def test_a_morning_close(closing: str, flags: dict[str, bool], bucket: str, overnight: bool | None) -> None:
    profile = BusinessProfile(business_type="bar", serves_alcohol=True, closing_hour=closing, **flags)
    read = concept_facts(profile).closing
    assert (read.bucket, read.overnight) == (bucket, overnight)


def test_t11_a_morning_close() -> None:
    def t11(district: str, closing: str, **flags: bool) -> Any:
        concept = concept_facts(
            BusinessProfile(business_type="bar", serves_alcohol=True, closing_hour=closing, **flags)
        )
        return {
            f.rule_id: f
            for f in tg.evaluate(concept, site(TODAY), zoning(district), [], rules_date=TODAY, today=TODAY)
        }["T11"]

    overnight = t11("NCD-NORTH BEACH", "07:00", closes_after_2am=True)
    assert overnight.control == "not_permitted" and "T11.overnight" in ids(overnight)
    unknown = t11("NCD-NORTH BEACH", "07:00")
    assert unknown.control == "not_decided" and unknown.missing_inputs == [tg.NOT_KNOWN["overnight"]]
    # a district with no hours control: a morning close decides nothing
    assert t11("C-2", "07:00").control == "does_not_apply"
    assert t11("NCD-NORTH BEACH", "06:00").control == "not_permitted"


# ---- T6, T8, T9 ---------------------------------------------------------------------------------------------------------------
def test_t6_amplified_sound_with_no_kind_stated() -> None:
    loud = run("NCD-PACIFIC", TODAY, planning_use="restaurant", amplified_sound=True, story="first")["T6"]
    assert loud.control == "not_decided" and loud.missing_inputs == [MISSING_PHRASES["entertainment_kind"]]
    easy = run("NCD-POLK", TODAY, planning_use="restaurant", amplified_sound=True, story="first")["T6"]
    assert easy.control == "principal" and "whatever the kind" in text_of(easy)


def test_t8_the_last_day_is_doubtful() -> None:
    given = {"planning_use": "restaurant", "existing_use_stated": "laundromat"}
    last = run("NC-2", D(2024, 12, 20), **given)["T8"]
    assert last.control == "conditional" and "T8.last_day" in ids(last)
    assert "whether 2024-12-20 or 2024-12-19 was the last day" in text_of(last)
    assert "T8.last_day" not in ids(run("NC-2", D(2024, 12, 19), **given)["T8"])
    assert run("NC-2", D(2024, 12, 21), **given)["T8"].control == "does_not_apply"


def test_t9_the_202_2_a_7_route_from_the_citywide_entry() -> None:
    rear = {"planning_use": "restaurant", "outdoor_area": "rear_or_side"}
    for district in ("NCT-MISSION", "NCT-24TH-MISSION"):
        found = run(district, TODAY, **rear)["T9"]
        assert found.control == "not_decided", district
        assert "T9.citywide_route" in ids(found)
    own = run("NC-1", TODAY, **rear)["T9"]
    assert own.control == "not_decided" and "T9.citywide_route" not in ids(own)
    assert run("NCT-MISSION", TODAY, planning_use="bar", outdoor_area="rear_or_side")["T9"].control == (
        "conditional"
    )


def test_t9_an_existing_outdoor_area_of_a_business_that_does_not_change() -> None:
    bar = {"planning_use": "bar", "existing_use_stated": "bar", "outdoor_area": "rear_or_side"}
    same = run("NCT-MISSION", TODAY, MISSION, **bar, changes_existing_business="none")["T9"]
    assert same.control == "not_decided"
    assert same.missing_inputs == [tg.NOT_KNOWN["existing_outdoor_area"]]
    assert "T9.existing" in ids(same)
    grows = run("NCT-MISSION", TODAY, MISSION, **bar, changes_existing_business="enlarge")["T9"]
    assert grows.control == "conditional"
