import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.integrations.access_headers import AccessHeaders
from app.integrations.errors import RemoteServiceError


@dataclass(frozen=True)
class ProgressEvent:
    kind: str
    progress: float | None = None
    outputs: dict[str, Any] = field(default_factory=dict)


EventStream = Callable[[str], AsyncIterator[ProgressEvent]]


class ComfyUIAdapter:
    def __init__(
        self,
        base_url: str,
        access: AccessHeaders,
        *,
        client: httpx.AsyncClient | None = None,
        event_stream: EventStream | None = None,
        poll_interval: float = 1,
        max_history_polls: int = 900,
    ) -> None:
        self._access = access
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=access.as_dict(),
            timeout=httpx.Timeout(120, connect=10),
        )
        self._event_stream = event_stream
        self._poll_interval = poll_interval
        self._max_history_polls = max_history_polls

    async def submit(self, workflow: dict[str, Any], client_id: str) -> str:
        try:
            response = await self._client.post(
                "/prompt",
                headers=self._access.as_dict(),
                json={"prompt": workflow, "client_id": client_id},
            )
        except httpx.TimeoutException as exc:
            raise RemoteServiceError("REMOTE_TIMEOUT", "生成服务响应超时") from exc
        except httpx.HTTPError as exc:
            raise RemoteServiceError("REMOTE_UNAVAILABLE", "生成服务暂时不可用") from exc
        self._raise_for_response(response)
        try:
            return str(response.json()["prompt_id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise RemoteServiceError("REMOTE_INVALID_RESPONSE", "生成服务返回格式不正确") from exc

    async def track(self, prompt_id: str) -> AsyncIterator[ProgressEvent]:
        if self._event_stream is not None:
            try:
                async for event in self._event_stream(prompt_id):
                    yield event
            except (OSError, httpx.HTTPError):
                yield ProgressEvent("progress", progress=None)

        for _ in range(self._max_history_polls):
            try:
                response = await self._client.get(
                    f"/history/{prompt_id}", headers=self._access.as_dict()
                )
            except httpx.HTTPError:
                await asyncio.sleep(self._poll_interval)
                continue
            if response.status_code == 1033 or response.status_code >= 500:
                await asyncio.sleep(self._poll_interval)
                continue
            self._raise_for_response(response)
            try:
                item = response.json().get(prompt_id)
            except (ValueError, TypeError) as exc:
                raise RemoteServiceError("REMOTE_INVALID_RESPONSE", "生成历史返回格式不正确") from exc
            if item and item.get("status", {}).get("completed"):
                yield ProgressEvent("completed", progress=1, outputs=item.get("outputs", {}))
                return
            await asyncio.sleep(self._poll_interval)
        raise RemoteServiceError("REMOTE_SOFT_TIMEOUT", "等待生成结果超时")

    async def download_output(self, output: dict[str, str]) -> AsyncIterator[bytes]:
        params = {key: output[key] for key in ("filename", "subfolder", "type") if output.get(key)}
        try:
            async with self._client.stream(
                "GET", "/view", params=params, headers=self._access.as_dict()
            ) as response:
                self._raise_for_response(response)
                async for chunk in response.aiter_bytes():
                    yield chunk
        except httpx.TimeoutException as exc:
            raise RemoteServiceError("REMOTE_TIMEOUT", "下载生成结果超时") from exc
        except httpx.HTTPError as exc:
            raise RemoteServiceError("DOWNLOAD_INTERRUPTED", "生成结果下载中断") from exc

    async def upload_image(self, name: str, content: bytes, *, overwrite: bool = False) -> str:
        try:
            response = await self._client.post(
                "/upload/image",
                headers=self._access.as_dict(),
                data={"type": "input", "overwrite": str(overwrite).lower()},
                files={"image": (name, content, "image/png")},
            )
        except httpx.TimeoutException as exc:
            raise RemoteServiceError("REMOTE_TIMEOUT", "首帧上传超时") from exc
        except httpx.HTTPError as exc:
            raise RemoteServiceError("REMOTE_UNAVAILABLE", "首帧上传失败") from exc
        self._raise_for_response(response)
        try:
            result = response.json()
            uploaded_name = str(result["name"])
            subfolder = str(result.get("subfolder", "")).strip("/")
            return f"{subfolder}/{uploaded_name}" if subfolder else uploaded_name
        except (ValueError, KeyError, TypeError) as exc:
            raise RemoteServiceError("REMOTE_INVALID_RESPONSE", "首帧上传响应格式不正确") from exc

    @staticmethod
    def _raise_for_response(response: httpx.Response) -> None:
        text = response.text.lower()
        if response.status_code in {401, 403} or 300 <= response.status_code < 400:
            raise RemoteServiceError("REMOTE_AUTH_FAILED", "远程服务认证失败")
        if response.status_code in {408, 504, 524}:
            raise RemoteServiceError("REMOTE_TIMEOUT", "远程服务响应超时")
        if "out of memory" in text or "cuda oom" in text:
            raise RemoteServiceError("REMOTE_OUT_OF_MEMORY", "远程 GPU 显存不足")
        if response.status_code == 400 and "validation" in text:
            raise RemoteServiceError("WORKFLOW_VALIDATION_FAILED", "工作流参数校验失败")
        if response.status_code >= 500:
            raise RemoteServiceError("REMOTE_UNAVAILABLE", "远程生成服务暂时不可用")
        if response.status_code >= 400:
            raise RemoteServiceError("REMOTE_INVALID_REQUEST", "远程生成服务拒绝了请求")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
