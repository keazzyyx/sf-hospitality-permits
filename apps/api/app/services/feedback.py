"""90-day outcome feedback: signed links, Resend email, storing results in the precedent store."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import time
from typing import Any

import httpx
from precedent.models import OutcomeFeedback
from precedent.store import Store

from app.core.config import Settings
from app.core.config import settings as app_settings
from app.core.errors import ApiError

log = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"
TOKEN_TTL_SECONDS = 180 * 24 * 3600


def sign_feedback_token(memo_id: str, settings: Settings, *, issued_at: int | None = None) -> str:
    secret = settings.feedback_secret
    if not secret:
        raise ApiError(503, "feedback_unavailable", "FEEDBACK_TOKEN_SECRET is not configured")
    ts = str(issued_at or int(time.time()))
    sig = hmac.new(secret.encode(), f"{memo_id}.{ts}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{memo_id}.{ts}.{sig}"


def verify_feedback_token(token: str, settings: Settings, *, now: int | None = None) -> str:
    secret = settings.feedback_secret
    try:
        memo_id, ts, sig = token.split(".")
    except ValueError as exc:
        raise ApiError(400, "invalid_token", "Malformed feedback link") from exc
    if not secret:
        raise ApiError(503, "feedback_unavailable", "FEEDBACK_TOKEN_SECRET is not configured")
    expected = hmac.new(secret.encode(), f"{memo_id}.{ts}".encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        raise ApiError(400, "invalid_token", "This feedback link is not valid")
    if (now or int(time.time())) - int(ts) > TOKEN_TTL_SECONDS:
        raise ApiError(410, "expired_token", "This feedback link has expired")
    return memo_id


def feedback_email_html(address: str, concept: str, link: str) -> str:
    return f"""<div style="font-family:Inter,Arial,sans-serif;max-width:560px;margin:0 auto;color:#141b2d">
<h2 style="font-weight:600">How did it go at {address}?</h2>
<p>About three months ago {app_settings.APP_NAME} wrote a Location Risk Memo for your {concept} at <b>{address}</b>.
One click tells us what actually happened, which makes the next operator's memo sharper:</p>
<p style="margin:24px 0"><a href="{link}" style="background:#e4572e;color:#fff;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:600">Report the outcome</a></p>
<p style="color:#6b7280;font-size:13px">Approved · approved with conditions · denied · withdrew · still pending. Takes ten seconds; a text box is there if you want to say more.</p>
<p style="color:#6b7280;font-size:12px">You are receiving this because you generated a memo on {app_settings.APP_NAME}. This is the only follow-up we send per memo.</p></div>"""


async def send_feedback_email(
    *,
    to: str,
    address: str,
    concept: str,
    link: str,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> str:
    if not settings.RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY not configured")
    if not settings.FEEDBACK_FROM_EMAIL:
        raise RuntimeError("FEEDBACK_FROM_EMAIL not configured")
    own = client is None
    client = client or httpx.AsyncClient(timeout=15.0)
    try:
        resp = await client.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.FEEDBACK_FROM_EMAIL,
                "to": [to],
                "subject": f"What happened at {address}?",
                "html": feedback_email_html(address, concept, link),
            },
        )
        resp.raise_for_status()
        return str(resp.json().get("id", ""))
    finally:
        if own:
            await client.aclose()


async def record_feedback(
    store: Store, *, memo_row: dict[str, Any], outcome: str, notes: str | None
) -> OutcomeFeedback:
    prof = memo_row.get("profile") or {}
    row = OutcomeFeedback(
        memo_id=str(memo_row["id"]),
        user_id=str(memo_row.get("user_id")) if memo_row.get("user_id") else None,
        address=memo_row["address"],
        lat=memo_row.get("lat"),
        lng=memo_row.get("lng"),
        concept_type=str(prof.get("business_type") or "other"),
        outcome=outcome,
        notes=(notes or "")[:2000] or None,
        reported_at=dt.datetime.now(dt.UTC),
    )
    return await store.insert_feedback(row)
