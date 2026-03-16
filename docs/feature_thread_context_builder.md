# Feature: Thread Context Builder for AI Email Replies

**Source of truth:** `docs/SPEC.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/feature_ai_reply_and_send.md`.

## Overview

The Thread Context Builder improves reply generation quality by providing **structured thread context** to the LLM instead of only the most recent message. When generating a reply draft, the backend builds a context object that includes:

- **Thread context:** Last N messages in the thread (sender, timestamp, body text), in chronological order.
- **Job context:** Company, role, current stage, recruiter/contact info.
- **User context:** User name (or email), tone preference.

This context is formatted into a clear prompt with a **thread summary** section followed by instructions to generate the reply, plus safety rules and a strict JSON output format.

## Context Construction Strategy

1. **Thread messages**
   - Resolve thread(s) for the job via `job_threads` (job_id → thread_id).
   - If `source_message_id` is provided, use that message’s `thread_id`; otherwise use any thread linked to the job.
   - Query messages for that thread, ordered by `date_header` ascending (chronological).
   - Take the **last N messages** (recommended N = 8). Configurable via constant (e.g. `THREAD_CONTEXT_MAX_MESSAGES = 8`).
   - For each message include: sender (`from_address`), timestamp (`date_header`), and body text (stripped of quoted replies, truncated per-message).

2. **Job context**
   - From `Job`: company, role, current_stage.
   - From job contacts: recruiter/contact names and emails (and roles if present).

3. **User context**
   - From authenticated user: display name if available, else email (e.g. `User.email`).
   - Tone: from request (e.g. professional, warm, concise, enthusiastic, direct).

4. **Order in prompt**
   - First: structured thread summary (recent messages, chronological).
   - Then: job + recipient info, user/tone, optional user instruction.
   - Then: instruction to generate reply and safety rules.
   - Finally: strict JSON output format.

## Backend Changes

- **New module:** `app/services/thread_context_builder.py`
  - `build_reply_context(db, tenant_id, job_id, source_message_id, tone, user_instruction, user_email)` → structured context dict (or a small dataclass/Pydantic model) containing:
    - `thread_messages`: list of `{ sender, timestamp, body_text }` (last N, chronological).
    - `job_company`, `job_role`, `job_stage`, `recipient_info`.
    - `user_name` (or email), `tone`, `user_instruction`.
  - Uses existing models: `Message`, `Job`, `JobThread`, `Contact`, `JobContact`, `User` (for email/name). No new tables.

- **Reply generation integration:** `app/services/reply_generation.py`
  - Call the context builder to get structured context.
  - Build user prompt from context: thread summary first, then job/user/tone/instruction, then “generate reply” + safety rules.
  - Keep using existing BYOK LLM and `REPLY_GENERATION_SYSTEM_PROMPT` (updated to reflect new structure and output format).

- **Prompts:** `app/llm/prompts.py`
  - New helper (e.g. `build_reply_user_content_from_context(context)`) that takes the structured context and produces the user message with:
    - “Thread summary:” block (list of recent messages).
    - “Job / Recipient:” block.
    - “User / Tone:” block.
    - “User instruction:” (if any).
    - “Generate a reply…” with safety rules.
    - “Output strict JSON: { subject, body, tone, confidence }.”

- **Schema:** `app/schemas/draft.py`
  - `DraftReplyResult`: add optional `tone` and `confidence` (float) so LLM can return them; existing callers can ignore if not needed.

## Limits for Context Size

- **Message count:** Last **8** messages in the thread (configurable constant). Avoids token explosion on long threads.
- **Per-message body length:** Truncate each message body to **800** characters (after stripping quoted replies). Prevents a single long email from dominating the context.
- **Total thread summary:** Soft cap ~6,400 characters (8 × 800) for thread bodies; plus sender/timestamp lines. No hard total cap; truncation per message is the main control.
- **Recipient / job block:** Use existing recipient list; no extra limit beyond reasonable contact count.
- **User instruction:** Already limited in API (e.g. 1000 chars in `DraftReplyRequest`).

Constants (in context builder or prompts):

- `THREAD_CONTEXT_MAX_MESSAGES = 8`
- `THREAD_MESSAGE_BODY_MAX_CHARS = 800`

## Prompt Format Design

1. **System prompt (existing, updated)**
   - Role: draft email replies for job-seeker correspondence.
   - Output: **only** a JSON object with exactly: `subject`, `body`, `tone`, `confidence` (number).
   - Safety: do not invent facts; do not promise availability unless explicitly given; keep replies concise and professional.
   - No markdown/code fences.

2. **User message structure**
   - **Thread summary**  
     “Recent messages in this thread (chronological):”  
     For each message: “From: … | Date: … | Body: …” (body truncated).
   - **Job context**  
     “Job: company=…, role=…, current_stage=…”  
     “Recipient: …” (contact list).
   - **User / tone**  
     “User: …” (name or email), “Tone: …”.
   - **User instruction** (if any)  
     “User instruction: …”.
   - **Task**  
     “Generate a short professional reply based on the thread above. Follow the user instruction if provided.”
   - **Safety**  
     “Do not invent facts. Do not promise specific times or availability unless explicitly given. Keep the reply concise and professional.”
   - **Output**  
     “Return only valid JSON: { \"subject\": \"...\", \"body\": \"...\", \"tone\": \"...\", \"confidence\": number }.”

## Edge Cases

- **No thread / no messages:** Job has no `job_threads` or thread has no messages. Context builder returns empty `thread_messages`; prompt still includes job + recipient + user/tone; instruction says “compose a short professional reply for this job” (same as current no-message behavior).
- **No source_message_id:** Use any thread linked to the job; if multiple threads, pick one (e.g. most recent activity) or merge; document “pick one thread” for v1.
- **Source message not in job thread:** If `source_message_id` points to a message whose `thread_id` is not in `job_threads`, still use that message’s thread for “last N messages” so we don’t drop user intent; optionally link thread to job in a follow-up.
- **Very long bodies:** Per-message truncation (800 chars) plus last-8-messages limit keeps context bounded.
- **Missing date_header:** Show “(no date)” for timestamp; still include message.
- **No user name:** Use email from `User.email` as “User: …”.
- **No BYOK / no job / no account:** Unchanged from current behavior (reply_generation and drafts router already handle these).

## Testing Plan

- **Unit: Thread context builder**
  - Build context for job with thread and 3 messages: assert last N messages, chronological order, sender/timestamp/body present; body truncated to 800.
  - Build context with no thread: assert `thread_messages` empty, job and recipient still present.
  - Build context with source_message_id in a different thread: assert that thread is used for message list.
  - Build context with > 8 messages: assert only last 8 returned.

- **Unit: Reply generation with context**
  - Mock LLM; call `generate_reply` with job that has thread + messages; assert user content contains “Thread summary”, list of messages, job stage, recipient, tone; assert output parsed to DraftReplyResult (subject, body, tone, confidence).

- **Unit: Prompt format**
  - Build user content from structured context; assert thread summary appears first; assert safety rules and JSON shape described; assert no API keys or tenant IDs.

- **Integration**
  - POST `/jobs/{id}/draft-reply` with job that has multiple thread messages; assert draft created and (if possible) body is contextually relevant; assert generation_context_json includes thread snapshot (or message count).

- **Regression**
  - Existing draft-reply and send tests still pass (DraftReplyResult backward compat: subject/body required; tone/confidence optional).

## Summary

| Area | Decision |
|------|----------|
| **Thread context** | Last 8 messages (chronological), sender + timestamp + body (800 chars/message). |
| **Job context** | Company, role, stage, recruiter/contact info. |
| **User context** | User email (or name if added later), tone from request. |
| **Prompt order** | Thread summary → Job/recipient → User/tone → Instruction → Generate reply + safety → JSON format. |
| **Safety** | No inventing facts; no promising availability unless given; concise and professional. |
| **Output** | Strict JSON: `subject`, `body`, `tone`, `confidence`. |
| **Limits** | 8 messages, 800 chars per body; no new DB tables. |
