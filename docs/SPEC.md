# JobTracker Spec (v1)

## Goal
Sync Gmail for multiple users/tenants, classify job-related emails (STATUS/RECRUITER/ALERT/OTHER),
auto-track job stages with audit + manual override, apply Gmail labels, and provide a split-pane UI.

## Tech
Backend: FastAPI + SQLAlchemy + Alembic
DB: Postgres
Queue: Redis + RQ
Frontend: Next.js (split-pane)
Auth: email/password (multi-tenant)
LLM: BYOK, store encrypted key in DB
Gmail: OAuth with gmail.modify
Sync: polling (swapable to Pub/Sub later via ChangeSource interface)
Search: Postgres full-text over message body_text

## Key Concepts
- Tenant isolation: every row has tenant_id
- Provider abstractions:
  - EmailProvider: fetch_message(message_id)
  - ChangeSource: get_changes(cursor)->message_refs,new_cursor
- Idempotent ingestion: unique(account_id, provider_msg_id)
- Deterministic reducer: event -> stage transitions in code (not LLM)
- Manual override wins; keep stage history.

## Categories
STATUS, RECRUITER, ALERT, OTHER

## Event types (v1)
APPLICATION_RECEIVED, INTERVIEW_REQUEST, INTERVIEW_SCHEDULED, INTERVIEW_RESCHEDULE,
TAKEHOME_REQUEST, OFFER, REJECTION, FOLLOW_UP, JOB_ALERT, NONE

## Stages (v1)
SOURCED, APPLIED, SCREEN, INTERVIEW, TAKEHOME, FINAL, OFFER, REJECTED, WITHDRAWN

## Stage reducer rules
- APPLICATION_RECEIVED => APPLIED
- INTERVIEW_* => INTERVIEW
- TAKEHOME_REQUEST => TAKEHOME
- OFFER => OFFER
- REJECTION => REJECTED
- Never auto-change out of REJECTED/WITHDRAWN
- Never auto-downgrade
- Only auto-change if confidence >= 0.80
- Always write job_stage_history with message_id and rationale

## Gmail labels
JobTracker/Status, JobTracker/Recruiter, JobTracker/Alerts
Apply based on category when confidence >= threshold.

## Pages (UI)
1) Auth (login/register)
2) Settings: Connect Gmail, set BYOK key, toggles (labeling, thresholds)
3) Jobs split-pane: list+filters+search (left), timeline/thread (right)
4) Alerts feed (job alerts)
5) Recruiters view (contacts + affiliations)