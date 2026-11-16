"""Shared plan-generation streaming used by /v1/plans, /clarify, /rerun and /v1/preview.

The WORKFLOW spans live here: each public operation is an async generator decorated with
`@neatlogs.span(kind="WORKFLOW", ...)`, so the span covers the entire SSE stream (the FastAPI route
function itself returns immediately with a StreamingResponse).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

import neatlogs

from app.agents.runner import AgentRunner, RequirementsOutcome, RunInput, RunnerEvent
from app.catalog.loader import Range
from app.core.auth import AuthUser
from app.core.config import settings
from app.core.observability import hash_user_id, set_span_attributes
from app.core.sse import format_event
from app.models.plan import Plan, PreviewResult
from app.models.profile import BusinessProfile, ClarifyingQuestion
from app.services.plans import PlanService
from app.tools.timeline import estimate_timeline, tasks_from_permits

log = logging.getLogger(__name__)


async def runner_events(runner: Any, inp: Any, *, run: Any = None) -> AsyncIterator[RunnerEvent]:
    """Bridge the runner's push-style progress callback and pull-style terminal events into one stream."""
    queue: asyncio.Queue[RunnerEvent | None] = asyncio.Queue()

    async def emit(ev: RunnerEvent) -> None:
        await queue.put(ev)

    async def worker() -> None:
        try:
            async for terminal in (run or runner.run)(inp, emit):
                await queue.put(terminal)
        except Exception:  # surfaced to the client as a generic error event
            log.exception("runner crashed")  # details stay server-side (and on the Neatlogs span)
            await queue.put(
                RunnerEvent(
                    "error",
                    {
                        "code": "generation_failed",
                        "message": "Plan generation failed. Please try again in a minute.",
                    },
                )
            )
        finally:
            await queue.put(None)

    task = asyncio.create_task(worker())
    try:
        while True:
            ev = await queue.get()
            if ev is None:
                break
            yield ev
    finally:
        if not task.done():
            task.cancel()


def _pass_through(ev: RunnerEvent) -> str | None:
    if ev.type in {"stage", "tool", "narrative"}:
        return format_event(ev.type, ev.data)
    return None


async def _generate_plan(
    *, plan_id: str, user: AuthUser, inp: RunInput, svc: PlanService, runner: AgentRunner, count_as_new: bool
) -> AsyncIterator[str]:
    set_span_attributes(user_id=hash_user_id(user.id, settings.USER_ID_HASH_SALT), plan_id=plan_id)
    async for ev in runner_events(runner, inp):
        passthrough = _pass_through(ev)
        if passthrough:
            yield passthrough
            continue
        if ev.type == "needs_clarification":
            questions = [ClarifyingQuestion.model_validate(q) for q in ev.data["questions"]]
            profile = BusinessProfile.model_validate(ev.data["profile"])
            await svc.set_clarification(plan_id, questions, profile)
            yield format_event(
                "needs_clarification",
                {"plan_id": plan_id, "questions": ev.data["questions"], "profile": ev.data["profile"]},
            )
            return
        if ev.type == "plan":
            plan: Plan = ev.data["plan"]
            profile = ev.data["profile"]
            set_span_attributes(
                city=plan.jurisdiction.city_slug or profile.city_name or "unknown",
                business_type=profile.business_type,
                permit_count=len(plan.steps),
                city_supported=plan.city_supported,
            )
            await svc.save_result(plan_id, profile, plan)
            if count_as_new:
                await svc.consume_plan(user)
            await svc.record_event(
                user.id,
                "plan_completed",
                {"plan_id": plan_id, "city": plan.jurisdiction.city_slug, "steps": len(plan.steps)},
            )
            record = await svc.record(user, plan_id)
            yield format_event("plan", record.model_dump())
            return
        if ev.type == "error":
            await svc.mark_failed(plan_id, ev.data.get("message", "unknown error"))
            set_span_attributes(error_code=ev.data.get("code"))
            yield format_event("error", ev.data)
            return


@neatlogs.span(kind="WORKFLOW", name="plan.generate", capture_output=False)
async def generate_new_plan(
    *, plan_id: str, user: AuthUser, inp: RunInput, svc: PlanService, runner: AgentRunner
) -> AsyncIterator[str]:
    async for chunk in _generate_plan(
        plan_id=plan_id, user=user, inp=inp, svc=svc, runner=runner, count_as_new=True
    ):
        yield chunk


@neatlogs.span(kind="WORKFLOW", name="plan.clarify", capture_output=False)
async def generate_after_clarification(
    *, plan_id: str, user: AuthUser, inp: RunInput, svc: PlanService, runner: AgentRunner
) -> AsyncIterator[str]:
    async for chunk in _generate_plan(
        plan_id=plan_id, user=user, inp=inp, svc=svc, runner=runner, count_as_new=True
    ):
        yield chunk


@neatlogs.span(kind="WORKFLOW", name="plan.rerun", capture_output=False)
async def generate_rerun(
    *, plan_id: str, user: AuthUser, inp: RunInput, svc: PlanService, runner: AgentRunner
) -> AsyncIterator[str]:
    async for chunk in _generate_plan(
        plan_id=plan_id, user=user, inp=inp, svc=svc, runner=runner, count_as_new=False
    ):
        yield chunk


def build_preview(
    preview_id: str, req: RequirementsOutcome, runner: AgentRunner, target_open_date: str | None
) -> PreviewResult:
    schedule, _ = runner.compute_schedule(req.permits, target_open_date)
    return PreviewResult(
        preview_id=preview_id,
        profile=req.profile,
        city_supported=req.city_supported,
        unsupported_city_note=req.unsupported_city_note,
        permits=runner.preview_permits(req),
        permit_count=len(req.permits),
        estimated_total_days=Range(min=schedule.total_days_min, max=schedule.total_days_max),
    )


@neatlogs.span(kind="WORKFLOW", name="plan.preview", capture_output=False)
async def generate_preview(
    *, preview_id: str, inp: RunInput, svc: PlanService, runner: AgentRunner
) -> AsyncIterator[str]:
    set_span_attributes(preview_id=preview_id, user_id="anonymous")
    async for ev in runner_events(runner, inp):
        passthrough = _pass_through(ev)
        if passthrough:
            yield passthrough
            continue
        if ev.type == "needs_clarification":
            await svc.update_preview(
                preview_id,
                {
                    "status": "pending_clarification",
                    "profile": ev.data["profile"],
                    "clarification": {"questions": ev.data["questions"], "answers": {}},
                },
            )
            yield format_event(
                "needs_clarification",
                {"preview_id": preview_id, "questions": ev.data["questions"], "profile": ev.data["profile"]},
            )
            return
        if ev.type == "requirements":
            req: RequirementsOutcome = ev.data["outcome"]
            result = build_preview(preview_id, req, runner, inp.target_open_date)
            set_span_attributes(
                city=req.profile.city_slug or req.profile.city_name or "unknown",
                business_type=req.profile.business_type,
                permit_count=len(req.permits),
            )
            await svc.update_preview(
                preview_id,
                {"status": "ready", "profile": req.profile.model_dump(), "result": result.model_dump()},
            )
            yield format_event("preview", result.model_dump())
            return
        if ev.type == "error":
            await svc.update_preview(preview_id, {"status": "failed"})
            yield format_event("error", ev.data)
            return
    _ = uuid  # keep import for type-checkers in some configurations


def preview_to_run_input(preview: dict[str, Any], *, target_open_date: str | None) -> RunInput:
    profile = BusinessProfile.model_validate(preview["profile"]) if preview.get("profile") else None
    return RunInput(
        description=str(preview["description"]),
        target_open_date=target_open_date or preview.get("target_open_date"),
        prior_profile=profile,
        allow_clarification=False,
    )


__all__ = [
    "build_preview",
    "estimate_timeline",
    "generate_after_clarification",
    "generate_new_plan",
    "generate_preview",
    "generate_rerun",
    "preview_to_run_input",
    "runner_events",
    "tasks_from_permits",
]
