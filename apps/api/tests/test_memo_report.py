"""Report format 3, the pure parts: required areas, the rows and the overall line as the rules set them, display
labels, source notes and days to decision.

Rule table v2: a row's status note, referral steps and missing inputs reach the report unchanged; the plain-text
report prints them; and days from filing are always given for one outcome, never as one figure across
outcomes."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from precedent.models import Application

from app.agents.memo_runner import required_areas
from app.memo.pathway import entitlement_path, overall_line
from app.memo.report import (
    NO_FIGURE,
    REPORT_TEXT,
    SOURCE_NOTES,
    TIMING_GROUPS,
    CaseTime,
    SiteRecord,
    case_outcome,
    case_time,
    change_answer_rows,
    comparable_source,
    comparable_time,
    days_to_decision,
    decision_times,
    determination_citations,
    group_time_line,
    iso_date,
    most_severe,
    not_given_text,
    pathway_lines,
    record_sources,
    row_headline,
    row_rule_lines,
    rule_citations,
    rule_line_text,
    rules_overall,
    rules_rows,
    site_history_entry,
    source_label,
    source_notes_for,
    status_label,
    status_with_note,
    timing_cell,
    trigger_differs_texts,
    trigger_headline,
    trigger_lines,
    unprinted_lines,
)
from app.models.memo import (
    STATUS_DEFINITIONS,
    STATUS_SEVERITY,
    ComparableCase,
    Determinations,
    OpenQuestion,
    Pathway,
    RowDetermination,
    RuleLine,
)
from app.models.profile import BusinessProfile
from tests.memo_fakes import case_determinations

CITATIONS = {"zoning:NC-2", "overlay:1", "app:1", "app:2", "stat:density", "catalog:x"}


# ---- required_areas ------------------------------------------------------------------------------
def test_required_areas_always_has_zoning_health_and_building() -> None:
    cafe = BusinessProfile(business_type="cafe").normalized()
    assert required_areas(cafe) == ["zoning_use", "health", "building_change_of_use"]


@pytest.mark.parametrize(
    ("fields", "extra"),
    [
        ({"serves_alcohol": True, "alcohol_type": "beer_wine"}, ["alcohol"]),
        ({"live_entertainment": True}, ["entertainment"]),
        ({"amplified_sound": True}, ["entertainment"]),  # a DJ
        ({"dancing": True}, ["entertainment"]),
        # open after 2 a.m.: the Extended-Hours Premises permit, with or without entertainment
        ({"closes_after_midnight": True, "closes_after_2am": True}, ["entertainment"]),
        ({"closes_after_2am": True, "live_entertainment": True}, ["entertainment"]),
        ({"outdoor_seating": True}, ["outdoor"]),  # patio or rooftop
        ({"sidewalk_or_parklet": True}, ["outdoor"]),
        (
            {"plays_recorded_music": True, "closes_after_midnight": True},
            [],
        ),  # background music is not a permit
    ],
)
def test_required_areas_follow_the_concept(fields: dict[str, Any], extra: list[str]) -> None:
    profile = BusinessProfile(business_type="restaurant", **fields).normalized()
    assert set(required_areas(profile)) == {"zoning_use", "health", "building_change_of_use", *extra}


def test_required_areas_are_in_report_order() -> None:
    everything = BusinessProfile(
        business_type="bar",
        serves_alcohol=True,
        alcohol_type="full_liquor",
        dancing=True,
        sidewalk_or_parklet=True,
    ).normalized()
    assert required_areas(everything) == [
        "zoning_use",
        "alcohol",
        "entertainment",
        "health",
        "building_change_of_use",
        "outdoor",
    ]


def rule_line(rule_id: str, text: str, *citations: str, code_section: str | None = None) -> RuleLine:
    return RuleLine(rule_id=rule_id, text=text, code_section=code_section, citations=list(citations))


CHANGE_OF_USE_LINE = "Bar to Restaurant is a change of use."
RULE_QUESTION = OpenQuestion(
    question="Is a Restaurant closing after 2 a.m. permitted at 1 Example St?",
    needs="agency_answer",
    ask="A written answer from San Francisco Planning, such as a Letter of Determination",
)


def make_determinations(**over: Any) -> Determinations:
    """What the rules decided for the report `risk_payload` explains, written out by hand. The policy under
    test only carries it into the report; `tests/test_pathway.py` covers how the rules reach it."""
    pathway_lines = [
        rule_line("zoning.use", "The concept is looked up as a Restaurant (Planning Code § 102)."),
        rule_line(
            "zoning.use_control",
            "Zoning district NC-2: a Restaurant is principally permitted (Planning Code § 711).",
            "zoning:NC-2",
            code_section="Planning Code § 711",
        ),
        rule_line(
            "zoning.existing_use", "An active ABC Type 48 licence is on file at 1 Example St.", "app:2"
        ),
        rule_line("zoning.change_of_use", CHANGE_OF_USE_LINE, "app:2"),
    ]
    rows = [
        RowDetermination(
            area="zoning_use",
            approval="Principally permitted use: no Conditional Use Authorization for the use itself",
            agency="San Francisco Planning",
            status="allowed",
            basis=[
                *pathway_lines,
                rule_line(
                    "zoning.status", "A new Restaurant here is principally permitted: allowed.", "zoning:NC-2"
                ),
            ],
        ),
        RowDetermination(
            area="alcohol",
            approval="ABC licence, Type 41 (on-sale beer and wine, eating place)",
            agency="California Department of Alcoholic Beverage Control",
            status="potential_blocker",
            basis=[
                rule_line("alcohol.licence_rule", "The district limits new licences.", "overlay:1"),
                rule_line("alcohol.status", "The licence can be used here only if that condition is met."),
            ],
        ),
        RowDetermination(
            area="entertainment",
            approval="Place of Entertainment, Limited Live Performance or Fixed Place Outdoor Amplified Sound permit",
            agency="San Francisco Entertainment Commission",
            status="further_review",
            basis=[rule_line("entertainment.status", "Live entertainment needs a permit: further review.")],
        ),
        RowDetermination(
            area="health",
            approval="Health permit to operate",
            agency="San Francisco Department of Public Health",
            status="allowed",
            basis=[rule_line("health.status", "A food or drink business needs a health permit: allowed.")],
        ),
        RowDetermination(
            area="building_change_of_use",
            approval="Building permit with change of use",
            agency="San Francisco Department of Building Inspection",
            status="further_review",
            basis=[
                rule_line(
                    "building.change_of_use", f"Taken from the zoning row: {CHANGE_OF_USE_LINE}", "app:2"
                ),
                rule_line("building.status", "A change of use needs a building permit: further review."),
            ],
        ),
    ]
    values: dict[str, Any] = {
        "pathway": Pathway(
            use="restaurant",
            use_label="Restaurant",
            district="NC-2",
            permission="principal",
            permission_label="Permitted",
            existing_use="bar",
            change_of_use="yes",
            change_of_use_label="Change of use",
            lines=pathway_lines,
            notes=[rule_line("zoning.note", "Note on file, not evaluated by the rules: x", "overlay:1")],
        ),
        "rows": rows,
        "overall_status": "potential_blocker",
        "overall_line": (
            "Of the 5 approvals this concept needs: 1 potential blocker (alcohol licence), 2 further review "
            "(entertainment permit, building permit and change of use), 2 allowed (zoning and use, health permit)."
        ),
        "entitlement_path": entitlement_path(rows),
        "open_questions": [RULE_QUESTION],
    }
    return Determinations.model_validate({**values, **over})


DETERMINATIONS = make_determinations()


def test_the_building_row_carries_the_zoning_rows_change_of_use_answer() -> None:
    rows = rules_rows(DETERMINATIONS)
    zoning, building = rows[0], rows[4]
    (answer,) = [line for line in zoning.basis if line.rule_id == "zoning.change_of_use"]
    (taken,) = [line for line in building.basis if line.rule_id == "building.change_of_use"]
    assert taken.text == f"Taken from the zoning row: {answer.text}" and taken.citations == answer.citations


def test_overall_citations_are_what_the_rows_rule_lines_cite() -> None:
    overall = rules_overall(DETERMINATIONS)
    # in row order, each id once; the pathway note's record is not a row's rule line
    assert overall.citations == ["zoning:NC-2", "app:2", "overlay:1"]
    assert (overall.status, overall.line) == (DETERMINATIONS.overall_status, DETERMINATIONS.overall_line)
    assert rule_citations(DETERMINATIONS.rows) == overall.citations
    assert determination_citations(DETERMINATIONS) == ["zoning:NC-2", "app:2", "overlay:1"]
    bare = make_determinations(
        rows=[
            RowDetermination(
                area="health",
                approval="Health permit to operate",
                agency="San Francisco Department of Public Health",
                status="allowed",
                basis=[
                    rule_line("health.status", "A food or drink business needs a health permit: allowed.")
                ],
            )
        ]
    )
    assert rules_overall(bare).citations == []
    # a record only a pathway note cites still reaches the report's citation list
    assert determination_citations(bare) == ["zoning:NC-2", "app:2", "overlay:1"]


def test_history_note_is_set_on_alcohol_and_entertainment_only() -> None:
    assert {r.area: r.history_note for r in rules_rows(DETERMINATIONS)} == {
        "zoning_use": None,
        "alcohol": "No outcome history for this pathway yet.",
        "entertainment": "No outcome history for this pathway yet.",
        "health": None,
        "building_change_of_use": None,
    }


# ---- labels, sources, days to decision -----------------------------------------------------------
def test_display_labels() -> None:
    assert [status_label(s) for s in STATUS_DEFINITIONS] == [
        "Allowed",
        "Further review",
        "Potential blocker",
        "Not permitted",
        "Insufficient information",
    ]


def test_most_severe_follows_status_severity() -> None:
    assert most_severe(["allowed", "further_review", "insufficient_information"]) == "further_review"
    assert most_severe(["allowed", "insufficient_information"]) == "insufficient_information"
    assert most_severe(["allowed"]) == "allowed"
    assert most_severe(reversed(STATUS_SEVERITY)) == "not_permitted"
    assert most_severe([]) == "insufficient_information"


def test_days_to_decision() -> None:
    d = dt.date
    assert days_to_decision(d(2024, 1, 1), d(2024, 5, 1)) == 121
    assert days_to_decision(d(2024, 1, 1), d(2024, 1, 1)) == 0
    assert days_to_decision(None, d(2024, 5, 1)) is None
    assert days_to_decision(d(2024, 1, 1), None) is None
    assert days_to_decision(d(2024, 5, 1), d(2024, 1, 1)) is None  # decided before filed: a data error


def _app(source: str, **extra: Any) -> Application:
    return Application(
        id=f"{source}:1",
        source=source,  # type: ignore[arg-type]
        source_id="1",
        source_url="https://example.org/1",
        fetched_at=dt.datetime(2026, 10, 21, tzinfo=dt.UTC),
        kind="cua",
        permit_type="Conditional Use Authorization",
        extra=extra,
    )


def test_comparable_source_prefers_the_motion() -> None:
    assert comparable_source(_app("datasf_planning")) == "datasf_planning"
    assert comparable_source(_app("datasf_planning", motion_url="https://example.org/m.pdf")) == (
        "sf_planning_hearings"
    )
    assert comparable_source(_app("datasf_entertainment")) == "datasf_entertainment"


def test_minutes_only_cases_are_not_labelled_as_a_motion() -> None:
    """The store sets `motion_url` for every hearing enrichment, including rows parsed from Commission minutes
    (`extra.source_kind == "minutes"`), where no motion was read."""
    motion = _app(
        "datasf_planning",
        motion_url="https://example.org/M-21497.pdf",
        source_kind="motion",
        doc_name="M-21497",
    )
    minutes = _app(
        "datasf_planning",
        motion_url="https://example.org/minutes/2024-01-25.pdf",
        source_kind="minutes",
        minutes_url="https://example.org/minutes/2024-01-25.pdf",
    )
    standalone_minutes = _app("sf_planning_hearings", source_kind="minutes")
    standalone_motion = _app(
        "sf_planning_hearings", source_kind="motion", motion_url="https://example.org/m.pdf"
    )
    assert comparable_source(motion) == "sf_planning_hearings"
    assert comparable_source(minutes) == comparable_source(standalone_minutes) == "sf_planning_minutes"
    assert comparable_source(standalone_motion) == "sf_planning_hearings"
    assert source_label(comparable_source(motion)) == "Planning Commission motion"
    assert source_label(comparable_source(minutes)) == "Planning Commission minutes"
    # the note shown for a minutes case does not claim adopted conditions
    assert record_sources(minutes) == {"datasf_planning", "sf_planning_minutes"}
    # a minutes-only row brings no motion note with it
    assert record_sources(standalone_minutes) == {"sf_planning_minutes"}
    assert record_sources(motion) == {"datasf_planning", "sf_planning_hearings"}
    assert record_sources(_app("abc")) == {"abc"}
    (note,) = source_notes_for(record_sources(standalone_minutes))
    assert note.label == "Planning Commission minutes" and "motion itself was not read" in note.leaves_out
    assert "Conditions as adopted" not in note.leaves_out


def test_source_notes_say_what_each_source_leaves_out() -> None:
    assert {k: (n.label, n.leaves_out) for k, n in SOURCE_NOTES.items()} == {
        "datasf_planning": (
            "Planning case list (DataSF)",
            "Outcome and dates only. Conditions are not in this list unless the Commission motion was read; "
            "withdrawn and cancelled cases carry no reason. The decision date is the date Planning closed the "
            "record.",
        ),
        "sf_planning_hearings": (
            "Planning Commission motion",
            "Conditions as adopted at the hearing. Later amendments, enforcement history and whether the business "
            "opened are not included.",
        ),
        "sf_planning_minutes": (
            "Planning Commission minutes",
            "The Commission's action as recorded in the hearing minutes; the motion itself was not read, so "
            "conditions are only those named in the minutes. Findings, later amendments, enforcement history and "
            "whether the business opened are not included.",
        ),
        "datasf_entertainment": (
            "Entertainment Commission permit list (DataSF)",
            "Active permits only: no denials, withdrawals, filing dates or conditions, so it cannot show that an "
            "application failed.",
        ),
        "abc": (
            "ABC licence export",
            "Licences that are active or pending today. Denied and withdrawn applications are absent and there is "
            "no filing date, so it cannot show a failure or a processing time.",
        ),
        "user_feedback": ("Outcome reported by a Permit Memo user", "Self-reported and not verified."),
    }
    notes = source_notes_for({"user_feedback", "abc", "datasf_business", "datasf_planning"})
    assert [n.source for n in notes] == [
        "datasf_planning",
        "abc",
        "user_feedback",
    ]  # fixed order, unknown skipped
    assert source_notes_for([]) == []


def test_pdf_text_spells_out_characters_the_font_cannot_draw() -> None:
    from app.services.memo_pdf import _esc

    assert _esc("limited to ⅓ of gross floor area; last ½ hour; R&D <5") == (
        "limited to 1/3 of gross floor area; last 1/2 hour; R&amp;D &lt;5"
    )


# ---- rule table v2 through the report ----------------------------------------------------------------
PRACTICE_NOTE = "Code and Planning practice differ"
PCN_NOTE = "public convenience or necessity finding likely required"
HOW_OBTAINED = (
    "how the liquor licence will be obtained (new, or a transfer from another owner or another location)"
)


def _set_by_rule(rows: Any) -> list[tuple[Any, ...]]:
    return [(r.area, r.status, r.status_note, r.referral_steps, r.missing_inputs) for r in rows]


def test_a_status_is_printed_with_its_note_after_a_colon() -> None:
    assert status_with_note("further_review", PRACTICE_NOTE) == (
        "Further review: Code and Planning practice differ"
    )
    assert status_with_note("further_review", PCN_NOTE) == (
        "Further review: public convenience or necessity finding likely required"
    )
    assert status_with_note("further_review", None) == status_label("further_review") == "Further review"


def test_the_status_note_referral_steps_and_missing_inputs_reach_the_report_unchanged(tmp_path: Path) -> None:
    """Each row of the report carries the rules' status note, referral steps and missing inputs."""
    rules = case_determinations("mission-east-restaurant", tmp_path, in_full=True)
    by_area = {r.area: r for r in rules.rows}
    assert (by_area["zoning_use"].status, by_area["zoning_use"].status_note) == (
        "further_review",
        PRACTICE_NOTE,
    )
    assert (by_area["alcohol"].status, by_area["alcohol"].status_note) == ("further_review", PCN_NOTE)
    assert (
        len(by_area["alcohol"].referral_steps) == 2
        and len(by_area["building_change_of_use"].missing_inputs) == 3
    )
    approvals = rules_rows(rules)
    overall = rules_overall(rules)
    assert _set_by_rule(approvals) == _set_by_rule(rules.rows)
    assert [row_headline(r) for r in approvals][:2] == [
        "Zoning and use: Further review: Code and Planning practice differ",
        "Alcohol licence: Further review: public convenience or necessity finding likely required",
    ]
    # a note never changes the status it is printed after
    assert overall.status == rules.overall_status and overall.line == rules.overall_line
    # the copies are the report's own: changing one does not reach the rules' result
    approvals[1].referral_steps.clear()
    approvals[-1].missing_inputs.clear()  # the building row
    assert (
        len(by_area["alcohol"].referral_steps) == 2
        and len(by_area["building_change_of_use"].missing_inputs) == 3
    )


def test_a_report_made_before_rule_table_v2_has_no_note_steps_or_missing_inputs() -> None:
    approvals = rules_rows(DETERMINATIONS)
    assert all((r.status_note, r.referral_steps, r.missing_inputs) == (None, [], []) for r in approvals)
    assert row_headline(approvals[1]) == "Alcohol licence: Potential blocker"
    assert pathway_lines(DETERMINATIONS.pathway)[0].startswith("PATHWAY (set by rule): Restaurant · NC-2")
    assert trigger_lines(DETERMINATIONS.pathway) == [] and change_answer_rows(None) == []
    # only the rule lines are printed under such a row
    building = approvals[4]
    assert row_rule_lines(building, DETERMINATIONS.pathway) == [
        f"    rule {rule_line_text(line)}" for line in building.basis
    ]


def test_a_referral_step_is_never_an_approval_and_is_never_in_the_entitlement_path(tmp_path: Path) -> None:
    rules = case_determinations("valencia-wine-bar", tmp_path)
    approvals = rules_rows(rules)
    steps = [line for row in approvals for line in row.referral_steps]
    # ABC to Police and Planning; the entertainment permits' referrals, ended ones included; health; building
    assert {r.area: len(r.referral_steps) for r in approvals} == {
        "zoning_use": 0,
        "alcohol": 2,
        "entertainment": 10,
        "health": 1,
        "building_change_of_use": 1,
    }
    assert all(step.rule_id == "referral.step" for step in steps)
    # one row per approval the rules set: a step adds no row, and no step is among a row's rule lines
    assert [r.area for r in approvals] == [r.area for r in rules.rows] and len(approvals) == 5
    basis = [line.text for row in approvals for line in row.basis]
    path = rules.entitlement_path
    assert path == entitlement_path(rules.rows)
    # the zoning row names the story, which is not given (decision of 2026-11-12), so the path lists no zoning
    # approval
    assert path == (
        "Place of Entertainment, Limited Live Performance or Fixed Place Outdoor Amplified Sound permit; Health "
        "permit to operate; Building permit with change of use"
    )
    names = [r.approval for r in approvals]
    assert set(path.split("; ")) <= set(names)
    for step in steps:
        assert step.text not in names and step.text not in basis and step.text not in path
    assert "sent to" not in path and "Police Department" not in path
    # the headline findings lead (pathway rule 9), then the rows are counted
    assert rules_overall(rules).line.startswith(
        "A Conditional Use Authorization is needed (use control of a special"
    )
    assert " Of the 5 approvals this concept needs:" in rules_overall(rules).line
    # a referral that ended is still listed as a step, and the permit it was part of is still the approval
    ended = [s.text for s in approvals[2].referral_steps if "That step has ended." in s.text]
    assert len(ended) == 4 and all(text.endswith("The permit is still required.") for text in ended)
    assert approvals[2].status == "further_review" and "Place of Entertainment" in approvals[2].approval
    # with every step taken away, the statuses, the approvals, the overall line and the path are the same
    bare = [row.model_copy(update={"referral_steps": []}) for row in rules.rows]
    assert entitlement_path(bare) == path
    assert overall_line(bare, rules.headline_findings) == rules.overall_line
    assert [(r.status, r.approval) for r in bare] == [(r.status, r.approval) for r in rules.rows]


def test_every_line_the_rules_wrote_has_its_records_in_the_citation_list(tmp_path: Path) -> None:
    rules = case_determinations("valencia-wine-bar", tmp_path)
    cited = determination_citations(rules)
    assert len(cited) == len(set(cited))
    p = rules.pathway
    assert p.changes is not None
    printed = [
        *p.lines,
        *p.notes,
        *(line for f in p.triggers for line in f.lines),
        *p.changes.planning_use_lines,
        *p.changes.building_occupancy_lines,
        *p.changes.neighbourhood_notice_lines,
        *(line for row in rules.rows for line in (*row.basis, *row.referral_steps)),
    ]
    assert {c for line in printed for c in line.citations} == set(cited)
    assert {"zoning:NCT-VALENCIA", "app:abc:651564"} <= set(cited)
    # the overall citations stay what the rows' rule lines cite
    assert set(rule_citations(rules.rows)) <= set(cited)


def test_a_trigger_whose_control_is_not_todays_prints_the_sentence_that_says_so(tmp_path: Path) -> None:
    """A restaurant with a new licence in the Haight Street NCD, under the rules of 13 January 2024: the liquor
    licence rule read not decided that day (the Restaurant quota of Table 719 Note (4), which the rules cannot
    count; corrected from "not permitted" by the review) and reads conditional from the next."""
    past = case_determinations(
        "haight-restaurant-alcohol", tmp_path, in_full=True, rules_date=dt.date(2024, 1, 13)
    )
    assert past.pathway.rules_date == "2024-01-13"
    t4 = next(f for f in past.pathway.triggers if f.rule_id == "T4")
    assert (t4.control, t4.differs_today) == ("not_decided", True)
    (sentence,) = trigger_differs_texts(t4)
    assert sentence == next(line.text for line in t4.lines if line.rule_id == "T4.differs")
    assert "2024-01-14" in sentence and "today it reads" in sentence
    assert trigger_headline(t4).startswith("T4 Liquor licence rule of a restricted district: ")
    lines = trigger_lines(past.pathway)
    assert lines[0] == (
        "TRIGGERS: Each reason the Planning Code can require a hearing, read for the rules in force on 2024-01-13."
    )
    at = lines.index(f"  {trigger_headline(t4)}")
    assert lines[at + 1] == f"    {sentence}"
    # all eleven triggers are listed, each with its control
    assert [line.split(" ", 3)[2] for line in lines if line.startswith("  T")] == [
        f"T{n}" for n in range(1, 12)
    ]
    text = pathway_lines(past.pathway)
    assert text[1] == "  Rules applied as of 2024-01-13" and text[-len(lines) :] == lines
    # the same case under today's rules: no trigger says it differs
    today = case_determinations("haight-restaurant-alcohol", tmp_path, in_full=True)
    assert all(not f.differs_today and trigger_differs_texts(f) == [] for f in today.pathway.triggers)
    # a finding marked as differing with no sentence of its own still says so, in the fixed words
    bare = t4.model_copy(update={"lines": [x for x in t4.lines if not x.rule_id.endswith(".differs")]})
    assert (
        trigger_differs_texts(bare)
        == [REPORT_TEXT["differs_today"]]
        == ["This control is not today's control."]
    )


def test_the_text_report_prints_what_the_rules_set_under_each_row(tmp_path: Path) -> None:
    rules = case_determinations("valencia-wine-bar", tmp_path)
    assert rules.pathway.changes is not None
    rows = {r.area: r for r in rules_rows(rules)}
    # the alcohol row: its rule lines, then the steps (said not to be approvals), then what was not given
    alcohol = rows["alcohol"]
    assert row_headline(alcohol) == "Alcohol licence: Insufficient information"
    printed = row_rule_lines(alcohol, rules.pathway)
    n = len(alcohol.basis)
    assert printed[:n] == [f"    rule {rule_line_text(line)}" for line in alcohol.basis]
    assert printed[n] == (
        "    Steps inside this approval. These are review steps inside the approval, where one agency sends "
        "the application to another. They are not separate approvals."
    )
    assert printed[n + 1 : n + 3] == [f"      step {rule_line_text(s)}" for s in alcohol.referral_steps]
    assert printed[n + 3 :] == [f"    Not given: {HOW_OBTAINED}"]
    assert (
        not_given_text(["the floor area of the business, in square feet", "the closing time"])
        == "Not given: the floor area of the business, in square feet; the closing time"
    )
    # the building row: the three change-of-use answers, each on its own line
    building = rows["building_change_of_use"]
    printed = row_rule_lines(building, rules.pathway)
    at = printed.index("    Change of use: three separate answers")
    answers = printed[at + 1 :]
    assert [line for line in answers if not line.startswith("        ")] == [
        "      Planning Code change of use: Yes",
        "      Building Code change of occupancy: Not established",
        "      Neighbourhood notification: Not required",
    ]
    # an answer's rule lines the row already prints are not printed twice; the notice lines are new
    changes = rules.pathway.changes
    assert unprinted_lines(changes.planning_use_lines, building.basis) == []
    assert unprinted_lines(changes.building_occupancy_lines, building.basis) == []
    notice = changes.neighbourhood_notice_lines
    assert notice and unprinted_lines(notice, building.basis) == notice
    assert answers[3:] == [f"        rule {rule_line_text(line)}" for line in notice]
    assert [(q, a) for q, a, _ in change_answer_rows(changes)] == [
        ("Planning Code change of use", "Yes"),
        ("Building Code change of occupancy", "Not established"),
        ("Neighbourhood notification", "Not required"),
    ]
    # no other row prints the answers; a row with no step prints its rule lines, then what was not given (the
    # zoning row: the story first, which is never assumed)
    for area in ("zoning_use", "alcohol", "entertainment", "health"):
        assert "    Change of use: three separate answers" not in row_rule_lines(rows[area], rules.pathway)
    zoning = rows["zoning_use"]
    assert zoning.missing_inputs[0] == "which stories the business occupies"
    assert row_rule_lines(zoning, rules.pathway) == [
        *(f"    rule {rule_line_text(line)}" for line in zoning.basis),
        f"    {not_given_text(zoning.missing_inputs)}",
    ]


# ---- timing: days from filing, by outcome, never one blended figure ------------------------------------
AS_OF = dt.date(2026, 11, 9)


def _comparable(n: int, outcome: str, filed: str | None, decided: str | None) -> ComparableCase:
    return ComparableCase(
        application_id=f"datasf_planning:{n}",
        citation_id=f"app:datasf_planning:{n}",
        source="datasf_planning",
        source_label="Planning case list (DataSF)",
        record_kind="use_decision",
        record_kind_label="Use decision",
        permit_type="Conditional Use Authorization",
        use_types=["bar"],
        address=f"{900 + n} Valencia St",
        distance_m=50.0,
        filed_at=filed,
        decided_at=decided,
        days_to_decision=days_to_decision(iso_date(filed), iso_date(decided)),
        outcome=outcome,
        hours_close=None,
        conditions=[],
        opposition_noted=None,
        similarity_score=0.5,
        lat=None,
        lng=None,
        source_url="https://example.org/record",
    )


def _planning_app(outcome: str, status: str) -> Application:
    return Application(
        id="datasf_planning:1",
        source="datasf_planning",
        source_id="1",
        source_url="https://example.org/record/1",
        fetched_at=dt.datetime(2026, 11, 9, tzinfo=dt.UTC),
        kind="cua",
        permit_type="Conditional Use Authorization",
        description="A bar",
        status=status,
        outcome=outcome,  # type: ignore[arg-type]
    )


def test_a_cancelled_case_is_shown_as_cancelled_not_withdrawn() -> None:
    """The store has no outcome for a cancelled case: the Planning case list's 'Closed - Cancelled' is stored
    as withdrawn. The report names it from its own status, so its days are never read with the withdrawals'."""
    assert case_outcome(_planning_app("withdrawn", "Closed - Cancelled")) == "cancelled"
    assert case_outcome(_planning_app("withdrawn", "Cancelled")) == "cancelled"
    assert case_outcome(_planning_app("withdrawn", "Closed - Withdrawn")) == "withdrawn"
    assert case_outcome(_planning_app("withdrawn", "Withdrawn")) == "withdrawn"
    # only a withdrawn case is read this way; every other outcome is the store's own
    for outcome in ("approved", "approved_with_conditions", "denied", "pending", "unknown"):
        assert case_outcome(_planning_app(outcome, "Cancelled")) == outcome
    # the site history names such a case the same way, and keeps the source's own status beside it
    entry = site_history_entry(SiteRecord(_planning_app("withdrawn", "Closed - Cancelled"), 0.0, "address"))
    assert (entry.outcome, entry.status) == ("cancelled", "Closed - Cancelled")


def test_each_cases_days_name_the_outcome_they_are_for() -> None:
    filed, decided = "2024-01-01", "2024-05-01"  # 121 days
    wanted = {
        "approved": "121 days to approval",
        "approved_with_conditions": "121 days to approval",
        "denied": "121 days to denial",
        "withdrawn": "121 days to withdrawal",
        "cancelled": "121 days to cancellation",
        "unknown": "121 days to closing, outcome not recorded",
    }
    for n, (outcome, text) in enumerate(wanted.items()):
        assert timing_cell(_comparable(n, outcome, filed, decided), AS_OF) == text, outcome
    # a case still pending shows its age on the records date, whatever decision date the row carries
    age = (AS_OF - dt.date(2026, 1, 1)).days
    assert age == 312
    assert timing_cell(_comparable(7, "pending", "2026-01-01", None), AS_OF) == "pending 312 days so far"
    assert (
        timing_cell(_comparable(8, "pending", "2026-01-01", "2026-02-01"), AS_OF) == "pending 312 days so far"
    )
    assert comparable_time(_comparable(7, "pending", "2026-01-01", None), AS_OF) == CaseTime(
        "pending", 312, "app:datasf_planning:7"
    )
    # no figure without the dates it needs: never a guess
    assert timing_cell(_comparable(9, "approved", None, decided), AS_OF) == NO_FIGURE == "–"
    assert timing_cell(_comparable(9, "withdrawn", filed, None), AS_OF) == NO_FIGURE
    assert timing_cell(_comparable(9, "pending", None, None), AS_OF) == NO_FIGURE
    assert timing_cell(_comparable(9, "pending", "2026-01-01", None), None) == NO_FIGURE
    assert timing_cell(_comparable(9, "approved", "2024-05-01", "2024-01-01"), AS_OF) == NO_FIGURE
    assert case_time("approved", dt.date(2024, 1, 1), dt.date(2024, 5, 1), None).days == 121
    assert (
        timing_cell(_comparable(9, "approved", "2020-01-01", "2024-05-01"), AS_OF) == "1,582 days to approval"
    )


def test_days_from_filing_are_given_by_outcome_and_never_as_one_figure() -> None:
    import statistics

    cases = [
        _comparable(1, "approved", "2024-01-01", "2024-04-10"),  # 100
        _comparable(2, "approved_with_conditions", "2024-01-01", "2024-10-27"),  # 300
        _comparable(3, "denied", "2024-01-01", "2024-02-20"),  # 50
        _comparable(4, "withdrawn", "2024-01-01", "2024-01-21"),  # 20
        _comparable(5, "cancelled", "2024-01-01", "2025-02-04"),  # 400
        _comparable(6, "pending", "2026-01-01", None),  # 312 so far
        _comparable(7, "pending", None, None),  # no figure
        _comparable(8, "unknown", "2024-01-01", None),  # no figure
    ]
    times = [comparable_time(c, AS_OF) for c in cases]
    groups, undated = decision_times(times)
    assert [(g.group.key, g.cases, g.low, g.high) for g in groups] == [
        ("approved", 2, 100, 300),
        ("denied", 1, 50, 50),
        ("withdrawn", 1, 20, 20),
        ("cancelled", 1, 400, 400),
        ("pending", 1, 312, 312),
    ]
    assert undated == 2
    lines = [group_time_line(g, AS_OF) for g in groups]
    assert lines == [
        "Approved: 2 cases, 100 to 300 days from filing to approval.",
        "Denied: 1 case, 50 days from filing to denial.",
        "Withdrawn: 1 case, 20 days from filing to withdrawal.",
        "Cancelled: 1 case, 400 days from filing to cancellation.",
        "Still pending: 1 case, 312 days since filing (age so far as of 2026-11-09, not a time to a decision).",
    ]
    # each group's figures come from its own cases only
    own = {
        "approved": {"app:datasf_planning:1", "app:datasf_planning:2"},
        "denied": {"app:datasf_planning:3"},
        "withdrawn": {"app:datasf_planning:4"},
        "cancelled": {"app:datasf_planning:5"},
        "pending": {"app:datasf_planning:6"},
    }
    assert {g.group.key: set(g.citation_ids) for g in groups} == own
    by_case = {t.citation_id: t.days for t in times}
    for g in groups:
        assert {g.low, g.high} <= {by_case[c] for c in g.citation_ids}
    # no line holds a figure taken across outcomes: not the mean, the median or the range of all the cases
    figures = [t.days for t in times if t.days is not None]
    across = {
        f"{round(statistics.mean(figures)):,}",
        f"{round(statistics.median(figures)):,}",
        f"{min(figures):,} to {max(figures):,}",
        f"{sum(figures):,}",
    }
    assert not any(value in line for value in across for line in lines)
    assert not any(word in " ".join(lines).lower() for word in ("average", "median", "mean", "typical"))
    # the withdrawn and the cancelled case are never one group, and a pending age is never a time to a decision
    assert [g.group.label for g in groups] == [
        "Approved",
        "Denied",
        "Withdrawn",
        "Cancelled",
        "Still pending",
    ]
    assert [g.key for g in TIMING_GROUPS] == [
        "approved",
        "denied",
        "withdrawn",
        "cancelled",
        "not_recorded",
        "pending",
    ]
    # nothing to group: no line and no figure
    assert decision_times([]) == ([], 0)
    assert decision_times([CaseTime("approved", None)]) == ([], 1)
