"""Раздел 12 контракта — мастер создания участка: проверка геометрии,
создание участка, прогресс расчёта.

Настоящего расчётного ядра (Р3) в этом тикете нет: `POST /api/plots`
синхронно кладёт в БД правдоподобный, но не основанный на спутниковых
данных результат (см. `_build_synthetic_result`) — чтобы `calc_id` сразу
был рабочим (GET по нему не падал в 503), а окно прогресса мастера могло
показать честную имитацию хода расчёта. Форма результата (раздел 6) не
меняется — когда появится настоящий Р3, этот генератор заменяется вызовом
расчётного модуля без изменений в API.
"""

import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import API_ROOT
from app.database import get_db
from app import models
from app.geometry import parse_uploaded_geometry, run_geometry_checks
from app.hashing import compute_input_hash
from app.ids import next_calc_id, next_plot_id, next_project_id
from app.previews import render_fallback_preview
from app.routers.calculations import STEP_NAMES
from app.schemas import PlotCreateRequest

router = APIRouter(prefix="/api", tags=["plots"])

STEP_SECONDS = 2  # раскрытие шагов прогресса по времени — см. модульный докстринг
STEP_RESULTS = {
    "Лесопокрытая площадь по годам": "11 из 12 лет",
    "Биомасса с погрешностью": "154 ± 26 т/га",
}


@router.post("/plots/validate")
async def validate_geometry(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    """Раздел 12, шаг 2 мастера. Только GeoJSON — см. app/geometry.py."""
    raw_bytes = await file.read()
    try:
        raw = json.loads(raw_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {
            "accepted": False,
            "checks": [{"name": "geometry_type", "ok": False, "value": "файл не является JSON/GeoJSON"}],
            "upload_token": None,
        }

    try:
        geom_dict = parse_uploaded_geometry(raw)
        checks, accepted, area_ha = run_geometry_checks(geom_dict)
    except (ValueError, KeyError, TypeError) as exc:
        return {
            "accepted": False,
            "checks": [{"name": "geometry_type", "ok": False, "value": str(exc)}],
            "upload_token": None,
        }

    upload_token = f"tmp-{secrets.token_hex(3)}"
    db.add(
        models.GeometryUpload(
            upload_token=upload_token,
            geometry=geom_dict,
            checks=checks,
            accepted=accepted,
            area_ha=area_ha,
        )
    )
    db.commit()

    return {"accepted": accepted, "checks": checks, "upload_token": upload_token}


@router.post("/plots")
def create_plot(body: PlotCreateRequest, db: Session = Depends(get_db)) -> dict:
    """Раздел 12, шаг 3–4 мастера. `boundary_source` обязателен (FR-21) —
    гарантируется схемой `PlotCreateRequest` (min_length=1, 422 при пустом)."""
    upload = db.get(models.GeometryUpload, body.upload_token)
    if upload is None:
        raise HTTPException(status_code=404, detail="upload_token не найден или истёк")
    if not upload.accepted:
        raise HTTPException(status_code=422, detail="геометрия не прошла проверку — есть блокирующие ошибки")

    if body.link_project_id is not None:
        project = db.get(models.Project, body.link_project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="link_project_id не найден")
    else:
        project_id = next_project_id(db)
        project = models.Project(
            project_id=project_id,
            name=body.name,
            region=None,
            mode=models.ProjectMode.territory_only,
            geometry_path=f"data/polygons/{project_id}.geojson",
            area_ha=upload.area_ha,
        )
        db.add(project)
        db.flush()

    geometry_path = API_ROOT / project.geometry_path
    geometry_path.parent.mkdir(parents=True, exist_ok=True)
    feature = {"type": "Feature", "properties": {"project_id": project.project_id}, "geometry": upload.geometry}
    geometry_path.write_text(json.dumps(feature, ensure_ascii=False), encoding="utf-8")
    project.area_ha = upload.area_ha

    calc_id = next_calc_id(db)
    now = datetime.now(timezone.utc)
    result = _build_synthetic_result(project, upload, calc_id, now)

    render_fallback_preview(
        upload.geometry,
        API_ROOT / result["preview_path"],
        calc_id=calc_id,
        observation_date=result["data_completeness"]["latest_observation_date"],
    )

    calc = models.Calculation(
        calc_id=calc_id,
        project_id=project.project_id,
        calculated_at=now,
        methodology_version="1.0",
        algorithm_version="calc-mock-0.1",
        model_version=None,
        input_hash=compute_input_hash({"geometry": upload.geometry, "boundary_source": body.boundary_source}),
        observation_dates=[now.date().isoformat()],
        datasets=[{"name": "заглушка мастера (без Р3)", "version": "mock-0.1"}],
        parameters={},
        result=result,
    )
    db.add(calc)

    plot = models.Plot(
        plot_id=next_plot_id(db),
        name=body.name,
        boundary_source=body.boundary_source,
        link_project_id=body.link_project_id,
        upload_token=body.upload_token,
        project_id=project.project_id,
        calc_id=calc_id,
        status=models.PlotStatus.running,
        created_at=now,
    )
    db.add(plot)
    db.commit()

    return {"calc_id": calc_id, "status": "running"}


def _build_synthetic_result(project: models.Project, upload: models.GeometryUpload, calc_id: str, now: datetime) -> dict:
    area_ha = float(upload.area_ha)
    forest_area = round(area_ha * 0.86, 2)
    agb = 150.0
    co2_per_ha = 255.0
    observation_date = now.date().isoformat()

    return {
        "calc_id": calc_id,
        "project_id": project.project_id,
        "calculated_at": now.isoformat(),
        "methodology_version": "1.0",
        "algorithm_version": "calc-mock-0.1",
        "input_hash": compute_input_hash({"geometry": upload.geometry}),
        "measurement": {
            "forest_area_ha_latest": forest_area,
            "forest_area_change_pct": 0.0,
            "agb_t_ha": agb,
            "agb_sd_t_ha": 25.0,
            "agb_source_year": now.year - 1,
            "co2_stock_equivalent_t_ha": co2_per_ha,
            "co2_stock_total_t": round(co2_per_ha * forest_area, 1),
            "series": [
                {"year": now.year, "forest_area_ha": forest_area, "co2_stock_total_t": round(co2_per_ha * forest_area, 1)}
            ],
        },
        "disturbances": {
            "historical_loss_share_pct": 0.0,
            "recent_loss_ha": 0.0,
            "recent_window_years": 1,
            "fire_exposure": "low",
            "events": [],
        },
        "vulnerability": {
            "level": "low",
            "drivers": [],
            "method": "heuristic",
            "model_version": None,
            "disclaimer": "Аналитический скрининг, не официальный расчёт риска реверсии",
        },
        "data_completeness": {
            "periods_available": 1,
            "periods_total": 1,
            "valid_coverage_pct": 100.0,
            "latest_observation_date": observation_date,
            "missing_years": [],
        },
        "measurement_confidence": {
            "overall": "low",
            "components": {
                "optical_coverage": "low",
                "observation_freshness": "high",
                "biomass_uncertainty": "low",
                "cross_source_support": "low",
            },
        },
        # claim_check осознанно отсутствует (не только для territory_only,
        # но и для link_project_id → with_project): сверка требует реального
        # ряда наблюдений от Р3, которого у этого синтетического результата
        # нет — честнее не показывать блок, чем подделывать сравнение.
        "scenario": {
            "expected_effect_co2_t_year": 0.0,
            "effect_source": "user_defined",
            "price_scenario": None,
            "price_rub_per_unit": 0.0,
            "haircut_pct": 0.0,
            "revenue_rub_year": 0.0,
            "revenue_rub_per_ha": 0.0,
            "area_basis": "polygon",
            "npv_rub": None,
            "npv_available": False,
            "npv_unavailable_reason": "Нет заявленных показателей эффекта для этого участка",
        },
        "preview_path": f"data/previews/{calc_id}.png",
        "provenance": {
            "datasets": [{"name": "заглушка мастера (без Р3)", "version": "mock-0.1"}],
            "observation_dates": [observation_date],
            "parameters": {"carbon_fraction": 0.47, "co2_factor": 3.6667, "discount_rate": 0.18},
        },
    }


def _progress_for_plot(plot: models.Plot) -> dict:
    now = datetime.now(timezone.utc)
    elapsed = (now - plot.created_at).total_seconds() if plot.created_at else 0.0
    n_done = min(len(STEP_NAMES), int(elapsed // STEP_SECONDS))

    steps = []
    for i, name in enumerate(STEP_NAMES):
        if i < n_done:
            steps.append({"name": name, "status": "done", "result": STEP_RESULTS.get(name)})
        elif i == n_done:
            steps.append({"name": name, "status": "running", "result": None})
        else:
            steps.append({"name": name, "status": "wait", "result": None})

    return {
        "calc_id": plot.calc_id,
        "status": "done" if n_done >= len(STEP_NAMES) else "running",
        "steps": steps,
    }
