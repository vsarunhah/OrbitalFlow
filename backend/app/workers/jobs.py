"""RQ job definitions for email ingestion.

sync_account(account_id)
    - Load the EmailAccount
    - Call ChangeSource.get_changes(cursor) to discover new message refs
    - Enqueue a process_message job for each ref
    - Update the account's sync_cursor_json

process_message(account_id, provider_msg_id)
    - Idempotency: skip if (account_id, provider_msg_id) already in messages
    - Fetch full message via EmailProvider
    - Parse and store in messages table
    - Run LLM extraction (Phase 5): classify email, persist extraction row
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import SessionLocal
from app.models.email_account import EmailAccount
from app.models.message import Message
from app.providers.gmail import GmailProvider, TokenRefreshError
from app.providers.polling import PollingChangeSource

logger = logging.getLogger(__name__)


def sync_account(account_id: str, lookback_days: int | None = None) -> dict:
    """Discover new messages for an account and enqueue processing jobs.

    Args:
        lookback_days: If provided, force-sync emails from this many days ago
                       instead of using the normal cursor-based lookback.
    """
    logger.info(
        "sync_account started for account_id=%s lookback_days=%s",
        account_id,
        lookback_days,
    )

    db = SessionLocal()
    try:
        account = db.query(EmailAccount).filter(
            EmailAccount.id == uuid.UUID(account_id),
            EmailAccount.status == "active",
        ).first()

        if account is None:
            logger.warning("Account %s not found or inactive, skipping", account_id)
            return {"status": "skipped", "reason": "not_found_or_inactive"}

        cursor = json.loads(account.sync_cursor_json)
        change_source = PollingChangeSource(db_session=db)

        after_epoch_override = None
        if lookback_days is not None:
            from datetime import timedelta
            after_epoch_override = int(
                (datetime.now(timezone.utc) - timedelta(days=lookback_days)).timestamp()
            )
            logger.info(
                "Force sync: looking back %d days (after_epoch=%s)",
                lookback_days,
                after_epoch_override,
            )

        try:
            result = change_source.get_changes(
                account, cursor, after_epoch_override=after_epoch_override
            )
        except TokenRefreshError as e:
            logger.warning(
                "sync_account skipped: invalid Gmail token account_id=%s: %s",
                account_id,
                e,
            )
            return {
                "status": "token_error",
                "detail": (
                    "Gmail authentication failed. Reconnect the account in Settings."
                ),
            }

        logger.info(
            "sync_account account_id=%s found %d refs",
            account_id,
            len(result.refs),
        )

        from app.workers.connection import task_queue

        enqueued = 0
        for ref in result.refs:
            existing = db.query(Message.id).filter(
                Message.account_id == account.id,
                Message.provider_msg_id == ref.provider_msg_id,
            ).first()

            if existing:
                logger.debug(
                    "Skipping already-ingested msg %s for account %s",
                    ref.provider_msg_id,
                    account_id,
                )
                continue

            task_queue.enqueue(
                process_message,
                str(account.id),
                ref.provider_msg_id,
                job_timeout=settings.rq_job_timeout,
                retry=_rq_retry(),
            )
            enqueued += 1

        account.sync_cursor_json = json.dumps(result.new_cursor)
        db.commit()

        logger.info(
            "sync_account done for account_id=%s: enqueued=%d, total_refs=%d",
            account_id,
            enqueued,
            len(result.refs),
        )
        return {"status": "ok", "enqueued": enqueued, "total_refs": len(result.refs)}

    except Exception:
        logger.exception("sync_account failed for account_id=%s", account_id)
        raise
    finally:
        db.close()


def process_message(account_id: str, provider_msg_id: str) -> dict:
    """Fetch, parse, and store a single message. Idempotent on (account_id, provider_msg_id)."""
    logger.info(
        "process_message started account_id=%s provider_msg_id=%s",
        account_id,
        provider_msg_id,
    )

    db = SessionLocal()
    try:
        existing = db.query(Message.id).filter(
            Message.account_id == uuid.UUID(account_id),
            Message.provider_msg_id == provider_msg_id,
        ).first()

        if existing:
            logger.info(
                "Message already exists, skipping. account_id=%s provider_msg_id=%s",
                account_id,
                provider_msg_id,
            )
            return {"status": "skipped", "reason": "duplicate"}

        account = db.query(EmailAccount).filter(
            EmailAccount.id == uuid.UUID(account_id),
        ).first()

        if account is None:
            logger.warning("Account %s not found, skipping message", account_id)
            return {"status": "skipped", "reason": "account_not_found"}

        provider = GmailProvider(db_session=db)
        fetched = provider.fetch_message(account, provider_msg_id)

        date_header_dt = None
        if fetched.date_header:
            try:
                date_header_dt = datetime.fromisoformat(fetched.date_header)
            except (ValueError, TypeError):
                pass

        msg = Message(
            tenant_id=account.tenant_id,
            account_id=account.id,
            provider_msg_id=fetched.provider_msg_id,
            thread_id=fetched.thread_id,
            subject=fetched.subject,
            from_address=fetched.from_address,
            to_addresses=fetched.to_addresses,
            date_header=date_header_dt,
            body_text=fetched.body_text,
            body_html=fetched.body_html,
            headers_json=fetched.headers_json,
            raw_payload_json=fetched.raw_payload_json,
            label_ids_json=fetched.label_ids_json,
            extraction_status="pending",
        )

        db.add(msg)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            logger.info(
                "Duplicate detected on commit (race condition handled). "
                "account_id=%s provider_msg_id=%s",
                account_id,
                provider_msg_id,
            )
            return {"status": "skipped", "reason": "duplicate_race"}

        logger.info(
            "Stored message id=%s account_id=%s provider_msg_id=%s subject=%s",
            msg.id,
            account_id,
            provider_msg_id,
            (fetched.subject or "")[:80],
        )

        _run_llm_extraction(db, msg)

        return {"status": "ok", "message_id": str(msg.id)}

    except Exception:
        logger.exception(
            "process_message failed account_id=%s provider_msg_id=%s",
            account_id,
            provider_msg_id,
        )
        raise
    finally:
        db.close()


def _run_llm_extraction(db, msg: Message) -> None:
    """Run LLM extraction inline after message storage, then process for job tracking.

    Failures are recorded in the extraction row; they do not bubble up
    to fail the entire process_message job.
    """
    try:
        from app.services.extraction import run_extraction

        extraction = run_extraction(db, msg.id, msg.tenant_id)
        _run_job_processing(db, msg, extraction)
    except Exception:
        logger.exception(
            "LLM extraction failed for message_id=%s (non-fatal)", msg.id
        )


def _run_job_processing(db, msg: Message, extraction) -> None:
    """Resolve/create job from extraction, apply stage reducer. Non-fatal."""
    try:
        from app.services.job_processing import process_extraction_for_job

        process_extraction_for_job(db, msg, extraction)
    except Exception:
        logger.exception(
            "Job processing failed for message_id=%s (non-fatal)", msg.id
        )

    _run_gmail_labeling(db, msg, extraction)


def _run_gmail_labeling(db, msg: Message, extraction) -> None:
    """Apply Gmail label based on extraction category. Non-fatal."""
    try:
        account = db.query(EmailAccount).filter(
            EmailAccount.id == msg.account_id,
        ).first()
        if account is None:
            return

        from app.services.gmail_labeling import label_message_if_configured

        label_message_if_configured(db, account, msg, extraction)
    except Exception:
        logger.exception(
            "Gmail labeling failed for message_id=%s (non-fatal)", msg.id
        )


def _rq_retry():
    """Build an RQ Retry spec from settings."""
    from rq import Retry

    return Retry(
        max=settings.rq_retry_max,
        interval=settings.rq_retry_delay,
    )
