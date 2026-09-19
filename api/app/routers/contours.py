"""Загруженные пользователем контуры. KAN-78.

Закрывает разрыв в пайплайне: раньше загруженный файл разбирался в
браузере, уходил на расчёт и исчезал. Результат показывался один раз, и
вернуться к нему было нельзя — ни списком, ни ссылкой, ни статистикой.

Теперь контур сохраняется вместе с уже посчитанным расчётом, находится в
списке, открывается повторно и участвует в сводной статистике.

Чтение открыто наблюдателю: демо должно просматриваться без входа.
Запись требует аналитика, и это проверяется здесь, а не в интерфейсе.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth, models
from app.database import get_db
from app.ids import next_contour_id
from app.schemas import SaveContourRequest

router = APIRouter(prefix="/api", tags=["contours"])


def _view(row: models.SavedContour) -> dict:
    result = row.calculation.result if row.calculation else {}
    period = result.get("period", {})

    # Картинки отдаются так же, как у участков набора: имя файла плюс
    # приставка `maps_base`, которую подставляет фронт. Склеивать адреса
    # здесь значило бы завести второй способ: у карточки был бы готовый
    # адрес, у страницы участка — имя файла, и одна из них однажды
    # показала бы пустоту. Способ один.
    scenes = (result.get("evidence") or {}).get("scenes") or []
    # Снимок на конец периода отвечает на вопрос «что это за место
    # сейчас», поэтому он и идёт на обложку.
    latest = max(scenes, key=lambda s: s.get("date", ""), default=None)

    return {
        "maps": result.get("maps"),
        "maps_base": result.get("maps_base"),
        "scene": (
            {"image": latest["image"], "date": latest.get("date")}
            if latest and latest.get("image")
            else None
        ),
        "scenes_count": len(scenes),
        "events_count": len((result.get("evidence") or {}).get("events") or []),
        "evidence_notes": (result.get("evidence") or {}).get("notes") or [],
        "data_sources": result.get("data_sources") or [],
        "baseline_kind": result.get("baseline_kind"),
        "contour_id": row.contour_id,
        "name": row.name,
        "source_name": row.source_name,
        "source_kind": row.source_kind,
        "geometry": row.geometry,
        "area_ha": float(row.area_ha),
        "year_start": row.year_start,
        "year_end": row.year_end,
        "calc_id": row.calc_id,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
        # Показатели берутся из сохранённого расчёта, а не пересчитываются:
        # список и карточка обязаны показывать одно и то же число.
        "e_tco2e": period.get("e_tco2e"),
        "units": period.get("units"),
        "reason": period.get("reason"),
    }


@router.get("/contours")
def list_contours(db: Session = Depends(get_db)) -> dict:
    """Список сохранённых контуров — открыт всем, включая наблюдателя."""
    rows = db.scalars(
        select(models.SavedContour).order_by(models.SavedContour.created_at.desc())
    ).all()
    return {"contours": [_view(row) for row in rows]}


@router.get("/contours/stats")
def contour_stats(db: Session = Depends(get_db)) -> dict:
    """Сводка по загруженным контурам.

    Считается запросом к базе, а не обходом списка на клиенте: статистика
    должна сходиться с содержимым таблицы и при тысяче строк.

    Участки, где единицы недоступны, считаются отдельно, а не нулями:
    «недоступно» и «ноль» — разные ответы, и смешивать их в среднем
    значило бы занижать его на ровном месте.
    """
    total = db.scalar(select(func.count()).select_from(models.SavedContour)) or 0
    area = db.scalar(select(func.sum(models.SavedContour.area_ha))) or 0

    rows = db.scalars(select(models.SavedContour)).all()
    with_units = [r for r in rows if r.calculation and r.calculation.result.get("period", {}).get("units") is not None]
    losses = [
        r.calculation.result["period"]["e_tco2e"]
        for r in rows
        if r.calculation and r.calculation.result.get("period", {}).get("e_tco2e") is not None
    ]

    return {
        "total": int(total),
        "area_ha": float(area),
        "with_units": len(with_units),
        "units_unavailable": len(rows) - len(with_units),
        "units_total": sum(r.calculation.result["period"]["units"] for r in with_units),
        "e_tco2e_total": sum(losses) if losses else None,
        "losing_carbon": sum(1 for value in losses if value > 0),
        "gaining_carbon": sum(1 for value in losses if value <= 0),
    }


@router.get("/contours/{contour_id}")
def get_contour(contour_id: str, db: Session = Depends(get_db)) -> dict:
    """Контур целиком — в той же форме, что участок набора.

    Экран участка один на оба случая, поэтому и отдаётся ему одно и то
    же: ряды по годам, все пары лет, базовая линия, карты, рельеф,
    устойчивость. Сверху подставляются имя и происхождение, которые ввёл
    человек, — они его, а не расчёта.
    """
    row = db.get(models.SavedContour, contour_id)
    if row is None:
        raise HTTPException(status_code=404, detail="контур не найден")

    result = dict(row.calculation.result) if row.calculation else {}

    # Внутреннее имя расчёта наружу не показывается. Пока контур не
    # сохранён, у него нет идентификатора, и расчёт пользуется служебным
    # «AOI-REQUEST»; в справке он читается как чужой номер. После
    # сохранения номер есть — его и подставляем.
    summary = result.get("summary")
    if isinstance(summary, dict) and isinstance(summary.get("text"), str):
        result["summary"] = {
            **summary,
            "text": summary["text"].replace("AOI-REQUEST", row.contour_id),
        }

    return {
        **result,
        **_view(row),
        "aoi_id": row.contour_id,
        "name": row.name,
        "region": "контур пользователя",
        "role": "контур пользователя",
        "status": "расчёт по запросу",
        "area_ha_declared": float(row.area_ha),
    }


@router.post("/contours")
def save_contour(
    body: SaveContourRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_analyst),
) -> dict:
    calc = db.get(models.Calculation, body.calc_id)
    if calc is None:
        raise HTTPException(status_code=404, detail="расчёт не найден — сохранять нечего")

    result = calc.result or {}
    period = result.get("period", {})
    contour_id = next_contour_id(db)

    row = models.SavedContour(
        contour_id=contour_id,
        name=body.name.strip(),
        source_name=body.source_name.strip(),
        source_kind=body.source_kind,
        geometry=body.geometry,
        # Площадь берётся из расчёта: это измеренная по долям пересечения
        # величина, а не площадь полигона, и расходиться они могут заметно.
        area_ha=result.get("area_ha") or 0.0,
        year_start=period.get("year_start") or 2019,
        year_end=period.get("year_end") or 2024,
        calc_id=body.calc_id,
        created_by=user.login,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _view(row)


@router.delete("/contours/{contour_id}")
def delete_contour(
    contour_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_analyst),
) -> dict:
    row = db.get(models.SavedContour, contour_id)
    if row is None:
        raise HTTPException(status_code=404, detail="контур не найден")
    # Свой контур удаляет аналитик, чужой — только администратор: иначе
    # один аналитик стирал бы работу другого.
    if row.created_by != user.login and user.role is not models.Role.admin:
        raise HTTPException(
            status_code=403,
            detail="Удалять чужой контур может только администратор.",
        )
    db.delete(row)
    db.commit()
    return {"ok": True, "contour_id": contour_id}
