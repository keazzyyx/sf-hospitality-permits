"""San Francisco geocoder: DataSF Enterprise Addressing System (EAS) first, Nominatim as a fallback.

Primary  — EAS base addresses, DataSF dataset ``3mea-di5p`` ("San Francisco Addresses - Enterprise
           Addressing System", ~224k active base addresses, refreshed nightly). Fields used:
           ``eas_baseid, address, address_number, address_number_suffix, street_name, street_type,
           zip_code, parcel_number, latitude, longitude``. EAS spells streets the city way:
           ``995 VALENCIA ST``, ``4004 03RD ST`` (single-digit ordinals are zero-padded),
           ``SAINT FRANCIS BLVD``, ``THE EMBARCADERO``; queries are normalised into that form.
           ``parcel_number`` is block+lot without a slash (``3609026`` → ``3609/026``); ~5% of base
           addresses have none.
Fallback — Nominatim (OpenStreetMap) ``/search?format=jsonv2``, bounded to the SF viewbox, at most
           1 request/second with the shared Permit Memo User-Agent (which carries a contact email), and
           any hit outside the SF bounding box is discarded. Confidence is capped at 0.6.

Results are memoised in an in-process LRU (normalised query → results, 24 h TTL).
"""

from __future__ import annotations

import os
import re
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import httpx

from precedent.geocode import GeocodeResult
from precedent.sources.base import USER_AGENT, RateLimiter

EAS_DATASET = "3mea-di5p"
EAS_RESOURCE = f"https://data.sf.gov/resource/{EAS_DATASET}.json"
EAS_HOME = f"https://data.sf.gov/d/{EAS_DATASET}"
EAS_FIELDS = "eas_baseid,address,address_number,address_number_suffix,street_name,street_type,zip_code,parcel_number,latitude,longitude"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# San Francisco (incl. Treasure Island, excl. the Farallones): lat/lng bounds used to reject fallback hits.
SF_BOUNDS = {"min_lat": 37.700, "max_lat": 37.835, "min_lng": -122.530, "max_lng": -122.350}
# Nominatim viewbox order: left,top,right,bottom (lng,lat,lng,lat)
SF_VIEWBOX = f"{SF_BOUNDS['min_lng']},{SF_BOUNDS['max_lat']},{SF_BOUNDS['max_lng']},{SF_BOUNDS['min_lat']}"

CACHE_TTL_SECONDS = 24 * 3600
CACHE_MAX_ENTRIES = 4096
NOMINATIM_MAX_CONFIDENCE = 0.6

STREET_TYPES: dict[str, str] = {
    "STREET": "ST",
    "STR": "ST",
    "ST": "ST",
    "AVENUE": "AVE",
    "AV": "AVE",
    "AVE": "AVE",
    "BOULEVARD": "BLVD",
    "BLVD": "BLVD",
    "BL": "BLVD",
    "DRIVE": "DR",
    "DR": "DR",
    "WAY": "WAY",
    "TERRACE": "TER",
    "TER": "TER",
    "COURT": "CT",
    "CT": "CT",
    "LANE": "LN",
    "LN": "LN",
    "PLACE": "PL",
    "PL": "PL",
    "ROAD": "RD",
    "RD": "RD",
    "CIRCLE": "CIR",
    "CIR": "CIR",
    "HIGHWAY": "HWY",
    "HWY": "HWY",
    "ALLEY": "ALY",
    "ALY": "ALY",
    "PLAZA": "PLZ",
    "PLZ": "PLZ",
    "LOOP": "LOOP",
    "ROW": "ROW",
    "WALK": "WALK",
    "PARK": "PARK",
    "STAIRWAY": "STWY",
    "STWY": "STWY",
}
_ORDINAL_WORDS = {
    "FIRST": "01ST",
    "SECOND": "02ND",
    "THIRD": "03RD",
    "FOURTH": "04TH",
    "FIFTH": "05TH",
    "SIXTH": "06TH",
    "SEVENTH": "07TH",
    "EIGHTH": "08TH",
    "NINTH": "09TH",
    "TENTH": "10TH",
    "ELEVENTH": "11TH",
    "TWELFTH": "12TH",
    "THIRTEENTH": "13TH",
    "FOURTEENTH": "14TH",
    "FIFTEENTH": "15TH",
    "SIXTEENTH": "16TH",
    "SEVENTEENTH": "17TH",
    "EIGHTEENTH": "18TH",
    "NINETEENTH": "19TH",
    "TWENTIETH": "20TH",
}
_DIRECTIONS = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST"}
_STREET_ALIASES = {"EMBARCADERO": "THE EMBARCADERO"}
_CITY_TOKENS = {"SAN FRANCISCO", "SF", "CA", "CALIFORNIA", "USA", "US", "UNITED STATES"}
_UNIT_RE = re.compile(
    r"(?:\b(?:APT|APARTMENT|UNIT|STE|SUITE|FL|FLOOR|RM|ROOM|SPC|SPACE|BLDG)\b\.?|#)\s*[\w-]+", re.I
)
_ZIP_RE = re.compile(r"\b(9[0-6]\d{3})(?:-\d{4})?\b")
_NUMBER_RE = re.compile(r"^(\d+)(?:-\d+[A-Z]?)?([A-Z])?$")
_ORDINAL_RE = re.compile(r"^(\d{1,3})(ST|ND|RD|TH)$")


@dataclass(frozen=True)
class ParsedAddress:
    number: str | None
    number_suffix: str | None
    street_name: str  # EAS form, e.g. "VALENCIA", "03RD", "SAINT FRANCIS"
    street_type: str | None  # EAS abbreviation, e.g. "ST"
    zip_code: str | None
    raw: str = field(compare=False, default="")

    @property
    def normalized(self) -> str:
        parts = [self.number or "", self.number_suffix or "", self.street_name, self.street_type or ""]
        return " ".join(p for p in parts if p)

    @property
    def cache_key(self) -> str:
        return f"{self.normalized}|{self.zip_code or ''}"


def _soql_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _norm_street_token(tok: str) -> str:
    m = _ORDINAL_RE.match(tok)
    if m:
        return f"{int(m.group(1)):02d}{m.group(2)}"
    return _ORDINAL_WORDS.get(tok, tok)


def parse_address(text: str) -> ParsedAddress:
    """Normalise free text ('995 Valencia Street, San Francisco, CA 94110') into EAS terms."""
    s = (text or "").upper()
    zips = [m for m in _ZIP_RE.finditer(s) if m.start() > 0]  # a leading 9xxxx is a street number
    zip_match = zips[-1] if zips else None
    zip_code = zip_match.group(1) if zip_match else None
    if zip_match:
        s = s[: zip_match.start()] + " " + s[zip_match.end() :]
    s = _UNIT_RE.sub(" ", s)
    # Drop city / state suffixes ("…, SAN FRANCISCO, CA")
    chunks = [c.strip() for c in s.split(",")]
    chunks = [c for i, c in enumerate(chunks) if i == 0 or c not in _CITY_TOKENS]
    s = " ".join(chunks)
    s = re.sub(r"\bSAN FRANCISCO\b(?:\s+CA(?:LIFORNIA)?)?\s*$", " ", s.strip())
    s = s.replace("'", "").replace("’", "")
    # "3286 1/2 MISSION" → half-number suffix; "450 & 470 FLORIDA ST" / "595 ALABAMA ST AND 2900 18TH ST" → first
    half = bool(re.match(r"^\s*\d+\s*(?:1/2|½)", s))
    s = re.sub(r"\b1/2\b|½", " ", s)
    s = re.sub(r"^(\s*\d+[A-Z]?)(?:\s*(?:&|\bAND\b|-)\s*\d+[A-Z]?\b)+", r"\1", s)
    s = re.split(r"\s(?:&|AND)\s+(?=\d)", s)[0]
    s = re.sub(r"[^\w\s-]", " ", s)
    tokens = s.split()

    number: str | None = None
    suffix: str | None = None
    if tokens:
        m = _NUMBER_RE.match(tokens[0])
        if m:
            number, suffix = str(int(m.group(1))), m.group(2)
            tokens = tokens[1:]
            if (
                suffix is None
                and len(tokens) >= 2
                and len(tokens[0]) == 1
                and tokens[0].isalpha()
                and tokens[0] not in _DIRECTIONS
                and tokens[1] not in STREET_TYPES
            ):
                suffix, tokens = tokens[0], tokens[1:]  # "990 A VALENCIA ST"
            if suffix is None and half:
                suffix = "½"
    if len(tokens) >= 2 and tokens[0] in _DIRECTIONS:
        tokens[0] = _DIRECTIONS[tokens[0]]  # "S VAN NESS AVE" → "SOUTH VAN NESS AVE"
    if len(tokens) >= 3 and len(tokens[-1]) == 1 and tokens[-1].isalpha() and tokens[-2] in STREET_TYPES:
        tokens = tokens[:-1]  # trailing unit letter: "3158 MISSION ST A"
    tokens = [t.strip("-") for t in tokens if t.strip("-")]
    street_type: str | None = None
    if len(tokens) >= 2 and tokens[-1] in STREET_TYPES:
        street_type = STREET_TYPES[tokens[-1]]
        tokens = tokens[:-1]
    if len(tokens) >= 2 and tokens[0] == "ST":
        tokens[0] = "SAINT"
    tokens = [_norm_street_token(t) for t in tokens]
    street_name = " ".join(tokens)
    street_name = _STREET_ALIASES.get(street_name, street_name)
    return ParsedAddress(
        number=number,
        number_suffix=suffix,
        street_name=street_name,
        street_type=street_type,
        zip_code=zip_code,
        raw=text,
    )


def format_parcel(parcel_number: str | None) -> str | None:
    """'3609026' → '3609/026'; '2051A010' → '2051A/010'; '6250007B' → '6250/007B'."""
    p = (parcel_number or "").strip().upper()
    if len(p) < 7:
        return None
    if len(p) >= 8 and p[4].isalpha():
        return f"{p[:5]}/{p[5:]}"
    return f"{p[:4]}/{p[4:]}"


def in_sf(lat: float, lng: float) -> bool:
    b = SF_BOUNDS
    return b["min_lat"] <= lat <= b["max_lat"] and b["min_lng"] <= lng <= b["max_lng"]


def _display(normalized: str, zip_code: str | None) -> str:
    def title(tok: str) -> str:
        if re.match(r"^0\d(ST|ND|RD|TH)$", tok):
            tok = tok[1:]
        return tok.lower() if re.match(r"^\d+(st|nd|rd|th)$", tok, re.I) else tok.capitalize()

    street = " ".join(title(t) for t in normalized.split())
    return f"{street}, San Francisco, CA{' ' + zip_code if zip_code else ''}"


class _TTLCache:
    def __init__(self, ttl: float, max_entries: int, clock: Callable[[], float]) -> None:
        self._ttl, self._max, self._clock = ttl, max_entries, clock
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> tuple[bool, Any]:
        hit = self._data.get(key)
        if hit is None:
            return False, None
        expires, value = hit
        if expires < self._clock():
            del self._data[key]
            return False, None
        self._data.move_to_end(key)
        return True, value

    def put(self, key: str, value: Any) -> None:
        self._data[key] = (self._clock() + self._ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)


class SFGeocoder:
    """`precedent.geocode.Geocoder` for San Francisco. Async; pass a shared httpx client or let it make one."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        eas_rate_per_second: float = 4.0,
        nominatim_rate_per_second: float = 1.0,
        use_nominatim: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._eas_limiter = RateLimiter(eas_rate_per_second)
        self._nominatim_limiter = RateLimiter(nominatim_rate_per_second)
        self._use_nominatim = use_nominatim
        self._cache = _TTLCache(CACHE_TTL_SECONDS, CACHE_MAX_ENTRIES, clock)
        self.stats = {"eas_requests": 0, "nominatim_requests": 0, "cache_hits": 0}

    # -- plumbing -------------------------------------------------------------------------------------------
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True
            )
            self._owns_client = True
        return self._client

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None

    async def _eas(
        self, where: str, *, limit: int, order: str = "street_name,address_number"
    ) -> list[dict[str, Any]]:
        params = {"$select": EAS_FIELDS, "$where": where, "$limit": str(limit), "$order": order}
        headers = {"User-Agent": USER_AGENT}
        token = os.environ.get("SOCRATA_APP_TOKEN")
        if token:
            headers["X-App-Token"] = token
        await self._eas_limiter.wait()
        self.stats["eas_requests"] += 1
        resp = await self._http().get(EAS_RESOURCE, params=params, headers=headers)
        resp.raise_for_status()
        rows = resp.json()
        return rows if isinstance(rows, list) else []

    async def _nominatim(self, query: str, limit: int) -> list[GeocodeResult]:
        params = {
            "q": f"{query}, San Francisco, CA",
            "format": "jsonv2",
            "addressdetails": "1",
            "countrycodes": "us",
            "viewbox": SF_VIEWBOX,
            "bounded": "1",
            "limit": str(max(1, min(limit, 10))),
        }
        await self._nominatim_limiter.wait()
        self.stats["nominatim_requests"] += 1
        resp = await self._http().get(NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        out: list[GeocodeResult] = []
        for hit in resp.json() or []:
            res = self._from_nominatim(hit, parse_address(query))
            if res is not None:
                out.append(res)
        return out

    # -- row → result ---------------------------------------------------------------------------------------
    @staticmethod
    def _from_eas(
        row: dict[str, Any], confidence: float, *, normalized: str | None = None, keep_parcel: bool = True
    ) -> GeocodeResult | None:
        try:
            lat, lng = float(row["latitude"]), float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            return None
        address = str(row.get("address") or "").upper().strip()
        zip_code = str(row["zip_code"]) if row.get("zip_code") else None
        norm = normalized or address
        return GeocodeResult(
            address=_display(norm, zip_code),
            normalized_address=norm,
            lat=lat,
            lng=lng,
            parcel=format_parcel(row.get("parcel_number")) if keep_parcel else None,
            zip_code=zip_code,
            source="datasf_eas",
            source_url=f"{EAS_RESOURCE}?eas_baseid={row.get('eas_baseid')}"
            if row.get("eas_baseid")
            else EAS_HOME,
            confidence=round(confidence, 3),
        )

    @staticmethod
    def _from_nominatim(hit: dict[str, Any], wanted: ParsedAddress) -> GeocodeResult | None:
        try:
            lat, lng = float(hit["lat"]), float(hit["lon"])
        except (KeyError, TypeError, ValueError):
            return None
        if not in_sf(lat, lng):
            return None
        addr = hit.get("address") or {}
        road = parse_address(f"1 {addr.get('road', '')}") if addr.get("road") else None
        house = str(addr.get("house_number") or "").split(";")[0].strip()
        if road is not None and road.street_name:
            normalized = " ".join(p for p in [house, road.street_name, road.street_type or ""] if p)
        else:
            normalized = str(hit.get("name") or hit.get("display_name") or "").upper().split(",")[0]
        if (
            wanted.number
            and wanted.street_name
            and road is not None
            and road.street_name != wanted.street_name
        ):
            return None  # a different street than the one asked for (Nominatim's fuzzy match): not a geocode
        confidence = 0.35
        if road is not None and wanted.street_name and road.street_name == wanted.street_name:
            confidence += 0.15
        if house and wanted.number and house == wanted.number:
            confidence += 0.1
        osm = (
            f"https://www.openstreetmap.org/{hit.get('osm_type')}/{hit.get('osm_id')}"
            if hit.get("osm_id")
            else NOMINATIM_URL
        )
        zip_code = str(addr.get("postcode"))[:5] if addr.get("postcode") else None
        return GeocodeResult(
            address=str(hit.get("display_name") or normalized),
            normalized_address=normalized,
            lat=lat,
            lng=lng,
            parcel=None,
            zip_code=zip_code,
            source="nominatim",
            source_url=osm,
            confidence=round(min(confidence, NOMINATIM_MAX_CONFIDENCE), 3),
        )

    # -- public API -----------------------------------------------------------------------------------------
    async def suggest(self, query: str, limit: int = 8) -> list[GeocodeResult]:
        """Autocomplete: street-number prefix + street-name prefix over EAS, ranked by closeness."""
        parsed = parse_address(query)
        if not parsed.street_name and not parsed.number:
            return []
        key = f"suggest:{parsed.cache_key}:{limit}"
        hit, cached = self._cache.get(key)
        if hit:
            self.stats["cache_hits"] += 1
            return list(cached)

        clauses: list[str] = []
        if parsed.number:
            clauses.append(f"address like {_soql_quote(parsed.number + '%')}")
        if parsed.street_name:
            street = (
                f"{parsed.street_name} {parsed.street_type}" if parsed.street_type else parsed.street_name
            )
            clauses.append(f"street_full_street_name like {_soql_quote(street + '%')}")
        if parsed.zip_code:
            clauses.append(f"zip_code = {parsed.zip_code}")
        rows = await self._eas(" AND ".join(clauses), limit=max(limit * 5, 25))

        def rank(row: dict[str, Any]) -> tuple[int, int, int, str]:
            num = str(row.get("address_number") or "")
            exact_num = 0 if parsed.number and num == parsed.number else 1
            exact_street = 0 if row.get("street_name") == parsed.street_name else 1
            return (exact_num, exact_street, len(num), str(row.get("address") or ""))

        results: list[GeocodeResult] = []
        seen: set[str] = set()
        for row in sorted(rows, key=rank):
            address = str(row.get("address") or "").upper()
            if address in seen:
                continue
            seen.add(address)
            exact_num, exact_street, _, _ = rank(row)
            conf = 1.0 if address == parsed.normalized else 0.9 - 0.1 * exact_num - 0.1 * exact_street
            res = self._from_eas(row, conf)
            if res is not None:
                results.append(res)
            if len(results) >= limit:
                break
        if not results and self._use_nominatim and parsed.number and len(parsed.street_name) >= 3:
            results = (await self._nominatim(parsed.normalized or query, limit))[:limit]
        self._cache.put(key, tuple(results))
        return results

    async def geocode(self, address: str) -> GeocodeResult | None:
        """Best match: exact EAS address → number + street name → nearest same-side number → Nominatim."""
        parsed = parse_address(address)
        if not parsed.street_name:
            return None
        key = f"geocode:{parsed.cache_key}"
        hit, cached = self._cache.get(key)
        if hit:
            self.stats["cache_hits"] += 1
            return cached  # type: ignore[no-any-return]
        result = await self._geocode_uncached(parsed)
        self._cache.put(key, result)
        return result

    async def _geocode_uncached(self, parsed: ParsedAddress) -> GeocodeResult | None:
        if parsed.number:
            if parsed.street_type:
                rows = await self._eas(f"address = {_soql_quote(parsed.normalized)}", limit=10)
                best = _pick_zip(rows, parsed.zip_code)
                if best is not None:
                    zip_ok = parsed.zip_code is None or str(best.get("zip_code")) == parsed.zip_code
                    return self._from_eas(best, 1.0 if zip_ok else 0.95)
            # number + street name, any street type / number suffix
            rows = await self._eas(
                f"address_number = {parsed.number} AND street_name = {_soql_quote(parsed.street_name)}",
                limit=20,
            )
            best = _pick_zip(
                [r for r in rows if not parsed.street_type or r.get("street_type") == parsed.street_type]
                or rows,
                parsed.zip_code,
            )
            if best is not None:
                return self._from_eas(best, 0.9)
            # nearest existing number on the same side of the same street (within 40)
            n = int(parsed.number)
            where = (
                f"street_name = {_soql_quote(parsed.street_name)} AND address_number between {max(0, n - 40)} AND {n + 40}"
                + (f" AND street_type = {_soql_quote(parsed.street_type)}" if parsed.street_type else "")
            )
            rows = await self._eas(where, limit=100)
            same_side = [r for r in rows if _int(r.get("address_number")) % 2 == n % 2] or rows
            if same_side:
                nearest = min(same_side, key=lambda r: abs(_int(r.get("address_number")) - n))
                return self._from_eas(nearest, 0.7, normalized=parsed.normalized, keep_parcel=False)
        if self._use_nominatim:
            hits = await self._nominatim(parsed.normalized or parsed.raw, 3)
            if hits:
                return max(hits, key=lambda h: h.confidence)
        return None

    async def geocode_many(
        self, addresses: Iterable[str], *, chunk: int = 40
    ) -> dict[str, GeocodeResult | None]:
        """Bulk exact lookup (`address in (...)`, `chunk` per request), then per-address fallback for misses."""
        parsed = {a: parse_address(a) for a in addresses}
        out: dict[str, GeocodeResult | None] = {}
        pending: dict[str, list[str]] = {}
        for raw, p in parsed.items():
            if not p.street_name:
                out[raw] = None
                continue
            hit, cached = self._cache.get(f"geocode:{p.cache_key}")
            if hit:
                self.stats["cache_hits"] += 1
                out[raw] = cached
            elif p.number and p.street_type:
                pending.setdefault(p.normalized, []).append(raw)
        keys = list(pending)
        for i in range(0, len(keys), chunk):
            batch = keys[i : i + chunk]
            rows = await self._eas(
                "address in (" + ",".join(_soql_quote(k) for k in batch) + ")", limit=len(batch) * 6
            )
            by_addr: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                by_addr.setdefault(str(row.get("address") or "").upper(), []).append(row)
            for norm in batch:
                for raw in pending[norm]:
                    p = parsed[raw]
                    best = _pick_zip(by_addr.get(norm, []), p.zip_code)
                    if best is None:
                        continue
                    zip_ok = p.zip_code is None or str(best.get("zip_code")) == p.zip_code
                    res = self._from_eas(best, 1.0 if zip_ok else 0.95)
                    out[raw] = res
                    self._cache.put(f"geocode:{p.cache_key}", res)
        for raw in parsed:
            if raw not in out:
                out[raw] = await self.geocode(raw)
        return out


def _int(value: Any) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return -(10**6)


def _pick_zip(rows: list[dict[str, Any]], zip_code: str | None) -> dict[str, Any] | None:
    rows = [r for r in rows if r.get("latitude") and r.get("longitude")]
    if not rows:
        return None
    if zip_code:
        for r in rows:
            if str(r.get("zip_code")) == zip_code:
                return r
    return rows[0]


__all__ = [
    "EAS_DATASET",
    "EAS_HOME",
    "GeocodeResult",
    "ParsedAddress",
    "SFGeocoder",
    "format_parcel",
    "in_sf",
    "parse_address",
]
