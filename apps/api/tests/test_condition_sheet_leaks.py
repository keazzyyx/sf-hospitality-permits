"""Text that is not the condition, run on into it from the motion's other pages (scripts/validation/condition_text.py:
leak_cut, tail_cut, inside_cut): the cuts on made-up and real cases, the real condition text they must leave alone,
and the built data (tools/conditions-search/data/conditions.json), checked with patterns written here, separately
from the ones the build uses. No network, no database."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
VALIDATION = REPO / "scripts" / "validation"
DATA = REPO / "tools" / "conditions-search" / "data" / "conditions.json"
LIST = REPO / "tools" / "conditions-search" / "sheet-leaks-2026-11-13.md"
if str(VALIDATION) not in sys.path:
    sys.path.insert(0, str(VALIDATION))

from condition_text import (  # noqa: E402
    NOISE_KIND,
    TITLE_KIND,
    Vocabulary,
    clean,
    inside_cut,
    leak_cut,
    leak_signatures,
    tail_cut,
)

# 2018-015652CUA #28 as extracted (case_conditions.text): the plan sheets after the conditions ran on into it
DRAFTING_HOMES = (
    "Electronic Amplification: The Project cannot use electronic amplification for sounds and/or music between "
    "midnight and 6 a.m. DRAFTING HOMES DraftingHomes.com Drawn by Job 9005 Date - Description - Revision "
    "3/29/19 - Initial - 0 4/10/19 - Scope of each Floor - 1 N 68.75 88.75 37.75 137.50 38.75 68.75 29.75 88.75 "
    "29.75 Powell St."
)
REVOCATION = (
    "Revocation due to Violation of Conditions: Should implementation of this Project result in complaints from "
    "interested property owners, residents, or commercial lessees which are not resolved by the Project Sponsor, the "
    "Zoning Administrator shall refer such complaints to the Commission, after which it may hold a public hearing on "
    "the matter to consider revocation of this authorization."
)
CONTACT = (
    "For information about compliance, contact Code Enforcement, Planning Department at 628.652.7463, "
    "www.sfplanning.org"
)


def cut(text: str, older: bool = False) -> tuple[str, list[tuple[str, str]]]:
    leaks: list[tuple[str, str]] = []
    return clean(text, older=older, leaks=leaks), leaks


def test_drafting_homes_title_block_is_cut_where_the_condition_ends() -> None:
    text, leaks = cut(DRAFTING_HOMES)
    assert text == (
        "Electronic Amplification: The Project cannot use electronic amplification for sounds and/or music "
        "between midnight and 6 a.m."
    )
    assert [k for k, _ in leaks] == ["drawing sheet"]
    assert leaks[0][1].startswith("DRAFTING HOMES DraftingHomes.com Drawn by Job 9005")
    assert leaks[0][1].endswith("Powell St.")
    assert leak_signatures(DRAFTING_HOMES) and not leak_signatures(text)


def test_a_run_of_dimensions_is_cut() -> None:
    body = "Hours: The hours of operation shall be 8 a.m. to 10 p.m. daily. "
    for junk in (
        "12.50 37.75 88.75 137.50 22.00",
        "N 14'-6\" 22'-0\" 9'-3\" Basement",
        "1308 1336 1314 1300 1326 1301 1340",
    ):
        text, leaks = cut(body + junk)
        assert text == body.strip(), junk
        assert [k for k, _ in leaks] == ["drawing sheet"], junk


def test_a_title_block_is_cut() -> None:
    body = "Signage: The Project Sponsor shall develop a signage program for the Project."
    for junk in (
        'A-2.1 Sheet Title PROPOSED FLOOR PLAN Drawn by JS Checked by MK Scale: 1/4" = 1\'-0" Project No. 2019-12',
        "Code Information 2016 Calif. Bldg. Code Amendments Drawn by DRAFTING HOMES Job 9005",
        "Mail Chute DN UP ELEC RECEP OFF OFFICE OFFICE EXAM OFFICE EXAM STRG LAB OFF WAITING",
    ):
        text, leaks = cut(f"{body} {junk}")
        assert text == body, junk
        assert [k for k, _ in leaks] == ["drawing sheet"], junk


def test_a_running_page_header_missed_by_the_older_clean_up_is_cut() -> None:
    body = (
        "Conformity with Current Law: No application for Building Permit, Site Permit, or other entitlement shall "
        "be approved unless it complies with all applicable provisions of City Codes in effect at the time of such "
        "approval."
    )
    for junk in (
        "Motion No. 20113 Case Number 2017-015083CUA February 22, 2018 721 Lincoln Way",  # 2017-015083CUA 5
        "Page 2 of 5SAN FRANCISCO Motion No. 19542 CASE NO. 2015-010314CUA January 7, 2016 3128 16th Street",
        "Motion No. 20414 RECORD NO. 2017-010011 CUA",  # 2017-010011CUA 5, decided 2019
    ):
        for older in (True, False):
            text, leaks = cut(f"{body} {junk}", older)
            assert text == body, junk
            assert [k for k, _ in leaks] == ["page header"], junk


@pytest.mark.parametrize(
    "junk",
    [
        "Page 3 of",  # 2015-003049CUA 4
        "Page 3 of 5SAN",  # 2015-010314CUA 11
        "SAN FRANCISCO 13P L/tNNiNG",  # 2016-000455CUA 16
        "org SAN FRANCISCO 13P UNNING",  # 2016-002830CUA 7
        "P LANNING D£PAR7MENT Page 7 of",  # 2016-005407CUA 17
        "SAN FRANCISCO 14P tAliNING",  # 2016-005143CUA 18
        "SAN PRANCtSCO",  # 2016-002498CUA 5
        "SAN FRANCISCQ 16P LMINING",  # 2016-014361CUA 11
        "zvww. s f-p lann ing. orb SAN FRARCISCO 14P LJ~NNING ~lPApTM",  # 2017-000519CUA 10
        "zvunu. org saw FRnNcisco 15P LARIMW6 DBPARTNlEMT",  # 2017-000519CUA 11
        "SAN FRANCISCO 14P L/\\NNING DEPARTMENT OPERATION GASE NO.",  # 2017-010871CUA 10
        "wwZas -Tannin orb SAN PPANCISCO",  # 2017-012465CUA 18
        "planning.org SAW FRANCISCO 8 P LANNINQi",  # 2017-012471CUA 18
        "P L/WNING",  # 2018-002906CUA 11
        "SAN FRANCISC6",  # 2016-005799CUA 20
        "SAN FRANCISCO 16P LANNINli DEPORTMENT",  # 2017-014693CUA 11
        "org DBPARTMENT",  # 2018-003141CUA 16
        "DEP/4RTMENT",  # 2016-000455CUA 20
        "ENT",  # 2019-006951CUA 5: the end of "PLANNING DEP4RTM ENT"
    ],
)
def test_the_page_footer_in_its_ocr_forms_is_cut_after_the_last_sentence(junk: str) -> None:
    text, leaks = cut(f"{REVOCATION} {junk}", older=True)
    assert text == REVOCATION
    assert [k for k, _ in leaks] == ["page header"]


@pytest.mark.parametrize(
    "heading",
    [
        "Operation",
        "O PERATION",
        "Monitoring - After Entitlement",
        "ITORING - AFTER ENTITLEMENT",
        "Monitoring",
        "Design – Compliance at Plan Stage",
        "Design – Compliance At Plan Stage",
        "D ESIGN",
        "Parking and Traffic",
        "Provisions",
        "Entertainment Commission – Noise Attenuation Conditions",
        "ENTERTAINMENT COMMISSION -NOISE ATTENUATION CONDITIONS Chapter 116 Residential Projects.",
        "STANDARD CONDITIONS",
        "MAXIMUM OCCUPANCY AND EVENTS",
    ],
)
def test_the_next_sections_heading_is_cut_after_the_last_sentence(heading: str) -> None:
    for older in (True, False):
        text, leaks = cut(f"{REVOCATION} {heading}", older)
        assert text == REVOCATION, heading
        assert [k for k, _ in leaks] == ["section heading"], heading


def test_a_heading_in_capitals_is_still_taken_by_the_older_clean_up() -> None:
    assert cut(f"{REVOCATION} OPERATION") == (REVOCATION, [])  # _HEADING, before tail_cut


def test_a_heading_after_a_contact_line_is_cut_and_the_contact_line_stays() -> None:
    # 2020-008474CUA 9: the reader split "F or", so the clean-up leaves the contact line (a separate decision)
    body = "Signage: The Project Sponsor shall develop a signage program for the Project."
    contact = (
        "F or information about compliance, contact Code Enforcement, Planning Department at 628.652.7463,"
    )
    text, leaks = cut(f"{body} {contact} Monitoring - After Entitlement")
    assert text == f"{body} {contact}"
    assert leaks == [("section heading", "Monitoring - After Entitlement")]
    url = "w ww.sfplanning.org"  # 2025-003645CUA 6
    assert tail_cut(f"{body} {contact} {url} Operation") == (
        len(f"{body} {contact} {url}"),
        "section heading",
    )


def test_a_file_path_and_the_plan_sets_title_are_cut() -> None:
    hours = "Hours of Operation: 6:00 a.m. to 10:00 p.m. daily."
    for junk, kind in (
        (
            "U:\\DVu\\Documents\\CUs\\3801 18th Street_2011.1138C\\Final Motion.doc",
            "file path",
        ),  # 2011.1138C 12
        (
            "SV:G:\\DOCUMENTS\\CONDITIONAL USES\\2010.0255C - 3111 Fillmore\\Motion.doc",
            "file path",
        ),  # 2010.0255C 20
        ("ESJ:", "file path"),  # 2010.0710C 25: the typist's initials before "G:\DOCUMENTS\...\18225.doc"
        ("EXHIBIT B: Plans & Renderings", "drawing sheet"),  # 2021-008505CUA 20
    ):
        text, leaks = cut(f"{hours} {junk}", older=True)
        assert text == hours, junk
        assert [k for k, _ in leaks] == [kind], junk


def test_page_furniture_between_two_words_is_taken_out() -> None:
    for before, junk, after in (
        ("the Zoning", "CASE NO.2015-005989CUA", "Administrator shall refer"),  # 2015-005989CUA 10
        ("which are not", "SAN FRANCISCO 15P LANNINti DEPARTMENT", "resolved by the"),  # 2016-015957CUA 11
        ("associated with", "P UINNING DEPARTMENT 11", "the business during"),  # 2017-000514CUA 6A
    ):
        body, taken = inside_cut(f"Litter: Litter {before} {junk} {after} hours.")
        assert body == f"Litter: Litter {before} {after} hours.", junk
        assert taken == [junk]
    # 2016-002372CUA 10: the footer between the last sentence and the contact line's end
    text, leaks = cut(
        "Sidewalk Maintenance: in compliance with the Department of Public Works Streets and Sidewalk Maintenance "
        "Standards. SAN PRAFlCISCO 1 O Works, 415-695-2017,",
        older=True,
    )
    assert text.endswith("Maintenance Standards. Works, 415-695-2017,")
    assert leaks == [("mid-condition page header", "SAN PRAFlCISCO 1 O")]


# 2016-008418CUA #15 as the clean-up left it: the OCR of an image page (page 18 of its PDF) after the last sentence
HOURS = (
    "Hours of Operation: The subject establishment is limited to the following hours of operation: Sunday through "
    "Saturday from 6 a.m. to 11 p.m."
)
IMAGE_PAGE_NOISE = (
    ":r~' ~ Yrsf~ ~:~\"a ~ ' I r'I_~~__ ~' \" 1_ ~L ~.li~ _yf~ ~ r _ I'~ ~ VIII ~~_~~~ ~I ',l a~~~{ r ~ ~±'~~~1~'~ "
    "~~~~ ~.J': I IT!~l-i~Y ~~A1~~i C~ ~~ 'I .11 ' ~~'~~. :~Y:al n1k 5~~~ f _ ~ ~ _~ ~~ rl: \".~ ~' ~''„;{ .~ hLl ~ F "
    "NL', \\~J:• ~' _? ~1;~ ~~'~ ='~_~LYt.•I'~.~J''' I~ I'n:P~ tint :~ ~~' r n :~lay~~.' ~.l~7~7'~~1 ~~ ,~~ .ti ~ - .7 "
    "-\"~J11~7C ~~ I -~A~~\"~ y' -4_~~: ~ -fir 'L"
)
# a few of the titles used on 10+ conditions, as letters only (the build passes them all to clean)
TITLES = {
    "rooftopmechanicalequipment",
    "sidewalkmaintenance",
    "revocationduetoviolationofconditions",
    "signage",
}
VOCAB = Vocabulary([("a", HOURS), ("b", REVOCATION), ("c", CONTACT)])


def test_an_image_pages_ocr_noise_after_the_last_sentence_is_cut() -> None:
    for vocab in (None, VOCAB):
        leaks: list[tuple[str, str]] = []
        text = clean(f"{HOURS} {IMAGE_PAGE_NOISE}", vocab, older=True, leaks=leaks)
        assert text == HOURS  # "to 11 p.m." stays: the cut is after the last sentence, not after "6 a.m."
        assert leaks == [(NOISE_KIND, IMAGE_PAGE_NOISE)]
    body = HOURS.partition(": ")[2]
    assert tail_cut(f"{body} {IMAGE_PAGE_NOISE}") == (len(body), NOISE_KIND)
    # with the page footer before it
    assert tail_cut(f"{body} SAN FRANCISCO 17P LANNING DEPARTMENT {IMAGE_PAGE_NOISE}") == (
        len(body),
        NOISE_KIND,
    )
    # a few stray symbols, a short piece, or words among the symbols are not taken as an image page
    for tail in (
        "~ ~ _",
        ":r~' ~ Yrsf~",
        "(see ~ Exhibit B)",
        "~ the rest of it ~ shall ~ follow ~ ~ ~ ~ ~ ~ ~",
    ):
        assert tail_cut(f"{body} {tail}") is None, tail


@pytest.mark.parametrize(
    ("before", "contact", "title"),
    [
        # 2018-010700CUA #8 (2019+): the next condition, #9, is missing from the data
        (
            "consistency with the Secretary of the Interior's Standards for the Treatment of Historic Properties.",
            "",
            "Rooftop Mechanical Equipment.",
        ),
        # 2018-015439CUA #8D and 2018-016549CUA #8D (2019+): what is kept of the contact line stays
        (
            "guidelines set forth by the Department of Public Works.",
            " Public Works at 415-554-.5810,",
            "Sidewalk Maintenance.",
        ),
        # 2018-002906CUA #6: after the web address left of its contact line, which stays
        (
            "for appropriate enforcement action under their jurisdiction.",
            " www.sf-planning.org",
            "Revocation due to Violation of Conditions.",
        ),
    ],
)
def test_the_next_conditions_title_after_the_last_sentence_is_cut(
    before: str, contact: str, title: str
) -> None:
    kept = f"Trash: Trash shall be contained and disposed of {before}{contact}"
    for older in (True, False):
        leaks: list[tuple[str, str]] = []
        assert clean(f"{kept} {title}", older=older, leaks=leaks, titles=TITLES) == kept
        assert leaks == [(TITLE_KIND, title)]
        assert clean(f"{kept} {title}", older=older) == f"{kept} {title}"  # not without the attested titles


def test_a_title_that_is_not_attested_or_not_the_whole_last_sentence_stays() -> None:
    body = "The Project Sponsor shall maintain the sidewalk."
    for tail in (
        "Rooftop Equipment.",  # not a title used on 10+ conditions
        "See Sidewalk Maintenance.",  # a sentence that ends with a title
        "sidewalk maintenance.",  # not in title case
        "Sidewalk Maintenance",  # no full stop
    ):
        assert tail_cut(f"{body} {tail}", titles=TITLES) is None, tail
    # no sentence end before it: where the condition ends is not known
    assert tail_cut("The Project Sponsor shall maintain the Sidewalk Maintenance.", titles=TITLES) is None


@pytest.mark.parametrize(
    ("before", "junk", "after"),
    [
        ("to not litter or", "SAN fRANCI$CO 1 7", "block driveways"),  # 2016-004115CUA 15
        ("the Zoning", "sam FRa~rcisco ~2", "Administrator shall refer"),  # 2016-000455CUA 11
        ("enclosed areas and clearly", "DBPARTMENT", "labeled and"),  # 2017-010871CUA 6
        ("Space for the collection and", "~ O PLANNING D<PARTMtNT", "storage of"),  # 2018-011926CUA 6
        ("collection and storage of", "'~ O", "recyclable and"),  # 2017-008461CUA 6
        ("to not litter or block", "~ 2", "driveways in"),  # 2019-004664CUA 11 (2019+)
    ],
)
def test_the_footer_garbled_by_ocr_between_two_words_is_taken_out(before: str, junk: str, after: str) -> None:
    body, taken = inside_cut(f"Litter: Litter {before} {junk} {after} the neighborhood.")
    assert body == f"Litter: Litter {before} {after} the neighborhood."
    assert taken == [junk]


@pytest.mark.parametrize(
    "text",
    [
        # hours and times
        "Hours of Operation: The business shall operate between 10 p.m. and 2 a.m., 7 days a week, and close by "
        "11:30 p.m. on Sundays.",
        # code sections, several in a row
        "Authorization: Conditional Use Authorization under Planning Code Sections 303, 721.21, 790.130, 721.41, "
        "790.22, 721.48, 790.38, for a use size exceeding 2,999 square feet.",
        "Authorization: pursuant to Planning Code Section(s) 121.2, 303, 316, 726.24, AND 726.41 within the "
        "Valencia Street NCD.",
        # phone numbers, contact lines and e-mail addresses
        "Community Liaison: The Project Sponsor shall appoint a liaison, who can be contacted at (415) 555-0100 or "
        "415-555-0101, or via email at liaison@example.com.",
        "Bicycle Parking: contact the SFMTA Bike Parking Program at bikeparking@sfmta.com to coordinate the "
        "installation of on-street bicycle racks.",
        # addresses and dates
        "Notices: The Project shall post notices at 4018 24th Street, 447 Broadway and 1331-1335 Polk Street by "
        "March 29, 2019 and April 10, 2019.",
        # plans, drawings and a scale mentioned in prose
        "Final Materials: in general conformance with plans drawn by the project architect, Drawn by Studio Inc., "
        "dated May 1, 2019 at a scale of 1/4 inch and stamped EXHIBIT B, with each Sheet No. listed.",
        # a motion and case number in prose
        "Prior Approvals: The conditions of Motion No. 19542 Case No. 2015-010314CUA shall continue to apply to "
        "the premises.",
        # an older condition whose title is in capitals
        "MAJOR AND MINOR CHANGES AND MODIFICATIONS OF CONDITIONS: Minor changes to the approved plans may be made "
        "with the approval of the Zoning Administrator.",
        # numbers in a list of license types
        "Alcohol: The addition of an ABC license type 47, 49, 59, or 75, while permitted with a Conditional Use, "
        "requires notice.",
        # "Operation" and the other headings' words inside a sentence, and at its end
        "Hours of Operation: Operation of the outdoor activity area shall end at 10 p.m., and the Operation and "
        "Design of the patio shall follow the approved Provisions.",
        "Monitoring: The Project Sponsor shall pay monitoring fees and work with the Planning Department on Design",
        "Use: The establishment shall remain in Operation",
        # "Page" in prose
        "Plans: The patio shall be built as shown on Page 3 of Exhibit B.",
        "Plans: The patio shall be built as shown on Page 3 of",
        # "San Francisco", "Planning" and "Department" in prose, at the end of the text too
        "Odor: The Project shall comply with the San Francisco Police Code and the Planning Department guidelines.",
        "Conformity: subject to the requirements of the San Francisco Planning Department",
        "Monitoring: pay fees as established under Planning Code Section 351(e) (1) and work with the Planning "
        "Department",
        "Signage: as approved by the City and County of San Francisco",
        # contact lines (left as they are: a separate decision), and what is left of one
        f"Hours: 8 a.m. to 10 p.m. daily. {CONTACT}",
        "Hours: 8 a.m. to 10 p.m. daily. For information about compliance, contact Code Enforcement, Planning "
        "Department at 628.652.7463,",
        "Monitoring: work with the Planning Department. pla Jill in gory",
        "Lighting: shall in no case be a nuisance to any surrounding property. orb",
        "Trash: as set forth by the Department of Public Works. Public Works.",
        # an attested title's words inside the last sentence; symbols and "San Francisco" in prose
        "Sidewalk: The Project Sponsor shall comply with the Sidewalk Maintenance Standards. See Signage below.",
        "Signage: The Project shall follow Section 3.1(a) ~ (c) and the San Francisco 2030 plan in the area.",
        "Hours: from 6 a.m. to 11 p.m. on Monday ~ Friday, and from 8 a.m. to 11 p.m. on Saturday and Sunday.",
    ],
)
def test_real_condition_text_is_never_cut(text: str) -> None:
    body = text.partition(": ")[2]
    assert leak_cut(text) is None
    assert leak_signatures(text) == []
    assert tail_cut(body) is None
    assert tail_cut(body, VOCAB, TITLES) is None
    assert inside_cut(body) == (body, [])
    for older in (True, False):
        assert cut(text, older) == (clean(text, older=older, cut_leaks=False), [])
        assert clean(text, VOCAB, older, [], titles=TITLES) == clean(text, VOCAB, older, cut_leaks=False)


def test_no_cut_without_a_sentence_end_before_the_leak() -> None:
    assert (
        leak_cut("Drawn by Job 9005 Date - Description - Revision 3/29/19 68.75 88.75 37.75 137.50") is None
    )
    # one piece of furniture after an unfinished sentence: where the condition ends is not known
    assert tail_cut("The Project Sponsor shall maintain the sidewalk and SAN FRANCISCO") is None
    assert tail_cut("The Project Sponsor shall maintain the sidewalk Operation") is None


# ---------------------------------------------------------------------------------------------------------------
# The built data, checked with patterns of this file's own (not the build's): nothing that is not the condition is
# left at the end of any condition. "The end" is what follows the condition's last sentence (or its contact line's
# phone number); a text that ends with a full stop has an empty end, and its last three words are checked too.

# the headings that start the condition groups in the motions' Exhibit A, as their letters
HEADINGS = [
    "PERFORMANCE",
    "OPERATION",
    "MONITORING",
    "MONITORING AFTER ENTITLEMENT",
    "MONITORING PROGRAM",
    "DESIGN",
    "DESIGN COMPLIANCE AT PLAN STAGE",
    "PARKING AND TRAFFIC",
    "PROVISIONS",
    "ENTERTAINMENT COMMISSION NOISE ATTENUATION CONDITIONS",
    "STANDARD CONDITIONS",
    "ADDITIONAL CONDITIONS",
    "MAXIMUM OCCUPANCY AND EVENTS",
    "MITIGATION MEASURES",
    "LOADING",
]
HEADING_LETTERS = [h.replace(" ", "") for h in HEADINGS]
SENTENCE_END = re.compile(r"[.;!?)][\"”’']?(?=\s)|\d{3}\s?[.\-‐]\s?\d{4}\s*,?")
TRAILING_FURNITURE = [
    re.compile(r"\bPage\s+\d{1,3}\s+(?:of|0#)\b"),
    re.compile(r"\b[CG]\S?SE\s+N[O0]\b\.?"),
    re.compile(r"\bMotion\s+(?:No|IVo|N0)\.?\s*\d{0,5}\s*$"),
    re.compile(r"\b(?:RECORD|Record)\s+No\.?\s*\d{4}"),
    re.compile(
        r"\b[Ss5][AaPp][NnWw]\s+\S*[A-Z]\S*[A-Z]"
    ),  # "SAN FRANCISCO", "saw FRnNcisco", "SAN PRANCtSCO"
    re.compile(
        r"(?<!\S)\d{0,3}\s?P\s?[A-Z/\\][A-Za-z/\\~]{3,8}\b"
    ),  # "13P L/tNNiNG", "P LANNING", "8 P LANNINQi"
]
# a word of the page footer, misread: two capitals or more and letters of FRANCISCO, PLANNING or DEPARTMENT
FOOTER_WORD = re.compile(
    r"(?=\S*[A-Z]\S*[A-Z])\S*(?i:ANC|NCI|CIS|ISC|ANN|NNI|NIN|ING|PAR|ART|RTM|TME|MEN|ENT)\S*"
)
FILE_PATH = re.compile(r"[A-Z]:\\|\\\S+\.docx?\b|\.docx?\s*$|(?<!\S)[A-Z]{2,4}:\s*$")
EXHIBIT_PLANS = re.compile(r"\bEXHIBIT\s+[BC]\b\s*:?\s*(?:Plans|Drawings|Renderings)", re.I)
TITLE_BLOCK = re.compile(
    r"\b(?:Drawn|Checked)\s+by\b|\bSheet\s+(?:No|Title|Index)\b|\bScale\s*:|\bJob\s+(?:No\.?\s*)?\d{3,}"
    r"|\bDRAFTING\b|\bSHEET\s+INDEX\b|\bPROJECT\s+INFORMATION\b|\bDate\s*-\s*Description\b"
)
DIMENSIONS = re.compile(
    r"(?:\b\d{1,4}\.\d{2}\s+){3,}\d{1,4}\.\d{2}\b|\d+'\s*-\s*\d+\"(?:\s+\S+){0,2}\s+\d+'\s*-\s*\d+\""
)


def symbol_tail(text: str) -> str | None:
    """What follows a sentence end when it is 20 characters or more and 30% or more of them are neither letters nor
    digits (a sentence has a few per cent): the OCR of an image page."""
    body = text.partition(": ")[2] if ": " in text[:140] else text
    for m in re.finditer(r"[.;!?)][\"”’']?\s", body):
        chars = re.sub(r"\s", "", body[m.end() :])
        if len(chars) >= 20 and sum(not ch.isalnum() for ch in chars) / len(chars) >= 0.3:
            return body[m.end() :]
    return None


def letters_of(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def trailing_title(text: str, titles: set[str]) -> str | None:
    """The last sentence, after a sentence end, a phone number or a web address, when on its own it is a title used
    on 10+ conditions (`titles`, letters only): the next condition's title."""
    body = text.partition(": ")[2] if ": " in text[:140] else text
    parts = re.split(r"[.;!?)][\"”’']?\s+|\d{4}\s*,\s+|\.(?:org|gov)\S*\s+", body.rstrip())
    last = parts[-1] if len(parts) > 1 else ""
    if last.endswith(".") and len(last.split()) <= 8 and letters_of(last) in titles:
        return last
    return None


def end_of(text: str) -> str:
    """What follows the condition's last sentence (or the phone number of its contact line); empty when the text
    ends with a sentence."""
    body = text.partition(": ")[2] if ": " in text[:140] else text
    if re.search(r"[.;!?)][\"”’']?$", body.rstrip()):
        return ""
    ends = [m.end() for m in SENTENCE_END.finditer(body)]
    return body[max(ends) :].strip() if ends else ""


def leftovers(text: str, titles: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """What is left at the end of a condition that is not the condition: (what kind, the text). `titles`: the titles
    used on 10+ conditions, as letters only."""
    end = end_of(text)
    last_words = " ".join(text.split()[-3:])
    found = []
    for pattern in TRAILING_FURNITURE:
        found += [f"page furniture: {m.group(0)}" for m in pattern.finditer(end)]
        found += [f"page furniture (last words): {m.group(0)}" for m in pattern.finditer(last_words)]
    for token in end.split() + last_words.split()[-2:]:
        core = token.strip(".,;:()'\"~`#")
        if len(re.sub(r"[^A-Za-z]", "", core)) >= 3 and FOOTER_WORD.fullmatch(core) and not core.istitle():
            found.append(f"footer word: {token}")
    # a heading after what is left of a contact line's web address ("www.sf- planning.org Operation")
    heading_end = re.sub(r"^(?:\S*(?:www|\.org|\.gov|/|planning)\S*\s+)+", "", end)
    letters = re.sub(r"[^A-Z]", "", heading_end.upper())
    # or a heading in capitals that opens the last sentence, with the next condition's title after it
    # ("ENTERTAINMENT COMMISSION -NOISE ATTENUATION CONDITIONS Chapter 116 Residential Projects.")
    body = text.partition(": ")[2] if ": " in text[:140] else text
    last = re.split(r"[.;!?)][\"”’']?\s", body.rstrip())[-1]
    if (caps := re.match(r"([A-Z][A-Z\s\-–&,]{4,}[A-Z])\s+[A-Z][a-z]", last)) and re.sub(
        r"[^A-Z]", "", caps.group(1)
    ) in HEADING_LETTERS:
        found.append(f"section heading opening the last sentence: {last}")
    if len(letters) >= 6 and any(
        h == letters or (len(letters) >= 8 and h.endswith(letters)) for h in HEADING_LETTERS
    ):
        found.append(f"section heading: {end}")
    elif any(  # "w ww.sfplanning.org Monitoring - After Entitlement": a web address split by OCR, then a heading
        letters.endswith(h) and re.search("ORG|WWW|GOV", letters[: -len(h)]) for h in HEADING_LETTERS
    ):
        found.append(f"section heading after a web address: {end}")
    for name, pattern in (("file path", FILE_PATH), ("plans title", EXHIBIT_PLANS)):
        found += [f"{name}: {m.group(0)}" for m in pattern.finditer(end)]
    found += [f"file path: {m.group(0)}" for m in re.finditer(r"[A-Z]:\\\S*|\S+\.docx?\b", text)]
    for name, pattern in (("title block", TITLE_BLOCK), ("dimensions", DIMENSIONS)):
        found += [f"{name}: {m.group(0)}" for m in pattern.finditer(end)]
    if (noise := symbol_tail(text)) is not None:
        found.append(f"symbols after the last sentence: {noise[:60]}")
    if (title := trailing_title(text, set(titles))) is not None:
        found.append(f"next condition's title: {title}")
    return found


def test_the_independent_patterns_find_every_kind_of_leftover() -> None:
    """The patterns below the line find what the build cut (so an empty result over the data means something)."""
    for junk in (
        "Page 3 of 5SAN",
        "SAN FRANCISCO 13P L/tNNiNG",
        "saw FRnNcisco 15P LARIMW6 DBPARTNlEMT",
        "P L/WNING",
        "DEP/4RTMENT",
        "ENT",
        "CASE NO. 2017-p00519CUA",
        "Operation",
        "O PERATION",
        "ITORING - AFTER ENTITLEMENT",
        "Design – Compliance at Plan Stage",
        "U:\\DVu\\Documents\\CUs\\Final Motion.doc",
        "ESJ:",
        "EXHIBIT B: Plans & Renderings",
        "DRAFTING HOMES Drawn by Job 9005",
        "N 68.75 88.75 37.75 137.50 38.75 Powell St",
    ):
        assert leftovers(f"{REVOCATION} {junk}"), junk
    assert leftovers(f"{REVOCATION[:-1]} DEP/fRTMENT Motion IVo.")  # furniture ending in a full stop
    assert leftovers(f"{REVOCATION} www.sf- planning.org Operation")
    assert leftovers(f"{REVOCATION} Planning Department at 628.652.7331 , w ww.sfplanning.org Monitoring")
    assert leftovers(
        f"{REVOCATION} ENTERTAINMENT COMMISSION -NOISE ATTENUATION CONDITIONS Chapter 116 Residential."
    )
    assert leftovers(f"{HOURS} {IMAGE_PAGE_NOISE}")
    assert leftovers(f"{HOURS} :r~' ~ Yrsf~ ~:~ _yf~ ~ r _ I'~ ~ VIII.")
    for kept in ("", " Public Works at 415-554-.5810,", " www.sf-planning.org"):
        assert leftovers(f"{REVOCATION}{kept} Sidewalk Maintenance.", TITLES), kept
        assert not leftovers(f"{REVOCATION}{kept} Sidewalk Maintenance."), kept  # not without the titles
    assert leftovers(f"{REVOCATION} Rooftop Mechanical Equipment.", TITLES)
    assert not leftovers(REVOCATION, TITLES)
    assert not leftovers(f"{REVOCATION} {CONTACT}", TITLES)
    assert not leftovers(f"{REVOCATION} See Sidewalk Maintenance.", TITLES)
    assert not leftovers(HOURS, TITLES)


@pytest.fixture(scope="module")
def data() -> dict:
    return json.loads(DATA.read_text())


@pytest.fixture(scope="module")
def attested(data: dict) -> set[str]:
    """Titles used on 10 or more conditions in the data, as letters only, counted here."""
    counts: dict[str, int] = {}
    for c in data["conditions"]:
        counts[letters_of(c["title"])] = counts.get(letters_of(c["title"]), 0) + 1
    return {t for t, n in counts.items() if n >= 10}


def test_the_built_data_has_nothing_left_at_the_end_of_a_condition_that_is_not_the_condition(
    data: dict, attested: set[str]
) -> None:
    left = [(c["record"], c["number"], x) for c in data["conditions"] for x in leftovers(c["text"], attested)]
    assert left == []


def test_the_built_data_has_no_symbol_tail_and_no_next_conditions_title(
    data: dict, attested: set[str]
) -> None:
    assert {
        "sidewalkmaintenance",
        "rooftopmechanicalequipment",
        "revocationduetoviolationofconditions",
    } <= attested
    by_key = {(c["record"], c["number"]): c for c in data["conditions"]}
    assert [k for k, c in by_key.items() if symbol_tail(c["text"])] == []
    assert [k for k, c in by_key.items() if trailing_title(c["text"], attested)] == []
    hours = by_key[("2016-008418CUA", "15")]
    assert hours["text"] == HOURS and hours["readable"]
    assert by_key[("2018-010700CUA", "8")]["text"].endswith("for the Treatment of Historic Properties.")
    for record in (
        "2018-015439CUA",
        "2018-016549CUA",
    ):  # the contact line's piece stays (the owner's decision)
        assert by_key[(record, "8D")]["text"].endswith(
            "Department of Public Works. Public Works at 415-554-.5810,"
        )
    assert by_key[("2018-002906CUA", "6")]["text"].endswith("under their jurisdiction. www.sf-planning.org")


def test_no_page_footer_is_left_inside_a_condition(data: dict) -> None:
    footer = re.compile(
        r"\bS[A-Z]N\s+[A-Z]\S{5,10}\s+\d{1,3}(?:\s?P\s?[A-Z/\\]|\s[O0]?\s?[A-Z][a-z]+,\s\d{3})"
        r"|\bC[A-Z]SE\s+N[O0]\.?\s*\d{4}[-.]\d|(?<=[a-z])\s+P\s?[A-Z]{2,}NN\S*\s+DEPARTMENT\b"
        # the footer garbled by OCR: a page number after a tilde ("~ 2", "'~ O PLANNING D<PARTMtNT"), the footer's
        # first line ("SAN fRANCI$CO 1 7", "sam FRa~rcisco ~2"), DEPARTMENT misread in capitals ("DBPARTMENT")
        r"|[a-z]\s+'?~\s?[O0\d]{1,2}\s+(?:PLANNING\s+\S+\s+)?[a-z]"
        r"|\b[Ss][A-Za-z][NnMmWw]\s+[Ff][Rr][A-Za-z~$]{5,8}\s+~?\d{1,2}(?:\s\d)?\s+[A-Za-z]"
        r"|[a-z]\s+D[A-Z<$£]{7,10}T\s+[a-z]"
    )
    for text in (
        "or SAN fRANCI$CO 1 7 block",
        "Zoning sam FRa~rcisco ~2 Administrator",
        "clearly DBPARTMENT labeled",
        "and ~ O PLANNING D<PARTMtNT storage",
        "of '~ O recyclable",
        "block ~ 2 driveways",
    ):
        assert footer.search(text), text
    assert [(c["record"], c["number"]) for c in data["conditions"] if footer.search(c["text"])] == []


def test_the_built_data_ends_2018_015652cua_28_at_its_last_sentence(data: dict) -> None:
    (c,) = [c for c in data["conditions"] if (c["record"], c["number"]) == ("2018-015652CUA", "28")]
    assert c["text"].endswith("between midnight and 6 a.m.")
    assert "Drawn by" not in c["text"] and "68.75" not in c["text"]
    assert c["readable"]


def test_the_list_names_every_cut_counted_in_text_quality(data: dict) -> None:
    quality = data["text_quality"]
    counted = sum(n for k, n in quality.items() if k.endswith(" text cut off"))
    rows = [line for line in LIST.read_text().splitlines() if re.match(r"\| \d{4}-\d{2}-\d{2} \|", line)]
    assert counted == len(rows) == 190
    by_key = {(c["record"], c["number"]): c for c in data["conditions"]}
    kinds = {}
    for line in rows:
        decided, record, number, era, kind, removed = [x.strip() for x in line.split(" | ")[:6]]
        c = by_key[(record, number)]
        assert decided.lstrip("| ") == c["decided"]
        assert era == ("2019+" if c["decided"] >= "2019-01-01" else "before 2019")
        removed = removed.replace("\\|", "|")
        if kind == "mid-condition page header":
            assert removed not in c["text"], (record, number)
        else:
            assert not c["text"].endswith(removed), (record, number)
        kinds[kind] = kinds.get(kind, 0) + 1
    assert kinds == {
        k.removesuffix(" text cut off"): n for k, n in quality.items() if k.endswith(" text cut off")
    }


def test_the_noise_cut_does_not_depend_on_the_system_word_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI has no /usr/share/dict/words: the cut must land at the same place without it."""
    import condition_text

    monkeypatch.setattr(condition_text, "DICT", Path("/nonexistent/words"))
    for vocab in (None, Vocabulary([("a", HOURS), ("b", REVOCATION), ("c", CONTACT)])):
        leaks: list[tuple[str, str]] = []
        assert clean(f"{HOURS} {IMAGE_PAGE_NOISE}", vocab, older=True, leaks=leaks) == HOURS
        assert leaks == [(NOISE_KIND, IMAGE_PAGE_NOISE)]
