import asyncio
import json
from dataclasses import dataclass
from time import monotonic

import httpx

from app.integrations.access_headers import AccessHeaders
from app.integrations.errors import RemoteServiceError


@dataclass(frozen=True)
class PlannedPrompts:
    image_prompt: str
    motion_prompt: str
    negative_prompt: str = ""
    title: str = ""

    @property
    def video_prompt(self) -> str:
        return self.motion_prompt


class OllamaAdapter:
    def __init__(
        self,
        base_url: str,
        access: AccessHeaders,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._access = access
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=access.as_dict(),
            timeout=httpx.Timeout(120, connect=10),
        )

    async def plan_video_text(self, request: str, *, model: str) -> PlannedPrompts:
        prompt = (
            "将下列中文创意整理成图片首帧提示词和图生视频动态提示词。"
            "只返回 JSON，字段为 image_prompt 和 video_prompt：\n" + request
        )
        try:
            response = await self._client.post(
                "/api/generate",
                headers=self._access.as_dict(),
                json={"model": model, "prompt": prompt, "stream": False, "format": "json", "keep_alive": "0s"},
            )
        except httpx.TimeoutException as exc:
            raise RemoteServiceError("REMOTE_TIMEOUT", "远程文本模型响应超时") from exc
        except httpx.HTTPError as exc:
            raise RemoteServiceError("REMOTE_UNAVAILABLE", "远程文本模型暂时不可用") from exc
        if response.status_code in {401, 403} or 300 <= response.status_code < 400:
            raise RemoteServiceError("REMOTE_AUTH_FAILED", "远程服务认证失败")
        if response.status_code >= 500:
            raise RemoteServiceError("REMOTE_UNAVAILABLE", "远程文本模型暂时不可用")
        if response.status_code >= 400:
            raise RemoteServiceError("REMOTE_INVALID_REQUEST", "远程文本模型拒绝了请求")
        try:
            body = response.json()
            planned = json.loads(body["response"])
            motion_prompt = planned.get("motion_prompt", planned.get("video_prompt"))
            return PlannedPrompts(
                image_prompt=str(planned["image_prompt"]),
                motion_prompt=str(motion_prompt),
                negative_prompt=str(planned.get("negative_prompt", "")),
                title=str(planned.get("title", "")),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise RemoteServiceError("REMOTE_INVALID_RESPONSE", "远程文本模型返回格式不正确") from exc

    async def wait_until_unloaded(self, timeout: float = 30) -> None:
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            try:
                response = await self._client.get("/api/ps", headers=self._access.as_dict())
                models = response.json().get("models", [])
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                raise RemoteServiceError("REMOTE_INVALID_RESPONSE", "无法确认文本模型显存释放状态") from exc
            if not models:
                return
            await asyncio.sleep(0.25)
        raise RemoteServiceError("REMOTE_SOFT_TIMEOUT", "等待文本模型释放显存超时")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
