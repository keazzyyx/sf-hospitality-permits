"""HTTP tests for memos: teaser gating, unlock with credits / Pro, paywall, PDF, map, bulk, feedback, admin."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agents.memo_runner import MemoRunner
from app.catalog.loader import get_catalog
from app.core.config import settings
from app.deps import get_db, get_memo_runner, get_memo_service, get_plan_service, get_runner
from app.main import app
from app.memo.intake import IntakeAnswers
from app.models.profile import CODE_ONLY_FIELDS, MODEL_MAY_NOT_SET
from app.services.db import MemoryDatabase
from app.services.feedback import sign_feedback_token
from app.services.memos import MemoService
from app.services.plans import PlanService
from tests.conftest import TODAY, parse_sse
from tests.fakes import FakeAnthropic
from tests.memo_fakes import FakeGeocoder, MemoScript, seed_store
from tests.test_api import USER_ID, auth, token

# What the scripted intake model's profile (tests.fakes.BASE_PROFILE) claims, all stated, so the stated-facts check
# (app.memo.stated) keeps every fact the memo's rules read.
DESC = (
    "40-seat wine bar of 1,400 square feet, small kitchen, open until 1am, occasional live music, amplified"
)


@pytest.fixture
def db() -> MemoryDatabase:
    return MemoryDatabase()


@pytest.fixture
def client(db: MemoryDatabase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    import app.memo.context as ctx
    import app.routes.memos as memo_routes
    import app.routes.public_memo as public_routes
    import app.tools.precedent_tools as pt

    store = seed_store(tmp_path / "data")
    geocoder = FakeGeocoder()
    for mod in (ctx, pt, memo_routes, public_routes):
        if hasattr(mod, "get_store"):
            monkeypatch.setattr(mod, "get_store", lambda: store)
        if hasattr(mod, "get_geocoder"):
            monkeypatch.setattr(mod, "get_geocoder", lambda: geocoder)
    # a normal account by default; the `owner` fixture lists the test user's email in ADMIN_EMAILS
    monkeypatch.setattr(settings, "ADMIN_EMAILS", ["someone-else@example.com"])
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_plan_service] = lambda: PlanService(db, settings)
    app.dependency_overrides[get_memo_service] = lambda: MemoService(db, settings)
    app.dependency_overrides[get_runner] = lambda: None
    app.dependency_overrides[get_memo_runner] = lambda: MemoRunner(
        FakeAnthropic(MemoScript()), get_catalog(), settings, store, geocoder, today=TODAY
    )  # type: ignore[arg-type]
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test user (owner@example.com) is an owner account: listed in ADMIN_EMAILS."""
    monkeypatch.setattr(settings, "ADMIN_EMAILS", ["Owner@Example.com "])


def create_memo(client: TestClient, **body):  # type: ignore[no-untyped-def]
    payload = {"address": "995 Valencia St", "description": DESC, **body}
    with client.stream("POST", "/v1/memos", json=payload, headers=auth()) as r:
        status = r.status_code
        text = "".join(r.iter_text())
    return status, (parse_sse(text) if status == 200 else text)


def test_memo_is_teaser_until_unlocked(client: TestClient, db: MemoryDatabase) -> None:
    status, events = create_memo(client)
    assert status == 200 and events[0][0] == "memo_created" and events[-1][0] == "memo"
    rec = events[-1][1]
    assert rec["status"] == "ready" and rec["access"] == "teaser" and rec["memo"] is None
    assert rec["legacy_format"] is False
    # the teaser's status and line are the computed ones: no model wrote them. The description gives no story
    # and the table on file for NCT-2 gives first-story controls, so no story is assumed: the zoning row is
    # insufficient information naming the story (the user's decision of 2026-11-12)
    assert rec["teaser"] == {
        "overall_status": "further_review",
        # first, what changes the plans (pathway rule 9): the Mission district's rule asks for a Conditional Use
        "overall_line": (
            "A Conditional Use Authorization is needed (use control of a special use district). "
            "Of the 5 approvals this concept needs: 1 further review (entertainment permit), 3 insufficient "
            "information (zoning and use, alcohol licence, building permit and change of use), 1 allowed "
            "(health permit)."
        ),
        "comparable_count": 8,
        "approvals_count": 5,
        "blockers_count": 0,
    }
    # the stream carries the four stages and no prose
    stages = [d["stage"] for e, d in events if e == "stage" and d["status"] == "started"]
    assert stages == ["intake", "records", "precedent", "finalize"]
    assert not any(e == "narrative" for e, _ in events)
    memo_id = rec["id"]
    summary = client.get("/v1/memos", headers=auth()).json()["memos"][0]
    assert summary["overall_status"] == "further_review" and summary["legacy_format"] is False
    assert summary["comparable_count"] == 8 and "verdict" not in summary
    assert client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]["memo"] is None
    # paid surfaces are gated
    assert client.get(f"/v1/memos/{memo_id}/export.pdf", headers=auth()).status_code == 402
    assert client.get(f"/v1/memos/{memo_id}/map.geojson", headers=auth()).status_code == 402
    assert client.post(f"/v1/memos/{memo_id}/unlock", headers=auth()).status_code == 402
    me = client.get("/v1/me", headers=auth()).json()["profile"]
    assert me["free_teasers_remaining"] == 1 and me["can_unlock_memo"] is False and me["is_admin"] is False
    # a credit unlocks, is consumed, and the full memo + PDF + map become available
    db.tables["profiles"][0]["memo_credits"] = 1
    r = client.post(f"/v1/memos/{memo_id}/unlock", headers=auth())
    assert r.status_code == 200 and r.json()["memo"]["access"] == "full"
    full = r.json()["memo"]["memo"]
    assert full["format_version"] == 3 and full["overall"]["status"] == "further_review"
    assert [row["area"] for row in full["approvals"]][:2] == ["zoning_use", "alcohol"]
    # the full memo carries the pathway and each row's rule lines, as the rules set them
    assert (full["pathway"]["use"], full["pathway"]["permission"]) == ("bar", "not_covered")
    assert full["approvals"][0]["status"] == "insufficient_information"
    assert full["approvals"][0]["basis"][-1]["rule_id"] == "zoning.status"
    assert full["overall"]["line"] == rec["teaser"]["overall_line"]
    assert "verification" not in full and all(row["facts"] for row in full["approvals"])
    assert "narrative" not in full and "verdict" not in full and "blocking_issues" not in full
    assert db.tables["profiles"][0]["memo_credits"] == 0
    pdf = client.get(f"/v1/memos/{memo_id}/export.pdf", headers=auth())
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 4000
    geo = client.get(f"/v1/memos/{memo_id}/map.geojson", headers=auth()).json()
    kinds = {f["properties"]["kind"] for f in geo["features"]}
    assert kinds == {"subject", "comparable", "overlay"}
    subject = next(f["properties"] for f in geo["features"] if f["properties"]["kind"] == "subject")
    assert subject["overall_status"] == "further_review" and "verdict" not in subject
    completed = next(e for e in db.tables["usage_events"] if e["event"] == "memo_completed")
    assert completed["properties"]["overall_status"] == "further_review"
    assert "verdict" not in completed["properties"]
    assert client.get("/v1/memos", headers=auth()).json()["memos"][0]["access"] == "full"
    events_logged = {e["event"] for e in db.tables["usage_events"]}
    assert {
        "memo_started",
        "memo_completed",
        "memo_teaser_viewed",
        "memo_unlocked",
        "memo_pdf_exported",
    } <= events_logged


def test_teaser_limit_then_paywall_then_pro(client: TestClient, db: MemoryDatabase) -> None:
    assert create_memo(client)[0] == 200
    assert create_memo(client)[0] == 200
    r = client.post("/v1/memos", json={"address": "995 Valencia St", "description": DESC}, headers=auth())
    assert r.status_code == 402 and r.json()["detail"]["code"] == "paywall_memo"
    assert any(e["event"] == "memo_paywall_hit" for e in db.tables["usage_events"])
    db.tables["profiles"][0]["pro_status"] = "active"
    status, events = create_memo(client)
    assert status == 200 and events[-1][1]["access"] == "full"  # Pro memos are unlocked immediately
    assert db.tables["profiles"][0]["teasers_generated"] == 2


def test_bulk_requires_pro_and_runs_in_background(client: TestClient, db: MemoryDatabase) -> None:
    csv_body = b"address,description\n995 Valencia St," + DESC.encode() + b"\n,too short\n"
    files = {"file": ("sites.csv", csv_body, "text/csv")}
    assert client.post("/v1/memos/bulk", files=files, headers=auth()).status_code == 403
    db.tables.setdefault("profiles", [])
    client.get("/v1/me", headers=auth())
    db.tables["profiles"][0]["pro_status"] = "active"
    r = client.post("/v1/memos/bulk", files=files, headers=auth())
    assert r.status_code == 202, r.text
    body = r.json()
    assert len(body["memo_ids"]) == 1 and body["skipped"] == [
        {"row": 3, "reason": "address or description missing / too short"}
    ]
    status = client.get(f"/v1/memos/bulk/{body['batch_id']}", headers=auth()).json()
    assert (
        status["memos"][0]["status"] == "ready" and status["memos"][0]["access"] == "full"
    )  # background task ran inside TestClient
    bad = client.post("/v1/memos/bulk", files={"file": ("x.csv", b"nope\n1\n", "text/csv")}, headers=auth())
    assert bad.status_code == 422


def test_feedback_token_round_trip(client: TestClient, db: MemoryDatabase) -> None:
    _status, events = create_memo(client)
    memo_id = events[-1][1]["id"]
    bad = client.get("/v1/feedback/not-a-token")
    assert bad.status_code == 400
    tok = sign_feedback_token(memo_id, settings)
    ctx = client.get(f"/v1/feedback/{tok}").json()
    assert ctx["memo_id"] == memo_id and ctx["already_answered"] is False and ctx["address"].startswith("995")
    r = client.post(
        f"/v1/feedback/{tok}", json={"outcome": "approved_with_conditions", "notes": "1am close imposed"}
    )
    assert r.status_code == 201 and r.json()["feedback_id"]
    assert client.get(f"/v1/feedback/{tok}").json()["already_answered"] is True
    dup = client.post(f"/v1/feedback/{tok}", json={"outcome": "denied"})
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "already_answered"
    expired = sign_feedback_token(memo_id, settings, issued_at=int(time.time()) - 400 * 24 * 3600)
    assert client.get(f"/v1/feedback/{expired}").status_code == 410
    forged = tok[:-4] + "zzzz"
    assert client.get(f"/v1/feedback/{forged}").status_code == 400


def test_admin_overview_gated(client: TestClient, monkeypatch: pytest.MonkeyPatch, owner: None) -> None:
    create_memo(client)
    r = client.get("/v1/admin/overview", headers=auth())
    assert r.status_code == 200
    body = r.json()
    assert (
        body["ingestion"]["counts"]["applications"] == 14
        and body["memos"]["total"] == 1
        and body["users"]["total"] == 1
    )
    assert body["feedback"]["total"] == 0 and body["feedback"]["response_rate_pct"] is None
    assert body["memos"]["by_overall_status"] == {"further_review": 1} and "by_verdict" not in body["memos"]
    assert body["memos"]["legacy_format"] == 0


def test_admin_rejects_non_admin_email(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_EMAILS", ["someone-else@example.com"])
    assert client.get("/v1/admin/overview", headers=auth()).status_code == 403


def test_geocode_suggestions(client: TestClient) -> None:
    r = client.get("/v1/geocode", params={"q": "995 valen"})
    assert r.status_code == 200 and r.json()["suggestions"][0]["normalized_address"] == "995 VALENCIA ST"
    assert client.get("/v1/geocode", params={"q": "zz"}).status_code == 422
    assert client.get("/v1/geocode", params={"q": "1 nowhere"}).json()["suggestions"] == []


def test_memo_owner_scoping(client: TestClient) -> None:
    _, events = create_memo(client)
    memo_id = events[-1][1]["id"]
    assert (
        client.get(
            f"/v1/memos/{memo_id}", headers=auth(token("33333333-3333-4333-8333-333333333333"))
        ).status_code
        == 404
    )
    assert client.delete(f"/v1/memos/{memo_id}", headers=auth()).status_code == 204
    assert client.get(f"/v1/memos/{memo_id}", headers=auth()).status_code == 404


# ---- memos stored before report format 2 ------------------------------------------------------------
LEGACY_MEMO = {  # the shape stored before 2026-11: no format_version, a verdict, a narrative
    "address": "995 Valencia St, San Francisco, CA 94110",
    "lat": 37.7577,
    "lng": -122.4213,
    "parcel": "3616/065",
    "concept_summary": "A 40-seat wine bar at 995 Valencia St.",
    "verdict": {"label": "conditional", "reason": "Bars need CUA in NCT-3.", "citations": ["zoning:NCT-3"]},
    "blocking_issues": [],
    "narrative": "A wine bar at 995 Valencia St is a conditional proposition.",
    "comparable_cases": [],
    "citations": [],
}
LEGACY_TEASER = {
    "verdict": "conditional",
    "verdict_reason": "Bars need CUA in NCT-3.",
    "comparable_count": 6,
    "blocking_count": 2,
    "base_rate_pct": 75.0,
}


def _legacy_row(db: MemoryDatabase, *, access: str, memo_id: str) -> None:
    db.tables.setdefault("memos", []).append(
        {
            "id": memo_id,
            "user_id": USER_ID,
            "address": "995 Valencia St",
            "lat": 37.7577,
            "lng": -122.4213,
            "description": DESC,
            "profile": None,
            "status": "ready",
            "access": access,
            "teaser": dict(LEGACY_TEASER),
            "memo": dict(LEGACY_MEMO),
            "clarification": None,
            "batch_id": None,
            "error": None,
            "unlocked_at": "2026-10-23T00:00:00+00:00" if access == "full" else None,
            "feedback_email_sent_at": None,
            "created_at": "2026-10-22T00:00:00+00:00",
        }
    )


def test_legacy_memo_is_served_as_legacy_format_without_an_exception(
    client: TestClient, db: MemoryDatabase, owner: None
) -> None:
    _legacy_row(db, access="full", memo_id="aaaaaaaa-0000-4000-8000-000000000001")
    _legacy_row(db, access="teaser", memo_id="aaaaaaaa-0000-4000-8000-000000000002")
    for memo_id, access in (
        ("aaaaaaaa-0000-4000-8000-000000000001", "full"),
        ("aaaaaaaa-0000-4000-8000-000000000002", "teaser"),
    ):
        r = client.get(f"/v1/memos/{memo_id}", headers=auth())
        assert r.status_code == 200, r.text
        rec = r.json()["memo"]
        assert rec["legacy_format"] is True and rec["memo"] is None and rec["teaser"] is None
        assert rec["status"] == "ready" and rec["access"] == access
    # list summaries: same flag, nothing derived from the old verdict
    memos = client.get("/v1/memos", headers=auth()).json()["memos"]
    assert len(memos) == 2
    assert all(m["legacy_format"] is True and m["overall_status"] is None for m in memos)
    assert all(m["comparable_count"] is None for m in memos)
    # PDF export and the map refuse a legacy memo with 409 legacy_format (402 while still locked)
    full_id, teaser_id = "aaaaaaaa-0000-4000-8000-000000000001", "aaaaaaaa-0000-4000-8000-000000000002"
    for path in ("export.pdf", "map.geojson"):
        r = client.get(f"/v1/memos/{full_id}/{path}", headers=auth())
        assert r.status_code == 409 and r.json()["detail"]["code"] == "legacy_format", r.text
        assert client.get(f"/v1/memos/{teaser_id}/{path}", headers=auth()).status_code == 402
    # unlocking a legacy memo never spends a credit: there is nothing to show for it
    client.get("/v1/me", headers=auth())
    db.tables["profiles"][0]["memo_credits"] = 1
    r = client.post(f"/v1/memos/{teaser_id}/unlock", headers=auth())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "legacy_format"
    assert db.tables["profiles"][0]["memo_credits"] == 1
    # an already unlocked legacy memo answers unlock idempotently, still withheld
    r = client.post(f"/v1/memos/{full_id}/unlock", headers=auth())
    assert r.status_code == 200 and r.json()["memo"]["legacy_format"] is True
    # admin stats count the new statuses only
    stats = client.get("/v1/admin/overview", headers=auth()).json()["memos"]
    assert stats["total"] == 2 and stats["by_overall_status"] == {} and stats["legacy_format"] == 2
    assert client.delete(f"/v1/memos/{full_id}", headers=auth()).status_code == 204


def test_legacy_and_current_memos_list_side_by_side(client: TestClient, db: MemoryDatabase) -> None:
    _legacy_row(db, access="full", memo_id="aaaaaaaa-0000-4000-8000-000000000003")
    status, events = create_memo(client)
    assert status == 200 and events[-1][1]["legacy_format"] is False
    by_legacy = {m["legacy_format"]: m for m in client.get("/v1/memos", headers=auth()).json()["memos"]}
    assert by_legacy[True]["overall_status"] is None
    assert by_legacy[False]["overall_status"] == "further_review"


def test_stored_memo_that_no_longer_validates_is_withheld_not_raised(
    client: TestClient, db: MemoryDatabase
) -> None:
    """A row marked format 2 whose JSON does not fit the schema must not turn into a 500."""
    _status, events = create_memo(client)
    memo_id = events[-1][1]["id"]
    row = next(r for r in db.tables["memos"] if r["id"] == memo_id)
    del row["memo"]["overall"]
    # still locked: the record, the list and unlock all treat it as a legacy memo, and no credit is spent
    rec = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert rec["legacy_format"] is True and rec["memo"] is None and rec["teaser"] is None
    summary = client.get("/v1/memos", headers=auth()).json()["memos"][0]
    assert summary["legacy_format"] is True
    assert summary["overall_status"] is None and summary["comparable_count"] is None
    db.tables["profiles"][0]["memo_credits"] = 1
    r = client.post(f"/v1/memos/{memo_id}/unlock", headers=auth())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "legacy_format", r.text
    assert db.tables["profiles"][0]["memo_credits"] == 1 and row["access"] == "teaser"
    # already unlocked: withheld on the record and refused by the paid surfaces
    row["access"] = "full"
    rec = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert rec["legacy_format"] is True and rec["memo"] is None and rec["teaser"] is None
    r = client.get(f"/v1/memos/{memo_id}/export.pdf", headers=auth())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "legacy_format"


def test_memo_stored_before_site_history_is_served_as_legacy(client: TestClient, db: MemoryDatabase) -> None:
    """A format-2 memo written before the site history and record kinds existed lacks three required fields.
    It must be withheld as a legacy memo, never a 500, and re-running the address gives a current one."""
    _status, events = create_memo(client)
    memo_id = events[-1][1]["id"]
    row = next(r for r in db.tables["memos"] if r["id"] == memo_id)
    assert row["memo"]["format_version"] == 3 and "site_history" in row["memo"]
    # the stored JSON as it was before this change
    del row["memo"]["site_history"]
    del row["memo"]["base_rate"]["excluded_not_use_decision"]
    for comparable in row["memo"]["comparable_cases"]:
        del comparable["record_kind"]
        del comparable["record_kind_label"]
    r = client.get(f"/v1/memos/{memo_id}", headers=auth())
    assert r.status_code == 200, r.text
    rec = r.json()["memo"]
    assert rec["legacy_format"] is True and rec["memo"] is None and rec["teaser"] is None
    assert rec["status"] == "ready"
    listed = client.get("/v1/memos", headers=auth())
    assert listed.status_code == 200
    summary = listed.json()["memos"][0]
    assert summary["legacy_format"] is True and summary["overall_status"] is None
    # unlocked: still withheld, and the paid surfaces answer 409 legacy_format rather than failing
    row["access"] = "full"
    rec = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert rec["legacy_format"] is True and rec["memo"] is None
    for path in ("export.pdf", "map.geojson"):
        r = client.get(f"/v1/memos/{memo_id}/{path}", headers=auth())
        assert r.status_code == 409 and r.json()["detail"]["code"] == "legacy_format", r.text
    # each missing field alone is enough to withhold the memo
    _status, events = create_memo(client)
    other = next(r for r in db.tables["memos"] if r["id"] == events[-1][1]["id"])
    assert client.get(f"/v1/memos/{other['id']}", headers=auth()).json()["memo"]["legacy_format"] is False
    del other["memo"]["site_history"]
    assert client.get(f"/v1/memos/{other['id']}", headers=auth()).json()["memo"]["legacy_format"] is True


def test_memo_stored_before_the_rules_set_the_statuses_is_withheld(
    client: TestClient, db: MemoryDatabase
) -> None:
    """A memo written when a model chose the statuses has no `pathway`, no rule lines on its
    rows, and fields the report no longer has (`original_status`, `rows_reset`). It is not shown with statuses
    no rule set: it is withheld like any earlier format, and the address can be run again."""
    _status, events = create_memo(client)
    memo_id = events[-1][1]["id"]
    row = next(r for r in db.tables["memos"] if r["id"] == memo_id)
    row["access"] = "full"
    current = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert current["legacy_format"] is False and current["memo"]["pathway"]["use"] == "bar"
    assert all(a["basis"] for a in current["memo"]["approvals"])
    stored = row["memo"]  # back to the shape it was stored in before this change
    del stored["pathway"]
    for approval in stored["approvals"]:
        del approval["basis"]
        approval["original_status"] = None
    stored["verification"] = {"rows_reset": 0}
    rec = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert rec["legacy_format"] is True and rec["memo"] is None and rec["teaser"] is None
    r = client.get(f"/v1/memos/{memo_id}/export.pdf", headers=auth())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "legacy_format"
    # the missing pathway alone is enough
    _status, events = create_memo(client)
    other = next(r for r in db.tables["memos"] if r["id"] == events[-1][1]["id"])
    del other["memo"]["pathway"]
    assert client.get(f"/v1/memos/{other['id']}", headers=auth()).json()["memo"]["legacy_format"] is True


def test_admin_stats_count_a_memo_that_no_longer_validates_as_legacy(
    client: TestClient, db: MemoryDatabase, owner: None
) -> None:
    """The admin counts must agree with what the API serves: a format-2 row without `site_history` is served as
    a legacy memo, so it is counted as one and its old status is not tallied."""
    create_memo(client)
    _status, events = create_memo(client)
    stats = client.get("/v1/admin/overview", headers=auth()).json()["memos"]
    assert stats["by_overall_status"] == {"further_review": 2} and stats["legacy_format"] == 0
    row = next(r for r in db.tables["memos"] if r["id"] == events[-1][1]["id"])
    assert row["memo"]["format_version"] == 3
    del row["memo"]["site_history"]
    assert client.get(f"/v1/memos/{row['id']}", headers=auth()).json()["memo"]["legacy_format"] is True
    stats = client.get("/v1/admin/overview", headers=auth()).json()["memos"]
    assert stats["total"] == 2 and stats["legacy_format"] == 1
    assert stats["by_overall_status"] == {"further_review": 1}
    # the same for each of the other two fields added with the site history
    other = next(r for r in db.tables["memos"] if r["id"] != row["id"])
    del other["memo"]["base_rate"]["excluded_not_use_decision"]
    stats = client.get("/v1/admin/overview", headers=auth()).json()["memos"]
    assert stats["legacy_format"] == 2 and stats["by_overall_status"] == {}


def test_user_id_fixture_sanity() -> None:
    assert USER_ID.count("-") == 4


# ---- the optional intake questions (app.memo.intake) --------------------------------------------------------
def test_the_create_request_takes_the_answers_and_the_rules_read_them(
    client: TestClient, db: MemoryDatabase
) -> None:
    body = {"part_of_chain": False, "floor_area_sqft": 1800, "liquor_licence": "transfer_from_another_owner"}
    status, events = create_memo(client, intake=body)
    assert status == 200 and events[-1][0] == "memo", events[-1]
    rec = events[-1][1]
    # the record shows all four answers, a skipped one as null; the row stores the answers given
    # every question is listed, a skipped one null
    assert rec["intake"] == {**dict.fromkeys(IntakeAnswers.model_fields), **body}
    row = db.tables["memos"][0]
    assert row["intake"] == body
    profile = row["profile"]
    assert (profile["part_of_chain"], profile["formula_retail"], profile["square_feet"]) == (
        False,
        False,
        1800,
    )
    assert (profile["alcohol_transaction"], profile["serves_alcohol"]) == ("person_to_person_transfer", True)
    assert client.get(f"/v1/memos/{rec['id']}", headers=auth()).json()["memo"]["intake"] == rec["intake"]


@pytest.mark.parametrize(
    ("answer", "transaction", "serves", "said_so"),
    [
        # decision 2: "already hold a licence at this address" is its own answer
        ("already_held", "licence_already_held", True, False),
        # "No alcohol" is no alcohol only, whatever the description said (the scripted one is a wine bar), and
        # the pathway's first line says the answer won
        ("none", None, False, True),
    ],
)
def test_the_licence_answers_already_held_and_no_alcohol(
    client: TestClient, db: MemoryDatabase, answer: str, transaction: str | None, serves: bool, said_so: bool
) -> None:
    status, events = create_memo(client, intake={"liquor_licence": answer})
    assert status == 200 and events[-1][0] == "memo", events[-1]
    rec = events[-1][1]
    assert rec["intake"]["liquor_licence"] == answer
    profile = db.tables["memos"][0]["profile"]
    assert (profile["alcohol_transaction"], profile["serves_alcohol"]) == (transaction, serves)
    if not serves:
        assert profile["alcohol_type"] == "none"
    stored = db.tables["memos"][0]["memo"]  # the teaser hides the memo; the stored one holds the pathway
    lines = [line["rule_id"] for line in stored["pathway"]["lines"]]
    assert ("intake.no_alcohol" in lines) is said_so


def test_a_create_request_without_answers_stores_none(
    client: TestClient,
    db: MemoryDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FREE_TEASER_LIMIT", 10)
    for body in ({}, {"intake": None}, {"intake": {}}, {"intake": {"part_of_chain": None}}):
        status, events = create_memo(client, **body)
        assert status == 200 and events[-1][1]["intake"] is None
    assert all("intake" not in row for row in db.tables["memos"])


@pytest.mark.parametrize(
    "bad",
    [
        {"other_locations": 4},
        {"part_of_chain": True, "other_locations": -1},
        {"floor_area_sqft": 0},
        {"floor_area_sqft": 2_000_000},
        {"liquor_licence": "maybe"},
        {"seats": 40},
    ],
)
def test_the_create_request_refuses_answers_outside_the_allowed_values(
    client: TestClient,
    bad: dict[str, Any],
) -> None:
    status, _ = create_memo(client, intake=bad)
    assert status == 422


def test_a_clarification_run_applies_the_stored_answers_again(client: TestClient, db: MemoryDatabase) -> None:
    status, events = create_memo(client, intake={"floor_area_sqft": 2222, "liquor_licence": "new"})
    assert status == 200
    memo_id = events[-1][1]["id"]
    row = db.tables["memos"][0]
    # put the memo back to waiting for an answer, as a run that asked a question leaves it
    question = {
        "id": "q1",
        "question": "Will the bar serve spirits as well as beer and wine?",
        "kind": "boolean",
        "options": None,
        "maps_to": "serves_alcohol",
        "required": True,
    }
    row.update(
        status="pending_clarification",
        clarification={"questions": [question], "answers": {}},
        profile={**row["profile"], "square_feet": None, "alcohol_transaction": None},
    )
    with client.stream(
        "POST", f"/v1/memos/{memo_id}/clarify", json={"answers": {"q1": True}}, headers=auth()
    ) as r:
        assert r.status_code == 200
        "".join(r.iter_text())
    row = db.tables["memos"][0]
    assert row["status"] == "ready"
    assert (row["profile"]["square_feet"], row["profile"]["alcohol_transaction"]) == (2222, "new_licence")
    assert row["intake"] == {"floor_area_sqft": 2222, "liquor_licence": "new"}


def test_a_stored_row_with_answers_that_no_longer_validate_reads_as_none() -> None:
    assert MemoService.intake_of({"id": "m1", "intake": {"floor_area_sqft": -5}}) == IntakeAnswers()
    assert MemoService.intake_of({"id": "m1"}) == IntakeAnswers()
    assert MemoService.intake_of({"id": "m1", "intake": {"liquor_licence": "new"}}).liquor_licence == "new"


def test_a_stored_row_keeps_the_answers_this_version_knows() -> None:
    """Review #14: after a rollback, a row the newer version wrote holds keys this version does not know. They are
    dropped and the known answers kept, so a re-run or a clarification does not lose them; a known key whose value
    no longer validates is dropped on its own."""
    newer = {"liquor_licence": "new", "floor_area_sqft": 1800, "a_later_question": ["first"]}
    assert MemoService.intake_of({"id": "m1", "intake": newer}) == IntakeAnswers(
        liquor_licence="new", floor_area_sqft=1800
    )
    one_bad = {"liquor_licence": "new", "floor_area_sqft": -5}
    assert MemoService.intake_of({"id": "m1", "intake": one_bad}) == IntakeAnswers(liquor_licence="new")
    # two answers that contradict each other: nothing is guessed, no answer is kept
    contradict = {"liquor_licence": "none", "alcohol_served": "beer_wine"}
    assert MemoService.intake_of({"id": "m1", "intake": contradict}) == IntakeAnswers()


def test_a_normal_account_hits_the_paywall_after_its_free_teasers(
    client: TestClient, db: MemoryDatabase
) -> None:
    """A normal account (not in ADMIN_EMAILS, no Pro, no credit): two free teasers, then the paywall; a teaser
    cannot be unlocked without a credit, and bulk upload stays a Pro feature."""
    me = client.get("/v1/me", headers=auth()).json()["profile"]
    assert me["is_admin"] is False and me["can_create_memo"] is True and me["can_unlock_memo"] is False
    first = create_memo(client)
    assert first[0] == 200 and first[1][-1][1]["access"] == "teaser"
    assert create_memo(client)[0] == 200
    r = client.post("/v1/memos", json={"address": "995 Valencia St", "description": DESC}, headers=auth())
    assert r.status_code == 402 and r.json()["detail"]["code"] == "paywall_memo"
    memo_id = first[1][-1][1]["id"]
    assert client.post(f"/v1/memos/{memo_id}/unlock", headers=auth()).status_code == 402
    assert client.get(f"/v1/memos/{memo_id}/export.pdf", headers=auth()).status_code == 402
    files = {
        "file": ("sites.csv", b"address,description\n995 Valencia St," + DESC.encode() + b"\n", "text/csv")
    }
    assert client.post("/v1/memos/bulk", files=files, headers=auth()).status_code == 403
    me = client.get("/v1/me", headers=auth()).json()["profile"]
    assert me["can_create_memo"] is False and me["free_teasers_remaining"] == 0


def test_an_owner_account_has_unlimited_memos_with_no_paywall_and_no_credit_used(
    client: TestClient, db: MemoryDatabase, owner: None
) -> None:
    """An owner account (its email in ADMIN_EMAILS, any case or spacing): every memo is created unlocked, past
    the free-teaser limit, with no credit used and no teaser counted; PDF export and bulk upload work."""
    me = client.get("/v1/me", headers=auth()).json()["profile"]
    assert me["is_admin"] is True and me["can_create_memo"] is True and me["can_unlock_memo"] is True
    ids = []
    for _ in range(4):  # twice the free-teaser limit
        status, events = create_memo(client)
        assert status == 200
        rec = events[-1][1]
        assert rec["access"] == "full" and rec["memo"] is not None
        ids.append(rec["id"])
    profile = db.tables["profiles"][0]
    assert int(profile.get("teasers_generated") or 0) == 0 and int(profile.get("memo_credits") or 0) == 0
    assert not any(e["event"] == "memo_paywall_hit" for e in db.tables["usage_events"])
    pdf = client.get(f"/v1/memos/{ids[0]}/export.pdf", headers=auth())
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    # a teaser made before the account was listed unlocks without a credit
    db.tables["memos"][0]["access"] = "teaser"
    r = client.post(f"/v1/memos/{db.tables['memos'][0]['id']}/unlock", headers=auth())
    assert r.status_code == 200 and r.json()["memo"]["access"] == "full"
    assert int(db.tables["profiles"][0].get("memo_credits") or 0) == 0
    unlocked = [e for e in db.tables["usage_events"] if e["event"] == "memo_unlocked"]
    assert unlocked[-1]["properties"]["via"] == "admin"
    files = {
        "file": ("sites.csv", b"address,description\n995 Valencia St," + DESC.encode() + b"\n", "text/csv")
    }
    assert client.post("/v1/memos/bulk", files=files, headers=auth()).status_code == 202


# ---- re-running a legacy memo (`rerun_of`) -------------------------------------------------------------
LEGACY_ID = "aaaaaaaa-0000-4000-8000-0000000000a1"
OTHER_USER = "33333333-3333-4333-8333-333333333333"


def _rerun(client: TestClient, memo_id: str, headers: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    """A re-run request as the web sends it, here with an address and description that differ from the legacy
    memo's: with `rerun_of` the API uses the legacy memo's own."""
    payload = {
        "address": "1 Somewhere Else",
        "description": "a different concept, sent with the re-run",
        "rerun_of": memo_id,
    }
    with client.stream("POST", "/v1/memos", json=payload, headers=headers or auth()) as r:
        status = r.status_code
        text = "".join(r.iter_text())
    return status, (parse_sse(text) if status == 200 else text)


def _use_up_free_teasers(client: TestClient, db: MemoryDatabase) -> None:
    for _ in range(settings.FREE_TEASER_LIMIT):
        assert create_memo(client)[0] == 200
    profile = db.tables["profiles"][0]
    assert profile["teasers_generated"] == settings.FREE_TEASER_LIMIT and not profile.get("memo_credits")


def _free_rerun_events(db: MemoryDatabase) -> list[dict[str, Any]]:
    return [e for e in db.tables.get("usage_events", []) if e["event"] == "memo_rerun_free"]


def _legacy_record(client: TestClient) -> dict[str, Any]:
    rec: dict[str, Any] = client.get(f"/v1/memos/{LEGACY_ID}", headers=auth()).json()["memo"]
    return rec


def test_the_first_rerun_of_an_unlocked_legacy_memo_is_free(client: TestClient, db: MemoryDatabase) -> None:
    """A legacy memo the user unlocked re-runs once for free: the new memo is created unlocked, no credit is used,
    no free teaser is counted, and it passes the create paywall with no previews and no credit left. It uses the
    legacy memo's address and description, whatever the request sends with `rerun_of`."""
    _use_up_free_teasers(client, db)
    _legacy_row(db, access="full", memo_id=LEGACY_ID)
    assert _legacy_record(client)["rerun_free"] is True
    # a plain create is stopped at the paywall: no previews and no credit left
    r = client.post("/v1/memos", json={"address": "995 Valencia St", "description": DESC}, headers=auth())
    assert r.status_code == 402 and r.json()["detail"]["code"] == "paywall_memo"

    status, events = _rerun(client, LEGACY_ID)
    assert status == 200, events
    rec = events[-1][1]
    assert rec["access"] == "full" and rec["memo"] is not None and rec["legacy_format"] is False
    assert rec["unlocked_at"] is not None and rec["description"] == DESC
    assert rec["memo"]["format_version"] == 3 and rec["rerun_free"] is False
    profile = db.tables["profiles"][0]
    assert profile["teasers_generated"] == settings.FREE_TEASER_LIMIT and not profile.get("memo_credits")
    (marker,) = _free_rerun_events(db)
    assert marker["properties"] == {"legacy_memo_id": LEGACY_ID, "memo_id": rec["id"], "attempt": 0}
    # the claim is the new memo's own id, derived from the legacy memo and the attempt number
    assert rec["id"] == MemoService.free_rerun_memo_id(LEGACY_ID, 0)
    new_rec = client.get(f"/v1/memos/{rec['id']}", headers=auth()).json()["memo"]
    assert new_rec["rerun_of"] == LEGACY_ID
    started = [e for e in db.tables["usage_events"] if e["event"] == "memo_started"][-1]
    assert started["properties"] == {"memo_id": rec["id"], "rerun_of": LEGACY_ID, "free_rerun": True}
    # the new memo's paid surfaces open; the legacy memo no longer offers a free re-run
    assert client.get(f"/v1/memos/{rec['id']}/export.pdf", headers=auth()).status_code == 200
    assert _legacy_record(client)["rerun_free"] is False

    # the second re-run of the same legacy memo is charged like any new memo: the paywall, with nothing left
    status, text = _rerun(client, LEGACY_ID)
    assert status == 402 and "paywall_memo" in text
    # ... and a free teaser, counted, when one is left
    db.tables["profiles"][0]["teasers_generated"] = settings.FREE_TEASER_LIMIT - 1
    status, events = _rerun(client, LEGACY_ID)
    assert status == 200 and events[-1][1]["access"] == "teaser" and events[-1][1]["memo"] is None
    assert db.tables["profiles"][0]["teasers_generated"] == settings.FREE_TEASER_LIMIT
    assert len(_free_rerun_events(db)) == 1


def _memo_row(db: MemoryDatabase, memo_id: str) -> dict[str, Any]:
    return next(r for r in db.tables["memos"] if r["id"] == memo_id)


def test_a_free_rerun_whose_memo_failed_does_not_use_it(client: TestClient, db: MemoryDatabase) -> None:
    """A failed memo is never charged, so its free re-run is given back, and the failed memo's own page names the
    legacy memo (`rerun_of`) so its Re-run link retries for free, with no previews or credits left."""
    _use_up_free_teasers(client, db)
    _legacy_row(db, access="full", memo_id=LEGACY_ID)
    status, events = _rerun(client, LEGACY_ID)
    assert status == 200 and events[-1][1]["access"] == "full"
    first_id = events[-1][1]["id"]
    assert _legacy_record(client)["rerun_free"] is False
    row = _memo_row(db, first_id)
    row.update(status="failed", memo=None, teaser=None, access="teaser", unlocked_at=None)
    assert _legacy_record(client)["rerun_free"] is True
    failed = client.get(f"/v1/memos/{first_id}", headers=auth()).json()["memo"]
    assert failed["legacy_format"] is False and failed["rerun_of"] == LEGACY_ID

    # the retry the failed page's Re-run link sends is the next free attempt
    status, events = _rerun(client, failed["rerun_of"])
    assert status == 200, events
    retry = events[-1][1]
    assert retry["access"] == "full" and retry["id"] == MemoService.free_rerun_memo_id(LEGACY_ID, 1)
    assert [e["properties"]["attempt"] for e in _free_rerun_events(db)] == [0, 1]
    assert db.tables["profiles"][0]["teasers_generated"] == settings.FREE_TEASER_LIMIT
    # a ready free re-run deleted afterwards stays used
    assert client.delete(f"/v1/memos/{retry['id']}", headers=auth()).status_code == 204
    assert _legacy_record(client)["rerun_free"] is False
    status, text = _rerun(client, LEGACY_ID)
    assert status == 402 and "paywall_memo" in text


def test_a_free_rerun_deleted_before_it_was_ready_gives_it_back(
    client: TestClient, db: MemoryDatabase
) -> None:
    _legacy_row(db, access="full", memo_id=LEGACY_ID)
    _, events = _rerun(client, LEGACY_ID)
    new_id = events[-1][1]["id"]
    _memo_row(db, new_id).update(status="failed")
    assert client.delete(f"/v1/memos/{new_id}", headers=auth()).status_code == 204
    (grant,) = _free_rerun_events(db)
    assert grant["properties"]["released_at"]
    assert _legacy_record(client)["rerun_free"] is True


@pytest.mark.parametrize("stuck", ["generating", "pending_clarification"])
def test_an_abandoned_free_rerun_gives_it_back_after_a_while(
    client: TestClient, db: MemoryDatabase, stuck: str
) -> None:
    """A free re-run whose memo never finishes gives the free re-run back once it has not changed for a while.
    A run cut off mid-way (the page was closed, the server restarted) counts as failed after GENERATING_TIMEOUT,
    and a failed memo gives its free re-run back; a clarification question left unanswered does so after
    FREE_RERUN_RELEASE_AFTER. Before that, it is still running and the free re-run is in use."""
    import datetime as dt

    from app.services.memos import FREE_RERUN_RELEASE_AFTER, GENERATING_TIMEOUT

    wait = GENERATING_TIMEOUT if stuck == "generating" else FREE_RERUN_RELEASE_AFTER

    _use_up_free_teasers(client, db)
    _legacy_row(db, access="full", memo_id=LEGACY_ID)
    _, events = _rerun(client, LEGACY_ID)
    first_id = events[-1][1]["id"]
    row = _memo_row(db, first_id)
    recent = dt.datetime.now(dt.UTC) - wait + dt.timedelta(minutes=5)
    row.update(status=stuck, memo=None, teaser=None, access="teaser", unlocked_at=None)
    row["updated_at"] = recent.isoformat()
    assert _legacy_record(client)["rerun_free"] is False
    status, text = _rerun(client, LEGACY_ID)
    assert status == 402 and "paywall_memo" in text

    row["updated_at"] = (recent - dt.timedelta(minutes=10)).isoformat()
    assert _legacy_record(client)["rerun_free"] is True
    status, events = _rerun(client, LEGACY_ID)
    assert status == 200 and events[-1][1]["access"] == "full"
    assert events[-1][1]["id"] == MemoService.free_rerun_memo_id(LEGACY_ID, 1)


async def test_an_abandoned_attempt_that_finishes_after_a_later_one_is_not_free(db: MemoryDatabase) -> None:
    from app.core.auth import AuthUser

    svc = MemoService(db, settings)
    user = AuthUser(id=USER_ID, email="someone@example.com", is_anonymous=False, claims={})
    _legacy_row(db, access="full", memo_id=LEGACY_ID)
    legacy = _memo_row(db, LEGACY_ID)
    first = await svc.create_free_rerun(user, legacy, 0, intake=IntakeAnswers())
    assert first is not None and await svc.is_free_rerun(user, first["id"])
    _memo_row(db, first["id"])["status"] = "failed"
    second = await svc.create_free_rerun(user, legacy, 1, intake=IntakeAnswers())
    assert second is not None
    assert not await svc.is_free_rerun(user, first["id"]) and await svc.is_free_rerun(user, second["id"])
    # an attempt someone else already took is not made twice
    assert await svc.create_free_rerun(user, legacy, 1, intake=IntakeAnswers()) is None
    assert len(_free_rerun_events(db)) == 2


async def test_two_reruns_sent_at_once_make_one_free_memo(client: TestClient, db: MemoryDatabase) -> None:
    """Both requests find the free re-run unused before either records it (each database read takes a little
    while, as over HTTP). The new memo's id is the claim, so only one insert goes through: one memo is free and
    the other request is charged like any new memo (here: the paywall, with no previews or credits left)."""
    import asyncio

    import httpx

    _use_up_free_teasers(client, db)
    _legacy_row(db, access="full", memo_id=LEGACY_ID)
    real_select = db.select

    async def slow_select(table: str, **kw: Any) -> list[dict[str, Any]]:
        out = await real_select(table, **kw)
        await asyncio.sleep(0.01)
        return out

    db.select = slow_select  # type: ignore[method-assign]
    payload = {"address": "995 Valencia St", "description": DESC, "rerun_of": LEGACY_ID}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as ac:
        r1, r2 = await asyncio.gather(
            ac.post("/v1/memos", json=payload, headers=auth()),
            ac.post("/v1/memos", json=payload, headers=auth()),
        )
    db.select = real_select  # type: ignore[method-assign]
    assert sorted([r1.status_code, r2.status_code]) == [200, 402]
    ok = r1 if r1.status_code == 200 else r2
    assert parse_sse(ok.text)[-1][1]["access"] == "full"
    assert len(_free_rerun_events(db)) == 1
    assert [m["id"] for m in db.tables["memos"] if m["id"] != LEGACY_ID and m["access"] == "full"] == [
        MemoService.free_rerun_memo_id(LEGACY_ID, 0)
    ]
    assert db.tables["profiles"][0]["teasers_generated"] == settings.FREE_TEASER_LIMIT


def test_a_rerun_is_the_same_concept(client: TestClient, db: MemoryDatabase) -> None:
    """With `rerun_of`, profile overrides are refused (422): a re-run, free or not, is the legacy memo's concept.
    Intake answers sent with it are used: they answer questions an earlier-format memo never asked."""
    _legacy_row(db, access="full", memo_id=LEGACY_ID)
    r = client.post(
        "/v1/memos",
        json={
            "address": "x St",
            "description": DESC,
            "rerun_of": LEGACY_ID,
            "profile_overrides": {"dancing": True},
        },
        headers=auth(),
    )
    assert r.status_code == 422 and "profile_overrides" in r.text
    assert [m["id"] for m in db.tables["memos"]] == [LEGACY_ID] and not _free_rerun_events(db)
    payload = {
        "address": "x St",
        "description": DESC,
        "rerun_of": LEGACY_ID,
        "intake": {"floor_area_sqft": 1400},
    }
    with client.stream("POST", "/v1/memos", json=payload, headers=auth()) as resp:
        assert resp.status_code == 200
        rec = parse_sse("".join(resp.iter_text()))[-1][1]
    assert rec["access"] == "full" and rec["intake"]["floor_area_sqft"] == 1400


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("intake_answered", ["stories", "occupants_under_50"]),
        ("outdoor_alcohol_answer_over_description", True),
        ("no_alcohol_answer_over_description", True),
        ("intake_cleared", {"seats": 40}),
    ],
)
def test_an_override_cannot_set_a_field_only_code_sets(
    client: TestClient, db: MemoryDatabase, field: str, value: Any
) -> None:
    """Review of 2026-11-15, round 2: a new memo's `profile_overrides` (no `rerun_of`) is refused (422) when it names
    a field only code sets: code's record of where a fact came from would otherwise be forged, and a line would say
    "You answered ..." for a fact no answer gave. Nothing is created."""
    assert field in CODE_ONLY_FIELDS and field in MODEL_MAY_NOT_SET
    status, text = create_memo(client, profile_overrides={field: value})
    assert status == 422 and field in text
    assert db.tables.get("memos", []) == []
    # an override of a fact is still accepted
    status, events = create_memo(client, profile_overrides={"dancing": False})
    assert status == 200 and events[-1][0] == "memo"


def test_another_users_legacy_memo_cannot_be_rerun(client: TestClient, db: MemoryDatabase) -> None:
    _legacy_row(db, access="full", memo_id=LEGACY_ID)
    memos_before = len(db.tables["memos"])
    status, text = _rerun(client, LEGACY_ID, headers=auth(token(OTHER_USER)))
    assert status == 404 and "not_found" in text
    assert len(db.tables["memos"]) == memos_before and not _free_rerun_events(db)
    # the owner's free re-run is still there
    assert _legacy_record(client)["rerun_free"] is True


def test_a_legacy_memo_never_unlocked_reruns_like_any_new_memo(
    client: TestClient, db: MemoryDatabase
) -> None:
    _legacy_row(db, access="teaser", memo_id=LEGACY_ID)
    assert _legacy_record(client)["rerun_free"] is False
    status, events = _rerun(client, LEGACY_ID)
    assert status == 200
    rec = events[-1][1]
    assert rec["access"] == "teaser" and rec["memo"] is None and rec["description"] == DESC
    assert db.tables["profiles"][0]["teasers_generated"] == 1 and not _free_rerun_events(db)
    started = [e for e in db.tables["usage_events"] if e["event"] == "memo_started"][-1]
    assert started["properties"]["free_rerun"] is False
    # with no previews left it meets the paywall
    db.tables["profiles"][0]["teasers_generated"] = settings.FREE_TEASER_LIMIT
    status, text = _rerun(client, LEGACY_ID)
    assert status == 402 and "paywall_memo" in text


def test_a_current_memo_cannot_be_given_as_rerun_of(client: TestClient, db: MemoryDatabase) -> None:
    _, events = create_memo(client)
    current_id = events[-1][1]["id"]
    memos_before = len(db.tables["memos"])
    status, text = _rerun(client, current_id)
    assert status == 409 and "rerun_not_legacy" in text
    assert len(db.tables["memos"]) == memos_before and not _free_rerun_events(db)
    # not a memo id at all
    r = client.post(
        "/v1/memos", json={"address": "995 Valencia St", "description": DESC, "rerun_of": "x"}, headers=auth()
    )
    assert r.status_code == 422


def test_a_pro_rerun_of_a_legacy_memo_is_unlocked_and_keeps_the_free_rerun(
    client: TestClient, db: MemoryDatabase
) -> None:
    client.get("/v1/me", headers=auth())
    db.tables["profiles"][0]["pro_status"] = "active"
    _legacy_row(db, access="full", memo_id=LEGACY_ID)
    status, events = _rerun(client, LEGACY_ID)
    assert status == 200 and events[-1][1]["access"] == "full"
    assert not _free_rerun_events(db) and int(db.tables["profiles"][0].get("teasers_generated") or 0) == 0


def test_the_free_rerun_record_must_be_written_or_the_new_memo_goes(
    client: TestClient, db: MemoryDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the free re-run's record cannot be written, the new memo row is removed and the request fails, so no
    memo is made free without the record that stops a second free re-run."""
    from app.core.errors import ApiError

    _legacy_row(db, access="full", memo_id=LEGACY_ID)
    real_insert = db.insert

    async def failing_insert(table: str, row: dict[str, Any]) -> dict[str, Any]:
        if table == "usage_events" and row.get("event") == "memo_rerun_free":
            raise ApiError(502, "database_error", "down")
        return await real_insert(table, row)

    monkeypatch.setattr(db, "insert", failing_insert)
    r = client.post(
        "/v1/memos",
        json={"address": "995 Valencia St", "description": DESC, "rerun_of": LEGACY_ID},
        headers=auth(),
    )
    assert r.status_code == 502
    assert [m["id"] for m in db.tables["memos"]] == [LEGACY_ID]


async def test_supabase_reports_a_duplicate_key_as_its_own_error() -> None:
    """PostgREST answers an insert that breaks a unique key with 409 and code 23505: the free re-run's claim reads
    that as "taken". Any other refused write stays a plain database error."""
    import httpx

    from app.core.errors import ApiError
    from app.services.db import DuplicateKeyError, SupabaseDatabase

    def reply(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/memos"):
            return httpx.Response(409, json={"code": "23505", "message": "duplicate key value"})
        return httpx.Response(409, json={"code": "23503", "message": "foreign key violation"})

    sdb = object.__new__(SupabaseDatabase)
    sdb._client = httpx.AsyncClient(base_url="http://db/rest/v1", transport=httpx.MockTransport(reply))
    with pytest.raises(DuplicateKeyError) as dup:
        await sdb.insert("memos", {"id": "x"})
    assert dup.value.status == 502 and dup.value.code == "database_error"
    with pytest.raises(ApiError) as other:
        await sdb.insert("usage_events", {})
    assert not isinstance(other.value, DuplicateKeyError)
    await sdb.aclose()
    # the in-memory twin refuses a second row with the same id too
    mem = MemoryDatabase()
    await mem.insert("memos", {"id": "x"})
    with pytest.raises(DuplicateKeyError):
        await mem.insert("memos", {"id": "x"})


# ---- a run cut off mid-way counts as failed (GENERATING_TIMEOUT) -----------------------------------------------


def _ago(minutes: float) -> str:
    import datetime as dt

    return (dt.datetime.now(dt.UTC) - dt.timedelta(minutes=minutes)).isoformat()


def _stuck_memo(client: TestClient, db: MemoryDatabase, *, minutes: float, **extra: Any) -> str:
    """A memo row left "generating" by a run that was cut off `minutes` ago (nothing charged, nothing stored)."""
    client.get("/v1/me", headers=auth())  # the profile row
    row = db.tables.setdefault("memos", [])
    memo = {
        "id": f"00000000-0000-4000-8000-{len(row):012d}",
        "user_id": USER_ID,
        "address": "995 Valencia St",
        "lat": None,
        "lng": None,
        "description": DESC,
        "profile": None,
        "status": "generating",
        "access": "teaser",
        "teaser": None,
        "memo": None,
        "clarification": None,
        "batch_id": None,
        "error": None,
        "unlocked_at": None,
        "created_at": _ago(minutes),
        "updated_at": _ago(minutes),
        **extra,
    }
    row.append(memo)
    return str(memo["id"])


def test_a_memo_still_generating_after_the_timeout_reads_as_failed_and_costs_nothing(
    client: TestClient, db: MemoryDatabase
) -> None:
    """A run cut off mid-way (the page that started it was left, or the API restarted) leaves its row
    "generating". Until GENERATING_TIMEOUT it reads as generating; from then on it reads as failed, with a message
    that says nothing was charged. The stored row is not rewritten, and no preview or credit is used."""
    from app.services.memos import GENERATING_TIMEOUT, STALLED_MESSAGE

    limit = GENERATING_TIMEOUT.total_seconds() / 60
    fresh = _stuck_memo(client, db, minutes=limit - 1)
    stale = _stuck_memo(client, db, minutes=limit + 1)
    db.tables["profiles"][0].update(memo_credits=2, teasers_generated=1)

    rec = client.get(f"/v1/memos/{fresh}", headers=auth()).json()["memo"]
    assert rec["status"] == "generating" and rec["error"] is None
    rec = client.get(f"/v1/memos/{stale}", headers=auth()).json()["memo"]
    assert rec["status"] == "failed" and rec["error"] == STALLED_MESSAGE
    assert rec["memo"] is None and rec["teaser"] is None and rec["access"] == "teaser"
    assert _memo_row(db, stale)["status"] == "generating"  # only what the API reports changes
    # it cannot be unlocked (no credit is taken) and it can be deleted
    r = client.post(f"/v1/memos/{stale}/unlock", headers=auth())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_ready"
    profile = db.tables["profiles"][0]
    assert profile["memo_credits"] == 2 and profile["teasers_generated"] == 1
    assert client.delete(f"/v1/memos/{stale}", headers=auth()).status_code == 204
    assert db.tables["profiles"][0]["memo_credits"] == 2


def test_the_timeout_counts_from_the_last_change_and_only_for_generating(
    client: TestClient, db: MemoryDatabase
) -> None:
    """The clock runs from the row's last change (a memo created long ago that was set running again a minute ago
    is running), and only a "generating" row times out: a clarification question waiting for an answer, a ready
    memo and a failed one read as stored."""
    from app.services.memos import GENERATING_TIMEOUT

    limit = GENERATING_TIMEOUT.total_seconds() / 60
    restarted = _stuck_memo(client, db, minutes=limit * 3, updated_at=_ago(1))
    waiting = _stuck_memo(client, db, minutes=limit * 3, status="pending_clarification")
    failed = _stuck_memo(client, db, minutes=limit * 3, status="failed", error="Plan generation failed.")
    no_stamp = _stuck_memo(client, db, minutes=limit * 3, updated_at=None)
    got = {
        m: client.get(f"/v1/memos/{m}", headers=auth()).json()["memo"]
        for m in (restarted, waiting, failed, no_stamp)
    }
    assert got[restarted]["status"] == "generating"
    assert got[waiting]["status"] == "pending_clarification"
    assert got[failed]["status"] == "failed" and got[failed]["error"] == "Plan generation failed."
    assert got[no_stamp]["status"] == "failed"  # falls back to created_at


def test_the_memo_list_and_a_batch_show_a_stalled_memo_as_failed(
    client: TestClient, db: MemoryDatabase
) -> None:
    from app.services.memos import GENERATING_TIMEOUT

    limit = GENERATING_TIMEOUT.total_seconds() / 60
    batch = "11111111-1111-4111-8111-111111111111"
    fresh = _stuck_memo(client, db, minutes=1, batch_id=batch)
    stale = _stuck_memo(client, db, minutes=limit + 5, batch_id=batch)
    listed = {m["id"]: m["status"] for m in client.get("/v1/memos", headers=auth()).json()["memos"]}
    assert listed[fresh] == "generating" and listed[stale] == "failed"
    in_batch = {
        m["id"]: m["status"] for m in client.get(f"/v1/memos/bulk/{batch}", headers=auth()).json()["memos"]
    }
    assert in_batch == {fresh: "generating", stale: "failed"}


def test_retrying_a_stalled_memo_makes_a_new_one_charged_only_like_any_new_memo(
    client: TestClient, db: MemoryDatabase
) -> None:
    """The Re-run link of a failed memo (not a free re-run) starts a new memo with the same address and
    description. The stalled one cost nothing; the new one counts a free preview when it is ready, as any new memo
    does, and uses no credit until it is unlocked."""
    from app.services.memos import GENERATING_TIMEOUT

    stale = _stuck_memo(client, db, minutes=GENERATING_TIMEOUT.total_seconds() / 60 + 1)
    db.tables["profiles"][0].update(memo_credits=1, teasers_generated=0)
    failed = client.get(f"/v1/memos/{stale}", headers=auth()).json()["memo"]
    assert failed["status"] == "failed" and failed["rerun_of"] is None  # a plain retry, not a free re-run

    status, events = create_memo(client, address=failed["address"], description=failed["description"])
    assert status == 200, events
    retry = events[-1][1]
    assert events[-1][0] == "memo", events[-1]
    assert retry["status"] == "ready" and retry["id"] != stale and retry["access"] == "teaser"
    profile = db.tables["profiles"][0]
    assert profile["teasers_generated"] == 1 and profile["memo_credits"] == 1


def test_a_stalled_free_rerun_reads_as_failed_and_its_retry_is_free(
    client: TestClient, db: MemoryDatabase
) -> None:
    """A free re-run cut off mid-way reads as failed once GENERATING_TIMEOUT has passed; like any failed free
    re-run it names its legacy memo, gives the free re-run back, and its retry is the next free attempt, with no
    preview counted and no credit used."""
    from app.services.memos import GENERATING_TIMEOUT

    _use_up_free_teasers(client, db)
    _legacy_row(db, access="full", memo_id=LEGACY_ID)
    _, events = _rerun(client, LEGACY_ID)
    first_id = events[-1][1]["id"]
    row = _memo_row(db, first_id)
    row.update(status="generating", memo=None, teaser=None, access="teaser", unlocked_at=None)
    row["updated_at"] = _ago(GENERATING_TIMEOUT.total_seconds() / 60 + 1)
    failed = client.get(f"/v1/memos/{first_id}", headers=auth()).json()["memo"]
    assert failed["status"] == "failed" and failed["rerun_of"] == LEGACY_ID
    assert _legacy_record(client)["rerun_free"] is True
    status, events = _rerun(client, failed["rerun_of"])
    assert status == 200 and events[-1][1]["access"] == "full"
    assert events[-1][1]["id"] == MemoService.free_rerun_memo_id(LEGACY_ID, 1)
    profile = db.tables["profiles"][0]
    assert profile["teasers_generated"] == settings.FREE_TEASER_LIMIT and not profile.get("memo_credits")


async def test_a_bulk_upload_refreshes_its_queued_rows_before_each_memo(
    db: MemoryDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bulk upload runs its rows one after another, so the last of 25 can wait longer than GENERATING_TIMEOUT.
    Before each memo it refreshes the rows of its batch still waiting, so a queued row never reads as stalled; rows
    of other batches and finished rows are left alone."""
    import app.routes.memos as memo_routes
    from app.core.auth import AuthUser
    from app.services.memos import GENERATING_TIMEOUT, effective_status

    old = _ago(GENERATING_TIMEOUT.total_seconds() / 60 + 10)
    batch, other = "22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333"
    base = {"user_id": USER_ID, "address": "x", "description": DESC, "created_at": old, "updated_at": old}
    db.tables["memos"] = [
        {**base, "id": "q1", "batch_id": batch, "status": "generating"},
        {**base, "id": "q2", "batch_id": batch, "status": "generating"},
        {**base, "id": "done", "batch_id": batch, "status": "ready"},
        {**base, "id": "elsewhere", "batch_id": other, "status": "generating"},
    ]
    seen: list[dict[str, str]] = []

    async def fake_generate(*, memo_id: str, **_: Any):  # type: ignore[no-untyped-def]
        seen.append({r["id"]: effective_status(r) for r in db.tables["memos"]})
        _memo_row(db, memo_id)["status"] = "ready"
        yield "event: memo\n\n"

    monkeypatch.setattr(memo_routes, "generate_memo", fake_generate)
    svc = MemoService(db, settings)
    user = AuthUser(id=USER_ID, email="someone@example.com", is_anonymous=False, claims={})
    await memo_routes._run_batch(["q1", "q2"], [None, None], user, svc, None)  # type: ignore[list-item, arg-type]
    assert seen[0]["q1"] == "generating" and seen[0]["q2"] == "generating"
    assert seen[1]["q2"] == "generating"
    assert _memo_row(db, "done")["updated_at"] == old
    assert _memo_row(db, "elsewhere")["updated_at"] == old
    assert effective_status(_memo_row(db, "elsewhere")) == "failed"


# ---- a run outlives its stream ---------------------------------------------------------------------------------


def _wait_for(pred, seconds: float = 10.0) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.02)
    return False


def _gated_events(monkeypatch: pytest.MonkeyPatch, *, fail: bool = False):  # type: ignore[no-untyped-def]
    """Hold every memo run after its first stage event until the returned gate is set (then go on, or raise)."""
    import asyncio
    import threading

    import app.routes.memos as memo_routes

    real = memo_routes._memo_events
    gate = threading.Event()

    async def held(runner, inp):  # type: ignore[no-untyped-def]
        first = True
        async for ev in real(runner, inp):
            yield ev
            if first and ev.type == "stage":
                first = False
                # the gate is set from the test's thread, so wait for it off the event loop
                await asyncio.to_thread(gate.wait, 10)
                if fail:
                    raise RuntimeError("the store went away")

    monkeypatch.setattr(memo_routes, "_memo_events", held)
    return gate


def _start_and_leave(client: TestClient) -> str:
    """Start a memo and close the stream after its first stage event, as a page that is left mid-run does."""
    payload = {"address": "995 Valencia St", "description": DESC}
    memo_id = None
    with client.stream("POST", "/v1/memos", json=payload, headers=auth()) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data:") and "memo_id" in line and memo_id is None:
                import json

                memo_id = json.loads(line[5:])["memo_id"]
            if line.startswith("event: stage"):
                break
    assert memo_id
    return str(memo_id)


def test_a_memo_run_goes_on_when_its_page_is_closed_mid_run(
    client: TestClient, db: MemoryDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Leaving the page mid-run no longer stops the run: the memo is saved when the run ends and the page that comes
    back reads it ready, charged exactly once like a memo whose page stayed open (one free preview, no credit)."""
    gate = _gated_events(monkeypatch)
    memo_id = _start_and_leave(client)
    rec = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert rec["status"] == "generating"
    gate.set()
    assert _wait_for(lambda: _memo_row(db, memo_id)["status"] == "ready"), _memo_row(db, memo_id)["status"]
    rec = client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]
    assert rec["status"] == "ready" and rec["access"] == "teaser" and rec["teaser"] is not None
    assert db.tables["profiles"][0]["teasers_generated"] == 1
    assert not db.tables["profiles"][0].get("memo_credits")
    completed = [e for e in db.tables["usage_events"] if e["event"] == "memo_completed"]
    assert [e["properties"]["memo_id"] for e in completed] == [memo_id]


def test_a_memo_run_that_crashes_after_its_page_is_closed_is_marked_failed(
    client: TestClient, db: MemoryDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _gated_events(monkeypatch, fail=True)
    memo_id = _start_and_leave(client)
    gate.set()
    assert _wait_for(lambda: _memo_row(db, memo_id)["status"] == "failed")
    assert _memo_row(db, memo_id)["error"] == "Generation failed. Please try again in a minute."
    assert not db.tables["profiles"][0].get("teasers_generated")


def test_a_memo_run_that_crashes_while_its_page_listens_says_so_and_marks_it_failed(
    client: TestClient, db: MemoryDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _gated_events(monkeypatch, fail=True)
    gate.set()
    status, events = create_memo(client)
    assert status == 200
    assert events[-1][0] == "error" and events[-1][1]["code"] == "generation_failed"
    memo_id = events[0][1]["memo_id"]
    assert _memo_row(db, memo_id)["status"] == "failed"


def test_a_crash_after_the_memo_was_saved_leaves_it_ready(
    client: TestClient, db: MemoryDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mark_failed_if_running: a run that raises after its memo was saved (here, recording `memo_completed`) does
    not turn a ready, charged memo into a failed one."""
    real = PlanService.record_event

    async def flaky(self, user_id, event, props=None):  # type: ignore[no-untyped-def]
        if event == "memo_completed":
            raise RuntimeError("analytics down")
        return await real(self, user_id, event, props)

    monkeypatch.setattr(PlanService, "record_event", flaky)
    status, events = create_memo(client)
    assert status == 200
    memo_id = events[0][1]["memo_id"]
    assert _memo_row(db, memo_id)["status"] == "ready"
    assert db.tables["profiles"][0]["teasers_generated"] == 1
    # the page listening gets the saved memo, not "Generation failed ... nothing was charged"
    assert events[-1][0] == "memo" and events[-1][1]["id"] == memo_id and events[-1][1]["status"] == "ready"


def test_a_memo_deleted_while_its_run_goes_on_is_not_saved_or_charged(
    client: TestClient, db: MemoryDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deleting a memo whose page was left mid-run stops its run; whatever the run gets to, nothing is saved, no
    preview is counted and no row comes back."""
    gate = _gated_events(monkeypatch)
    memo_id = _start_and_leave(client)
    assert client.delete(f"/v1/memos/{memo_id}", headers=auth()).status_code == 204
    gate.set()
    time.sleep(0.5)
    assert not any(r["id"] == memo_id for r in db.tables["memos"])
    assert not db.tables["profiles"][0].get("teasers_generated")


async def test_save_result_saves_nothing_for_a_memo_that_is_gone_or_already_ended(db: MemoryDatabase) -> None:
    """The run itself also checks: a memo deleted (or already ended) before its run saves is not written back and
    not charged, even if the run was not stopped."""
    from app.core.auth import AuthUser

    svc = MemoService(db, settings)
    user = AuthUser(id=USER_ID, email="someone@example.com", is_anonymous=False, claims={})
    db.tables["profiles"] = [{"id": USER_ID, "email": "someone@example.com", "teasers_generated": 0}]
    db.tables["memos"] = [{"id": "ended", "user_id": USER_ID, "status": "failed", "created_at": _ago(1)}]
    args: Any = (None, None, None)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(MemoService, "is_free_rerun", lambda *_a, **_k: _false())
        assert await svc.save_result(user, "gone", *args, lat=0, lng=0, address="x") is None
        assert await svc.save_result(user, "ended", *args, lat=0, lng=0, address="x") is None
    assert _memo_row(db, "ended")["status"] == "failed"
    assert db.tables["profiles"][0]["teasers_generated"] == 0


async def _false() -> bool:
    return False


def test_a_run_that_finishes_after_its_memo_was_reported_stalled_is_saved_without_a_charge(
    client: TestClient, db: MemoryDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run slower than GENERATING_TIMEOUT: the page said it stopped and nothing was charged, so when it does
    finish the memo is saved (the user gets it) but no preview is counted."""
    from app.services.memos import GENERATING_TIMEOUT

    gate = _gated_events(monkeypatch)
    memo_id = _start_and_leave(client)
    _memo_row(db, memo_id)["updated_at"] = _ago(GENERATING_TIMEOUT.total_seconds() / 60 + 1)
    _memo_row(db, memo_id)["created_at"] = _ago(GENERATING_TIMEOUT.total_seconds() / 60 + 1)
    assert client.get(f"/v1/memos/{memo_id}", headers=auth()).json()["memo"]["status"] == "failed"
    gate.set()
    assert _wait_for(lambda: _memo_row(db, memo_id)["status"] == "ready")
    assert not db.tables["profiles"][0].get("teasers_generated")


def test_previews_still_running_count_against_the_free_limit(
    client: TestClient, db: MemoryDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run left behind by a closed page still finishes and counts its preview, so a second memo started while it
    runs, with no preview left besides it, meets the paywall instead of going past the limit. With a credit, or once
    the run has ended, memos start as usual."""
    gate = _gated_events(monkeypatch)
    client.get("/v1/me", headers=auth())
    db.tables["profiles"][0]["teasers_generated"] = settings.FREE_TEASER_LIMIT - 1
    memo_id = _start_and_leave(client)
    r = client.post("/v1/memos", json={"address": "995 Valencia St", "description": DESC}, headers=auth())
    assert r.status_code == 402 and r.json()["detail"]["code"] == "paywall_memo"
    gate.set()
    assert _wait_for(lambda: _memo_row(db, memo_id)["status"] == "ready")
    assert db.tables["profiles"][0]["teasers_generated"] == settings.FREE_TEASER_LIMIT  # counted once
    # a credit lets memos start whatever is running
    db.tables["profiles"][0]["memo_credits"] = 1
    status, _events = create_memo(client)
    assert status == 200


def test_a_stalled_or_bulk_row_does_not_hold_a_free_preview(client: TestClient, db: MemoryDatabase) -> None:
    from app.services.memos import GENERATING_TIMEOUT

    client.get("/v1/me", headers=auth())
    db.tables["profiles"][0]["teasers_generated"] = settings.FREE_TEASER_LIMIT - 1
    _stuck_memo(client, db, minutes=GENERATING_TIMEOUT.total_seconds() / 60 + 1)
    _stuck_memo(client, db, minutes=1, batch_id="44444444-4444-4444-8444-444444444444")
    status, _events = create_memo(client)
    assert status == 200
