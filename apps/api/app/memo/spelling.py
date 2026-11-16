"""Spelling slips in the applicant's own words. No model call, no clock, and no I/O beyond one bundled data file.

The rules are the change of 2026-11-15, approved with the release of 2026-11-16.

The stated-facts check (app.memo.stated) matches the applicant's words against fixed tables of words ("alcohol",
"patio", "ground floor"). A description typed in a hurry misspells them ("alochol license", "outside ppatio"), and
the intake model, asked to quote the applicant's words, often quotes them with the spelling put right ("outside
patio"). Before this module both lost a fact the applicant had stated: the misspelt word matched no table, and the
corrected quote was not found in the text. In the report of 2026-11-15 for 2301 Chestnut St the description said
"40 people sitting with a outside ppatio" and the report said it "does not state whether there will be an outdoor
area".

THE RULES, all narrow, and none lets a fact in that the applicant's words do not state. When in doubt a word is
left as written, so the fact it might state is "not stated", never assumed.

1. `respell(word)`: a word of five or more letters that is not a word of the tables, not a real word
   (`NOT_MISSPELLINGS`), and exactly one slip from a word of `SPELLING_WORDS` is read as that word. One slip
   (`one_slip`) is one letter dropped, added or changed, or two neighbouring letters swapped. A word two slips
   away is left as written, and so is a word one slip from two different table words: the rules never pick
   between two readings. A word one slip from a table word and its plural ("pation": "patio" and "patios") is
   read as the singular, since both state the same thing (`_lemma`).
2. Never into a negation (`NEGATION_WORDS`: "never", "without", "neither", ...). A word read as "never" states a
   "no" ("newer patio" read as "never patio"), so no word is respelt into one. The only exception is
   `KNOWN_SLIPS`, the one misspelling the tests of the patch need ("wihtout"). A word IS respelt into a hedge
   ("maybee", "mayby", "evenutally", "hopefuly"): a hedge read makes the quote state nothing
   (`app.memo.stated.HEDGED_FIELDS`), so the fact becomes "not stated", while a hedge lost would let "maybee live
   music" state live music (second review of 2026-11-15).
3. Only a word the text writes all in plain lower case may be respelt (`may_respell`, `respell_text`), wherever it
   is. A word with any capital letter ("Patino Family Kitchen", "run by Chang", "ALOCHOL"), at the start of a
   sentence or not, and a word with any letter that is not plain ASCII ("Patiño", "patiño") are left as written:
   either may be a name, and "Patiño" without its accent would read as "patio". The cost: a misspelt first word
   of a sentence ("Alochol license.") gets no spelling help, and neither does a description typed in title case
   or capitals. `app.memo.stated` also keeps every such word of the text as written wherever a quote writes it in
   lower case, and so is a lower-case copy of it elsewhere in the text (`names_in`). One exception, as rule 2 says
   why: a word read as a hedge is read as the hedge whatever its case ("Mabye live music." states nothing).
4. `same_word(a, b)`: whether a word of a quote and a word of the text are the same word. Equal, or equal once
   respelt, or four or more letters each and one slip apart. Numbers and short words must be equal: "40" is never
   "400", and "no" is never "on". `app.memo.stated.quote_found` uses it only when the quote is not found as
   written, so a quote the model spelt correctly still points at the applicant's misspelt words, and the words
   then read for the value are the applicant's, cut from the text (`quote_spans`), not the model's.

The intake model still has to read the fact and quote the words: this module only widens what those quoted words
are allowed to state, by one slip. It never adds a fact on its own.

HOW `NOT_MISSPELLINGS` IS BUILT (review of 2026-11-15; the first list, the words in both Webster's Second and
GCIDE, left out hundreds of real words, and "mocktails" was read as "cocktails", "newer" as "never" and "outsize"
as "outside"). `build_real_words` takes the UNION of every word list on the Mac it was built on
(`SYSTEM_WORD_LISTS`: /usr/share/dict web2, web2a, words, propernames and connectives), the hand-kept modern words
and names (`MODERN_WORDS`: "mocktail", "outdoorsy", "omakase", "Byers") and the table words themselves; adds every
inflection of each (`inflections`: -s, -es, -ed, -ing, -er, -est, -y, -ly, -ier, -iest, with a final "e" dropped,
a "y" made "i" and a last consonant doubled); and keeps those of five or more letters one slip from a table word.
THE SPELL CHECKER is a word source too (second review of 2026-11-15: web2 is of 1934, and "zines", "sidewalls",
"stats", "seabed", "fresca" were respelt). `spellchecker_candidates` is every string of five or more letters one
slip from a table word, in lower case and capitalised; `run_spellchecker` asks the macOS spell checker
(NSSpellChecker, US English, words the user taught it left out) about each, through
scripts/spelling/spellchecker_accepts.swift, and keeps those it accepts, as it accepted them. They are written to
data/spelling_spellchecker_words.json (`SPELLCHECKER_FILE`) and folded into the list in lower case. One exception
keeps rule 2 safe: a string one slip from a hedge and from no other table word is listed only when it is a word
written in lower case (of a word list or `MODERN_WORDS`, or accepted by the spell checker in lower case), never
when it is only an inflection the build made ("mayby" from "maybe") or a name accepted only capitalised ("Mayne"),
so "mayby a patio" still hedges.

Rebuild both files with `python -m app.memo.spelling` (from apps/api, on a Mac with the Swift toolchain) whenever
`SPELLING_WORDS` or `MODERN_WORDS` changes; `python -m app.memo.spelling --no-spellchecker` rebuilds the list from
the committed spell-checker file, on a Mac without Swift. At run time and in the tests only the two committed files
are read: a test rebuilds the list from the system word lists and the committed spell-checker file and checks it
equals the bundled file, another re-runs the spell checker (skipped where there is none) and checks it gives the
committed file, and another runs every word of web2 and propernames through `respell` and checks none is changed.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unicodedata
from collections.abc import Collection, Iterable
from functools import lru_cache
from pathlib import Path

# The shortest word that may be respelt.
RESPELL_MIN_LETTERS = 5
# The shortest word of a quote that may differ by one slip from the word of the text it points at.
SAME_WORD_MIN_LETTERS = 4

# The words of the stated-facts tables (app.memo.stated: VALUE_WORDS, EXISTING_USE_WORDS, the seat units, the
# alcohol, outdoor, entertainment, hedge and negation words) of five or more letters, in the forms applicants
# write. A word here is never respelt, and a misspelt word is respelt only to one of these.
SPELLING_WORDS: frozenset[str] = frozenset(
    """
    alcohol alcoholic beers wines liquor liquors spirits cocktail cocktails tavern taverns taproom taprooms brewery
    breweries brewpub brewpubs cider ciders drinks booze whiskey whisky mezcal tequila vodka martini martinis
    distilled license licence licenses licences licensed
    outdoor outdoors outside patio patios terrace terraces sidewalk sidewalks parklet parklets fresco garden gardens
    courtyard courtyards rooftop decks parking backyard setback indoor indoors
    entertainment music musician musicians performance performances performer performers bands karaoke dance dancing
    concert concerts comedy singer singers cabaret amplified amplification speaker speakers sound system
    nightclub nightclubs nighttime
    maybe might possibly perhaps eventually someday potentially future later undecided hopefully
    restaurant restaurants eatery eateries diner diners bistro brasserie trattoria osteria taqueria pizzeria
    steakhouse cantina izakaya noodle ramen burger saloon lounge speakeasy cafes coffee bakery bakeries espresso
    patisserie donut donuts doughnut doughnuts gelato creamery dessert desserts bagel bagels creperie juice truck
    trucks trailer trailers mobile vending hotel hotels motel motels hostel hostels lodging cater catering caterer
    enlarge enlarged enlarging expand expanded expanding expansion addition larger bigger extend extended extending
    increase increased combine combined combining intensify intensified longer hours merge merged merging
    consolidate consolidated storefront storefronts
    condition conditions amend amended amending modify modified approval approvals permission conditional
    entitlement previous previously earlier existing
    ground floor floors level levels story storey stories storeys street first second third fourth fifth sixth
    basement basements cellar cellars underground
    limited place front change changed changes convert converted converting conversion repurpose repurposed
    construction building
    retail store stores shops boutique gallery market laundromat laundromats laundry laundries cleaners vacant empty
    unoccupied unused shuttered closed former formerly occupied vacated replace replaced replacing
    seats seating seated sitting chairs guests patrons people persons capacity square
    midnight until close closes closing through without never neither
    """.split()  # noqa: SIM905 (a table of words, kept as text so it reads and diffs by line)
)

# The negations (rule 2). No word is ever respelt into one of these, but the misspelling of `KNOWN_SLIPS`. (The
# words under five letters are never a word a slip is respelt to; they are here so the rule reads whole.)
NEGATION_WORDS: frozenset[str] = frozenset(
    """
    without never neither nor none not no
    """.split()  # noqa: SIM905 (a table of words, kept as text so it reads and diffs by line)
)
# The hedges of `SPELLING_WORDS`. A word may be respelt into one (rule 2): a hedge read states nothing.
HEDGE_WORDS: frozenset[str] = frozenset(
    """
    maybe might possibly perhaps eventually someday potentially future later undecided hopefully
    """.split()  # noqa: SIM905 (a table of words, kept as text so it reads and diffs by line)
)
# The only misspelling read as a negation: the one the tests of the patch of 2026-11-15 need.
KNOWN_SLIPS: dict[str, str] = {"wihtout": "without"}
# Four-letter slips of "maybe" (third pass of the review of 2026-11-15): too short for rule 1, and read as the hedge,
# which can only make a fact "not stated" ("mybe live music" states no live music). None is an English word.
HEDGE_SLIPS: dict[str, str] = {"mybe": "maybe", "mabe": "maybe", "maby": "maybe", "mayb": "maybe"}

# Real words no word list of 1934 has, and names: added to the system word lists when `NOT_MISSPELLINGS` is built,
# so none is ever respelt. Only those one slip from a table word end up in the list, so the list can be broad.
MODERN_WORDS: frozenset[str] = frozenset(
    """
    mocktail mocktails mocktailing zeroproof nonalcoholic alcoholfree booze boozy boozer boozers sober sobriety
    seltzer seltzers spritz spritzes negroni negronis kombucha kombuchas cidery cideries meadery meaderies winery
    wineries microbrewery microbreweries nanobrewery brewpub brewpubs taproom taprooms gastropub gastropubs
    speakeasy speakeasies tiki wino winos vino vinos sommelier somm natural sake soju makgeolli baijiu shochu
    highball highballs aperitivo aperitif amaro mixology mixologist mixologists bartending barback barbacks
    outdoorsy indoorsy rooftop rooftops streetery streeteries parklet parklets alfresco popup popups pop pops
    foodhall foodhalls ghostkitchen commissary takeout takeaway takeaways delivery doordash ubereats grubhub
    omakase boba poke pokes taqueria taquerias taco tacos burrito burritos birria pupusa pupusas pupuseria
    pho banh ramen ramens udon soba izakaya izakayas yakitori dimsum dumpling dumplings bao baos hotpot shabu
    sushi sashimi bento teriyaki tempura katsu matcha chai latte lattes cappuccino cappuccinos espresso espressos
    barista baristas cafe cafes coffeehouse coffeehouses coffeeshop bistro bistros brasserie brasseries trattoria
    trattorias osteria osterias enoteca pizzeria pizzerias pizzas calzone panini paninis gelateria gelato gelatos
    creperie creperies boulangerie patisserie patisseries bagelry bakeshop donut donuts doughnut doughnuts
    cupcake cupcakes cupcakery brunch brunches foodie foodies vegan vegans vegetarian glutenfree keto
    burger burgers burgery smashburger steakhouse steakhouses cantina cantinas tapas tapasbar mezze meze taverna
    tavernas gyro gyros shawarma falafel kebab kebabs halal kosher deli delis bodega bodegas
    karaoke karaokes livestream livestreams dj djs emcee emcees deejay deejays openmic rave raves edm
    nightlife nightclubbing clubbing clubber clubbers lounge lounges loungey speakerphone soundbar soundbars
    soundproof soundproofed soundproofing subwoofer subwoofers amp amps
    online offline email emails website websites app apps wifi smartphone selfie selfies covid pandemic
    sitdown walkup fastcasual counterservice ventless hood hoods hvac signage eatery eateries cookhouse
    upzoning rezoning rezone rezoned permitting permittee permittees entitlements setback setbacks
    byers chang changs fresno frisco ramon salomon berger gardner garner seaton dinah dina liquori lisa
    sitton sutton sutter barr barrs beyer beyers bayers wein weiner weiss lounsbury storey storeys patton
    mission sunset castro noe soma dogpatch bayview excelsior richmond marina nob tenderloin presidio haight
    """.split()  # noqa: SIM905 (a table of words, kept as text so it reads and diffs by line)
)

# The word lists `NOT_MISSPELLINGS` is built from (macOS /usr/share/dict; see the module docstring).
SYSTEM_WORD_LISTS: tuple[Path, ...] = tuple(
    Path("/usr/share/dict") / name for name in ("web2", "web2a", "words", "propernames", "connectives")
)

# Real words one slip from a word of `SPELLING_WORDS` (see the module docstring for how the list is built), in
# the bundled file data/spelling_real_words.json. Never respelt: "ratio" stays "ratio".
_REAL_WORDS_FILE = Path(__file__).parent / "data" / "spelling_real_words.json"
NOT_MISSPELLINGS: frozenset[str] = frozenset(
    json.loads(_REAL_WORDS_FILE.read_text(encoding="utf-8"))["words"]
)
# What the macOS spell checker accepted when the list was last built (see the module docstring): read only by the
# build and its tests, never at run time.
SPELLCHECKER_FILE = Path(__file__).parent / "data" / "spelling_spellchecker_words.json"
# The helper that asks the spell checker (apps/api/app/memo/spelling.py -> the repository root).
SPELLCHECKER_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "spelling" / "spellchecker_accepts.swift"
)

_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _letters(word: str) -> bool:
    return word.isascii() and word.isalpha()


def slips(a: str, b: str, limit: int) -> int:
    """How many slips turn `a` into `b`, counted up to `limit` + 1 (a result above `limit` only says "more"). One
    slip is one letter dropped, added or changed, or two neighbouring letters swapped (the optimal string alignment
    distance)."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous2: list[int] = []
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            cost = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cost = min(cost, previous2[j - 2] + 1)
            current.append(cost)
        if min(current) > limit:
            return limit + 1
        previous2, previous = previous, current
    return min(previous[-1], limit + 1)


def one_slip(a: str, b: str) -> bool:
    """`a` and `b` differ by exactly one slip."""
    return slips(a, b, 1) == 1


@lru_cache(maxsize=1)
def _near_table_words() -> dict[str, frozenset[str]]:
    """Every string of letters one slip from a word of `SPELLING_WORDS`, with the table words it is one slip from.
    The same as testing `one_slip` against every table word, done once."""
    near: dict[str, set[str]] = {}
    for word in SPELLING_WORDS:
        cuts = [(word[:i], word[i:]) for i in range(len(word) + 1)]
        forms = {a + b[1:] for a, b in cuts if b}
        forms |= {a + b[1] + b[0] + b[2:] for a, b in cuts if len(b) > 1}
        forms |= {a + c + b[1:] for a, b in cuts if b for c in _LETTERS}
        forms |= {a + c + b for a, b in cuts for c in _LETTERS}
        for form in forms - {word}:
            near.setdefault(form, set()).add(word)
    return {form: frozenset(words) for form, words in near.items()}


_LEMMA_WORDS = frozenset(w.replace("licence", "license") for w in SPELLING_WORDS)


def _lemma(word: str) -> str:
    """The singular of a table word, licence and license read as one ("patios" -> "patio")."""
    word = word.replace("licence", "license")
    for end, base in (("ies", "y"), ("es", ""), ("s", "")):
        stem = word[: -len(end)] + base
        if word.endswith(end) and stem in _LEMMA_WORDS:
            return stem
    return word


@lru_cache(maxsize=4096)
def respell(word: str) -> str:
    """Rules 1 and 2 of the module docstring: the word of `SPELLING_WORDS` a misspelt word means, or the word as
    written. `word` is lower case; whether it may be respelt at all (rule 3) is for `respell_text`."""
    if word in KNOWN_SLIPS:
        return KNOWN_SLIPS[word]
    if word in HEDGE_SLIPS:
        return HEDGE_SLIPS[word]
    if (
        len(word) < RESPELL_MIN_LETTERS
        or not _letters(word)
        or word in SPELLING_WORDS
        or word in NOT_MISSPELLINGS
    ):
        return word
    found = _near_table_words().get(word, frozenset())
    if not found or found & NEGATION_WORDS:
        return word  # no table word, or a negation among them: never read as a "no"
    if len({_lemma(c) for c in found}) > 1:
        return word  # two different words: never pick between two readings
    return min(found, key=lambda c: (len(c), c))


# A word as `respell_text` reads it: a run of letters and digits of any script, with any accent written as a mark
# of its own ("n" + U+0303) kept inside the word, so "patiño" is one word, never "patin" and "o".
COMBINING_MARKS = "̀-ͯ᪰-᫿᷀-᷿⃐-⃿︠-︯"
WORD = re.compile(rf"(?:[^\W_]|[{COMBINING_MARKS}])+")


def plain(text: str) -> str:
    """Accents dropped ("Patiño" -> "Patino"), curly quotes made plain; the case kept."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.replace("’", "'").replace("‘", "'")


def may_respell(word: str) -> bool:
    """Rule 3 of the module docstring: a word may be respelt only when it is written all in plain lower-case
    letters. A capital anywhere in it, a digit, or a letter that is not plain ASCII ("ñ", "é"), and it stays as
    written."""
    return word.isascii() and word.isalpha() and word.islower()


def respell_text(text: str, names: Collection[str] = ()) -> str:
    """`text` in lower case with accents dropped (`plain`), every word that may be respelt (rule 3 of the module
    docstring, `may_respell`) respelt, everything else as written. A word of `names` is never respelt."""
    out: list[str] = []
    last = 0
    for m in WORD.finditer(text):
        word = m.group()
        low = plain(word).lower()
        read = respell(low)
        if not (read in HEDGE_WORDS or (may_respell(word) and low not in names)):
            read = (
                low  # rule 3: a capital, an accent or a name is left as written, unless it is read as a hedge
            )
        out += [plain(text[last : m.start()]).lower(), read]
        last = m.end()
    out.append(plain(text[last:]).lower())
    return "".join(out)


def names_in(text: str) -> frozenset[str]:
    """The words `text` writes, anywhere, with a capital or with a letter that is not plain ASCII, as
    `respell_text` gives them (lower case, accents dropped): names (rule 3). Neither a quote that writes one in
    lower case ("patino" for the text's "Patiño") nor a lower-case copy of it elsewhere in the text ("Patino Family
    Kitchen. we cook patino family recipes") is respelt (third pass of the review of 2026-11-15)."""
    named: set[str] = set()
    for m in WORD.finditer(text):
        word = m.group()
        if not word.isascii() or any(c.isupper() for c in word):
            named.add(plain(word).lower())
    return frozenset(named)


def same_word(a: str, b: str) -> bool:
    """Rule 4 of the module docstring: a word of a quote and a word of the text are the same word. Both lower
    case."""
    if a == b:
        return True
    if not (_letters(a) and _letters(b)):
        return False  # a number, or a word with a digit in it, must be equal
    if respell(a) == respell(b):
        return True
    return min(len(a), len(b)) >= SAME_WORD_MIN_LETTERS and one_slip(a, b)


# ---- building NOT_MISSPELLINGS (see the module docstring) --------------------------------------------------------
_SUFFIXES = ("s", "es", "ed", "ing", "er", "est", "y", "ly", "ier", "iest")
_VOWELS = "aeiou"


def inflections(word: str) -> set[str]:
    """The word and its regular inflections: -s, -es, -ed, -ing, -er, -est, -y, -ly, -ier, -iest; with a final
    "e" dropped ("wide" -> "wider", "booze" -> "boozy"), a final "y" made "i" ("happy" -> "happier") and a last
    consonant doubled ("hit" -> "hitting"). Some forms are not words; none is a misspelling a test needs read."""
    forms = {word, *(word + end for end in _SUFFIXES)}
    if word.endswith("e"):
        stem = word[:-1]
        forms |= {word + "d", word + "r", word + "st", stem + "ing", stem + "y", stem + "ier", stem + "iest"}
    if word.endswith("y"):
        stem = word[:-1]
        forms |= {stem + "ies", stem + "ied", stem + "ier", stem + "iest", stem + "ily"}
    if len(word) >= 3 and word[-1] not in _VOWELS + "wxy" and word[-2] in _VOWELS and word[-3] not in _VOWELS:
        forms |= {word + word[-1] + end for end in ("ed", "ing", "er", "est", "y")}
    return forms


def read_word_lists(paths: Iterable[Path]) -> set[str]:
    """Every word of the word lists, in lower case (a phrase of web2a gives each of its words)."""
    words: set[str] = set()
    for path in paths:
        words.update(re.findall(r"[a-z]+", path.read_text(encoding="utf-8").lower()))
    return words


def build_real_words(words: Iterable[str], checked: Iterable[str] = ()) -> list[str]:
    """`NOT_MISSPELLINGS` from the words of the word lists: they, `MODERN_WORDS` and the table words, with their
    inflections, and the words the spell checker accepted (`checked`, in lower case), that have five or more
    letters, are not table words and are one slip from a table word. Sorted.

    A string one slip from a hedge and from no other table word is kept only when it is itself a word, written
    in lower case: a word of the word lists or `MODERN_WORDS`, or one the spell checker accepts in lower case. An
    inflection made by `inflections` ("mayby" from "maybe", "eventualy" from "eventual") and a name the spell
    checker accepts only capitalised ("Mayne") are not kept, so they are read as the hedge (rule 2): a hedge lost
    would state the fact."""
    near = _near_table_words()
    checked = list(checked)
    bases = {*words, *MODERN_WORDS}
    in_lower_case = bases | {c for c in checked if c.islower()}
    forms = {f for w in {*bases, *SPELLING_WORDS} for f in inflections(w) if f in near}
    forms |= {c.lower() for c in checked if c.lower() in near}
    return sorted(
        f
        for f in forms
        if len(f) >= RESPELL_MIN_LETTERS
        and _letters(f)
        and f not in SPELLING_WORDS
        and (f in in_lower_case or not near[f] <= HEDGE_WORDS)
    )


def spellchecker_candidates() -> list[str]:
    """What the spell checker is asked about: every string of five or more letters one slip from a table word and
    not a table word (every string `respell` could change), in lower case and capitalised ("fresca" is a misspelling
    to the spell checker, "Fresca" a word). Sorted."""
    forms = sorted(
        f for f in _near_table_words() if len(f) >= RESPELL_MIN_LETTERS and f not in SPELLING_WORDS
    )
    return [form for f in forms for form in (f, f.capitalize())]


def run_spellchecker(candidates: Iterable[str]) -> list[str]:
    """The candidates the macOS spell checker accepts (scripts/spelling/spellchecker_accepts.swift: NSSpellChecker,
    US English, words the user taught it left out), as asked ("zines", "Fresca"), sorted. Needs macOS and the
    Swift toolchain."""
    result = subprocess.run(
        ["swift", str(SPELLCHECKER_SCRIPT)],
        input="\n".join(candidates) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


def read_spellchecker_words() -> list[str]:
    """The words of the committed `SPELLCHECKER_FILE`."""
    words: list[str] = json.loads(SPELLCHECKER_FILE.read_text(encoding="utf-8"))["words"]
    return words


def _write_words(path: Path, about: str, words: list[str]) -> None:
    path.write_text(json.dumps({"about": about, "words": words}, indent=1, ensure_ascii=True) + "\n", "utf-8")


def write_spellchecker_words() -> int:
    """Re-run the spell checker over `spellchecker_candidates` and write `SPELLCHECKER_FILE`. Returns how many
    words it holds."""
    words = run_spellchecker(spellchecker_candidates())
    about = (
        "Strings of five or more letters one slip from a word of app.memo.spelling.SPELLING_WORDS that the macOS "
        "spell checker (NSSpellChecker, en_US, learned words left out) accepts, in lower case or capitalised, as "
        "it accepted them. Asked by scripts/spelling/spellchecker_accepts.swift over "
        "app.memo.spelling.spellchecker_candidates; folded into spelling_real_words.json by "
        "app.memo.spelling.build_real_words. Rebuild with `python -m app.memo.spelling` (from apps/api, on a Mac "
        "with Swift) when SPELLING_WORDS changes. Read only by the build and its tests."
    )
    _write_words(SPELLCHECKER_FILE, about, words)
    return len(words)


def write_real_words() -> int:
    """Rebuild data/spelling_real_words.json from `SYSTEM_WORD_LISTS` and the committed `SPELLCHECKER_FILE`.
    Returns how many words it holds."""
    words = build_real_words(read_word_lists(SYSTEM_WORD_LISTS), read_spellchecker_words())
    about = (
        "Real English words of five or more letters that are one slip (a letter dropped, added or changed, or two "
        "neighbouring letters swapped) from a word of app.memo.spelling.SPELLING_WORDS. app.memo.spelling never "
        "respells them. Built by app.memo.spelling.build_real_words from the union of /usr/share/dict web2, "
        "web2a, words, propernames and connectives, app.memo.spelling.MODERN_WORDS and the table words, with "
        "their inflections, and the words the macOS spell checker accepts (spelling_spellchecker_words.json); "
        "rebuild with `python -m app.memo.spelling` (from apps/api, on a Mac with Swift; add --no-spellchecker "
        "to reuse the committed spell-checker file) when SPELLING_WORDS or MODERN_WORDS changes "
        "(tests/test_spelling.py fails until it is rebuilt)."
    )
    _write_words(_REAL_WORDS_FILE, about, words)
    return len(words)


if __name__ == "__main__":
    if "--no-spellchecker" not in sys.argv[1:]:
        print(f"{write_spellchecker_words()} words written to {SPELLCHECKER_FILE}")
    print(f"{write_real_words()} words written to {_REAL_WORDS_FILE}")
