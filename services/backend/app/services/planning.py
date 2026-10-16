from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlannedPrompts(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str = Field(min_length=1, max_length=200)
    image_prompt: str = Field(min_length=1, max_length=4000)
    motion_prompt: str = Field(min_length=1, max_length=4000)
    negative_prompt: str = Field(default="", max_length=4000)
    requested_model: str | None = None
    actual_model: str | None = None
    fallback_reason: str | None = None


class PlanningService:
    def __init__(self, model_router: Any, ollama: Any) -> None:
        self._model_router = model_router
        self._ollama = ollama

    async def plan(self, source_text: str) -> PlannedPrompts:
        selection = self._model_router.select("story_planning", "interactive")
        raw = await self._ollama.plan_video_text(source_text, model=selection.model)
        if not isinstance(raw, dict):
            raw = {
                "title": getattr(raw, "title", None) or source_text[:80],
                "image_prompt": getattr(raw, "image_prompt", None),
                "motion_prompt": getattr(raw, "motion_prompt", None)
                or getattr(raw, "video_prompt", None),
                "negative_prompt": getattr(raw, "negative_prompt", ""),
            }
        plan = PlannedPrompts.model_validate(raw)
        plan.requested_model = selection.model
        plan.actual_model = selection.model
        await self._ollama.wait_until_unloaded()
        return plan
