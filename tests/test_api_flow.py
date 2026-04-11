import time

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Campaign, CampaignArtifact


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _create_project_with_selection_and_upload() -> str:
    project_resp = client.post(
        "/projects",
        json={"tenant_id": "tenant-1", "name": "Demo Project", "niche_tags": ["skincare", "dtc"]},
    )
    assert project_resp.status_code == 200
    project_id = project_resp.json()["id"]

    trend_resp = client.post(f"/projects/{project_id}/trend-scan", json={"force_refresh": True})
    assert trend_resp.status_code == 200

    recs_resp = client.get(f"/projects/{project_id}/recommendations")
    assert recs_resp.status_code == 200
    recommendations = recs_resp.json()
    assert len(recommendations) > 0

    select_resp = client.post(
        f"/projects/{project_id}/reference-page/select",
        json={"recommendation_id": recommendations[0]["id"]},
    )
    assert select_resp.status_code == 200

    file_bytes = b"fake-image-content"
    upload_resp = client.post(
        f"/projects/{project_id}/uploads/product-image",
        files={"file": ("product.jpg", file_bytes, "image/jpeg")},
    )
    assert upload_resp.status_code == 200
    return project_id


def _start_and_wait_campaign(project_id: str, idempotency_key: str) -> tuple[str, str, dict]:
    final_task_payload: dict = {}
    final_task_id = ""
    final_campaign_id = ""
    for attempt in range(2):
        key = idempotency_key if attempt == 0 else f"{idempotency_key}-retry-{attempt}"
        generate_resp = client.post(
            f"/projects/{project_id}/campaigns/generate",
            json={"idempotency_key": key},
        )
        assert generate_resp.status_code == 200
        payload = generate_resp.json()
        task_id = payload["task_id"]
        campaign_id = payload["campaign_id"]

        task_payload: dict = {}
        for _ in range(50):
            task_resp = client.get(f"/projects/{project_id}/tasks/{task_id}")
            assert task_resp.status_code == 200
            task_payload = task_resp.json()
            if task_payload["status"] in {"completed", "failed", "blocked"}:
                break
            time.sleep(0.1)
        if task_payload.get("status") == "completed":
            return task_id, campaign_id, task_payload
        final_task_payload = task_payload
        final_task_id = task_id
        final_campaign_id = campaign_id
    return final_task_id, final_campaign_id, final_task_payload


def test_end_to_end_api_flow() -> None:
    project_id = _create_project_with_selection_and_upload()
    _, campaign_id, task_payload = _start_and_wait_campaign(project_id, "campaign-flow-1")
    assert task_payload["status"] == "completed"

    artifacts_resp = client.get(f"/projects/{project_id}/campaigns/{campaign_id}/artifacts")
    assert artifacts_resp.status_code == 200
    assert len(artifacts_resp.json()) >= 3

    approve_resp = client.post(
        f"/projects/{project_id}/campaigns/{campaign_id}/approve",
        json={"approved_by": "qa-user", "notes": "Looks good"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"


def test_campaign_generation_regression_no_invalid_transition_failure() -> None:
    project_id = _create_project_with_selection_and_upload()
    _, campaign_id, task_payload = _start_and_wait_campaign(project_id, "campaign-flow-regression")

    assert task_payload["status"] == "completed"
    assert task_payload.get("error_reason") in (None, "")
    assert "Invalid task transition" not in (task_payload.get("error_reason") or "")
    assert task_payload["checkpoint"] == "artifacts_saved"

    artifacts_resp = client.get(f"/projects/{project_id}/campaigns/{campaign_id}/artifacts")
    assert artifacts_resp.status_code == 200
    assert len(artifacts_resp.json()) >= 1


def test_regenerate_single_artifact_endpoint() -> None:
    project_id = _create_project_with_selection_and_upload()
    _, campaign_id, task_payload = _start_and_wait_campaign(project_id, "campaign-flow-regenerate")
    assert task_payload["status"] == "completed"

    regenerate_resp = client.post(
        f"/projects/{project_id}/campaigns/{campaign_id}/artifacts/regenerate",
        json={"artifact_type": "email"},
    )
    assert regenerate_resp.status_code == 200
    regenerated = regenerate_resp.json()
    assert regenerated["artifact_type"] == "email"
    assert len(regenerated["content"]) > 0

    artifacts_resp = client.get(f"/projects/{project_id}/campaigns/{campaign_id}/artifacts")
    assert artifacts_resp.status_code == 200
    emails = [a for a in artifacts_resp.json() if a["artifact_type"] == "email"]
    assert len(emails) >= 1

    db = SessionLocal()
    try:
        stored_email = (
            db.query(CampaignArtifact)
            .filter(CampaignArtifact.campaign_id == campaign_id, CampaignArtifact.artifact_type == "email")
            .first()
        )
        assert stored_email is not None
        assert stored_email.provenance["prompt_version"] == "email.v1"
    finally:
        db.close()


def test_update_single_artifact_content_endpoint() -> None:
    project_id = _create_project_with_selection_and_upload()
    _, campaign_id, task_payload = _start_and_wait_campaign(project_id, "campaign-flow-edit")
    assert task_payload["status"] == "completed"

    artifacts_resp = client.get(f"/projects/{project_id}/campaigns/{campaign_id}/artifacts")
    assert artifacts_resp.status_code == 200
    artifacts = artifacts_resp.json()
    assert len(artifacts) > 0
    target = artifacts[0]

    updated = client.put(
        f"/projects/{project_id}/campaigns/{campaign_id}/artifacts/{target['id']}",
        json={"content": "Edited manually from test"},
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "Edited manually from test"

    revisions_resp = client.get(
        f"/projects/{project_id}/campaigns/{campaign_id}/artifacts/{target['id']}/revisions"
    )
    assert revisions_resp.status_code == 200
    revisions = revisions_resp.json()
    assert len(revisions) >= 1

    restore_resp = client.post(
        f"/projects/{project_id}/campaigns/{campaign_id}/artifacts/{target['id']}/restore",
        json={"revision_id": revisions[0]["id"]},
    )
    assert restore_resp.status_code == 200
    assert restore_resp.json()["content"] != "Edited manually from test"


def test_campaign_generation_stores_prompt_versions_in_campaign_context_and_artifacts() -> None:
    project_id = _create_project_with_selection_and_upload()
    task_id, campaign_id, task_payload = _start_and_wait_campaign(project_id, "campaign-flow-prompt-versions")
    assert task_payload["status"] == "completed"
    assert task_id

    db = SessionLocal()
    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        assert campaign is not None
        assert campaign.prompt_context["prompt_versions"]["hero"] == "hero.v1"
        assert campaign.prompt_context["prompt_versions"]["creative_brief"] == "creative_brief.v1"
        assert campaign.prompt_context["qa"]["quality_checks"]["tone_alignment"]["passed"] is True
        assert campaign.prompt_context["qa"]["quality_checks"]["cta_clarity"]["passed"] is True
        assert campaign.prompt_context["qa"]["quality_checks"]["policy_safe_claims"]["passed"] is True

        artifacts = db.query(CampaignArtifact).filter(CampaignArtifact.campaign_id == campaign_id).all()
        assert len(artifacts) >= 3
        assert all(artifact.provenance.get("prompt_version") for artifact in artifacts)
        prompt_versions = {artifact.artifact_type: artifact.provenance["prompt_version"] for artifact in artifacts}
        assert prompt_versions["hero"] == "hero.v1"
        assert prompt_versions["page_draft"] == "page_draft.v1"
    finally:
        db.close()
