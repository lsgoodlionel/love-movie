from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    CREATOR = "creator"
    REVIEWER = "reviewer"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)


class CurrentUser(BaseModel):
    id: UUID
    tenant_id: UUID
    email: str
    role: Role

    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProjectView(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)
