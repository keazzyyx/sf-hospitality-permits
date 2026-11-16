"""Pure helpers for report format 3: display labels, source notes, comparable-case fields, the site history
(which records are on file at the report's own address or parcel), the rows and the overall line as the rules
set them (`app.memo.pathway`), and the report as plain text. No model writes any of it.

Nothing here calls a model or a store; the runner feeds these functions and assembles the Memo from them.
`app.memo.pathway` imports this module, so this module takes the rules' result as data (`Determinations`) and
never imports the rule engine.

Rule table v2 is carried through unchanged: a row's status note, its referral steps and its missing inputs, the
eleven triggers, the three change-of-use answers and the rules date are printed as the rules gave them. The
headline findings (app.memo.pathway rule 9, change of 2026-11-16) are printed first, before the overall line,
each with its status and whether it depends on an answer not given (`headline_lines`). Every
heading and fixed sentence this module adds around them is in one table, `REPORT_TEXT`, with the label tables
next to it (`TRIGGER_CONTROL_LABELS`, `CHANGE_QUESTION_LABELS`, `CHANGE_ANSWER_LABELS`, `TIMING_GROUPS`), so a
reviewer can check each fixed sentence in one place.

Timing: a number of days drawn from the records is always for one outcome (approved, denied, withdrawn,
cancelled, outcome not recorded) or, for a case still pending, its age so far. `decision_times` groups the
comparables that way; no figure here combines outcomes, and none is a mean or a median.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, NamedTuple

from precedent.models import Application
from precedent.store.base import Nearby

from app.core.config import settings
from app.memo.analytics import record_kind
from app.models.memo import (
    APPROVAL_AREA_LABELS,
    NO_HISTORY_AREAS,
    NO_HISTORY_NOTE,
    PLANNING_USE_LABELS,
    RECORD_KIND_LABELS,
    SITE_HISTORY_LIMIT,
    STATUS_DEFINITIONS,
    STATUS_SEVERITY,
    ApprovalStatus,
    ChangeAnswers,
    ComparableCase,
    CountedDecision,
    Determinations,
    Memo,
    MemoApprovalRow,
    MemoFact,
    MemoOverall,
    Pathway,
    RowDetermination,
    RuleLine,
    SiteHistory,
    SiteHistoryEntry,
    SourceNote,
    TriggerFinding,
)

# Every value of the contract's PlanningUse: its PLANNING_USE_LABELS has no entry for "nighttime_entertainment";
# the label is § 102's (the same table as app.memo.pathway.USE_LABELS, which imports this module).
USE_LABELS: dict[str, str] = {**PLANNING_USE_LABELS, "nighttime_entertainment": "Nighttime Entertainment"}


# ---- display labels ------------------------------------------------------------------------------
def status_label(status: str) -> str:
    """'further_review' → 'Further review' (the label each definition opens with)."""
    return STATUS_DEFINITIONS[status].split(":", 1)[0] if status in STATUS_DEFINITIONS else status


# Every heading and fixed sentence the report prints around what rule table v2 decided. The rule lines, the
# status notes, the missing-input phrases and the referral steps themselves come from the rules, unchanged.
REPORT_TEXT: dict[str, str] = {
    # first in the report: the headline findings (app.memo.pathway rule 9)
    "headline_heading": "Read this first",
    "headline_hint": (
        "What changes this business's plans at this address: a public hearing it must go through, or a rule that "
        "bars it. A finding that turns on something not yet known says so, and the report names what is missing."
    ),
    "headline_definite": "Set by rule",
    "headline_contingent": "Depends on an answer not given",
    # under a row
    "steps_heading": "Steps inside this approval",
    "steps_hint": (
        "These are review steps inside the approval, where one agency sends the application to another. "
        "They are not separate approvals."
    ),
    "not_given_heading": "Not given",
    "changes_heading": "Change of use: three separate answers",
    "facts_read_heading": "Facts the rules read",
    # the facts the rules read, for the whole report
    "facts_heading": "What the rules read",
    "facts_hint": (
        "Every fact the rules read about the business, and where each came from. What your words do not state is "
        "not known, and the report does not assume it."
    ),
    # the decisions the outcome counts are made of
    "counted_heading": "The decisions counted",
    # in the zoning section
    "rules_date_label": "Rules applied as of",
    "triggers_heading": "Triggers",
    "triggers_hint": "Each reason the Planning Code can require a hearing, read for the rules in force on {date}.",
    "triggers_hint_undated": "Each reason the Planning Code can require a hearing.",
    "in_force_from": "control in force from {date}",
    "in_force_from_ordinance": "control in force from {date}, {ordinance}",
    "differs_today": "This control is not today's control.",  # only when the rules gave no sentence of their own
    # timing
    "timing_heading": "Days from filing, by outcome",
    "timing_hint": (
        "From the comparable cases listed. Each figure is for one outcome; cases with different outcomes are "
        "never combined, and no average is given."
    ),
    "timing_pending_note": "age so far as of {date}, not a time to a decision",
    "timing_undated": "{n} of the comparable cases {have} no figure: a date is missing.",
    "timing_none": "No comparable case has both a filing date and a decision date.",
    "timing_column": "Days from filing",
    "timeline_hint": (
        "The day range is the time to obtain the approvals listed when they are granted, taken from the permit "
        "catalog. It is not a time to a denial or a withdrawal, and it is not drawn from the comparable cases; "
        "their days from filing are listed by outcome under Comparable cases."
    ),
}
# What a trigger's control means, in the words the report prints (`TriggerControl`).
TRIGGER_CONTROL_LABELS: dict[str, str] = {
    "principal": "Asks for nothing",
    "conditional": "Conditional use",
    "not_permitted": "Not permitted",
    "not_decided": "Not decided",
    "does_not_apply": "Does not apply",
    "code_and_practice_differ": "Code and Planning practice differ",
}
# The three change-of-use questions (`ChangeAnswers`), in report order, and their answers.
CHANGE_QUESTION_LABELS: dict[str, str] = {
    "planning_use": "Planning Code change of use",
    "building_occupancy": "Building Code change of occupancy",
    "neighbourhood_notice": "Neighbourhood notification",
}
CHANGE_ANSWER_LABELS: dict[str, str] = {
    "yes": "Yes",
    "no": "No",
    "not_established": "Not established",
    "required": "Required",
    "not_required": "Not required",
}


def status_with_note(status: str, note: str | None) -> str:
    """A status as the report prints it: 'Further review', or with the rules' fixed qualifier after a colon,
    'Further review: Code and Planning practice differ'. The note is printed as the rules gave it."""
    label = status_label(status)
    return f"{label}: {note}" if note else label


def most_severe(statuses: Iterable[str]) -> ApprovalStatus:
    """The report's overall status: the most severe status among its rows (STATUS_SEVERITY order)."""
    present = set(statuses)
    for s in STATUS_SEVERITY:
        if s in present:
            return s
    return "insufficient_information"


# ---- sources: what each one leaves out -----------------------------------------------------------
HEARINGS_SOURCE = "sf_planning_hearings"  # a Commission motion was read for the case
MINUTES_SOURCE = "sf_planning_minutes"  # only the Commission's hearing minutes were read
SOURCE_NOTES: dict[str, SourceNote] = {
    n.source: n
    for n in (
        SourceNote(
            source="datasf_planning",
            label="Planning case list (DataSF)",
            leaves_out=(
                "Outcome and dates only. Conditions are not in this list unless the Commission motion was read; "
                "withdrawn and cancelled cases carry no reason. The decision date is the date Planning closed "
                "the record."
            ),
        ),
        SourceNote(
            source=HEARINGS_SOURCE,
            label="Planning Commission motion",
            leaves_out=(
                "Conditions as adopted at the hearing. Later amendments, enforcement history and whether the "
                "business opened are not included."
            ),
        ),
        SourceNote(
            source=MINUTES_SOURCE,
            label="Planning Commission minutes",
            leaves_out=(
                "The Commission's action as recorded in the hearing minutes; the motion itself was not read, so "
                "conditions are only those named in the minutes. Findings, later amendments, enforcement "
                "history and whether the business opened are not included."
            ),
        ),
        SourceNote(
            source="datasf_entertainment",
            label="Entertainment Commission permit list (DataSF)",
            leaves_out=(
                "Active permits only: no denials, withdrawals, filing dates or conditions, so it cannot show that "
                "an application failed."
            ),
        ),
        SourceNote(
            source="abc",
            label="ABC licence export",
            leaves_out=(
                "Licences that are active or pending today. Denied and withdrawn applications are absent and "
                "there is no filing date, so it cannot show a failure or a processing time."
            ),
        ),
        SourceNote(
            source="user_feedback",
            label=f"Outcome reported by a {settings.APP_NAME} user",
            leaves_out="Self-reported and not verified.",
        ),
    )
}


def comparable_source(app: Application) -> str:
    """Where a comparable's content comes from. A hearing record (a row from the hearings source, or a Planning
    row one enriched: its `extra` then carries `motion_url`, which the store sets for every hearing
    enrichment) is the Commission motion, or the Commission minutes when `extra.source_kind` says the row
    was parsed from minutes and no motion was read. Otherwise the application's own source."""
    if app.source == HEARINGS_SOURCE or app.extra.get("motion_url"):
        return MINUTES_SOURCE if app.extra.get("source_kind") == "minutes" else HEARINGS_SOURCE
    own: str = app.source
    return own


def record_sources(app: Application) -> set[str]:
    """Every source that contributed to a stored record (an enriched Planning row has two)."""
    content = comparable_source(app)
    return {content} if app.source == HEARINGS_SOURCE else {app.source, content}


def source_label(source: str) -> str:
    note = SOURCE_NOTES.get(source)
    return note.label if note else source


def source_notes_for(sources: Iterable[str]) -> list[SourceNote]:
    """One note per source that appears, in a fixed order; sources without a note are skipped."""
    present = set(sources)
    return [note.model_copy() for key, note in SOURCE_NOTES.items() if key in present]


def days_to_decision(filed_at: dt.date | None, decided_at: dt.date | None) -> int | None:
    """Decided minus filed, in days. None unless both dates exist and the decision is not before the filing."""
    if filed_at is None or decided_at is None or decided_at < filed_at:
        return None
    return (decided_at - filed_at).days


# ---- timing: days from filing, always for one outcome ----------------------------------------------
# A number of days read from the records means different things by outcome: the time to an approval, to a
# denial, to the day the applicant withdrew or Planning cancelled the case, or, for a case still open, only its
# age so far. The report never prints one figure across outcomes and never a mean or a median: per case the
# figure names its outcome (`timing_cell`), and per outcome it is the lowest and the highest (`decision_times`).
CANCELLED = "cancelled"


def case_outcome(app: Application) -> str:
    """The outcome a case is shown with. The store has no outcome for a cancelled case: the Planning case
    list's 'Closed - Cancelled' and 'Cancelled' are stored as "withdrawn". A withdrawn case whose own status
    says cancelled is shown as "cancelled", so the two are never counted or timed together; every other case
    keeps the store's outcome."""
    if app.outcome == "withdrawn" and "cancel" in (app.status or "").casefold():
        return CANCELLED
    outcome: str = app.outcome
    return outcome


class TimingGroup(NamedTuple):
    key: str
    label: str  # the group's name in the report
    per_case: str  # one case's figure: '{days} days to approval'
    measured: str  # what a group's figure measures: 'from filing to approval'


TIMING_GROUPS: tuple[TimingGroup, ...] = (
    TimingGroup("approved", "Approved", "{days} days to approval", "from filing to approval"),
    TimingGroup("denied", "Denied", "{days} days to denial", "from filing to denial"),
    TimingGroup("withdrawn", "Withdrawn", "{days} days to withdrawal", "from filing to withdrawal"),
    TimingGroup("cancelled", "Cancelled", "{days} days to cancellation", "from filing to cancellation"),
    TimingGroup(
        "not_recorded",
        "Outcome not recorded",
        "{days} days to closing, outcome not recorded",
        "from filing to the day the record was closed",
    ),
    TimingGroup("pending", "Still pending", "pending {days} days so far", "since filing"),
)
_TIMING_BY_KEY: dict[str, TimingGroup] = {g.key: g for g in TIMING_GROUPS}
_TIMING_GROUP_OF: dict[str, str] = {
    "approved": "approved",
    "approved_with_conditions": "approved",
    "denied": "denied",
    "withdrawn": "withdrawn",
    CANCELLED: "cancelled",
    "pending": "pending",
}
NO_FIGURE = "–"


@dataclass(frozen=True)
class CaseTime:
    """One case's days from filing: which outcome the figure is for, and the figure (None when a date is
    missing). For a pending case the figure is its age on the records date, not a time to a decision."""

    group: str  # a TIMING_GROUPS key
    days: int | None
    citation_id: str | None = None


def case_time(
    outcome: str,
    filed_at: dt.date | None,
    decided_at: dt.date | None,
    as_of: dt.date | None,
    citation_id: str | None = None,
) -> CaseTime:
    """The days from filing for one case. Pending: filing to `as_of` (the records date), whatever decision
    date the row carries. Any other outcome: filing to the decision date (`days_to_decision`). An outcome the
    list does not name is 'not_recorded'."""
    group = _TIMING_GROUP_OF.get(outcome, "not_recorded")
    if group == "pending":
        return CaseTime(group, days_to_decision(filed_at, as_of), citation_id)
    return CaseTime(group, days_to_decision(filed_at, decided_at), citation_id)


def iso_date(text: str | None) -> dt.date | None:
    """'2026-11-09' (or a timestamp that starts with one) as a date; None when it is not one."""
    try:
        return dt.date.fromisoformat(text[:10]) if text else None
    except ValueError:
        return None


def comparable_time(comp: ComparableCase, as_of: dt.date | None) -> CaseTime:
    """`case_time` for a comparable as the report stores it."""
    return case_time(
        comp.outcome, iso_date(comp.filed_at), iso_date(comp.decided_at), as_of, comp.citation_id
    )


def timing_cell(comp: ComparableCase, as_of: dt.date | None) -> str:
    """One comparable's figure with the outcome it is for: '120 days to approval', '77 days to withdrawal',
    'pending 410 days so far'. A dash when a date is missing."""
    time = comparable_time(comp, as_of)
    if time.days is None:
        return NO_FIGURE
    return _TIMING_BY_KEY[time.group].per_case.format(days=f"{time.days:,}")


@dataclass(frozen=True)
class GroupTimes:
    """The figures of one outcome: how many cases have one, the lowest and the highest."""

    group: TimingGroup
    cases: int
    low: int
    high: int
    citation_ids: tuple[str, ...] = ()


def decision_times(times: Iterable[CaseTime]) -> tuple[list[GroupTimes], int]:
    """The cases' figures by outcome, in TIMING_GROUPS order, and how many cases have no figure. A group is
    listed only when a case in it has a figure. Each group gives its lowest and highest figure; nothing is
    averaged and no group is combined with another."""
    by_group: dict[str, list[CaseTime]] = {}
    undated = 0
    for time in times:
        if time.days is None:
            undated += 1
        else:
            by_group.setdefault(time.group, []).append(time)
    out = [
        GroupTimes(
            group=group,
            cases=len(found),
            low=min(t.days for t in found if t.days is not None),
            high=max(t.days for t in found if t.days is not None),
            citation_ids=tuple(t.citation_id for t in found if t.citation_id),
        )
        for group in TIMING_GROUPS
        if (found := by_group.get(group.key))
    ]
    return out, undated


def _days_range(low: int, high: int) -> str:
    return f"{low:,} days" if low == high else f"{low:,} to {high:,} days"


def group_time_line(times: GroupTimes, as_of: dt.date | None) -> str:
    """'Approved: 3 cases, 120 to 140 days from filing to approval.' A pending group also says that its figure
    is an age so far and on which date."""
    noun = "case" if times.cases == 1 else "cases"
    line = f"{times.group.label}: {times.cases} {noun}, {_days_range(times.low, times.high)} {times.group.measured}"
    if times.group.key == "pending" and as_of is not None:
        line += f" ({REPORT_TEXT['timing_pending_note'].format(date=as_of.isoformat())})"
    return line + "."


def decision_time_lines(memo: Memo) -> list[str]:
    """The comparables' days from filing, one line per outcome, then how many cases have no figure. Pending
    cases are aged to the report's records date (`Memo.data_as_of`)."""
    as_of = iso_date(memo.data_as_of)
    groups, undated = decision_times(comparable_time(c, as_of) for c in memo.comparable_cases)
    lines = [group_time_line(g, as_of) for g in groups]
    if not lines and memo.comparable_cases:
        lines.append(REPORT_TEXT["timing_none"])
    elif undated:
        lines.append(REPORT_TEXT["timing_undated"].format(n=undated, have="has" if undated == 1 else "have"))
    return lines


def timing_lines(memo: Memo) -> list[str]:
    """The days-from-filing block of the plain-text report: the heading with what the figures are, then one
    line per outcome. Empty when the report has no comparable case."""
    lines = decision_time_lines(memo)
    if not lines:
        return []
    return [
        f"{REPORT_TEXT['timing_heading'].upper()}: {REPORT_TEXT['timing_hint']}",
        *(f"  {x}" for x in lines),
    ]


# ---- site history: the records on file at the report's own address or parcel ---------------------
SITE_PROXIMITY_M = 12.0  # a record with no parcel and no street number counts as "at the site" inside this
# One more read takes every record of any kind this close to the report's point (see `collect_records`).
# Inside it, a street written without its suffix ('995 Valencia') still matches the report's address.
SITE_READ_RADIUS_M = 30.0
SITE_HISTORY_NOTE = (
    "Records on file at this address or parcel, newest first. Building work is listed here and is not counted "
    "in the outcome counts."
)
SITE_HISTORY_EMPTY_NOTE = (
    "No records at this address or parcel in the data. That does not mean nothing was ever filed here."
)
DESCRIPTION_LIMIT = 300

_STREET_SUFFIXES = {
    "STREET": "ST",
    "AVENUE": "AVE",
    "AV": "AVE",
    "BOULEVARD": "BLVD",
    "DRIVE": "DR",
    "ROAD": "RD",
    "COURT": "CT",
    "PLACE": "PL",
    "LANE": "LN",
    "TERRACE": "TER",
    "HIGHWAY": "HWY",
    "PLAZA": "PLZ",
    "ALLEY": "ALY",
    "CIRCLE": "CIR",
    "SQUARE": "SQ",
    "PARKWAY": "PKWY",
    # the Planning case list's own short forms
    "BL": "BLVD",
    "WY": "WAY",
    "PZ": "PLZ",
    "TR": "TER",
    "HY": "HWY",
    "CR": "CIR",
}
# every suffix as it is written once abbreviated; WAY has no shorter form
_SUFFIX_TOKENS = frozenset({*_STREET_SUFFIXES.values(), "WAY"})
_COMPASS = frozenset({"N", "S", "E", "W"})
_DIRECTIONS = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}
_SPELLED_ORDINALS = {
    "FIRST": "1ST",
    "SECOND": "2ND",
    "THIRD": "3RD",
    "FOURTH": "4TH",
    "FIFTH": "5TH",
    "SIXTH": "6TH",
    "SEVENTH": "7TH",
    "EIGHTH": "8TH",
    "NINTH": "9TH",
    "TENTH": "10TH",
}
_CITY_TAIL = re.compile(r"\bSAN FRANCISCO\b.*$")
_STATE_ZIP_TAIL = re.compile(r"\s+(?:CA\b\s*)?(?:\d{5}(?:-\d{4})?)?\s*$")
# unit text runs to the end: '#2', 'Suite 200', 'Apt B', '2nd Floor'. A unit word must be followed by its
# number or letter, so a name such as '1 Ferry Building' is left alone
_UNIT_TAIL = re.compile(
    r"(?:#"
    r"|\b(?:APT|APARTMENT|UNIT|STE|SUITE|RM|ROOM|FL|FLOOR|SPACE|SPC)\b\.?\s*#?\s*[A-Z0-9]"
    r"|\b\d+(?:ST|ND|RD|TH)\s+(?:FL|FLOOR)\b"
    r").*$"
)
# a street number or a range of them ('993-995', '991 - 999', '997/999'), without a letter or a fraction,
# then the street
# A number, then any further numbers of a range ('993-995', '501-503-505', '997/999'), then a letter on the number
# written straight on or after a dash ('425A', '425-A'; never after a space: '100 A St' is A Street), then a fraction.
_NUMBER_AND_STREET = re.compile(r"^(\d+)((?:\s*[-/]\s*\d+)*)(?:-?[A-Z])?(?:\s+\d/\d)?\s+(.+)$")
_TWO_NUMBERS = re.compile(r"^\s*(\d+)\s*,\s*(\d+)\b")  # '997, 999 Valencia St' names two numbers
_PADDED_ORDINAL = re.compile(r"^0+(\d+(?:ST|ND|RD|TH))$")
_RANGE_SPAN_MAX = 100  # a block has 100 numbers; a wider "range" is read as its first number only
_CITY_SHOWN_TAIL = re.compile(r",?\s*\bSAN FRANCISCO\b.*$", re.IGNORECASE)


@dataclass(frozen=True)
class StreetAddress:
    """A street address as the site history compares it: the number or range of numbers, and the street."""

    low: int  # the street number, or the first number of a range
    high: int  # the last number of a range; equal to `low` for a single number
    name: str  # the street without its suffix, e.g. 'VALENCIA' or 'S VAN NESS'
    suffix: str  # 'ST', 'AVE', or 'AVE E' for a street such as Buena Vista Ave East; '' when none is written

    @property
    def key(self) -> str:
        """'995 VALENCIA ST': the first number and the street."""
        return f"{self.low} {self.name} {self.suffix}".rstrip()

    def covers(self, number: int) -> bool:
        """Is `number` this address, or inside its range on the same side of the street? A range whose two
        ends differ in parity ('100-105') takes every number between them."""
        if not self.low <= number <= self.high:
            return False
        return self.low % 2 != self.high % 2 or number % 2 == self.low % 2


def parse_street_address(text: str | None) -> StreetAddress | None:
    """'993-995 Valencia Street, Suite 2, San Francisco, CA 94110' → 993 to 995, 'VALENCIA', 'ST'.

    Upper-cased, without city, state, ZIP or unit text, with the street suffix abbreviated (STREET → ST,
    AVENUE and AV → AVE, BL → BLVD, WY → WAY, PZ → PLZ, TR → TER), compass words shortened (SOUTH → S) and numbered
    streets written one way (03RD, THIRD → 3RD). Both ends of a number range are kept ('993-995', '991 - 999',
    '997/999', '997, 999', '501-503-505'); a letter ('425A', '425-A') or a fraction on the number is dropped. The street ends at its suffix:
    the Planning case list writes floor and unit text after it ('995 VALENCIA ST STREET LEV', '70 OCEAN AV
    0001'), which is dropped; only a compass word straight after the suffix is kept (Buena Vista Ave East).
    The first word of a street is never read as a suffix (Avenue of the Palms, St Francis Blvd). None when
    the text has no street number followed by a street: such an address cannot tie a record to a site."""
    if not text:
        return None
    s = _TWO_NUMBERS.sub(r"\1-\2", text.upper()).split(",")[0]
    s = _CITY_TAIL.sub("", s)
    s = _UNIT_TAIL.sub("", s)
    s = re.sub(r"[^A-Z0-9/ -]", " ", s)
    s = _STATE_ZIP_TAIL.sub("", " ".join(s.split()))
    m = _NUMBER_AND_STREET.match(s.strip())
    if m is None:
        return None
    tokens = [t for t in m.group(3).replace("-", " ").replace("/", " ").split() if t]
    if not tokens:
        return None
    name: list[str] = []
    suffix = ""
    for i, token in enumerate(tokens):
        padded = _PADDED_ORDINAL.match(token)
        if padded:
            token = padded.group(1)
        token = _SPELLED_ORDINALS.get(token, token)
        token = _DIRECTIONS.get(token, token)
        if i > 0:
            token = _STREET_SUFFIXES.get(token, token)
            if token in _SUFFIX_TOKENS:
                after = _DIRECTIONS.get(tokens[i + 1], tokens[i + 1]) if i + 1 < len(tokens) else ""
                suffix = f"{token} {after}" if after in _COMPASS else token
                break
        name.append(token)
    low = high = int(m.group(1))
    ends = re.findall(r"\d+", m.group(2))
    if ends and low < int(ends[-1]) <= low + _RANGE_SPAN_MAX:
        high = int(ends[-1])
    return StreetAddress(low=low, high=high, name=" ".join(name), suffix=suffix)


def normalize_street_address(text: str | None) -> str | None:
    """'995 Valencia Street, Suite 2, San Francisco, CA 94110' → '995 VALENCIA ST'.

    The first street number and the street as `parse_street_address` reads them; None when it reads none."""
    parsed = parse_street_address(text)
    return parsed.key if parsed else None


def same_street_address(a: StreetAddress, b: StreetAddress, *, allow_missing_suffix: bool = False) -> bool:
    """Do two addresses name the same place? The streets are equal and the numbers meet: one address's number,
    or an end of its range, is the other's number or lies inside the other's range on the same side of the
    street. So '993-995 Valencia St' and '991 - 999 VALENCIA ST' are both 995 Valencia St; 997 is not.
    With `allow_missing_suffix`, a street written without its suffix ('995 Valencia') equals the same name with
    one; callers allow that only for a record right at the report's point, because 3rd St and 3rd Ave both
    exist."""
    if a.name != b.name:
        return False
    if a.suffix != b.suffix and not (allow_missing_suffix and (not a.suffix or not b.suffix)):
        return False
    return a.covers(b.low) or a.covers(b.high) or b.covers(a.low) or b.covers(a.high)


def normalize_parcel(parcel: str | None) -> str | None:
    """Block and lot as one upper-case key, so '3616/065', '3616 / 065' and '3616065' are the same parcel."""
    key = re.sub(r"[^A-Z0-9]", "", (parcel or "").upper())
    return key or None


SiteMatch = Literal["parcel", "address", "proximity"]


@dataclass(frozen=True)
class Site:
    """The report's own address and parcel, as the site history matches against them."""

    address: str | None  # street address for display, e.g. "995 Valencia St"; None when it cannot be matched
    address_key: str | None  # normalize_street_address of the report's address
    parcel: str | None  # as the geocoder gave it, e.g. "3616/065"
    parcel_key: str | None  # normalize_parcel of it
    street: StreetAddress | None = None  # parse_street_address of the report's address


def site_of(address: str, normalized_address: str | None, parcel: str | None) -> Site:
    """The report's site from the geocoder's result. `address` may carry city, state and ZIP."""
    street = parse_street_address(normalized_address) or parse_street_address(address)
    shown = address.split(",")[0].strip() if street else None
    return Site(
        address=shown or None,
        address_key=street.key if street else None,
        parcel=parcel,
        parcel_key=normalize_parcel(parcel),
        street=street,
    )


@dataclass(frozen=True)
class SiteRecord:
    """One record at the report's site, and which rule tied it there."""

    app: Application
    distance_m: float
    matched: SiteMatch


def site_match(app: Application, distance_m: float, site: Site) -> SiteMatch | None:
    """Is this record on file at the report's own site? Three rules, checked in order:

    * parcel: the record's parcel equals the report's parcel (both present);
    * address: the record's street address is the report's (`same_street_address`: the same street, and the
      report's number is the record's number or inside its range). A street written without its suffix
      matches only when the record is mapped within 30 metres of the report's point;
    * proximity: the record has no parcel and no number anywhere in its address, and is mapped within 12
      metres of the report's point.
    A record with its own parcel or address that matches neither is somewhere else, however close. That
    includes an address with a number that cannot be read as number and street ('Valencia St & 21st St')."""
    parcel = normalize_parcel(app.parcel)
    if parcel is not None and parcel == site.parcel_key:
        return "parcel"
    address = parse_street_address(app.address)
    if (
        address is not None
        and site.street is not None
        and same_street_address(address, site.street, allow_missing_suffix=distance_m <= SITE_READ_RADIUS_M)
    ):
        return "address"
    names_a_number = any(ch.isdigit() for ch in app.address or "")
    if parcel is None and not names_a_number and distance_m <= SITE_PROXIMITY_M:
        return "proximity"
    return None


def filed_under(record_address: str | None, site_street: StreetAddress | None) -> str | None:
    """The record's own street address, for display ('993 Valencia St'), when it names one that is not the
    report's. A record tied to the site by its parcel can belong to another unit or storefront on the lot.
    None when the record has no readable street address, or when it is the report's address."""
    own = parse_street_address(record_address)
    if own is None:
        return None
    if site_street is not None and same_street_address(own, site_street, allow_missing_suffix=True):
        return None
    return one_line(_CITY_SHOWN_TAIL.sub("", record_address or "").strip(" ,"), 120)


def _record_date(app: Application) -> dt.date | None:
    date: dt.date | None = app.decided_at or app.filed_at
    return date


def site_records(rows: Iterable[Nearby[Application]], site: Site) -> list[SiteRecord]:
    """Every record at the site, each id once, newest first by decision date or else filing date; undated
    records last. All record kinds are kept: use decisions, referrals, building work, other records, ABC
    licences, Entertainment Commission permits and records without labels."""
    found: dict[str, SiteRecord] = {}
    for n in rows:
        if n.item.id in found:
            continue
        matched = site_match(n.item, n.distance_m, site)
        if matched is not None:
            found[n.item.id] = SiteRecord(n.item, n.distance_m, matched)

    def newest_first(r: SiteRecord) -> tuple[bool, int, str]:
        date = _record_date(r.app)
        return (date is None, -date.toordinal() if date else 0, r.app.id)

    return sorted(found.values(), key=newest_first)


def one_line(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    """Collapse whitespace to single spaces and clip to `limit` characters, ending in an ellipsis when cut."""
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def site_history_entry(rec: SiteRecord) -> SiteHistoryEntry:
    a = rec.app
    source = comparable_source(a)
    kind = record_kind(a)
    return SiteHistoryEntry(
        application_id=a.id,
        citation_id=f"app:{a.id}",
        source=source,
        source_label=source_label(source),
        record_kind=kind,
        record_kind_label=RECORD_KIND_LABELS[kind],
        permit_type=a.permit_type,
        description=one_line(a.description),
        address=a.address,
        filed_at=a.filed_at.isoformat() if a.filed_at else None,
        decided_at=a.decided_at.isoformat() if a.decided_at else None,
        outcome=case_outcome(a),
        status=a.status,
        source_url=a.source_url,
        use_types=list(a.use_types),
        hours_close=a.hours_close,
        conditions=list(a.conditions),
    )


def site_matched_by(site: Site, records: Iterable[SiteRecord] = ()) -> str:
    """In words, how records were tied to the site: 'Parcel 3616/065 or the address 995 Valencia St'."""
    by_point = "a record with no parcel or street number within 12 m of the address point"
    if site.parcel and site.address:
        text = f"Parcel {site.parcel} or the address {site.address}"
    elif site.parcel:
        text = f"Parcel {site.parcel}"
    elif site.address:
        text = f"The address {site.address}"
    else:
        return by_point[0].upper() + by_point[1:]
    if any(r.matched == "proximity" for r in records):
        text += f", or {by_point}"
    return text


def build_site_history(records: list[SiteRecord], site: Site) -> SiteHistory:
    """The report's site history from `site_records` (already newest first): the first SITE_HISTORY_LIMIT are
    listed; `total` and `by_kind` count all of them. No model writes any of this."""
    counts: Counter[str] = Counter(record_kind(r.app) for r in records)
    return SiteHistory(
        matched_by=site_matched_by(site, records),
        total=len(records),
        by_kind={kind: counts[kind] for kind in RECORD_KIND_LABELS if counts[kind]},
        entries=[site_history_entry(r) for r in records[:SITE_HISTORY_LIMIT]],
        note=SITE_HISTORY_NOTE if records else SITE_HISTORY_EMPTY_NOTE,
    )


# ---- the pathway in plain words --------------------------------------------------------------------
EXISTING_USE_NOT_SHOWN = "not shown by the records"


def pathway_facts(pathway: Pathway) -> dict[str, str | None]:
    """The pathway in plain words: the use, the district, the answer for a new use here, the use the records
    show now and the change-of-use answer."""
    return {
        "use": pathway.use_label,
        "zoning_district": pathway.district,
        "new_use_here": pathway.permission_label,
        "existing_use": USE_LABELS[pathway.existing_use] if pathway.existing_use else EXISTING_USE_NOT_SHOWN,
        "change_of_use": pathway.change_of_use_label,
    }


def trigger_control_label(control: str) -> str:
    """'not_decided' → 'Not decided'."""
    return TRIGGER_CONTROL_LABELS.get(control, control)


def trigger_differs_lines(finding: TriggerFinding) -> list[RuleLine]:
    """The sentence the rules wrote where the control on the rules date is not today's control (rule id
    '<trigger>.differs'). Empty when the control is today's."""
    if not finding.differs_today:
        return []
    return [line for line in finding.lines if line.rule_id.endswith(".differs")]


def change_answer_rows(changes: ChangeAnswers | None) -> list[tuple[str, str, list[RuleLine]]]:
    """The three change-of-use answers in report order, each as (question, answer, its rule lines). Empty on
    a report made before rule table v2."""
    if changes is None:
        return []
    return [
        (
            CHANGE_QUESTION_LABELS[key],
            CHANGE_ANSWER_LABELS[getattr(changes, key)],
            list(getattr(changes, f"{key}_lines")),
        )
        for key in CHANGE_QUESTION_LABELS
    ]


def rule_citations(rows: Iterable[RowDetermination]) -> list[str]:
    """The ids the rows' rule lines cite, in order of first appearance, each once."""
    return list(dict.fromkeys(c for row in rows for line in row.basis for c in line.citations))


def determination_citations(determinations: Determinations) -> list[str]:
    """Every id any line the rules wrote cites, in order of first appearance, each once: the pathway's rule
    lines and notes, every trigger's lines, the lines of the three change-of-use answers, and each row's rule
    lines and referral steps. The report prints all of them, so each id must resolve in its citation list."""
    p = determinations.pathway
    lines = [
        *p.lines,
        *p.notes,
        *(line for finding in p.triggers for line in finding.lines),
        *(line for _, _, answer_lines in change_answer_rows(p.changes) for line in answer_lines),
        *(line for row in determinations.rows for line in (*row.basis, *row.referral_steps)),
    ]
    return list(dict.fromkeys(c for line in lines for c in line.citations))


# ---- the rows and the overall line as the rules set them -------------------------------------------
def rules_rows(determinations: Determinations) -> list[MemoApprovalRow]:
    """The report's rows as the rules set them: the area, the approval, the agency, the
    status and its note, the rule lines, the referral steps, the missing inputs and the fixed history note."""
    return [
        MemoApprovalRow(
            area=rule.area,
            area_label=APPROVAL_AREA_LABELS[rule.area],
            approval=rule.approval,
            agency=rule.agency,
            status=rule.status,
            status_note=rule.status_note,
            basis=[line.model_copy() for line in rule.basis],
            referral_steps=[line.model_copy() for line in rule.referral_steps],
            missing_inputs=list(rule.missing_inputs),
            history_note=NO_HISTORY_NOTE if rule.area in NO_HISTORY_AREAS else None,
        )
        for rule in determinations.rows
    ]


def rules_overall(determinations: Determinations) -> MemoOverall:
    """The overall status and line as the rules set them, citing the records the rows' rule lines cite."""
    return MemoOverall(
        status=determinations.overall_status,
        line=determinations.overall_line,
        citations=rule_citations(determinations.rows),
    )


# ---- the report as text ---------------------------------------------------------------------------
def base_rate_line(memo: Memo) -> str:
    """Counts with their N; a rate only when the block shows one; then what was not counted and why."""
    b = memo.base_rate
    line = f"{b.approved + b.approved_with_conditions} approved / {b.denied} denied / {b.withdrawn} withdrawn or cancelled. {b.scope}."
    if b.rate_shown and b.approval_rate_pct is not None:
        line += f" {b.approval_rate_pct:g}% of N approved."
    if b.excluded_not_use_decision and "left out:" in b.scope:
        # the scope already gives the three counts; say in plain words what each one is
        notes = [
            GRANT_LISTS_NOTE if b.excluded_grant_only else "",
            NOT_USE_DECISION_NOTE,
            UNDATED_NOTE if b.excluded_undated else "",
        ]
        return " ".join([line, *(n for n in notes if n)])
    left_out = []
    if b.excluded_grant_only:
        left_out.append(
            f"{b.excluded_grant_only} Entertainment Commission permits and ABC licences (lists of grants only)"
        )
    if b.excluded_not_use_decision:
        left_out.append(
            f"{b.excluded_not_use_decision} Planning records that are not use decisions for this kind of "
            "business (agency referrals, building work, other records, decisions about other kinds of business)"
        )
    if b.excluded_undated:
        left_out.append(f"{b.excluded_undated} decided Planning rows without both dates")
    if left_out:
        line += " Not counted: " + "; ".join(left_out) + "."
    return line


GRANT_LISTS_NOTE = (
    "Entertainment Commission permits and ABC licences are lists of grants only, so they are not counted."
)
NOT_USE_DECISION_NOTE = "Agency referrals, building work, other records and decisions about other kinds of business are not counted."
UNDATED_NOTE = "Decided Planning records without both dates are not counted."


def site_history_count_line(history: SiteHistory) -> str | None:
    """'Showing 20 of 37' when the list is cut short, else None."""
    if history.total > len(history.entries):
        return f"Showing {len(history.entries)} of {history.total}"
    return None


def site_entry_date(entry: SiteHistoryEntry) -> str:
    """The date a site-history row shows: the decision date, else 'filed <date>', else 'undated'."""
    if entry.decided_at:
        return entry.decided_at
    return f"filed {entry.filed_at}" if entry.filed_at else "undated"


def site_entry_outcome(entry: SiteHistoryEntry) -> str:
    """The outcome a site-history row shows; the source's own status when no outcome is known."""
    if entry.outcome != "unknown":
        return entry.outcome.replace("_", " ")
    return entry.status or "not stated"


def site_entry_filed_under(entry: SiteHistoryEntry, report_address: str | None) -> str | None:
    """'Filed under 993 Valencia St' when a site-history row names an address that is not the report's."""
    other = filed_under(entry.address, parse_street_address(report_address))
    return f"Filed under {other}" if other else None


def site_history_lines(history: SiteHistory, report_address: str | None) -> list[str]:
    """The site history as plain-text lines for `report_text`. A record filed under another address than
    `report_address` says so."""
    lines = [f"SITE HISTORY: {history.total} on file. Matched by: {history.matched_by}.", f"  {history.note}"]
    for e in history.entries:
        what = f"{e.permit_type}: {e.description}" if e.description else e.permit_type
        other = site_entry_filed_under(e, report_address)
        if other:
            what += f" ({other})"
        lines.append(
            f"  - {site_entry_date(e)} · {e.record_kind_label} · {what} · {site_entry_outcome(e)} "
            f"[{e.citation_id}]"
        )
    count = site_history_count_line(history)
    if count:
        lines.append(f"  {count}.")
    return lines


def rule_line_text(line: RuleLine) -> str:
    """One rule line with its rule id, and the records it read when it read any:
    '[zoning.use_control] Zoning district NCT-3: a Bar is a conditional use. [zoning:NCT-3]'."""
    cites = f" [{', '.join(line.citations)}]" if line.citations else ""
    return f"[{line.rule_id}] {line.text}{cites}"


def pathway_headline(pathway: Pathway) -> str:
    """'Bar · NCT-3 · Conditional use · Change of use': the use, the district, the answer for a new use here
    and the change-of-use answer."""
    district = pathway.district or "no zoning district on file"
    return " · ".join([pathway.use_label, district, pathway.permission_label, pathway.change_of_use_label])


def rules_date_line(pathway: Pathway) -> str | None:
    """'Rules applied as of 2026-11-10': the date whose rules the report applied. None on a report made
    before rule table v2."""
    return f"{REPORT_TEXT['rules_date_label']} {pathway.rules_date}" if pathway.rules_date else None


def triggers_hint(pathway: Pathway) -> str:
    """The line under the triggers heading, naming the rules date when the report carries one."""
    if pathway.rules_date:
        return REPORT_TEXT["triggers_hint"].format(date=pathway.rules_date)
    return REPORT_TEXT["triggers_hint_undated"]


def trigger_headline(finding: TriggerFinding) -> str:
    """One trigger with its control: 'T7 Use size: Not decided (control in force from 2025-10-06, Ord.
    173-25). Not given: the floor area'. The version of the control and the missing inputs are printed only
    when the rules gave them."""
    text = f"{finding.rule_id} {finding.label}: {trigger_control_label(finding.control)}"
    if finding.in_force_from:
        key = "in_force_from_ordinance" if finding.ordinance else "in_force_from"
        text += f" ({REPORT_TEXT[key].format(date=finding.in_force_from, ordinance=finding.ordinance)})"
    if finding.missing_inputs:
        text += f". {not_given_text(finding.missing_inputs)}"
    return text


def trigger_differs_texts(finding: TriggerFinding) -> list[str]:
    """The sentence printed under a trigger whose control on the rules date is not today's: the rules' own
    '.differs' line, or the fixed fallback when the rules wrote none. Empty when the control is today's."""
    if not finding.differs_today:
        return []
    return [line.text for line in trigger_differs_lines(finding)] or [REPORT_TEXT["differs_today"]]


def not_given_text(missing_inputs: Iterable[str]) -> str:
    """'Not given: the floor area; the closing time'. The phrases are the rules' own, unchanged."""
    return f"{REPORT_TEXT['not_given_heading']}: {'; '.join(missing_inputs)}"


def trigger_lines(pathway: Pathway) -> list[str]:
    """The triggers as plain-text lines: the heading, then every trigger with its control and, where the
    control differs today from the rules date, that sentence under it. Empty on a report with no triggers."""
    if not pathway.triggers:
        return []
    lines = [f"{REPORT_TEXT['triggers_heading'].upper()}: {triggers_hint(pathway)}"]
    for finding in pathway.triggers:
        lines.append(f"  {trigger_headline(finding)}")
        lines += [f"    {text}" for text in trigger_differs_texts(finding)]
    return lines


def pathway_lines(pathway: Pathway) -> list[str]:
    """The pathway as plain-text lines: the headline, the rules date, each rule applied with its rule id, the
    notes, then the triggers with their controls."""
    lines = [f"PATHWAY (set by rule): {pathway_headline(pathway)}"]
    dated = rules_date_line(pathway)
    if dated:
        lines.append(f"  {dated}")
    lines += [f"  {rule_line_text(line)}" for line in pathway.lines]
    lines += [f"  {rule_line_text(line)}" for line in pathway.notes]
    return [*lines, *trigger_lines(pathway)]


def unprinted_lines(lines: Iterable[RuleLine], printed: Iterable[RuleLine]) -> list[RuleLine]:
    """The lines of `lines` that `printed` does not already hold (same rule id and text), in order. The
    building row's rule lines already carry most lines of the three change-of-use answers; only the others are
    printed again under the answers."""
    seen = {(line.rule_id, line.text) for line in printed}
    return [line for line in lines if (line.rule_id, line.text) not in seen]


def row_headline(row: MemoApprovalRow) -> str:
    """'Alcohol licence: Further review: public convenience or necessity finding likely required'."""
    return f"{row.area_label}: {status_with_note(row.status, row.status_note)}"


def row_rule_lines(row: MemoApprovalRow, pathway: Pathway) -> list[str]:
    """Everything the rules set under one row, as plain-text lines: the rules applied; the steps inside the
    approval, said to be review steps and not approvals; the inputs not given; and, under the building row,
    the three change-of-use answers each on its own line."""
    lines = [f"    rule {rule_line_text(line)}" for line in row.basis]
    if row.referral_steps:
        lines.append(f"    {REPORT_TEXT['steps_heading']}. {REPORT_TEXT['steps_hint']}")
        lines += [f"      step {rule_line_text(line)}" for line in row.referral_steps]
    if row.missing_inputs:
        lines.append(f"    {not_given_text(row.missing_inputs)}")
    if row.area == "building_change_of_use":
        answers = change_answer_rows(pathway.changes)
        if answers:
            lines.append(f"    {REPORT_TEXT['changes_heading']}")
        for question, answer, answer_lines in answers:
            lines.append(f"      {question}: {answer}")
            lines += [
                f"        rule {rule_line_text(line)}" for line in unprinted_lines(answer_lines, row.basis)
            ]
    return lines


def status_summary_lines(memo: Memo) -> list[str]:
    """Every row's status with its note and its missing inputs, one row per line, under the rules date: the
    lines a local run prints to compare runs."""
    lines = ["ROWS"]
    dated = rules_date_line(memo.pathway)
    if dated:
        lines.append(f"  {dated}")
    for row in memo.approvals:
        line = f"  {row_headline(row)}"
        if row.missing_inputs:
            line += f". {not_given_text(row.missing_inputs)}"
        lines.append(line)
    return lines


def statuses_line(memo: Memo) -> str:
    """Every row's status with the rule ids that set it, on one line, for comparing runs side by side:
    'STATUSES: zoning_use=further_review [zoning.use, ..., zoning.status]; alcohol=...'."""
    rows = [
        f"{row.area}={row.status} [{', '.join(dict.fromkeys(line.rule_id for line in row.basis))}]"
        for row in memo.approvals
    ]
    return "STATUSES: " + "; ".join(rows)


# ---- evidence in plain words (the facts the rules read, the comparables, the counted decisions) ---------------
NOT_KNOWN_VALUE = "Not known"


def fact_value_text(fact: MemoFact) -> str:
    """The fact's value, or "Not known"."""
    return fact.value if fact.value is not None else NOT_KNOWN_VALUE


def fact_origin_text(fact: MemoFact) -> str:
    """Where a fact came from, with the applicant's words when they state it:
    'Your description: "open until 2 a.m."'. A record fact names no record here: its citations do."""
    if fact.quotes:
        return f"{fact.origin_label}: " + "; ".join(f"“{q}”" for q in fact.quotes)
    return fact.origin_label


def fact_line(fact: MemoFact) -> str:
    """'Closing time: 2:00 a.m. (Your description: "until 2am")'."""
    return f"{fact.label}: {fact_value_text(fact)} ({fact_origin_text(fact)})"


def comparable_facts_line(comp: ComparableCase) -> str:
    """What the record of one comparable says, in one line: kind, use, dates, outcome, hours, conditions."""
    parts = [comp.permit_type]
    if comp.use_types:
        parts.append("use: " + ", ".join(u.replace("_", " ") for u in comp.use_types))
    parts.append(f"filed {comp.filed_at or 'not recorded'}")
    parts.append(f"decided {comp.decided_at}" if comp.decided_at else "not decided")
    parts.append(comp.outcome.replace("_", " "))
    if comp.hours_close:
        parts.append(f"closes {comp.hours_close}")
    if comp.conditions:
        parts.append(
            f"{len(comp.conditions)} {'condition' if len(comp.conditions) == 1 else 'conditions'} on file"
        )
    return " · ".join(parts)


def counted_decision_line(d: CountedDecision) -> str:
    return (
        f"{d.decided_at or 'undated'} · {d.permit_type} · {d.address or 'address not recorded'} · "
        f"{d.outcome.replace('_', ' ')} · {d.source_url or d.application_id}"
    )


def headline_lines(memo: Memo) -> list[str]:
    """The headline findings as plain-text lines, first in the report: one line per finding with its status and
    whether it depends on an answer not given, then the trigger line it rests on. None when there is none."""
    if not memo.headline_findings:
        return []
    lines = [f"{REPORT_TEXT['headline_heading'].upper()} (set by rule)", f"  {REPORT_TEXT['headline_hint']}"]
    for h in memo.headline_findings:
        how = REPORT_TEXT["headline_definite" if h.definite else "headline_contingent"]
        lines.append(f"  - {status_label(h.status)} ({how}): {h.sentence}")
        lines += [f"      rule {rule_line_text(line)}" for line in h.basis]
    return lines


def report_text(memo: Memo) -> str:
    """The report as plain text: the headline findings first, overall, the pathway with its rules date and
    triggers, rows with their status
    and status note, rule lines, referral steps, missing inputs and the facts each row's rules read, every fact
    with where it came from, could-not-establish with the fixed line on what public records cannot show, the site
    history, the comparables with their recorded facts and days from filing by outcome, the counted decisions."""
    lines = [
        "",
        f"{memo.address} — {memo.description}",
        *headline_lines(memo),
        f"OVERALL: {status_label(memo.overall.status)} — {memo.overall.line}",
        "",
        *pathway_lines(memo.pathway),
        "",
        "APPROVALS (status, approval and agency set by rule)",
    ]
    for row in memo.approvals:
        lines.append(f"  {row_headline(row)} — {row.approval} · {row.agency}")
        lines += row_rule_lines(row, memo.pathway)
        if row.facts:
            lines.append(f"    {REPORT_TEXT['facts_read_heading']}:")
            lines += [
                f"      fact {fact_line(f)}" + (f" {f.citations}" if f.citations else "") for f in row.facts
            ]
        if row.history_note:
            lines.append(f"    {row.history_note}")
    if memo.facts:
        lines += ["", f"{REPORT_TEXT['facts_heading'].upper()}"]
        lines += [f"  - {fact_line(f)}" for f in memo.facts]
    lines += ["", "COULD NOT ESTABLISH"]
    lines += [
        f"  - ({q.needs}) {q.question}" + (f" — {q.ask}" if q.ask else "") for q in memo.could_not_establish
    ]
    lines.append(f"  {memo.records_limits}")
    lines += ["", *site_history_lines(memo.site_history, memo.address)]
    lines += ["", f"COMPARABLE CASES: {len(memo.comparable_cases)}"]
    if memo.comparables_note:
        lines.append(f"  {memo.comparables_note}")
    for comp in memo.comparable_cases:
        lines.append(
            f"  - {comp.address or 'address not recorded'} · {comparable_facts_line(comp)} [{comp.citation_id}]"
        )
    lines += [
        "",
        f"DATED DECISIONS: {base_rate_line(memo)}",
        *[f"  - {counted_decision_line(d)}" for d in memo.base_rate.counted],
        *timing_lines(memo),
        f"ENTITLEMENT PATH (set by rule): {memo.entitlement_path}",
        statuses_line(memo),
        "",
    ]
    return "\n".join(lines)
