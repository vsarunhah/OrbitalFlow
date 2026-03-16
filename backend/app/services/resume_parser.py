"""Extract text from PDF and structure into configurable sections (rule-based)."""

from __future__ import annotations

import io
import re
import uuid

import pdfplumber

from app.schemas.resume import (
    ParsedResume,
    ResumeContact,
    ResumeSection,
    SectionItem,
)


# Max file size 10 MB
MAX_PDF_BYTES = 10 * 1024 * 1024

# Known section headers (case-insensitive); map variants to display name
SECTION_HEADERS = [
    "experience",
    "work experience",
    "employment",
    "education",
    "skills",
    "summary",
    "professional summary",
    "objective",
    "contact",
    "contact information",
    "projects",
    "certifications",
    "awards",
    "publications",
    "references",
]

CANONICAL_NAME = {
    "work experience": "Experience",
    "employment": "Experience",
    "professional summary": "Summary",
    "objective": "Summary",
    "contact information": "Contact",
}


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract raw text from a PDF. Raises ValueError if not a PDF or empty."""
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds maximum size (10 MB)")
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    parts.append(text)
            if not parts:
                raise ValueError("PDF contains no extractable text")
            return "\n\n".join(parts)
    except Exception as e:
        if "PDF" in type(e).__name__ or "pdf" in str(e).lower():
            raise ValueError("Invalid or corrupted PDF") from e
        raise


def _find_section_positions(text: str) -> list[tuple[int, str, str]]:
    """
    Find all section headers in text. Returns list of (start_pos, header_key, display_name).
    Uses known headers first, then any line that looks like a section title (short, title case).
    """
    text_lower = text.lower()
    found: list[tuple[int, str, str]] = []

    # 1) Known headers
    for header in SECTION_HEADERS:
        pattern = rf"(?m)^\s*{re.escape(header)}\s*:?\s*$"
        for m in re.finditer(pattern, text_lower, re.IGNORECASE):
            # Get actual casing from original text for display
            display = CANONICAL_NAME.get(header, header.title())
            found.append((m.start(), header, display))

    # 2) Generic: line that looks like a section title (short, starts with letter, no period in middle)
    # Skip matches in the first ~120 chars to avoid treating the resume holder's name as a section
    SKIP_HEADER_PREFIX_CHARS = 120
    generic = re.compile(r"(?m)^\s*([A-Z][A-Za-z0-9\s&]{2,50}?)\s*:?\s*$")
    for m in generic.finditer(text):
        if m.start() < SKIP_HEADER_PREFIX_CHARS:
            continue
        title = m.group(1).strip()
        if len(title) < 3 or "." in title:
            continue
        key = title.lower()
        if key in (h.lower() for h in SECTION_HEADERS):
            continue
        if any(f[1] == key for f in found):
            continue
        found.append((m.start(), key, title))

    found.sort(key=lambda x: x[0])
    return found


def _section_content(text: str, start: int, end: int) -> str:
    """Extract section body (strip the header line)."""
    content = text[start:end]
    first_nl = content.find("\n")
    if first_nl >= 0:
        content = content[first_nl:].lstrip("\n")
    return content.strip()


# Pattern for a line that starts a new job entry: contains " | " and year/PRESENT
_JOB_HEADER_RE = re.compile(
    r".+\|.+(?:\d{4}|PRESENT|(?:JAN|FEB|MAR|APR|MAY|JUN|JULY?|AUG|SEP|OCT|NOV|DEC)[A-Za-z]*\s*\d{4})",
    re.IGNORECASE,
)


def _parse_experience_items(content: str) -> list[SectionItem]:
    """Parse experience block into list of SectionItem. Splits by job header lines (Title | Company | Location DATE)."""
    items: list[SectionItem] = []
    lines = [ln.strip() for ln in content.split("\n") if ln.strip()]
    if not lines:
        return items

    # Find indices where a new job starts (line with | and date/PRESENT)
    job_starts: list[int] = []
    for i, line in enumerate(lines):
        if "|" in line and _JOB_HEADER_RE.search(line):
            job_starts.append(i)
    if not job_starts:
        # Fallback: treat first line as single job header, rest as body
        job_starts = [0]

    for j, start in enumerate(job_starts):
        end = job_starts[j + 1] if j + 1 < len(job_starts) else len(lines)
        job_lines = lines[start:end]
        if not job_lines:
            continue
        header = job_lines[0]
        # Parse "Title | Company | Location DATE - DATE" or similar
        parts = [p.strip() for p in re.split(r"\s*\|\s*", header, maxsplit=2)]
        title = parts[0] if parts else header
        company = parts[1] if len(parts) >= 2 else ""
        location_dates = parts[2] if len(parts) >= 3 else ""
        subheading_parts = [p for p in [company, location_dates] if p]
        subheading = " | ".join(subheading_parts) if subheading_parts else ""
        body_lines = job_lines[1:]
        items.append(
            SectionItem(
                heading=title,
                subheading=subheading,
                body="\n".join(body_lines),
            )
        )
    return items


def _parse_education_items(content: str) -> list[SectionItem]:
    """Parse education block into list of SectionItem. First line = degree; second often dates; rest (GPA, bullets) = body."""
    items: list[SectionItem] = []
    blocks = re.split(r"\n\s*\n", content)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        degree = lines[0]
        institution = ""
        dates = ""
        body_lines: list[str] = []
        for line in lines[1:]:
            if re.match(r"^(?:AUGUST|JAN|FEB|MAR|APR|MAY|JUN|JULY?|AUG|SEP|OCT|NOV|DEC)[A-Za-z]*\s*\d{4}\s*[-–]\s*", line, re.IGNORECASE):
                dates = line
            elif re.match(r"^[\d\-\–\s,]+$", line):
                dates = line
            elif not institution and not line.lower().startswith("gpa") and not line.startswith("o "):
                institution = line
            else:
                body_lines.append(line)
        items.append(
            SectionItem(
                heading=degree,
                subheading=f"{institution} ({dates})".strip(" ()") if institution or dates else "",
                body="\n".join(body_lines),
            )
        )
    return items


def _parse_skills_items(content: str) -> list[SectionItem]:
    """Parse skills block into list of SectionItem (body only)."""
    if not content.strip():
        return []
    parts = re.split(r"[,;\n]+", content)
    return [SectionItem(body=p.strip()) for p in parts if p.strip()]


def _extract_contact_from_text(text: str) -> tuple[str, str, str]:
    """Try to get name, email, phone from top of document."""
    name = ""
    email = ""
    phone = ""
    for line in text.split("\n")[:20]:
        line = line.strip()
        if not line:
            continue
        if not name and len(line) < 80 and "@" not in line and not re.search(r"\d{3}[-.\s]?\d{3}[-.\s]?\d{4}", line):
            name = line
        em = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", line)
        if em and not email:
            email = em.group(0)
        ph = re.search(r"[\d\s\-\.\(\)]{10,}", line)
        if ph and not phone and re.search(r"\d{3}", line):
            phone = ph.group(0).strip()
    return name, email, phone


def structure_resume_text(text: str) -> dict:
    """
    Convert raw extracted text into stored parsed_json shape:
    { contact: { name, email, phone }, sections: [ { id, name, order, content_type, text?, items? } ] }
    """
    positions = _find_section_positions(text)
    name, email, phone = _extract_contact_from_text(text)
    contact = ResumeContact(name=name or "", email=email or "", phone=phone or "")

    sections: list[dict] = []
    for i, (pos, key, display_name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        content = _section_content(text, pos, end)
        if not content and key not in ("contact", "contact information"):
            continue

        section_id = str(uuid.uuid4())
        order = i

        if key in ("experience", "work experience", "employment"):
            items = _parse_experience_items(content)
            sections.append({
                "id": section_id,
                "name": display_name,
                "order": order,
                "content_type": "list",
                "text": None,
                "items": [{"heading": it.heading, "subheading": it.subheading, "body": it.body} for it in items],
            })
        elif key == "education":
            items = _parse_education_items(content)
            sections.append({
                "id": section_id,
                "name": display_name,
                "order": order,
                "content_type": "list",
                "text": None,
                "items": [{"heading": it.heading, "subheading": it.subheading, "body": it.body} for it in items],
            })
        elif key == "skills":
            items = _parse_skills_items(content)
            sections.append({
                "id": section_id,
                "name": display_name,
                "order": order,
                "content_type": "list",
                "text": None,
                "items": [{"heading": "", "subheading": "", "body": it.body} for it in items],
            })
        else:
            sections.append({
                "id": section_id,
                "name": display_name,
                "order": order,
                "content_type": "text",
                "text": content,
                "items": [],
            })

    if not sections and text.strip():
        sections.append({
            "id": str(uuid.uuid4()),
            "name": "Summary",
            "order": 0,
            "content_type": "text",
            "text": text.strip(),
            "items": [],
        })

    return {
        "contact": contact.model_dump(),
        "sections": sections,
    }


def parse_pdf_resume(pdf_bytes: bytes) -> dict:
    """
    Extract text from PDF and return stored parsed_json shape (contact + sections).
    Raises ValueError on invalid PDF.
    """
    text = extract_text_from_pdf(pdf_bytes)
    return structure_resume_text(text)
