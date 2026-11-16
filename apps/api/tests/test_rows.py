"""app.memo.rows: the alcohol row, the three change-of-use answers, the building row, the entertainment row and
the referral steps (rule table v2; spec sections 3a and 4).

Everything runs on the bundled data files. The trigger findings are built by hand: the rows read only their
family, control, missing inputs and lines.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
from typing import Any

import pytest

from app.memo import controls, rows, tracts
from app.memo.facts import MISSING_PHRASES, ConceptFacts, SiteFacts, concept_facts
from app.memo.pathway import AGENCIES, APPROVALS, LEGAL_BASIS
from app.models.memo import (
    TRIGGER_LABELS,
    ChangeAnswers,
    PlanningUse,
    RowDetermination,
    RuleLine,
    TriggerControl,
    TriggerFamily,
    TriggerFinding,
)
from app.models.profile import BusinessProfile, BusinessType

D = dt.date
TODAY = D(2026, 11, 10)
T4: TriggerFamily = "licence_in_restricted_district"
LICENCE_TYPE = MISSING_PHRASES["licence_type"]
TRANSACTION = MISSING_PHRASES["alcohol_transaction"]
POURS = MISSING_PHRASES["alcohol_served"]
LAST_USE = MISSING_PHRASES["existing_use_stated"]
OCCUPANTS = MISSING_PHRASES["occupants_under_50"]
PCN_SECTION = "California Business and Professions Code § 23958.4"

OVER = next(t for t in tracts.tracts_with_figures() if tracts.concentration(t, "on_sale").over)  # type: ignore[union-attr]
UNDER = next(t for t in tracts.tracts_with_figures() if not tracts.concentration(t, "on_sale").over)  # type: ignore[union-attr]

# The four Entertainment Commission permits of Ordinance 118-25, by the data's `permit` key.
FOUR_PERMITS = (
    rows.PLACE_OF_ENTERTAINMENT,
    rows.LIMITED_LIVE_PERFORMANCE,
    rows.FIXED_PLACE_OUTDOOR_AMPLIFIED_SOUND,
    rows.EXTENDED_HOURS_PREMISES,
)
APPLICATION = {
    rows.PLACE_OF_ENTERTAINMENT: "Place of Entertainment Permit application",
    rows.LIMITED_LIVE_PERFORMANCE: "Limited Live Performance Permit application",
    rows.FIXED_PLACE_OUTDOOR_AMPLIFIED_SOUND: "Fixed Place Outdoor Amplified Sound Permit application",
    rows.EXTENDED_HOURS_PREMISES: "Extended-Hours Premises Permit application",
}
BEFORE_250_23, FROM_250_23 = D(2024, 1, 13), D(2024, 1, 14)  # Ord. 250-23, effective 14 January 2024
BEFORE_118_25, FROM_118_25 = D(2025, 8, 16), D(2025, 8, 17)  # Ord. 118-25, effective 17 August 2025


# ---- builders -------------------------------------------------------------------------------------------
def concept(business_type: BusinessType = "bar", **kw: Any) -> ConceptFacts:
    return concept_facts(BusinessProfile(business_type=business_type, **kw))


def bar(**kw: Any) -> ConceptFacts:
    """A bar pouring spirits (Type 48, derived) under a new licence, unless told otherwise."""
    base: dict[str, Any] = {
        "serves_alcohol": True,
        "alcohol_type": "full_liquor",
        "alcohol_transaction": "new_licence",
    }
    return concept("bar", **{**base, **kw})


def restaurant(**kw: Any) -> ConceptFacts:
    """A restaurant pouring beer and wine (Type 41, derived) under a new licence, unless told otherwise."""
    base: dict[str, Any] = {
        "serves_alcohol": True,
        "alcohol_type": "beer_wine",
        "alcohol_transaction": "new_licence",
    }
    return concept("restaurant", **{**base, **kw})


def site(existing: PlanningUse | None = None, *, on: dt.date = TODAY) -> SiteFacts:
    """Site facts as the records give them: an existing use shown by one licence record, or none shown."""
    if existing is None:
        lines = (
            RuleLine(
                rule_id="zoning.existing_use",
                text="No active ABC licence of a type the rules read is on file at 1 Test St.",
                code_section=None,
            ),
        )
    else:
        lines = (
            RuleLine(
                rule_id="zoning.existing_use",
                text=f"An active ABC licence is on file at 1 Test St; the rules read the space as a {existing}.",
                code_section="Planning Code § 102",
                citations=["app:lic-1"],
            ),
        )
    return SiteFacts(
        rules_date=on, licences=(), existing_use=existing, existing_use_lines=lines, prior_decisions=()
    )


def finding(
    family: TriggerFamily,
    control: TriggerControl,
    *,
    section: str | None = None,
    missing: tuple[str, ...] = (),
    line_id: str | None = None,
    text: str | None = None,
    citations: tuple[str, ...] = ("overlay:sud-1",),
    more: tuple[RuleLine, ...] = (),
) -> TriggerFinding:
    number = {
        "licence_in_restricted_district": "T4",
        "new_use_control": "T1",
        "nighttime_entertainment": "T6",
    }
    rule_id = number.get(family, "T2")
    return TriggerFinding(
        rule_id=rule_id,
        family=family,
        label=TRIGGER_LABELS[family],
        control=control,
        missing_inputs=list(missing),
        lines=[
            RuleLine(
                rule_id=line_id or rule_id,
                text=text or f"{TRIGGER_LABELS[family]}: {control}.",
                code_section=section,
                citations=list(citations),
            ),
            *more,
        ],
    )


# T4 as the trigger rules give it for a new Bar inside the Mission Alcoholic Beverage Special Use District: one
# finding, conditional, whose lines are each built around one rule of the data ("T4:<the data's rule_id>"). The
# transfer requirement states no control; it is one of the lines.
MISSION_TRANSFER = RuleLine(
    rule_id="T4:mission.new_bar_licence_from_bar_in_district",
    text=(
        "Mission Alcoholic Beverage Special Use District: A new Bar must use a liquor licence transferred from "
        "another Bar located inside the district. This is a requirement, not a control."
    ),
    code_section="Planning Code § 249.60(b)(2)(C)",
    citations=["overlay:sud-1"],
)
MISSION_BAR = {
    "line_id": "T4:mission.new_or_relocated_bar",
    "section": "Planning Code § 249.60(b)(2)(C)",
    "text": "Mission Alcoholic Beverage Special Use District: a new Bar is a conditional use.",
}
MISSION_CONDITIONAL = finding(T4, "conditional", more=(MISSION_TRANSFER,), **MISSION_BAR)  # type: ignore[arg-type]


def alcohol(
    c: ConceptFacts,
    *,
    s: SiteFacts | None = None,
    findings: tuple[TriggerFinding, ...] = (),
    prohibited: bool = False,
    tract: str | None = None,
    on: dt.date = TODAY,
) -> RowDetermination:
    return rows.alcohol_row(
        c, s or site(), list(findings), zoning_prohibits_use=prohibited, tract=tract, rules_date=on
    )


def changes(
    c: ConceptFacts,
    *,
    s: SiteFacts | None = None,
    findings: tuple[TriggerFinding, ...] = (),
    district: str | None = "NC-2",
    on: dt.date = TODAY,
    existing_group: str | None = None,
) -> ChangeAnswers:
    return rows.change_answers(
        c, s or site(), list(findings), district, rules_date=on, existing_occupancy_group=existing_group
    )


def texts(lines: list[RuleLine]) -> list[str]:
    return [line.text for line in lines]


def ids(lines: list[RuleLine]) -> list[str]:
    return [line.rule_id for line in lines]


def dump(value: Any) -> str:
    return json.dumps(value.model_dump(), sort_keys=True)


def tract_lines(row: RowDetermination) -> list[RuleLine]:
    return [line for line in row.basis if line.rule_id == tracts.RULE_ID]


# ---- the fixed text -------------------------------------------------------------------------------------
def test_the_fixed_sentences_are_in_one_table_and_spell_licence_as_the_code_does() -> None:
    assert not set(rows.ROW_BASIS) & set(LEGAL_BASIS), "a key must name one sentence"
    for key, basis in rows.ROW_BASIS.items():
        assert "license" not in basis.text.lower(), key
        assert basis.text[0].isupper() or basis.text.startswith("{"), key
        # a whole sentence; two end in a clause that is itself a sentence or empty
        assert basis.text.endswith((".", "{since}", "{still}")), key
    assert set(rows.TESTED_TRANSACTIONS) == set(tracts.TRANSACTIONS_TESTED)
    assert rows.EXISTING_GROUP_PHRASE not in MISSING_PHRASES.values()
    assert rows.USE_LABELS["nighttime_entertainment"] == "Nighttime Entertainment"


def test_no_line_is_left_with_an_unfilled_field() -> None:
    made: list[RuleLine] = []
    for c, on in itertools.product(
        (bar(), restaurant(), concept("cafe"), concept("other"), bar(alcohol_transaction=None)),
        (D(2023, 1, 1), FROM_250_23, TODAY),
    ):
        row = alcohol(c, tract=OVER, findings=(MISSION_CONDITIONAL,), on=on)
        answers = changes(c, on=on)
        building = rows.building_row(answers, c, zoning_prohibits_use=False, rules_date=on)
        show = rows.entertainment_row(c, [], rules_date=on, zoning_prohibits_use=False)
        for r in (row, building, show):
            made += [*r.basis, *r.referral_steps]
        made += [
            *answers.planning_use_lines,
            *answers.building_occupancy_lines,
            *answers.neighbourhood_notice_lines,
        ]
    assert made
    for line in made:
        assert "{" not in line.text and "}" not in line.text, line.text
        assert "  " not in line.text and line.text.strip() == line.text, line.text
        assert line.rule_id


# ---- the alcohol row ------------------------------------------------------------------------------------
def test_a3_a_licence_with_nothing_else_is_further_review() -> None:
    row = alcohol(restaurant(), tract=UNDER)
    assert (row.area, row.status, row.status_note) == ("alcohol", "further_review", None)
    assert row.approval == "ABC licence, Type 41 (on-sale beer and wine, eating place)"
    assert row.agency == AGENCIES["alcohol"]
    assert row.missing_inputs == []
    assert ids(row.basis) == ["alcohol.licence", "alcohol.transaction", "alcohol.status"]
    assert row.basis[-1].text == LEGAL_BASIS["alcohol.status/A3"].text.format(status="further review")
    assert row.basis[-1].code_section == LEGAL_BASIS["alcohol.status/A3"].code_section


def test_a_derived_licence_type_counts_as_given_and_the_line_says_it_was_derived() -> None:
    derived = alcohol(restaurant())
    assert derived.status == "further_review" and derived.missing_inputs == []
    assert derived.basis[0].text == (
        "The description does not state a licence type. The rules derived ABC Type 41 (on-sale beer and wine, "
        "eating place) from the kind of business and what it pours."
    )
    stated = alcohol(restaurant(licence_type="47"))
    assert stated.basis[0].text == (
        "The licence looked up is ABC Type 47 (on-sale general, eating place), as stated in the description."
    )
    assert stated.approval == "ABC licence, Type 47 (on-sale general, eating place)"
    other = alcohol(concept("bar", serves_alcohol=True, licence_type="90", alcohol_transaction="new_licence"))
    assert other.approval == "ABC licence, Type 90"
    assert other.basis[0].text == "The licence looked up is ABC Type 90, as stated in the description."


@pytest.mark.parametrize(
    ("transaction", "words"),
    [
        ("new_licence", "as a new licence"),
        (
            "person_to_person_transfer",
            "by transfer from another licence holder (a person-to-person transfer)",
        ),
        ("premises_transfer", "by transfer from other premises (a premises-to-premises transfer)"),
    ],
)
def test_the_transaction_line_says_what_the_applicant_states(transaction: str, words: str) -> None:
    # the description or an intake answer gives it (app.memo.intake): either way the applicant states it
    row = alcohol(restaurant(alcohol_transaction=transaction))
    assert row.basis[1].text == f"The licence is to be obtained {words}, as the applicant states."
    assert row.status == "further_review"


def test_a1_zoning_prohibits_a_new_use() -> None:
    row = alcohol(bar(), prohibited=True)
    assert row.status == "not_permitted" and row.status_note is None
    last = row.basis[-1]
    assert last.text == LEGAL_BASIS["alcohol.status/A1"].text.format(use="Bar", status="not permitted")
    assert last.code_section == "California Business and Professions Code § 23790"
    assert row.referral_steps == [] and row.missing_inputs == []
    # A1 comes before the missing inputs: the licence cannot issue whatever they are
    assert alcohol(concept("bar", serves_alcohol=True), prohibited=True).status == "not_permitted"


@pytest.mark.parametrize(
    ("c", "s"),
    [
        (bar(), site("bar")),  # the records show the same use
        (bar(existing_use_stated=["bar"]), site()),  # the description says so
        (bar(changes_existing_business="intensify"), site()),  # an existing business stays
        (bar(changes_existing_business="none"), site()),
    ],
)
def test_a1_is_not_reached_when_the_existing_use_continues(c: ConceptFacts, s: SiteFacts) -> None:
    assert rows.existing_use_continues(c, s)
    assert alcohol(c, s=s, prohibited=True).status == "further_review"


def test_a_new_use_does_not_continue() -> None:
    assert not rows.existing_use_continues(bar(), site())
    assert not rows.existing_use_continues(bar(), site("restaurant"))
    assert not rows.existing_use_continues(bar(existing_use_stated=["retail"]), site())


@pytest.mark.parametrize(
    ("c", "missing"),
    [
        # what is poured is not said: it is named in place of the licence type it would decide
        (concept("bar", serves_alcohol=True, alcohol_transaction="new_licence"), [POURS]),
        (bar(alcohol_transaction=None), [TRANSACTION]),
        (concept("bar", serves_alcohol=True), [POURS, TRANSACTION]),
        (concept("bar", serves_alcohol=True, alcohol_type="unknown"), [POURS, TRANSACTION]),
        # no use to look a type up by: the licence type itself
        (concept("other", serves_alcohol=True), [LICENCE_TYPE, TRANSACTION]),
        (concept("other", serves_alcohol=True, alcohol_type="unknown"), [LICENCE_TYPE, TRANSACTION]),
    ],
)
def test_a0_a_missing_licence_type_or_transaction_is_named(c: ConceptFacts, missing: list[str]) -> None:
    row = alcohol(c, tract=UNDER)
    assert row.status == "insufficient_information" and row.status_note is None
    assert row.missing_inputs == missing
    last = row.basis[-1]
    assert last.rule_id == "alcohol.status"
    assert last.text == (
        f"The description does not give {' and '.join(missing)}, so the rules cannot say which licence rules "
        "apply: insufficient information."
    )
    assert row.approval == (
        "ABC licence"
        if LICENCE_TYPE in missing or POURS in missing
        else "ABC licence, Type 48 (on-sale general, public premises)"
    )


def test_the_missing_input_phrases_are_the_facts_modules_own() -> None:
    assert LICENCE_TYPE == "the licence type"
    assert TRANSACTION == (
        "how the liquor licence will be obtained (new, or a transfer from another owner or another location)"
    )
    c = concept("restaurant", serves_alcohol=True)
    assert alcohol(c).missing_inputs == list(c.missing(("licence_type", "alcohol_transaction")))


def test_t4_conditional_is_further_review() -> None:
    conditional = finding(
        T4, "conditional", section="Planning Code § 780.3(c)(2)(A)", text="North Beach: a CU."
    )
    row = alcohol(restaurant(), findings=(conditional,))
    assert row.status == "further_review" and row.status_note is None
    assert "North Beach: a CU." in texts(row.basis)
    last = row.basis[-1]
    assert last.rule_id == "alcohol.status" and "Conditional Use Authorization" in last.text
    assert last.code_section is not None and last.code_section.startswith("Planning Code § 303")
    assert last.citations == ["overlay:sud-1"]


def test_t4_not_permitted_is_not_permitted() -> None:
    barred = finding(
        T4, "not_permitted", section="Planning Code § 249.62(a)(1)", text="Third Street: not permitted."
    )
    row = alcohol(bar(), findings=(barred,))
    assert row.status == "not_permitted"
    assert "Third Street: not permitted." in texts(row.basis)
    assert row.basis[-1].code_section == "California Business and Professions Code § 23790"
    assert row.referral_steps == []
    # it does not wait for a missing input either
    assert alcohol(bar(alcohol_transaction=None), findings=(barred,)).status == "not_permitted"


def test_t4_not_decided_names_what_t4_could_not_read() -> None:
    open_ = finding(
        T4, "not_decided", missing=("whether the establishment is new",), text="Haight: not decided."
    )
    row = alcohol(bar(), findings=(open_,))
    assert row.status == "insufficient_information"
    assert row.missing_inputs == ["whether the establishment is new"]
    assert row.basis[-1].text == (
        "The liquor licence rule of the restricted district cannot be decided without whether the establishment "
        "is new: insufficient information."
    )
    # with the row's own inputs missing too, every missing input is named once, the row's first
    both = alcohol(bar(alcohol_transaction=None), findings=(open_,))
    assert both.missing_inputs == [TRANSACTION, "whether the establishment is new"]


def test_a_missing_input_comes_before_the_requirement_and_does_not_hide_it() -> None:
    # spec section 4 orders the alcohol row: the missing input first, the restricted-district rule after
    row = alcohol(bar(alcohol_transaction=None), findings=(MISSION_CONDITIONAL,))
    assert row.status == "insufficient_information" and row.missing_inputs == [TRANSACTION]
    assert MISSION_TRANSFER in row.basis and MISSION_BAR["text"] in texts(row.basis)
    assert row.basis[-1].rule_id == "alcohol.status"


def test_a_t4_finding_that_asks_for_nothing_changes_nothing() -> None:
    plain = alcohol(restaurant())
    for control in ("principal", "does_not_apply"):
        quiet = finding(T4, control, section="Planning Code § 784", text="Lower Haight: not reached.")  # type: ignore[arg-type]
        assert dump(alcohol(restaurant(), findings=(quiet,))) == dump(plain)


def test_a2_the_mission_transfer_requirement_for_a_new_bar_is_a_potential_blocker() -> None:
    row = alcohol(bar(), findings=(MISSION_CONDITIONAL,))
    assert row.status == "potential_blocker" and row.status_note is None
    assert rows.blocking_requirements([MISSION_CONDITIONAL]) == [MISSION_TRANSFER]
    # the requirement is T4's own line, printed once, straight before the status line that says "that condition"
    assert row.basis[-2] == MISSION_TRANSFER
    assert texts(row.basis).count(MISSION_TRANSFER.text) == 1
    assert row.basis[-1].text == LEGAL_BASIS["alcohol.status/A2"].text.format(status="potential blocker")
    assert row.basis[-1].citations == ["overlay:sud-1"]
    assert MISSION_BAR["text"] in texts(row.basis)  # the rest of what T4 found is kept
    # the requirement states no control: it blocks whatever control T4 gives
    for control in ("principal", "conditional"):
        only = finding(T4, control, line_id=MISSION_TRANSFER.rule_id, text=MISSION_TRANSFER.text)  # type: ignore[arg-type]
        assert alcohol(bar(), findings=(only,)).status == "potential_blocker"


@pytest.mark.parametrize(
    "found",
    [
        (finding(T4, "conditional", **MISSION_BAR),),  # type: ignore[arg-type]  # T4 did not print the requirement
        (finding(T4, "conditional", line_id="T4:mission.existing_liquor_establishment_expansion"),),
        (finding(T4, "conditional", line_id="T4:mission.good_neighbor_policies"),),  # another requirement
        (finding(T4, "conditional", line_id="T4:mission.new_bar_licence_from_bar_in_district_x"),),
        # the same line under another trigger is not a licence finding
        (finding("new_use_control", "conditional", line_id=MISSION_TRANSFER.rule_id),),
        (),
    ],
)
def test_a2_is_reached_only_by_a_t4_line_that_states_a_blocking_requirement(
    found: tuple[TriggerFinding, ...],
) -> None:
    assert rows.blocking_requirements(found) == []
    assert alcohol(bar(), findings=found).status == "further_review"


def test_every_blocking_requirement_is_a_requirement_of_the_dated_data() -> None:
    on_file = {
        rule.rule_id: rule.control
        for key in controls.special_district_keys()
        for rule in controls.special_rules(key, TODAY)
    }
    assert sorted(rows.BLOCKING_REQUIREMENTS) == ["mission.new_bar_licence_from_bar_in_district"]
    for rule_id in rows.BLOCKING_REQUIREMENTS:
        assert on_file[rule_id] == "requirement"


@pytest.mark.parametrize("transaction", sorted(tracts.TRANSACTIONS_TESTED))
def test_over_concentration_with_a_tested_transaction_is_further_review_with_the_qualifier(
    transaction: str,
) -> None:
    row = alcohol(restaurant(alcohol_transaction=transaction), tract=OVER)
    assert row.status == "further_review"
    assert (
        row.status_note == "public convenience or necessity finding likely required" == tracts.PCN_STATUS_NOTE
    )
    numbers, tested = tract_lines(row)
    c = tracts.concentration(OVER, "on_sale")
    assert c is not None
    assert numbers.text == tracts.concentration_line(c)
    assert str(c.active) in numbers.text and str(c.authorised) in numbers.text
    assert tracts.plain_date(c.active_as_of) in numbers.text
    assert tracts.plain_date(c.authorised_as_of) in numbers.text
    assert numbers.code_section == tested.code_section == PCN_SECTION
    assert tested.text == (
        f"The tract is over its authorised number, and state law tests {rows.TESTED_TRANSACTIONS[transaction]} "
        "for undue concentration. The licence may still issue if public convenience or necessity would be "
        "served: public convenience or necessity finding likely required."
    )
    assert row.basis[-1].rule_id == "alcohol.status"  # the status line is still the last one


@pytest.mark.parametrize("transaction", ["person_to_person_transfer", "licence_already_held"])
def test_a_transaction_the_statute_does_not_test_gets_no_qualifier(transaction: str) -> None:
    row = alcohol(restaurant(alcohol_transaction=transaction), tract=OVER)
    # a licence already held files nothing with ABC (corrected from further review by the review)
    expected = "allowed" if transaction == "licence_already_held" else "further_review"
    assert row.status == expected and row.status_note is None
    assert tract_lines(row) == []
    assert dump(row) == dump(alcohol(restaurant(alcohol_transaction=transaction), tract=None))


@pytest.mark.parametrize("tract", [None, UNDER, "9999.99", "not a tract"])
def test_a_tract_that_is_unknown_or_not_over_prints_nothing(tract: str | None) -> None:
    row = alcohol(restaurant(), tract=tract)
    assert row.status == "further_review" and row.status_note is None
    assert tract_lines(row) == []
    assert not any("tract" in text.lower() or "convenience" in text.lower() for text in texts(row.basis))
    assert dump(row) == dump(alcohol(restaurant(), tract=None))


def test_over_concentration_on_top_of_a_potential_blocker_prints_the_line_and_keeps_the_status() -> None:
    row = alcohol(bar(), findings=(MISSION_CONDITIONAL,), tract=OVER)
    assert row.status == "potential_blocker" and row.status_note is None
    assert len(tract_lines(row)) == 2
    without = alcohol(bar(), findings=(MISSION_CONDITIONAL,), tract=None)
    assert without.status == "potential_blocker"
    assert [line for line in row.basis if line.rule_id != tracts.RULE_ID] == without.basis


def test_over_concentration_on_top_of_not_permitted_prints_the_line_and_keeps_the_status() -> None:
    row = alcohol(bar(), prohibited=True, tract=OVER)
    assert row.status == "not_permitted" and row.status_note is None
    # the numbers only: a licence that cannot issue is never said to "still issue" (corrected from 2 lines)
    assert len(tract_lines(row)) == 1
    assert not any("may still issue" in text for text in texts(row.basis))
    assert row.basis[-1].rule_id == "alcohol.status"


def test_over_concentration_with_the_transaction_missing_stays_insufficient_information() -> None:
    row = alcohol(restaurant(alcohol_transaction=None), tract=OVER)
    assert row.status == "insufficient_information" and row.status_note is None
    assert row.missing_inputs == [TRANSACTION]
    numbers, said = tract_lines(row)
    assert numbers.text.startswith(f"Census tract {OVER}:")
    assert said.text == (
        "The tract is over its authorised number. State law tests a new licence and a transfer from other "
        "premises for undue concentration, and the applicant does not say how the liquor licence will be "
        "obtained."
    )
    # with the licence type missing the kind of licence is not known, so no tract is read at all
    assert tract_lines(alcohol(concept("bar", serves_alcohol=True), tract=OVER)) == []


def test_over_concentration_alone_never_gives_a_blocker_or_not_permitted() -> None:
    over = [t for t in tracts.tracts_with_figures() if tracts.concentration(t, "on_sale").over]  # type: ignore[union-attr]
    assert len(over) > 10
    for tract, number, transaction in itertools.product(
        over[:25], ("41", "42", "47", "48", "90"), ("new_licence", "premises_transfer")
    ):
        c = concept("bar", serves_alcohol=True, licence_type=number, alcohol_transaction=transaction)
        row = alcohol(c, tract=tract)
        assert row.status == "further_review", (tract, number, transaction)
        assert row.status_note == tracts.PCN_STATUS_NOTE


def test_a_licence_type_that_is_not_counted_reads_no_tract() -> None:
    c = concept("bar", serves_alcohol=True, licence_type="23", alcohol_transaction="new_licence")
    assert tracts.kind_for_licence_type("23") is None
    row = alcohol(c, tract=OVER)
    assert row.status_note is None and tract_lines(row) == []


@pytest.mark.parametrize(("number", "limited"), [("41", False), ("42", False), ("47", True), ("48", True)])
def test_the_county_limit_line_is_kept_for_types_47_and_48(number: str, limited: bool) -> None:
    c = concept("bar", serves_alcohol=True, licence_type=number, alcohol_transaction="new_licence")
    row = alcohol(c)
    assert ("alcohol.county_limit" in ids(row.basis)) is limited
    if limited:
        line = next(x for x in row.basis if x.rule_id == "alcohol.county_limit")
        assert line.text == LEGAL_BASIS["alcohol.county_limit"].text.format(type=number)
        assert line.code_section == "California Business and Professions Code § 23816"
    # v1 kept it off the not-permitted row; a licence already held is not transferred, so it is left out there
    assert "alcohol.county_limit" not in ids(alcohol(c, prohibited=True).basis)
    held = concept(
        "bar", serves_alcohol=True, licence_type=number, alcohol_transaction="licence_already_held"
    )
    assert "alcohol.county_limit" not in ids(alcohol(held).basis)


def test_the_alcohol_rows_referral_steps() -> None:
    row = alcohol(restaurant(), tract=OVER)
    assert [line.rule_id for line in row.referral_steps] == ["referral.step", "referral.step"]
    assert "Police Department (ABC Liaison Unit)" in row.referral_steps[0].text
    assert "Planning Department" in row.referral_steps[1].text
    assert all("§ 23987" in (line.code_section or "") for line in row.referral_steps)
    # the Board of Supervisors' determination is for licences other than an eating place's (§ 23958.4(b)(2))
    board = "Public convenience or necessity determination by the Board of Supervisors"
    assert not any(board in line.text for line in row.referral_steps)
    bar_row = alcohol(bar(), tract=OVER)
    assert sum(board in line.text for line in bar_row.referral_steps) == 2
    assert not any(board in line.text for line in alcohol(bar(), tract=UNDER).referral_steps)
    # a licence already held is not applied for
    assert alcohol(restaurant(alcohol_transaction="licence_already_held")).referral_steps == []


# ---- change of use 1: the Planning Code use -------------------------------------------------------------
def test_planning_use_no_when_the_records_show_the_same_use() -> None:
    got = changes(restaurant(), s=site("restaurant"))
    assert got.planning_use == "no"
    assert ids(got.planning_use_lines) == ["zoning.existing_use", "zoning.change_of_use"]
    assert got.planning_use_lines[-1].text == LEGAL_BASIS["zoning.change_of_use/no"].text.format(
        a_use="a Restaurant"
    )
    assert got.planning_use_lines[-1].citations == ["app:lic-1"]


def test_planning_use_yes_when_the_records_show_another_use_or_a_use_is_added() -> None:
    got = changes(bar(), s=site("restaurant"))
    assert got.planning_use == "yes"
    assert got.planning_use_lines[-1].text == "Restaurant to Bar is a change of use."
    assert got.planning_use_lines[-1].code_section == "Planning Code § 102"
    added = changes(restaurant(entertainment_kind="place_of_entertainment"), s=site("restaurant"))
    assert added.planning_use == "yes"
    assert added.planning_use_lines[-1].text == (
        "Restaurant to Restaurant and Nighttime Entertainment is a change of use."
    )


def test_planning_use_from_the_description_says_as_described() -> None:
    same = changes(restaurant(existing_use_stated=["restaurant"]))
    assert same.planning_use == "no"
    assert same.planning_use_lines[-1].text == (
        "The last use of the space, as described, is Restaurant. The proposed use is Restaurant, so this is not "
        "a change of use."
    )
    other = changes(restaurant(existing_use_stated=["retail"]))
    assert other.planning_use == "yes"
    assert other.planning_use_lines[-1].text == (
        "Retail to Restaurant is a change of use, with the last use of the space as described."
    )
    # the records come first: what they show is not overridden by the description
    records = changes(restaurant(existing_use_stated=["retail"]), s=site("restaurant"))
    assert records.planning_use == "no" and "as described" not in records.planning_use_lines[-1].text


def test_a_description_that_agrees_with_the_records_adds_the_uses_a_licence_cannot_show() -> None:
    venue = {"entertainment_kind": "place_of_entertainment"}
    by_records = changes(restaurant(**venue), s=site("restaurant"))
    assert by_records.planning_use == "yes"  # the licence shows a Restaurant only
    stated = ["nighttime_entertainment", "restaurant"]
    both = changes(restaurant(existing_use_stated=stated, **venue), s=site("restaurant"))
    assert both.planning_use == "no"
    last = both.planning_use_lines[-1]
    assert last.text == (
        "The last use of the space, as described, is Restaurant and Nighttime Entertainment. The proposed use is "
        "Restaurant and Nighttime Entertainment, so this is not a change of use."
    )
    assert last.citations == ["app:lic-1"]
    # a description that disagrees with the records is not read
    other = changes(restaurant(existing_use_stated=["bar", "retail"]), s=site("restaurant"))
    assert other.planning_use == "no" and "as described" not in other.planning_use_lines[-1].text


def test_limited_restaurant_to_restaurant_is_a_change_of_use() -> None:
    got = changes(restaurant(existing_use_stated=["limited_restaurant"]))
    assert got.planning_use == "yes"
    assert got.planning_use_lines[-1].text.startswith("Limited Restaurant to Restaurant is a change of use")
    back = changes(concept("cafe", existing_use_stated=["restaurant"]))
    assert back.planning_use == "yes"


@pytest.mark.parametrize(
    ("c", "words"),
    [
        (restaurant(), "the description does not say what it was last used as"),
        (restaurant(existing_use_stated=["vacant"]), "The description says the space is vacant"),
        (concept("other"), "The rules have no Planning Code use for the concept"),
        (concept("food_truck"), "The rules have no Planning Code use for the concept"),
    ],
)
def test_planning_use_not_established(c: ConceptFacts, words: str) -> None:
    got = changes(c)
    assert got.planning_use == "not_established"
    assert words in got.planning_use_lines[-1].text


def test_a_vacant_space_with_its_last_use_stated_is_compared_by_that_use() -> None:
    got = changes(restaurant(existing_use_stated=["vacant", "retail"]))
    assert got.planning_use == "yes"
    assert got.planning_use_lines[-1].text.startswith("Retail to Restaurant")


# ---- change of use 2: the Building Code occupancy -------------------------------------------------------
def test_the_occupancy_rule_is_the_datas_on_the_rules_date() -> None:
    for on, edition in ((D(2022, 6, 1), "2019"), (D(2024, 6, 1), "2022"), (TODAY, "2025")):
        (rule,) = controls.citywide_rules("change_of_occupancy", on)
        first = changes(restaurant(), on=on).building_occupancy_lines[0]
        assert first.text == (
            "Building Code: a restaurant or bar is Assembly Group A-2, and a space for fewer than 50 people is "
            f"Group B ({edition} California Building Code)."
        )
        assert first.code_section == rule.source.section and "§ 303" in first.code_section
        assert first.source_url == rule.source.url


@pytest.mark.parametrize(
    ("kw", "group", "words"),
    [
        ({"occupants_under_50": True}, "B", "for fewer than 50 people, so the proposed occupancy is Group B"),
        (
            {"occupants_under_50": False},
            "A-2",
            "for 50 people or more, so the proposed occupancy is Group A-2",
        ),
        ({"seats": 50}, "A-2", "50 seats means at least 50 people, so the proposed occupancy is Group A-2"),
        ({"seats": 120}, "A-2", "A count of seats is not the occupant load"),
        (
            {"seats": 49},
            None,
            "fewer than 50 seats does not show whether the proposed occupancy is Group B or",
        ),
        ({"seats": 49}, None, "A count of seats is not the occupant load"),
        ({}, None, f"The description does not give {OCCUPANTS}, so the proposed occupancy group is not"),
        (
            {"occupants_under_50": True, "seats": 80},
            None,
            "but it also gives 80 seats, which means at least 50 people. The two disagree",
        ),  # fewer than 50 people against 80 seats: neither is read over the other (review of 2026-11-15)
    ],
)
def test_the_proposed_occupancy_group(kw: dict[str, Any], group: str | None, words: str) -> None:
    got = changes(restaurant(**kw))
    assert words in got.building_occupancy_lines[1].text
    # shown against a stated existing group: both shown, so the answer is yes or no
    for existing in ("B", "A-2", "group m"):
        answer = changes(restaurant(**kw), existing_group=existing).building_occupancy
        if group is None:
            assert answer == "not_established"
        else:
            assert answer == ("no" if existing.upper().replace("GROUP ", "") == group else "yes")


def test_the_existing_group_is_not_in_public_records_so_the_answer_is_not_established() -> None:
    got = changes(restaurant(occupants_under_50=False, existing_use_stated=["retail"]))
    assert got.building_occupancy == "not_established"
    assert got.building_occupancy_lines[-1].text == (
        "The existing occupancy group of the space is not in public records; only plans or an inspection show "
        "it. A change of occupancy is not established."
    )


def test_building_occupancy_no_when_the_same_use_continues_with_no_change_stated() -> None:
    none = {"changes_existing_business": "none"}
    for c, s in (
        (restaurant(**none), site("restaurant")),
        (restaurant(existing_use_stated=["restaurant"], **none), site()),
        (restaurant(square_feet=1500, floor_area_before_sqft=1500, **none), site("restaurant")),
    ):
        got = changes(c, s=s)
        assert (got.planning_use, got.building_occupancy) == ("no", "no")
        assert got.building_occupancy_lines[-1].text.startswith(
            "The same use continues and the description states no enlargement or other change to the business"
        )
    # silence is not "no change" (spec section 2; corrected: these three read "no" before the review)
    for c, s in (
        (restaurant(), site("restaurant")),
        (restaurant(existing_use_stated=["restaurant"]), site()),
        (restaurant(square_feet=1500, floor_area_before_sqft=1500), site("restaurant")),
    ):
        got = changes(c, s=s)
        assert (got.planning_use, got.building_occupancy) == ("no", "not_established")
    # a proposed group shown to be the assembly group: a small existing space could be Group B
    big = changes(restaurant(seats=200, **none), s=site("restaurant"))
    assert big.building_occupancy == "not_established"


@pytest.mark.parametrize(
    "kw",
    [
        {"changes_existing_business": "enlarge"},
        {"changes_existing_business": "intensify"},
        {"changes_existing_business": "enlarge_and_intensify"},
        {"square_feet": 2400, "floor_area_before_sqft": 1500},
    ],
)
def test_a_stated_change_to_the_business_leaves_the_occupancy_not_established(kw: dict[str, Any]) -> None:
    got = changes(restaurant(**kw), s=site("restaurant"))
    assert (got.planning_use, got.building_occupancy) == ("no", "not_established")


def test_building_occupancy_is_never_yes_without_both_groups_shown() -> None:
    sites = (site(), site("restaurant"), site("bar"))
    kws: tuple[dict[str, Any], ...] = (
        {},
        {"seats": 200},
        {"occupants_under_50": False},
        {"occupants_under_50": True},
        {"existing_use_stated": ["retail"], "occupants_under_50": False},
        {"existing_use_stated": ["laundromat"], "seats": 90},
        {"changes_existing_business": "enlarge", "seats": 90},
    )
    for s, kw, on in itertools.product(sites, kws, (D(2022, 3, 1), TODAY)):
        assert changes(restaurant(**kw), s=s, on=on).building_occupancy != "yes"
    # both shown and different: yes, and the line shows both groups
    got = changes(restaurant(occupants_under_50=False), existing_group="B")
    assert got.building_occupancy == "yes"
    assert got.building_occupancy_lines[-1].text == (
        "The existing occupancy is stated as Group B and the proposed occupancy is Group A-2: a change of "
        "occupancy."
    )
    # the existing group stated and the proposed one unknown: still not established
    assert changes(restaurant(seats=20), existing_group="B").building_occupancy == "not_established"


def test_a_concept_with_no_use_has_no_proposed_group() -> None:
    got = changes(concept("other", occupants_under_50=True), existing_group="B")
    assert got.building_occupancy == "not_established"
    assert "no Planning Code use" in got.building_occupancy_lines[1].text


# ---- change of use 3: neighbourhood notification --------------------------------------------------------
NEW_RESTAURANT = {"existing_use_stated": ["retail"]}
PRINCIPAL = (finding("new_use_control", "principal", citations=("zoning:NC-2",)),)
CONDITIONAL = (finding("new_use_control", "conditional", citations=("zoning:NC-2",)),)
BEFORE_248_23, FROM_248_23 = D(2024, 1, 13), D(2024, 1, 14)  # Ord. 248-23 took change of use out of § 311


@pytest.mark.parametrize("on", [FROM_248_23, D(2025, 6, 1), TODAY])
def test_from_14_january_2024_a_change_of_use_needs_no_neighbourhood_notice(on: dt.date) -> None:
    (rule,) = controls.citywide_rules("neighbourhood_notification", on)
    assert rule.extra["facts"]["change_of_use_triggers_section_311"] is False
    for c, s, found, district in (
        (restaurant(**NEW_RESTAURANT), site(), CONDITIONAL, "NC-2"),  # the use changes
        (restaurant(), site("restaurant"), (), "NC-2"),  # it does not
        (restaurant(), site(), (), "NCT-MISSION"),  # not established: the answer does not turn on it
        (restaurant(**NEW_RESTAURANT), site(), (), None),
        (restaurant(**NEW_RESTAURANT), site(), (), "RH-2"),
    ):
        got = changes(c, s=s, findings=found, district=district, on=on)
        assert got.neighbourhood_notice == "not_required"
        (line,) = got.neighbourhood_notice_lines
        assert line.text == (
            f"Under the Planning Code as in force on {tracts.plain_date(on.isoformat())}, a change of use does "
            "not by itself need neighbourhood notice: the change-of-use trigger has been out of Planning Code "
            "§ 311 since 14 January 2024 (Ord. 248-23, File No. 230446). Notice for work that enlarges a "
            "building, and for demolition or new construction, is a separate question the rules did not check."
        )
        assert line.code_section == rule.source.section == "Planning Code § 311(b)(1)-(4)"
        assert line.source_url == rule.source.url


@pytest.mark.parametrize("on", [D(2022, 6, 1), D(2023, 6, 2), D(2023, 6, 3), BEFORE_248_23])
@pytest.mark.parametrize(
    ("district", "found", "answer", "words"),
    [
        ("NC-2", PRINCIPAL, "not_required", "NC-2 is an NC district and Restaurant is principally permitted"),
        ("NCT-VALENCIA", PRINCIPAL, "not_required", "NCT-VALENCIA is an NCT district"),
        ("NCD-POLK", CONDITIONAL, "required", "in an NC district needed neighbourhood notice unless"),
        (
            "NCT-MISSION",
            CONDITIONAL,
            "required",
            "It is not principally permitted here, so notice was required",
        ),
        ("NC-3", (finding("new_use_control", "not_permitted"),), "required", "so notice was required"),
        ("NC-2", (), "not_established", "Whether it is principally permitted here is not decided"),
        ("NC-2", (finding("new_use_control", "not_decided"),), "not_established", "is not decided"),
        (
            "NC-2",
            (*PRINCIPAL, finding("special_district_use_control", "code_and_practice_differ")),
            "not_established",
            "is not decided",
        ),
        ("NC-2", (*PRINCIPAL, finding(T4, "conditional")), "required", "so notice was required"),
        ("RH-2", CONDITIONAL, "required", "in a Residential district needed neighbourhood notice, and"),
        ("RC-4", PRINCIPAL, "not_established", "limited commercial use or a limited corner commercial use"),
        ("MUR", PRINCIPAL, "not_established", "The rules do not decide land use categories"),
        ("UMU", CONDITIONAL, "not_established", "Eastern Neighborhoods Mixed Use district"),
        ("C-2", CONDITIONAL, "not_required", "C-2 is not one of them"),
        ("C-3-G", PRINCIPAL, "not_required", "C-3-G is not one of them"),
        ("CCB", PRINCIPAL, "not_established", "The rules do not place CCB inside or outside that list"),
        ("RH DTR", PRINCIPAL, "not_established", "The rules do not place RH DTR inside or outside"),
        (None, PRINCIPAL, "not_established", "No zoning district is on file"),
    ],
)
def test_before_14_january_2024_notice_follows_the_district_and_the_use(
    on: dt.date, district: str | None, found: tuple[TriggerFinding, ...], answer: str, words: str
) -> None:
    # not a chain: establishing a Formula Retail use also triggered notice before 2024-01-14 (see the review
    # tests), so the chain answer is stated here
    got = changes(
        restaurant(**NEW_RESTAURANT, formula_retail=False), findings=found, district=district, on=on
    )
    assert got.planning_use == "yes"
    assert got.neighbourhood_notice == answer
    (line,) = got.neighbourhood_notice_lines
    assert words in line.text
    assert tracts.plain_date(on.isoformat()) in line.text
    (rule,) = controls.citywide_rules("neighbourhood_notification", on)
    assert rule.extra["facts"]["change_of_use_triggers_section_311"] is True
    assert line.code_section is not None and "311" in line.code_section
    assert line.source_url == rule.source.url


def test_before_14_january_2024_the_notice_answer_follows_the_planning_answer() -> None:
    on = BEFORE_248_23
    same = changes(restaurant(), s=site("restaurant"), findings=CONDITIONAL, on=on)
    assert (same.planning_use, same.neighbourhood_notice) == ("no", "not_required")
    assert same.neighbourhood_notice_lines[0].text == (
        "The use does not change, so no neighbourhood notice was needed for a change of use on 13 January 2024."
    )
    unknown = changes(restaurant(), findings=CONDITIONAL, on=on)
    assert (unknown.planning_use, unknown.neighbourhood_notice) == ("not_established", "not_established")
    assert "Whether the use changes is not established" in unknown.neighbourhood_notice_lines[0].text


def test_a_restaurant_becoming_a_limited_restaurant_was_exempt_from_notice() -> None:
    got = changes(
        concept("cafe", existing_use_stated=["restaurant"], formula_retail=False),
        findings=CONDITIONAL,
        on=BEFORE_248_23,
    )
    assert (got.planning_use, got.neighbourhood_notice) == ("yes", "not_required")
    assert got.neighbourhood_notice_lines[0].code_section == "Planning Code § 311(b)(1)(A)"
    # the other way round is a change to a listed use like any other
    back = changes(
        restaurant(existing_use_stated=["limited_restaurant"]), findings=CONDITIONAL, on=BEFORE_248_23
    )
    assert back.neighbourhood_notice == "required"


def test_notice_names_the_use_that_is_added_and_cites_the_findings_it_read() -> None:
    c = restaurant(entertainment_kind="place_of_entertainment")
    found = (finding("nighttime_entertainment", "conditional", citations=("zoning:NC-2", "overlay:x")),)
    got = changes(c, s=site("restaurant"), findings=found, on=BEFORE_248_23)
    (line,) = got.neighbourhood_notice_lines
    assert got.neighbourhood_notice == "required"
    assert "a change of use to Nighttime Entertainment in an NC district" in line.text
    assert line.citations == ["overlay:x", "zoning:NC-2"]


def test_a_date_before_the_data_starts_is_not_established() -> None:
    got = changes(restaurant(**NEW_RESTAURANT), findings=PRINCIPAL, on=D(2021, 6, 1))
    assert got.neighbourhood_notice == "not_established"
    assert got.neighbourhood_notice_lines[0].text.startswith(
        "No version of the neighbourhood notification rule"
    )
    assert got.building_occupancy_lines[0].text.startswith("No version of the Building Code occupancy rule")


def test_notice_district_classes() -> None:
    placed = {
        "NC-1": "NC",
        "NC-S": "NC",
        "NCD-LOWER POLK STREET": "NC",
        "NCT-3": "NCT",
        "NCT-24TH-MISSION": "NCT",
        "RH-2": "Residential",
        "RM-3": "Residential",
        "RC-4": "Residential",
        "RTO": "Residential",
        "MUR": "Eastern Neighborhoods Mixed Use",
        "UMU": "Eastern Neighborhoods Mixed Use",
        "C-2": "outside",
        "C-3-G": "outside",
    }
    for code, name in placed.items():
        assert rows.notice_district_class(code) == name, code
    for code in ("CCB", "CVR", "CRNC", "RH DTR", "PDR-1-G", "", None):
        assert rows.notice_district_class(code) is None, code
    # every district of the dated data is either placed or left "not placed": none is guessed
    for code in controls.districts():
        assert rows.notice_district_class(code) in {*placed.values(), None}
    (rule,) = controls.citywide_rules("neighbourhood_notification", BEFORE_248_23)
    assert {name for _, name in rows.NOTICE_DISTRICT_CLASSES} == set(rule.extra["facts"]["districts"])


# ---- the building row -----------------------------------------------------------------------------------
def building(
    c: ConceptFacts,
    *,
    s: SiteFacts | None = None,
    prohibited: bool = False,
    on: dt.date = TODAY,
    existing_group: str | None = None,
) -> RowDetermination:
    answers = changes(c, s=s, on=on, existing_group=existing_group)
    return rows.building_row(
        answers, c, zoning_prohibits_use=prohibited, rules_date=on, existing_occupancy_group=existing_group
    )


def test_b1_a_change_of_use_is_further_review() -> None:
    row = building(restaurant(**NEW_RESTAURANT))
    assert (row.area, row.status) == ("building_change_of_use", "further_review")
    assert row.approval == APPROVALS["building_change_of_use/yes"] == "Building permit with change of use"
    assert row.agency == AGENCIES["building_change_of_use"]
    assert row.basis[-1].text == LEGAL_BASIS["building.status/B1"].text.format(status="further review")
    assert row.missing_inputs == []
    assert row.basis[0].text.startswith("No active ABC licence")  # the answers' own lines come first


def test_b1_a_change_of_occupancy_alone_is_further_review() -> None:
    row = building(restaurant(occupants_under_50=False), s=site("restaurant"), existing_group="B")
    assert row.status == "further_review"
    assert row.approval == "Building permit with change of occupancy"
    last = row.basis[-1]
    assert (
        last.text
        == "A change of occupancy needs a building permit, secured before the change is made: further review."
    )
    assert last.code_section is not None and "106A.1.12" in last.code_section


def test_b2_no_change_of_use_and_no_change_of_occupancy_is_allowed() -> None:
    row = building(restaurant(changes_existing_business="none"), s=site("restaurant"))
    assert row.status == "allowed" and row.missing_inputs == []
    assert row.approval == APPROVALS["building_change_of_use"] == "Building permit"
    assert row.basis[-1].text == LEGAL_BASIS["building.status/B2"].text.format(status="allowed")
    stated = building(
        restaurant(occupants_under_50=True, changes_existing_business="none"),
        s=site("restaurant"),
        existing_group="B",
    )
    assert stated.status == "allowed"


def test_b0_a_prohibited_use_that_changes_the_planning_use_is_not_permitted() -> None:
    row = building(restaurant(**NEW_RESTAURANT), prohibited=True)
    assert row.status == "not_permitted"
    assert row.basis[-1].text == LEGAL_BASIS["building.status/B0"].text.format(
        use="Restaurant", status="not permitted"
    )
    assert row.basis[-1].code_section == "Planning Code § 175(a)"
    assert row.referral_steps == []
    # not where the planning use stays the same; where the change is not established the prohibited use is
    # barred too (the decision of 2026-11-12: the use triggers never read a use that continues)
    none = restaurant(changes_existing_business="none")
    assert building(none, s=site("restaurant"), prohibited=True).status == "allowed"
    unknown = building(restaurant(), prohibited=True)
    assert (unknown.status, unknown.missing_inputs, unknown.approval) == (
        "not_permitted",
        [],
        "Building permit",
    )
    assert unknown.basis[-1].text == row.basis[-1].text


@pytest.mark.parametrize(
    ("c", "s", "missing"),
    [
        (restaurant(), site(), [LAST_USE, OCCUPANTS, rows.EXISTING_GROUP_PHRASE]),
        (restaurant(seats=30), site(), [LAST_USE, OCCUPANTS, rows.EXISTING_GROUP_PHRASE]),
        (restaurant(seats=80), site(), [LAST_USE, rows.EXISTING_GROUP_PHRASE]),
        (restaurant(occupants_under_50=True), site(), [LAST_USE, rows.EXISTING_GROUP_PHRASE]),
        (
            restaurant(existing_use_stated=["vacant"]),
            site(),
            [LAST_USE, OCCUPANTS, rows.EXISTING_GROUP_PHRASE],
        ),
        # the same use continues, but the business is enlarged: only the occupancy is open
        (
            restaurant(changes_existing_business="enlarge"),
            site("restaurant"),
            [OCCUPANTS, rows.EXISTING_GROUP_PHRASE],
        ),
        (
            restaurant(changes_existing_business="enlarge", occupants_under_50=False),
            site("restaurant"),
            [rows.EXISTING_GROUP_PHRASE],
        ),
        (concept("other"), site(), [MISSING_PHRASES["planning_uses"], rows.EXISTING_GROUP_PHRASE]),
    ],
)
def test_b3_names_what_is_missing(c: ConceptFacts, s: SiteFacts, missing: list[str]) -> None:
    row = building(c, s=s)
    assert row.status == "insufficient_information"
    assert row.missing_inputs == missing
    assert row.approval == "Building permit"
    last = row.basis[-1]
    assert last.rule_id == "building.status" and last.text.endswith(": insufficient information.")
    for phrase in missing:
        assert phrase in last.text
    assert rows.EXISTING_GROUP_PHRASE == (
        "the existing occupancy group of the space, which only plans or an inspection show"
    )


def test_b3_with_the_existing_group_stated_names_only_the_occupant_count() -> None:
    row = building(restaurant(changes_existing_business="none"), s=site("restaurant"), existing_group="B")
    assert row.status == "allowed"  # the same use continues with no change stated
    row = building(restaurant(changes_existing_business="enlarge"), s=site("restaurant"), existing_group="B")
    assert row.status == "insufficient_information" and row.missing_inputs == [OCCUPANTS]


def test_the_building_rows_referral_step_is_the_planning_review() -> None:
    before = building(restaurant(**NEW_RESTAURANT), on=D(2025, 10, 5)).referral_steps
    after = building(restaurant(**NEW_RESTAURANT), on=D(2025, 10, 6)).referral_steps
    assert len(before) == len(after) == 1
    assert before[0].text == (
        "Building permit application (and any other City permit or licence authorizing a use): this application "
        "is sent to the Planning Department for review (Planning Code § 175(a))."
    )
    assert after[0].text == before[0].text + (
        " It has applied in this form since 6 October 2025 (Ord. 170-25, File No. 240803)."
    )
    assert "That step has ended" not in after[0].text  # replaced by its next version, not ended


# ---- referral steps -------------------------------------------------------------------------------------
def steps_of(permit: str, on: dt.date) -> dict[str, RuleLine]:
    """The referral lines of one entertainment permit on a date, by agency."""
    found = [line for line in rows._steps(rows.ENTERTAINMENT_GROUP, (permit,), on)]
    out: dict[str, RuleLine] = {}
    for line in found:
        assert line.text.startswith(f"{APPLICATION[permit]}: "), line.text
        agency = next(
            a
            for a in (
                "Police Department",
                "Planning Department",
                "Department of Building Inspection",
                "Department of Public Health",
                "Fire Department",
            )
            if f"sent to the {a}" in line.text
        )
        assert agency not in out, "one line for each agency"
        out[agency] = line
    return out


def in_force(line: RuleLine) -> bool:
    return "this application is sent to" in line.text and "That step has ended" not in line.text


def ended(line: RuleLine, day: str, ordinance: str) -> bool:
    return (
        f"until {day} this application was also sent to" in line.text
        and f"ended by {ordinance}" in line.text
        and line.text.endswith("That step has ended. The permit is still required.")
    )


ORD_118 = "Ord. 118-25, File No. 250537"
ORD_250 = "Ord. 250-23, File No. 230861"
POLICE, PLANNING = "Police Department", "Planning Department"
DBI, DPH, FIRE = "Department of Building Inspection", "Department of Public Health", "Fire Department"


def test_the_bundled_data_carries_the_referral_lists() -> None:
    assert set(controls.citywide_entry_groups()) == {rows.ENTERTAINMENT_GROUP, rows.OTHER_GROUP}
    record = controls.citywide_record("ordinance_118_25")
    assert record["effective"] == FROM_118_25.isoformat()


@pytest.mark.parametrize("on", [D(2022, 6, 1), BEFORE_250_23, FROM_250_23, BEFORE_118_25, FROM_118_25, TODAY])
def test_all_four_entertainment_permits_are_approvals_on_every_date(on: dt.date) -> None:
    approvals = rows.entertainment_approvals(on)
    assert set(FOUR_PERMITS) <= set(approvals)
    assert len(approvals) == len(set(approvals))
    # the approvals that did end are gone from the list on the day they ended, and only then
    assert ("dance_hall" in approvals) is (on < FROM_118_25)
    assert ("ball_or_ring_throwing" in approvals) is (on < FROM_118_25)
    assert ("masked_ball" in approvals) is (on < FROM_250_23)
    for permit in FOUR_PERMITS:
        assert steps_of(permit, on), permit  # and each still has steps inside it


def test_place_of_entertainment_referrals_either_side_of_both_ordinances() -> None:
    permit = rows.PLACE_OF_ENTERTAINMENT
    for on in (BEFORE_250_23, FROM_250_23, BEFORE_118_25):
        got = steps_of(permit, on)
        assert list(got) == [POLICE, PLANNING, DBI, DPH, FIRE]
        assert all(in_force(line) for line in got.values())
    widened = " It has applied in this form since 14 January 2024 (Ord. 250-23, File No. 230861)."
    assert not steps_of(permit, BEFORE_250_23)[DBI].text.endswith(widened)
    assert steps_of(permit, FROM_250_23)[DBI].text.endswith(widened)
    assert steps_of(permit, BEFORE_118_25)[DBI].text.endswith(widened)
    after = steps_of(permit, FROM_118_25)
    assert list(after) == [POLICE, PLANNING, DBI, DPH, FIRE]
    assert ended(after[DBI], "16 August 2025", ORD_118)
    assert after[DBI].text == (
        "Place of Entertainment Permit application: until 16 August 2025 this application was also sent to the "
        "Department of Building Inspection (Police Code § 1060.2(b)(3); ended by Ord. 118-25, File No. 250537). "
        "That step has ended. The permit is still required."
    )
    assert all(in_force(after[a]) for a in (POLICE, PLANNING, DPH, FIRE))
    assert after[PLANNING].text == (
        "Place of Entertainment Permit application: this application is sent to the Planning Department for "
        "review (Police Code § 1060.2(b)(2))."
    )
    assert after[PLANNING].code_section == "Police Code § 1060.2(b)(2)"
    assert after[PLANNING].source_url


def test_limited_live_performance_referrals_either_side_of_both_ordinances() -> None:
    permit = rows.LIMITED_LIVE_PERFORMANCE
    for on in (BEFORE_250_23, FROM_250_23, BEFORE_118_25):
        got = steps_of(permit, on)
        assert list(got) == [POLICE, PLANNING] and all(in_force(line) for line in got.values())
    after = steps_of(permit, FROM_118_25)
    assert in_force(after[POLICE]) and ended(after[PLANNING], "16 August 2025", ORD_118)
    assert "Police Code § 1060.2.1(b)" in after[PLANNING].text


def test_fixed_place_outdoor_amplified_sound_referrals_either_side_of_both_ordinances() -> None:
    permit = rows.FIXED_PLACE_OUTDOOR_AMPLIFIED_SOUND
    first = steps_of(permit, BEFORE_250_23)
    assert list(first) == [POLICE, PLANNING, DPH] and all(in_force(line) for line in first.values())
    for on in (FROM_250_23, BEFORE_118_25):
        got = steps_of(permit, on)
        assert in_force(got[POLICE]) and in_force(got[PLANNING])
        assert ended(got[DPH], "13 January 2024", ORD_250)
    after = steps_of(permit, FROM_118_25)
    assert in_force(after[POLICE])
    assert ended(after[PLANNING], "16 August 2025", ORD_118)
    assert ended(after[DPH], "13 January 2024", ORD_250)


def test_extended_hours_premises_referrals_either_side_of_both_ordinances() -> None:
    permit = rows.EXTENDED_HOURS_PREMISES
    for on in (BEFORE_250_23, FROM_250_23, BEFORE_118_25):
        got = steps_of(permit, on)
        assert list(got) == [POLICE, PLANNING, DBI, DPH, FIRE]
        assert all(in_force(line) for line in got.values())
        assert not any("in this form since" in line.text for line in got.values())
    after = steps_of(permit, FROM_118_25)
    assert in_force(after[POLICE]) and in_force(after[PLANNING])
    assert ended(after[DBI], "16 August 2025", ORD_118)
    # narrowed, not removed: still a step, in its new form
    narrowed = " It has applied in this form since 17 August 2025 (Ord. 118-25, File No. 250537)."
    for agency in (DPH, FIRE):
        assert in_force(after[agency]) and after[agency].text.endswith(narrowed)


@pytest.mark.parametrize("on", [D(2022, 6, 1), BEFORE_250_23, FROM_250_23, BEFORE_118_25, FROM_118_25, TODAY])
def test_an_approval_that_ended_is_never_listed_as_a_referral_step(on: dt.date) -> None:
    every = [
        line
        for area in ("zoning_use", "alcohol", "entertainment", "health", "building_change_of_use", "outdoor")
        for c in (bar(live_entertainment=True, closes_after_2am=True, dancing=True), restaurant())
        for line in rows.referral_steps(area, c, rules_date=on, public_convenience=True)  # type: ignore[arg-type]
    ]
    assert every
    for line in every:
        assert line.rule_id == "referral.step"
        assert not any(word in line.text.lower() for word in ("dance", "masked ball", "ring throwing"))
        assert "approval" not in line.text.lower()
        assert line.code_section and line.source_url
    # asked for by name, a permit that is no longer an approval has no steps either
    assert rows._steps(rows.ENTERTAINMENT_GROUP, ("dance_hall",), on) == []


def test_referral_steps_by_row() -> None:
    c = restaurant()
    assert rows.referral_steps("zoning_use", c, rules_date=TODAY) == []
    assert rows.referral_steps("outdoor", c, rules_date=TODAY) == []
    (health,) = rows.referral_steps("health", c, rules_date=TODAY)
    assert "sent to the Planning Department for review" in health.text
    assert health.text.startswith("Department of Public Health permit to operate")
    assert len(rows.referral_steps("alcohol", c, rules_date=TODAY)) == 2
    assert len(rows.referral_steps("alcohol", c, rules_date=TODAY, public_convenience=True)) == 4
    assert len(rows.referral_steps("building_change_of_use", c, rules_date=TODAY)) == 1


def test_missing_referral_data_gives_an_empty_list_never_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    c = bar(live_entertainment=True, closes_after_2am=True)
    with_data = rows.entertainment_row(c, [], rules_date=TODAY, zoning_prohibits_use=False)
    assert with_data.referral_steps

    def raises(*args: Any, **kwargs: Any) -> Any:
        raise KeyError("no such group")

    for missing in (lambda *a, **k: (), raises):
        monkeypatch.setattr(controls, "citywide_entries", missing)
        for area in ("zoning_use", "alcohol", "entertainment", "health", "building_change_of_use", "outdoor"):
            assert rows.referral_steps(area, c, rules_date=TODAY, public_convenience=True) == []  # type: ignore[arg-type]
        assert rows.entertainment_approvals(TODAY) == ()
        row = rows.entertainment_row(c, [], rules_date=TODAY, zoning_prohibits_use=False)
        assert row.referral_steps == []
        # a referral step never sets or changes a status, a name or a rule line
        assert (row.status, row.approval, row.basis) == (
            with_data.status,
            with_data.approval,
            with_data.basis,
        )
        assert alcohol(bar(), tract=OVER).referral_steps == []
        assert alcohol(bar(), tract=OVER).status == "further_review"
        assert building(restaurant(**NEW_RESTAURANT)).referral_steps == []


def test_a_group_with_no_entries_in_the_data_file_gives_an_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = controls.plain(controls._data())
    for key in (rows.ENTERTAINMENT_GROUP, rows.OTHER_GROUP, "ordinance_118_25", "ordinance_250_23"):
        raw["citywide"].pop(key)
    monkeypatch.setattr(controls, "_data", lambda: raw)  # the data file as it was before the referrals
    c = bar(live_entertainment=True, closes_after_2am=True)
    assert rows.referral_steps("entertainment", c, rules_date=TODAY) == []
    assert rows.referral_steps("alcohol", c, rules_date=TODAY) == []
    row = rows.entertainment_row(c, [], rules_date=TODAY, zoning_prohibits_use=False)
    assert row.status == "further_review" and row.referral_steps == []


# ---- the entertainment row ------------------------------------------------------------------------------
def show_row(
    c: ConceptFacts,
    *,
    on: dt.date = TODAY,
    prohibited: bool = False,
    findings: tuple[TriggerFinding, ...] = (),
) -> RowDetermination:
    return rows.entertainment_row(c, list(findings), rules_date=on, zoning_prohibits_use=prohibited)


def test_e1_entertainment_closing_by_2am() -> None:
    row = show_row(bar(live_entertainment=True, closing_hour="01:00"))
    assert (row.area, row.status, row.status_note) == ("entertainment", "further_review", None)
    assert row.approval == APPROVALS["entertainment"]
    assert row.agency == AGENCIES["entertainment"]
    assert texts(row.basis) == [LEGAL_BASIS["entertainment.status/E1"].text.format(status="further review")]
    applications = {line.text.split(":")[0] for line in row.referral_steps}
    assert applications == {APPLICATION[p] for p in rows.GENERAL_ENTERTAINMENT_PERMITS}


def test_e2_closing_after_2am_with_no_entertainment() -> None:
    for c in (bar(closing_hour="04:00"), bar(closes_after_2am=True, entertainment_kind="none")):
        row = show_row(c)
        assert row.status == "further_review"
        assert row.approval == APPROVALS["entertainment/extended_hours"] == "Extended-Hours Premises permit"
        assert row.basis[0].text == LEGAL_BASIS["entertainment.status/E2"].text.format(
            status="further review"
        )
        assert {line.text.split(":")[0] for line in row.referral_steps} == {
            APPLICATION[rows.EXTENDED_HOURS_PREMISES]
        }


def test_e3_entertainment_and_closing_after_2am() -> None:
    row = show_row(bar(dancing=True, closes_after_2am=True))
    assert row.status == "further_review"
    assert row.approval == APPROVALS["entertainment/with_extended_hours"]
    assert row.basis[0].text == LEGAL_BASIS["entertainment.status/E3"].text.format(status="further review")
    assert {line.text.split(":")[0] for line in row.referral_steps} == set(APPLICATION.values())


def test_e0_a_prohibited_use_is_not_permitted() -> None:
    row = show_row(bar(live_entertainment=True), prohibited=True)
    assert row.status == "not_permitted" and row.referral_steps == []
    assert texts(row.basis) == [
        LEGAL_BASIS["entertainment.status/E0"].text.format(use="Bar", status="not permitted")
    ]
    assert row.basis[0].code_section == "Planning Code § 175(a)"
    # when it is the entertainment use that the findings bar, the line names that use and cites them
    barred = finding("nighttime_entertainment", "not_permitted", citations=("zoning:NC-1",))
    c = restaurant(entertainment_kind="place_of_entertainment")
    row = show_row(c, prohibited=True, findings=(barred,))
    assert row.basis[0].text.startswith(
        "Zoning does not permit a new Nighttime Entertainment at this address"
    )
    assert row.basis[0].citations == ["zoning:NC-1"]
    assert row.approval == "Place of Entertainment permit"


@pytest.mark.parametrize(
    ("kw", "approval", "permits"),
    [
        (
            {"entertainment_kind": "limited_live_performance", "closing_hour": "23:00"},
            "Limited Live Performance permit",
            {rows.LIMITED_LIVE_PERFORMANCE},
        ),
        (
            {"entertainment_kind": "place_of_entertainment", "closing_hour": "01:30"},
            "Place of Entertainment permit",
            {rows.PLACE_OF_ENTERTAINMENT},
        ),
        (
            {"entertainment_kind": "place_of_entertainment", "closing_hour": "04:00"},
            "Place of Entertainment permit, and Extended-Hours Premises permit",
            {rows.PLACE_OF_ENTERTAINMENT, rows.EXTENDED_HOURS_PREMISES},
        ),
        (
            {"entertainment_kind": "limited_live_performance", "closes_after_2am": True},
            "Limited Live Performance permit, and Extended-Hours Premises permit",
            {rows.LIMITED_LIVE_PERFORMANCE, rows.EXTENDED_HOURS_PREMISES},
        ),
    ],
)
def test_the_approval_is_named_for_the_permit_the_facts_point_to(
    kw: dict[str, Any], approval: str, permits: set[str]
) -> None:
    c = bar(**kw)
    row = show_row(c)
    assert row.status == "further_review" and row.approval == approval == rows.entertainment_approval(c)
    first = row.basis[0]
    name = approval.split(",")[0]
    assert first.rule_id == "entertainment.permit"
    assert (
        first.text
        == f"The description gives the kind of entertainment, so the permit looked up is the {name}."
    )
    assert first.code_section is not None and first.code_section.startswith("Police Code § 1060.1(a)")
    assert first.source_url
    assert row.basis[1].rule_id == "entertainment.status"
    assert {line.text.split(":")[0] for line in row.referral_steps} == {APPLICATION[p] for p in permits}


def test_the_general_name_is_kept_where_the_kind_is_not_stated() -> None:
    assert show_row(bar(live_entertainment=True)).approval == APPROVALS["entertainment"]
    assert (
        show_row(bar(amplified_sound=True, entertainment_kind="none")).approval == APPROVALS["entertainment"]
    )
    assert show_row(bar()).approval == APPROVALS["entertainment"]  # nothing stated: as v1 reads it


def test_a_missing_closing_time_is_not_read_as_by_2am() -> None:
    row = show_row(bar(live_entertainment=True))
    assert ids(row.basis) == ["entertainment.status", "entertainment.closing"]
    assert row.basis[-1].text == (
        "The description does not give the closing time. Staying open to patrons between 2 a.m. and 6 a.m. "
        "would also need an Extended-Hours Premises permit."
    )
    assert row.status == "further_review" and row.missing_inputs == []
    for stated in ({"closing_hour": "23:30"}, {"closes_after_midnight": True}, {"closes_after_2am": True}):
        assert "entertainment.closing" not in ids(show_row(bar(live_entertainment=True, **stated)).basis)


@pytest.mark.parametrize("on", [BEFORE_250_23, FROM_250_23, BEFORE_118_25, FROM_118_25, TODAY])
def test_the_entertainment_row_is_the_same_approval_either_side_of_both_ordinances(on: dt.date) -> None:
    for kw, approval in (
        ({"entertainment_kind": "place_of_entertainment"}, "Place of Entertainment permit"),
        ({"entertainment_kind": "limited_live_performance"}, "Limited Live Performance permit"),
        ({"amplified_sound": True}, APPROVALS["entertainment"]),
        ({"closes_after_2am": True}, "Extended-Hours Premises permit"),
    ):
        row = show_row(bar(**kw), on=on)
        assert (row.status, row.approval) == ("further_review", approval)
        assert row.referral_steps  # the steps changed; the approval did not


# ---- determinism ----------------------------------------------------------------------------------------
def test_the_same_inputs_in_any_order_give_byte_identical_output() -> None:
    found = (
        MISSION_CONDITIONAL,
        finding("new_use_control", "conditional", citations=("zoning:NCT-MISSION",)),
        finding("nighttime_entertainment", "principal", citations=("zoning:NCT-MISSION", "overlay:a")),
        finding(T4, "conditional", section="Planning Code § 249.60(c)(3)", text="Another Mission line."),
    )

    def run(order: tuple[TriggerFinding, ...], stated: list[str], on: dt.date) -> str:
        c = bar(
            existing_use_stated=stated,
            entertainment_kind="place_of_entertainment",
            closes_after_2am=True,
            seats=80,
        )
        s = site()
        answers = rows.change_answers(c, s, list(order), "NCT-MISSION", rules_date=on)
        made = [
            rows.alcohol_row(c, s, list(order), zoning_prohibits_use=False, tract=OVER, rules_date=on),
            answers,
            rows.building_row(answers, c, zoning_prohibits_use=False, rules_date=on),
            rows.entertainment_row(c, list(order), rules_date=on, zoning_prohibits_use=False),
        ]
        steps = rows.referral_steps("entertainment", c, rules_date=on)
        return "\n".join([*(dump(m) for m in made), *(dump(line) for line in steps)])

    for on in (D(2023, 3, 1), TODAY):
        first = run(found, ["retail", "restaurant"], on)
        assert first == run(found, ["retail", "restaurant"], on)  # twice
        for order in itertools.permutations(found):
            assert run(order, ["restaurant", "retail"], on) == first
