"""Resume review: call LLM to get improvement suggestions for a resume."""

from __future__ import annotations

import json
import logging
import uuid

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.encryption import decrypt
from app.llm.base import LlmResponse
from app.llm.factory import get_llm_client
from app.llm.prompts import (
    RESUME_REVIEW_SYSTEM_PROMPT,
    build_resume_review_user_content,
)
from app.models.llm_key import LlmKey
from app.schemas.resume import ResumeReviewResponse, ResumeSuggestion

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


def run_resume_review(db: Session, resume_id: uuid.UUID, tenant_id: uuid.UUID) -> ResumeReviewResponse:
    """
    Load resume by id (tenant-scoped), call LLM for suggestions, return validated response.
    Raises ValueError if resume not found, no LLM key, or parsing fails after retries.
    """
    from app.models.resume import Resume

    resume = (
        db.query(Resume)
        .filter(Resume.id == resume_id, Resume.tenant_id == tenant_id)
        .first()
    )
    if not resume:
        raise ValueError("Resume not found")

    llm_key_row = db.query(LlmKey).filter(LlmKey.tenant_id == tenant_id).first()
    if not llm_key_row:
        raise ValueError("Configure an API key in Settings to use resume review")

    try:
        api_key = decrypt(llm_key_row.encrypted_key)
    except Exception:
        logger.exception("Failed to decrypt LLM key for tenant_id=%s", tenant_id)
        raise ValueError("LLM key decryption failed")

    client = get_llm_client(llm_key_row.provider, api_key)
    user_content = build_resume_review_user_content(resume.parsed_json or {})

    last_error: str | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            llm_response: LlmResponse = client.chat_json(
                system_prompt=RESUME_REVIEW_SYSTEM_PROMPT,
                user_content=user_content,
                temperature=0.2,
                max_tokens=2048,
            )
            raw = llm_response.raw_text.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                raw = "\n".join(lines)
            parsed = json.loads(raw)
            result = ResumeReviewResponse.model_validate(parsed)
            return result
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:200]}"
            logger.warning(
                "Resume review parse failed (attempt %d/%d) resume_id=%s: %s",
                attempt, MAX_RETRIES, resume_id, last_error,
            )
            continue
        except Exception as exc:
            last_error = f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:200]}"
            logger.exception(
                "Resume review LLM call failed (attempt %d/%d) resume_id=%s",
                attempt, MAX_RETRIES, resume_id,
            )
            continue

    raise ValueError(
        f"Resume review failed after {MAX_RETRIES} attempts: {last_error or 'unknown'}"
    )
