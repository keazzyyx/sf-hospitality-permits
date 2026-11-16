"""ABC Annual Workload Summaries next to the rebuilt application histories (Step 1b, part b).

Reads the saved workload pages (one per fiscal year, FY2019-20 to FY2025-26). Reads local files only.

From every page it takes
  * the top "Licensing" table of the Departmental Workload Summary (statewide only). Each page has three
    fiscal-year columns; the column whose header dates are the page's own year is the one used, and the two
    older columns are compared with the pages of those years (``cross_check``).
  * the two tables of application investigations, "Original Application Investigations (220's)" and
    "Transfer Application Investigations (220's)", for the statewide total and the San Francisco office.

    apps/api/.venv/bin/python scripts/validation/abc_workload.py --out docs/validation
    apps/api/.venv/bin/python scripts/validation/abc_workload.py --out docs/validation \
        --histories docs/validation/abc-histories.json

``--histories`` prints the check that abc_histories.py wrote into abc-histories.json (key
``check_against_abc``) as a markdown table, after confirming that the ABC figures stored there are the ones
on the saved pages. A gap is a percentage only where both counts are 10 or more; below that the two counts
stand alone. Rows that split original from transfer say which grouping of actions they use, and the FY2019-20
San Francisco office rows carry the territory note (that year the office also handled San Mateo county).

abc-workload-summaries.csv: one row per fiscal year, scope and class. Classes "original" and "transfer" are the
220 tables (columns received ... pending). Class "licensing summary" is the top Licensing table, statewide:
  received           Permanent License Applications Received
  approved           Applications Recommended for Approval
  denied             Applications Recommended for Denial
  withdrawn          Applications Withdrawn
  priority_received  Priority License Applications Received
  protested          Applications Protested
  licences_issued    Permanent Licenses Issued
  pages_agree        "yes (n pages)" when every saved page that shows the year gives the same seven figures;
                     "only one page shows this year" when there is nothing to compare (the latest year)
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
from pathlib import Path

PAGES = (Path(os.environ.get("LOCAL_DATA_DIR", "~/sfhp-local")).expanduser() / "abc-workload")
YEARS = ["2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
TABLES = {
    "original": "Original Application Investigations",
    "transfer": "Transfer Application Investigations",
}
ROWS = {"statewide": "Statewide Totals", "sf_office": "San Francisco"}
COLS = [
    "received",
    "completed",
    "approved",
    "denied",
    "withdrawn",
    "voided",
    "no_credit_wd",
    "pending",
]
# Top "Licensing" table: row label on the page -> key. Labels are matched after footnote marks are removed.
SUMMARY_ROWS = {
    "Permanent License Applications Received": "received",
    "Priority License Applications Received": "priority_received",
    "Applications Protested": "protested",
    "Applications Withdrawn": "withdrawn",
    "Applications Recommended for Denial": "denied",
    "Applications Recommended for Approval": "approved",
    "Permanent Licenses Issued": "licences_issued",
}
SUMMARY_COLS = [
    "received",
    "approved",
    "denied",
    "withdrawn",
    "priority_received",
    "protested",
    "licences_issued",
]
SUMMARY_CLASS = "licensing summary"
CSV_COLS = [
    "fiscal_year",
    "scope",
    "class",
    *COLS,
    "priority_received",
    "protested",
    "licences_issued",
    "pages_agree",
]
HEADER_YEAR_RE = re.compile(r"07/01/(\d{4})\s*-\s*06/30/(\d{4})")


def cells(row: str) -> list[str]:
    return [
        html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
        for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.DOTALL)
    ]


def number(cell: str) -> int:
    """'1,234' or '15[1]' (a footnote mark) -> the number; blank -> 0."""
    digits = re.sub(r"\[\d+\]", "", cell).replace(",", "").strip()
    return int(digits) if digits else 0


def table_rows(s: str, start: int) -> list[list[str]]:
    j = s.index("<table", start)
    table = s[j : s.index("</table>", j)]
    return [cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.DOTALL)]


def parse_page(
    path: Path, wanted: dict[str, str] | None = None
) -> dict[str, dict[str, dict[str, int]]]:
    """{class: {scope: {column: n}}} for the two 220 tables of one fiscal year's page.

    ``wanted`` maps a key to the row label on the page (an office name or "Statewide Totals"); default ROWS."""
    wanted = ROWS if wanted is None else wanted
    s = path.read_text(encoding="utf-8", errors="replace")
    out: dict[str, dict[str, dict[str, int]]] = {}
    for cls, heading in TABLES.items():
        m = re.search(heading.replace(" ", r"(?:\s|&nbsp;|\xa0)+") + r"[^<]*</h", s)
        assert m, (path.name, heading)
        rows = table_rows(s, m.start())
        head = [c.lower() for c in rows[0]]
        assert head[1:4] == ["received", "completed", "approved"], (path.name, head)
        out[cls] = {}
        for scope, name in wanted.items():
            row = next(r for r in rows if r and r[0] == name)
            out[cls][scope] = {c: number(v) for c, v in zip(COLS, row[1:], strict=True)}
    return out


def parse_summary(path: Path) -> dict[str, dict[str, int]]:
    """{fiscal year: {key: n}} for every fiscal-year column of the page's top "Licensing" table."""
    s = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<h\d[^>]*>\s*Licensing\s*</h\d>", s)
    assert m, (path.name, "Licensing heading")
    rows = table_rows(s, m.start())
    years: list[str | None] = []
    for c in rows[0][1:]:
        hm = HEADER_YEAR_RE.search(c)
        years.append(f"{hm.group(1)}-{hm.group(2)[2:]}" if hm else None)
    assert any(years), (path.name, rows[0])
    out: dict[str, dict[str, int]] = {y: {} for y in years if y}
    for r in rows[1:]:
        if not r:
            continue
        label = re.sub(r"\s*(\[\d+\]|\*+)\s*$", "", r[0]).strip()
        key = SUMMARY_ROWS.get(label)
        if key is None:
            continue
        for y, v in zip(years, r[1:], strict=True):
            if y:
                out[y][key] = number(v)
    for y, vals in out.items():
        assert set(vals) == set(SUMMARY_ROWS.values()), (path.name, y, sorted(vals))
    return out


def page(fy: str) -> Path:
    return PAGES / f"workload{fy[2:4]}{fy[5:7]}.html"


def load() -> dict[str, dict[str, dict[str, dict[str, int]]]]:
    """{fiscal year: {class: {scope: {column: n}}}} for the two 220 tables."""
    return {fy: parse_page(page(fy)) for fy in YEARS}


def load_rows(
    wanted: dict[str, str],
) -> dict[str, dict[str, dict[str, dict[str, int]]]]:
    """Like load(), for any rows of the two 220 tables: {fiscal year: {class: {key: {column: n}}}}."""
    return {fy: parse_page(page(fy), wanted) for fy in YEARS}


def restated_figures() -> dict[str, dict[str, int]]:
    """{fiscal year: {Licensing-table row label: n}} for every figure a LATER page gives differently from the
    year's own page (ABC restates some prior-year figures). The value is the one on the latest page."""
    labels = {v: k for k, v in SUMMARY_ROWS.items()}
    by_page = {fy: parse_summary(page(fy)) for fy in YEARS}
    out: dict[str, dict[str, int]] = {}
    for fy in YEARS:
        latest = max(p for p, cols in by_page.items() if fy in cols)
        diff = {
            labels[k]: by_page[latest][fy][k]
            for k in SUMMARY_COLS
            if by_page[latest][fy][k] != by_page[fy][fy][k]
        }
        if diff:
            out[fy] = diff
    return out


def pages_agree(c: dict) -> str:
    """The pages_agree cell: nothing was compared when only one saved page shows the year."""
    if c["pages"] == 1:
        return "only one page shows this year"
    if c["agree"]:
        return f"yes ({c['pages']} pages)"
    return "no: " + describe(c["differences"])


def load_summary() -> tuple[dict[str, dict[str, int]], dict[str, dict]]:
    """The top Licensing table per fiscal year (own-year column), and the cross-check between pages.

    cross_check[fy] = {"pages": n pages that show the year, "agree": bool (None when only one page shows the
    year: nothing was compared), "differences": {key: {page: n}}}
    """
    by_page = {fy: parse_summary(page(fy)) for fy in YEARS}
    own: dict[str, dict[str, int]] = {}
    cross: dict[str, dict] = {}
    for fy in YEARS:
        assert fy in by_page[fy], (fy, "own-year column missing", sorted(by_page[fy]))
        own[fy] = by_page[fy][fy]
        shown = {p: cols[fy] for p, cols in by_page.items() if fy in cols}
        diffs = {
            k: {p: v[k] for p, v in shown.items()}
            for k in SUMMARY_COLS
            if len({v[k] for v in shown.values()}) > 1
        }
        cross[fy] = {
            "pages": len(shown),
            "agree": (not diffs) if len(shown) > 1 else None,
            "differences": diffs,
        }
        cross[fy]["pages_agree"] = pages_agree(cross[fy])
    return own, cross


def describe(differences: dict[str, dict[str, int]]) -> str:
    """'withdrawn 913 on the 2021-22 page, 883 on the 2023-24 page; ...'"""
    parts = []
    for key, by_page in differences.items():
        seen: dict[int, list[str]] = {}
        for pg, v in by_page.items():
            seen.setdefault(v, []).append(pg)
        parts.append(
            f"{key} "
            + ", ".join(
                f"{v:,} on the {' and '.join(pgs)} page{'s' if len(pgs) > 1 else ''}"
                for v, pgs in seen.items()
            )
        )
    return "; ".join(parts)


SMALL_N = 10


def gap(ours: int, abc: int) -> str:
    """The gap as a percentage; where either count is under 10, the two counts only."""
    if ours < SMALL_N or abc < SMALL_N:
        return f"{ours:,} against {abc:,} (under 10: no percentage)"
    return f"{(ours - abc) / abc * 100:+.1f}%"


def abc_figures() -> dict[str, dict[str, dict[str, int]]]:
    """Every ABC figure the check uses: {fiscal year: {scope: {measure: n}}}."""
    wl = load()
    summary, _ = load_summary()
    out: dict[str, dict[str, dict[str, int]]] = {}
    for fy in YEARS:
        out[fy] = {}
        for scope in ROWS:
            tot = {c: sum(wl[fy][cls][scope][c] for cls in TABLES) for c in COLS}
            fig = {
                "investigations approved (original + transfer)": tot["approved"],
                "investigations approved, original": wl[fy]["original"][scope][
                    "approved"
                ],
                "investigations approved, transfer": wl[fy]["transfer"][scope][
                    "approved"
                ],
                "investigations withdrawn (original + transfer)": tot["withdrawn"],
                "investigations withdrawn + voided + no credit WD": tot["withdrawn"]
                + tot["voided"]
                + tot["no_credit_wd"],
                "investigations denied (original + transfer)": tot["denied"],
            }
            if scope == "statewide":
                s = summary[fy]
                fig |= {
                    "Permanent Licenses Issued": s["licences_issued"],
                    "Applications Recommended for Approval": s["approved"],
                    "Applications Withdrawn": s["withdrawn"],
                    "Applications Recommended for Denial": s["denied"],
                    "Priority License Applications Received": s["priority_received"],
                    "Permanent License Applications Received": s["received"],
                    "Permanent + Priority License Applications Received": s["received"]
                    + s["priority_received"],
                }
            out[fy][scope] = fig
    return out


def write_csv(out: Path) -> None:
    wl = load()
    summary, cross = load_summary()
    with open(out / "abc-workload-summaries.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS, restval="")
        w.writeheader()
        for fy, by_cls in wl.items():
            for cls, by_scope in by_cls.items():
                for scope, row in by_scope.items():
                    w.writerow({"fiscal_year": fy, "scope": scope, "class": cls, **row})
        for fy, row in summary.items():
            agree = pages_agree(cross[fy])
            w.writerow(
                {
                    "fiscal_year": fy,
                    "scope": "statewide",
                    "class": SUMMARY_CLASS,
                    **{k: row[k] for k in SUMMARY_COLS},
                    "pages_agree": agree,
                }
            )


def print_abc_tables() -> None:
    wl = load()
    summary, cross = load_summary()
    print("ABC top Licensing table (statewide)\n")
    print(
        "| Fiscal year | Permanent applications received | Priority applications received | Withdrawn "
        "| Recommended for denial | Recommended for approval | Permanent licences issued | Pages agree |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for fy, s in summary.items():
        agree = pages_agree(cross[fy])
        print(
            f"| {fy} | {s['received']:,} | {s['priority_received']:,} | {s['withdrawn']:,} | {s['denied']:,} "
            f"| {s['approved']:,} | {s['licences_issued']:,} | {agree} |"
        )
    print("\nABC application investigations (220's), original + transfer\n")
    print(
        "| Fiscal year | Scope | Approved | Denied | Withdrawn | Voided | No credit WD | Received |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for fy, by_cls in wl.items():
        for scope in ROWS:
            tot = {c: sum(by_cls[cls][scope][c] for cls in TABLES) for c in COLS}
            print(
                f"| {fy} | {scope} | {tot['approved']:,} | {tot['denied']:,} | {tot['withdrawn']:,} "
                f"| {tot['voided']:,} | {tot['no_credit_wd']:,} | {tot['received']:,} |"
            )


def print_check(histories: Path) -> None:
    """The check written by abc_histories.py, as markdown; fails if its ABC figures are not the pages'."""
    rows = json.loads(histories.read_text())["check_against_abc"]
    figures = abc_figures()
    for r in rows:
        on_page = figures[r["fiscal_year"]][r["scope"]][r["abc_measure"]]
        assert on_page == r["abc"], (
            "ABC figure in the histories differs from the saved page",
            r,
            on_page,
        )
    groupings: list[str] = []
    notes: list[str] = []
    for scope in ROWS:
        print(f"\nCheck against ABC, {scope}\n")
        print(
            "| Fiscal year | Archive count (files) | n | ABC figure | n | Gap | Restated by ABC later | Notes |"
        )
        print("|---|---|---|---|---|---|---|---|")
        for r in rows:
            if r["scope"] != scope:
                continue
            marks = []
            grouping = r.get("grouping", "")
            if grouping and not grouping.startswith("all actions"):
                if grouping not in groupings:
                    groupings.append(grouping)
                marks.append(f"grouping {groupings.index(grouping) + 1}")
            if r.get("territory_note"):
                if r["territory_note"] not in notes:
                    notes.append(r["territory_note"])
                marks.append("territory")
            later = r.get("abc_restated_on_a_later_page")
            restated = (
                f"{later:,} ({gap(r['ours'], later)})" if later is not None else ""
            )
            print(
                f"| {r['fiscal_year']} | {r['measure']} | {r['ours']:,} | {r['abc_measure']} "
                f"| {r['abc']:,} | {gap(r['ours'], r['abc'])} | {restated} | {', '.join(marks)} |"
            )
    for i, g in enumerate(groupings, 1):
        print(f"\ngrouping {i}: {g}")
    for n in notes:
        print(f"\nterritory: {n}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="docs/validation")
    p.add_argument(
        "--histories",
        help="abc-histories.json from abc_histories.py; prints the check against ABC",
    )
    args = p.parse_args()
    write_csv(Path(args.out))
    print_abc_tables()
    if args.histories:
        print_check(Path(args.histories))


if __name__ == "__main__":
    main()
