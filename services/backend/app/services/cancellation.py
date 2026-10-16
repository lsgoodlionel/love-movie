from typing import Any
from uuid import UUID


class CancellationService:
    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def cancel(self, tenant_id: UUID, task_id: UUID) -> tuple[str, bool]:
        return self._repository.request_cancellation(tenant_id, task_id)
