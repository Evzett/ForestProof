"""Pydantic-схемы для тел запросов. Ответы в большинстве эндпоинтов — уже
готовые dict/JSONB из БД (раздел 6 целиком хранится в `calculations.result`
и отдаётся как есть), поэтому отдельные response-модели для них не заводим:
дублирование схемы расчёта здесь неизбежно разошлось бы с контрактом.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    набора — ровно одним из двух. Раньше проверка жила в обработчике и
    ловила только пустой запрос: запрос с обоими полями принимался, и
    геометрия молча побеждала идентификатор. Человек при этом считал,
    что считает участок набора.

    Порядок лет тоже проверяется здесь. Перевёрнутый период раньше
    доходил до расчёта и падал где-то внутри, где причина уже не
    складывается во внятный ответ.
    """

    geometry: dict | None = None
    aoi_id: str | None = None
    year_start: int = Field(ge=2019, le=2024)
    year_end: int = Field(ge=2019, le=2024)

    @model_validator(mode="after")
    def _one_source_and_forward_period(self) -> "CalcRequest":
        if (self.geometry is None) == (self.aoi_id is None):
            raise ValueError(
                "нужен ровно один источник контура: geometry или aoi_id"
            )
        if self.year_end <= self.year_start:
            raise ValueError(
                f"конец периода ({self.year_end}) должен быть позже начала ({self.year_start})"
            )
        return self


class SummaryRequest(BaseModel):
    """Факты для изложения. Считает их фронт из уже готового расчёта —
    сервер ничего не пересчитывает и ничего не добавляет."""

    facts: dict


class LoginRequest(BaseModel):
    """`POST /api/auth/login`. KAN-78.

    Пароль приходит один раз и дальше нигде не хранится: сервер сверяет
    его с хешем и забывает. В логи это поле не попадает.
    """

    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class SaveContourRequest(BaseModel):
    """`POST /api/contours`. KAN-78.

    Сохраняет загруженный пользователем контур вместе с уже посчитанным
    расчётом, чтобы к нему можно было вернуться: `calc_id` приходит от
    `POST /api/calc`, а не считается заново — иначе одно и то же получило
    бы два разных номера.
    """

    name: str = Field(min_length=1, max_length=255)
    source_name: str = Field(min_length=1, max_length=255)
    source_kind: str = Field(min_length=1, max_length=32)
    geometry: dict
    calc_id: str = Field(min_length=1, max_length=32)


class RegisterRequest(BaseModel):
    """`POST /api/auth/register`. KAN-78.

    Поля роли здесь нет намеренно: роль назначает сервер, и прислать её
    нельзя. Восемь символов пароля — не идеал, но нижняя граница, ниже
    которой подбор перестаёт быть работой.
    """

    login: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=256)


class ProfileRequest(BaseModel):
    """`PATCH /api/auth/me`. Своё имя и цвет аватара — и только они."""

    display_name: str | None = Field(default=None, max_length=255)
    avatar_color: str | None = Field(default=None, max_length=16)


class ChangePasswordRequest(BaseModel):
    """`POST /api/auth/password`. Текущий пароль обязателен: иначе
    украденного токена хватило бы, чтобы забрать учётную запись."""

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class AdminUserRequest(BaseModel):
    """`PATCH /api/admin/users/{login}`. Роль и блокировка.

    Пароля здесь нет: сброс чужого пароля — отдельное действие с
    отдельным следом, а не поле среди прочих.
    """

    role: str | None = Field(default=None, max_length=32)
    blocked: bool | None = None


class AdminPasswordRequest(BaseModel):
    """`POST /api/admin/users/{login}/password`. Новый пароль задаёт
    администратор и передаёт человеку сам."""

    new_password: str = Field(min_length=8, max_length=256)
