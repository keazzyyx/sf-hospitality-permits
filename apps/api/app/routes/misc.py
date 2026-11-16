"""Health, catalog, me, leads."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.catalog.loader import get_catalog
from app.core.auth import AuthUser, current_user
from app.core.config import settings
from app.core.observability import local_doctor
from app.core.ratelimit import SlidingWindowLimiter, client_ip
from app.deps import get_plan_service
from app.models.plan import Me
from app.services.memos import MemoService
from app.services.plans import PlanService

router = APIRouter(tags=["misc"])
leads_limiter = SlidingWindowLimiter(settings.LEADS_RATE_LIMIT_PER_HOUR)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


@router.get("/healthz")
async def healthz() -> dict[str, object]:
    return {
        "status": "ok",
        "version": settings.GIT_SHA,
        "env": settings.ENV,
        "catalog_permits": len(get_catalog().permits),
        "neatlogs": local_doctor(),
    }


class City(BaseModel):
    slug: str
    name: str
    state: str | None
    supported: bool


@router.get("/v1/catalog/cities")
async def cities() -> dict[str, list[City]]:
    return {
        "cities": [
            City(slug=j.city_slug or "", name=j.name, state=j.state, supported=j.supported)
            for j in get_catalog().supported_cities
        ]
    }


@router.get("/v1/me", response_model=dict[str, Me])
async def me(
    user: AuthUser = Depends(current_user), svc: PlanService = Depends(get_plan_service)
) -> dict[str, Me]:
    profile = await svc.ensure_profile(user)
    me = svc.entitlement_for(profile)
    ent = MemoService(svc.db, settings).memo_entitlement(profile)
    return {
        "profile": me.model_copy(
            update={
                "memo_credits": ent["memo_credits"],
                "pro_status": ent["pro_status"],
                "pro_current_period_end": ent["pro_current_period_end"],
                "free_teasers_remaining": ent["free_teasers_remaining"],
                "can_create_memo": ent["can_create_memo"],
                "can_unlock_memo": ent["can_unlock"],
                "is_admin": ent["is_admin"],
            }
        )
    }


class LeadBody(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=2000)


@router.post("/v1/leads", status_code=201)
async def capture_lead(
    body: LeadBody, request: Request, svc: PlanService = Depends(get_plan_service)
) -> dict[str, bool]:
    leads_limiter.check(client_ip(request))
    if not EMAIL_RE.match(body.email.strip()):
        from app.core.errors import ApiError

        raise ApiError(422, "validation_error", "Please enter a valid email address")
    await svc.capture_lead(body.email.strip().lower(), body.city, body.state, body.description)
    await svc.record_event(None, "lead_captured", {"city": body.city, "state": body.state})
    return {"ok": True}
