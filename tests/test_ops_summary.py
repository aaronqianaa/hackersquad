from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_ops_task_summary_endpoint_returns_counts() -> None:
    project_resp = client.post(
        "/projects",
        json={"tenant_id": "tenant-ops", "name": "Ops Project", "niche_tags": ["ops"]},
    )
    assert project_resp.status_code == 200
    project_id = project_resp.json()["id"]

    trend_resp = client.post(f"/projects/{project_id}/trend-scan", json={"force_refresh": True})
    assert trend_resp.status_code == 200

    summary_resp = client.get("/ops/tasks/summary")
    assert summary_resp.status_code == 200
    payload = summary_resp.json()
    assert payload["total_tasks"] >= 1
    assert payload["completed_tasks"] >= 1
