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
            raise RemoteServiceError("REMOTE_SUBMISSION_UNKNOWN", "远程提交结果未确认，需要人工核对") from exc
        except httpx.HTTPError as exc:
            raise RemoteServiceError("REMOTE_SUBMISSION_UNKNOWN", "远程提交结果未确认，需要人工核对") from exc
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
                yield ProgressEvent("progress", progress=None)
                await asyncio.sleep(self._poll_interval)
                continue
            if self._is_tunnel_1033(response) or response.status_code >= 500:
                yield ProgressEvent("progress", progress=None)
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
            yield ProgressEvent("progress", progress=None)
            await asyncio.sleep(self._poll_interval)
        raise RemoteServiceError("REMOTE_SOFT_TIMEOUT", "等待生成结果超时")

    async def history(self, prompt_id: str) -> ProgressEvent | None:
        try:
            response = await self._client.get(f"/history/{prompt_id}", headers=self._access.as_dict())
        except httpx.HTTPError as exc:
            raise RemoteServiceError("REMOTE_UNAVAILABLE", "生成服务暂时不可用") from exc
        self._raise_for_response(response)
        try:
            item = response.json().get(prompt_id)
        except (ValueError, TypeError) as exc:
            raise RemoteServiceError("REMOTE_INVALID_RESPONSE", "生成历史返回格式不正确") from exc
        if item and item.get("status", {}).get("completed"):
            return ProgressEvent("completed", 1, item.get("outputs", {}))
        return ProgressEvent("progress", None) if item else None

    async def queue_contains(self, prompt_id: str) -> bool:
        try:
            response = await self._client.get("/queue", headers=self._access.as_dict())
        except httpx.HTTPError as exc:
            raise RemoteServiceError("REMOTE_UNAVAILABLE", "生成队列暂时不可用") from exc
        self._raise_for_response(response)
        try:
            payload = response.json()
            entries = [*payload.get("queue_running", []), *payload.get("queue_pending", [])]
            return any(prompt_id in entry for entry in entries if isinstance(entry, list))
        except (ValueError, TypeError) as exc:
            raise RemoteServiceError("REMOTE_INVALID_RESPONSE", "生成队列返回格式不正确") from exc

    async def cancel(self, prompt_id: str, *, confirmation_polls: int = 5) -> None:
        try:
            queue = await self._queue_payload()
            running = self._queue_has_prompt(queue.get("queue_running", []), prompt_id)
            pending = self._queue_has_prompt(queue.get("queue_pending", []), prompt_id)
            if pending:
                response = await self._client.post(
                    "/queue",
                    headers=self._access.as_dict(),
                    json={"delete": [prompt_id]},
                )
                self._raise_for_response(response)
            elif running:
                response = await self._client.post("/interrupt", headers=self._access.as_dict())
                self._raise_for_response(response)
            else:
                history = await self.history(prompt_id)
                if history and history.kind == "completed":
                    raise RemoteServiceError("REMOTE_ALREADY_COMPLETED", "远程任务已完成，需要恢复生成结果")
                return
            for _ in range(confirmation_polls):
                queue = await self._queue_payload()
                if not self._queue_has_prompt(
                    [*queue.get("queue_running", []), *queue.get("queue_pending", [])], prompt_id
                ):
                    history = await self.history(prompt_id)
                    if history and history.kind == "completed":
                        raise RemoteServiceError("REMOTE_ALREADY_COMPLETED", "远程任务已完成，需要恢复生成结果")
                    return
                await asyncio.sleep(self._poll_interval)
            raise RemoteServiceError("REMOTE_CANCEL_UNCONFIRMED", "远程任务取消尚未确认")
        except RemoteServiceError:
            raise
        except httpx.HTTPError as exc:
            raise RemoteServiceError("REMOTE_UNAVAILABLE", "远程任务取消失败") from exc

    async def _queue_payload(self) -> dict[str, Any]:
        response = await self._client.get("/queue", headers=self._access.as_dict())
        self._raise_for_response(response)
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError
            return payload
        except (ValueError, TypeError) as exc:
            raise RemoteServiceError("REMOTE_INVALID_RESPONSE", "生成队列返回格式不正确") from exc

    @staticmethod
    def _queue_has_prompt(entries: list[Any], prompt_id: str) -> bool:
        return any(prompt_id in entry for entry in entries if isinstance(entry, list))

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
        if ComfyUIAdapter._is_tunnel_1033(response):
            raise RemoteServiceError("REMOTE_TUNNEL_UNAVAILABLE", "远程服务隧道暂时不可用")
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

    @staticmethod
    def _is_tunnel_1033(response: httpx.Response) -> bool:
        return response.status_code in {530, 1033} and "1033" in response.text

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
