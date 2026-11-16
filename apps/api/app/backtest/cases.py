"""The 40 backtest cases and what each run is given (docs/validation/backtest-plan.md §1, §7, §8).

Reads backtest/cases.yaml (address, neutral concept text, record number, outcome, why closed), backtest/inputs.json
(rules date, input facts, record facts, intake answers) and backtest/coverage.json (the trigger inventory as the
coverage script read it, and the rule coverage of each case).

Another case file (the 20 holdout cases, backtest/holdout/cases.yaml) is read the same way from its own folder:
its inputs.json and motions.json sit beside it. Where that folder has no coverage.json (the rule coverage is written
by running the rules, which is not done on the holdout before it is scored), the trigger inventory is read from its
triggers.json instead, with the family-to-trigger names of backtest/coverage.json; the coverage is then "".

THE CORRECT PATHWAY (for the conditional run and for scoring "missed pathways"). From the inventory's net result
at filing (`inventory.net_result_at_filing`), two independent readings of each decision record under the code in
force at filing. Most read "conditional". The ones written out in words are settled here, each with its reason:
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml

ROOT = Path(__file__).resolve().parents[4]
BACKTEST = ROOT / "backtest"
DEFAULT_CASE_FILE = BACKTEST / "cases.yaml"
HOLDOUT_CASE_FILE = BACKTEST / "holdout" / "cases.yaml"

ExpectedZoning = Literal["further_review", "not_permitted", "allowed", "unclear"]

# The net results written in words, settled to the zoning row the rules should give on the rules date.
SETTLED: dict[str, tuple[ExpectedZoning, str]] = {
    "N05": ("further_review", "conditional on the code text; the Department later approved the same request "
            "without a Conditional Use as a continuation"),
    "N08": ("allowed", "no Conditional Use needed on the listed filing date (2024-01-22); it was conditional on "
            "the earlier project application date"),
    "N11": ("further_review", "conditional unless all five § 202.2(a)(7) limits are met; the record does not "
            "say which was exceeded"),
    "N13": ("allowed", "no Conditional Use needed, as Planning decided; the applicant's own theory would give "
            "conditional"),
    "N14": ("unclear", "conditional only if the business is Formula Retail, which the record does not settle; "
            "a report that says it cannot tell (naming chain status) is right"),
    "N15": ("allowed", "no Conditional Use needed: the change of formula-retail operator was approved "
            "administratively"),
    "D05": ("not_permitted", "mixed at filing: conditional for the first-story nighttime entertainment and the "
            "bar, not permitted for the second-story nighttime entertainment and the addition"),
    "D14": ("not_permitted", "mixed at filing: conditional for the first-story nighttime entertainment and use "
            "size, not permitted for the second-story nighttime entertainment until 2023-12-10"),
}  # fmt: skip


@dataclass(frozen=True)
class Case:
    id: str
    group: str  # "decided" or "did_not_reach_approval"
    record: str
    address: str
    filed: dt.date
    rules_date: dt.date
    outcome: str
    concept_input: str
    intake_answers: dict[str, Any]
    input_facts: dict[str, Any]
    record_facts: dict[str, Any]
    expected_zoning: ExpectedZoning
    expected_note: str
    coverage: str  # the rule coverage on the record's facts: fully / partly / not
    yaml: dict[str, Any]
    inputs: dict[str, Any]
    cov: dict[str, Any]
    case_dir: Path = BACKTEST  # the folder of the case file: its motions.json is read for the leak guard

    @property
    def motion_number(self) -> str | None:
        """The case's own motion number (motions.json beside the case file, read from the motion PDF); None for a
        case that did not reach approval."""
        m = _motions(self.case_dir).get(self.id, {}).get("motion_number")
        return str(m) if m else None


def _expected(case_id: str, net: str) -> tuple[ExpectedZoning, str]:
    if case_id in SETTLED:
        return SETTLED[case_id]
    word = net.strip().split()[0].rstrip(",;:")
    table: dict[str, ExpectedZoning] = {"conditional": "further_review", "not_permitted": "not_permitted",
                                        "principal": "allowed", "no_cu_needed": "allowed"}  # fmt: skip
    if word not in table:
        raise ValueError(f"{case_id}: net result {net!r} is not settled in SETTLED")
    return table[word], net


@cache
def _motions(case_dir: Path = BACKTEST) -> dict[str, Any]:
    path = case_dir / "motions.json"
    return dict(json.loads(path.read_text())["cases"]) if path.exists() else {}


SEVERITY = ("not_permitted", "conditional", "unclear", "principal")  # most severe first


def _rank(control: str) -> int:
    return SEVERITY.index(control) if control in SEVERITY else len(SEVERITY)


def inventory_from_triggers(case_dir: Path) -> dict[str, dict[str, Any]]:
    """The trigger inventory of each case in case_dir/triggers.json, in the shape backtest/coverage.json gives it
    (net result at filing and one item per family; two entries of one family are one item with the more severe
    control), with the family-to-trigger names of backtest/coverage.json. No rule is run."""
    mapping = json.loads((BACKTEST / "coverage.json").read_text())["mapping"]
    to_trigger, labels = mapping["family_to_trigger"], mapping["trigger_labels"]
    out: dict[str, dict[str, Any]] = {}
    for c in json.loads((case_dir / "triggers.json").read_text())["cases"]:
        items: dict[str, dict[str, Any]] = {}
        for t in c["triggers"]:
            fam = t["family"]
            word = str(t["control_at_filing"]).strip().split()[0].rstrip(",;:")
            item = items.setdefault(fam, {"key": fam, "family": fam, "entries": [], "trigger": to_trigger.get(fam),
                                          "label": labels.get(to_trigger.get(fam, ""), fam),
                                          "control_at_filing": word, "basis": t["basis"]})  # fmt: skip
            item["entries"].append({"sub_rule": t.get("sub_rule"), "basis": t["basis"], "control_at_filing": word,
                                    "control_today": t.get("control_today")})  # fmt: skip
            if _rank(word) < _rank(item["control_at_filing"]):
                item["control_at_filing"] = word
            if t["basis"] == "stated_in_record":
                item["basis"] = "stated_in_record"
        out[c["id"]] = {
            "id": c["id"],
            "inventory": {
                "net_result_at_filing": c["net_result_at_filing"],
                "controls_changed_since_filing": c.get("controls_changed_since_filing"),
                "items": list(items.values()),
            },
        }
    return out


@cache
def load_cases(case_file: Path | None = None) -> tuple[Case, ...]:
    """The cases of case_file (default backtest/cases.yaml, the 40), with the inputs.json, coverage.json (or
    triggers.json) and motions.json of its folder."""
    path = Path(case_file) if case_file is not None else DEFAULT_CASE_FILE
    case_dir = path.resolve().parent
    ys = {c["id"]: c for c in yaml.safe_load(path.read_text())["cases"]}
    inputs = json.loads((case_dir / "inputs.json").read_text())["cases"]
    if (case_dir / "coverage.json").exists():
        cov = {c["id"]: c for c in json.loads((case_dir / "coverage.json").read_text())["cases"]}
    else:
        cov = inventory_from_triggers(case_dir)
    out = []
    for cid, y in ys.items():
        i, c = inputs[cid], cov[cid]
        status, note = _expected(cid, c["inventory"]["net_result_at_filing"])
        out.append(
            Case(
                id=cid,
                group=y["group"],
                record=y["record"],
                address=y["address"],
                filed=dt.date.fromisoformat(str(i["filed"])),
                rules_date=dt.date.fromisoformat(str(i["rules_date"])),
                outcome=y["outcome"],
                concept_input=y["concept_input"],
                intake_answers=dict(i.get("intake_answers") or {}),
                input_facts=dict(i["input_facts"]),
                record_facts=dict(i["record_facts"]),
                expected_zoning=status,
                expected_note=note,
                coverage=str(c.get("record_run", {}).get("coverage") or c.get("coverage") or ""),
                yaml=y,
                inputs=i,
                cov=c,
                case_dir=case_dir,
            )
        )
    return tuple(out)


def case(case_id: str, case_file: Path | None = None) -> Case:
    for c in load_cases(case_file):
        if c.id == case_id:
            return c
    raise KeyError(case_id)
