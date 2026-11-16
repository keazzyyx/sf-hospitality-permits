"""The evidence the report shows beside the rules (report format 3). Pure code: no model call, no I/O, no clock.

Three things, each built from data the runner already holds:

* the facts the rules read (`fact_list`, `row_facts`), each with its value in plain words and where it came from:
  the applicant's description (with the words that state it), an answer to an intake question, an answer to a
  follow-up question, the request itself, or the records on file at the address. A fact the rules worked out from
  another one says so. A fact nothing gives is "Not known".
* the comparable cases (`comparable_cases`): the top of the fixed ranking (`app.memo.analytics.rank_candidates`),
  each with its recorded facts and its source link. No model picks them and none writes about them.
* the decisions the base rate counted (`counted_decisions`), each with its source link.

Every label and fixed sentence is in the tables at the top of this module.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from precedent.models import Application

from app.memo.analytics import Scored, record_kind
from app.memo.facts import MISSING_PHRASES, ConceptFacts, Fact, SiteFacts, concept_facts
from app.memo.pathway import LICENCE_TYPES, format_time
from app.memo.report import USE_LABELS, case_outcome, comparable_source, days_to_decision, source_label
from app.memo.rows import EXISTING_USE_LABELS
from app.memo.stated import QUOTE_GROUPS, quote_spans
from app.models.memo import (
    FACT_ORIGIN_LABELS,
    RECORD_KIND_LABELS,
    ComparableCase,
    CountedDecision,
    Determinations,
    FactOrigin,
    MemoFact,
)
from app.models.profile import BusinessProfile, FactQuote

# ---- the fixed tables (for review) ------------------------------------------------------------------------------
# How many comparable cases the report lists: the top of the fixed ranking.
COMPARABLE_LIMIT = 10
COMPARABLES_NOTE = (
    "Planning and Entertainment Commission records within 1,000 ft, ranked by a fixed score: the kind of business "
    "in common (40%), the distance (25%), how recent the record is (15%), late-night hours in common (10%) and "
    "whether the case was decided (10%); a Conditional Use case scores a little higher. The top {n} are listed, best first. Each row shows what the record says, "
    "with a link to it. No model picks them."
)
NO_COMPARABLES_NOTE = (
    "No Planning or Entertainment Commission record within 1,000 ft matched this kind of business."
)

# The name of each fact as the report prints it.
FACT_LABELS: dict[str, str] = {
    "planning_uses": "Kind of business (Planning Code use)",
    # a bar that serves no alcohol is not a Bar (app.memo.pathway rule 1b); only named: an answer gives the use, listed
    # as the kind of business
    "food_service": "Kind of food or drink service (a business that serves no alcohol is not a Bar)",
    "alcohol_served": "Alcohol served",
    "licence_type": "Liquor licence type",
    "licences_held": "Licences already held",
    "alcohol_transaction": "How the liquor licence is obtained",
    "formula_retail": "Part of a chain (formula retail)",
    "other_locations": "Other locations of the chain",
    "floor_area_sqft": "Floor area",
    "floor_area_before_sqft": "Floor area before the project",
    "merges_storefronts": "Storefronts merged",
    "existing_use_stated": "Last use of the space, as described",
    "changes_existing_business": "Change to a business already there",
    "amends_prior_approval": "Changes the conditions of an earlier approval",
    "stories": "Stories the business is on",
    "closing": "Closing time",
    "entertainment_described": "Live music, amplified sound or dancing",
    "entertainment_kind": "Kind of entertainment",
    "outdoor_area": "Outdoor area",
    "outdoor_alcohol_service": "Alcohol served outdoors",
    "seats": "Seats",
    "occupants_under_50": "Fewer than 50 people",
    # the one fact only an intake answer gives that is not a concept fact (`PROFILE_FACTS`)
    "existing_occupancy_group": "Existing occupancy group of the space",
    # facts the records give
    "existing_use_records": "Use the records show at this address",
    "active_licences": "Active ABC licences at this address",
    "prior_approvals": "Earlier approved use decisions at this address",
}
# The facts each row's rules read (app.memo.triggers for the zoning row, app.memo.rows and app.memo.pathway for the
# others), in report order. Record facts are listed after the concept facts.
ROW_FACTS: dict[str, tuple[str, ...]] = {
    "zoning_use": (
        "planning_uses",
        "stories",
        "closing",
        "formula_retail",
        "other_locations",
        "floor_area_sqft",
        "floor_area_before_sqft",
        "merges_storefronts",
        "existing_use_stated",
        "changes_existing_business",
        "amends_prior_approval",
        "entertainment_described",
        "entertainment_kind",
        "outdoor_area",
        "licence_type",
        "alcohol_transaction",
        "existing_use_records",
        "prior_approvals",
    ),
    "alcohol": (
        "planning_uses",
        "alcohol_served",
        "licence_type",
        "licences_held",
        "alcohol_transaction",
        "changes_existing_business",
        "existing_use_stated",
        "active_licences",
    ),
    "entertainment": ("planning_uses", "entertainment_described", "entertainment_kind", "closing"),
    "health": ("planning_uses",),
    "building_change_of_use": (
        "planning_uses",
        "existing_use_stated",
        "changes_existing_business",
        "floor_area_sqft",
        "floor_area_before_sqft",
        "seats",
        "occupants_under_50",
        "existing_occupancy_group",
        "formula_retail",
        "existing_use_records",
    ),
    "outdoor": ("outdoor_area", "outdoor_alcohol_service", "changes_existing_business"),
}
RECORD_FACTS: frozenset[str] = frozenset({"existing_use_records", "active_licences", "prior_approvals"})
# Facts read straight from the profile, not from `ConceptFacts`: the existing occupancy group, which only the
# applicant's intake answer gives (app.memo.intake) and the building row reads (app.memo.rows).
PROFILE_FACTS: frozenset[str] = frozenset({"existing_occupancy_group"})
OCCUPANCY_GROUP_WORDS: dict[str, str] = {"B": "Group B", "A-2": "Assembly Group A-2"}
# The entertainment the description gives (the rules read the three flags as well as the kind), in report order.
ENTERTAINMENT_FLAGS: tuple[tuple[str, str], ...] = (
    ("live_entertainment", "Live music or performance"),
    ("amplified_sound", "Amplified sound or a DJ"),
    ("dancing", "Dancing"),
)
# Every concept fact the report lists, in its order: MISSING_PHRASES' order, with the entertainment flags before the
# kind of entertainment.
CONCEPT_FACT_ORDER: tuple[str, ...] = tuple(
    n
    for name in MISSING_PHRASES
    for n in (("entertainment_described", name) if name == "entertainment_kind" else (name,))
)

YES_NO = {True: "Yes", False: "No"}
VALUE_WORDS: dict[str, dict[Any, str]] = {
    "alcohol_served": {
        "beer_wine": "Beer and wine",
        "full_liquor": "Beer, wine and spirits",
        "none": "No alcohol",
    },
    "alcohol_transaction": {
        "new_licence": "A new licence",
        "person_to_person_transfer": "A transfer from another owner",
        "premises_transfer": "A transfer from other premises",
        "licence_already_held": "A licence the business already holds",
    },
    "changes_existing_business": {
        "none": "No change",
        "enlarge": "Enlarged",
        "intensify": "Intensified",
        "enlarge_and_intensify": "Enlarged and intensified",
    },
    "stories": {
        "first": "First story",
        "second": "Second story",
        "third_or_above": "Third story or above",
        "basement": "Basement",
    },
    "entertainment_kind": {
        "none": "None",
        "limited_live_performance": "Limited live performance",
        "place_of_entertainment": "Place of entertainment",
    },
    "outdoor_area": {
        "none": "None",
        "front": "In front",
        "rear_or_side": "At the rear or side",
        "rooftop": "On the roof",
        "parking_lot": "In a parking lot",
        "sidewalk": "On the sidewalk",
    },
}
NOT_COVERED_USE = "A use the rule table does not cover"
LATE_CLOSE_WORDS = {"after_2am": "After 2 a.m.", "after_midnight": "After midnight"}
DERIVED_PREFIX = "Worked out by the rules from"
# When the description says nothing about alcohol the rules read "no alcohol" (the alcohol row is then not needed).
NO_ALCOHOL_MENTIONED = "Your description does not mention alcohol"
NONE_ON_FILE = "None on file"
NOT_SHOWN = "Not shown by the records"


# ---- where the applicant's facts came from -----------------------------------------------------------------------
@dataclass(frozen=True)
class FactOrigins:
    """What the runner knows about where each profile field came from.

    `quotes`: profile field -> the applicant's words that the intake model's quotes for it point at, cut from the
    applicant's text (`counted_quotes`). `answered`: the fields an intake answer set. `clarified`: the fields a
    follow-up answer set. `requested`: the fields the request set directly (profile overrides)."""

    quotes: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    answered: frozenset[str] = frozenset()
    clarified: frozenset[str] = frozenset()
    requested: frozenset[str] = frozenset()


def counted_quotes(quotes: Iterable[FactQuote], text: str) -> dict[str, tuple[str, ...]]:
    """The applicant's words that the intake model's quotes point at, by field, each once, in the order given.
    Each is cut from the applicant's text as written, never the model's own string: a quote in parts ("a ... b")
    gives one snippet per part, so words from different places are never shown as one sentence. A quote not
    found in the text gives nothing (the stated-facts check does not count it either)."""
    out: dict[str, list[str]] = {}
    for q in quotes:
        for span in quote_spans(q.quote, text):
            kept = out.setdefault(q.field, [])
            if span not in kept:
                kept.append(span)
    return {f: tuple(v) for f, v in out.items()}


def _basis_fields(basis: str | None) -> list[str]:
    return [b.strip() for b in (basis or "").split(",") if b.strip()]


def _origin(fields: Sequence[str], origins: FactOrigins) -> FactOrigin:
    """An answer the applicant gave wins over the description, as it does on the profile."""
    for kind, given in (
        ("intake_answer", origins.answered),
        ("clarification_answer", origins.clarified),
        ("request", origins.requested),
    ):
        if any(f in given for f in fields):
            return kind  # type: ignore[return-value]
    return "description"


def _quotes(fields: Sequence[str], origins: FactOrigins) -> list[str]:
    found: list[str] = []
    for f in fields:
        for pooled in QUOTE_GROUPS.get(f, (f,)):
            for q in origins.quotes.get(pooled, ()):
                if q not in found:
                    found.append(q)
    return found


# ---- values in plain words -----------------------------------------------------------------------------------
def _licence_words(number: str) -> str:
    kind = LICENCE_TYPES.get(number)
    return f"Type {number} ({kind.label})" if kind else f"Type {number}"


def _words(name: str, value: Any) -> str:
    if isinstance(value, bool):
        return YES_NO[value]
    words = VALUE_WORDS.get(name, {})
    return words.get(value, str(value).replace("_", " "))


def fact_value(name: str, concept: ConceptFacts) -> str | None:
    """One concept fact in plain words; None when it is not known."""
    if name == "entertainment_described":  # none described is "no": the fact is then not listed
        said = [label for flag, label in ENTERTAINMENT_FLAGS if getattr(concept, flag)]
        return ", ".join(said) or None
    if name == "closing":
        c = concept.closing
        if c.missing:
            return None
        if c.minute is not None:
            return format_time(c.minute)
        return LATE_CLOSE_WORDS.get(c.bucket or "")
    if name == "food_service" and not concept.food_service.missing:
        # an answered kind of food or drink service is the concept's use: the report lists it once, as the kind of
        # business ("planning_uses", from the answer)
        return None
    fact: Fact[Any] = getattr(concept, name)
    if fact.missing:
        return None
    value = fact.value
    if name == "planning_uses":
        return ", ".join(USE_LABELS[u] for u in value) if value else NOT_COVERED_USE
    if name == "licence_type":
        return _licence_words(value)
    if name == "licences_held":
        return ", ".join(_licence_words(v) for v in value)
    if name in ("existing_use_stated",):
        return ", ".join(EXISTING_USE_LABELS.get(v, str(v)) for v in value)
    if name == "stories":
        return ", ".join(_words("stories", v) for v in value)
    if name in ("floor_area_sqft", "floor_area_before_sqft"):
        return f"{int(value):,} sq ft"
    if name in ("seats", "other_locations"):
        return f"{int(value):,}"
    return _words(name, value)


def _source(name: str, concept: ConceptFacts) -> tuple[str, str | None]:
    if name == "entertainment_described":
        flags = [flag for flag, _ in ENTERTAINMENT_FLAGS if getattr(concept, flag)]
        return ("stated" if flags else "missing"), ",".join(flags) or None
    if name == "closing":
        return concept.closing.source, concept.closing.basis
    fact: Fact[Any] = getattr(concept, name)
    return fact.source, fact.basis


def concept_fact(name: str, concept: ConceptFacts, origins: FactOrigins) -> MemoFact:
    """One fact the rules read from the concept, with where it came from."""
    label = FACT_LABELS[name]
    value = fact_value(name, concept)
    source, basis = _source(name, concept)
    if source == "missing" or value is None:
        return MemoFact(
            fact=name,
            label=label,
            value=None,
            origin="not_known",
            origin_label=FACT_ORIGIN_LABELS["not_known"],
        )
    fields = _basis_fields(basis)
    origin = _origin(fields, origins)
    quotes = _quotes(fields, origins) if origin == "description" else []
    derived = source == "derived"
    origin_label = FACT_ORIGIN_LABELS[origin]
    if (
        name == "alcohol_served"
        and value == VALUE_WORDS["alcohol_served"]["none"]
        and origin == "description"
    ):
        origin_label = NO_ALCOHOL_MENTIONED if not quotes else origin_label
        derived = derived and bool(quotes)
    if derived:
        origin_label = f"{DERIVED_PREFIX} {origin_label[:1].lower()}{origin_label[1:]}"
    return MemoFact(
        fact=name,
        label=label,
        value=value,
        origin=origin,
        origin_label=origin_label,
        derived=derived,
        quotes=quotes,
    )


def profile_fact(name: str, profile: BusinessProfile, origins: FactOrigins) -> MemoFact | None:
    """One fact of `PROFILE_FACTS`, with where it came from; None when the profile does not hold it (the building
    row then names it as not given). Only an answer gives it, so an origin the runner does not know is the request."""
    value = getattr(profile, name)
    if value is None:
        return None
    origin = _origin([name], origins)
    if origin == "description":  # never the description: the intake model cannot set it (MODEL_MAY_NOT_SET)
        origin = "request"
    return MemoFact(
        fact=name,
        label=FACT_LABELS[name],
        value=OCCUPANCY_GROUP_WORDS.get(str(value), str(value)),
        origin=origin,
        origin_label=FACT_ORIGIN_LABELS[origin],
    )


def _record_fact(name: str, value: str, citations: Iterable[str]) -> MemoFact:
    return MemoFact(
        fact=name,
        label=FACT_LABELS[name],
        value=value,
        origin="record",
        origin_label=FACT_ORIGIN_LABELS["record"],
        citations=list(dict.fromkeys(citations)),
    )


def record_facts(site: SiteFacts) -> dict[str, MemoFact]:
    """The facts the rules read from the records at the report's own street address, on the rules date."""
    shown_by = [c for line in site.existing_use_lines for c in line.citations]
    existing = (
        _record_fact("existing_use_records", USE_LABELS[site.existing_use], shown_by)
        if site.existing_use is not None
        else _record_fact("existing_use_records", NOT_SHOWN, shown_by)
    )
    licences = _record_fact(
        "active_licences",
        "; ".join(_licence_words(lic.licence_type) for lic in site.licences) or NONE_ON_FILE,
        (lic.citation for lic in site.licences),
    )
    approvals = _record_fact(
        "prior_approvals",
        "; ".join(
            f"{d.permit_type} ({d.date.isoformat() if d.date else 'undated'})" for d in site.prior_decisions
        )
        or NONE_ON_FILE,
        (d.citation for d in site.prior_decisions),
    )
    return {f.fact: f for f in (existing, licences, approvals)}


def _named_missing(determinations: Determinations) -> set[str]:
    """Every missing-input phrase a row or a trigger names."""
    named = {phrase for row in determinations.rows for phrase in row.missing_inputs}
    named |= {phrase for t in determinations.pathway.triggers for phrase in t.missing_inputs}
    return named


def fact_list(
    profile: BusinessProfile, determinations: Determinations, origins: FactOrigins
) -> list[MemoFact]:
    """Every fact the rules read from the concept that is known, then every one that is not known and that a row
    or a trigger names or that the stated-facts check left not known. In the order of `CONCEPT_FACT_ORDER`."""
    concept = concept_facts(profile)
    named = _named_missing(determinations)
    known: list[MemoFact] = []
    unknown: list[MemoFact] = []
    for name in CONCEPT_FACT_ORDER:
        f = concept_fact(name, concept, origins)
        if f.origin != "not_known":
            known.append(f)
        elif name in MISSING_PHRASES and (MISSING_PHRASES[name] in named or name in concept.cleared_facts):
            unknown.append(f)
    given = [g for name in sorted(PROFILE_FACTS) if (g := profile_fact(name, profile, origins)) is not None]
    return [*known, *given, *unknown]


def row_facts(
    area: str, profile: BusinessProfile, site: SiteFacts | None, origins: FactOrigins
) -> list[MemoFact]:
    """The known facts one row's rules read (`ROW_FACTS`), concept facts first, then the record facts. What is
    not known is the row's own `missing_inputs`."""
    concept = concept_facts(profile)
    records = record_facts(site) if site is not None else {}
    out: list[MemoFact] = []
    for name in ROW_FACTS.get(area, ()):
        if name in RECORD_FACTS:
            if name in records:
                out.append(records[name])
            continue
        if name in PROFILE_FACTS:
            given = profile_fact(name, profile, origins)
            if given is not None:
                out.append(given)
            continue
        f = concept_fact(name, concept, origins)
        if f.origin != "not_known":
            out.append(f)
    return out


# ---- comparable cases and the base rate's records --------------------------------------------------------------
def comparable_case(s: Scored, *, opposition: bool = False) -> ComparableCase:
    """One ranked candidate with its recorded facts. No model text. The opposition flag is shown only when
    `opposition` (settings.REPORT_OPPOSITION_FLAG) is on."""
    a = s.app
    source = comparable_source(a)
    kind = record_kind(a)
    return ComparableCase(
        application_id=a.id,
        citation_id=f"app:{a.id}",
        source=source,
        source_label=source_label(source),
        record_kind=kind,
        record_kind_label=RECORD_KIND_LABELS[kind],
        permit_type=a.permit_type,
        use_types=list(a.use_types),
        address=a.address,
        distance_m=round(s.distance_m, 1),
        filed_at=a.filed_at.isoformat() if a.filed_at else None,
        decided_at=a.decided_at.isoformat() if a.decided_at else None,
        days_to_decision=days_to_decision(a.filed_at, a.decided_at),
        # "cancelled" where the case's own status says so (`case_outcome`)
        outcome=case_outcome(a),
        hours_close=a.hours_close,
        conditions=list(a.conditions),
        opposition_noted=a.opposition_noted if opposition else None,
        similarity_score=s.score,
        lat=a.lat,
        lng=a.lng,
        source_url=a.source_url,
    )


def comparable_cases(
    candidates: Sequence[Scored], limit: int = COMPARABLE_LIMIT, *, opposition: bool = False
) -> list[ComparableCase]:
    """The top `limit` of the fixed ranking, in ranking order."""
    return [comparable_case(s, opposition=opposition) for s in candidates[:limit]]


def comparables_note(n: int) -> str:
    return COMPARABLES_NOTE.format(n=n) if n else NO_COMPARABLES_NOTE


def counted_decisions(apps: Iterable[Application]) -> list[CountedDecision]:
    """The decisions the base rate counted, newest decision first, each with its source link."""
    rows = sorted(
        apps, key=lambda a: (a.decided_at is None, -(a.decided_at.toordinal() if a.decided_at else 0), a.id)
    )
    return [
        CountedDecision(
            application_id=a.id,
            permit_type=a.permit_type,
            address=a.address,
            outcome=case_outcome(a),
            filed_at=a.filed_at.isoformat() if a.filed_at else None,
            decided_at=a.decided_at.isoformat() if a.decided_at else None,
            source_url=a.source_url,
        )
        for a in rows
    ]
