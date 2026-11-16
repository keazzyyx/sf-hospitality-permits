"""Real addresses and concepts, each with the pathway the Planning Code gives (tests/fixtures/pathway_cases.json).

For every case the zoning and overlay rows are built from the rule table the product uses: the static rules file
shipped with the records package, turned into rows by the same source modules that fill the store
(`datasf_zoning.overlay_for`, `datasf_sud.overlay_for`, the static rule rows), and looked up through the
file-backed store's `zoning_at` and `overlays_at`. No control is typed into this file or read from the fixture.
The fixture holds the address, the concept, which districts the store returned at the point, the licences near
it, and the expected answers with the code text they rest on. The controls themselves come from the dated
control data (rule table v2), read for RULES_DATE, the day the code text in the fixture was read.

No database, no network, no model.

Every case is run twice:
* as written: the fixture's profile holds what the first rule table could carry. Rule table v2 needs more (how
  the licence is to be obtained, whether the business is part of a chain, the floor area, the closing hour).
  A row that needs an input the profile does not give must read insufficient_information and name the input:
  `expected` and `expected_missing_inputs`;
* stated in full: the same profile with those inputs supplied by `stated_in_full` below (the closing hour is
  the one the concept text gives). The rules must then give the Planning Code's answer: `code_answer`.

Four kinds of case:
* undisputed: both runs must give the fixture's answers;
* rules gap: the rules cannot return the Code's answer (the fixture says why). The comparison with the Code is
  an expected failure, and a second test pins what the rules return today;
* depends on a fact: the Code's answer turns on a fact not on file (the fixture names it). The best case the
  rules return is pinned; the case is not counted as undisputed;
* disputed: the readings could not be settled. Skipped, with the reason, so the run lists it; what the rules
  return is pinned (further review, "Code and Planning practice differ") without calling either reading right.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import datetime as dt
import json
import os
import random
from pathlib import Path
from typing import Any

import pytest
from precedent.models import Application, Overlay
from precedent.sources import datasf_sud, datasf_zoning
from precedent.store.base import Nearby, ZoningInfo
from precedent.store.local import LocalStore

from app.agents.memo_runner import required_areas
from app.memo import controls, tracts, triggers
from app.memo.evidence import FactOrigins, fact_list, row_facts
from app.memo.facts import MISSING_PHRASES, site_facts
from app.memo.pathway import NO_PATH, PROHIBITED_USE_TRIGGERS, determine
from app.memo.report import Site, SiteRecord, site_of, site_records
from app.memo.rows import EXISTING_GROUP_PHRASE
from app.memo.tracts import PCN_STATUS_NOTE
from app.models.memo import Determinations
from app.models.profile import BusinessProfile

FIXTURE = Path(__file__).parent / "fixtures" / "pathway_cases.json"
DOC: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
CASES: list[dict[str, Any]] = DOC["cases"]
FETCHED = dt.datetime(2026, 11, 10, tzinfo=dt.UTC)
# The day the code text in the fixture was read: the rules are read for this date, and it is "today".
RULES_DATE = dt.date(2026, 11, 10)
# DataSF's name for each special use district, by the slug the store id carries ("datasf_sud:<slug>")
SUD_NAMES = {
    datasf_sud.slug(name): name
    for name in (*datasf_sud.SUD_SECTIONS, *datasf_zoning.rules_doc().get("sud_name_aliases", {}))
}
RULE_FIELDS = ("kind", "name", "code_section", "bar_permission", "restaurant_permission")


def _ids(cases: list[dict[str, Any]]) -> list[str]:
    return [c["id"] for c in cases]


UNDISPUTED = [c for c in CASES if not c["disputed"] and not c["rules_gap"] and not c.get("depends_on_fact")]
GAPS = [c for c in CASES if c["rules_gap"]]
DISPUTED = [c for c in CASES if c["disputed"]]
DEPENDS = [c for c in CASES if c.get("depends_on_fact")]


# ---- the rows, from the rule table ---------------------------------------------------------------------
def _square(lat: float, lng: float, half: float = 0.0004) -> dict[str, Any]:
    ring = [
        [lng - half, lat - half],
        [lng + half, lat - half],
        [lng + half, lat + half],
        [lng - half, lat + half],
        [lng - half, lat - half],
    ]
    return {"type": "MultiPolygon", "coordinates": [[ring]]}


def rule_table_rows(case: dict[str, Any]) -> list[Overlay]:
    """Every row the product would hold for this point: all the static rule rows (they attach by district code),
    and the zoning district and special use districts the store returned here, built by the source modules from
    the rules file and drawn as a small square round the point."""
    rows = [Overlay.model_validate(o) for o in datasf_zoning.rules_doc()["overlays"]]
    geom = _square(case["lat"], case["lng"])
    for recorded in case["store"]["overlays"]:
        source, key = recorded["id"].split(":", 1)
        if source == "datasf_zoning":
            row = datasf_zoning.overlay_for(key, [], FETCHED)
            assert row is not None
        elif source == "datasf_sud":
            row = datasf_sud.overlay_for(SUD_NAMES[key], [], FETCHED)
        else:
            continue  # a static rule row: already loaded, attaches through the district code
        rows.append(row.model_copy(update={"geom": geom}))
    return rows


def store_lookup(case: dict[str, Any], data_dir: Path) -> tuple[ZoningInfo | None, list[Overlay]]:
    """`zoning_at` and `overlays_at` of the file-backed store, loaded with the rule-table rows."""

    async def run() -> tuple[ZoningInfo | None, list[Overlay]]:
        store = LocalStore(data_dir)
        await store.upsert_overlays(rule_table_rows(case))
        return await store.zoning_at(case["lat"], case["lng"]), await store.overlays_at(
            case["lat"], case["lng"]
        )

    return asyncio.run(run())


def profile_of(case: dict[str, Any]) -> BusinessProfile:
    return BusinessProfile.model_validate(case["profile"])


def site_of_case(case: dict[str, Any]) -> Site:
    return site_of(case["address"], None, case["parcel"])


def licence_rows(case: dict[str, Any]) -> list[Nearby[Application]]:
    """The ABC licences on file at and near the address, as the store would return them."""
    rows = []
    for lic in case["licences"]:
        source_id = lic["record_id"].split(":", 1)[1]
        app = Application(
            id=lic["record_id"],
            source="abc",
            source_id=source_id,
            source_url=f"https://example.org/abc/{source_id}",
            fetched_at=FETCHED,
            kind="abc_license",
            permit_type=lic["permit_type"],
            license_type=lic["license_type"],
            status=lic["status"],
            address=lic["address"],
            parcel=lic["parcel"],
            lat=lic["lat"],
            lng=lic["lng"],
        )
        rows.append(Nearby(app, float(lic["distance_m"])))
    return rows


# ---- the inputs the fixture's profiles do not carry ---------------------------------------------------------
# The closing hour each concept text gives ("closes 11pm", "open until 1am", "closes at midnight"). The first
# rule table's profile had no field for it; the fixture's profiles are left as recorded and the hour is read
# from the concept text here. The 24-hour diner has none.
CLOSING_IN_CONCEPT_TEXT: dict[str, str] = {
    "valencia-wine-bar": "01:00",
    "valencia-restaurant-same-space": "22:00",
    "mission-st-restaurant": "23:00",
    "calle24-restaurant": "00:00",
    "mission-east-restaurant": "22:00",
    "castro-bar": "02:00",
    "pacific-bar": "22:00",
    "pacific-restaurant-11pm": "23:00",
    "haight-restaurant-alcohol": "22:00",
    "north-beach-restaurant": "23:00",
    "polk-bar": "00:00",
    "nc3-bar": "02:00",
    "nc1-late-bar": "01:00",
    "c3-bar": "02:00",
    "nct3-restaurant": "00:00",
    "rh2-restaurant": "21:00",
    "third-street-bar": "00:00",
    "third-street-wine-bar": "00:00",
    "cafe-no-alcohol": "18:00",
    "existing-bar-same-use": "02:00",
}
# "Occasional live music" at the wine bar, read as a Limited Live Performance (not Nighttime Entertainment).
ENTERTAINMENT_KIND: dict[str, str] = {"valencia-wine-bar": "limited_live_performance"}
# The cases where the same use already holds a licence at the address and the concept takes that business over.
TAKES_OVER_THE_EXISTING_BUSINESS = frozenset(
    {"valencia-restaurant-same-space", "nc1-late-bar", "nc2-all-night-restaurant", "existing-bar-same-use"}
)


def stated_in_full(case: dict[str, Any]) -> dict[str, Any]:
    """The fixture's profile with every input rule table v2 reads and the concept text leaves out, the way the
    readers of the Code took the concept: an independent business (not a chain) of 1,000 square feet on the
    first story (the readers read the tables' first-story column; the rules never assume a story, so it is
    stated here); a new business applies for a new licence; a business that takes over the one at the address
    takes its licence by a person-to-person transfer and does not enlarge or intensify it. What the space was
    last used as is left out, as in the Code's answers (the building row stays "not established" there)."""
    profile = {**case["profile"], "formula_retail": False, "square_feet": 1000, "stories": ["first"]}
    if case["id"] in CLOSING_IN_CONCEPT_TEXT:
        profile["closing_hour"] = CLOSING_IN_CONCEPT_TEXT[case["id"]]
    if case["id"] in ENTERTAINMENT_KIND:
        profile["entertainment_kind"] = ENTERTAINMENT_KIND[case["id"]]
    takes_over = case["id"] in TAKES_OVER_THE_EXISTING_BUSINESS
    if takes_over:
        profile["changes_existing_business"] = "none"
    if profile.get("serves_alcohol"):
        profile["alcohol_transaction"] = "person_to_person_transfer" if takes_over else "new_licence"
    return profile


def run_case(
    case: dict[str, Any],
    data_dir: Path,
    *,
    in_full: bool = False,
    rules_date: dt.date = RULES_DATE,
    today: dt.date = RULES_DATE,
) -> Determinations:
    zoning, overlays = store_lookup(case, data_dir)
    site = site_of_case(case)
    profile = BusinessProfile.model_validate(stated_in_full(case)) if in_full else profile_of(case)
    return determine(
        profile,
        zoning,
        overlays,
        site_records(licence_rows(case), site),
        site,
        required_areas(profile),
        today=today,
        rules_date=rules_date,
        tract=tracts.tract_at(case["lat"], case["lng"]),
    )


def answer(d: Determinations) -> dict[str, Any]:
    """What the rules returned, in the fixture's shape."""
    return {
        "use": d.pathway.use,
        "permission": d.pathway.permission,
        "existing_use": d.pathway.existing_use or "none_shown",
        "change_of_use": d.pathway.change_of_use,
        "statuses": {r.area: r.status for r in d.rows},
    }


def missing(d: Determinations) -> dict[str, list[str]]:
    """The inputs each row names as missing, in the fixture's shape; rows that name none are left out."""
    return {r.area: r.missing_inputs for r in d.rows if r.missing_inputs}


# ---- the fixture itself ----------------------------------------------------------------------------------
ANSWER_KEYS = {"use", "permission", "existing_use", "change_of_use", "statuses"}
# Every fixed phrase a row may name as missing: the inputs of the description, and what the rules cannot place.
KNOWN_PHRASES = {*MISSING_PHRASES.values(), *triggers.NOT_KNOWN.values(), EXISTING_GROUP_PHRASE}


def test_fixture_has_995_valencia_and_enough_undisputed_cases_across_districts() -> None:
    assert len(_ids(CASES)) == len(set(_ids(CASES)))
    assert any(c["address"].startswith("995 Valencia St") for c in UNDISPUTED)
    assert len(UNDISPUTED) >= 11
    assert len({c["store"]["district"] for c in UNDISPUTED}) >= 10
    assert {c["code_answer"]["permission"] for c in UNDISPUTED} == {
        "principal",
        "conditional",
        "not_permitted",
    }
    assert {c["code_answer"]["change_of_use"] for c in UNDISPUTED} == {"yes", "no", "not_established"}
    # as written, a control the rules cannot decide without an input reads "not_covered", never permitted
    assert "not_covered" in {c["expected"]["permission"] for c in UNDISPUTED}
    assert set(CLOSING_IN_CONCEPT_TEXT) | {"nc2-all-night-restaurant", "rincon-hill-restaurant"} == set(
        _ids(CASES)
    )


@pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
def test_every_case_cites_the_code_text_it_rests_on(case: dict[str, Any]) -> None:
    quoted = [s for s in case["source"] if s["quote"].strip() and s["url_read"].startswith("https://")]
    assert quoted, "a case needs at least one quoted passage"
    for s in case["source"]:
        assert s["section"].strip() and s["date_read"] == "2026-11-10"
    assert case["conditions_the_rules_cannot_evaluate"]
    if case["disputed"]:
        assert case["expected"] is None and case["code_answer"] is None
        assert len(case["dispute"]["readings"]) == 2
        assert case["dispute"]["readings"][0]["permission"] != case["dispute"]["readings"][1]["permission"]
        for reading in case["dispute"]["readings"]:
            assert all(s["quote"].strip() for s in reading["rests_on"])
        return
    areas = set(required_areas(profile_of(case)))
    for name in ("expected", "code_answer"):
        assert set(case[name]) == ANSWER_KEYS, name
        assert set(case[name]["statuses"]) == areas, "one expected status per approval the concept needs"
    # as written: every row that is insufficient names what is missing, in the rules' own fixed phrases, and
    # the fixture says why the expectation is what it is
    named = case["expected_missing_inputs"]
    insufficient = {a for a, s in case["expected"]["statuses"].items() if s == "insufficient_information"}
    assert set(named) == insufficient
    for phrases in named.values():
        assert phrases and all(
            p in KNOWN_PHRASES or p.startswith("whether the address is in") for p in phrases
        )
    assert case["expected_note"].strip()
    # the Code's answer never rests on a missing input of the zoning or alcohol row
    code = case["code_answer"]["statuses"]
    assert code["zoning_use"] != "insufficient_information"
    assert code.get("alcohol") != "insufficient_information"


@pytest.mark.parametrize("change", DOC["table_corrections"], ids=lambda c: f"{c['where']}:{c['field']}")
def test_every_table_correction_is_in_the_rules_file_and_quoted(change: dict[str, Any]) -> None:
    doc = datasf_zoning.rules_doc()
    assert change["rests_on"] and all(s["quote"].strip() and s["url_read"] for s in change["rests_on"])
    where, field = change["where"], change["field"]
    if where.startswith("zoning_controls["):
        code = where.removeprefix("zoning_controls['").removesuffix("']")
        assert doc["zoning_controls"][code][field] == change["new"]
    elif where == "sud_name_aliases":
        assert doc["sud_name_aliases"][field] == change["new"]
    elif where == "overlays":
        assert any(o["id"] == change["new"] for o in doc["overlays"])
    else:
        assert next(o for o in doc["overlays"] if o["id"] == where)[field] == change["new"]


# ---- the rule table gives the rows the store returned ------------------------------------------------------
@pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
def test_rule_table_rows_are_the_rows_the_store_returned(case: dict[str, Any], tmp_path: Path) -> None:
    """The same overlay ids attach at the point, and each carries the fields the store held when the case was
    recorded. Where the rule table was corrected after that, the fixture says so (`rule_table_now`)."""
    zoning, overlays = store_lookup(case, tmp_path)
    recorded = {o["id"]: o for o in case["store"]["overlays"]}
    assert zoning is not None and zoning.district == case["store"]["district"]
    assert sorted(o.id for o in overlays) == sorted(recorded)
    for row in overlays:
        want = {**recorded[row.id], **recorded[row.id].get("rule_table_now", {})}
        for name in RULE_FIELDS:
            assert getattr(row, name) == want[name], f"{row.id}.{name}"
    # the district's control is read the way the store reads it: the attached rule row first, else the district row
    source = next((o for o in overlays if o.kind == "nc_rule"), None) or next(
        o for o in overlays if o.kind == "zoning_district"
    )
    assert (zoning.bar_permission, zoning.restaurant_permission) == (
        source.bar_permission,
        source.restaurant_permission,
    )
    # every district of the fixture is one the dated control data carries
    assert controls.covers(zoning.district)


# ---- the pathway and the statuses ------------------------------------------------------------------------
@pytest.mark.parametrize("case", UNDISPUTED, ids=_ids(UNDISPUTED))
def test_as_written_a_row_that_lacks_an_input_says_so_and_names_it(
    case: dict[str, Any], tmp_path: Path
) -> None:
    """The profile as the fixture holds it. A row whose input is missing is insufficient_information and names
    the input; it is never filled with an assumption."""
    d = run_case(case, tmp_path)
    assert answer(d) == case["expected"]
    assert missing(d) == case["expected_missing_inputs"]


@pytest.mark.parametrize("case", UNDISPUTED, ids=_ids(UNDISPUTED))
def test_stated_in_full_the_rules_give_the_planning_code_answer(case: dict[str, Any], tmp_path: Path) -> None:
    d = run_case(case, tmp_path, in_full=True)
    assert answer(d) == case["code_answer"]
    rows = {r.area: r for r in d.rows}
    assert not rows["zoning_use"].missing_inputs
    assert "alcohol" not in rows or not rows["alcohol"].missing_inputs


def test_the_three_gaps_rule_table_v2_closed_are_counted_now() -> None:
    """A beer-and-wine bar in the Bayview NCD (the control turns on the licence type), an 11 p.m. close where
    principal hours end at 10 p.m. (the closing hour), and a cafe without alcohol (the Limited Restaurant row)
    were known gaps of the first rule table. Their expected-failure marks are gone: stated in full, each gives
    the Code's answer in the test above."""
    closed = {"third-street-wine-bar", "pacific-restaurant-11pm", "cafe-no-alcohol"}
    assert closed <= set(_ids(UNDISPUTED))
    for case in (c for c in CASES if c["id"] in closed):
        assert case["rules_gap"] is None and case["rules_gap_closed"]["was"]["why"].strip()
        assert case["rules_gap_closed"]["closed_by"].strip()
    by_id = {c["id"]: c for c in CASES}
    assert by_id["third-street-wine-bar"]["code_answer"]["permission"] == "conditional"
    assert by_id["pacific-restaurant-11pm"]["code_answer"]["statuses"]["zoning_use"] == "further_review"
    assert by_id["cafe-no-alcohol"]["code_answer"]["permission"] == "principal"


@pytest.mark.parametrize("case", GAPS, ids=_ids(GAPS))
@pytest.mark.xfail(strict=True, reason="known gap: the rules cannot return the Planning Code's answer here")
def test_known_gap_rules_do_not_yet_give_the_planning_code_answer(
    case: dict[str, Any], tmp_path: Path
) -> None:
    """Strict: when the rules start giving the Code's answer this fails, and the case moves to the undisputed list
    (set its `rules_gap` to null)."""
    assert answer(run_case(case, tmp_path, in_full=True)) == case["code_answer"]


# Gaps where the rules' answer as written is not the right answer as written either. (Review: as written, the
# late bar's zoning row is insufficient information, the right answer as written; its gap is stated in full only.
# Since the decision of 2026-11-12 the same holds for the diner and the restaurant west of the Mission Street NCT:
# neither gives a story, so as written the zoning row is insufficient information naming it.)
GAPS_AS_WRITTEN = [c for c in GAPS if c["rules_gap"]["rules_return"] != c["expected"]]


def test_a_gap_whose_statuses_as_written_are_right_still_names_the_input_the_rules_cannot_read() -> None:
    # As written none of these three gives a story, and no story is assumed (decision of 2026-11-12): the zoning
    # row is insufficient information naming it, the right answer as written. The late bar and the all-night
    # diner also name the hours the rules cannot read; the restaurant west of the Mission Street NCT is a gap
    # stated in full only.
    hours = triggers.NOT_KNOWN["existing_hours"]
    for case in (c for c in GAPS if c not in GAPS_AS_WRITTEN):
        named = case["rules_gap"]["rules_return_missing_inputs"]["zoning_use"]
        assert MISSING_PHRASES["stories"] in case["expected_missing_inputs"]["zoning_use"]
        assert hours not in case["expected_missing_inputs"]["zoning_use"]
        assert (hours in named) is (case["id"] != "valencia-restaurant-same-space")
    assert [c["id"] for c in GAPS if c not in GAPS_AS_WRITTEN] == [
        "valencia-restaurant-same-space",
        "nc1-late-bar",
        "nc2-all-night-restaurant",
    ]


@pytest.mark.parametrize("case", GAPS_AS_WRITTEN, ids=_ids(GAPS_AS_WRITTEN))
@pytest.mark.xfail(
    strict=True, reason="known gap: the rules cannot return the right answer as written either"
)
def test_known_gap_as_written(case: dict[str, Any], tmp_path: Path) -> None:
    assert answer(run_case(case, tmp_path)) == case["expected"]


@pytest.mark.parametrize("case", GAPS, ids=_ids(GAPS))
def test_known_gap_answer_is_the_one_on_record(case: dict[str, Any], tmp_path: Path) -> None:
    gap = case["rules_gap"]
    assert gap["why"].strip() and gap["needs"].strip()
    d = run_case(case, tmp_path)
    assert answer(d) == gap["rules_return"]
    assert missing(d) == gap["rules_return_missing_inputs"]
    assert answer(run_case(case, tmp_path, in_full=True)) == gap["rules_return_stated_in_full"]


def test_the_gaps_that_remain() -> None:
    # (review: the 24-hour diner and the RH-2 restaurant joined the two earlier gaps)
    assert sorted(_ids(GAPS)) == [
        "nc1-late-bar",
        "nc2-all-night-restaurant",
        "rh2-restaurant",
        "valencia-restaurant-same-space",
    ]
    by_id = {c["id"]: c for c in GAPS}
    # the bar whose late hours Planning has recorded as lawful: by the Code no Conditional Use; the rules do not
    # decide hours an existing business already keeps (spec 1a T11), so they name that
    late_bar = by_id["nc1-late-bar"]
    assert late_bar["code_answer"]["statuses"]["zoning_use"] == "allowed"
    assert late_bar["rules_gap"]["rules_return_stated_in_full"]["statuses"]["zoning_use"] == (
        "insufficient_information"
    )
    diner = by_id["nc2-all-night-restaurant"]["rules_gap"]
    assert diner["rules_return_stated_in_full"]["statuses"]["zoning_use"] == "insufficient_information"
    # the RH-2 restaurant on an interior lot: the rules cannot tell a corner lot (§ 231)
    rh2 = by_id["rh2-restaurant"]
    assert (
        rh2["code_answer"]["permission"],
        rh2["rules_gap"]["rules_return_stated_in_full"]["permission"],
    ) == (
        "not_permitted",
        "not_covered",
    )
    # the restaurant west of the Mission Street NCT: the rules cannot place the address, so the control for a
    # NEW restaurant reads "not covered" (the Code and Planning practice differ); every row is right
    west = by_id["valencia-restaurant-same-space"]
    full = west["rules_gap"]["rules_return_stated_in_full"]
    assert (west["code_answer"]["permission"], full["permission"]) == ("principal", "not_covered")
    assert full["statuses"] == west["code_answer"]["statuses"]


@pytest.mark.parametrize("case", DEPENDS, ids=_ids(DEPENDS))
def test_fact_dependent_case_returns_the_best_case_on_record(case: dict[str, Any], tmp_path: Path) -> None:
    """The Code's answer turns on a fact that is not on file. `code_answer` is the answer if the fact goes the
    applicant's way. Pinned here; not counted as the Planning Code's answer."""
    dep = case["depends_on_fact"]
    assert not case["disputed"] and not case["rules_gap"]
    assert case not in UNDISPUTED
    assert dep["fact"].strip() and dep["section"].strip()
    assert dep["otherwise"]["permission"] == "not_permitted" != case["code_answer"]["permission"]
    assert dep["otherwise"]["zoning_use"] == "not_permitted" != case["code_answer"]["statuses"]["zoning_use"]
    d = run_case(case, tmp_path)
    assert answer(d) == case["expected"]
    assert missing(d) == case["expected_missing_inputs"]
    assert d.pathway.notes, "the limit must at least print among the notes"
    full = run_case(case, tmp_path, in_full=True)
    if "rules_return_stated_in_full" in dep:
        # the rules name the fact rather than take the best case (review: the North Beach prior-use rule)
        assert answer(full) == dep["rules_return_stated_in_full"]
        named = [m for r in full.rows for m in r.missing_inputs]
        assert dep["rules_name"] in named
    else:
        assert answer(full) == case["code_answer"]


def test_the_three_fact_dependent_cases_are_not_counted_as_undisputed() -> None:
    assert sorted(_ids(DEPENDS)) == ["calle24-restaurant", "mission-st-restaurant", "north-beach-restaurant"]
    assert not {c["id"] for c in DEPENDS} & {c["id"] for c in UNDISPUTED}


@pytest.mark.parametrize("case", DISPUTED, ids=_ids(DISPUTED))
def test_disputed_case_reads_further_review_code_and_planning_practice_differ(
    case: dict[str, Any], tmp_path: Path
) -> None:
    """What the rules return where the Code text and Planning's own records disagree. Neither reading is called
    right: the row says they differ and sends the reader to Planning."""
    read = case["dispute"]["rules_read"]
    full = run_case(case, tmp_path, in_full=True)
    zoning_row = next(r for r in full.rows if r.area == "zoning_use")
    assert (zoning_row.status, zoning_row.status_note) == (
        "further_review",
        "Code and Planning practice differ",
    )
    assert (zoning_row.status, zoning_row.status_note) == (
        read["stated_in_full"]["zoning_use"],
        read["stated_in_full"]["status_note"],
    )
    assert zoning_row.missing_inputs == []
    assert zoning_row.approval.startswith("Conditional Use Authorization (Planning Code § 303), unless")
    assert zoning_row.basis[-1].text == (
        "The Planning Code text and San Francisco Planning's own records differ here (use control of a "
        "special use district). Ask San Francisco Planning which it applies: further review (Code and "
        "Planning practice differ)."
    )
    assert (full.pathway.permission, full.pathway.permission_label) == (
        "not_covered",
        "Code and Planning practice differ",
    )
    assert any(q.question.startswith("Is a Restaurant permitted at ") for q in full.open_questions)
    by_id = {f.rule_id: f for f in full.pathway.triggers}
    assert by_id["T2"].control == "code_and_practice_differ"
    assert "§ 249.60(f)(1)" in " ".join(line.code_section or "" for line in by_id["T2"].lines)
    # as written the profile lacks two inputs the zoning row needs. A missing input comes first (spec section
    # 4): the row is insufficient information and names them; the trigger still says the two sources differ.
    written = run_case(case, tmp_path)
    row = next(r for r in written.rows if r.area == "zoning_use")
    assert (row.status, row.status_note) == (read["as_written"]["zoning_use"], None)
    assert row.missing_inputs == read["as_written"]["missing_inputs"]
    assert {f.rule_id: f.control for f in written.pathway.triggers}["T2"] == "code_and_practice_differ"


@pytest.mark.parametrize("case", DISPUTED, ids=_ids(DISPUTED))
def test_disputed_case_is_listed_not_judged(case: dict[str, Any], tmp_path: Path) -> None:
    got = answer(run_case(case, tmp_path, in_full=True))  # it still runs: a crash here is a failure
    matches = [r["name"] for r in case["dispute"]["readings"] if {k: r[k] for k in got} == got]
    pytest.skip(
        f"disputed: {case['dispute']['why']} Stated in full, the rules return {got['permission']!r} for a new "
        f"use and {got['statuses']['zoning_use']!r} for the zoning row, which matches "
        f"{', '.join(matches) or 'neither reading'}."
    )


# ---- what must hold for every case, whatever the answer ---------------------------------------------------
BOTH_RUNS = [(c, full) for c in CASES for full in (False, True)]
BOTH_IDS = [f"{c['id']}-{'in_full' if full else 'as_written'}" for c, full in BOTH_RUNS]


@pytest.mark.parametrize(("case", "in_full"), BOTH_RUNS, ids=BOTH_IDS)
def test_building_row_reads_the_change_of_use_answer_the_pathway_holds(
    case: dict[str, Any], in_full: bool, tmp_path: Path
) -> None:
    d = run_case(case, tmp_path, in_full=in_full)
    p = d.pathway
    changes = p.changes
    assert changes is not None and p.change_of_use == changes.planning_use
    zoning_row = next(r for r in d.rows if r.area == "zoning_use")
    building = next(r for r in d.rows if r.area == "building_change_of_use")
    # one answer, read three times: the pathway's last line, the zoning row and the building row print the
    # same planning-use lines, word for word, with the same records behind them
    answer_line = changes.planning_use_lines[-1]
    assert p.lines[-1] == answer_line
    assert p.lines[-len(changes.planning_use_lines) :] == changes.planning_use_lines
    assert all(line in zoning_row.basis for line in changes.planning_use_lines)
    assert building.basis[: len(changes.planning_use_lines)] == changes.planning_use_lines
    # B0 (a new use the use controls prohibit, unless the use is shown to stay the same) and B0z (otherwise, a
    # prohibited use: formula retail): Planning Code § 175(a)
    b0 = building.basis[-1].code_section == "Planning Code § 175(a)"
    prohibited = any(
        f.rule_id in PROHIBITED_USE_TRIGGERS and f.control == "not_permitted" for f in p.triggers
    )
    assert b0 == prohibited
    if b0:
        assert building.status == "not_permitted" and not building.missing_inputs
        assert building.basis[-1].text.startswith("Zoning does not permit")
    elif "yes" in (changes.planning_use, changes.building_occupancy):
        assert building.status == "further_review"
    elif (changes.planning_use, changes.building_occupancy) == ("no", "no"):
        assert building.status == "allowed"
    else:
        assert building.status == "insufficient_information" and building.missing_inputs
    assert building.approval == (
        "Building permit with change of use" if p.change_of_use == "yes" else "Building permit"
    )


@pytest.mark.parametrize(("case", "in_full"), BOTH_RUNS, ids=BOTH_IDS)
def test_every_row_follows_from_the_triggers(case: dict[str, Any], in_full: bool, tmp_path: Path) -> None:
    """Spec section 4, on real districts: the zoning row is the triggers' own outcome, a missing input is named
    on the row and asked as a question, and the path lists no approval for a row the rules could not decide."""
    d = run_case(case, tmp_path, in_full=in_full)
    found = d.pathway.triggers
    assert [f.rule_id for f in found] == list(triggers.ORDER)
    assert d.pathway.rules_date == RULES_DATE.isoformat()
    rows = {r.area: r for r in d.rows}
    outcome = triggers.zoning_outcome(found)
    zoning_row = rows["zoning_use"]
    assert (zoning_row.status, zoning_row.status_note) == (outcome.status, outcome.status_note)
    assert zoning_row.missing_inputs == list(outcome.missing_inputs)
    for f in found:  # every trigger that applies is printed in the zoning row
        if f.control != "does_not_apply":
            assert all(line in zoning_row.basis for line in f.lines), f.rule_id
    use_barred = any(f.rule_id in ("T1", "T2") and f.control == "not_permitted" for f in found)
    assert (rows["health"].status == "not_permitted") == use_barred
    asked = " ".join(q.question for q in d.open_questions)
    for row in d.rows:
        assert bool(row.missing_inputs) == (row.status == "insufficient_information"), row.area
        if row.status == "not_permitted":
            assert row.referral_steps == []
        for phrase in row.missing_inputs:
            assert f"Not known: {phrase}." in asked
        if row.status == "insufficient_information":
            assert row.approval not in d.entitlement_path
    if "alcohol" in rows:
        alcohol = rows["alcohol"]
        assert alcohol.status_note in (None, PCN_STATUS_NOTE)
        if alcohol.status_note:
            assert alcohol.status == "further_review"
        if (
            not in_full and alcohol.status != "not_permitted"
        ):  # no fixture profile says how the licence is obtained
            assert alcohol.status == "insufficient_information"
            assert MISSING_PHRASES["alcohol_transaction"] in alcohol.missing_inputs


@pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
def test_same_facts_in_any_order_give_the_same_determinations(case: dict[str, Any], tmp_path: Path) -> None:
    zoning, overlays = store_lookup(case, tmp_path)
    site = site_of_case(case)
    records = site_records(licence_rows(case), site)
    tract = tracts.tract_at(case["lat"], case["lng"])
    dates = {"today": RULES_DATE, "rules_date": RULES_DATE, "tract": tract}
    for fields in (case["profile"], stated_in_full(case)):
        profile = BusinessProfile.model_validate(fields)
        areas = required_areas(profile)
        first = determine(profile, zoning, overlays, records, site, areas, **dates).model_dump_json()
        rng = random.Random(995)
        for _ in range(5):
            shuffled_overlays = rng.sample(overlays, len(overlays))
            shuffled_records = rng.sample(records, len(records))
            shuffled_areas = rng.sample(areas, len(areas))
            again = determine(
                profile.normalized(),
                zoning,
                shuffled_overlays,
                shuffled_records,
                site,
                shuffled_areas,
                **dates,
            )
            assert again.model_dump_json() == first
        # `rules_date` defaults to `today`
        assert determine(profile, zoning, overlays, records, site, areas, today=RULES_DATE, tract=tract) == (
            Determinations.model_validate_json(first)
        )


@pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
def test_only_a_licence_at_the_address_itself_shows_the_existing_use(
    case: dict[str, Any], tmp_path: Path
) -> None:
    """A licence next door, or under another address on the same parcel, is never read as this address."""
    d = run_case(case, tmp_path)
    elsewhere = {f"app:{lic['record_id']}" for lic in case["licences"] if not lic["at_address"]}
    cited = {c for row in d.rows for line in row.basis for c in line.citations}
    cited |= {c for line in (*d.pathway.lines, *d.pathway.notes) for c in line.citations}
    cited |= {c for f in d.pathway.triggers for line in f.lines for c in line.citations}
    assert not cited & elsewhere
    here = [lic for lic in case["licences"] if lic["at_address"]]
    if d.pathway.existing_use is not None:
        assert here and any(f"app:{lic['record_id']}" in cited for lic in here)
    # the site records the rules were given include the same-parcel licence: the address rule, not the read, kept it out
    site = site_of_case(case)
    matched: list[SiteRecord] = site_records(licence_rows(case), site)
    same_parcel = {lic["record_id"] for lic in case["licences"] if lic["parcel"] == case["parcel"]}
    assert same_parcel <= {r.app.id for r in matched}


def test_995_valencia_wine_bar_every_row(tmp_path: Path) -> None:
    """The lead's example, end to end from the rule table: "40-seat wine bar, small kitchen, open until 1am,
    occasional live music" at 995 Valencia St, as the description reads. It gives no story, and no story is
    assumed (the user's decision of 2026-11-12: "MISSING STORY: always 'Insufficient information', naming it.
    Never default to the first story."): the zoning row is insufficient information naming the story, although
    the Mission district's rule already asks for a Conditional Use."""
    case = next(c for c in CASES if c["id"] == "valencia-wine-bar")
    assert case["concept"] == "40-seat wine bar, small kitchen, open until 1am, occasional live music"
    d = run_case(case, tmp_path)
    p = d.pathway
    assert (p.use_label, p.permission_label, p.change_of_use_label) == (
        "Bar",
        "Not decided by the rules",
        "Change of use",
    )
    texts = [line.text for line in p.lines]
    assert texts[0] == "The concept is looked up as a Bar (Planning Code § 102)."
    assert (
        "Zoning district NCT-VALENCIA: the table sets a different control for a Bar on different stories. Which "
        "story the business is on is not given, so no story is assumed and this is not decided until it is "
        "(Planning Code § 762, in force since before 2022-01-01)." in texts
    )
    assert not any("first story" in text.lower() for text in texts)
    assert texts[-1] == "Restaurant to Bar is a change of use."
    assert (
        {f.rule_id: f.control for f in p.triggers}
        == {
            "T1": "not_decided",  # Table 762: a Bar is C on the first story, NP above; no story is given
            "T2": "conditional",  # § 249.60(b)(2)(C): a new Bar is always a Conditional Use in the Mission district
            "T3": "does_not_apply",  # the Restaurant on file does not continue: a Bar is proposed
            "T4": "principal",  # the licence rule is a requirement, not a control
            "T5": "not_decided",  # formula retail is conditional here and the description does not say
            "T6": "not_decided",  # "occasional live music": the kind is not given, nor the story
            "T7": "not_decided",  # no floor area; 3,001 square feet or more is conditional
            "T8": "does_not_apply",
            "T9": "does_not_apply",
            "T10": "does_not_apply",
            "T11": "principal",  # read at 1 a.m., inside P 6 a.m. to 2 a.m.
        }
    )
    rows = {r.area: r for r in d.rows}
    assert {a: (r.status, r.status_note) for a, r in rows.items()} == {
        "zoning_use": ("insufficient_information", None),
        "alcohol": ("insufficient_information", None),
        "entertainment": ("further_review", None),
        "health": ("allowed", None),
        "building_change_of_use": ("further_review", None),
    }
    # zoning: the story comes first among what is missing, and the Conditional Use already asked for is named
    zoning_row = rows["zoning_use"]
    assert zoning_row.approval == "Use authorization (not decided: an input is missing)"
    assert zoning_row.missing_inputs == [
        MISSING_PHRASES["stories"],
        MISSING_PHRASES["formula_retail"],
        MISSING_PHRASES["entertainment_kind"],
        MISSING_PHRASES["floor_area_sqft"],
    ]
    assert zoning_row.basis[-1].text == (
        "The rules could not decide: use control of the zoning district, formula retail, nighttime "
        "entertainment and use size. What is missing: " + "; ".join(zoning_row.missing_inputs) + ". No story "
        "is assumed, so until that is known the rules cannot say what zoning asks of the concept, although use "
        "control of a special use district already asks for a Conditional Use Authorization: insufficient "
        "information."
    )
    # alcohol: the description does not say how the licence is to be obtained. The row names that input; the
    # Mission transfer requirement and the tract's over-concentration are still printed
    alcohol = rows["alcohol"]
    assert alcohol.approval == "ABC licence, Type 42 (on-sale beer and wine, public premises)"
    assert alcohol.missing_inputs == [
        "how the liquor licence will be obtained (new, or a transfer from another owner or another location)"
    ]
    ids = [line.rule_id for line in alcohol.basis]
    assert ids == [
        "alcohol.licence",
        "T4:mission.new_bar_licence_from_bar_in_district",
        "alcohol.tract_concentration",
        "alcohol.tract_concentration",
        "alcohol.status",
    ]
    assert "must use a liquor licence transferred from another Bar located inside the district" in (
        alcohol.basis[1].text
    )
    assert alcohol.basis[2].text.startswith("Census tract 208.01: 28 active on-sale retail licences")
    assert "against 12 authorised" in alcohol.basis[2].text
    assert alcohol.basis[3].text.startswith("The tract is over its authorised number. State law tests a new")
    assert [s.rule_id for s in alcohol.referral_steps] == ["referral.step", "referral.step"]
    # entertainment: the general permit list, with the referral steps on the rules date
    entertainment = rows["entertainment"]
    assert entertainment.approval.startswith(
        "Place of Entertainment, Limited Live Performance or Fixed Place"
    )
    steps = " ".join(s.text for s in entertainment.referral_steps)
    assert (
        "until 16 August 2025 this application was also sent to the Department of Building Inspection"
        in steps
    )
    assert "That step has ended. The permit is still required." in steps
    # health and building
    assert rows["health"].basis[-1].rule_id == "health.status" and rows["health"].referral_steps
    building = rows["building_change_of_use"]
    assert building.approval == "Building permit with change of use"
    assert (p.changes.planning_use, p.changes.building_occupancy, p.changes.neighbourhood_notice) == (  # type: ignore[union-attr]
        "yes",
        "not_established",
        "not_required",
    )
    assert d.overall_status == "further_review"
    # first (rule 9): the Mission district's rule asks for a Conditional Use whatever the story; the district's
    # table would ask for one on the first story or in the basement and bar the use above it; formula retail would
    # ask for one if the business is a chain of eleven or more; and the use size control would if the floor area is
    # at or over its threshold and, as the Type 41 on file makes the space an existing Restaurant, it grows or
    # storefronts are merged (Interpretation 121.2). The zoning row itself stays insufficient information, naming
    # the story
    assert d.overall_line == (
        "A Conditional Use Authorization is needed (use control of a special use district). A Conditional Use "
        "Authorization is needed if the business occupies no story other than the first story or the basement "
        "(use control of the zoning district). Zoning does not permit the concept if the business occupies the "
        "second story or the third story or above (use control of the zoning district). A Conditional Use "
        "Authorization is needed if the business is part of a chain with eleven or more other locations (formula "
        "retail). A Conditional Use Authorization is needed if the floor area is 3,001 square feet or more and "
        "either the floor area grows or storefronts are merged (use size). Of the 5 approvals this concept needs: "
        "2 further review (entertainment permit, building permit and change of use), 2 insufficient information "
        "(zoning and use, alcohol licence), 1 allowed (health permit)."
    )
    assert [(h.kind, h.trigger, h.status, h.definite) for h in d.headline_findings] == [
        ("conditional", "T2", "further_review", True),
        ("conditional_if", "T1", "insufficient_information", False),
        ("not_permitted_if", "T1", "insufficient_information", False),
        ("conditional_if", "T5", "insufficient_information", False),
        ("conditional_if", "T7", "insufficient_information", False),
    ]
    assert d.headline_findings[0].sentence.startswith(
        "Whatever the story, the concept needs a Conditional Use"
    )
    # the zoning and alcohol rows are not decided, so the path lists neither the Conditional Use nor a licence
    assert d.entitlement_path == (
        "Place of Entertainment, Limited Live Performance or Fixed Place Outdoor Amplified Sound permit; Health "
        "permit to operate; Building permit with change of use"
    )
    assert [q.question for q in d.open_questions] == [
        "Not known: which stories the business occupies. Needed for: zoning and use.",
        "Not known: whether the business is part of a chain that shares its name, look or menu with other "
        "locations. Needed for: zoning and use.",
        "Not known: whether there is entertainment, and what kind. Needed for: zoning and use.",
        "Not known: the floor area of the business, in square feet. Needed for: zoning and use.",
        "Not known: how the liquor licence will be obtained (new, or a transfer from another owner or another "
        "location). Needed for: alcohol licence.",
    ]
    # stated in full (a new licence): the Mission requirement decides the row, as in the Code's answer
    full = run_case(case, tmp_path, in_full=True)
    blocked = next(r for r in full.rows if r.area == "alcohol")
    assert (blocked.status, blocked.missing_inputs) == ("potential_blocker", [])
    assert full.overall_status == "potential_blocker"


def test_the_rules_date_decides_which_control_is_read(tmp_path: Path) -> None:
    """A restaurant with beer and wine, a new licence, in the Haight Street NCD. Until 13 January 2024 a new
    on-sale liquor establishment was not permitted there, except a Restaurant within the quota of Table 719
    Note (4), which the rules cannot count (review: not decided); from 14 January 2024 it is a conditional use."""
    case = next(c for c in CASES if c["id"] == "haight-restaurant-alcohol")
    before = run_case(case, tmp_path, in_full=True, rules_date=dt.date(2024, 1, 13))
    after = run_case(case, tmp_path, in_full=True, rules_date=dt.date(2024, 1, 14))
    today = run_case(case, tmp_path, in_full=True)

    def statuses(d: Determinations) -> dict[str, str]:
        return {r.area: r.status for r in d.rows}

    assert before.pathway.rules_date == "2024-01-13" and after.pathway.rules_date == "2024-01-14"
    quota = triggers.NOT_KNOWN["haight_restaurant_quota"]
    assert (statuses(before)["zoning_use"], statuses(before)["alcohol"]) == (
        "insufficient_information",
        "insufficient_information",
    )
    assert quota in next(r for r in before.rows if r.area == "zoning_use").missing_inputs
    assert (statuses(after)["zoning_use"], statuses(after)["alcohol"]) == ("further_review", "further_review")
    assert statuses(today) == statuses(after) == case["code_answer"]["statuses"]
    t4_before = next(f for f in before.pathway.triggers if f.rule_id == "T4")
    t4_after = next(f for f in after.pathway.triggers if f.rule_id == "T4")
    assert (t4_before.control, t4_before.differs_today) == ("not_decided", True)
    assert (t4_after.control, t4_after.differs_today) == ("conditional", False)
    assert any(line.rule_id == "T4.differs" and "2024-01-14" in line.text for line in t4_before.lines)
    # Table 719 itself changed on the same day: before it the Restaurant row was "NP(3)(4)", not permitted on the
    # ground level unless within the Note (4) quota (C), which the rules cannot count (corrected by the review:
    # this read not permitted, with the City permits following it)
    t1 = {
        d.pathway.rules_date: next(f for f in d.pathway.triggers if f.rule_id == "T1")
        for d in (before, after)
    }
    assert (t1["2024-01-13"].control, t1["2024-01-14"].control) == ("not_decided", "principal")
    assert t1["2024-01-13"].missing_inputs == [quota]
    assert (statuses(before)["health"], statuses(after)["health"]) == ("allowed", "allowed")
    assert before.entitlement_path != NO_PATH
    assert before.pathway.permission == "not_covered" and after.pathway.permission == "conditional"


# ---- every district in the rule table ---------------------------------------------------------------------
SWEEP_PROFILES: dict[str, dict[str, Any]] = {
    "wine bar, closes by midnight": {
        "business_type": "bar",
        "serves_alcohol": True,
        "alcohol_type": "beer_wine",
    },
    "cocktail bar, closes after midnight": {
        "business_type": "bar",
        "serves_alcohol": True,
        "alcohol_type": "full_liquor",
        "closes_after_midnight": True,
    },
    "restaurant with beer and wine, open past 2 a.m.": {
        "business_type": "restaurant",
        "serves_alcohol": True,
        "alcohol_type": "beer_wine",
        "closes_after_midnight": True,
        "closes_after_2am": True,
    },
    "restaurant, no alcohol": {"business_type": "restaurant"},
    "cafe, no alcohol": {"business_type": "cafe"},
}
ON_FILE = {"principal": "principal", "conditional": "conditional", "prohibited": "not_permitted"}


@pytest.mark.parametrize("code", sorted(datasf_zoning.zoning_controls()))
def test_every_district_in_the_rule_table_gives_a_consistent_answer(code: str, tmp_path: Path) -> None:
    """Each zoning code the product's rule table carries, with its own rows and no special use district: the
    rules run, each status follows from the triggers by the row rules, and a district the dated data does not
    carry is read from the product's table and never comes out Allowed on a control the rules did not read."""
    control = datasf_zoning.zoning_controls()[code]
    case = {"lat": 37.76, "lng": -122.42, "store": {"overlays": [{"id": f"datasf_zoning:{code}"}]}}
    zoning, overlays = store_lookup(case, tmp_path)
    assert zoning is not None and zoning.district == code
    site = site_of("1 Test St, San Francisco, CA 94110", None, None)
    carried = controls.covers(code)
    for label, fields in SWEEP_PROFILES.items():
        profile = BusinessProfile.model_validate(fields)
        d = determine(profile, zoning, overlays, [], site, required_areas(profile), today=RULES_DATE)
        p = d.pathway
        rows = {r.area: r for r in d.rows}
        found = {f.rule_id: f for f in p.triggers}
        assert set(rows) == set(required_areas(profile)), label
        outcome = triggers.zoning_outcome(p.triggers)
        assert (rows["zoning_use"].status, rows["zoning_use"].missing_inputs) == (
            outcome.status,
            list(outcome.missing_inputs),
        ), (code, label)
        assert (p.existing_use, p.change_of_use) == (None, "not_established")
        # Planning Code § 175(a) (the user's decision of 2026-11-12): a prohibited use (the use itself, formula
        # retail) makes every later City permit not permitted; other bars do not
        prohibited = any(found[t].control == "not_permitted" for t in PROHIBITED_USE_TRIGGERS)
        assert rows["building_change_of_use"].status == (
            "not_permitted" if prohibited else "insufficient_information"
        ), (code, label)
        # no special use district here, unless the district is one itself (North Beach, Haight Street): T2 and
        # T4 then have nothing to read
        if not triggers.special_district_keys(zoning, overlays):
            assert (found["T2"].control, found["T4"].control) == ("does_not_apply", "does_not_apply")
        barred = "not_permitted" in (found["T1"].control, found["T2"].control)
        assert not barred or prohibited
        assert rows["health"].status == ("not_permitted" if prohibited else "allowed"), (code, label)
        if "alcohol" in rows:  # no sweep profile says how the licence is to be obtained
            # (review: a zoning row that is not permitted for the concept as described bars the licence too)
            banned = outcome.status == "not_permitted" or found["T4"].control == "not_permitted"
            want = "not_permitted" if banned else "insufficient_information"
            assert rows["alcohol"].status == want, (code, label)
        if "entertainment" in rows:  # open past 2 a.m.: the Extended-Hours Premises permit
            assert profile.closes_after_2am
            night = found["T6"].control == "not_permitted"
            assert rows["entertainment"].status == (
                "not_permitted" if prohibited or night else "further_review"
            )
        if carried:
            continue
        # not in the dated data: Bar and Restaurant come from the product's table, and the row is never allowed
        # (the hours, at least, were not read)
        assert rows["zoning_use"].status != "allowed", (code, label)
        assert "the rule table does not carry this zoning district" in triggers.missing_inputs(p.triggers)
        if p.use == "limited_restaurant":
            assert (
                found["T1"].control == "not_decided"
            )  # the product's table has no Limited Restaurant control
            continue
        on_file = control["bar_permission"] if p.use == "bar" else control["restaurant_permission"]
        # the product's table gives first-story controls: with no story given it is not decided and names the
        # story (no story is assumed), unless the district's own table has no story columns (one control on every
        # story, as the dated data's notes record); with the first story stated it is read as it reads
        if code in triggers.NO_STORY_COLUMNS:
            assert found["T1"].control == ON_FILE.get(on_file, "not_decided"), (code, label)
            assert MISSING_PHRASES["stories"] not in found["T1"].missing_inputs, (code, label)
        else:
            assert found["T1"].control == "not_decided", (code, label)
            if on_file in ON_FILE:
                assert MISSING_PHRASES["stories"] in found["T1"].missing_inputs, (code, label)
        first = BusinessProfile.model_validate({**fields, "stories": ["first"]})
        stated = determine(first, zoning, overlays, [], site, required_areas(first), today=RULES_DATE)
        t1 = next(f for f in stated.pathway.triggers if f.rule_id == "T1")
        assert t1.control == ON_FILE.get(on_file, "not_decided"), (code, label)
        assert MISSING_PHRASES["stories"] not in t1.missing_inputs, (code, label)


def test_the_sweep_reads_both_kinds_of_district() -> None:
    codes = set(datasf_zoning.zoning_controls())
    assert {c for c in codes if controls.covers(c)} and {c for c in codes if not controls.covers(c)}


# ---- the web fixture: its rule-set parts are what the rules return, not hand-written -------------------
WEB_FIXTURE = (
    Path(__file__).resolve().parents[3] / "apps/web/src/lib/fixtures/determinations-995-valencia.json"
)
WEB_FIXTURE_DOC = (
    "Generated, do not edit by hand. What app.memo.pathway.determine returns for the case 'valencia-wine-bar' "
    "of apps/api/tests/fixtures/pathway_cases.json (a wine bar at 995 Valencia St), under the rules in force on "
    "2026-11-10: as the records are ('with_licence': an active Type 41 licence at the address) and with no "
    "licence on file ('no_licence'); and for the case 'pacific-bar' ('not_permitted': a bar where the "
    "district's table does not permit one, with the zoning record and the citations the rule lines cite). The "
    "concept is run as its description reads, so a row whose input the description does not give is "
    "'insufficient_information' and names the input. The web fixture, the landing sample and the Playwright "
    "suite take every rule-set field from here: the pathway with its triggers and change-of-use answers, each "
    "row's approval, agency, status, status note, rule lines, referral steps and missing inputs, the overall "
    "status and line, the entitlement path and the rules' open questions; and the facts the rules read, each with "
    "where it came from ('facts', and each row's known facts in 'row_facts'). Regenerate: cd apps/api && "
    "WRITE_WEB_FIXTURE=1 .venv/bin/pytest -q tests/test_pathway_cases.py -k web_fixture"
)
# The cases build each licence record with a placeholder link; the web fixture shows ABC's own lookup page.
_PLACEHOLDER_LICENCE_URL = "https://example.org/abc/"
_ABC_LICENCE_URL = "https://www.abc.ca.gov/licensing/license-lookup/single-license/?RPTTYPE=12&LICENSE="


def _zoning_and_overlay_citations(
    zoning: ZoningInfo | None, overlays: list[Overlay], cited: set[str]
) -> list[dict[str, Any]]:
    """The citation the report lists for the zoning record and for each overlay, written the way
    `MemoRunner._build_citations` writes them; only the ones in `cited`."""
    out: list[dict[str, Any]] = []
    if zoning is not None:
        out.append(
            {
                "id": f"zoning:{zoning.district}",
                "kind": "zoning",
                "label": f"Zoning {zoning.district} — {zoning.code_section}",
                "source_url": zoning.source_url,
                "excerpt": zoning.rules[:300],
            }
        )
    for o in sorted(overlays, key=lambda o: o.id):
        out.append(
            {
                "id": f"overlay:{o.id}",
                "kind": "overlay",
                "label": f"{o.name} — {o.code_section}",
                "source_url": o.source_url,
                "excerpt": o.rules[:300],
            }
        )
    return [c for c in out if c["id"] in cited]


# The words of the sample's description (WEB_SAMPLE_DESCRIPTION, the case's own "concept") that state each field,
# as the intake model quotes them (app.memo.stated). Only these are written by hand; the facts are built by code.
WEB_SAMPLE_QUOTES: dict[str, tuple[str, ...]] = {
    "business_type": ("wine bar",),
    "serves_alcohol": ("wine bar",),
    "alcohol_type": ("wine bar",),
    "seats": ("40-seat",),
    "closes_after_midnight": ("open until 1am",),
    "live_entertainment": ("occasional live music",),
}


def _evidence(
    case: dict[str, Any], rules: Determinations, quotes: dict[str, tuple[str, ...]] | None = None
) -> dict[str, Any]:
    """The facts the rules read for one sample, as the report shows them (app.memo.evidence): every fact with
    where it came from, and the known facts of each row."""
    profile = profile_of(case)
    site = site_of_case(case)
    on_site = site_facts(
        site_records(licence_rows(case), site), site, rules_date=RULES_DATE, today=RULES_DATE
    )
    origins = FactOrigins(quotes=WEB_SAMPLE_QUOTES if quotes is None else quotes)
    return {
        "facts": [f.model_dump(mode="json") for f in fact_list(profile, rules, origins)],
        "row_facts": {
            r.area: [f.model_dump(mode="json") for f in row_facts(r.area, profile, on_site, origins)]
            for r in rules.rows
        },
    }


def web_fixture(data_dir: Path) -> dict[str, Any]:
    """The rule-set parts of the web's sample memos, built by the rules themselves, and the facts the rules read
    with where each came from."""
    case = next(c for c in CASES if c["id"] == "valencia-wine-bar")
    no_licence = copy.deepcopy(case)
    no_licence["licences"] = []
    with_rules = run_case(case, data_dir / "with")
    without_rules = run_case(no_licence, data_dir / "without")
    built: dict[str, Any] = {
        "with_licence": {**with_rules.model_dump(mode="json"), **_evidence(case, with_rules)},
        "no_licence": {**without_rules.model_dump(mode="json"), **_evidence(no_licence, without_rules)},
    }
    # a second address, where the district's table does not permit the use: every City row follows the zoning
    # row and there is no approval path
    banned = next(c for c in CASES if c["id"] == "pacific-bar")
    zoning, overlays = store_lookup(banned, data_dir / "banned-rows")
    assert zoning is not None
    rules = run_case(banned, data_dir / "banned")
    lines = [
        *rules.pathway.lines,
        *rules.pathway.notes,
        *(line for f in rules.pathway.triggers for line in f.lines),
        *(line for r in rules.rows for line in (*r.basis, *r.referral_steps)),
    ]
    built["not_permitted"] = {
        "case": banned["id"],
        "address": banned["address"],
        "parcel": banned["parcel"],
        "lat": banned["lat"],
        "lng": banned["lng"],
        "concept": banned["concept"],
        "zoning": dataclasses.asdict(zoning),
        "citations": _zoning_and_overlay_citations(
            zoning, overlays, {c for line in lines for c in line.citations}
        ),
        "determinations": rules.model_dump(mode="json"),
        **_evidence(banned, rules, quotes={}),
    }
    text = json.dumps(built, ensure_ascii=False).replace(_PLACEHOLDER_LICENCE_URL, _ABC_LICENCE_URL)
    return {"_doc": WEB_FIXTURE_DOC, "case": case["id"], **json.loads(text)}


def test_the_web_fixture_carries_what_the_rules_return(tmp_path: Path) -> None:
    """The web's sample memo (preview route, landing card, Playwright) must show the strings the API sends, so
    its rule-set parts are a file this test writes and pins. A change to a rule sentence, an approval name or
    the overall line fails here until the file is regenerated (WRITE_WEB_FIXTURE=1)."""
    if not WEB_FIXTURE.parent.is_dir():
        pytest.skip("apps/web is not in this checkout")
    built = web_fixture(tmp_path)
    if os.environ.get("WRITE_WEB_FIXTURE") == "1":
        WEB_FIXTURE.write_text(json.dumps(built, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert WEB_FIXTURE.is_file(), "run once with WRITE_WEB_FIXTURE=1 to write the web fixture"
    assert json.loads(WEB_FIXTURE.read_text(encoding="utf-8")) == built
    with_licence, no_licence = built["with_licence"], built["no_licence"]
    assert (with_licence["pathway"]["existing_use"], with_licence["pathway"]["change_of_use"]) == (
        "restaurant",
        "yes",
    )
    assert (no_licence["pathway"]["existing_use"], no_licence["pathway"]["change_of_use"]) == (
        None,
        "not_established",
    )
    assert [r["area"] for r in with_licence["rows"]] == [r["area"] for r in no_licence["rows"]]
    for sample in (with_licence, no_licence):
        assert sample["pathway"]["rules_date"] == "2026-11-10"
        assert [t["rule_id"] for t in sample["pathway"]["triggers"]] == list(triggers.ORDER)
        alcohol = next(r for r in sample["rows"] if r["area"] == "alcohol")
        assert alcohol["status"] == "insufficient_information" and alcohol["missing_inputs"]
    banned = built["not_permitted"]["determinations"]
    assert banned["overall_status"] == "not_permitted"
    assert banned["entitlement_path"] == NO_PATH
    cited = {c for r in banned["rows"] for line in r["basis"] for c in line["citations"]}
    assert cited and cited <= {c["id"] for c in built["not_permitted"]["citations"]}
