"""Census-tract licence concentration, for the alcohol row. Pure code: no model call, no clock, no randomness.

What this answers: which census tract an address is in, how many on-sale or off-sale retail licences ABC has
authorised for that tract, how many are active there, and whether the tract is over its authorised number.

OVER-CONCENTRATION IS NEVER A BLOCKER AND NEVER "NOT PERMITTED". California Business and Professions Code
§ 23958.4(b) lets the licence still issue when public convenience or necessity would be served. So the only
thing this module ever returns for a tract that is over is the further-review qualifier
"Further review: public convenience or necessity finding likely required". `ConcentrationFinding.status` has
one allowed value, "further_review", and the class refuses any other.

THE RULE (§ 23958.4(a)(2) and (3), read 2026-11-10 from the Internet Archive capture of 2025-05-01 of
leginfo.legislature.ca.gov; text as amended by Stats. 2019, ch. 29, sec. 46):

    "the ratio of on-sale retail licenses to population in the census tract ... exceeds the ratio of on-sale
    retail licenses to population in the county"          (the off-sale sentence is the same with "off-sale")

"Exceeds" is strictly greater. ABC's authorised number for a tract is the tract population divided by the
county's people-per-licence figure, rounded down (true of all 244 San Francisco tracts in the September 2026
report). For a whole number of licences, "licences / population exceeds 1 / county figure" is therefore exactly
"licences > authorised". A tract with exactly its authorised number is NOT over (`is_over`).

WHICH LICENCES COUNT (§ 23958.4(c)(5)):
  off-sale retail  "Type 20 (off-sale beer and wine) and Type 21 (off-sale general)". A closed list.
  on-sale retail   "All retail on-sale licenses, except" Types 43, 44, 45, 46, 53, 54, 55, 56 and 62 (trains,
                   boats, airplanes, vessels). The statute does not number the types it includes, so
                   ON_SALE_RETAIL_TYPES below is this module's reading of ABC's published list of licence types
                   (titles as in precedent.sources.abc.LICENSE_TYPES): every type that is an on-sale licence for
                   a premises in its own right, less the nine excluded. Permits that ride on another licence
                   (58 caterer's permit, 66 controlled access cabinet, 68 portable bar, 77 event permit,
                   86 instructional tasting) and manufacturer, importer and wholesaler types are not counted.
                   ABC's own per-type counting list was not available and is not confirmed.

WHAT "ACTIVE" MEANS HERE: a file number with at least one row in ABC's export that is a licence
(`lic_or_app` = "LIC"), has status ACTIVE and is of a counted type. Licences are counted, not rows: a file with
duplicate licences or several counted types counts once per kind. Rows marked "APP" are applications, carry no
issue or expiry date and are often an older file number superseded by a newer licence at the same address, so
they are not counted. Suspended, surrendered, revocation-pending and Rule 64(b) licences are not "active"; they
are reported separately (`issued_not_active`).

THE FIGURES are read once from two bundled files and never change at run time:
  data/sf_census_tracts.json   2020 Census tract boundaries for San Francisco County (U.S. Census Bureau
                               TIGER/Line 2020), not simplified. ABC's 244 tract numbers are the 2020 numbers.
  data/sf_tract_licences.json  per tract: population and authorised numbers (ABC census tract authorisations,
                               September 2026) and active counts (ABC daily export of 2026-11-09).
Both dates travel with every answer.

NOT DECIDED HERE: whether the test applies to this application at all (it applies to an original licence or
a premises-to-premises transfer, § 23958.4(a): see TRANSACTIONS_TESTED), and the statute's other ground for
undue concentration, a crime reporting district with 20 percent more reported crimes than average
(§ 23958.4(a)(1)), for which there is no data here. A tract that is not over says nothing about that ground.

LIMITS, which a reader of the numbers should know:
  - The active count follows the tract number ABC wrote on each licence, not the licence's position. Checked
    on the 434 licences in ZIP 94110 that have a geocoded point: 399 carry the number of the 2020 tract their
    point is in, 32 carry another 2020 tract's number (neighbours on one block face can differ), 3 an older
    number. So a tract's count can be a few licences off in either direction.
  - 88 active on-sale and 7 active off-sale licences carry a blank or older tract number and are in no tract's
    count (`Concentration.older_number_not_placed` says how many might belong to a tract).
  - ABC's own count of licences per tract is not published in the report; this count is ours.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, NamedTuple, cast, get_args

Kind = Literal["on_sale", "off_sale"]
KINDS: tuple[Kind, ...] = get_args(Kind)

DATA_DIR = Path(__file__).resolve().parent / "data"
TRACTS_FILE = DATA_DIR / "sf_census_tracts.json"
LICENCES_FILE = DATA_DIR / "sf_tract_licences.json"

# ---- the fixed words ------------------------------------------------------------------------------------------

PCN_STATUS: Literal["further_review"] = "further_review"
PCN_STATUS_NOTE = "public convenience or necessity finding likely required"
PCN_SENTENCE = "Further review: public convenience or necessity finding likely required"
PCN_CITATION = "California Business and Professions Code § 23958.4"
PCN_SOURCE_URL = (
    "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=BPC&sectionNum=23958.4."
)
RULE_ID = "alcohol.tract_concentration"

# ---- the licence types that count (§ 23958.4(c)(5)) -----------------------------------------------------------

LICENCE_TYPES_SOURCE = (
    "California Business and Professions Code § 23958.4(c)(5), as amended by Stats. 2019, ch. 29, sec. 46; read "
    "2026-11-10 from web.archive.org/web/20250501074342/https://leginfo.legislature.ca.gov/faces/"
    "codes_displaySection.xhtml?lawCode=BPC&sectionNum=23958.4. Type titles: ABC's published list of licence types."
)
# (c)(5)(A): "Off-sale retail licenses: Type 20 (off-sale beer and wine) and Type 21 (off-sale general)."
OFF_SALE_RETAIL_TYPES: frozenset[str] = frozenset({"20", "21"})
# (c)(5)(B): "All retail on-sale licenses, except" these nine.
ON_SALE_TYPES_EXCLUDED_BY_STATUTE: frozenset[str] = frozenset(
    {"43", "44", "45", "46", "53", "54", "55", "56", "62"}
)
# The on-sale licence types on ABC's published list, less the nine above. The statute gives the rule, not the
# numbers: this list is a reading of the type titles, and ABC's own counting list is not confirmed.
ON_SALE_RETAIL_TYPES: frozenset[str] = frozenset(
    {
        "40",  # On-Sale Beer
        "41",  # On-Sale Beer & Wine - Eating Place
        "42",  # On-Sale Beer & Wine - Public Premises
        "47",  # On-Sale General - Eating Place
        "48",  # On-Sale General - Public Premises
        "49",  # On-Sale General - Seasonal
        "50",  # On-Sale General Club
        "51",  # Club
        "52",  # Veteran's Club
        "57",  # Special On-Sale General
        "59",  # On-Sale Beer and Wine - Seasonal
        "60",  # On-Sale Beer - Seasonal
        "61",  # On-Sale Beer - Public Premises
        "63",  # On-Sale Special Beer and Wine Hospital
        "64",  # Special On-Sale General for Nonprofit Theater Company
        "65",  # Special On-Sale Beer and Wine Symphony
        "67",  # Bed and Breakfast Inn
        "69",  # Special On-Sale Beer and Wine Theater
        "70",  # On-Sale General - Restrictive Service
        "71",  # Special On-Sale General for a For-Profit Theater within the City and County of San Francisco
        "72",  # Special On-Sale General for a For-Profit Theater within the county of Napa
        "75",  # Brewpub-Restaurant
        "76",  # On-Sale General Maritime Museum Association
        "78",  # On-Sale General for Wine, Food and Art Cultural Museum, and Educational Center
        "80",  # Bed and Breakfast Inn - General
        "83",  # General On-Sale License to Caterer
        "87",  # Special On-Sale General License for Specified Census Tracts in the City/County of San Francisco
        "88",  # Special On-Sale General License for a For-Profit Cemetery with Specified Characteristics
        "90",  # On-Sale General - Music Venue
        "99",  # On-Sale General for Special Use
    }
)
RETAIL_TYPES: dict[Kind, frozenset[str]] = {
    "on_sale": ON_SALE_RETAIL_TYPES,
    "off_sale": OFF_SALE_RETAIL_TYPES,
}
KIND_WORDS: dict[Kind, str] = {"on_sale": "on-sale", "off_sale": "off-sale"}

# § 23958.4(a): the test applies to "the applicant premises for an original or premises-to-premises transfer of
# any retail license". A person-to-person transfer, or a licence already held at the premises, is not tested.
# Values are the profile's `alcohol_transaction`. Also not evaluated here: (f), "This section shall not apply if
# the premises have been licensed and operated with the same type license within 90 days of the application".
TRANSACTIONS_TESTED: frozenset[str] = frozenset({"new_licence", "premises_transfer"})


def kind_for_licence_type(licence_type: str | None) -> Kind | None:
    """Which count a licence type belongs to: "41" -> on_sale, "21" -> off_sale. None for a type that is not a
    retail licence under § 23958.4(c)(5) (a permit, a manufacturer, one of the nine excluded types)."""
    if licence_type is None or not licence_type.strip():
        return None
    code = licence_type.strip().zfill(2)
    for kind in KINDS:
        if code in RETAIL_TYPES[kind]:
            return kind
    return None


# Statuses in ABC's export. ACTIVE is the only one counted as active; the others are licences that still exist.
ACTIVE_STATUS = "ACTIVE"
ISSUED_NOT_ACTIVE_STATUSES: frozenset[str] = frozenset({"SUSPEN", "REVPEN", "SUREND", "R64B"})
LICENCE_RECORD = "LIC"  # `lic_or_app`: "LIC" is a licence, "APP" an application


# ---- tract numbers --------------------------------------------------------------------------------------------


def normalise_tract(value: str | None) -> str | None:
    """A tract number as ABC's report writes it: "208.01", "103.00".

    Accepts the export's "0208.01", a bare "103", and the Census Bureau's six-digit code "020801". Returns None
    for a blank or anything that is not a tract number.
    """
    if value is None:
        return None
    text = value.strip()
    if not text or not text.isascii():
        return None
    if "." not in text and len(text) == 6 and text.isdigit():  # TRACTCE: four digits and two decimals
        text = f"{text[:4]}.{text[4:]}"
    whole, _, part = text.partition(".")
    if not whole.isdigit() or (part and not part.isdigit()) or len(part) > 2:
        return None
    return f"{int(whole)}.{part.ljust(2, '0')}"


# ---- boundaries and point in polygon --------------------------------------------------------------------------

Point = tuple[float, float]  # (lng, lat)
Ring = tuple[Point, ...]


@dataclass(frozen=True)
class _Shape:
    tract: str
    west: float
    south: float
    east: float
    north: float
    polygons: tuple[tuple[Ring, ...], ...]  # each polygon: the outer ring, then its holes


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def _boundaries() -> tuple[dict[str, str], tuple[_Shape, ...]]:
    """The boundary file, read once: its source note, and the tracts in number order (so an answer never
    depends on file order)."""
    data = _read_json(TRACTS_FILE)
    source = {key: str(value) for key, value in data["source"].items()}
    raw = data["tracts"]
    shapes: list[_Shape] = []
    for tract in sorted(raw, key=_tract_sort_key):
        polygons = tuple(
            tuple(tuple((float(x), float(y)) for x, y in ring) for ring in polygon)
            for polygon in raw[tract]["polygons"]
        )
        xs = [x for polygon in polygons for x, _ in polygon[0]]
        ys = [y for polygon in polygons for _, y in polygon[0]]
        shapes.append(_Shape(tract, min(xs), min(ys), max(xs), max(ys), polygons))
    return source, tuple(shapes)


def _shapes() -> tuple[_Shape, ...]:
    return _boundaries()[1]


def _tract_sort_key(tract: str) -> tuple[int, int]:
    whole, _, part = tract.partition(".")
    return int(whole), int(part or 0)


def _in_ring(lng: float, lat: float, ring: Ring) -> bool:
    """Ray casting, half-open on each edge, so a point on a shared edge falls in exactly one of two neighbours."""
    inside = False
    x1, y1 = ring[-1]
    for x2, y2 in ring:
        if (y1 > lat) != (y2 > lat) and lng < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
        x1, y1 = x2, y2
    return inside


def _in_shape(lng: float, lat: float, shape: _Shape) -> bool:
    if not (shape.west <= lng <= shape.east and shape.south <= lat <= shape.north):
        return False
    for polygon in shape.polygons:
        if _in_ring(lng, lat, polygon[0]) and not any(_in_ring(lng, lat, hole) for hole in polygon[1:]):
            return True
    return False


def tract_at(lat: float, lng: float) -> str | None:
    """The 2020 census tract containing the point, as ABC writes it ("208.01"), or None outside San Francisco
    County.

    The county's two water tracts (9901.00 Pacific, 9902.00 Bay) are tracts like any other and are returned.
    Boundaries are the Census Bureau's, accurate to a few metres; most run down the middle of a street, so a
    point geocoded to the street centre line can land on either side.
    """
    if not (math.isfinite(lat) and math.isfinite(lng)):
        return None
    for shape in _shapes():
        if _in_shape(lng, lat, shape):
            return shape.tract
    return None


def tracts_with_polygon() -> tuple[str, ...]:
    """Every tract number in the boundary file, in number order."""
    return tuple(shape.tract for shape in _shapes())


def boundary_source() -> dict[str, str]:
    """Where the boundaries came from: name, url, vintage, downloaded_on and the rest of the file's own note."""
    return dict(_boundaries()[0])


# ---- counting licences in ABC's export (used to build the data file and to check it) ---------------------------


class ExportRow(NamedTuple):
    """The five columns of one row of ABC's daily export that the count reads."""

    census_tract: str | None
    file_number: str
    license_type: str
    lic_or_app: str
    type_status: str


@dataclass(frozen=True)
class LicenceCounts:
    active_on_sale: int = 0
    active_off_sale: int = 0
    issued_not_active_on_sale: int = 0
    issued_not_active_off_sale: int = 0

    def active(self, kind: Kind) -> int:
        return self.active_on_sale if kind == "on_sale" else self.active_off_sale

    def issued_not_active(self, kind: Kind) -> int:
        return self.issued_not_active_on_sale if kind == "on_sale" else self.issued_not_active_off_sale


def count_licences(rows: Iterable[ExportRow]) -> dict[str, LicenceCounts]:
    """Retail licences per tract from rows of ABC's export. Licences (file numbers) are counted, not rows.

    A file is an active licence of a kind in a tract when it has a row there that is a licence ("LIC"), has
    status ACTIVE and is of a counted type for that kind. A file with no such row but a licence row of a counted
    type that is suspended, surrendered, revocation pending or under Rule 64(b) is "issued, not active".
    Application rows ("APP") and pending rows are not counted.

    Keys are tract numbers as ABC's report writes them; a row whose tract is blank or not a number is kept under
    the text as written (blank: ""). Tracts with nothing to count are left out.
    """
    active: dict[Kind, dict[str, set[str]]] = {kind: {} for kind in KINDS}
    other: dict[Kind, dict[str, set[str]]] = {kind: {} for kind in KINDS}
    for row in rows:
        if row.lic_or_app.strip().upper() != LICENCE_RECORD:
            continue
        status = row.type_status.strip().upper()
        if status != ACTIVE_STATUS and status not in ISSUED_NOT_ACTIVE_STATUSES:
            continue
        licence_type = row.license_type.strip().zfill(2)
        tract = normalise_tract(row.census_tract) or (row.census_tract or "").strip()
        file_number = row.file_number.strip()
        for kind in KINDS:
            if licence_type in RETAIL_TYPES[kind]:
                bucket = active if status == ACTIVE_STATUS else other
                bucket[kind].setdefault(tract, set()).add(file_number)
    counts: dict[str, LicenceCounts] = {}
    for tract in sorted({t for kind in KINDS for t in (*active[kind], *other[kind])}):
        on, off = active["on_sale"].get(tract, set()), active["off_sale"].get(tract, set())
        counts[tract] = LicenceCounts(
            active_on_sale=len(on),
            active_off_sale=len(off),
            issued_not_active_on_sale=len(other["on_sale"].get(tract, set()) - on),
            issued_not_active_off_sale=len(other["off_sale"].get(tract, set()) - off),
        )
    return counts


# ---- concentration --------------------------------------------------------------------------------------------


ACTIVE_DESCRIBED = "ABC's licence export of"


def is_over(active: int, authorised: int) -> bool:
    """§ 23958.4(a): the tract's ratio "exceeds" the county's. Strictly more licences than authorised; a tract
    with exactly its authorised number is not over."""
    return active > authorised


@dataclass(frozen=True)
class Concentration:
    """One tract and one kind of licence: ABC's authorised number against the active licences counted."""

    tract: str
    kind: Kind
    authorised: int
    active: int
    population: int
    authorised_as_of: str  # "2026-09": the month ABC's authorisations report is dated
    active_as_of: str  # "2026-11-09": the date of ABC's export the active licences were counted from
    authorised_source: str
    active_source: str
    # Licences of this kind that exist but are not active (suspended, surrendered, revocation pending, Rule 64(b)).
    # Not part of `active` and not part of the over test.
    issued_not_active: int = 0
    # Active licences of this kind whose tract number in the export is not one of ABC's 244 but has the same
    # whole number ("208.00" for 208.01): older tract numbers ABC has not updated. They belong to this tract or
    # to a neighbour with the same whole number, cannot be placed, and are not part of `active`. When this is not
    # zero, `active` is a floor, and "not over" may be wrong by up to this many.
    older_number_not_placed: int = 0
    # how the line names where the active count is from, before its date
    active_described: str = "ABC's licence export of"

    @property
    def over(self) -> bool:
        return is_over(self.active, self.authorised)


@lru_cache(maxsize=1)
def _licence_data() -> dict[str, Any]:
    return _read_json(LICENCES_FILE)


def _figures() -> dict[str, Any]:
    """The figures `concentration` reads: the bundled file, or, inside a backtest case, that case's figures with
    the licences counted as they stood on its cut-off day (app.backtest.asof.TRACT_DATA). A live report never sets
    the override."""
    from app.backtest.asof import TRACT_DATA

    override = TRACT_DATA.get()
    return override if override is not None else _licence_data()


def tracts_with_figures() -> tuple[str, ...]:
    """Every tract in ABC's authorisations report, in number order."""
    return tuple(sorted(_licence_data()["tracts"], key=_tract_sort_key))


def tracts_without_polygon() -> tuple[str, ...]:
    """Tracts in ABC's report that the boundary file does not have. Empty for the bundled files."""
    have = set(tracts_with_polygon())
    return tuple(t for t in tracts_with_figures() if t not in have)


def licence_figures_source() -> dict[str, Any]:
    """The two source notes of the figures file ("authorised" and "active"), as written there."""
    data = _licence_data()
    return {"authorised": dict(data["authorised"]), "active": dict(data["active"])}


def concentration(tract: str, kind: Kind) -> Concentration | None:
    """ABC's authorised number, the active count and both dates for one tract. None when the tract is not in
    ABC's report (a tract number of another vintage, or outside San Francisco County)."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, not {kind!r}")
    key = normalise_tract(tract)
    data = _figures()
    row = data["tracts"].get(key) if key else None
    if key is None or row is None:
        return None
    whole = key.partition(".")[0]
    older = sum(
        int(counts[f"active_{kind}"])
        for number, counts in data["not_placed"].items()
        if number.partition(".")[0] == whole
    )
    return Concentration(
        tract=key,
        kind=kind,
        authorised=int(row[f"authorised_{kind}"]),
        active=int(row[f"active_{kind}"]),
        population=int(row["population"]),
        authorised_as_of=str(data["authorised"]["as_of"]),
        active_as_of=str(data["active"]["export_date"]),
        authorised_source=str(data["authorised"]["source"]),
        active_source=str(data["active"]["source"]),
        issued_not_active=int(row[f"issued_not_active_{kind}"]),
        older_number_not_placed=older,
        active_described=str(data["active"].get("described_as") or ACTIVE_DESCRIBED),
    )


# ---- the report row -------------------------------------------------------------------------------------------

_MONTHS = (
    "January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
    "November", "December",
)  # fmt: skip


def plain_date(value: str) -> str:
    """Write "2026-11-09" as "9 November 2026" and "2026-09" as "September 2026"; anything else as given."""
    parts = value.split("-")
    if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts) or not 1 <= int(parts[1]) <= 12:
        return value
    month_year = f"{_MONTHS[int(parts[1]) - 1]} {int(parts[0])}"
    return f"{int(parts[2])} {month_year}" if len(parts) == 3 else month_year


def concentration_line(c: Concentration) -> str:
    """One plain line with the two numbers and their dates. The same wording whether or not the tract is over."""
    word = KIND_WORDS[c.kind]
    licences = "licence" if c.active == 1 else "licences"
    return (
        f"Census tract {c.tract}: {c.active} active {word} retail {licences} in {c.active_described} "
        f"{plain_date(c.active_as_of)}, against {c.authorised} authorised in ABC's census tract authorisations of "
        f"{plain_date(c.authorised_as_of)}."
    )


@dataclass(frozen=True)
class ConcentrationFinding:
    """What the alcohol row prints when the tract is over its authorised number. The words are fixed.

    `status` can only be "further_review". Over-concentration alone never makes a row a potential blocker or not
    permitted (§ 23958.4(b): the licence may still issue on a finding of public convenience or necessity), and
    this class cannot be built with any other status.
    """

    line: str  # the two numbers and their dates
    status: Literal["further_review"] = PCN_STATUS
    status_note: str = PCN_STATUS_NOTE
    sentence: str = PCN_SENTENCE
    citation: str = PCN_CITATION
    source_url: str = PCN_SOURCE_URL
    rule_id: str = RULE_ID

    def __post_init__(self) -> None:
        fixed = {
            "status": PCN_STATUS,
            "status_note": PCN_STATUS_NOTE,
            "sentence": PCN_SENTENCE,
            "citation": PCN_CITATION,
        }
        for name, value in fixed.items():
            if getattr(self, name) != value:
                raise ValueError(
                    f"over-concentration is only ever {PCN_SENTENCE!r} ({PCN_CITATION}); {name} cannot be changed"
                )


def over_concentration_finding(c: Concentration | None) -> ConcentrationFinding | None:
    """The fixed further-review qualifier when the tract is over its authorised number; otherwise None.

    None means "this fact changes nothing": the tract is at or under its number, or has no figures. It never
    means allowed. The only finding this can return is further review; it never returns a blocker or not
    permitted.
    """
    if c is None or not c.over:
        return None
    return ConcentrationFinding(line=concentration_line(c))
