# JobTracker Monorepo (Phase 0)

This repository currently includes only Phase 0 setup:
- `infra/` for local Postgres + Redis
- `backend/` FastAPI skeleton with `/health`
- `frontend/` Next.js skeleton with a health ping page

## Prerequisites

- Docker + Docker Compose
- Python 3.10+
- Node.js 18+
- tmux

## One-command dev startup (tmux)

```bash
./scripts/dev-up.sh
```

This will:
- Start Postgres + Redis with Docker Compose
- Ensure backend virtualenv/dependencies are installed
- Ensure frontend dependencies are installed
- Start a tmux session with panes for infra logs, backend, frontend, and the RQ worker (needed for Force Sync / lookback)

If you run it again, it will attach to the existing tmux session.

## 1) Start infrastructure

```bash
docker compose -f infra/docker-compose.yml up -d
```

## 2) Run backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**2b) Run the RQ worker** (required for Force Sync / lookback to actually run)

In a separate terminal, from the backend directory:

```bash
cd backend
source .venv/bin/activate
python -m app.workers.run_worker
```

Keep this running. Sync jobs (e.g. from Settings → Force Sync with a lookback) are processed here; you’ll see logs like `sync_account started`, `Gmail after query`, etc.

Open `http://localhost:8000/health` and expect:

```json
{"status":"ok"}
```

## 3) Run frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`, click `Ping /health`, and expect:

```text
Result: {"status":"ok"}
```
