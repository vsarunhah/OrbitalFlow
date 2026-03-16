from pydantic import BaseModel, Field


class TenantSettingsResponse(BaseModel):
    labeling_enabled: bool
    labeling_confidence_threshold: float
    label_status: str
    label_recruiter: str
    label_alerts: str

    model_config = {"from_attributes": True}


class TenantSettingsUpdate(BaseModel):
    labeling_enabled: bool | None = None
    labeling_confidence_threshold: float | None = Field(None, ge=0.0, le=1.0)
    label_status: str | None = Field(None, min_length=1, max_length=255)
    label_recruiter: str | None = Field(None, min_length=1, max_length=255)
    label_alerts: str | None = Field(None, min_length=1, max_length=255)
