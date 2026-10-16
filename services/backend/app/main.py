from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="爱视频 API", version="0.1.0")

    @app.get("/health/live", tags=["系统"])
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
