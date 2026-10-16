from fastapi import FastAPI
from sqlalchemy import Engine, create_engine

from app.api.auth import router as auth_router
from app.api.projects import router as projects_router
from app.api.generations import router as generations_router
from app.core.config import Settings, get_settings
from app.domain.generation.repository import GenerationRepository
from app.domain.identity.repository import IdentityRepository


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    dispatcher: object | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(title="爱视频 API", version="0.1.0")
    resolved_engine = engine or create_engine(resolved_settings.database_url, pool_pre_ping=True)
    app.state.settings = resolved_settings
    app.state.identity_repository = IdentityRepository(resolved_engine, create_schema=engine is not None)
    app.state.generation_repository = GenerationRepository(resolved_engine)
    app.state.generation_dispatcher = dispatcher

    @app.get("/health/live", tags=["系统"])
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(projects_router)
    app.include_router(generations_router)
    return app


app = create_app()
