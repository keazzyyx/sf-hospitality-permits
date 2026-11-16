from __future__ import annotations

import pytest

from precedent.textparse import (
    classify_use_types,
    detect_opposition,
    extract_closing_hour,
    extract_conditions,
    is_late_night,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Full-service restaurant with a wine bar, live music and a rear patio",
            ["bar", "restaurant", "live_entertainment", "outdoor_seating"],
        ),
        ("Change of use from retail to a Limited Restaurant (coffee shop)", ["restaurant", "cafe"]),
        ("Establish a nightclub with DJ and dancing", ["nightclub"]),
        ("Type 21 off-sale liquor store", ["retail_alcohol"]),
        ("Tourist hotel lobby renovation", ["hotel"]),
        ("Medical cannabis dispensary", ["cannabis"]),
        ("Rear yard variance for a single-family house", []),
        ("", []),
    ],
)
def test_classify_use_types(text: str, expected: list[str]) -> None:
    assert classify_use_types(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Extend hours of operation until 2:00 a.m.", "02:00"),
        ("open until 10pm daily", "22:00"),
        ("close at 11:30 p.m. on weeknights", "23:30"),
        ("hours of operation 11 a.m. - 2 a.m.", "02:00"),
        ("extend hours of bar from 10p.m. to 2a.m.", "02:00"),
        (
            "until 10 p.m. Sunday-Thursday and until 2 a.m. Friday and Saturday",
            "02:00",
        ),  # latest wins, after-midnight counts late
        ("closing time of 12 a.m.", "00:00"),
        ("Interior remodel, no change of hours", None),
        ("", None),
    ],
)
def test_extract_closing_hour(text: str, expected: str | None) -> None:
    assert extract_closing_hour(text) == expected


def test_is_late_night() -> None:
    assert is_late_night("02:00") is True
    assert is_late_night("00:00") is True
    assert is_late_night("22:00") is False
    assert is_late_night(None) is None


def test_extract_conditions() -> None:
    text = (
        "Approved with conditions. The bar shall close by 2 a.m. A security plan is required; "
        "No amplified music on the patio. The applicant shall maintain a community liaison. Unrelated sentence here."
    )
    assert extract_conditions(text) == [
        "The bar shall close by 2 a.m.",
        "A security plan is required;",
        "No amplified music on the patio.",
        "The applicant shall maintain a community liaison.",
    ]
    assert extract_conditions("Change of use from retail to restaurant.") == []
    assert extract_conditions("") == []


def test_detect_opposition() -> None:
    assert detect_opposition("Neighbors filed letters in opposition and a DR request.") is True
    assert detect_opposition("The project was appealed to the Board of Supervisors.") is True
    assert detect_opposition("There was no opposition at the hearing.") is False
    assert detect_opposition("Unopposed consent calendar item.") is False
    assert detect_opposition("A routine change of use.") is None
    assert detect_opposition("") is None
