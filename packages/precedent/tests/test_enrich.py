"""Post-ingest bar enrichment against real DataSF business rows and real ABC records (tests/fixtures/enrich)."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from precedent import enrich, ingest
from precedent.sources import abc, datasf_business
from precedent.store.local import LocalStore

FIX = Path(__file__).parent / "fixtures" / "enrich"
BUSINESSES = FIX / "business-bars-p0000.json"
LICENSES = FIX / "abc-sf-licenses-bars.json"


def seeded(tmp: Path) -> LocalStore:
    store = LocalStore(tmp)
    asyncio.run(store.upsert_businesses(datasf_business.parse(BUSINESSES).businesses))
    asyncio.run(store.upsert_applications(abc.parse(LICENSES).applications))
    return store


def by_name(store: LocalStore) -> dict[str, bool]:
    return {b.dba_name: b.is_bar for b in store.businesses.values()}


@pytest.mark.parametrize(
    ("address", "keys"),
    [
        ("527-29 VALENCIA ST, SAN FRANCISCO, CA 94110", {("527", "VALENCIA"), ("529", "VALENCIA")}),
        ("527 Valencia St, San Francisco, CA 94110", {("527", "VALENCIA")}),
        ("298 Pacific", {("298", "PACIFIC")}),
        ("298 PACIFIC AVE, SAN FRANCISCO, CA 94111", {("298", "PACIFIC")}),
        ("1007 1/2 VALENCIA ST", {("1007", "VALENCIA")}),
        ("3158 MISSION ST A", {("3158", "MISSION")}),
        ("2519 & 2521 MISSION ST", {("2519", "MISSION"), ("2521", "MISSION")}),
        ("2341C FOLSOM ST", {("2341", "FOLSOM")}),
        ("995 Valencia St., Ste 2, San Francisco", {("995", "VALENCIA")}),
        ("3251 20th Ave #Op183, San Francisco", {("3251", "20TH")}),
        ("1398 SOUTH VAN NESS AVENUE", {("1398", "S VAN NESS")}),
        ("600 THIRD ST", {("600", "3RD")}),
        ("Pier 39 P214a2.3.4", set()),
        (None, set()),
    ],
)
def test_premises_keys(address: str | None, keys: set[tuple[str, str]]) -> None:
    assert enrich.premises_keys(address) == keys


def test_name_tokens_fold_apostrophes_and_drop_generic_words() -> None:
    assert enrich.name_tokens("Durty Nelly's LLC") == {"DURTY", "NELLYS"}
    assert enrich.name_tokens("DURTY NELLYS IRISH PUB") == {"DURTY", "NELLYS", "IRISH"}
    assert enrich.name_tokens("The Bar & Grill Restaurant Inc") == set()


def test_enrich_flags_bars_from_licenses_and_names(tmp_path: Path) -> None:
    store = seeded(tmp_path)
    before = by_name(store)
    assert before["Casanova Lounge"] and before["Vesuvio Cafe"]  # parse-time: NAICS 722410 / BARS/TAVERNS
    assert before["Southern Pacific Brewing"]  # parse-time name keyword ("brewing")
    assert not any(before[n] for n in ("Vesuvio Inc", "Durty Nelly's LLC", "Old Ship", "Chieftain The"))

    stats = asyncio.run(enrich.enrich_businesses(store))
    after = by_name(store)
    # Type 48 at the same premises, names share a word (255 Columbus has two tenants; apostrophe folded)
    assert after["Vesuvio Inc"] and after["Durty Nelly's LLC"]
    # on-sale (Type 47) license whose DBA reads as a bar: OLD SHIP SALOON, THE CHIEFTAIN IRISH PUB ...
    assert after["Old Ship"] and after["Chieftain The"]
    # not bars: a Type 47 restaurant license with no bar name, Taco Bell Cantina, mall tenants next to
    # "KURA REVOLVING SUSHI BAR", Palace Hotel restaurants next to a Type 42 wine shop, hotel kitchens and
    # coffee bar under the hotel's Type 48, a sushi counter inside a market with a Type 42
    for name in (
        "The Napper Tandy",
        "Taco Bell Cantina #31685",
        "Panda Express",
        "Boudin Sourdough Bakery/Cafe",
        "Peet's Coffee Inc",
        "Wise Sons",
        "Garden Court Restaurant",
        "Maxfield's",
        "Ghiradelli Chocolate Co",
        "Grand Hyatt - Main Kitchen",
        "Grand Hyatt - Coffee Bar",
        "Hissho Sushi",
    ):
        assert after[name] is False, name
    assert stats.as_dict() == {
        "businesses": 22,
        "already_bar": 3,
        "by_abc_license": 2,
        "by_abc_dba": 2,
        "by_name": 0,
        "updated": 4,
        "bar_premises": 9,
    }
    # persisted, and a second run changes nothing
    assert by_name(LocalStore(tmp_path)) == after
    again = asyncio.run(enrich.enrich_businesses(LocalStore(tmp_path)))
    assert again.updated == 0 and again.already_bar == 7


def test_name_signal_upgrades_rows_parsed_before_the_keyword_list_grew(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    rows = datasf_business.parse(BUSINESSES).businesses
    brewery = next(b for b in rows if b.dba_name == "Southern Pacific Brewing")
    stale = brewery.model_copy(update={"is_bar": False})
    juice = brewery.model_copy(
        update={"id": "datasf_business:x", "dba_name": "Sidewalk Juice Bar", "is_bar": False}
    )
    asyncio.run(store.upsert_businesses([stale, juice]))
    stats = asyncio.run(enrich.enrich_businesses(store))
    assert (
        stats.by_name == 1
        and store.businesses[brewery.id].is_bar
        and not store.businesses["datasf_business:x"].is_bar
    )


def test_inactive_licenses_are_ignored() -> None:
    lic = next(a for a in abc.parse(LICENSES).applications if a.id == "abc:525090")  # DURTY NELLYS, Type 48
    assert enrich.active_license_types(lic) == {"48"}
    gone = lic.model_copy(
        update={
            "status": "CANCELED",
            "extra": {
                **lic.extra,
                "license_types": [{**t, "status": "CANCELED"} for t in lic.extra["license_types"]],
            },
        }
    )
    assert enrich.active_license_types(gone) == set()
    assert enrich.index_licenses([gone]) == {}
    assert enrich.index_licenses([lic])[("2328", "IRVING")][0].bar_type


def test_cli_prints_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.delenv("PRECEDENT_DATABASE_URL", raising=False)
    seeded(tmp_path)
    assert enrich.main(["businesses", "--data-dir", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["businesses"]["updated"] == 4


@pytest.mark.parametrize(
    ("argv", "expect"),
    [(["--all"], True), (["--source", "abc"], True), (["--source", "datasf_zoning"], False)],
)
def test_ingest_runs_enrichment_after_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str], expect: bool
) -> None:
    monkeypatch.delenv("PRECEDENT_DATABASE_URL", raising=False)
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    calls: list[str] = []

    async def fake_run_all(sources: list[str], store: Any, raw_dir: Path, since: dt.date | None) -> list[Any]:
        calls.append("sources")
        return []

    async def fake_enrich(store: Any) -> enrich.BarEnrichment:
        calls.append("enrich")
        return enrich.BarEnrichment()

    monkeypatch.setattr(ingest, "run_all", fake_run_all)
    monkeypatch.setattr(ingest, "enrich_businesses", fake_enrich)
    assert ingest.main([*argv, "--data-dir", str(tmp_path), "--raw-dir", str(tmp_path / "raw")]) == 0
    assert calls == (["sources", "enrich"] if expect else ["sources"])


def test_ingest_enrichment_failure_is_logged_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRECEDENT_DATABASE_URL", raising=False)
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)

    async def fake_run_all(sources: list[str], store: Any, raw_dir: Path, since: dt.date | None) -> list[Any]:
        return []

    async def boom(store: Any) -> enrich.BarEnrichment:
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(ingest, "run_all", fake_run_all)
    monkeypatch.setattr(ingest, "enrich_businesses", boom)
    assert ingest.main(["--all", "--data-dir", str(tmp_path), "--raw-dir", str(tmp_path / "raw")]) == 1
