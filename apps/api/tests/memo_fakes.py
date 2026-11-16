"""Fixtures for the memo chain: a seeded LocalStore around 995 Valencia St, a fake geocoder, a scripted model."""

from __future__ import annotations

import asyncio
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from precedent.geocode import GeocodeResult
from precedent.models import Application, Business, Overlay
from precedent.store.local import LocalStore

from app.models.memo import Determinations
from tests.fakes import ScriptedModel

NOW = dt.datetime(2026, 10, 21, tzinfo=dt.UTC)
# The seeded address is in zoning district "NCT-2", a code the dated control data (rule table v2) does not
# carry. The rules then read the controls of the rows seeded here (a Bar is conditional by the district's rule
# row and prohibited by the alcohol district row), which is the made-up world these tests are written for. A
# code the dated data carries would be read from that data instead, whatever these rows say.
VALENCIA = GeocodeResult(
    address="995 Valencia St, San Francisco, CA 94110",
    normalized_address="995 VALENCIA ST",
    lat=37.7577,
    lng=-122.4213,
    parcel="3616/065",
    zip_code="94110",
    source="datasf_eas",
    source_url="https://data.sf.gov/d/eas",
    confidence=1.0,
)
# a square ~1.2 km around the point for the zoning polygon; a smaller one for the SUD
BIG = {
    "type": "Polygon",
    "coordinates": [
        [[-122.428, 37.752], [-122.414, 37.752], [-122.414, 37.763], [-122.428, 37.763], [-122.428, 37.752]]
    ],
}
SMALL = {
    "type": "Polygon",
    "coordinates": [
        [[-122.425, 37.754], [-122.417, 37.754], [-122.417, 37.761], [-122.425, 37.761], [-122.425, 37.754]]
    ],
}


def _app(
    i: int,
    *,
    kind: str = "cua",
    use: list[str],
    outcome: str,
    dlat: float,
    dlng: float,
    years_ago: float = 1.0,
    hours: str | None = "02:00",
    conditions: list[str] | None = None,
    opposition: bool | None = None,
    license_type: str | None = None,
    status: str = "Active",
    extra: dict[str, Any] | None = None,
) -> Application:
    decided = NOW.date() - dt.timedelta(days=int(365 * years_ago))
    source = (
        "abc"
        if kind == "abc_license"
        else ("datasf_entertainment" if kind.startswith("entertainment") else "datasf_planning")
    )
    return Application(
        id=f"{source}:{i}",
        source=source,  # type: ignore[arg-type]
        source_id=str(i),
        source_url=f"https://example.org/record/{i}",
        fetched_at=NOW,
        kind=kind,  # type: ignore[arg-type]
        permit_type="Conditional Use Authorization"
        if kind == "cua"
        else ("Place of Entertainment" if kind == "entertainment_poe" else f"Type {license_type}"),
        use_types=use,
        description=f"Record {i}: {' '.join(use)} with hours until {hours}",
        address=f"{900 + i} Valencia St",  # type: ignore[arg-type]
        lat=VALENCIA.lat + dlat,
        lng=VALENCIA.lng + dlng,
        zoning_district="NCT-2",
        status=status,
        outcome=outcome,  # type: ignore[arg-type]
        filed_at=decided - dt.timedelta(days=120),
        decided_at=decided,
        hours_close=hours,
        late_night=hours is not None and hours < "06:00",
        conditions=conditions or [],
        opposition_noted=opposition,
        decision_summary=f"Motion {20000 + i}: {outcome}",
        extraction_confidence="high",
        license_type=license_type,
        extra=extra or {},
    )


def seed_store(data_dir: Path) -> LocalStore:
    store = LocalStore(data_dir)
    apps = [
        _app(
            1,
            use=["bar", "live_entertainment"],
            outcome="approved_with_conditions",
            dlat=0.0008,
            dlng=0.0003,
            conditions=[
                "Hours of operation shall end at 2:00 a.m.",
                "A security plan shall be submitted",
                "No dancing",
            ],
            opposition=True,
            # enriched from the adopted Commission motion: the report's source for this case is the motion
            extra={"motion_url": "https://example.org/motions/M-20001.pdf"},
        ),
        _app(
            2,
            use=["bar"],
            outcome="approved_with_conditions",
            dlat=-0.0012,
            dlng=0.0004,
            conditions=["Close by 1:00 a.m."],
            hours="01:00",
            years_ago=2,
        ),
        _app(3, use=["bar"], outcome="denied", dlat=0.0015, dlng=-0.0009, opposition=True, years_ago=3),
        _app(
            4, use=["restaurant"], outcome="approved", dlat=0.0004, dlng=-0.0002, hours="23:00", years_ago=0.5
        ),
        _app(
            5,
            use=["restaurant", "outdoor_seating"],
            outcome="approved",
            dlat=-0.0005,
            dlng=0.001,
            hours="22:00",
            years_ago=4,
        ),
        _app(6, use=["nightclub", "bar"], outcome="withdrawn", dlat=0.002, dlng=0.001, years_ago=1.5),
        _app(
            7,
            kind="entertainment_poe",
            use=["live_entertainment", "bar"],
            outcome="approved",
            dlat=0.0009,
            dlng=0.0004,
            conditions=["Sound limiter installed"],
            years_ago=1,
        ),
        _app(
            8, use=["bar"], outcome="approved_with_conditions", dlat=0.02, dlng=0.02, years_ago=1
        ),  # ~2.8 km away: outside 1,000 ft
        _app(
            9, use=["restaurant"], outcome="approved", dlat=0.0003, dlng=0.0003, years_ago=8
        ),  # outside the 5-year window
        _app(
            21,
            kind="abc_license",
            use=["bar"],
            outcome="approved",
            dlat=0.0006,
            dlng=0.0002,
            license_type="42",
            hours=None,
        ),
        _app(
            22,
            kind="abc_license",
            use=["bar"],
            outcome="approved",
            dlat=-0.0007,
            dlng=0.0003,
            license_type="48",
            hours=None,
        ),
        _app(
            23,
            kind="abc_license",
            use=["restaurant"],
            outcome="approved",
            dlat=0.0004,
            dlng=-0.0006,
            license_type="47",
            hours=None,
        ),
        _app(
            24,
            kind="abc_license",
            use=["restaurant"],
            outcome="approved",
            dlat=0.0002,
            dlng=0.0004,
            license_type="41",
            hours=None,
        ),
        _app(
            25,
            kind="abc_license",
            use=["bar"],
            outcome="approved",
            dlat=0.0025,
            dlng=0.0003,
            license_type="42",
            hours=None,
            status="Surrendered",
        ),
    ]
    overlays = [
        Overlay(
            id="datasf_zoning:NCT-2",
            kind="zoning_district",
            name="NCT-2",
            rules="Moderate-Scale Neighborhood Commercial Transit District",
            code_section="Planning Code § 752",
            geom=BIG,
            source="datasf_zoning",
            source_url="https://data.sf.gov/d/zoning",
            fetched_at=NOW,
        ),
        Overlay(
            id="static:sf:nc_bar_rule_general",
            kind="nc_rule",
            name="Neighborhood Commercial districts: bar use",
            rules="Bars require Conditional Use Authorization; restaurants principally permitted.",
            code_section="Planning Code §§ 710–781, § 303",
            district_codes=["NCT-2"],
            bar_permission="conditional",
            restaurant_permission="principal",
            late_night_rule="2 a.m.–6 a.m. requires CUA",
            source="static",
            source_url="https://codelibrary.amlegal.com/x",
            fetched_at=NOW,
        ),
        Overlay(
            id="static:sf:mission_alcoholic_beverage_sud",
            kind="alcohol_sud",
            name="Mission Alcoholic Beverage Special Use District",
            rules="New bar uses prohibited; restaurants with incidental alcohol allowed.",
            code_section="Planning Code § 249.60",
            geom=SMALL,
            bar_permission="prohibited",
            restaurant_permission="conditional",
            source="static",
            source_url="https://codelibrary.amlegal.com/y",
            fetched_at=NOW,
        ),
    ]
    businesses = [
        Business(
            id=f"datasf_business:{i}",
            dba_name=f"Biz {i}",
            naics_code="722410" if i % 2 else "722511",
            naics_description="Drinking Places" if i % 2 else "Full-Service Restaurants",
            address=f"{950 + i} Valencia St",
            lat=VALENCIA.lat + 0.0003 * i,
            lng=VALENCIA.lng + 0.0002,
            start_date=dt.date(2015, 1, 1),
            end_date=None,
            is_food_or_drink=True,
            is_bar=bool(i % 2),
            source_url="https://data.sf.gov/d/g8m3-pdis",
            fetched_at=NOW,
        )
        for i in range(1, 7)
    ]
    # synchronous seeding (tests run inside an event loop): populate dicts and flush snapshots directly
    for a in apps:
        store.applications[a.id] = a
    for o in overlays:
        store.overlays[o.id] = o
    for b in businesses:
        store.businesses[b.id] = b
    for table in ("applications", "overlays", "businesses"):
        store._flush(table)
    return store


class FakeGeocoder:
    def __init__(self, hit: GeocodeResult | None = VALENCIA) -> None:
        self.hit = hit
        self.calls: list[str] = []

    async def suggest(self, query: str, limit: int = 8) -> list[GeocodeResult]:
        self.calls.append(query)
        return [self.hit] if self.hit and "valen" in query.lower() else []

    async def geocode(self, address: str) -> GeocodeResult | None:
        self.calls.append(address)
        return self.hit if self.hit and "valencia" in address.lower() else None

    async def close(self) -> None:
        return None


def case_determinations(
    case_id: str,
    data_dir: Path,
    *,
    in_full: bool = False,
    rules_date: dt.date | None = None,
    today: dt.date | None = None,
) -> Determinations:
    """What rule table v2 decides for one case of tests/fixtures/pathway_cases.json: real districts read from
    the dated control data, not the made-up district of the seeded store. `in_full` supplies the inputs the
    concept text leaves out (see `tests.test_pathway_cases.stated_in_full`). The dates default to that
    module's RULES_DATE. For tests of how the report carries a status note, referral steps, missing inputs,
    triggers and a past rules date."""
    from tests.test_pathway_cases import CASES, RULES_DATE, run_case

    case = next(c for c in CASES if c["id"] == case_id)

    def run() -> Determinations:
        return run_case(
            case, data_dir, in_full=in_full, rules_date=rules_date or RULES_DATE, today=today or RULES_DATE
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return run()
    # called from an async test: the case's store lookup starts an event loop of its own, so it runs in a thread
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(run).result()


def sent_temperature(call: dict[str, Any]) -> float | None:
    """The temperature a scripted call was sent with, however the installed SDK takes it: as an argument
    (anthropic 0.x) or in the request body (anthropic 1.x and 2.x). None when the call sets none."""
    if "temperature" in call:
        value: float = call["temperature"]
        return value
    body: dict[str, Any] = call.get("extra_body") or {}
    return body.get("temperature")


@dataclass
class MemoScript(ScriptedModel):
    """The memo's scripted model. The memo makes one model call, the intake, which the plan script answers
    (`tests.fakes.ScriptedModel`); every other stage of the report is code."""
