"""SF Planning Department records (Accela) — Conditional Use Authorizations and hospitality-related entitlements.

Dataset: "Planning Department Records - Non-Projects" (y673-d69b). Child records of PRJ projects (CUA, VAR,
PRL ...) live here; the PRJ parents are in qvu5-m3a2. Neither dataset carries a point, so each raw page is
followed by a companion parcel lookup against "Parcels – Active and Retired" (acdm-wktn), saved next to the
page as `<page>.parcels.json`, which gives the parcel centroid, zoning code and analysis neighborhood.

Volume filter (server side): every CUA, plus records of the entitlement / referral types below whose
description mentions a bar, restaurant, nightclub, liquor, alcohol, entertainment or outdoor activity/seating.
Record type suffixes: https://sfplanning.org/resource/project-suffixes-and-descriptions-case-numbers
"""

from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path
from typing import Any, Final

import httpx

from precedent.models import Application, ApplicationKind, Outcome, SourceBatch, UseType
from precedent.sources import socrata
from precedent.sources.base import RateLimiter, SourceSpec, fetched_at_from, read_raw, write_raw
from precedent.textparse import (
    classify_use_types,
    detect_opposition,
    extract_closing_hour,
    extract_conditions,
    is_late_night,
)

SOURCE_NAME: Final = "datasf_planning"
DATASET_ID = "y673-d69b"
PARCELS_DATASET_ID = "acdm-wktn"
RATE = 2.0

# Suffix → description, from the Planning Department's suffix table (only the types this source fetches).
RECORD_TYPES = {
    "CUA": "Conditional Use Authorization",
    "PRL": "Project Profile Lite",
    "MIS": "Miscellaneous Permit",
    "PRV": "Project Review Meeting",
    "VAR": "Variance",
    "ZAD": "Zoning Administrator (ZA) - Letter of Determination",
    "DRP": "Discretionary Review - Public Initiated",
    "DRM": "Discretionary Review - Mandatory",
    "COA": "Certificate of Appropriateness",
    "GEN": "Generic Application w/o Hearing",
    "LBR": "Legacy Business Registry",
    "APL": "Appeal",
}
OTHER_TYPES = [t for t in RECORD_TYPES if t != "CUA"]

# upper(description) LIKE patterns (Socrata has no regex); parse() re-checks with word boundaries.
_LIKE_TERMS = [
    "%RESTAURANT%",
    "% BAR %",
    "% BAR,%",
    "% BAR.%",
    "% BAR/%",
    "% BARS %",
    "BAR %",
    "%NIGHTCLUB%",
    "%NIGHT CLUB%",
    "%LIQUOR%",
    "%ALCOHOL%",
    "%ENTERTAINMENT%",
    "%OUTDOOR ACTIVITY%",
    "%OUTDOOR SEATING%",
    "%OUTDOOR DINING%",
    "%TAVERN%",
    "%COCKTAIL%",
]
HOSPITALITY: set[UseType] = {
    "bar",
    "restaurant",
    "cafe",
    "nightclub",
    "live_entertainment",
    "outdoor_seating",
    "retail_alcohol",
}


# Parcels carry a generic code ("NCD" / "NCT") for named districts plus the district name; map the name to the
# code used by the zoning dataset (3i4a-hu95) so applications join to zoning overlays and rule rows.
NAMED_DISTRICT_CODES = {
    "24TH STREET- NOE VALLEY NEIGHBORHOOD COMMERCIAL": "NCD-24TH-NOE-VALLEY",
    "24TH-MISSION NEIGHBORHOOD COMMERCIAL TRANSIT": "NCT-24TH-MISSION",
    "BAYVIEW NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-BAYVIEW",
    "BROADWAY NEIGHBORHOOD COMMERCIAL": "NCD-BROADWAY",
    "CASTRO STREET NEIGHBORHOOD COMMERCIAL": "NCD-CASTRO",
    "COLE VALLEY NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-COLE VALLEY",
    "CORTLAND AVENUE NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-CORTLAND AVENUE",
    "DIVISADERO STREET NEIGHBORHOOD COMMERCIAL TRANSIT DISTRICT": "NCT-DIVISADERO",
    "EXCELSIOR OUTER MISSION STREET NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-EXCELSIOR",
    "FILLMORE STREET NEIGHBORHOOD COMMERCIAL TRANSIT DISTRICT": "NCT-FILLMORE",
    "FOLSOM STREET NEIGHBORHOOD COMMERCIAL TRANSIT": "NCT-FOLSOM",
    "GEARY BOULEVARD NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-GEARY BOULEVARD",
    "GLEN PARK NEIGHBORHOOD COMMERCIAL TRANSIT": "NCT-GLEN PARK",
    "HAIGHT STREET NEIGHBORHOOD COMMERCIAL": "NCD-HAIGHT",
    "HAYES NCT": "NCT-HAYES",
    "INNER BALBOA STREET NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-INNER BALBOA STREET",
    "INNER CLEMENT STREET NEIGHBORHOOD COMMERCIAL": "NCD-INNER CLEMENT",
    "INNER SUNSET NEIGHBORHOOD COMMERCIAL": "NCD-INNER SUNSET",
    "INNER TARAVAL STREET NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-INNER TARAVAL STREET",
    "IRVING STREET NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-IRVING",
    "JAPANTOWN NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-JAPANTOWN",
    "JUDAH STREET NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-JUDAH",
    "LAKESIDE VILLAGE NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-LAKESIDE VILLAGE",
    "LELAND AVENUE NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-LELAND",
    "LOWER HAIGHT STREET NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-LOWER HAIGHT STREET",
    "LOWER POLK STREET NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-LOWER POLK STREET",
    "MISSION BERNAL NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-MISSION BERNAL",
    "MISSION STREET NEIGHBORHOOD COMMERCIAL TRANSIT": "NCT-MISSION",
    "NORIEGA STREET NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-NORIEGA",
    "NORTH BEACH NEIGHBORHOOD COMMERCIAL": "NCD-NORTH BEACH",
    "OCEAN AVENUE NEIGHBORHOOD COMMERCIAL TRANSIT": "NCT-OCEAN",
    "OUTER BALBOA STREET NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-OUTER BALBOA STREET",
    "OUTER CLEMENT STREET NEIGHBORHOOD COMMERCIAL": "NCD-OUTER CLEMENT",
    "PACIFIC AVENUE NEIGHBORHOOD COMMERCIAL": "NCD-PACIFIC",
    "POLK STREET NEIGHBORHOOD COMMERCIAL": "NCD-POLK",
    "SACRAMENTO STREET NEIGHBORHOOD COMMERCIAL": "NCD-SACRAMENTO",
    "SAN BRUNO AVENUE NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-SAN BRUNO AVENUE",
    "SOMA NEIGHBORHOOD COMMERCIAL TRANSIT": "NCT-SOMA",
    "TARAVAL STREET NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-TARAVAL",
    "UNION STREET NEIGHBORHOOD COMMERCIAL": "NCD-UNION",
    "UPPER FILLMORE NEIGHBORHOOD COMMERCIAL DISTRICT": "NCD-UPPER FILLMORE",
    "UPPER MARKET NEIGHBORHOOD COMMERCIAL TRANSIT": "NCT-UPPER MARKET",
    "VALENCIA STREET NEIGHBORHOOD COMMERCIAL TRANSIT": "NCT-VALENCIA",
    "WEST PORTAL AVENUE NEIGHBORHOOD COMMERCIAL": "NCD-WEST PORTAL",
}


def zoning_code_for(parcel: dict[str, Any]) -> str | None:
    code = (parcel.get("zoning_code") or "").split("|")[0].strip()
    name = (parcel.get("zoning_district") or "").split("|")[0].strip().upper()
    if code in {"NCD", "NCT"}:
        return NAMED_DISTRICT_CODES.get(name, code)
    return code or None


def where_clause(since: dt.date | None) -> str:
    desc = " OR ".join(f"upper(description) like '{t}'" for t in _LIKE_TERMS)
    types = ", ".join(f"'{t}'" for t in OTHER_TYPES)
    where = f"(record_type = 'CUA' OR (record_type in ({types}) AND ({desc})))"
    if since:
        stamp = f"{since.isoformat()}T00:00:00"
        where += f" AND (open_date >= '{stamp}' OR close_date >= '{stamp}')"
    return where


def _max_pages() -> int | None:
    val = os.environ.get("DATASF_MAX_PAGES")
    return int(val) if val else None


def parcels_path(page: Path) -> Path:
    return page.with_name(f"{page.stem}.parcels.json")


async def _lookup_parcels(
    client: httpx.AsyncClient, blklots: list[str], limiter: RateLimiter
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    headers = {"X-App-Token": os.environ["SOCRATA_APP_TOKEN"]} if os.environ.get("SOCRATA_APP_TOKEN") else {}
    for i in range(0, len(blklots), 150):
        chunk = blklots[i : i + 150]
        params: dict[str, str | int] = {
            "$select": "blklot,block_num,lot_num,centroid_latitude,centroid_longitude,zoning_code,zoning_district,analysis_neighborhood,active",
            "$where": "blklot in (" + ",".join(f"'{b}'" for b in chunk) + ")",
            "$limit": 5000,
        }
        await limiter.wait()
        resp = await client.get(socrata.dataset_url(PARCELS_DATASET_ID), params=params, headers=headers)
        resp.raise_for_status()
        out.extend(resp.json())
    return out


_BLOCK = re.compile(r"\d{4}[A-Z]?")
_LOT = re.compile(r"\d{3}[A-Z]?")


def block_lot(row: dict[str, Any]) -> tuple[str, str] | None:
    """Assessor (block, lot). Legacy records often have the two swapped (block '035', lot '0686')."""
    block, lot = (row.get("block") or "").strip().upper(), (row.get("lot") or "").strip().upper()
    if _BLOCK.fullmatch(block) and _LOT.fullmatch(lot):
        return block, lot
    if _BLOCK.fullmatch(lot) and _LOT.fullmatch(block):
        return lot, block
    return None


def _blklot(row: dict[str, Any]) -> str | None:
    bl = block_lot(row)
    return f"{bl[0]}{bl[1]}" if bl else None


async def fetch(client: httpx.AsyncClient, raw_dir: Path, since: dt.date | None) -> list[Path]:
    limiter = RateLimiter(RATE)
    pages = await socrata.fetch_all(
        client,
        source=SOURCE_NAME,
        dataset_id=DATASET_ID,
        raw_dir=raw_dir,
        where=where_clause(since),
        limiter=limiter,
        max_pages=_max_pages(),
    )
    for page in pages:
        _, rows = read_raw(page)
        blklots = sorted({b for r in rows if (b := _blklot(r))})
        parcels = await _lookup_parcels(client, blklots, limiter) if blklots else []
        write_raw(
            parcels_path(page),
            parcels,
            {
                "kind": "parcel_lookup",
                "for_page": page.name,
                "dataset_id": PARCELS_DATASET_ID,
                "url": socrata.dataset_url(PARCELS_DATASET_ID),
                "count": len(parcels),
            },
        )
    return pages


# ---- parsing ------------------------------------------------------------------------------------------------
# "bar" in building-permit scopes that has nothing to do with a drinking establishment.
_NON_HOSPITALITY_BAR = re.compile(
    r"\b(?:grab|towel|security|window|iron|steel|safety|wet|roll|sand|reinforcing)\s+bars?\b|\bbar\s+(?:sink|joists?|grating)\b",
    re.I,
)
_CONDITIONS_WORD = re.compile(r"\bcondition(?:s|ed)?\b(?! use)", re.I)


def map_outcome(status: str, text: str = "") -> Outcome:
    s = (status or "").strip().lower()
    if "disapprov" in s or "denied" in s or "deni" in s:
        return "denied"
    if "withdrawn" in s or "cancel" in s:
        return "withdrawn"
    if "approv" in s:  # "Closed - Approved", "Approved", "Closed - Approval Ltr Issued"
        # The dataset never says whether conditions were imposed; the word "condition" in a description is not
        # evidence of them, so approvals stay "approved". Conditions come from the decision document only.
        return "approved"
    if s in {
        "open",
        "submitted",
        "accepted",
        "under review",
        "pending review",
        "on hold",
        "filed",
        "pending",
    }:
        return "pending"
    return "unknown"


def _parcel_index(page: Path) -> dict[str, dict[str, Any]]:
    companion = parcels_path(page)
    if not companion.exists():
        return {}
    _, rows = read_raw(companion)
    index: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = r.get("blklot")
        if key and (key not in index or (r.get("active") and not index[key].get("active"))):
            index[key] = r
    return index


def _float(val: Any) -> float | None:
    try:
        return float(val) if val not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_row(
    row: dict[str, Any], parcels: dict[str, dict[str, Any]], fetched_at: dt.datetime, raw_ref: str
) -> Application | None:
    record_id = (row.get("record_id") or "").strip()
    if not record_id:
        return None
    rtype = (row.get("record_type") or "").strip()
    kind: ApplicationKind = "cua" if rtype == "CUA" or record_id.upper().endswith("CUA") else "planning_other"
    description = (row.get("description") or "").strip()
    text = " ".join(t for t in (row.get("project_name"), description) if t)
    use_types = classify_use_types(_NON_HOSPITALITY_BAR.sub(" ", description))
    if kind == "planning_other" and not HOSPITALITY & set(use_types):
        return None  # LIKE matched something like "barrier" — not a hospitality record
    status = (row.get("record_status") or "").strip()
    outcome = map_outcome(status, description)
    hours = extract_closing_hour(description)
    blklot = _blklot(row)
    parcel = parcels.get(blklot or "") or {}
    lat, lng = _float(parcel.get("centroid_latitude")), _float(parcel.get("centroid_longitude"))
    if lat is None or lng is None:
        lat = lng = None
    link = row.get("pim_link")
    source_url = (
        link.get("url") if isinstance(link, dict) and link.get("url") else socrata.dataset_home(DATASET_ID)
    )
    decided = (
        socrata.parse_date(row.get("close_date"))
        if outcome in {"approved", "approved_with_conditions", "denied", "withdrawn"}
        else None
    )
    extra: dict[str, Any] = {
        "record_type": rtype,
        "project_name": row.get("project_name"),
        "planner": row.get("assigned_to_planner"),
        "parent_id": row.get("parent_id"),
        "neighborhood": parcel.get("analysis_neighborhood"),
        "zoning": zoning_code_for(parcel),
        "zoning_name": parcel.get("zoning_district"),
        "close_date": row.get("close_date"),
        "building_permits": row.get("building_permits"),
        "applicant_org": row.get("applicant_org"),
        "hearing_date": None,  # not published in this dataset
    }
    return Application(
        id=f"{SOURCE_NAME}:{record_id}",
        source=SOURCE_NAME,
        source_id=record_id,
        source_url=source_url,
        fetched_at=fetched_at,
        raw_ref=raw_ref,
        kind=kind,
        permit_type=RECORD_TYPES.get(rtype, rtype or "Planning record"),
        use_types=use_types,
        description=description,
        address=(row.get("project_address") or None),
        lat=lat,
        lng=lng,
        parcel="/".join(bl) if (bl := block_lot(row)) else None,
        zoning_district=zoning_code_for(parcel),
        status=status,
        outcome=outcome,
        filed_at=socrata.parse_date(row.get("open_date")),
        decided_at=decided,
        hours_close=hours,
        late_night=is_late_night(hours),
        conditions=extract_conditions(description),
        opposition_noted=detect_opposition(text),
        extraction_confidence="medium",
        extra={k: v for k, v in extra.items() if v is not None or k == "hearing_date"},
    )


def parse(path: Path) -> SourceBatch:
    meta, rows = read_raw(path)
    if meta.get("kind") == "parcel_lookup":
        return SourceBatch()
    fetched_at = fetched_at_from(meta)
    parcels = _parcel_index(path)
    apps: dict[str, Application] = {}
    for row in rows:
        app = parse_row(row, parcels, fetched_at, str(path))
        if app is not None:
            apps[app.id] = app
    return SourceBatch(applications=list(apps.values()))


SOURCE = SourceSpec(
    name=SOURCE_NAME,
    description=f"SF Planning records (DataSF {DATASET_ID}): all CUAs + hospitality-related entitlements; points from parcel centroids ({PARCELS_DATASET_ID})",
    fetch=fetch,
    parse=parse,
    rate_limit_per_second=RATE,
    source_home=socrata.dataset_home(DATASET_ID),
)
