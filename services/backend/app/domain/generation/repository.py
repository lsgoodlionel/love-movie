from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.domain.generation.models import GenerationTask
from app.domain.generation.models import UsageLedger
from app.domain.generation.schemas import CreateGenerationCommand, GenerationStatus
from app.domain.assets.models import Asset
from app.integrations.storage import StoredObject


class GenerationRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def create_or_get_task(
        self,
        command: CreateGenerationCommand,
        idempotency_key: str,
    ) -> tuple[GenerationTask, bool]:
        db = self._sessions()
        try:
            task = GenerationTask(
                tenant_id=command.tenant_id,
                project_id=command.project_id,
                created_by=command.created_by,
                kind=command.kind.value,
                status=GenerationStatus.DRAFT.value,
                parameters=command.parameters,
                workflow_version=command.workflow_version,
                idempotency_key=idempotency_key,
            )
            db.add(task)
            db.commit()
            return task, True
        except IntegrityError:
            db.rollback()
            existing = db.scalar(
                select(GenerationTask).where(
                    GenerationTask.tenant_id == command.tenant_id,
                    GenerationTask.idempotency_key == idempotency_key,
                )
            )
            if existing is None:
                raise
            return existing, False
        finally:
            db.close()

    def get_task(self, task_id: Any) -> GenerationTask | None:
        with self._sessions() as db:
            return db.get(GenerationTask, task_id)

    def set_status(self, task_id: Any, status: str, **values: Any) -> None:
        allowed = {"remote_prompt_id", "error_code", "current_step", "started_at", "finished_at"}
        with self._sessions.begin() as db:
            task = db.get(GenerationTask, task_id)
            if task is None:
                raise LookupError("生成任务不存在")
            task.status = status
            for name, value in values.items():
                if name not in allowed:
                    raise ValueError(f"不允许更新字段：{name}")
                setattr(task, name, value)

    def persist_asset(self, task_id: Any, stored: StoredObject, kind: str) -> Asset:
        with self._sessions.begin() as db:
            task = db.get(GenerationTask, task_id)
            if task is None:
                raise LookupError("生成任务不存在")
            asset = Asset(
                tenant_id=task.tenant_id,
                project_id=task.project_id,
                generation_task_id=task.id,
                kind=kind,
                object_key=stored.key,
                content_type=stored.content_type,
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
            )
            db.add(asset)
            db.flush()
            return asset

    def record_usage(self, task_id: Any, **values: Any) -> None:
        with self._sessions.begin() as db:
            task = db.get(GenerationTask, task_id)
            if task is None:
                raise LookupError("生成任务不存在")
            db.add(
                UsageLedger(
                    tenant_id=task.tenant_id,
                    project_id=task.project_id,
                    generation_task_id=task.id,
                    **values,
                )
            )
