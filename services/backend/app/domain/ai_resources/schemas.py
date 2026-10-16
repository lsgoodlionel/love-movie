from pydantic import BaseModel, Field


class ModelRouteConfig(BaseModel):
    capability: str = Field(min_length=1, max_length=80)
    quality: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=120)
    priority: int = Field(default=100, ge=0, le=1000)
    enabled: bool = True
