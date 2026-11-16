"""The kind of food or drink service of a bar that serves no alcohol (owner decision of 2026-11-16: "a business that
serves no alcohol is not a Bar use (Planning Code § 102). No alcohol row, and ask what kind of food or drink service
it is; don't assume.").

Before this change the report named the kind of food or drink service as not known (pathway rule 1b) but no intake
question gave it, so the applicant could not answer it, in a new memo or in an answer round. Now the intake question
"food_service" gives it: "restaurant" or "limited_restaurant" is the concept's use, read from the answer, and the rules
run for it (still no alcohol row); "other" ("Other, or not sure") keeps it not known and named. The missing input
points at the question. The last tests run answer rounds through the API: the food service answer, and a T7 headline
that a round makes definite or takes away.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from precedent.geocode import GeocodeResult
from precedent.models import Application
from precedent.store.base import ZoningInfo
from precedent.store.local import LocalStore
from pydantic import ValidationError

from app.agents.memo_runner import MemoRunner
from app.catalog.loader import get_catalog
from app.core.config import settings
from app.memo import controls, evidence, intake, pathway
from app.memo import triggers as tg
from app.memo.answers import ANSWERS_FOOD_SERVICE_MESSAGE, FoodServiceNeedsNoAlcoholError, merge_answers
from app.memo.facts import MISSING_PHRASES, concept_facts
from app.memo.intake import QUESTION_BY_ID, IntakeAnswers, apply_intake_answers
from app.models.memo import Determinations
from app.models.profile import MODEL_MAY_NOT_SET, BusinessProfile
from app.services.db import MemoryDatabase
from tests import test_memo_answers as tma
from tests.conftest import TODAY
from tests.fakes import BASE_PROFILE, FakeAnthropic
from tests.memo_fakes import FakeGeocoder, MemoScript
from tests.test_all_rows_decided import NC_2, SITE
from tests.test_intake_review_round_2 import row, through_the_runner

client = tma.client
db = tma.db
many_previews = tma.many_previews

FOOD = MISSING_PHRASES["food_service"]
ZERO_PROOF = "A zero-proof cocktail bar on the ground floor"
ZERO_PROOF_MODEL: dict[str, Any] = {"business_type": "bar", "stories": ["first"]}
ZERO_PROOF_QUOTES = [("business_type", "zero-proof cocktail bar"), ("stories", "ground floor")]
MOCKTAIL = "A mocktail bar on the ground floor"
MOCKTAIL_QUOTES = [("business_type", "mocktail bar"), ("stories", "ground floor")]


def zero_proof(answers: IntakeAnswers) -> tuple[BusinessProfile, Determinations]:
    return through_the_runner(ZERO_PROOF_MODEL, ZERO_PROOF_QUOTES, ZERO_PROOF, answers)


def named(d: Determinations) -> list[str]:
    """Every missing input the report names: the rows, the triggers and the open questions."""
    return [
        *(p for r in d.rows for p in r.missing_inputs),
        *(p for t in d.pathway.triggers for p in t.missing_inputs),
        *(q.question for q in d.open_questions),
    ]


# ---- 1. the question ------------------------------------------------------------------------------------------------
def test_the_question_asks_the_kind_of_service_in_the_words_of_section_102() -> None:
    q = QUESTION_BY_ID["food_service"]
    assert (q.question, q.kind, q.fact, q.group) == (
        "What kind of food or drink service is it?",
        "choice",
        "food_service",
        "main",
    )
    # a follow-up of "No alcohol" (the page also shows it when the report asks for it)
    assert q.shown_when == "liquor_licence=none"
    assert [(a.value, a.label) for a in q.answers] == [
        ("restaurant", "A Restaurant (cooked food served on the premises, with seating)"),
        ("limited_restaurant", "A Limited Restaurant (ready-to-eat food or drinks, with or without seating)"),
        ("other", "Other, or not sure"),
    ]
    # the help quotes the two § 102 definitions, and each is the definition the dated control data carries
    for words in (
        "serves prepared, ready-to-eat cooked foods",
        "for consumption on the premises",
        "ready-to-eat foods and/or drinks",
        "for consumption on or off the premises",
    ):
        assert words in q.help
    doc = json.loads(controls.DATA_PATH.read_text(encoding="utf-8"))
    for version in doc["citywide"]["use_definitions"]:
        assert (
            "serves prepared, ready-to-eat cooked foods for consumption on the premises and has seating"
            in version["rule"]
        )
        assert (
            "serves ready-to-eat foods and/or drinks for consumption on or off the premises, with or without "
            in version["rule"]
        )
    # neutral: neither use is put forward as the likely one
    assert not any(w in q.help.lower() for w in ("usually", "most ", "likely", "probably", "typical"))
    # the intake model never gives it: only the applicant's answer does
    assert "food_service" in MODEL_MAY_NOT_SET
    assert "food_service" not in json.dumps(BusinessProfile.model_json_schema())


@pytest.mark.parametrize(
    "answers",
    [
        {"food_service": "restaurant", "liquor_licence": "new"},
        {"food_service": "limited_restaurant", "liquor_licence": "already_held"},
        {"food_service": "other", "alcohol_served": "beer_wine"},
        {"food_service": "restaurant", "outdoor_area": "front", "outdoor_alcohol_service": True},
        {"food_service": "bar"},
        {"food_service": "cafe"},
    ],
)
def test_an_answer_that_says_alcohol_is_served_or_names_another_use_is_refused(
    answers: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        IntakeAnswers.model_validate(answers)


def test_the_answer_is_accepted_with_no_alcohol_or_no_licence_answer() -> None:
    for answers in (
        {"food_service": "restaurant"},
        {"food_service": "limited_restaurant", "liquor_licence": "none"},
        {"food_service": "other", "outdoor_area": "front", "outdoor_alcohol_service": False},
    ):
        assert IntakeAnswers.model_validate(answers).answered()[-1] == "food_service"


def test_a_round_drops_a_stored_answer_the_new_one_contradicts() -> None:
    def merged(stored: dict[str, Any], new: dict[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
        got, gone = merge_answers(IntakeAnswers.model_validate(stored), IntakeAnswers.model_validate(new))
        return got.model_dump(exclude_none=True), gone

    # a licence after all: the kind of food or drink service goes
    assert merged({"liquor_licence": "none", "food_service": "restaurant"}, {"liquor_licence": "new"}) == (
        {"liquor_licence": "new"},
        ("food_service",),
    )
    assert merged({"food_service": "restaurant"}, {"alcohol_served": "beer_wine"}) == (
        {"alcohol_served": "beer_wine"},
        ("food_service",),
    )
    # the kind of food or drink service after a licence, with "No alcohol": the licence and what is poured go
    assert merged(
        {"liquor_licence": "new", "alcohol_served": "beer_wine"},
        {"liquor_licence": "none", "food_service": "limited_restaurant"},
    ) == ({"liquor_licence": "none", "food_service": "limited_restaurant"}, ("alcohol_served",))
    # "No alcohol" stays with it
    assert merged({"liquor_licence": "none"}, {"food_service": "other"}) == (
        {"liquor_licence": "none", "food_service": "other"},
        (),
    )


@pytest.mark.parametrize(
    "stored",
    [
        {"liquor_licence": "new"},
        {"liquor_licence": "new", "alcohol_served": "full_liquor", "stories": ["first"]},
        {"alcohol_served": "beer_wine"},
        {"outdoor_area": "front", "outdoor_alcohol_service": True},
    ],
)
def test_a_round_refuses_the_kind_of_service_over_stored_answers_that_serve_alcohol(
    stored: dict[str, Any],
) -> None:
    """On 1a531f2 a new food_service dropped the stored answers that say alcohol is served, though the rules then
    read the food_service answer only for a bar that serves no alcohol: an answer they ignore removed answers they
    read (the alcohol row lost what is poured and how the licence is obtained). The round is refused instead; with
    "No alcohol" sent too, it is not."""
    with pytest.raises(FoodServiceNeedsNoAlcoholError):
        merge_answers(IntakeAnswers.model_validate(stored), IntakeAnswers(food_service="restaurant"))
    if "outdoor_area" not in stored:
        got, _ = merge_answers(
            IntakeAnswers.model_validate(stored),
            IntakeAnswers(liquor_licence="none", food_service="restaurant"),
        )
        assert (got.liquor_licence, got.food_service, got.alcohol_served) == ("none", "restaurant", None)
    else:  # an outdoor area with no alcohol served there: the answer the rules read is the new one
        got, gone = merge_answers(
            IntakeAnswers.model_validate(stored),
            IntakeAnswers(outdoor_alcohol_service=False, food_service="restaurant"),
        )
        assert (got.outdoor_alcohol_service, got.food_service, gone) == (False, "restaurant", ())


# ---- 2. an answer gives the use, and the rules run for it -----------------------------------------------------------
@pytest.mark.parametrize(
    ("answer", "use", "label"),
    [
        ("restaurant", "restaurant", "a Restaurant"),
        ("limited_restaurant", "limited_restaurant", "a Limited Restaurant"),
    ],
)
def test_an_answer_sets_the_use_of_a_zero_proof_bar(answer: str, use: str, label: str) -> None:
    profile, d = zero_proof(IntakeAnswers.model_validate({"food_service": answer}))
    assert profile.no_alcohol_stated and profile.food_service == answer
    concept = concept_facts(profile)
    assert concept.not_a_bar
    assert concept.planning_uses.value == (use,)
    assert (concept.planning_uses.source, concept.planning_uses.basis) == ("stated", "food_service")
    assert d.pathway.use == use
    # still no alcohol row, and no Bar
    assert "alcohol" not in {r.area for r in d.rows}
    assert "bar" not in concept.planning_uses.value
    # the kind of food or drink service is no longer named anywhere
    assert not [p for p in named(d) if FOOD in p]
    assert not [q for q in d.open_questions if q.intake_question == "food_service"]
    # T1 reads the use's own control: decided, not "no use control was looked up"
    t1 = tg.by_id(d.pathway.triggers, "T1")
    assert t1.control != "not_decided" and FOOD not in t1.missing_inputs
    assert not [line for line in t1.lines if line.rule_id == "T1.no_use"]
    # the use line says the answer gave it ("you answered"), after the line that it is not a Bar
    first, second = d.pathway.lines[0], d.pathway.lines[1]
    assert first.rule_id == "zoning.food_service"
    assert first.text == (
        "The business is described as a bar that serves no alcohol, so it is not a Bar: Planning Code § 102 defines "
        f"a Bar by its on-site alcoholic beverage sales. You answered that it is {label}, and the rules read that use."
    )
    assert first.code_section == "Planning Code § 102 (Bar)"
    assert second.text == f"The concept is looked up as {label} (Planning Code § 102)."
    zoning = row(d, "zoning_use")
    assert zoning.basis[0].text == first.text


def test_with_no_alcohol_answered_the_line_says_both_answers() -> None:
    profile, d = through_the_runner(
        {"business_type": "bar", "stories": ["first"]},
        MOCKTAIL_QUOTES,
        MOCKTAIL,
        IntakeAnswers(liquor_licence="none", food_service="limited_restaurant"),
    )
    assert not profile.no_alcohol_stated
    assert d.pathway.use == "limited_restaurant"
    assert "alcohol" not in {r.area for r in d.rows}
    assert d.pathway.lines[0].text.startswith(
        "The business is described as a bar, and you answered that it serves no alcohol, so it is not a Bar"
    )
    assert "You answered that it is a Limited Restaurant" in d.pathway.lines[0].text


def test_the_report_lists_the_answered_use_once_as_the_applicants_answer() -> None:
    answers = IntakeAnswers(food_service="limited_restaurant")
    profile, d = zero_proof(answers)
    origins = evidence.FactOrigins(answered=intake.answered_fields(answers))
    facts = {f.fact: f for f in evidence.fact_list(profile, d, origins)}
    assert (facts["planning_uses"].value, facts["planning_uses"].origin) == (
        "Limited Restaurant",
        "intake_answer",
    )
    assert not facts["planning_uses"].derived
    assert "food_service" not in facts


def test_a_bar_that_serves_alcohol_lists_no_kind_of_food_or_drink_service() -> None:
    """On 22501ef every report for a bar listed "Kind of food or drink service: None, worked out by the rules from
    your description" (the fact holds no value for a Bar); the web fixture carried it three times."""
    profile = BusinessProfile.model_validate(
        {"business_type": "bar", "serves_alcohol": True, "stories": ["first"]}
    )
    d = pathway.determine(profile, NC_2, [], [], SITE, ["zoning_use"])
    facts = [f.fact for f in evidence.fact_list(profile, d, evidence.FactOrigins())]
    assert "food_service" not in facts


# ---- "Other, or not sure": the input stays not known and named --------------------------------------------------
def test_other_or_not_sure_keeps_it_not_known_and_named() -> None:
    profile, d = zero_proof(IntakeAnswers(food_service="other"))
    assert profile.food_service == "other"
    concept = concept_facts(profile)
    assert concept.food_service.missing and concept.planning_uses.value == ()
    assert d.pathway.use == "not_covered"
    assert "alcohol" not in {r.area for r in d.rows}
    t1 = tg.by_id(d.pathway.triggers, "T1")
    assert (t1.control, t1.missing_inputs) == ("not_decided", [FOOD])
    assert t1.lines[0].text == (
        "The business is described as a bar that serves no alcohol. A Bar provides on-site alcoholic beverage sales "
        "for drinking on the premises, so this business is not a Bar. You answered that it is another kind of food "
        "or drink service, or that you are not sure, so the rules do not know which use it is; no use control was "
        "looked up."
    )
    assert FOOD in row(d, "zoning_use").missing_inputs
    (asked,) = [q for q in d.open_questions if FOOD in q.question]
    assert asked.intake_question == "food_service"


def test_other_with_no_alcohol_answered_says_both_answers() -> None:
    _, d = through_the_runner(
        {"business_type": "bar", "stories": ["first"]},
        MOCKTAIL_QUOTES,
        MOCKTAIL,
        IntakeAnswers(liquor_licence="none", food_service="other"),
    )
    line = tg.by_id(d.pathway.triggers, "T1").lines[0].text
    assert line.startswith("The business is described as a bar, and you answered that it serves no alcohol.")
    assert "You answered that it is another kind of food or drink service, or that you are not sure" in line


# ---- 3. the missing input points at the question --------------------------------------------------------------------
def test_the_missing_kind_of_service_points_at_its_question() -> None:
    _, d = zero_proof(IntakeAnswers())
    (asked,) = [q for q in d.open_questions if FOOD in q.question]
    assert asked.intake_question == "food_service"
    assert pathway.intake_question_for(FOOD) == "food_service"
    # the same where the "No alcohol" answer, not the description, said it serves none
    _, d = through_the_runner(
        {"business_type": "bar", "stories": ["first"]},
        MOCKTAIL_QUOTES,
        MOCKTAIL,
        IntakeAnswers(liquor_licence="none"),
    )
    (asked,) = [q for q in d.open_questions if FOOD in q.question]
    assert asked.intake_question == "food_service"


# ---- the answer is read only for a bar that serves no alcohol ---------------------------------------------------------
@pytest.mark.parametrize(
    ("model", "quotes", "text", "use"),
    [
        # a restaurant: the kind of business the description gives decides the use
        (
            {"business_type": "restaurant", "stories": ["first"]},
            [("business_type", "Indian restaurant"), ("stories", "ground floor")],
            "Indian restaurant on the ground floor",
            "restaurant",
        ),
        # a bar the description does not say serves no alcohol is still a Bar (a Bar sells alcohol by definition)
        (
            {"business_type": "bar", "stories": ["first"]},
            [("business_type", "cocktail bar"), ("stories", "ground floor")],
            "A cocktail bar on the ground floor",
            "bar",
        ),
    ],
)
@pytest.mark.parametrize(
    ("answer", "said"),
    [
        ("limited_restaurant", "that it is a Limited Restaurant"),
        ("restaurant", "that it is a Restaurant"),
        # on 1a531f2: "You answered that it is another kind of food or drink service, or that you are not sure to
        # the question on the kind of food or drink service.", one run-on clause
        ("other", "that it is another kind of food or drink service, or that you are not sure"),
    ],
)
def test_for_any_other_business_the_answer_is_not_read_and_a_line_says_so(
    model: dict[str, Any], quotes: list[tuple[str, str]], text: str, use: str, answer: str, said: str
) -> None:
    profile, d = through_the_runner(
        model, quotes, text, IntakeAnswers.model_validate({"food_service": answer})
    )
    assert d.pathway.use == use
    assert d.pathway.lines[0].rule_id == "zoning.food_service"
    assert d.pathway.lines[0].text == (
        f"To the question on the kind of food or drink service, you answered {said}. That question is read only "
        "for a business described as a bar that serves no alcohol, which is not a Bar; the rules read the use from "
        "the kind of business the description gives."
    )
    assert row(d, "zoning_use").basis[0].text == d.pathway.lines[0].text
    without, _ = through_the_runner(model, quotes, text, IntakeAnswers())
    # nothing else changes
    assert concept_facts(profile).planning_uses == concept_facts(without).planning_uses


def test_the_mapping_puts_the_answer_on_the_profile_as_given() -> None:
    base = BusinessProfile.model_validate({"business_type": "bar"})
    for answer in ("restaurant", "limited_restaurant", "other"):
        out = apply_intake_answers(base, IntakeAnswers.model_validate({"food_service": answer}))
        assert out.food_service == answer and out.intake_answered == ["food_service"]
        # the answer alone does not say the business serves no alcohol: it is read only where something else does
        assert pathway.planning_use(out) == "bar"


# ---- 4. answer rounds through the API ---------------------------------------------------------------------------------
ZERO_PROOF_SCRIPT_PROFILE: dict[str, Any] = {
    **BASE_PROFILE,
    "serves_alcohol": False,
    "alcohol_type": "none",
    "live_entertainment": False,
    "amplified_sound": False,
    "closes_after_midnight": False,
    "stories": ["first"],
}
ZERO_PROOF_SCRIPT_QUOTES = [{"field": f, "quote": q} for f, q in ZERO_PROOF_QUOTES]


def _zero_proof_script() -> MemoScript:
    return MemoScript(profile=dict(ZERO_PROOF_SCRIPT_PROFILE), intake_quotes=list(ZERO_PROOF_SCRIPT_QUOTES))


def test_a_zero_proof_bar_is_not_a_bar_through_the_runner(client: TestClient, db: MemoryDatabase) -> None:
    """On 22501ef the runner reset the stated-facts check's `no_alcohol_stated` with the fields the model may not
    set (`AgentRunner._merge_profile`), so a "zero-proof cocktail bar" was read as a Bar in a real memo, with an
    alcohol row, though the rules (pathway rule 1b) say it is not one."""
    tma._use_runner(lambda: tma._runner(FakeAnthropic(_zero_proof_script())))
    row_ = tma._row(db, tma._new_memo(client, description=ZERO_PROOF))
    assert row_["profile"]["no_alcohol_stated"] is True
    assert row_["intake_basis"]["profile"]["no_alcohol_stated"] is True
    assert row_["memo"]["pathway"]["use"] == "not_covered"
    assert "alcohol" not in [r["area"] for r in row_["memo"]["approvals"]]
    asked = [q for q in row_["memo"]["could_not_establish"] if FOOD in q["question"]]
    assert [q["intake_question"] for q in asked] == ["food_service"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"licence_type": "48"},
        {"licences_held": ["48"]},
        {"outdoor_alcohol_service": True},
        {"serves_alcohol": True},
    ],
)
def test_an_override_that_says_alcohol_is_served_keeps_a_zero_proof_bar_a_bar(
    client: TestClient, db: MemoryDatabase, overrides: dict[str, Any]
) -> None:
    """On 1a531f2 the runner put the check's `no_alcohol_stated` back after the overrides were applied, though the
    check refuses it where a licence type, a licence held or alcohol served outdoors is given: a "zero-proof cocktail
    bar" given the licence type 48 by an override was looked up as a Bar with no alcohol row. The flag is read again
    on the profile with the overrides."""
    tma._use_runner(lambda: tma._runner(FakeAnthropic(_zero_proof_script())))
    row_ = tma._row(db, tma._new_memo(client, description=ZERO_PROOF, profile_overrides=overrides))
    assert row_["profile"]["no_alcohol_stated"] is False
    assert row_["intake_basis"]["profile"]["no_alcohol_stated"] is False
    assert row_["memo"]["pathway"]["use"] == "bar"
    assert "alcohol" in [r["area"] for r in row_["memo"]["approvals"]]


def test_a_round_with_the_kind_of_service_over_a_stored_licence_is_refused(
    client: TestClient, db: MemoryDatabase
) -> None:
    """The finding of 1a531f2 through the API: a bar whose stored answers say a new licence and full liquor, then a
    round of {food_service: "restaurant"} alone. It is refused (422) and the memo stays as it was; with "No alcohol"
    sent too, the round runs."""
    memo_id = tma._new_memo(
        client, intake={"liquor_licence": "new", "alcohol_served": "full_liquor", "stories": ["first"]}
    )
    before = dict(tma._row(db, memo_id))
    status, body, _ = tma.answer(client, memo_id, {"food_service": "restaurant"})
    assert status == 422 and body["detail"]["code"] == "validation_error", body
    assert body["detail"]["message"] == ANSWERS_FOOD_SERVICE_MESSAGE
    assert tma._row(db, memo_id) == before

    tma._use_runner(lambda: tma._runner(tma.NoModel()))
    status, events, _ = tma.answer(client, memo_id, {"liquor_licence": "none", "food_service": "restaurant"})
    assert status == 200 and events[-1][0] == "memo", events
    assert tma._row(db, memo_id)["intake"] == {
        "liquor_licence": "none",
        "food_service": "restaurant",
        "stories": ["first"],
    }


def test_an_answer_round_gives_a_zero_proof_bar_its_use_with_no_model_call(
    client: TestClient, db: MemoryDatabase, many_previews: None
) -> None:
    tma._use_runner(lambda: tma._runner(FakeAnthropic(_zero_proof_script())))
    memo_id = tma._new_memo(client, description=ZERO_PROOF)
    before = tma._row(db, memo_id)
    assert before["memo"]["pathway"]["use"] == "not_covered"

    tma._use_runner(lambda: tma._runner(tma.NoModel()))  # a round makes no model call
    status, events, _ = tma.answer(client, memo_id, {"food_service": "limited_restaurant"})
    assert status == 200 and events[-1][0] == "memo", events
    after = tma._row(db, memo_id)
    memo = after["memo"]
    assert after["intake"] == {"food_service": "limited_restaurant"}
    assert memo["pathway"]["use"] == "limited_restaurant"
    assert "alcohol" not in [r["area"] for r in memo["approvals"]]
    for r in memo["approvals"]:
        assert FOOD not in r["missing_inputs"], r["area"]
    assert not [q for q in memo["could_not_establish"] if FOOD in q["question"]]
    assert memo["pathway"]["lines"][0]["text"].endswith(
        "You answered that it is a Limited Restaurant, and the rules read that use."
    )
    # the same as a new memo with the same description and the answer
    tma._use_runner(lambda: tma._runner(FakeAnthropic(_zero_proof_script())))
    fresh = tma._row(db, tma._new_memo(client, description=ZERO_PROOF, intake=after["intake"]))
    assert tma._without_time(memo) == tma._without_time(fresh["memo"])


# A round recomputes the headline findings (app.memo.pathway rule 9). 2301 Chestnut St (NC-2, use size from 4,001
# square feet) with the ACTIVE Type 47 licence on file there (tests/test_memo_headline.py): a 6,000 square foot
# Restaurant reads as continuing, so T7 needs a Conditional Use only if the business is enlarged or storefronts are
# merged. The store and the geocoder are the seeded ones of the answers tests, with that zoning and that licence.
CHESTNUT_LICENCE = Application.model_validate(
    json.loads(
        (Path(__file__).parent / "fixtures" / "abc_636535_2301_chestnut.json").read_text(encoding="utf-8")
    )["record"]
)
assert CHESTNUT_LICENCE.lat is not None and CHESTNUT_LICENCE.lng is not None
CHESTNUT_GEO = GeocodeResult(
    address="2301 Chestnut St, San Francisco, CA 94123",
    normalized_address="2301 CHESTNUT ST",
    lat=CHESTNUT_LICENCE.lat,
    lng=CHESTNUT_LICENCE.lng,
    parcel="0936/001",
    zip_code="94123",
    source="datasf_eas",
    source_url="https://data.sf.gov/d/eas",
    confidence=1.0,
)
CHESTNUT_DESC = "Restaurant with a full bar"
CHESTNUT_SCRIPT_PROFILE: dict[str, Any] = {
    **BASE_PROFILE,
    "business_type": "restaurant",
    "serves_alcohol": True,
    "alcohol_type": "full_liquor",
    "live_entertainment": False,
    "amplified_sound": False,
    "closes_after_midnight": False,
}
CHESTNUT_ANSWERS = {
    "part_of_chain": False,
    "floor_area_sqft": 6000,
    "liquor_licence": "new",
    "alcohol_served": "full_liquor",
    "stories": ["first"],
}
ENLARGED = "the existing business is enlarged or storefronts are merged"


class ChestnutStore(LocalStore):
    """The seeded local store, read at 2301 Chestnut St: NC-2 zoning, no overlay."""

    async def zoning_at(self, lat: float, lng: float) -> ZoningInfo | None:
        return NC_2

    async def overlays_at(self, lat: float, lng: float, *, snap_m: float = 30.0) -> list[Any]:
        return []


class ChestnutGeocoder(FakeGeocoder):
    async def geocode(self, address: str) -> GeocodeResult | None:
        self.calls.append(address)
        return CHESTNUT_GEO if "chestnut" in address.lower() else None


def _headline(memo: dict[str, Any]) -> list[tuple[str, str, bool, str | None]]:
    return [(h["kind"], h["trigger"], h["definite"], h.get("condition")) for h in memo["headline_findings"]]


async def _seed(path: Path) -> ChestnutStore:
    store = ChestnutStore(path)
    await store.upsert_applications([CHESTNUT_LICENCE])
    return store


@pytest.mark.parametrize(
    ("change", "headline", "lead"),
    [
        (
            "enlarge",
            [("conditional", "T7", True, None)],
            "A Conditional Use Authorization is needed (use size). ",
        ),
        ("none", [], "Of the 4 approvals this concept needs: 1 further review (alcohol licence), 3 allowed"),
    ],
)
def test_an_answer_round_recomputes_the_headline_findings(
    client: TestClient,
    db: MemoryDatabase,
    many_previews: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
    headline: list[tuple[str, str, bool, str | None]],
    lead: str,
) -> None:
    import anyio

    import app.memo.context as ctx
    import app.routes.memos as memo_routes
    import app.tools.precedent_tools as pt

    store = anyio.run(_seed, tmp_path / "chestnut")
    geocoder = ChestnutGeocoder()
    for mod in (ctx, pt, memo_routes):
        if hasattr(mod, "get_store"):
            monkeypatch.setattr(mod, "get_store", lambda: store)
        if hasattr(mod, "get_geocoder"):
            monkeypatch.setattr(mod, "get_geocoder", lambda: geocoder)

    def runner(model: Any) -> MemoRunner:
        return MemoRunner(model, get_catalog(), settings, store, geocoder, today=TODAY)

    tma._use_runner(lambda: runner(FakeAnthropic(MemoScript(profile=dict(CHESTNUT_SCRIPT_PROFILE)))))
    memo_id = tma._new_memo(
        client, address=CHESTNUT_GEO.address, description=CHESTNUT_DESC, intake=dict(CHESTNUT_ANSWERS)
    )
    before = tma._row(db, memo_id)["memo"]
    assert before["pathway"]["existing_use"] == "restaurant"
    assert _headline(before) == [("conditional_if", "T7", False, ENLARGED)]
    assert before["overall"]["line"].startswith(
        "A Conditional Use Authorization is needed if the existing business is enlarged or storefronts are merged "
        "(use size). "
    )

    tma._use_runner(lambda: runner(tma.NoModel()))
    status, events, _ = tma.answer(client, memo_id, {"existing_business_change": change})
    assert status == 200 and events[-1][0] == "memo", events
    after = tma._row(db, memo_id)
    assert after["answers_round"] == 1
    assert _headline(after["memo"]) == headline
    assert after["memo"]["overall"]["line"].startswith(lead)
    if headline:
        assert after["memo"]["overall"]["status"] == "further_review"
    # the version the round replaced keeps the headline it had
    (rev,) = db.tables["memo_revisions"]
    assert _headline(rev["memo"]) == [("conditional_if", "T7", False, ENLARGED)]
    # the same as a new memo with the merged answers
    tma._use_runner(lambda: runner(FakeAnthropic(MemoScript(profile=dict(CHESTNUT_SCRIPT_PROFILE)))))
    fresh = tma._row(
        db,
        tma._new_memo(
            client, address=CHESTNUT_GEO.address, description=CHESTNUT_DESC, intake=after["intake"]
        ),
    )
    assert tma._without_time(after["memo"]) == tma._without_time(fresh["memo"])
