from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError

from app.api.dependencies import CurrentPrincipal, get_identity_repository
from app.domain.generation.repository import GenerationRepository, IdempotencyConflict, QuotaExceeded
from app.domain.generation.schemas import CreateGenerationCommand, GenerationKind
from app.domain.identity.permissions import can_create_generation
from app.domain.identity.repository import IdentityRepository
from app.workflows.policies import ImageParameters, VideoParameters


router = APIRouter(prefix="/api/v1/generations", tags=["生成"])


class CreateImageRequest(BaseModel):
    project_id: UUID
    prompt: str = Field(min_length=1, max_length=4000)
    width: int = 768
    height: int = 1024
    steps: int = 8
    batch_size: int = 1
    seed: int = 0
    adult_content_declared: bool = False


class GenerationAccepted(BaseModel):
    task_id: UUID
    status: str


class CreateVideoRequest(BaseModel):
    project_id: UUID
    prompt: str = Field(min_length=1, max_length=4000)
    camera_pose: str = "Zoom In"
    camera_speed: float = 0.45
    seed: int = 0
    adult_content_declared: bool = False


def get_generation_repository(request: Request) -> GenerationRepository:
    return request.app.state.generation_repository


def get_dispatcher(request: Request) -> Any:
    dispatcher = request.app.state.generation_dispatcher
    if dispatcher is None:
        raise HTTPException(status_code=503, detail="生成队列尚未就绪")
    return dispatcher


async def _dispatch_if_needed(repository: GenerationRepository, dispatcher: Any, task: Any, created: bool) -> str:
    retryable = (task.status == "queued" and task.dispatch_confirmed_at is None) or (
        task.status == "needs_attention" and task.error_code == "DISPATCH_FAILED"
    )
    if not created and not retryable:
        return task.status
    repository.set_status(task.id, "queued", error_code=None)
    try:
        await dispatcher.enqueue_generation(task.id)
        repository.mark_dispatch_confirmed(task.id)
    except Exception as exc:
        repository.set_status(task.id, "needs_attention", error_code="DISPATCH_FAILED")
        raise HTTPException(status_code=503, detail="生成任务入队失败，可安全重试") from exc
    return "queued"


@router.post("/images", response_model=GenerationAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_image(
    payload: CreateImageRequest,
    principal: CurrentPrincipal,
    identity: Annotated[IdentityRepository, Depends(get_identity_repository)],
    repository: Annotated[GenerationRepository, Depends(get_generation_repository)],
    dispatcher: Annotated[Any, Depends(get_dispatcher)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=160)],
) -> GenerationAccepted:
    if not can_create_generation(principal.role):
        raise HTTPException(status_code=403, detail="当前角色无权创建生成任务")
    project, cross_tenant = identity.get_project(principal, payload.project_id)
    if cross_tenant or project is None:
        raise HTTPException(status_code=403 if cross_tenant else 404, detail="无权访问该项目" if cross_tenant else "项目不存在")
    if not can_create_generation(identity.project_role(principal, payload.project_id)):
        raise HTTPException(status_code=403, detail="当前项目角色无权创建生成任务")
    try:
        parameters = ImageParameters.model_validate(payload.model_dump(exclude={"project_id"}))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="图片参数不符合生成限制") from exc
    command = CreateGenerationCommand(
        tenant_id=principal.tenant_id,
        project_id=payload.project_id,
        created_by=principal.user_id,
        kind=GenerationKind.IMAGE,
        parameters=parameters.model_dump(),
        workflow_version="z_image_turbo:v1",
    )
    try:
        task, created = repository.create_or_get_task(
            command,
            idempotency_key,
            estimated_gpu_seconds=60,
            estimated_storage_bytes=50 * 1024**2,
        )
    except QuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    accepted_status = await _dispatch_if_needed(repository, dispatcher, task, created)
    return GenerationAccepted(task_id=task.id, status=accepted_status)


@router.post("/videos", response_model=GenerationAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_video(
    payload: CreateVideoRequest,
    principal: CurrentPrincipal,
    identity: Annotated[IdentityRepository, Depends(get_identity_repository)],
    repository: Annotated[GenerationRepository, Depends(get_generation_repository)],
    dispatcher: Annotated[Any, Depends(get_dispatcher)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=160)],
) -> GenerationAccepted:
    if not can_create_generation(principal.role):
        raise HTTPException(status_code=403, detail="当前角色无权创建生成任务")
    project, cross_tenant = identity.get_project(principal, payload.project_id)
    if cross_tenant or project is None:
        raise HTTPException(status_code=403 if cross_tenant else 404, detail="无权访问该项目" if cross_tenant else "项目不存在")
    if not can_create_generation(identity.project_role(principal, payload.project_id)):
        raise HTTPException(status_code=403, detail="当前项目角色无权创建生成任务")
    try:
        policy = VideoParameters(
            prompt=payload.prompt,
            camera_pose=payload.camera_pose,
            camera_speed=payload.camera_speed,
            seed=payload.seed,
            adult_content_declared=payload.adult_content_declared,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="视频参数不符合当前单镜头生成限制") from exc
    parameters = policy.model_dump()
    command = CreateGenerationCommand(
        tenant_id=principal.tenant_id,
        project_id=payload.project_id,
        created_by=principal.user_id,
        kind=GenerationKind.VIDEO,
        parameters=parameters,
        workflow_version="z_image_turbo:v1+wan_i2v:v1",
    )
    try:
        task, created = repository.create_or_get_task(
            command,
            idempotency_key,
            estimated_gpu_seconds=600,
            estimated_storage_bytes=500 * 1024**2,
        )
    except QuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    accepted_status = await _dispatch_if_needed(repository, dispatcher, task, created)
    return GenerationAccepted(task_id=task.id, status=accepted_status)
