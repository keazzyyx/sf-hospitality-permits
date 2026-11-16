"""Evaluation of the catalog's `applies_when` rule DSL over a BusinessProfile dict.

A fact the profile marks "unknown" (today only `alcohol_type`: the concept serves alcohol and the description
does not say what) is never read as one of its values and never as "none". `evaluate` reads the literal
value, so a rule on an unknown fact simply does not match; the permit checklist uses `applicability`, which
reads the rule once for every value the fact can take (`POSSIBLE_VALUES`): the same answer for all of them
decides the rule, and different answers leave it undetermined (None). `applies_if` lists the values under which
an undetermined rule applies and `condition_text` says them in plain words, so a licence that depends on what
is served never drops out of the checklist silently and is never picked at random: it is listed as not
determined, with the condition under which it applies (app.tools.catalog_tool.lookup).
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from typing import Any

Rule = Mapping[str, Any]

_COMPARATORS = {"gt", "gte", "lt", "lte"}

# The value a profile field holds when the description does not say, for a field that has no null.
UNKNOWN = "unknown"
# The values an unknown field can take, in the order they are tried and listed.
POSSIBLE_VALUES: dict[str, tuple[str, ...]] = {"alcohol_type": ("beer_wine", "full_liquor")}
# Each value of an unknown field as a condition, in plain words ("applies if ...").
VALUE_WORDS: dict[tuple[str, str], str] = {
    ("alcohol_type", "beer_wine"): "only beer and wine are served",
    ("alcohol_type", "full_liquor"): "spirits are served too",
}


class RuleError(ValueError):
    pass


def evaluate(rule: Rule, profile: Mapping[str, Any]) -> bool:
    """Return True when `rule` matches `profile`. Unknown/None field values never match comparisons."""
    if "always" in rule:
        return True
    if "all" in rule:
        return all(evaluate(sub, profile) for sub in rule["all"])
    if "any" in rule:
        return any(evaluate(sub, profile) for sub in rule["any"])
    if "not" in rule:
        return not evaluate(rule["not"], profile)
    if "field" in rule:
        field = rule["field"]
        value = profile.get(field)
        ops = [k for k in rule if k != "field"]
        if len(ops) != 1:
            raise RuleError(f"field rule for {field!r} must have exactly one operator")
        op = ops[0]
        expected = rule[op]
        if op == "eq":
            return bool(value == expected)
        if op == "neq":
            return bool(value is not None and value != expected)
        if op == "in":
            return bool(value in expected)
        if op == "not_in":
            return bool(value is not None and value not in expected)
        if op in _COMPARATORS:
            if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
                return False
            if op == "gt":
                return bool(value > expected)
            if op == "gte":
                return bool(value >= expected)
            if op == "lt":
                return bool(value < expected)
            return bool(value <= expected)
        raise RuleError(f"unknown operator {op!r}")
    raise RuleError(f"unrecognised rule shape: {sorted(rule)}")


def describe(rule: Rule) -> str:
    """Human-readable rendering used in the catalog context given to the model."""
    if "always" in rule:
        return "always"
    if "all" in rule:
        return "(" + " AND ".join(describe(r) for r in rule["all"]) + ")"
    if "any" in rule:
        return "(" + " OR ".join(describe(r) for r in rule["any"]) + ")"
    if "not" in rule:
        return "NOT " + describe(rule["not"])
    field = rule["field"]
    op = next(k for k in rule if k != "field")
    symbol = {
        "eq": "=",
        "neq": "!=",
        "in": "in",
        "not_in": "not in",
        "gt": ">",
        "gte": ">=",
        "lt": "<",
        "lte": "<=",
    }[op]
    return f"{field} {symbol} {rule[op]!r}"


# ---- unknown facts ---------------------------------------------------------------------------------------
def unknown_fields(profile: Mapping[str, Any]) -> tuple[str, ...]:
    """The fields of `profile` that hold UNKNOWN and have a list of possible values, in POSSIBLE_VALUES order."""
    return tuple(f for f in POSSIBLE_VALUES if profile.get(f) == UNKNOWN)


def readings(profile: Mapping[str, Any]) -> list[dict[str, str]]:
    """Every way the unknown fields can be filled: one dict of field -> value per combination (one empty dict
    when no field is unknown)."""
    fields = unknown_fields(profile)
    return [
        dict(zip(fields, values, strict=True))
        for values in itertools.product(*(POSSIBLE_VALUES[f] for f in fields))
    ]


def applies_if(rule: Rule, profile: Mapping[str, Any]) -> list[dict[str, str]]:
    """The readings (`readings`) under which `rule` matches `profile`."""
    return [r for r in readings(profile) if evaluate(rule, {**profile, **r})]


def applicability(rule: Rule, profile: Mapping[str, Any]) -> bool | None:
    """True or False when the rule gives the same answer whatever the unknown fields hold (exactly `evaluate`
    when none is unknown); None when the answer depends on them: the rule is undetermined."""
    every = readings(profile)
    matching = applies_if(rule, profile)
    if not matching:
        return False
    if len(matching) == len(every):
        return True
    return None


def condition_text(matching: Sequence[Mapping[str, str]]) -> str:
    """The readings under which a rule applies, in plain words: "spirits are served too"; several readings
    are joined with "or"."""
    parts = [" and ".join(VALUE_WORDS[(f, v)] for f, v in r.items()) for r in matching]
    return " or ".join(dict.fromkeys(parts))
