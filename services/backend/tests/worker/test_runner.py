import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.worker.runner import GenerationRunner
from app.worker.gpu_lease import LeaseGuard
from app.integrations.errors import RemoteServiceError


class Repo:
    def __init__(self, task):
        self.task = task
        self.statuses = []

    def get_task(self, task_id):
        return self.task

    def set_status(self, task_id, status, **values):
        self.statuses.append(status)


class Service:
    def __init__(self):
        self.calls = []

    async def run(self, task_id):
        self.calls.append(task_id)


class FailingService(Service):
    async def run(self, task_id):
        raise RemoteServiceError("REMOTE_SUBMISSION_UNKNOWN", "未确认")


class SoftTimeoutService(Service):
    async def run(self, task_id):
        raise RemoteServiceError("REMOTE_SOFT_TIMEOUT", "等待生成结果超时")


class LostLeaseService(Service):
    async def run(self, task_id):
        LeaseGuard(None, "lease", "token", 30, lost=True).ensure_owned()


class CancelUnconfirmedService(Service):
    async def run(self, task_id):
        raise RemoteServiceError("REMOTE_CANCEL_UNCONFIRMED", "远程任务取消尚未确认")


class SnapshotRepo(Repo):
    def __init__(self, first, persisted):
        super().__init__(first)
        self.persisted = persisted
        self.reads = 0

    def get_task(self, task_id):
        self.reads += 1
        return self.task if self.reads == 1 else self.persisted


def test_running_remote_task_cancellation_is_delegated_to_service() -> None:
    task_id = uuid4()
    repo = Repo(
        SimpleNamespace(
            id=task_id,
            kind="image",
            status="cancelling",
            cancellation_requested_at=datetime.now(timezone.utc),
            remote_prompt_id="prompt-running",
        )
    )
    image = Service()

    asyncio.run(GenerationRunner(repo, image, Service()).run(str(task_id)))

    assert image.calls == [task_id]
    assert repo.statuses == []


def test_queued_cancellation_finishes_without_remote_service() -> None:
    task_id = uuid4()
    repo = Repo(
        SimpleNamespace(
            id=task_id,
            kind="image",
            status="cancelled",
            cancellation_requested_at=datetime.now(timezone.utc),
            remote_prompt_id=None,
        )
    )
    image = Service()

    asyncio.run(GenerationRunner(repo, image, Service()).run(str(task_id)))

    assert image.calls == []
    assert repo.statuses == ["cancelled"]


def test_uncertain_remote_submission_needs_attention() -> None:
    task_id = uuid4()
    repo = Repo(
        SimpleNamespace(
            id=task_id,
            kind="image",
            status="running",
            cancellation_requested_at=None,
            remote_prompt_id=None,
        )
    )

    try:
        asyncio.run(GenerationRunner(repo, FailingService(), Service()).run(str(task_id)))
    except RemoteServiceError:
        pass

    assert repo.statuses == ["needs_attention"]


def test_soft_timeout_after_prompt_persisted_needs_attention() -> None:
    task_id = uuid4()
    initial = SimpleNamespace(
        id=task_id,
        kind="image",
        status="running",
        cancellation_requested_at=None,
        remote_prompt_id=None,
    )
    persisted = SimpleNamespace(
        id=task_id,
        kind="image",
        status="running",
        cancellation_requested_at=None,
        remote_prompt_id="prompt-persisted",
    )
    repo = SnapshotRepo(initial, persisted)

    try:
        asyncio.run(GenerationRunner(repo, SoftTimeoutService(), Service()).run(str(task_id)))
    except RemoteServiceError:
        pass

    assert repo.reads >= 2
    assert repo.statuses == ["needs_attention"]


def test_lost_gpu_lease_after_prompt_persisted_needs_attention() -> None:
    task_id = uuid4()
    repo = Repo(
        SimpleNamespace(
            id=task_id,
            kind="image",
            status="running",
            cancellation_requested_at=None,
            remote_prompt_id="prompt-persisted",
        )
    )

    try:
        asyncio.run(GenerationRunner(repo, LostLeaseService(), Service()).run(str(task_id)))
    except RuntimeError:
        pass

    assert repo.statuses == ["needs_attention"]


def test_cancel_unconfirmed_after_cancellation_persisted_needs_attention() -> None:
    task_id = uuid4()
    initial = SimpleNamespace(
        id=task_id,
        kind="image",
        status="running",
        cancellation_requested_at=None,
        remote_prompt_id="prompt-persisted",
    )
    persisted = SimpleNamespace(
        id=task_id,
        kind="image",
        status="cancelling",
        cancellation_requested_at=datetime.now(timezone.utc),
        remote_prompt_id="prompt-persisted",
    )
    repo = SnapshotRepo(initial, persisted)

    try:
        asyncio.run(GenerationRunner(repo, CancelUnconfirmedService(), Service()).run(str(task_id)))
    except RemoteServiceError:
        pass

    assert repo.statuses == ["needs_attention"]
