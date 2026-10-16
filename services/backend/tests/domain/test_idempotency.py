from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine

from app.domain.generation.models import Base
from app.domain.generation.repository import GenerationRepository, IdempotencyConflict
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


def test_same_key_with_different_command_is_rejected(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'conflict.db'}")
    Base.metadata.create_all(engine)
    repository = GenerationRepository(engine)
    command = CreateGenerationCommand(
        tenant_id=uuid4(),
        project_id=uuid4(),
        created_by=uuid4(),
        kind=GenerationKind.IMAGE,
        parameters={"prompt": "雨夜"},
        workflow_version="z_image_turbo:v1",
    )
    repository.create_or_get_task(command, "same-key")
    changed = CreateGenerationCommand(
        tenant_id=command.tenant_id,
        project_id=command.project_id,
        created_by=command.created_by,
        kind=command.kind,
        parameters={"prompt": "晴天"},
        workflow_version=command.workflow_version,
    )

    with pytest.raises(IdempotencyConflict):
        repository.create_or_get_task(changed, "same-key")
