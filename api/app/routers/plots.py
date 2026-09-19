"""Мастер создания участка: проверка геометрии и настоящий расчёт.

`POST /api/plots` использует ту же цепочку `case_service.calculate`, что
и основной `POST /api/calc`. Правдоподобные синтетические числа здесь
запрещены: если для контура нет сохранённых растров, API возвращает
объяснимый 422, а не выдаёт выдуманный результат.
"""

import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import API_ROOT
from app.database import get_db
from app import auth, case_service, models
from app.geometry import parse_uploaded_geometry, run_geometry_checks
from app.hashing import compute_input_hash
from app.ids import next_calc_id, next_plot_id, next_project_id
from app.previews import render_fallback_preview
from app.routers.calculations import STEP_NAMES
from app.schemas import PlotCreateRequest

router = APIRouter(prefix="/api", tags=["plots"])

@router.post("/plots/validate")
async def validate_geometry(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: models.User = Depends(auth.require_operator),
) -> dict:
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

    if accepted:
        parent = case_service.covering_area(geom_dict)
        coverage_ok = parent is not None
        checks.append(
            {
                "name": "prepared_data_coverage",
                "ok": coverage_ok,
                "value": (
                    f"2019–2024, родительский участок {parent['aoi_id']}"
                    if parent
                    else "контур вне подготовленного покрытия"
                ),
            }
        )
        accepted = accepted and coverage_ok

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
def create_plot(
    body: PlotCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_operator),
) -> dict:
    """Раздел 12, шаг 3–4 мастера. `boundary_source` обязателен (FR-21) —
    гарантируется схемой `PlotCreateRequest` (min_length=1, 422 при пустом)."""
    upload = db.get(models.GeometryUpload, body.upload_token)
    if upload is None:
        raise HTTPException(status_code=404, detail="upload_token не найден или истёк")
    if not upload.accepted:
        raise HTTPException(status_code=422, detail="геометрия не прошла проверку — есть блокирующие ошибки")

    try:
        result = case_service.calculate(upload.geometry, body.year_start, body.year_end)
    except case_service.CalculationError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.reason) from exc

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

    calc_id = next_calc_id(db)
    now = datetime.now(timezone.utc)
    result.update(
        {
            "calc_id": calc_id,
            "project_id": project.project_id,
            "calculated_at": now.isoformat(),
            "methodology_version": "case-1.0",
            "algorithm_version": "calc-1.0",
            "input_hash": compute_input_hash(
                {
                    "geometry": upload.geometry,
                    "boundary_source": body.boundary_source,
                    "year_start": body.year_start,
                    "year_end": body.year_end,
                }
            ),
            "preview_path": f"data/previews/{calc_id}.png",
        }
    )

    geometry_path = API_ROOT / project.geometry_path
    geometry_path.parent.mkdir(parents=True, exist_ok=True)
    feature = {"type": "Feature", "properties": {"project_id": project.project_id}, "geometry": upload.geometry}
    geometry_path.write_text(json.dumps(feature, ensure_ascii=False), encoding="utf-8")
    project.area_ha = result["area_ha"]

    render_fallback_preview(
        upload.geometry,
        API_ROOT / result["preview_path"],
        calc_id=calc_id,
        observation_date=str(body.year_end),
    )

    calc = models.Calculation(
        calc_id=calc_id,
        project_id=project.project_id,
        calculated_at=now,
        methodology_version="case-1.0",
        algorithm_version="calc-1.0",
        model_version=None,
        input_hash=compute_input_hash({"geometry": upload.geometry, "boundary_source": body.boundary_source}),
        observation_dates=[str(body.year_start), str(body.year_end)],
        datasets=[{"name": "ESA CCI Biomass", "version": "v7.0"}],
        parameters={"year_start": body.year_start, "year_end": body.year_end},
        result=result,
        created_by=user.login,
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
        status=models.PlotStatus.done,
        created_at=now,
    )
    db.add(plot)
    db.commit()

    return {"calc_id": calc_id, "status": "done"}


def _progress_for_plot(plot: models.Plot) -> dict:
    return {
        "calc_id": plot.calc_id,
        "status": "done",
        "steps": [{"name": name, "status": "done", "result": None} for name in STEP_NAMES],
    }
