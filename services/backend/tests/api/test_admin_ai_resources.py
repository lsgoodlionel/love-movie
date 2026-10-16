from tests.api.test_admin_health import make_admin_client
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.main import create_app


def test_admin_can_create_and_update_model_route_metadata() -> None:
    client = make_admin_client("admin")
    created = client.post(
        "/api/v1/admin/ai-resources/model-routes",
        json={"capability": "story_planning", "quality": "interactive", "model": "qwen3.5:latest", "priority": 20, "enabled": True},
    )
    assert created.status_code == 201
    route_id = created.json()["id"]
    updated = client.patch(
        f"/api/v1/admin/ai-resources/model-routes/{route_id}",
        json={"priority": 5, "enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["priority"] == 5
    assert updated.json()["enabled"] is False
    assert "secret" not in updated.text.lower()


def test_resource_api_rejects_non_admin_and_credential_fields() -> None:
    reviewer = make_admin_client("reviewer")
    assert reviewer.get("/api/v1/admin/ai-resources/model-routes").status_code == 403

    admin = make_admin_client("admin")
    rejected = admin.post(
        "/api/v1/admin/ai-resources/model-routes",
        json={
            "capability": "cleanup",
            "quality": "interactive",
            "model": "qwen3.5:4b",
            "priority": 10,
            "enabled": True,
            "cf_access_client_secret": "must-not-be-accepted",
        },
    )
    assert rejected.status_code == 422


def test_tenant_admin_cannot_read_or_modify_another_tenant_route() -> None:
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    app = create_app(Settings(app_env="test"), engine=engine, dispatcher=object(), storage=object())
    repo = app.state.identity_repository
    repo.create_tenant_with_user(
        tenant_name="甲团队", email="admin-a@example.com", password="safe-password-123", role="admin"
    )
    repo.create_tenant_with_user(
        tenant_name="乙团队", email="admin-b@example.com", password="safe-password-123", role="admin"
    )
    client_a = TestClient(app, base_url="https://testserver")
    client_b = TestClient(app, base_url="https://testserver")
    client_a.post("/api/v1/auth/login", json={"email": "admin-a@example.com", "password": "safe-password-123"})
    created = client_a.post(
        "/api/v1/admin/ai-resources/model-routes",
        json={"capability": "story_planning", "quality": "interactive", "model": "model-a"},
    )
    route_id = created.json()["id"]
    client_b.post("/api/v1/auth/login", json={"email": "admin-b@example.com", "password": "safe-password-123"})

    assert client_b.get("/api/v1/admin/ai-resources/model-routes").json() == []
    assert client_b.patch(
        f"/api/v1/admin/ai-resources/model-routes/{route_id}", json={"enabled": False}
    ).status_code == 404
