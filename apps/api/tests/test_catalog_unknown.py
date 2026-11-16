"""Decision 1 in the older permit checklist: a concept that serves alcohol without saying what (alcohol_type
"unknown"). A catalog licence that depends on what is served never drops out silently and is never picked: the
engine leaves it undetermined, names what is missing, and lists each possible licence with the condition under
which it applies. Beer and wine, and spirits, behave as before. No network, no model.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.catalog import rules
from app.catalog.loader import GENERIC_CITY, GENERIC_STATE, Catalog, get_catalog
from app.core.config import settings
from app.memo.facts import MISSING_PHRASES
from app.models.profile import BusinessProfile, BusinessType
from app.tools.catalog_tool import lookup

POURS = MISSING_PHRASES["alcohol_served"]
BEER_AND_WINE = "only beer and wine are served"
SPIRITS = "spirits are served too"
BUSINESS_TYPES: tuple[BusinessType, ...] = ("bar", "restaurant", "cafe", "hotel", "catering")


def _keys_on_alcohol_type(rule: Any) -> bool:
    return "alcohol_type" in json.dumps(rule)


def _jurisdictions(catalog: Catalog) -> list[tuple[str | None, str | None]]:
    """Every supported city (with its state), every state without a city, and the generic fallback."""
    cities = [(j.state, j.city_slug) for j in catalog.supported_cities]
    states = [(st, None) for st in catalog.states if st != GENERIC_STATE]
    return [*cities, *states, ("ID", None)]


JURISDICTIONS = _jurisdictions(get_catalog())


def _profile(
    state: str | None, city: str | None, business_type: BusinessType, pours: str, **kw: Any
) -> BusinessProfile:
    return BusinessProfile(
        business_type=business_type,
        state=state,
        city_slug=city,
        seats=60,
        square_feet=2500,
        serves_alcohol=True,
        alcohol_type=pours,  # type: ignore[arg-type]
        **kw,
    )


def _ids(profile: BusinessProfile) -> set[str]:
    return {m.id for m in lookup(profile).matches}


@pytest.mark.parametrize("business_type", BUSINESS_TYPES)
@pytest.mark.parametrize(("state", "city"), JURISDICTIONS, ids=[f"{s}-{c}" for s, c in JURISDICTIONS])
def test_unknown_pours_leave_the_licence_undetermined_never_dropped_nor_picked(
    state: str | None, city: str | None, business_type: BusinessType
) -> None:
    beer = _ids(_profile(state, city, business_type, "beer_wine"))
    spirits = _ids(_profile(state, city, business_type, "full_liquor"))
    out = lookup(_profile(state, city, business_type, "unknown"))
    # what applies whatever is served is a match; what depends on it is undetermined, never a match
    assert {m.id for m in out.matches} == beer & spirits
    assert {u.id for u in out.undetermined} == beer ^ spirits
    # nothing silently drops out: every licence of either reading is a match or undetermined
    assert beer | spirits == {m.id for m in out.matches} | {u.id for u in out.undetermined}
    for u in out.undetermined:
        assert u.missing == [POURS]
        assert u.applies_if == (BEER_AND_WINE if u.id in beer else SPIRITS)
    if out.undetermined:
        note = out.undetermined_note
        assert note is not None
        assert note.startswith(f"Not determined: the description does not say {POURS}.")
        for u in out.undetermined:
            assert f"{u.name} ({u.issuing_agency}; applies if {u.applies_if})" in note
    else:
        assert out.undetermined_note is None


# The jurisdictions whose catalog files key on alcohol_type, read with a bar and a restaurant: the alcohol licence
# is undetermined there, and the missing fact is named.
NAMED = [
    ("CO", "denver", "den."),
    ("WA", "seattle", "wa."),
    ("NY", "new_york_city", "ny."),
    ("FL", "miami", "fl."),
    ("TX", "austin", "tx."),
    ("TX", "houston", "tx."),
    ("CO", None, "co."),
    ("CA", "san_francisco", "ca."),
    ("CA", "los_angeles", "ca."),
    ("CA", "san_diego", "ca."),
]


@pytest.mark.parametrize(("state", "city", "prefix"), NAMED, ids=[f"{s}-{c}" for s, c, _ in NAMED])
@pytest.mark.parametrize("business_type", ("bar", "restaurant"))
def test_the_alcohol_licence_is_undetermined_where_the_catalog_keys_on_what_is_served(
    state: str, city: str | None, prefix: str, business_type: BusinessType
) -> None:
    out = lookup(_profile(state, city, business_type, "unknown"))
    alcohol = [u for u in out.undetermined if u.category == "alcohol" and u.id.startswith(prefix)]
    assert alcohol, "the alcohol licence must be listed as undetermined"
    assert {u.applies_if for u in alcohol} == {BEER_AND_WINE, SPIRITS}  # both possible licences are listed
    assert not any(m.id in {u.id for u in alcohol} for m in out.matches)
    assert out.undetermined_note is not None and POURS in out.undetermined_note


def test_every_catalog_file_that_keys_on_what_is_served_is_read_with_unknown() -> None:
    """The cities and states above cover every catalog file whose rules read alcohol_type."""
    catalog = get_catalog()
    keyed: set[str] = set()
    for path in sorted(settings.CATALOG_DIR.rglob("*.json")):
        doc = json.loads(path.read_text())
        if any(_keys_on_alcohol_type(p["applies_when"]) for p in doc["permits"]):
            keyed.add(path.stem)
    assert keyed == {"denver", "san_francisco", "ca", "co", "fl", "ny", "tx", "wa"}
    covered: set[str] = set()
    for state, city, _ in NAMED:
        for business_type in BUSINESS_TYPES:
            late = _profile(state, city, business_type, "unknown", closes_after_2am=True)
            for u in [
                *lookup(_profile(state, city, business_type, "unknown")).undetermined,
                *lookup(late).undetermined,
            ]:
                p = catalog.get(u.id)
                assert p is not None
                covered.add(p.id.split(".", 1)[0])
    # every file's prefix: den (denver), sf, ca, co, fl, ny, tx, wa
    assert {"den", "sf", "ca", "co", "fl", "ny", "tx", "wa"} <= covered


def test_sf_conditional_use_for_spirits_after_2am_is_undetermined_too() -> None:
    """Not only the licence: the San Francisco Conditional Use rule reads "full liquor and after 2 a.m." for a
    restaurant, so with what is served unknown it is listed as undetermined with its condition."""
    out = lookup(_profile("CA", "san_francisco", "restaurant", "unknown", closes_after_2am=True))
    cua = next(u for u in out.undetermined if u.id == "sf.conditional_use_authorization")
    assert cua.applies_if == SPIRITS and cua.category == "zoning"
    # a bar needs it whatever is served
    assert "sf.conditional_use_authorization" in _ids(_profile("CA", "san_francisco", "bar", "unknown"))


@pytest.mark.parametrize("pours", ["beer_wine", "full_liquor", "none"])
@pytest.mark.parametrize("business_type", BUSINESS_TYPES)
@pytest.mark.parametrize(("state", "city"), JURISDICTIONS, ids=[f"{s}-{c}" for s, c in JURISDICTIONS])
def test_stated_pours_behave_as_before(
    state: str | None, city: str | None, business_type: BusinessType, pours: str
) -> None:
    """Beer and wine, spirits and no alcohol: the matches are exactly the rules' literal matches (the engine
    before decision 1), and nothing is undetermined."""
    profile = _profile(state, city, business_type, pours).model_copy(
        update={"serves_alcohol": pours != "none"}
    )
    prof = profile.normalized().model_dump()
    jur = get_catalog().jurisdiction_for(prof.get("state"), prof.get("city_slug"))
    before = {p.id for p in jur.permits if rules.evaluate(p.applies_when, prof)}
    out = lookup(profile)
    assert {m.id for m in out.matches} == before
    assert out.undetermined == [] and out.undetermined_note is None


def test_a_concept_that_serves_alcohol_without_saying_what_is_unknown_after_normalising() -> None:
    p = BusinessProfile(business_type="bar", state="CA", city_slug="san_francisco", serves_alcohol=True)
    assert p.alcohol_type == "none" and p.normalized().alcohol_type == "unknown"
    out = lookup(p)  # lookup normalises: the bar's licence is undetermined, not Type 42 by default
    assert "ca.abc_type_42" not in {m.id for m in out.matches}
    assert {u.id for u in out.undetermined} >= {"ca.abc_type_42", "ca.abc_type_48"}
    assert GENERIC_CITY not in {u.id for u in out.undetermined}
