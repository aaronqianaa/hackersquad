from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_history_endpoints_list_projects_tasks_campaigns() -> None:
    project_resp = client.post(
        "/projects",
        json={"tenant_id": "tenant-history", "name": "History Project", "niche_tags": ["demo"]},
    )
    assert project_resp.status_code == 200
    project_id = project_resp.json()["id"]

    projects_resp = client.get("/projects")
    assert projects_resp.status_code == 200
    assert any(p["id"] == project_id for p in projects_resp.json())

    trend_resp = client.post(f"/projects/{project_id}/trend-scan", json={"force_refresh": True})
    assert trend_resp.status_code == 200

    tasks_resp = client.get(f"/projects/{project_id}/tasks")
    assert tasks_resp.status_code == 200
    assert len(tasks_resp.json()) >= 1

    campaigns_resp = client.get(f"/projects/{project_id}/campaigns")
    assert campaigns_resp.status_code == 200
    assert isinstance(campaigns_resp.json(), list)
