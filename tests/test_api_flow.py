import time

from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


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
    generate_resp = client.post(
        f"/projects/{project_id}/campaigns/generate",
        json={"idempotency_key": idempotency_key},
    )
    assert generate_resp.status_code == 200
    payload = generate_resp.json()
    task_id = payload["task_id"]
    campaign_id = payload["campaign_id"]

    task_payload: dict = {}
    for _ in range(30):
        task_resp = client.get(f"/projects/{project_id}/tasks/{task_id}")
        assert task_resp.status_code == 200
        task_payload = task_resp.json()
        if task_payload["status"] in {"completed", "failed", "blocked"}:
            break
        time.sleep(0.1)
    return task_id, campaign_id, task_payload


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
