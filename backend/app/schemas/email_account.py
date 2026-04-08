import uuid
from datetime import datetime

from pydantic import BaseModel


class OAuthStartResponse(BaseModel):
    auth_url: str


class EmailAccountOut(BaseModel):
    id: uuid.UUID
    email_address: str
    provider: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmailAccountDisconnected(BaseModel):
    id: uuid.UUID
    status: str


class GmailTokenHealthAccount(BaseModel):
    id: uuid.UUID
    ok: bool
    detail: str | None = None


class GmailTokenHealthResponse(BaseModel):
    accounts: list[GmailTokenHealthAccount]
