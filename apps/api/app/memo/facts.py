"""The facts the pathway rules read (rule table v2), in one place. No I/O, no model call, no clock.

Two sets of facts, each built by one pure function:

* `concept_facts(profile)` -> `ConceptFacts`: what the description says about the concept. Every fact keeps its
  value and where the value came from:
    "stated"  the input gave it;
    "derived" the rules worked it out from something the input gave (`basis` names the profile field);
    "missing" the input does not give it. A missing fact has no value. It is never read as "no", and nothing
              here fills it with a default. `ConceptFacts.missing(names)` names it in plain words, always with
              the same phrase (`MISSING_PHRASES`), so the report can say "the description does not give X".
* `site_facts(site_records, site, rules_date=...)` -> `SiteFacts`: what the records on file at the report's own
  street address show on the rules date: the ACTIVE licences, the existing use those licences show, and the
  earlier approved use decisions. Records dated on or after the rules date are left out.

`profile_from_facts(facts)` builds a profile from one hand-entered "input_facts" or "record_facts" object of
backtest/inputs.json, with no model call, for the rules-only baseline.

HOW EACH CONCEPT FACT IS READ
  planning_uses        the Planning Code § 102 uses of the concept, in the fixed order of `USE_ORDER`:
                       1. uses stated outright (only `concept_facts(..., stated_uses=...)` carries them; the
                          profile has no field for a stated § 102 use);
                       2. the use rule table v1 reads from the business type (`pathway.planning_use`); for a
                          bar that serves no alcohol, the use the applicant answered for the kind of food or drink
                          service (`pathway.food_service_use`), marked stated (basis "food_service");
                       3. when the business type decides no use, the use a stated licence type alone shows
                          (`USE_FOR_LICENCE`, from § 102);
                       4. "nighttime_entertainment" when the entertainment kind is place_of_entertainment or the
                          profile says dancing.
                       Empty when nothing above gives a use. It is "missing" when the business type is "other"
                       (the input does not say what kind of business it is), and when the business is a bar
                       that serves no alcohol (pathway rule 1b: not a Bar, and no other use is assumed), where
                       it is named as "food_service" (`MISSING_PHRASES`), and "derived" when the business
                       type is one the rule table does not cover (a food truck, a hotel, a caterer).
  food_service         only for a bar that serves no alcohol (pathway rule 1b): the use the applicant answered
                       ("restaurant" or "limited_restaurant", from the intake question "What kind of food or drink
                       service is it?"), stated; else missing (not answered, or answered "other": another use, or
                       not sure), and named in place of "planning_uses". For any other business it is derived and
                       holds no value, and an answer to the question is kept in `food_service_given` only, so a line
                       can say it was not read.
  licence_type         the stated type; else, for a concept that serves alcohol and says what it pours,
                       `pathway.LICENCE_FOR_CONCEPT[(use, alcohol_type)]`, marked derived; else missing. A
                       concept that serves alcohol without saying what it pours (alcohol_type "unknown") gets no
                       derived type: what is poured is never guessed (v1 read it as beer and wine). A type the
                       intake model read and the stated-facts check cleared is not named as not known when the
                       rules derive one (from what the description states or an answer gives is poured); when they
                       cannot, it is named as `licence_type_missing_name` names it.
  alcohol_served       what the concept pours: "beer_wine" or "full_liquor" as stated; "none", derived, when it
                       serves no alcohol; missing when it serves alcohol without saying what ("unknown"). It is
                       named only in place of the licence type: when the licence type is missing and what is
                       poured would decide it (the use is a Bar or a Restaurant), the rules name "what alcohol
                       will be served: beer and wine, or spirits too" instead of "the licence type"
                       (`ConceptFacts.licence_type_missing_name`). Every rule that reads the licence type reads
                       a missing one as missing, never as "no alcohol".
  alcohol_transaction  stated or missing. Never derived.
  closing              the stated closing hour, read at its last open minute (a 2 a.m. close is read at
                       1:59 a.m., inside "P 6 a.m. to 2 a.m."). A stated morning close (after 6 a.m., before
                       noon) with closes_after_2am or closes_after_midnight is open through the night: bucket
                       "after_2am", `overnight` True, read from 2 a.m. (or midnight) to the close; with neither
                       flag `overnight` is None (not known whether the business is open overnight). Else the
                       v1 bucket from closes_after_midnight /
                       closes_after_2am, marked derived and read where v1 reads it (`pathway.READ_AT`); else
                       missing. The profile's default "closes by midnight" is never read as a closing time.
  stories              as stated, in the fixed order of `Story`; else missing. A missing story is never filled in:
                       no story is assumed, and every rule whose answer depends on the story is not decided and
                       names it (`story_missing`, app.memo.triggers; the user's decision of 2026-11-12: "always
                       'Insufficient information', naming it. Never default to the first story."). A story the
                       intake model read but the text does not state (`stories_not_stated`) is cleared and missing
                       in the same way.
  outdoor_area         the stated value; else "sidewalk" from sidewalk_or_parklet, marked derived; else missing.
                       `outdoor_area_described` is true when the input mentions an outdoor area at all.
  formula_retail       stated or missing. The intake answers (app.memo.intake) set it from the chain question
                       and the count; `part_of_chain` keeps the chain answer, so a chain whose count is missing
                       is named by the count ("other_locations"), not by the chain question.
  every other fact     stated or missing.

Every fixed phrase and every code reference is in the tables at the top of this module.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Generic, Literal, NamedTuple, TypeVar, cast, get_args

from app.memo.analytics import record_kind
from app.memo.pathway import (
    LICENCE_FOR_CONCEPT,
    LICENCE_TYPES,
    READ_AT,
    ClosingBucket,
    _at_report_address,
    _serves_alcohol,
    _sorted_records,
    existing_use,
    food_service_use,
    not_a_bar,
    planning_use,
)
from app.memo.pathway import licence_type as record_licence_type
from app.memo.report import Site, SiteRecord, one_line
from app.memo.stated import cleared_fact_names, cleared_readings
from app.models.memo import PlanningUse, RuleLine
from app.models.profile import (
    AlcoholTransaction,
    BusinessProfile,
    EntertainmentKind,
    ExistingBusinessChange,
    ExistingUse,
    FoodService,
    OutdoorArea,
    Story,
)

T = TypeVar("T")
FactSource = Literal["stated", "derived", "missing"]
PouredAlcohol = Literal["beer_wine", "full_liquor", "none"]


# ---- the fixed tables (for review) ----------------------------------------------------------------------
class CodeSource(NamedTuple):
    section: str
    quote: str  # the words relied on, verbatim
    url: str
    read_on: str
    in_force: str  # the dates the words were in force, as the reconciled control data records them


# Planning Code § 102, "Bar" and "Restaurant": the ABC licence types each use may hold. Taken from the
# reconciled control data (controls/reconciled/citywide.json, key "use_definitions", fields `bar_abc_types` and
# `restaurant_on_sale_abc_types`). The two lists are the same in all four dated versions on file there
# (in force from before 2022-01-01 to the date read).
_SECTION_102_URL = (
    "https://gocodebook.com/library/us/ca/san-francisco-planning/"
    "article-1-general-zoning-provisions/sec.-102.-definitions"
)
_SECTION_102_IN_FORCE = "every version on file from before 2022-01-01 to 2026-11-10"
BAR_LICENCE_SOURCE = CodeSource(
    section="Planning Code § 102 (Bar)",
    quote=(
        "including bars serving beer, wine, and/or liquor to the customer where no person under 21 years of "
        "age is admitted (with Alcoholic Beverage Control [ABC] license types 23, 42, 48, or 61), drinking "
        "establishments serving beer where minors are present (with ABC license types 40 or 60)"
    ),
    url=_SECTION_102_URL,
    read_on="2026-11-10",
    in_force=_SECTION_102_IN_FORCE,
)
RESTAURANT_LICENCE_SOURCE = CodeSource(
    section="Planning Code § 102 (Restaurant)",
    quote=(
        "It may provide on-site beer, wine, and/or liquor sales for drinking on the premises (with ABC "
        "license types 02, 23, 41, 47, 49, 59, 75, or 87); however, if it does so, it shall be required to "
        "operate as a Bona Fide Eating Place."
    ),
    url=_SECTION_102_URL,
    read_on="2026-11-10",
    in_force=_SECTION_102_IN_FORCE,
)
# The lists as § 102 gives them. Bar: 23, 42, 48, 61 (no one under 21 admitted); 40, 60 (beer where minors are
# present, in conjunction with other uses); 02 (wine bars operated by licensed winegrowers).
BAR_LICENCE_TYPES: tuple[str, ...] = ("23", "42", "48", "61", "40", "60", "02")
RESTAURANT_LICENCE_TYPES: tuple[str, ...] = ("02", "23", "41", "47", "49", "59", "75", "87")
# Types 40 and 60 make a Bar only "in conjunction with other uses", so the licence alone decides nothing
# (rule table v1 says the same of Type 40).
BAR_ONLY_WITH_OTHER_USES: frozenset[str] = frozenset({"40", "60"})
# Types § 102 lists under both uses (02 winegrower, 23 small beer manufacturer). Such a licence alone does not
# say which of the two uses the concept is, so it decides nothing.
LICENCE_TYPES_EITHER_USE: frozenset[str] = frozenset(BAR_LICENCE_TYPES) & frozenset(RESTAURANT_LICENCE_TYPES)
# The use a stated licence type alone shows, read only when the business type decides no use:
# 42, 48, 61 -> bar; 41, 47, 49, 59, 75, 87 -> restaurant. A type under both uses, or under neither, shows none.
USE_FOR_LICENCE: dict[str, PlanningUse] = {
    **{
        t: "bar"
        for t in BAR_LICENCE_TYPES
        if t not in LICENCE_TYPES_EITHER_USE and t not in BAR_ONLY_WITH_OTHER_USES
    },
    **{t: "restaurant" for t in RESTAURANT_LICENCE_TYPES if t not in LICENCE_TYPES_EITHER_USE},
}

# The order uses are listed in, whatever order the input gave them in.
USE_ORDER: tuple[PlanningUse, ...] = ("bar", "restaurant", "limited_restaurant", "nighttime_entertainment")
# What the concept pours, for a stated licence type: the reverse of v1's LICENCE_FOR_CONCEPT
# (41, 42 -> beer_wine; 47, 48 -> full_liquor). Used only by `profile_from_facts`.
POURS_FOR_LICENCE: dict[str, str] = {number: pours for (_, pours), number in LICENCE_FOR_CONCEPT.items()}
# A stated closing hour after midnight and up to this minute is a late close; later in the day it is that
# day's closing time. 6 a.m. is where the hours controls on file start their day.
LATE_CLOSE_UNTIL = 6 * 60
# A stated closing time after LATE_CLOSE_UNTIL and before this minute is a morning close: with a profile flag
# saying the business closes after midnight or after 2 a.m. it is read as open through the night until then.
MORNING_ENDS = 12 * 60
_DAY = 24 * 60

# One fixed phrase per input, so the same missing input is always named the same way. The keys are the
# attribute names of `ConceptFacts`; the report prints the phrases in this order. The inputs an optional intake
# question asks for (app.memo.intake.QUESTIONS; since 2026-11-15 every input but the kind of business, the seats
# and the licences already held) are named in words the question uses, so the applicant recognises the question
# they skipped: the first four questions were written with the phrases (alcohol_transaction, formula_retail,
# other_locations, floor_area_sqft), and the later questions were written from the phrases already here.
# "other_locations" is named only in place of "formula_retail", when the applicant says the business is part of a
# chain but not how many other locations it has (`ConceptFacts.missing_names`); "alcohol_served" only in place of
# "licence_type", when the concept serves alcohol without saying what and what it pours would decide the type.
MISSING_PHRASES: dict[str, str] = {
    "planning_uses": "what kind of business it is (a bar, a restaurant, a cafe or an entertainment venue)",
    # named in place of "planning_uses" for a bar that serves no alcohol, which is not a Bar (pathway rule 1b)
    "food_service": (
        "what kind of food or drink service it is, since a business that serves no alcohol is not a Bar: a "
        "Restaurant (prepared food, with seating), a Limited Restaurant (ready-to-eat food or drinks) or another use"
    ),
    # named in place of "licence_type" when what is poured would decide the type (`missing_names`)
    "alcohol_served": "what alcohol will be served: beer and wine, or spirits too",
    "licence_type": "the licence type",
    "licences_held": "which licences the business already holds",
    "alcohol_transaction": (
        "how the liquor licence will be obtained (new, or a transfer from another owner or another location)"
    ),
    "formula_retail": (
        "whether the business is part of a chain that shares its name, look or menu with other locations"
    ),
    "other_locations": "how many other locations the chain has, open or approved, anywhere in the world",
    "floor_area_sqft": "the floor area of the business, in square feet",
    "floor_area_before_sqft": "the floor area before the project",
    "merges_storefronts": "whether storefronts are to be merged",
    "existing_use_stated": "what the space was last used as",
    "changes_existing_business": "whether an existing business is to be enlarged or intensified",
    "amends_prior_approval": "whether the conditions of an earlier approval are to be changed",
    "stories": "which stories the business occupies",
    "closing": "the closing time",
    "entertainment_kind": "whether there is entertainment, and what kind",
    "outdoor_area": "where the outdoor area is",
    "outdoor_alcohol_service": "whether alcohol is to be served in the outdoor area",
    "seats": "the number of seats",
    "occupants_under_50": "whether the space is for fewer than 50 people",
}
# The spec's and the profile's names for the same inputs.
FACT_ALIASES: dict[str, str] = {
    "planning_use": "planning_uses",
    "licences_already_held": "licences_held",
    "square_feet": "floor_area_sqft",
    "story": "stories",
    "closing_hour": "closing",
    "occupants": "occupants_under_50",
}

# backtest/inputs.json: the keys of one "input_facts" or "record_facts" object.
FACT_KEYS: frozenset[str] = frozenset(
    {
        "business_type",
        "planning_use",
        "serves_alcohol",
        "licence_type",
        "licences_already_held",
        "alcohol_transaction",
        "formula_retail",
        "operator_name",
        "floor_area_sqft",
        "floor_area_before_sqft",
        "seats",
        "occupants",
        "existing_use_stated",
        "existing_use_text",
        "changes_existing_business",
        "merges_storefronts",
        "story",
        "closing_hour",
        "opening_hour",
        "entertainment_kind",
        "amplified_sound",
        "live_entertainment",
        "outdoor_area",
        "outdoor_alcohol_service",
        "amends_prior_approval",
        "prior_approval_limits",
        "tenant_improvements",
        "new_construction",
        "historic_building",
        "legacy_business",
    }
)
# Facts the profile has no field for. `profile_from_facts` leaves them out; `facts_not_carried` lists the ones
# a facts object states. "planning_use" is carried by `concept_facts_from_facts`, not by the profile.
FACTS_WITHOUT_A_PROFILE_FIELD: tuple[str, ...] = (
    "planning_use",
    "existing_use_text",
    "opening_hour",
    "prior_approval_limits",
    "historic_building",
    "legacy_business",
)
OCCUPANTS_UNDER_50 = "under 50"  # the one text value "occupants" takes in backtest/inputs.json
APPROVED_OUTCOMES: frozenset[str] = frozenset({"approved", "approved_with_conditions"})


# ---- a fact and where it came from ----------------------------------------------------------------------
@dataclass(frozen=True)
class Fact(Generic[T]):
    """One fact: its value, and whether the input stated it, the rules derived it, or it is missing.
    A missing fact holds None (an empty tuple for a list of values) and must not be read as "no"."""

    value: T
    source: FactSource
    basis: str | None = None  # the profile field the value was read from; None when missing

    @property
    def stated(self) -> bool:
        return self.source == "stated"

    @property
    def derived(self) -> bool:
        return self.source == "derived"

    @property
    def missing(self) -> bool:
        return self.source == "missing"


@dataclass(frozen=True)
class UseReading:
    """One § 102 use of the concept and what showed it."""

    use: PlanningUse
    source: FactSource  # "stated" or "derived"
    # "planning_use" (stated outright), "business_type", "licence_type", "entertainment_kind" or "dancing"
    basis: str


@dataclass(frozen=True)
class Closing:
    """The closing time the rules read. Minutes are minutes after midnight."""

    source: FactSource
    minute: int | None  # the stated closing time (02:00 -> 120, 00:00 -> 0); None unless stated
    bucket: ClosingBucket | None  # v1's bucket; None when missing
    read_at: int | None  # the minute at which the rules read the hours control; None when missing
    basis: str | None = None
    # A stated closing time in the morning (after 6 a.m. and before noon): True when the profile also says the
    # business closes after midnight or after 2 a.m., so it is open through the night until then; None when it
    # does not say (the time may be a morning close of a daytime business); False for any other closing time.
    overnight: bool | None = False
    open_from: int | None = None  # overnight: the minute the late close begins (2 a.m., or midnight)

    @property
    def stated(self) -> bool:
        return self.source == "stated"

    @property
    def derived(self) -> bool:
        return self.source == "derived"

    @property
    def missing(self) -> bool:
        return self.source == "missing"

    @property
    def after_2am(self) -> bool:
        """The concept closes after 2 a.m. False when the closing time is missing: check `missing` first."""
        return self.bucket == "after_2am"


@dataclass(frozen=True)
class ConceptFacts:
    """What the input says about the concept, as the rules read it. See the module docstring."""

    planning_uses: Fact[tuple[PlanningUse, ...]]
    use_readings: tuple[UseReading, ...]  # one per use in `planning_uses`, in the same order
    serves_alcohol: bool  # the test `required_areas` uses for the alcohol row
    # what the concept pours: "beer_wine" / "full_liquor" stated, "none" derived (no alcohol), missing ("unknown")
    alcohol_served: Fact[PouredAlcohol | None]
    # a licence type is derived from what is poured for this concept (rule table v1's use is a Bar or a
    # Restaurant), so a missing pour is what leaves the licence type missing
    pours_decide_licence_type: bool
    licence_type: Fact[str | None]  # ABC type number as two digits of text, e.g. "41", "02"
    licences_held: Fact[tuple[str, ...]]
    alcohol_transaction: Fact[AlcoholTransaction | None]
    formula_retail: Fact[bool | None]
    # the applicant's answer to the intake chain question (None: not answered) and the chain's other locations
    part_of_chain: bool | None
    other_locations: Fact[int | None]
    floor_area_sqft: Fact[int | None]
    floor_area_before_sqft: Fact[int | None]
    merges_storefronts: Fact[bool | None]
    existing_use_stated: Fact[tuple[ExistingUse, ...]]
    changes_existing_business: Fact[ExistingBusinessChange | None]
    amends_prior_approval: Fact[bool | None]
    stories: Fact[tuple[Story, ...]]
    closing: Closing
    entertainment_kind: Fact[EntertainmentKind | None]
    live_entertainment: bool
    amplified_sound: bool
    dancing: bool
    outdoor_area: Fact[OutdoorArea | None]
    outdoor_area_described: bool  # the input mentions an outdoor area, whether or not it says where
    outdoor_alcohol_service: Fact[bool | None]
    seats: Fact[int | None]
    occupants_under_50: Fact[bool | None]
    # The facts the stated-facts check left not known (app.memo.stated): the intake model filled them, no quote
    # from the text stated them, and nothing the applicant gave set them since. `MISSING_PHRASES` keys, in its
    # order; a fact the input states after all (another field gives it) is not listed, nor a licence type the rules
    # derive, and a missing licence type is listed by `licence_type_missing_name`.
    cleared_facts: tuple[str, ...] = ()
    # Of those, the facts where the intake model read that something is there (alcohol served, entertainment, an
    # outdoor area, a story) and the text does not state it: not known, never read as "no". The row for each is
    # added and is insufficient information; a story not stated makes the use controls not decided.
    cleared_readings: tuple[str, ...] = ()
    # The profile fields an intake answer set (`BusinessProfile.intake_answered`): a rule line about one of them
    # says "You answered ...", never "The description says ..." (app.memo.rows).
    answered: frozenset[str] = frozenset()
    # Alcohol served outdoors is the applicant's only alcohol answer and the description did not say alcohol is
    # served (`BusinessProfile.outdoor_alcohol_answer_over_description`): the alcohol row says the two disagree.
    outdoor_alcohol_answer_over_description: bool = False
    # A bar that serves no alcohol is not a Bar (pathway rule 1b): what kind of food or drink service it is, is then
    # the use the applicant answered (stated), or missing and named in place of "planning_uses" (`missing_names`).
    # Derived, with no value and never named, for any other business.
    food_service: Fact[PlanningUse | None] = Fact(None, "derived", "business_type")
    # The applicant's answer to the question on the kind of food or drink service, whatever the business
    # (`BusinessProfile.food_service`): "other" included, and for a business it is not read for.
    food_service_given: FoodService | None = None

    @property
    def not_a_bar(self) -> bool:
        """A business described as a bar that serves no alcohol (pathway rule 1b), whether or not the kind of food or
        drink service is answered."""
        return self.food_service.source != "derived"

    def by_answer(self, field: str) -> bool:
        """Whether an intake answer gave this profile field (else the description, or nothing, gave it)."""
        return field in self.answered

    @property
    def alcohol_not_stated(self) -> bool:
        """Whether alcohol is served is not known: the intake model read it, the text does not state it."""
        return "alcohol_served" in self.cleared_readings

    @property
    def entertainment_not_stated(self) -> bool:
        """Whether there is entertainment is not known (as `alcohol_not_stated`)."""
        return "entertainment_kind" in self.cleared_readings

    @property
    def outdoor_not_stated(self) -> bool:
        """Whether there is an outdoor area is not known (as `alcohol_not_stated`)."""
        return "outdoor_area" in self.cleared_readings

    @property
    def stories_not_stated(self) -> bool:
        """Which story the business is on is not known: the intake model read one, the text does not state it."""
        return "stories" in self.cleared_readings

    @property
    def use(self) -> PlanningUse:
        """The first use in `planning_uses`, or "not_covered" when there is none (what `Pathway.use` holds)."""
        return self.planning_uses.value[0] if self.planning_uses.value else "not_covered"

    @property
    def story_missing(self) -> bool:
        """No story is stated (or the one the intake model read was cleared): no story is assumed, and every rule
        whose answer depends on the story is not decided and names it."""
        return self.stories.missing

    def source_of(self, name: str) -> FactSource:
        """Where one fact came from ("stated", "derived" or "missing"), by its name here or in the spec."""
        fact: Fact[Any] | Closing = getattr(self, fact_name(name))
        return fact.source

    @property
    def chain_count_missing(self) -> bool:
        """Whether the business is formula retail is missing only because the applicant says it is part of a
        chain without saying how many other locations the chain has."""
        return self.formula_retail.missing and self.part_of_chain is True and self.other_locations.missing

    @property
    def pours_missing(self) -> bool:
        """The licence type is missing only because the concept serves alcohol without saying what it pours,
        and what it pours would decide the type."""
        return self.licence_type.missing and self.alcohol_served.missing and self.pours_decide_licence_type

    @property
    def licence_type_missing_name(self) -> str:
        """The fact a rule names when the licence type is missing: "alcohol_served" when what is poured would
        decide it (`pours_missing`), else "licence_type"."""
        return "alcohol_served" if self.pours_missing else "licence_type"

    @property
    def licence_type_phrase(self) -> str:
        """The fixed phrase a rule names when the licence type is missing (`licence_type_missing_name`)."""
        return MISSING_PHRASES[self.licence_type_missing_name]

    def missing_names(self, names: Iterable[str] | None = None) -> tuple[str, ...]:
        """The missing facts among `names` (all facts when None), in the order of `MISSING_PHRASES`. A missing
        "formula_retail" is named as "other_locations" when the applicant says the business is part of a chain
        but not how many other locations it has; "other_locations" is never named otherwise. A missing
        "licence_type" is named as "alcohol_served" when the concept serves alcohol without saying what it pours
        and that would decide the type (`pours_missing`); "alcohol_served" is never named otherwise."""
        wanted = set(MISSING_PHRASES) if names is None else {fact_name(n) for n in names}
        if "formula_retail" in wanted and self.chain_count_missing:
            wanted = (wanted - {"formula_retail"}) | {"other_locations"}
        else:
            wanted.discard("other_locations")
        if "licence_type" in wanted and self.pours_missing:
            wanted = (wanted - {"licence_type"}) | {"alcohol_served"}
        else:
            wanted.discard("alcohol_served")
        if "planning_uses" in wanted and self.not_a_bar:
            wanted = (wanted - {"planning_uses"}) | {"food_service"}
        else:
            wanted.discard("food_service")
        return tuple(n for n in MISSING_PHRASES if n in wanted and self.source_of(n) == "missing")

    def missing(self, names: Iterable[str] | None = None) -> tuple[str, ...]:
        """The plain-words name of each missing input among `names` (all facts when None), each once, in the
        order of `MISSING_PHRASES`. An input the description gives, or the rules derived, is not listed."""
        return tuple(MISSING_PHRASES[n] for n in self.missing_names(names))


def fact_name(name: str) -> str:
    """The `ConceptFacts` attribute for a fact name; the spec's own names are accepted ("story",
    "closing_hour"). An unknown name is an error, so a misspelt input is never silently "not missing"."""
    key = FACT_ALIASES.get(name, name)
    if key not in MISSING_PHRASES:
        raise KeyError(f"not a concept fact: {name!r}")
    return key


def missing_phrase(name: str) -> str:
    """The fixed plain-words name of one input, e.g. "the closing time" for "closing" or "closing_hour"."""
    return MISSING_PHRASES[fact_name(name)]


# ---- concept facts --------------------------------------------------------------------------------------
def normal_licence_type(text: str | None) -> str | None:
    """An ABC licence type as two digits of text: '41' -> '41'; 'Type 47' -> '47'; '2' and '02' -> '02'.
    None when the text names no number."""
    m = re.search(r"\d{1,3}", text or "")
    return f"{int(m.group(0)):02d}" if m else None


def _scalar(value: T, basis: str) -> Fact[T]:
    """A profile field that is None when the description does not say. `T` is the field's whole type, None
    included, so a field of fixed values keeps them."""
    if value is None:
        return Fact(value, "missing")
    return Fact(value, "stated", basis)


def _listed(values: Iterable[T], basis: str) -> Fact[tuple[T, ...]]:
    """A profile list that is empty when the description does not say. Each value once, in the order given."""
    kept = tuple(dict.fromkeys(values))
    return Fact(kept, "stated", basis) if kept else Fact((), "missing")


def _use_readings(profile: BusinessProfile, stated_uses: Sequence[PlanningUse]) -> tuple[UseReading, ...]:
    found: dict[PlanningUse, UseReading] = {}

    def add(use: PlanningUse, source: FactSource, basis: str) -> None:
        if use != "not_covered":
            found.setdefault(use, UseReading(use, source, basis))

    for use in stated_uses:
        add(use, "stated", "planning_use")
    by_business = planning_use(profile)
    if food_service_use(profile) is not None:
        # rule 1b: the applicant answered the kind of food or drink service of a bar that serves no alcohol
        add(by_business, "stated", "food_service")
    else:
        add(by_business, "derived", "business_type")
    if by_business == "not_covered":
        by_licence = USE_FOR_LICENCE.get(normal_licence_type(profile.licence_type) or "")
        if by_licence is not None:
            add(by_licence, "derived", "licence_type")
    if profile.entertainment_kind == "place_of_entertainment":
        add("nighttime_entertainment", "derived", "entertainment_kind")
    elif profile.dancing:
        add("nighttime_entertainment", "derived", "dancing")
    return tuple(found[use] for use in USE_ORDER if use in found)


def _planning_uses(profile: BusinessProfile, readings: Sequence[UseReading]) -> Fact[tuple[PlanningUse, ...]]:
    uses = tuple(r.use for r in readings)
    if uses:
        stated = any(r.source == "stated" for r in readings)
        return Fact(
            uses, "stated" if stated else "derived", ", ".join(dict.fromkeys(r.basis for r in readings))
        )
    if profile.business_type == "other" or not_a_bar(profile):
        # not said, or a bar that serves no alcohol, which is not a Bar and is not given another use (rule 1b)
        return Fact((), "missing")
    return Fact((), "derived", "business_type")  # a business the rule table does not cover


def _food_service(profile: BusinessProfile) -> Fact[PlanningUse | None]:
    """Pathway rule 1b: the kind of food or drink service of a bar that serves no alcohol."""
    if not not_a_bar(profile):
        return Fact(None, "derived", "business_type")
    use = food_service_use(profile)
    return Fact(use, "stated", "food_service") if use is not None else Fact(None, "missing")


def _alcohol_served(profile: BusinessProfile) -> Fact[PouredAlcohol | None]:
    if not _serves_alcohol(profile):
        return Fact("none", "derived", "serves_alcohol")
    if profile.alcohol_type in ("beer_wine", "full_liquor"):
        return Fact(cast(PouredAlcohol, profile.alcohol_type), "stated", "alcohol_type")
    return Fact(None, "missing")  # "unknown" (or a profile that serves alcohol with alcohol_type "none")


def _pours_decide_licence_type(profile: BusinessProfile) -> bool:
    return any((planning_use(profile), pours) in LICENCE_FOR_CONCEPT for pours in get_args(PouredAlcohol))


def _licence_type(profile: BusinessProfile) -> Fact[str | None]:
    stated = normal_licence_type(profile.licence_type)
    if stated is not None:
        return Fact(stated, "stated", "licence_type")
    if _serves_alcohol(profile) and profile.alcohol_type in ("beer_wine", "full_liquor"):
        needed = LICENCE_FOR_CONCEPT.get((planning_use(profile), profile.alcohol_type))
        if needed is not None:
            return Fact(normal_licence_type(needed), "derived", "business_type, alcohol_type")
    return Fact(None, "missing")


def clock_minutes(hour: str) -> int:
    """'HH:MM' (24-hour) as minutes after midnight: '02:00' -> 120, '00:00' -> 0, '23:30' -> 1410."""
    m = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", hour.strip())
    if m is None:
        raise ValueError(f"not a time as HH:MM: {hour!r}")
    return int(m.group(1)) * 60 + int(m.group(2))


def closing_bucket_at(minute: int) -> ClosingBucket:
    """v1's bucket for a stated closing time: after midnight and up to 2 a.m. -> 'after_midnight'; after
    2 a.m. and up to 6 a.m. -> 'after_2am'; midnight itself, or any time later in the day -> 'by_midnight'."""
    if 0 < minute <= 2 * 60:
        return "after_midnight"
    if 2 * 60 < minute <= LATE_CLOSE_UNTIL:
        return "after_2am"
    return "by_midnight"


def _closing(profile: BusinessProfile) -> Closing:
    if profile.closing_hour is not None:
        minute = clock_minutes(profile.closing_hour)
        # the last open minute: the hours windows run from their start up to, not including, their end
        read_at = (minute - 1) % _DAY
        if LATE_CLOSE_UNTIL < minute < MORNING_ENDS:  # a morning close
            if profile.closes_after_2am or profile.closes_after_midnight:
                open_from = 2 * 60 if profile.closes_after_2am else 0
                return Closing(
                    "stated",
                    minute,
                    "after_2am",
                    read_at,
                    "closing_hour",
                    overnight=True,
                    open_from=open_from,
                )
            return Closing(
                "stated", minute, closing_bucket_at(minute), read_at, "closing_hour", overnight=None
            )
        return Closing("stated", minute, closing_bucket_at(minute), read_at, "closing_hour")
    if profile.closes_after_2am:
        return Closing("derived", None, "after_2am", READ_AT["after_2am"], "closes_after_2am")
    if profile.closes_after_midnight:
        return Closing("derived", None, "after_midnight", READ_AT["after_midnight"], "closes_after_midnight")
    return Closing("missing", None, None, None)


def _outdoor_area(profile: BusinessProfile) -> Fact[OutdoorArea | None]:
    if profile.outdoor_area is not None:
        return Fact(profile.outdoor_area, "stated", "outdoor_area")
    if profile.sidewalk_or_parklet:
        return Fact("sidewalk", "derived", "sidewalk_or_parklet")
    return Fact(None, "missing")


def concept_facts(profile: BusinessProfile, *, stated_uses: Sequence[PlanningUse] = ()) -> ConceptFacts:
    """The facts the rules read from the profile. `stated_uses` are § 102 uses the input states outright (the
    hand-entered "planning_use" of a backtest case); a live profile has no field for them and passes none.
    The profile is read as given. `BusinessProfile.normalized()` sets alcohol_type "unknown" for a concept that
    serves alcohol without saying what it pours; the rules read that as what is poured missing, as they read a
    profile that serves alcohol with alcohol_type "none", so normalising changes no answer here."""
    readings = _use_readings(profile, stated_uses)
    outdoor = _outdoor_area(profile)
    held = (normal_licence_type(t) for t in profile.licences_held)
    # declared types keep the fields' literal types (a bare call would widen them to str)
    transaction: Fact[AlcoholTransaction | None] = _scalar(profile.alcohol_transaction, "alcohol_transaction")
    change: Fact[ExistingBusinessChange | None] = _scalar(
        profile.changes_existing_business, "changes_existing_business"
    )
    entertainment: Fact[EntertainmentKind | None] = _scalar(profile.entertainment_kind, "entertainment_kind")
    facts = ConceptFacts(
        planning_uses=_planning_uses(profile, readings),
        use_readings=readings,
        serves_alcohol=_serves_alcohol(profile),
        alcohol_served=_alcohol_served(profile),
        pours_decide_licence_type=_pours_decide_licence_type(profile),
        licence_type=_licence_type(profile),
        licences_held=_listed((t for t in held if t is not None), "licences_held"),
        alcohol_transaction=transaction,
        formula_retail=_scalar(profile.formula_retail, "formula_retail"),
        part_of_chain=profile.part_of_chain,
        other_locations=_scalar(profile.other_locations, "other_locations"),
        floor_area_sqft=_scalar(profile.square_feet, "square_feet"),
        floor_area_before_sqft=_scalar(profile.floor_area_before_sqft, "floor_area_before_sqft"),
        merges_storefronts=_scalar(profile.merges_storefronts, "merges_storefronts"),
        existing_use_stated=_listed(profile.existing_use_stated, "existing_use_stated"),
        changes_existing_business=change,
        amends_prior_approval=_scalar(profile.amends_prior_approval, "amends_prior_approval"),
        stories=_listed((s for s in get_args(Story) if s in profile.stories), "stories"),  # a fixed order
        closing=_closing(profile),
        entertainment_kind=entertainment,
        live_entertainment=profile.live_entertainment,
        amplified_sound=profile.amplified_sound,
        dancing=profile.dancing,
        outdoor_area=outdoor,
        outdoor_area_described=(
            (outdoor.value is not None and outdoor.value != "none") or profile.outdoor_seating
        ),
        outdoor_alcohol_service=_scalar(profile.outdoor_alcohol_service, "outdoor_alcohol_service"),
        seats=_scalar(profile.seats, "seats"),
        occupants_under_50=_scalar(profile.occupants_under_50, "occupants_under_50"),
        answered=frozenset(profile.intake_answered),
        outdoor_alcohol_answer_over_description=profile.outdoor_alcohol_answer_over_description,
        food_service=_food_service(profile),
        food_service_given=profile.food_service,
    )
    cleared = cleared_fact_names(profile.intake_cleared)
    if not cleared:
        return facts
    named = tuple(n for n in MISSING_PHRASES if n in cleared and facts.source_of(n) != "stated")
    # a cleared reading that something is there stays not known only while nothing else says it is there
    there = {
        "alcohol_served": facts.serves_alcohol,
        "entertainment_kind": facts.live_entertainment or facts.amplified_sound or facts.dancing,
        "outdoor_area": facts.outdoor_area_described or not facts.outdoor_area.missing,
        "stories": not facts.stories.missing,
    }
    unknown = tuple(n for n in cleared_readings(profile.intake_cleared) if n in named and not there[n])
    facts = replace(facts, cleared_facts=named, cleared_readings=unknown)
    if facts.alcohol_not_stated:
        # what is poured, if anything, is not known, and it is what the licence type turns on: the rules name
        # "what alcohol will be served" (`licence_type_missing_name`), never "no alcohol"
        facts = replace(facts, alcohol_served=Fact(None, "missing"), pours_decide_licence_type=True)
    if "licence_type" in facts.cleared_facts:
        # A licence type the intake model read and the check cleared: when the rules derive one from what is
        # poured (stated or answered), it is known, as if the model had set none. When they cannot, it is named
        # as the rules name it elsewhere, so the report points at the answer that settles it ("what alcohol will
        # be served" when that decides the type) and at no question when none does.
        names = set(facts.cleared_facts) - {"licence_type"}
        if facts.licence_type.missing:
            names.add(facts.licence_type_missing_name)
        facts = replace(facts, cleared_facts=tuple(n for n in MISSING_PHRASES if n in names))
    return facts


# ---- site facts -----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SiteLicence:
    """An ACTIVE ABC licence on file at the report's own street address."""

    record_id: str
    licence_type: str  # two digits of text, e.g. "41", "02"
    label: str | None  # the type in plain words when rule table v1 reads the type (LICENCE_TYPES); else None
    issued: dt.date | None  # the record's date: the original issue date in the ABC export
    citation: str  # "app:<record id>"
    source_url: str


@dataclass(frozen=True)
class PriorDecision:
    """An earlier approved use decision on file at the report's own street address (rule T10 reads these)."""

    record_id: str
    date: dt.date | None  # the decision date, else the filing date
    description: str  # the record's own description, on one line
    permit_type: str  # the source's own label, e.g. "Conditional Use Authorization"
    conditional_use: bool  # the record is a Conditional Use Authorization
    outcome: str  # "approved" or "approved_with_conditions"
    citation: str  # "app:<record id>"
    source_url: str


@dataclass(frozen=True)
class SiteFacts:
    """What the records at the report's own street address show on the rules date."""

    rules_date: dt.date
    licences: tuple[SiteLicence, ...]  # in record id order
    existing_use: PlanningUse | None  # the use the licences show (pathway.existing_use); None = not shown
    existing_use_lines: tuple[RuleLine, ...]  # the rule lines saying which record showed it, or that none did
    prior_decisions: tuple[PriorDecision, ...]  # newest first; undated last

    @property
    def licence_types(self) -> tuple[str, ...]:
        """The types of the licences on file, each once, in number order."""
        return tuple(sorted({lic.licence_type for lic in self.licences}, key=int))


def record_date(rec: SiteRecord) -> dt.date | None:
    """The date a record is read at: its decision date, else its filing date (as the site history orders
    records). For an ABC licence the decision date is the original issue date."""
    date: dt.date | None = rec.app.decided_at or rec.app.filed_at
    return date


def on_file_before(site_records: Iterable[SiteRecord], rules_date: dt.date) -> list[SiteRecord]:
    """The records the rules may read on `rules_date`, each id once, in id order: every record dated before
    it, and every record with no date. A record dated on or after the rules date is left out."""
    kept: list[SiteRecord] = []
    for rec in _sorted_records(site_records):
        date = record_date(rec)
        if date is None or date < rules_date:
            kept.append(rec)
    return kept


def site_facts(
    site_records: Sequence[SiteRecord], site: Site, *, rules_date: dt.date, today: dt.date | None = None
) -> SiteFacts:
    """The site facts on `rules_date`, from the records on file at the report's own street address. A record
    tied to the site only by its parcel (another address on the same lot) is not read. The answer does not
    depend on the order of `site_records`. With `today` later than `rules_date` the existing-use lines say the
    records read are the ones dated before the rules date."""
    records = on_file_before(site_records, rules_date)
    here = [rec for rec in records if _at_report_address(rec, site)]

    licences: list[SiteLicence] = []
    for rec in here:
        number = normal_licence_type(record_licence_type(rec.app))
        if number is None or rec.app.status.strip().upper() != "ACTIVE":
            continue
        kind = LICENCE_TYPES.get(number)
        licences.append(
            SiteLicence(
                record_id=rec.app.id,
                licence_type=number,
                label=kind.label if kind else None,
                issued=record_date(rec),
                citation=f"app:{rec.app.id}",
                source_url=rec.app.source_url,
            )
        )

    decisions = [
        PriorDecision(
            record_id=rec.app.id,
            date=record_date(rec),
            description=one_line(rec.app.description),
            permit_type=rec.app.permit_type,
            conditional_use=rec.app.kind == "cua",
            outcome=rec.app.outcome,
            citation=f"app:{rec.app.id}",
            source_url=rec.app.source_url,
        )
        for rec in here
        if record_kind(rec.app) == "use_decision" and rec.app.outcome in APPROVED_OUTCOMES
    ]
    decisions.sort(key=lambda d: (d.date is None, -d.date.toordinal() if d.date else 0, d.record_id))

    use, lines = existing_use(records, site, rules_date=rules_date, today=today)
    return SiteFacts(
        rules_date=rules_date,
        licences=tuple(licences),
        existing_use=use,
        existing_use_lines=tuple(lines),
        prior_decisions=tuple(decisions),
    )


# ---- a profile from hand-entered facts (backtest/inputs.json) ---------------------------------------------
def _one(facts: Mapping[str, Any], key: str) -> Any:
    """A fact that takes one value. A list of one value is that value; a longer list is an error."""
    value = facts.get(key)
    if isinstance(value, list):
        if len(value) > 1:
            raise ValueError(f"{key} takes one value, got {value!r}")
        return value[0] if value else None
    return value


def _many(facts: Mapping[str, Any], key: str) -> list[Any]:
    """A fact that may be one value or a list; null is the empty list."""
    value = facts.get(key)
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _check_keys(facts: Mapping[str, Any]) -> None:
    unknown = sorted(set(facts) - FACT_KEYS)
    if unknown:
        raise ValueError(f"not a fact name of the spec: {', '.join(unknown)}")


def stated_planning_uses(facts: Mapping[str, Any]) -> tuple[PlanningUse, ...]:
    """The § 102 uses a facts object states under "planning_use", in the order of `USE_ORDER`. "not_covered"
    and null state no use."""
    _check_keys(facts)
    given = _many(facts, "planning_use")
    unknown = [u for u in given if u not in USE_ORDER and u != "not_covered"]
    if unknown:
        raise ValueError(f"not a planning use: {unknown!r}")
    return tuple(use for use in USE_ORDER if use in given)


def facts_not_carried(facts: Mapping[str, Any]) -> tuple[str, ...]:
    """The facts this object states that the profile has no field for (`FACTS_WITHOUT_A_PROFILE_FIELD`)."""
    _check_keys(facts)
    return tuple(k for k in FACTS_WITHOUT_A_PROFILE_FIELD if facts.get(k) is not None)


def profile_from_facts(facts: Mapping[str, Any]) -> BusinessProfile:
    """A profile from one "input_facts" or "record_facts" object of backtest/inputs.json. No model call.

    A null stays null: every v2 field the object leaves null is None or empty in the profile, and comes out
    missing from `concept_facts`. Nothing is filled from what is typical. What is set beyond the stated values:
      - business_type null -> "other" (the profile needs one; the rules then read no use from it);
      - alcohol_type from a stated licence type (41, 42 -> beer_wine; 47, 48 -> full_liquor); else "unknown"
        when the object says the business serves alcohol (what it pours is not guessed), else "none";
      - closes_after_midnight / closes_after_2am from a stated closing hour, so rule table v1 reads the same
        closing time on the same profile;
      - outdoor_seating (and sidewalk_or_parklet for "sidewalk") from a stated outdoor area;
      - occupants "under 50", or a number below 50, -> occupants_under_50 true; 50 or more -> false.
    The profile's older yes/no fields cannot hold "not stated": a null serves_alcohol, live_entertainment,
    amplified_sound or new_construction is left at the profile's default, and a null tenant_improvements is
    left at its default too. The v2 rules do not read those defaults as stated.
    "planning_use" has no profile field: pass `stated_planning_uses(facts)` to `concept_facts`, or call
    `concept_facts_from_facts`. `facts_not_carried` lists what else the profile cannot hold."""
    _check_keys(facts)
    licence = normal_licence_type(_one(facts, "licence_type"))
    data: dict[str, Any] = {
        "business_type": _one(facts, "business_type") or "other",
        "business_name": _one(facts, "operator_name"),
        "serves_alcohol": _one(facts, "serves_alcohol") is True,
        "alcohol_type": POURS_FOR_LICENCE.get(
            licence or "", "unknown" if _one(facts, "serves_alcohol") is True else "none"
        ),
        "licence_type": licence,
        "licences_held": [t for t in map(normal_licence_type, _many(facts, "licences_already_held")) if t],
        "alcohol_transaction": _one(facts, "alcohol_transaction"),
        "formula_retail": _one(facts, "formula_retail"),
        "square_feet": _one(facts, "floor_area_sqft"),
        "floor_area_before_sqft": _one(facts, "floor_area_before_sqft"),
        "seats": _one(facts, "seats"),
        "existing_use_stated": _many(facts, "existing_use_stated"),
        "changes_existing_business": _one(facts, "changes_existing_business"),
        "merges_storefronts": _one(facts, "merges_storefronts"),
        "stories": _many(facts, "story"),
        "closing_hour": _one(facts, "closing_hour"),
        "entertainment_kind": _one(facts, "entertainment_kind"),
        "live_entertainment": _one(facts, "live_entertainment") is True,
        "amplified_sound": _one(facts, "amplified_sound") is True,
        "outdoor_area": _one(facts, "outdoor_area"),
        "outdoor_alcohol_service": _one(facts, "outdoor_alcohol_service"),
        "amends_prior_approval": _one(facts, "amends_prior_approval"),
        "new_construction": _one(facts, "new_construction") is True,
    }
    if (improvements := _one(facts, "tenant_improvements")) is not None:
        data["tenant_improvements"] = improvements
    if (closing := data["closing_hour"]) is not None:
        bucket = closing_bucket_at(clock_minutes(closing))
        data["closes_after_midnight"] = bucket != "by_midnight"
        data["closes_after_2am"] = bucket == "after_2am"
    if data["outdoor_area"] not in (None, "none"):
        data["outdoor_seating"] = True
        data["sidewalk_or_parklet"] = data["outdoor_area"] == "sidewalk"
    occupants = _one(facts, "occupants")
    if occupants == OCCUPANTS_UNDER_50:
        data["occupants_under_50"] = True
    elif isinstance(occupants, int) and not isinstance(occupants, bool):
        data["occupants_under_50"] = occupants < 50
    elif occupants is not None:
        raise ValueError(f'occupants is a number or "{OCCUPANTS_UNDER_50}", got {occupants!r}')
    return BusinessProfile.model_validate(data)


def concept_facts_from_facts(facts: Mapping[str, Any]) -> ConceptFacts:
    """The concept facts of one "input_facts" or "record_facts" object: `profile_from_facts`, with the uses
    the object states under "planning_use" carried as stated uses."""
    return concept_facts(profile_from_facts(facts), stated_uses=stated_planning_uses(facts))
