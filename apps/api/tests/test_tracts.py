"""app.memo.tracts: which census tract a point is in, and the tract's licence concentration.

Everything runs on the two bundled files. Two tests read something else and skip when it is not on this machine:
ABC's authorisations CSV under docs/validation, and the local table `abc_export_sf`.
"""

from __future__ import annotations

import csv
import dataclasses
import itertools
import math
import os
from pathlib import Path
from typing import Any, get_args

import pytest
from precedent.sources.abc import LICENSE_TYPES

from app.memo import tracts
from app.memo.tracts import (
    KINDS,
    OFF_SALE_RETAIL_TYPES,
    ON_SALE_RETAIL_TYPES,
    ON_SALE_TYPES_EXCLUDED_BY_STATUTE,
    PCN_CITATION,
    PCN_SENTENCE,
    Concentration,
    ConcentrationFinding,
    ExportRow,
    LicenceCounts,
    concentration,
    concentration_line,
    count_licences,
    is_over,
    normalise_tract,
    over_concentration_finding,
    plain_date,
    tract_at,
)
from app.models.profile import AlcoholTransaction

REPO = Path(__file__).resolve().parents[3]
AUTHORISATIONS_CSV = REPO / "docs" / "validation" / "abc-census-tract-authorizations-sf-2026-09.csv"
LOCAL_DB = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres@localhost:55433/sfhp_local")

# 995 Valencia St as the local database holds it (applications.geom, sources abc and datasf_planning).
VALENCIA_995 = (37.757083, -122.420838)
# One degree of latitude and of longitude at San Francisco, in metres: enough to step a few metres.
M_PER_DEG_LAT = 111_000.0
M_PER_DEG_LNG = 88_000.0


def a_concentration(active: int, authorised: int, **changes: Any) -> Concentration:
    base = Concentration(
        tract="208.01",
        kind="on_sale",
        authorised=authorised,
        active=active,
        population=3618,
        authorised_as_of="2026-09",
        active_as_of="2026-11-09",
        authorised_source="ABC Census Tract Authorizations",
        active_source="ABC Daily Data Export",
    )
    return dataclasses.replace(base, **changes)


# ---- tract_at -------------------------------------------------------------------------------------------------


def test_995_valencia_is_in_tract_208_01() -> None:
    assert tract_at(*VALENCIA_995) == "208.01"
    assert tract_at(37.75795, -122.42107) == "208.01"  # the approximate point in the task note


def test_995_valencia_tract_figures() -> None:
    """The Step 3 write-up: population 3,618, authorised 12 on-sale and 3 off-sale, about 27 active on-sale."""
    on = concentration("208.01", "on_sale")
    off = concentration("208.01", "off_sale")
    assert on is not None and off is not None
    assert (on.population, on.authorised, off.authorised) == (3618, 12, 3)
    # 28 with the statute's list: the 27 of the write-up (Types 41, 47, 48) and one Type 90 music venue
    assert on.active == 28
    assert on.over is True
    assert (off.active, off.over) == (6, True)
    assert (on.authorised_as_of, on.active_as_of) == ("2026-09", "2026-11-09")
    assert "Census Tract Authorizations" in on.authorised_source
    assert "Daily Data Export" in on.active_source


def test_points_on_either_side_of_valencia_street() -> None:
    """Valencia Street's centre line is the boundary between 208.01 (east) and 207.01 (west) at 21st Street."""
    lat, lng = VALENCIA_995
    assert tract_at(lat, lng + 20 / M_PER_DEG_LNG) == "208.01"
    assert tract_at(lat, lng - 15 / M_PER_DEG_LNG) == "208.01"  # still the east side of the street
    assert tract_at(lat, lng - 40 / M_PER_DEG_LNG) == "207.01"
    assert tract_at(lat, lng - 60 / M_PER_DEG_LNG) == "207.01"
    # and north along Valencia the tract changes to 208.02
    assert tract_at(lat + 200 / M_PER_DEG_LAT, lng) == "208.01"
    assert tract_at(lat + 400 / M_PER_DEG_LAT, lng) == "208.02"


def test_every_tract_has_its_own_side_of_its_longest_edge() -> None:
    """For each of the 244 tracts: 1.5 m either side of the middle of its longest boundary edge, exactly one
    point is in the tract and the other is in a neighbour or outside the county."""
    shapes = tracts._shapes()
    assert len(shapes) == 244
    for shape in shapes:
        ring = max((polygon[0] for polygon in shape.polygons), key=len)
        edges = [
            (math.hypot((x2 - x1) * M_PER_DEG_LNG, (y2 - y1) * M_PER_DEG_LAT), x1, y1, x2, y2)
            for (x1, y1), (x2, y2) in itertools.pairwise(ring)
        ]
        length, x1, y1, x2, y2 = max(edges)
        normal_x = -(y2 - y1) * M_PER_DEG_LAT / length
        normal_y = (x2 - x1) * M_PER_DEG_LNG / length
        mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
        sides = [
            tract_at(
                mid_y + sign * normal_y * 1.5 / M_PER_DEG_LAT, mid_x + sign * normal_x * 1.5 / M_PER_DEG_LNG
            )
            for sign in (1, -1)
        ]
        assert sides.count(shape.tract) == 1, (shape.tract, sides)


@pytest.mark.parametrize(
    ("place", "lat", "lng"),
    [
        ("Oakland City Hall", 37.8044, -122.2712),
        ("Daly City", 37.6879, -122.4702),
        ("just south of the county line", 37.7060, -122.4500),
        ("Sausalito", 37.8591, -122.4853),
        ("San Francisco Airport (San Mateo County)", 37.6213, -122.3790),
        ("the Bay east of the county line", 37.80, -122.33),
        ("Los Angeles", 34.05, -118.24),
        ("latitude and longitude swapped", -122.420838, 37.757083),
    ],
)
def test_a_point_outside_san_francisco_is_none(place: str, lat: float, lng: float) -> None:
    assert tract_at(lat, lng) is None, place


def test_a_point_that_is_not_a_number_is_none() -> None:
    assert tract_at(math.nan, -122.42) is None
    assert tract_at(37.75, math.inf) is None


@pytest.mark.parametrize(
    ("place", "lat", "lng", "tract"),
    [
        ("just north of the county line", 37.7100, -122.4500, "262.01"),
        ("City Hall", 37.7793, -122.4193, "124.05"),
        ("Ferry Building", 37.7955, -122.3937, "105.00"),
        ("Treasure Island", 37.8235, -122.3706, "179.03"),
        ("Farallon Islands", 37.6989, -123.0034, "9804.01"),
        ("the Pacific inside the county (a water tract)", 37.76, -122.56, "9901.00"),
    ],
)
def test_known_points_inside_the_county(place: str, lat: float, lng: float, tract: str) -> None:
    assert tract_at(lat, lng) == tract, place


def test_the_same_point_gives_the_same_tract_every_time() -> None:
    assert {tract_at(*VALENCIA_995) for _ in range(5)} == {"208.01"}


# ---- the two files agree with each other and say where they came from ----------------------------------------


def test_every_tract_abc_lists_has_a_polygon_and_the_reverse() -> None:
    figures, polygons = tracts.tracts_with_figures(), tracts.tracts_with_polygon()
    assert len(figures) == 244
    assert tracts.tracts_without_polygon() == ()  # none missing
    assert set(polygons) == set(figures)  # and no polygon without figures
    assert figures == polygons  # both in number order
    assert figures[0] == "101.01" and figures[-1] == "9902.00"


def test_the_boundary_file_names_its_source_vintage_and_download_date() -> None:
    source = tracts.boundary_source()
    assert source["url"] == "https://www2.census.gov/geo/tiger/TIGER2020/TRACT/tl_2020_06_tract.zip"
    assert "2020" in source["vintage"]
    assert source["downloaded_on"] == "2026-11-10"
    assert len(source["sha256"]) == 64


def test_the_figures_file_names_both_sources_and_dates() -> None:
    source = tracts.licence_figures_source()
    assert source["authorised"]["as_of"] == "2026-09"
    assert source["active"]["export_date"] == "2026-11-09"
    assert source["active"]["on_sale_types"] == sorted(ON_SALE_RETAIL_TYPES)
    assert source["active"]["off_sale_types"] == sorted(OFF_SALE_RETAIL_TYPES)
    assert (
        source["authorised"]["people_per_on_sale_licence"],
        source["authorised"]["people_per_off_sale_licence"],
    ) == (
        288,
        1183,
    )


def test_authorised_is_population_over_the_county_figure_rounded_down() -> None:
    """What makes "active > authorised" the same test as the statute's ratio against ratio."""
    per = {"on_sale": 288, "off_sale": 1183}
    for tract in tracts.tracts_with_figures():
        for kind in KINDS:
            c = concentration(tract, kind)
            assert c is not None
            assert c.authorised == c.population // per[kind], (tract, kind)
            # licences / population exceeds 1 / county figure  <=>  licences > authorised
            assert c.over == (c.active * per[kind] > c.population), (tract, kind)


def test_how_many_tracts_are_over() -> None:
    """Pinned from the bundled figures (export of 2026-11-09). Step 3 found 74 and 98 on a shorter on-sale list."""
    over = {
        kind: sum(
            1 for t in tracts.tracts_with_figures() if (c := concentration(t, kind)) is not None and c.over
        )
        for kind in KINDS
    }
    assert over == {"on_sale": 78, "off_sale": 98}


def test_the_figures_equal_abcs_csv() -> None:
    if not AUTHORISATIONS_CSV.exists():
        pytest.skip("ABC's authorisations CSV is not on this machine")
    with AUTHORISATIONS_CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 244
    assert {normalise_tract(r["census_tract"]) for r in rows} == set(tracts.tracts_with_figures())
    for r in rows:
        on = concentration(r["census_tract"], "on_sale")
        off = concentration(r["census_tract"], "off_sale")
        assert on is not None and off is not None
        assert on.population == off.population == int(r["tract_population"])
        assert on.authorised == int(r["authorized_on_sale"])
        assert off.authorised == int(r["authorized_off_sale"])


def test_the_counts_equal_a_fresh_count_from_the_local_table() -> None:
    """Skipped when the local database is not reachable, or holds a different export from the bundled file."""
    psycopg = pytest.importorskip("psycopg")
    try:
        conn = psycopg.connect(LOCAL_DB, connect_timeout=2)
    except psycopg.Error as exc:
        pytest.skip(f"local database not reachable: {type(exc).__name__}")
    with conn:
        try:
            dates = [r[0].isoformat() for r in conn.execute("select distinct export_date from abc_export_sf")]
            rows = [
                ExportRow(*r)
                for r in conn.execute(
                    "select census_tract, file_number, license_type, lic_or_app, type_status from abc_export_sf"
                )
            ]
        except psycopg.Error as exc:
            pytest.skip(f"table abc_export_sf not readable: {type(exc).__name__}")
    bundled = tracts.licence_figures_source()["active"]["export_date"]
    if dates != [bundled]:
        pytest.skip(
            f"the local table holds the export of {dates}, the bundled file that of {bundled}: rebuild with "
            "scripts/validation/build_tract_data.py licences"
        )
    fresh = count_licences(rows)
    listed = set(tracts.tracts_with_figures())
    for tract in listed:
        want = fresh.get(tract, LicenceCounts())
        for kind in KINDS:
            c = concentration(tract, kind)
            assert c is not None
            assert c.active == want.active(kind), (tract, kind)
            assert c.issued_not_active == want.issued_not_active(kind), (tract, kind)
    # every licence the count found is either in a listed tract or in the file's "not placed" section
    not_placed = tracts._licence_data()["not_placed"]
    assert set(not_placed) == set(fresh) - listed
    for kind in KINDS:
        total = sum(c.active(kind) for c in fresh.values())
        in_file = sum(c.active for t in listed if (c := concentration(t, kind)) is not None) + sum(
            int(v[f"active_{kind}"]) for v in not_placed.values()
        )
        assert total == in_file, kind


# ---- which licences count -------------------------------------------------------------------------------------


def test_off_sale_is_the_statutes_closed_list() -> None:
    assert frozenset({"20", "21"}) == OFF_SALE_RETAIL_TYPES


def test_on_sale_leaves_out_the_nine_types_the_statute_excludes() -> None:
    assert (
        frozenset({"43", "44", "45", "46", "53", "54", "55", "56", "62"}) == ON_SALE_TYPES_EXCLUDED_BY_STATUTE
    )
    assert not ON_SALE_RETAIL_TYPES & ON_SALE_TYPES_EXCLUDED_BY_STATUTE
    assert not ON_SALE_RETAIL_TYPES & OFF_SALE_RETAIL_TYPES


def test_on_sale_is_every_on_sale_title_on_abcs_list_less_the_nine() -> None:
    """Every type ABC titles "On-Sale" is counted or is one of the nine; the types counted without "On-Sale" in
    the title are the club, bed-and-breakfast and brewpub licences."""
    titled = {code for code, title in LICENSE_TYPES.items() if "on-sale" in title.lower()}
    assert titled <= ON_SALE_RETAIL_TYPES | ON_SALE_TYPES_EXCLUDED_BY_STATUTE
    assert titled >= ON_SALE_TYPES_EXCLUDED_BY_STATUTE
    assert ON_SALE_RETAIL_TYPES - titled == {"51", "52", "67", "75", "80"}
    assert set(LICENSE_TYPES) >= ON_SALE_RETAIL_TYPES


@pytest.mark.parametrize("permit", ["58", "66", "68", "77", "86", "85", "02", "23", "17"])
def test_permits_and_non_retail_types_are_not_counted(permit: str) -> None:
    assert permit not in ON_SALE_RETAIL_TYPES | OFF_SALE_RETAIL_TYPES


@pytest.mark.parametrize(
    ("licence_type", "kind"),
    [("41", "on_sale"), ("47", "on_sale"), ("48", "on_sale"), ("90", "on_sale"), (" 42 ", "on_sale"),
     ("21", "off_sale"), ("20", "off_sale"), ("58", None), ("54", None), ("85", None), ("2", None), ("", None),
     (None, None)],
)  # fmt: skip
def test_kind_for_licence_type(licence_type: str | None, kind: str | None) -> None:
    assert tracts.kind_for_licence_type(licence_type) == kind


def test_the_test_applies_to_a_new_licence_or_a_premises_transfer_only() -> None:
    """§ 23958.4(a): "an original or premises-to-premises transfer of any retail license"."""
    assert frozenset({"new_licence", "premises_transfer"}) == tracts.TRANSACTIONS_TESTED
    assert set(get_args(AlcoholTransaction)) >= tracts.TRANSACTIONS_TESTED


def row(
    tract: str | None, file: str, licence_type: str, record: str = "LIC", status: str = "ACTIVE"
) -> ExportRow:
    return ExportRow(tract, file, licence_type, record, status)


def test_licences_are_counted_not_rows() -> None:
    counts = count_licences(
        [
            row("0208.01", "00478662", "47"),
            row("0208.01", "00478662", "47"),  # a duplicate licence on the same file
            row("0208.01", "00478662", "58"),  # its caterer's permit: not a retail licence
            row("0208.01", "00578934", "48"),
            row("0208.01", "00565850", "21"),
        ]
    )
    assert counts == {"208.01": LicenceCounts(active_on_sale=2, active_off_sale=1)}


def test_a_file_with_an_on_sale_and_an_off_sale_licence_counts_once_in_each() -> None:
    counts = count_licences([row("0105.00", "1", "21"), row("0105.00", "1", "47"), row("0105.00", "1", "41")])
    assert counts == {"105.00": LicenceCounts(active_on_sale=1, active_off_sale=1)}


def test_applications_and_pending_rows_are_not_licences() -> None:
    counts = count_licences(
        [
            row("0208.01", "1", "41", record="APP", status="ACTIVE"),  # an application row, no issue date
            row("0208.01", "2", "41", record="APP", status="PEND"),
            row("0208.01", "3", "41", record="LIC", status="PEND"),
            row("0208.01", "4", "41"),
        ]
    )
    assert counts == {"208.01": LicenceCounts(active_on_sale=1)}


def test_suspended_and_surrendered_licences_are_issued_not_active() -> None:
    counts = count_licences(
        [
            row("0208.01", "1", "47", status="R64B"),
            row("0208.01", "2", "41", status="SUSPEN"),
            row("0208.01", "3", "21", status="SUREND"),
            row("0208.01", "4", "20", status="REVPEN"),
            row("0208.01", "5", "48"),
            row("0208.01", "5", "48", status="SUSPEN"),  # the same file is active on another row: active only
        ]
    )
    assert counts == {
        "208.01": LicenceCounts(
            active_on_sale=1, active_off_sale=0, issued_not_active_on_sale=2, issued_not_active_off_sale=2
        )
    }


def test_excluded_types_and_other_types_count_nowhere() -> None:
    rows = [
        row("0105.00", str(n), t)
        for n, t in enumerate(["54", "45", "62", "58", "66", "68", "85", "86", "02"])
    ]
    assert count_licences(rows) == {}


def test_a_blank_or_older_tract_number_is_kept_apart() -> None:
    counts = count_licences(
        [row("", "1", "41"), row(None, "2", "41"), row("0208.00", "3", "41"), row("208.01", "4", "41")]
    )
    assert counts == {
        "": LicenceCounts(active_on_sale=2),
        "208.00": LicenceCounts(active_on_sale=1),
        "208.01": LicenceCounts(active_on_sale=1),
    }


def test_older_tract_numbers_are_reported_beside_the_count_not_inside_it() -> None:
    """The export has one active on-sale licence under "208.00", a number ABC's report no longer lists."""
    c = concentration("208.01", "on_sale")
    assert c is not None
    assert c.older_number_not_placed == 1
    assert c.active == 28  # unchanged by it


@pytest.mark.parametrize(
    ("given", "want"),
    [
        ("0208.01", "208.01"),
        ("208.01", "208.01"),
        (" 103 ", "103.00"),
        ("0103.00", "103.00"),
        ("020801", "208.01"),
        ("980401", "9804.01"),
        ("9809", "9809.00"),
        ("", None),
        (None, None),
        ("N/A", None),
        ("208.011", None),
        ("-1", None),
    ],
)
def test_normalise_tract(given: str | None, want: str | None) -> None:
    assert normalise_tract(given) == want


# ---- the over rule and the report row -------------------------------------------------------------------------


def test_the_over_rule_at_the_boundary() -> None:
    """§ 23958.4(a): the tract's ratio "exceeds" the county's. Equal to the authorised number is not over."""
    assert is_over(11, 12) is False
    assert is_over(12, 12) is False
    assert is_over(13, 12) is True
    assert is_over(0, 0) is False
    assert is_over(1, 0) is True


def test_a_tract_exactly_at_its_number_is_not_over_and_prints_nothing() -> None:
    at = a_concentration(active=12, authorised=12)
    assert at.over is False
    assert over_concentration_finding(at) is None
    one_more = a_concentration(active=13, authorised=12)
    assert one_more.over is True
    assert over_concentration_finding(one_more) is not None


def test_a_real_tract_exactly_at_its_number_is_not_over() -> None:
    at_limit = [
        c
        for t in tracts.tracts_with_figures()
        if (c := concentration(t, "on_sale")) is not None and c.active == c.authorised
    ]
    assert at_limit, "the bundled figures have tracts exactly at their authorised number"
    assert all(not c.over and over_concentration_finding(c) is None for c in at_limit)


def test_the_fixed_words_for_a_tract_that_is_over() -> None:
    finding = over_concentration_finding(concentration("208.01", "on_sale"))
    assert finding is not None
    assert finding.sentence == "Further review: public convenience or necessity finding likely required"
    assert finding.citation == "California Business and Professions Code § 23958.4"
    assert finding.status == "further_review"
    assert finding.status_note == "public convenience or necessity finding likely required"
    assert finding.sentence == f"Further review: {finding.status_note}"
    assert finding.line == (
        "Census tract 208.01: 28 active on-sale retail licences in ABC's licence export of 9 November 2026, "
        "against 12 authorised in ABC's census tract authorisations of September 2026."
    )
    assert "23958.4" in finding.source_url
    assert finding.rule_id == "alcohol.tract_concentration"


def test_the_line_for_off_sale_and_for_one_licence() -> None:
    c = a_concentration(active=1, authorised=0, kind="off_sale", tract="9805.01")
    assert concentration_line(c) == (
        "Census tract 9805.01: 1 active off-sale retail licence in ABC's licence export of 9 November 2026, "
        "against 0 authorised in ABC's census tract authorisations of September 2026."
    )


def test_over_concentration_is_only_ever_further_review() -> None:
    """Every tract, both kinds: the finding is the further-review qualifier or nothing. Never a blocker."""
    seen = 0
    for tract in tracts.tracts_with_figures():
        for kind in KINDS:
            c = concentration(tract, kind)
            assert c is not None
            finding = over_concentration_finding(c)
            assert (finding is not None) == c.over
            if finding is None:
                continue
            seen += 1
            assert finding.status == "further_review"
            assert (finding.sentence, finding.citation) == (PCN_SENTENCE, PCN_CITATION)
            words = f"{finding.sentence} {finding.status_note} {finding.line}".lower()
            assert "blocker" not in words and "not permitted" not in words
    assert seen == 78 + 98


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "potential_blocker"},
        {"status": "not_permitted"},
        {"status": "allowed"},
        {"sentence": "Potential blocker: the tract is over-concentrated"},
        {"status_note": "not permitted"},
        {"citation": "Business and Professions Code § 23790"},
    ],
)
def test_a_finding_cannot_be_built_with_any_other_status_or_words(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="only ever"):
        ConcentrationFinding(line="x", **changes)
    with pytest.raises(ValueError, match="only ever"):
        dataclasses.replace(ConcentrationFinding(line="x"), **changes)


def test_no_figures_means_no_finding() -> None:
    assert over_concentration_finding(None) is None
    assert concentration("208.00", "on_sale") is None  # an older tract number
    assert concentration("9999.99", "off_sale") is None
    assert concentration("", "on_sale") is None


def test_the_tract_number_may_be_written_as_the_export_writes_it() -> None:
    assert concentration("0208.01", "on_sale") == concentration("208.01", "on_sale")


def test_an_unknown_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="kind must be one of"):
        concentration("208.01", "retail")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("given", "want"),
    [
        ("2026-11-09", "9 November 2026"),
        ("2026-09", "September 2026"),
        ("2026-01-31", "31 January 2026"),
        ("September 2026", "September 2026"),
        ("2026-13", "2026-13"),
    ],
)
def test_plain_date(given: str, want: str) -> None:
    assert plain_date(given) == want


def test_each_file_is_read_once(monkeypatch: pytest.MonkeyPatch) -> None:
    tract_at(*VALENCIA_995)
    concentration("208.01", "on_sale")  # both files are now loaded

    def no_more_reads(path: Path) -> dict[str, Any]:
        raise AssertionError(f"{path.name} read again")

    monkeypatch.setattr(tracts, "_read_json", no_more_reads)
    assert tract_at(*VALENCIA_995) == "208.01"
    assert concentration("101.01", "off_sale") is not None
    assert tracts.boundary_source()["downloaded_on"] == "2026-11-10"
    assert tracts.licence_figures_source()["active"]["export_date"] == "2026-11-09"
    assert tracts.tracts_without_polygon() == ()
