"""Assemble the reconciled dated-control batches into the one file the rule engine reads.

Input: $LOCAL_DATA_DIR/controls/reconciled/*.json, one per batch. Each batch was read twice (the second time
blind) from the Planning Code text and settled where the two readings differed. Output:
apps/api/app/memo/data/sf_dated_controls.json. No network, no model, no database.

Checks before anything is written (the script stops on the first failure):
- every expected district is present, with all eight rows;
- the versions of a row neither overlap nor leave a gap, the first starts at null (in force on 2022-01-01) and
  the last ends at null (in force today), and each "to" is the day before the next "from";
- every version has a quote and a URL;
- story cells are P, C, NP, NA or DISPUTED, and an NA cell says what governs instead;
- an entry marked approval_required must not be a rule that speaks only of a referral (referral steps are kept apart);
- the typed fields read from a version's quoted code text have their shape: square-foot figures and the cap on
  eating and drinking uses are whole numbers (a figure of the other code text may be null), the cap names table
  columns, a dated list of exception rows meets like versions inside its version's own dates, and each overlay
  section of `subarea_overlay_sections` is a section number naming a sub-area entry of the version.

    apps/api/.venv/bin/python scripts/validation/assemble_dated_controls.py            # check and write
    apps/api/.venv/bin/python scripts/validation/assemble_dated_controls.py --check    # check only
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import os
import sys
from pathlib import Path

SRC = (Path(os.environ.get("LOCAL_DATA_DIR", "~/sfhp-local")).expanduser() / "controls/reconciled")
OUT = (
    Path(__file__).resolve().parents[2]
    / "apps/api/app/memo/data/sf_dated_controls.json"
)
DISTRICTS = [
    "C-2", "CRNC", "CVR", "CCB", "NCD-POLK", "NCD-LOWER POLK STREET", "NCT-FILLMORE", "NCD-NORTH BEACH",
    "NCD-BROADWAY", "NCT-MISSION", "NCT-24TH-MISSION", "NCT-VALENCIA", "NCD-IRVING", "NCD-INNER SUNSET",
    "NCD-INNER CLEMENT", "NCD-CASTRO", "NCD-HAIGHT", "NCD-WEST PORTAL", "NCD-LAKESIDE VILLAGE", "NCD-BAYVIEW",
    "NCD-PACIFIC", "NC-1", "NC-2", "NC-3", "NCT-3", "RC-4", "RM-3", "RH-2", "MUR", "UMU", "C-3-G", "RH DTR",
]  # fmt: skip
STORY_ROWS = ("bar", "restaurant", "limited_restaurant", "nighttime_entertainment")
ROWS = (*STORY_ROWS, "formula_retail", "use_size", "outdoor_activity_area", "hours")
CELLS = {"P", "C", "NP", "NA", "DISPUTED"}


class Problem(Exception):
    pass


def day(value: str | None) -> dt.date | None:
    return dt.date.fromisoformat(value) if value else None


def check_versions(where: str, versions: list[dict]) -> None:
    if not versions:
        raise Problem(f"{where}: no versions")
    if versions[0].get("from") is not None:
        raise Problem(
            f"{where}: the first version must start at null (in force on 2022-01-01)"
        )
    if versions[-1].get("to") is not None:
        raise Problem(f"{where}: the last version must end at null (in force today)")
    for a, b in itertools.pairwise(versions):
        end, start = day(a.get("to")), day(b.get("from"))
        if end is None or start is None or start != end + dt.timedelta(days=1):
            raise Problem(
                f"{where}: versions do not meet ({a.get('to')} then {b.get('from')})"
            )
    for v in versions:
        if not (v.get("quote") or "").strip() or not (v.get("url") or "").strip():
            raise Problem(
                f"{where}: a version has no quote or no URL (from {v.get('from')})"
            )


def whole(value: object, *, null: bool = False) -> bool:
    return (value is None and null) or (isinstance(value, int) and not isinstance(value, bool) and value > 0)


def check_typed_fields(where: str, v: dict) -> None:
    """The fields typed from a version's quoted code text (the rules read them; tests hold them to the words)."""
    exempt = v.get("conditional_not_required_for")
    if exempt is not None and not (
        exempt.get("use") in STORY_ROWS and whole(exempt.get("larger_than_sqft")) and exempt.get("source")
    ):
        raise Problem(f"{where}: conditional_not_required_for needs a use, a whole larger_than_sqft and a source")
    other = v.get("other_code_text_figures")
    if other is not None and not (
        str(other.get("section", "")).startswith("Planning Code § ")
        and whole(other.get("principal_below_sqft"), null=True)
        and whole(other.get("not_permitted_from_sqft"), null=True)
    ):
        raise Problem(f"{where}: other_code_text_figures needs a section and whole figures (or null)")
    cap = v.get("eating_drinking_cap")
    if cap is not None and not (
        whole(cap.get("max_uses"))
        and cap.get("columns")
        and set(cap["columns"]) <= {"first", "second", "third"}
        and cap.get("source")
    ):
        raise Problem(f"{where}: eating_drinking_cap needs a whole max_uses, table columns and a source")
    dated = v.get("exception_rows_by_date")
    if dated is not None:
        check_versions(f"{where} / exception_rows_by_date", [{**d, "quote": "-", "url": "-"} for d in dated])
        start, end = day(v.get("from")), day(v.get("to"))
        inner = [day(d.get("to")) for d in dated[:-1]]
        if any((start and x < start) or (end and x >= end) for x in inner if x):
            raise Problem(f"{where}: exception_rows_by_date changes outside the version's dates")
        if not all(d.get("rows") and all(isinstance(r, str) and r for r in d["rows"]) for d in dated):
            raise Problem(f"{where}: an exception_rows_by_date entry names no rows")
    sections = v.get("subarea_overlay_sections")
    if sections is not None:
        entries = [*(v.get("subarea_controls") or ()), *(v.get("not_permitted_for_in_subarea") or ())]
        for name, section in sections.items():
            if not str(section).replace(".", "").isdigit():
                raise Problem(f"{where}: subarea_overlay_sections[{name!r}] is not a section number")
            if not any(str(e.get("where", "")).startswith(name) for e in entries):
                raise Problem(f"{where}: subarea_overlay_sections[{name!r}] names no sub-area entry")


def check_district(code: str, body: dict) -> list[str]:
    disputed: list[str] = []
    rows = body.get("rows") or {}
    for row in ROWS:
        if row not in rows:
            raise Problem(f"{code}: row {row!r} is missing")
        versions = rows[row]
        check_versions(f"{code} / {row}", versions)
        for v in versions:
            check_typed_fields(f"{code} / {row} (from {v.get('from')})", v)
            if row in STORY_ROWS:
                for story in ("first", "second", "third"):
                    cell = v.get(story)
                    if cell not in CELLS:
                        raise Problem(f"{code} / {row}: {story} is {cell!r}")
                    if cell == "DISPUTED":
                        disputed.append(
                            f"{code} / {row} / {story} (from {v.get('from')})"
                        )
                    if cell == "NA" and not (
                        v.get("governed_by")
                        or v.get("governing_control")
                        or v.get("note")
                    ):
                        raise Problem(
                            f"{code} / {row}: an NA cell does not say what governs"
                        )
            if "DISPUTED" in json.dumps(v) and row not in STORY_ROWS:
                disputed.append(f"{code} / {row} (from {v.get('from')})")
    return disputed


def walk_rules(node: object, where: str, found: list[tuple[str, dict]]) -> None:
    """Every dict that looks like a dated rule (has 'from' and 'to' keys), anywhere under a citywide or special key."""
    if isinstance(node, dict):
        if "from" in node and "to" in node:
            found.append((where, node))
        for k, v in node.items():
            walk_rules(v, f"{where}.{k}", found)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk_rules(v, f"{where}[{i}]", found)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true", help="check only; write nothing")
    args = p.parse_args()
    districts: dict[str, dict] = {}
    special: dict[str, dict] = {}
    citywide: dict[str, object] = {}
    batches: list[str] = []
    for f in sorted(SRC.glob("*.json")):
        d = json.loads(f.read_text())
        batches.append(f.stem)
        for code, body in (d.get("districts") or {}).items():
            if code in districts:
                raise Problem(f"{code} is in two batches")
            districts[code] = body
        special.update(d.get("special_districts") or {})
        for key, value in (d.get("citywide") or {}).items():
            if key in citywide:
                raise Problem(f"citywide rule {key!r} is in two batches")
            citywide[key] = value
    missing = [c for c in DISTRICTS if c not in districts]
    if missing:
        raise Problem(f"districts not reconciled yet: {missing}")
    disputed: list[str] = []
    for code in DISTRICTS:
        disputed += check_district(code, districts[code])
    rules: list[tuple[str, dict]] = []
    walk_rules(special, "special_districts", rules)
    walk_rules(citywide, "citywide", rules)
    kinds: dict[str, int] = {}
    for where, r in rules:
        kind = r.get("kind")
        if kind is not None:
            kinds[kind] = kinds.get(kind, 0) + 1
        # A rule that removes or adds a referral must be marked as a referral step, never as an approval.
        text = json.dumps(r).lower()
        if (
            kind == "approval_required"
            and "referral" in str(r.get("rule", "")).lower()
            and "permit" not in str(r.get("rule", "")).lower()
        ):
            raise Problem(
                f"{where}: an approval entry whose rule speaks only of a referral"
            )
        if "DISPUTED" in json.dumps(r):
            disputed.append(where)
        del text
    referral_steps, approvals = (
        kinds.get("referral_step", 0),
        kinds.get("approval_required", 0),
    )
    versions = sum(len(v) for b in districts.values() for v in b["rows"].values())
    changed = sum(len(v) > 1 for b in districts.values() for v in b["rows"].values())
    print(f"batches: {', '.join(batches)}")
    print(
        f"districts: {len(districts)}; rows: {len(districts) * len(ROWS)}; versions: {versions}; rows with more than one version: {changed}"
    )
    print(
        f"special districts: {len(special)}; citywide rule groups: {len(citywide)}; dated rules: {len(rules)} ({approvals} marked approval, {referral_steps} marked referral step)"
    )
    print(f"disputed entries: {len(disputed)}")
    for x in disputed:
        print(f"  DISPUTED {x}")
    if args.check:
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "_doc": "Dated Planning Code controls for the pathway rules (rule table v2). Transcribed from the code text on "
        "2026-11-10, each entry read twice (the second time blind) and settled where the readings differed; every "
        "version carries a verbatim quote and the URL read. 'from' null = already in force on 2022-01-01; 'to' null "
        "= in force today. Built by scripts/validation/assemble_dated_controls.py; do not edit by hand.",
        "_read_on": "2026-11-10",
        "_districts": DISTRICTS,
        "districts": {c: districts[c] for c in DISTRICTS},
        "special_districts": special,
        "citywide": citywide,
        "_disputed": disputed,
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Problem as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        sys.exit(1)
