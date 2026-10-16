from tests.api.test_tasks import setup_app


def test_queued_cancel_is_terminal_and_running_cancel_records_intent() -> None:
    app, client, queued = setup_app("cancel@example.com")
    app.state.generation_repository.set_status(queued.id, "queued")
    response = client.post(f"/api/v1/tasks/{queued.id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    app.state.generation_repository.set_status(queued.id, "running")
    response = client.post(f"/api/v1/tasks/{queued.id}/cancel")
    assert response.json()["status"] == "cancelling"
    assert app.state.generation_repository.get_task(queued.id).cancellation_requested_at is not None

