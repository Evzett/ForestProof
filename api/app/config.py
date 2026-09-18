from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения. Значения берутся из переменных окружения
    (см. .env.example) — на Render DATABASE_URL подставляется автоматически
    из подключённой Postgres-базы (render.yaml, fromDatabase)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://forestproof:forestproof@db:5432/forestproof"
    environment: str = "development"


settings = Settings()
