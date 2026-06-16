import io
from datetime import datetime


def _clean(value):
    return str(value or "").replace("\n", " ").strip()


def build_screening_questions_pdf(payload):
    try:
        return _build_reportlab_pdf(payload)
    except ModuleNotFoundError:
        return _build_basic_pdf(payload)


def _build_reportlab_pdf(payload):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    questions = payload.get("questions") or []
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title="Interview Screening Questions",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("Screen_Title", parent=styles["Title"], fontSize=18, leading=22, textColor=colors.HexColor("#1f2937"), spaceAfter=12)
    h2 = ParagraphStyle("Screen_H2", parent=styles["Heading2"], fontSize=11, leading=14, textColor=colors.HexColor("#e8643a"), spaceBefore=10, spaceAfter=5)
    body = ParagraphStyle("Screen_Body", parent=styles["BodyText"], fontSize=9, leading=12, textColor=colors.HexColor("#263142"), spaceAfter=4)
    small = ParagraphStyle("Screen_Small", parent=body, fontSize=8, leading=10, textColor=colors.HexColor("#4b5563"))
    story = [
        Paragraph("Interview Screening Questions", title),
        Paragraph(f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}", small),
        Spacer(1, 8),
    ]
    for idx, item in enumerate(questions, start=1):
        skill = _clean(item.get("skill") or f"Question {idx}")
        story.append(Paragraph(f"{idx}. {skill}", h2))
        story.append(Paragraph("<b>Question:</b> " + _clean(item.get("question")), body))
        story.append(Paragraph("<b>Good answer signal:</b> " + _clean(item.get("expected_signal")), body))
        story.append(Paragraph("<b>Follow-up:</b> " + _clean(item.get("follow_up")), body))
    doc.build(story)
    buffer.seek(0)
    return buffer


def _pdf_escape(text):
    return str(text or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_basic_pdf(payload):
    lines = ["Interview Screening Questions", f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}", ""]
    for idx, item in enumerate(payload.get("questions") or [], start=1):
        lines.extend([
            f"{idx}. {item.get('skill') or 'Question'}",
            "Question: " + _clean(item.get("question")),
            "Good answer signal: " + _clean(item.get("expected_signal")),
            "Follow-up: " + _clean(item.get("follow_up")),
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
            stream_lines.append(f"({_pdf_escape(line)}) Tj")
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
