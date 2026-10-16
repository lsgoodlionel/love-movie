import asyncio
from dataclasses import dataclass

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

    def incomplete_tasks(self):
        return self.tasks

    def mark_needs_attention(self, task_id: str, code: str):
        self.attention.append(task_id)


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

    async def track(self, prompt_id: str):
        self.tracked.append(prompt_id)
        yield type("Event", (), {"kind": "completed"})()

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

    assert dispatcher.queued == ["queued"]
    assert comfy.tracked == ["prompt-9"]
    assert comfy.submitted == 0
    assert repo.attention == ["unknown"]
    assert report.requeued == 1
    assert report.resumed == 1
    assert report.needs_attention == 1
