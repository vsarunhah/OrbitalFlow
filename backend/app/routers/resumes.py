"""Resumes API: upload PDF, CRUD, review (AI suggestions), export PDF."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.database import get_db
from app.models.resume import Resume
from app.schemas.resume import (
    ParsedResume,
    ResumeListItem,
    ResumeReviewResponse,
    ResumeSchema,
    ResumeUpdate,
)
from app.services.resume_parser import parse_pdf_resume
from app.services.resume_pdf import build_pdf
from app.services.resume_review import run_resume_review

router = APIRouter(prefix="/resumes", tags=["resumes"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/upload", response_model=ResumeSchema)
async def upload_resume(
    file: UploadFile = File(...),
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a PDF resume: parse and create. Use multipart/form-data with key 'file'."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted",
        )
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 10 MB limit",
        )
    try:
        parsed_json = parse_pdf_resume(content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    name = file.filename.replace(".pdf", "")[:255] if file.filename else "Untitled"
    resume = Resume(
        tenant_id=auth.tenant_id,
        created_by_user_id=auth.user_id,
        name=name,
        original_filename=file.filename[:512] if file.filename else None,
        parsed_json=parsed_json,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return ResumeSchema.model_validate(resume)


@router.get("", response_model=list[ResumeListItem])
def list_resumes(
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List resumes for the current tenant."""
    rows = (
        db.query(Resume)
        .filter(Resume.tenant_id == auth.tenant_id)
        .order_by(Resume.updated_at.desc())
        .all()
    )
    return [ResumeListItem.model_validate(r) for r in rows]


@router.get("/{resume_id}", response_model=ResumeSchema)
def get_resume(
    resume_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get one resume by id (tenant-scoped)."""
    resume = (
        db.query(Resume)
        .filter(Resume.id == resume_id, Resume.tenant_id == auth.tenant_id)
        .first()
    )
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found",
        )
    return ResumeSchema.model_validate(resume)


@router.patch("/{resume_id}", response_model=ResumeSchema)
def update_resume(
    resume_id: uuid.UUID,
    body: ResumeUpdate,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update resume name and/or parsed_json."""
    resume = (
        db.query(Resume)
        .filter(Resume.id == resume_id, Resume.tenant_id == auth.tenant_id)
        .first()
    )
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found",
        )
    if body.name is not None:
        resume.name = body.name
    if body.parsed_json is not None:
        resume.parsed_json = body.parsed_json
    db.commit()
    db.refresh(resume)
    return ResumeSchema.model_validate(resume)


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(
    resume_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a resume."""
    resume = (
        db.query(Resume)
        .filter(Resume.id == resume_id, Resume.tenant_id == auth.tenant_id)
        .first()
    )
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found",
        )
    db.delete(resume)
    db.commit()
    return None


@router.post("/{resume_id}/review", response_model=ResumeReviewResponse)
def review_resume(
    resume_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get AI improvement suggestions for the resume (requires LLM key in Settings)."""
    try:
        return run_resume_review(db, resume_id, auth.tenant_id)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resume not found",
            )
        if "configure" in str(e).lower() or "key" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Configure an API key in Settings to use resume review",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{resume_id}/export")
def export_resume_pdf(
    resume_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate and download PDF for the resume."""
    resume = (
        db.query(Resume)
        .filter(Resume.id == resume_id, Resume.tenant_id == auth.tenant_id)
        .first()
    )
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found",
        )
    try:
        parsed = ParsedResume.from_parsed_json(resume.parsed_json or {})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid resume content; cannot generate PDF",
        )
    pdf_bytes = build_pdf(parsed)
    filename = (resume.name or "resume").replace(" ", "_") + ".pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
