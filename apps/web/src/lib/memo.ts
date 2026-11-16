import type {
  ApprovalArea,
  ApprovalStatus,
  BaseRateBlock,
  ChangeOfUse,
  ComparableCase,
  Citation,
  IntakeQuestionId,
  Memo,
  MemoFact,
  MemoRecord,
  MemoSummary,
  NoticeAnswer,
  OpenQuestion,
  Pathway,
  PlanningUse,
  RecordKind,
  RuleLine,
  SiteHistory,
  SiteHistoryEntry,
  TriggerControl,
  TriggerFinding,
  UnknownNeeds,
} from "@/lib/api-types";
import { formatDate } from "@/lib/format";
import { isIntakeQuestionId } from "@/lib/intake";

// ---------------------------------------------------------------------------
// Report format 3: approval statuses (set by rule) and the evidence behind them
// ---------------------------------------------------------------------------

/** Most to least severe (same order as STATUS_SEVERITY in apps/api/app/models/memo.py). */
export const STATUS_ORDER: readonly ApprovalStatus[] = ["not_permitted", "potential_blocker", "further_review", "insufficient_information", "allowed"];

/** The order the definitions are listed in the report. */
export const STATUS_DISPLAY_ORDER: readonly ApprovalStatus[] = ["allowed", "further_review", "potential_blocker", "not_permitted", "insufficient_information"];

export const STATUS_LABELS: Record<ApprovalStatus, string> = {
  allowed: "Allowed",
  further_review: "Further review",
  potential_blocker: "Potential blocker",
  not_permitted: "Not permitted",
  insufficient_information: "Insufficient information",
};

/** Tailwind classes for the status pill, on the existing colour tokens. */
export const STATUS_CLASSES: Record<ApprovalStatus, string> = {
  allowed: "border-verified/40 bg-verified-soft text-verified",
  further_review: "border-estimated/50 bg-estimated-soft text-estimated",
  potential_blocker: "border-signal/40 bg-signal-soft text-signal",
  not_permitted: "border-dead/40 bg-dead-soft text-dead",
  insufficient_information: "border-border bg-muted text-muted-foreground",
};

/** Solid bar colours (admin chart). */
export const STATUS_BAR_CLASSES: Record<ApprovalStatus, string> = {
  allowed: "bg-verified",
  further_review: "bg-estimated",
  potential_blocker: "bg-signal",
  not_permitted: "bg-dead",
  insufficient_information: "bg-muted-foreground/60",
};

export function isApprovalStatus(v: unknown): v is ApprovalStatus {
  return typeof v === "string" && v in STATUS_LABELS;
}

/** "Could not establish" groups, in display order, by what would settle the question. */
export const NEEDS_ORDER: readonly UnknownNeeds[] = ["plans", "inspection", "applicant_history", "agency_answer"];

export const NEEDS_LABELS: Record<UnknownNeeds, string> = {
  plans: "Plans",
  inspection: "Inspection",
  applicant_history: "Applicant history",
  agency_answer: "Agency answer",
};

export function groupOpenQuestions(questions: OpenQuestion[]): { needs: UnknownNeeds; label: string; questions: OpenQuestion[] }[] {
  return NEEDS_ORDER.map((needs) => ({ needs, label: NEEDS_LABELS[needs], questions: questions.filter((q) => q.needs === needs) })).filter((g) => g.questions.length > 0);
}

/**
 * The optional intake questions that would settle what a report could not establish (`OpenQuestion.intake_question`),
 * each once, in the order the report names them. Empty on a memo stored before the API sent them.
 */
export function answerableQuestions(questions: OpenQuestion[]): IntakeQuestionId[] {
  const ids = questions.map((q) => q.intake_question).filter(isIntakeQuestionId);
  return [...new Set(ids)];
}

/**
 * The memo's own definition strings start with their label ("Allowed: the cited records…").
 * The report shows the label as a pill or badge, so the repeated prefix is dropped.
 */
export function definitionBody(label: string, definition: string | undefined): string {
  const text = (definition ?? "").trim();
  const prefix = `${label}:`;
  if (text.toLowerCase().startsWith(prefix.toLowerCase())) {
    const rest = text.slice(prefix.length).trim();
    return rest.charAt(0).toUpperCase() + rest.slice(1);
  }
  return text;
}

// ---------------------------------------------------------------------------
// The facts the rules read, each with where it came from (apps/api/app/memo/evidence.py). The headings are
// REPORT_TEXT in apps/api/app/memo/report.py, word for word (an API test checks they are the same).
// ---------------------------------------------------------------------------

/** On the earlier-format card of a memo the user unlocked, while its one free re-run is unused (`rerun_free`). */
export const LEGACY_PAID_NOTE =
  "You unlocked this memo before the report changed, so re-running it is free: the new memo opens in full, with no memo credit used and no free preview counted. This covers the first re-run of this memo.";

/** On the earlier-format card of a memo the user unlocked, once its free re-run has been used. */
export const LEGACY_RERUN_USED_NOTE =
  "You have already used the free re-run of this memo. Another re-run makes a new memo, charged like any new one.";

/** First in the report (app.memo.pathway rule 9): `REPORT_TEXT["headline_..."]` in apps/api/app/memo/report.py. */
export const HEADLINE_HEADING = "Read this first";
export const HEADLINE_HINT =
  "What changes this business's plans at this address: a public hearing it must go through, or a rule that bars it. A finding that turns on something not yet known says so, and the report names what is missing.";
export const HEADLINE_DEFINITE = "Set by rule";
export const HEADLINE_CONTINGENT = "Depends on an answer not given";

// ---------------------------------------------------------------------------
// Answer rounds (owner decision of 2026-11-16; apps/api/app/memo/answers.py): the same memo run again with more
// intake answers, free, up to five times. The API's own messages (a refused round, a round that did not finish)
// are shown as it sends them.
// ---------------------------------------------------------------------------
export const ANSWER_ROUND_LIMIT = 5;
export const ANSWERS_BUTTON = "Answer and run again";
export const ANSWERS_SUBMIT = "Run this memo again with these answers";
export const ANSWERS_CANCEL = "Cancel";
export const ANSWERS_FORM_TITLE = "Answer and run again, free, on this memo";
export const ANSWERS_FORM_NOTE =
  "The address and the description stay as they are. The answers you gave before stay unless you change them. No memo credit is used and no free preview is counted, and the memo stays as it is unlocked or not.";
export const ANSWERS_UNCHANGED = "Change at least one answer first.";
/** Shown after the answers have been applied. */
export function answersRoundLabel(round: number): string {
  return `Updated with your answers (round ${round})`;
}
export function answersRoundsLeftLine(left: number): string {
  return left === 1 ? "1 round of answers left on this memo." : `${left} rounds of answers left on this memo.`;
}
export function answersRunningLine(round: number): string {
  return `Applying your answers (round ${round}). The report below is the one from before them; the page refreshes itself.`;
}
/** A memo the API cannot answer with a round: the old flow, a new memo, charged like any new one. */
export const ANSWERS_NEW_MEMO_NOTE =
  "This memo was made before answers could be added to it, so answering makes a new memo, charged like any new one.";
export const ANSWERS_LIMIT_NOTE = `This memo has been run again with answers ${ANSWER_ROUND_LIMIT} times, the most one memo allows. Answering again makes a new memo, charged like any new one.`;
export const EARLIER_VERSIONS_HEADING = "Earlier versions";
export const EARLIER_VERSIONS_HINT = "Each version an answer round replaced, with the answers it was run with.";
/** The label of the version an answer round replaced (`MemoRevision.round` is the round that replaced it). */
export function earlierVersionLabel(replacedByRound: number): string {
  return replacedByRound === 1 ? "The report the memo was made with" : `After round ${replacedByRound - 1}`;
}
export const NO_ANSWERS_GIVEN = "No answers given.";

export const FACTS_HEADING = "What the rules read";
export const FACTS_HINT =
  "Every fact the rules read about the business, and where each came from. What your words do not state is not known, and the report does not assume it.";
export const FACTS_READ_HEADING = "Facts the rules read";
export const COUNTED_HEADING = "The decisions counted";
/** What a fact shows when nothing gave it. */
export const NOT_KNOWN = "Not known";

export function factValueText(f: Pick<MemoFact, "value">): string {
  return f.value ?? NOT_KNOWN;
}

/** The facts the rules read that are known, then the ones that are not. */
export function splitFacts(facts: MemoFact[] | null | undefined): { known: MemoFact[]; unknown: MemoFact[] } {
  const all = facts ?? [];
  return { known: all.filter((f) => f.value !== null), unknown: all.filter((f) => f.value === null) };
}

// ---------------------------------------------------------------------------
// Pathway: the zoning answer the API looks up by rule (apps/api/app/memo/pathway.py)
// ---------------------------------------------------------------------------

/**
 * PLANNING_USE_LABELS in apps/api/app/models/memo.py, plus the Planning Code § 102 name the rules use for
 * Nighttime Entertainment (USE_LABELS in apps/api/app/memo/pathway.py). The API sends a label for the proposed
 * use, not for the existing one.
 */
export const PLANNING_USE_LABELS: Record<PlanningUse, string> = {
  bar: "Bar",
  restaurant: "Restaurant",
  limited_restaurant: "Limited Restaurant",
  nighttime_entertainment: "Nighttime Entertainment",
  not_covered: "A use the rule table does not cover",
};

/** The API's label with its first letter upper-cased, as the PDF prints it (pathway_rows in apps/api/app/services/memo_pdf.py). */
export function sentenceCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * The pathway block's subtitle: PATHWAY_HINT in apps/api/app/services/memo_pdf.py, word for word (an API test
 * checks the two are the same).
 */
export const PATHWAY_HINT =
  "Looked up by rule from the zoning district and its special use districts, and from what the description and the records at the address give: the use, its size and hours, whether it is part of a chain, the business already there and its licences, any outdoor area and earlier approvals.";

/** What the pathway block prints when no zoning district is on file: NO_DISTRICT in apps/api/app/services/memo_pdf.py. */
export const NO_DISTRICT = "No zoning district on file";

/** The use the records show at the address now, or that they do not show one. */
export function existingUseLabel(existing: Pathway["existing_use"] | undefined): string {
  if (!existing) return "Not shown by the records";
  return PLANNING_USE_LABELS[existing] ?? String(existing).replace(/_/g, " ");
}

/** Tailwind classes for the control on a new use, on the same colour tokens as the status pill. */
export const USE_PERMISSION_CLASSES: Record<Pathway["permission"], string> = {
  principal: "border-verified/40 bg-verified-soft text-verified",
  conditional: "border-estimated/50 bg-estimated-soft text-estimated",
  not_permitted: "border-dead/40 bg-dead-soft text-dead",
  not_covered: "border-border bg-muted text-muted-foreground",
};

// ---------------------------------------------------------------------------
// Rule table v2: the status note, the inputs not given, referral steps, triggers, the three change-of-use
// answers and the rules date. Every sentence comes from the API; the fixed words the page adds are the
// constants in this block and nowhere else.
// ---------------------------------------------------------------------------

/** Heading over a row's `missing_inputs`. The inputs under it are the API's own phrases, printed as sent. */
export const MISSING_INPUTS_HEADING = "Not given";

/** Heading and the one line over a row's `referral_steps`. A referral step never sets or changes a status. */
export const REFERRAL_STEPS_HEADING = "Steps inside this approval";
export const REFERRAL_STEPS_NOTE =
  "These are review steps inside the approval, where one agency sends the application to another. They are not separate approvals.";

/**
 * A row's status with its fixed qualifier, as it reads: "Further review: Code and Planning practice differ".
 * The note is set by rule and never changes the status. Null when the row has no note.
 */
export function statusNoteLine(status: ApprovalStatus, note: string | null | undefined): string | null {
  const text = (note ?? "").trim();
  if (!text) return null;
  return `${STATUS_LABELS[status] ?? status}: ${text}`;
}

/** REPORT_TEXT["rules_date_label"] in apps/api/app/memo/report.py. */
export const RULES_DATE_LABEL = "Rules applied as of";

/**
 * "Rules applied as of Nov 3, 2025", printed whenever the pathway carries a rules date, as the PDF and the text
 * report print it (rules_date_line in apps/api/app/memo/report.py). Null for a report made before rule table v2.
 * The rules date is not compared with `generated_at`: the two are read on different clocks.
 */
export function rulesDateLine(rulesDate: string | null | undefined): string | null {
  const day = (rulesDate ?? "").slice(0, 10);
  if (!day) return null;
  return `${RULES_DATE_LABEL} ${formatDate(day)}`;
}

/**
 * What one trigger asks for. Each trigger is one reason the code can require a hearing, evaluated on its own
 * (TriggerControl in apps/api/app/models/memo.py): "principal" means this trigger asks for nothing, which is
 * not a statement about the other triggers or about a requirement the trigger's own lines state.
 */
export const TRIGGER_CONTROL_LABELS: Record<TriggerControl, string> = {
  principal: "Asks for nothing",
  conditional: "Conditional use",
  not_permitted: "Not permitted",
  not_decided: "Not decided",
  does_not_apply: "Does not apply",
  code_and_practice_differ: "Code and Planning practice differ",
};

/**
 * The colour tokens of the status a trigger leads to: amber where it leads to Further review, red for Not
 * permitted, grey where it is not decided. A trigger that asks for nothing is plain, not green: its lines can
 * still state a requirement (a licence that must be transferred from inside the district).
 */
export const TRIGGER_CONTROL_CLASSES: Record<TriggerControl, string> = {
  principal: "border-border bg-card text-foreground",
  conditional: "border-estimated/50 bg-estimated-soft text-estimated",
  not_permitted: "border-dead/40 bg-dead-soft text-dead",
  not_decided: "border-border bg-muted text-muted-foreground",
  does_not_apply: "border-border bg-muted text-muted-foreground",
  code_and_practice_differ: "border-estimated/50 bg-estimated-soft text-estimated",
};

/** The triggers the zoning row lists: every trigger, with its control, in the API's order (as the PDF lists them). */
export function shownTriggers(pathway: Pick<Pathway, "triggers"> | null | undefined): TriggerFinding[] {
  return pathway?.triggers ?? [];
}

/** Change of use is three separate questions (ChangeAnswers in the API), in this order. */
export const CHANGE_QUESTIONS = ["planning_use", "building_occupancy", "neighbourhood_notice"] as const;
export type ChangeQuestion = (typeof CHANGE_QUESTIONS)[number];

export const CHANGE_QUESTION_LABELS: Record<ChangeQuestion, string> = {
  planning_use: "Planning Code change of use",
  building_occupancy: "Building Code change of occupancy",
  neighbourhood_notice: "Neighbourhood notification",
};

export const CHANGE_ANSWER_LABELS: Record<ChangeOfUse | NoticeAnswer, string> = {
  yes: "Yes",
  no: "No",
  required: "Required",
  not_required: "Not required",
  not_established: "Not established",
};

const CHANGE_ANSWER_CLASS = "border-ink/20 bg-paper-deep text-ink";
const CHANGE_NOT_ESTABLISHED_CLASS = "border-border bg-muted text-muted-foreground";

/**
 * Rule lines that belong together under one name and one answer: the lines of a trigger (zoning row) or of a
 * change-of-use answer (building row). `testId` names the block on the page.
 */
export interface RuleGroup {
  testId: "trigger" | "change-answer";
  key: string;        // the trigger's rule id ("T1") or the change question ("planning_use")
  label: string;
  value: string;      // the control or the answer as the API sends it
  valueLabel: string;
  valueClass: string;
  lines: RuleLine[];
}

export function triggerGroups(pathway: Pick<Pathway, "triggers"> | null | undefined): RuleGroup[] {
  return shownTriggers(pathway).map((t) => ({
    testId: "trigger",
    key: t.rule_id,
    label: t.label,
    value: t.control,
    valueLabel: TRIGGER_CONTROL_LABELS[t.control] ?? String(t.control).replace(/_/g, " "),
    valueClass: TRIGGER_CONTROL_CLASSES[t.control] ?? TRIGGER_CONTROL_CLASSES.not_decided,
    lines: t.lines ?? [],
  }));
}

export function changeGroups(pathway: Pick<Pathway, "changes"> | null | undefined): RuleGroup[] {
  const c = pathway?.changes;
  if (!c) return [];
  return CHANGE_QUESTIONS.map((q) => {
    const value = c[q];
    return {
      testId: "change-answer",
      key: q,
      label: CHANGE_QUESTION_LABELS[q],
      value,
      valueLabel: CHANGE_ANSWER_LABELS[value] ?? String(value).replace(/_/g, " "),
      valueClass: value === "not_established" ? CHANGE_NOT_ESTABLISHED_CLASS : CHANGE_ANSWER_CLASS,
      lines: c[`${q}_lines`] ?? [],
    };
  });
}

/** The groups one row shows: the triggers under the zoning row, the three change answers under the building row. */
export function rowRuleGroups(area: ApprovalArea, pathway: Pathway | null | undefined): RuleGroup[] {
  if (area === "zoning_use") return triggerGroups(pathway);
  if (area === "building_change_of_use") return changeGroups(pathway);
  return [];
}

export type RuleItem = { group: null; line: RuleLine } | { group: RuleGroup; line: null };

/**
 * A row's rule lines in the API's order, with the lines of each group set under the group's name and answer
 * instead of being printed a second time. A basis line belongs to a group when the group has a line with the
 * same rule id and the same text; the group is printed once, where its first line stands, with all of its lines.
 * A group none of whose lines is in the basis (the neighbourhood notification answer) is printed after the last
 * group that was placed; when none was placed, the groups go before the row's final line, which states the
 * status. No basis line is dropped. With no groups (a report made before rule table v2) the lines stay as they are.
 */
export function groupRuleLines(basis: RuleLine[], groups: RuleGroup[]): RuleItem[] {
  const same = (a: RuleLine, b: RuleLine) => a.rule_id === b.rule_id && a.text === b.text;
  const out: RuleItem[] = [];
  const placed = new Set<string>();
  let after = -1;
  for (const line of basis) {
    const group = groups.find((g) => g.lines.some((l) => same(l, line)));
    if (!group) {
      out.push({ group: null, line });
    } else if (!placed.has(group.key)) {
      placed.add(group.key);
      out.push({ group, line: null });
      after = out.length - 1;
    }
  }
  const rest = groups.filter((g) => !placed.has(g.key)).map((group): RuleItem => ({ group, line: null }));
  if (rest.length > 0) out.splice(after >= 0 ? after + 1 : Math.max(0, out.length - 1), 0, ...rest);
  // The groups keep the API's order (a trigger that does not apply has no line in the row, and is listed in its
  // place among the others): the slots the groups take are filled in the order of `groups`.
  const slots = out.flatMap((item, i) => (item.group ? [i] : []));
  const ordered = groups.filter((g) => out.some((item) => item.group?.key === g.key));
  slots.forEach((slot, i) => {
    out[slot] = { group: ordered[i], line: null };
  });
  return out;
}

/** The approval rate is displayed only when the API says the sample is large enough. */
export function showsApprovalRate(b: BaseRateBlock): b is BaseRateBlock & { approval_rate_pct: number } {
  return b.rate_shown === true && typeof b.approval_rate_pct === "number";
}

/**
 * Memos stored before report format 3 come back with `legacy_format: true` and no memo or teaser.
 * The shape checks keep the page from crashing if an older API build answers with an earlier format.
 */
export function isLegacyRecord(record: Pick<MemoRecord, "legacy_format" | "memo" | "teaser">): boolean {
  if (record.legacy_format === true) return true;
  const memo = record.memo as { format_version?: unknown } | null;
  if (memo && memo.format_version !== 3) return true;
  const teaser = record.teaser as { overall_status?: unknown } | null;
  if (teaser && !isApprovalStatus(teaser.overall_status)) return true;
  return false;
}

export function isLegacySummary(m: Pick<MemoSummary, "legacy_format">): boolean {
  return m.legacy_format === true;
}

// ---------------------------------------------------------------------------
// Days from filing, always for one outcome: TIMING_GROUPS and the timing keys of REPORT_TEXT in
// apps/api/app/memo/report.py, word for word (an API test checks every string below appears there).
// ---------------------------------------------------------------------------

export const TIMING_COLUMN = "Days from filing";
export const TIMING_HEADING = "Days from filing, by outcome";
export const TIMING_HINT =
  "From the comparable cases listed. Each figure is for one outcome; cases with different outcomes are never combined, and no average is given.";
export const TIMING_PENDING_NOTE = "age so far as of {date}, not a time to a decision";
export const TIMING_UNDATED = "{n} of the comparable cases {have} no figure: a date is missing.";
export const TIMING_NONE = "No comparable case has both a filing date and a decision date.";
export interface TimingGroup {
  key: string;
  label: string;
  perCase: string; // "{days} days to approval"
  measured: string; // "from filing to approval"
}

export const TIMING_GROUPS: readonly TimingGroup[] = [
  { key: "approved", label: "Approved", perCase: "{days} days to approval", measured: "from filing to approval" },
  { key: "denied", label: "Denied", perCase: "{days} days to denial", measured: "from filing to denial" },
  { key: "withdrawn", label: "Withdrawn", perCase: "{days} days to withdrawal", measured: "from filing to withdrawal" },
  { key: "cancelled", label: "Cancelled", perCase: "{days} days to cancellation", measured: "from filing to cancellation" },
  {
    key: "not_recorded",
    label: "Outcome not recorded",
    perCase: "{days} days to closing, outcome not recorded",
    measured: "from filing to the day the record was closed",
  },
  { key: "pending", label: "Still pending", perCase: "pending {days} days so far", measured: "since filing" },
];

const TIMING_GROUP_OF: Record<string, string> = {
  approved: "approved",
  approved_with_conditions: "approved",
  denied: "denied",
  withdrawn: "withdrawn",
  cancelled: "cancelled",
  pending: "pending",
};

function isoDay(text: string | null | undefined): string | null {
  const day = (text ?? "").slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : null;
}

function daysBetween(from: string | null, to: string | null): number | null {
  if (!from || !to) return null;
  const days = Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
  return days >= 0 ? days : null;
}

/** case_time in report.py: which outcome a comparable's figure is for, and the figure (pending: aged to `asOf`). */
export function caseTime(c: Pick<ComparableCase, "outcome" | "filed_at" | "decided_at">, asOf: string | null | undefined): { group: string; days: number | null } {
  const group = TIMING_GROUP_OF[c.outcome] ?? "not_recorded";
  const end = group === "pending" ? isoDay(asOf) : isoDay(c.decided_at);
  return { group, days: daysBetween(isoDay(c.filed_at), end) };
}

/** timing_cell in report.py: "120 days to approval", "pending 410 days so far"; a dash when a date is missing. */
export function timingCell(c: Pick<ComparableCase, "outcome" | "filed_at" | "decided_at">, asOf: string | null | undefined): string {
  const t = caseTime(c, asOf);
  if (t.days === null) return "–";
  const group = TIMING_GROUPS.find((g) => g.key === t.group) ?? TIMING_GROUPS[4];
  return group.perCase.replace("{days}", t.days.toLocaleString("en-US"));
}

/** decision_time_lines in report.py: one line per outcome group (lowest and highest, never an average). */
export function decisionTimeLines(cases: Pick<ComparableCase, "outcome" | "filed_at" | "decided_at">[], asOf: string | null | undefined): string[] {
  const byGroup = new Map<string, number[]>();
  let undated = 0;
  for (const c of cases) {
    const t = caseTime(c, asOf);
    if (t.days === null) undated += 1;
    else byGroup.set(t.group, [...(byGroup.get(t.group) ?? []), t.days]);
  }
  const lines: string[] = [];
  for (const g of TIMING_GROUPS) {
    const found = byGroup.get(g.key);
    if (!found) continue;
    const low = Math.min(...found);
    const high = Math.max(...found);
    const range = low === high ? `${low.toLocaleString("en-US")} days` : `${low.toLocaleString("en-US")} to ${high.toLocaleString("en-US")} days`;
    const noun = found.length === 1 ? "case" : "cases";
    let line = `${g.label}: ${found.length} ${noun}, ${range} ${g.measured}`;
    const day = isoDay(asOf);
    if (g.key === "pending" && day) line += ` (${TIMING_PENDING_NOTE.replace("{date}", day)})`;
    lines.push(`${line}.`);
  }
  if (lines.length === 0 && cases.length > 0) lines.push(TIMING_NONE);
  else if (undated) lines.push(TIMING_UNDATED.replace("{n}", String(undated)).replace("{have}", undated === 1 ? "has" : "have"));
  return lines;
}

// ---------------------------------------------------------------------------
// Case outcomes (free-text in the records; normalised for colour + badges)
// ---------------------------------------------------------------------------

export type OutcomeBucket = "approved" | "conditions" | "denied" | "withdrawn" | "cancelled" | "pending" | "other";

export function outcomeBucket(outcome: string | null | undefined): OutcomeBucket {
  const o = (outcome ?? "").toLowerCase();
  if (!o) return "other";
  if (o.includes("condition")) return "conditions";
  if (o.includes("cancel")) return "cancelled";
  if (o.includes("withdr")) return "withdrawn";
  if (o.includes("den") || o.includes("disapprov") || o.includes("reject")) return "denied";
  if (o.includes("approv") || o.includes("grant") || o.includes("issued")) return "approved";
  if (o.includes("pend") || o.includes("open") || o.includes("review") || o.includes("filed") || o.includes("under")) return "pending";
  return "other";
}

export const OUTCOME_CLASSES: Record<OutcomeBucket, string> = {
  approved: "border-verified/40 bg-verified-soft text-verified",
  conditions: "border-estimated/50 bg-estimated-soft text-estimated",
  denied: "border-dead/40 bg-dead-soft text-dead",
  withdrawn: "border-border bg-muted text-muted-foreground",
  cancelled: "border-border bg-muted text-muted-foreground",
  pending: "border-ink/20 bg-paper-deep text-ink",
  other: "border-border bg-card text-foreground",
};

export const OUTCOME_HEX: Record<OutcomeBucket, string> = {
  approved: "#1a7f4b",
  conditions: "#b7791f",
  denied: "#b42318",
  withdrawn: "#8a8f99",
  cancelled: "#8a8f99",
  pending: "#141b2d",
  other: "#5c6270",
};

export const OUTCOME_LABELS: Record<OutcomeBucket, string> = {
  approved: "Approved",
  conditions: "Approved w/ conditions",
  denied: "Denied",
  withdrawn: "Withdrawn",
  cancelled: "Cancelled",
  pending: "Pending",
  other: "Other",
};

export function outcomeLabel(outcome: string | null | undefined): string {
  if (!outcome) return "Unknown";
  return outcome
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\w/, (c) => c.toUpperCase());
}

// ---------------------------------------------------------------------------
// Record kinds and the site history (records on file at the report's own address or parcel)
// ---------------------------------------------------------------------------

/** Display order for the counts by kind. Labels are RECORD_KIND_LABELS in apps/api/app/models/memo.py. */
export const RECORD_KIND_ORDER: readonly RecordKind[] = ["use_decision", "agency_referral", "building_work", "licence", "entertainment_permit", "other", "not_labelled"];

export const RECORD_KIND_LABELS: Record<RecordKind, string> = {
  use_decision: "Use decision",
  agency_referral: "Agency referral",
  building_work: "Building work",
  other: "Other record",
  licence: "ABC licence",
  entertainment_permit: "Entertainment permit",
  not_labelled: "Not labelled",
};

/**
 * Neutral badge styles, no status colours: use decisions and referrals (the records that count toward a pathway)
 * are filled, building work is a dashed outline, everything else is plain.
 */
export const RECORD_KIND_CLASSES: Record<RecordKind, string> = {
  use_decision: "border-ink/25 bg-paper-deep text-ink",
  agency_referral: "border-ink/25 bg-paper-deep text-ink",
  building_work: "border-dashed border-ink/40 bg-transparent text-foreground/80",
  licence: "border-border bg-card text-foreground",
  entertainment_permit: "border-border bg-card text-foreground",
  other: "border-border bg-muted text-muted-foreground",
  not_labelled: "border-border bg-muted text-muted-foreground",
};

export function isRecordKind(v: unknown): v is RecordKind {
  return typeof v === "string" && v in RECORD_KIND_LABELS;
}

/** The label the API sent, else the built-in one, else the raw kind. */
export function recordKindLabel(kind: string, label?: string | null): string {
  return label?.trim() || (isRecordKind(kind) ? RECORD_KIND_LABELS[kind] : kind.replace(/_/g, " "));
}

/**
 * The comparables table names the kind only for the two kinds the classifier assigns to a pathway record: a use
 * decision or an agency referral. Records without labels show no kind, and neither do Entertainment Commission
 * permits, which the API marks as such whether or not the store has labels; so a report written from unlabelled
 * records looks as it did before the labels existed.
 */
export function showsRecordKind(kind: string | null | undefined): boolean {
  return kind === "use_decision" || kind === "agency_referral";
}

/**
 * The base-rate scope without the API's "; left out: 6 grant-only, 31 not use decisions, 3 undated" tail
 * (`left_out_clause` in apps/api/app/memo/analytics.py). The page lists the same counts on its own
 * "Not counted" line, so the heading leaves them out.
 */
export function baseRateScopeText(scope: string): string {
  return scope.split("; left out:")[0];
}

/** "37 records on file at this address or parcel", or "No records on file at this address or parcel". */
export function siteHistoryCountLine(total: number): string {
  if (total <= 0) return "No records on file at this address or parcel";
  return `${total.toLocaleString("en-US")} ${total === 1 ? "record" : "records"} on file at this address or parcel`;
}

/** "Showing 20 of 37" when the list is cut short (the API's note says the order); null when every record is listed. */
export function siteHistoryShownLine(h: Pick<SiteHistory, "total" | "entries">): string | null {
  if (h.entries.length === 0 || h.total <= h.entries.length) return null;
  return `Showing ${h.entries.length} of ${h.total.toLocaleString("en-US")}`;
}

/** The date shown for a site record: decided, else filed, else none. */
export function siteHistoryDate(e: Pick<SiteHistoryEntry, "filed_at" | "decided_at">): { date: string; which: "decided" | "filed" } | null {
  if (e.decided_at) return { date: e.decided_at, which: "decided" };
  if (e.filed_at) return { date: e.filed_at, which: "filed" };
  return null;
}

/** Counts by kind over every record at the site, in display order; kinds this build does not know come last. */
export function siteHistoryKindCounts(byKind: Record<string, number>): { kind: string; label: string; n: number }[] {
  const known = RECORD_KIND_ORDER.filter((k) => (byKind[k] ?? 0) > 0).map((k) => ({ kind: k as string, label: RECORD_KIND_LABELS[k], n: byKind[k] }));
  const rest = Object.keys(byKind)
    .filter((k) => !isRecordKind(k) && byKind[k] > 0)
    .sort()
    .map((k) => ({ kind: k, label: recordKindLabel(k), n: byKind[k] }));
  return [...known, ...rest];
}

/**
 * `matched_by` as the API writes it (`site_matched_by` in apps/api/app/memo/report.py): a phrase that starts with
 * a capital and has no full stop, e.g. "Parcel 3596/024 or the address 995 Valencia St". The page prints it after
 * "Matched by: " and adds the full stop.
 */
export function matchedByText(matchedBy: string | null | undefined): string {
  return (matchedBy ?? "").trim().replace(/\.$/, "");
}

// ---------------------------------------------------------------------------
// Citations: `citations: string[]` → [n] superscripts resolving to memo.citations by id
// ---------------------------------------------------------------------------

export interface CitationIndex {
  /** id → 1-based footnote number */
  numbers: Map<string, number>;
  /** ordered citations (footnote order) */
  ordered: Citation[];
}

export function buildCitationIndex(citations: Citation[]): CitationIndex {
  const numbers = new Map<string, number>();
  const ordered: Citation[] = [];
  for (const c of citations) {
    if (numbers.has(c.id)) continue;
    ordered.push(c);
    numbers.set(c.id, ordered.length);
  }
  return { numbers, ordered };
}

export const CITATION_KIND_LABELS: Record<Citation["kind"], string> = {
  application: "Application",
  overlay: "Overlay",
  zoning: "Zoning",
  license: "License",
  statistic: "Statistic",
  feedback: "Operator report",
  catalog: "Permit catalog",
};

export const CITATION_KIND_CLASSES: Record<Citation["kind"], string> = {
  application: "border-ink/20 bg-paper-deep text-ink",
  overlay: "border-signal/30 bg-signal-soft text-signal",
  zoning: "border-verified/30 bg-verified-soft text-verified",
  license: "border-estimated/40 bg-estimated-soft text-estimated",
  statistic: "border-border bg-muted text-muted-foreground",
  feedback: "border-chart-5/40 bg-card text-foreground",
  catalog: "border-border bg-card text-foreground",
};

export function footnoteId(n: number): string {
  return `cite-${n}`;
}

/** Hex fill for overlay polygons from `map.geojson`, by the overlay's kind (`properties.overlay_kind`). */
export function overlayKindHex(kind: string | null | undefined): string {
  const k = (kind ?? "").toLowerCase();
  if (k.includes("alcohol") || k.includes("liquor")) return "#e4572e";
  if (k.includes("historic")) return "#7c6f9b";
  if (k.includes("entertainment") || k.includes("night")) return "#b7791f";
  if (k.includes("residential") || k.includes("rh")) return "#1a7f4b";
  if (k.includes("transit") || k.includes("nct")) return "#1f2940";
  return "#5c6270";
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

const FEET_PER_METER = 3.28084;

export function metersToFeet(m: number): number {
  return m * FEET_PER_METER;
}

export function formatDistance(m: number): string {
  const ft = metersToFeet(m);
  if (ft < 1000) return `${Math.round(ft)} ft`;
  return `${(ft / 5280).toFixed(2)} mi`;
}

export function formatPct(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${n.toFixed(digits)}%`;
}

export function similarityPct(score: number): number {
  return Math.round(Math.max(0, Math.min(1, score)) * 100);
}

/** The applicant's own words: the report quotes them as sent and writes no summary of its own. */
export function conceptFromRecord(record: Pick<MemoRecord, "description" | "memo">): string {
  return record.memo?.description || record.description;
}

/** Overall status and line for the header card: from the full memo when present, else the teaser. */
export function overallOf(record: Pick<MemoRecord, "memo" | "teaser">): { status: ApprovalStatus; line: string } | null {
  if (record.memo?.overall) return { status: record.memo.overall.status, line: record.memo.overall.line };
  if (record.teaser) return { status: record.teaser.overall_status, line: record.teaser.overall_line };
  return null;
}

/** The overall status of a finished memo record, for analytics. */
export function overallStatusOf(record: Pick<MemoRecord, "memo" | "teaser"> | null | undefined): ApprovalStatus | null {
  return record?.teaser?.overall_status ?? record?.memo?.overall?.status ?? null;
}

/** Rows whose status is potential_blocker or not_permitted (the teaser's `blockers_count`). */
export function blockerCount(memo: Pick<Memo, "approvals">): number {
  return memo.approvals.filter((r) => r.status === "potential_blocker" || r.status === "not_permitted").length;
}

export function memoSlug(record: Pick<MemoRecord, "address">): string {
  return record.address.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "memo";
}

// ---------------------------------------------------------------------------
// Bulk CSV (header `address,description`, max 25 rows)
// ---------------------------------------------------------------------------

export const BULK_MAX_ROWS = 25;
export const BULK_CSV_HEADER = ["address", "description"] as const;

export interface ParsedCsv {
  header: string[];
  rows: { address: string; description: string; line: number }[];
  problems: string[];
}

/** Minimal RFC 4180 parser: quoted fields, escaped quotes, CRLF. Good enough for a 25-row upload preview. */
export function parseCsv(text: string): string[][] {
  const out: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else inQuotes = false;
      } else field += ch;
      continue;
    }
    if (ch === '"') inQuotes = true;
    else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      out.push(row);
      row = [];
      field = "";
    } else field += ch;
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    out.push(row);
  }
  return out.filter((r) => r.some((c) => c.trim().length > 0));
}

export function parseBulkCsv(text: string): ParsedCsv {
  const problems: string[] = [];
  const table = parseCsv(text.replace(/^﻿/, ""));
  if (table.length === 0) return { header: [], rows: [], problems: ["The file is empty."] };
  const header = table[0].map((h) => h.trim().toLowerCase());
  const ai = header.indexOf("address");
  const di = header.indexOf("description");
  if (ai === -1 || di === -1) {
    problems.push(`The first line must be the header "address,description" (found "${table[0].join(",")}").`);
    return { header, rows: [], problems };
  }
  const rows: ParsedCsv["rows"] = [];
  table.slice(1).forEach((r, idx) => {
    const line = idx + 2;
    const address = (r[ai] ?? "").trim();
    const description = (r[di] ?? "").trim();
    if (!address || !description) {
      problems.push(`Line ${line}: ${!address ? "missing address" : "missing description"} — this row will be skipped by the API.`);
    }
    rows.push({ address, description, line });
  });
  if (rows.length > BULK_MAX_ROWS) problems.push(`${rows.length} rows found; only the first ${BULK_MAX_ROWS} are accepted per upload.`);
  return { header, rows, problems };
}

export function csvEscape(v: string): string {
  return /[",\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
}

export const BULK_TEMPLATE_ROWS: { address: string; description: string }[] = [
  { address: "2500 Mission St, San Francisco, CA 94110", description: "40-seat wine bar, small kitchen, open until 1am, occasional live music" },
  { address: "1 Ferry Building, San Francisco, CA 94111", description: "Daytime cafe with pastries from a commissary, beer and wine, closes 6pm" },
  { address: "598 Haight St, San Francisco, CA 94117", description: "Cocktail bar with DJ on weekends, 60 seats, open until 2am" },
];

export function bulkTemplateCsv(): string {
  return [BULK_CSV_HEADER.join(","), ...BULK_TEMPLATE_ROWS.map((r) => `${csvEscape(r.address)},${csvEscape(r.description)}`)].join("\n") + "\n";
}
