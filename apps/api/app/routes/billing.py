from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.auth import AuthUser, current_user
from app.core.config import get_settings
from app.deps import get_db, get_plan_service
from app.services.billing import BillingService
from app.services.db import Database
from app.services.plans import PlanService

router = APIRouter(prefix="/v1/billing", tags=["billing"])


def get_billing(db: Database = Depends(get_db)) -> BillingService:
    return BillingService(db, get_settings())


class CheckoutBody(BaseModel):
    mode: Literal["plan", "subscription", "memo", "pro"]
    success_url: str = Field(pattern=r"^https?://")
    cancel_url: str = Field(pattern=r"^https?://")


class PortalBody(BaseModel):
    return_url: str = Field(pattern=r"^https?://")


@router.post("/checkout")
async def checkout(
    body: CheckoutBody,
    user: AuthUser = Depends(current_user),
    svc: PlanService = Depends(get_plan_service),
    billing: BillingService = Depends(get_billing),
) -> dict[str, str]:
    profile = await svc.ensure_profile(user)
    url = await billing.checkout_url(user, profile, body.mode, body.success_url, body.cancel_url)
    await svc.record_event(user.id, "checkout_started", {"mode": body.mode})
    return {"url": url}


@router.post("/portal")
async def portal(
    body: PortalBody,
    user: AuthUser = Depends(current_user),
    svc: PlanService = Depends(get_plan_service),
    billing: BillingService = Depends(get_billing),
) -> dict[str, str]:
    profile = await svc.ensure_profile(user)
    return {"url": await billing.portal_url(user, profile, body.return_url)}


@router.post("/webhook")
async def webhook(request: Request, billing: BillingService = Depends(get_billing)) -> dict[str, object]:
    payload = await request.body()
    event = billing.construct_event(payload, request.headers.get("stripe-signature"))
    outcome = await billing.handle_event(event.to_dict() if hasattr(event, "to_dict") else dict(event))
    return {"received": True, "outcome": outcome}
