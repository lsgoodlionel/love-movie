from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class GenerationKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


class GenerationStatus(StrEnum):
    DRAFT = "draft"
    VALIDATING = "validating"
    QUEUED = "queued"
    PLANNING = "planning"
    REMOTE_SUBMITTED = "remote_submitted"
    RUNNING = "running"
    DOWNLOADING = "downloading"
    QUALITY_CHECK = "quality_check"
    PERSISTED = "persisted"
    COMPLETED = "completed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"
    NEEDS_ATTENTION = "needs_attention"


RECOVERABLE_PERSISTED_PROMPT_ERRORS = {
    "REMOTE_SOFT_TIMEOUT",
    "REMOTE_TUNNEL_UNAVAILABLE",
    "REMOTE_UNAVAILABLE",
    "REMOTE_TIMEOUT",
    "DOWNLOAD_INTERRUPTED",
    "STORAGE_WRITE_FAILED",
    "GPU_LEASE_LOST",
    "REMOTE_CANCEL_UNCONFIRMED",
}


class CreateGenerationCommand(BaseModel):
    tenant_id: UUID
    project_id: UUID
    created_by: UUID
    kind: GenerationKind
    parameters: dict[str, Any] = Field(default_factory=dict)
    workflow_version: str = Field(min_length=1, max_length=120)
