import asyncio
from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.domain.generation.repository import GenerationRepository
from app.domain.generation.schemas import CreateGenerationCommand, GenerationKind
from app.domain.identity.repository import IdentityRepository
from app.worker.recovery import RecoveryCoordinator


@dataclass
class Task:
    id: str
    status: str
    remote_prompt_id: str | None = None
    error_code: str | None = None


class Repo:
    def __init__(self, tasks: list[Task]) -> None:
        self.tasks = tasks
        self.attention: list[str] = []
        self.confirmed: list[str] = []

    def incomplete_tasks(self):
        return self.tasks

    def mark_needs_attention(self, task_id: str, code: str):
        self.attention.append(task_id)

    def set_status(self, task_id: str, status: str):
        return None

    def mark_dispatch_confirmed(self, task_id: str):
        self.confirmed.append(task_id)


class Dispatcher:
    def __init__(self) -> None:
        self.queued: list[str] = []

    async def enqueue_generation(self, task_id: str) -> str:
        self.queued.append(task_id)
        return task_id


class Comfy:
    def __init__(self) -> None:
        self.tracked: list[str] = []
        self.submitted = 0

    async def history(self, prompt_id: str):
        self.tracked.append(prompt_id)
        return type("Event", (), {"kind": "completed"})()

    async def submit(self, workflow, client_id):
        self.submitted += 1


def test_recovery_tracks_persisted_prompt_without_resubmission() -> None:
    repo = Repo(
        [
            Task("queued", "queued"),
            Task("remote", "running", remote_prompt_id="prompt-9", error_code="REMOTE_1033"),
            Task("unknown", "remote_submitted"),
            Task("done", "completed"),
        ]
    )
    dispatcher = Dispatcher()
    comfy = Comfy()
    report = asyncio.run(RecoveryCoordinator(repo, dispatcher, comfy).recover_incomplete_tasks())

    assert dispatcher.queued == ["queued", "remote"]
    assert comfy.tracked == ["prompt-9"]
    assert comfy.submitted == 0
    assert repo.attention == ["unknown"]
    assert report.requeued == 1
    assert report.resumed == 1
    assert report.needs_attention == 1


def test_recovery_uses_real_sql_repository_and_persisted_prompt() -> None:
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    identity = IdentityRepository(engine, create_schema=True)
    tenant, user = identity.create_tenant_with_user(
        tenant_name="恢复团队", email="recover@example.com", password="safe-password-123", role="creator"
    )
    principal = identity.authenticate("recover@example.com", "safe-password-123")
    project = identity.create_project(principal, "恢复项目")
    repository = GenerationRepository(engine)
    task, _ = repository.create_or_get_task(
        CreateGenerationCommand(
            tenant_id=tenant.id,
            project_id=project.id,
            created_by=user.id,
            kind=GenerationKind.IMAGE,
            parameters={"prompt": "晨雾"},
            workflow_version="z_image_turbo:v1",
        ),
        "recover-real-1",
    )
    repository.set_status(task.id, "running", remote_prompt_id="prompt-persisted")
    dispatcher = Dispatcher()
    comfy = Comfy()

    report = asyncio.run(RecoveryCoordinator(repository, dispatcher, comfy).recover_incomplete_tasks())

    assert dispatcher.queued == [task.id]
    assert comfy.tracked == ["prompt-persisted"]
    assert comfy.submitted == 0
    assert report.resumed == 1
