"""Раздел 7 контракта — участки/проекты с расчётами."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.config import API_ROOT
from app.database import get_db
from app import models
from app.schemas import ScenarioRequest

router = APIRouter(prefix="/api", tags=["projects"])


def _latest_calc(project: models.Project) -> models.Calculation | None:
    """`calculations` на проекте отсортирована по `calculated_at` (см.
    `relationship(..., order_by=...)` в models.py) — последняя и есть текущая."""
    return project.calculations[-1] if project.calculations else None


def _get_project_or_404(db: Session, project_id: str, *, with_calculations: bool = True) -> models.Project:
    options = [selectinload(models.Project.claims), selectinload(models.Project.registry)]
    if with_calculations:
        options.append(selectinload(models.Project.calculations))
    project = db.scalars(
        select(models.Project).options(*options).where(models.Project.project_id == project_id)
    ).first()
    if project is None:
        raise HTTPException(status_code=404, detail="проект не найден")
    return project


def _project_list_item(project: models.Project) -> dict | None:
    calc = _latest_calc(project)
    if calc is None:
        # Участок без единого расчёта на экране сравнения не показывается —
        # это не ошибка API (раздел 7: "ошибка никогда не возвращается вместо
        # значения"), просто такому участку ещё нечего сравнивать.
        return None

    result = calc.result
    measurement = result.get("measurement", {})
    disturbances = result.get("disturbances", {})
    vulnerability = result.get("vulnerability", {})
    confidence = result.get("measurement_confidence", {})
    scenario = result.get("scenario", {})
    data_completeness = result.get("data_completeness", {})
    claim_check = result.get("claim_check")

    latest_obs = data_completeness.get("latest_observation_date")
    days_ago = (date.today() - date.fromisoformat(latest_obs)).days if latest_obs else None

    # Раздел 7: для territory_only claim_status и revenue_rub_per_ha — null,
    # фронт рисует прочерк (KAN-29), а не ошибку.
    is_territory_only = project.mode == models.ProjectMode.territory_only

    return {
        "project_id": project.project_id,
        "name": project.name,
        "mode": project.mode.value,
        "area_ha": float(project.area_ha),
        "agb_t_ha": measurement.get("agb_t_ha"),
        "agb_sd_t_ha": measurement.get("agb_sd_t_ha"),
        "historical_loss_share_pct": disturbances.get("historical_loss_share_pct"),
        "recent_loss_ha": disturbances.get("recent_loss_ha"),
        "fire_exposure": disturbances.get("fire_exposure"),
        "measurement_confidence_overall": confidence.get("overall"),
        "latest_observation_days_ago": days_ago,
        "claim_status": None if is_territory_only else (claim_check or {}).get("status"),
        "vulnerability_level": vulnerability.get("level"),
        "revenue_rub_per_ha": None if is_territory_only else scenario.get("revenue_rub_per_ha"),
        "area_basis": scenario.get("area_basis"),
        "calc_id": calc.calc_id,
    }


def _project_meta(project: models.Project) -> dict:
    claims = None
    if project.claims:
        c = project.claims
        claims = {
            "forest_area_ha": float(c.forest_area_ha),
            "area_kind": c.area_kind.value,
            "agb_t_ha": float(c.agb_t_ha),
            "expected_effect_co2_t_year": float(c.expected_effect_co2_t_year),
            "effect_kind": c.effect_kind.value,
            "monitoring_date": c.monitoring_date.isoformat(),
            "source": c.source.value,
        }
    registry = None
    if project.registry:
        r = project.registry
        registry = {
            "registry_number": r.registry_number,
            "company": r.company,
            "methodology": r.methodology,
            "crediting_period_start": r.crediting_period_start.isoformat() if r.crediting_period_start else None,
            "crediting_period_end": r.crediting_period_end.isoformat() if r.crediting_period_end else None,
            "units_in_circulation": r.units_in_circulation,
            "source": r.source,
        }
    return {
        "project_id": project.project_id,
        "name": project.name,
        "region": project.region,
        "mode": project.mode.value,
        "area_ha": float(project.area_ha),
        "registry": registry,
        "claims": claims,
        "geometry_path": project.geometry_path,
    }


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)) -> dict:
    """Экран сравнения — раздел 7. Один запрос: проекты + расчёты одним
    `selectinload`, без цикла запросов на рендере списка."""
    projects = db.scalars(select(models.Project).options(selectinload(models.Project.calculations))).all()
    items = [item for p in projects if (item := _project_list_item(p)) is not None]
    return {"projects": items}


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = _get_project_or_404(db, project_id)
    calc = _latest_calc(project)
    if calc is None:
        raise HTTPException(status_code=503, detail="расчёт ещё не готов")
    body = dict(calc.result)
    body["project"] = _project_meta(project)
    return body


@router.get("/projects/{project_id}/geometry")
def get_project_geometry(project_id: str, db: Session = Depends(get_db)) -> FileResponse:
    project = _get_project_or_404(db, project_id, with_calculations=False)
    path = API_ROOT / project.geometry_path
    if not path.is_file():
        raise HTTPException(status_code=503, detail="файл геометрии не найден на диске")
    return FileResponse(path, media_type="application/geo+json")


@router.post("/projects/{project_id}/scenario")
def recalculate_scenario(project_id: str, body: ScenarioRequest, db: Session = Depends(get_db)) -> dict:
    """Раздел 7 + требование задачи: "параметры сценария хранятся внутри
    расчёта, а не в браузере" — иначе открытый по ссылке расчёт перестанет
    совпадать сам с собой. Поэтому пересчёт МУТИРУЕТ `scenario` внутри
    ТЕКУЩЕГО (последнего) расчёта проекта — тот же `calc_id`, не новая
    строка. Это осознанный выбор: раздел 10 требует новый `calc_id` при
    пересборке справки (FR-70), но там речь о смене входных данных, а не о
    просмотре другого what-if по тем же данным; плодить новую строку в
    `calculations` на каждое движение слайдера цены — это как раз то,
    от чего предостерегает QUESTIONS_FOR_R1.md (вопрос 2)."""
    project = _get_project_or_404(db, project_id)
    calc = _latest_calc(project)
    if calc is None:
        raise HTTPException(status_code=503, detail="расчёт ещё не готов")

    scenario = _compute_scenario(project, calc, body)

    calc.result = dict(calc.result)
    calc.result["scenario"] = scenario
    flag_modified(calc, "result")
    db.commit()

    return scenario


def _compute_scenario(project: models.Project, calc: models.Calculation, body: ScenarioRequest) -> dict:
    # area_basis не входит в тело запроса (раздел 7, пример) — сохраняется
    # из текущего расчёта, пересчёт сценария её не меняет.
    area_basis = (calc.result.get("scenario") or {}).get("area_basis") or "polygon"
    if area_basis == "forest":
        area = calc.result.get("measurement", {}).get("forest_area_ha_latest")
    else:
        area = float(project.area_ha)

    revenue_rub_year = body.expected_effect_co2_t_year * body.price_rub_per_unit * (1 - body.haircut_pct / 100)
    revenue_rub_per_ha = round(revenue_rub_year / area, 2) if area else None

    npv_rub = None
    npv_available = False
    npv_unavailable_reason = "Нет CAPEX, OPEX и графика выпуска"
    if body.capex_rub is not None and body.opex_rub_year is not None and body.project_lifetime_years:
        cash_year = revenue_rub_year - body.opex_rub_year
        npv = -body.capex_rub + sum(
            cash_year / (1 + body.discount_rate) ** t for t in range(1, body.project_lifetime_years + 1)
        )
        npv_rub = round(npv, 2)
        npv_available = True
        npv_unavailable_reason = None

    return {
        "expected_effect_co2_t_year": body.expected_effect_co2_t_year,
        "effect_source": body.effect_source,
        "price_scenario": body.price_scenario,
        "price_rub_per_unit": body.price_rub_per_unit,
        "haircut_pct": body.haircut_pct,
        "revenue_rub_year": round(revenue_rub_year, 2),
        "revenue_rub_per_ha": revenue_rub_per_ha,
        "area_basis": area_basis,
        "npv_rub": npv_rub,
        "npv_available": npv_available,
        "npv_unavailable_reason": npv_unavailable_reason,
    }
