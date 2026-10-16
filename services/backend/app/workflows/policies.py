import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator


_SEXUAL_TERMS = re.compile(r"性感|裸露|裸体|性行为|nude|nudity|sexual", re.IGNORECASE)
_MINOR_AGE = re.compile(r"(?:^|\D)([0-9]|1[0-7])\s*岁")
_MINOR_TERMS = re.compile(r"未成年|儿童|小学生|初中生|child|teenager", re.IGNORECASE)


def _validate_content(prompt: str, adult_content_declared: bool) -> None:
    if _SEXUAL_TERMS.search(prompt) and (_MINOR_AGE.search(prompt) or _MINOR_TERMS.search(prompt)):
        raise ValueError("禁止涉及未成年人的性化内容")
    if _SEXUAL_TERMS.search(prompt) and not adult_content_declared:
        raise ValueError("成人内容需要明确的成年人确认")


class ImageParameters(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    width: int = Field(default=768, ge=256, le=2048, multiple_of=64)
    height: int = Field(default=1024, ge=256, le=2048, multiple_of=64)
    steps: int = Field(default=8, ge=1, le=50)
    batch_size: int = Field(default=1, ge=1, le=4)
    seed: int = Field(default=0, ge=0, le=2**63 - 1)
    adult_content_declared: bool = False

    @model_validator(mode="after")
    def validate_content_declaration(self) -> "ImageParameters":
        _validate_content(self.prompt, self.adult_content_declared)
        return self


CameraPose = Literal[
    "Static",
    "Pan Up",
    "Pan Down",
    "Pan Left",
    "Pan Right",
    "Zoom In",
    "Zoom Out",
    "Anti Clockwise (ACW)",
    "ClockWise (CW)",
]


class VideoParameters(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    negative_prompt: str = Field(default="", max_length=4000)
    width: int = Field(default=512, ge=512, le=512)
    height: int = Field(default=512, ge=512, le=512)
    frames: int = Field(default=81, ge=81, le=81)
    fps: int = Field(default=16, ge=16, le=16)
    steps: int = Field(default=20, ge=20, le=20)
    seed: int = Field(default=0, ge=0, le=2**63 - 1)
    camera_pose: CameraPose = "Zoom In"
    camera_speed: float = Field(default=0.45, ge=0.1, le=1.0)
    adult_content_declared: bool = False

    @model_validator(mode="after")
    def validate_content_declaration(self) -> "VideoParameters":
        _validate_content(self.prompt, self.adult_content_declared)
        return self


class TenantQuota(BaseModel):
    remaining_gpu_seconds: float = Field(ge=0)
    remaining_storage_bytes: int = Field(ge=0)

    def ensure_available(self) -> None:
        if self.remaining_gpu_seconds <= 0:
            raise ValueError("GPU 秒数配额已用尽")
        if self.remaining_storage_bytes <= 0:
            raise ValueError("存储配额已用尽")
