#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_NAME="${SESSION_NAME:-jobtracker-dev}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command '$1' was not found." >&2
    exit 1
  fi
}

require_command docker
require_command python3
require_command npm
require_command tmux

if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker daemon is not running. Start Docker Desktop and try again." >&2
  exit 1
fi

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "tmux session '$SESSION_NAME' already exists. Attaching..."
  exec tmux attach-session -t "$SESSION_NAME"
fi

echo "Starting Postgres + Redis..."
docker compose -f "$ROOT_DIR/infra/docker-compose.yml" up -d

echo "Preparing backend virtualenv and dependencies..."
if [ ! -d "$ROOT_DIR/backend/.venv" ]; then
  python3 -m venv "$ROOT_DIR/backend/.venv"
fi
"$ROOT_DIR/backend/.venv/bin/pip" install -r "$ROOT_DIR/backend/requirements.txt"

echo "Preparing frontend dependencies..."
if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
  npm --prefix "$ROOT_DIR/frontend" install
fi

echo "Starting tmux session '$SESSION_NAME'..."
# Window 0: docker logs
tmux new-session -d -s "$SESSION_NAME" -n docker -c "$ROOT_DIR"
tmux send-keys -t "$SESSION_NAME:docker" \
  "cd \"$ROOT_DIR\" && docker compose -f infra/docker-compose.yml logs -f --tail=20" C-m

# Window 1: backend
tmux new-window -t "$SESSION_NAME" -n backend -c "$ROOT_DIR/backend"
tmux send-keys -t "$SESSION_NAME:backend" \
  "cd \"$ROOT_DIR/backend\" && source .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000" C-m

# Window 2: frontend
tmux new-window -t "$SESSION_NAME" -n frontend -c "$ROOT_DIR/frontend"
tmux send-keys -t "$SESSION_NAME:frontend" \
  "cd \"$ROOT_DIR/frontend\" && npm run dev -- --port 3000" C-m

# Window 3: RQ worker (processes sync jobs; required for Force Sync / lookback to run)
tmux new-window -t "$SESSION_NAME" -n worker -c "$ROOT_DIR/backend"
tmux send-keys -t "$SESSION_NAME:worker" \
  "cd \"$ROOT_DIR/backend\" && source .venv/bin/activate && python -m app.workers.run_worker" C-m

# Window 4: Scheduler (enqueues sync_account every 5 minutes for active accounts)
tmux new-window -t "$SESSION_NAME" -n scheduler -c "$ROOT_DIR/backend"
tmux send-keys -t "$SESSION_NAME:scheduler" \
  "cd \"$ROOT_DIR/backend\" && source .venv/bin/activate && python -m app.workers.scheduler" C-m

# Start on first window
tmux select-window -t "$SESSION_NAME:docker"
exec tmux attach-session -t "$SESSION_NAME"
