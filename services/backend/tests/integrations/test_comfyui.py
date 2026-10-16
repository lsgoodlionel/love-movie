import asyncio

import httpx
import pytest
from pydantic import SecretStr

from app.integrations.access_headers import AccessHeaders
from app.integrations.comfyui import ComfyUIAdapter
from app.integrations.errors import RemoteServiceError


def test_submit_parses_prompt_id_and_attaches_headers() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"prompt_id": "prompt-123", "number": 1})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://comfy.test")
    adapter = ComfyUIAdapter(
        "https://comfy.test",
        AccessHeaders(SecretStr("id"), SecretStr("secret")),
        client=client,
    )
    prompt_id = asyncio.run(adapter.submit({"1": {"class_type": "Demo"}}, "browser-client"))
    asyncio.run(client.aclose())

    assert prompt_id == "prompt-123"
    assert seen["cf-access-client-id"] == "id"
    assert seen["cf-access-client-secret"] == "secret"


def test_history_is_authoritative_after_websocket_failure() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={})
        return httpx.Response(
            200,
            json={"p-1": {"status": {"completed": True}, "outputs": {"9": {"images": [{"filename": "out.png", "type": "output"}]}}}},
        )

    async def broken_events(prompt_id: str):
        raise OSError("Cloudflare 1033 <html>secret</html>")
        yield  # pragma: no cover

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://comfy.test")
    adapter = ComfyUIAdapter(
        "https://comfy.test",
        AccessHeaders(SecretStr("id"), SecretStr("secret")),
        client=client,
        event_stream=broken_events,
        poll_interval=0,
        max_history_polls=3,
    )

    async def collect():
        return [event async for event in adapter.track("p-1")]

    events = asyncio.run(collect())
    asyncio.run(client.aclose())
    assert [event.kind for event in events] == ["progress", "progress", "completed"]
    assert events[-1].outputs["9"]["images"][0]["filename"] == "out.png"


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(302, headers={"location": "https://access.example/login"}), "REMOTE_AUTH_FAILED"),
        (httpx.Response(400, json={"error": {"type": "prompt_outputs_failed_validation", "message": "bad"}}), "WORKFLOW_VALIDATION_FAILED"),
        (httpx.Response(500, text="CUDA out of memory"), "REMOTE_OUT_OF_MEMORY"),
        (httpx.Response(524, text="<html>timeout secret</html>"), "REMOTE_TIMEOUT"),
        (httpx.Response(530, text="Cloudflare Tunnel error 1033"), "REMOTE_TUNNEL_UNAVAILABLE"),
    ],
)
def test_submit_normalizes_remote_failures(response: httpx.Response, code: str) -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response), base_url="https://comfy.test")
    adapter = ComfyUIAdapter("https://comfy.test", AccessHeaders.empty(), client=client)
    with pytest.raises(RemoteServiceError) as caught:
        asyncio.run(adapter.submit({}, "client"))
    asyncio.run(client.aclose())
    assert caught.value.code == code
    assert "html" not in str(caught.value).lower()


def test_cancel_pending_deletes_only_target_without_global_interrupt() -> None:
    calls: list[tuple[str, str]] = []
    queue_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal queue_calls
        calls.append((request.method, request.url.path))
        if request.url.path == "/queue" and request.method == "GET":
            queue_calls += 1
            pending = [[2, "prompt-pending", {}]] if queue_calls == 1 else []
            return httpx.Response(200, json={"queue_running": [[1, "other-running", {}]], "queue_pending": pending})
        if request.url.path == "/queue" and request.method == "POST":
            return httpx.Response(200, json={})
        if request.url.path.startswith("/history/"):
            return httpx.Response(200, json={})
        raise AssertionError(request.url.path)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://comfy.test")
    adapter = ComfyUIAdapter("https://comfy.test", AccessHeaders.empty(), client=client, poll_interval=0)
    asyncio.run(adapter.cancel("prompt-pending"))
    asyncio.run(client.aclose())

    assert ("POST", "/queue") in calls
    assert ("POST", "/interrupt") not in calls


def test_track_yields_heartbeat_during_tunnel_1033() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(530, text="Cloudflare 1033")),
        base_url="https://comfy.test",
    )
    adapter = ComfyUIAdapter(
        "https://comfy.test", AccessHeaders.empty(), client=client, poll_interval=0, max_history_polls=1
    )

    async def first_event():
        stream = adapter.track("prompt-1")
        event = await anext(stream)
        await stream.aclose()
        return event

    assert asyncio.run(first_event()).kind == "progress"
    asyncio.run(client.aclose())


def test_cancel_running_interrupts_only_after_queue_identification() -> None:
    calls: list[tuple[str, str]] = []
    queue_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal queue_calls
        calls.append((request.method, request.url.path))
        if request.url.path == "/queue":
            queue_calls += 1
            running = [[1, "prompt-running", {}]] if queue_calls == 1 else []
            return httpx.Response(200, json={"queue_running": running, "queue_pending": []})
        if request.url.path == "/interrupt":
            return httpx.Response(200, json={})
        if request.url.path.startswith("/history/"):
            return httpx.Response(200, json={})
        raise AssertionError(request.url.path)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://comfy.test")
    adapter = ComfyUIAdapter("https://comfy.test", AccessHeaders.empty(), client=client, poll_interval=0)
    asyncio.run(adapter.cancel("prompt-running"))
    asyncio.run(client.aclose())

    assert ("POST", "/interrupt") in calls
    assert ("POST", "/queue") not in calls


def test_submit_timeout_is_uncertain_not_safe_retry() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://comfy.test")
    adapter = ComfyUIAdapter("https://comfy.test", AccessHeaders.empty(), client=client)
    with pytest.raises(RemoteServiceError) as caught:
        asyncio.run(adapter.submit({}, "client"))
    asyncio.run(client.aclose())

    assert caught.value.code == "REMOTE_SUBMISSION_UNKNOWN"

