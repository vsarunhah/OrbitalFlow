import uuid

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    tenant_name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserInfo(BaseModel):
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
