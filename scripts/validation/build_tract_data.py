"""Build the two bundled files that apps/api/app/memo/tracts.py reads (local only; no network, no model call).

    # 1. boundaries, from the Census Bureau's 2020 tract shapefile for California, downloaded by hand:
    #      https://www2.census.gov/geo/tiger/TIGER2020/TRACT/tl_2020_06_tract.zip
    #      ogr2ogr -f GeoJSON -where "COUNTYFP='075'" -lco COORDINATE_PRECISION=7 sf_tracts_2020.geojson \
    #          /vsizip/tl_2020_06_tract.zip/tl_2020_06_tract.shp
    apps/api/.venv/bin/python scripts/validation/build_tract_data.py boundaries sf_tracts_2020.geojson \
        --downloaded-on 2026-11-10 --sha256 <sha256 of the zip>

    # 2. licence counts, from the local table abc_export_sf and ABC's authorisations CSV:
    apps/api/.venv/bin/python scripts/validation/build_tract_data.py licences

Boundaries are not simplified: the county is 244 tracts and about 13,000 points. Coordinates are rounded to six
decimal places (about 0.1 m); neighbouring tracts share their points exactly, so rounding opens no gaps.

The counting rule and the licence type lists live in app.memo.tracts (`count_licences`), which the test suite
also uses to check the file against the table.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.memo import tracts  # noqa: E402

LOCAL = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres@localhost:55433/sfhp_local")
AUTHORISATIONS_CSV = ROOT / "docs" / "validation" / "abc-census-tract-authorizations-sf-2026-09.csv"
TIGER_URL = "https://www2.census.gov/geo/tiger/TIGER2020/TRACT/tl_2020_06_tract.zip"


def write(path: Path, data: dict[str, Any], *, indent: int | None) -> None:
    text = json.dumps(data, indent=indent, separators=None if indent else (",", ":"), ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {path} ({path.stat().st_size:,} bytes)")


def boundaries(geojson: Path, downloaded_on: str, sha256: str) -> None:
    features = json.loads(geojson.read_text(encoding="utf-8"))["features"]
    out: dict[str, Any] = {}
    points = 0
    for feature in features:
        props, geom = feature["properties"], feature["geometry"]
        if props["STATEFP"] != "06" or props["COUNTYFP"] != "075":
            raise SystemExit(f"not a San Francisco County tract: {props['GEOID']}")
        tract = tracts.normalise_tract(props["TRACTCE"])
        if tract is None or tract in out:
            raise SystemExit(f"bad or repeated tract: {props['TRACTCE']}")
        polygons = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        rounded = [
            [[[round(x, 6), round(y, 6)] for x, y, *_ in ring] for ring in polygon] for polygon in polygons
        ]
        points += sum(len(ring) for polygon in rounded for ring in polygon)
        out[tract] = {
            "geoid": props["GEOID"],
            "land_sq_m": props["ALAND"],
            "water_sq_m": props["AWATER"],
            "polygons": rounded,
        }
    data = {
        "source": {
            "name": "U.S. Census Bureau, TIGER/Line Shapefiles 2020, Census Tracts, California (tl_2020_06_tract)",
            "url": TIGER_URL,
            "sha256": sha256,
            "vintage": "2020 Census tracts (TIGER/Line 2020)",
            "downloaded_on": downloaded_on,
            "extent": f"COUNTYFP 075, San Francisco County: {len(out)} tracts, {points} points",
            "datum": "NAD83 (EPSG:4269) as published; read as WGS84, a difference of about one metre here",
            "simplified": "no; coordinates rounded to 6 decimal places (about 0.1 m)",
            "coordinates": "[longitude, latitude]; each polygon is its outer ring followed by any holes",
            "tract_numbers": "as ABC's census tract authorisations report writes them, e.g. 208.01, 103.00",
        },
        "tracts": {t: out[t] for t in sorted(out, key=lambda t: float(t))},
    }
    write(tracts.TRACTS_FILE, data, indent=None)


def licences() -> None:
    import psycopg

    with psycopg.connect(LOCAL, connect_timeout=5) as conn:
        rows = [
            tracts.ExportRow(*r)
            for r in conn.execute(
                "select census_tract, file_number, license_type, lic_or_app, type_status from abc_export_sf"
            )
        ]
        dates = [r[0] for r in conn.execute("select distinct export_date from abc_export_sf")]
    if len(dates) != 1:
        raise SystemExit(f"expected one export date, found {dates}")
    counts = tracts.count_licences(rows)

    with AUTHORISATIONS_CSV.open(encoding="utf-8") as f:
        report = list(csv.DictReader(f))
    county = {
        (r["county"], r["county_population"], r["county_ratio_on_sale"], r["county_ratio_off_sale"])
        for r in report
    }
    if len(county) != 1:
        raise SystemExit(f"expected one county line, found {county}")
    name, county_population, ratio_on, ratio_off = next(iter(county))

    per_tract: dict[str, Any] = {}
    for r in report:
        tract = tracts.normalise_tract(r["census_tract"])
        if tract is None or tract in per_tract:
            raise SystemExit(f"bad or repeated tract in the CSV: {r['census_tract']}")
        c = counts.get(tract, tracts.LicenceCounts())
        per_tract[tract] = {
            "population": int(r["tract_population"]),
            "authorised_on_sale": int(r["authorized_on_sale"]),
            "authorised_off_sale": int(r["authorized_off_sale"]),
            "active_on_sale": c.active_on_sale,
            "active_off_sale": c.active_off_sale,
            "issued_not_active_on_sale": c.issued_not_active_on_sale,
            "issued_not_active_off_sale": c.issued_not_active_off_sale,
        }
    not_placed = {
        tract: {
            "active_on_sale": c.active_on_sale,
            "active_off_sale": c.active_off_sale,
            "issued_not_active_on_sale": c.issued_not_active_on_sale,
            "issued_not_active_off_sale": c.issued_not_active_off_sale,
        }
        for tract, c in counts.items()
        if tract not in per_tract
    }
    data = {
        "authorised": {
            "source": "ABC Census Tract Authorizations, San Francisco County (California Department of Alcoholic "
            "Beverage Control)",
            "as_of": "2026-09",
            "saved_as": "docs/validation/abc-census-tract-authorizations-sf-2026-09.csv",
            "county": name,
            "county_population": int(county_population),
            "people_per_on_sale_licence": int(ratio_on),
            "people_per_off_sale_licence": int(ratio_off),
            "note": "authorised = tract population divided by the county figure, rounded down (true of every tract)",
        },
        "active": {
            "source": "ABC Daily Data Export, licences in San Francisco County (California Department of Alcoholic "
            "Beverage Control)",
            "export_date": dates[0].isoformat(),
            "table": "abc_export_sf (local)",
            "counting_rule": "file numbers with a licence row (lic_or_app LIC) of status ACTIVE and a counted type; "
            "issued_not_active: licence rows with status SUSPEN, REVPEN, SUREND or R64B and no active row of the kind",
            "on_sale_types": sorted(tracts.ON_SALE_RETAIL_TYPES),
            "off_sale_types": sorted(tracts.OFF_SALE_RETAIL_TYPES),
            "types_source": tracts.LICENCE_TYPES_SOURCE,
        },
        "tracts": {t: per_tract[t] for t in sorted(per_tract, key=lambda t: float(t))},
        # licences whose tract number in the export is blank ("") or is not one of the report's tracts (older
        # tract numbers); counted here, in no tract above
        "not_placed": {t: not_placed[t] for t in sorted(not_placed)},
    }
    write(tracts.LICENCES_FILE, data, indent=1)
    for kind in tracts.KINDS:
        over = sum(tracts.is_over(v[f"active_{kind}"], v[f"authorised_{kind}"]) for v in per_tract.values())
        placed = sum(v[f"active_{kind}"] for v in per_tract.values())
        unplaced = sum(v[f"active_{kind}"] for v in not_placed.values())
        print(
            f"{kind}: {over} of {len(per_tract)} tracts over; {placed} active licences placed, {unplaced} not placed"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("boundaries")
    b.add_argument("geojson", type=Path)
    b.add_argument("--downloaded-on", required=True)
    b.add_argument("--sha256", required=True)
    sub.add_parser("licences")
    args = parser.parse_args()
    if args.command == "boundaries":
        boundaries(args.geojson, args.downloaded_on, args.sha256)
    else:
        licences()


if __name__ == "__main__":
    main()
