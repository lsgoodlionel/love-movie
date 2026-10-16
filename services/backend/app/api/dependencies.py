from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status

from app.domain.identity.repository import IdentityRepository, Principal


def get_identity_repository(request: Request) -> IdentityRepository:
    return request.app.state.identity_repository


def get_current_principal(
    repository: Annotated[IdentityRepository, Depends(get_identity_repository)],
    session_token: Annotated[str | None, Cookie()] = None,
) -> Principal:
    principal = repository.principal_for_token(session_token)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
IdentityRepo = Annotated[IdentityRepository, Depends(get_identity_repository)]
