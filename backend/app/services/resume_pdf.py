"""Generate a single-page, polished PDF from structured resume content."""

from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

from app.schemas.resume import ParsedResume

# Single-page fit: tight margins and compact spacing (letter = 11in height)
MARGIN = 0.4 * inch
NAME_SIZE = 11
SECTION_SIZE = 8
BODY_SIZE = 7
BULLET_SIZE = 6
LINE_HEIGHT = 1.1
SPACE_AFTER_HEADING = 1.5
SPACE_AFTER_ITEM = 0.5
SPACE_BETWEEN_SECTIONS = 3
ACCENT = colors.HexColor("#2c5282")  # professional blue-gray


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _to_para(style: ParagraphStyle, text: str) -> Paragraph:
    if not text:
        return Paragraph("&nbsp;", style)
    return Paragraph(_escape(text).replace("\n", "<br/>"), style)


def _horizontal_rule(width_inches: float = 7.5) -> Table:
    return Table(
        [[""]],
        colWidths=[width_inches * inch],
        rowHeights=[0.5],
        style=[("BACKGROUND", (0, 0), (-1, -1), ACCENT)],
    )


def build_pdf(parsed: ParsedResume) -> bytes:
    """Build a single-page PDF from ParsedResume. Compact layout, clear hierarchy."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )
    styles = getSampleStyleSheet()

    name_style = ParagraphStyle(
        "ResumeName",
        parent=styles["Normal"],
        fontSize=NAME_SIZE,
        leading=NAME_SIZE * LINE_HEIGHT,
        textColor=colors.HexColor("#1a202c"),
        spaceAfter=2,
        fontName="Helvetica-Bold",
    )
    contact_style = ParagraphStyle(
        "ResumeContact",
        parent=styles["Normal"],
        fontSize=BODY_SIZE,
        leading=BODY_SIZE * LINE_HEIGHT,
        textColor=colors.HexColor("#4a5568"),
        spaceAfter=SPACE_BETWEEN_SECTIONS - 1,
    )
    section_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontSize=SECTION_SIZE,
        leading=SECTION_SIZE * LINE_HEIGHT,
        textColor=ACCENT,
        spaceBefore=SPACE_BETWEEN_SECTIONS,
        spaceAfter=SPACE_AFTER_HEADING,
        fontName="Helvetica-Bold",
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=BODY_SIZE,
        leading=BODY_SIZE * LINE_HEIGHT,
        textColor=colors.HexColor("#2d3748"),
        spaceAfter=SPACE_AFTER_ITEM,
    )
    job_header_style = ParagraphStyle(
        "JobHeader",
        parent=styles["Normal"],
        fontSize=BODY_SIZE,
        leading=BODY_SIZE * LINE_HEIGHT,
        textColor=colors.HexColor("#1a202c"),
        spaceAfter=0.5,
        fontName="Helvetica-Bold",
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        parent=styles["Normal"],
        fontSize=BULLET_SIZE,
        leading=BULLET_SIZE * 1.18,
        textColor=colors.HexColor("#2d3748"),
        leftIndent=10,
        spaceAfter=0,
    )

    story = []

    # Name
    contact = parsed.contact
    if contact and contact.name:
        story.append(_to_para(name_style, contact.name))
    if contact:
        parts = [p for p in [contact.email, contact.phone] if p]
        if parts:
            story.append(_to_para(contact_style, " &middot; ".join(parts)))
    story.append(_horizontal_rule())

    sections = sorted(parsed.sections, key=lambda s: s.order)
    for sec in sections:
        if not sec.name:
            continue
        story.append(_to_para(section_style, sec.name.upper()))
        if sec.content_type == "text":
            if sec.text:
                story.append(_to_para(body_style, sec.text))
        else:
            is_experience = sec.name.lower() == "experience"
            for it in sec.items or []:
                if is_experience:
                    # Experience: show role on first line, company/location/dates on second line
                    if it.heading:
                        story.append(_to_para(job_header_style, it.heading))
                    if it.subheading:
                        story.append(_to_para(body_style, it.subheading))
                else:
                    # Other list sections: keep compact one-line header
                    header_text = ""
                    if it.heading:
                        header_text = it.heading
                    if it.subheading:
                        header_text = (
                            f"{header_text} — {it.subheading}" if header_text else it.subheading
                        )
                    if header_text:
                        story.append(_to_para(job_header_style, header_text))

                if it.body:
                    for line in (it.body or "").strip().split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("o ") or line.startswith("• "):
                            line = "• " + line[2:].strip()
                        story.append(_to_para(bullet_style, line))
        story.append(Spacer(1, 1))

    doc.build(story)
    return buffer.getvalue()
