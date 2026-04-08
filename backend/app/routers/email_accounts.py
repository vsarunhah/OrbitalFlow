import json
import logging
import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.auth.security import create_access_token, decode_access_token
from app.config import settings
from app.database import get_db
from app.encryption import decrypt, encrypt
from app.models.email_account import EmailAccount
from app.schemas.email_account import (
    EmailAccountDisconnected,
    EmailAccountOut,
    GmailTokenHealthAccount,
    GmailTokenHealthResponse,
    OAuthStartResponse,
)
from app.providers.gmail import verify_gmail_connection

router = APIRouter(prefix="/email-accounts", tags=["email-accounts"])
logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GMAIL_SCOPES = (
    "openid email "
    "https://www.googleapis.com/auth/gmail.modify "
    "https://www.googleapis.com/auth/gmail.send"
)

DEFAULT_SYNC_CURSOR = json.dumps({"history_id": None, "last_polled_at": None})


def _build_google_auth_url(state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": GMAIL_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


@router.post("/gmail/start-oauth", response_model=OAuthStartResponse)
def start_gmail_oauth(
    auth: AuthContext = Depends(get_current_user),
) -> OAuthStartResponse:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth is not configured on the server",
        )
    state_token = create_access_token(
        {"sub": str(auth.user_id), "tenant_id": str(auth.tenant_id), "purpose": "oauth"}
    )
    auth_url = _build_google_auth_url(state_token)
    return OAuthStartResponse(auth_url=auth_url)


@router.get("/gmail/oauth-callback")
def gmail_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    payload = decode_access_token(state)
    if payload is None or payload.get("purpose") != "oauth":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired state"
        )
    tenant_id = uuid.UUID(payload["tenant_id"])

    token_data = _exchange_code_for_tokens(code)
    user_info = _get_google_user_info(token_data["access_token"])
    email_address = user_info["email"]
    display_name = user_info.get("name") or None

    oauth_blob = json.dumps(
        {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "token_uri": GOOGLE_TOKEN_URL,
            "scopes": GMAIL_SCOPES,
            "expires_in": token_data.get("expires_in"),
        }
    )

    existing = (
        db.query(EmailAccount)
        .filter(
            EmailAccount.tenant_id == tenant_id,
            EmailAccount.email_address == email_address,
        )
        .first()
    )

    if existing:
        existing.oauth_encrypted = encrypt(oauth_blob)
        existing.status = "active"
        existing.sync_cursor_json = DEFAULT_SYNC_CURSOR
        existing.display_name = display_name
    else:
        db.add(
            EmailAccount(
                tenant_id=tenant_id,
                email_address=email_address,
                display_name=display_name,
                provider="gmail",
                oauth_encrypted=encrypt(oauth_blob),
                sync_cursor_json=DEFAULT_SYNC_CURSOR,
                status="active",
            )
        )

    db.commit()
    return RedirectResponse(url="http://localhost:3000/settings?gmail=connected")


def _exchange_code_for_tokens(code: str) -> dict:
    resp = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Google token exchange failed: {resp.text}",
        )
    return resp.json()


def _get_google_user_info(access_token: str) -> dict:
    """Fetch email and optional display name from Google OAuth2 userinfo."""
    resp = httpx.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch user info from Google",
        )
    data = resp.json()
    email = data.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google did not return an email address",
        )
    return {"email": email, "name": (data.get("name") or "").strip() or None}


@router.get("/gmail-token-health", response_model=GmailTokenHealthResponse)
def gmail_token_health(
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GmailTokenHealthResponse:
    """Check whether each active Gmail account can refresh or use its OAuth token."""
    accounts = (
        db.query(EmailAccount)
        .filter(
            EmailAccount.tenant_id == auth.tenant_id,
            EmailAccount.status == "active",
            EmailAccount.provider == "gmail",
        )
        .order_by(EmailAccount.created_at)
        .all()
    )
    out: list[GmailTokenHealthAccount] = []
    for acc in accounts:
        ok, detail = verify_gmail_connection(acc, db)
        out.append(GmailTokenHealthAccount(id=acc.id, ok=ok, detail=detail))
    return GmailTokenHealthResponse(accounts=out)


@router.get("", response_model=list[EmailAccountOut])
def list_email_accounts(
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[EmailAccountOut]:
    accounts = (
        db.query(EmailAccount)
        .filter(EmailAccount.tenant_id == auth.tenant_id)
        .order_by(EmailAccount.created_at)
        .all()
    )
    return accounts


@router.post("/{account_id}/disconnect", response_model=EmailAccountDisconnected)
def disconnect_email_account(
    account_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailAccountDisconnected:
    account = (
        db.query(EmailAccount)
        .filter(
            EmailAccount.id == account_id,
            EmailAccount.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Email account not found")
    account.status = "disconnected"
    db.commit()
    db.refresh(account)
    return EmailAccountDisconnected(id=account.id, status=account.status)


@router.delete("/{account_id}/messages")
def delete_account_messages(
    account_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Wipe all ingested data for an account: messages, extractions, jobs, contacts. Resets sync cursor."""
    account = (
        db.query(EmailAccount)
        .filter(
            EmailAccount.id == account_id,
            EmailAccount.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Email account not found")

    from app.models.contact import Contact, ContactAffiliation, JobContact
    from app.models.job import (
        Job,
        JobEvent,
        JobIdentity,
        JobManualChange,
        JobStageHistory,
        JobThread,
    )
    from app.models.merge_suggestion import JobMergeSuggestion
    from app.models.message import Message
    from app.models.message_extraction import MessageExtraction

    tenant_id = auth.tenant_id

    # Delete in FK-safe order: leaves first, then parents.
    # Job child tables
    db.query(JobManualChange).filter(JobManualChange.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(JobStageHistory).filter(JobStageHistory.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(JobEvent).filter(JobEvent.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(JobThread).filter(JobThread.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(JobIdentity).filter(JobIdentity.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(JobContact).filter(JobContact.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(JobMergeSuggestion).filter(JobMergeSuggestion.tenant_id == tenant_id).delete(synchronize_session=False)

    del_jobs = db.query(Job).filter(Job.tenant_id == tenant_id).delete(synchronize_session=False)

    # Contact tables
    db.query(ContactAffiliation).filter(ContactAffiliation.tenant_id == tenant_id).delete(synchronize_session=False)
    del_contacts = db.query(Contact).filter(Contact.tenant_id == tenant_id).delete(synchronize_session=False)

    # Extractions and messages (scoped to this account)
    msg_ids = [
        row[0]
        for row in db.query(Message.id).filter(Message.account_id == account.id).all()
    ]
    del_extractions = 0
    if msg_ids:
        del_extractions = (
            db.query(MessageExtraction)
            .filter(MessageExtraction.message_id.in_(msg_ids))
            .delete(synchronize_session=False)
        )
    del_messages = (
        db.query(Message)
        .filter(Message.account_id == account.id)
        .delete(synchronize_session=False)
    )

    account.sync_cursor_json = DEFAULT_SYNC_CURSOR
    db.commit()

    return {
        "deleted_messages": del_messages,
        "deleted_extractions": del_extractions,
        "deleted_jobs": del_jobs,
        "deleted_contacts": del_contacts,
    }


@router.post("/{account_id}/sync")
def trigger_sync(
    account_id: uuid.UUID,
    lookback_days: int = Query(default=None, ge=1, le=365),
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    account = (
        db.query(EmailAccount)
        .filter(
            EmailAccount.id == account_id,
            EmailAccount.tenant_id == auth.tenant_id,
            EmailAccount.status == "active",
        )
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Email account not found or inactive")

    ok, token_err = verify_gmail_connection(account, db)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=token_err or "Gmail authentication failed. Reconnect in Settings.",
        )

    from app.workers.connection import task_queue
    from app.workers.jobs import sync_account

    job = task_queue.enqueue(
        sync_account,
        str(account.id),
        lookback_days,
        job_timeout=settings.rq_job_timeout,
    )
    logger.info(
        "Sync enqueued account_id=%s job_id=%s lookback_days=%s (worker must be running to process)",
        account_id,
        job.id,
        lookback_days,
    )
    return {
        "status": "enqueued",
        "job_id": job.id,
        "lookback_days": lookback_days,
    }
