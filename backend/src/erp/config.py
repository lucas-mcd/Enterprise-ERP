from functools import lru_cache
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+asyncpg://erp:erp@localhost:5432/erp"
    redis_url: str = "redis://localhost:6379/0"
    broker_url: str = "redis://localhost:6379/1"
    jwt_secret: SecretStr  # Required; never provide a production default.
    report_directory: str = "/home/erp/reports"
    jwt_issuer: str = "enterprise-erp"
    jwt_audience: str = "enterprise-erp-spa"
    refresh_token_seconds: int = Field(default=604800, ge=3600, le=2592000)
    refresh_cookie_secure: bool = True
    public_origin: str = "http://localhost:8080"
    access_token_seconds: int = Field(default=900, ge=60, le=3600)


@lru_cache
def settings() -> Settings:
    return Settings()
