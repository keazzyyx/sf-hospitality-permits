"""The PDF of a Location Risk Memo: what the rules decided is printed as the rules wrote it (status, "Rules
applied", the pathway block), then the facts the rules read; nothing a model wrote is printed.

Rule table v2: a status prints its status note after a colon; under a row come "Rules applied", "Steps inside
this approval" (said to be review steps, not approvals), "Not given", and under the building row the three
change-of-use answers; the zoning section lists the triggers with their controls and the rules date. The
end-to-end checks of these against real rule output are in tests/test_memo_chain.py."""

from __future__ import annotations

import datetime as dt
import io
from collections.abc import Iterator
from pathlib import Path

import pypdf
import pytest

from app.agents.memo_runner import MemoRunInput, MemoRunner
from app.agents.runner import RunnerEvent
from app.catalog.loader import get_catalog
from app.core.config import settings
from app.memo.report import (
    REPORT_TEXT,
    status_with_note,
)
from app.models.memo import RECORDS_LIMITS, Memo, MemoApprovalRow, Pathway, RuleLine, TriggerFinding
from app.services.memo_pdf import (
    CHANGES_HEADING,
    NO_DISTRICT,
    NOT_GIVEN_HEADING,
    PATHWAY_HEADING,
    PATHWAY_HINT,
    RULES_APPLIED_HEADING,
    STEPS_HEADING,
    STEPS_HINT,
    TIMING_COLUMN,
    TRIGGERS_HEADING,
    _status,
    pathway_rows,
    render_memo_pdf,
    row_rule_markup,
    rule_line_markup,
    trigger_markup,
)
from tests.fakes import FakeAnthropic
from tests.memo_fakes import FakeGeocoder, MemoScript, seed_store

TODAY = dt.date(2026, 10, 21)
# What the scripted intake model's profile (tests.fakes.BASE_PROFILE) claims, all stated, so the stated-facts check
# (app.memo.stated) keeps every fact the memo's rules read.
DESC = (
    "40-seat wine bar of 1,400 square feet, small kitchen, open until 1am, occasional live music, amplified"
)
# The same wine bar on a stated first story. With no story given no story is assumed and the zoning row is
# insufficient information (the user's decision of 2026-11-12); on the first story the table on file for NCT-2 is
# read and the district bars the wine bar, so every row of the report is not permitted.
DESC_FIRST = (
    "40-seat ground-floor wine bar of 1,400 square feet, small kitchen, open until 1am, occasional live music, "
    "amplified"
)


def _first_story() -> MemoScript:
    script = MemoScript()
    script.profile = {**script.profile, "stories": ["first"]}
    return script


@pytest.fixture(autouse=True)
def _wire_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tools read the store and the geocoder through app.deps; point them at the seeded fixtures."""
    import app.memo.context as ctx
    import app.tools.precedent_tools as pt

    store = seed_store(tmp_path / "data")
    for mod in (ctx, pt):
        monkeypatch.setattr(mod, "get_store", lambda: store)
        monkeypatch.setattr(mod, "get_geocoder", lambda: FakeGeocoder())
    yield


async def _memo(tmp_path: Path, script: MemoScript | None = None, description: str = DESC) -> Memo:
    store = seed_store(tmp_path / "run")
    runner = MemoRunner(
        FakeAnthropic(script or MemoScript()),  # type: ignore[arg-type]
        get_catalog(),
        settings,
        store,
        FakeGeocoder(),  # type: ignore[arg-type]
        today=TODAY,
    )

    async def emit(ev: RunnerEvent) -> None:
        return None

    run = runner.run_memo(MemoRunInput(address="995 Valencia St", description=description), emit)
    terminal = [ev async for ev in run]
    assert [e.type for e in terminal] == ["memo"], terminal
    memo: Memo = terminal[0].data["memo"]
    return memo


async def _memo_first(tmp_path: Path) -> Memo:
    return await _memo(tmp_path, _first_story(), DESC_FIRST)


def _pdf_text(memo: Memo) -> str:
    reader = pypdf.PdfReader(io.BytesIO(render_memo_pdf(memo)))
    return " ".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)


def _line(text: str, section: str | None = None, citations: list[str] | None = None) -> RuleLine:
    return RuleLine(rule_id="zoning.test", text=text, code_section=section, citations=citations or [])


def _pathway(**changes: object) -> Pathway:
    base: dict[str, object] = {
        "use": "bar",
        "use_label": "Bar",
        "district": "NCT-2",
        "permission": "conditional",
        "permission_label": "Conditional use",
        "existing_use": "restaurant",
        "change_of_use": "yes",
        "change_of_use_label": "Change of use",
        "lines": [],
        "notes": [],
    }
    return Pathway.model_validate({**base, **changes})


@pytest.mark.anyio
async def test_each_row_prints_status_then_rules_applied_then_the_facts_it_read(
    tmp_path: Path,
) -> None:
    memo = await _memo_first(tmp_path)
    text = _pdf_text(memo)
    rows = text.split("Approvals this concept needs", 1)[1].split("What the records could not establish", 1)[
        0
    ]
    assert rows.count(RULES_APPLIED_HEADING) == len(memo.approvals) == 5
    at = 0
    for row in memo.approvals:
        # in this order: the row and its status (with its status note when the rules gave one), "Rules
        # applied", every rule line as the rules wrote it, the steps inside the approval, what was not given,
        # then the facts the rules read, each with its value
        wanted = [
            f"{row.area_label} · {status_with_note(row.status, row.status_note)} {RULES_APPLIED_HEADING}",
            *(line.text for line in row.basis),
            *(
                [STEPS_HEADING, STEPS_HINT, *(s.text for s in row.referral_steps)]
                if row.referral_steps
                else []
            ),
            *([NOT_GIVEN_HEADING, *row.missing_inputs] if row.missing_inputs else []),
            REPORT_TEXT["facts_read_heading"],
            *(f"{f.label}: {f.value}" for f in row.facts),
        ]
        for part in wanted:
            found = rows.find(part, at)
            assert found >= 0, (row.area, part)
            at = found + len(part)
    # the code section a rule rests on follows its line; a line that already names it does not print it twice
    alcohol = next(r for r in memo.approvals if r.area == "alcohol")
    section = alcohol.basis[-1].code_section  # the status line; the row opens with the licence the rules read
    assert section == "California Business and Professions Code § 23790" and section in rows
    zoning = memo.approvals[0]
    use_line = zoning.basis[0]
    assert use_line.code_section == "Planning Code § 102" and use_line.code_section in use_line.text
    assert rows.count("Planning Code § 102") == 1
    # the building row prints the zoning row's change-of-use line, word for word
    building = next(r for r in memo.approvals if r.area == "building_change_of_use")
    change = next(line for line in zoning.basis if line.rule_id == "change.planning_use")
    assert change in building.basis
    assert rows.count(change.text) == 2
    # every row of this report is not permitted (the district bars the wine bar, and Planning Code § 175(a)
    # carries that to every later row, the decision of 2026-11-12): no row lists a referral step or a missing
    # input. The building row still prints the three change-of-use answers, each on its own line.
    assert [r.area for r in memo.approvals if r.referral_steps] == []
    assert [r.area for r in memo.approvals if r.missing_inputs] == []
    assert rows.count(STEPS_HEADING) == rows.count(NOT_GIVEN_HEADING) == 0
    assert rows.count(CHANGES_HEADING) == 1
    after = rows.split(CHANGES_HEADING, 1)[1]
    assert (
        after.index("Planning Code change of use: Not established")
        < after.index("Building Code change of occupancy: Not established")
        < after.index("Neighbourhood notification: Not required")
        < after.index(REPORT_TEXT["facts_read_heading"])
    )
    # the fixed line on what public records cannot show closes the could-not-establish section
    could_not = text.split("What the records could not establish", 1)[1].split("Site history", 1)[0]
    assert memo.records_limits == RECORDS_LIMITS and could_not.strip().endswith(RECORDS_LIMITS)
    # days are printed per outcome: the column is not "Days to decision"
    assert TIMING_COLUMN == "Days from filing" and "Days to decision" not in text
    assert REPORT_TEXT["timing_heading"] in text
    # nothing a model wrote: no explanation, finding, label, next step or check line
    for gone in (
        "Next step",
        "Citation check",
        "Verified",
        "Likely applicable",
        "Expected conditions",
        "Takeaway",
    ):
        assert gone not in text, gone


@pytest.mark.anyio
async def test_a_row_prints_its_referral_steps_and_what_was_not_given_after_its_rule_lines(
    tmp_path: Path,
) -> None:
    """A restaurant at the same address is not barred: its rows list the steps inside each approval and the
    inputs not given, in that order after the rule lines and before the facts the rules read."""
    script = MemoScript()
    script.profile = {
        **script.profile,
        "business_type": "restaurant",
        "live_entertainment": False,
        "amplified_sound": False,
    }
    memo = await _memo(tmp_path, script)
    text = _pdf_text(memo)
    rows = text.split("Approvals this concept needs", 1)[1].split("What the records could not establish", 1)[
        0
    ]
    building = next(r for r in memo.approvals if r.area == "building_change_of_use")
    assert building.status == "insufficient_information"
    assert building.referral_steps and building.missing_inputs
    stepped = [r for r in memo.approvals if r.referral_steps]
    assert rows.count(STEPS_HEADING) == rows.count(STEPS_HINT) == len(stepped)
    assert rows.count(NOT_GIVEN_HEADING) == len([r for r in memo.approvals if r.missing_inputs])
    at = rows.find(f"{building.area_label} · ")
    assert at >= 0
    for part in [
        *(line.text for line in building.basis),
        STEPS_HEADING,
        STEPS_HINT,
        *(s.text for s in building.referral_steps),
        NOT_GIVEN_HEADING,
        *building.missing_inputs,
        CHANGES_HEADING,
        REPORT_TEXT["facts_read_heading"],
    ]:
        found = rows.find(part, at)
        assert found >= 0, part
        at = found + len(part)


@pytest.mark.anyio
async def test_pathway_block_in_the_zoning_section(tmp_path: Path) -> None:
    memo = await _memo_first(tmp_path)
    text = _pdf_text(memo)
    glance = text.split("At a glance", 1)[1].split("Expected conditions", 1)[0]
    p = memo.pathway
    assert (p.use, p.district, p.permission, p.existing_use, p.change_of_use) == (
        "bar",
        "NCT-2",
        "not_permitted",
        None,
        "not_established",
    )
    # use, district, control for a new use, existing use, change-of-use answer, then the notes, then the table
    block = (
        f"{PATHWAY_HEADING} {PATHWAY_HINT} Proposed use Bar Zoning district NCT-2 Control on a new use Not "
        "permitted Existing use Not shown by the records Change of use Change of use not established "
    )
    assert glance.strip().startswith(block)
    # the district's note and the alcohol district's; the hours text on the rule row is no longer a note, because
    # rule table v2 reads hours from the dated control data and not from that text
    assert len(p.notes) == 2
    at = len(block) - 1
    for note in p.notes:
        assert note.text.startswith("Note on file, not evaluated by the rules: ")
        found = glance.find(note.text, at)
        assert found >= 0, note.text
        at = found + len(note.text)
    assert glance.find("Zoning NCT-2 — bars: conditional", at) > 0
    # the pathway's own rule lines are printed once, in the zoning row, not again here
    assert p.lines[0].text not in glance
    # the date whose rules were applied closes the pathway table; the triggers follow the notes
    assert "Change of use Change of use not established Rules applied as of 2026-10-21 " in glance
    assert glance.index(p.notes[-1].text) < glance.index(
        f"{TRIGGERS_HEADING} Each reason the Planning Code can require a hearing, read for the rules in "
        "force on 2026-10-21."
    )
    assert len(p.triggers) == 11
    at = glance.index(TRIGGERS_HEADING)
    for finding in p.triggers:
        found = glance.find(f"{finding.rule_id} {finding.label}: ", at)
        assert found >= 0, finding.rule_id
        at = found
    assert "T1 Use control of the zoning district: Not permitted" in glance
    assert "T3 Enlarging or intensifying an existing use: Does not apply" in glance


@pytest.mark.anyio
async def test_same_memo_gives_the_same_rule_text_in_the_pdf(tmp_path: Path) -> None:
    """Two runs on the same records print the same statuses and rule lines."""
    first = await _memo(tmp_path / "a")
    second = await _memo(tmp_path / "b")

    def rules(memo: Memo) -> list[tuple[str, str, list[str]]]:
        return [(r.area, r.status, [line.text for line in r.basis]) for r in memo.approvals]

    assert rules(first) == rules(second) and first.pathway == second.pathway
    for memo in (first, second):
        text = _pdf_text(memo)
        for row in memo.approvals:
            assert (
                f"{row.area_label} · {status_with_note(row.status, row.status_note)} {RULES_APPLIED_HEADING}"
                in text
            )
            assert all(line.text in text for line in row.basis)


@pytest.mark.anyio
async def test_a_path_that_says_there_is_none_prints_no_days_or_cost(tmp_path: Path) -> None:
    """A row is not permitted: the entitlement path is the sentence that says so, and no day or cost figure is
    printed anywhere."""
    memo = await _memo_first(tmp_path)
    assert memo.overall.status == "not_permitted"
    no_path = "No approval path: zoning does not permit the concept as described at this address."
    assert memo.entitlement_path == no_path
    text = _pdf_text(memo)
    assert f"Approvals to file, in order: {no_path}" in text
    assert "Timeline & cost" not in text and "$" not in text


def test_rule_line_markup_prints_the_section_once_and_the_record_numbers() -> None:
    index = {"zoning:NCT-2": 4, "overlay:x": 9}
    # the section follows the sentence, after the record numbers
    out = rule_line_markup(
        _line("A new Bar here needs a Conditional Use Authorization.", "Planning Code § 303"), index
    )
    assert out == (
        "A new Bar here needs a Conditional Use Authorization. <font color='#6b7280'>Planning Code § 303</font>"
    )
    cited = rule_line_markup(
        _line("NCT-2: a Bar is a conditional use.", "Planning Code § 752", ["zoning:NCT-2"]), index
    )
    assert cited.startswith("NCT-2: a Bar is a conditional use. <super>")
    assert "[4]" in cited and cited.endswith("<font color='#6b7280'>Planning Code § 752</font>")
    # a sentence that already names its section in the same words prints it once
    named = _line("The concept is looked up as a Bar (Planning Code § 102).", "Planning Code § 102")
    assert rule_line_markup(named, index) == "The concept is looked up as a Bar (Planning Code § 102)."
    # no section on file: the sentence alone; a record that is not in the citation list prints no number
    assert rule_line_markup(_line("Hours: the district sets no limit.", None, ["app:missing"]), index) == (
        "Hours: the district sets no limit."
    )
    # the rules' text is escaped like any other text
    assert rule_line_markup(_line("Hours <= 2 a.m. & later", "§ 1 & 2"), {}) == (
        "Hours &lt;= 2 a.m. &amp; later <font color='#6b7280'>§ 1 &amp; 2</font>"
    )


def test_pathway_rows_for_what_the_records_do_not_show() -> None:
    assert pathway_rows(_pathway()) == [
        ("Proposed use", "Bar"),
        ("Zoning district", "NCT-2"),
        ("Control on a new use", "Conditional use"),
        ("Existing use", "Restaurant"),
        ("Change of use", "Change of use"),
    ]
    # a report made under rule table v2 says which date's rules it applied; an older one has no such row
    assert pathway_rows(_pathway(rules_date="2024-01-13"))[-1] == ("Rules applied as of", "2024-01-13")
    assert len(pathway_rows(_pathway(rules_date="2024-01-13"))) == 6
    bare = _pathway(
        use="not_covered",
        use_label="a use the rule table does not cover",
        district=None,
        permission="not_covered",
        permission_label="Not covered by the rule table",
        existing_use=None,
        change_of_use="not_established",
        change_of_use_label="Change of use not established",
    )
    assert pathway_rows(bare) == [
        ("Proposed use", "A use the rule table does not cover"),
        ("Zoning district", NO_DISTRICT),
        ("Control on a new use", "Not covered by the rule table"),
        ("Existing use", "Not shown by the records"),
        ("Change of use", "Change of use not established"),
    ]


# ---- rule table v2 ---------------------------------------------------------------------------------------
def _rule(rule_id: str, text: str, section: str | None = None) -> RuleLine:
    return RuleLine(rule_id=rule_id, text=text, code_section=section)


def _row(**changes: object) -> MemoApprovalRow:
    base: dict[str, object] = {
        "area": "building_change_of_use",
        "area_label": "Building permit and change of use",
        "approval": "Building permit with change of use",
        "agency": "San Francisco Department of Building Inspection",
        "status": "further_review",
        "basis": [_rule("change.planning_use", "Restaurant to Bar is a change of use.")],
    }
    return MemoApprovalRow.model_validate({**base, **changes})


def test_a_status_prints_its_note_after_a_colon_as_the_rules_wrote_it() -> None:
    plain = _status("further_review")
    assert plain.endswith("<b>Further review</b></font>")
    assert _status("further_review", None) == plain
    assert _status("further_review", "Code and Planning practice differ") == (
        f"{plain}: Code and Planning practice differ"
    )
    assert _status("further_review", "public convenience or necessity finding likely required") == (
        f"{plain}: public convenience or necessity finding likely required"
    )
    assert _status("further_review", "a < b & c").endswith(": a &lt; b &amp; c")  # escaped like any text


def test_row_rule_markup_prints_rules_then_steps_then_what_was_not_given_then_the_three_answers() -> None:
    change = _rule("change.planning_use", "Restaurant to Bar is a change of use.")
    occupancy = _rule("change.occupancy", "A change of occupancy is not established.")
    notice = _rule("change.notice", "A change of use does not by itself need notice.", "Planning Code § 311")
    step = _rule("referral.step", "This application is sent to the Planning Department for review.")
    pathway = _pathway(
        changes={
            "planning_use": "yes",
            "planning_use_lines": [change],
            "building_occupancy": "not_established",
            "building_occupancy_lines": [occupancy],
            "neighbourhood_notice": "not_required",
            "neighbourhood_notice_lines": [notice],
        }
    )
    row = _row(
        basis=[change, occupancy],
        referral_steps=[step],
        missing_inputs=["the existing occupancy group of the space", "seats < 50 & plans"],
    )
    assert row_rule_markup(row, pathway, {}) == [
        ("heading", "Rules applied"),
        ("line", "• Restaurant to Bar is a change of use."),
        ("line", "• A change of occupancy is not established."),
        ("heading", "Steps inside this approval"),
        (
            "hint",
            "These are review steps inside the approval, where one agency sends the application to another. "
            "They are not separate approvals.",
        ),
        ("line", "• This application is sent to the Planning Department for review."),
        ("heading", "Not given"),
        ("line", "• the existing occupancy group of the space"),
        ("line", "• seats &lt; 50 &amp; plans"),
        ("heading", "Change of use: three separate answers"),
        ("line", "• <b>Planning Code change of use:</b> Yes"),
        ("line", "• <b>Building Code change of occupancy:</b> Not established"),
        ("line", "• <b>Neighbourhood notification:</b> Not required"),
        # the one rule line of an answer that "Rules applied" did not already print
        (
            "line",
            "&nbsp;&nbsp;&nbsp;A change of use does not by itself need notice. "
            "<font color='#6b7280'>Planning Code § 311</font>",
        ),
    ]
    # a row with no step and nothing missing prints only its rule lines; no other row prints the answers
    zoning = _row(area="zoning_use", area_label="Zoning and use", basis=[change])
    assert row_rule_markup(zoning, pathway, {}) == [
        ("heading", "Rules applied"),
        ("line", "• Restaurant to Bar is a change of use."),
    ]
    # a report made before rule table v2 has no answers to print
    assert row_rule_markup(_row(), _pathway(), {}) == [
        ("heading", "Rules applied"),
        ("line", "• Restaurant to Bar is a change of use."),
    ]


def test_trigger_markup_lists_each_trigger_with_its_control_and_the_sentence_where_it_differs_today() -> None:
    cell = RuleLine(
        rule_id="T4.rule",
        text="Haight Street: a new on-sale establishment is not permitted.",
        code_section="Planning Code § 719",
        citations=["zoning:NCD-HAIGHT"],
    )
    differs = _rule(
        "T4.differs", "This control changed on 2024-01-14 (Ord. 248-23); today it reads conditional."
    )
    t4 = TriggerFinding(
        rule_id="T4",
        family="licence_in_restricted_district",
        label="Liquor licence rule of a restricted district",
        control="not_permitted",
        lines=[cell, differs],
        differs_today=True,
    )
    t5 = TriggerFinding(
        rule_id="T5",
        family="formula_retail",
        label="Formula retail",
        control="not_decided",
        missing_inputs=[
            "whether the business is part of a chain that shares its name, look or menu with other locations"
        ],
        lines=[_rule("T5.missing", "The description does not say whether the business is part of a chain.")],
        in_force_from="2025-10-06",
        ordinance="Ord. 173-25",
    )
    pathway = _pathway(rules_date="2024-01-13", triggers=[t4, t5])
    out = trigger_markup(pathway, {"zoning:NCD-HAIGHT": 3})
    assert len(out) == 3
    assert out[0].startswith("• T4 Liquor licence rule of a restricted district: Not permitted <super>")
    assert "[3]" in out[0]
    assert (
        out[1]
        == "&nbsp;&nbsp;&nbsp;This control changed on 2024-01-14 (Ord. 248-23); today it reads conditional."
    )
    assert out[2] == (
        "• T5 Formula retail: Not decided (control in force from 2025-10-06, Ord. 173-25). Not given: whether "
        "the business is part of a chain that shares its name, look or menu with other locations"
    )
    assert trigger_markup(_pathway(), {}) == []  # a report made before rule table v2


@pytest.mark.anyio
async def test_the_pdf_names_the_intake_question_that_answers_each_open_question(tmp_path: Path) -> None:
    """An open question the applicant can answer prints the question to answer (app.memo.intake), and one line above
    the list says how many there are; a question only an agency answers prints neither."""
    from app.memo.intake import QUESTION_BY_ID
    from app.services.memo_pdf import ANSWERABLE_PREFIX, answerable_line

    memo = await _memo(tmp_path)  # no story, no chain answer, no licence answer: the report asks for them
    answerable = [q for q in memo.could_not_establish if q.intake_question]
    assert answerable and all(q.intake_question in QUESTION_BY_ID for q in answerable)
    could_not = (
        _pdf_text(memo).split("What the records could not establish", 1)[1].split("Site history", 1)[0]
    )
    assert " ".join(answerable_line(len(answerable)).split()) in could_not
    assert could_not.count(ANSWERABLE_PREFIX) == len(answerable)
    for q in answerable:
        assert f"{ANSWERABLE_PREFIX} “{QUESTION_BY_ID[q.intake_question or ''].question}”" in could_not
    assert answerable_line(1).startswith("One of these is a question you can answer.")
    assert answerable_line(3).startswith("3 of these are questions you can answer.")
    # a memo stored before the questions carried their intake question prints the list as before
    stored = memo.model_copy(
        update={
            "could_not_establish": [
                q.model_copy(update={"intake_question": None}) for q in memo.could_not_establish
            ]
        }
    )
    before = _pdf_text(stored).split("What the records could not establish", 1)[1].split("Site history", 1)[0]
    assert ANSWERABLE_PREFIX not in before and "questions you can answer" not in before


@pytest.mark.anyio
async def test_the_headline_findings_come_first_in_the_text_report_and_the_pdf(tmp_path: Path) -> None:
    """Pathway rule 9 (change of 2026-11-16): what changes the plans is printed first, before the overall line and
    the rows, each finding with its status, whether it depends on an answer not given, and the line it rests on.
    The seeded wine bar gives no story: the special use district's rule asks for a Conditional Use whatever the
    story, and the zoning row itself stays insufficient information."""
    from app.memo.report import headline_lines, report_text

    memo = await _memo(tmp_path)
    assert memo.headline_findings, "the seeded report has a Conditional Use to lead with"
    first = memo.headline_findings[0]
    assert (first.kind, first.definite, first.status) == ("conditional", True, "further_review")
    zoning = next(r for r in memo.approvals if r.area == "zoning_use")
    assert zoning.status == "insufficient_information"
    assert memo.overall.status == "further_review"
    # the text report: the headline block sits between the address line and the overall line
    lines = report_text(memo).splitlines()
    head = lines.index(f"{REPORT_TEXT['headline_heading'].upper()} (set by rule)")
    overall = next(i for i, line in enumerate(lines) if line.startswith("OVERALL: "))
    approvals = lines.index("APPROVALS (status, approval and agency set by rule)")
    assert head < overall < approvals
    assert lines[head : head + len(headline_lines(memo))] == headline_lines(memo)
    assert f"  - Further review ({REPORT_TEXT['headline_definite']}): {first.sentence}" in lines
    assert lines[overall].startswith("OVERALL: Further review — A Conditional Use Authorization is needed")
    # the PDF: "Read this first" before "Overall:" and before the approvals table
    text = _pdf_text(memo)
    at = text.index(REPORT_TEXT["headline_heading"])
    assert at < text.index("Overall:") < text.index("Approvals this concept needs")
    assert " ".join(first.sentence.split())[:80] in text[at:]
    # a memo stored before the headline findings prints no such block
    stored = memo.model_copy(update={"headline_findings": []})
    assert headline_lines(stored) == []
    assert REPORT_TEXT["headline_heading"] not in _pdf_text(stored)
