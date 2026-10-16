from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.domain.generation.schemas import CreateGenerationCommand, GenerationKind
from app.main import create_app


def setup_app(email: str = "owner@example.com"):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    app = create_app(Settings(app_env="test"), engine=engine, dispatcher=object(), storage=object())
    app.state.identity_repository.create_tenant_with_user(
        tenant_name=email, email=email, password="safe-password-123", role="creator"
    )
    client = TestClient(app, base_url="https://testserver")
    client.post("/api/v1/auth/login", json={"email": email, "password": "safe-password-123"})
    project_id = client.post("/api/v1/projects", json={"name": "项目"}).json()["id"]
    principal = app.state.identity_repository.authenticate(email, "safe-password-123")
    task, _ = app.state.generation_repository.create_or_get_task(
        CreateGenerationCommand(
            tenant_id=principal.tenant_id,
            project_id=project_id,
            created_by=principal.user_id,
            kind=GenerationKind.IMAGE,
            parameters={"prompt": "测试"},
            workflow_version="test:v1",
        ),
        str(uuid4()),
    )
    return app, client, task


def test_task_query_is_tenant_scoped() -> None:
    app, owner, task = setup_app()
    assert owner.get(f"/api/v1/tasks/{task.id}").status_code == 200

    app.state.identity_repository.create_tenant_with_user(
        tenant_name="其他团队", email="other@example.com", password="safe-password-123", role="creator"
    )
    other = TestClient(app, base_url="https://testserver")
    other.post("/api/v1/auth/login", json={"email": "other@example.com", "password": "safe-password-123"})
    denied = other.get(f"/api/v1/tasks/{task.id}")
    assert denied.status_code == 403

