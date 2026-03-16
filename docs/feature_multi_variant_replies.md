# Feature: Multi-Variant Reply Suggestions

**Source of truth:** `docs/SPEC.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/feature_ai_reply_and_send.md`.

## Overview

When the user clicks "Suggest Reply", the system generates **multiple reply variants** with different tones and styles (concise, warm, enthusiastic) so the user can choose one, optionally edit it, and send. Only one variant becomes the final draft that can be edited and sent. The existing draft system (single draft row, PATCH, POST send) is preserved; we extend it by storing multiple variants on the draft and returning them from the create endpoint.

## Goals

- Produce 3 variants per "Suggest Reply" request: **concise**, **warm**, **enthusiastic**.
- Each variant includes: `variant_id`, `tone`, `subject`, `body`, `confidence`.
- User can switch between variants in the UI, edit the chosen one, and send a single draft.
- Outputs are deterministic JSON; no breaking changes to the existing draft/send flow.

---

## LLM Strategy

**Approach: Single prompt, single LLM call returning all 3 variants.**

- **Why single call:** Lower latency (one round-trip), lower token cost, and a single structured JSON object is easier to validate and keep deterministic. The model sees the same context once and produces three distinct tones in one response.
- **Alternative considered:** Multiple calls (one per tone) would triple latency and cost and could yield inconsistent context handling; we avoid that.
- **Prompt design:** System prompt instructs the LLM to return a JSON object with a `variants` array. Each element has `variant_id` (e.g. "concise" | "warm" | "enthusiastic"), `tone`, `subject`, `body`, `confidence`. We request exactly three variants with these tones so the schema is fixed and parsing is reliable.
- **Determinism:** Use low temperature (e.g. 0.3), strict JSON-only output, and retries with validation. No markdown fences; strip them if present before parsing.

---

## Schema Changes

### Reply variant (in-memory / API)

Each variant in the API and in stored JSON has the shape:

```json
{
  "variant_id": "concise",
  "tone": "concise",
  "subject": "Re: ...",
  "body": "...",
  "confidence": 0.85
}
```

- `variant_id`: One of `concise`, `warm`, `enthusiastic` (fixed set).
- `tone`: Same as variant_id for consistency.
- `subject`, `body`: Generated content.
- `confidence`: Number in [0, 1].

### Database: store variants within the draft record

- **Table:** `message_drafts` (existing).
- **New column:** `variants_json` (TEXT, nullable). Stores a JSON array of variant objects as above. When present, the draft was created via multi-variant generation; the draft’s `subject`, `body_text`, and `tone` represent the **selected** (or default first) variant so that GET/PATCH/send continue to work without change.
- No new tables. One draft row = one generation request; the row’s main fields are the “current” variant for editing and sending.

---

## API Changes

- **POST /jobs/{job_id}/draft-reply**
  - **Request:** Unchanged. `source_message_id?`, `tone?`, `user_instruction?` (optional; for multi-variant we ignore `tone` in the sense that we always generate all three).
  - **Response:** Returns **multiple variants** along with the created draft.
    - New response shape: `{ "draft": MessageDraftSchema, "variants": [ ReplyVariantSchema, ... ] }`.
    - `draft`: The single created draft (id, job_id, subject, body_text, tone, status, etc.). Its subject/body/tone are initialized from the first variant (e.g. concise).
    - `variants`: Array of 3 items, each with `variant_id`, `tone`, `subject`, `body`, `confidence`.
  - **Behavior:** Build context once, call LLM once for 3 variants, create one draft row (subject/body/tone from first variant, all variants stored in `variants_json`), return draft + variants.

- **GET /drafts/{draft_id}**
  - When the draft has `variants_json` set, the response includes a `variants` array (parsed from `variants_json`) so the UI can show the variant switcher when reopening. `MessageDraftSchema` has an optional `variants` field.

- **PATCH /drafts/{draft_id}**
  - Unchanged. Updates subject/body (and optionally tone) of the draft. Used when the user selects a variant (we copy that variant’s subject/body into the draft and may PATCH) or edits manually.

- **POST /drafts/{draft_id}/send**
  - Unchanged. Sends the draft’s current subject/body.

---

## UI Expectations

1. **Suggest Reply**
   - User clicks "Suggest Reply". Frontend calls POST `/jobs/{id}/draft-reply`.
   - Show loading state until response returns.

2. **Display variants**
   - When the response includes `variants` (length ≥ 1), show a way to switch between them (e.g. tabs or chips: "Concise", "Warm", "Enthusiastic").
   - Display the **current** variant’s subject and body in the composer (initially the first variant / draft’s subject and body).

3. **Switching variants**
   - Selecting another variant updates the displayed subject and body (and optionally tone) to that variant’s content. Optionally call PATCH to persist the chosen variant as the draft’s subject/body so that GET and send use it.

4. **Editing**
   - User can edit subject and body in the composer. On Save, call PATCH `/drafts/{id}` as today. Only one “current” draft content exists.

5. **Send**
   - "Send" uses the draft’s current subject/body (the one displayed, possibly from a chosen variant and/or edited). Only one variant becomes the final sent draft.

6. **Backward compatibility**
   - If the API ever returns a draft without `variants` (e.g. legacy path), the UI should still show the single draft and allow edit/send.

---

## Testing Plan

- **Unit – reply generation**
  - Mock LLM to return valid JSON with a `variants` array of 3 items (concise, warm, enthusiastic). Assert `generate_reply_variants()` returns 3 variants with correct fields and that variant_ids/tones match.
  - Assert prompt/content does not include API keys or tenant IDs; assert truncation of long bodies.

- **Unit – parsing and fallback**
  - Invalid JSON or missing `variants` after retries: assert appropriate error (ValueError or similar).
  - If LLM returns markdown fences, assert they are stripped before parsing.

- **API – POST /jobs/{id}/draft-reply**
  - With mocked `generate_reply_variants`: assert response has `draft` and `variants`; `variants` has length 3; each variant has `variant_id`, `tone`, `subject`, `body`, `confidence`. Assert draft row created with `variants_json` populated and draft subject/body equal to first variant.
  - Existing tests that assert draft-reply success: update to expect new response shape and assert on `response.json()["draft"]` and `response.json()["variants"]` where needed; ensure GET/PATCH/send still work with the created draft.

- **API – GET /drafts/{id}**
  - When draft has `variants_json`, assert response includes `variants` (if we add it to GET) so UI can restore variant switcher.

- **API – PATCH /drafts/{id} and POST /drafts/{id}/send**
  - No change in contract; existing tests remain. Optional: test that after selecting a different variant (PATCH with that variant’s subject/body), send uses the patched content.

- **Frontend**
  - Suggest Reply → response with 3 variants → UI shows variant switcher and first variant content; switch to another variant → subject/body update; edit and save → PATCH; send → only one draft sent. Manual or E2E as applicable.

---

## Summary

| Area | Decision |
|------|----------|
| **Variants** | 3 fixed: concise, warm, enthusiastic. |
| **LLM** | Single prompt, single call, JSON with `variants` array. |
| **Storage** | One draft row; `variants_json` holds all 3; draft subject/body/tone = selected variant. |
| **API** | POST draft-reply returns `{ draft, variants }`; GET can include `variants`. |
| **UI** | Switch between variants; edit chosen one; single draft sent. |
| **Determinism** | Low temperature, JSON-only, retries, no fences. |
