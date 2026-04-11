import time

from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_end_to_end_api_flow() -> None:
    project_resp = client.post(
        "/projects",
        json={"tenant_id": "tenant-1", "name": "Demo Project", "niche_tags": ["skincare", "dtc"]},
    )
    assert project_resp.status_code == 200
    project_id = project_resp.json()["id"]

    trend_resp = client.post(f"/projects/{project_id}/trend-scan", json={"force_refresh": True})
    assert trend_resp.status_code == 200
    assert trend_resp.json()["status"] == "completed"

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

    generate_resp = client.post(
        f"/projects/{project_id}/campaigns/generate",
        json={"idempotency_key": "campaign-flow-1"},
    )
    assert generate_resp.status_code == 200
    payload = generate_resp.json()
    task_id = payload["task_id"]
    campaign_id = payload["campaign_id"]

    status = "running"
    for _ in range(30):
        task_resp = client.get(f"/projects/{project_id}/tasks/{task_id}")
        assert task_resp.status_code == 200
        status = task_resp.json()["status"]
        if status in {"completed", "failed", "blocked"}:
            break
        time.sleep(0.1)

    assert status == "completed"

    artifacts_resp = client.get(f"/projects/{project_id}/campaigns/{campaign_id}/artifacts")
    assert artifacts_resp.status_code == 200
    assert len(artifacts_resp.json()) >= 3

    approve_resp = client.post(
        f"/projects/{project_id}/campaigns/{campaign_id}/approve",
        json={"approved_by": "qa-user", "notes": "Looks good"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"
