import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.integrations.access_headers import AccessHeaders
from app.integrations.errors import RemoteServiceError
from app.integrations.ollama import OllamaAdapter


def test_plan_text_attaches_access_headers_and_unloads_model() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"response": json.dumps({"image_prompt": "电影感山谷", "video_prompt": "镜头缓慢推进"})},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://ollama.test")
    adapter = OllamaAdapter(
        "https://ollama.test",
        AccessHeaders(SecretStr("client-id"), SecretStr("top-secret")),
        client=client,
    )
    planned = asyncio.run(adapter.plan_video_text("山谷中的清晨", model="qwen3.5:4b"))
    asyncio.run(client.aclose())

    assert planned.image_prompt == "电影感山谷"
    assert planned.video_prompt == "镜头缓慢推进"
    assert seen["body"]["keep_alive"] == "0s"  # type: ignore[index]
    assert seen["headers"]["cf-access-client-id"] == "client-id"  # type: ignore[index]
    assert seen["headers"]["cf-access-client-secret"] == "top-secret"  # type: ignore[index]


@pytest.mark.parametrize("status", [401, 403])
def test_access_failures_are_stable_and_redacted(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="<html>top-secret internal gateway</html>")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://ollama.test")
    adapter = OllamaAdapter(
        "https://ollama.test",
        AccessHeaders(SecretStr("client-id"), SecretStr("top-secret")),
        client=client,
    )
    with pytest.raises(RemoteServiceError) as caught:
        asyncio.run(adapter.plan_video_text("测试", model="qwen3.5:4b"))
    asyncio.run(client.aclose())

    assert caught.value.code == "REMOTE_AUTH_FAILED"
    assert "top-secret" not in str(caught.value)
    assert "html" not in str(caught.value).lower()

