"""BusinessProfile and intake / triage structured outputs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.json_schema import SkipJsonSchema

BusinessType = Literal["restaurant", "bar", "cafe", "food_truck", "hotel", "catering", "other"]
CookingType = Literal["none", "limited", "full"]
# "unknown": the concept serves alcohol and the description does not say what (beer and wine, or spirits too).
# It is never filled with a guess: the rules then derive no licence type and name what is missing, and the
# permit checklist leaves the licence that depends on it undetermined (app.catalog.rules).
AlcoholType = Literal["none", "beer_wine", "full_liquor", "unknown"]
AlcoholTransaction = Literal[
    "new_licence", "person_to_person_transfer", "premises_transfer", "licence_already_held"
]
ExistingUse = Literal[
    "bar",
    "restaurant",
    "limited_restaurant",
    "nighttime_entertainment",
    "retail",
    "laundromat",
    "other",
    "vacant",
]
ExistingBusinessChange = Literal["none", "enlarge", "intensify", "enlarge_and_intensify"]
Story = Literal["first", "second", "third_or_above", "basement"]
EntertainmentKind = Literal["none", "limited_live_performance", "place_of_entertainment"]
OutdoorArea = Literal["none", "front", "rear_or_side", "rooftop", "parking_lot", "sidewalk"]
# The Building Code occupancy group of the existing space, as its plans or certificate of occupancy show it: the two
# groups the rules compare for a food or drink use (Group B below 50 people, Assembly Group A-2 from 50).
OccupancyGroup = Literal["B", "A-2"]
# The kind of food or drink service of a business described as a bar that serves no alcohol, which is not a Bar
# (Planning Code § 102; app.memo.pathway rule 1b): the two Planning Code § 102 uses the rules know for it, or "other"
# (another use, or the applicant is not sure), which gives no use.
FoodService = Literal["restaurant", "limited_restaurant", "other"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Fields only code sets: none is a fact. `intake_cleared` is code's record of what the stated-facts check removed
# (app.memo.stated); `intake_answered` its record of the fields the intake answers set; the two
# `..._answer_over_description` flags say an intake answer overruled the description (app.memo.intake);
# `no_alcohol_stated` says the description states the business serves no alcohol (app.memo.stated). A rule line
# reads them to say where its fact came from ("You answered ..." or "The description says ..."), so neither the
# intake model nor an operator override may set them: an override of one would forge a line's origin. POST
# /v1/memos refuses them in `profile_overrides` (422).
CODE_ONLY_FIELDS: tuple[str, ...] = (
    "intake_cleared",
    "intake_answered",
    "no_alcohol_answer_over_description",
    "outdoor_alcohol_answer_over_description",
    "no_alcohol_stated",
)
# Facts the applicant gives only through the intake questions (or an operator override): the intake model never
# sets them, because it guessed them from the description (runs of 2026-11-11: a wine bar read as not a chain in one
# run of five; "40 seats" read as fewer than 50 occupants in three). Nor can it set the fields only code sets.
MODEL_MAY_NOT_SET: tuple[str, ...] = (
    "formula_retail",
    "other_locations",
    "part_of_chain",
    "alcohol_transaction",
    "occupants_under_50",
    "existing_occupancy_group",
    "food_service",
    *CODE_ONLY_FIELDS,
)

# The profile fields the memo's rules read that the intake model may set, each only with a quote from the text
# that states it (`MemoIntakeResult.quotes`). Code checks every quote and clears a field whose quote is missing, is
# not in the text, or does not state the value (app.memo.stated).
QUOTED_FIELDS: tuple[str, ...] = (
    "business_type",
    "serves_alcohol",
    "alcohol_type",
    "licence_type",
    "licences_held",
    "square_feet",
    "floor_area_before_sqft",
    "seats",
    "existing_use_stated",
    "changes_existing_business",
    "merges_storefronts",
    "amends_prior_approval",
    "stories",
    "closing_hour",
    "closes_after_midnight",
    "closes_after_2am",
    "entertainment_kind",
    "live_entertainment",
    "amplified_sound",
    "dancing",
    "outdoor_area",
    "outdoor_seating",
    "sidewalk_or_parklet",
    "outdoor_alcohol_service",
    "change_of_use",
    "new_construction",
)
QuotedField = Literal[
    "business_type",
    "serves_alcohol",
    "alcohol_type",
    "licence_type",
    "licences_held",
    "square_feet",
    "floor_area_before_sqft",
    "seats",
    "existing_use_stated",
    "changes_existing_business",
    "merges_storefronts",
    "amends_prior_approval",
    "stories",
    "closing_hour",
    "closes_after_midnight",
    "closes_after_2am",
    "entertainment_kind",
    "live_entertainment",
    "amplified_sound",
    "dancing",
    "outdoor_area",
    "outdoor_seating",
    "sidewalk_or_parklet",
    "outdoor_alcohol_service",
    "change_of_use",
    "new_construction",
]


class BusinessProfile(StrictModel):
    business_type: BusinessType = Field(
        description="Primary concept. Wine bars, breweries, taprooms and cocktail bars are 'bar'; bakeries and coffee shops are 'cafe'."
    )
    business_name: str | None = Field(default=None, description="Name of the business if given.")
    city_name: str | None = Field(
        default=None, description="City / neighborhood exactly as the user wrote it."
    )
    city_slug: str | None = Field(
        default=None,
        description="Catalog slug when the city is supported (san_francisco, los_angeles, san_diego, new_york_city, austin, houston, miami, chicago, denver, seattle); null otherwise.",
    )
    state: str | None = Field(default=None, description="Two-letter US state code, or null if unknown.")
    neighborhood: str | None = None
    seats: int | None = Field(default=None, ge=0)
    square_feet: int | None = Field(default=None, ge=0)
    employees: int | None = Field(
        default=None, ge=0, description="Expected headcount. Assume at least 1 for anything but a solo cart."
    )
    hotel_rooms: int | None = Field(default=None, ge=0)
    serves_food: bool = True
    has_kitchen: bool = Field(default=True, description="Any on-site food preparation.")
    cooking_type: CookingType = Field(
        default="limited",
        description="'full' = fryers/grills/hood; 'limited' = small plates, panini, reheating; 'none' = packaged only.",
    )
    serves_alcohol: bool = False
    alcohol_type: AlcoholType = Field(
        default="none",
        description="What is served, only if the description says: 'beer_wine' (beer and wine; a wine bar) or "
        "'full_liquor' (spirits too: cocktails, a full bar). 'unknown' when it serves alcohol without saying "
        "what; 'none' when it serves none.",
    )
    closes_after_midnight: bool = False
    closes_after_2am: bool = False
    live_entertainment: bool = False
    amplified_sound: bool = False
    dancing: bool = False
    outdoor_seating: bool = False
    sidewalk_or_parklet: bool = Field(
        default=False, description="Seating on the public sidewalk or in the parking lane."
    )
    change_of_use: bool = Field(
        default=False, description="Space was not previously a restaurant/bar, or is new construction."
    )
    tenant_improvements: bool = Field(
        default=True, description="Build-out beyond paint and furniture (walls, plumbing, electrical, hood)."
    )
    new_construction: bool = False
    exterior_signage: bool = True
    plays_recorded_music: bool = True
    mobile_vending: bool = False
    uses_commissary: bool = False
    sells_packaged_goods: bool = False
    # ---- facts the pathway rules read (rule table v2). Each is None or empty when the description does not say.
    # A missing fact is never read as "no" and is never filled with a default or a guess: the rules then answer
    # "Insufficient information" and name what is missing.
    licence_type: str | None = Field(
        default=None,
        description="ABC licence type number the concept needs, only if stated (e.g. '41', '47', '42', '48').",
    )
    licences_held: list[str] = Field(
        default_factory=list,
        description="ABC licence type numbers the business already holds at this address, if stated.",
    )
    # Set only by the applicant's intake answers (app.memo.intake), never by the intake model: hidden from its tool
    # schema, and cleared from its output by AgentRunner._merge_profile (MODEL_MAY_NOT_SET).
    alcohol_transaction: SkipJsonSchema[AlcoholTransaction | None] = Field(
        default=None,
        description="How the licence is to be obtained, only if stated: a new licence, a transfer from another person, "
        "a transfer from other premises, or a licence the business already holds.",
    )
    formula_retail: SkipJsonSchema[bool | None] = Field(
        default=None,
        description="True if the description says the business is part of a chain; false if it says it is not.",
    )
    # True when the applicant answered "No alcohol" to the liquor licence intake question while the description, as
    # the intake model read it, served alcohol (app.memo.intake): the answer wins, and the rules say so in a line.
    # Set only by that answer; the intake model's tool schema does not show it.
    no_alcohol_answer_over_description: SkipJsonSchema[bool] = False
    # True when the description itself states that the business serves no alcohol, in the words that name the kind
    # of business ("a zero-proof cocktail bar", "an alcohol-free bar"), and states no alcohol served anywhere else
    # (app.memo.stated, `NO_ALCOHOL_WORDS`). A false serves_alcohol cannot say this: it is also the value of "not
    # stated". Read by app.memo.pathway rule 1: a business that serves no alcohol is not a Bar (Planning Code
    # § 102). Set only by that check; the intake model's tool schema does not show it.
    no_alcohol_stated: SkipJsonSchema[bool] = False
    # True when the applicant answered that alcohol will be served in the outdoor area, gave no other alcohol answer,
    # and the description, as the intake model read it, did not say alcohol is served (it may have said none is).
    # The answer is read (the business serves alcohol), and the alcohol row says the two disagree. Set only by that
    # answer (app.memo.intake); the intake model's tool schema does not show it.
    outdoor_alcohol_answer_over_description: SkipJsonSchema[bool] = False
    # The applicant's answer to the intake question "Is the business part of a chain ...?" (app.memo.intake), set
    # only by that answer: the intake model's tool schema does not show it. With it the rules can tell a chain
    # whose count was not given (they name the count) from a skipped chain question (they name the question).
    part_of_chain: SkipJsonSchema[bool | None] = None
    other_locations: SkipJsonSchema[int | None] = Field(
        default=None,
        ge=0,
        description="How many other locations the chain has, if the applicant says (intake question). Planning Code "
        "§ 303.1 counts a business as formula retail when it has eleven or more other establishments and shares "
        "standardised features such as a name, look or menu.",
    )
    floor_area_before_sqft: int | None = Field(
        default=None, ge=0, description="Floor area of the existing business before the project, if stated."
    )
    existing_use_stated: list[ExistingUse] = Field(
        default_factory=list, description="What the description says the space is, or was last, used as."
    )
    changes_existing_business: ExistingBusinessChange | None = Field(
        default=None,
        description="For an existing business that stays: 'enlarge' (more floor area), 'intensify' (new entertainment, "
        "longer hours, a stronger licence), both, or 'none'. Only if stated.",
    )
    merges_storefronts: bool | None = None
    stories: list[Story] = Field(default_factory=list, description="Stories the use occupies, if stated.")
    closing_hour: str | None = Field(
        default=None,
        pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
        description="Closing time as HH:MM (24-hour), if stated.",
    )
    entertainment_kind: EntertainmentKind | None = Field(
        default=None,
        description="'limited_live_performance' or 'place_of_entertainment' only when the description names the permit "
        "or gives what decides it; 'none' when it says there is no entertainment.",
    )
    outdoor_area: OutdoorArea | None = Field(
        default=None, description="Where the outdoor area is, if stated."
    )
    outdoor_alcohol_service: bool | None = None
    amends_prior_approval: bool | None = Field(
        default=None,
        description="True if the description says an earlier approval's conditions are to be changed.",
    )
    # Not filled from a seat count (seats are not the occupant load). Set only by the applicant's answer to the
    # intake question "Is the space for fewer than 50 people?" (app.memo.intake), never by the intake model.
    occupants_under_50: SkipJsonSchema[bool | None] = None
    # The existing Building Code occupancy group of the space. No public record shows it: only the applicant's answer
    # to an intake question gives it (app.memo.intake), from the plans or the certificate of occupancy. The rules
    # compare it with the proposed group (app.memo.rows, change of occupancy).
    existing_occupancy_group: SkipJsonSchema[OccupancyGroup | None] = None
    # The kind of food or drink service, for a business described as a bar that serves no alcohol (not a Bar: Planning
    # Code § 102). Only the applicant's answer to the intake question "What kind of food or drink service is it?"
    # gives it (app.memo.intake), never the intake model; the rules read it only for such a business (app.memo.pathway
    # rule 1b), and "other" gives no use.
    food_service: SkipJsonSchema[FoodService | None] = None
    target_open_date: str | None = Field(default=None, description="YYYY-MM-DD if the user gave a target.")
    # Set only by code (app.memo.stated.record_cleared): each field the stated-facts check cleared, in whole or in
    # part, because no quote from the text stated it -> the intake model's value that was removed. The rules name
    # each one as not given. Hidden from the intake model's tool schema; empty outside the memo.
    intake_cleared: SkipJsonSchema[dict[str, Any]] = Field(default_factory=dict)
    # Set only by code (app.memo.intake.apply_intake_answers): the profile fields an intake answer set, so a rule line
    # can say "You answered ..." for them and "The description says ..." for the rest. Hidden from the intake model's
    # tool schema; empty when nothing was answered.
    intake_answered: SkipJsonSchema[list[str]] = Field(default_factory=list)
    assumptions: list[str] = Field(
        default_factory=list,
        description="Plain-English list of what was assumed because the user did not say.",
    )

    @field_validator("state")
    @classmethod
    def _upper_state(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        return v if len(v) == 2 and v.isalpha() else None

    @field_validator("alcohol_type")
    @classmethod
    def _alcohol_consistency(cls, v: AlcoholType, info: Any) -> AlcoholType:
        return v

    def normalized(self) -> BusinessProfile:
        """Apply cross-field consistency rules so catalog rules see coherent data. A concept that serves alcohol
        without saying what it pours gets alcohol_type "unknown", never a guess."""
        data = self.model_dump()
        if data["serves_alcohol"] and data["alcohol_type"] == "none":
            data["alcohol_type"] = "unknown"
        if not data["serves_alcohol"]:
            data["alcohol_type"] = "none"
        if data["closes_after_2am"]:
            data["closes_after_midnight"] = True
        if data["business_type"] == "food_truck":
            data["mobile_vending"] = True
        if data["mobile_vending"]:
            data["tenant_improvements"] = False
            data["change_of_use"] = False
            data["exterior_signage"] = False
            data["sidewalk_or_parklet"] = False
        if data["sidewalk_or_parklet"]:
            data["outdoor_seating"] = True
        if data["dancing"]:
            data["amplified_sound"] = True
        if not data["has_kitchen"]:
            data["cooking_type"] = "none"
        if data["business_type"] == "hotel" and data["hotel_rooms"] is None:
            data["hotel_rooms"] = 20
        if data["employees"] is None:
            data["employees"] = 1 if data["mobile_vending"] else 5
        return BusinessProfile.model_validate(data)


class ClarifyingOption(StrictModel):
    value: str
    label: str


class ClarifyingQuestion(StrictModel):
    id: str = Field(pattern=r"^q[0-9]+$")
    question: str = Field(min_length=8, max_length=240)
    kind: Literal["single_choice", "boolean", "number", "text"]
    options: list[ClarifyingOption] | None = Field(
        default=None, description="Required for single_choice; 2–6 options."
    )
    maps_to: str = Field(description="BusinessProfile field this answer fills.")
    required: bool = True

    @field_validator("maps_to")
    @classmethod
    def _known_field(cls, v: str) -> str:
        if v not in BusinessProfile.model_fields:
            raise ValueError(f"maps_to must be a BusinessProfile field, got {v!r}")
        return v


class FactQuote(StrictModel):
    field: QuotedField = Field(description="The profile field the quote states.")
    quote: str = Field(
        min_length=1,
        max_length=300,
        description="The exact words of the description (or a clarification answer) that state the value, copied "
        "verbatim: a few words, not a paraphrase.",
    )


class IntakeResult(StrictModel):
    profile: BusinessProfile
    needs_clarification: bool = Field(
        description="True only when a missing fact would change which permits apply (city/state unknown, alcohol unclear, hotel vs restaurant)."
    )
    questions: list[ClarifyingQuestion] = Field(default_factory=list, max_length=2)
    reasoning_summary: str = Field(description="One or two sentences on how the description was interpreted.")

    @field_validator("questions")
    @classmethod
    def _max_two(cls, v: list[ClarifyingQuestion]) -> list[ClarifyingQuestion]:
        if len(v) > 2:
            raise ValueError("at most 2 clarifying questions")
        return v


class MemoIntakeResult(IntakeResult):
    """The memo's intake result: the checklist's, with a quote for every rule-read field the model sets
    (app.memo.stated). The checklist product (/v1/plans) keeps `IntakeResult`, with no quotes and no check."""

    quotes: list[FactQuote] = Field(
        default_factory=list,
        max_length=80,
        description="One entry for every field of the list in the instructions that you set to anything but its "
        "'not stated' value. A value without a quote that states it is cleared.",
    )


class TriageResult(StrictModel):
    is_hospitality_business: bool = Field(
        description="True if the text describes opening or operating a restaurant, bar, cafe, bakery, food truck, hotel, catering or similar food/beverage/lodging business."
    )
    language: str = Field(default="en", description="BCP-47 language code of the description.")
    city_guess: str | None = Field(default=None, description="City mentioned or implied, as written.")
    state_guess: str | None = Field(default=None, description="Two-letter state code if determinable.")
    reject_reason: str | None = Field(
        default=None, description="If not a hospitality business, a short user-facing explanation."
    )
