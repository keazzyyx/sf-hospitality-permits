"""Answer rounds (owner decision of 2026-11-16, app.memo.answers): "Answer and run again" runs the same memo again
with more intake answers, free, with no model call, up to five times a memo."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.memo.context as ctx
import app.routes.memos as memo_routes
from app.agents.memo_runner import MemoRunner
from app.agents.runner import RunnerEvent
from app.catalog.loader import get_catalog
from app.core.config import settings
from app.deps import get_memo_runner
from app.main import app
from app.memo.answers import (
    ANSWER_ROUND_LIMIT,
    ANSWERS_FAILED_MESSAGE,
    ANSWERS_FOLLOW_UP_MESSAGE,
    ANSWERS_STOPPED_MESSAGE,
    ANSWERS_UNAVAILABLE_MESSAGE,
    IntakeBasis,
    merge_answers,
)
from app.memo.intake import IntakeAnswers
from app.services.db import MemoryDatabase
from app.services.memos import GENERATING_TIMEOUT, MemoService
from tests import test_memo_api
from tests.conftest import TODAY, parse_sse
from tests.fakes import BASE_PROFILE, FakeAnthropic
from tests.memo_fakes import MemoScript
from tests.test_api import USER_ID, auth, token
from tests.test_memo_api import LEGACY_ID, _legacy_row, _rerun, create_memo

# the fixtures of the memo API tests: a client on an in-memory database and the seeded store, and an owner account
client = test_memo_api.client
db = test_memo_api.db
owner = test_memo_api.owner

OTHER_USER = "33333333-3333-4333-8333-333333333333"


class NoModel:
    """A model client that fails the test if anything reads it: an answer round makes no model call."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the intake model was called ({name})")


def _runner(client: Any) -> MemoRunner:
    return MemoRunner(client, get_catalog(), settings, ctx.get_store(), ctx.get_geocoder(), today=TODAY)


def _use_runner(make: Any) -> None:
    app.dependency_overrides[get_memo_runner] = make


def answer(client: TestClient, memo_id: str, body: Any, headers: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    with client.stream("POST", f"/v1/memos/{memo_id}/answers", json=body, headers=headers or auth()) as r:
        status = r.status_code
        text = "".join(r.iter_text())
    return status, (parse_sse(text) if status == 200 else json.loads(text)), text


def _row(db: MemoryDatabase, memo_id: str) -> dict[str, Any]:
    return next(r for r in db.tables["memos"] if r["id"] == memo_id)


def _new_memo(client: TestClient, **body: Any) -> str:
    status, events = create_memo(client, **body)
    assert status == 200 and events[-1][0] == "memo", events
    return str(events[-1][1]["id"])


def _without_time(memo: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in memo.items() if k != "generated_at"}


@pytest.fixture
def many_previews(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "FREE_TEASER_LIMIT", 50)


@pytest.fixture(autouse=True)
def _fresh_limiter() -> None:
    memo_routes.answers_limiter._hits.clear()


# ---- the report: the same as a new memo with the merged answers -------------------------------------------------
@pytest.mark.parametrize(
    ("first", "then", "merged"),
    [
        # answers added to none
        (
            None,
            {"stories": ["first"], "last_use": "restaurant"},
            {"stories": ["first"], "last_use": "restaurant"},
        ),
        # added to the answers the memo has
        (
            {"floor_area_sqft": 1400},
            {"stories": ["first"], "fewer_than_50_people": True},
            {"floor_area_sqft": 1400, "stories": ["first"], "fewer_than_50_people": True},
        ),
        # "No alcohol" after "beer and wine": what is poured is dropped, and the line that the answer won over the
        # description is read from the description, as on a new memo
        ({"alcohol_served": "beer_wine"}, {"liquor_licence": "none"}, {"liquor_licence": "none"}),
        # "No alcohol" changed to a new licence: the alcohol the description states is back, as on a new memo (a
        # round that put the answers on the profile the first answers had cleared would have lost it)
        ({"liquor_licence": "none"}, {"liquor_licence": "new"}, {"liquor_licence": "new"}),
        # alcohol outdoors after "no outdoor area": the place is not known
        ({"outdoor_area": "none"}, {"outdoor_alcohol_service": True}, {"outdoor_alcohol_service": True}),
        # not a chain after a chain of 15: the count goes
        ({"part_of_chain": True, "other_locations": 15}, {"part_of_chain": False}, {"part_of_chain": False}),
    ],
)
def test_a_round_gives_the_report_a_new_memo_with_the_merged_answers_gets(
    client: TestClient,
    db: MemoryDatabase,
    many_previews: None,
    first: dict[str, Any] | None,
    then: dict[str, Any],
    merged: dict[str, Any],
) -> None:
    memo_id = _new_memo(client, intake=first)
    _use_runner(lambda: _runner(NoModel()))
    status, events, _ = answer(client, memo_id, then)
    assert status == 200 and events[-1][0] == "memo", events
    assert events[0] == ("answers_round", {"memo_id": memo_id, "round": 1})
    row = _row(db, memo_id)
    assert row["intake"] == merged and row["answers_round"] == 1 and row["status"] == "ready"

    # a new memo with the same description and the merged answers, read by the same intake model
    _use_runner(lambda: _runner(FakeAnthropic(MemoScript())))
    fresh = _row(db, _new_memo(client, intake=merged))
    assert row["profile"] == fresh["profile"]
    assert row["teaser"] == fresh["teaser"]
    assert _without_time(row["memo"]) == _without_time(fresh["memo"])


def test_an_answer_that_contradicts_the_description_is_read_as_on_a_new_memo(
    client: TestClient, db: MemoryDatabase, many_previews: None
) -> None:
    """Fewer than 50 people against 60 seats the description states: the building row names the conflict, on a
    round as on a new memo."""
    desc = (
        "60-seat restaurant of 1,400 square feet, small kitchen, beer and wine, open until 1am, occasional live "
        "music, amplified"
    )
    profile = {**BASE_PROFILE, "business_type": "restaurant", "seats": 60}
    script = lambda: MemoScript(profile=dict(profile))  # noqa: E731
    first = {"stories": ["first"], "last_use": "retail", "existing_occupancy_group": "B"}
    _use_runner(lambda: _runner(FakeAnthropic(script())))
    memo_id = _new_memo(client, description=desc, intake=first)
    _use_runner(lambda: _runner(NoModel()))
    status, events, _ = answer(client, memo_id, {"fewer_than_50_people": True})
    assert status == 200 and events[-1][0] == "memo", events
    row = _row(db, memo_id)
    assert row["profile"]["seats"] == 60 and row["profile"]["occupants_under_50"] is True
    building = next(r for r in row["memo"]["approvals"] if r["area"] == "building_change_of_use")
    texts = [line["text"] for line in building["basis"]]
    assert (
        "You answered that the space is for fewer than 50 people, but the description gives 60 seats, which means "
        "at least 50 people. The two disagree, so the proposed occupancy group is not established."
    ) in texts
    assert row["memo"]["pathway"]["changes"]["building_occupancy"] == "not_established"
    # before the round the 60 seats were read: Assembly Group A-2, a change of occupancy from Group B
    (rev,) = db.tables["memo_revisions"]
    assert rev["memo"]["pathway"]["changes"]["building_occupancy"] != "not_established"
    _use_runner(lambda: _runner(FakeAnthropic(script())))
    fresh = _row(db, _new_memo(client, description=desc, intake=row["intake"]))
    assert _without_time(row["memo"]) == _without_time(fresh["memo"])


def test_a_round_makes_no_model_call(client: TestClient, db: MemoryDatabase) -> None:
    script = MemoScript()
    _use_runner(lambda: _runner(FakeAnthropic(script)))
    memo_id = _new_memo(client)
    intake_calls = len(script.calls)
    assert intake_calls >= 1  # the intake of the new memo
    status, events, _ = answer(client, memo_id, {"stories": ["first"]})
    assert status == 200 and events[-1][0] == "memo", events
    assert len(script.calls) == intake_calls  # none for the round
    # the stage events say what the round does: no reading of the description
    started = [d for e, d in events if e == "stage" and d["status"] == "started"]
    assert [d["stage"] for d in started] == ["intake", "records", "precedent", "finalize"]
    assert started[0]["message"] == "Applying your answers to the facts read from your description…"
    # and the report names the model that read the description when the memo was made
    assert _row(db, memo_id)["memo"]["model_versions"] == _row(db, memo_id)["intake_basis"]["model_versions"]
    assert _row(db, memo_id)["memo"]["model_versions"]


def test_a_new_memo_keeps_its_intake_basis_without_the_models_own_text(
    client: TestClient, db: MemoryDatabase
) -> None:
    memo_id = _new_memo(client, intake={"liquor_licence": "new"})
    basis = IntakeBasis.model_validate(_row(db, memo_id)["intake_basis"])
    # before the answers: the licence answer is not on it
    assert basis.profile.alcohol_transaction is None and basis.profile.intake_answered == []
    assert basis.profile.business_name is None and basis.profile.neighborhood is None
    assert basis.profile.assumptions == []
    assert basis.quotes  # the applicant's words each fact came from
    rec = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert rec["answers_available"] is True and rec["answers_round"] == 0
    assert rec["answers_rounds_left"] == ANSWER_ROUND_LIMIT and rec["answers_running"] is False
    assert "intake_basis" not in rec


# ---- who and which memo ---------------------------------------------------------------------------------------
def test_only_the_owner_can_answer_or_read_the_revisions(client: TestClient, db: MemoryDatabase) -> None:
    memo_id = _new_memo(client)
    other = auth(token(OTHER_USER))
    status, body, _ = answer(client, memo_id, {"stories": ["first"]}, headers=other)
    assert status == 404 and body["detail"]["code"] == "not_found"
    assert _row(db, memo_id)["status"] == "ready" and not _row(db, memo_id).get("answers_run")
    assert client.get(f"/v1/memos/{memo_id}/revisions", headers=other).status_code == 404
    assert client.get(f"/v1/memos/{memo_id}/revisions", headers=auth()).json() == {"revisions": []}
    assert client.post(f"/v1/memos/{memo_id}/answers", json={"stories": ["first"]}).status_code == 401


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"status": "generating"}, "not_ready"),
        ({"status": "pending_clarification"}, "not_ready"),
        ({"status": "generating", "answers_run": "11111111-0000-4000-8000-000000000000"}, "answers_running"),
        # a failed memo whose run never got to the intake has no basis to answer
        ({"status": "failed", "intake_basis": None}, "answers_unavailable"),
        # a memo made before the basis was kept
        ({"intake_basis": None}, "answers_unavailable"),
    ],
)
def test_a_memo_that_is_not_ready_or_has_no_basis_is_refused(
    client: TestClient, db: MemoryDatabase, change: dict[str, Any], code: str
) -> None:
    memo_id = _new_memo(client)
    _row(db, memo_id).update(change)
    before = dict(_row(db, memo_id))
    status, body, _ = answer(client, memo_id, {"stories": ["first"]})
    assert status == 409 and body["detail"]["code"] == code
    assert _row(db, memo_id) == before
    if code == "answers_unavailable":
        assert body["detail"]["message"] == ANSWERS_UNAVAILABLE_MESSAGE
        rec = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
        assert rec["answers_available"] is False


def test_a_legacy_memo_is_refused(client: TestClient, db: MemoryDatabase) -> None:
    _legacy_row(db, access="full", memo_id=LEGACY_ID)
    status, body, _ = answer(client, LEGACY_ID, {"stories": ["first"]})
    assert status == 409 and body["detail"]["code"] == "legacy_format"
    assert client.get(f"/v1/memos/{LEGACY_ID}", headers=auth()).json()["memo"]["answers_available"] is False


@pytest.mark.parametrize(
    "body",
    [
        {"address": "1 Somewhere Else", "stories": ["first"]},
        {"description": "a different concept altogether", "stories": ["first"]},
        {"profile_overrides": {"seats": 10}, "stories": ["first"]},
        {"rerun_of": LEGACY_ID, "stories": ["first"]},
        {"intake": {"stories": ["first"]}},
        {"seats": 40},
        # two answers that contradict each other in the same request
        {"liquor_licence": "none", "alcohol_served": "beer_wine"},
        {"outdoor_area": "none", "outdoor_alcohol_service": False},
        {"part_of_chain": False, "other_locations": 4},
        {"floor_area_sqft": 0},
    ],
)
def test_anything_but_valid_intake_answers_is_refused(
    client: TestClient, db: MemoryDatabase, body: dict[str, Any]
) -> None:
    memo_id = _new_memo(client)
    before = dict(_row(db, memo_id))
    status, _, _ = answer(client, memo_id, body)
    assert status == 422
    assert _row(db, memo_id) == before


@pytest.mark.parametrize(
    ("stored", "body", "merged"),
    [
        # a new count for a chain the memo already has
        (
            {"part_of_chain": True, "other_locations": 3},
            {"other_locations": 7},
            {"part_of_chain": True, "other_locations": 7},
        ),
        # the count added to a stored "part of a chain"
        ({"part_of_chain": True}, {"other_locations": 2}, {"part_of_chain": True, "other_locations": 2}),
    ],
)
def test_a_follow_up_sent_alone_stands_on_the_answer_it_follows_when_that_is_stored(
    client: TestClient,
    db: MemoryDatabase,
    stored: dict[str, Any],
    body: dict[str, Any],
    merged: dict[str, Any],
) -> None:
    memo_id = _new_memo(client, intake=stored)
    status, events, _ = answer(client, memo_id, body)
    assert status == 200 and events[-1][0] == "memo", events
    assert _row(db, memo_id)["intake"] == merged and _row(db, memo_id)["answers_round"] == 1


@pytest.mark.parametrize("stored", [None, {"part_of_chain": False}, {"floor_area_sqft": 1800}])
def test_a_follow_up_with_no_answer_to_stand_on_is_refused(
    client: TestClient, db: MemoryDatabase, stored: dict[str, Any] | None
) -> None:
    """A count of other locations with no "part of a chain" answer, sent or stored (or against a stored "no"), is
    refused: the chain is never inferred from the count."""
    memo_id = _new_memo(client, intake=stored)
    before = dict(_row(db, memo_id))
    status, body, _ = answer(client, memo_id, {"other_locations": 4})
    assert status == 422 and body["detail"]["code"] == "validation_error", body
    assert body["detail"]["message"] == ANSWERS_FOLLOW_UP_MESSAGE
    assert _row(db, memo_id) == before
    assert not [e for e in db.tables.get("usage_events", []) if e["event"] == "memo_answers_rerun"]


def test_no_answer_or_the_same_answers_are_refused(client: TestClient, db: MemoryDatabase) -> None:
    memo_id = _new_memo(client, intake={"floor_area_sqft": 1800})
    status, body, _ = answer(client, memo_id, {})
    assert status == 422 and body["detail"]["code"] == "validation_error"
    status, body, _ = answer(client, memo_id, {"floor_area_sqft": None})
    assert status == 422
    status, body, _ = answer(client, memo_id, {"floor_area_sqft": 1800})
    assert status == 422 and body["detail"]["code"] == "no_new_answers"
    assert _row(db, memo_id).get("answers_round") is None


# ---- merging ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("stored", "new", "merged", "dropped"),
    [
        (
            {"floor_area_sqft": 1800, "liquor_licence": "new"},
            {"floor_area_sqft": 2000},
            {"floor_area_sqft": 2000, "liquor_licence": "new"},
            (),
        ),
        (
            {"part_of_chain": True, "other_locations": 15},
            {"part_of_chain": False},
            {"part_of_chain": False},
            ("other_locations",),
        ),
        (
            {"part_of_chain": True, "other_locations": 15},
            {"part_of_chain": True},
            {"part_of_chain": True, "other_locations": 15},
            (),
        ),
        (
            {"alcohol_served": "beer_wine", "stories": ["first"]},
            {"liquor_licence": "none"},
            {"liquor_licence": "none", "stories": ["first"]},
            ("alcohol_served",),
        ),
        (
            {"outdoor_alcohol_service": True},
            {"liquor_licence": "none"},
            {"liquor_licence": "none"},
            ("outdoor_alcohol_service",),
        ),
        (
            {"outdoor_alcohol_service": False},
            {"liquor_licence": "none"},
            {"liquor_licence": "none", "outdoor_alcohol_service": False},
            (),
        ),
        (
            {"outdoor_area": "front", "outdoor_alcohol_service": True},
            {"outdoor_area": "none"},
            {"outdoor_area": "none"},
            ("outdoor_alcohol_service",),
        ),
        (
            {"liquor_licence": "none"},
            {"alcohol_served": "full_liquor"},
            {"alcohol_served": "full_liquor"},
            ("liquor_licence",),
        ),
        (
            {"liquor_licence": "none"},
            {"outdoor_alcohol_service": True},
            {"outdoor_alcohol_service": True},
            ("liquor_licence",),
        ),
        (
            {"outdoor_area": "none"},
            {"outdoor_alcohol_service": False},
            {"outdoor_alcohol_service": False},
            ("outdoor_area",),
        ),
    ],
)
def test_the_new_answers_win_and_a_stored_answer_they_contradict_is_dropped(
    stored: dict[str, Any], new: dict[str, Any], merged: dict[str, Any], dropped: tuple[str, ...]
) -> None:
    got, gone = merge_answers(IntakeAnswers.model_validate(stored), IntakeAnswers.model_validate(new))
    assert got.model_dump(exclude_none=True) == merged
    assert gone == dropped


def test_every_answer_that_can_contradict_another_follows_the_one_it_depends_on() -> None:
    """`merge_answers` reads the questions in order; that is the whole rule only while each answer that can
    contradict another comes after it in `QUESTIONS`."""
    from app.memo.intake import QUESTIONS

    order = [q.id for q in QUESTIONS]
    for later, earlier in (
        ("other_locations", "part_of_chain"),
        ("alcohol_served", "liquor_licence"),
        ("outdoor_alcohol_service", "liquor_licence"),
        ("outdoor_alcohol_service", "outdoor_area"),
        ("food_service", "liquor_licence"),
        ("food_service", "alcohol_served"),
        ("food_service", "outdoor_alcohol_service"),
    ):
        assert order.index(earlier) < order.index(later)


def test_a_round_merges_into_the_stored_answers(client: TestClient, db: MemoryDatabase) -> None:
    memo_id = _new_memo(client, intake={"floor_area_sqft": 1800, "alcohol_served": "beer_wine"})
    status, events, _ = answer(client, memo_id, {"liquor_licence": "none", "stories": ["first"]})
    assert status == 200 and events[-1][0] == "memo", events
    assert events[-1][1]["intake"] == {
        **dict.fromkeys(IntakeAnswers.model_fields),
        "floor_area_sqft": 1800,
        "liquor_licence": "none",
        "stories": ["first"],
    }
    (event,) = [e for e in db.tables["usage_events"] if e["event"] == "memo_answers_rerun"]
    assert event["properties"] == {
        "memo_id": memo_id,
        "round": 1,
        "answered": ["liquor_licence", "stories"],
        "replaced": ["alcohol_served"],
        "access": "teaser",
    }


# ---- access and charges ---------------------------------------------------------------------------------------------
def test_a_teaser_stays_a_teaser_and_reveals_nothing_locked(client: TestClient, db: MemoryDatabase) -> None:
    memo_id = _new_memo(client)
    _new_memo(client)  # both free previews used
    profile = dict(db.tables["profiles"][0])
    assert profile["teasers_generated"] == settings.FREE_TEASER_LIMIT
    status, events, text = answer(client, memo_id, {"stories": ["first"], "last_use": "bar"})
    assert status == 200 and events[-1][0] == "memo", events
    rec = events[-1][1]
    assert rec["access"] == "teaser" and rec["memo"] is None and rec["teaser"] is not None
    assert rec["answers_round"] == 1 and rec["unlocked_at"] is None
    # no rule line, fact or record of the full report is in the stream
    assert "zoning.status" not in text and "citations" not in text and 'approvals"' not in text
    assert client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]["memo"] is None
    for path in ("export.pdf", "map.geojson"):
        assert client.get(f"/v1/memos/{memo_id}/{path}", headers=auth()).status_code == 402
    (rev,) = client.get(f"/v1/memos/{memo_id}/revisions", headers=auth()).json()["revisions"]
    assert rev["memo"] is None and rev["teaser"] is not None
    # nothing charged: no preview counted, no credit used, and the round went ahead with none left
    assert db.tables["profiles"][0] == profile
    assert _row(db, memo_id)["access"] == "teaser"


def test_an_unlocked_memo_stays_unlocked_and_a_pro_accounts_teaser_stays_a_teaser(
    client: TestClient, db: MemoryDatabase, many_previews: None
) -> None:
    teaser_id = _new_memo(client)
    db.tables["profiles"][0]["memo_credits"] = 1
    full_id = _new_memo(client)
    assert client.post(f"/v1/memos/{full_id}/unlock", headers=auth()).status_code == 200
    unlocked_at = _row(db, full_id)["unlocked_at"]
    db.tables["profiles"][0]["pro_status"] = "active"  # Pro since: a round still gains no access
    profile = dict(db.tables["profiles"][0])
    status, events, _ = answer(client, full_id, {"stories": ["first"]})
    assert status == 200 and events[-1][1]["access"] == "full" and events[-1][1]["memo"] is not None
    assert _row(db, full_id)["unlocked_at"] == unlocked_at
    status, events, _ = answer(client, teaser_id, {"stories": ["first"]})
    assert status == 200 and events[-1][1]["access"] == "teaser" and events[-1][1]["memo"] is None
    assert _row(db, teaser_id).get("unlocked_at") is None
    assert db.tables["profiles"][0] == profile


def test_a_round_running_does_not_hold_a_free_preview(client: TestClient, db: MemoryDatabase) -> None:
    memo_id = _new_memo(client)  # one free preview left
    _row(db, memo_id).update(status="generating", answers_run="11111111-0000-4000-8000-000000000000")
    status, events = create_memo(client)
    assert status == 200 and events[-1][0] == "memo"


# ---- rounds, history and limits ---------------------------------------------------------------------------------------
def test_each_round_keeps_the_version_it_replaced(
    client: TestClient, db: MemoryDatabase, owner: None
) -> None:
    memo_id = _new_memo(client, intake={"floor_area_sqft": 1800})
    original = dict(_row(db, memo_id))
    assert answer(client, memo_id, {"stories": ["first"]})[0] == 200
    after_one = dict(_row(db, memo_id))
    assert answer(client, memo_id, {"last_use": "bar"})[0] == 200
    revs = sorted(db.tables["memo_revisions"], key=lambda r: r["round"])
    assert [r["round"] for r in revs] == [1, 2]
    for rev, version in zip(revs, (original, after_one), strict=True):
        assert rev["memo_id"] == memo_id and rev["user_id"] == USER_ID and rev["created_at"]
        assert rev["id"] == MemoService.revision_id(memo_id, rev["round"])
        for key in ("intake", "profile", "memo", "teaser"):
            assert rev[key] == version[key]
    listed = client.get(f"/v1/memos/{memo_id}/revisions", headers=auth()).json()["revisions"]
    assert [r["round"] for r in listed] == [1, 2]
    assert listed[0]["intake"]["floor_area_sqft"] == 1800 and listed[0]["intake"]["stories"] is None
    assert listed[1]["intake"]["stories"] == ["first"]
    assert listed[0]["generated_at"] == original["memo"]["generated_at"]
    assert listed[0]["memo"] is not None  # an unlocked memo shows its earlier versions in full
    rec = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert rec["answers_round"] == 2 and rec["answers_rounds_left"] == ANSWER_ROUND_LIMIT - 2
    assert rec["answered_at"] and rec["intake"]["last_use"] == "bar"
    # deleting the memo deletes its history
    assert client.delete(f"/v1/memos/{memo_id}", headers=auth()).status_code == 204
    assert db.tables["memo_revisions"] == []


def test_the_sixth_round_is_refused(client: TestClient, db: MemoryDatabase) -> None:
    memo_id = _new_memo(client)
    areas = [1000, 1100, 1200, 1300, 1400]
    for n, area in enumerate(areas, start=1):
        status, events, _ = answer(client, memo_id, {"floor_area_sqft": area})
        assert status == 200 and events[0][1]["round"] == n
    rec = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert rec["answers_round"] == ANSWER_ROUND_LIMIT == 5
    assert rec["answers_rounds_left"] == 0 and rec["answers_available"] is False
    status, body, _ = answer(client, memo_id, {"floor_area_sqft": 1500})
    assert status == 409 and body["detail"]["code"] == "answers_round_limit"
    assert "5 times" in body["detail"]["message"]
    assert _row(db, memo_id)["intake"] == {"floor_area_sqft": 1400}
    assert len(db.tables["memo_revisions"]) == 5
    rounds = [e for e in db.tables["usage_events"] if e["event"] == "memo_answers_rerun"]
    assert [e["properties"]["round"] for e in rounds] == [1, 2, 3, 4, 5]


def test_answer_rounds_are_rate_limited(
    client: TestClient, db: MemoryDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    memo_id = _new_memo(client)
    monkeypatch.setattr(memo_routes.answers_limiter, "limit", 1)
    assert answer(client, memo_id, {"stories": ["first"]})[0] == 200
    status, body, _ = answer(client, memo_id, {"last_use": "bar"})
    assert status == 429 and body["detail"]["code"] == "rate_limited"
    assert _row(db, memo_id)["answers_round"] == 1


# ---- a round that does not finish --------------------------------------------------------------------------------------
def _failing_round(monkeypatch: pytest.MonkeyPatch, *, crash: bool) -> dict[str, bool]:
    """Make the next rounds fail: the run reports an error, or (crash) the save raises, so the detached run's own
    handler ends the round. Returns a switch to turn it off."""
    on = {"fail": True}
    real_run, real_save = MemoRunner.run_answers, MemoService.save_answers_result

    async def failing_run(self: MemoRunner, inp: Any, emit: Any) -> Any:
        if on["fail"] and not crash:
            yield RunnerEvent("error", {"code": "generation_failed", "message": "records unavailable"})
            return
        async for ev in real_run(self, inp, emit):
            yield ev

    async def failing_save(self: MemoService, *args: Any, **kwargs: Any) -> Any:
        if on["fail"] and crash:
            raise RuntimeError("the save broke")
        return await real_save(self, *args, **kwargs)

    monkeypatch.setattr(MemoRunner, "run_answers", failing_run)
    monkeypatch.setattr(MemoService, "save_answers_result", failing_save)
    return on


@pytest.mark.parametrize("crash", [False, True])
def test_a_round_that_fails_leaves_the_memo_as_it_was_and_is_not_counted(
    client: TestClient, db: MemoryDatabase, monkeypatch: pytest.MonkeyPatch, crash: bool
) -> None:
    memo_id = _new_memo(client, intake={"floor_area_sqft": 1800})
    before = dict(_row(db, memo_id))
    switch = _failing_round(monkeypatch, crash=crash)
    status, events, _ = answer(client, memo_id, {"stories": ["first"]})
    assert status == 200 and events[-1][0] == "error"
    row = _row(db, memo_id)
    assert row["status"] == "ready" and row["error"] == ANSWERS_FAILED_MESSAGE and row["answers_run"] is None
    for key in ("memo", "teaser", "profile", "intake", "access"):
        assert row[key] == before[key]
    assert not row.get("answers_round") and not db.tables.get("memo_revisions")
    rec = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert rec["status"] == "ready" and rec["error"] == ANSWERS_FAILED_MESSAGE and rec["answers_available"]
    if crash:
        assert events[-1][1] == {"code": "generation_failed", "message": ANSWERS_FAILED_MESSAGE}
    switch["fail"] = False
    # tried again, it is round 1
    status, events, _ = answer(client, memo_id, {"stories": ["first"]})
    assert status == 200 and events[0][1]["round"] == 1 and events[-1][0] == "memo"
    assert _row(db, memo_id)["error"] is None


def _late_save(
    db: MemoryDatabase, memo_id: str, claim: str, version: dict[str, Any]
) -> dict[str, Any] | None:
    """A round with this claim finishing now: it tries to save the report of `version` with a new answer."""
    import asyncio

    from app.models.memo import Memo, MemoTeaser
    from app.models.profile import BusinessProfile

    return asyncio.run(
        MemoService(db, settings).save_answers_result(
            memo_id,
            claim,
            1,
            IntakeAnswers(last_use="bar"),
            BusinessProfile.model_validate(version["profile"]),
            Memo.model_validate(version["memo"]),
            MemoTeaser.model_validate(version["teaser"]),
            lat=0.0,
            lng=0.0,
            address="elsewhere",
        )
    )


def _end(db: MemoryDatabase, memo_id: str, claim: str) -> bool:
    import asyncio

    return asyncio.run(MemoService(db, settings).end_answers(memo_id, claim, ANSWERS_FAILED_MESSAGE))


STALE_CLAIM = "22222222-0000-4000-8000-000000000000"


def _stall(db: MemoryDatabase, memo_id: str, claim: str = STALE_CLAIM) -> None:
    long_ago = (dt.datetime.now(dt.UTC) - GENERATING_TIMEOUT - dt.timedelta(minutes=1)).isoformat()
    _row(db, memo_id).update(status="generating", answers_run=claim, updated_at=long_ago)


def test_a_round_left_stalled_reads_as_the_report_before_it_and_its_late_result_is_not_saved(
    client: TestClient, db: MemoryDatabase
) -> None:
    memo_id = _new_memo(client)
    before = dict(_row(db, memo_id))
    _stall(db, memo_id)
    rec = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert rec["status"] == "ready" and rec["error"] == ANSWERS_STOPPED_MESSAGE
    assert rec["teaser"] == before["teaser"] and rec["answers_running"] is False
    # a new round takes it over
    status, events, _ = answer(client, memo_id, {"stories": ["first"]})
    assert status == 200 and events[-1][0] == "memo" and _row(db, memo_id)["answers_round"] == 1
    # the stalled round, finishing now, saves nothing
    assert _late_save(db, memo_id, STALE_CLAIM, before) is None
    assert _row(db, memo_id)["intake"] == {"stories": ["first"]}


def test_a_stalled_round_that_finishes_with_no_round_after_it_saves_nothing_and_is_not_counted(
    client: TestClient, db: MemoryDatabase
) -> None:
    """The page said the stalled round stopped and was not counted (ANSWERS_STOPPED_MESSAGE), so its late result
    is not saved even when no later round took its claim: the memo is ended as the page showed it."""
    memo_id = _new_memo(client, intake={"floor_area_sqft": 1800})
    before = dict(_row(db, memo_id))
    _stall(db, memo_id)
    shown = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert shown["status"] == "ready" and shown["error"] == ANSWERS_STOPPED_MESSAGE
    assert _late_save(db, memo_id, STALE_CLAIM, before) is None
    row = _row(db, memo_id)
    for key in ("memo", "teaser", "profile", "intake", "access"):
        assert row[key] == before[key]
    assert not row.get("answers_round") and not db.tables.get("memo_revisions")
    # the stored row now says what the page said
    assert row["status"] == "ready" and row["answers_run"] is None and row["error"] == ANSWERS_STOPPED_MESSAGE
    rec = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert rec["status"] == "ready" and rec["error"] == ANSWERS_STOPPED_MESSAGE
    assert rec["answers_round"] == 0 and rec["answers_rounds_left"] == ANSWER_ROUND_LIMIT
    # tried again, it is round 1
    status, events, _ = answer(client, memo_id, {"stories": ["first"]})
    assert status == 200 and events[0][1]["round"] == 1 and events[-1][0] == "memo"


def test_a_round_left_behind_never_saves_over_or_ends_the_round_running_now(
    client: TestClient, db: MemoryDatabase
) -> None:
    """Round A stalls; round B claims the memo and is still running. A finishing (or failing) now changes nothing:
    only the round whose claim the row holds saves or ends it."""
    import asyncio

    memo_id = _new_memo(client)
    before = dict(_row(db, memo_id))
    _stall(db, memo_id)
    b_claim = asyncio.run(MemoService(db, settings).start_answers(dict(_row(db, memo_id))))
    assert b_claim is not None and b_claim != STALE_CLAIM
    running = dict(_row(db, memo_id))
    assert running["status"] == "generating" and running["answers_run"] == b_claim
    assert _late_save(db, memo_id, STALE_CLAIM, before) is None
    assert _row(db, memo_id) == running and not db.tables.get("memo_revisions")
    assert _end(db, memo_id, STALE_CLAIM) is False
    assert _row(db, memo_id) == running
    # B's own claim still saves
    assert _late_save(db, memo_id, b_claim, before) is not None
    assert _row(db, memo_id)["answers_round"] == 1 and _row(db, memo_id)["answers_run"] is None


@pytest.mark.parametrize("stalled", [False, True])
def test_a_memo_in_an_answer_round_can_be_unlocked(
    client: TestClient, db: MemoryDatabase, stalled: bool
) -> None:
    """The report from before the round is there, and a round never changes `access`: unlocking it while a round
    runs, or after one stalled, spends the credit as on a ready memo, and the round's result keeps the access."""
    memo_id = _new_memo(client)
    before = dict(_row(db, memo_id))
    db.tables["profiles"][0]["memo_credits"] = 1
    if stalled:
        _stall(db, memo_id)
    else:
        _row(db, memo_id).update(status="generating", answers_run=STALE_CLAIM)
    r = client.post(f"/v1/memos/{memo_id}/unlock", headers=auth())
    assert r.status_code == 200, r.text
    rec = r.json()["memo"]
    assert rec["access"] == "full" and rec["memo"] is not None
    assert db.tables["profiles"][0]["memo_credits"] == 0
    row = _row(db, memo_id)
    assert row["access"] == "full" and row["unlocked_at"]
    assert row["status"] == "generating" and row["answers_run"] == STALE_CLAIM  # the round is left as it is
    if not stalled:
        saved = _late_save(db, memo_id, STALE_CLAIM, before)
        assert saved is not None and saved["access"] == "full" and saved["unlocked_at"] == row["unlocked_at"]


def test_a_memo_still_being_made_cannot_be_unlocked(client: TestClient, db: MemoryDatabase) -> None:
    memo_id = _new_memo(client)
    db.tables["profiles"][0]["memo_credits"] = 1
    _row(db, memo_id).update(status="generating", memo=None, teaser=None, answers_run=None)
    r = client.post(f"/v1/memos/{memo_id}/unlock", headers=auth())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_ready"
    assert db.tables["profiles"][0]["memo_credits"] == 1


def test_two_rounds_sent_at_once_start_one(client: TestClient, db: MemoryDatabase) -> None:
    import asyncio

    memo_id = _new_memo(client)
    svc = MemoService(db, settings)
    row = dict(_row(db, memo_id))
    first = asyncio.run(svc.start_answers(row))
    second = asyncio.run(svc.start_answers(row))  # read the same row before the first claimed it
    assert first is not None and second is None
    assert _row(db, memo_id)["answers_run"] == first
    status, body, _ = answer(client, memo_id, {"stories": ["first"]})
    assert status == 409 and body["detail"]["code"] == "answers_running"


def test_a_free_rerun_in_an_answer_round_does_not_give_the_free_rerun_back(
    client: TestClient, db: MemoryDatabase
) -> None:
    """A round makes the free re-run's memo "generating" again; that memo was ready, so neither deleting it nor
    leaving it stalled gives the legacy memo's free re-run back."""

    _legacy_row(db, access="full", memo_id=LEGACY_ID)
    status, events = _rerun(client, LEGACY_ID)
    assert status == 200
    new_id = events[-1][1]["id"]
    long_ago = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)).isoformat()
    _row(db, new_id).update(
        status="generating", answers_run="33333333-0000-4000-8000-000000000000", updated_at=long_ago
    )
    legacy = client.get(f"/v1/memos/{LEGACY_ID}", headers=auth()).json()["memo"]
    assert legacy["rerun_free"] is False
    assert client.delete(f"/v1/memos/{new_id}", headers=auth()).status_code == 204
    legacy = client.get(f"/v1/memos/{LEGACY_ID}", headers=auth()).json()["memo"]
    assert legacy["rerun_free"] is False


def test_a_round_reads_the_records_at_the_address_the_memo_was_made_for(
    client: TestClient, db: MemoryDatabase
) -> None:
    """The address is fixed: a round reads the records at the point and parcel the first run read and never
    geocodes the stored address again, so a geocoder that no longer finds it changes nothing."""
    memo_id = _new_memo(client)
    before = dict(_row(db, memo_id))
    assert _row(db, memo_id)["intake_basis"]["geo"]["parcel"] == before["memo"]["parcel"] == "3616/065"
    geocoder = ctx.get_geocoder()
    calls = len(geocoder.calls)
    geocoder.hit = None  # the address is not found any more
    status, events, _ = answer(client, memo_id, {"stories": ["first"]})
    assert status == 200 and events[-1][0] == "memo", events
    assert len(geocoder.calls) == calls
    row = _row(db, memo_id)
    assert (row["address"], row["lat"], row["lng"]) == (before["address"], before["lat"], before["lng"])
    assert row["memo"]["parcel"] == "3616/065"
    assert row["memo"]["site_history"] == before["memo"]["site_history"]


def test_the_web_page_has_the_same_round_limit() -> None:
    from pathlib import Path

    memo_ts = Path(__file__).resolve().parents[3] / "apps/web/src/lib/memo.ts"
    if not memo_ts.exists():
        pytest.skip("apps/web is not in this checkout")
    assert f"export const ANSWER_ROUND_LIMIT = {ANSWER_ROUND_LIMIT};" in memo_ts.read_text(encoding="utf-8")
