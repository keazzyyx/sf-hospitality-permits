"""Deterministic scheduling: dependency validation, topological sort, critical path, parallel tracks.

Pure functions, no I/O, fully unit-tested. The agent calls these through the `estimate_timeline`
and `check_dependencies` tools; the plan builder calls them directly as the source of truth.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

import neatlogs
from pydantic import BaseModel, Field

from app.catalog.loader import CatalogPermit, Category, get_catalog
from app.tools.base import ToolExecutionError, ToolSpec

TRACKS: dict[str, tuple[Category, ...]] = {
    "Entity, tax & payroll": ("business_registration", "federal_tax", "state_tax", "local_tax", "labor"),
    "Build-out & inspections": ("building", "fire", "grease", "health", "signage"),
    "Zoning & entertainment": ("zoning", "entertainment", "outdoor_dining"),
    "Alcohol license": ("alcohol",),
    "Team & training": ("food_safety_cert", "music_licensing"),
    "Hotel": ("hotel",),
    "Mobile vending": ("mobile_vending",),
    "Other": ("other",),
}
TRACK_ORDER = list(TRACKS)


def track_for(category: str) -> str:
    for name, cats in TRACKS.items():
        if category in cats:
            return name
    return "Other"


@dataclass(frozen=True)
class Task:
    id: str
    name: str
    category: str
    duration_min: int
    duration_max: int
    prerequisites: tuple[str, ...]


@dataclass
class DependencyReport:
    ok: bool
    missing: list[dict[str, str]] = field(default_factory=list)  # prereq ids not in the set
    cycles: list[list[str]] = field(default_factory=list)
    unknown_ids: list[str] = field(default_factory=list)


class DependencyError(ValueError):
    pass


def check_dependencies(tasks: list[Task]) -> DependencyReport:
    ids = {t.id for t in tasks}
    missing = [
        {"permit_id": t.id, "missing_prerequisite": p} for t in tasks for p in t.prerequisites if p not in ids
    ]
    graph = {t.id: [p for p in t.prerequisites if p in ids] for t in tasks}
    state: dict[str, int] = {}
    cycles: list[list[str]] = []

    def visit(node: str, stack: list[str]) -> None:
        if state.get(node) == 1:
            cycles.append([*stack[stack.index(node) :], node])
            return
        if state.get(node) == 2:
            return
        state[node] = 1
        for pre in graph[node]:
            visit(pre, [*stack, node])
        state[node] = 2

    for node in sorted(graph):
        visit(node, [])
    return DependencyReport(ok=not cycles, missing=missing, cycles=cycles)


def topological_order(tasks: list[Task]) -> list[str]:
    """Kahn's algorithm with deterministic tie-breaking (lexicographic id). Raises on cycles."""
    ids = {t.id for t in tasks}
    indeg = {t.id: 0 for t in tasks}
    succ: dict[str, list[str]] = defaultdict(list)
    for t in tasks:
        for p in t.prerequisites:
            if p in ids:
                indeg[t.id] += 1
                succ[p].append(t.id)
    ready = sorted(i for i, d in indeg.items() if d == 0)
    out: list[str] = []
    queue = deque(ready)
    while queue:
        node = queue.popleft()
        out.append(node)
        newly = []
        for s in succ[node]:
            indeg[s] -= 1
            if indeg[s] == 0:
                newly.append(s)
        for s in sorted(newly):
            queue.append(s)
        queue = deque(sorted(queue))
    if len(out) != len(tasks):
        raise DependencyError("dependency cycle detected")
    return out


@dataclass
class ScheduledTask:
    id: str
    name: str
    category: str
    track: str
    order: int
    earliest_start: int
    earliest_finish: int
    latest_start: int
    latest_finish: int
    slack: int
    on_critical_path: bool
    scheduled_start: str
    scheduled_end: str
    prerequisites: list[str]


@dataclass
class Schedule:
    start_date: str
    target_open_date: str | None
    projected_open_date: str
    optimistic_open_date: str
    total_days_min: int
    total_days_max: int
    feasible: bool | None
    days_short: int | None
    critical_path: list[str]
    parallel_tracks: list[dict[str, Any]]
    tasks: list[ScheduledTask]
    weeks: list[dict[str, Any]]


def _iso(d: dt.date) -> str:
    return d.isoformat()


def estimate_timeline(
    tasks: list[Task], start_date: dt.date, target_open_date: dt.date | None = None
) -> Schedule:
    report = check_dependencies(tasks)
    if report.cycles:
        raise DependencyError("dependency cycle: " + " -> ".join(report.cycles[0]))
    ids = {t.id for t in tasks}
    by_id = {t.id: t for t in tasks}
    # prerequisites outside the set are dropped (they did not apply to this profile)
    pre = {t.id: [p for p in t.prerequisites if p in ids] for t in tasks}
    order = topological_order(tasks)

    es: dict[str, int] = {}
    ef: dict[str, int] = {}
    es_min: dict[str, int] = {}
    ef_min: dict[str, int] = {}
    for tid in order:
        es[tid] = max((ef[p] for p in pre[tid]), default=0)
        ef[tid] = es[tid] + by_id[tid].duration_max
        es_min[tid] = max((ef_min[p] for p in pre[tid]), default=0)
        ef_min[tid] = es_min[tid] + by_id[tid].duration_min
    total_max = max(ef.values(), default=0)
    total_min = max(ef_min.values(), default=0)

    # backward pass against the true project duration → critical path
    succ: dict[str, list[str]] = defaultdict(list)
    for tid in order:
        for p in pre[tid]:
            succ[p].append(tid)
    lf_cp: dict[str, int] = {}
    ls_cp: dict[str, int] = {}
    for tid in reversed(order):
        lf_cp[tid] = min((ls_cp[s] for s in succ[tid]), default=total_max)
        ls_cp[tid] = lf_cp[tid] - by_id[tid].duration_max
    critical = {tid for tid in order if ls_cp[tid] - es[tid] == 0}

    # latest dates against the real deadline (target if later than projected)
    target_offset = (target_open_date - start_date).days if target_open_date else None
    deadline = max(total_max, target_offset) if target_offset is not None else total_max
    shift = deadline - total_max

    # ordered critical path: walk forward from a zero-ES critical node through critical successors
    path: list[str] = []
    cp_candidates = [tid for tid in order if tid in critical]
    if cp_candidates:
        # pick the longest chain among critical nodes (follow successors with matching ES/EF)
        current = next(tid for tid in cp_candidates if es[tid] == 0)
        path.append(current)
        while True:
            nxt = sorted(s for s in succ[current] if s in critical and es[s] == ef[current])
            if not nxt:
                break
            current = nxt[0]
            path.append(current)

    ranked = sorted(order, key=lambda t: (es[t], 0 if t in critical else 1, t))
    rank = {tid: i + 1 for i, tid in enumerate(ranked)}
    scheduled = [
        ScheduledTask(
            id=tid,
            name=by_id[tid].name,
            category=by_id[tid].category,
            track=track_for(by_id[tid].category),
            order=rank[tid],
            earliest_start=es[tid],
            earliest_finish=ef[tid],
            latest_start=ls_cp[tid] + shift,
            latest_finish=lf_cp[tid] + shift,
            slack=ls_cp[tid] + shift - es[tid],
            on_critical_path=tid in critical,
            scheduled_start=_iso(start_date + dt.timedelta(days=es[tid])),
            scheduled_end=_iso(start_date + dt.timedelta(days=ef[tid])),
            prerequisites=pre[tid],
        )
        for tid in ranked
    ]
    tracks = [
        {"name": name, "step_ids": [t.id for t in scheduled if t.track == name]}
        for name in TRACK_ORDER
        if any(t.track == name for t in scheduled)
    ]
    horizon = max(deadline, 7)
    n_weeks = (horizon + 6) // 7
    weeks: list[dict[str, Any]] = []
    for w in range(n_weeks):
        lo, hi = w * 7, w * 7 + 7
        weeks.append(
            {
                "week_number": w + 1,
                "start_date": _iso(start_date + dt.timedelta(days=lo)),
                "end_date": _iso(start_date + dt.timedelta(days=hi - 1)),
                "step_ids_starting": [t.id for t in scheduled if lo <= t.earliest_start < hi],
                "step_ids_due": [
                    t.id
                    for t in scheduled
                    if lo <= t.earliest_finish < hi or (w == n_weeks - 1 and t.earliest_finish >= hi)
                ],
            }
        )
    feasible = None if target_offset is None else target_offset >= total_max
    days_short = None if target_offset is None else max(0, total_max - target_offset)
    return Schedule(
        start_date=_iso(start_date),
        target_open_date=_iso(target_open_date) if target_open_date else None,
        projected_open_date=_iso(start_date + dt.timedelta(days=total_max)),
        optimistic_open_date=_iso(start_date + dt.timedelta(days=total_min)),
        total_days_min=total_min,
        total_days_max=total_max,
        feasible=feasible,
        days_short=days_short,
        critical_path=path,
        parallel_tracks=tracks,
        tasks=scheduled,
        weeks=weeks,
    )


def tasks_from_permits(permits: list[CatalogPermit]) -> list[Task]:
    return [
        Task(
            id=p.id,
            name=p.name,
            category=p.category,
            duration_min=int(p.typical_timeline_days.min),
            duration_max=int(p.typical_timeline_days.max),
            prerequisites=tuple(p.prerequisites),
        )
        for p in permits
    ]


# ---- function tools ------------------------------------------------------------------
class EstimateTimelineInput(BaseModel):
    permit_ids: list[str] = Field(min_length=1, description="Catalog ids of every permit in the plan.")
    start_date: str = Field(description="YYYY-MM-DD; the day the operator starts (today).")
    target_open_date: str | None = Field(default=None, description="YYYY-MM-DD target opening, if any.")


class ScheduledTaskOut(BaseModel):
    id: str
    name: str
    track: str
    order: int
    earliest_start_day: int
    earliest_finish_day: int
    latest_start_day: int
    latest_finish_day: int
    slack_days: int
    on_critical_path: bool
    scheduled_start: str
    scheduled_end: str
    prerequisites: list[str]


class WeekOut(BaseModel):
    week_number: int
    start_date: str
    end_date: str
    step_ids_starting: list[str]
    step_ids_due: list[str]


class EstimateTimelineOutput(BaseModel):
    start_date: str
    target_open_date: str | None
    projected_open_date: str
    optimistic_open_date: str
    total_days_min: int
    total_days_max: int
    feasible: bool | None
    days_short: int | None
    critical_path: list[str]
    parallel_tracks: list[dict[str, Any]]
    tasks: list[ScheduledTaskOut]
    weeks: list[WeekOut]


def _parse_date(value: str, label: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ToolExecutionError("invalid_date", f"{label} must be YYYY-MM-DD") from exc


def _permits_for_ids(ids: list[str]) -> list[CatalogPermit]:
    catalog = get_catalog()
    unknown = [i for i in ids if catalog.get(i) is None]
    if unknown:
        raise ToolExecutionError("unknown_permit_ids", f"Not in catalog: {', '.join(unknown)}")
    seen: set[str] = set()
    out: list[CatalogPermit] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            p = catalog.get(i)
            assert p is not None
            out.append(p)
    return out


@neatlogs.span(kind="TOOL", name="tool.estimate_timeline")
async def _estimate_timeline_tool(inp: BaseModel) -> BaseModel:
    assert isinstance(inp, EstimateTimelineInput)
    permits = _permits_for_ids(inp.permit_ids)
    start = _parse_date(inp.start_date, "start_date")
    target = _parse_date(inp.target_open_date, "target_open_date") if inp.target_open_date else None
    try:
        sched = estimate_timeline(tasks_from_permits(permits), start, target)
    except DependencyError as exc:
        raise ToolExecutionError("dependency_cycle", str(exc)) from exc
    return EstimateTimelineOutput(
        start_date=sched.start_date,
        target_open_date=sched.target_open_date,
        projected_open_date=sched.projected_open_date,
        optimistic_open_date=sched.optimistic_open_date,
        total_days_min=sched.total_days_min,
        total_days_max=sched.total_days_max,
        feasible=sched.feasible,
        days_short=sched.days_short,
        critical_path=sched.critical_path,
        parallel_tracks=sched.parallel_tracks,
        tasks=[
            ScheduledTaskOut(
                id=t.id,
                name=t.name,
                track=t.track,
                order=t.order,
                earliest_start_day=t.earliest_start,
                earliest_finish_day=t.earliest_finish,
                latest_start_day=t.latest_start,
                latest_finish_day=t.latest_finish,
                slack_days=t.slack,
                on_critical_path=t.on_critical_path,
                scheduled_start=t.scheduled_start,
                scheduled_end=t.scheduled_end,
                prerequisites=t.prerequisites,
            )
            for t in sched.tasks
        ],
        weeks=[WeekOut(**w) for w in sched.weeks],
    )


class CheckDependenciesInput(BaseModel):
    permit_ids: list[str] = Field(min_length=1)


class CheckDependenciesOutput(BaseModel):
    ok: bool
    missing_prerequisites: list[dict[str, str]]
    cycles: list[list[str]]
    topological_order: list[str]


@neatlogs.span(kind="TOOL", name="tool.check_dependencies")
async def _check_dependencies_tool(inp: BaseModel) -> BaseModel:
    assert isinstance(inp, CheckDependenciesInput)
    permits = _permits_for_ids(inp.permit_ids)
    tasks = tasks_from_permits(permits)
    report = check_dependencies(tasks)
    order = [] if report.cycles else topological_order(tasks)
    return CheckDependenciesOutput(
        ok=report.ok, missing_prerequisites=report.missing, cycles=report.cycles, topological_order=order
    )


ESTIMATE_TIMELINE = ToolSpec(
    name="estimate_timeline",
    description=(
        "Deterministically schedule a set of catalog permits: topological order, earliest/latest start, "
        "critical path, parallel tracks and a week grid from start_date. Pass every permit id in the plan."
    ),
    input_model=EstimateTimelineInput,
    handler=_estimate_timeline_tool,
)

CHECK_DEPENDENCIES = ToolSpec(
    name="check_dependencies",
    description="Validate prerequisite links among a set of permit ids: reports missing prerequisites and cycles.",
    input_model=CheckDependenciesInput,
    handler=_check_dependencies_tool,
)
