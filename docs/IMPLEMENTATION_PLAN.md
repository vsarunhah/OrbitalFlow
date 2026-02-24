# Implementation Plan (v1)

## Phase 0: Repo + Dev Env
- docker-compose: postgres + redis
- FastAPI app skeleton, health endpoint
- Next.js skeleton

## Phase 1: Auth + Tenancy
- tenants/users tables (Alembic)
- register/login endpoints
- auth middleware
- tenant scoping helper

## Phase 2: Encryption + BYOK
- APP_ENCRYPTION_KEY env
- llm_keys table, endpoints to set/check key configured
- never return raw key from API

## Phase 3: Gmail OAuth + Account Model
- email_accounts table
- OAuth start + callback endpoints
- store oauth_encrypted + cursor_json

## Phase 4: Ingestion + Polling (RQ)
- Provider interfaces: EmailProvider, ChangeSource
- GmailProvider.fetch_message(format=full)
- PollingChangeSource.get_changes(after=cursor-last_lookback)
- RQ worker: sync_account -> enqueue process_message
- store messages (raw + normalized)

## Phase 5: LLM extract + classification
- message_extractions table
- BYOK LLM client wrapper
- structured JSON output validation
- persist extractions

## Phase 6: Jobs + reducer + timeline
- jobs/job_events/job_stage_history/job_threads tables
- job resolution: threadId strongest, then req_id, then fuzzy company+role
- reducer applies deterministic stage changes
- manual override endpoint

## Phase 7: Gmail labeling
- create labels if missing
- apply label per message based on category

## Phase 8: Search + UI
- Postgres FTS index on messages.body_text
- jobs list endpoint supports search/filter
- timeline endpoint
- split-pane UI

## Phase 9: Recruiters + Alerts pages
- contacts + affiliations + job_contacts
- alerts feed endpoint + UI