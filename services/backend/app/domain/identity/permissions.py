from collections.abc import Collection

from app.domain.identity.schemas import Role


class PermissionDenied(Exception):
    pass


def can_create_generation(role: Role | None) -> bool:
    return role in {Role.OWNER, Role.ADMIN, Role.CREATOR}


def require_project_role(role: Role, allowed_roles: Collection[Role]) -> None:
    if role not in allowed_roles:
        raise PermissionDenied("无权执行此操作")
