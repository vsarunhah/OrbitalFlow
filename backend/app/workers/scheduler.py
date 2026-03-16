"""Minimal polling scheduler.

Runs in a loop: every SYNC_POLL_INTERVAL_SECONDS it enqueues a sync_account
job for each active EmailAccount.

Usage:
    cd backend
    python -m app.workers.scheduler

Environment:
    Reads .env via app.config.settings (DATABASE_URL, REDIS_URL, etc.)
"""

from __future__ import annotations

import logging
import signal
import sys
import time

from app.config import settings
from app.database import SessionLocal
from app.models.email_account import EmailAccount
from app.workers.connection import task_queue
from app.workers.jobs import sync_account

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

_running = True


def _handle_signal(signum, _frame):
    global _running
    logger.info("Received signal %s, shutting down scheduler gracefully", signum)
    _running = False


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def run() -> None:
    interval = settings.sync_poll_interval_seconds
    logger.info(
        "Scheduler started. Polling every %ds. Redis=%s",
        interval,
        settings.redis_url.split("@")[-1] if "@" in settings.redis_url else settings.redis_url,
    )

    while _running:
        try:
            _enqueue_all_accounts()
        except Exception:
            logger.exception("Error in scheduler loop")

        for _ in range(interval):
            if not _running:
                break
            time.sleep(1)

    logger.info("Scheduler stopped.")


def _enqueue_all_accounts() -> None:
    db = SessionLocal()
    try:
        accounts = (
            db.query(EmailAccount)
            .filter(EmailAccount.status == "active")
            .all()
        )
        logger.info("Found %d active accounts to sync", len(accounts))

        for account in accounts:
            task_queue.enqueue(
                sync_account,
                str(account.id),
                job_timeout=settings.rq_job_timeout,
            )
            logger.info("Enqueued sync_account for account_id=%s", account.id)
    finally:
        db.close()


if __name__ == "__main__":
    run()
