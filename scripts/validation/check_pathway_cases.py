"""Run the pathway cases against the LOCAL validation database and print found against expected.

For each case in apps/api/tests/fixtures/pathway_cases.json the address point is looked up through the real
store, the way `MemoRunner.collect_records` does it: the zoning district, the overlays, and the records on file
at the address. Then `app.memo.pathway.determine` runs and the result is compared with the fixture. No model is
called, nothing is geocoded and nothing is written.

Safety:
* refuses any database whose host is not localhost;
* every connection is opened read-only (`default_transaction_read_only=on`), and the script checks that it is.

    cd apps/api && .venv/bin/python ../../scripts/validation/check_pathway_cases.py
    cd apps/api && .venv/bin/python ../../scripts/validation/check_pathway_cases.py --rules-file
    cd apps/api && .venv/bin/python ../../scripts/validation/check_pathway_cases.py --table-diff --print-sql

`--rules-file` answers "what will this print once the rule-table corrections are in the local database?": the
rows come from the database as before, and the fields the rules file sets (name, rules text, code section, the
two controls, the hours) are replaced in memory by what the current rules file gives. The database is not
changed.

`--table-diff` lists every overlay row in the database whose rule fields differ from the current rules file, and
`--print-sql` prints the UPDATE statements that would bring them in line. The statements are printed only: this
script never runs them.

Result column: PASS / FAIL for an undisputed case; GAP for a case where the rules are known not to give the
Code's answer (PASS-GAP when they return what the fixture records, FAIL-GAP when that changed). A gap may show
only when the inputs are stated in full (nc1-late-bar: as written the rules' answer is the right one, and the
gap is the Code's answer stated in full); such a case is PASS-GAP when the answer as written is both the one the
fixture records and the expected one, and this script, which runs the profile as written, says so. FACT for a case
whose answer under the Code turns on a fact that is not on file (PASS-FACT when the rules return the best case
the fixture records, FAIL-FACT when they do not; never counted as PASS); DISPUTED for a case whose readings
could not be settled (never counted). The exit code is 1 when any case is FAIL, FAIL-GAP or FAIL-FACT.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

LOCAL = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres@localhost:55433/sfhp_local")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
if urlsplit(LOCAL).hostname not in LOCAL_HOSTS:
    raise SystemExit(
        "refusing: check_pathway_cases.py only reads the local validation database (host localhost)"
    )
os.environ["PRECEDENT_DATABASE_URL"] = LOCAL
os.environ["NEATLOGS_API_KEY"] = ""  # no trace export

import psycopg  # noqa: E402
from precedent.models import Application, Overlay  # noqa: E402
from precedent.sources import datasf_sud, datasf_zoning  # noqa: E402
from precedent.store.base import Nearby, ZoningInfo  # noqa: E402
from precedent.store.postgres import PostgresStore  # noqa: E402
from psycopg.conninfo import make_conninfo  # noqa: E402

from app.agents.memo_runner import SITE_READ_LIMIT, required_areas  # noqa: E402
from app.memo import analytics  # noqa: E402
from app.memo.pathway import determine  # noqa: E402
from app.memo.report import SITE_READ_RADIUS_M, site_of, site_records  # noqa: E402
from app.models.memo import Determinations  # noqa: E402
from app.models.profile import BusinessProfile  # noqa: E402
from app.tools.precedent_tools import read_base_rate_rows  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "apps" / "api" / "tests" / "fixtures" / "pathway_cases.json"
READ_ONLY = make_conninfo(LOCAL, options="-c default_transaction_read_only=on")
# the record kinds collect_records reads for the comparable list (MemoRunner.collect_records)
APPLICATION_KINDS = [
    "cua",
    "planning_other",
    "entertainment_poe",
    "entertainment_llp",
    "entertainment_sound",
    "entertainment_other",
]
RULE_FIELDS = ("name", "rules", "code_section", "bar_permission", "restaurant_permission", "late_night_rule")
SUD_NAMES = {
    datasf_sud.slug(name): name
    for name in (*datasf_sud.SUD_SECTIONS, *datasf_zoning.rules_doc().get("sud_name_aliases", {}))
}
STATUS_CODES = {
    "allowed": "AL",
    "further_review": "FR",
    "potential_blocker": "PB",
    "not_permitted": "NP",
    "insufficient_information": "II",
}
AREAS = ("zoning_use", "alcohol", "entertainment", "health", "building_change_of_use", "outdoor")
AREA_HEADS = {
    "zoning_use": "zoning",
    "alcohol": "alcohol",
    "entertainment": "entert.",
    "health": "health",
    "building_change_of_use": "building",
    "outdoor": "outdoor",
}
# What a passing result becomes when the store rows at the address differ from the fixture's.
FAILED_AS = {"PASS": "FAIL", "PASS-GAP": "FAIL-GAP", "PASS-FACT": "FAIL-FACT"}
LEGEND = (
    "Statuses: AL allowed, FR further review, PB potential blocker, NP not permitted, II insufficient information, "
    "- no such row. A cell shows what was found; '(exp X)' follows when the fixture expects X."
)


# ---- the rules file, applied over a row in memory --------------------------------------------------------
def rules_file_row(row: Overlay) -> Overlay | None:
    """The row the current rules file gives for this overlay id; None when the rules file does not set it."""
    source, key = row.id.split(":", 1)
    if source == "datasf_zoning":
        if key not in datasf_zoning.zoning_controls():
            return None  # no control on file for the code: the row's text comes from the dataset alone
        return datasf_zoning.overlay_for(key, [], row.fetched_at)
    if source == "datasf_sud":
        name = SUD_NAMES.get(key)
        return datasf_sud.overlay_for(name, [], row.fetched_at) if name else None
    if source == "static":
        found = next((o for o in datasf_zoning.rules_doc()["overlays"] if o["id"] == row.id), None)
        return Overlay.model_validate(found) if found else None
    return None


def differences(row: Overlay) -> dict[str, tuple[Any, Any]]:
    """field -> (on file, rules file) for every rule field that differs."""
    fresh = rules_file_row(row)
    if fresh is None:
        return {}
    return {
        f: (getattr(row, f), getattr(fresh, f)) for f in RULE_FIELDS if getattr(row, f) != getattr(fresh, f)
    }


def with_rules_file(row: Overlay) -> Overlay:
    changed = differences(row)
    return row.model_copy(update={f: new for f, (_old, new) in changed.items()}) if changed else row


def zoning_from(overlays: list[Overlay]) -> ZoningInfo | None:
    """The same reading as the store's `zoning_at`: the attached rule row first, else the district's own row."""
    zoning = next((o for o in overlays if o.kind == "zoning_district"), None)
    if zoning is None:
        return None
    rule = next((o for o in overlays if o.kind == "nc_rule"), None)
    src = rule or zoning
    return ZoningInfo(
        district=zoning.name,
        name=rule.name if rule else zoning.name,
        code_section=src.code_section,
        bar_permission=src.bar_permission,
        restaurant_permission=src.restaurant_permission,
        rules=src.rules,
        source_url=src.source_url,
    )


# ---- one case ---------------------------------------------------------------------------------------------
async def run_case(
    store: PostgresStore, case: dict[str, Any], *, rules_file: bool
) -> tuple[Determinations, ZoningInfo | None, list[Overlay], list[str]]:
    lat, lng = case["lat"], case["lng"]
    profile = BusinessProfile.model_validate(case["profile"])
    zoning = await store.zoning_at(lat, lng)
    overlays = await store.overlays_at(lat, lng)
    if rules_file:
        overlays = [with_rules_file(o) for o in overlays]
        zoning = zoning_from(overlays)
    # the same reads collect_records makes before it matches records to the site
    applications: list[Nearby[Application]] = await store.nearby_applications(
        lat, lng, analytics.FT_1000_M, kinds=APPLICATION_KINDS, limit=analytics.CANDIDATE_WINDOW
    )
    licenses_1000 = await store.nearby_applications(
        lat, lng, analytics.FT_1000_M, kinds=["abc_license"], limit=300
    )
    rate_pool = await read_base_rate_rows(store, lat, lng)
    applications = analytics.fill_candidate_window(applications, rate_pool)
    at_point = await store.nearby_applications(lat, lng, SITE_READ_RADIUS_M, limit=SITE_READ_LIMIT)
    site = site_of(case["address"], None, case["parcel"])
    at_site = site_records([*applications, *licenses_1000, *rate_pool, *at_point], site)
    d = determine(profile, zoning, overlays, at_site, site, required_areas(profile))
    licences_here = sorted(
        r.app.id
        for r in at_site
        if r.app.kind == "abc_license"
        and f"app:{r.app.id}" in {c for line in d.pathway.lines for c in line.citations}
    )
    return d, zoning, overlays, licences_here


def answer(d: Determinations) -> dict[str, Any]:
    return {
        "use": d.pathway.use,
        "permission": d.pathway.permission,
        "existing_use": d.pathway.existing_use or "none_shown",
        "change_of_use": d.pathway.change_of_use,
        "statuses": {r.area: r.status for r in d.rows},
    }


def cell(found: str | None, expected: str | None, codes: dict[str, str] | None = None) -> str:
    def show(value: str | None) -> str:
        if value is None:
            return "-"
        return (codes or {}).get(value, value.replace("_", " "))

    return show(found) if found == expected else f"{show(found)} (exp {show(expected)})"


def judge(case: dict[str, Any], got: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str]:
    """(result, the answer to print as expected, a remark)."""
    if case["disputed"]:
        matches = [r["name"] for r in case["dispute"]["readings"] if {k: r[k] for k in got} == got]
        return "DISPUTED", None, f"the rules give the answer of: {', '.join(matches) or 'neither reading'}"
    expected = case["expected"]
    if case["rules_gap"]:
        gap = case["rules_gap"]
        as_recorded = got == gap["rules_return"]
        if got == expected and not as_recorded:
            return (
                "FAIL-GAP",
                expected,
                "the rules now give the right answer as written: update rules_gap in the fixture",
            )
        if got == expected:
            # the gap shows only stated in full: as written the recorded answer is the right one
            return (
                "PASS-GAP",
                expected,
                "known gap, stated in full only (the answer as written is right): " + gap["why"],
            )
        return ("PASS-GAP" if as_recorded else "FAIL-GAP"), expected, "known gap: " + gap["why"]
    if case.get("depends_on_fact"):
        fact = case["depends_on_fact"]["fact"]
        return (
            ("PASS-FACT" if got == expected else "FAIL-FACT"),
            expected,
            "best case only; depends on a fact not on file: " + fact,
        )
    return ("PASS" if got == expected else "FAIL"), expected, ""


def table(rows: list[list[str]], heads: list[str]) -> str:
    widths = [max(len(r[i]) for r in [heads, *rows]) for i in range(len(heads))]

    def line(r: list[str]) -> str:
        return " | ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)).rstrip()

    return "\n".join([line(heads), "-+-".join("-" * w for w in widths), *(line(r) for r in rows)])


# ---- the whole run -----------------------------------------------------------------------------------------
async def check(args: argparse.Namespace) -> tuple[int, list[dict[str, Any]]]:
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = doc["cases"]
    store = PostgresStore(READ_ONLY, min_size=1, max_size=2)
    out_rows: list[list[str]] = []
    remarks: list[str] = []
    results: list[dict[str, Any]] = []
    stale: dict[str, dict[str, tuple[Any, Any]]] = {}
    try:
        async with store._connection() as conn:  # the store's own connection: prove it cannot write
            cur = await conn.execute("show transaction_read_only")
            row = await cur.fetchone()
            read_only = next(iter(row.values())) if isinstance(row, dict) else row[0]
            if read_only != "on":
                raise SystemExit("refusing: the database connection is not read-only")
            cur = await conn.execute(
                "select count(*) as n, max(fetched_at) as latest from applications where kind = 'abc_license'"
            )
            abc = await cur.fetchone()
        for case in cases:
            d, zoning, overlays, licences_here = await run_case(store, case, rules_file=args.rules_file)
            for o in overlays:
                changed = differences(o)
                if changed:
                    stale[o.id] = changed
            got = answer(d)
            result, expected, remark = judge(case, got)
            district = zoning.district if zoning else None
            recorded_ids = sorted(o["id"] for o in case["store"]["overlays"])
            found_ids = sorted(o.id for o in overlays)
            if district != case["store"]["district"] or found_ids != recorded_ids:
                extra = sorted(set(found_ids) - set(recorded_ids))
                missing = sorted(set(recorded_ids) - set(found_ids))
                remark = (remark + " " if remark else "") + (
                    f"store rows differ from the fixture: district {district!r}, extra {extra}, missing {missing}"
                )
                result = FAILED_AS.get(result, result)
            exp = expected or {}
            exp_status = exp.get("statuses", {})
            out_rows.append(
                [
                    case["id"],
                    cell(district, case["store"]["district"]),
                    cell(got["use"], exp.get("use", got["use"])),
                    cell(got["permission"], exp.get("permission", got["permission"])),
                    cell(got["existing_use"], exp.get("existing_use", got["existing_use"])),
                    cell(got["change_of_use"], exp.get("change_of_use", got["change_of_use"])),
                    *[
                        cell(
                            got["statuses"].get(a),
                            exp_status.get(a) if expected else got["statuses"].get(a),
                            STATUS_CODES,
                        )
                        for a in AREAS
                    ],
                    result,
                ]
            )
            if remark:
                remarks.append(f"{case['id']}: {remark}")
            results.append(
                {
                    "id": case["id"],
                    "result": result,
                    "district": district,
                    "found": got,
                    "expected": expected,
                    "overall_status": d.overall_status,
                    "overall_line": d.overall_line,
                    "licences_read_at_address": licences_here,
                    "overlay_ids": found_ids,
                }
            )
    finally:
        await store.close()

    heads = [
        "case",
        "district",
        "use",
        "permission",
        "existing use",
        "change of use",
        *[AREA_HEADS[a] for a in AREAS],
        "result",
    ]
    mode = (
        "rows on file, rule fields replaced in memory by the current rules file"
        if args.rules_file
        else "rows as on file"
    )
    print(
        f"Pathway cases against {urlsplit(LOCAL).hostname}:{urlsplit(LOCAL).port}{urlsplit(LOCAL).path} (read-only; {mode})"
    )
    n_abc = abc["n"] if isinstance(abc, dict) else abc[0]
    latest = abc["latest"] if isinstance(abc, dict) else abc[1]
    print(f"ABC licences on file: {n_abc} (latest fetched {latest:%Y-%m-%d}). No model call, no write.")
    print()
    print(table(out_rows, heads))
    print()
    print(LEGEND)
    counts: dict[str, int] = {}
    for r in results:
        counts[r["result"]] = counts.get(r["result"], 0) + 1
    print("Result: " + ", ".join(f"{n} {name}" for name, n in sorted(counts.items())))
    if remarks:
        print()
        print("Remarks")
        for text in remarks:
            print(f"- {text}")
    if stale and not args.rules_file:
        print()
        print("Rows on file at these addresses whose rule fields differ from the current rules file")
        for oid in sorted(stale):
            for name, (old, new) in stale[oid].items():
                print(f"- {oid}.{name}: on file {short(old)} -> rules file {short(new)}")
    return (1 if any(r["result"] in FAILED_AS.values() for r in results) else 0), results


def short(value: Any, limit: int = 110) -> str:
    text = "null" if value is None else str(value)
    return repr(text if len(text) <= limit else text[: limit - 1] + "…")


def table_diff(print_sql: bool) -> None:
    """Every overlay row in the database whose rule fields differ from the current rules file. Read-only."""
    with psycopg.connect(READ_ONLY) as conn:
        if conn.execute("show transaction_read_only").fetchone()[0] != "on":  # type: ignore[index]
            raise SystemExit("refusing: the database connection is not read-only")
        cur = conn.execute(
            "select id, kind, name, rules, code_section, district_codes, bar_permission, restaurant_permission, "
            "late_night_rule, source, source_url, fetched_at from overlays order by id"
        )
        names = [c.name for c in cur.description or []]
        rows = [
            Overlay.model_validate({**dict(zip(names, r, strict=True)), "geom": None}) for r in cur.fetchall()
        ]
    on_file = {r.id for r in rows}
    changes = [(r.id, differences(r)) for r in rows]
    changes = [(oid, diff) for oid, diff in changes if diff]
    missing = [o["id"] for o in datasf_zoning.rules_doc()["overlays"] if o["id"] not in on_file]
    print(
        f"Overlay rows in the database: {len(rows)}. Rows whose rule fields differ from the rules file: {len(changes)}."
    )
    for oid, diff in changes:
        for name, (old, new) in diff.items():
            print(f"- {oid}.{name}: on file {short(old)} -> rules file {short(new)}")
    for oid in missing:
        print(
            f"- {oid}: in the rules file, not in the database (a rule row; it is added by the static source)"
        )
    if print_sql:
        print()
        print(
            "-- UPDATE statements for the LOCAL validation database. Printed only; this script did not run them."
        )
        for oid, diff in changes:
            sets = ", ".join(f"{name} = {sql_literal(new)}" for name, (_old, new) in diff.items())
            print(f"update overlays set {sets} where id = {sql_literal(oid)};")
        if missing:
            print(
                "-- rule rows to add: run the static source ingest for the local database, or insert them by hand:"
            )
            for oid in missing:
                row = next(o for o in datasf_zoning.rules_doc()["overlays"] if o["id"] == oid)
                cols = [
                    "id",
                    "kind",
                    "name",
                    "rules",
                    "code_section",
                    "bar_permission",
                    "restaurant_permission",
                    "late_night_rule",
                    "source",
                    "source_url",
                    "fetched_at",
                ]
                values = ", ".join(sql_literal(row[c]) for c in cols)
                print(
                    f"-- insert into overlays ({', '.join(cols)}, district_codes) values ({values}, '{{}}');"
                )


def sql_literal(value: Any) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument(
        "--rules-file",
        action="store_true",
        help="replace each row's rule fields, in memory, with what the current rules file gives",
    )
    parser.add_argument(
        "--table-diff", action="store_true", help="list database rows that differ from the rules file"
    )
    parser.add_argument(
        "--print-sql", action="store_true", help="with --table-diff: print the UPDATE statements (not run)"
    )
    parser.add_argument("--json", help="also write the results to this file")
    args = parser.parse_args()
    if args.table_diff:
        table_diff(args.print_sql)
        return
    code, results = asyncio.run(check(args))
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1, default=str) + "\n", encoding="utf-8")
    sys.exit(code)


if __name__ == "__main__":
    main()
