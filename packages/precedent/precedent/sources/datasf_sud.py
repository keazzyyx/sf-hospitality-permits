"""SF Zoning Map – Special Use Districts polygons (DataSF 5yf5-ms5f) → `alcohol_sud` / `special_use_district` Overlays.

The dataset is small (~145 polygons; fields `name`, `url` (amlegal link), `the_geom`). Polygons are
dissolved per name. Rules / code sections are copied from the cited rows in static/sf_overlay_rules.json
when the name is listed in its `sud_name_aliases`; otherwise the Planning Code section is resolved from the
curated name → section table below (checked against the Article 2 and Article 7 section titles), else left
explicitly unresolved.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Final

import httpx

from precedent.models import Overlay, OverlayKind, SourceBatch
from precedent.sources import socrata
from precedent.sources.base import RateLimiter, SourceSpec, fetched_at_from, read_raw
from precedent.sources.datasf_zoning import dissolve, rules_doc

SOURCE_NAME: Final = "datasf_sud"
DATASET_ID = "5yf5-ms5f"
RATE = 2.0
_ALCOHOL = re.compile(r"alcohol|liquor|beverage", re.I)
UNRESOLVED = "Planning Code Article 2 / Article 7 special use district (section not resolved)"

# DataSF SUD name → Planning Code section, matched by hand against the section titles in Articles 2 and 7.
SUD_SECTIONS = {
    "17th Rhode Island Grocery": "781.10",
    "1800 Market Community Center": "787",
    "3rd St Alcohol Restrict": "249.62",
    "3rd St and Le Conte Affordable": "249.43",
    "3rd Street Formula Retail Restricted Use": "786",
    "4th and Freelon Streets": "249.23",
    "Alabama 18th Affordable": "249.27",
    "Alexandria Theater SUD": "249.4",
    "Art & Design Education": "249.67",
    "Balboa Reservoir": "249.90",
    "Bayshore Blvd Home Improvement": "249.65",
    "Bayshore Hester NC": "780.2",
    "Bayview Industrial Triangle Cannabis RUD": "249.88",
    "California Presidio Comm Ctr": "249.21",
    "Calle 24 SUD": "249.59",
    "Candlestick Pt Activity Node": "249.50",
    "Cayuga/Alemany SUD": "249.63",
    "Central Neighborhoods Large Residence": "249.92",
    "Central SoMa": "249.78",
    "Cesar Chavez/Valencia Streets Medical": "249.68",
    "Chestnut St Fin Svcs Restrict": "781.7",
    "Chinatown Transit Station": "249.66",
    "Design & Development": "249.35B",
    "Executive Park": "249.54",
    "Family and Senior Housing Opportunity SUD": "249.94",
    "Fifth and Mission": "249.74",
    "Folsom & Main Res Comm": "249.1",
    "Fringe Financial Services RUD": "249.35",
    "Within 1/4 Mile of an Existing Fringe Financial Service": "249.35",
    "Within 1/4 Mile of the Fringe Financial Services RUD": "249.35",
    "Fulton St Grocery Store": "249.35A",
    "Geary Blvd Divisadero St": "249.13",
    "Geary Blvd Formula Retail Pet Supply Store and Formula Retail Eating and Drinking Subdistrict": "781.4",
    "Geary-Masonic": "249.20",
    "Group Housing Special Use District": "249.93",
    "Haight St Affordable Housing": "249.24",
    "Haight Street Alcohol Restricted Use": "781.9",
    "Hunters Pt Shipyard Phase 2": "249.51",
    "Hunters View SUD": "249.44",
    "India Basin Industrial Park": "249.42",
    "India Basin SUD": "249.84",
    "Innovative Industries": "249.37",
    "Jackson Square": "249.25",
    "Japantown": "249.31",
    "Jewish Home of San Francisco": "249.73",
    "Laguna Haight Buchanan Herman": "249.32",
    "Lakeshore Plaza NC": "780.1",
    "Lower Haight Alcohol Restrict": "784",
    "Mission Alcohol Restrict": "249.60",
    "Mission Harrington": "780.4",
    "Mission Rock": "249.80",
    "Mission and 9th Street SUD": "249.15",
    "New Asia Senior Affordable Housing SUD": "249.19",
    "Non-Contiguous SFMTA Special Use District": "249.22",
    "Non-Profit Arts Education SUD": "249.8",
    "North Beach Limited Financial": "781.6",
    "North China Basin": "249.18",
    "North of Market Residential 1": "249.5",
    "North of Market Residential 2": "249.5",
    "Oceanview Large Residence": "249.3",
    "Parkmerced": "249.64",
    "Pier 70": "249.79",
    "Potrero Center Mixed Use": "249.40",
    "Potrero Hope SF": "249.76",
    "Potrero Power Station SUD": "249.87",
    "Potrero Yard SUD": "249.98",
    "Presidio-Sutter": "249.53",
    "Priority Equity Geographies SUD": "249.97",
    "San Francisco Gateway SUD": "249.7",
    "Scott St Aff Grp Housing": "249.55",
    "SoMa Hall of Justice Legal Svc": "249.6",
    "Stonestown Special Use District": "249.9",
    "Sunnydale Hope SF": "249.75",
    "Taraval Street Restaurant Subdistrict": "781.1",
    "Telegraph Hill-NB Residential": "249.49",
    "The Village SUD": "249.2",
    "Third Street": "249.14",
    "Transbay C3": "249.28",
    "Treasure Island/Yerba Buena Island SUD": "249.52",
    "Treasure Island/Yerba Buena Island SUD; Tidelands Trust Overlay": "249.52",
    "Trinity Plaza": "249.34",
    "Van Ness and Market Residential": "249.33",
    "Veterans Commons": "249.46",
    "Visitacion Valley/Schlage SUD": "249.45",
    "Wawona Street and 45th Avenue Cultural Center SUD": "249.96",
    "Western SoMa": "249.39",
    "Yerba Buena Center Mixed-Use SUD": "249.71",
    "Youth and Family Zone": "249.38",
    # Resolved 2026-10-28 against the Planning Code text (gocodebook.com mirror, text as of 2026-09-23); the
    # DataSF row's amlegal anchor order agrees with each section's place in Article 2.
    "1500 Mission Street": "249.12",
    "1500 Page Street Residential Care": "249.47",  # "1500 Page Street Affordable Housing SUD" (vacant residential care facility)
    "1550 Evans Avenue": "249.85",
    "1629 Market Street SUD": "249.81",
    "2000 Marin Street SUD": "249.89",
    "2245 Post Street SUD": "249.26",
    "2500-2530 18th Street Affordable Housing SUD": "249.91",
    "30 Van Ness Avenue SUD": "249.99",
    "3333 California Street SUD": "249.86",
    "430 29th Avenue": "249.82",
    "530 Sansome Mixed-Use Tower and Fire Station SUD": "249.11",
    "600 Townsend Street West SUD": "249.10",
    "900 Kearny Street SUD": "249.95",
    "901 Bush Street SUD": "249.41",
    "Bernal Heights": "242",
    "C-3-S (SU)": "247",  # Downtown Support (Open Space Demonstration) SUD, a.k.a. the C-3-S (SU) District
    "Central Subway Tunnel Boring Machine Extraction Site": "249.70 (expired 4/5/2018; Ord. 33-13)",
    "Dolores Heights": "241",
    "Nob Hill": "238",
    "Transit Center C-3-O(SD) Commercial": "248 (deleted by Ord. 37-25; still drawn on the Zoning Map dataset)",
    "Van Ness": "243",
    "Van Ness Automotive": "237",  # Automotive SUD, Sectional Map SU02 (Van Ness corridor)
    "Van Ness Medical Use Subdistrict": "243",  # subdistrict defined inside § 243
    "Washington-Broadway SUD": "239",
    "Waterfront 1": "240.1",
    "Waterfront 2": "240.2",
    "Waterfront 3": "240.3",
    "Waterfront 4": "240.4",
    "Westwood Park": "244.1",  # Westwood Park Residential Character District
}

# SUDs whose section text regulates Bars, liquor licenses / liquor stores, Entertainment or Nighttime
# Entertainment uses, or restaurant/eating-and-drinking uses (scan of the Planning Code text, 2026-10-28).
# Every one must resolve to a Planning Code section (tests/test_sources_datasf.py).
ALCOHOL_ENTERTAINMENT_SUDS = (
    "Mission Alcohol Restrict",  # § 249.60
    "3rd St Alcohol Restrict",  # § 249.62
    "Haight Street Alcohol Restricted Use",  # § 781.9
    "Lower Haight Alcohol Restrict",  # § 784
    "Taraval Street Restaurant Subdistrict",  # § 781.1
    "Geary Blvd Formula Retail Pet Supply Store and Formula Retail Eating and Drinking Subdistrict",  # § 781.4
    "17th Rhode Island Grocery",  # liquor sales
    "Van Ness",  # Nighttime Entertainment
    "California Presidio Comm Ctr",
    "Jackson Square",  # Bars
    "Youth and Family Zone",  # Bars, liquor, Nighttime Entertainment
    "Western SoMa",  # Nighttime Entertainment
    "Treasure Island/Yerba Buena Island SUD",
    "Calle 24 SUD",  # Bars, Restaurants
    "Central SoMa",  # Bars, Nighttime Entertainment
    "Pier 70",
    "Mission Rock",
    "India Basin SUD",
    "Potrero Power Station SUD",
    "Stonestown Special Use District",
    "Balboa Reservoir",
    "Wawona Street and 45th Avenue Cultural Center SUD",
    "Potrero Yard SUD",
)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


async def fetch(client: httpx.AsyncClient, raw_dir: Path, since: dt.date | None) -> list[Path]:
    # ~145 rows and no edit dates: always a full snapshot; `since` is not applicable.
    max_pages = int(os.environ["DATASF_MAX_PAGES"]) if os.environ.get("DATASF_MAX_PAGES") else None
    return await socrata.fetch_all(
        client,
        source=SOURCE_NAME,
        dataset_id=DATASET_ID,
        raw_dir=raw_dir,
        select="name,url,the_geom",
        order="name",
        page_size=50000,
        limiter=RateLimiter(RATE),
        max_pages=max_pages,
    )


def _static_rows() -> dict[str, dict[str, Any]]:
    return {o["id"]: o for o in rules_doc().get("overlays", [])}


def overlay_for(name: str, rows: list[dict[str, Any]], fetched_at: dt.datetime) -> Overlay:
    geom = dissolve([r.get("the_geom") for r in rows if isinstance(r.get("the_geom"), dict)])
    urls = [r["url"] for r in rows if r.get("url")]
    ds_url = Counter(urls).most_common(1)[0][0] if urls else socrata.dataset_home(DATASET_ID)
    kind: OverlayKind = "alcohol_sud" if _ALCOHOL.search(name) else "special_use_district"
    rule_id = rules_doc().get("sud_name_aliases", {}).get(name)
    rule = _static_rows().get(rule_id) if rule_id else None
    if rule is not None:
        return Overlay(
            id=f"{SOURCE_NAME}:{slug(name)}",
            kind=kind,
            name=rule["name"],
            rules=rule["rules"],
            code_section=rule["code_section"],
            geom=geom,
            bar_permission=rule["bar_permission"],
            restaurant_permission=rule["restaurant_permission"],
            late_night_rule=rule.get("late_night_rule"),
            source=SOURCE_NAME,
            source_url=rule.get("source_url") or ds_url,
            fetched_at=fetched_at,
        )
    section = SUD_SECTIONS.get(name)
    code_section = f"Planning Code § {section}" if section else UNRESOLVED
    label = (
        "restricted use district" if re.search(r"\b(RUD|restrict)", name, re.I) else "special use district"
    )
    rules = f"{name}: {label} on the SF Zoning Map; its controls are in {code_section}."
    if not section:
        rules = f"{name}: {label} on the SF Zoning Map; the governing Planning Code section was not resolved — see the linked code page."
    return Overlay(
        id=f"{SOURCE_NAME}:{slug(name)}",
        kind=kind,
        name=name,
        rules=rules,
        code_section=code_section,
        geom=geom,
        source=SOURCE_NAME,
        source_url=ds_url,
        fetched_at=fetched_at,
    )


def parse(path: Path) -> SourceBatch:
    meta, rows = read_raw(path)
    fetched_at = fetched_at_from(meta)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        name = (r.get("name") or "").strip()
        if name:
            by_name[name].append(r)
    return SourceBatch(overlays=[overlay_for(n, rs, fetched_at) for n, rs in sorted(by_name.items())])


SOURCE = SourceSpec(
    name=SOURCE_NAME,
    description=f"SF Special Use Districts (DataSF {DATASET_ID}): alcohol SUDs/RUDs and other SUDs with Planning Code sections",
    fetch=fetch,
    parse=parse,
    rate_limit_per_second=RATE,
    source_home=socrata.dataset_home(DATASET_ID),
)
