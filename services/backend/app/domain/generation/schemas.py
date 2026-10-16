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


class CreateGenerationCommand(BaseModel):
    tenant_id: UUID
    project_id: UUID
    created_by: UUID
    kind: GenerationKind
    parameters: dict[str, Any] = Field(default_factory=dict)
    workflow_version: str = Field(min_length=1, max_length=120)
