import pytest
from pydantic import ValidationError

from app.workflows.policies import ImageParameters, TenantQuota, VideoParameters


@pytest.mark.parametrize(
    ("field", "value"),
    [("width", 4096), ("height", 4096), ("steps", 101), ("batch_size", 5)],
)
def test_image_parameters_reject_server_limit_overrides(field: str, value: int) -> None:
    payload = {"prompt": "雨夜城市", "width": 768, "height": 1024, "steps": 8, "batch_size": 1}
    payload[field] = value

    with pytest.raises(ValidationError) as error:
        ImageParameters(**payload)

    assert field in str(error.value)


def test_video_parameters_reject_unverified_frame_count() -> None:
    with pytest.raises(ValidationError, match="frames"):
        VideoParameters(prompt="镜头缓慢推进", negative_prompt="闪烁", frames=240)


def test_quota_rejects_exhausted_gpu_or_storage() -> None:
    with pytest.raises(ValueError, match="GPU"):
        TenantQuota(remaining_gpu_seconds=0, remaining_storage_bytes=1024).ensure_available()
    with pytest.raises(ValueError, match="存储"):
        TenantQuota(remaining_gpu_seconds=100, remaining_storage_bytes=0).ensure_available()


def test_sexualized_minor_content_is_rejected() -> None:
    with pytest.raises(ValidationError, match="未成年人"):
        ImageParameters(prompt="一名 15 岁少女的性感裸露写真")


def test_adult_content_requires_explicit_adult_declaration() -> None:
    with pytest.raises(ValidationError, match="成年人确认"):
        ImageParameters(prompt="一名成年人的性感裸露艺术写真", adult_content_declared=False)
