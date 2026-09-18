"""Pydantic-схемы для тел запросов. Ответы в большинстве эндпоинтов — уже
готовые dict/JSONB из БД (раздел 6 целиком хранится в `calculations.result`
и отдаётся как есть), поэтому отдельные response-модели для них не заводим:
дублирование схемы расчёта здесь неизбежно разошлось бы с контрактом.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ScenarioRequest(BaseModel):
    """Раздел 7, `POST /api/projects/{project_id}/scenario`."""

    expected_effect_co2_t_year: float = Field(ge=0)
    effect_source: Literal["project_reported", "user_defined"]
    price_rub_per_unit: float = Field(ge=0)
    price_scenario: Literal["pessimistic", "base", "optimistic"] | None = None
    haircut_pct: float = Field(ge=0, le=100)
    capex_rub: float | None = Field(default=None, ge=0)
    opex_rub_year: float | None = Field(default=None, ge=0)
    project_lifetime_years: int | None = Field(default=None, ge=1)
    discount_rate: float = Field(ge=0, le=1)


class PlotCreateRequest(BaseModel):
    """Раздел 12, `POST /api/plots`. `boundary_source` обязателен (FR-21)."""

    upload_token: str
    name: str = Field(min_length=1)
    boundary_source: str = Field(min_length=1)
    link_project_id: str | None = None


class WatchlistAddRequest(BaseModel):
    """Раздел 12, `POST /api/watchlist`."""

    project_id: str


class CalcRequest(BaseModel):
    """`POST /api/calc` — расчёт по контуру и периоду (документ 06, раздел 6.1).

    Контур задаётся либо геометрией GeoJSON, либо идентификатором участка
    набора. Диапазон лет проверяется в case_service, а не здесь: там же
    лежит и причина отказа, которую увидит пользователь.
    """

    geometry: dict | None = None
    aoi_id: str | None = None
    year_start: int = Field(ge=2019, le=2024)
    year_end: int = Field(ge=2019, le=2024)


class SummaryRequest(BaseModel):
    """Факты для изложения. Считает их фронт из уже готового расчёта —
    сервер ничего не пересчитывает и ничего не добавляет."""

    facts: dict
