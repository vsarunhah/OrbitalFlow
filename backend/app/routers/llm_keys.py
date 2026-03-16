from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.database import get_db
from app.encryption import encrypt
from app.models.llm_key import LlmKey
from app.schemas.llm_key import LlmKeyStatus, SetLlmKeyRequest

router = APIRouter(prefix="/llm-keys", tags=["llm-keys"])


@router.put("", response_model=LlmKeyStatus, status_code=200)
def set_llm_key(
    body: SetLlmKeyRequest,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LlmKeyStatus:
    existing = (
        db.query(LlmKey)
        .filter(LlmKey.tenant_id == auth.tenant_id, LlmKey.provider == body.provider)
        .first()
    )

    encrypted = encrypt(body.api_key)

    if existing:
        existing.encrypted_key = encrypted
    else:
        db.add(
            LlmKey(
                tenant_id=auth.tenant_id,
                provider=body.provider,
                encrypted_key=encrypted,
            )
        )

    db.commit()
    return LlmKeyStatus(configured=True, provider=body.provider)


@router.get("", response_model=LlmKeyStatus)
def check_llm_key(
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider: str = "openai",
) -> LlmKeyStatus:
    exists = (
        db.query(LlmKey)
        .filter(LlmKey.tenant_id == auth.tenant_id, LlmKey.provider == provider)
        .first()
    )
    return LlmKeyStatus(
        configured=exists is not None,
        provider=provider if exists else None,
    )
