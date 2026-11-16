from app.catalog.loader import get_catalog
from app.tools.fees import fee_summary


def test_fee_totals_and_breakdown() -> None:
    c = get_catalog()
    permits = [
        c.get("us.ein"),
        c.get("ca.sellers_permit"),
        c.get("sf.business_registration"),
        c.get("sf.health_permit"),
    ]
    assert all(permits)
    s = fee_summary([p for p in permits if p])
    assert s.total_min == sum(p.fee_range_usd.min for p in permits if p)
    assert s.total_max == sum(p.fee_range_usd.max for p in permits if p)
    cats = {c.category: (c.min, c.max) for c in s.by_category}
    health = [p for p in permits if p and p.category == "health"]
    assert cats["health"] == (
        sum(p.fee_range_usd.min for p in health),
        sum(p.fee_range_usd.max for p in health),
    )
    assert sum(c.min for c in s.by_category) == s.total_min
    assert [b.step_id for b in s.by_step] == sorted(p.id for p in permits if p)
    assert "Excludes construction" in s.notes
