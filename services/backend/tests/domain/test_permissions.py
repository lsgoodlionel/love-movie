import pytest

from app.domain.identity.permissions import PermissionDenied, can_create_generation, require_project_role
from app.domain.identity.schemas import Role


def test_reviewer_cannot_create_generation_but_creator_can() -> None:
    assert can_create_generation(Role.CREATOR) is True
    assert can_create_generation(Role.REVIEWER) is False


def test_require_project_role_rejects_role_outside_allowlist() -> None:
    with pytest.raises(PermissionDenied):
        require_project_role(Role.REVIEWER, {Role.OWNER, Role.ADMIN, Role.CREATOR})
