"""DataSF sources: parse() against real captured pages (tests/fixtures/datasf_*), fetch() with a mocked API."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from shapely.geometry import Point, shape

from precedent.models import Overlay
from precedent.sources import (
    datasf_business,
    datasf_entertainment,
    datasf_planning,
    datasf_sud,
    datasf_zoning,
    registry,
    socrata,
)
from precedent.sources.base import read_raw

FIX = Path(__file__).parent / "fixtures"
PLANNING = FIX / "datasf_planning" / "planning-sample-p0000.json"
ENTERTAINMENT = FIX / "datasf_entertainment" / "entertainment-sample-p0000.json"
BUSINESS = FIX / "datasf_business" / "business-sample-p0000.json"
ZONING = FIX / "datasf_zoning" / "zoning-sample-p0000.json"
SUD = FIX / "datasf_sud" / "sud-sample-p0000.json"
RULES = Path(datasf_zoning.RULES_FILE)


def in_sf(lat: float | None, lng: float | None) -> bool:
    return lat is not None and lng is not None and 37.70 <= lat <= 37.84 and -122.52 <= lng <= -122.35


def id_shape(source: str, value: str) -> bool:
    return re.fullmatch(rf"{source}:[^:\s]+(?:[^:]*)", value) is not None and value.startswith(f"{source}:")


def test_registry_has_all_datasf_sources() -> None:
    names = set(registry())
    assert {
        "datasf_planning",
        "datasf_entertainment",
        "datasf_business",
        "datasf_zoning",
        "datasf_sud",
    } <= names


@pytest.mark.parametrize(
    "path",
    [PLANNING, PLANNING.with_name(PLANNING.stem + ".parcels.json"), ENTERTAINMENT, BUSINESS, ZONING, SUD],
)
def test_fixtures_are_small_real_envelopes(path: Path) -> None:
    assert path.stat().st_size < 300_000
    meta, data = read_raw(path)
    assert meta["url"].startswith("https://data.sf.gov/resource/") and meta["fetched_at"]
    assert isinstance(data, list) and data


# ---- planning ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def planning() -> dict[str, Any]:
    return {a.source_id: a for a in datasf_planning.parse(PLANNING).applications}


def test_planning_counts_and_ids(planning: dict[str, Any]) -> None:
    _, rows = read_raw(PLANNING)
    assert len(rows) == 24
    # 2023-009707PRL ("install shower grab bar backing") and 2026-008913MIS (non-alcoholic extended hours, no
    # hospitality term once "grab bar" is ignored) are dropped; every CUA is kept.
    assert len(planning) == 22
    assert "2023-009707PRL" not in planning
    assert all(
        id_shape("datasf_planning", a.id) and a.id == f"datasf_planning:{a.source_id}"
        for a in planning.values()
    )
    kinds = {a.kind for a in planning.values()}
    assert kinds == {"cua", "planning_other"}
    assert sum(a.kind == "cua" for a in planning.values()) == 17
    assert planning["1988.393C"].kind == "cua"  # legacy case number, record_type CUA
    assert planning["2026-009124MIS"].kind == "planning_other"
    assert planning["2026-009124MIS"].permit_type == "Miscellaneous Permit"


def test_planning_outcomes(planning: dict[str, Any]) -> None:
    assert planning["1986.572C"].outcome == "denied"  # Closed - Disapproved
    assert planning["2003.1177C"].outcome == "withdrawn"  # Closed - Withdrawn
    assert planning["2024-010647CUA"].outcome == "withdrawn"  # Withdrawn
    assert planning["2014-000692CUA"].outcome == "withdrawn"  # Closed - Cancelled
    assert planning["2014-001343CUA"].outcome == "approved"  # Closed - Approved, no conditions mentioned
    assert planning["1998.186C"].outcome == "approved"  # "...MODIFICATION OF CONDITIONS..." is not an outcome
    assert planning["2026-008352CUA"].outcome == "pending"  # Submitted
    assert planning["2026-006532CUA"].outcome == "pending"  # Pending Review
    assert planning["2026-005503PRV"].outcome == "pending"  # Under Review
    assert planning["2026-008580PRL"].outcome == "unknown"  # Closed
    assert planning["2014-001343CUA"].decided_at == dt.date(2016, 12, 8)
    assert planning["2026-008352CUA"].decided_at is None


def test_planning_status_mapping_table() -> None:
    m = datasf_planning.map_outcome
    assert (
        m("Closed - Approved", "Conditions of approval require a security plan.") == "approved"
    )  # the description's wording is not evidence that conditions were imposed
    assert (
        m("Approved", "Conditional Use Authorization to establish a bar") == "approved"
    )  # "conditional" ≠ conditions
    assert m("Closed - Approval Ltr Issued") == "approved"
    assert m("Disapproved") == "denied"
    assert m("Closed - Cancelled") == "withdrawn"
    assert m("Open") == "pending" and m("Accepted") == "pending" and m("On Hold") == "pending"
    assert m("Appeal Upheld") == "unknown" and m("Closed - Informational") == "unknown"


def test_planning_text_extraction(planning: dict[str, Any]) -> None:
    riptide = planning[
        "2014-001343CUA"
    ]  # "...extension of the Hours of Operation until 2am ... Bar (d.b.a. The Riptide)"
    assert "bar" in riptide.use_types
    assert riptide.hours_close == "02:00" and riptide.late_night is True
    links = planning["2019-012888CUA"]  # restaurant and bar, hours up to 2 a.m., outdoor activity area
    assert set(links.use_types) >= {"bar", "restaurant", "outdoor_seating"}
    assert links.hours_close == "02:00"
    reef = planning["1990.027C"]  # "extend hours of bar (The Reef) from 10p.m. to 2a.m."
    assert reef.hours_close == "02:00"
    assert planning["2026-008055CUA"].use_types == ["restaurant"]
    assert planning["2026-008055CUA"].hours_close is None and planning["2026-008055CUA"].late_night is None


def test_planning_conditions_and_opposition_extraction() -> None:
    row = {
        "record_id": "2099-000001CUA",
        "record_type": "CUA",
        "record_status": "Closed - Approved",
        "description": "Conditional Use Authorization to establish a bar. The bar shall close by 2 a.m. A security plan is required. "
        "Neighbors submitted letters in opposition.",
        "block": "3596",
        "lot": "024",
    }
    app = datasf_planning.parse_row(row, {}, dt.datetime(2026, 10, 21, tzinfo=dt.UTC), "x")
    assert app is not None
    assert app.conditions == ["The bar shall close by 2 a.m.", "A security plan is required."]
    assert app.opposition_noted is True and app.outcome == "approved"
    assert app.parcel == "3596/024" and app.lat is None  # no parcel lookup row → no point


def test_planning_points_and_zoning_from_parcels(planning: dict[str, Any]) -> None:
    with_point = [a for a in planning.values() if a.has_geom]
    assert len(with_point) == 21
    assert all(in_sf(a.lat, a.lng) for a in with_point)
    valencia = planning["1988.393C"]
    assert valencia.parcel and valencia.zoning_district == "NCT-VALENCIA"  # parcel says "NCT" + district name
    assert valencia.extra["neighborhood"] == "Mission"
    assert planning["1994.612C"].zoning_district == "NCD-NORTH BEACH"
    assert planning["2026-008352CUA"].source_url == "https://sfplanninggis.org/pim?search=2026-008352CUA"
    assert planning["2026-008352CUA"].extra["planner"]


def test_planning_block_lot_normalisation() -> None:
    bl = datasf_planning.block_lot
    assert bl({"block": "3596", "lot": "024"}) == ("3596", "024")
    assert bl({"block": "0490", "lot": "002A"}) == ("0490", "002A")
    assert bl({"block": "035", "lot": "0686"}) == ("0686", "035")  # legacy rows store them swapped
    assert bl({"block": None, "lot": "0682"}) is None


def test_planning_parcels_companion_parses_to_nothing() -> None:
    assert len(datasf_planning.parse(PLANNING.with_name(PLANNING.stem + ".parcels.json"))) == 0


def test_planning_where_clause() -> None:
    w = datasf_planning.where_clause(dt.date(2026, 1, 1))
    assert w.startswith("(record_type = 'CUA' OR (record_type in ('PRL'")
    assert "upper(description) like '%RESTAURANT%'" in w and "upper(description) like '%LIQUOR%'" in w
    assert w.endswith("AND (open_date >= '2026-01-01T00:00:00' OR close_date >= '2026-01-01T00:00:00')")


# ---- entertainment ----------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def entertainment() -> dict[str, Any]:
    return {a.source_id: a for a in datasf_entertainment.parse(ENTERTAINMENT).applications}


def test_entertainment_counts_kinds_outcomes(entertainment: dict[str, Any]) -> None:
    assert len(entertainment) == 36
    assert all(a.id == f"datasf_entertainment:{a.source_id}" for a in entertainment.values())
    poe = entertainment["003"]  # 111 Minna Gallery, Place of Entertainment
    assert poe.kind == "entertainment_poe" and poe.outcome == "approved" and poe.status == "Active"
    assert "live_entertainment" in poe.use_types
    assert (
        entertainment["1087"].kind == "entertainment_llp"
        and "live_entertainment" in entertainment["1087"].use_types
    )
    ehp = entertainment["009"]  # SOMArts, Extended Hours Premises only
    assert (
        ehp.kind == "entertainment_other"
        and ehp.late_night is True
        and "live_entertainment" not in ehp.use_types
    )
    assert entertainment["015"].use_types == ["live_entertainment", "bar"]  # The Chieftain Irish Pub
    assert (
        entertainment["079"].kind == "entertainment_poe" and entertainment["079"].late_night is True
    )  # POE + EHP
    assert entertainment["1689"].kind == "entertainment_sound"  # Fixed Place Amplified Sound only
    kinds = ("entertainment_poe", "entertainment_llp", "entertainment_sound", "entertainment_other")
    counts = {k: sum(a.kind == k for a in entertainment.values()) for k in kinds}
    assert counts == {
        "entertainment_poe": 14,
        "entertainment_llp": 5,
        "entertainment_sound": 2,
        "entertainment_other": 15,
    }
    assert all(in_sf(a.lat, a.lng) for a in entertainment.values())


def test_entertainment_mappings() -> None:
    assert datasf_entertainment.kind_for(["FPAS"]) == "entertainment_sound"
    assert datasf_entertainment.kind_for(["MAD", "BP"]) == "entertainment_other"
    assert datasf_entertainment.kind_for(["LLP", "BP"]) == "entertainment_llp"
    m = datasf_entertainment.map_outcome
    assert (m("Active"), m("Approved"), m("Denied"), m("Expired"), m("Revoked"), m("Pending")) == (
        "approved",
        "approved",
        "denied",
        "approved",
        "approved",
        "pending",
    )


# ---- business ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def businesses() -> dict[str, Any]:
    return {b.id: b for b in datasf_business.parse(BUSINESS).businesses}


def test_business_counts_and_flags(businesses: dict[str, Any]) -> None:
    assert len(businesses) == 42
    assert all(re.fullmatch(r"datasf_business:\d{7}-\d{2}-\d{3}-\d{7}", i) for i in businesses)
    casanova = businesses["datasf_business:0309542-01-001-0309542"]  # Casanova Lounge, NAICS 722410
    assert (
        casanova.is_bar
        and casanova.is_food_or_drink
        and casanova.naics_description == "Drinking Places (Alcoholic Beverages)"
    )
    taqueria = businesses["datasf_business:0134378-01-001-0134378"]  # La Taqueria, 722513
    assert taqueria.is_food_or_drink and not taqueria.is_bar
    club = businesses["datasf_business:0090123-02-001-0090123"]  # no 722 NAICS, but BARS/TAVERNS license code
    assert club.is_bar and club.is_food_or_drink
    liquor = businesses["datasf_business:0097307-01-001-0097307"]  # Sonoma Liquor, 445320
    assert not liquor.is_food_or_drink and not liquor.is_bar
    assert sum(b.is_bar for b in businesses.values()) == 10
    assert all(in_sf(b.lat, b.lng) for b in businesses.values())
    assert casanova.address and casanova.address.endswith("San Francisco, CA 94110")


def test_business_bar_name_heuristic() -> None:
    c = datasf_business.classify
    assert c(None, "", "Bourbon & Branch Cocktail Lounge") == (True, True)
    assert c("722515", "", "Juice Bar Collective") == (True, False)
    assert c("722511", "", "Bar Crudo") == (True, True)
    assert c("722511", "", "Memphis Minnie's Bar-B-Q") == (True, False)


# ---- zoning -----------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def zoning() -> dict[str, Overlay]:
    return {o.name: o for o in datasf_zoning.parse(ZONING).overlays}


def test_zoning_rows_dissolved_multipolygons(zoning: dict[str, Overlay]) -> None:
    _, rows = read_raw(ZONING)
    assert len(rows) == 5 and sum(r["zoning"] == "NCT-1" for r in rows) == 2
    assert set(zoning) == {"NCT-1", "NCT-VALENCIA", "RM-1", "HP-RA"}  # one row per code
    for code, o in zoning.items():
        assert o.id == f"datasf_zoning:{code}" and o.kind == "zoning_district" and o.district_codes == [code]
        assert o.geom is not None and o.geom["type"] == "MultiPolygon"
        g = shape(o.geom)
        assert g.is_valid and in_sf(g.centroid.y, g.centroid.x)
    assert len(zoning["NCT-1"].geom["coordinates"]) == 2  # type: ignore[index]


def test_zoning_permissions_and_sections(zoning: dict[str, Overlay]) -> None:
    v = zoning["NCT-VALENCIA"]
    assert (v.bar_permission, v.restaurant_permission) == ("conditional", "principal")
    assert v.code_section.startswith("Planning Code § 762")  # dataset still says 726.1 (pre-renumbering)
    assert v.late_night_rule and "C 2 a.m.–6 a.m." in v.late_night_rule
    assert (zoning["NCT-1"].bar_permission, zoning["NCT-1"].code_section[:20]) == (
        "principal",
        "Planning Code § 750 ",
    )
    assert (zoning["RM-1"].bar_permission, zoning["RM-1"].restaurant_permission) == (
        "prohibited",
        "prohibited",
    )
    hp = zoning["HP-RA"]
    assert hp.bar_permission == "unknown" and "not verified" in hp.code_section


def test_zoning_controls_cover_every_nc_code_with_valid_values() -> None:
    controls = datasf_zoning.zoning_controls()
    for code, c in controls.items():
        assert c["bar_permission"] in {"principal", "conditional", "prohibited", "unknown"}, code
        assert re.fullmatch(r"\d{3}(\.\d+)?", c["section"]), code
    assert (
        controls["NCT-MISSION"]["section"] == "754"
        and controls["NCT-24TH-MISSION"]["restaurant_permission"] == "conditional"
    )
    assert (
        controls["NCD-POLK"]["bar_permission"] == "conditional"
        and controls["NCD-HAIGHT"]["bar_permission"] == "conditional"
    )


# ---- SUD --------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def suds() -> dict[str, Overlay]:
    return {o.id: o for o in datasf_sud.parse(SUD).overlays}


def test_sud_rows_kinds_sections_geoms(suds: dict[str, Overlay]) -> None:
    assert len(suds) == 4  # 5 polygons, Waterfront 3 dissolved
    mission = suds["datasf_sud:mission_alcohol_restrict"]
    assert mission.kind == "alcohol_sud" and mission.name == "Mission Alcoholic Beverage Special Use District"
    assert (
        mission.code_section.startswith("Planning Code § 249.60") and mission.bar_permission == "conditional"
    )
    assert mission.geom and mission.geom["type"] == "MultiPolygon"
    # 2969 24th St (inside the Mission SUD) / 1500 Haight St (inside the Haight RUSD)
    assert shape(mission.geom).covers(Point(-122.4116, 37.7527))
    haight = suds["datasf_sud:haight_street_alcohol_restricted_use"]
    assert haight.kind == "alcohol_sud" and haight.code_section == "Planning Code § 781.9"
    assert haight.geom and shape(haight.geom).covers(Point(-122.4467, 37.7701))
    japantown = suds["datasf_sud:japantown"]
    assert japantown.kind == "special_use_district" and japantown.code_section == "Planning Code § 249.31"
    waterfront = suds["datasf_sud:waterfront_3"]
    assert waterfront.code_section == "Planning Code § 240.3" and waterfront.source_url.startswith(
        "https://codelibrary.amlegal.com/"
    )
    assert len(waterfront.geom["coordinates"]) >= 1  # type: ignore[index]
    assert all(o.code_section for o in suds.values())


def test_sud_unknown_name_stays_unresolved_with_dataset_url() -> None:
    row = {"name": "Brand New SUD", "url": "https://codelibrary.amlegal.com/codes/x#rid-1", "the_geom": None}
    o = datasf_sud.overlay_for("Brand New SUD", [row], dt.datetime(2026, 10, 28, tzinfo=dt.UTC))
    assert o.code_section == datasf_sud.UNRESOLVED and "section not resolved" in o.code_section
    assert o.source_url == row["url"] and "not resolved" in o.rules


def test_alcohol_and_entertainment_suds_all_have_a_section() -> None:
    aliases = datasf_zoning.rules_doc().get("sud_name_aliases", {})
    fetched = dt.datetime(2026, 10, 28, tzinfo=dt.UTC)
    for name in datasf_sud.ALCOHOL_ENTERTAINMENT_SUDS:
        assert name in datasf_sud.SUD_SECTIONS or name in aliases, name
        o = datasf_sud.overlay_for(name, [], fetched)
        assert o.code_section.startswith("Planning Code § ") and "not resolved" not in o.code_section, name
    # every name matching the alcohol pattern is in the list
    _, names = read_raw(FIX / "datasf_sud" / "sud-names-2026-10-28.json")
    alcohol = {n for n in names if re.search(r"alcohol|liquor|beverage", n, re.I)}
    assert alcohol <= set(datasf_sud.ALCOHOL_ENTERTAINMENT_SUDS)


def test_every_live_sud_name_resolves() -> None:
    """Distinct names in DataSF 5yf5-ms5f as of 2026-10-28 (117): none should fall back to 'not resolved'."""
    aliases = datasf_zoning.rules_doc().get("sud_name_aliases", {})
    _, names = read_raw(FIX / "datasf_sud" / "sud-names-2026-10-28.json")
    assert len(names) == 117
    unresolved = [n for n in names if n not in datasf_sud.SUD_SECTIONS and n not in aliases]
    assert unresolved == []
    expired = datasf_sud.overlay_for(
        "Central Subway Tunnel Boring Machine Extraction Site", [], dt.datetime.now(dt.UTC)
    )
    assert expired.code_section == "Planning Code § 249.70 (expired 4/5/2018; Ord. 33-13)"


# ---- static rules file --------------------------------------------------------------------------------------
def test_static_rules_rows_valid_and_unique_nc_attachment() -> None:
    doc = json.loads(RULES.read_text())
    rows = [Overlay.model_validate(o) for o in doc["overlays"]]
    seen: dict[str, str] = {}
    for o in rows:
        if o.kind == "nc_rule":
            for code in o.district_codes:
                assert code not in seen, f"{code} attached to {seen.get(code)} and {o.id}"
                seen[code] = o.id
                assert code in doc["zoning_controls"], code
    by_id = {o.id: o for o in rows}
    assert by_id["static:sf:mission_alcoholic_beverage_sud"].code_section.startswith("Planning Code § 249.60")
    assert by_id["static:sf:third_street_alcohol_rud"].code_section.startswith("Planning Code § 249.62")
    assert by_id["static:sf:haight_street_alcohol_rusd"].code_section == "Planning Code § 781.9"
    assert by_id["static:sf:lower_haight_alcohol_rud"].code_section == "Planning Code § 784"
    for alias, rid in doc["sud_name_aliases"].items():
        assert rid in by_id, alias
    for code in (
        "NCT-VALENCIA",
        "NCT-MISSION",
        "NCT-24TH-MISSION",
        "NCD-POLK",
        "NCD-HAIGHT",
        "NCD-NORTH BEACH",
    ):
        assert code in seen


# ---- fetch (mocked) -----------------------------------------------------------------------------------------
@respx.mock
async def test_planning_fetch_writes_page_and_parcel_companion(tmp_path: Path) -> None:
    _, rows = read_raw(PLANNING)
    _, parcels = read_raw(PLANNING.with_name(PLANNING.stem + ".parcels.json"))
    page_route = respx.get(socrata.dataset_url(datasf_planning.DATASET_ID)).mock(
        return_value=httpx.Response(200, json=rows)
    )
    parcel_route = respx.get(socrata.dataset_url(datasf_planning.PARCELS_DATASET_ID)).mock(
        return_value=httpx.Response(200, json=parcels)
    )
    async with httpx.AsyncClient() as client:
        paths = await datasf_planning.fetch(client, tmp_path, dt.date(2026, 1, 1))
    assert len(paths) == 1 and page_route.call_count == 1 and parcel_route.call_count == 1
    assert "open_date" in str(page_route.calls[0].request.url)
    companion = datasf_planning.parcels_path(paths[0])
    assert companion.exists() and read_raw(companion)[0]["kind"] == "parcel_lookup"
    batch = datasf_planning.parse(paths[0])
    assert len(batch.applications) == 22 and sum(a.has_geom for a in batch.applications) == 21


@respx.mock
async def test_zoning_fetch_one_raw_file_per_code(tmp_path: Path) -> None:
    _, rows = read_raw(ZONING)

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("$group") == "zoning":
            return httpx.Response(200, json=[{"zoning": c} for c in sorted({r["zoning"] for r in rows})])
        code = re.search(r"zoning = '(.+)'", params["$where"]).group(1)  # type: ignore[union-attr]
        return httpx.Response(200, json=[r for r in rows if r["zoning"] == code])

    respx.get(socrata.dataset_url(datasf_zoning.DATASET_ID)).mock(side_effect=handler)
    async with httpx.AsyncClient() as client:
        paths = await datasf_zoning.fetch(client, tmp_path, None)
    assert len(paths) == 4
    names = sorted(o.name for p in paths for o in datasf_zoning.parse(p).overlays)
    assert names == ["HP-RA", "NCT-1", "NCT-VALENCIA", "RM-1"]
