"""AgentRunner: the intake → requirements → timeline → blocker handoff chain on the Anthropic SDK.

Each stage is one Claude conversation with a tool-use loop. Structured output is enforced by a
`submit_<stage>_result` tool whose input_schema is the stage's Pydantic model; the loop ends only when
that tool is called with input that validates. No free-form JSON is ever parsed.

Observability: every stage method is a Neatlogs AGENT span; the route wraps the whole run in a
WORKFLOW span; tools carry their own TOOL spans; the Anthropic auto-instrumentation records the LLM
calls underneath.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar, cast

import neatlogs
from anthropic import AsyncAnthropic, BadRequestError
from anthropic.resources.messages import AsyncMessages
from anthropic.types import Message, MessageParam, ToolParam, ToolUseBlock
from pydantic import BaseModel, ValidationError

from app.agents import prompts
from app.catalog.loader import Catalog, CatalogPermit
from app.core.config import Settings
from app.core.config import settings as app_settings
from app.core.observability import set_span_attributes
from app.models.plan import (
    Blocker,
    BlockerResult,
    FeeSummary,
    ParallelTrack,
    PermitPreview,
    Plan,
    PlanJurisdiction,
    PlanStep,
    RequirementsResult,
    Timeline,
    TimelineNarrative,
    TimelineWeek,
)
from app.models.profile import (
    MODEL_MAY_NOT_SET,
    BusinessProfile,
    ClarifyingQuestion,
    IntakeResult,
    TriageResult,
)
from app.tools import CHECK_DEPENDENCIES, ESTIMATE_TIMELINE, GET_FEE_TOTAL, LOOKUP_PERMIT_CATALOG, WEB_VERIFY
from app.tools.base import ToolSpec, json_schema_for
from app.tools.catalog_tool import lookup
from app.tools.fees import fee_summary
from app.tools.timeline import DependencyError, Schedule, estimate_timeline, tasks_from_permits
from app.tools.web_verify import VerifyOutput, verify_url

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

# Intake writes the concept profile, and the memo's rules (app.memo.pathway) read that profile. It is sampled
# at temperature 0 so the same description gives the same profile as often as the model allows. Triage only
# accepts or rejects the description and guesses the city and state that intake is given; it writes no profile
# and the memo never runs it, so it sets no temperature. No other stage sets one. None here sends none for
# intake either.
PROFILE_TEMPERATURE: float | None = 0.0
# How a temperature reaches the API depends on the SDK installed. anthropic 0.x takes `temperature` as an
# argument. anthropic 1.x and 2.x have no such argument, and the API version 2.x sends by default (2026-10-21)
# rejects `temperature` on every model. On those SDKs the value goes in the request body, and that one call
# is sent on the API version that still accepts it. Only calls that set a temperature are affected. Newer
# models reject a temperature on every API version; `_call` then sends the call again without one, once, and
# no later call sets one (the log line says so: the first live run shows whether the temperature is accepted).
SAMPLING_API_VERSION = "2023-06-01"
_SDK_TAKES_TEMPERATURE = "temperature" in inspect.signature(AsyncMessages.stream).parameters


def sampling_params(temperature: float) -> dict[str, Any]:
    """The request parameters that send `temperature` with the SDK installed (see SAMPLING_API_VERSION)."""
    if _SDK_TAKES_TEMPERATURE:
        return {"temperature": temperature}
    return {
        "extra_headers": {"anthropic-version": SAMPLING_API_VERSION},
        "extra_body": {"temperature": temperature},
    }


# How the progress line names what is poured. A concept that serves alcohol without saying what reads plainly.
ALCOHOL_WORDS = {"beer_wine": "beer & wine", "full_liquor": "full bar"}
ALCOHOL_NOT_STATED = "alcohol: not stated"
# A preview entry for a permit the catalog leaves undetermined.
NOT_DETERMINED_PREVIEW = "Not determined: applies if {condition}. The description does not say {missing}."

DISCLAIMERS = [
    f"{app_settings.APP_NAME} is operational guidance, not legal advice. Confirm every requirement, fee and timeline with the issuing agency before relying on it.",
    "Items marked 'Estimated' were not verified against the agency page at the time of generation.",
    "Timelines assume complete applications; agency backlogs, protests and corrections can extend them.",
]


class StageError(RuntimeError):
    """The model did not produce a valid structured result for a stage."""


class NotHospitalityError(ValueError):
    pass


@dataclass
class RunnerEvent:
    type: str  # stage | tool | narrative | needs_clarification | requirements | plan | error
    data: dict[str, Any] = field(default_factory=dict)


EventSink = Callable[[RunnerEvent], Awaitable[None]]


@dataclass
class RunInput:
    description: str
    target_open_date: str | None = None
    prior_profile: BusinessProfile | None = None
    clarification_questions: list[ClarifyingQuestion] = field(default_factory=list)
    clarification_answers: dict[str, Any] = field(default_factory=dict)
    profile_overrides: dict[str, Any] = field(default_factory=dict)
    preview_only: bool = False
    allow_clarification: bool = True


@dataclass
class RequirementsOutcome:
    profile: BusinessProfile
    permits: list[CatalogPermit]
    why_required: dict[str, str]
    priorities: dict[str, str]
    city_supported: bool
    jurisdiction: PlanJurisdiction
    unsupported_city_note: str | None
    notes: str
    # Permits whose rule depends on a fact the profile does not give (what alcohol is served): never steps, never
    # picked; the plan names them with the condition under which each applies (`undetermined_note`).
    undetermined: list[CatalogPermit] = field(default_factory=list)
    undetermined_note: str | None = None


@dataclass
class _Submit(Generic[T]):
    name: str
    model: type[T]
    description: str

    def to_anthropic(self) -> ToolParam:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": json_schema_for(self.model),
        }


SUBMIT_TRIAGE = _Submit(
    "submit_triage_result", TriageResult, "Submit the triage decision. Required to finish."
)
SUBMIT_INTAKE = _Submit(
    "submit_intake_result",
    IntakeResult,
    "Submit the structured BusinessProfile (and any clarifying questions). Required to finish.",
)
SUBMIT_REQUIREMENTS = _Submit(
    "submit_requirements_result",
    RequirementsResult,
    "Submit the final list of required permits with justifications. Required to finish.",
)
SUBMIT_TIMELINE = _Submit(
    "submit_timeline_result",
    TimelineNarrative,
    "Submit the week-by-week narrative and sequencing rationale. Required to finish.",
)
SUBMIT_BLOCKER = _Submit(
    "submit_blocker_result",
    BlockerResult,
    "Submit the executive summary and the ranked stall risks. Required to finish.",
)


def _text_blocks(message: Message) -> str:
    return "".join(getattr(b, "text", "") for b in message.content if b.type == "text")


class AgentRunner:
    # The intake stage's instructions and submit tool. The memo (MemoRunner) has its own: it may record only
    # stated facts, each with a quote (app.memo.stated); the checklist (/v1/plans) keeps these.
    intake_prompt: str = prompts.INTAKE
    intake_submit: _Submit[Any] = SUBMIT_INTAKE

    def __init__(
        self,
        client: AsyncAnthropic,
        catalog: Catalog,
        settings: Settings,
        *,
        today: dt.date | None = None,
    ) -> None:
        self.client = client
        self.catalog = catalog
        self.settings = settings
        self.today = today or dt.date.today()
        self.model_main = settings.ANTHROPIC_MODEL_MAIN
        self.model_triage = settings.ANTHROPIC_MODEL_TRIAGE
        self.max_turns = settings.ANTHROPIC_MAX_TOOL_TURNS
        self.model_versions: dict[str, str] = {}
        # False once the API has rejected a call that set a temperature: no later call of this runner sets one
        self._temperature_accepted = True

    # ------------------------------------------------------------------ public entry point
    async def run(self, inp: RunInput, emit: EventSink) -> AsyncIterator[RunnerEvent]:
        """Run the chain, pushing progress to `emit`; yields the terminal event(s)."""
        try:
            # 1. triage (skipped on clarification / rerun: the description was already accepted)
            city_hint: str | None = None
            state_hint: str | None = None
            if inp.prior_profile is None:
                await emit(
                    RunnerEvent(
                        "stage",
                        {"stage": "triage", "status": "started", "message": prompts.STAGE_MESSAGES["triage"]},
                    )
                )
                triage = await self.triage(inp.description)
                await emit(
                    RunnerEvent(
                        "stage",
                        {
                            "stage": "triage",
                            "status": "completed",
                            "message": "Looks like a hospitality business.",
                        },
                    )
                )
                if not triage.is_hospitality_business:
                    raise NotHospitalityError(
                        triage.reject_reason
                        or "That does not look like a restaurant, bar, cafe, food truck or hotel."
                    )
                city_hint, state_hint = triage.city_guess, triage.state_guess
            else:
                city_hint, state_hint = inp.prior_profile.city_name, inp.prior_profile.state

            # 2. intake
            await emit(
                RunnerEvent(
                    "stage",
                    {"stage": "intake", "status": "started", "message": prompts.STAGE_MESSAGES["intake"]},
                )
            )
            intake = await self.intake(inp, city_hint, state_hint)
            profile = self._finalize_profile(intake.profile, inp)
            set_span_attributes(
                city=profile.city_slug or profile.city_name or "unknown", business_type=profile.business_type
            )
            if (
                intake.needs_clarification
                and intake.questions
                and inp.allow_clarification
                and not inp.clarification_answers
            ):
                await emit(
                    RunnerEvent(
                        "stage",
                        {
                            "stage": "intake",
                            "status": "completed",
                            "message": "I have a couple of quick questions.",
                        },
                    )
                )
                yield RunnerEvent(
                    "needs_clarification",
                    {
                        "questions": [q.model_dump() for q in intake.questions],
                        "profile": profile.model_dump(),
                    },
                )
                return
            await emit(
                RunnerEvent(
                    "stage",
                    {
                        "stage": "intake",
                        "status": "completed",
                        "message": f"Profile ready: {self._describe(profile)}",
                    },
                )
            )

            # 3. requirements
            city_jur = self.catalog.city(profile.city_slug)
            where = city_jur.name if city_jur is not None else (profile.state or "state and federal")
            await emit(
                RunnerEvent(
                    "stage",
                    {
                        "stage": "requirements",
                        "status": "started",
                        "message": prompts.STAGE_MESSAGES["requirements"].format(where=where),
                    },
                )
            )
            req = await self.requirements(profile, emit)
            await emit(
                RunnerEvent(
                    "stage",
                    {
                        "stage": "requirements",
                        "status": "completed",
                        "message": f"{len(req.permits)} permits and licenses identified.",
                    },
                )
            )
            if inp.preview_only:
                yield RunnerEvent("requirements", {"outcome": req})
                return

            # 4. timeline (deterministic schedule + narrative)
            await emit(
                RunnerEvent(
                    "stage",
                    {
                        "stage": "timeline",
                        "status": "started",
                        "message": prompts.STAGE_MESSAGES["timeline"].format(n=len(req.permits)),
                    },
                )
            )
            schedule, fees = self.compute_schedule(
                req.permits, inp.target_open_date or profile.target_open_date
            )
            narrative = await self.timeline(req, schedule, fees, emit)
            await emit(
                RunnerEvent(
                    "stage",
                    {
                        "stage": "timeline",
                        "status": "completed",
                        "message": f"Critical path is {len(schedule.critical_path)} steps; realistic opening {schedule.projected_open_date}.",
                    },
                )
            )

            # 5. blockers (streams narrative)
            await emit(
                RunnerEvent(
                    "stage",
                    {"stage": "blocker", "status": "started", "message": prompts.STAGE_MESSAGES["blocker"]},
                )
            )
            link_checks = await self.verify_links(req.permits, emit)
            blockers = await self.blocker(req, schedule, fees, narrative, link_checks, emit)
            await emit(
                RunnerEvent(
                    "stage",
                    {
                        "stage": "blocker",
                        "status": "completed",
                        "message": f"{len(blockers.blockers)} stall risks scored.",
                    },
                )
            )

            # 6. finalize
            await emit(
                RunnerEvent(
                    "stage",
                    {"stage": "finalize", "status": "started", "message": prompts.STAGE_MESSAGES["finalize"]},
                )
            )
            plan = self.assemble_plan(req, schedule, fees, narrative, blockers, link_checks)
            await emit(
                RunnerEvent("stage", {"stage": "finalize", "status": "completed", "message": "Plan ready."})
            )
            yield RunnerEvent("plan", {"plan": plan, "profile": profile})
        except NotHospitalityError as exc:
            yield RunnerEvent("error", {"code": "not_hospitality", "message": str(exc)})
        except (StageError, DependencyError) as exc:
            log.exception("plan generation failed")
            yield RunnerEvent("error", {"code": "generation_failed", "message": str(exc)})

    # ------------------------------------------------------------------ stages
    @neatlogs.span(kind="AGENT", name="agent.triage")
    async def triage(self, description: str) -> TriageResult:
        system = [{"type": "text", "text": prompts.TRIAGE}]
        user = f"Today is {self.today.isoformat()}.\n\nUSER DESCRIPTION:\n<<<\n{description.strip()}\n>>>"
        result = await self._run_stage(
            stage="triage",
            model=self.model_triage,
            system=system,
            user=user,
            tools=[],
            submit=SUBMIT_TRIAGE,
            max_turns=2,
            emit=None,
        )
        return result

    @neatlogs.span(kind="AGENT", name="agent.intake")
    async def intake(self, inp: RunInput, city_hint: str | None, state_hint: str | None) -> IntakeResult:
        slug_hint = self.catalog.resolve_city(city_hint) if city_hint else None
        prior_slug = inp.prior_profile.city_slug if inp.prior_profile else None
        system = self._system(
            self.intake_prompt,
            state_hint or (inp.prior_profile.state if inp.prior_profile else None),
            slug_hint or prior_slug,
        )
        parts = [
            f"Today is {self.today.isoformat()}.",
            f"USER DESCRIPTION:\n<<<\n{inp.description.strip()}\n>>>",
        ]
        if inp.target_open_date:
            parts.append(f"Target open date given separately: {inp.target_open_date}")
        if slug_hint:
            parts.append(f"Hint: the city text matches the supported catalog city slug '{slug_hint}'.")
        elif city_hint:
            parts.append(
                f"Hint: the city '{city_hint}' did not match a supported catalog city; set city_slug=null and fill state if known."
            )
        if inp.prior_profile is not None:
            parts.append(
                "PREVIOUS PROFILE (start from this, apply the changes below):\n"
                + inp.prior_profile.model_dump_json(indent=2)
            )
        if inp.clarification_questions and inp.clarification_answers:
            qa = [
                {"question": q.question, "maps_to": q.maps_to, "answer": inp.clarification_answers.get(q.id)}
                for q in inp.clarification_questions
            ]
            parts.append(
                "CLARIFICATION ANSWERS (apply these; do not ask again):\n" + json.dumps(qa, indent=2)
            )
        if inp.profile_overrides:
            parts.append(
                "OPERATOR OVERRIDES (these win over everything else):\n"
                + json.dumps(inp.profile_overrides, indent=2)
            )
        result = await self._run_stage(
            stage="intake",
            model=self.model_main,
            system=system,
            user="\n\n".join(parts),
            tools=[LOOKUP_PERMIT_CATALOG],
            submit=self.intake_submit,
            emit=None,
            temperature=PROFILE_TEMPERATURE,
        )
        return cast(IntakeResult, result)

    @neatlogs.span(kind="AGENT", name="agent.requirements")
    async def requirements(self, profile: BusinessProfile, emit: EventSink) -> RequirementsOutcome:
        system = self._system(prompts.REQUIREMENTS, profile.state, profile.city_slug)
        user = (
            f"Today is {self.today.isoformat()}.\n\nBUSINESS PROFILE:\n{profile.model_dump_json(indent=2)}\n\n"
            "Call lookup_permit_catalog with this exact profile first, then submit the requirements."
        )
        result = await self._run_stage(
            stage="requirements",
            model=self.model_main,
            system=system,
            user=user,
            tools=[LOOKUP_PERMIT_CATALOG, CHECK_DEPENDENCIES],
            submit=SUBMIT_REQUIREMENTS,
            emit=emit,
        )
        return self._reconcile_requirements(profile, result)

    @neatlogs.span(kind="AGENT", name="agent.timeline")
    async def timeline(
        self, req: RequirementsOutcome, schedule: Schedule, fees: FeeSummary, emit: EventSink
    ) -> TimelineNarrative:
        system = self._system(prompts.TIMELINE, req.profile.state, req.profile.city_slug)
        steps_brief = [
            {
                "id": t.id,
                "name": t.name,
                "track": t.track,
                "order": t.order,
                "start_day": t.earliest_start,
                "finish_day": t.earliest_finish,
                "slack_days": t.slack,
                "critical": t.on_critical_path,
                "prerequisites": t.prerequisites,
                "why_required": req.why_required.get(t.id, ""),
            }
            for t in schedule.tasks
        ]
        narrate = weeks_to_narrate(schedule.weeks)
        user = (
            f"Today is {self.today.isoformat()}.\n\nBUSINESS PROFILE:\n{req.profile.model_dump_json(indent=2)}\n\n"
            f"DETERMINISTIC SCHEDULE (from estimate_timeline):\n"
            f"start_date={schedule.start_date} target_open_date={schedule.target_open_date} "
            f"projected_open_date={schedule.projected_open_date} optimistic_open_date={schedule.optimistic_open_date} "
            f"total_days={schedule.total_days_min}-{schedule.total_days_max} feasible={schedule.feasible} days_short={schedule.days_short}\n"
            f"critical_path={schedule.critical_path}\n"
            f"weeks_in_grid={len(schedule.weeks)}\n"
            f"WEEKS TO NARRATE (one entry per week_number listed; quiet weeks are auto-filled): {narrate}\n"
            f"STEPS:\n{json.dumps(steps_brief, indent=1)}\n\n"
            f"WEEK GRID:\n{json.dumps(schedule.weeks, indent=1)}\n\n"
            f"FEES: total ${fees.total_min:,.0f}–${fees.total_max:,.0f}\n\n"
            "Submit the timeline narrative."
        )
        result = await self._run_stage(
            stage="timeline",
            model=self.model_main,
            system=system,
            user=user,
            tools=[ESTIMATE_TIMELINE, CHECK_DEPENDENCIES, GET_FEE_TOTAL],
            submit=SUBMIT_TIMELINE,
            emit=emit,
            max_tokens=16384,
        )
        return result

    @neatlogs.span(kind="AGENT", name="agent.blocker")
    async def blocker(
        self,
        req: RequirementsOutcome,
        schedule: Schedule,
        fees: FeeSummary,
        narrative: TimelineNarrative,
        link_checks: dict[str, VerifyOutput],
        emit: EventSink,
    ) -> BlockerResult:
        system = self._system(prompts.BLOCKER, req.profile.state, req.profile.city_slug)
        steps = [
            {
                "id": p.id,
                "name": p.name,
                "agency": p.issuing_agency,
                "confidence": p.confidence,
                "days": [int(p.typical_timeline_days.min), int(p.typical_timeline_days.max)],
                "stall_risk": p.stall_risk,
                "why_required": req.why_required.get(p.id, ""),
                "link_status": link_checks[p.id].status if p.id in link_checks else "unchecked",
                "critical": any(t.id == p.id and t.on_critical_path for t in schedule.tasks),
            }
            for p in req.permits
        ]
        # the permits the checklist could not determine: the narrative says so, and does not pick one
        undetermined = (
            f"NOT DETERMINED (say so plainly; do not pick one): {req.undetermined_note}\n"
            if req.undetermined_note
            else ""
        )
        user = (
            f"Today is {self.today.isoformat()}.\n\nBUSINESS PROFILE:\n{req.profile.model_dump_json(indent=2)}\n\n"
            f"SCHEDULE: projected opening {schedule.projected_open_date} (optimistic {schedule.optimistic_open_date}); "
            f"target {schedule.target_open_date or 'none'}; feasible={schedule.feasible}; days_short={schedule.days_short}; "
            f"critical_path={schedule.critical_path}\n"
            f"FEES: ${fees.total_min:,.0f}–${fees.total_max:,.0f}\n"
            f"FEASIBILITY (from timeline stage): {narrative.feasibility_assessment}\n"
            f"{undetermined}\n"
            f"STEPS WITH STALL RISKS AND LINK CHECKS:\n{json.dumps(steps, indent=1)}\n\n"
            "Write the narrative, then submit the blockers."
        )
        result = await self._run_stage(
            stage="blocker",
            model=self.model_main,
            system=system,
            user=user,
            tools=[WEB_VERIFY],
            submit=SUBMIT_BLOCKER,
            emit=emit,
            stream=True,
        )
        return result

    # ------------------------------------------------------------------ deterministic pieces
    def compute_schedule(
        self, permits: list[CatalogPermit], target_open_date: str | None
    ) -> tuple[Schedule, FeeSummary]:
        target = None
        if target_open_date:
            try:
                target = dt.date.fromisoformat(target_open_date)
            except ValueError:
                target = None
        schedule = estimate_timeline(tasks_from_permits(permits), self.today, target)
        return schedule, fee_summary(permits)

    async def verify_links(self, permits: list[CatalogPermit], emit: EventSink) -> dict[str, VerifyOutput]:
        if not self.settings.WEB_VERIFY_ENABLED:
            return {}
        await emit(
            RunnerEvent(
                "tool",
                {
                    "stage": "blocker",
                    "tool": "web_verify",
                    "status": "started",
                    "message": f"Checking {len(permits)} application links…",
                },
            )
        )
        sem = asyncio.Semaphore(6)

        async def one(p: CatalogPermit) -> VerifyOutput:
            async with sem:
                return await verify_url(p.id, p.application_url)

        results = await asyncio.gather(*(one(p) for p in permits), return_exceptions=True)
        out: dict[str, VerifyOutput] = {}
        for p, r in zip(permits, results, strict=True):
            if isinstance(r, VerifyOutput):
                out[p.id] = r
        dead = sum(1 for r in out.values() if r.status == "dead")
        await emit(
            RunnerEvent(
                "tool",
                {
                    "stage": "blocker",
                    "tool": "web_verify",
                    "status": "completed",
                    "message": f"{len(out) - dead} links live, {dead} flagged.",
                },
            )
        )
        return out

    def _finalize_profile(self, profile: BusinessProfile, inp: RunInput) -> BusinessProfile:
        return self._merge_profile(profile, inp).normalized()

    def _merge_profile(self, profile: BusinessProfile, inp: RunInput) -> BusinessProfile:
        """The intake profile with the clarification answers, the overrides and the city applied, as given:
        `BusinessProfile.normalized()` is applied by the caller (it never guesses what is poured: "unknown")."""
        data = profile.model_dump()
        # facts only the applicant gives (the intake questions): whatever the model put there is dropped
        for key in MODEL_MAY_NOT_SET:
            data[key] = BusinessProfile.model_fields[key].get_default(call_default_factory=True)
        # clarification answers and operator overrides win over the model's reading
        for q in inp.clarification_questions:
            if q.id in inp.clarification_answers:
                data[q.maps_to] = _coerce(
                    inp.clarification_answers[q.id], BusinessProfile.model_fields[q.maps_to].annotation
                )
        for key, value in inp.profile_overrides.items():
            if key in BusinessProfile.model_fields:
                data[key] = value
        if inp.target_open_date:
            data["target_open_date"] = inp.target_open_date
        # the catalog decides what counts as a supported city
        resolved = self.catalog.resolve_city(data.get("city_name")) or self.catalog.resolve_city(
            data.get("neighborhood")
        )
        slug = data.get("city_slug")
        if slug and self.catalog.city(slug) is None:
            slug = None
        data["city_slug"] = slug or resolved
        city = self.catalog.city(data["city_slug"])
        if city is not None:
            data["state"] = city.state
        try:
            return BusinessProfile.model_validate(data)
        except ValidationError as exc:
            raise StageError(f"intake produced an invalid profile: {exc}") from exc

    def _reconcile_requirements(
        self, profile: BusinessProfile, result: RequirementsResult
    ) -> RequirementsOutcome:
        """Catalog rules are the floor; the agent adds justifications and may add (not remove) permits. A permit
        the catalog leaves undetermined (it depends on a fact the profile does not give) is never added: that
        would pick one of the possible licences; the plan names them instead."""
        prof = profile.model_dump()
        found = lookup(profile)
        jur = self.catalog.jurisdiction_for(prof.get("state"), prof.get("city_slug"))
        allowed = {p.id: p for p in jur.permits}
        chosen: dict[str, CatalogPermit] = {m.id: allowed[m.id] for m in found.matches if m.id in allowed}
        undetermined = [allowed[u.id] for u in found.undetermined if u.id in allowed]
        not_addable = {p.id for p in undetermined}
        why: dict[str, str] = {}
        priorities: dict[str, str] = {}
        for rp in result.permits:
            if rp.permit_id in allowed and rp.permit_id not in not_addable:
                chosen.setdefault(rp.permit_id, allowed[rp.permit_id])
                why[rp.permit_id] = rp.why_required
                priorities[rp.permit_id] = rp.priority
        for pid, p in chosen.items():
            why.setdefault(pid, p.notes.split(". ")[0].rstrip(".") + ".")
            priorities.setdefault(pid, "standard")
        permits = sorted(chosen.values(), key=lambda p: p.id)
        return RequirementsOutcome(
            profile=profile,
            permits=permits,
            why_required=why,
            priorities=priorities,
            city_supported=jur.supported,
            jurisdiction=PlanJurisdiction(
                city_name=jur.city_name, city_slug=jur.city_slug, state=jur.state, county=jur.county
            ),
            unsupported_city_note=result.unsupported_city_note if not jur.supported else None,
            notes=result.notes,
            undetermined=undetermined,
            undetermined_note=found.undetermined_note,
        )

    def assemble_plan(
        self,
        req: RequirementsOutcome,
        schedule: Schedule,
        fees: FeeSummary,
        narrative: TimelineNarrative,
        blockers: BlockerResult,
        link_checks: dict[str, VerifyOutput],
    ) -> Plan:
        by_id = {p.id: p for p in req.permits}
        steps: list[PlanStep] = []
        for t in schedule.tasks:
            p = by_id[t.id]
            steps.append(
                PlanStep(
                    id=p.id,
                    name=p.name,
                    category=p.category,
                    issuing_agency=p.issuing_agency,
                    jurisdiction_level=p.jurisdiction_level,
                    application_url=p.application_url,
                    url_status=link_checks[p.id].status if p.id in link_checks else "unchecked",
                    typical_timeline_days=p.typical_timeline_days,
                    fee_range_usd=p.fee_range_usd,
                    prerequisites=t.prerequisites,
                    confidence=p.confidence,
                    notes=p.notes,
                    why_required=req.why_required.get(p.id, ""),
                    stall_risk=p.stall_risk,
                    order=t.order,
                    track=t.track,
                    earliest_start_day=t.earliest_start,
                    earliest_finish_day=t.earliest_finish,
                    latest_start_day=t.latest_start,
                    latest_finish_day=t.latest_finish,
                    slack_days=t.slack,
                    on_critical_path=t.on_critical_path,
                    scheduled_start=t.scheduled_start,
                    scheduled_end=t.scheduled_end,
                )
            )
        by_week = {w.week_number: w for w in narrative.weeks}
        weeks: list[TimelineWeek] = []
        for w in schedule.weeks:
            n = int(w["week_number"])
            nar = by_week.get(n)
            starting = list(w["step_ids_starting"])
            due = list(w["step_ids_due"])
            focus = (
                nar.focus
                if nar
                else (
                    f"File: {', '.join(by_id[s].name for s in starting[:2])}"
                    if starting
                    else "Monitor open applications"
                )
            )
            actions = (
                nar.actions
                if nar
                else [f"Submit {by_id[s].name}" for s in starting]
                + [f"Follow up on {by_id[s].name}" for s in due]
            )
            weeks.append(
                TimelineWeek(
                    week_number=n,
                    start_date=str(w["start_date"]),
                    end_date=str(w["end_date"]),
                    focus=focus,
                    actions=actions or ["Chase outstanding approvals."],
                    step_ids_starting=starting,
                    step_ids_due=due,
                )
            )
        timeline = Timeline(
            start_date=schedule.start_date,
            target_open_date=schedule.target_open_date,
            projected_open_date=schedule.projected_open_date,
            optimistic_open_date=schedule.optimistic_open_date,
            total_days_min=schedule.total_days_min,
            total_days_max=schedule.total_days_max,
            feasible=schedule.feasible,
            days_short=schedule.days_short,
            critical_path=schedule.critical_path,
            parallel_tracks=[
                ParallelTrack(name=str(t["name"]), step_ids=list(t["step_ids"]))
                for t in schedule.parallel_tracks
            ],
            weeks=weeks,
            sequencing_rationale=narrative.sequencing_rationale,
        )
        valid_ids = set(by_id)
        cleaned_blockers = [
            Blocker(
                **{**b.model_dump(), "related_step_ids": [s for s in b.related_step_ids if s in valid_ids]}
            )
            for b in blockers.blockers
        ]
        # what the checklist could not determine comes first: it is about this business, not a general caveat
        disclaimers = [*([req.undetermined_note] if req.undetermined_note else []), *DISCLAIMERS]
        if req.notes:
            disclaimers.append(req.notes)
        return Plan(
            summary=blockers.executive_summary,
            city_supported=req.city_supported,
            jurisdiction=req.jurisdiction,
            steps=steps,
            timeline=timeline,
            fees=fees,
            blockers=cleaned_blockers,
            unsupported_city_note=req.unsupported_city_note,
            disclaimers=disclaimers,
            generated_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            model_versions=dict(self.model_versions),
        )

    def preview_permits(self, req: RequirementsOutcome) -> list[PermitPreview]:
        """The permits that apply, then the undetermined ones (marked "Not determined", with the condition under
        which each applies), so the preview never drops one silently. `PreviewResult.permit_count` counts the
        first kind only."""
        conditions = {u.id: (u.applies_if, u.missing) for u in lookup(req.profile).undetermined}
        undetermined = [
            PermitPreview(
                id=p.id,
                name=p.name,
                category=p.category,
                issuing_agency=p.issuing_agency,
                jurisdiction_level=p.jurisdiction_level,
                confidence=p.confidence,
                typical_timeline_days=p.typical_timeline_days,
                fee_range_usd=p.fee_range_usd,
                why_required=NOT_DETERMINED_PREVIEW.format(
                    condition=conditions[p.id][0], missing=" and ".join(conditions[p.id][1])
                ),
            )
            for p in req.undetermined
            if p.id in conditions
        ]
        return [
            PermitPreview(
                id=p.id,
                name=p.name,
                category=p.category,
                issuing_agency=p.issuing_agency,
                jurisdiction_level=p.jurisdiction_level,
                confidence=p.confidence,
                typical_timeline_days=p.typical_timeline_days,
                fee_range_usd=p.fee_range_usd,
                why_required=req.why_required.get(p.id, ""),
            )
            for p in req.permits
        ] + undetermined

    # ------------------------------------------------------------------ the tool-use loop
    def _system(
        self, stage_instructions: str, state: str | None, city_slug: str | None
    ) -> list[dict[str, Any]]:
        """[cached: preamble + catalog context] + [stage instructions]."""
        return [
            {
                "type": "text",
                "text": prompts.SHARED_PREAMBLE + self.catalog.context_text(state, city_slug),
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": stage_instructions},
        ]

    async def _run_stage(
        self,
        *,
        stage: str,
        model: str,
        system: list[dict[str, Any]],
        user: str,
        tools: list[ToolSpec],
        submit: _Submit[T],
        emit: EventSink | None,
        stream: bool = False,
        max_turns: int | None = None,
        max_tokens: int = 8192,
        submit_context: dict[str, Any] | None = None,
        temperature: float | None = None,
    ) -> T:
        """One stage: the tool-use loop, ended by a valid call of the submit tool. `temperature` is sent on
        every call of the stage when given; None (every stage but intake) sends none."""
        self.model_versions[stage] = model
        tool_params: list[ToolParam] = [t.to_anthropic() for t in tools]  # type: ignore[misc]
        tool_params.append(submit.to_anthropic())
        by_name = {t.name: t for t in tools}
        messages: list[MessageParam] = [{"role": "user", "content": user}]
        turns = max_turns or self.max_turns
        force_next = False
        validation_failures = 0

        for turn in range(turns):
            force = force_next or turn == turns - 1
            tool_choice: dict[str, Any]
            if force and self.settings.ANTHROPIC_FORCE_TOOL_CHOICE:
                tool_choice = {"type": "tool", "name": submit.name}
            else:
                tool_choice = {"type": "auto"}
            response = await self._call(
                model, system, messages, tool_params, tool_choice, stream, emit, max_tokens, temperature
            )
            if response.stop_reason == "refusal":
                raise StageError(f"{stage}: the model declined this request")
            if response.stop_reason == "max_tokens":
                raise StageError(f"{stage}: response truncated (max_tokens)")
            messages.append({"role": "assistant", "content": response.content})
            tool_uses = [b for b in response.content if isinstance(b, ToolUseBlock)]
            submit_block = next((b for b in tool_uses if b.name == submit.name), None)
            if submit_block is not None:
                try:
                    result = submit.model.model_validate(submit_block.input, context=submit_context)
                    set_span_attributes(**{f"stage.{stage}.turns": turn + 1})
                    return result
                except ValidationError as exc:
                    validation_failures += 1
                    if validation_failures > 2:
                        raise StageError(
                            f"{stage}: structured output failed validation 3 times: {exc.errors()[:3]}"
                        ) from exc
                    # tell the model exactly what was wrong and make it resubmit
                    results = [
                        {
                            "type": "tool_result",
                            "tool_use_id": b.id,
                            "is_error": True,
                            "content": json.dumps(
                                {"error": "validation_error", "details": exc.errors(include_url=False)},
                                default=str,
                            )
                            if b.id == submit_block.id
                            else "skipped: submit the corrected result",
                        }
                        for b in tool_uses
                    ]
                    messages.append(cast(MessageParam, {"role": "user", "content": results}))
                    force_next = True
                    continue
            if tool_uses:
                results = await self._execute_tools(stage, tool_uses, by_name, emit)
                messages.append(cast(MessageParam, {"role": "user", "content": results}))
                continue
            # end_turn without a submit: demand it on the next turn
            messages.append(
                {"role": "user", "content": f"Now call {submit.name} with your complete final result."}
            )
            force_next = True
        raise StageError(f"{stage}: no structured result after {turns} turns")

    async def _call(
        self,
        model: str,
        system: list[dict[str, Any]],
        messages: list[MessageParam],
        tools: list[ToolParam],
        tool_choice: dict[str, Any],
        stream: bool,
        emit: EventSink | None,
        max_tokens: int = 8192,
        temperature: float | None = None,
    ) -> Message:
        """One Messages API call. Always streamed (long structured outputs would otherwise hit HTTP
        timeouts); text deltas are forwarded to the UI only when `stream=True` (the checklist's blocker
        stage; no memo stage forwards text). A `temperature` is sent only when one is given. If the API
        rejects that call (400), the same call is sent once more without the temperature, so a model or an
        API version that does not take one cannot fail a run."""
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
        }
        if temperature is not None and self._temperature_accepted:
            try:
                return await self._stream(params | sampling_params(temperature), stream, emit)
            except BadRequestError as exc:
                # The model or the API version does not take a temperature. A 400 comes back before anything
                # is streamed, so the same call is sent once more without it, and no later call sets one. A
                # 400 that has nothing to do with the temperature fails the same way on the second send.
                self._temperature_accepted = False
                log.warning(
                    "the API rejected a call that set a temperature (%s); sent again without one", exc
                )
        return await self._stream(params, stream, emit)

    async def _stream(self, params: dict[str, Any], stream: bool, emit: EventSink | None) -> Message:
        """One streamed Messages API request with these parameters; the final message."""
        async with self.client.messages.stream(**params) as s:
            async for event in s:
                if (
                    stream
                    and emit is not None
                    and event.type == "content_block_delta"
                    and event.delta.type == "text_delta"
                ):
                    await emit(RunnerEvent("narrative", {"delta": event.delta.text}))
            return await s.get_final_message()

    async def _execute_tools(
        self, stage: str, tool_uses: list[ToolUseBlock], by_name: dict[str, ToolSpec], emit: EventSink | None
    ) -> list[dict[str, Any]]:
        async def one(block: ToolUseBlock) -> dict[str, Any]:
            spec = by_name.get(block.name)
            if spec is None:
                return {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "is_error": True,
                    "content": json.dumps(
                        {"error": "unknown_tool", "message": f"No tool named {block.name}"}
                    ),
                }
            if emit is not None:
                await emit(
                    RunnerEvent(
                        "tool",
                        {
                            "stage": stage,
                            "tool": spec.name,
                            "status": "started",
                            "message": _tool_message(spec.name, block.input),
                        },
                    )
                )
            content, is_error = await spec.run(block.input if isinstance(block.input, dict) else {})
            if emit is not None:
                await emit(
                    RunnerEvent(
                        "tool",
                        {
                            "stage": stage,
                            "tool": spec.name,
                            "status": "completed",
                            "message": "error" if is_error else "done",
                        },
                    )
                )
            out: dict[str, Any] = {"type": "tool_result", "tool_use_id": block.id, "content": content}
            if is_error:
                out["is_error"] = True
            return out

        return list(await asyncio.gather(*(one(b) for b in tool_uses)))

    @staticmethod
    def _describe(p: BusinessProfile) -> str:
        bits = [p.business_type.replace("_", " ")]
        if p.seats:
            bits.append(f"{p.seats} seats")
        if p.serves_alcohol or p.alcohol_type != "none":
            bits.append(ALCOHOL_WORDS.get(p.alcohol_type, ALCOHOL_NOT_STATED))
        if p.live_entertainment:
            bits.append("live music")
        where = p.city_name or p.state or "unknown city"
        return f"{', '.join(bits)} in {where}."


def weeks_to_narrate(weeks: list[dict[str, Any]], cap: int = 36) -> list[int]:
    """Weeks worth a written narrative: anything with a filing or approval, plus the first and last week.
    Long horizons are thinned evenly so the structured output stays well under the token budget."""
    if not weeks:
        return []
    active = [int(w["week_number"]) for w in weeks if w["step_ids_starting"] or w["step_ids_due"]]
    chosen = sorted({1, int(weeks[-1]["week_number"]), *active})
    if len(chosen) <= cap:
        return chosen
    step = len(chosen) / cap
    return sorted({chosen[int(i * step)] for i in range(cap)} | {chosen[0], chosen[-1]})


def _tool_message(name: str, inp: Any) -> str:
    if name == "lookup_permit_catalog":
        return "Querying the permit catalog…"
    if name == "estimate_timeline":
        n = len(inp.get("permit_ids", [])) if isinstance(inp, dict) else 0
        return f"Scheduling {n} permits…"
    if name == "check_dependencies":
        return "Validating prerequisite chains…"
    if name == "get_fee_total":
        return "Totalling fees…"
    if name == "web_verify":
        pid = inp.get("permit_id", "") if isinstance(inp, dict) else ""
        return f"Checking application link for {pid}…"
    return f"Running {name}…"


def _coerce(value: Any, annotation: Any) -> Any:
    """Coerce a clarification answer (string from a form) into the profile field's type."""
    text = str(value).strip().lower() if not isinstance(value, (bool, int, float)) else value
    if annotation is bool or str(annotation) in {"<class 'bool'>"}:
        if isinstance(text, bool):
            return text
        return str(text) in {"true", "yes", "y", "1", "on"}
    if isinstance(text, str) and text.lstrip("-").isdigit():
        return int(text)
    if isinstance(value, str):
        return value.strip()
    return value
