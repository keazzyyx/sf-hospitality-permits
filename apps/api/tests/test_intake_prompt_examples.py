"""The memo intake prompt's misspelling examples are made up: none comes from the 2301 Chestnut St description the
spelling rules were built from and are checked against, nor from a backtest, holdout or validation description. A
prompt that holds the text of a check hands the model its answer, so a pass shows nothing about other text
(docs/validation/intake-stated-facts.md: the prompt's examples are new, general ones)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

import yaml

from app.agents import prompts
from app.memo.stated import normalise

REPO = Path(__file__).resolve().parents[3]
CHESTNUT = (
    "Indian food restaurant with alochol license, open till 2 am and 40 people sitting with a outside ppatio"
)
# The keys whose values are a business description in the case and report files.
DESCRIPTION_KEYS = frozenset(
    {"concept_input", "concept_as_filed", "description", "existing_use_text", "concept_summary"}
)
SHORTEST = 4  # the fewest words a phrase shared with a description may have


def _words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).split()


def _phrases(words: list[str], n: int) -> set[str]:
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def _strings(value: object, key: str | None = None) -> Iterator[str]:
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(v, str(k))
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v, key)
    elif isinstance(value, str) and key in DESCRIPTION_KEYS:
        yield value


@lru_cache(maxsize=1)
def _descriptions() -> tuple[str, ...]:
    """Every description in backtest/ (the 40 and the holdout) and docs/validation/."""
    found: set[str] = set()
    for folder in (REPO / "backtest", REPO / "docs" / "validation"):
        for path in sorted(folder.rglob("*")):
            if path.suffix == ".json":
                found.update(_strings(json.loads(path.read_text())))
            elif path.suffix in (".yaml", ".yml"):
                found.update(_strings(yaml.safe_load(path.read_text())))
    return tuple(sorted(found))


def _misspelling_examples() -> str:
    """The prompt's sentence on misspelt words, up to the end of its line."""
    start = prompts.MEMO_INTAKE.index("A misspelt word still states the fact")
    return prompts.MEMO_INTAKE[start:].split("\n", 1)[0]


def test_the_memo_intake_prompt_still_says_a_misspelt_word_states_the_fact_and_is_quoted_as_written() -> None:
    sentence = _misspelling_examples()
    assert "you quote it as the applicant wrote it" in sentence
    assert sentence.count("(quote ") >= 3  # each example gives its quote, misspelt as written
    assert "A misspelt word" not in prompts.INTAKE  # the checklist's intake has no quotes


def test_no_intake_prompt_holds_the_chestnut_description() -> None:
    for prompt in (prompts.MEMO_INTAKE, prompts.INTAKE):
        for form in (" ".join(_words(prompt)), normalise(prompt)):
            padded = f" {form} "
            for word in ("alochol", "ppatio"):
                assert f" {word} " not in padded, word
            for chestnut in (_words(CHESTNUT), normalise(CHESTNUT).split()):
                for phrase in _phrases(chestnut, 3):  # "40 people sitting" is three words
                    assert f" {phrase} " not in padded, phrase


def test_the_misspelling_examples_share_no_phrase_with_a_backtest_holdout_or_validation_description() -> None:
    descriptions = _descriptions()
    assert len(descriptions) > 60  # the 40, the holdout and the validation runs were all read
    assert any("Type 20 licence by transfer" in d for d in descriptions)  # a holdout description
    sentence = _misspelling_examples()
    for form in (_words, lambda t: normalise(t).split()):
        ours = _phrases(form(sentence), SHORTEST)
        for description in descriptions:
            shared = ours & _phrases(form(description), SHORTEST)
            assert not shared, (shared, description[:80])
