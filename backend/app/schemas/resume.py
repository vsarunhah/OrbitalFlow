"""Pydantic schemas for resume upload, CRUD, review suggestions, and export."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# --------------- Parsed resume structure (stored in parsed_json) ---------------

class ResumeContact(BaseModel):
    """Top-of-resume contact block."""
    name: str = ""
    email: str = ""
    phone: str = ""


class SectionItem(BaseModel):
    """One entry in a list-type section (e.g. experience item, education item, skill)."""
    heading: str = ""
    subheading: str = ""
    body: str = ""


class ResumeSection(BaseModel):
    """A configurable section: named, ordered, with text or list content."""
    id: str = ""
    name: str = ""
    order: int = 0
    content_type: str = "text"  # "text" | "list"
    text: str | None = None
    items: list[SectionItem] = Field(default_factory=list)


class ParsedResume(BaseModel):
    """Structured content: contact + ordered configurable sections."""
    contact: ResumeContact = Field(default_factory=ResumeContact)
    sections: list[ResumeSection] = Field(default_factory=list)

    @classmethod
    def from_parsed_json(cls, data: dict) -> "ParsedResume":
        """Build ParsedResume from stored parsed_json (supports legacy flat shape)."""
        if not data:
            return cls()
        if "sections" in data and isinstance(data.get("sections"), list):
            contact = ResumeContact(
                name=(data.get("contact") or {}).get("name", "") or data.get("name", ""),
                email=(data.get("contact") or {}).get("email", "") or data.get("email", ""),
                phone=(data.get("contact") or {}).get("phone", "") or data.get("phone", ""),
            )
            sections = []
            for s in data["sections"]:
                if isinstance(s, dict):
                    items = []
                    for it in (s.get("items") or []):
                        if isinstance(it, dict):
                            items.append(SectionItem(
                                heading=it.get("heading", ""),
                                subheading=it.get("subheading", ""),
                                body=it.get("body", ""),
                            ))
                    sections.append(ResumeSection(
                        id=str(s.get("id", "")),
                        name=str(s.get("name", "")),
                        order=int(s.get("order", len(sections))),
                        content_type=s.get("content_type", "text"),
                        text=s.get("text"),
                        items=items,
                    ))
            sections.sort(key=lambda x: x.order)
            return cls(contact=contact, sections=sections)
        # Legacy shape: name, email, phone, summary, experience, education, skills
        contact = ResumeContact(
            name=str(data.get("name", "")),
            email=str(data.get("email", "")),
            phone=str(data.get("phone", "")),
        )
        sections = []
        order = 0
        if data.get("summary"):
            sections.append(ResumeSection(id="summary", name="Summary", order=order, content_type="text", text=data["summary"]))
            order += 1
        exp_list = data.get("experience") or []
        if exp_list:
            items = [
                SectionItem(
                    heading=e.get("title", "") if isinstance(e, dict) else "",
                    subheading=f"{e.get('company', '')} ({e.get('dates', '')})".strip(" ()") if isinstance(e, dict) else "",
                    body=e.get("description", "") if isinstance(e, dict) else "",
                )
                for e in exp_list if isinstance(e, dict)
            ]
            sections.append(ResumeSection(id="experience", name="Experience", order=order, content_type="list", items=items))
            order += 1
        edu_list = data.get("education") or []
        if edu_list:
            items = [
                SectionItem(
                    heading=e.get("degree", "") if isinstance(e, dict) else "",
                    subheading=f"{e.get('institution', '')} ({e.get('dates', '')})".strip(" ()") if isinstance(e, dict) else "",
                    body="",
                )
                for e in edu_list if isinstance(e, dict)
            ]
            sections.append(ResumeSection(id="education", name="Education", order=order, content_type="list", items=items))
            order += 1
        if data.get("skills"):
            sk = data["skills"]
            items = [SectionItem(body=str(s)) for s in (sk if isinstance(sk, list) else [sk])]
            sections.append(ResumeSection(id="skills", name="Skills", order=order, content_type="list", items=items))
        return cls(contact=contact, sections=sections)


# Legacy shape (for backward compatibility when reading old parsed_json)
class ExperienceItem(BaseModel):
    title: str = ""
    company: str = ""
    dates: str = ""
    description: str = ""


class EducationItem(BaseModel):
    degree: str = ""
    institution: str = ""
    dates: str = ""


# --------------- API request / response ---------------

class ResumeCreate(BaseModel):
    """Set after upload/parse; not a direct request body."""
    name: str
    original_filename: str | None = None
    parsed_json: dict  # ParsedResume-compatible dict


class ResumeUpdate(BaseModel):
    """Request body for PATCH /resumes/{id}."""
    name: str | None = Field(None, max_length=255)
    parsed_json: dict | None = None


class ResumeManualCreate(BaseModel):
    """Request body for POST /resumes — create a resume from Markdown (+ optional structured form)."""
    name: str = Field(..., min_length=1, max_length=255)
    markdown: str = Field(default="", max_length=500_000)
    source_form: dict | None = None


class ResumeSchema(BaseModel):
    """Resume as returned by API."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by_user_id: uuid.UUID
    name: str
    original_filename: str | None
    parsed_json: dict
    created_at: datetime
    updated_at: datetime


class ResumeListItem(BaseModel):
    """Summary for list endpoint."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    updated_at: datetime


# --------------- Review / suggestions (LLM response) ---------------

class ResumeSuggestion(BaseModel):
    """One improvement suggestion from the review endpoint."""
    section: str = Field(description="e.g. summary, experience[0].description, skills")
    suggestion_type: str = Field(description="e.g. wording, add_detail, ats_friendly, consistency, missing")
    current_value: str | None = Field(None, description="Excerpt of current content")
    suggested_value: str | None = Field(None, description="Replacement or instruction")
    comment: str = Field(description="Short reason for the suggestion")


class ResumeReviewResponse(BaseModel):
    """Response from POST /resumes/{id}/review."""
    suggestions: list[ResumeSuggestion] = Field(default_factory=list)
