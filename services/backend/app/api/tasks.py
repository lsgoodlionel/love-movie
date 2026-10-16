from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.dependencies import CurrentPrincipal
from app.api.generations import get_generation_repository
from app.domain.generation.repository import GenerationRepository
from app.services.cancellation import CancellationService
from app.services.progress import encode_sse


router = APIRouter(prefix="/api/v1/tasks", tags=["任务"])


class TaskResponse(BaseModel):
    id: UUID
    project_id: UUID
    kind: str
    status: str
    current_step: str | None
    error_code: str | None


def _task_or_error(repository: GenerationRepository, tenant_id: UUID, task_id: UUID):
    task, forbidden = repository.get_scoped_task(tenant_id, task_id)
    if forbidden:
        raise HTTPException(status_code=403, detail="无权访问该生成任务")
    if task is None:
        raise HTTPException(status_code=404, detail="生成任务不存在")
    return task


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: UUID,
    principal: CurrentPrincipal,
    repository: Annotated[GenerationRepository, Depends(get_generation_repository)],
) -> TaskResponse:
    return TaskResponse.model_validate(
        _task_or_error(repository, principal.tenant_id, task_id), from_attributes=True
    )


@router.get("/{task_id}/events")
def task_events(
    task_id: UUID,
    principal: CurrentPrincipal,
    repository: Annotated[GenerationRepository, Depends(get_generation_repository)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> Response:
    _task_or_error(repository, principal.tenant_id, task_id)
    try:
        cursor = int(last_event_id or 0)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="事件游标格式错误") from exc
    body = encode_sse(repository.events_after(task_id, cursor))
    return Response(body, media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/{task_id}/cancel")
def cancel_task(
    task_id: UUID,
    principal: CurrentPrincipal,
    repository: Annotated[GenerationRepository, Depends(get_generation_repository)],
) -> dict[str, str]:
    _task_or_error(repository, principal.tenant_id, task_id)
    status, forbidden = CancellationService(repository).cancel(principal.tenant_id, task_id)
    if forbidden:
        raise HTTPException(status_code=403, detail="无权取消该生成任务")
    return {"status": status}
