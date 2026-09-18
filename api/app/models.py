"""Схема БД ForestProof.

Источник истины по именам полей и допустимым значениям —
docs/04-kontrakty-dannyh.md. Расхождение с контрактом — баг.

Таблицы:
    projects            — проекты (раздел 2 контракта)
    project_registry    — метаданные реестра, 1:1 с projects, только при mode=with_project
    project_claims      — заявленные показатели, 1:1 с projects, только при mode=with_project
    observations        — наблюдения по годам (раздел 1)
    disturbance_events  — события нарушений (раздел 1)
    calculations        — расчёты, с аудит-полями (раздел 6 и 8) — ядро воспроизводимости
"""

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# --- Перечисления допустимых значений (раздел 0, 1, 2, 6 контракта) ---
# native_enum=False — чтобы Alembic не возился с CREATE TYPE в Postgres
# и добавление нового значения не требовало отдельной миграции типа.


class ProjectMode(str, enum.Enum):
    with_project = "with_project"
    territory_only = "territory_only"


class AreaKind(str, enum.Enum):
    forest_cover = "forest_cover"
    project_territory = "project_territory"


class EffectKind(str, enum.Enum):
    removals = "removals"
    avoided_emissions = "avoided_emissions"


class ClaimsSource(str, enum.Enum):
    registry_xlsx = "registry_xlsx"
    manual = "manual"


class EventType(str, enum.Enum):
    fire_supported = "fire_supported"
    non_fire = "non_fire"
    vegetation_stress = "vegetation_stress"
    unknown = "unknown"


class Confidence(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


def _enum(python_enum: type[enum.Enum]):
    return Enum(python_enum, values_callable=lambda e: [m.value for m in e], native_enum=False)


class Project(Base):
    """Раздел 2. Один проект — один полигон, один комплект метаданных."""

    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    region: Mapped[str | None] = mapped_column(String(255))
    mode: Mapped[ProjectMode] = mapped_column(_enum(ProjectMode))
    geometry_path: Mapped[str] = mapped_column(String(512))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    registry: Mapped["ProjectRegistry | None"] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    claims: Mapped["ProjectClaims | None"] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    observations: Mapped[list["Observation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Observation.year"
    )
    disturbance_events: Mapped[list["DisturbanceEvent"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="DisturbanceEvent.year"
    )
    calculations: Mapped[list["Calculation"]] = relationship(
        back_populates="project", order_by="Calculation.calculated_at"
    )


class ProjectRegistry(Base):
    """Раздел 2, ключ `registry`. Существует только при mode=with_project —
    при territory_only строка просто не создаётся (контракт требует null, а не пустых полей)."""

    __tablename__ = "project_registry"

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.project_id", ondelete="CASCADE"), primary_key=True
    )
    registry_number: Mapped[str] = mapped_column(String(64))
    company: Mapped[str] = mapped_column(String(512))
    methodology: Mapped[str] = mapped_column(String(255))
    crediting_period_start: Mapped[date | None] = mapped_column(Date)
    crediting_period_end: Mapped[date | None] = mapped_column(Date)
    units_in_circulation: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32), default="registry_xlsx")

    project: Mapped["Project"] = relationship(back_populates="registry")


class ProjectClaims(Base):
    """Раздел 2, ключ `claims`. area_kind, effect_kind, monitoring_date —
    обязательны при mode=with_project (см. правила раздела 2)."""

    __tablename__ = "project_claims"

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.project_id", ondelete="CASCADE"), primary_key=True
    )
    forest_area_ha: Mapped[float] = mapped_column(Numeric(12, 2))
    area_kind: Mapped[AreaKind] = mapped_column(_enum(AreaKind))
    agb_t_ha: Mapped[float] = mapped_column(Numeric(8, 2))
    expected_effect_co2_t_year: Mapped[float] = mapped_column(Numeric(14, 2))
    effect_kind: Mapped[EffectKind] = mapped_column(_enum(EffectKind))
    monitoring_date: Mapped[date] = mapped_column(Date)
    source: Mapped[ClaimsSource] = mapped_column(_enum(ClaimsSource))

    project: Mapped["Project"] = relationship(back_populates="claims")


class Observation(Base):
    """Раздел 1, ключ `observations`. Непрерывный ряд лет без пропусков в
    массиве на выходе API — год без данных хранится строкой с valid=false,
    а не отсутствует."""

    __tablename__ = "observations"
    __table_args__ = (UniqueConstraint("project_id", "year", name="uq_observations_project_year"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.project_id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer)

    forest_area_ha: Mapped[float | None] = mapped_column(Numeric(12, 2))
    agb_t_ha: Mapped[float | None] = mapped_column(Numeric(8, 2))
    agb_sd_t_ha: Mapped[float | None] = mapped_column(Numeric(8, 2))
    agb_source_year: Mapped[int | None] = mapped_column(Integer)
    valid: Mapped[bool] = mapped_column(Boolean)
    valid_coverage_pct: Mapped[float] = mapped_column(Numeric(5, 2))

    project: Mapped["Project"] = relationship(back_populates="observations")


class DisturbanceEvent(Base):
    """Раздел 1, ключ `disturbances`. event_id приходит от Р4 готовым
    (`proj-01-2021-01`) — используем его как первичный ключ, не генерируем свой."""

    __tablename__ = "disturbance_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.project_id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer)
    area_ha: Mapped[float] = mapped_column(Numeric(12, 2))
    fire_evidence: Mapped[bool] = mapped_column(Boolean)
    event_type: Mapped[EventType] = mapped_column(_enum(EventType))
    confidence: Mapped[Confidence] = mapped_column(_enum(Confidence))
    sources: Mapped[list] = mapped_column(JSONB)  # ["hansen_gfc_v1_13", ...]
    detected_between_start: Mapped[date | None] = mapped_column(Date)
    detected_between_end: Mapped[date | None] = mapped_column(Date)

    project: Mapped["Project"] = relationship(back_populates="disturbance_events")


class Calculation(Base):
    """Раздел 6 + раздел 8. Один расчёт = одна неизменяемая строка.

    Аудит-поля (раздел 8) заложены с первого дня и не подлежат удалению —
    на их основе строится реестр расчётов (P1) и независимая перепроверка
    по `GET /api/calculations/{calc_id}`.

    `result` хранит ПОЛНЫЙ объект результата (раздел 6 целиком, включая
    measurement, disturbances, vulnerability, claim_check, scenario,
    summary) — это то, что отдаёт `GET /api/projects/{project_id}` и
    `GET /api/calculations/{calc_id}` один в один. Часто используемые для
    списков поля (claim_check.status, vulnerability.level и т.п.)
    намеренно не дублируются отдельными колонками, чтобы не рассинхронить
    их с `result`; при необходимости — читать через JSON-путь при выборке
    или считать материализованными колонками отдельной миграцией позже.
    """

    __tablename__ = "calculations"

    # --- обязательные аудит-поля, раздел 8 контракта — не переименовывать ---
    calc_id: Mapped[str] = mapped_column(String(32), primary_key=True)  # "CALC-0148"
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.project_id", ondelete="RESTRICT"), index=True
    )
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    methodology_version: Mapped[str] = mapped_column(String(32))
    algorithm_version: Mapped[str] = mapped_column(String(32))
    model_version: Mapped[str | None] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))  # полный SHA-256, не усечённый
    observation_dates: Mapped[list] = mapped_column(JSONB)
    datasets: Mapped[list] = mapped_column(JSONB)
    parameters: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)
    # --- конец обязательных аудит-полей ---

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="calculations")
