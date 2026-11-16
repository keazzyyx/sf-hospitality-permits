"""Score the backtest results (docs/validation/backtest-plan.md §8) and write the summary and reviewer packets.

Four result sets per case: full report end to end (backtest/results/<case>/e2e/memo.json), full report
conditional (conditional/memo.json), rules only end to end (rules_only_e2e.json), rules only conditional
(rules_only_conditional.json). The measures are reported separately for each set, never as one score, and for
each group of cases: all, decided, did not reach approval, the cases with a licence of unknown status at the
address on the cut-off day (scored like every other case, and also shown as their own group), and the others.

  critical issues found / unknown / different control / missed
        one per item of the trigger inventory (what required the hearing at filing, two readings of the decision
        record), compared as scripts/validation/backtest_coverage.py `result_of` compares them. Found: the
        report's trigger for it asks what the record shows (`same_ask`: the same control, or both ask nothing).
        Unknown: the rules left it "not decided" and named what is missing. Different control: the trigger
        raised the item, with another control than the record's (conditional for not permitted, or the
        reverse); counted in its own row, not as missed. Missed: an item no rule covers, or a trigger that
        returned nothing or a control that asks nothing where the record shows one ("not returned"). A trigger
        reading "Code and Planning practice differ" is kept out of the share, in its own row.
        Plus, for the two cases whose file supports a regulatory problem outside the hearing triggers (N07,
        a Notice of Violation; N09 is a trigger), nothing is scored automatically: the reviewer packet asks.
  triggers raised outside the inventory
        every trigger that returns conditional or not permitted for something not an item of the case's
        inventory, listed per case (for the rules-only sets beside what coverage.json's own runs raised).
  missed pathways (end to end only)
        the zoning row against the correct pathway (cases.SETTLED / the inventory's net result at filing).
        "Insufficient information" on the zoning row is not a miss: it is counted in its own row. A row reading
        "Code and Planning practice differ" is kept out of the pass/fail count. A case whose correct pathway is
        "unclear" (N14) is right only when the zoning row says it cannot tell AND names the fact that decides it
        (`UNCLEAR_MUST_NAME`). In the conditional sets the zoning row is supplied from the decision record, so
        the pathway rows read "supplied" there.
  false blockers
        a "Potential blocker" or "Not permitted" row where the record shows none: a decided case whose correct
        pathway is not "not permitted", and the cases that did not reach approval only because no hearing was
        needed. Other cases that did not reach approval are not scored for this (the file does not say).
  materially unsafe cases (a case-level measure, beside the issue-level ones above)
        a case is materially unsafe in a result set when at least one critical issue of its inventory is missed
        (the result "missed": no rule, or not returned) or raised with a different control than the record's, or
        the case has a false blocker. A missed issue counts only when the record's control for it asks for
        something (conditional or not permitted): an issue the record shows as principally permitted or not
        applying (N15's change of operator, approved administratively) needed no hearing, so missing it does not
        make the case unsafe (it still counts as missed at the issue level). An issue listed as unknown, naming the
        missing input, does NOT make a case unsafe: the report says plainly that it cannot decide the issue and
        what it needs to know. Neither does a trigger kept out as "Code and Planning practice differ" (the report
        flags it). A missed pathway is not
        counted on its own (the summary lists any unsafe-free case with one). False blockers are scored only in
        the cases above, so in the others only a missed issue can make the case unsafe. Count and share of cases,
        per result set and per group.
  unsupported findings (full report only)
        from each cited sentence's outcome in verification.json (`ItemOutcome`): unsupported outright (the first
        check's verdict was "unsupported"); partly supported and cut down to the supported part; partly
        supported but the cut failed (the sentence lost its citation, or was removed); kept as written. The
        unsupported share is the first of these over the sentences checked. Over-claiming, reported per case:
        every sentence not kept as written, with the same breakdown.
  correct / wrong "Insufficient information"
        each missing input a row names: correct when the fact is not in what that run was given (end to end:
        the neutral text's facts and the intake answers; conditional: the decision record's facts), wrong
        when it is. The phrases are read through MISSING_PHRASES and, for the fixed phrases the rules and the
        runner name that are not inputs, `SCORE_PHRASES`. A phrase neither maps is listed as unmapped, and the
        run exits non-zero. In the conditional sets the zoning row is left out (it is supplied).
  facts the intake model assumed (full report, end to end)
        the model's profile (e2e/profile.json) against the profile the input facts and intake answers give:
        its own `assumptions`, and every field the rules read whose value differs, as assumed (the input does
        not state it) or misread (the input states something else).

    cd apps/api && .venv/bin/python -m app.backtest.score            # the 40: reads and writes backtest/results

Another case file (the holdout), scored the same way from the results its run wrote:

    cd apps/api && .venv/bin/python -m app.backtest.score --case-file ../../backtest/holdout/cases.yaml \
        --results-dir ../../backtest/holdout/results

--results-dir defaults to <the case file's folder>/results, where app.backtest.run writes another case file's
results. Another case file never reads from or writes into the 40's backtest/results: the scorer refuses.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from app.backtest.cases import BACKTEST, DEFAULT_CASE_FILE, Case, load_cases
from app.memo.facts import FACT_ALIASES, MISSING_PHRASES, profile_from_facts
from app.memo.intake import NO_ALCOHOL, apply_intake_answers, intake_answers
from app.memo.rows import EXISTING_GROUP_PHRASE
from app.memo.triggers import NOT_KNOWN

RESULTS = BACKTEST / "results"
FORTY_RESULTS = BACKTEST / "results"  # the 40's results: another case file never reads or writes here
SETS = ("full_e2e", "full_conditional", "rules_e2e", "rules_conditional")
SET_LABELS = {
    "full_e2e": "Full report, end to end",
    "full_conditional": "Full report, conditional",
    "rules_e2e": "Rules only, end to end",
    "rules_conditional": "Rules only, conditional",
}
BLOCKING = ("potential_blocker", "not_permitted")
NO_HEARING_NEEDED = ("allowed",)
# scripts/validation/backtest_coverage.py ASKS_NOTHING and RAISES
NO_ASK = frozenset({"principal", "does_not_apply"})
RAISES = frozenset({"conditional", "not_permitted"})
PRACTICE_NOTE = "Code and Planning practice differ"
# The issue results that make a case materially unsafe. "unknown" (listed as unknown, naming the missing input) and
# "practice_differs" do not: the report says it cannot decide, and what it needs.
UNSAFE_RESULTS = frozenset({"missed", "different_control"})
UNSAFE_DEFINITION_SHORT = "a critical issue missed or with a different control, or a false blocker"
UNSAFE_DEFINITION = (
    "A case is materially unsafe when the report misses at least one critical issue of the case (no rule for it, "
    "or the rules returned nothing or a control that asks nothing where the record shows one), raises one with a "
    "different control than the record's, or shows a false blocker. A missed issue counts only when the record's "
    "control for it asks for something (a Conditional Use, or not permitted): an issue the record shows as "
    "principally permitted or not applying needed no hearing, so missing it does not make a case unsafe (it still "
    "counts as missed among the issues). An issue listed as unknown, naming the "
    "missing input, does not make a case unsafe: the report says it cannot decide that issue and what it needs. "
    "Neither does a trigger reading 'Code and Planning practice differ'. False blockers are scored only where the "
    "record shows there was none (decided cases not 'not permitted', and cases closed because no hearing was "
    "needed); in other cases only a missed issue counts. A missed pathway is not counted on its own."
)
# The facts a zoning row that says it cannot tell must name for a case whose correct pathway is "unclear".
UNCLEAR_MUST_NAME: dict[str, frozenset[str]] = {"N14": frozenset({"formula_retail", "other_locations"})}

# The fixed phrases a row can name that are not in MISSING_PHRASES, by the start of the phrase (a template is
# matched up to its first field), and the fact each stands for in `fact_given`. (The chain phrase the conditional
# run supplies on an "unclear" zoning row, backtest/run.py, is MISSING_PHRASES["formula_retail"] and maps there.)
#   occupancy_group   the Building Code occupancy group of the space: never in any input, so always correct.
#   outdoor_limits    the § 202.2(a)(7) limits of an outdoor area. The rules ask only when no stated fact breaks
#                     a limit they read (a Bar use, a rooftop); the input settles it when it states a Bar use or
#                     a rooftop area the rules did not read. The other limits (hours of the outdoor area, seated
#                     only, who serves alcohol outside) have no input field.
#   use_not_covered   a rule gap, not a missing input: wrong whenever the input says what kind of business it is.
#   table_rows        whether the use is one of the named rows of the zoning table (e.g. a § 186 Limited
#                     Commercial Use): given when the stated text on the existing use names one of the rows.
SCORE_PHRASES: dict[str, str] = {
    EXISTING_GROUP_PHRASE: "occupancy_group",
    NOT_KNOWN["outdoor_limits"].split("{")[0]: "outdoor_limits",
    NOT_KNOWN["use_not_covered"]: "use_not_covered",
    NOT_KNOWN["table_rows"].split("{")[0]: "table_rows",
}

# The profile fields the rules read (facts.concept_facts and the rows), each with what states it: input_facts
# keys, and intake answers as "intake:<key>". A field with nothing listed is never stated by the input.
RULE_READ_FIELDS: dict[str, tuple[str, ...]] = {
    "business_type": ("business_type",),
    "serves_alcohol": ("serves_alcohol", "licence_type", "intake:liquor_licence"),
    "alcohol_type": ("licence_type", "serves_alcohol", "intake:liquor_licence"),
    "licence_type": ("licence_type",),
    "licences_held": ("licences_already_held",),
    "alcohol_transaction": ("alcohol_transaction", "intake:liquor_licence"),
    "formula_retail": ("formula_retail", "intake:part_of_chain"),
    "part_of_chain": ("intake:part_of_chain",),
    "other_locations": ("intake:other_locations",),
    "square_feet": ("floor_area_sqft", "intake:floor_area_sqft"),
    "floor_area_before_sqft": ("floor_area_before_sqft",),
    "seats": ("seats",),
    "occupants_under_50": ("occupants",),
    "existing_use_stated": ("existing_use_stated",),
    "changes_existing_business": ("changes_existing_business",),
    "merges_storefronts": ("merges_storefronts",),
    "amends_prior_approval": ("amends_prior_approval",),
    "stories": ("story",),
    "closing_hour": ("closing_hour",),
    "closes_after_midnight": ("closing_hour",),
    "closes_after_2am": ("closing_hour",),
    "entertainment_kind": ("entertainment_kind",),
    "live_entertainment": ("live_entertainment",),
    "amplified_sound": ("amplified_sound",),
    "dancing": (),
    "outdoor_area": ("outdoor_area",),
    "outdoor_seating": ("outdoor_area",),
    "sidewalk_or_parklet": ("outdoor_area",),
    "outdoor_alcohol_service": ("outdoor_alcohol_service",),
    "change_of_use": (),
    "new_construction": ("new_construction",),
}

Group = tuple[str, Callable[[Case], bool] | None]


def load_set(case: Case, which: str) -> dict[str, Any] | None:
    d = RESULTS / case.id
    path = {"full_e2e": d / "e2e" / "memo.json", "full_conditional": d / "conditional" / "memo.json",
            "rules_e2e": d / "rules_only_e2e.json", "rules_conditional": d / "rules_only_conditional.json"}[which]  # fmt: skip
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if which.startswith("full"):
        rows = [{"area": r["area"], "status": r["status"], "status_note": r.get("status_note"),
                 "missing_inputs": r.get("missing_inputs") or []} for r in data["approvals"]]  # fmt: skip
        pathway = data.get("pathway") or {}
        ver_path, profile_path = path.parent / "verification.json", path.parent / "profile.json"
        ver = json.loads(ver_path.read_text()) if ver_path.exists() else None
        profile = json.loads(profile_path.read_text()) if profile_path.exists() else None
        return {"rows": rows, "triggers": pathway.get("triggers") or [], "verification": ver, "memo": data,
                "profile": profile}  # fmt: skip
    det = data["determinations"]
    return {"rows": det["rows"], "triggers": det["pathway"].get("triggers") or [], "verification": None}


def phrase_key(phrase: str) -> str | None:
    for key, text in MISSING_PHRASES.items():
        if phrase.startswith(text) or text.startswith(phrase):
            return key
    for start, key in SCORE_PHRASES.items():
        if phrase.startswith(start):
            return key
    return None


def _values(v: Any) -> list[Any]:
    if v in (None, ""):
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


_ROW_NAME = re.compile(r"([A-Z][A-Za-z' -]+?) \(§")


def table_rows_named(phrase: str) -> list[str]:
    """The zoning-table rows a "table_rows" phrase names, singular ("Limited Commercial Use")."""
    rows = phrase.split(":", 1)[1] if ":" in phrase else ""
    return [m.group(1).strip().removesuffix("s") for m in _ROW_NAME.finditer(rows)]


def fact_given(key: str, facts: Mapping[str, Any], answers: Mapping[str, Any], phrase: str = "") -> bool:
    """Whether the run was given the fact a missing-input phrase names."""
    rev = {v: k for k, v in FACT_ALIASES.items()}
    if key == "occupancy_group":
        return False
    if key == "outdoor_limits":
        uses = _values(facts.get("planning_use")) + _values(facts.get("business_type"))
        return "bar" in uses or facts.get("outdoor_area") == "rooftop"
    if key == "use_not_covered":
        return facts.get("business_type") not in (None, "", "other")
    if key == "table_rows":
        text = str(facts.get("existing_use_text") or "").lower()
        return any(row.lower() in text for row in table_rows_named(phrase))
    if key == "existing_use_stated":
        # "vacant" says the space is empty, not what it was last used as
        return any(v != "vacant" for v in _values(facts.get("existing_use_stated")))
    if key == "alcohol_served":
        return facts.get("licence_type") is not None
    if key == "formula_retail":
        return facts.get("formula_retail") is not None or answers.get("part_of_chain") is not None
    if key == "other_locations":
        return answers.get("other_locations") is not None
    if key == "floor_area_sqft":
        return facts.get("floor_area_sqft") is not None or answers.get("floor_area_sqft") is not None
    if key == "alcohol_transaction":
        return facts.get("alcohol_transaction") is not None or answers.get("liquor_licence") is not None
    name = rev.get(key, key)
    v = facts.get(name)
    return v not in (None, [], "")


def same_ask(a: str | None, b: str | None) -> bool:
    """scripts/validation/backtest_coverage.py `same_ask`."""
    return a == b or (a in NO_ASK and b in NO_ASK)


def score_triggers(case: Case, triggers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each inventory item against the trigger the run returned, as backtest_coverage.py `result_of` reads it."""
    by_id = {t["rule_id"]: t for t in triggers}
    out = []
    for item in case.cov["inventory"]["items"]:
        want = item.get("control_at_filing")
        rid = item.get("trigger")
        got = by_id.get(rid) if rid else None
        control = got.get("control") if got else None
        if rid is None:
            result, why = "missed", f"no rule: {item.get('no_rule') or 'no rule for this trigger'}"
        elif control is None:
            result, why = (
                "missed",
                f"not returned: the rules returned nothing for {rid} where the record shows {want}",
            )
        elif same_ask(control, want):
            result, why = "found", ""
        elif control == "not_decided":
            result, why = "unknown", "; ".join((got or {}).get("missing_inputs") or []) or "not decided"
        elif control == "code_and_practice_differ":
            result, why = "practice_differs", "Code and Planning practice differ"
        elif control in RAISES and want in RAISES:
            result, why = "different_control", f"the rules returned {control} where the record shows {want}"
        else:
            result, why = (
                "missed",
                f"not returned: the rules returned {control} where the record shows {want}",
            )
        out.append({"item": item.get("label") or item["family"], "trigger": rid, "want": want, "got": control,
                    "result": result, "why": why, "basis": item.get("basis")})  # fmt: skip
    return out


def raised_outside(case: Case, triggers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The triggers that return conditional or not permitted for something not an item of the inventory."""
    items = {i.get("trigger") for i in case.cov["inventory"]["items"]}
    return [{"trigger": t["rule_id"], "label": t.get("label") or t.get("family"), "control": t["control"]}
            for t in triggers if t.get("control") in RAISES and t["rule_id"] not in items]  # fmt: skip


def coverage_raised(case: Case, which: str) -> list[str] | None:
    """What coverage.json's own run of the same facts raised outside the inventory (rules-only sets only)."""
    run = {"rules_e2e": "input_run", "rules_conditional": "record_run"}.get(which)
    if run is None:
        return None
    return [r["trigger"] for r in (case.cov.get(run) or {}).get("raised_outside_the_inventory") or []]


def verification_counts(ver: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The cited sentences by what the check did, from each outcome's first-pass verdict and result."""
    if not ver:
        return None
    c: Counter[str] = Counter()
    for o in ver.get("outcomes") or []:
        verdict, result = o.get("verdict"), o.get("result")
        if verdict is None or result == "not_checked":
            c["not_checked"] += 1
        elif verdict == "unsupported":
            c["unsupported"] += 1
        elif verdict == "partially_supported" and result == "trimmed":
            c["partly_cut"] += 1
        elif verdict == "partially_supported":
            c["partly_failed"] += 1
            c["partly_failed_" + ("removed" if result == "dropped" else "lost_citation")] += 1
        elif result == "kept":
            c["kept"] += 1
        else:  # a supported sentence not kept as written
            c["other"] += 1
    checked = sum(c[k] for k in ("unsupported", "partly_cut", "partly_failed", "kept", "other"))
    if not checked and not c["not_checked"]:
        return None
    return {
        "checked": checked,
        "unsupported": c["unsupported"],
        "partly_cut": c["partly_cut"],
        "partly_failed": c["partly_failed"],
        "partly_failed_lost_citation": c["partly_failed_lost_citation"],
        "partly_failed_removed": c["partly_failed_removed"],
        "kept": c["kept"],
        "other": c["other"],
        "not_checked": c["not_checked"],
        # None when no sentence got a first-pass verdict (every checker call failed)
        "unsupported_share": round(c["unsupported"] / checked, 3) if checked else None,
        "overclaim_share": round((checked - c["kept"]) / checked, 3) if checked else None,
    }


def expected_profile(case: Case) -> dict[str, Any]:
    """The profile the input facts and the intake answers give, as the runner builds it (no model)."""
    p = profile_from_facts(case.input_facts)
    if case.intake_answers:
        p = apply_intake_answers(p, intake_answers(case.intake_answers))
    return p.normalized().model_dump(mode="json")


def _stated(source: str, facts: Mapping[str, Any], answers: Mapping[str, Any]) -> bool:
    if source.startswith("intake:"):
        return answers.get(source.removeprefix("intake:")) is not None
    return facts.get(source) not in (None, [], "")


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        return sorted(map(str, a)) == sorted(map(str, b))
    return bool(a == b)


def intake_check(case: Case, profile: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The intake model's profile against the input: its assumptions, and each rule-read field that differs."""
    if profile is None:
        return None
    want = expected_profile(case)
    facts, answers = case.input_facts, case.intake_answers
    assumed: list[dict[str, Any]] = []
    misread: list[dict[str, Any]] = []
    for name, sources in RULE_READ_FIELDS.items():
        got, exp = profile.get(name), want.get(name)
        if _same(got, exp):
            continue
        stated = exp not in (None, [], "unknown") and any(_stated(s, facts, answers) for s in sources)
        # a no-alcohol answer states what is poured as much as a licence type does
        if name == "alcohol_type" and answers.get("liquor_licence") == NO_ALCOHOL:
            stated = True
        (misread if stated else assumed).append({"field": name, "input": exp, "model": got})
    # what the stated-facts check cleared from the model's profile (app.memo.stated); absent before 2026-11-12
    cleared = dict(profile.get("intake_cleared") or {})
    return {"assumptions": list(profile.get("assumptions") or []), "assumed": assumed, "misread": misread,
            "cleared": cleared}  # fmt: skip


def unsafe_case(triggers: list[dict[str, Any]], false_blockers: list[str]) -> dict[str, Any]:
    """Whether one case is materially unsafe in one result set: at least one critical issue missed or raised with a
    different control, or a false blocker. An issue listed as unknown (naming the missing input) does not count, and
    neither does a missed issue whose record control asks nothing (principal, does_not_apply)."""
    issues = [t["item"] for t in triggers if t["result"] in UNSAFE_RESULTS and t.get("want") in RAISES]
    return {
        "unsafe": bool(issues or false_blockers),
        "issues": issues,
        "false_blockers": list(false_blockers),
    }


def score_set(case: Case, which: str, data: dict[str, Any]) -> dict[str, Any]:
    rows = {r["area"]: r for r in data["rows"]}
    z = rows.get("zoning_use", {})
    want = case.expected_zoning
    zs, note = z.get("status"), z.get("status_note")
    e2e = which.endswith("e2e")
    if not e2e:
        pathway = "supplied"
    elif note and PRACTICE_NOTE in note:
        pathway = "practice_differs"
    elif want == "unclear":
        named = {phrase_key(p) for p in z.get("missing_inputs") or []}
        pathway = (
            "right" if zs == "insufficient_information" and named & UNCLEAR_MUST_NAME[case.id] else "missed"
        )
    elif zs == want:
        pathway = "right"
    elif zs == "insufficient_information":
        pathway = "unknown"
    else:
        pathway = "missed"
    scorable_blockers = (case.group == "decided" and want != "not_permitted") or (
        case.group != "decided" and want in NO_HEARING_NEEDED
    )
    blockers = [r["area"] for r in data["rows"] if r["status"] in BLOCKING]
    false_blockers = blockers if scorable_blockers else []
    facts, answers = (case.input_facts, case.intake_answers) if e2e else (case.record_facts, {})
    ii = []
    for r in data["rows"]:
        if r["status"] != "insufficient_information" or (not e2e and r["area"] == "zoning_use"):
            continue
        for phrase in r.get("missing_inputs") or []:
            key = phrase_key(phrase)
            given = fact_given(key, facts, answers, phrase) if key else None
            ii.append({"row": r["area"], "missing": phrase, "fact": key,
                       "result": "unmapped" if key is None else ("wrong" if given else "correct")})  # fmt: skip
    triggers = score_triggers(case, data["triggers"])
    return {
        "pathway": pathway,
        "zoning_status": zs,
        "expected": want,
        "statuses": {a: r["status"] for a, r in rows.items()},
        "false_blockers": false_blockers,
        "blockers_unscored": [] if scorable_blockers else blockers,
        "unsafe": unsafe_case(triggers, false_blockers),
        "triggers": triggers,
        "raised_outside": raised_outside(case, data["triggers"]),
        "insufficient": ii,
        "verification": verification_counts(data.get("verification")),
        "intake": intake_check(case, data.get("profile")) if which == "full_e2e" else None,
    }


def leakage(case: Case) -> dict[str, Any]:
    path = RESULTS / case.id / "leakage.json"
    data: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {}
    return data


def unknown_licences(case: Case) -> int:
    """How many licences tied to the case's own address (or parcel) have a status on the cut-off day that is not
    in ABC's archive (leakage.json `licences_unknown_at_the_address`, however the runner matched them)."""
    return len(leakage(case).get("licences_unknown_at_the_address") or [])


def unknown_at_address(case: Case) -> bool:
    return unknown_licences(case) > 0


def unknown_group_label(cases: tuple[Case, ...]) -> str:
    gap = [c for c in cases if unknown_at_address(c)]
    n = len(gap)
    m = sum(unknown_licences(c) for c in gap)
    return f"{n} case{'s' if n != 1 else ''} ({m} licence{'s' if m != 1 else ''})"


# The line backtest/asof.py adds to the alcohol row naming the licences of unknown status that day. It differs
# between the two runs by construction, so the reasoning-text comparison leaves it out.
DISCLOSURE_LINE = "Licences with an unknown status on "
SENSITIVITY_RUNS = (("end to end", "rules_only_e2e.json", "e2e"),
                    ("conditional", "rules_only_conditional.json", "conditional"))  # fmt: skip


def _joined(items: Any) -> str:
    return "; ".join(str(i) for i in items) or "none"


def sensitivity_changes(case: Case) -> dict[str, list[dict[str, Any]]] | None:
    """What reads differently in the rules-only runs once every licence of unknown status is counted as active
    (sensitivity_unknown_as_active.json against rules_only_*.json), or None when the case has no such file.

    `answer`: a trigger whose control differs, or a row whose status, missing inputs or status note differs; each
    with what it was with the licences left out and with them counted as active. `text`: a row whose answer is the
    same but whose reasoning lines differ (the disclosure line of the unknown licences left out)."""
    path = RESULTS / case.id / "sensitivity_unknown_as_active.json"
    if not path.exists():
        return None
    alt = json.loads(path.read_text())
    inventory = {i.get("trigger") for i in case.cov["inventory"]["items"]}
    answer: list[dict[str, Any]] = []
    text: list[dict[str, Any]] = []
    for run, base_file, key in SENSITIVITY_RUNS:
        base = json.loads((RESULTS / case.id / base_file).read_text())["determinations"]
        other = alt[key]
        bt = {t["rule_id"]: t for t in (base.get("pathway") or {}).get("triggers") or []}
        at = {t["rule_id"]: t for t in (other.get("pathway") or {}).get("triggers") or []}
        for rid in sorted(set(bt) | set(at)):
            b, a = (bt.get(rid) or {}).get("control"), (at.get(rid) or {}).get("control")
            if b != a:
                label = (bt.get(rid) or at.get(rid) or {}).get("label") or rid
                answer.append({"run": run, "kind": "trigger", "name": f"{rid} {label}", "what": "control",
                               "inventory": rid in inventory, "left_out": b or "-", "active": a or "-"})  # fmt: skip
        br = {r["area"]: r for r in base.get("rows") or []}
        ar = {r["area"]: r for r in other.get("rows") or []}
        for area in sorted(set(br) | set(ar)):
            b_row, a_row = br.get(area) or {}, ar.get(area) or {}
            changed = False

            def add(what: str, left: str, active: str, run: str = run, area: str = area) -> None:
                answer.append({"run": run, "kind": "row", "name": area, "what": what, "inventory": False,
                               "left_out": left, "active": active})  # fmt: skip

            if b_row.get("status") != a_row.get("status"):
                changed = True
                add("status", b_row.get("status") or "-", a_row.get("status") or "-")
            bm, am = b_row.get("missing_inputs") or [], a_row.get("missing_inputs") or []
            if set(bm) != set(am):
                changed = True
                add(
                    "missing inputs",
                    _joined(m for m in bm if m not in am),
                    _joined(m for m in am if m not in bm),
                )
            if (b_row.get("status_note") or None) != (a_row.get("status_note") or None):
                changed = True
                add("status note", b_row.get("status_note") or "none", a_row.get("status_note") or "none")
            if not changed:

                def lines(row: Mapping[str, Any]) -> list[str]:
                    return [
                        ln["text"]
                        for ln in row.get("basis") or []
                        if not ln["text"].startswith(DISCLOSURE_LINE)
                    ]

                bl, al = lines(b_row), lines(a_row)
                if bl != al:
                    n = max(sum(t not in al for t in bl), sum(t not in bl for t in al))
                    text.append({"run": run, "row": area, "lines": n})
    return {"answer": answer, "text": text}


def sensitivity(cases: tuple[Case, ...]) -> list[str]:
    """Whether leaving out the licences of unknown status changed an answer: the rules-only runs again with every
    such licence counted as active (backtest/results/<case>/sensitivity_unknown_as_active.json). An answer is a
    trigger's control, or a row's status, missing inputs or status note. A case with no such file is listed as not
    run, never counted as unchanged."""
    out = ["## Licences of unknown status on the cut-off day: did leaving them out change an answer?", "",
           "Rules only, end to end and conditional, recomputed with every licence whose status that day is not in "
           "ABC's archive counted as active. An answer changes when a trigger's control, or a row's status, "
           "missing inputs or status note, reads differently under that assumption; each such difference is a "
           "line below. A checked case not listed reads the same.", "",
           "| Case | Unknown within 1,000 ft (at the address) | Run | Trigger or row | What | Left out | Counted as active |",
           "|---|---|---|---|---|---|---|"]  # fmt: skip
    checked: list[Case] = []
    changed: list[Case] = []
    text_only: list[tuple[Case, dict[str, Any]]] = []
    kinds: Counter[str] = Counter()
    for c in cases:
        ch = sensitivity_changes(c)
        if ch is None:
            continue
        checked.append(c)
        lk = leakage(c)
        n, here = lk.get("licences_unknown_within_1000ft", 0), unknown_licences(c)
        for d in ch["answer"]:
            if d["kind"] == "trigger":
                where = "inventory" if d["inventory"] else "outside the inventory"
                name, kind = f"trigger {d['name']} ({where})", f"trigger controls ({where})"
            else:
                name, kind = f"row {d['name']}", f"row {d['what']}"
            kinds[kind] += 1
            out.append(f"| {c.id} | {n} ({here}) | {d['run']} | {name} | {d['what']} | {d['left_out']} | "
                       f"{d['active']} |")  # fmt: skip
        if ch["answer"]:
            changed.append(c)
        text_only += [(c, t) for t in ch["text"]]
    gap = [c for c in cases if unknown_at_address(c)]
    not_run = [c for c in cases if c not in checked]
    out += ["", f"Checked {len(checked)} of {len(cases)} cases; an answer changes in {len(changed)} of them"
            + (f" ({', '.join(c.id for c in changed)})." if changed else "."),
            f"Unknown-status group ({unknown_group_label(cases)}): checked {sum(c in checked for c in gap)} of "
            f"{len(gap)}; an answer changes in {sum(c in changed for c in gap)}"
            + (f" ({', '.join(c.id for c in changed if c in gap)})." if any(c in gap for c in changed) else "."),
            f"All other cases: checked {sum(c in checked and c not in gap for c in cases)} of "
            f"{len(cases) - len(gap)}; an answer changes in {sum(c not in gap for c in changed)}.",
            "", "| Differences (lines above) | Count |", "|---|---|"]  # fmt: skip
    for kind in ("trigger controls (inventory)", "trigger controls (outside the inventory)", "row status",
                 "row missing inputs", "row status note"):  # fmt: skip
        out.append(f"| {kind} | {kinds[kind]} |")
    text_cases = sorted({c.id for c, _ in text_only})
    out += ["", "Same answer, different reasoning: rows whose status, missing inputs and status note are the "
            "same but whose lines read differently (e.g. the licence counts of the alcohol row), leaving out the "
            f"line that names the unknown licences. {len(text_only)} rows in {len(text_cases)} cases.", "",
            "| Case | Run | Row | Lines that differ |", "|---|---|---|---|"]  # fmt: skip
    for c, t in text_only:
        out.append(f"| {c.id} | {t['run']} | {t['row']} | {t['lines']} |")
    out += ["", "| Not run (no sensitivity file) | Cases |", "|---|---|",
            f"| unknown-status group | {', '.join(c.id for c in not_run if c in gap) or 'none'} |",
            f"| other cases | {', '.join(c.id for c in not_run if c not in gap) or 'none'} |", ""]  # fmt: skip
    return out


def restatement_section(cases: tuple[Case, ...], scores: Mapping[str, Any]) -> list[str]:
    """The over-claiming share again, without the sentences that only restate the rules' own lines (the citation
    check is not shown a finding's rule lines; backtest/results/restatements.json, app.backtest.restatements)."""
    path = RESULTS / "restatements.json"
    if not path.exists():
        return ["## Over-claiming without restatements of the rule lines", "", "Not run yet.", ""]
    data = json.loads(path.read_text())
    by: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for r in data["rows"]:
        by[(r["case"], r["run"])][r["in_rule_lines"] or "no answer"] += 1
    out = ["## Over-claiming without restatements of the rule lines", "",
           f"Each cited sentence not kept as written was compared with its row's rule lines ({data['model']}, "
           f"{data['answered']} of {data['sentences']} sentences, ${data['cost_usd']:.2f}). 'All in the rule lines': "
           "the sentence only restates what the rules printed, so its cut or removal says nothing about the writer.", "",
           "| Set | Checked | Not kept as written | of which all in the rule lines | part | Over-claim | Over-claim without full restatements |",
           "|---|---|---|---|---|---|---|"]  # fmt: skip
    for which, run in (("full_e2e", "e2e"), ("full_conditional", "conditional")):
        checked = not_kept = full = part = 0
        for c in cases:
            v = (scores[c.id][which] or {}).get("verification")
            if not v:
                continue
            checked += v["checked"]
            not_kept += v["checked"] - v["kept"]
            k = by.get((c.id, run), Counter())
            full += k["all"]
            part += k["part"]
        if checked:
            out.append(f"| {SET_LABELS[which]} | {checked} | {not_kept} | {full} | {part} | {not_kept / checked:.0%} | "
                       f"{(not_kept - full) / checked:.0%} |")  # fmt: skip
    out.append("")
    return out


def harder(case: Case) -> str:
    """How hard the case is for the report, from what is on file before running it: the rule coverage of its
    triggers on the record's facts, and how many triggers it has."""
    n = len(case.cov["inventory"]["items"])
    return f"{case.coverage or 'unknown'} covered, {n} trigger{'s' if n != 1 else ''}"


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "0/0"


def unmapped_phrases(scores: Mapping[str, Mapping[str, Any]]) -> list[tuple[str, str, str, str]]:
    """Every (case, set, row, phrase) whose missing input maps to no fact."""
    out = []
    for cid, per in scores.items():
        for which in SETS:
            s = per.get(which)
            for i in (s or {}).get("insufficient") or []:
                if i["result"] == "unmapped":
                    out.append((cid, which, i["row"], i["missing"]))
    return out


def _shown(path: Path) -> str:
    """A path as the summary prints it: from the repository root when it is inside it."""
    try:
        return str(path.resolve().relative_to(BACKTEST.parent.resolve()))
    except ValueError:
        return str(path)


def results_dir_for(case_file: Path | None, results_dir: Path | None) -> Path | None:
    """Where another case file's results are read and its scores written: --results-dir, else <the case file's
    folder>/results (where app.backtest.run writes them). None for the 40 with no --results-dir (keep RESULTS).
    Another case file never reads from or writes into the 40's backtest/results."""
    default = case_file is None or case_file.resolve() == DEFAULT_CASE_FILE.resolve()
    if results_dir is not None:
        out = results_dir.resolve()
    elif default:
        return None
    else:
        assert case_file is not None
        out = case_file.resolve().parent / "results"
    if not default and out == FORTY_RESULTS.resolve():
        raise SystemExit(
            f"refusing: {case_file} is not the 40; its scores never go into the 40's results ({FORTY_RESULTS})"
        )
    return out


def main(argv: Sequence[str] | None = None) -> int:
    """Score one case file. RESULTS is set for this call only and put back afterwards, so a later call in the same
    process (the 40 with no --results-dir) never reads from or writes into an earlier call's folder."""
    global RESULTS
    before = RESULTS
    try:
        return _main(argv)
    finally:
        RESULTS = before


def _main(argv: Sequence[str] | None) -> int:
    global RESULTS
    p = argparse.ArgumentParser(prog="python -m app.backtest.score")
    p.add_argument("--case-file", type=Path, default=None,
                   help="the cases to score (default backtest/cases.yaml, the 40); e.g. backtest/holdout/cases.yaml")  # fmt: skip
    p.add_argument("--results-dir", type=Path, default=None,
                   help="the run results to read and where the scores go (default backtest/results for the 40, "
                   "<the case file's folder>/results for another case file)")  # fmt: skip
    args = p.parse_args(list(argv or []))
    out = results_dir_for(args.case_file, args.results_dir)
    if out is not None:
        if not out.is_dir():
            print(f"no results directory {out}", file=sys.stderr)
            return 2
        RESULTS = out
    cases = load_cases(args.case_file)
    scores: dict[str, dict[str, Any]] = {}
    for c in cases:
        per: dict[str, Any] = {}
        for which in SETS:
            data = load_set(c, which)
            per[which] = score_set(c, which, data) if data else None
        scores[c.id] = per
    (RESULTS / "scores.json").write_text(json.dumps(scores, indent=1) + "\n")
    source = "backtest/results/" if out is None else f"{_shown(out)}/"
    md = summary(cases, scores, source)
    (RESULTS / "summary.md").write_text(md)
    for c in cases:
        packet(c, scores[c.id])
    print(md)
    unmapped = unmapped_phrases(scores)
    if unmapped:
        print(
            f"{len(unmapped)} missing-input phrase(s) map to no fact; add them to SCORE_PHRASES:",
            file=sys.stderr,
        )
        for cid, which, row, phrase in unmapped:
            print(f"  {cid} {which} {row}: {phrase}", file=sys.stderr)
        return 1
    return 0


def totals(
    cases: tuple[Case, ...], scores: dict[str, Any], which: str, only: Callable[[Case], bool] | None = None
) -> dict[str, Any]:
    t: Counter[str] = Counter()
    ran = 0
    for c in cases:
        s = scores[c.id][which]
        if s is None or (only and not only(c)):
            continue
        ran += 1
        t["pathway_" + s["pathway"]] += 1
        t["false_blockers"] += len(s["false_blockers"])
        t["cases_with_false_blocker"] += bool(s["false_blockers"])
        u = s.get("unsafe") or unsafe_case(s["triggers"], s["false_blockers"])
        t["unsafe_cases"] += u["unsafe"]
        t["unsafe_issue_cases"] += bool(u["issues"])
        t["unsafe_blocker_cases"] += bool(u["false_blockers"])
        t["raised_outside"] += len(s["raised_outside"])
        t["cases_raised_outside"] += bool(s["raised_outside"])
        for tr in s["triggers"]:
            t["crit_" + tr["result"]] += 1
        for i in s["insufficient"]:
            t["ii_" + i["result"]] += 1
        if v := s["verification"]:
            for k in (
                "checked",
                "unsupported",
                "partly_cut",
                "partly_failed",
                "kept",
                "other",
                "not_checked",
            ):
                t["v_" + k] += v[k]
        if ic := s.get("intake"):
            t["intake_cases"] += 1
            t["intake_assumptions"] += len(ic["assumptions"])
            t["intake_assumed"] += len(ic["assumed"])
            t["intake_misread"] += len(ic["misread"])
    return {"ran": ran, **t}


def groups_of(cases: tuple[Case, ...]) -> list[Group]:
    n_dec = sum(c.group == "decided" for c in cases)
    n_gap = sum(unknown_at_address(c) for c in cases)
    return [
        (f"all ({len(cases)})", None),
        (f"decided ({n_dec})", lambda c: c.group == "decided"),
        (f"did not reach approval ({len(cases) - n_dec})", lambda c: c.group != "decided"),
        (f"licence status unknown at the address: {unknown_group_label(cases)}", unknown_at_address),
        (f"all other cases ({len(cases) - n_gap})", lambda c: not unknown_at_address(c)),
    ]


def measure_table(cases: tuple[Case, ...], scores: dict[str, Any], which: str) -> list[str]:
    groups = groups_of(cases)
    lines = [f"## {SET_LABELS[which]}", ""]
    ts = [totals(cases, scores, which, f) for _, f in groups]
    if not ts[0]["ran"]:
        return [*lines, "Not run.", ""]
    lines += ["| Measure | " + " | ".join(g for g, _ in groups) + " |", "|---|" + "---|" * len(groups)]

    def row(label: str, fn: Callable[[dict[str, Any]], str]) -> None:
        lines.append(f"| {label} | " + " | ".join(fn(t) for t in ts) + " |")

    def n(key: str) -> Callable[[dict[str, Any]], str]:
        return lambda t: str(t.get(key, 0))

    supplied = not which.endswith("e2e")
    row("Cases run", n("ran"))
    crit = ("crit_found", "crit_unknown", "crit_different_control", "crit_missed")
    row("Critical issues found", lambda t: pct(t.get("crit_found", 0), sum(t.get(k, 0) for k in crit)))
    row("Critical issues listed as unknown (named missing input)", n("crit_unknown"))
    row("Critical issues raised with a different control", n("crit_different_control"))
    row("Critical issues missed (no rule, or not returned)", n("crit_missed"))
    row(
        f"Materially unsafe cases ({UNSAFE_DEFINITION_SHORT})",
        lambda t: pct(t.get("unsafe_cases", 0), t["ran"]),
    )
    row("Unsafe: a critical issue missed or with a different control (cases)", n("unsafe_issue_cases"))
    row("Unsafe: a false blocker (cases)", n("unsafe_blocker_cases"))
    row("Kept out: trigger reads Code and practice differ", n("crit_practice_differs"))
    row(
        "Triggers raised outside the inventory",
        lambda t: f"{t.get('raised_outside', 0)} in {t.get('cases_raised_outside', 0)} cases",
    )
    for label, key in (("Pathway right", "pathway_right"), ("Missed pathways", "pathway_missed"),
                       ("Zoning row 'Insufficient information'", "pathway_unknown"),
                       ("Kept out: zoning row reads Code and practice differ", "pathway_practice_differs")):  # fmt: skip
        row(label, (lambda t: "supplied") if supplied else n(key))
    row(
        "False blockers (rows)",
        lambda t: f"{t.get('false_blockers', 0)} in {t.get('cases_with_false_blocker', 0)} cases",
    )
    scope = " (zoning row left out: supplied)" if supplied else ""
    row(f"Correct 'Insufficient information'{scope}", n("ii_correct"))
    row(f"Wrong 'Insufficient information'{scope}", n("ii_wrong"))
    row("Unmapped missing-input phrases", n("ii_unmapped"))
    if which.startswith("full"):

        def share(*keys: str) -> Callable[[dict[str, Any]], str]:
            # n/a when no sentence was checked: a report with no model-written sentence
            return lambda t: (
                pct(sum(t.get("v_" + k, 0) for k in keys), t["v_checked"]) if t.get("v_checked") else "n/a"
            )

        row("Cited sentences checked", n("v_checked"))
        row("Unsupported findings (unsupported outright)", share("unsupported"))
        row("Partly supported, cut down", share("partly_cut"))
        row("Partly supported, cut failed (lost citation or removed)", share("partly_failed"))
        row("Supported, not kept as written", share("other"))
        row("Kept as written", share("kept"))
        row(
            "Over-claiming (not kept as written)",
            share("unsupported", "partly_cut", "partly_failed", "other"),
        )
        row("Not checked (no first-pass verdict; not in the shares above)", n("v_not_checked"))
    else:
        row("Unsupported findings", lambda t: "n/a (no model text)")
    if which == "full_e2e":
        row("Intake: assumptions the model listed", n("intake_assumptions"))
        row("Intake: rule-read facts assumed (not in the input)", n("intake_assumed"))
        row("Intake: rule-read facts misread (input says otherwise)", n("intake_misread"))
    return [*lines, ""]


def unsafe_section(cases: tuple[Case, ...], scores: dict[str, Any]) -> list[str]:
    """The materially unsafe cases: count and share per result set and group, beside the critical issues found,
    then every unsafe case with what made it so, and any case with a missed pathway that is not unsafe."""
    groups = groups_of(cases)
    out = ["## Materially unsafe cases, each result set", "", UNSAFE_DEFINITION, "",
           "Each cell: unsafe cases of the cases run; then critical issues found, for comparison.", "",
           "| Group | " + " | ".join(SET_LABELS[w] for w in SETS) + " |", "|---|" + "---|" * len(SETS)]  # fmt: skip
    crit = ("crit_found", "crit_unknown", "crit_different_control", "crit_missed")
    for label, only in groups:
        cells = []
        for which in SETS:
            t = totals(cases, scores, which, only)
            if not t["ran"]:
                cells.append("not run")
                continue
            found = pct(t.get("crit_found", 0), sum(t.get(k, 0) for k in crit))
            cells.append(f"unsafe {pct(t.get('unsafe_cases', 0), t['ran'])}; issues found {found}")
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    out += ["", "| Case | Set | Missed or with a different control | False blocker |", "|---|---|---|---|"]
    for c in cases:
        for which in SETS:
            s = scores[c.id][which]
            u = (s or {}).get("unsafe")
            if not u or not u["unsafe"]:
                continue
            out.append(f"| {c.id} | {SET_LABELS[which]} | {'; '.join(u['issues']) or 'none'} | "
                       f"{', '.join(u['false_blockers']) or 'none'} |")  # fmt: skip
    safe_missed = [(c.id, SET_LABELS[w]) for c in cases for w in SETS
                   if scores[c.id][w] and scores[c.id][w]["pathway"] == "missed"
                   and not scores[c.id][w]["unsafe"]["unsafe"]]  # fmt: skip
    out += ["", "Cases with a missed pathway that are not counted as unsafe: "
            + ("; ".join(f"{cid} ({label})" for cid, label in safe_missed) or "none") + ".", ""]  # fmt: skip
    return out


def summary(cases: tuple[Case, ...], scores: dict[str, Any], source: str = "backtest/results/") -> str:
    lines: list[str] = ["# Backtest results", ""]
    lines += [f"Generated by `python -m app.backtest.score` from `{source}`. Every measure is reported "
              "separately for each of the four result sets; there is no combined score. The cases with a "
              "licence of unknown status at the address are scored like every other case and also shown as "
              "their own group.", ""]  # fmt: skip
    for which in SETS:
        lines += measure_table(cases, scores, which)
    lines += unsafe_section(cases, scores)
    lines += sensitivity(cases)
    # critical misses and different controls
    lines += ["## Every critical miss and different control", "", "| Case | Set | Result | Issue | Why |",
              "|---|---|---|---|---|"]  # fmt: skip
    for c in cases:
        for which in SETS:
            s = scores[c.id][which]
            if s is None:
                continue
            for tr in s["triggers"]:
                if tr["result"] in ("missed", "different_control"):
                    result = tr["result"].replace("_", " ")
                    lines.append(f"| {c.id} | {SET_LABELS[which]} | {result} | {tr['item']} | {tr['why']} |")
            if s["pathway"] == "missed":
                lines.append(f"| {c.id} | {SET_LABELS[which]} | missed | pathway: zoning row {s['zoning_status']}, "
                             f"record shows {c.expected_zoning} | {c.expected_note} |")  # fmt: skip
            for fb in s["false_blockers"]:
                lines.append(f"| {c.id} | {SET_LABELS[which]} | false blocker | {fb} row {s['statuses'][fb]} | "
                             f"the record shows the case {c.outcome} |")  # fmt: skip
    lines.append("")
    # raised outside the inventory
    lines += ["## Triggers raised outside the inventory", "",
              "A trigger that returns conditional or not permitted for something the case's inventory does not "
              "list. For the rules-only sets, coverage.json's own run of the same facts (input_run, record_run).",
              "", "| Case | Set | Raised (control) | coverage.json |", "|---|---|---|---|"]  # fmt: skip
    for c in cases:
        for which in SETS:
            s = scores[c.id][which]
            cov = coverage_raised(c, which)
            if s is None or not (s["raised_outside"] or cov):
                continue
            raised = ", ".join(f"{r['trigger']} {r['label']} ({r['control']})" for r in s["raised_outside"])
            lines.append(f"| {c.id} | {SET_LABELS[which]} | {raised or 'none'} | "
                         f"{'-' if cov is None else ', '.join(cov) or 'none'} |")  # fmt: skip
    lines.append("")
    # what the intake model assumed
    lines += ["## Facts the intake model assumed (full report, end to end)", "",
              "The model's profile (e2e/profile.json) against the profile the input facts and intake answers give. "
              "Assumed: the input does not state the fact. Misread: the input states something else.", "",
              "| Case | Assumptions it listed | Rule-read facts assumed | Rule-read facts misread |",
              "|---|---|---|---|"]  # fmt: skip

    def facts_cell(fs: list[dict[str, Any]]) -> str:
        return "; ".join(f"{f['field']}: {f['input']!r} -> {f['model']!r}" for f in fs) or "none"

    for c in cases:
        ic = (scores[c.id]["full_e2e"] or {}).get("intake")
        if ic:
            lines.append(f"| {c.id} | {'; '.join(ic['assumptions']) or 'none'} | {facts_cell(ic['assumed'])} | "
                         f"{facts_cell(ic['misread'])} |")  # fmt: skip
    lines.append("")
    # over-claiming by case
    lines += ["## The writer's over-claiming, per case", "",
              "Cited sentences not kept as written, by what the citation check found: unsupported outright; partly "
              "supported and cut down; partly supported with the cut failed (lost the citation, or removed); "
              "supported but not kept as written. The four add up to 'Not kept as written'. Not checked: the first "
              "pass gave no verdict (a failed checker call), outside 'Checked'. By the case's difficulty: rule "
              "coverage on the record's facts and number of triggers.", "",
              "| Case | Difficulty | Group | Set | Checked | Unsupported | Partly, cut | Partly, cut failed (lost / removed) | Supported, not kept | Kept | Not kept as written | Not checked |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    by_diff: dict[str, list[float]] = defaultdict(list)
    for c in cases:
        for which in ("full_e2e", "full_conditional"):
            v = (scores[c.id][which] or {}).get("verification")
            if not v:
                continue
            share = v["overclaim_share"]
            if which == "full_e2e" and share is not None:
                by_diff[c.coverage or "unknown"].append(share)
            failed = (
                f"{v['partly_failed']} ({v['partly_failed_lost_citation']} / {v['partly_failed_removed']})"
            )
            not_kept = f"{v['checked'] - v['kept']} ({'n/a' if share is None else f'{share:.0%}'})"
            lines.append(f"| {c.id} | {harder(c)} | {c.group.replace('_', ' ')} | {SET_LABELS[which]} | "
                         f"{v['checked']} | {v['unsupported']} | {v['partly_cut']} | {failed} | {v['other']} | "
                         f"{v['kept']} | {not_kept} | {v['not_checked']} |")  # fmt: skip
    lines += ["", "| Rule coverage | Cases | Mean over-claim (end to end) |", "|---|---|---|"]
    for d, vals in sorted(by_diff.items()):
        lines.append(f"| {d} | {len(vals)} | {statistics.mean(vals):.0%} |")
    lines.append("")
    lines += restatement_section(cases, scores)
    # timing, by outcome, never blended
    lines += ["## Days from filing, by outcome (the decision records)", "", "| Outcome | Cases | Median days | Range |",
              "|---|---|---|---|"]  # fmt: skip
    days: dict[str, list[int]] = defaultdict(list)
    for c in cases:
        closed = c.yaml.get("closed") or c.yaml.get("decided")
        if closed:
            days[c.outcome].append((dt.date.fromisoformat(str(closed)) - c.filed).days)
    for o, ds in sorted(days.items()):
        lines.append(f"| {o} | {len(ds)} | {statistics.median(ds):.0f} | {min(ds)} to {max(ds)} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def packet(c: Case, s: dict[str, Any]) -> None:
    """A reviewer packet per case: the ground truth, what each run said, and a blank grading sheet."""
    lines = [f"# {c.id}: {c.address}", "",
             f"Record {c.record}, filed {c.filed}, {c.outcome}. Rules date {c.rules_date}.", "",
             "## Ground truth (decision record)", "",
             f"- Correct pathway: **{c.expected_zoning}** ({c.expected_note})",
             f"- Rule coverage on the record's facts: {c.coverage}",
             f"- Why closed: {c.yaml.get('why_closed') or 'decided'}",
             f"- Regulatory problem: {c.yaml.get('regulatory_problem', 'n/a')}",
             f"- Concept as filed (not given to the report): {c.yaml.get('concept_as_filed')}",
             f"- Concept given to the report: {c.concept_input}",
             f"- Intake answers given: {json.dumps(c.intake_answers) if c.intake_answers else 'none'}",
             "", "Triggers:", ""]  # fmt: skip
    for i in c.cov["inventory"]["items"]:
        lines.append(
            f"- {i.get('label') or i['family']}: {i.get('control_at_filing')} at filing ({i.get('basis')})"
        )
    lines += ["", "## What each run said", "", "| | " + " | ".join(SET_LABELS[w] for w in SETS) + " |",
              "|---|" + "---|" * len(SETS)]  # fmt: skip
    areas = sorted({a for w in SETS if s[w] for a in s[w]["statuses"]})
    for a in areas:
        lines.append(
            f"| {a} | "
            + " | ".join((s[w]["statuses"].get(a, "-") if s[w] else "not run") for w in SETS)
            + " |"
        )
    lines += ["", "In the conditional runs the zoning row is supplied from the decision record.", "",
              "Files: `e2e/memo.pdf`, `conditional/memo.pdf`, `rules_only_e2e.json`, `rules_only_conditional.json`, "
              "`leakage.json`.", "", "## Grading sheet (for a permit professional)", "",
              "| Question | Full, end to end | Full, conditional |", "|---|---|---|",
              "| Did the report flag every issue that made the use impossible, forced the pathway, led to withdrawal or "
              "imposed a concept-changing condition? Which did it miss? | | |",
              "| Any finding the cited record does not support? | | |",
              "| Any blocker that was not one? | | |",
              "| Are the expected conditions close to the motion's conditions? | | |",
              "| Anything materially wrong not covered above? | | |", ""]  # fmt: skip
    (RESULTS / c.id / "packet.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
