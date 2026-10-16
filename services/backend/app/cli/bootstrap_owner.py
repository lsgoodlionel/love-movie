import os

from sqlalchemy import create_engine

from app.core.config import get_settings
from app.domain.identity.repository import IdentityRepository


def main() -> None:
    email = os.environ["BOOTSTRAP_OWNER_EMAIL"]
    password = os.environ["BOOTSTRAP_OWNER_PASSWORD"]
    tenant_name = os.environ.get("BOOTSTRAP_TENANT_NAME", "爱视频工作室")
    repository = IdentityRepository(create_engine(get_settings().database_url))
    repository.create_tenant_with_user(
        tenant_name=tenant_name,
        email=email,
        password=password,
        role="owner",
    )
    print("初始所有者已创建")


if __name__ == "__main__":
    main()
