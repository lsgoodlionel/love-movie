from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RecoveryReport:
    requeued: int = 0
    resumed: int = 0
    needs_attention: int = 0


class RecoveryCoordinator:
    def __init__(self, repository: Any, dispatcher: Any, comfyui: Any) -> None:
        self._repository = repository
        self._dispatcher = dispatcher
        self._comfyui = comfyui

    async def recover_incomplete_tasks(self) -> RecoveryReport:
        requeued = resumed = needs_attention = 0
        for task in self._repository.incomplete_tasks():
            if task.status in {"draft", "queued"}:
                await self._dispatcher.enqueue_generation(task.id)
                requeued += 1
            elif task.remote_prompt_id:
                try:
                    history = await self._comfyui.history(task.remote_prompt_id)
                    known_remote = history is not None or await self._comfyui.queue_contains(task.remote_prompt_id)
                except Exception:
                    # 远程隧道短暂不可用不能阻止 Worker 启动；任务继续使用已持久化 prompt 恢复。
                    known_remote = True
                if known_remote:
                    await self._dispatcher.enqueue_generation(task.id)
                    resumed += 1
                else:
                    self._repository.mark_needs_attention(task.id, "REMOTE_PROMPT_NOT_FOUND")
                    needs_attention += 1
            elif task.status in {"planning", "cancelling"}:
                await self._dispatcher.enqueue_generation(task.id)
                requeued += 1
            elif task.status in {"remote_submitted", "running", "downloading"}:
                self._repository.mark_needs_attention(task.id, "REMOTE_SUBMISSION_UNKNOWN")
                needs_attention += 1
        return RecoveryReport(requeued, resumed, needs_attention)
