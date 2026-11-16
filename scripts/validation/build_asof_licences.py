"""Build the ABC licence file the backtest reads instead of today's licence table: every San Francisco licence
file that existed at some point since 2021, with what is needed to say what it was on any past day.

Why: the licence rows the report reads are today's (ABC's daily export, and in the local database ZIP 94110
only). They include licences issued after a case was filed, possibly to the case's own business, and leave out
licences cancelled since. The backtest needs the licences as they stood on the day before each case was filed.

Sources (all local):
  abc_export_sf (local table)                ABC's daily export of 2026-11-09, San Francisco: today's files
  $LOCAL_DATA_DIR/abc-histories.csv.gz   Step 1b: every file in ABC's daily reports 2019-01-01 to 2026-11-09,
                                             with its original issue dates, the dates its status changed and its
                                             latest transition (ABC's reports keep only the latest)
Geocoding: DataSF's address service (EAS), the one the app uses, in bulk (40 addresses a request, 4 requests a
second at most), no other service. Results are cached in $LOCAL_DATA_DIR/backtest/geocode.json, so a second
run sends nothing. A file whose address EAS does not find is kept without a point and counted.

Names: the business name (DBA) of a company licensee; blank where the licensee is an individual (the same rule as
Step 1b, abc_histories.business_name). No owner name and no mailing address is written.

Output: $LOCAL_DATA_DIR/backtest/licences_asof.json, read by app.backtest.asof. Local only, not committed.

    apps/api/.venv/bin/python scripts/validation/build_asof_licences.py
"""

from __future__ import annotations

import asyncio
import csv
import datetime as dt
import gzip
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import abc_histories

LOCAL = Path(os.environ.get("LOCAL_DATA_DIR", "~/sfhp-local")).expanduser()
HISTORIES = LOCAL / "abc-histories.csv.gz"
OUT_DIR = LOCAL / "backtest"
OUT = OUT_DIR / "licences_asof.json"
GEO_CACHE = OUT_DIR / "geocode.json"
PSQL = [
    "psql",
    "-h",
    "localhost",
    "-p",
    "55433",
    "-U",
    "postgres",
    "sfhp_local",
    "-At",
    "-F",
    "\t",
    "-c",
]
# A file that ended before this day cannot be held on any backtest rules date (the earliest is 2022-01-16).
EARLIEST = dt.date(2021, 1, 1)
SF_COUNTY = "38"
TRANSITION_RE = re.compile(r"type (\S+) (\S+) to (\S+)")


def day(text: str | None) -> dt.date | None:
    text = (text or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%d-%b-%y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def strip_zeros(n: str) -> str:
    return n.strip().lstrip("0") or "0"


def export_files() -> dict[str, dict]:
    sql = (
        "select file_number, license_type, lic_or_app, type_status, orig_iss_date, master_ind, primary_name, "
        "dba_name, prem_addr_1, prem_zip, census_tract from abc_export_sf"
    )
    out = subprocess.run([*PSQL, sql], capture_output=True, text=True, check=True).stdout
    files: dict[str, dict] = {}
    for line in out.splitlines():
        num, typ, lic, status, iss, master, owner, dba, addr, zipc, tract = line.split("\t")
        f = files.setdefault(
            strip_zeros(num),
            {"types": [], "owner": owner, "dba": dba, "address": addr, "zip": zipc[:5], "tract": tract},
        )
        f["types"].append(
            {
                "type": typ.zfill(2),
                "lic_or_app": lic,
                "status": status.upper(),
                "issued": day(iss),
                "master": master,
            }
        )
    return files


def primary(types: list[dict]) -> dict:
    """The licence row the file is read by: a licence (not an application) first, the master row first, then the
    lowest type number."""
    return sorted(types, key=lambda t: (t["lic_or_app"] != "LIC", t["master"] != "Y", t["type"]))[0]


def company_name(owner: str, dba: str) -> str:
    return abc_histories.shown_name(abc_histories.File(number="", owner=owner, dba=dba).business_name())


async def geocode(addresses: list[str]) -> dict[str, dict | None]:
    cache: dict[str, dict | None] = json.loads(GEO_CACHE.read_text()) if GEO_CACHE.exists() else {}
    todo = sorted(a for a in set(addresses) if a not in cache)
    if todo:
        from precedent.geocode_sf import SFGeocoder

        g = SFGeocoder(use_nominatim=False)
        try:
            for i in range(0, len(todo), 400):
                part = todo[i : i + 400]
                res = await g.geocode_many(part)
                for a in part:
                    r = res.get(a)
                    cache[a] = (
                        None
                        if r is None
                        else {"lat": r.lat, "lng": r.lng, "parcel": r.parcel, "normalized": r.normalized_address,
                              "source": r.source, "confidence": r.confidence}
                    )  # fmt: skip
                GEO_CACHE.write_text(json.dumps(cache))
                print(f"geocoded {min(i + 400, len(todo))}/{len(todo)} (EAS requests {g.stats['eas_requests']})",
                      file=sys.stderr)  # fmt: skip
        finally:
            await g.close()
    return {a: cache.get(a) for a in addresses}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    export = export_files()
    with gzip.open(HISTORIES, "rt") as fh:
        hist = {r["file_number"]: r for r in csv.DictReader(fh) if r["county"] == SF_COUNTY}
    files: list[dict] = []
    skipped = Counter()
    for num in sorted(set(export) | set(hist), key=lambda n: int(n) if n.isdigit() else 0):
        e, h = export.get(num), hist.get(num)
        status_dates = sorted({d for d in (day(x) for x in (h["status_dates"].split() if h else [])) if d})
        latest = []
        for part in h["latest_transitions"].split("; ") if h and h["latest_transitions"] else []:
            m = TRANSITION_RE.match(part)
            if m:
                latest.append({"type": m[1].zfill(2), "from": m[2], "to": m[3]})
        # the date of the latest transition is the last status date (Step 1b: the report lists a record's latest
        # transition on every date it changed, so the newest of those dates is when it happened)
        latest_date = status_dates[-1] if status_dates else None
        if e is not None:
            p = primary(e["types"])
            if p["lic_or_app"] != "LIC":
                skipped["application only today (never issued)"] += 1
                continue
            issued = p["issued"] or min(
                (day(x) for x in (h["original_issue_dates"].split() if h else [])), default=None
            )
            types = sorted({t["type"] for t in e["types"] if t["lic_or_app"] == "LIC"})
            status_today = p["status"]
            name = company_name(e["owner"], e["dba"])
            address, zipc, tract = e["address"], e["zip"], e["tract"]
            primary_type = p["type"]
        else:
            iss = sorted(d for d in (day(x) for x in h["original_issue_dates"].split()) if d)
            if not iss:
                skipped["never issued (application withdrawn, denied or pending)"] += 1
                continue
            if latest_date is None or latest_date < EARLIEST:
                skipped["ended before 2021"] += 1
                continue
            issued = iss[0]
            types = sorted({t.zfill(2) for t in h["licence_types"].split()} or {h["primary_type"].zfill(2)})
            primary_type = (h["primary_type"] or types[0]).zfill(2)
            status_today = next(
                (t["to"] for t in latest if t["type"] == primary_type), latest[0]["to"] if latest else ""
            )
            name = "" if h["name_withheld"] == "yes" else h["business"]
            address, zipc, tract = abc_histories.CARE_OF_RE.sub("", h["premises_address"]).strip(), "", ""
        if issued is None:
            skipped["no issue date"] += 1
            continue
        files.append(
            {
                "file_number": num,
                "types": types,
                "primary_type": primary_type,
                "name": name,
                "address": address,
                "zip": zipc,
                "export_tract": tract,
                "issued": issued.isoformat(),
                "in_export_today": e is not None,
                "status_today": status_today,
                "status_dates": [d.isoformat() for d in status_dates],
                "latest_transition": (
                    {
                        **next((t for t in latest if t["type"] == primary_type), latest[0]),
                        "date": latest_date.isoformat(),
                    }
                    if latest and latest_date
                    else None
                ),
            }
        )
    keys = [f"{f['address']}, SAN FRANCISCO, CA" + (f" {f['zip']}" if f["zip"] else "") for f in files]
    geo = asyncio.run(geocode([k for k, f in zip(keys, files, strict=True) if f["address"]]))
    from app.memo.tracts import tract_at

    placed = 0
    for k, f in zip(keys, files, strict=True):
        g = geo.get(k) if f["address"] else None
        f["geocode_key"] = k
        if g:
            placed += 1
            f |= {"lat": g["lat"], "lng": g["lng"], "parcel": g["parcel"], "normalized_address": g["normalized"],
                  "tract": tract_at(g["lat"], g["lng"])}  # fmt: skip
        else:
            f |= {"lat": None, "lng": None, "parcel": None, "normalized_address": None, "tract": None}
    out = {
        "_doc": __doc__.split("\n\n")[0],
        "built": dt.date.today().isoformat(),
        "export_date": "2026-11-09",
        "histories": "2019-01-01 to 2026-11-09 (Step 1b)",
        "files": files,
        "counts": {
            "files": len(files),
            "in_export_today": sum(f["in_export_today"] for f in files),
            "ended_since_2021_not_in_export": sum(not f["in_export_today"] for f in files),
            "placed_on_map": placed,
            "skipped": dict(skipped),
        },
    }
    OUT.write_text(json.dumps(out, indent=0) + "\n")
    print(json.dumps(out["counts"], indent=1))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
