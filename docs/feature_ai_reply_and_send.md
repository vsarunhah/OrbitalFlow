# Feature: AI Reply Suggestions + Send from App

**Source of truth:** `docs/SPEC.md`, `docs/IMPLEMENTATION_PLAN.md`.

## Overview

Allow the user to generate a suggested email reply for a job-related message/thread, edit it inside the app, and explicitly send it using the connected Gmail account. The feature is **human-in-the-loop**: we never auto-send; the user must review and/or edit before sending. All sent messages are logged in the app and reflected in the job timeline.

## V1 Scope

- **Suggest Reply**: From job detail/timeline, user clicks “Suggest Reply”. Backend generates a draft using thread/message context, job stage, recruiter/contact info, and optional user instruction (e.g. “say I’m interested”, “ask for compensation range”).
- **Edit draft**: User can edit subject and body in the app before sending.
- **Send**: User clicks Send; backend sends via the connected Gmail account, replying in-thread when possible. Sent message is stored and a job event (e.g. `REPLY_SENT`) is added to the timeline.
- **Timeline**: Sent replies appear in the job timeline so the user sees a complete audit.

Out of scope for v1: Gmail draft sync (create/update Gmail drafts in the Gmail UI), attachments, multiple recipients beyond To/Cc derived from thread.

---

## Data Model Changes

### message_drafts

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| tenant_id | UUID | FK tenants, not null |
| job_id | UUID | FK jobs, not null |
| source_message_id | UUID | FK messages, nullable — message we’re replying to (if any) |
| account_id | UUID | FK email_accounts, not null — account used to send |
| draft_type | String(32) | e.g. "reply" |
| subject | Text | nullable |
| body_text | Text | nullable |
| tone | String(32) | e.g. professional, warm, concise, enthusiastic, direct |
| status | String(32) | GENERATED, EDITED, SENT, FAILED |
| generation_context_json | Text | nullable — snapshot of context used for LLM (thread snippets, job, etc.) |
| created_by_user_id | UUID | FK users, not null |
| created_at | Timestamptz | |
| updated_at | Timestamptz | |

Indexes: `tenant_id`, `job_id`, `(tenant_id, status)` for listing.

### sent_messages

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| tenant_id | UUID | FK tenants, not null |
| job_id | UUID | FK jobs, not null |
| account_id | UUID | FK email_accounts, not null |
| provider | String(32) | e.g. "gmail" |
| provider_message_id | String(255) | Gmail message ID after send |
| thread_id | String(255) | nullable — Gmail thread ID |
| to_addrs_json | Text | JSON array of email addresses |
| cc_addrs_json | Text | nullable, JSON array |
| subject | Text | nullable |
| body_text | Text | nullable |
| sent_at | Timestamptz | not null |

Indexes: `tenant_id`, `job_id`, `account_id`.

---

## Backend API Changes

- **POST /jobs/{job_id}/draft-reply**  
  Request: `source_message_id?`, `tone?`, `user_instruction?`.  
  Creates a draft: resolves account from job/thread, builds context, calls LLM (BYOK), stores row in `message_drafts` with status GENERATED. Returns draft schema (id, subject, body_text, tone, status, etc.).

- **GET /drafts/{draft_id}**  
  Returns a single draft (tenant-scoped). Used to load draft into composer.

- **PATCH /drafts/{draft_id}**  
  Request: `subject?`, `body_text?`. Updates draft; if body/subject changed from generated, set status to EDITED.

- **POST /drafts/{draft_id}/send**  
  Sends the email via Gmail (see below). On success: create `sent_messages` row, update draft status to SENT, add job event type `REPLY_SENT` (with optional reference to sent_messages id or draft id). On failure: set draft status to FAILED, return 4xx/5xx with clear message; do not create sent_messages.

All endpoints require auth; tenant from JWT. Drafts and sent_messages are tenant-scoped.

---

## Gmail API / Send Integration

- **Scope**: Sending email requires `https://www.googleapis.com/auth/gmail.send` (in addition to existing `gmail.modify` if we only had read/label). For v1 we may use `gmail.compose` or `gmail.send`; typically `gmail.send` is sufficient for sending. **Recommendation:** document that re-auth may be needed if the app was previously authorized only with `gmail.modify`; request `gmail.send` (or full `gmail.compose`) in OAuth flow for “Send from app” to work.
- **Send flow**: Use Gmail API `users.messages.send` with:
  - **Body**: `raw` (RFC 2822 message, base64url-encoded) and, when replying, `threadId`.
  - **Reply-in-thread**: To keep the reply in the same thread, include in the request body the same `threadId` as the thread we’re replying to. The RFC 2822 message should have `Subject` consistent with the thread (e.g. “Re: …”), and optionally `References` / `In-Reply-To` if we have the original Message-ID (from message headers). If we don’t have thread_id (e.g. new thread), omit `threadId` and send as a new thread.
- **Recipients**: Validate that at least one To (or Cc) is present; derive from source message (e.g. reply to From, or from thread participants). Never send without explicit user action.
- **Errors**: Map Gmail API errors (quota, invalid credentials, invalid recipient) to clear HTTP responses and log send failures; set draft status to FAILED and store error reason if desired for v1.

---

## Prompt / Generation Strategy

- **Inputs**: Source message (or last message in thread) subject/body snippet, job (company, role, stage), recruiter/contact names and emails (from job_contacts/contacts), user-selected tone, optional free-form user instruction (e.g. “say I’m interested”, “ask for compensation range”, “propose scheduling next week”).
- **Output**: Structured JSON only: `{ "subject": string, "body": string }`. No markdown fences.
- **Prompt requirements** (to be embedded in system/user prompt):
  - Generate professional, concise, context-aware emails.
  - Do not invent facts (dates, numbers, names not in context or user instruction).
  - Do not commit to specific times unless explicitly provided in context or user instruction.
  - Prefer “Re:” subject when replying; keep subject line consistent with thread.
- **Tone presets**: professional, warm, concise, enthusiastic, direct. Pass the selected tone into the prompt.
- **Security**: Same as extraction: no API keys or tenant IDs in prompts; truncate long bodies in context; use tenant’s BYOK LLM key only.

---

## UI/UX Flow

1. **Job detail / timeline**: Show a “Suggest Reply” action (e.g. button in timeline header or per message).
2. **Suggest Reply**: On click, optional: let user pick tone and/or add a short instruction; then call POST `/jobs/{job_id}/draft-reply`. Show loading state.
3. **Draft composer**: When draft is returned, open a composer panel or modal with subject and body (editable). Display tone and optional “Regenerate” if we add that in v1.
4. **Edit**: User edits subject/body; on blur or explicit Save, call PATCH `/drafts/{draft_id}` so draft is persisted.
5. **Send**: “Send” button calls POST `/drafts/{draft_id}/send`. Show loading; on success close composer and refresh timeline; show success toast. On error show error message (e.g. “Send failed: invalid recipient”).
6. **Timeline**: Include sent replies in the timeline (from `sent_messages` + job events). Display them similarly to received messages but with a “Sent” indicator and timestamp.

---

## Auth / Scope Considerations

- **Backend**: All draft and send endpoints require authenticated user (JWT); tenant_id from token. Only drafts/sent_messages for that tenant are accessible.
- **Gmail**: Sending requires OAuth scope that allows sending (e.g. `gmail.send`). If the app currently only requests `gmail.modify`, existing users may need to re-authorize to grant send permission. Document this and handle 403 from Gmail send gracefully (e.g. “Reconnect Gmail with send permission”).
- **LLM**: Use existing BYOK flow; no new auth for LLM.

---

## Edge Cases

- **No BYOK key**: POST draft-reply returns 400/503 with message “LLM key not configured”.
- **No connected account / account not for this thread**: Resolve account from job’s thread (job_threads → messages → account_id) or job’s first message; if none, return 400 “No email account available for this job”.
- **No source message**: Allow draft-reply without source_message_id (e.g. “compose new email for this job”); context is job + contacts only; subject/body may be generic.
- **Thread without thread_id**: Send as new conversation (no threadId in send request).
- **Send failure**: Don’t create sent_messages; set draft status to FAILED; return error detail to UI.
- **Duplicate send**: Idempotency — if draft already SENT, POST send returns 400 “Draft already sent”.
- **Recipient validation**: Reject send if To + Cc are empty or invalid; return 400 with clear message.

---

## Testing Plan

- **Unit**: Reply generation service: mock LLM, assert prompt contains job/thread/contact context and tone; assert output is parsed to subject/body.
- **Unit**: Gmail send: mock httpx; assert request body has raw + threadId when thread exists; assert 4xx/5xx from Gmail mapped to draft FAILED and appropriate HTTP status.
- **Integration**: POST draft-reply with test job/message/contacts; assert draft row created with status GENERATED; PATCH draft; POST send with mocked Gmail success → assert sent_messages row, REPLY_SENT event, draft status SENT.
- **Integration**: Timeline endpoint returns sent_messages as timeline items and REPLY_SENT events.
- **Frontend**: Suggest Reply opens composer with generated content; edit and PATCH; send and assert timeline refresh and sent entry visible (e2e or component tests as applicable).

---

## Summary

| Area | Decision |
|------|----------|
| **Human-in-the-loop** | Never auto-send; user must review/edit and click Send. |
| **Draft storage** | message_drafts table; status GENERATED → EDITED → SENT / FAILED. |
| **Sent audit** | sent_messages table; job event REPLY_SENT; timeline includes sent replies. |
| **LLM** | Tenant BYOK key; structured JSON subject/body; tone + optional user instruction. |
| **Gmail** | messages.send with raw + threadId; validate recipients; clear error handling. |
| **APIs** | POST /jobs/{id}/draft-reply, GET/PATCH /drafts/{id}, POST /drafts/{id}/send. |

---

## Gmail scopes / permissions required

- **Read (existing):** `https://www.googleapis.com/auth/gmail.modify` — used for fetching messages and applying labels.
- **Send (new for this feature):** `https://www.googleapis.com/auth/gmail.send` — required to send emails via `users.messages.send`.

If the app was previously authorized only with `gmail.modify`, users must re-authorize (reconnect Gmail in Settings) to grant `gmail.send` so that “Send” from the app works. A 403 from the Gmail API on send should be surfaced as a clear message (e.g. “Reconnect Gmail with send permission”).
