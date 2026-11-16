"""Geocode suggestions, outcome feedback and the admin overview."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.core.auth import AuthUser, current_user
from app.core.config import settings
from app.core.errors import ApiError
from app.core.ratelimit import SlidingWindowLimiter, client_ip
from app.deps import get_memo_service
from app.memo.context import get_geocoder, get_store
from app.services.feedback import record_feedback, verify_feedback_token
from app.services.memos import MemoService

router = APIRouter(tags=["memo-public"])
geocode_limiter = SlidingWindowLimiter(settings.GEOCODE_RATE_LIMIT_PER_MINUTE, window_seconds=60)
feedback_limiter = SlidingWindowLimiter(30, window_seconds=3600)


class Suggestion(BaseModel):
    address: str
    normalized_address: str
    lat: float
    lng: float
    parcel: str | None
    zip_code: str | None
    confidence: float


@router.get("/v1/geocode")
async def geocode(
    request: Request, q: str = Query(min_length=3, max_length=120), limit: int = Query(default=8, ge=1, le=15)
) -> dict[str, list[Suggestion]]:
    geocode_limiter.check(client_ip(request))
    results = await get_geocoder().suggest(q, limit=limit)
    return {
        "suggestions": [
            Suggestion(
                address=r.address,
                normalized_address=r.normalized_address,
                lat=r.lat,
                lng=r.lng,
                parcel=r.parcel,
                zip_code=r.zip_code,
                confidence=r.confidence,
            )
            for r in results
        ]
    }


class FeedbackBody(BaseModel):
    outcome: Literal["approved", "approved_with_conditions", "denied", "withdrew", "still_pending"]
    notes: str | None = Field(default=None, max_length=2000)


@router.get("/v1/feedback/{token}")
async def feedback_context(
    token: str, request: Request, svc: MemoService = Depends(get_memo_service)
) -> dict[str, Any]:
    feedback_limiter.check(client_ip(request))
    memo_id = verify_feedback_token(token, settings)
    row = await svc.memo_by_id(memo_id)
    if row is None:
        raise ApiError(404, "not_found", "Memo not found")
    prof = row.get("profile") or {}
    answered = await _already_answered(svc, memo_id)
    return {
        "memo_id": memo_id,
        "address": row["address"],
        "concept_type": prof.get("business_type", "business"),
        "already_answered": answered,
    }


@router.post("/v1/feedback/{token}", status_code=201)
async def submit_feedback(
    token: str, body: FeedbackBody, request: Request, svc: MemoService = Depends(get_memo_service)
) -> dict[str, Any]:
    feedback_limiter.check(client_ip(request))
    memo_id = verify_feedback_token(token, settings)
    row = await svc.memo_by_id(memo_id)
    if row is None:
        raise ApiError(404, "not_found", "Memo not found")
    if await _already_answered(svc, memo_id):
        raise ApiError(409, "already_answered", "The outcome for this memo was already recorded.")
    saved = await record_feedback(get_store(), memo_row=row, outcome=body.outcome, notes=body.notes)
    await svc.plans.record_event(
        str(row["user_id"]),
        "feedback_submitted",
        {"memo_id": memo_id, "outcome": body.outcome, "feedback_id": saved.id},
    )
    return {"ok": True, "feedback_id": saved.id}


async def _already_answered(svc: MemoService, memo_id: str) -> bool:
    existing = await svc.db.select("usage_events", filters={"event": "feedback_submitted"})
    return any((e.get("properties") or {}).get("memo_id") == memo_id for e in existing)


async def require_admin(user: AuthUser = Depends(current_user)) -> AuthUser:
    # the same test as the owner accounts' entitlement (PlanService.is_admin): case and spaces ignored
    admins = {e.strip().lower() for e in settings.ADMIN_EMAILS if e.strip()}
    if not user.email or user.email.strip().lower() not in admins:
        raise ApiError(403, "forbidden", "Admins only")
    return user


@router.get("/v1/admin/overview")
async def admin_overview(
    _: AuthUser = Depends(require_admin), svc: MemoService = Depends(get_memo_service)
) -> dict[str, Any]:
    store = get_store()
    ingestion = await store.status()
    fb = await store.feedback_stats()
    memos = await svc.memo_stats()
    sent = int(memos.pop("feedback_emails_sent", 0))
    fb["emails_sent"] = sent
    fb["response_rate_pct"] = round(100.0 * fb["total"] / sent, 1) if sent else None
    return {"ingestion": ingestion, "feedback": fb, "memos": memos, "users": await svc.user_stats()}
