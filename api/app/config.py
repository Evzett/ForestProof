from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень пакета api/ — `data/` живёт внутри него (не в корне репозитория),
# чтобы попадать в Docker-образ через `COPY . .` и в volume `.:/app` из
# docker-compose.yml без дополнительных монтирований. См. api/README.md.
API_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Настройки приложения. Значения берутся из переменных окружения
    (см. .env.example) — на Render DATABASE_URL подставляется автоматически
    из подключённой Postgres-базы (render.yaml, fromDatabase)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://forestproof:forestproof@db:5432/forestproof"
    environment: str = "development"
    data_dir: str = "data"

    @property
    def data_root(self) -> Path:
        """Абсолютный путь к `api/data/` — превью, полигоны, загрузки геометрии.
        NFR-01: всё, что отдаётся по этому пути, читается с диска, без сети."""
        return API_ROOT / self.data_dir


settings = Settings()
