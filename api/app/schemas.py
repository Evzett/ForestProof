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
