"""The backtest's cut-off (docs/validation/backtest-plan.md §3, "The test that proves it").

1. For random cut-off dates, every record any read of AsOfStore returns was filed by the cut-off; every decision
   date, condition, outcome and description it carries belongs to a record decided by then; every licence was
   issued by then and not ended; every business had started and not ended.
2. Planted records: records carrying a marker in every answer-bearing field, filed after the cut-off or decided
   after it, licences issued after it or ended before it, a business started after it, an Entertainment
   Commission permit. A whole report is run through the store (scripted model): the marker appears nowhere in
   what any stage is sent, nor in the finished report.
3. The case's own record and project are never returned, and a request carrying the case's record number,
   project number or motion number is refused before it is sent.
"""

from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path
from typing import Any

import pytest
from precedent.models import Application, Business

from app.agents.memo_runner import MemoRunInput, MemoRunner
from app.backtest import asof
from app.backtest.asof import OPEN_STATUS, AsOfStore, LicenceFile, licence_set, status_on_cut_off
from app.core.config import settings
from app.deps import get_catalog
from tests.fakes import FakeAnthropic
from tests.memo_fakes import NOW, VALENCIA, FakeGeocoder, MemoScript, seed_store

MARK = "ZZLEAKZZ"
AS_OF = dt.date(2025, 6, 1)


def lic(num: str, *, issued: str, name: str = "OK", status_today: str = "ACTIVE", in_export: bool = True,
        dates: tuple[str, ...] = (), latest: tuple[str, str] | None = None, dlat: float = 0.0002) -> LicenceFile:  # fmt: skip
    ds = tuple(dt.date.fromisoformat(d) for d in dates)
    return LicenceFile(
        file_number=num, types=("41",), primary_type="41", name=name, address=f"{990 + int(num) % 9} VALENCIA ST",
        zip="94110", issued=dt.date.fromisoformat(issued), in_export_today=in_export, status_today=status_today,
        status_dates=ds, latest_from=latest[0] if latest else None, latest_to=latest[1] if latest else None,
        latest_date=ds[-1] if ds else None, lat=VALENCIA.lat + dlat, lng=VALENCIA.lng, parcel=None, tract="208.01",
    )  # fmt: skip


# ---- the status of a licence on a past day ---------------------------------------------------------------------


def test_status_on_the_cut_off_day() -> None:
    d = dt.date(2023, 1, 1)
    assert status_on_cut_off(lic("1", issued="2023-02-01"), d) is None  # issued later: not held
    assert status_on_cut_off(lic("2", issued="2020-01-01"), d) == "ACTIVE"  # nothing changed since
    ended_later = lic("3", issued="2020-01-01", status_today="", in_export=False, dates=("2024-05-01",),
                      latest=("ACTIVE", "CANCEL"))  # fmt: skip
    assert status_on_cut_off(ended_later, d) == "ACTIVE"  # held on the day, ended after it
    ended_before = lic(
        "4", issued="2020-01-01", in_export=False, dates=("2022-05-01",), latest=("ACTIVE", "CANCEL")
    )
    assert status_on_cut_off(ended_before, d) == "CANCEL"
    two_later = lic("5", issued="2020-01-01", dates=("2023-03-01", "2024-03-01"), latest=("REVPEN", "ACTIVE"))
    assert status_on_cut_off(two_later, d) == asof.UNKNOWN  # the status in between is not in the archive
    ls = licence_set(d, [ended_later, ended_before, two_later, lic("6", issued="2024-01-01")])
    assert [f.file_number for f, _ in ls.held] == ["3"] and [f.file_number for f in ls.unknown] == ["5"]


# ---- masking, field by field ------------------------------------------------------------------------------------


def app(i: int, *, filed: dt.date | None, decided: dt.date | None, kind: str = "cua", outcome: str = "approved",
        status: str = "Closed - Approved", text: str = "x") -> Application:  # fmt: skip
    return Application(
        id=f"datasf_planning:2020-{i:06d}CUA", source="datasf_planning", source_id=f"2020-{i:06d}CUA",
        source_url="https://example.org", fetched_at=NOW, kind=kind, permit_type="Conditional Use Authorization",
        use_types=["bar"], description=f"{text} description", address=f"{900 + i % 50} Valencia St",
        lat=VALENCIA.lat + (i % 7) * 0.0003, lng=VALENCIA.lng, status=status, outcome=outcome,
        filed_at=filed, decided_at=decided, hours_close="02:00", late_night=True, conditions=[f"{text} condition"],
        decision_summary=f"{text} summary", extraction_confidence="high", opposition_noted=True,
        extra={"motion_url": f"https://example.org/{text}", "record_kind": "use_decision", "premises": True,
               "record_type": "CUA", "building_permits": [text]},
    )  # fmt: skip


class ListStore:
    def __init__(self, apps: list[Application], businesses: list[Business]) -> None:
        self.apps, self.businesses = apps, businesses

    async def nearby_applications(self, lat, lng, radius_m, *, kinds=None, since=None, limit=500):  # type: ignore[no-untyped-def]
        from precedent.store.base import Nearby

        return [Nearby(a, 10.0) for a in self.apps if kinds is None or a.kind in kinds][:limit]

    async def nearby_businesses(self, lat, lng, radius_m, *, active_only=True, limit=1000):  # type: ignore[no-untyped-def]
        from precedent.store.base import Nearby

        return [Nearby(b, 10.0) for b in self.businesses if not active_only or b.end_date is None][:limit]

    async def application(self, app_id):  # type: ignore[no-untyped-def]
        return next((a for a in self.apps if a.id == app_id), None)

    async def applications_of_kind(self, kind):  # type: ignore[no-untyped-def]
        return [a for a in self.apps if a.kind == kind]

    async def all_businesses(self):  # type: ignore[no-untyped-def]
        return list(self.businesses)


def business(i: int, start: dt.date | None, end: dt.date | None, name: str = "Biz") -> Business:
    return Business(id=f"datasf_business:{i}", dba_name=name, address="1 Valencia St", lat=VALENCIA.lat,
                    lng=VALENCIA.lng, start_date=start, end_date=end, is_food_or_drink=True,
                    source_url="https://example.org", fetched_at=NOW)  # fmt: skip


@pytest.mark.parametrize("seed", range(25))
async def test_every_read_holds_only_what_was_knowable_on_a_random_cut_off(seed: int) -> None:
    rnd = random.Random(seed)
    base = dt.date(2018, 1, 1)

    def day() -> dt.date:
        return base + dt.timedelta(days=rnd.randrange(0, 3200))

    apps = []
    for i in range(120):
        filed = None if rnd.random() < 0.05 else day()
        decided = (
            None if rnd.random() < 0.3 or filed is None else filed + dt.timedelta(days=rnd.randrange(0, 700))
        )
        outcome = (
            rnd.choice(["approved", "withdrawn", "denied"])
            if decided
            else rnd.choice(["pending", "unknown", "approved"])
        )
        status = "Closed - Approved" if decided or outcome == "approved" else "Under Review"
        apps.append(app(i, filed=filed, decided=decided, outcome=outcome, status=status,
                        kind=rnd.choice(["cua", "cua", "planning_other", "entertainment_poe"])))  # fmt: skip
    bizs = [business(i, None if rnd.random() < 0.05 else day(), day() if rnd.random() < 0.5 else None)
            for i in range(60)]  # fmt: skip
    lics = [
        lic(
            str(100 + i),
            issued=day().isoformat(),
            status_today=rnd.choice(["ACTIVE", "SUREND"]),
            dates=tuple(sorted(x.isoformat() for x in {day() for _ in range(rnd.randrange(0, 3))})),
            latest=rnd.choice([("ACTIVE", "CANCEL"), ("REVPEN", "ACTIVE"), None]),
            in_export=rnd.random() < 0.7,
        )
        for i in range(60)
    ]
    cut = day()
    store = AsOfStore(ListStore(apps, bizs), cut, licences=licence_set(cut, lics))
    reads: list[Application] = [n.item for n in await store.nearby_applications(0, 0, 1e9, limit=10_000)]
    reads += [
        n.item for n in await store.nearby_applications(0, 0, 1e9, kinds=["cua", "abc_license"], limit=10_000)
    ]
    reads += await store.applications_of_kind("cua") + await store.applications_of_kind("abc_license")
    reads += [a for a in [await store.application(x.id) for x in apps] if a is not None]
    by_id = {a.id: a for a in apps}
    lic_by = {f"abc:{f.file_number}": f for f in lics}
    for r in reads:
        if r.kind == "abc_license":
            f = lic_by[r.id]
            assert f.issued <= cut and status_on_cut_off(f, cut) in ("ACTIVE", *asof.HELD_NOT_ACTIVE)
            continue
        src = by_id[r.id]
        assert r.kind in ("cua", "planning_other")
        assert src.filed_at is not None and src.filed_at <= cut
        if src.decided_at is not None and src.decided_at <= cut:
            assert r.decided_at == src.decided_at and "building_permits" not in r.extra
        else:
            assert r.status == OPEN_STATUS and r.outcome == "pending" and r.decided_at is None
            assert (
                not r.description
                and not r.conditions
                and r.decision_summary is None
                and r.hours_close is None
            )
            assert set(r.extra) <= asof.KEEP_EXTRA_OPEN
    bs = [n.item for n in await store.nearby_businesses(0, 0, 1e9)] + await store.all_businesses()
    for b in bs:
        assert b.start_date is not None and b.start_date <= cut and b.end_date is None
        src_b = next(x for x in bizs if x.id == b.id)
        assert src_b.end_date is None or src_b.end_date > cut
    assert await store.feedback_near(0, 0, 1e9) == []


async def test_the_cases_own_project_is_never_returned() -> None:
    own = app(5, filed=dt.date(2019, 1, 1), decided=dt.date(2019, 6, 1))
    sibling = own.model_copy(update={"id": "datasf_planning:2020-000005PRJ", "source_id": "2020-000005PRJ"})
    other = app(6, filed=dt.date(2019, 1, 1), decided=dt.date(2019, 6, 1))
    store = AsOfStore(ListStore([own, sibling, other], []), dt.date(2024, 1, 1), excluded_records=["2020-000005CUA"],
                      licences=licence_set(dt.date(2024, 1, 1), []))  # fmt: skip
    got = [n.item.id for n in await store.nearby_applications(0, 0, 1e9)]
    assert got == [other.id] and await store.application(own.id) is None


async def test_writes_are_refused() -> None:
    store = AsOfStore(ListStore([], []), AS_OF, licences=licence_set(AS_OF, []))
    with pytest.raises(asof.WriteRefusedError):
        await store.upsert_applications([])


# ---- the planted records, through a whole report -------------------------------------------------------------


def planted(store: Any) -> None:
    after = app(
        901, filed=dt.date(2025, 8, 1), decided=dt.date(2025, 12, 1), text=MARK, status=f"Closed {MARK}"
    )
    decided_after = app(902, filed=dt.date(2025, 3, 1), decided=dt.date(2025, 9, 1), text=MARK,
                        status=f"Closed {MARK}")  # fmt: skip
    open_now = app(903, filed=dt.date(2025, 1, 10), decided=None, outcome="pending", status=f"Under review {MARK}",
                   text=MARK)  # fmt: skip
    today_licence = app(904, filed=None, decided=dt.date(2025, 7, 1), kind="abc_license", text=MARK,
                        status=MARK).model_copy(update={"id": "abc:904", "source": "abc", "license_type": "41"})  # fmt: skip
    ent = app(905, filed=None, decided=None, kind="entertainment_poe", text=MARK, status=MARK)
    for a in (after, decided_after, open_now, today_licence, ent):
        a = a.model_copy(update={"lat": VALENCIA.lat + 0.0002, "lng": VALENCIA.lng + 0.0001})
        store.applications[a.id] = a
    store.businesses["datasf_business:900"] = business(900, dt.date(2025, 9, 1), None, name=MARK).model_copy(
        update={"lat": VALENCIA.lat + 0.0001}
    )
    store._flush("applications")
    store._flush("businesses")


async def test_no_planted_record_reaches_the_intake_or_the_rules_only_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The intake is the only model call, and neither it nor the report carries a record dated after the
    cut-off."""
    from app.tools import precedent_tools

    inner = seed_store(tmp_path / "data")
    planted(inner)
    lics = [lic("11", issued="2015-01-01"), lic("12", issued="2025-07-01", name=MARK)]
    store = AsOfStore(inner, AS_OF, excluded_records=["2099-000001CUA"], licences=licence_set(AS_OF, lics))
    monkeypatch.setattr(precedent_tools, "get_store", lambda: store)
    monkeypatch.setattr(precedent_tools, "get_geocoder", lambda: FakeGeocoder())
    script = MemoScript()
    runner = MemoRunner(FakeAnthropic(script), get_catalog(), settings, store, FakeGeocoder(), today=AS_OF)  # type: ignore[arg-type]

    async def emit(ev: Any) -> None:
        return None

    events = [ev async for ev in runner.run_memo(
        MemoRunInput(address="995 Valencia St", description="40-seat wine bar", rules_date=AS_OF,
                     allow_clarification=False), emit)]  # fmt: skip
    assert events[-1].type == "memo", events[-1].data
    sent = json.dumps(script.calls, default=str)
    assert script.calls and MARK not in sent
    memo = events[-1].data["memo"]
    assert MARK not in memo.model_dump_json()
    assert "abc:12" not in memo.model_dump_json()


async def test_a_request_carrying_the_cases_own_numbers_is_not_sent() -> None:
    from app.backtest.run import LeakError, make_runner_class

    runner_cls = make_runner_class()
    r = runner_cls(FakeAnthropic(MemoScript()), get_catalog(), settings, None, FakeGeocoder(), today=AS_OF,
               queue=None, forbidden=("2022-003434CUA", "2022-003434", "21132"))  # fmt: skip
    for text in ("see 2022-003434PRJ", "Motion 21132", "2022-003434CUA"):
        with pytest.raises(LeakError):
            await r._stream({"messages": [{"role": "user", "content": text}]}, False, None)


def test_the_alcohol_row_says_how_many_nearby_licences_had_an_unknown_status() -> None:
    d = dt.date(2023, 1, 1)
    changed_twice = ("2023-03-01", "2024-03-01")
    here = lic("21", issued="2020-01-01", dates=changed_twice, latest=("REVPEN", "ACTIVE"), dlat=0.0)
    near = lic("22", issued="2020-01-01", dates=changed_twice, latest=("REVPEN", "ACTIVE"), dlat=0.001)
    far = lic("23", issued="2020-01-01", dates=changed_twice, latest=("REVPEN", "ACTIVE"), dlat=0.01)
    ls = licence_set(d, [here, near, far, lic("24", issued="2020-01-01")])
    line = asof.unknown_status_line(
        ls, VALENCIA.lat, VALENCIA.lng, "208.01", normalized_address="993 VALENCIA ST"
    )
    assert line.rule_id == "backtest.licences_status_unknown"
    assert line.text.startswith(
        "Licences with an unknown status on 2023-01-01: 2 ABC licences within 1,000 ft (1 at this address) and 3 in the census tract"
    )
    assert "left out" in line.text
    none = asof.unknown_status_line(
        licence_set(d, [lic("25", issued="2020-01-01")]), VALENCIA.lat, VALENCIA.lng, "208.01"
    )
    assert (
        none.text
        == "Licences with an unknown status on 2023-01-01: none within 1,000 ft or in the census tract."
    )
    # the sensitivity check counts them as active, and nothing else changes
    alt = asof.with_unknown_as_active(ls)
    assert {f.file_number for f, s in alt.held if s == "ACTIVE"} == {
        "21",
        "22",
        "23",
        "24",
    } and not alt.unknown
