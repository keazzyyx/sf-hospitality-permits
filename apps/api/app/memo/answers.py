"""Answering the intake questions on a memo that is already made: the answer rounds. No I/O, no model call, no
clock.

Owner decision of 2026-11-16: "answer and run again" is free and stays on the same memo, up to five rounds a memo
(`ANSWER_ROUND_LIMIT`). Before it, the report's "Answer and run again" made a new memo, so a normal account spent a
free preview or a memo credit to give an answer the report itself asked for.

WHAT A ROUND DOES NOT DO. It never calls the intake model and never runs the stated-facts check again. The
description is the same, so what the intake model read from it, and what the check kept and cleared, are the same:
they were checked once, when the memo was made, and the result is kept with the memo (`IntakeBasis`, the
`intake_basis` column). A round applies the merged answers to that kept result by the same code a new memo uses
(`apply_basis`), and the runner then reads the records and the rules exactly as it does after the intake of a new
memo (`MemoRunner.run_answers`). So a round gives the report a new memo with the same description and the merged
answers would get from the same intake reading.

WHAT IS KEPT (`IntakeBasis`), all of it written by code from the intake of the memo's first run:
  profile    the profile after the stated-facts check, with the clarification answers and the operator overrides
             applied, and before the intake answers (`AgentRunner._merge_profile`). Without the intake model's own
             text (`app.memo.stated.without_model_text`): no rule reads it.
  cleared    what the check cleared: field -> the value removed (`StatedCheck.cleared`).
  checked    for each cleared field, the value the check left (what `record_cleared` compares with).
  quotes     the applicant's words each fact came from, cut from the applicant's text (`counted_quotes`).
  clarified  the fields a clarification answer set; `requested`, the fields the operator overrides set; `given`,
             every field given after the check other than by an intake answer (both, and the city fields).
  model_versions  the model that read the description, which a round's report names as a new memo's does.
  geo        the address record the first run read: the address is fixed, so a round reads the records at the same
             point and parcel, and never geocodes the stored display address again (a geocoder that did not find it
             would fall back to the bare coordinates, with no parcel, and change the site records read).
A memo made before the basis was kept has none, and is not answered this way (409 `answers_unavailable`): its
answers would have to be put on a profile that already holds the earlier answers, and an earlier answer cannot be
taken off it again (a "No alcohol" answer clears the licence type the description gave, for good). The report's
"Answer and run again" then makes a new memo, as before.

MERGING THE ANSWERS (`merge_answers`). The answers sent win; a question not answered in the request keeps the answer
stored with the memo (so an answer is never taken back by a round, only changed). A stored answer that cannot stand
with a new one is dropped, so the new one wins:
  stored other_locations          dropped by a new part_of_chain false
  stored alcohol_served           dropped by a new liquor_licence "none"
  stored outdoor_alcohol_service  dropped by a new liquor_licence "none" (when true) or outdoor_area "none"
  stored liquor_licence "none"    dropped by a new alcohol_served, or a new outdoor_alcohol_service true
  stored outdoor_area "none"      dropped by a new outdoor_alcohol_service
  stored food_service             dropped by a new answer that says alcohol is served (a liquor licence other than
                                  "none", alcohol_served, outdoor_alcohol_service true)
A new food_service is refused (422, ANSWERS_FOOD_SERVICE_MESSAGE) where the stored answers the round keeps say
alcohol is served (a liquor licence other than "none", alcohol_served, outdoor_alcohol_service true): the question
is asked only for a business that serves no alcohol, and the rules read the answer only for a bar that serves none,
so dropping those answers for it would let an answer the rules may not read remove answers they do read. Sent with
liquor_licence "none", it is accepted, and the "No alcohol" answer drops what is poured as above (review fix of
2026-11-16: before it a new food_service dropped them, on a cocktail bar whose alcohol row then named what is
poured and how the licence is obtained as not known).
Two answers in the same request that contradict each other are refused (422), as on a new memo (`IntakeAnswers`).
A follow-up may come on its own when the answer it follows is stored (`RoundAnswers`): a new count of other
locations on a memo whose stored answers say it is part of a chain. With no such answer, sent or stored, the count
is refused (422, ANSWERS_FOLLOW_UP_MESSAGE); the chain is never inferred from the count.
An answer that disagrees with the description is read as on a new memo: the answer wins, and where the rules
cannot read the two together they say so (fewer than 50 people against 50 seats or more: the building row names
the conflict, `app.memo.rows`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.memo.evidence import FactOrigins
from app.memo.intake import QUESTIONS, IntakeAnswers, QuestionId, answered_fields, apply_intake_answers
from app.memo.stated import StatedCheck, record_cleared, without_model_text
from app.models.profile import BusinessProfile

# The rounds of answers one memo can be run again with (owner decision of 2026-11-16).
ANSWER_ROUND_LIMIT = 5

# The fixed sentences of the answer rounds (the API's error messages and the record's error line).
ANSWERS_UNAVAILABLE_MESSAGE = (
    "This memo was made before answers could be added to it. Answering the questions makes a new memo for it."
)
ANSWERS_LIMIT_MESSAGE = (
    f"This memo has been run again with answers {ANSWER_ROUND_LIMIT} times, the most one memo allows. "
    "To change it again, start a new memo."
)
ANSWERS_EMPTY_MESSAGE = "Answer at least one question."
ANSWERS_UNCHANGED_MESSAGE = "These are the answers the memo already has. Change at least one."
# A count of other locations sent with no "part of a chain" answer to stand on, in the request or stored with the memo.
ANSWERS_FOLLOW_UP_MESSAGE = (
    "The number of other locations is asked only when the business is part of a chain. "
    "Answer that question with yes first."
)
# A kind of food or drink service sent in a round whose stored answers say alcohol is served, with no "No alcohol" sent:
# the question is asked only for a business that serves none, so the round is refused (`FoodServiceNeedsNoAlcoholError`).
ANSWERS_FOOD_SERVICE_MESSAGE = (
    "The kind of food or drink service is asked only for a business that serves no alcohol, and the answers this "
    'memo has say alcohol is served. To change that, answer the liquor licence question with "No alcohol" too.'
)
ANSWERS_RUNNING_MESSAGE = "This memo is being run again with answers already. Wait until it is finished."
ANSWERS_NOT_READY_MESSAGE = "This memo is not finished yet. Answer the questions once it is ready."
# A round that did not finish leaves the memo as it was before it, with one of these as its error line.
ANSWERS_FAILED_MESSAGE = (
    "Your answers could not be applied, so the report below is the one from before them. Nothing was charged and "
    "the round was not counted. Try again."
)
ANSWERS_STOPPED_MESSAGE = (
    "Applying your answers stopped before it was finished, so the report below is the one from before them. "
    "Nothing was charged and the round was not counted. Try again."
)


class FoodServiceNeedsNoAlcoholError(Exception):
    """A round sends the kind of food or drink service where the answers stored with the memo, and not replaced by
    the round, say alcohol is served (see MERGING THE ANSWERS)."""


class RoundAnswers(IntakeAnswers):
    """The body of an answer round: the intake answers, with every rule of `IntakeAnswers` but the one a stored answer
    can meet. A count of other locations needs "part of a chain" true, and in a round that answer may be the one
    stored with the memo; `merge_answers` checks the merged answers against every rule, and the route refuses them
    (422) when the count has nothing to stand on."""

    @model_validator(mode="after")
    def _count_needs_a_chain(self) -> RoundAnswers:  # replaces the rule of IntakeAnswers of the same name
        return self


class IntakeBasis(BaseModel):
    """What the intake of a memo's first run left, before the intake answers (see WHAT IS KEPT)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    profile: BusinessProfile
    cleared: dict[str, Any] = Field(default_factory=dict)
    checked: dict[str, Any] = Field(default_factory=dict)
    quotes: dict[str, list[str]] = Field(default_factory=dict)
    clarified: list[str] = Field(default_factory=list)
    requested: list[str] = Field(default_factory=list)
    given: list[str] = Field(default_factory=list)
    # the model that read the description (`Memo.model_versions`): a round's report was read by that same model
    model_versions: dict[str, str] = Field(default_factory=dict)
    # the address record the first run read (`precedent.geocode.GeocodeResult` as a dict): the address is fixed, so a
    # round reads the records at the same point and parcel and never geocodes again
    geo: dict[str, Any] | None = None


def intake_basis(
    base: BusinessProfile,
    check: StatedCheck,
    *,
    quotes: Mapping[str, Iterable[str]],
    clarified: Iterable[str] = (),
    requested: Iterable[str] = (),
    given: Iterable[str] = (),
    model_versions: Mapping[str, str] | None = None,
    geo: Mapping[str, Any] | None = None,
) -> IntakeBasis:
    """The basis of a memo's first run: `base` is the checked profile with the clarification answers and the
    overrides applied (`AgentRunner._merge_profile`), `check` the stated-facts check it came from."""
    after = check.profile.model_dump()
    return IntakeBasis(
        profile=without_model_text(base),
        cleared=dict(check.cleared),
        checked={f: after[f] for f in check.cleared},
        quotes={f: list(v) for f, v in quotes.items()},
        clarified=sorted(set(clarified)),
        requested=sorted(set(requested)),
        given=sorted(set(given)),
        model_versions=dict(model_versions or {}),
        geo=dict(geo) if geo is not None else None,
    )


def apply_basis(basis: IntakeBasis, answers: IntakeAnswers) -> tuple[BusinessProfile, FactOrigins]:
    """The profile the rules read, and where each fact came from, for these answers on this basis. A new memo and an
    answer round both get their profile here, so the two cannot differ."""
    answered = answered_fields(answers)
    merged = apply_intake_answers(basis.profile, answers)
    # the check as it ran: `record_cleared` reads only the value it left in each field it cleared
    check = StatedCheck(basis.profile.model_copy(update=basis.checked), dict(basis.cleared))
    # a field the applicant gave (an intake answer, a clarification answer, an override) is no longer cleared,
    # whatever its value
    merged = record_cleared(merged, check, {*basis.given, *answered})
    origins = FactOrigins(
        quotes={f: tuple(v) for f, v in basis.quotes.items()},
        answered=answered,
        clarified=frozenset(basis.clarified),
        requested=frozenset(basis.requested),
    )
    # normalized() leaves what is poured "unknown" when the description does not say it, so the rules read the
    # same profile as the catalog: no licence type is derived from a guess
    return merged.normalized(), origins


def basis_of(stored: Any) -> IntakeBasis | None:
    """The basis stored with a memo row (`intake_basis`), or None when there is none or it does not validate. A
    stored row never fails a request."""
    if not isinstance(stored, dict) or not stored:
        return None
    try:
        return IntakeBasis.model_validate(stored)
    except ValidationError:
        return None


def merge_answers(stored: IntakeAnswers, new: IntakeAnswers) -> tuple[IntakeAnswers, tuple[QuestionId, ...]]:
    """The answers of a round: the new answers, and each stored answer that can stand with them (see MERGING THE
    ANSWERS). Also the stored answers dropped because a new one contradicts them, in the order they are asked.

    The questions are read in the order they are asked, and every answer that can contradict another depends only on
    an earlier one (a follow-up on its question, what is poured on the licence), so keeping each stored answer that
    validates with the new answers and the stored ones kept before it is the whole rule.

    `new` may be `RoundAnswers`; the merged answers are always checked as `IntakeAnswers`, and a ValidationError
    here means a count of other locations with no "part of a chain" true to stand on (every other rule the new answers
    already met on their own, and each stored answer is kept only when the rules hold with it).
    `FoodServiceNeedsNoAlcoholError`: a new kind of food or drink service where the stored answers the round keeps say
    alcohol is served (the round must answer "No alcohol" too)."""
    if new.food_service is not None:
        # the kind of food or drink service is read only for a business that serves no alcohol: over stored answers
        # that say alcohol is served it would drop answers the rules read, so the round must say "No alcohol" too
        without, _ = merge_answers(stored, new.model_copy(update={"food_service": None}))
        if without.serves_alcohol_by_answer:
            raise FoodServiceNeedsNoAlcoholError(ANSWERS_FOOD_SERVICE_MESSAGE)
    given = new.model_dump(exclude_none=True)
    kept: dict[str, Any] = {}
    dropped: list[QuestionId] = []
    for q in QUESTIONS:
        value = getattr(stored, q.id)
        if q.id in given or value is None:
            continue
        try:
            IntakeAnswers.model_validate({**kept, q.id: value, **given})
        except ValidationError:
            dropped.append(q.id)
            continue
        kept[q.id] = value
    return IntakeAnswers.model_validate({**kept, **given}), tuple(dropped)
