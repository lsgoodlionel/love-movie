import asyncio
import hashlib

import pytest

from app.integrations.errors import RemoteServiceError
from app.integrations.storage import StorageAdapter


class FakeStorageClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.content = b""

    def upload_fileobj(self, fileobj, bucket: str, key: str, ExtraArgs: dict) -> None:
        if self.fail:
            raise OSError("secret storage details")
        self.content = fileobj.read()

    def generate_presigned_url(self, operation: str, Params: dict, ExpiresIn: int) -> str:
        return f"https://objects.test/{Params['Key']}?ttl={ExpiresIn}"


async def chunks():
    yield b"\x00\x00\x00\x18ftyp"
    yield b"mp42movie"


def test_streaming_put_checks_size_digest_and_presigns() -> None:
    client = FakeStorageClient()
    adapter = StorageAdapter(client, "assets", max_bytes=100)
    stored = asyncio.run(adapter.put_stream("tenant/video.mp4", chunks(), "video/mp4", declared_size=17))

    assert client.content == b"\x00\x00\x00\x18ftypmp42movie"
    assert stored.size_bytes == 17
    assert stored.sha256 == hashlib.sha256(client.content).hexdigest()
    assert adapter.presign_get("tenant/video.mp4") == "https://objects.test/tenant/video.mp4?ttl=300"


def test_size_mismatch_and_storage_failure_have_distinct_codes() -> None:
    with pytest.raises(RemoteServiceError) as mismatch:
        asyncio.run(StorageAdapter(FakeStorageClient(), "assets").put_stream("x.mp4", chunks(), "video/mp4", declared_size=99))
    assert mismatch.value.code == "DOWNLOAD_INTERRUPTED"

    with pytest.raises(RemoteServiceError) as failed:
        asyncio.run(StorageAdapter(FakeStorageClient(fail=True), "assets").put_stream("x.mp4", chunks(), "video/mp4"))
    assert failed.value.code == "STORAGE_WRITE_FAILED"
    assert "secret" not in str(failed.value)

