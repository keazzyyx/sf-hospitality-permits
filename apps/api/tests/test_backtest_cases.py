"""The backtest case loader (app.backtest.cases) on another case file: its own inputs and motion numbers, and the
trigger inventory read from its triggers.json when the folder has no coverage.json. Synthetic files only; no rule is
run and the holdout's own files are not read."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from app.backtest import cases

CASES_YAML = """\
cases:
  - id: H98
    group: decided
    record: "2099-000098CUA"
    address: "1 Test St, San Francisco, CA 94100"
    filed: 2024-03-05
    outcome: approved_with_conditions
    concept_input: "A liquor store."
  - id: H99
    group: did_not_reach_approval
    record: "2099-000099CUA"
    address: "2 Test St, San Francisco, CA 94100"
    filed: 2024-07-23
    outcome: withdrawn
    concept_input: "A new licence."
"""


def _trigger(family: str, control: str, basis: str = "stated_in_record") -> dict[str, object]:
    return {"family": family, "sub_rule": None, "basis": basis, "control_at_filing": control,
            "control_today": control}  # fmt: skip


def _write(folder: Path) -> Path:
    (folder / "cases.yaml").write_text(CASES_YAML)
    facts = {"business_type": "other"}
    (folder / "inputs.json").write_text(json.dumps({"cases": {
        cid: {"filed": filed, "rules_date": rules, "input_facts": facts, "record_facts": facts,
              "intake_answers": {"floor_area_sqft": 900}}
        for cid, filed, rules in (("H98", "2024-03-05", "2024-03-04"), ("H99", "2024-07-23", "2024-07-22"))
    }}))  # fmt: skip
    (folder / "triggers.json").write_text(json.dumps({"cases": [
        {"id": "H98", "net_result_at_filing": "conditional", "controls_changed_since_filing": "no",
         "triggers": [_trigger("formula_retail", "conditional"),
                      _trigger("formula_retail", "principal (administrative)", "inferred_from_code"),
                      _trigger("landmark_use_in_residential_district", "conditional")]},
        {"id": "H99", "net_result_at_filing": "not_permitted", "controls_changed_since_filing": "no",
         "triggers": [_trigger("alcohol_licence_in_restricted_district", "not_permitted", "inferred_from_code")]},
    ]}))  # fmt: skip
    (folder / "motions.json").write_text(json.dumps({"cases": {"H98": {"motion_number": "29998"}}}))
    return folder / "cases.yaml"


def test_another_case_file_reads_its_own_folder(tmp_path: Path) -> None:
    loaded = {c.id: c for c in cases.load_cases(_write(tmp_path))}
    assert sorted(loaded) == ["H98", "H99"]
    h98, h99 = loaded["H98"], loaded["H99"]
    assert h98.case_dir == tmp_path.resolve()
    assert h98.rules_date == dt.date(2024, 3, 4) and h98.intake_answers == {"floor_area_sqft": 900}
    assert h98.motion_number == "29998"  # from the folder's own motions.json, for the leak guard
    assert h99.motion_number is None
    assert (h98.expected_zoning, h99.expected_zoning) == ("further_review", "not_permitted")
    assert h98.coverage == ""  # no rule coverage without a coverage.json


def test_inventory_from_triggers_one_item_per_family(tmp_path: Path) -> None:
    _write(tmp_path)
    inv = cases.inventory_from_triggers(tmp_path)["H98"]["inventory"]
    assert inv["net_result_at_filing"] == "conditional"
    items = {i["family"]: i for i in inv["items"]}
    assert list(items) == ["formula_retail", "landmark_use_in_residential_district"]
    fr = items["formula_retail"]
    assert fr["trigger"] == "T5" and fr["control_at_filing"] == "conditional" and len(fr["entries"]) == 2
    assert items["landmark_use_in_residential_district"]["trigger"] is None  # a family with no rule


def test_default_is_the_40() -> None:
    forty = cases.load_cases()
    assert len(forty) == 40 and all(c.case_dir == cases.BACKTEST for c in forty)


# ---- the supplied pathway (the conditional run) carries no headline from the rules it replaces --------------------
def test_the_supplied_pathway_drops_the_rules_headline_findings() -> None:
    """Review of 2026-11-16: the supplied run replaced the zoning row but kept the rules' headline findings, so a
    memo whose supplied pathway needs no Conditional Use still led with "The concept needs a Conditional Use
    Authorization" (2301 Chestnut St, first story, no licence on file: T7 asks for one by the rules)."""
    from types import SimpleNamespace

    from app.backtest.run import supply_pathway
    from app.memo.pathway import overall_line
    from app.models.memo import STATUS_SEVERITY
    from tests.test_memo_headline import profile, report

    det = report(profile(stories=["first"], last_use="other"))
    assert [h.kind for h in det.headline_findings] == ["conditional"]
    for expected in ("allowed", "further_review", "not_permitted", "unclear"):
        case = SimpleNamespace(expected_zoning=expected, cov={"inventory": {"items": []}})
        got = supply_pathway(det, case)
        assert got.headline_findings == [], expected
        assert got.overall_line == overall_line(got.rows), expected
        assert not got.overall_line.startswith(("A Conditional Use", "Zoning does not permit")), expected
        assert got.overall_status == min((r.status for r in got.rows), key=STATUS_SEVERITY.index), expected
