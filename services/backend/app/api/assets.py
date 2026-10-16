from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.dependencies import CurrentPrincipal, get_identity_repository
from app.api.generations import get_generation_repository
from app.domain.generation.repository import GenerationRepository
from app.domain.identity.repository import IdentityRepository


router = APIRouter(prefix="/api/v1/assets", tags=["素材"])


class AssetResponse(BaseModel):
    id: UUID
    project_id: UUID
    generation_task_id: UUID
    parent_asset_id: UUID | None
    kind: str
    content_type: str
    size_bytes: int


def get_storage(request: Request) -> Any:
    if request.app.state.storage is None:
        raise HTTPException(status_code=503, detail="素材存储尚未就绪")
    return request.app.state.storage


@router.get("", response_model=list[AssetResponse])
def list_assets(
    principal: CurrentPrincipal,
    repository: Annotated[GenerationRepository, Depends(get_generation_repository)],
    identity: Annotated[IdentityRepository, Depends(get_identity_repository)],
    project_id: UUID | None = Query(default=None),
) -> list[AssetResponse]:
    accessible_ids = {project.id for project in identity.list_projects(principal)}
    if project_id is not None and project_id not in accessible_ids:
        raise HTTPException(status_code=403, detail="无权访问该项目素材")
    return [
        AssetResponse.model_validate(item, from_attributes=True)
        for item in repository.list_assets(principal.tenant_id, project_id, accessible_project_ids=accessible_ids)
    ]


@router.post("/{asset_id}/access")
def access_asset(
    asset_id: UUID,
    principal: CurrentPrincipal,
    repository: Annotated[GenerationRepository, Depends(get_generation_repository)],
    identity: Annotated[IdentityRepository, Depends(get_identity_repository)],
    storage: Annotated[Any, Depends(get_storage)],
) -> dict[str, str | int]:
    asset, forbidden = repository.get_scoped_asset(principal.tenant_id, asset_id)
    if forbidden:
        raise HTTPException(status_code=403, detail="无权访问该素材")
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    project, project_forbidden = identity.get_project(principal, asset.project_id)
    if project_forbidden or project is None:
        raise HTTPException(status_code=403, detail="无权访问该素材")
    return {"url": storage.presign_get(asset.object_key, ttl_seconds=300), "expires_in": 300}
