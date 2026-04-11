from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    tenant_id: str
    name: str
    niche_tags: list[str] = Field(default_factory=list)


class ProjectOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    niche_tags: list[str]
    selected_recommendation_id: str | None
    created_at: datetime


class TrendScanRequest(BaseModel):
    force_refresh: bool = False


class TrendRecommendationOut(BaseModel):
    id: str
    source_url: str
    title: str
    score: float
    reasons: list[str]
    signals: dict
    selected: bool


class ReferenceSelectRequest(BaseModel):
    recommendation_id: str


class CampaignGenerateRequest(BaseModel):
    idempotency_key: str


class TaskOut(BaseModel):
    id: str
    project_id: str
    task_type: str
    owner_agent: str
    status: str
    retries: int
    max_retries: int
    checkpoint: str | None
    error_reason: str | None
    heartbeat_age_seconds: int | None


class CampaignGenerateResponse(BaseModel):
    task_id: str
    campaign_id: str
    status: str


class CampaignApprovalRequest(BaseModel):
    approved_by: str
    notes: str | None = None


class CampaignArtifactOut(BaseModel):
    id: str
    artifact_type: str
    content: str
    created_at: datetime


class UploadResponse(BaseModel):
    upload_id: str
    file_path: str


class PurgeMemoryRequest(BaseModel):
    project_id: str | None = None
    scope: str | None = None


class PurgeMemoryResponse(BaseModel):
    deleted_count: int
