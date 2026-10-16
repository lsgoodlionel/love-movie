import asyncio
import uuid

from app.services.generation_dispatcher import GenerationDispatcher


class FakeArqPool:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def enqueue_job(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return type("Job", (), {"job_id": kwargs["_job_id"]})()


def test_dispatch_uses_generation_uuid_as_stable_job_id() -> None:
    pool = FakeArqPool()
    dispatcher = GenerationDispatcher(pool)
    task_id = uuid.uuid4()
    first = asyncio.run(dispatcher.enqueue_generation(task_id))
    second = asyncio.run(dispatcher.enqueue_generation(task_id))

    assert first == second == str(task_id)
    assert all(call[1]["_job_id"] == str(task_id) for call in pool.calls)

