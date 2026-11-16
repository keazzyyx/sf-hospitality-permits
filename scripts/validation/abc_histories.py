"""Step 1b: rebuild ABC application histories from the archived daily reports (local files only).

Reads the parsed CSVs in the private data repo (``~/abc-archive-data/daily/<date>/*.csv``), never the ABC site.
Reads the local validation database for Planning's ABC referrals and the citywide export; writes nothing to it.

    apps/api/.venv/bin/python scripts/validation/abc_histories.py [--out docs/validation] [--since 2019-01-01]
    apps/api/.venv/bin/python scripts/validation/abc_histories.py --self-test

Outputs
  <out>/abc-histories.json                    every number in the write-up
  <out>/abc-sf-histories.csv                  one row per San Francisco file number (company and DBA names only)
  <out>/abc-sf-withdrawn-since-2024-11.csv    San Francisco applications withdrawn since November 2024
  <out>/abc-referral-file-match-sample.csv    20 random referral-to-file matches for the hand check, one per file
  $LOCAL_DATA_DIR/abc-histories.csv.gz    one row per file number, statewide, no names (kept out of the repo)

How the three reports are read (the evidence for each line is recomputed on every run, key ``reading``)
  Status Changes   one row per licence-type record on a file. A record is listed on EVERY date on which its
                   status changed, and each listing shows the record's MOST RECENT transition as of the day the
                   page was fetched, not the change made on that date.
                   * A record that was never issued (no Original Issue Date) and reads PEND to WITHDRAWN has,
                     in the simple case, two dates: the first is the day the application entered PEND (the
                     filing), the last is the withdrawal. The same holds for PEND to DENIED.
                   * A record that was issued shows no date before its Original Issue Date. Its first date IS
                     the Original Issue Date, which is also the date of its row in Issued Licenses. Its second
                     date is the next business day and is not an event in any other report. The filing date of
                     an issued application is therefore not in this report.
  Issued Licenses  every row is an issue on the report's date, and that date is the Original Issue Date. The
                   status column is the licence's status today (Active, Canceled, Auto Revoked ...). Type 30
                   rows are temporary permits, not licences.
  New Applications for a past date, only the applications that are still pending today.

Definitions
  file             an ABC file (licence) number. Counts are files, never report rows.
  issued           the file has a permanent (not type 30) row in Issued Licenses; date = the first such report
                   date (the Original Issue Date). A file missing from that report whose Original Issue Date
                   falls in the archive period counts as issued on that date, and the basis says so.
  withdrawn        never issued in the archive; a record reads PEND/NEW to WITHDRAWN/WTHDRN; date = that
                   record's last status date. denied: PEND to DENIED, same rule.
  pending          never issued; listed in New Applications today, or pending in the citywide export, or the
                   record reads WTHDRN to PENDING. The export counts only while Status Changes shows no
                   withdrawal or denial dated on or after the export's own date: the export is fetched a day
                   before the Status Changes page of the same date, so on that day it is the older record.
  original         action ORI. transfer: PER (person to person) and/or PRM (premises to premises). other:
                   fiduciary, exchange, duplicate, stock and similar. The action comes from Issued Licenses or
                   New Applications; where a file has neither it is inferred from Transfer-From/To (present =
                   transfer) and marked "(inferred)". This is the application class shown in the tables.
  investigation grouping (used only in the check against ABC's two tables of application investigations)
                   original investigation = action ORI, PRM (alone or with PER) or ICO; transfer investigation
                   = PER, FID, DPR, STK and every other action. ABC counts a premises transfer as an original
                   investigation; see ``limits`` in the JSON for where that comes from.
  priority drawing entry
                   a never-issued file (withdrawn, denied or pending; no licence record on the file) of general
                   type 47, 48 or 21 that is an original: reported action ORI or, where no action is reported,
                   no Transfer-From/To on its records. A new general licence can only be applied for through
                   the priority drawing, so the filing date plays no part in the rule. The application-window
                   days (30 or more such files filed in one day) are reported as evidence only. Kept as its
                   own class everywhere.
  partial years    the archive's first and last fiscal years are part-years and are labelled with the dates
                   they cover; every by-year table that ends in the archive's last year carries the same note.
  business name    the DBA, or the company name where there is no DBA, and only where the licensee is a
                   company. Where the licensee is an individual nothing is published: a sole proprietor's trade
                   name is often the person's own name or built on it.
  filing date      "status report first date": first date of the file's never-issued record (two or more dates),
                   on a file with no licence record and a file number handed out inside the archive. A lower
                   file number was handed out before the archive began: the first date the archive shows for
                   it need not be the filing, so it has none.
                   "new applications listing": the listing date of a still-pending application.
                   "estimated from file number": file numbers are handed out in filing order, so a file with no
                   reported filing date takes the median filing date of the nearest numbers that have one. Used
                   only when the leave-one-out error of that rule is small (see number_order), and always
                   labelled estimated.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import gzip
import json
import os
import random
import re
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import abc_workload
from abc_referral_match import ABC_RX, keys, named_types, norm_name, referral_dba

DATA = Path(os.environ.get("ABC_DATA", "~/abc-archive-data")).expanduser()
LOCAL_DIR = Path(os.environ.get("LOCAL_DATA_DIR", "~/sfhp-local")).expanduser()
LOCAL = os.environ.get(
    "LOCAL_DATABASE_URL", "postgresql://postgres@localhost:55433/sfhp_local"
)
SF_COUNTY, SF_DISTRICT = "38", "24"
SAN_MATEO_COUNTY, SAN_JOSE_DISTRICT = "41", "25"
ISSUED, WITHDRAWN, DENIED, PENDING, CANCELLED = (
    "issued",
    "withdrawn",
    "denied",
    "pending",
    "cancelled while pending",
)
NO_APPLICATION = "no application in the archive (licence issued earlier)"
TEMP_ONLY = "temporary permit only"
UNCLEAR = "unclear"
APPLICATION_OUTCOMES = (
    ISSUED,
    WITHDRAWN,
    DENIED,
    CANCELLED,
    PENDING,
    TEMP_ONLY,
    UNCLEAR,
)
PENDING_STATES = {"PEND", "NEW", "PENDING"}
WITHDRAWN_STATES = {"WITHDRAWN", "WTHDRN"}
REPENDED = {
    ("WTHDRN", "PENDING"),
    ("WTHDRN", "PEND"),
    ("WITHDRAWN", "PENDING"),
    ("WITHDRAWN", "PEND"),
}
GENERAL_TYPES = {"47", "48", "21"}
TEMP_TYPE = "30"
# Evidence only, not part of the rule: an application-window day is one on which this many never-issued
# general-type originals were filed.
WINDOW_DAY_MIN = 30
WINDOW_NEAR_DAYS = 7
# ABC's two tables of application investigations (220's): actions counted in the "original" table.
ORIGINAL_INVESTIGATION_ACTIONS = {"ORI", "PRM", "ICO"}
ORIGINAL_INVESTIGATION = "original investigation"
TRANSFER_INVESTIGATION = "transfer investigation"
BASIS_STATUS = "status report first date"
BASIS_STATUS_ISSUED = (
    "status report first date (withdrawn licence type on the issued file)"
)
BASIS_LISTING = "new applications listing"
BASIS_ESTIMATE = "estimated from file number"
BASIS_NONE = "unknown"
KNOWN_BASES = (BASIS_STATUS, BASIS_STATUS_ISSUED, BASIS_LISTING)
# The file-number estimate is used only if the leave-one-out test on reported filing dates is this good.
EST_MAX_MEDIAN_ERROR_DAYS, EST_MAX_P90_ERROR_DAYS = 2.0, 7.0
EST_NEIGHBOURS, EST_NUMBER_SPAN, EST_MAX_SPREAD_DAYS = 5, 300, 30
OUT_OF_ORDER_DAYS, MAX_INVERSIONS = 3, 5
MAIN_TYPES = [
    "47",
    "48",
    "41",
    "42",
    "40",
    "75",
    "23",
    "21",
    "20",
    "90",
    "64",
    "57",
    "51",
    "52",
]
RIDER_TYPES = {"58", "68", "77", "66", "67", "69", "14", "18", "9", "10"}
TABLE_TYPES = ["41", "47", "48", "42", "20", "21", "40", "75", "58"]
COMPANY_RE = re.compile(
    r"\b(LLC|L\.L\.C|INC|INCORPORATED|CORP|CORPORATION|LP|LLP|LTD|CO|COMPANY|COMPANIES|GROUP|PARTNERS|"
    r"PARTNERSHIP|HOLDINGS|ENTERPRISES?|ASSOCIATION|ASSN|CLUB|FOUNDATION|TRUST|SOCIETY|CHURCH|POST|LODGE|"
    r"UNIVERSITY|COLLEGE|DISTRICT|CITY OF|COUNTY OF|HOTEL|RESTAURANT|CAFE|WINERY|BREWERY|BREWING|CELLARS|"
    r"VINEYARDS?|MARKET|IMPORTS|DISTRIBUT\w+|HOSPITALITY|VENTURES|BRANDS|WINES?|SPIRITS|FOODS?|STORES?)\b"
)
# An individual licensee is written "SURNAME, GIVEN NAMES" (the citywide export writes two spaces for the comma).
# A string of that shape is a person unless it carries one of the entity suffixes below, whatever other words
# it contains: CO, POST, WINE, CHURCH and FOOD are surnames too.
PERSON_RE = re.compile(r"^[A-Z'\-. ]+?(?:,|\s{2,})\s*[A-Z]")
HARD_ENTITY_RE = re.compile(
    r"\b(LLC|L\.L\.C|INC|INCORPORATED|CORP|CORPORATION|LP|L\.P|LLP|L\.L\.P|LTD|LIMITED|L-PSHIP|PARTNERSHIP|"
    r"TRUST|ASSOCIATION|ASSN|FOUNDATION)\b"
)
NAME_WITHHELD = (
    "(individual licensee, name withheld)"  # internal marker; a CSV shows a blank name
)


def shown_name(name: str) -> str:
    """The name as a CSV shows it: blank where it is withheld (the row carries name_withheld = yes)."""
    return "" if name == NAME_WITHHELD else name


def withheld_flag(name: str) -> str:
    return "yes" if name == NAME_WITHHELD else "no"


CARE_OF_RE = re.compile(r"[,;]?\s*\bC/O\b.*$", re.IGNORECASE)


# ---------------------------------------------------------------------------- model


@dataclass
class Rec:
    """One licence-type record on a file, as Status Changes lists it: its latest transition and every date on
    which its status changed. Rows are grouped by type, duplicate number, transition and Original Issue Date."""

    type: str
    dup: str
    frm: str
    to: str
    orig_issue: dt.date | None
    dates: set[dt.date] = field(default_factory=set)
    transfer: str = ""

    @property
    def kind(self) -> str:
        if self.orig_issue or (self.frm in PENDING_STATES and self.to == "ACTIVE"):
            return "licence"
        if self.frm in PENDING_STATES and self.to in WITHDRAWN_STATES:
            return WITHDRAWN
        if self.frm in PENDING_STATES and self.to == "DENIED":
            return DENIED
        if self.frm in PENDING_STATES and self.to in ("CANCEL", "NREN"):
            return CANCELLED
        if (self.frm, self.to) in REPENDED:
            return "repended"
        return "other"

    @property
    def first(self) -> dt.date:
        return min(self.dates)

    @property
    def last(self) -> dt.date:
        return max(self.dates)

    def label(self) -> str:
        return f"{self.frm} to {self.to}"


@dataclass(frozen=True)
class IssueRow:
    type: str
    dup: str
    action: str
    status: str  # the licence's status today, not when issued


@dataclass
class File:
    number: str
    recs: dict[tuple, Rec] = field(default_factory=dict)
    issues: dict[dt.date, set[IssueRow]] = field(
        default_factory=lambda: defaultdict(set)
    )
    listed: dict[dt.date, set[tuple[str, str]]] = field(
        default_factory=lambda: defaultdict(set)
    )
    export_pending_types: set[str] = field(default_factory=set)
    export_date: dt.date | None = None
    street: str = ""
    city: str = ""
    county: str = ""
    zip: str = ""
    district: str = ""
    dba: str = ""
    owner: str = ""
    # derived by classify()
    outcome: str = UNCLEAR
    outcome_date: dt.date | None = None
    outcome_basis: str = ""
    app_types: set[str] = field(default_factory=set)
    action: str = ""
    cls: str = "original"
    cls_inferred: bool = True
    priority: bool = False
    priority_reason: str = ""
    filed: dt.date | None = None
    filed_basis: str = BASIS_NONE
    filed_note: str = ""
    pattern: str = ""
    notes: list[str] = field(default_factory=list)

    # -- raw views
    def perm_issue_dates(self) -> list[dt.date]:
        return sorted(
            d
            for d, rows in self.issues.items()
            if any(r.type != TEMP_TYPE for r in rows)
        )

    def temp_permit_dates(self) -> list[dt.date]:
        return sorted(
            d
            for d, rows in self.issues.items()
            if any(r.type == TEMP_TYPE for r in rows)
        )

    def status_dates(self) -> list[dt.date]:
        return (
            sorted(set().union(*(r.dates for r in self.recs.values())))
            if self.recs
            else []
        )

    def recs_of(self, *kinds: str) -> list[Rec]:
        return [r for r in self.recs.values() if r.kind in kinds]

    def transitions(self) -> set[tuple[str, str]]:
        return {(r.frm, r.to) for r in self.recs.values()}

    def types(self) -> set[str]:
        ts = {r.type for r in self.recs.values()}
        ts |= {r.type for rows in self.issues.values() for r in rows}
        ts |= {t for rows in self.listed.values() for _, t in rows}
        return (ts | self.export_pending_types) - {""}

    def listing_date(self) -> dt.date | None:
        return min(self.listed) if self.listed else None

    def export_superseded(self) -> bool:
        """The citywide export shows the file pending, and Status Changes shows a withdrawal or denial dated on
        or after the export's date. The export of a date is fetched before the Status Changes page of that
        date, so the status record is the later of the two."""
        return (
            bool(self.export_pending_types)
            and self.export_date is not None
            and any(r.last >= self.export_date for r in self.recs_of(WITHDRAWN, DENIED))
        )

    def export_pending(self) -> bool:
        return bool(self.export_pending_types) and not self.export_superseded()

    def is_pending_now(self) -> bool:
        return (
            bool(self.listed) or self.export_pending() or bool(self.recs_of("repended"))
        )

    def general_original(self) -> bool:
        """General licence type (21, 47, 48) and an original: the kind of application the priority drawing is for."""
        return bool(self.app_types & GENERAL_TYPES) and self.cls == "original"

    def issued_in_archive(self) -> bool:
        return self.outcome == ISSUED

    def primary_type(self) -> str:
        ts = self.app_types or self.types()
        for t in MAIN_TYPES:
            if t in ts:
                return t
        rest = sorted(ts - RIDER_TYPES - {TEMP_TYPE}, key=type_key) or sorted(
            ts, key=type_key
        )
        return rest[0] if rest else "?"

    def table_type(self) -> str:
        t = self.primary_type()
        return t if t in TABLE_TYPES else "other"

    def app_class(self) -> str:
        """original / transfer / other, with priority-drawing entries as their own class."""
        return "priority drawing entry" if self.priority else self.cls

    def class_label(self) -> str:
        return self.app_class() + (" (inferred)" if self.cls_inferred else "")

    def has_application(self) -> bool:
        return self.outcome in APPLICATION_OUTCOMES

    def licensee_is_individual(self) -> bool:
        """The owner string has the shape "SURNAME, GIVEN" and no entity suffix (LLC, INC, CORP, LP, TRUST ...).
        Shape decides, not vocabulary: "CO, THANH VAN" and "POST, EMILY JANE" are people."""
        return bool(PERSON_RE.match(self.owner)) and not HARD_ENTITY_RE.search(
            self.owner
        )

    def business_name(self) -> str:
        """DBA or company name of a company licensee. Never an individual's name.

        Where the licensee is an individual, or the licensee is not known, nothing is published, DBA included:
        a sole proprietor's trade name is often the person's own name or built on it ("<GIVEN> <SURNAME>
        WINES", "<SURNAME> COMPANY"), and no word list can tell those from an ordinary trade name."""
        if not self.owner or self.licensee_is_individual():
            return NAME_WITHHELD
        if self.dba:
            return self.dba
        if HARD_ENTITY_RE.search(self.owner) or COMPANY_RE.search(self.owner):
            return self.owner
        return NAME_WITHHELD

    def premises(self) -> str:
        """Premises street as ABC gives it, without a care-of line (a mailing construct, not a location)."""
        return CARE_OF_RE.sub("", self.street).strip()

    def events(self) -> list[tuple[dt.date, str]]:
        """Every dated event on the file, in date order, for the histories CSV."""
        ev: list[tuple[dt.date, str]] = []
        if self.filed:
            ev.append((self.filed, f"filed ({self.filed_basis})"))
        for d in sorted(self.listed):
            acts = "/".join(sorted({a for a, _ in self.listed[d]})) or "no action"
            ev.append((d, f"listed in New Applications, still pending ({acts})"))
        for d in sorted(self.issues):
            rows = self.issues[d]
            perm = sorted({r.type for r in rows if r.type != TEMP_TYPE}, key=type_key)
            if perm:
                acts = (
                    " + ".join(sorted({r.action for r in rows if r.type != TEMP_TYPE}))
                    or "no action"
                )
                now = "/".join(sorted({r.status for r in rows if r.type != TEMP_TYPE}))
                ev.append(
                    (d, f"issued, type {' '.join(perm)} ({acts}; status today {now})")
                )
            if any(r.type == TEMP_TYPE for r in rows):
                ev.append((d, "temporary permit issued"))
        for r in self.recs.values():
            if r.kind in (WITHDRAWN, DENIED, CANCELLED):
                ev.append(
                    (r.last, f"{r.kind}, type {r.type} ({r.label()}; last status date)")
                )
            elif (r.frm, r.to) != ("PEND", "ACTIVE"):
                ev.append(
                    (
                        r.last,
                        f"type {r.type} {r.label()} (latest transition; last status date)",
                    )
                )
        return sorted(set(ev))


def type_key(t: str) -> tuple[int, str]:
    return (int(t), "") if t.isdigit() else (10**6, t)


def split_type(cell: str) -> tuple[str, str]:
    typ, _, dup = cell.partition("|")
    return typ.strip().lstrip("0") or "0", dup.strip()


def parse_name(cell: str) -> tuple[str, str]:
    parts = [p.strip() for p in cell.split(" | ")]
    if parts and parts[0].upper().startswith("DBA:"):
        return parts[0][4:].strip(), parts[1] if len(parts) > 1 else ""
    return "", parts[0] if parts else ""


def parse_us_date(s: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(s.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def action_class(action: str) -> str:
    parts = set(re.split(r"[/+ ]+", action)) - {""}
    if "ORI" in parts:
        return "original"
    if parts & {"PER", "PRM"}:
        return "transfer"
    return "other"


def investigation_class(action: str) -> str:
    """Which of ABC's two tables of application investigations an issued application falls in.

    Not the application class above. ABC's "original" table holds originals and premises transfers (PRM,
    alone or with PER) and, as far as can be told, ICO; its "transfer" table holds person-to-person transfers,
    fiduciary, drop-partner and stock changes and everything else. See ``limits`` for the evidence."""
    parts = set(re.split(r"[/+ ]+", action)) - {""}
    return (
        ORIGINAL_INVESTIGATION
        if parts & ORIGINAL_INVESTIGATION_ACTIONS
        else TRANSFER_INVESTIGATION
    )


# ---------------------------------------------------------------------------- load


def load(data: Path, since: dt.date) -> tuple[dict[str, File], dict]:
    """Read every daily report. A row repeated on one date (same file, type, transition) counts once."""
    files: dict[str, File] = {}
    raw_rows, days, repeats = Counter(), Counter(), Counter()
    all_days: set[dt.date] = set()
    for d in sorted((data / "daily").iterdir()):
        try:
            date = dt.date.fromisoformat(d.name)
        except ValueError:
            continue
        if date < since:
            continue
        for report in ("new-applications", "status-changes", "issued-licenses"):
            f = d / f"{report}.csv"
            if not f.exists():
                continue
            days[report] += 1
            with open(f, newline="") as fh:
                for r in csv.DictReader(fh):
                    raw_rows[report] += 1
                    num = r["License Number"].strip().lstrip("0")
                    if not num:
                        continue
                    all_days.add(date)
                    fl = files.get(num)
                    if fl is None:
                        fl = files[num] = File(num)
                    dba, owner = parse_name(
                        r.get("Primary Owner and Premises Addr.", "")
                    )
                    fl.street = r.get("Prem Street", "").strip() or fl.street
                    fl.city = r.get("City", "").strip() or fl.city
                    fl.county = r.get("County", "").strip() or fl.county
                    fl.zip = r.get("Zip Code", "").strip() or fl.zip
                    fl.district = r.get("District Code", "").strip() or fl.district
                    fl.dba, fl.owner = dba or fl.dba, owner or fl.owner
                    typ, dup = split_type(r["Type| Dup"])
                    if report == "status-changes":
                        frm, _, to = (
                            p.strip()
                            for p in r["Status Changed From/To"].partition("|")
                        )
                        orig = parse_us_date(r.get("Original Issue Date", ""))
                        key = (typ, dup, frm, to, orig)
                        rec = fl.recs.get(key)
                        if rec is None:
                            rec = fl.recs[key] = Rec(typ, dup, frm, to, orig)
                        if date in rec.dates:
                            repeats[report] += 1
                        rec.dates.add(date)
                        rec.transfer = (
                            r.get("Transfer-From/To", "").strip() or rec.transfer
                        )
                    elif report == "issued-licenses":
                        row = IssueRow(
                            typ, dup, r["Action"].strip(), r["Status"].strip()
                        )
                        if row in fl.issues[date]:
                            repeats[report] += 1
                        fl.issues[date].add(row)
                    else:
                        row2 = (r["Action"].strip(), typ)
                        if row2 in fl.listed[date]:
                            repeats[report] += 1
                        fl.listed[date].add(row2)
    meta = {
        "report_days": dict(days),
        "rows": dict(raw_rows),
        "rows_repeated_on_one_date": dict(repeats),
        "files": len(files),
        "first_day": min(all_days).isoformat() if all_days else None,
        "last_day": max(all_days).isoformat() if all_days else None,
        "days_with_rows": len(all_days),
    }
    return files, meta


def fetch_export_pending() -> list[tuple]:
    """Applications pending in the citywide Daily Data Export (San Francisco only, local table), with the
    export's own date."""
    import psycopg

    with psycopg.connect(LOCAL) as conn:
        conn.read_only = True
        return conn.execute(
            """select ltrim(file_number,'0'), ltrim(license_type,'0'), prem_addr_1, prem_city,
                      left(prem_zip, 5), dba_name, primary_name, district, export_date
               from abc_export_sf where type_status='PEND' and lic_or_app='APP'"""
        ).fetchall()


def add_export_pending(files: dict[str, File], rows: list[tuple]) -> dict:
    """Mark the files the citywide export shows as pending applications, and keep the export's date: a
    withdrawal or denial dated on or after it in Status Changes is the later record (File.export_superseded)."""
    added = 0
    seen: set[str] = set()
    dates: set[dt.date] = set()
    for num, typ, addr, city, zipc, dba, owner, district, export_date in rows:
        if not num:
            continue
        seen.add(num)
        fl = files.get(num)
        if fl is None:
            fl = files[num] = File(num, county=SF_COUNTY)
            fl.street, fl.city, fl.zip = (
                (addr or "").strip(),
                (city or "").strip(),
                (zipc or "").strip(),
            )
            fl.district = (district or "").strip()
            fl.dba, fl.owner = (dba or "").strip(), (owner or "").strip()
            added += 1
        fl.export_pending_types.add(typ or "0")
        if export_date and (fl.export_date is None or export_date > fl.export_date):
            fl.export_date = export_date
        if export_date:
            dates.add(export_date)
    superseded = sorted(n for n in seen if files[n].export_superseded())
    return {
        "export_date": max(dates).isoformat() if dates else None,
        "pending_application_files_in_export": len(seen),
        "of_which_not_in_the_archive": added,
        "of_which_withdrawn_or_denied_in_status_changes_on_or_after_the_export_date": len(
            superseded
        ),
        "those_files": superseded,
        "rule": "the export of a date is fetched before the Status Changes page of that date; a withdrawal or "
        "denial dated on or after the export date is the later record, and the file is not counted as pending",
    }


# ---------------------------------------------------------------------------- outcome and class


def classify(f: File, first_day: dt.date) -> None:
    """Outcome, outcome date, licence types of the application and original/transfer class."""
    perm = f.perm_issue_dates()
    licence = f.recs_of("licence")
    origs_in_archive = sorted(
        r.orig_issue for r in licence if r.orig_issue and r.orig_issue >= first_day
    )
    unissued_active = [r for r in licence if not r.orig_issue]
    withdrawn, denied, cancelled = (
        f.recs_of(WITHDRAWN),
        f.recs_of(DENIED),
        f.recs_of(CANCELLED),
    )
    f.notes = []
    if perm:
        f.outcome, f.outcome_date, f.outcome_basis = (
            ISSUED,
            perm[0],
            "Issued Licenses report date",
        )
        f.app_types = {r.type for r in f.issues[perm[0]] if r.type != TEMP_TYPE}
    elif origs_in_archive:
        f.outcome, f.outcome_date = ISSUED, origs_in_archive[0]
        f.outcome_basis = "Original Issue Date (file is not in Issued Licenses)"
        f.app_types = {r.type for r in licence if r.orig_issue == origs_in_archive[0]}
    elif unissued_active and not any(r.orig_issue for r in licence):
        r0 = min(unissued_active, key=lambda r: r.first)
        f.outcome, f.outcome_date = ISSUED, r0.first
        f.outcome_basis = "first status date of a PEND to ACTIVE record (no Original Issue Date, not in Issued Licenses)"
        f.app_types = {r.type for r in unissued_active}
    elif f.is_pending_now():
        f.outcome, f.outcome_date, f.outcome_basis = PENDING, None, ""
        f.app_types = {t for rows in f.listed.values() for _, t in rows}
        if f.export_pending():
            f.app_types |= f.export_pending_types
        f.app_types |= {r.type for r in f.recs_of("repended")}
        if withdrawn or denied:
            f.notes.append(
                "pending today, and a record on the file reads withdrawn or denied"
            )
    elif denied:
        f.outcome, f.outcome_date = DENIED, max(r.last for r in denied)
        f.outcome_basis = "last status date"
        f.app_types = {r.type for r in denied + withdrawn}
    elif withdrawn:
        f.outcome, f.outcome_date = WITHDRAWN, max(r.last for r in withdrawn)
        f.outcome_basis = "last status date"
        f.app_types = {r.type for r in withdrawn}
    elif cancelled:
        f.outcome, f.outcome_date = CANCELLED, max(r.last for r in cancelled)
        f.outcome_basis = "last status date"
        f.app_types = {r.type for r in cancelled}
    elif f.issues:
        f.outcome, f.outcome_date, f.outcome_basis = TEMP_ONLY, None, ""
        f.notes.append("temporary permit issued; no later record of the application")
    elif licence:
        f.outcome, f.outcome_date, f.outcome_basis = NO_APPLICATION, None, ""
    else:
        f.outcome, f.outcome_date, f.outcome_basis = UNCLEAR, None, ""
    if f.export_superseded():
        f.notes.append(
            f"pending in the citywide export of {f.export_date.isoformat()}; Status Changes shows a withdrawal "
            "or denial dated on or after that date, which is the later record"
        )
    if f.outcome == ISSUED:
        if f.listed:
            f.notes.append(
                f"a later application on this file is pending (listed {min(f.listed).isoformat()})"
            )
        later = [r for r in withdrawn + denied if r.last >= f.outcome_date]
        if later:
            f.notes.append(
                "a licence type on this issued file reads withdrawn or denied"
            )
    if not f.app_types:
        f.app_types = f.types() - {TEMP_TYPE} or f.types()

    # original / transfer / other: reported action first, Transfer-From/To otherwise
    acts: set[str] = set()
    if perm:
        acts = {r.action for r in f.issues[perm[0]] if r.type != TEMP_TYPE}
    elif f.listed:
        acts = {a for a, _ in f.listed[min(f.listed)]}
    elif f.issues:
        acts = {r.action for r in f.issues[min(f.issues)]}
    acts -= {""}
    f.action = " + ".join(sorted(acts))
    if acts:
        f.cls, f.cls_inferred = action_class(f.action), False
    else:
        f.cls, f.cls_inferred = inferred_class(f), True


def inferred_class(f: File) -> str:
    """Transfer-From/To present on the application's records = transfer. Used when no action is reported."""
    app = f.recs_of(WITHDRAWN, DENIED, CANCELLED, "repended") or list(f.recs.values())
    return "transfer" if any(r.transfer for r in app) else "original"


def never_issued_filing(f: File) -> tuple[dt.date | None, list[Rec]]:
    """First date of the file's never-issued records, when those records show two or more dates."""
    app = [r for r in f.recs_of(WITHDRAWN, DENIED, "repended") if len(r.dates) >= 2]
    return (min(r.first for r in app), app) if app else (None, [])


def is_new_number(f: File) -> bool:
    """True when nothing shows the file number existed before this application. A temporary permit issued
    while the application was pending does not make the number an old one."""
    return not f.recs_of("licence") and not f.perm_issue_dates()


def candidate_filing(f: File) -> tuple[dt.date | None, str]:
    """The filing date the reports give directly, and its basis, before the file-number check. No estimates.

    A first status date counts only on a file with no licence record: with an earlier Original Issue Date on
    the file, the first date seen in the archive need not be the filing.
    """
    first, _ = never_issued_filing(f)
    if f.outcome in (WITHDRAWN, DENIED):
        if first and first < f.outcome_date and is_new_number(f):
            return first, BASIS_STATUS
        return None, BASIS_NONE
    if f.outcome == PENDING:
        if f.recs_of("repended") and first and is_new_number(f):
            return first, BASIS_STATUS
        if f.listed:
            return min(f.listed), BASIS_LISTING
    return None, BASIS_NONE


# ---------------------------------------------------------------------------- file-number order


class NumberOrder:
    """Filing date as a function of file number, from files whose filing date the reports give."""

    def __init__(self, anchors: dict[int, dt.date]):
        self.pts = sorted((n, d.toordinal()) for n, d in anchors.items())
        self.nums = [n for n, _ in self.pts]

    def neighbours(
        self, n: int, exclude: int | None = None
    ) -> tuple[list[int], list[int]]:
        i = bisect.bisect_left(self.nums, n)
        lo: list[int] = []
        j = i - 1
        while (
            j >= 0
            and len(lo) < EST_NEIGHBOURS
            and n - self.pts[j][0] <= EST_NUMBER_SPAN
        ):
            if self.pts[j][0] != exclude:
                lo.append(self.pts[j][1])
            j -= 1
        hi: list[int] = []
        j = i
        while (
            j < len(self.pts)
            and len(hi) < EST_NEIGHBOURS
            and self.pts[j][0] - n <= EST_NUMBER_SPAN
        ):
            if self.pts[j][0] != exclude and self.pts[j][0] != n:
                hi.append(self.pts[j][1])
            j += 1
        return lo, hi

    def estimate(self, n: int, exclude: int | None = None) -> float | None:
        """Median filing date (as an ordinal) of up to 5 known files below and 5 above, all within 300 file
        numbers. None unless there are at least two on each side and they agree to within 30 days."""
        lo, hi = self.neighbours(n, exclude)
        if len(lo) < 2 or len(hi) < 2:
            return None
        near = sorted(lo + hi)
        trimmed = near[1:-1] if len(near) >= 6 else near
        if trimmed[-1] - trimmed[0] > EST_MAX_SPREAD_DAYS:
            return None
        return statistics.median(near)

    def estimate_date(self, n: int) -> dt.date | None:
        e = self.estimate(n)
        return dt.date.fromordinal(int(e + 0.5)) if e is not None else None

    def leave_one_out(self, sample: list[tuple[int, dt.date]]) -> dict:
        errs = []
        no_est = 0
        for n, d in sample:
            e = self.estimate(n, exclude=n)
            if e is None:
                no_est += 1
            else:
                errs.append(abs(e - d.toordinal()))
        return error_summary(errs, no_est)


def error_summary(errs: list[float], no_est: int = 0) -> dict:
    if len(errs) < 10:
        return {"n": len(errs), "no_estimate": no_est}
    return {
        "n": len(errs),
        "no_estimate": no_est,
        "median_abs_error_days": pct(errs, 0.5),
        "p90_abs_error_days": pct(errs, 0.9),
        "p99_abs_error_days": pct(errs, 0.99),
        "share_within_7_days": round(sum(e <= 7 for e in errs) / len(errs), 3),
    }


def inversions(anchors: dict[int, dt.date]) -> dict[int, int]:
    """For each dated file number: how many higher numbers carry a date more than 3 days earlier."""
    seen: list[int] = []
    inv: dict[int, int] = {}
    for n, d in sorted(anchors.items(), reverse=True):
        o = d.toordinal()
        inv[n] = bisect.bisect_left(seen, o - OUT_OF_ORDER_DAYS)
        bisect.insort(seen, o)
    return inv


def number_order(
    files: dict[str, File], first_day: dt.date, listing_since: dt.date
) -> tuple[NumberOrder | None, int | None, dict]:
    """The file-number order test, twice, and the decision whether file numbers may date a filing.

    A. New Applications listing dates since ``listing_since`` only, by action (ORI, PER, PRM, PER/PRM).
    B. Status-report first dates of never-issued files, all years, by class and by filing year; plus issued
       files that carry a withdrawn licence type whose first date precedes the issue, by action: their date is
       not in the reference set, so this is an out-of-sample check on issued files.
    Error = distance in days between a file's date and the median date of its nearest files by number.

    Returns the estimator (None if the test fails), the first file number handed out inside the archive, and
    the numbers. A file number below that start was handed out before the archive began (or in its first week):
    the first date the archive shows for it need not be the filing, so it is not used.
    """
    listing: dict[int, tuple[dt.date, str]] = {}
    status: dict[int, tuple[dt.date, str]] = {}
    issued_known: list[tuple[int, dt.date, str, int]] = []
    for f in files.values():
        if not f.number.isdigit():
            continue
        n = int(f.number)
        d, basis = candidate_filing(f)
        if d and is_new_number(f):
            if basis == BASIS_LISTING:
                listing[n] = (d, f.action)
            else:
                status[n] = (d, f"{f.cls}, inferred" if f.cls_inferred else f.action)
        elif f.outcome == ISSUED:
            first, _ = never_issued_filing(f)
            if first and first < f.outcome_date:
                issued_known.append((n, first, f.action, (f.outcome_date - first).days))
    res: dict = {}
    raw = {n: d for n, (d, _) in status.items()} | {
        n: d for n, (d, _) in listing.items() if n not in status
    }
    inv = inversions(raw)
    in_order = {n for n, k in inv.items() if k <= MAX_INVERSIONS}
    settled = [n for n in in_order if raw[n] >= first_day + dt.timedelta(days=7)]
    n_start = min(settled) if settled else None
    anchors = {
        n: d
        for n, d in raw.items()
        if n in in_order and n_start is not None and n >= n_start
    }
    res["reference_files"] = {
        "files_with_a_reported_date_and_a_new_number": len(raw),
        "first_file_number_handed_out_inside_the_archive": n_start,
        "that_number_was_filed_on": raw[n_start].isoformat() if n_start else None,
        "below_that_number_not_used": sum(n_start is None or n < n_start for n in raw),
        "of_which_status_report_first_dates": sum(
            n_start is None or n < n_start for n in status
        ),
        "out_of_order_not_used_as_reference": sum(
            n_start is not None and n >= n_start and n not in in_order for n in raw
        ),
        "out_of_order_means": f"more than {MAX_INVERSIONS} higher file numbers carry a date more than "
        f"{OUT_OF_ORDER_DAYS} days earlier",
        "used": len(anchors),
    }
    # A: New Applications listing dates since September 2025 only, as asked; nothing removed
    recent = {n: d for n, (d, _) in listing.items() if d >= listing_since}
    order_a = NumberOrder(recent)
    a: dict = {"reference_files": len(recent), "since": listing_since.isoformat()}
    for act in ("ORI", "PER", "PRM", "PER/PRM"):
        a[act] = order_a.leave_one_out(
            [(n, d) for n, (d, x) in listing.items() if x == act and n in recent]
        )
    a["all"] = order_a.leave_one_out(sorted(recent.items()))
    res["new_applications_listing_since_2025_09"] = a
    # B: status-report first dates, all years; file numbers from the archive's start on, nothing else removed
    ref = {n: d for n, (d, _) in status.items() if n_start is not None and n >= n_start}
    order_b = NumberOrder(ref)
    b: dict = {"reference_files": len(ref)}
    for cls in (
        "ORI",
        "PER",
        "PRM",
        "PER/PRM",
        "original, inferred",
        "transfer, inferred",
    ):
        b[cls] = order_b.leave_one_out(
            [(n, d) for n, (d, c) in status.items() if c == cls and n in ref]
        )
    b["all"] = order_b.leave_one_out(sorted(ref.items()))
    b["by_filing_year"] = {
        y: order_b.leave_one_out([(n, d) for n, d in ref.items() if d.year == y])
        for y in sorted({d.year for d in ref.values()})
    }
    res["status_report_first_dates_all_years"] = b
    # issued files with an independently known filing date, against the reference set actually used
    order = NumberOrder(anchors)
    chk: dict = {}
    for act in ("ORI", "PER", "PRM", "PER/PRM", "all"):
        errs, lead, no_est = [], [], 0
        for n, d, x, days in issued_known:
            if act != "all" and x != act:
                continue
            e = order.estimate(n)
            if e is None:
                no_est += 1
            else:
                errs.append(abs(e - d.toordinal()))
                lead.append(days)
        chk[act] = error_summary(errs, no_est)
        if len(lead) >= 10:
            chk[act]["days_from_that_first_date_to_issue"] = {
                "median": pct(lead, 0.5),
                "p90": pct(lead, 0.9),
            }
    res["issued_files_with_a_withdrawn_type_first_date"] = chk
    allb = b["all"]
    ok = (
        allb.get("median_abs_error_days") is not None
        and allb["median_abs_error_days"] <= EST_MAX_MEDIAN_ERROR_DAYS
        and allb["p90_abs_error_days"] <= EST_MAX_P90_ERROR_DAYS
    )
    res["estimate_rule"] = {
        "used": ok,
        "rule": f"median filing date of up to {EST_NEIGHBOURS} files below and {EST_NEIGHBOURS} above by number, "
        f"all within {EST_NUMBER_SPAN} numbers, at least two on each side, agreeing to within "
        f"{EST_MAX_SPREAD_DAYS} days; never later than the file's outcome date",
        "threshold": f"used only if test B (all) has median error <= {EST_MAX_MEDIAN_ERROR_DAYS} days and "
        f"p90 <= {EST_MAX_P90_ERROR_DAYS} days",
    }
    # file numbers handed out per fiscal year: the first number of each year, from the reference files
    by_number = sorted(anchors.items())
    handed: dict[str, dict] = {}
    if by_number:
        last = max(d for _, d in by_number)
        for y in range(first_day.year, last.year + 1):
            lo_d, hi_d = dt.date(y, 7, 1), dt.date(y + 1, 7, 1)
            lo = next((n for n, d in by_number if d >= lo_d), None)
            hi = next((n for n, d in by_number if d >= hi_d), None)
            if lo is None or hi is None or lo_d < first_day + dt.timedelta(days=7):
                continue
            seen = [
                f
                for f in files.values()
                if f.number.isdigit() and lo <= int(f.number) < hi
            ]
            handed[fiscal_year(lo_d)] = {
                "first_number": lo,
                "numbers_handed_out": hi - lo,
                "of_which_in_the_archive": len(seen),
                "by_outcome": dict(Counter(f.outcome for f in seen).most_common()),
            }
    res["file_numbers_handed_out_by_fiscal_year"] = handed
    return (order if ok else None), n_start, res


def assign_filing(
    files: dict[str, File], order: NumberOrder | None, n_start: int | None
) -> dict:
    """Filing date and basis for every file with an application; returns counts of what was estimated."""
    info = Counter()
    for f in files.values():
        f.filed, f.filed_basis, f.filed_note = None, BASIS_NONE, ""
        if not f.has_application():
            continue
        num = int(f.number) if f.number.isdigit() else None
        d, basis = candidate_filing(f)
        if (
            d
            and basis == BASIS_STATUS
            and (num is None or n_start is None or num < n_start)
        ):
            d = None
            f.filed_note = (
                "the file number was handed out before the archive began (or in its first week), so the first "
                "status date in the archive need not be the filing"
            )
            info["first status date not used: file number older than the archive"] += 1
        if d:
            f.filed, f.filed_basis = d, basis
            continue
        est = order.estimate_date(num) if order and num is not None else None
        if f.outcome == ISSUED:
            first, _ = never_issued_filing(f)
            if (
                first
                and first < f.outcome_date
                and est
                and abs((est - first).days) <= 7
            ):
                f.filed, f.filed_basis = first, BASIS_STATUS_ISSUED
                continue
            f.filed_note = (
                f.filed_note
                or "issued records show no date before the Original Issue Date"
            )
        elif f.outcome in (WITHDRAWN, DENIED, CANCELLED) and not f.filed_note:
            if is_new_number(f):
                f.filed_note = "one status date only: filed before the archive began, or on the same day"
            else:
                f.filed_note = "the file has an earlier licence, so the first status date need not be the filing"
        if est is None:
            info[
                "no estimate: no dated file numbers nearby (file number older than the archive)"
            ] += 1
            continue
        if f.outcome_date and est > f.outcome_date:
            info["no estimate: file-number date is after the outcome date"] += 1
            continue
        if f.outcome != ISSUED and not is_new_number(f) and f.outcome != TEMP_ONLY:
            info["no estimate: application on a file that had a licence already"] += 1
            continue
        f.filed, f.filed_basis = est, BASIS_ESTIMATE
        info["estimated"] += 1
    return dict(sorted(info.items()))


# ---------------------------------------------------------------------------- priority-drawing entries


def mark_priority(files: dict[str, File]) -> dict:
    """Priority-drawing entries: never-issued files of general type that are originals, whatever the filing date.

    The rule: outcome withdrawn, denied or pending; no licence record on the file; licence type 21, 47 or 48;
    class original, from the reported action (ORI) or, with no reported action, from the absence of a
    Transfer-From/To on the file's status records. A pending file with neither an action nor a status record
    has no class evidence and is not marked.

    A new general licence can only be applied for through the priority drawing, so the rule needs no date. The
    application-window days are computed afterwards, as evidence: where the entries' reported filing dates fall.
    """

    def candidate(f: File) -> bool:
        return (
            f.outcome in (WITHDRAWN, DENIED, PENDING)
            and is_new_number(f)
            and f.general_original()
        )

    filed_on = Counter()
    no_class_evidence = 0
    for f in files.values():
        f.priority, f.priority_reason = False, ""
        if not candidate(f):
            continue
        if f.cls_inferred and not f.recs:
            no_class_evidence += 1
            continue
        f.priority = True
        if f.filed and f.filed_basis in KNOWN_BASES:
            filed_on[f.filed] += 1
    window = {d for d, n in filed_on.items() if n >= WINDOW_DAY_MIN}
    seasons: dict[int, list[dt.date]] = defaultdict(list)
    for d in window:
        seasons[d.year].append(d)
    spans = {y: (min(v), max(v)) for y, v in seasons.items()}
    near = dt.timedelta(days=WINDOW_NEAR_DAYS)

    def where_filed(f: File) -> str:
        if not f.filed or f.filed_basis not in KNOWN_BASES:
            return "no reported filing date"
        if f.filed in window:
            return "filed on an application-window day"
        if any(lo <= f.filed <= hi for lo, hi in spans.values()):
            return f"filed inside an application window, on a day with fewer than {WINDOW_DAY_MIN} such filings"
        if any(lo - near <= f.filed <= hi + near for lo, hi in spans.values()):
            return f"filed within {WINDOW_NEAR_DAYS} days of an application window"
        return "filed outside the application windows"

    where: Counter = Counter()
    no_date_by_year: Counter = Counter()
    transfers_on_window = 0
    for f in files.values():
        if (
            not f.priority
            and f.outcome in (WITHDRAWN, DENIED, PENDING)
            and f.app_types & GENERAL_TYPES
            and f.cls != "original"
            and f.filed in window
        ):
            transfers_on_window += 1
        if not f.priority:
            continue
        w = where_filed(f)
        where[w] += 1
        if w == "no reported filing date" and f.outcome_date:
            no_date_by_year[f.outcome_date.year] += 1
        basis = (
            "no Transfer-From/To on its records"
            if f.cls_inferred
            else "reported action ORI"
        )
        f.priority_reason = (
            f"never issued, general licence type, original ({basis}); {w}"
        )
    return {
        "rule": "never-issued file (withdrawn, denied or pending; no licence record on the file) of type 21, 47 "
        "or 48 that is an original: reported action ORI or, with no reported action, no Transfer-From/To on "
        "its status records. The filing date plays no part.",
        "entries": sum(f.priority for f in files.values()),
        "entries_by_outcome": dict(
            Counter(f.outcome for f in files.values() if f.priority).most_common()
        ),
        "entries_by_class_evidence": dict(
            Counter(
                "no Transfer-From/To (class inferred)"
                if f.cls_inferred
                else "reported action ORI"
                for f in files.values()
                if f.priority
            ).most_common()
        ),
        "not_marked_pending_with_no_action_and_no_status_record": no_class_evidence,
        "issued_general_type_originals": sum(
            f.outcome == ISSUED and f.general_original() for f in files.values()
        ),
        "evidence_only_application_windows": {
            "window_day_means": f"a day on which {WINDOW_DAY_MIN} or more entries were filed (reported filing "
            "dates only)",
            "where_the_entries_were_filed": dict(where.most_common()),
            "entries_with_no_reported_filing_date_by_year_of_outcome": dict(
                sorted(no_date_by_year.items())
            ),
            "never_issued_general_type_transfers_filed_on_a_window_day_not_entries": transfers_on_window,
            "window_days": sorted(d.isoformat() for d in window),
            "window_days_by_year": {y: len(v) for y, v in sorted(seasons.items())},
            "window_span_by_year": {
                y: [lo.isoformat(), hi.isoformat()]
                for y, (lo, hi) in sorted(spans.items())
            },
        },
    }


# ---------------------------------------------------------------------------- helpers


def fiscal_year(d: dt.date) -> str:
    y = d.year if d.month >= 7 else d.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 1)


def timing(xs: list[float]) -> dict:
    """Median and p90 with N; the count only where N is under 10."""
    if len(xs) < 10:
        return {"n": len(xs)}
    return {"n": len(xs), "median": pct(xs, 0.5), "p90": pct(xs, 0.9)}


def spread(xs: list[float]) -> dict:
    if len(xs) < 10:
        return {"n": len(xs)}
    return {
        "n": len(xs),
        "median": pct(xs, 0.5),
        "p10": pct(xs, 0.1),
        "p90": pct(xs, 0.9),
    }


def scopes(f: File) -> tuple[str, ...]:
    return (
        ("statewide",)
        + (("sf_office",) if f.district == SF_DISTRICT else ())
        + (("sf_county",) if f.county == SF_COUNTY else ())
    )


PATTERN_ISSUED_SIMPLE = (
    "simple: first status date is the Original Issue Date and the Issued Licenses date; "
    "later dates are the next business day and later changes"
)


def pattern(f: File) -> str:
    """Which of the simple date patterns the file follows, or why it does not."""
    kinds = Counter(r.kind for r in f.recs.values())
    if f.outcome in (WITHDRAWN, DENIED):
        app = f.recs_of(WITHDRAWN, DENIED)
        dates = {frozenset(r.dates) for r in app}
        if (
            kinds["licence"]
            or kinds["other"]
            or kinds[CANCELLED]
            or f.perm_issue_dates()
        ):
            return "not simple: other records on the file"
        if len(dates) > 1:
            return "not simple: records with different dates"
        n = len(next(iter(dates)))
        if n == 2:
            return "simple: two dates (filed, then withdrawn or denied)"
        return (
            "one date only (filing date not in the report)"
            if n == 1
            else "not simple: more than two dates"
        )
    if f.outcome == ISSUED:
        perm = f.perm_issue_dates()
        lic = f.recs_of("licence")
        if len(perm) > 1:
            return "not simple: several issue dates"
        if (
            kinds[WITHDRAWN]
            or kinds[DENIED]
            or kinds["other"]
            or kinds["repended"]
            or kinds[CANCELLED]
        ):
            return "not simple: other records on the file"
        if not perm or not lic:
            return "not simple: missing from Issued Licenses or from Status Changes"
        origs = {r.orig_issue for r in lic}
        if len(origs) > 1 or None in origs:
            return "not simple: several Original Issue Dates"
        orig = next(iter(origs))
        if perm[0] != orig:
            return "not simple: Issued Licenses date is not the Original Issue Date"
        sd = f.status_dates()
        if sd[0] < orig:
            return "not simple: a status date before the Original Issue Date"
        if sd[0] > orig:
            return "not simple: first status date is after the Original Issue Date"
        return PATTERN_ISSUED_SIMPLE
    if f.outcome == PENDING:
        return (
            "simple: listed as pending"
            if not f.recs
            else "not simple: pending with status records"
        )
    return ""


# ---------------------------------------------------------------------------- Planning referrals


def shared_name(referral_name: str, f: File) -> str:
    """The business name a referral and an ABC file have in common, or "".

    Planning's text after "dba" runs on into the description ("ZHUZH BAR AUTHORIZES THE SALE OF BEER"), so the
    referral's name counts when it is contained in ABC's DBA or begins with it, and only the part the two share
    is returned. Nothing else of Planning's free text is ever published."""
    abc = norm_name(f.dba)
    if not referral_name or not abc:
        return ""
    if referral_name in abc:
        return referral_name
    if len(abc) >= 4 and (referral_name + " ").startswith(abc + " "):
        return abc
    return ""


def planning_match(
    files: dict[str, File], first_day: dt.date
) -> tuple[dict, list[dict]]:
    """Match Planning's dated ABC referrals to file numbers by address, then by business name, licence type and
    the closeness of the file's outcome date. The filing date plays no part in the match, so the comparison of
    the two dates afterwards is a fair one."""
    import psycopg

    with psycopg.connect(LOCAL) as conn:
        conn.read_only = True
        referrals = conn.execute(
            f"""select a.source_id, a.address, a.description, a.filed_at
                from applications a join record_labels r using (id)
                where a.source='datasf_planning' and r.record_kind='agency_referral' and r.premises
                  and a.description ~* '{ABC_RX}' and a.filed_at is not null"""
        ).fetchall()
    index: dict[tuple[int, str], list[File]] = defaultdict(list)
    for f in files.values():
        if f.county == SF_COUNTY and f.outcome in (ISSUED, WITHDRAWN, DENIED, PENDING):
            for k in keys(f.street):
                index[k].append(f)
    matched: dict[str, tuple[dt.date, str]] = {}
    by_year: dict[int, Counter] = defaultdict(Counter)
    rows: list[dict] = []
    for record, address, desc, filed in referrals:
        if filed < first_day - dt.timedelta(days=365):
            continue
        y = filed.year
        by_year[y]["referrals"] += 1
        cands = {f.number: f for k in keys(address) for f in index.get(k, [])}
        types, dba = named_types(desc), referral_dba(desc)
        best = None
        for f in cands.values():
            ref_date = f.outcome_date or f.listing_date()
            if ref_date is None or not -45 <= (ref_date - filed).days <= 900:
                continue
            type_ok = not types or bool({t.zfill(2) for t in f.types()} & types)
            name_ok = bool(shared_name(dba, f))
            score = (name_ok, type_ok, -abs((ref_date - filed).days))
            if best is None or score > best[0]:
                how = (
                    "name"
                    if name_ok
                    else "type"
                    if type_ok and types
                    else "address and date"
                )
                best = (score, f, how)
        if best is None:
            by_year[y]["no_file_at_address_in_window"] += 1
            continue
        _, f, how = best
        by_year[y]["matched"] += 1
        by_year[y][f"by_{how.replace(' ', '_')}"] += 1
        if f.number not in matched or filed < matched[f.number][0]:
            matched[f.number] = (filed, how)
        rows.append(
            {
                "planning_record": record,
                "referral_filed": filed.isoformat(),
                "referral_address": address,
                "referral_names_types": " ".join(sorted(types)),
                "referral_names_business": shared_name(dba, f)
                if f.business_name() != NAME_WITHHELD
                else "",
                "abc_file": f.number,
                "abc_business": shown_name(f.business_name()),
                "abc_name_withheld": withheld_flag(f.business_name()),
                "abc_address": f.premises(),
                "abc_types": " ".join(sorted(f.types(), key=type_key)),
                "abc_class": f.class_label(),
                "matched_on": how,
                "abc_filing_date": f.filed.isoformat() if f.filed else "",
                "abc_filing_date_basis": f.filed_basis,
                "abc_filing_minus_referral_days": (f.filed - filed).days
                if f.filed
                else "",
                "abc_outcome": f.outcome,
                "abc_outcome_date": f.outcome_date.isoformat()
                if f.outcome_date
                else "",
            }
        )

    def gap_stats(pairs: list[int]) -> dict:
        s = spread(pairs)
        if pairs:
            s["share_within_30_days"] = round(
                sum(abs(g) <= 30 for g in pairs) / len(pairs), 3
            )
            s["share_filed_at_abc_first"] = round(
                sum(g <= 0 for g in pairs) / len(pairs), 3
            )
        return s

    gaps: dict[str, list[int]] = defaultdict(list)
    for n, (ref, how) in matched.items():
        f = files[n]
        if not f.filed:
            gaps["no filing date"].append(0)
            continue
        g = (f.filed - ref).days
        known = (
            "reported" if f.filed_basis in KNOWN_BASES else "estimated from file number"
        )
        gaps["all"].append(g)
        gaps[known].append(g)
        gaps[f"matched on {how}"].append(g)
        if how in ("name", "type"):
            gaps["matched on name or type"].append(g)
    info = {
        "by_year": {y: dict(c) for y, c in sorted(by_year.items())},
        "referrals": sum(c["referrals"] for c in by_year.values()),
        "matched": sum(c["matched"] for c in by_year.values()),
        "files_matched": len(matched),
        "files_matched_without_a_filing_date": len(gaps.pop("no filing date", [])),
        "abc_filing_date_minus_planning_referral_date_days": {
            k: gap_stats(v) for k, v in sorted(gaps.items())
        },
    }
    return info, rows


# ---------------------------------------------------------------------------- the evidence for the reading


def reading_evidence(files: dict[str, File], first_day: dt.date) -> dict:
    """Recompute, from the archive, the facts the model of the Status Changes report rests on.

    Every count is of files: a file counts once if any of its licence-type records fits. The number of
    licence-type records is kept beside it under ``licence_type_records``, labelled as such."""
    multi_date_same = multi_date = 0
    files_record_differs = records_differ = 0
    for f in files.values():
        view: dict[tuple, set] = defaultdict(set)
        for r in f.recs.values():
            view[(r.type, r.dup)].add((r.frm, r.to))
        differ = sum(len(v) > 1 for v in view.values())
        records_differ += differ
        files_record_differs += differ > 0
        if len(f.status_dates()) > 1:
            multi_date += 1
            multi_date_same += len(f.transitions()) == 1
    iss: Counter = Counter()
    gaps_issued: list[int] = []
    gaps_withdrawn: list[int] = []
    wd_files = wd_records = 0
    oid: Counter = Counter()
    for f in files.values():
        perm = set(f.perm_issue_dates())
        two = [
            r
            for r in f.recs.values()
            if (r.frm, r.to) == ("PEND", "ACTIVE")
            and len(r.dates) == 2
            and r.orig_issue
        ]
        if two:
            iss["files"] += 1
            iss["records"] += len(two)
            iss["first_is_orig"] += any(r.first == r.orig_issue for r in two)
            iss["within_5"] += any((r.last - r.first).days <= 5 for r in two)
            iss["issued_on_first"] += any(r.first in perm for r in two)
            iss["issued_on_second_only"] += any(
                r.last in perm and r.first not in perm for r in two
            )
            iss["records_issued_on_first"] += sum(r.first in perm for r in two)
            iss["records_issued_on_second_only"] += sum(
                r.last in perm and r.first not in perm for r in two
            )
            r0 = min(two, key=lambda r: r.first)
            gaps_issued.append((r0.last - r0.first).days)
        wd2 = (
            [r for r in f.recs.values() if r.kind == WITHDRAWN and len(r.dates) == 2]
            if is_new_number(f)
            else []
        )
        if wd2:
            wd_files += 1
            wd_records += len(wd2)
            r0 = min(wd2, key=lambda r: r.first)
            gaps_withdrawn.append((r0.last - r0.first).days)
        origs = {
            r.orig_issue
            for r in f.recs_of("licence")
            if r.orig_issue and r.orig_issue >= first_day
        }
        if perm and origs:
            oid["files"] += 1
            oid["equal"] += bool(perm & origs)
    statuses = Counter()
    temp_only = perm_files = 0
    for f in files.values():
        if not f.issues:
            continue
        rows = [r for rs in f.issues.values() for r in rs]
        if all(r.type == TEMP_TYPE for r in rows):
            temp_only += 1
        else:
            perm_files += 1
        for s in {r.status for r in rows if r.type != TEMP_TYPE}:
            statuses[s] += 1
    listed = [f for f in files.values() if f.listed]
    return {
        "counts_are": "files; a file counts once if any of its licence-type records fits",
        "status_changes": {
            "files_on_more_than_one_date": multi_date,
            "of_which_show_one_and_the_same_transition_on_every_date": multi_date_same,
            "files_showing_two_or_more_different_transitions": sum(
                len(f.transitions()) > 1 for f in files.values()
            ),
            "files_with_one_licence_type_record_showing_different_transitions": files_record_differs,
            "licence_type_records": {
                "records_showing_two_or_more_different_transitions": records_differ
            },
        },
        "issued_files_pend_to_active_with_two_dates": {
            "files": iss["files"],
            "first_date_is_the_original_issue_date": iss["first_is_orig"],
            "issued_licences_date_equals_the_first_date": iss["issued_on_first"],
            "issued_licences_date_equals_the_second_date_and_not_the_first": iss[
                "issued_on_second_only"
            ],
            "two_dates_within_5_days": iss["within_5"],
            "days_between_the_two_dates": spread(gaps_issued),
            "licence_type_records": {
                "records": iss["records"],
                "issued_licences_date_equals_the_first_date": iss[
                    "records_issued_on_first"
                ],
                "issued_licences_date_equals_the_second_date_and_not_the_first": iss[
                    "records_issued_on_second_only"
                ],
            },
        },
        "never_issued_withdrawn_files_with_two_dates": {
            "files": wd_files,
            "days_between_the_two_dates": spread(gaps_withdrawn),
            "licence_type_records": {"records": wd_records},
        },
        "issued_licences": {
            "files_with_a_permanent_licence_row": perm_files,
            "files_with_temporary_permit_rows_only_type_30": temp_only,
            "files_by_status_today": dict(statuses.most_common()),
            "files_with_a_permanent_row_and_an_original_issue_date_in_the_archive_period": oid[
                "files"
            ],
            "of_which_an_issued_licences_date_is_the_original_issue_date": oid["equal"],
        },
        "new_applications": {
            "files_listed": len(listed),
            "of_which_also_issued_in_the_archive": sum(
                f.outcome == ISSUED for f in listed
            ),
            "listing_dates_by_year": dict(
                sorted(Counter(min(f.listed).year for f in listed).items())
            ),
        },
    }


# ---------------------------------------------------------------------------- tables


def workload(files: dict[str, File]) -> dict:
    """Counts per fiscal year and scope for the check against ABC. A file counts once per year and measure."""
    wl: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for f in files.values():
        sc = scopes(f)
        fys_perm: dict[str, set[str]] = defaultdict(set)
        fys_inv: dict[str, set[str]] = defaultdict(set)
        fys_temp_only: set[str] = set()
        for d, rows in f.issues.items():
            perm_rows = [r for r in rows if r.type != TEMP_TYPE]
            if perm_rows:
                action = " + ".join(sorted({r.action for r in perm_rows}))
                fys_perm[fiscal_year(d)].add(action_class(action))
                fys_inv[fiscal_year(d)].add(investigation_class(action))
        for d in f.issues:
            if fiscal_year(d) not in fys_perm:
                fys_temp_only.add(fiscal_year(d))
        for fy, classes in fys_perm.items():
            cls = (
                "original"
                if "original" in classes
                else "transfer"
                if "transfer" in classes
                else "other"
            )
            inv = (
                ISSUED_ORIGINAL_INV
                if ORIGINAL_INVESTIGATION in fys_inv[fy]
                else ISSUED_TRANSFER_INV
            )
            for s in sc:
                wl[fy][s]["issued files (permanent licences)"] += 1
                wl[fy][s][f"issued files, {cls}"] += 1
                wl[fy][s][inv] += 1
                wl[fy][s]["files in Issued Licenses, temporary permits included"] += 1
        for fy in fys_temp_only:
            for s in sc:
                wl[fy][s]["files with a temporary permit only (type 30)"] += 1
                wl[fy][s]["files in Issued Licenses, temporary permits included"] += 1
        if f.outcome == ISSUED and not f.perm_issue_dates():
            for s in sc:
                wl[fiscal_year(f.outcome_date)][s][
                    "issued by Original Issue Date, not in Issued Licenses"
                ] += 1
        if f.outcome in (WITHDRAWN, DENIED, CANCELLED):
            fy = fiscal_year(f.outcome_date)
            key = {
                WITHDRAWN: PRIORITY_WITHDRAWN
                if f.priority
                else "withdrawn files (not priority)",
                DENIED: "denied files",
                CANCELLED: "cancelled while pending",
            }[f.outcome]
            late = (
                f.priority
                and f.outcome == WITHDRAWN
                and f.filed is not None
                and f.filed_basis in KNOWN_BASES
                and (f.outcome_date - f.filed).days >= 365
            )
            for s in sc:
                wl[fy][s][key] += 1
                if late:
                    wl[fy][s][PRIORITY_LATE] += 1
                if f.outcome == WITHDRAWN and not f.priority:
                    wl[fy][s][f"withdrawn files (not priority), {f.cls}"] += 1
                    if f.recs_of("licence"):
                        wl[fy][s][
                            "withdrawn files (not priority), on a file with an earlier licence"
                        ] += 1
        if f.outcome == ISSUED:
            for fy in {
                fiscal_year(r.last)
                for r in f.recs_of(WITHDRAWN)
                if r.last >= f.outcome_date
            }:
                for s in sc:
                    wl[fy][s][
                        "issued files with a withdrawn licence type (not counted as withdrawn)"
                    ] += 1
        if f.filed and (f.priority or (f.outcome == ISSUED and f.general_original())):
            key = PRIORITY_FILED if f.priority else PRIORITY_ISSUED
            for s in sc:
                wl[fiscal_year(f.filed)][s][key] += 1
                wl[fiscal_year(f.filed)][s][PRIORITY_ALL] += 1
        if f.filed and f.filed_basis != BASIS_NONE and f.has_application():
            for s in sc:
                wl[fiscal_year(f.filed)][s][
                    "files with a filing date in the year (any basis)"
                ] += 1
    return {
        fy: {s: dict(sorted(c.items())) for s, c in v.items()}
        for fy, v in sorted(wl.items())
    }


def label_partial_years(wl: dict, first_day: dt.date, last_day: dt.date) -> dict:
    """Fiscal years the archive covers only in part get their coverage in the key:
    '2018-19 (partial: 2019-01-01 to 2019-06-30)'. Complete years keep the plain key."""
    out = {}
    for fy, v in wl.items():
        y = int(fy[:4])
        lo, hi = dt.date(y, 7, 1), dt.date(y + 1, 6, 30)
        a, b = max(lo, first_day), min(hi, last_day)
        if (a, b) == (lo, hi):
            out[fy] = v
        elif a > b:
            out[f"{fy} (outside the archive)"] = v
        else:
            out[f"{fy} (partial: {a.isoformat()} to {b.isoformat()})"] = v
    return out


def partial_year_note(first_day: dt.date, last_day: dt.date) -> str:
    """The note that goes next to every calendar-year table: which years the archive covers only in part."""
    parts = []
    if first_day > dt.date(first_day.year, 1, 1):
        parts.append(
            f"{first_day.year} is a part-year: the archive begins on {first_day.isoformat()}"
        )
    if last_day < dt.date(last_day.year, 12, 31):
        parts.append(
            f"{last_day.year} is a part-year: {last_day.year}-01-01 to {last_day.isoformat()} only"
        )
    return "; ".join(parts) or "every year shown is a complete calendar year"


def office_territory(files: dict[str, File]) -> list[dict]:
    """Issued files (permanent licences) for the San Francisco and San Jose offices, by district code and by
    county, next to ABC's approved investigations for the two offices.

    The district code on a file is the office that holds the premises today. San Mateo county files carry San
    Jose's code 25, but in FY2019-20 the San Francisco office still handled San Mateo county, so that year the
    district-24 count and ABC's San Francisco row cover different territories."""
    c: dict[str, Counter] = defaultdict(Counter)
    for f in files.values():
        for fy in {fiscal_year(d) for d in f.perm_issue_dates()}:
            c[fy]["d24"] += f.district == SF_DISTRICT
            c[fy]["d25"] += f.district == SAN_JOSE_DISTRICT
            c[fy]["sf"] += f.county == SF_COUNTY
            c[fy]["sm"] += f.county == SAN_MATEO_COUNTY
            c[fy]["sm24"] += f.county == SAN_MATEO_COUNTY and f.district == SF_DISTRICT
    abc = abc_workload.load_rows({"sf": "San Francisco", "sj": "San Jose"})
    rows = []
    for fy in abc_workload.YEARS:
        k = c[fy]
        abc_sf = sum(abc[fy][cls]["sf"]["approved"] for cls in abc_workload.TABLES)
        abc_sj = sum(abc[fy][cls]["sj"]["approved"] for cls in abc_workload.TABLES)
        rows.append(
            {
                "fiscal_year": fy,
                "issued_files_district_24": k["d24"],
                "issued_files_sf_county": k["sf"],
                "issued_files_san_mateo_county": k["sm"],
                "of_which_carry_district_24": k["sm24"],
                "sf_county_plus_san_mateo_county": k["sf"] + k["sm"],
                "abc_san_francisco_office_approved": abc_sf,
                "gap_pct_district_24": gap_pct(k["d24"], abc_sf),
                "gap_pct_sf_plus_san_mateo_counties": gap_pct(
                    k["sf"] + k["sm"], abc_sf
                ),
                "issued_files_district_25": k["d25"],
                "abc_san_jose_office_approved": abc_sj,
                "gap_pct_district_25": gap_pct(k["d25"], abc_sj),
                "issued_files_districts_24_and_25": k["d24"] + k["d25"],
                "abc_both_offices_approved": abc_sf + abc_sj,
                "gap_pct_both_offices": gap_pct(k["d24"] + k["d25"], abc_sf + abc_sj),
            }
        )
    return rows


SMALL_N = 10  # below this, counts only: no percentage, median or percentile


def gap_pct(ours: int, abc: int) -> float | None:
    """Percentage gap, or None where either count is under 10 (or ABC's is zero)."""
    if not abc or ours < SMALL_N or abc < SMALL_N:
        return None
    return round((ours - abc) / abc * 100, 1)


ISSUED_ORIGINAL_INV = "issued files, original investigation (ORI, PRM, ICO)"
ISSUED_TRANSFER_INV = (
    "issued files, transfer investigation (PER, FID, DPR, STK and other actions)"
)
PRIORITY_WITHDRAWN = "priority entries withdrawn"
PRIORITY_FILED = "priority entries filed (withdrawn, denied or pending)"
PRIORITY_ISSUED = "issued general-type originals, by filing year"
PRIORITY_ALL = "general-type originals filed (never issued, pending or issued)"
PRIORITY_LATE = "priority entries withdrawn 12 or more months after filing (not moved)"
HANDED_OUT = "file numbers handed out"
GROUPING_ALL = "all actions together"
GROUPING_ABC = (
    "ABC's investigation grouping: original = ORI, PRM (alone or with PER), ICO; transfer = PER, FID, DPR, "
    "STK and every other action"
)
GROUPING_CLASS = (
    "application class, not ABC's grouping: original = ORI only; transfer = PER and/or PRM. Shown for the "
    "size of the difference; ABC's original table also holds premises transfers"
)
GROUPING = {
    ISSUED_ORIGINAL_INV: GROUPING_ABC,
    ISSUED_TRANSFER_INV: GROUPING_ABC,
    "issued files, original": GROUPING_CLASS,
    "issued files, transfer": GROUPING_CLASS,
}
CHECKS = [
    # (our measure, ABC measure, scopes)
    ("issued files (permanent licences)", "Permanent Licenses Issued", ("statewide",)),
    (
        "files in Issued Licenses, temporary permits included",
        "Permanent Licenses Issued",
        ("statewide",),
    ),
    (
        "issued files (permanent licences)",
        "Applications Recommended for Approval",
        ("statewide",),
    ),
    (
        "issued files (permanent licences)",
        "investigations approved (original + transfer)",
        ("sf_office",),
    ),
    (
        ISSUED_ORIGINAL_INV,
        "investigations approved, original",
        ("statewide", "sf_office"),
    ),
    (
        ISSUED_TRANSFER_INV,
        "investigations approved, transfer",
        ("statewide", "sf_office"),
    ),
    (
        "issued files, original",
        "investigations approved, original",
        ("statewide", "sf_office"),
    ),
    (
        "issued files, transfer",
        "investigations approved, transfer",
        ("statewide", "sf_office"),
    ),
    ("withdrawn files (not priority)", "Applications Withdrawn", ("statewide",)),
    (
        "withdrawn files (not priority)",
        "investigations withdrawn (original + transfer)",
        ("sf_office",),
    ),
    (
        "withdrawn files (not priority)",
        "investigations withdrawn + voided + no credit WD",
        ("statewide", "sf_office"),
    ),
    # Priority applications received = every general-type original filed in the year, whatever became of it.
    # Its parts (PRIORITY_FILED, PRIORITY_ISSUED) and the entries withdrawn in the year are in
    # workload_from_archive; they are parts, not comparable with ABC's figure, so they are not rows here.
    (PRIORITY_ALL, "Priority License Applications Received", ("statewide",)),
    (HANDED_OUT, "Permanent + Priority License Applications Received", ("statewide",)),
    ("denied files", "Applications Recommended for Denial", ("statewide",)),
    ("denied files", "investigations denied (original + transfer)", ("sf_office",)),
]


def territory_note(territory: list[dict]) -> str:
    t = next(r for r in territory if r["fiscal_year"] == "2019-20")
    return (
        "District code 24 is the San Francisco office's territory today. In FY2019-20 that office still handled "
        "San Mateo county, whose files now carry San Jose's code 25, so this row compares different territories. "
        f"San Francisco county plus San Mateo county: {t['sf_county_plus_san_mateo_county']:,} issued files "
        f"against ABC's {t['abc_san_francisco_office_approved']:,} approved investigations; the two offices "
        f"together: {t['issued_files_districts_24_and_25']:,} against {t['abc_both_offices_approved']:,}. The "
        "handover date (about late January 2020, the second verifier's estimate from San Mateo files that still "
        "carry code 24) is inferred, not stated by ABC, and is not recomputed here."
    )


def check_against_abc(wl: dict, territory: list[dict]) -> list[dict]:
    """Our counts next to ABC's, for the seven complete fiscal years. A percentage is given only where both
    counts are 10 or more. Every row says which grouping of actions it uses."""
    figures = abc_workload.abc_figures()
    restated = abc_workload.restated_figures()
    note = territory_note(territory)
    rows = []
    for fy in abc_workload.YEARS:
        for ours_key, abc_key, in_scopes in CHECKS:
            for scope in in_scopes:
                ours = wl.get(fy, {}).get(scope, {}).get(ours_key, 0)
                abc = figures[fy][scope][abc_key]
                row = {
                    "fiscal_year": fy,
                    "scope": scope,
                    "measure": ours_key,
                    "ours": ours,
                    "abc_measure": abc_key,
                    "abc": abc,
                    "gap_pct": gap_pct(ours, abc),
                    "grouping": GROUPING.get(ours_key, GROUPING_ALL),
                }
                if ours < SMALL_N or abc < SMALL_N:
                    row["gap_note"] = "a count is under 10: counts only, no percentage"
                later = restated.get(fy, {}).get(abc_key)
                if scope == "statewide" and later is not None:
                    row["abc_restated_on_a_later_page"] = later
                    row["gap_pct_against_restated"] = gap_pct(ours, later)
                if scope == "sf_office" and fy == "2019-20":
                    row["territory_note"] = note
                rows.append(row)
    return rows


def from_pending(files: dict[str, File]) -> dict:
    """Every latest transition out of a pending state, in files, split by whether the record was ever issued."""
    out: dict[str, dict[str, dict[str, int]]] = {}
    for scope, keep in (
        ("statewide", lambda f: True),
        ("sf_county", lambda f: f.county == SF_COUNTY),
    ):
        c: dict[str, Counter] = defaultdict(Counter)
        for f in files.values():
            if not keep(f):
                continue
            seen: set[tuple[str, bool]] = set()
            for r in f.recs.values():
                if r.frm in PENDING_STATES:
                    seen.add((r.label(), bool(r.orig_issue)))
            for lab in {lab for lab, _ in seen}:
                c[lab]["files"] += 1
            for lab, has_orig in seen:
                c[lab][
                    "with an Original Issue Date" if has_orig else "never issued"
                ] += 1
        out[scope] = {
            k: dict(v) for k, v in sorted(c.items(), key=lambda kv: -kv[1]["files"])
        }
    return out


def other_never_issued(files: dict[str, File]) -> dict:
    """Latest transitions of never-issued records that do not start from a pending state, in files."""
    out: dict[str, dict[str, int]] = {}
    for scope, keep in (
        ("statewide", lambda f: True),
        ("sf_county", lambda f: f.county == SF_COUNTY),
    ):
        c = Counter()
        for f in files.values():
            if keep(f):
                for lab in {
                    r.label()
                    for r in f.recs.values()
                    if not r.orig_issue and r.frm not in PENDING_STATES
                }:
                    c[lab] += 1
        out[scope] = dict(c.most_common())
    return out


def reading_statement(result: dict) -> list[str]:
    """What the Status Changes report can and cannot show, in plain words, with this run's numbers."""
    r = result["reading"]
    sc, iss, wd = (
        r["status_changes"],
        r["issued_files_pend_to_active_with_two_dates"],
        r["never_issued_withdrawn_files_with_two_dates"],
    )
    gap_i, gap_w = iss["days_between_the_two_dates"], wd["days_between_the_two_dates"]
    b = result["number_order"]["status_report_first_dates_all_years"]["all"]
    fp = result["from_pending"]["statewide"]
    den = result["denials_in_status_changes"]
    basis = result["totals"]["statewide"]["filing_date_basis_by_outcome"][ISSUED]
    licence_only = ", ".join(
        f"{k} ({v['files']:,} files)"
        for k, v in fp.items()
        if k not in ("PEND to ACTIVE",)
        and v.get("with an Original Issue Date", 0) == v["files"]
        and v["files"] >= 20
    )
    return [
        (
            "How it works: the report lists a licence-type record on every date on which its status changed, and "
            "every listing shows the record's latest transition as of the day the page was fetched, not the change "
            f"made on the listed date. {sc['of_which_show_one_and_the_same_transition_on_every_date']:,} of "
            f"{sc['files_on_more_than_one_date']:,} files listed on more than one date show one and the same "
            "transition on every date; the rest are files with several licence-type records, each with its own "
            f"latest transition ({sc['files_with_one_licence_type_record_showing_different_transitions']:,} "
            "files have a single licence-type record that reads differently on different dates)."
        ),
        (
            "It can show, for an application that was never issued: the filing date (the record's first date) and "
            f"the withdrawal or denial date (its last date). {wd['files']:,} never-issued withdrawn files have a "
            f"record with exactly two dates, {gap_w.get('median')} days apart at the median (p10 {gap_w.get('p10')}, p90 "
            f"{gap_w.get('p90')}); their first dates run in file-number order (median error "
            f"{b.get('median_abs_error_days')} days, p90 {b.get('p90_abs_error_days')}, N={b.get('n'):,}), as "
            "filing dates must."
        ),
        (
            "It can show, for a licence that was issued: the issue date and the date of its latest later change "
            f"(cancelled, surrendered, revoked ...). Of {iss['files']:,} files with a PEND to ACTIVE record on "
            f"two dates, the first date is the Original Issue Date in {iss['first_date_is_the_original_issue_date']:,} "
            f"and is the date of the file's row in Issued Licenses in "
            f"{iss['issued_licences_date_equals_the_first_date']:,} (the second date is, and the first is not, in "
            f"{iss['issued_licences_date_equals_the_second_date_and_not_the_first']:,}). The second date follows "
            f"{gap_i.get('median')} day later at the median (p90 {gap_i.get('p90')}): it is the next business day "
            "and is not an event in any other report."
        ),
        (
            "It cannot show when an issued application was filed: an issued record carries no date before its "
            "Original Issue Date, so days from filing to issue cannot be read from this report. Here "
            f"{basis.get(BASIS_ESTIMATE, 0):,} issued files take a filing date estimated from the file number, "
            f"{basis.get(BASIS_STATUS_ISSUED, 0):,} take one from a withdrawn licence type on the same file and "
            f"{basis.get(BASIS_NONE, 0):,} have none."
        ),
        (
            "It cannot show a history: only the latest transition survives. An application withdrawn and later "
            "reinstated and issued reads as issued; a licence issued and later cancelled reads ACTIVE to CANCEL. "
            "Protests, hearings and conditions are not in it. An application still pending with no status change "
            "is not in it at all (it is in New Applications only), and nothing filed before the archive's first "
            "day has a filing date."
        ),
        (
            f"Denials do appear: {den['files_reading_pend_to_denied']:,} files read PEND to DENIED "
            f"({den['sf_county']} in San Francisco county). The weekly Legal Actions Filed and Finalized reports "
            "hold accusations against licensees only; no row is an application denial."
        ),
        (
            f"Not applications: {licence_only}. Every such record carries an Original Issue Date, so it is a "
            "licence that was pending for another reason (a transfer out, for example) and then ended."
        ),
    ]


def legal_reports(data: Path) -> dict:
    """The weekly Legal Actions reports, counted in files: a file counts once under each action, licence status
    and proceeding type it appears with. ``rows`` is kept as a description of the archive only."""
    out: dict = {}
    for kind in ("legal-actions-filed", "legal-actions-finalized"):
        weeks = sorted((data / "weekly" / kind).glob("*/rows.csv"))
        actions: dict[str, set[str]] = defaultdict(set)
        proceedings: dict[str, set[str]] = defaultdict(set)
        status: dict[str, set[str]] = defaultdict(set)
        files_seen: set[str] = set()
        n_rows = 0
        for wk in weeks:
            with open(wk, newline="") as fh:
                for r in csv.DictReader(fh):
                    n_rows += 1
                    num = r.get("file_number", "").strip()
                    files_seen.add(num)
                    actions[r.get("file_action", "").strip() or "(blank)"].add(num)
                    if "proceeding_proceeding_type" in r:
                        proceedings[
                            r["proceeding_proceeding_type"].strip() or "(blank)"
                        ].add(num)
                    status[r.get("file_license_status", "").strip() or "(blank)"].add(
                        num
                    )

        def by_files(d: dict[str, set[str]]) -> dict[str, int]:
            return dict(
                sorted(((k, len(v)) for k, v in d.items()), key=lambda kv: -kv[1])
            )

        out[kind] = {
            "weeks": len(weeks),
            "first_week": weeks[0].parent.name if weeks else None,
            "last_week": weeks[-1].parent.name if weeks else None,
            "rows": n_rows,
            "files": len(files_seen),
            "files_by_action": by_files(actions),
            "files_by_licence_status": by_files(status),
        }
        if proceedings:
            out[kind]["files_by_proceeding_type"] = by_files(proceedings)
    return out


def sf_by_type(sf_files: list[File]) -> tuple[list[dict], dict]:
    cells: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "counts": Counter(),
            "issue_known": [],
            "issue_any": [],
            "wd_known": [],
            "wd_any": [],
            "left_out": Counter(),
        }
    )
    for f in sf_files:
        if f.outcome not in (ISSUED, WITHDRAWN, DENIED, PENDING):
            continue
        c = cells[(f.table_type(), f.app_class())]
        c["counts"][f.outcome] += 1
        if f.outcome in (ISSUED, WITHDRAWN):
            pre = "issue" if f.outcome == ISSUED else "wd"
            if f.filed:
                days = (f.outcome_date - f.filed).days
                c[f"{pre}_any"].append(days)
                if f.filed_basis in KNOWN_BASES:
                    c[f"{pre}_known"].append(days)
            else:
                c["left_out"][f"{pre}: no filing date"] += 1
    order = {t: i for i, t in enumerate([*TABLE_TYPES, "other"])}
    cls_order = {"original": 0, "transfer": 1, "other": 2, "priority drawing entry": 3}
    rows = []
    for (t, cls), c in sorted(
        cells.items(), key=lambda kv: (order[kv[0][0]], cls_order[kv[0][1]])
    ):
        rows.append(
            {
                "type": t,
                "class": cls,
                **{o: c["counts"][o] for o in (ISSUED, WITHDRAWN, DENIED, PENDING)},
                "days_filing_to_issue_reported_filing_date": timing(c["issue_known"]),
                "days_filing_to_issue_reported_or_estimated": timing(c["issue_any"]),
                "days_filing_to_withdrawal_reported_filing_date": timing(c["wd_known"]),
                "days_filing_to_withdrawal_reported_or_estimated": timing(c["wd_any"]),
                "left_out_no_filing_date": dict(c["left_out"]),
            }
        )
    totals: dict = {}
    for cls in cls_order:
        sel = [c for (_, k), c in cells.items() if k == cls]
        if not sel:
            continue
        totals[cls] = {
            **{
                o: sum(c["counts"][o] for c in sel)
                for o in (ISSUED, WITHDRAWN, DENIED, PENDING)
            },
            "days_filing_to_issue_reported_filing_date": timing(
                [x for c in sel for x in c["issue_known"]]
            ),
            "days_filing_to_issue_reported_or_estimated": timing(
                [x for c in sel for x in c["issue_any"]]
            ),
            "days_filing_to_withdrawal_reported_filing_date": timing(
                [x for c in sel for x in c["wd_known"]]
            ),
            "days_filing_to_withdrawal_reported_or_estimated": timing(
                [x for c in sel for x in c["wd_any"]]
            ),
            "left_out_no_filing_date": dict(
                sum((c["left_out"] for c in sel), Counter())
            ),
        }
    return rows, totals


def coverage(sf_files: list[File]) -> dict:
    """Part 1 label-coverage columns for San Francisco ABC applications in the archive (2019 onwards)."""
    cols = [
        "total",
        "filed_date",
        "filed_date_reported",
        "filed_date_estimated",
        "decision_date",
        "approved",
        "withdrawn",
        "denied",
        "cancelled",
        "pending",
        "unknown",
        "premises_address",
        "complete",
        "complete_failures",
    ]
    cov: dict[str, Counter] = defaultdict(Counter)
    for f in sf_files:
        if not f.has_application():
            continue
        for key in (f"ABC {f.app_class()}", "ABC all"):
            c = cov[key]
            c["total"] += 1
            c["filed_date"] += bool(f.filed)
            c["filed_date_reported"] += bool(f.filed) and f.filed_basis in KNOWN_BASES
            c["filed_date_estimated"] += f.filed_basis == BASIS_ESTIMATE
            decided = f.outcome in (ISSUED, WITHDRAWN, DENIED, CANCELLED)
            c["decision_date"] += decided and bool(f.outcome_date)
            c["approved"] += f.outcome == ISSUED
            c["withdrawn"] += f.outcome == WITHDRAWN
            c["denied"] += f.outcome == DENIED
            c["cancelled"] += f.outcome == CANCELLED
            c["pending"] += f.outcome == PENDING
            c["unknown"] += f.outcome in (TEMP_ONLY, UNCLEAR)
            c["premises_address"] += bool(f.street)
            complete = (
                decided and bool(f.filed) and bool(f.outcome_date) and bool(f.street)
            )
            c["complete"] += complete
            c["complete_failures"] += complete and f.outcome in (
                WITHDRAWN,
                DENIED,
                CANCELLED,
            )
    return {k: {c: v[c] for c in cols} for k, v in sorted(cov.items())}


def totals(sel: list[File]) -> dict:
    apps = [f for f in sel if f.has_application()]
    return {
        "files": len(sel),
        "files_with_an_application_in_the_archive": len(apps),
        "by_outcome": dict(Counter(f.outcome for f in sel).most_common()),
        "by_class": dict(Counter(f.app_class() for f in apps).most_common()),
        "class_reported_or_inferred": dict(
            Counter(
                "inferred from Transfer-From/To"
                if f.cls_inferred
                else "reported action"
                for f in apps
            )
        ),
        "by_class_and_outcome": {
            cls: dict(
                Counter(f.outcome for f in apps if f.app_class() == cls).most_common()
            )
            for cls in ("original", "transfer", "other", "priority drawing entry")
        },
        "filing_date_basis": dict(Counter(f.filed_basis for f in apps).most_common()),
        "filing_date_basis_by_outcome": {
            o: dict(
                Counter(f.filed_basis for f in apps if f.outcome == o).most_common()
            )
            for o in (ISSUED, WITHDRAWN, DENIED, PENDING)
        },
        "pattern": dict(Counter(f.pattern for f in apps if f.pattern).most_common()),
    }


# ---------------------------------------------------------------------------- output files

HISTORY_COLS = [
    "file_number",
    "licence_types",
    "primary_type",
    "action",
    "original_or_transfer",
    "priority_drawing_entry",
    "business",
    "name_withheld",
    "premises_address",
    "city",
    "county",
    "district",
    "filing_date",
    "filing_date_basis",
    "outcome",
    "outcome_date",
    "outcome_date_basis",
    "original_issue_dates",
    "status_dates",
    "latest_transitions",
    "pattern",
    "events",
    "notes",
]


def history_row(f: File, names: bool) -> dict:
    origs = sorted({r.orig_issue for r in f.recs.values() if r.orig_issue})
    notes = list(f.notes)
    if f.filed_note and not f.filed:
        notes.append(f"filing date: {f.filed_note}")
    if f.priority:
        notes.append(f"priority drawing entry: {f.priority_reason}")
    return {
        "file_number": f.number,
        "licence_types": " ".join(sorted(f.types(), key=type_key)),
        "primary_type": f.primary_type(),
        "action": f.action,
        "original_or_transfer": f.class_label() if f.has_application() else "",
        "priority_drawing_entry": "yes" if f.priority else "no",
        "business": shown_name(f.business_name()) if names else "",
        "name_withheld": withheld_flag(f.business_name()) if names else "",
        "premises_address": f.premises(),
        "city": f.city,
        "county": f.county,
        "district": f.district,
        "filing_date": f.filed.isoformat() if f.filed else "",
        "filing_date_basis": f.filed_basis if f.has_application() else "",
        "outcome": f.outcome,
        "outcome_date": f.outcome_date.isoformat() if f.outcome_date else "",
        "outcome_date_basis": f.outcome_basis,
        "original_issue_dates": " ".join(d.isoformat() for d in origs),
        "status_dates": " ".join(d.isoformat() for d in f.status_dates()),
        "latest_transitions": "; ".join(
            sorted({f"type {r.type} {r.label()}" for r in f.recs.values()})
        ),
        "pattern": f.pattern,
        "events": "; ".join(f"{d.isoformat()} {what}" for d, what in f.events()),
        "notes": "; ".join(notes),
    }


def read_text(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as fh:
            return fh.read()
    return path.read_text()


def file_sort_key(f: File) -> tuple[int, str]:
    return (int(f.number), "") if f.number.isdigit() else (0, f.number)


def write_outputs(
    files: dict[str, File],
    result: dict,
    sample_rows: list[dict],
    out: Path,
    local_dir: Path,
) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    local_dir.mkdir(parents=True, exist_ok=True)
    written = []
    sf_files = sorted(
        (f for f in files.values() if f.county == SF_COUNTY), key=file_sort_key
    )
    path = out / "abc-sf-histories.csv"
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HISTORY_COLS)
        w.writeheader()
        for f in sf_files:
            w.writerow(history_row(f, names=True))
    written.append(path)
    path = local_dir / "abc-histories.csv.gz"
    with gzip.open(path, "wt", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HISTORY_COLS)
        w.writeheader()
        for f in sorted(files.values(), key=file_sort_key):
            w.writerow(history_row(f, names=False))
    written.append(path)
    wd_cols = [
        "business_name",
        "name_withheld",
        "premises_address",
        "licence_type",
        "all_licence_types",
        "original_or_transfer",
        "class_inferred",
        "priority_drawing_entry",
        "filing_date",
        "filing_date_basis",
        "withdrawal_date",
        "file_number",
    ]
    wd = [
        {
            "business_name": shown_name(f.business_name()),
            "name_withheld": withheld_flag(f.business_name()),
            "premises_address": ", ".join(
                p for p in (f.premises(), f"{f.city} {f.zip}".strip()) if p
            ),
            "licence_type": f.primary_type(),
            "all_licence_types": " ".join(sorted(f.app_types, key=type_key)),
            "original_or_transfer": f.cls,
            "class_inferred": "yes" if f.cls_inferred else "no",
            "priority_drawing_entry": "yes" if f.priority else "no",
            "filing_date": f.filed.isoformat() if f.filed else "",
            "filing_date_basis": f.filed_basis,
            "withdrawal_date": f.outcome_date.isoformat(),
            "file_number": f.number,
        }
        for f in sf_files
        if f.outcome == WITHDRAWN and f.outcome_date >= dt.date(2024, 11, 1)
    ]
    path = out / "abc-sf-withdrawn-since-2024-11.csv"
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=wd_cols)
        w.writeheader()
        w.writerows(
            sorted(
                wd, key=lambda r: (r["withdrawal_date"], r["file_number"]), reverse=True
            )
        )
    written.append(path)
    result["sf_withdrawn_since_2024_11"] = {
        "files": len(wd),
        "priority_drawing_entries": sum(
            r["priority_drawing_entry"] == "yes" for r in wd
        ),
        "by_class": dict(
            Counter(
                r["original_or_transfer"]
                for r in wd
                if r["priority_drawing_entry"] == "no"
            )
        ),
        "class_inferred": sum(r["class_inferred"] == "yes" for r in wd),
        "with_a_filing_date": sum(bool(r["filing_date"]) for r in wd),
        "name_withheld": sum(r["name_withheld"] == "yes" for r in wd),
    }
    if sample_rows:
        path = out / "abc-referral-file-match-sample.csv"
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(sample_rows[0]))
            w.writeheader()
            w.writerows(sample_rows)
        written.append(path)
    path = out / "abc-histories.json"
    path.write_text(json.dumps(result, indent=1, default=str) + "\n")
    written.append(path)
    return written


# ---------------------------------------------------------------------------- build


def build(
    data: Path,
    since: dt.date,
    use_db: bool,
    seed: int,
    with_abc_check: bool = True,
    export_rows: list[tuple] | None = None,
):
    files, meta = load(data, since)
    first_day = dt.date.fromisoformat(meta["first_day"])
    last_day = dt.date.fromisoformat(meta["last_day"])
    note = partial_year_note(first_day, last_day)
    result: dict = {"archive": meta}
    if use_db and export_rows is None:
        export_rows = fetch_export_pending()
    if export_rows is not None:
        result["citywide_export"] = add_export_pending(files, export_rows)
    for f in files.values():
        classify(f, first_day)
    order, n_start, order_info = number_order(files, first_day, dt.date(2025, 9, 1))
    order_info["status_report_first_dates_all_years"]["partial_year"] = note
    result["number_order"] = order_info
    est_info = assign_filing(files, order, n_start)
    priority_info = mark_priority(files)
    for f in files.values():
        f.pattern = pattern(f)
    result["estimated_filing"] = est_info
    priority_info["evidence_only_application_windows"]["partial_year"] = note
    result["priority_drawing"] = priority_info
    result["reading"] = reading_evidence(files, first_day)
    result["reading"]["new_applications"]["partial_year"] = note
    sf_files = [f for f in files.values() if f.county == SF_COUNTY]

    # (a) totals
    result["totals"] = {
        "statewide": totals(list(files.values())),
        "sf_county": totals(sf_files),
    }
    multi = [f for f in files.values() if len(f.transitions()) > 1]
    result["files_with_several_latest_transitions"] = {
        "files": len(multi),
        "by_outcome": dict(Counter(f.outcome for f in multi).most_common()),
    }
    apps = [
        f for f in files.values() if f.outcome in (ISSUED, WITHDRAWN, DENIED, PENDING)
    ]
    result["outside_the_simple_patterns"] = {
        "files_issued_withdrawn_denied_or_pending": len(apps),
        "simple": sum(f.pattern.startswith("simple") for f in apps),
        "one_date_only": sum(f.pattern.startswith("one date") for f in apps),
        "not_simple": sum(f.pattern.startswith("not simple") for f in apps),
    }

    # (b) check against ABC
    wl = workload(files)
    for fy, v in order_info["file_numbers_handed_out_by_fiscal_year"].items():
        wl.setdefault(fy, {}).setdefault("statewide", {})[HANDED_OUT] = v[
            "numbers_handed_out"
        ]
    result["workload_from_archive"] = label_partial_years(wl, first_day, last_day)
    result["workload_partial_years"] = (
        "The archive covers "
        f"{first_day.isoformat()} to {last_day.isoformat()}; a fiscal year it covers only in part is labelled "
        "'(partial: first day to last day)' in workload_from_archive and is not compared with ABC"
    )
    if with_abc_check:
        territory = office_territory(files)
        result["check_against_abc"] = check_against_abc(wl, territory)
        result["sf_office_territory"] = {
            "note": territory_note(territory),
            "by_fiscal_year": territory,
        }
        _, cross = abc_workload.load_summary()
        result["abc_licensing_table_cross_check"] = cross

    # (c) out of PEND, denials, legal actions
    result["from_pending"] = from_pending(files)
    result["never_issued_records_other_transitions"] = other_never_issued(files)
    denied = [f for f in files.values() if f.outcome == DENIED]
    denied_recs = [f for f in files.values() if f.recs_of(DENIED)]
    result["denials_in_status_changes"] = {
        "files_reading_pend_to_denied": len(denied_recs),
        "of_which_outcome_denied": len(denied),
        "of_which_later_issued_or_pending": len(denied_recs) - len(denied),
        "sf_county": sum(f.county == SF_COUNTY for f in denied),
        "sf_office": sum(f.district == SF_DISTRICT for f in denied),
        "by_year": dict(sorted(Counter(f.outcome_date.year for f in denied).items())),
        "by_year_sf_county": dict(
            sorted(
                Counter(
                    f.outcome_date.year for f in denied if f.county == SF_COUNTY
                ).items()
            )
        ),
        "by_class": dict(Counter(f.class_label() for f in denied).most_common()),
        "by_type": dict(Counter(f.primary_type() for f in denied).most_common()),
        "files_with_another_record_ending_in_denied": dict(
            Counter(
                lab
                for f in files.values()
                for lab in {
                    r.label()
                    for r in f.recs.values()
                    if r.to == "DENIED" and r.frm not in PENDING_STATES
                }
            )
        ),
        "partial_year": note,
    }
    result["legal_reports"] = legal_reports(data)
    result["reading"]["what_status_changes_can_and_cannot_show"] = reading_statement(
        result
    )

    # transfer inference: Transfer-From/To against the reported action, where a file has both
    chk = Counter()
    for f in files.values():
        if not f.cls_inferred and f.recs and f.has_application():
            chk[(f.cls, inferred_class(f))] += 1
    both = sum(chk.values())
    agree = sum(n for (a, b), n in chk.items() if a == b)
    orig_tr = sum(n for (a, _), n in chk.items() if a in ("original", "transfer"))
    agree_ot = sum(
        n for (a, b), n in chk.items() if a == b and a in ("original", "transfer")
    )
    result["transfer_inference_check"] = {
        "files_with_a_reported_action_and_a_status_record": both,
        "agree": agree,
        "share_agree": round(agree / both, 4) if both else None,
        "share_agree_where_reported_original_or_transfer": round(agree_ot / orig_tr, 4)
        if orig_tr
        else None,
        "table": {f"reported {a} / inferred {b}": n for (a, b), n in chk.most_common()},
    }

    # (d) filing dates and Planning referrals
    sample_rows: list[dict] = []
    if use_db:
        pinfo, match_rows = planning_match(files, first_day)
        pinfo["partial_year"] = note
        result["planning_match"] = pinfo
        sample_rows = sample_one_per_file(match_rows, seed)

    # (e) San Francisco by licence type and class
    rows_e, tot_e = sf_by_type(sf_files)
    result["sf_by_type"] = rows_e
    result["sf_by_class"] = tot_e

    # (g) coverage
    result["coverage_sf"] = coverage(sf_files)
    result["limits"] = limits(files, result)
    return files, result, sample_rows


def sample_one_per_file(match_rows: list[dict], seed: int, n: int = 20) -> list[dict]:
    """A random sample of referral-to-file matches for the hand check, one match per ABC file: the file's
    earliest referral, which is the one the date comparison uses."""
    by_file: dict[str, dict] = {}
    for r in sorted(
        match_rows, key=lambda r: (r["referral_filed"], r["planning_record"])
    ):
        by_file.setdefault(r["abc_file"], r)
    pool = sorted(by_file.values(), key=lambda r: r["planning_record"])
    return random.Random(seed).sample(pool, min(n, len(pool)))


def limits(files: dict[str, File], result: dict) -> list[str]:
    """What the numbers cannot settle, stated once, with this run's counts. Findings of the two verifiers that
    would have to be fitted to ABC's totals are recorded here and not applied."""
    where = result["priority_drawing"]["evidence_only_application_windows"][
        "where_the_entries_were_filed"
    ]
    gen_transfers = [
        f
        for f in files.values()
        if f.outcome == ISSUED
        and f.app_types & GENERAL_TYPES
        and not f.cls_inferred
        and f.cls == "transfer"
        and f.recs
    ]
    blank = sum(not any(r.transfer for r in f.recs.values()) for f in gen_transfers)
    reversed_wd = sum(
        any(r.frm in WITHDRAWN_STATES for r in f.recs.values()) for f in files.values()
    )
    wl = result["workload_from_archive"]
    late = ", ".join(
        f"{fy} {wl.get(fy, {}).get('statewide', {}).get(PRIORITY_LATE, 0)}"
        for fy in abc_workload.YEARS
    )
    return [
        (
            "Priority entries. The rule is: never issued, general type (21, 47, 48), original. It does not use "
            f"the filing date. {where.get('filed outside the application windows', 0):,} entries have a reported "
            "filing date outside every application window and are counted as entries all the same. A transfer "
            "whose status rows carry no Transfer-From/To would be counted as an entry: among issued "
            f"general-type files with a reported transfer action, {blank:,} of {len(gen_transfers):,} carry none. "
            f"{result['priority_drawing']['not_marked_pending_with_no_action_and_no_status_record']:,} pending "
            "general-type files are known from the citywide export alone, with no action and no status record: "
            "their class is unknown (shown as original, inferred) and they are not counted as entries."
        ),
        (
            "Withdrawals against ABC. Withdrawn files that are not priority entries come out a few per cent "
            "under ABC's Applications Withdrawn in most years. Likely reason, NOT applied: a drawing winner who "
            "withdraws later is an ordinary withdrawal to ABC. Priority entries withdrawn 12 or more months "
            f"after filing, by fiscal year of withdrawal: {late}. Moving them would need a cut-off chosen "
            "against ABC's totals, so they stay priority entries."
        ),
        (
            "FY2021-22 withdrawals stay well under ABC's figure with or without that adjustment. ABC restated "
            "that year's figure downward on a later page (abc_licensing_table_cross_check). Unexplained."
        ),
        (
            "Only a record's latest transition survives in Status Changes, so a withdrawal that was later "
            f"reversed is not counted as one: {reversed_wd:,} files now carry a record that reads from "
            "WTHDRN or WITHDRAWN to another status. This biases every year's withdrawals slightly low."
        ),
        (
            "Issued files against ABC. With temporary permits (type 30) left out, issued files are a few per "
            "cent under ABC's Permanent Licenses Issued in every year, and further under Applications "
            "Recommended for Approval. ABC's own issued figure is below its approved figure every year; ABC "
            "also counts a licence number once per duplicate number and issue date where a file counts once "
            "here. The rest is unexplained."
        ),
        (
            "Original and transfer investigations. ABC's pages do not say which actions go in which table. "
            "The grouping used (premises transfers with originals) comes from the second verifier's regression "
            "of ABC's per-office approved counts on action classes over 152 office-years (original table: ORI "
            "1.02, PRM 0.96, PER -0.04; transfer table: PER 1.05, FID/DPR/STK 0.96); it is not recomputed "
            "here. ICO is placed with originals on thin evidence; MBR, MBM, STM, EXC-only and blank actions "
            "are placed with transfers and are too rare to test. Transfer investigations stay under ABC's "
            "after regrouping: an approved transfer with no issue in the year is not visible in the reports."
        ),
        (
            "Offices. The district code on a file is the office that holds the premises today. FY2019-20 San "
            "Francisco office rows carry a territory note (sf_office_territory); no per-office figure is "
            "adjusted, and the handover date of San Mateo county is inferred, not stated by ABC. The same "
            "effect may explain other office-years (LA / Metro in FY2019-20); not tested."
        ),
        (
            "ABC's workload pages define none of the Licensing summary rows in words. What a row counts is "
            "inferred from table titles and from arithmetic between the tables."
        ),
        (
            "Filing dates. Status Changes never shows when an issued application was filed; the filing date "
            "of an issued file is estimated from its file number and labelled so. Nothing filed before the "
            "archive's first day has a filing date."
        ),
        (
            "Pending. A file is pending if New Applications lists it today or the citywide export shows it "
            "pending. The export is San Francisco only and a day older than the Status Changes page of the same "
            "date; a withdrawal or denial dated on or after the export date overrides it (citywide_export)."
        ),
        (
            "Business names. An individual licensee is recognised by ABC's 'SURNAME, GIVEN' form with no entity "
            "suffix; for those files no name is published, DBA included. A company's DBA can itself be a "
            "person's name (an eponymous restaurant or winery); it is the trade name of a company and is "
            "published."
        ),
        (
            "Part-years. "
            + result["workload_partial_years"]
            + ". Calendar-year tables carry a partial_year note."
        ),
    ]


def summary_keys(result: dict) -> dict:
    keep = (
        "archive",
        "totals",
        "outside_the_simple_patterns",
        "priority_drawing",
        "estimated_filing",
        "transfer_inference_check",
        "denials_in_status_changes",
        "coverage_sf",
        "sf_withdrawn_since_2024_11",
    )
    return {k: result[k] for k in keep if k in result}


# ---------------------------------------------------------------------------- self-test

ST_HEAD = (
    "License Number,Status Changed From/To,Type| Dup,Original Issue Date,Expir. Date,"
    "Primary Owner and Premises Addr.,Transfer-From/To,Conditions,Escrow,District Code,Geo Code,Prem Street,"
    "City,County,Zip Code"
)
ISS_HEAD = (
    "License Number,Status,Type| Dup,Expir. Date,Primary Owner and Premises Addr.,Action,Conditions,Escrow,"
    "District Code,Geo Code,Prem Street,City,County,Zip Code"
)


def self_test() -> None:
    """Synthetic rows through the real loader, classifier and writers."""
    person = "QUIXANO, ALONSO DE LA MANCHA"
    person2 = "PANZA, SANCHO"
    with tempfile.TemporaryDirectory() as tmp:
        data, out, local = Path(tmp) / "data", Path(tmp) / "out", Path(tmp) / "local"

        def put(date: str, report: str, head: str, rows: list[list[str]]) -> None:
            d = data / "daily" / date
            d.mkdir(parents=True, exist_ok=True)
            with open(d / f"{report}.csv", "a", newline="") as fh:
                w = csv.writer(fh)
                if fh.tell() == 0:
                    w.writerow(head.split(","))
                w.writerows(rows)

        def st(
            num: str,
            ft: str,
            typ: str,
            orig: str,
            name: str,
            street: str,
            transfer: str = "",
        ) -> list[str]:
            return [
                num,
                ft,
                typ,
                orig,
                "",
                name,
                transfer,
                "",
                "",
                "24",
                "3800",
                street,
                "SAN FRANCISCO",
                "38",
                "94110",
            ]

        def iss(
            num: str, status: str, typ: str, name: str, action: str, street: str
        ) -> list[str]:
            return [
                num,
                status,
                typ,
                "",
                name,
                action,
                "",
                "",
                "24",
                "3800",
                street,
                "SAN FRANCISCO",
                "38",
                "94110",
            ]

        def withdrawn(
            num: str,
            first: str,
            last: str,
            typ: str,
            name: str,
            street: str,
            transfer: str = "",
        ) -> None:
            row = st(num, "PEND | WITHDRAWN", typ, "", name, street, transfer)
            put(first, "status-changes", ST_HEAD, [row])
            put(last, "status-changes", ST_HEAD, [row])

        corp = "DBA: WINDMILL TAVERN | WINDMILL TAVERN LLC | 1 MAIN ST, | SAN FRANCISCO, CA 94110"
        # 900100: never issued, PEND to WITHDRAWN on two dates; the second date's row is repeated three times
        put(
            "2025-02-03",
            "status-changes",
            ST_HEAD,
            [st("900100", "PEND | WITHDRAWN", "41 | 0", "", corp, "1 MAIN ST")],
        )
        put(
            "2025-05-20",
            "status-changes",
            ST_HEAD,
            [st("900100", "PEND | WITHDRAWN", "41 | 0", "", corp, "1 MAIN ST")] * 3,
        )
        # Individual licensees. 900200: no DBA. 900201: the DBA is the same name. 900202: the DBA is
        # "<GIVEN> <SURNAME> WINES". 900203 and 900204: surnames that are also business words (CO, POST).
        # 900205: an individual whose DBA is an ordinary trade name, withheld all the same.
        tail = " | 2 MAIN ST, | SAN FRANCISCO, CA 94110"
        ind = f"{person}{tail}"
        ind_dba = f"DBA: ALONSO QUIXANO | {person}{tail}"
        ind_wines = f"DBA: SANCHO PANZA WINES | {person2}{tail}"
        ind_co = f"CO, THANH VAN{tail}"
        ind_post = f"POST, EMILY JANE{tail}"
        ind_trade = f"DBA: ROCINANTE LIQUORS | {person2}{tail}"
        withdrawn("900200", "2025-02-04", "2025-06-10", "20 | 0", ind, "2 MAIN ST")
        withdrawn("900201", "2025-02-05", "2025-06-11", "20 | 0", ind_dba, "3 MAIN ST")
        withdrawn(
            "900202", "2025-02-05", "2025-06-12", "20 | 0", ind_wines, "7 MAIN ST"
        )
        withdrawn("900203", "2025-02-05", "2025-06-12", "20 | 0", ind_co, "8 MAIN ST")
        withdrawn("900204", "2025-02-05", "2025-06-12", "20 | 0", ind_post, "9 MAIN ST")
        withdrawn(
            "900205",
            "2025-02-05",
            "2025-06-12",
            "20 | 0",
            ind_trade,
            "FERRY PLAZA PIER, C/O ROCINANTE CONCESSIONS",
        )
        # 900150: issued; today the licence is Canceled. Its first status date is the Original Issue Date,
        # which is also the date of its Issued Licenses row; the second is the next day (no event anywhere
        # else); the third is the cancellation. The first status date must NOT be taken as the filing date.
        for day in ("2025-06-02", "2025-06-03", "2026-03-09"):
            put(
                day,
                "status-changes",
                ST_HEAD,
                [
                    st(
                        "900150",
                        "ACTIVE | CANCEL",
                        "47 | 0",
                        "06/02/2025",
                        corp,
                        "4 MAIN ST",
                        "47-1/ 47-2",
                    )
                ],
            )
        put(
            "2025-06-02",
            "issued-licenses",
            ISS_HEAD,
            [iss("900150", "Canceled", "47 | 0", corp, "PER", "4 MAIN ST")] * 2,
        )
        # 900160: a temporary permit (type 30) only: not a licence issued
        put(
            "2025-06-03",
            "issued-licenses",
            ISS_HEAD,
            [iss("900160", "Expired", "30", corp, "PER", "5 MAIN ST")],
        )
        # dated neighbours by file number, so that 900150 can take an estimated filing date
        neighbours = {
            "2025-02-03": ("900070", "900080", "900090", "900095", "900110"),
            "2025-02-04": ("900120", "900130", "900140", "900170", "900180", "900190"),
            "2025-02-05": ("900210", "900220", "900230"),
        }
        for day, nums in neighbours.items():
            for num in nums:
                withdrawn(num, day, "2025-07-01", "41 | 0", corp, f"{num[3:]} MAIN ST")
        # The citywide export, dated 2025-06-20, shows three files pending.
        # 900300: Status Changes shows a withdrawal dated ON the export date: the status record is the later
        #         one, the file is withdrawn and its first status date is its filing date.
        # 900301: withdrawn the day BEFORE the export date and pending in the export: still pending.
        # 900302: in the export only.
        withdrawn("900300", "2025-02-06", "2025-06-20", "41 | 0", corp, "10 MAIN ST")
        withdrawn("900301", "2025-02-06", "2025-06-19", "41 | 0", corp, "11 MAIN ST")
        export_day = dt.date(2025, 6, 20)
        export_rows = [
            (num, "41", f"{n} MAIN ST", "SAN FRANCISCO", "94110", "WINDMILL TAVERN", "WINDMILL TAVERN  LLC", "24", export_day)
            for num, n in (("900300", 10), ("900301", 11), ("900302", 12))
        ]  # fmt: skip
        # Priority drawing. 900400: general type, no Transfer-From/To, never issued, the only such file filed
        # that day: an entry all the same (the rule has no 30-a-day test). 900401: same but a transfer.
        withdrawn("900400", "2025-02-07", "2025-06-25", "47 | 0", corp, "13 MAIN ST")
        withdrawn(
            "900401", "2025-02-07", "2025-06-25", "47 | 0", corp, "14 MAIN ST", "47-5"
        )

        # an old licence, so that the archive begins a year before the synthetic filings
        old = st("700000", "ACTIVE | CANCEL", "41 | 0", "03/04/2015", corp, "6 MAIN ST")
        put("2024-01-02", "status-changes", ST_HEAD, [old])

        files, result, sample = build(
            data,
            dt.date(2019, 1, 1),
            use_db=False,
            seed=1,
            with_abc_check=False,
            export_rows=export_rows,
        )
        written = write_outputs(files, result, sample, out, local)

        f = files["900100"]
        assert f.outcome == WITHDRAWN, f.outcome
        assert (f.filed, f.filed_basis) == (dt.date(2025, 2, 3), BASIS_STATUS), (
            f.filed,
            f.filed_basis,
        )
        assert f.outcome_date == dt.date(2025, 5, 20), f.outcome_date
        print(
            "ok  two-date PEND|WITHDRAWN file: filed = first date, withdrawn = last date"
        )

        assert result["archive"]["rows_repeated_on_one_date"] == {
            "status-changes": 2,
            "issued-licenses": 1,
        }
        assert len(f.recs) == 1 and next(iter(f.recs.values())).dates == {
            dt.date(2025, 2, 3),
            dt.date(2025, 5, 20),
        }
        wl = result["workload_from_archive"]
        # 900100, 900200 to 900205, 900300 and the transfer 900401; not the priority entry 900400
        assert wl["2024-25"]["statewide"]["withdrawn files (not priority)"] == 9, wl[
            "2024-25"
        ]
        print("ok  repeated rows on one date count once")

        g = files["900150"]
        orig = next(iter(g.recs.values())).orig_issue
        assert g.outcome == ISSUED and g.outcome_date == orig == dt.date(2025, 6, 2), (
            g.outcome,
            g.outcome_date,
            orig,
        )
        assert g.pattern == PATTERN_ISSUED_SIMPLE, g.pattern
        assert wl["2024-25"]["statewide"]["issued files (permanent licences)"] == 1
        assert wl["2024-25"]["sf_office"]["issued files, transfer"] == 1
        ev = result["reading"]["issued_licences"]
        assert (
            ev["of_which_an_issued_licences_date_is_the_original_issue_date"]
            == ev[
                "files_with_a_permanent_row_and_an_original_issue_date_in_the_archive_period"
            ]
            == 1
        ), ev
        print(
            "ok  a Canceled-status row in Issued Licenses counts as an issue, dated on the Original Issue Date"
        )

        assert g.filed_basis == BASIS_ESTIMATE and g.filed == dt.date(2025, 2, 4), (
            g.filed,
            g.filed_basis,
        )
        assert g.filed != dt.date(2025, 6, 2)
        print(
            "ok  an issued file's first status date (its Original Issue Date) is not its filing date"
        )

        assert files["700000"].outcome == NO_APPLICATION and not files["700000"].filed
        t = files["900160"]
        assert t.outcome == TEMP_ONLY, t.outcome
        assert (
            wl["2024-25"]["statewide"][
                "files in Issued Licenses, temporary permits included"
            ]
            == 2
        )
        assert (
            wl["2024-25"]["statewide"]["files with a temporary permit only (type 30)"]
            == 1
        )
        print("ok  a temporary permit (type 30) is not a licence issued")

        x = files["900300"]
        assert x.export_superseded() and x.outcome == WITHDRAWN, x.outcome
        assert x.outcome_date == export_day, x.outcome_date
        assert (x.filed, x.filed_basis) == (dt.date(2025, 2, 6), BASIS_STATUS), (
            x.filed,
            x.filed_basis,
        )
        assert files["900301"].outcome == PENDING and files["900302"].outcome == PENDING
        ce = result["citywide_export"]
        assert ce["those_files"] == ["900300"] and ce["export_date"] == "2025-06-20", ce
        print(
            "ok  export says pending, Status Changes shows a withdrawal dated on the export date: withdrawn"
        )

        e, tr = files["900400"], files["900401"]
        assert e.priority and e.app_class() == "priority drawing entry", (
            e.priority_reason
        )
        assert not tr.priority and tr.cls == "transfer", (tr.priority, tr.cls)
        assert not any(f.priority for f in files.values() if f.number != "900400")
        assert wl["2024-25"]["statewide"][PRIORITY_WITHDRAWN] == 1
        assert not result["priority_drawing"]["evidence_only_application_windows"][
            "window_days"
        ]
        print(
            "ok  a never-issued general-type original is a priority entry whatever day it was filed; "
            "a transfer is not"
        )

        assert investigation_class("ORI") == ORIGINAL_INVESTIGATION
        assert investigation_class("PRM") == ORIGINAL_INVESTIGATION
        assert investigation_class("PER/PRM") == ORIGINAL_INVESTIGATION
        assert investigation_class("ICO") == ORIGINAL_INVESTIGATION
        for act in ("PER", "FID", "DPR", "STK", "EXC/PER", ""):
            assert investigation_class(act) == TRANSFER_INVESTIGATION, act
        assert (
            action_class("PER/PRM") == "transfer" and action_class("PRM") == "transfer"
        )
        assert wl["2024-25"]["sf_office"][ISSUED_TRANSFER_INV] == 1
        print(
            "ok  ABC's investigation grouping: PRM with originals, PER with transfers; application class unchanged"
        )

        assert "2024-25" in wl and "2025-26" not in wl, list(wl)
        assert "2025-26 (partial: 2025-07-01 to 2026-03-09)" in wl, list(wl)
        labelled = label_partial_years(
            {"2018-19": {}, "2019-20": {}, "2026-27": {}},
            dt.date(2019, 1, 1),
            dt.date(2026, 11, 9),
        )
        assert list(labelled) == [
            "2018-19 (partial: 2019-01-01 to 2019-06-30)",
            "2019-20",
            "2026-27 (partial: 2026-07-01 to 2026-11-09)",
        ], list(labelled)
        assert fiscal_year(dt.date(2025, 6, 30)) == "2024-25"
        assert fiscal_year(dt.date(2025, 7, 1)) == "2025-26"
        note = result["denials_in_status_changes"]["partial_year"]
        assert "2024 is a part-year" in note and "2026 is a part-year" in note, note
        print("ok  part fiscal years and part calendar years are labelled")

        assert gap_pct(3, 5) is None and gap_pct(30, 5) is None
        assert gap_pct(12, 10) == 20.0
        assert abc_workload.gap(3, 5).startswith("3 against 5")
        assert abc_workload.gap(12, 10) == "+20.0%"
        assert (
            abc_workload.pages_agree({"pages": 1, "agree": None, "differences": {}})
            == "only one page shows this year"
        )
        assert (
            abc_workload.pages_agree({"pages": 3, "agree": True, "differences": {}})
            == "yes (3 pages)"
        )
        print(
            "ok  no percentage where a count is under 10; one page alone is not 'pages agree'"
        )

        for num in ("900200", "900201", "900202", "900203", "900204", "900205"):
            assert files[num].business_name() == NAME_WITHHELD, num
        for owner, dba in (
            ("CO, THANH VAN", ""),
            ("POST, EMILY JANE", ""),
            ("WINE, JAMES", ""),
            ("CHURCH, ROBERT LEE", "CHURCH STREET MARKET"),
            ("PANZA, SANCHO", "SANCHO PANZA WINES"),
            (
                "PANZA  SANCHO",
                "PANZA COMPANY",
            ),  # the export writes two spaces for the comma
            ("", "WINDMILL TAVERN"),  # licensee not known
        ):
            assert File("1", owner=owner, dba=dba).business_name() == NAME_WITHHELD, (
                owner,
                dba,
            )
        for owner, dba, shown in (
            ("WINDMILL TAVERN LLC", "WINDMILL TAVERN", "WINDMILL TAVERN"),
            ("WINDMILL TAVERN, LLC", "", "WINDMILL TAVERN, LLC"),
            ("POST HOTEL GROUP, INC.", "", "POST HOTEL GROUP, INC."),
            ("WINDMILL TAVERN  LLC", "", "WINDMILL TAVERN  LLC"),
            ("WINDMILL HOSPITALITY GROUP", "", "WINDMILL HOSPITALITY GROUP"),
        ):
            assert File("1", owner=owner, dba=dba).business_name() == shown, (
                owner,
                dba,
            )
        assert File("1", street="PIER 1, C/O X CONCESSIONS").premises() == "PIER 1"
        words = sorted(
            {w for w in re.findall(r"[A-Z]{4,}", f"{person} {person2}")}
            | {"THANH", "EMILY", "ROCINANTE"}
        )
        checked = 0
        for path in written:
            text = read_text(path).upper()
            for w in words:
                assert w not in text, (path.name, w)
            assert "C/O" not in text, path.name
            checked += 1
        assert (
            checked >= 4
            and NAME_WITHHELD
            not in (out / "abc-sf-withdrawn-since-2024-11.csv").read_text()
            and "\n,yes," in (out / "abc-sf-withdrawn-since-2024-11.csv").read_text()
        )
        assert "WINDMILL TAVERN" in (out / "abc-sf-histories.csv").read_text()
        assert "WINDMILL" not in read_text(local / "abc-histories.csv.gz")
        print(
            "ok  an individual's name never reaches a CSV, DBA included; company and DBA names of companies "
            "do, in the docs CSVs only; no care-of line"
        )

        matches = [
            {"abc_file": "1", "referral_filed": "2025-03-01", "planning_record": "B"},
            {"abc_file": "1", "referral_filed": "2025-02-01", "planning_record": "A"},
            {"abc_file": "2", "referral_filed": "2025-02-02", "planning_record": "C"},
        ]
        picked = sample_one_per_file(matches, seed=1)
        assert sorted(r["planning_record"] for r in picked) == ["A", "C"], picked
        zhuzh = File("1", owner="ZHUZH LLC", dba="ZHUZH BAR")
        assert (
            shared_name("ZHUZH BAR AUTHORIZES THE SALE OF BEER", zhuzh) == "ZHUZH BAR"
        )
        assert shared_name("ZHUZH", zhuzh) == "ZHUZH"
        assert shared_name("SOME OTHER PLACE", zhuzh) == ""
        print(
            "ok  the referral sample holds one match per file; only the name shared with ABC's DBA is published"
        )
    print("self-test passed")


# ---------------------------------------------------------------------------- main


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="docs/validation")
    p.add_argument("--since", default="2019-01-01")
    p.add_argument("--seed", type=int, default=20261110)
    p.add_argument("--no-db", action="store_true")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    files, result, sample_rows = build(
        DATA, dt.date.fromisoformat(args.since), not args.no_db, args.seed
    )
    written = write_outputs(files, result, sample_rows, Path(args.out), LOCAL_DIR)
    print(json.dumps(summary_keys(result), indent=1, default=str))
    for path in written:
        print("wrote", path)


if __name__ == "__main__":
    main()
