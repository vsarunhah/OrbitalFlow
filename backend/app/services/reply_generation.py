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
from app.services.user_profile import get_or_create_profile

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
        "user_timezone": ctx.user_timezone,
        "user_profile_summary": ctx.user_profile_summary,
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


EXPECTED_VARIANT_IDS = ("concise", "warm", "enthusiastic", "reject")

_VARIANT_ID_ALIASES = {
    "short": "concise",
    "brief": "concise",
    "friendly": "warm",
    "decline": "reject",
    "declined": "reject",
    "pass": "reject",
    "polite_decline": "reject",
    "polite decline": "reject",
}


def _resolve_variant_id(value: object, index: int) -> str | None:
    """Map LLM variant_id/tone values to canonical ids."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        if 1 <= value <= len(EXPECTED_VARIANT_IDS):
            return EXPECTED_VARIANT_IDS[value - 1]
        if 0 <= value < len(EXPECTED_VARIANT_IDS):
            return EXPECTED_VARIANT_IDS[value]
    text = str(value).strip().lower()
    if text in EXPECTED_VARIANT_IDS:
        return text
    if text in _VARIANT_ID_ALIASES:
        return _VARIANT_ID_ALIASES[text]
    if text.isdigit():
        number = int(text)
        if 1 <= number <= len(EXPECTED_VARIANT_IDS):
            return EXPECTED_VARIANT_IDS[number - 1]
        if 0 <= number < len(EXPECTED_VARIANT_IDS):
            return EXPECTED_VARIANT_IDS[number]
    return None


def normalize_reply_variant(raw: dict, index: int) -> dict:
    """Coerce one raw LLM variant object before schema validation."""
    data = dict(raw)
    variant_id = _resolve_variant_id(data.get("variant_id"), index)
    if variant_id is None:
        variant_id = _resolve_variant_id(data.get("tone"), index)
    if variant_id is None and index < len(EXPECTED_VARIANT_IDS):
        variant_id = EXPECTED_VARIANT_IDS[index]
    data["variant_id"] = variant_id

    tone = _resolve_variant_id(data.get("tone"), index) or variant_id
    data["tone"] = tone

    confidence = data.get("confidence")
    if confidence is not None:
        try:
            data["confidence"] = float(confidence)
        except (TypeError, ValueError):
            data["confidence"] = None

    return data


def parse_reply_variants(raw_variants: object) -> list[ReplyVariantSchema]:
    """Validate LLM variant output, tolerating numeric or positional variant_id values."""
    if not isinstance(raw_variants, list) or len(raw_variants) < len(EXPECTED_VARIANT_IDS):
        raise ValueError(
            f"Agent output missing 'variants' array with {len(EXPECTED_VARIANT_IDS)} items"
        )

    normalized: list[dict] = []
    for index, item in enumerate(raw_variants[: len(EXPECTED_VARIANT_IDS)]):
        if not isinstance(item, dict):
            raise ValueError(f"Variant at index {index} must be an object")
        normalized.append(normalize_reply_variant(item, index))

    validated = [ReplyVariantSchema.model_validate(item) for item in normalized]
    seen = {variant.variant_id for variant in validated}
    if seen != set(EXPECTED_VARIANT_IDS):
        validated = [
            variant.model_copy(
                update={
                    "variant_id": EXPECTED_VARIANT_IDS[index],
                    "tone": EXPECTED_VARIANT_IDS[index],
                }
            )
            for index, variant in enumerate(validated)
        ]

    order = {variant_id: index for index, variant_id in enumerate(EXPECTED_VARIANT_IDS)}
    return sorted(validated, key=lambda variant: order.get(variant.variant_id, 99))


def generate_reply_variants(
    db: Session,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    source_message_id: uuid.UUID | None,
    user_instruction: str | None,
    user_email: str | None = None,
    user_id: uuid.UUID | None = None,
) -> tuple[list[ReplyVariantSchema], dict]:
    """
    Build context, run agentic generation for 4 variants (concise, warm, enthusiastic, reject).
    Raises ValueError if no LLM key, job not found, or generation fails.
    """
    context_snapshot = {
        "job_id": str(job_id),
        "job_stage": None,
        "source_message_id": str(source_message_id) if source_message_id else None,
        "user_instruction": (user_instruction[:500] if user_instruction else None),
        "thread_message_count": 0,
        "agentic": True,
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
    if user_id is None:
        raise ValueError("user_id is required for reply generation")

    profile = get_or_create_profile(db, user_id, tenant_id)
    last_error: str | None = None
    variants_result: list[ReplyVariantSchema] | None = None

    from app.services.reply_agent import run_agentic_reply_variants

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            variants_result = run_agentic_reply_variants(
                client,
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                job_id=job_id,
                source_message_id=source_message_id,
                user_instruction=user_instruction,
                user_email=user_email,
                default_timezone=profile.timezone,
            )
            ctx = build_reply_context(
                db=db,
                tenant_id=tenant_id,
                job_id=job_id,
                source_message_id=source_message_id,
                tone="professional",
                user_instruction=user_instruction,
                user_email=user_email,
                user_id=user_id,
            )
            context_snapshot["job_stage"] = ctx.job_stage
            context_snapshot["thread_message_count"] = len(ctx.thread_messages)
            break
        except (ValidationError, ValueError) as exc:
            last_error = f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:200]}"
            logger.warning(
                "Agentic reply variants failed (attempt %d/%d) job_id=%s: %s",
                attempt, MAX_RETRIES, job_id, last_error,
            )
            continue
        except Exception as exc:
            last_error = f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:200]}"
            logger.exception(
                "Agentic reply variants failed (attempt %d/%d) job_id=%s",
                attempt, MAX_RETRIES, job_id,
            )
            continue

    if variants_result is None:
        raise ValueError(
            f"Reply variants generation failed after {MAX_RETRIES} attempts: {last_error or 'unknown'}"
        )

    return variants_result, context_snapshot
