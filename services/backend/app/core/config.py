from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_secret_key: SecretStr = SecretStr("local-development-only")
    database_url: str = "postgresql+psycopg://love_movie:love_movie@postgres:5432/love_movie"
    redis_url: str = "redis://redis:6379/0"
    object_storage_endpoint: str = "http://minio:9000"
    object_storage_public_endpoint: str = "http://localhost:9000"
    object_storage_access_key: str = "love-movie-local"
    object_storage_secret_key: SecretStr = SecretStr("local-development-only")
    object_storage_bucket: str = "love-movie-assets"
    ollama_base_url: str = "https://openclaw.lsgood.cn"
    comfyui_base_url: str = "https://comfyui.lsgood.cn"
    cf_access_client_id: SecretStr = SecretStr("")
    cf_access_client_secret: SecretStr = SecretStr("")


@lru_cache
def get_settings() -> Settings:
    return Settings()
