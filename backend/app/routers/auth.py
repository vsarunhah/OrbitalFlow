import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.auth.security import (
    create_access_token,
    create_password_reset_token,
    decode_password_reset_token,
    hash_password,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserInfo,
)
from app.services.email import send_password_reset_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = (
        db.query(User).filter(User.email == body.email).first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    tenant = Tenant(name=body.tenant_name)
    db.add(tenant)
    db.flush()

    user = User(
        tenant_id=tenant.id,
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        {"sub": str(user.id), "tenant_id": str(user.tenant_id)}
    )
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    token = create_access_token(
        {"sub": str(user.id), "tenant_id": str(user.tenant_id)}
    )
    return TokenResponse(access_token=token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(auth: AuthContext = Depends(get_current_user)) -> TokenResponse:
    """Issue a new access token using the current valid token. Call before expiry to avoid mid-session logout."""
    token = create_access_token(
        {"sub": str(auth.user_id), "tenant_id": str(auth.tenant_id)}
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserInfo)
def me(
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserInfo:
    user = db.query(User).filter(User.id == auth.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserInfo(user_id=user.id, tenant_id=user.tenant_id, email=user.email)


@router.post("/forgot-password", status_code=204)
def forgot_password(
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> None:
    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        return
    token = create_password_reset_token(str(user.id))
    reset_link = f"{settings.frontend_base_url.rstrip('/')}/reset-password?token={token}"
    send_password_reset_email(user.email, reset_link)


@router.post("/reset-password", status_code=204)
def reset_password(
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> None:
    payload = decode_password_reset_token(body.token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link",
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset link",
        )
    try:
        user_uuid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset link",
        )
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found",
        )
    user.password_hash = hash_password(body.new_password)
    db.commit()
