"""MemoRunner: intake → records → precedent → finalize for the Location Risk Memo (report format 3).

The report is the rules and the evidence only. The intake is the only model call: it reads the description
into facts, and the stated-facts check (app.memo.stated) keeps only what the text states. Everything after it is
code. `collect_records` reads the store through the same TOOL-span tool handlers the checklist's agents call
(geocode, nearby records, overlays, zoning, density, base rate, candidate ranking) and runs the rules once
(`app.memo.pathway.determine`, rule table v2): the pathway, every row's status, status note, approval and agency,
the overall line and the entitlement path. The rules are read for a rules date (`MemoRunInput.rules_date`; today
when none is given) and for the census tract of the geocoded point (`app.memo.tracts.tract_at`).
`assemble_memo` builds every field of the report in code: the rows as the rules set them, the facts each row's
rules read with where each came from, the comparables (the top of the fixed ranking, each with what its record
says), the decisions behind the outcome counts (app.memo.evidence) and the site history. No field holds text a
model wrote, and no clarifying question a model wrote is asked: what is not known is named by the rules.

Site history: every record on file at the report's own address or parcel (building work included) is listed by
code in `Memo.site_history`.

Answer rounds (owner decision of 2026-11-16, app.memo.answers): what the intake left before the applicant's answers
(the checked profile, what the check cleared, where each fact came from) is the memo's `IntakeBasis`, carried on the
`memo` event and kept with the memo. `run_memo` puts the answers on it with `apply_basis`; `run_answers` puts a
round's merged answers on the kept one with the same function, with no model call and no second stated-facts check,
and both then read the records and the rules by the same code (`_after_intake`).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import neatlogs
from anthropic import AsyncAnthropic
from precedent.geocode import Geocoder, GeocodeResult
from precedent.models import Application, Business, OutcomeFeedback, Overlay
from precedent.store import Store
from precedent.store.base import Nearby, ZoningInfo

from app.agents import prompts
from app.agents.runner import AgentRunner, RunInput, RunnerEvent, StageError, _Submit
from app.catalog.loader import Catalog
from app.core.config import Settings
from app.core.config import settings as app_settings
from app.core.observability import set_span_attributes
from app.memo import analytics
from app.memo.analytics import FT_500_M, FT_1000_M, BaseRate, Density, Scored
from app.memo.answers import IntakeBasis, apply_basis, intake_basis
from app.memo.evidence import (
    COMPARABLE_LIMIT,
    FactOrigins,
    comparable_cases,
    comparables_note,
    counted_decisions,
    counted_quotes,
    fact_list,
    row_facts,
)
from app.memo.facts import SiteFacts, concept_facts, site_facts
from app.memo.intake import IntakeAnswers, answered_fields
from app.memo.pathway import determine, planning_use
from app.memo.report import (
    SITE_READ_RADIUS_M,
    SiteRecord,
    build_site_history,
    case_outcome,
    determination_citations,
    record_sources,
    rules_overall,
    rules_rows,
    site_of,
    site_records,
    source_notes_for,
)
from app.memo.stated import check_stated, no_alcohol_can_stand, stated_text, without_model_text
from app.memo.tracts import tract_at
from app.models.memo import (
    RECORDS_LIMITS,
    STATUS_DEFINITIONS,
    ApprovalArea,
    BaseRateBlock,
    Citation,
    Determinations,
    Memo,
    MemoTeaser,
    OverlayBlock,
    SiteHistory,
    ZoningBlock,
)
from app.models.profile import BusinessProfile, ClarifyingQuestion, MemoIntakeResult
from app.tools.precedent_tools import (
    BaseRateInput,
    GeocodeInput,
    LatLng,
    NearbyBusinessesInput,
    NearbyInput,
    NearbyLicensesInput,
    _base_rate,
    _geocode,
    _nearby_apps,
    _nearby_businesses,
    _nearby_licenses,
    _overlays_at,
    _zoning_at,
    read_base_rate_rows,
    scrub_summary,
)

log = logging.getLogger(__name__)

SUBMIT_MEMO_INTAKE = _Submit(
    "submit_intake_result",
    MemoIntakeResult,
    "Submit the structured BusinessProfile, a quote for every rule-read field you set (and any clarifying "
    "questions). Required to finish.",
)

# The 1,000 ft reads keep only the nearest rows (200 applications, 300 licences, 1,000 per group for the base
# rate), which on a crowded parcel can drop records at the report's own address. One more read takes every
# record of any kind this close to the point (SITE_READ_RADIUS_M, 30 m); its limit is far above what 30 m can
# hold.
SITE_READ_LIMIT = 5000

# The progress messages of the four stages. No stage after the intake calls a model.
STAGE_MESSAGES = {
    "intake": "Reading your concept…",
    # an answer round's intake stage: no model call, the answers go on the facts read when the memo was made
    "answers": "Applying your answers to the facts read from your description…",
    "records": "Pulling records within 500 ft and 1,000 ft of {address}…",
    "precedent": "Ranking {n} comparable cases by a fixed score…",
    "finalize": "Assembling the report from the rules and the records…",
}
# The fixed lines at the end of every report.
DISCLAIMERS = [
    f"{app_settings.APP_NAME} is operational guidance, not legal advice. Confirm every requirement with the issuing agency "
    "before relying on it.",
    "Comparable cases and counts come from public records (DataSF, California ABC, SF Planning) as of the data "
    "date shown; records may lag agency decisions by weeks.",
    "Statuses are set by rules from the public record and are not a guarantee. Planning Commission and ABC "
    "decisions are discretionary.",
    "No sentence in this report is written by an AI model. A model reads your description into facts; each fact "
    "shows the words it came from, and what your words do not state is listed as not known.",
]


def required_areas(profile: BusinessProfile) -> list[ApprovalArea]:
    """The approvals this concept needs a row for, in report order.

    Zoning and use, the health permit, and the building permit / change of use always; the alcohol licence
    when the concept serves alcohol; the entertainment permit when it has live entertainment, amplified sound
    (a DJ) or dancing, or stays open after 2 a.m. (the Extended-Hours Premises permit, Police Code § 1070 et
    seq., is the Entertainment Commission's, with or without entertainment); the outdoor row when it has a
    patio, rooftop, sidewalk seating or a parklet. A Bar always gets the alcohol row (§ 102; a bar that serves no
    alcohol, by the answer or the description's own words, is not a Bar: pathway rule 1b), and the v2 fields
    count as well as the older flags: a stated closing time after 2 a.m., an entertainment kind that takes a
    permit, an outdoor area that is placed. A reading the stated-facts check cleared (the intake model read alcohol,
    entertainment or an outdoor area the text does not state) adds the row too: the row then says it is not known
    (app.memo.stated)."""
    wanted: set[str] = {"zoning_use", "health", "building_change_of_use"}
    concept = concept_facts(profile)
    # a Bar sells alcohol by its § 102 definition, whether or not the description says so
    if (
        profile.serves_alcohol
        or profile.alcohol_type != "none"
        or planning_use(profile) == "bar"
        or concept.alcohol_not_stated
    ):
        wanted.add("alcohol")
    # the v2 fields count as well as the older flags: a closing time after 2 a.m., or an entertainment kind
    # that takes a permit
    if (
        profile.live_entertainment
        or profile.amplified_sound
        or profile.dancing
        or profile.closes_after_2am
        or (concept.closing.stated and concept.closing.after_2am)
        or profile.entertainment_kind in ("limited_live_performance", "place_of_entertainment")
        or concept.entertainment_not_stated
    ):
        wanted.add("entertainment")
    if (
        profile.outdoor_seating
        or profile.sidewalk_or_parklet
        or profile.outdoor_area not in (None, "none")
        or concept.outdoor_not_stated
    ):
        wanted.add("outdoor")
    order: tuple[ApprovalArea, ...] = (
        "zoning_use",
        "alcohol",
        "entertainment",
        "health",
        "building_change_of_use",
        "outdoor",
    )
    return [a for a in order if a in wanted]


class AddressNotFoundError(ValueError):
    pass


class OutsideCoverageError(ValueError):
    pass


@dataclass
class MemoRunInput:
    address: str
    description: str
    lat: float | None = None
    lng: float | None = None
    prior_profile: BusinessProfile | None = None
    clarification_questions: list[ClarifyingQuestion] = field(default_factory=list)
    clarification_answers: dict[str, Any] = field(default_factory=dict)
    profile_overrides: dict[str, Any] = field(default_factory=dict)
    allow_clarification: bool = True
    # The applicant's answers to the optional intake questions (app.memo.intake). Applied by code to the profile
    # the intake model built, before the rules read it: an answer wins over the description, a skipped one
    # changes nothing. A clarification run passes the same answers again.
    intake_answers: IntakeAnswers = field(default_factory=IntakeAnswers)
    # The date whose rules apply (rule table v2). None = today, which is what a live report uses; a past date
    # reads every control as it stood on that day. Only the rules read it: the records, the comparables and
    # the counts are today's.
    rules_date: dt.date | None = None


@dataclass
class AnswersRunInput:
    """An answer round (app.memo.answers): the memo's own address, coordinates and description, the intake result
    kept with it, and the merged answers."""

    address: str
    description: str
    basis: IntakeBasis
    intake_answers: IntakeAnswers
    lat: float | None = None
    lng: float | None = None
    rules_date: dt.date | None = None


@dataclass
class RecordBundle:
    geo: GeocodeResult
    zoning: ZoningInfo | None
    overlays: list[Overlay]
    applications: list[Nearby[Application]]  # within 1,000 ft, non-license
    licenses_500: list[Nearby[Application]]
    licenses_1000: list[Nearby[Application]]
    businesses: list[Nearby[Business]]
    density: Density
    base_rate: BaseRate
    candidates: list[Scored]
    feedback: list[Nearby[OutcomeFeedback]]
    citations: dict[str, Citation]
    site_history: SiteHistory  # what the report shows: at most SITE_HISTORY_LIMIT entries, counts over all
    site_records: list[SiteRecord]  # every record at the report's address or parcel, newest first
    # What the rules decided from the profile, the zoning, the overlays, the site records, the census tract
    # and the rules date: the pathway, every row's status, status note, approval and agency, the overall line,
    # the entitlement path. No stage changes it.
    determinations: Determinations
    # the census tract of the geocoded point as ABC writes it ("208.01"); None outside the county
    tract: str | None = None
    # what the records at the report's own street address show on the rules date (the facts the rules read)
    on_site: SiteFacts | None = None


class MemoRunner(AgentRunner):
    # the memo's intake records only stated facts, each with a quote (app.memo.stated)
    intake_prompt = prompts.MEMO_INTAKE
    intake_submit = SUBMIT_MEMO_INTAKE

    def __init__(
        self,
        client: AsyncAnthropic,
        catalog: Catalog,
        settings: Settings,
        store: Store,
        geocoder: Geocoder,
        *,
        today: dt.date | None = None,
    ) -> None:
        super().__init__(client, catalog, settings, today=today)
        self.store = store
        self.geocoder = geocoder

    # ------------------------------------------------------------------ entry point
    async def run_memo(self, inp: MemoRunInput, emit: Any) -> AsyncIterator[RunnerEvent]:
        try:
            # 0. geocode (also the coverage gate: the SF geocoder only resolves SF addresses)
            await emit(
                RunnerEvent(
                    "stage", {"stage": "intake", "status": "started", "message": STAGE_MESSAGES["intake"]}
                )
            )
            geo = await self._geocode(inp)
            # 1. intake, the one model call: the city is known, so the model reads only the concept
            run_inp = RunInput(
                description=inp.description,
                prior_profile=inp.prior_profile,
                clarification_questions=inp.clarification_questions,
                clarification_answers=inp.clarification_answers,
                profile_overrides={
                    **inp.profile_overrides,
                    "city_slug": "san_francisco",
                    "state": "CA",
                    "city_name": "San Francisco",
                },
                allow_clarification=inp.allow_clarification,
            )
            intake = await self.intake(run_inp, "San Francisco", "CA")
            # The intake model may only record facts the text states: every field the rules read that no quote
            # from the text states is cleared, so it is not known and the rules name it (app.memo.stated).
            quotes = intake.quotes if isinstance(intake, MemoIntakeResult) else []
            text = self._stated_text(run_inp)
            checked = check_stated(intake.profile, quotes, text)
            if checked.cleared:
                log.info("intake: cleared what the text does not state: %s", checked.cleared)
            # What the intake left before the applicant's answers, kept with the memo so that an answer round can
            # put new answers on it without a model call (app.memo.answers): the checked profile with the
            # clarification answers and the overrides, what the check cleared, and where each fact came from.
            clarified = {
                q.maps_to for q in run_inp.clarification_questions if q.id in run_inp.clarification_answers
            }
            # `_merge_profile` resets every field the model may not set, and so the check's own reading that the
            # description states the business serves no alcohol (`no_alcohol_stated`, set by `check_stated`, which
            # overwrites whatever the model gave): it is code's, and is put back (fix of 2026-11-16: before it a
            # "zero-proof cocktail bar" was read as a Bar through the runner, though the rules say it is not one).
            # It is put back only where it can still stand on the profile with the clarification answers and the
            # overrides: one that gives a licence type, a licence held or alcohol served keeps the business a Bar,
            # as the check itself would (review fix of 2026-11-16: an override of licence type 48 on a "zero-proof
            # cocktail bar" was looked up as a Bar with no alcohol row).
            merged = self._merge_profile(checked.profile, run_inp)
            merged = merged.model_copy(
                update={
                    "no_alcohol_stated": checked.profile.no_alcohol_stated
                    and no_alcohol_can_stand(merged.model_dump())
                }
            )
            basis = intake_basis(
                merged,
                checked,
                quotes=counted_quotes(quotes, text),
                clarified=clarified,
                requested=inp.profile_overrides,
                given=self._given_fields(run_inp, IntakeAnswers()),
                model_versions=self.model_versions,
                geo=dataclasses.asdict(geo),
            )
            # The applicant's answers to the optional intake questions win over what the intake model read from
            # the description (app.memo.intake); a skipped question changes nothing. An answer round applies its
            # answers by the same function (`run_answers`).
            profile, origins = apply_basis(basis, inp.intake_answers)
            async for ev in self._after_intake(
                geo,
                profile,
                origins,
                emit,
                description=inp.description,
                rules_date=inp.rules_date,
                basis=basis,
            ):
                yield ev
        except AddressNotFoundError as exc:
            yield RunnerEvent("error", {"code": "address_not_found", "message": str(exc)})
        except OutsideCoverageError as exc:
            yield RunnerEvent("error", {"code": "outside_coverage", "message": str(exc)})
        except StageError as exc:
            log.exception("memo generation failed")
            yield RunnerEvent("error", {"code": "generation_failed", "message": str(exc)})

    async def run_answers(self, inp: AnswersRunInput, emit: Any) -> AsyncIterator[RunnerEvent]:
        """An answer round (app.memo.answers): the merged answers on the intake result kept with the memo, then the
        records and the rules exactly as `run_memo` reads them after its intake. No model call and no stated-facts
        check: the description is the same, and both ran on it when the memo was made."""
        try:
            await emit(
                RunnerEvent(
                    "stage", {"stage": "intake", "status": "started", "message": STAGE_MESSAGES["answers"]}
                )
            )
            # the address is fixed: the records are read at the point and parcel the memo's first run read
            if inp.basis.geo is not None:
                geo = GeocodeResult(**inp.basis.geo)
            else:
                geo = await self._geocode(
                    MemoRunInput(address=inp.address, description=inp.description, lat=inp.lat, lng=inp.lng)
                )
            profile, origins = apply_basis(inp.basis, inp.intake_answers)
            # the report names the model that read the description when the memo was made: no model ran now
            self.model_versions = dict(inp.basis.model_versions)
            async for ev in self._after_intake(
                geo,
                profile,
                origins,
                emit,
                description=inp.description,
                rules_date=inp.rules_date,
                basis=inp.basis,
            ):
                yield ev
        except AddressNotFoundError as exc:
            yield RunnerEvent("error", {"code": "address_not_found", "message": str(exc)})
        except OutsideCoverageError as exc:
            yield RunnerEvent("error", {"code": "outside_coverage", "message": str(exc)})
        except StageError as exc:
            log.exception("memo answer round failed")
            yield RunnerEvent("error", {"code": "generation_failed", "message": str(exc)})

    async def _after_intake(
        self,
        geo: GeocodeResult,
        profile: BusinessProfile,
        origins: FactOrigins,
        emit: Any,
        *,
        description: str,
        rules_date: dt.date | None,
        basis: IntakeBasis,
    ) -> AsyncIterator[RunnerEvent]:
        """Everything after the intake, the same for a new memo and an answer round: the coverage gate, the records
        and the rules, the comparables, the report. The `memo` event carries the basis, which is stored with it."""
        if profile.city_slug not in self.settings.MEMO_COVERAGE_CITIES:
            raise OutsideCoverageError(
                f"Memos currently cover {', '.join(self.settings.MEMO_COVERAGE_CITIES)} only."
            )
        set_span_attributes(
            city=profile.city_slug, business_type=profile.business_type, address=geo.normalized_address
        )
        # No question a model wrote is asked, whatever the intake model returned: what is not known is
        # named by the rules ("Not known: X. Needed for: Y.").
        await emit(
            RunnerEvent(
                "stage",
                {
                    "stage": "intake",
                    "status": "completed",
                    "message": f"Concept: {self._describe(profile)}",
                },
            )
        )

        # 2. records, and the rules
        await emit(
            RunnerEvent(
                "stage",
                {
                    "stage": "records",
                    "status": "started",
                    "message": STAGE_MESSAGES["records"].format(address=geo.address),
                },
            )
        )
        bundle = await self.collect_records(geo, profile, emit, rules_date=rules_date)
        await emit(
            RunnerEvent(
                "stage",
                {
                    "stage": "records",
                    "status": "completed",
                    "message": f"{len(bundle.applications)} applications, {len(bundle.licenses_1000)} licenses, "
                    f"{len(bundle.overlays)} overlays found. Rules applied.",
                },
            )
        )

        # 3. precedent: the top of the fixed ranking
        await emit(
            RunnerEvent(
                "stage",
                {
                    "stage": "precedent",
                    "status": "started",
                    "message": STAGE_MESSAGES["precedent"].format(n=len(bundle.candidates)),
                },
            )
        )
        shown = min(len(bundle.candidates), COMPARABLE_LIMIT)
        await emit(
            RunnerEvent(
                "stage",
                {
                    "stage": "precedent",
                    "status": "completed",
                    "message": f"{shown} comparable {'case' if shown == 1 else 'cases'} listed.",
                },
            )
        )

        # 4. finalize
        await emit(
            RunnerEvent(
                "stage", {"stage": "finalize", "status": "started", "message": STAGE_MESSAGES["finalize"]}
            )
        )
        memo = self.assemble_memo(profile, bundle, origins=origins, description=description)
        set_span_attributes(
            overall_status=memo.overall.status,
            comparable_count=len(memo.comparable_cases),
            citation_count=len(memo.citations),
        )
        await emit(
            RunnerEvent("stage", {"stage": "finalize", "status": "completed", "message": "Memo ready."})
        )
        # stored and served with the memo: none of the intake model's own text (app.memo.stated)
        yield RunnerEvent(
            "memo", {"memo": memo, "profile": without_model_text(profile), "geo": geo, "basis": basis}
        )

    # ------------------------------------------------------------------ deterministic bundle
    async def _geocode(self, inp: MemoRunInput) -> GeocodeResult:
        out = await _geocode(GeocodeInput(address=inp.address))
        if not getattr(out, "found", False):
            if inp.lat is not None and inp.lng is not None:
                return GeocodeResult(
                    address=inp.address,
                    normalized_address=inp.address.upper(),
                    lat=inp.lat,
                    lng=inp.lng,
                    parcel=None,
                    zip_code=None,
                    source="client",
                    source_url="",
                    confidence=0.5,
                )
            raise AddressNotFoundError(
                f"Could not find '{inp.address}' in San Francisco's address database. Try the street number and name only, e.g. '995 Valencia St'."
            )
        return GeocodeResult(
            address=out.address or inp.address,
            normalized_address=out.normalized_address or inp.address.upper(),
            lat=float(out.lat),
            lng=float(out.lng),
            parcel=out.parcel,
            zip_code=out.zip_code,
            source=out.source or "unknown",
            source_url=out.source_url or "",
            confidence=float(out.confidence or 0.0),
        )

    @neatlogs.span(kind="CHAIN", name="memo.collect_records", capture_output=False)
    async def collect_records(
        self,
        geo: GeocodeResult,
        profile: BusinessProfile,
        emit: Any,
        *,
        rules_date: dt.date | None = None,
    ) -> RecordBundle:
        """Everything read for one report, and what the rules decide from it. `rules_date` is the date whose
        rules apply; None means today (`self.today`)."""
        pt = LatLng(lat=geo.lat, lng=geo.lng)
        await emit(
            RunnerEvent(
                "tool",
                {
                    "stage": "records",
                    "tool": "zoning_at",
                    "status": "started",
                    "message": "Looking up zoning and overlays…",
                },
            )
        )
        await _zoning_at(pt)
        await _overlays_at(pt)
        zoning = await self.store.zoning_at(geo.lat, geo.lng)
        overlays = await self.store.overlays_at(geo.lat, geo.lng)
        await emit(
            RunnerEvent(
                "tool",
                {
                    "stage": "records",
                    "tool": "zoning_at",  # same tool name as the started event above, so the UI can pair them
                    "status": "completed",
                    "message": f"{len(overlays)} overlays",
                    "rows": len(overlays),
                },
            )
        )

        await emit(
            RunnerEvent(
                "tool",
                {
                    "stage": "records",
                    "tool": "nearby_applications",
                    "status": "started",
                    "message": "Applications within 1,000 ft…",
                },
            )
        )
        apps_out = await _nearby_apps(NearbyInput(lat=geo.lat, lng=geo.lng, radius_m=FT_1000_M, limit=200))
        applications = await self.store.nearby_applications(
            geo.lat,
            geo.lng,
            FT_1000_M,
            kinds=[
                "cua",
                "planning_other",
                "entertainment_poe",
                "entertainment_llp",
                "entertainment_sound",
                "entertainment_other",
            ],
            limit=analytics.CANDIDATE_WINDOW,
        )
        await emit(
            RunnerEvent(
                "tool",
                {
                    "stage": "records",
                    "tool": "nearby_applications",
                    "status": "completed",
                    "message": f"{apps_out.count} applications",
                    "rows": apps_out.count,
                },
            )
        )

        await emit(
            RunnerEvent(
                "tool",
                {
                    "stage": "records",
                    "tool": "nearby_licenses",
                    "status": "started",
                    "message": "ABC licenses within 500 ft and 1,000 ft…",
                },
            )
        )
        await _nearby_licenses(
            NearbyLicensesInput(lat=geo.lat, lng=geo.lng, radius_m=FT_1000_M, active_only=False)
        )
        licenses_1000 = await self.store.nearby_applications(
            geo.lat, geo.lng, FT_1000_M, kinds=["abc_license"], limit=300
        )
        licenses_500 = [n for n in licenses_1000 if n.distance_m <= FT_500_M]
        await emit(
            RunnerEvent(
                "tool",
                {
                    "stage": "records",
                    "tool": "nearby_licenses",
                    "status": "completed",
                    "message": f"{len(licenses_500)} within 500 ft, {len(licenses_1000)} within 1,000 ft",
                    "rows": len(licenses_1000),
                },
            )
        )

        await emit(
            RunnerEvent(
                "tool",
                {
                    "stage": "records",
                    "tool": "nearby_businesses",
                    "status": "started",
                    "message": "Food & drink businesses within 500 ft…",
                },
            )
        )
        await _nearby_businesses(
            NearbyBusinessesInput(lat=geo.lat, lng=geo.lng, radius_m=FT_500_M, limit=300)
        )
        businesses = await self.store.nearby_businesses(geo.lat, geo.lng, FT_500_M, limit=300)
        await emit(
            RunnerEvent(
                "tool",
                {
                    "stage": "records",
                    "tool": "nearby_businesses",
                    "status": "completed",
                    "message": f"{len(businesses)} businesses",
                    "rows": len(businesses),
                },
            )
        )

        await emit(
            RunnerEvent(
                "tool",
                {
                    "stage": "records",
                    "tool": "base_rate",
                    "status": "started",
                    "message": "Computing the base rate…",
                },
            )
        )
        await _base_rate(
            BaseRateInput(
                lat=geo.lat, lng=geo.lng, profile=profile, zoning_district=zoning.district if zoning else None
            )
        )
        # the comparable list above keeps the 200 nearest records; the base rate needs every record within
        # 1,000 ft (a dense corridor has 400+), the same rows the base_rate tool reads: Planning rows for the
        # pool, and (read separately, so they cannot crowd the pool out of the limit) Entertainment Commission
        # permits and ABC licences only to count them as left out
        rate_pool = await read_base_rate_rows(self.store, geo.lat, geo.lng)
        rate = analytics.base_rate(
            rate_pool, profile, self.today, zoning_district=zoning.district if zoning else None
        )
        # labelled rows that can never be comparables (building work, other records, other premises) must not
        # use up the 200 nearest rows: top the list up with the nearest rows that can be, from the rows just
        # read. Citations and verify evidence follow, since both are built from `applications`. With no labels
        # nothing is added.
        applications = analytics.fill_candidate_window(applications, rate_pool)
        await emit(
            RunnerEvent(
                "tool",
                {
                    "stage": "records",
                    "tool": "base_rate",
                    "status": "completed",
                    "message": f"{rate.total} dated comparable decisions in {rate.window_years} years",
                    "rows": rate.total,
                },
            )
        )

        # site history: every record on file at the report's own address or parcel, whatever its kind. Read
        # from the rows already in hand plus one small read around the point (see SITE_READ_RADIUS_M), merged
        # by id. A record the store holds without a map point is never returned by these reads.
        at_point = await self.store.nearby_applications(
            geo.lat, geo.lng, SITE_READ_RADIUS_M, limit=SITE_READ_LIMIT
        )
        site = site_of(geo.address, geo.normalized_address, geo.parcel)
        at_site = site_records([*applications, *licenses_1000, *rate_pool, *at_point], site)
        site_history = build_site_history(at_site, site)

        dens = analytics.density(businesses, licenses_500, licenses_1000)
        candidates = analytics.rank_candidates(applications, profile, self.today)
        feedback = await self.store.feedback_near(geo.lat, geo.lng, FT_1000_M)
        citations = self._build_citations(geo, zoning, overlays, applications, licenses_1000, feedback, rate)
        # every listed site-history record can be cited as app:<id>, whatever its kind
        listed = {e.application_id for e in site_history.entries}
        for rec in at_site:
            if rec.app.id in listed:
                citations.setdefault(f"app:{rec.app.id}", self._application_citation(rec.app))
        # The pathway and every row's status, by rule. The rules read the full overlay list (the hours control
        # is on the district's own rows), every record at the site, not only the listed ones, the census tract
        # of the geocoded point (for the alcohol row's concentration lines) and the rules date. `today` is the
        # runner's own date, so the rules read no clock.
        tract = tract_at(geo.lat, geo.lng)
        on_site = site_facts(at_site, site, rules_date=rules_date or self.today, today=self.today)
        determinations = determine(
            profile,
            zoning,
            overlays,
            at_site,
            site,
            required_areas(profile),
            today=self.today,
            rules_date=rules_date,
            tract=tract,
        )
        # every record a rule line cites must resolve in the report's citation list: a licence at the site that
        # the site history does not list (it shows the newest SITE_HISTORY_LIMIT) is added here
        by_citation = {f"app:{rec.app.id}": rec for rec in at_site}
        for cid in determination_citations(determinations):
            if cid in citations:
                continue
            if cid in by_citation:
                citations[cid] = self._application_citation(by_citation[cid].app)
            else:
                log.warning("rule line cites %s, which is not in the citation list", cid)
        set_span_attributes(
            rows_applications=len(applications),
            rows_licenses=len(licenses_1000),
            rows_businesses=len(businesses),
            rows_overlays=len(overlays),
            rows_site_history=site_history.total,
            candidates=len(candidates),
            pathway_use=determinations.pathway.use,
            pathway_permission=determinations.pathway.permission,
            pathway_change_of_use=determinations.pathway.change_of_use,
            rules_date=determinations.pathway.rules_date,
            census_tract=tract,
            rule_statuses={r.area: r.status for r in determinations.rows},
            rule_status_notes={r.area: r.status_note for r in determinations.rows if r.status_note},
            rule_overall_status=determinations.overall_status,
        )
        return RecordBundle(
            geo=geo,
            zoning=zoning,
            overlays=overlays,
            applications=applications,
            licenses_500=licenses_500,
            licenses_1000=licenses_1000,
            businesses=businesses,
            density=dens,
            base_rate=rate,
            candidates=candidates,
            feedback=feedback,
            citations=citations,
            site_history=site_history,
            site_records=at_site,
            determinations=determinations,
            tract=tract,
            on_site=on_site,
        )

    @staticmethod
    def _application_citation(a: Application) -> Citation:
        when = a.decided_at or a.filed_at
        # a cancelled case is named as one, as in the comparables table (`case_outcome`)
        label = f"{a.permit_type} · {a.address or 'address n/a'} · {case_outcome(a).replace('_', ' ')}{f' ({when.year})' if when else ''}"
        return Citation(
            id=f"app:{a.id}",
            kind="application",
            label=label,
            source_url=a.source_url,
            excerpt=(scrub_summary(a.decision_summary) or a.description or "")[:300] or None,
        )

    @staticmethod
    def _build_citations(
        geo: GeocodeResult,
        zoning: ZoningInfo | None,
        overlays: list[Overlay],
        applications: list[Nearby[Application]],
        licenses: list[Nearby[Application]],
        feedback: list[Nearby[OutcomeFeedback]],
        rate: BaseRate,
    ) -> dict[str, Citation]:
        cites: dict[str, Citation] = {}
        if zoning is not None:
            cites[f"zoning:{zoning.district}"] = Citation(
                id=f"zoning:{zoning.district}",
                kind="zoning",
                label=f"Zoning {zoning.district} — {zoning.code_section}",
                source_url=zoning.source_url,
                excerpt=zoning.rules[:300],
            )
        for o in overlays:
            cites[f"overlay:{o.id}"] = Citation(
                id=f"overlay:{o.id}",
                kind="overlay",
                label=f"{o.name} — {o.code_section}",
                source_url=o.source_url,
                excerpt=o.rules[:300],
            )
        for n in applications:
            cites[f"app:{n.item.id}"] = MemoRunner._application_citation(n.item)
        for n in licenses:
            a = n.item
            cites[f"license:{a.id}"] = Citation(
                id=f"license:{a.id}",
                kind="license",
                label=f"ABC {a.permit_type} · {a.address or ''} · {a.status}",
                source_url=a.source_url,
                excerpt=(a.description or "")[:200] or None,
            )
        for n in feedback:
            f = n.item
            cites[f"feedback:{f.id}"] = Citation(
                id=f"feedback:{f.id}",
                kind="feedback",
                label=f"User-reported outcome: {f.outcome.replace('_', ' ')} for a {f.concept_type} at {f.address}",
                source_url="",
                excerpt=(f.notes or "")[:200] or None,
            )
        cites["stat:base_rate"] = Citation(
            id="stat:base_rate",
            kind="statistic",
            label=f"Dated Planning decisions: {rate.approved + rate.approved_with_conditions} approved / {rate.denied} denied / {rate.withdrawn} withdrawn; {rate.scope}",
            source_url="https://data.sf.gov",
            excerpt=(
                f"Not counted: {rate.excluded_grant_only} Entertainment Commission permits and ABC licences "
                "(lists of grants only)"
                + (
                    f", {rate.excluded_not_use_decision} Planning records that are not use decisions for this "
                    "kind of business (agency referrals, building work, other records, decisions about other "
                    "kinds of business)"
                    if rate.excluded_not_use_decision
                    else ""
                )
                + f" and {rate.excluded_undated} decided Planning rows without both dates."
            ),
        )
        cites["geo:address"] = Citation(
            id="geo:address",
            kind="statistic",
            label=f"Address record: {geo.address} ({geo.source})",
            source_url=geo.source_url,
            excerpt=f"parcel {geo.parcel or 'n/a'}",
        )
        return cites

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _data_as_of(bundle: RecordBundle) -> dt.date:
        """The report's records date: the newest fetch date among the applications read (today's date when
        none was read). A pending case's age is counted to this date."""
        newest = max((n.item.fetched_at for n in bundle.applications), default=dt.datetime.now(dt.UTC))
        as_of: dt.date = newest.date()
        return as_of

    @staticmethod
    def _stated_text(inp: RunInput) -> str:
        """The text the intake model's quotes may come from: the description and the clarification answers."""
        return stated_text(inp.description, inp.clarification_answers.values())

    @staticmethod
    def _given_fields(inp: RunInput, answers: IntakeAnswers) -> frozenset[str]:
        """The profile fields the applicant or the operator gave after the intake model read the text. The basis
        kept for an answer round holds these without the intake answers (`answers` empty)."""
        clarified = {q.maps_to for q in inp.clarification_questions if q.id in inp.clarification_answers}
        return frozenset({*clarified, *inp.profile_overrides, *answered_fields(answers)})

    # ------------------------------------------------------------------ assembly
    def assemble_memo(
        self,
        profile: BusinessProfile,
        bundle: RecordBundle,
        *,
        origins: FactOrigins | None = None,
        description: str = "",
    ) -> Memo:
        """The report: the rules and the evidence. Each row's status, rule lines, the facts its rules read and
        where each came from, what is not known, the referral steps and the source links; the comparables are the
        top of the fixed ranking, each with what its record says; the outcome counts list the decisions they
        count. No field holds text a model wrote."""
        determinations = bundle.determinations
        origins = origins or FactOrigins()
        rows = [
            row.model_copy(update={"facts": row_facts(row.area, profile, bundle.on_site, origins)})
            for row in rules_rows(determinations)
        ]
        overall = rules_overall(determinations)
        comparables = comparable_cases(bundle.candidates, opposition=self.settings.REPORT_OPPOSITION_FLAG)
        # one note per source that appears among the comparables, the nearby records or the site history
        site_history = bundle.site_history
        listed = {e.application_id for e in site_history.entries}
        sources: set[str] = {c.source for c in comparables}
        for n in (*bundle.applications, *bundle.licenses_1000):
            sources |= record_sources(n.item)
        for rec in bundle.site_records:
            if rec.app.id in listed:
                sources |= record_sources(rec.app)
        if bundle.feedback:
            sources.add("user_feedback")

        # every record a rule line, a pathway note or a fact cites, every comparable and every listed site record
        used: set[str] = {*overall.citations, *determination_citations(determinations)}
        used |= {c for row in rows for f in row.facts for c in f.citations}
        used |= {c.citation_id for c in comparables}
        used |= {e.citation_id for e in site_history.entries}
        z = bundle.zoning
        zoning_block = None
        if z is not None:
            used.add(f"zoning:{z.district}")
            zoning_block = ZoningBlock(
                district=z.district,
                name=z.name,
                bar_permission=z.bar_permission,
                restaurant_permission=z.restaurant_permission,
                rules=z.rules,
                code_section=z.code_section,
                citation_id=f"zoning:{z.district}",
            )
        overlays = []
        for o in bundle.overlays:
            if o.kind == "zoning_district":
                continue
            used.add(f"overlay:{o.id}")
            overlays.append(
                OverlayBlock(
                    name=o.name,
                    kind=o.kind,
                    effect=o.rules,
                    code_section=o.code_section,
                    citation_id=f"overlay:{o.id}",
                )
            )
        used |= {"stat:base_rate", "geo:address"}
        citations = [bundle.citations[c] for c in sorted(used) if c in bundle.citations]
        rate = bundle.base_rate
        return Memo(
            address=bundle.geo.address,
            lat=bundle.geo.lat,
            lng=bundle.geo.lng,
            parcel=bundle.geo.parcel,
            description=description,
            headline_findings=[h.model_copy(deep=True) for h in determinations.headline_findings],
            overall=overall,
            pathway=determinations.pathway,
            approvals=rows,
            facts=fact_list(profile, determinations, origins),
            could_not_establish=list(determinations.open_questions),
            records_limits=RECORDS_LIMITS,  # the contract's fixed line, on every report
            zoning=zoning_block,
            overlays=overlays,
            base_rate=BaseRateBlock(
                approved=rate.approved,
                approved_with_conditions=rate.approved_with_conditions,
                denied=rate.denied,
                withdrawn=rate.withdrawn,
                total=rate.total,
                window_years=rate.window_years,
                scope=rate.scope,
                rate_shown=rate.rate_shown,
                approval_rate_pct=rate.approval_rate_pct,
                excluded_grant_only=rate.excluded_grant_only,
                excluded_undated=rate.excluded_undated,
                excluded_not_use_decision=rate.excluded_not_use_decision,
                citation_id="stat:base_rate",
                counted=counted_decisions(rate.counted),
            ),
            comparable_cases=comparables,
            comparables_note=comparables_note(len(comparables)),
            site_history=site_history,
            source_notes=source_notes_for(sources),
            entitlement_path=determinations.entitlement_path,
            status_definitions=dict(STATUS_DEFINITIONS),
            citations=citations,
            disclaimers=list(DISCLAIMERS),
            generated_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            model_versions=dict(self.model_versions),
            data_as_of=self._data_as_of(bundle).isoformat(),
        )

    @staticmethod
    def teaser(memo: Memo) -> MemoTeaser:
        return MemoTeaser(
            overall_status=memo.overall.status,
            overall_line=memo.overall.line,
            comparable_count=len(memo.comparable_cases),
            approvals_count=len(memo.approvals),
            blockers_count=sum(
                1 for r in memo.approvals if r.status in ("potential_blocker", "not_permitted")
            ),
        )
