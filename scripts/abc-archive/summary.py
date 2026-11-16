"""Summarise the ABC archive: rows per report per day, and the San Francisco rows.

    apps/api/.venv/bin/python scripts/abc-archive/summary.py ~/abc-archive-data [--sf-csv out.csv]
"""

from __future__ import annotations

import argparse
import csv
import gzip
from collections import Counter, defaultdict
from pathlib import Path

SF_COUNTY_CODE = "38"


def is_sf(row: dict[str, str]) -> bool:
    if row.get("County", "").strip() == SF_COUNTY_CODE:
        return True
    if row.get("Prem County", "").strip().upper() == "SAN FRANCISCO":
        return True
    addr = (row.get("licensee_premises_address") or row.get("Primary Owner and Premises Addr.") or "").upper()
    return ", SAN FRANCISCO, CA" in addr


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("repo", type=Path)
    p.add_argument("--sf-csv", type=Path)
    args = p.parse_args()
    repo: Path = args.repo

    counts: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    sf_rows: list[dict[str, str]] = []
    for f in sorted(repo.glob("daily/*/*.csv")):
        rows = list(csv.DictReader(f.open()))
        sf = [r for r in rows if is_sf(r)]
        counts[f.parent.name][f.stem] = (len(rows), len(sf))
        sf_rows += [{"source": f"daily/{f.stem}", "date": f.parent.name, **r} for r in sf]
    reports = ["issued-licenses", "new-applications", "status-changes"]
    print("| report date | " + " | ".join(f"{r} (SF)" for r in reports) + " |")
    print("|---|" + "---|" * len(reports))
    for day in sorted(counts):
        cells = [f"{counts[day][r][0]} ({counts[day][r][1]})" if r in counts[day] else "—" for r in reports]
        print(f"| {day} | " + " | ".join(cells) + " |")

    print("\n| weekly report | week ending | rows (SF) |\n|---|---|---|")
    for f in sorted(repo.glob("weekly/*/*/rows.csv")):
        rows = list(csv.DictReader(f.open()))
        sf = [r for r in rows if is_sf(r)]
        print(f"| {f.parent.parent.name} | {f.parent.name} | {len(rows)} ({len(sf)}) |")
        sf_rows += [{"source": f"weekly/{f.parent.parent.name}", "date": f.parent.name, **r} for r in sf]

    base = sorted(repo.glob("export/baseline/*.csv.gz"))
    latest = repo / "export" / "latest.csv.gz"
    src = latest if latest.exists() else (base[-1] if base else None)
    if src:
        with gzip.open(src, "rt", newline="") as fh:
            rows = list(csv.DictReader(fh))
        sf = [r for r in rows if is_sf(r)]
        status = Counter(r.get("Type Status", "") for r in sf)
        print(f"\nDaily Data Export ({src.name}): {len(rows):,} rows statewide, {len(sf):,} in San Francisco")
        print("SF by status: " + ", ".join(f"{k} {v:,}" for k, v in status.most_common()))
    for f in sorted(repo.glob("export/changes/*.csv")):
        rows = list(csv.DictReader(f.open()))
        c = Counter(r["change"] for r in rows)
        csf = Counter(r["change"] for r in rows if is_sf(r))
        print(f"export changes {f.stem}: {dict(c)} | SF {dict(csf)}")

    if args.sf_csv:
        cols: list[str] = []
        for r in sf_rows:
            cols += [k for k in r if k not in cols]
        with args.sf_csv.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(sf_rows)
        print(f"\nwrote {len(sf_rows)} San Francisco rows to {args.sf_csv}")


if __name__ == "__main__":
    main()
