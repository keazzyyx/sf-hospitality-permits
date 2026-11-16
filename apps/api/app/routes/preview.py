"""Pre-auth preview: triage → intake → requirements only. The timeline / fees / blockers are behind signup."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.agents.runner import AgentRunner, RunInput
from app.core.config import settings
from app.core.errors import ApiError
from app.core.ratelimit import SlidingWindowLimiter, client_ip
from app.core.sse import sse_response
from app.deps import get_plan_service, get_runner
from app.models.profile import BusinessProfile, ClarifyingQuestion
from app.routes.generation import generate_preview
from app.services.plans import PlanService

router = APIRouter(prefix="/v1/preview", tags=["preview"])
limiter = SlidingWindowLimiter(settings.PREVIEW_RATE_LIMIT_PER_HOUR)


class PreviewBody(BaseModel):
    description: str = Field(min_length=12, max_length=4000)
    target_open_date: str | None = None

    @field_validator("target_open_date")
    @classmethod
    def _date(cls, v: str | None) -> str | None:
        if not v:
            return None
        dt.date.fromisoformat(v)
        return v


class PreviewClarifyBody(BaseModel):
    answers: dict[str, Any] = Field(min_length=1)


@router.post("", response_class=StreamingResponse)
async def start_preview(
    body: PreviewBody,
    request: Request,
    svc: PlanService = Depends(get_plan_service),
    runner: AgentRunner = Depends(get_runner),
) -> StreamingResponse:
    ip = client_ip(request)
    limiter.check(ip)
    row = await svc.create_preview(body.description, body.target_open_date, ip)
    await svc.record_event(None, "preview_started", {"preview_id": row["id"]})
    inp = RunInput(description=body.description, target_open_date=body.target_open_date, preview_only=True)
    return sse_response(generate_preview(preview_id=str(row["id"]), inp=inp, svc=svc, runner=runner))


@router.post("/{preview_id}/clarify", response_class=StreamingResponse)
async def clarify_preview(
    preview_id: str,
    body: PreviewClarifyBody,
    request: Request,
    svc: PlanService = Depends(get_plan_service),
    runner: AgentRunner = Depends(get_runner),
) -> StreamingResponse:
    limiter.check(client_ip(request))
    row = await svc.get_preview(preview_id)
    if row.get("status") != "pending_clarification" or not row.get("clarification"):
        raise ApiError(409, "not_pending", "This preview is not waiting for clarification")
    questions = [ClarifyingQuestion.model_validate(q) for q in row["clarification"]["questions"]]
    profile = BusinessProfile.model_validate(row["profile"]) if row.get("profile") else None
    await svc.update_preview(
        preview_id,
        {
            "status": "generating",
            "clarification": {"questions": row["clarification"]["questions"], "answers": body.answers},
        },
    )
    inp = RunInput(
        description=row["description"],
        target_open_date=row.get("target_open_date"),
        prior_profile=profile,
        clarification_questions=questions,
        clarification_answers=body.answers,
        preview_only=True,
        allow_clarification=False,
    )
    return sse_response(generate_preview(preview_id=preview_id, inp=inp, svc=svc, runner=runner))
