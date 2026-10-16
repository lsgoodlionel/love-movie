from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.main import create_app


class HealthProbe:
    async def snapshot(self):
        return {
            "postgresql": "healthy",
            "redis": "healthy",
            "minio": "healthy",
            "worker": "healthy",
            "ollama": "healthy",
            "comfyui": "healthy",
            "queue_length": 0,
            "current_lease_task_id": None,
        }


def make_admin_client(role: str = "admin"):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    app = create_app(Settings(app_env="test"), engine=engine, dispatcher=object(), storage=object(), health_probe=HealthProbe())
    app.state.identity_repository.create_tenant_with_user(
        tenant_name="管理团队", email="admin@example.com", password="safe-password-123", role=role
    )
    client = TestClient(app, base_url="https://testserver")
    client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "safe-password-123"})
    return client


def test_admin_health_has_operational_state_without_secrets() -> None:
    response = make_admin_client().get("/api/v1/admin/health")
    assert response.status_code == 200
    assert response.json()["comfyui"] == "healthy"
    serialized = response.text.lower()
    assert "secret" not in serialized
    assert "credential" not in serialized


def test_creator_cannot_read_admin_health() -> None:
    assert make_admin_client("creator").get("/api/v1/admin/health").status_code == 403

