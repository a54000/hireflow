import io
from datetime import datetime

from services.match_analysis import build_match_dashboard


def _clean(value):
    return str(value or "").replace("\n", " ").strip()


def _para(text, style):
    from reportlab.platypus import Paragraph

    return Paragraph(_clean(text), style)


def _bullet_list(items, style):
    from reportlab.platypus import Paragraph

    flow = []
    items = items or []
    if not items:
        return [Paragraph("None noted.", style)]
    for item in items:
        flow.append(Paragraph("• " + _clean(item), style))
    return flow


def build_match_pdf(analysis):
    try:
        return _build_reportlab_pdf(analysis)
    except ModuleNotFoundError:
        return _build_basic_pdf(analysis)


def _build_reportlab_pdf(analysis):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    dashboard = analysis.get("dashboard") or build_match_dashboard(analysis)
    overview = dashboard.get("overview", {})
    snapshot = dashboard.get("candidate_snapshot", {})
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title="ATS Match Analysis",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("ATS_Title", parent=styles["Title"], fontSize=18, leading=22, textColor=colors.HexColor("#1f2937"), spaceAfter=12)
    h2 = ParagraphStyle("ATS_H2", parent=styles["Heading2"], fontSize=12, leading=15, textColor=colors.HexColor("#e8643a"), spaceBefore=10, spaceAfter=6)
    body = ParagraphStyle("ATS_Body", parent=styles["BodyText"], fontSize=9, leading=12, textColor=colors.HexColor("#263142"), spaceAfter=4)
    small = ParagraphStyle("ATS_Small", parent=body, fontSize=8, leading=10, textColor=colors.HexColor("#4b5563"))
    story = []
    candidate_name = snapshot.get("candidate_name") or "Candidate"
    story.append(Paragraph(f"ATS Match Analysis: {candidate_name}", title))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}", small))
    story.append(Spacer(1, 8))

    overview_rows = [
        ["Final Score", f"{overview.get('final_score', 0)}%"],
        ["Verdict", overview.get("verdict", "-")],
        ["Recommendation", overview.get("recommendation", "-")],
        ["Confidence", f"{(overview.get('confidence') or {}).get('label', '-')} ({(overview.get('confidence') or {}).get('score', 0)}%)"],
        ["Manual Review", "Required" if (dashboard.get("manual_review") or {}).get("required") else "Not Required"],
        ["Structured Score", f"{overview.get('structured_score', 0)}%"],
        ["Semantic Score", f"{overview.get('semantic_score', 0)}%"],
        ["Hard Filter Score", f"{overview.get('hard_filter_score', 0)}%"],
    ]
    story.append(Paragraph("Match Overview", h2))
    story.append(_table(overview_rows, col_widths=[1.7 * inch, 4.8 * inch]))

    story.append(Paragraph("Candidate Overall Summary", h2))
    story.append(_para(analysis.get("overall_recruiter_summary") or dashboard.get("recruiter_summary", "-"), body))

    candidate_summary = dashboard.get("candidate_summary", {}) or {}
    role_family = dashboard.get("role_family_comparison", {}) or {}
    experience_cmp = dashboard.get("experience_comparison", {}) or {}
    skill_years = dashboard.get("tech_skills_experience_years", []) or []
    recent = dashboard.get("recent_professional_experience", {}) or {}

    story.append(Paragraph("Candidate Summary", h2))
    story.append(_table([
        ["Score", f"{candidate_summary.get('score_percent', overview.get('final_score', 0))}%"],
        ["Verdict", candidate_summary.get("verdict", overview.get("verdict", "-"))],
        ["Recommendation", candidate_summary.get("recommendation", overview.get("recommendation", "-"))],
        ["Confidence", f"{(candidate_summary.get('confidence') or {}).get('label', '-')} ({(candidate_summary.get('confidence') or {}).get('score', 0)}%)"],
    ], col_widths=[1.6 * inch, 4.9 * inch]))

    story.append(Paragraph("Role Family Comparison", h2))
    story.append(_table([
        ["JD Role Family", role_family.get("jd_family", "-")],
        ["CV Role Family", role_family.get("candidate_family", "-")],
        ["Shared Skills", ", ".join(role_family.get("shared_skills", [])[:12]) or "-"],
        ["Validation Evidence", ", ".join(role_family.get("validation_evidence", [])[:12]) or "-"],
    ], col_widths=[1.8 * inch, 4.7 * inch]))
    story.append(_para(role_family.get("match_summary", "-"), body))

    story.append(Paragraph("Experience Comparison", h2))
    story.append(_table([
        ["JD Requirement", experience_cmp.get("jd_required", "-")],
        ["Candidate Experience", f"{experience_cmp.get('candidate_years', 0)} years"],
        ["Fit Summary", experience_cmp.get("fit_summary", "-")],
    ], col_widths=[1.8 * inch, 4.7 * inch]))

    validation_gaps = dashboard.get("validation_gaps", []) or []
    if validation_gaps:
        story.append(Paragraph("Validation Gaps", h2))
        gap_rows = [["Area", "Severity", "Message"]]
        for gap in validation_gaps:
            gap_rows.append([
                gap.get("area", "-"),
                str(gap.get("severity", "medium")).upper(),
                gap.get("message", "-"),
            ])
        story.append(_table(gap_rows, col_widths=[1.4 * inch, 0.9 * inch, 4.2 * inch], header=True))
        for gap in validation_gaps:
            evidence = gap.get("evidence", []) or []
            if evidence:
                story.append(_para(f"{gap.get('area', 'Validation')} evidence: {', '.join(str(e) for e in evidence[:6])}", body))

    if skill_years:
        story.append(Paragraph("Technical Skills Experience in Years", h2))
        skill_rows = [["Skill", "Years", "Evidence Roles"]]
        for item in skill_years:
            skill_rows.append([
                item.get("skill", "-"),
                f"{item.get('years', 0)}",
                ", ".join(item.get("evidence_roles", [])[:3]) or "-",
            ])
        story.append(_table(skill_rows, col_widths=[1.8 * inch, 0.9 * inch, 4.0 * inch], header=True))

    if recent:
        story.append(Paragraph("Most Recent Professional Experience", h2))
        story.append(_table([
            ["Title", recent.get("title", "-")],
            ["Company", recent.get("company", "-")],
            ["Duration", f"{recent.get('duration_years', 0)} years"],
            ["Skills Used", ", ".join(recent.get("skills_used", [])[:10]) or "-"],
        ], col_widths=[1.5 * inch, 5.0 * inch]))
        story.append(Paragraph("Achievements / Tangible Output", h2))
        story.extend(_bullet_list(recent.get("achievements", []), body))
        story.append(Paragraph("Responsibilities", h2))
        story.extend(_bullet_list(recent.get("responsibilities", []), body))

    story.append(Paragraph("Strengths", h2))
    story.extend(_bullet_list(dashboard.get("strengths", []), body))

    story.append(Paragraph("Concerns", h2))
    story.extend(_bullet_list(dashboard.get("concerns", []), body))

    semantic_insights = analysis.get("semantic_match_insights") or dashboard.get("semantic_insights", [])
    story.append(Paragraph("Semantic Match Insights", h2))
    story.extend(_bullet_list(semantic_insights, body))

    role_reasoning = analysis.get("role_alignment_reasoning") or dashboard.get("role_alignment_reasoning", [])
    story.append(Paragraph("Role Alignment Reasoning", h2))
    story.extend(_bullet_list(role_reasoning, body))

    hard_filters = dashboard.get("hard_filters", {})
    filters = hard_filters.get("filters", []) if isinstance(hard_filters, dict) else []
    if filters:
        story.append(Paragraph("Hard Filters", h2))
        filter_rows = [["Filter", "Status", "Reason"]]
        for item in filters:
            filter_rows.append([
                item.get("name", "-"),
                "Passed" if item.get("passed") else item.get("severity", "Failed").title(),
                item.get("reason", ""),
            ])
        story.append(_table(filter_rows, col_widths=[1.4 * inch, 0.9 * inch, 4.0 * inch], header=True))

    story.append(Paragraph("Score Breakdown", h2))
    breakdown_rows = [["Category", "Score", "Weight", "Reason"]]
    for item in dashboard.get("score_breakdown", []) or []:
        breakdown_rows.append([
            item.get("label", "-"),
            f"{item.get('score', 0)}%",
            f"{round(float(item.get('weight', 0)) * 100)}%",
            item.get("reason", ""),
        ])
    story.append(_table(breakdown_rows, col_widths=[1.45 * inch, 0.65 * inch, 0.65 * inch, 3.8 * inch], header=True))

    penalties = dashboard.get("penalties", []) or []
    if penalties:
        story.append(Paragraph("Penalties Applied", h2))
        penalty_rows = [["Reason", "Impact"]]
        for penalty in penalties:
            penalty_rows.append([penalty.get("reason", "-"), str(penalty.get("impact", 0))])
        story.append(_table(penalty_rows, col_widths=[5.4 * inch, 0.9 * inch], header=True))

    doc.build(story)
    buffer.seek(0)
    return buffer


def _table(rows, col_widths=None, header=False):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(rows, colWidths=col_widths, hAlign="LEFT", repeatRows=1 if header else 0)
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
    table.setStyle(TableStyle(style))
    return table


def _build_basic_pdf(analysis):
    dashboard = analysis.get("dashboard") or build_match_dashboard(analysis)
    overview = dashboard.get("overview", {})
    snapshot = dashboard.get("candidate_snapshot", {})
    lines = [
        f"ATS Match Analysis: {snapshot.get('candidate_name') or 'Candidate'}",
        f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}",
        "",
        "Match Overview",
        f"Final Score: {overview.get('final_score', 0)}%",
        f"Verdict: {overview.get('verdict', '-')}",
        f"Recommendation: {overview.get('recommendation', '-')}",
        f"Confidence: {(overview.get('confidence') or {}).get('label', '-')} ({(overview.get('confidence') or {}).get('score', 0)}%)",
        f"Manual Review: {'Required' if (dashboard.get('manual_review') or {}).get('required') else 'Not Required'}",
        f"Structured Score: {overview.get('structured_score', 0)}%",
        f"Semantic Score: {overview.get('semantic_score', 0)}%",
        f"Hard Filter Score: {overview.get('hard_filter_score', 0)}%",
        "",
        "Candidate Overall Summary",
        analysis.get("overall_recruiter_summary") or dashboard.get("recruiter_summary", "-"),
        "",
        "Candidate Summary",
        f"- Score: {dashboard.get('candidate_summary', {}).get('score_percent', overview.get('final_score', 0))}%",
        f"- Verdict: {dashboard.get('candidate_summary', {}).get('verdict', overview.get('verdict', '-'))}",
        f"- Recommendation: {dashboard.get('candidate_summary', {}).get('recommendation', overview.get('recommendation', '-'))}",
        f"- Confidence: {(dashboard.get('candidate_summary', {}).get('confidence') or {}).get('label', '-')} ({(dashboard.get('candidate_summary', {}).get('confidence') or {}).get('score', 0)}%)",
        "",
        "Role Family Comparison",
        f"- JD Role Family: {dashboard.get('role_family_comparison', {}).get('jd_family', '-')}",
        f"- CV Role Family: {dashboard.get('role_family_comparison', {}).get('candidate_family', '-')}",
        f"- Shared Skills: {', '.join(dashboard.get('role_family_comparison', {}).get('shared_skills', [])[:12]) or '-'}",
        f"- Validation Evidence: {', '.join(dashboard.get('role_family_comparison', {}).get('validation_evidence', [])[:12]) or '-'}",
        f"- {dashboard.get('role_family_comparison', {}).get('match_summary', '-')}",
        "",
        "Experience Comparison",
        f"- JD Requirement: {dashboard.get('experience_comparison', {}).get('jd_required', '-')}",
        f"- Candidate Experience: {dashboard.get('experience_comparison', {}).get('candidate_years', 0)} years",
        f"- Fit Summary: {dashboard.get('experience_comparison', {}).get('fit_summary', '-')}",
        "",
        "Validation Gaps",
    ]
    validation_gaps = dashboard.get("validation_gaps", []) or []
    if validation_gaps:
        for gap in validation_gaps:
            lines.append(
                f"- {gap.get('area', 'Validation')} [{str(gap.get('severity', 'medium')).upper()}]: {gap.get('message', '-')}"
            )
            evidence = gap.get("evidence", []) or []
            if evidence:
                lines.append(f"  - Evidence: {', '.join(str(item) for item in evidence[:6])}")
    else:
        lines.append("- No explicit validation gaps were generated for this match.")
    lines.extend([
        "",
        "Technical Skills Experience in Years",
    ])
    skill_years = dashboard.get("tech_skills_experience_years", []) or []
    lines.extend([f"- {item.get('skill', '-')}: {item.get('years', 0)} years ({', '.join(item.get('evidence_roles', [])[:3]) or 'evidence role not isolated'})" for item in skill_years] or ["- None noted."])
    recent = dashboard.get("recent_professional_experience", {}) or {}
    lines.extend([
        "",
        "Most Recent Professional Experience",
        f"- Title: {recent.get('title', '-')}",
        f"- Company: {recent.get('company', '-')}",
        f"- Duration: {recent.get('duration_years', 0)} years",
        f"- Skills Used: {', '.join(recent.get('skills_used', [])[:10]) or '-'}",
        "- Achievements / Tangible Output",
    ])
    lines.extend([f"  - {item}" for item in recent.get('achievements', [])] or ["  - None noted."])
    lines.extend(["- Responsibilities"])
    lines.extend([f"  - {item}" for item in recent.get('responsibilities', [])] or ["  - None noted."])
    lines.extend(["", "Strengths"])
    lines.extend([f"- {item}" for item in dashboard.get("strengths", [])] or ["- None noted."])
    lines.extend(["", "Concerns"])
    lines.extend([f"- {item}" for item in dashboard.get("concerns", [])] or ["- None noted."])
    manual_review = dashboard.get("manual_review", {}) or {}
    if manual_review.get("required"):
        lines.extend(["", "Manual Review Required"])
        lines.extend([f"- {item}" for item in manual_review.get("reasons", [])] or ["- Manual review recommended."])
    lines.extend(["", "Semantic Match Insights"])
    semantic_insights = analysis.get("semantic_match_insights") or dashboard.get("semantic_insights", [])
    lines.extend([f"- {item}" for item in semantic_insights] or ["- None noted."])
    lines.extend(["", "Role Alignment Reasoning"])
    role_reasoning = analysis.get("role_alignment_reasoning") or dashboard.get("role_alignment_reasoning", [])
    lines.extend([f"- {item}" for item in role_reasoning] or ["- None noted."])
    hard_filters = dashboard.get("hard_filters", {})
    filters = hard_filters.get("filters", []) if isinstance(hard_filters, dict) else []
    if filters:
        lines.extend(["", "Hard Filters"])
        for item in filters:
            status = "Passed" if item.get("passed") else item.get("severity", "Failed").title()
            lines.append(f"- {item.get('name', '-')}: {status}. {item.get('reason', '')}")
    lines.extend(["", "Score Breakdown"])
    for item in dashboard.get("score_breakdown", []) or []:
        lines.append(f"- {item.get('label', '-')}: {item.get('score', 0)}% | Weight {round(float(item.get('weight', 0))*100)}% | {item.get('reason', '')}")
    if dashboard.get("penalties"):
        lines.extend(["", "Penalties Applied"])
        lines.extend([f"- {p.get('reason', '-')} ({p.get('impact', 0)})" for p in dashboard.get("penalties", [])])
    return _simple_pdf(lines)


def _pdf_escape(text):
    return str(text or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _simple_pdf(lines):
    # Minimal single-font PDF fallback for environments without ReportLab.
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
    pages = []
    for i in range(0, len(wrapped), 48):
        pages.append(wrapped[i:i + 48])
    objects = []
    page_refs = []
    font_obj = 3
    objects.append("<< /Type /Catalog /Pages 2 0 R >>")
    objects.append("")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for page in pages or [[]]:
        content_lines = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
        for line in page:
            content_lines.append(f"({_pdf_escape(line)}) Tj")
            content_lines.append("T*")
        content_lines.append("ET")
        stream = "\n".join(content_lines)
        content_obj_num = len(objects) + 2
        page_obj_num = len(objects) + 1
        page_refs.append(f"{page_obj_num} 0 R")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_obj} 0 R >> >> /Contents {content_obj_num} 0 R >>")
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
    buf = io.BytesIO("".join(pdf).encode("latin-1", "ignore"))
    buf.seek(0)
    return buf
