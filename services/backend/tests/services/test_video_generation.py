import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.integrations.comfyui import ProgressEvent
from app.integrations.errors import RemoteServiceError
from app.integrations.storage import StoredObject
from app.services.planning import PlannedPrompts
from app.services.video_generation import VideoGenerationService


class Repo:
    def __init__(self) -> None:
        self.task = SimpleNamespace(
            id="task-video",
            tenant_id="tenant",
            project_id="project",
            parameters={"prompt": "山谷晨雾", "camera_pose": "Zoom In", "camera_speed": 0.45, "seed": 7},
            remote_prompt_id=None,
        )
        self.timeline: list[str] = []
        self.prompts: dict[str, str] = {}
        self.assets = []

    def get_task(self, task_id):
        return self.task

    def set_status(self, task_id, status, **values):
        self.timeline.append(status)
        for key, value in values.items():
            setattr(self.task, key, value)

    def persist_plan(self, task_id, plan):
        self.timeline.append("plan")
        self.task.parameters["plan"] = plan.model_dump()

    def get_step(self, task_id, name):
        prompt_id = self.prompts.get(name)
        return SimpleNamespace(remote_prompt_id=prompt_id) if prompt_id else None

    def find_asset(self, task_id, kind):
        return next((asset for asset in reversed(self.assets) if asset.kind == kind), None)

    def is_cancellation_requested(self, task_id):
        return False

    def persist_step_prompt(self, task_id, step, prompt_id):
        self.prompts[step] = prompt_id
        self.timeline.append(f"prompt:{step}")

    def persist_asset(self, task_id, stored, kind, parent_asset_id=None):
        asset = SimpleNamespace(
            id=f"asset-{kind}",
            kind=kind,
            object_key=stored.key,
            parent_asset_id=parent_asset_id,
            size_bytes=stored.size_bytes,
        )
        self.assets.append(asset)
        self.timeline.append(f"asset:{kind}")
        return asset

    def persist_asset_and_usage(self, task_id, stored, kind, *, usage, parent_asset_id=None):
        asset = self.persist_asset(task_id, stored, kind, parent_asset_id)
        self.record_usage(task_id, **usage)
        return asset

    def record_usage(self, task_id, **values):
        self.timeline.append("usage")


class Planner:
    def __init__(self, fail_unload: bool = False) -> None:
        self.fail_unload = fail_unload

    async def plan(self, text, *, tenant_id=None):
        if self.fail_unload:
            raise RemoteServiceError("REMOTE_SOFT_TIMEOUT", "等待显存释放超时")
        return PlannedPrompts(
            title="山谷",
            image_prompt="山谷晨雾，电影感",
            motion_prompt="镜头缓慢推进，薄雾流动",
            negative_prompt="水印，抖动",
        )


class Comfy:
    def __init__(self, repo: Repo) -> None:
        self.repo = repo
        self.submits = 0
        self.uploads = []

    async def submit(self, workflow, client_id):
        self.submits += 1
        return f"prompt-{self.submits}"

    async def track(self, prompt_id):
        if prompt_id == "prompt-1":
            assert self.repo.prompts["first_frame"] == prompt_id
            outputs = {"9": {"images": [{"filename": "frame.png", "type": "output"}]}}
        else:
            assert self.repo.prompts["video"] == prompt_id
            outputs = {"15": {"gifs": [{"filename": "shot.mp4", "type": "output"}]}}
        yield ProgressEvent("completed", 1, outputs)

    async def download_output(self, output):
        yield b"video" if output["filename"].endswith("mp4") else b"image"

    async def upload_image(self, name, content, *, overwrite):
        self.uploads.append((name, content, overwrite))
        return name

    async def cancel(self, prompt_id):
        raise AssertionError("不应取消")


class Storage:
    def __init__(self) -> None:
        self.objects = {}

    async def put_stream(self, key, source, content_type, declared_size=None):
        content = b"".join([chunk async for chunk in source])
        self.objects[key] = content
        return StoredObject(key, content_type, len(content), "digest")

    def get_bytes(self, key):
        return self.objects[key]


class Lease:
    @asynccontextmanager
    async def acquire(self, task_id):
        yield SimpleNamespace(ensure_owned=lambda: None)


def test_video_generation_preserves_order_lineage_and_collision_safe_upload() -> None:
    repo = Repo()
    comfy = Comfy(repo)
    service = VideoGenerationService(repo, Planner(), comfy, Storage(), Lease())
    video = asyncio.run(service.run("task-video"))

    assert comfy.submits == 2
    assert comfy.uploads[0][0].startswith("tenant/project/task-video/")
    assert comfy.uploads[0][0].endswith("-frame.png")
    assert comfy.uploads[0][2] is False
    assert video.parent_asset_id == "asset-image"
    assert repo.timeline.index("prompt:first_frame") < repo.timeline.index("asset:image")
    assert repo.timeline.index("prompt:video") < repo.timeline.index("asset:video")


def test_ollama_unload_timeout_prevents_any_comfy_submission() -> None:
    repo = Repo()
    comfy = Comfy(repo)
    service = VideoGenerationService(repo, Planner(fail_unload=True), comfy, Storage(), Lease())
    with pytest.raises(RemoteServiceError) as caught:
        asyncio.run(service.run("task-video"))
    assert caught.value.code == "REMOTE_SOFT_TIMEOUT"
    assert comfy.submits == 0


def test_video_resume_reuses_plan_first_frame_and_video_prompt() -> None:
    repo = Repo()
    repo.task.parameters["plan"] = PlannedPrompts(
        title="山谷",
        image_prompt="山谷晨雾，电影感",
        motion_prompt="镜头缓慢推进，薄雾流动",
        negative_prompt="水印，抖动",
    ).model_dump()
    storage = Storage()
    stored = StoredObject("tenant/project/task-video/first-frame-frame.png", "image/png", 5, "digest")
    storage.objects[stored.key] = b"image"
    repo.persist_asset("task-video", stored, "image")
    repo.prompts["video"] = "prompt-resume-video"
    planner = Planner()
    comfy = Comfy(repo)

    video = asyncio.run(VideoGenerationService(repo, planner, comfy, storage, Lease()).run("task-video"))

    assert comfy.submits == 0
    assert video.parent_asset_id == "asset-image"
