from __future__ import annotations

from collections import defaultdict

import neatlogs
from pydantic import BaseModel, Field

from app.catalog.loader import CatalogPermit, get_catalog
from app.models.plan import FeeByCategory, FeeByStep, FeeSummary
from app.tools.base import ToolExecutionError, ToolSpec


def fee_summary(permits: list[CatalogPermit]) -> FeeSummary:
    by_cat: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    by_step: list[FeeByStep] = []
    total_min = total_max = 0.0
    for p in sorted(permits, key=lambda p: p.id):
        lo, hi = p.fee_range_usd.min, p.fee_range_usd.max
        total_min += lo
        total_max += hi
        by_cat[p.category][0] += lo
        by_cat[p.category][1] += hi
        by_step.append(FeeByStep(step_id=p.id, min=lo, max=hi))
    cats = [FeeByCategory(category=c, min=v[0], max=v[1]) for c, v in sorted(by_cat.items())]  # type: ignore[arg-type,unused-ignore]
    notes = (
        "Government application and first-year fees only. Excludes construction, architect/expediter fees, "
        "insurance premiums, and the purchase price of quota liquor licenses beyond the range shown."
    )
    return FeeSummary(
        total_min=total_min, total_max=total_max, by_category=cats, by_step=by_step, notes=notes
    )


class FeeTotalInput(BaseModel):
    permit_ids: list[str] = Field(min_length=1)


@neatlogs.span(kind="TOOL", name="tool.get_fee_total")
async def _fee_tool(inp: BaseModel) -> BaseModel:
    assert isinstance(inp, FeeTotalInput)
    catalog = get_catalog()
    permits = []
    for pid in dict.fromkeys(inp.permit_ids):
        p = catalog.get(pid)
        if p is None:
            raise ToolExecutionError("unknown_permit_ids", f"Not in catalog: {pid}")
        permits.append(p)
    return fee_summary(permits)


GET_FEE_TOTAL = ToolSpec(
    name="get_fee_total",
    description="Sum the catalog fee ranges for a set of permit ids, broken down by category and step.",
    input_model=FeeTotalInput,
    handler=_fee_tool,
)
