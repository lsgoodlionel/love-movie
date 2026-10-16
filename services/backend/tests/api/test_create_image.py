from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.main import create_app


class Dispatcher:
    def __init__(self) -> None:
        self.task_ids: list[str] = []

    async def enqueue_generation(self, task_id) -> str:
        self.task_ids.append(str(task_id))
        return str(task_id)


def make_client(role: str = "creator"):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    dispatcher = Dispatcher()
    app = create_app(Settings(app_env="test"), engine=engine, dispatcher=dispatcher)
    app.state.identity_repository.create_tenant_with_user(
        tenant_name="图片团队",
        email="user@example.com",
        password="safe-password-123",
        role=role,
    )
    client = TestClient(app, base_url="https://testserver")
    assert client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "safe-password-123"}).status_code == 200
    if role == "reviewer":
        principal = app.state.identity_repository.authenticate("user@example.com", "safe-password-123")
        project_id = str(app.state.identity_repository.create_project(principal, "宣传片").id)
    else:
        project_id = client.post("/api/v1/projects", json={"name": "宣传片"}).json()["id"]
    return client, project_id, dispatcher


def test_create_image_is_idempotent_and_enqueued_once() -> None:
    client, project_id, dispatcher = make_client()
    payload = {"project_id": project_id, "prompt": "雨夜霓虹街道", "width": 768, "height": 1024}
    headers = {"Idempotency-Key": "image-request-1"}

    first = client.post("/api/v1/generations/images", json=payload, headers=headers)
    second = client.post("/api/v1/generations/images", json=payload, headers=headers)

    assert first.status_code == second.status_code == 202
    assert first.json()["task_id"] == second.json()["task_id"]
    assert len(dispatcher.task_ids) == 1


def test_reusing_idempotency_key_with_different_payload_is_conflict() -> None:
    client, project_id, dispatcher = make_client()
    headers = {"Idempotency-Key": "image-request-conflict"}

    first = client.post(
        "/api/v1/generations/images",
        json={"project_id": project_id, "prompt": "雨夜霓虹街道"},
        headers=headers,
    )
    conflict = client.post(
        "/api/v1/generations/images",
        json={"project_id": project_id, "prompt": "晴天海边"},
        headers=headers,
    )

    assert first.status_code == 202
    assert conflict.status_code == 409
    assert len(dispatcher.task_ids) == 1


def test_video_applies_minor_content_policy_before_enqueue() -> None:
    client, project_id, dispatcher = make_client()
    response = client.post(
        "/api/v1/generations/videos",
        json={
            "project_id": project_id,
            "prompt": "16岁少女裸体短片",
            "adult_content_declared": True,
        },
        headers={"Idempotency-Key": "unsafe-video-1"},
    )

    assert response.status_code == 422
    assert not dispatcher.task_ids


def test_reviewer_is_forbidden_and_oversize_is_rejected_without_enqueue() -> None:
    reviewer, project_id, dispatcher = make_client("reviewer")
    denied = reviewer.post(
        "/api/v1/generations/images",
        json={"project_id": project_id, "prompt": "测试"},
        headers={"Idempotency-Key": "reviewer-1"},
    )
    assert denied.status_code == 403
    assert not dispatcher.task_ids

    creator, creator_project, creator_dispatcher = make_client("creator")
    invalid = creator.post(
        "/api/v1/generations/images",
        json={"project_id": creator_project, "prompt": "测试", "width": 4096},
        headers={"Idempotency-Key": "oversize-1"},
    )
    assert invalid.status_code == 422
    assert not creator_dispatcher.task_ids

