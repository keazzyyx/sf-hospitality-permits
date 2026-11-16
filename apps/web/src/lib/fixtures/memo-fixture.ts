import type {
  AdminOverview,
  ApprovalArea,
  ApprovalStatus,
  Citation,
  ComparableCase,
  CountedDecision,
  GeoJsonFeatureCollection,
  HeadlineFinding,
  Me,
  Memo,
  MemoApprovalRow,
  MemoFact,
  MemoRecord,
  MemoSummary,
  OpenQuestion,
  Pathway,
  RecordKind,
  SiteHistory,
  SiteHistoryEntry,
} from "@/lib/api-types";
import EVIDENCE from "./evidence-995-valencia.json";
import RULE_SET from "./determinations-995-valencia.json";

/**
 * Sample memo in report format 3 (the rules and the evidence; no text a model wrote) for the development preview
 * route (`/dev/memo-preview`), the landing-page sample card and the Playwright suite. Shaped exactly like
 * `GET /v1/memos/{id}` (apps/api/app/models/memo.py).
 *
 * The example is a 40-seat wine bar at 995 Valencia St. Nothing in it is written by hand except the few
 * made-up records the variants below say are made up:
 *   - what the rules set (the pathway with its triggers, its three change-of-use answers and its rules date,
 *     each row's approval, agency, status, status note, rule lines, referral steps and missing inputs, the
 *     overall status and line, the entitlement path, the rules' open questions) and the facts the rules read
 *     with where each came from are read from `determinations-995-valencia.json`, which a test in the API writes
 *     from `app.memo.pathway.determine` and `app.memo.evidence` and pins (apps/api/tests/test_pathway_cases.py,
 *     `test_the_web_fixture_carries_what_the_rules_return`);
 *   - the comparable cases, their citations, what each site record carries (use, closing hour, conditions) and
 *     the decisions behind the outcome counts are read from `evidence-995-valencia.json`, which
 *     `MemoRunner.collect_records` returned from the local validation database for the same case;
 *   - the zoning, overlay and site-history records are the public records the local validation runs read for
 *     that address (docs/validation/part3).
 *
 * What the rules (rule table v2) give for this example, run as its description reads, and why:
 *   zoning and use        Further review            a Bar is a conditional use in NCT-VALENCIA and in the Mission
 *                                                   Alcoholic Beverage SUD, so it needs a Conditional Use
 *                                                   Authorization; formula retail, nighttime entertainment and
 *                                                   use size are not decided because the description does not
 *                                                   give those inputs
 *   alcohol licence       Insufficient information  the description does not say how the licence is to be
 *                                                   obtained (new, or transferred), so the rules cannot say
 *                                                   which licence rules apply; the row names that input
 *   entertainment permit  Further review            live music needs an Entertainment Commission permit
 *   health permit         Allowed                   plan check, inspection, permit to operate
 *   building permit       Further review            the records show a Restaurant here (an active Type 41 licence
 *                                                   at the address) and the concept is a Bar: a change of use
 *   read first (headline findings, from 2026-11-16, as generated): the Mission district's rule asks for a
 *   Conditional Use whatever the story; the use size control would if the floor area is 3,001 square feet or more.
 *
 * Variants:
 *   MEMO_RECORD_FULL_RATE            a base rate large enough to show a percentage (its counts are made up, so it
 *                                    lists no counted decisions)
 *   MEMO_RECORD_FULL_RULES_DATE      the same report generated two days after its rules date, as a backtest
 *                                    report is; the page prints "Rules applied as of" whatever the day. Only `generated_at` differs.
 *   MEMO_RECORD_FULL_BEFORE_V2       the same report without the fields rule table v2 added. Fields are removed; none is typed.
 *   MEMO_RECORD_FULL_HISTORY_LONG    37 records at the site with the newest 20 listed. The 14 extra records are
 *                                    made up to fill the list; they are not real records.
 *   MEMO_RECORD_FULL_HISTORY_ONE     one record at the site (no date, no outcome), which does not show a use
 *   MEMO_RECORD_FULL_HISTORY_EMPTY   no records at the site
 *   MEMO_RECORD_FULL_UNLABELLED      records that carry no kind labels yet
 *   MEMO_RECORD_FULL_NOT_PERMITTED   a second address (a wine bar at 1448 Pacific Ave, NCD-PACIFIC) where the
 *                                    district's table does not permit a Bar: the alcohol and health rows follow
 *                                    the zoning row, and there is no approval path. Its rule-set parts, facts,
 *                                    zoning record and citations are generated from the API like the rest; the
 *                                    record sections are left empty.
 * With one record or none at the site the rules cannot say what the space is used as now, so in those two
 * variants the change of use is "not established" and the building row is Insufficient information.
 */

const SUBJECT = { lat: 37.7570827, lng: -122.4208381 };
const SITE_ADDRESS = "995 Valencia St";
const ADDRESS = "995 Valencia St, San Francisco, CA 94110";
const PARCEL = "3609/026";
const DISTRICT = "NCT-VALENCIA";

// Citation ids as the runner writes them (`_build_citations` in apps/api/app/agents/memo_runner.py).
const ZONING = `zoning:${DISTRICT}`;
const MISSION_SUD = "overlay:datasf_sud:mission_alcohol_restrict";

// The API writes these strings itself (apps/api/app/memo/analytics.py): the scope always starts with N, and
// when records were left out it ends with the list of what was left out (`left_out_clause`).
function leftOut(grantOnly: number, notUseDecision: number, undated: number): string {
  const parts = [
    grantOnly ? (grantOnly === 1 ? "1 permit or licence" : `${grantOnly} permits and licences`) : "",
    notUseDecision
      ? notUseDecision === 1
        ? "1 record that is not a use decision for this kind of business"
        : `${notUseDecision} records that are not use decisions for this kind of business`
      : "",
    undated ? `${undated} undated` : "",
  ].filter(Boolean);
  return parts.length ? `; left out: ${parts.join(", ")}` : "";
}
const BASE_RATE_SCOPE = "N = 3 dated decisions within 1,000 ft, last 10 years (fewer than 5 in the last 5); too few for a rate";

const BASE_RATE: Memo["base_rate"] = {
  approved: 1,
  approved_with_conditions: 0,
  denied: 0,
  withdrawn: 2,
  total: 3,
  window_years: 10,
  scope: BASE_RATE_SCOPE + leftOut(74, 321, 0),
  rate_shown: false,
  approval_rate_pct: null,
  excluded_grant_only: 74,
  excluded_undated: 0,
  excluded_not_use_decision: 321,
  citation_id: "stat:base_rate",
  // the three decisions counted, each with its link (read from the local validation database: EVIDENCE)
  counted: EVIDENCE.counted as CountedDecision[],
};


/** The base-rate citation as the runner writes it (`_build_citations` in apps/api/app/agents/memo_runner.py). */
function baseRateCitation(b: Memo["base_rate"]): Citation {
  const notUseDecisions = b.excluded_not_use_decision
    ? `, ${b.excluded_not_use_decision} Planning records that are not use decisions for this kind of business (agency referrals, building work, other records, decisions about other kinds of business)`
    : "";
  return {
    id: "stat:base_rate",
    kind: "statistic",
    label: `Dated Planning decisions: ${b.approved + b.approved_with_conditions} approved / ${b.denied} denied / ${b.withdrawn} withdrawn; ${b.scope}`,
    source_url: "https://data.sf.gov",
    excerpt: `Not counted: ${b.excluded_grant_only} Entertainment Commission permits and ABC licences (lists of grants only)${notUseDecisions} and ${b.excluded_undated} decided Planning rows without both dates.`,
  };
}

/**
 * The citation the runner adds for a record (`_application_citation`): id "app:<application_id>", label
 * "<permit type> · <address> · <outcome> (<year>)", and the record's description as the excerpt.
 */
function recordCitation(r: Pick<SiteHistoryEntry, "application_id" | "permit_type" | "description" | "address" | "filed_at" | "decided_at" | "outcome" | "source_url">): Citation {
  const when = r.decided_at ?? r.filed_at;
  return {
    id: `app:${r.application_id}`,
    kind: "application",
    label: `${r.permit_type} · ${r.address ?? "address n/a"} · ${r.outcome.replace(/_/g, " ")}${when ? ` (${when.slice(0, 4)})` : ""}`,
    source_url: r.source_url,
    excerpt: r.description || null,
  };
}

/**
 * The memo with the citation list the API would send for it: the base-rate citation written from the memo's own
 * base rate, and one citation for every listed site-history record, an ABC licence included.
 */
function withCitations(memo: Memo): Memo {
  const citations = memo.citations.map((c) => (c.id === "stat:base_rate" ? baseRateCitation(memo.base_rate) : c));
  const have = new Set(citations.map((c) => c.id));
  for (const e of memo.site_history.entries) {
    if (have.has(e.citation_id)) continue;
    have.add(e.citation_id);
    citations.push(recordCitation(e));
  }
  return { ...memo, citations };
}

// Where the two code sections behind the zoning answer can be read (the URLs on the zoning and overlay records).
const URL_762 = "https://codelibrary.amlegal.com/codes/san_francisco/latest/sf_planning/0-0-0-25360#rid-0-0-0-57178";
const URL_249_60 = "https://codelibrary.amlegal.com/codes/san_francisco/latest/sf_planning/0-0-0-34810";
// The zoning record's own text for the district (ZoningInfo.rules); the Valencia Street NCT overlay carries the same text.
const ZONING_RULES =
  "Bar requires Conditional Use Authorization; Restaurant principally permitted (First Story). Bar C on the First Story only; Liquor Store NP; within the Mission Alcoholic Beverage SUD (§ 249.60), a new Bar must use a license transferred from another Bar in the SUD.";
const ZONING_SECTION = "Planning Code § 762 (Zoning Control Table 762); § 102 (Bar, Restaurant)";
// The overlay record's own text (Overlay.effect).
const MISSION_SUD_EFFECT =
  "No new Liquor Stores. A Restaurant operating as a Bona Fide Eating Place may serve alcohol (licenses may be transferred in from inside or outside the SUD), as may non-profit theaters, bowling alleys/mini-golf with an integrated Restaurant, single-screen movie theaters (beer and wine) and ABC Type 90 music venues. A new or relocated Bar is considered under the underlying zoning but only as a Conditional Use, and must use a liquor license transferred from another Bar within the SUD. Existing liquor establishments may relocate or expand only with CU. East of the western boundary of the Mission Street NCT and north of Cesar Chavez Street, any new Restaurant requires CU and new ABC Type 75 (brewpub) licenses are prohibited. Good-neighbor operating conditions (§ 202.2 plus lighting and window-signage limits) apply.";

const CITATIONS: Memo["citations"] = [
  { id: ZONING, kind: "zoning", label: `Zoning ${DISTRICT} — ${ZONING_SECTION}`, source_url: URL_762, excerpt: ZONING_RULES },
  {
    id: MISSION_SUD,
    kind: "overlay",
    label: "Mission Alcoholic Beverage Special Use District — Planning Code § 249.60 (§ 781.8 cross-references it)",
    source_url: URL_249_60,
    excerpt: MISSION_SUD_EFFECT,
  },
  {
    id: "overlay:static:sf:nc_nct_valencia",
    kind: "overlay",
    label: `Valencia Street Neighborhood Commercial Transit District — ${ZONING_SECTION}`,
    source_url: URL_762,
    excerpt: ZONING_RULES,
  },
  {
    // The district's own row in the zoning map layer (an overlay record the runner cites like any other).
    id: `overlay:datasf_zoning:${DISTRICT}`,
    kind: "overlay",
    label: `${DISTRICT} — Planning Code § 762 (zoning control table for ${DISTRICT})`,
    source_url: URL_762,
    excerpt: ZONING_RULES,
  },
  {
    id: "overlay:datasf_sud:priority_equity_geographies_sud",
    kind: "overlay",
    label: "Priority Equity Geographies SUD — Planning Code § 249.97",
    source_url: "https://codelibrary.amlegal.com/codes/san_francisco/latest/sf_planning/0-0-0-68826",
    excerpt: "Priority Equity Geographies SUD: special use district on the SF Zoning Map; its controls are in Planning Code § 249.97.",
  },
  baseRateCitation(BASE_RATE),
  {
    id: "geo:address",
    kind: "statistic",
    label: `Address record: ${ADDRESS} (datasf_eas)`,
    source_url: "https://data.sf.gov/resource/3mea-di5p.json?eas_baseid=443862",
    excerpt: `parcel ${PARCEL}`,
  },
  // The comparable cases' own records (EVIDENCE.comparable_citations), as the runner writes them.
  ...(EVIDENCE.comparable_citations as Citation[]),
  // The records at the address itself (see SITE_ENTRIES) are added by `withCitations`, one citation per listed record.
];

// RECORDS_LIMITS in apps/api/app/models/memo.py: the one fixed line the API sends with every memo.

// RECORDS_LIMITS in apps/api/app/models/memo.py: the one fixed line the API sends with every memo.
const RECORDS_LIMITS =
  "Physical and cost issues are outside what public records can show: ventilation and kitchen exhaust, exits and occupant load, accessibility, the condition of the space, and the landlord's consent.";

// Copied from STATUS_DEFINITIONS in apps/api/app/models/memo.py; the API sends them with every memo.
const STATUS_DEFINITIONS: Memo["status_definitions"] = {
  allowed:
    "Allowed: the cited records or code sections show this approval is available as of right, or already exists for this space, without a discretionary hearing.",
  further_review:
    "Further review: the approval is obtainable only through a discretionary or multi-step review (a hearing, a referral, a licence investigation) whose result the records do not settle.",
  potential_blocker:
    "Potential blocker: a cited rule, cap or record could stop this approval or force a change to the concept unless a specific condition is met.",
  not_permitted: "Not permitted: a cited code section prohibits this use or approval at this address as the concept is described.",
  insufficient_information:
    "Insufficient information: the records in hand do not show whether this approval is needed or obtainable; the could-not-establish section says what would settle it.",
};

const NO_HISTORY_NOTE = "No outcome history for this pathway yet.";
// NO_HISTORY_AREAS in apps/api/app/models/memo.py: the rows that carry NO_HISTORY_NOTE.
const NO_HISTORY_AREAS: readonly ApprovalArea[] = ["alcohol", "entertainment"];

// Source names and labels as in SOURCE_NOTES (apps/api/app/memo/report.py). A Planning row whose Commission
// motion was read reports the motion as its source.
const PLANNING = { source: "datasf_planning", source_label: "Planning case list (DataSF)" } as const;
const MOTION = { source: "sf_planning_hearings", source_label: "Planning Commission motion" } as const;

// Record kinds and their labels, as RECORD_KIND_LABELS in apps/api/app/models/memo.py.
const KIND_LABELS: Record<RecordKind, string> = {
  use_decision: "Use decision",
  agency_referral: "Agency referral",
  building_work: "Building work",
  other: "Other record",
  licence: "ABC licence",
  entertainment_permit: "Entertainment permit",
  not_labelled: "Not labelled",
};

// The API's own strings: `site_matched_by`, SITE_HISTORY_NOTE and SITE_HISTORY_EMPTY_NOTE in apps/api/app/memo/report.py.
const SITE_MATCHED_BY = `Parcel ${PARCEL} or the address ${SITE_ADDRESS}`;
const SITE_NOTE = "Records on file at this address or parcel, newest first. Building work is listed here and is not counted in the outcome counts.";
const SITE_NOTE_EMPTY = "No records at this address or parcel in the data. That does not mean nothing was ever filed here.";

/** What a site record carries about its use, closing hour and conditions (EVIDENCE.site_recorded; none for a made-up record). */
function recorded(id: string): Pick<SiteHistoryEntry, "use_types" | "hours_close" | "conditions"> {
  const r = (EVIDENCE.site_recorded as Record<string, Pick<SiteHistoryEntry, "use_types" | "hours_close" | "conditions">>)[id];
  return r ? { use_types: r.use_types, hours_close: r.hours_close, conditions: r.conditions } : { use_types: [], hours_close: null, conditions: [] };
}

/**
 * One Planning record. Ids are "<source>:<source_id>", citation ids "app:<id>". The Planning case list gives a
 * decision date only when the outcome is known (packages/precedent, datasf_planning). Addresses are the
 * source's own strings.
 */
function planningRecord(recordId: string, kind: RecordKind, permitType: string, description: string, address: string, filed: string, decided: string | null, outcome: string, status: string): SiteHistoryEntry {
  return {
    application_id: `datasf_planning:${recordId}`,
    citation_id: `app:datasf_planning:${recordId}`,
    ...PLANNING,
    record_kind: kind,
    record_kind_label: KIND_LABELS[kind],
    permit_type: permitType,
    description,
    address,
    filed_at: filed,
    decided_at: decided,
    outcome,
    status,
    source_url: `https://sfplanninggis.org/pim?search=${recordId}`,
    ...recorded(`datasf_planning:${recordId}`),
  };
}

/** An ABC licence: the export has no filing date; the decision date is the date the licence was issued. */
function abcLicence(licence: string, permitType: string, holder: string, address: string, issued: string): SiteHistoryEntry {
  return {
    application_id: `abc:${licence}`,
    citation_id: `app:abc:${licence}`,
    source: "abc",
    source_label: "ABC licence export",
    record_kind: "licence",
    record_kind_label: KIND_LABELS.licence,
    // The permit type and description are the ABC source's own strings, dashes included (packages/precedent, abc).
    permit_type: permitType,
    description: `${holder} — ${permitType} (ACTIVE)`,
    address,
    filed_at: null,
    decided_at: issued,
    outcome: "approved",
    status: "ACTIVE",
    source_url: `https://www.abc.ca.gov/licensing/license-lookup/single-license/?RPTTYPE=12&LICENSE=${licence}`,
    ...recorded(`abc:${licence}`),
  };
}

const PRL = "Project Profile Lite";
const MIS = "Miscellaneous Permit";
const CUA = "Conditional Use Authorization";
const APPROVED = ["approved", "Closed - Approved"] as const;

// The nine records on file at 995 Valencia St or its parcel, newest first, as the local validation database has
// them. The parcel also holds 991 to 999 Valencia St, so a shop's off-sale licence and its Conditional Use are
// listed. The Type 41 licence is the one at the report's own street address: it is what shows a Restaurant here.
const SITE_ENTRIES: SiteHistoryEntry[] = [
  abcLicence("650575", "Type 20 – Off-Sale Beer & Wine", "VALENCIA WHOLE FOODS", "999 VALENCIA ST, SAN FRANCISCO, CA 94110", "2024-01-10"),
  abcLicence("651564", "Type 41 – On-Sale Beer & Wine - Eating Place", "SARITA'S GRILL & BEER", "995 VALENCIA ST, SAN FRANCISCO, CA 94110", "2023-11-03"),
  {
    ...planningRecord(
      "2023-002340CUA",
      "use_decision",
      CUA,
      "The Project is seeking Conditional Use authorization from Planning Code Section 249.60 related to Valencia Whole Foods' purchase of a Type 20 liquor license from Ish's Community Market Corp.",
      "999 VALENCIA ST 94110",
      "2023-04-04",
      "2023-07-27",
      "approved_with_conditions",
      "Closed - Approved",
    ),
    ...MOTION,
  },
  planningRecord(
    "2020-012158MIS",
    "agency_referral",
    MIS,
    "DPH referral - Restaurant Recommend approval for 995 Valencia Street as a continuation of restaurant use per Section 102 and 762 and Conditional Use authorization Motion No. 18363",
    "995 VALENCIA ST 94110",
    "2020-12-30",
    "2021-01-20",
    ...APPROVED,
  ),
  planningRecord("2011.0255C", "use_decision", CUA, "Existing full service restaurant changing ABC license from a Type 41 to a Type 47.", "991 - 999 VALENCIA ST, SAN FRANCISCO, CA 94110", "2011-03-17", "2011-05-19", ...APPROVED),
  planningRecord("MB1000854", "agency_referral", MIS, "Type 41 accessory to full service restaurant. -", "995 - 999 VALENCIA ST, SAN FRANCISCO, CA 94110", "2010-08-10", "2010-08-11", ...APPROVED),
  planningRecord("MB0201343", "agency_referral", MIS, "Large full service restaurant permitted per Planning codeSection 726.42 & 790.92. -", "995 VALENCIA ST ST., SAN FRANCISCO, CA 94110", "2002-12-04", "2002-12-10", ...APPROVED),
  planningRecord("MB0100446", "agency_referral", MIS, "Large full service restaurant permitted per Planning Code Section 726.42 and 730.92. -", "995 - 999 VALENCIA ST STREET, SAN FRANCISCO, CA 94110", "2001-05-16", "2001-06-11", ...APPROVED),
  planningRecord("MA9901527", "agency_referral", MIS, "- Large full service restaurant approved per Planning Code Sections 726.42 and 790.92 (waiter service and seating).", "991 - 999 VALENCIA ST BSMT, SAN FRANCISCO, CA 94110", "1999-08-18", "1999-08-25", ...APPROVED),
];

function countByKind(entries: SiteHistoryEntry[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const e of entries) out[e.record_kind] = (out[e.record_kind] ?? 0) + 1;
  return out;
}

const SITE_HISTORY: SiteHistory = {
  matched_by: SITE_MATCHED_BY,
  total: SITE_ENTRIES.length,
  by_kind: countByKind(SITE_ENTRIES),
  entries: SITE_ENTRIES,
  note: SITE_NOTE,
};

// ---------------------------------------------------------------------------
// What the rules set, and the facts they read (read from the generated file; nothing here is hand-written)
// ---------------------------------------------------------------------------

/** `Determinations` in apps/api/app/models/memo.py: what the rules return for one set of records. */
interface RuleSet {
  pathway: Pathway;
  rows: Pick<MemoApprovalRow, "area" | "approval" | "agency" | "status" | "status_note" | "basis" | "referral_steps" | "missing_inputs">[];
  overall_status: ApprovalStatus;
  overall_line: string;
  entitlement_path: string;
  open_questions: OpenQuestion[];
  headline_findings: HeadlineFinding[];  // printed first (app.memo.pathway rule 9)
  // The facts the rules read (apps/api/app/memo/evidence.py), generated with the rules: every fact, and each row's known ones.
  facts: MemoFact[];
  row_facts: Partial<Record<ApprovalArea, MemoFact[]>>;
}

/** The records as they are: an active Type 41 licence at the address shows a Restaurant, so a Bar is a change of use. */
const RULES = RULE_SET.with_licence as unknown as RuleSet;
/** The same address with no licence on file: the change of use is not established, and the building row names what is missing. */
const RULES_NO_LICENCE = RULE_SET.no_licence as unknown as RuleSet;

// APPROVAL_AREA_LABELS in apps/api/app/models/memo.py.
const AREA_LABELS: Record<ApprovalArea, string> = {
  zoning_use: "Zoning and use",
  alcohol: "Alcohol licence",
  entertainment: "Entertainment permit",
  health: "Health permit",
  building_change_of_use: "Building permit and change of use",
  outdoor: "Outdoor seating or activity area",
};

/** The rows as the API sends them: the rules' part of each row with the facts its rules read. */
function rowsOf(rules: RuleSet): MemoApprovalRow[] {
  return rules.rows.map((r) => ({
    ...r,
    area_label: AREA_LABELS[r.area],
    facts: rules.row_facts[r.area] ?? [],
    history_note: NO_HISTORY_AREAS.includes(r.area) ? NO_HISTORY_NOTE : null,
  }));
}

/**
 * The fields the API takes from the rules: the headline findings, the pathway, the rows, the overall status and
 * line (and the ids the rule lines cite), the entitlement path, the rules' open questions and the facts.
 */
function fromRules(memo: Omit<Memo, "pathway" | "approvals" | "overall" | "entitlement_path" | "could_not_establish" | "facts">, rules: RuleSet): Memo {
  const rows = rowsOf(rules);
  return {
    ...memo,
    headline_findings: rules.headline_findings,
    pathway: rules.pathway,
    approvals: rows,
    overall: {
      status: rules.overall_status,
      line: rules.overall_line,
      citations: Array.from(new Set(rows.flatMap((r) => r.basis.flatMap((l) => l.citations)))),
    },
    entitlement_path: rules.entitlement_path,
    could_not_establish: rules.open_questions,
    facts: rules.facts,
  };
}

// COMPARABLES_NOTE in apps/api/app/memo/evidence.py, for the ten cases listed.
const COMPARABLES_NOTE = (n: number) =>
  `Planning and Entertainment Commission records within 1,000 ft, ranked by a fixed score: the kind of business in common (40%), the distance (25%), how recent the record is (15%), late-night hours in common (10%) and whether the case was decided (10%); a Conditional Use case scores a little higher. The top ${n} are listed, best first. Each row shows what the record says, with a link to it. No model picks them.`;
// DISCLAIMERS in apps/api/app/agents/memo_runner.py.
const DISCLAIMERS = [
  "Permit Memo is operational guidance, not legal advice. Confirm every requirement with the issuing agency before relying on it.",
  "Comparable cases and counts come from public records (DataSF, California ABC, SF Planning) as of the data date shown; records may lag agency decisions by weeks.",
  "Statuses are set by rules from the public record and are not a guarantee. Planning Commission and ABC decisions are discretionary.",
  "No sentence in this report is written by an AI model. A model reads your description into facts; each fact shows the words it came from, and what your words do not state is listed as not known.",
];
const DESCRIPTION = "40-seat wine bar, small kitchen, open until 1am, occasional live music";
const COMPARABLES = EVIDENCE.comparable_cases as ComparableCase[];

const MEMO_BASE: Memo = fromRules(
  {
    format_version: 3,
    address: ADDRESS,
    lat: SUBJECT.lat,
    lng: SUBJECT.lng,
    parcel: PARCEL,
    description: DESCRIPTION,
    records_limits: RECORDS_LIMITS,
    zoning: {
      district: DISTRICT,
      name: "Valencia Street Neighborhood Commercial Transit District",
      bar_permission: "conditional",
      restaurant_permission: "principal",
      rules: ZONING_RULES,
      code_section: ZONING_SECTION,
      citation_id: ZONING,
    },
    overlays: [
      { name: "Mission Alcoholic Beverage Special Use District", kind: "alcohol_sud", effect: MISSION_SUD_EFFECT, code_section: "Planning Code § 249.60 (§ 781.8 cross-references it)", citation_id: MISSION_SUD },
      { name: "Valencia Street Neighborhood Commercial Transit District", kind: "nc_rule", effect: ZONING_RULES, code_section: ZONING_SECTION, citation_id: "overlay:static:sf:nc_nct_valencia" },
      {
        name: "Priority Equity Geographies SUD",
        kind: "special_use_district",
        effect: "Priority Equity Geographies SUD: special use district on the SF Zoning Map; its controls are in Planning Code § 249.97.",
        code_section: "Planning Code § 249.97",
        citation_id: "overlay:datasf_sud:priority_equity_geographies_sud",
      },
    ],
    base_rate: BASE_RATE,
    comparable_cases: COMPARABLES,
    comparables_note: COMPARABLES_NOTE(COMPARABLES.length),
    site_history: SITE_HISTORY,
  source_notes: [
    { source: "datasf_planning", label: "Planning case list (DataSF)", leaves_out: "Outcome and dates only. Conditions are not in this list unless the Commission motion was read; withdrawn and cancelled cases carry no reason. The decision date is the date Planning closed the record." },
    { source: "sf_planning_hearings", label: "Planning Commission motion", leaves_out: "Conditions as adopted at the hearing. Later amendments, enforcement history and whether the business opened are not included." },
    { source: "datasf_entertainment", label: "Entertainment Commission permit list (DataSF)", leaves_out: "Active permits only: no denials, withdrawals, filing dates or conditions, so it cannot show that an application failed." },
    { source: "abc", label: "ABC licence export", leaves_out: "Licences that are active or pending today. Denied and withdrawn applications are absent and there is no filing date, so it cannot show a failure or a processing time." },
  ],
    status_definitions: STATUS_DEFINITIONS,
    citations: CITATIONS,
    disclaimers: DISCLAIMERS,
    generated_at: "2026-11-10T11:21:23Z",
    model_versions: { intake: "claude-sonnet-4-5" },
    data_as_of: "2026-11-09",
  },
  RULES,
);

export const MEMO_FIXTURE_FULL: Memo = withCitations(MEMO_BASE);

function teaserOf(memo: Memo): NonNullable<MemoRecord["teaser"]> {
  return {
    overall_status: memo.overall.status,
    overall_line: memo.overall.line,
    comparable_count: memo.comparable_cases.length,
    approvals_count: memo.approvals.length,
    blockers_count: memo.approvals.filter((r) => r.status === "potential_blocker" || r.status === "not_permitted").length,
  };
}

export const MEMO_RECORD_FULL: MemoRecord = {
  id: "memo_fixture_full",
  user_id: "user_fixture",
  address: MEMO_FIXTURE_FULL.address,
  lat: SUBJECT.lat,
  lng: SUBJECT.lng,
  description: "40-seat wine bar, small kitchen, open until 1am, occasional live music",
  profile: null,
  status: "ready",
  access: "full",
  teaser: teaserOf(MEMO_FIXTURE_FULL),
  memo: MEMO_FIXTURE_FULL,
  legacy_format: false,
  clarification: null,
  batch_id: null,
  created_at: "2026-11-10T11:14:02Z",
  updated_at: "2026-11-10T11:21:23Z",
  unlocked_at: "2026-11-10T11:25:00Z",
  error: null,
};

export const MEMO_RECORD_TEASER: MemoRecord = {
  ...MEMO_RECORD_FULL,
  id: "memo_fixture_teaser",
  access: "teaser",
  memo: null,
  unlocked_at: null,
};

/** Memos the API can run again with answers (an answer round, owner decision of 2026-11-16), with one answer given. */
export const MEMO_RECORD_FULL_ANSWERABLE: MemoRecord = {
  ...MEMO_RECORD_FULL,
  intake: { floor_area_sqft: 1400 },
  answers_round: 0,
  answers_rounds_left: 5,
  answers_running: false,
  answers_available: true,
  answered_at: null,
};
export const MEMO_RECORD_TEASER_ANSWERABLE: MemoRecord = { ...MEMO_RECORD_FULL_ANSWERABLE, id: "memo_fixture_teaser", access: "teaser", memo: null, unlocked_at: null };
/** A memo made before its intake result was kept: answering it makes a new memo, as before. */
export const MEMO_RECORD_FULL_NOT_ANSWERABLE: MemoRecord = { ...MEMO_RECORD_FULL_ANSWERABLE, answers_available: false };

/**
 * Not something the API sends (it nulls `memo` unless access is full): a teaser record with the memo still
 * attached, to check that the page shows nothing from it.
 */
export const MEMO_RECORD_TEASER_WITH_MEMO: MemoRecord = { ...MEMO_RECORD_TEASER, id: "memo_fixture_teaser_with_memo", memo: MEMO_FIXTURE_FULL };

/**
 * The same memo with a base rate large enough for a percentage (N = 12, so the API sets `rate_shown`), and three
 * undated rows among the records left out. The counts are made up, so no decision is listed under them. Nothing
 * else changes: the statuses are set by rule.
 */
export const MEMO_FIXTURE_RATE: Memo = withCitations({
  ...MEMO_BASE,
  base_rate: {
    ...BASE_RATE,
    approved: 6,
    approved_with_conditions: 3,
    denied: 2,
    withdrawn: 1,
    total: 12,
    window_years: 5,
    scope: "N = 12 dated decisions within 1,000 ft, last 5 years" + leftOut(74, 321, 3),
    rate_shown: true,
    approval_rate_pct: 75,
    excluded_undated: 3,
    counted: [],
  },
});

export const MEMO_RECORD_FULL_RATE: MemoRecord = { ...MEMO_RECORD_FULL, id: "memo_fixture_full_rate", memo: MEMO_FIXTURE_RATE };

/**
 * The same report without anything rule table v2 added: no triggers, change-of-use answers or rules date on the
 * pathway, no status note, referral steps or missing inputs on a row, and no records-limits line. A report
 * stored before rule table v2 has none of them, and the page must still print its rule lines as they are.
 */
function beforeRuleTableV2(memo: Memo): Memo {
  const without = <T extends object, K extends keyof T>(value: T, keys: readonly K[]): Omit<T, K> => {
    const copy = { ...value };
    for (const k of keys) delete copy[k];
    return copy;
  };
  return {
    ...without(memo, ["records_limits", "headline_findings"]),
    pathway: without(memo.pathway, ["rules_date", "triggers", "changes"]),
    approvals: memo.approvals.map((row) => without(row, ["status_note", "referral_steps", "missing_inputs"]) as MemoApprovalRow),
  };
}
export const MEMO_RECORD_FULL_BEFORE_V2: MemoRecord = { ...MEMO_RECORD_FULL, id: "memo_fixture_full_before_v2", memo: beforeRuleTableV2(MEMO_FIXTURE_FULL) };

/**
 * The same report generated two days after the date whose rules it applies, as a backtest report is. The rules
 * date is the generated file's own; only the day of generation is moved; the page prints "Rules applied as of" as it does for every v2 report.
 */
const LATER_GENERATED_AT = "2026-11-12T09:30:00Z";
export const MEMO_RECORD_FULL_RULES_DATE: MemoRecord = {
  ...MEMO_RECORD_FULL,
  id: "memo_fixture_full_rules_date",
  memo: { ...MEMO_FIXTURE_FULL, generated_at: LATER_GENERATED_AT },
  created_at: LATER_GENERATED_AT,
  updated_at: LATER_GENERATED_AT,
  unlocked_at: LATER_GENERATED_AT,
};

// Fourteen made-up records at the same parcel (upper floors and other tenants included), all newer than mid-2015.
// They only fill the long list; none of them is a real record.
const PARCEL_ADDRESS = "995 VALENCIA ST 94110";
const extra = (recordId: string, kind: RecordKind, permitType: string, description: string, filed: string, decided: string | null, outcome: string, status: string) =>
  planningRecord(recordId, kind, permitType, description, PARCEL_ADDRESS, filed, decided, outcome, status);
const SITE_ENTRIES_MORE: SiteHistoryEntry[] = [
  extra("2025-004471PRL", "building_work", PRL, "Replace the storefront glazing and entry door in kind at the ground floor.", "2025-04-02", "2025-04-09", ...APPROVED),
  extra("2024-010236PRL", "building_work", PRL, "Install one non-illuminated wall sign for a ground-floor tenant.", "2024-10-21", "2024-10-30", ...APPROVED),
  extra("2024-002958PRL", "building_work", PRL, "Reroof and replace two rooftop mechanical units; not visible from the street.", "2024-03-05", "2024-03-19", ...APPROVED),
  extra("2023-001644PRL", "building_work", PRL, "Seismic strengthening of the ground floor under the soft-story program.", "2023-02-06", "2023-03-14", ...APPROVED),
  extra("2022-008075PRL", "building_work", PRL, "Tenant improvement at the second-floor offices: new partitions and ceiling.", "2022-08-09", "2022-08-23", ...APPROVED),
  extra("2022-003312PRV", "other", "Project Review Meeting", "Project review meeting on adding two dwelling units at the rear of the lot.", "2022-03-28", null, "unknown", "Closed"),
  extra("2020-007719PRL", "building_work", PRL, "Install an accessible entry ramp and widen the storefront door.", "2020-07-13", "2020-07-27", ...APPROVED),
  extra("2019-016540PRL", "building_work", PRL, "Replace the awning fabric on the existing frame at the Valencia Street frontage.", "2019-11-18", "2019-11-25", ...APPROVED),
  extra("2019-002207MIS", "agency_referral", MIS, "Entertainment Commission referral for a one-time outdoor event with amplified sound on the Valencia Street frontage.", "2019-02-11", "2019-02-26", ...APPROVED),
  extra("2018-012093PRL", "building_work", PRL, "Upgrade the electrical service and add a rooftop conduit run.", "2018-09-04", "2018-09-17", ...APPROVED),
  extra("2018-004866DRP", "other", "Discretionary Review - Public Initiated", "Public request for discretionary review of a rear addition at the upper floor.", "2018-04-02", "2018-08-09", "withdrawn", "Closed - Withdrawn"),
  extra("2017-009318PRL", "building_work", PRL, "Repair fire damage at the second floor: replace drywall and windows in kind.", "2017-07-17", "2017-08-01", ...APPROVED),
  extra("2017-001275VAR", "use_decision", "Variance", "Variance from the rear yard requirement for a second-floor deck.", "2017-01-30", "2017-06-28", ...APPROVED),
  extra("2016-013684PRL", "building_work", PRL, "Install a Type I kitchen exhaust hood and extend the rooftop grease exhaust duct for the ground-floor kitchen.", "2016-10-11", "2016-10-24", ...APPROVED),
];

/** Newest first by the decision date, else the filing date (the order the API sends). */
function newestFirst(entries: SiteHistoryEntry[]): SiteHistoryEntry[] {
  const when = (e: SiteHistoryEntry) => e.decided_at ?? e.filed_at ?? "";
  return entries.slice().sort((a, b) => when(b).localeCompare(when(a)));
}

/**
 * 37 records at the site, of which the API lists the newest 20 (SITE_HISTORY_LIMIT): the 14 made-up records and
 * the 6 newest real ones. `by_kind` counts all 37: the 20 listed here, the 3 older real referrals, and 14 more
 * that are not listed (12 building work and 2 other records).
 */
export const MEMO_FIXTURE_HISTORY_LONG: Memo = withCitations({
  ...MEMO_BASE,
  site_history: {
    ...SITE_HISTORY,
    total: 37,
    by_kind: { building_work: 22, agency_referral: 6, other: 4, use_decision: 3, licence: 2 },
    entries: newestFirst([...SITE_ENTRIES, ...SITE_ENTRIES_MORE]).slice(0, 20),
  },
});

/**
 * The memo as the rules write it when the records at the site do not show what the space is used as now (no
 * active on-sale licence at the address): the change of use is "not established", the building row is
 * Insufficient information and names what is missing, and the rules ask what the space was last used as. Every
 * rule-set field and fact is the rules' own for that case (RULES_NO_LICENCE).
 */
function withoutExistingUse(memo: Memo, site_history: SiteHistory): Memo {
  return withCitations(fromRules({ ...memo, site_history }, RULES_NO_LICENCE));
}

/** No record at the address or parcel: an empty list, with the API's sentence on what that does and does not mean. */
export const MEMO_FIXTURE_HISTORY_EMPTY: Memo = withoutExistingUse(MEMO_BASE, { matched_by: SITE_MATCHED_BY, total: 0, by_kind: {}, entries: [], note: SITE_NOTE_EMPTY });

// A made-up Entertainment Commission permit at the address. The permit list has no dates, and this row's status
// is blank, so the record has no date, no known outcome and no status (packages/precedent, datasf_entertainment).
const SITE_ENTERTAINMENT_PERMIT: SiteHistoryEntry = {
  application_id: "datasf_entertainment:EC-0932",
  citation_id: "app:datasf_entertainment:EC-0932",
  source: "datasf_entertainment",
  source_label: "Entertainment Commission permit list (DataSF)",
  record_kind: "entertainment_permit",
  record_kind_label: KIND_LABELS.entertainment_permit,
  permit_type: "Limited Live Performance",
  description: "SAMPLE VENUE: Limited Live Performance",
  address: "995 Valencia St, San Francisco, CA",
  filed_at: null,
  decided_at: null,
  outcome: "unknown",
  status: "",
  source_url: "https://data.sf.gov/d/86e8-rfem",
  use_types: [],
  hours_close: null,
  conditions: [],
};

/**
 * The singular forms and the fall-back words: one record on file at the site, with no date, outcome or status,
 * and one labelled record left out of the base rate for not being a use decision (the scope is the API's own
 * for those counts). An entertainment permit does not show a use, so the change of use is not established.
 */
export const MEMO_FIXTURE_HISTORY_ONE: Memo = withoutExistingUse(
  { ...MEMO_BASE, base_rate: { ...BASE_RATE, scope: BASE_RATE_SCOPE + leftOut(74, 1, 0), excluded_not_use_decision: 1 } },
  { ...SITE_HISTORY, total: 1, by_kind: { entertainment_permit: 1 }, entries: [SITE_ENTERTAINMENT_PERMIT] },
);

const NOT_LABELLED = { record_kind: "not_labelled", record_kind_label: KIND_LABELS.not_labelled } as const;
const UNLABELLED_SITE_ENTRIES: SiteHistoryEntry[] = SITE_ENTRIES.map((e) => (e.source === "abc" ? e : { ...e, ...NOT_LABELLED }));

/**
 * The same report written from records that have not been through the record classifier: every Planning record
 * is "not_labelled" and nothing is left out of the base rate for not being a use decision. An Entertainment
 * Commission permit stays an entertainment permit (`record_kind` in apps/api/app/memo/analytics.py).
 */
export const MEMO_FIXTURE_UNLABELLED: Memo = withCitations({
  ...MEMO_BASE,
  base_rate: { ...BASE_RATE, scope: BASE_RATE_SCOPE + leftOut(74, 0, 0), excluded_not_use_decision: 0 },
  comparable_cases: MEMO_BASE.comparable_cases.map((c) => (c.record_kind === "entertainment_permit" ? c : { ...c, ...NOT_LABELLED })),
  site_history: { ...SITE_HISTORY, by_kind: countByKind(UNLABELLED_SITE_ENTRIES), entries: UNLABELLED_SITE_ENTRIES },
});

// ---------------------------------------------------------------------------
// A use the district does not permit: no approval path
// ---------------------------------------------------------------------------

const BANNED = RULE_SET.not_permitted;
const RULES_NOT_PERMITTED = { ...BANNED.determinations, facts: BANNED.facts, row_facts: BANNED.row_facts } as unknown as RuleSet;
const BANNED_ZONING = `zoning:${BANNED.zoning.district}`;

export const MEMO_FIXTURE_NOT_PERMITTED: Memo = withCitations(
  fromRules(
    {
      ...MEMO_BASE,
      address: BANNED.address,
      lat: BANNED.lat,
      lng: BANNED.lng,
      parcel: BANNED.parcel,
      description: BANNED.concept,
      zoning: {
        district: BANNED.zoning.district,
        name: BANNED.zoning.name,
        bar_permission: BANNED.zoning.bar_permission,
        restaurant_permission: BANNED.zoning.restaurant_permission,
        rules: BANNED.zoning.rules,
        code_section: BANNED.zoning.code_section,
        citation_id: BANNED_ZONING,
      },
      // The record sections are empty for this address: the fixture holds no record data for it.
      overlays: [],
      base_rate: {
        ...BASE_RATE,
        approved: 0,
        withdrawn: 0,
        total: 0,
        scope: "N = 0 dated decisions within 1,000 ft, last 10 years (fewer than 5 in the last 5); too few for a rate",
        excluded_grant_only: 0,
        excluded_not_use_decision: 0,
        counted: [],
      },
      comparable_cases: [],
      comparables_note: "No Planning or Entertainment Commission record within 1,000 ft matched this kind of business.",
      site_history: { matched_by: `Parcel ${BANNED.parcel} or the address ${BANNED.address.split(",")[0]}`, total: 0, by_kind: {}, entries: [], note: SITE_NOTE_EMPTY },
      citations: [
        ...(BANNED.citations as Citation[]),
        baseRateCitation(BASE_RATE), // rewritten from this memo's own base rate by `withCitations`
      ],
    },
    RULES_NOT_PERMITTED,
  ),
);

export const MEMO_RECORD_FULL_NOT_PERMITTED: MemoRecord = {
  ...MEMO_RECORD_FULL,
  id: "memo_fixture_full_not_permitted",
  address: MEMO_FIXTURE_NOT_PERMITTED.address,
  lat: BANNED.lat,
  lng: BANNED.lng,
  description: BANNED.concept,
  teaser: teaserOf(MEMO_FIXTURE_NOT_PERMITTED),
  memo: MEMO_FIXTURE_NOT_PERMITTED,
};

export const MEMO_RECORD_FULL_HISTORY_LONG: MemoRecord = { ...MEMO_RECORD_FULL, id: "memo_fixture_full_history_long", memo: MEMO_FIXTURE_HISTORY_LONG };
export const MEMO_RECORD_FULL_HISTORY_EMPTY: MemoRecord = { ...MEMO_RECORD_FULL, id: "memo_fixture_full_history_empty", teaser: teaserOf(MEMO_FIXTURE_HISTORY_EMPTY), memo: MEMO_FIXTURE_HISTORY_EMPTY };
export const MEMO_RECORD_FULL_HISTORY_ONE: MemoRecord = { ...MEMO_RECORD_FULL, id: "memo_fixture_full_history_one", teaser: teaserOf(MEMO_FIXTURE_HISTORY_ONE), memo: MEMO_FIXTURE_HISTORY_ONE };
export const MEMO_RECORD_FULL_UNLABELLED: MemoRecord = { ...MEMO_RECORD_FULL, id: "memo_fixture_full_unlabelled", teaser: teaserOf(MEMO_FIXTURE_UNLABELLED), memo: MEMO_FIXTURE_UNLABELLED };

/** A memo stored before report format 3: the API withholds its memo and teaser and sets `legacy_format`. */
export const MEMO_RECORD_LEGACY: MemoRecord = {
  ...MEMO_RECORD_FULL,
  id: "memo_fixture_legacy",
  teaser: null,
  memo: null,
  legacy_format: true,
  rerun_free: true,
  created_at: "2026-09-02T17:05:00Z",
  updated_at: "2026-09-02T17:07:40Z",
  unlocked_at: "2026-09-02T17:10:00Z",
};

/** An earlier-format memo the user unlocked whose free re-run has been used. */
export const MEMO_RECORD_LEGACY_RERUN_USED: MemoRecord = {
  ...MEMO_RECORD_LEGACY,
  id: "memo_fixture_legacy_rerun_used",
  rerun_free: false,
};

/** The free re-run of MEMO_RECORD_LEGACY, failed: the API names the earlier memo in `rerun_of`. */
export const MEMO_RECORD_FAILED_FREE_RERUN: MemoRecord = {
  ...MEMO_RECORD_FULL,
  id: "memo_fixture_failed_free_rerun",
  status: "failed",
  access: "teaser",
  teaser: null,
  memo: null,
  rerun_of: "memo_fixture_legacy",
  unlocked_at: null,
  error: null,
};

/** A failed memo that was not a free re-run. */
export const MEMO_RECORD_FAILED: MemoRecord = { ...MEMO_RECORD_FAILED_FREE_RERUN, id: "memo_fixture_failed", rerun_of: null };

/** An earlier-format memo that was never unlocked. */
export const MEMO_RECORD_LEGACY_LOCKED: MemoRecord = {
  ...MEMO_RECORD_LEGACY,
  id: "memo_fixture_legacy_locked",
  access: "teaser",
  rerun_free: false,
  unlocked_at: null,
};

export const MEMO_GEOJSON_FIXTURE: GeoJsonFeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [SUBJECT.lng, SUBJECT.lat] },
      properties: { kind: "subject", address: MEMO_FIXTURE_FULL.address, overall_status: MEMO_FIXTURE_FULL.overall.status },
    },
    ...MEMO_FIXTURE_FULL.comparable_cases.map((c) => ({
      type: "Feature" as const,
      geometry: { type: "Point", coordinates: [c.lng, c.lat] },
      properties: {
        kind: "comparable",
        application_id: c.application_id,
        permit_type: c.permit_type,
        outcome: c.outcome,
        distance_m: c.distance_m,
        decided_at: c.decided_at,
        similarity: c.similarity_score,
        source_url: c.source_url,
        address: c.address,
      },
    })),
    {
      type: "Feature",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-122.4235, 37.7625],
            [-122.4135, 37.7625],
            [-122.4135, 37.7495],
            [-122.4235, 37.7495],
            [-122.4235, 37.7625],
          ],
        ],
      },
      // Overlay features are all `kind: "overlay"`; the overlay's own kind is in `overlay_kind`.
      properties: { kind: "overlay", overlay_kind: "alcohol_sud", name: "Mission Alcoholic Beverage Special Use District", code_section: "Planning Code § 249.60" },
    },
    {
      type: "Feature",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-122.4245, 37.7605],
            [-122.4145, 37.7605],
            [-122.4145, 37.7545],
            [-122.4245, 37.7545],
            [-122.4245, 37.7605],
          ],
        ],
      },
      properties: { kind: "overlay", overlay_kind: "special_use_district", name: "Priority Equity Geographies SUD", code_section: "Planning Code § 249.97" },
    },
  ],
};

export const ME_FIXTURE_FREE: Me = {
  id: "user_fixture",
  email: "operator@example.com",
  plans_created: 1,
  free_limit: 3,
  free_plans_remaining: 2,
  entitlement: { kind: "free", plan_credits: 0, subscription_status: null, current_period_end: null },
  can_create_plan: true,
  memo_credits: 0,
  pro_status: null,
  pro_current_period_end: null,
  free_teasers_remaining: 1,
  can_create_memo: true,
  can_unlock_memo: false,
  is_admin: false,
};

export const ME_FIXTURE_CREDIT: Me = { ...ME_FIXTURE_FREE, memo_credits: 1, can_unlock_memo: true };
export const ME_FIXTURE_PRO: Me = { ...ME_FIXTURE_FREE, pro_status: "active", pro_current_period_end: "2026-11-20T00:00:00Z", free_teasers_remaining: 0, can_unlock_memo: true };

/**
 * `GET /v1/admin/overview` with every key the API sends. It is typed as a literal so that `pnpm typecheck`
 * fails if `AdminOverview` falls behind the response (as it did for `memos.legacy_format`).
 */
export const ADMIN_OVERVIEW_FIXTURE: AdminOverview = {
  ingestion: { backend: "local", counts: { applications: 14, overlays: 3, businesses: 6, feedback: 0 }, by_source: { datasf_planning: 8, datasf_entertainment: 1, abc: 5 }, last_runs: {} },
  feedback: { total: 0, by_outcome: {}, by_concept: {}, emails_sent: 0, response_rate_pct: null },
  memos: { total: 2, full: 2, teaser: 0, last_7_days: 1, by_overall_status: { potential_blocker: 1 }, legacy_format: 1 },
  users: { total: 1, pro: 0 },
};

export const MEMO_SUMMARIES_FIXTURE: MemoSummary[] = [
  {
    id: MEMO_RECORD_FULL.id,
    address: MEMO_RECORD_FULL.address,
    concept: MEMO_RECORD_FULL.description,
    status: "ready",
    access: "full",
    overall_status: MEMO_FIXTURE_FULL.overall.status, // the rules' own overall status for the example
    comparable_count: MEMO_FIXTURE_FULL.comparable_cases.length,
    legacy_format: false,
    created_at: MEMO_RECORD_FULL.created_at,
    batch_id: null,
  },
  {
    id: MEMO_RECORD_TEASER.id,
    address: "598 Haight St, San Francisco, CA 94117",
    concept: "Cocktail bar with DJ on weekends, 60 seats, open until 2am",
    status: "ready",
    access: "teaser",
    overall_status: "not_permitted",
    comparable_count: 6,
    legacy_format: false,
    created_at: "2026-10-19T02:11:00Z",
    batch_id: "batch_fixture",
  },
  {
    id: MEMO_RECORD_LEGACY.id,
    address: "1 Ferry Building, San Francisco, CA 94111",
    concept: "Daytime cafe with pastries from a commissary, beer and wine, closes 6pm",
    status: "ready",
    access: "full",
    overall_status: null,
    comparable_count: null,
    legacy_format: true,
    created_at: MEMO_RECORD_LEGACY.created_at,
    batch_id: null,
  },
];
