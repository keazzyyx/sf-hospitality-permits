"""Every catalog entry must satisfy the JSON schema, the rule DSL, and the dependency graph."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.catalog import rules
from app.catalog.loader import GENERIC_CITY, GENERIC_STATE, Catalog, get_catalog
from app.core.config import settings
from app.models.profile import BusinessProfile
from app.tools.catalog_tool import lookup
from app.tools.timeline import check_dependencies, tasks_from_permits

DATA = settings.CATALOG_DIR
SCHEMA = json.loads((DATA.parent / "schema" / "permit.schema.json").read_text())
FILES = sorted(p for p in DATA.rglob("*.json"))
REQUIRED_CITIES = {
    "san_francisco",
    "los_angeles",
    "san_diego",
    "new_york_city",
    "austin",
    "houston",
    "miami",
    "chicago",
    "denver",
    "seattle",
}


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return get_catalog()


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(DATA)))
def test_file_matches_schema(path: Path) -> None:
    doc = json.loads(path.read_text())
    errors = sorted(Draft202012Validator(SCHEMA).iter_errors(doc), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors[:10])


def _all_entries() -> list[tuple[str, dict]]:
    out = []
    for path in FILES:
        for p in json.loads(path.read_text())["permits"]:
            out.append((p["id"], p))
    return out


@pytest.mark.parametrize(("pid", "entry"), _all_entries(), ids=lambda x: x if isinstance(x, str) else "")
def test_entry_rules_and_ranges(pid: str, entry: dict) -> None:
    sample = BusinessProfile(business_type="restaurant", seats=60, employees=10).normalized().model_dump()
    # rule must evaluate without raising for a fully populated profile
    assert rules.evaluate(entry["applies_when"], sample) in (True, False)
    assert entry["typical_timeline_days"]["min"] <= entry["typical_timeline_days"]["max"]
    assert entry["fee_range_usd"]["min"] <= entry["fee_range_usd"]["max"]
    assert entry["application_url"].startswith("https://")
    assert pid not in entry["prerequisites"]


def test_ids_unique_and_prereqs_resolve(catalog: Catalog) -> None:
    ids = [pid for pid, _ in _all_entries()]
    assert len(ids) == len(set(ids)), "duplicate permit ids"
    for p in catalog.permits.values():
        for pre in p.prerequisites:
            assert pre in catalog.permits, f"{p.id} requires unknown {pre}"


def test_whole_catalog_is_acyclic(catalog: Catalog) -> None:
    report = check_dependencies(tasks_from_permits(list(catalog.permits.values())))
    assert report.cycles == []


def test_required_cities_present(catalog: Catalog) -> None:
    present = {j.city_slug for j in catalog.supported_cities}
    missing = REQUIRED_CITIES - present
    assert not missing, f"missing city catalogs: {sorted(missing)}"
    for slug in REQUIRED_CITIES:
        jur, permits = catalog.cities[slug]
        assert len(permits) >= 12, f"{slug} has only {len(permits)} permits"
        cats = {p.category for p in permits}
        for needed in {
            "health",
            "building",
            "zoning",
            "entertainment",
            "outdoor_dining",
            "hotel",
            "mobile_vending",
        }:
            assert needed in cats, f"{slug} lacks a {needed} permit"
        assert jur.state in catalog.states, f"{slug}: state file {jur.state} missing"


def test_each_state_has_alcohol_and_tax(catalog: Catalog) -> None:
    for st, (_, permits) in catalog.states.items():
        if st == GENERIC_STATE:
            continue
        cats = {p.category for p in permits}
        assert "alcohol" in cats, f"{st} lacks alcohol licenses"
        assert cats & {"state_tax", "business_registration"}, f"{st} lacks registration/tax"


def test_city_resolution(catalog: Catalog) -> None:
    assert catalog.resolve_city("SF Mission") == "san_francisco"
    assert catalog.resolve_city("opening in Brooklyn next spring") == "new_york_city"
    assert catalog.resolve_city("Wynwood") == "miami"
    assert catalog.resolve_city("Boise, Idaho") is None


def test_sf_wine_bar_requirements(catalog: Catalog) -> None:
    profile = BusinessProfile(
        business_type="bar",
        city_name="SF Mission",
        city_slug="san_francisco",
        state="CA",
        seats=40,
        serves_alcohol=True,
        alcohol_type="beer_wine",
        closes_after_midnight=True,
        live_entertainment=True,
        amplified_sound=True,
        cooking_type="limited",
    )
    ids = {m.id for m in lookup(profile).matches}
    for expected in {
        "us.ein",
        "ca.sellers_permit",
        "ca.abc_type_42",
        "sf.business_registration",
        "sf.health_permit",
        "sf.conditional_use_authorization",
        "sf.place_of_entertainment_permit",
        "sf.fog_wastewater_permit",
        "us.ascap_license",
    }:
        assert expected in ids
    assert "ca.abc_type_47" not in ids
    assert "sf.limited_live_performance_permit" not in ids  # late shows → POE instead
    assert "sf.tot_certificate_of_authority" not in ids


def test_unsupported_city_falls_back(catalog: Catalog) -> None:
    profile = BusinessProfile(business_type="restaurant", city_name="Boise", state="ID", seats=50)
    out = lookup(profile)
    assert out.city_supported is False
    ids = {m.id for m in out.matches}
    assert (
        "us.ein" in ids
        and any(i.startswith("gens.") for i in ids)
        and any(i.startswith("genc.") for i in ids)
    )
    # supported state, unsupported city → real state items + generic city
    profile = BusinessProfile(business_type="restaurant", city_name="Oakland", state="CA", seats=50)
    ids = {m.id for m in lookup(profile).matches}
    assert (
        "ca.sellers_permit" in ids
        and "genc.food_service_permit" in ids
        and not any(i.startswith("sf.") for i in ids)
    )
    assert GENERIC_CITY not in {j.city_slug for j in catalog.supported_cities}


def test_context_text_is_deterministic(catalog: Catalog) -> None:
    a = catalog.context_text("CA", "san_francisco")
    b = Catalog(settings.CATALOG_DIR).context_text("CA", "san_francisco")
    assert a == b and len(a) > 5000
