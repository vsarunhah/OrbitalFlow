"""Generate a polished PDF from structured resume content or Markdown."""

from __future__ import annotations

import io
from typing import Any

import mistune
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

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

# Markdown PDF: sizes chosen to match on-screen preview (pt) / readable print
_MD_BODY_SIZE = 11
_MD_BODY_LEADING = 13.5
_MD_BULLET_SIZE = 10
_MD_BULLET_LEADING = 11.5
_MD_CODE_SIZE = 9
_MD_HEADING_SIZES = {1: 16, 2: 12, 3: 11, 4: 10, 5: 10, 6: 10}

# Markdown PDF: usable width inside margins (inches)
_MD_CONTENT_WIDTH_IN = 7.5

_md_parse = mistune.create_markdown(
    renderer="ast",
    plugins=["strikethrough", "table", "url"],
    hard_wrap=True,
)


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


def _inline_nodes_to_markup(nodes: list[dict[str, Any]] | None) -> str:
    """Turn mistune inline nodes into ReportLab Paragraph mini-markup."""
    if not nodes:
        return ""
    parts: list[str] = []
    for n in nodes:
        t = n.get("type")
        if t == "text":
            parts.append(_escape(str(n.get("raw", ""))).replace("\n", "<br/>"))
        elif t == "strong":
            inner = _inline_nodes_to_markup(n.get("children"))
            parts.append(f"<b>{inner}</b>")
        elif t in ("emphasis", "em"):
            inner = _inline_nodes_to_markup(n.get("children"))
            parts.append(f"<i>{inner}</i>")
        elif t == "codespan":
            raw = _escape(str(n.get("raw", "")))
            parts.append(f'<font name="Courier">{raw}</font>')
        elif t == "linebreak":
            parts.append("<br/>")
        elif t == "link":
            url = _escape(str(n.get("attrs", {}).get("url", "") or ""))
            inner = _inline_nodes_to_markup(n.get("children")) or url
            parts.append(f'<a href="{url}" color="blue">{inner}</a>')
        elif t == "strikethrough":
            inner = _inline_nodes_to_markup(n.get("children"))
            parts.append(f"<strike>{inner}</strike>")
        elif t == "block_text":
            parts.append(_inline_nodes_to_markup(n.get("children")))
        else:
            raw = n.get("raw")
            if isinstance(raw, str):
                parts.append(_escape(raw))
    return "".join(parts)


def _paragraph_from_inlines(children: list[dict[str, Any]] | None, style: ParagraphStyle) -> Paragraph:
    markup = _inline_nodes_to_markup(children)
    if not markup.strip():
        return Paragraph("&nbsp;", style)
    return Paragraph(markup, style)


def _md_heading_style(base: ParagraphStyle, level: int) -> ParagraphStyle:
    level = max(1, min(6, level))
    sz = _MD_HEADING_SIZES.get(level, 10)
    return ParagraphStyle(
        f"MdH{level}",
        parent=base,
        fontSize=sz,
        leading=sz * LINE_HEIGHT,
        textColor=ACCENT if level <= 2 else colors.HexColor("#1a202c"),
        spaceBefore=8 if level == 1 else 6,
        spaceAfter=4,
        fontName="Helvetica-Bold" if level <= 3 else "Helvetica",
    )


def _emit_table(node: dict[str, Any], story: list, body_style: ParagraphStyle) -> None:
    rows_out: list[list[Paragraph]] = []
    for sec in node.get("children") or []:
        st = sec.get("type")
        if st == "table_head":
            row: list[Paragraph] = []
            for cell in sec.get("children") or []:
                if cell.get("type") != "table_cell":
                    continue
                row.append(_paragraph_from_inlines(cell.get("children"), body_style))
            if row:
                rows_out.append(row)
        elif st == "table_body":
            for tr in sec.get("children") or []:
                if tr.get("type") != "table_row":
                    continue
                row = []
                for cell in tr.get("children") or []:
                    if cell.get("type") != "table_cell":
                        continue
                    row.append(_paragraph_from_inlines(cell.get("children"), body_style))
                if row:
                    rows_out.append(row)
    if not rows_out:
        return
    col_count = max(len(r) for r in rows_out)
    for r in rows_out:
        while len(r) < col_count:
            r.append(Paragraph("&nbsp;", body_style))
    col_w = (_MD_CONTENT_WIDTH_IN * inch) / col_count
    tbl = Table(rows_out, colWidths=[col_w] * col_count, hAlign="LEFT")
    tbl.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f7fafc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(tbl)
    story.append(Spacer(1, 6))


def _emit_list(
    node: dict[str, Any],
    story: list,
    bullet_style: ParagraphStyle,
    *,
    depth: int = 0,
) -> None:
    ordered = bool(node.get("attrs", {}).get("ordered", False))
    items = [x for x in (node.get("children") or []) if x.get("type") == "list_item"]
    for i, item in enumerate(items):
        bullet = f"{i + 1}." if ordered else "•"
        first = True
        for child in item.get("children") or []:
            ct = child.get("type")
            if ct == "block_text":
                inner = _inline_nodes_to_markup(child.get("children"))
                prefix = f"{bullet} " if first else ""
                first = False
                left = 10 + depth * 14
                st = ParagraphStyle(
                    "MdLi",
                    parent=bullet_style,
                    leftIndent=left,
                    spaceAfter=2,
                    alignment=TA_LEFT,
                )
                markup = prefix + inner if inner.strip() else prefix + "&nbsp;"
                story.append(Paragraph(markup, st))
            elif ct == "paragraph":
                inner = _inline_nodes_to_markup(child.get("children"))
                prefix = f"{bullet} " if first else ""
                first = False
                left = 10 + depth * 14
                st = ParagraphStyle(
                    "MdLiP",
                    parent=bullet_style,
                    leftIndent=left,
                    spaceAfter=3,
                    alignment=TA_LEFT,
                )
                story.append(Paragraph(prefix + inner if inner.strip() else prefix + "&nbsp;", st))
            elif ct == "list":
                _emit_list(child, story, bullet_style, depth=depth + 1)


def _emit_block(
    node: dict[str, Any],
    story: list,
    *,
    styles_pack: dict[str, ParagraphStyle],
    quote_depth: int = 0,
) -> None:
    t = node.get("type")
    base_body = styles_pack["body"]
    if t == "blank_line":
        return
    if t == "thematic_break":
        story.append(_horizontal_rule(_MD_CONTENT_WIDTH_IN))
        story.append(Spacer(1, 4))
        return
    if t == "heading":
        level = int((node.get("attrs") or {}).get("level") or 1)
        hst = _md_heading_style(base_body, level)
        if quote_depth:
            hst = ParagraphStyle(
                f"{hst.name}Q",
                parent=hst,
                leftIndent=quote_depth * 10,
            )
        story.append(_paragraph_from_inlines(node.get("children"), hst))
        return
    if t == "paragraph":
        pst = ParagraphStyle(
            "MdP",
            parent=base_body,
            leftIndent=quote_depth * 10,
            spaceAfter=4,
        )
        story.append(_paragraph_from_inlines(node.get("children"), pst))
        return
    if t == "list":
        _emit_list(node, story, styles_pack["bullet"], depth=0)
        return
    if t == "block_code":
        raw = str(node.get("raw", "")).rstrip("\n")
        cst = ParagraphStyle(
            "MdCode",
            parent=styles_pack["code"],
            fontName="Courier",
            fontSize=_MD_CODE_SIZE,
            leading=_MD_CODE_SIZE + 1,
            leftIndent=quote_depth * 10,
            spaceAfter=6,
        )
        story.append(Preformatted(raw if raw else " ", cst, maxLineLength=120))
        return
    if t == "block_quote":
        for ch in node.get("children") or []:
            _emit_block(ch, story, styles_pack=styles_pack, quote_depth=quote_depth + 1)
        return
    if t == "table":
        _emit_table(node, story, base_body)
        return


def build_pdf_from_markdown(md: str) -> bytes:
    """Render Markdown to a letter-size multi-page PDF using mistune + ReportLab."""
    ast = _md_parse(md or "")
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
    body = ParagraphStyle(
        "MdBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=_MD_BODY_SIZE,
        leading=_MD_BODY_LEADING,
        textColor=colors.HexColor("#2d3748"),
        spaceAfter=4,
    )
    bullet = ParagraphStyle(
        "MdBullet",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=_MD_BULLET_SIZE,
        leading=_MD_BULLET_LEADING,
        textColor=colors.HexColor("#2d3748"),
        leftIndent=14,
        spaceAfter=2,
    )
    code = ParagraphStyle(
        "MdCodeParent",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=_MD_CODE_SIZE,
        leading=_MD_CODE_SIZE + 1,
    )
    pack = {"body": body, "bullet": bullet, "code": code}
    story: list = []
    if isinstance(ast, list):
        for node in ast:
            if isinstance(node, dict):
                _emit_block(node, story, styles_pack=pack)
    if not story:
        story.append(Paragraph("&nbsp;", body))
    doc.build(story)
    return buffer.getvalue()
