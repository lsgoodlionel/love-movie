from typing import Any

import boto3
import httpx
import redis.asyncio as redis_async
from botocore.client import Config
from sqlalchemy import Engine, text

from app.core.config import Settings
from app.integrations.access_headers import AccessHeaders

from fastapi import APIRouter, HTTPException, Request

from app.api.dependencies import CurrentPrincipal
from app.domain.identity.schemas import Role


router = APIRouter(prefix="/api/v1/admin", tags=["管理诊断"])


class DefaultHealthProbe:
    async def snapshot(self) -> dict[str, Any]:
        return {
            "postgresql": "unknown",
            "redis": "unknown",
            "minio": "unknown",
            "worker": "unknown",
            "ollama": "unknown",
            "comfyui": "unknown",
            "queue_length": None,
            "current_lease_task_id": None,
        }


class OperationalHealthProbe:
    def __init__(self, settings: Settings, engine: Engine) -> None:
        self._settings = settings
        self._engine = engine

    async def snapshot(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "postgresql": "unhealthy",
            "redis": "unhealthy",
            "minio": "unhealthy",
            "worker": "unknown",
            "ollama": "unhealthy",
            "comfyui": "unhealthy",
            "queue_length": None,
            "current_lease_task_id": None,
        }
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            result["postgresql"] = "healthy"
        except Exception:
            pass

        redis = redis_async.from_url(self._settings.redis_url, decode_responses=True)
        try:
            await redis.ping()
            result["redis"] = "healthy"
            result["queue_length"] = await redis.zcard("arq:queue")
            lease_owner = await redis.get("love-movie:gpu:lease")
            result["current_lease_task_id"] = lease_owner.split(":", 1)[0] if lease_owner else None
            result["worker"] = "healthy" if await redis.get("arq:queue:health-check") else "unknown"
        except Exception:
            pass
        finally:
            await redis.aclose()

        try:
            s3 = boto3.client(
                "s3",
                endpoint_url=self._settings.object_storage_endpoint,
                aws_access_key_id=self._settings.object_storage_access_key,
                aws_secret_access_key=self._settings.object_storage_secret_key.get_secret_value(),
                region_name="us-east-1",
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            )
            s3.head_bucket(Bucket=self._settings.object_storage_bucket)
            result["minio"] = "healthy"
        except Exception:
            pass

        access = AccessHeaders(
            self._settings.cf_access_client_id,
            self._settings.cf_access_client_secret,
        )
        async with httpx.AsyncClient(headers=access.as_dict(), timeout=10) as client:
            for key, base_url, path in (
                ("ollama", self._settings.ollama_base_url, "/api/tags"),
                ("comfyui", self._settings.comfyui_base_url, "/system_stats"),
            ):
                try:
                    response = await client.get(base_url.rstrip("/") + path)
                    result[key] = "healthy" if response.status_code == 200 else "unhealthy"
                except httpx.HTTPError:
                    pass
        return result


@router.get("/health")
async def admin_health(principal: CurrentPrincipal, request: Request) -> dict[str, Any]:
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise HTTPException(status_code=403, detail="仅所有者或管理员可查看系统诊断")
    return await request.app.state.health_probe.snapshot()
