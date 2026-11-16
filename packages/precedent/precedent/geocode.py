"""Geocoding contract. The SF implementation (DataSF Enterprise Addressing System + Nominatim fallback)
lives in `precedent.geocode_sf`; the memo chain only depends on this interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GeocodeResult:
    address: str  # display form, e.g. "995 Valencia St, San Francisco, CA 94110"
    normalized_address: str  # upper-cased street address without city/state
    lat: float
    lng: float
    parcel: str | None  # assessor block/lot when known
    zip_code: str | None
    source: str  # "datasf_eas" | "nominatim"
    source_url: str
    confidence: float  # 0..1


class Geocoder(Protocol):
    async def suggest(self, query: str, limit: int = 8) -> list[GeocodeResult]: ...
    async def geocode(self, address: str) -> GeocodeResult | None: ...
    async def close(self) -> None: ...
