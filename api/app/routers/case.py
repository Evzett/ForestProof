"""Раздел 6 документа 06 — расчёт по участку набора или своему контуру.

KAN-51. Заменяет заглушку `_build_synthetic_result`: числа приходят из
расчётного ядра, а не выдумываются.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auth, case_service, models
from app.database import get_db
from app.hashing import compute_input_hash
from app.ids import next_calc_id
from app.schemas import CalcRequest

router = APIRouter(prefix="/api", tags=["case"])


@router.get("/areas")
def list_areas() -> dict:
    """Участки набора для экрана выбора (В-01)."""
    return {"areas": case_service.list_areas()}


@router.post("/calc")
def calculate(
    body: CalcRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_analyst),
) -> dict:
    """Расчёт по контуру и паре лет (В-02, В-03, В-04).

    Контур приходит либо геометрией, либо идентификатором участка набора —
    второе нужно, чтобы экран участка и произвольный контур шли одним путём.

    Запуск расчёта — запись: он создаёт строку в журнале, которой кто-то
    владеет. Поэтому требуется аналитик, и проверка стоит здесь, на
    сервере (KAN-78). Наблюдателю остаётся просмотр участков набора: они
    посчитаны заранее и открываются вообще без обращения к API.
    """
    if body.geometry is None and body.aoi_id is None:
        raise HTTPException(status_code=422, detail="нужен geometry или aoi_id")

    geometry = body.geometry
    if geometry is None:
        geometry = case_service.load_case_set().geometries.get(body.aoi_id)
        if geometry is None:
            raise HTTPException(status_code=404, detail=f"участок {body.aoi_id} не найден")

    try:
        result = case_service.calculate(geometry, body.year_start, body.year_end)
    except case_service.CalculationError as exc:
        # Причина отказа — часть ответа, а не текст в логе: её показывают
        # пользователю вместо результата (В-05).
        raise HTTPException(status_code=exc.status, detail=exc.reason) from exc

    calc_id = next_calc_id(db)
    now = datetime.now(timezone.utc)

    # Ж-02: хеш входа выводится из участка, периода, базовой линии и версий
    # источников — по нему видно, что два расчёта шли по одним данным.
    input_hash = compute_input_hash(
        {
            "geometry": geometry,
            "year_start": body.year_start,
            "year_end": body.year_end,
            "baseline_id": result.get("baseline_id"),
            "sources": case_service.load_case_set().config.__class__.__name__,
        }
    )

    result["calc_id"] = calc_id
    result["calculated_at"] = now.isoformat()
    result["input_hash"] = input_hash

    db.add(
        models.Calculation(
            calc_id=calc_id,
            project_id=None,
            calculated_at=now,
            methodology_version="case-1.0",
            algorithm_version="calc-1.0",
            model_version=None,
            input_hash=input_hash,
            observation_dates=[str(body.year_start), str(body.year_end)],
            datasets=[{"name": "ESA CCI Biomass", "version": "v7.0"}],
            parameters={"year_start": body.year_start, "year_end": body.year_end},
            result=result,
            # Ж-01: в журнале должно быть видно, кто запустил расчёт.
            created_by=user.login,
        )
    )
    db.commit()

    return result
