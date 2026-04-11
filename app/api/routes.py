import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.security import AuthContext, get_auth_context
from app.core.config import settings
from app.db import SessionLocal, get_db
from app.models import (
    ApprovalEvent,
    Campaign,
    CampaignArtifact,
    CampaignArtifactRevision,
    CampaignStatus,
    MemoryRecord,
    ProductUpload,
    Project,
    Task,
    TrendRecommendation,
)
from app.schemas import (
    ArtifactRegenerateRequest,
    ArtifactRestoreRequest,
    ArtifactUpdateRequest,
    CampaignListOut,
    CampaignApprovalRequest,
    CampaignArtifactOut,
    CampaignArtifactRevisionOut,
    CampaignGenerateRequest,
    CampaignGenerateResponse,
    OpenAIKeyUpdateRequest,
    ProjectCreate,
    ProjectOut,
    PurgeMemoryRequest,
    PurgeMemoryResponse,
    ReferenceSelectRequest,
    TaskOut,
    TaskSummaryOut,
    TrendRecommendationOut,
    TrendScanRequest,
    UploadResponse,
)
from app.services.supervisor import SupervisorAgent
from app.services.task_manager import heartbeat_age_seconds


router = APIRouter()
supervisor = SupervisorAgent()


@router.post("/settings/openai-key")
def set_openai_key(payload: OpenAIKeyUpdateRequest) -> dict:
    settings.openai_api_key = payload.api_key.strip()
    return {"configured": bool(settings.openai_api_key)}


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


def require_project_access(db: Session, project_id: str, auth: AuthContext) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if auth.tenant_id and project.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=403, detail="Project is not accessible for this tenant")
    return project


def to_project_out(project: Project) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        tenant_id=project.tenant_id,
        name=project.name,
        niche_tags=project.niche_tags,
        selected_recommendation_id=project.selected_recommendation_id,
        created_at=project.created_at,
    )


@router.post("/projects", response_model=ProjectOut)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ProjectOut:
    if auth.tenant_id and payload.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=403, detail="Payload tenant does not match tenant header")
    project = Project(tenant_id=payload.tenant_id, name=payload.name, niche_tags=payload.niche_tags)
    db.add(project)
    db.commit()
    db.refresh(project)
    return to_project_out(project)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[ProjectOut]:
    query = db.query(Project)
    if auth.tenant_id:
        query = query.filter(Project.tenant_id == auth.tenant_id)
    projects = query.order_by(Project.created_at.desc()).all()
    return [to_project_out(project) for project in projects]


@router.post("/projects/{project_id}/trend-scan", response_model=TaskOut)
def trend_scan(
    project_id: str,
    _: TrendScanRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TaskOut:
    project = require_project_access(db, project_id, auth)
    task = supervisor.run_trend_scan(db, project, idempotency_key=f"trend:{project_id}:{uuid.uuid4()}")
    return to_task_out(task)


@router.get("/projects/{project_id}/recommendations", response_model=list[TrendRecommendationOut])
def list_recommendations(
    project_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[TrendRecommendationOut]:
    require_project_access(db, project_id, auth)
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
def select_reference_page(
    project_id: str,
    payload: ReferenceSelectRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    project = require_project_access(db, project_id, auth)
    try:
        pattern = supervisor.select_reference_page(
            db,
            project,
            recommendation_id=payload.recommendation_id,
            source_url=payload.source_url,
            title=payload.title,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return {
        "brand_pattern_id": pattern.id,
        "tone": pattern.tone,
        "headline_style": pattern.headline_style,
        "cta_style": pattern.cta_style,
    }


@router.post("/projects/{project_id}/uploads/product-image", response_model=UploadResponse)
def upload_product_image(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> UploadResponse:
    require_project_access(db, project_id, auth)

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
def generate_campaign(
    project_id: str,
    payload: CampaignGenerateRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> CampaignGenerateResponse:
    require_project_access(db, project_id, auth)

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
def get_task(
    project_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TaskOut:
    require_project_access(db, project_id, auth)
    task = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return to_task_out(task)


@router.get("/projects/{project_id}/tasks", response_model=list[TaskOut])
def list_tasks(
    project_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[TaskOut]:
    require_project_access(db, project_id, auth)
    tasks = db.query(Task).filter(Task.project_id == project_id).order_by(Task.created_at.desc()).all()
    return [to_task_out(task) for task in tasks]


@router.post("/projects/{project_id}/campaigns/{campaign_id}/approve")
def approve_campaign(
    project_id: str,
    campaign_id: str,
    payload: CampaignApprovalRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    require_project_access(db, project_id, auth)
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
def list_artifacts(
    project_id: str,
    campaign_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[CampaignArtifactOut]:
    require_project_access(db, project_id, auth)
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.project_id == project_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    artifacts = db.query(CampaignArtifact).filter(CampaignArtifact.campaign_id == campaign_id).all()
    return [
        CampaignArtifactOut(id=a.id, artifact_type=a.artifact_type, content=a.content, created_at=a.created_at)
        for a in artifacts
    ]


@router.post("/projects/{project_id}/campaigns/{campaign_id}/artifacts/regenerate", response_model=CampaignArtifactOut)
def regenerate_artifact(
    project_id: str,
    campaign_id: str,
    payload: ArtifactRegenerateRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> CampaignArtifactOut:
    require_project_access(db, project_id, auth)
    try:
        artifact = supervisor.regenerate_artifact(
            db,
            project_id,
            campaign_id,
            payload.artifact_type,
            instruction=payload.instruction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CampaignArtifactOut(
        id=artifact.id,
        artifact_type=artifact.artifact_type,
        content=artifact.content,
        created_at=artifact.created_at,
    )


@router.put("/projects/{project_id}/campaigns/{campaign_id}/artifacts/{artifact_id}", response_model=CampaignArtifactOut)
def update_artifact(
    project_id: str,
    campaign_id: str,
    artifact_id: str,
    payload: ArtifactUpdateRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> CampaignArtifactOut:
    require_project_access(db, project_id, auth)
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.project_id == project_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    artifact = (
        db.query(CampaignArtifact)
        .filter(CampaignArtifact.id == artifact_id, CampaignArtifact.campaign_id == campaign_id)
        .first()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    revision = CampaignArtifactRevision(
        artifact_id=artifact.id,
        campaign_id=campaign_id,
        artifact_type=artifact.artifact_type,
        content=artifact.content,
        source="manual_edit",
    )
    db.add(revision)
    artifact.content = payload.content
    artifact.provenance = {"edited": True, "edited_at": datetime.now(timezone.utc).isoformat()}
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return CampaignArtifactOut(
        id=artifact.id,
        artifact_type=artifact.artifact_type,
        content=artifact.content,
        created_at=artifact.created_at,
    )


@router.get(
    "/projects/{project_id}/campaigns/{campaign_id}/artifacts/{artifact_id}/revisions",
    response_model=list[CampaignArtifactRevisionOut],
)
def list_artifact_revisions(
    project_id: str,
    campaign_id: str,
    artifact_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[CampaignArtifactRevisionOut]:
    require_project_access(db, project_id, auth)
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.project_id == project_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    artifact = (
        db.query(CampaignArtifact)
        .filter(CampaignArtifact.id == artifact_id, CampaignArtifact.campaign_id == campaign_id)
        .first()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    revisions = (
        db.query(CampaignArtifactRevision)
        .filter(CampaignArtifactRevision.artifact_id == artifact_id, CampaignArtifactRevision.campaign_id == campaign_id)
        .order_by(CampaignArtifactRevision.created_at.desc())
        .all()
    )
    return [
        CampaignArtifactRevisionOut(
            id=r.id,
            artifact_id=r.artifact_id,
            campaign_id=r.campaign_id,
            artifact_type=r.artifact_type,
            content=r.content,
            source=r.source,
            created_at=r.created_at,
        )
        for r in revisions
    ]


@router.post(
    "/projects/{project_id}/campaigns/{campaign_id}/artifacts/{artifact_id}/restore",
    response_model=CampaignArtifactOut,
)
def restore_artifact_revision(
    project_id: str,
    campaign_id: str,
    artifact_id: str,
    payload: ArtifactRestoreRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> CampaignArtifactOut:
    require_project_access(db, project_id, auth)
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.project_id == project_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    artifact = (
        db.query(CampaignArtifact)
        .filter(CampaignArtifact.id == artifact_id, CampaignArtifact.campaign_id == campaign_id)
        .first()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    revision = (
        db.query(CampaignArtifactRevision)
        .filter(
            CampaignArtifactRevision.id == payload.revision_id,
            CampaignArtifactRevision.artifact_id == artifact_id,
            CampaignArtifactRevision.campaign_id == campaign_id,
        )
        .first()
    )
    if not revision:
        raise HTTPException(status_code=404, detail="Revision not found")

    # Save current content before restore for full reversibility.
    db.add(
        CampaignArtifactRevision(
            artifact_id=artifact.id,
            campaign_id=campaign_id,
            artifact_type=artifact.artifact_type,
            content=artifact.content,
            source="restore_snapshot",
        )
    )
    artifact.content = revision.content
    artifact.provenance = {
        "restored": True,
        "revision_id": revision.id,
        "restored_at": datetime.now(timezone.utc).isoformat(),
    }
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return CampaignArtifactOut(
        id=artifact.id,
        artifact_type=artifact.artifact_type,
        content=artifact.content,
        created_at=artifact.created_at,
    )


@router.get("/projects/{project_id}/campaigns", response_model=list[CampaignListOut])
def list_campaigns(
    project_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[CampaignListOut]:
    require_project_access(db, project_id, auth)
    campaigns = db.query(Campaign).filter(Campaign.project_id == project_id).order_by(Campaign.created_at.desc()).all()
    out: list[CampaignListOut] = []
    for campaign in campaigns:
        artifact_count = db.query(CampaignArtifact).filter(CampaignArtifact.campaign_id == campaign.id).count()
        out.append(
            CampaignListOut(
                id=campaign.id,
                project_id=campaign.project_id,
                status=campaign.status,
                created_at=campaign.created_at,
                artifact_count=artifact_count,
            )
        )
    return out


@router.post("/memory/purge", response_model=PurgeMemoryResponse)
def purge_memory(
    payload: PurgeMemoryRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> PurgeMemoryResponse:
    if payload.project_id:
        project = db.query(Project).filter(Project.id == payload.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        if auth.tenant_id and project.tenant_id != auth.tenant_id:
            raise HTTPException(status_code=403, detail="Project is not accessible for this tenant")
    query = db.query(MemoryRecord).filter(MemoryRecord.deleted_at.is_(None))
    if auth.tenant_id:
        query = query.filter(MemoryRecord.tenant_id == auth.tenant_id)
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
def delete_upload(
    project_id: str,
    upload_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    require_project_access(db, project_id, auth)
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


@router.get("/ops/tasks/summary", response_model=TaskSummaryOut)
def task_summary(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TaskSummaryOut:
    query = db.query(Task)
    if auth.tenant_id:
        query = query.join(Project, Project.id == Task.project_id).filter(Project.tenant_id == auth.tenant_id)

    total_tasks = query.count()
    running_tasks = query.filter(Task.status == "running").count()
    failed_tasks = query.filter(Task.status == "failed").count()
    blocked_tasks = query.filter(Task.status == "blocked").count()
    completed_tasks = query.filter(Task.status == "completed").count()

    completion_query = query.filter(Task.status == "completed").with_entities(
        func.avg(func.julianday(Task.updated_at) - func.julianday(Task.created_at))
    )
    avg_completion_seconds = completion_query.scalar()
    avg_seconds = float(avg_completion_seconds * 86400) if avg_completion_seconds else 0.0

    return TaskSummaryOut(
        total_tasks=total_tasks,
        running_tasks=running_tasks,
        failed_tasks=failed_tasks,
        blocked_tasks=blocked_tasks,
        completed_tasks=completed_tasks,
        avg_completion_seconds=round(avg_seconds, 3),
    )
