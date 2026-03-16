"""Run RQ worker with INFO logging so sync_account and polling logs are visible.

Usage (from backend directory):
    python -m app.workers.run_worker

Requires Redis (REDIS_URL). Processes the 'jobtracker' queue.

On macOS we use SpawnWorker (os.spawn) instead of the default Worker (fork) to avoid
"crashed on child side of fork pre-exec" / CoreFoundation fork-safety crashes.
"""

from __future__ import annotations

import logging
import sys

from app.config import settings
from app.workers.connection import redis_conn, task_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)


def main() -> None:
    queue_name = task_queue.name
    # Use SpawnWorker on macOS to avoid fork-safety crash (OBJC/fork pre-exec)
    if sys.platform == "darwin":
        from rq import SpawnWorker
        worker_class = SpawnWorker
        logger.info("Using SpawnWorker (macOS fork-safe) for queue=%s redis=%s", queue_name, settings.redis_url)
    else:
        from rq import Worker
        worker_class = Worker
        logger.info("Starting RQ worker for queue=%s redis=%s", queue_name, settings.redis_url)
    worker = worker_class([queue_name], connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    main()
