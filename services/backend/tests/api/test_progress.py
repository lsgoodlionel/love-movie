from tests.api.test_tasks import setup_app


def test_sse_reconnect_replays_only_events_after_last_id() -> None:
    app, client, task = setup_app("events@example.com")
    first = app.state.generation_repository.append_event(task.id, "queued", "已进入队列", 0)
    second = app.state.generation_repository.append_event(task.id, "running", "正在生成", 45)
    app.state.generation_repository.append_event(task.id, "completed", "生成完成", 100)

    response = client.get(
        f"/api/v1/tasks/{task.id}/events",
        headers={"Last-Event-ID": str(second.id)},
    )
    assert response.status_code == 200
    assert f"id: {first.id}" not in response.text
    assert f"id: {second.id}" not in response.text
    assert "event: completed" in response.text
    assert response.text.count("event:") == 1

