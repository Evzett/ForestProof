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
    # Кому разрешено обращаться к API из браузера. Раньше здесь стояла
    # звёздочка «на время хакатона»: любой сайт мог послать запрос от
    # имени открытой у человека вкладки. Список задаётся окружением, а в
    # разработке по умолчанию — наш же фронт.
    cors_origins: str = "http://localhost:5173,http://localhost"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # Языковая модель для краткой справки. Пустой ключ — штатное
    # состояние: сервис обязан работать без неё, показывая шаблонную
    # справку. Ключ держится только на сервере и во фронт не уезжает.
    routerai_base_url: str = "https://routerai.ru/api/v1"
    routerai_model: str = "deepseek/deepseek-v4-pro-0813"
    # Пустая строка в переменной окружения значит «не задано», а не
    # «модель без имени»: иначе запрос уходил бы с пустым полем model и
    # сервис модели отвечал бы 400 вместо текста.
    routerai_api_key: str = ""

    @property
    def routerai(self) -> tuple[str, str] | None:
        """Ключ и имя модели, если справку действительно есть чем излагать."""
        key = self.routerai_api_key.strip()
        model = self.routerai_model.strip()
        if not key or not model:
            return None
        return key, model

    @property
    def data_root(self) -> Path:
        """Абсолютный путь к `api/data/` — превью, полигоны, загрузки геометрии.
        NFR-01: всё, что отдаётся по этому пути, читается с диска, без сети."""
        return API_ROOT / self.data_dir


settings = Settings()
