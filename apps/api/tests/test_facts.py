"""app.memo.facts: the facts the pathway rules read, from the profile and from the records at the address.

All synthetic except two files read as data: backtest/inputs.json (the 40 hand-entered cases) and, when it is on
this machine, the reconciled control data the licence lists were taken from.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import random
from pathlib import Path
from typing import Any, get_args

import pytest
from precedent.models import Application

from app.agents import prompts
from app.memo import facts as fx
from app.memo.facts import (
    BAR_LICENCE_SOURCE,
    BAR_LICENCE_TYPES,
    BAR_ONLY_WITH_OTHER_USES,
    FACT_ALIASES,
    FACT_KEYS,
    FACTS_WITHOUT_A_PROFILE_FIELD,
    LICENCE_TYPES_EITHER_USE,
    MISSING_PHRASES,
    RESTAURANT_LICENCE_SOURCE,
    RESTAURANT_LICENCE_TYPES,
    USE_FOR_LICENCE,
    USE_ORDER,
    Closing,
    ConceptFacts,
    Fact,
    clock_minutes,
    closing_bucket_at,
    concept_facts,
    concept_facts_from_facts,
    fact_name,
    facts_not_carried,
    missing_phrase,
    normal_licence_type,
    profile_from_facts,
    site_facts,
    stated_planning_uses,
)
from app.memo.pathway import (
    LEGAL_BASIS,
    LICENCE_FOR_CONCEPT,
    LICENCE_TYPES,
    READ_AT,
    closing_bucket,
    existing_use,
    parse_hours,
    planning_use,
)
from app.memo.report import SiteMatch, SiteRecord, site_of
from app.models.memo import PlanningUse
from app.models.profile import BusinessProfile, BusinessType

NOW = dt.datetime(2026, 11, 10, tzinfo=dt.UTC)
TODAY = dt.date(2026, 11, 10)
SITE_995 = site_of("995 Valencia St, San Francisco, CA 94110", "995 VALENCIA ST", "3609/026")
REPO = Path(__file__).resolve().parents[3]
INPUTS = REPO / "backtest" / "inputs.json"
# The reconciled control data (outside the repository) and the engine's data file the spec names (not built
# yet). Whichever is on this machine is compared with the module table.
CONTROL_FILES = (
    Path(os.environ.get("LOCAL_DATA_DIR", "~/sfhp-local")).expanduser()
    / "controls"
    / "reconciled"
    / "citywide.json",
    REPO / "apps" / "api" / "app" / "memo" / "data" / "sf_dated_controls.json",
)
HOURS_2AM = "Hours of operation: P 6 a.m.–2 a.m.; C 2 a.m.–6 a.m."

# The new profile fields, each None or empty when the description does not say.
NEW_FIELDS = (
    "licence_type",
    "licences_held",
    "alcohol_transaction",
    "formula_retail",
    "floor_area_before_sqft",
    "existing_use_stated",
    "changes_existing_business",
    "merges_storefronts",
    "stories",
    "closing_hour",
    "entertainment_kind",
    "outdoor_area",
    "outdoor_alcohol_service",
    "amends_prior_approval",
    "occupants_under_50",
)


# ---- builders ------------------------------------------------------------------------------------------
def profile(business_type: BusinessType = "bar", **kw: Any) -> BusinessProfile:
    return BusinessProfile(business_type=business_type, **kw)


def record(
    record_id: str,
    *,
    address: str | None = "995 VALENCIA ST, SAN FRANCISCO, CA 94110",
    matched: SiteMatch = "address",
    distance_m: float = 0.0,
    **fields: Any,
) -> SiteRecord:
    source = record_id.split(":")[0]
    app = Application.model_validate(
        {
            "id": record_id,
            "source": source,
            "source_id": record_id.split(":")[1],
            "source_url": f"https://example.org/{record_id}",
            "fetched_at": NOW,
            "address": address,
            "parcel": "3609/026",
            **fields,
        }
    )
    return SiteRecord(app, distance_m, matched)


def licence(
    source_id: str,
    number: str,
    *,
    issued: dt.date | None = dt.date(2015, 3, 1),
    status: str = "ACTIVE",
    **kw: Any,
) -> SiteRecord:
    """An ABC licence record. As in the ABC export, `decided_at` is the original issue date."""
    return record(
        f"abc:{source_id}",
        kind="abc_license",
        permit_type=f"Type {number} – On-Sale",
        license_type=number,
        status=status,
        outcome="approved",
        decided_at=issued,
        **kw,
    )


def decision(
    source_id: str,
    *,
    decided: dt.date | None,
    filed: dt.date | None = None,
    outcome: str = "approved",
    kind: str = "cua",
    record_kind: str | None = "use_decision",
    description: str = "Conditional Use Authorization to establish a Bar.",
    **kw: Any,
) -> SiteRecord:
    """A Planning record. `record_kind` is the classifier's label; None leaves the record unlabelled."""
    return record(
        f"datasf_planning:{source_id}",
        kind=kind,
        permit_type="Conditional Use Authorization" if kind == "cua" else "Variance",
        description=description,
        outcome=outcome,
        filed_at=filed,
        decided_at=decided,
        extra={"record_kind": record_kind, "premises": True} if record_kind else {},
        **kw,
    )


def cases() -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = json.loads(INPUTS.read_text())["cases"]
    return loaded


def fact_sets() -> list[tuple[str, dict[str, Any]]]:
    """Every "input_facts" and "record_facts" object of the 40 cases: 80 in all."""
    return [
        (f"{case_id}/{which}", case[which])
        for case_id, case in cases().items()
        for which in ("input_facts", "record_facts")
    ]


# ---- a fact and its source -----------------------------------------------------------------------------
def test_nothing_stated_means_every_new_fact_is_missing() -> None:
    """A profile with only a business type: every fact of the new fields is missing, with no value. The older
    yes/no defaults (closes by midnight, no outdoor seating) are never read as stated."""
    f = concept_facts(profile("bar"))
    assert f.planning_uses == Fact(("bar",), "derived", "business_type")
    # the chain count is named only in place of the chain question (when the applicant says it is a chain),
    # what alcohol will be served only in place of the licence type (when the concept serves alcohol), and the
    # kind of food or drink service only in place of the kind of business (a bar that serves no alcohol)
    assert f.missing_names() == tuple(
        n
        for n in MISSING_PHRASES
        if n not in ("planning_uses", "other_locations", "alcohol_served", "food_service")
    )
    for name in f.missing_names():
        fact = getattr(f, name)
        if isinstance(fact, Closing):
            assert (fact.minute, fact.bucket, fact.read_at, fact.basis) == (None, None, None, None)
        else:
            assert fact.value in (None, ()), name
            assert fact.basis is None
    assert (f.live_entertainment, f.amplified_sound, f.dancing, f.serves_alcohol) == (
        False,
        False,
        False,
        False,
    )
    assert f.outdoor_area_described is False


def test_every_new_profile_field_is_read_as_stated() -> None:
    f = concept_facts(
        profile(
            "restaurant",
            serves_alcohol=True,
            alcohol_type="full_liquor",
            seats=98,
            square_feet=2950,
            licence_type="47",
            licences_held=["41"],
            alcohol_transaction="premises_transfer",
            formula_retail=False,
            floor_area_before_sqft=1486,
            existing_use_stated=["vacant", "restaurant"],
            changes_existing_business="enlarge",
            merges_storefronts=True,
            stories=["first", "basement"],
            closing_hour="23:00",
            entertainment_kind="none",
            outdoor_area="rear_or_side",
            outdoor_alcohol_service=False,
            amends_prior_approval=False,
            occupants_under_50=False,
        )
    )
    assert f.missing() == ()
    assert f.licence_type == Fact("47", "stated", "licence_type")
    assert f.licences_held == Fact(("41",), "stated", "licences_held")
    assert f.alcohol_transaction == Fact("premises_transfer", "stated", "alcohol_transaction")
    # a stated "no" is a value, not a missing fact
    assert f.formula_retail == Fact(False, "stated", "formula_retail")
    assert f.outdoor_alcohol_service == Fact(False, "stated", "outdoor_alcohol_service")
    assert f.amends_prior_approval == Fact(False, "stated", "amends_prior_approval")
    assert f.occupants_under_50 == Fact(False, "stated", "occupants_under_50")
    assert f.entertainment_kind == Fact("none", "stated", "entertainment_kind")
    assert f.floor_area_sqft == Fact(2950, "stated", "square_feet")
    assert f.floor_area_before_sqft == Fact(1486, "stated", "floor_area_before_sqft")
    assert f.merges_storefronts == Fact(True, "stated", "merges_storefronts")
    assert f.existing_use_stated == Fact(("vacant", "restaurant"), "stated", "existing_use_stated")
    assert f.changes_existing_business == Fact("enlarge", "stated", "changes_existing_business")
    assert f.stories == Fact(("first", "basement"), "stated", "stories")
    assert f.outdoor_area == Fact("rear_or_side", "stated", "outdoor_area")
    assert f.seats == Fact(98, "stated", "seats")
    assert f.closing.stated and not f.story_missing and f.outdoor_area_described


def test_fact_flags() -> None:
    assert Fact(1, "stated", "seats").stated and not Fact(1, "stated", "seats").missing
    assert Fact(1, "derived", "seats").derived
    assert Fact(None, "missing").missing
    with pytest.raises(dataclasses.FrozenInstanceError):
        Fact(1, "stated").value = 2  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        concept_facts(profile()).dancing = True  # type: ignore[misc]


def test_entertainment_flags_are_read_as_today() -> None:
    f = concept_facts(profile("bar", live_entertainment=True, amplified_sound=True, dancing=True))
    assert (f.live_entertainment, f.amplified_sound, f.dancing) == (True, True, True)
    assert f.entertainment_kind.missing  # live music does not say which permit


# ---- planning uses -------------------------------------------------------------------------------------
@pytest.mark.parametrize("business_type", get_args(BusinessType))
@pytest.mark.parametrize("serves_alcohol", [False, True])
def test_the_use_from_the_business_type_is_rule_table_v1s(
    business_type: BusinessType, serves_alcohol: bool
) -> None:
    p = profile(business_type, serves_alcohol=serves_alcohol)
    f = concept_facts(p)
    v1 = planning_use(p)
    assert f.use == v1
    if v1 == "not_covered":
        assert f.planning_uses.value == () and f.use_readings == ()
        # "other" does not say what the business is; a food truck or a hotel does, and is outside the table
        assert f.planning_uses.source == ("missing" if business_type == "other" else "derived")
    else:
        assert f.planning_uses == Fact((v1,), "derived", "business_type")


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("42", "bar"),
        ("48", "bar"),
        ("61", "bar"),
        ("41", "restaurant"),
        ("47", "restaurant"),
        ("75", "restaurant"),
        ("49", "restaurant"),
        ("59", "restaurant"),
        ("87", "restaurant"),
    ],
)
def test_a_licence_type_alone_decides_the_use_when_the_business_type_does_not(
    number: str, expected: str
) -> None:
    f = concept_facts(profile("other", serves_alcohol=True, licence_type=number))
    assert f.planning_uses == Fact((expected,), "derived", "licence_type")
    assert [(r.use, r.source, r.basis) for r in f.use_readings] == [(expected, "derived", "licence_type")]


@pytest.mark.parametrize("number", ["02", "23", "40", "60", "20", "21", "64", "86", "90", "beer and wine"])
def test_a_licence_type_under_both_uses_or_neither_decides_no_use(number: str) -> None:
    f = concept_facts(profile("other", serves_alcohol=True, licence_type=number))
    assert f.planning_uses == Fact((), "missing")
    assert f.use == "not_covered"
    assert f.missing(["planning_use"]) == (MISSING_PHRASES["planning_uses"],)


def test_the_business_type_wins_over_the_licence_type() -> None:
    f = concept_facts(profile("restaurant", serves_alcohol=True, licence_type="48"))
    assert f.planning_uses == Fact(("restaurant",), "derived", "business_type")
    assert f.licence_type == Fact("48", "stated", "licence_type")


def test_nighttime_entertainment_is_added_only_on_a_place_of_entertainment_or_dancing() -> None:
    poe = concept_facts(profile("bar", entertainment_kind="place_of_entertainment"))
    assert poe.planning_uses == Fact(
        ("bar", "nighttime_entertainment"), "derived", "business_type, entertainment_kind"
    )
    assert poe.use == "bar"
    dancing = concept_facts(profile("restaurant", dancing=True))
    assert dancing.planning_uses.value == ("restaurant", "nighttime_entertainment")
    assert dancing.use_readings[1].basis == "dancing"
    club = concept_facts(profile("other", entertainment_kind="place_of_entertainment"))
    assert club.planning_uses == Fact(("nighttime_entertainment",), "derived", "entertainment_kind")
    # never on live music, amplified sound or a Limited Live Performance permit
    for kw in (
        {"live_entertainment": True, "amplified_sound": True},
        {"entertainment_kind": "limited_live_performance"},
        {"entertainment_kind": "none"},
        {"closes_after_2am": True},
    ):
        assert concept_facts(profile("bar", **kw)).planning_uses.value == ("bar",), kw


def test_stated_uses_are_kept_as_stated_and_listed_in_one_order() -> None:
    f = concept_facts(profile("other"), stated_uses=["nighttime_entertainment", "bar"])
    assert f.planning_uses == Fact(("bar", "nighttime_entertainment"), "stated", "planning_use")
    assert f == concept_facts(profile("other"), stated_uses=["bar", "nighttime_entertainment", "bar"])
    # a stated use and a derived one: each keeps its own source
    mixed = concept_facts(profile("food_truck", dancing=True), stated_uses=["restaurant"])
    assert [(r.use, r.source, r.basis) for r in mixed.use_readings] == [
        ("restaurant", "stated", "planning_use"),
        ("nighttime_entertainment", "derived", "dancing"),
    ]
    assert mixed.planning_uses.source == "stated"
    # "not covered" states no use
    assert concept_facts(profile("food_truck"), stated_uses=["not_covered"]).planning_uses.value == ()


def test_uses_never_include_one_the_input_does_not_support() -> None:
    """Every use comes from the business type, a stated use, a licence type, a Place of Entertainment permit
    or dancing. A profile with none of them has no use, whatever else it says."""
    busy = profile(
        "other",
        serves_alcohol=True,
        alcohol_type="full_liquor",
        live_entertainment=True,
        amplified_sound=True,
        closes_after_2am=True,
        seats=200,
        existing_use_stated=["bar", "nighttime_entertainment"],
        licences_held=["48"],
        entertainment_kind="limited_live_performance",
    )
    assert concept_facts(busy).planning_uses == Fact((), "missing")


# ---- the licence-type-to-use table against § 102 -------------------------------------------------------
def test_the_licence_table_is_the_reconciled_lists_as_read_on_2026_11_10() -> None:
    assert set(BAR_LICENCE_TYPES) == {"23", "42", "48", "61", "40", "60", "02"}
    assert set(RESTAURANT_LICENCE_TYPES) == {"02", "23", "41", "47", "49", "59", "75", "87"}
    assert frozenset({"02", "23"}) == LICENCE_TYPES_EITHER_USE
    assert frozenset({"40", "60"}) == BAR_ONLY_WITH_OTHER_USES
    assert USE_FOR_LICENCE == {
        "42": "bar",
        "48": "bar",
        "61": "bar",
        "41": "restaurant",
        "47": "restaurant",
        "49": "restaurant",
        "59": "restaurant",
        "75": "restaurant",
        "87": "restaurant",
    }


def test_the_licence_table_never_shows_a_use_section_102_does_not_give_the_type() -> None:
    for number, use in USE_FOR_LICENCE.items():
        own, other = (
            (BAR_LICENCE_TYPES, RESTAURANT_LICENCE_TYPES)
            if use == "bar"
            else (RESTAURANT_LICENCE_TYPES, BAR_LICENCE_TYPES)
        )
        assert number in own and number not in other, number
    # each list's own words name every type in it that decides a use
    for number, use in USE_FOR_LICENCE.items():
        quote = (BAR_LICENCE_SOURCE if use == "bar" else RESTAURANT_LICENCE_SOURCE).quote
        assert number in quote, number
    for source in (BAR_LICENCE_SOURCE, RESTAURANT_LICENCE_SOURCE):
        assert source.section.startswith("Planning Code § 102")
        assert source.url.startswith("https://") and source.read_on == "2026-11-10"


def test_the_licence_table_agrees_with_rule_table_v1() -> None:
    """v1 reads six on-sale types from the records; the same type must show the same use here."""
    for number, kind in LICENCE_TYPES.items():
        assert USE_FOR_LICENCE[number] == kind.shows, number
    for (use, _), number in LICENCE_FOR_CONCEPT.items():
        assert USE_FOR_LICENCE[number] == use


def _use_definitions(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    found: list[dict[str, Any]] = data.get("citywide", data).get("use_definitions") or []
    return found


@pytest.mark.parametrize("path", CONTROL_FILES, ids=lambda p: p.name)
def test_the_licence_table_against_the_reconciled_definitions(path: Path) -> None:
    """Every dated version of the § 102 definitions on file gives the same two lists as the module table."""
    if not path.exists():
        pytest.skip(f"{path} is not on this machine")
    versions = _use_definitions(path)
    if not versions and path.name != "citywide.json":
        pytest.skip(f"{path.name} carries no use definitions")
    assert versions, "the reconciled control data has no use definitions"
    for version in versions:
        dated = f"{version['from']} to {version['to']}"
        assert sorted(version["facts"]["bar_abc_types"]) == sorted(BAR_LICENCE_TYPES), dated
        assert sorted(version["facts"]["restaurant_on_sale_abc_types"]) == sorted(RESTAURANT_LICENCE_TYPES), (
            dated
        )
        assert version["facts"]["limited_restaurant_on_sale_allowed"] is False, dated
        for number, use in USE_FOR_LICENCE.items():
            key = "bar_abc_types" if use == "bar" else "restaurant_on_sale_abc_types"
            other = "restaurant_on_sale_abc_types" if use == "bar" else "bar_abc_types"
            assert number in version["facts"][key] and number not in version["facts"][other], (dated, number)
    quotes = " ".join(" ".join(s["quote"].split()) for v in versions for s in v.get("sources", []))
    assert BAR_LICENCE_SOURCE.quote in quotes
    assert RESTAURANT_LICENCE_SOURCE.quote in quotes


# ---- licence type and transaction ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("41", "41"),
        ("Type 47", "47"),
        ("2", "02"),
        ("02", "02"),
        ("type 048", "48"),
        ("", None),
        (None, None),
    ],
)
def test_normal_licence_type(text: str | None, expected: str | None) -> None:
    assert normal_licence_type(text) == expected


@pytest.mark.parametrize(("key", "number"), LICENCE_FOR_CONCEPT.items())
def test_the_licence_type_is_derived_exactly_as_v1s_table_does(key: tuple[str, str], number: str) -> None:
    use, pours = key
    f = concept_facts(profile(use, serves_alcohol=True, alcohol_type=pours))  # type: ignore[arg-type]
    assert f.licence_type == Fact(number, "derived", "business_type, alcohol_type")
    assert f.source_of("licence_type") == "derived"
    assert f.missing(["licence_type"]) == ()


def test_the_licence_type_stated_wins_and_is_written_one_way() -> None:
    f = concept_facts(profile("bar", serves_alcohol=True, alcohol_type="beer_wine", licence_type="Type 48"))
    assert f.licence_type == Fact("48", "stated", "licence_type")
    held = concept_facts(profile("bar", licences_held=["2", "Type 20", "86", "20"]))
    assert held.licences_held == Fact(("02", "20", "86"), "stated", "licences_held")


POURS = "what alcohol will be served: beer and wine, or spirits too"


@pytest.mark.parametrize(
    ("p", "named"),
    [
        (profile("bar"), "the licence type"),  # no alcohol said
        # alcohol, but not what it pours (v1 assumed beer and wine): what is poured is named instead
        (profile("bar", serves_alcohol=True), POURS),
        (profile("bar", serves_alcohol=True, alcohol_type="unknown"), POURS),
        (profile("restaurant", serves_alcohol=True, alcohol_type="unknown"), POURS),
        (profile("cafe"), "the licence type"),  # a Limited Restaurant has no on-sale licence
        # no use to look the type up by: what is poured would not decide it, so the type itself is named
        (profile("other", serves_alcohol=True, alcohol_type="full_liquor"), "the licence type"),
        (profile("food_truck", serves_alcohol=True, alcohol_type="unknown"), "the licence type"),
        (
            profile("bar", serves_alcohol=True, alcohol_type="beer_wine", licence_type="a liquor licence"),
            None,
        ),
    ],
)
def test_the_licence_type_is_missing_when_nothing_gives_it(p: BusinessProfile, named: str | None) -> None:
    f = concept_facts(p)
    if named is not None:
        assert f.licence_type == Fact(None, "missing")
        assert f.missing(["licence_type"]) == (named,)
        assert f.licence_type_phrase == named
        assert f.pours_missing is (named == POURS)
    else:  # words with no type number are not a stated type; the type is then derived
        assert f.licence_type == Fact("42", "derived", "business_type, alcohol_type")


def test_unknown_pours_are_never_read_as_beer_and_wine_nor_as_no_alcohol() -> None:
    for p in (
        profile("bar", serves_alcohol=True, alcohol_type="unknown"),
        profile("bar", serves_alcohol=True),
    ):
        f = concept_facts(p)
        assert f.serves_alcohol is True and f.alcohol_served == Fact(None, "missing")
        assert f.licence_type == Fact(None, "missing")
        # named only in place of the licence type, and only once
        assert f.missing().count(POURS) == 1 and "the licence type" not in f.missing()
        assert f.missing(["alcohol_served"]) == ()
    # normalising a profile that serves alcohol without saying what leaves it unknown, and changes no answer
    raw = profile("restaurant", serves_alcohol=True)
    assert raw.normalized().alcohol_type == "unknown"
    assert concept_facts(raw.normalized()).missing() == concept_facts(raw).missing()
    # a stated licence type still decides it
    stated = concept_facts(profile("bar", serves_alcohol=True, alcohol_type="unknown", licence_type="48"))
    assert stated.licence_type == Fact("48", "stated", "licence_type") and POURS not in stated.missing()
    # what is stated is read; no alcohol is derived "none"
    assert concept_facts(
        profile("bar", serves_alcohol=True, alcohol_type="full_liquor")
    ).alcohol_served == Fact("full_liquor", "stated", "alcohol_type")
    assert concept_facts(profile("cafe")).alcohol_served == Fact("none", "derived", "serves_alcohol")


def test_the_transaction_is_stated_or_missing_and_never_derived() -> None:
    for p in (
        profile("bar", serves_alcohol=True, alcohol_type="full_liquor"),
        profile("bar", serves_alcohol=True, licence_type="48", licences_held=["48"]),
        profile("restaurant", serves_alcohol=True, changes_existing_business="none"),
    ):
        f = concept_facts(p)
        assert f.alcohol_transaction == Fact(None, "missing")
        assert f.missing(["alcohol_transaction"]) == (
            "how the liquor licence will be obtained (new, or a transfer from another owner or another location)",
        )
    for value in ("new_licence", "person_to_person_transfer", "premises_transfer", "licence_already_held"):
        f = concept_facts(profile("bar", alcohol_transaction=value))
        assert f.alcohol_transaction == Fact(value, "stated", "alcohol_transaction")


# ---- closing time --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("hour", "minute", "bucket", "read_at"),
    [
        ("22:00", 1320, "by_midnight", 1319),
        ("23:59", 1439, "by_midnight", 1438),
        ("00:00", 0, "by_midnight", 1439),  # midnight: the last open minute is 11:59 p.m.
        ("00:30", 30, "after_midnight", 29),
        ("01:30", 90, "after_midnight", 89),
        ("02:00", 120, "after_midnight", 119),  # a 2 a.m. close is not "after 2 a.m."
        ("02:01", 121, "after_2am", 120),
        ("04:00", 240, "after_2am", 239),
        ("06:00", 360, "after_2am", 359),
        ("06:01", 361, "by_midnight", 360),
        ("14:00", 840, "by_midnight", 839),
    ],
)
def test_a_stated_closing_hour_is_read_at_its_last_open_minute(
    hour: str, minute: int, bucket: str, read_at: int
) -> None:
    c = concept_facts(profile("bar", closing_hour=hour)).closing
    # a morning close with no flag saying the business is open overnight: not known whether it is (review)
    overnight = None if 6 * 60 < minute < 12 * 60 else False
    assert c == Closing("stated", minute, bucket, read_at, "closing_hour", overnight=overnight)  # type: ignore[arg-type]
    assert clock_minutes(hour) == minute and closing_bucket_at(minute) == bucket
    assert c.after_2am is (bucket == "after_2am")


def test_a_stated_closing_hour_reads_the_right_window_of_an_hours_control() -> None:
    control = parse_hours(HOURS_2AM)
    assert control is not None

    def at(hour: str) -> str | None:
        read_at = concept_facts(profile("bar", closing_hour=hour)).closing.read_at
        assert read_at is not None
        return control.at(read_at)

    assert at("23:00") == "P"
    assert at("02:00") == "P"  # closing at 2 a.m. is inside "P 6 a.m. to 2 a.m."
    assert at("02:30") == "C"
    assert at("06:00") == "C"


def test_the_closing_flags_give_v1s_bucket_marked_derived() -> None:
    after_midnight = profile("bar", closes_after_midnight=True)
    c = concept_facts(after_midnight).closing
    assert c == Closing("derived", None, "after_midnight", READ_AT["after_midnight"], "closes_after_midnight")
    after_2am = profile("bar", closes_after_midnight=True, closes_after_2am=True)
    c = concept_facts(after_2am).closing
    assert c == Closing("derived", None, "after_2am", READ_AT["after_2am"], "closes_after_2am")
    assert c.after_2am and c.derived
    for p in (after_midnight, after_2am):
        assert concept_facts(p).closing.bucket == closing_bucket(p)
        assert concept_facts(p).missing(["closing_hour"]) == ()


def test_the_stated_hour_wins_over_the_flags() -> None:
    c = concept_facts(profile("bar", closing_hour="23:00", closes_after_2am=True)).closing
    assert (c.source, c.bucket, c.read_at) == ("stated", "by_midnight", 1379)


def test_no_closing_time_is_missing_not_by_midnight() -> None:
    f = concept_facts(profile("bar"))
    assert f.closing == Closing("missing", None, None, None)
    assert f.closing.missing and not f.closing.after_2am
    assert f.missing(["closing"]) == ("the closing time",)


def test_clock_minutes_rejects_anything_but_hh_mm() -> None:
    for bad in ("2am", "24:00", "7:30", "12:60", ""):
        with pytest.raises(ValueError, match="HH:MM"):
            clock_minutes(bad)


# ---- stories -------------------------------------------------------------------------------------------
def test_no_story_is_assumed_when_none_is_stated() -> None:
    # the user's decision of 2026-11-12: "MISSING STORY: always 'Insufficient information', naming it. Never
    # default to the first story."
    f = concept_facts(profile("bar"))
    assert f.stories == Fact((), "missing")
    assert f.story_missing is True
    assert not hasattr(f, "stories_read") and not hasattr(f, "first_story_assumed")
    assert f.missing(["story"]) == ("which stories the business occupies",)


def test_stated_stories_are_read_as_stated() -> None:
    # each once, in the fixed order of Story whatever order they were given in (corrected: the order given was
    # kept before the review, which made the output depend on it)
    f = concept_facts(profile("bar", stories=["second", "first", "second"]))
    assert f.stories == Fact(("first", "second"), "stated", "stories")
    assert f.story_missing is False
    assert f.missing(["stories"]) == ()
    assert concept_facts(profile("bar", stories=["basement"])).stories.value == ("basement",)


# ---- outdoor area --------------------------------------------------------------------------------------
def test_outdoor_area_reads_the_new_field_first() -> None:
    f = concept_facts(profile("bar", outdoor_area="rooftop", sidewalk_or_parklet=True, outdoor_seating=True))
    assert f.outdoor_area == Fact("rooftop", "stated", "outdoor_area")
    assert f.outdoor_area_described is True
    none = concept_facts(profile("bar", outdoor_area="none"))
    assert none.outdoor_area == Fact("none", "stated", "outdoor_area")
    assert none.outdoor_area_described is False and none.missing(["outdoor_area"]) == ()


def test_outdoor_area_from_the_older_fields_only_where_they_say_where() -> None:
    sidewalk = concept_facts(profile("bar", sidewalk_or_parklet=True))
    assert sidewalk.outdoor_area == Fact("sidewalk", "derived", "sidewalk_or_parklet")
    assert sidewalk.outdoor_area_described is True
    # outdoor seating says there is an outdoor area, not where it is
    somewhere = concept_facts(profile("bar", outdoor_seating=True))
    assert somewhere.outdoor_area == Fact(None, "missing")
    assert somewhere.outdoor_area_described is True
    assert somewhere.missing(["outdoor_area"]) == ("where the outdoor area is",)
    # the default "no outdoor seating" is never read as "no outdoor area"
    silent = concept_facts(profile("bar"))
    assert silent.outdoor_area == Fact(None, "missing") and silent.outdoor_area_described is False


# ---- occupants -----------------------------------------------------------------------------------------
def test_occupants_are_stated_or_missing() -> None:
    f = concept_facts(profile("restaurant", seats=30))
    assert f.seats == Fact(30, "stated", "seats")
    assert f.occupants_under_50 == Fact(None, "missing")  # thirty seats do not say how many people
    assert f.missing(["occupants"]) == ("whether the space is for fewer than 50 people",)
    f = concept_facts(profile("restaurant", occupants_under_50=True))
    assert f.occupants_under_50 == Fact(True, "stated", "occupants_under_50")
    assert f.seats == Fact(None, "missing") and f.missing(["seats"]) == ("the number of seats",)


# ---- the fixed missing-input phrases -------------------------------------------------------------------
def test_the_missing_input_phrases_are_fixed() -> None:
    assert MISSING_PHRASES == {
        "planning_uses": "what kind of business it is (a bar, a restaurant, a cafe or an entertainment venue)",
        "food_service": (
            "what kind of food or drink service it is, since a business that serves no alcohol is not a Bar: a "
            "Restaurant (prepared food, with seating), a Limited Restaurant (ready-to-eat food or drinks) or "
            "another use"
        ),
        "alcohol_served": "what alcohol will be served: beer and wine, or spirits too",
        "licence_type": "the licence type",
        "licences_held": "which licences the business already holds",
        "alcohol_transaction": (
            "how the liquor licence will be obtained (new, or a transfer from another owner or another location)"
        ),
        "formula_retail": (
            "whether the business is part of a chain that shares its name, look or menu with other locations"
        ),
        "other_locations": "how many other locations the chain has, open or approved, anywhere in the world",
        "floor_area_sqft": "the floor area of the business, in square feet",
        "floor_area_before_sqft": "the floor area before the project",
        "merges_storefronts": "whether storefronts are to be merged",
        "existing_use_stated": "what the space was last used as",
        "changes_existing_business": "whether an existing business is to be enlarged or intensified",
        "amends_prior_approval": "whether the conditions of an earlier approval are to be changed",
        "stories": "which stories the business occupies",
        "closing": "the closing time",
        "entertainment_kind": "whether there is entertainment, and what kind",
        "outdoor_area": "where the outdoor area is",
        "outdoor_alcohol_service": "whether alcohol is to be served in the outdoor area",
        "seats": "the number of seats",
        "occupants_under_50": "whether the space is for fewer than 50 people",
    }


def test_every_fact_with_a_source_has_one_phrase_and_the_phrases_differ() -> None:
    sourced = {
        f.name
        for f in dataclasses.fields(ConceptFacts)
        if isinstance(getattr(concept_facts(profile()), f.name), Fact | Closing)
    }
    assert sourced == set(MISSING_PHRASES)
    assert len(set(MISSING_PHRASES.values())) == len(MISSING_PHRASES)
    for phrase in MISSING_PHRASES.values():
        assert phrase == phrase.strip() and not phrase.endswith(".") and phrase[0].islower()
        assert "license" not in phrase  # spelt "licence", as the code does
    assert set(FACT_ALIASES.values()) <= set(MISSING_PHRASES)
    assert not set(FACT_ALIASES) & set(MISSING_PHRASES)


def test_missing_names_each_input_once_in_one_order() -> None:
    f = concept_facts(profile("other"))
    asked = ["story", "closing_hour", "licence_type", "stories", "formula_retail", "closing", "planning_use"]
    assert f.missing(asked) == (
        "what kind of business it is (a bar, a restaurant, a cafe or an entertainment venue)",
        "the licence type",
        "whether the business is part of a chain that shares its name, look or menu with other locations",
        "which stories the business occupies",
        "the closing time",
    )
    assert f.missing(reversed(asked)) == f.missing(asked)
    assert f.missing_names(asked) == ("planning_uses", "licence_type", "formula_retail", "stories", "closing")
    assert f.missing([]) == ()
    # nothing is stated; the chain count is named only in place of the chain question, and what is poured only
    # in place of the licence type
    assert f.missing() == tuple(
        v
        for k, v in MISSING_PHRASES.items()
        if k not in ("other_locations", "alcohol_served", "food_service")
    )


def test_missing_lists_only_what_is_missing() -> None:
    f = concept_facts(profile("bar", formula_retail=False, closing_hour="23:00", sidewalk_or_parklet=True))
    asked = ["formula_retail", "closing", "outdoor_area", "floor_area_sqft", "planning_uses"]
    assert f.missing(asked) == ("the floor area of the business, in square feet",)
    assert [f.source_of(n) for n in asked] == ["stated", "stated", "derived", "missing", "derived"]


def test_an_unknown_fact_name_is_an_error() -> None:
    f = concept_facts(profile())
    for call in (f.missing, f.missing_names, f.source_of, fact_name, missing_phrase):
        with pytest.raises(KeyError, match="not a concept fact"):
            call(["storey"] if call in (f.missing, f.missing_names) else "storey")  # type: ignore[operator]
    assert missing_phrase("closing_hour") == missing_phrase("closing") == "the closing time"
    assert fact_name("square_feet") == "floor_area_sqft"


# ---- profile_from_facts on the 40 cases ----------------------------------------------------------------
def test_the_backtest_has_40_cases_in_the_field_names_of_the_spec() -> None:
    sets = fact_sets()
    assert len(cases()) == 40 and len(sets) == 80
    for label, facts in sets:
        assert set(facts) == FACT_KEYS, label


# a facts key -> the concept fact that must be missing when the key is null
NULL_MEANS_MISSING = {
    "licence_type": "licence_type",
    "licences_already_held": "licences_held",
    "alcohol_transaction": "alcohol_transaction",
    "formula_retail": "formula_retail",
    "floor_area_sqft": "floor_area_sqft",
    "floor_area_before_sqft": "floor_area_before_sqft",
    "merges_storefronts": "merges_storefronts",
    "existing_use_stated": "existing_use_stated",
    "changes_existing_business": "changes_existing_business",
    "amends_prior_approval": "amends_prior_approval",
    "story": "stories",
    "closing_hour": "closing",
    "entertainment_kind": "entertainment_kind",
    "outdoor_area": "outdoor_area",
    "outdoor_alcohol_service": "outdoor_alcohol_service",
    "seats": "seats",
    "occupants": "occupants_under_50",
}


@pytest.mark.parametrize(("label", "facts"), fact_sets(), ids=[label for label, _ in fact_sets()])
def test_every_case_builds_a_valid_profile_and_a_null_stays_missing(
    label: str, facts: dict[str, Any]
) -> None:
    p = profile_from_facts(facts)
    assert BusinessProfile.model_validate(p.model_dump()) == p
    assert p.assumptions == []
    for f in (concept_facts(p), concept_facts_from_facts(facts)):
        for key, name in NULL_MEANS_MISSING.items():
            source = f.source_of(name)
            if facts[key] is None:
                assert source == "missing", (key, source)
                # a missing licence type of a concept that serves alcohol without saying what is named by what
                # is poured
                named = f.licence_type_missing_name if name == "licence_type" else name
                assert MISSING_PHRASES[named] in f.missing([name])
            else:
                assert source == "stated", (key, source)
                assert f.missing([name]) == ()
    # a null use is never "stated"; the uses a facts object states are carried as stated
    carried = concept_facts_from_facts(facts)
    stated = stated_planning_uses(facts)
    assert concept_facts(p).planning_uses.source != "stated"
    if stated:
        assert carried.planning_uses.source == "stated"
        assert set(stated) <= set(carried.planning_uses.value)
    else:
        assert carried == concept_facts(p)
    # nothing else is invented: the yes/no fields are true only where the facts say true
    assert p.serves_alcohol is (facts["serves_alcohol"] is True)
    assert p.live_entertainment is (facts["live_entertainment"] is True)
    assert p.amplified_sound is (facts["amplified_sound"] is True)
    assert p.new_construction is (facts["new_construction"] is True)
    assert p.dancing is False and p.change_of_use is False
    assert (p.city_slug, p.neighborhood, p.employees, p.target_open_date) == (None, None, None, None)


@pytest.mark.parametrize(("label", "facts"), fact_sets(), ids=[label for label, _ in fact_sets()])
def test_every_case_keeps_the_values_it_states(label: str, facts: dict[str, Any]) -> None:
    def listed(value: Any) -> list[Any]:
        return [] if value is None else value if isinstance(value, list) else [value]

    p = profile_from_facts(facts)
    f = concept_facts_from_facts(facts)
    assert p.business_type == (facts["business_type"] or "other")
    assert f.licence_type.value == facts["licence_type"]
    assert list(f.licences_held.value) == listed(facts["licences_already_held"])
    assert f.alcohol_transaction.value == facts["alcohol_transaction"]
    assert f.formula_retail.value == facts["formula_retail"]
    assert f.floor_area_sqft.value == facts["floor_area_sqft"]
    assert f.floor_area_before_sqft.value == facts["floor_area_before_sqft"]
    assert f.merges_storefronts.value == facts["merges_storefronts"]
    assert list(f.existing_use_stated.value) == listed(facts["existing_use_stated"])
    assert f.changes_existing_business.value == facts["changes_existing_business"]
    assert f.amends_prior_approval.value == facts["amends_prior_approval"]
    assert list(f.stories.value) == listed(facts["story"])
    assert f.story_missing is (facts["story"] is None)
    assert p.closing_hour == facts["closing_hour"]
    assert f.entertainment_kind.value == facts["entertainment_kind"]
    assert f.outdoor_area.value == facts["outdoor_area"]
    assert f.outdoor_alcohol_service.value == facts["outdoor_alcohol_service"]
    assert f.seats.value == facts["seats"]
    occupants = facts["occupants"]
    expected = None if occupants is None else True if occupants == "under 50" else occupants < 50
    assert f.occupants_under_50.value is expected
    # the uses: what the facts state, plus only what the rules derive from the same facts
    uses = set(f.planning_uses.value)
    assert set(listed(facts["planning_use"])) - {"not_covered"} <= uses
    assert all(
        r.source == "stated" or r.basis in ("business_type", "licence_type", "entertainment_kind")
        for r in f.use_readings
    )
    assert facts_not_carried(facts) == tuple(k for k in FACTS_WITHOUT_A_PROFILE_FIELD if facts[k] is not None)


def test_the_same_closing_time_is_read_by_both_rule_tables() -> None:
    """A stated closing hour also sets the v1 flags, so `pathway.closing_bucket` agrees on the same profile."""
    seen = set()
    for _, facts in fact_sets():
        p = profile_from_facts(facts)
        c = concept_facts(p).closing
        if facts["closing_hour"] is None:
            assert c.missing and closing_bucket(p) == "by_midnight"
        else:
            assert c.minute == clock_minutes(facts["closing_hour"])
            assert c.bucket == closing_bucket(p)
            seen.add(facts["closing_hour"])
    assert {"00:00", "01:30", "02:00", "23:00"} <= seen


def test_profile_from_facts_reads_single_values_lists_and_under_50() -> None:
    p = profile_from_facts(
        {
            "business_type": "bar",
            "serves_alcohol": True,
            "licence_type": "48",
            "licences_already_held": ["20", "86"],
            "existing_use_stated": ["vacant", "nighttime_entertainment"],
            "story": ["first", "basement"],
            "occupants": "under 50",
            "outdoor_area": "sidewalk",
            "closing_hour": "02:30",
            "operator_name": "Club Deluxe",
            "tenant_improvements": False,
        }
    )
    assert (p.licence_type, p.alcohol_type, p.licences_held) == ("48", "full_liquor", ["20", "86"])
    assert p.existing_use_stated == ["vacant", "nighttime_entertainment"]
    assert p.stories == ["first", "basement"] and p.occupants_under_50 is True
    assert (p.outdoor_area, p.outdoor_seating, p.sidewalk_or_parklet) == ("sidewalk", True, True)
    assert (p.closing_hour, p.closes_after_midnight, p.closes_after_2am) == ("02:30", True, True)
    assert p.business_name == "Club Deluxe" and p.tenant_improvements is False
    single = profile_from_facts({"existing_use_stated": "laundromat", "story": "second", "occupants": 26})
    assert single.business_type == "other"
    assert single.existing_use_stated == ["laundromat"] and single.stories == ["second"]
    assert single.occupants_under_50 is True
    assert profile_from_facts({"occupants": 50}).occupants_under_50 is False
    assert profile_from_facts({"licence_type": ["41"]}).licence_type == "41"
    # a licence type the rules have no pour for leaves the alcohol type unsaid
    assert profile_from_facts({"serves_alcohol": True, "licence_type": "90"}).alcohol_type == "unknown"
    assert profile_from_facts({"serves_alcohol": True}).alcohol_type == "unknown"
    assert profile_from_facts({"licence_type": "90"}).alcohol_type == "none"


def test_profile_from_facts_of_nothing_states_nothing() -> None:
    p = profile_from_facts({})
    assert p == BusinessProfile(business_type="other")
    f = concept_facts(p)
    assert f.missing() == tuple(
        v
        for k, v in MISSING_PHRASES.items()
        if k not in ("other_locations", "alcohol_served", "food_service")
    )
    assert all(getattr(p, name) in (None, []) for name in NEW_FIELDS)


def test_profile_from_facts_refuses_what_it_cannot_read() -> None:
    with pytest.raises(ValueError, match="not a fact name of the spec: storey"):
        profile_from_facts({"storey": "first"})
    with pytest.raises(ValueError, match="licence_type takes one value"):
        profile_from_facts({"licence_type": ["41", "47"]})
    with pytest.raises(ValueError, match="occupants is a number"):
        profile_from_facts({"occupants": "about fifty"})
    with pytest.raises(ValueError, match="not a planning use"):
        stated_planning_uses({"planning_use": ["bar", "nightclub"]})
    with pytest.raises(ValueError):  # the profile's own validation: not a story of the spec
        profile_from_facts({"story": "mezzanine"})
    with pytest.raises(ValueError):
        profile_from_facts({"closing_hour": "2am"})


def test_stated_planning_uses() -> None:
    assert stated_planning_uses({"planning_use": None}) == ()
    assert stated_planning_uses({"planning_use": "not_covered"}) == ()
    assert stated_planning_uses({"planning_use": "restaurant"}) == ("restaurant",)
    assert stated_planning_uses({"planning_use": ["nighttime_entertainment", "bar"]}) == (
        "bar",
        "nighttime_entertainment",
    )
    assert set(USE_ORDER) == set(get_args(PlanningUse)) - {"not_covered"}


def test_a_stated_use_the_profile_cannot_hold_is_carried_by_concept_facts_from_facts() -> None:
    """Case N03 as coded from the description: "convert a bar/restaurant to nighttime entertainment". The
    profile has no field for the stated use, so only `concept_facts_from_facts` keeps it."""
    facts = cases()["N03"]["input_facts"]
    assert (facts["business_type"], facts["planning_use"], facts["entertainment_kind"]) == (
        "other",
        "nighttime_entertainment",
        None,
    )
    assert concept_facts(profile_from_facts(facts)).planning_uses == Fact((), "missing")
    carried = concept_facts_from_facts(facts)
    assert carried.planning_uses == Fact(("nighttime_entertainment",), "stated", "planning_use")
    assert carried.entertainment_kind.missing  # the permit kind is still not stated
    assert "planning_use" in facts_not_carried(facts)


# ---- site facts ----------------------------------------------------------------------------------------
TYPE_41 = licence("651564", "41", issued=dt.date(2015, 3, 1))
TYPE_20_OFF_SALE = licence("700020", "20", issued=dt.date(2001, 5, 9))
TYPE_48_NEXT_DOOR = licence(
    "700999", "48", address="999 VALENCIA ST, SAN FRANCISCO, CA 94110", matched="parcel"
)
TYPE_47_LATER = licence("800047", "47", issued=dt.date(2024, 6, 1))
TYPE_48_CANCELED = licence("700048", "48", status="CANCELED")
CUA_2019 = decision("2018-001234CUA", decided=dt.date(2019, 4, 11), filed=dt.date(2018, 2, 1))
CUA_2012 = decision(
    "2011.0456C",
    decided=dt.date(2012, 9, 6),
    outcome="approved_with_conditions",
    description="Conditional Use   Authorization for a full-service\nrestaurant.",
)
VARIANCE_2016 = decision("2016-000777VAR", decided=dt.date(2016, 1, 20), kind="planning_other")
CUA_DENIED = decision("2014.0001C", decided=dt.date(2014, 5, 1), outcome="denied")
CUA_WITHDRAWN = decision("2013.0002C", decided=dt.date(2013, 5, 1), outcome="withdrawn")
CUA_PENDING = decision("2021-000003CUA", decided=None, filed=dt.date(2021, 3, 3), outcome="pending")
REFERRAL = decision("2017-000004MIS", decided=dt.date(2017, 7, 7), record_kind="agency_referral")
BUILDING = decision("2015-000005PRJ", decided=dt.date(2015, 7, 7), record_kind="building_work")
UNLABELLED = decision("2010.0006C", decided=dt.date(2010, 7, 7), record_kind=None)
CUA_NEXT_DOOR = decision(
    "2009.0007C",
    decided=dt.date(2009, 7, 7),
    address="999 VALENCIA ST, SAN FRANCISCO, CA 94110",
    matched="parcel",
)
CUA_THE_CASE = decision("2023-005555CUA", decided=dt.date(2023, 9, 14), filed=dt.date(2023, 3, 2))
ALL_RECORDS = [
    TYPE_41,
    TYPE_20_OFF_SALE,
    TYPE_48_NEXT_DOOR,
    TYPE_47_LATER,
    TYPE_48_CANCELED,
    CUA_2019,
    CUA_2012,
    VARIANCE_2016,
    CUA_DENIED,
    CUA_WITHDRAWN,
    CUA_PENDING,
    REFERRAL,
    BUILDING,
    UNLABELLED,
    CUA_NEXT_DOOR,
    CUA_THE_CASE,
]


def test_site_facts_reads_the_active_licences_at_the_address() -> None:
    s = site_facts(ALL_RECORDS, SITE_995, rules_date=TODAY)
    assert s.rules_date == TODAY
    # in record id order; every ACTIVE type at the address, the ones v1 does not read among them
    assert [(lic.record_id, lic.licence_type, lic.label) for lic in s.licences] == [
        ("abc:651564", "41", "on-sale beer and wine, eating place"),
        ("abc:700020", "20", None),
        ("abc:800047", "47", "on-sale general, eating place"),
    ]
    assert s.licence_types == ("20", "41", "47")
    first = s.licences[0]
    assert (first.issued, first.citation, first.source_url) == (
        dt.date(2015, 3, 1),
        "app:abc:651564",
        "https://example.org/abc:651564",
    )
    assert s.existing_use == "restaurant"


def test_site_facts_existing_use_is_pathways() -> None:
    for records in (ALL_RECORDS, [TYPE_41], [TYPE_20_OFF_SALE], [], [TYPE_41, licence("700042", "42")]):
        s = site_facts(records, SITE_995, rules_date=TODAY)
        use, lines = existing_use(records, SITE_995)
        assert s.existing_use == use
        assert s.existing_use_lines == tuple(lines)
    both = site_facts([TYPE_41, licence("700042", "42")], SITE_995, rules_date=TODAY)
    assert both.existing_use is None and both.licence_types == ("41", "42")


def test_site_facts_lists_earlier_approved_use_decisions_newest_first() -> None:
    s = site_facts(ALL_RECORDS, SITE_995, rules_date=TODAY)
    assert [(d.record_id, d.date, d.outcome) for d in s.prior_decisions] == [
        ("datasf_planning:2023-005555CUA", dt.date(2023, 9, 14), "approved"),
        ("datasf_planning:2018-001234CUA", dt.date(2019, 4, 11), "approved"),
        ("datasf_planning:2016-000777VAR", dt.date(2016, 1, 20), "approved"),
        ("datasf_planning:2011.0456C", dt.date(2012, 9, 6), "approved_with_conditions"),
    ]
    by_id = {d.record_id: d for d in s.prior_decisions}
    cua = by_id["datasf_planning:2011.0456C"]
    assert cua.description == "Conditional Use Authorization for a full-service restaurant."
    assert (cua.permit_type, cua.conditional_use) == ("Conditional Use Authorization", True)
    assert (cua.citation, cua.source_url) == (
        "app:datasf_planning:2011.0456C",
        "https://example.org/datasf_planning:2011.0456C",
    )
    # a use decision that is not a Conditional Use is listed and marked
    assert by_id["datasf_planning:2016-000777VAR"].conditional_use is False
    # not listed: denied, withdrawn, pending, a referral, building work, an unlabelled record
    for left_out in (CUA_DENIED, CUA_WITHDRAWN, CUA_PENDING, REFERRAL, BUILDING, UNLABELLED):
        assert left_out.app.id not in by_id


def test_site_facts_ignores_records_on_or_after_the_rules_date() -> None:
    """The backtest runs on a past date: what was issued or decided on or after it is not on file yet."""
    s = site_facts(ALL_RECORDS, SITE_995, rules_date=dt.date(2023, 3, 1))
    assert s.licence_types == ("20", "41")  # the Type 47 issued in 2024 is not there yet
    assert [d.record_id for d in s.prior_decisions] == [  # nor is the case's own decision of 2023-09-14
        "datasf_planning:2018-001234CUA",
        "datasf_planning:2016-000777VAR",
        "datasf_planning:2011.0456C",
    ]
    # the date itself is "on or after": a record dated on the rules date is ignored, the day before is read
    on_the_day = site_facts(ALL_RECORDS, SITE_995, rules_date=dt.date(2019, 4, 11))
    assert "datasf_planning:2018-001234CUA" not in [d.record_id for d in on_the_day.prior_decisions]
    day_after = site_facts(ALL_RECORDS, SITE_995, rules_date=dt.date(2019, 4, 12))
    assert day_after.prior_decisions[0].record_id == "datasf_planning:2018-001234CUA"
    issued_on_the_day = site_facts([TYPE_41], SITE_995, rules_date=dt.date(2015, 3, 1))
    assert issued_on_the_day.licences == () and issued_on_the_day.existing_use is None
    assert site_facts([TYPE_41], SITE_995, rules_date=dt.date(2015, 3, 2)).existing_use == "restaurant"
    # before anything was on file
    early = site_facts(ALL_RECORDS, SITE_995, rules_date=dt.date(2000, 1, 1))
    assert (early.licences, early.prior_decisions, early.existing_use) == ((), (), None)
    assert [line.text for line in early.existing_use_lines] == [
        LEGAL_BASIS["zoning.existing_use/none"].text.format(
            address="995 Valencia St", types="41, 42, 47, 48, 61, 75"
        )
    ]


def test_site_facts_reads_a_decision_at_its_decision_date_not_its_filing_date() -> None:
    """Filed before the rules date and decided after it: not an earlier decision on that date."""
    s = site_facts([CUA_2019], SITE_995, rules_date=dt.date(2018, 6, 1))
    assert s.prior_decisions == ()
    # an approved record with no decision date is read at its filing date; one with no date at all is kept last
    filed_only = decision("2005.0008C", decided=None, filed=dt.date(2005, 2, 2))
    undated = decision("2004.0009C", decided=None)
    s = site_facts([undated, filed_only, CUA_2012], SITE_995, rules_date=dt.date(2020, 1, 1))
    assert [(d.record_id, d.date) for d in s.prior_decisions] == [
        ("datasf_planning:2011.0456C", dt.date(2012, 9, 6)),
        ("datasf_planning:2005.0008C", dt.date(2005, 2, 2)),
        ("datasf_planning:2004.0009C", None),
    ]


def test_site_facts_ignores_another_address_on_the_same_parcel() -> None:
    s = site_facts([TYPE_48_NEXT_DOOR, CUA_NEXT_DOOR], SITE_995, rules_date=TODAY)
    assert (s.licences, s.prior_decisions, s.existing_use) == ((), (), None)
    with_own = site_facts([TYPE_48_NEXT_DOOR, CUA_NEXT_DOOR, TYPE_41], SITE_995, rules_date=TODAY)
    assert with_own.licence_types == ("41",) and with_own.existing_use == "restaurant"
    # the same records are read when the report is for that other address
    site_999 = site_of("999 Valencia St, San Francisco, CA 94110", "999 VALENCIA ST", "3609/026")
    next_door = site_facts(ALL_RECORDS, site_999, rules_date=TODAY)
    assert next_door.licence_types == ("48",) and next_door.existing_use == "bar"
    assert [d.record_id for d in next_door.prior_decisions] == ["datasf_planning:2009.0007C"]


def test_site_facts_reads_only_active_licences() -> None:
    for status in ("CANCELED", "EXPIRED", "SURRENDERED", "PENDING", "SUSPENDED", ""):
        s = site_facts([licence("700048", "48", status=status)], SITE_995, rules_date=TODAY)
        assert s.licences == () and s.existing_use is None, status
    assert site_facts(
        [licence("700048", "48", status=" active ")], SITE_995, rules_date=TODAY
    ).licence_types == ("48",)


def test_site_facts_without_a_readable_address_reads_nothing() -> None:
    nowhere = site_of("Valencia St & 21st St, San Francisco, CA", None, "3609/026")
    s = site_facts(ALL_RECORDS, nowhere, rules_date=TODAY)
    assert (s.licences, s.prior_decisions, s.existing_use) == ((), (), None)
    assert [line.text for line in s.existing_use_lines] == [
        LEGAL_BASIS["zoning.existing_use/no_address"].text
    ]


def test_site_facts_is_the_same_under_any_record_order() -> None:
    expected = {
        date: site_facts(ALL_RECORDS, SITE_995, rules_date=date)
        for date in (TODAY, dt.date(2023, 3, 1), dt.date(2014, 1, 1))
    }
    rng = random.Random(20261110)
    for _ in range(25):
        shuffled = rng.sample(ALL_RECORDS, len(ALL_RECORDS))
        doubled = shuffled + rng.sample(ALL_RECORDS, 5)  # a record passed twice is read once
        for date, facts in expected.items():
            assert site_facts(shuffled, SITE_995, rules_date=date) == facts
            assert site_facts(doubled, SITE_995, rules_date=date) == facts
            assert site_facts(list(reversed(shuffled)), SITE_995, rules_date=date) == facts


def test_concept_facts_is_the_same_under_any_order_of_stated_uses() -> None:
    p = profile("other", entertainment_kind="place_of_entertainment", licence_type="48", serves_alcohol=True)
    expected = concept_facts(p, stated_uses=["bar", "restaurant", "nighttime_entertainment"])
    assert expected.planning_uses.value == ("bar", "restaurant", "nighttime_entertainment")
    for uses in (
        ["nighttime_entertainment", "restaurant", "bar"],
        ["restaurant", "bar", "nighttime_entertainment", "bar"],
    ):
        assert concept_facts(p, stated_uses=uses) == expected  # type: ignore[arg-type]
    assert concept_facts(p) == concept_facts(p.model_copy())


# ---- the intake prompt ---------------------------------------------------------------------------------
def test_the_intake_prompt_names_every_new_field_and_the_stated_only_rule() -> None:
    text = " ".join(prompts.INTAKE.split())
    from app.models.profile import MODEL_MAY_NOT_SET

    for name in NEW_FIELDS:
        assert name in BusinessProfile.model_fields
        if name in MODEL_MAY_NOT_SET:
            # given only by the applicant's intake answers; the prompt tells the model these are not its to fill
            continue
        assert name in text, name
    assert (
        "Whether the business is part of a chain, how the licence is obtained and the occupant count are not yours to fill"
        in text
    )
    assert "Fill one ONLY when the description (or a clarification answer) states it in words." in text
    assert (
        "Never infer it from what is typical, from the neighbourhood or from the business type, and never put "
        "a guess for it in `assumptions`." in text
    )
    assert 'Null means "not stated"; it never means "no".' in text
    # stated against not stated
    assert (
        'licence type → licence_type null. "We will apply for a new Type 41 licence" states it → licence_type "41".'
        in text
    )
    assert '"Taking over the old laundromat" states what the space was last used as' in text
    assert 'existing_use_stated ["laundromat"]' in text
    assert '"Open late" does not → closing_hour null' in text
    assert "license" not in text.replace("liquor license", "")  # spelt "licence", as the code does


def test_the_intake_prompt_keeps_its_earlier_instructions() -> None:
    text = prompts.INTAKE
    assert text.startswith("STAGE: INTAKE — build the BusinessProfile.")
    assert text.endswith("Call submit_intake_result when done.")
    for kept in (
        '- business_type: wine bar / cocktail bar / brewery taproom / pub → "bar"',
        "- city_slug: set ONLY to one of the supported slugs",
        "- Infer sensible defaults and list each inference in `assumptions`",
        '"Serve until 1am" → closes_after_midnight true, closes_after_2am false.',
        "- Clarify sparingly.",
        "- If clarification answers are provided, incorporate them and set needs_clarification=false.",
    ):
        assert kept in text, kept
    # the examples in the prompt are valid profile values
    p = BusinessProfile(
        business_type="bar",
        licence_type="41",
        alcohol_transaction="new_licence",
        existing_use_stated=["laundromat"],
        closing_hour="01:30",
    )
    f = concept_facts(p)
    assert (f.licence_type.stated, f.alcohol_transaction.stated, f.closing.read_at) == (True, True, 89)
    assert fx.concept_facts(BusinessProfile(business_type="bar")).missing(
        ["licence_type", "alcohol_transaction", "existing_use_stated", "closing"]
    ) == (
        "the licence type",
        "how the liquor licence will be obtained (new, or a transfer from another owner or another location)",
        "what the space was last used as",
        "the closing time",
    )
