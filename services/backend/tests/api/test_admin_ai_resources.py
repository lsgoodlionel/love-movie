from tests.api.test_admin_health import make_admin_client


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
