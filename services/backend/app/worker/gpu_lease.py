import asyncio
import uuid
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import AsyncIterator, Protocol


class LeaseBackend(Protocol):
    async def acquire(self, key: str, token: str, ttl_seconds: int) -> bool: ...
    async def renew(self, key: str, token: str, ttl_seconds: int) -> bool: ...
    async def release(self, key: str, token: str) -> bool: ...


class GpuLeaseLostError(RuntimeError):
    code = "GPU_LEASE_LOST"

    def __init__(self) -> None:
        super().__init__(self.code)


class RedisLeaseBackend:
    _RENEW = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
      return redis.call('expire', KEYS[1], ARGV[2])
    end
    return 0
    """
    _RELEASE = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
      return redis.call('del', KEYS[1])
    end
    return 0
    """

    def __init__(self, redis: object) -> None:
        self._redis = redis

    async def acquire(self, key: str, token: str, ttl_seconds: int) -> bool:
        return bool(await self._redis.set(key, token, ex=ttl_seconds, nx=True))  # type: ignore[attr-defined]

    async def renew(self, key: str, token: str, ttl_seconds: int) -> bool:
        return bool(await self._redis.eval(self._RENEW, 1, key, token, ttl_seconds))  # type: ignore[attr-defined]

    async def release(self, key: str, token: str) -> bool:
        return bool(await self._redis.eval(self._RELEASE, 1, key, token))  # type: ignore[attr-defined]


@dataclass
class LeaseGuard:
    backend: LeaseBackend
    key: str
    token: str
    ttl_seconds: int
    lost: bool = False

    async def renew(self) -> bool:
        owned = await self.backend.renew(self.key, self.token, self.ttl_seconds)
        self.lost = not owned
        return owned

    def ensure_owned(self) -> None:
        if self.lost:
            raise GpuLeaseLostError()


class GpuLease:
    def __init__(
        self,
        backend: LeaseBackend,
        *,
        key: str = "love-movie:gpu:lease",
        ttl_seconds: int = 30,
        retry_interval: float = 0.5,
    ) -> None:
        self._backend = backend
        self._key = key
        self._ttl_seconds = ttl_seconds
        self._retry_interval = retry_interval

    @asynccontextmanager
    async def acquire(self, task_id: str) -> AsyncIterator[LeaseGuard]:
        token = f"{task_id}:{uuid.uuid4()}"
        while not await self._backend.acquire(self._key, token, self._ttl_seconds):
            await asyncio.sleep(self._retry_interval)
        guard = LeaseGuard(self._backend, self._key, token, self._ttl_seconds)

        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(max(self._ttl_seconds / 3, 0.01))
                if not await guard.renew():
                    return

        heartbeat_task = asyncio.create_task(heartbeat())
        try:
            yield guard
        finally:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
            await self._backend.release(self._key, token)
