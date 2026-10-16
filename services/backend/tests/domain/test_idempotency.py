from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from app.domain.generation.models import Base, GenerationTask
from app.domain.generation.repository import GenerationRepository, IdempotencyConflict, QuotaExceeded
from app.domain.generation.schemas import CreateGenerationCommand, GenerationKind
from app.domain.identity.models import Tenant


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


def test_legacy_null_digest_is_backfilled_for_matching_request(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")
    Base.metadata.create_all(engine)
    repository = GenerationRepository(engine)
    command = CreateGenerationCommand(
        tenant_id=uuid4(), project_id=uuid4(), created_by=uuid4(), kind=GenerationKind.IMAGE,
        parameters={"prompt": "旧请求"}, workflow_version="z_image_turbo:v1",
    )
    task, _ = repository.create_or_get_task(command, "legacy-key")
    with engine.begin() as connection:
        connection.execute(update(GenerationTask).where(GenerationTask.id == task.id).values(request_digest=None))

    existing, created = repository.create_or_get_task(command, "legacy-key")

    assert created is False
    assert existing.request_digest is not None


def test_quota_reservation_blocks_new_work_but_not_idempotent_retry(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'quota.db'}")
    Base.metadata.create_all(engine)
    tenant_id = uuid4()
    with Session(engine) as db:
        db.add(Tenant(id=tenant_id, name="配额团队", gpu_seconds_limit=100, storage_bytes_limit=1000))
        db.commit()
    repository = GenerationRepository(engine)
    command = CreateGenerationCommand(
        tenant_id=tenant_id, project_id=uuid4(), created_by=uuid4(), kind=GenerationKind.IMAGE,
        parameters={"prompt": "配额请求"}, workflow_version="z_image_turbo:v1",
    )
    first, _ = repository.create_or_get_task(
        command, "quota-key-1", estimated_gpu_seconds=60, estimated_storage_bytes=600
    )

    same, created = repository.create_or_get_task(
        command, "quota-key-1", estimated_gpu_seconds=60, estimated_storage_bytes=600
    )
    assert same.id == first.id
    assert created is False

    with pytest.raises(QuotaExceeded):
        repository.create_or_get_task(
            command, "quota-key-2", estimated_gpu_seconds=60, estimated_storage_bytes=600
        )
