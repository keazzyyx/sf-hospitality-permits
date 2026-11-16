#!/usr/bin/env python3
"""Dependency-free validator for the Permit Memo catalog.

Usage:  python3 packages/catalog/scripts/validate.py [--strict-dates]

Checks every entry against the schema's required fields / enums / patterns,
verifies prerequisite ids resolve, detects dependency cycles, and validates
`applies_when` rules. Exits non-zero on the first category of failure.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema" / "permit.schema.json").read_text())
DEFS = SCHEMA["$defs"]
PERMIT_PROPS = DEFS["permit"]["properties"]
CATEGORIES = set(PERMIT_PROPS["category"]["enum"])
LEVELS = set(PERMIT_PROPS["jurisdiction_level"]["enum"])
CONFIDENCE = set(PERMIT_PROPS["confidence"]["enum"])
FIELDS = set(DEFS["profileField"]["enum"])
ID_RE = re.compile(PERMIT_PROPS["id"]["pattern"])
OPS = {"eq", "neq", "in", "not_in", "gt", "gte", "lt", "lte"}


def rule_errors(rule: object, where: str) -> list[str]:
    errs: list[str] = []
    if not isinstance(rule, dict) or len(rule) == 0:
        return [f"{where}: rule must be a non-empty object"]
    if "always" in rule:
        if rule != {"always": True}:
            errs.append(f"{where}: 'always' rule must be exactly {{\"always\": true}}")
        return errs
    for combinator in ("all", "any"):
        if combinator in rule:
            if set(rule) != {combinator} or not isinstance(rule[combinator], list) or not rule[combinator]:
                errs.append(f"{where}: '{combinator}' must be the only key and a non-empty list")
                return errs
            for i, sub in enumerate(rule[combinator]):
                errs += rule_errors(sub, f"{where}.{combinator}[{i}]")
            return errs
    if "not" in rule:
        if set(rule) != {"not"}:
            errs.append(f"{where}: 'not' must be the only key")
        return errs + rule_errors(rule.get("not"), f"{where}.not")
    if "field" in rule:
        if rule["field"] not in FIELDS:
            errs.append(f"{where}: unknown profile field {rule['field']!r}")
        ops = set(rule) - {"field"}
        if len(ops) != 1 or not ops <= OPS:
            errs.append(f"{where}: field rule needs exactly one operator from {sorted(OPS)}, got {sorted(ops)}")
        else:
            op = ops.pop()
            if op in {"in", "not_in"} and (not isinstance(rule[op], list) or not rule[op]):
                errs.append(f"{where}: '{op}' needs a non-empty list")
            if op in {"gt", "gte", "lt", "lte"} and not isinstance(rule[op], (int, float)):
                errs.append(f"{where}: '{op}' needs a number")
        return errs
    return [f"{where}: unrecognised rule shape {sorted(rule)}"]


def permit_errors(p: dict, where: str) -> list[str]:
    errs: list[str] = []
    required = DEFS["permit"]["required"]
    for key in required:
        if key not in p:
            errs.append(f"{where}: missing required field '{key}'")
    extra = set(p) - set(PERMIT_PROPS)
    if extra:
        errs.append(f"{where}: unknown fields {sorted(extra)}")
    if errs:
        return errs
    if not ID_RE.match(p["id"]):
        errs.append(f"{where}: id {p['id']!r} does not match {ID_RE.pattern}")
    if not (4 <= len(p["name"]) <= 120):
        errs.append(f"{where}: name length out of range")
    if p["category"] not in CATEGORIES:
        errs.append(f"{where}: bad category {p['category']!r}")
    if p["jurisdiction_level"] not in LEVELS:
        errs.append(f"{where}: bad jurisdiction_level {p['jurisdiction_level']!r}")
    if p["confidence"] not in CONFIDENCE:
        errs.append(f"{where}: bad confidence {p['confidence']!r}")
    for rng in ("typical_timeline_days", "fee_range_usd"):
        r = p[rng]
        if not isinstance(r, dict) or set(r) != {"min", "max"}:
            errs.append(f"{where}: {rng} must be {{min,max}}")
            continue
        if not all(isinstance(r[k], (int, float)) and r[k] >= 0 for k in ("min", "max")):
            errs.append(f"{where}: {rng} values must be non-negative numbers")
        elif r["min"] > r["max"]:
            errs.append(f"{where}: {rng} min > max")
    if not isinstance(p["prerequisites"], list) or len(set(p["prerequisites"])) != len(p["prerequisites"]):
        errs.append(f"{where}: prerequisites must be a list of unique ids")
    else:
        for pre in p["prerequisites"]:
            if not ID_RE.match(pre):
                errs.append(f"{where}: prerequisite {pre!r} is not a valid id")
            if pre == p["id"]:
                errs.append(f"{where}: permit lists itself as a prerequisite")
    if not str(p["application_url"]).startswith("https://"):
        errs.append(f"{where}: application_url must be https")
    for u in p.get("sources", []):
        if not str(u).startswith("https://"):
            errs.append(f"{where}: source {u!r} must be https")
    if len(p["notes"]) < 10:
        errs.append(f"{where}: notes too short")
    try:
        d = dt.date.fromisoformat(p["last_verified"])
        if d > dt.date.today():
            errs.append(f"{where}: last_verified is in the future")
    except ValueError:
        errs.append(f"{where}: last_verified must be YYYY-MM-DD")
    errs += rule_errors(p["applies_when"], f"{where}.applies_when")
    return errs


def file_errors(path: Path, doc: dict) -> list[str]:
    errs: list[str] = []
    where = str(path.relative_to(ROOT))
    if set(doc) != {"jurisdiction", "permits"}:
        errs.append(f"{where}: top-level keys must be exactly jurisdiction, permits")
        return errs
    j = doc["jurisdiction"]
    if j.get("level") not in {"federal", "state", "city"}:
        errs.append(f"{where}: jurisdiction.level invalid")
    if j.get("level") == "state" and not re.fullmatch(r"[A-Z]{2}", str(j.get("state"))):
        errs.append(f"{where}: state files need jurisdiction.state (2 letters)")
    if j.get("level") == "city":
        if not j.get("city_slug") or path.stem != j["city_slug"]:
            errs.append(f"{where}: city files must set jurisdiction.city_slug == filename stem")
        if not re.fullmatch(r"[A-Z]{2}", str(j.get("state"))):
            errs.append(f"{where}: city files need jurisdiction.state")
    if not isinstance(doc["permits"], list) or not doc["permits"]:
        errs.append(f"{where}: permits must be a non-empty list")
        return errs
    for i, p in enumerate(doc["permits"]):
        errs += permit_errors(p, f"{where}#{i}")
    return errs


def main() -> int:
    files = sorted((ROOT / "data").rglob("*.json"))
    files = [f for f in files if f.name != "generic_city_checklist.json"]
    if not files:
        print(f"FAILED: no catalog files under {ROOT / 'data'} (is packages/catalog/data/ checked out?)")
        return 1
    all_permits: dict[str, dict] = {}
    errors: list[str] = []
    for path in files:
        try:
            doc = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            errors.append(f"{path}: invalid JSON: {e}")
            continue
        errors += file_errors(path, doc)
        for p in doc.get("permits", []):
            pid = p.get("id")
            if pid in all_permits:
                errors.append(f"{path}: duplicate id {pid!r} (also in {all_permits[pid]['_file']})")
            if pid:
                all_permits[pid] = {**p, "_file": str(path.relative_to(ROOT))}
    if errors:
        print("\n".join(errors))
        print(f"\nFAILED: {len(errors)} schema error(s)")
        return 1
    # Cross-file checks: prerequisites resolve, no cycles.
    for pid, p in all_permits.items():
        for pre in p["prerequisites"]:
            if pre not in all_permits:
                errors.append(f"{p['_file']}: {pid} requires unknown permit {pre!r}")
    if errors:
        print("\n".join(errors))
        print(f"\nFAILED: {len(errors)} unresolved prerequisite(s)")
        return 1
    state: dict[str, int] = {}

    def visit(node: str, stack: list[str]) -> None:
        if state.get(node) == 1:
            cycle = " -> ".join(stack[stack.index(node):] + [node])
            errors.append(f"dependency cycle: {cycle}")
            return
        if state.get(node) == 2:
            return
        state[node] = 1
        for pre in all_permits[node]["prerequisites"]:
            visit(pre, stack + [node])
        state[node] = 2

    for pid in all_permits:
        visit(pid, [])
    if errors:
        print("\n".join(errors))
        print(f"\nFAILED: {len(errors)} cycle(s)")
        return 1
    verified = sum(1 for p in all_permits.values() if p["confidence"] == "verified")
    print(f"OK: {len(files)} files, {len(all_permits)} permits ({verified} verified, {len(all_permits) - verified} estimated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
