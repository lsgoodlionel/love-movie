import uuid
from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from typing import Any

from app.workflows.policies import ImageParameters, VideoParameters
from app.workflows.registry import WorkflowRegistry


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
        self._repository.set_status(task_id, "planning")
        plan = await self._planning.plan(task.parameters["prompt"])
        self._repository.persist_plan(task_id, plan)

        async with self._gpu_lease.acquire(str(task_id)) as guard:
            first_frame_workflow = self._workflows.render_image_workflow(
                ImageParameters(
                    prompt=plan.image_prompt,
                    width=512,
                    height=512,
                    seed=task.parameters.get("seed", 0),
                    adult_content_declared=task.parameters.get("adult_content_declared", False),
                )
            )
            image_prompt_id = await self._comfyui.submit(first_frame_workflow, f"{task_id}:first-frame")
            self._repository.persist_step_prompt(task_id, "first_frame", image_prompt_id)
            self._repository.set_status(task_id, "running", remote_prompt_id=image_prompt_id)
            guard.ensure_owned()
            image_output = await self._completed_output(image_prompt_id, "images")
            image_bytes = b"".join([chunk async for chunk in self._comfyui.download_output(image_output)])
            image_filename = PurePosixPath(image_output["filename"]).name
            image_key = f"{task.tenant_id}/{task.project_id}/{task.id}/first-frame-{image_filename}"
            stored_image = await self._storage.put_stream(
                image_key, _one_chunk(image_bytes), "image/png"
            )
            first_frame = self._repository.persist_asset(task_id, stored_image, "image")

            upload_name = (
                f"{task.tenant_id}/{task.project_id}/{task.id}/"
                f"{uuid.uuid4().hex}-{image_filename}"
            )
            uploaded_name = await self._comfyui.upload_image(
                upload_name, image_bytes, overwrite=False
            )
            guard.ensure_owned()
            video_parameters = VideoParameters(
                prompt=plan.motion_prompt,
                negative_prompt=plan.negative_prompt,
                seed=task.parameters.get("seed", 0),
                camera_pose=task.parameters.get("camera_pose", "Zoom In"),
                camera_speed=task.parameters.get("camera_speed", 0.45),
            )
            video_workflow = self._workflows.render_video_workflow(video_parameters, uploaded_name)
            video_prompt_id = await self._comfyui.submit(video_workflow, f"{task_id}:video")
            self._repository.persist_step_prompt(task_id, "video", video_prompt_id)
            self._repository.set_status(task_id, "running", remote_prompt_id=video_prompt_id)
            video_output = await self._completed_output(video_prompt_id, "gifs", "videos")
            video_filename = PurePosixPath(video_output["filename"]).name
            video_key = f"{task.tenant_id}/{task.project_id}/{task.id}/{video_filename}"
            stored_video = await self._storage.put_stream(
                video_key,
                self._comfyui.download_output(video_output),
                "video/mp4",
            )
            video = self._repository.persist_asset(
                task_id,
                stored_video,
                "video",
                parent_asset_id=first_frame.id,
            )
            self._repository.record_usage(
                task_id,
                requested_model="qwen3.5:latest",
                actual_model="qwen3.5:latest",
                gpu_seconds=0,
                storage_bytes=stored_image.size_bytes + stored_video.size_bytes,
                content_safety_decision="allowed",
                adult_content_declared=task.parameters.get("adult_content_declared", False),
            )
            self._repository.set_status(task_id, "completed")
            return video

    async def _completed_output(self, prompt_id: str, *collections: str) -> dict[str, str]:
        outputs: dict[str, Any] = {}
        async for event in self._comfyui.track(prompt_id):
            if event.kind == "completed":
                outputs = event.outputs
                break
        for node in outputs.values():
            for collection in collections:
                items = node.get(collection, [])
                if items:
                    return items[0]
        raise ValueError("生成服务未返回预期素材")
