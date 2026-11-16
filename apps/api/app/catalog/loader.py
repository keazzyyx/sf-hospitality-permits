"""Loads packages/catalog/data into memory and answers jurisdiction / applicability questions."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.catalog import rules
from app.core.config import settings

Confidence = Literal["verified", "estimated"]
JurisdictionLevel = Literal["federal", "state", "county", "city"]
Category = Literal[
    "business_registration",
    "federal_tax",
    "state_tax",
    "local_tax",
    "health",
    "food_safety_cert",
    "building",
    "fire",
    "alcohol",
    "zoning",
    "signage",
    "grease",
    "entertainment",
    "outdoor_dining",
    "labor",
    "music_licensing",
    "hotel",
    "mobile_vending",
    "other",
]

GENERIC_STATE = "XX"
GENERIC_CITY = "generic_city"


class Range(BaseModel):
    model_config = ConfigDict(frozen=True)
    min: float = Field(ge=0)
    max: float = Field(ge=0)


class CatalogPermit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    category: Category
    issuing_agency: str
    jurisdiction_level: JurisdictionLevel
    typical_timeline_days: Range
    fee_range_usd: Range
    prerequisites: list[str]
    applies_when: dict[str, Any]
    application_url: str
    notes: str
    last_verified: str
    confidence: Confidence
    sources: list[str] = Field(default_factory=list)
    renewal: str | None = None
    stall_risk: str | None = None

    def applies_to(self, profile: Mapping[str, Any]) -> bool:
        """The rule matches the profile's literal values (a fact marked "unknown" matches no value)."""
        return rules.evaluate(self.applies_when, profile)

    def applicability(self, profile: Mapping[str, Any]) -> bool | None:
        """True or False when the rule is decided whatever the profile's unknown facts hold; None when it
        depends on them (`rules.applicability`)."""
        return rules.applicability(self.applies_when, profile)


class Jurisdiction(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: Literal["federal", "state", "city"]
    name: str
    state: str | None = None
    city_slug: str | None = None
    county: str | None = None
    supported: bool = True
    aliases: list[str] = Field(default_factory=list)
    notes: str = ""


@dataclass
class ResolvedJurisdiction:
    city_slug: str | None
    city_name: str | None
    state: str | None
    county: str | None
    supported: bool
    permits: list[CatalogPermit] = field(default_factory=list)


_slug_re = re.compile(r"[^a-z0-9]+")


def _norm(text: str) -> str:
    return _slug_re.sub(" ", text.lower()).strip()


class Catalog:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.federal: list[CatalogPermit] = []
        self.states: dict[str, tuple[Jurisdiction, list[CatalogPermit]]] = {}
        self.cities: dict[str, tuple[Jurisdiction, list[CatalogPermit]]] = {}
        self.permits: dict[str, CatalogPermit] = {}
        self._alias_index: dict[str, str] = {}
        self._load()

    # -- loading --------------------------------------------------------------------------
    def _load(self) -> None:
        for path in sorted(self.data_dir.rglob("*.json")):
            doc = json.loads(path.read_text())
            if "jurisdiction" not in doc:
                continue
            jur = Jurisdiction.model_validate(doc["jurisdiction"])
            permits = [CatalogPermit.model_validate(p) for p in doc["permits"]]
            for p in permits:
                if p.id in self.permits:
                    raise ValueError(f"duplicate permit id {p.id} in {path}")
                self.permits[p.id] = p
            if jur.level == "federal":
                self.federal.extend(permits)
            elif jur.level == "state":
                self.states[jur.state or ""] = (jur, permits)
            else:
                slug = jur.city_slug or path.stem
                self.cities[slug] = (jur, permits)
                if slug != GENERIC_CITY:
                    self._alias_index[_norm(jur.name)] = slug
                    self._alias_index[_norm(slug.replace("_", " "))] = slug
                    for alias in jur.aliases:
                        self._alias_index[_norm(alias)] = slug
        if not self.permits:
            raise RuntimeError(
                f"no permit catalog files under {self.data_dir} (is packages/catalog/data/ checked out? "
                "CATALOG_DIR points the API at it)"
            )

    # -- lookups --------------------------------------------------------------------------
    @property
    def supported_cities(self) -> list[Jurisdiction]:
        return sorted(
            (j for slug, (j, _) in self.cities.items() if slug != GENERIC_CITY and j.supported),
            key=lambda j: j.name,
        )

    def resolve_city(self, text: str | None) -> str | None:
        """Map free text ("SF Mission", "Brooklyn") to a supported city slug, or None."""
        if not text:
            return None
        n = _norm(text)
        if n in self._alias_index:
            return self._alias_index[n]
        # longest alias contained in the text wins
        best: tuple[int, str] | None = None
        for alias, slug in self._alias_index.items():
            if re.search(rf"\b{re.escape(alias)}\b", n) and (best is None or len(alias) > best[0]):
                best = (len(alias), slug)
        return best[1] if best else None

    def city(self, slug: str | None) -> Jurisdiction | None:
        return self.cities[slug][0] if slug and slug in self.cities else None

    def jurisdiction_for(self, state: str | None, city_slug: str | None) -> ResolvedJurisdiction:
        """Federal + state (or generic state) + city (or generic city checklist)."""
        permits: list[CatalogPermit] = list(self.federal)
        city_jur = self.city(city_slug)
        supported = city_jur is not None and city_jur.supported and city_slug != GENERIC_CITY
        effective_state = (city_jur.state if city_jur else state) or None
        if effective_state and effective_state in self.states:
            permits += self.states[effective_state][1]
        else:
            permits += self.states[GENERIC_STATE][1]
        if supported and city_jur is not None:
            permits += self.cities[city_slug or ""][1]
        else:
            permits += self.cities[GENERIC_CITY][1]
        return ResolvedJurisdiction(
            city_slug=city_slug if supported else None,
            city_name=city_jur.name if (city_jur and supported) else None,
            state=effective_state,
            county=city_jur.county if (city_jur and supported) else None,
            supported=supported,
            permits=permits,
        )

    def applicable(self, profile: Mapping[str, Any]) -> list[CatalogPermit]:
        """The permits whose rule is decided and matches (`CatalogPermit.applicability` True). A permit left
        undetermined by an unknown fact is not among them: `app.tools.catalog_tool.lookup` lists it apart."""
        jur = self.jurisdiction_for(profile.get("state"), profile.get("city_slug"))
        chosen = [p for p in jur.permits if p.applicability(profile) is True]
        return sorted(chosen, key=lambda p: p.id)

    def get(self, permit_id: str) -> CatalogPermit | None:
        return self.permits.get(permit_id)

    # -- prompt context -------------------------------------------------------------------
    def context_text(self, state: str | None, city_slug: str | None) -> str:
        """Deterministic, compact catalog listing for one jurisdiction.

        Identical input → byte-identical output, so it can sit behind a prompt-cache
        breakpoint and be reused across every stage and every user in that jurisdiction.
        """
        jur = self.jurisdiction_for(state, city_slug)
        lines = [
            f"CATALOG JURISDICTION: city={jur.city_name or 'unsupported/unknown'} state={jur.state or 'unknown'} supported_city={str(jur.supported).lower()}",
            "Each entry: id | name | category | level | agency | days min-max | fee USD min-max | confidence | prerequisites | applies_when",
        ]
        for p in sorted(jur.permits, key=lambda p: p.id):
            lines.append(
                f"- {p.id} | {p.name} | {p.category} | {p.jurisdiction_level} | {p.issuing_agency} | "
                f"{int(p.typical_timeline_days.min)}-{int(p.typical_timeline_days.max)}d | "
                f"${int(p.fee_range_usd.min)}-{int(p.fee_range_usd.max)} | {p.confidence} | "
                f"prereqs={','.join(p.prerequisites) or 'none'} | applies_when={rules.describe(p.applies_when)}"
            )
            lines.append(f"    notes: {p.notes}")
            if p.stall_risk:
                lines.append(f"    stall_risk: {p.stall_risk}")
        return "\n".join(lines)

    def ids(self) -> Iterable[str]:
        return self.permits.keys()


@lru_cache
def get_catalog() -> Catalog:
    return Catalog(settings.CATALOG_DIR)
