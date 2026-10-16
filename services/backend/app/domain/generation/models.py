import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.generation.schemas import GenerationStatus
from app.domain.identity.models import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GenerationTask(Base):
    __tablename__ = "generation_tasks"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_generation_tenant_idempotency"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(32), default=GenerationStatus.DRAFT.value, index=True)
    current_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    remote_prompt_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    workflow_version: Mapped[str] = mapped_column(String(120))
    idempotency_key: Mapped[str] = mapped_column(String(160))
    request_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GenerationStep(Base):
    __tablename__ = "generation_steps"
    __table_args__ = (UniqueConstraint("generation_task_id", "name", name="uq_generation_step_task_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    generation_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_tasks.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    remote_prompt_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    input_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UsageLedger(Base):
    __tablename__ = "usage_ledger"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    generation_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_tasks.id", ondelete="CASCADE"), index=True
    )
    requested_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actual_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    gpu_seconds: Mapped[float] = mapped_column(Float, default=0)
    storage_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    content_safety_decision: Mapped[str] = mapped_column(String(64), default="not_evaluated")
    adult_content_declared: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GenerationEvent(Base):
    __tablename__ = "generation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    generation_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_tasks.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(String(240))
    progress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = ["Base", "GenerationTask", "GenerationStep", "UsageLedger", "GenerationEvent"]
