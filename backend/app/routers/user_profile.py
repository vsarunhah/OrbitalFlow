"""Job-seeker profile API (preferences for AI drafts)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.database import get_db
from app.schemas.user_profile import UserProfileSchema, UserProfileUpdateRequest
from app.services.user_profile import (
    apply_profile_update,
    get_or_create_profile,
    profile_to_schema,
)

router = APIRouter(prefix="/user/profile", tags=["user-profile"])


@router.get("", response_model=UserProfileSchema)
def get_profile(
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfileSchema:
    row = get_or_create_profile(db, auth.user_id, auth.tenant_id)
    db.commit()
    return profile_to_schema(row)


@router.patch("", response_model=UserProfileSchema)
def update_profile(
    body: UserProfileUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfileSchema:
    row = get_or_create_profile(db, auth.user_id, auth.tenant_id)
    apply_profile_update(row, body)
    db.commit()
    db.refresh(row)
    return profile_to_schema(row)
