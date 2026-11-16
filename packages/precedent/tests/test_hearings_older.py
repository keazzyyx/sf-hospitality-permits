"""Conditions of approval from 2009-2018 Planning Commission motions (all_conditions(older_formats=True)).

Fixtures in fixtures/sf_planning_hearings/older: three small motion PDFs, and the extracted text of OCR'd motions
whose PDFs are over 1 MB. Each expected list was checked against the motion PDF. No network.
"""

from __future__ import annotations

from pathlib import Path

from precedent.pdftext import find_sections, read_pdf, strip_running_headers
from precedent.sources import sf_planning_hearings as hearings

OLDER = Path(__file__).parent / "fixtures" / "sf_planning_hearings" / "older"


def _pdf_section(name: str) -> str:
    """The conditions section of an older motion PDF, read the way full_conditions.extract reads it (cut at an
    Exhibit C after the conditions)."""
    doc = read_pdf(
        (OLDER / name).read_bytes(), max_pages=hearings.MOTION_MAX_PAGES, stop=hearings.is_plan_page
    )
    body = hearings.cut_older_exhibits(hearings.motion_body(doc.text))
    return find_sections(strip_running_headers(body))["conditions"]


def _older(section: str) -> list[hearings.Condition]:
    return hearings.all_conditions(section, older_formats=True)


def test_untitled_numbered_paragraphs_2009() -> None:
    """2009.1001C: "1. This authorization is ...". Before, the titled pattern took "12. An enclosed garbage area"
    as the only condition and the sentence fallback made junk rows."""
    section = _pdf_section("2009.1001C.pdf")
    conds = _older(section)
    assert [c.number for c in conds] == [str(n) for n in range(1, 14)]
    assert {c.title for c in conds} == {"Condition"}
    assert conds[11].text.startswith(
        "Condition: An enclosed garbage area shall be provided within the establishment"
    )
    assert "deemed void and canceled" in conds[12].text
    assert "Community Liaison Officer" in conds[7].text
    # off by default: the 2019+ reading is unchanged (nothing numbered, so extract() fell back to sentences)
    assert hearings.all_conditions(section) == []


def test_non_breaking_spaces_2011() -> None:
    """2011.0571C: the text layer joins words with U+00A0, which the titled pattern did not take for a space."""
    section = _pdf_section("2011.0571C.pdf")
    assert "\xa0" in section
    conds = _older(section)
    assert [(c.number, c.title) for c in conds] == [
        ("1", "Validity and Expiration"),
        ("2", "Extension"),
        ("3", "Enforcement"),
        ("4", "Revocation due to Violation of Conditions"),
        ("5", "Garbage, Recycling, and Composting Receptacles"),
        ("6", "Sidewalk Maintenance"),
        ("7", "Community Liaison"),
        ("8", "Notices Posted at Bars and Entertainment Venues"),
        ("9", "Noise Control"),
    ]
    assert "\xa0" not in conds[0].text
    assert hearings.all_conditions(section) == []


def test_titled_paragraphs_without_numbers_2012() -> None:
    """2012.0638C: bold titled paragraphs whose list numbers are not in the PDF text; numbered in order."""
    conds = _older(_pdf_section("2012.0638C.pdf"))
    assert [c.title for c in conds] == [
        "Validity and Expiration",
        "Extension",
        "Garbage, composting and recycling storage",
        "Enforcement",
        "Revocation due to Violation of Conditions",
        "Garbage, Recycling, and Composting Receptacles",
        "Sidewalk Maintenance",
        "Noise Control",
        "Odor Control",
        "Community Liaison",
    ]
    assert [c.number for c in conds] == [str(n) for n in range(1, 11)]
    assert "soundproofed or insulated for noise" in conds[7].text


def test_garbled_exhibit_heading_finds_conditions_2015() -> None:
    """2015-004164CUA: OCR garbled "EXHIBIT A" and left a dash after the conditions heading; the loose heading
    is tried only when no conditions section was found."""
    text = (OLDER / "2015-004164CUA.motion-tail.txt").read_text()
    assert "Conditions of Approval, Compliance, Monitoring, and Reporting —" in text
    sections = find_sections(text)
    assert "exhibit_a" not in sections
    section = sections["conditions"]
    assert section.lstrip().startswith("PERFORMANCE")
    conds = _older(section)
    assert [(c.number, c.title) for c in conds] == [
        ("1", "Validity"),
        ("2", "Expiration and Renewal"),
        ("3", "Diligent pursuit"),
        ("4", "Extension"),
        ("5", "Conformity with Current Law"),
        ("6", "Garbage, composting and recycling storage"),  # number lost in OCR
        ("7", "Enforcement"),
        ("8", "Garbage, Recycling, and Composting Receptacles"),
        ("9", "Sidewalk Maintenance"),
    ]


def test_strict_heading_still_wins() -> None:
    text = "Conditions of Approval\n1. Validity. Three years.\nConditions of Approval, Compliance, Monitoring, and Reporting —\n"
    assert find_sections(text)["conditions"].startswith("1. Validity")


def test_condition_number_lost_in_ocr_2016() -> None:
    """2016-010652CUA lost condition 9's number; it is the one titled paragraph between 8 and 10."""
    section = (OLDER / "2016-010652CUA.conditions.txt").read_text()
    assert "9" not in [c.number for c in hearings.all_conditions(section)]
    conds = {c.number: c for c in _older(section)}
    assert list(conds) == [str(n) for n in range(1, 15)]
    assert conds["9"].title == "Sidewalk Maintenance"
    assert conds["9"].text.startswith(
        "Sidewalk Maintenance: The Project Sponsor shall maintain the main entrance"
    )
    assert "Sidewalk Maintenance" not in conds["8"].text  # no longer folded into the condition before


def test_several_numbers_lost_and_a_leading_gap() -> None:
    conds = {c.number: c.title for c in _older((OLDER / "2016-002498CUA.conditions.txt").read_text())}
    assert list(conds) == [str(n) for n in range(1, 13)]
    assert (conds["6"], conds["8"], conds["9"]) == (
        "Enforcement",
        "Garbage, Recycling, and Composting Receptacles",
        "Sidewalk Maintenance",
    )
    conds = {c.number: c.title for c in _older((OLDER / "2016-014422CUA.conditions.txt").read_text())}
    assert list(conds) == [str(n) for n in range(1, 9)]
    assert (conds["1"], conds["2"], conds["3"]) == ("Validity and Expiration", "Extension", "Signage")


def test_garbled_numbers_and_titles_2016() -> None:
    """2016-005799CUA: "L Validity." (1 read as L), "4. E~ctension." and "9. Design Considerations." at a line end."""
    conds = _older((OLDER / "2016-005799CUA.conditions.txt").read_text())
    numbers = [c.number for c in conds]
    assert numbers[:26] == [str(n) for n in range(1, 27)]
    assert numbers[26:] == ["27A", "27B", "27C", "27D", "28", "29", "30"]
    titles = {c.number: c.title for c in conds}
    assert (titles["1"], titles["4"], titles["9"]) == ("Validity", "E~ctension", "Design Considerations")


def test_gap_not_filled_when_the_count_does_not_match() -> None:
    section = (
        "1. Validity. Valid for three years.\n\n"
        "Extension. May be extended.\n\n"
        "Enforcement. Violations are enforced.\n\n"
        "3. Hours of Operation. Closed by 11 p.m.\n"
    )
    assert [c.number for c in _older(section)] == ["1", "3"]  # two candidates for one missing number
    section = section.replace("Enforcement. Violations are enforced.\n\n", "")
    assert [(c.number, c.title) for c in _older(section)] == [
        ("1", "Validity"),
        ("2", "Extension"),
        ("3", "Hours of Operation"),
    ]


def test_complete_numbered_run_is_read_the_same_either_way() -> None:
    section = (
        "1. Validity. Valid for three years.\n"
        "2. Hours of Operation. The business shall close by 11 p.m. daily.\n"
        "3. Community Liaison. The sponsor shall appoint a liaison.\n"
        "A. The liaison shall answer calls.\nB. The liaison shall report.\n"
    )
    assert _older(section) == hearings.all_conditions(section)
    assert [c.number for c in _older(section)] == ["1", "2", "3A", "3B"]


def test_numbered_list_inside_a_condition_is_not_the_conditions_2012() -> None:
    """2012.0370C: titled paragraphs without numbers, and inside "Transformer Vault" a preference schedule 1-7 joined
    by semicolons. Before, the schedule was taken for seven untitled conditions and the 19 real ones were lost."""
    conds = _older(_pdf_section("2012.0370C.pdf"))
    assert [c.title for c in conds[:19]] == [
        "Validity and Expiration",
        "Extension",
        "Mitigation Measures",
        "Final Materials",
        "Garbage, composting and recycling storage",
        "Rooftop Mechanical Equipment",
        "Streetscape Plan",
        "Transformer Vault",
        "Noise",
        "Street Trees",
        "Showers and Clothes Lockers",
        "Managing Traffic During Construction",
        "Transit Impact Development Fee",
        "Enforcement",
        "Revocation due to Violation of Conditions",
        "Garbage, Recycling, and Composting Receptacles",
        "Sidewalk Maintenance",
        "Noise Control",
        "Community Liaison",
    ]
    assert [c.number for c in conds] == [str(n) for n in range(1, len(conds) + 1)]
    # the Mitigation Monitoring and Reporting Program (Exhibit C) after #19 is not read as conditions 20-23, and
    # its table no longer runs on into #19 (whose categories it changed)
    assert len(conds) == 19
    assert conds[18].categories == ("community_liaison",)
    assert "Mitigation Measure" not in conds[18].text
    vault = conds[7]
    assert "preference schedule" in vault.text and "in a basement area accessed via a garage" in vault.text
    assert "Condition" not in {c.title for c in conds}


def test_numbered_run_items_must_open_paragraphs() -> None:
    """A run of numbered lines continued after a semicolon is a list inside a paragraph, not untitled conditions."""
    section = (
        "Validity. Valid for three years.\n\n"
        "Transformer Vault. Locations, most to least desirable:\n"
        "1. On-site, in a basement;\n"
        "2. On-site, in a driveway;\n"
        "3. Public right-of-way, underground;\n"
        "4. On-site, in a ground floor facade.\n\n"
        "Enforcement. Violations are enforced.\n"
    )
    conds = _older(section)
    assert [(c.number, c.title) for c in conds] == [
        ("1", "Validity"),
        ("2", "Transformer Vault"),
        ("3", "Enforcement"),
    ]
    assert "in a driveway" in conds[1].text


def test_compliance_contact_lines_removed_whatever_the_spacing_2011() -> None:
    """2011.0571C: once its non-breaking spaces are spaces, "For  information  about  compliance" has two spaces
    between words and the strict pattern kept the contact lines (and their categories: "amplified" made #9 Noise
    Control an entertainment condition)."""
    conds = {c.number: c for c in _older(_pdf_section("2011.0571C.pdf"))}
    for n in ("5", "6", "8", "9"):
        assert "compliance, contact" not in conds[n].text
        assert "information about" not in conds[n].text.replace("  ", " ")
    assert conds["5"].text.endswith("guidelines set forth by the Department of Public Works.")
    assert conds["9"].categories == ("noise",)


def test_strict_compliance_pattern_kept_without_older_formats() -> None:
    """2019+ reading unchanged: contact lines with doubled spaces stay (32 cached 2019+ conditions carry them)."""
    section = (
        "1. Validity. Valid for three years.\n"
        "2. Sidewalk Maintenance. Keep the sidewalk clean.\n"
        "For  information  about  compliance, contact Public Works.\n"
    )
    assert "contact Public Works" in hearings.all_conditions(section)[1].text
    assert "contact Public Works" not in _older(section)[1].text


def test_numbering_restarted_under_headings_made_unique_2012() -> None:
    """2012.0262CUA prints PERFORMANCE 1-6, then DESIGN 1 and 2, MONITORING 3, OPERATION 4-6; OCR lost the numbers
    of DESIGN 1 and OPERATION 4-5. case_conditions is keyed by (motion, number), so the repeated numbers dropped the
    later list. The second list's leading gap is filled from its titled paragraph: before, "Garbage, composting and
    recycling storage" (DESIGN 1) ran on into #6 "Conformity with Current Law"."""
    section = (OLDER / "2012.0262CUA.conditions.txt").read_text()
    plain = [c.number for c in hearings.all_conditions(section)]
    assert len(plain) != len(set(plain))  # the 2019+ reading repeats numbers
    conds = _older(section)
    assert [(c.number, c.title) for c in conds] == [
        ("1", "Mitigation Measures"),
        ("2", "Validity and Expiration"),
        ("3", "Expiration and Renewal"),
        ("4", "Diligent Pursuit"),
        ("5", "Extension"),
        ("6", "Conformity with Current Law"),
        ("2.1", "Garbage, composting and recycling storage"),
        ("2.2", "Signage"),
        ("2.3", "Enforcement"),
        ("2.4", "Garbage, Recycling, and Composting Receptacles"),
        ("2.5", "Sidewalk Maintenance"),
        ("2.6", "Community Liaison"),
    ]


def test_unique_numbers_scheme() -> None:
    """Only a later list that repeats a number gets the "<list>." prefix; lettered parts follow it ("2.1A")."""
    section = (
        "1. Validity. Valid for three years.\n"
        "2. Hours. Closed by 11 p.m.\n"
        "8. Noise. Kept down.\n"
        "1. Liaison. A liaison is named.\n"
        "A. The liaison answers calls.\nB. The liaison reports.\n"
        "2. Odor. Controlled.\n"
        "3. Litter. Picked up.\n"
    )
    numbers = [c.number for c in _older(section)]
    assert numbers == ["1", "2", "8", "2.1A", "2.1B", "2.2", "2.3"]
    assert len(numbers) == len(set(numbers))
    # a later list that repeats no number keeps its numbers as printed
    section = "1. Validity. Three years.\n2. Hours. Closed by 11 p.m.\n9. Noise. Kept down.\n4. Odor. Controlled.\n"
    assert [c.number for c in _older(section)] == ["1", "2", "9", "4"]


def test_pick_motion_falls_back_to_a_motion_filed_under_another_class() -> None:
    """Older motions moved in the July 2016 migration are sometimes filed under "Application" as "19183.pdf.pdf"."""
    listing = {
        "a": {"ClassName": "Application", "Name": "application packet.pdf", "docLink": "u-app"},
        "b": {"ClassName": "Application", "Name": "19183.pdf.pdf", "docLink": "u-motion"},
        "c": {"ClassName": "Application", "Name": "Draft Motion 19183.pdf", "docLink": "u-draft"},
        "d": {"ClassName": "Executive Summary", "Name": "2012.0370C.pdf", "docLink": "u-summary"},
    }
    assert (hearings.Fetcher.pick_motion(listing) or {})["docLink"] == "u-motion"
    # a draft, or a pdf not named for a motion number, is never picked
    del listing["b"]
    assert hearings.Fetcher.pick_motion(listing) is None
    listing["e"] = {"ClassName": "Application", "Name": "DRAFT-19183.pdf", "docLink": "u-draft2"}
    assert hearings.Fetcher.pick_motion(listing) is None
    # a motion filed under the motion class still wins
    listing["f"] = {"ClassName": hearings.MOTION_CLASS, "Name": "M-19183.pdf", "docLink": "u-real"}
    listing["g"] = {"ClassName": "Application", "Name": "19183.pdf.pdf", "docLink": "u-motion"}
    assert (hearings.Fetcher.pick_motion(listing) or {})["docLink"] == "u-real"


def test_restarted_list_leading_gap_needs_a_matching_count() -> None:
    """A restarted list's missing start is filled only when the titled paragraphs before it match the count."""
    section = (
        "1. Validity. Valid for three years.\n"
        "2. Extension. May be extended.\n"
        "3. Conformity with Current Law. Codes apply.\n"
        "DESIGN\n"
        "Garbage Storage. Space for garbage.\n\n"
        "Rooftop Equipment. Screened.\n"
        "3. Signage. Signs comply.\n"
    )
    assert [c.number for c in _older(section)] == ["1", "2", "3", "2.1", "2.2", "2.3"]
    assert [c.title for c in _older(section)][3:5] == ["Garbage Storage", "Rooftop Equipment"]
    one_short = section.replace("Rooftop Equipment. Screened.\n", "")
    assert [c.number for c in _older(one_short)] == [
        "1",
        "2",
        "3",
        "2.3",
    ]  # two missing, one paragraph: not filled


def test_ocr_eight_read_as_s_or_dollar() -> None:
    """2016-013754CUA "S. Enforcement.", 2017-003848CUA "$. Signs and Awnings.": the 8 ran on into #7."""
    for mark in ("S", "$"):
        section = (
            "6. Final Materials. Final materials are reviewed.\n"
            "7. Signage. A signage program is required.\n"
            f"{mark}. Enforcement. Violations are enforced.\n"
            "9. Revocation due to Violation of Conditions. Complaints are referred.\n"
        )
        conds = _older(section)
        assert [(c.number, c.title) for c in conds] == [
            ("6", "Final Materials"),
            ("7", "Signage"),
            ("8", "Enforcement"),
            ("9", "Revocation due to Violation of Conditions"),
        ]
        assert "Enforcement" not in conds[1].text
    # only when the 8 is the one number missing: with 7 and 8 missing, "S." is not taken for either
    section = (
        "6. Final Materials. Final materials are reviewed.\n"
        "Signage is required on the storefront and\n"
        "S. Enforcement. Violations are enforced.\n"
        "9. Revocation due to Violation of Conditions. Complaints are referred.\n"
    )
    assert [c.number for c in _older(section)] == ["6", "9"]


def test_double_period_after_the_number() -> None:
    """2018-008376CUA "10.. Odor Control.": the condition ran on into #9."""
    section = (
        "9. Sidewalk Maintenance. Keep it clean.\n"
        "10.. Odor Control. Odors are controlled.\n"
        "11. Noise Control. Noise is controlled.\n"
    )
    assert [(c.number, c.title) for c in _older(section)] == [
        ("9", "Sidewalk Maintenance"),
        ("10", "Odor Control"),
        ("11", "Noise Control"),
    ]
    assert [c.number for c in hearings.all_conditions(section)] == [
        "9",
        "11",
    ]  # the 2019+ reading is unchanged


def test_running_header_is_not_a_paragraph_title() -> None:
    """2016-000455CUA: the running header "Motion No. 19659 CASE NO. ..." counted as a second titled paragraph in
    the 4-6 gap, so "Conformity with Current Law" (#5) was not restored and ran on into #4."""
    section = (
        "4. Extension. All time limits may be extended.\n"
        "Conformity with Current Law. No application shall be approved.\n"
        "SAN FRANCISCO 11 PLANNING DEPARTMENT\n\n"
        "Motion No. 19659 CASE NO. 2016-000455CUA\n"
        "June 9, 2016 1327 Polk Street\n"
        "DESIGN - COMPLIANCE AT PLAN STAGE\n"
        "6. Garbage, composting and recycling storage. Space for garbage.\n"
    )
    conds = _older(section)
    assert [(c.number, c.title) for c in conds] == [
        ("4", "Extension"),
        ("5", "Conformity with Current Law"),
        ("6", "Garbage, composting and recycling storage"),
    ]


def test_contact_line_ending_in_a_comma_ends_a_paragraph() -> None:
    """2016-008418CUA: "... at 415-558-8728," before "Signage." kept Signage from opening a paragraph, so the 5-9 gap
    (Rooftop Mechanical Equipment, Signage, Enforcement) was not filled."""
    section = (
        "5. Conformity with Current Law. No application shall be approved.\n"
        "DESIGN\n"
        "Rooftop Mechanical Equipment. Equipment is screened.\n"
        "For information about compliance, contact the Case Planner, Planning Department at 415-558-8728,\n"
        "Signage. Any signs shall comply with Article 6.\n"
        "For information about compliance, contact the Case Planner, Planning Department at 415-558-8728,\n"
        "MONITORING\n"
        "Enforcement. Violations are enforced.\n"
        "9. Revocation due to Violation of Conditions. Complaints are referred.\n"
    )
    assert [(c.number, c.title) for c in _older(section)] == [
        ("5", "Conformity with Current Law"),
        ("6", "Rooftop Mechanical Equipment"),
        ("7", "Signage"),
        ("8", "Enforcement"),
        ("9", "Revocation due to Violation of Conditions"),
    ]


def test_numbers_with_a_closing_parenthesis() -> None:
    """2016-003525CUA and 2017-000519CUA number "1) Validity.": every condition was lost (4 sentence fragments)."""
    section = (
        "PERFORMANCE\n"
        "1) Validity. Valid for three years.\n"
        "2) Expiration and Renewal. Renew by filing.\n"
        "3) Diligent Pursuit. Build promptly.\n"
        "OPERATION\n"
        "4) Community Liaison. A liaison is named.\n"
    )
    assert [(c.number, c.title) for c in _older(section)] == [
        ("1", "Validity"),
        ("2", "Expiration and Renewal"),
        ("3", "Diligent Pursuit"),
        ("4", "Community Liaison"),
    ]
    assert hearings.all_conditions(section) == []  # the 2019+ reading is unchanged


def test_exhibit_c_after_the_conditions_is_cut_off() -> None:
    body = (
        "DECISION\nApproved subject to the conditions in EXHIBIT A and the MMRP attached as\n"
        "EXHIBIT C to this Motion.\n\f\n"
        "EXHIBIT A\nCONDITIONS OF APPROVAL\n"
        "1. Validity. Valid for three years.\n"
        "2. Community Liaison. A liaison is named.\n\f\n"
        "MITIGATION MONITORING AND REPORTING PROGRAM\n"
        "Mitigation Measure M-NO-1: Reduction of Building Operation Noise. Noise is reduced.\n"
    )
    cut = hearings.cut_older_exhibits(body)
    assert cut.endswith("2. Community Liaison. A liaison is named.\n\f\n")
    assert "EXHIBIT C to this Motion" in cut  # a mention before the conditions heading is not the cut
    assert (
        hearings.cut_older_exhibits("1. Validity. Valid.\nEXHIBIT C\n") == "1. Validity. Valid.\nEXHIBIT C\n"
    )


def test_contact_lines_in_their_ocr_forms() -> None:
    """2016-006961CUA "Far information abouf", 2017-004187CUA "For .information", 2016-016026CUA a page footer
    between "For" and "information": the contact lines stayed in the condition text."""
    for line in (
        "Far information about compliance, contact Code Enforcement.",
        "For information abouf compliance, contact the Case Planner.",
        "For .information about compliance, contact Code Enforcement.",
        "For\nSAN FRANCISCO 14P LANNING DEPARTMENT\n\n\ninformation about compliance, contact Public Works.",
    ):
        section = (
            f"1. Validity. Valid for three years.\n2. Sidewalk Maintenance. Keep the sidewalk clean. {line}\n"
        )
        assert _older(section)[1].text == "Sidewalk Maintenance: Keep the sidewalk clean.", line
    section = (
        "1. Validity. Valid.\n2. Sidewalk. Keep it clean. Far information about compliance, contact DPW.\n"
    )
    assert "Far information" in hearings.all_conditions(section)[1].text  # the 2019+ reading is unchanged


def test_colon_ended_title_on_the_gap_fill_path() -> None:
    """2012.0145C #19 "Temporary Liquor Service: Per Planning Code Section 205.3, ..." was titled "Condition"."""
    section = (
        "18. Hours of Operation. Open 7 a.m. to 2 a.m.\n"
        "19. Temporary Liquor Service: Per Planning Code Section 205.3, liquor may be served in the event\n"
        "space under a temporary license.\n"
        "20. Odor Control. Odors are controlled.\n"
    )
    conds = _older(section)
    assert [(c.number, c.title) for c in conds] == [
        ("18", "Hours of Operation"),
        ("19", "Temporary Liquor Service"),
        ("20", "Odor Control"),
    ]
    assert conds[1].text.startswith("Temporary Liquor Service: Per Planning Code Section 205.3, liquor")


def test_title_case_heading_opens_a_paragraph_2009() -> None:
    """2009.1103C: a "Parking & Traffic" heading between #7 and #8 ended the run of untitled numbered paragraphs."""
    section = (
        "1. This authorization is for a grocery store.\n\n"
        "2. The sponsor shall maintain the storefront.\n\n"
        "3. An enclosed garbage area shall be provided.\n"
        "Parking & Traffic\n"
        "4. Loading shall not occur at night.\n\n"
        "5. The project shall provide bicycle parking.\n"
    )
    assert [c.number for c in _older(section)] == ["1", "2", "3", "4", "5"]


def test_second_reading_helpers_for_motions_whose_text_ends_early() -> None:
    """2011.0026C: a short last findings page ("Motion 18420", no "No.") was taken for a plan sheet and the text
    ended before Exhibit A; full_conditions.extract reads such a motion again with pdftotext."""
    findings_end = (
        "Motion 18420\nAugust 4, 2011\n\nCASE NO. 2011.0026 C\n11. The Commission finds approval desirable.\n"
    )
    assert hearings.is_plan_page(9, findings_end)
    assert not hearings.is_plan_page_older(9, findings_end)
    assert not hearings.is_plan_page_older(9, "\n\n")  # a blank page
    assert hearings.is_plan_page_older(9, "FLOOR PLAN  SCALE: 1/4\" = 1'  SHEET A1")
    assert hearings.join_number_lines("PERFORMANCE\n1.\n\nValidity. Valid.\n2)\nExtension. Ok.\n") == (
        "PERFORMANCE\n1. Validity. Valid.\n2) Extension. Ok.\n"
    )
    text = "page one\f" + findings_end + "\fCASE NO. 2011.0026 C\nEXHIBIT A\n"
    assert hearings.motion_body(text) == "page one"
    assert hearings.motion_body(text, hearings.is_plan_page_older) == text


def test_read_pdf_poppler() -> None:
    import shutil

    from precedent.pdftext import PAGE_BREAK, read_pdf_poppler

    if shutil.which("pdftotext") is None:
        return
    doc = read_pdf_poppler(OLDER / "2011.0571C.pdf", max_pages=hearings.MOTION_MAX_PAGES)
    assert "Noise Control" in doc.text and doc.pages >= 2
    assert doc.text.count(PAGE_BREAK) == doc.pages - 1
    first = read_pdf_poppler(OLDER / "2011.0571C.pdf", stop=lambda i, page: i >= 1)
    assert PAGE_BREAK not in first.text
    assert read_pdf_poppler(OLDER / "missing.pdf").text == ""


# ---- 2026-11-13 review of the 2010-2018 extraction: run-on and lost conditions -------------------------------------


def test_number_printed_twice_is_kept_2010() -> None:
    """2010.0514C prints "5." twice (1-5, "5. The ground level storefront ...", 6-13). The second 5 ran on inside the
    first. It is kept as "2.5" (a list of one, _unique_numbers); 6-13 keep their printed numbers."""
    section = (
        "1. This authorization is to allow Other Entertainment.\n\n"
        "2. The Commission may consider revocation of this authorization.\n\n"
        "3. The operator shall obtain all necessary approvals.\n\n"
        "4. The use of electronic amplification shall not be permitted after midnight.\n\n"
        "5. All doors and windows shall be closed while entertainment activities are occurring.\n\n"
        "5. The ground level storefront shall be maintained in an attractive manner.\n\n"
        "6. The operator shall maintain the entrances and all sidewalks in a clean condition.\n\n"
        "7. Noise and odors shall be regulated so as not to be a nuisance.\n"
    )
    conds = _older(section)
    assert [c.number for c in conds] == ["1", "2", "3", "4", "5", "2.5", "6", "7"]
    assert conds[4].text == (
        "Condition: All doors and windows shall be closed while entertainment activities are occurring."
    )
    assert conds[5].text == "Condition: The ground level storefront shall be maintained in an attractive manner."
    # titled conditions: the same scheme
    titled = (
        "4. Validity. Three years.\n5. Noise. Kept down.\n5. Storefront. Kept attractive.\n6. Odor. Controlled.\n"
    )
    assert [(c.number, c.title) for c in _older(titled)] == [
        ("4", "Validity"),
        ("5", "Noise"),
        ("2.5", "Storefront"),
        ("6", "Odor"),
    ]
    # a repeated number the numbering does not go on after is not taken as a condition of its own
    section = section.split("6. The operator")[0]
    assert [c.number for c in _older(section)] == ["1", "2", "3", "4", "5"]
    assert "storefront" in _older(section)[-1].text


def test_untitled_numbered_lines_after_the_last_titled_condition() -> None:
    """2010.1162C (29 "Hours of Operation.", then untitled 30-33), 2011.0126C (24) and 2013.0224C (23): nothing took
    the untitled tail, so it ran on inside the last condition, whose text is cut at 600 characters, and 31-33 were
    dropped. Each is now a condition; a title-case heading ("11. Security." at a line end, 2017-007658CUA) is its
    title, a sentence is not."""
    long = " ".join(["The outdoor activity area shall be kept clean and quiet at all times."] * 12)
    section = (
        "28. Lighting. All Project lighting shall be directed onto the Project site.\n\n"
        "29. Hours of Operation. The subject establishment is limited to 10:00 a.m. to 12:00 a.m. daily.\n\n"
        f"30. The Planning Department will conduct a public information hearing at the Planning Commission\n{long}\n\n"
        "31. The hours of operation for the outdoor activity area shall be 11:00 a.m. to 10:00 p.m.\n\n"
        "32. The outdoor activity area is not allowed to have amplified music or a bar.\n\n"
        "33. All required permits shall be obtained.\n\n"
        "34. Security.\na. The Project Sponsor shall install exterior lighting.\n"
    )
    conds = _older(section)
    assert [(c.number, c.title) for c in conds] == [
        ("28", "Lighting"),
        ("29", "Hours of Operation"),
        ("30", "Condition"),
        ("31", "Condition"),
        ("32", "Condition"),
        ("33", "Condition"),
        ("34", "Security"),
    ]
    assert conds[1].text.endswith("10:00 a.m. to 12:00 a.m. daily.")
    assert conds[3].categories == ("hours", "outdoor")
    assert conds[5].text == "Condition: All required permits shall be obtained."
    # the 2019+ reading is unchanged: the tail runs on inside 29
    assert [c.number for c in hearings.all_conditions(section)] == ["28", "29"]
    # a numbered line that does not open a paragraph is not taken
    joined = "28. Lighting. Directed onto the site per\n29. Hours of Operation. Closed by 11 p.m. and\n30. more text\n"
    assert [c.number for c in _older(joined)] == ["28", "29"]


def test_title_with_curly_quotes_and_a_unicode_hyphen_2011() -> None:
    """2011.0701C: "14. ‘Bar Use’ ‐ Hours of Operation." (opening quote, U+2010 hyphen) was not a title, so the wine
    bar's hours ran on inside #13 Lighting."""
    section = (
        "13. Lighting. All project lighting shall be directed onto the project site.\n\n"
        "14. ‘Bar Use’ ‐ Hours of Operation. Under the subject Conditional Use authorization, the permitted\n"
        "hours of operation of the wine bar is 10 a.m. to 2 a.m., seven days a week.\n"
    )
    conds = _older(section)
    assert [(c.number, c.title) for c in conds] == [("13", "Lighting"), ("14", "‘Bar Use’ ‐ Hours of Operation")]
    assert "wine bar" not in conds[0].text
    assert conds[1].categories == ("hours",)
    other = "12. Noise. Kept down.\n\n13. ’Outdoor Activity Area’ – Hours of Operation. 5 p.m. to 10 p.m.\n"
    assert _older(other)[1].title == "’Outdoor Activity Area’ – Hours of Operation"


def test_fewer_titled_paragraphs_than_missing_numbers_2016() -> None:
    """2016-002786CUA: 5, an unnumbered "Enforcement." paragraph, then 8 (the motion lost 7 altogether). The
    paragraph takes the first missing number; an untitled paragraph is not taken."""
    section = (
        "5. Conformity with Current Law. No application shall be approved unless it complies.\n"
        "MONITORING\n"
        "Enforcement. Violation of any of the Planning Department conditions of approval contained in\n"
        "this Motion shall be subject to the enforcement procedures.\n"
        "OPERATION\n"
        "8. Garbage, Recycling, and Composting Receptacles. Containers shall be kept within the premises.\n"
    )
    conds = _older(section)
    assert [(c.number, c.title) for c in conds] == [
        ("5", "Conformity with Current Law"),
        ("6", "Enforcement"),
        ("8", "Garbage, Recycling, and Composting Receptacles"),
    ]
    assert "Violation" not in conds[0].text
    untitled = section.replace("Enforcement. Violation", "Violation")
    assert [c.number for c in _older(untitled)] == ["5", "8"]


def test_monitoring_sentence_keeps_its_compliance_phrase_2011() -> None:
    """The Monitoring template ends "... work with the Planning Department for information about compliance." and
    was cut to "... work with the Planning Department" (2009.0342C #5, 2011.0026C #8, 2011.0208C #3). The phrase is
    the sentence's own; the contact line after it is still removed, and so is a bare URL left of one."""
    head = (
        "8. Monitoring. The Project requires monitoring of the conditions of approval in this Motion. The\n"
        "Project Sponsor shall pay fees as established under Planning Code Section 351(e) (1) and work with the\n"
        "Planning Department for information about compliance.\n"
    )
    tail = "9. Odor Control. Odors shall be contained.\n"
    expected = (
        "Monitoring: The Project requires monitoring of the conditions of approval in this Motion. The Project "
        "Sponsor shall pay fees as established under Planning Code Section 351(e) (1) and work with the Planning "
        "Department for information about compliance."
    )
    for after in (
        "",
        "For information about compliance, contact Code Enforcement, Planning Department at 415-575-6863,\n"
        "www.sf-planning.org\n",
        "www.s f~lanning.org\n",  # the contact line itself stripped as a repeated line (2015-005788CUA)
    ):
        conds = _older(head + after + tail)
        assert [c.number for c in conds] == ["8", "9"]
        assert conds[0].text == expected
    # the 2019+ reading is unchanged
    assert hearings.all_conditions(head + tail)[0].text.endswith("work with the Planning Department")
