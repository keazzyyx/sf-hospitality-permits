"""Server-rendered PDF of a Location Risk Memo (ReportLab), report format 3: the rules and the evidence.

What the rules decided is printed as the rules wrote it. First, under "Read this first", come the headline
findings (app.memo.pathway rule 9): each with its status, whether it depends on an answer not given, and the
trigger line it rests on. Then each approval row shows its status with its status
note ("Further review: Code and Planning practice differ"), then "Rules applied" (the row's rule lines, with
the code section each rests on), "Steps inside this approval" (the referral steps, said to be review steps and
not separate approvals), "Not given" (the inputs the rules name as missing), under the building row the three
change-of-use answers each on its own line, then "Facts the rules read" (each fact with where it came from).
"What the rules read" lists every fact, the ones not known included. The zoning part of "At a glance" shows the
pathway the rules looked up, the date whose rules were applied, and every trigger with its control and, where
that control is not today's, the sentence that says so. The could-not-establish section ends with the fixed line
on what public records cannot show. The comparables are the top of the fixed ranking, each with what its record
says and a link to it; the decisions the outcome counts count are listed with their links. No text here was
written by a model.

Days from filing are printed per outcome: each comparable's figure names its outcome, a pending case shows its
age so far, and the summary under the table gives one range per outcome. No figure combines outcomes.
"""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import settings
from app.memo.intake import QUESTION_BY_ID
from app.memo.report import (
    HEARINGS_SOURCE,
    REPORT_TEXT,
    base_rate_line,
    change_answer_rows,
    decision_time_lines,
    fact_origin_text,
    fact_value_text,
    iso_date,
    pathway_facts,
    site_entry_date,
    site_entry_filed_under,
    site_entry_outcome,
    site_history_count_line,
    status_label,
    timing_cell,
    trigger_differs_texts,
    trigger_headline,
    triggers_hint,
    unprinted_lines,
)
from app.models.memo import (
    PATHWAY_RECORD_KINDS,
    ComparableCase,
    Memo,
    MemoApprovalRow,
    MemoFact,
    Pathway,
    RuleLine,
)

INK = colors.HexColor("#141b2d")
MUTED = colors.HexColor("#6b7280")
LINE = colors.HexColor("#e5e7eb")
STATUS_COLOR = {
    "allowed": colors.HexColor("#15803d"),
    "further_review": colors.HexColor("#b45309"),
    "potential_blocker": colors.HexColor("#c2410c"),
    "not_permitted": colors.HexColor("#b91c1c"),
    "insufficient_information": colors.HexColor("#4b5563"),
}
NEEDS_LABEL = {
    "plans": "Needs plans",
    "inspection": "Needs an inspection",
    "applicant_history": "Needs the applicant's history",
    "agency_answer": "Needs an agency's answer",
}

# What the report says about the open questions an optional intake question answers (app.memo.intake).
ANSWERABLE_ONE = (
    "One of these is a question you can answer. Answer it where you start a report and run the report again: "
    "the rules never guess a missing input, so a row that needs one stays undecided until you give it."
)
ANSWERABLE_MANY = (
    "{n} of these are questions you can answer. Answer them where you start a report and run the report again: "
    "the rules never guess a missing input, so a row that needs one stays undecided until you give it."
)
ANSWERABLE_PREFIX = "Question to answer:"


def answerable_line(n: int) -> str:
    """The line above the open questions when the applicant can answer `n` of them."""
    return ANSWERABLE_ONE if n == 1 else ANSWERABLE_MANY.format(n=n)


# Characters the PDF's built-in font has no glyph for (they print as a black box) and their plain spelling.
_NO_GLYPH = str.maketrans(
    {"½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4", "⅕": "1/5", "⅛": "1/8", "≤": "<=", "≥": ">="}
)


# Printed under the header of every PDF, whatever the memo's format. The holdout of 2026-11-12: on 20 past cases not
# used to build the rules, the report missed a critical issue in 12. The web page shows the same sentence
# (`TESTING_NOTICE` in apps/web/src/lib/site-copy.ts); keep the two identical.
TESTING_NOTICE = (
    "In testing: checked against past cases, this report missed important issues in more than half of new cases. "
    "Use it as a starting point, not a conclusion."
)


def _esc(t: str | None) -> str:
    return (t or "").translate(_NO_GLYPH).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _refs(ids: list[str], index: dict[str, int]) -> str:
    nums = sorted({index[i] for i in ids if i in index})
    return (
        (" <super><font color='#6b7280'>[" + ",".join(str(n) for n in nums) + "]</font></super>")
        if nums
        else ""
    )


def _status(status: str, note: str | None = None) -> str:
    """The status in its colour, then the rules' status note after a colon when the row has one, as the rules
    wrote it: 'Further review: Code and Planning practice differ'."""
    color = STATUS_COLOR.get(status, MUTED).hexval()
    text = f"<font color='{color}'><b>{_esc(status_label(status))}</b></font>"
    return f"{text}: {_esc(note)}" if note else text


RULES_APPLIED_HEADING = "Rules applied"
STEPS_HEADING = REPORT_TEXT["steps_heading"]
STEPS_HINT = REPORT_TEXT["steps_hint"]
NOT_GIVEN_HEADING = REPORT_TEXT["not_given_heading"]
CHANGES_HEADING = REPORT_TEXT["changes_heading"]
TRIGGERS_HEADING = REPORT_TEXT["triggers_heading"]
RULES_DATE_LABEL = REPORT_TEXT["rules_date_label"]
TIMING_HEADING = REPORT_TEXT["timing_heading"]
TIMING_COLUMN = REPORT_TEXT["timing_column"]
PATHWAY_HEADING = "Pathway"
# The same words as the pathway block's subtitle on the web (apps/web/src/lib/memo.ts PATHWAY_HINT).
PATHWAY_HINT = (
    "Looked up by rule from the zoning district and its special use districts, and from what the description and "
    "the records at the address give: the use, its size and hours, whether it is part of a chain, the business "
    "already there and its licences, any outdoor area and earlier approvals."
)
NO_DISTRICT = "No zoning district on file"


def rule_line_markup(line: RuleLine, index: dict[str, int]) -> str:
    """One rule line as the rules wrote it, with its record references and then the code section it rests on.
    The section is left off when the sentence already names it in the same words."""
    out = f"{_esc(line.text)}{_refs(line.citations, index)}"
    if line.code_section and line.code_section not in line.text:
        out += f" <font color='#6b7280'>{_esc(line.code_section)}</font>"
    return out


def pathway_rows(pathway: Pathway) -> list[tuple[str, str]]:
    """The pathway block's rows, in order: use, district, control for a new use, existing use, change of use,
    and the date whose rules were applied (left out on a report made before rule table v2)."""
    facts = pathway_facts(pathway)

    def shown(key: str, missing: str = "") -> str:
        text = facts[key] or missing
        return text[:1].upper() + text[1:]

    rows = [
        ("Proposed use", shown("use")),
        ("Zoning district", shown("zoning_district", NO_DISTRICT)),
        ("Control on a new use", shown("new_use_here")),
        ("Existing use", shown("existing_use")),
        ("Change of use", shown("change_of_use")),
    ]
    if pathway.rules_date:
        rows.append((RULES_DATE_LABEL, pathway.rules_date))
    return rows


def trigger_markup(pathway: Pathway, index: dict[str, int]) -> list[str]:
    """The triggers block of the zoning section, one paragraph of markup per line: every trigger with its
    control (and the inputs it was not given), and under a trigger whose control on the rules date is not
    today's control, the sentence that says so. Empty on a report with no triggers."""
    out: list[str] = []
    for finding in pathway.triggers:
        out.append(f"• {_esc(trigger_headline(finding))}{_refs(_cited(finding.lines), index)}")
        out.extend(f"&nbsp;&nbsp;&nbsp;{_esc(text)}" for text in trigger_differs_texts(finding))
    return out


def _cited(lines: list[RuleLine]) -> list[str]:
    return list(dict.fromkeys(c for line in lines for c in line.citations))


def row_rule_markup(row: MemoApprovalRow, pathway: Pathway, index: dict[str, int]) -> list[tuple[str, str]]:
    """What the rules set under one row after its status, as (style, markup) pairs in print order: "Rules
    applied" and the rule lines; "Steps inside this approval", the sentence saying these are review steps and
    not separate approvals, and the referral steps; "Not given" and the missing inputs; and, under the
    building row, the three change-of-use answers each on its own line (with any rule line of an answer that
    "Rules applied" does not already print). A part with nothing in it is left out. Styles: "heading", "hint",
    "line"."""
    out: list[tuple[str, str]] = []
    if row.basis:  # set by rule; printed as the rules wrote them
        out.append(("heading", RULES_APPLIED_HEADING))
        out.extend(("line", f"• {rule_line_markup(line, index)}") for line in row.basis)
    if row.referral_steps:
        out.append(("heading", STEPS_HEADING))
        out.append(("hint", _esc(STEPS_HINT)))
        out.extend(("line", f"• {rule_line_markup(line, index)}") for line in row.referral_steps)
    if row.missing_inputs:
        out.append(("heading", NOT_GIVEN_HEADING))
        out.extend(("line", f"• {_esc(text)}") for text in row.missing_inputs)
    if row.area == "building_change_of_use":
        answers = change_answer_rows(pathway.changes)
        if answers:
            out.append(("heading", CHANGES_HEADING))
        for question, answer, lines in answers:
            out.append(("line", f"• <b>{_esc(question)}:</b> {_esc(answer)}"))
            out.extend(
                ("line", f"&nbsp;&nbsp;&nbsp;{rule_line_markup(line, index)}")
                for line in unprinted_lines(lines, row.basis)
            )
    return out


# A row block with more paragraphs than this is not kept on one page (it could not fit on one).
KEEP_TOGETHER_MAX = 30
NOT_IN_SOURCE = "–"
SITE_HISTORY_HEADING = "Site history"
NO_CONDITIONS_NOTE = "A dash under Conditions means the source does not carry conditions for that case, not that there were none."
FACTS_HEADING = REPORT_TEXT["facts_heading"]
FACTS_HINT = REPORT_TEXT["facts_hint"]
FACTS_READ_HEADING = REPORT_TEXT["facts_read_heading"]
COUNTED_HEADING = REPORT_TEXT["counted_heading"]
CONDITIONS_HEADING = "Conditions on file"
PATH_HEADING = "Approvals to file, in order"
# A table cell cannot run onto the next page, so a cell lists at most this many of a record's conditions; the
# list under the table and the record itself carry all of them.
CELL_CONDITIONS_MAX = 3


def conditions_cell(comp: ComparableCase) -> str:
    """The Conditions cell of the comparables table: how many conditions were extracted. When there are none
    and no Commission motion was read for the case, a dash: the source does not carry conditions, and a bare 0
    would read as 'approved with no conditions'."""
    if not comp.conditions and comp.source != HEARINGS_SOURCE:
        return NOT_IN_SOURCE
    return str(len(comp.conditions))


def _link(url: str | None, text: str) -> str:
    """A link to a source record, printed as its text when there is no address."""
    if not url:
        return _esc(text)
    return f"<a href='{_esc(url)}' color='#b45309'>{_esc(text)}</a>"


def fact_markup(fact: MemoFact, index: dict[str, int]) -> str:
    """'<b>Closing time:</b> 2:00 a.m. · Your description: “until 2am”' with the records a record fact cites."""
    value = _esc(fact_value_text(fact))
    if fact.value is None:
        value = f"<font color='#6b7280'>{value}</font>"
    origin = f"<font color='#6b7280'>{_esc(fact_origin_text(fact))}</font>"
    return f"<b>{_esc(fact.label)}:</b> {value} · {origin}{_refs(fact.citations, index)}"


def record_facts_markup(
    *,
    record_id: str,
    source_url: str | None,
    use_types: list[str],
    hours_close: str | None,
    conditions: list[str],
) -> str:
    """The recorded facts of one record for a table cell: its id (a link to the record), its uses, its closing
    hour and its first conditions."""
    out = [_link(source_url, record_id)]
    if use_types:
        out.append("Use: " + _esc(", ".join(u.replace("_", " ") for u in use_types)))
    if hours_close:
        out.append(f"Closes: {_esc(hours_close)}")
    if conditions:
        shown = "; ".join(conditions[:CELL_CONDITIONS_MAX])
        more = len(conditions) - CELL_CONDITIONS_MAX
        out.append(f"Conditions: {_esc(shown)}" + (f" (and {more} more)" if more > 0 else ""))
    return "<br/>".join(out)


def render_memo_pdf(memo: Memo, *, generated_for: str | None = None) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
        title=f"Location Risk Memo — {memo.address}",
        author=settings.APP_NAME,
    )
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=19, textColor=INK, alignment=0, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=INK, spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10.5, textColor=MUTED)
    cell = ParagraphStyle("cell", parent=body, fontSize=8, leading=10)
    headcell = ParagraphStyle("headcell", parent=cell, textColor=colors.white)
    index = {c.id: i + 1 for i, c in enumerate(memo.citations)}
    header = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), INK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
    )

    story: list[object] = [
        Paragraph("Location Risk Memo", h1),
        Paragraph(_esc(memo.address), ParagraphStyle("addr", parent=h2, spaceBefore=0)),
    ]
    meta = f"Generated {memo.generated_at[:10]} · Records as of {memo.data_as_of}"
    if generated_for:
        meta += f" · Prepared for {_esc(generated_for)}"
    story.append(Paragraph(meta, small))
    if memo.description:
        story.append(Paragraph(f"<b>Your description:</b> {_esc(memo.description)}", small))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<b>{_esc(TESTING_NOTICE)}</b>", body))
    story.append(Spacer(1, 8))

    # first: the findings that change the business's plans here, set by rule (app.memo.pathway rule 9)
    if memo.headline_findings:
        story.append(Paragraph(f"<b>{_esc(REPORT_TEXT['headline_heading'])}</b>", h2))
        story.append(Paragraph(_esc(REPORT_TEXT["headline_hint"]), small))
        for h in memo.headline_findings:
            how = REPORT_TEXT["headline_definite" if h.definite else "headline_contingent"]
            story.append(
                Paragraph(
                    f"{_status(h.status)} <font color='#6b7280'>({_esc(how)})</font> — <b>{_esc(h.sentence)}</b>"
                    f"{_refs(h.citations, index)}",
                    body,
                )
            )
            story.extend(Paragraph(rule_line_markup(line, index), small) for line in h.basis)
        story.append(Spacer(1, 6))

    # overall status and line, set by rule
    o = memo.overall
    story.append(Paragraph(f"Overall: {_status(o.status)} — {_esc(o.line)}{_refs(o.citations, index)}", body))

    # approvals table; then, per row: status, the rule lines that set it, the facts its rules read
    story.append(Paragraph("Approvals this concept needs", h2))
    arows = [[Paragraph(x, headcell) for x in ("Area", "Approval", "Agency", "Status")]]
    for row in memo.approvals:
        arows.append(
            [
                Paragraph(_esc(row.area_label), cell),
                Paragraph(_esc(row.approval), cell),
                Paragraph(_esc(row.agency), cell),
                Paragraph(_status(row.status, row.status_note), cell),
            ]
        )
    atbl = Table(arows, colWidths=[1.5 * inch, 2.4 * inch, 1.7 * inch, 1.3 * inch], repeatRows=1)
    atbl.setStyle(header)
    story.append(atbl)
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>{PATH_HEADING}:</b> {_esc(memo.entitlement_path)}", cell))
    story.append(Spacer(1, 6))
    for row in memo.approvals:
        block: list[object] = [
            Paragraph(f"<b>{_esc(row.area_label)}</b> · {_status(row.status, row.status_note)}", body)
        ]
        # set by rule and printed as the rules wrote it: rule lines, referral steps, missing inputs, and the
        # three change-of-use answers under the building row
        rule_parts = row_rule_markup(row, memo.pathway, index)
        for style, markup in rule_parts:
            if style == "heading":
                block.append(Paragraph(f"<b>{markup}</b>", small))
            else:
                block.append(Paragraph(markup, small if style == "hint" else cell))
        if row.facts:  # the known facts these rules read, each with where it came from
            block.append(Paragraph(f"<b>{FACTS_READ_HEADING}</b>", small))
            block.extend(Paragraph(f"• {fact_markup(f, index)}", cell) for f in row.facts)
        if rule_parts or row.facts:
            block.append(Spacer(1, 3))
        if row.history_note:
            block.append(Paragraph(f"<i>{_esc(row.history_note)}</i>", small))
        block.append(Spacer(1, 6))
        # a row with many rule lines and referral steps can be taller than a page: let it break
        story.extend(block if len(block) > KEEP_TOGETHER_MAX else [KeepTogether(block)])

    # every fact the rules read, known or not, with where it came from
    if memo.facts:
        story.append(Paragraph(FACTS_HEADING, h2))
        story.append(Paragraph(_esc(FACTS_HINT), small))
        story.append(Spacer(1, 3))
        frows = [[Paragraph(x, headcell) for x in ("Fact", "Value", "Where it came from")]]
        for fact in memo.facts:
            value = _esc(fact_value_text(fact))
            frows.append(
                [
                    Paragraph(_esc(fact.label), cell),
                    Paragraph(
                        value if fact.value is not None else f"<font color='#6b7280'>{value}</font>", cell
                    ),
                    Paragraph(_esc(fact_origin_text(fact)) + _refs(fact.citations, index), cell),
                ]
            )
        ftbl = Table(frows, colWidths=[2.0 * inch, 1.9 * inch, 3.0 * inch], repeatRows=1)
        ftbl.setStyle(header)
        story.append(ftbl)

    story.append(Paragraph("What the records could not establish", h2))
    # the open questions an optional intake question answers (app.memo.intake): the report names the question
    answerable = [q for q in memo.could_not_establish if q.intake_question in QUESTION_BY_ID]
    if answerable:
        story.append(Paragraph(_esc(answerable_line(len(answerable))), body))
        story.append(Spacer(1, 3))
    for q in memo.could_not_establish:
        ask = f" — {_esc(q.ask)}" if q.ask else ""
        asked = QUESTION_BY_ID.get(q.intake_question or "")
        answer = f" {ANSWERABLE_PREFIX} “{_esc(asked.question)}”" if asked is not None else ""
        story.append(
            Paragraph(f"• <b>{NEEDS_LABEL.get(q.needs, q.needs)}:</b> {_esc(q.question)}{ask}{answer}", cell)
        )
    if not memo.could_not_establish:
        story.append(Paragraph("Nothing listed.", cell))
    # the fixed line on every report: what public records cannot show
    story.append(Spacer(1, 4))
    story.append(Paragraph(_esc(memo.records_limits), body))

    # site history: what is on file at this address or parcel (code-built; building work is listed here only)
    history = memo.site_history
    story.append(Paragraph(SITE_HISTORY_HEADING, h2))
    story.append(Paragraph(_esc(history.note), body))
    story.append(Paragraph(f"Matched by: {_esc(history.matched_by)}.", small))
    if history.entries:
        story.append(Spacer(1, 4))
        hrows = [[Paragraph(x, headcell) for x in ("Date", "Kind", "What", "Outcome")]]
        for entry in history.entries:
            what = f"<b>{_esc(entry.permit_type)}</b>"
            if entry.address:
                what += f"<br/>{_esc(entry.address)}"
            what += "<br/>" + record_facts_markup(
                record_id=entry.application_id,
                source_url=entry.source_url,
                use_types=entry.use_types,
                hours_close=entry.hours_close,
                conditions=entry.conditions,
            )
            if entry.description:
                what += f"<br/>{_esc(entry.description)}"
            other = site_entry_filed_under(entry, memo.address)
            if other:  # same parcel, another street number: say so, it may be another unit or storefront
                what += f"<br/>{_esc(other)}"
            what += f" <font color='#6b7280'>[{index.get(entry.citation_id, '?')}]</font>"
            hrows.append(
                [
                    Paragraph(_esc(site_entry_date(entry)), cell),
                    Paragraph(_esc(entry.record_kind_label), cell),
                    Paragraph(what, cell),
                    Paragraph(_esc(site_entry_outcome(entry)), cell),
                ]
            )
        htbl = Table(hrows, colWidths=[0.95 * inch, 1.15 * inch, 3.7 * inch, 1.1 * inch], repeatRows=1)
        htbl.setStyle(header)
        story.append(htbl)
        count_line = site_history_count_line(history)
        if count_line:
            story.append(Spacer(1, 4))
            story.append(Paragraph(_esc(count_line), small))

    story.append(Paragraph("At a glance", h2))
    # the pathway the rules looked up for this concept at this address, then the notes they did not evaluate
    two_col = TableStyle(
        [
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ]
    )
    story.append(Paragraph(f"<b>{PATHWAY_HEADING}</b>", body))
    story.append(Paragraph(_esc(PATHWAY_HINT), small))
    story.append(Spacer(1, 3))
    ptbl = Table(
        [[Paragraph(_esc(a), cell), Paragraph(_esc(b), cell)] for a, b in pathway_rows(memo.pathway)],
        colWidths=[1.3 * inch, 5.6 * inch],
    )
    ptbl.setStyle(two_col)
    story.append(ptbl)
    for pathway_note in memo.pathway.notes:
        story.append(Paragraph(f"• {rule_line_markup(pathway_note, index)}", cell))
    triggers = trigger_markup(memo.pathway, index)
    if triggers:  # every trigger with its control; a control that is not today's says so under it
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>{TRIGGERS_HEADING}</b>", body))
        story.append(Paragraph(_esc(triggers_hint(memo.pathway)), small))
        story.extend(Paragraph(line, cell) for line in triggers)
    story.append(Spacer(1, 8))
    z = memo.zoning
    rows = [
        [
            "Zoning",
            f"{z.district} — bars: {z.bar_permission}, restaurants: {z.restaurant_permission} ({z.code_section})"
            if z
            else "not resolved",
        ],
        ["Overlays", "; ".join(f"{ov.name} ({ov.code_section})" for ov in memo.overlays) or "none"],
        ["Dated decisions", base_rate_line(memo)],
    ]
    t = Table(
        [[Paragraph(_esc(a), cell), Paragraph(_esc(b), cell)] for a, b in rows],
        colWidths=[1.3 * inch, 5.6 * inch],
    )
    t.setStyle(two_col)
    story.append(t)
    if memo.base_rate.counted:  # each decision the counts are made of, with a link to its record
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>{COUNTED_HEADING}</b>", cell))
        for dec in memo.base_rate.counted:
            story.append(
                Paragraph(
                    f"• {_esc(dec.decided_at or 'undated')} · {_esc(dec.permit_type)} · "
                    f"{_esc(dec.address or 'address not recorded')} · {_esc(dec.outcome.replace('_', ' '))} · "
                    f"{_link(dec.source_url, dec.application_id)}",
                    cell,
                )
            )

    story.append(PageBreak())
    story.append(Paragraph("Comparable cases", h2))
    if memo.comparables_note:
        story.append(Paragraph(_esc(memo.comparables_note), small))
        story.append(Spacer(1, 4))
    head = [
        Paragraph(x, headcell) for x in ("Case", "Outcome", TIMING_COLUMN, "Conditions", "Source", "Record")
    ]
    trows = [head]
    as_of = iso_date(memo.data_as_of)  # a pending case's age is counted to the records date
    for comp in memo.comparable_cases:
        last = Paragraph(
            record_facts_markup(
                record_id=comp.application_id,
                source_url=comp.source_url,
                use_types=comp.use_types,
                hours_close=comp.hours_close,
                conditions=[],
            ),
            cell,
        )
        trows.append(
            [
                Paragraph(
                    f"<b>{_esc(comp.permit_type)}</b><br/>{_esc(comp.address or '')}<br/>"
                    f"{comp.distance_m:,.0f} m · {_esc(comp.decided_at or comp.filed_at or 'undated')} "
                    f"<font color='#6b7280'>[{index.get(comp.citation_id, '?')}]</font>",
                    cell,
                ),
                Paragraph(_esc(comp.outcome.replace("_", " ")), cell),
                # the figure names its outcome: days to approval, to withdrawal, pending so far
                Paragraph(_esc(timing_cell(comp, as_of)), cell),
                Paragraph(conditions_cell(comp), cell),
                Paragraph(
                    f"{_esc(comp.source_label)}<br/>{_esc(comp.record_kind_label)}"
                    if comp.record_kind in PATHWAY_RECORD_KINDS  # same rule as the web table
                    else _esc(comp.source_label),
                    cell,
                ),
                last,
            ]
        )
    tbl = Table(
        trows,
        colWidths=[1.65 * inch, 0.8 * inch, 0.85 * inch, 0.7 * inch, 1.0 * inch, 1.9 * inch],
        repeatRows=1,
    )
    tbl.setStyle(header)
    story.append(tbl)
    story.append(Spacer(1, 4))
    story.append(Paragraph(_esc(NO_CONDITIONS_NOTE), small))
    with_conditions = [c for c in memo.comparable_cases if c.conditions]
    if with_conditions:  # every condition on file, case by case, as the record states it
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>{CONDITIONS_HEADING}</b>", cell))
        for comp in with_conditions:
            story.append(
                Paragraph(
                    f"<b>{_esc(comp.address or comp.application_id)}</b> "
                    f"({_link(comp.source_url, comp.application_id)}): " + _esc("; ".join(comp.conditions)),
                    cell,
                )
            )
    timing = decision_time_lines(memo)
    if timing:  # one range per outcome, never one figure across outcomes
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>{TIMING_HEADING}</b>", cell))
        story.append(Paragraph(_esc(REPORT_TEXT["timing_hint"]), small))
        story.extend(Paragraph(f"• {_esc(line)}", cell) for line in timing)
    if memo.source_notes:
        story.append(Spacer(1, 6))
        story.append(Paragraph("<b>What each source leaves out</b>", cell))
        for note in memo.source_notes:
            story.append(Paragraph(f"• <b>{_esc(note.label)}:</b> {_esc(note.leaves_out)}", cell))

    story.append(Paragraph("What the statuses mean", h2))
    for text in memo.status_definitions.values():
        name, _, rest = text.partition(":")
        story.append(Paragraph(f"<b>{_esc(name)}:</b>{_esc(rest)}", cell))

    story.append(Paragraph("Citations", h2))
    for i, cit in enumerate(memo.citations, start=1):
        line = f"[{i}] <b>{_esc(cit.label)}</b>"
        if cit.excerpt:
            line += f" — <i>{_esc(cit.excerpt[:220])}</i>"
        if cit.source_url:
            line += f" <font color='#6b7280'>{_esc(cit.source_url)}</font>"
        story.append(Paragraph(line, cell))
    story.append(Spacer(1, 8))
    for d in memo.disclaimers:
        story.append(Paragraph(_esc(d), small))
    doc.build(story)
    return buf.getvalue()
