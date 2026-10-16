from typing import Any
from uuid import UUID


class GenerationDispatcher:
    def __init__(self, queue_pool: Any) -> None:
        self._queue_pool = queue_pool

    async def enqueue_generation(self, task_id: UUID | str) -> str:
        stable_id = str(task_id)
        job = await self._queue_pool.enqueue_job(
            "run_generation",
            stable_id,
            _job_id=stable_id,
        )
        return stable_id if job is None else str(job.job_id)
