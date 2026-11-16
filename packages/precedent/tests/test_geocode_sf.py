"""SFGeocoder against saved DataSF EAS (3mea-di5p) and Nominatim responses — no network."""

from __future__ import annotations

import asyncio
import itertools
import json
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from precedent.geocode import Geocoder
from precedent.geocode_sf import (
    EAS_RESOURCE,
    NOMINATIM_URL,
    SFGeocoder,
    format_parcel,
    in_sf,
    parse_address,
)
from precedent.sources import base

GEO = Path(__file__).parent / "fixtures" / "geocode"


def load(name: str) -> Any:
    return json.loads((GEO / name).read_text())


class FakeClock:
    """Stands in for time.monotonic / asyncio.sleep inside precedent.sources.base (the RateLimiter)."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(base, "time", types.SimpleNamespace(monotonic=fake.monotonic))
    monkeypatch.setattr(base, "asyncio", types.SimpleNamespace(sleep=fake.sleep, Lock=asyncio.Lock))
    return fake


def eas_router(by_where: Callable[[str], Any]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=by_where(request.url.params.get("$where", "")))

    return handler


def default_eas(where: str) -> Any:
    if "address like '995%'" in where and "VALEN" in where:
        return load("eas_suggest_995_valen.json")
    if "address like '99%'" in where and "VALENCIA" in where:
        return load("eas_suggest_99_valencia.json")
    if where == "address = '995 VALENCIA ST'":
        return load("eas_exact_995_valencia_st.json")
    if where == "address = '3200 16TH ST'":
        return load("eas_exact_3200_16th_st.json")
    return load("eas_empty.json")


# --- pure helpers ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "normalized", "zip_code"),
    [
        ("995 Valencia St", "995 VALENCIA ST", None),
        ("995 Valencia Street, San Francisco, CA 94110", "995 VALENCIA ST", "94110"),
        ("3200 16th St.", "3200 16TH ST", None),
        ("4004 3rd Street", "4004 03RD ST", None),
        ("123 St. Francis Blvd", "123 SAINT FRANCIS BLVD", None),
        ("1117-1125 OCEAN AVENUE", "1117 OCEAN AVE", None),
        ("716 Kearny St Ste 200", "716 KEARNY ST", None),
        ("990 A Valencia St", "990 A VALENCIA ST", None),
        ("1 Embarcadero", "1 THE EMBARCADERO", None),
    ],
)
def test_parse_address_normalises_to_eas_form(text: str, normalized: str, zip_code: str | None) -> None:
    parsed = parse_address(text)
    assert parsed.normalized == normalized
    assert parsed.zip_code == zip_code


def test_format_parcel_and_bounds() -> None:
    assert format_parcel("3609026") == "3609/026"
    assert format_parcel("2051A010") == "2051A/010"
    assert format_parcel("6250007B") == "6250/007B"
    assert format_parcel(None) is None
    assert in_sf(37.757, -122.4208)
    assert not in_sf(37.8053, -122.2726)  # Oakland City Hall


def test_implements_protocol() -> None:
    geocoder: Geocoder = SFGeocoder()  # structural check (mypy) + runtime attrs
    assert callable(geocoder.suggest) and callable(geocoder.geocode) and callable(geocoder.close)


# --- EAS ------------------------------------------------------------------------------------------------------
@respx.mock
async def test_suggest_995_valen_returns_valencia_candidate() -> None:
    route = respx.get(EAS_RESOURCE).mock(side_effect=eas_router(default_eas))
    async with httpx.AsyncClient() as client:
        geo = SFGeocoder(client)
        results = await geo.suggest("995 Valen")
    assert route.called
    where = route.calls.last.request.url.params["$where"]
    assert "address like '995%'" in where and "street_full_street_name like 'VALEN%'" in where
    assert results, "expected a Valencia St candidate"
    top = results[0]
    assert top.normalized_address == "995 VALENCIA ST"
    assert top.lat == pytest.approx(37.7570827, abs=1e-6)
    assert top.lng == pytest.approx(-122.4208381, abs=1e-6)
    assert top.parcel == "3609/026"
    assert top.zip_code == "94110"
    assert top.source == "datasf_eas"
    assert top.source_url.endswith("eas_baseid=443862")
    assert 0 < top.confidence < 1.0  # prefix match, not exact


@respx.mock
async def test_suggest_ranks_exact_number_first_and_respects_limit() -> None:
    respx.get(EAS_RESOURCE).mock(side_effect=eas_router(default_eas))
    async with httpx.AsyncClient() as client:
        results = await SFGeocoder(client).suggest("99 Valencia", limit=5)
    assert len(results) == 5
    assert all("VALENCIA ST" in r.normalized_address for r in results)
    assert all(37.75 < r.lat < 37.76 for r in results)


@respx.mock
async def test_geocode_exact_995_valencia() -> None:
    respx.get(EAS_RESOURCE).mock(side_effect=eas_router(default_eas))
    async with httpx.AsyncClient() as client:
        res = await SFGeocoder(client).geocode("995 Valencia St")
    assert res is not None
    assert res.confidence == 1.0
    assert res.normalized_address == "995 VALENCIA ST"
    assert res.parcel == "3609/026"
    assert res.address == "995 Valencia St, San Francisco, CA 94110"


@respx.mock
async def test_geocode_without_parcel() -> None:
    respx.get(EAS_RESOURCE).mock(side_effect=eas_router(default_eas))
    async with httpx.AsyncClient() as client:
        res = await SFGeocoder(client).geocode("3200 16th Street")
    assert res is not None and res.confidence == 1.0
    assert res.normalized_address == "3200 16TH ST"
    assert res.parcel is None and res.zip_code == "94103"


@respx.mock
async def test_nonsense_query_returns_empty() -> None:
    eas = respx.get(EAS_RESOURCE).mock(side_effect=eas_router(default_eas))
    nom = respx.get(NOMINATIM_URL).mock(return_value=httpx.Response(200, json=load("nominatim_empty.json")))
    async with httpx.AsyncClient() as client:
        geo = SFGeocoder(client)
        assert await geo.suggest("zzqx florp") == []
        assert await geo.suggest("   ,,, ") == []
        assert await geo.geocode("zzqx florp") is None
    assert eas.call_count == 1  # the blank query never hits the network
    assert nom.call_count == 1


@respx.mock
async def test_cache_avoids_repeat_requests() -> None:
    route = respx.get(EAS_RESOURCE).mock(side_effect=eas_router(default_eas))
    async with httpx.AsyncClient() as client:
        geo = SFGeocoder(client)
        a = await geo.geocode("995 Valencia St")
        b = await geo.geocode("995 VALENCIA STREET")
    assert a == b
    assert route.call_count == 1
    assert geo.stats["cache_hits"] == 1


@respx.mock
async def test_cache_expires_after_24h() -> None:
    now = [0.0]
    route = respx.get(EAS_RESOURCE).mock(side_effect=eas_router(default_eas))
    async with httpx.AsyncClient() as client:
        geo = SFGeocoder(client, clock=lambda: now[0])
        await geo.geocode("995 Valencia St")
        now[0] += 24 * 3600 + 1
        await geo.geocode("995 Valencia St")
    assert route.call_count == 2


@respx.mock
async def test_geocode_many_batches_exact_lookups() -> None:
    def where(w: str) -> Any:
        if w.startswith("address in ("):
            return load("eas_exact_995_valencia_st.json") + load("eas_exact_3200_16th_st.json")
        return []

    route = respx.get(EAS_RESOURCE).mock(side_effect=eas_router(where))
    async with httpx.AsyncClient() as client:
        out = await SFGeocoder(client, use_nominatim=False).geocode_many(
            ["995 VALENCIA ST, SAN FRANCISCO, CA 94110", "3200 16TH ST"]
        )
    assert route.call_count == 1
    assert out["3200 16TH ST"] is not None and out["3200 16TH ST"].confidence == 1.0
    hit = out["995 VALENCIA ST, SAN FRANCISCO, CA 94110"]
    assert hit is not None and hit.parcel == "3609/026"


# --- Nominatim fallback -------------------------------------------------------------------------------------
@respx.mock
async def test_nominatim_fallback_when_eas_has_no_match(clock: FakeClock) -> None:
    eas = respx.get(EAS_RESOURCE).mock(return_value=httpx.Response(200, json=[]))
    nom = respx.get(NOMINATIM_URL).mock(
        return_value=httpx.Response(200, json=load("nominatim_2124_folsom_st.json"))
    )
    async with httpx.AsyncClient() as client:
        res = await SFGeocoder(client).geocode("2124 Folsom St")
    assert eas.called and nom.called
    params = nom.calls.last.request.url.params
    assert params["format"] == "jsonv2" and params["countrycodes"] == "us" and params["bounded"] == "1"
    assert params["viewbox"] == "-122.53,37.835,-122.35,37.7"
    assert "independent research" in nom.calls.last.request.headers["User-Agent"]
    assert res is not None
    assert res.source == "nominatim"
    assert res.confidence <= 0.6
    assert in_sf(res.lat, res.lng)
    assert res.source_url.startswith("https://www.openstreetmap.org/")
    assert res.normalized_address == "2124 FOLSOM ST"
    assert res.lat == pytest.approx(37.76323, abs=1e-4)


@respx.mock
async def test_nominatim_hit_on_another_street_is_rejected(clock: FakeClock) -> None:
    respx.get(EAS_RESOURCE).mock(return_value=httpx.Response(200, json=[]))
    respx.get(NOMINATIM_URL).mock(return_value=httpx.Response(200, json=load("nominatim_pier_39.json")))
    async with httpx.AsyncClient() as client:
        geo = SFGeocoder(client)
        assert await geo.geocode("39 Valencia St") is None  # Nominatim fuzzy-matched "Pier 39"
        hit = await geo.geocode("Pier 39")  # no street number: a named place is acceptable
    assert hit is not None and hit.source == "nominatim" and hit.confidence <= 0.6


@respx.mock
async def test_nominatim_rejects_results_outside_sf(clock: FakeClock) -> None:
    respx.get(EAS_RESOURCE).mock(return_value=httpx.Response(200, json=[]))
    respx.get(NOMINATIM_URL).mock(
        return_value=httpx.Response(200, json=load("nominatim_oakland_outside_sf.json"))
    )
    async with httpx.AsyncClient() as client:
        assert await SFGeocoder(client).geocode("1 Frank H Ogawa Plaza") is None


@respx.mock
async def test_nominatim_is_rate_limited_to_one_per_second(clock: FakeClock) -> None:
    times: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        times.append(clock.now)
        return httpx.Response(200, json=load("nominatim_pier_39.json"))

    respx.get(NOMINATIM_URL).mock(side_effect=handler)
    async with httpx.AsyncClient() as client:
        geo = SFGeocoder(client)
        for q in ("Pier 39", "Pier 41", "Pier 45", "Pier 33"):  # no street number → straight to Nominatim
            await geo.geocode(q)
    assert len(times) == 4
    gaps = [b - a for a, b in itertools.pairwise(times)]
    assert all(g >= 1.0 - 1e-9 for g in gaps), gaps
    assert len(clock.sleeps) == 3


async def test_close_only_closes_owned_client() -> None:
    shared = httpx.AsyncClient()
    geo = SFGeocoder(shared)
    await geo.close()
    assert not shared.is_closed
    await shared.aclose()

    own = SFGeocoder()
    client = own._http()
    await own.close()
    assert client.is_closed
