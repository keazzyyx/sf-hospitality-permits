"""The memo trace Neatlogs receives: one root, AGENT spans under it, TOOL spans under those with row counts.

Captured in-process from the provider `app.main`'s neatlogs.init() set up (export disabled in tests)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import neatlogs
import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import app.main  # noqa: F401  (runs neatlogs.init exactly as the server does)
from app.core.observability import set_span_attributes

_EXPORTER = InMemorySpanExporter()


@pytest.fixture
def spans() -> Any:
    from neatlogs._wrap_utils import get_neatlogs_provider

    provider = get_neatlogs_provider()
    if provider is None:  # an earlier test (the local doctor) shut the SDK down; re-init like app.main does
        from app.core.observability import mask_pii

        neatlogs.init(
            api_key=None,
            workflow_name="permit_memo",
            instrumentations=["anthropic"],
            mask=mask_pii,
            disable_export=True,
        )
        provider = get_neatlogs_provider()
    assert provider is not None
    if not getattr(provider, "_sfhp_test_capture", False):
        provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
        provider._sfhp_test_capture = True  # type: ignore[attr-defined]
    _EXPORTER.clear()
    yield _EXPORTER
    _EXPORTER.clear()


def test_set_span_attributes_lands_on_the_neatlogs_span(spans: InMemorySpanExporter) -> None:
    @neatlogs.span(kind="TOOL", name="tool.probe")
    def probe() -> None:
        set_span_attributes(rows=7, scope="x")

    probe()
    (span,) = [s for s in spans.get_finished_spans() if s.name == "tool.probe"]
    assert span.attributes is not None and span.attributes["rows"] == 7 and span.attributes["scope"] == "x"


async def _traced_memo(tmp_path: Path, monkeypatch: Any, script: Any = None) -> list[Any]:
    """One scripted memo run under a WORKFLOW span, the way the route wraps it. Returns the terminal events."""
    import app.memo.context as ctx
    import app.tools.precedent_tools as pt
    from app.agents.memo_runner import MemoRunInput, MemoRunner
    from app.catalog.loader import get_catalog
    from app.core.config import settings
    from tests.fakes import FakeAnthropic
    from tests.memo_fakes import FakeGeocoder, MemoScript, seed_store

    store = seed_store(tmp_path / "data")
    for mod in (ctx, pt):
        monkeypatch.setattr(mod, "get_store", lambda: store)
        monkeypatch.setattr(mod, "get_geocoder", lambda: FakeGeocoder())
    runner = MemoRunner(
        FakeAnthropic(script or MemoScript()),  # type: ignore[arg-type]
        get_catalog(),
        settings,
        store,
        FakeGeocoder(),
        today=dt.date(2026, 10, 21),
    )

    @neatlogs.span(kind="WORKFLOW", name="memo.generate", capture_output=False)
    async def generate() -> list[Any]:
        async def emit(_: Any) -> None:
            return None

        return [
            e
            async for e in runner.run_memo(
                MemoRunInput(
                    address="899 Valencia St", description="40-seat wine bar, open until 1am, live music"
                ),
                emit,
            )
        ]

    return await generate()


def _kind(s: ReadableSpan) -> str:
    return str((s.attributes or {}).get("openinference.span.kind"))


@pytest.mark.anyio
async def test_memo_trace_tree(tmp_path: Path, spans: InMemorySpanExporter, monkeypatch: Any) -> None:
    assert [e.type for e in await _traced_memo(tmp_path, monkeypatch)] == ["memo"]
    finished: list[ReadableSpan] = list(spans.get_finished_spans())
    by_id = {s.context.span_id: s for s in finished}
    roots = [s for s in finished if s.parent is None or s.parent.span_id not in by_id]
    assert [r.name for r in roots] == ["memo.generate"]
    root = roots[0]

    def parent(s: ReadableSpan) -> ReadableSpan:
        assert s.parent is not None
        return by_id[s.parent.span_id]

    kind = _kind
    # the intake is the one AGENT span: no stage after it calls a model
    agents = [s.name for s in finished if kind(s) == "AGENT"]
    assert agents == ["agent.intake"]
    tools = [s for s in finished if kind(s) == "TOOL"]
    assert tools and all(parent(t) is not root or t.name == "tool.geocode_address" for t in tools)
    # the deterministic record tools sit under the records chain
    chain = next(s for s in finished if s.name == "memo.collect_records")
    assert parent(chain) is root
    under_chain = {t.name for t in tools if parent(t) is chain}
    assert {"tool.zoning_at", "tool.nearby_applications", "tool.base_rate"} <= under_chain
    assert not any(t.name == "tool.read_decision" for t in tools)
    # every precedent tool reports its row count as a filterable attribute
    precedent_tools = [t for t in tools if t.name != "tool.lookup_permit_catalog"]
    missing = [t.name for t in precedent_tools if "rows" not in (t.attributes or {})]
    assert missing == []
    rows = {t.name: (t.attributes or {})["rows"] for t in precedent_tools if parent(t) is chain}
    # base rate: the four dated Planning decisions (Entertainment Commission and ABC rows are never counted)
    assert rows["tool.nearby_applications"] == 8 and rows["tool.base_rate"] == 4
    # the run carries the overall status (not a verdict) and what the report holds
    attrs = root.attributes or {}
    assert attrs["overall_status"] == "further_review" and "verdict" not in attrs
    assert attrs["comparable_count"] >= 1 and attrs["citation_count"] >= 1
    assert (chain.attributes or {})["rule_overall_status"] == "further_review"
