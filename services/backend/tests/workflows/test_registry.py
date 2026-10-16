import pytest

from app.workflows.exceptions import UnknownWorkflow
from app.workflows.registry import WorkflowRegistry


def test_registry_rejects_unknown_workflow() -> None:
    registry = WorkflowRegistry()

    with pytest.raises(UnknownWorkflow):
        registry.get("user-uploaded-json", "v1")


def test_registry_only_exposes_reviewed_versions() -> None:
    registry = WorkflowRegistry()

    assert registry.get("z_image_turbo", "v1").name == "z_image_turbo"
    assert registry.get("wan_i2v", "v1").version == "v1"
