"""Count how far the pathway rules (rule table v2) cover the 40 backtest cases.

Spec: docs/validation/rule-table-extension-spec.md, section 5. No model call, no network, no database, no
clock: "today" is the day the dated control data was read (`app.memo.controls.read_on`), or `--today`.

    cd apps/api && .venv/bin/python ../../scripts/validation/backtest_coverage.py           # writes both files
    cd apps/api && .venv/bin/python ../../scripts/validation/backtest_coverage.py --check   # exit 1 if they differ

Reads   backtest/triggers.json   the trigger inventory: for each case, what required the hearing at filing
        backtest/inputs.json     per case: rules_date, record_facts, input_facts
        backtest/cases.yaml      only to cross-check the zoning district on the Planning record
Writes  backtest/coverage.json                       every case, every trigger, every run, the mapping used
        docs/validation/rule-coverage-of-the-40.md   the counts and the tables, built from the same result

WHAT IS RUN
For each case `app.memo.triggers.evaluate` (all eleven triggers) is run three times:
  record run   on record_facts (the facts as the decision record shows them) at the case's rules_date;
  input run    on input_facts (only what the neutral concept text states) at the same date, with the case's
               intake answers (inputs.json "intake_answers": the optional intake questions answered where the
               case file states the fact) applied the way the product applies them
               (`app.memo.intake.apply_intake_answers` on the profile, then `BusinessProfile.normalized()`); the
               same run without the answers is kept beside it, and the input coverage is counted both ways;
  today run    on record_facts at today's date, to show what dating the rules changes.
The concept facts come from `app.memo.facts.concept_facts_from_facts`. No site record is read: the site facts
are empty, so what the space is used as comes from the facts object alone (see SITE_RECORDS_NOTE).

THE DISTRICT AND THE SPECIAL DISTRICTS
The zoning district is the code at the start of the inventory's `zoning_district_at_filing`. The special
districts are the inventory's `special_districts`, each matched by the Planning Code section it names to the
name the product's special use district table gives that section (`datasf_sud.SUD_SECTIONS`). The rows are
then built the way tests/test_pathway_cases.py builds them: every static rule row of the rules file, the
zoning row from `datasf_zoning.overlay_for`, each special district row from `datasf_sud.overlay_for`, drawn as
a small square round one notional point and looked up through the file-backed store's `zoning_at` and
`overlays_at`. No control is typed into this file. An entry the inventory says is only on today's map, or that
names no section, or whose section the product's table does not carry, builds no row; each is listed with the
reason in the output. `_check_rows` proves the rows no rule reads change no answer.

HOW THE INVENTORY IS COMPARED (the same in every run)
Family to trigger: FAMILY_TO_TRIGGER. Three families were seen once and have no rule (NO_RULE_FAMILIES).
An item is one family of one case. Two entries of one family are one item (first and second story; the
formula retail baseline and the district prohibition): the item's control at filing is the more severe of the
two, which is how the rules combine several readings of one trigger. One sub-rule is kept as an item of its
own because the rules do not evaluate it (SUB_RULES_WITHOUT_A_RULE: the change-of-operator rule of
Planning Code § 178(c)(3), which spec section 1a says is printed as a note).
A control the inventory writes with a qualifier is read by its first word (`plain_control`); the full text is
kept beside it.
An item is "returned" when the trigger's control equals the item's control at filing ("principal" and "does not
apply" both ask for nothing and count as the same). Otherwise it is "not decided" (the rules name what is
missing), "different control", "Code and practice differ", "not returned" or "no rule".
A case is fully covered when every item is returned, partly covered when some are, not covered when none is.
The counts are given twice: over every item, and over the items a decision document names
(basis stated_in_record), leaving out what the readers inferred from the code and the one applicant's claim.
A trigger the rules raise (conditional or not permitted) that is no item of the case is a possible false
trigger; the inventory's `considered_not_triggers` notes that name the same ground are printed beside it
(matched by the words in NOTE_WORDS, then read by hand).

The input run uses its own words for the same comparison: found, not decided, missed, different control, no rule.

Every fixed sentence of the document is in this file: the tables at the top, the notes tables above `document`
(CASE_NOTES, FALSE_TRIGGER_NOTES, INPUT_RAISED_NOTES, INPUT_GAP_NOTES, TODAY_NOTES, RULE_POINTS) and the
sentences of `document`. Each note is tied to the result it explains. When the rules change and a note no
longer matches, the script says which one on stderr and exits 1; the note then needs a new sentence.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import re
import sys
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from precedent.models import Overlay
from precedent.sources import datasf_sud, datasf_zoning
from precedent.store.base import ZoningInfo
from precedent.store.local import LocalStore

from app.memo import controls, facts, triggers
from app.memo.intake import IntakeAnswers, apply_intake_answers, intake_answers_from_case
from app.memo.report import site_of
from app.models.memo import TRIGGER_LABELS, TriggerFinding

REPO = Path(__file__).resolve().parents[2]
TRIGGERS_FILE = REPO / "backtest" / "triggers.json"
INPUTS_FILE = REPO / "backtest" / "inputs.json"
CASES_FILE = REPO / "backtest" / "cases.yaml"
OUT_JSON = REPO / "backtest" / "coverage.json"
OUT_DOC = REPO / "docs" / "validation" / "rule-coverage-of-the-40.md"

# ---- the mapping (fixed tables, for review) ----------------------------------------------------------------
# The inventory's family -> the rule that reads it.
FAMILY_TO_TRIGGER: dict[str, str] = {
    "new_use_control": "T1",
    "new_use_control_special_district": "T2",
    "enlarge_or_intensify_existing_use": "T3",
    "alcohol_licence_in_restricted_district": "T4",
    "formula_retail": "T5",
    "nighttime_entertainment": "T6",
    "use_size": "T7",
    "laundromat_removal": "T8",
    "outdoor_activity_area": "T9",
    "amend_prior_conditions": "T10",
    "hours_of_operation": "T11",
}
# Seen once in the 40 and not built (spec section 1). Always "no rule".
NO_RULE_FAMILIES: dict[str, str] = {
    "legacy_business_replacement": "Planning Code § 754(c)(4)",
    "storefront_merger": "Planning Code § 754(c)(2)",
    "unscreened_open_air_use_waterfront_sud": "Planning Code § 240.2(d)",
}
# A sub-rule the rules print as a note and do not evaluate: an item of its own, always "no rule".
SUB_RULES_WITHOUT_A_RULE: dict[str, str] = {
    "change_of_operator_intensification": (
        "Planning Code § 178(c)(3), the change-of-operator rule for formula retail: spec section 1a says the "
        "rules print it as a note and do not evaluate it"
    ),
}
# The two story sub-rules: one item, and each story is also read on its own for the record.
STORY_SUB_RULES: dict[str, str] = {"first_story": "first", "second_story": "second"}
FAMILY_LABELS: dict[str, str] = {
    "new_use_control": "New use control of the district",
    "new_use_control_special_district": "Use control of a special use district",
    "enlarge_or_intensify_existing_use": "Enlarging or intensifying an existing use",
    "alcohol_licence_in_restricted_district": "Liquor licence in a restricted district",
    "formula_retail": "Formula retail",
    "nighttime_entertainment": "Nighttime entertainment",
    "use_size": "Use size",
    "laundromat_removal": "Laundromat removal",
    "outdoor_activity_area": "Outdoor activity area",
    "amend_prior_conditions": "Changing the conditions of an earlier approval",
    "hours_of_operation": "Hours of operation",
    "legacy_business_replacement": "Legacy business replacement",
    "storefront_merger": "Storefront merger",
    "unscreened_open_air_use_waterfront_sud": "Unscreened open-air use, Waterfront SUD",
    "formula_retail/change_of_operator_intensification": "Formula retail: change of operator",
}
# Most to least severe: two entries of one family combine to the first that appears.
CONTROL_SEVERITY: tuple[str, ...] = ("not_permitted", "conditional", "principal")
ASKS_NOTHING: frozenset[str] = frozenset({"principal", "does_not_apply"})
RAISES: frozenset[str] = frozenset({"conditional", "not_permitted"})
STATED = "stated_in_record"
CONTROL_WORDS: dict[str, str] = {
    "principal": "principal",
    "conditional": "conditional",
    "not_permitted": "not permitted",
    "not_decided": "not decided",
    "does_not_apply": "does not apply",
    "code_and_practice_differ": "Code and practice differ",
}
RESULT_WORDS: dict[str, str] = {
    "returned": "returned",
    "not_decided": "not decided",
    "different_control": "different control",
    "code_and_practice_differ": "Code and practice differ",
    "not_returned": "not returned",
    "no_rule": "no rule",
}
# The input run: found, not decided (the rules name what is missing), or missed. Two more words stay apart:
# "different control" (the trigger is found with another control) and "no rule" (no description could change it).
INPUT_RESULT: dict[str, str] = {
    "returned": "found",
    "not_decided": "not_decided",
    "different_control": "different_control",
    "code_and_practice_differ": "missed",
    "not_returned": "missed",
    "no_rule": "no_rule",
}
INPUT_WORDS: dict[str, str] = {
    "found": "found",
    "not_decided": "not decided",
    "missed": "missed",
    "different_control": "different control",
    "no_rule": "no rule",
}
COVERAGE_WORDS: dict[str, str] = {
    "fully": "fully covered",
    "partly": "partly covered",
    "not": "not covered",
    "none_stated": "no trigger stated in the record",
}
GROUP_WORDS: dict[str, str] = {
    "did_not_reach_approval": "did not reach approval",
    "decided": "decided",
}
ROW_WORDS: dict[str, str] = {
    "allowed": "allowed",
    "further_review": "further review",
    "potential_blocker": "potential blocker",
    "not_permitted": "not permitted",
    "insufficient_information": "insufficient information",
}

# An inventory entry that names one of these builds no row: the inventory says it was not on the map at filing.
NOT_AT_FILING = re.compile(r"today's|post-dates filing|after filing", re.IGNORECASE)
SECTION = re.compile(r"§ (\d+(?:\.\d+)?[A-Z]?)")
# The line the rules add to a finding whose control is not today's: "This control changed on <date> (<ordinance>); ..."
CHANGED_ON = re.compile(r"changed on (\d{4}-\d{2}-\d{2})(?: \((.+?)\))?;")
# Where the product's table gives one section to several map names, the name used here.
SECTION_NAME_CHOICE: dict[str, str] = {"249.35": "Fringe Financial Services RUD"}
# Sections the inventory names that the product's special use district table does not carry, and what follows.
SECTIONS_WITHOUT_A_ROW: dict[str, str] = {
    "780.3": (
        "North Beach Special Use District: the map has no polygon; the rules key it on the zoning district "
        "NCD-NORTH BEACH (triggers.MATCHES), so it is read"
    ),
    "788": "Lower Polk Street Alcohol Restricted Use District (expired 2023-06-01): not in the product's table",
    "781.5": (
        "Mission Street Formula Retail Restaurant Subdistrict (repealed by Ord. 249-23): not in the product's "
        "table; the formula retail trigger says it cannot place an address in it"
    ),
}
# Sections an entry may name in passing that are not a district of their own.
NOT_A_DISTRICT: frozenset[str] = frozenset({"303"})  # the Conditional Use section
# The notional point the rows are drawn round. The district comes from the inventory, not from this point.
POINT = (37.7749, -122.4194)
CENTRAL_SOMA_ROW = "Central SoMa"
FETCHED = dt.datetime(2026, 11, 10, tzinfo=dt.UTC)
SITE_RECORDS_NOTE = (
    "No site record is read. In the product a licence on file at the address can show the existing use; here "
    "only the facts object does. Where a description says the space was last used as the use proposed without "
    "saying whether that business stays, the use controls answer not decided and name it."
)

# Words that tie a `considered_not_triggers` note, or a settlement note of inputs.json, to a trigger.
NOTE_WORDS: dict[str, tuple[str, ...]] = {
    "T1": ("new-use control", "new use control", "restaurant use", "new restaurant", "bar "),
    "T2": ("249.60(f)", "249.40a", "249.38", "youth and family"),
    "T3": ("§ 178", "186.1", "enlarge", "intensif", "nonconforming"),
    "T4": ("alcohol", "liquor", "781.9", "249.62", "780.3(c)(2)"),
    "T5": ("formula retail",),
    "T6": ("entertainment",),
    "T7": ("use size", "121.2", "floor-area", "floor area"),
    "T8": ("laundromat", "202.12", "dry cleaner"),
    "T9": ("outdoor", "145.2", "202.2(a)(7)"),
    "T10": ("303(e)", "prior approval", "condition of approval"),
    "T11": ("hours",),
}


# ---- reading the inventory -----------------------------------------------------------------------------------
# Record facts whose deciding value the inventory's own trigger entry supplied, not the decision record
# (inputs.json record_sources). The record run is repeated with the fact cleared, and the counts are given both
# ways. inputs.json is not edited by this script.
INVENTORY_CODED_FACTS: dict[str, tuple[str, str]] = {
    "D17": (
        "changes_existing_business",
        "intensify comes from triggers.json trigger 2; the motion cites §§ 178 and 780.3 and never says "
        "intensification",
    ),
    "D24": (
        "changes_existing_business",
        "intensify comes from triggers.json trigger 3, which the inventory marks derived; the motion does not "
        "cite § 178",
    ),
}
# Items found on the description whose deciding fact the readers say the description does not give
# (inputs.json input_missing). Picked from the entries that say they decide the case, confirmed by hand.
# Key: (case, trigger).
DECIDING_FACT_NOT_DESCRIBED: dict[tuple[str, str], str] = {
    ("D07", "T1"): (
        "found only by reading the stated existing restaurant as new; the record's ground is Limited "
        "Restaurant to Restaurant"
    ),
    ("N12", "T1"): "the present use of the premises is not in the description, and it decides the case",
    ("N12", "T2"): "the present use of the premises is not in the description, and it decides the case",
    ("N05", "T4"): "whether the earlier Type 47 was authorised here, which the readers say decided the case",
    ("D18", "T5"): "the last use and operator, which decide new formula retail against a change of operator",
}
# A ground inside a returned trigger that the inventory rules out. Key: (case, trigger). Flagged by hand.
WRONG_GROUND: dict[tuple[str, str], str] = {
    ("D24", "T3"): (
        "The record run reads a Bar continuing and intensified (§ 178). The inventory's considered_not_triggers "
        "says no Bar or alcohol finding was made (§ 102: a Type 90 facility is not a Bar use). The control "
        "rests on the Nighttime Entertainment reading alone."
    ),
}
# What a fully covered case means where the end of the case was not the hearing the inventory records.
HEADLINE_CAVEATS: dict[str, str] = {
    "N05": "needed no hearing in the end (approved as a continuation)",
    "N08": "had nothing to find (principal at filing)",
    "N13": "needed no hearing in the end (approved by letter)",
    "N15": "needed no hearing in the end (approved by letter)",
}
# One cause written in two places of the code (triggers.json notes.counting_rules: count hearings by cause
# once). Key: case; value: the two families that are one cause.
CAUSE_PAIRS: dict[str, tuple[str, str, str]] = {
    "N07": ("new_use_control", "new_use_control_special_district", "Table 754 or 763 and § 249.60(f)(1)"),
    "N12": ("new_use_control", "new_use_control_special_district", "Table 754 or 763 and § 249.60(f)(1)"),
    "D11": ("new_use_control", "new_use_control_special_district", "Table 754 or 763 and § 249.60(f)(1)"),
    "D22": ("new_use_control", "new_use_control_special_district", "Table 754 or 763 and § 249.60(f)(1)"),
    "D25": ("new_use_control", "new_use_control_special_district", "Table 754 or 763 and § 249.60(f)(1)"),
    "D23": ("new_use_control", "alcohol_licence_in_restricted_district", "§ 249.62 and Table 737 Note 7"),
    "D17": ("amend_prior_conditions", "enlarge_or_intensify_existing_use", "§ 303(e) and § 178(c)(1)"),
    "D24": ("amend_prior_conditions", "enlarge_or_intensify_existing_use", "§ 303(e) and § 178(c)(1)"),
}


def plain_control(text: str | None, at_filing: str | None = None) -> str | None:
    """The control an inventory string starts with: "conditional (as the Commission applied it; ...)" is
    conditional. "same as at filing" is the control at filing. Anything else is None (kept as written)."""
    if text is None:
        return None
    words = text.strip().lower()
    if words.startswith("same as at filing"):
        return at_filing
    for word, control in (
        ("not_permitted", "not_permitted"),
        ("not permitted", "not_permitted"),
        ("conditional", "conditional"),
        ("principal", "principal"),
    ):
        if words.startswith(word):
            return control
    return None


def most_severe(found: Iterable[str | None]) -> str | None:
    have = [c for c in found if c is not None]
    return min(have, key=CONTROL_SEVERITY.index) if have else None


def sub_rule_key(entry: Mapping[str, Any]) -> str | None:
    """The sub-rule's name without its section references: "change_of_operator_intensification (§ ...)"."""
    text = entry.get("sub_rule")
    return text.split(" (", 1)[0].strip() if text else None


def district_code(text: str) -> str:
    """The zoning district code at the start of `zoning_district_at_filing`: "NCD-POLK (Polk Street NCD,
    § 723)" -> "NCD-POLK"; "CRNC - Chinatown ..." -> "CRNC"; "RC-4 (Residential-Commercial ...), § 209.3; 65-A"
    -> "RC-4"."""
    match = re.match(r"^(.+?)(?= \(| - |;|,|$)", text.strip())
    if match is None:
        raise ValueError(f"no district code in {text!r}")
    return match.group(1).strip()


def _section_names() -> dict[str, str]:
    """Planning Code section -> the product's name for the special use district of that section."""
    by_section: dict[str, list[str]] = {}
    for name, section in datasf_sud.SUD_SECTIONS.items():
        by_section.setdefault(section, []).append(name)
    names: dict[str, str] = {}
    for section, found in by_section.items():
        if len(found) == 1:
            names[section] = found[0]
        elif section in SECTION_NAME_CHOICE:
            names[section] = SECTION_NAME_CHOICE[section]
    # § 249.40A became § 249.38 on 2023-06-03 (triggers.MATCHES); the product's table lists today's number.
    names["249.40A"] = names["249.38"]
    return names


def special_district_rows(entries: Sequence[str]) -> tuple[list[str], list[dict[str, Any]]]:
    """The product's special use district names to build rows for, and what was done with each entry."""
    names = _section_names()
    rows: list[str] = []
    mapping: list[dict[str, Any]] = []
    for entry in entries:
        sections = [s for s in dict.fromkeys(SECTION.findall(entry)) if s not in NOT_A_DISTRICT]
        if NOT_AT_FILING.search(entry):
            mapping.append(
                {"inventory": entry, "rows": [], "left_out": "the inventory places it on today's map"}
            )
            continue
        if not sections:
            mapping.append(
                {"inventory": entry, "rows": [], "left_out": "names no Planning Code section of its own"}
            )
            continue
        built = [names[s] for s in sections if s in names]
        without = {
            s: SECTIONS_WITHOUT_A_ROW.get(s, "not in the product's table") for s in sections if s not in names
        }
        for name in built:
            if name not in rows:
                rows.append(name)
        item: dict[str, Any] = {"inventory": entry, "rows": list(dict.fromkeys(built))}
        if without:
            item["sections_without_a_row"] = without
        mapping.append(item)
    return rows, mapping


# ---- the rows, from the rule table (as tests/test_pathway_cases.py builds them) ------------------------------
def _square(lat: float, lng: float, half: float = 0.0004) -> dict[str, Any]:
    ring = [
        [lng - half, lat - half],
        [lng + half, lat - half],
        [lng + half, lat + half],
        [lng - half, lat + half],
        [lng - half, lat - half],
    ]
    return {"type": "MultiPolygon", "coordinates": [[ring]]}


def rule_table_rows(code: str, special: Sequence[str]) -> list[Overlay]:
    rows = [Overlay.model_validate(o) for o in datasf_zoning.rules_doc()["overlays"]]
    geom = _square(*POINT)
    zoning_row = datasf_zoning.overlay_for(code, [], FETCHED)
    if zoning_row is None:
        raise ValueError(f"no zoning row for {code!r}")
    rows.append(zoning_row.model_copy(update={"geom": geom}))
    for name in special:
        rows.append(datasf_sud.overlay_for(name, [], FETCHED).model_copy(update={"geom": geom}))
    return rows


_LOOKUPS: dict[tuple[str, tuple[str, ...]], tuple[ZoningInfo | None, list[Overlay]]] = {}


def store_lookup(code: str, special: Sequence[str]) -> tuple[ZoningInfo | None, list[Overlay]]:
    """`zoning_at` and `overlays_at` of the file-backed store, loaded with the rule-table rows."""
    key = (code, tuple(special))
    if key not in _LOOKUPS:

        async def run() -> tuple[ZoningInfo | None, list[Overlay]]:
            with tempfile.TemporaryDirectory() as folder:
                store = LocalStore(Path(folder))
                await store.upsert_overlays(rule_table_rows(code, special))
                return await store.zoning_at(*POINT), await store.overlays_at(*POINT)

        _LOOKUPS[key] = asyncio.run(run())
    return _LOOKUPS[key]


# ---- one run ---------------------------------------------------------------------------------------------------
def run_triggers(
    case: Mapping[str, Any],
    fact_object: Mapping[str, Any],
    zoning: ZoningInfo | None,
    overlays: Sequence[Overlay],
    *,
    rules_date: dt.date,
    today: dt.date,
    product_path: bool = False,
    answers: IntakeAnswers | None = None,
) -> list[TriggerFinding]:
    """`product_path`: read the facts the way the product reads a description, through a profile
    (`facts.concept_facts(facts.profile_from_facts(...))`), so a hand-stated `planning_use`, which the product has
    no field for, is not carried. Otherwise the stated § 102 use is carried (`concept_facts_from_facts`).
    `answers`: the case's intake answers, applied to the profile as the product applies them
    (`apply_intake_answers`, then `normalized()`); None or empty changes nothing."""
    if answers is None or answers.empty:
        concept = (
            facts.concept_facts(facts.profile_from_facts(fact_object))
            if product_path
            else facts.concept_facts_from_facts(fact_object)
        )
    else:
        profile = apply_intake_answers(facts.profile_from_facts(fact_object), answers).normalized()
        stated = () if product_path else facts.stated_planning_uses(fact_object)
        concept = facts.concept_facts(profile, stated_uses=stated)
    site = facts.site_facts([], site_of(case["address"], None, None), rules_date=rules_date)
    return triggers.evaluate(concept, site, zoning, overlays, rules_date=rules_date, today=today)


def finding_json(finding: TriggerFinding, *, lines: bool) -> dict[str, Any]:
    """One finding. The rule lines are kept where `lines` is set: for a trigger that is an item of the case,
    and for a trigger the rules raise. A trigger that is only not decided keeps the names of what is missing."""
    out: dict[str, Any] = {"control": finding.control}
    if finding.missing_inputs:
        out["missing"] = list(finding.missing_inputs)
    if finding.differs_today:
        out["differs_today"] = True
    if finding.in_force_from or finding.ordinance:
        out["in_force_from"] = finding.in_force_from
        out["ordinance"] = finding.ordinance
    if lines:
        out["lines"] = [{"rule_id": line.rule_id, "text": line.text} for line in finding.lines]
    return out


def findings_json(
    findings: Sequence[TriggerFinding], items: Sequence[Mapping[str, Any]], *, lines: bool = True
) -> dict[str, Any]:
    in_inventory = {item["trigger"] for item in items}
    return {
        f.rule_id: finding_json(
            f, lines=lines and (f.control in RAISES or (f.rule_id in in_inventory and triggers.matters(f)))
        )
        for f in findings
    }


def same_ask(a: str | None, b: str | None) -> bool:
    return a == b or (a in ASKS_NOTHING and b in ASKS_NOTHING)


def result_of(expected: str | None, finding: TriggerFinding | None) -> str:
    if finding is None:
        return "no_rule"
    if same_ask(finding.control, expected):
        return "returned"
    if finding.control == "not_decided":
        return "not_decided"
    if finding.control == "code_and_practice_differ":
        return "code_and_practice_differ"
    if finding.control in RAISES and expected in RAISES:
        return "different_control"
    return "not_returned"


def items_of(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The items of one case, in the inventory's order: one per family, the entries of a family merged, a
    sub-rule the rules do not evaluate kept apart."""
    items: dict[str, dict[str, Any]] = {}
    for entry in case["triggers"]:
        family = entry["family"]
        sub = sub_rule_key(entry)
        key = f"{family}/{sub}" if sub in SUB_RULES_WITHOUT_A_RULE else family
        control = plain_control(entry["control_at_filing"])
        item = items.setdefault(key, {"key": key, "family": family, "entries": []})
        item["entries"].append(
            {
                "sub_rule": entry.get("sub_rule"),
                "basis": entry["basis"],
                "control_at_filing_as_written": entry["control_at_filing"],
                "control_at_filing": control,
                "control_today_as_written": entry.get("control_today"),
                "control_today": plain_control(entry.get("control_today"), control),
                "permission_changed_since_filing": entry.get("permission_changed_since_filing"),
            }
        )
    for key, item in items.items():
        entries = item["entries"]
        family = item["family"]
        if key != family:
            item["trigger"] = None
            item["no_rule"] = SUB_RULES_WITHOUT_A_RULE[key.split("/", 1)[1]]
        elif family in NO_RULE_FAMILIES:
            item["trigger"] = None
            item["no_rule"] = f"seen once in the 40 and not built ({NO_RULE_FAMILIES[family]})"
        else:
            item["trigger"] = FAMILY_TO_TRIGGER[family]
        item["label"] = FAMILY_LABELS[key]
        item["control_at_filing"] = most_severe(e["control_at_filing"] for e in entries)
        item["control_today"] = most_severe(e["control_today"] for e in entries)
        bases = {e["basis"] for e in entries}
        if len(bases) != 1:
            raise ValueError(f"{case['id']} {key}: entries of one item with different bases; split them")
        item["basis"] = entries[0]["basis"]
    return list(items.values())


def coverage(results: Sequence[str]) -> str:
    if not results:
        return "none_stated"
    hit = sum(1 for r in results if r == "returned")
    return "fully" if hit == len(results) else "partly" if hit else "not"


def notes_naming(trigger: str, notes: Iterable[tuple[str, str]]) -> list[str]:
    """The notes whose text names the ground of this trigger (NOTE_WORDS), as written."""
    words = NOTE_WORDS[trigger]
    return [f"{item}: {why}" for item, why in notes if any(w in f"{item} {why}".lower() for w in words)]


def compare(
    items: Sequence[Mapping[str, Any]],
    findings: Sequence[TriggerFinding],
    *,
    date_key: str = "control_at_filing",
) -> list[dict[str, Any]]:
    by_id = {f.rule_id: f for f in findings}
    out: list[dict[str, Any]] = []
    for item in items:
        finding = by_id.get(item["trigger"]) if item["trigger"] else None
        expected = item[date_key]
        row: dict[str, Any] = {
            "item": item["key"],
            "trigger": item["trigger"],
            "basis": item["basis"],
            "inventory_control": expected,
            "rules_control": finding.control if finding else None,
            "result": result_of(expected, finding),
        }
        if finding is not None and finding.control == "not_decided":
            row["missing"] = list(finding.missing_inputs)
        elif finding is not None and finding.missing_inputs:
            row["missing_in_the_trigger"] = list(finding.missing_inputs)
        if finding is None:
            row["no_rule"] = item["no_rule"]
        out.append(row)
    return out


def extras(
    items: Sequence[Mapping[str, Any]], findings: Sequence[TriggerFinding]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Triggers that are no item of the case: the ones the rules raise, and the ones they leave open."""
    in_inventory = {item["trigger"] for item in items if item["trigger"]}
    raised: list[dict[str, Any]] = []
    left_open: list[dict[str, Any]] = []
    for finding in findings:
        if finding.rule_id in in_inventory:
            continue
        if finding.control in RAISES:
            raised.append({"trigger": finding.rule_id, "family": finding.family, "control": finding.control})
        elif triggers.matters(finding):
            left_open.append(
                {
                    "trigger": finding.rule_id,
                    "family": finding.family,
                    "control": finding.control,
                    "missing": list(finding.missing_inputs),
                }
            )
    return raised, left_open


def rows_the_rules_read(code: str, special: Sequence[str]) -> list[str]:
    """The special district rows that tie the address to something a rule reads: a row whose presence changes
    `triggers.special_district_keys`, and the Central SoMa row (the MUR rows read it)."""
    base = set(triggers.special_district_keys(*store_lookup(code, [])))
    return [
        name
        for name in special
        if name == CENTRAL_SOMA_ROW
        or set(triggers.special_district_keys(*store_lookup(code, [name]))) != base
    ]


def _check_rows(
    case: Mapping[str, Any],
    fact_object: Mapping[str, Any],
    code: str,
    special: Sequence[str],
    findings: Sequence[TriggerFinding],
    *,
    rules_date: dt.date,
    today: dt.date,
    product_path: bool = False,
    answers: IntakeAnswers | None = None,
) -> None:
    """The special district rows no rule reads change no answer: the same run with only the rows the rules
    read gives the same controls and names the same missing inputs."""
    kept = rows_the_rules_read(code, special)
    if kept == list(special):
        return
    lean = run_triggers(
        case,
        fact_object,
        *store_lookup(code, kept),
        rules_date=rules_date,
        today=today,
        product_path=product_path,
        answers=answers,
    )
    if [(f.rule_id, f.control, f.missing_inputs) for f in lean] != [
        (f.rule_id, f.control, f.missing_inputs) for f in findings
    ]:
        raise AssertionError(f"{case['id']}: a special district row no rule reads changed an answer")


# ---- one case ---------------------------------------------------------------------------------------------------
def evaluate_case(
    case: Mapping[str, Any], inputs: Mapping[str, Any], on_record: str | None, today: dt.date
) -> dict[str, Any]:
    code = district_code(case["zoning_district_at_filing"])
    special, special_mapping = special_district_rows(case["special_districts"])
    zoning, overlays = store_lookup(code, special)
    rules_date = dt.date.fromisoformat(inputs["rules_date"])
    record_facts, input_facts = inputs["record_facts"], inputs["input_facts"]
    # the optional intake questions, answered where the case file states the fact
    answers = intake_answers_from_case(inputs)

    record = run_triggers(case, record_facts, zoning, overlays, rules_date=rules_date, today=today)
    # the input run stands for what the product does with a description and the intake answers: the product's
    # own path
    described = run_triggers(
        case,
        input_facts,
        zoning,
        overlays,
        rules_date=rules_date,
        today=today,
        product_path=True,
        answers=answers,
    )
    # the same without the intake answers: the description alone
    described_alone = run_triggers(
        case, input_facts, zoning, overlays, rules_date=rules_date, today=today, product_path=True
    )
    # beside it, the same with the hand-stated § 102 use carried (the figures of the earlier count)
    described_stated = run_triggers(
        case, input_facts, zoning, overlays, rules_date=rules_date, today=today, answers=answers
    )
    # the record facts through the product's path too (no hand-stated § 102 use)
    record_profile = run_triggers(
        case, record_facts, zoning, overlays, rules_date=rules_date, today=today, product_path=True
    )
    now = run_triggers(case, record_facts, zoning, overlays, rules_date=today, today=today)
    _check_rows(case, record_facts, code, special, record, rules_date=rules_date, today=today)
    _check_rows(
        case,
        input_facts,
        code,
        special,
        described,
        rules_date=rules_date,
        today=today,
        product_path=True,
        answers=answers,
    )
    # the record facts with the fact the inventory itself supplied cleared (INVENTORY_CODED_FACTS)
    coded = INVENTORY_CODED_FACTS.get(case["id"])
    record_uncoded = (
        run_triggers(
            case, {**record_facts, coded[0]: None}, zoning, overlays, rules_date=rules_date, today=today
        )
        if coded
        else record
    )

    items = items_of(case)
    notes = [(n["item"], n["why"]) for n in case.get("considered_not_triggers", [])]
    settled = [
        (f"inputs.json, {s['field']}", s["note"])
        for s in inputs.get("record_facts_settled", [])
        if s.get("note")
    ]

    # record run
    record_items = compare(items, record)
    all_results = [r["result"] for r in record_items]
    stated_results = [r["result"] for r in record_items if r["basis"] == STATED]
    raised, left_open = extras(items, record)
    for extra in raised:
        extra["inventory_notes"] = notes_naming(extra["trigger"], notes)
        extra["settlement_notes"] = notes_naming(extra["trigger"], settled)
    # each story on its own, where the inventory gives one entry per story
    stories: list[dict[str, Any]] = []
    for entry in case["triggers"]:
        story = STORY_SUB_RULES.get(sub_rule_key(entry) or "")
        if story is None:
            continue
        one = run_triggers(
            case, {**record_facts, "story": [story]}, zoning, overlays, rules_date=rules_date, today=today
        )
        read = triggers.by_id(one, FAMILY_TO_TRIGGER[entry["family"]]).control
        stories.append(
            {
                "family": entry["family"],
                "story": story,
                "inventory_control": plain_control(entry["control_at_filing"]),
                "rules_control": read,
                "same": same_ask(read, plain_control(entry["control_at_filing"])),
            }
        )

    # input run
    input_items = compare(items, described)
    for row in input_items:
        row["result"] = INPUT_RESULT[row["result"]]
    input_raised, input_open = extras(items, described)
    for extra in input_raised:
        extra["inventory_notes"] = notes_naming(extra["trigger"], notes)
    record_by_item = {r["item"]: r for r in record_items}
    covered_not_described = [
        {
            "item": row["item"],
            "trigger": row["trigger"],
            "input_result": row["result"],
            "rules_control_on_the_description": row["rules_control"],
            "missing": row.get("missing", []),
        }
        for row in input_items
        if record_by_item[row["item"]]["result"] == "returned" and row["result"] != "found"
    ]
    input_results = [r["result"] for r in input_items]
    found = sum(1 for r in input_results if r == "found")
    alone_items = compare(items, described_alone)
    for row in alone_items:
        row["result"] = INPUT_RESULT[row["result"]]
    alone_found = sum(1 for r in alone_items if r["result"] == "found")
    stated_use_items = compare(items, described_stated)
    for row in stated_use_items:
        row["result"] = INPUT_RESULT[row["result"]]
    stated_found = sum(1 for r in stated_use_items if r["result"] == "found")
    profile_items = compare(items, record_profile)
    uncoded_items = compare(items, record_uncoded)
    uncoded_raised, _ = extras(items, record_uncoded)
    # items found on the description whose deciding fact the readers say the description does not give
    deciding_missing = [
        {
            "item": row["item"],
            "trigger": row["trigger"],
            "why": DECIDING_FACT_NOT_DESCRIBED[(case["id"], row["trigger"])],
        }
        for row in input_items
        if row["result"] == "found" and (case["id"], row["trigger"]) in DECIDING_FACT_NOT_DESCRIBED
    ]
    deciding_candidates = [m for m in inputs.get("input_missing", []) if "decid" in json.dumps(m).lower()]

    # today run
    then = {f.rule_id: f for f in record}
    differences: list[dict[str, Any]] = []
    for finding in now:
        before = then[finding.rule_id]
        if same_ask(before.control, finding.control):
            continue
        item = next((i for i in items if i["trigger"] == finding.rule_id), None)
        differs = next((ln.text for ln in before.lines if ln.rule_id.endswith(".differs")), None)
        changed = CHANGED_ON.search(differs or "")
        differences.append(
            {
                "trigger": finding.rule_id,
                "family": finding.family,
                "at_filing": before.control,
                "today": finding.control,
                "in_inventory": item is not None,
                "inventory_control_today": item["control_today"] if item else None,
                "inventory_control_today_as_written": (
                    [e["control_today_as_written"] for e in item["entries"]] if item else None
                ),
                "changed_on": changed.group(1) if changed else None,
                "ordinance": changed.group(2) if changed else None,
                "rules_line": differs,
            }
        )
    today_items = compare(items, now, date_key="control_today")
    row_then = triggers.zoning_outcome(record)
    row_now = triggers.zoning_outcome(now)

    return {
        "id": case["id"],
        "group": case["group"],
        "outcome": case["outcome"],
        "record": case["record"],
        "address": case["address"],
        "filed": case["filed"],
        "rules_date": inputs["rules_date"],
        "district": {
            "inventory": case["zoning_district_at_filing"],
            "code": code,
            "on_the_planning_record": on_record,
            "store_returned": zoning.district if zoning else None,
            "in_the_dated_control_data": controls.covers(code),
            "in_the_rule_table": code in datasf_zoning.zoning_controls(),
        },
        "special_districts": {
            "mapping": special_mapping,
            "rows_built": special,
            "rows_a_rule_reads": rows_the_rules_read(code, special),
            "read_by_the_rules": [
                {"key": key, "name": controls.special_district(key).name}
                for key in triggers.special_district_keys(zoning, overlays)
            ],
        },
        "inventory": {
            "net_result_at_filing": case["net_result_at_filing"],
            "controls_changed_since_filing": case["controls_changed_since_filing"],
            "items": items,
        },
        "record_run": {
            "facts": "record_facts",
            "rules_date": inputs["rules_date"],
            "triggers": findings_json(record, items),
            "zoning_row": row_then.status,
            "zoning_row_note": row_then.status_note,
            "items": record_items,
            "each_story": stories,
            "coverage": coverage(all_results),
            "coverage_stated_in_record_only": coverage(stated_results),
            "raised_outside_the_inventory": raised,
            "left_open_outside_the_inventory": left_open,
            "wrong_ground_inside_a_returned_trigger": [
                {"trigger": t, "why": why} for (cid, t), why in WRONG_GROUND.items() if cid == case["id"]
            ],
        },
        "record_run_profile_only": {
            "facts": "record_facts, through the product's path (no hand-stated planning_use)",
            "items": profile_items,
            "coverage": coverage([r["result"] for r in profile_items]),
            "zoning_row": triggers.zoning_outcome(record_profile).status,
        },
        "record_run_without_inventory_coded_fact": {
            "cleared": coded[0] if coded else None,
            "why": coded[1] if coded else None,
            "items": uncoded_items,
            "coverage": coverage([r["result"] for r in uncoded_items]),
            "raised_outside_the_inventory": uncoded_raised,
        },
        "input_run": {
            "facts": "input_facts, with the intake answers the case file states",
            "intake_answers": answers.model_dump(exclude_none=True),
            "rules_date": inputs["rules_date"],
            "triggers": findings_json(described, items),
            "zoning_row": triggers.zoning_outcome(described).status,
            "items": input_items,
            "coverage": "fully" if found == len(input_results) else "partly" if found else "not",
            "rules_cover_input_does_not": covered_not_described,
            "found_but_the_deciding_fact_is_not_described": deciding_missing,
            "input_missing_entries_that_say_they_decide": deciding_candidates,
            "raised_outside_the_inventory": input_raised,
            "left_open_outside_the_inventory": input_open,
            "input_missing_as_the_readers_listed_it": inputs.get("input_missing", []),
        },
        "input_run_without_intake_answers": {
            "facts": "input_facts alone (no intake answer)",
            "items": alone_items,
            "coverage": "fully" if alone_found == len(alone_items) else "partly" if alone_found else "not",
            "zoning_row": triggers.zoning_outcome(described_alone).status,
        },
        "input_run_stated_use": {
            "facts": "input_facts and the intake answers, with the hand-stated planning_use carried",
            "items": stated_use_items,
            "coverage": "fully"
            if stated_found == len(stated_use_items)
            else "partly"
            if stated_found
            else "not",
            "zoning_row": triggers.zoning_outcome(described_stated).status,
        },
        "today_run": {
            "facts": "record_facts",
            "rules_date": today.isoformat(),
            "triggers": findings_json(now, items, lines=False),
            "zoning_row": row_now.status,
            "zoning_row_note": row_now.status_note,
            "items": today_items,
            "differs_from_filing": differences,
            "zoning_row_differs": row_then.status != row_now.status,
        },
    }


# ---- every case -------------------------------------------------------------------------------------------------
def _by_cause(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The record run counted by cause: the two families of a pair in CAUSE_PAIRS are one cause, returned when
    both are returned."""
    causes = returned = 0
    pairs: list[dict[str, Any]] = []
    for case in cases:
        items = {r["item"]: r for r in case["record_run"]["items"]}
        pair = CAUSE_PAIRS.get(case["id"])
        joined = set(pair[:2]) if pair and set(pair[:2]) <= set(items) else set()
        if joined:
            causes += 1
            both = all(items[k]["result"] == "returned" for k in joined)
            returned += both
            pairs.append({"case": case["id"], "families": list(pair[:2]), "code": pair[2], "returned": both})
        for key, row in items.items():
            if key in joined:
                continue
            causes += 1
            returned += row["result"] == "returned"
    return {"causes": causes, "returned": returned, "pairs": pairs}


def data_read_on() -> dt.date:
    """The day the dated control data was read: "today" for this script, which reads no clock."""
    day = controls.read_on()
    if day is None:
        raise SystemExit("the dated control data does not say when it was read; pass --today")
    return day


def _tally(values: Iterable[str], order: Sequence[str]) -> dict[str, int]:
    counted = Counter(values)
    return {key: counted.get(key, 0) for key in order}


def build(today: dt.date) -> dict[str, Any]:
    inventory = json.loads(TRIGGERS_FILE.read_text(encoding="utf-8"))
    inputs = json.loads(INPUTS_FILE.read_text(encoding="utf-8"))["cases"]
    on_record = {
        c["id"]: c.get("zoning_district_on_record")
        for c in yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))["cases"]
    }
    ids = [c["id"] for c in inventory["cases"]]
    if set(ids) != set(inputs) or set(ids) != set(on_record) or len(ids) != len(set(ids)):
        raise SystemExit("triggers.json, inputs.json and cases.yaml do not list the same cases")
    cases = [evaluate_case(c, inputs[c["id"]], on_record[c["id"]], today) for c in inventory["cases"]]

    order = ("fully", "partly", "not")
    groups = ("decided", "did_not_reach_approval")

    def by_group(key: str, run: str, keys: Sequence[str]) -> dict[str, dict[str, int]]:
        out = {"all": _tally((c[run][key] for c in cases), keys)}
        for group in groups:
            out[group] = _tally((c[run][key] for c in cases if c["group"] == group), keys)
        return out

    record_items = [(c, r) for c in cases for r in c["record_run"]["items"]]
    input_items = [(c, r) for c in cases for r in c["input_run"]["items"]]
    results = tuple(RESULT_WORDS)
    input_results = tuple(INPUT_WORDS)
    counts = {
        "cases": len(cases),
        "groups": _tally((c["group"] for c in cases), groups),
        "items": len(record_items),
        "items_stated_in_record": sum(1 for _, r in record_items if r["basis"] == STATED),
        "rule_coverage": {
            "every_item": by_group("coverage", "record_run", order),
            "items_stated_in_record_only": by_group(
                "coverage_stated_in_record_only", "record_run", (*order, "none_stated")
            ),
            "items": {
                "every_item": _tally((r["result"] for _, r in record_items), results),
                "stated_in_record": _tally(
                    (r["result"] for _, r in record_items if r["basis"] == STATED), results
                ),
                "inferred_or_claimed": _tally(
                    (r["result"] for _, r in record_items if r["basis"] != STATED), results
                ),
            },
        },
        "input_coverage": {
            "every_item": by_group("coverage", "input_run", order),
            "items": _tally((r["result"] for _, r in input_items), input_results),
            "rules_cover_input_does_not": {
                "items": sum(len(c["input_run"]["rules_cover_input_does_not"]) for c in cases),
                "cases": sum(1 for c in cases if c["input_run"]["rules_cover_input_does_not"]),
                "cases_fully_covered_by_the_rules_and_not_fully_found": sum(
                    1
                    for c in cases
                    if c["record_run"]["coverage"] == "fully" and c["input_run"]["coverage"] != "fully"
                ),
            },
        },
        "input_coverage_without_the_intake_answers": {
            "every_item": by_group("coverage", "input_run_without_intake_answers", order),
            "items": _tally(
                (r["result"] for c in cases for r in c["input_run_without_intake_answers"]["items"]),
                input_results,
            ),
            "cases_with_intake_answers": [c["id"] for c in cases if c["input_run"]["intake_answers"]],
            "cases_that_differ": [
                c["id"]
                for c in cases
                if c["input_run_without_intake_answers"]["items"] != c["input_run"]["items"]
            ],
        },
        "input_coverage_with_the_stated_use": {
            "every_item": by_group("coverage", "input_run_stated_use", order),
            "items": _tally(
                (r["result"] for c in cases for r in c["input_run_stated_use"]["items"]), input_results
            ),
            "cases_that_differ": [
                c["id"] for c in cases if c["input_run_stated_use"]["items"] != c["input_run"]["items"]
            ],
        },
        "record_facts_through_the_product_path": {
            "every_item": by_group("coverage", "record_run_profile_only", order),
            "returned": sum(
                1 for c in cases for r in c["record_run_profile_only"]["items"] if r["result"] == "returned"
            ),
            "cases_that_differ": [
                c["id"] for c in cases if c["record_run_profile_only"]["items"] != c["record_run"]["items"]
            ],
            "zoning_row_differs": {
                c["id"]: [c["record_run"]["zoning_row"], c["record_run_profile_only"]["zoning_row"]]
                for c in cases
                if c["record_run"]["zoning_row"] != c["record_run_profile_only"]["zoning_row"]
            },
        },
        "without_the_inventory_coded_facts": {
            "cases": sorted(INVENTORY_CODED_FACTS),
            "every_item": by_group("coverage", "record_run_without_inventory_coded_fact", order),
            "returned": sum(
                1
                for c in cases
                for r in c["record_run_without_inventory_coded_fact"]["items"]
                if r["result"] == "returned"
            ),
            "enlarge_or_intensify_returned": sum(
                1
                for c in cases
                for r in c["record_run_without_inventory_coded_fact"]["items"]
                if r["item"] == "enlarge_or_intensify_existing_use" and r["result"] == "returned"
            ),
            "enlarge_or_intensify_items": sum(
                1
                for c in cases
                for r in c["record_run_without_inventory_coded_fact"]["items"]
                if r["item"] == "enlarge_or_intensify_existing_use"
            ),
            "possible_false_triggers": sum(
                len(c["record_run_without_inventory_coded_fact"]["raised_outside_the_inventory"])
                for c in cases
            ),
            "possible_false_trigger_cases": sum(
                1
                for c in cases
                if c["record_run_without_inventory_coded_fact"]["raised_outside_the_inventory"]
            ),
        },
        "by_cause": _by_cause(cases),
        "found_but_the_deciding_fact_is_not_described": {
            "items": [
                f"{c['id']} {m['trigger']}"
                for c in cases
                for m in c["input_run"]["found_but_the_deciding_fact_is_not_described"]
            ],
            "fully_found": sum(1 for c in cases if c["input_run"]["coverage"] == "fully"),
            "fully_found_without_them": sum(
                1
                for c in cases
                if c["input_run"]["coverage"] == "fully"
                and not c["input_run"]["found_but_the_deciding_fact_is_not_described"]
            ),
            "new_use_control_found": sum(
                1
                for c in cases
                for r in c["input_run"]["items"]
                if r["item"] == "new_use_control" and r["result"] == "found"
            ),
            "new_use_control_found_without_them": sum(
                1
                for c in cases
                for r in c["input_run"]["items"]
                if r["item"] == "new_use_control"
                and r["result"] == "found"
                and (c["id"], "T1") not in DECIDING_FACT_NOT_DESCRIBED
            ),
            "new_use_control_items": sum(
                1 for c in cases for r in c["input_run"]["items"] if r["item"] == "new_use_control"
            ),
        },
        "zoning_row_on_record_facts_at_filing": _tally(
            (c["record_run"]["zoning_row"] for c in cases), tuple(ROW_WORDS)
        ),
        "possible_false_triggers": {
            "record_run": sum(len(c["record_run"]["raised_outside_the_inventory"]) for c in cases),
            "record_run_cases": sum(1 for c in cases if c["record_run"]["raised_outside_the_inventory"]),
            "input_run": sum(len(c["input_run"]["raised_outside_the_inventory"]) for c in cases),
            "input_run_cases": sum(1 for c in cases if c["input_run"]["raised_outside_the_inventory"]),
        },
        "today": {
            "cases_where_a_trigger_reads_differently": sum(
                1 for c in cases if c["today_run"]["differs_from_filing"]
            ),
            "cases_where_the_zoning_row_differs": sum(
                1 for c in cases if c["today_run"]["zoning_row_differs"]
            ),
        },
    }

    # the items the rules do not return, by family
    uncovered: dict[str, list[dict[str, Any]]] = {}
    for case, row in record_items:
        if row["result"] != "returned":
            uncovered.setdefault(row["item"], []).append(
                {
                    "case": case["id"],
                    "basis": row["basis"],
                    "result": row["result"],
                    "inventory_control": row["inventory_control"],
                    "rules_control": row["rules_control"],
                    "missing": row.get("missing", []),
                }
            )
    family_counts = {
        key: {
            "items": sum(1 for _, r in record_items if r["item"] == key),
            "returned": sum(1 for _, r in record_items if r["item"] == key and r["result"] == "returned"),
            "found_on_the_description": sum(
                1 for _, r in input_items if r["item"] == key and r["result"] == "found"
            ),
        }
        for key in FAMILY_LABELS
        if any(r["item"] == key for _, r in record_items)
    }

    districts = {c["id"]: c["district"] for c in cases}
    not_mapped = sorted(
        {
            f"§ {section}: {why}"
            for c in cases
            for m in c["special_districts"]["mapping"]
            for section, why in m.get("sections_without_a_row", {}).items()
        }
    )
    return {
        "_doc": (
            "Coverage of the 40 backtest cases by the pathway rules (rule table v2). Written by "
            "scripts/validation/backtest_coverage.py from backtest/triggers.json and backtest/inputs.json; do "
            "not edit by hand. No model, no network, no database. Read with "
            "docs/validation/rule-coverage-of-the-40.md."
        ),
        "today": today.isoformat(),
        "control_data_read_on": data_read_on().isoformat(),
        "inventory_generated": inventory["generated"],
        "mapping": {
            "family_to_trigger": FAMILY_TO_TRIGGER,
            "families_without_a_rule": NO_RULE_FAMILIES,
            "sub_rules_without_a_rule": SUB_RULES_WITHOUT_A_RULE,
            "trigger_labels": {tid: TRIGGER_LABELS[family] for tid, family in triggers.FAMILIES.items()},
            "item": (
                "one family of one case; two entries of one family are one item with the more severe control; a "
                "sub-rule the rules do not evaluate is an item of its own"
            ),
            "control": "an inventory control written with a qualifier is read by its first word",
            "returned": (
                "the trigger's control equals the item's control at filing; principal and does_not_apply are "
                "the same"
            ),
            "district": "the code at the start of zoning_district_at_filing",
            "special_districts": (
                "each inventory entry is matched by the Planning Code section it names to the product's special "
                "use district table (datasf_sud.SUD_SECTIONS); entries the inventory places on today's map, "
                "entries that name no section, and sections the table does not carry build no row"
            ),
            "section_name_choice": SECTION_NAME_CHOICE,
            "sections_named_without_a_row": not_mapped,
            "districts_not_in_the_dated_control_data": sorted(
                {d["code"] for d in districts.values() if not d["in_the_dated_control_data"]}
            ),
            "districts_that_differ_from_the_planning_record": {
                cid: d for cid, d in districts.items() if d["on_the_planning_record"] != d["code"]
            },
            "site_records": SITE_RECORDS_NOTE,
            "point": "one notional point for every case; the district comes from the inventory, not from the map",
        },
        "counts": counts,
        "by_family": family_counts,
        "not_returned_by_family": uncovered,
        "cases": cases,
    }


# ---- the notes (fixed sentences, for review) ------------------------------------------------------------------
# Why a case is not fully covered. Each note is tied to the result it explains: the items the rules did not
# return, as "item=result" in the inventory's order. When the rules change and the result with them, the note
# no longer matches; the document then says so, and this table needs a new sentence.
CASE_NOTES: dict[str, tuple[str, str]] = {
    "N01": (
        "unscreened_open_air_use_waterfront_sud=no_rule",
        "The only trigger is the unscreened open-air use clause of the Waterfront Special Use District No. 2 "
        "(§ 240.2(d); the clause was deleted on 2023-08-28). It was seen once and has no rule. Every built trigger asks for "
        "nothing on the record facts, so the zoning row reads allowed where a hearing was required at filing.",
    ),
    "N04": (
        "formula_retail/change_of_operator_intensification=no_rule",
        "Formula retail (Table 760) is returned. The second entry is the change-of-operator rule of "
        "§ 178(c)(3), which the rules print as a note and do not evaluate. At filing both gave conditional, so "
        "the row is right.",
    ),
    "N11": (
        "outdoor_activity_area=not_decided",
        "An outdoor dining area at the rear of the lot in NCD-HAIGHT. Table 719 makes it conditional unless it "
        "keeps within every limit of § 202.2(a)(7). The record never says which limit the patio exceeded, and "
        "the record facts do not either, so the rules answer not decided and name the limits. The inventory "
        "records conditional because the Commission packet required the hearing.",
    ),
    "N13": (
        "enlarge_or_intensify_existing_use=not_returned",
        "The only entry is the applicant's claim (§ 186.1(b): adding a Type 48 licence intensifies an existing "
        "use). Planning did not adopt it and approved by letter. The rules do not return it either: the last "
        "use was an adult business, which is not a use the rule table carries, so the uses are read as new and "
        "both are principally permitted. On this point the rules agree with Planning. They raise use size "
        "instead, which Planning did not (see the possible false triggers).",
    ),
    "N14": (
        "formula_retail=not_decided",
        "Formula retail is the only ground that fits the section the application cites, and nothing found "
        "shows the business is a chain. The record facts leave it unstated, so the rules answer not decided "
        "and name it.",
    ),
    "N15": (
        "formula_retail/change_of_operator_intensification=no_rule",
        "The same address as N04, filed after Ord. 62-25 (effective 2025-06-01) took limb (E) out of "
        "§ 178(c)(3). Formula retail (Table 760) is returned as conditional, which is the ground the "
        "application states. The deciding rule was the change-of-operator test, under which Planning approved "
        "by letter without a hearing. The rules do not evaluate that test, so their answer here (conditional) "
        "is not what happened.",
    ),
    "D04": (
        "enlarge_or_intensify_existing_use=not_returned",
        "A formula retail restaurant enlarged in NC-2 on Chestnut Street. Formula retail is returned: the "
        "Taraval Street Restaurant Subdistrict is now placed by its overlay (§ 781.1), and no overlay at this "
        "address places it there. Not returned: enlarging an existing conditional use. The existing restaurant "
        "is a conditional use only because it is formula retail, and T3 reads the Restaurant row, which is "
        "principal (see the points for the rules).",
    ),
    "N07": (
        "new_use_control=not_decided",
        "A new Restaurant in NCT-MISSION. Table 754 Note 7 caps the eating and drinking uses of the district "
        "(167 on the filing date), and a new one is not permitted above the cap. No input carries the count, so "
        "the use control is not decided and names the cap. The special district's rule (§ 249.60(f)(1)) is "
        "returned as conditional.",
    ),
    "D09": (
        "outdoor_activity_area=not_decided",
        "An outdoor dining area on a parking lot behind a restaurant in NCT-MISSION. The district's own row "
        "makes it conditional; § 202.2(a)(7) itself makes it principally permitted in every NCT district within "
        "five limits, and the record facts do not say which limit it exceeds, so the rules answer not decided "
        "and name the limits. The Commission heard it as conditional.",
    ),
    "D10": (
        "outdoor_activity_area=not_decided",
        "As D09: an outdoor area behind a restaurant in NCT-MISSION, read against the § 202.2(a)(7) limits "
        "that the record facts do not settle.",
    ),
    "D11": (
        "new_use_control=not_decided",
        "As N07: a new Restaurant in NCT-MISSION, not decided on the Table 754 Note 7 cap (167 on the filing "
        "date). § 249.60(f)(1) is returned.",
    ),
    "D05": (
        "enlarge_or_intensify_existing_use=not_returned",
        "Returned: Nighttime Entertainment (conditional on the first story, not permitted on the second), the "
        "new Bar (conditional) and use size (not permitted from 4,000 square feet). Not returned: the change "
        "of a nonconforming use (§ 182(b)). The existing use is a movie theatre, which is not a use the rule "
        "table carries, so the trigger for enlarging or intensifying an existing use does not apply.",
    ),
    "D12": (
        "enlarge_or_intensify_existing_use=not_decided",
        "Laundromat removal is returned. The expansion of a nonconforming restaurant in RM-3 is not decided: "
        "Table 209.2 has no Restaurant row, the row that governs reads not permitted, and the rules cannot "
        "tell whether the use falls under the Limited Commercial Use rows (§§ 186, 186.3). The inventory "
        "itself records that neither reader found the clause that makes this expansion conditional.",
    ),
    "D16": (
        "legacy_business_replacement=no_rule",
        "The only trigger is the legacy business replacement control of the Mission Street NCT (§ 754(c)(4)). "
        "It was seen once and has no rule. On the record facts (a bar after a bar, nothing enlarged) every "
        "built trigger asks for nothing, so the zoning row reads allowed where a hearing was required.",
    ),
    "D19": (
        "alcohol_licence_in_restricted_district=not_decided",
        "A restaurant adding alcohol in the Haight Street Alcohol Restricted Use Subdistrict. The rule reads a "
        "named licence type (40, 41, 42, 47, 48 or 57). The record says on-sale beer and wine at a bona fide "
        "eating place and gives no type number, and the facts objects have no field for what a concept pours, "
        "so the record facts hold no licence type. The rules answer not decided and name the licence type. "
        "Given beer and wine, they derive Type 41 and return conditional.",
    ),
    "D22": (
        "new_use_control=not_decided, storefront_merger=no_rule",
        "The new Restaurant is returned under § 249.60(f)(1). The use control of Table 754 is not decided on "
        "the Note 7 cap (179 on the filing date): the readers record 148 open in July 2025, but no input carries "
        "the count. The storefront merger control (§ 754(c)(2)) was seen once and has no rule. The row is "
        "right: further review.",
    ),
    "D24": (
        "nighttime_entertainment=not_returned",
        "Returned: changing the conditions of the 1996 approval, and intensifying an existing use. Not "
        "returned: Nighttime Entertainment. The record facts say the entertainment use already exists and "
        "continues, and the rules do not apply the nighttime entertainment trigger to a use that continues; "
        "they read it under enlarging or intensifying. The motion makes the Table 719 Nighttime Entertainment "
        "findings. The row is right: further review.",
    ),
}
# A trigger the rules raise on the record facts that is no item of the case. Key: (case, trigger).
FALSE_TRIGGER_NOTES: dict[tuple[str, str], str] = {
    ("N10", "T8"): (
        "The storefront the bar expands into was a dry cleaner, and the filing date is inside the laundromat "
        "rule's period (2021-12-20 to 2024-12-20). The record never raises § 202.12. Either the record missed "
        "it or the dry cleaner was not the last use; the record does not say. A hearing was needed in any case."
    ),
    ("N13", "T7"): (
        "14,139 square feet against a threshold of 6,000. The rules read the uses as new, so use size applies. "
        "Planning approved by letter without a hearing: an existing space, not enlarged. This is the one case "
        "where a trigger outside the inventory would have asked for a hearing and none was required."
    ),
    ("D09", "T3"): (
        "The record facts say the existing restaurant is enlarged (the outdoor area), and a new Restaurant is "
        "conditional here, so the rules also read it as enlarging a conditional use (§ 178). The motion rests "
        "on the outdoor activity area and on § 249.60(c)(3), expansion of a liquor establishment: the same "
        "event under other sections."
    ),
    ("D10", "T3"): (
        "As D09: the existing restaurant is enlarged by the outdoor area, and the rules also read it under "
        "§ 178. The motion rests on the outdoor activity area and § 249.60(c)(3)."
    ),
    ("D20", "T3"): (
        "The record facts call the licence upgrade an intensification, so the rules also raise § 178. The "
        "inventory checked this: § 178 appears once in the motion, in the basis-for-approval sentence, and is "
        "the same licence change in other words. Today the North Beach licence rule is gone, and this trigger "
        "alone keeps the row at further review."
    ),
}
# The same on the description. Key: case.
INPUT_RAISED_NOTES: dict[str, str] = {
    "N13": (
        "As on the record facts, now that the intake answer gives the floor area: 14,139 square feet against a "
        "threshold of 6,000, read as a new use. Planning approved by letter without a hearing (an existing "
        "space, not enlarged)."
    ),
    "D02": (
        "The intake answer gives the floor area: 2,008 square feet, over North Beach's 2,000. The description "
        "says the space is a restaurant and not whether it changes, and in North Beach on this date a new "
        "Conditional Use is needed to change a use over the threshold, so the threshold is read: conditional. "
        "On the record facts it is not raised: the existing restaurant does not change and the floor area does "
        "not grow."
    ),
    "D20": (
        "As D02: the intake answer gives 2,570 square feet, over North Beach's 2,000, and the threshold is read: "
        "conditional. The inventory notes Restaurant to Restaurant with no enlargement; on the record facts the "
        "floor area does not grow, and there it is not raised."
    ),
    "D10": "As on the record facts: the enlarged restaurant is also read under § 178.",
    "D16": (
        "The description does not say the earlier business was a bar, so the Bar is read as new: conditional "
        "under § 249.60(b)(2)(C). A hearing was required, on another ground (the legacy business control, which "
        "has no rule)."
    ),
}
# An item the rules return on the record facts and do not find on the description. Key: (case, item).
INPUT_GAP_NOTES: dict[tuple[str, str], str] = {
    ("N03", "nighttime_entertainment"): (
        "Only the hand-stated § 102 use makes it Nighttime Entertainment, and the product has no field for it. "
        "Read through a profile the description holds no entertainment use, so the trigger says nothing."
    ),
    ("D05", "nighttime_entertainment"): (
        "As N03: Nighttime Entertainment comes only from the hand-stated § 102 use, which a profile does not carry."
    ),
    ("D05", "new_use_control"): (
        "Read through a profile the description gives no kind of business the rules read, so the use control "
        "names what kind of business it is."
    ),
    ("D07", "new_use_control"): (
        "The description says an existing restaurant and does not say whether that business stays, so the rules "
        "name that instead of reading the Restaurant as new. The record's ground is Limited Restaurant to "
        "Restaurant, which the description does not give."
    ),
    ("D09", "alcohol_licence_in_restricted_district"): (
        "The description is one sentence about turning a parking lot into a dining patio. It does not say "
        "there is a restaurant, or that it is enlarged. The intake answer says a licence is already held at the "
        "address, so the licence rules are read for a business that exists, and the rule for expanding a liquor "
        "establishment (§ 249.60(c)(3)) is not reached without a use that is enlarged."
    ),
    ("D12", "laundromat_removal"): (
        "The description says the restaurant expands into the vacant retail space next door. It does not say "
        "that space was last a laundromat."
    ),
    ("D14", "nighttime_entertainment"): (
        "The description names no story, so the rules read the first story: conditional. The second story "
        "made it not permitted at filing."
    ),
    ("D17", "amend_prior_conditions"): "The description does not mention an earlier approval.",
    ("D17", "enlarge_or_intensify_existing_use"): (
        "The input facts hold no change to an existing business, so the trigger for enlarging or intensifying "
        "one does not apply."
    ),
    ("D17", "nighttime_entertainment"): "The description does not say what kind of entertainment there is.",
    ("D23", "alcohol_licence_in_restricted_district"): (
        "The description is 'wants an ABC Type 42 licence': not whether the licence is new, nor what the "
        "space is used as."
    ),
    ("D24", "enlarge_or_intensify_existing_use"): (
        "The description does not say a business continues (the space is long vacant), so the rules read "
        "Nighttime Entertainment as a new use and find it under that trigger instead."
    ),
}
# A trigger that reads differently today. Key: (case, trigger).
TODAY_NOTES: dict[tuple[str, str], str] = {
    ("N06", "T4"): "Not in the inventory. Not decided at filing (no licence type in the record facts).",
    ("N10", "T8"): "A possible false trigger at filing; the rule ended 2024-12-20.",
    ("D05", "T6"): (
        "The row stays not permitted: the rules still read use size as not permitted. From 2023-12-10 the "
        "table exempts Article 10 Landmark buildings in the Castro NCD; the rules print that exemption and do "
        "not apply it."
    ),
    ("D20", "T4"): (
        "The licence rule ended with the North Beach Special Use District. The row stays at further review "
        "because the rules also raise § 178 (see the possible false triggers)."
    ),
    ("D23", "T1"): (
        "The inventory (code text of 2026-09-23) reads conditional today. The table in force from 2026-08-23 "
        "adds exceptions for a bar that already existed in the district; the rules cannot rule them out, "
        "although the record facts say the space was retail."
    ),
}
# Points for whoever owns the rules. Nothing here was changed. Each names the case and the text it rests on.
RULE_POINTS: tuple[tuple[str, str], ...] = (
    (
        "D24: the nighttime entertainment trigger is not read for a use that continues",
        'Spec section 1a writes "does not apply to a use that already exists and continues" for T1 and T2 '
        'only. `triggers.py` applies it to T6 as well. Motion No. 21811 makes "§719 findings for '
        'Entertainment, Nighttime on the Ground Floor" for a venue it calls "a continuation of existing '
        'Nighttime Entertainment Use". The row is still further review, through T3 and T10.',
    ),
    (
        "D05 and N13: an existing use the table does not carry",
        "T3 reads only Bar, Restaurant, Limited Restaurant and Nighttime Entertainment as existing uses. For "
        'a movie theatre (D05) or an adult business (N13) it says "no use the rule table covers continues" '
        "and reads the proposed uses as new. In D05 that loses the § 182(b) ground the motion cites (Motion "
        'No. 21334: "PURSUANT TO PLANNING CODE SECTIONS 182(b), 303, and 715"). In N13 it makes use size apply '
        "to a space that is not enlarged, which Planning did not do.",
    ),
    (
        "D04: T3 does not read formula retail as what makes a use conditional",
        'Motion No. 21149, finding 6.D: "The Project proposes to enlarge an existing Formula Retail Use". '
        "The existing restaurant is a conditional use only because it is formula retail. T3 reads the "
        "Restaurant row, which is principal at filing and today, so it answers principal.",
    ),
    (
        "D23, today: exceptions for a bar that already existed are left open",
        "From 2026-08-23 (Ord. 130-26) Table 737 carries exceptions for a liquor establishment that already "
        "existed and reopens, and for a Bar that already existed and moves inside the district. With a last "
        'use of retail stated, T1 still answers not decided, naming "whether this is a bar that already '
        'existed in the Third Street district and is reopening or moving".',
    ),
    (
        "D05, today: the landmark exemption from use size is printed, not applied",
        'Table 715 Note 1, as the dated data carries it from 2023-12-10 (Ord. 225-23): "the use size limitation does not '
        'apply to Article 10 Landmark buildings in the Castro NCD". The Castro Theatre is Landmark No. 100. '
        "The rules print the exemption and still answer not permitted for 24,138 square feet. No input says a "
        "building is an Article 10 Landmark.",
    ),
    (
        "D19: no way to state what a concept pours",
        'The Haight rule reads a named licence type. Motion No. 21688: "to allow a Restaurant Use which will '
        'sell on-sale alcoholic beverages on the ground floor"; the project description says on-sale beer and '
        "wine at a bona fide eating place. The rules can derive Type 41 from a restaurant that pours beer and "
        "wine, but the facts objects of backtest/inputs.json have no key for it, so the record facts cannot "
        "carry it.",
    ),
    (
        "D03, N13, D15: use size for a new use in a space that is not enlarged",
        "The Commission applied use size to a new restaurant in an existing 4,440 square foot building (D15, "
        "Motion No. 21546, under Table 727). It made no use size finding for a new Bar in an existing 5,478 square "
        "foot space (D03), and Planning approved N13 (14,139 square feet) by letter. The rules now read "
        "Zoning Administrator Interpretation 121.2 (use_size_general): D03, whose record facts give the floor "
        "area before and no merger, reads does not apply. N13 (the last use is not one the rules carry) and D15 "
        "still read the threshold.",
    ),
    (
        "N05, D02, D07, D17, D20 on the description: an existing business that may continue",
        "Spec section 1a takes a business as continuing when `changes_existing_business` is stated or a "
        'record shows the use. A description that says "an existing restaurant that holds a Type 41 licence" '
        "states the last use and neither of those. The rules no longer read such a use as new: the use controls "
        "answer not decided, naming whether an existing business is to be enlarged or intensified. In the "
        "product a licence on file at the address would show the use; this run reads no site record.",
    ),
)


# ---- the document -------------------------------------------------------------------------------------------------
def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out.extend("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)
    return out


def _control(control: str | None) -> str:
    return CONTROL_WORDS[control] if control else "none"


def _short(phrase: str) -> str:
    """A long name for what is missing, cut at its first colon (the list of limits or streets follows it)."""
    return phrase.split(": ", 1)[0] if len(phrase) > 100 else phrase


def _missing(row: Mapping[str, Any]) -> str:
    return "; ".join(_short(m) for m in row.get("missing", []))


def _record_cell(row: Mapping[str, Any]) -> str:
    result = row["result"]
    if result == "returned":
        return f"returned ({_control(row['rules_control'])})"
    if result == "not_decided":
        return f"not decided: {_missing(row)}"
    if result == "no_rule":
        return "no rule"
    return f"{RESULT_WORDS[result]} (rules: {_control(row['rules_control'])})"


def _input_cell(row: Mapping[str, Any]) -> str:
    result = row["result"]
    if result == "found":
        return f"found ({_control(row['rules_control'])})"
    if result == "not_decided":
        return f"not decided: {_missing(row)}"
    if result == "no_rule":
        return "no rule"
    return f"{INPUT_WORDS[result]} (rules: {_control(row['rules_control'])})"


def _basis(basis: str) -> str:
    return {"stated_in_record": "stated", "inferred_from_code": "inferred", "applicant_claim_only": "claim"}[
        basis
    ]


def _signature(case: Mapping[str, Any]) -> str:
    return ", ".join(
        f"{r['item']}={r['result']}" for r in case["record_run"]["items"] if r["result"] != "returned"
    )


def _entry_name(entry: str) -> str:
    return re.split(r" \(|:|;|,", entry)[0].strip()


def _ids(cases: Iterable[Mapping[str, Any]]) -> str:
    return ", ".join(c["id"] for c in cases) or "none"


def document(result: Mapping[str, Any]) -> tuple[str, list[str]]:
    """The document, and the notes of this file that no longer match a result."""
    cases: list[dict[str, Any]] = result["cases"]
    counts = result["counts"]
    rule, inp = counts["rule_coverage"], counts["input_coverage"]
    stale: list[str] = []
    used: set[Any] = set()
    out: list[str] = []
    add = out.append
    today = result["today"]

    add("# How far the rules cover the 40 backtest cases")
    add("")
    add(
        "Written by `scripts/validation/backtest_coverage.py` from the trigger inventory "
        "([`backtest/triggers.json`](../../backtest/triggers.json)) and the hand-entered facts "
        "([`backtest/inputs.json`](../../backtest/inputs.json)). No model, no network, no database. Every case, "
        "every trigger and every run is in [`backtest/coverage.json`](../../backtest/coverage.json). Do not edit "
        "this file by hand: change the script and run it again."
    )
    add("")
    add(
        "The 40 cases are 25 decided by the Planning Commission and 15 that did not reach approval (withdrawn "
        "or cancelled). Coverage is defined in "
        "[`rule-table-extension-spec.md`](rule-table-extension-spec.md), section 5."
    )
    add("")

    # ---- the counts
    add("## The counts")
    add("")
    add(
        "**Rule coverage.** The rules are run on the facts in the decision record, on the day before filing. "
        "A case is fully covered when the rules return every trigger in the inventory with the control the "
        "inventory gives at filing, partly covered when they return some, not covered when they return none."
    )
    add("")
    every, stated = rule["every_item"], rule["items_stated_in_record_only"]

    def cover_row(label: str, tally: Mapping[str, int], *, none_stated: bool) -> list[Any]:
        return [
            label,
            tally["fully"],
            tally["partly"],
            tally["not"],
            tally["none_stated"] if none_stated else "",
        ]

    groups = counts["groups"]
    add_rows = [
        cover_row("**Every trigger in the inventory**, all 40 cases", every["all"], none_stated=False),
        cover_row(f"- decided ({groups['decided']})", every["decided"], none_stated=False),
        cover_row(
            f"- did not reach approval ({groups['did_not_reach_approval']})",
            every["did_not_reach_approval"],
            none_stated=False,
        ),
        cover_row(
            "**Only triggers a decision document names**, all 40 cases", stated["all"], none_stated=True
        ),
        cover_row(f"- decided ({groups['decided']})", stated["decided"], none_stated=True),
        cover_row(
            f"- did not reach approval ({groups['did_not_reach_approval']})",
            stated["did_not_reach_approval"],
            none_stated=True,
        ),
    ]
    out.extend(
        _table(
            ["", "Fully covered", "Partly covered", "Not covered", "No trigger stated in the record"],
            add_rows,
        )
    )
    add("")
    add(
        "The second count leaves out the triggers the readers inferred from the code (no decision document "
        "names them) and the one that is an applicant's claim only. A case with no other trigger is in the "
        "last column."
    )
    add("")
    it = rule["items"]
    add(
        f'By trigger: the inventory holds {counts["items"]} (one per family per case, see "How the comparison is '
        f'made"). The rules return {it["every_item"]["returned"]}. Of the {counts["items_stated_in_record"]} '
        f"stated in a record they return {it['stated_in_record']['returned']}; of the "
        f"{counts['items'] - counts['items_stated_in_record']} inferred or claimed, "
        f"{it['inferred_or_claimed']['returned']}."
    )
    add("")
    out.extend(
        _table(
            ["Triggers", *[RESULT_WORDS[k].capitalize() for k in RESULT_WORDS]],
            [
                ["Every trigger", *[it["every_item"][k] for k in RESULT_WORDS]],
                ["Stated in the record", *[it["stated_in_record"][k] for k in RESULT_WORDS]],
                ["Inferred or claimed", *[it["inferred_or_claimed"][k] for k in RESULT_WORDS]],
            ],
        )
    )
    add("")
    cause = counts["by_cause"]
    pair_text = "; ".join(f"{pr['case']} ({pr['code']})" for pr in cause["pairs"])
    add(
        f"By cause: the inventory counts a hearing by cause once (its counting rule: one cause written in two "
        f"places of the code). Counted that way the {counts['items']} triggers are {cause['causes']} causes, and "
        f"the rules return {cause['returned']} (a pair counts as returned when both halves are). The pairs: "
        f"{pair_text}."
    )
    add("")
    fully_ids = [c["id"] for c in cases if c["record_run"]["coverage"] == "fully"]
    stated_fully = [c["id"] for c in cases if c["record_run"]["coverage_stated_in_record_only"] == "fully"]
    no_hearing = [cid for cid in ("N05", "N08", "N13", "N15") if cid in fully_ids]
    add(
        f"Of the {len(fully_ids)} fully covered cases, "
        + "; ".join(f"{cid} {HEADLINE_CAVEATS[cid]}" for cid in no_hearing)
        + f". Of the {len(stated_fully)} fully covered on the triggers a decision document names, "
        + "; ".join(f"{cid} {HEADLINE_CAVEATS[cid]}" for cid in ("N05", "N08", "N15") if cid in stated_fully)
        + "."
    )
    add("")
    alone = counts["input_coverage_without_the_intake_answers"]
    add(
        "**Input coverage.** The same rules on the same dates, run on only what the neutral description "
        "states, read the way the product reads a description (through a profile: `facts.concept_facts("
        "facts.profile_from_facts(...))`), with the optional intake questions answered where the case file "
        "states the fact (`intake_answers` in the inputs file, applied as the product applies them: "
        "`app.memo.intake.apply_intake_answers`, then `normalized()`). "
        f"{len(alone['cases_with_intake_answers'])} cases answer at least one question. The same run without "
        "the answers is counted beside it. Fully found means every trigger in the inventory is found with the "
        "control at filing."
    )
    add("")
    ie, ae = inp["every_item"], alone["every_item"]
    keys3 = ("fully", "partly", "not")
    out.extend(
        _table(
            ["", "Fully found", "Partly found", "None found"],
            [
                ["**With the intake answers**, all 40 cases", *[ie["all"][k] for k in keys3]],
                [f"- decided ({groups['decided']})", *[ie["decided"][k] for k in keys3]],
                [
                    f"- did not reach approval ({groups['did_not_reach_approval']})",
                    *[ie["did_not_reach_approval"][k] for k in keys3],
                ],
                ["**The description alone**, all 40 cases", *[ae["all"][k] for k in keys3]],
                [f"- decided ({groups['decided']})", *[ae["decided"][k] for k in keys3]],
                [
                    f"- did not reach approval ({groups['did_not_reach_approval']})",
                    *[ae["did_not_reach_approval"][k] for k in keys3],
                ],
            ],
        )
    )
    add("")
    ii, ai = inp["items"], alone["items"]
    gap = inp["rules_cover_input_does_not"]
    add(
        f"By trigger, with the intake answers: {ii['found']} found, {ii['not_decided']} not decided (the rules "
        f"name the missing input), {ii['missed']} missed (the rules say nothing), {ii['different_control']} "
        f"found with a different control, {ii['no_rule']} with no rule. The description alone: {ai['found']} "
        f"found, {ai['not_decided']} not decided, {ai['missed']} missed, {ai['different_control']} with a "
        f"different control, {ai['no_rule']} with no rule. The cases whose triggers the answers change: "
        f"{', '.join(alone['cases_that_differ']) or 'none'}. Everything below is the run with the answers."
    )
    add("")
    su = counts["input_coverage_with_the_stated_use"]
    sue, sui = su["every_item"]["all"], su["items"]
    add(
        f"With the § 102 use handed to the rules by hand (the inputs file's `planning_use`, which the product "
        f"has no field for): fully found {sue['fully']}, partly {sue['partly']}, none {sue['not']}; by trigger "
        f"{sui['found']} found, {sui['not_decided']} not decided, {sui['missed']} missed, "
        f"{sui['different_control']} with a different control. The cases that differ: "
        f"{', '.join(su['cases_that_differ']) or 'none'}."
    )
    add("")
    add(
        f"**The rules cover it and the input does not:** {gap['items']} triggers in {gap['cases']} cases are "
        f"returned on the record facts and not found on the description. "
        f"{gap['cases_fully_covered_by_the_rules_and_not_fully_found']} of those cases are fully covered by the "
        "rules. They are listed below."
    )
    add("")
    false = counts["possible_false_triggers"]
    add(
        f"**Possible false triggers:** on the record facts the rules raise {false['record_run']} triggers the "
        f"inventory does not have, in {false['record_run_cases']} cases. On the description they raise "
        f"{false['input_run']}, in {false['input_run_cases']} cases."
    )
    add("")
    add(
        f"**Dating the rules:** read for {today} instead of the filing date, at least one trigger reads "
        f"differently in {counts['today']['cases_where_a_trigger_reads_differently']} cases, and the zoning row "
        f"changes in {counts['today']['cases_where_the_zoning_row_differs']}."
    )
    add("")
    rows_then = counts["zoning_row_on_record_facts_at_filing"]
    allowed = [c for c in cases if c["record_run"]["zoning_row"] == "allowed"]
    profile_rows = counts["record_facts_through_the_product_path"]["zoning_row_differs"]
    stated_only = [cid for cid in _ids(allowed).split(", ") if cid in profile_rows]
    add(
        "**What the zoning row would have read** on the record facts at filing: "
        + ", ".join(f"{ROW_WORDS[k]} {v}" for k, v in rows_then.items() if v)
        + f". The {len(allowed)} that read allowed ({_ids(allowed)}) needed a hearing: in each the only trigger "
        "is one with no rule."
        + (
            f" {', '.join(stated_only)} reads allowed only with the § 102 use stated by hand; without it the row "
            f"reads {ROW_WORDS[profile_rows[stated_only[0]][1]]}."
            if stated_only
            else ""
        )
    )
    add("")

    # ---- not fully covered
    add("## Cases not fully covered, and why")
    add("")
    for word in ("not", "partly"):
        group = [c for c in cases if c["record_run"]["coverage"] == word]
        add(f"**{COVERAGE_WORDS[word].capitalize()} ({len(group)}):**")
        add("")
        for case in group:
            note = CASE_NOTES.get(case["id"])
            if note is None or note[0] != _signature(case):
                stale.append(f"CASE_NOTES[{case['id']!r}] does not match {_signature(case)!r}")
                text = "No note on file for this result. Not returned: " + _signature(case) + "."
            else:
                used.add(("case", case["id"]))
                text = note[1]
            add(f"- **{case['id']}** ({case['district']['code']}, {GROUP_WORDS[case['group']]}). {text}")
        add("")
    for cid in CASE_NOTES:
        if ("case", cid) not in used:
            stale.append(f"CASE_NOTES[{cid!r}] is not used: the case is fully covered or the result changed")

    # ---- per-case table
    add("## Every case")
    add("")
    add(
        "One line per trigger in the inventory. Basis: stated (a decision document names it), inferred (the "
        "readers derived it from the code), claim (the applicant's theory, which Planning did not adopt). "
        '"At filing" is the inventory\'s control. The two coverage columns are for the whole case.'
    )
    add("")
    headers = [
        "Case",
        "District",
        "Trigger in the inventory",
        "Basis",
        "At filing",
        "Rules on the record facts",
        "Rules on the description",
        "Rule coverage",
        "Input coverage",
    ]
    input_cover = {"fully": "fully found", "partly": "partly found", "not": "none found"}
    for group_key in ("decided", "did_not_reach_approval"):
        group = [c for c in cases if c["group"] == group_key]
        add(f"### {GROUP_WORDS[group_key].capitalize()} ({len(group)})")
        add("")
        rows: list[list[Any]] = []
        for case in group:
            inputs_by_item = {r["item"]: r for r in case["input_run"]["items"]}
            for n, row in enumerate(case["record_run"]["items"]):
                first = n == 0
                rows.append(
                    [
                        case["id"] if first else "",
                        case["district"]["code"] if first else "",
                        FAMILY_LABELS[row["item"]],
                        _basis(row["basis"]),
                        _control(row["inventory_control"]),
                        _record_cell(row),
                        _input_cell(inputs_by_item[row["item"]]),
                        COVERAGE_WORDS[case["record_run"]["coverage"]] if first else "",
                        input_cover[case["input_run"]["coverage"]] if first else "",
                    ]
                )
        out.extend(_table(headers, rows))
        add("")
    add(
        "N08: the inventory's control at filing is principal (a first-story Restaurant in CVR became "
        "principally permitted eight days before the listed filing date), and the rules return principal."
    )
    stories = [(c["id"], s) for c in cases for s in c["record_run"]["each_story"]]
    if stories:
        add("")
        add(
            "Where the inventory gives one entry per story, each story was also read on its own: "
            + "; ".join(
                f"{cid} {s['story']} story, inventory {_control(s['inventory_control'])}, rules "
                f"{_control(s['rules_control'])}"
                for cid, s in stories
            )
            + "."
        )
    add("")

    # ---- by family
    add("## Triggers the rules do not return, by family")
    add("")
    family_rows: list[list[Any]] = []
    for key, tally in result["by_family"].items():
        missed = result["not_returned_by_family"].get(key, [])
        trigger = FAMILY_TO_TRIGGER.get(key, "none")
        family_rows.append(
            [
                FAMILY_LABELS[key],
                trigger,
                tally["items"],
                tally["returned"],
                tally["found_on_the_description"],
                "; ".join(
                    f"{m['case']} {RESULT_WORDS[m['result']]}"
                    + (f" ({'; '.join(_short(x) for x in m['missing'])})" if m["missing"] else "")
                    for m in missed
                )
                or "",
            ]
        )
    out.extend(
        _table(
            [
                "Family",
                "Rule",
                "In the inventory",
                "Returned on the record facts",
                "Found on the description",
                "Not returned",
            ],
            family_rows,
        )
    )
    add("")

    # ---- rules cover, input does not
    add("## The rules cover it; the description does not give the deciding fact")
    add("")
    add(
        'Triggers the rules return on the record facts and do not find on the description. "Not decided" '
        'means the report would name the missing input. "Missed" means it would say nothing about this '
        "trigger."
    )
    add("")
    gap_rows: list[list[Any]] = []
    for case in cases:
        for g in case["input_run"]["rules_cover_input_does_not"]:
            key = (case["id"], g["item"])
            lacks = INPUT_GAP_NOTES.get(key)
            if lacks is None:
                stale.append(f"INPUT_GAP_NOTES has no note for {key!r}")
            else:
                used.add(("gap", key))
            named = "; ".join(_short(m) for m in g["missing"])
            gap_rows.append(
                [
                    case["id"],
                    FAMILY_LABELS[g["item"]],
                    INPUT_WORDS[g["input_result"]]
                    + (
                        f": {named}"
                        if named
                        else f" (rules: {_control(g['rules_control_on_the_description'])})"
                    ),
                    lacks or "",
                    ROW_WORDS[case["input_run"]["zoning_row"]],
                ]
            )
    out.extend(
        _table(
            [
                "Case",
                "Trigger",
                "On the description",
                "What the description lacks",
                "Zoning row on the description",
            ],
            gap_rows,
        )
    )
    for key in INPUT_GAP_NOTES:
        if ("gap", key) not in used:
            stale.append(f"INPUT_GAP_NOTES[{key!r}] is not used")
    add("")
    reverse = [
        (c["id"], r["item"])
        for c in cases
        for r, i in zip(c["record_run"]["items"], c["input_run"]["items"], strict=True)
        if r["result"] != "returned" and i["result"] == "found"
    ]
    if reverse:
        add(
            "The other way round (found on the description, not returned on the record facts): "
            + "; ".join(f"{cid}, {FAMILY_LABELS[item]}" for cid, item in reverse)
            + "."
        )
        add("")
    add(
        "Every other trigger that is not found on the description is also not returned on the record facts; "
        "those are in the list of cases above."
    )
    add("")
    dec = counts["found_but_the_deciding_fact_is_not_described"]
    add(
        "**Found on the description, but the deciding fact is not in it** (spec section 5 lists these apart):"
    )
    add("")
    dec_rows = [
        [c["id"], f"{m['trigger']} {FAMILY_LABELS[m['item']].lower()}", m["why"]]
        for c in cases
        for m in c["input_run"]["found_but_the_deciding_fact_is_not_described"]
    ]
    out.extend(_table(["Case", "Trigger", "Why"], dec_rows))
    add("")
    add(
        "Picked from the readers' `input_missing` entries that say a fact decides the case, and confirmed by "
        f"hand. Fully found: {dec['fully_found']} with them, {dec['fully_found_without_them']} without the "
        f"cases they are in. The use control of the zoning district on the description: "
        f"{dec['new_use_control_found']} of {dec['new_use_control_items']} found, "
        f"{dec['new_use_control_found_without_them']} without these. Each case's own candidate entries are in "
        "`coverage.json` (`input_missing_entries_that_say_they_decide`)."
    )
    add("")

    # ---- possible false triggers
    add("## Possible false triggers")
    add("")
    add(
        "A trigger the rules raise (conditional or not permitted) that the inventory does not list for the "
        'case. "Inventory note" is what the inventory\'s `considered_not_triggers`, or a settlement note of '
        "the record facts, says about the same ground."
    )
    add("")
    add("**On the record facts:**")
    add("")
    false_rows: list[list[Any]] = []
    for case in cases:
        for extra in case["record_run"]["raised_outside_the_inventory"]:
            key = (case["id"], extra["trigger"])
            happened = FALSE_TRIGGER_NOTES.get(key)
            if happened is None:
                stale.append(f"FALSE_TRIGGER_NOTES has no note for {key!r}")
            else:
                used.add(("false", key))
            said = extra["inventory_notes"] + extra["settlement_notes"]
            false_rows.append(
                [
                    case["id"],
                    f"{extra['trigger']} {TRIGGER_LABELS[extra['family']].lower()}",
                    _control(extra["control"]),
                    happened or "",
                    " / ".join(said) if said else "none speaks to it",
                ]
            )
    out.extend(_table(["Case", "Trigger", "Rules", "What happened", "Inventory note"], false_rows))
    for key in FALSE_TRIGGER_NOTES:
        if ("false", key) not in used:
            stale.append(f"FALSE_TRIGGER_NOTES[{key!r}] is not used")
    add("")
    wrong = [(c["id"], w) for c in cases for w in c["record_run"]["wrong_ground_inside_a_returned_trigger"]]
    if wrong:
        add(
            "**A wrong ground inside a returned trigger** (flagged by hand against the inventory's "
            "`considered_not_triggers`): " + " ".join(f"{cid} {w['trigger']}: {w['why']}" for cid, w in wrong)
        )
        add("")
    add("**On the description:**")
    add("")
    input_rows: list[list[Any]] = []
    for case in cases:
        raised = case["input_run"]["raised_outside_the_inventory"]
        if not raised:
            continue
        why_raised = INPUT_RAISED_NOTES.get(case["id"])
        if why_raised is None:
            stale.append(f"INPUT_RAISED_NOTES has no note for {case['id']!r}")
        else:
            used.add(("raised", case["id"]))
        input_rows.append(
            [
                case["id"],
                ", ".join(f"{e['trigger']} {_control(e['control'])}" for e in raised),
                why_raised or "",
            ]
        )
    out.extend(_table(["Case", "Raised", "Why"], input_rows))
    for cid in INPUT_RAISED_NOTES:
        if ("raised", cid) not in used:
            stale.append(f"INPUT_RAISED_NOTES[{cid!r}] is not used")
    add("")
    add(SITE_RECORDS_NOTE)
    add("")

    # ---- today
    add(f"## What dating the rules changes: the record facts read for {today}")
    add("")
    add(
        f'"Today" is {today}, the day the dated control data was read. The inventory\'s "today" is the code '
        "text of 2026-09-23. Principal and does not apply both ask for nothing and are not listed as a "
        "difference."
    )
    add("")
    today_rows: list[list[Any]] = []
    for case in cases:
        for n, diff in enumerate(case["today_run"]["differs_from_filing"]):
            key = (case["id"], diff["trigger"])
            if key in TODAY_NOTES:
                used.add(("today", key))
            changed = diff["changed_on"] or ""
            if diff["ordinance"]:
                changed += f" ({diff['ordinance']})"
            today_rows.append(
                [
                    case["id"] if n == 0 else "",
                    f"{diff['trigger']} {TRIGGER_LABELS[diff['family']].lower()}",
                    _control(diff["at_filing"]),
                    _control(diff["today"]),
                    changed,
                    _control(diff["inventory_control_today"])
                    if diff["in_inventory"]
                    else "not in the inventory",
                    (
                        f"{ROW_WORDS[case['record_run']['zoning_row']]} -> "
                        f"{ROW_WORDS[case['today_run']['zoning_row']]}"
                        if n == 0
                        else ""
                    ),
                    TODAY_NOTES.get(key, ""),
                ]
            )
    out.extend(
        _table(
            [
                "Case",
                "Trigger",
                "Rules at filing",
                "Rules today",
                "Changed on",
                "Inventory, today",
                "Zoning row, filing -> today",
                "Note",
            ],
            today_rows,
        )
    )
    for key in TODAY_NOTES:
        if ("today", key) not in used:
            stale.append(f"TODAY_NOTES[{key!r}] is not used")
    add("")
    add(
        "Where the zoning row goes from further review to insufficient information, the trigger that required "
        "the hearing no longer does, and what is left is an input the record facts do not give (most often "
        "whether the business is part of a chain)."
    )
    add("")
    silent: list[str] = []
    for case in cases:
        differing = {d["trigger"] for d in case["today_run"]["differs_from_filing"]}
        for item in case["inventory"]["items"]:
            changed_entries = [
                e for e in item["entries"] if e["permission_changed_since_filing"] not in (None, "no")
            ]
            if changed_entries and item["trigger"] not in differing:
                why = (
                    "no rule"
                    if item["trigger"] is None
                    else "; ".join(
                        dict.fromkeys(
                            "a Historic Building question the rules do not evaluate"
                            if e["permission_changed_since_filing"] == "depends_on_historic_building_status"
                            else f'the inventory reads "{e["control_today_as_written"]}" today'
                            for e in changed_entries
                        )
                    )
                )
                silent.append(f"{case['id']}, {item['label']} ({why})")
    add(
        "The inventory records a change, or a possible change, that the rules do not show: "
        + "; ".join(silent)
        + "."
    )
    add("")

    # ---- left open
    add("## Inputs the rules ask for that the inventory does not turn on")
    add("")
    add(
        "Triggers outside the inventory that come back not decided. They are not false triggers. Where nothing "
        "else is conditional they set the zoning row to insufficient information."
    )
    add("")
    open_counts: dict[tuple[str, str], dict[str, list[str]]] = {}
    for case in cases:
        for run in ("record_run", "input_run"):
            for extra in case[run]["left_open_outside_the_inventory"]:
                for name in extra["missing"] or [_control(extra["control"])]:
                    slot = open_counts.setdefault(
                        (extra["trigger"], _short(name)), {"record_run": [], "input_run": []}
                    )
                    slot[run].append(case["id"])
    open_rows = [
        [trigger, name, len(found["record_run"]), len(found["input_run"]), ""]
        for (trigger, name), found in sorted(
            open_counts.items(), key=lambda kv: (int(kv[0][0][1:]), kv[0][1])
        )
    ]
    inside: dict[tuple[str, str], list[str]] = {}
    for case in cases:
        for run in ("record_run", "input_run"):
            for row in case[run]["items"]:
                for name in row.get("missing_in_the_trigger", []):
                    slot = inside.setdefault((row["trigger"], _short(name)), [])
                    if case["id"] not in slot:
                        slot.append(case["id"])
    for (trigger, name), ids in sorted(inside.items()):
        open_rows.append([trigger, name, "", "", ", ".join(ids)])
    out.extend(
        _table(
            ["Trigger", "Not known", "Cases, record facts", "Cases, description", "In a returned trigger"],
            open_rows,
        )
    )
    add("")
    if inside:
        add(
            "In a returned trigger: the input a trigger that is returned still names, on both runs. The share "
            "of commercial frontage decides conditional against not permitted under § 249.59(d)(1) (above 35% "
            "the uses are prohibited)."
        )
        add("")

    # ---- rule points
    add("## Points for the rules, found on the way (nothing was changed)")
    add("")
    for title, text in RULE_POINTS:
        add(f"- **{title}.** {text}")
    add("")

    # ---- how
    add("## How the comparison is made")
    add("")
    add(
        "- **Three runs per case**, all through `app.memo.triggers.evaluate`: the record facts on the day "
        f"before filing; the description's facts on the same day; the record facts on {today}."
    )
    prof = counts["record_facts_through_the_product_path"]
    add(
        "- **The § 102 use.** The record run hands the rules the inputs file's `planning_use` (the decision "
        "record classifies the use); the product has no field for it. Through the product's path the record "
        f"facts give: fully {prof['every_item']['all']['fully']}, partly {prof['every_item']['all']['partly']}, "
        f"not {prof['every_item']['all']['not']}; {prof['returned']} returned of {counts['items']}. The cases "
        f"that differ: {', '.join(prof['cases_that_differ']) or 'none'}"
        + (
            "; the zoning row differs in "
            + ", ".join(
                f"{cid} ({ROW_WORDS[a]} -> {ROW_WORDS[b]})"
                for cid, (a, b) in prof["zoning_row_differs"].items()
            )
            if prof["zoning_row_differs"]
            else ""
        )
        + ". The input run uses the product's path."
    )
    add(
        "- **By cause.** One cause written in two places counts once (triggers.json `notes.counting_rules`): "
        + "; ".join(f"{pr['case']}, {pr['code']}" for pr in counts["by_cause"]["pairs"])
        + ". Of the special district use control, most items are such mirrors of the district's use control."
    )
    add(
        "- **Families.** "
        + "; ".join(f"{FAMILY_LABELS[f]} -> {t}" for f, t in FAMILY_TO_TRIGGER.items())
        + ". Three families were seen once and have no rule: "
        + "; ".join(f"{FAMILY_LABELS[f]} ({s})" for f, s in NO_RULE_FAMILIES.items())
        + "."
    )
    add(
        "- **One item per family per case.** Two entries of one family count once, with the more severe "
        "control, which is how the rules combine several readings of one trigger (D05 and D14: first and "
        "second story; N09: the formula retail baseline and the district prohibition). The change-of-operator "
        "rule (N04, N15) is counted on its own, as no rule: spec section 1a says the rules print it as a note."
    )
    add(
        "- **Controls.** An inventory control written with a qualifier is read by its first word; the full "
        "text is kept in the output. Returned means the same control; principal and does not apply count as "
        "the same."
    )
    add(f"- **Site records.** {SITE_RECORDS_NOTE}")
    add(
        "- **District and special districts.** The zoning district is the code at the start of the "
        "inventory's district at filing. Each special district the inventory lists is matched by the Planning "
        "Code section it names to the product's special use district table. The rows are built from the rule "
        "table the product uses, as `tests/test_pathway_cases.py` builds them, and looked up through the "
        "file-backed store at one notional point. No control is typed into the script."
    )
    mapping = result["mapping"]
    add(
        "- **Not mapped.** "
        + (
            "Districts the dated control data does not carry: "
            + ", ".join(mapping["districts_not_in_the_dated_control_data"])
            + ". "
            if mapping["districts_not_in_the_dated_control_data"]
            else "Every district of the 40 is in the dated control data and matches the district on the Planning "
            "record. "
            if not mapping["districts_that_differ_from_the_planning_record"]
            else "Every district of the 40 is in the dated control data. "
        )
        + "Sections the inventory names that the product's table has no row for: "
        + "; ".join(mapping["sections_named_without_a_row"])
        + ". An entry the inventory places on today's map, or that names no section (a cultural district, a "
        "landmark, an area plan), builds no row."
    )
    add(
        "- **Check.** Each run is repeated with only the special district rows a rule reads. The answers are "
        "the same in all 40 cases; the script stops if they are not."
    )
    add("")
    add("### District and special districts, case by case")
    add("")
    map_rows: list[list[Any]] = []
    for case in cases:
        special = case["special_districts"]
        left: list[str] = []
        for entry in special["mapping"]:
            if entry.get("left_out"):
                name = _entry_name(entry["inventory"])
                left.append(
                    "none named at filing; the entry lists today's map"
                    if name.startswith("None")
                    else f"{name}: {entry['left_out']}"
                )
            for section in entry.get("sections_without_a_row", {}):
                left.append(f"§ {section}: no row")
        map_rows.append(
            [
                case["id"],
                case["district"]["code"],
                ", ".join(special["rows_built"]) or "none",
                ", ".join(
                    [
                        *[r["name"] for r in special["read_by_the_rules"]],
                        *(
                            ["Central SoMa Special Use District (read by the MUR rows)"]
                            if CENTRAL_SOMA_ROW in special["rows_built"]
                            else []
                        ),
                    ]
                )
                or "none",
                "; ".join(left) or "",
            ]
        )
    out.extend(
        _table(
            ["Case", "District", "Special district rows built", "Read by the rules", "No row built"], map_rows
        )
    )
    add("")

    # ---- limits
    add("## Limits")
    add("")
    add(
        "- The comparison is on controls. A trigger counted as returned gives the inventory's control; the "
        "sentence of the code it rests on was not compared with the motion's."
    )
    add(
        "- The facts are hand-entered. Where the record facts leave a fact empty the rules answer not "
        "decided, even where the record implies the fact (D19)."
    )
    add(
        "- The Historic Buildings rule (§ 202.11, from 2026-04-11) is not evaluated; the rules print a line "
        "where it could change an answer."
    )
    add(
        "- Three cases needed no hearing in the end (N05, N13, N15) and one was principal at filing (N08). "
        "They are counted by the inventory's trigger entries like every other case. N05: the rules return the "
        "North Beach licence trigger (conditional) as the inventory gives it at filing, and the Department then "
        "approved the same request without a Conditional Use as a continuation, so the zoning row (further "
        "review) is not what happened. In N13, and in N05 and N15, the rules ask for a hearing where none was "
        "required in the end (N13 on a trigger outside the inventory, N05 and N15 inside it)."
    )
    add(
        "- The not-permitted rows of D05 and D14 are right at filing; the Commission approved those parts under "
        "Ord. 225-23 (Eff. 12/10/2023), as the inventory's open_points record."
    )
    unc = counts["without_the_inventory_coded_facts"]
    add(
        "- Two record facts restate the inventory's own trigger entry rather than the record: "
        + "; ".join(
            f"{cid}, {INVENTORY_CODED_FACTS[cid][0]} ({INVENTORY_CODED_FACTS[cid][1]})"
            for cid in unc["cases"]
        )
        + f". With them cleared: fully covered {unc['every_item']['all']['fully']}, partly "
        f"{unc['every_item']['all']['partly']}, not {unc['every_item']['all']['not']}; {unc['returned']} "
        f"returned; enlarging or intensifying returned {unc['enlarge_or_intensify_returned']} of "
        f"{unc['enlarge_or_intensify_items']}; possible false triggers on the record {unc['possible_false_triggers']} "
        f"in {unc['possible_false_trigger_cases']} cases. Changing an earlier approval is stated in both motions "
        "and is not affected."
    )
    add("")
    return "\n".join(out), stale


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--today", type=dt.date.fromisoformat, default=None, help="default: the day the control data was read"
    )
    parser.add_argument(
        "--check", action="store_true", help="write nothing; exit 1 if either file would change"
    )
    args = parser.parse_args(argv)
    result = build(args.today if args.today is not None else data_read_on())
    data = json.dumps(result, indent=1, ensure_ascii=False) + "\n"
    text, stale = document(result)
    for line in stale:
        print(f"note out of date: {line}", file=sys.stderr)
    if args.check:
        changed = [
            str(path.relative_to(REPO))
            for path, new in ((OUT_JSON, data), (OUT_DOC, text))
            if not path.exists() or path.read_text(encoding="utf-8") != new
        ]
        print("would change: " + ", ".join(changed) if changed else "both files are up to date")
        return 1 if changed or stale else 0
    OUT_JSON.write_text(data, encoding="utf-8")
    OUT_DOC.write_text(text, encoding="utf-8")
    print(json.dumps(result["counts"], indent=1))
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
