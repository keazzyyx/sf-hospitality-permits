"""The rows that are not the zoning triggers (rule table v2): the alcohol licence row, the three change-of-use
answers, the building row, the entertainment row, and the referral steps inside each approval.

Spec: docs/validation/rule-table-extension-spec.md, sections 3a (referral steps are not approvals) and 4 (how a
row's status is set). Pure code: no model call, no clock (the rules date is passed in), no randomness, no I/O
beyond the bundled data files that `app.memo.controls` and `app.memo.tracts` read. The same inputs in any order
give the same output.

The zoning triggers are evaluated elsewhere and come in as `TriggerFinding` objects. This module reads only
their `family`, `control`, `missing_inputs` and `lines`; it imports nothing from the module that makes them.

THE RULES (binding; every sentence is built from the fields of the facts, records or data entries the rule
read, plus the fixed text in `ROW_BASIS` below and in `pathway.LEGAL_BASIS`)

1. `alcohol_row`: the ABC licence. The first rule that applies sets the status.
   A1   `zoning_prohibits_use` and the existing use does not continue -> not_permitted (Business and
        Professions Code § 23790). "Continues" is `existing_use_continues`: the planning-use answer of rule 2
        is "no", or the description says an existing business stays (`changes_existing_business` is stated).
        A caller whose `zoning_prohibits_use` is already about a new use only passes `prohibited_use_is_new`,
        and the row is then not_permitted whatever this module's own test says (a business that stays while a
        different, prohibited use is proposed).
   A1r  a licence finding of a restricted district (family "licence_in_restricted_district", T4) is
        not_permitted -> not_permitted (§ 23790). T4 decides for itself whether the establishment is new.
   A1z  the zoning row is not permitted for the concept as described (`zoning_barred_by`: every finding that
        bars it, any of T3 to T11) and the existing use does not continue -> not_permitted (§ 23790: the
        licence cannot issue where using it would be contrary to zoning). Where one of those findings is a
        prohibited use (`pathway.PROHIBITED_USE_TRIGGERS`: T1, T2, T5 formula retail), A1z applies whether or
        not an existing use continues (the user's decision of 2026-11-12: "a prohibited use, including the
        formula-retail prohibition, means no later approvals apply"). The sentence names the triggers that bar
        it. A1, A1r and A1z print the tract's numbers only, never "the licence may still issue".
   Where alcohol served outdoors is the applicant's only alcohol answer and the description did not say alcohol
   is served (`ConceptFacts.outdoor_alcohol_answer_over_description`), every status below is read on the answer
   and the row's first line says the two disagree ("alcohol.outdoor_answer").
   A0   the licence type or how the licence is to be obtained is missing -> insufficient_information, with
        `missing_inputs` naming each with the fixed phrase of `app.memo.facts`. A licence type the facts
        derived from the kind of business and what it pours counts as given; a line says it was derived. A
        concept that serves alcohol without saying what (alcohol_type "unknown") has no licence type, and the row
        names "what alcohol will be served: beer and wine, or spirits too" in its place
        (`ConceptFacts.missing_names`); it is never read as beer and wine nor as no alcohol.
   A0r a T4 finding is not_decided -> insufficient_information, naming what T4 names.
        (A0 and A0r come before A2, as the spec orders them: a missing input gives insufficient_information
        even where a requirement of A2 is known. The lines T4 found, the requirement among them, are still
        printed on the row.)
   A2   a T4 finding carries a requirement on the licence itself that could stop it (BLOCKING_REQUIREMENTS:
        inside the Mission Alcoholic Beverage Special Use District a new Bar must use a licence transferred
        from a Bar inside the district) -> potential_blocker. T4 prints a requirement of the dated data as a
        line whose rule_id ends with the data's own rule_id ("T4:<rule_id>"), and only when it reaches the
        concept on the rules date; that line is the requirement line of this row.
   Ah   the licence is already held (`alcohol_transaction` "licence_already_held") and no T4 finding is
        conditional -> allowed: nothing is filed with ABC unless the type, the premises or the operation changes
        (the entitlement path lists nothing for it).
   A2c  a T4 finding is conditional -> further_review.
   A3   otherwise -> further_review (investigation, notice, referral).
   Census tract (`app.memo.tracts`): when the tract is over its authorised number for the licence's kind and
   the licence is new or transferred from other premises (§ 23958.4(a)), the two tract lines are printed and a
   further_review row carries the status note "public convenience or necessity finding likely required". This
   fact alone never gives potential_blocker or not_permitted, and never changes a status: on a row that is
   already a potential blocker or not permitted the lines are printed and the status stays. A transfer from
   another person, a licence already held, a licence type that is not counted, a tract that is not over, a
   tract with no figures and an unknown tract print nothing. On an insufficient_information row the lines
   are printed and no qualifier is set; when it is the transaction that is missing (rule A0), the numbers are
   printed with a line saying which transactions state law tests. The qualifier is not set, and a line says
   why, when the figures are later than the rules date (the tract's standing then is not established), and when
   an active licence of the same type is on file at the address (§ 23958.4(f): the test does not apply to
   premises licensed and operated with that type within 90 days, which the rules cannot tell).
   v1's county-limit line for Types 47 and 48 is kept on every row except A1 and A1r, and is left out when
   the description says the licence is already held (nothing is transferred).
   Referral steps (rule 4) are listed on every row except a not_permitted one and a licence already held
   (nothing is applied for). The steps of a public convenience or necessity determination by the Board of
   Supervisors are added when the qualifier is set and the licence is a public-premises type (§ 23958.4(b)(2);
   for an eating-place licence the applicant makes the showing to ABC). For a type the rules cannot place in
   either limb a line says so and no such steps are added.

2. `change_answers`: change of use is three separate answers, each with its own lines.
   planning_use (Planning Code § 102): the last use of the space against the proposed use or uses. The last
     use is the one the licence records show (`SiteFacts.existing_use`); when they show none, the use the
     description states, and the line then says "as described" (or "as you answered", when the last use is the
     applicant's intake answer: `ConceptFacts.by_answer`). A description that agrees with the records and
     names more uses adds to what they show; one that disagrees with them is not read. "no" when every
     proposed use is among the last uses; "yes" when a proposed use is not (Limited Restaurant to Restaurant
     is a change of use, and so is adding a use); "not_established" when neither source gives a last use
     ("vacant" alone gives none) or the concept has no use the rules read. Rule table v1's rule is kept for
     that last case only: where the engine passes `described_change` (the profile says new construction, or
     that the space was not a food or drink use), the answer is "yes", as described by the applicant.
   building_occupancy (the data's citywide "change_of_occupancy" rule): the proposed group is Group B when
     the description says the space is for fewer than 50 people and Assembly Group A-2 when it says 50 or
     more (a line that reads the applicant's intake answer says "You answered"). A count of seats is not the
     occupant load: 50 or more seats is read as A-2, fewer than 50 seats is not enough to tell. "Fewer than 50
     people" with 50 seats or more is a conflict: the proposed group is not established, the same use is not read
     as unchanged either, and the row names whether the space is for fewer than 50 people (neither is read over
     the other; the report's open question names the conflict, `occupants_conflict_seats`). The existing group is
     not in public records; `existing_occupancy_group` carries it
     when an input states it. Both groups shown: "yes" when they differ, "no" when they are the same. Else
     "no" when the same use continues (planning_use "no"), the description states that the business does not
     change (`changes_existing_business` "none": silence is never read as no change), the two floor areas are
     equal when both are given, and the proposed group is not shown to be the assembly group. Where the same
     use continues and the change is missing, "not_established" names it with the existing group. Otherwise
     "not_established". Never "yes" without both groups shown.
   neighbourhood_notice (the data's citywide "neighbourhood_notification" rule, as in force on the rules
     date):
       from 2024-01-14 a change of use does not by itself trigger Planning Code § 311 notice in any district
         -> not_required, whether or not the use changes (the answer does not turn on it);
       before that: the use does not change -> not_required; the change is not established ->
         not_established; a district outside the section's list (C-2, C-3) -> not_required; a Restaurant
         becoming a Limited Restaurant -> not_required; in an NC or NCT district a change to a principally
         permitted use -> not_required (the exemption adopted in 2020), to a use that is conditional or not
         permitted -> required; in a Residential district a use that is conditional or not permitted ->
         required; everything the rules cannot place (the district's class, whether the new use is
         principally permitted, a limited commercial use in a Residential district, a land use category in
         an Eastern Neighborhoods Mixed Use district) -> not_established.
     "Principally permitted" is read from the findings of the use-control families (USE_CONTROL_FAMILIES).
     Formula Retail: where the version's quoted text names "establishment of a Formula Retail Use" (the
     versions before 2024-01-14), in a district class it lists, a chain that does not continue at the address
     -> required, without a change of use; whether it is a chain, when not stated, makes any answer short of
     required "not_established". Its line names what is not known as T5 does: whether the business is part of a
     chain ("formula_retail_missing"), or, where the applicant says it is but gave no count, how many other
     locations it has, since Planning Code § 303.1 counts formula retail from eleven other locations
     ("formula_retail_count_missing", in T5's words; "..._answered", "You answered ...", where the intake answer
     gave the chain; change of 2026-11-16).

3. `building_row`:
   B0  `zoning_prohibits_use` and planning_use is not "no" -> not_permitted (Planning Code § 175(a)). Before
       the decision of 2026-11-12 this needed planning_use "yes"; a prohibited use whose change is not
       established is now barred too (the use triggers never read a use that continues).
   B0z otherwise, the zoning row is not permitted by a prohibited use (`zoning_barred_by`: the findings among
       `pathway.PROHIBITED_USE_TRIGGERS` that bar it, in practice formula retail) -> not_permitted (Planning
       Code § 175(a)); the sentence names what bars it. Hours, use size, the outdoor area and the other
       triggers do not reach this row.
       For B0 and B0z the approval is the change-of-use permit when the use changes, the plain one otherwise.
   B1  planning_use or building_occupancy is "yes"     -> further_review.
   B2  both are "no"                                   -> allowed.
   B3  otherwise -> insufficient_information, naming what is missing: what the space was last used as; whether
       the space is for fewer than 50 people; whether an existing business is to be enlarged or intensified
       (the same use continues); the existing occupancy group, which only plans or an inspection show. The
       sentence names only the question that is open (change of use, change of occupancy, or both).

4. `referral_steps`: the steps inside an approval where one agency sends the application to another, on the
   rules date, from the data's citywide "entertainment_permits" and "other_referrals" lists (entries whose
   kind is "referral_step"). One line per agency: a step in force names the agency and the section, and the
   date and ordinance when its present form began after 2022; a step that has ended says until when and by
   which ordinance. A step that was replaced by a later version of itself is not listed as ended. A referral
   step never sets or changes a status. An approval that ended (the dance hall permit) is not a referral step
   and is never listed here; the steps of a permit that is no longer an approval on the rules date are not
   listed either. Missing referral data gives an empty list. A row that is not_permitted lists no steps.

5. `entertainment_row`: v1's E0 to E3, on the facts:
   E0  `zoning_prohibits_use`                           -> not_permitted (Planning Code § 175(a))
   E0z otherwise, the zoning row is not permitted by a prohibited use (`zoning_barred_by`, in practice
       formula retail)                                  -> not_permitted (Planning Code § 175(a)), naming it
   E1  otherwise, not closing after 2 a.m.              -> further_review
   E2  closing after 2 a.m., no entertainment           -> further_review (Extended-Hours Premises permit)
   E3  entertainment and closing after 2 a.m.           -> further_review (both permits)
   The approval is named for the permit the description points to where `entertainment_kind` is stated
   (Limited Live Performance, Place of Entertainment), with the Extended-Hours Premises permit when the concept
   closes after 2 a.m.; the general name otherwise. `referral_steps` are those of rule 4 for the permits named.
   A closing time that is missing is never read as "by 2 a.m.": a line says the Extended-Hours Premises permit
   would be needed for those hours. While the dance permit is an approval on the rules date (the data's
   "dance_hall" entry, to 2025-08-16), E1 and E3 do not say that dancing needs no permit; a concept with dancing
   gets a line about the dance permit, and the approval names it unless a Place of Entertainment permit is
   named.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, get_args

from precedent.store.base import ZoningInfo

from app.memo import controls, tracts
from app.memo.facts import MISSING_PHRASES, ConceptFacts, SiteFacts
from app.memo.pathway import (
    AGENCIES,
    APPROVALS,
    BUILDING_PERMIT_SECTION,
    COUNTY_LIMITED_TYPES,
    LEGAL_BASIS,
    LICENCE_TYPES,
    PROHIBITED_USE_TRIGGERS,
    Basis,
    _a,
    _merge,
    _status_words,
)
from app.models.memo import (
    PLANNING_USE_LABELS,
    ApprovalArea,
    ApprovalStatus,
    ChangeAnswers,
    ChangeOfUse,
    NoticeAnswer,
    PlanningUse,
    RowDetermination,
    RuleLine,
    TriggerFamily,
    TriggerFinding,
)
from app.models.profile import ExistingUse

# ---- the fixed text and the code references (for legal review) ---------------------------------------
_LICENCE_INVESTIGATION = LEGAL_BASIS["alcohol.status/A3"].code_section
_ZONING_AND_LICENCE = LEGAL_BASIS["alcohol.status/A1"].code_section  # B&P § 23790
_BUILDING_PERMIT = BUILDING_PERMIT_SECTION
_NOTICE_SECTION = "Planning Code § 311"
_EXTENDED_HOURS = LEGAL_BASIS["entertainment.status/E2"].code_section

# Key = "<rule_id>" or "<rule_id>/<variant>". The part before the slash is the RuleLine.rule_id. A sentence
# with no code_section takes its section from the data entry or the record it read, or states no law.
ROW_BASIS: dict[str, Basis] = {
    # ---- alcohol: what the facts give
    "alcohol.licence/stated": Basis(
        "The licence looked up is ABC Type {type}{label}, as stated in the description."
    ),
    "alcohol.licence/derived": Basis(
        "The description does not state a licence type. The rules derived ABC Type {type}{label} from the kind "
        "of business and what it pours."
    ),
    "alcohol.licence/derived_answered": Basis(
        "The description does not state a licence type. The rules derived ABC Type {type}{label} from the kind "
        "of business and what you answered it pours."
    ),
    # an answer that alcohol is served outdoors, where the description did not say alcohol is served (it may say
    # none is): the answer is read, the safe reading, since the licence is then checked
    "alcohol.outdoor_answer": Basis(
        "You answered that alcohol will be served in the outdoor area, but the description does not say that "
        "alcohol is served, or says that it is not. The two disagree; the report reads your answer, so the "
        "business is read as serving alcohol and this licence is checked."
    ),
    "alcohol.transaction/new_licence": Basis(
        "The licence is to be obtained as a new licence, as the applicant states."
    ),
    "alcohol.transaction/person_to_person_transfer": Basis(
        "The licence is to be obtained by transfer from another licence holder (a person-to-person transfer), "
        "as the applicant states."
    ),
    "alcohol.transaction/premises_transfer": Basis(
        "The licence is to be obtained by transfer from other premises (a premises-to-premises transfer), as "
        "the applicant states."
    ),
    "alcohol.transaction/licence_already_held": Basis(
        "The business already holds the licence, as the applicant states."
    ),
    # ---- alcohol: statuses (A1, A2 and A3 are v1's sentences in pathway.LEGAL_BASIS)
    "alcohol.status/A1r": Basis(
        "The liquor licence rule of the restricted district does not permit this licence here, and ABC may not "
        "issue a retail licence where using the licence would be contrary to zoning: {status}.",
        _ZONING_AND_LICENCE,
    ),
    "alcohol.status/A1z": Basis(
        "Zoning does not permit the concept as described at this address ({triggers}), and ABC may not issue a "
        "retail licence where using the licence would be contrary to zoning: {status}.",
        _ZONING_AND_LICENCE,
    ),
    "alcohol.status/held": Basis(
        "The business already holds the licence for these premises, so nothing is filed with ABC unless the "
        "licence type, the premises or the operation changes: {status}."
    ),
    "alcohol.status/A0": Basis(
        "The description does not give {missing}, so the rules cannot say which licence rules apply: {status}."
    ),
    "alcohol.status/A0r": Basis(
        "The liquor licence rule of the restricted district cannot be decided without {missing}: {status}."
    ),
    "alcohol.status/A2c": Basis(
        "The liquor licence rule of the restricted district makes this licence a conditional use here, so it "
        "can be used only with a Conditional Use Authorization. ABC also investigates the application, and the "
        "applicant must post public notice: {status}.",
        f"Planning Code § 303; {_LICENCE_INVESTIGATION}",
    ),
    # ---- alcohol: census tract. The numbers line and the status note are app.memo.tracts' own fixed words.
    "alcohol.tract_concentration/tested": Basis(
        "The tract is over its authorised number, and state law tests {transaction} for undue concentration. "
        "The licence may still issue if public convenience or necessity would be served: {note}.",
        tracts.PCN_CITATION,
        tracts.PCN_SOURCE_URL,
    ),
    "alcohol.tract_concentration/later": Basis(
        "These figures are later than the rules date ({date}); the tract's standing on that date is not "
        "established.",
        tracts.PCN_CITATION,
        tracts.PCN_SOURCE_URL,
    ),
    "alcohol.tract_concentration/same_type": Basis(
        "The undue concentration test does not apply if the premises held a licence of the same type and "
        "operated under it within 90 days of the application. An active ABC Type {type} licence is on file at "
        "this address, but the rules cannot tell whether it was operated within that time.",
        "California Business and Professions Code § 23958.4(f)",
        tracts.PCN_SOURCE_URL,
    ),
    "alcohol.tract_concentration/limb_unknown": Basis(
        "The rules cannot tell which limb of § 23958.4(b) reaches ABC Type {type}: whether the applicant shows "
        "public convenience or necessity to ABC, or the local governing body determines it.",
        tracts.PCN_CITATION,
        tracts.PCN_SOURCE_URL,
    ),
    "alcohol.tract_concentration/transaction_missing": Basis(
        "The tract is over its authorised number. State law tests a new licence and a transfer from other "
        "premises for undue concentration, and the applicant does not say how the liquor licence will be "
        "obtained.",
        tracts.PCN_CITATION,
        tracts.PCN_SOURCE_URL,
    ),
    # ---- change of use 1: Planning Code use (the records' own sentences are v1's "zoning.change_of_use")
    "change.planning_use/described_no": Basis(
        "The last use of the space, as described, is {existing}. The proposed use is {uses}, so this is not a "
        "change of use.",
        "Planning Code § 102",
    ),
    "change.planning_use/described_yes": Basis(
        "{existing} to {uses} is a change of use, with the last use of the space as described.",
        "Planning Code § 102",
    ),
    # the same two, where the last use is the applicant's answer to an intake question
    "change.planning_use/answered_no": Basis(
        "The last use of the space, as you answered, is {existing}. The proposed use is {uses}, so this is not a "
        "change of use.",
        "Planning Code § 102",
    ),
    "change.planning_use/answered_yes": Basis(
        "{existing} to {uses} is a change of use, with the last use of the space as you answered.",
        "Planning Code § 102",
    ),
    "change.planning_use/vacant": Basis(
        "The description says the space is vacant and does not say what it was last used as, so whether the "
        "proposed use ({uses}) is a change of use is not established."
    ),
    "change.planning_use/not_established": Basis(
        "The records do not show what the space is used as, and the description does not say what it was last "
        "used as, so whether the proposed use ({uses}) is a change of use is not established."
    ),
    "change.planning_use/no_use": Basis(
        "The rules have no Planning Code use for the concept, so it was not compared with the last use of the "
        "space and a change of use is not established."
    ),
    # ---- change of use 2: Building Code occupancy ({assembly}, {limit} and {edition} are the data's facts)
    "change.occupancy/rule": Basis(
        "Building Code: a restaurant or bar is Assembly Group {assembly}, and a space for fewer than {limit} "
        "people is Group B ({edition} California Building Code)."
    ),
    "change.occupancy/no_rule": Basis(
        "No version of the Building Code occupancy rule is on file for {date}, so the proposed occupancy group "
        "is not established."
    ),
    "change.occupancy/proposed_under": Basis(
        "The description says the space is for fewer than {limit} people, so the proposed occupancy is Group B."
    ),
    "change.occupancy/proposed_over": Basis(
        "The description says the space is for {limit} people or more, so the proposed occupancy is Group "
        "{assembly}."
    ),
    # the same two, where it is the applicant's answer to an intake question
    "change.occupancy/answered_under": Basis(
        "You answered that the space is for fewer than {limit} people, so the proposed occupancy is Group B."
    ),
    "change.occupancy/answered_over": Basis(
        "You answered that the space is for {limit} people or more, so the proposed occupancy is Group "
        "{assembly}."
    ),
    # "fewer than 50 people" against a seat count of 50 or more: neither is read over the other
    "change.occupancy/under_but_seats_answered": Basis(
        "You answered that the space is for fewer than {limit} people, but the description gives {seats} seats, "
        "which means at least {limit} people. The two disagree, so the proposed occupancy group is not "
        "established."
    ),
    "change.occupancy/under_but_seats_described": Basis(
        "The description says the space is for fewer than {limit} people, but it also gives {seats} seats, "
        "which means at least {limit} people. The two disagree, so the proposed occupancy group is not "
        "established."
    ),
    "change.occupancy/proposed_seats_over": Basis(
        "The description gives {seats} seats. A count of seats is not the occupant load, which is worked out "
        "from the floor plan, but {seats} seats means at least {limit} people, so the proposed occupancy is "
        "Group {assembly}."
    ),
    "change.occupancy/proposed_seats_under": Basis(
        "The description gives {seats} seats. A count of seats is not the occupant load, which is worked out "
        "from the floor plan and can be higher, so fewer than {limit} seats does not show whether the proposed "
        "occupancy is Group B or Group {assembly}."
    ),
    "change.occupancy/proposed_missing": Basis(
        "The description does not give {missing}, so the proposed occupancy group is not established."
    ),
    "change.occupancy/proposed_no_use": Basis(
        "The rules have no Planning Code use for the concept, so the proposed occupancy group is not established."
    ),
    "change.occupancy/same_use": Basis(
        "The same use continues and the description states no enlargement or other change to the business, so "
        "the rules read the occupancy group as unchanged: not a change of occupancy. The existing group itself "
        "is not in public records; plans or an inspection show it."
    ),
    "change.occupancy/same_use_answered": Basis(
        "The same use continues and you answered that the business stays as it is, with no enlargement or other "
        "change, so the rules read the occupancy group as unchanged: not a change of occupancy. The existing "
        "group itself is not in public records; plans or an inspection show it."
    ),
    "change.occupancy/change_missing": Basis(
        "The same use continues, but the description does not say whether the business is to be enlarged or "
        "otherwise changed, and the existing occupancy group of the space is not in public records. A change of "
        "occupancy is not established."
    ),
    "change.occupancy/existing_unknown": Basis(
        "The existing occupancy group of the space is not in public records; only plans or an inspection show "
        "it. A change of occupancy is not established."
    ),
    "change.occupancy/stated_same": Basis(
        "The existing occupancy is stated as Group {existing}, the same as the proposed group: not a change of "
        "occupancy."
    ),
    "change.occupancy/stated_differs": Basis(
        "The existing occupancy is stated as Group {existing} and the proposed occupancy is Group {proposed}: a "
        "change of occupancy."
    ),
    "change.occupancy/stated_proposed_unknown": Basis(
        "The existing occupancy is stated as Group {existing}, but the proposed group is not established, so a "
        "change of occupancy is not established."
    ),
    # ---- change of use 3: neighbourhood notification (Planning Code § 311; the section and the link printed
    # are the data entry's own)
    "change.notice/no_version": Basis(
        "No version of the neighbourhood notification rule is on file for {date}, so whether the change needs "
        "notice is not established.",
        _NOTICE_SECTION,
    ),
    "change.notice/not_read": Basis(
        "The neighbourhood notification rule on file for {date} is not in a form the rules read, so whether the "
        "change needs notice is not established."
    ),
    "change.notice/no_trigger": Basis(
        "Under the Planning Code as in force on {date}, a change of use does not by itself need neighbourhood "
        "notice{since}. Notice for work that enlarges a building, and for demolition or new construction, is a "
        "separate question the rules did not check."
    ),
    "change.notice/use_not_established": Basis(
        "On {date} a change of use could need neighbourhood notice. Whether the use changes is not established, "
        "so whether notice was needed is not established."
    ),
    "change.notice/no_change": Basis(
        "The use does not change, so no neighbourhood notice was needed for a change of use on {date}."
    ),
    "change.notice/no_district": Basis(
        "No zoning district is on file for this address, so whether the change of use needed neighbourhood "
        "notice on {date} is not established."
    ),
    "change.notice/district_outside": Basis(
        "On {date} neighbourhood notice for a change of use applied in {districts} districts. {district} is "
        "not one of them, so no notice was needed for the change of use."
    ),
    "change.notice/district_not_placed": Basis(
        "On {date} neighbourhood notice for a change of use applied in {districts} districts. The rules do not "
        "place {district} inside or outside that list, so whether notice was needed is not established."
    ),
    "change.notice/formula_retail": Basis(
        "On {date} establishing a Formula Retail use in {a_class} district needed neighbourhood notice, whether "
        "or not the use changed, and the business is stated to be part of a chain, so notice was required."
    ),
    "change.notice/formula_retail_answered": Basis(
        "On {date} establishing a Formula Retail use in {a_class} district needed neighbourhood notice, whether "
        "or not the use changed, and you answered that the business is part of a chain with eleven or more other "
        "locations, so notice was required."
    ),
    "change.notice/formula_retail_missing": Basis(
        "On {date} establishing a Formula Retail use in {a_class} district needed neighbourhood notice, whether "
        "or not the use changed. The description does not say whether the business is part of a chain, so "
        "whether notice was needed is not established."
    ),
    # the business is said to be part of a chain but no count is given (change of 2026-11-16), in T5's words for
    # the same case ("T5.count_missing"); "You answered" where the intake answer gave it
    "change.notice/formula_retail_count_missing": Basis(
        "On {date} establishing a Formula Retail use in {a_class} district needed neighbourhood notice, whether "
        "or not the use changed. The applicant says the business is part of a chain but not how many other "
        "locations it has. Planning Code § 303.1 counts a business as formula retail from eleven other "
        "locations, so whether notice was needed is not established."
    ),
    "change.notice/formula_retail_count_missing_answered": Basis(
        "On {date} establishing a Formula Retail use in {a_class} district needed neighbourhood notice, whether "
        "or not the use changed. You answered that the business is part of a chain but not how many other "
        "locations it has. Planning Code § 303.1 counts a business as formula retail from eleven other "
        "locations, so whether notice was needed is not established."
    ),
    "change.notice/restaurant_to_limited": Basis(
        "On {date} a change from a Restaurant to a Limited Restaurant was exempt from neighbourhood notice.",
        "Planning Code § 311(b)(1)(A)",
    ),
    "change.notice/not_listed": Basis(
        "On {date} a change of use needed neighbourhood notice in {a_class} district only when it was a change "
        "to, or the addition of, a listed use. {uses} is not one of the uses on file, so no notice was needed "
        "for the change of use."
    ),
    "change.notice/exempt_principal": Basis(
        "On {date} a change of use to a principally permitted use in an NC or NCT district was exempt from "
        "neighbourhood notice. {district} is {a_class} district and {uses} is principally permitted here, so "
        "no notice was needed for the change of use."
    ),
    "change.notice/required": Basis(
        "On {date} a change of use to {uses} in {a_class} district needed neighbourhood notice unless the new "
        "use was principally permitted. It is not principally permitted here, so notice was required."
    ),
    "change.notice/required_residential": Basis(
        "On {date} a change of use to {uses} in a Residential district needed neighbourhood notice, and the new "
        "use is not principally permitted here, so notice was required."
    ),
    "change.notice/principal_not_decided": Basis(
        "On {date} a change of use to {uses} in {a_class} district needed neighbourhood notice unless the new "
        "use was principally permitted. Whether it is principally permitted here is not decided, so whether "
        "notice was needed is not established."
    ),
    "change.notice/residential_principal": Basis(
        "On {date} a change of use to {uses} in a Residential district needed neighbourhood notice, except a "
        "change to a principally permitted use in a limited commercial use or a limited corner commercial use "
        "(Planning Code §§ 186, 231). The rules cannot tell whether the space is one, so whether notice was "
        "needed is not established."
    ),
    "change.notice/mixed_use": Basis(
        "On {date}, in an Eastern Neighborhoods Mixed Use district, a change of use for neighbourhood notice "
        "meant a change in, or the addition of, a land use category. The rules do not decide land use "
        "categories, so whether notice was needed is not established."
    ),
    # ---- building row (B0, B1 and B2 are v1's sentences in pathway.LEGAL_BASIS)
    "building.status/B1_occupancy": Basis(
        "A change of occupancy needs a building permit, secured before the change is made: {status}."
    ),
    "building.status/B3_missing": Basis(
        "Without {missing}, the rules cannot say whether this is a change of use or of occupancy, so they "
        "cannot say which building permit applies: {status}.",
        _BUILDING_PERMIT,
    ),
    "building.status/B3_occupancy_missing": Basis(
        "Without {missing}, the rules cannot say whether this is a change of occupancy, so they cannot say which "
        "building permit applies: {status}.",
        _BUILDING_PERMIT,
    ),
    "building.status/B3_use_missing": Basis(
        "Without {missing}, the rules cannot say whether this is a change of use, so they cannot say which "
        "building permit applies: {status}.",
        _BUILDING_PERMIT,
    ),
    "building.status/B3_not_covered": Basis(
        "The rules have no Planning Code use for the concept, so they cannot say whether this is a change of "
        "use or of occupancy, or which building permit applies: {status}.",
        _BUILDING_PERMIT,
    ),
    # ---- entertainment row (E0 to E3 are v1's sentences in pathway.LEGAL_BASIS)
    "entertainment.permit": Basis(
        "The description gives the kind of entertainment, so the permit looked up is the {permit}."
    ),
    "entertainment.permit/answered": Basis(
        "You answered the kind of entertainment, so the permit looked up is the {permit}."
    ),
    "entertainment.dance": Basis(
        "On {date} a dance permit from the Entertainment Commission was needed to conduct a dance, unless the "
        "location held a valid Place of Entertainment permit."
    ),
    "entertainment.closing/missing": Basis(
        "The description does not give the closing time. Staying open to patrons between 2 a.m. and 6 a.m. "
        "would also need an Extended-Hours Premises permit.",
        _EXTENDED_HOURS,
    ),
    # ---- referral steps ({application}, {agency} and {section} are the data entry's own words)
    "referral.step": Basis(
        "{application}: this application is sent to the {agency} for review ({section}).{since}"
    ),
    "referral.step/ended": Basis(
        "{application}: until {date} this application was also sent to the {agency} ({section}{ended_by}). That "
        "step has ended.{still}"
    ),
}
# Clauses dropped into the sentences above when the data gives a date.
NOTICE_SINCE = ": the change-of-use trigger has been out of Planning Code § 311 since {date}{ordinance}"
REFERRAL_SINCE = " It has applied in this form since {date}{ordinance}."
REFERRAL_ENDED_BY = "; ended by {ordinance}"
REFERRAL_STILL_REQUIRED = " The permit is still required."

# The transactions state law tests for undue concentration (tracts.TRANSACTIONS_TESTED), in words.
TESTED_TRANSACTIONS: dict[str, str] = {
    "new_licence": "a new licence",
    "premises_transfer": "a transfer from other premises",
}
# Rule 2, neighbourhood notice: the words of a version of Planning Code § 311(b) that make establishing a Formula
# Retail use trigger notice on its own (quoted text of the versions before 2024-01-14).
FORMULA_RETAIL_NOTICE = "establishment of a formula retail use"
# Rule A0r: what the status line says when a T4 finding is not decided and names no input.
UNNAMED_INPUT = "an input the description does not give"
# Rule B3: the one missing input that is not a concept fact (no description states it).
EXISTING_GROUP_PHRASE = "the existing occupancy group of the space, which only plans or an inspection show"
ROW_APPROVALS: dict[str, str] = {
    "building_change_of_use/occupancy": "Building permit with change of occupancy",
}
# The contract's PLANNING_USE_LABELS has no entry for "nighttime_entertainment"; the label is § 102's.
USE_LABELS: dict[str, str] = {**PLANNING_USE_LABELS, "nighttime_entertainment": "Nighttime Entertainment"}
# `change_answers(described_change=...)`: the variants of pathway.LEGAL_BASIS "zoning.change_of_use/<name>"
# that state a change of use on the applicant's own description (rule table v1's two profile flags).
DESCRIBED_CHANGES: tuple[str, ...] = ("new_construction", "applicant")
# What the description can say the space was last used as. "vacant" is not a use and gives no last use.
EXISTING_USE_LABELS: dict[str, str] = {
    "bar": USE_LABELS["bar"],
    "restaurant": USE_LABELS["restaurant"],
    "limited_restaurant": USE_LABELS["limited_restaurant"],
    "nighttime_entertainment": USE_LABELS["nighttime_entertainment"],
    "retail": "Retail",
    "laundromat": "Laundromat",
    "other": "Another use",
}
_EXISTING_USE_ORDER: tuple[ExistingUse, ...] = get_args(ExistingUse)

T4: TriggerFamily = "licence_in_restricted_district"
# The findings that say whether the use itself is principally permitted (rule 2, neighbourhood notice).
USE_CONTROL_FAMILIES: tuple[TriggerFamily, ...] = (
    "new_use_control",
    "special_district_use_control",
    "nighttime_entertainment",
    "licence_in_restricted_district",
)
# Of those, the ones whose "principal" says the use is principally permitted (a licence rule that asks for
# nothing says nothing about the use).
_USE_TABLE_FAMILIES: frozenset[str] = frozenset(USE_CONTROL_FAMILIES) - {T4}


# Rule A2: the requirements of the dated data that could stop the licence, by the data's own rule_id. A
# requirement states no control, so T4's control never shows it; T4 prints it as a line whose rule_id ends with
# this id, and only when it reaches the concept (here: a Bar that is new). To add one, add its rule_id.
BLOCKING_REQUIREMENTS: frozenset[str] = frozenset({"mission.new_bar_licence_from_bar_in_district"})

# Planning Code § 311(b) as in force before 2024-01-14 named classes of district. A district code is placed
# in a class by its form; a code that matches nothing is "not placed" and the answer is "not established".
# The class names are the ones the data's `districts` fact uses.
NOTICE_DISTRICT_CLASSES: tuple[tuple[str, str], ...] = (
    (r"NCT(-.+)?", "NCT"),
    (r"NC-[123S]|NCD(-.+)?", "NC"),
    (r"R[HMC]-\S+|RTO(-M)?", "Residential"),
    (r"MUR|UMU", "Eastern Neighborhoods Mixed Use"),
)
# Districts the data's rule text names as outside the section's list ("for example C-2 and C-3").
NOTICE_DISTRICTS_OUTSIDE = r"C-2|C-3-\S+"
_A_CLASS: dict[str, str] = {
    "NC": "an NC",
    "NCT": "an NCT",
    "Residential": "a Residential",
    "Eastern Neighborhoods Mixed Use": "an Eastern Neighborhoods Mixed Use",
}

# The Entertainment Commission permits the row can name: the data's `permit` key -> the name printed.
PLACE_OF_ENTERTAINMENT = "place_of_entertainment"
LIMITED_LIVE_PERFORMANCE = "limited_live_performance"
FIXED_PLACE_OUTDOOR_AMPLIFIED_SOUND = "fixed_place_outdoor_amplified_sound"
EXTENDED_HOURS_PREMISES = "extended_hours_premises"
# The dance permit (Police Code Article 15), an approval until Ordinance 118-25 ended it (the data's dates).
DANCE_PERMIT = "dance_hall"
DANCE_PERMIT_NAME = "dance permit"
ENTERTAINMENT_PERMIT_NAMES: dict[str, str] = {
    PLACE_OF_ENTERTAINMENT: "Place of Entertainment permit",
    LIMITED_LIVE_PERFORMANCE: "Limited Live Performance permit",
    FIXED_PLACE_OUTDOOR_AMPLIFIED_SOUND: "Fixed Place Outdoor Amplified Sound permit",
    EXTENDED_HOURS_PREMISES: "Extended-Hours Premises permit",
}
# The permits behind v1's general approval name, in the order it names them.
GENERAL_ENTERTAINMENT_PERMITS: tuple[str, ...] = (
    PLACE_OF_ENTERTAINMENT,
    LIMITED_LIVE_PERFORMANCE,
    FIXED_PLACE_OUTDOOR_AMPLIFIED_SOUND,
)
ENTERTAINMENT_GROUP = "entertainment_permits"
OTHER_GROUP = "other_referrals"
# The data's `permit` keys under "other_referrals" for each row.
ABC_LICENCE = "abc_licence"
ABC_PUBLIC_CONVENIENCE = "abc_licence_public_convenience_or_necessity"
OTHER_REFERRAL_PERMITS: dict[str, tuple[str, ...]] = {
    "alcohol": (ABC_LICENCE,),
    "health": ("health_permit",),
    "building_change_of_use": ("building_permit",),
}
_ORDINANCE = re.compile(r"Ord\. [\w-]+(?:, File No\. \d+)?")


# ---- small helpers ------------------------------------------------------------------------------------
def _say(
    key: str,
    *,
    citations: Iterable[str] = (),
    code_section: str | None = None,
    source_url: str | None = None,
    **fields: Any,
) -> RuleLine:
    """One rule line from its fixed sentence in ROW_BASIS, else in pathway.LEGAL_BASIS. `code_section` and
    `source_url` are the data entry's or the record's own, used when the sentence carries no fixed reference."""
    basis = ROW_BASIS[key] if key in ROW_BASIS else LEGAL_BASIS[key]
    return RuleLine(
        rule_id=key.split("/", 1)[0],
        text=basis.text.format(**fields),
        code_section=basis.code_section if basis.code_section is not None else (code_section or None),
        source_url=basis.source_url if basis.source_url is not None else (source_url or None),
        citations=sorted(set(citations)),
    )


def _row(
    area: ApprovalArea,
    approval: str,
    status: ApprovalStatus,
    basis: Iterable[RuleLine],
    *,
    status_note: str | None = None,
    referral: Iterable[RuleLine] = (),
    missing: Iterable[str] = (),
) -> RowDetermination:
    return RowDetermination(
        area=area,
        approval=approval,
        agency=AGENCIES[area],
        status=status,
        status_note=status_note,
        basis=_merge(basis),
        referral_steps=list(referral),
        missing_inputs=list(dict.fromkeys(missing)),
    )


def _day(on: dt.date) -> str:
    """'2025-08-16' as '16 August 2025'."""
    return tracts.plain_date(on.isoformat())


def _and(parts: Sequence[str]) -> str:
    """'A', 'A and B', 'A, B and C'."""
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


def _uses(uses: Iterable[str]) -> str:
    """'Restaurant and Nighttime Entertainment', in the order given."""
    return _and([USE_LABELS[u] for u in uses])


def _use_name(concept: ConceptFacts) -> str:
    """The concept's first use for v1's 'a new {use}' sentences; 'use' when the rules read none."""
    return USE_LABELS[concept.use] if concept.use != "not_covered" else "use"


def _sorted_findings(findings: Iterable[TriggerFinding]) -> list[TriggerFinding]:
    """The findings in one order, whatever order they were passed in."""
    return sorted(findings, key=lambda f: (f.rule_id, f.family, f.model_dump_json()))


def _cited(lines: Iterable[RuleLine]) -> list[str]:
    return sorted({c for line in lines for c in line.citations})


def _barred_names(findings: Iterable[TriggerFinding]) -> str:
    """'formula retail and use size': the labels of the findings that bar the concept, in trigger order (T1 to
    T11, as the zoning row names them), whatever order they were passed in."""

    def number(f: TriggerFinding) -> int:
        digits = f.rule_id[1:]
        return int(digits) if f.rule_id[:1] == "T" and digits.isdigit() else 99

    ordered = sorted(_sorted_findings(findings), key=number)
    return _and([f.label[:1].lower() + f.label[1:] for f in ordered])


def _not_as_described(key: str, zoning_barred_by: Sequence[TriggerFinding]) -> RuleLine:
    """Rules B0z and E0z (and H0z, O0z in app.memo.pathway): Planning Code § 175(a) where a prohibited use bars
    the concept, naming what bars it."""
    return _say(
        key,
        triggers=_barred_names(zoning_barred_by),
        status=_status_words("not_permitted"),
        citations=_cited(line for f in zoning_barred_by for line in f.lines),
    )


def _ordinance(text: str | None) -> str:
    """'Ord. 118-25, File No. 250537' from the data's 'Ord. 118-25, File No. 250537, App. 7/17/2025, Eff.
    8/17/2025 (referral removed)'; '' when the data names none."""
    if not text:
        return ""
    m = _ORDINANCE.search(text)
    return m.group(0) if m else text.split(" (", 1)[0].strip()


def _in_brackets(text: str) -> str:
    return f" ({text})" if text else ""


def _citywide(key: str, on: dt.date) -> controls.Rule | None:
    """The citywide rule in force on the date; None when the data has no such rule, no version covers the date,
    the date is before the data starts, or the version on file says the rule had lapsed."""
    try:
        found = controls.citywide_rules(key, on)
    except KeyError:
        return None
    if not found or found[0].source.before_data_start or not found[0].in_force:
        return None
    return found[0]


def _quoted(rule: controls.Rule) -> str:
    """The quoted code text of a citywide rule's version: its quote and the quotes of its sources, lower case."""
    sources = rule.extra.get("sources")
    quotes = (
        [str(q.get("quote") or "") for q in sources if isinstance(q, Mapping)]
        if isinstance(sources, tuple)
        else []
    )
    return " ".join([rule.source.quote, *quotes]).lower()


def _facts(rule: controls.Rule) -> Mapping[str, Any]:
    facts = rule.extra.get("facts")
    return facts if isinstance(facts, Mapping) else {}


# ---- rule 2: the three change-of-use answers ------------------------------------------------------------
@dataclass(frozen=True)
class _PlanningChange:
    answer: ChangeOfUse
    lines: tuple[RuleLine, ...]
    last: tuple[str, ...]  # the last uses compared (planning uses or stated uses); () when none is shown
    added: tuple[PlanningUse, ...]  # the proposed uses that are not among the last uses
    missing: tuple[str, ...]  # fixed phrases of the inputs that would settle a "not_established"


def _planning_change(
    concept: ConceptFacts, site: SiteFacts, described_change: str | None = None
) -> _PlanningChange:
    """Rule 2, planning_use. `described_change`: see `change_answers`."""
    proposed = concept.planning_uses.value
    evidence = tuple(site.existing_use_lines)

    def as_described() -> _PlanningChange:
        """Rule table v1's rule, kept: neither the records nor a stated last use decide it, and the applicant
        describes new construction or a space that was not a food or drink use."""
        line = _say(f"zoning.change_of_use/{described_change}", a_use=_a(concept.use))
        return _PlanningChange("yes", (*evidence, line), (), proposed, ())

    if not proposed:
        if described_change is not None:
            return as_described()
        missing = concept.missing(["planning_uses"])  # "food_service" for a bar that serves no alcohol
        return _PlanningChange(
            "not_established", (*evidence, _say("change.planning_use/no_use")), (), (), missing
        )
    given = set(concept.existing_use_stated.value)
    stated = tuple(u for u in _EXISTING_USE_ORDER if u in given and u != "vacant")
    shown = site.existing_use
    cited = _cited(evidence) if shown is not None else []
    # The licence records show the last use. A description that agrees with them and names more uses adds to
    # what they show (a licence type cannot show entertainment); one that disagrees is not read.
    if shown is not None and not (shown in stated and len(stated) > 1):
        if proposed == (shown,):
            line = _say("zoning.change_of_use/no", a_use=_a(shown), citations=cited)
            return _PlanningChange("no", (*evidence, line), (shown,), (), ())
        line = _say(
            "zoning.change_of_use/yes", existing=USE_LABELS[shown], use=_uses(proposed), citations=cited
        )
        added = tuple(u for u in proposed if u != shown)
        return _PlanningChange("yes", (*evidence, line), (shown,), added, ())
    if not stated:
        if described_change is not None:
            return as_described()
        key = "change.planning_use/vacant" if "vacant" in given else "change.planning_use/not_established"
        line = _say(key, uses=_uses(proposed))
        return _PlanningChange(
            "not_established", (*evidence, line), (), (), (MISSING_PHRASES["existing_use_stated"],)
        )
    existing_text = _and([EXISTING_USE_LABELS[u] for u in stated])
    added = tuple(u for u in proposed if u not in stated)
    source = "answered" if concept.by_answer("existing_use_stated") else "described"
    key = f"change.planning_use/{source}_yes" if added else f"change.planning_use/{source}_no"
    line = _say(key, existing=existing_text, uses=_uses(proposed), citations=cited)
    return _PlanningChange("yes" if added else "no", (*evidence, line), stated, added, ())


def existing_use_continues(concept: ConceptFacts, site: SiteFacts) -> bool:
    """Rule A1: the existing use continues, so the control for a NEW use is not what decides the licence. True
    when the planning-use answer is "no", or the description says an existing business stays."""
    return _planning_change(concept, site).answer == "no" or concept.changes_existing_business.stated


def _group(text: str) -> str:
    """'group a-2' -> 'A-2'."""
    return re.sub(r"^GROUP\s+", "", text.strip().upper())


@dataclass(frozen=True)
class _ProposedGroup:
    group: str | None  # "B", "A-2"; None when not established
    lines: tuple[RuleLine, ...]
    missing: tuple[str, ...]
    # "fewer than 50 people" against 50 seats or more: not established, and never read as unchanged either
    conflict: bool = False


def _proposed_group(concept: ConceptFacts, rules_date: dt.date) -> _ProposedGroup:
    """Rule 2, building_occupancy: the proposed occupancy group, from the data's rule on the rules date."""
    rule = _citywide("change_of_occupancy", rules_date)
    facts = _facts(rule) if rule is not None else {}
    assembly, limit = facts.get("food_and_drink_assembly_group"), facts.get("group_b_if_occupant_load_below")
    if rule is None or not isinstance(assembly, str) or not isinstance(limit, int):
        return _ProposedGroup(None, (_say("change.occupancy/no_rule", date=_day(rules_date)),), ())
    ref = {"code_section": rule.source.section, "source_url": rule.source.url}
    said = _say(
        "change.occupancy/rule",
        assembly=assembly,
        limit=limit,
        edition=str(facts.get("california_building_code_edition") or "").strip(),
        **ref,
    )
    if not concept.planning_uses.value:
        return _ProposedGroup(None, (said, _say("change.occupancy/proposed_no_use")), ())
    under, seats = concept.occupants_under_50.value, concept.seats.value
    answered = concept.by_answer("occupants_under_50")
    # the answer (or the description) is about 50 people; it is read only against a rule whose line is 50
    if under is not None and limit == 50:
        if under and seats is not None and seats >= limit:
            # fewer than 50 people, yet 50 seats or more: neither is read over the other, and the row names it
            key = "change.occupancy/under_but_seats_" + ("answered" if answered else "described")
            line = _say(key, limit=limit, seats=seats, **ref)
            return _ProposedGroup(None, (said, line), (MISSING_PHRASES["occupants_under_50"],), conflict=True)
        source = "answered" if answered else "proposed"
        key = f"change.occupancy/{source}_under" if under else f"change.occupancy/{source}_over"
        line = _say(key, limit=limit, assembly=assembly, **ref)
        return _ProposedGroup("B" if under else _group(assembly), (said, line), ())
    if seats is not None and seats >= limit:
        line = _say(
            "change.occupancy/proposed_seats_over", seats=seats, limit=limit, assembly=assembly, **ref
        )
        return _ProposedGroup(_group(assembly), (said, line), ())
    missing = MISSING_PHRASES["occupants_under_50"]
    if seats is not None:
        line = _say(
            "change.occupancy/proposed_seats_under", seats=seats, limit=limit, assembly=assembly, **ref
        )
    else:
        line = _say("change.occupancy/proposed_missing", missing=missing)
    return _ProposedGroup(None, (said, line), (missing,))


def occupants_conflict_seats(concept: ConceptFacts, rules_date: dt.date) -> int | None:
    """The seat count that disagrees with "fewer than 50 people" (the building row then names whether the space is
    for fewer than 50 people, reading neither over the other: `_proposed_group`); None when there is no such
    conflict. The report's open question names the conflict with it (`pathway.OCCUPANTS_CONFLICT_QUESTION`)."""
    return concept.seats.value if _proposed_group(concept, rules_date).conflict else None


def _no_change_stated(concept: ConceptFacts) -> bool:
    """The description states no enlargement or other change to the business: it says there is none (silence is
    never read as "none"), and the two floor areas, when both are given, are the same."""
    if concept.changes_existing_business.value != "none":
        return False
    before, after = concept.floor_area_before_sqft.value, concept.floor_area_sqft.value
    return before is None or after is None or before == after


@dataclass(frozen=True)
class _Occupancy:
    answer: ChangeOfUse
    lines: tuple[RuleLine, ...]
    missing: tuple[str, ...]


def _occupancy_change(
    concept: ConceptFacts, planning: _PlanningChange, rules_date: dt.date, existing_group: str | None
) -> _Occupancy:
    """Rule 2, building_occupancy. Never "yes" without both groups shown."""
    proposed = _proposed_group(concept, rules_date)
    existing = _group(existing_group) if existing_group is not None and existing_group.strip() else None
    if existing is not None and proposed.group is not None:  # both groups shown
        if proposed.group == existing:
            same = _say("change.occupancy/stated_same", existing=existing)
            return _Occupancy("no", (*proposed.lines, same), ())
        differs = _say("change.occupancy/stated_differs", existing=existing, proposed=proposed.group)
        return _Occupancy("yes", (*proposed.lines, differs), ())
    # the same use continues and the description says nothing changes: read as unchanged, unless the proposed
    # group is shown to be the assembly group (a small existing space could be Group B)
    assembly = _proposed_group(concept, rules_date)
    shown_assembly = (assembly.group is not None and assembly.group != "B") or assembly.conflict
    if planning.answer == "no" and _no_change_stated(concept) and not shown_assembly:
        key = (
            "change.occupancy/same_use_answered"
            if concept.by_answer("changes_existing_business")
            else "change.occupancy/same_use"
        )
        return _Occupancy("no", (*proposed.lines, _say(key)), ())
    if planning.answer == "no" and existing is None and concept.changes_existing_business.missing:
        return _Occupancy(
            "not_established",
            (*proposed.lines, _say("change.occupancy/change_missing")),
            (*proposed.missing, MISSING_PHRASES["changes_existing_business"], EXISTING_GROUP_PHRASE),
        )
    if existing is not None:
        line = _say("change.occupancy/stated_proposed_unknown", existing=existing)
        return _Occupancy("not_established", (*proposed.lines, line), proposed.missing)
    return _Occupancy(
        "not_established",
        (*proposed.lines, _say("change.occupancy/existing_unknown")),
        (*proposed.missing, EXISTING_GROUP_PHRASE),
    )


def notice_district_class(district: str | None) -> str | None:
    """The class of district § 311(b) put the code in before 2024-01-14 ("NC", "NCT", "Residential", "Eastern
    Neighborhoods Mixed Use"), "outside" for a district outside the section's list, None when the rules do not
    place the code."""
    code = (district or "").strip().upper()
    if not code:
        return None
    for pattern, name in NOTICE_DISTRICT_CLASSES:
        if re.fullmatch(pattern, code):
            return name
    return "outside" if re.fullmatch(NOTICE_DISTRICTS_OUTSIDE, code) else None


def _principally_permitted(findings: Sequence[TriggerFinding]) -> bool | None:
    """Is the new use principally permitted here, by the findings of the use-control families? False when one
    is conditional or not permitted; None (not decided) when one is not decided, the code and practice differ,
    or no finding says the use is principally permitted."""
    found = [f for f in findings if f.family in USE_CONTROL_FAMILIES]
    if any(f.control in ("conditional", "not_permitted") for f in found):
        return False
    if any(f.control in ("not_decided", "code_and_practice_differ") for f in found):
        return None
    if any(f.control == "principal" and f.family in _USE_TABLE_FAMILIES for f in found):
        return True
    return None


def _notice(
    planning: _PlanningChange,
    findings: Sequence[TriggerFinding],
    district: str | None,
    rules_date: dt.date,
    concept: ConceptFacts | None = None,
    continues: bool = False,
) -> tuple[NoticeAnswer, list[RuleLine]]:
    """Rule 2, neighbourhood_notice. `concept` and `continues` (a business that continues at the address) are
    read for the version of § 311(b) whose quoted text also names the establishment of a Formula Retail use."""
    date = _day(rules_date)
    rule = _citywide("neighbourhood_notification", rules_date)
    if rule is None:
        return "not_established", [_say("change.notice/no_version", date=date)]
    facts = _facts(rule)
    ref: dict[str, Any] = {"code_section": rule.source.section, "source_url": rule.source.url}
    triggers = facts.get("change_of_use_triggers_section_311")
    if triggers is False:  # the answer does not turn on whether the use changes
        since = ""
        if rule.source.in_force_from is not None:
            since = NOTICE_SINCE.format(
                date=_day(rule.source.in_force_from),
                ordinance=_in_brackets(_ordinance(rule.source.ordinance)),
            )
        return "not_required", [_say("change.notice/no_trigger", date=date, since=since, **ref)]
    if triggers is not True:
        return "not_established", [_say("change.notice/not_read", date=date, **ref)]
    # the version's quoted text: "... for a change of use; ... establishment of a Formula Retail Use". Establishing
    # one triggers notice without a change of use, in the district classes the version lists: a chain that does not
    # continue at the address needs notice; whether it is a chain, when not stated, decides any answer short of
    # "required".
    chain = concept.formula_retail if concept is not None else None
    fr_class = notice_district_class(district)
    if (
        chain is not None
        and chain.value is not False
        and not continues
        and fr_class is not None
        and fr_class in [str(d) for d in facts.get("districts") or ()]
        and FORMULA_RETAIL_NOTICE in _quoted(rule)
    ):
        fr_fields: dict[str, Any] = {
            "date": date,
            "a_class": _A_CLASS[fr_class],
            "citations": [f"zoning:{(district or '').strip()}"],
            **ref,
        }
        if chain.value:
            answered = concept is not None and concept.by_answer("formula_retail")
            key = "change.notice/formula_retail" + ("_answered" if answered else "")
            return "required", [_say(key, **fr_fields)]
        answer, lines = _notice_by_use(planning, findings, district, rules_date, rule, facts, ref)
        if answer == "required":
            return answer, lines
        # a chain whose count is not given is named by the count, a skipped chain question by the question; the
        # count's line says "You answered" only where the intake answer gave the chain
        unknown = "missing"
        if concept is not None and concept.chain_count_missing:
            unknown = "count_missing_answered" if concept.by_answer("part_of_chain") else "count_missing"
        return "not_established", [*lines, _say(f"change.notice/formula_retail_{unknown}", **fr_fields)]
    return _notice_by_use(planning, findings, district, rules_date, rule, facts, ref)


def _notice_by_use(
    planning: _PlanningChange,
    findings: Sequence[TriggerFinding],
    district: str | None,
    rules_date: dt.date,
    rule: controls.Rule,
    facts: Mapping[str, Any],
    ref: Mapping[str, Any],
) -> tuple[NoticeAnswer, list[RuleLine]]:
    """Rule 2, neighbourhood_notice, for a version under which a change of use triggers notice: by the use."""
    date = _day(rules_date)
    if planning.answer == "not_established":
        return "not_established", [_say("change.notice/use_not_established", date=date, **ref)]
    if planning.answer == "no":
        return "not_required", [_say("change.notice/no_change", date=date, **ref)]
    district = (district or "").strip()
    if not district:
        return "not_established", [_say("change.notice/no_district", date=date, **ref)]
    covered = [str(d) for d in facts.get("districts") or ()]
    name = notice_district_class(district)
    cites = [f"zoning:{district}"]
    if name is None or (name != "outside" and name not in covered):
        key = "change.notice/district_not_placed"
        return "not_established", [
            _say(key, date=date, districts=_and(covered), district=district, citations=cites, **ref)
        ]
    if name == "outside":
        key = "change.notice/district_outside"
        return "not_required", [
            _say(key, date=date, districts=_and(covered), district=district, citations=cites, **ref)
        ]
    if name == "Eastern Neighborhoods Mixed Use":
        return "not_established", [_say("change.notice/mixed_use", date=date, citations=cites, **ref)]
    added = planning.added
    if planning.last == ("restaurant",) and added == ("limited_restaurant",):
        return "not_required", [
            _say("change.notice/restaurant_to_limited", date=date, citations=cites, **ref)
        ]
    listed = {str(u) for u in facts.get("listed_uses_include") or ()}
    fields: dict[str, Any] = {
        "date": date,
        "uses": _uses(added),
        "a_class": _A_CLASS[name],
        "district": district,
    }
    if not any(USE_LABELS[u] in listed for u in added):
        return "not_required", [_say("change.notice/not_listed", citations=cites, **fields, **ref)]
    relied = [f for f in findings if f.family in USE_CONTROL_FAMILIES]
    cites = sorted({*cites, *(c for f in relied for c in _cited(f.lines))})
    principal = _principally_permitted(findings)
    if (
        name == "Residential"
    ):  # no exemption but for a limited (corner) commercial use, which the rules cannot tell
        if principal is False:
            return "required", [_say("change.notice/required_residential", citations=cites, **fields, **ref)]
        return "not_established", [
            _say("change.notice/residential_principal", citations=cites, **fields, **ref)
        ]
    if facts.get("exempt_if_principally_permitted_in_nc_or_nct") is not True:
        return "not_established", [_say("change.notice/not_read", date=date, **ref)]
    if principal is False:
        return "required", [_say("change.notice/required", citations=cites, **fields, **ref)]
    if principal is None:
        return "not_established", [
            _say("change.notice/principal_not_decided", citations=cites, **fields, **ref)
        ]
    return "not_required", [_say("change.notice/exempt_principal", citations=cites, **fields, **ref)]


def change_answers(
    concept: ConceptFacts,
    site: SiteFacts,
    findings: Sequence[TriggerFinding],
    zoning: ZoningInfo | str | None,
    *,
    rules_date: dt.date,
    existing_occupancy_group: str | None = None,
    described_change: str | None = None,
) -> ChangeAnswers:
    """Rule 2: the three change-of-use answers on the rules date. `zoning` is the district at the address (its
    record or its code; None when none is on file). `existing_occupancy_group` is the existing Building Code
    group ("B", "A-2") when an input states it; no public record does.

    `described_change` carries rule table v1's two profile flags, which `ConceptFacts` does not hold:
    "new_construction" (the project is new construction) or "applicant" (the applicant says the space was not
    a food or drink use). It is read only where the planning-use answer would otherwise be "not_established"
    (no last use from the records and none stated): the answer is then "yes", and the line says it is as
    described by the applicant (the two "zoning.change_of_use" sentences of pathway.LEGAL_BASIS). None, the
    default, reads neither flag."""
    if described_change is not None and described_change not in DESCRIBED_CHANGES:
        raise ValueError(f"described_change is one of {DESCRIBED_CHANGES}, got {described_change!r}")
    ordered = _sorted_findings(findings)
    district = zoning if isinstance(zoning, str) or zoning is None else zoning.district
    planning = _planning_change(concept, site, described_change)
    occupancy = _occupancy_change(concept, planning, rules_date, existing_occupancy_group)
    continues = concept.changes_existing_business.stated or (
        site.existing_use is not None and site.existing_use in concept.planning_uses.value
    )
    notice, notice_lines = _notice(planning, ordered, district, rules_date, concept, continues)
    return ChangeAnswers(
        planning_use=planning.answer,
        planning_use_lines=_merge(planning.lines),
        building_occupancy=occupancy.answer,
        building_occupancy_lines=_merge(occupancy.lines),
        neighbourhood_notice=notice,
        neighbourhood_notice_lines=_merge(notice_lines),
    )


# ---- rule 4: referral steps -----------------------------------------------------------------------------
def _entries(group: str, on: dt.date, *, kind: str) -> tuple[controls.Rule, ...]:
    """The entries of one group of the dated data, in force on the date or ended by it, in the data's order.
    Missing data is an empty list, never an error."""
    try:
        return controls.citywide_entries(group, on, kind=kind, include_ended=True)
    except KeyError:
        return ()


def entertainment_approvals(rules_date: dt.date) -> tuple[str, ...]:
    """The Entertainment Commission permits that are approvals on the rules date: the data's `permit` key of
    every "approval_required" entry in force, each once, in the data's order. Empty when the data carries no
    entertainment permits."""
    live = [r for r in _entries(ENTERTAINMENT_GROUP, rules_date, kind="approval_required") if r.in_force]
    return tuple(dict.fromkeys(str(r.extra.get("permit") or "") for r in live if r.extra.get("permit")))


def _step_line(step: controls.Rule, *, still_required: bool) -> RuleLine:
    application = step.applies_to or ""
    agency = str(step.extra.get("agency") or "")
    ref: dict[str, Any] = {"code_section": step.source.section, "source_url": step.source.url}
    if step.in_force:
        since = ""
        if step.source.in_force_from is not None:
            since = REFERRAL_SINCE.format(
                date=_day(step.source.in_force_from),
                ordinance=_in_brackets(_ordinance(step.source.ordinance)),
            )
        return _say(
            "referral.step",
            application=application,
            agency=agency,
            section=step.source.section,
            since=since,
            **ref,
        )
    ended_by = step.extra.get("ended_by")
    ordinance = _ordinance(ended_by if isinstance(ended_by, str) else None)
    assert step.source.in_force_to is not None  # `_steps` keeps an ended entry only when it has its last day
    return _say(
        "referral.step/ended",
        application=application,
        agency=agency,
        date=_day(step.source.in_force_to),
        section=step.source.section,
        ended_by=REFERRAL_ENDED_BY.format(ordinance=ordinance) if ordinance else "",
        still=REFERRAL_STILL_REQUIRED if still_required else "",
        **ref,
    )


def _later_version(step: controls.Rule, held: controls.Rule) -> bool:
    """Of two versions of one step, is `step` the one to print: the one in force, else the one that ended
    later."""
    if step.in_force != held.in_force:
        return step.in_force
    return (step.source.in_force_to or dt.date.max) > (held.source.in_force_to or dt.date.max)


def _steps(group: str, permits: Sequence[str], rules_date: dt.date) -> list[RuleLine]:
    """One line per permit and agency: the version of the step in force on the date; when none is, the last
    version that had ended by it. Permits in the order asked, agencies in the data's order."""
    by_step: dict[tuple[str, str], controls.Rule] = {}
    for step in _entries(group, rules_date, kind="referral_step"):
        key = (str(step.extra.get("permit") or ""), str(step.extra.get("agency") or ""))
        if not step.applies_to or not key[1]:
            continue  # an entry that names no application or no agency cannot be printed as a step
        if not step.in_force and step.source.in_force_to is None:
            continue
        held = by_step.get(key)
        if held is None or _later_version(step, held):
            by_step[key] = step
    approvals = set(entertainment_approvals(rules_date)) if group == ENTERTAINMENT_GROUP else None
    lines: list[RuleLine] = []
    for permit in dict.fromkeys(permits):
        if approvals is not None and permit not in approvals:
            continue  # not an approval on the rules date, so it has no steps to list
        lines += [
            _step_line(step, still_required=approvals is not None)
            for (name, _), step in by_step.items()
            if name == permit
        ]
    return lines


def _entertainment_permits(concept: ConceptFacts) -> tuple[tuple[str, ...], bool, bool]:
    """The permits the facts point to: (the entertainment permits, whether one permit is named by the stated
    kind, whether the concept closes after 2 a.m.). No entertainment and no late closing reads as v1 does: the
    general list."""
    kind = concept.entertainment_kind.value
    described = concept.live_entertainment or concept.amplified_sound or concept.dancing
    late = concept.closing.after_2am
    if kind == "place_of_entertainment":
        return (PLACE_OF_ENTERTAINMENT,), True, late
    if kind == "limited_live_performance":
        return (LIMITED_LIVE_PERFORMANCE,), True, late
    if late and not described:  # kind is "none" or not stated
        return (), False, late
    return GENERAL_ENTERTAINMENT_PERMITS, False, late


def referral_steps(
    area: ApprovalArea, concept: ConceptFacts, *, rules_date: dt.date, public_convenience: bool = False
) -> list[RuleLine]:
    """Rule 4: the referral steps inside the approval of one row on the rules date. `public_convenience` adds
    the steps of a public convenience or necessity determination to the alcohol row. Rows with no referral on
    file, and missing referral data, give an empty list. A referral step never sets or changes a status."""
    if area == "entertainment":
        permits, _, late = _entertainment_permits(concept)
        wanted = (*permits, EXTENDED_HOURS_PREMISES) if late else permits
        return _steps(ENTERTAINMENT_GROUP, wanted, rules_date)
    other = OTHER_REFERRAL_PERMITS.get(area, ())
    if area == "alcohol" and public_convenience:
        other = (*other, ABC_PUBLIC_CONVENIENCE)
    return _steps(OTHER_GROUP, other, rules_date) if other else []


# ---- rule 1: the alcohol row ----------------------------------------------------------------------------
def alcohol_approval(licence_type: str | None) -> str:
    """'ABC licence, Type 42 (on-sale beer and wine, public premises)'; 'ABC licence, Type 90' for a type v1's
    table does not name; plain 'ABC licence' when the type is not known."""
    if not licence_type:
        return APPROVALS["alcohol"]
    kind = LICENCE_TYPES.get(licence_type)
    label = f" ({kind.label})" if kind else ""
    return f"{APPROVALS['alcohol']}, Type {licence_type}{label}"


def _licence_fact_lines(concept: ConceptFacts) -> list[RuleLine]:
    lines: list[RuleLine] = []
    if concept.outdoor_alcohol_answer_over_description:
        lines.append(_say("alcohol.outdoor_answer"))
    number = concept.licence_type.value
    if number is not None:
        kind = LICENCE_TYPES.get(number)
        key = "alcohol.licence/derived" if concept.licence_type.derived else "alcohol.licence/stated"
        if concept.licence_type.derived and concept.by_answer("alcohol_type"):
            key = "alcohol.licence/derived_answered"  # what is poured is the applicant's answer
        lines.append(_say(key, type=number, label=f" ({kind.label})" if kind else ""))
    transaction = concept.alcohol_transaction.value
    if transaction is not None:
        lines.append(_say(f"alcohol.transaction/{transaction}"))
    return lines


def _concentration(
    concept: ConceptFacts, tract: str | None, site: SiteFacts, rules_date: dt.date
) -> tuple[list[RuleLine], bool]:
    """The census tract lines, and whether the further-review qualifier applies (the tract is over and the
    transaction is one the statute tests). Nothing is printed, and nothing is implied, when the tract or the
    licence's kind is unknown, the tract has no figures or is not over, or the transaction is not tested. The
    qualifier is not set when the figures are later than the rules date (the tract's standing then is not
    established) or when an active licence of the same type is on file at the address (§ 23958.4(f): the test does
    not apply to premises licensed and operated with that type within 90 days, which the rules cannot tell)."""
    number = concept.licence_type.value
    kind = tracts.kind_for_licence_type(number)
    if tract is None or kind is None:
        return [], False
    figures = tracts.concentration(tract, kind)
    finding = tracts.over_concentration_finding(figures)
    if finding is None or figures is None:
        return [], False
    numbers = RuleLine(
        rule_id=finding.rule_id,
        text=finding.line,
        code_section=finding.citation,
        source_url=finding.source_url,
    )
    later = (
        [_say("alcohol.tract_concentration/later", date=_day(rules_date))]
        if rules_date < dt.date.fromisoformat(figures.active_as_of)
        else []
    )
    transaction = concept.alcohol_transaction.value
    if transaction is None:
        return [numbers, *later, _say("alcohol.tract_concentration/transaction_missing")], False
    if transaction not in tracts.TRANSACTIONS_TESTED:
        return [], False
    if later:
        return [numbers, *later], False
    if number in site.licence_types:
        return [numbers, _say("alcohol.tract_concentration/same_type", type=number)], False
    tested = _say(
        "alcohol.tract_concentration/tested",
        transaction=TESTED_TRANSACTIONS[transaction],
        note=finding.status_note,
    )
    return [numbers, tested], True


def blocking_requirements(findings: Iterable[TriggerFinding]) -> list[RuleLine]:
    """Rule A2: the lines of the licence findings (T4) that state a requirement in BLOCKING_REQUIREMENTS, in
    the findings' order."""
    return [
        line
        for f in findings
        if f.family == T4
        for line in f.lines
        if any(
            line.rule_id == rid or line.rule_id.endswith((f":{rid}", f".{rid}"))
            for rid in BLOCKING_REQUIREMENTS
        )
    ]


def alcohol_row(
    concept: ConceptFacts,
    site: SiteFacts,
    findings: Sequence[TriggerFinding],
    *,
    zoning_prohibits_use: bool,
    tract: str | None,
    rules_date: dt.date,
    prohibited_use_is_new: bool = False,
    zoning_barred_by: Sequence[TriggerFinding] = (),
) -> RowDetermination:
    """Rule 1: the alcohol licence row. `zoning_prohibits_use`: the use controls prohibit a new use of this
    kind at the address. `tract`: the census tract of the address as ABC writes it (tracts.tract_at), None
    when it is not known. `prohibited_use_is_new`: the caller's `zoning_prohibits_use` already leaves out a
    use that continues (the engine reads it from the use triggers, which never read a use that continues), so
    rule A1 applies without this module's own test of whether the existing use continues. `zoning_barred_by`:
    the findings that make the zoning row not permitted (rule A1z), when it is not the use itself."""
    t4 = [f for f in _sorted_findings(findings) if f.family == T4]
    number = concept.licence_type.value
    transaction = concept.alcohol_transaction.value
    approval = alcohol_approval(number)
    continues = existing_use_continues(concept, site)
    facts = _licence_fact_lines(concept)
    tract_lines, qualifier = _concentration(concept, tract, site, rules_date)

    def words(status: ApprovalStatus) -> str:
        return _status_words(status)

    def lines_of(*controls_: str) -> list[RuleLine]:
        return [line for f in t4 if f.control in controls_ for line in f.lines]

    # A1, A1r
    barred = lines_of("not_permitted")
    if zoning_prohibits_use and (prohibited_use_is_new or not continues):
        a1 = _say(
            "alcohol.status/A1",
            use=_use_name(concept),
            status=words("not_permitted"),
            citations=_cited(barred),
        )
        # a licence that cannot issue: the tract's numbers only, never "the licence may still issue"
        return _row("alcohol", approval, "not_permitted", [*facts, *barred, *tract_lines[:1], a1])
    if barred:
        a1r = _say("alcohol.status/A1r", status=words("not_permitted"), citations=_cited(barred))
        return _row("alcohol", approval, "not_permitted", [*facts, *barred, *tract_lines[:1], a1r])
    # A1z: zoning bars the concept as described and the existing use does not continue; or a prohibited use
    # (formula retail) bars it, whether or not an existing use continues (the decision of 2026-11-12)
    prohibited = any(f.rule_id in PROHIBITED_USE_TRIGGERS for f in zoning_barred_by)
    if zoning_barred_by and (prohibited or not continues):
        named = _barred_names(zoning_barred_by)
        a1z = _say(
            "alcohol.status/A1z",
            triggers=named,
            status=words("not_permitted"),
            citations=_cited(line for f in zoning_barred_by for line in f.lines),
        )
        return _row("alcohol", approval, "not_permitted", [*facts, *tract_lines[:1], a1z])

    held = transaction == "licence_already_held"
    limit = [_say("alcohol.county_limit", type=number)] if number in COUNTY_LIMITED_TYPES and not held else []
    # § 23958.4(b): for an eating-place licence (b)(1) the applicant shows public convenience or necessity to
    # ABC; for any other licence (b)(2) (a bar's) the local governing body determines it, and that request is
    # referred on. A type the rules cannot place in either limb is said so, and no steps are added.
    shows = LICENCE_TYPES[number].shows if number in LICENCE_TYPES else None
    local_finding = qualifier and shows == "bar"
    if qualifier and number is not None and shows is None:
        tract_lines = [*tract_lines, _say("alcohol.tract_concentration/limb_unknown", type=number)]
    steps = (
        []
        if held  # nothing is applied for
        else referral_steps("alcohol", concept, rules_date=rules_date, public_convenience=local_finding)
    )
    undecided = lines_of("not_decided")
    undecided_inputs = [m for f in t4 if f.control == "not_decided" for m in f.missing_inputs]

    conditional = lines_of("conditional")
    required = blocking_requirements(t4)
    # what T4 found is printed on every row below, so a missing input never hides a rule that is known
    known = [*(line for line in conditional if line not in required), *undecided]

    # A0
    missing = list(concept.missing(("licence_type", "alcohol_transaction")))
    if missing:
        status: ApprovalStatus = "insufficient_information"
        a0 = _say("alcohol.status/A0", missing=_and(missing), status=words(status))
        basis = [*facts, *limit, *known, *required, *tract_lines, a0]
        return _row("alcohol", approval, status, basis, referral=steps, missing=[*missing, *undecided_inputs])
    # A0r
    if undecided:
        status = "insufficient_information"
        named = _and(list(dict.fromkeys(undecided_inputs))) or UNNAMED_INPUT
        a0r = _say("alcohol.status/A0r", missing=named, status=words(status), citations=_cited(undecided))
        basis = [*facts, *limit, *known, *required, *tract_lines, a0r]
        return _row("alcohol", approval, status, basis, referral=steps, missing=undecided_inputs)
    # A2
    if required:
        status = "potential_blocker"
        a2 = _say("alcohol.status/A2", status=words(status), citations=_cited(required))
        # the requirement comes last before the status line, which says "that condition"
        basis = [*facts, *limit, *known, *tract_lines, *required, a2]
        return _row("alcohol", approval, status, basis, referral=steps)
    note = tracts.PCN_STATUS_NOTE if qualifier else None
    # the licence is already held: nothing is filed with ABC (a requirement of A2 still stands, and a conditional
    # licence rule is read by A2c)
    if held and not conditional:
        status = "allowed"
        line = _say("alcohol.status/held", status=words(status))
        return _row("alcohol", approval, status, [*facts, *lines_of("code_and_practice_differ"), line])
    # A2c
    if conditional:
        status = "further_review"
        a2c = _say("alcohol.status/A2c", status=words(status), citations=_cited(conditional))
        basis = [*facts, *limit, *conditional, *tract_lines, a2c]
        return _row("alcohol", approval, status, basis, status_note=note, referral=steps)
    # A3
    status = "further_review"
    differ = lines_of("code_and_practice_differ")
    a3 = _say("alcohol.status/A3", status=words(status))
    basis = [*facts, *limit, *differ, *tract_lines, a3]
    return _row("alcohol", approval, status, basis, status_note=note, referral=steps)


# ---- rule 3: the building row ---------------------------------------------------------------------------
def building_row(
    changes: ChangeAnswers,
    concept: ConceptFacts,
    *,
    zoning_prohibits_use: bool,
    rules_date: dt.date,
    existing_occupancy_group: str | None = None,
    zoning_barred_by: Sequence[TriggerFinding] = (),
) -> RowDetermination:
    """Rule 3: the building permit row, from the answers `change_answers` gave for the same concept (pass the
    same `existing_occupancy_group`). `zoning_prohibits_use`: the use controls prohibit a new use of this kind
    at the address. `zoning_barred_by`: the prohibited uses (`pathway.PROHIBITED_USE_TRIGGERS`) that make the
    zoning row not permitted (rule B0z)."""
    area: ApprovalArea = "building_change_of_use"
    lines = [*changes.planning_use_lines, *changes.building_occupancy_lines]
    plain, with_use = APPROVALS["building_change_of_use"], APPROVALS["building_change_of_use/yes"]
    barred_approval = with_use if changes.planning_use == "yes" else plain
    if zoning_prohibits_use and changes.planning_use != "no":  # B0
        b0 = _say("building.status/B0", use=_use_name(concept), status=_status_words("not_permitted"))
        return _row(area, barred_approval, "not_permitted", [*changes.planning_use_lines, b0])
    if zoning_barred_by:  # B0z
        b0z = _not_as_described("building.status/B0z", zoning_barred_by)
        return _row(area, barred_approval, "not_permitted", [*changes.planning_use_lines, b0z])
    steps = referral_steps(area, concept, rules_date=rules_date)
    if changes.planning_use == "yes":  # B1
        b1 = _say("building.status/B1", status=_status_words("further_review"))
        return _row(area, with_use, "further_review", [*lines, b1], referral=steps)
    if changes.building_occupancy == "yes":  # B1, by the occupancy
        rule = _citywide("change_of_occupancy", rules_date)
        b1 = _say(
            "building.status/B1_occupancy",
            status=_status_words("further_review"),
            code_section=rule.source.section if rule else None,
            source_url=rule.source.url if rule else None,
        )
        approval = ROW_APPROVALS["building_change_of_use/occupancy"]
        return _row(area, approval, "further_review", [*lines, b1], referral=steps)
    if changes.planning_use == "no" and changes.building_occupancy == "no":  # B2
        b2 = _say("building.status/B2", status=_status_words("allowed"))
        return _row(area, plain, "allowed", [*lines, b2], referral=steps)
    # B3: name what is missing
    missing: list[str] = []
    if changes.planning_use == "not_established":
        if not concept.planning_uses.value:
            missing += concept.missing(["planning_uses"])  # "food_service" for a bar that serves no alcohol
        else:
            missing.append(MISSING_PHRASES["existing_use_stated"])
    if changes.building_occupancy == "not_established":
        missing += _proposed_group(concept, rules_date).missing
        if changes.planning_use == "no" and concept.changes_existing_business.missing:
            missing.append(MISSING_PHRASES["changes_existing_business"])
        if not (existing_occupancy_group or "").strip():
            missing.append(EXISTING_GROUP_PHRASE)
    missing = list(dict.fromkeys(missing))
    status: ApprovalStatus = "insufficient_information"
    # the sentence names only the question that is open
    if missing and changes.planning_use == "no":
        b3 = _say("building.status/B3_occupancy_missing", missing=_and(missing), status=_status_words(status))
    elif missing and changes.building_occupancy == "no":
        b3 = _say("building.status/B3_use_missing", missing=_and(missing), status=_status_words(status))
    elif missing:
        b3 = _say("building.status/B3_missing", missing=_and(missing), status=_status_words(status))
    else:
        b3 = _say("building.status/B3_not_covered", status=_status_words(status))
    return _row(area, plain, status, [*lines, b3], referral=steps, missing=missing)


# ---- rule 5: the entertainment row ----------------------------------------------------------------------
def entertainment_approval(concept: ConceptFacts) -> str:
    """The approval named for the permit the facts point to; v1's general name when they point to none."""
    permits, named, late = _entertainment_permits(concept)
    if not named:
        if not late:
            return APPROVALS["entertainment"]
        return APPROVALS["entertainment/with_extended_hours" if permits else "entertainment/extended_hours"]
    name = ENTERTAINMENT_PERMIT_NAMES[permits[0]]
    return f"{name}, and {ENTERTAINMENT_PERMIT_NAMES[EXTENDED_HOURS_PREMISES]}" if late else name


def entertainment_row(
    concept: ConceptFacts,
    findings: Sequence[TriggerFinding],
    *,
    rules_date: dt.date,
    zoning_prohibits_use: bool,
    zoning_barred_by: Sequence[TriggerFinding] = (),
) -> RowDetermination:
    """Rule 5: v1's E0 to E3, and E0z. `zoning_prohibits_use`: the use controls prohibit a new use of this kind
    at the address and the use does not already exist there (v1's test for E0). `zoning_barred_by`: the
    prohibited uses (`pathway.PROHIBITED_USE_TRIGGERS`) that make the zoning row not permitted (rule E0z)."""
    area: ApprovalArea = "entertainment"
    permits, named, late = _entertainment_permits(concept)
    approval = entertainment_approval(concept)
    if zoning_prohibits_use:  # E0
        barred = [f for f in _sorted_findings(findings) if f.control == "not_permitted"]
        # name the use the findings bar: Nighttime Entertainment when its own trigger is the one not permitted
        by_entertainment = any(f.family == "nighttime_entertainment" for f in barred) and not any(
            f.family in ("new_use_control", "special_district_use_control") for f in barred
        )
        e0 = _say(
            "entertainment.status/E0",
            use=USE_LABELS["nighttime_entertainment"] if by_entertainment else _use_name(concept),
            status=_status_words("not_permitted"),
            citations=_cited(line for f in barred for line in f.lines),
        )
        return _row(area, approval, "not_permitted", [e0])
    if zoning_barred_by:  # E0z
        return _row(
            area, approval, "not_permitted", [_not_as_described("entertainment.status/E0z", zoning_barred_by)]
        )
    if concept.entertainment_not_stated:  # the intake model read entertainment the text does not state
        status: ApprovalStatus = "insufficient_information"
        lines = [_say("entertainment.status/not_stated", status=_status_words(status))]
        if late:
            lines.append(_say("entertainment.status/E2", status=_status_words("further_review")))
        missing = [MISSING_PHRASES["entertainment_kind"]]
        return _row(
            area,
            approval,
            status,
            lines,
            referral=referral_steps(area, concept, rules_date=rules_date),
            missing=missing,
        )
    basis: list[RuleLine] = []
    if named:
        live = {
            str(r.extra.get("permit") or ""): r
            for r in _entries(ENTERTAINMENT_GROUP, rules_date, kind="approval_required")
            if r.in_force
        }
        entry = live.get(permits[0])
        basis.append(
            _say(
                "entertainment.permit/answered"
                if concept.by_answer("entertainment_kind")
                else "entertainment.permit",
                permit=ENTERTAINMENT_PERMIT_NAMES[permits[0]],
                code_section=entry.source.section if entry else None,
                source_url=entry.source.url if entry else None,
            )
        )
    key = (
        "entertainment.status/E1"
        if not late
        else "entertainment.status/E3"
        if permits
        else "entertainment.status/E2"
    )
    # until Ordinance 118-25 (the data's dates) a dance permit was an approval: the sentences that say dancing
    # needs no permit of its own are not used on those dates
    dance = DANCE_PERMIT in entertainment_approvals(rules_date)
    if dance and key != "entertainment.status/E2":
        key = f"{key}_dance_permit"
    if dance and concept.dancing:
        entry = next(
            (
                r
                for r in _entries(ENTERTAINMENT_GROUP, rules_date, kind="approval_required")
                if r.in_force and r.extra.get("permit") == DANCE_PERMIT
            ),
            None,
        )
        basis.append(
            _say(
                "entertainment.dance",
                date=_day(rules_date),
                code_section=entry.source.section if entry else None,
                source_url=entry.source.url if entry else None,
            )
        )
        if PLACE_OF_ENTERTAINMENT not in permits:
            approval = f"{approval}, and {DANCE_PERMIT_NAME}"
    basis.append(_say(key, status=_status_words("further_review")))
    if concept.closing.missing:
        basis.append(_say("entertainment.closing/missing"))
    steps = referral_steps(area, concept, rules_date=rules_date)
    return _row(area, approval, "further_review", basis, referral=steps)
