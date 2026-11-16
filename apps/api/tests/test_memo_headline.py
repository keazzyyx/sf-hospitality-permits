"""The headline findings (app.memo.pathway rule 9, change of 2026-11-16): what changes a business's plans at an
address is printed first, and the overall status reflects it, whatever else is still not known. No database
(but for the one PostGIS test, skipped without PRECEDENT_TEST_DATABASE_URL), no network, no model.

The case is 2301 Chestnut St (zoning district NC-2): a Restaurant with a full bar, 40 seats, an outdoor patio, not
a chain, 6,000 square feet, a new licence. NC-2 asks for a Conditional Use for a use of 4,001 square feet or more
(trigger T7, use size: the rules print "4,001 square feet or more"). The local store holds every SF ABC licence since
the data fix of 2026-11-15, and one is an ACTIVE Type 47 at 2301 CHESTNUT ST (abc:636535,
`tests/fixtures/abc_636535_2301_chestnut.json`, the real row). What the rules give there, and so what the report
leads with:

  licence on file (the space reads as a Restaurant, which continues), whether the business is enlarged not given:
      T7 is not decided, its own reading over the threshold: "If the existing business is enlarged or storefronts
      are merged, the concept needs a Conditional Use Authorization". Only if ENLARGED (or merged): intensifying
      alone does not apply the use size control (T7.not_new), so the headline does not say "or intensified". With
      "no merger" answered, the merger is not offered again: "If the existing business is enlarged, ...".
  licence on file, answered "enlarge": a Conditional Use, definite.
  licence on file, answered "intensify" or "none": T7 does not apply; nothing leads.
  no licence on file, last use not given: T7 reads the use as new and asks for a Conditional Use, but a former
      bar, restaurant or shop would make it turn on Interpretation 121.2, so the finding is not definite: "If the
      space was last used as another use (...), or the floor area grows, or storefronts are merged, ...". It does
      not raise the overall status.
  no licence on file, last used as another use: a Conditional Use, definite; with no story given the zoning row
      stays insufficient information (the user's decision of 2026-11-12) and the overall status is at least
      further review.
  no licence on file, last used as a restaurant: T7 is not decided (Zoning Administrator Interpretation 121.2): "If
      the floor area grows or storefronts are merged, ...".

Every contingent condition is checked here against the rules themselves: supplying an answer that meets it gives
the control it names (`test_each_contingent_condition_is_what_the_rules_give_once_answered`). No rule's outcome
changes: the tests check T7's own control is what it was.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

import pytest
from precedent.models import Application
from precedent.store.base import Nearby, ZoningInfo

from app.agents.memo_runner import SITE_READ_RADIUS_M, required_areas
from app.memo import facts, triggers
from app.memo.intake import IntakeAnswers, apply_intake_answers
from app.memo.pathway import (
    HEADLINE_TEXT,
    _at_report_address,
    determine,
    existing_use,
    most_severe,
    overall_lead,
)
from app.memo.report import (
    SiteRecord,
    build_site_history,
    parse_street_address,
    same_street_address,
    site_match,
    site_records,
)
from app.models.memo import Determinations, RowDetermination
from app.models.profile import BusinessProfile
from tests.test_all_rows_decided import NC_2, RULES_DATE, SITE
from tests.test_spelling import CHESTNUT_PROFILE

FIXTURE = Path(__file__).parent / "fixtures" / "abc_636535_2301_chestnut.json"
LICENCE = Application.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8"))["record"])
# the profile the work order names: Restaurant, full alcohol, 40 seats, an outdoor patio, not a chain, 6,000 sq ft,
# a new licence
BASE = {
    "part_of_chain": False,
    "floor_area_sqft": 6000,
    "liquor_licence": "new",
    "alcohol_served": "full_liquor",
}
ENLARGED = (
    "If the existing business is enlarged or storefronts are merged, the concept needs a Conditional Use "
    "Authorization, which the Planning Commission decides at a public hearing (Planning Code § 303). What would ask "
    "for one: use size. Not known: whether an existing business is to be enlarged or intensified; whether "
    "storefronts are to be merged."
)
EXISTING_USE_LINE = (
    "An active ABC Type 47 licence (on-sale general, eating place) is on file at 2301 Chestnut St. That is a licence "
    "type a Restaurant holds (Planning Code § 102), so the rules read the space as a Restaurant; other uses can hold "
    "it too."
)


def profile(**answers: Any) -> BusinessProfile:
    base = BusinessProfile.model_validate(CHESTNUT_PROFILE)
    return apply_intake_answers(base, IntakeAnswers.model_validate({**BASE, **answers})).normalized()


def on_file() -> list[SiteRecord]:
    matched = site_match(LICENCE, 0.0, SITE)
    assert matched is not None
    return [SiteRecord(LICENCE, 0.0, matched)]


def report(p: BusinessProfile, records: list[SiteRecord] | None = None) -> Determinations:
    return determine(p, NC_2, [], records or [], SITE, required_areas(p), today=RULES_DATE)


def row(d: Determinations, area: str) -> RowDetermination:
    return next(r for r in d.rows if r.area == area)


def t7(d: Determinations) -> Any:
    return triggers.by_id(d.pathway.triggers, "T7")


# ---- the ABC record at 2301 Chestnut St --------------------------------------------------------------------------
def test_the_abc_export_spelling_matches_the_report_address() -> None:
    """The export writes "2301 CHESTNUT ST, SAN FRANCISCO, CA 94123"; the report's address is "2301 Chestnut St"."""
    own = parse_street_address(LICENCE.address)
    report_street = parse_street_address("2301 Chestnut St")
    assert own is not None and report_street is not None and SITE.street is not None
    assert own.key == report_street.key == SITE.street.key
    assert same_street_address(own, SITE.street)
    assert same_street_address(own, report_street, allow_missing_suffix=False)
    (rec,) = on_file()
    assert _at_report_address(rec, SITE)


def test_the_active_type_47_reads_as_a_restaurant_at_2301_chestnut() -> None:
    use, lines = existing_use(on_file(), SITE, rules_date=RULES_DATE, today=RULES_DATE)
    assert use == "restaurant"
    assert [line.text for line in lines] == [EXISTING_USE_LINE]
    assert lines[0].citations == ["app:abc:636535"]
    d = report(profile(), on_file())
    assert d.pathway.existing_use == "restaurant"
    assert EXISTING_USE_LINE in [line.text for line in d.pathway.lines]
    # the record is listed in the site history
    history = build_site_history(on_file(), SITE)
    assert [e.application_id for e in history.entries] == ["abc:636535"]


def test_without_the_record_the_rules_show_no_existing_use() -> None:
    use, lines = existing_use([], SITE, rules_date=RULES_DATE, today=RULES_DATE)
    assert use is None and lines[0].rule_id == "zoning.existing_use"
    assert "No active ABC licence" in lines[0].text


@pytest.mark.skipif(
    not os.environ.get("PRECEDENT_TEST_DATABASE_URL"),
    reason="set PRECEDENT_TEST_DATABASE_URL to a PostGIS database",
)
@pytest.mark.anyio
async def test_postgis_the_store_returns_the_type_47_and_the_report_reads_it() -> None:
    """The real row through the PostGIS store: written to the test database, read back by the same query the
    runner makes for the site history (`nearby_applications` within SITE_READ_RADIUS_M of the point), tied to the
    report's address, and read by rule 4. The row is removed again afterwards; nothing else is touched."""
    from precedent.store.postgres import PostgresStore

    store = PostgresStore(os.environ["PRECEDENT_TEST_DATABASE_URL"])
    try:
        await store.ensure_schema()
        await store.upsert_applications([LICENCE])
        assert LICENCE.lat is not None and LICENCE.lng is not None
        rows = await store.nearby_applications(LICENCE.lat, LICENCE.lng, SITE_READ_RADIUS_M)
        ours: list[Nearby[Application]] = [n for n in rows if n.item.id == "abc:636535"]
        assert len(ours) == 1
        got = ours[0].item
        assert (got.status, got.license_type, got.address) == ("ACTIVE", "47", LICENCE.address)
        at_site = site_records(ours, SITE)
        assert [r.app.id for r in at_site] == ["abc:636535"]
        d = report(profile(), at_site)
        assert EXISTING_USE_LINE in [line.text for line in d.pathway.lines]
        assert d.pathway.existing_use == "restaurant"
    finally:
        async with store.pool.connection() as conn:
            await conn.execute("delete from applications where id = %s", ("abc:636535",))
        await store.close()


# ---- what T7 gives at 2301 Chestnut St, and what the report leads with ---------------------------------------------
CHANGE = facts.MISSING_PHRASES["changes_existing_business"]
MERGES = facts.MISSING_PHRASES["merges_storefronts"]
BEFORE = facts.MISSING_PHRASES["floor_area_before_sqft"]
AREA = facts.MISSING_PHRASES["floor_area_sqft"]
LAST_USE = facts.MISSING_PHRASES["existing_use_stated"]
NEW_SPACE = (
    "the space was last used as another use (not a Bar, a Restaurant, a Limited Restaurant, Nighttime "
    "Entertainment, a retail use or a laundromat), or the floor area grows, or storefronts are merged"
)


def zone(district: str) -> ZoningInfo:
    """A zoning record for a district the dated rule table carries (its controls are read from the table)."""
    return NC_2.__class__(**{**NC_2.__dict__, "district": district, "name": district})


def contingent(d: Determinations) -> list[tuple[str, str]]:
    return [(h.kind, h.condition or "") for h in d.headline_findings if not h.definite]


def test_with_the_licence_on_file_a_conditional_use_is_needed_only_if_the_business_is_enlarged() -> None:
    for answers in ({}, {"stories": ["first"]}, {"stories": ["first"], "outdoor_area": "front"}):
        d = report(profile(**answers), on_file())
        finding = t7(d)
        # T7's own outcome is unchanged: not decided, naming whether the business is enlarged
        assert finding.control == "not_decided", answers
        assert finding.missing_inputs == [CHANGE]
        assert [(c.control, c.condition) for c in finding.contingent] == [
            ("conditional", "the existing business is enlarged or storefronts are merged")
        ]
        # the report leads with it, worded with its condition, never as definite
        (h,) = d.headline_findings
        assert (h.kind, h.trigger, h.definite, h.area) == ("conditional_if", "T7", False, "zoning_use")
        assert h.sentence == ENLARGED
        assert h.missing_inputs == [CHANGE, MERGES]
        assert h.basis[0].rule_id == "T7.conditional"
        assert "6,000 square feet is at or over it" in h.basis[0].text
        # its row stays insufficient information for the missing input
        assert row(d, "zoning_use").status == h.status == "insufficient_information"
        assert d.overall_line.startswith(
            "A Conditional Use Authorization is needed if the existing business is enlarged or storefronts are "
            "merged (use size). Of the 5 approvals this concept needs:"
        )
        # and the input is still asked
        asked = [q.question for q in d.open_questions]
        assert any(CHANGE in q for q in asked)


def test_an_answer_already_given_is_not_offered_again_as_a_way() -> None:
    """Review of 2026-11-16: with "no merger" answered the headline still said "or storefronts are merged"."""
    d = report(profile(stories=["first"], merges_storefronts=False), on_file())
    assert contingent(d) == [("conditional_if", "the existing business is enlarged")]
    assert d.headline_findings[0].missing_inputs == [CHANGE]
    former = report(profile(stories=["first"], last_use="restaurant", merges_storefronts=False))
    assert contingent(former) == [("conditional_if", "the floor area grows")]
    assert former.headline_findings[0].missing_inputs == [BEFORE]


def test_with_the_licence_on_file_enlarging_makes_it_definite_and_intensifying_does_not_apply_it() -> None:
    enlarged = report(profile(stories=["first"], existing_business_change="enlarge"), on_file())
    assert t7(enlarged).control == "conditional" and t7(enlarged).contingent == []
    (h,) = enlarged.headline_findings
    assert (h.kind, h.definite, h.status) == ("conditional", True, "further_review")
    assert row(enlarged, "zoning_use").status == "further_review"
    assert enlarged.overall_line.startswith("A Conditional Use Authorization is needed (use size). ")
    for change in ("intensify", "none"):
        d = report(profile(stories=["first"], existing_business_change=change), on_file())
        assert t7(d).control == "does_not_apply", change
        assert d.headline_findings == [], change
        assert d.overall_line.startswith("Of the 5 approvals"), change


def test_with_no_licence_on_file_and_no_last_use_the_conditional_use_is_not_definite() -> None:
    """Review of 2026-11-16: with no licence and no answers the report said "Whatever the story, the concept needs
    a Conditional Use Authorization" (set by rule) and raised the overall status, while it asked what the space was
    last used as, and a former restaurant makes T7 turn on the floor area before. T7 itself is unchanged (it reads
    the use as new); the finding names the last use it rests on."""
    for answers in ({}, {"stories": ["first"]}):
        d = report(profile(**answers))
        finding = t7(d)
        assert finding.control == "conditional" and finding.missing_inputs == []  # T7 unchanged
        assert finding.unsettled_by == [LAST_USE]
        assert not [h for h in d.headline_findings if h.definite], answers
        (h,) = [h for h in d.headline_findings if h.trigger == "T7"]
        assert (h.kind, h.condition) == ("conditional_if", NEW_SPACE)
        assert h.missing_inputs == [LAST_USE, BEFORE, MERGES]
        assert h.status == row(d, "zoning_use").status
        assert "Whatever the story" not in h.sentence
        assert f"A Conditional Use Authorization is needed if {NEW_SPACE} (use size)." in d.overall_line
    # the two answers the condition names, each supplied: the rules give what it says
    other = report(profile(stories=["first"], last_use="other"))
    assert t7(other).control == "conditional" and t7(other).unsettled_by == []
    assert [(h.kind, h.definite) for h in other.headline_findings] == [("conditional", True)]
    former = report(profile(stories=["first"], last_use="restaurant"))
    assert t7(former).control == "not_decided"
    grown = report(
        profile(
            stories=["first"], last_use="restaurant", floor_area_before_sqft=3000, merges_storefronts=False
        )
    )
    assert t7(grown).control == "conditional"
    same = report(
        profile(
            stories=["first"], last_use="restaurant", floor_area_before_sqft=6000, merges_storefronts=False
        )
    )
    assert t7(same).control == "does_not_apply" and same.headline_findings == []


def test_with_no_licence_on_file_and_no_story_a_definite_conditional_use_leads_and_the_story_stays_unknown() -> (
    None
):
    d = report(profile(last_use="other"))
    assert t7(d).control == "conditional" and t7(d).unsettled_by == []
    h = d.headline_findings[0]
    assert (h.kind, h.trigger, h.definite, h.status) == ("conditional", "T7", True, "further_review")
    assert h.sentence == HEADLINE_TEXT["conditional/story"].format(trigger="use size")
    assert h.sentence.startswith("Whatever the story, the concept needs a Conditional Use Authorization")
    assert "Which stories the business occupies is not known" in h.sentence
    # Z-S is kept: no story is assumed, so the zoning row is insufficient information and names the story
    zoning = row(d, "zoning_use")
    assert zoning.status == "insufficient_information"
    assert zoning.missing_inputs[0] == facts.MISSING_PHRASES["stories"]
    assert d.open_questions[0].question.startswith(f"Not known: {facts.MISSING_PHRASES['stories']}.")
    assert d.overall_status == "further_review"
    assert d.overall_line.startswith("A Conditional Use Authorization is needed (use size). ")


def test_with_no_licence_on_file_and_a_story_the_zoning_row_is_further_review() -> None:
    d = report(profile(stories=["first"], outdoor_area="front", last_use="other"))
    (h,) = d.headline_findings
    assert (h.kind, h.definite) == ("conditional", True)
    assert h.sentence == (
        "The concept needs a Conditional Use Authorization, which the Planning Commission decides at a public "
        "hearing (Planning Code § 303). What asks for one: use size."
    )
    assert row(d, "zoning_use").status == "further_review"


def test_with_no_licence_on_file_a_former_restaurant_needs_one_only_if_the_floor_area_grows() -> None:
    d = report(profile(stories=["first"], last_use="restaurant"))
    finding = t7(d)
    assert finding.control == "not_decided"
    assert finding.missing_inputs == [BEFORE, MERGES]
    (h,) = d.headline_findings
    assert (h.kind, h.definite) == ("conditional_if", False)
    assert h.sentence.startswith(
        "If the floor area grows or storefronts are merged, the concept needs a Conditional Use Authorization"
    )
    assert h.sentence.endswith(
        "Not known: the floor area before the project; whether storefronts are to be merged."
    )


def test_a_former_restaurant_with_no_floor_area_needs_one_only_if_it_is_large_and_grows() -> None:
    """Review of 2026-11-16: with the floor area not given the headline said "If the floor area is 4,001 square feet
    or more, ... needs a Conditional Use Authorization", yet at 6,000 square feet with the same floor area before
    and no merger T7 does not apply (Interpretation 121.2). The condition now names both."""
    d = report(profile(stories=["first"], last_use="restaurant", floor_area_sqft=None))
    assert t7(d).control == "not_decided" and t7(d).missing_inputs == [AREA]
    (h,) = d.headline_findings
    assert (h.kind, h.condition) == (
        "conditional_if",
        "the floor area is 4,001 square feet or more and either the floor area grows or storefronts are merged",
    )
    assert h.missing_inputs == [AREA, BEFORE, MERGES]


@pytest.mark.parametrize(
    ("district", "expected", "checks"),
    [
        # Chinatown Visitor Retail: no use size Conditional Use for a Restaurant over 2,500 square feet (Table
        # 811 Note 1), not permitted from 5,001: no Conditional Use is ever needed for size, only the bar
        ("CVR", [("not_permitted_if", "the floor area is 5,001 square feet or more")],
         {2600: "principal", 5000: "principal", 5001: "not_permitted", 9000: "not_permitted"}),
        # Chinatown Residential Neighborhood Commercial: a Conditional Use from 2,501, not permitted from 4,001
        ("CRNC", [("conditional_if", "the floor area is from 2,501 to 4,000 square feet"),
                  ("not_permitted_if", "the floor area is 4,001 square feet or more")],
         {2500: "principal", 2501: "conditional", 4000: "conditional", 4001: "not_permitted"}),
        # Chinatown Community Business: a Conditional Use from 2,501, not permitted from 5,001
        ("CCB", [("conditional_if", "the floor area is from 2,501 to 5,000 square feet"),
                 ("not_permitted_if", "the floor area is 5,001 square feet or more")],
         {2501: "conditional", 5000: "conditional", 5001: "not_permitted"}),
    ],
)  # fmt: skip
def test_with_no_floor_area_the_condition_follows_the_restaurant_note_and_the_cap(
    district: str, expected: list[tuple[str, str]], checks: dict[int, str]
) -> None:
    """Review of 2026-11-16: with the floor area not given the headline said "If the floor area is 2,501 square
    feet or more, ... needs a Conditional Use Authorization" in CVR, CRNC and CCB, ignoring the Restaurant note
    and the cap above which the use is not permitted."""
    d = determine(
        p := profile(stories=["first"], floor_area_sqft=None), zone(district), [], [], SITE,
        required_areas(p), today=RULES_DATE,
    )  # fmt: skip
    assert t7(d).control == "not_decided" and t7(d).missing_inputs == [AREA]
    assert [(h.kind, h.condition) for h in d.headline_findings if h.trigger == "T7"] == expected
    # the rules themselves, once the floor area is given
    for area, control in checks.items():
        p = profile(stories=["first"], floor_area_sqft=area)
        got = determine(p, zone(district), [], [], SITE, required_areas(p), today=RULES_DATE)
        assert t7(got).control == control, (district, area)


def test_each_contingent_condition_is_what_the_rules_give_once_answered() -> None:
    """An independent check of every contingent condition above: answers that meet the condition are supplied
    through the intake answers, as the applicant would give them, with every other input T7 then asks for (a
    condition says what the rules give once they can decide: "the floor area grows" holds whatever the merger
    answer, but T7 still asks it), and T7 must then give the control the condition names; answers that do not
    meet it must not."""
    cases: list[tuple[str, dict[str, Any], bool, dict[str, Any], str]] = [
        # (district, answers, licence on file, answers that meet the condition, control)
        ("NC-2", {"stories": ["first"]}, True, {"existing_business_change": "enlarge"}, "conditional"),
        ("NC-2", {"stories": ["first"]}, True, {"existing_business_change": "enlarge_and_intensify"}, "conditional"),
        ("NC-2", {"stories": ["first"]}, True, {"existing_business_change": "none", "merges_storefronts": True}, "conditional"),
        ("NC-2", {"stories": ["first"]}, True, {"existing_business_change": "intensify", "merges_storefronts": False}, "does_not_apply"),
        ("CRNC", {"stories": ["first"]}, True, {"existing_business_change": "enlarge"}, "not_permitted"),
        ("CRNC", {"stories": ["first"]}, True, {"existing_business_change": "none", "merges_storefronts": True}, "not_permitted"),
        ("NC-2", {"stories": ["first"]}, False, {"last_use": "other"}, "conditional"),
        ("NC-2", {"stories": ["first"]}, False, {"last_use": "bar", "floor_area_before_sqft": 5000, "merges_storefronts": False}, "conditional"),
        ("NC-2", {"stories": ["first"]}, False, {"last_use": "retail", "merges_storefronts": True}, "conditional"),
        ("NC-2", {"stories": ["first"]}, False, {"last_use": "laundromat", "floor_area_before_sqft": 6000, "merges_storefronts": False}, "does_not_apply"),
        ("NC-2", {"stories": ["first"], "last_use": "restaurant", "floor_area_sqft": None}, False,
         {"floor_area_sqft": 4001, "floor_area_before_sqft": 4000, "merges_storefronts": False}, "conditional"),
        ("NC-2", {"stories": ["first"], "last_use": "restaurant", "floor_area_sqft": None}, False,
         {"floor_area_sqft": 12000, "merges_storefronts": True}, "conditional"),
        ("NC-2", {"stories": ["first"], "last_use": "restaurant", "floor_area_sqft": None}, False,
         {"floor_area_sqft": 4000, "floor_area_before_sqft": 3000}, "principal"),
    ]  # fmt: skip
    for district, answers, licence, supplied, control in cases:
        p = profile(**{**answers, **supplied})
        d = determine(
            p, zone(district), [], on_file() if licence else [], SITE, required_areas(p), today=RULES_DATE
        )
        assert t7(d).control == control, (district, answers, supplied)
    # 995 Valencia St with its Type 41 on file (the web's sample): "If the floor area is 3,001 square feet or more
    # and either the floor area grows or storefronts are merged"
    from tests.test_pathway import TYPE_41_AT_995, WINE_BAR, run

    d = run(WINE_BAR, records=[TYPE_41_AT_995])
    assert [(c.control, c.condition) for c in t7(d).contingent] == [
        (
            "conditional",
            "the floor area is 3,001 square feet or more and either the floor area grows or storefronts are merged",
        )
    ]
    for update, control in (
        ({"square_feet": 4000, "floor_area_before_sqft": 3000, "merges_storefronts": False}, "conditional"),
        ({"square_feet": 4000, "merges_storefronts": True}, "conditional"),
        (
            {"square_feet": 4000, "floor_area_before_sqft": 4000, "merges_storefronts": False},
            "does_not_apply",
        ),
        ({"square_feet": 4000}, "not_decided"),  # the floor area alone does not settle it
        ({"square_feet": 3000, "merges_storefronts": True}, "principal"),
    ):
        got = run(WINE_BAR.model_copy(update=update), records=[TYPE_41_AT_995])
        assert t7(got).control == control, update


def test_a_definite_conditional_use_raises_the_overall_status_when_no_row_is_further_review() -> None:
    """A Restaurant with no alcohol, its patio in front and storefronts merged, no story given: no row is further
    review (the zoning row is insufficient information for the story). Before 2026-11-16 the overall status was the
    most severe row's, insufficient information, and the Conditional Use for its size was buried in the zoning
    row's last line."""
    dry = profile(liquor_licence="none", alcohol_served=None, outdoor_area="front", merges_storefronts=True)
    d = report(dry)
    assert "further_review" not in {r.status for r in d.rows}
    assert row(d, "zoning_use").status == "insufficient_information"
    assert d.overall_status == "further_review"
    assert [h.trigger for h in d.headline_findings if h.definite] == ["T7"]


def test_a_contingent_finding_never_raises_the_overall_status() -> None:
    """CRNC with the licence on file, first story: T7 would bar the use if the business is enlarged. The finding
    is not_permitted_if; were it read into rule 8 the overall status would be not permitted."""
    p = profile(stories=["first"])
    d = determine(p, zone("CRNC"), [], on_file(), SITE, required_areas(p), today=RULES_DATE)
    t7_findings = [h for h in d.headline_findings if h.trigger == "T7"]
    assert [(h.kind, h.condition) for h in t7_findings] == [
        ("not_permitted_if", "the existing business is enlarged or storefronts are merged")
    ]
    assert t7_findings[0].sentence == (
        "If the existing business is enlarged or storefronts are merged, zoning does not permit the concept as "
        "described at this address. What would bar it: use size. Not known: whether an existing business is to be "
        "enlarged or intensified; whether storefronts are to be merged."
    )
    assert "Zoning does not permit the concept if the existing business is enlarged" in d.overall_line
    assert "not_permitted" not in {r.status for r in d.rows}
    definite = [h.status for h in d.headline_findings if h.definite]
    assert d.overall_status == most_severe([*(r.status for r in d.rows), *definite])
    assert d.overall_status != "not_permitted"


def test_a_trigger_that_bars_the_concept_leads_alone() -> None:
    """A Bar where the district's table does not permit one: the not permitted finding leads, and no Conditional
    Use is listed (no answer changes that)."""
    from tests.test_pathway import zoning as zoning_row

    bar = BusinessProfile(
        business_type="bar", serves_alcohol=True, alcohol_type="full_liquor", stories=["first"]
    )
    d = determine(
        bar,
        zoning_row("NCD-PACIFIC", bar="prohibited", name="Pacific Avenue NCD"),
        [],
        [],
        SITE,
        required_areas(bar),
        today=RULES_DATE,
    )
    assert d.headline_findings and {h.kind for h in d.headline_findings} == {"not_permitted"}
    assert all(h.status == "not_permitted" and h.definite for h in d.headline_findings)
    assert d.overall_status == "not_permitted"
    assert d.overall_line.startswith("Zoning does not permit the concept as described here (")


# ---- other triggers: formula retail (T5) and the story (T1) ------------------------------------------------------
FR_CHAIN = "the business is part of a chain with eleven or more other locations"
FR_COUNT = "the business has eleven or more other locations"


def test_a_formula_retail_conditional_use_that_turns_on_the_chain_leads() -> None:
    """Review of 2026-11-16: in NC-2 a Restaurant with the chain question skipped, or answered yes without the
    count, had T5 not decided while NC-2 makes formula retail a conditional use, yet nothing led the report."""
    base = BusinessProfile(business_type="restaurant", stories=["first"], square_feet=1500)

    def chestnut(**answers: Any) -> Determinations:
        p = apply_intake_answers(base, IntakeAnswers.model_validate({"liquor_licence": "none", **answers}))
        p = p.normalized()
        return determine(p, NC_2, [], [], SITE, required_areas(p), today=RULES_DATE)

    silent, counted = chestnut(), chestnut(part_of_chain=True)
    for d, condition, missing in (
        (silent, FR_CHAIN, facts.MISSING_PHRASES["formula_retail"]),
        (counted, FR_COUNT, facts.MISSING_PHRASES["other_locations"]),
    ):
        t5 = triggers.by_id(d.pathway.triggers, "T5")
        assert t5.control == "not_decided" and t5.missing_inputs == [missing]
        (h,) = d.headline_findings
        assert (h.kind, h.trigger, h.condition, h.definite) == ("conditional_if", "T5", condition, False)
        assert h.missing_inputs == [missing]
        assert h.sentence.startswith(f"If {condition}, the concept needs a Conditional Use Authorization")
        assert h.status == row(d, "zoning_use").status == "insufficient_information"
        assert d.overall_line.startswith(
            f"A Conditional Use Authorization is needed if {condition} (formula retail). Of the 3 approvals"
        )
    # the rules, answered: eleven other locations asks for one, ten does not
    eleven = chestnut(part_of_chain=True, other_locations=11)
    assert triggers.by_id(eleven.pathway.triggers, "T5").control == "conditional"
    assert [(h.kind, h.definite) for h in eleven.headline_findings] == [("conditional", True)]
    ten = chestnut(part_of_chain=True, other_locations=10)
    assert triggers.by_id(ten.pathway.triggers, "T5").control == "principal" and ten.headline_findings == []


def test_a_use_control_that_turns_on_the_story_leads_with_the_story() -> None:
    """T1 with no story given: NC-2 does not permit a Restaurant on the third story or above. The finding names
    the story; the zoning row stays insufficient information (the user's decision of 2026-11-12)."""
    d = report(profile(last_use="other"))
    t1 = triggers.by_id(d.pathway.triggers, "T1")
    assert t1.control == "not_decided" and t1.missing_inputs == [facts.MISSING_PHRASES["stories"]]
    assert [(c.control, c.condition) for c in t1.contingent] == [
        ("not_permitted", "the business occupies the third story or above")
    ]
    assert ("not_permitted_if", "the business occupies the third story or above") in contingent(d)
    assert row(d, "zoning_use").status == "insufficient_information"
    for stories, control in (
        (["third_or_above"], "not_permitted"),
        (["first", "third_or_above"], "not_permitted"),
    ):
        got = report(profile(last_use="other", stories=stories))
        assert triggers.by_id(got.pathway.triggers, "T1").control == control, stories
    first = report(profile(last_use="other", stories=["first"]))
    assert triggers.by_id(first.pathway.triggers, "T1").control != "not_permitted"


def test_a_reading_that_is_the_same_on_every_story_is_not_worded_as_turning_on_it() -> None:
    from tests.test_pathway import WINE_BAR_NO_STORY, run

    d = run(WINE_BAR_NO_STORY)
    t1 = triggers.by_id(d.pathway.triggers, "T1")
    for c in t1.contingent:
        assert "first story, the second story, the third story or above or the basement" not in c.condition
    assert [(c.control, c.condition) for c in t1.contingent] == [
        ("conditional", "the business occupies no story other than the first story or the basement"),
        ("not_permitted", "the business occupies the second story or the third story or above"),
    ]


def test_the_overall_lead_names_definite_findings_together_and_each_contingent_one_alone() -> None:
    d = report(profile(stories=["first"]), on_file())
    assert overall_lead(d.headline_findings) == [
        "A Conditional Use Authorization is needed if the existing business is enlarged or storefronts are merged "
        "(use size)."
    ]
    assert overall_lead([]) == []


def test_no_headline_without_a_zoning_row() -> None:
    p = profile(stories=["first"])
    d = determine(p, NC_2, [], [], SITE, ["health"], today=RULES_DATE)
    assert d.headline_findings == [] and d.overall_line.startswith("Of the 1 approval")


def test_the_same_inputs_give_the_same_headline_in_any_order() -> None:
    """Two records at the address (the active Type 47 and a surrendered Type 41 before it), in either order."""
    old = LICENCE.model_copy(
        update={
            "id": "abc:500001",
            "source_id": "500001",
            "license_type": "41",
            "permit_type": "Type 41 – On-Sale Beer & Wine - Eating Place",
            "status": "SURRENDERED",
        }
    )
    matched = site_match(old, 0.0, SITE)
    assert matched is not None
    records = [*on_file(), SiteRecord(old, 0.0, matched)]
    a = report(profile(), records)
    b = report(profile(), list(reversed(records)))
    assert a.headline_findings and a.pathway.existing_use == "restaurant"
    assert [h.model_dump() for h in a.headline_findings] == [h.model_dump() for h in b.headline_findings]
    assert a.overall_line == b.overall_line and a.model_dump() == b.model_dump()


def test_the_headline_is_dated_by_the_rules_date() -> None:
    """The rules date reads the controls; a later today does not change what leads."""
    p = profile(last_use="other")
    d = determine(
        p,
        NC_2,
        [],
        [],
        SITE,
        required_areas(p),
        today=RULES_DATE + dt.timedelta(days=1),
        rules_date=RULES_DATE,
    )
    assert [h.trigger for h in d.headline_findings if h.definite] == ["T7"]
