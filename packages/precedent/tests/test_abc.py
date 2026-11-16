"""ABC source: parsers against real abc.ca.gov pages, parse() against a real raw page, fetch() fully mocked."""

from __future__ import annotations

import asyncio
import datetime as dt
import itertools
import json
import re
import types
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from precedent.geocode_sf import EAS_RESOURCE, in_sf
from precedent.sources import abc, base
from precedent.sources.base import read_raw

FIX = Path(__file__).parent / "fixtures" / "abc"
GEO = Path(__file__).parent / "fixtures" / "geocode"
RAW_SAMPLE = FIX / "raw-sf-licenses-94110-sample.json"
LOOKUP_RE = re.compile(
    r"^https://www\.abc\.ca\.gov/licensing/license-lookup/single-license/\?RPTTYPE=12&LICENSE=\d+$"
)


def html(name: str) -> str:
    return (FIX / name).read_text()


class FakeClock:
    def __init__(self) -> None:
        self.now = 5000.0
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


# --- small pure pieces --------------------------------------------------------------------------------------
def test_type_labels_and_lookup_url() -> None:
    assert abc.type_label("42") == "Type 42 – On-Sale Beer & Wine - Public Premises"
    assert abc.type_label("48") == "Type 48 – On-Sale General - Public Premises"
    assert abc.type_label("41") == "Type 41 – On-Sale Beer & Wine - Eating Place"
    assert abc.type_label("2") == "Type 02 – Winegrower"
    assert LOOKUP_RE.match(abc.lookup_url("34420"))


@pytest.mark.parametrize(
    ("status", "lic_or_app", "outcome"),
    [
        ("ACTIVE", "LIC", "approved"),
        ("ISSUED", "LIC", "approved"),
        ("PEND", "APP", "pending"),
        ("PENDING", "APP", "pending"),
        ("SUREND", "LIC", "approved"),  # it was granted; the status string says what happened since
        ("REVPEN", "LIC", "approved"),
        ("DEPARTMENT REVOKED", "LIC", "approved"),
        ("CANCELED", "LIC", "approved"),
        ("DENY", "APP", "denied"),
        ("WDRL", "APP", "withdrawn"),
        ("VOID", "APP", "unknown"),
    ],
)
def test_status_to_outcome(status: str, lic_or_app: str, outcome: str) -> None:
    assert abc.outcome_for(status, lic_or_app) == outcome


def test_type_use_type_mapping() -> None:
    m = abc.TYPE_USE_TYPES
    assert m["41"] == m["47"] == m["57"] == ["restaurant"]
    assert m["42"] == m["48"] == m["61"] == ["bar"]
    assert m["20"] == m["21"] == ["retail_alcohol"]
    assert "hotel" in m["70"] and "restaurant" in m["75"] and "bar" in m["75"]


# --- LQS detail + daily report parsers (real pages) ---------------------------------------------------------
def test_detail_revoked_bar_with_history_and_holds() -> None:
    d = abc.parse_detail_html(html("lqs-1352-sam-jordans.html"))
    assert d["found"] and d["license_number"] == "1352"
    assert d["business_name"] == "SAM JORDANS BAR"
    t48 = d["license_types"][0]
    assert (t48["code"], t48["status"], t48["orig_issue_date"]) == ("48", "DEPARTMENT REVOKED", "22-MAR-1978")
    assert t48["conditions"] == ["CODE 8 - SELF-INCORPORATION - HISTORICAL VALUE"]
    assert d["operating_restrictions"] is True
    assert d["disciplinary_history"][0]["decision"] == "REVOKED"
    assert next(h["hold_type"] for h in d["holds"]) == "BOARD OF EQUALIZATION HOLD"
    assert "officers" not in json.dumps(d).lower()


def test_detail_pending_transferred_and_missing() -> None:
    pend = abc.parse_detail_html(html("lqs-683645-pending.html"))
    assert pend["license_types"][0]["status"] == "PENDING"
    assert pend["license_types"][0]["orig_issue_date"] == ""
    assert pend["holds"] == [{"hold_type": "FORM 220", "hold_date": "15-OCT-2026"}]
    moved = abc.parse_detail_html(html("lqs-503827-transferred.html"))
    assert moved["license_types"][0]["status"] == "CANCELED"
    assert "41-528874" in moved["license_types"][0]["transfers"]
    scomas = abc.parse_detail_html(html("lqs-34420-scomas.html"))
    assert len(scomas["license_types"]) == 2 and scomas["operating_restrictions"] is False
    assert abc.parse_detail_html(html("lqs-530979-not-found.html")) == {"found": False}


def test_daily_reports_parse() -> None:
    day, rows = abc.parse_report_html(html("report-new-applications-2026-10-15.html"))
    assert day == dt.date(2026, 10, 15)
    ev = abc.report_event("new_application", day, rows[0])
    assert ev["license_number"] == "683645" and ev["type"] == "41" and ev["action"] == "ORI"
    assert ev["dba"] == "SUSHI TOKKI" and ev["owner"] == "TOKKI SUSHI LLC" and ev["county"] == "38"
    day, rows = abc.parse_report_html(html("report-status-changes-2026-10-20.html"))
    ev = abc.report_event("status_change", day, rows[0])
    assert (ev["status_from"], ev["status_to"], ev["conditions"]) == ("PEND", "ACTIVE", "7")


# --- parse() on a real raw page -----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def batch() -> Any:
    return abc.parse(RAW_SAMPLE)


def test_raw_sample_envelope_and_counts(batch: Any) -> None:
    meta, data = read_raw(RAW_SAMPLE)
    assert meta["url"] == abc.EXPORT_URL and "fetched_at" in meta
    assert 0 < len(data["licenses"]) <= 100
    assert len(batch.applications) == len(data["licenses"])
    assert len(batch) == len(batch.applications)


def test_ids_kinds_and_urls(batch: Any) -> None:
    ids = [a.id for a in batch.applications]
    assert len(ids) == len(set(ids))
    for a in batch.applications:
        assert re.fullmatch(r"abc:\d+", a.id)
        assert a.id == f"abc:{a.source_id}"
        assert a.kind == "abc_license" and a.source == "abc"
        assert LOOKUP_RE.match(a.source_url) and a.source_url.endswith(f"LICENSE={a.source_id}")
        assert a.permit_type.startswith(f"Type {a.license_type} – ")


def test_type_48_and_type_41_rows(batch: Any) -> None:
    t48 = [a for a in batch.applications if a.license_type == "48"]
    t41 = [a for a in batch.applications if a.license_type == "41"]
    assert t48 and t41
    for a in t48:
        assert a.permit_type == "Type 48 – On-Sale General - Public Premises"
        assert "bar" in a.use_types
    for a in t41:
        assert a.permit_type == "Type 41 – On-Sale Beer & Wine - Eating Place"
        assert "restaurant" in a.use_types
    active48 = next(a for a in t48 if a.outcome == "approved")
    assert active48.decided_at is not None and active48.extra["owner"]


def test_status_outcome_consistency(batch: Any) -> None:
    for a in batch.applications:
        assert a.outcome == abc.outcome_for(a.status, a.extra.get("record_kind", ""))
        if a.outcome == "pending":
            assert a.decided_at is None
        if a.status.upper() in ("ACTIVE", "SUREND", "REVPEN", "SUSPEN"):
            assert a.outcome == "approved"
    assert {"approved", "pending"} <= {a.outcome for a in batch.applications}


def test_geocoded_rows_are_in_sf(batch: Any) -> None:
    geocoded = [a for a in batch.applications if a.has_geom]
    assert len(geocoded) >= 0.8 * len(batch.applications)
    for a in geocoded:
        assert a.lat is not None and a.lng is not None and in_sf(a.lat, a.lng)
        assert a.extra["geocode_source"] in ("datasf_eas", "nominatim")
    assert any(a.parcel and re.fullmatch(r"\d{4}[A-Z]?/\d{3}[A-Z]?", a.parcel) for a in geocoded)


def test_parse_is_pure(batch: Any) -> None:
    again = abc.parse(RAW_SAMPLE)
    assert [a.model_dump() for a in again.applications] == [a.model_dump() for a in batch.applications]


# --- fetch() end to end, mocked, with the rate limiter observed -------------------------------------------
def _abc_handler(clock: FakeClock, seen: list[tuple[float, str]]) -> Any:
    export = (FIX / "DailyExport-CSV-sample.zip").read_bytes()
    detail = {
        "1352": "lqs-1352-sam-jordans.html",
        "34420": "lqs-34420-scomas.html",
        "503827": "lqs-503827-transferred.html",
        "683645": "lqs-683645-pending.html",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((clock.now, str(request.url)))
        assert request.headers["User-Agent"].startswith("CA ABC public-report archiver/1.0")
        path, params = request.url.path, request.url.params
        if path.endswith("DailyExport-CSV.zip"):
            return httpx.Response(
                200, content=export, headers={"last-modified": "Wed, 21 Oct 2026 10:50:29 GMT"}
            )
        if "new-applications" in path:
            return httpx.Response(200, text=html("report-new-applications-2026-10-15.html"))
        if "status-changes" in path:
            return httpx.Response(200, text=html("report-status-changes-2026-10-20.html"))
        if "issued-licenses" in path:
            return httpx.Response(
                200, text='<html><table id="license_report"><thead></thead><tbody></tbody></table></html>'
            )
        if "single-license" in path:
            return httpx.Response(200, text=html(detail.get(params["LICENSE"], "lqs-530979-not-found.html")))
        return httpx.Response(404)

    return handler


@respx.mock
async def test_fetch_end_to_end_respects_rate_limit_and_caches(
    tmp_path: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ABC_REPORT_DAYS", "1")
    monkeypatch.delenv("ABC_ZIP_CODES", raising=False)
    monkeypatch.delenv("ABC_DETAILS", raising=False)
    seen: list[tuple[float, str]] = []
    respx.route(host="www.abc.ca.gov").mock(side_effect=_abc_handler(clock, seen))
    eas_rows = json.loads((GEO / "eas_in_abc_sample.json").read_text())
    respx.get(EAS_RESOURCE).mock(
        side_effect=lambda req: httpx.Response(
            200, json=eas_rows if req.url.params["$where"].startswith("address in (") else []
        )
    )
    respx.get("https://nominatim.openstreetmap.org/search").mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient() as client:
        paths = await abc.fetch(client, tmp_path, None)

    # rate limit: every abc.ca.gov request ≥ 2 s after the previous one (fake clock; sleeps recorded)
    times = [t for t, _ in seen]
    assert len(times) >= 1 + 3 + 6  # export + ≥1 day of 3 reports + 6 SF license detail pages
    gaps = [b - a for a, b in itertools.pairwise(times)]
    assert min(gaps) >= 2.0 - 1e-9, gaps
    assert sum(1 for s in clock.sleeps if s == pytest.approx(2.0)) >= len(times) - 1  # (geocoder sleeps too)

    assert len(paths) == 1 and paths[0].parent == tmp_path / "abc"
    meta, data = read_raw(paths[0])
    assert meta["rate_limit_per_second"] == 0.5
    nums = {r["license_number"] for r in data["licenses"]}
    assert nums == {"1352", "34420", "503827", "530979", "683645", "683652", "683663", "680418"}  # SF only

    apps = {a.source_id: a for a in abc.parse(paths[0]).applications}
    sam = apps["1352"]
    assert sam.license_type == "48" and sam.status == "DEPARTMENT REVOKED" and sam.outcome == "approved"
    assert sam.decided_at == dt.date(1978, 3, 22)
    assert "CODE 8 - SELF-INCORPORATION - HISTORICAL VALUE" in sam.conditions
    assert sam.opposition_noted is False and sam.extra["disciplinary_history"]
    assert sam.parcel == "5253/030" and sam.lat is not None and in_sf(sam.lat, sam.lng or 0)
    tokki = apps["683645"]  # known only from the new-applications report + its LQS page
    assert tokki.outcome == "pending" and tokki.filed_at == dt.date(2026, 10, 15) and tokki.decided_at is None
    assert tokki.extra["application_actions"] == ["ORI"] and "restaurant" in tokki.use_types
    meat = apps["680418"]  # status change PEND → ACTIVE
    assert meat.outcome == "approved" and meat.decided_at == dt.date(2026, 10, 19)
    assert meat.extra["condition_codes"] == ["7"]
    assert apps["530979"].outcome == "pending" and apps["530979"].license_type == "21"
    assert "retail_alcohol" in apps["530979"].use_types
    assert apps["503827"].status == "CANCELED" and apps["503827"].outcome == "approved"

    # second run: detail pages and past report days come from the cache
    seen.clear()
    async with httpx.AsyncClient() as client:
        await abc.fetch(client, tmp_path, None)
    assert not [u for _, u in seen if "single-license" in u]


@respx.mock
async def test_fetch_zip_filter_and_detail_limit(
    tmp_path: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ABC_REPORT_DAYS", "1")
    monkeypatch.setenv("ABC_ZIP_CODES", "94124,94108")
    monkeypatch.setenv("ABC_DETAILS", "1")
    seen: list[tuple[float, str]] = []
    respx.route(host="www.abc.ca.gov").mock(side_effect=_abc_handler(clock, seen))
    respx.get(EAS_RESOURCE).mock(return_value=httpx.Response(200, json=[]))
    respx.get("https://nominatim.openstreetmap.org/search").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient() as client:
        paths = await abc.fetch(client, tmp_path, None)
    _, data = read_raw(paths[0])
    assert {r["license_number"] for r in data["licenses"]} == {"1352", "503827"}
    assert len([u for _, u in seen if "single-license" in u]) == 1


# --- offline build: files on disk only, no request to abc.ca.gov -------------------------------------------
def _sample_export_rows() -> tuple[str, list[dict[str, str]]]:
    return abc.read_export((FIX / "DailyExport-CSV-sample.zip").read_bytes())


def _write_csv(path: Path, rows: list[dict[str, str]], banner: str | None) -> None:
    import csv as csv_mod
    import gzip as gzip_mod
    import io as io_mod

    buf = io_mod.StringIO()
    if banner is not None:
        buf.write(f'"{banner}"\n')
    w = csv_mod.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    data = buf.getvalue().encode()
    path.write_bytes(gzip_mod.compress(data) if path.suffix == ".gz" else data)


def test_read_export_file_takes_abc_zip_and_the_archives_csv(tmp_path: Path) -> None:
    banner, rows = _sample_export_rows()
    z = tmp_path / "export.zip"
    z.write_bytes((FIX / "DailyExport-CSV-sample.zip").read_bytes())
    assert abc.read_export_file(z) == (banner, rows)
    gz = tmp_path / "latest.csv.gz"  # the ABC archive's copy: no title line
    _write_csv(gz, rows, banner=None)
    assert abc.read_export_file(gz) == ("", rows)
    plain = tmp_path / "export.csv"  # ABC's own CSV, unzipped: title line first
    _write_csv(plain, rows, banner=banner)
    assert abc.read_export_file(plain) == (banner, rows)


async def test_fetch_offline_builds_raw_pages_without_contacting_abc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, rows = _sample_export_rows()
    export = tmp_path / "latest.csv.gz"
    _write_csv(export, rows, banner=None)
    raw_dir = tmp_path / "raw"
    cache = raw_dir / "abc" / "_cache"
    # a cached detail page (any age) is attached, never refetched
    (cache / "detail").mkdir(parents=True)
    (cache / "detail" / "1352.json").write_text(
        json.dumps(
            {
                "fetched_at": "2025-01-01T00:00:00+00:00",
                "signature": "old",
                "detail": abc.parse_detail_html(html("lqs-1352-sam-jordans.html")),
            }
        )
    )
    # events of an earlier raw page carry over to a license still in the export (a status change of 34420)
    _, status_rows = abc.parse_report_html(html("report-status-changes-2026-10-20.html"))
    old_events = [
        {**abc.report_event("status_change", dt.date(2026, 10, 20), r), "license_number": "34420"}
        for r in status_rows[:1]
    ]
    assert old_events[0]["conditions"] == "7"
    base.write_raw(
        raw_dir / "abc" / "20261020T000000000000Z-sf-licenses-p000.json",
        {"licenses": [{"license_number": "34420", "events": old_events}]},
        {"url": "x"},
    )
    # an archived daily report (the ABC archive's daily/<date>/<slug>.html.gz) adds a license only it knows
    import gzip as gzip_mod

    today = dt.datetime.now(dt.UTC).date()
    day = next(d for d in (today - dt.timedelta(days=k) for k in range(1, 8)) if d.weekday() < 5)
    reports = tmp_path / "daily"
    (reports / day.isoformat()).mkdir(parents=True)
    (reports / day.isoformat() / "new-applications.html.gz").write_bytes(
        gzip_mod.compress(html("report-new-applications-2026-10-15.html").encode())
    )

    monkeypatch.setenv("ABC_OFFLINE_EXPORT", str(export))
    monkeypatch.setenv("ABC_OFFLINE_REPORTS_DIR", str(reports))
    monkeypatch.delenv("ABC_ZIP_CODES", raising=False)
    monkeypatch.delenv("ABC_DETAILS", raising=False)
    with respx.mock(assert_all_called=False) as router:
        abc_route = router.route(host="www.abc.ca.gov").mock(
            side_effect=AssertionError("the offline build must not contact abc.ca.gov")
        )
        eas_rows = json.loads((GEO / "eas_in_abc_sample.json").read_text())
        router.get(EAS_RESOURCE).mock(
            side_effect=lambda req: httpx.Response(
                200, json=eas_rows if req.url.params["$where"].startswith("address in (") else []
            )
        )
        router.get("https://nominatim.openstreetmap.org/search").mock(
            return_value=httpx.Response(200, json=[])
        )
        async with httpx.AsyncClient() as client:
            paths = await abc.fetch(client, raw_dir, today - dt.timedelta(days=10))

    assert not abc_route.called
    meta, _ = read_raw(paths[0])
    assert meta["offline"] is True and meta["abc_requests"] == 0 and meta["url"] == "file:latest.csv.gz"
    apps = {a.source_id: a for a in abc.parse(paths[0]).applications}
    assert {"1352", "34420", "503827", "530979", "683645"} <= set(apps)
    sam = apps["1352"]  # cached detail page used
    assert sam.status == "DEPARTMENT REVOKED" and sam.extra["status_source"] == "lqs"
    assert apps["34420"].extra["condition_codes"] == ["7"]  # carried-over event
    tokki = apps["683645"]  # known only from the archived report
    assert tokki.outcome == "pending" and tokki.extra["application_actions"] == ["ORI"]
    assert all(a.lat is None or in_sf(a.lat, a.lng or 0) for a in apps.values())


# --- the data fix of 2026-11-15: every SF licence, not only ZIP 94110 ------------------------------------------------
# A tiny export in ABC's own columns: the ACTIVE Type 47 at 2301 Chestnut St (ZIP 94123, as the real export writes
# it: licence 636535, abc:636535 in the local store) and a licence outside San Francisco. Only the columns the loader
# reads carry values; the rest are blank as in the sample export.
CHESTNUT_ROW = {
    "License Type": "47",
    "File Number": "00636535",
    "Lic or App": "LIC",
    "Type Status": "ACTIVE",
    "Type Orig Iss Date": "",
    "Expir Date": "",
    "Fee Codes": "",
    "Dup Counts": "",
    "Master Ind": "Y",
    "Term in # of Months": "12",
    "Geo Code": "3800",
    "District": "24",
    "Primary Name": "LOJ TWO LP",
    "Prem Addr 1": "2301 CHESTNUT ST",
    "Prem Addr 2": "",
    "Prem City": "SAN FRANCISCO",
    "Prem State": "CA",
    "Prem Zip": "94123-2604",
    "DBA Name": "LITTLE ORIGINAL JOE'S",
    "Mail Addr 1": "",
    "Mail Addr 2": "",
    "Mail City": "",
    "Mail State": "",
    "Mail Zip": "",
    "Prem County": "SAN FRANCISCO",
    "Prem Census Tract #": "0128.01",
}
CHESTNUT_ADDRESS = "2301 CHESTNUT ST, SAN FRANCISCO, CA 94123"


def _chestnut_export(tmp_path: Path) -> Path:
    _, sample = _sample_export_rows()
    elsewhere = next(r for r in sample if r["Prem County"] != "SAN FRANCISCO")
    export = tmp_path / "latest.csv.gz"
    _write_csv(export, [elsewhere, CHESTNUT_ROW], banner=None)
    return export


def test_read_export_file_keeps_the_94123_row_and_filter_sf_keeps_it_with_no_zip_filter(
    tmp_path: Path,
) -> None:
    _, rows = abc.read_export_file(_chestnut_export(tmp_path))
    assert len(rows) == 2
    sf = abc.filter_sf(rows, None)
    assert [(r["File Number"], r["Prem Zip"], r["License Type"]) for r in sf] == [
        ("00636535", "94123-2604", "47")
    ]
    # a ZIP filter is read on the first five digits; 94110 alone would leave Chestnut out (the state before the fix)
    assert abc.filter_sf(rows, ["94123"]) == sf
    assert abc.filter_sf(rows, ["94110"]) == []


async def test_fetch_offline_loads_the_active_type_47_at_2301_chestnut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export = _chestnut_export(tmp_path)
    raw_dir = tmp_path / "raw"
    cache = raw_dir / "abc" / "_cache"
    cache.mkdir(parents=True)
    # the address geocoded already (as a run before this one cached it), so no geocoder is asked
    (cache / "geocode.json").write_text(
        json.dumps(
            {
                "_version": abc.GEOCODE_CACHE_VERSION,
                CHESTNUT_ADDRESS: {
                    "lat": 37.79992933659679,
                    "lng": -122.44148722440673,
                    "normalized_address": "2301 CHESTNUT ST",
                    "parcel": "0936/001",
                    "zip_code": "94123",
                    "source": "datasf_eas",
                    "source_url": "https://data.sf.gov/resource/3mea-di5p.json?eas_baseid=290806",
                    "confidence": 1.0,
                },
            }
        )
    )
    monkeypatch.setenv("ABC_OFFLINE_EXPORT", str(export))
    monkeypatch.delenv("ABC_OFFLINE_REPORTS_DIR", raising=False)
    monkeypatch.delenv("ABC_ZIP_CODES", raising=False)
    with respx.mock(assert_all_called=False) as router:
        abc_route = router.route(host="www.abc.ca.gov").mock(
            side_effect=AssertionError("the offline build must not contact abc.ca.gov")
        )
        other = router.route().mock(side_effect=AssertionError("no request is needed"))
        async with httpx.AsyncClient() as client:
            paths = await abc.fetch_offline(client, raw_dir, None)
    assert not abc_route.called and not other.called
    apps = [a for p in paths for a in abc.parse(p).applications]
    assert [a.id for a in apps] == ["abc:636535"]
    (joe,) = apps
    assert (joe.kind, joe.license_type, joe.status, joe.address) == (
        "abc_license",
        "47",
        "ACTIVE",
        CHESTNUT_ADDRESS,
    )
    assert joe.permit_type.startswith("Type 47") and "restaurant" in joe.use_types
    assert joe.parcel == "0936/001" and joe.lat is not None and in_sf(joe.lat, joe.lng or 0)
