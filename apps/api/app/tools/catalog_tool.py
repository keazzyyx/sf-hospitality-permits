"""The permit checklist's catalog lookup: which catalog permits apply to a profile.

A permit whose rule depends on a fact the profile marks "unknown" (what alcohol is served) is neither a match
nor dropped: it is listed under `undetermined`, with the fact that is missing (the fixed phrase of
`app.memo.facts.MISSING_PHRASES`) and the condition under which it applies, and `undetermined_note` says it in
one sentence. It never becomes a step: the plan names it instead (app.agents.runner).
"""

from __future__ import annotations

from collections.abc import Sequence

import neatlogs
from pydantic import BaseModel, Field

from app.catalog import rules
from app.catalog.loader import CatalogPermit, Category, Confidence, JurisdictionLevel, Range, get_catalog
from app.memo.facts import MISSING_PHRASES
from app.models.profile import BusinessProfile
from app.tools.base import ToolSpec

# The fact an unknown profile field leaves missing, in the report's own words.
UNKNOWN_FIELD_PHRASES: dict[str, str] = {"alcohol_type": MISSING_PHRASES["alcohol_served"]}
# The sentence the plan and the requirements stage are given for the permits left undetermined.
NOT_DETERMINED_NOTE = (
    "Not determined: the description does not say {missing}. Which of these applies depends on it, so none of "
    "them is in the checklist, the timeline or the fees until it is known: {items}."
)
NOT_DETERMINED_ITEM = "{name} ({agency}; applies if {condition})"


class LookupInput(BaseModel):
    profile: BusinessProfile = Field(
        description="The structured business profile to match catalog rules against."
    )


class CatalogMatch(BaseModel):
    id: str
    name: str
    category: Category
    jurisdiction_level: JurisdictionLevel
    issuing_agency: str
    typical_timeline_days: Range
    fee_range_usd: Range
    prerequisites: list[str]
    confidence: Confidence
    notes: str
    stall_risk: str | None


class UndeterminedMatch(BaseModel):
    """A permit whose rule depends on a fact the profile does not give."""

    id: str
    name: str
    category: Category
    jurisdiction_level: JurisdictionLevel
    issuing_agency: str
    applies_if: str = Field(description="The condition under which it applies, in plain words.")
    missing: list[str] = Field(
        description="The facts the description does not give, as the report names them."
    )


class LookupOutput(BaseModel):
    city_supported: bool
    city_name: str | None
    state: str | None
    county: str | None
    matches: list[CatalogMatch]
    match_count: int
    undetermined: list[UndeterminedMatch] = Field(
        default_factory=list,
        description="Permits that apply or not depending on a fact the profile does not give. Not matches: do "
        "not list them as required.",
    )
    undetermined_note: str | None = None


def undetermined_note(undetermined: Sequence[UndeterminedMatch]) -> str | None:
    """One sentence naming what is missing and each permit it leaves undetermined, with its condition; None
    when there is none."""
    if not undetermined:
        return None
    missing = list(dict.fromkeys(m for u in undetermined for m in u.missing))
    items = "; ".join(
        NOT_DETERMINED_ITEM.format(name=u.name, agency=u.issuing_agency, condition=u.applies_if)
        for u in undetermined
    )
    return NOT_DETERMINED_NOTE.format(missing=" and ".join(missing), items=items)


def resolve(profile: BusinessProfile) -> tuple[list[CatalogPermit], list[tuple[CatalogPermit, str]]]:
    """The permits that apply (decided), and the undetermined ones with the condition under which each
    applies, both in id order. The profile is normalised first (what is poured stays "unknown")."""
    catalog = get_catalog()
    prof = profile.normalized().model_dump()
    jur = catalog.jurisdiction_for(prof.get("state"), prof.get("city_slug"))
    applicable: list[CatalogPermit] = []
    undecided: list[tuple[CatalogPermit, str]] = []
    for p in sorted(jur.permits, key=lambda p: p.id):
        decided = p.applicability(prof)
        if decided is True:
            applicable.append(p)
        elif decided is None:
            undecided.append((p, rules.condition_text(rules.applies_if(p.applies_when, prof))))
    return applicable, undecided


def lookup(profile: BusinessProfile) -> LookupOutput:
    catalog = get_catalog()
    prof = profile.normalized().model_dump()
    jur = catalog.jurisdiction_for(prof.get("state"), prof.get("city_slug"))
    applicable, undecided = resolve(profile)
    missing = [UNKNOWN_FIELD_PHRASES[f] for f in rules.unknown_fields(prof)]
    undetermined = [
        UndeterminedMatch(
            id=p.id,
            name=p.name,
            category=p.category,
            jurisdiction_level=p.jurisdiction_level,
            issuing_agency=p.issuing_agency,
            applies_if=condition,
            missing=missing,
        )
        for p, condition in undecided
    ]
    ids = {p.id for p in applicable}
    matches = [
        CatalogMatch(
            id=p.id,
            name=p.name,
            category=p.category,
            jurisdiction_level=p.jurisdiction_level,
            issuing_agency=p.issuing_agency,
            typical_timeline_days=p.typical_timeline_days,
            fee_range_usd=p.fee_range_usd,
            prerequisites=[x for x in p.prerequisites if x in ids],
            confidence=p.confidence,
            notes=p.notes,
            stall_risk=p.stall_risk,
        )
        for p in applicable
    ]
    return LookupOutput(
        city_supported=jur.supported,
        city_name=jur.city_name,
        state=jur.state,
        county=jur.county,
        matches=matches,
        match_count=len(matches),
        undetermined=undetermined,
        undetermined_note=undetermined_note(undetermined),
    )


@neatlogs.span(kind="TOOL", name="tool.lookup_permit_catalog")
async def _lookup_tool(inp: BaseModel) -> BaseModel:
    assert isinstance(inp, LookupInput)
    return lookup(inp.profile)


LOOKUP_PERMIT_CATALOG = ToolSpec(
    name="lookup_permit_catalog",
    description=(
        "Query the permit catalog with a BusinessProfile. Returns every federal, state and city permit whose "
        "applicability rule matches the profile, with timelines, fees, prerequisites and confidence, and under "
        "`undetermined` the permits that depend on a fact the profile does not give (with the condition under "
        "which each applies)."
    ),
    input_model=LookupInput,
    handler=_lookup_tool,
)
