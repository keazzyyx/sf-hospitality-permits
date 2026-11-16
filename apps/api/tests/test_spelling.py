"""Spelling slips in the applicant's own words (app.memo.spelling) and what the stated-facts check does with them
(app.memo.stated). No database, no network, no model.

The case behind the rule is the report of 2026-11-15 for 2301 Chestnut St: the description said "Indian food
restaurant with alochol license, open till 2 am and 40 people sitting with a outside ppatio", and the report said
the description "does not state whether there will be an outdoor area" and did not know the seats.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from app.agents import prompts
from app.memo import facts, intake, spelling
from app.memo.evidence import counted_quotes
from app.memo.spelling import (
    _REAL_WORDS_FILE,
    NOT_MISSPELLINGS,
    RESPELL_MIN_LETTERS,
    SAME_WORD_MIN_LETTERS,
    SPELLING_WORDS,
    one_slip,
    respell,
    same_word,
    slips,
)
from app.memo.stated import (
    check_stated,
    normalise,
    quote_found,
    quote_found_as_written,
    quote_spans,
    value_stated,
)
from app.models.profile import BusinessProfile, FactQuote

CHESTNUT = (
    "Indian food restaurant with alochol license, open till 2 am and 40 people sitting with a outside ppatio"
)
# what the intake model reads from it
CHESTNUT_PROFILE: dict[str, Any] = {
    "business_type": "restaurant",
    "serves_alcohol": True,
    "alcohol_type": "unknown",
    "seats": 40,
    "closing_hour": "02:00",
    "closes_after_midnight": True,
    "outdoor_seating": True,
}
# the quotes as the applicant wrote the words, and as a model that puts the spelling right writes them
AS_WRITTEN = [
    ("business_type", "Indian food restaurant"),
    ("serves_alcohol", "alochol license"),
    ("seats", "40 people sitting"),
    ("closing_hour", "open till 2 am"),
    ("closes_after_midnight", "open till 2 am"),
    ("outdoor_seating", "outside ppatio"),
]
CORRECTED = [
    ("business_type", "Indian food restaurant"),
    ("serves_alcohol", "alcohol license"),
    ("seats", "40 people sitting"),
    ("closing_hour", "open till 2 am"),
    ("closes_after_midnight", "open till 2 am"),
    ("outdoor_seating", "outside patio"),
]


def quotes(pairs: list[tuple[str, str]]) -> list[FactQuote]:
    return [FactQuote.model_validate({"field": f, "quote": q}) for f, q in pairs]


def checked(profile: dict[str, Any], pairs: list[tuple[str, str]], text: str) -> dict[str, Any]:
    return check_stated(BusinessProfile.model_validate(profile), quotes(pairs), text).cleared


# ---- the tables ---------------------------------------------------------------------------------------------------
def test_the_two_tables_do_not_overlap_and_hold_only_words_long_enough_to_respell() -> None:
    assert SPELLING_WORDS and NOT_MISSPELLINGS
    assert not SPELLING_WORDS & NOT_MISSPELLINGS
    for word in (*SPELLING_WORDS, *NOT_MISSPELLINGS):
        assert word == word.lower() and word.isascii() and word.isalpha(), word
        assert len(word) >= RESPELL_MIN_LETTERS, word


def test_no_word_of_either_table_is_ever_respelt() -> None:
    for word in (*SPELLING_WORDS, *NOT_MISSPELLINGS):
        assert respell(word) == word, word


def test_every_listed_real_word_is_one_slip_from_a_table_word() -> None:
    """The list holds only words `respell` would otherwise change: nothing in it is there for another reason."""
    for word in NOT_MISSPELLINGS:
        assert any(abs(len(t) - len(word)) <= 1 and one_slip(word, t) for t in SPELLING_WORDS), word


def test_the_real_words_file_says_how_it_was_built() -> None:
    doc = json.loads(_REAL_WORDS_FILE.read_text(encoding="utf-8"))
    assert sorted(doc) == ["about", "words"]
    assert "SPELLING_WORDS" in doc["about"] and "rebuild" in doc["about"]
    assert doc["words"] == sorted(set(doc["words"]))


@pytest.mark.parametrize(
    ("near", "table_word"),
    [
        ("ratio", "patio"),  # "floor area ratio" is not a patio
        ("bears", "beers"),
        ("wives", "wines"),
        ("flour", "floor"),
        ("eight", "might"),
        ("sweats", "seats"),
        ("garner", "garden"),
        ("vacate", "vacant"),
        ("retain", "retail"),
    ],
)
def test_a_real_word_next_to_a_table_word_stays_as_written(near: str, table_word: str) -> None:
    assert one_slip(near, table_word) or slips(near, table_word, 2) <= 2
    assert respell(near) == near
    assert normalise(f"a {near} here") == f"a {near} here"


# ---- one slip -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("written", "meant"),
    [
        ("alochol", "alcohol"),  # two letters swapped
        ("ppatio", "patio"),  # a letter added
        ("patoi", "patio"),
        ("resturant", "restaurant"),  # a letter dropped
        ("restuarant", "restaurant"),
        ("liqour", "liquor"),
        ("cocktials", "cocktails"),
        ("sidewlak", "sidewalk"),
        ("outsdie", "outside"),
        ("muisc", "music"),
        ("basment", "basement"),
        ("wihtout", "without"),  # a negation keeps negating
        ("mabye", "maybe"),  # a hedge keeps hedging
        ("posibly", "possibly"),
        ("lisence", "licence"),
        ("licnese", "license"),
    ],
)
def test_a_word_one_slip_from_one_table_word_is_read_as_it(written: str, meant: str) -> None:
    assert one_slip(written, meant)
    assert respell(written) == meant
    assert normalise(f"The {written}!") == f"the {meant}"
    # second review of 2026-11-15: a word with a capital is never respelt, even the first word of a sentence; third
    # pass: but a word read as a hedge is read as the hedge whatever its case (it can only make a fact "not stated")
    capital = meant if meant in spelling.HEDGE_WORDS else written
    assert normalise(f"{written.upper()} here") == f"{capital} here"
    assert normalise(f"{written.capitalize()} here. a {written}") == f"{capital} here a {meant}"


@pytest.mark.parametrize(
    "word",
    [
        "pat",  # under five letters: never respelt
        "wien",
        "bere",
        "resturaunt",  # two slips from "restaurant"
        "alkohall",
        "indain",  # one slip from "Indian", which is not a table word
        "x9ppatio",  # not a word
        "40",
    ],
)
def test_what_is_not_one_slip_from_a_table_word_stays_as_written(word: str) -> None:
    assert respell(word) == word


def test_a_word_one_slip_from_two_table_words_is_left_alone() -> None:
    """The rules never pick between two readings: "hotel" and "motel" are both table words, and a word one slip
    from each is read as neither."""
    assert {"hotel", "motel"} <= SPELLING_WORDS
    assert one_slip("xotel", "hotel") and one_slip("xotel", "motel")
    assert respell("xotel") == "xotel"


def test_slips_counts_one_letter_or_one_swap() -> None:
    assert slips("patio", "patio", 1) == 0
    assert slips("ppatio", "patio", 1) == 1 and slips("patio", "ppatio", 1) == 1
    assert slips("alochol", "alcohol", 1) == 1  # a swap is one slip, not two
    assert slips("ratio", "patio", 1) == 1
    assert slips("resturaunt", "restaurant", 1) == 2  # "more than one", capped at the limit plus one
    assert slips("resturaunt", "restaurant", 2) == 2
    assert slips("bar", "restaurant", 1) == 2


# ---- the same word, in a quote and in the text ----------------------------------------------------------------------
def test_same_word() -> None:
    assert same_word("patio", "ppatio") and same_word("ppatio", "patio")
    assert same_word("indian", "indain")  # not a table word: one slip apart is enough
    assert same_word("alcohol", "alochol")
    # numbers must be equal, and so must words under four letters
    assert not same_word("40", "400") and not same_word("40", "04") and same_word("40", "40")
    assert not same_word("no", "on") and not same_word("bar", "car") and not same_word("2am", "3am")
    assert SAME_WORD_MIN_LETTERS == 4 and same_word("wine", "wien") and not same_word("wine", "beer")
    # two slips apart is another word
    assert not same_word("restaurant", "resturaunt")


def test_a_quote_with_the_spelling_put_right_points_at_the_applicants_words() -> None:
    assert not quote_found_as_written("outside patio", "with a outside pptaio")
    assert quote_found_as_written("outside patio", CHESTNUT)  # "ppatio" is read as "patio" on both sides
    # a misspelt word that is not a table word: only the quote-to-text match can find it
    text = "An Indain food restaurant on Chestnut"
    assert not quote_found_as_written("Indian food restaurant", text)
    assert quote_found("Indian food restaurant", text)
    assert quote_spans("Indian food restaurant", text) == ("Indain food restaurant",)
    # the words shown are always the applicant's, as written
    assert quote_spans("outside patio", CHESTNUT) == ("outside ppatio",)
    assert quote_spans("alcohol license", CHESTNUT) == ("alochol license",)
    assert counted_quotes(quotes([("outdoor_seating", "outside patio")]), CHESTNUT) == {
        "outdoor_seating": ("outside ppatio",)
    }


def test_a_quote_that_changes_a_number_or_a_short_word_is_not_found() -> None:
    text = "40 seats, no patio, open till 2 am"
    assert quote_found("40 seats", text)
    assert not quote_found("400 seats", text) and not quote_found("45 seats", text)
    assert not quote_found("a patio", text)  # "a" is not "no"
    assert not quote_found("open till 3 am", text)
    # a quote of words that are not in the text at all stays not found
    assert not quote_found("rooftop terrace", text)
    assert quote_spans("rooftop terrace", text) == ()


def test_the_value_is_read_from_the_applicants_words_not_from_the_models() -> None:
    """A model that "corrects" a real word into a table word states nothing: "ratio" is not "patio"."""
    text = "A restaurant with a floor area ratio of two"
    profile = {"business_type": "restaurant", "outdoor_seating": True}
    # the quote is found (one slip a word), and the applicant's words, "floor area ratio", state no outdoor area
    assert quote_found("floor area patio", text) and not quote_found_as_written("floor area patio", text)
    assert checked(
        profile, [("business_type", "A restaurant"), ("outdoor_seating", "floor area patio")], text
    ) == {"outdoor_seating": True}


# ---- the stated-facts check on the description of 2026-11-15 ---------------------------------------------------------
@pytest.mark.parametrize(
    "pairs", [AS_WRITTEN, CORRECTED], ids=["quoted as written", "quoted with the spelling put right"]
)
def test_the_chestnut_description_keeps_every_fact_it_states(pairs: list[tuple[str, str]]) -> None:
    result = check_stated(BusinessProfile.model_validate(CHESTNUT_PROFILE), quotes(pairs), CHESTNUT)
    assert result.cleared == {}
    kept = result.profile
    assert (kept.serves_alcohol, kept.seats, kept.closing_hour, kept.outdoor_seating) == (
        True,
        40,
        "02:00",
        True,
    )
    # what it does not state is still not known: what is poured, where the patio is, which story
    concept = facts.concept_facts(kept.normalized())
    assert concept.alcohol_served.missing and concept.outdoor_area.missing and concept.stories.missing
    assert (
        concept.outdoor_area_described and not concept.outdoor_not_stated and not concept.alcohol_not_stated
    )
    assert concept.seats.value == 40


def test_a_liquor_licence_misspelt_still_does_not_state_spirits() -> None:
    """ "liquor license" names the licence, not what is poured; a misspelt "lisence" must not turn it into spirits."""
    for text in ("a liquor license", "a liquor lisence", "a liqour licnese", "liquor licenses"):
        assert not value_stated("alcohol_type", "full_liquor", [text]), text
        assert value_stated("serves_alcohol", True, [text]), text
    assert value_stated("alcohol_type", "full_liquor", ["cocktials and wine"])


def test_a_misspelt_hedge_still_hedges_and_a_misspelt_negation_still_negates() -> None:
    assert not value_stated("live_entertainment", True, ["mabye live music"])
    assert not value_stated("live_entertainment", True, ["posibly live music"])
    assert value_stated("live_entertainment", True, ["live muisc on Fridays"])
    assert value_stated("entertainment_kind", "none", ["wihtout live music"])
    assert value_stated("outdoor_area", "none", ["no patoi"])


# ---- seats: how many the room seats, in the words applicants use ------------------------------------------------------
@pytest.mark.parametrize(
    "words",
    [
        "40 seats",
        "seating for 40",
        "40 people sitting",
        "40 poeple sitting",  # misspelt
        "a 40-seat room",
        "40 chairs",
        "room for 40 seated guests",
        "seats 40 people with a staff of 6",
        "can seat 40",
        "seating capacity of 40",
        "40 indoor seats",
        "40 bar stools",
    ],
)
def test_a_seat_count_in_the_applicants_words(words: str) -> None:
    assert value_stated("seats", 40, [words]), words


@pytest.mark.parametrize(
    "words",
    [
        "40",  # no unit
        "40 square feet",
        "a staff of 40 people",  # the people who work there are not the seats
        "40 employees",
        "a team of 40",
        "hiring 40 people as servers",
        "45 seats",  # another number
        "4,000 people a week walk past",  # 4000 is not 40
        # people, guests or diners with no word for sitting are not seats (review of 2026-11-15)
        "room for 40 guests",
        "40 diners at a time",
        "capacity of 40",
        "40 people",
        "fewer than 40 seats",  # a comparison is not a count
        "up to 40 seats",
        "seating for up to 40",
        "40 seats a night",  # a rate is not a count
        "40 covers",  # covers are meals served, never seats (second review of 2026-11-15)
    ],
)
def test_what_is_not_a_seat_count(words: str) -> None:
    assert not value_stated("seats", 40, [words]), words


def test_a_number_still_needs_its_own_unit() -> None:
    assert not value_stated("square_feet", 40, ["40 people sitting"])
    assert value_stated("square_feet", 1800, ["1,800 sqaure feet"])  # "sqaure" is read as "square"
    assert not value_stated("seats", 1800, ["1,800 square feet"])


# ---- the prompt, and the constants the modules share ---------------------------------------------------------------
def test_the_intake_prompt_says_a_misspelt_word_states_the_fact_and_is_quoted_as_written() -> None:
    assert (
        "A misspelt word" in prompts.MEMO_INTAKE
        and "you quote it as the applicant wrote it" in prompts.MEMO_INTAKE
    )
    # the examples are made up; the 2301 Chestnut St text is a held-out check, never an example (review #13, #19)
    for phrase in ("alochol", "ppatio", "40 people sitting", "Indian food"):
        assert phrase not in prompts.MEMO_INTAKE, phrase
    assert "A misspelt word" not in prompts.INTAKE  # the checklist's intake has no quotes


def test_the_late_close_limit_is_the_same_in_the_intake_answers_and_the_facts() -> None:
    assert intake.LATE_CLOSE_UNTIL == facts.LATE_CLOSE_UNTIL


# ---- review of 2026-11-15: a real word is never respelt ------------------------------------------------------------
# Words the review found respelt into a table word, and so read as a fact the text does not state.
REAL_WORDS_ONCE_RESPELT = [
    "mocktail",  # cocktail
    "mocktails",
    "newer",  # never
    "outdoorsy",  # outdoors
    "outsize",  # outside
    "byers",  # beers
    "chang",  # change
    "pitting",  # sitting
    "hitting",
    "witting",
    "spitting",
    "fresno",  # fresco
    "frisco",
    "coder",  # cider
    "wider",
    "winos",  # wines
    "firmer",  # former
    "someway",  # someday
    "tavernas",  # taverns
    "ramon",  # ramen
    "berger",  # burger
    "salomon",  # saloon
    "seater",  # seated
    "rever",  # never
]
_DICT = Path("/usr/share/dict")
_NO_SYSTEM_LISTS = "the system word lists (macOS /usr/share/dict) are not on this machine"


@pytest.mark.parametrize("word", REAL_WORDS_ONCE_RESPELT)
def test_a_real_word_the_review_found_respelt_stays_as_written(word: str) -> None:
    assert respell(word) == word
    assert normalise(f"a {word} here") == f"a {word} here"


@pytest.mark.skipif(
    not (_DICT / "web2").exists() or not (_DICT / "propernames").exists(), reason=_NO_SYSTEM_LISTS
)
def test_no_word_of_web2_or_propernames_is_respelt() -> None:
    changed = []
    for name in ("web2", "propernames"):
        for line in (_DICT / name).read_text(encoding="utf-8").split():
            word = line.lower()
            if respell(word) != word:
                changed.append(word)
    assert changed == []


@pytest.mark.skipif(
    not all((_DICT / n).exists() for n in ("web2", "web2a", "words", "propernames", "connectives")),
    reason=_NO_SYSTEM_LISTS,
)
def test_the_real_words_file_is_what_the_build_gives() -> None:
    """The bundled list is rebuilt from the system word lists, their inflections, the modern words and the
    committed spell-checker words, and gives exactly what is in the file. Every inflection of every listed word is
    then left as written."""
    bases = spelling.read_word_lists(spelling.SYSTEM_WORD_LISTS)
    checked = spelling.read_spellchecker_words()
    assert spelling.build_real_words(bases, checked) == sorted(NOT_MISSPELLINGS)
    listed = bases | spelling.MODERN_WORDS
    for word in listed:
        for form in spelling.inflections(word):
            if form in spelling.HEDGE_SLIPS:  # a four-letter slip of "maybe" (third pass): read as the hedge
                assert respell(form) == spelling.HEDGE_SLIPS[form], form
            elif form in listed or not _only_near_hedges(form):
                assert respell(form) == form, form
            else:  # an inflection the build made, one slip from a hedge only: read as the hedge (rule 2)
                assert respell(form) in {form, *spelling.HEDGE_WORDS}, form


def _only_near_hedges(form: str) -> bool:
    near = spelling._near_table_words().get(form)
    return bool(near) and near <= spelling.HEDGE_WORDS


def test_a_made_up_inflection_or_a_capitalised_name_next_to_a_hedge_is_read_as_the_hedge() -> None:
    """ "mayby" is an inflection the build makes from "maybe" ("-y" with the "e" dropped), "eventualy" one it makes
    from "eventual", and "Mayne" a name the spell checker accepts only capitalised: none is a word in lower case,
    so each is read as the hedge, and the quote states nothing. A real word written in lower case next to a hedge
    ("night", "eight", "layer") stays as written."""
    assert "mayby" in spelling.inflections("maybe") and "eventualy" in spelling.inflections("eventual")
    for written, hedge in [
        ("mayby", "maybe"),
        ("mayne", "maybe"),
        ("eventualy", "eventually"),
        ("hopefuly", "hopefully"),
        ("potentialy", "potentially"),
        ("possibley", "possibly"),
    ]:
        assert written not in NOT_MISSPELLINGS and respell(written) == hedge, written
    for word in ("night", "eight", "light", "layer", "water", "possible", "futures"):
        assert respell(word) == word, word
    assert not value_stated("live_entertainment", True, ["mayne live music"])
    assert not value_stated("serves_alcohol", True, ["eventualy beer and wine"])
    assert value_stated("live_entertainment", True, ["live music every night"])


# ---- second review of 2026-11-15: the macOS spell checker is a word source of the build ---------------------------
def test_the_spellchecker_file_says_how_it_was_built_and_is_folded_into_the_list() -> None:
    doc = json.loads(spelling.SPELLCHECKER_FILE.read_text(encoding="utf-8"))
    assert sorted(doc) == ["about", "words"]
    assert "NSSpellChecker" in doc["about"] and "spellchecker_accepts.swift" in doc["about"]
    words = doc["words"]
    assert words and words == sorted(set(words))
    candidates = set(spelling.spellchecker_candidates())
    for word in words:
        assert word in candidates, word  # as the spell checker accepted it: "zines", "Fresca"
        low = word.lower()
        if word.islower() or not _only_near_hedges(low):
            assert low in NOT_MISSPELLINGS and respell(low) == low, word  # folded in, so never respelt
    # the review's words that are still one slip from a table word are among them, as the review found them
    # ("cavers" and "covens" were one slip from "covers", no longer a table word)
    review = {*SPELL_CHECKER_LOWER_CASE, *SPELL_CHECKER_CAPITALISED}
    assert {w for w in review if w in candidates} <= set(words)
    assert {w for w in review if w not in candidates} == {"cavers", "covens", "Cavers", "Covens"}


def test_the_spellchecker_candidates_are_every_string_respell_could_change() -> None:
    candidates = spelling.spellchecker_candidates()
    lower = {c for c in candidates if c.islower()}
    assert candidates == [form for f in sorted(lower) for form in (f, f.capitalize())]
    assert {"zines", "Zines", "fresca", "Fresca", "ppatio", "Ppatio"} <= set(candidates)
    assert not lower & SPELLING_WORDS
    assert all(len(c) >= RESPELL_MIN_LETTERS for c in lower)
    assert SPELLING_WORDS.isdisjoint(lower)


_SWIFT = shutil.which("swift")
_NO_SPELL_CHECKER = "the macOS spell checker (NSSpellChecker, through swift) is not on this machine"


@pytest.mark.skipif(sys.platform != "darwin" or _SWIFT is None, reason=_NO_SPELL_CHECKER)
def test_the_spell_checker_still_accepts_every_committed_word() -> None:
    """Re-runs scripts/spelling/spellchecker_accepts.swift over the committed words and the review's lists (the
    full re-run of the build, every candidate, takes about a minute: `python -m app.memo.spelling`, or set
    SPELLCHECKER_FULL=1 to run it here)."""
    words = spelling.read_spellchecker_words()
    assert spelling.run_spellchecker(words) == words
    # and it tells a misspelling from a word, and a name from a word in lower case
    asked = ["zines", "ppatio", "alochol", "Fresca", "fresca", "Mayne", "mayne"]
    assert spelling.run_spellchecker(asked) == ["Fresca", "Mayne", "zines"]


@pytest.mark.skipif(
    sys.platform != "darwin" or _SWIFT is None or not os.environ.get("SPELLCHECKER_FULL"),
    reason=f"{_NO_SPELL_CHECKER}, or SPELLCHECKER_FULL is not set",
)
def test_the_spell_checker_gives_the_committed_file() -> None:
    assert spelling.run_spellchecker(spelling.spellchecker_candidates()) == spelling.read_spellchecker_words()


def test_the_modern_words_are_never_respelt() -> None:
    for word in spelling.MODERN_WORDS:
        assert respell(word) == word, word
    assert {"mocktail", "mocktails", "outdoorsy", "rooftop", "speakeasy", "gastropub", "omakase", "boba"} <= (
        spelling.MODERN_WORDS
    )


def test_inflections() -> None:
    forms = spelling.inflections
    assert {"new", "news", "newer", "newest"} <= forms("new")
    assert {"hitting", "hitter"} <= forms("hit")
    assert "wider" in forms("wide") and "outdoorsy" in forms("outdoors")
    assert {"boozy", "boozing", "boozed"} <= forms("booze")
    assert {"happier", "happiest", "happily"} <= forms("happy")


# ---- never respelt into a negation or a hedge -----------------------------------------------------------------------
def _one_slip_neighbours(word: str) -> set[str]:
    letters = "abcdefghijklmnopqrstuvwxyz"
    cuts = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    return (
        {a + b[1:] for a, b in cuts if b}
        | {a + b[1] + b[0] + b[2:] for a, b in cuts if len(b) > 1}
        | {a + c + b[1:] for a, b in cuts if b for c in letters}
        | {a + c + b for a, b in cuts for c in letters}
    ) - {word}


def test_no_word_is_respelt_into_a_negation_but_the_known_slip() -> None:
    """ "newer" was read as "never" and stated "no patio". A misspelt negation is read as it only when it is one of
    `KNOWN_SLIPS` (the one the tests of the patch need). A misspelt hedge is read as the hedge (second review of
    2026-11-15): a hedge read states nothing, a hedge lost would state the fact."""
    assert {"never", "neither", "without", "nor", "none", "not", "no"} <= spelling.NEGATION_WORDS
    assert not spelling.NEGATION_WORDS & spelling.HEDGE_WORDS
    assert spelling.HEDGE_WORDS <= SPELLING_WORDS
    assert spelling.KNOWN_SLIPS == {"wihtout": "without"}
    assert not set(spelling.KNOWN_SLIPS) & NOT_MISSPELLINGS  # not a real word
    for negation in spelling.NEGATION_WORDS & SPELLING_WORDS:
        for near in _one_slip_neighbours(negation):
            if near not in spelling.KNOWN_SLIPS:
                assert respell(near) not in spelling.NEGATION_WORDS, (near, respell(near))
    # no table word under five letters, so no negation under five letters, is ever a word a slip is respelt to
    assert all(len(w) >= RESPELL_MIN_LETTERS for w in SPELLING_WORDS)
    # into a hedge, yes: every hedge has misspellings read as it
    for hedge in spelling.HEDGE_WORDS:
        assert any(respell(near) == hedge for near in _one_slip_neighbours(hedge)), hedge


@pytest.mark.parametrize(
    ("profile", "pairs", "text", "cleared"),
    [
        (  # "newer" is not "never": the text states a patio, and no "no outdoor area"
            {"business_type": "cafe", "outdoor_area": "none"},
            [("business_type", "Cafe"), ("outdoor_area", "newer patio")],
            "Cafe with 20 seats inside and a newer patio out back",
            {"outdoor_area": "none"},
        ),
        (
            {"business_type": "bar", "entertainment_kind": "none"},
            [("business_type", "Bar"), ("entertainment_kind", "newer live music")],
            "Bar with a newer live music program on weekends",
            {"entertainment_kind": "none"},
        ),
        (
            {"business_type": "restaurant", "amends_prior_approval": False},
            [("business_type", "restaurant"), ("amends_prior_approval", "newer conditions")],
            "A restaurant. We want the newer conditions of approval to apply",
            {"amends_prior_approval": False},
        ),
    ],
)
def test_a_newer_thing_is_never_a_no(
    profile: dict[str, Any], pairs: list[tuple[str, str]], text: str, cleared: dict[str, Any]
) -> None:
    assert checked(profile, pairs, text) == cleared


# ---- the failure texts of the review: a real word states nothing it does not say ------------------------------------
@pytest.mark.parametrize(
    ("profile", "pairs", "text", "must_clear"),
    [
        (
            {
                "business_type": "cafe",
                "serves_alcohol": True,
                "alcohol_type": "full_liquor",
                "outdoor_alcohol_service": True,
            },
            [
                ("serves_alcohol", "mocktails"),
                ("alcohol_type", "mocktails"),
                ("outdoor_alcohol_service", "mocktails on the patio"),
            ],
            "Juice and mocktails on the patio, no alcohol, 20 seats",
            {"serves_alcohol", "alcohol_type", "outdoor_alcohol_service"},
        ),
        (
            {"business_type": "bar"},
            [("business_type", "mocktail")],
            "Sober hangout serving mocktail flights",
            {"business_type"},
        ),
        (
            {"business_type": "cafe", "serves_alcohol": True, "alcohol_type": "full_liquor"},
            [("business_type", "cafe"), ("serves_alcohol", "mocktails"), ("alcohol_type", "mocktails")],
            "Juice bar and cafe, alcohol-free: fresh juices and mocktails.",
            {"serves_alcohol", "alcohol_type"},
        ),
        (
            {"business_type": "cafe", "serves_alcohol": True, "alcohol_type": "full_liquor"},
            [
                ("business_type", "cafe"),
                ("serves_alcohol", "serving mocktails"),
                ("alcohol_type", "mocktails"),
            ],
            "A zero-proof cafe serving mocktails only.",
            {"serves_alcohol", "alcohol_type"},
        ),
        (
            {"business_type": "cafe", "serves_alcohol": True, "alcohol_type": "beer_wine"},
            [("business_type", "cafe"), ("serves_alcohol", "Byers"), ("alcohol_type", "Byers")],
            "Byers Coffee, a small cafe.",
            {"serves_alcohol", "alcohol_type"},
        ),
        (
            {"business_type": "restaurant", "change_of_use": True},
            [("change_of_use", "Chang from the Sunset")],
            "Noodle shop run by Chang from the Sunset.",
            {"change_of_use"},
        ),
        (
            {"business_type": "cafe", "outdoor_seating": True},
            [("business_type", "cafe"), ("outdoor_seating", "outdoorsy")],
            "Outdoorsy camping-themed cafe, all seating indoors, 30 seats",
            {"outdoor_seating"},
        ),
        (
            {"business_type": "restaurant", "outdoor_seating": True},
            [("outdoor_seating", "outsize")],
            "Burger joint with outsize portions, 25 seats",
            {"outdoor_seating"},
        ),
        (
            {"business_type": "restaurant", "outdoor_seating": True},
            [("business_type", "Thai restaurant"), ("outdoor_seating", "outsize dining room")],
            "Thai restaurant with an outsize dining room",
            {"outdoor_seating"},
        ),
        (
            {"business_type": "restaurant", "serves_alcohol": True, "alcohol_type": "beer_wine"},
            [("serves_alcohol", "wider"), ("alcohol_type", "wider")],
            "Taqueria, want a wider dining room",
            {"serves_alcohol", "alcohol_type"},
        ),
        (
            {"business_type": "restaurant", "serves_alcohol": True},
            [("serves_alcohol", "winos")],
            "Soup kitchen serving winos and anyone in need",
            {"serves_alcohol"},
        ),
        (
            {"business_type": "cafe", "serves_alcohol": True},
            [("serves_alcohol", "every coder")],
            "Coffee shop for every coder in SoMa",
            {"serves_alcohol"},
        ),
        (
            {"business_type": "restaurant", "outdoor_seating": True},
            [("outdoor_seating", "al Fresno")],
            "Mexican restaurant, tacos al Fresno style",
            {"outdoor_seating"},
        ),
        (
            {"business_type": "bar", "seats": 12},
            [("seats", "12 people hitting")],
            "Batting cage bar with 12 people hitting at once",
            {"seats"},
        ),
        (  # a name in no word list, capitalised mid-sentence: never respelt, even at the start of a quote
            {"business_type": "cafe", "outdoor_seating": True},
            [("business_type", "Cafe"), ("outdoor_seating", "Patoi Brown")],
            "Cafe owned by Patoi Brown, seats 20",
            {"outdoor_seating"},
        ),
    ],
)
def test_a_real_word_or_a_name_states_no_fact(
    profile: dict[str, Any], pairs: list[tuple[str, str]], text: str, must_clear: set[str]
) -> None:
    cleared = checked(profile, pairs, text)
    assert must_clear <= set(cleared), cleared


def test_a_capitalised_word_is_a_name_and_is_never_respelt() -> None:
    assert normalise("Owned by Alochol Smith") == "owned by alochol smith"
    assert normalise("Owned by ALOCHOL SMITH") == "owned by alochol smith"
    # second review of 2026-11-15: the first word of a sentence or a line is not respelt either; only a word
    # written all in lower case is
    assert (
        normalise("Alochol license. Outsdie ppatio\nPatoi too") == "alochol license outsdie patio patoi too"
    )
    assert normalise("an alochol license") == "an alcohol license"
    assert not value_stated("existing_use_stated", "other", ["a firmer floor"])  # "firmer" is not "former"


# ---- review of 2026-11-15: a misspelt closing word keeps the closing time -------------------------------------------
@pytest.mark.parametrize(
    ("field", "value", "words"),
    [
        ("closing_hour", "02:00", "open unitl 2 am"),
        ("closing_hour", "00:00", "open until midnigt"),
        ("closing_hour", "00:00", "closes at midnigt"),
        ("closing_hour", "02:00", "open thorugh 2 am"),
        ("closing_hour", "01:00", "clsoing at 1 am"),
        ("closes_after_midnight", True, "open thorugh 2 am"),
        ("closes_after_midnight", True, "open unitl 2 am"),
        ("closes_after_2am", True, "open unitl 3 am"),
    ],
)
def test_a_misspelt_closing_word_keeps_the_closing_time(field: str, value: Any, words: str) -> None:
    assert value_stated(field, value, [words]), words


def test_a_misspelt_closing_word_does_not_make_an_opening_time_a_closing_time() -> None:
    assert not value_stated("closing_hour", "05:30", ["open 5:30 a.m. unitl 3 p.m."])
    assert value_stated("closing_hour", "15:00", ["open 5:30 a.m. unitl 3 p.m."])


# ---- review of 2026-11-15: a slip from a singular and its plural ----------------------------------------------------
@pytest.mark.parametrize(
    ("written", "meant"), [("pation", "patio"), ("gardenn", "garden"), ("licensse", "license")]
)
def test_a_word_one_slip_from_a_word_and_its_plural_is_read_as_the_word(written: str, meant: str) -> None:
    assert respell(written) == meant


@pytest.mark.parametrize(
    ("field", "value", "words"),
    [
        ("outdoor_area", "rear_or_side", "back pation"),
        ("outdoor_seating", True, "back pation"),
        ("outdoor_area", "rear_or_side", "back gardenn"),
    ],
)
def test_a_patio_misspelt_next_to_its_plural_is_still_a_patio(field: str, value: Any, words: str) -> None:
    assert value_stated(field, value, [words])


# ---- review of 2026-11-15: seats are seated places, not people ------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "words"),
    [
        (300, "we expect 300 customers a day"),
        (7, "Cafe open 7 days a week for our customers"),
        (50, "Small cafe for fewer than 50 people"),
        (50, "for fewer than 50 people"),
        (50, "more than 50 people"),
        (80, "80 people standing, no seats"),
        (100, "100 people standing"),
        (100, "room for 100 people standing"),
        (40, "a staff of 40"),
        (45, "we will employ 45 people"),
        (60, "seating for 30 and a staff of 60"),
        (3, "3 diners in the neighborhood already"),
        (200, "private events for up to 200 guests"),
        (120, "a capacity of 120"),
        (150, "capacity of 150 standing"),
        (2, "serving customers until 2 am"),
        (500, "500 people a night"),
        (4000, "4,000 customers a month"),
        (200, "serve 200 customers a day"),
        (500, "expect 500 guests a week"),
        (50, "fewer than 50 seats"),
        (200, "200 covers a night"),
        (12, "12 people hitting at once"),
    ],
)
def test_a_count_of_people_that_is_not_seated_is_not_a_seat_count(value: int, words: str) -> None:
    assert not value_stated("seats", value, [words]), words


@pytest.mark.parametrize(
    ("value", "words"),
    [
        (40, "40 people sitting"),
        (40, "40 seats"),
        (40, "seating for 40"),
        (40, "room for 40 seated guests"),
        (30, "seating for 30 and a staff of 60"),
        (40, "40 guests seated"),
    ],
)
def test_a_seated_count_is_a_seat_count(value: int, words: str) -> None:
    assert value_stated("seats", value, [words]), words


@pytest.mark.parametrize(
    ("text", "quote", "seats"),
    [
        ("Taqueria in the Mission, we expect 300 customers a day.", "300 customers a day", 300),
        (
            "Small restaurant in a former retail shop, a room for fewer than 50 people",
            "for fewer than 50 people",
            50,
        ),
        ("Bar for 80 people standing, no seats", "80 people standing", 80),
        ("Cafe with seating for 30 and a staff of 60", "seating for 30 and a staff of 60", 60),
        ("Restaurant, we will employ 45 people", "employ 45 people", 45),
    ],
)
def test_the_check_clears_a_seat_count_the_text_does_not_give(text: str, quote: str, seats: int) -> None:
    assert (
        checked({"business_type": "restaurant", "seats": seats}, [("seats", quote)], text).get("seats")
        == seats
    )


# ---- the label of the change ------------------------------------------------------------------------------------
def test_the_spelling_change_is_labelled_with_its_release() -> None:
    from app.memo import stated

    for module in (spelling, stated):
        source = Path(module.__file__ or "").read_text(encoding="utf-8")
        assert "decision of 2026-11-15" not in source, module.__name__
        assert "change of 2026-11-15, approved with the release of 2026-11-16" in source, module.__name__


# ---- second review of 2026-11-15 -----------------------------------------------------------------------------------
# 1. Only a word the text writes all in lower case is respelt: a capitalised word, wherever it is, and a word with a
# letter that is not plain ASCII are never respelt.
@pytest.mark.parametrize(
    ("text", "quote"),
    [
        ("Patino Family Kitchen. Mexican food, 30 seats, all indoors.", "Patino"),
        ("Patino Family Kitchen. Mexican food, 30 seats, all indoors.", "patino family kitchen"),
        ("Patiño Family Kitchen. Mexican food, 30 seats, all indoors.", "Patiño"),
        # the model dropped the accent
        ("Patiño Family Kitchen. Mexican food, 30 seats, all indoors.", "Patino"),
        ("Patiño Family Kitchen. Mexican food, 30 seats, all indoors.", "patino family kitchen"),
        ("Mexican food at patiño's, 30 seats, all indoors.", "patiño"),  # an accent in lower case
        ("Mexican food at patiño's, 30 seats, all indoors.", "patino"),
        ("Mexican food at patiño's, 30 seats, all indoors.", "patiño"),  # the accent as its own mark
        ("Food by chef Ppatio Ruiz.\nPpatio cooks", "Ppatio"),  # the first word of a line
    ],
)
def test_a_name_at_the_start_of_a_sentence_or_with_an_accent_states_no_outdoor_area(
    text: str, quote: str
) -> None:
    profile = {"business_type": "restaurant", "outdoor_seating": True}
    assert checked(profile, [("outdoor_seating", quote)], text).get("outdoor_seating") is True


def test_only_a_word_written_all_in_lower_case_is_respelt() -> None:
    assert normalise("Ppatio and ppatio") == "ppatio and patio"
    assert (
        normalise("Alochol license. Outsdie ppatio\nPatoi too") == "alochol license outsdie patio patoi too"
    )
    assert normalise("ALOCHOL; alochol") == "alochol alcohol"
    assert normalise("patiño, patiño, Patiño") == "patino patino patino"
    assert normalise("a café patioé") == "a cafe patioe"


# 2. Real words the macOS spell checker knows that no word list of the build had: never respelt (the review's lists,
# lower case and capitalised, from NSSpellChecker over every string `respell` changed).
SPELL_CHECKER_LOWER_CASE = """
bandh basemen beeps bingers cavers concerti couvert covens decls decos drecks flors gardena lavern mobil netback
patin patins pingers ragmen seabed seato shitting shorefront shorefronts sidewall sidewalls stats storefys swops
terrae trattorie widnes zines zingers
""".split()  # noqa: SIM905 (a list of words, kept as text so it reads by line)
SPELL_CHECKER_CAPITALISED = """
Arden Ardens Baers Bandh Banos Basel Basels Basemen Beeps Beerse Berge Biggera Bingers Boole Cabarete Caterina
Cather Catina Cavers Chaims Changi Cloke Concerta Concerti Couvert Covens Danae Danke Danne Dante Darden Dardens
Decls Decos Drecks Emobile Flors Fresca Gardel Gardena Gellar Horus Kamen Karger Kartini Keating Keats Landry Lavern
Laverns Lebel Leven Maraini Markel Markey Martina Martinas Martine Martinus Melato Merced Meroe Merwe Mgallery Mitel
Mobil Mobils Mosel Mosels Musil Nespresso Netback Pagel Palio Patin Patins Pearsons Piersons Pingers Ragmen Rajen
Riestaurants Santina Seabed Seato Seays Shitting Shons Shorefront Shorefronts Sidewall Sidewalls Sittang Sixto Stats
Storme Stowe Swops Systemj Taroom Terrae Thord Trattorie Varden Widnes Zines Zingers
""".split()  # noqa: SIM905 (a list of words, kept as text so it reads by line)


@pytest.mark.parametrize("word", [*SPELL_CHECKER_LOWER_CASE, *SPELL_CHECKER_CAPITALISED])
def test_a_word_the_spell_checker_knows_is_left_as_written(word: str) -> None:
    low = word.lower()
    assert respell(low) == low
    assert normalise(f"a {low} here") == f"a {low} here"


# 3. A misspelt hedge still hedges (a hedge lost would state the fact); a word is still never read as a "no".
@pytest.mark.parametrize(
    ("field", "value", "words"),
    [
        ("live_entertainment", True, "maybee live music"),
        ("outdoor_seating", True, "mayby a patio later on"),
        ("outdoor_area", "rear_or_side", "mayby a back patio"),
        ("serves_alcohol", True, "evenutally beer and wine"),
        ("alcohol_type", "beer_wine", "evenutally beer and wine"),
        ("live_entertainment", True, "posibly live music"),
        ("live_entertainment", True, "mabye live music"),
        ("live_entertainment", True, "hopefuly live music"),
        ("live_entertainment", True, "hopefully live music"),
    ],
)
def test_a_misspelt_hedge_states_no_fact(field: str, value: Any, words: str) -> None:
    assert not value_stated(field, value, [words]), words


def test_a_misspelt_hedge_clears_the_fact_in_the_check() -> None:
    text = "Wine bar, evenutally beer and wine on the patio. maybee live music, mayby a patio later on"
    profile = {
        "business_type": "bar",
        "live_entertainment": True,
        "outdoor_seating": True,
        "outdoor_alcohol_service": True,
    }
    pairs = [
        ("business_type", "Wine bar"),
        ("live_entertainment", "maybee live music"),
        ("outdoor_seating", "mayby a patio later on"),
        ("outdoor_alcohol_service", "evenutally beer and wine on the patio"),
    ]
    assert set(checked(profile, pairs, text)) == {
        "live_entertainment",
        "outdoor_seating",
        "outdoor_alcohol_service",
    }


@pytest.mark.parametrize(
    ("written", "meant"), [("maybee", "maybe"), ("mayby", "maybe"), ("evenutally", "eventually")]
)
def test_a_misspelt_hedge_is_read_as_the_hedge(written: str, meant: str) -> None:
    assert respell(written) == meant


# 4-6. Covers, "sit for" and counts a day or for a time are never seat counts.
@pytest.mark.parametrize(
    ("value", "words"),
    [
        (200, "200 covers on Saturdays"),
        (150, "150 covers per dinner service"),
        (150, "150 covers at dinner"),
        (40, "40 covers"),
        (2, "Cafe where guests can sit for 2 hours."),
        (2, "guests sit for 2 hours"),
        (30, "the room sits for 30"),
        (30, "the room sits 30"),
        (300, "we can seat 300 people a day"),
        (300, "seating 300 customers a day"),
        (200, "we seat 200 guests a night"),
        (90, "seating for 90 minutes per table"),
        (6, "patio seating for 6 months a year"),
        (7, "indoor seating 7 days a week"),
        (40, "40 seats per sitting"),
        (2, "seating for 2 hours"),
        (100, "100 seats daily"),
        (60, "seats 60 diners each evening"),
    ],
)
def test_covers_sitting_and_counts_over_time_are_not_seat_counts(value: int, words: str) -> None:
    assert not value_stated("seats", value, [words]), words


@pytest.mark.parametrize(
    ("value", "words"),
    [
        (40, "40 seats"),
        (40, "seating for 40"),
        (40, "40 people sitting with a outside ppatio"),
        (40, "a 40-seat full service restaurant"),
        (40, "seats 40 people with a staff of 6"),
        (30, "seating for 30 and a staff of 60"),
        (40, "40 seats and a patio"),
    ],
)
def test_a_seat_count_next_to_no_time_word_is_still_a_seat_count(value: int, words: str) -> None:
    assert value_stated("seats", value, [words]), words


def test_covers_are_no_longer_a_table_word() -> None:
    assert "covers" not in SPELLING_WORDS


# ---- third pass of the review of 2026-11-15 ------------------------------------------------------------------------
# A word read as a hedge is read as the hedge whatever its case: a hedge can only make a fact "not stated".
@pytest.mark.parametrize(
    ("text", "field", "value", "quote"),
    [
        ("Wine bar. Posibly live music.", "live_entertainment", True, "Posibly live music"),
        ("Wine bar. Mabye live music.", "live_entertainment", True, "Mabye live music"),
        ("Wine bar. Maybee live music.", "live_entertainment", True, "Maybee live music"),
        ("Mexican food. Mayby a back patio.", "outdoor_seating", True, "Mayby a back patio"),
        ("Taqueria. Evenutally beer and wine.", "serves_alcohol", True, "Evenutally beer and wine"),
        ("Taqueria. EVENUTALLY BEER AND WINE.", "serves_alcohol", True, "EVENUTALLY BEER AND WINE"),
        ("wine bar, mybe live music", "live_entertainment", True, "mybe live music"),
        (
            "wine bar, we will probably have live music",
            "live_entertainment",
            True,
            "probably have live music",
        ),
        ("wine bar, we may have live music", "live_entertainment", True, "may have live music"),
        ("wine bar, unsure about live music", "live_entertainment", True, "unsure about live music"),
        ("cafe, hoping to add a patio", "outdoor_seating", True, "hoping to add a patio"),
    ],
)
def test_a_hedge_in_any_case_or_spelling_states_nothing(
    text: str, field: str, value: object, quote: str
) -> None:
    profile = {"business_type": "restaurant", field: value}
    assert checked(profile, [(field, quote)], text).get(field) == value


# A word the text writes with a capital or an accent anywhere is a name everywhere in it.
@pytest.mark.parametrize(
    ("text", "quote"),
    [
        ("Patino Family Kitchen. we cook patino family recipes, all indoors.", "patino family recipes"),
        ("Mexican food at Patiño's. patino's is all indoors.", "patino's"),
    ],
)
def test_a_lower_case_copy_of_a_name_is_not_respelt(text: str, quote: str) -> None:
    profile = {"business_type": "restaurant", "outdoor_seating": True}
    assert checked(profile, [("outdoor_seating", quote)], text).get("outdoor_seating") is True


# A count of people over time, a count per table and a clock time are never the room's seat count; a clause ends
# at a comma, so a seat count before it stands.
@pytest.mark.parametrize(
    ("quote", "seats"),
    [
        ("we seat 300 people throughout the day", set()),
        ("we seat 300 people over the course of a day", set()),
        ("we seat 300 hungry lunch customers a day", set()),
        ("seats 1000 guests per annum", set()),
        ("seats 4 per table", set()),
        ("booths seat 6 people per booth", set()),
        ("tables seat 4 each", set()),
        ("first seating 5:30 pm, second seating 8 pm", set()),
        ("seating 6 pm to 10 pm", set()),
        ("40 seats, open 7 days a week", {40}),
        ("seating for 40, open late", {40}),
        ("seating capacity of 40", {40}),
        ("40 indoor seats and 12 patio seats", {40, 12}),
        ("40 people sitting with a outside ppatio", {40}),
    ],
)
def test_seat_counts_by_clause(quote: str, seats: set[int]) -> None:
    from app.memo.stated import seat_counts_in

    assert seat_counts_in(quote) == seats
