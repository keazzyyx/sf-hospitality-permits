"""The pathway, every row's status and the headline findings, decided by rules in code (rule table v2). No model
call is made here.

Same facts in, same answer out. The facts are: the concept profile, the zoning district at the address, the
special use districts and other overlays at the address, the records on file at the address itself, the census
tract of the address, and two dates. The writer model is shown the result and writes the explanation; it cannot
change the pathway, a status, a status note, the name of an approval or a change-of-use answer. The building row
is set from the same `ChangeAnswers` the pathway holds, so the two cannot disagree.

Spec: docs/validation/rule-table-extension-spec.md. This module is the entry point (`determine`). The pieces are
in four modules, each with its own binding docstring and its own table of fixed sentences:
  app.memo.facts     what the description and the records say (`ConceptFacts`, `SiteFacts`); a missing input
                     has no value and one fixed phrase (`MISSING_PHRASES`)
  app.memo.triggers  the eleven triggers T1 to T11 (spec section 1a), read from the dated control data
  app.memo.rows      the alcohol row, the three change-of-use answers, the building row, the entertainment
                     row and the referral steps (spec sections 3a and 4)
  app.memo.tracts    the census tract's licence concentration

THE RULES (binding; every rule has a stable `rule_id`, and every `RuleLine.text` is built from the fields of the
records or data entries the rule read plus the fixed text in the tables below, never from model text)

0. The dates. `rules_date` is the date whose rules apply: today for a live report, a past date in the backtest.
   Every control is read from the dated control data for that date, and a record at the address dated on or
   after it is not read (`facts.site_facts`). `today` is used only to say where the control on the rules date
   is not today's control (`TriggerFinding.differs_today`). `rules_date` defaults to `today`; `today` defaults
   to the current date, read once in `determine`, which is the only place the rules touch a clock.

1. Proposed use (`planning_use`), Planning Code § 102, from the kind of business:
   bar -> "bar"; restaurant -> "restaurant"; cafe that serves alcohol -> "restaurant"; cafe that does not ->
   "limited_restaurant"; anything else -> "not_covered". `facts.concept_facts` reads the concept's uses from
   this, adding Nighttime Entertainment where the description gives it. `Pathway.use` is the first of them.
   1a. The applicant's answers. Where the applicant answered "No alcohol" to the liquor licence intake question
   and the description mentioned alcohol (`BusinessProfile.no_alcohol_answer_over_description`, set only by
   app.memo.intake), the answer is the one read, and the pathway's first line says so ("intake.no_alcohol").
   1b. A bar that serves no alcohol is not a Bar (an owner decision, as the work order of 2026-11-16 relays it).
   Planning Code § 102 opens the definition: "Bar. A Retail Sales and Service Use that provides on-site alcoholic beverage sales for drinking
   on the premises". Where the applicant answered "No alcohol", or the description names the business in words
   that say it serves none ("a zero-proof cocktail bar": `BusinessProfile.no_alcohol_stated`, app.memo.stated),
   and nothing says it serves any (`not_a_bar`), the business type "bar" gives no use. No other use is assumed
   in its place: the kind of food or drink service is a missing input (`facts.MISSING_PHRASES["food_service"]`,
   asking whether it is a Restaurant, a Limited Restaurant or another use), T1 is not decided and names it, and
   the report asks it. The concept has no alcohol row (`required_areas` reads a Bar's alcohol from this rule). A
   bar the description does not say serves alcohol, and that answered nothing, is still a Bar: a Bar sells
   alcohol by its definition, so silence is never read as "no alcohol".
   The kind of food or drink service has an intake question since 2026-11-16 ("What kind of food or drink service
   is it?", app.memo.intake, id "food_service"; before it the report named the input and no question gave it).
   The answer "restaurant" or "limited_restaurant" is then the concept's use (`food_service_use`), read from the
   answer: the use line says "You answered ..." ("zoning.food_service"), the rules run for that use, and there is
   still no alcohol row (the concept serves none, and it is not a Bar). The answer "other" ("Other, or not sure")
   gives no use: the input stays not known and is named, and T1's line says what was answered. The answer is read
   only for a business described as a bar that serves no alcohol: for any other business the kind of business the
   description gives decides the use, and a line says the answer was not read ("zoning.food_service/not_read"),
   so no answer is dropped without a word.

2. The triggers. `triggers.evaluate` returns T1 to T11, always all eleven, each "principal", "conditional",
   "not_permitted", "not_decided" (it matters here and something is not known: `missing_inputs` names it),
   "does_not_apply" or "code_and_practice_differ". Spec section 1a and the docstring of app.memo.triggers say
   how each is read. `Pathway.triggers` carries all eleven.

3. Zoning and use row (spec section 4), from the eleven findings:
     Z-NP  any trigger not_permitted            -> not_permitted
     Z-S   else any trigger not_decided because no story is given (it names "which stories the business
           occupies")                          -> insufficient_information, as Z-ND, even where another trigger
                                                   is conditional; the status line then names that trigger too
                                                   (the user's decision of 2026-11-12: "MISSING STORY: always
                                                   'Insufficient information', naming it. Never default to the
                                                   first story.")
     Z-C   else any trigger conditional         -> further_review; the approval is the Conditional Use
                                                   Authorization, and the status line names every trigger that
                                                   asks for it (and every trigger still not decided)
     Z-ND  else any trigger not_decided         -> insufficient_information; `missing_inputs` holds each fixed
                                                   phrase once, in trigger order
     Z-D   else any code_and_practice_differ    -> further_review, status note "Code and Planning practice
                                                   differ"
     Z-A   else                                 -> allowed
   A missing input never becomes an assumption: Z-ND comes before Z-D and Z-A, and a missing story is never
   resolved by assuming one: Z-S comes before Z-C.
   The basis lists, in order: the use line; the lines of every trigger that is not "does_not_apply"; the lines
   of a trigger that does not apply, unless every one of them is in QUIET_LINES (nothing in the concept or at
   the address touches the trigger: no special use district, no existing business, no entertainment, no
   outdoor area, no earlier approval, the laundromat rule out of force), so a reader sees why a control was not
   applied (the use continues, the area is on the sidewalk) without ten lines that say nothing; the
   planning-use lines of rule 5; the status line.

4. The pathway.
   `permission` is the answer for a NEW use of this kind here: the most restrictive of T1 (the district's use
   control), T2 (a special use district's use control), T4 (the liquor licence rule of a restricted district,
   which the Code writes on the use's own row: Table 719 Note 3, Table 737 Note 7) and T11 (hours), and T6
   when the concept's first use is Nighttime Entertainment (T6 is the trigger that reads that use's cell).
   The other triggers (formula retail, use size, the outdoor area and the rest) are about how this business
   takes the use, not about the use, and are not part of it. When a business or a use continues at the address
   those triggers do not apply to it, so they are read again as for a new use
   (`triggers.evaluate(..., as_new=True)`); the rows are always set from the plain reading. not_permitted ->
   "not_permitted"; else one of them not decided because no story is given -> "not_covered" with the label
   NOT_DECIDED_LABEL (as Z-S); conditional -> "conditional"; principal or does_not_apply -> "principal"; not_decided or
   code_and_practice_differ -> "not_covered", with the label NOT_DECIDED_LABEL or the practice note (the value
   list has no word for either; the label says which). A concept with no use the rules read is "not_covered"
   with the contract's own label.
   `lines` are the rule 1a line (where there is one), the use line, the lines of those triggers as read for
   `permission`, and the planning-use lines of rule 5 (the change-of-use answer is the last line). `notes` are the notes on file for the district and
   its special use districts, verbatim; the rules read typed fields and the dated data, not that text.
   `existing_use` is the use an ACTIVE ABC licence at the report's own street address shows on the rules date
   (`existing_use` below; a licence type is one the use may hold under § 102, not proof of the use). At a
   rules date before today its sentences say the records read are the ones dated before that date.
   `change_of_use` is `changes.planning_use`.

5. Change of use is three answers (`rows.change_answers`, spec section 4): the Planning Code use, the
   Building Code occupancy, and neighbourhood notification on the rules date. Rule table v1's rule for the
   applicant's own flags is kept where neither the records nor a stated last use decide the first answer: the
   profile says new construction, or that the space was not a food or drink use -> "yes", and the line says
   "as described by the applicant". The profile's default change_of_use=False is never read as "no".

6. The other rows. One `RowDetermination` per area asked for, in report order.
   "The use itself is prohibited" means T1 or T2 is not_permitted (for the entertainment row also T6). A use
   that continues, or may continue, is not read by those triggers, and hours that are not permitted (T11),
   formula retail (T5), use size (T7) and the outdoor area (T9) never make it true.
   "A prohibited use" (`PROHIBITED_USE_TRIGGERS`) means the zoning row is not_permitted because T1, T2 or T5
   (formula retail) is not_permitted. Planning Code § 175(a) then reaches every later row (the user's decision
   of 2026-11-12: "a prohibited use, including the formula-retail prohibition, means no later approvals
   apply"): the alcohol row by A1z (§ 23790) even where an existing business continues, and the
   entertainment, health, building and outdoor rows by E0z, H0z, B0z and O0z, each not_permitted with a line
   that names what bars the concept. Where the use itself is prohibited, the rows keep v1's sentences (A1, E0,
   H0, B0), which name the use. A zoning row that is not permitted only for another reason (enlarging an
   existing business T3, a liquor licence rule of a restricted district T4, Nighttime Entertainment T6, use
   size T7, the laundromat rule T8, the outdoor area T9, earlier conditions T10, the hours T11) does not
   carry § 175(a) to the health, building, entertainment or outdoor rows; the alcohol row's A1z still applies
   to it where the existing use does not continue (spec section 4, as before the decision), T4 bars the
   licence by A1r, and the entertainment row reads T6 by E0.
   alcohol        `rows.alcohol_row` (rule 1 there): not_permitted where the use itself is prohibited (a new
                  use by definition, so that module's own test of a continuing use is not applied), where a
                  licence rule of a restricted district bars the licence, or where the zoning row is not
                  permitted for the concept as described and the existing use does not continue, or the
                  zoning row is not permitted by a prohibited use whether or not an existing use continues
                  (spec section 4, § 23790; the user's decision of 2026-11-12); insufficient_information naming
                  the licence type or how the licence is to be
                  obtained when either is missing (a concept that serves alcohol without saying what, alcohol_type
                  "unknown", has no licence type, and the row names "what alcohol will be served: beer and wine,
                  or spirits too" in its place; a stated licence type still decides it); potential_blocker for a requirement that could stop the
                  licence; allowed for a licence already held; otherwise further_review. An over-concentrated
                  census tract adds the note "public convenience or necessity finding likely required" to a
                  further_review row and never changes a status.
   entertainment  `rows.entertainment_row` (v1's E0 to E3).
   health         H0  the use itself is prohibited -> not_permitted (Planning Code § 175(a))
                  H0z otherwise, a prohibited use (formula retail) -> not_permitted (Planning Code § 175(a))
                  H1  otherwise                    -> allowed (plan check, inspection, permit to operate)
   building       `rows.building_row`, from the answers of rule 5: B0 not_permitted (the use itself is
                  prohibited and the Planning Code use is not shown to stay the same; before the decision of
                  2026-11-12 it needed a change of use), B0z not_permitted (otherwise, a prohibited use:
                  formula retail), B1 further_review (either answer is "yes"),
                  B2 allowed (both "no"), B3 insufficient_information naming what is missing.
   outdoor        O0z  a prohibited use (T1, T2, T5), and T9 is not itself not_permitted ->
                       not_permitted (Planning Code § 175(a)). Otherwise by T9 where the outdoor area is on the lot:
                  O-C   conditional    -> further_review (Conditional Use Authorization)
                  O-ND  not_decided    -> insufficient_information, naming the input
                  O-U   principal, but the description does not say where the area is -> insufficient_information,
                        naming where the outdoor area is (on the sidewalk it takes other approvals)
                  O-P   principal      -> allowed
                  O-NP  not_permitted  -> not_permitted
                  O1    T9 does not apply (the area is on the sidewalk, or the description says there is
                        none) -> further_review, as v1: the sidewalk and the parking lane take other approvals
                        the rules do not check.
   Referral steps (`rows.referral_steps`) are listed under the alcohol, entertainment, health and building rows.
   A referral step is not an approval: it never sets or changes a status, and a row that is not_permitted
   lists none.

7. What the rules could not establish (`open_questions`): one question per missing input, worded from its
   fixed phrase ("Not known: <phrase>. Needed for: <rows>."), each phrase once: first for every trigger that
   is not decided, also where the zoning row is further review (the answer could add a ground or bar the
   concept) but not where it is not permitted (no answer changes that); then for every row's
   `missing_inputs`. Then one question for Planning where the Code and Planning practice differ, and the
   last-legal-use question where "no change of use" rests on a licence type alone. A question for an input an
   optional intake question gives carries that question's id (`OpenQuestion.intake_question`,
   `intake_question_for`; change of 2026-11-15, approved with the release of 2026-11-16), so the report can say which
   question to answer: every input of `facts.MISSING_PHRASES` but the kind of business, the seats, the licences
   already held and the licence type itself has one, and so has the existing occupancy group, which no public
   record shows and the applicant can read off the plans or the certificate of occupancy. "The licence type" is
   named only where what is poured would not decide it (`ConceptFacts.licence_type_missing_name`). No question
   gives the type itself, so its question is read for the concept (`_intake_question`): the liquor licence
   question when alcohol is not established (the answer "No alcohol" settles it), the question on what is poured
   when alcohol is established and that decides the type, and none otherwise (a hotel or a caterer).
   7a. A fact the intake model filled that no quote from the text stated is cleared before the rules read it
   (app.memo.stated) and is not known: a row or trigger that needs it names it as above. A cleared reading that
   something is there (alcohol, entertainment, an outdoor area, a story: `ConceptFacts.cleared_readings`) is
   never read as "no": its row is added and is insufficient information (A0, the entertainment and outdoor
   rows' "not_stated" lines), T4 and T6 are not decided, and a story not stated is a missing story like any
   other (no story is assumed: rule 3, Z-S). Every such fact that none of them asks for is asked too ("Not
   known: <phrase>. The description does not state it, so the report does not assume it."), after the
   missing-input questions, so each one is named in the report. A cleared licence type the rules derive from
   what is poured is known and not asked; one they cannot derive is asked by `licence_type_missing_name`
   (`ConceptFacts.cleared_facts`).
   7b. "Fewer than 50 people" with 50 seats or more is not missing but in conflict: the building row names it,
   and its question says so in plain words ("Your answer says the space is for fewer than 50 people, but the
   description gives 120 seats. Which is right? ...", `OCCUPANTS_CONFLICT_QUESTION`), still pointing at the
   question "Is the space for fewer than 50 people?".

8. Overall status = the most severe row status, and never less severe than a definite headline finding of rule 9
   (change of 2026-11-16): a Conditional Use Authorization a trigger asks for makes it at least further_review
   even where the zoning row stays insufficient_information because no story is given (Z-S, which is
   unchanged: the user's decision of 2026-11-12 keeps that row "Insufficient information", naming the story).
   A contingent headline finding never raises it. The overall line and the entitlement path are composed from
   the rows by code; the overall line opens with one sentence per kind of headline finding (`OVERALL_LEAD`, the
   definite ones named together, each contingent one on its own with its condition), then counts the rows. The
   entitlement path lists only approvals to file: a row that is insufficient_information adds
   none (the rules do not know which approval it is), and the zoning, outdoor and alcohol entries are left out
   when those rows are allowed (nothing is filed with Planning; a licence already held files nothing with ABC). When any row is not_permitted the path is the
   sentence NO_PATH and lists no approval.

9. Headline findings (`headline_findings`, change of 2026-11-16): what changes the business's plans for this
   address is printed first in the report, ahead of the rows, whatever else is still not known. In order:
     H-NP  every trigger that is not_permitted ("Zoning does not permit the concept as described ..."), and
           nothing else: no answer changes that (a not_permitted trigger with `unsettled_by` is read as H-CIF);
     H-C   otherwise every trigger that is conditional, without `unsettled_by` ("The concept needs a Conditional
           Use Authorization, which the Planning Commission decides at a public hearing"). Where no story is given the sentence
           says the story is not known and that the rules cannot yet say whether zoning permits the use there at
           all; where another trigger is not decided it names it;
     H-CIF every contingent reading of a trigger that is not decided, or whose decided control an input not given
           could change (`TriggerFinding.contingent`, `unsettled_by`: app.memo.triggers, "Contingent readings",
           each checked by running the trigger again over every value the inputs can take): "If <condition>, the
           concept needs a Conditional Use Authorization ... Not known: <inputs>.", or "If <condition>, zoning
           does not permit the concept ...". It is never worded as definite, takes its row's own status, and its
           inputs are named in the open questions as before (rule 7). A conditional trigger with `unsettled_by`
           (T7 with the space's last use not given) gives no definite finding and does not raise rule 8.
   Each finding names the row that carries it (the outdoor row for T9 where that row is asked for, else the zoning
   row), its status (not_permitted, further_review, or the row's own for a contingent one), the trigger's first
   line that is not an aside and that line's section and records. No rule's outcome is changed by rule 9: the
   statuses of rules 3 and 6 are as before, and only the overall status of rule 8 reads the definite findings.

Citation ids used in `RuleLine.citations`: "zoning:<district>", "overlay:<overlay id>", "app:<application id>"
(the same ids `MemoRunner._build_citations` and the site history use).

Every fixed sentence and every code reference of this module that does not come from a record field is in the
tables at the top (`LEGAL_BASIS` first), so a reviewer can check each one in one place. app.memo.rows and
app.memo.triggers reuse some of these sentences and keep their own in `ROW_BASIS` and `TEXT`.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, NamedTuple

from precedent.models import Application, Overlay
from precedent.store.base import ZoningInfo

from app.memo.report import (
    SITE_READ_RADIUS_M,
    Site,
    SiteRecord,
    most_severe,
    parse_street_address,
    same_street_address,
    status_label,
)
from app.models.memo import (
    APPROVAL_AREA_LABELS,
    CHANGE_OF_USE_LABELS,
    PLANNING_USE_LABELS,
    STATUS_SEVERITY,
    USE_PERMISSION_LABELS,
    ApprovalArea,
    ApprovalStatus,
    ContingentReading,
    Determinations,
    HeadlineFinding,
    HeadlineKind,
    OpenQuestion,
    Pathway,
    PlanningUse,
    RowDetermination,
    RuleLine,
    TriggerFinding,
    UnknownNeeds,
    UsePermission,
)
from app.models.profile import BusinessProfile

if TYPE_CHECKING:  # these modules import this one; `determine` imports them when it runs
    from app.memo.facts import ConceptFacts


# ---- the fixed text and the code references (for legal review) ---------------------------------------
class Basis(NamedTuple):
    """One fixed sentence. `text` is a template: its {fields} are filled from record fields and from the label
    tables below, never from model text. `code_section` is the fixed reference the sentence rests on; None
    means the sentence takes its section from the record it read (a zoning or overlay row) or states no law."""

    text: str
    code_section: str | None = None
    source_url: str | None = None  # no link is on file for a fixed reference; a reviewer may add one here


_USE_DEFINITIONS = "Planning Code § 102"
# Rule 1b, the pieces of the line "zoning.food_service": what says the bar serves no alcohol (the description's own
# words, or the "No alcohol" answer), and what gave the use (the intake answer, or the request's own profile).
FOOD_SERVICE_LEAD: dict[bool, str] = {
    False: "The business is described as a bar that serves no alcohol",
    True: "The business is described as a bar, and you answered that it serves no alcohol",
}
FOOD_SERVICE_GIVEN: dict[bool, str] = {False: "The request gives it as", True: "You answered that it is"}
FOOD_SERVICE_ANSWERED: dict[str, str] = {
    "restaurant": "that it is a Restaurant",
    "limited_restaurant": "that it is a Limited Restaurant",
    "other": "that it is another kind of food or drink service, or that you are not sure",
}
# Planning Code § 175(a): no City permit or licence may authorize a use the Code prohibits (rules E0, H0, B0).
_NO_CITY_PERMIT_TEXT = (
    "Zoning does not permit a new {use} at this address, and no City department may issue a permit or licence "
    "that would authorize a use the Planning Code prohibits: {status}."
)
_NO_CITY_PERMIT_SECTION = "Planning Code § 175(a)"
# The same rule where what zoning bars is a prohibited use other than the use's own kind (formula retail, T5):
# rules H0z, B0z, E0z and O0z. {triggers} names what bars it, in the zoning row's own words.
_NOT_AS_DESCRIBED_TEXT = (
    "Zoning does not permit the concept as described at this address (what bars it: {triggers}), and no City "
    "department may issue a permit or licence that would authorize a use the Planning Code does not permit: "
    "{status}."
)
BUILDING_PERMIT_SECTION = "San Francisco Building Code § 106A.1; Planning Code § 175"
_CONDITIONAL_USE = "Planning Code § 303"

# Key = "<rule_id>" or "<rule_id>/<variant>". The part before the slash is the RuleLine.rule_id.
LEGAL_BASIS: dict[str, Basis] = {
    # rule 1a: the applicant's "No alcohol" answer to the liquor licence intake question wins over a description
    # that mentioned alcohol (app.memo.intake); the rules say so
    "intake.no_alcohol": Basis(
        'The applicant answered "No alcohol" to the liquor licence question. The description mentioned '
        "alcohol; the applicant's answer is the one the rules read, so the concept is read as serving no alcohol."
    ),
    # rule 1b: the applicant's answer on the kind of food or drink service of a bar that serves no alcohol.
    # {lead} is FOOD_SERVICE_LEAD (what says the bar serves no alcohol), {given} is FOOD_SERVICE_GIVEN (what gave
    # the use), {a_use} the use's label; {answer} is FOOD_SERVICE_ANSWERED
    "zoning.food_service": Basis(
        "{lead}, so it is not a Bar: Planning Code § 102 defines a Bar by its on-site alcoholic beverage sales. "
        "{given} {a_use}, and the rules read that use.",
        "Planning Code § 102 (Bar)",
    ),
    "zoning.food_service/not_read": Basis(
        "To the question on the kind of food or drink service, you answered {answer}. That question is read only "
        "for a business described as a bar that serves no alcohol, which is not a Bar; the rules read the use "
        "from the kind of business the description gives."
    ),
    # rule 1: the proposed use
    "zoning.use": Basis("The concept is looked up as {a_use} (Planning Code § 102).", _USE_DEFINITIONS),
    "zoning.use/several": Basis(
        "The concept is looked up as these uses: {uses} (Planning Code § 102).", _USE_DEFINITIONS
    ),
    # A district the dated data does not carry: app.memo.triggers reads Bar and Restaurant from the zoning
    # control table on file with these three sentences ({section} comes from the zoning or overlay record).
    "zoning.use_control": Basis("Zoning district {district}: {a_use} is {control}{section}."),
    "zoning.sud_control": Basis("{name}: {a_use} is {control}{section}."),
    "zoning.sud_control/not_applied": Basis(
        "{name}: not applied, because the concept serves no alcohol{section}."
    ),
    "zoning.sud_control/not_stated": Basis(
        "{name}: not applied, because the description does not state whether alcohol will be served{section}."
    ),
    # rule 4: existing use (§ 102 lists the ABC licence types a Bar or a Restaurant may hold; the type is read as
    # the use, and the line says that is a reading)
    "zoning.existing_use": Basis(
        "An active ABC Type {type} licence ({type_label}) is on file at {address}. That is a licence type "
        "{a_use} holds (Planning Code § 102), so the rules read the space as {a_use}; other uses can hold it "
        "too.",
        _USE_DEFINITIONS,
    ),
    "zoning.existing_use/one_of_both": Basis(
        "An active ABC Type {type} licence ({type_label}) is on file at {address}.", _USE_DEFINITIONS
    ),
    "zoning.existing_use/both": Basis(
        "Active licences for both a Restaurant and a Bar are on file at {address}, so the records do not "
        "establish one existing use.",
        _USE_DEFINITIONS,
    ),
    "zoning.existing_use/none": Basis(
        "No active ABC licence of a type the rules read (Types {types}) is on file at {address}, so the records "
        "do not show what the space is used as now."
    ),
    "zoning.existing_use/no_address": Basis(
        "The report's address could not be read as a street address, so no licence could be tied to it and "
        "the records do not show what the space is used as now."
    ),
    # the same, at a past rules date: the records read are the ones dated before it
    "zoning.existing_use/dated": Basis(
        "An active ABC Type {type} licence ({type_label}) dated before {date} is on file at {address}. That is a "
        "licence type {a_use} holds (Planning Code § 102), so the rules read the space on {date} as {a_use}; "
        "other uses can hold it too.",
        _USE_DEFINITIONS,
    ),
    "zoning.existing_use/one_of_both_dated": Basis(
        "An active ABC Type {type} licence ({type_label}) dated before {date} is on file at {address}.",
        _USE_DEFINITIONS,
    ),
    "zoning.existing_use/both_dated": Basis(
        "Active licences dated before {date} for both a Restaurant and a Bar are on file at {address}, so the "
        "records do not establish one existing use on that date.",
        _USE_DEFINITIONS,
    ),
    "zoning.existing_use/none_dated": Basis(
        "No active ABC licence of a type the rules read (Types {types}) dated before {date} is on file at "
        "{address}; records dated on or after {date} were not read, so the records do not show what the space "
        "was used as on that date."
    ),
    "zoning.existing_use/no_address_dated": Basis(
        "The report's address could not be read as a street address, so no licence could be tied to it and "
        "the records do not show what the space was used as on {date}."
    ),
    # rule 5: change of use, where the licence records or the applicant's own flags decide it (app.memo.rows
    # writes these lines; its other change-of-use sentences are in rows.ROW_BASIS)
    "zoning.change_of_use/no": Basis(
        "The rules read the space as {a_use} from its licence type. If it is in fact {a_use}, {a_use} here is "
        "not a change of use.",
        _USE_DEFINITIONS,
    ),
    "zoning.change_of_use/yes": Basis("{existing} to {use} is a change of use.", _USE_DEFINITIONS),
    "zoning.change_of_use/new_construction": Basis(
        "The project is new construction, as described by the applicant, so the use is new to the site: a "
        "change of use."
    ),
    "zoning.change_of_use/applicant": Basis(
        "The space was not a food or drink use, as described by the applicant, so {a_use} here is a change of "
        "use."
    ),
    # rule 3: zoning row ({triggers} and {undecided} are trigger labels from the contract's TRIGGER_LABELS;
    # {missing} are the fixed phrases the findings name; the section printed is the deciding line's own)
    "zoning.status/not_permitted": Basis(
        "Zoning does not permit the concept as described at this address. What bars it: {triggers}: {status}."
    ),
    "zoning.status/conditional": Basis(
        "The concept as described needs a Conditional Use Authorization here. What asks for one: {triggers}: "
        "{status}.",
        _CONDITIONAL_USE,
    ),
    "zoning.status/conditional_and_undecided": Basis(
        "The concept as described needs a Conditional Use Authorization here. What asks for one: {triggers}. "
        "Not decided as well: {undecided}; the lines above name what is missing: {status}.",
        _CONDITIONAL_USE,
    ),
    "zoning.status/not_decided": Basis(
        "The rules could not decide: {triggers}. What is missing: {missing}. Until that is known the rules "
        "cannot say what zoning asks of the concept: {status}."
    ),
    # Z-S: no story is given and another trigger asks for a Conditional Use; no story is assumed
    "zoning.status/not_decided_story": Basis(
        "The rules could not decide: {triggers}. What is missing: {missing}. No story is assumed, so until that "
        "is known the rules cannot say what zoning asks of the concept, although {conditional} already asks for a "
        "Conditional Use Authorization: {status}."
    ),
    "zoning.status/practice_differs": Basis(
        "The Planning Code text and San Francisco Planning's own records differ here ({triggers}). Ask San "
        "Francisco Planning which it applies: {status} ({note})."
    ),
    "zoning.status/allowed": Basis(
        "Of the reasons the rules check for a Conditional Use Authorization (the lines above), none applies "
        "here and none bars the concept as described: {status}."
    ),
    # rule 6: alcohol row (app.memo.rows writes these lines; its other alcohol sentences are in ROW_BASIS)
    "alcohol.status/A1": Basis(
        "Zoning does not permit a new {use} at this address, and ABC may not issue a retail licence where using "
        "the licence would be contrary to zoning: {status}.",
        "California Business and Professions Code § 23790",
    ),
    "alcohol.county_limit": Basis(
        "A Type {type} licence is an on-sale general licence. State law limits these to one for each 2,000 "
        "inhabitants of the county; in a county over that number ABC issues no additional one, so the licence "
        "comes by transfer of an existing licence unless state law allows otherwise.",
        "California Business and Professions Code § 23816",
    ),
    "alcohol.status/A2": Basis("The licence can be used here only if that condition is met: {status}."),
    "alcohol.status/A3": Basis(
        "ABC investigates every licence application, and the applicant must post public notice, before a "
        "licence is issued: {status}.",
        "California Business and Professions Code §§ 23958 (investigation) and 23985 (public notice)",
    ),
    # rule 6: entertainment row (app.memo.rows writes these lines)
    "entertainment.status/E0": Basis(_NO_CITY_PERMIT_TEXT, _NO_CITY_PERMIT_SECTION),
    "entertainment.status/E0z": Basis(_NOT_AS_DESCRIBED_TEXT, _NO_CITY_PERMIT_SECTION),
    "entertainment.status/E1": Basis(
        "A live performance, a DJ or karaoke needs a Place of Entertainment or Limited Live Performance permit "
        "(one performer without amplification who ends by 10 p.m. needs none). Regular amplified sound outdoors "
        "needs a Fixed Place Outdoor Amplified Sound permit. The Entertainment Commission holds a public hearing "
        "on each application. Recorded music indoors with no performer needs no entertainment permit, and dancing "
        "by patrons needs no permit of its own. Where a permit is needed: {status}.",
        "San Francisco Police Code § 1060 et seq. (Place of Entertainment; Limited Live Performance; Fixed Place "
        "Outdoor Amplified Sound)",
    ),
    # E1 and E3 while the dance permit was an approval (Police Code § 1023, to 2025-08-16 in the data)
    "entertainment.status/E1_dance_permit": Basis(
        "A live performance, a DJ or karaoke needs a Place of Entertainment or Limited Live Performance permit "
        "(one performer without amplification who ends by 10 p.m. needs none). Regular amplified sound outdoors "
        "needs a Fixed Place Outdoor Amplified Sound permit. The Entertainment Commission holds a public hearing "
        "on each application. Recorded music indoors with no performer needs no entertainment permit. Where a "
        "permit is needed: {status}.",
        "San Francisco Police Code § 1060 et seq. (Place of Entertainment; Limited Live Performance; Fixed Place "
        "Outdoor Amplified Sound)",
    ),
    "entertainment.status/E3_dance_permit": Basis(
        "A live performance, a DJ or karaoke needs a Place of Entertainment or Limited Live Performance permit, "
        "and regular amplified sound outdoors needs a Fixed Place Outdoor Amplified Sound permit; recorded music "
        "indoors with no performer needs no permit of its own. Staying open to patrons between 2 a.m. and 6 a.m. "
        "needs an Extended-Hours Premises permit as well, and entertainment between 2 a.m. and 6 a.m. needs a "
        "Place of Entertainment permit, not a Limited Live Performance permit: {status}.",
        "San Francisco Police Code § 1060 et seq. (Place of Entertainment; Limited Live Performance; Fixed Place "
        "Outdoor Amplified Sound), § 1060.1(a) and § 1070 et seq. (Extended-Hours Premises)",
    ),
    # the intake model read entertainment the description does not state (app.memo.stated)
    "entertainment.status/not_stated": Basis(
        "The description does not state whether there will be entertainment (live music, a DJ, karaoke or "
        "dancing), so the rules do not say which entertainment permit applies: {status}."
    ),
    "entertainment.status/E2": Basis(
        "Staying open to patrons between 2 a.m. and 6 a.m. needs an Extended-Hours Premises permit from the "
        "Entertainment Commission, with or without entertainment: {status}.",
        "San Francisco Police Code § 1070 et seq. (Extended-Hours Premises)",
    ),
    "entertainment.status/E3": Basis(
        "A live performance, a DJ or karaoke needs a Place of Entertainment or Limited Live Performance permit, "
        "and regular amplified sound outdoors needs a Fixed Place Outdoor Amplified Sound permit; recorded music "
        "indoors with no performer and dancing by patrons need no permit of their own. Staying open to patrons "
        "between 2 a.m. and 6 a.m. needs an Extended-Hours Premises permit as well, and entertainment between "
        "2 a.m. and 6 a.m. needs a Place of Entertainment permit, not a Limited Live Performance permit: "
        "{status}.",
        "San Francisco Police Code § 1060 et seq. (Place of Entertainment; Limited Live Performance; Fixed Place "
        "Outdoor Amplified Sound), § 1060.1(a) and § 1070 et seq. (Extended-Hours Premises)",
    ),
    # rule 6: health row
    "health.status/H0": Basis(_NO_CITY_PERMIT_TEXT, _NO_CITY_PERMIT_SECTION),
    "health.status/H0z": Basis(_NOT_AS_DESCRIBED_TEXT, _NO_CITY_PERMIT_SECTION),
    "health.status/H1": Basis(
        "A food or drink business needs a health permit to operate, which is issued after plan check and "
        "inspection without a hearing: {status}.",
        "California Retail Food Code §§ 114380–114381; San Francisco Health Code Article 8",
    ),
    # rule 6: building row (app.memo.rows writes these lines; B3 and the occupancy sentences are in ROW_BASIS)
    "building.status/B0": Basis(_NO_CITY_PERMIT_TEXT, _NO_CITY_PERMIT_SECTION),
    "building.status/B0z": Basis(_NOT_AS_DESCRIBED_TEXT, _NO_CITY_PERMIT_SECTION),
    "building.status/B1": Basis(
        "A change of use needs a building permit, and the permit must conform to the Planning Code before it "
        "is issued: {status}.",
        BUILDING_PERMIT_SECTION,
    ),
    # § 106A.1 opens "Except as specified in Section 106A.2", which lists work that needs no permit
    "building.status/B2": Basis(
        "The use does not change, so a building permit is needed only for building work that is not exempt, "
        "and it is a permit without a change of use: {status}.",
        "San Francisco Building Code §§ 106A.1 and 106A.2; Planning Code § 175",
    ),
    # rule 6: outdoor row. O1 is v1's sentence, for the sidewalk and for an area the description does not place.
    # § 145.2 and § 202.2(a)(7) cover Neighborhood Commercial districts only; elsewhere the district's own
    # control table governs. Sidewalk tables and chairs rest on Public Works Code Article 5.2, not Chapter 94A.
    "outdoor.status/O1": Basis(
        "Outdoor seating on private property is an Outdoor Activity Area under the district's zoning controls, "
        "which is principally permitted in some locations and a conditional use in others. Tables and chairs on "
        "the sidewalk are registered with Public Works. A Shared Spaces permit, on the sidewalk or for a parklet "
        "in the parking lane, is issued by Public Works, and the parking lane also needs approval from the "
        "SFMTA. The rules did not check which of these applies: {status}.",
        "Planning Code § 102 (Outdoor Activity Area) and the district's zoning control table (§ 145.2 and "
        "§ 202.2(a)(7) in Neighborhood Commercial districts); San Francisco Public Works Code Article 5.2 (café "
        "tables and chairs); San Francisco Administrative Code Chapter 94A and Public Works Code § 793 et seq. "
        "(Shared Spaces)",
    ),
    # the outdoor area is on the lot: the status follows the outdoor activity area trigger (T9), whose own
    # lines come first and carry the district's section
    "outdoor.status/conditional": Basis(
        "The outdoor activity area as described is a conditional use here, so it needs a Conditional Use "
        "Authorization: {status}.",
        _CONDITIONAL_USE,
    ),
    "outdoor.status/not_decided": Basis(
        "The rules cannot say whether the outdoor activity area needs a Conditional Use Authorization without "
        "{missing}: {status}."
    ),
    "outdoor.status/principal": Basis(
        "The outdoor activity area as described is principally permitted here, so it needs no Conditional Use "
        "Authorization: {status}."
    ),
    "outdoor.status/not_permitted": Basis(
        "The outdoor activity area as described is not permitted here: {status}."
    ),
    # the same three where the place of the outdoor area is the applicant's intake answer
    "outdoor.status/conditional/answered": Basis(
        "The outdoor activity area, where you answered it is, is a conditional use here, so it needs a "
        "Conditional Use Authorization: {status}.",
        _CONDITIONAL_USE,
    ),
    "outdoor.status/principal/answered": Basis(
        "The outdoor activity area, where you answered it is, is principally permitted here, so it needs no "
        "Conditional Use Authorization: {status}."
    ),
    "outdoor.status/not_permitted/answered": Basis(
        "The outdoor activity area, where you answered it is, is not permitted here: {status}."
    ),
    # O0z: zoning bars the concept as described for another reason; Planning Code § 175(a) reaches the outdoor
    # approvals too (Public Works and SFMTA are City departments)
    "outdoor.status/O0z": Basis(_NOT_AS_DESCRIBED_TEXT, _NO_CITY_PERMIT_SECTION),
    # O-U: the zoning trigger is principal on the lot, and the description does not place the area
    # the intake model read an outdoor area the description does not state (app.memo.stated)
    "outdoor.status/not_stated": Basis(
        "The description does not state whether there will be an outdoor area, so the rules do not say which "
        "outdoor approval applies: {status}."
    ),
    "outdoor.status/unplaced": Basis(
        "The description does not say where the outdoor area is. On the lot it is principally permitted here; "
        "on the sidewalk or in the parking lane it needs a Public Works registration or a Shared Spaces permit "
        "instead: {status}.",
        "Planning Code § 145.2 and the district's zoning control table; San Francisco Public Works Code Article "
        "5.2 (café tables and chairs); San Francisco Administrative Code Chapter 94A (Shared Spaces)",
    ),
    # notes: text on file that the rules do not read ({rules} is the record's own text, verbatim)
    "zoning.note": Basis("Note on file, not evaluated by the rules: {rules}"),
}
NOTE_PREFIX = "Note on file, not evaluated by the rules:"

# What the rules could not establish: key -> (question, who or which document settles it).
OPEN_QUESTIONS: dict[str, tuple[str, str]] = {
    "last_legal_use": (
        "What was the last legal use of the space at {address}?",
        "Planning's Property Information Map, or a Letter of Determination from San Francisco Planning",
    ),
    "use_permitted": (
        "Is {a_use} permitted at {address}, and under which approval?",
        "A written answer from San Francisco Planning, such as a Letter of Determination",
    ),
}
# Rule 7: one question per missing input. {phrase} is the fixed phrase the rule named (facts.MISSING_PHRASES,
# triggers.NOT_KNOWN or rows.EXISTING_GROUP_PHRASE); {rows} are the report's own row labels.
MISSING_INPUT_QUESTION = "Not known: {phrase}. Needed for: {rows}."
# Rule 7a: a fact the intake model filled but the description does not state (app.memo.stated), that no row or
# trigger asks for.
NOT_STATED_QUESTION = (
    "Not known: {phrase}. The description does not state it, so the report does not assume it."
)
# Rule 7b: "fewer than 50 people" against a seat count of 50 or more (the building row names whether the space is
# for fewer than 50 people: neither is read over the other). The question names the conflict, by whether the
# applicant's intake answer or the description gave "fewer than 50 people", instead of asking it as unanswered.
OCCUPANTS_CONFLICT_QUESTION: dict[bool, str] = {
    True: (
        "Your answer says the space is for fewer than 50 people, but the description gives {seats} seats. Which "
        "is right? Needed for: {rows}."
    ),
    False: (
        "The description says the space is for fewer than 50 people, but it also gives {seats} seats. Which is "
        "right? Needed for: {rows}."
    ),
}
# OpenQuestion.question holds this many characters. A phrase too long for it is cut and ends with "…", so the
# question still says which rows need the input.
QUESTION_MAX = 300
# Who settles a missing input, by what kind of thing it is: (OpenQuestion.needs, OpenQuestion.ask).
MISSING_INPUT_ASKS: dict[str, tuple[UnknownNeeds, str]] = {
    # an input the project description can give (a phrase of facts.MISSING_PHRASES)
    "description": ("applicant_history", "The applicant: the project description does not say"),
    # the existing occupancy group (rows.EXISTING_GROUP_PHRASE)
    "plans": ("plans", "Plans or a code analysis of the existing space"),
    # anything else the rules could not place or read (a phrase of triggers.NOT_KNOWN)
    "agency": (
        "agency_answer",
        "A written answer from San Francisco Planning, such as a Letter of Determination",
    ),
}
# The inputs of facts.MISSING_PHRASES that a public source can also settle: fact name -> who.
MISSING_INPUT_ASK_FOR: dict[str, str] = {
    "existing_use_stated": "The applicant, or Planning's Property Information Map",
}


class LicenceType(NamedTuple):
    label: str  # ABC's name for the type, in plain words
    shows: PlanningUse  # the use an ACTIVE licence of this type shows at an address (rule 4)


# ABC on-sale licence types the rules read. Any other type establishes nothing.
LICENCE_TYPES: dict[str, LicenceType] = {
    "41": LicenceType("on-sale beer and wine, eating place", "restaurant"),
    "42": LicenceType("on-sale beer and wine, public premises", "bar"),
    "47": LicenceType("on-sale general, eating place", "restaurant"),
    "48": LicenceType("on-sale general, public premises", "bar"),
    "61": LicenceType("on-sale beer, public premises", "bar"),
    "75": LicenceType("on-sale general, brewpub", "restaurant"),
}
# The licence a new concept applies for: (proposed use, what it pours) -> ABC type (facts derives the licence
# type from it when the description states none).
LICENCE_FOR_CONCEPT: dict[tuple[str, str], str] = {
    ("bar", "beer_wine"): "42",
    ("bar", "full_liquor"): "48",
    ("restaurant", "beer_wine"): "41",
    ("restaurant", "full_liquor"): "47",
}
# On-sale general licence types, limited in number per county (B&P § 23816).
COUNTY_LIMITED_TYPES: frozenset[str] = frozenset({"47", "48"})


@dataclass(frozen=True)
class SubareaRule:
    """A control that applies in only part of one overlay, where the overlay on file does not show which part
    an address is in. The overlay's own flat control for the use is then not counted when app.memo.triggers
    reads a district the dated data does not carry; the dated rule of the special district decides (T2)."""

    overlay_section: str  # applies inside an overlay whose code_section names this section number
    uses: frozenset[str]  # the proposed uses it applies to


SUBAREA_RULES: tuple[SubareaRule, ...] = (
    SubareaRule(
        overlay_section="249.60",  # Mission Alcoholic Beverage Special Use District, subsection (f)(1)
        uses=frozenset({"restaurant"}),
    ),
)

AGENCIES: dict[str, str] = {
    "zoning_use": "San Francisco Planning",
    "alcohol": "California Department of Alcoholic Beverage Control",
    "entertainment": "San Francisco Entertainment Commission",
    "health": "San Francisco Department of Public Health",
    "building_change_of_use": "San Francisco Department of Building Inspection",
    "outdoor": "San Francisco Planning, Public Works and the SFMTA",
}
ZONING_APPROVALS: dict[str, str] = {
    "conditional": "Conditional Use Authorization (Planning Code § 303)",
    "principal": "Principally permitted use: no Conditional Use Authorization for the use itself",
    "existing": "No new use authorization: the existing use continues",
    "not_permitted": "Not permitted at this address",
    "not_covered": "Use authorization (not covered by the rule table)",
    "not_decided": "Use authorization (not decided: an input is missing)",
    "practice_differs": "Conditional Use Authorization (Planning Code § 303), unless Planning confirms none is needed",
}
# Pathway.permission_label where the value is "not_covered" because a trigger is not decided (rule 4). Where
# the Code and Planning practice differ the label is the practice note of app.memo.triggers.
NOT_DECIDED_LABEL = "Not decided by the rules"
APPROVALS: dict[str, str] = {
    "alcohol": "ABC licence",  # with the type when the rules know it, see `rows.alcohol_approval`
    "entertainment": "Place of Entertainment, Limited Live Performance or Fixed Place Outdoor Amplified Sound permit",
    "entertainment/extended_hours": "Extended-Hours Premises permit",
    "entertainment/with_extended_hours": (
        "Place of Entertainment, Limited Live Performance or Fixed Place Outdoor Amplified Sound permit, and "
        "Extended-Hours Premises permit"
    ),
    "health": "Health permit to operate",
    "building_change_of_use": "Building permit",
    "building_change_of_use/yes": "Building permit with change of use",
    "outdoor": "Outdoor activity area, sidewalk tables and chairs registration or Shared Spaces permit",
    "outdoor/conditional": "Conditional Use Authorization for the outdoor activity area (Planning Code § 303)",
    "outdoor/principal": "Outdoor activity area: principally permitted",
    "outdoor/not_permitted": "Outdoor activity area: not permitted as described",
}
# Rule 9, the headline findings: one sentence per finding, by its kind (`HeadlineFinding.kind`) and, for a definite
# Conditional Use, by what else the zoning row has not decided. {trigger} and {undecided} are trigger labels from
# the contract's TRIGGER_LABELS; {condition} is a contingent reading's condition; {missing} the inputs it turns on.
# A Conditional Use Authorization is heard and decided by the Planning Commission (Planning Code § 303).
_CONDITIONAL_USE_HEARING = (
    "a Conditional Use Authorization, which the Planning Commission decides at a public hearing (Planning Code "
    "§ 303)"
)
HEADLINE_TEXT: dict[str, str] = {
    "not_permitted": "Zoning does not permit the concept as described at this address. What bars it: {trigger}.",
    "conditional": f"The concept needs {_CONDITIONAL_USE_HEARING}. What asks for one: {{trigger}}.",
    # the zoning row is Z-S: no story is assumed, so the row stays insufficient information
    "conditional/story": (
        f"Whatever the story, the concept needs {_CONDITIONAL_USE_HEARING}. What asks for one: {{trigger}}. Which "
        "stories the business occupies is not known, so the rules cannot yet say whether zoning permits the use "
        "there at all."
    ),
    "conditional/undecided": (
        f"The concept needs {_CONDITIONAL_USE_HEARING}. What asks for one: {{trigger}}. Not decided as well: "
        "{undecided}; the report names what is missing."
    ),
    "conditional_if": (
        f"If {{condition}}, the concept needs {_CONDITIONAL_USE_HEARING}. What would ask for one: {{trigger}}. "
        "Not known: {missing}."
    ),
    "not_permitted_if": (
        "If {condition}, zoning does not permit the concept as described at this address. What would bar it: "
        "{trigger}. Not known: {missing}."
    ),
}
# Rule 8: the sentence the overall line opens with, one per kind of headline finding ({triggers}: the labels of
# every finding of that kind, in trigger order; a contingent finding gets its own sentence).
OVERALL_LEAD: dict[str, str] = {
    "not_permitted": "Zoning does not permit the concept as described here ({triggers}).",
    "conditional": "A Conditional Use Authorization is needed ({triggers}).",
    "conditional_if": "A Conditional Use Authorization is needed if {condition} ({triggers}).",
    "not_permitted_if": "Zoning does not permit the concept if {condition} ({triggers}).",
}
# Rule 9: a trigger line that is an aside (the control changed since, a Historic Buildings passage, a date before
# the data starts) is never the line a headline finding rests on.
_ASIDE_SUFFIXES: tuple[str, ...] = (".differs", ".historic", ".before_start")
# Rule 9: the row that carries a trigger's headline finding, where it is not the zoning row (when that row is
# asked for).
HEADLINE_AREA: dict[str, ApprovalArea] = {"T9": "outdoor"}  # the outdoor activity area

# Rule 8, the entitlement path: what it says when there is nothing to list.
NO_PATH = "No approval path: zoning does not permit the concept as described at this address."
NOTHING_TO_FILE = "No approval to file."
# Rule 8: rows where "allowed" means nothing is filed (the use, or the outdoor area, is principally permitted; the
# licence is already held).
NOTHING_FILED_WHEN_ALLOWED: frozenset[str] = frozenset({"zoning_use", "outdoor", "alcohol"})
CONTROL_PHRASES: dict[str, str] = {
    "principal": "principally permitted",
    "conditional": "a conditional use",
    "prohibited": "not permitted",
}
CLOSING_PHRASES: dict[str, str] = {
    "after_2am": "closing after 2 a.m.",
    "after_midnight": "closing after midnight",
}
# The hour, in minutes after midnight, at which the hours control is read for a closing time the profile gives
# only as "after midnight" or "after 2 a.m." (facts.Closing).
READ_AT: dict[str, int] = {"after_2am": 3 * 60, "after_midnight": 1 * 60}
# The contract's PLANNING_USE_LABELS has no entry for "nighttime_entertainment"; the label is § 102's.
USE_LABELS: dict[str, str] = {**PLANNING_USE_LABELS, "nighttime_entertainment": "Nighttime Entertainment"}
# "a Bar", "a Restaurant"; Nighttime Entertainment takes no article.
A_USE: dict[str, str] = {
    "bar": "a Bar",
    "restaurant": "a Restaurant",
    "limited_restaurant": "a Limited Restaurant",
    "nighttime_entertainment": "Nighttime Entertainment",
    "not_covered": "the proposed use",
}
# Rule 4: the triggers that give the control for a new use (`Pathway.permission`): the district's use control,
# the use control and the liquor licence rule of a special use district, and the hours. T6 joins them when the
# concept's first use is Nighttime Entertainment.
PERMISSION_TRIGGERS: tuple[str, ...] = ("T1", "T2", "T4", "T11")
ENTERTAINMENT_TRIGGER = "T6"
OUTDOOR_TRIGGER = "T9"
# Rule 6: the triggers that say the use itself is prohibited (Planning Code § 175(a) then reaches every City
# permit); the entertainment row also reads T6.
USE_TRIGGERS: tuple[str, ...] = ("T1", "T2")
# Rule 6: the prohibitions that carry Planning Code § 175(a) to every later row (the user's decision of
# 2026-11-12: "a prohibited use, including the formula-retail prohibition, means no later approvals apply"):
# the use itself and formula retail. The other triggers that can make the zoning row not permitted (T3, T4, T6,
# T7, T8, T9, T10, T11) are controls on how or where a permitted use operates, and are left out.
PROHIBITED_USE_TRIGGERS: frozenset[str] = frozenset({*USE_TRIGGERS, "T5"})
# Rule 3: the line a trigger writes when nothing in the concept or at the address touches it. A trigger that
# does not apply is left out of the zoning row and of `Pathway.lines` when all its lines are among these.
QUIET_LINES: frozenset[str] = frozenset(
    {
        "T2.none",  # no special use district at the address carries a use control
        "T3.none",  # no existing business stays
        "T4.none",  # no special use district at the address carries a liquor licence rule
        "T6.none",  # no entertainment is described
        "T8.no_data",  # the rule table holds no laundromat rule
        "T8.outside",  # the laundromat rule was not in force on the rules date
        "T9.none",  # no outdoor area is described
        "T10.none",  # no earlier approval is said to change
    }
)
# ... except that the laundromat line is printed when the description says the space was a laundromat.
LAUNDROMAT_LINE = "T8.outside"

_REPORT_ORDER: tuple[ApprovalArea, ...] = (
    "zoning_use",
    "alcohol",
    "entertainment",
    "health",
    "building_change_of_use",
    "outdoor",
)
_RESTRICTION: dict[str, int] = {"principal": 0, "conditional": 1, "prohibited": 2}
_DISTRICT_KINDS = frozenset({"zoning_district", "nc_rule"})
_NOTE_KINDS = frozenset({"alcohol_sud", "nc_rule", "special_use_district"})

ClosingBucket = Literal["after_2am", "after_midnight", "by_midnight"]
HoursPermission = Literal["P", "C", "NP"]


# ---- small helpers ------------------------------------------------------------------------------------
def _line(
    key: str,
    *,
    citations: Iterable[str] = (),
    code_section: str | None = None,
    source_url: str | None = None,
    **fields: str,
) -> RuleLine:
    """One rule line from its LEGAL_BASIS sentence. `code_section` and `source_url` are the record's own, used
    when the sentence carries no fixed reference; `fields` fill the sentence."""
    basis = LEGAL_BASIS[key]
    return RuleLine(
        rule_id=key.split("/", 1)[0],
        text=basis.text.format(**fields),
        code_section=basis.code_section if basis.code_section is not None else (code_section or None),
        source_url=basis.source_url if basis.source_url is not None else (source_url or None),
        citations=sorted(set(citations)),
    )


def _merge(lines: Iterable[RuleLine]) -> list[RuleLine]:
    """The lines in order, each sentence once; a repeated sentence keeps its first place and gains the later
    one's citations."""
    out: dict[tuple[str, str], RuleLine] = {}
    for line in lines:
        key = (line.rule_id, line.text)
        if key in out:
            first = out[key]
            out[key] = first.model_copy(update={"citations": sorted({*first.citations, *line.citations})})
        else:
            out[key] = line
    return list(out.values())


def _status_words(status: str) -> str:
    """'further_review' -> 'further review'."""
    return status_label(status).lower()


def _a(use: str) -> str:
    """'a Bar', 'a Restaurant', 'a Limited Restaurant', 'Nighttime Entertainment'; 'the proposed use' when the
    table does not cover it."""
    return A_USE[use]


def _and(parts: Sequence[str]) -> str:
    """'A', 'A and B', 'A, B and C'."""
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


def _short_section(code_section: str | None) -> str | None:
    """'Planning Code § 762 (Zoning Control Table 762); § 102 (Bar, Restaurant)' -> 'Planning Code § 762'."""
    head = re.split(r"\s*[;(]", code_section or "", maxsplit=1)[0].strip()
    return head or None


def _in_brackets(section: str | None) -> str:
    return f" ({section})" if section else ""


def _serves_alcohol(profile: BusinessProfile) -> bool:
    """The same test `required_areas` uses for the alcohol row."""
    return profile.serves_alcohol or profile.alcohol_type != "none"


def _sorted_overlays(overlays: Iterable[Overlay]) -> list[Overlay]:
    """Each overlay id once, in id order, whatever order the store returned them in."""
    by_id: dict[str, Overlay] = {}
    for o in sorted(overlays, key=lambda o: (o.id, o.model_dump_json())):
        by_id.setdefault(o.id, o)
    return list(by_id.values())


def _sorted_records(records: Iterable[SiteRecord]) -> list[SiteRecord]:
    """Each record id once, in id order, whatever order they were passed in."""
    by_id: dict[str, SiteRecord] = {}
    for r in sorted(records, key=lambda r: (r.app.id, r.distance_m, r.matched, r.app.model_dump_json())):
        by_id.setdefault(r.app.id, r)
    return list(by_id.values())


def _address(site: Site) -> str:
    return site.address or "this address"


def _day(value: dt.date) -> dt.date:
    return value.date() if isinstance(value, dt.datetime) else value


# ---- rule 1: the proposed use -------------------------------------------------------------------------
def stated_no_alcohol(profile: BusinessProfile) -> bool:
    """Rule 1b: the applicant answered "No alcohol" (the answer set serves_alcohol, to false), or the description
    states the business serves no alcohol (`BusinessProfile.no_alcohol_stated`), and nothing else says it serves
    any. A false serves_alcohol alone is not this: it is also what "not stated" leaves."""
    if _serves_alcohol(profile):
        return False
    return profile.no_alcohol_stated or "serves_alcohol" in profile.intake_answered


def not_a_bar(profile: BusinessProfile) -> bool:
    """Rule 1b: a business described as a bar that serves no alcohol, by the applicant's answer or the
    description's own words, is not a Bar (Planning Code § 102 defines a Bar by its on-site alcohol sales)."""
    return profile.business_type == "bar" and stated_no_alcohol(profile)


# Rule 1b: the uses the answer to the intake question "What kind of food or drink service is it?" gives a business
# that is not a Bar ("other", another use or not sure, gives none).
FOOD_SERVICE_USES: dict[str, PlanningUse] = {
    "restaurant": "restaurant",
    "limited_restaurant": "limited_restaurant",
}


def food_service_use(profile: BusinessProfile) -> PlanningUse | None:
    """Rule 1b: the use the applicant answered for a bar that serves no alcohol; None when it is not such a business,
    or the answer is "other" or not given."""
    if not not_a_bar(profile) or profile.food_service is None:
        return None
    return FOOD_SERVICE_USES.get(profile.food_service)


def planning_use(profile: BusinessProfile) -> PlanningUse:
    """Rule 1."""
    if profile.business_type == "bar":
        if not_a_bar(profile):
            return food_service_use(profile) or "not_covered"
        return "bar"
    if profile.business_type == "restaurant":
        return "restaurant"
    if profile.business_type == "cafe":
        return "restaurant" if _serves_alcohol(profile) else "limited_restaurant"
    return "not_covered"


# ---- an hours control as the static control table writes it ---------------------------------------------
# The triggers read hours from the dated control data (T11). This parser reads the hours text of the product's
# own table, for `controls.consistency_report`, which compares the two.
@dataclass(frozen=True)
class HoursWindow:
    """One window of an hours control. Times are minutes after midnight; an `end` at or before `start` means the
    window runs past midnight ('P 6 a.m. to 2 a.m.' is 360 to 120)."""

    permission: HoursPermission
    start: int
    end: int

    def covers(self, minute: int) -> bool:
        if self.start < self.end:
            return self.start <= minute < self.end
        return minute >= self.start or minute < self.end

    @property
    def text(self) -> str:
        return f"{self.permission} {format_time(self.start)}–{format_time(self.end)}"


@dataclass(frozen=True)
class HoursControl:
    """A district's hours control, parsed. `windows` are in the order written and are empty when `no_limit`.
    `scope` is the text before the windows that says which uses they apply to; None means every use."""

    windows: tuple[HoursWindow, ...]
    no_limit: bool = False
    scope: str | None = None

    def at(self, minute: int) -> HoursPermission | None:
        """The control at that minute after midnight; None when no window covers it (or there is no limit)."""
        return next((w.permission for w in self.windows if w.covers(minute)), None)

    @property
    def text(self) -> str:
        if self.no_limit:
            return "no limit on hours of operation"
        return "; ".join(w.text for w in self.windows)


_HOURS_PREFIX = re.compile(r"^\s*hours of operation(?:\s*\([^)]*\))?\s*:\s*", re.IGNORECASE)
_NO_LIMIT = re.compile(r"^no (?:limit|restrictions?) on hours of operation$", re.IGNORECASE)
_CLOCK = r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s?m\.?"
_WINDOW = re.compile(rf"^(NP|P|C)\s+{_CLOCK}\s*[–—-]\s*{_CLOCK}$", re.IGNORECASE)
_HOURS_PERMISSIONS: dict[str, HoursPermission] = {"P": "P", "C": "C", "NP": "NP"}


def _minutes(hour: str, minute: str | None, half: str) -> int | None:
    h, m = int(hour), int(minute or 0)
    if not 1 <= h <= 12 or m >= 60:
        return None
    return (h % 12 + (12 if half.lower() == "p" else 0)) * 60 + m


def format_time(minute: int) -> str:
    """360 -> '6 a.m.'; 0 -> '12 a.m.'; 1350 -> '10:30 p.m.'."""
    h, m = divmod(minute % (24 * 60), 60)
    half = "a.m." if h < 12 else "p.m."
    clock = h % 12 or 12
    return f"{clock}:{m:02d} {half}" if m else f"{clock} {half}"


def parse_hours(text: str | None) -> HoursControl | None:
    """An hours control as written in the zoning control table on file, with or without the store's 'Hours of
    operation:' or 'Hours of operation (Table 762):' opening:

      'P 6 a.m.-2 a.m.; C 2 a.m.-6 a.m.'           -> P 360 to 120, C 120 to 360
      'P 6 a.m.-10 p.m.; C 10 p.m.-2 a.m.; NP 2 a.m.-6 a.m.'
      'No limit on hours of operation', 'No restrictions on hours of operation' -> no_limit
      'Limited Corner Commercial / § 186 uses: P 6 a.m.-10 p.m.' -> scope + one window

    (the table writes an en dash between the two times; a hyphen is read the same way)

    None when the text is empty or any part of it is not a window (for example one sentence that lists several
    districts): the caller then changes nothing and lists the text among the notes."""
    body = _HOURS_PREFIX.sub("", text or "").strip().rstrip(".").strip()
    if not body:
        return None
    if _NO_LIMIT.match(body):
        return HoursControl(windows=(), no_limit=True)
    scope: str | None = None
    parts = [p.strip() for p in body.split(";")]
    if not _WINDOW.match(parts[0]) and ":" in parts[0]:
        head, rest = parts[0].split(":", 1)
        if head.strip() and _WINDOW.match(rest.strip()):
            scope, parts[0] = head.strip(), rest.strip()
    windows: list[HoursWindow] = []
    for part in parts:
        m = _WINDOW.match(part)
        if m is None:
            return None
        start = _minutes(m.group(2), m.group(3), m.group(4))
        end = _minutes(m.group(5), m.group(6), m.group(7))
        if start is None or end is None:
            return None
        windows.append(HoursWindow(_HOURS_PERMISSIONS[m.group(1).upper()], start, end))
    return HoursControl(windows=tuple(windows), scope=scope)


def closing_bucket(profile: BusinessProfile) -> ClosingBucket:
    """Which closing time the profile's two flags hold. 'by_midnight' also covers a profile that gives no
    closing time (both flags are False by default), so the rules never read it as a closing time: see
    `facts.Closing`."""
    if profile.closes_after_2am:
        return "after_2am"
    if profile.closes_after_midnight:
        return "after_midnight"
    return "by_midnight"


# ---- rule 4: the existing use the licence records show --------------------------------------------------
def licence_type(app: Application) -> str | None:
    """The ABC licence type number of a licence record ('41'), from `license_type` or else from the source's
    own label ('Type 41 - On-Sale Beer & Wine - Eating Place'). None when the record is not an ABC licence or
    names no type."""
    if app.kind != "abc_license" and app.source != "abc":
        return None
    raw = (app.license_type or "").strip()
    if not raw:
        m = re.search(r"\bType\s*(\d+)", app.permit_type or "", re.IGNORECASE)
        raw = m.group(1) if m else ""
    digits = raw.lstrip("0") if raw.isdigit() else ""
    return digits or None


def _at_report_address(rec: SiteRecord, site: Site) -> bool:
    """Is the record's own street address the report's? A record tied to the site only by its parcel ('999
    Valencia St' on the lot of 995 Valencia St) is not. As in `site_match`, a street written without its suffix
    matches only when the record is mapped within 30 metres of the report's point."""
    own = parse_street_address(rec.app.address)
    if own is None or site.street is None:
        return False
    return same_street_address(own, site.street, allow_missing_suffix=rec.distance_m <= SITE_READ_RADIUS_M)


def _active_licences(
    site_records: Sequence[SiteRecord], site: Site
) -> list[tuple[Application, str, LicenceType]]:
    """The ACTIVE ABC licences of a type the rules read (LICENCE_TYPES) on file at the report's own street
    address, in record id order: (record, type number, type)."""
    found: list[tuple[Application, str, LicenceType]] = []
    if site.street is None:
        return found
    for rec in _sorted_records(site_records):
        number = licence_type(rec.app)
        if number is None or number not in LICENCE_TYPES:
            continue
        if rec.app.status.strip().upper() != "ACTIVE" or not _at_report_address(rec, site):
            continue
        found.append((rec.app, number, LICENCE_TYPES[number]))
    return found


def existing_use(
    site_records: Sequence[SiteRecord],
    site: Site,
    *,
    rules_date: dt.date | None = None,
    today: dt.date | None = None,
) -> tuple[PlanningUse | None, list[RuleLine]]:
    """Rule 4: the use the rules read at the report's own street address from the licences on file there, and
    the lines saying which record showed it (or that none did). With a past `rules_date` (earlier than `today`)
    the sentences say the records read are the ones dated before it (the caller has left out the later ones)."""
    dated = rules_date is not None and today is not None and rules_date < today
    suffix = "_dated" if dated else ""
    date = rules_date.isoformat() if rules_date is not None else ""
    if site.street is None:
        return None, [_line(f"zoning.existing_use/no_address{suffix}", date=date)]
    address = _address(site)
    found = _active_licences(site_records, site)
    if not found:
        types = ", ".join(sorted(LICENCE_TYPES, key=int))
        return None, [_line(f"zoning.existing_use/none{suffix}", address=address, types=types, date=date)]
    shown = {kind.shows for _, _, kind in found}
    one = len(shown) == 1
    first = "zoning.existing_use/dated" if dated else "zoning.existing_use"
    lines = [
        _line(
            first if one else f"zoning.existing_use/one_of_both{suffix}",
            citations=[f"app:{app.id}"],
            source_url=app.source_url,
            type=number,
            type_label=kind.label,
            address=address,
            a_use=_a(kind.shows),
            date=date,
        )
        for app, number, kind in found
    ]
    if one:
        return found[0][2].shows, lines
    cited = [f"app:{app.id}" for app, _, _ in found]
    return None, [
        *lines,
        _line(f"zoning.existing_use/both{suffix}", address=address, citations=cited, date=date),
    ]


# ---- reading the zoning and overlay rows on file ----------------------------------------------------------
def _names_section(code_section: str, number: str) -> bool:
    """Does the code section text name this section number ('249.60', not '249.601' or '1249.60')?"""
    return re.search(rf"(?<![\d.]){re.escape(number)}(?![\d])", code_section) is not None


def _subarea_rule(use: str, o: Overlay) -> SubareaRule | None:
    """The subarea rule that reads this overlay for this use, if any (SUBAREA_RULES)."""
    return next(
        (r for r in SUBAREA_RULES if use in r.uses and _names_section(o.code_section, r.overlay_section)),
        None,
    )


def _control_for(use: PlanningUse, bar: str, restaurant: str) -> str | None:
    """The control on file for the use: principal, conditional or prohibited; None when there is none."""
    value = bar if use == "bar" else restaurant if use == "restaurant" else None
    return value if value in _RESTRICTION else None


def _district_ref(zoning: ZoningInfo, overlays: Sequence[Overlay]) -> tuple[str | None, list[str]]:
    """The section to print for the district and the records it comes from. The district's own zoning_district
    row names its one table ('Planning Code § 711'); the ZoningInfo of a shared rule row names several."""
    cited = [f"zoning:{zoning.district}"]
    own = next(
        (
            o
            for o in overlays
            if o.kind == "zoning_district"
            and zoning.district in (o.name, o.id.rsplit(":", 1)[-1])
            and _short_section(o.code_section)
        ),
        None,
    )
    mine = _short_section(zoning.code_section)
    if own is not None and _short_section(own.code_section) != mine:
        return _short_section(own.code_section), [*cited, f"overlay:{own.id}"]
    return mine, cited


def _notes(
    profile: BusinessProfile, zoning: ZoningInfo | None, overlays: Sequence[Overlay]
) -> list[RuleLine]:
    """One line per note on file, verbatim: the district's, then each alcohol district (when the concept serves
    alcohol), each rule row attached to the district, and each special use district that carries a bar or
    restaurant control. Unrelated special use districts are left out. The rules do not read this text."""
    notes: list[RuleLine] = []
    if zoning is not None and zoning.rules.strip():
        notes.append(
            _line(
                "zoning.note",
                rules=zoning.rules.strip(),
                citations=[f"zoning:{zoning.district}"],
                code_section=_short_section(zoning.code_section),
                source_url=zoning.source_url,
            )
        )
    for o in overlays:
        if o.kind not in _NOTE_KINDS or not o.rules.strip():
            continue
        if o.kind == "alcohol_sud" and not _serves_alcohol(profile):
            continue
        if o.kind == "special_use_district" and "unknown" == o.bar_permission == o.restaurant_permission:
            continue
        notes.append(
            _line(
                "zoning.note",
                rules=o.rules.strip(),
                citations=[f"overlay:{o.id}"],
                code_section=_short_section(o.code_section),
                source_url=o.source_url,
            )
        )
    return _merge(notes)


# ---- rules 3 and 4: the triggers, the zoning row and the pathway -----------------------------------------
def _use_lines(concept: ConceptFacts) -> list[RuleLine]:
    """Rule 1 as a line, after rule 1b's line on the kind of food or drink service where an answer gave it. A concept
    with no use the rules read gets no use line: T1's own line says so."""
    lines = _food_service_lines(concept)
    uses = concept.planning_uses.value
    if not uses:
        return lines
    if len(uses) == 1:
        return [*lines, _line("zoning.use", a_use=_a(uses[0]))]
    return [*lines, _line("zoning.use/several", uses=_and([USE_LABELS[u] for u in uses]))]


def _food_service_lines(concept: ConceptFacts) -> list[RuleLine]:
    """Rule 1b: the line for the kind of food or drink service, where it was given. Read for a bar that serves no
    alcohol, it is the concept's use ("zoning.food_service"); answered for any other business it is not read, and
    the line says so ("zoning.food_service/not_read"). An answer of "other" for a bar that serves no alcohol gives
    no use, and T1's own line says what was answered."""
    service = concept.food_service
    if service.source == "stated" and service.value is not None:
        return [
            _line(
                "zoning.food_service",
                lead=FOOD_SERVICE_LEAD[concept.by_answer("serves_alcohol")],
                given=FOOD_SERVICE_GIVEN[concept.by_answer("food_service")],
                a_use=_a(service.value),
            )
        ]
    given = concept.food_service_given
    if not concept.not_a_bar and given is not None and concept.by_answer("food_service"):
        return [_line("zoning.food_service/not_read", answer=FOOD_SERVICE_ANSWERED[given])]
    return []


def _shown(finding: TriggerFinding, concept: ConceptFacts) -> bool:
    """Rule 3: is this finding printed in the zoning row? Every finding that applies is. One that does not
    apply is left out only when all its lines are in QUIET_LINES."""
    if finding.control != "does_not_apply":
        return True
    ids = {line.rule_id for line in finding.lines}
    if LAUNDROMAT_LINE in ids and "laundromat" in concept.existing_use_stated.value:
        return True
    return not ids <= QUIET_LINES


def _trigger_names(findings: Iterable[TriggerFinding]) -> str:
    """'use control of the zoning district and formula retail': the contract's labels, in trigger order."""
    return _and([f.label[:1].lower() + f.label[1:] for f in findings])


def _cited(findings: Iterable[TriggerFinding]) -> list[str]:
    return sorted({c for f in findings for line in f.lines for c in line.citations})


def _reference(findings: Iterable[TriggerFinding]) -> tuple[str | None, str | None]:
    """The section and link of the first line of these findings that names a code section."""
    line = next((line for f in findings for line in f.lines if line.code_section), None)
    return (line.code_section, line.source_url) if line is not None else (None, None)


def _question(key: str, **fields: str) -> OpenQuestion:
    question, ask = OPEN_QUESTIONS[key]
    return OpenQuestion(question=question.format(**fields), needs="agency_answer", ask=ask)


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


def _zoning_row(
    concept: ConceptFacts,
    findings: Sequence[TriggerFinding],
    change_lines: Sequence[RuleLine],
    *,
    use_continues: bool,
) -> RowDetermination:
    """Rule 3."""
    from app.memo import triggers

    outcome = triggers.zoning_outcome(findings)
    deciding = outcome.deciding
    words = _status_words(outcome.status)
    names = _trigger_names(deciding)
    section, url = _reference(deciding)
    cited = _cited(deciding)
    missing: tuple[str, ...] = ()
    if outcome.status == "not_permitted":  # Z-NP
        approval = ZONING_APPROVALS["not_permitted"]
        last = _line(
            "zoning.status/not_permitted",
            triggers=names,
            status=words,
            citations=cited,
            code_section=section,
            source_url=url,
        )
    elif outcome.status == "further_review" and outcome.status_note is None:  # Z-C
        approval = ZONING_APPROVALS["conditional"]
        undecided = triggers.not_decided(findings)
        if undecided:
            last = _line(
                "zoning.status/conditional_and_undecided",
                triggers=names,
                undecided=_trigger_names(undecided),
                status=words,
                citations=cited,
            )
        else:
            last = _line("zoning.status/conditional", triggers=names, status=words, citations=cited)
    elif outcome.status == "insufficient_information":  # Z-S and Z-ND
        missing = outcome.missing_inputs
        covered = bool(concept.planning_uses.value)
        approval = ZONING_APPROVALS["not_decided" if covered else "not_covered"]
        asks = triggers.conditional(findings)  # only under Z-S: a missing story outranks a Conditional Use
        if asks:
            last = _line(
                "zoning.status/not_decided_story",
                triggers=names,
                missing="; ".join(missing),
                conditional=_trigger_names(asks),
                status=words,
                citations=cited,
            )
        else:
            last = _line(
                "zoning.status/not_decided",
                triggers=names,
                missing="; ".join(missing),
                status=words,
                citations=cited,
            )
    elif outcome.status == "further_review":  # Z-D
        approval = ZONING_APPROVALS["practice_differs"]
        last = _line(
            "zoning.status/practice_differs",
            triggers=names,
            status=words,
            note=outcome.status_note or "",
            citations=cited,
            code_section=section,
            source_url=url,
        )
    else:  # Z-A
        approval = ZONING_APPROVALS["existing" if use_continues else "principal"]
        last = _line("zoning.status/allowed", status=words)
    shown = [line for f in findings if _shown(f, concept) for line in f.lines]
    basis = [*_use_lines(concept), *shown, *change_lines, last]
    return _row(
        "zoning_use", approval, outcome.status, basis, status_note=outcome.status_note, missing=missing
    )


def _permission(concept: ConceptFacts, as_new: Sequence[TriggerFinding]) -> tuple[UsePermission, str]:
    """Rule 4: the control for a new use of this kind here, and its label. `as_new` are the findings of
    `_permission_findings`."""
    from app.memo import triggers

    if not concept.planning_uses.value:
        return "not_covered", USE_PERMISSION_LABELS["not_covered"]
    worst = min((f.control for f in as_new), key=triggers.SEVERITY.index, default="does_not_apply")
    if worst == "not_permitted":
        return "not_permitted", USE_PERMISSION_LABELS["not_permitted"]
    if triggers.story_not_given(as_new):  # no story is given: never resolved by assuming one (as Z-S)
        return "not_covered", NOT_DECIDED_LABEL
    if worst == "conditional":
        return "conditional", USE_PERMISSION_LABELS["conditional"]
    if worst == "not_decided":
        return "not_covered", NOT_DECIDED_LABEL
    if worst == "code_and_practice_differ":
        return "not_covered", triggers.PRACTICE_DIFFERS_NOTE
    return "principal", USE_PERMISSION_LABELS["principal"]


def _permission_findings(concept: ConceptFacts, findings: Sequence[TriggerFinding]) -> list[TriggerFinding]:
    """Rule 4: the findings `Pathway.permission` reads, in trigger order."""
    wanted = {*PERMISSION_TRIGGERS}
    if concept.use == "nighttime_entertainment":
        wanted.add(ENTERTAINMENT_TRIGGER)
    return [f for f in findings if f.rule_id in wanted]


# ---- rule 6: the health and outdoor rows -----------------------------------------------------------------
def _not_as_described(key: str, zoning_barred: Sequence[TriggerFinding]) -> RuleLine:
    """Rules H0z and O0z: the § 175(a) line where a prohibited use bars the concept, worded as app.memo.rows
    words B0z and E0z. `zoning_barred` are the prohibited uses that make the zoning row not permitted."""
    from app.memo import rows

    return rows._not_as_described(key, zoning_barred)


def _health_row(
    concept: ConceptFacts,
    barred: Sequence[TriggerFinding],
    referral: Sequence[RuleLine],
    zoning_barred: Sequence[TriggerFinding] = (),
) -> RowDetermination:
    """H0, H0z, H1. `barred` are the findings that say the use itself is prohibited; `zoning_barred` the prohibited
    uses (`PROHIBITED_USE_TRIGGERS`) that make the zoning row not permitted."""
    approval = APPROVALS["health"]
    if barred:
        use = USE_LABELS[concept.use] if concept.use != "not_covered" else "use"
        line = _line(
            "health.status/H0", use=use, status=_status_words("not_permitted"), citations=_cited(barred)
        )
        return _row("health", approval, "not_permitted", [line])
    if zoning_barred:  # H0z
        return _row(
            "health", approval, "not_permitted", [_not_as_described("health.status/H0z", zoning_barred)]
        )
    line = _line("health.status/H1", status=_status_words("allowed"))
    return _row("health", approval, "allowed", [line], referral=referral)


def _outdoor_row(
    finding: TriggerFinding | None, concept: ConceptFacts, zoning_barred: Sequence[TriggerFinding] = ()
) -> RowDetermination:
    """O0z, O-NS, O-C, O-ND, O-U, O-P, O-NP and O1. `finding` is T9; `zoning_barred` the prohibited uses
    (`PROHIBITED_USE_TRIGGERS`) that make the zoning row not permitted. O-NP keeps its own sentence when the
    outdoor area is itself not permitted."""
    if zoning_barred and (finding is None or finding.control != "not_permitted"):  # O0z
        lines = list(finding.lines) if finding is not None and not _all_quiet(finding) else []
        last = _not_as_described("outdoor.status/O0z", zoning_barred)
        return _row("outdoor", APPROVALS["outdoor"], "not_permitted", [*lines, last])
    if concept.outdoor_not_stated:  # O-NS: the intake model read an outdoor area the text does not state
        from app.memo import facts

        unknown: ApprovalStatus = "insufficient_information"
        last = _line("outdoor.status/not_stated", status=_status_words(unknown))
        missing = [facts.MISSING_PHRASES["outdoor_area"]]
        return _row("outdoor", APPROVALS["outdoor"], unknown, [last], missing=missing)
    if finding is None or finding.control in ("does_not_apply", "code_and_practice_differ"):  # O1
        status: ApprovalStatus = "further_review"
        lines = list(finding.lines) if finding is not None and not _all_quiet(finding) else []
        last = _line("outdoor.status/O1", status=_status_words(status))
        return _row("outdoor", APPROVALS["outdoor"], status, [*lines, last])
    section, url = _reference([finding])
    cited = _cited([finding])
    # the place of the area is the applicant's answer: the line says so (never "as described")
    answered = "/answered" if concept.by_answer("outdoor_area") else ""
    if finding.control == "conditional":  # O-C
        status = "further_review"
        last = _line(f"outdoor.status/conditional{answered}", status=_status_words(status), citations=cited)
        return _row("outdoor", APPROVALS["outdoor/conditional"], status, [*finding.lines, last])
    if finding.control == "not_decided":  # O-ND
        status = "insufficient_information"
        missing = list(dict.fromkeys(finding.missing_inputs))
        last = _line(
            "outdoor.status/not_decided",
            missing="; ".join(missing),
            status=_status_words(status),
            citations=cited,
            code_section=section,
            source_url=url,
        )
        return _row("outdoor", APPROVALS["outdoor"], status, [*finding.lines, last], missing=missing)
    if finding.control == "principal" and concept.outdoor_area.missing:  # O-U
        from app.memo import facts

        status = "insufficient_information"
        missing = [facts.MISSING_PHRASES["outdoor_area"]]
        last = _line("outdoor.status/unplaced", status=_status_words(status), citations=cited)
        return _row("outdoor", APPROVALS["outdoor"], status, [*finding.lines, last], missing=missing)
    key = "principal" if finding.control == "principal" else "not_permitted"  # O-P, O-NP
    status = "allowed" if key == "principal" else "not_permitted"
    last = _line(
        f"outdoor.status/{key}{answered}",
        status=_status_words(status),
        citations=cited,
        code_section=section,
        source_url=url,
    )
    return _row("outdoor", APPROVALS[f"outdoor/{key}"], status, [*finding.lines, last])


def _all_quiet(finding: TriggerFinding) -> bool:
    return {line.rule_id for line in finding.lines} <= QUIET_LINES


# ---- rule 7: what the rules could not establish -----------------------------------------------------------
def missing_input_question(phrase: str, areas: Sequence[str]) -> str:
    """'Not known: the floor area. Needed for: zoning and use.' The rows are named in report order."""
    labels = "; ".join(APPROVAL_AREA_LABELS[a].lower() for a in _REPORT_ORDER if a in areas)
    room = QUESTION_MAX - len(MISSING_INPUT_QUESTION.format(phrase="", rows=labels))
    shown = phrase if len(phrase) <= room else phrase[: room - 1].rstrip() + "…"
    return MISSING_INPUT_QUESTION.format(phrase=shown, rows=labels)


def _missing_input_question(
    phrase: str, areas: Sequence[str], concept: ConceptFacts, *, seats_against: int | None = None
) -> OpenQuestion:
    """One question for one missing input, worded from its fixed phrase. `seats_against` is the seat count that
    disagrees with "fewer than 50 people" (`rows.occupants_conflict_seats`): the input is then not missing but in
    conflict, and the question names the conflict in plain words instead of asking it again as unanswered."""
    from app.memo import facts, rows

    by_phrase = {text: name for name, text in facts.MISSING_PHRASES.items()}
    if phrase in by_phrase:
        needs, ask = MISSING_INPUT_ASKS["description"]
        ask = MISSING_INPUT_ASK_FOR.get(by_phrase[phrase], ask)
    elif phrase == rows.EXISTING_GROUP_PHRASE:
        needs, ask = MISSING_INPUT_ASKS["plans"]
    else:
        needs, ask = MISSING_INPUT_ASKS["agency"]
    question = missing_input_question(phrase, areas)
    if seats_against is not None and phrase == facts.MISSING_PHRASES["occupants_under_50"]:
        labels = "; ".join(APPROVAL_AREA_LABELS[a].lower() for a in _REPORT_ORDER if a in areas)
        template = OCCUPANTS_CONFLICT_QUESTION[concept.by_answer("occupants_under_50")]
        question = template.format(seats=seats_against, rows=labels)
    return OpenQuestion(
        question=question,
        needs=needs,
        ask=ask,
        intake_question=_intake_question(phrase, concept),
    )


def _intake_question(phrase: str, concept: ConceptFacts) -> str | None:
    """`intake_question_for`, read for this concept where the phrase alone does not settle it: "the licence type".
    No question gives the type itself, but an answer can settle why it is not known. When alcohol is not
    established (the concept is not read as serving any), the liquor licence question does: "No alcohol" leaves no
    licence to type, and any other answer makes what is poured the open input. When alcohol is established and
    what is poured decides the type, the question on what is poured does. Otherwise (a hotel or a caterer, or the
    type not derivable from what is poured) no answer settles it, and no question is named."""
    from app.memo import facts

    if phrase != facts.MISSING_PHRASES["licence_type"]:
        return intake_question_for(phrase)
    if not concept.serves_alcohol:
        # third pass of the review of 2026-11-15: an applicant who answered the liquor licence question ("No
        # alcohol") is never sent back to it; no other answer settles the type here
        return None if concept.by_answer("serves_alcohol") else "liquor_licence"
    if concept.pours_decide_licence_type and concept.alcohol_served.missing:
        return "alcohol_served"
    return None


def intake_question_for(phrase: str) -> str | None:
    """The id of the optional intake question (app.memo.intake.QUESTIONS) whose answer gives a missing input named
    by its fixed phrase; None when no question gives it (an answer only Planning or the records can give). With it
    the report can say which question to answer and run again."""
    from app.memo import facts, intake, rows

    by_phrase = {text: name for name, text in facts.MISSING_PHRASES.items()}
    if phrase == rows.EXISTING_GROUP_PHRASE:
        fact: str | None = intake.EXISTING_OCCUPANCY_GROUP_FACT
    else:
        fact = by_phrase.get(phrase)
    question = intake.question_for_fact(fact) if fact is not None else None
    return question.id if question is not None else None


def _not_stated_question(phrase: str, concept: ConceptFacts) -> OpenQuestion:
    """Rule 7a: one question for a fact the intake model filled that the description does not state."""
    room = QUESTION_MAX - len(NOT_STATED_QUESTION.format(phrase=""))
    shown = phrase if len(phrase) <= room else phrase[: room - 1].rstrip() + "…"
    needs, ask = MISSING_INPUT_ASKS["description"]
    return OpenQuestion(
        question=NOT_STATED_QUESTION.format(phrase=shown),
        needs=needs,
        ask=ask,
        intake_question=_intake_question(phrase, concept),
    )


# ---- rule 8: the overall line and the entitlement path ----------------------------------------------------
def entitlement_path(rows: Sequence[RowDetermination]) -> str:
    """The approvals to file, in report order. A row that is insufficient_information adds none: the rules do
    not know which approval it is. The zoning and outdoor entries are left out when those rows are allowed
    (principally permitted, or an existing use that continues): nothing is filed with Planning. When any row is
    not permitted there is no path, and the sentence says so instead of listing approvals that cannot be
    issued. A row other than the zoning row is not permitted only where a zoning trigger is (the use itself,
    the liquor licence rule of a restricted district, the outdoor activity area), so the sentence is always
    true."""
    if any(r.status == "not_permitted" for r in rows):
        return NO_PATH
    steps = [
        r.approval
        for r in rows
        if r.status != "insufficient_information"
        and not (r.area in NOTHING_FILED_WHEN_ALLOWED and r.status == "allowed")
    ]
    return "; ".join(steps) or NOTHING_TO_FILE


def overall_line(rows: Sequence[RowDetermination], headlines: Sequence[HeadlineFinding] = ()) -> str:
    """'A Conditional Use Authorization is needed (use size). Of the 5 approvals this concept needs: 1 potential
    blocker (alcohol licence), 3 further review (zoning and use, entertainment permit, building permit and change
    of use), 1 allowed (health permit).' The headline findings come first (`overall_lead`); then the statuses in
    STATUS_SEVERITY order, the rows of each status in report order."""
    lead = overall_lead(headlines)
    if not rows:
        return " ".join([*lead, "No approval was looked up for this concept."])
    parts = []
    for status in STATUS_SEVERITY:
        names = [APPROVAL_AREA_LABELS[r.area].lower() for r in rows if r.status == status]
        if names:
            parts.append(f"{len(names)} {_status_words(status)} ({', '.join(names)})")
    noun = "approval" if len(rows) == 1 else "approvals"
    return " ".join([*lead, f"Of the {len(rows)} {noun} this concept needs: {', '.join(parts)}."])


def overall_lead(headlines: Sequence[HeadlineFinding]) -> list[str]:
    """Rule 8: the sentences the overall line opens with, one per kind of definite headline finding (its triggers
    named together) and one per contingent finding, in the order of the headline findings."""
    out: list[str] = []
    done: set[str] = set()
    for h in headlines:
        if h.definite:
            if h.kind in done:
                continue
            done.add(h.kind)
            same = [x.trigger_label for x in headlines if x.kind == h.kind]
            out.append(OVERALL_LEAD[h.kind].format(triggers=_and(same)))
        else:
            out.append(OVERALL_LEAD[h.kind].format(triggers=h.trigger_label, condition=h.condition or ""))
    return out


# ---- rule 9: the headline findings ------------------------------------------------------------------------
def _deciding_line(finding: TriggerFinding) -> RuleLine:
    """The line a headline finding rests on: the trigger's first line that is not an aside."""
    return next(
        (line for line in finding.lines if not line.rule_id.endswith(_ASIDE_SUFFIXES)), finding.lines[0]
    )


def headline_findings(
    findings: Sequence[TriggerFinding], rows: Sequence[RowDetermination]
) -> list[HeadlineFinding]:
    """Rule 9: the findings that change what the business needs at this address, in the order the report prints
    them. When a trigger bars the concept, the triggers that bar it, and nothing else (no answer changes that).
    Otherwise every trigger that asks for a Conditional Use Authorization, then every reading that would ask for
    one, or bar the use, only if inputs not given go one way (`TriggerFinding.contingent`), each in trigger order.
    A decided control that an input not given could change (`TriggerFinding.unsettled_by`) is never definite: only
    its contingent readings are shown. A contingent finding is worded with its condition and the inputs it turns
    on, never as definite, and takes its row's own status."""
    from app.memo import triggers

    by_area = {r.area: r for r in rows}
    barred = [f for f in triggers.not_permitted(findings) if not f.unsettled_by]
    undecided = triggers.not_decided(findings)
    no_story = bool(triggers.story_not_given(findings))
    out: list[HeadlineFinding] = []

    def area_of(f: TriggerFinding) -> ApprovalArea:
        area = HEADLINE_AREA.get(f.rule_id)
        return area if area is not None and area in by_area else "zoning_use"

    def finding(
        f: TriggerFinding,
        kind: HeadlineKind,
        sentence: str,
        status: ApprovalStatus,
        reading: ContingentReading | None = None,
    ) -> HeadlineFinding:
        line = _deciding_line(f)
        section, url = (line.code_section, line.source_url) if line.code_section else _reference([f])
        return HeadlineFinding(
            kind=kind,
            sentence=sentence,
            area=area_of(f),
            status=status,
            trigger=f.rule_id,
            trigger_label=_trigger_names([f]),
            definite=reading is None,
            condition=None if reading is None else reading.condition,
            missing_inputs=[] if reading is None else _missing_of(f, reading),
            code_section=section,
            source_url=url,
            citations=_cited([f]),
            basis=[line],
        )

    if barred:
        for f in barred:
            text = HEADLINE_TEXT["not_permitted"].format(trigger=_trigger_names([f]))
            out.append(finding(f, "not_permitted", text, "not_permitted"))
        return out
    for f in triggers.conditional(findings):
        if f.unsettled_by:
            continue
        key = "conditional/story" if no_story else "conditional/undecided" if undecided else "conditional"
        text = HEADLINE_TEXT[key].format(trigger=_trigger_names([f]), undecided=_trigger_names(undecided))
        out.append(finding(f, "conditional", text, "further_review"))
    for f in findings:
        if f.control != "not_decided" and not f.unsettled_by:
            continue
        for reading in f.contingent:
            kind: HeadlineKind = "conditional_if" if reading.control == "conditional" else "not_permitted_if"
            text = HEADLINE_TEXT[kind].format(
                condition=reading.condition,
                trigger=_trigger_names([f]),
                missing="; ".join(_missing_of(f, reading)),
            )
            row = by_area.get(area_of(f))
            status = row.status if row is not None else "insufficient_information"
            out.append(finding(f, kind, text, status, reading))
    return out


def _missing_of(f: TriggerFinding, reading: ContingentReading) -> list[str]:
    """What a contingent finding names as not known: the inputs its condition turns on (else the trigger's)."""
    return list(reading.missing_inputs or f.missing_inputs or f.unsettled_by)


# ---- the entry point --------------------------------------------------------------------------------------
def determine(
    profile: BusinessProfile,
    zoning: ZoningInfo | None,
    overlays: Sequence[Overlay],
    site_records: Sequence[SiteRecord],
    site: Site,
    areas: Sequence[ApprovalArea],
    *,
    today: dt.date | None = None,
    rules_date: dt.date | None = None,
    tract: str | None = None,
) -> Determinations:
    """Rules 0 to 9 for the approvals in `areas` (pass `required_areas(profile)`).

    `rules_date` is the date whose rules apply and defaults to `today`; `today` defaults to the current date,
    read once here. With `today` given the call is pure: no I/O beyond the bundled data files, no clock, no
    randomness, no model, and the same inputs in any order give byte-identical output. `tract` is the census
    tract of the address as ABC writes it (`tracts.tract_at(lat, lng)`); None when it is not known, and the
    alcohol row then says nothing about the tract. The rows come back in report order whatever order `areas`
    is in, each area once."""
    from app.memo import facts, rows, triggers

    today = _day(today) if today is not None else dt.date.today()
    rules_date = _day(rules_date) if rules_date is not None else today
    ordered = _sorted_overlays(overlays)
    concept = facts.concept_facts(profile)
    on_site = facts.site_facts(site_records, site, rules_date=rules_date, today=today)

    # rule 2: the eleven triggers
    findings = triggers.evaluate(concept, on_site, zoning, ordered, rules_date=rules_date, today=today)
    by_id = {f.rule_id: f for f in findings}
    # rule 5: the three change-of-use answers
    described = (
        "new_construction" if profile.new_construction else "applicant" if profile.change_of_use else None
    )
    # the existing occupancy group is in no public record: only the applicant's intake answer gives it
    existing_group = profile.existing_occupancy_group
    changes = rows.change_answers(
        concept,
        on_site,
        findings,
        zoning,
        rules_date=rules_date,
        existing_occupancy_group=existing_group,
        described_change=described,
    )
    # rule 4: the control for a new use. Where a business or a use continues, the use triggers are read again
    # as for a new use; otherwise the plain reading already is that.
    may_continue = on_site.existing_use is not None or not concept.changes_existing_business.missing
    as_new = _permission_findings(
        concept,
        triggers.evaluate(concept, on_site, zoning, ordered, rules_date=rules_date, today=today, as_new=True)
        if may_continue
        else findings,
    )
    permission, permission_label = _permission(concept, as_new)
    use_lines = [
        *(  # rule 1a
            [_line("intake.no_alcohol")] if profile.no_alcohol_answer_over_description else []
        ),
        *_use_lines(concept),
    ]
    change_lines = list(changes.planning_use_lines)
    pathway = Pathway(
        use=concept.use,
        use_label=USE_LABELS[concept.use],
        district=zoning.district if zoning is not None else None,
        permission=permission,
        permission_label=permission_label,
        existing_use=on_site.existing_use,
        change_of_use=changes.planning_use,
        change_of_use_label=CHANGE_OF_USE_LABELS[changes.planning_use],
        lines=_merge(
            [*use_lines, *(line for f in as_new if _shown(f, concept) for line in f.lines), *change_lines]
        ),
        notes=_notes(profile, zoning, ordered),
        rules_date=rules_date.isoformat(),
        triggers=list(findings),
        changes=changes,
    )

    # rule 6: "the use itself is prohibited", and "zoning does not permit the concept as described"
    use_barred = [f for f in findings if f.rule_id in USE_TRIGGERS and f.control == "not_permitted"]
    zoning_outcome = triggers.zoning_outcome(findings)
    zoning_barred = list(zoning_outcome.deciding) if zoning_outcome.status == "not_permitted" else []
    # the prohibited uses among them, which carry § 175(a) to the health, building, entertainment and outdoor rows
    prohibited = [f for f in zoning_barred if f.rule_id in PROHIBITED_USE_TRIGGERS]
    entertainment_barred = [
        *use_barred,
        *(f for f in findings if f.rule_id == ENTERTAINMENT_TRIGGER and f.control == "not_permitted"),
    ]
    wanted = set(areas)
    out: list[RowDetermination] = []
    for area in _REPORT_ORDER:
        if area not in wanted:
            continue
        if area == "zoning_use":
            continues = by_id["T3"].control != "does_not_apply"
            out.append(_zoning_row(concept, findings, change_lines, use_continues=continues))
        elif area == "alcohol":
            out.append(
                rows.alcohol_row(
                    concept,
                    on_site,
                    findings,
                    zoning_prohibits_use=bool(use_barred),
                    tract=tract,
                    rules_date=rules_date,
                    # T1 and T2 never read a use that continues (nor one that may continue), so a use they bar is
                    # new; otherwise the row's own test of a continuing use applies
                    prohibited_use_is_new=bool(use_barred),
                    zoning_barred_by=zoning_barred,
                )
            )
        elif area == "entertainment":
            out.append(
                rows.entertainment_row(
                    concept,
                    findings,
                    rules_date=rules_date,
                    zoning_prohibits_use=bool(entertainment_barred),
                    zoning_barred_by=prohibited,
                )
            )
        elif area == "health":
            steps = rows.referral_steps("health", concept, rules_date=rules_date)
            out.append(_health_row(concept, use_barred, steps, prohibited))
        elif area == "building_change_of_use":
            out.append(
                rows.building_row(
                    changes,
                    concept,
                    zoning_prohibits_use=bool(use_barred),
                    rules_date=rules_date,
                    existing_occupancy_group=existing_group,
                    zoning_barred_by=prohibited,
                )
            )
        else:
            out.append(_outdoor_row(by_id.get(OUTDOOR_TRIGGER), concept, prohibited))

    # rule 7: one question per missing input, each phrase once, then the two standing questions
    needed_for: dict[str, list[str]] = {}
    if "zoning_use" in wanted and triggers.zoning_outcome(findings).status != "not_permitted":
        for phrase in triggers.missing_inputs(findings):
            needed_for.setdefault(phrase, []).append("zoning_use")
    for row in out:
        for phrase in row.missing_inputs:
            found = needed_for.setdefault(phrase, [])
            if row.area not in found:
                found.append(row.area)
    # "fewer than 50 people" against 50 seats or more is asked as the conflict it is, not as unanswered
    seats_against = rows.occupants_conflict_seats(concept, rules_date)
    questions = [
        _missing_input_question(phrase, where, concept, seats_against=seats_against)
        for phrase, where in needed_for.items()
    ]
    # rule 7a: every fact the stated-facts check left not known that no row or trigger asks for already
    for name in concept.cleared_facts:
        phrase = facts.MISSING_PHRASES[name]
        if phrase not in needed_for:
            questions.append(_not_stated_question(phrase, concept))
    address = _address(site)
    if "zoning_use" in wanted and triggers.practice_differs(findings):
        questions.append(_question("use_permitted", a_use=_a(concept.use), address=address))
    rests_on_licence = changes.planning_use == "no" and on_site.existing_use is not None
    if rests_on_licence and wanted & {"zoning_use", "building_change_of_use"}:
        questions.append(_question("last_legal_use", address=address))  # "no" rests on a licence type alone
    # rule 9: what changes the business's plans comes first; rule 8: the overall status and line reflect it
    headlines = headline_findings(findings, out) if "zoning_use" in wanted else []
    definite = [h.status for h in headlines if h.definite]
    return Determinations(
        pathway=pathway,
        rows=out,
        overall_status=most_severe([*(r.status for r in out), *definite]),
        overall_line=overall_line(out, headlines),
        entitlement_path=entitlement_path(out),
        open_questions=questions,
        headline_findings=headlines,
    )
