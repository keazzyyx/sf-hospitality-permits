"""SF Entertainment Commission permits — "Active Entertainment Permits" (DataSF 86e8-rfem).

The dataset lists only currently active, fixed-location permits (no denied / expired history and no
one-time event permits), one row per business with every active permit type in `active_licenses`
(POE = Place of Entertainment, LLP = Limited Live Performance, FPAS = Fixed Place Amplified Sound,
EHP = Extended Hours Premises, MAD = Mechanical Amusement Device, BP = Billiard or Pool Tables).
It has no filing / decision dates and no conditions column, so those fields stay empty.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any, Final

import httpx

from precedent.models import Application, ApplicationKind, Outcome, SourceBatch, UseType
from precedent.sources import socrata
from precedent.sources.base import RateLimiter, SourceSpec, fetched_at_from, read_raw
from precedent.textparse import classify_use_types, extract_conditions

SOURCE_NAME: Final = "datasf_entertainment"
DATASET_ID = "86e8-rfem"
RATE = 2.0
ONE_TIME_CODES = {
    "OTE",
    "OT",
    "ONE-TIME",
    "ONE TIME",
}  # not present in the current dataset; skipped if they appear


def _codes(row: dict[str, Any]) -> list[str]:
    return [c.strip().upper() for c in (row.get("active_licenses") or "").split(",") if c.strip()]


def kind_for(codes: list[str], license_type: str = "") -> ApplicationKind:
    lt = license_type.lower()
    if "POE" in codes or "place of entertainment" in lt:
        return "entertainment_poe"
    if "LLP" in codes or "limited live" in lt:
        return "entertainment_llp"
    if "FPAS" in codes or "amplified sound" in lt:
        return "entertainment_sound"
    return "entertainment_other"


def map_outcome(status: str) -> Outcome:
    s = (status or "").strip().lower()
    if s in {"active", "approved", "issued"}:
        return "approved"
    if "denied" in s or "disapproved" in s:
        return "denied"
    if s.startswith(("expired", "revoked", "suspended", "inactive", "surrendered")):
        return "approved"  # it was granted; `status` keeps the current state
    if "withdrawn" in s:
        return "withdrawn"
    if "pending" in s or "review" in s or "filed" in s:
        return "pending"
    return "unknown"


async def fetch(client: httpx.AsyncClient, raw_dir: Path, since: dt.date | None) -> list[Path]:
    # Small dataset (<1k rows) without filing dates: always a full snapshot; `since` is not applicable.
    max_pages = int(os.environ["DATASF_MAX_PAGES"]) if os.environ.get("DATASF_MAX_PAGES") else None
    return await socrata.fetch_all(
        client,
        source=SOURCE_NAME,
        dataset_id=DATASET_ID,
        raw_dir=raw_dir,
        order="permit_number",
        limiter=RateLimiter(RATE),
        max_pages=max_pages,
    )


def parse_row(row: dict[str, Any], fetched_at: dt.datetime, raw_ref: str) -> Application | None:
    permit = (row.get("permit_number") or "").strip()
    if not permit:
        return None
    codes = _codes(row)
    if codes and set(codes) <= ONE_TIME_CODES:
        return None
    license_type = (row.get("license_type") or "").strip()
    kind = kind_for(codes, license_type)
    dba = (row.get("dba_name") or "").strip()
    use_types: list[UseType] = []
    if kind in {"entertainment_poe", "entertainment_llp"}:
        use_types.append("live_entertainment")
    for u in classify_use_types(f"{dba} {license_type}"):
        if u not in use_types:
            use_types.append(u)
    lat, lng = socrata.parse_point(row, "point")
    status = (row.get("permit_status") or "").strip()
    notes = " ".join(str(row[k]) for k in ("conditions", "notes", "permit_conditions") if row.get(k))
    extended = "EHP" in codes
    address = (row.get("street_address") or "").strip() or None
    return Application(
        id=f"{SOURCE_NAME}:{permit}",
        source=SOURCE_NAME,
        source_id=permit,
        source_url=socrata.dataset_home(DATASET_ID),
        fetched_at=fetched_at,
        raw_ref=raw_ref,
        kind=kind,
        permit_type=license_type or ", ".join(codes),
        use_types=use_types,
        description=f"{dba}: {license_type}" if dba else license_type,
        address=f"{address}, San Francisco, CA" if address else None,
        lat=lat,
        lng=lng,
        status=status,
        outcome=map_outcome(status),
        # An Extended Hours Premises permit is what allows a business to operate between 2 a.m. and 6 a.m.
        late_night=True if extended else None,
        conditions=extract_conditions(notes),
        extraction_confidence="high",
        extra={
            k: v
            for k, v in {
                "dba_name": dba or None,
                "active_licenses": codes,
                "poe_class_code": row.get("poe_class_code"),
                "ban": row.get("ban"),
                "neighborhood": row.get("analysis_neighborhood"),
                "supervisor_district": row.get("supervisor_district"),
                "police_district": row.get("police_district"),
                "data_as_of": row.get("data_as_of"),
                "extended_hours": extended,
            }.items()
            if v not in (None, "", [])
        },
    )


def parse(path: Path) -> SourceBatch:
    meta, rows = read_raw(path)
    fetched_at = fetched_at_from(meta)
    apps = [a for r in rows if (a := parse_row(r, fetched_at, str(path))) is not None]
    return SourceBatch(applications=apps)


SOURCE = SourceSpec(
    name=SOURCE_NAME,
    description=f"SF Entertainment Commission active permits (DataSF {DATASET_ID}): POE, LLP, amplified sound, extended hours",
    fetch=fetch,
    parse=parse,
    rate_limit_per_second=RATE,
    source_home=socrata.dataset_home(DATASET_ID),
)
