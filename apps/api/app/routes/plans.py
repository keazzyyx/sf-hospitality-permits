from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.agents.runner import AgentRunner, RunInput
from app.core.auth import AuthUser, current_user
from app.core.errors import ApiError
from app.core.sse import format_event, sse_response
from app.deps import get_plan_service, get_runner
from app.models.plan import PlanRecord, PlanStepRecord, PlanSummary
from app.models.profile import BusinessProfile, ClarifyingQuestion
from app.routes.generation import (
    generate_after_clarification,
    generate_new_plan,
    generate_rerun,
    preview_to_run_input,
)
from app.services.pdf import render_plan_pdf
from app.services.plans import PlanService

router = APIRouter(prefix="/v1/plans", tags=["plans"])


def _validate_date(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("target_open_date must be YYYY-MM-DD") from exc
    return value


class CreatePlanBody(BaseModel):
    description: str = Field(min_length=12, max_length=4000)
    target_open_date: str | None = None
    preview_id: str | None = None

    _d = field_validator("target_open_date")(_validate_date)


class ClarifyBody(BaseModel):
    answers: dict[str, Any] = Field(min_length=1)


class RerunBody(BaseModel):
    description: str | None = Field(default=None, min_length=12, max_length=4000)
    target_open_date: str | None = None
    profile_overrides: dict[str, Any] = Field(default_factory=dict)

    _d = field_validator("target_open_date")(_validate_date)

    @field_validator("profile_overrides")
    @classmethod
    def _known(cls, v: dict[str, Any]) -> dict[str, Any]:
        unknown = [k for k in v if k not in BusinessProfile.model_fields]
        if unknown:
            raise ValueError(f"unknown profile fields: {unknown}")
        return v


class PatchStepBody(BaseModel):
    done: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class PlansResponse(BaseModel):
    plans: list[PlanSummary]


class PlanResponse(BaseModel):
    plan: PlanRecord


class StepResponse(BaseModel):
    step: PlanStepRecord


@router.post("", response_class=StreamingResponse, responses={402: {"description": "paywall"}})
async def create_plan(
    body: CreatePlanBody,
    user: AuthUser = Depends(current_user),
    svc: PlanService = Depends(get_plan_service),
    runner: AgentRunner = Depends(get_runner),
) -> StreamingResponse:
    await svc.assert_can_create(user)
    if body.preview_id:
        preview = await svc.get_preview(body.preview_id)
        inp = preview_to_run_input(preview, target_open_date=body.target_open_date)
        description = inp.description
    else:
        inp = RunInput(description=body.description, target_open_date=body.target_open_date)
        description = body.description
    row = await svc.create_plan(user, description, body.target_open_date or inp.target_open_date)
    plan_id = str(row["id"])
    await svc.record_event(
        user.id, "plan_started", {"plan_id": plan_id, "from_preview": bool(body.preview_id)}
    )

    async def stream() -> AsyncIterator[str]:
        yield format_event("plan_created", {"plan_id": plan_id})
        async for chunk in generate_new_plan(plan_id=plan_id, user=user, inp=inp, svc=svc, runner=runner):
            yield chunk

    return sse_response(stream())


@router.post("/{plan_id}/clarify", response_class=StreamingResponse)
async def clarify_plan(
    plan_id: str,
    body: ClarifyBody,
    user: AuthUser = Depends(current_user),
    svc: PlanService = Depends(get_plan_service),
    runner: AgentRunner = Depends(get_runner),
) -> StreamingResponse:
    row = await svc.get_plan_row(user, plan_id)
    if row.get("status") != "pending_clarification" or not row.get("clarification"):
        raise ApiError(409, "not_pending", "This plan is not waiting for clarification")
    questions = [ClarifyingQuestion.model_validate(q) for q in row["clarification"]["questions"]]
    profile = BusinessProfile.model_validate(row["profile"]) if row.get("profile") else None
    await svc.save_clarification_answers(plan_id, row, body.answers)
    await svc.set_generating(plan_id)
    inp = RunInput(
        description=row["description"],
        target_open_date=row.get("target_open_date"),
        prior_profile=profile,
        clarification_questions=questions,
        clarification_answers=body.answers,
        allow_clarification=False,
    )
    return sse_response(
        generate_after_clarification(plan_id=plan_id, user=user, inp=inp, svc=svc, runner=runner)
    )


@router.post("/{plan_id}/rerun", response_class=StreamingResponse)
async def rerun_plan(
    plan_id: str,
    body: RerunBody,
    user: AuthUser = Depends(current_user),
    svc: PlanService = Depends(get_plan_service),
    runner: AgentRunner = Depends(get_runner),
) -> StreamingResponse:
    row = await svc.get_plan_row(user, plan_id)
    if row.get("status") == "generating":
        raise ApiError(409, "busy", "This plan is already being generated")
    profile = BusinessProfile.model_validate(row["profile"]) if row.get("profile") else None
    description = body.description or row["description"]
    target = body.target_open_date or row.get("target_open_date")
    await svc.set_generating(
        plan_id,
        description=description,
        target_open_date=target,
        bump_version=True,
        current_version=int(row.get("version") or 1),
    )
    inp = RunInput(
        description=description,
        target_open_date=target,
        prior_profile=profile,
        profile_overrides=body.profile_overrides,
        allow_clarification=False,
    )
    return sse_response(generate_rerun(plan_id=plan_id, user=user, inp=inp, svc=svc, runner=runner))


@router.get("", response_model=PlansResponse)
async def list_plans(
    user: AuthUser = Depends(current_user), svc: PlanService = Depends(get_plan_service)
) -> PlansResponse:
    return PlansResponse(plans=await svc.list_summaries(user))


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: str, user: AuthUser = Depends(current_user), svc: PlanService = Depends(get_plan_service)
) -> PlanResponse:
    return PlanResponse(plan=await svc.record(user, plan_id))


@router.patch("/{plan_id}/steps/{step_id}", response_model=StepResponse)
async def patch_step(
    plan_id: str,
    step_id: str,
    body: PatchStepBody,
    user: AuthUser = Depends(current_user),
    svc: PlanService = Depends(get_plan_service),
) -> StepResponse:
    step = await svc.patch_step(user, plan_id, step_id, done=body.done, notes=body.notes)
    await svc.record_event(
        user.id, "step_toggled", {"plan_id": plan_id, "step_key": step.step_key, "done": step.done}
    )
    return StepResponse(step=step)


@router.get("/{plan_id}/export.pdf")
async def export_pdf(
    plan_id: str, user: AuthUser = Depends(current_user), svc: PlanService = Depends(get_plan_service)
) -> Response:
    record = await svc.record(user, plan_id)
    if record.plan is None:
        raise ApiError(409, "not_ready", "Plan is not ready yet")
    pdf = render_plan_pdf(record)
    await svc.record_event(user.id, "pdf_exported", {"plan_id": plan_id})
    filename = f"permit-memo-{plan_id[:8]}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{plan_id}", status_code=204)
async def delete_plan(
    plan_id: str, user: AuthUser = Depends(current_user), svc: PlanService = Depends(get_plan_service)
) -> Response:
    await svc.delete_plan(user, plan_id)
    return Response(status_code=204)
