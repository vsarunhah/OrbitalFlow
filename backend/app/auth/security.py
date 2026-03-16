from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None


PASSWORD_RESET_PURPOSE = "password_reset"


def create_password_reset_token(user_id: str) -> str:
    to_encode = {
        "sub": user_id,
        "purpose": PASSWORD_RESET_PURPOSE,
        "exp": datetime.now(timezone.utc)
        + timedelta(minutes=settings.password_reset_expire_minutes),
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_password_reset_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        if payload.get("purpose") != PASSWORD_RESET_PURPOSE:
            return None
        return payload
    except JWTError:
        return None


# Password reset token: short-lived JWT with purpose="password_reset"
PASSWORD_RESET_EXPIRE_MINUTES = 60


def create_password_reset_token(user_id: str) -> str:
    to_encode = {
        "sub": user_id,
        "purpose": "password_reset",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES),
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_password_reset_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("purpose") != "password_reset":
            return None
        return payload
    except JWTError:
        return None
