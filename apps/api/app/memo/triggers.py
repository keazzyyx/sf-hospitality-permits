"""The eleven trigger rules (rule table v2). Pure code: no I/O beyond the bundled data files, no clock (both
dates are passed in), no randomness, no model. The same inputs in any order give byte-identical output.

Spec: docs/validation/rule-table-extension-spec.md, section 1a. `evaluate` returns one `TriggerFinding` for each of
T1 to T11, always all eleven and always in that order. Every control is read from the dated control data
(`app.memo.controls`) for `rules_date`. `differs_today` is set when the same question answered for `today` gives
a different control; the finding then carries one line saying when the control changed and what it reads today.

HOW THE RULES READ (binding; where this refines the spec the reason is given)

Controls of a finding
  principal                 the trigger was read and asks for nothing
  conditional               a Conditional Use Authorization is needed
  not_permitted             the code bars it
  not_decided               the trigger matters here and something is not known; `missing_inputs` names it with
                            the fixed phrase of `app.memo.facts.MISSING_PHRASES`, or with a phrase of `NOT_KNOWN`
                            below when what is not known is not an input (which part of a district an address is
                            in, a fact no input carries)
  does_not_apply            the concept or the district is outside the trigger; one line says why
  code_and_practice_differ  only where the spec says so (T2, Mission restaurants outside the two Mission districts),
                            and T3 for a continuing use whose standing as new is that T2 split

One entry, one answer. A control that reaches only part of a district (the data's `subarea_controls`,
`exceptions`, `special_district_override`, `exception_rows`, `not_permitted_for_in_subarea`,
`formula_retail_restaurant_rule`, `principal_exception`, `conditional_where`, `conflicting_text`, the § 186
variants, the cap on eating and drinking uses) is never ignored and never applied to an address that is not shown
to be in it. Where it could change the entry's answer and the rules cannot place the address or the fact, that
entry is "not_decided". An exception the facts can decide is applied (NCD-BAYVIEW: a Bar is not permitted,
conditional with an ABC Type 42 licence from 2025-04-07; NCD-INNER CLEMENT: a Bar is conditional with Type 42 and
not permitted with any other type but the § 102 Restaurant types). A sub-area an overlay on file names by its
section is placed by that overlay, as Central SoMa is by § 249.78: inside, its control applies; with no such
overlay at the point the address is outside it (the Geary Boulevard and Taraval Street subdistricts, §§ 781.4 and
781.1).

Typed fields read from quoted code text. Where a version of a district row carries a control in its quote or in
its note's quotation of the code, the data file carries it as a typed field of that version, and the rules read
the field: `conditional_not_required_for` (Table 811 / 810 Note 1), `eating_drinking_cap` (Table 754 Note 7),
`exceptions` (Table 716 Note 3, Table 719 Note (4)), `principal_exception` (Table 838 Note 1),
`exception_rows_by_date` (the RH-2 rows outside the use's row, dated inside the version),
`other_code_text_figures` (the other code text a use size row disagrees with) and `subarea_overlay_sections`
(the overlays that place a sub-area). A test holds each to the words of its version's quote or note. The quoted
code text wins over the spec where the two differ.

Several entries in one trigger (several stories, several uses, several special district rules) combine by the
order of spec section 4: not_permitted, then conditional, then not_decided, then code_and_practice_differ, then
principal. `missing_inputs` lists what would settle every entry that is not decided, also when another entry
already makes the trigger conditional.

Uses and stories. The uses are `ConceptFacts.planning_uses`. The stories are the ones stated, in the fixed order of
`Story`. No story is ever assumed (the user's decision of 2026-11-12: "MISSING STORY: always 'Insufficient
information', naming it. Never default to the first story."). When none is given (`ConceptFacts.story_missing`, a
story the intake model read that the text does not state included), every entry whose answer depends on the
story is not_decided and names it with MISSING_PHRASES["stories"]: the district's cells (T1, T3's standing as new,
T6) when the table does not read the same on every story (`EVERY_STORY`); a special district rule for the First
Story only, read for the First Story (on any other story it does not apply), when that reading asks for something or
is itself not decided (T2, T4, and the Haight Street ground-level quota; a not decided reading names its own missing
input and the story); and the control of a district the dated data does not carry (`_v1_reading`: the zoning
control table on file gives first-story controls), unless the district's own table has no story columns
(`NO_STORY_COLUMNS`) and no overlay adds its own control. This holds whatever any one story would read, a story that
would need a Conditional Use or bar the use included, and the zoning row is then "Insufficient information"
(`zoning_outcome`, Z-S). A table that reads the same on every story is read as it reads, with a line saying the
story does not change it, and a First Story rule that asks for nothing on the First Story stands as it reads: no
story is assumed there either.

A business that continues. A business continues at the address when `changes_existing_business` is stated, or
when the records show an existing use that is among the uses proposed. The uses that continue are then: the uses
proposed that are among the existing uses stated or shown; when no existing use is stated or shown, every use
proposed except Nighttime Entertainment (the description is of the existing business). T1, T2 and T6 are not
applied to a use that continues: that is T3's ground. A use proposed that the description states the space is,
or was last, used as, where `changes_existing_business` is missing and the records do not show it, may or may not
continue: T1, T2 and T6 answer not_decided for it, naming whether an existing business is to be enlarged or
intensified (spec 1a T3 keeps its definition of a business that continues).

T1   reads Bar, Restaurant and Limited Restaurant. Refinement: the Nighttime Entertainment cell is read by T6
     only, so one cell never makes two triggers. No use known: not_decided; for a bar that serves no alcohol
     (pathway rule 1b, not a Bar) the line says why and names the kind of food or drink service. Where the first-story cell's note is a
     special district's prior-use rule (NCD-NORTH BEACH, Note (5)), the cell follows that rule's reading (T2).
     The cap on eating and drinking uses (Table 754 Note 7) is not decided: no input carries the count.
T2   one bound rule per special district use rule (`BINDINGS`). § 249.60(f)(1): conditional in NCT-MISSION and
     NCT-24TH-MISSION, code_and_practice_differ elsewhere in the district. North Beach prior-use rule: a space to
     be enlarged or merged fails its condition (not permitted); until 2025-12-14 the same use as the prior
     authorized use needs no Conditional Use unless enlarged or intensified, so with the change missing it is not
     decided. SoMa Youth and Family until 2023-06-02: the data does not map "Other entertainment" (§ 890.37) onto
     Nighttime Entertainment, so that rule is not decided for it.
T3   the existing use is read as a new use on the rules date: the district's cell, every bound T2 rule that asks
     for something or is not decided, and the special district licence rules for a new establishment (T4's
     `new_establishment` and `adds_licence` rules) read for the licence types the business holds (the records'
     active licences and the types stated as held, else the concept's type; not decided, naming the licence
     type, or what alcohol will be served when that is what leaves the type missing, for a business that serves
     alcohol when neither is known). The worst of them: principal -> principal;
     conditional -> conditional (§ 178); not permitted -> conditional in a Neighborhood Commercial district
     (§ 186.1); outside those districts the data's rule text says a nonconforming use may not be enlarged or
     intensified at all, with exceptions the rules cannot place (§ 181): not_decided. The spec says
     "conditional (§ 182 elsewhere)"; the data's text is followed. Not decided -> not_decided, naming every input
     the readings name. The Code and Planning practice differ -> code_and_practice_differ when the change is
     stated. The § 178 and § 186.1 lines are dated by the run of versions in which the Conditional Use term reads
     the same (`T3_CONDITIONAL_USE_TERM`).
T4   one bound rule per special district licence rule. A rule whose control is "requirement" is printed as a
     line and never sets the control; `requirements` and `blocking_requirements` find those lines. A Bar sells
     alcohol by its § 102 definition, so a Bar that does not say so is never read as serving none. A concept that
     serves alcohol without saying what (alcohol_type "unknown") has no licence type: a rule that turns on the
     type is not decided and names what alcohol will be served (`ConceptFacts.licence_type_phrase`), never read
     as "no alcohol" nor as a type. Haight Street
     until 2024-01-13: a Restaurant with Type 41 or 47 on the ground level could fall within the Restaurant
     quota the data records as C, so for it the not permitted rule is not decided.
T5   formula retail true: the district's control; false: principal; missing where a control is C or NP:
     not_decided. The change-of-operator rule (§ 178(c)(3)) is printed as a note, dated by the run of versions
     in which its limbs read the same.
T6   Nighttime Entertainment by story; entertainment (live, or amplified sound) described without its kind:
     not_decided where the cell is C or NP.
T7   floor area against the district's threshold, for a use that is new, merged or enlarged. The row's
     exemption is printed; its Restaurant part (Table 811 / 810 Note 1) is applied above its own figure. Where
     the row and the section it cites disagree (`other_code_text_figures`) and the two give different answers:
     not_decided. A new use taking over an existing non-residential space in a Neighborhood Commercial district
     (spec 1a: not "taking over an existing space unchanged"): not decided without the floor area before and
     whether storefronts are merged; no growth and no merger -> does_not_apply; North Beach and Castro until
     2025-10-05 need a new Conditional Use to change an oversized use, so the threshold is read.
     Intensifying a continuing use alone does not apply T7.
T8   laundromat removal, in force 2021-12-20 to 2024-12-20; on the last day a line says the data does not
     settle whether that day or the one before was the last.
T9   the outdoor activity area by its place. Elsewhere on the lot, the § 202.2(a)(7) route is read from the
     district's row or from the citywide entry's list of district classes for the date. An existing business
     stated not to change: a conditional or not permitted area is not decided (whether it is new).
T10  changing the conditions of an earlier approval.
T11  the closing time against the district's hours windows. No closing time stated: not_decided where a C or NP
     window begins before 2 a.m. A business open through the night to a morning close is read over every hour
     to the close; a morning close not said to be overnight is not decided where that would change the answer.
     An existing business that is not intensified: a conditional or not permitted window is not decided
     (whether it already lawfully keeps these hours; spec 1a T11).

Contingent readings (change of 2026-11-16; the review of that day replaced a T7-only reading that took the
floor area as the only open input, and so said "If the floor area is 2,501 square feet or more, ... needs a
Conditional Use Authorization" in districts where the Restaurant note, a cap or Interpretation 121.2 says otherwise).
For T1 and T6 (the story), T5 (whether the business is a chain of eleven or more) and T7 (the floor area, whether a
continuing business is enlarged, a merger, the floor area before, the space's last use), `evaluate` asks what the
trigger's own reading gives once those inputs go one way (`TriggerFinding.contingent`). No control changes. The
trigger is run again with each input supposed, over every value it can take (`_suppositions`: the floor area
over each run of areas T7 reads alike, from its threshold, cap, Restaurant note, corner and grocery caps and the
other code text's figures; a merger with an enlargement; the last use for T7 from the start, as T7 reads it
without naming it), and a condition is kept only where every run it covers gives the same control that asks for
something (`_sufficient`): "the floor area is from 2,501 to 4,000 square feet" (CRNC: conditional), "the floor area
is 4,001 square feet or more" (not permitted), "the floor area is 4,001 square feet or more and either the floor
area grows or storefronts are merged" (a former restaurant in NC-2). Only inputs not given are offered as a way
(an answered "no merger" is never named again). A story reading that is the same on every story is not worded as
turning on the story. A decided T7 that a last use not given could change (the space read as new where a former
bar, restaurant or shop would make it turn on Interpretation 121.2) names that input (`TriggerFinding.unsettled_by`):
it is then not a definite headline finding, only its contingent readings are (app.memo.pathway rule 9). A
condition says what the rules give once they can decide: "the floor area grows" holds whatever the merger answer,
though T7 still asks that answer. Not covered: T11 (a closing time not given) and T2 and T4 (the story in a special
district's rule); their not decided findings give no contingent reading.

A district the dated data does not carry: T1 answers for Bar and Restaurant from the zoning control table on file
(rule table v1's own functions) and says so; T3 reads the same table; T5, T6, T7, T9 and T11 are not_decided,
naming "the rule table does not carry this zoning district", when the concept touches them.

Historic Buildings (Planning Code § 202.11, from 2026-04-11) are never evaluated. Where the data carries a
Historic Buildings passage for a cell on the date, the finding gains one line saying so.

`differs_today` compares what the control asks for: "principal" and "does_not_apply" both ask for nothing, so a
trigger that goes from one to the other has not changed. The day the control changed is found by reading the
trigger again on each day the dated data changes.

Rule ids on the lines: "T<n>.<name>" for a fixed sentence of `TEXT`; "T<n>:<rule_id>" for a line built from the
special district rule of that `rule_id` in the data; rule table v1's own ids ("zoning.use_control",
"zoning.sud_control") on the lines its functions write for a district the dated data does not carry. Citations: "zoning:<district>" for a district row,
"overlay:<overlay id>" for a special district found through an overlay, "app:<record id>" for a site record.

Where a line's fact came from: a sentence that says what the description says, gives or describes has a
"<key>/answered" sentence ("You answered ...") for the same fact given by an intake answer (`_by_origin`, read from
`ConceptFacts.answered`, the profile's `intake_answered`). The rule id is the same either way.

Every fixed sentence is in `TEXT`, every phrase for something not known in `NOT_KNOWN`, the words of every way a
contingent reading names in `CONDITION_WORDS`, every special district rule in `BINDINGS` or `UNBOUND`, every match
of an overlay to a special district in `MATCHES`.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any, Literal, NamedTuple, cast, get_args

from precedent.models import Overlay
from precedent.store.base import ZoningInfo

from app.memo import controls
from app.memo import pathway as pw
from app.memo.facts import (
    BAR_LICENCE_TYPES,
    MISSING_PHRASES,
    RESTAURANT_LICENCE_TYPES,
    ConceptFacts,
    Fact,
    SiteFacts,
)
from app.models.memo import (
    TRIGGER_LABELS,
    ApprovalStatus,
    ContingentReading,
    RuleLine,
    TriggerControl,
    TriggerFamily,
    TriggerFinding,
)
from app.models.profile import ExistingBusinessChange, ExistingUse, Story

# ---- the triggers ---------------------------------------------------------------------------------------
ORDER: tuple[str, ...] = ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11")
FAMILIES: dict[str, TriggerFamily] = {
    "T1": "new_use_control",
    "T2": "special_district_use_control",
    "T3": "enlarge_or_intensify",
    "T4": "licence_in_restricted_district",
    "T5": "formula_retail",
    "T6": "nighttime_entertainment",
    "T7": "use_size",
    "T8": "laundromat_removal",
    "T9": "outdoor_activity_area",
    "T10": "amend_prior_conditions",
    "T11": "hours_of_operation",
}
# Spec section 4, most to least severe. Several entries in one trigger combine by this order.
SEVERITY: tuple[TriggerControl, ...] = (
    "not_permitted",
    "conditional",
    "not_decided",
    "code_and_practice_differ",
    "principal",
    "does_not_apply",
)
# A finding with one of these controls changes the zoning row (spec section 4).
MATTERS: frozenset[str] = frozenset(
    {"not_permitted", "conditional", "not_decided", "code_and_practice_differ"}
)
# The fixed qualifier printed after "Further review" when the Code and Planning's records differ.
PRACTICE_DIFFERS_NOTE = "Code and Planning practice differ"

Use = controls.Use
T1_USES: tuple[Use, ...] = ("bar", "restaurant", "limited_restaurant")
NIGHTTIME: Use = "nighttime_entertainment"

# ---- labels (fixed words) -------------------------------------------------------------------------------
USE_LABELS: dict[str, str] = {
    "bar": "Bar",
    "restaurant": "Restaurant",
    "limited_restaurant": "Limited Restaurant",
    "nighttime_entertainment": "Nighttime Entertainment",
}
A_USE: dict[str, str] = {
    "bar": "a Bar",
    "restaurant": "a Restaurant",
    "limited_restaurant": "a Limited Restaurant",
    "nighttime_entertainment": "Nighttime Entertainment",
}
# What the space is, or was last, used as, in the words of `existing_use_stated`.
LAST_USE_LABELS: dict[str, str] = {
    **A_USE,
    "retail": "a retail use",
    "laundromat": "a laundromat",
    "other": "another use",
    "vacant": "vacant",
}
STORY_LABELS: dict[str, str] = {
    "first": "first story",
    "second": "second story",
    "third_or_above": "third story or above",
    "basement": "basement",
}
CONTROL_WORDS: dict[str, str] = {
    "principal": "principally permitted",
    "conditional": "a conditional use",
    "not_permitted": "not permitted",
    "not_decided": "not decided",
    "does_not_apply": "does not apply",
    "code_and_practice_differ": "the Code and Planning practice differ",
}
CHANGE_WORDS: dict[str, str] = {
    "enlarge": "enlarged",
    "intensify": "intensified",
    "enlarge_and_intensify": "enlarged and intensified",
}
ENLARGES: frozenset[str] = frozenset({"enlarge", "enlarge_and_intensify"})
_LETTERS: dict[str, controls.Permission] = {"P": "principal", "C": "conditional", "NP": "not_permitted"}
# Zoning districts of Article 7 (Neighborhood Commercial), where § 186.1 governs a nonconforming use.
NC_PREFIXES: tuple[str, ...] = ("NC-", "NCD-", "NCT-")

# ---- what is not known, when it is not an input (fixed phrases) -------------------------------------------
NOT_KNOWN: dict[str, str] = {
    "district_not_carried": "the rule table does not carry this zoning district",
    "no_district": "the zoning district of the address",
    "use_not_covered": "a use the rule table covers (it has none on file for this kind of business)",
    "no_control": "a control the rule table can read for this use on this date",
    "part_of_district": "whether the address is in this part of the district: {where}",
    "table_rows": "whether the use falls under one of these rows of the table: {rows}",
    "third_street": "whether the address is inside the Third Street Alcohol Restricted Use District",
    "pre_existing_bar": (
        "whether this is a bar that already existed in the Third Street district and is reopening or moving"
    ),
    "central_soma_area": (
        "whether the address is in the area bounded by 4th, 6th, Bryant and Townsend Streets "
        "(Planning Code § 249.78(c)(2))"
    ),
    "historic_803_9": "whether the building is a historic building under Planning Code § 803.9(b)",
    "lot_3750_050": "whether the lot is Assessor's Block 3750, Lot 050",
    "table_exception": "whether this exception of the table applies: {key}",
    "mission_subarea": (
        "whether the address is east of the western boundary of the Mission Street NCT and north of Cesar "
        "Chavez Street"
    ),
    "frontage": (
        "the share of commercial frontage within 300 feet that restaurants, limited restaurants and bars take up"
    ),
    "exceptions_181": (
        "whether an exception in Planning Code § 181 lets this nonconforming use be enlarged or intensified"
    ),
    "formula_row_reach": "whether the use is one the formula retail row reaches: {applies_to}",
    "mission_fr_subdistrict": (
        "whether the address is inside the Mission Street Formula Retail Restaurant Subdistrict"
    ),
    "limited_commercial": "whether the use is a Limited Commercial Use under Planning Code § 186",
    "limited_corner_commercial": "whether the use is a Limited Corner Commercial Use",
    "large_grocery": "whether the business is a large grocery retailer as the use size row describes",
    "outdoor_limits": "whether the outdoor area meets every limit of Planning Code § 202.2(a)(7): {limits}",
    "outdoor_control": "an outdoor activity area control for this district on this date",
    "hours_not_covered": "what the hours control says for this closing time (no window on file covers it)",
    "eating_drinking_cap": (
        "the number of eating and drinking uses (Restaurants, Limited Restaurants and Bars) in the district "
        "against the cap of {max}"
    ),
    "haight_restaurant_quota": (
        "whether a new Restaurant falls within the quota of Table 719 Note (4) (no more than 3 Restaurants "
        "approved by Conditional Use)"
    ),
    "code_texts_differ": "which of two code texts that disagree Planning applied: {a} or {b}",
    "soma_other_entertainment": (
        "whether the venue was 'other entertainment' as former Planning Code § 890.37 defined it"
    ),
    "existing_hours": "whether the business already lawfully keeps these hours",
    "existing_outdoor_area": "whether the outdoor area already exists and is lawful",
    "overnight": "whether the business is open through the night until this closing time",
}


# ---- the fixed sentences (for review) -------------------------------------------------------------------
class Fixed(NamedTuple):
    """One fixed sentence. `text` is a template: its {fields} are filled from the data entry or the record the
    rule read and from the label tables above. `code_section` is a fixed reference; None means the line takes
    its section and URL from the data entry it read, or states no law."""

    text: str
    code_section: str | None = None


_HISTORIC_SECTION = "Planning Code § 202.11"
_USE_DEFINITIONS = "Planning Code § 102"

# Key = "<rule id>" or "<rule id>/<variant>"; the part before the slash is the RuleLine.rule_id. A key that
# starts with "rule." is a sentence built around a special district rule: its line takes the rule id
# "T2:<rule_id>" or "T4:<rule_id>". A key that starts with "cell." is used by T1, T3 and T6 with their own id.
TEXT: dict[str, Fixed] = {
    # every trigger
    "differs": Fixed("This control changed on {date} ({ordinance}); today it reads {today}."),
    "differs/no_ordinance": Fixed("This control changed on {date}; today it reads {today}."),
    "differs/undated": Fixed("This control is not today's control; today it reads {today}."),
    "historic": Fixed(
        "From {date} a qualifying Historic Building may read differently (Planning Code § 202.11). The "
        "Planning Director decides whether a building qualifies; the rules do not evaluate it.",
        _HISTORIC_SECTION,
    ),
    "before_start": Fixed(
        "The rule table starts on {start}. The data does not go back to {date}: the rules read the controls "
        "as they stood on {start}."
    ),
    "not_carried": Fixed("The dated rule table does not carry {district}, so this was not decided."),
    "no_district": Fixed("No zoning district is on file for this address, so this was not decided."),
    # one cell of a district table (T1, T3, T6)
    "cell": Fixed("Zoning district {district}: {a_use} on the {story} is {control} ({section}, {in_force})."),
    "cell/governed": Fixed(
        'Zoning district {district}: the table has no row for {a_use}; the row "{row}" governs, and on the '
        "{story} it reads {control} ({section}, {in_force})."
    ),
    "cell/unreadable": Fixed(
        "Zoning district {district}: the rule table holds no control it can read for {a_use} on the {story}."
    ),
    # no story is given (none stated, or the intake model read one the description does not state): no story is
    # assumed, so the cell is not decided
    "cell.story_missing": Fixed(
        "Zoning district {district}: the table sets a different control for {a_use} on different stories. Which "
        "story the business is on is not given, so no story is assumed and this is not decided until it is "
        "({section}, {in_force})."
    ),
    # no story is given, and the table reads the same on every story: the story does not change the answer
    "cell.every_story": Fixed(
        "Which story the business is on is not given. The table reads the same for {a_use} on every story, so "
        "the story does not change this."
    ),
    "cell.basement": Fixed(
        "The tables have no basement column, so the basement was read as the first story."
    ),
    "cell.subarea": Fixed(
        "In part of {district} {a_use} on the {story} is {control}: {where} ({source}). The records do not show "
        "whether this address is in that part."
    ),
    "cell.subarea/inside": Fixed(
        "{district}: an overlay on file places the address inside {where}, where {a_use} on the {story} is "
        "{control} ({source})."
    ),
    "cell.cap": Fixed(
        "{district}: the table caps the eating and drinking uses (Restaurants, Limited Restaurants and Bars) in "
        "the district at {max}, and a new one is not permitted if it would take the total above that ({source}, "
        "{in_force}). The records do not show how many there are."
    ),
    "cell.prior_use": Fixed(
        "{district}: the note on this cell is the prior-use rule of {name}, which the special district use "
        "control reads; the cell follows it: {control}."
    ),
    "cell.exception/applied": Fixed(
        "{district}: the table makes an exception that applies here: {what} is {control} ({section}, "
        "{in_force})."
    ),
    "cell.exception/not_applied": Fixed("{district}: the table's exception for {what} does not apply here."),
    "cell.exception/unplaced": Fixed(
        "{district}: the table makes {what} {control}. The rules cannot tell whether that applies here."
    ),
    "cell.exception/unknown": Fixed(
        "{district}: the table carries an exception the rules do not read ({key}: {value})."
    ),
    "cell.override": Fixed("{district}: a special district rule also reaches this cell: {override}."),
    "cell.override/elsewhere": Fixed(
        "{district}: a special district rule also reaches this cell: {override}. That rule is read under the "
        "liquor licence trigger."
    ),
    "cell.rows": Fixed(
        "{district}: the table also has the rows {rows}. The rules cannot tell whether the use falls under one."
    ),
    "cell.central_soma": Fixed(
        "The address is inside the Central SoMa Special Use District, where the table makes {a_use} {control}."
    ),
    # T1
    "T1.continues": Fixed(
        "{a_use} already exists at this address and continues, so the control for a new use was not applied. "
        "See enlarging or intensifying an existing use."
    ),
    "T1.no_use/missing": Fixed(
        "The description does not say what kind of business it is, so no use control was looked up."
    ),
    # pathway rule 1b: a bar that serves no alcohol is not a Bar, and no other use is assumed
    "T1.no_use/not_a_bar": Fixed(
        "The business is described as a bar that serves no alcohol. A Bar provides on-site alcoholic beverage "
        "sales for drinking on the premises, so this business is not a Bar, and the rules do not know which use "
        "it is instead; no use control was looked up.",
        "Planning Code § 102 (Bar)",
    ),
    "T1.no_use/not_a_bar/answered": Fixed(
        "The business is described as a bar, and you answered that it serves no alcohol. A Bar provides on-site "
        "alcoholic beverage sales for drinking on the premises, so this business is not a Bar, and the rules do "
        "not know which use it is instead; no use control was looked up.",
        "Planning Code § 102 (Bar)",
    ),
    # the same where the applicant answered "Other, or not sure" to the kind of food or drink service: no use is
    # assumed, and the answer is named
    "T1.no_use/not_a_bar/other": Fixed(
        "The business is described as a bar that serves no alcohol. A Bar provides on-site alcoholic beverage "
        "sales for drinking on the premises, so this business is not a Bar. You answered that it is another kind "
        "of food or drink service, or that you are not sure, so the rules do not know which use it is; no use "
        "control was looked up.",
        "Planning Code § 102 (Bar)",
    ),
    "T1.no_use/not_a_bar/answered/other": Fixed(
        "The business is described as a bar, and you answered that it serves no alcohol. A Bar provides on-site "
        "alcoholic beverage sales for drinking on the premises, so this business is not a Bar. You answered that "
        "it is another kind of food or drink service, or that you are not sure, so the rules do not know which "
        "use it is; no use control was looked up.",
        "Planning Code § 102 (Bar)",
    ),
    "T1.no_use/not_covered": Fixed(
        "The rule table covers bars, restaurants, cafes and nighttime entertainment. It has no use on file "
        "for this kind of business, so no use control was looked up."
    ),
    "T1.maybe_continues": Fixed(
        "The space is, or was last, {a_use}, the use proposed, and the description does not say whether that "
        "business stays. The control for a new use applies only if it does not, so this is not decided."
    ),
    "T1.entertainment": Fixed("Nighttime Entertainment is read under the nighttime entertainment trigger."),
    "T1.not_carried": Fixed(
        "The dated rule table does not carry {district}. The control was read from the zoning control table "
        "on file, which gives today's control only."
    ),
    # no story is given: the table on file gives one control, not read by story, so no story is assumed
    "T1.not_carried/story": Fixed(
        "The dated rule table does not carry {district}. The control above was read from the zoning control "
        "table on file, which gives today's control only and does not read it by story; the Planning Code may set "
        "a different control on another story. Which story the business is on is not given, so no story is "
        "assumed and this is not decided until it is."
    ),
    # no story is given, and the district's table has no story columns: the story does not change the control
    "T1.not_carried/no_story_columns": Fixed(
        "Which story the business is on is not given. The district's zoning control table has no story columns: "
        "it sets one control for {a_use} on every story, so the story does not change this."
    ),
    "T1.not_carried/use": Fixed(
        "The dated rule table does not carry {district}, and the zoning control table on file has no control "
        "for {a_use}."
    ),
    # T2 and T4: sentences built around a special district rule ({name}, {rule}, {section}, {in_force} are the
    # data's own)
    "rule": Fixed("{name}: {rule} Here: {a_use} is {control} ({section}, {in_force})."),
    "rule/licence": Fixed("{name}: {rule} Here: {control} ({section}, {in_force})."),
    "rule/nothing": Fixed("{name}: {rule} This rule asks for nothing here ({section}, {in_force})."),
    "rule/requirement": Fixed("{name}: {rule} This is a requirement, not a control ({section}, {in_force})."),
    "rule/exception": Fixed(
        "{name}: {rule} The rules do not evaluate this exception ({section}, {in_force})."
    ),
    "rule/continues": Fixed(
        "{name}: {a_use} already exists at this address and continues, so the district's rule for a new use "
        "was not applied ({section})."
    ),
    "rule/story": Fixed(
        "{name}: {rule} The rule is for the First Story, which is not among the stories stated, so it was not "
        "applied ({section}, {in_force})."
    ),
    # "<key>/answered": the same sentence where an intake answer gave the fact it rests on (`_by_origin`)
    "rule/story/answered": Fixed(
        "{name}: {rule} The rule is for the First Story, which is not among the stories you answered, so it was "
        "not applied ({section}, {in_force})."
    ),
    "rule/story_missing": Fixed(
        "{name}: {rule} The rule is for the First Story. Which story the business is on is not given, so no story "
        "is assumed and this is not decided until it is ({section}, {in_force})."
    ),
    # printed after a line of the same rule that is not decided for another input: the story is open too
    "rule/story_missing/also": Fixed(
        "{name}: this rule is for the First Story. Which story the business is on is not given either, so no "
        "story is assumed ({section}, {in_force})."
    ),
    "rule/subarea_inside": Fixed(
        "{name}: {rule} Zoning district {district} lies inside that sub-area: {control} ({section}, {in_force})."
    ),
    "rule/subarea_differs": Fixed(
        "{name}: {rule} The records do not show whether this address is in that sub-area, and Planning's own "
        "records treat restaurants elsewhere in the district as permitted: the Code and Planning practice "
        "differ here ({section}, {in_force})."
    ),
    "rule/subarea_unplaced": Fixed(
        "{name}: {rule} The records do not show whether this address is in that sub-area, so this is not "
        "decided ({section}, {in_force})."
    ),
    "rule/prior_use_qualifies": Fixed(
        "{name}: {rule} The space is, or was last, {last}, which qualifies: {a_use} is a conditional use "
        "({section}, {in_force})."
    ),
    "rule/prior_use_not": Fixed(
        "{name}: {rule} The space is, or was last, {last}, which does not qualify: {a_use} is not permitted "
        "({section}, {in_force})."
    ),
    "rule/prior_use_unknown": Fixed(
        "{name}: {rule} The description does not say what the space was last used as, so this is not decided "
        "({section}, {in_force})."
    ),
    "rule/prior_use_enlarges": Fixed(
        "{name}: {rule} The space is to be enlarged or storefronts merged, so the rule's condition that the new "
        "use will not enlarge the space is not met: {a_use} is not permitted ({section}, {in_force})."
    ),
    "rule/prior_use_same": Fixed(
        "{name}: {rule} The space is, or was last, {last}, the same use. The rule in force says no Conditional "
        "Use is needed if the use stays the same as the prior authorized use with no enlargement or "
        "intensification, and the description does not say whether it is enlarged or intensified, so this is "
        "not decided ({section}, {in_force})."
    ),
    "rule/prior_use_same_none": Fixed(
        "{name}: {rule} The space is, or was last, {last}, the same use, and the description says it is not "
        "enlarged or intensified. The rule in force needs no Conditional Use then ({section}, {in_force})."
    ),
    "rule/prior_use_same_none/answered": Fixed(
        "{name}: {rule} The space is, or was last, {last}, the same use, and you answered that it is not "
        "enlarged or intensified. The rule in force needs no Conditional Use then ({section}, {in_force})."
    ),
    "rule/prior_use_same_intensify": Fixed(
        "{name}: {rule} The space is, or was last, {last}, the same use, and it is to be intensified, so the "
        "rule's exception for a use that stays the same does not reach it: {a_use} is a conditional use "
        "({section}, {in_force})."
    ),
    "rule/use_unmapped": Fixed(
        "{name}: {rule} The data does not state which use of Planning Code § 102 these words name, so whether "
        "{a_use} is reached is not decided ({section}, {in_force})."
    ),
    "rule/maybe_continues": Fixed(
        "{name}: {rule} The space is, or was last, {a_use}, the use proposed, and the description does not say "
        "whether that business stays, so whether this rule for a new use applies is not decided ({section}, "
        "{in_force})."
    ),
    "rule/quota_unknown": Fixed(
        "{name}: {rule} A Restaurant with ABC Type {type} on the ground level could fall within the Restaurant "
        "quota, and the rules cannot count the Restaurants already approved, so this is not decided ({section}, "
        "{in_force})."
    ),
    "rule/frontage": Fixed(
        "{name}: {rule} The records do not show that share of frontage, so this is not decided ({section}, "
        "{in_force})."
    ),
    "rule/frontage_exempt": Fixed(
        "{name}: {rule} The space is stated to be a Limited Restaurant and the concept is a Restaurant, so the "
        "35% rule was not applied ({section}, {in_force})."
    ),
    "rule/frontage_exempt/answered": Fixed(
        "{name}: {rule} You answered that the space was last a Limited Restaurant, and the concept is a "
        "Restaurant, so the 35% rule was not applied ({section}, {in_force})."
    ),
    "rule/type_missing": Fixed(
        "{name}: {rule} The description does not give the licence type, so this is not decided ({section}, "
        "{in_force})."
    ),
    "rule/pours_missing": Fixed(
        "{name}: {rule} The description does not say what alcohol will be served (beer and wine, or spirits "
        "too), so the licence type is not known and this is not decided ({section}, {in_force})."
    ),
    "rule/type_not_reached": Fixed(
        "{name}: {rule} The concept needs ABC Type {type}, which is not one of the licence types this rule "
        "reaches ({types}), so it was not applied ({section}, {in_force})."
    ),
    "rule/use_not_reached": Fixed(
        "{name}: {rule} The licence types this rule reaches ({types}) are not ones the use proposed "
        "may hold, so it was not applied ({section}, {in_force})."
    ),
    "rule/type_named": Fixed(
        "{name}: {rule} The concept needs ABC Type {type}, which this rule names ({section}, {in_force})."
    ),
    "rule/new_missing": Fixed(
        "{name}: {rule} The description does not say whether the establishment is new, so this is not decided "
        "({section}, {in_force})."
    ),
    "rule/held_missing": Fixed(
        "{name}: {rule} The description does not say which licence the business already holds, so this is not "
        "decided ({section}, {in_force})."
    ),
    "rule/existing": Fixed(
        "{name}: {rule} The business already exists at this address, so the rule for a new establishment was "
        "not applied ({section}, {in_force})."
    ),
    "rule/same_type": Fixed(
        "{name}: {rule} The business already exists at this address and keeps ABC Type {type}. This is a "
        "requirement, not a control ({section}, {in_force})."
    ),
    "rule/type_changes": Fixed(
        "{name}: {rule} The business holds ABC {on_file} and the concept needs Type {type}, so the rule "
        "for a new establishment applies ({section}, {in_force})."
    ),
    "rule/change_allowed": Fixed(
        "{name}: {rule} The business holds ABC {on_file} and the concept needs Type {type}, a change this "
        "rule allows ({section}, {in_force})."
    ),
    "rule/already_held": Fixed(
        "{name}: {rule} The business already holds ABC Type {type}, so no licence is added and the rule was "
        "not applied ({section}, {in_force})."
    ),
    "rule/adds_missing": Fixed(
        "{name}: {rule} The description does not say whether the business already holds the licence, so this "
        "is not decided ({section}, {in_force})."
    ),
    "rule/no_expansion": Fixed(
        "{name}: {rule} The description says the business is not to be enlarged, so it was not applied "
        "({section}, {in_force})."
    ),
    "rule/no_expansion/answered": Fixed(
        "{name}: {rule} You answered that the business is not to be enlarged, so it was not applied "
        "({section}, {in_force})."
    ),
    "rule/change_missing": Fixed(
        "{name}: {rule} The description does not say whether the business is to be enlarged, so this is not "
        "decided ({section}, {in_force})."
    ),
    "rule/definition_note": Fixed(
        "Planning Code § 249.60(c) defines a liquor establishment so as to leave out a Restaurant that "
        "operates as a Bona Fide Eating Place and a Bar (the uses listed in § 249.60(b)(1)-(2)). The rules "
        "still read the expansion rule for these; confirm with San Francisco Planning whether it applies.",
        "Planning Code § 249.60(c)",
    ),
    "T2.none": Fixed(
        "No special use district on file for this address carries a use control the rules read, so this "
        "trigger does not apply."
    ),
    "T2.no_rule": Fixed("{names}: no use rule on file reaches this concept on {date}."),
    "T4.none": Fixed(
        "No special use district on file for this address carries a liquor licence rule the rules read, so "
        "this trigger does not apply."
    ),
    "T4.no_alcohol": Fixed(
        "The concept is not described as serving alcohol, so the liquor licence rules of {names} were not "
        "applied."
    ),
    "T4.no_alcohol/answered": Fixed(
        "You answered that no alcohol will be served, so the liquor licence rules of {names} were not applied."
    ),
    "T4.no_rule": Fixed("{names}: no liquor licence rule on file reaches this concept on {date}."),
    "T4.alcohol_not_stated": Fixed(
        "The description does not state whether alcohol will be served, so the liquor licence rules of {names} "
        "are not decided."
    ),
    # T3
    "T3.none": Fixed(
        "No existing business is described as staying, and the records show no existing use of this kind at "
        "the address, so this trigger does not apply."
    ),
    "T3.no_use": Fixed(
        "A business stays, but no use the rule table covers continues at the address. The uses proposed are "
        "read as new uses."
    ),
    "T3.no_change": Fixed(
        "{a_use} continues at this address, and the description says it is not to be enlarged or intensified."
    ),
    "T3.no_change/answered": Fixed(
        "{a_use} continues at this address, and you answered that it is not to be enlarged or intensified."
    ),
    "T3.principal": Fixed(
        "{a_use} continues at this address. A new {use} would be principally permitted here, so enlarging or "
        "intensifying it needs no Conditional Use under this rule."
    ),
    "T3.conditional_use": Fixed(
        "{a_use} continues at this address and is to be {change}. A new {use} would be a conditional use "
        "here, and a conditional use may not be significantly altered, enlarged or intensified without a new "
        "Conditional Use (Planning Code § 178; this text {in_force})."
    ),
    "T3.nonconforming_nc": Fixed(
        "{a_use} continues at this address and is to be {change}. A new {use} would not be permitted here, so "
        "the existing one is a nonconforming use. In a Neighborhood Commercial district a nonconforming use "
        "may not be significantly altered, enlarged or intensified without a Conditional Use (Planning Code "
        "§ 186.1; this text {in_force})."
    ),
    "T3.nonconforming_other": Fixed(
        "{a_use} continues at this address and is to be {change}. A new {use} would not be permitted here, so "
        "the existing one is a nonconforming use. Outside the Neighborhood Commercial districts a nonconforming "
        "use may not be enlarged or intensified, with exceptions the rules do not evaluate (Planning Code "
        "§ 181; this text {in_force}), so this is not decided."
    ),
    "T3.practice_differs": Fixed(
        "{a_use} continues at this address and is to be {change}. By the Code a new {use} here needs a "
        "Conditional Use in the sub-area, and Planning's records treat it as permitted, so whether enlarging it "
        "needs one: the Code and Planning practice differ."
    ),
    "T3.licence_missing": Fixed(
        "{a_use} continues at this address. The special district's licence rule for a new establishment turns "
        "on the licence type, which neither the description nor the records give."
    ),
    "T3.change_missing": Fixed(
        "{a_use} continues at this address. A new {use} would be {control} here, and the description does not "
        "say whether the business is to be enlarged or intensified, so this is not decided."
    ),
    "T3.change_missing/practice": Fixed(
        "{a_use} continues at this address. By the Code a new {use} here needs a Conditional Use in the "
        "sub-area, and Planning's records treat it as permitted; the description does not say whether the "
        "business is to be enlarged or intensified, so this is not decided."
    ),
    "T3.both_unknown": Fixed(
        "{a_use} continues at this address. The rules could not decide what the control for a new {use} is "
        "here, and the description does not say whether the business is to be enlarged or intensified, so "
        "this is not decided."
    ),
    "T3.standing_unknown": Fixed(
        "{a_use} continues at this address and is to be {change}, but the rules could not decide what the "
        "control for a new {use} is here, so this is not decided."
    ),
    # T5
    "T5.no": Fixed(
        "The business is stated not to be part of a chain, so the formula retail control asks for nothing."
    ),
    "T5.no/answered": Fixed(
        "You answered that the business is not part of a chain, so the formula retail control asks for nothing."
    ),
    "T5.under_count": Fixed(
        "The applicant says the chain has {count} other {locations}. Planning Code § 303.1 counts a business as "
        "formula retail from eleven other locations, so the formula retail control asks for nothing.",
        "Planning Code § 303.1(b)",
    ),
    "T5.no_use": Fixed("The concept has no use that the formula retail rows on file cover."),
    "T5.row": Fixed("Zoning district {district}: formula retail is {control} ({section}, {in_force})."),
    "T5.row/governed": Fixed(
        'Zoning district {district}: the table has no formula retail row; "{row}" governs, and formula retail '
        "is {control} ({section}, {in_force})."
    ),
    "T5.row/narrow": Fixed(
        "Zoning district {district}: the formula retail row reaches only these uses: {applies_to} ({section}, "
        "{in_force})."
    ),
    "T5.row/unreadable": Fixed(
        "Zoning district {district}: the rule table holds no formula retail control it can read on this date."
    ),
    "T5.not_permitted_for": Fixed(
        "Zoning district {district}: formula retail is not permitted for {uses} ({section}, {in_force})."
    ),
    "T5.subarea": Fixed(
        "In part of {district} formula retail is {control}{uses}: {where} ({source}). The records do not show "
        "whether this address is in that part."
    ),
    "T5.subarea/inside": Fixed(
        "Zoning district {district}: an overlay on file places the address inside {where}, where formula retail "
        "is {control}{uses} ({source})."
    ),
    "T5.central_soma": Fixed(
        "The address is inside the Central SoMa Special Use District, where formula retail is {control}."
    ),
    "T5.central_soma/not_permitted": Fixed(
        "The address is inside the Central SoMa Special Use District, where formula retail is not permitted "
        "for {uses}."
    ),
    "T5.missing": Fixed(
        "The description does not say whether the business is part of a chain, so this is not decided."
    ),
    "T5.missing/principal": Fixed(
        "The description does not say whether the business is part of a chain. Formula retail is principally "
        "permitted here whatever the answer."
    ),
    "T5.count_missing": Fixed(
        "The applicant says the business is part of a chain but not how many other locations it has. Planning "
        "Code § 303.1 counts a business as formula retail from eleven other locations, so this is not decided.",
        "Planning Code § 303.1(b)",
    ),
    "T5.count_missing/principal": Fixed(
        "The applicant says the business is part of a chain but not how many other locations it has. Formula "
        "retail is principally permitted here whatever the answer."
    ),
    "T5.operator": Fixed(
        "Note, not evaluated by the rules: a change of owner or operator of an existing formula retail "
        "business needs a new Conditional Use in the cases Planning Code § 178(c)(3) lists (limbs {limbs}; "
        "this text {in_force})."
    ),
    # T6
    "T6.none": Fixed("No entertainment is described, so this trigger does not apply."),
    "T6.none/answered": Fixed("You answered that there is no entertainment, so this trigger does not apply."),
    "T6.limited_live": Fixed(
        "The entertainment described is a Limited Live Performance. A venue with only that is not Nighttime "
        "Entertainment (Planning Code § 102), so this trigger does not apply."
    ),
    "T6.limited_live/answered": Fixed(
        "You answered that the entertainment is a Limited Live Performance. A venue with only that is not "
        "Nighttime Entertainment (Planning Code § 102), so this trigger does not apply."
    ),
    "T6.maybe_continues": Fixed(
        "The space is, or was last, Nighttime Entertainment, the use proposed, and the description does not say "
        "whether that business stays. The control for a new use applies only if it does not, so this is not "
        "decided."
    ),
    "T6.continues": Fixed(
        "Nighttime Entertainment already exists at this address and continues, so the control for a new use "
        "was not applied. See enlarging or intensifying an existing use."
    ),
    "T6.kind_missing": Fixed(
        "Entertainment is described, but not whether it is a Limited Live Performance or a Place of "
        "Entertainment. Nighttime Entertainment is not principally permitted here on every story read, so "
        "this is not decided."
    ),
    "T6.not_stated": Fixed(
        "The description does not state whether there will be entertainment. Nighttime Entertainment is not "
        "principally permitted here on every story read, so this is not decided."
    ),
    "T6.not_stated/principal": Fixed(
        "The description does not state whether there will be entertainment. Nighttime Entertainment is "
        "principally permitted here on every story read, whatever the kind."
    ),
    "T6.kind_missing/principal": Fixed(
        "Entertainment is described, but not whether it is a Limited Live Performance or a Place of "
        "Entertainment. Nighttime Entertainment is principally permitted here on every story read, whatever "
        "the kind."
    ),
    # T7
    "T7.not_new": Fixed("The use is not new, merged or enlarged, so the use size control was not applied."),
    "T7.none": Fixed("Zoning district {district} states no use size threshold ({section}, {in_force})."),
    "T7.below": Fixed(
        "Zoning district {district}: a use below {threshold} square feet is principally permitted, and "
        "{area} square feet is below it ({section}, {in_force})."
    ),
    "T7.conditional": Fixed(
        "Zoning district {district}: a use of {threshold} square feet or more needs a Conditional Use, and "
        "{area} square feet is at or over it ({section}, {in_force})."
    ),
    "T7.cap": Fixed(
        "Zoning district {district}: a use of {cap} square feet or more is not permitted, and {area} square "
        "feet is at or over it ({section}, {in_force})."
    ),
    "T7.missing": Fixed(
        "Zoning district {district}: a use of {threshold} square feet or more needs a Conditional Use. The "
        "description does not give the floor area, so this is not decided ({section}, {in_force})."
    ),
    "T7.change_missing": Fixed(
        "The use already exists at this address, and the description does not say whether it is to be "
        "enlarged, so this is not decided."
    ),
    "T7.exemption": Fixed("The row records an exemption the rules do not evaluate: {exemption}"),
    "T7.restaurant": Fixed(
        "Zoning district {district}: {source} says a Restaurant larger than {larger} square feet needs no "
        "Conditional Use for its size, and the concept is a Restaurant of {area} square feet, so the use size "
        "control asks for nothing ({section}, {in_force})."
    ),
    "T7.texts_differ": Fixed(
        "Zoning district {district}: the table row and {other} disagree on this date. Under {other} a use of "
        "{area} square feet is {alternative}; under the row it is {control}. Which text Planning applied is not "
        "established, so this is not decided ({section}, {in_force})."
    ),
    "T7.existing_space": Fixed(
        "The space is, or was last, {last}. The use size limit does not say whether taking over an existing "
        "space is a new use of that size, and Zoning Administrator Interpretation 121.2 lets a use over the "
        "threshold change to a different use in the same floor area without a Conditional Use where the floor "
        "area does not grow significantly ({section}, {in_force})."
    ),
    "T7.existing_space/missing": Fixed(
        "The description does not give {missing}, so whether the use size control applies is not decided."
    ),
    "T7.existing_space/same": Fixed(
        "The floor area does not grow and no storefronts are merged, so the use size control does not apply."
    ),
    "T7.existing_space/district": Fixed(
        "In zoning district {district} a new Conditional Use is needed to change a use over the threshold on "
        "this date ({section}, {in_force}), so the threshold is read."
    ),
    "T7.corner_cap": Fixed(
        "Zoning district {district}: a Limited Corner Commercial Use may not be larger than {cap} square "
        "feet. The rules cannot tell whether the use is one ({section}, {in_force})."
    ),
    "T7.only_if": Fixed(
        "Zoning district {district}: a use is not permitted only if: {only_if}. The rules cannot tell whether "
        "that applies ({section}, {in_force})."
    ),
    # T8
    "T8.no_data": Fixed("The rule table holds no laundromat rule, so this trigger does not apply."),
    "T8.outside": Fixed(
        "Removing a laundromat needed a Conditional Use from {start} to {end} (Planning Code § 202.12). That "
        "rule was not in force on {date}, so this trigger does not apply."
    ),
    "T8.conditional": Fixed(
        "The space is, or was last, a laundromat. From {start} to {end} a change of use or demolition of a "
        "laundromat needed a Conditional Use (Planning Code § 202.12)."
    ),
    "T8.not_laundromat": Fixed(
        "The space is, or was last, {last}, not a laundromat, so the laundromat rule in force from {start} to "
        "{end} asks for nothing."
    ),
    "T8.missing": Fixed(
        "From {start} to {end} a change of use or demolition of a laundromat needed a Conditional Use "
        "(Planning Code § 202.12). The description does not say what the space was last used as, so this is "
        "not decided."
    ),
    "T8.last_day": Fixed(
        "The data does not settle whether {end} or {day_before} was the last day of this rule (Planning Code "
        "§ 202.12 ran for three years from {start})."
    ),
    # T9
    "T9.none": Fixed("No outdoor area is described, so this trigger does not apply."),
    "T9.none/answered": Fixed("You answered that there is no outdoor area, so this trigger does not apply."),
    "T9.sidewalk": Fixed(
        "The outdoor area is on the sidewalk, which is public right of way and takes a different approval, "
        "so this trigger does not apply."
    ),
    "T9.front": Fixed(
        "Zoning district {district}: an outdoor activity area in front is {control} ({section}, {in_force})."
    ),
    "T9.elsewhere": Fixed(
        "Zoning district {district}: an outdoor activity area elsewhere on the lot is {control} ({section}, "
        "{in_force})."
    ),
    "T9.limits": Fixed(
        "Zoning district {district}: an outdoor activity area elsewhere on the lot is a conditional use, "
        "unless it keeps within the limits of Planning Code § 202.2(a)(7): {limits}. The description does not "
        "show that it does, so this is not decided ({section}, {in_force})."
    ),
    "T9.limits/bar": Fixed(
        "Zoning district {district}: an outdoor activity area elsewhere on the lot is a conditional use, "
        "unless it keeps within the limits of Planning Code § 202.2(a)(7). One limit is that it is not "
        "operated with a Bar, and the concept is a Bar: a conditional use ({section}, {in_force})."
    ),
    "T9.limits/rooftop": Fixed(
        "Zoning district {district}: an outdoor activity area elsewhere on the lot is a conditional use, "
        "unless it keeps within the limits of Planning Code § 202.2(a)(7). One limit is that it is on the "
        "ground level, and the area is on the rooftop: a conditional use ({section}, {in_force})."
    ),
    "T9.missing": Fixed(
        "An outdoor area is described, but not where it is. Zoning district {district}: in front it is "
        "{front}, elsewhere on the lot {elsewhere} ({section}, {in_force}), so this is not decided."
    ),
    "T9.missing/principal": Fixed(
        "An outdoor area is described, but not where it is. Zoning district {district} principally permits an "
        "outdoor activity area in front and elsewhere on the lot ({section}, {in_force})."
    ),
    # the outdoor area is there by the answer that alcohol will be served in it (app.memo.intake)
    "T9.missing/answered": Fixed(
        "You answered that alcohol will be served in an outdoor area, but not where the area is. Zoning district "
        "{district}: in front it is {front}, elsewhere on the lot {elsewhere} ({section}, {in_force}), so this "
        "is not decided."
    ),
    "T9.missing/principal/answered": Fixed(
        "You answered that alcohol will be served in an outdoor area, but not where the area is. Zoning district "
        "{district} principally permits an outdoor activity area in front and elsewhere on the lot ({section}, "
        "{in_force})."
    ),
    "T9.citywide_route": Fixed(
        "Zoning district {district}: the district's own row does not mention Planning Code § 202.2(a)(7). The "
        "route is read from § 202.2(a)(7) itself, which reaches {classes} districts ({section}, {in_force})."
    ),
    "T9.existing": Fixed(
        "An existing business may keep an outdoor area it already lawfully has. The rules cannot tell whether "
        "this one is new and do not decide that."
    ),
    "T9.unreadable": Fixed(
        "Zoning district {district}: the rule table holds no outdoor activity area control it can read for "
        "this place on this date."
    ),
    # T10
    "T10.amends": Fixed(
        "The description says the conditions of an earlier approval are to be changed. Changing a condition "
        "of a Conditional Use goes through the same procedure as a new Conditional Use (Planning Code "
        "§ 303(e); this text {in_force})."
    ),
    "T10.no": Fixed(
        "The description says no condition of an earlier approval is to be changed, so this trigger does not "
        "apply."
    ),
    "T10.amends/answered": Fixed(
        "You answered that the conditions of an earlier approval are to be changed. Changing a condition of a "
        "Conditional Use goes through the same procedure as a new Conditional Use (Planning Code § 303(e); this "
        "text {in_force})."
    ),
    "T10.no/answered": Fixed(
        "You answered that no condition of an earlier approval is to be changed, so this trigger does not apply."
    ),
    "T10.none": Fixed(
        "The description does not say that the conditions of an earlier approval are to be changed, and the "
        "rules found no earlier Conditional Use at the address with a business that stays, so this trigger "
        "does not apply."
    ),
    "T10.missing": Fixed(
        "An earlier Conditional Use decision is on file at this address ({record}) and a business stays. The "
        "description does not say whether the proposal changes a condition of that approval, so this is not "
        "decided (Planning Code § 303(e))."
    ),
    # T11
    "T11.no_limit": Fixed(
        "Zoning district {district} has no hours of operation control on file ({section}, {in_force}), so this "
        "trigger does not apply."
    ),
    "T11.principal": Fixed(
        "Hours: {closing} falls inside the principally permitted hours ({windows}; {section}, {in_force})."
    ),
    "T11.conditional": Fixed(
        "Hours: {closing} falls inside hours that need a Conditional Use ({windows}; {section}, {in_force})."
    ),
    "T11.not_permitted": Fixed(
        "Hours: {closing} falls inside hours that are not permitted ({windows}; {section}, {in_force})."
    ),
    "T11.not_covered": Fixed(
        "Hours: {closing} falls outside every window of the hours control on file ({windows}; {section}, "
        "{in_force}), so this is not decided."
    ),
    "T11.missing": Fixed(
        "Hours: the description gives no closing time, and hours that are not principally permitted begin "
        "before 2 a.m. here ({windows}; {section}, {in_force}), so this is not decided."
    ),
    "T11.missing/late": Fixed(
        "Hours: the description gives no closing time. Hours that are not principally permitted begin at "
        "2 a.m. or later here ({windows}; {section}, {in_force}); the rules did not check a closing time after "
        "2 a.m."
    ),
    "T11.overnight": Fixed(
        "Hours: the description says the business stays open through the night to {closing}, so every hour from "
        "{start} to then was read ({windows}; {section}, {in_force})."
    ),
    "T11.morning": Fixed(
        "Hours: {closing} is a morning close, and the description does not say whether the business is open "
        "through the night until then, so this is not decided ({windows}; {section}, {in_force})."
    ),
    "T11.morning/answered": Fixed(
        "Hours: you answered {closing}, a morning close, and not whether the business is open through the night "
        "until then, so this is not decided ({windows}; {section}, {in_force})."
    ),
    "T11.limited_commercial": Fixed(
        "Hours: for a Limited Commercial Use under Planning Code § 186 the windows are different "
        "({windows}). The rules cannot tell whether the use is one, so this is not decided."
    ),
    "T11.existing": Fixed(
        "An existing business may keep hours it already lawfully keeps. The rules cannot read those hours and "
        "do not decide that."
    ),
}


# ---- which special districts cover an address -----------------------------------------------------------
class Match(NamedTuple):
    """How one special district of the dated data is tied to an address."""

    key: str  # the data's key
    sections: tuple[str, ...]  # an overlay matches when its code section names one of these section numbers
    words: tuple[str, ...]  # ... and its name holds every one of these words (lower case)
    not_words: tuple[str, ...]  # ... and none of these
    districts: tuple[str, ...]  # zoning districts the data's overlay_hint says it is coterminous with
    why: str


MATCHES: tuple[Match, ...] = (
    Match(
        "mission_alcohol_sud",
        ("249.60",),
        ("mission", "alcohol"),
        (),
        (),
        "Map polygon 'Mission Alcohol Restrict'. The polygon is wider than any one zoning district, so no "
        "district alone shows it.",
    ),
    Match(
        "north_beach_sud",
        (),
        (),
        (),
        ("NCD-NORTH BEACH",),
        "overlay_hint: no map polygon; § 780.3(a) made it coterminous with NCD-NORTH BEACH, and after the "
        "repeal the surviving rules sit in that district's own table. Keyed on the zoning district alone.",
    ),
    Match(
        "haight_alcohol_rusd",
        ("781.9",),
        ("haight", "alcohol"),
        ("lower",),
        ("NCD-HAIGHT",),
        "Map polygon 'Haight Street Alcohol Restricted Use'; overlay_hint: § 781.9(b) makes it coterminous "
        "with NCD-HAIGHT, so the zoning district shows it as well. 'Lower Haight' is a different district.",
    ),
    Match(
        "third_street_alcohol_rud",
        ("249.62",),
        ("alcohol",),
        (),
        (),
        "Map polygon '3rd St Alcohol Restrict' (section 249.62 and 'alcohol' in the name). The overlay_hint "
        "does not say it is coterminous with a district, so NCD-BAYVIEW alone does not show it.",
    ),
    Match(
        "soma_youth_family_sud",
        ("249.38", "249.40A"),
        ("youth", "family"),
        (),
        (),
        "Map polygon 'Youth and Family Zone'; § 249.40A until 2023-06-02, § 249.38 from 2023-06-03.",
    ),
    Match(
        "calle_24_sud",
        ("249.59",),
        ("calle 24",),
        (),
        (),
        "Map polygon 'Calle 24 SUD'.",
    ),
)
# Special districts of the data that are not matched, and why.
NOT_MATCHED: dict[str, str] = {
    "lower_haight_alcohol_rud": (
        "The data records reaches_bars_or_restaurants: false. It deals with Liquor Stores only."
    ),
}
# The Central SoMa Special Use District is not a special district of the data; the MUR rows carry controls for
# the part of MUR inside it, and an overlay places an address there.
CENTRAL_SOMA_SECTION = "249.78"
CENTRAL_SOMA_WORDS: tuple[str, ...] = ("central soma",)


class SubArea(NamedTuple):
    """A sub-area of a special district that the map has no polygon for."""

    districts: frozenset[str]  # zoning districts that lie inside it
    not_known: str  # NOT_KNOWN key naming it
    why: str


SUBAREAS: dict[str, SubArea] = {
    "mission_f": SubArea(
        frozenset({"NCT-MISSION", "NCT-24TH-MISSION"}),
        "mission_subarea",
        "§ 249.60(f): east of the western boundary of the Mission Street NCT and north of Cesar Chavez "
        "Street. Spec section 1a: in NCT-MISSION and NCT-24TH-MISSION the address is inside that area.",
    ),
}


# ---- the special district rules the triggers use ----------------------------------------------------------
BindingKind = Literal[
    # T2
    "use",  # the rule's control for a new use
    "use_subarea",  # ... in a sub-area the map cannot place
    "use_prior",  # ... only in a space last occupied by one of the uses in `prior_use`
    "use_frontage",  # ... barred over a share of frontage the records do not show
    "use_frontage_exempt",  # the exemption from that rule the facts can decide
    # T4
    "new_establishment",  # the rule's control for a new establishment with one of `types`
    "adds_licence",  # the rule's control for a use that adds a licence of one of `types`
    "expansion",  # the rule's control for an existing licensed business that is enlarged
    "type_named",  # the rule says a licence of one of `types` is not reached, or is allowed
    "use_named",  # the rule says a licensed use of `uses` is allowed
    "requirement",  # a condition, printed as a line
    "continuation",  # an existing establishment continues only with the same licence type
    "licence_change",  # a change of licence to one of `types` does not break continuation
    "exception_note",  # an exception to another rule that the rules do not evaluate
    "quota_exception",  # a quota under which the rule `with_rule` does not bar the use; the rules cannot count it
]
TypeSets = Mapping[str | None, frozenset[str]]  # by the start date of the rule's version (None: before 2022)
_NO_TYPES: frozenset[str] = frozenset()
_EATING_AND_DRINKING: frozenset[str] = frozenset(T1_USES)


@dataclass(frozen=True)
class Binding:
    """One special district rule of the data, bound to the trigger that reads it."""

    rule_id: str  # the data's rule_id
    trigger: Literal["T2", "T4"]
    kind: BindingKind
    why: str  # the reason for this row, for review
    uses: frozenset[str] = frozenset()  # the § 102 uses it reaches (empty: any)
    types: frozenset[str] = _NO_TYPES  # the ABC licence types it reaches (empty: any)
    types_by_start: TypeSets | None = None  # ... where the list differs between versions of the rule
    prior_use: TypeSets | None = None  # use_prior: the last uses that qualify, by version
    first_story: bool = False  # the rule is for the First Story only
    subarea: str | None = None  # SUBAREAS key: the rule reaches that sub-area only
    districts: frozenset[str] = frozenset()  # the rule reaches these zoning districts only (empty: any)
    overrides: str | None = None  # where this rule applies, the rule of that rule_id is not read
    with_rule: str | None = None  # printed together with the rule of that rule_id
    when: Literal["always", "new_bar"] = "always"  # requirement: when it is printed
    reaches_expansion: bool = False  # T2: also reaches the physical expansion of an existing use
    requirement: bool = False  # the data's control is "requirement"
    could_stop: bool = False  # a requirement that could stop the licence (alcohol row: potential blocker)
    # use_prior: the versions (by start date) whose text carries the proviso "no Conditional Use shall be required
    # if the use remains the same as the prior authorized use, with no enlargement or intensification of use"
    same_use_proviso: frozenset[str | None] = frozenset()
    # use: the versions (by start date) whose words the data does not map onto a use of § 102
    unmapped: frozenset[str | None] = frozenset()

    def types_on(self, rule: controls.Rule) -> frozenset[str]:
        if self.types_by_start is None:
            return self.types
        return self.types_by_start[_iso(rule.source.in_force_from)]

    def prior_on(self, rule: controls.Rule) -> frozenset[str]:
        return (self.prior_use or {}).get(_iso(rule.source.in_force_from), frozenset())


def _iso(date: dt.date | None) -> str | None:
    return date.isoformat() if date is not None else None


_HAIGHT_ON_SALE = frozenset({"40", "41", "42", "47", "48", "57"})
_THIRD_ON_SALE = frozenset({"40", "42", "48", "57"})
_NORTH_BEACH_RESTAURANT = frozenset({"02", "23", "41", "47", "49", "59", "75"})

BINDINGS: tuple[Binding, ...] = (
    # Mission Alcoholic Beverage Special Use District (§ 249.60)
    Binding(
        "mission.restaurant_bona_fide_eating_place",
        "T4",
        "use_named",
        "(b)(1)(A): a Restaurant that is a Bona Fide Eating Place may serve alcohol; no licence control.",
        uses=frozenset({"restaurant"}),
    ),
    Binding(
        "mission.music_venue_type_90",
        "T4",
        "type_named",
        "(b)(1)(E), from 2024-01-14: a Type 90 venue may serve alcohol.",
        types=frozenset({"90"}),
    ),
    Binding(
        "mission.new_or_relocated_bar",
        "T2",
        "use",
        "(b)(2)(C): a new or relocated Bar is always a Conditional Use. The use itself is made conditional.",
        uses=frozenset({"bar"}),
    ),
    Binding(
        "mission.new_bar_licence_from_bar_in_district",
        "T4",
        "requirement",
        "(b)(2)(C): a new Bar must use a licence transferred from a Bar inside the district. A requirement; "
        "the alcohol row turns it into a potential blocker.",
        uses=frozenset({"bar"}),
        when="new_bar",
        requirement=True,
        could_stop=True,
    ),
    Binding(
        "mission.existing_liquor_establishment_expansion",
        "T4",
        "expansion",
        "(c)(3): an existing liquor establishment may expand only with Conditional Use. Spec section 1a reads "
        "it for every existing licensed business that is enlarged; the data notes that (c) leaves out a "
        "Bona Fide Eating Place and a Bar (the uses of (b)(1)-(2)), and that Planning has applied (c)(3) to a "
        "Restaurant. A line says so for a Restaurant and for a Bar.",
    ),
    Binding(
        "mission.good_neighbor_policies",
        "T4",
        "requirement",
        "(d): operating conditions for every liquor establishment in the district. A requirement.",
        requirement=True,
    ),
    Binding(
        "mission.restaurant_cu_sub_area",
        "T2",
        "use_subarea",
        "(f)(1): any proposed Restaurant in the sub-area needs Conditional Use, with or without alcohol.",
        uses=frozenset({"restaurant"}),
        subarea="mission_f",
    ),
    Binding(
        "mission.type_75_new_prohibited_sub_area",
        "T4",
        "new_establishment",
        "(f)(2): no new Type 75 establishment in the sub-area.",
        types=frozenset({"75"}),
        subarea="mission_f",
    ),
    # North Beach (§ 780.3 until 2025-12-14, then Table 722)
    Binding(
        "north_beach.prior_use.bar",
        "T2",
        "use_prior",
        "A new Bar on the First Story only in a space last occupied by a Bar, without enlarging the space (both "
        "versions). Until 2025-12-14 the lead-in of § 780.3(c)(1) also says no Conditional Use is needed if the "
        "use stays the same with no enlargement or intensification; the data's quote of today's Note (5) is "
        "cut before that point, so the proviso is read for the first version only.",
        uses=frozenset({"bar"}),
        prior_use={None: frozenset({"bar"}), "2025-12-15": frozenset({"bar"})},
        first_story=True,
        same_use_proviso=frozenset({None}),
    ),
    Binding(
        "north_beach.prior_use.restaurant",
        "T2",
        "use_prior",
        "A new Restaurant on the First Story only in a space last occupied by a Restaurant or a Bar; from "
        "2025-12-15 a Limited Restaurant space qualifies too. The same-use proviso as for a Bar (first version).",
        uses=frozenset({"restaurant"}),
        prior_use={
            None: frozenset({"restaurant", "bar"}),
            "2025-12-15": frozenset({"limited_restaurant", "restaurant", "bar"}),
        },
        first_story=True,
        same_use_proviso=frozenset({None}),
    ),
    Binding(
        "north_beach.prior_use.limited_restaurant",
        "T2",
        "use_prior",
        "A new Limited Restaurant on the First Story only in a space last occupied by a Limited Restaurant, "
        "a Restaurant or a Bar until 2025-12-14; principally permitted from 2025-12-15. The same-use proviso as "
        "for a Bar (first version).",
        uses=frozenset({"limited_restaurant"}),
        prior_use={None: frozenset({"limited_restaurant", "restaurant", "bar"}), "2025-12-15": frozenset()},
        first_story=True,
        same_use_proviso=frozenset({None}),
    ),
    Binding(
        "north_beach.restaurant_liquor_licence",
        "T4",
        "adds_licence",
        "§ 780.3(c)(2)(A): a Restaurant selling alcohol under Types 02, 23, 41, 47, 49, 59 or 75 on the First "
        "Story: conditional until 2025-12-14, nothing after.",
        uses=frozenset({"restaurant"}),
        types=_NORTH_BEACH_RESTAURANT,
        first_story=True,
    ),
    Binding(
        "north_beach.restaurant_liquor_licence_records",
        "T4",
        "requirement",
        "The records a Restaurant with that approval must give the Department. A requirement, printed with "
        "the licence rule when it is conditional.",
        with_rule="north_beach.restaurant_liquor_licence",
        requirement=True,
    ),
    Binding(
        "north_beach.music_venue_type_90",
        "T4",
        "type_named",
        "§ 780.3(c)(2)(B), 2024-01-14 to 2025-12-14: a Type 90 venue may serve alcohol.",
        types=frozenset({"90"}),
    ),
    # Haight Street Alcohol Restricted Use Subdistrict (§ 781.9)
    Binding(
        "haight.new_on_sale_establishment",
        "T4",
        "new_establishment",
        "(c)(2): a new on-sale establishment (Types 40, 41, 42, 47, 48, 57): not permitted until 2024-01-13, "
        "conditional from 2024-01-14.",
        types=_HAIGHT_ON_SALE,
    ),
    Binding(
        "haight.restaurant_quota_exception",
        "T4",
        "quota_exception",
        "Until 2024-01-13: a capped number of new Restaurants (Types 41 and 47, the data's applies_to) on the "
        "ground level by Conditional Use. The data's control is C: the rules cannot count the places taken, so "
        "for such a Restaurant the not permitted rule for a new on-sale establishment becomes not decided (the "
        "spec's 'not permitted with a capped restaurant exception' is read with the data's control). Bars and "
        "the other types stay not permitted.",
        uses=frozenset({"restaurant"}),
        types=frozenset({"41", "47"}),
        first_story=True,
        with_rule="haight.new_on_sale_establishment",
    ),
    Binding(
        "haight.licence_types_excluded_from_on_sale",
        "T4",
        "type_named",
        "(c)(1)(B): licence types that are not 'on-sale liquor establishments'; Types 64 and 90 added on "
        "2024-01-14.",
        types_by_start={
            None: frozenset({"51", "52", "59", "60", "61", "67", "70", "75"}),
            "2024-01-14": frozenset({"51", "52", "59", "60", "61", "64", "67", "70", "75", "90"}),
        },
    ),
    Binding(
        "haight.existing_establishment_continuation",
        "T4",
        "continuation",
        "An existing establishment continues only with the same type of licence. With another type the rule "
        "for a new establishment applies (rule table v1 reads § 781.9 the same way).",
        requirement=True,
    ),
    Binding(
        "haight.existing_establishment_licence_change",
        "T4",
        "licence_change",
        "A change to Type 64 or 90 does not break continuation, from 2024-01-14. Type 21 to Type 20 is an "
        "off-sale change the rules do not read.",
        types_by_start={None: frozenset(), "2024-01-14": frozenset({"64", "90"})},
    ),
    # Third Street Alcohol Restricted Use District (§ 249.62)
    Binding(
        "third.new_on_sale_establishment",
        "T4",
        "new_establishment",
        "(a)(1): no new on-sale establishment (Types 40, 42, 48, 57).",
        types=_THIRD_ON_SALE,
    ),
    Binding(
        "third.licence_types_excluded_from_on_sale",
        "T4",
        "type_named",
        "(c): licence types that are not 'on-sale liquor establishments' (a Restaurant with Type 41 or 47).",
        types=frozenset({"41", "47", "51", "52", "59", "60", "61", "67", "70", "75"}),
    ),
    Binding(
        "third.exceptions_type_2_and_type_23",
        "T4",
        "type_named",
        "(a)(2): Types 02 and 23 are outside the prohibition. The temporary-use and pre-2003 application "
        "limbs of the same rule turn on facts no input carries and are not read.",
        types=frozenset({"02", "23"}),
    ),
    Binding(
        "third.type_42_bayview_ncd",
        "T4",
        "new_establishment",
        "A new Type 42 establishment in the Bayview NCD: not permitted until 2025-04-06, conditional from "
        "2025-04-07. Read in NCD-BAYVIEW only, where it replaces the general rule for Type 42.",
        types=frozenset({"42"}),
        districts=frozenset({"NCD-BAYVIEW"}),
        overrides="third.new_on_sale_establishment",
    ),
    Binding(
        "third.pre_existing_continuation",
        "T4",
        "continuation",
        "An existing establishment continues only with the same type of licence (rule table v1 reads "
        "§ 249.62 the same way).",
        requirement=True,
    ),
    Binding(
        "third.change_to_type_41",
        "T4",
        "licence_change",
        "A change to Type 41 does not break continuation. Type 21 to Type 20 is an off-sale change the rules "
        "do not read.",
        types=frozenset({"41"}),
    ),
    Binding(
        "third.operating_requirements",
        "T4",
        "requirement",
        "(b): operating conditions for every liquor establishment in the district. A requirement.",
        requirement=True,
    ),
    # SoMa Youth and Family Special Use District (§ 249.40A, then § 249.38)
    Binding(
        "soma_yf.restaurant",
        "T2",
        "use",
        "A Restaurant needs Conditional Use anywhere in the district.",
        uses=frozenset({"restaurant"}),
    ),
    Binding(
        "soma_yf.bar",
        "T2",
        "use",
        "A Bar needs Conditional Use anywhere in the district.",
        uses=frozenset({"bar"}),
    ),
    Binding(
        "soma_yf.entertainment",
        "T2",
        "use",
        "From 2023-06-03 (§ 249.38) Nighttime Entertainment needs Conditional Use. Until 2023-06-02 the list "
        "named 'Other entertainment' (§ 890.37); the data does not state how that maps onto today's uses, so for "
        "that version the rule is not decided for Nighttime Entertainment.",
        uses=frozenset({"nighttime_entertainment"}),
        unmapped=frozenset({None}),
    ),
    Binding(
        "soma_yf.limited_restaurant",
        "T2",
        "use",
        "A Limited Restaurant is not in the district's list: no control added.",
        uses=frozenset({"limited_restaurant"}),
    ),
    # Calle 24 Special Use District (§ 249.59)
    Binding(
        "calle24.frontage_35_percent",
        "T2",
        "use_frontage",
        "(d)(1): a new Restaurant, Limited Restaurant or Bar, or the physical expansion of one, is barred "
        "where those uses take more than 35% of the commercial frontage within 300 feet. The records do not "
        "show that share.",
        uses=_EATING_AND_DRINKING,
        reaches_expansion=True,
    ),
    Binding(
        "calle24.frontage_35_percent_exemptions",
        "T2",
        "use_frontage_exempt",
        "(d)(1): a change from an existing Limited Restaurant to a Restaurant is outside the 35% rule. The "
        "filing-date limb (applications filed by 2017-03-31) is before the data starts and is not read.",
        uses=frozenset({"restaurant"}),
        with_rule="calle24.frontage_35_percent",
    ),
    Binding(
        "calle24.no_use_specific_conditional_use",
        "T2",
        "use",
        "§ 249.59 itself does not make a Restaurant, Limited Restaurant or Bar a Conditional Use.",
        uses=_EATING_AND_DRINKING,
    ),
)
BOUND: dict[str, Binding] = {b.rule_id: b for b in BINDINGS}

# Every other rule of the matched special districts, and why no trigger reads it.
_OFF_SALE = "Off-sale (a Liquor Store or a grocery): not a use the rule table covers."
_OTHER_USE = "A use the rule table does not cover."
_RELOCATION = "A relocation or a closure: no input says a business is moving, closing or reopening."
_CROSS_REFERENCE = "A cross-reference or a definition; it states no control."
_NOT_BUILT = "Spec section 1: this family was seen once and is not built."
_FINDING = "A finding the Planning Commission makes; neither a control nor a condition on the operator."
UNBOUND: dict[str, str] = {
    "mission.new_liquor_store": _OFF_SALE,
    "mission.non_profit_theater": _OTHER_USE,
    "mission.entertainment_with_integrated_restaurant": _OTHER_USE,
    "mission.single_screen_movie_theater": _OTHER_USE,
    "mission.grocery_5000_or_smaller": _OFF_SALE,
    "mission.grocery_over_5000": _OFF_SALE,
    "mission.existing_liquor_establishment_nonconforming": (
        "The frame for (c)(1) to (c)(3): it states no approval of its own. The expansion rule (c)(3) is bound."
    ),
    "mission.existing_liquor_establishment_relocation": _RELOCATION,
    "mission.existing_liquor_establishment_temporary_closure": _RELOCATION,
    "mission.type_75_existing_may_relocate": _RELOCATION,
    "mission.sec_781_8_cross_reference": _CROSS_REFERENCE,
    "north_beach.non_profit_theater": _OTHER_USE,
    "north_beach.storefront_merger": _NOT_BUILT + " (storefront merger control)",
    "north_beach.specialty_grocery_use_size": _OFF_SALE,
    "north_beach.specialty_food_manufacturing": _OTHER_USE,
    "north_beach.hours": (
        "The same windows as the hours row of NCD-NORTH BEACH, which T11 reads (a test holds the two equal)."
    ),
    "north_beach.legacy_business_replacement": _NOT_BUILT + " (legacy business replacement)",
    "north_beach.conditional_use_extra_finding": _FINDING,
    "haight.new_off_sale_establishment": _OFF_SALE,
    "haight.on_sale_definition": (
        _CROSS_REFERENCE + " Its licence types are the `types` of haight.new_on_sale_establishment."
    ),
    "haight.exemptions_before_2024": _OTHER_USE + " (temporary uses, earlier applications, a movie theater)",
    "haight.existing_establishment_relocation": _RELOCATION,
    "third.new_off_sale_establishment": _OFF_SALE,
    "third.on_sale_definition": (
        _CROSS_REFERENCE + " Its licence types are the `types` of third.new_on_sale_establishment."
    ),
    "third.temporary_closure_and_reestablishment": _RELOCATION,
    "third.relocation_within_district.bar": _RELOCATION,
    "third.relocation_within_district.other": _RELOCATION,
    "third.sec_782_cross_reference": _CROSS_REFERENCE,
    "soma_yf.liquor_store": _OFF_SALE,
    "calle24.first_story_merger": _NOT_BUILT + " (storefront merger control)",
    "calle24.legacy_business_replacement": _NOT_BUILT + " (legacy business replacement)",
    "calle24.conditional_use_extra_findings": _FINDING,
}


# ---- controls for part of a district (the data's extra fields) --------------------------------------------
class TableException(NamedTuple):
    """One key of a use row's `exceptions`."""

    kind: Literal["licence_type", "licence_type_other", "pre_existing", "area", "unplaced"]
    what: str  # in words, for the line
    not_known: str  # NOT_KNOWN key, named when the rules cannot tell whether it applies
    columns: tuple[str, ...] = ("first", "second", "third")  # the table columns it reaches
    # licence_type: the ABC type that meets it; licence_type_other: the one type the cell's control is for (any
    # other type, except the Restaurant types of § 102, meets the exception)
    licence_type: str | None = None
    overlay_section: str | None = None  # area: it lies inside the special district of this section


TABLE_EXCEPTIONS: dict[str, TableException] = {
    # NCD-BAYVIEW, Bar, Table 737 Note 7 ("C (first and second story)")
    "bar_with_abc_licence_type_42": TableException(
        "licence_type",
        "a Bar with an ABC Type 42 licence",
        "third_street",
        columns=("first", "second"),
        licence_type="42",
    ),
    # ... and Note 7's two exceptions for an establishment that already existed (the first and second story:
    # the quote reads "NP(7) | NP(7) | NP")
    "reestablishment_under_249_62_a_3_B_iv": TableException(
        "pre_existing",
        "a liquor establishment that already existed and reopens under its licence issued before 19 May 2003 "
        "(Planning Code § 249.62(a)(3)(B)(iv))",
        "pre_existing_bar",
        columns=("first", "second"),
    ),
    "relocation_of_pre_existing_bar_under_249_62_a_3_B_v": TableException(
        "pre_existing",
        "a Bar that already existed in the district and moves inside it (Planning Code § 249.62(a)(3)(B)(v))",
        "pre_existing_bar",
        columns=("first", "second"),
    ),
    # NCD-INNER CLEMENT, Bar, Table 716 Note 3 (the data's `exceptions`): C only for a wine and beer bar that
    # keeps only an ABC Type 42; other types, except those of the § 102 Restaurant definition, are not permitted
    "bar_licence_other_than_abc_type_42_note_3": TableException(
        "licence_type_other",
        "a Bar with an ABC licence other than Type 42 (Table 716 Note 3)",
        "table_exception",
        columns=("first",),
        licence_type="42",
    ),
    # NCD-HAIGHT, Restaurant, until 2024-01-13, Table 719 Note (4) (the data's `exceptions`)
    "haight_restaurant_quota_note_4": TableException(
        "unplaced",
        "a new Restaurant on the ground level within the quota of Table 719 Note (4)",
        "haight_restaurant_quota",
        columns=("first",),
    ),
    # MUR, Nighttime Entertainment
    "area_bounded_by_4th_6th_bryant_townsend_249_78_c_2": TableException(
        "area",
        "Nighttime Entertainment in the area bounded by 4th, 6th, Bryant and Townsend Streets (Planning Code "
        "§ 249.78(c)(2))",
        "central_soma_area",
        overlay_section=CENTRAL_SOMA_SECTION,
    ),
    "historic_building_803_9_b": TableException(
        "unplaced",
        "Nighttime Entertainment in a historic building under Planning Code § 803.9(b)",
        "historic_803_9",
    ),
    "assessors_block_3750_lot_050": TableException(
        "unplaced", "Nighttime Entertainment on Assessor's Block 3750, Lot 050", "lot_3750_050"
    ),
}


def _overlay_section(extra: Mapping[str, Any], where: str) -> str | None:
    """The section of the overlay that places a sub-area entry, when one does (`subarea_overlay_sections`: the
    sub-area's name, as its entry's `where` begins, to the section the overlay's code section names)."""
    sections = extra.get("subarea_overlay_sections")
    if not isinstance(sections, Mapping):
        return None
    return next((str(v) for k, v in sections.items() if where.startswith(str(k))), None)


# The special district a use row's `special_district_override` speaks of, by zoning district.
OVERRIDE_DISTRICTS: dict[str, str] = {"NCD-BAYVIEW": "third_street_alcohol_rud"}
# The use size row of C-3-G bars a use only over this floor area and only for a large grocery retailer
# (`not_permitted_only_if`: "over 120,000 gross sq ft AND ...").
ONLY_IF_OVER_SQFT = 120_000
# Keys of a version's extra fields that the triggers read, by row; and keys that are the readers' bookkeeping
# (how a version was established or settled), which state no control. A test holds every key of the data in one
# of the two, so a new kind of sub-area control cannot be passed over silently.
EXTRA_KEYS_READ: dict[str, frozenset[str]] = {
    "use": frozenset(
        {
            "subarea_controls",
            "exceptions",
            "special_district_override",
            "exception_rows",
            "exception_rows_by_date",
            "eating_drinking_cap",
            "subarea_overlay_sections",
            "in_central_soma_sud",
        }
    ),
    "formula_retail": frozenset(
        {
            "not_permitted_for_in_subarea",
            "formula_retail_restaurant_rule",
            "principal_exception",
            "in_central_soma_sud",
            "conditional_where",
            "conflicting_text",
            "limited_commercial_use_sec_186_control",
            "limited_commercial_use_sec_186",
            "code_texts_differ",  # the flag beside `conflicting_text`, which carries the other text
            "subarea_overlay_sections",
        }
    ),
    "use_size": frozenset(
        {
            "limited_corner_commercial_use_cap_sqft",
            "limited_corner_commercial_use_max_sqft",
            "not_permitted_only_if",
            "conditional_not_required_for",
            "other_code_text_figures",
            "code_texts_differ",  # the flag beside `other_code_text_figures`, which carries the other text
        }
    ),
    "outdoor_activity_area": frozenset(),
    "hours": frozenset({"windows_sec_186_limited_commercial_use"}),
}
EXTRA_KEYS_BOOKKEEPING: frozenset[str] = frozenset(
    {
        "governed_by",  # typed by app.memo.controls
        "governing_control",
        "windows_not_stated",  # typed by app.memo.controls (Hours.not_stated)
        "windows_not_printed",  # typed by app.memo.controls (HoursWindow.printed)
        "settled",
        "control_changed_at_this_edge",
        "cells_changed_from_previous",
        "change_kind",
        "reworded_by",
        "not_permitted_for_as_read",  # the same control as in_central_soma_sud, in the reader's words
        "in_central_soma_sud_as_read",
        "table_row_present",
        "windows_source",
    }
)


# ---- small helpers --------------------------------------------------------------------------------------
def _line(
    key: str,
    /,
    *,
    rule_id: str | None = None,
    section: str | None = None,
    url: str | None = None,
    cites: Iterable[str] = (),
    **fields: Any,
) -> RuleLine:
    """One rule line from its fixed sentence. `section` and `url` are the data entry's own, used when the
    sentence carries no fixed reference."""
    fixed = TEXT[key]
    text = fixed.text.format(**{"section": section or "", **fields})
    return RuleLine(
        rule_id=rule_id or key.split("/", 1)[0],
        text=text[:1].upper() + text[1:],
        code_section=fixed.code_section if fixed.code_section is not None else (section or None),
        source_url=url or None,
        citations=sorted(set(cites)),
    )


def _by_origin(key: str, concept: ConceptFacts, field: str) -> str:
    """The sentence for a line that rests on one profile field: `key` when the description gave the field, its
    "<key>/answered" sentence ("You answered ...") when an intake answer did (`ConceptFacts.by_answer`). A line
    never says "the description says" for a fact only an answer gave."""
    return f"{key}/answered" if concept.by_answer(field) else key


def _worst(found: Iterable[TriggerControl]) -> TriggerControl:
    """The most severe control, by the order of spec section 4. "does_not_apply" when there is none."""
    return min(found, key=SEVERITY.index, default="does_not_apply")


def _asks(control: TriggerControl) -> str:
    """What a control asks for. "principal" and "does_not_apply" both ask for nothing, so a trigger that goes
    from one to the other has not changed (`differs_today`)."""
    return "nothing" if control in ("principal", "does_not_apply") else control


def _each_once(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _square_feet(value: int) -> str:
    return f"{value:,}"


def _listed(words: Sequence[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _letter(value: Any) -> controls.Permission | None:
    """'C' or 'C (first and second story)' -> 'conditional'. None when the value names no control."""
    head = str(value).split(" ", 1)[0].rstrip(":;,") if isinstance(value, str) else ""
    return _LETTERS.get(head)


@dataclass(frozen=True)
class _Reading:
    """One entry read: its answer, the lines that say what was read, and what is not known."""

    control: TriggerControl
    lines: tuple[RuleLine, ...]
    missing: tuple[str, ...] = ()
    source: controls.Source | None = None  # the version of the entry that was used
    historic: bool = False  # the data carries a Historic Buildings passage for this cell on the date
    dated: bool = False  # read from the dated data


@dataclass(frozen=True)
class _Result:
    """One trigger on one date."""

    control: TriggerControl
    lines: tuple[RuleLine, ...]
    missing: tuple[str, ...] = ()
    in_force_from: dt.date | None = None
    ordinance: str | None = None
    historic: bool = False
    dated: bool = False


def _result(readings: Sequence[_Reading], *, control: TriggerControl | None = None) -> _Result:
    """The readings of one trigger combined: the most severe control, every line, everything not known, and
    the version of the first reading that gives that control."""
    answer = control or _worst(r.control for r in readings)
    deciding = next((r for r in readings if r.control == answer and r.source is not None), None)
    source = deciding.source if deciding is not None else None
    return _Result(
        control=answer,
        lines=tuple(line for r in readings for line in r.lines),
        missing=_each_once(m for r in readings for m in r.missing),
        in_force_from=source.in_force_from if source is not None else None,
        ordinance=source.ordinance if source is not None else None,
        historic=any(r.historic for r in readings),
        dated=any(r.dated for r in readings),
    )


def _outside(key: str, **fields: Any) -> _Result:
    """The trigger does not apply; one line says why."""
    return _Result("does_not_apply", (_line(key, **fields),))


# ---- which special districts cover the address ------------------------------------------------------------
@dataclass(frozen=True)
class _Special:
    key: str
    name: str
    citations: tuple[str, ...]  # "overlay:<id>" for each overlay that showed it, else "zoning:<district>"


def _overlay_matches(
    overlay: Overlay, sections: Sequence[str], words: Sequence[str], not_words: Sequence[str]
) -> bool:
    name = overlay.name.lower()
    return (
        any(pw._names_section(overlay.code_section, s) for s in sections)
        and all(w in name for w in words)
        and not any(w in name for w in not_words)
    )


def _specials(zoning: ZoningInfo | None, overlays: Sequence[Overlay]) -> tuple[_Special, ...]:
    rows = pw._sorted_overlays(overlays)
    found: list[_Special] = []
    for match in MATCHES:
        cited = [
            f"overlay:{o.id}"
            for o in rows
            if _overlay_matches(o, match.sections, match.words, match.not_words)
        ]
        if not cited and zoning is not None and zoning.district in match.districts:
            cited = [f"zoning:{zoning.district}"]
        if cited:
            found.append(_Special(match.key, controls.special_district(match.key).name, tuple(cited)))
    order = controls.special_district_keys()
    return tuple(sorted(found, key=lambda s: order.index(s.key)))


def special_district_keys(zoning: ZoningInfo | None, overlays: Sequence[Overlay]) -> tuple[str, ...]:
    """The special districts of the dated data that cover the address, in the data's order (`MATCHES`): matched
    from the overlays at the point by their code section and name, and from the zoning district where the
    data's overlay_hint says the special district is coterminous with one."""
    return tuple(s.key for s in _specials(zoning, overlays))


# ---- the context of one evaluation ------------------------------------------------------------------------
@dataclass(frozen=True)
class _Ctx:
    concept: ConceptFacts
    site: SiteFacts
    zoning: ZoningInfo | None
    overlays: tuple[Overlay, ...]  # in id order
    on: dt.date  # the date the controls are read for
    district: str | None
    covered: bool  # the dated data carries the district
    specials: tuple[_Special, ...]
    central_soma: tuple[str, ...]  # citations of the overlays that place the address in the Central SoMa SUD
    uses: tuple[Use, ...]  # the concept's uses, in USE_ORDER
    business_continues: bool
    continuing: frozenset[str]  # the uses that already exist at the address and continue
    # the uses proposed that the description states the space is, or was last, used as, where the description
    # does not say whether that business stays: whether the control for a new use applies is not known
    maybe_continuing: frozenset[str] = frozenset()
    # every trigger is read as for a new use (`evaluate(as_new=True)`): kept when an input is supposed
    as_new: bool = False

    @property
    def zone(self) -> str:
        """The district code of a covered district."""
        assert self.district is not None
        return self.district

    @property
    def cites(self) -> tuple[str, ...]:
        return (f"zoning:{self.district}",) if self.district else ()

    @property
    def stories(self) -> tuple[Story, ...]:
        """The stories stated; empty when none is given (`story_missing`). Never a default."""
        return self.concept.stories.value

    @property
    def story_missing(self) -> bool:
        return self.concept.story_missing

    @property
    def reads_first(self) -> bool:
        """A story stated is the first story (the basement is read as the first). False when none is given: a
        caller checks `story_missing` first, as that is not decided, not "not the first story"."""
        return any(story in ("first", "basement") for story in self.stories)

    def special(self, key: str) -> _Special | None:
        return next((s for s in self.specials if s.key == key), None)

    @property
    def last_uses(self) -> tuple[str, ...]:
        """What the space is, or was last, used as: the uses stated (leaving out "vacant", which says nothing
        about the last use), then the use the records show."""
        given = set(self.concept.existing_use_stated.value)
        stated = [u for u in get_args(ExistingUse) if u in given and u != "vacant"]  # in a fixed order
        shown = self.site.existing_use
        return _each_once([*stated, *([shown] if shown else [])])


def _continuing(concept: ConceptFacts, site: SiteFacts, uses: Sequence[str]) -> tuple[bool, frozenset[str]]:
    """Does a business continue at the address, and which of the uses proposed already exist and continue."""
    shown = site.existing_use
    stated = set(concept.existing_use_stated.value)
    if not concept.changes_existing_business.missing:
        if stated or shown:
            known = stated | ({shown} if shown else set())
            return True, frozenset(u for u in uses if u in known)
        return True, frozenset(u for u in uses if u != NIGHTTIME)
    if shown is not None and shown in uses:
        return True, frozenset({shown})
    return False, frozenset()


def _context(
    concept: ConceptFacts,
    site: SiteFacts,
    zoning: ZoningInfo | None,
    overlays: Sequence[Overlay],
    on: dt.date,
) -> _Ctx:
    rows = tuple(pw._sorted_overlays(overlays))
    district = zoning.district if zoning is not None else None
    base = _Ctx(
        concept=concept,
        site=site,
        zoning=zoning,
        overlays=rows,
        on=on,
        district=district,
        covered=district is not None and controls.covers(district),
        specials=_specials(zoning, rows),
        central_soma=tuple(
            f"overlay:{o.id}"
            for o in rows
            if _overlay_matches(o, (CENTRAL_SOMA_SECTION,), CENTRAL_SOMA_WORDS, ())
        ),
        uses=(),
        business_continues=False,
        continuing=frozenset(),
    )
    return _with_concept(base, concept)


def _with_concept(ctx: _Ctx, concept: ConceptFacts) -> _Ctx:
    """The context for `concept` at the same address: the parts read from the concept are read again (the uses,
    and which of them continue). An `as_new` context stays one."""
    uses = tuple(u for u in controls.USES if u in concept.planning_uses.value)
    if ctx.as_new:
        return replace(ctx, concept=concept, uses=uses)
    business_continues, continuing = _continuing(concept, ctx.site, uses)
    stated = set(concept.existing_use_stated.value) - {"vacant"}
    maybe = (
        frozenset(u for u in uses if u in stated and u not in continuing)
        if concept.changes_existing_business.missing
        else frozenset()
    )
    return replace(
        ctx,
        concept=concept,
        uses=uses,
        business_continues=business_continues,
        continuing=continuing,
        maybe_continuing=maybe,
    )


def _not_carried(ctx: _Ctx, *missing: str) -> _Result:
    """T5, T6, T7, T9, T11 in a district the dated data does not carry."""
    if ctx.district is None:
        return _Result(
            "not_decided", (_line("no_district"),), _each_once([*missing, NOT_KNOWN["no_district"]])
        )
    return _Result(
        "not_decided",
        (_line("not_carried", district=ctx.district, cites=ctx.cites),),
        _each_once([*missing, NOT_KNOWN["district_not_carried"]]),
    )


# ---- one cell of a district table (T1, T3, T6) --------------------------------------------------------------
def _row_line(
    key: str,
    ctx: _Ctx,
    source: controls.Source,
    /,
    *,
    rule_id: str | None = None,
    also_cites: Iterable[str] = (),
    **fields: Any,
) -> RuleLine:
    """A line about a row of the district's table: the section and URL are the row's own."""
    return _line(
        key,
        rule_id=rule_id,
        section=source.section,
        url=source.source_url,
        cites=[*ctx.cites, *also_cites],
        district=ctx.zone,
        in_force=source.in_force_text,
        **fields,
    )


def _cell(ctx: _Ctx, use: Use, story: Story, tid: str) -> _Reading:
    """One use at one story on the date, with the controls for part of the district applied where the facts
    place them and named where they do not."""
    cell = controls.use_control(ctx.zone, use, story, ctx.on)
    extra = cell.extra
    rid = f"{tid}.cell"
    words = {"a_use": A_USE[use], "story": STORY_LABELS[story]}
    historic = cell.historic_buildings is not None
    if cell.permission is None:
        line = _row_line("cell/unreadable", ctx, cell.source, rule_id=rid, **words)
        return _Reading("not_decided", (line,), (NOT_KNOWN["no_control"],), cell.source, historic, True)
    base: controls.Permission = cell.permission
    if cell.governed:
        first = _row_line(
            "cell/governed",
            ctx,
            cell.source,
            rule_id=rid,
            row=cell.governing_row or "",
            control=CONTROL_WORDS[base],
            **words,
        )
    else:
        first = _row_line("cell", ctx, cell.source, rule_id=rid, control=CONTROL_WORDS[base], **words)
    lines: list[RuleLine] = [first]
    open_: list[str] = []  # what would settle a control for part of the district that could change the answer

    # the address is inside the Central SoMa Special Use District, where the row gives another control
    inside = _letter(extra.get("in_central_soma_sud"))
    if inside is not None and ctx.central_soma:
        base = inside
        lines.append(
            _row_line(
                "cell.central_soma",
                ctx,
                cell.source,
                rule_id=f"{tid}.central_soma",
                also_cites=ctx.central_soma,
                a_use=A_USE[use],
                control=CONTROL_WORDS[base],
            )
        )

    # exceptions by licence type, by area or by a fact no input carries
    exceptions = extra.get("exceptions")
    for key, value in exceptions.items() if isinstance(exceptions, Mapping) else ():
        known = TABLE_EXCEPTIONS.get(key)
        control = _letter(value)
        if known is None or control is None:
            lines.append(
                _row_line(
                    "cell.exception/unknown",
                    ctx,
                    cell.source,
                    rule_id=f"{tid}.exception",
                    key=key,
                    value=str(value),
                )
            )
            open_.append(NOT_KNOWN["table_exception"].format(key=key))
            continue
        if cell.column not in known.columns or control == base:
            continue
        rid_exception = f"{tid}.exception"
        applies: bool | None = None
        not_known = NOT_KNOWN[known.not_known]
        needed = ctx.concept.licence_type
        if known.kind == "licence_type":
            applies = None if needed.missing else needed.value == known.licence_type
            not_known = ctx.concept.licence_type_phrase
        elif known.kind == "licence_type_other":
            # the cell's control is for one licence type; any other type (but the § 102 Restaurant types) meets
            # the exception
            applies = (
                None
                if needed.missing
                else needed.value != known.licence_type and needed.value not in RESTAURANT_LICENCE_TYPES
            )
            not_known = ctx.concept.licence_type_phrase
        elif known.kind == "pre_existing":
            # a concept that takes out a new licence is not an establishment that already existed, and a use
            # that stays at its address (its standing as new, T3) is neither reopening nor moving
            new_licence = ctx.concept.alcohol_transaction.value == "new_licence"
            applies = False if new_licence or tid == "T3" or use in ctx.continuing else None
        elif known.kind == "area" and known.overlay_section is not None:
            placed = any(pw._names_section(o.code_section, known.overlay_section) for o in ctx.overlays)
            applies = None if placed else False
        if applies:
            base = control
            lines.append(
                _row_line(
                    "cell.exception/applied",
                    ctx,
                    cell.source,
                    rule_id=rid_exception,
                    what=known.what,
                    control=CONTROL_WORDS[control],
                )
            )
        elif applies is None:
            lines.append(
                _row_line(
                    "cell.exception/unplaced",
                    ctx,
                    cell.source,
                    rule_id=rid_exception,
                    what=known.what,
                    control=CONTROL_WORDS[control],
                )
            )
            open_.append(not_known)
        else:
            lines.append(
                _row_line(
                    "cell.exception/not_applied", ctx, cell.source, rule_id=rid_exception, what=known.what
                )
            )

    # a different control in part of the district: applied where an overlay on file places the address, named
    # where the records cannot place it
    subareas = extra.get("subarea_controls")
    for sub in subareas if isinstance(subareas, tuple) else ():
        control = _letter(sub.get(cell.column))
        if control is None or control == base:
            continue
        where = str(sub.get("where", ""))
        section = _overlay_section(extra, where)
        if section is not None:
            placing = [f"overlay:{o.id}" for o in ctx.overlays if pw._names_section(o.code_section, section)]
            if placing:
                base = control
                lines.append(
                    _row_line(
                        "cell.subarea/inside",
                        ctx,
                        cell.source,
                        rule_id=f"{tid}.subarea",
                        also_cites=placing,
                        control=CONTROL_WORDS[control],
                        where=where,
                        source=str(sub.get("source", "")),
                        **words,
                    )
                )
            continue  # no overlay places the address there: it is outside, as for Central SoMa
        lines.append(
            _row_line(
                "cell.subarea",
                ctx,
                cell.source,
                rule_id=f"{tid}.subarea",
                control=CONTROL_WORDS[control],
                where=where,
                source=str(sub.get("source", "")),
                **words,
            )
        )
        open_.append(NOT_KNOWN["part_of_district"].format(where=where))

    # a cap on the number of eating and drinking uses in the district (Table 754 Note 7). A use that stays at
    # its address is already counted, so the cap is not read for its standing as new (T3).
    cap = extra.get("eating_drinking_cap")
    if (
        isinstance(cap, Mapping)
        and cell.column in (cap.get("columns") or ())
        and base != "not_permitted"
        and tid != "T3"
    ):
        most = cap["max_uses"]
        lines.append(
            _row_line("cell.cap", ctx, cell.source, rule_id=f"{tid}.cap", max=most, source=cap["source"])
        )
        open_.append(NOT_KNOWN["eating_drinking_cap"].format(max=most))

    # a special district rule the row says also reaches the cell
    override = extra.get("special_district_override")
    if isinstance(override, str) and override:
        special = ctx.special(OVERRIDE_DISTRICTS.get(ctx.zone, ""))
        if special is not None:  # T4 reads that district's rules for this address
            lines.append(
                _row_line(
                    "cell.override/elsewhere", ctx, cell.source, rule_id=f"{tid}.override", override=override
                )
            )
        elif _letter(override) != base:
            lines.append(
                _row_line("cell.override", ctx, cell.source, rule_id=f"{tid}.override", override=override)
            )
            open_.append(NOT_KNOWN["third_street"])

    # other rows of the table that could govern instead (where they change inside the version, as they read on
    # the date)
    rows = extra.get("exception_rows")
    dated = extra.get("exception_rows_by_date")
    if isinstance(dated, tuple):
        found = controls.version_on(dated, ctx.on)
        rows = found.version.get("rows") if found is not None else None
    if isinstance(rows, tuple) and rows:
        named = _listed([str(r) for r in rows])
        lines.append(_row_line("cell.rows", ctx, cell.source, rule_id=f"{tid}.rows", rows=named))
        open_.append(NOT_KNOWN["table_rows"].format(rows=named))

    # the cell's note is a special district's prior-use rule (North Beach, Note (5)): T1 follows that rule's
    # reading for the same use, so the zoning row and the special district use control say the same thing
    if tid == "T1" and cell.column == "first" and not open_ and base == "conditional":
        prior = _prior_use(ctx, use)
        if prior:
            answer = _worst(r.control for _, r in prior)
            if answer != base:
                lines.append(
                    _row_line(
                        "cell.prior_use",
                        ctx,
                        cell.source,
                        rule_id=f"{tid}.prior_use",
                        name=_listed(list(dict.fromkeys(name for name, _ in prior))),
                        control=CONTROL_WORDS[answer],
                    )
                )
                missing = _each_once(m for _, r in prior for m in r.missing)
                return _Reading(answer, tuple(lines), missing, cell.source, historic, True)

    if open_:
        return _Reading("not_decided", tuple(lines), _each_once(open_), cell.source, historic, True)
    return _Reading(base, tuple(lines), (), cell.source, historic, True)


# Every column of the district tables (the basement is read as the first story).
EVERY_STORY: tuple[Story, ...] = ("first", "second", "third_or_above")


def _use_reading(ctx: _Ctx, use: Use, tid: str) -> _Reading:
    """A use on every story stated: the most severe cell. No story given: no story is assumed. Every column is
    read; when they all read the same (the same control and the same open inputs) the story does not change the
    answer and that reading stands, with a line saying so. Otherwise the cell depends on the story and is not
    decided, naming it, whatever any one story would read (a story that would need a Conditional Use or bar the
    use included)."""
    if ctx.story_missing:
        every = [_cell(ctx, use, story, tid) for story in EVERY_STORY]
        same = every[0]
        if all(r.control == same.control and r.missing == same.missing for r in every[1:]):
            printed = {(line.rule_id, line.text): line for r in every for line in r.lines}
            told = _line("cell.every_story", rule_id=f"{tid}.story", a_use=A_USE[use])
            return _Reading(
                same.control,
                (*printed.values(), told),
                same.missing,
                same.source,
                any(r.historic for r in every),
                True,
            )
        # the row's own version, section and Historic Buildings passage, which are the same on every story
        row = controls.use_control(ctx.zone, use, "first", ctx.on)
        line = _row_line("cell.story_missing", ctx, row.source, rule_id=f"{tid}.story", a_use=A_USE[use])
        historic = row.historic_buildings is not None
        return _Reading("not_decided", (line,), (MISSING_PHRASES["stories"],), row.source, historic, True)
    readings = [_cell(ctx, use, story, tid) for story in ctx.stories]
    lines = [line for r in readings for line in r.lines]
    missing = [m for r in readings for m in r.missing]
    if "basement" in ctx.stories:
        lines.append(_line("cell.basement", rule_id=f"{tid}.basement"))
    answer = _worst(r.control for r in readings)
    deciding = next(r for r in readings if r.control == answer)
    return _Reading(
        answer,
        tuple(lines),
        _each_once(missing),
        deciding.source,
        any(r.historic for r in readings),
        True,
    )


# The districts whose zoning control table has no story columns, as the dated data's own notes record them ("Table
# 209.1 has no story columns (its columns are RH-1(D), RH-1, RH-1(S), RH-2 and RH-3)", and so for Tables 209.2,
# 209.3, 210.1, 210.2 and 827): one control holds on every story. For such a district the dated data does not
# carry, the control of the table on file (a first-story control) is the control on every story, so a missing
# story does not change it. Any other district's table on file is read for the first story only.
NO_STORY_COLUMNS: frozenset[str] = frozenset(
    {
        "RH-1(D)", "RH-1", "RH-1(S)", "RH-2", "RH-3",  # Table 209.1
        "RM-1", "RM-2", "RM-3", "RM-4",  # Table 209.2
        "RC-3", "RC-4",  # Table 209.3
        "C-2",  # Table 210.1
        "C-3-O", "C-3-O(SD)", "C-3-R", "C-3-G", "C-3-S",  # Table 210.2
        "RH DTR",  # Table 827
    }
)  # fmt: skip


def _v1_reading(ctx: _Ctx, use: Use) -> _Reading:
    """A district the dated data does not carry: Bar and Restaurant from the zoning control table on file and
    the overlays, as rule table v1 reads them (its rules 2a and 2b, with its own functions and sentences)."""
    zoning = ctx.zoning
    if zoning is None:
        return _Reading("not_decided", (_line("no_district"),), (NOT_KNOWN["no_district"],))
    base = (
        pw._control_for(use, zoning.bar_permission, zoning.restaurant_permission)
        if use in ("bar", "restaurant")
        else None
    )
    if base is None:
        line = _line("T1.not_carried/use", district=zoning.district, a_use=A_USE[use], cites=ctx.cites)
        return _Reading("not_decided", (line,), (NOT_KNOWN["district_not_carried"],))
    section, cited = pw._district_ref(zoning, ctx.overlays)
    lines = [
        pw._line(
            "zoning.use_control",
            district=zoning.district,
            a_use=pw._a(use),
            control=pw.CONTROL_PHRASES[base],
            section=pw._in_brackets(section),
            citations=cited,
            code_section=section,
            source_url=zoning.source_url,
        )
    ]
    counted = [base]
    by_overlay = False  # an overlay's own control was counted: the table on file reads it for the first story
    for o in ctx.overlays:
        if pw._subarea_rule(use, o) is not None:
            continue  # v1 rule 2d; here the dated rule of the special district reads it (T2)
        control = pw._control_for(use, o.bar_permission, o.restaurant_permission)
        if control is None:
            continue
        ref = pw._short_section(o.code_section)
        if o.kind == "alcohol_sud" and not ctx.concept.serves_alcohol:
            lines.append(
                pw._line(
                    "zoning.sud_control/not_stated"
                    if ctx.concept.alcohol_not_stated
                    else "zoning.sud_control/not_applied",
                    name=o.name,
                    section=pw._in_brackets(ref),
                    citations=[f"overlay:{o.id}"],
                    code_section=ref,
                    source_url=o.source_url,
                )
            )
            continue
        counted.append(control)
        if o.kind in pw._DISTRICT_KINDS and control == base:
            continue
        by_overlay = True
        lines.append(
            pw._line(
                "zoning.sud_control",
                name=o.name,
                a_use=pw._a(use),
                control=pw.CONTROL_PHRASES[control],
                section=pw._in_brackets(ref),
                citations=[f"overlay:{o.id}"],
                code_section=ref,
                source_url=o.source_url,
            )
        )
    worst = max(counted, key=lambda c: pw._RESTRICTION[c])
    if ctx.story_missing and (zoning.district not in NO_STORY_COLUMNS or by_overlay):
        # the table on file gives first-story controls: with no story given it is never read as the first story
        lines.append(_line("T1.not_carried/story", district=zoning.district, cites=ctx.cites))
        return _Reading("not_decided", tuple(pw._merge(lines)), (MISSING_PHRASES["stories"],))
    lines.append(_line("T1.not_carried", district=zoning.district, cites=ctx.cites))
    if ctx.story_missing:
        lines.append(_line("T1.not_carried/no_story_columns", rule_id="T1.story", a_use=A_USE[use]))
    answers: dict[str, TriggerControl] = {
        "principal": "principal",
        "conditional": "conditional",
        "prohibited": "not_permitted",
    }
    return _Reading(answers[worst], tuple(pw._merge(lines)))


def _as_new(ctx: _Ctx, use: Use, tid: str) -> _Reading:
    """The control for a new use of this kind at the address on the date: the district's cells."""
    return _use_reading(ctx, use, tid) if ctx.covered else _v1_reading(ctx, use)


# ---- T1: new use control ------------------------------------------------------------------------------------
def _t1(ctx: _Ctx) -> _Result:
    concept = ctx.concept
    if not ctx.uses:
        if concept.not_a_bar:  # pathway rule 1b
            key = _by_origin("T1.no_use/not_a_bar", concept, "serves_alcohol")
            if concept.food_service_given == "other" and concept.by_answer("food_service"):
                key += "/other"  # the kind of food or drink service, answered "Other, or not sure"
            line = _line(key)
            return _Result("not_decided", (line,), concept.missing(["planning_uses"]))
        if concept.planning_uses.missing:
            return _Result("not_decided", (_line("T1.no_use/missing"),), (MISSING_PHRASES["planning_uses"],))
        return _Result("not_decided", (_line("T1.no_use/not_covered"),), (NOT_KNOWN["use_not_covered"],))
    readings: list[_Reading] = []
    for use in ctx.uses:
        if use == NIGHTTIME:
            readings.append(_Reading("does_not_apply", (_line("T1.entertainment"),)))
        elif use in ctx.continuing:
            readings.append(_Reading("does_not_apply", (_line("T1.continues", a_use=A_USE[use]),)))
        elif use in ctx.maybe_continuing:
            line = _line("T1.maybe_continues", a_use=A_USE[use])
            readings.append(_Reading("not_decided", (line,), (MISSING_PHRASES["changes_existing_business"],)))
        else:
            readings.append(_as_new(ctx, use, "T1"))
    return _result(readings)


# ---- T2: special district use control -------------------------------------------------------------------------
def _rule_line(
    key: str, tid: str, special: _Special, rule: controls.Rule, /, *, cites: Iterable[str] = (), **fields: Any
) -> RuleLine:
    """A line built around one special district rule of the data."""
    return _line(
        key,
        rule_id=f"{tid}:{rule.rule_id}",
        section=rule.source.section,
        url=rule.source.source_url,
        cites=[*special.citations, *cites],
        name=special.name,
        rule=rule.rule,
        in_force=rule.source.in_force_text,
        **fields,
    )


def _rule_control(rule: controls.Rule) -> TriggerControl:
    if rule.control in ("principal", "conditional", "not_permitted"):
        return cast(TriggerControl, rule.control)
    return "principal"  # a requirement states no control


def _rules_of(ctx: _Ctx, special: _Special) -> dict[str, controls.Rule]:
    return {rule.rule_id: rule for rule in controls.special_rules(special.key, ctx.on)}


def _t2_use(
    ctx: _Ctx,
    special: _Special,
    rule: controls.Rule,
    binding: Binding,
    use: Use,
    rules: Mapping[str, controls.Rule],
    *,
    as_new: bool,
    on_first: bool = False,
) -> _Reading | None:
    """One T2 rule for one use. `as_new`: read it as for a new use although the use continues (T3). `on_first`:
    read it for the First Story (a cell of the first-story column, or a rule for the First Story only read with
    no story given)."""
    change = ctx.concept.changes_existing_business.value
    expands = binding.reaches_expansion and use in ctx.continuing and change in ENLARGES

    def reading(control: TriggerControl, key: str, /, *missing: str, **fields: Any) -> _Reading:
        line = _rule_line(key, "T2", special, rule, a_use=A_USE[use], **fields)
        return _Reading(control, (line,), tuple(missing), rule.source, False, True)

    if use in ctx.continuing and not expands and not as_new:
        return reading("does_not_apply", "rule/continues")
    control = _rule_control(rule)
    if binding.first_story and ctx.story_missing and not on_first:
        # no story given: on any story but the first the rule does not apply, so it is read for the First Story;
        # that reading stands when it asks for nothing there, else the story decides it and is named
        first = _t2_use(ctx, special, rule, binding, use, rules, as_new=as_new, on_first=True)
        if first is None or first.control in ("principal", "does_not_apply"):
            return first
        if first.control == "not_decided":
            also = _rule_line("rule/story_missing/also", "T2", special, rule)
            missing = _each_once([*first.missing, MISSING_PHRASES["stories"]])
            return _Reading(
                "not_decided", (*first.lines, also), missing, first.source, first.historic, first.dated
            )
        return reading("not_decided", "rule/story_missing", MISSING_PHRASES["stories"])
    if binding.first_story and not on_first and not ctx.reads_first:
        return reading("does_not_apply", _by_origin("rule/story", ctx.concept, "stories"))
    if use in ctx.maybe_continuing and not as_new and control != "principal":
        return reading("not_decided", "rule/maybe_continues", MISSING_PHRASES["changes_existing_business"])
    if _iso(rule.source.in_force_from) in binding.unmapped:
        return reading("not_decided", "rule/use_unmapped", NOT_KNOWN["soma_other_entertainment"])
    if binding.kind == "use_subarea" and binding.subarea is not None:
        area = SUBAREAS[binding.subarea]
        if ctx.district in area.districts:
            return reading(
                control, "rule/subarea_inside", district=ctx.district, control=CONTROL_WORDS[control]
            )
        return reading("code_and_practice_differ", "rule/subarea_differs")
    if binding.kind == "use_prior" and control != "principal":
        allowed = binding.prior_on(rule)
        last = ctx.last_uses
        named = _listed([LAST_USE_LABELS[u] for u in last])
        concept = ctx.concept
        if concept.merges_storefronts.value is True or concept.changes_existing_business.value in ENLARGES:
            # the rule's condition that the new use will not enlarge the space fails
            return reading("not_permitted", "rule/prior_use_enlarges")
        if use in last and _iso(rule.source.in_force_from) in binding.same_use_proviso:
            # the same use as the prior authorized use: no Conditional Use if not enlarged or intensified
            change = concept.changes_existing_business.value
            if change == "none":
                key = _by_origin("rule/prior_use_same_none", concept, "changes_existing_business")
                return reading("principal", key, last=named)
            if change == "intensify":
                return reading(control, "rule/prior_use_same_intensify", last=named)
            missing = (MISSING_PHRASES["changes_existing_business"], *concept.missing(["merges_storefronts"]))
            return reading("not_decided", "rule/prior_use_same", *missing, last=named)
        if any(u in allowed for u in last):
            return reading(control, "rule/prior_use_qualifies", last=named)
        if last:
            return reading("not_permitted", "rule/prior_use_not", last=named)
        return reading("not_decided", "rule/prior_use_unknown", MISSING_PHRASES["existing_use_stated"])
    if binding.kind == "use_frontage":
        exemption = next(
            (
                rules[b.rule_id]
                for b in BINDINGS
                if b.kind == "use_frontage_exempt" and b.with_rule == binding.rule_id and b.rule_id in rules
            ),
            None,
        )
        stated = ctx.concept.existing_use_stated.value
        if exemption is not None and use == "restaurant" and "limited_restaurant" in stated:
            key = _by_origin("rule/frontage_exempt", ctx.concept, "existing_use_stated")
            line = _rule_line(key, "T2", special, exemption)
            return _Reading("principal", (line,), (), exemption.source, False, True)
        return reading("not_decided", "rule/frontage", NOT_KNOWN["frontage"])
    if control == "principal":
        return reading(control, "rule/nothing")
    return reading(control, "rule", control=CONTROL_WORDS[control])


def _t2_readings(ctx: _Ctx, *, only: Use | None = None, as_new: bool = False) -> list[_Reading]:
    readings: list[_Reading] = []
    for special in ctx.specials:
        rules = _rules_of(ctx, special)
        for rule in rules.values():
            binding = BOUND.get(rule.rule_id)
            if binding is None or binding.trigger != "T2" or binding.kind == "use_frontage_exempt":
                continue
            for use in ctx.uses:
                if use not in binding.uses or (only is not None and use != only):
                    continue
                found = _t2_use(ctx, special, rule, binding, use, rules, as_new=as_new)
                if found is not None:
                    readings.append(found)
    return readings


def _prior_use(ctx: _Ctx, use: Use) -> list[tuple[str, _Reading]]:
    """The readings of the prior-use rules (`use_prior`) for one new use, each with its special district's
    name. T1 reads them for a cell whose note is that rule."""
    found: list[tuple[str, _Reading]] = []
    for special in ctx.specials:
        rules = _rules_of(ctx, special)
        for rule in rules.values():
            binding = BOUND.get(rule.rule_id)
            if binding is None or binding.kind != "use_prior" or use not in binding.uses:
                continue
            reading = _t2_use(ctx, special, rule, binding, use, rules, as_new=False, on_first=True)
            if reading is not None and reading.control != "does_not_apply":
                found.append((special.name, reading))
    return found


def _with_rules(ctx: _Ctx, trigger: str) -> list[_Special]:
    """The special districts at the address that carry a bound rule of this trigger."""
    prefixes = {b.rule_id.split(".", 1)[0] for b in BINDINGS if b.trigger == trigger}
    return [s for s in ctx.specials if _RULE_PREFIX.get(s.key) in prefixes]


# The prefix of the data's rule ids in each matched special district.
_RULE_PREFIX: dict[str, str] = {
    "mission_alcohol_sud": "mission",
    "north_beach_sud": "north_beach",
    "haight_alcohol_rusd": "haight",
    "third_street_alcohol_rud": "third",
    "soma_youth_family_sud": "soma_yf",
    "calle_24_sud": "calle24",
}


def _t2(ctx: _Ctx) -> _Result:
    found = _with_rules(ctx, "T2")
    if not found:
        return _outside("T2.none")
    readings = _t2_readings(ctx)
    if not readings:
        names = _listed([s.name for s in found])
        cites = [c for s in found for c in s.citations]
        return _Result(
            "does_not_apply", (_line("T2.no_rule", names=names, date=ctx.on.isoformat(), cites=cites),)
        )
    return _result(readings)


# ---- T3: enlarging or intensifying an existing use --------------------------------------------------------------
# The term of the citywide enlarge_or_intensify rule that T3's Conditional Use rests on (§ 178(c)(1) and
# § 186.1): its lines are dated by the run of versions in which it reads the same, not by edges where only other
# terms of the rule changed.
T3_CONDITIONAL_USE_TERM = "new_conditional_use_needed_to_significantly_alter_enlarge_or_intensify"
# The term of the citywide formula_retail_definition rule the change-of-operator note prints.
T5_OPERATOR_TERM = "change_of_operator_limbs"


def _licence_as_new(ctx: _Ctx, use: Use) -> list[_Reading]:
    """The licence rules of the special districts at the address for a NEW establishment (T4's
    `new_establishment` and `adds_licence` rules), read for the licence types the business that continues
    holds: the records' active licences and the types stated as held, else the concept's licence type. Not
    decided, naming the licence type, when the business serves alcohol and neither is known. Only the readings
    that ask for something are returned, each with its rule line under the id "T3:<rule_id>"."""
    found = _with_rules(ctx, "T4")
    if not found:
        return []
    concept = ctx.concept
    held, _ = _held(ctx)
    if held:
        types = sorted(held, key=int)
    elif not concept.licence_type.missing:
        types = [str(concept.licence_type.value)]
    else:
        if concept.serves_alcohol or use == "bar":
            line = _line("T3.licence_missing", a_use=A_USE[use], cites=ctx.cites)
            return [_Reading("not_decided", (line,), (concept.licence_type_phrase,))]
        return []
    readings: list[_Reading] = []
    for type_ in types:
        new = replace(
            ctx,
            concept=replace(
                concept,
                licence_type=Fact(type_, "stated", "licences_held"),
                alcohol_transaction=Fact("new_licence", "stated", "alcohol_transaction"),
                licences_held=Fact((), "missing"),
            ),
            uses=(use,),
            business_continues=False,
            continuing=frozenset(),
            maybe_continuing=frozenset(),
        )
        for special in found:
            for r in _t4_district(new, special):
                binding = _bound_rule(r.lines[0])
                if binding is None or binding.kind not in ("new_establishment", "adds_licence"):
                    continue
                if r.control in ("principal", "does_not_apply"):
                    continue
                line = r.lines[0].model_copy(update={"rule_id": f"T3:{binding.rule_id}"})
                readings.append(replace(r, lines=(line,)))
    return readings


def _t3(ctx: _Ctx) -> _Result:
    if not ctx.business_continues:
        return _outside("T3.none")
    uses = [use for use in ctx.uses if use in ctx.continuing]
    if not uses:
        return _outside("T3.no_use")
    change = ctx.concept.changes_existing_business
    found = controls.citywide_rules("enlarge_or_intensify", ctx.on)
    rule = found[0] if found else None
    run = controls.citywide_run("enlarge_or_intensify", ctx.on, T3_CONDITIONAL_USE_TERM) if rule else None

    def say(key: str, /, *, dated: controls.Source | None, **fields: Any) -> RuleLine:
        """A line that rests on the citywide rule: the section and URL are the rule's own; `dated` is the
        version, or the run of versions, the line's text is dated by."""
        return _line(
            key,
            section=rule.source.section if rule else None,
            url=rule.source.source_url if rule else None,
            cites=ctx.cites,
            in_force=dated.in_force_text if dated else "",
            **fields,
        )

    readings: list[_Reading] = []
    for use in uses:
        a_use, name = A_USE[use], USE_LABELS[use]
        if change.value == "none":
            key = _by_origin("T3.no_change", ctx.concept, "changes_existing_business")
            readings.append(_Reading("principal", (_line(key, a_use=a_use),)))
            continue
        # the use's standing as new: the district's cell, the special district use rules and the special
        # district licence rules for a new establishment, read for this use as if it were new
        standing = _as_new(ctx, use, "T3")
        special = [
            r
            for r in _t2_readings(ctx, only=use, as_new=True)
            if r.control not in ("principal", "does_not_apply")
        ]
        read = [standing, *special, *_licence_as_new(ctx, use)]
        as_new = _worst(r.control for r in read)
        lines = [line for r in read for line in r.lines]
        unknown = _each_once(m for r in read for m in r.missing)
        changed = CHANGE_WORDS.get(str(change.value), "")
        source = run if run is not None else standing.source
        missing: tuple[str, ...] = ()
        control: TriggerControl
        if as_new == "principal":
            control, source = "principal", standing.source
            lines.append(_line("T3.principal", a_use=a_use, use=name))
        elif as_new == "not_decided":  # the control for a new use is itself not decided
            control, source, missing = "not_decided", standing.source, unknown
            if change.missing:
                missing = (*missing, MISSING_PHRASES["changes_existing_business"])
                lines.append(_line("T3.both_unknown", a_use=a_use, use=name))
            else:
                lines.append(_line("T3.standing_unknown", a_use=a_use, use=name, change=changed))
        elif as_new == "code_and_practice_differ":
            if change.missing:
                control, missing = "not_decided", (MISSING_PHRASES["changes_existing_business"],)
                lines.append(_line("T3.change_missing/practice", a_use=a_use, use=name))
            else:
                control = "code_and_practice_differ"
                lines.append(_line("T3.practice_differs", a_use=a_use, use=name, change=changed))
        elif change.missing:
            control, missing = "not_decided", (MISSING_PHRASES["changes_existing_business"],)
            lines.append(_line("T3.change_missing", a_use=a_use, use=name, control=CONTROL_WORDS[as_new]))
        elif as_new == "conditional":
            control = "conditional"
            lines.append(say("T3.conditional_use", dated=run, a_use=a_use, use=name, change=changed))
        elif (ctx.district or "").startswith(NC_PREFIXES):
            control = "conditional"
            lines.append(say("T3.nonconforming_nc", dated=run, a_use=a_use, use=name, change=changed))
        else:
            control, missing = "not_decided", (NOT_KNOWN["exceptions_181"],)
            source = rule.source if rule else standing.source  # § 181(f) is dated by its own version
            lines.append(say("T3.nonconforming_other", dated=source, a_use=a_use, use=name, change=changed))
        readings.append(_Reading(control, tuple(lines), _each_once(missing), source, standing.historic, True))
    return _result(readings)


# ---- T4: liquor licence in a restricted district ------------------------------------------------------------------
class _Known(NamedTuple):
    """A yes / no fact that may not be known: `value` None, with the inputs that would settle it."""

    value: bool | None
    missing: tuple[str, ...] = ()
    cites: tuple[str, ...] = ()


def _held(ctx: _Ctx) -> tuple[frozenset[str], tuple[str, ...]]:
    """The licence types the business already holds at the address: those stated, and for a business that
    continues the ACTIVE licences on file. With the records that showed them."""
    held = set(ctx.concept.licences_held.value)
    cites: list[str] = []
    if ctx.business_continues:
        held |= set(ctx.site.licence_types)
        cites = [licence.citation for licence in ctx.site.licences]
    return frozenset(held), tuple(cites)


def _existing_establishment(ctx: _Ctx) -> _Known:
    """Is the establishment already at the address (spec T4: "whether the establishment is new")."""
    concept = ctx.concept
    transaction = concept.alcohol_transaction.value
    if ctx.business_continues or transaction == "licence_already_held":
        return _Known(True)
    if transaction in ("new_licence", "premises_transfer"):
        return _Known(False)
    stated = concept.existing_use_stated.value
    if stated and not set(stated) & set(ctx.uses):
        return _Known(False)  # the space is, or was last, another use
    shown = ctx.site.existing_use
    if shown is not None and shown not in ctx.uses:
        return _Known(False)
    if transaction == "person_to_person_transfer":
        return _Known(True)  # a licence of these premises changing hands
    return _Known(None, concept.missing(["existing_use_stated", "alcohol_transaction"]))


def _adds_licence(ctx: _Ctx, needed: str) -> _Known:
    """Does the concept add a licence of this type to what the business holds."""
    concept = ctx.concept
    held, cites = _held(ctx)
    transaction = concept.alcohol_transaction.value
    if needed in held or transaction == "licence_already_held":
        return _Known(False, cites=cites)
    if transaction is not None or not ctx.business_continues or concept.licences_held.value:
        return _Known(True, cites=cites)
    return _Known(None, concept.missing(["licences_held", "alcohol_transaction"]))


def _possible_types(ctx: _Ctx) -> frozenset[str] | None:
    """The licence types the uses proposed may hold under § 102; None when the uses do not narrow it."""
    possible: set[str] = set()
    for use in ctx.uses:
        if use == "bar":
            possible |= set(BAR_LICENCE_TYPES)
        elif use == "restaurant":
            possible |= set(RESTAURANT_LICENCE_TYPES)
        else:
            return None
    return frozenset(possible) if possible else None


def _types_text(types: Iterable[str]) -> str:
    """'Type 75'; 'Types 40, 42, 48 and 57'."""
    numbers = sorted(types, key=int)
    return ("Type " if len(numbers) == 1 else "Types ") + _listed(numbers)


def _type_missing_key(concept: ConceptFacts) -> str:
    """The line of a licence rule the missing licence type leaves not decided: what is poured is missing, or
    the type itself."""
    return "rule/pours_missing" if concept.pours_missing else "rule/type_missing"


def _t4_district(ctx: _Ctx, special: _Special) -> list[_Reading]:
    concept = ctx.concept
    rules = _rules_of(ctx, special)
    needed = concept.licence_type
    readings: list[_Reading] = []

    def reading(
        control: TriggerControl,
        key: str,
        rule: controls.Rule,
        /,
        *missing: str,
        cites: Iterable[str] = (),
        extra: Sequence[RuleLine] = (),
        **fields: Any,
    ) -> _Reading:
        line = _rule_line(key, "T4", special, rule, cites=cites, **fields)
        return _Reading(control, (line, *extra), tuple(missing), rule.source, False, True)

    def bound(kind: BindingKind) -> list[tuple[Binding, controls.Rule]]:
        return [(b, rules[b.rule_id]) for b in BINDINGS if b.kind == kind and b.rule_id in rules]

    def with_rule(rule_id: str, kind: BindingKind) -> list[RuleLine]:
        key = "rule/requirement" if kind == "requirement" else "rule/exception"
        return [
            _rule_line(key, "T4", special, r)
            for b, r in bound(kind)
            if b.with_rule == rule_id and (not b.uses or set(b.uses) & set(ctx.uses))
        ]

    def establishment(type_: str, restrictive: bool) -> tuple[_Known, list[RuleLine]]:
        """Is the establishment new for the district's licence rule, with the continuation rule applied: an
        existing establishment continues only with the same licence type."""
        existing = _existing_establishment(ctx)
        continuation = bound("continuation")
        if existing.value is not True or not continuation:
            if existing.value is None:
                return _Known(None, existing.missing), []
            return _Known(not existing.value), []
        _, rule = continuation[0]
        held, cites = _held(ctx)
        if type_ in held or (not held and concept.alcohol_transaction.value == "licence_already_held"):
            return _Known(False), [_rule_line("rule/same_type", "T4", special, rule, cites=cites, type=type_)]
        if not held:
            if not restrictive:
                return _Known(False), []
            line = _rule_line("rule/held_missing", "T4", special, rule)
            return _Known(None, (MISSING_PHRASES["licences_held"],)), [line]
        on_file = _types_text(held)
        return _Known(True), [
            _rule_line("rule/type_changes", "T4", special, rule, cites=cites, on_file=on_file, type=type_)
        ]

    for rule in rules.values():
        binding = BOUND.get(rule.rule_id)
        if binding is None or binding.trigger != "T4":
            continue
        if binding.districts and ctx.district not in binding.districts:
            continue
        control = _rule_control(rule)
        restrictive = control != "principal"
        types = binding.types_on(rule)
        word = CONTROL_WORDS[control]

        if binding.kind == "new_establishment":
            replaced = any(
                other.overrides == binding.rule_id
                and other.rule_id in rules
                and (not other.districts or ctx.district in other.districts)
                and needed.value in other.types_on(rules[other.rule_id])
                for other in BINDINGS
            )
            if replaced:
                continue
            if needed.missing:
                possible = _possible_types(ctx)
                if possible is not None and not possible & types:
                    readings.append(
                        reading("principal", "rule/use_not_reached", rule, types=_types_text(types))
                    )
                elif not restrictive:
                    pass
                elif _existing_establishment(ctx).value is True and not bound("continuation"):
                    # whatever the type, the rule is for a new establishment and this one already exists
                    readings.append(reading("principal", "rule/existing", rule))
                else:
                    readings.append(
                        reading("not_decided", _type_missing_key(concept), rule, concept.licence_type_phrase)
                    )
                continue
            type_ = str(needed.value)
            if type_ not in types:
                # the district's general rule says why it does not reach the concept; a sub-area rule is
                # passed over
                if binding.subarea is None:
                    not_reached = _types_text(types)
                    readings.append(
                        reading("principal", "rule/type_not_reached", rule, type=type_, types=not_reached)
                    )
                continue
            new, lines = establishment(type_, restrictive)
            if new.value is None:
                if restrictive:
                    key = "rule/held_missing" if lines else "rule/new_missing"
                    readings.append(reading("not_decided", key, rule, *new.missing))
                continue
            if not new.value:
                readings.append(reading("principal", "rule/existing", rule, extra=lines))
                continue
            notes = with_rule(binding.rule_id, "exception_note") if restrictive else []
            quota = [
                (b, r)
                for b, r in bound("quota_exception")
                if b.with_rule == binding.rule_id
                and set(ctx.uses) <= b.uses
                and type_ in b.types_on(r)
                and (not b.first_story or ctx.reads_first or ctx.story_missing)
            ]
            if quota and control == "not_permitted":
                quota_binding, quota_rule = quota[0]
                quota_lines = [_rule_line("rule/quota_unknown", "T4", special, quota_rule, type=type_)]
                unknown = [NOT_KNOWN["haight_restaurant_quota"]]
                if quota_binding.first_story and ctx.story_missing:
                    # the quota is for the ground level only: with no story given it may or may not reach
                    quota_lines.append(_rule_line("rule/story_missing", "T4", special, quota_rule))
                    unknown.append(MISSING_PHRASES["stories"])
                readings.append(
                    reading(
                        "not_decided",
                        "rule/licence",
                        rule,
                        *unknown,
                        extra=[*lines, *quota_lines],
                        control=word,
                    )
                )
                continue
            if binding.subarea is not None and restrictive:
                area = SUBAREAS[binding.subarea]
                if ctx.district in area.districts:
                    readings.append(
                        reading(
                            control,
                            "rule/subarea_inside",
                            rule,
                            extra=[*lines, *notes],
                            district=ctx.district,
                            control=word,
                        )
                    )
                else:
                    readings.append(
                        reading(
                            "not_decided",
                            "rule/subarea_unplaced",
                            rule,
                            NOT_KNOWN[area.not_known],
                            extra=lines,
                        )
                    )
                continue
            readings.append(reading(control, "rule/licence", rule, extra=[*lines, *notes], control=word))

        elif binding.kind == "adds_licence":
            if binding.uses and not set(binding.uses) & set(ctx.uses):
                continue
            # no story given: on any story but the first the rule does not apply, so it is read for the First
            # Story, and the story is named only where that reading asks for something or is not decided
            unplaced = binding.first_story and ctx.story_missing
            story: tuple[str, ...] = (MISSING_PHRASES["stories"],) if unplaced else ()
            also = [_rule_line("rule/story_missing/also", "T4", special, rule)] if unplaced else []
            if binding.first_story and not ctx.story_missing and not ctx.reads_first:
                readings.append(reading("does_not_apply", _by_origin("rule/story", concept, "stories"), rule))
            elif not restrictive:
                readings.append(reading("principal", "rule/nothing", rule))
            elif needed.missing:
                readings.append(
                    reading(
                        "not_decided",
                        _type_missing_key(concept),
                        rule,
                        concept.licence_type_phrase,
                        *story,
                        extra=also,
                    )
                )
            elif needed.value not in types:
                readings.append(
                    reading(
                        "principal",
                        "rule/type_not_reached",
                        rule,
                        type=needed.value,
                        types=_types_text(types),
                    )
                )
            else:
                adds = _adds_licence(ctx, str(needed.value))
                if adds.value is None:
                    readings.append(
                        reading("not_decided", "rule/adds_missing", rule, *adds.missing, *story, extra=also)
                    )
                elif adds.value and unplaced:
                    readings.append(
                        reading("not_decided", "rule/story_missing", rule, MISSING_PHRASES["stories"])
                    )
                elif adds.value:
                    extra = with_rule(binding.rule_id, "requirement")
                    readings.append(
                        reading(control, "rule/licence", rule, cites=adds.cites, extra=extra, control=word)
                    )
                else:
                    readings.append(
                        reading("principal", "rule/already_held", rule, cites=adds.cites, type=needed.value)
                    )

        elif binding.kind == "expansion":
            if not ctx.business_continues:
                continue
            held, cites = _held(ctx)
            transaction = concept.alcohol_transaction.value
            licensed: bool | None = None
            if held or transaction in ("licence_already_held", "person_to_person_transfer"):
                licensed = True  # it holds a licence here, or takes over the licence of these premises
            elif transaction is not None:
                licensed = False  # a new licence, or one brought from other premises: not yet licensed here
            change = concept.changes_existing_business
            if licensed is False:
                continue
            if not change.missing and change.value not in ENLARGES:
                key = _by_origin("rule/no_expansion", concept, "changes_existing_business")
                readings.append(reading("principal", key, rule, cites=cites))
            elif change.missing:
                readings.append(
                    reading(
                        "not_decided",
                        "rule/change_missing",
                        rule,
                        MISSING_PHRASES["changes_existing_business"],
                    )
                )
            elif licensed is None:
                readings.append(
                    reading("not_decided", "rule/held_missing", rule, MISSING_PHRASES["licences_held"])
                )
            else:
                note = (
                    [
                        _line(
                            "rule/definition_note",
                            rule_id="T4.definition_note",
                            url=rule.source.source_url,
                            cites=special.citations,
                        )
                    ]
                    if set(ctx.uses) & {"restaurant", "bar"}
                    else []
                )
                readings.append(reading(control, "rule/licence", rule, cites=cites, extra=note, control=word))

        elif binding.kind == "type_named":
            if not needed.missing and needed.value in types:
                readings.append(reading("principal", "rule/type_named", rule, type=needed.value))

        elif binding.kind == "licence_change":
            # An existing establishment that changes to one of these types keeps its standing. These are types
            # the district's rule for a new establishment does not reach (a test holds the two apart), so
            # this never changes the control: it is printed for a business that changes its licence.
            held, cites = _held(ctx)
            changes = not needed.missing and needed.value in types and held and needed.value not in held
            if changes and _existing_establishment(ctx).value is True:
                readings.append(
                    reading(
                        "principal",
                        "rule/change_allowed",
                        rule,
                        cites=cites,
                        on_file=_types_text(held),
                        type=needed.value,
                    )
                )

        elif binding.kind == "use_named":
            if set(binding.uses) & set(ctx.uses):
                readings.append(reading("principal", "rule/nothing", rule))

        elif binding.kind == "requirement" and binding.with_rule is None:
            if binding.when == "new_bar" and not ("bar" in ctx.uses and "bar" not in ctx.continuing):
                continue
            readings.append(reading("principal", "rule/requirement", rule))
    return readings


def _t4(ctx: _Ctx) -> _Result:
    found = _with_rules(ctx, "T4")
    if not found:
        return _outside("T4.none")
    names = _listed([s.name for s in found])
    cites = [c for s in found for c in s.citations]
    # a Bar sells alcohol by its § 102 definition, so "alcohol not stated" is never read as "no alcohol" for one
    if not ctx.concept.serves_alcohol and ctx.concept.licence_type.missing and "bar" not in ctx.uses:
        if ctx.concept.alcohol_not_stated:  # the intake model read alcohol the text does not state
            line = _line("T4.alcohol_not_stated", names=names, cites=cites)
            return _Result("not_decided", (line,), (ctx.concept.licence_type_phrase,))
        key = _by_origin("T4.no_alcohol", ctx.concept, "serves_alcohol")  # "No alcohol" answered
        return _Result("does_not_apply", (_line(key, names=names, cites=cites),))
    readings = [r for special in found for r in _t4_district(ctx, special)]
    if not readings:
        return _Result("principal", (_line("T4.no_rule", names=names, date=ctx.on.isoformat(), cites=cites),))
    return _result(readings)


# ---- T5: formula retail --------------------------------------------------------------------------------------------
def _t5(ctx: _Ctx) -> _Result:
    chain = ctx.concept.formula_retail
    count = ctx.concept.other_locations.value
    if chain.value is False:
        if ctx.concept.part_of_chain and count is not None:  # a chain below the § 303.1 count
            plural = "location" if count == 1 else "locations"
            return _Result("principal", (_line("T5.under_count", count=f"{count:,}", locations=plural),))
        return _Result("principal", (_line(_by_origin("T5.no", ctx.concept, "formula_retail")),))
    uses = [use for use in ctx.uses if use in T1_USES]
    if not uses:
        return _outside("T5.no_use")
    if not ctx.covered:
        return _not_carried(ctx, *ctx.concept.missing(["formula_retail"]))
    row = controls.formula_retail(ctx.zone, ctx.on)
    extra = row.extra
    labels = [USE_LABELS[use] for use in uses]
    lines: list[RuleLine] = []
    open_: list[str] = []  # what would settle a control for part of the district that could change the answer
    possible: set[controls.Permission | None] = set()  # every control the row could give this concept

    def say(key: str, *, also_cites: Iterable[str] = (), **fields: Any) -> RuleLine:
        return _row_line(key, ctx, row.source, also_cites=also_cites, **fields)

    def answer(control: TriggerControl, *missing: str) -> _Result:
        return _result([_Reading(control, tuple(lines), _each_once(missing), row.source, False, True)])

    base: controls.Permission | None = row.control if row.applies_to_all else None
    if row.control is None:
        lines.append(say("T5.row/unreadable"))
        open_.append(NOT_KNOWN["no_control"])
    elif not row.applies_to_all:
        lines.append(say("T5.row/narrow", applies_to=row.applies_to))
        open_.append(NOT_KNOWN["formula_row_reach"].format(applies_to=row.applies_to))
        possible.add(row.control)
    elif row.governed:
        lines.append(say("T5.row/governed", row=row.governing_row or "", control=CONTROL_WORDS[row.control]))
    else:
        lines.append(say("T5.row", control=CONTROL_WORDS[row.control]))
    named = [label for label in labels if label in row.not_permitted_for]
    if named and base is not None:
        base = "not_permitted"
        lines.append(say("T5.not_permitted_for", uses=_listed(named)))

    # the address is inside the Central SoMa Special Use District, where the row gives another control
    inside = extra.get("in_central_soma_sud")
    if isinstance(inside, Mapping) and ctx.central_soma and base is not None:
        control = _letter(inside.get("control"))
        barred = [label for label in labels if label in (inside.get("not_permitted_for") or ())]
        if barred:
            base = "not_permitted"
            lines.append(
                say("T5.central_soma/not_permitted", also_cites=ctx.central_soma, uses=_listed(barred))
            )
        elif control is not None:
            base = control
            lines.append(say("T5.central_soma", also_cites=ctx.central_soma, control=CONTROL_WORDS[control]))

    def part(
        control: controls.Permission | None, where: str, source: str, reached: Sequence[str] = ()
    ) -> None:
        """A control for part of the district: applied where an overlay on file places the address there, not
        read where no such overlay does (the address is outside), named where the records cannot place it."""
        nonlocal base
        uses_text = f" for {_listed(list(reached))}" if reached else ""
        section = _overlay_section(extra, where)
        if section is not None:
            placing = [f"overlay:{o.id}" for o in ctx.overlays if pw._names_section(o.code_section, section)]
            if placing and control is not None and base is not None:
                possible.discard(base)
                possible.add(control)
                base = control if SEVERITY.index(control) < SEVERITY.index(base) else base
                lines.append(
                    say(
                        "T5.subarea/inside",
                        also_cites=placing,
                        control=CONTROL_WORDS[control],
                        uses=uses_text,
                        where=where,
                        source=source,
                    )
                )
            return
        possible.add(control)
        if control is None or control == base:
            return
        lines.append(
            say("T5.subarea", control=CONTROL_WORDS[control], uses=uses_text, where=where, source=source)
        )
        open_.append(NOT_KNOWN["part_of_district"].format(where=where))

    subareas = extra.get("not_permitted_for_in_subarea")
    for sub in subareas if isinstance(subareas, tuple) else ():
        reached = [label for label in labels if label in (sub.get("uses") or ())]
        if reached:
            part(_letter(sub.get("control")), str(sub.get("where", "")), str(sub.get("source", "")), reached)
    restaurant_rule = extra.get("formula_retail_restaurant_rule")
    if isinstance(restaurant_rule, Mapping):
        reached = [label for label in labels if label in ("Restaurant", "Limited Restaurant")]
        control = _letter(restaurant_rule.get("control"))
        if reached and control is not None and control != base:
            possible.add(control)
            section = controls.section_label(str(restaurant_rule.get("section", "")))
            lines.append(
                _line(  # the sub-rule's own section and URL
                    "T5.subarea",
                    section=section,
                    url=str(restaurant_rule.get("url", "")),
                    cites=ctx.cites,
                    district=ctx.zone,
                    control=CONTROL_WORDS[control],
                    uses="",
                    where=str(restaurant_rule.get("applies_to", "")),
                    source=section,
                )
            )
            open_.append(NOT_KNOWN["mission_fr_subdistrict"])
    exception = extra.get("principal_exception")
    if isinstance(exception, Mapping):
        part(
            _letter(exception.get("control")),
            str(exception.get("where", "")),
            str(exception.get("source", "")),
        )
    fronting = extra.get("conditional_where")
    if isinstance(fronting, str) and fronting:
        part("conditional", fronting, row.source.section)
    conflict = extra.get("conflicting_text")
    if isinstance(conflict, Mapping):
        source = controls.section_label(str(conflict.get("section", "")))
        part(_letter(conflict.get("control")), str(conflict.get("where", "")), source)
    for key in ("limited_commercial_use_sec_186_control", "limited_commercial_use_sec_186"):
        control = _letter(extra.get(key))
        if control is not None:
            possible.add(control)
            if control != base:
                open_.append(NOT_KNOWN["limited_commercial"])

    possible.add(base)
    if chain.missing:
        # a chain whose count is not given is named by the count, a skipped chain question by the question
        key = "T5.count_missing" if ctx.concept.chain_count_missing else "T5.missing"
        if possible <= {"principal"}:
            lines.append(_line(f"{key}/principal"))
            return answer("principal")
        lines.append(_line(key))
        return answer("not_decided", *ctx.concept.missing(["formula_retail"]))
    found = controls.citywide_rules("formula_retail_definition", ctx.on)
    if found:
        note = found[0]
        limbs = note.extra.get("facts", {}).get(T5_OPERATOR_TERM) or ()
        # dated by the run of versions in which the limbs read the same, not by a renumbering
        dated = controls.citywide_run("formula_retail_definition", ctx.on, T5_OPERATOR_TERM) or note.source
        lines.append(
            _line(
                "T5.operator",
                section=note.source.section,
                url=note.source.source_url,
                limbs=_listed([str(limb) for limb in limbs]),
                in_force=dated.in_force_text,
            )
        )
    if open_ or base is None:
        return answer("not_decided", *open_)
    return answer(base)


# ---- T6: nighttime entertainment -----------------------------------------------------------------------------------
def _t6(ctx: _Ctx) -> _Result:
    concept = ctx.concept
    kind = concept.entertainment_kind
    if NIGHTTIME in ctx.uses:
        if NIGHTTIME in ctx.continuing:
            return _outside("T6.continues")
        if NIGHTTIME in ctx.maybe_continuing:
            line = _line("T6.maybe_continues")
            return _Result("not_decided", (line,), (MISSING_PHRASES["changes_existing_business"],))
        if not ctx.covered:
            return _not_carried(ctx)
        return _result([_use_reading(ctx, NIGHTTIME, "T6")])
    if kind.value == "limited_live_performance":
        found = controls.citywide_rules("nighttime_entertainment_definition", ctx.on)
        rule = found[0] if found else None
        line = _line(
            _by_origin("T6.limited_live", concept, "entertainment_kind"),
            section=rule.source.section if rule else _USE_DEFINITIONS,
            url=rule.source.source_url if rule else None,
        )
        return _Result("does_not_apply", (line,))
    # amplified sound is entertainment (§ 102 Nighttime Entertainment is "not limited to non-amplified live
    # entertainment"); with no kind stated it is read like live entertainment of no stated kind
    described = concept.live_entertainment or concept.amplified_sound
    if not (kind.missing and (described or concept.entertainment_not_stated)):
        # "You answered ..." only for the answer "No entertainment" (an answered kind is read above)
        return _outside(_by_origin("T6.none", concept, "entertainment_kind"))
    # the intake model read entertainment the text does not state: whether there is any is not known
    key = "T6.kind_missing" if described else "T6.not_stated"
    if not ctx.covered:
        return _not_carried(ctx, MISSING_PHRASES["entertainment_kind"])
    cells = _use_reading(ctx, NIGHTTIME, "T6")
    if cells.control == "principal":
        line = _line(f"{key}/principal")
        return _result([_Reading("principal", (*cells.lines, line), (), cells.source, cells.historic, True)])
    line = _line(key)
    # with no story given the cells are not decided for the story too, and the story is named with the kind
    story = tuple(m for m in cells.missing if m == MISSING_PHRASES["stories"])
    missing = (MISSING_PHRASES["entertainment_kind"], *story)
    return _result(
        [_Reading("not_decided", (*cells.lines, line), missing, cells.source, cells.historic, True)]
    )


# ---- T7: use size ----------------------------------------------------------------------------------------------------
def _size_applies(ctx: _Ctx) -> bool | None:
    """Is the use new, merged or enlarged (True), an existing use taking no more space (False), or an existing
    use whose change is not stated (None)."""
    concept = ctx.concept
    if concept.merges_storefronts.value is True or concept.changes_existing_business.value in ENLARGES:
        return True
    if ctx.uses and all(use in ctx.continuing for use in ctx.uses):
        return None if concept.changes_existing_business.missing else False
    return True


# Uses a space can last have held that are not residential: taking one over is a change of use inside an existing
# space (use_size_general: the Code is silent; Zoning Administrator Interpretation 121.2).
NON_RESIDENTIAL_LAST_USES: frozenset[str] = frozenset(
    {"bar", "restaurant", "limited_restaurant", "nighttime_entertainment", "retail", "laundromat"}
)
# The names use_size_general gives the districts where a new Conditional Use is needed to change an oversized
# use (facts.new_conditional_use_to_change_oversized_use), as zoning district codes.
NAMED_DISTRICTS: dict[str, str] = {"North Beach NCD": "NCD-NORTH BEACH", "Castro Street NCD": "NCD-CASTRO"}


def _size_by(principal_below: int | None, not_permitted_from: int | None, area: int) -> controls.Permission:
    """The size control for an area under a pair of figures (the other code text of `other_code_text_figures`)."""
    if principal_below is None or area < principal_below:
        return "principal"
    if not_permitted_from is not None and area >= not_permitted_from:
        return "not_permitted"
    return "conditional"


def _t7(ctx: _Ctx) -> _Result:
    applies = _size_applies(ctx)
    if applies is False:
        return _outside("T7.not_new")
    concept = ctx.concept
    area = concept.floor_area_sqft
    if not ctx.covered:
        return _not_carried(ctx, *concept.missing(["floor_area_sqft"]))
    row = controls.use_size(ctx.zone, ctx.on)
    extra = row.extra

    def say(key: str, **fields: Any) -> RuleLine:
        return _row_line(key, ctx, row.source, **fields)

    lines: list[RuleLine] = []
    missing: list[str] = []
    control: TriggerControl
    exempted = False
    threshold = row.principal_below_sqft
    if threshold is None:
        control = "does_not_apply"
        lines.append(say("T7.none"))
    elif area.value is None:
        control = "not_decided"
        missing.append(MISSING_PHRASES["floor_area_sqft"])
        lines.append(say("T7.missing", threshold=_square_feet(threshold)))
    else:
        size = row.size_control(area.value) or "principal"
        control = size
        words = {"threshold": _square_feet(threshold), "area": _square_feet(area.value)}
        if size == "principal":
            lines.append(say("T7.below", **words))
        elif size == "conditional":
            lines.append(say("T7.conditional", **words))
        else:
            lines.append(
                say("T7.cap", cap=_square_feet(row.not_permitted_from_sqft or 0), area=words["area"])
            )
        # the table's note: no Conditional Use for use size for a Restaurant larger than its own figure
        exempt = extra.get("conditional_not_required_for")
        if (
            size == "conditional"
            and isinstance(exempt, Mapping)
            and ctx.uses
            and all(use == exempt["use"] for use in ctx.uses)
            and area.value > exempt["larger_than_sqft"]
        ):
            control, exempted = "principal", True
            larger = _square_feet(exempt["larger_than_sqft"])
            lines.append(say("T7.restaurant", source=exempt["source"], larger=larger, area=words["area"]))
        # the row against the section it cites, where the two disagree
        other = extra.get("other_code_text_figures")
        if isinstance(other, Mapping):
            alternative = _size_by(
                other["principal_below_sqft"], other["not_permitted_from_sqft"], area.value
            )
            if _asks(alternative) != _asks(control):
                lines.append(
                    say(
                        "T7.texts_differ",
                        other=other["section"],
                        area=words["area"],
                        alternative=CONTROL_WORDS[alternative],
                        control=CONTROL_WORDS[control],
                    )
                )
                missing.append(
                    NOT_KNOWN["code_texts_differ"].format(
                        a=f"the table row ({row.source.section})", b=other["section"]
                    )
                )
                control = "not_decided"
        # a new use taking over an existing space (spec 1a T7: the control is not for taking over an existing
        # space unchanged; the Code is silent and Interpretation 121.2 needs no Conditional Use where the floor
        # area does not grow)
        last = [u for u in ctx.last_uses if u in NON_RESIDENTIAL_LAST_USES]
        if (
            control == "conditional"
            and applies is True
            and last
            and concept.merges_storefronts.value is not True
            and concept.changes_existing_business.value not in ENLARGES
            and ctx.zone.startswith(NC_PREFIXES)
        ):
            general = controls.citywide_rules("use_size_general", ctx.on)
            rule = general[0] if general else None
            if rule is not None:
                facts = rule.extra.get("facts", {})
                named = facts.get("new_conditional_use_to_change_oversized_use") or ()
                ref: dict[str, Any] = {
                    "section": rule.source.section,
                    "url": rule.source.source_url,
                    "cites": ctx.cites,
                    "in_force": rule.source.in_force_text,
                }
                lines.append(
                    _line("T7.existing_space", last=_listed([LAST_USE_LABELS[u] for u in last]), **ref)
                )
                if ctx.zone in {NAMED_DISTRICTS.get(str(n), "") for n in named}:
                    lines.append(_line("T7.existing_space/district", district=ctx.zone, **ref))
                else:
                    open_size = concept.missing(["floor_area_before_sqft", "merges_storefronts"])
                    before = concept.floor_area_before_sqft.value
                    if open_size:
                        control = "not_decided"
                        missing.extend(open_size)
                        lines.append(_line("T7.existing_space/missing", missing=_listed(list(open_size))))
                    elif before is not None and area.value <= before:
                        lines.append(_line("T7.existing_space/same"))
                        return _result(
                            [_Reading("does_not_apply", tuple(lines), (), rule.source, False, True)]
                        )
    # a cap for Limited Corner Commercial Uses, where the rules cannot tell whether the use is one
    for key in ("limited_corner_commercial_use_cap_sqft", "limited_corner_commercial_use_max_sqft"):
        cap = extra.get(key)
        if isinstance(cap, int) and (area.value is None or area.value > cap):
            lines.append(say("T7.corner_cap", cap=_square_feet(cap)))
            missing.append(
                NOT_KNOWN["limited_corner_commercial"]
                if area.value is not None
                else MISSING_PHRASES["floor_area_sqft"]
            )
            control = "not_decided"
    only_if = extra.get("not_permitted_only_if")
    if isinstance(only_if, str) and area.value is not None and area.value > ONLY_IF_OVER_SQFT:
        lines.append(say("T7.only_if", only_if=only_if))
        missing.append(NOT_KNOWN["large_grocery"])
        control = "not_decided"
    if (control in ("conditional", "not_permitted") or exempted) and row.exemption:
        lines.append(say("T7.exemption", exemption=row.exemption))
    if applies is None and control not in ("principal", "does_not_apply"):
        # the use already exists; whether it is enlarged decides whether the size control is read at all
        lines.append(_line("T7.change_missing"))
        missing.append(MISSING_PHRASES["changes_existing_business"])
        control = "not_decided"
    return _result([_Reading(control, tuple(lines), _each_once(missing), row.source, False, True)])


# ---- T8: laundromat removal ------------------------------------------------------------------------------------------
def _laundromat_window(on: dt.date) -> tuple[controls.Rule, dt.date, dt.date] | None:
    """The rule while it was in force, with its first and last day; None when the data does not hold it."""
    found = controls.citywide_rules("laundromat_removal", on)
    if not found:
        return None
    started = found[0].extra.get("facts", {}).get("period_started")
    if not isinstance(started, str):
        return None
    start = dt.date.fromisoformat(started)
    in_force = controls.citywide_rules("laundromat_removal", max(start, controls.DATA_START))
    if not in_force or not in_force[0].in_force or in_force[0].source.in_force_to is None:
        return None
    return in_force[0], start, in_force[0].source.in_force_to


def _t8(ctx: _Ctx) -> _Result:
    window = _laundromat_window(ctx.on)
    if window is None:
        return _outside("T8.no_data")
    rule, start, end = window

    def say(key: str, /, *, cites: Iterable[str] = (), **fields: Any) -> RuleLine:
        return _line(
            key,
            section=rule.source.section,
            url=rule.source.source_url,
            cites=cites,
            start=start.isoformat(),
            end=end.isoformat(),
            **fields,
        )

    # the data does not settle whether the last day was this one or the day before
    doubt = (
        [say("T8.last_day", day_before=(end - dt.timedelta(days=1)).isoformat())]
        if ctx.on == end and rule.extra.get("facts", {}).get("last_day_uncertain_by_one_day") is True
        else []
    )

    def answer(control: TriggerControl, line: RuleLine, *missing: str) -> _Result:
        return _result([_Reading(control, (line, *doubt), tuple(missing), rule.source, False, True)])

    if not start <= ctx.on <= end:
        return _Result("does_not_apply", (say("T8.outside", date=ctx.on.isoformat()),))
    if "laundromat" in ctx.concept.existing_use_stated.value:
        return answer("conditional", say("T8.conditional"))
    last = ctx.last_uses
    if last:
        shown = ctx.site.existing_use
        cites = [c for line in ctx.site.existing_use_lines for c in line.citations] if shown else []
        named = _listed([LAST_USE_LABELS[u] for u in last])
        return answer("principal", say("T8.not_laundromat", cites=cites, last=named))
    return answer("not_decided", say("T8.missing"), MISSING_PHRASES["existing_use_stated"])


# ---- T9: outdoor activity area ---------------------------------------------------------------------------------------
def _route_202_2_a_7(ctx: _Ctx) -> tuple[bool, tuple[str, ...]]:
    """Is the § 202.2(a)(7) route (principally permitted within five limits) available elsewhere on the lot: by
    the district's own row, or by the citywide entry's list of district classes on the date. With the classes
    when only the citywide entry gives it."""
    row = controls.outdoor_activity_area(ctx.zone, ctx.on)
    if row.elsewhere_principal_if_202_2_a_7:
        return True, ()
    found = controls.citywide_rules("outdoor_activity_area_general", ctx.on)
    classes = (
        tuple(str(c) for c in (found[0].extra.get("facts", {}).get("s202_2_a_7_districts") or ()))
        if found
        else ()
    )
    zone = ctx.zone
    for name in classes:
        if name == "NC" and zone.startswith(("NC-", "NCD-")):
            return True, classes
        if name == "NCT" and zone.startswith("NCT-"):
            return True, classes
        if name == zone:
            return True, classes
    return False, ()


def _t9(ctx: _Ctx) -> _Result:
    concept = ctx.concept
    place = concept.outdoor_area.value
    if place == "sidewalk":
        return _outside("T9.sidewalk")
    if place == "none":  # "No outdoor area", stated or answered
        return _outside(_by_origin("T9.none", concept, "outdoor_area"))
    if place is None and not concept.outdoor_area_described:
        return _outside("T9.none")
    if not ctx.covered:
        return _not_carried(ctx, *concept.missing(["outdoor_area"]))
    row = controls.outdoor_activity_area(ctx.zone, ctx.on)
    # an existing business that is stated not to change keeps an outdoor area it already lawfully has; the rules
    # cannot tell whether this one is new
    unchanged = ctx.business_continues and concept.changes_existing_business.value == "none"

    def answer(control: TriggerControl, key: str, /, *missing: str, **fields: Any) -> _Result:
        lines = [_row_line(key, ctx, row.source, **fields)]
        if extra_line is not None:
            lines.insert(0, extra_line)
        if unchanged and control in ("conditional", "not_permitted"):
            lines.append(_line("T9.existing"))
            missing = (*missing, NOT_KNOWN["existing_outdoor_area"])
            control = "not_decided"
        return _result([_Reading(control, tuple(lines), _each_once(missing), row.source, False, True)])

    def words(control: controls.Permission | None) -> str:
        return CONTROL_WORDS[control] if control is not None else "not on file"

    extra_line: RuleLine | None = None
    if place is None:
        # an outdoor area with no place: the description gives it, or the answer that alcohol is served in it
        if row.in_front == "principal" and row.elsewhere == "principal":
            return answer("principal", _by_origin("T9.missing/principal", concept, "outdoor_seating"))
        return answer(
            "not_decided",
            _by_origin("T9.missing", concept, "outdoor_seating"),
            MISSING_PHRASES["outdoor_area"],
            front=words(row.in_front),
            elsewhere=words(row.elsewhere),
        )
    control = row.in_front if place == "front" else row.elsewhere
    if control is None:
        return answer("not_decided", "T9.unreadable", NOT_KNOWN["outdoor_control"])
    if place == "front":
        return answer(control, "T9.front", control=CONTROL_WORDS[control])
    route, classes = _route_202_2_a_7(ctx) if control == "conditional" else (False, ())
    if route:
        found = controls.citywide_rules("outdoor_activity_area_general", ctx.on)
        if classes and found:
            general = found[0]
            extra_line = _line(
                "T9.citywide_route",
                section=general.source.section,
                url=general.source.source_url,
                cites=ctx.cites,
                district=ctx.zone,
                classes=_listed(list(classes)),
                in_force=general.source.in_force_text,
            )
        if "bar" in ctx.uses:
            return answer("conditional", "T9.limits/bar")
        if place == "rooftop":
            return answer("conditional", "T9.limits/rooftop")
        conditions = found[0].extra.get("facts", {}).get("s202_2_a_7_conditions") if found else ()
        limits = "; ".join(str(c) for c in conditions or ())
        return answer(
            "not_decided", "T9.limits", NOT_KNOWN["outdoor_limits"].format(limits=limits), limits=limits
        )
    return answer(control, "T9.elsewhere", control=CONTROL_WORDS[control])


# ---- T10: amending an earlier approval -------------------------------------------------------------------------------
def _t10(ctx: _Ctx) -> _Result:
    amends = ctx.concept.amends_prior_approval
    found = controls.citywide_rules("amend_prior_conditions", ctx.on)
    rule = found[0] if found else None
    source = rule.source if rule else None

    def say(key: str, /, *, cites: Iterable[str] = (), **fields: Any) -> RuleLine:
        return _line(
            key,
            section=source.section if source else None,
            url=source.source_url if source else None,
            cites=cites,
            in_force=source.in_force_text if source else "",
            **fields,
        )

    if amends.value is True:
        line = say(_by_origin("T10.amends", ctx.concept, "amends_prior_approval"))
        return _result([_Reading("conditional", (line,), (), source, False, True)])
    if amends.value is False:
        return _outside(_by_origin("T10.no", ctx.concept, "amends_prior_approval"))
    earlier = [d for d in ctx.site.prior_decisions if d.conditional_use]
    if earlier and ctx.business_continues:
        named = _listed([f"{d.record_id}, {d.date.isoformat()}" if d.date else d.record_id for d in earlier])
        line = say("T10.missing", cites=[d.citation for d in earlier], record=named)
        missing = (MISSING_PHRASES["amends_prior_approval"],)
        return _result([_Reading("not_decided", (line,), missing, source, False, True)])
    return _outside("T10.none")


# ---- T11: hours of operation -----------------------------------------------------------------------------------------
_DAY_STARTS = 6 * 60  # the hours controls on file start their day at 6 a.m.
_TWO_AM = 2 * 60
_MINUTES = 24 * 60


def _minute(clock: str) -> int:
    """'06:00' -> 360."""
    return int(clock[:2]) * 60 + int(clock[3:5])


def _begins_before_2am(start: int) -> bool:
    """Does a window that starts at this minute begin before 2 a.m., counting the day from 6 a.m."""
    return (start - _DAY_STARTS) % _MINUTES < (_TWO_AM - _DAY_STARTS) % _MINUTES


def _other_windows(row: controls.Hours) -> tuple[controls.HoursWindow, ...]:
    """The windows the row records for a Limited Commercial Use under § 186, where they differ."""
    raw = row.extra.get("windows_sec_186_limited_commercial_use")
    windows = tuple(
        controls.HoursWindow(_LETTERS[item[0]], _minute(item[1]), _minute(item[2]))
        for item in (raw if isinstance(raw, tuple) else ())
        if isinstance(item, tuple) and len(item) == 3 and item[0] in _LETTERS
    )
    same = tuple((w.permission, w.start, w.end) for w in windows) == tuple(
        (w.permission, w.start, w.end) for w in row.windows
    )
    return () if same else windows


def _closing_words(ctx: _Ctx) -> str:
    closing = ctx.concept.closing
    if closing.minute is not None:
        return f"a closing time of {pw.format_time(closing.minute)}"
    return f"{pw.CLOSING_PHRASES[str(closing.bucket)]} (read at {pw.format_time(closing.read_at or 0)})"


def _worst_hours(row: controls.Hours, start: int, end: int) -> controls.Permission | None:
    """The most severe control of the hours windows at any minute from `start` to `end` (both included,
    counting on past midnight). None when no window covers any of those minutes."""
    span = (end - start) % _MINUTES
    found = {row.permission_at((start + m) % _MINUTES) for m in range(span + 1)}
    known = [c for c in found if c is not None]
    return min(known, key=SEVERITY.index) if known else None


# Intensifying a business includes keeping longer hours (BusinessProfile.changes_existing_business).
INTENSIFIES: frozenset[str] = frozenset({"intensify", "enlarge_and_intensify"})


def _t11(ctx: _Ctx) -> _Result:
    closing = ctx.concept.closing
    if not ctx.covered:
        return _not_carried(ctx, *ctx.concept.missing(["closing"]))
    row = controls.hours(ctx.zone, ctx.on)

    def say(key: str, **fields: Any) -> RuleLine:
        return _row_line(key, ctx, row.source, **fields)

    if row.no_limit:
        return _Result("does_not_apply", (say("T11.no_limit"),), dated=True)
    other = _other_windows(row)
    other_text = "; ".join(w.text for w in other)
    lines: list[RuleLine] = []
    missing: list[str] = []
    control: TriggerControl
    if closing.missing or closing.read_at is None:
        early = [
            w for w in (*row.windows, *other) if w.permission != "principal" and _begins_before_2am(w.start)
        ]
        if early:
            control = "not_decided"
            missing.append(MISSING_PHRASES["closing"])
            lines.append(say("T11.missing", windows=row.text))
        else:
            control = "principal"
            lines.append(say("T11.missing/late", windows=row.text))
    else:
        found = row.permission_at(closing.read_at)
        words = {"closing": _closing_words(ctx), "windows": row.text}
        morning_unknown = False
        if closing.overnight is True:
            # open through the night to a morning close: every hour from the late close on is read
            start = closing.open_from or 0
            found = _worst_hours(row, start, closing.read_at)
            lines.append(say("T11.overnight", start=pw.format_time(start), **words))
        elif closing.overnight is None and _worst_hours(row, 0, closing.read_at) != found:
            morning_unknown = True
        if morning_unknown:
            control = "not_decided"
            missing.append(NOT_KNOWN["overnight"])
            lines.append(say(_by_origin("T11.morning", ctx.concept, "closing_hour"), **words))
        elif found is None:
            control = "not_decided"
            missing.append(NOT_KNOWN["hours_not_covered"])
            lines.append(say("T11.not_covered", **words))
        else:
            control = found
            lines.append(say(f"T11.{found}", **words))
            if other and next((w.permission for w in other if w.covers(closing.read_at)), None) != found:
                control = "not_decided"
                missing.append(NOT_KNOWN["limited_commercial"])
                lines.append(say("T11.limited_commercial", windows=other_text))
    if ctx.business_continues and control in ("conditional", "not_permitted"):
        lines.append(_line("T11.existing"))
        change = ctx.concept.changes_existing_business
        if change.value not in INTENSIFIES:
            # spec 1a T11: an existing business keeping hours it already lawfully keeps is not decided by the
            # rules; a business that is intensified (longer hours) keeps the window's control
            control = "not_decided"
            missing.append(NOT_KNOWN["existing_hours"])
            if change.missing:
                missing.append(MISSING_PHRASES["changes_existing_business"])
    return _result([_Reading(control, tuple(lines), _each_once(missing), row.source, False, True)])


# ---- all eleven ------------------------------------------------------------------------------------------------------
_TRIGGERS: tuple[tuple[str, Callable[[_Ctx], _Result]], ...] = (
    ("T1", _t1),
    ("T2", _t2),
    ("T3", _t3),
    ("T4", _t4),
    ("T5", _t5),
    ("T6", _t6),
    ("T7", _t7),
    ("T8", _t8),
    ("T9", _t9),
    ("T10", _t10),
    ("T11", _t11),
)


def _dates_in(value: Any, found: set[dt.date]) -> None:
    if isinstance(value, dict):
        for key in ("from", "to"):
            text = value.get(key)
            if isinstance(text, str) and len(text) == 10:
                day = dt.date.fromisoformat(text)
                found.add(day if key == "from" else day + dt.timedelta(days=1))
        for item in value.values():
            _dates_in(item, found)
    elif isinstance(value, list):
        for item in value:
            _dates_in(item, found)


@lru_cache(maxsize=1)
def _change_dates() -> tuple[dt.date, ...]:
    """Every day on which some entry of the dated data begins or stops, in order: the days on which a control
    can change."""
    found: set[dt.date] = set()
    _dates_in(json.loads(controls.DATA_PATH.read_text(encoding="utf-8")), found)
    return tuple(sorted(found))


def _changed(
    rule: Callable[[_Ctx], _Result], ctx: _Ctx, today: dt.date, now: _Result
) -> tuple[dt.date | None, str | None]:
    """The day from which the trigger has read as it reads today, and the ordinance of the version that began
    that day when the data names one."""
    since: dt.date | None = None
    ordinance: str | None = None
    low, high = sorted((ctx.on, today))
    for day in reversed(_change_dates()):
        if not low < day <= high:
            continue
        then = rule(replace(ctx, on=day))
        if _asks(then.control) != _asks(now.control):
            break
        since = day
        ordinance = then.ordinance if then.in_force_from == day else None
    return since, ordinance


def _day(value: dt.date) -> dt.date:
    return value.date() if isinstance(value, dt.datetime) else value


# ---- contingent readings (app.memo.pathway rule 9) ------------------------------------------------------------------
# What a trigger's own reading gives once an input not given goes one way. Nothing here changes a control: every
# condition is checked by running the trigger itself again with the inputs supposed, for every value they can take
# (`_suppositions`), and is kept only when every run it covers gives the same control, one that asks for something.
#
# The inputs each trigger is run again over (ConceptFacts fields, by their `MISSING_PHRASES` names). An input is
# supposed only where it is not given, and where the trigger names it as missing in the run being tried.
SUPPOSED_INPUTS: dict[str, tuple[str, ...]] = {
    "T1": ("stories",),
    "T5": ("formula_retail",),
    "T6": ("stories",),
    "T7": (
        "floor_area_sqft",
        "changes_existing_business",
        "floor_area_before_sqft",
        "merges_storefronts",
        "existing_use_stated",
    ),
}
# Inputs a trigger reads without naming them when they are not given, so they are supposed from the start, even
# where the trigger is decided: T7 reads the space's last use (Zoning Administrator Interpretation 121.2) and,
# where none is stated and the records show none, reads the use as new. A decided control that another last use
# would change is not a definite finding (`TriggerFinding.unsettled_by`).
READ_UNNAMED: dict[str, tuple[str, ...]] = {"T7": ("existing_use_stated",)}
# Inputs supposed together with a named one where they are not given: whether an existing business is enlarged is
# asked without a merger, which T7 reads as "not merged" while it is not given, though a merger makes the use size
# control apply as an enlargement does.
SUPPOSED_WITH: dict[str, tuple[str, ...]] = {"changes_existing_business": ("merges_storefronts",)}
# The words of each way an input can go, printed after "if" (`ContingentReading.condition`). {uses}: the last uses
# that are an existing non-residential space for T7 (NON_RESIDENTIAL_LAST_USES); {stories}: STORY_LABELS.
CONDITION_WORDS: dict[str, str] = {
    "floor_area/from": "the floor area is {low} square feet or more",
    "floor_area/between": "the floor area is from {low} to {high} square feet",
    "floor_area/under": "the floor area is under {high} square feet",
    "floor_area/and": "{area} and {ways}",
    "floor_area/and_either": "{area} and either {ways}",
    "enlarged": "the existing business is enlarged",
    "merged": "storefronts are merged",
    "grows": "the floor area grows",
    "last_use_other": "the space was last used as another use (not {uses})",
    "chain": "the business is part of a chain with eleven or more other locations",
    "chain_count": "the business has eleven or more other locations",
    "story": "the business occupies {stories}",
    "story_only": "the business occupies only {stories}",
    "story_within": "the business occupies no story other than {stories}",
}
_ASKS_FOR: tuple[Literal["conditional", "not_permitted"], ...] = ("conditional", "not_permitted")

_Supposed = Mapping[str, Any]  # input name -> the value supposed


@dataclass(frozen=True)
class _Way:
    """One way the inputs can go, in words: `holds` says, for a run, whether it went that way (None: the run did
    not suppose the input, so its answer does not turn on it)."""

    key: str  # a CONDITION_WORDS key
    inputs: tuple[str, ...]
    holds: Callable[[_Supposed], bool | None]
    words: str


def _open(ctx: _Ctx, name: str) -> bool:
    """The input is not given (for the last use: nor shown by the records at the address)."""
    fact: Fact[Any] = getattr(ctx.concept, name)
    if name == "existing_use_stated":
        return fact.missing and ctx.site.existing_use is None
    return fact.missing


def _named(missing: Sequence[str], name: str) -> bool:
    """The trigger names the input as missing (a chain whose count is not given is named by the count)."""
    if name == "formula_retail" and MISSING_PHRASES["other_locations"] in missing:
        return True
    return MISSING_PHRASES[name] in missing


def _area_bounds(ctx: _Ctx) -> tuple[int, ...]:
    """The floor areas at which T7's reading can change, from 1 square foot: each is the lowest area of a run of
    areas that T7 reads alike (the threshold, the cap, the Restaurant note's figure, the corner and large grocery
    caps, the other code text's figures)."""
    if not ctx.covered:
        return ()
    row = controls.use_size(ctx.zone, ctx.on)
    if row.principal_below_sqft is None:
        return ()
    found: set[int] = {1, row.principal_below_sqft, ONLY_IF_OVER_SQFT + 1}
    if row.not_permitted_from_sqft is not None:
        found.add(row.not_permitted_from_sqft)
    extra = row.extra
    exempt = extra.get("conditional_not_required_for")
    if isinstance(exempt, Mapping) and isinstance(exempt.get("larger_than_sqft"), int):
        found.add(exempt["larger_than_sqft"] + 1)
    for key in ("limited_corner_commercial_use_cap_sqft", "limited_corner_commercial_use_max_sqft"):
        cap = extra.get(key)
        if isinstance(cap, int):
            found.add(cap + 1)
    other = extra.get("other_code_text_figures")
    if isinstance(other, Mapping):
        found |= {v for k, v in other.items() if k.endswith("_sqft") and isinstance(v, int)}
    return tuple(sorted(v for v in found if v >= 1))


def _values(ctx: _Ctx, name: str) -> tuple[Any, ...]:
    """Every value an input can take, as the trigger reads it (for the floor areas: one per run read alike)."""
    concept = ctx.concept
    if name == "stories":
        stories = get_args(Story)
        return tuple(c for n in range(1, len(stories) + 1) for c in itertools.combinations(stories, n))
    if name in ("formula_retail", "merges_storefronts"):
        return (True, False)
    if name == "floor_area_sqft":
        return _area_bounds(ctx)
    if name == "changes_existing_business":
        return get_args(ExistingBusinessChange)
    if name == "floor_area_before_sqft":  # smaller than the floor area (it grows), or the same
        area = concept.floor_area_sqft.value
        return () if area is None else tuple(dict.fromkeys((max(area - 1, 0), area)))
    if name == "existing_use_stated":
        return tuple((u,) for u in get_args(ExistingUse))
    return ()


def _supposing(ctx: _Ctx, name: str, value: Any) -> _Ctx:
    """The context with one input supposed given, as stated."""
    changes: dict[str, Any] = {
        name: Fact(value, "stated", name),
        "cleared_facts": tuple(n for n in ctx.concept.cleared_facts if n != name),
        "cleared_readings": tuple(n for n in ctx.concept.cleared_readings if n != name),
    }
    concept = replace(ctx.concept, **changes)
    return _with_concept(ctx, concept)


def _suppositions(
    rule: Callable[[_Ctx], _Result], ctx: _Ctx, rule_id: str
) -> list[tuple[_Supposed, TriggerControl]]:
    """Every run of the trigger over the inputs not given: the inputs `READ_UNNAMED` first, then, while a run is
    not decided, the first input of `SUPPOSED_INPUTS` it names as missing. Each run's supposed values and control;
    a run still not decided once nothing more can be supposed is kept as not decided."""
    names = SUPPOSED_INPUTS.get(rule_id, ())
    out: list[tuple[_Supposed, TriggerControl]] = []

    def walk(c: _Ctx, supposed: dict[str, Any], pending: tuple[str, ...]) -> None:
        if pending:
            for value in _values(c, pending[0]):
                walk(_supposing(c, pending[0], value), {**supposed, pending[0]: value}, pending[1:])
            return
        result = rule(c)
        if result.control != "not_decided":
            out.append((supposed, result.control))
            return
        named = [n for n in names if n not in supposed and _named(result.missing, n)]
        values = _values(c, named[0]) if named else ()
        if not values:
            out.append((supposed, "not_decided"))
            return
        name = named[0]
        also = tuple(n for n in SUPPOSED_WITH.get(name, ()) if n not in supposed and _open(c, n))
        for value in values:
            walk(_supposing(c, name, value), {**supposed, name: value}, also)

    walk(ctx, {}, tuple(n for n in READ_UNNAMED.get(rule_id, ()) if _open(ctx, n)))
    return out


def _ways(ctx: _Ctx, rule_id: str) -> list[_Way]:
    """The ways an input not given can go that a condition may name, for this trigger: only inputs that are not
    given (an answer already given is never offered again as a way)."""
    concept = ctx.concept
    open_ = {n for n in SUPPOSED_INPUTS.get(rule_id, ()) if _open(ctx, n)}
    out: list[_Way] = []

    def given(name: str) -> Callable[[_Supposed], Any]:
        return lambda s: s.get(name)

    if "existing_use_stated" in open_:
        last = given("existing_use_stated")
        uses = [LAST_USE_LABELS[u] for u in get_args(ExistingUse) if u in NON_RESIDENTIAL_LAST_USES]
        out.append(
            _Way(
                "last_use_other",
                ("existing_use_stated",),
                lambda s: None if last(s) is None else last(s) == ("other",),
                CONDITION_WORDS["last_use_other"].format(uses=_either(uses)),
            )
        )
    if "changes_existing_business" in open_:
        change = given("changes_existing_business")
        out.append(
            _Way(
                "enlarged",
                ("changes_existing_business",),
                lambda s: None if change(s) is None else change(s) in ENLARGES,
                CONDITION_WORDS["enlarged"],
            )
        )
    if "floor_area_before_sqft" in open_:

        def grows(s: _Supposed) -> bool | None:
            before = s.get("floor_area_before_sqft")
            area = s.get("floor_area_sqft", concept.floor_area_sqft.value)
            return None if before is None or area is None else before < area

        out.append(_Way("grows", ("floor_area_before_sqft",), grows, CONDITION_WORDS["grows"]))
    if "merges_storefronts" in open_:
        merges = given("merges_storefronts")
        out.append(_Way("merged", ("merges_storefronts",), merges, CONDITION_WORDS["merged"]))
    if "formula_retail" in open_:
        chain = given("formula_retail")
        key = "chain_count" if concept.chain_count_missing else "chain"
        out.append(_Way(key, ("formula_retail",), lambda s: chain(s) is True, CONDITION_WORDS[key]))
    if "stories" in open_:
        # one way per set of stories: "occupies any of them" and "occupies none but them" (`_sufficient`)
        stories = given("stories")
        for n in range(1, len(get_args(Story)) + 1):
            for these in itertools.combinations(get_args(Story), n):
                words = _either([f"the {STORY_LABELS[story]}" for story in these])

                def any_of(s: _Supposed, these: tuple[str, ...] = these) -> bool | None:
                    got = stories(s)
                    return None if got is None else bool(set(got) & set(these))

                def within(s: _Supposed, these: tuple[str, ...] = these) -> bool | None:
                    got = stories(s)
                    return None if got is None else set(got) <= set(these)

                key = "story_only" if n == 1 else "story_within"
                out.append(
                    _Way(f"story/{n}", ("stories",), any_of, CONDITION_WORDS["story"].format(stories=words))
                )
                out.append(
                    _Way(f"{key}/{n}", ("stories",), within, CONDITION_WORDS[key].format(stories=words))
                )
    return out


def _either(words: Sequence[str]) -> str:
    """'a', 'a or b', 'a, b or c'; 'a (x, y or z), or b, or c' where a way's own words hold a comma."""
    if len(words) <= 1:
        return "".join(words)
    if any("," in w for w in words):
        return ", or ".join(words)
    return ", ".join(words[:-1]) + " or " + words[-1]


def _sufficient(
    target: TriggerControl, runs: Sequence[tuple[_Supposed, TriggerControl]], ways: Sequence[_Way]
) -> list[_Way]:
    """The ways under which every run gives `target`: every run that went that way, or did not turn on it, gives
    it, and at least one run went that way. Of the story ways, the widest that holds is kept: occupying any of the
    most stories, else occupying none but the most; none where it would take every story (the reading is then the
    same whatever the story, and is not shown as if it turned on it)."""

    def holds(way: _Way) -> bool:
        went = [(way.holds(s), c) for s, c in runs]
        return any(h is True for h, _ in went) and all(c == target for h, c in went if h is not False)

    out = [w for w in ways if not w.key.startswith("story") and holds(w)]
    every = len(get_args(Story))
    for kinds in (("story/",), ("story_only/", "story_within/")):
        found = [w for w in ways if w.key.startswith(kinds) and holds(w)]
        if found:
            widest = max(found, key=lambda w: int(w.key.split("/")[1]))
            if int(widest.key.split("/")[1]) < every:
                out.append(widest)
            break
    return out


def _area_words(low: int, high: int | None) -> str:
    if high is None:
        return CONDITION_WORDS["floor_area/from"].format(low=_square_feet(low))
    if low <= 1:
        return CONDITION_WORDS["floor_area/under"].format(high=_square_feet(high + 1))
    return CONDITION_WORDS["floor_area/between"].format(low=_square_feet(low), high=_square_feet(high))


def _contingent(
    rule_id: str, rule: Callable[[_Ctx], _Result], ctx: _Ctx, result: _Result
) -> tuple[list[ContingentReading], list[str]]:
    """The trigger's contingent readings, and the inputs not given that could change its decided control."""
    names = SUPPOSED_INPUTS.get(rule_id, ())
    unnamed = [n for n in READ_UNNAMED.get(rule_id, ()) if _open(ctx, n)]
    if result.control == "not_decided":
        if not unnamed and not any(_named(result.missing, n) for n in names):
            return [], []
    elif result.control not in _ASKS_FOR or not unnamed:
        return [], []
    runs = _suppositions(rule, ctx, rule_id)
    unsettled: list[str] = []
    if result.control != "not_decided":
        if all(c == result.control for _, c in runs):
            return [], []
        unsettled = list(ctx.concept.missing(unnamed))
    ways = _ways(ctx, rule_id)
    readings: list[ContingentReading] = []

    def reading(target: Literal["conditional", "not_permitted"], words: str, inputs: Iterable[str]) -> None:
        # what the condition turns on: the trigger's own missing inputs first, in its order, then the others in
        # the order the condition names them
        named = _each_once(p for n in inputs for p in ctx.concept.missing([n]))
        order = {phrase: i for i, phrase in enumerate(result.missing)}
        missing = sorted(named, key=lambda p: order.get(p, len(order)))
        readings.append(ContingentReading(control=target, condition=words, missing_inputs=missing))

    areas = sorted({s["floor_area_sqft"] for s, _ in runs if "floor_area_sqft" in s})
    if not areas:
        for target in _ASKS_FOR:
            found = _sufficient(target, runs, ways)
            if found:
                inputs = [n for w in found for n in w.inputs]
                reading(target, _either([w.words for w in found]), inputs)
        return readings, unsettled
    # the floor area is not given: the runs of areas T7 reads alike, merged where they give the same answer
    for target in _ASKS_FOR:
        spans: list[tuple[int, int | None, bool, tuple[_Way, ...]]] = []
        for i, low in enumerate(areas):
            high = areas[i + 1] - 1 if i + 1 < len(areas) else None
            these = [(s, c) for s, c in runs if s.get("floor_area_sqft", low) == low]
            alone = bool(these) and all(c == target for _, c in these)
            kept: tuple[_Way, ...] = () if alone else tuple(_sufficient(target, these, ways))
            if not alone and not kept:
                continue
            last = spans[-1] if spans else None
            same = last is not None and (last[2], [w.key for w in last[3]]) == (alone, [w.key for w in kept])
            if last is not None and same and last[1] == low - 1:
                spans[-1] = (last[0], high, alone, kept)
            else:
                spans.append((low, high, alone, kept))
        for low, high, alone, kept in spans:
            area = _area_words(low, high)
            inputs = ["floor_area_sqft", *(n for w in kept for n in w.inputs)]
            if alone:
                reading(target, area, inputs)
            else:
                key = "floor_area/and" if len(kept) == 1 else "floor_area/and_either"
                reading(
                    target,
                    CONDITION_WORDS[key].format(area=area, ways=_either([w.words for w in kept])),
                    inputs,
                )
    return readings, unsettled


def evaluate(
    concept: ConceptFacts,
    site: SiteFacts,
    zoning: ZoningInfo | None,
    overlays: Sequence[Overlay],
    *,
    rules_date: dt.date,
    today: dt.date,
    as_new: bool = False,
) -> list[TriggerFinding]:
    """One finding for each of T1 to T11, in that order, for the rules in force on `rules_date`.

    `today` is passed in (the rules read no clock): `differs_today` is set on a finding when the same question
    answered for `today` gives a different control. The answer does not depend on the order of `overlays`.

    `as_new` reads every trigger as for a NEW use: no business and no use at the address is taken to continue,
    whatever the description and the records say. The engine uses it for `Pathway.permission` ("for a new use
    of this kind here") when a use continues; the rows are always set from the plain reading."""
    rules_date, today = _day(rules_date), _day(today)
    ctx = _context(concept, site, zoning, overlays, rules_date)
    if as_new:
        ctx = replace(
            ctx, business_continues=False, continuing=frozenset(), maybe_continuing=frozenset(), as_new=True
        )
    findings: list[TriggerFinding] = []
    for rule_id, rule in _TRIGGERS:
        result = rule(ctx)
        contingent, unsettled = _contingent(rule_id, rule, ctx, result)
        lines = list(result.lines)
        now = rule(replace(ctx, on=today)) if today != rules_date else result
        differs = _asks(now.control) != _asks(result.control)
        if differs:
            since, ordinance = _changed(rule, ctx, today, now)
            words = CONTROL_WORDS[now.control]
            if since is None:
                lines.append(_line("differs/undated", rule_id=f"{rule_id}.differs", today=words))
            elif ordinance is None:
                lines.append(
                    _line(
                        "differs/no_ordinance",
                        rule_id=f"{rule_id}.differs",
                        date=since.isoformat(),
                        today=words,
                    )
                )
            else:
                lines.append(
                    _line(
                        "differs",
                        rule_id=f"{rule_id}.differs",
                        date=since.isoformat(),
                        ordinance=ordinance,
                        today=words,
                    )
                )
        if result.historic:
            lines.append(
                _line(
                    "historic",
                    rule_id=f"{rule_id}.historic",
                    date=controls.HISTORIC_BUILDINGS_FROM.isoformat(),
                )
            )
        if result.dated and rules_date < controls.DATA_START:
            lines.append(
                _line(
                    "before_start",
                    rule_id=f"{rule_id}.before_start",
                    start=controls.DATA_START.isoformat(),
                    date=rules_date.isoformat(),
                )
            )
        family = FAMILIES[rule_id]
        findings.append(
            TriggerFinding(
                rule_id=rule_id,
                family=family,
                label=TRIGGER_LABELS[family],
                control=result.control,
                missing_inputs=list(result.missing),
                lines=pw._merge(lines),
                in_force_from=_iso(result.in_force_from),
                ordinance=result.ordinance,
                differs_today=differs,
                contingent=contingent,
                unsettled_by=unsettled,
            )
        )
    return findings


# ---- what the row rules read (spec section 4) ----------------------------------------------------------------------
def matters(finding: TriggerFinding) -> bool:
    """Does this finding change the zoning row: it is not permitted, conditional, not decided, or a place where
    the Code and Planning practice differ. A trigger is "not_decided" only where it matters in the district, so
    a missing input in a district where the trigger is principal for every answer never makes this true."""
    return finding.control in MATTERS


def by_id(findings: Iterable[TriggerFinding], rule_id: str) -> TriggerFinding:
    """The finding of one trigger ("T4")."""
    return next(f for f in findings if f.rule_id == rule_id)


def with_control(findings: Iterable[TriggerFinding], control: TriggerControl) -> list[TriggerFinding]:
    return [f for f in findings if f.control == control]


def not_permitted(findings: Iterable[TriggerFinding]) -> list[TriggerFinding]:
    return with_control(findings, "not_permitted")


def conditional(findings: Iterable[TriggerFinding]) -> list[TriggerFinding]:
    return with_control(findings, "conditional")


def not_decided(findings: Iterable[TriggerFinding]) -> list[TriggerFinding]:
    return with_control(findings, "not_decided")


def practice_differs(findings: Iterable[TriggerFinding]) -> list[TriggerFinding]:
    return with_control(findings, "code_and_practice_differ")


def missing_inputs(findings: Iterable[TriggerFinding]) -> tuple[str, ...]:
    """What the findings that are not decided name as not known, each once, in trigger order."""
    return _each_once(m for f in not_decided(findings) for m in f.missing_inputs)


class ZoningOutcome(NamedTuple):
    """The zoning and use row as spec section 4 sets it from the triggers."""

    status: ApprovalStatus
    status_note: str | None  # PRACTICE_DIFFERS_NOTE, or None
    deciding: tuple[TriggerFinding, ...]  # the findings that set the status; empty when allowed
    missing_inputs: tuple[str, ...]  # named when the status is insufficient_information


def story_not_given(findings: Iterable[TriggerFinding]) -> list[TriggerFinding]:
    """The findings that are not decided because no story is given (they name MISSING_PHRASES["stories"])."""
    return [f for f in not_decided(findings) if MISSING_PHRASES["stories"] in f.missing_inputs]


def zoning_outcome(findings: Sequence[TriggerFinding]) -> ZoningOutcome:
    """Spec section 4, zoning and use row: any trigger not permitted -> not_permitted; else (Z-S) a trigger not
    decided because no story is given -> insufficient_information, naming what is missing, even where another
    trigger is conditional (the user's decision of 2026-11-12: a missing story is always "Insufficient
    information" and is never resolved by assuming a story); else any conditional -> further_review; else any not
    decided -> insufficient_information, naming what is missing; else the Code and Planning practice differ ->
    further_review with that note; else allowed."""
    if found := not_permitted(findings):
        return ZoningOutcome("not_permitted", None, tuple(found), ())
    if story_not_given(findings):  # Z-S
        found = not_decided(findings)
        return ZoningOutcome("insufficient_information", None, tuple(found), missing_inputs(found))
    if found := conditional(findings):
        return ZoningOutcome("further_review", None, tuple(found), ())
    if found := not_decided(findings):
        return ZoningOutcome("insufficient_information", None, tuple(found), missing_inputs(found))
    if found := practice_differs(findings):
        return ZoningOutcome("further_review", PRACTICE_DIFFERS_NOTE, tuple(found), ())
    return ZoningOutcome("allowed", None, (), ())


def _bound_rule(line: RuleLine) -> Binding | None:
    """The binding of the special district rule a line was built around ("T4:<rule_id>")."""
    _, _, rule_id = line.rule_id.partition(":")
    return BOUND.get(rule_id) if rule_id else None


def requirements(findings: Iterable[TriggerFinding]) -> list[RuleLine]:
    """The lines that state a requirement of a special district (a condition, not a control), in order."""
    return [
        line
        for f in findings
        for line in f.lines
        if (binding := _bound_rule(line)) is not None and binding.requirement
    ]


def blocking_requirements(findings: Iterable[TriggerFinding]) -> list[RuleLine]:
    """The requirements that could stop the licence (spec section 4, alcohol row: a potential blocker). One is
    bound: in the Mission district a new Bar must use a licence transferred from a Bar inside the district."""
    return [
        line
        for line in requirements(findings)
        if (binding := _bound_rule(line)) is not None and binding.could_stop
    ]
