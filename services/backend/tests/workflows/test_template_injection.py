from copy import deepcopy

from app.workflows.policies import ImageParameters, VideoParameters
from app.workflows.registry import WorkflowRegistry


def test_image_template_only_changes_declared_inputs() -> None:
    registry = WorkflowRegistry()
    source = registry.get("z_image_turbo", "v1").workflow
    original = deepcopy(source)

    rendered = registry.render_image_workflow(
        ImageParameters(prompt="雨夜中的未来城市", width=768, height=1024, steps=8, seed=42)
    )

    assert source == original
    assert rendered["4"]["inputs"]["text"] == "雨夜中的未来城市"
    assert rendered["6"]["inputs"]["width"] == 768
    assert rendered["8"]["inputs"]["seed"] == 42
    assert rendered["1"] == original["1"]


def test_video_template_injects_collision_safe_input_and_has_no_webp_node() -> None:
    registry = WorkflowRegistry()

    rendered = registry.render_video_workflow(
        VideoParameters(prompt="人物回头，镜头缓慢推进", negative_prompt="闪烁", seed=7),
        "tenant/project/task-random.png",
    )

    assert rendered["6"]["inputs"]["image"] == "tenant/project/task-random.png"
    assert rendered["10"]["inputs"]["length"] == 81
    assert rendered["14"]["inputs"]["fps"] == 16
    assert "16" not in rendered
