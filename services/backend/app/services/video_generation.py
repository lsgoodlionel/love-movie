import uuid
import time
from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from typing import Any

from app.workflows.policies import ImageParameters, VideoParameters
from app.workflows.registry import WorkflowRegistry
from app.services.exceptions import GenerationCancelled
from app.services.planning import PlannedPrompts


async def _one_chunk(content: bytes) -> AsyncIterator[bytes]:
    yield content


class VideoGenerationService:
    def __init__(
        self,
        repository: Any,
        planning: Any,
        comfyui: Any,
        storage: Any,
        gpu_lease: Any,
        *,
        workflows: WorkflowRegistry | None = None,
    ) -> None:
        self._repository = repository
        self._planning = planning
        self._comfyui = comfyui
        self._storage = storage
        self._gpu_lease = gpu_lease
        self._workflows = workflows or WorkflowRegistry()

    async def run(self, task_id: Any):
        task = self._repository.get_task(task_id)
        if task is None:
            raise LookupError("生成任务不存在")
        async with self._gpu_lease.acquire(str(task_id)) as guard:
            gpu_started = time.monotonic()
            await self._ensure_active(task_id, task.remote_prompt_id)
            plan_data = task.parameters.get("plan")
            if plan_data:
                plan = PlannedPrompts.model_validate(plan_data)
            else:
                self._repository.set_status(task_id, "planning")
                plan = await self._planning.plan(task.parameters["prompt"], tenant_id=task.tenant_id)
                self._repository.persist_plan(task_id, plan)

            video = self._repository.find_asset(task_id, "video")
            if video is not None:
                self._repository.set_status(task_id, "completed")
                return video

            first_frame = self._repository.find_asset(task_id, "image")
            if first_frame is None:
                first_frame_workflow = self._workflows.render_image_workflow(
                    ImageParameters(
                        prompt=plan.image_prompt,
                        width=512,
                        height=512,
                        seed=task.parameters.get("seed", 0),
                        adult_content_declared=task.parameters.get("adult_content_declared", False),
                    )
                )
                image_step = self._repository.get_step(task_id, "first_frame")
                image_prompt_id = image_step.remote_prompt_id if image_step else None
                if not image_prompt_id:
                    image_prompt_id = await self._comfyui.submit(first_frame_workflow, f"{task_id}:first-frame")
                    self._repository.persist_step_prompt(task_id, "first_frame", image_prompt_id)
                self._repository.set_status(
                    task_id,
                    "running",
                    remote_prompt_id=image_prompt_id,
                    error_code=None,
                )
                image_output = await self._completed_output(task_id, image_prompt_id, guard, "images")
                image_bytes = b"".join([
                    chunk async for chunk in self._guarded_download(task_id, image_prompt_id, guard, image_output)
                ])
                image_filename = PurePosixPath(image_output["filename"]).name
                image_key = f"{task.tenant_id}/{task.project_id}/{task.id}/first-frame-{image_filename}"
                stored_image = await self._storage.put_stream(
                    image_key, _one_chunk(image_bytes), "image/png"
                )
                first_frame = self._repository.persist_asset_and_usage(
                    task_id,
                    stored_image,
                    "image",
                    usage={
                        "requested_model": plan.requested_model,
                        "actual_model": plan.actual_model,
                        "fallback_reason": plan.fallback_reason,
                        "gpu_seconds": max(time.monotonic() - gpu_started, 0.001),
                        "storage_bytes": stored_image.size_bytes,
                        "content_safety_decision": "allowed",
                        "adult_content_declared": task.parameters.get("adult_content_declared", False),
                    },
                )
                gpu_started = time.monotonic()
            else:
                image_bytes = self._storage.get_bytes(first_frame.object_key)
                image_filename = PurePosixPath(first_frame.object_key).name.removeprefix("first-frame-")

            upload_name = (
                f"{task.tenant_id}/{task.project_id}/{task.id}/"
                f"{uuid.uuid4().hex}-{image_filename}"
            )
            uploaded_name = await self._comfyui.upload_image(
                upload_name, image_bytes, overwrite=False
            )
            guard.ensure_owned()
            await self._ensure_active(task_id, task.remote_prompt_id)
            video_parameters = VideoParameters(
                prompt=plan.motion_prompt,
                negative_prompt=plan.negative_prompt,
                seed=task.parameters.get("seed", 0),
                camera_pose=task.parameters.get("camera_pose", "Zoom In"),
                camera_speed=task.parameters.get("camera_speed", 0.45),
                adult_content_declared=task.parameters.get("adult_content_declared", False),
            )
            video_workflow = self._workflows.render_video_workflow(video_parameters, uploaded_name)
            video_step = self._repository.get_step(task_id, "video")
            video_prompt_id = video_step.remote_prompt_id if video_step else None
            if not video_prompt_id:
                video_prompt_id = await self._comfyui.submit(video_workflow, f"{task_id}:video")
                self._repository.persist_step_prompt(task_id, "video", video_prompt_id)
            self._repository.set_status(
                task_id,
                "running",
                remote_prompt_id=video_prompt_id,
                error_code=None,
            )
            video_output = await self._completed_output(task_id, video_prompt_id, guard, "gifs", "videos")
            video_filename = PurePosixPath(video_output["filename"]).name
            video_key = f"{task.tenant_id}/{task.project_id}/{task.id}/{video_filename}"
            stored_video = await self._storage.put_stream(
                video_key,
                self._guarded_download(task_id, video_prompt_id, guard, video_output),
                self._video_content_type(video_filename),
            )
            video = self._repository.persist_asset_and_usage(
                task_id,
                stored_video,
                "video",
                usage={
                    "requested_model": plan.requested_model,
                    "actual_model": plan.actual_model,
                    "fallback_reason": plan.fallback_reason,
                    "gpu_seconds": max(time.monotonic() - gpu_started, 0.001),
                    "storage_bytes": stored_video.size_bytes,
                    "content_safety_decision": "allowed",
                    "adult_content_declared": task.parameters.get("adult_content_declared", False),
                },
                parent_asset_id=first_frame.id,
            )
            self._repository.set_status(task_id, "completed")
            return video

    async def _completed_output(self, task_id: Any, prompt_id: str, guard: Any, *collections: str) -> dict[str, str]:
        outputs: dict[str, Any] = {}
        async for event in self._comfyui.track(prompt_id):
            guard.ensure_owned()
            await self._ensure_active(task_id, prompt_id)
            if event.kind == "completed":
                outputs = event.outputs
                break
        for node in outputs.values():
            for collection in collections:
                items = node.get(collection, [])
                if items:
                    return items[0]
        raise ValueError("生成服务未返回预期素材")

    async def _ensure_active(self, task_id: Any, prompt_id: str | None = None) -> None:
        if self._repository.is_cancellation_requested(task_id):
            if prompt_id:
                await self._comfyui.cancel(prompt_id)
            raise GenerationCancelled()

    async def _guarded_download(self, task_id: Any, prompt_id: str, guard: Any, output: dict[str, str]):
        async for chunk in self._comfyui.download_output(output):
            guard.ensure_owned()
            await self._ensure_active(task_id, prompt_id)
            yield chunk

    @staticmethod
    def _video_content_type(filename: str) -> str:
        if filename.lower().endswith(".mp4"):
            return "video/mp4"
        if filename.lower().endswith(".webm"):
            return "video/webm"
        raise ValueError("生成服务返回了不支持的视频格式")
