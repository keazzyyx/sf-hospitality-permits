"""Mocked end-to-end runs of the handoff chain (no network)."""

from __future__ import annotations

import inspect
import json
from typing import Any

import pytest
from anthropic.resources.messages import AsyncMessages

from app.agents.runner import (
    PROFILE_TEMPERATURE,
    SAMPLING_API_VERSION,
    AgentRunner,
    RunInput,
    RunnerEvent,
    StageError,
    sampling_params,
)
from app.catalog.loader import get_catalog
from app.core.config import settings
from app.models.plan import BlockerResult, Plan
from app.tools.base import json_schema_for
from tests.conftest import TODAY
from tests.fakes import FakeAnthropic, ScriptedModel
from tests.memo_fakes import sent_temperature

DESCRIPTION = "Opening a 40-seat wine bar in SF Mission, small kitchen, serve until 1am, maybe live music"


async def run_chain(script: ScriptedModel, inp: RunInput) -> tuple[list[RunnerEvent], list[RunnerEvent]]:
    runner = AgentRunner(FakeAnthropic(script), get_catalog(), settings, today=TODAY)  # type: ignore[arg-type]
    progress: list[RunnerEvent] = []

    async def emit(ev: RunnerEvent) -> None:
        progress.append(ev)

    terminal = [ev async for ev in runner.run(inp, emit)]
    return progress, terminal


@pytest.mark.anyio
async def test_full_chain_produces_valid_plan() -> None:
    script = ScriptedModel()
    progress, terminal = await run_chain(
        script, RunInput(description=DESCRIPTION, target_open_date="2027-03-01")
    )
    assert [e.type for e in terminal] == ["plan"]
    plan: Plan = terminal[0].data["plan"]
    Plan.model_validate(plan.model_dump())  # strictly structured
    ids = {s.id for s in plan.steps}
    assert "sf.conditional_use_authorization" in ids and "sf.not_a_real_permit" not in ids
    assert plan.timeline.critical_path and plan.timeline.feasible is False
    assert plan.timeline.weeks[0].focus == "Week 1 focus"  # narrative merged
    assert all(w.actions for w in plan.timeline.weeks)  # quiet weeks auto-filled
    assert plan.fees.total_max > plan.fees.total_min > 0
    assert plan.blockers[0].related_step_ids == ["sf.conditional_use_authorization"]  # bogus id cleaned
    assert plan.summary.startswith("You are opening")
    assert set(plan.model_versions) == {"triage", "intake", "requirements", "timeline", "blocker"}
    assert plan.model_versions["triage"] == settings.ANTHROPIC_MODEL_TRIAGE
    # the step 'why_required' came from the agent, and critical-path steps are flagged
    cua = next(s for s in plan.steps if s.id == "sf.conditional_use_authorization")
    assert cua.on_critical_path and "required because" in cua.why_required
    # progress events: every stage started+completed, tools reported, narrative streamed
    stages = [(e.data["stage"], e.data["status"]) for e in progress if e.type == "stage"]
    for st in ("triage", "intake", "requirements", "timeline", "blocker", "finalize"):
        assert (st, "started") in stages and (st, "completed") in stages
    assert any(e.type == "tool" and e.data["tool"] == "lookup_permit_catalog" for e in progress)
    narrative = "".join(e.data["delta"] for e in progress if e.type == "narrative")
    assert narrative.startswith("You are opening")


@pytest.mark.anyio
async def test_requests_are_well_formed_for_caching_and_structured_output() -> None:
    script = ScriptedModel()
    await run_chain(script, RunInput(description=DESCRIPTION))
    main_calls = [c for c in script.calls if c["model"] == settings.ANTHROPIC_MODEL_MAIN]
    assert main_calls and all(
        c["system"][0].get("cache_control") == {"type": "ephemeral"} for c in main_calls
    )
    assert all("PERMIT CATALOG" in c["system"][0]["text"] for c in main_calls)
    # system prefix identical across calls within a stage → cache hits
    req_calls = [
        c for c in script.calls if any(t["name"] == "submit_requirements_result" for t in c["tools"])
    ]
    assert len(req_calls) >= 2 and req_calls[0]["system"] == req_calls[1]["system"]
    # the submit tool schema is exactly the Pydantic model's JSON schema
    blocker_call = next(
        c for c in script.calls if any(t["name"] == "submit_blocker_result" for t in c["tools"])
    )
    submit = next(t for t in blocker_call["tools"] if t["name"] == "submit_blocker_result")
    assert submit["input_schema"] == json_schema_for(BlockerResult)
    # triage uses the cheap model and a forced tool_choice on its last allowed turn
    triage_calls = [c for c in script.calls if c["model"] == settings.ANTHROPIC_MODEL_TRIAGE]
    assert triage_calls and triage_calls[0]["tool_choice"] == {"type": "auto"}


@pytest.mark.anyio
async def test_clarification_round_trip() -> None:
    script = ScriptedModel(ask_clarification=True)
    _, terminal = await run_chain(script, RunInput(description=DESCRIPTION))
    assert terminal[0].type == "needs_clarification"
    questions = terminal[0].data["questions"]
    assert len(questions) == 1 and questions[0]["maps_to"] == "live_entertainment"
    # second turn with answers → no further clarification, full plan
    from app.models.profile import BusinessProfile, ClarifyingQuestion

    inp = RunInput(
        description=DESCRIPTION,
        prior_profile=BusinessProfile.model_validate(terminal[0].data["profile"]),
        clarification_questions=[ClarifyingQuestion.model_validate(q) for q in questions],
        clarification_answers={"q1": "no"},
        allow_clarification=False,
    )
    _, terminal2 = await run_chain(ScriptedModel(ask_clarification=True), inp)
    assert terminal2[0].type == "plan"
    profile = terminal2[0].data["profile"]
    assert profile.live_entertainment is False  # the answer overrode the model's profile
    # late-night amplified sound still triggers the POE permit, but the LLP permit never applies
    assert "sf.limited_live_performance_permit" not in {s.id for s in terminal2[0].data["plan"].steps}


@pytest.mark.anyio
async def test_invalid_structured_output_is_retried_with_errors() -> None:
    script = ScriptedModel(invalid_first_blocker_submit=True)
    _, terminal = await run_chain(script, RunInput(description=DESCRIPTION))
    assert terminal[0].type == "plan"
    blocker_calls = [c for c in script.calls if any(t["name"] == "submit_blocker_result" for t in c["tools"])]
    assert len(blocker_calls) == 2
    retry_msg = blocker_calls[1]["messages"][-1]
    assert retry_msg["role"] == "user" and retry_msg["content"][0]["is_error"] is True
    assert "validation_error" in retry_msg["content"][0]["content"]
    assert blocker_calls[1]["tool_choice"] == {"type": "tool", "name": "submit_blocker_result"}


@pytest.mark.anyio
async def test_loop_terminates_when_model_never_submits() -> None:
    script = ScriptedModel(never_submit_stage="requirements")
    _, terminal = await run_chain(script, RunInput(description=DESCRIPTION))
    assert terminal[0].type == "error" and terminal[0].data["code"] == "generation_failed"
    req_calls = [
        c for c in script.calls if any(t["name"] == "submit_requirements_result" for t in c["tools"])
    ]
    assert len(req_calls) == settings.ANTHROPIC_MAX_TOOL_TURNS
    assert req_calls[-1]["tool_choice"] == {"type": "tool", "name": "submit_requirements_result"}
    assert req_calls[1]["messages"][-1]["content"].startswith("Now call submit_requirements_result")


@pytest.mark.anyio
async def test_forced_tool_choice_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ANTHROPIC_FORCE_TOOL_CHOICE", False)
    script = ScriptedModel(never_submit_stage="intake")
    _, terminal = await run_chain(script, RunInput(description=DESCRIPTION))
    assert terminal[0].type == "error"
    assert all(c["tool_choice"] == {"type": "auto"} for c in script.calls)


@pytest.mark.anyio
async def test_preview_only_stops_after_requirements() -> None:
    script = ScriptedModel()
    progress, terminal = await run_chain(script, RunInput(description=DESCRIPTION, preview_only=True))
    assert terminal[0].type == "requirements"
    assert not any(e.type == "stage" and e.data["stage"] == "timeline" for e in progress)
    outcome = terminal[0].data["outcome"]
    assert outcome.city_supported and len(outcome.permits) > 10


@pytest.mark.anyio
async def test_not_hospitality_is_rejected() -> None:
    class Rejecting(ScriptedModel):
        def respond(self, params):  # type: ignore[no-untyped-def]
            from tests.fakes import make_message, tool_use

            return make_message(
                [
                    tool_use(
                        "submit_triage_result",
                        {
                            "is_hospitality_business": False,
                            "language": "en",
                            "city_guess": None,
                            "state_guess": None,
                            "reject_reason": "This describes a software startup.",
                        },
                    )
                ]
            ), []

    _, terminal = await run_chain(
        Rejecting(), RunInput(description="We are building a SaaS for dentists in Ohio")
    )
    assert terminal[0].type == "error" and terminal[0].data["code"] == "not_hospitality"


def test_stage_error_is_runtime_error() -> None:
    assert issubclass(StageError, RuntimeError)


# ---- temperature: 0 for the stage that writes the profile, unset everywhere else ------------------
def stage_of(call: dict[str, Any]) -> str:
    name = next(t["name"] for t in call["tools"] if t["name"].startswith("submit_"))
    return str(name.removeprefix("submit_").removesuffix("_result"))


@pytest.mark.anyio
async def test_intake_runs_at_temperature_zero_and_no_other_stage_sets_one() -> None:
    script = ScriptedModel()
    await run_chain(script, RunInput(description=DESCRIPTION))
    by_stage: dict[str, list[dict[str, Any]]] = {}
    for call in script.calls:
        by_stage.setdefault(stage_of(call), []).append(call)
    assert set(by_stage) == {"triage", "intake", "requirements", "timeline", "blocker"}
    assert PROFILE_TEMPERATURE == 0.0
    # every call of the stage that writes the profile, including the turn after a tool result
    assert len(by_stage["intake"]) >= 2
    assert [sent_temperature(c) for c in by_stage["intake"]] == [0.0] * len(by_stage["intake"])
    # the other stages send no temperature and nothing that comes with one. Triage writes no profile (it
    # accepts or rejects the description), so it is one of them.
    for stage in ("triage", "requirements", "timeline", "blocker"):
        for call in by_stage[stage]:
            assert sent_temperature(call) is None, stage
            assert not {"temperature", "extra_body", "extra_headers"} & set(call), stage


def test_a_temperature_is_sent_the_way_the_installed_sdk_and_api_version_accept_it() -> None:
    """anthropic 2.x has no `temperature` argument and its default API version (2026-10-21) rejects the field
    on every model, so there the value goes in the body and that call is pinned to the version that takes it.
    An older SDK takes the argument directly."""
    params = sampling_params(0.0)
    takes_argument = "temperature" in inspect.signature(AsyncMessages.stream).parameters
    if takes_argument:
        assert params == {"temperature": 0.0}
    else:
        assert params == {
            "extra_headers": {"anthropic-version": "2023-06-01"},
            "extra_body": {"temperature": 0.0},
        }
        assert SAMPLING_API_VERSION == "2023-06-01"
    # whichever it is, the real SDK accepts these parameters: a call that set them would not raise TypeError
    accepted = set(inspect.signature(AsyncMessages.stream).parameters)
    assert set(params) <= accepted


@pytest.mark.anyio
async def test_the_real_sdk_puts_the_temperature_on_the_wire_only_when_asked() -> None:
    """The scripted client accepts any argument, so this builds the request with the real SDK against a
    transport that answers locally (nothing leaves the machine): a call with a temperature carries it in the
    request, on an API version that accepts it; a call without one carries no temperature. A rejected call
    that set a temperature is sent once more without it, and a rejection that has nothing to do with the
    temperature is still raised."""
    import importlib

    import anthropic

    try:
        transport_lib = importlib.import_module("httpx2")  # the HTTP library of anthropic 1.x and 2.x
    except ModuleNotFoundError:
        transport_lib = importlib.import_module("httpx")
    seen: list[tuple[str | None, dict[str, Any]]] = []

    def answer(request: Any) -> Any:
        seen.append((request.headers.get("anthropic-version"), json.loads(request.content)))
        return transport_lib.Response(
            400, json={"type": "error", "error": {"type": "invalid_request_error", "message": "stop here"}}
        )

    client = anthropic.AsyncAnthropic(
        api_key="not-a-real-key",
        max_retries=0,
        http_client=transport_lib.AsyncClient(transport=transport_lib.MockTransport(answer)),
    )
    runner = AgentRunner(client, get_catalog(), settings, today=TODAY)
    for temperature in (None, PROFILE_TEMPERATURE):
        with pytest.raises(anthropic.BadRequestError, match="stop here"):
            await runner._call(
                settings.ANTHROPIC_MODEL_TRIAGE,
                [{"type": "text", "text": "system"}],
                [{"role": "user", "content": "hello"}],
                [],
                {"type": "auto"},
                False,
                None,
                16,
                temperature,
            )
    (plain_version, plain), (set_version, with_temperature), (resent_version, resent) = seen
    assert "temperature" not in plain and plain_version == client.default_headers["anthropic-version"]
    assert with_temperature["temperature"] == 0.0
    # the version that call is sent on still accepts a temperature
    assert set_version == "2023-06-01"
    assert {k: v for k, v in with_temperature.items() if k != "temperature"} == plain
    # the rejected call was sent once more, as the plain call: no temperature, the client's own API version
    assert resent == plain and resent_version == plain_version
    assert runner._temperature_accepted is False
    # and no later call of this runner sets one
    with pytest.raises(anthropic.BadRequestError, match="stop here"):
        await runner._call(
            settings.ANTHROPIC_MODEL_TRIAGE,
            [{"type": "text", "text": "system"}],
            [{"role": "user", "content": "hello"}],
            [],
            {"type": "auto"},
            False,
            None,
            16,
            PROFILE_TEMPERATURE,
        )
    assert len(seen) == 4 and seen[3] == (plain_version, plain)


@pytest.mark.anyio
async def test_a_rejected_temperature_does_not_fail_the_call() -> None:
    """An API that answers 400 to any request carrying a temperature (a model or an API version that does not
    take one) and a streamed message otherwise: the call comes back with the message."""
    import importlib

    import anthropic

    try:
        transport_lib = importlib.import_module("httpx2")
    except ModuleNotFoundError:
        transport_lib = importlib.import_module("httpx")
    bodies: list[dict[str, Any]] = []

    def event(name: str, data: dict[str, Any]) -> str:
        return f"event: {name}\ndata: {json.dumps({'type': name, **data})}\n\n"

    usage = {"input_tokens": 3, "output_tokens": 1}
    message = {
        "id": "msg_local",
        "type": "message",
        "role": "assistant",
        "model": settings.ANTHROPIC_MODEL_TRIAGE,
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": usage,
    }
    stream = "".join(
        [
            event("message_start", {"message": message}),
            event("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
            event("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "ok"}}),
            event("content_block_stop", {"index": 0}),
            event(
                "message_delta", {"delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": usage}
            ),
            event("message_stop", {}),
        ]
    )

    def answer(request: Any) -> Any:
        body = json.loads(request.content)
        bodies.append(body)
        if "temperature" in body:
            return transport_lib.Response(
                400,
                json={
                    "type": "error",
                    "error": {"type": "invalid_request_error", "message": "temperature: not supported"},
                },
            )
        return transport_lib.Response(200, headers={"content-type": "text/event-stream"}, content=stream)

    client = anthropic.AsyncAnthropic(
        api_key="not-a-real-key",
        max_retries=0,
        http_client=transport_lib.AsyncClient(transport=transport_lib.MockTransport(answer)),
    )
    runner = AgentRunner(client, get_catalog(), settings, today=TODAY)
    args = (
        settings.ANTHROPIC_MODEL_TRIAGE,
        [{"type": "text", "text": "system"}],
        [{"role": "user", "content": "hello"}],
        [],
        {"type": "auto"},
        False,
        None,
        16,
    )
    got = await runner._call(*args, PROFILE_TEMPERATURE)  # type: ignore[arg-type]
    assert [block.text for block in got.content if block.type == "text"] == ["ok"]
    assert ["temperature" in b for b in bodies] == [True, False]
    assert runner._temperature_accepted is False
    # the next call that asks for a temperature goes out without one, in a single request
    again = await runner._call(*args, PROFILE_TEMPERATURE)  # type: ignore[arg-type]
    assert again.stop_reason == "end_turn"
    assert ["temperature" in b for b in bodies] == [True, False, False]


# ---- decision 1 in the checklist: what is served not stated --------------------------------------------------
NOT_STATED = "Opening a 40-seat bar in SF Mission with drinks, small kitchen, serve until 1am"
POURS = "what alcohol will be served: beer and wine, or spirits too"


def _bar_with_drinks(**flags: Any) -> ScriptedModel:
    script = ScriptedModel(**flags)
    script.profile = {**script.profile, "serves_alcohol": True, "alcohol_type": "unknown"}
    return script


@pytest.mark.anyio
async def test_the_plan_names_the_undetermined_licence_and_never_picks_one() -> None:
    # the requirements model tries to add one of the two possible licences: it is refused
    script = _bar_with_drinks(extra_permit_ids=["ca.abc_type_42"])
    _progress, terminal = await run_chain(script, RunInput(description=NOT_STATED))
    plan: Plan = terminal[0].data["plan"]
    ids = {s.id for s in plan.steps}
    assert not ids & {"ca.abc_type_42", "ca.abc_type_48"}  # neither licence is picked
    note = plan.disclaimers[0]
    assert note.startswith(f"Not determined: the description does not say {POURS}.")
    catalog = get_catalog()
    for pid, condition in (
        ("ca.abc_type_42", "only beer and wine are served"),
        ("ca.abc_type_48", "spirits are served too"),
    ):
        permit = catalog.get(pid)
        assert permit is not None
        assert f"{permit.name} ({permit.issuing_agency}; applies if {condition})" in note
    # the blocker stage is told, so the summary can say so
    blocker_call = next(c for c in script.calls if "STEPS WITH STALL RISKS" in json.dumps(c["messages"][0]))
    assert "NOT DETERMINED" in json.dumps(blocker_call["messages"][0])
    # the progress line says what is poured plainly
    stage_lines = [e.data["message"] for e in _progress if e.type == "stage" and e.data["stage"] == "intake"]
    assert any("alcohol: not stated" in m for m in stage_lines)


@pytest.mark.anyio
async def test_the_preview_lists_the_undetermined_licences_after_the_ones_that_apply() -> None:
    script = _bar_with_drinks()
    runner = AgentRunner(FakeAnthropic(script), get_catalog(), settings, today=TODAY)  # type: ignore[arg-type]

    async def emit(ev: RunnerEvent) -> None:
        return None

    terminal = [ev async for ev in runner.run(RunInput(description=NOT_STATED, preview_only=True), emit)]
    outcome = terminal[0].data["outcome"]
    assert {p.id for p in outcome.undetermined} == {"ca.abc_type_42", "ca.abc_type_48"}
    previews = runner.preview_permits(outcome)
    applying, rest = previews[: len(outcome.permits)], previews[len(outcome.permits) :]
    assert [p.id for p in applying] == [p.id for p in outcome.permits]
    assert {p.id for p in rest} == {"ca.abc_type_42", "ca.abc_type_48"}
    for p in rest:
        assert p.why_required.startswith("Not determined: applies if ")
        assert p.why_required.endswith(f"The description does not say {POURS}.")


@pytest.mark.anyio
async def test_a_stated_pour_plans_as_before() -> None:
    _progress, terminal = await run_chain(ScriptedModel(), RunInput(description=DESCRIPTION))
    plan: Plan = terminal[0].data["plan"]
    assert "ca.abc_type_42" in {s.id for s in plan.steps}
    assert not any(d.startswith("Not determined") for d in plan.disclaimers)
