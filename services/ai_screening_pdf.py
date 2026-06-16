import io
import re
from datetime import datetime


def _clean(value):
    return str(value or "").replace("\n", " ").strip()


def _plain(value):
    text = _clean(value)
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _para(text, style):
    from reportlab.platypus import Paragraph

    return Paragraph(_clean(text), style)


def _cell(text, style):
    return _para(_plain(text), style)


def _bullet_list(items, style):
    from reportlab.platypus import Paragraph

    flow = []
    items = items or []
    if not items:
        return [Paragraph("None noted.", style)]
    for item in items:
        flow.append(Paragraph("&bull; " + _plain(item), style))
    return flow


def build_ai_screening_pdf(candidate=None, requirement=None, report=None):
    candidate = candidate or {}
    requirement = requirement or {}
    report = report or {}
    try:
        return _build_reportlab_pdf(candidate, requirement, report)
    except ModuleNotFoundError:
        return _build_basic_pdf(candidate, requirement, report)


def _build_reportlab_pdf(candidate, requirement, report):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=0.45 * inch,
        leftMargin=0.45 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        title="AI Screening Report",
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "AI_Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=21,
        textColor=colors.HexColor("#1f2937"),
        spaceAfter=10,
    )
    h2 = ParagraphStyle(
        "AI_H2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=colors.HexColor("#e8643a"),
        spaceBefore=10,
        spaceAfter=5,
    )
    body = ParagraphStyle(
        "AI_Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.6,
        leading=11,
        textColor=colors.HexColor("#263142"),
        spaceAfter=3,
    )
    small = ParagraphStyle(
        "AI_Small",
        parent=body,
        fontSize=7.8,
        leading=9.5,
        textColor=colors.HexColor("#4b5563"),
    )

    def table(rows, col_widths=None, header=False):
        tbl = Table(rows, colWidths=col_widths, hAlign="LEFT", repeatRows=1 if header else 0)
        style = [
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#263142")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
        if header:
            style.extend([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ])
        tbl.setStyle(TableStyle(style))
        return tbl

    candidate_name = _plain(candidate.get("candidate_name") or report.get("candidate_name") or "Candidate")
    target_job = _plain(report.get("target_job_title") or requirement.get("title") or requirement.get("requirement_title") or "-")
    score = report.get("final_score", 0)
    verdict = _plain(report.get("ats_verdict") or "-")
    call_or_reject = _plain(report.get("call_or_reject") or "-")
    summary = report.get("summary") or report.get("recommendation") or "-"
    questions = report.get("screening_questions") or []
    requirement_matches = report.get("requirement_matches") or []

    story = [
        Paragraph(f"AI Screening Report: {candidate_name}", title),
        Paragraph(f"Target Job: {target_job}", body),
        Paragraph(f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}", small),
        Spacer(1, 8),
        Paragraph("Screening Summary", h2),
        table([
            [_cell("Candidate", body), _cell(candidate_name, body)],
            [_cell("Client", body), _cell(requirement.get("client_name") or requirement.get("requirement_client_name") or "-", body)],
            [_cell("Score", body), _cell(f"{score}%", body)],
            [_cell("Verdict", body), _cell(verdict, body)],
            [_cell("Call or Reject", body), _cell(call_or_reject, body)],
            [_cell("Recommendation", body), _cell(report.get("recommendation") or "-", body)],
        ], col_widths=[1.65 * inch, 4.85 * inch]),
        Paragraph("Summary", h2),
        _para(summary, body),
    ]

    if requirement_matches:
        story.append(Paragraph("Requirement Match Summary", h2))
        rows = [[_cell("Job Ask", body), _cell("Candidate Has", body), _cell("Verdict", body)]]
        for item in requirement_matches[:8]:
            rows.append([
                _cell(item.get("what_the_job_asks_for", "-"), body),
                _cell(item.get("what_the_candidate_actually_has", "-"), body),
                _cell(item.get("junior_recruiter_verdict", "-"), body),
            ])
        story.append(table(rows, col_widths=[2.45 * inch, 2.75 * inch, 1.3 * inch], header=True))

    greens = report.get("green_flags") or []
    reds = report.get("red_flags") or []
    story.append(Paragraph("Green Flags", h2))
    story.extend(_bullet_list(greens, body))
    story.append(Paragraph("Red Flags & Gaps", h2))
    story.extend(_bullet_list(reds, body))

    if questions:
        story.append(Paragraph("Recruiter Interview Cheat Sheet", h2))
        for idx, item in enumerate(questions, start=1):
            story.append(Paragraph(f"{idx}. {_plain(item.get('question') or '-')}", body))
            story.append(Paragraph(f"<b>Bad answer:</b> {_plain(item.get('bad_answer') or '-')}", body))
            story.append(Paragraph(f"<b>Good answer:</b> {_plain(item.get('good_answer') or '-')}", body))

    story.append(Paragraph("Candidate Details", h2))
    story.append(table([
        [_cell("Current Role", body), _cell(candidate.get("current_role") or "-", body)],
        [_cell("Current Company", body), _cell(candidate.get("current_company") or "-", body)],
        [_cell("Experience", body), _cell(candidate.get("experience_years") or "-", body)],
        [_cell("Skills", body), _cell(candidate.get("key_skills") or "-", body)],
        [_cell("Requirement", body), _cell(requirement.get("title") or requirement.get("requirement_title") or "-", body)],
    ], col_widths=[1.65 * inch, 4.85 * inch]))

    doc.build(story)
    buffer.seek(0)
    return buffer


def _build_basic_pdf(candidate, requirement, report):
    lines = [
        f"AI Screening Report: {_plain(candidate.get('candidate_name') or report.get('candidate_name') or 'Candidate')}",
        f"Target Job: {_plain(report.get('target_job_title') or requirement.get('title') or requirement.get('requirement_title') or '-')}",
        f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}",
        "",
        "Screening Summary",
        f"Score: {report.get('final_score', 0)}%",
        f"Verdict: {_plain(report.get('ats_verdict') or '-')}",
        f"Call or Reject: {_plain(report.get('call_or_reject') or '-')}",
        f"Recommendation: {_plain(report.get('recommendation') or '-')}",
        f"Client: {_plain(requirement.get('client_name') or requirement.get('requirement_client_name') or '-')}",
        "",
        "Summary",
        _plain(report.get("summary") or report.get("recommendation") or "-"),
        "",
        "Green Flags",
    ]
    lines.extend([f"- {_plain(item)}" for item in (report.get("green_flags") or [])] or ["- None noted."])
    lines.extend(["", "Red Flags & Gaps"])
    lines.extend([f"- {_plain(item)}" for item in (report.get("red_flags") or [])] or ["- None noted."])
    lines.extend(["", "Recruiter Interview Cheat Sheet"])
    for idx, item in enumerate(report.get("screening_questions") or [], start=1):
        lines.extend([
            f"{idx}. {_plain(item.get('question') or '-')}",
            f"Bad answer: {_plain(item.get('bad_answer') or '-')}",
            f"Good answer: {_plain(item.get('good_answer') or '-')}",
            "",
        ])
    wrapped = []
    for line in lines:
        text = _clean(line)
        if not text:
            wrapped.append("")
            continue
        while len(text) > 92:
            cut = text.rfind(" ", 0, 92)
            if cut <= 0:
                cut = 92
            wrapped.append(text[:cut])
            text = text[cut:].strip()
        wrapped.append(text)
    pages = [wrapped[i:i + 48] for i in range(0, len(wrapped), 48)] or [[]]
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    page_refs = []
    for page in pages:
        stream_lines = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
        for line in page:
            stream_lines.append(f"({_clean(line).replace('\\\\', '\\\\\\\\').replace('(', '\\(').replace(')', '\\)')}) Tj")
            stream_lines.append("T*")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines)
        page_obj = len(objects) + 1
        content_obj = len(objects) + 2
        page_refs.append(f"{page_obj} 0 R")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>")
        objects.append(f"<< /Length {len(stream.encode('latin-1', 'ignore'))} >>\nstream\n{stream}\nendstream")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>"
    pdf = ["%PDF-1.4\n"]
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(sum(len(part.encode("latin-1", "ignore")) for part in pdf))
        pdf.append(f"{idx} 0 obj\n{obj}\nendobj\n")
    xref = sum(len(part.encode("latin-1", "ignore")) for part in pdf)
    pdf.append(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.append(f"{offset:010d} 00000 n \n")
    pdf.append(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n")
    buffer = io.BytesIO("".join(pdf).encode("latin-1", "ignore"))
    buffer.seek(0)
    return buffer
