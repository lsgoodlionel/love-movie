from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import CurrentPrincipal, IdentityRepo
from app.domain.identity.permissions import PermissionDenied, require_project_role
from app.domain.identity.schemas import ProjectCreate, ProjectView, Role


router = APIRouter(prefix="/api/v1/projects", tags=["项目"])


@router.post("", response_model=ProjectView, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, principal: CurrentPrincipal, repository: IdentityRepo) -> ProjectView:
    try:
        require_project_role(principal.role, {Role.OWNER, Role.ADMIN, Role.CREATOR})
    except PermissionDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    project = repository.create_project(principal, payload.name)
    return ProjectView.model_validate(project)


@router.get("", response_model=list[ProjectView])
def list_projects(principal: CurrentPrincipal, repository: IdentityRepo) -> list[ProjectView]:
    return [ProjectView.model_validate(project) for project in repository.list_projects(principal)]


@router.get("/{project_id}", response_model=ProjectView)
def get_project(project_id: UUID, principal: CurrentPrincipal, repository: IdentityRepo) -> ProjectView:
    project, foreign_tenant = repository.get_project(principal, project_id)
    if foreign_tenant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目")
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return ProjectView.model_validate(project)
