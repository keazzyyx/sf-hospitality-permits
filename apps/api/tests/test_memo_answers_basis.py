"""The intake basis (app.memo.answers) gives exactly the profile the memo pipeline gave before it was kept.

An independent check of the refactor that made `MemoRunner.run_memo` build its profile through the basis (the same
function an answer round uses): the code from the intake to the profile, as it was at f0fcdf7, is copied here line
for line and compared with the new path over three intake readings and more than 400 answer sets. The live report
and the end-to-end backtest go through `run_memo`, so a difference here would move their numbers.
"""

from __future__ import annotations

import json
import random
from typing import Any

from app.agents.memo_runner import MemoRunner
from app.agents.runner import RunInput
from app.catalog.loader import get_catalog
from app.core.config import settings
from app.memo.answers import IntakeBasis, apply_basis, intake_basis
from app.memo.evidence import FactOrigins, counted_quotes
from app.memo.intake import QUESTIONS, IntakeAnswers, answered_fields, apply_intake_answers
from app.memo.stated import check_stated, record_cleared, without_model_text
from app.models.profile import QUOTED_FIELDS, BusinessProfile, ClarifyingQuestion, FactQuote
from tests.conftest import TODAY
from tests.fakes import BASE_PROFILE

DESC = (
    "40-seat wine bar of 1,400 square feet, small kitchen, open until 1am, occasional live music, amplified"
)
CITY = {"city_slug": "san_francisco", "state": "CA", "city_name": "San Francisco"}


class NoModel:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the intake model was called ({name})")


def _runner() -> MemoRunner:
    return MemoRunner(NoModel(), get_catalog(), settings, None, None, today=TODAY)  # type: ignore[arg-type]


def _old_pipeline(
    runner: MemoRunner,
    intake: BusinessProfile,
    quotes: list[FactQuote],
    run_inp: RunInput,
    overrides: dict[str, Any],
    answers: IntakeAnswers,
) -> tuple[BusinessProfile, FactOrigins]:
    """`MemoRunner.run_memo` from the stated-facts check to the profile, at f0fcdf7."""
    text = runner._stated_text(run_inp)
    checked = check_stated(intake, quotes, text)
    origins = FactOrigins(
        quotes=counted_quotes(quotes, text),
        answered=answered_fields(answers),
        clarified=frozenset(
            q.maps_to for q in run_inp.clarification_questions if q.id in run_inp.clarification_answers
        ),
        requested=frozenset(overrides),
    )
    merged = apply_intake_answers(runner._merge_profile(checked.profile, run_inp), answers)
    merged = record_cleared(merged, checked, runner._given_fields(run_inp, answers))
    return merged.normalized(), origins


def _new_pipeline(
    runner: MemoRunner,
    intake: BusinessProfile,
    quotes: list[FactQuote],
    run_inp: RunInput,
    overrides: dict[str, Any],
    answers: IntakeAnswers,
) -> tuple[BusinessProfile, FactOrigins]:
    """The same through the basis, as `run_memo` builds it now, stored and read back as JSON as a round reads it."""
    text = runner._stated_text(run_inp)
    checked = check_stated(intake, quotes, text)
    clarified = {q.maps_to for q in run_inp.clarification_questions if q.id in run_inp.clarification_answers}
    basis = intake_basis(
        runner._merge_profile(checked.profile, run_inp),
        checked,
        quotes=counted_quotes(quotes, text),
        clarified=clarified,
        requested=overrides,
        given=runner._given_fields(run_inp, IntakeAnswers()),
    )
    stored = IntakeBasis.model_validate(json.loads(json.dumps(basis.model_dump(mode="json"))))
    return apply_basis(stored, answers)


def _answer_sets() -> list[IntakeAnswers]:
    """No answer; every single answer each question allows (numbers and times at a few values); and 400 seeded
    random sets of two to seven answers that validate together."""
    values: dict[str, list[Any]] = {}
    for q in QUESTIONS:
        if q.kind == "yes_no":
            values[q.id] = [True, False]
        elif q.kind == "number":
            values[q.id] = [0, 10, 11, 40] if q.id == "other_locations" else [1, 10, 11, 1800]
        elif q.kind == "time":
            values[q.id] = ["00:00", "01:30", "02:00", "02:30", "23:00"]
        elif q.kind == "multi_choice":
            values[q.id] = [["first"], ["second"], ["basement", "first"], ["third_or_above"]]
        else:
            values[q.id] = [o.value for o in q.answers]
    sets: list[IntakeAnswers] = [IntakeAnswers()]
    for qid, options in values.items():
        for v in options:
            body = {qid: v, **({"part_of_chain": True} if qid == "other_locations" else {})}
            sets.append(IntakeAnswers.model_validate(body))
    singles = len(sets)
    rng = random.Random(20261116)
    ids = list(values)
    while len(sets) < singles + 400:
        body = {qid: rng.choice(values[qid]) for qid in rng.sample(ids, rng.randint(2, 7))}
        if "other_locations" in body:
            body["part_of_chain"] = True
        try:
            sets.append(IntakeAnswers.model_validate(body))
        except ValueError:
            continue
    return sets


def _readings() -> list[tuple[BusinessProfile, list[FactQuote], RunInput, dict[str, Any]]]:
    question = ClarifyingQuestion(
        id="q1", question="Will the restaurant serve alcohol?", kind="boolean", maps_to="serves_alcohol"
    )
    return [
        # every field quoted with the whole description: the check keeps what its words state
        (
            BusinessProfile.model_validate(BASE_PROFILE),
            [FactQuote(field=f, quote=DESC) for f in QUOTED_FIELDS],  # type: ignore[arg-type]
            RunInput(description=DESC, profile_overrides=dict(CITY)),
            {},
        ),
        # only the business type quoted: the check clears every other fact it read
        (
            BusinessProfile.model_validate(BASE_PROFILE),
            [FactQuote(field="business_type", quote="wine bar")],
            RunInput(description=DESC, profile_overrides=dict(CITY)),
            {},
        ),
        # a restaurant with a clarification answer and an operator override
        (
            BusinessProfile.model_validate({**BASE_PROFILE, "business_type": "restaurant", "seats": 60}),
            [
                FactQuote(field="business_type", quote="restaurant"),
                FactQuote(field="seats", quote="60 seats"),
            ],
            RunInput(
                description="A restaurant with 60 seats, open until 2 am",
                clarification_questions=[question],
                clarification_answers={"q1": True},
                profile_overrides={**CITY, "square_feet": 900},
            ),
            {"square_feet": 900},
        ),
    ]


def test_the_basis_gives_exactly_the_profile_and_origins_the_pipeline_gave_before() -> None:
    runner = _runner()
    sets = _answer_sets()
    compared = 0
    cleared_somewhere = False
    for intake, quotes, run_inp, overrides in _readings():
        for answers in sets:
            old_profile, old_origins = _old_pipeline(runner, intake, quotes, run_inp, overrides, answers)
            new_profile, new_origins = _new_pipeline(runner, intake, quotes, run_inp, overrides, answers)
            # the old profile still held the intake model's own text, which no rule reads and nothing stores
            assert without_model_text(old_profile).model_dump() == new_profile.model_dump(), answers
            assert old_origins == new_origins, answers
            cleared_somewhere |= bool(new_profile.intake_cleared)
            compared += 1
    assert compared == 3 * len(sets) and len(sets) > 450
    assert cleared_somewhere  # the readings exercise the cleared facts too
