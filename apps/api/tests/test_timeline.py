import datetime as dt

import pytest

from app.agents.runner import weeks_to_narrate
from app.tools.timeline import DependencyError, Task, check_dependencies, estimate_timeline, topological_order

START = dt.date(2026, 10, 21)


def t(i: str, mn: int, mx: int, *pre: str, cat: str = "other") -> Task:
    return Task(id=i, name=i, category=cat, duration_min=mn, duration_max=mx, prerequisites=tuple(pre))


def test_topological_order_is_deterministic() -> None:
    tasks = [t("c", 1, 1, "a", "b"), t("b", 1, 1), t("a", 1, 1), t("d", 1, 1, "c")]
    assert topological_order(tasks) == ["a", "b", "c", "d"]
    assert topological_order(list(reversed(tasks))) == ["a", "b", "c", "d"]


def test_cycle_detected() -> None:
    tasks = [t("a", 1, 2, "c"), t("b", 1, 2, "a"), t("c", 1, 2, "b")]
    report = check_dependencies(tasks)
    assert not report.ok and report.cycles
    with pytest.raises(DependencyError):
        topological_order(tasks)
    with pytest.raises(DependencyError):
        estimate_timeline(tasks, START)


def test_missing_prerequisite_reported_and_dropped() -> None:
    tasks = [t("a", 1, 5, "ghost"), t("b", 2, 10, "a")]
    report = check_dependencies(tasks)
    assert report.missing == [{"permit_id": "a", "missing_prerequisite": "ghost"}]
    sched = estimate_timeline(tasks, START)
    assert sched.total_days_max == 15 and sched.tasks[0].prerequisites == []


def test_critical_path_and_slack() -> None:
    # a(10) -> c(30) -> e(5) is the long pole; b(5) -> d(5) -> e runs in parallel with slack
    tasks = [
        t("a", 5, 10, cat="business_registration"),
        t("b", 2, 5),
        t("c", 20, 30, "a", cat="alcohol"),
        t("d", 3, 5, "b", cat="health"),
        t("e", 2, 5, "c", "d", cat="fire"),
    ]
    sched = estimate_timeline(tasks, START)
    assert sched.total_days_max == 45 and sched.total_days_min == 27
    assert sched.critical_path == ["a", "c", "e"]
    by = {x.id: x for x in sched.tasks}
    assert by["b"].slack == 30 and by["d"].slack == 30 and by["a"].slack == 0
    assert by["c"].earliest_start == 10 and by["e"].earliest_start == 40
    assert by["e"].scheduled_end == (START + dt.timedelta(days=45)).isoformat()
    assert [x.id for x in sched.tasks] == [
        "a",
        "b",
        "d",
        "c",
        "e",
    ]  # ordered by earliest start, then critical
    assert sched.feasible is None and sched.days_short is None
    tracks = {tr["name"]: tr["step_ids"] for tr in sched.parallel_tracks}
    assert tracks["Alcohol license"] == ["c"] and tracks["Build-out & inspections"] == ["d", "e"]


def test_target_date_feasibility_and_latest_dates() -> None:
    tasks = [t("a", 5, 10), t("b", 10, 20, "a")]
    tight = estimate_timeline(tasks, START, START + dt.timedelta(days=20))
    assert tight.feasible is False and tight.days_short == 10
    roomy = estimate_timeline(tasks, START, START + dt.timedelta(days=40))
    assert roomy.feasible is True and roomy.days_short == 0
    by = {x.id: x for x in roomy.tasks}
    assert by["a"].latest_start == 10 and by["a"].slack == 10 and by["a"].on_critical_path
    assert len(roomy.weeks) == 6 and roomy.weeks[0]["step_ids_starting"] == ["a"]
    assert "b" in roomy.weeks[-1]["step_ids_due"] or any("b" in w["step_ids_due"] for w in roomy.weeks)


def test_weeks_grid_covers_horizon() -> None:
    tasks = [t("a", 1, 100)]
    sched = estimate_timeline(tasks, START)
    assert len(sched.weeks) == 15
    assert sched.weeks[-1]["end_date"] >= sched.projected_open_date[:10] or sched.weeks[-1][
        "step_ids_due"
    ] == ["a"]


def test_weeks_to_narrate_thins_long_horizons() -> None:
    weeks = [
        {"week_number": i, "step_ids_starting": ["x"] if i % 2 else [], "step_ids_due": []}
        for i in range(1, 101)
    ]
    chosen = weeks_to_narrate(weeks, cap=20)
    assert chosen[0] == 1 and chosen[-1] == 100 and len(chosen) <= 22
    short = weeks_to_narrate(weeks[:6], cap=20)
    assert short == [1, 3, 5, 6]
