# Feature: Follow-Up Email Suggestions

## Goal
Allow the system to generate follow-up emails when a job appears stalled, so the user can send a polite, context-aware nudge without sounding pushy.

## Detection Rules

A job is considered **stalled** (and we offer "Generate Follow-Up") when any of the following holds:

1. **No reply after interview for 7–10 days**
   - Job stage is INTERVIEW, TAKEHOME, or FINAL.
   - Last message in the thread is from the recruiter (not the account owner).
   - Days since that last message ≥ 7 (and optionally ≤ 10 for a softer window; we use ≥ 7).

2. **Recruiter conversation stalled for 5+ days**
   - Last message in the thread is from the recruiter.
   - Days since that message ≥ 5.
   - Job is not in a terminal stage (REJECTED, WITHDRAWN).

These align with the existing **next_action** system:
- `next_action.type === "follow_up"`: last message from recruiter, no reply for ≥ NEEDS_REPLY_DAYS (6). Treat as stalled.
- `next_action.type === "ghosted"`: no activity for ≥ GHOSTED_DAYS (14). Treat as stalled.
- We also treat `next_action.type === "needs_reply"` with ≥ 5 days as eligible when we want to suggest a follow-up earlier.

**Implementation:** A job is **suggest_followup** when:
- `next_action` is present and `next_action.type` is `"follow_up"` or `"ghosted"`, **or**
- `next_action.type === "needs_reply"` and days since last (recruiter) message ≥ 5.

No new next_action types are required; we derive a boolean `suggest_followup` from existing next_action + stage/days where useful.

## Integration with next_action

- **next_action** continues to drive the label shown (e.g. "Follow up with recruiter (no reply in X days)", "Ghosted?").
- **suggest_followup** is a derived flag exposed on job list, job detail, and timeline responses. When true, the UI shows a "Generate Follow-Up" button.
- Follow-up generation uses the same thread/job/recruiter context as reply generation but with a dedicated prompt and no reply-to specific message (it’s a new follow-up, not a direct reply).

## UI Flow

1. **Where:** Jobs list (optional chip/icon) and **timeline view** (primary): when a job is selected and `job.suggest_followup` is true, show a "Generate Follow-Up" button next to "Reply".
2. **Click "Generate Follow-Up":**
   - Call `POST /jobs/{id}/follow-up-suggestion`.
   - Backend generates subject + body (and optionally creates a draft). Response includes `subject`, `body`, `tone`, `confidence` and optionally `draft_id`.
   - Frontend opens the existing Reply/Draft modal with the created draft (or pre-filled subject/body) so the user can edit and send.
3. **Edit & send:** Same as existing reply flow: user can edit the draft and send via the same modal.

## Prompt Design

- **Role:** Generate a short follow-up email for a job seeker to send to a recruiter when the conversation has stalled.
- **Inputs (in user message):**
  - Job: company, role, current stage.
  - Recruiter/recipient info (from contacts or thread).
  - Last message in thread (or last few messages) for context.
  - Stage and time since last activity (e.g. "Last activity 8 days ago; stage INTERVIEW").
- **Constraints:**
  - Polite and professional.
  - Reference the prior conversation (e.g. "Following up on our conversation…", "After our interview…").
  - Avoid sounding pushy or demanding.
  - Keep body under ~120 words.
- **Output:** JSON only: `{ "subject": "...", "body": "...", "tone": "...", "confidence": number }`. Same shape as reply generation for consistency.

## API

### POST /jobs/{job_id}/follow-up-suggestion

- **Auth:** Required (tenant-scoped).
- **Response:** 
  - Option A: `{ "subject", "body", "tone", "confidence" }` only.
  - Option B (implemented): Also create a draft of type `follow_up` and return `{ "subject", "body", "tone", "confidence", "draft": MessageDraftSchema }` so the UI can open the draft in the reply modal in one step.
- **Errors:** 400 if job not found, no LLM key, or job not eligible (e.g. terminal stage). 404 if job not found.

## Testing Plan

1. **Detection**
   - Unit tests: `suggest_followup` true when `next_action.type` is `follow_up` or `ghosted`; true when `needs_reply` and days ≥ 5; false for terminal stages or when last message from owner.
   - API tests: list/detail/timeline include `suggest_followup` and it is true/false as expected for fixture jobs.

2. **Generation**
   - Unit test: `generate_follow_up_suggestion()` with mocked LLM returns valid subject/body/tone/confidence and body word count ≤ ~120 (or soft check).
   - Integration/API test: POST follow-up-suggestion for a job with thread and recruiter returns 200, valid JSON, and optionally a draft; draft has correct job_id and type.

3. **UI**
   - Manual: Select a job that has "Follow up with recruiter" or "Ghosted?" → "Generate Follow-Up" visible; click → draft modal opens with suggested content; edit and send works.
   - Optional E2E: Trigger follow-up, assert modal content and draft creation.

4. **Edge cases**
   - Job in REJECTED/WITHDRAWN: no suggest_followup, endpoint returns 400 if called.
   - No thread / no messages: endpoint returns 400 or graceful message.
   - LLM key missing: 400 with clear message.

## Files Changed (Summary)

- **docs/feature_followup_emails.md** – this feature doc
- **Backend:**  
  - `app/services/next_action.py` – `suggest_followup_for_next_action()`
  - `app/services/followup_generation.py` – new; `generate_followup_suggestion()`
  - `app/llm/prompts.py` – `FOLLOW_UP_GENERATION_SYSTEM_PROMPT`, `build_followup_user_content()`
  - `app/schemas/draft.py` – `FollowUpSuggestionResponse`
  - `app/schemas/job.py` – `JobSummary.suggest_followup`
  - `app/routers/jobs.py` – `suggest_followup` on list/detail/timeline; `POST /jobs/{id}/follow-up-suggestion`
  - `app/routers/drafts.py` – `create_draft_from_followup()`
- **Frontend:**  
  - `frontend/lib/api.js` – `generateFollowUpSuggestion(jobId)`
  - `frontend/pages/jobs.js` – "Generate Follow-Up" button when `job.suggest_followup`, flow to open draft modal
- **Tests:**  
  - `tests/test_next_action.py` – `suggest_followup_for_next_action` and `suggest_followup` in API responses
  - `tests/test_followup.py` – POST follow-up-suggestion (404, 400 when not stalled, 200 with draft, 400 when LLM key missing)
