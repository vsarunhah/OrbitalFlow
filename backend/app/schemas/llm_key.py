from pydantic import BaseModel


class SetLlmKeyRequest(BaseModel):
    api_key: str
    provider: str = "openai"


class LlmKeyStatus(BaseModel):
    configured: bool
    provider: str | None = None
