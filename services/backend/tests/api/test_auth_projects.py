from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def make_app():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return create_app(Settings(app_env="test"), engine=engine)


def test_disabled_user_cannot_log_in() -> None:
    app = make_app()
    app.state.identity_repository.create_tenant_with_user(
        tenant_name="停用测试团队",
        email="disabled@example.com",
        password="safe-password-123",
        role="creator",
        is_active=False,
    )

    response = TestClient(app, base_url="https://testserver").post(
        "/api/v1/auth/login",
        json={"email": "disabled@example.com", "password": "safe-password-123"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "账号或密码错误"


def test_login_cookie_is_http_only_secure_and_same_site_lax() -> None:
    app = make_app()
    app.state.identity_repository.create_tenant_with_user(
        tenant_name="创作团队",
        email="creator@example.com",
        password="safe-password-123",
        role="creator",
    )

    response = TestClient(app, base_url="https://testserver").post(
        "/api/v1/auth/login",
        json={"email": "creator@example.com", "password": "safe-password-123"},
    )

    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie


def test_user_from_other_tenant_cannot_read_project() -> None:
    app = make_app()
    repo = app.state.identity_repository
    repo.create_tenant_with_user(
        tenant_name="甲团队",
        email="a@example.com",
        password="safe-password-123",
        role="creator",
    )
    repo.create_tenant_with_user(
        tenant_name="乙团队",
        email="b@example.com",
        password="safe-password-123",
        role="creator",
    )
    client_a = TestClient(app, base_url="https://testserver")
    client_b = TestClient(app, base_url="https://testserver")
    assert client_a.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "safe-password-123"},
    ).status_code == 200
    created = client_a.post("/api/v1/projects", json={"name": "甲项目"})
    assert created.status_code == 201
    project_id = created.json()["id"]
    assert client_b.post(
        "/api/v1/auth/login",
        json={"email": "b@example.com", "password": "safe-password-123"},
    ).status_code == 200

    denied = client_b.get(f"/api/v1/projects/{project_id}")

    assert denied.status_code == 403
    assert denied.json()["detail"] == "无权访问该项目"


def test_logout_revokes_server_side_session() -> None:
    app = make_app()
    app.state.identity_repository.create_tenant_with_user(
        tenant_name="注销测试团队",
        email="logout@example.com",
        password="safe-password-123",
        role="creator",
    )
    client = TestClient(app, base_url="https://testserver")
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "logout@example.com", "password": "safe-password-123"},
    ).status_code == 200
    stolen_token = client.cookies["session_token"]

    assert client.post("/api/v1/auth/logout").status_code == 204
    replay = TestClient(app, base_url="https://testserver")
    replay.cookies.set("session_token", stolen_token)

    assert replay.get("/api/v1/auth/me").status_code == 401
