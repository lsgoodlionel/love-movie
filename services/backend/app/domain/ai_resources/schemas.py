from pydantic import BaseModel, ConfigDict, Field


class ModelRouteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability: str = Field(min_length=1, max_length=80)
    quality: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=120)
    priority: int = Field(default=100, ge=0, le=1000)
    enabled: bool = True


class ModelRouteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: int | None = Field(default=None, ge=0, le=1000)
    enabled: bool | None = None
