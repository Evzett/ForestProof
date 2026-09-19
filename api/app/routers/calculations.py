"""Раздел 7 контракта — реестр расчётов (независимая перепроверка)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app import auth, models

router = APIRouter(prefix="/api", tags=["calculations"])

STEP_NAMES = [
    "Лесопокрытая площадь по годам",
    "Биомасса с погрешностью",
    "События нарушений и пожарные признаки",
    "Полнота данных и доверие",
    "Уязвимость территории",
]


def _done_step(name: str) -> dict:
    return {"name": name, "status": "done", "result": None}


@router.get("/calculations")
def list_calculations(
    mine: bool = False,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(auth.current_user),
) -> dict:
    """Журнал расчётов. `mine=true` — только свои (Ж-01).

    Сам журнал открыт всем: в нём номера, версии методики и хеши входа, а
    не содержимое чужих участков. Скрывать его значило бы отнять у
    проверяющего главное — возможность увидеть, что расчёт вообще был.

    Автор показывается именем, а не логином: журнал читают люди.
    """
    query = select(models.Calculation).order_by(models.Calculation.calculated_at.desc())
    if mine:
        query = query.where(models.Calculation.created_by == (user.login if user else None))
    calcs = db.scalars(query).all()

    # Имена авторов — одним запросом, а не по строке на расчёт: журнал
    # растёт, и обход в цикле превратился бы в сотню запросов.
    names = dict(db.execute(select(models.User.login, models.User.display_name)).all())

    return {
        "calculations": [
            {
                "calc_id": c.calc_id,
                "project_id": c.project_id,
                "calculated_at": c.calculated_at.isoformat(),
                "methodology_version": c.methodology_version,
                "algorithm_version": c.algorithm_version,
                "model_version": c.model_version,
                "input_hash": c.input_hash,
                "created_by": c.created_by,
                # Расчёты старше ролей автора не имеют, и приписывать им
                # кого-то задним числом нельзя. Так и пишем.
                "author": names.get(c.created_by) if c.created_by else None,
                "mine": bool(user and c.created_by == user.login),
            }
            for c in calcs
        ]
    }


@router.get("/calculations/{calc_id}")
def get_calculation(calc_id: str, db: Session = Depends(get_db)) -> dict:
    """Полный объект расчёта — раздел 6 один в один, включая `provenance`.
    Это и есть выгрузка расчёта в JSON для независимой перепроверки."""
    calc = db.get(models.Calculation, calc_id)
    if calc is None:
        raise HTTPException(status_code=404, detail="расчёт не найден")
    return calc.result


@router.get("/calculations/{calc_id}/progress")
def get_calculation_progress(calc_id: str, db: Session = Depends(get_db)) -> dict:
    """Раздел 12. Состояние расчёта для окна прогресса мастера.

    У расчётов, созданных сразу с полным результатом (сегодняшний мок-сид и
    расчёты вне мастера), прогресс — все шаги `done`. У расчётов, запущенных
    `POST /api/plots`, шаги открываются по времени с момента создания
    участка — см. `plots.py`, `_progress_for_plot`. Настоящего асинхронного
    расчётного ядра (Р3) здесь нет, это витрина состояния для интерфейса."""
    calc = db.get(models.Calculation, calc_id)
    if calc is None:
        raise HTTPException(status_code=404, detail="расчёт не найден")

    plot = db.scalars(select(models.Plot).where(models.Plot.calc_id == calc_id)).first()
    if plot is None:
        return {"calc_id": calc_id, "status": "done", "steps": [_done_step(name) for name in STEP_NAMES]}

    from app.routers.plots import _progress_for_plot  # локальный импорт — избегаем цикла

    return _progress_for_plot(plot)
