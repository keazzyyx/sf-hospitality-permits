#!/usr/bin/env python3
"""Print a coverage table for the catalog (entries, verified share, categories) per jurisdiction.

Usage: python3 packages/catalog/scripts/coverage.py [--markdown]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data"
KEY_CATEGORIES = ["business_registration", "health", "building", "fire", "alcohol", "zoning", "signage", "grease",
                  "entertainment", "outdoor_dining", "labor", "hotel", "mobile_vending"]


def main() -> int:
    markdown = "--markdown" in sys.argv
    rows = []
    total = Counter()
    for path in sorted(ROOT.rglob("*.json")):
        doc = json.loads(path.read_text())
        jur = doc["jurisdiction"]
        permits = doc["permits"]
        verified = sum(1 for p in permits if p["confidence"] == "verified")
        cats = {p["category"] for p in permits}
        stall = sum(1 for p in permits if p.get("stall_risk"))
        rows.append((jur["level"], jur["name"], len(permits), verified, stall, cats))
        total["permits"] += len(permits)
        total["verified"] += verified
    if markdown:
        print("| level | jurisdiction | entries | verified | stall risks | missing key categories |")
        print("|---|---|---:|---:|---:|---|")
        for level, name, n, v, s, cats in rows:
            missing = [c for c in KEY_CATEGORIES if c not in cats] if level == "city" else []
            print(f"| {level} | {name} | {n} | {v} ({v * 100 // max(n, 1)}%) | {s} | {', '.join(missing) or '—'} |")
        print(f"\n**Total:** {total['permits']} entries, {total['verified']} verified ({total['verified'] * 100 // max(total['permits'], 1)}%).")
    else:
        for level, name, n, v, s, _ in rows:
            print(f"{level:8} {name:60} {n:3} entries  {v:3} verified  {s:2} stall risks")
        print(f"\nTotal: {total['permits']} entries, {total['verified']} verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
