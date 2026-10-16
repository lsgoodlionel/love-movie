import asyncio

import pytest

from app.services.planning import PlannedPrompts, PlanningService


class Router:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def select(self, capability: str, quality: str):
        self.calls.append((capability, quality))
        return type("Selection", (), {"model": "qwen3.5:latest"})()


class Ollama:
    def __init__(self, unload_error: Exception | None = None) -> None:
        self.model = None
        self.unload_error = unload_error

    async def plan_video_text(self, request: str, *, model: str):
        self.model = model
        return {
            "title": "清晨山谷",
            "image_prompt": "电影感，清晨山谷，薄雾",
            "motion_prompt": "镜头缓慢向前推进，薄雾流动",
            "negative_prompt": "画面抖动，文字，水印",
        }

    async def wait_until_unloaded(self):
        if self.unload_error:
            raise self.unload_error


def test_planning_selects_configured_model_and_validates_schema() -> None:
    router = Router()
    ollama = Ollama()
    plan = asyncio.run(PlanningService(router, ollama).plan("山谷中的清晨"))
    assert isinstance(plan, PlannedPrompts)
    assert router.calls == [("story_planning", "interactive")]
    assert ollama.model == "qwen3.5:latest"
    assert plan.motion_prompt.startswith("镜头")


def test_planning_rejects_missing_or_oversized_fields() -> None:
    with pytest.raises(ValueError):
        PlannedPrompts(title="", image_prompt="图", motion_prompt="动", negative_prompt="")
    with pytest.raises(ValueError):
        PlannedPrompts(title="标题", image_prompt="图" * 4001, motion_prompt="动", negative_prompt="")

