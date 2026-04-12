import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    AgentRun,
    BrandPattern,
    Campaign,
    CampaignArtifact,
    CampaignArtifactRevision,
    CampaignStatus,
    MemoryRecord,
    MemoryScope,
    ProductUpload,
    Project,
    Task,
    TaskStatus,
    TrendRecommendation,
)
from app.services.task_manager import (
    create_task,
    heartbeat,
    mark_stale_if_needed,
    recover_stale_task,
    save_checkpoint,
    transition_task,
)
from app.services.workflow_engine import TemporalWorkflowEngine, WorkflowEngine
from app.services.workers import (
    BrandPatternAgent,
    CampaignGeneratorAgent,
    DeliverablesAgent,
    PageAnalyzerAgent,
    QAComplianceAgent,
    StrategyPlannerAgent,
    TrendScoutAgent,
    VisionProductAgent,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SupervisorAgent:
    def __init__(self, workflow_engine: WorkflowEngine | None = None) -> None:
        self.workflow_engine = workflow_engine or TemporalWorkflowEngine()
        self.trend_scout = TrendScoutAgent()
        self.page_analyzer = PageAnalyzerAgent()
        self.brand_pattern_agent = BrandPatternAgent()
        self.vision_agent = VisionProductAgent()
        self.strategy_planner = StrategyPlannerAgent()
        self.generator = CampaignGeneratorAgent()
        self.deliverables_agent = DeliverablesAgent()
        self.qa_agent = QAComplianceAgent()

    def _create_agent_run(self, db: Session, task_id: str, agent_name: str, status: str, details: dict | None = None) -> AgentRun:
        run = AgentRun(task_id=task_id, agent_name=agent_name, status=status, details=details or {})
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def _artifact_content(self, campaign_bundle: dict, artifact_type: str) -> str:
        mapping = {
            "hero": lambda b: json.dumps(b["hero"]),
            "product_description": lambda b: b["product_description"],
            "ads": lambda b: json.dumps(b["ads"]),
            "email": lambda b: b["email"],
            "social": lambda b: b["social"],
            "page_draft": lambda b: b["page_draft"],
            "creative_brief": lambda b: json.dumps(b["creative_brief"]),
            "image_concepts": lambda b: b["image_concepts"],
            "video_script": lambda b: b["video_script"],
        }
        if artifact_type not in mapping:
            raise ValueError("Unsupported artifact type")
        return mapping[artifact_type](campaign_bundle)

    def _prompt_version(self, artifact_type: str, campaign_bundle: dict | None = None, campaign: Campaign | None = None) -> str:
        if campaign_bundle and campaign_bundle.get("_prompt_versions", {}).get(artifact_type):
            return campaign_bundle["_prompt_versions"][artifact_type]
        if campaign and campaign.prompt_context.get("prompt_versions", {}).get(artifact_type):
            return campaign.prompt_context["prompt_versions"][artifact_type]
        return "unknown"

    def _snapshot_artifact_revision(self, db: Session, artifact: CampaignArtifact, source: str) -> CampaignArtifactRevision:
        revision = CampaignArtifactRevision(
            artifact_id=artifact.id,
            campaign_id=artifact.campaign_id,
            artifact_type=artifact.artifact_type,
            content=artifact.content,
            source=source,
        )
        db.add(revision)
        return revision

    def run_trend_scan(
        self,
        db: Session,
        project: Project,
        idempotency_key: str,
        source_type: str | None = None,
    ) -> Task:
        task = create_task(db, project.id, "trend_scan", "SupervisorAgent", idempotency_key)
        transition_task(db, task, TaskStatus.running)
        heartbeat(db, task)
        save_checkpoint(db, task, "trend_scan_started", {"project_id": project.id})

        run = self._create_agent_run(db, task.id, self.trend_scout.name, "running")
        effective_tags = list(project.niche_tags)
        if source_type in {"instagram", "x"}:
            effective_tags = [tag for tag in effective_tags if tag.lower() not in {"instagram", "x"}]
            effective_tags.append(source_type)
            project.niche_tags = effective_tags
            project.selected_recommendation_id = None
            db.add(project)
        db.query(TrendRecommendation).filter(TrendRecommendation.project_id == project.id).delete()
        recommendations = self.trend_scout.run(effective_tags)

        for recommendation in recommendations:
            rec = TrendRecommendation(project_id=project.id, **recommendation)
            db.add(rec)
        run.status = "completed"
        run.ended_at = utcnow()
        db.add(run)

        save_checkpoint(db, task, "trend_scan_saved", {"count": len(recommendations)})
        heartbeat(db, task)
        transition_task(db, task, TaskStatus.completed)
        return task

    def select_reference_page(
        self,
        db: Session,
        project: Project,
        recommendation_id: str | None = None,
        source_url: str | None = None,
        title: str | None = None,
    ) -> BrandPattern:
        recommendation: TrendRecommendation | None = None
        if recommendation_id:
            recommendation = (
                db.query(TrendRecommendation)
                .filter(TrendRecommendation.id == recommendation_id, TrendRecommendation.project_id == project.id)
                .first()
            )
            if not recommendation:
                raise ValueError("Recommendation not found")
        elif source_url and source_url.strip():
            normalized_url = source_url.strip()
            recommendation = TrendRecommendation(
                project_id=project.id,
                source_url=normalized_url,
                title=(title or "Manual trend page").strip() or "Manual trend page",
                score=1.0,
                reasons=["manual_url"],
                signals={
                    "recency": 1.0,
                    "engagement": 1.0,
                    "structural_quality": 1.0,
                    "niche_relevance": 1.0,
                    "novelty": 1.0,
                },
                selected=False,
            )
            db.add(recommendation)
            db.flush()
        else:
            raise ValueError("Provide a recommendation_id or source_url")

        db.query(TrendRecommendation).filter(TrendRecommendation.project_id == project.id).update({"selected": False})
        recommendation.selected = True
        project.selected_recommendation_id = recommendation.id

        analysis = self.page_analyzer.run(recommendation.source_url)
        extracted = self.brand_pattern_agent.run(analysis)
        pattern = BrandPattern(
            project_id=project.id,
            reference_url=recommendation.source_url,
            tone=extracted["tone"],
            headline_style=extracted["headline_style"],
            cta_style=extracted["cta_style"],
            proof_strategy=extracted["proof_strategy"],
            raw_extraction=extracted["raw_extraction"],
            anonymized_features=extracted["anonymized_features"],
            provenance={"source": recommendation.source_url, "agent": self.brand_pattern_agent.name},
        )

        # Global cross-account memory: store raw + anonymized with explicit sharing signal.
        raw_memory = MemoryRecord(
            tenant_id=project.tenant_id,
            project_id=project.id,
            scope=MemoryScope.raw.value,
            share_globally=False,
            data={"pattern": extracted["raw_extraction"]},
            provenance={"reference_url": recommendation.source_url},
        )
        anonymized_memory = MemoryRecord(
            tenant_id=project.tenant_id,
            project_id=project.id,
            scope=MemoryScope.anonymized.value,
            share_globally=True,
            data={"pattern": extracted["anonymized_features"]},
            provenance={"reference_url": recommendation.source_url},
        )

        db.add(project)
        db.add(pattern)
        db.add(raw_memory)
        db.add(anonymized_memory)
        db.commit()
        db.refresh(pattern)
        return pattern

    def generate_campaign_async(self, session_factory, project_id: str, upload_id: str, idempotency_key: str) -> tuple[str, str]:
        db: Session = session_factory()
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise ValueError("Project not found")
            upload = db.query(ProductUpload).filter(ProductUpload.id == upload_id, ProductUpload.project_id == project_id).first()
            if not upload:
                raise ValueError("Product upload not found")
            upload_path = upload.file_path

            campaign = Campaign(project_id=project_id, status=CampaignStatus.draft.value)
            db.add(campaign)
            db.commit()
            db.refresh(campaign)

            task = create_task(db, project_id, "campaign_generate", "SupervisorAgent", idempotency_key)

            def workflow() -> None:
                wf_db: Session = session_factory()
                try:
                    wf_task = wf_db.query(Task).filter(Task.id == task.id).first()
                    wf_project = wf_db.query(Project).filter(Project.id == project_id).first()
                    wf_campaign = wf_db.query(Campaign).filter(Campaign.id == campaign.id).first()
                    if not wf_task or not wf_project or not wf_campaign:
                        return

                    transition_task(wf_db, wf_task, TaskStatus.running)
                    heartbeat(wf_db, wf_task)
                    save_checkpoint(wf_db, wf_task, "campaign_started", {"campaign_id": wf_campaign.id})

                    selected = (
                        wf_db.query(TrendRecommendation)
                        .filter(TrendRecommendation.project_id == project_id, TrendRecommendation.selected.is_(True))
                        .first()
                    )
                    if not selected:
                        transition_task(wf_db, wf_task, TaskStatus.failed, "No selected recommendation found")
                        return

                    page_run = self._create_agent_run(wf_db, wf_task.id, self.page_analyzer.name, "running")
                    page_analysis = self.page_analyzer.run(selected.source_url)
                    page_run.status = "completed"
                    page_run.ended_at = utcnow()
                    wf_db.add(page_run)
                    heartbeat(wf_db, wf_task)
                    save_checkpoint(wf_db, wf_task, "page_analyzed", page_analysis)

                    brand_run = self._create_agent_run(wf_db, wf_task.id, self.brand_pattern_agent.name, "running")
                    brand_pattern = self.brand_pattern_agent.run(page_analysis)
                    brand_run.status = "completed"
                    brand_run.ended_at = utcnow()
                    wf_db.add(brand_run)
                    heartbeat(wf_db, wf_task)
                    save_checkpoint(wf_db, wf_task, "brand_pattern_extracted", brand_pattern)

                    vision_run = self._create_agent_run(wf_db, wf_task.id, self.vision_agent.name, "running")
                    product_context = self.vision_agent.run(upload_path)
                    vision_run.status = "completed"
                    vision_run.ended_at = utcnow()
                    wf_db.add(vision_run)
                    heartbeat(wf_db, wf_task)
                    save_checkpoint(wf_db, wf_task, "product_analyzed", product_context)

                    strategy_run = self._create_agent_run(wf_db, wf_task.id, self.strategy_planner.name, "running")
                    strategy_plan = self.strategy_planner.run(brand_pattern, product_context)
                    strategy_run.status = "completed"
                    strategy_run.ended_at = utcnow()
                    wf_db.add(strategy_run)
                    heartbeat(wf_db, wf_task)
                    save_checkpoint(wf_db, wf_task, "strategy_planned", {"strategy_plan": strategy_plan})

                    gen_run = self._create_agent_run(wf_db, wf_task.id, self.generator.name, "running")
                    campaign_bundle = self.generator.run(brand_pattern, product_context, strategy_plan=strategy_plan)
                    gen_run.status = "completed"
                    gen_run.ended_at = utcnow()
                    wf_db.add(gen_run)
                    heartbeat(wf_db, wf_task)
                    save_checkpoint(wf_db, wf_task, "campaign_generated", {"keys": list(campaign_bundle.keys())})

                    qa_run = self._create_agent_run(wf_db, wf_task.id, self.qa_agent.name, "running")
                    qa_result = self.qa_agent.run(campaign_bundle)
                    qa_run.status = "completed"
                    qa_run.ended_at = utcnow()
                    wf_db.add(qa_run)
                    heartbeat(wf_db, wf_task)
                    save_checkpoint(wf_db, wf_task, "qa_completed", qa_result)

                    if not qa_result.get("ready_for_draft"):
                        transition_task(wf_db, wf_task, TaskStatus.blocked, "QA checks failed")
                        return

                    artifact_pairs = [
                        ("hero", self._artifact_content(campaign_bundle, "hero")),
                        ("product_description", self._artifact_content(campaign_bundle, "product_description")),
                        ("ads", self._artifact_content(campaign_bundle, "ads")),
                        ("email", self._artifact_content(campaign_bundle, "email")),
                        ("social", self._artifact_content(campaign_bundle, "social")),
                        ("page_draft", self._artifact_content(campaign_bundle, "page_draft")),
                        ("creative_brief", self._artifact_content(campaign_bundle, "creative_brief")),
                        ("image_concepts", self._artifact_content(campaign_bundle, "image_concepts")),
                        ("video_script", self._artifact_content(campaign_bundle, "video_script")),
                    ]
                    for artifact_type, content in artifact_pairs:
                        artifact_idempotency = f"{wf_campaign.id}:{artifact_type}:{wf_task.idempotency_key}"
                        exists = (
                            wf_db.query(CampaignArtifact)
                            .filter(CampaignArtifact.idempotency_key == artifact_idempotency)
                            .first()
                        )
                        if exists:
                            continue
                        artifact = CampaignArtifact(
                            campaign_id=wf_campaign.id,
                            artifact_type=artifact_type,
                            content=content,
                            idempotency_key=artifact_idempotency,
                            provenance={
                                "task_id": wf_task.id,
                                "agent": self.generator.name,
                                "prompt_version": self._prompt_version(artifact_type, campaign_bundle=campaign_bundle),
                            },
                        )
                        wf_db.add(artifact)

                    wf_campaign.prompt_context = {
                        "brand_pattern": brand_pattern,
                        "product_context": product_context,
                        "strategy_plan": strategy_plan,
                        "qa": qa_result,
                        "prompt_versions": campaign_bundle.get("_prompt_versions", {}),
                    }
                    wf_db.add(wf_campaign)
                    heartbeat(wf_db, wf_task)
                    save_checkpoint(wf_db, wf_task, "artifacts_saved", {"campaign_id": wf_campaign.id})
                    transition_task(wf_db, wf_task, TaskStatus.completed)
                except Exception as exc:
                    wf_task = wf_db.query(Task).filter(Task.id == task.id).first()
                    if wf_task:
                        wf_task.status = TaskStatus.failed.value
                        wf_task.error_reason = str(exc)
                        wf_db.add(wf_task)
                    wf_db.commit()
                finally:
                    wf_db.close()

            self.workflow_engine.run_async(workflow)
            return task.id, campaign.id
        finally:
            db.close()

    def regenerate_artifact(
        self,
        db: Session,
        project_id: str,
        campaign_id: str,
        artifact_type: str,
        instruction: str | None = None,
    ) -> CampaignArtifact:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.project_id == project_id).first()
        if not campaign:
            raise ValueError("Campaign not found")
        context = campaign.prompt_context or {}
        brand_pattern = context.get("brand_pattern")
        product_context = context.get("product_context")
        strategy_plan = context.get("strategy_plan")
        if not brand_pattern or not product_context:
            raise ValueError("Campaign context missing for regeneration")

        normalized_instruction = instruction.strip() if instruction and instruction.strip() else None
        artifact_instructions = {artifact_type: normalized_instruction} if normalized_instruction else None
        campaign_bundle = self.generator.run(
            brand_pattern,
            product_context,
            artifact_instructions=artifact_instructions,
            strategy_plan=strategy_plan,
        )
        content = self._artifact_content(campaign_bundle, artifact_type)

        artifact = (
            db.query(CampaignArtifact)
            .filter(CampaignArtifact.campaign_id == campaign_id, CampaignArtifact.artifact_type == artifact_type)
            .order_by(CampaignArtifact.created_at.desc())
            .first()
        )
        if artifact:
            self._snapshot_artifact_revision(db, artifact, source="regenerate")
            artifact.content = content
            artifact.provenance = {
                "regenerated": True,
                "agent": self.generator.name,
                "at": utcnow().isoformat(),
                "prompt_version": self._prompt_version(artifact_type, campaign_bundle=campaign_bundle, campaign=campaign),
            }
            if normalized_instruction:
                artifact.provenance["instruction"] = normalized_instruction
            db.add(artifact)
            db.commit()
            db.refresh(artifact)
            return artifact

        new_artifact = CampaignArtifact(
            campaign_id=campaign_id,
            artifact_type=artifact_type,
            content=content,
            idempotency_key=f"{campaign_id}:{artifact_type}:regen:{uuid.uuid4()}",
            provenance={
                "regenerated": True,
                "agent": self.generator.name,
                "at": utcnow().isoformat(),
                "prompt_version": self._prompt_version(artifact_type, campaign_bundle=campaign_bundle, campaign=campaign),
            },
        )
        if normalized_instruction:
            new_artifact.provenance["instruction"] = normalized_instruction
        db.add(new_artifact)
        db.commit()
        db.refresh(new_artifact)
        return new_artifact

    def build_deliverables(self, db: Session, project_id: str, campaign_id: str) -> dict:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.project_id == project_id).first()
        if not campaign:
            raise ValueError("Campaign not found")
        artifacts = db.query(CampaignArtifact).filter(CampaignArtifact.campaign_id == campaign_id).all()
        if not artifacts:
            raise ValueError("Campaign artifacts not found")
        artifact_map = {artifact.artifact_type: artifact.content for artifact in artifacts}
        prompt_context = campaign.prompt_context or {}
        strategy_plan = prompt_context.get("strategy_plan")
        product_context = prompt_context.get("product_context") or {}
        output_dir = Path(settings.uploads_dir) / project_id / "generated" / campaign_id
        deliverables = self.deliverables_agent.run(
            artifact_map,
            strategy_plan=strategy_plan,
            output_dir=str(output_dir),
            reference_image_path=product_context.get("image_path"),
        )
        campaign.prompt_context = {**(campaign.prompt_context or {}), "deliverables": deliverables}
        db.add(campaign)
        db.commit()
        return deliverables

    def watchdog_scan(self, db: Session) -> list[str]:
        changed: list[str] = []
        running_tasks = db.query(Task).filter(Task.status.in_([TaskStatus.running.value, TaskStatus.stale.value])).all()
        for task in running_tasks:
            before = task.status
            task = mark_stale_if_needed(db, task)
            if task.status == TaskStatus.stale.value:
                task = recover_stale_task(db, task)
            if task.status != before:
                changed.append(task.id)
        return changed
