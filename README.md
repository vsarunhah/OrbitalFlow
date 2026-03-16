JobTracker – Gmail‑powered job search tracker

This monorepo contains:
- `infra/` – local Postgres + Redis via Docker Compose
- `backend/` – FastAPI backend for auth, Gmail sync, jobs, analytics, alerts, and AI‑assisted replies
- `frontend/` – Next.js + MUI web app for managing your job pipeline

---

## Features

- **Email‑driven job tracking**
  - Connect one or more **Gmail** accounts and automatically ingest job‑related emails.
  - Classify emails (status updates, recruiter outreach, alerts, etc.) using your own OpenAI API key.
  - Map emails to **jobs**, with a full timeline view (incoming emails, status changes, and your sent replies).

- **Job pipeline**
  - Board‑style `Jobs` view with stages: `SOURCED`, `APPLIED`, `SCREEN`, `INTERVIEW`, `TAKEHOME`, `FINAL`, `OFFER`, `REJECTED`, `WITHDRAWN`.
  - Search by company/role/email content and filter by stage.
  - Edit company/role/req ID, override stages with rationale, and merge duplicate jobs.

- **Gmail integration**
  - OAuth connection flow from the `Settings` page.
  - Background worker syncs new emails every few minutes.
  - **Force Sync** with configurable lookback (e.g. last 7 / 30 / 90 days).
  - Optionally **delete all ingested data** for a given Gmail account and re‑ingest.

- **AI‑assisted replies**
  - Generate suggested replies and follow‑ups for a job using your OpenAI key.
  - Multiple tone variants (e.g. concise/friendly/etc.), with inline editing and one‑click send via Gmail.

- **Analytics**
  - Summary metrics: total jobs, applications, interviews, offers, rejections, recent activity.
  - Conversion rates (application→interview, interview→offer) and time‑to‑first‑interview.
  - **Funnel view** (ever reached each milestone).
  - **Sankey flow** chart for stage‑to‑stage transitions.
  - Time‑series charts for jobs created and activity.

- **Multi‑tenant + auth**
  - Email/password auth with registration and JWT‑based sessions.
  - Per‑tenant data isolation.
  - Password reset flow (forgot/reset) with tokenized links.

---

## Prerequisites

- Docker + Docker Compose
- Python 3.10+
- Node.js 18+
- `tmux` (optional but recommended for the one‑command dev setup)

---

## Quick start (one command dev setup)

From the repo root:

```bash
./scripts/dev-up.sh
```

This will:
- Start Postgres + Redis via Docker Compose.
- Ensure backend virtualenv/dependencies are installed.
- Ensure frontend dependencies are installed.
- Start a `tmux` session with panes for infra logs, backend, frontend, and the RQ worker (required for Gmail sync and lookback jobs).

Running it again will attach to the existing `tmux` session.

---

## Manual setup

### 1) Start infrastructure

From the repo root:

```bash
docker compose -f infra/docker-compose.yml up -d
```

This launches:
- Postgres on `localhost:5432` with database `jobtracker`.
- Redis on `localhost:6379`.

### 2) Backend

#### 2.1 Configure environment

Copy the example env file and fill in values:

```bash
cd backend
cp .env.example .env
```

Key settings in `.env`:

- **Database & Redis**
  - `DATABASE_URL=postgresql://jobtracker:jobtracker@localhost:5432/jobtracker`
  - `REDIS_URL=redis://localhost:6379/0`

- **Security & encryption**
  - `SECRET_KEY` – random string for signing JWTs.
  - `APP_ENCRYPTION_KEY` – Fernet key for encrypting stored secrets. Generate with:

    ```bash
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ```

- **Gmail OAuth**
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`
  - `GOOGLE_REDIRECT_URI=http://localhost:8000/email-accounts/gmail/oauth-callback`

- **Sync / worker**
  - `SYNC_POLL_INTERVAL_SECONDS` – how often background sync runs.
  - `SYNC_LOOKBACK_MINUTES` – default lookback window for polling.

#### 2.2 Install dependencies and run API

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend exposes:
- `GET /health` – health check returning `{"status": "ok"}`.
- Auth routes under `/auth` (login/register/forgot-password/reset-password/me/refresh).
- Gmail, jobs, drafts, analytics, recruiters, resumes, alerts, merge suggestions, and tenant settings routers.

#### 2.3 Run the RQ worker

The worker processes Gmail sync jobs and other background tasks (e.g. Force Sync, lookback scans).

In a separate terminal:

```bash
cd backend
source .venv/bin/activate
python -m app.workers.run_worker
```

Leave this running; you should see logs like `sync_account started` as emails are processed.

#### 2.4 Verify backend

Open `http://localhost:8000/health` in your browser or curl:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "ok"}
```

---

### 3) Frontend

From the repo root:

```bash
cd frontend
npm install
npm run dev
```

The app runs at `http://localhost:3000`.

Main pages:
- `/login` – sign in / register, password reset entry point.
- `/jobs` – primary pipeline view with per‑job timeline and reply composer.
- `/analytics` – metrics, funnel, and Sankey flow chart.
- `/settings` – Gmail connection, Force Sync, delete‑all‑emails, and OpenAI API key configuration.
- `/alerts`, `/recruiters`, `/merge-suggestions`, `/resumes` – additional views powered by the backend routers.

---

## Typical local flow

1. **Start services**
   - Either run `./scripts/dev-up.sh`, or:
     - `docker compose -f infra/docker-compose.yml up -d`
     - Backend `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
     - Worker `python -m app.workers.run_worker`
     - Frontend `npm run dev`

2. **Create an account**
   - Go to `http://localhost:3000/login`, register with an email/password.

3. **Configure settings**
   - In `Settings`:
     - Connect Gmail and complete the OAuth flow.
     - Paste your OpenAI API key and save.

4. **Ingest emails**
   - Use **Force Sync** with a lookback window (e.g. last 30 days).
   - Wait for the worker to process jobs; then open `Jobs` and `Analytics`.

---

## Testing & validation

- **Backend health**: `curl http://localhost:8000/health` → `{"status": "ok"}`.
- **Frontend**: `http://localhost:3000` automatically redirects to `/jobs` when authenticated.
- **Gmail**: connect an account in `Settings`, then trigger a Force Sync and watch worker logs.
- **Analytics**: visit `/analytics` once you have some jobs and email activity to see funnel and Sankey visualizations.
