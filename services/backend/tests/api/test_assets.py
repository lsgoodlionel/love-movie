from app.integrations.storage import StoredObject
from tests.api.test_tasks import setup_app


class Storage:
    def __init__(self) -> None:
        self.ttl = None

    def presign_get(self, key: str, ttl_seconds: int = 300) -> str:
        self.ttl = ttl_seconds
        return "https://objects.test/signed"


def test_asset_access_is_scoped_and_signed_for_300_seconds() -> None:
    app, client, task = setup_app("assets@example.com")
    storage = Storage()
    app.state.storage = storage
    asset = app.state.generation_repository.persist_asset(
        task.id,
        StoredObject("private/internal.png", "image/png", 10, "a" * 64),
        "image",
    )
    listing = client.get(f"/api/v1/assets?project_id={task.project_id}")
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == str(asset.id)
    assert "object_key" not in listing.json()[0]

    access = client.post(f"/api/v1/assets/{asset.id}/access")
    assert access.json()["url"] == "https://objects.test/signed"
    assert access.json()["expires_in"] == 300
    assert storage.ttl == 300
