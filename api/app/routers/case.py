"""Раздел 6 документа 06 — расчёт по участку набора или своему контуру.

KAN-51. Заменяет заглушку `_build_synthetic_result`: числа приходят из
расчётного ядра, а не выдумываются.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import secrets

from app import auth, case_service, jobs, models
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
    user: models.User = Depends(auth.require_operator),
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
    # Контур прислали или это участок набора по идентификатору — от этого
    # зависит, искать ли под него свои снимки.
    own_geometry = geometry is not None
    if geometry is None:
        geometry = case_service.load_case_set().geometries.get(body.aoi_id)
        if geometry is None:
            raise HTTPException(status_code=404, detail=f"участок {body.aoi_id} не найден")

    try:
        result = case_service.calculate(
            geometry, body.year_start, body.year_end, own_geometry=own_geometry
        )
    except case_service.CalculationError as exc:
        # Причина отказа — часть ответа, а не текст в логе: её показывают
        # пользователю вместо результата (В-05).
        raise HTTPException(status_code=exc.status, detail=exc.reason) from exc

    now = datetime.now(timezone.utc)

    # Номер расчёта тоже берётся из журнала — значит и он недоступен,
    # когда база лежит. Без него результат всё равно есть, и показать
    # его важнее, чем присвоить красивый номер.
    try:
        calc_id = next_calc_id(db)
    except SQLAlchemyError:
        db.rollback()
        calc_id = f"CALC-LOCAL-{now.strftime('%Y%m%d-%H%M%S')}"

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

    # Журнал — не условие расчёта. Раньше недоступная база роняла весь
    # запрос пятисоткой: числа были посчитаны, но пользователь видел
    # «Запрос отклонён (500)» и не получал ничего. Запись в журнал и
    # ответ на вопрос «сколько углерода на участке» — разные задачи, и
    # отказ первой не отменяет вторую.
    #
    # Молчать об этом нельзя: незаписанный расчёт не попадёт ни в список
    # расчётов, ни в раздел «что изменилось», и человек должен знать об
    # этом сразу, а не обнаружить позже пропажу.
    try:
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
        result["stored"] = True
    except SQLAlchemyError:
        db.rollback()
        result["stored"] = False
        result["storage_note"] = (
            "Расчёт выполнен, но не записан в журнал: база данных недоступна. "
            "Числа верны, однако этого расчёта не будет в списке сохранённых."
        )

    return result


@router.post("/calc/jobs")
def start_calc_job(
    body: CalcRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_operator),
) -> dict:
    """Ставит расчёт в фон и сразу возвращает номер задачи.

    Синхронный `POST /api/calc` остаётся: по участку набора расчёт идёт
    секунды, и гонять его через задачу незачем. Фон нужен контуру вне
    набора — там данные едут из открытых источников минутами.
    """
    if body.geometry is None and body.aoi_id is None:
        raise HTTPException(status_code=422, detail="нужен geometry или aoi_id")

    geometry = body.geometry
    if geometry is None:
        geometry = case_service.load_case_set().geometries.get(body.aoi_id)
        if geometry is None:
            raise HTTPException(status_code=404, detail=f"участок {body.aoi_id} не найден")

    # Запрос проверяется сразу: отказ по годам или по геометрии должен
    # прийти немедленно, а не через две минуты ожидания.
    try:
        case_service.validate_request(geometry, body.year_start, body.year_end)
    except case_service.CalculationError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.reason) from exc

    job = models.CalcJob(
        job_id=f"JOB-{secrets.token_hex(6)}",
        geometry=geometry,
        year_start=body.year_start,
        year_end=body.year_end,
        status=models.JobStatus.queued,
        created_by=user.login,
    )
    db.add(job)
    db.commit()

    jobs.start(job.job_id)
    return {"job_id": job.job_id, "status": job.status.value, "steps": jobs.STEPS}


@router.get("/calc/jobs/{job_id}")
def calc_job_status(job_id: str, db: Session = Depends(get_db)) -> dict:
    """Состояние задачи. Открыто всем: по номеру задачи ничего чужого не
    видно, а спрашивать своё состояние должно быть можно без входа —
    вкладку могли перезагрузить."""
    job = db.get(models.CalcJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="задача не найдена")
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "step": job.step,
        "steps": jobs.STEPS,
        "error": job.error,
        "calc_id": job.calc_id,
        "created_by": job.created_by,
        "result": job.result if job.status is models.JobStatus.done else None,
    }
