"""Load and update per-user job-search profile."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_profile import UserProfile
from app.schemas.user_profile import UserProfileSchema, UserProfileUpdateRequest


def get_or_create_profile(
    db: Session, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> UserProfile:
    row = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if row:
        return row
    row = UserProfile(user_id=user_id, tenant_id=tenant_id)
    db.add(row)
    db.flush()
    return row


def profile_to_schema(row: UserProfile) -> UserProfileSchema:
    sizes = row.preferred_company_sizes if isinstance(row.preferred_company_sizes, list) else []
    arrangements = row.work_arrangements if isinstance(row.work_arrangements, list) else []
    return UserProfileSchema(
        display_name=row.display_name,
        timezone=row.timezone,
        location_preferences=row.location_preferences,
        work_arrangements=arrangements,
        compensation_expectations=row.compensation_expectations,
        preferred_company_sizes=sizes,
        availability_notes=row.availability_notes,
    )


def apply_profile_update(row: UserProfile, body: UserProfileUpdateRequest) -> None:
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)


def profile_summary_for_prompt(row: UserProfile | None, user: User | None) -> str:
    """Short text block for LLM context (non-tool path)."""
    if row is None and user is None:
        return "Job seeker profile: not configured."
    parts: list[str] = []
    name = (row.display_name if row else None) or (user.email if user else None) or "User"
    parts.append(f"Name: {name}")
    if row:
        if row.timezone:
            parts.append(f"Timezone: {row.timezone}")
        if row.work_arrangements and isinstance(row.work_arrangements, list):
            parts.append(f"Work arrangements: {', '.join(row.work_arrangements)}")
        if row.location_preferences:
            parts.append(f"Location preferences: {row.location_preferences}")
        if row.compensation_expectations:
            parts.append(f"Compensation expectations: {row.compensation_expectations}")
        if row.preferred_company_sizes:
            parts.append(f"Preferred company sizes: {', '.join(row.preferred_company_sizes)}")
        if row.availability_notes:
            parts.append(f"Availability notes: {row.availability_notes}")
    return "Job seeker profile:\n" + "\n".join(parts)


def profile_dict_for_agent(row: UserProfile | None, user: User | None) -> dict:
    """Structured profile returned by get_user_profile tool."""
    if row is None and user is None:
        return {"configured": False}
    sizes = []
    if row and isinstance(row.preferred_company_sizes, list):
        sizes = row.preferred_company_sizes
    arrangements = []
    if row and isinstance(row.work_arrangements, list):
        arrangements = row.work_arrangements
    return {
        "configured": bool(
            row
            and any(
                [
                    row.display_name,
                    row.timezone,
                    row.location_preferences,
                    arrangements,
                    row.compensation_expectations,
                    sizes,
                    row.availability_notes,
                ]
            )
        ),
        "display_name": (row.display_name if row else None)
        or (user.email.split("@")[0] if user else None),
        "email": user.email if user else None,
        "timezone": row.timezone if row else None,
        "work_arrangements": arrangements,
        "location_preferences": row.location_preferences if row else None,
        "compensation_expectations": row.compensation_expectations if row else None,
        "preferred_company_sizes": sizes,
        "availability_notes": row.availability_notes if row else None,
    }
