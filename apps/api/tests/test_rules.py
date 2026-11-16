import pytest

from app.catalog import rules

P = {
    "seats": 40,
    "serves_alcohol": True,
    "alcohol_type": "beer_wine",
    "employees": None,
    "business_type": "bar",
}


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ({"always": True}, True),
        ({"field": "serves_alcohol", "eq": True}, True),
        ({"field": "serves_alcohol", "eq": False}, False),
        ({"field": "alcohol_type", "in": ["beer_wine", "full_liquor"]}, True),
        ({"field": "alcohol_type", "not_in": ["none"]}, True),
        ({"field": "seats", "gte": 50}, False),
        ({"field": "seats", "gte": 40}, True),
        ({"field": "seats", "lt": 50}, True),
        ({"field": "employees", "gte": 1}, False),  # None never matches comparisons
        ({"field": "employees", "neq": 3}, False),  # None never matches neq either
        ({"all": [{"field": "serves_alcohol", "eq": True}, {"field": "business_type", "eq": "bar"}]}, True),
        ({"any": [{"field": "seats", "gte": 500}, {"field": "business_type", "eq": "bar"}]}, True),
        ({"not": {"field": "business_type", "eq": "bar"}}, False),
    ],
)
def test_evaluate(rule: dict, expected: bool) -> None:
    assert rules.evaluate(rule, P) is expected


def test_bad_rule_raises() -> None:
    with pytest.raises(rules.RuleError):
        rules.evaluate({"field": "seats", "gte": 1, "lte": 5}, P)
    with pytest.raises(rules.RuleError):
        rules.evaluate({"nonsense": 1}, P)


def test_describe_round_trips_shape() -> None:
    text = rules.describe({"all": [{"field": "seats", "gte": 50}, {"not": {"field": "dancing", "eq": True}}]})
    assert "seats >= 50" in text and "NOT dancing = True" in text


# ---- a fact the profile marks "unknown" (decision 1) --------------------------------------------------------
UNKNOWN = {**P, "alcohol_type": "unknown"}
BEER = {"field": "alcohol_type", "eq": "beer_wine"}
SPIRITS = {"field": "alcohol_type", "eq": "full_liquor"}


def test_an_unknown_fact_matches_no_literal_value() -> None:
    assert rules.evaluate(BEER, UNKNOWN) is False and rules.evaluate(SPIRITS, UNKNOWN) is False
    # "serves something" is still true: unknown is never "none"
    assert rules.evaluate({"field": "alcohol_type", "neq": "none"}, UNKNOWN) is True


@pytest.mark.parametrize(
    ("rule", "expected", "condition"),
    [
        (BEER, None, "only beer and wine are served"),
        (SPIRITS, None, "spirits are served too"),
        ({"any": [BEER, SPIRITS]}, True, "only beer and wine are served or spirits are served too"),
        ({"field": "alcohol_type", "in": ["beer_wine", "full_liquor"]}, True, None),
        ({"field": "alcohol_type", "eq": "none"}, False, None),
        ({"all": [SPIRITS, {"field": "business_type", "eq": "bar"}]}, None, "spirits are served too"),
        (
            {"all": [SPIRITS, {"field": "business_type", "eq": "cafe"}]},
            False,
            None,
        ),  # decided by a known fact
        ({"not": BEER}, None, "spirits are served too"),
        ({"field": "seats", "gte": 10}, True, None),
    ],
)
def test_applicability_reads_every_value_an_unknown_fact_can_take(
    rule: dict, expected: bool | None, condition: str | None
) -> None:
    assert rules.applicability(rule, UNKNOWN) is expected
    if condition is not None:
        assert rules.condition_text(rules.applies_if(rule, UNKNOWN)) == condition


def test_applicability_is_evaluate_when_nothing_is_unknown() -> None:
    for rule in (BEER, SPIRITS, {"not": BEER}, {"field": "seats", "gte": 50}):
        assert rules.applicability(rule, P) is rules.evaluate(rule, P)
    assert rules.unknown_fields(P) == () and rules.readings(P) == [{}]
    assert rules.unknown_fields(UNKNOWN) == ("alcohol_type",)
    assert rules.readings(UNKNOWN) == [{"alcohol_type": "beer_wine"}, {"alcohol_type": "full_liquor"}]
