from typing import Annotated

from fastapi import APIRouter, Cookie, Response, status

from app.api.dependencies import CurrentPrincipal, IdentityRepo
from app.domain.identity.schemas import CurrentUser, LoginRequest


router = APIRouter(prefix="/api/v1/auth", tags=["账号"])


@router.post("/login", response_model=CurrentUser)
def login(payload: LoginRequest, response: Response, repository: IdentityRepo) -> CurrentUser:
    principal = repository.authenticate(payload.email, payload.password)
    if principal is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    token = repository.create_session(principal)
    response.set_cookie(
        "session_token",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=12 * 60 * 60,
        path="/",
    )
    return CurrentUser(id=principal.user_id, tenant_id=principal.tenant_id, email=principal.email, role=principal.role)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    repository: IdentityRepo,
    session_token: Annotated[str | None, Cookie()] = None,
) -> Response:
    repository.revoke_session(session_token)
    response.delete_cookie("session_token", path="/", secure=True, httponly=True, samesite="lax")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=CurrentUser)
def me(principal: CurrentPrincipal) -> CurrentUser:
    return CurrentUser(id=principal.user_id, tenant_id=principal.tenant_id, email=principal.email, role=principal.role)
