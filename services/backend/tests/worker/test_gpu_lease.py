import asyncio
from contextlib import asynccontextmanager

from app.worker.gpu_lease import GpuLease


class MemoryLeaseBackend:
    def __init__(self) -> None:
        self.owner: str | None = None

    async def acquire(self, key: str, token: str, ttl_seconds: int) -> bool:
        if self.owner is not None:
            return False
        self.owner = token
        return True

    async def renew(self, key: str, token: str, ttl_seconds: int) -> bool:
        return self.owner == token

    async def release(self, key: str, token: str) -> bool:
        if self.owner != token:
            return False
        self.owner = None
        return True


def test_two_jobs_never_hold_gpu_lease_together() -> None:
    backend = MemoryLeaseBackend()
    lease = GpuLease(backend, ttl_seconds=1, retry_interval=0.001)
    active = 0
    peak = 0

    async def job(task_id: str) -> None:
        nonlocal active, peak
        async with lease.acquire(task_id):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    async def run_jobs() -> None:
        await asyncio.gather(job("one"), job("two"))

    asyncio.run(run_jobs())
    assert peak == 1


def test_lost_ownership_is_exposed_before_next_remote_step() -> None:
    backend = MemoryLeaseBackend()
    lease = GpuLease(backend, ttl_seconds=1, retry_interval=0)

    async def scenario() -> bool:
        async with lease.acquire("one") as guard:
            backend.owner = "another-worker"
            return await guard.renew()

    assert asyncio.run(scenario()) is False

