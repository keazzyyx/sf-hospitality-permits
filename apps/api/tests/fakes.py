"""A scripted stand-in for `anthropic.AsyncAnthropic` that drives the tool-use loop without the network."""

from __future__ import annotations

import copy
import json
import re
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

BASE_PROFILE: dict[str, Any] = {
    "business_type": "bar",
    "business_name": "Rioja Room",
    "city_name": "SF Mission",
    "city_slug": "san_francisco",
    "state": "CA",
    "neighborhood": "Mission",
    "seats": 40,
    "square_feet": 1400,
    "employees": 8,
    "hotel_rooms": None,
    "serves_food": True,
    "has_kitchen": True,
    "cooking_type": "limited",
    "serves_alcohol": True,
    "alcohol_type": "beer_wine",
    "closes_after_midnight": True,
    "closes_after_2am": False,
    "live_entertainment": True,
    "amplified_sound": True,
    "dancing": False,
    "outdoor_seating": False,
    "sidewalk_or_parklet": False,
    "change_of_use": False,
    "tenant_improvements": True,
    "new_construction": False,
    "exterior_signage": True,
    "plays_recorded_music": True,
    "mobile_vending": False,
    "uses_commissary": False,
    "sells_packaged_goods": False,
    "target_open_date": None,
    "assumptions": ["Assumed 8 employees"],
}


def make_message(blocks: list[Any], stop_reason: str = "tool_use") -> Message:
    return Message(
        id="msg_fake",
        type="message",
        role="assistant",
        model="fake-model",
        content=blocks,
        stop_reason=stop_reason,  # type: ignore[arg-type]
        stop_sequence=None,
        usage=Usage(input_tokens=10, output_tokens=10),
    )


def tool_use(name: str, inp: dict[str, Any], tid: str = "tu_1") -> ToolUseBlock:
    return ToolUseBlock(type="tool_use", id=tid, name=name, input=inp)


class _FakeStream:
    """`gate`, when a script gives one, is entered and left with the stream: it is how a script keeps a call
    open for a while (so calls overlap) and counts the calls that are open at once."""

    def __init__(
        self, message: Message, deltas: list[str], gate: AbstractAsyncContextManager[None] | None = None
    ) -> None:
        self._message = message
        self._deltas = deltas
        self._gate = gate

    async def __aenter__(self) -> _FakeStream:
        if self._gate is not None:
            await self._gate.__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._gate is not None:
            await self._gate.__aexit__(None, None, None)
        return None

    def __aiter__(self):  # type: ignore[no-untyped-def]
        async def gen():  # type: ignore[no-untyped-def]
            for d in self._deltas:
                yield SimpleNamespace(
                    type="content_block_delta", delta=SimpleNamespace(type="text_delta", text=d)
                )
            yield SimpleNamespace(type="message_stop")

        return gen()

    async def get_final_message(self) -> Message:
        return self._message


@dataclass
class ScriptedModel:
    """Produces plausible stage responses. Flags switch on specific behaviours under test."""

    ask_clarification: bool = False
    invalid_first_blocker_submit: bool = False
    never_submit_stage: str | None = None
    # permit ids the requirements stage adds to the catalog's matches (as a model may add one it thinks applies)
    extra_permit_ids: list[str] = field(default_factory=list)
    profile: dict[str, Any] = field(default_factory=lambda: dict(BASE_PROFILE))
    # The quotes the intake stage submits (app.memo.stated). None: every field the memo's rules read is quoted with
    # the whole description, so the check keeps what the description's words state and clears the rest.
    intake_quotes: list[dict[str, str]] | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    _blocker_attempts: int = 0

    # ---- helpers -------------------------------------------------------------------------
    @staticmethod
    def _submit_name(params: dict[str, Any]) -> str:
        names = [t["name"] for t in params["tools"]]
        return next(n for n in names if n.startswith("submit_"))

    @staticmethod
    def _last_tool_results(params: dict[str, Any]) -> list[dict[str, Any]]:
        last = params["messages"][-1]
        if last["role"] != "user" or not isinstance(last["content"], list):
            return []
        return [b for b in last["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]

    @staticmethod
    def _user_text(params: dict[str, Any]) -> str:
        first = params["messages"][0]
        return first["content"] if isinstance(first["content"], str) else ""

    @staticmethod
    def _tool_takes(params: dict[str, Any], name: str, key: str) -> bool:
        """Whether the request's tool `name` has a top-level input field `key`."""
        for tool in params.get("tools") or []:
            if tool.get("name") == name:
                return key in (tool.get("input_schema") or {}).get("properties", {})
        return False

    @staticmethod
    def _quote_all(text: str) -> list[dict[str, str]]:
        """Every field the memo's rules read, quoted with the description the runner sent (cut at a word to fit)."""
        from app.models.profile import QUOTED_FIELDS

        m = re.search(r"USER DESCRIPTION:\n<<<\n(.*?)\n>>>", text, re.S)
        quote = (m.group(1) if m else "").strip()
        if len(quote) > 300:
            quote = quote[:300].rsplit(" ", 1)[0]
        return [{"field": f, "quote": quote} for f in QUOTED_FIELDS] if quote else []

    def gate(self, params: dict[str, Any]) -> AbstractAsyncContextManager[None] | None:
        """What the call's stream waits in while it is open. None: the call answers at once."""
        return None

    def _profile_from(self, params: dict[str, Any]) -> dict[str, Any]:
        """Use the profile the runner put in the user message when there is one (like a real model would)."""
        m = re.search(r"BUSINESS PROFILE:\n(\{.*?\n\})", self._user_text(params), re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        return self.profile

    # ---- the script ----------------------------------------------------------------------
    def respond(self, params: dict[str, Any]) -> tuple[Message, list[str]]:
        self.calls.append(copy.deepcopy(params))
        submit = self._submit_name(params)
        stage = submit.removeprefix("submit_").removesuffix("_result")
        forced = params.get("tool_choice", {}).get("type") == "tool"
        if self.never_submit_stage == stage and not forced:
            return make_message(
                [TextBlock(type="text", text="Thinking out loud without submitting.")], "end_turn"
            ), []
        if self.never_submit_stage == stage and forced:
            # even when forced we misbehave to prove the loop terminates
            return make_message([TextBlock(type="text", text="still no tool call")], "end_turn"), []
        results = self._last_tool_results(params)

        if stage == "triage":
            return make_message(
                [
                    tool_use(
                        submit,
                        {
                            "is_hospitality_business": True,
                            "language": "en",
                            "city_guess": "SF Mission",
                            "state_guess": "CA",
                            "reject_reason": None,
                        },
                    )
                ]
            ), []

        if stage == "intake":
            if not results and not forced:
                return make_message(
                    [tool_use("lookup_permit_catalog", {"profile": self.profile}, "tu_lookup")]
                ), []
            text = self._user_text(params)
            answered = "CLARIFICATION ANSWERS" in text
            needs = self.ask_clarification and not answered
            payload: dict[str, Any] = {
                "profile": self.profile,
                "needs_clarification": needs,
                "questions": [
                    {
                        "id": "q1",
                        "question": "Will you host live music after 10pm?",
                        "kind": "boolean",
                        "options": None,
                        "maps_to": "live_entertainment",
                        "required": True,
                    }
                ]
                if needs
                else [],
                "reasoning_summary": "40-seat wine bar in the Mission with limited kitchen and late hours.",
            }
            # only the memo's intake tool takes quotes (app.memo.stated); the checklist's has none
            if self._tool_takes(params, submit, "quotes"):
                payload["quotes"] = (
                    self.intake_quotes if self.intake_quotes is not None else self._quote_all(text)
                )
            return make_message([tool_use(submit, payload)]), []

        if stage == "requirements":
            if not results and not forced:
                return make_message(
                    [tool_use("lookup_permit_catalog", {"profile": self._profile_from(params)}, "tu_lookup")]
                ), []
            ids: list[str] = []
            for r in results:
                try:
                    data = json.loads(r["content"])
                    ids = [m["id"] for m in data.get("matches", [])]
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass
            if not ids:
                ids = ["us.ein", "sf.business_registration"]
            ids = [*ids, *self.extra_permit_ids]
            permits = [
                {
                    "permit_id": i,
                    "why_required": f"{i} is required because of the stated business facts.",
                    "priority": "standard",
                }
                for i in ids
            ]
            permits.append(
                {
                    "permit_id": "sf.not_a_real_permit",
                    "why_required": "A hallucinated id that must be dropped by the runner.",
                    "priority": "optional",
                }
            )
            return make_message(
                [
                    tool_use(
                        submit,
                        {
                            "permits": permits,
                            "unsupported_city_note": None,
                            "notes": "Rule matches confirmed.",
                        },
                    )
                ]
            ), []

        if stage == "timeline":
            m = re.search(r"WEEKS TO NARRATE[^:]*: \[([0-9, ]+)\]", self._user_text(params))
            weeks = [int(x) for x in m.group(1).split(",")] if m else [1]
            payload = {
                "weeks": [
                    {"week_number": w, "focus": f"Week {w} focus", "actions": [f"Do the week {w} thing"]}
                    for w in weeks[:5]
                ],
                "sequencing_rationale": "Entity and tax registrations unlock every city filing; the conditional use hearing is the long pole.",
                "feasibility_assessment": "The target date is tight because the conditional use authorization alone takes six to ten months.",
            }
            return make_message([tool_use(submit, payload)]), []

        if stage == "blocker":
            self._blocker_attempts += 1
            if self.invalid_first_blocker_submit and self._blocker_attempts == 1:
                return make_message([tool_use(submit, {"executive_summary": "too short", "blockers": []})]), [
                    "Partial "
                ]
            summary = (
                "You are opening a 40-seat wine bar in the Mission with live music until 1am. The realistic opening "
                "window is driven by the Planning Commission's conditional use hearing. Start the entity, tax and "
                "business registrations this week and brief the neighborhood association early."
            )
            blockers = [
                {
                    "id": "b1",
                    "title": "Conditional Use hearing",
                    "severity": "high",
                    "likelihood": "likely",
                    "impact_days_min": 60,
                    "impact_days_max": 120,
                    "description": "Bars are conditional uses in the Mission NCT; the hearing calendar and neighbor opposition routinely add months.",
                    "mitigation": "Hold the pre-application community meeting within two weeks and secure a lease contingency on CUA approval.",
                    "related_step_ids": ["sf.conditional_use_authorization", "sf.bogus_step"],
                },
                {
                    "id": "b2",
                    "title": "Failed pre-opening health inspection",
                    "severity": "medium",
                    "likelihood": "possible",
                    "impact_days_min": 14,
                    "impact_days_max": 21,
                    "description": "Missing hand sinks or unsealed surfaces are the most common reasons the permit to operate is withheld.",
                    "mitigation": "Walk the space against the DPH checklist one week before the inspection with your contractor.",
                    "related_step_ids": ["sf.health_permit"],
                },
            ]
            return make_message(
                [
                    TextBlock(type="text", text=summary),
                    tool_use(submit, {"executive_summary": summary, "blockers": blockers}),
                ]
            ), [summary[:40], summary[40:]]

        raise AssertionError(f"unexpected stage {stage}")


class FakeMessagesAPI:
    def __init__(self, script: ScriptedModel) -> None:
        self.script = script

    def stream(self, **params: Any) -> _FakeStream:
        message, deltas = self.script.respond(params)
        return _FakeStream(message, deltas, self.script.gate(params))

    async def create(self, **params: Any) -> Message:  # not used by the runner, kept for parity
        message, _ = self.script.respond(params)
        return message


class FakeAnthropic:
    def __init__(self, script: ScriptedModel | None = None) -> None:
        self.script = script or ScriptedModel()
        self.messages = FakeMessagesAPI(self.script)
