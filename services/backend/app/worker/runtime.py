import boto3
from botocore.client import Config
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.domain.generation.repository import GenerationRepository
from app.integrations.access_headers import AccessHeaders
from app.integrations.comfyui import ComfyUIAdapter
from app.integrations.ollama import OllamaAdapter
from app.integrations.storage import StorageAdapter
from app.services.image_generation import ImageGenerationService
from app.services.planning import PlanningService
from app.services.video_generation import VideoGenerationService
from app.worker.gpu_lease import GpuLease, RedisLeaseBackend
from app.worker.runner import GenerationRunner
from app.workflows.model_router import ModelRouter


def _s3_client(endpoint: str, settings):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.object_storage_access_key,
        aws_secret_access_key=settings.object_storage_secret_key.get_secret_value(),
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


async def startup_worker(ctx: dict) -> None:
    settings = get_settings()
    repository = GenerationRepository(create_engine(settings.database_url, pool_pre_ping=True))
    access = AccessHeaders(settings.cf_access_client_id, settings.cf_access_client_secret)
    ollama = OllamaAdapter(settings.ollama_base_url, access)
    comfyui = ComfyUIAdapter(settings.comfyui_base_url, access)
    storage = StorageAdapter(
        _s3_client(settings.object_storage_endpoint, settings),
        settings.object_storage_bucket,
    )
    lease = GpuLease(RedisLeaseBackend(ctx["redis"]))
    planning = PlanningService(ModelRouter.defaults(), ollama)
    image_service = ImageGenerationService(repository, comfyui, storage, lease)
    video_service = VideoGenerationService(repository, planning, comfyui, storage, lease)
    ctx["generation_runner"] = GenerationRunner(repository, image_service, video_service)
    ctx["ollama_adapter"] = ollama
    ctx["comfyui_adapter"] = comfyui


async def shutdown_worker(ctx: dict) -> None:
    for name in ("ollama_adapter", "comfyui_adapter"):
        adapter = ctx.get(name)
        if adapter is not None:
            await adapter.aclose()
