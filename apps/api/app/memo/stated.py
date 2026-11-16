"""The stated-facts check: the intake model may only record facts the user's text states. No I/O, no model call.

User decision of 2026-11-12: "it may only record facts the text states. Anything it would infer becomes unknown
and is named in 'Insufficient information'." In the 40-case backtest the intake model filled 61 facts the rules
read that the text did not state; in D22 it read "a mezzanine" as a second story, where a Restaurant is not
permitted, and produced the only false blocker.

HOW IT WORKS
  1. The intake model sets a profile field the rules read (`QUOTED_FIELDS`) to anything but its "not stated"
     value only with a quote: the exact words of the text that state it (`MemoIntakeResult.quotes`, one entry per
     field, several allowed).
  2. Code checks each quote (`check_stated`). A quote counts when it is found in the text, after both are
     normalised (`normalise`: lower case, accents and punctuation dropped, spaces collapsed, a misspelt table word
     read as the word meant). A quote with "..." counts when every part is found, and each part is then read on
     its own (`quote_parts`): the words of a value must be inside one part, never joined across the "...".
     SPELLING (app.memo.spelling, change of 2026-11-15, approved with the release of 2026-11-16: a spelling mistake must
     not lose a fact the applicant stated). A word one slip from exactly one word of the tables is read as that
     word ("alochol" is "alcohol", "ppatio" is "patio"; a real word such as "ratio" or "mocktails" stays as
     written, no word is read as a negation, and only a word written all in plain lower case is ever respelt: a
     word with a capital, wherever it is, or with an accent may be a name, `names_in`). And a quote the intake model wrote with the spelling put right
     ("outside patio" for the applicant's "outside ppatio") still counts when each of its words is one slip at
     most from the word of the text it points at (`quote_found`; numbers and words under four letters must be
     equal). The words then read for the value are the applicant's own, cut from the text (`quote_spans`), never
     the model's.
  3. Code checks that the quoted words can state the value (`value_stated`). Mapping stated wording to a value is
     allowed ("ground-floor" -> the first story; "wine bar" -> a bar that pours beer and wine). The words for each
     value are in the tables below. A number must appear in the same quote as its unit for floor area
     (`NUMBER_UNITS`), and next to a word for seated places for seats (`seat_counts_in`: "40 seats", "seating for
     40", "40 people sitting", "room for 40 seated guests"; people, guests or customers with no word for sitting
     are not seats, nor are covers, nor "sit for 2 hours", nor a limit, "fewer than 50", nor a number with a time
     or a rate within two words, "seat 300 people a day", "seating for 90 minutes"); a closing time
     must be a time the quote gives after a closing word ("until 2 a.m.", "7am-2am", a misspelt "unitl 2 am"; not
     the opening time of "open 5:30 a.m. to 3 p.m."); a "no" needs a negation next to its own subject ("no live
     music", not just any "not" in the quote). A quote that hedges ("maybe live music") states none of the
     yes/no facts, the hours or the outdoor area (`HEDGED_FIELDS`).
  4. A field with no counted quote, or whose quotes do not state its value, is set back to "not stated" (`unset`:
     null, an empty list, false, "other" for the business type, "none" for what is poured). From a list
     (`stories`, `existing_use_stated`, `licences_held`) only the values the quotes do not state are removed.
  5. Every field cleared in whole or in part is recorded on the profile (`BusinessProfile.intake_cleared`: field
     -> the value removed), unless an applicant's answer, a clarification answer or an operator override later
     gives it, whatever the value (`record_cleared`). The rules (`app.memo.facts.ConceptFacts.cleared_facts`)
     name each one whose fact is not stated in the fixed phrase of `app.memo.facts.MISSING_PHRASES`. A row that
     needs it reads it as missing and is "Insufficient information". A cleared reading that something is there
     (alcohol served, entertainment, an outdoor area, a story: `cleared_readings`) is not read as "no": the row
     for it is added and is "Insufficient information", and a story not stated makes the use controls not
     decided. Every other cleared fact is asked in the report's open questions.
  6. A bar that the text says serves no alcohol (change of 2026-11-16). A false serves_alcohol cannot hold "no":
     it is also "not stated", and a Bar is read as serving alcohol whenever the text is silent. So where a counted
     quote for the kind of business or for alcohol says the business serves none (`NO_ALCOHOL_WORDS`:
     "zero-proof", "alcohol-free", "non-alcoholic", "sober", or a "no" next to a word for alcohol itself), and no
     kept value says alcohol is served, poured, licensed or held, `BusinessProfile.no_alcohol_stated` is set
     (`no_alcohol_stated`), and a cleared reading of alcohol is not recorded as "not stated": the text states the
     "no". The phrase a no-alcohol word modifies never states alcohol (`without_no_alcohol`: up to two other words,
     the words for drinks and the joins between them, and the business noun next, so "a zero-proof cocktail bar"
     and "a non-alcoholic beer and wine bar" serve none, for serves_alcohol and for what is poured alike); what
     follows it is still read ("a zero-proof bar serving wine", "and real cocktails", "and low-ABV"). "Sober
     curious" and "mocktail" are not no-alcohol words (review of 2026-11-16): neither says that no alcohol is
     served, so such a bar that answered nothing is a Bar. app.memo.pathway rule 1b reads the flag: such a
     business is not a Bar.

Quotes may come from the description and the clarification answers (`stated_text`). The applicant's intake
answers are applied by code after this check and always win, so they need no quote. Facts only the applicant
gives (`MODEL_MAY_NOT_SET`) are cleared before any of this.

WHAT THE CHECK CANNOT DO. It cannot tell a quoted word used in another sense ("a bar/restaurant" as the space's
last use read as the new business). It catches values the quoted words cannot state: "a mezzanine" never states a
second story, "vacant since 2017" never states a change of use, and no quote states an assumed closing hour or
seat count.

Pooled quotes: a field also reads the quotes of the fields that state the same thing (`QUOTE_GROUPS`): what is
poured, the licence type and the licences held for whether alcohol is served; the closing time for the two "closes
after" flags; the entertainment kind for live entertainment, amplified sound and dancing; the outdoor area for
outdoor seating and the sidewalk.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from app.memo.spelling import WORD, names_in, respell_text, same_word
from app.models.profile import QUOTED_FIELDS, BusinessProfile, FactQuote

# ---- the "not stated" value of each field ----------------------------------------------------------------------
# What a field holds when the text does not state it. The yes/no fields cannot hold "not stated", so they go back to
# false. On its own the rules would read that false as "no"; `cleared_readings` keeps the cleared "yes" so the rules
# read it as not known instead (app.memo.facts.ConceptFacts.cleared_readings).
UNSET: dict[str, Any] = {
    "business_type": "other",
    "serves_alcohol": False,
    "alcohol_type": "none",
    "licence_type": None,
    "licences_held": [],
    "square_feet": None,
    "floor_area_before_sqft": None,
    "seats": None,
    "existing_use_stated": [],
    "changes_existing_business": None,
    "merges_storefronts": None,
    "amends_prior_approval": None,
    "stories": [],
    "closing_hour": None,
    "closes_after_midnight": False,
    "closes_after_2am": False,
    "entertainment_kind": None,
    "live_entertainment": False,
    "amplified_sound": False,
    "dancing": False,
    "outdoor_area": None,
    "outdoor_seating": False,
    "sidewalk_or_parklet": False,
    "outdoor_alcohol_service": None,
    "change_of_use": False,
    "new_construction": False,
}
# Values that say nothing more than "not stated" and need no quote.
NEEDS_NO_QUOTE: dict[str, frozenset[Any]] = {"alcohol_type": frozenset({"none", "unknown"})}
LIST_FIELDS = frozenset({"licences_held", "existing_use_stated", "stories"})

# Fields that state the same thing: a field also reads the quotes given for the others in its group.
QUOTE_GROUPS: dict[str, tuple[str, ...]] = {
    "serves_alcohol": (
        "serves_alcohol",
        "alcohol_type",
        "licence_type",
        "licences_held",
        "outdoor_alcohol_service",
    ),
    "alcohol_type": ("alcohol_type", "licence_type"),
    "closes_after_midnight": ("closes_after_midnight", "closes_after_2am", "closing_hour"),
    "closes_after_2am": ("closes_after_2am", "closing_hour"),
    "live_entertainment": ("live_entertainment", "entertainment_kind"),
    "amplified_sound": ("amplified_sound", "live_entertainment", "entertainment_kind"),
    "dancing": ("dancing", "entertainment_kind"),
    "outdoor_seating": ("outdoor_seating", "outdoor_area", "sidewalk_or_parklet"),
    "sidewalk_or_parklet": ("sidewalk_or_parklet", "outdoor_area"),
}

# The fact of `app.memo.facts.MISSING_PHRASES` a cleared field leaves not known, and that the report names.
FACT_OF_FIELD: dict[str, str] = {
    "business_type": "planning_uses",
    "serves_alcohol": "alcohol_served",
    "alcohol_type": "alcohol_served",
    "licence_type": "licence_type",
    "licences_held": "licences_held",
    "square_feet": "floor_area_sqft",
    "floor_area_before_sqft": "floor_area_before_sqft",
    "seats": "seats",
    "existing_use_stated": "existing_use_stated",
    "changes_existing_business": "changes_existing_business",
    "merges_storefronts": "merges_storefronts",
    "amends_prior_approval": "amends_prior_approval",
    "stories": "stories",
    "closing_hour": "closing",
    "closes_after_midnight": "closing",
    "closes_after_2am": "closing",
    "entertainment_kind": "entertainment_kind",
    "live_entertainment": "entertainment_kind",
    "amplified_sound": "entertainment_kind",
    "dancing": "entertainment_kind",
    "outdoor_area": "outdoor_area",
    "outdoor_seating": "outdoor_area",
    "sidewalk_or_parklet": "outdoor_area",
    "outdoor_alcohol_service": "outdoor_alcohol_service",
    # what the space was before is what decides a change of use, and what new construction replaces
    "change_of_use": "existing_use_stated",
    "new_construction": "existing_use_stated",
}

# ---- the words that state each value (matched on the normalised quote) -----------------------------------------
_NEG_WORD = (
    r"(?:no|not|non|without|never|none|nor|neither|isn t|won t|will not|does not|doesn t|don t|aren t)"
)


def _negated(subject: str) -> str:
    """A "no" about one subject: a negation at most four words before the subject's words ("no live music",
    "will not be merged"), or at most three words after them ("entertainment: none"). A negation elsewhere in the
    quote states nothing about this subject."""
    return rf"\b{_NEG_WORD}(?: \w+){{0,4}} (?:{subject})\b|\b(?:{subject})(?: \w+){{0,3}} {_NEG_WORD}\b"


_ALCOHOL_WORDS = (
    r"alcohol\w*|beers?|wines?|liquors?|spirits|cocktails?|bars?|pubs?|taverns?|taprooms?|tap rooms?|"
    r"brewery|breweries|brewpubs?|sake|soju|ciders?|drinks|booze|abc|type \d{1,2}|on sale"
)
_ALCOHOL = rf"\b({_ALCOHOL_WORDS})\b"
# Words that say a business serves no alcohol (change of 2026-11-16): "a zero-proof cocktail bar", "an alcohol-free
# bar", "a non-alcoholic bar", "a sober bar", or a "no" next to a word for alcohol itself ("no alcohol", "without
# beer or wine"; "no bar" is not one). Matched on the normalised text, where "zero-proof" is "zero proof".
# "Sober curious" is not one: such a bar may serve low-alcohol drinks, so the words state no "no". "Mocktail" is
# not one either: it names a drink the business serves, not that it serves no alcohol (the applicant's "No alcohol"
# answer settles that). `NO_ALCOHOL_STATED_BY` reads them, and a quote's words they modify state no alcohol
# (`without_no_alcohol`).
NO_ALCOHOL_WORDS = (
    r"\b(zero proof|zero alcohol|alcohol free|alcoholfree|non alcoholic|nonalcoholic|booze free|spirit free|"
    r"sober(?! curious))\b"
)
# The phrase a no-alcohol word modifies (`without_no_alcohol`): up to two other words ("craft"), then the words for
# drinks and the joins between them ("beer and wine"), then the business noun it names, if one comes next ("bar").
# It stops at the first other word, so what follows ("serving wine", "and real cocktails") is still read.
_DRINKS_ONLY = r"alcohol\w*|beers?|wines?|liquors?|spirits|cocktails?|sake|soju|ciders?|drinks|booze"
_DRINKS_JOINED = rf"(?:{_DRINKS_ONLY}|and|or|n|plus)"
_BUSINESS_NOUNS = (
    r"bars?|pubs?|taverns?|taprooms?|tap rooms?|lounges?|brewpubs?|cafes?|clubs?|spots?|shops?|restaurants?|"
    r"venues?|places?|tasting rooms?"
)
_NO_ALCOHOL_PHRASE = (
    rf"(?:{NO_ALCOHOL_WORDS})(?: (?!(?:{_DRINKS_JOINED}|{_BUSINESS_NOUNS})\b)\w+){{0,2}}"
    rf"(?: {_DRINKS_JOINED}\b)*(?: (?:{_BUSINESS_NOUNS})\b)?"
)
_NO_ALCOHOL = rf"{NO_ALCOHOL_WORDS}|" + _negated(
    r"alcohol\w*|booze|liquors?|spirits|beers?|wines?|ciders?|sake|soju"
)
# The fields whose quotes can state that the business serves no alcohol (`BusinessProfile.no_alcohol_stated`).
NO_ALCOHOL_STATED_BY: tuple[str, ...] = ("business_type", "serves_alcohol")
_OUTDOOR_WORDS = (
    r"outdoors?|outside|patios?|terraces?|sidewalks?|parklets?|al fresco|gardens?|courtyards?|rooftop|roof|"
    r"decks?|beer garden|parking lot|yard"
)
_OUTDOOR = rf"\b({_OUTDOOR_WORDS})\b"
_ENTERTAINMENT_WORDS = (
    r"entertainment|music|musicians?|performances?|performers?|bands?|djs?|karaoke|danc\w*|shows?|live acts?"
)
# Words that make a quote a hope or a maybe, not a statement ("maybe live music"). A quote with one states no
# value of the fields in `HEDGED_FIELDS`.
_HEDGE = (
    r"\b(maybe|might|may|probably|possibly|perhaps|eventually|someday|potentially|in the future|down the road|"
    r"later on|not sure|unsure|undecided|tbd|hopeful\w*|hoping|hope to|considering)\b"
)
HEDGED_FIELDS = frozenset(
    {
        "serves_alcohol",
        "alcohol_type",
        "changes_existing_business",
        "merges_storefronts",
        "amends_prior_approval",
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
    }
)
VALUE_WORDS: dict[str, dict[Any, str]] = {
    "business_type": {
        "restaurant": (
            r"\b(restaurants?|eatery|eateries|diner|bistro|brasserie|trattoria|osteria|taqueria|pizzeria|"
            r"steakhouse|eating place|food hall|cantina|izakaya|noodle house|ramen shop|dim sum|burger joint)\b"
        ),
        "bar": (
            r"\b(bars?|pubs?|taverns?|saloon|lounge|taprooms?|tap rooms?|brewpubs?|brewery|breweries|"
            r"cocktail\w*|speakeasy|beer garden|beer hall|wine bar|sake bar)\b"
        ),
        "cafe": (
            r"\b(cafes?|coffee\w*|bakery|bakeries|teas?|tea ?(?:house|shop|room)s?|boba|juice|espresso|"
            r"patisserie|donuts?|doughnuts?|"
            r"ice cream|gelato|creamery|dessert\w*|bagels?|creperie)\b"
        ),
        "food_truck": r"\b(food trucks?|trucks?|carts?|trailers?|mobile food|mobile vending|food stand)\b",
        "hotel": r"\b(hotels?|motels?|inns?|b b|bed and breakfast|hostels?|lodging|guest house)\b",
        "catering": r"\b(cater\w*)\b",
    },
    "serves_alcohol": {True: _ALCOHOL},
    "alcohol_type": {
        "beer_wine": r"\b(beers?|wines?|ciders?|sake|type (0?2|23|40|41|42|60|61))\b",
        "full_liquor": (
            r"\b(cocktails?|spirits|liquor(?! licen[cs]es?)|liquors|full bar|distilled|whiske?y|mezcal|tequila|"
            r"vodka|gin|rum|martinis?|type (47|48|57|75|87))\b"
        ),
    },
    "changes_existing_business": {
        "enlarge": (
            r"\b(enlarg\w*|expan\w*|addition|larger|bigger|extend\w* into|add\w* (an? )?(\d+ )*(square f\w*|sq ft|"
            r"floor area|space|room|floor|stor\w*)|increase\w* (the |its )?(floor area|size|space)|"
            r"combin\w* (\w+ ){0,3}with (the |an )?existing)\b"
        ),
        # new entertainment or longer hours, in words (the field's own definition); a stronger licence alone is
        # not read as stated
        "intensify": (
            r"\b(intensif\w*|longer hours|later hours|extend\w* (the |its |their )?(\w+ )?hours|"
            r"add\w* (\w+ ){0,2}(nighttime entertainment|entertainment|live music|amplified \w+|dancing|djs?))\b"
        ),
        "none": (
            _negated(r"chang\w*|expan\w*|enlarg\w*|intensif\w*|alter\w*|bigger|larger|extend\w*")
            + r"|\b(unchanged|as is|same (size|hours|business|operation|footprint))\b"
        ),
    },
    "merges_storefronts": {
        True: r"\b(merg\w*|combin\w*|consolidat\w*|into one|join\w* (the |two )?(storefronts?|units?|spaces?))\b",
        False: _negated(r"merg\w*|combin\w*|consolidat\w*|join\w*"),
    },
    "amends_prior_approval": {
        True: (
            r"\b(conditions?|amend\w*|modif\w*|prior approval|earlier approval|existing (permission|approval|"
            r"conditional use|entitlement)|previous approval)\b"
        ),
        False: _negated(r"amend\w*|modif\w*|conditions?|approvals?"),
    },
    "stories": {
        "first": (
            r"\b(ground (floor|level|stor\w*)|street level|(first|1st) (floor|stor\w*|level)|"
            r"first and second (floor|stor)\w*)"
        ),
        "second": r"\b((second|2nd) (floor|stor\w*|level))",
        # a roof is not a story, and "top floor", "upstairs" or "an upper floor" do not say which (an upper floor
        # may be the third story or above): only a numbered story states it
        "third_or_above": r"\b((third|fourth|fifth|sixth|3rd|4th|5th|6th) (floor|stor\w*|level))",
        "basement": r"\b(basements?|cellars?|lower level|below grade|underground)\b",
    },
    "entertainment_kind": {
        "limited_live_performance": r"\b(limited live performance\w*|llp)\b",
        # Planning's Nighttime Entertainment use is what a Place of Entertainment permit covers; the profile has no
        # field for a stated use, so the stated use is carried here
        "place_of_entertainment": (
            r"\b(place of entertainment|nighttime entertainment|night time entertainment|nightclubs?|"
            r"night clubs?|danc\w*)\b"
        ),
        "none": _negated(_ENTERTAINMENT_WORDS),
    },
    "live_entertainment": {
        True: (
            r"\b(live (music|entertainment|performances?|bands?|jazz|acts?|shows?|djs?)|bands?|concerts?|"
            r"perform\w*|karaoke|comedy|open mic|djs?|musicians?|singers?|drag show\w*|cabaret)\b"
        ),
    },
    "amplified_sound": {True: r"\b(amplif\w*|sound system|speakers?|djs?|pa system|loud music)\b"},
    "dancing": {True: r"\b(danc\w*)\b"},
    "outdoor_area": {
        "front": r"\b(front (patio|yard|terrace|area|setback)|in front)\b",
        "rear_or_side": (
            r"\b(rear|back ?yard|back (patio|garden|terrace)|side (patio|yard)|courtyard|garden)\b"
        ),
        "rooftop": r"\b(rooftop|roof\w*)\b",
        "parking_lot": r"\b(parking (lot|area|space)s?|car park)\b",
        "sidewalk": r"\b(sidewalks?|parklets?|curb\w*|shared spaces?|parking lane|street seating)\b",
        "none": _negated(_OUTDOOR_WORDS) + r"|\b(indoors? only|only indoors?)\b",
    },
    "outdoor_seating": {True: _OUTDOOR},
    "sidewalk_or_parklet": {
        True: r"\b(sidewalks?|parklets?|curb\w*|shared spaces?|parking lane|street seating)\b"
    },
    "change_of_use": {
        True: (
            r"\b(change (of|in) use|change from|convert\w*|conversion|repurpos\w*|turn\w* (\w+ ){0,4}into|"
            r"from (an? |the )?\w+ (\w+ )?(to|into) (an? )?(restaurant|bar|cafe))\b"
        ),
    },
    "new_construction": {
        True: (
            r"\b(new construction|new building|ground up|newly built|(build|construct)\w* (an? )?(new|\w+ stor\w*|"
            r"rear|side)|addition)\b"
        ),
    },
}
# The words of each value of `existing_use_stated` (a list: each value is checked on its own).
EXISTING_USE_WORDS: dict[str, str] = {
    "bar": r"\b(bars?|pubs?|taverns?|lounge|saloon|taprooms?)\b",
    "restaurant": r"\b(restaurants?|eatery|diner|bistro|taqueria|pizzeria)\b",
    "limited_restaurant": (
        r"\b(limited restaurant|cafes?|coffee\w*|bakery|deli|take ?out|boba|tea|juice|ice cream|sandwich\w*)\b"
    ),
    "nighttime_entertainment": (
        r"\b(nighttime entertainment|night time entertainment|nightclubs?|night clubs?|clubs?|music venue|"
        r"entertainment venue|dance hall)\b"
    ),
    "retail": r"\b(retail|stores?|shops?|boutique|gallery|market)\b",
    "laundromat": r"\b(laundromats?|laundry|laundries|dry clean\w*|cleaners)\b",
    "vacant": r"\b(vacant|empty|unoccupied|unused|shuttered|closed)\b",
    # "other" has no words of its own: the quote must say it is about the space's earlier use
    "other": (
        r"\b(former\w*|previous\w*|prior|old|was|were|used to be|last used|occupied by|home to|vacated|"
        r"took over|taking over|replac\w*|existing)\b"
    ),
}
# A unit a number must come with, so a seat count is never read as a floor area.
NUMBER_UNITS: dict[str, str] = {
    # not a bare "sf", which is also San Francisco
    "square_feet": r"\b(square f\w*|sq ft|sqft|sq feet)\b",
    "floor_area_before_sqft": r"\b(square f\w*|sq ft|sqft|sq feet)\b",
}
# A seat count: a number next to a word for seated places (review of 2026-11-15). "40 seats", "a 40-seat room",
# "40 indoor seats", "40 bar stools"; "40 people sitting", "40 guests seated"; "seating for 40", "seats 40",
# "can seat 40", "seating capacity of 40". People, guests, diners or customers with no word for sitting are not
# seats ("300 customers a day", "100 people standing", "room for 40 guests"), nor is a capacity, nor a count of
# staff ("seating for 30 and a staff of 60" gives 30 seats, never 60). Second review of 2026-11-15: covers are
# meals served, never seats ("200 covers on Saturdays"), and "sit for" or "sits" is how long or how many sit, never
# a seat count ("guests can sit for 2 hours").
_SEAT_UNIT = r"(?:seats?|seated|seaters?|seating|sit down|chairs|stools)"
_SEAT_KIND = (
    r"(?:indoor|outdoor|inside|outside|interior|patio|dining|bar|counter|table|booth|total|fixed|existing)"
)
_SEATED = r"(?:people|persons|guests|diners|patrons|customers) (?:sitting|seated)"
_SEAT_COUNT = re.compile(
    rf"\b(?P<before>\d+) (?:{_SEAT_KIND} ){{0,2}}{_SEAT_UNIT}\b|\b(?P<people>\d+) {_SEATED}\b"
    r"|\b(?:seats?|seating)(?: capacity)?(?: for| of)? (?P<after>\d+)\b"
)
# A number after one of these is a limit, not a count ("fewer than 50 seats", "seating for up to 40") ...
_SEAT_LIMIT = re.compile(
    r"\b(?:fewer than|less than|more than|greater than|under|over|below|above|at least|at most|up to|upwards of|"
    r"nearly|almost|maximum of|max|minimum of|min)\s*$"
)
# ... and a count a day, a night or a week is how many are served, not how many the room seats ("200 seats a
# night"), and a number of minutes, days or months is a time, not a count ("seating for 90 minutes"). Second
# review of 2026-11-15: a number followed, within two words, by a unit of time or a rate is never a seat count,
# wherever the seat word is ("we can seat 300 people a day", "patio seating for 6 months a year"). "Sitting",
# "service" and "turn" are units of time only as nouns of a count ("per sitting", "two sittings", "each dinner
# service"), so "40 people sitting" and "a 40-seat full service restaurant" are still seat counts.
_PERIOD = (
    r"(?:minutes?|mins?|hours?|hrs?|days?|weeks?|weekends?|months?|years?|nights?|evenings?|mornings?|afternoons?|"
    r"seasons?|shifts?|services?|sittings?|turns?)"
)
_TIME_UNIT = (
    r"(?:minutes?|mins?|hours?|hrs?|days?|weeks?|weekends?|months?|years?|nights?|evenings?|seasons?|services|"
    r"sittings|turns)"
)
_RATE = rf"(?:(?:a|an|per|each|every) (?:\w+ )?{_PERIOD}|daily|nightly|weekly|monthly|yearly|annually|hourly)"
_SEAT_RATE = re.compile(rf"^ {_RATE}\b")
# Third pass of the review of 2026-11-15. A number AFTER the seat word ("we seat 300 ...", "seating 5:30 pm",
# "tables seat 4 each") is not the room's seat count when anything later in its clause makes it a rate, a time or
# a count per table: "we seat 300 people throughout the day", "seats 1000 guests per annum", "first seating 5:30
# pm", "booths seat 6 people per booth". The clause ends at a comma, a full stop or a semicolon, so "seating for
# 40, open 7 days a week" is still 40 seats.
_PER_UNIT = r"(?:each|apiece|per (?:table|booth|bench|counter|person|head|guest|seating|party|group))"
_SEAT_TIME = re.compile(rf"^(?: \w+){{0,2}} (?:{_TIME_UNIT}|{_RATE}|{_PER_UNIT}|am|pm|noon|o clock|oclock)\b")
_LATER_IN_CLAUSE = re.compile(
    rf"\b(?:{_TIME_UNIT}|{_RATE}|{_PER_UNIT}|throughout|per annum|annum|am|pm|noon|o clock|oclock)\b"
)
_CLAUSE_END = re.compile(r"[.,;!?()]+(?=\s|$)")
# Words for a close after midnight / after 2 a.m. when no time is given.
AFTER_MIDNIGHT_WORDS = (
    r"\b(after midnight|past midnight|all night|overnight|24 hours|24 7|around the clock)\b"
)
AFTER_2AM_WORDS = (
    r"\b(after 2 ?am|past 2 ?am|after 2 a m|past 2 a m|all night|overnight|24 hours|24 7|around the clock)\b"
)
_DAY = 24 * 60


# ---- normalising and finding a quote ---------------------------------------------------------------------------
# The names of the text being checked (`app.memo.spelling.names_in`: words the text writes anywhere with a capital or
# an accent, "Chang", "Patino", "Patiño"), never respelt in a quote that writes them in lower case
# ("chang from the sunset", "patino").
_NAMES: ContextVar[frozenset[str]] = ContextVar("stated_names", default=frozenset())


@contextmanager
def _names_of(text: str) -> Iterator[None]:
    token = _NAMES.set(_NAMES.get() | names_in(text))
    try:
        yield
    finally:
        _NAMES.reset(token)


def _read(text: str) -> str:
    """Lower case, accents dropped, curly quotes made plain, and every misspelt word that may be respelt read as
    the word meant (`app.memo.spelling.respell_text`: only words written all in plain lower case, never a name).
    Punctuation is kept, so a time ("1:30", "2 a.m.") reads as written."""
    return respell_text(text, _NAMES.get())


def _normalise(text: str) -> str:
    text = re.sub(r"(?<=\d)[,.](?=\d{3}\b)", "", _read(text))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def normalise(text: str) -> str:
    """The text as quotes are matched: lower case, accents dropped, every run of characters that is not a letter
    or a digit made one space, a comma or a point between digits dropped ("3,953" -> "3953"), and a word one
    slip from exactly one word of the tables read as that word (`app.memo.spelling.respell`: "alochol" ->
    "alcohol"; a real word such as "ratio" and a name such as "Chang" are never changed)."""
    return _normalise(text)


def quote_parts(quote: str) -> list[str]:
    """The parts of a quote: the words either side of each "..." (or "…"), as written. A quote without one is
    one part. The words of a value must be inside one part, never across a join."""
    return [p.strip() for p in re.split(r"\.\.\.+|…", quote) if normalise(p)]


def quote_found_as_written(quote: str, text: str) -> bool:
    """Whether a quote is in the text word for word, both normalised, on word boundaries. A quote with "..." (or
    "…") counts when each part is found. A part needs at least two letters or digits."""
    with _names_of(text):
        padded = f" {normalise(text)} "
        parts = [normalise(p) for p in quote_parts(quote)]
    if not parts or any(len(p.replace(" ", "")) < 2 for p in parts):
        return False
    return all(f" {p} " in padded for p in parts)


def _find(want: Sequence[str], words: Sequence[str]) -> int | None:
    """Where the words `want` start in `words`: the first place they are found as written, else the first place
    each is the same word as the one it points at (`app.memo.spelling.same_word`: one slip apart at most, numbers
    and short words equal). None when there is no such place."""
    spans = range(len(words) - len(want) + 1)
    hit = next((i for i in spans if list(words[i : i + len(want)]) == list(want)), None)
    if hit is not None:
        return hit
    return next(
        (i for i in spans if all(same_word(w, words[i + k]) for k, w in enumerate(want))),
        None,
    )


def quote_found(quote: str, text: str) -> bool:
    """Whether a quote points at words of the text: found as written (`quote_found_as_written`), or, word for
    word, one slip of spelling apart at most (the intake model quoted "outside patio" where the applicant wrote
    "outside ppatio"). A quote with "..." (or "…") counts when each part is found. A part needs at least two
    letters or digits."""
    if quote_found_as_written(quote, text):
        return True
    with _names_of(text):
        parts = [normalise(p).split() for p in quote_parts(quote)]
        words = normalise(text).split()
    if not parts or any(len("".join(p)) < 2 for p in parts):
        return False
    return all(_find(p, words) is not None for p in parts)


# A word, or a number written with group separators ("3,953"), as `normalise` reads it (`app.memo.spelling.WORD`:
# an accent written as a mark of its own stays inside its word).
_TOKEN = re.compile(rf"\d+(?:[,.]\d{{3}})+(?!\d)|{WORD.pattern}")


def quote_spans(quote: str, text: str) -> tuple[str, ...]:
    """The applicant's own words a quote matches, cut from the text as written (a misspelt word stays as the
    applicant wrote it): one span for each part of the quote (the words either side of a "..."), so words from
    different places are never shown joined as one sentence. Empty when a part is not found (as `quote_found`, on
    word boundaries)."""
    with _names_of(text):
        return _quote_spans(quote, text)


def _quote_spans(quote: str, text: str) -> tuple[str, ...]:
    words: list[tuple[str, int, int]] = []
    for m in _TOKEN.finditer(text):
        # each word read as it is read in the whole text: a word with a capital or an accent stays as written
        words.extend((w, m.start(), m.end()) for w in _normalise(m.group()).split())
    norm = [w for w, _start, _end in words]
    spans: list[str] = []
    for part in quote_parts(quote):
        want = normalise(part).split()
        if len("".join(want)) < 2:
            return ()
        hit = _find(want, norm)
        if hit is None:
            return ()
        spans.append(text[words[hit][1] : words[hit + len(want) - 1][2]])
    return tuple(spans)


# ---- whether quoted words state a value ------------------------------------------------------------------------
_TIME = re.compile(
    r"\b(?P<h>\d{1,2})(?:[:.](?P<m>[0-5]\d))?\s*(?P<ap>a\.?\s?m\b\.?|p\.?\s?m\b\.?|o'?clock)?|\b(?P<w>midnight|noon)\b"
)


def times_in(quote: str) -> set[int]:
    """The clock times a quote gives, as minutes after midnight. A bare number is a time only with minutes
    ("1:30"), "am"/"pm" or "o'clock"; "midnight" is 00:00 and "noon" 12:00. Without am/pm both readings count."""
    found: set[int] = set()
    for m in _TIME.finditer(_read(quote)):
        if m.group("w"):
            found.add(0 if m.group("w") == "midnight" else 12 * 60)
            continue
        hour, minute, ap = int(m.group("h")), int(m.group("m") or 0), (m.group("ap") or "").replace(" ", "")
        if m.group("m") is None and not ap:
            continue
        if hour > 24 or (ap and ap[0] in "ap" and not 1 <= hour <= 12):
            continue
        if ap.startswith("a"):
            found.add((hour % 12) * 60 + minute)
        elif ap.startswith("p"):
            found.add((hour % 12 + 12) * 60 + minute)
        else:
            found.update({(hour % 24) * 60 + minute, ((hour + 12) % 24) * 60 + minute})
    return found


# Words just before a time that make it a closing time ("until 2 a.m.", "to 3 p.m.", "closes at 1", "7am-2am").
_CLOSING_BEFORE = re.compile(
    r"(?:\b(?:until|till|til|to|through|thru|close[sd]?|closing|last call|ends?|ending)|[-–—])\W*"
    r"(?:[a-z]+\W+){0,2}$"
)


def closing_times_in(quote: str) -> set[int]:
    """The closing times a quote gives: the times of `times_in` that follow a closing word ("until", "to",
    "closes", a dash). In "open 5:30 a.m. to 3 p.m." only 3 p.m. is a closing time. A misspelt closing word is
    read as the word meant ("open unitl 2 am", "until midnigt")."""
    folded = _read(quote)
    found: set[int] = set()
    for m in _TIME.finditer(folded):
        if _CLOSING_BEFORE.search(folded[: m.start()]):
            found |= times_in(m.group(0))
    return found


def seat_counts_in(quote: str) -> set[int]:
    """The seat counts a quote gives: each number next to a word for seated places (`_SEAT_COUNT`), unless it is
    a limit ("fewer than 50 seats"), a rate ("200 seats a night") or a time ("seating for 90 minutes"; a unit of
    time or a rate within two words of the number, `_SEAT_TIME`)."""
    found: set[int] = set()
    for clause in _CLAUSE_END.split(quote):
        norm = normalise(clause)
        for m in _SEAT_COUNT.finditer(norm):
            key = next(k for k in ("before", "people", "after") if m.group(k))
            if (
                _SEAT_LIMIT.search(norm[: m.start(key)])
                or _SEAT_TIME.search(norm[m.end(key) :])
                or _SEAT_RATE.search(norm[m.end() :])
                or (key == "after" and _LATER_IN_CLAUSE.search(norm[m.end(key) :]))
            ):
                continue
            found.add(int(m.group(key)))
    return found


def numbers_in(quote: str) -> set[int]:
    """The whole numbers in a quote ("3,953" is 3953)."""
    return {int(n) for n in re.findall(r"\d+", normalise(quote))}


def without_no_alcohol(quote: str) -> str:
    """The quote, normalised, with every phrase a no-alcohol word modifies left out (`_NO_ALCOHOL_PHRASE`): "a
    non-alcoholic beer and wine bar" -> "a ", "a zero-proof bar serving wine" -> "a  serving wine"."""
    return re.sub(_NO_ALCOHOL_PHRASE, " ", normalise(quote))


def _says(pattern: str, quotes: Sequence[str]) -> bool:
    return any(re.search(pattern, normalise(q)) for q in quotes)


def value_stated(field: str, value: Any, quotes: Sequence[str]) -> bool:
    """Whether the quoted words state this value of the field (one value of a list field). `quotes` are the
    counted quotes the field reads."""
    if field in HEDGED_FIELDS:
        quotes = [q for q in quotes if not re.search(_HEDGE, normalise(q))]
    if not quotes:
        return False
    if field == "seats":
        # the number next to its word for seated places, in the same quote (or the same part of one)
        return isinstance(value, int) and any(value in seat_counts_in(q) for q in quotes)
    if field in ("square_feet", "floor_area_before_sqft"):
        # the number and its unit in the same quote (or the same part of one)
        return isinstance(value, int) and any(
            value in numbers_in(q) and re.search(NUMBER_UNITS[field], normalise(q)) for q in quotes
        )
    if field == "licence_type" or field == "licences_held":
        m = re.search(r"\d{1,3}", str(value))
        return m is not None and int(m.group(0)) in set().union(*map(numbers_in, quotes))
    if field == "closing_hour":
        hh, mm = str(value).split(":")
        return int(hh) * 60 + int(mm) in set().union(*map(closing_times_in, quotes))
    if field in ("closes_after_midnight", "closes_after_2am"):
        start, words = (
            (0, AFTER_MIDNIGHT_WORDS) if field == "closes_after_midnight" else (120, AFTER_2AM_WORDS)
        )
        late = any(start < t <= 6 * 60 for t in set().union(*map(closing_times_in, quotes)))
        return late or _says(words, quotes)
    if field == "existing_use_stated":
        return value in EXISTING_USE_WORDS and _says(EXISTING_USE_WORDS[value], quotes)
    if field == "outdoor_alcohol_service":
        if value is True:
            return any(
                re.search(_ALCOHOL, normalise(q)) and re.search(_OUTDOOR, normalise(q)) for q in quotes
            )
        return _says(_negated(_ALCOHOL_WORDS), quotes)
    if field == "serves_alcohol" and value is True:
        # "zero-proof cocktail bar" states no alcohol: the phrase a no-alcohol word modifies is left out before the
        # alcohol words are looked for
        return any(re.search(_ALCOHOL, without_no_alcohol(q)) for q in quotes)
    if field == "alcohol_type" and value in ("beer_wine", "full_liquor"):
        # "a non-alcoholic beer and wine bar" states no beer or wine served, as for serves_alcohol
        poured = VALUE_WORDS[field][value]
        return any(re.search(poured, without_no_alcohol(q)) for q in quotes)
    if field == "changes_existing_business" and value == "enlarge_and_intensify":
        return value_stated(field, "enlarge", quotes) and value_stated(field, "intensify", quotes)
    pattern = VALUE_WORDS.get(field, {}).get(value)
    return pattern is not None and _says(pattern, quotes)


# ---- the check ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class StatedCheck:
    """The profile with every unquoted or unstated value set back to "not stated", and what was removed: field ->
    the model's value (for a list field, the values removed)."""

    profile: BusinessProfile
    cleared: dict[str, Any]


def is_unset(field: str, value: Any) -> bool:
    """Whether a value says no more than "not stated"."""
    return value == UNSET[field] or (
        isinstance(value, str) and value in NEEDS_NO_QUOTE.get(field, frozenset())
    )


# The profile fields that hold text the intake model wrote and that no rule reads, so the stated-facts check does
# not check them: its note on what it assumed, and the name and neighbourhood as it copied them.
MODEL_TEXT_FIELDS = ("assumptions", "business_name", "neighborhood")


def without_model_text(profile: BusinessProfile) -> BusinessProfile:
    """The profile with `MODEL_TEXT_FIELDS` emptied. The memo stores and serves only this, so no text the intake
    model wrote leaves the API with a memo."""
    return profile.model_copy(update={"assumptions": [], "business_name": None, "neighborhood": None})


def stated_text(description: str, answers: Iterable[Any] = ()) -> str:
    """The text quotes may come from: the description, then each clarification answer the applicant wrote in
    words. (A yes/no, number or choice answer sets its own field by code, `AgentRunner._merge_profile`, so it
    needs no quote; the question's wording is not the applicant's.)"""
    return "\n".join([description, *(a for a in answers if isinstance(a, str) and a.strip())])


def check_stated(profile: BusinessProfile, quotes: Sequence[FactQuote], text: str) -> StatedCheck:
    """Clear every field of `QUOTED_FIELDS` the quotes do not state (see the module docstring). Pure."""
    with _names_of(text):  # a name of the text is never respelt, in the text or in a quote
        return _check_stated(profile, quotes, text)


def _check_stated(profile: BusinessProfile, quotes: Sequence[FactQuote], text: str) -> StatedCheck:
    counted: dict[str, list[str]] = {}
    for q in quotes:
        if quote_found_as_written(q.quote, text):
            counted.setdefault(q.field, []).extend(quote_parts(q.quote))
        elif quote_found(q.quote, text):
            # found only once its spelling is allowed one slip a word: the value is read from the applicant's own
            # words, never from the model's corrected ones
            counted.setdefault(q.field, []).extend(quote_spans(q.quote, text))
    data = profile.model_dump()
    cleared: dict[str, Any] = {}
    for field in QUOTED_FIELDS:
        value = data[field]
        if is_unset(field, value):
            continue
        said = [q for f in QUOTE_GROUPS.get(field, (field,)) for q in counted.get(f, [])]
        if field in LIST_FIELDS:
            kept = [v for v in value if value_stated(field, v, said)]
            removed = [v for v in value if v not in kept]
            if removed:
                data[field], cleared[field] = kept, removed
        elif not value_stated(field, value, said):
            data[field], cleared[field] = UNSET[field], value
    # what is poured goes with whether alcohol is served: a concept left serving none pours none
    if not data["serves_alcohol"] and data["alcohol_type"] != "none" and "serves_alcohol" in cleared:
        cleared.setdefault("alcohol_type", data["alcohol_type"])
        data["alcohol_type"] = "none"
    # the text names the business in words that say it serves no alcohol ("a zero-proof cocktail bar") and states
    # no alcohol served: pathway rule 1 does not read it as a Bar (Planning Code § 102)
    data["no_alcohol_stated"] = no_alcohol_stated(data, counted)
    if data["no_alcohol_stated"]:
        # the text states the "no" the profile now holds: a cleared reading of alcohol is not "not stated"
        for field in ("serves_alcohol", "alcohol_type"):
            cleared.pop(field, None)
    data["intake_cleared"] = {}
    return StatedCheck(BusinessProfile.model_validate(data), cleared)


def no_alcohol_stated(data: Mapping[str, Any], counted: Mapping[str, Sequence[str]]) -> bool:
    """Whether the text states that the business serves no alcohol: a counted quote of `NO_ALCOHOL_STATED_BY`
    says so (`NO_ALCOHOL_WORDS`, or a "no" next to a word for alcohol), and nothing kept says alcohol is served,
    poured, licensed or held. Only a bar is asked about: the other kinds of business are read as serving no alcohol
    already whenever the text does not state it."""
    if not no_alcohol_can_stand(data):
        return False
    said = [q for f in NO_ALCOHOL_STATED_BY for q in counted.get(f, [])]
    return _says(_NO_ALCOHOL, said)


def no_alcohol_can_stand(data: Mapping[str, Any]) -> bool:
    """Whether a profile can carry `no_alcohol_stated`: a bar, and nothing on it says alcohol is served, poured,
    licensed or held. The check reads it before the clarification answers and the operator overrides are applied,
    and the runner again after (`MemoRunner.run_memo`), so an override that gives a licence type keeps it a Bar."""
    if data["business_type"] != "bar" or data["serves_alcohol"] or data["alcohol_type"] != "none":
        return False
    return not (data["licence_type"] or data["licences_held"] or data["outdoor_alcohol_service"])


def record_cleared(
    final: BusinessProfile, checked: StatedCheck, given: Iterable[str] = ()
) -> BusinessProfile:
    """The final profile with `intake_cleared` set: each field the check cleared, unless something given later
    set it. `given` are the fields an intake answer, a clarification answer or an operator override set, whatever
    the value (a "No alcohol" answer gives serves_alcohol false, the same value the check left, and it is given).
    A field whose value changed since the check is given too."""
    after = checked.profile.model_dump()
    now = final.model_dump()
    told = set(given)
    kept = {f: v for f, v in checked.cleared.items() if f not in told and now[f] == after[f]}
    return final.model_copy(update={"intake_cleared": kept})


# A cleared value that said something is there, by the fact the rules read: whether alcohol is served, whether
# there is entertainment, whether there is an outdoor area, which story. The rules read these as not known, not as
# "no" (`cleared_readings`).
PRESENCE_FIELDS: dict[str, str] = {
    "serves_alcohol": "alcohol_served",
    "live_entertainment": "entertainment_kind",
    "amplified_sound": "entertainment_kind",
    "dancing": "entertainment_kind",
    "entertainment_kind": "entertainment_kind",
    "outdoor_seating": "outdoor_area",
    "sidewalk_or_parklet": "outdoor_area",
    "outdoor_area": "outdoor_area",
    "stories": "stories",
}


def cleared_readings(cleared: Mapping[str, Any]) -> tuple[str, ...]:
    """The facts (`app.memo.facts.MISSING_PHRASES` keys) for which the check removed a reading that something is
    there: a yes, a kind of entertainment, a place for the outdoor area, a story. A removed "no" ("none", false) is
    not one. Each once, in the order of `QUOTED_FIELDS`."""
    found = (
        PRESENCE_FIELDS[f]
        for f in QUOTED_FIELDS
        if f in PRESENCE_FIELDS and f in cleared and cleared[f] not in (False, None, "none", [], "unknown")
    )
    return tuple(dict.fromkeys(found))


def cleared_fact_names(cleared: Mapping[str, Any]) -> tuple[str, ...]:
    """The facts (`app.memo.facts.MISSING_PHRASES` keys) the cleared fields leave not known, each once, in the
    order of `QUOTED_FIELDS`."""
    return tuple(dict.fromkeys(FACT_OF_FIELD[f] for f in QUOTED_FIELDS if f in cleared))
