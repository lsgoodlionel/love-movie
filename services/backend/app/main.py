from fastapi import FastAPI
from sqlalchemy import Engine, create_engine
import boto3
from botocore.client import Config

from app.api.auth import router as auth_router
from app.api.projects import router as projects_router
from app.api.generations import router as generations_router
from app.api.tasks import router as tasks_router
from app.api.assets import router as assets_router
from app.api.admin_health import OperationalHealthProbe, router as admin_health_router
from app.api.admin_ai_resources import router as admin_ai_resources_router
from app.core.config import Settings, get_settings
from app.domain.generation.repository import GenerationRepository
from app.domain.ai_resources.repository import AIResourceRepository
from app.domain.identity.repository import IdentityRepository
from app.integrations.storage import StorageAdapter
from app.services.generation_dispatcher import LazyGenerationDispatcher


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    dispatcher: object | None = None,
    storage: object | None = None,
    health_probe: object | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(title="爱视频 API", version="0.1.0")
    resolved_engine = engine or create_engine(resolved_settings.database_url, pool_pre_ping=True)
    app.state.settings = resolved_settings
    app.state.identity_repository = IdentityRepository(resolved_engine, create_schema=engine is not None)
    app.state.generation_repository = GenerationRepository(resolved_engine)
    app.state.generation_dispatcher = dispatcher or LazyGenerationDispatcher(resolved_settings.redis_url)
    if storage is None:
        presigner = boto3.client(
            "s3",
            endpoint_url=resolved_settings.object_storage_public_endpoint,
            aws_access_key_id=resolved_settings.object_storage_access_key,
            aws_secret_access_key=resolved_settings.object_storage_secret_key.get_secret_value(),
            region_name="us-east-1",
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        storage = StorageAdapter(presigner, resolved_settings.object_storage_bucket)
    app.state.storage = storage
    app.state.health_probe = health_probe or OperationalHealthProbe(resolved_settings, resolved_engine)
    app.state.ai_resource_repository = AIResourceRepository(resolved_engine)

    @app.get("/health/live", tags=["系统"])
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(projects_router)
    app.include_router(generations_router)
    app.include_router(tasks_router)
    app.include_router(assets_router)
    app.include_router(admin_health_router)
    app.include_router(admin_ai_resources_router)
    return app


app = create_app()
