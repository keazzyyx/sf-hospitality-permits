"""The backtest scorer (app.backtest.score) on small synthetic cases and result files: unsupported findings from
the citation check's outcomes, the score-side missing-input phrases, a last use of only "vacant", the "unclear"
pathway of N14, the trigger comparison, the unknown-status group, the materially unsafe cases and the --case-file
option."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from app.backtest import score
from app.backtest.cases import Case
from app.memo.facts import MISSING_PHRASES
from app.memo.rows import EXISTING_GROUP_PHRASE
from app.memo.triggers import NOT_KNOWN

OUTDOOR_LIMITS = NOT_KNOWN["outdoor_limits"].format(limits="on the ground level; seated areas only")
CHAIN = MISSING_PHRASES["formula_retail"]


def make_case(
    cid: str = "D99",
    *,
    group: str = "decided",
    expected: str = "further_review",
    items: list[dict[str, Any]] | None = None,
    input_facts: dict[str, Any] | None = None,
    record_facts: dict[str, Any] | None = None,
    answers: dict[str, Any] | None = None,
) -> Case:
    return Case(
        id=cid, group=group, record="2099-000001CUA", address="1 Test St, San Francisco, CA 94100",
        filed=dt.date(2023, 1, 1), rules_date=dt.date(2023, 1, 1), outcome="approved_with_conditions",
        concept_input="A restaurant.", intake_answers=answers or {}, input_facts=input_facts or {},
        record_facts=record_facts or {}, expected_zoning=expected, expected_note="test",  # type: ignore[arg-type]
        coverage="fully", yaml={}, inputs={}, cov={"inventory": {"items": items or []}},
    )  # fmt: skip


def rows_data(*rows: dict[str, Any], triggers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"rows": list(rows), "triggers": triggers or [], "verification": None}


def ii_row(area: str, *missing: str) -> dict[str, Any]:
    return {
        "area": area,
        "status": "insufficient_information",
        "status_note": None,
        "missing_inputs": list(missing),
    }


def outcome(verdict: str | None, result: str) -> dict[str, Any]:
    return {"item_id": "x", "verdict": verdict, "result": result}


# ---- 2. unsupported findings from the outcomes -----------------------------------------------------------------
def test_unsupported_counts_the_first_pass_verdict_not_the_result() -> None:
    ver = {
        "summary": {"checked": 7, "supported": 1, "trimmed": 1, "downgraded": 3, "dropped": 2},
        "outcomes": [
            outcome("unsupported", "downgraded"),
            outcome("unsupported", "dropped"),
            outcome("partially_supported", "trimmed"),
            outcome("partially_supported", "downgraded"),  # the cut failed: lost its citation
            outcome("partially_supported", "dropped"),  # the cut failed: removed
            outcome("partially_supported", "downgraded"),
            outcome("supported", "kept"),
            outcome(None, "not_checked"),
        ],
    }
    v = score.verification_counts(ver)
    assert v is not None
    # the summary's (downgraded + dropped) would give 5; only 2 were unsupported outright
    assert v["checked"] == 7
    assert v["unsupported"] == 2
    assert v["partly_cut"] == 1
    assert v["partly_failed"] == 3
    assert (v["partly_failed_lost_citation"], v["partly_failed_removed"]) == (2, 1)
    assert v["kept"] == 1
    assert v["not_checked"] == 1
    assert v["unsupported_share"] == round(2 / 7, 3)
    assert v["overclaim_share"] == round(6 / 7, 3)


def test_unsupported_read_from_a_result_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(score, "RESULTS", tmp_path)
    c = make_case()
    e2e = tmp_path / c.id / "e2e"
    e2e.mkdir(parents=True)
    memo = {"approvals": [{"area": "zoning_use", "status": "further_review"}], "pathway": {"triggers": []}}
    (e2e / "memo.json").write_text(json.dumps(memo))
    ver = {
        "summary": {"checked": 2},
        "outcomes": [outcome("partially_supported", "dropped"), outcome("supported", "kept")],
    }
    (e2e / "verification.json").write_text(json.dumps(ver))
    data = score.load_set(c, "full_e2e")
    assert data is not None
    s = score.score_set(c, "full_e2e", data)
    assert s["verification"]["unsupported"] == 0
    assert s["verification"]["partly_failed"] == 1
    assert s["verification"]["overclaim_share"] == 0.5
    assert score.load_set(c, "full_conditional") is None


def test_supported_not_kept_and_not_checked_are_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(score, "RESULTS", tmp_path)
    c = make_case()
    e2e = tmp_path / c.id / "e2e"
    e2e.mkdir(parents=True)
    memo = {"approvals": [{"area": "zoning_use", "status": "further_review"}], "pathway": {"triggers": []}}
    (e2e / "memo.json").write_text(json.dumps(memo))
    ver = {
        "outcomes": [
            outcome("supported", "downgraded"),  # supported, but not kept as written
            outcome("unsupported", "dropped"),
            outcome("supported", "kept"),
            outcome(None, "not_checked"),
            outcome(None, "not_checked"),
        ]
    }
    (e2e / "verification.json").write_text(json.dumps(ver))
    data = score.load_set(c, "full_e2e")
    assert data is not None
    scores = {c.id: {w: (score.score_set(c, w, data) if w == "full_e2e" else None) for w in score.SETS}}
    table = "\n".join(score.measure_table((c,), scores, "full_e2e"))
    assert "| Supported, not kept as written | 1/3 (33%) |" in table
    assert "| Over-claiming (not kept as written) | 2/3 (67%) |" in table
    assert "| Not checked (no first-pass verdict; not in the shares above) | 2 |" in table
    per_case = score.summary((c,), scores)
    # checked 3: unsupported 1, partly cut 0, cut failed 0, supported not kept 1, kept 1, not kept 2, not checked 2
    assert "| 3 | 1 | 0 | 0 (0 / 0) | 1 | 1 | 2 (67%) | 2 |" in per_case


def test_a_run_whose_checker_calls_all_failed_is_not_dropped() -> None:
    v = score.verification_counts({"outcomes": [outcome(None, "not_checked")] * 3})
    assert v is not None
    assert (v["checked"], v["not_checked"], v["overclaim_share"]) == (0, 3, None)


# ---- 3. the fixed phrases that are not inputs --------------------------------------------------------------------
def test_score_side_phrases_map() -> None:
    assert score.phrase_key(EXISTING_GROUP_PHRASE) == "occupancy_group"
    assert score.phrase_key(OUTDOOR_LIMITS) == "outdoor_limits"
    # the chain phrase backtest/run.py supplies on an "unclear" zoning row
    assert score.phrase_key(MISSING_PHRASES["formula_retail"]) == "formula_retail"
    assert score.phrase_key(NOT_KNOWN["use_not_covered"]) == "use_not_covered"
    assert (
        score.phrase_key(NOT_KNOWN["table_rows"].format(rows="Limited Commercial Uses (§ 186)"))
        == "table_rows"
    )
    assert score.phrase_key("something no rule says") is None


def test_occupancy_group_is_always_correct_and_outdoor_limits_read_the_outdoor_facts() -> None:
    c = make_case(
        input_facts={
            "outdoor_area": "parking_lot",
            "planning_use": "restaurant",
            "existing_use_stated": "restaurant",
        },
        record_facts={"outdoor_area": "rooftop", "planning_use": "restaurant"},
    )
    data = rows_data(
        ii_row("building_change_of_use", EXISTING_GROUP_PHRASE), ii_row("outdoor", OUTDOOR_LIMITS)
    )
    e2e = {i["fact"]: i["result"] for i in score.score_set(c, "rules_e2e", data)["insufficient"]}
    assert e2e == {"occupancy_group": "correct", "outdoor_limits": "correct"}
    # the record states a rooftop area: one limit is settled as broken
    cond = {i["fact"]: i["result"] for i in score.score_set(c, "rules_conditional", data)["insufficient"]}
    assert cond == {"occupancy_group": "correct", "outdoor_limits": "wrong"}


def test_table_rows_given_when_the_existing_use_text_names_a_row() -> None:
    phrase = NOT_KNOWN["table_rows"].format(
        rows="Limited Corner Commercial Uses (§ 231) and Limited Commercial Uses (§§ 186, 186.3)"
    )
    assert score.table_rows_named(phrase) == ["Limited Corner Commercial Use", "Limited Commercial Use"]
    c = make_case(
        input_facts={"existing_use_text": "An existing restaurant"},
        record_facts={
            "existing_use_text": "Restaurant, a legally nonconforming Limited Commercial Use under § 186"
        },
    )
    data = rows_data(ii_row("hours", phrase))
    assert score.score_set(c, "rules_e2e", data)["insufficient"][0]["result"] == "correct"
    assert score.score_set(c, "rules_conditional", data)["insufficient"][0]["result"] == "wrong"


def test_a_rule_gap_is_a_wrong_insufficient_when_the_input_names_the_business() -> None:
    c = make_case(input_facts={"business_type": "food_truck"})
    data = rows_data(ii_row("health", NOT_KNOWN["use_not_covered"]))
    assert score.score_set(c, "rules_e2e", data)["insufficient"][0]["result"] == "wrong"


def test_an_unmapped_phrase_is_listed_and_fails_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = make_case()
    s = score.score_set(c, "rules_e2e", rows_data(ii_row("health", "a phrase nobody wrote down")))
    assert s["insufficient"][0]["result"] == "unmapped"
    unmapped = score.unmapped_phrases({c.id: {"rules_e2e": s}})
    assert unmapped == [(c.id, "rules_e2e", "health", "a phrase nobody wrote down")]

    monkeypatch.setattr(score, "RESULTS", tmp_path)
    monkeypatch.setattr(score, "load_cases", lambda case_file=None: (c,))
    (tmp_path / c.id).mkdir()
    det = {"rows": [ii_row("health", "a phrase nobody wrote down")], "pathway": {"triggers": []}}
    (tmp_path / c.id / "rules_only_e2e.json").write_text(json.dumps({"determinations": det}))
    assert score.main() == 1
    assert "| Unmapped missing-input phrases | 1 |" in (tmp_path / "summary.md").read_text()


# ---- 5. a last use of only "vacant" --------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("stated", "result"),
    [
        (["vacant"], "correct"),
        ("vacant", "correct"),
        (None, "correct"),
        (["vacant", "retail"], "wrong"),
        ("restaurant", "wrong"),
    ],
)
def test_vacant_alone_does_not_give_the_last_use(stated: Any, result: str) -> None:
    c = make_case(input_facts={"existing_use_stated": stated})
    data = rows_data(ii_row("building_change_of_use", MISSING_PHRASES["existing_use_stated"]))
    assert score.score_set(c, "rules_e2e", data)["insufficient"][0]["result"] == result


# ---- 6 and 7. the zoning row: supplied in the conditional sets; N14 must name chain status -------------------------
def test_n14_is_right_only_when_the_zoning_row_names_chain_status() -> None:
    c = make_case("N14", group="did_not_reach_approval", expected="unclear")
    named = rows_data(ii_row("zoning_use", CHAIN))
    other = rows_data(ii_row("zoning_use", MISSING_PHRASES["closing"]))
    count = rows_data(ii_row("zoning_use", MISSING_PHRASES["other_locations"]))
    decided = rows_data(
        {"area": "zoning_use", "status": "further_review", "status_note": None, "missing_inputs": []}
    )
    assert score.score_set(c, "rules_e2e", named)["pathway"] == "right"
    assert score.score_set(c, "rules_e2e", count)["pathway"] == "right"
    assert score.score_set(c, "rules_e2e", other)["pathway"] == "missed"
    assert score.score_set(c, "rules_e2e", decided)["pathway"] == "missed"


def test_conditional_sets_supply_the_pathway_and_leave_the_zoning_row_out() -> None:
    c = make_case(record_facts={})
    data = rows_data(ii_row("zoning_use", CHAIN), ii_row("hours", MISSING_PHRASES["closing"]))
    s = score.score_set(c, "rules_conditional", data)
    assert s["pathway"] == "supplied"
    assert [i["row"] for i in s["insufficient"]] == ["hours"]
    assert [i["row"] for i in score.score_set(c, "rules_e2e", data)["insufficient"]] == [
        "zoning_use",
        "hours",
    ]


# ---- 8. the trigger comparison, as backtest_coverage.py result_of --------------------------------------------------
def test_trigger_results_follow_result_of() -> None:
    items = [
        {"family": "a", "label": "same control", "trigger": "T1", "control_at_filing": "conditional"},
        {"family": "b", "label": "both ask nothing", "trigger": "T2", "control_at_filing": "principal"},
        {"family": "c", "label": "other control", "trigger": "T3", "control_at_filing": "not_permitted"},
        {"family": "d", "label": "not decided", "trigger": "T4", "control_at_filing": "conditional"},
        {"family": "e", "label": "practice", "trigger": "T5", "control_at_filing": "conditional"},
        {"family": "f", "label": "asks nothing", "trigger": "T6", "control_at_filing": "conditional"},
        {"family": "g", "label": "returned nothing", "trigger": "T7", "control_at_filing": "conditional"},
        {"family": "h", "label": "no rule", "trigger": None, "no_rule": "not built", "control_at_filing": "conditional"},
        {"family": "i", "label": "nothing where nothing asked", "trigger": "T9", "control_at_filing": "does_not_apply"},
    ]  # fmt: skip
    triggers = [
        {"rule_id": "T1", "control": "conditional"},
        {"rule_id": "T2", "control": "does_not_apply"},
        {"rule_id": "T3", "control": "conditional"},
        {"rule_id": "T4", "control": "not_decided", "missing_inputs": ["the closing time"]},
        {"rule_id": "T5", "control": "code_and_practice_differ"},
        {"rule_id": "T6", "control": "principal"},
        {"rule_id": "T10", "control": "not_permitted", "label": "Outside"},
        {"rule_id": "T11", "control": "conditional", "label": "Also outside"},
        {"rule_id": "T12", "control": "not_decided"},
    ]
    c = make_case(items=items)
    got = {t["item"]: t["result"] for t in score.score_triggers(c, triggers)}
    assert got == {
        "same control": "found",
        "both ask nothing": "found",
        "other control": "different_control",
        "not decided": "unknown",
        "practice": "practice_differs",
        "asks nothing": "missed",
        "returned nothing": "missed",
        "no rule": "missed",
        # None is no longer read as asking nothing: a trigger that returned nothing is not returned
        "nothing where nothing asked": "missed",
    }
    whys = {t["item"]: t["why"] for t in score.score_triggers(c, triggers)}
    assert whys["returned nothing"].startswith("not returned")
    assert whys["no rule"].startswith("no rule")
    assert [r["trigger"] for r in score.raised_outside(c, triggers)] == ["T10", "T11"]


def test_totals_count_different_control_apart_and_keep_practice_out_of_the_share() -> None:
    items = [
        {"family": "a", "label": "x", "trigger": "T1", "control_at_filing": "conditional"},
        {"family": "b", "label": "y", "trigger": "T2", "control_at_filing": "conditional"},
        {"family": "c", "label": "z", "trigger": "T3", "control_at_filing": "conditional"},
    ]
    triggers = [{"rule_id": "T1", "control": "conditional"}, {"rule_id": "T2", "control": "not_permitted"},
                {"rule_id": "T3", "control": "code_and_practice_differ"}]  # fmt: skip
    c = make_case(items=items)
    s = score.score_set(c, "rules_e2e", rows_data(triggers=triggers))
    t = score.totals((c,), {c.id: {"rules_e2e": s}}, "rules_e2e")
    assert (t["crit_found"], t["crit_different_control"], t["crit_practice_differs"]) == (1, 1, 1)
    assert t.get("crit_missed", 0) == 0
    table = "\n".join(score.measure_table((c,), {c.id: {"rules_e2e": s}}, "rules_e2e"))
    assert "| Critical issues found | 1/2 (50%) |" in table
    assert "| Critical issues raised with a different control | 1 |" in table


# ---- 1 and 9. the unknown-status group and the sensitivity check ---------------------------------------------------
def test_unknown_status_group_and_sensitivity_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(score, "RESULTS", tmp_path)
    a, b, c = make_case("D97"), make_case("D98"), make_case("D99")
    for case, unknown in ((a, ["1", "2"]), (b, ["3"]), (c, [])):
        (tmp_path / case.id).mkdir()
        (tmp_path / case.id / "leakage.json").write_text(
            json.dumps({"licences_unknown_at_the_address": unknown})
        )
    assert score.unknown_group_label((a, b, c)) == "2 cases (3 licences)"
    det = {"rows": [{"area": "alcohol", "status": "allowed"}], "pathway": {"triggers": []}}
    alt = {"rows": [{"area": "alcohol", "status": "further_review"}]}
    (tmp_path / a.id / "rules_only_e2e.json").write_text(json.dumps({"determinations": det}))
    (tmp_path / a.id / "rules_only_conditional.json").write_text(json.dumps({"determinations": det}))
    (tmp_path / a.id / "sensitivity_unknown_as_active.json").write_text(
        json.dumps({"e2e": alt, "conditional": det})
    )
    out = "\n".join(score.sensitivity((a, b, c)))
    assert "Checked 1 of 3 cases; an answer changes in 1 of them (D97)." in out
    assert "Unknown-status group (2 cases (3 licences)): checked 1 of 2; an answer changes in 1 (D97)." in out
    assert "| unknown-status group | D98 |" in out
    assert "| other cases | D99 |" in out
    assert "| D97 | 0 (2) | end to end | row alcohol | status | allowed | further_review |" in out


def _sensitivity_files(tmp: Path, case: Case, base: dict[str, Any], alt: dict[str, Any]) -> None:
    (tmp / case.id).mkdir(exist_ok=True)
    (tmp / case.id / "leakage.json").write_text(json.dumps({"licences_unknown_at_the_address": ["1"]}))
    for name in ("rules_only_e2e.json", "rules_only_conditional.json"):
        (tmp / case.id / name).write_text(json.dumps({"determinations": base}))
    (tmp / case.id / "sensitivity_unknown_as_active.json").write_text(
        json.dumps({"e2e": alt, "conditional": base})
    )


def _det(t1: str, missing: list[str], basis: list[str] | None = None) -> dict[str, Any]:
    row = {"area": "building_change_of_use", "status": "insufficient_information", "status_note": None,
           "missing_inputs": missing, "basis": [{"text": t} for t in basis or []]}  # fmt: skip
    trig = [{"rule_id": "T1", "label": "Use control", "control": t1}]
    return {"rows": [row], "pathway": {"triggers": trig}}


def test_sensitivity_counts_a_trigger_control_change_when_the_statuses_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(score, "RESULTS", tmp_path)
    c = make_case(
        "D97", items=[{"family": "new_use_control", "trigger": "T1", "control_at_filing": "principal"}]
    )
    _sensitivity_files(tmp_path, c, _det("principal", ["x"]), _det("does_not_apply", ["x"]))
    ch = score.sensitivity_changes(c)
    assert ch is not None
    assert [(d["kind"], d["left_out"], d["active"], d["inventory"]) for d in ch["answer"]] == [
        ("trigger", "principal", "does_not_apply", True)
    ]
    out = "\n".join(score.sensitivity((c,)))
    assert "Checked 1 of 1 cases; an answer changes in 1 of them (D97)." in out
    assert (
        "| D97 | 0 (1) | end to end | trigger T1 Use control (inventory) | control | principal | does_not_apply |"
        in out
    )
    assert "| trigger controls (inventory) | 1 |" in out


def test_sensitivity_counts_a_missing_input_change_and_keeps_text_only_changes_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(score, "RESULTS", tmp_path)
    a, b = make_case("D97"), make_case("D98")
    last_use, enlarged = "what the space was last used as", "whether an existing business is to be enlarged"
    _sensitivity_files(tmp_path, a, _det("principal", [last_use, "y"]), _det("principal", ["y", enlarged]))
    # same answer; the lines differ only in a count and in the disclosure line, which is left out
    disclosed = score.DISCLOSURE_LINE + "2022-03-09: 2 ABC licences within 1,000 ft"
    none = score.DISCLOSURE_LINE + "2022-03-09: none within 1,000 ft or in the census tract."
    _sensitivity_files(tmp_path, b, _det("principal", ["y"], ["52 active", disclosed]),
                       _det("principal", ["y"], ["65 active", none]))  # fmt: skip
    out = "\n".join(score.sensitivity((a, b)))
    assert f"| row building_change_of_use | missing inputs | {last_use} | {enlarged} |" in out
    assert "an answer changes in 1 of them (D97)." in out
    assert "| D98 | end to end | building_change_of_use | 1 |" in out
    assert "1 rows in 1 cases." in out
    # only the disclosure line differs: not a text change either
    c = make_case("D99")
    _sensitivity_files(
        tmp_path, c, _det("principal", ["y"], ["52", disclosed]), _det("principal", ["y"], ["52", none])
    )
    ch = score.sensitivity_changes(c)
    assert ch == {"answer": [], "text": []}


# ---- 10. materially unsafe cases ----------------------------------------------------------------------------------
UNSAFE_ITEMS = [
    {"family": "a", "label": "use control", "trigger": "T1", "control_at_filing": "conditional"},
    {"family": "b", "label": "entertainment", "trigger": "T6", "control_at_filing": "conditional"},
]


def _zoning(status: str = "further_review") -> dict[str, Any]:
    return {"area": "zoning_use", "status": status, "status_note": None, "missing_inputs": []}


def _unsafe(c: Case, which: str, *rows: dict[str, Any], t1: str, t6: str) -> dict[str, Any]:
    triggers = [
        {"rule_id": "T1", "control": t1},
        {"rule_id": "T6", "control": t6, "missing_inputs": ["kind"]},
    ]
    s = score.score_set(c, which, rows_data(*(rows or (_zoning(),)), triggers=triggers))
    u: dict[str, Any] = s["unsafe"]
    return u


def test_an_issue_listed_as_unknown_does_not_make_a_case_unsafe() -> None:
    c = make_case(items=UNSAFE_ITEMS)
    u = _unsafe(c, "rules_e2e", t1="conditional", t6="not_decided")
    assert u == {"unsafe": False, "issues": [], "false_blockers": []}
    # a trigger kept out as "Code and Planning practice differ" does not either
    assert not _unsafe(c, "rules_e2e", t1="conditional", t6="code_and_practice_differ")["unsafe"]


@pytest.mark.parametrize("t6", ["does_not_apply", "principal", "not_permitted"])
def test_a_missed_issue_or_a_different_control_makes_a_case_unsafe(t6: str) -> None:
    # does_not_apply / principal: missed (not returned); not_permitted: raised with a different control
    c = make_case(items=UNSAFE_ITEMS)
    u = _unsafe(c, "rules_e2e", t1="conditional", t6=t6)
    assert u == {"unsafe": True, "issues": ["entertainment"], "false_blockers": []}


def test_an_issue_with_no_rule_makes_a_case_unsafe() -> None:
    items = [
        *UNSAFE_ITEMS,
        {"family": "c", "label": "merger", "trigger": None, "control_at_filing": "conditional"},
    ]
    u = _unsafe(make_case(items=items), "rules_e2e", t1="conditional", t6="conditional")
    assert u["issues"] == ["merger"]


@pytest.mark.parametrize("want", ["principal", "does_not_apply"])
def test_a_missed_issue_whose_record_control_asks_nothing_does_not_make_a_case_unsafe(want: str) -> None:
    # N15: the change of operator was approved administratively (principal) and no rule covers it. It counts as
    # missed among the issues, but the record needed no hearing for it, so the case is not unsafe for it.
    items = [
        *UNSAFE_ITEMS,
        {"family": "c", "label": "change of operator", "trigger": None, "control_at_filing": want},
    ]
    c = make_case(items=items)
    trig = [{"rule_id": "T1", "control": "conditional"}, {"rule_id": "T6", "control": "conditional"}]
    s = score.score_set(c, "rules_e2e", rows_data(_zoning(), triggers=trig))
    assert [t["result"] for t in s["triggers"]] == ["found", "found", "missed"]
    assert s["unsafe"] == {"unsafe": False, "issues": [], "false_blockers": []}
    scores = {c.id: {w: (s if w == "rules_e2e" else None) for w in score.SETS}}
    t = score.totals((c,), scores, "rules_e2e")
    assert (t["crit_missed"], t.get("unsafe_cases", 0)) == (1, 0)
    # the same item with a record control that asks for something does make it unsafe
    items[-1] = {**items[-1], "control_at_filing": "conditional"}
    s = score.score_set(make_case(items=items), "rules_e2e", rows_data(_zoning(), triggers=trig))
    assert s["unsafe"]["issues"] == ["change of operator"]


def test_a_false_blocker_alone_makes_a_case_unsafe_only_where_blockers_are_scored() -> None:
    blocked = _zoning("not_permitted")
    decided = make_case(items=UNSAFE_ITEMS)
    u = _unsafe(decided, "full_e2e", blocked, t1="conditional", t6="conditional")
    assert u == {"unsafe": True, "issues": [], "false_blockers": ["zoning_use"]}
    # a case that did not reach approval for another reason is not scored for false blockers
    withdrawn = make_case(group="did_not_reach_approval", items=UNSAFE_ITEMS)
    assert not _unsafe(withdrawn, "full_e2e", blocked, t1="conditional", t6="conditional")["unsafe"]
    # the record's pathway is "not permitted": a blocker is not false
    prohibited = make_case(expected="not_permitted", items=UNSAFE_ITEMS)
    assert not _unsafe(prohibited, "full_e2e", blocked, t1="conditional", t6="conditional")["unsafe"]


def test_unsafe_count_and_share_by_set_and_group() -> None:
    a = make_case("D97", items=UNSAFE_ITEMS)  # unsafe: a missed issue
    b = make_case("D98", items=UNSAFE_ITEMS)  # safe: one issue listed as unknown
    c = make_case("N99", group="did_not_reach_approval", items=UNSAFE_ITEMS)  # unsafe: a different control
    triggers = {a.id: ("conditional", "does_not_apply"), b.id: ("conditional", "not_decided"),
                c.id: ("not_permitted", "conditional")}  # fmt: skip
    scores: dict[str, Any] = {}
    for case in (a, b, c):
        t1, t6 = triggers[case.id]
        trig = [{"rule_id": "T1", "control": t1}, {"rule_id": "T6", "control": t6}]
        s = score.score_set(case, "rules_e2e", rows_data(_zoning(), triggers=trig))
        scores[case.id] = {w: (s if w == "rules_e2e" else None) for w in score.SETS}
    t = score.totals((a, b, c), scores, "rules_e2e")
    assert (t["ran"], t["unsafe_cases"], t["unsafe_issue_cases"], t.get("unsafe_blocker_cases", 0)) == (
        3,
        2,
        2,
        0,
    )
    table = "\n".join(score.measure_table((a, b, c), scores, "rules_e2e"))
    unsafe_row = f"| Materially unsafe cases ({score.UNSAFE_DEFINITION_SHORT}) |"
    # all (3), decided (2), did not reach approval (1), unknown-status group (0), all others (3)
    assert f"{unsafe_row} 2/3 (67%) | 1/2 (50%) | 1/1 (100%) | 0/0 | 2/3 (67%) |" in table
    # the issue-level share sits next to it
    assert "| Critical issues found | 3/6 (50%) | 2/4 (50%) | 1/2 (50%) | 0/0 | 3/6 (50%) |" in table
    section = "\n".join(score.unsafe_section((a, b, c), scores))
    assert "| all (3) | not run | not run | unsafe 2/3 (67%); issues found 3/6 (50%) | not run |" in section
    assert "| D97 | Rules only, end to end | entertainment | none |" in section
    assert "| N99 | Rules only, end to end | use control | none |" in section
    assert "| D98 |" not in section
    assert "Cases with a missed pathway that are not counted as unsafe: none." in section


def test_a_missed_pathway_in_a_case_that_is_not_unsafe_is_listed() -> None:
    c = make_case(items=UNSAFE_ITEMS)
    s = score.score_set(c, "rules_e2e", rows_data(_zoning("allowed"), triggers=[
        {"rule_id": "T1", "control": "conditional"}, {"rule_id": "T6", "control": "not_decided"}]))  # fmt: skip
    assert s["pathway"] == "missed"
    assert not s["unsafe"]["unsafe"]
    scores = {c.id: {w: (s if w == "rules_e2e" else None) for w in score.SETS}}
    section = "\n".join(score.unsafe_section((c,), scores))
    assert "not counted as unsafe: D99 (Rules only, end to end)." in section


# ---- 11. --case-file: another case file is scored from its own results, never the 40's -----------------------------
def _write_rules_only(results: Path, c: Case) -> None:
    (results / c.id).mkdir(parents=True)
    det = {"rows": [_zoning()], "pathway": {"triggers": [{"rule_id": "T1", "control": "does_not_apply"},
                                                         {"rule_id": "T6", "control": "conditional"}]}}  # fmt: skip
    (results / c.id / "rules_only_e2e.json").write_text(json.dumps({"determinations": det}))


def test_case_file_scores_into_its_own_results_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    forty = tmp_path / "backtest" / "results"
    forty.mkdir(parents=True)
    monkeypatch.setattr(score, "RESULTS", forty)
    monkeypatch.setattr(score, "FORTY_RESULTS", forty)
    holdout = tmp_path / "backtest" / "holdout"
    case_file = holdout / "cases.yaml"
    holdout.mkdir()
    case_file.write_text("cases: []\n")
    c = make_case("H01", items=UNSAFE_ITEMS)
    seen: list[Path | None] = []

    def fake_load(case_file: Path | None = None) -> tuple[Case, ...]:
        seen.append(case_file)
        return (c,)

    monkeypatch.setattr(score, "load_cases", fake_load)
    out = tmp_path / "holdout-scores"
    _write_rules_only(out, c)
    assert score.main(["--case-file", str(case_file), "--results-dir", str(out)]) == 0
    assert seen == [case_file]
    # RESULTS is put back after the call: a later call for the 40 does not read or write the holdout's folder
    assert forty == score.RESULTS
    assert (out / "summary.md").exists() and (out / "scores.json").exists()
    assert json.loads((out / "scores.json").read_text())["H01"]["rules_e2e"]["unsafe"]["unsafe"] is True
    assert "| Materially unsafe cases" in (out / "summary.md").read_text()
    # nothing was written into the 40's results
    assert list(forty.iterdir()) == []
    # a later call for the 40 in the same process reads and writes the 40's folder, not the holdout's
    forty_case = make_case("D01", items=UNSAFE_ITEMS)
    monkeypatch.setattr(score, "load_cases", lambda case_file=None: (forty_case,))
    _write_rules_only(forty, forty_case)
    holdout_scores = (out / "scores.json").read_text()
    assert score.main([]) == 0
    assert set(json.loads((forty / "scores.json").read_text())) == {"D01"}
    assert (out / "scores.json").read_text() == holdout_scores
    assert not (out / "D01").exists()


def test_case_file_defaults_to_its_folder_and_never_the_forty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forty = tmp_path / "backtest" / "results"
    forty.mkdir(parents=True)
    monkeypatch.setattr(score, "RESULTS", forty)
    monkeypatch.setattr(score, "FORTY_RESULTS", forty)
    case_file = tmp_path / "backtest" / "holdout" / "cases.yaml"
    assert score.results_dir_for(case_file, None) == (case_file.parent / "results").resolve()
    with pytest.raises(SystemExit, match="refusing"):
        score.results_dir_for(case_file, forty)
    # the 40 with no --results-dir keep RESULTS as it is
    assert score.results_dir_for(None, None) is None
    assert score.results_dir_for(score.DEFAULT_CASE_FILE, None) is None
    # a missing results dir is an error, not an empty score
    monkeypatch.setattr(score, "load_cases", lambda case_file=None: ())
    assert score.main(["--case-file", str(case_file)]) == 2
    assert forty == score.RESULTS


def test_a_report_with_no_writers_sentences_scores_without_the_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live report has no writer (MEMO_WRITER_ENABLED off): no verification.json. The scorer reads it, and the
    measures of the citation check are n/a, never a crash."""
    monkeypatch.setattr(score, "RESULTS", tmp_path)
    c = make_case()
    for run in ("e2e", "conditional"):
        d = tmp_path / c.id / run
        d.mkdir(parents=True)
        memo = {"format_version": 3, "approvals": [{"area": "zoning_use", "status": "further_review"}],
                "pathway": {"triggers": []}, "verification": None}  # fmt: skip
        (d / "memo.json").write_text(json.dumps(memo))
    scores = {c.id: {}}  # type: dict[str, dict[str, Any]]
    for which in score.SETS:
        data = score.load_set(c, which)
        scores[c.id][which] = score.score_set(c, which, data) if data is not None else None
    assert scores[c.id]["full_e2e"]["verification"] is None
    table = "\n".join(score.measure_table((c,), scores, "full_e2e"))
    assert "| Cited sentences checked | 0 |" in table
    assert "n/a" in table
    assert score.summary((c,), scores)
