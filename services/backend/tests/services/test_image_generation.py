import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from app.integrations.comfyui import ProgressEvent
from app.integrations.storage import StoredObject
from app.services.image_generation import ImageGenerationService


class Repo:
    def __init__(self) -> None:
        self.task = SimpleNamespace(
            id="task-1",
            tenant_id="tenant-1",
            project_id="project-1",
            parameters={"prompt": "云海日出", "width": 768, "height": 1024},
            remote_prompt_id=None,
        )
        self.timeline: list[str] = []

    def get_task(self, task_id):
        return self.task

    def find_asset(self, task_id, kind):
        return None

    def is_cancellation_requested(self, task_id):
        return False

    def set_status(self, task_id, status, **values):
        self.timeline.append(status)
        for key, value in values.items():
            setattr(self.task, key, value)

    def persist_asset(self, task_id, stored, kind):
        self.timeline.append("asset_persisted")
        return SimpleNamespace(id="asset-1", object_key=stored.key)

    def record_usage(self, task_id, **values):
        self.timeline.append("usage_persisted")


class Comfy:
    def __init__(self, repo: Repo) -> None:
        self.repo = repo
        self.submits = 0

    async def submit(self, workflow, client_id):
        self.submits += 1
        return "prompt-1"

    async def track(self, prompt_id):
        assert self.repo.task.remote_prompt_id == "prompt-1"
        yield ProgressEvent("completed", 1, {"9": {"images": [{"filename": "result.png", "type": "output"}]}})

    async def download_output(self, output):
        yield b"png-bytes"

    async def cancel(self, prompt_id):
        raise AssertionError("不应取消")


class Storage:
    async def put_stream(self, key, source, content_type, declared_size=None):
        content = b"".join([chunk async for chunk in source])
        assert content == b"png-bytes"
        assert key.startswith("tenant-1/project-1/task-1/")
        return StoredObject(key, content_type, len(content), "digest")


class Lease:
    @asynccontextmanager
    async def acquire(self, task_id):
        yield SimpleNamespace(ensure_owned=lambda: None)


def test_image_service_persists_prompt_before_tracking_and_stores_asset() -> None:
    repo = Repo()
    comfy = Comfy(repo)
    service = ImageGenerationService(repo, comfy, Storage(), Lease())

    asset = asyncio.run(service.run("task-1"))

    assert comfy.submits == 1
    assert asset.object_key.endswith("result.png")
    assert repo.timeline == [
        "remote_submitted",
        "running",
        "downloading",
        "asset_persisted",
        "usage_persisted",
        "completed",
    ]
