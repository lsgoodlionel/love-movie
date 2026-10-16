from typing import Any
from uuid import UUID

from app.worker.queue import create_queue_pool


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


class LazyGenerationDispatcher:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._pool: Any | None = None

    async def enqueue_generation(self, task_id: UUID | str) -> str:
        if self._pool is None:
            self._pool = await create_queue_pool(self._redis_url)
        return await GenerationDispatcher(self._pool).enqueue_generation(task_id)
