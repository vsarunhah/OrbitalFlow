from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.tenant_settings import TenantSettingsResponse, TenantSettingsUpdate
from app.services.gmail_labeling import get_or_create_tenant_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=TenantSettingsResponse)
def get_settings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = get_or_create_tenant_settings(db, user.tenant_id)
    db.commit()
    return settings


@router.patch("", response_model=TenantSettingsResponse)
def update_settings(
    body: TenantSettingsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = get_or_create_tenant_settings(db, user.tenant_id)
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)
    db.commit()
    db.refresh(settings)
    return settings
