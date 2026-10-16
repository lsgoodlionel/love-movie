from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import create_session_token, hash_password, hash_session_token, verify_password
from app.domain.identity.models import AuthSession, Base, Membership, Project, ProjectMember, Tenant, User
from app.domain.identity.schemas import Role


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    tenant_id: UUID
    email: str
    role: Role


class IdentityRepository:
    def __init__(self, engine: Engine, *, create_schema: bool = False) -> None:
        if create_schema:
            Base.metadata.create_all(engine)
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def create_tenant_with_user(
        self,
        *,
        tenant_name: str,
        email: str,
        password: str,
        role: str,
        is_active: bool = True,
    ) -> tuple[Tenant, User]:
        with self._sessions.begin() as db:
            tenant = Tenant(name=tenant_name)
            user = User(email=email.casefold(), password_hash=hash_password(password), is_active=is_active)
            db.add_all([tenant, user])
            db.flush()
            db.add(Membership(tenant_id=tenant.id, user_id=user.id, role=Role(role).value))
            return tenant, user

    def create_user_in_tenant(
        self,
        *,
        tenant_id: UUID,
        email: str,
        password: str,
        role: str,
        is_active: bool = True,
    ) -> User:
        with self._sessions.begin() as db:
            user = User(email=email.casefold(), password_hash=hash_password(password), is_active=is_active)
            db.add(user)
            db.flush()
            db.add(Membership(tenant_id=tenant_id, user_id=user.id, role=Role(role).value))
            return user

    def authenticate(self, email: str, password: str) -> Principal | None:
        with self._sessions() as db:
            row = db.execute(
                select(User, Membership).join(Membership, Membership.user_id == User.id).where(User.email == email.casefold())
            ).first()
            if row is None:
                return None
            user, membership = row
            if not user.is_active or not verify_password(user.password_hash, password):
                return None
            return Principal(user.id, membership.tenant_id, user.email, Role(membership.role))

    def create_session(self, principal: Principal, *, lifetime: timedelta = timedelta(hours=12)) -> str:
        token = create_session_token()
        with self._sessions.begin() as db:
            db.add(
                AuthSession(
                    user_id=principal.user_id,
                    token_hash=hash_session_token(token),
                    expires_at=datetime.now(timezone.utc) + lifetime,
                )
            )
        return token

    def principal_for_token(self, token: str | None) -> Principal | None:
        if not token:
            return None
        now = datetime.now(timezone.utc)
        with self._sessions() as db:
            row = db.execute(
                select(User, Membership, AuthSession)
                .join(Membership, Membership.user_id == User.id)
                .join(AuthSession, AuthSession.user_id == User.id)
                .where(AuthSession.token_hash == hash_session_token(token))
            ).first()
            if row is None:
                return None
            user, membership, auth_session = row
            expires_at = auth_session.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if auth_session.revoked_at is not None or expires_at <= now or not user.is_active:
                return None
            return Principal(user.id, membership.tenant_id, user.email, Role(membership.role))

    def revoke_session(self, token: str | None) -> None:
        if not token:
            return
        with self._sessions.begin() as db:
            session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_session_token(token)))
            if session is not None:
                session.revoked_at = datetime.now(timezone.utc)

    def create_project(self, principal: Principal, name: str) -> Project:
        with self._sessions.begin() as db:
            project = Project(tenant_id=principal.tenant_id, name=name.strip(), created_by=principal.user_id)
            db.add(project)
            db.flush()
            db.add(ProjectMember(project_id=project.id, user_id=principal.user_id, role=principal.role.value))
            return project

    def list_projects(self, principal: Principal) -> list[Project]:
        with self._sessions() as db:
            query = select(Project).where(Project.tenant_id == principal.tenant_id)
            if principal.role not in {Role.OWNER, Role.ADMIN}:
                query = query.join(ProjectMember).where(ProjectMember.user_id == principal.user_id)
            return list(db.scalars(query.order_by(Project.created_at.desc())))

    def get_project(self, principal: Principal, project_id: UUID) -> tuple[Project | None, bool]:
        with self._sessions() as db:
            project = db.get(Project, project_id)
            if project is None:
                return None, False
            if project.tenant_id != principal.tenant_id:
                return None, True
            if principal.role not in {Role.OWNER, Role.ADMIN}:
                membership = db.scalar(
                    select(ProjectMember).where(
                        ProjectMember.project_id == project_id,
                        ProjectMember.user_id == principal.user_id,
                    )
                )
                if membership is None:
                    return None, True
            return project, False
