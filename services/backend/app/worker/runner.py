from typing import Any
from uuid import UUID

from app.domain.generation.schemas import GenerationKind
from app.services.exceptions import GenerationCancelled


async def run_generation(ctx: dict[str, Any], task_id: str) -> None:
    runner = ctx.get("generation_runner")
    if runner is None:
        raise RuntimeError("generation_runner 未配置")
    await runner.run(task_id)


class GenerationRunner:
    def __init__(self, repository: Any, image_service: Any, video_service: Any) -> None:
        self._repository = repository
        self._image_service = image_service
        self._video_service = video_service

    async def run(self, task_id: str) -> None:
        normalized_id = UUID(task_id)
        task = self._repository.get_task(normalized_id)
        if task is None:
            raise LookupError("生成任务不存在")
        if task.status == "cancelled":
            self._repository.set_status(normalized_id, "cancelled")
            return
        if task.cancellation_requested_at is not None and not task.remote_prompt_id:
            self._repository.set_status(normalized_id, "cancelled")
            return
        try:
            if task.kind == GenerationKind.IMAGE.value:
                await self._image_service.run(normalized_id)
            elif task.kind == GenerationKind.VIDEO.value:
                await self._video_service.run(normalized_id)
            else:
                raise ValueError("未知生成类型")
        except GenerationCancelled:
            self._repository.set_status(normalized_id, "cancelled")
        except Exception as exc:
            code = getattr(exc, "code", "GENERATION_FAILED")
            self._repository.set_status(normalized_id, "failed", error_code=code)
            raise
