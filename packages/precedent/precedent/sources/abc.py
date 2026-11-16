"""California ABC (Department of Alcoholic Beverage Control) licenses in San Francisco County.

Access path (all public, no key; abc.ca.gov robots.txt only disallows /wp-admin/):

1. **Daily Data Export** — https://www.abc.ca.gov/wp-content/uploads/DailyExport-CSV.zip, linked from
   https://www.abc.ca.gov/licensing/licensing-reports/ and refreshed every business day (~7 MB zip, one CSV
   of ~130k license-type rows statewide). One row per (file number, license type, LIC/APP record) with type
   status (ACTIVE, PEND, SUREND, REVPEN, SUSPEN, R64B), original issue date, expiration, primary owner, DBA,
   premises address, county and census tract. This is the bulk backbone: one request for the whole county.
2. **Daily licensing reports** — ``/licensing/licensing-reports/{new-applications|status-changes|issued-licenses}/
   ?RPTTYPE={2|3|1}&RPTDATE=MM/DD/YYYY`` (statewide HTML tables, filtered here to County 38 = San Francisco).
   They add what the export lacks: the application date (= report date of the ``new-applications`` row),
   the application action (ORI original, PER person-to-person, PREM premises-to-premises transfer …),
   ABC condition codes, escrow, transfer from/to, and licenses that just went inactive (CANCELED, REVOKED …)
   and therefore dropped out of the export. Past report days never change, so they are cached forever.
3. **License Query System detail page** — ``/licensing/license-lookup/single-license/?RPTTYPE=12&LICENSE=<n>``
   (one page per license). Adds per-type status as ABC words it ("DEPARTMENT REVOKED", "PENDING", "CANCELED"),
   status date, transfers, condition text, the "Operating Restrictions exist" flag, disciplinary action /
   history (accusations → hearings), holds and notifications (where protests would surface). There is no
   bulk or JSON form of this; it is scraped politely and cached.

Rate limit: **at most 1 request every 2 seconds to abc.ca.gov** (``RateLimiter(0.5)``, shared by every request
in a run), with the ABC archive's User-Agent (``abc_user_agent``). Detail pages are cached under
``raw_dir/abc/_cache/detail/`` and re-fetched only when the export rows for that license change or the cache
is older than ``ABC_DETAIL_MAX_AGE_DAYS``; a full first pull of the county (~3.9k licenses) takes ~2.2 h, a
nightly refresh a few minutes. Geocoding uses DataSF EAS via ``precedent.geocode_sf`` (bulk ``address in (…)``
lookups, its own DataSF rate limit), cached in ``raw_dir/abc/_cache/geocode.json``.

Environment knobs:
  ``ABC_ZIP_CODES``            comma-separated premises ZIPs to keep (default: every row whose premises county is
                               SAN FRANCISCO), e.g. ``ABC_ZIP_CODES=94110,94103`` for a quick slice.
  ``ABC_DETAILS``              ``all`` (default) | ``none`` | N — how many LQS detail pages to (re)fetch this run.
  ``ABC_DETAIL_MAX_AGE_DAYS``  detail-page cache lifetime (default 30).
  ``ABC_REPORT_DAYS``          business days of daily reports to read when no ``--since`` is given (default 10).
  ``ABC_OFFLINE_EXPORT``       path to an export already on disk (ABC's zip, or the ABC archive's csv / csv.gz):
                               build the raw pages from files only (`fetch_offline`), with no request to
                               abc.ca.gov. Report events come from ``ABC_OFFLINE_REPORTS_DIR`` (the archive's
                               ``daily/`` folder), the ingest's report cache and earlier raw pages; detail pages
                               from the cache only. Geocoding still uses DataSF.

Raw output: ``raw_dir/abc/<stamp>-sf-licenses-pNNN.json`` (``write_raw`` envelope, ≤500 licenses per file), one
pre-joined, pre-geocoded record per license number, so ``parse()`` is a pure function of that file.
"""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import html as html_lib
import io
import json
import logging
import os
import re
import zipfile
from pathlib import Path
from typing import Any

import httpx

from precedent.models import Application, Outcome, SourceBatch, UseType
from precedent.sources.base import (
    RateLimiter,
    SourceSpec,
    abc_user_agent,
    fetched_at_from,
    raw_path,
    read_raw,
    write_raw,
)
from precedent.textparse import classify_use_types

log = logging.getLogger("precedent.sources.abc")

ABC_BASE = "https://www.abc.ca.gov"
EXPORT_URL = f"{ABC_BASE}/wp-content/uploads/DailyExport-CSV.zip"
REPORTS_HOME = f"{ABC_BASE}/licensing/licensing-reports/"
LOOKUP_URL = f"{ABC_BASE}/licensing/license-lookup/single-license/?RPTTYPE=12&LICENSE={{number}}"
REPORTS = {  # rpttype → (slug, short name)
    "2": ("new-applications", "new_application"),
    "3": ("status-changes", "status_change"),
    "1": ("issued-licenses", "issued"),
}
REQUESTS_PER_SECOND = 0.5  # one request every 2 s
SF_COUNTY_NAME = "SAN FRANCISCO"
SF_COUNTY_CODE = "38"
SF_ZIPS = [f"941{n:02d}" for n in range(2, 35)] + ["94158"]
LICENSES_PER_RAW_FILE = 500
GEOCODE_CACHE_VERSION = 2  # bump when precedent.geocode_sf normalisation changes

# https://www.abc.ca.gov/licensing/license-types/ (titles as ABC publishes them)
LICENSE_TYPES: dict[str, str] = {
    "01": "Beer Manufacturer",
    "02": "Winegrower",
    "03": "Brandy Manufacturer",
    "04": "Distilled Spirits Manufacturer",
    "05": "Distilled Spirits Manufacturer's Agent",
    "06": "Still",
    "07": "Rectifier",
    "08": "Wine Rectifier",
    "09": "Beer and Wine Importer",
    "10": "Beer and Wine Importer's General",
    "11": "Brandy Importer",
    "12": "Distilled Spirits Importer",
    "13": "Distilled Spirits Importer's General",
    "14": "Public Warehouse",
    "15": "Customs Broker",
    "16": "Wine Broker",
    "17": "Beer and Wine Wholesaler",
    "18": "Distilled Spirits Wholesaler",
    "19": "Industrial Alcohol Dealer",
    "20": "Off-Sale Beer & Wine",
    "21": "Off-Sale General",
    "22": "Wine Blender",
    "23": "Small Beer Manufacturer",
    "24": "Distilled Spirits Rectifier's General",
    "25": "California Brandy Wholesaler",
    "26": "Out-of-State Beer Manufacturer's Certificate",
    "27": "California Winegrower's Agent",
    "28": "Out-of-State Distilled Spirits Shipper's Certificate",
    "29": "Wine Grape Grower's Storage",
    "31": "Special Daily (beer, wine, distilled spirits)",
    "34": "Daily Beer and Wine",
    "37": "Daily General",
    "40": "On-Sale Beer",
    "41": "On-Sale Beer & Wine - Eating Place",
    "42": "On-Sale Beer & Wine - Public Premises",
    "43": "On-Sale Beer and Wine Train",
    "44": "On-Sale Beer Fishing Party Boat",
    "45": "On-Sale Beer and Wine Boat",
    "46": "On-Sale Beer and Wine Airplane",
    "47": "On-Sale General - Eating Place",
    "48": "On-Sale General - Public Premises",
    "49": "On-Sale General - Seasonal",
    "50": "On-Sale General Club",
    "51": "Club",
    "52": "Veteran's Club",
    "53": "On-Sale General Train",
    "54": "On-Sale General Boat",
    "55": "On-Sale General Airplane",
    "56": "On-Sale General Vessel 1000 Tons",
    "57": "Special On-Sale General",
    "58": "Caterer's Permit",
    "59": "On-Sale Beer and Wine - Seasonal",
    "60": "On-Sale Beer - Seasonal",
    "61": "On-Sale Beer - Public Premises",
    "62": "On-Sale General Dockside, 7000 tons",
    "63": "On-Sale Special Beer and Wine Hospital",
    "64": "Special On-Sale General for Nonprofit Theater Company",
    "65": "Special On-Sale Beer and Wine Symphony",
    "66": "Controlled Access Cabinet Permits",
    "67": "Bed and Breakfast Inn",
    "68": "Portable Bar License",
    "69": "Special On-Sale Beer and Wine Theater",
    "70": "On-Sale General - Restrictive Service",
    "71": "Special On-Sale General for a For-Profit Theater within the City and County of San Francisco",
    "72": "Special On-Sale General for a For-Profit Theater within the county of Napa",
    "73": "Special Non-Profit Sales License",
    "74": "Craft Distiller",
    "75": "Brewpub-Restaurant",
    "76": "On-Sale General Maritime Museum Association",
    "77": "Event Permit",
    "78": "On-Sale General for Wine, Food and Art Cultural Museum, and Educational Center",
    "79": "Certified Farmers' Market Permit",
    "80": "Bed and Breakfast Inn - General",
    "81": "Wine Sales Event Permit",
    "82": "Wine Direct Shipper Permit",
    "83": "General On-Sale License to Caterer",
    "84": "Certified Farmers' Market Beer Sales Permit",
    "85": "Limited Off-Sale - Wine License",
    "86": "Instructional Tasting License",
    "87": "Special On-Sale General License for Specified Census Tracts in the City/County of San Francisco",
    "88": "Special On-Sale General License for a For-Profit Cemetery with Specified Characteristics",
    "90": "On-Sale General - Music Venue",
    "91": "Beer Manufacturer's Caterer's Permit",
    "93": "Estate Tasting Event Permit",
    "94": "Craft Distillers Direct Shipper Permit",
    "99": "On-Sale General for Special Use",
}

# License type → memo use types. Only types whose privileges imply the use; everything else relies on the DBA text.
TYPE_USE_TYPES: dict[str, list[UseType]] = {
    "41": ["restaurant"],
    "47": ["restaurant"],
    "57": ["restaurant"],
    "75": ["restaurant", "bar"],
    "40": ["bar"],
    "42": ["bar"],
    "48": ["bar"],
    "61": ["bar"],
    "20": ["retail_alcohol"],
    "21": ["retail_alcohol"],
    "85": ["retail_alcohol"],
    "66": ["hotel"],
    "67": ["hotel"],
    "70": ["hotel"],
    "80": ["hotel"],
    "64": ["live_entertainment"],
    "65": ["live_entertainment"],
    "69": ["live_entertainment"],
    "71": ["live_entertainment"],
    "90": ["live_entertainment", "bar"],
}
# Order used to pick the "headline" type when a license number carries several (47 + 58 + 66 …).
_TYPE_PRIORITY = [
    "48",
    "47",
    "42",
    "41",
    "75",
    "90",
    "61",
    "40",
    "57",
    "70",
    "87",
    "21",
    "20",
    "23",
    "85",
    "64",
    "71",
]

_ISSUED_STATUSES = {
    "ACTIVE",
    "ISSUED",
    "R64B",
    "ISSUE AND HOLD",
    "SUSPEN",
    "SUSPEND",
    "SUSPENDED",
    "ISSUPD",
    "INDEFINITE SUSPENSION",
    "REVPEN",
    "REVP",
    "RNST",
    "NREN",
    "NON-RENEWAL",
    "SUREND",
    "SURRENDERED",
    "R65",
    "CAN",
    "CANCELED",
    "CANCELLED",
    "REV",
    "REVOKED",
    "A/REV",
    "S/REV",
    "SLMS",
    "AUTREV",
    "DEPARTMENT REVOKED",
    "AUTO REVOKED",
    "INACT",
    "INACTIVE",
    "EXPIRED",
    "RULE 64B",
    "REV PENDING",
}
_PENDING_STATUSES = {"PEND", "PENDING", "APPLIED"}
_DENIED_STATUSES = {"DENY", "DENIED"}
_WITHDRAWN_STATUSES = {"WDRL", "WITHDRAWN", "WITHDRAWL"}
_PROTEST_RE = re.compile(r"\bPROTEST", re.I)
_HEARING_RE = re.compile(r"\b(HEARING|ACCUSATION)\b", re.I)


# ---------------------------------------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------------------------------------
def lookup_url(license_number: str) -> str:
    return LOOKUP_URL.format(number=license_number)


def strip_zeros(file_number: str) -> str:
    return (file_number or "").strip().lstrip("0") or "0"


def type_label(code: str) -> str:
    code = code.zfill(2)
    desc = LICENSE_TYPES.get(code)
    return f"Type {code} – {desc}" if desc else f"Type {code}"


def parse_abc_date(value: str | None) -> dt.date | None:
    """'14-MAR-1968' (export / LQS) or '10/19/2026' (reports) → date."""
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%d-%b-%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt).date()  # %b matching is case-insensitive
        except ValueError:
            continue
    return None


def _env_zips() -> list[str] | None:
    raw = os.environ.get("ABC_ZIP_CODES", "").strip()
    if not raw:
        return None
    return [z.strip()[:5] for z in raw.split(",") if z.strip()]


def _clean(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _html_lines(page: str) -> list[str]:
    page = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", page, flags=re.S | re.I)
    page = re.sub(r"<[^>]+>", "\n", page)
    page = html_lib.unescape(page)
    return [ln.strip() for ln in page.splitlines() if ln.strip()]


# ---------------------------------------------------------------------------------------------------------
# 1. Daily export
# ---------------------------------------------------------------------------------------------------------
def read_export(zip_bytes: bytes) -> tuple[str, list[dict[str, str]]]:
    """Return (the export's 'Updated …' banner, rows with stripped keys/values)."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        text = zf.read(name).decode("utf-8-sig", errors="replace")
    buf = io.StringIO(text, newline="")
    banner = buf.readline().strip().strip('"')
    rows = [{(k or "").strip(): _clean(v) for k, v in row.items()} for row in csv.DictReader(buf)]
    return banner, rows


def filter_sf(rows: list[dict[str, str]], zips: list[str] | None) -> list[dict[str, str]]:
    out = [r for r in rows if r.get("Prem County", "").upper() == SF_COUNTY_NAME]
    if zips:
        out = [r for r in out if r.get("Prem Zip", "")[:5] in zips]
    return out


def export_type_row(r: dict[str, str]) -> dict[str, Any]:
    return {
        "type": r.get("License Type", "").zfill(2),
        "lic_or_app": r.get("Lic or App", ""),
        "status": r.get("Type Status", ""),
        "orig_iss_date": r.get("Type Orig Iss Date", ""),
        "expir_date": r.get("Expir Date", ""),
        "fee_codes": r.get("Fee Codes", ""),
        "dup_count": r.get("Dup Counts", ""),
        "master": r.get("Master Ind", ""),
        "term_months": r.get("Term in # of Months", ""),
    }


# ---------------------------------------------------------------------------------------------------------
# 2. Daily licensing reports
# ---------------------------------------------------------------------------------------------------------
def report_url(rpttype: str, day: dt.date) -> str:
    slug = REPORTS[rpttype][0]
    return (
        f"{ABC_BASE}/licensing/licensing-reports/{slug}/?RPTTYPE={rpttype}&RPTDATE={day.strftime('%m/%d/%Y')}"
    )


def parse_report_html(page: str) -> tuple[dt.date | None, list[dict[str, str]]]:
    """Parse one daily report page (table#license_report) into (report date, rows keyed by column header)."""
    m = re.search(r"Report Date:\s*</strong>\s*([^<]+)", page)
    report_date = None
    if m:
        try:
            report_date = dt.datetime.strptime(m.group(1).strip(), "%A, %B %d, %Y").date()
        except ValueError:
            report_date = None
    start = page.find('id="license_report"')
    if start < 0:
        return report_date, []
    end = page.find("</table>", start)
    table = page[start:end]
    head, _, body = table.partition("<tbody>")
    headers = [
        _clean(html_lib.unescape(re.sub(r"<[^>]+>", " ", h)))
        for h in re.findall(r"<th[^>]*>(.*?)</th>", head, re.S)
    ]
    rows: list[dict[str, str]] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        cells = [
            _clean(html_lib.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<br\s*/?>", " | ", c, flags=re.I))))
            for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)
        ]
        if len(cells) >= len(headers) - 1 and cells:
            rows.append(dict(zip(headers, cells, strict=False)))
    return report_date, rows


def report_event(kind: str, report_date: dt.date | None, row: dict[str, str]) -> dict[str, Any]:
    type_dup = row.get("Type| Dup", "")
    code, _, dup = type_dup.partition("|")
    owner_block = [p.strip() for p in row.get("Primary Owner and Premises Addr.", "").split("|")]
    dba = owner_block[0][4:].strip() if owner_block and owner_block[0].startswith("DBA:") else None
    owner = (
        owner_block[1]
        if dba is not None and len(owner_block) > 1
        else (owner_block[0] if owner_block else "")
    )
    status = row.get("Status", "")
    status_from = status_to = None
    if "Status Changed From/To" in row:
        parts = [p.strip() for p in row["Status Changed From/To"].split("|")]
        padded = [*parts, "", ""]
        status_from, status_to = padded[0], padded[1]
        status = status_to or status
    return {
        "report": kind,
        "report_date": report_date.isoformat() if report_date else None,
        "license_number": strip_zeros(row.get("License Number", "")),
        "type": code.strip().zfill(2),
        "dup": dup.strip(),
        "status": status,
        "status_from": status_from,
        "status_to": status_to,
        "action": row.get("Action") or None,
        "conditions": row.get("Conditions") or None,
        "escrow": row.get("Escrow") or None,
        "transfer": row.get("Transfer-From/To") or None,
        "orig_iss_date": row.get("Original Issue Date") or None,
        "expir_date": row.get("Expir. Date") or None,
        "dba": dba,
        "owner": owner or None,
        "prem_street": row.get("Prem Street") or None,
        "city": row.get("City") or None,
        "county": row.get("County") or None,
        "zip": (row.get("Zip Code") or "")[:5] or None,
    }


def business_days(start: dt.date, end: dt.date) -> list[dt.date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)
    return days


# ---------------------------------------------------------------------------------------------------------
# 3. LQS single-license detail page
# ---------------------------------------------------------------------------------------------------------
_TYPE_HEADER_RE = re.compile(r"^(\d{2})\s+-\s+(.+)$")
_TYPE_KEYS = {
    "License Type Status:": "status",
    "Status Date:": "status_date",
    "Term:": "term",
    "Original Issue Date:": "orig_issue_date",
    "Expiration Date*:": "expiration_date",
    "Master:": "master",
    "Duplicate:": "duplicate",
    "Fee Code:": "fee_code",
}
_SECTIONS = [
    "Operating Restrictions:",
    "Disciplinary Action:",
    "Disciplinary History:",
    "Holds:",
    "Escrows:",
    "Notifications:",
]
_NONE_PREFIXES = ("No ", "*Operating Restrictions exist")


def parse_detail_html(page: str) -> dict[str, Any]:
    """Structured view of a License Details page. Officer / stockholder names are deliberately not kept."""
    lines = _html_lines(page)
    if any(ln.startswith("No license found") for ln in lines):
        return {"found": False}
    try:
        start = next(i for i, ln in enumerate(lines) if ln == "License Number:")
    except StopIteration:
        return {"found": False}
    end = next((i for i, ln in enumerate(lines) if ln.startswith("For definition of codes")), len(lines))
    body = lines[start:end]

    def after(label: str) -> str | None:
        for i, ln in enumerate(body):
            if ln == label and i + 1 < len(body):
                return body[i + 1]
        return None

    out: dict[str, Any] = {
        "found": True,
        "license_number": after("License Number:"),
        "primary_owner": after("Primary Owner:"),
        "office": after("Office of Application:"),
        "business_name": after("Business Name"),
        "business_address": _clean(after("Business Address")),
        "census_tract": after("Census Tract:"),
    }
    # License types block
    try:
        t0 = next(i for i, ln in enumerate(body) if ln == "License Types")
    except StopIteration:
        t0 = len(body)
    t_end = next((i for i, ln in enumerate(body) if ln in _SECTIONS), len(body))
    types: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    mode: str | None = None
    keys = set(_TYPE_KEYS)
    i = t0 + 1
    while i < t_end:
        ln = body[i]
        nxt = body[i + 1] if i + 1 < t_end else ""
        header = _TYPE_HEADER_RE.match(ln)
        if header and nxt == "License Type Status:":
            cur = {
                "code": header.group(1),
                "description": header.group(2).strip(),
                "transfers": [],
                "conditions": [],
            }
            types.append(cur)
            mode = None
        elif cur is not None and ln in keys:
            value = (
                ""
                if (nxt in keys or nxt in ("Transfers:", "Conditions:") or _TYPE_HEADER_RE.match(nxt))
                else nxt
            )
            cur[_TYPE_KEYS[ln]] = value
            if value:
                i += 1
            mode = None
        elif cur is not None and ln == "Transfers:":
            mode = "transfers"
        elif cur is not None and ln == "Conditions:":
            mode = "conditions"
        elif cur is not None and mode:
            cur[mode].append(ln)
        i += 1
    out["license_types"] = types

    def section(label: str) -> list[str]:
        try:
            s = body.index(label)
        except ValueError:
            return []
        e = next((j for j in range(s + 1, len(body)) if body[j] in _SECTIONS), len(body))
        return body[s + 1 : e]

    restrictions = section("Operating Restrictions:")
    out["operating_restrictions"] = any(ln.startswith("*Operating Restrictions exist") for ln in restrictions)
    out["operating_restrictions_text"] = [
        ln
        for ln in restrictions
        if not ln.startswith(_NONE_PREFIXES)
        and not ln.startswith(("For more information", "Guidelines for Access", "."))
    ]
    out["disciplinary_action"] = _kv_records(section("Disciplinary Action:"), "Reg. Number:")
    out["disciplinary_history"] = _kv_records(section("Disciplinary History:"), "Reg. Number:")
    out["holds"] = _kv_records(section("Holds:"), "Hold Type:")
    out["escrows"] = [ln for ln in section("Escrows:") if not ln.startswith("No ")]
    out["notifications"] = [ln for ln in section("Notifications:") if not ln.startswith("No ")]
    return out


def _kv_records(lines: list[str], first_key: str) -> list[dict[str, str]]:
    """['Hold Type:', 'FORM 220', 'Hold Date:', '15-OCT-2026'] → [{'hold_type': 'FORM 220', 'hold_date': …}]."""
    records: list[dict[str, str]] = []
    cur: dict[str, str] | None = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("No ") and cur is None:
            i += 1
            continue
        m = re.match(r"^([A-Za-z.# ]+):\s*(.*)$", ln)
        if m:
            key = re.sub(r"[^a-z0-9]+", "_", m.group(1).lower()).strip("_")
            value = m.group(2).strip()
            if not value and i + 1 < len(lines) and not re.match(r"^[A-Za-z.# ]+:", lines[i + 1]):
                value = lines[i + 1]
                i += 1
            if ln.startswith(first_key) or cur is None:
                cur = {}
                records.append(cur)
            cur[key] = value
        elif cur is not None:
            cur.setdefault("text", "")
            cur["text"] = (cur["text"] + " " + ln).strip()
        i += 1
    return records


# ---------------------------------------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------------------------------------
class _AbcClient:
    def __init__(self, client: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self.client = client
        self.limiter = limiter
        self.requests = 0

    async def get(self, url: str) -> httpx.Response:
        await self.limiter.wait()
        self.requests += 1
        resp = await self.client.get(url, headers={"User-Agent": abc_user_agent()})
        resp.raise_for_status()
        return resp


def _signature(record: dict[str, Any]) -> str:
    basis = json.dumps(
        [record.get("types"), record.get("dba_name"), record.get("prem_addr_1")], sort_keys=True
    )
    return hashlib.sha1(basis.encode()).hexdigest()[:16]


def _detail_limit() -> int | None:
    raw = os.environ.get("ABC_DETAILS", "all").strip().lower()
    if raw in ("", "all"):
        return None
    if raw in ("none", "0", "off", "false"):
        return 0
    return max(0, int(raw))


def _records_from_export(sf_rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """One record per license number from the export's SF rows (one row per license type / LIC-APP record)."""
    records: dict[str, dict[str, Any]] = {}
    for r in sf_rows:
        num = strip_zeros(r.get("File Number", ""))
        rec = records.setdefault(
            num,
            {
                "license_number": num,
                "file_number": r.get("File Number", ""),
                "in_export": True,
                "primary_name": r.get("Primary Name", ""),
                "dba_name": r.get("DBA Name", ""),
                "prem_addr_1": r.get("Prem Addr 1", ""),
                "prem_addr_2": r.get("Prem Addr 2", ""),
                "prem_city": r.get("Prem City", ""),
                "prem_zip": r.get("Prem Zip", ""),
                "census_tract": r.get("Prem Census Tract #", ""),
                "district": r.get("District", ""),
                "types": [],
                "events": [],
            },
        )
        rec["types"].append(export_type_row(r))
        for key, col in (("primary_name", "Primary Name"), ("dba_name", "DBA Name")):
            if not rec[key] and r.get(col):
                rec[key] = r[col]
    return records


def _add_report_rows(
    records: dict[str, dict[str, Any]],
    kind: str,
    report_date: dt.date | None,
    rows: list[dict[str, str]],
    zips: list[str] | None,
) -> None:
    """Add one daily report's SF rows to the records as events (a license only in the reports gets a record)."""
    for row in rows:
        if row.get("County") != SF_COUNTY_CODE:
            continue
        ev = report_event(kind, report_date, row)
        if zips and ev["zip"] not in zips:
            continue
        if ev["license_number"] not in records:
            records[ev["license_number"]] = {
                "license_number": ev["license_number"],
                "file_number": ev["license_number"].zfill(8),
                "in_export": False,
                "primary_name": ev["owner"] or "",
                "dba_name": ev["dba"] or "",
                "prem_addr_1": ev["prem_street"] or "",
                "prem_addr_2": "",
                "prem_city": ev["city"] or "",
                "prem_zip": ev["zip"] or "",
                "census_tract": "",
                "district": "24",
                "types": [],
                "events": [],
            }
        rec = records[ev["license_number"]]
        if ev not in rec["events"]:
            rec["events"].append(ev)


def _detail_signature(rec: dict[str, Any]) -> str:
    return (
        _signature(rec)
        + "|"
        + hashlib.sha1(json.dumps(rec["events"], sort_keys=True).encode()).hexdigest()[:8]
    )


async def _geocode_records(
    client: httpx.AsyncClient, cache: Path, records: dict[str, dict[str, Any]]
) -> None:
    """Geocode premises addresses (DataSF EAS bulk + fallback, never abc.ca.gov), cached across runs."""
    from precedent.geocode_sf import SFGeocoder

    geo_cache_path = cache / "geocode.json"
    geo_cache: dict[str, Any] = json.loads(geo_cache_path.read_text()) if geo_cache_path.exists() else {}
    if geo_cache.get("_version") != GEOCODE_CACHE_VERSION:  # address normalisation changed → re-geocode
        geo_cache = {"_version": GEOCODE_CACHE_VERSION}
    addr_for: dict[str, str] = {}
    for num, rec in records.items():
        if rec["prem_addr_1"]:
            addr_for[num] = f"{rec['prem_addr_1']}, SAN FRANCISCO, CA {rec['prem_zip'][:5]}".strip()
    missing = sorted({a for a in addr_for.values() if a not in geo_cache})
    if missing:
        geocoder = SFGeocoder(client)
        try:
            results = await geocoder.geocode_many(missing)
        finally:
            await geocoder.close()
        for addr, res in results.items():
            geo_cache[addr] = (
                None
                if res is None
                else {
                    "lat": res.lat,
                    "lng": res.lng,
                    "normalized_address": res.normalized_address,
                    "parcel": res.parcel,
                    "zip_code": res.zip_code,
                    "source": res.source,
                    "source_url": res.source_url,
                    "confidence": res.confidence,
                }
            )
        geo_cache_path.parent.mkdir(parents=True, exist_ok=True)
        geo_cache_path.write_text(json.dumps(geo_cache))
    for num, rec in records.items():
        rec["geocode"] = geo_cache.get(addr_for.get(num, ""))
        rec.pop("_sig", None)


def _write_pages(raw_dir: Path, records: dict[str, dict[str, Any]], meta: dict[str, Any]) -> list[Path]:
    nums = sorted(records, key=lambda n: int(n) if n.isdigit() else 0)
    paths: list[Path] = []
    for page_no, i in enumerate(range(0, max(len(nums), 1), LICENSES_PER_RAW_FILE)):
        chunk = [records[n] for n in nums[i : i + LICENSES_PER_RAW_FILE]]
        path = raw_path(raw_dir, "abc", f"sf-licenses-p{page_no:03d}")
        write_raw(path, {"licenses": chunk}, {**meta, "count": len(chunk)})
        paths.append(path)
    return paths


def _report_window(since: dt.date | None, today: dt.date) -> dt.date:
    if since is not None:
        return max(since, today - dt.timedelta(days=180))
    n_days = int(os.environ.get("ABC_REPORT_DAYS", "10"))
    return today - dt.timedelta(days=int(n_days * 7 / 5) + 2)


async def fetch(client: httpx.AsyncClient, raw_dir: Path, since: dt.date | None) -> list[Path]:
    if os.environ.get("ABC_OFFLINE_EXPORT", "").strip():
        return await fetch_offline(client, raw_dir, since)

    zips = _env_zips()
    abc = _AbcClient(client, RateLimiter(REQUESTS_PER_SECOND))
    cache = raw_dir / "abc" / "_cache"
    for sub in ("export", "reports", "detail"):
        (cache / sub).mkdir(parents=True, exist_ok=True)
    today = dt.datetime.now(dt.UTC).date()

    # 1. export
    resp = await abc.get(EXPORT_URL)
    export_stamp = resp.headers.get("last-modified", "")
    export_file = cache / "export" / f"DailyExport-CSV-{today.isoformat()}.zip"
    export_file.write_bytes(resp.content)
    banner, all_rows = read_export(resp.content)
    sf_rows = filter_sf(all_rows, zips)
    del all_rows
    records = _records_from_export(sf_rows)
    log.info(
        "abc export: %d SF rows → %d license numbers (zips=%s)", len(sf_rows), len(records), zips or "all"
    )

    # 2. daily reports
    start = _report_window(since, today)
    for day in business_days(start, today):
        for rpttype, (_slug, kind) in REPORTS.items():
            cached = cache / "reports" / f"{kind}-{day.isoformat()}.html"
            if cached.exists() and day < today:
                page = cached.read_text()
            else:
                try:
                    page = (await abc.get(report_url(rpttype, day))).text
                except httpx.HTTPError as exc:
                    log.warning("abc report %s %s failed: %s", kind, day, exc)
                    continue
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_text(page)
            report_date, rows = parse_report_html(page)
            _add_report_rows(records, kind, report_date or day, rows, zips)

    # 3. LQS detail pages (cached; refetched on change or age)
    limit = _detail_limit()
    max_age = dt.timedelta(days=int(os.environ.get("ABC_DETAIL_MAX_AGE_DAYS", "30")))
    now = dt.datetime.now(dt.UTC)
    todo: list[tuple[int, str, str]] = []
    for num, rec in records.items():
        sig = _detail_signature(rec)
        rec["_sig"] = sig
        meta_path = cache / "detail" / f"{num}.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            age = now - dt.datetime.fromisoformat(meta["fetched_at"])
            rec["detail"], rec["detail_fetched_at"] = meta["detail"], meta["fetched_at"]
            if meta.get("signature") == sig and age < max_age:
                continue
            todo.append((1, meta["fetched_at"], num))  # stale / changed
        else:
            todo.append((0, "", num))  # never fetched first
    todo.sort()
    if limit is not None:
        todo = todo[:limit]
    log.info(
        "abc details: %d to fetch at %.1f req/s (~%d min)",
        len(todo),
        REQUESTS_PER_SECOND,
        round(len(todo) / REQUESTS_PER_SECOND / 60),
    )
    for _, _, num in todo:
        rec = records[num]
        try:
            page = (await abc.get(lookup_url(num))).text
        except httpx.HTTPError as exc:
            log.warning("abc detail %s failed: %s", num, exc)
            continue
        detail = parse_detail_html(page)
        fetched = dt.datetime.now(dt.UTC).isoformat()
        (cache / "detail").mkdir(parents=True, exist_ok=True)  # survive a cleaned-out cache dir mid-run
        (cache / "detail" / f"{num}.html").write_text(page)
        (cache / "detail" / f"{num}.json").write_text(
            json.dumps({"fetched_at": fetched, "signature": rec["_sig"], "detail": detail})
        )
        rec["detail"], rec["detail_fetched_at"] = detail, fetched

    # 4. geocode premises addresses (EAS bulk + fallback), cached across runs
    await _geocode_records(client, cache, records)

    # 5. raw pages
    return _write_pages(
        raw_dir,
        records,
        {
            "url": EXPORT_URL,
            "export_banner": banner,
            "export_last_modified": export_stamp,
            "reports_home": REPORTS_HOME,
            "report_window": [start.isoformat(), today.isoformat()],
            "zip_filter": zips,
            "abc_requests": abc.requests,
            "rate_limit_per_second": REQUESTS_PER_SECOND,
        },
    )


# ---------------------------------------------------------------------------------------------------------
# Offline build: the same raw pages from files already on disk, with no request to abc.ca.gov
# ---------------------------------------------------------------------------------------------------------
def read_export_file(path: Path) -> tuple[str, list[dict[str, str]]]:
    """Rows of a Daily Data Export saved on disk: ABC's own zip, or a CSV / CSV.gz (the ABC archive's copy has
    no title line; ABC's file has one before the header). Returns (title line or '', rows)."""
    data = path.read_bytes()
    if data[:2] == b"PK":
        return read_export(data)
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    text = data.decode("utf-8-sig", errors="replace")
    buf = io.StringIO(text, newline="")
    first = buf.readline()
    banner = ""
    if first.lstrip('"').startswith("License Type"):
        buf = io.StringIO(text, newline="")
    else:
        banner = first.strip().strip('"')
    rows = [{(k or "").strip(): _clean(v) for k, v in row.items()} for row in csv.DictReader(buf)]
    return banner, rows


def _previous_events(raw_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Report events already gathered for each license in earlier raw pages (newest page wins per license)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for path in sorted((raw_dir / "abc").glob("*-sf-licenses-p*.json")):
        try:
            _, data = read_raw(path)
        except (OSError, ValueError, KeyError):
            continue
        for rec in data.get("licenses", []):
            if rec.get("events"):
                out[str(rec.get("license_number"))] = rec["events"]
    return out


def _archived_report(reports_dir: Path, kind: str, day: dt.date) -> str | None:
    """A daily report page saved by the ABC archive (daily/<date>/<slug>.html.gz), or the ingest's own cache."""
    slug = next(s for s, k in REPORTS.values() if k == kind)
    archived = reports_dir / day.isoformat() / f"{slug}.html.gz"
    if archived.exists():
        return gzip.decompress(archived.read_bytes()).decode("utf-8", errors="replace")
    return None


async def fetch_offline(client: httpx.AsyncClient, raw_dir: Path, since: dt.date | None) -> list[Path]:
    """Build the raw pages from files on disk only: the export at ``ABC_OFFLINE_EXPORT`` (zip, csv or csv.gz),
    daily reports saved by the ABC archive under ``ABC_OFFLINE_REPORTS_DIR`` (its ``daily/`` folder) and the
    ingest's own report cache, the events of earlier raw pages, and the cached detail pages, whatever their age.
    No request goes to abc.ca.gov; geocoding uses DataSF EAS as in `fetch`. ``ABC_ZIP_CODES`` applies."""
    export_path = Path(os.environ["ABC_OFFLINE_EXPORT"])  # a full path ("~" is not expanded)
    reports_env = os.environ.get("ABC_OFFLINE_REPORTS_DIR", "").strip()
    reports_dir = Path(reports_env) if reports_env else None
    zips = _env_zips()
    cache = raw_dir / "abc" / "_cache"
    today = dt.datetime.now(dt.UTC).date()

    banner, all_rows = read_export_file(export_path)
    sf_rows = filter_sf(all_rows, zips)
    del all_rows
    records = _records_from_export(sf_rows)
    log.info(
        "abc offline export %s: %d SF rows → %d license numbers (zips=%s)",
        export_path.name,
        len(sf_rows),
        len(records),
        zips or "all",
    )

    for num, events in _previous_events(raw_dir).items():
        if num in records:
            for ev in events:
                if ev not in records[num]["events"]:
                    records[num]["events"].append(ev)

    start = _report_window(since, today)
    read_days = 0
    for day in business_days(start, today):
        for _rpttype, (_slug, kind) in REPORTS.items():
            page = _archived_report(reports_dir, kind, day) if reports_dir is not None else None
            cached = cache / "reports" / f"{kind}-{day.isoformat()}.html"
            if not page and cached.exists():
                page = cached.read_text()
            if not page:
                continue
            read_days += 1
            report_date, rows = parse_report_html(page)
            # rows of a license that left the export (canceled, revoked …) add a record from the report alone
            _add_report_rows(records, kind, report_date or day, rows, zips)

    with_detail = 0
    for num, rec in records.items():
        meta_path = cache / "detail" / f"{num}.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            rec["detail"], rec["detail_fetched_at"] = meta["detail"], meta["fetched_at"]
            with_detail += 1
    log.info(
        "abc offline: %d report pages read, %d licenses with a cached detail page (not refetched)",
        read_days,
        with_detail,
    )

    await _geocode_records(client, cache, records)
    return _write_pages(
        raw_dir,
        records,
        {
            "url": f"file:{export_path.name}",
            "offline": True,
            "export_banner": banner,
            "reports_home": REPORTS_HOME,
            "report_window": [start.isoformat(), today.isoformat()],
            "zip_filter": zips,
            "abc_requests": 0,
            "rate_limit_per_second": REQUESTS_PER_SECOND,
        },
    )


# ---------------------------------------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------------------------------------
def outcome_for(status: str, lic_or_app: str = "", issued: bool = False) -> Outcome:
    s = (status or "").strip().upper().split(" - ")[0].strip()  # "SUSPENDED - (Start Date: …)" → "SUSPENDED"
    if s in _DENIED_STATUSES:
        return "denied"
    if s in _WITHDRAWN_STATUSES:
        return "withdrawn"
    if s in _PENDING_STATUSES:
        return "pending"
    if (
        s in _ISSUED_STATUSES
        or s.endswith("REVOKED")
        or s.startswith(("SURREND", "CANCEL", "SUSPEN", "EXPIRED", "REV PEND"))
    ):
        # It was granted at some point; the current status string says what happened since.
        return "approved"
    if s in ("VOID", "VOIDED"):
        return "unknown"
    return "unknown"


def _transfer_entries(detail: dict[str, Any]) -> list[str]:
    """LQS 'Transfers:' lines → ['From License Number: 41-62507 (Transferred On: 09-NOV-2010)', …]."""
    out: list[str] = []
    for t in detail.get("license_types", []):
        cur: str | None = None
        for ln in t.get("transfers", []):
            if ln.endswith("License Number:"):
                if cur:
                    out.append(cur)
                cur = ln
            elif cur is not None and ln.startswith("Transferred On"):
                cur = f"{cur} ({ln})"
            elif cur is not None:
                cur = f"{cur} {ln}"
        if cur:
            out.append(cur)
    return list(dict.fromkeys(out))


def _primary_type(types: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not types:
        return None

    def key(t: dict[str, Any]) -> tuple[int, int, int, int]:
        code = t.get("type", "")
        return (
            0 if t.get("lic_or_app") == "LIC" else 1,
            0 if t.get("status") in ("ACTIVE", "PEND") else 1,
            0 if t.get("master") == "Y" else 1,
            _TYPE_PRIORITY.index(code) if code in _TYPE_PRIORITY else len(_TYPE_PRIORITY),
        )

    return sorted(types, key=key)[0]


def _parse_license(rec: dict[str, Any], fetched_at: dt.datetime, raw_ref: str) -> Application:
    num = rec["license_number"]
    detail = rec.get("detail") or {}
    if not detail.get("found"):
        detail = {}
    events: list[dict[str, Any]] = sorted(rec.get("events") or [], key=lambda e: e.get("report_date") or "")
    types: list[dict[str, Any]] = list(rec.get("types") or [])
    if not types and events:  # license known only from reports (e.g. just canceled → gone from export)
        last = events[-1]
        types = [
            {
                "type": last["type"],
                "lic_or_app": "LIC" if last.get("orig_iss_date") else "APP",
                "status": last["status"],
                "orig_iss_date": last.get("orig_iss_date") or "",
                "expir_date": last.get("expir_date") or "",
                "master": "Y",
                "dup_count": last.get("dup") or "",
            }
        ]
    primary = _primary_type(types) or {"type": "", "lic_or_app": "", "status": ""}
    code = str(primary.get("type", "")).zfill(2) if primary.get("type") else ""
    detail_type = next((t for t in detail.get("license_types", []) if t.get("code") == code), None)

    status = str(primary.get("status") or "")
    status_source = "export" if rec.get("in_export") else "report"
    if detail_type and detail_type.get("status"):
        status, status_source = detail_type["status"], "lqs"
    elif not rec.get("in_export") and events:
        status = events[-1].get("status") or status

    orig = parse_abc_date(primary.get("orig_iss_date")) or parse_abc_date(
        (detail_type or {}).get("orig_issue_date")
    )
    issued = orig is not None or primary.get("lic_or_app") == "LIC"
    outcome = outcome_for(status, str(primary.get("lic_or_app") or ""), issued)
    # Export "APP / ACTIVE" rows without a LIC row and without an LQS page: spot checks against the LQS show
    # these are issued (often long-standing) licenses, so they map to "approved" but are flagged in extra.
    app_only_active = not issued and primary.get("lic_or_app") == "APP" and status.upper() == "ACTIVE"

    new_apps = [e for e in events if e["report"] == "new_application"]
    # Application date: an original application's report date; a transfer application (PER/PREM …) only
    # dates the record when nothing has been issued yet (otherwise it is kept in extra.transfer_filed_at).
    originals = [e for e in new_apps if str(e.get("action") or "").split("/")[0] in ("ORI", "DOR", "ICO", "")]
    first_app = originals[0] if originals else (new_apps[0] if new_apps and outcome == "pending" else None)
    filed_at = parse_abc_date(first_app["report_date"]) if first_app else None
    transfer_apps = [e for e in new_apps if e not in originals]
    if filed_at is None and outcome == "pending" and detail_type:
        filed_at = parse_abc_date(detail_type.get("status_date"))
    decided_at: dt.date | None = orig
    if outcome in ("denied", "withdrawn"):
        decided_at = parse_abc_date((detail_type or {}).get("status_date")) or (
            parse_abc_date(events[-1]["report_date"]) if events else None
        )
    if outcome == "pending":
        decided_at = None

    conditions: list[str] = []
    for t in detail.get("license_types", []):
        for c in t.get("conditions", []):
            if c not in conditions:
                conditions.append(c)
    if detail.get("operating_restrictions"):
        conditions.append("ABC operating restrictions (conditions) on file for this license")
    conditions.extend(x for x in detail.get("operating_restrictions_text", []) if x not in conditions)
    condition_codes = sorted(
        {c.strip() for e in events for c in (e.get("conditions") or "").split(",") if c.strip()}
    )
    if condition_codes and not conditions:
        conditions.append(f"ABC report condition code(s): {', '.join(condition_codes)}")

    hold_types = [h.get("hold_type", "") for h in detail.get("holds", [])]
    text_blobs = (
        hold_types
        + list(detail.get("notifications", []))
        + [h.get("text", "") for h in detail.get("holds", [])]
    )
    protest = any(_PROTEST_RE.search(t or "") for t in text_blobs)
    active_disc = detail.get("disciplinary_action", [])
    hearing = bool(active_disc) or any(_HEARING_RE.search(t or "") for t in text_blobs)
    opposition: bool | None = (protest or hearing) if detail else None

    dba = rec.get("dba_name") or detail.get("business_name") or ""
    owner = rec.get("primary_name") or detail.get("primary_owner") or ""
    use_types: list[UseType] = []
    for t in types:
        for u in TYPE_USE_TYPES.get(str(t.get("type", "")).zfill(2), []):
            if u not in use_types:
                use_types.append(u)
    for u in classify_use_types(dba):
        if u not in use_types:
            use_types.append(u)

    geo = rec.get("geocode") or {}
    zip5 = (rec.get("prem_zip") or "")[:5]
    address = (
        ", ".join(p for p in [rec.get("prem_addr_1") or "", "SAN FRANCISCO", f"CA {zip5}".strip()] if p)
        if rec.get("prem_addr_1")
        else None
    )
    actions = sorted({e["action"] for e in events if e.get("action")})
    transfers = _transfer_entries(detail)
    label = type_label(code) if code else "ABC license"
    expiration = parse_abc_date(primary.get("expir_date")) or parse_abc_date(
        (detail_type or {}).get("expiration_date")
    )

    extra: dict[str, Any] = {
        "owner": owner or None,
        "dba": dba or None,
        "expiration": expiration.isoformat() if expiration else None,
        "license_types": [
            {
                "type": t.get("type"),
                "label": type_label(str(t.get("type", ""))),
                "lic_or_app": t.get("lic_or_app"),
                "status": t.get("status"),
                "orig_iss_date": (d.isoformat() if (d := parse_abc_date(t.get("orig_iss_date"))) else None),
                "master": t.get("master"),
                "dup_count": t.get("dup_count"),
            }
            for t in types
        ],
        "record_kind": primary.get("lic_or_app"),
        "status_unverified": True if app_only_active else None,
        "status_source": status_source,
        "in_daily_export": bool(rec.get("in_export")),
        "census_tract": rec.get("census_tract") or detail.get("census_tract"),
        "premises_addr_2": rec.get("prem_addr_2") or None,
        "application_actions": actions,
        "transfer_pending": any(
            a.split("/")[0] in ("PER", "PREM", "PRM", "DBL", "STK", "EXC") for a in actions
        ),
        "transfers": transfers,
        "transfer_filed_at": transfer_apps[0]["report_date"] if transfer_apps else None,
        "condition_codes": condition_codes,
        "operating_restrictions": detail.get("operating_restrictions") if detail else None,
        "holds": hold_types,
        "disciplinary_action": active_disc,
        "disciplinary_history": detail.get("disciplinary_history", []),
        "protest_indicator": protest if detail else None,
        "hearing_indicator": hearing if detail else None,
        "events": [
            {
                k: e.get(k)
                for k in (
                    "report",
                    "report_date",
                    "type",
                    "status",
                    "status_from",
                    "status_to",
                    "action",
                    "conditions",
                    "transfer",
                )
            }
            for e in events
        ],
        "detail_fetched_at": rec.get("detail_fetched_at"),
        "geocode_source": geo.get("source"),
        "geocode_confidence": geo.get("confidence"),
        "geocode_source_url": geo.get("source_url"),
    }
    return Application(
        id=f"abc:{num}",
        source="abc",
        source_id=num,
        source_url=lookup_url(num),
        fetched_at=fetched_at,
        raw_ref=raw_ref,
        kind="abc_license",
        permit_type=label,
        use_types=use_types,
        description=f"{dba or owner or 'ABC licensee'} — {label} ({status or 'status unknown'})",
        address=address,
        lat=geo.get("lat"),
        lng=geo.get("lng"),
        parcel=geo.get("parcel"),
        status=status,
        outcome=outcome,
        filed_at=filed_at,
        decided_at=decided_at,
        conditions=conditions[:12],
        opposition_noted=opposition,
        extraction_confidence="high",
        license_type=code or None,
        extra={k: v for k, v in extra.items() if v not in (None, [], "")},
    )


def parse(path: Path) -> SourceBatch:
    meta, data = read_raw(path)
    fetched_at = fetched_at_from(meta)
    apps: list[Application] = []
    for rec in data.get("licenses", []):
        try:
            apps.append(_parse_license(rec, fetched_at, str(path)))
        except Exception:  # one bad record must not sink the page
            log.exception("abc: could not parse license %s", rec.get("license_number"))
    return SourceBatch(applications=apps)


SOURCE = SourceSpec(
    name="abc",
    description=(
        "California ABC alcohol licenses in SF County: daily CSV export + daily licensing reports + LQS detail "
        "pages (rate limit: 1 request / 2 s to abc.ca.gov; ABC_ZIP_CODES / ABC_DETAILS limit a run)"
    ),
    fetch=fetch,
    parse=parse,
    rate_limit_per_second=REQUESTS_PER_SECOND,
    source_home=REPORTS_HOME,
)

__all__ = [
    "SOURCE",
    "fetch",
    "fetch_offline",
    "lookup_url",
    "outcome_for",
    "parse",
    "parse_detail_html",
    "parse_report_html",
    "read_export_file",
    "type_label",
]
