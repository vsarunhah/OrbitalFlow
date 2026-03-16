"""Generate suggested email reply using tenant BYOK LLM. No sending; draft only."""

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
    REPLY_GENERATION_SYSTEM_PROMPT,
    REPLY_MULTI_VARIANT_SYSTEM_PROMPT,
    build_reply_multi_variant_user_content,
    build_reply_user_content_from_context,
)
from app.models.job import Job
from app.models.llm_key import LlmKey
from app.schemas.draft import DraftReplyResult, ReplyVariantSchema
from app.services.thread_context_builder import ReplyContext, build_reply_context

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


def _context_to_dict(ctx: ReplyContext) -> dict:
    """Convert ReplyContext to dict for prompt builder."""
    thread_messages = [
        {"sender": m.sender, "timestamp": m.timestamp, "body_text": m.body_text}
        for m in ctx.thread_messages
    ]
    return {
        "thread_messages": thread_messages,
        "job_company": ctx.job_company,
        "job_role": ctx.job_role,
        "job_stage": ctx.job_stage,
        "recipient_info": ctx.recipient_info,
        "user_name": ctx.user_name,
        "tone": ctx.tone,
        "user_instruction": ctx.user_instruction,
    }


def generate_reply(
    db: Session,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    source_message_id: uuid.UUID | None,
    tone: str,
    user_instruction: str | None,
    user_email: str | None = None,
) -> tuple[DraftReplyResult, dict]:
    """
    Build structured thread/job/user context, call LLM, return subject+body+tone+confidence and context snapshot.
    Raises ValueError if no LLM key, job not found, or generation fails.
    """
    ctx = build_reply_context(
        db=db,
        tenant_id=tenant_id,
        job_id=job_id,
        source_message_id=source_message_id,
        tone=tone,
        user_instruction=user_instruction,
        user_email=user_email,
    )
    user_content = build_reply_user_content_from_context(_context_to_dict(ctx))

    # Context snapshot for storage (no huge bodies)
    context_snapshot = {
        "job_id": str(job_id),
        "job_stage": ctx.job_stage,
        "source_message_id": str(source_message_id) if source_message_id else None,
        "tone": ctx.tone,
        "user_instruction": (ctx.user_instruction[:500] if ctx.user_instruction else None),
        "thread_message_count": len(ctx.thread_messages),
    }

    llm_key_row = db.query(LlmKey).filter(LlmKey.tenant_id == tenant_id).first()
    if not llm_key_row:
        raise ValueError("LLM key not configured for this tenant")

    try:
        api_key = decrypt(llm_key_row.encrypted_key)
    except Exception:
        logger.exception("Failed to decrypt LLM key for tenant_id=%s", tenant_id)
        raise ValueError("LLM key decryption failed")

    client = get_llm_client(llm_key_row.provider, api_key)
    result: DraftReplyResult | None = None
    last_error: str | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            llm_response: LlmResponse = client.chat_json(
                system_prompt=REPLY_GENERATION_SYSTEM_PROMPT,
                user_content=user_content,
                temperature=0.3,
                max_tokens=1024,
            )
            raw = llm_response.raw_text.strip()
            # Strip markdown code fence if present
            if raw.startswith("```"):
                lines = raw.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                raw = "\n".join(lines)
            parsed = json.loads(raw)
            result = DraftReplyResult.model_validate(parsed)
            break
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:200]}"
            logger.warning(
                "Reply generation parse failed (attempt %d/%d) job_id=%s: %s",
                attempt, MAX_RETRIES, job_id, last_error,
            )
            continue
        except Exception as exc:
            last_error = f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:200]}"
            logger.exception(
                "Reply generation LLM call failed (attempt %d/%d) job_id=%s",
                attempt, MAX_RETRIES, job_id,
            )
            continue

    if result is None:
        raise ValueError(
            f"Reply generation failed after {MAX_RETRIES} attempts: {last_error or 'unknown'}"
        )

    if result.confidence is not None:
        context_snapshot["confidence"] = result.confidence
    return result, context_snapshot


EXPECTED_VARIANT_IDS = ("concise", "warm", "enthusiastic")


def generate_reply_variants(
    db: Session,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    source_message_id: uuid.UUID | None,
    user_instruction: str | None,
    user_email: str | None = None,
) -> tuple[list[ReplyVariantSchema], dict]:
    """
    Build context, call LLM once for 3 variants (concise, warm, enthusiastic), return validated variants and context snapshot.
    Raises ValueError if no LLM key, job not found, or generation fails.
    """
    ctx = build_reply_context(
        db=db,
        tenant_id=tenant_id,
        job_id=job_id,
        source_message_id=source_message_id,
        tone="professional",
        user_instruction=user_instruction,
        user_email=user_email,
    )
    user_content = build_reply_multi_variant_user_content(_context_to_dict(ctx))

    context_snapshot = {
        "job_id": str(job_id),
        "job_stage": ctx.job_stage,
        "source_message_id": str(source_message_id) if source_message_id else None,
        "user_instruction": (ctx.user_instruction[:500] if ctx.user_instruction else None),
        "thread_message_count": len(ctx.thread_messages),
    }

    llm_key_row = db.query(LlmKey).filter(LlmKey.tenant_id == tenant_id).first()
    if not llm_key_row:
        raise ValueError("LLM key not configured for this tenant")

    try:
        api_key = decrypt(llm_key_row.encrypted_key)
    except Exception:
        logger.exception("Failed to decrypt LLM key for tenant_id=%s", tenant_id)
        raise ValueError("LLM key decryption failed")

    client = get_llm_client(llm_key_row.provider, api_key)
    variants_result: list[ReplyVariantSchema] | None = None
    last_error: str | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            llm_response: LlmResponse = client.chat_json(
                system_prompt=REPLY_MULTI_VARIANT_SYSTEM_PROMPT,
                user_content=user_content,
                temperature=0.3,
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
            raw_variants = parsed.get("variants")
            if not isinstance(raw_variants, list) or len(raw_variants) < 3:
                last_error = f"attempt {attempt}: expected 'variants' array with at least 3 items"
                continue
            validated = [ReplyVariantSchema.model_validate(v) for v in raw_variants[:3]]
            seen = {v.variant_id for v in validated}
            if seen != set(EXPECTED_VARIANT_IDS):
                last_error = f"attempt {attempt}: variant_id must be concise, warm, enthusiastic; got {seen}"
                continue
            order = {vid: i for i, vid in enumerate(EXPECTED_VARIANT_IDS)}
            variants_result = sorted(validated, key=lambda v: order.get(v.variant_id, 99))
            break
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:200]}"
            logger.warning(
                "Multi-variant reply parse failed (attempt %d/%d) job_id=%s: %s",
                attempt, MAX_RETRIES, job_id, last_error,
            )
            continue
        except Exception as exc:
            last_error = f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:200]}"
            logger.exception(
                "Multi-variant reply LLM call failed (attempt %d/%d) job_id=%s",
                attempt, MAX_RETRIES, job_id,
            )
            continue

    if variants_result is None:
        raise ValueError(
            f"Reply variants generation failed after {MAX_RETRIES} attempts: {last_error or 'unknown'}"
        )

    return variants_result, context_snapshot
