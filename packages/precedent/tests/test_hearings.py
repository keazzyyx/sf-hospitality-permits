"""SF Planning Commission hearing documents (motions / minutes) → enrichment rows. No network."""

from __future__ import annotations

import datetime as dt
import io
import json
import shutil
from pathlib import Path

import httpx
import pytest
import respx
from pypdf import PdfWriter

from precedent.pdftext import extract_text, find_sections, read_pdf, strip_running_headers
from precedent.sources import sf_planning_hearings as hearings
from precedent.sources.base import make_client

FX = Path(__file__).parent / "fixtures" / "sf_planning_hearings"
HILO = FX / "20261021T204000000000Z-2011.0097CUA-02-motion.json"  # bar hours change, no public comment
CASEMENTS = (
    FX / "20261021T204000000000Z-2022-008254CUA-motion.json"
)  # outdoor area + entertainment, opposition
DENIAL = FX / "20261021T204000000000Z-2025-006395CUA-motion.json"  # formula retail gym, disapproved
MINUTES = FX / "20261021T204000000000Z-minutes-20250501.json"  # adopted minutes excerpt, May 1 2025


def _one(path: Path):  # type: ignore[no-untyped-def]
    batch = hearings.parse(path)
    assert len(batch.applications) == 1
    return batch.applications[0]


def _copy_fixture(sidecar: Path, dest_root: Path, **meta_updates: object) -> Path:
    """Copy a sidecar + its PDF into dest_root/sf_planning_hearings/, optionally editing meta."""
    folder = dest_root / "sf_planning_hearings"
    (folder / "pdf").mkdir(parents=True, exist_ok=True)
    env = json.loads(sidecar.read_text())
    shutil.copy(FX / env["meta"]["pdf"], folder / env["meta"]["pdf"])
    env["meta"].update(meta_updates)
    out = folder / sidecar.name
    out.write_text(json.dumps(env))
    return out


# ---- motions ------------------------------------------------------------------------------------


def test_motion_hours_condition_bar() -> None:
    a = _one(HILO)
    meta = json.loads(HILO.read_text())["meta"]
    assert a.id == "datasf_planning:2011.0097CUA-02"
    assert a.source == "sf_planning_hearings" and a.source_id == "2011.0097CUA-02"
    assert a.kind == "cua" and a.permit_type == "Conditional Use Authorization"
    assert a.source_url == meta["url"] == a.extra["motion_url"]
    assert a.outcome == "approved_with_conditions"
    assert a.decided_at == dt.date(2024, 11, 14)
    assert a.hours_close == "02:00"  # "6 a.m. to 2 a.m. every day"
    assert a.late_night is True
    assert any(c.startswith("Hours of Operation:") for c in a.conditions)
    assert a.opposition_noted is False  # "Department staff have not received any public comment"
    assert a.extraction_confidence == "high"
    assert a.extra["motion_number"] == "21646" and a.extra["vote"] == "6-0"
    assert a.extra["source_kind"] == "motion" and a.extra["pdf_pages"] == 4
    assert a.extra["hearing_date"] == "2024-11-14"
    assert "21646" in (a.decision_summary or "")
    assert a.address == "1423 Polk Street" and a.parcel == "0646/003"
    assert "bar" in a.use_types


def test_motion_conditioned_approval_with_opposition() -> None:
    a = _one(CASEMENTS)
    assert a.outcome == "approved_with_conditions"
    assert len(a.conditions) >= 3
    assert all(len(c) <= 300 for c in a.conditions)
    joined = " | ".join(a.conditions)
    assert "Community Liaison" in joined
    assert "soundproofed" in joined  # Eating and Drinking Uses (B) noise condition
    assert "Entertainment Commission" in joined
    assert not any(c.startswith(("Validity", "Enforcement", "Revocation")) for c in a.conditions)
    assert a.hours_close == "22:00"  # Outdoor Activity Area "between 9:00 a.m. and 10:00 p.m. daily"
    assert a.late_night is False
    assert a.extra["hours_close_mentioned"] == "02:00"  # indoor hours in the findings
    assert a.opposition_noted is True  # "three comments in opposition"
    assert a.extra["vote"] == "5-0" and a.extra["motion_number"] == "21497"
    assert a.extraction_confidence == "high"
    summary = a.decision_summary or ""
    assert "Motion No. 21497" in summary and "Community Liaison" in summary
    assert {"hours", "entertainment", "community_liaison", "noise"} <= set(a.extra["condition_categories"])


def test_motion_denial() -> None:
    a = _one(DENIAL)
    assert a.outcome == "denied"
    assert a.conditions == []
    assert a.opposition_noted is True  # fifteen letters in opposition
    assert a.extra["vote"] == "6-1"
    assert a.decided_at == dt.date(2025, 10, 2)
    assert "21840" in (a.decision_summary or "") and "disapproved" in (a.decision_summary or "")
    assert a.extraction_confidence == "high"


def test_motion_takes_hearing_opposition_from_minutes(tmp_path: Path) -> None:
    side = _copy_fixture(HILO, tmp_path, minutes_item={"opposition": True, "oppose": 2, "minutes_url": "u"})
    a = _one(side)
    assert a.opposition_noted is True
    assert a.extra["hearing_speakers_opposed"] == 2


# ---- minutes ------------------------------------------------------------------------------------


def test_minutes_rows_are_decisive_cua_items_only() -> None:
    batch = hearings.parse(MINUTES)
    assert [a.id for a in batch.applications] == ["datasf_planning:2017-003559CUA-03"]
    a = batch.applications[0]
    assert a.outcome == "approved_with_conditions"
    assert a.decided_at == dt.date(2025, 5, 1)
    assert a.opposition_noted is True  # one "-" speaker
    assert a.extraction_confidence == "medium"  # action + vote only
    assert a.extra["source_kind"] == "minutes"
    assert a.extra["motion_number"] == "21731" and a.extra["vote"] == "7-0"
    assert a.extra["speakers_oppose"] == 1 and a.extra["speakers_support"] >= 10
    assert "21731" in (a.decision_summary or "")
    assert a.address == "3700 CALIFORNIA STREET"


def test_minutes_skip_records_already_covered_by_a_motion(tmp_path: Path) -> None:
    side = _copy_fixture(MINUTES, tmp_path, skip_records=["2017-003559CUA-03"])
    assert len(hearings.parse(side)) == 0


def test_minutes_item_parser_handles_continuances_and_same_as_speakers() -> None:
    text = read_pdf((FX / json.loads(MINUTES.read_text())["meta"]["pdf"]).read_bytes()).text
    items = {i.item: i for i in hearings.parse_minutes_items(text)}
    assert items["12"].records == ["2017-003559CUA-03"]
    assert items["12"].oppose == 1
    assert items["13"].opposition is False  # speakers present, none opposed


# ---- scanned / broken PDFs ----------------------------------------------------------------------


def _blank_pdf() -> bytes:
    w = PdfWriter()
    w.add_blank_page(612, 792)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


@pytest.mark.parametrize("pdf_bytes", [_blank_pdf(), b"%PDF-1.4 truncated garbage"])
def test_scanned_or_broken_pdf_is_low_confidence(tmp_path: Path, pdf_bytes: bytes) -> None:
    side = _copy_fixture(HILO, tmp_path)
    pdf = side.parent / json.loads(side.read_text())["meta"]["pdf"]
    pdf.write_bytes(pdf_bytes)
    a = _one(side)
    assert a.extraction_confidence == "low"
    assert a.id == "datasf_planning:2011.0097CUA-02"
    assert a.conditions == [] and a.opposition_noted is None and a.outcome == "unknown"
    assert a.decided_at == dt.date(2024, 11, 14)  # from the sidecar's hearing date


def test_missing_pdf_yields_empty_batch(tmp_path: Path) -> None:
    side = _copy_fixture(HILO, tmp_path)
    (side.parent / json.loads(side.read_text())["meta"]["pdf"]).unlink()
    assert len(hearings.parse(side)) == 0


# ---- helpers ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "The subject establishment is limited to the following hours of operation: 6 a.m. to 2 a.m. every day.",
            "02:00",
        ),
        ("Hours of operation shall be limited to 2:00 a.m.", "02:00"),
        ("The establishment shall close by 2:00 a.m. nightly.", "02:00"),
        ("The establishment shall not operate between 2a.m. to 6a.m.", "02:00"),
        ("limited to between 9:00 a.m. and 10:00 p.m. daily", "22:00"),
        ("permitted hours of entertainment between noon and 1:30 am daily", "01:30"),
        ("open until midnight on weekends", "00:00"),
        ("no hours mentioned here", None),
    ],
)
def test_closing_hour(text: str, expected: str | None) -> None:
    assert hearings.closing_hour([text]) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The Department received one email from a neighbor in opposition to the project.", True),
        (
            "received at least 37 comments in support of the Project and at three comments in opposition.",
            True,
        ),
        (
            "The Department has received 4 messages of support and one letter of opposition to the Project.",
            True,
        ),
        (
            "The Department also received 22 letters in opposition, including from the Pacific Heights Residents Association",
            True,
        ),
        ("Department staff have not received any public comment regarding the Project.", False),
        ("Department staff received twelve public comments. All twelve were letters of support.", False),
        ("The Department has received no opposition to the Project.", False),
        ("The Sponsor held a pre-application meeting.", None),
    ],
)
def test_opposition_from_comment(text: str, expected: bool | None) -> None:
    assert hearings.opposition_from_comment(text) is expected


def test_rejoin_split_words() -> None:
    assert hearings.rejoin_split_words("A pproved with Conditions") == "Approved with Conditions"
    assert hearings.rejoin_split_words("A motion was A dopted") == "A motion was Adopted"
    assert (
        hearings._minutes_outcome(hearings.rejoin_split_words("A pproved with Conditions"))
        == "approved_with_conditions"
    )


def test_parse_vote_tolerates_broken_labels() -> None:
    ayes, nays, vote = hearings.parse_vote(
        "AYE\nS: Campbell, McGarry, So\nNAYS: None\nABSENT: None\nADOPTED: September 12, 2024"
    )
    assert ayes == ["Campbell", "McGarry", "So"] and nays == [] and vote == "3-0"


def test_pick_motion_prefers_latest_numbered_motion_pdf() -> None:
    listing = {
        "a": {
            "ClassName": "CPC Motions and Resolutions",
            "Name": "M-21334.pdf",
            "LastModified": "2023-07-13",
            "docLink": "u1",
        },
        "b": {
            "ClassName": "CPC Motions and Resolutions",
            "Name": "M-21334 corr.pdf",
            "LastModified": "2023-11-27",
            "docLink": "u2",
        },
        "c": {
            "ClassName": "CPC Motions and Resolutions",
            "Name": "M-21334v4.docx",
            "LastModified": "2023-12-01",
            "docLink": "u3",
        },
        "d": {
            "ClassName": "Commission Submittal",
            "Name": "2022-005675CUA.pdf",
            "LastModified": "2024-01-01",
            "docLink": "u4",
        },
    }
    assert (hearings.Fetcher.pick_motion(listing) or {})["docLink"] == "u2"
    assert hearings.Fetcher.pick_motion({"x": {"ClassName": "Notification", "Name": "n.pdf"}}) is None
    assert hearings.Fetcher.pick_motion(None) is None


# ---- pdftext ------------------------------------------------------------------------------------

MOTION_TEXT = """Planning Commission Motion No. 21000
HEARING DATE: MARCH 3, 2022
FINDINGS
1. The above recitals are accurate.
5. Public Comment. The Department received two letters in opposition.
6. Planning Code Compliance. The project complies.
DECISION
the Commission hereby APPROVES Conditional Use Application No. 2021-000001CUA subject to the conditions
contained in "EXHIBIT A" of this motion.
APPEAL AND EFFECTIVE DATE OF MOTION: Any aggrieved person may appeal this Conditional Use Authorization.
EXHIBIT A
Authorization
This authorization is for a bar.
Conditions of Approval, Compliance,
Monitoring, and Reporting
1. Validity. Valid for three years.
2. Hours of Operation. The establishment shall close by 2:00 a.m.
EXHIBIT B
plans
SPEAKERS: + Jane Doe – Support
- John Roe – Noise
ACTION: Approved with Conditions
"""


def test_find_sections_locates_blocks() -> None:
    s = find_sections(MOTION_TEXT)
    assert "APPROVES" in s["decision"] and "aggrieved" not in s["decision"]
    assert s["public_comment"].lstrip(". ").startswith("The Department received two letters in opposition")
    assert "Planning Code Compliance" not in s["public_comment"]
    assert "Hours of Operation" in s["conditions"] and "Validity" in s["conditions"]
    assert "plans" not in s["conditions"] and "Authorization" not in s["conditions"]
    assert "Authorization" in s["exhibit_a"]
    assert "Public Comment" in s["findings"] and "DECISION" not in s["findings"]
    assert "John Roe" in s["speakers"] and "ACTION" not in s["speakers"]


def test_find_sections_ignores_inline_mentions_and_falls_back_to_exhibit_a() -> None:
    text = 'subject to conditions contained in the attached "EXHIBIT A" and\nDecision\nThe Commission hereby DENIES the application.\nEXHIBIT A\n1. Hours of Operation. Until 11 p.m.\n'
    s = find_sections(text)
    assert s["decision"].startswith("The Commission hereby DENIES")
    assert s["conditions"] == s["exhibit_a"]
    assert s["conditions"].startswith("1. Hours of Operation")
    assert find_sections("") == {}


def test_strip_running_headers_keeps_vote_lines() -> None:
    pages = [
        f"Motion No. 21000  RECORD NO. 2021-000001CUA\nMarch 3, 2022  1 Main Street\n{n}\nBody {n}\nNAYS: None\n"
        for n in range(1, 4)
    ]
    clean = strip_running_headers("\f".join(pages))
    assert "RECORD NO" not in clean and "1 Main Street" not in clean
    assert clean.count("NAYS: None") == 3 and "Body 2" in clean


def test_extract_text_is_tolerant() -> None:
    assert extract_text(_blank_pdf()) == ""
    assert extract_text(b"not a pdf at all") == ""
    real = FX / json.loads(HILO.read_text())["meta"]["pdf"]
    assert "Hi-Lo Club" in extract_text(real.read_bytes())
    assert read_pdf(real.read_bytes(), max_pages=1).pages == 4


# ---- fetch (mocked HTTP) ------------------------------------------------------------------------

LIST_HTML = """
<div class="view-content"><h3>May 2025</h3>
<article about="/event/planning-commission-290" class="x"><div class="date-circle"><div class="month">May</div>
<div class="day">1</div></div></article>
<article about="/event/planning-commission-cancelled-12" class="x"><div class="date-circle"><div class="month">Apr</div>
<div class="day">24</div></div></article>
<h3>April 2025</h3>
<article about="/event/planning-commission-289" class="x"><div class="date-circle"><div class="month">Apr</div>
<div class="day">17</div></div></article></div>
"""


@respx.mock
async def test_fetch_minutes_then_motions_with_cache_and_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hearings, "RATE_LIMIT", 0)
    monkeypatch.setenv("PLANNING_HEARINGS_MAX_DOCS", "3")
    minutes_pdf = (FX / json.loads(MINUTES.read_text())["meta"]["pdf"]).read_bytes()
    motion_pdf = (FX / json.loads(HILO.read_text())["meta"]["pdf"]).read_bytes()
    base = "https://citypln-m-extnl.sfgov.org/Commissions/Agenda_or_Minutes/"

    def list_page(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=LIST_HTML if request.url.params.get("page") == "0" else "<div></div>")

    lst = respx.get(hearings.CPC_LIST_URL).mock(side_effect=list_page)
    may1 = respx.get(base + "20250501_cpc_min.pdf").mock(
        return_value=httpx.Response(200, content=minutes_pdf)
    )
    respx.get(base + "20250417_cpc_min.pdf").mock(return_value=httpx.Response(404))
    respx.get(base + "20250417_cal_min.pdf").mock(return_value=httpx.Response(404))
    listing = {
        "doc0_1": {
            "ClassName": "CPC Motions and Resolutions",
            "Name": "M-21731.pdf",
            "LastModified": "2025-05-20T00:00:00Z",
            "docLink": "https://citypln-m-extnl.sfgov.org/External/link.ashx?Action=Download&objectGUID={X}",
        }
    }
    mfiles = respx.get(hearings.MFILES_URL).mock(return_value=httpx.Response(200, text=json.dumps(listing)))
    dl = respx.get("https://citypln-m-extnl.sfgov.org/External/link.ashx").mock(
        return_value=httpx.Response(200, content=motion_pdf)
    )

    raw = tmp_path / "raw"
    async with make_client() as client:
        paths = await hearings.fetch(client, raw, dt.date(2025, 1, 1))
    kinds = [json.loads(p.read_text())["meta"]["source_kind"] for p in paths]
    assert kinds == ["minutes", "motion"]
    motion_meta = json.loads(paths[1].read_text())["meta"]
    assert motion_meta["record_number"] == "2017-003559CUA-03"
    assert motion_meta["minutes_item"]["motion_number"] == "21731"
    assert mfiles.call_count == 1 and dl.call_count == 1 and may1.call_count == 1
    assert len(list((raw / "sf_planning_hearings" / "pdf").glob("*.pdf"))) == 2
    assert all(p.parent.name == "sf_planning_hearings" for p in paths)
    assert len(hearings.parse(paths[0])) == 1 and len(hearings.parse(paths[1])) == 1

    # second run: everything cached → no downloads, no lookups, nothing new to ingest
    async with make_client() as client:
        again = await hearings.fetch(client, raw, dt.date(2025, 1, 1))
    assert again == []
    assert mfiles.call_count == 1 and dl.call_count == 1 and may1.call_count == 1
    assert lst.call_count >= 2


@respx.mock
async def test_fetch_respects_document_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hearings, "RATE_LIMIT", 0)
    monkeypatch.setenv("PLANNING_HEARINGS_MAX_DOCS", "1")
    minutes_pdf = (FX / json.loads(MINUTES.read_text())["meta"]["pdf"]).read_bytes()
    respx.get(hearings.CPC_LIST_URL).mock(return_value=httpx.Response(200, text=LIST_HTML))
    respx.get(url__startswith="https://citypln-m-extnl.sfgov.org/Commissions/").mock(
        return_value=httpx.Response(200, content=minutes_pdf)
    )
    mfiles = respx.get(hearings.MFILES_URL).mock(return_value=httpx.Response(200, text="{}"))
    async with make_client() as client:
        paths = await hearings.fetch(client, tmp_path, dt.date(2025, 1, 1))
    assert len(paths) == 1  # the single allowed document is one minutes PDF; no motion downloads
    assert mfiles.call_count == 0


def test_planning_candidates_from_saved_dataset_pages(tmp_path: Path) -> None:
    folder = tmp_path / "datasf_planning"
    folder.mkdir()
    rows = [
        {
            "record_id": "2024-001579CUA",
            "record_type": "CUA",
            "record_status": "Closed - Approved",
            "close_date": "2025-01-23T00:00:00.000",
        },
        {
            "record_id": "2023-002974CUA",
            "record_type": "CUA",
            "record_status": "Closed - Withdrawn",
            "close_date": "2023-09-06T00:00:00.000",
        },
        {
            "record_id": "2025-012220PRJ",
            "record_type": "PRJ",
            "record_status": "Closed",
            "close_date": "2026-04-01T00:00:00.000",
        },
        {
            "record_id": "2015-012697CUA",
            "record_type": "CUA",
            "record_status": "Closed - Approved",
            "close_date": "2016-02-01T00:00:00.000",
        },
    ]
    (folder / "20261021T000000Z-y673-d69b-p0000.json").write_text(
        json.dumps({"meta": {"fetched_at": "2026-10-21T00:00:00+00:00"}, "data": rows})
    )
    f = hearings.Fetcher(httpx.AsyncClient(), tmp_path, dt.date(2021, 10, 21))
    assert f.planning_candidates() == {"2024-001579CUA": dt.date(2025, 1, 23)}


def test_lettered_sub_items_survive_compliance_lines_and_parenthesised_letters() -> None:
    from precedent.sources.sf_planning_hearings import all_conditions, operational_conditions

    section = """
 12. Eating and Drinking Uses. Eating and Drinking Uses shall be subject to the following conditions:

     A. The business operator shall maintain the main entrance and all sidewalks in a clean condition.
        For information about compliance, contact the Bureau of Street Use and Mapping, 415-554-5810.

     B. When located within an enclosed space, the premises shall be adequately soundproofed for noise.
        For information about compliance, contact the Environmental Health Section, 415-252-3800.

     C. Appropriate odor control equipment shall be installed to prevent noxious or offensive odors.
        For information about compliance, contact the Bay Area Air Quality Management District.

     D. Garbage, recycling, and compost containers shall be kept within the premises and hidden from view.

 13. Good Neighbor Policies. The establishment shall comply with the following:

     (A) Employees shall walk a 100-foot radius to collect litter each night;

     (B) The establishment shall provide outside lighting sufficient to illuminate the sidewalk;
"""
    numbers = [c.number for c in all_conditions(section)]
    assert numbers == ["12A", "12B", "12C", "12D", "13A", "13B"]
    by_number = {c.number: c for c in all_conditions(section)}
    assert "odor control" in by_number["12C"].text and "odor" in by_number["12C"].categories
    assert "For information about compliance" not in by_number["12A"].text
    assert {"12C", "12D"} <= {c.number for c in operational_conditions(section)}


def test_operative_verb_split_by_pdf_spacing() -> None:
    from precedent.sources.sf_planning_hearings import _outcome_from_decision

    decision = "the Commission hereby AP PROVES Conditional Use Authorization No. 2024-009436CUA subject to conditions"
    assert _outcome_from_decision(decision, decision, True) == "approved_with_conditions"
    assert _outcome_from_decision("the Commission hereby DIS APPROVES the application", "", False) == "denied"
