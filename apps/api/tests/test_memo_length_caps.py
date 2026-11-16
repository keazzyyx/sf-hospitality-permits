"""Over-long text in a memo model is clamped to the schema cap, not rejected (production regression)."""

from __future__ import annotations

from app.models.memo import OpenQuestion


def test_long_text_is_clamped_to_cap() -> None:
    cap = next(
        m.max_length for m in OpenQuestion.model_fields["question"].metadata if hasattr(m, "max_length")
    )
    long = "Not known: " + "x" * (cap + 400)
    q = OpenQuestion.model_validate({"question": long, "needs": "applicant_history"})
    assert len(q.question) == cap
    assert q.question.endswith("…")
