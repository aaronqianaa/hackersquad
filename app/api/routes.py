import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import SessionLocal, get_db
from app.models import (
    ApprovalEvent,
    BrandPattern,
    Campaign,
    CampaignArtifact,
    CampaignStatus,
    MemoryRecord,
    ProductUpload,
    Project,
    Task,
    TrendRecommendation,
)
from app.schemas import (
    CampaignApprovalRequest,
    CampaignArtifactOut,
    CampaignGenerateRequest,
    CampaignGenerateResponse,
    ProjectCreate,
    ProjectOut,
    PurgeMemoryRequest,
    PurgeMemoryResponse,
    ReferenceSelectRequest,
    TaskOut,
    TrendRecommendationOut,
    TrendScanRequest,
    UploadResponse,
)
from app.services.supervisor import SupervisorAgent
from app.services.task_manager import heartbeat_age_seconds


router = APIRouter()
supervisor = SupervisorAgent()


def to_task_out(task: Task) -> TaskOut:
    return TaskOut(
        id=task.id,
        project_id=task.project_id,
        task_type=task.task_type,
        owner_agent=task.owner_agent,
        status=task.status,
        retries=task.retries,
        max_retries=task.max_retries,
        checkpoint=task.checkpoint,
        error_reason=task.error_reason,
        heartbeat_age_seconds=heartbeat_age_seconds(task),
    )


@router.post("/projects", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectOut:
    project = Project(tenant_id=payload.tenant_id, name=payload.name, niche_tags=payload.niche_tags)
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectOut(
        id=project.id,
        tenant_id=project.tenant_id,
        name=project.name,
        niche_tags=project.niche_tags,
        selected_recommendation_id=project.selected_recommendation_id,
        created_at=project.created_at,
    )


@router.post("/projects/{project_id}/trend-scan", response_model=TaskOut)
def trend_scan(project_id: str, _: TrendScanRequest, db: Session = Depends(get_db)) -> TaskOut:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    task = supervisor.run_trend_scan(db, project, idempotency_key=f"trend:{project_id}:{uuid.uuid4()}")
    return to_task_out(task)


@router.get("/projects/{project_id}/recommendations", response_model=list[TrendRecommendationOut])
def list_recommendations(project_id: str, db: Session = Depends(get_db)) -> list[TrendRecommendationOut]:
    rows = (
        db.query(TrendRecommendation)
        .filter(TrendRecommendation.project_id == project_id)
        .order_by(TrendRecommendation.score.desc())
        .all()
    )
    return [
        TrendRecommendationOut(
            id=row.id,
            source_url=row.source_url,
            title=row.title,
            score=row.score,
            reasons=row.reasons,
            signals=row.signals,
            selected=row.selected,
        )
        for row in rows
    ]


@router.post("/projects/{project_id}/reference-page/select")
def select_reference_page(project_id: str, payload: ReferenceSelectRequest, db: Session = Depends(get_db)) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        pattern = supervisor.select_reference_page(db, project, payload.recommendation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "brand_pattern_id": pattern.id,
        "tone": pattern.tone,
        "headline_style": pattern.headline_style,
        "cta_style": pattern.cta_style,
    }


@router.post("/projects/{project_id}/uploads/product-image", response_model=UploadResponse)
def upload_product_image(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> UploadResponse:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_dir = Path(settings.uploads_dir) / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid.uuid4()}-{file.filename or 'product-image'}"
    path = project_dir / safe_name
    contents = file.file.read()
    path.write_bytes(contents)

    upload = ProductUpload(project_id=project_id, file_path=str(path), mime_type=file.content_type or "application/octet-stream")
    db.add(upload)
    db.commit()
    db.refresh(upload)
    return UploadResponse(upload_id=upload.id, file_path=upload.file_path)


@router.post("/projects/{project_id}/campaigns/generate", response_model=CampaignGenerateResponse)
def generate_campaign(project_id: str, payload: CampaignGenerateRequest, db: Session = Depends(get_db)) -> CampaignGenerateResponse:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    upload = (
        db.query(ProductUpload)
        .filter(ProductUpload.project_id == project_id)
        .order_by(ProductUpload.created_at.desc())
        .first()
    )
    if not upload:
        raise HTTPException(status_code=400, detail="Upload a product image first")

    task_id, campaign_id = supervisor.generate_campaign_async(
        SessionLocal,
        project_id=project_id,
        upload_id=upload.id,
        idempotency_key=payload.idempotency_key,
    )
    return CampaignGenerateResponse(task_id=task_id, campaign_id=campaign_id, status="running")


@router.get("/projects/{project_id}/tasks/{task_id}", response_model=TaskOut)
def get_task(project_id: str, task_id: str, db: Session = Depends(get_db)) -> TaskOut:
    task = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return to_task_out(task)


@router.post("/projects/{project_id}/campaigns/{campaign_id}/approve")
def approve_campaign(project_id: str, campaign_id: str, payload: CampaignApprovalRequest, db: Session = Depends(get_db)) -> dict:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.project_id == project_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign.status = CampaignStatus.approved.value
    event = ApprovalEvent(campaign_id=campaign.id, approved_by=payload.approved_by, notes=payload.notes)
    db.add(campaign)
    db.add(event)
    db.commit()
    return {"campaign_id": campaign.id, "status": campaign.status, "approved_by": payload.approved_by}


@router.get("/projects/{project_id}/campaigns/{campaign_id}/artifacts", response_model=list[CampaignArtifactOut])
def list_artifacts(project_id: str, campaign_id: str, db: Session = Depends(get_db)) -> list[CampaignArtifactOut]:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.project_id == project_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    artifacts = db.query(CampaignArtifact).filter(CampaignArtifact.campaign_id == campaign_id).all()
    return [
        CampaignArtifactOut(id=a.id, artifact_type=a.artifact_type, content=a.content, created_at=a.created_at)
        for a in artifacts
    ]


@router.post("/memory/purge", response_model=PurgeMemoryResponse)
def purge_memory(payload: PurgeMemoryRequest, db: Session = Depends(get_db)) -> PurgeMemoryResponse:
    query = db.query(MemoryRecord).filter(MemoryRecord.deleted_at.is_(None))
    if payload.project_id:
        query = query.filter(MemoryRecord.project_id == payload.project_id)
    if payload.scope:
        query = query.filter(MemoryRecord.scope == payload.scope)

    rows = query.all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.deleted_at = now
        db.add(row)
    db.commit()
    return PurgeMemoryResponse(deleted_count=len(rows))


@router.delete("/projects/{project_id}/uploads/{upload_id}")
def delete_upload(project_id: str, upload_id: str, db: Session = Depends(get_db)) -> dict:
    upload = db.query(ProductUpload).filter(ProductUpload.id == upload_id, ProductUpload.project_id == project_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    try:
        os.remove(upload.file_path)
    except FileNotFoundError:
        pass

    db.delete(upload)
    db.commit()
    return {"deleted": True, "upload_id": upload_id}
