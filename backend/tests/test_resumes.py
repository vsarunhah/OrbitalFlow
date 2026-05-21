"""Tests for resume upload, CRUD, review, and export."""

import io
import uuid

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _minimal_pdf_bytes():
    """Create minimal valid PDF with one page and some text (for upload test)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 700, "John Doe")
    c.drawString(100, 680, "john@example.com")
    c.drawString(100, 660, "Summary: Software engineer with 5 years experience.")
    c.drawString(100, 620, "Experience")
    c.drawString(100, 600, "Senior Engineer at Acme (2020-2024)")
    c.save()
    return buf.getvalue()


def test_list_resumes_empty(client, auth_header):
    r = client.get("/resumes", headers=auth_header)
    assert r.status_code == 200
    assert r.json() == []


def test_upload_resume_rejects_non_pdf(client, auth_header):
    r = client.post(
        "/resumes/upload",
        headers=auth_header,
        files={"file": ("resume.txt", io.BytesIO(b"not a pdf"), "text/plain")},
    )
    assert r.status_code == 400
    assert "PDF" in r.json().get("detail", "")


def test_upload_resume_success(client, auth_header):
    pdf = _minimal_pdf_bytes()
    r = client.post(
        "/resumes/upload",
        headers=auth_header,
        files={"file": ("resume.pdf", io.BytesIO(pdf), "application/pdf")},
    )
    assert r.status_code == 200
    data = r.json()
    assert "id" in data
    assert data["name"]
    assert "parsed_json" in data
    assert data["tenant_id"]


def test_get_resume_not_found(client, auth_header):
    r = client.get(f"/resumes/{uuid.uuid4()}", headers=auth_header)
    assert r.status_code == 404


def test_list_resumes_requires_auth(client):
    r = client.get("/resumes")
    assert r.status_code == 401


def test_create_resume_stores_optional_source_form(client, auth_header):
    form = {
        "contact": {"name": "Ada", "email": "ada@example.com", "phone": ""},
        "sections": [],
    }
    r = client.post(
        "/resumes",
        headers=auth_header,
        json={"name": "CV", "markdown": "# Ada\n", "source_form": form},
    )
    assert r.status_code == 200
    assert r.json()["parsed_json"]["source_form"] == form


def test_create_resume_markdown_and_export(client, auth_header):
    r = client.post(
        "/resumes",
        headers=auth_header,
        json={"name": "My CV", "markdown": "# Jane Doe\n\njane@example.com\n\n## Summary\n\nEngineer."},
    )
    assert r.status_code == 200
    resume_id = r.json()["id"]
    assert r.json()["parsed_json"]["format"] == "markdown"

    export_r = client.get(f"/resumes/{resume_id}/export", headers=auth_header)
    assert export_r.status_code == 200
    assert export_r.headers.get("content-type", "").startswith("application/pdf")
    assert len(export_r.content) > 100


def test_resume_crud_and_export(client, auth_header):
    r = client.post(
        "/resumes",
        headers=auth_header,
        json={"name": "resume.pdf", "markdown": "# John Doe\n\nSummary here."},
    )
    assert r.status_code == 200
    resume_id = r.json()["id"]

    # List
    list_r = client.get("/resumes", headers=auth_header)
    assert list_r.status_code == 200
    assert len(list_r.json()) >= 1
    assert any(str(item["id"]) == str(resume_id) for item in list_r.json())

    # Get
    get_r = client.get(f"/resumes/{resume_id}", headers=auth_header)
    assert get_r.status_code == 200
    assert get_r.json()["id"] == resume_id

    # Update
    patch_r = client.patch(
        f"/resumes/{resume_id}",
        headers=auth_header,
        json={"name": "Updated Name", "parsed_json": get_r.json()["parsed_json"]},
    )
    assert patch_r.status_code == 200
    assert patch_r.json()["name"] == "Updated Name"

    # Export PDF
    export_r = client.get(f"/resumes/{resume_id}/export", headers=auth_header)
    assert export_r.status_code == 200
    assert export_r.headers.get("content-type", "").startswith("application/pdf")
    assert len(export_r.content) > 100

    # Delete
    del_r = client.delete(f"/resumes/{resume_id}", headers=auth_header)
    assert del_r.status_code == 204

    get_after = client.get(f"/resumes/{resume_id}", headers=auth_header)
    assert get_after.status_code == 404


def test_review_resume_not_found(client, auth_header):
    r = client.post(f"/resumes/{uuid.uuid4()}/review", headers=auth_header)
    assert r.status_code == 404


def test_review_resume_no_llm_key_returns_400(client, auth_header):
    pdf = _minimal_pdf_bytes()
    upload = client.post(
        "/resumes/upload",
        headers=auth_header,
        files={"file": ("resume.pdf", io.BytesIO(pdf), "application/pdf")},
    )
    assert upload.status_code == 200
    resume_id = upload.json()["id"]

    # No LLM key configured -> 400
    r = client.post(f"/resumes/{resume_id}/review", headers=auth_header)
    assert r.status_code == 400
    assert "API key" in r.json().get("detail", "") or "Configure" in r.json().get("detail", "")
