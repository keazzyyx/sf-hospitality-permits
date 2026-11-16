"""Registered Business Locations - San Francisco (DataSF g8m3-pdis), food & drink subset.

The dataset no longer has `naic_code` / `naic_code_description`; the industry signal is now the
business-reported `self_reported_naics_code` plus the Tax Collector's license codes (`lic`,
`lic_code_description`, `lic_code_descriptions_list`, e.g. "BARS/TAVERNS W/O FOOD PREP",
"RESTAURANT 1,000 - 2,000 SQFT"). Many older rows have no NAICS code, so the filter also accepts
restaurant / bar license codes.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path
from typing import Any, Final

import httpx

from precedent.models import Business, SourceBatch
from precedent.sources import socrata
from precedent.sources.base import RateLimiter, SourceSpec, fetched_at_from, read_raw

SOURCE_NAME: Final = "datasf_business"
DATASET_ID = "g8m3-pdis"
RATE = 2.0

# 2017/2022 NAICS titles for the codes this source keeps.
NAICS_TITLES = {
    "722": "Food Services and Drinking Places",
    "7223": "Special Food Services",
    "722310": "Food Service Contractors",
    "722320": "Caterers",
    "722330": "Mobile Food Services",
    "7224": "Drinking Places (Alcoholic Beverages)",
    "72241": "Drinking Places (Alcoholic Beverages)",
    "722410": "Drinking Places (Alcoholic Beverages)",
    "7225": "Restaurants and Other Eating Places",
    "72251": "Restaurants and Other Eating Places",
    "722511": "Full-Service Restaurants",
    "722513": "Limited-Service Restaurants",
    "722514": "Cafeterias, Grill Buffets, and Buffets",
    "722515": "Snack and Nonalcoholic Beverage Bars",
    "4453": "Beer, Wine, and Liquor Retailers",
    "445310": "Beer, Wine, and Liquor Stores",
    "445320": "Beer, Wine, and Liquor Retailers",
}

_BAR_NAME = re.compile(
    r"\b(bar|tavern|pub|lounge|saloon|taproom|tap room|wine bar|cocktails?|brewpub|beer hall|brewery|brewing"
    r"|cantina)\b",
    re.I,
)
_NOT_A_BAR = re.compile(
    r"\b(juice|salad|nail|brow|lash|blow ?dry|smoothie|poke|yogurt|candy|snack|espresso|coffee|tea|oxygen|raw"
    r"|sushi|ramen|hand ?roll|shabu|noodle|food|oyster|taco|sandwich|burger|pho|dumpling|cereal|protein|acai"
    r"|salsa|soup|waffle|crepe)\s+bar\b"
    r"|\b(restaurant|kitchen|grill|eatery|bistro|cafe|tapas|ramen|sushi|pizza|taqueria|noodles?)\s+(&|and)\s+bar\b"
    r"|\bbar[\s-]*b[\s-]*q\b|\bbarbe|\btaco(\s+bell)?\s+cantina\b",
    re.I,
)


def where_clause(since: dt.date | None) -> str:
    where = (
        "upper(city) like 'SAN FRAN%' AND ("
        "self_reported_naics_code like '722%' OR self_reported_naics_code like '4453%'"
        " OR upper(lic_code_descriptions_list) like '%RESTAURANT%'"
        " OR upper(lic_code_descriptions_list) like '%BARS/TAVERNS%')"
    )
    if since:
        stamp = f"{since.isoformat()}T00:00:00"
        where += f" AND (location_start_date >= '{stamp}' OR location_end_date >= '{stamp}')"
    return where


async def fetch(client: httpx.AsyncClient, raw_dir: Path, since: dt.date | None) -> list[Path]:
    max_pages = int(os.environ["DATASF_MAX_PAGES"]) if os.environ.get("DATASF_MAX_PAGES") else None
    return await socrata.fetch_all(
        client,
        source=SOURCE_NAME,
        dataset_id=DATASET_ID,
        raw_dir=raw_dir,
        where=where_clause(since),
        order="uniqueid",
        limiter=RateLimiter(RATE),
        max_pages=max_pages,
    )


def is_bar_name(name: str) -> bool:
    """Name keywords that mark a drinking place (bar, tavern, pub, lounge, saloon, taproom, wine bar,
    cocktail, brewery, cantina ...), minus juice / nail / salad 'bars' and bar-b-q."""
    return bool(_BAR_NAME.search(name)) and not _NOT_A_BAR.search(name)


def classify(naics: str | None, lic_desc: str, dba: str) -> tuple[bool, bool]:
    """(is_food_or_drink, is_bar)."""
    code = (naics or "").strip()
    lic = lic_desc.upper()
    food = code.startswith("722") or "RESTAURANT" in lic or "BARS/TAVERNS" in lic
    bar = code.startswith("7224") or "BARS/TAVERNS" in lic or is_bar_name(dba)
    return food or bar, bar


def parse_row(row: dict[str, Any], fetched_at: dt.datetime) -> Business | None:
    uid = (row.get("uniqueid") or "").strip()
    if not uid:
        return None
    naics = (row.get("self_reported_naics_code") or "").strip() or None
    lic_list = row.get("lic_code_descriptions_list") or row.get("lic_code_description") or ""
    dba = (row.get("dba_name") or row.get("ownership_name") or "").strip()
    food, bar = classify(naics, lic_list, dba)
    lat, lng = socrata.parse_point(row, "location")
    street = (row.get("full_business_address") or "").strip()
    zip_code = (row.get("business_zip") or "").strip()
    address = (
        ", ".join(p for p in (street, "San Francisco", f"CA {zip_code}".strip()) if p) if street else None
    )
    return Business(
        id=f"{SOURCE_NAME}:{uid}",
        dba_name=dba or uid,
        naics_code=naics,
        naics_description=NAICS_TITLES.get(naics or "") or (lic_list or None),
        address=address,
        lat=lat,
        lng=lng,
        start_date=socrata.parse_date(row.get("location_start_date")),
        end_date=socrata.parse_date(row.get("location_end_date")),
        is_food_or_drink=food,
        is_bar=bar,
        source=SOURCE_NAME,
        source_url=socrata.dataset_home(DATASET_ID),
        fetched_at=fetched_at,
    )


def parse(path: Path) -> SourceBatch:
    meta, rows = read_raw(path)
    fetched_at = fetched_at_from(meta)
    return SourceBatch(businesses=[b for r in rows if (b := parse_row(r, fetched_at)) is not None])


SOURCE = SourceSpec(
    name=SOURCE_NAME,
    description=f"SF Registered Business Locations (DataSF {DATASET_ID}), food & drink subset: NAICS 722*/4453 or restaurant/bar license codes",
    fetch=fetch,
    parse=parse,
    rate_limit_per_second=RATE,
    source_home=socrata.dataset_home(DATASET_ID),
)
