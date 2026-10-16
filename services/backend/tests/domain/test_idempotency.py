from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine

from app.domain.generation.models import Base
from app.domain.generation.repository import GenerationRepository
from app.domain.generation.schemas import CreateGenerationCommand, GenerationKind


def test_concurrent_duplicate_idempotency_key_creates_one_task(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'idempotency.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    repository = GenerationRepository(engine)
    command = CreateGenerationCommand(
        tenant_id=uuid4(),
        project_id=uuid4(),
        created_by=uuid4(),
        kind=GenerationKind.IMAGE,
        parameters={"prompt": "雨夜中的未来城市"},
        workflow_version="z_image_turbo:v1",
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: repository.create_or_get_task(command, "same-request"), range(2)))

    assert {task.id for task, _ in results}.__len__() == 1
    assert sorted(created for _, created in results) == [False, True]
