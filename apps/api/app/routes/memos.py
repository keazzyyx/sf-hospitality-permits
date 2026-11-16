"""Location Risk Memo routes: generation (SSE), answer rounds (SSE), teaser/unlock, PDF, map, bulk CSV."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import neatlogs
from fastapi import APIRouter, BackgroundTasks, Depends, File, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.agents.memo_runner import AnswersRunInput, MemoRunInput, MemoRunner
from app.agents.runner import RunnerEvent
from app.core.auth import AuthUser, current_user
from app.core.config import settings
from app.core.errors import ApiError
from app.core.observability import hash_user_id, set_span_attributes
from app.core.ratelimit import SlidingWindowLimiter
from app.core.sse import format_event, sse_response
from app.deps import get_memo_runner, get_memo_service
from app.memo.answers import (
    ANSWERS_EMPTY_MESSAGE,
    ANSWERS_FAILED_MESSAGE,
    ANSWERS_FOLLOW_UP_MESSAGE,
    ANSWERS_FOOD_SERVICE_MESSAGE,
    ANSWERS_RUNNING_MESSAGE,
    ANSWERS_UNCHANGED_MESSAGE,
    FoodServiceNeedsNoAlcoholError,
    RoundAnswers,
    merge_answers,
)
from app.memo.context import get_store
from app.memo.intake import IntakeAnswers
from app.models.memo import MemoRecord, MemoRevision, MemoSummary
from app.models.profile import CODE_ONLY_FIELDS, BusinessProfile, ClarifyingQuestion
from app.routes.generation import runner_events
from app.services.memo_pdf import render_memo_pdf
from app.services.memos import MemoService

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/memos", tags=["memos"])
# answer rounds, per signed-in account (the other write routes are limited per address; these need an account)
answers_limiter = SlidingWindowLimiter(settings.MEMO_ANSWERS_RATE_LIMIT_PER_HOUR)
ANSWERS_ROUND_EVENT = "memo_answers_rerun"


class CreateMemoBody(BaseModel):
    address: str = Field(min_length=4, max_length=200)
    description: str = Field(min_length=12, max_length=4000)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    profile_overrides: dict[str, Any] = Field(default_factory=dict)
    # The optional intake questions (app.memo.intake): every key optional, a missing or null key a skipped one.
    intake: IntakeAnswers | None = None
    # Re-run of a memo stored in an earlier report format (MemoService.rerun_source). The new memo uses that
    # memo's address, coordinates and description; the `address`, `lat`, `lng` and `description` sent with it
    # are ignored, and `profile_overrides` is refused, so a re-run is the same concept. The intake answers sent
    # are used (they answer questions an earlier-format memo never asked); without them, the stored ones. The
    # first re-run of a legacy memo the user unlocked is free (MemoService.free_rerun_attempt).
    rerun_of: uuid.UUID | None = None

    @field_validator("profile_overrides")
    @classmethod
    def _known(cls, v: dict[str, Any]) -> dict[str, Any]:
        unknown = [k for k in v if k not in BusinessProfile.model_fields]
        if unknown:
            raise ValueError(f"unknown profile fields: {unknown}")
        # code's own records of where a fact came from: an override of one would forge a line's origin
        code_only = [k for k in v if k in CODE_ONLY_FIELDS]
        if code_only:
            raise ValueError(f"profile fields only the rules set, never an override: {code_only}")
        return v

    @model_validator(mode="after")
    def _rerun_is_the_same_concept(self) -> CreateMemoBody:
        if self.rerun_of is not None and self.profile_overrides:
            raise ValueError("profile_overrides cannot be sent with rerun_of: a re-run is the same concept")
        return self


class ClarifyBody(BaseModel):
    answers: dict[str, Any] = Field(min_length=1)


class MemosResponse(BaseModel):
    memos: list[MemoSummary]


class MemoResponse(BaseModel):
    memo: MemoRecord


# Memo runs that outlive their stream: a run started by POST /v1/memos or /clarify goes on to the end when the page
# that started it is closed or navigated away (the page polls GET /v1/memos/{id} and picks the result up), so the
# memo is saved, and charged, exactly as if the page had stayed. The tasks are held here so that nothing collects them
# while no stream reads them. An API restart still ends a run; the stalled-run rule in app.services.memos
# (GENERATING_TIMEOUT) then reports it as failed.
_RUNS: dict[str, asyncio.Task[None]] = {}
GENERATION_FAILED = "Generation failed. Please try again in a minute."


def _detached(
    source: AsyncIterator[str],
    *,
    memo_id: str,
    svc: MemoService,
    end: Callable[[], Awaitable[bool]] | None = None,
    failure_message: str = GENERATION_FAILED,
) -> AsyncIterator[str]:
    """Run `source` (a memo run's SSE chunks) to the end in its own task, and stream its chunks for as long as the
    client listens. The run saves its own result (`save_result`, `mark_failed`); if it raises, `end` ends it unless
    it already finished (by default the memo is marked failed; an answer round puts the memo back as it was)."""
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    listening = {"on": True}

    async def run() -> None:
        try:
            async for chunk in source:
                if listening["on"]:
                    await queue.put(chunk)
        except Exception:  # surfaced to the client as a generic error event
            log.exception("memo run %s crashed", memo_id)
            if end is None:
                failed = await svc.mark_failed_if_running(memo_id, failure_message)
            else:
                failed = await end()
            if listening["on"]:
                if failed:
                    await queue.put(
                        format_event("error", {"code": "generation_failed", "message": failure_message})
                    )
                else:
                    # the memo was saved before the crash: give the page the saved memo, not a failure
                    row = await svc.memo_by_id(memo_id)
                    if row is not None and row.get("status") == "ready":
                        await queue.put(format_event("memo", svc.to_record(row).model_dump()))
        finally:
            await queue.put(None)

    task = asyncio.create_task(run(), name=f"memo-run-{memo_id}")
    _RUNS[memo_id] = task

    def forget(done: asyncio.Task[None]) -> None:
        if _RUNS.get(memo_id) is done:
            del _RUNS[memo_id]

    task.add_done_callback(forget)

    async def listen() -> AsyncIterator[str]:
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    return
                yield chunk
        finally:
            # the client went away (or the run ended): stop queueing chunks, never stop the run
            listening["on"] = False

    return listen()


async def _memo_events(runner: MemoRunner, inp: MemoRunInput) -> AsyncIterator[RunnerEvent]:
    async for ev in runner_events(runner, inp, run=runner.run_memo):
        yield ev


async def _generate(
    *, memo_id: str, user: AuthUser, inp: MemoRunInput, svc: MemoService, runner: MemoRunner
) -> AsyncIterator[str]:
    set_span_attributes(
        user_id=hash_user_id(user.id, settings.USER_ID_HASH_SALT), memo_id=memo_id, address=inp.address
    )
    async for ev in _memo_events(runner, inp):
        if ev.type in {"stage", "tool"}:  # report format 2 streams no prose
            yield format_event(ev.type, ev.data)
            continue
        if ev.type == "needs_clarification":
            questions = [ClarifyingQuestion.model_validate(q) for q in ev.data["questions"]]
            profile = BusinessProfile.model_validate(ev.data["profile"])
            await svc.set_clarification(memo_id, questions, profile)
            yield format_event(
                "needs_clarification",
                {"memo_id": memo_id, "questions": ev.data["questions"], "profile": ev.data["profile"]},
            )
            return
        if ev.type == "memo":
            memo, profile, geo = ev.data["memo"], ev.data["profile"], ev.data["geo"]
            teaser = MemoRunner.teaser(memo)
            row = await svc.save_result(
                user, memo_id, profile, memo, teaser, lat=geo.lat, lng=geo.lng, address=geo.address
            )
            if (
                row is None
            ):  # deleted, or already ended, while the run went on: nothing saved, nothing charged
                return
            # what the intake left, kept for the memo's answer rounds (app.memo.answers)
            row = await svc.save_basis(memo_id, ev.data["basis"]) or row
            set_span_attributes(
                overall_status=memo.overall.status,
                access=row.get("access"),
                city=profile.city_slug,
                business_type=profile.business_type,
            )
            await svc.plans.record_event(
                user.id,
                "memo_completed",
                {"memo_id": memo_id, "overall_status": memo.overall.status, "access": row.get("access")},
            )
            yield format_event("memo", svc.to_record(row).model_dump())
            return
        if ev.type == "error":
            await svc.mark_failed(memo_id, ev.data.get("message", "unknown error"))
            set_span_attributes(error_code=ev.data.get("code"))
            yield format_event("error", ev.data)
            return


@neatlogs.span(kind="WORKFLOW", name="memo.generate", capture_output=False)
async def generate_memo(
    *, memo_id: str, user: AuthUser, inp: MemoRunInput, svc: MemoService, runner: MemoRunner
) -> AsyncIterator[str]:
    yield format_event("memo_created", {"memo_id": memo_id})
    async for chunk in _generate(memo_id=memo_id, user=user, inp=inp, svc=svc, runner=runner):
        yield chunk


@neatlogs.span(kind="WORKFLOW", name="memo.clarify", capture_output=False)
async def generate_memo_after_clarification(
    *, memo_id: str, user: AuthUser, inp: MemoRunInput, svc: MemoService, runner: MemoRunner
) -> AsyncIterator[str]:
    async for chunk in _generate(memo_id=memo_id, user=user, inp=inp, svc=svc, runner=runner):
        yield chunk


@router.post("", response_class=StreamingResponse, responses={402: {"description": "paywall_memo"}})
async def create_memo(
    body: CreateMemoBody,
    user: AuthUser = Depends(current_user),
    svc: MemoService = Depends(get_memo_service),
    runner: MemoRunner = Depends(get_memo_runner),
) -> StreamingResponse:
    address, description, lat, lng = body.address, body.description, body.lat, body.lng
    answers = body.intake or IntakeAnswers()
    source: dict[str, Any] | None = None
    row: dict[str, Any] | None = None
    if body.rerun_of is not None:
        source = await svc.rerun_source(user, str(body.rerun_of))
        address, description = source["address"], source["description"]
        lat, lng = source.get("lat"), source.get("lng")
        if body.intake is None:
            answers = MemoService.intake_of(source)
        profile = await svc.plans.ensure_profile(user)
        # Pro and owner accounts get every memo unlocked anyway: their re-run does not use the free one
        attempt = None if svc.is_unlimited(profile) else await svc.free_rerun_attempt(user, source)
        if attempt is not None:
            # None when a request sent at the same moment took this free re-run: this one is charged
            row = await svc.create_free_rerun(user, source, attempt, intake=answers)
    free_rerun = row is not None
    if row is None:
        await svc.assert_can_create(user)
        row = await svc.create(
            user, address=address, description=description, lat=lat, lng=lng, intake=answers
        )
    memo_id = str(row["id"])
    started: dict[str, Any] = {"memo_id": memo_id}
    if source is not None:
        started |= {"rerun_of": str(source["id"]), "free_rerun": free_rerun}
    await svc.plans.record_event(user.id, "memo_started", started)
    inp = MemoRunInput(
        address=address,
        description=description,
        lat=lat,
        lng=lng,
        profile_overrides=body.profile_overrides,
        intake_answers=answers,
    )
    return sse_response(
        _detached(
            generate_memo(memo_id=memo_id, user=user, inp=inp, svc=svc, runner=runner),
            memo_id=memo_id,
            svc=svc,
        )
    )


@router.post("/{memo_id}/clarify", response_class=StreamingResponse)
async def clarify_memo(
    memo_id: str,
    body: ClarifyBody,
    user: AuthUser = Depends(current_user),
    svc: MemoService = Depends(get_memo_service),
    runner: MemoRunner = Depends(get_memo_runner),
) -> StreamingResponse:
    row = await svc.row(user, memo_id)
    if row.get("status") != "pending_clarification" or not row.get("clarification"):
        raise ApiError(409, "not_pending", "This memo is not waiting for clarification")
    questions = [ClarifyingQuestion.model_validate(q) for q in row["clarification"]["questions"]]
    profile = BusinessProfile.model_validate(row["profile"]) if row.get("profile") else None
    await svc.set_generating(memo_id, row, body.answers)
    inp = MemoRunInput(
        address=row["address"],
        description=row["description"],
        lat=row.get("lat"),
        lng=row.get("lng"),
        prior_profile=profile,
        clarification_questions=questions,
        clarification_answers=body.answers,
        allow_clarification=False,
        intake_answers=MemoService.intake_of(row),  # the answers sent with the create request still win
    )
    return sse_response(
        _detached(
            generate_memo_after_clarification(memo_id=memo_id, user=user, inp=inp, svc=svc, runner=runner),
            memo_id=memo_id,
            svc=svc,
        )
    )


# ---- answer rounds (app.memo.answers): more intake answers on the same memo, free, no model call --------------
@neatlogs.span(kind="WORKFLOW", name="memo.answers", capture_output=False)
async def generate_answer_round(
    *,
    memo_id: str,
    claim: str,
    round_no: int,
    user: AuthUser,
    inp: AnswersRunInput,
    svc: MemoService,
    runner: MemoRunner,
) -> AsyncIterator[str]:
    set_span_attributes(
        user_id=hash_user_id(user.id, settings.USER_ID_HASH_SALT),
        memo_id=memo_id,
        address=inp.address,
        answers_round=round_no,
    )
    yield format_event("answers_round", {"memo_id": memo_id, "round": round_no})
    async for ev in runner_events(runner, inp, run=runner.run_answers):
        if ev.type in {"stage", "tool"}:
            yield format_event(ev.type, ev.data)
            continue
        if ev.type == "memo":
            memo, profile, geo = ev.data["memo"], ev.data["profile"], ev.data["geo"]
            row = await svc.save_answers_result(
                memo_id,
                claim,
                round_no,
                inp.intake_answers,
                profile,
                memo,
                MemoRunner.teaser(memo),
                lat=geo.lat,
                lng=geo.lng,
                address=geo.address,
            )
            if row is None:  # deleted, or taken over by a later round, while this one went on
                return
            set_span_attributes(overall_status=memo.overall.status, access=row.get("access"))
            yield format_event("memo", svc.to_record(row).model_dump())
            return
        if ev.type == "error":
            # the memo is as it was before the round, with the round's failure as its error line
            await svc.end_answers(memo_id, claim, ANSWERS_FAILED_MESSAGE)
            set_span_attributes(error_code=ev.data.get("code"))
            yield format_event("error", ev.data)
            return


@router.post(
    "/{memo_id}/answers",
    response_class=StreamingResponse,
    responses={409: {"description": "answers_unavailable, answers_round_limit, answers_running, not_ready"}},
)
async def answer_memo(
    memo_id: str,
    body: RoundAnswers,
    user: AuthUser = Depends(current_user),
    svc: MemoService = Depends(get_memo_service),
    runner: MemoRunner = Depends(get_memo_runner),
) -> StreamingResponse:
    """Run the memo again with more intake answers (an answer round): same memo, free, no model call. The body is
    the intake answers only (`RoundAnswers`; any other key, an address, a description or `profile_overrides`
    among them, is refused with 422, as are two answers that contradict each other). A follow-up may come alone when
    the answer it follows is stored with the memo; with nothing to stand on it is refused with 422. So is the kind of
    food or drink service where the stored answers say alcohol is served, unless "No alcohol" is sent with it."""
    answers_limiter.check(user.id)
    if body.empty:
        raise ApiError(422, "validation_error", ANSWERS_EMPTY_MESSAGE)
    row, basis = await svc.answers_source(user, memo_id)
    stored = MemoService.intake_of(row)
    try:
        merged, replaced = merge_answers(stored, body)
    # a kind of food or drink service over stored answers that serve alcohol, with no "No alcohol" sent
    except FoodServiceNeedsNoAlcoholError:
        raise ApiError(422, "validation_error", ANSWERS_FOOD_SERVICE_MESSAGE, memo_id=memo_id) from None
    except ValidationError:  # a count of other locations with no "part of a chain" true, sent or stored
        raise ApiError(422, "validation_error", ANSWERS_FOLLOW_UP_MESSAGE, memo_id=memo_id) from None
    if merged == stored:
        raise ApiError(422, "no_new_answers", ANSWERS_UNCHANGED_MESSAGE, memo_id=memo_id)
    round_no = int(row.get("answers_round") or 0) + 1
    claim = await svc.start_answers(row)
    if claim is None:  # another round started first, or the memo was deleted, since it was read
        raise ApiError(409, "answers_running", ANSWERS_RUNNING_MESSAGE, memo_id=memo_id)
    await svc.plans.record_event(
        user.id,
        ANSWERS_ROUND_EVENT,
        {
            "memo_id": memo_id,
            "round": round_no,
            "answered": list(body.answered()),
            "replaced": list(replaced),
            "access": row.get("access"),
        },
    )
    inp = AnswersRunInput(
        address=row["address"],
        description=row["description"],
        lat=row.get("lat"),
        lng=row.get("lng"),
        basis=basis,
        intake_answers=merged,
    )

    async def end() -> bool:
        return await svc.end_answers(memo_id, claim, ANSWERS_FAILED_MESSAGE)

    return sse_response(
        _detached(
            generate_answer_round(
                memo_id=memo_id,
                claim=claim,
                round_no=round_no,
                user=user,
                inp=inp,
                svc=svc,
                runner=runner,
            ),
            memo_id=memo_id,
            svc=svc,
            end=end,
            failure_message=ANSWERS_FAILED_MESSAGE,
        )
    )


class RevisionsResponse(BaseModel):
    revisions: list[MemoRevision]


@router.get("/{memo_id}/revisions", response_model=RevisionsResponse)
async def memo_revisions(
    memo_id: str, user: AuthUser = Depends(current_user), svc: MemoService = Depends(get_memo_service)
) -> RevisionsResponse:
    """The versions of the memo that answer rounds replaced, oldest first (owner only, as every memo route)."""
    return RevisionsResponse(revisions=await svc.revisions(user, memo_id))


@router.get("", response_model=MemosResponse)
async def list_memos(
    user: AuthUser = Depends(current_user), svc: MemoService = Depends(get_memo_service)
) -> MemosResponse:
    return MemosResponse(memos=await svc.list_summaries(user))


# bulk routes are declared before /{memo_id} so "bulk" is never parsed as an id
class BulkResponse(BaseModel):
    batch_id: str
    memo_ids: list[str]
    skipped: list[dict[str, Any]]


async def _run_batch(
    memo_ids: list[str], inputs: list[MemoRunInput], user: AuthUser, svc: MemoService, runner: MemoRunner
) -> None:
    batch_id = None
    for memo_id, inp in zip(memo_ids, inputs, strict=True):
        if batch_id is None:
            row = await svc.memo_by_id(memo_id)
            batch_id = str(row["batch_id"]) if row and row.get("batch_id") else ""
        if batch_id:  # the rows still queued are not stalled runs (MemoService.touch_batch)
            await svc.touch_batch(batch_id)
        try:
            async for _ in generate_memo(memo_id=memo_id, user=user, inp=inp, svc=svc, runner=runner):
                pass
        except Exception:  # keep the batch going
            log.exception("bulk memo %s failed", memo_id)
            await svc.mark_failed(memo_id, "generation failed")


@router.post("/bulk", response_model=BulkResponse, status_code=202)
async def bulk_upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user: AuthUser = Depends(current_user),
    svc: MemoService = Depends(get_memo_service),
    runner: MemoRunner = Depends(get_memo_runner),
) -> BulkResponse:
    await svc.assert_pro(user)
    raw = await file.read()
    if len(raw) > 200_000:
        raise ApiError(413, "too_large", "CSV must be under 200 KB")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ApiError(
            422, "validation_error", "Could not parse the CSV (UTF-8, header: address,description)"
        ) from exc
    if (
        not rows
        or not reader.fieldnames
        or not {"address", "description"} <= {f.strip().lower() for f in reader.fieldnames}
    ):
        raise ApiError(422, "validation_error", "CSV needs a header row with columns: address, description")
    if len(rows) > 25:
        raise ApiError(422, "validation_error", "At most 25 rows per upload")
    batch = await svc.create_batch(user, file.filename, len(rows))
    batch_id = str(batch["id"])
    memo_ids: list[str] = []
    inputs: list[MemoRunInput] = []
    skipped: list[dict[str, Any]] = []
    for i, r in enumerate(rows, start=2):
        norm = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
        address, description = norm.get("address", ""), norm.get("description", "")
        if len(address) < 4 or len(description) < 12:
            skipped.append({"row": i, "reason": "address or description missing / too short"})
            continue
        row = await svc.create(
            user, address=address, description=description, lat=None, lng=None, batch_id=batch_id
        )
        memo_ids.append(str(row["id"]))
        inputs.append(MemoRunInput(address=address, description=description, allow_clarification=False))
    await svc.plans.record_event(
        user.id, "bulk_uploaded", {"batch_id": batch_id, "rows": len(memo_ids), "skipped": len(skipped)}
    )
    background.add_task(_run_batch, memo_ids, inputs, user, svc, runner)
    return BulkResponse(batch_id=batch_id, memo_ids=memo_ids, skipped=skipped)


@router.get("/bulk/{batch_id}", response_model=dict[str, Any])
async def bulk_status(
    batch_id: str, user: AuthUser = Depends(current_user), svc: MemoService = Depends(get_memo_service)
) -> dict[str, Any]:
    memos = await svc.list_summaries(user, batch_id=batch_id)
    if not memos:
        raise ApiError(404, "not_found", "Batch not found")
    return {"batch_id": batch_id, "memos": [m.model_dump() for m in memos]}


@router.get("/{memo_id}", response_model=MemoResponse)
async def get_memo(
    memo_id: str, user: AuthUser = Depends(current_user), svc: MemoService = Depends(get_memo_service)
) -> MemoResponse:
    rec = await svc.record(user, memo_id)
    if rec.access == "teaser" and rec.status == "ready":
        await svc.plans.record_event(user.id, "memo_teaser_viewed", {"memo_id": memo_id})
    return MemoResponse(memo=rec)


@router.post("/{memo_id}/unlock", response_model=MemoResponse)
async def unlock_memo(
    memo_id: str, user: AuthUser = Depends(current_user), svc: MemoService = Depends(get_memo_service)
) -> MemoResponse:
    return MemoResponse(memo=await svc.unlock(user, memo_id))


@router.get("/{memo_id}/export.pdf")
async def export_memo_pdf(
    memo_id: str, user: AuthUser = Depends(current_user), svc: MemoService = Depends(get_memo_service)
) -> Response:
    _row, memo = await svc.full_memo(user, memo_id)
    pdf = render_memo_pdf(memo, generated_for=user.email)
    await svc.plans.record_event(user.id, "memo_pdf_exported", {"memo_id": memo_id})
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="permit-memo-{memo_id[:8]}.pdf"'},
    )


@router.get("/{memo_id}/map.geojson")
async def memo_map(
    memo_id: str, user: AuthUser = Depends(current_user), svc: MemoService = Depends(get_memo_service)
) -> dict[str, Any]:
    _, memo = await svc.full_memo(user, memo_id)
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [memo.lng, memo.lat]},
            "properties": {
                "kind": "subject",
                "address": memo.address,
                "overall_status": memo.overall.status,
            },
        },
    ]
    for c in memo.comparable_cases:
        if c.lat is None or c.lng is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [c.lng, c.lat]},
                "properties": {
                    "kind": "comparable",
                    "application_id": c.application_id,
                    "permit_type": c.permit_type,
                    "outcome": c.outcome,
                    "distance_m": c.distance_m,
                    "decided_at": c.decided_at,
                    "similarity": c.similarity_score,
                    "source_url": c.source_url,
                    "address": c.address,
                },
            }
        )
    store = get_store()
    for o in await store.overlays_at(memo.lat, memo.lng):
        if o.geom:
            features.append(
                {
                    "type": "Feature",
                    "geometry": o.geom,
                    "properties": {
                        "kind": "overlay",
                        "overlay_kind": o.kind,
                        "name": o.name,
                        "code_section": o.code_section,
                    },
                }
            )
    return {"type": "FeatureCollection", "features": features}


@router.delete("/{memo_id}", status_code=204)
async def delete_memo(
    memo_id: str, user: AuthUser = Depends(current_user), svc: MemoService = Depends(get_memo_service)
) -> Response:
    await svc.delete(user, memo_id)
    # a run still going for the deleted memo stops here (it would save nothing anyway)
    task = _RUNS.get(memo_id)
    if task is not None and not task.done():
        task.cancel()
    return Response(status_code=204)
