from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import CurrentPrincipal
from app.domain.ai_resources.repository import AIResourceRepository
from app.domain.ai_resources.schemas import ModelRouteConfig, ModelRouteUpdate
from app.domain.identity.schemas import Role


router = APIRouter(prefix="/api/v1/admin/ai-resources", tags=["AI 资源管理"])


class ModelRouteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    capability: str
    quality: str
    model: str
    priority: int
    enabled: bool


def get_repository(request: Request) -> AIResourceRepository:
    return request.app.state.ai_resource_repository


def require_admin(principal: CurrentPrincipal) -> None:
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise HTTPException(status_code=403, detail="仅所有者或管理员可配置 AI 资源")


@router.get("/model-routes", response_model=list[ModelRouteResponse])
def list_model_routes(
    principal: CurrentPrincipal,
    repository: Annotated[AIResourceRepository, Depends(get_repository)],
) -> list[ModelRouteResponse]:
    require_admin(principal)
    return [ModelRouteResponse.model_validate(item) for item in repository.list_model_routes(principal.tenant_id)]


@router.post("/model-routes", response_model=ModelRouteResponse, status_code=status.HTTP_201_CREATED)
def create_model_route(
    payload: ModelRouteConfig,
    principal: CurrentPrincipal,
    repository: Annotated[AIResourceRepository, Depends(get_repository)],
) -> ModelRouteResponse:
    require_admin(principal)
    return ModelRouteResponse.model_validate(repository.create_model_route(principal.tenant_id, payload.model_dump()))


@router.patch("/model-routes/{route_id}", response_model=ModelRouteResponse)
def update_model_route(
    route_id: UUID,
    payload: ModelRouteUpdate,
    principal: CurrentPrincipal,
    repository: Annotated[AIResourceRepository, Depends(get_repository)],
) -> ModelRouteResponse:
    require_admin(principal)
    route = repository.update_model_route(principal.tenant_id, route_id, payload.model_dump(exclude_none=True))
    if route is None:
        raise HTTPException(status_code=404, detail="模型路由不存在")
    return ModelRouteResponse.model_validate(route)
