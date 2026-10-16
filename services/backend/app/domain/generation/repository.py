from typing import Any

import hashlib
import json

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.domain.generation.models import GenerationEvent, GenerationStep, GenerationTask
from app.domain.generation.models import UsageLedger
from app.domain.generation.schemas import CreateGenerationCommand, GenerationStatus
from app.domain.assets.models import Asset
from app.integrations.storage import StoredObject
from app.domain.identity.models import Tenant


_STATUS_EVENTS = {
    "queued": ("已进入生成队列", 5),
    "planning": ("正在理解创意并规划镜头", 12),
    "remote_submitted": ("任务已提交到生成服务", 20),
    "running": ("正在生成素材", 45),
    "downloading": ("正在保存生成结果", 85),
    "completed": ("生成完成", 100),
    "cancelling": ("正在取消任务", None),
    "cancelled": ("任务已取消", None),
    "failed": ("生成未完成", None),
    "needs_attention": ("任务需要人工处理", None),
}


class IdempotencyConflict(ValueError):
    pass


class QuotaExceeded(ValueError):
    pass


def _command_digest(command: CreateGenerationCommand) -> str:
    payload = {
        "tenant_id": str(command.tenant_id),
        "project_id": str(command.project_id),
        "created_by": str(command.created_by),
        "kind": command.kind.value,
        "parameters": command.parameters,
        "workflow_version": command.workflow_version,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class GenerationRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def create_or_get_task(
        self,
        command: CreateGenerationCommand,
        idempotency_key: str,
    ) -> tuple[GenerationTask, bool]:
        request_digest = _command_digest(command)
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
                request_digest=request_digest,
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
            if existing.request_digest != request_digest:
                raise IdempotencyConflict("同一幂等键不能用于不同的生成请求")
            return existing, False
        finally:
            db.close()

    def ensure_quota(
        self,
        tenant_id: UUID,
        *,
        estimated_gpu_seconds: float,
        estimated_storage_bytes: int,
    ) -> None:
        with self._sessions() as db:
            tenant = db.get(Tenant, tenant_id)
            if tenant is None:
                raise LookupError("租户不存在")
            gpu_used, storage_used = db.execute(
                select(
                    func.coalesce(func.sum(UsageLedger.gpu_seconds), 0),
                    func.coalesce(func.sum(UsageLedger.storage_bytes), 0),
                ).where(UsageLedger.tenant_id == tenant_id)
            ).one()
            if tenant.gpu_seconds_limit is not None and float(gpu_used) + estimated_gpu_seconds > tenant.gpu_seconds_limit:
                raise QuotaExceeded("GPU 生成配额不足")
            if tenant.storage_bytes_limit is not None and int(storage_used) + estimated_storage_bytes > tenant.storage_bytes_limit:
                raise QuotaExceeded("素材存储配额不足")

    def get_task(self, task_id: Any) -> GenerationTask | None:
        with self._sessions() as db:
            return db.get(GenerationTask, task_id)

    def incomplete_tasks(self) -> list[GenerationTask]:
        with self._sessions() as db:
            return list(
                db.scalars(
                    select(GenerationTask).where(
                        GenerationTask.status.in_(
                            {"queued", "planning", "remote_submitted", "running", "downloading", "cancelling"}
                        )
                    )
                )
            )

    def mark_needs_attention(self, task_id: Any, error_code: str) -> None:
        self.set_status(task_id, "needs_attention", error_code=error_code)

    def is_cancellation_requested(self, task_id: Any) -> bool:
        with self._sessions() as db:
            task = db.get(GenerationTask, task_id)
            return bool(task and task.cancellation_requested_at is not None)

    def get_step(self, task_id: Any, name: str) -> GenerationStep | None:
        with self._sessions() as db:
            return db.scalar(
                select(GenerationStep).where(
                    GenerationStep.generation_task_id == task_id,
                    GenerationStep.name == name,
                )
            )

    def find_asset(self, task_id: Any, kind: str) -> Asset | None:
        with self._sessions() as db:
            return db.scalar(
                select(Asset)
                .where(Asset.generation_task_id == task_id, Asset.kind == kind)
                .order_by(Asset.created_at.desc())
            )

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
            message, progress = _STATUS_EVENTS.get(status, ("任务状态已更新", None))
            db.add(
                GenerationEvent(
                    generation_task_id=task.id,
                    kind=status,
                    message=message,
                    progress=progress,
                )
            )

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

    def list_tasks(
        self,
        tenant_id: UUID,
        accessible_project_ids: set[UUID],
        *,
        project_id: UUID | None = None,
        limit: int = 50,
    ) -> list[GenerationTask]:
        if not accessible_project_ids:
            return []
        with self._sessions() as db:
            query = select(GenerationTask).where(
                GenerationTask.tenant_id == tenant_id,
                GenerationTask.project_id.in_(accessible_project_ids),
            )
            if project_id is not None:
                query = query.where(GenerationTask.project_id == project_id)
            return list(db.scalars(query.order_by(GenerationTask.created_at.desc()).limit(limit)))

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
            message, progress = _STATUS_EVENTS[task.status]
            db.add(GenerationEvent(generation_task_id=task.id, kind=task.status, message=message, progress=progress))
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

    def list_assets(
        self,
        tenant_id: UUID,
        project_id: UUID | None = None,
        *,
        accessible_project_ids: set[UUID] | None = None,
    ) -> list[Asset]:
        with self._sessions() as db:
            query = select(Asset).where(Asset.tenant_id == tenant_id)
            if project_id is not None:
                query = query.where(Asset.project_id == project_id)
            elif accessible_project_ids is not None:
                if not accessible_project_ids:
                    return []
                query = query.where(Asset.project_id.in_(accessible_project_ids))
            return list(db.scalars(query.order_by(Asset.created_at.desc())))

    def get_scoped_asset(self, tenant_id: UUID, asset_id: UUID) -> tuple[Asset | None, bool]:
        with self._sessions() as db:
            asset = db.get(Asset, asset_id)
            if asset is None:
                return None, False
            if asset.tenant_id != tenant_id:
                return None, True
            return asset, False
