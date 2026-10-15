from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables (e.g. on Render) take precedence over backend/.env.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://coachai:coachai@localhost:5432/coachai"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days, convenient for a demo
    cors_origins: list[str] = ["*"]

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, url: str) -> str:
        # Hosted Postgres providers (Neon, Render, Heroku) hand out postgres:// or
        # postgresql:// URLs; SQLAlchemy 2.0 needs an explicit driver.
        if url.startswith("postgres://"):
            return "postgresql+psycopg2://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            return "postgresql+psycopg2://" + url[len("postgresql://"):]
        return url


settings = Settings()
