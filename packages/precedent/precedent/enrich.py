"""Post-ingest enrichment: steps that need two sources to be in the store at once.

    python -m precedent.enrich businesses        # flag bars among registered businesses

`businesses` — the Registered Business Locations dataset (DataSF g8m3-pdis) lost its `naic_code` columns and
`self_reported_naics_code` is sparse, so parse-time `is_bar` (NAICS 7224*, a BARS/TAVERNS license code, or a
bar-like name) misses most bars. This step adds two signals from the rest of the store:

  1. **Premises match with an ABC bar license.** The business's street address, normalised to
     (house number, street name), equals the premises of an *active* ABC license of type 42 (on-sale beer &
     wine, public premises), 48 (on-sale general, public premises) or 61 (on-sale beer, public premises).
     Public-premises licenses are, by ABC definition, places where minors are not admitted and food is not
     required: bars, taverns, pubs, lounges. A license belongs to a business at that address only when
     their names share a distinctive word (DBA or licensee owner) or the business is the only active food &
     drink business there; otherwise one bar in a mall, hotel or market hall would flag every tenant.
     Only food & drink businesses are matched, so a liquor store at the same street number is never flagged.
  2. **Name keywords.** The business DBA, or the DBA of an active on-sale license matched as above,
     contains bar / tavern / pub / lounge / saloon / taproom / wine bar / cocktail / brewery / cantina
     (juice / nail / salad "bars" and bar-b-q excluded; see `datasf_business.is_bar_name`).

The step only ever turns `is_bar` on. A business row that loses its evidence is reset the next time the
business source re-parses it (the nightly `ingest --all` does that before enriching), so the flag converges.
Runs after the sources in `python -m precedent.ingest --all` and whenever datasf_business or abc is ingested.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from precedent.models import Application, Business
from precedent.sources.datasf_business import is_bar_name
from precedent.store import Store, open_store

log = logging.getLogger("precedent.enrich")

BAR_LICENSE_TYPES = frozenset({"42", "48", "61"})
ON_SALE_TYPES = frozenset(
    {"40", "41", "42", "47", "48", "49", "51", "52", "57", "58", "59", "61", "64", "70", "75", "78", "86"}
)

_SUFFIXES = {
    "STREET": "ST",
    "ST": "ST",
    "AVENUE": "AVE",
    "AVE": "AVE",
    "AV": "AVE",
    "BOULEVARD": "BLVD",
    "BLVD": "BLVD",
    "DRIVE": "DR",
    "DR": "DR",
    "PLACE": "PL",
    "PL": "PL",
    "TERRACE": "TER",
    "TER": "TER",
    "ROAD": "RD",
    "RD": "RD",
    "LANE": "LN",
    "LN": "LN",
    "COURT": "CT",
    "CT": "CT",
    "ALLEY": "ALY",
    "ALY": "ALY",
    "HIGHWAY": "HWY",
    "HWY": "HWY",
    "WAY": "WAY",
    "PLAZA": "PLZ",
    "PLZ": "PLZ",
    "CIRCLE": "CIR",
    "CIR": "CIR",
}
_ORDINALS = {
    "FIRST": "1ST",
    "SECOND": "2ND",
    "THIRD": "3RD",
    "FOURTH": "4TH",
    "FIFTH": "5TH",
    "SIXTH": "6TH",
    "SEVENTH": "7TH",
    "EIGHTH": "8TH",
    "NINTH": "9TH",
    "TENTH": "10TH",
}
_UNIT = re.compile(r"\s+(#|APT\b|UNIT\b|STE\b|SUITE\b|FL\b|FLOOR\b|RM\b|ROOM\b|BLDG\b|SPC\b|SPACE\b).*$")
_NUMBER = re.compile(r"^(\d+)[A-Z]?(?:\s*[-&]\s*(\d+)[A-Z]?)?\s+(.+)$")


_DIRECTIONS = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}


def premises_keys(address: str | None) -> set[tuple[str, str]]:
    """(house number, street name) keys for an address line such as "993-995 Valencia St., Ste 2, San
    Francisco, CA 94110": unit / suite dropped, street type dropped, ordinals spelled as digits, both ends
    of a number range kept ("527-29" = 527 and 529). Empty when the address has no leading house number."""
    if not address:
        return set()
    line = address.split(",")[0].upper().replace(".", " ")
    line = re.sub(r"#\s*\S+", " ", line)
    line = _UNIT.sub("", re.sub(r"\s+", " ", line).strip())
    m = _NUMBER.match(line)
    if not m:
        return set()
    first, last, street = m.group(1), m.group(2), m.group(3)
    words = [w for w in street.split() if not re.fullmatch(r"\d+/\d+", w)]  # "1007 1/2 VALENCIA"
    words = [_ORDINALS.get(w, w) for w in words]
    words = [re.sub(r"^0+(\d)", r"\1", w) for w in words]  # "03RD" → "3RD"
    if len(words) > 1 and words[0] in _DIRECTIONS:
        words[0] = _DIRECTIONS[words[0]]
    if len(words) > 2 and words[-2] in _SUFFIXES and len(words[-1]) <= 2:  # "MISSION ST A" (unit letter)
        words = words[:-1]
    if len(words) > 1 and words[-1] in _SUFFIXES:
        words = words[:-1]
    name = " ".join(words)
    if not name:
        return set()
    numbers = {first.lstrip("0") or "0"}
    if last:
        if len(last) < len(first):  # "527-29" → 529
            last = first[: len(first) - len(last)] + last
        numbers.add(last.lstrip("0") or "0")
    return {(n, name) for n in numbers}


def _active(status: str | None) -> bool:
    return (status or "").strip().upper().startswith("ACT")


def active_license_types(lic: Application) -> set[str]:
    """License type codes that are active on this ABC record (a file number can carry several types)."""
    types: set[str] = set()
    for t in lic.extra.get("license_types") or []:
        code = str(t.get("type") or "").strip()
        if code and _active(t.get("status")):
            types.add(code.zfill(2))
    if lic.license_type and _active(lic.status):
        types.add(lic.license_type.strip().zfill(2))
    return types


_NAME_STOPWORDS = frozenset(
    [
        "THE",
        "AND",
        "OF",
        "DBA",
        "INC",
        "LLC",
        "LP",
        "LLP",
        "LTD",
        "CO",
        "CORP",
        "CORPORATION",
        "COMPANY",
        "SF",
        "SAN",
        "FRANCISCO",
        "GROUP",
        "HOLDINGS",
        "HOSPITALITY",
        "ENTERPRISES",
        "ENTERPRISE",
        "MANAGEMENT",
        "INVESTMENTS",
        "PARTNERS",
        "VENTURES",
        "INTERNATIONAL",
        "USA",
        "AMERICA",
        "SERVICES",
        "BAR",
        "BARS",
        "PUB",
        "TAVERN",
        "LOUNGE",
        "SALOON",
        "TAPROOM",
        "COCKTAIL",
        "COCKTAILS",
        "WINE",
        "BREWING",
        "BREWERY",
        "CANTINA",
        "CLUB",
        "SOCIAL",
        "RESTAURANT",
        "RESTAURANTS",
        "CAFE",
        "KITCHEN",
        "GRILL",
        "HOUSE",
        "FOOD",
        "FOODS",
        "DINING",
        "EATERY",
        "BISTRO",
    ]
)


# A business whose own name says it is a food counter is not the bar, even when it shares the licensee's name
# (hotel "Main Kitchen" / "Coffee Bar" under the hotel's Type 48, a sushi counter inside a market's Type 42).
_FOOD_COUNTER = re.compile(
    r"\b(coffee|espresso|bakery|bakehouse|kitchen|catering|caterers?|ice cream|donuts?|juice|tea|boba|bento"
    r"|sushi|deli|delicatessen|creamery|patisserie|cafeteria)\b",
    re.I,
)


def name_tokens(*names: str | None) -> set[str]:
    """Distinctive words of business / licensee names: apostrophes folded ("NELLY'S" → "NELLYS"), legal-form,
    generic venue and city words dropped, at least 3 characters."""
    out: set[str] = set()
    for n in names:
        if not n:
            continue
        for w in re.findall(r"[A-Z0-9]+", n.upper().replace("'", "").replace("’", "")):
            if len(w) >= 3 and w not in _NAME_STOPWORDS:
                out.add(w)
    return out


@dataclass(frozen=True)
class LicenseFacts:
    id: str
    bar_type: bool  # an active Type 42 / 48 / 61
    bar_named: bool  # an active on-sale license whose DBA reads as a bar
    tokens: frozenset[str]


def index_licenses(licenses: Iterable[Application]) -> dict[tuple[str, str], list[LicenseFacts]]:
    """Premises key → active ABC licenses there that carry a bar signal."""
    out: dict[tuple[str, str], list[LicenseFacts]] = {}
    for lic in licenses:
        types = active_license_types(lic)
        if not types:
            continue
        dba = str(lic.extra.get("dba") or "")
        facts = LicenseFacts(
            id=lic.id,
            bar_type=bool(types & BAR_LICENSE_TYPES),
            bar_named=bool(types & ON_SALE_TYPES) and bool(dba) and is_bar_name(dba),
            tokens=frozenset(name_tokens(dba, str(lic.extra.get("owner") or ""))),
        )
        if not (facts.bar_type or facts.bar_named):
            continue
        for key in premises_keys(lic.address):
            out.setdefault(key, []).append(facts)
    return out


def tenant_counts(businesses: Iterable[Business]) -> dict[tuple[str, str], int]:
    """Active food & drink businesses per premises key (a mall or hotel address has many)."""
    counts: dict[tuple[str, str], int] = {}
    for b in businesses:
        if b.is_food_or_drink and b.end_date is None:
            for key in premises_keys(b.address):
                counts[key] = counts.get(key, 0) + 1
    return counts


@dataclass
class BarEnrichment:
    businesses: int = 0
    already_bar: int = 0
    by_abc_license: int = 0
    by_abc_dba: int = 0
    by_name: int = 0
    updated: int = 0
    bar_premises: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def matched_licenses(
    b: Business, premises: dict[tuple[str, str], list[LicenseFacts]], tenants: dict[tuple[str, str], int]
) -> list[LicenseFacts]:
    """Licenses at the business's premises that belong to it: the names share a distinctive word, or the
    business is the only active food & drink business at that address (then it is the licensee)."""
    mine = name_tokens(b.dba_name)
    out: list[LicenseFacts] = []
    for key in premises_keys(b.address):
        sole = b.end_date is None and tenants.get(key, 0) == 1
        out += [f for f in premises.get(key, []) if sole or (mine & f.tokens)]
    return out


def bar_evidence(
    b: Business, premises: dict[tuple[str, str], list[LicenseFacts]], tenants: dict[tuple[str, str], int]
) -> str | None:
    """Why this business should be flagged as a bar, or None. Order: ABC bar license, ABC DBA, own name."""
    if not b.is_food_or_drink:
        return None
    lics = [] if _FOOD_COUNTER.search(b.dba_name) else matched_licenses(b, premises, tenants)
    if any(f.bar_type for f in lics):
        return "abc_license"
    if any(f.bar_named for f in lics):
        return "abc_dba"
    if is_bar_name(b.dba_name):
        return "name"
    return None


async def enrich_businesses(store: Store) -> BarEnrichment:
    licenses = await store.applications_of_kind("abc_license")
    premises = index_licenses(licenses)
    businesses = await store.all_businesses()
    tenants = tenant_counts(businesses)
    stats = BarEnrichment(businesses=len(businesses), bar_premises=len(premises))
    changed: list[Business] = []
    for b in businesses:
        if b.is_bar:
            stats.already_bar += 1
            continue
        why = bar_evidence(b, premises, tenants)
        if why is None:
            continue
        if why == "abc_license":
            stats.by_abc_license += 1
        elif why == "abc_dba":
            stats.by_abc_dba += 1
        else:
            stats.by_name += 1
        changed.append(b.model_copy(update={"is_bar": True}))
    if changed:
        await store.upsert_businesses(changed)
    stats.updated = len(changed)
    log.info("enrich businesses: %s", stats.as_dict())
    return stats


STEPS = {"businesses": enrich_businesses}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="precedent-enrich")
    parser.add_argument("step", choices=sorted(STEPS), help="enrichment step to run")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("PRECEDENT_DATA_DIR", "data")))
    parser.add_argument("--database-url", default=os.environ.get("PRECEDENT_DATABASE_URL"))
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    async def go() -> int:
        store = open_store(args.database_url, str(args.data_dir))
        try:
            stats = await STEPS[args.step](store)
        finally:
            await store.close()
        print(json.dumps({args.step: stats.as_dict()}))
        return 0

    return asyncio.run(go())


if __name__ == "__main__":
    sys.exit(main())
