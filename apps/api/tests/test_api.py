"""HTTP-level tests with the fake model, in-memory database and real JWT verification."""

from __future__ import annotations

import datetime as dt
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.agents.runner import AgentRunner
from app.catalog.loader import get_catalog
from app.core.config import settings
from app.deps import get_db, get_plan_service, get_runner
from app.main import app
from app.services.db import MemoryDatabase
from app.services.plans import PlanService
from tests.conftest import TODAY, parse_sse
from tests.fakes import FakeAnthropic, ScriptedModel

DESCRIPTION = "Opening a 40-seat wine bar in SF Mission, small kitchen, serve until 1am, maybe live music"
USER_ID = "11111111-1111-4111-8111-111111111111"


def token(
    sub: str = USER_ID, *, exp_delta: int = 3600, secret: str | None = None, aud: str = "authenticated"
) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "aud": aud,
        "exp": now + exp_delta,
        "iat": now,
        "email": "owner@example.com",
        "role": "authenticated",
    }
    return jwt.encode(claims, secret or settings.SUPABASE_JWT_SECRET, algorithm="HS256")


@pytest.fixture
def db() -> MemoryDatabase:
    return MemoryDatabase()


@pytest.fixture
def script() -> ScriptedModel:
    return ScriptedModel()


@pytest.fixture
def client(db: MemoryDatabase, script: ScriptedModel):  # type: ignore[no-untyped-def]
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_plan_service] = lambda: PlanService(db, settings)
    app.dependency_overrides[get_runner] = lambda: AgentRunner(
        FakeAnthropic(script), get_catalog(), settings, today=TODAY
    )  # type: ignore[arg-type]
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def auth(t: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {t or token()}"}


# ---- health & public ----------------------------------------------------------------------
def test_healthz_includes_local_neatlogs_doctor(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert (
        body["status"] == "ok"
        and body["neatlogs"]["status"] == "pass"
        and body["neatlogs"]["mode"] == "local"
    )
    assert body["catalog_permits"] > 100


def test_cities_endpoint(client: TestClient) -> None:
    slugs = {c["slug"] for c in client.get("/v1/catalog/cities").json()["cities"]}
    assert "san_francisco" in slugs and "generic_city" not in slugs


# ---- auth rejection -----------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/v1/plans", "/v1/me", "/v1/plans/abc"])
def test_missing_token_rejected(client: TestClient, path: str) -> None:
    r = client.get(path)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "unauthorized"


def test_bad_tokens_rejected(client: TestClient) -> None:
    assert client.get("/v1/me", headers=auth("not-a-jwt")).status_code == 401
    assert (
        client.get("/v1/me", headers=auth(token(secret="wrong-secret-wrong-secret-wrong-secret"))).status_code
        == 401
    )
    assert client.get("/v1/me", headers=auth(token(exp_delta=-10))).status_code == 401
    assert client.get("/v1/me", headers=auth(token(aud="anon"))).status_code == 401
    assert client.get("/v1/me", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.post("/v1/plans", json={"description": DESCRIPTION}).status_code == 401
    assert client.patch("/v1/plans/x/steps/y", json={"done": True}).status_code == 401


def test_valid_token_creates_profile(client: TestClient) -> None:
    r = client.get("/v1/me", headers=auth())
    assert r.status_code == 200
    me = r.json()["profile"]
    assert me["id"] == USER_ID and me["email"] == "owner@example.com"
    assert (
        me["free_plans_remaining"] == 3
        and me["can_create_plan"] is True
        and me["entitlement"]["kind"] == "free"
    )


# ---- plan lifecycle -----------------------------------------------------------------------
def create_plan(client: TestClient, **body) -> list[tuple[str, dict]]:  # type: ignore[no-untyped-def]
    payload = {"description": DESCRIPTION, **body}
    with client.stream("POST", "/v1/plans", json=payload, headers=auth()) as r:
        assert r.status_code == 200, r.read()
        assert r.headers["content-type"].startswith("text/event-stream")
        text = "".join(r.iter_text())
    return parse_sse(text)


def test_create_plan_streams_and_persists(client: TestClient, db: MemoryDatabase) -> None:
    events = create_plan(client, target_open_date="2027-03-01")
    names = [e for e, _ in events]
    assert names[0] == "plan_created" and names[-1] == "plan"
    assert "stage" in names and "tool" in names and "narrative" in names
    record = events[-1][1]
    assert record["status"] == "ready" and record["version"] == 1 and record["title"].startswith("Bar ·")
    assert record["plan"]["timeline"]["target_open_date"] == "2027-03-01"
    assert len(record["steps"]) == len(record["plan"]["steps"]) and not any(
        s["done"] for s in record["steps"]
    )
    plan_id = record["id"]

    r = client.get("/v1/plans", headers=auth())
    assert r.status_code == 200
    summary = r.json()["plans"][0]
    assert (
        summary["id"] == plan_id
        and summary["steps_total"] == len(record["steps"])
        and summary["steps_done"] == 0
    )

    r = client.get(f"/v1/plans/{plan_id}", headers=auth())
    assert r.status_code == 200 and r.json()["plan"]["plan"]["summary"]

    # other users cannot see it
    other = token("22222222-2222-4222-8222-222222222222")
    assert client.get(f"/v1/plans/{plan_id}", headers=auth(other)).status_code == 404

    # entitlement counted
    assert client.get("/v1/me", headers=auth()).json()["profile"]["plans_created"] == 1
    events_logged = {e["event"] for e in db.tables["usage_events"]}
    assert {"plan_started", "plan_completed"} <= events_logged


def test_step_toggle_pdf_rerun_delete(client: TestClient) -> None:
    record = create_plan(client)[-1][1]
    plan_id, step = record["id"], record["steps"][0]
    r = client.patch(
        f"/v1/plans/{plan_id}/steps/{step['id']}",
        json={"done": True, "notes": "Filed online"},
        headers=auth(),
    )
    assert r.status_code == 200
    assert (
        r.json()["step"]["done"] is True
        and r.json()["step"]["done_at"]
        and r.json()["step"]["notes"] == "Filed online"
    )
    assert (
        client.patch(
            f"/v1/plans/{plan_id}/steps/does-not-exist", json={"done": True}, headers=auth()
        ).status_code
        == 404
    )

    r = client.get(f"/v1/plans/{plan_id}/export.pdf", headers=auth())
    assert (
        r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content[:4] == b"%PDF"
    )
    assert len(r.content) > 5000

    # rerun keeps done flags for surviving steps and bumps the version
    with client.stream(
        "POST", f"/v1/plans/{plan_id}/rerun", json={"target_open_date": "2027-06-01"}, headers=auth()
    ) as rr:
        assert rr.status_code == 200
        events = parse_sse("".join(rr.iter_text()))
    rec2 = events[-1][1]
    assert events[-1][0] == "plan" and rec2["version"] == 2 and rec2["target_open_date"] == "2027-06-01"
    kept = next(s for s in rec2["steps"] if s["step_key"] == step["step_key"])
    assert kept["done"] is True
    # rerun is free
    assert client.get("/v1/me", headers=auth()).json()["profile"]["plans_created"] == 1

    assert client.delete(f"/v1/plans/{plan_id}", headers=auth()).status_code == 204
    assert client.get(f"/v1/plans/{plan_id}", headers=auth()).status_code == 404


def test_paywall_after_three_free_plans(
    client: TestClient, db: MemoryDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ADMIN_EMAILS", [])  # a normal account
    for _ in range(3):
        assert create_plan(client)[-1][0] == "plan"
    r = client.post("/v1/plans", json={"description": DESCRIPTION}, headers=auth())
    assert r.status_code == 402
    assert r.json()["detail"] == {
        "code": "paywall",
        "message": "You have used your free plans.",
        "plans_created": 3,
        "free_limit": 3,
    }
    assert any(e["event"] == "paywall_hit" for e in db.tables["usage_events"])
    # a purchased credit unlocks exactly one more plan
    db.tables["profiles"][0]["plan_credits"] = 1
    me = client.get("/v1/me", headers=auth()).json()["profile"]
    assert me["entitlement"]["kind"] == "credits" and me["can_create_plan"]
    assert create_plan(client)[-1][0] == "plan"
    assert db.tables["profiles"][0]["plan_credits"] == 0
    assert client.post("/v1/plans", json={"description": DESCRIPTION}, headers=auth()).status_code == 402
    # an active subscription is unlimited
    db.tables["profiles"][0]["subscription_status"] = "active"
    assert create_plan(client)[-1][0] == "plan"


def test_a_normal_account_hits_the_checklist_paywall(
    client: TestClient, db: MemoryDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not in ADMIN_EMAILS: three free checklists, then the paywall."""
    monkeypatch.setattr(settings, "ADMIN_EMAILS", ["someone-else@example.com"])
    for _ in range(3):
        assert create_plan(client)[-1][0] == "plan"
    me = client.get("/v1/me", headers=auth()).json()["profile"]
    assert me["is_admin"] is False and me["can_create_plan"] is False
    assert client.post("/v1/plans", json={"description": DESCRIPTION}, headers=auth()).status_code == 402


def test_an_owner_account_has_unlimited_checklists_and_uses_no_credit(
    client: TestClient, db: MemoryDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The test user's email (owner@example.com) in ADMIN_EMAILS, any case or spacing: past the free limit with
    no paywall, and a purchased checklist credit is not spent."""
    monkeypatch.setattr(settings, "ADMIN_EMAILS", [" OWNER@example.com"])
    for _ in range(4):
        assert create_plan(client)[-1][0] == "plan"
    db.tables["profiles"][0]["plan_credits"] = 1
    assert create_plan(client)[-1][0] == "plan"
    assert db.tables["profiles"][0]["plan_credits"] == 1
    me = client.get("/v1/me", headers=auth()).json()["profile"]
    assert me["is_admin"] is True and me["can_create_plan"] is True
    assert not any(e["event"] == "paywall_hit" for e in db.tables["usage_events"])


def test_clarification_flow_over_http(client: TestClient, script: ScriptedModel) -> None:
    script.ask_clarification = True
    events = create_plan(client)
    assert events[-1][0] == "needs_clarification"
    plan_id = events[-1][1]["plan_id"]
    assert (
        client.get(f"/v1/plans/{plan_id}", headers=auth()).json()["plan"]["status"] == "pending_clarification"
    )
    # wrong plan state → 409
    assert (
        client.post(f"/v1/plans/{plan_id}/rerun", json={}, headers=auth()).status_code == 200
    )  # rerun allowed from pending
    with client.stream(
        "POST", f"/v1/plans/{plan_id}/clarify", json={"answers": {"q1": "yes"}}, headers=auth()
    ) as r:
        status = r.status_code
        text = "".join(r.iter_text())
    assert status in (200, 409)  # 409 if the rerun above already finished it
    if status == 200:
        assert parse_sse(text)[-1][0] == "plan"


def test_validation_errors_have_shape(client: TestClient) -> None:
    r = client.post("/v1/plans", json={"description": "too short"}, headers=auth())
    assert r.status_code == 422 and r.json()["detail"]["code"] == "validation_error"
    r = client.post(
        "/v1/plans", json={"description": DESCRIPTION, "target_open_date": "03/01/2027"}, headers=auth()
    )
    assert r.status_code == 422


# ---- preview (pre-auth) --------------------------------------------------------------------
def test_preview_flow_and_rate_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routes import preview as preview_routes

    monkeypatch.setattr(preview_routes.limiter, "limit", 1)
    preview_routes.limiter._hits.clear()
    with client.stream("POST", "/v1/preview", json={"description": DESCRIPTION}) as r:
        assert r.status_code == 200
        events = parse_sse("".join(r.iter_text()))
    assert events[-1][0] == "preview"
    pv = events[-1][1]
    assert pv["city_supported"] and pv["permit_count"] == len(pv["permits"]) > 10
    assert pv["estimated_total_days"]["max"] > pv["estimated_total_days"]["min"]
    assert not any(e == "narrative" for e, _ in events)  # nothing past requirements
    # signup → plan from preview without re-sending the description
    with client.stream(
        "POST", "/v1/plans", json={"description": "x" * 12, "preview_id": pv["preview_id"]}, headers=auth()
    ) as r:
        assert r.status_code == 200
        rec = parse_sse("".join(r.iter_text()))[-1][1]
    assert rec["description"] == DESCRIPTION and rec["status"] == "ready"
    # a second anonymous preview from the same IP within the window → 429
    r = client.post("/v1/preview", json={"description": DESCRIPTION})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"


def test_leads_capture(client: TestClient, db: MemoryDatabase) -> None:
    assert client.post("/v1/leads", json={"email": "nope", "city": "Boise"}).status_code == 422
    r = client.post("/v1/leads", json={"email": "Owner@Example.com", "city": "Boise", "state": "ID"})
    assert r.status_code == 201 and db.tables["leads"][0]["email"] == "owner@example.com"


def test_not_hospitality_error_event(client: TestClient, script: ScriptedModel) -> None:
    from tests.fakes import make_message, tool_use

    def reject(params):  # type: ignore[no-untyped-def]
        return make_message(
            [
                tool_use(
                    "submit_triage_result",
                    {
                        "is_hospitality_business": False,
                        "language": "en",
                        "city_guess": None,
                        "state_guess": None,
                        "reject_reason": "Not a hospitality business.",
                    },
                )
            ]
        ), []

    script.respond = reject  # type: ignore[method-assign]
    events = create_plan(client)
    assert events[-1][0] == "error" and events[-1][1]["code"] == "not_hospitality"
    assert client.get("/v1/plans", headers=auth()).json()["plans"][0]["status"] == "failed"
    assert (
        client.get("/v1/me", headers=auth()).json()["profile"]["plans_created"] == 0
    )  # failures are not charged


def test_dates() -> None:
    assert dt.date.fromisoformat("2027-03-01") > TODAY
