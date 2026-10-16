import pytest

from app.workflows.model_router import ModelRouter


def test_default_model_routes_match_verified_hardware_policy() -> None:
    router = ModelRouter.defaults()

    assert router.select("cleanup", "interactive").model == "qwen3.5:4b"
    assert router.select("story_planning", "interactive").model == "qwen3.5:latest"
    assert router.select("dialogue_enhancement", "interactive").model == "gemma4:12b"


def test_large_models_require_async_or_manual_quality() -> None:
    router = ModelRouter.defaults()

    with pytest.raises(ValueError, match="不能用于同步交互"):
        router.select("longform_planning", "interactive")
    assert router.select("longform_planning", "high_quality_async").model in {"qwen3.8:27b", "qwen3.5:27b"}
    assert router.select("final_review", "manual").model == "gemma4:31b"
