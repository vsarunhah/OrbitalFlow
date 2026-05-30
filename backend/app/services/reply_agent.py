"""Agentic reply draft generation with tool use (profile, calendar)."""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy.orm import Session

from app.llm.base import LlmClient
from app.llm.prompts import (
    REPLY_AGENT_FINAL_USER_INSTRUCTION,
    REPLY_AGENT_SYSTEM_PROMPT,
    build_reply_multi_variant_user_content,
)
from app.schemas.draft import ReplyVariantSchema
from app.services.reply_agent_tools import REPLY_AGENT_TOOLS, execute_reply_agent_tool
from app.services.reply_generation import parse_reply_variants, _context_to_dict
from app.services.thread_context_builder import build_reply_context

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6


def run_agentic_reply_variants(
    client: LlmClient,
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    source_message_id: uuid.UUID | None,
    user_instruction: str | None,
    user_email: str | None,
    default_timezone: str | None,
) -> list[ReplyVariantSchema]:
    """
    Run tool-augmented LLM loop, then a final JSON call for four variants.
    Raises ValueError on failure.
    """
    if not hasattr(client, "chat_with_messages"):
        raise ValueError("LLM provider does not support agentic draft generation")

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
    user_content = build_reply_multi_variant_user_content(_context_to_dict(ctx))
    messages: list[dict] = [
        {"role": "system", "content": REPLY_AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        assistant = client.chat_with_messages(
            messages,
            tools=REPLY_AGENT_TOOLS,
            temperature=0.3,
            max_tokens=3072,
        )
        assistant_msg = _assistant_message_dict(assistant)
        messages.append(assistant_msg)

        if not assistant.tool_calls:
            logger.debug("Agent finished tool loop at round %d (no tool calls)", round_num)
            break

        for tc in assistant.tool_calls:
            result = execute_reply_agent_tool(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                job_id=job_id,
                name=tc.name,
                arguments_json=tc.arguments,
                default_timezone=default_timezone or ctx.user_timezone,
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                }
            )

    messages.append({"role": "user", "content": REPLY_AGENT_FINAL_USER_INSTRUCTION})

    final = client.chat_with_messages(
        messages,
        tools=None,
        temperature=0.3,
        max_tokens=3072,
        response_format_json=True,
    )
    raw = (final.content or "").strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent final JSON parse failed: {exc}") from exc

    raw_variants = parsed.get("variants")
    return parse_reply_variants(raw_variants)


def _assistant_message_dict(assistant) -> dict:
    msg: dict = {
        "role": "assistant",
        "content": assistant.content,
    }
    if assistant.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": tc.arguments},
            }
            for tc in assistant.tool_calls
        ]
    return msg
