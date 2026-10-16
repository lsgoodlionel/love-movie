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
            if task.status == "queued":
                await self._dispatcher.enqueue_generation(task.id)
                requeued += 1
            elif task.remote_prompt_id:
                async for event in self._comfyui.track(task.remote_prompt_id):
                    if event.kind == "completed":
                        break
                resumed += 1
            elif task.status in {"remote_submitted", "running", "downloading"}:
                self._repository.mark_needs_attention(task.id, "REMOTE_SUBMISSION_UNKNOWN")
                needs_attention += 1
        return RecoveryReport(requeued, resumed, needs_attention)
