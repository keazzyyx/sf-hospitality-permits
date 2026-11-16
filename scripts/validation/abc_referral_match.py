"""Match Planning's dated ABC referrals to today's ABC licences by address (local database only).

Planning reviews most ABC applications as a "Miscellaneous Permit" referral, which carries a filing date the ABC
export lacks. This script matches each referral filed since 2019 to the rows of the citywide Daily Data Export
(table ``abc_export_sf``) at the same street address and reports how many never appear there.

    apps/api/.venv/bin/python scripts/validation/abc_referral_match.py [--sample 20] [--csv out.csv]

Match levels, strictest last:
  near  no licence at the exact address, but one on the same street within 12 street numbers whose business name
        or licence type matches the referral (ABC and Planning often write a corner or multi-door premises
        differently: 549 Geary vs 553-561 Geary), or a licence anywhere in the city under the referral's business name
  A     any licence or application at the address today
  B     A, and the address holds a licence type the referral names (when it names one)
  C     B, and that licence was first issued on or after the referral's filing date (minus 30 days) or is pending

A hand check of 20 "no licence at the address" referrals (docs/validation/step3-abc-and-sources.md) found that
half had an active licence written differently, which is why the address rules below are loose.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import random
import re
from collections import Counter, defaultdict

import psycopg

LOCAL = os.environ.get(
    "LOCAL_DATABASE_URL", "postgresql://postgres@localhost:55433/sfhp_local"
)
ABC_RX = r"(\mabc\M|liquor|alcohol|type[- ]?(20|21|40|41|42|47|48)\M|beer and wine|on-sale|off-sale|pcn|public convenience)"
SUFFIX = {
    "STREET": "ST", "AVENUE": "AVE", "AV": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR", "ROAD": "RD", "PLACE": "PL",
    "COURT": "CT", "LANE": "LN", "TERRACE": "TER", "HIGHWAY": "HWY", "PLAZA": "PLZ", "ALLEY": "ALY", "WAY": "WAY",
    "SQUARE": "SQ", "CIRCLE": "CIR", "PARKWAY": "PKWY",
}  # fmt: skip
UNIT_RE = re.compile(
    r"(?:\b(?:STE|SUITE|UNIT|APT|SPACE|SPC|RM|ROOM|FL|FLOOR|BLDG|BASEMENT|BSMT|INCL|AND)\b|#|&|,).*$"
)
DIRECTION = {"SOUTH": "S", "NORTH": "N", "EAST": "E", "WEST": "W"}
SUFFIXES = set(SUFFIX.values())
DBA_RE = re.compile(
    r"\bd\.?\s?b\.?\s?a\.?\s*:?\s*[\"“'(]*([A-Za-z0-9&' .\-]{3,40})", re.IGNORECASE
)
NUM_RE = re.compile(r"^(\d+)(?:\s*(?:-|&|AND|/)\s*(\d+))?\s+(.*)$")
TYPE_RE = re.compile(
    r"\b(?:type|types|license)\s*#?\s*((?:\d{2}\b[\s,&/and]*)+)", re.IGNORECASE
)


def norm_street(rest: str) -> str:
    rest = UNIT_RE.sub("", rest.upper()).strip()
    words = [w for w in re.sub(r"[^A-Z0-9 ]", " ", rest).split() if w]
    words = [SUFFIX.get(w, w) for w in words]
    words = [
        DIRECTION.get(w, w) if i == 0 and len(words) > 1 else w
        for i, w in enumerate(words)
    ]
    words = [re.sub(r"^0+(\d)", r"\1", w) for w in words]  # 03RD -> 3RD
    if (
        len(words) > 1 and words[-1] in SUFFIXES
    ):  # "BROADWAY" vs "BROADWAY ST", "LA PLAYA" vs "LA PLAYA ST"
        words = words[:-1]
    return " ".join(words)


def norm_name(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", (name or "").upper()).strip()


def referral_dba(description: str) -> str:
    m = DBA_RE.search(description or "")
    if not m:
        return ""
    name = norm_name(
        re.split(
            r"\s+(?:is|at|in|for|permitted|as|with)\b", m.group(1), flags=re.IGNORECASE
        )[0]
    )
    return name if len(name) >= 4 else ""


def keys(address: str | None) -> set[tuple[int, str]]:
    """(street number, normalised street) pairs for an address; ranges like 731-33 or 1007 - 1017 expand."""
    if not address:
        return set()
    a = re.sub(r"\s+\d{5}(?:-\d{4})?\s*$", "", address.strip().upper())
    m = NUM_RE.match(a)
    if not m:
        return set()
    lo, hi_raw, rest = int(m.group(1)), m.group(2), m.group(3)
    street = norm_street(rest)
    if not street:
        return set()
    nums = {lo}
    if hi_raw:
        hi = int(hi_raw)
        if hi < lo and len(hi_raw) < len(m.group(1)):  # 731-33 means 731-733
            hi = int(m.group(1)[: -len(hi_raw)] + hi_raw)
        if lo <= hi <= lo + 60:
            nums = set(range(lo, hi + 1))
    return {(n, street) for n in nums}


def named_types(description: str) -> set[str]:
    out: set[str] = set()
    for m in TYPE_RE.finditer(description or ""):
        out |= set(re.findall(r"\d{2}", m.group(1)))
    return out


def parse_abc_date(s: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(s.strip(), "%d-%b-%Y").date()
    except ValueError:
        return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=0)
    p.add_argument("--csv")
    p.add_argument("--seed", type=int, default=20261110)
    args = p.parse_args()
    with psycopg.connect(LOCAL) as conn:
        labelled = conn.execute(
            "select to_regclass('record_labels') is not null"
        ).fetchone()[0]
        labelled = (
            labelled
            and conn.execute("select count(*) > 20000 from record_labels").fetchone()[0]
        )
        if labelled:
            referral_sql = f"""select a.id, a.source_id, a.address, a.description, a.filed_at, a.decided_at, a.outcome, a.status
                 from applications a join record_labels r using (id)
                 where a.source='datasf_planning' and r.record_kind='agency_referral' and r.premises
                   and a.description ~* '{ABC_RX}' and a.filed_at >= '2019-01-01'"""
        else:
            referral_sql = f"""select a.id, a.source_id, a.address, a.description, a.filed_at, a.decided_at, a.outcome, a.status
                 from applications a
                 where a.source='datasf_planning' and a.extra->>'record_type'='MIS'
                   and a.description ~* '{ABC_RX}' and a.filed_at >= '2019-01-01'"""
        referrals = conn.execute(referral_sql).fetchall()
        export = conn.execute(
            "select prem_addr_1, ltrim(license_type,'0'), lic_or_app, type_status, orig_iss_date, ltrim(file_number,'0'), dba_name from abc_export_sf"
        ).fetchall()
    index: dict[tuple[int, str], list[tuple]] = defaultdict(list)
    by_street: dict[str, list[tuple[int, tuple]]] = defaultdict(list)
    for row in export:
        for k in keys(row[0]):
            index[k].append(row)
            by_street[k[1]].append((k[0], row))

    by_year: dict[int, Counter] = defaultdict(Counter)
    out_rows = []
    for id_, record, address, desc, filed, decided, outcome, status in referrals:
        ks = keys(address)
        hits = [h for k in ks for h in index.get(k, [])]
        types = named_types(desc)
        level = "none"
        if not ks:
            level = "no_address"
        elif not hits:
            dba = referral_dba(desc)
            near = [
                row
                for n0, street in ks
                for n1, row in by_street.get(street, [])
                if abs(n1 - n0) <= 12 and n1 % 2 == n0 % 2  # same side of the street
            ]
            near = [
                h for h in near
                if (dba and dba in norm_name(h[6])) or (types and h[1].zfill(2) in types and (
                    h[3] == "PEND" or ((d := parse_abc_date(h[4])) and d >= filed - dt.timedelta(days=30))))
            ]  # fmt: skip
            by_name = [
                h
                for h in export
                if dba and len(dba) >= 6 and norm_name(h[6]).startswith(dba)
            ]
            if near or by_name:
                level = "near"
                hits = near or by_name
        elif hits:
            level = "A"
            typed = [h for h in hits if not types or h[1].zfill(2) in types]
            if typed:
                level = "B"
                cutoff = filed - dt.timedelta(days=30)
                if any(
                    h[3] == "PEND" or ((d := parse_abc_date(h[4])) and d >= cutoff)
                    for h in typed
                ):
                    level = "C"
        y = filed.year
        by_year[y]["referrals"] += 1
        by_year[y][level] += 1
        by_year[y][
            f"planning_{'approved' if outcome.startswith('approved') else outcome}"
        ] += 1
        out_rows.append(
            {
                "record": record, "filed": filed.isoformat(), "planning_outcome": outcome, "address": address,
                "types_named": " ".join(sorted(types)), "match": level,
                "licences_at_address": "; ".join(sorted({f"{h[5]}/{h[1]}/{h[3]}/{h[4]}" for h in hits}))[:300],
                "description": re.sub(r"\s+", " ", desc or "")[:200],
            }
        )  # fmt: skip

    print(
        f"referral definition: {'record_labels (agency referral, premises, ABC text)' if labelled else 'MIS record with ABC text'}"
    )
    print(
        "| filed | referrals | no licence found | near or by name | address only (A) | + type (B) | + issued after filing or pending (C) | no usable address |"
    )
    print("|---|---|---|---|---|---|---|---|")
    tot: Counter = Counter()
    for y in sorted(by_year):
        c = by_year[y]
        tot.update(c)
        print(
            f"| {y} | {c['referrals']} | {c['none']} | {c['near']} | {c['A']} | {c['B']} | {c['C']} | {c['no_address']} |"
        )
    print(
        f"| total | {tot['referrals']} | {tot['none']} | {tot['near']} | {tot['A']} | {tot['B']} | {tot['C']} | {tot['no_address']} |"
    )
    matched = tot["near"] + tot["A"] + tot["B"] + tot["C"]
    print(
        f"\nmatched to a licence at the address today: {matched} of {tot['referrals']} ({matched / tot['referrals']:.0%}); never appear: {tot['none']}"
    )

    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out_rows[0]))
            w.writeheader()
            w.writerows(out_rows)
    if args.sample:
        pool = [
            r for r in out_rows
            if r["match"] == "none" and r["planning_outcome"].startswith("approved") and r["filed"] < "2026-01-01"
        ]  # fmt: skip
        print(
            f"\nnon-matches approved by Planning, filed 2019-2025: {len(pool)}; sample of {args.sample}:"
        )
        for r in random.Random(args.seed).sample(
            sorted(pool, key=lambda r: r["record"]), min(args.sample, len(pool))
        ):
            print(
                f"{r['record']} | {r['filed']} | {r['address']} | types {r['types_named'] or '?'} | {r['description'][:110]}"
            )


if __name__ == "__main__":
    main()
