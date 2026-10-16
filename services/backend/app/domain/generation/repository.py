from typing import Any

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.domain.generation.models import GenerationEvent, GenerationStep, GenerationTask
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

    def persist_asset(
        self,
        task_id: Any,
        stored: StoredObject,
        kind: str,
        parent_asset_id: Any | None = None,
    ) -> Asset:
        with self._sessions.begin() as db:
            task = db.get(GenerationTask, task_id)
            if task is None:
                raise LookupError("生成任务不存在")
            asset = Asset(
                tenant_id=task.tenant_id,
                project_id=task.project_id,
                generation_task_id=task.id,
                parent_asset_id=parent_asset_id,
                kind=kind,
                object_key=stored.key,
                content_type=stored.content_type,
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
            )
            db.add(asset)
            db.flush()
            return asset

    def persist_plan(self, task_id: Any, plan: Any) -> None:
        with self._sessions.begin() as db:
            task = db.get(GenerationTask, task_id)
            if task is None:
                raise LookupError("生成任务不存在")
            parameters = dict(task.parameters)
            parameters["plan"] = plan.model_dump()
            task.parameters = parameters

    def persist_step_prompt(self, task_id: Any, step: str, prompt_id: str) -> None:
        with self._sessions.begin() as db:
            record = db.scalar(
                select(GenerationStep).where(
                    GenerationStep.generation_task_id == task_id,
                    GenerationStep.name == step,
                )
            )
            if record is None:
                record = GenerationStep(
                    generation_task_id=task_id,
                    name=step,
                    status="remote_submitted",
                    remote_prompt_id=prompt_id,
                    attempt_count=1,
                )
                db.add(record)
            else:
                record.status = "remote_submitted"
                record.remote_prompt_id = prompt_id

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

    def get_scoped_task(self, tenant_id: UUID, task_id: UUID) -> tuple[GenerationTask | None, bool]:
        with self._sessions() as db:
            task = db.get(GenerationTask, task_id)
            if task is None:
                return None, False
            if task.tenant_id != tenant_id:
                return None, True
            return task, False

    def request_cancellation(self, tenant_id: UUID, task_id: UUID) -> tuple[str, bool]:
        with self._sessions.begin() as db:
            task = db.get(GenerationTask, task_id)
            if task is None:
                raise LookupError("生成任务不存在")
            if task.tenant_id != tenant_id:
                return task.status, True
            task.cancellation_requested_at = datetime.now(timezone.utc)
            if task.status in {"draft", "validating", "queued"}:
                task.status = "cancelled"
            elif task.status not in {"completed", "cancelled", "failed"}:
                task.status = "cancelling"
            return task.status, False

    def append_event(self, task_id: Any, kind: str, message: str, progress: int | None = None) -> GenerationEvent:
        with self._sessions.begin() as db:
            event = GenerationEvent(
                generation_task_id=task_id,
                kind=kind,
                message=message,
                progress=progress,
            )
            db.add(event)
            db.flush()
            return event

    def events_after(self, task_id: UUID, last_event_id: int = 0) -> list[GenerationEvent]:
        with self._sessions() as db:
            return list(
                db.scalars(
                    select(GenerationEvent)
                    .where(
                        GenerationEvent.generation_task_id == task_id,
                        GenerationEvent.id > last_event_id,
                    )
                    .order_by(GenerationEvent.id)
                )
            )

    def list_assets(self, tenant_id: UUID, project_id: UUID | None = None) -> list[Asset]:
        with self._sessions() as db:
            query = select(Asset).where(Asset.tenant_id == tenant_id)
            if project_id is not None:
                query = query.where(Asset.project_id == project_id)
            return list(db.scalars(query.order_by(Asset.created_at.desc())))

    def get_scoped_asset(self, tenant_id: UUID, asset_id: UUID) -> tuple[Asset | None, bool]:
        with self._sessions() as db:
            asset = db.get(Asset, asset_id)
            if asset is None:
                return None, False
            if asset.tenant_id != tenant_id:
                return None, True
            return asset, False
