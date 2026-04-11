from fastapi.testclient import TestClient

from app.core.config import settings
from app.db import Base, engine
from app.main import app


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    settings.api_key = ""
    settings.require_tenant_header = False


def teardown_function() -> None:
    settings.api_key = ""
    settings.require_tenant_header = False


def test_tenant_header_blocks_cross_tenant_project_access() -> None:
    created = client.post(
        "/projects",
        json={"tenant_id": "tenant-a", "name": "Tenant A Project", "niche_tags": []},
    )
    assert created.status_code == 200
    project_id = created.json()["id"]

    blocked = client.post(
        f"/projects/{project_id}/trend-scan",
        json={"force_refresh": True},
        headers={"X-Tenant-Id": "tenant-b"},
    )
    assert blocked.status_code == 403
    assert "not accessible" in blocked.json()["detail"]


def test_api_key_enforced_when_configured() -> None:
    settings.api_key = "top-secret"

    no_key = client.post(
        "/projects",
        json={"tenant_id": "tenant-a", "name": "Secure Project", "niche_tags": []},
    )
    assert no_key.status_code == 401

    with_key = client.post(
        "/projects",
        json={"tenant_id": "tenant-a", "name": "Secure Project", "niche_tags": []},
        headers={"X-API-Key": "top-secret"},
    )
    assert with_key.status_code == 200
