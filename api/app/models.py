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
    registry_import_meta — метаданные последней загрузки выгрузки реестра (раздел 12)
    registry_catalog     — каталог всех проектов выгрузки реестра (раздел 12, KAN-43)
    geometry_uploads     — временные проверенные геометрии между /plots/validate и /plots
    plots                — участки, созданные через мастер загрузки границы (раздел 12)
    watchlist            — отслеживаемые участки (раздел 12)
    users                — учётные записи и роли (KAN-78), пароли только хешем
    saved_contours       — загруженные пользователем контуры и расчёты по ним (KAN-78)
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


class Role(str, enum.Enum):
    """Роли из KAN-78. Порядок значений — по возрастанию прав."""

    viewer = "viewer"  # наблюдатель: только смотреть
    analyst = "analyst"  # аналитик: плюс загружать контур и считать
    admin = "admin"  # администратор: плюс управлять набором и журналом


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


class DataStatus(str, enum.Enum):
    """Раздел 12, GET /api/registry/projects."""

    calculated = "calculated"
    no_geometry = "no_geometry"
    in_progress = "in_progress"


class PlotStatus(str, enum.Enum):
    """Статус расчёта, запущенного мастером (раздел 12). Не путать с
    `claim_check.status` из раздела 6 — это состояние пайплайна, а не сверки."""

    running = "running"
    done = "done"
    failed = "failed"


class WatchStatus(str, enum.Enum):
    attention = "attention"
    quiet = "quiet"


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
    # Площадь полигона участка (раздел 1, `polygon_area_ha`) — статический атрибут
    # геометрии, а не результата расчёта, поэтому живёт на проекте, а не в
    # `calculations.result`. Используется как `area_ha` в GET /api/projects
    # и как основа `revenue_rub_per_ha` при `area_basis: polygon` (раздел 6).
    area_ha: Mapped[float] = mapped_column(Numeric(14, 2))

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
    # Расчёт по контуру проекту не принадлежит: в постановке кейса проекта
    # нет ни в данных, ни по смыслу (миграция 0003).
    project_id: Mapped[str | None] = mapped_column(
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
    # Ж-01 (KAN-78): чей это расчёт. Пусто у расчётов, созданных до
    # появления ролей, и у сидовых — врать об авторстве нельзя.
    created_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.login", ondelete="SET NULL"), index=True
    )

    project: Mapped["Project"] = relationship(back_populates="calculations")


class RegistryImportMeta(Base):
    """Раздел 12, `GET /api/registry/projects` → `export_date`. Одна строка —
    метаданные последней загруженной выгрузки реестра. `total_declared`
    хранит число проектов, заявленное самой выгрузкой (для мок-набора может
    расходиться с фактическим количеством строк в `registry_catalog`, если
    загружен неполный/демонстрационный срез — тогда API честно отдаёт
    количество реально загруженных строк, а не `total_declared`)."""

    __tablename__ = "registry_import_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    export_date: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(255))
    total_declared: Mapped[int | None] = mapped_column(Integer)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RegistryCatalogEntry(Base):
    """Раздел 12, `GET /api/registry/projects`. Каталог ВСЕХ проектов из
    выгрузки реестра (KAN-43) — не только тех, что уже посчитаны. При
    `data_status != calculated` `project_id`/`calc_id` пустые (раздел 12)."""

    __tablename__ = "registry_catalog"

    registry_number: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    company: Mapped[str] = mapped_column(String(512))
    region: Mapped[str] = mapped_column(String(255))
    methodology: Mapped[str] = mapped_column(String(255))
    effect_kind: Mapped[EffectKind | None] = mapped_column(_enum(EffectKind))
    units_in_circulation: Mapped[int | None] = mapped_column(Integer)
    data_status: Mapped[DataStatus] = mapped_column(_enum(DataStatus))
    project_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("projects.project_id", ondelete="SET NULL")
    )
    calc_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("calculations.calc_id", ondelete="SET NULL")
    )


class GeometryUpload(Base):
    """Раздел 12, `POST /api/plots/validate` → `upload_token`. Хранит
    проверенную геометрию между шагом 2 (проверка) и шагом 3 (создание
    участка) мастера — живёт до использования в `POST /api/plots`, старые
    непринятые токены можно чистить по `created_at` отдельной задачей."""

    __tablename__ = "geometry_uploads"

    upload_token: Mapped[str] = mapped_column(String(32), primary_key=True)  # "tmp-7f31c9"
    geometry: Mapped[dict] = mapped_column(JSONB)  # GeoJSON Feature, EPSG:4326
    checks: Mapped[list] = mapped_column(JSONB)
    accepted: Mapped[bool] = mapped_column(Boolean)
    area_ha: Mapped[float] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Plot(Base):
    """Раздел 12, `POST /api/plots`. Участок, созданный мастером загрузки
    границы — отдельно от `projects`, потому что фиксирует сам факт и
    обстоятельства загрузки (кто откуда взял границу, к какому проекту
    привязал), а не расчётные данные. `boundary_source` обязателен (FR-21)."""

    __tablename__ = "plots"

    plot_id: Mapped[str] = mapped_column(String(32), primary_key=True)  # "PLOT-0001"
    name: Mapped[str] = mapped_column(String(255))
    boundary_source: Mapped[str] = mapped_column(String(512))
    link_project_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("projects.project_id", ondelete="SET NULL")
    )
    upload_token: Mapped[str] = mapped_column(String(32), ForeignKey("geometry_uploads.upload_token"))
    project_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("projects.project_id", ondelete="SET NULL")
    )
    calc_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("calculations.calc_id", ondelete="SET NULL")
    )
    status: Mapped[PlotStatus] = mapped_column(_enum(PlotStatus))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    """Учётная запись. KAN-78.

    Пароль хранится ТОЛЬКО хешем bcrypt — открытого пароля в базе нет и
    быть не может, и в логи он не попадает ни при каких обстоятельствах.

    Регистрации нет намеренно: на хакатоне подтверждение почты — время без
    баллов. Учётные записи заводятся заранее (`python -m app.seed_users`).
    """

    __tablename__ = "users"

    login: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SavedContour(Base):
    """Контур, загруженный пользователем, вместе с расчётом по нему. KAN-78.

    Почему отдельно от `geometry_uploads`: там временный токен между двумя
    шагами мастера, который живёт до использования. Здесь — сам результат
    работы пользователя: он должен пережить перезагрузку страницы, найтись
    в списке и открыться снова. Без этого загруженный файл исчезал сразу
    после показа результата, и вернуться к нему было нельзя.

    Геометрия хранится целиком: по ней участок отрисовывается повторно и
    пересчитывается, а `source_name` — имя исходного файла, чтобы человек
    узнал свою загрузку среди прочих.
    """

    __tablename__ = "saved_contours"

    contour_id: Mapped[str] = mapped_column(String(32), primary_key=True)  # "AOI-0001"
    name: Mapped[str] = mapped_column(String(255))
    source_name: Mapped[str] = mapped_column(String(255))  # имя файла или способ ввода
    source_kind: Mapped[str] = mapped_column(String(32))  # file | coords | table | draw
    geometry: Mapped[dict] = mapped_column(JSONB)
    area_ha: Mapped[float] = mapped_column(Numeric(14, 4))
    year_start: Mapped[int] = mapped_column(Integer)
    year_end: Mapped[int] = mapped_column(Integer)
    calc_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("calculations.calc_id", ondelete="SET NULL"), index=True
    )
    created_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.login", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    calculation: Mapped["Calculation"] = relationship()


class WatchlistEntry(Base):
    """Раздел 12, `GET/POST /api/watchlist`. Подписки и уведомления не
    реализуются в прототипе (контракт) — только список и добавление/удаление."""

    __tablename__ = "watchlist"

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.project_id", ondelete="CASCADE"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    new_events_count: Mapped[int] = mapped_column(Integer, default=0)
    recent_loss_ha: Mapped[float | None] = mapped_column(Numeric(12, 2))
    status: Mapped[WatchStatus] = mapped_column(_enum(WatchStatus), default=WatchStatus.quiet)

    project: Mapped["Project"] = relationship()


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class CalcJob(Base):
    """Фоновый расчёт по контуру. KAN-78.

    Состояние живёт в базе, а не в памяти процесса: окно мастера можно
    закрыть, вкладку перезагрузить, а задача останется и найдётся по
    номеру. В памяти она пережила бы только текущую вкладку.
    """

    __tablename__ = "calc_jobs"

    job_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    geometry: Mapped[dict] = mapped_column(JSONB)
    year_start: Mapped[int] = mapped_column(Integer)
    year_end: Mapped[int] = mapped_column(Integer)
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus), default=JobStatus.queued)
    step: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(1024))
    result: Mapped[dict | None] = mapped_column(JSONB)
    calc_id: Mapped[str | None] = mapped_column(String(32))
    created_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.login", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
