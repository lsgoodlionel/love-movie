from pathlib import PurePosixPath
from typing import Any

from app.workflows.policies import ImageParameters
from app.workflows.registry import WorkflowRegistry


class ImageGenerationService:
    def __init__(
        self,
        repository: Any,
        comfyui: Any,
        storage: Any,
        gpu_lease: Any,
        *,
        workflows: WorkflowRegistry | None = None,
    ) -> None:
        self._repository = repository
        self._comfyui = comfyui
        self._storage = storage
        self._gpu_lease = gpu_lease
        self._workflows = workflows or WorkflowRegistry()

    async def run(self, task_id: Any):
        task = self._repository.get_task(task_id)
        if task is None:
            raise LookupError("生成任务不存在")
        parameters = ImageParameters.model_validate(task.parameters)

        async with self._gpu_lease.acquire(str(task_id)) as guard:
            workflow = self._workflows.render_image_workflow(parameters)
            prompt_id = task.remote_prompt_id
            if not prompt_id:
                prompt_id = await self._comfyui.submit(workflow, str(task_id))
                self._repository.set_status(
                    task_id,
                    "remote_submitted",
                    remote_prompt_id=prompt_id,
                    error_code=None,
                )
            guard.ensure_owned()
            self._repository.set_status(task_id, "running")
            outputs: dict[str, Any] = {}
            async for event in self._comfyui.track(prompt_id):
                if event.kind == "completed":
                    outputs = event.outputs
                    break
            output = self._first_image(outputs)
            self._repository.set_status(task_id, "downloading")
            filename = PurePosixPath(output["filename"]).name
            key = f"{task.tenant_id}/{task.project_id}/{task.id}/{filename}"
            content_type = "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg")) else "image/png"
            stored = await self._storage.put_stream(
                key,
                self._comfyui.download_output(output),
                content_type,
            )
            asset = self._repository.persist_asset(task_id, stored, "image")
            self._repository.record_usage(
                task_id,
                gpu_seconds=0,
                storage_bytes=stored.size_bytes,
                content_safety_decision="allowed",
                adult_content_declared=parameters.adult_content_declared,
            )
            self._repository.set_status(task_id, "completed")
            return asset

    @staticmethod
    def _first_image(outputs: dict[str, Any]) -> dict[str, str]:
        for node in outputs.values():
            images = node.get("images", [])
            if images:
                return images[0]
        raise ValueError("生成服务未返回图片")
