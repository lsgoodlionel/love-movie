from uuid import uuid4

from app.domain.assets.models import Asset
from app.domain.assets.schemas import AssetKind
from app.domain.generation.models import UsageLedger


def test_video_asset_references_first_frame_and_originating_task() -> None:
    task_id = uuid4()
    first_frame = Asset(
        id=uuid4(),
        tenant_id=uuid4(),
        project_id=uuid4(),
        generation_task_id=task_id,
        kind=AssetKind.IMAGE.value,
        object_key="tenant/project/first-frame.png",
        content_type="image/png",
        size_bytes=100,
        sha256="a" * 64,
    )
    video = Asset(
        id=uuid4(),
        tenant_id=first_frame.tenant_id,
        project_id=first_frame.project_id,
        generation_task_id=task_id,
        parent_asset_id=first_frame.id,
        kind=AssetKind.VIDEO.value,
        object_key="tenant/project/shot.mp4",
        content_type="video/mp4",
        size_bytes=200,
        sha256="b" * 64,
    )

    assert video.parent_asset_id == first_frame.id
    assert video.generation_task_id == task_id


def test_usage_ledger_keeps_model_safety_and_resource_audit_without_credentials() -> None:
    usage = UsageLedger(
        tenant_id=uuid4(),
        project_id=uuid4(),
        generation_task_id=uuid4(),
        requested_model="qwen3.5:latest",
        actual_model="qwen3.5:4b",
        fallback_reason="资源不足",
        gpu_seconds=12.5,
        storage_bytes=2048,
        content_safety_decision="allow_adult",
        adult_content_declared=True,
    )

    assert usage.requested_model == "qwen3.5:latest"
    assert usage.actual_model == "qwen3.5:4b"
    assert usage.adult_content_declared is True
    assert all("secret" not in column.name and "credential" not in column.name for column in UsageLedger.__table__.columns)
