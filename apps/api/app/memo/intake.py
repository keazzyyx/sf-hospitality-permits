"""The optional intake questions, and how their answers reach the profile. No I/O, no model call, no clock.

Every question is optional, and each gives one fact the rules read. They are asked on the page where a report is
started, under the description, in two groups (`IntakeQuestion.group`):

  "main"  the facts most reports turn on, always shown:
            1. Is the business part of a chain? With a follow-up when the answer is yes: how many other locations?
            2. The floor area, in square feet.
            3. How the liquor licence will be obtained: new, a transfer from another owner, a transfer from another
               location, a licence already held at this address, or no alcohol.
            4. Which stories the business occupies.
            5. What alcohol will be served: beer and wine, or spirits too.
            6. The closing time.
            7. What the space was last used as.
            8. Whether the space is for fewer than 50 people.
            9. Where the outdoor area is. With a follow-up when there is one: is alcohol served there?
           10. What kind of food or drink service it is: asked only for a business that serves no alcohol, which is
               not a Bar (Planning Code § 102, pathway rule 1b). The page shows it under the liquor licence question
               once "No alcohol" is answered, or when the report asked for it (the description says the bar serves
               no alcohol).
  "more"  facts only some reports ask for, shown under "More details" (the report names each one it needs):
            whether an existing business is enlarged or intensified, the floor area before the project, whether
            storefronts are merged, whether the conditions of an earlier approval change, the kind of
            entertainment, and the existing occupancy group of the space.

WHY THEY ARE ALL HERE (change of 2026-11-15, approved with the release of 2026-11-16). The rules never fill a missing
input with an assumption, so a row whose input is missing is "Insufficient information" and names it. Before this
date only questions 1 to 3 could be answered outside the description: a report for a restaurant whose description
did not say which story it is on, what it pours, what the space was before or where the patio is left four of its
five rows undecided, with no way for the applicant to give those facts except by rewriting the description. Now
every input a row or a trigger can name from `app.memo.facts.MISSING_PHRASES` (and the existing occupancy group of
`app.memo.rows`), but the kind of business, the seats, the licences already held and the licence type, has a
question (since 2026-11-16 also the kind of food or drink service of a bar that serves no alcohol, which the report
named before with no question to answer it), and
`question_for_fact` gives the question for a named input, so the report can point at it. No question gives "the
licence type" itself: it is named only where what is poured would not decide it
(`app.memo.facts.ConceptFacts.licence_type_missing_name`), and the report reads its question for the concept
(`app.memo.pathway._intake_question`): the liquor licence question when alcohol is not established, none for a
hotel or a caterer that serves alcohol.

`apply_intake_answers(profile, answers)` maps the answers onto the profile by code, after the intake model has
built it from the description and before the rules read it. An answer always wins over what the model read from
the description. A skipped answer (None) changes nothing, so the fact stays as the description gave it, and when
the description does not give it either the rules answer "Insufficient information" and name it, in the fixed
phrase of `app.memo.facts.MISSING_PHRASES` that matches the question.

The questions can also be answered on a memo already made, with no model call: an answer round
(`app.memo.answers`, owner decision of 2026-11-16) merges the new answers into the stored ones
(`app.memo.answers.merge_answers`) and puts them on the intake result kept with the memo by this same function.

Where an answer comes from: `app.memo.facts` reads any value the profile holds for these facts as "stated" (the
input gave it), whether the description or an intake answer gave it, and both come from the applicant. The
additions the answers need are `BusinessProfile.part_of_chain`: it holds the chain answer itself, so the rules can
tell "part of a chain, count skipped" (they name the count) from "chain question skipped" (they name the chain
question); `BusinessProfile.no_alcohol_answer_over_description`: the applicant answered "No alcohol" where the
description served alcohol, so the rules can say the answer won;
`BusinessProfile.outdoor_alcohol_answer_over_description`: alcohol outdoors is the only alcohol answer and the
description did not say alcohol is served, so the alcohol row can say the two disagree;
`BusinessProfile.occupants_under_50`, `BusinessProfile.existing_occupancy_group` and `BusinessProfile.food_service`,
which only an answer gives;
`BusinessProfile.intake_answered`, the fields the answers set (`answered_fields`), so a rule line can say "You
answered ..." for a fact an answer gave and "The description says ..." for one the description gave. All are set
here only; the intake model's tool schema does not show them.

THE MAPPING (for review)
  part_of_chain   False                       -> formula_retail False (other_locations cleared)
                  True, other_locations >= 11 -> formula_retail True
                  True, other_locations < 11  -> formula_retail False (Planning Code § 303.1 counts formula retail
                                                 from eleven other establishments)
                  True, other_locations None  -> formula_retail None: the rules answer "not decided" and name the
                                                 count
                  part_of_chain is stored as given; other_locations is stored when given
  floor_area_sqft                             -> square_feet
  liquor_licence  "new"                       -> alcohol_transaction "new_licence", serves_alcohol True
                  "transfer_from_another_owner"    -> "person_to_person_transfer", serves_alcohol True
                  "transfer_from_another_location" -> "premises_transfer", serves_alcohol True
                  "already_held"                   -> "licence_already_held", serves_alcohol True
                  (an applicant with a licence serves alcohol; alcohol_type stays as the description gave it, so
                  a description that does not say what is poured leaves it "unknown" once normalised, and the
                  rules name what alcohol will be served, unless `alcohol_served` answers it)
                  "none" ("No alcohol")       -> serves_alcohol False, alcohol_type "none", and the licence type
                                                 and transaction the description gave are cleared (an outdoor
                                                 alcohol service it stated becomes False), whatever the
                                                 description said: the applicant's answer wins. When the
                                                 description served alcohol, no_alcohol_answer_over_description
                                                 is set and the rules say so in a line (pathway rule 1a).
  A licence already held is never inferred here from what the description says about alcohol: only the
  "already_held" answer sets it (before decision 2 a "none" answer did, for a description that served alcohol).
  The intake model may still give it where the description states it in words (a stated fact, app.agents.prompts).
  stories         one or more of basement, first, second, third_or_above -> stories, in the fixed order of `Story`
  alcohol_served  "beer_wine" / "full_liquor" -> serves_alcohol True, alcohol_type as answered (the licence type
                                                 is then derived by the rules, `facts._licence_type`, and a
                                                 licence type the check cleared is no longer named as not known:
                                                 `facts.concept_facts`). Refused with liquor_licence "none": the
                                                 two answers contradict.
  closing_time    "HH:MM" (24-hour)           -> closing_hour, and closes_after_midnight / closes_after_2am from the
                                                 same time (as `facts.profile_from_facts` sets them)
  last_use        one `ExistingUse` but "vacant" -> existing_use_stated [that use]. "vacant" is not offered: it
                                                 names no last use (`rows._planning_change`), so the question asks
                                                 what an empty space was last used as.
  fewer_than_50_people  True / False          -> occupants_under_50. True with a seat count of 50 or more is not
                                                 read either way: the building row names the conflict
                                                 (`app.memo.rows`, change of occupancy).
  outdoor_area    "none"                      -> outdoor_area "none", outdoor_seating False, sidewalk_or_parklet
                                                 False, outdoor_alcohol_service False (the applicant's answer
                                                 wins over the description; with no outdoor area there is no
                                                 alcohol served in one, and the question is not asked)
                  a place                     -> outdoor_area as answered, outdoor_seating True,
                                                 sidewalk_or_parklet True for "sidewalk" only
  outdoor_alcohol_service  True / False       -> outdoor_alcohol_service. True also sets outdoor_seating True:
                                                 the answer says there is an outdoor area, so the outdoor row is
                                                 read; where it is stays as the outdoor_area answer or the
                                                 description gave it, and is not known when neither does (a
                                                 description's outdoor_area "none" is cleared), so the row names
                                                 the outdoor-area question. True also sets serves_alcohol True: the
                                                 business serves alcohol, so the alcohol row is read. Where it is
                                                 the only alcohol answer and the description did not say alcohol
                                                 is served, outdoor_alcohol_answer_over_description is set and the
                                                 alcohol row says the two disagree (the answer is read: the safe
                                                 reading, since the licence is then checked). Refused with
                                                 outdoor_area "none", and True is refused with liquor_licence
                                                 "none".
  existing_business_change  none / enlarge / intensify / enlarge_and_intensify -> changes_existing_business. The
                                                 rules read any stated value, "none" included, as "a business of
                                                 this kind is already there and stays" (`rows.existing_use_continues`,
                                                 pathway rule 4), so the question says so and is answered only then.
  floor_area_before_sqft                      -> floor_area_before_sqft
  merges_storefronts  True / False            -> merges_storefronts
  amends_prior_approval  True / False         -> amends_prior_approval
  entertainment   "none"                      -> entertainment_kind "none"; live_entertainment, amplified_sound and
                                                 dancing False (the applicant's answer wins over the description)
                  "limited_live_performance" / "place_of_entertainment" -> entertainment_kind as answered
  existing_occupancy_group  "B" / "A-2"       -> existing_occupancy_group (the rules compare it with the proposed
                                                 group; no public record shows it)
  food_service    "restaurant" / "limited_restaurant" / "other" -> food_service (owner decision of 2026-11-16: "a
                                                 business that serves no alcohol is not a Bar use (Planning Code
                                                 § 102). No alcohol row, and ask what kind of food or drink service
                                                 it is; don't assume."). The rules read it only for a business
                                                 described as a bar that serves no alcohol (`pathway.not_a_bar`):
                                                 "restaurant" and "limited_restaurant" are then its use, as answered,
                                                 and "other" ("Other, or not sure") gives none, so the kind of
                                                 service stays not known and is named. For any other business the
                                                 kind of business the description gives decides the use, and a line
                                                 says the answer was not read (`pathway.LEGAL_BASIS`,
                                                 "zoning.food_service/not_read"). Refused with an answer that says
                                                 alcohol is served (a liquor licence other than "none", what is
                                                 poured, alcohol served outdoors): the question is asked only for a
                                                 business that serves none.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.profile import (
    AlcoholTransaction,
    BusinessProfile,
    EntertainmentKind,
    ExistingBusinessChange,
    FoodService,
    OccupancyGroup,
    OutdoorArea,
    Story,
)

LiquorLicence = Literal[
    "new", "transfer_from_another_owner", "transfer_from_another_location", "already_held", "none"
]
AlcoholServed = Literal["beer_wine", "full_liquor"]
# `ExistingUse` without "vacant": an empty space is asked what it was last used as.
LastUse = Literal[
    "restaurant", "bar", "limited_restaurant", "nighttime_entertainment", "retail", "laundromat", "other"
]
QuestionId = Literal[
    "part_of_chain",
    "other_locations",
    "floor_area_sqft",
    "liquor_licence",
    "stories",
    "alcohol_served",
    "closing_time",
    "last_use",
    "fewer_than_50_people",
    "outdoor_area",
    "outdoor_alcohol_service",
    "food_service",
    "existing_business_change",
    "floor_area_before_sqft",
    "merges_storefronts",
    "amends_prior_approval",
    "entertainment",
    "existing_occupancy_group",
]
# The existing occupancy group is the one input a question gives that is not a fact of `facts.MISSING_PHRASES`:
# `app.memo.rows.EXISTING_GROUP_PHRASE` names it (a test checks the two strings are the same).
EXISTING_OCCUPANCY_GROUP_FACT = "existing_occupancy_group"
EXISTING_OCCUPANCY_GROUP_PHRASE = (
    "the existing occupancy group of the space, which only plans or an inspection show"
)

# Planning Code § 303.1(b): a Formula Retail use "has eleven or more other retail sales establishments in
# operation, or with local land use or permit entitlements already approved, located anywhere in the world". The
# dated control data (citywide "formula_retail_definition", fact `other_establishments_minimum`) gives 11 in every
# version on file; a test reads it from there.
FORMULA_RETAIL_OTHER_LOCATIONS = 11
# Sane bounds for the two numbers. The largest floor area among the 40 backtest cases is 24,138 square feet.
OTHER_LOCATIONS_MAX = 100_000
FLOOR_AREA_MAX_SQFT = 1_000_000
# backtest/inputs.json writes a chain the record calls Formula Retail without giving its count as "11_or_more".
ELEVEN_OR_MORE = "11_or_more"

# What a liquor licence answer sets.
TRANSACTION_FOR_LICENCE: dict[str, AlcoholTransaction] = {
    "new": "new_licence",
    "transfer_from_another_owner": "person_to_person_transfer",
    "transfer_from_another_location": "premises_transfer",
    "already_held": "licence_already_held",
}
# The answer that says the business serves no alcohol.
NO_ALCOHOL = "none"
# A closing time after midnight and up to this minute is a late close (app.memo.facts.LATE_CLOSE_UNTIL; a test
# checks the two are the same).
LATE_CLOSE_UNTIL = 6 * 60

_Count = Annotated[int, Field(strict=True, ge=0, le=OTHER_LOCATIONS_MAX)]
_Area = Annotated[int, Field(strict=True, ge=1, le=FLOOR_AREA_MAX_SQFT)]
_YesNo = Annotated[bool, Field(strict=True)]
# A closing time as the profile holds it: HH:MM on the 24-hour clock ("02:00" is 2 a.m., "23:30" is 11:30 p.m.).
CLOSING_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class IntakeAnswers(BaseModel):
    """The applicant's answers. Every key is optional; None is a skipped question."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    part_of_chain: Annotated[bool, Field(strict=True)] | None = None
    other_locations: _Count | None = None
    floor_area_sqft: _Area | None = None
    liquor_licence: LiquorLicence | None = None
    stories: Annotated[list[Story], Field(min_length=1, max_length=len(get_args(Story)))] | None = None
    alcohol_served: AlcoholServed | None = None
    closing_time: Annotated[str, Field(pattern=CLOSING_TIME_PATTERN)] | None = None
    last_use: LastUse | None = None
    fewer_than_50_people: _YesNo | None = None
    outdoor_area: OutdoorArea | None = None
    outdoor_alcohol_service: _YesNo | None = None
    food_service: FoodService | None = None
    existing_business_change: ExistingBusinessChange | None = None
    floor_area_before_sqft: _Area | None = None
    merges_storefronts: _YesNo | None = None
    amends_prior_approval: _YesNo | None = None
    entertainment: EntertainmentKind | None = None
    existing_occupancy_group: OccupancyGroup | None = None

    @field_validator("stories")
    @classmethod
    def _each_story_once_in_order(cls, v: list[Story] | None) -> list[Story] | None:
        """The stories in the fixed order of `Story`, each once, whatever order they were ticked in."""
        if v is None:
            return None
        if len(set(v)) != len(v):
            raise ValueError("each story is given once")
        return [s for s in get_args(Story) if s in v]

    @model_validator(mode="after")
    def _count_needs_a_chain(self) -> IntakeAnswers:
        if self.other_locations is not None and self.part_of_chain is not True:
            raise ValueError("other_locations is asked only when part_of_chain is true")
        return self

    @model_validator(mode="after")
    def _answers_agree(self) -> IntakeAnswers:
        """Two answers that contradict each other are refused, so neither is silently dropped."""
        if self.liquor_licence == NO_ALCOHOL and self.alcohol_served is not None:
            raise ValueError('alcohol_served cannot be answered with liquor_licence "none" (no alcohol)')
        if self.liquor_licence == NO_ALCOHOL and self.outdoor_alcohol_service is True:
            raise ValueError('outdoor_alcohol_service cannot be true with liquor_licence "none" (no alcohol)')
        if self.outdoor_area == "none" and self.outdoor_alcohol_service is not None:
            raise ValueError("outdoor_alcohol_service is asked only when there is an outdoor area")
        if self.food_service is not None and self.serves_alcohol_by_answer:
            raise ValueError("food_service is asked only for a business that serves no alcohol")
        return self

    @property
    def serves_alcohol_by_answer(self) -> bool:
        """An answer says alcohol is served: a liquor licence other than "No alcohol", what is poured, or alcohol
        served outdoors."""
        return (
            self.liquor_licence in TRANSACTION_FOR_LICENCE
            or self.alcohol_served is not None
            or self.outdoor_alcohol_service is True
        )

    def answered(self) -> tuple[QuestionId, ...]:
        """The questions answered, in the order they are asked."""
        return tuple(q.id for q in QUESTIONS if getattr(self, q.id) is not None)

    @property
    def empty(self) -> bool:
        return not self.answered()


# ---- the questions, as the page asks them ---------------------------------------------------------------
@dataclass(frozen=True)
class IntakeOption:
    value: str
    label: str


@dataclass(frozen=True)
class IntakeQuestion:
    id: QuestionId
    question: str
    # "multi_choice": one or more of the answers (the stories); "time": a time of day, sent as HH:MM (24-hour)
    kind: Literal["yes_no", "number", "choice", "multi_choice", "time"]
    answers: tuple[IntakeOption, ...]  # the allowed answers of a choice; empty for a number or a time
    help: str
    # the `ConceptFacts` fact the answer gives (its phrase is named when the question is skipped), or
    # EXISTING_OCCUPANCY_GROUP_FACT
    fact: str
    unit: str | None = None
    minimum: int | None = None
    maximum: int | None = None
    shown_when: str | None = None  # a follow-up: shown only when this answer is given
    # "main": always shown; "more": shown under "More details" (only some reports ask for it)
    group: Literal["main", "more"] = "main"


# Printed under every question: each is optional, and skipping it is never read as "no".
SKIP_NOTE = "Optional. If you skip it, the report will say it could not tell."
SKIP_LABEL = "Skip"

QUESTIONS: tuple[IntakeQuestion, ...] = (
    IntakeQuestion(
        id="part_of_chain",
        question="Is the business part of a chain that shares its name, look or menu with other locations?",
        kind="yes_no",
        answers=(IntakeOption("yes", "Yes"), IntakeOption("no", "No")),
        help=(
            "Planning Code § 303.1 treats a business as formula retail when it has eleven or more other "
            "locations and shares two or more standard features with them, such as its name or trademark, "
            "signage, facade, decor or a standard range of merchandise."
        ),
        fact="formula_retail",
    ),
    IntakeQuestion(
        id="other_locations",
        question="How many other locations does the chain have, open or approved, anywhere in the world?",
        kind="number",
        answers=(),
        help=(
            "Count the locations already open and those with their permits approved. Eleven or more makes "
            "the business formula retail."
        ),
        fact="other_locations",
        unit="locations",
        minimum=0,
        maximum=OTHER_LOCATIONS_MAX,
        shown_when="part_of_chain=yes",
    ),
    IntakeQuestion(
        id="floor_area_sqft",
        question="What is the floor area of the business, in square feet?",
        kind="number",
        answers=(),
        help="Some districts need a Conditional Use for a business above a set size.",
        fact="floor_area_sqft",
        unit="square feet",
        minimum=1,
        maximum=FLOOR_AREA_MAX_SQFT,
    ),
    IntakeQuestion(
        id="liquor_licence",
        question="How will the liquor licence be obtained?",
        kind="choice",
        answers=(
            IntakeOption("new", "New licence"),
            IntakeOption("transfer_from_another_owner", "Transfer from another owner"),
            IntakeOption("transfer_from_another_location", "Transfer from another location"),
            IntakeOption("already_held", "Already hold a licence at this address"),
            IntakeOption("none", "No alcohol"),
        ),
        help=(
            "Some districts limit new licences, and state law tests a new licence or a transfer from another "
            "location for over-concentration."
        ),
        fact="alcohol_transaction",
    ),
    IntakeQuestion(
        id="stories",
        question="Which stories does the business occupy?",
        kind="multi_choice",
        answers=(
            IntakeOption("basement", "Basement"),
            IntakeOption("first", "First story (street level)"),
            IntakeOption("second", "Second story"),
            IntakeOption("third_or_above", "Third story or above"),
        ),
        help=(
            "The zoning tables set the control for a business story by story, so the report cannot decide the "
            "zoning row without it. Pick every story the business will use."
        ),
        fact="stories",
    ),
    IntakeQuestion(
        id="alcohol_served",
        question="What alcohol will be served: beer and wine, or spirits too?",
        kind="choice",
        answers=(
            IntakeOption("beer_wine", "Beer and wine only"),
            IntakeOption("full_liquor", "Spirits too (a full bar)"),
        ),
        help=(
            "It decides the licence type: a restaurant that pours beer and wine takes a Type 41 licence and one "
            "that pours spirits a Type 47; a bar takes a Type 42 or a Type 48."
        ),
        fact="alcohol_served",
        shown_when="liquor_licence!=none",
    ),
    IntakeQuestion(
        id="closing_time",
        question="What is the closing time?",
        kind="time",
        answers=(),
        help=(
            "Each district permits business hours up to a set time and asks for a Conditional Use after it. "
            "Give the latest closing time of the week."
        ),
        fact="closing",
    ),
    IntakeQuestion(
        id="last_use",
        question="What was the space last used as?",
        kind="choice",
        answers=(
            IntakeOption("restaurant", "A restaurant"),
            IntakeOption("bar", "A bar"),
            IntakeOption("limited_restaurant", "A cafe or take-out counter (a limited restaurant)"),
            IntakeOption("nighttime_entertainment", "A nightclub or entertainment venue"),
            IntakeOption("retail", "A shop (retail)"),
            IntakeOption("laundromat", "A laundromat"),
            IntakeOption("other", "Something else"),
        ),
        help=(
            "It decides whether opening here is a change of use. If the space is empty now, pick what it was "
            "last used as."
        ),
        fact="existing_use_stated",
    ),
    IntakeQuestion(
        id="fewer_than_50_people",
        question="Is the space for fewer than 50 people?",
        kind="yes_no",
        answers=(IntakeOption("yes", "Yes"), IntakeOption("no", "No")),
        help=(
            "The Building Code treats a restaurant or bar for fewer than 50 people as Group B and a larger one "
            "as Assembly Group A-2. It is the number of people the space is built to hold (its occupant load), "
            "not only the seats."
        ),
        fact="occupants_under_50",
    ),
    IntakeQuestion(
        id="outdoor_area",
        question="Where is the outdoor area?",
        kind="choice",
        answers=(
            IntakeOption("none", "No outdoor area"),
            IntakeOption("front", "In front, on the lot"),
            IntakeOption("rear_or_side", "At the rear or side"),
            IntakeOption("rooftop", "On the roof"),
            IntakeOption("parking_lot", "In a parking lot"),
            IntakeOption("sidewalk", "On the sidewalk or in the parking lane"),
        ),
        help=(
            "An outdoor area in front is read differently from one at the rear, on the roof or on the sidewalk, "
            "so the report cannot decide the outdoor row without its place."
        ),
        fact="outdoor_area",
    ),
    IntakeQuestion(
        id="outdoor_alcohol_service",
        question="Will alcohol be served in the outdoor area?",
        kind="yes_no",
        answers=(IntakeOption("yes", "Yes"), IntakeOption("no", "No")),
        help="Some outdoor areas are permitted only where alcohol is brought to seated patrons by wait staff.",
        fact="outdoor_alcohol_service",
        shown_when="outdoor_area!=none",
    ),
    # Owner decision of 2026-11-16. The words of the two uses are Planning Code § 102's own ("Restaurant" and
    # "Restaurant, Limited", gocodebook.com mirror, read 2026-11-16; the dated control data carries the same
    # definitions, citywide "use_definitions"). Neither option is put first as the likely one: the report does not
    # assume either.
    IntakeQuestion(
        id="food_service",
        question="What kind of food or drink service is it?",
        kind="choice",
        answers=(
            IntakeOption("restaurant", "A Restaurant (cooked food served on the premises, with seating)"),
            IntakeOption(
                "limited_restaurant",
                "A Limited Restaurant (ready-to-eat food or drinks, with or without seating)",
            ),
            IntakeOption("other", "Other, or not sure"),
        ),
        help=(
            "Asked for a business that serves no alcohol: Planning Code § 102 defines a Bar by its on-site alcohol "
            'sales, so such a business is not a Bar. Under § 102 a Restaurant "serves prepared, ready-to-eat cooked '
            'foods to customers for consumption on the premises" and has seating; it may serve them to take away '
            'only as a minor and incidental use. A Limited Restaurant "serves ready-to-eat foods and/or drinks to '
            'customers for consumption on or off the premises", with or without seating, for example a sandwich '
            "shop, coffee house, pizzeria or ice cream shop."
        ),
        fact="food_service",
        shown_when="liquor_licence=none",
    ),
    IntakeQuestion(
        id="existing_business_change",
        question="Is an existing business to be enlarged or intensified?",
        kind="choice",
        answers=(
            IntakeOption("none", "No: it stays as it is"),
            IntakeOption("enlarge", "Enlarged (more floor area)"),
            IntakeOption("intensify", "Intensified (new entertainment, longer hours or a stronger licence)"),
            IntakeOption("enlarge_and_intensify", "Both"),
        ),
        help=(
            "Answer only when a business of the same kind is already at the address and stays or is taken over: "
            "any answer tells the report that it is. Skip it when the space was something else."
        ),
        fact="changes_existing_business",
        group="more",
    ),
    IntakeQuestion(
        id="floor_area_before_sqft",
        question="What was the floor area before the project, in square feet?",
        kind="number",
        answers=(),
        help="The size rules compare the floor area before the project with the floor area after it.",
        fact="floor_area_before_sqft",
        unit="square feet",
        minimum=1,
        maximum=FLOOR_AREA_MAX_SQFT,
        group="more",
    ),
    IntakeQuestion(
        id="merges_storefronts",
        question="Are storefronts to be merged?",
        kind="yes_no",
        answers=(IntakeOption("yes", "Yes"), IntakeOption("no", "No")),
        help="The size rules ask whether two or more storefronts are combined into one business.",
        fact="merges_storefronts",
        group="more",
    ),
    IntakeQuestion(
        id="amends_prior_approval",
        question="Are the conditions of an earlier approval to be changed?",
        kind="yes_no",
        answers=(IntakeOption("yes", "Yes"), IntakeOption("no", "No")),
        help=(
            "Asked when an earlier approval at the address set conditions, such as hours: changing them goes "
            "back to the body that set them."
        ),
        fact="amends_prior_approval",
        group="more",
    ),
    IntakeQuestion(
        id="entertainment",
        question="Is there entertainment, and what kind?",
        kind="choice",
        answers=(
            IntakeOption("none", "No entertainment"),
            IntakeOption(
                "limited_live_performance", "Limited live performance (a Limited Live Performance permit)"
            ),
            IntakeOption(
                "place_of_entertainment", "A place of entertainment (a Place of Entertainment permit)"
            ),
        ),
        help="The kind of entertainment decides which Entertainment Commission permit applies.",
        fact="entertainment_kind",
        group="more",
    ),
    IntakeQuestion(
        id="existing_occupancy_group",
        question="What occupancy group do the plans or the certificate of occupancy of the existing space show?",
        kind="choice",
        answers=(IntakeOption("B", "Group B"), IntakeOption("A-2", "Assembly Group A-2")),
        help=(
            "No public record shows it. With it the report can say whether the Building Code occupancy changes; "
            "without it that question stays open until plans or an inspection show the group."
        ),
        fact=EXISTING_OCCUPANCY_GROUP_FACT,
        group="more",
    ),
)
QUESTION_BY_ID: dict[str, IntakeQuestion] = {q.id: q for q in QUESTIONS}


def question_for_fact(fact: str) -> IntakeQuestion | None:
    """The intake question that gives a fact of `app.memo.facts.MISSING_PHRASES` (or the existing occupancy
    group); None when no question gives it. "other_locations" has its own follow-up question. "licence_type" has
    none: the rules name it only where what is poured would not decide it (a hotel, a caterer, or what is poured
    already given), and name "alcohol_served" where it would, so no answer gives "the licence type" itself. Which
    answer settles why it is not known depends on the concept (`app.memo.pathway._intake_question`)."""
    return next((q for q in QUESTIONS if q.fact == fact), None)


# ---- the answers on the profile ---------------------------------------------------------------------------
def _mentions_alcohol(profile: BusinessProfile) -> bool:
    """The profile the description gave serves alcohol: the test `required_areas` and the rules use for the
    alcohol row (`pathway._serves_alcohol`), or a licence type, a transaction or outdoor alcohol service it
    states."""
    return (
        profile.serves_alcohol
        or profile.alcohol_type != "none"
        or profile.licence_type is not None
        or profile.alcohol_transaction is not None
        or profile.outdoor_alcohol_service is True
    )


def apply_intake_answers(profile: BusinessProfile, answers: IntakeAnswers) -> BusinessProfile:
    """The profile with the applicant's answers on it (see THE MAPPING in the module docstring). Pure: the
    profile passed in is not changed, and with no answer the same profile comes back."""
    if answers.empty:
        return profile
    data = profile.model_dump()
    chain = answers.part_of_chain
    if chain is not None:
        data["part_of_chain"] = chain
        if chain is False:
            data["formula_retail"] = False
            data["other_locations"] = None
        elif answers.other_locations is None:
            data["formula_retail"] = None  # a chain, count not given: the rules name the count
        else:
            data["other_locations"] = answers.other_locations
            data["formula_retail"] = answers.other_locations >= FORMULA_RETAIL_OTHER_LOCATIONS
    if answers.floor_area_sqft is not None:
        data["square_feet"] = answers.floor_area_sqft
    licence = answers.liquor_licence
    if licence in TRANSACTION_FOR_LICENCE:
        data["alcohol_transaction"] = TRANSACTION_FOR_LICENCE[licence]
        data["serves_alcohol"] = True
    elif licence == NO_ALCOHOL:
        data["no_alcohol_answer_over_description"] = _mentions_alcohol(profile)
        data["serves_alcohol"] = False
        data["alcohol_type"] = "none"
        data["licence_type"] = None
        data["alcohol_transaction"] = None
        if data["outdoor_alcohol_service"] is True:
            data["outdoor_alcohol_service"] = False
    if answers.stories is not None:
        data["stories"] = list(answers.stories)
    if answers.alcohol_served is not None:
        data["serves_alcohol"] = True
        data["alcohol_type"] = answers.alcohol_served
    if answers.closing_time is not None:
        hour, minute = (int(part) for part in answers.closing_time.split(":"))
        late = hour * 60 + minute
        data["closing_hour"] = answers.closing_time
        # as app.memo.facts.closing_bucket_at: after midnight up to 6 a.m. is a late close, after 2 a.m. the later one
        data["closes_after_midnight"] = 0 < late <= LATE_CLOSE_UNTIL
        data["closes_after_2am"] = 2 * 60 < late <= LATE_CLOSE_UNTIL
    if answers.last_use is not None:
        data["existing_use_stated"] = [answers.last_use]
    if answers.fewer_than_50_people is not None:
        data["occupants_under_50"] = answers.fewer_than_50_people
    if answers.outdoor_area is not None:
        there = answers.outdoor_area != "none"
        data["outdoor_area"] = answers.outdoor_area
        data["outdoor_seating"] = there
        data["sidewalk_or_parklet"] = answers.outdoor_area == "sidewalk"
        if not there:  # no outdoor area: no alcohol served in one (the follow-up is not asked)
            data["outdoor_alcohol_service"] = False
    if answers.outdoor_alcohol_service is not None:
        data["outdoor_alcohol_service"] = answers.outdoor_alcohol_service
        if answers.outdoor_alcohol_service:
            # alcohol served in the outdoor area says there is an outdoor area: the outdoor row is read. Where it
            # is stays as given; a description's "no outdoor area" is overruled, so the place is then not known
            # (the row names the outdoor-area question), never assumed.
            data["outdoor_seating"] = True
            if data["outdoor_area"] == "none":
                data["outdoor_area"] = None
            # alcohol served outdoors is alcohol served: the alcohol row is read
            data["serves_alcohol"] = True
            other_alcohol_answer = licence in TRANSACTION_FOR_LICENCE or answers.alcohol_served is not None
            data["outdoor_alcohol_answer_over_description"] = (
                not other_alcohol_answer and not _mentions_alcohol(profile)
            )
    if answers.existing_business_change is not None:
        data["changes_existing_business"] = answers.existing_business_change
    if answers.floor_area_before_sqft is not None:
        data["floor_area_before_sqft"] = answers.floor_area_before_sqft
    if answers.merges_storefronts is not None:
        data["merges_storefronts"] = answers.merges_storefronts
    if answers.amends_prior_approval is not None:
        data["amends_prior_approval"] = answers.amends_prior_approval
    if answers.entertainment is not None:
        data["entertainment_kind"] = answers.entertainment
        if answers.entertainment == "none":
            data["live_entertainment"] = data["amplified_sound"] = data["dancing"] = False
    if answers.existing_occupancy_group is not None:
        data["existing_occupancy_group"] = answers.existing_occupancy_group
    if answers.food_service is not None:
        data["food_service"] = answers.food_service
    data["intake_answered"] = sorted(answered_fields(answers))
    return BusinessProfile.model_validate(data)


def answered_fields(answers: IntakeAnswers) -> frozenset[str]:
    """The profile fields `apply_intake_answers` sets for these answers, whatever the values (a "No alcohol"
    answer sets serves_alcohol false: the applicant gave it). app.memo.stated.record_cleared reads these as given,
    and `BusinessProfile.intake_answered` holds them. The two flags the answers set for a line
    (no_alcohol_answer_over_description, outdoor_alcohol_answer_over_description) are not facts and are not listed."""
    fields: set[str] = set()
    if answers.part_of_chain is not None:
        fields |= {"part_of_chain", "formula_retail", "other_locations"}
    if answers.floor_area_sqft is not None:
        fields.add("square_feet")
    if answers.liquor_licence in TRANSACTION_FOR_LICENCE:
        fields |= {"alcohol_transaction", "serves_alcohol"}
    elif answers.liquor_licence == NO_ALCOHOL:
        fields |= {
            "serves_alcohol",
            "alcohol_type",
            "licence_type",
            "alcohol_transaction",
            "outdoor_alcohol_service",
        }
    if answers.stories is not None:
        fields.add("stories")
    if answers.alcohol_served is not None:
        fields |= {"serves_alcohol", "alcohol_type"}
    if answers.closing_time is not None:
        fields |= {"closing_hour", "closes_after_midnight", "closes_after_2am"}
    if answers.last_use is not None:
        fields.add("existing_use_stated")
    if answers.fewer_than_50_people is not None:
        fields.add("occupants_under_50")
    if answers.outdoor_area is not None:
        fields |= {"outdoor_area", "outdoor_seating", "sidewalk_or_parklet"}
        if answers.outdoor_area == "none":
            fields.add("outdoor_alcohol_service")
    if answers.outdoor_alcohol_service is not None:
        fields.add("outdoor_alcohol_service")
        if answers.outdoor_alcohol_service:
            # there is an outdoor area (where it is, the answer does not say: outdoor_area is not listed)
            fields |= {"serves_alcohol", "outdoor_seating"}
    if answers.existing_business_change is not None:
        fields.add("changes_existing_business")
    if answers.floor_area_before_sqft is not None:
        fields.add("floor_area_before_sqft")
    if answers.merges_storefronts is not None:
        fields.add("merges_storefronts")
    if answers.amends_prior_approval is not None:
        fields.add("amends_prior_approval")
    if answers.entertainment is not None:
        fields.add("entertainment_kind")
        if answers.entertainment == "none":
            fields |= {"live_entertainment", "amplified_sound", "dancing"}
    if answers.existing_occupancy_group is not None:
        fields.add("existing_occupancy_group")
    if answers.food_service is not None:
        fields.add("food_service")
    return frozenset(fields)


# ---- answers written as data (the local run script, backtest/inputs.json) ---------------------------------
def intake_answers(data: Mapping[str, Any] | None) -> IntakeAnswers:
    """Answers from a JSON object with the question ids as keys (any may be absent or null). `other_locations` may also be
    "11_or_more", read as 11: a chain the record calls formula retail without giving its count. An unknown key
    or a value outside the allowed answers is an error."""
    raw = dict(data or {})
    if raw.get("other_locations") == ELEVEN_OR_MORE:
        raw["other_locations"] = FORMULA_RETAIL_OTHER_LOCATIONS
    return IntakeAnswers.model_validate(raw)


def intake_answers_from_case(case: Mapping[str, Any]) -> IntakeAnswers:
    """The intake answers of one case of backtest/inputs.json ("intake_answers"; an absent key is a skipped
    question, and a case with none answered gives empty answers)."""
    return intake_answers(case.get("intake_answers"))
