"""Server-rendered PDF export of a plan (ReportLab, pure Python)."""

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
from app.models.plan import PlanRecord

INK = colors.HexColor("#14213d")
ACCENT = colors.HexColor("#e36414")
MUTED = colors.HexColor("#6b7280")
LINE = colors.HexColor("#e5e7eb")


def _esc(text: str | None) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _money(lo: float, hi: float) -> str:
    return f"${lo:,.0f}" if lo == hi else f"${lo:,.0f}–${hi:,.0f}"


def render_plan_pdf(record: PlanRecord) -> bytes:
    if record.plan is None:
        raise ValueError("plan has no content yet")
    plan = record.plan
    done = {s.step_key for s in record.steps if s.done}
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
        title=record.title,
        author=settings.APP_NAME,
    )
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=20, textColor=INK, alignment=0, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=INK, spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10.5, textColor=MUTED)
    cell = ParagraphStyle("cell", parent=body, fontSize=8, leading=10)

    story: list[object] = [Paragraph(_esc(record.title), h1)]
    tl = plan.timeline
    meta = (
        f"Generated {plan.generated_at[:10]} · Start {tl.start_date} · Realistic opening {tl.projected_open_date} "
        f"(optimistic {tl.optimistic_open_date})"
    )
    if tl.target_open_date:
        verdict = "feasible" if tl.feasible else f"{tl.days_short} days short"
        meta += f" · Target {tl.target_open_date} ({verdict})"
    story.append(Paragraph(_esc(meta), small))
    story.append(Spacer(1, 10))
    for para in plan.summary.split("\n"):
        if para.strip():
            story.append(Paragraph(_esc(para.strip()), body))
            story.append(Spacer(1, 4))
    if plan.unsupported_city_note:
        story.append(Paragraph("<b>City coverage:</b> " + _esc(plan.unsupported_city_note), body))

    # ---- fees + critical path
    story.append(Paragraph("At a glance", h2))
    names = {s.id: s.name for s in plan.steps}
    glance = [
        ["Permits & licenses", str(len(plan.steps))],
        ["Government fees", _money(plan.fees.total_min, plan.fees.total_max)],
        ["Total duration", f"{tl.total_days_min}–{tl.total_days_max} days"],
        ["Critical path", " → ".join(names.get(i, i) for i in tl.critical_path)],
    ]
    t = Table(
        [[Paragraph(_esc(a), cell), Paragraph(_esc(b), cell)] for a, b in glance],
        colWidths=[1.6 * inch, 5.2 * inch],
    )
    t.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
            ]
        )
    )
    story.append(t)

    # ---- checklist
    story.append(Paragraph("Checklist (in order)", h2))
    rows = [[Paragraph(x, cell) for x in ("#", "Permit", "Agency", "Days", "Fee", "Status")]]
    for s in plan.steps:
        flag = " ✓" if s.id in done else ""
        name = f"<b>{_esc(s.name)}</b>{flag}<br/><font color='#6b7280'>{_esc(s.why_required)}</font>"
        if s.url_status == "dead":
            name += "<br/><font color='#b91c1c'>Link may be outdated — confirm with agency</font>"
        conf = "Verified" if s.confidence == "verified" else "Estimated"
        cp = " · critical path" if s.on_critical_path else ""
        rows.append(
            [
                Paragraph(str(s.order), cell),
                Paragraph(name, cell),
                Paragraph(_esc(s.issuing_agency), cell),
                Paragraph(f"{int(s.typical_timeline_days.min)}–{int(s.typical_timeline_days.max)}", cell),
                Paragraph(_money(s.fee_range_usd.min, s.fee_range_usd.max), cell),
                Paragraph(_esc(conf + cp), cell),
            ]
        )
    table = Table(
        rows,
        colWidths=[0.3 * inch, 2.7 * inch, 1.7 * inch, 0.55 * inch, 0.85 * inch, 0.9 * inch],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    for i, s in enumerate(plan.steps, start=1):
        if s.on_critical_path:
            table.setStyle(TableStyle([("LINEBEFORE", (0, i), (0, i), 2, ACCENT)]))
    story.append(table)

    # ---- week by week
    story.append(PageBreak())
    story.append(Paragraph("Week-by-week schedule", h2))
    story.append(Paragraph(_esc(tl.sequencing_rationale), body))
    story.append(Spacer(1, 6))
    for w in tl.weeks:
        block = [
            Paragraph(f"<b>Week {w.week_number}</b> · {w.start_date} → {w.end_date} — {_esc(w.focus)}", body)
        ]
        block += [Paragraph("• " + _esc(a), cell) for a in w.actions]
        block.append(Spacer(1, 5))
        story.append(KeepTogether(block))

    # ---- blockers
    story.append(Paragraph("Top stall risks", h2))
    for b in plan.blockers:
        block = [
            Paragraph(
                f"<b>{_esc(b.title)}</b> · {b.severity} severity · {b.likelihood} · +{b.impact_days_min}–{b.impact_days_max} days",
                body,
            ),
            Paragraph(_esc(b.description), cell),
            Paragraph("<b>Mitigation:</b> " + _esc(b.mitigation), cell),
            Spacer(1, 6),
        ]
        story.append(KeepTogether(block))

    # ---- fees by category + disclaimers
    story.append(Paragraph("Fees by category", h2))
    fee_rows = [
        [Paragraph(c.category.replace("_", " ").title(), cell), Paragraph(_money(c.min, c.max), cell)]
        for c in plan.fees.by_category
    ]
    ft = Table(fee_rows, colWidths=[3 * inch, 2 * inch])
    ft.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE)]))
    story.append(ft)
    story.append(Paragraph(_esc(plan.fees.notes), small))
    story.append(Spacer(1, 10))
    for d in plan.disclaimers:
        story.append(Paragraph(_esc(d), small))
    doc.build(story)
    return buf.getvalue()
