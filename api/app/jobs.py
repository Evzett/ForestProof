"""Фоновый расчёт по контуру. KAN-78.

Зачем. Расчёт по контуру вне набора тянет данные из открытых источников:
десять лет биомассы, потери покрова, пара снимков Sentinel и гранулы
MODIS. Это минуты, а не секунды, и держать всё это время открытое окно
мастера нельзя — на защите белый экран на три минуты хуже, чем отсутствие
функции.

Поэтому запрос возвращает номер задачи сразу, а расчёт идёт в фоне.
Мастер спрашивает состояние и показывает, что именно сейчас делается.
Окно можно закрыть: задача живёт в базе, а не в памяти вкладки.

Почему поток, а не очередь задач. Очередь (Celery, RQ) — это ещё один
процесс, брокер и способ их уронить на защите. Здесь одна машина и
десятки задач в день; поток с записью состояния в базу решает ту же
задачу и не добавляет того, что может не запуститься.

Честность состояния. Шаги — настоящие: они отмечаются по мере того, как
расчёт их проходит, а не крутятся по таймеру. Если источник недоступен,
задача завершается с причиной, и причина показывается.
"""

from __future__ import annotations

import threading
import traceback
from datetime import datetime, timezone

from sqlalchemy import select

from app import case_service, models
from app.database import SessionLocal
from app.hashing import compute_input_hash
from app.ids import next_calc_id, next_contour_id

# Шаги, которые видит пользователь. Список закреплён здесь, чтобы
# интерфейс не придумывал свой и не расходился с тем, что происходит.
STEPS = [
    "Проверяем контур и период",
    "Читаем биомассу за 2015—2024",
    "Потери покрова и базовая линия",
    "Карты изменений и рельеф",
    "Снимки и подтверждение гарей",
]


def _set(db, job: models.CalcJob, **fields) -> None:
    for key, value in fields.items():
        setattr(job, key, value)
    db.commit()


def run(job_id: str) -> None:
    """Выполняет задачу. Вызывается в отдельном потоке."""
    db = SessionLocal()
    try:
        job = db.get(models.CalcJob, job_id)
        if job is None:
            return

        _set(db, job, status=models.JobStatus.running, step=0)

        # Каждый пройденный шаг сразу пишется в базу: мастер опрашивает
        # состояние и показывает ровно то, что уже сделано. Отдельная
        # сессия не нужна — эта живёт всю задачу.
        def mark(done: int) -> None:
            current = db.get(models.CalcJob, job_id)
            if current is not None:
                _set(db, current, step=done)

        try:
            result = case_service.calculate(
                job.geometry, job.year_start, job.year_end, progress=mark
            )
        except case_service.CalculationError as error:
            _set(
                db,
                job,
                status=models.JobStatus.failed,
                error=error.reason,
                finished_at=datetime.now(timezone.utc),
            )
            return
        except Exception:  # noqa: BLE001
            # Неожиданный отказ тоже должен доехать до пользователя
            # текстом, а не остаться вечным «считаем».
            _set(
                db,
                job,
                status=models.JobStatus.failed,
                error="Расчёт прервался из-за внутренней ошибки сервиса.",
                finished_at=datetime.now(timezone.utc),
            )
            traceback.print_exc()
            return

        now = datetime.now(timezone.utc)
        try:
            calc_id = next_calc_id(db)
        except Exception:  # noqa: BLE001
            db.rollback()
            calc_id = f"CALC-LOCAL-{now.strftime('%Y%m%d-%H%M%S')}"

        input_hash = compute_input_hash(
            {
                "geometry": job.geometry,
                "year_start": job.year_start,
                "year_end": job.year_end,
                "baseline_id": result.get("baseline_id"),
            }
        )
        result["calc_id"] = calc_id
        result["calculated_at"] = now.isoformat()
        result["input_hash"] = input_hash

        # Журнал — не условие расчёта: если запись не удалась, числа всё
        # равно отдаются, а о том, что расчёта не будет в списке, сказано
        # прямо.
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
                    observation_dates=[str(job.year_start), str(job.year_end)],
                    datasets=[{"name": "ESA CCI Biomass", "version": "v7.0"}],
                    parameters={"year_start": job.year_start, "year_end": job.year_end},
                    result=result,
                    created_by=job.created_by,
                )
            )
            db.commit()
            result["stored"] = True
        except Exception:  # noqa: BLE001
            db.rollback()
            result["stored"] = False
            result["storage_note"] = (
                "Расчёт выполнен, но не записан в журнал: база недоступна."
            )

        job = db.get(models.CalcJob, job_id)

        # Контур сохраняется здесь, а не браузером после опроса. Раньше
        # это делал фронт, и результат многоминутного расчёта терялся от
        # чего угодно: закрытой вкладки, перезагрузки, второго расчёта,
        # запущенного поверх первого. Расчёт при этом проходил целиком —
        # терялась только запись о нём.
        #
        # Сохранение отделено от расчёта: если оно не удалось, числа всё
        # равно отдаются, а о том, что контура в списке не будет, сказано
        # прямо. Молча терять — худшее из возможного.
        contour_id = None
        if job.name:
            try:
                contour_id = _save_contour(db, job, result, calc_id)
                result["contour_id"] = contour_id
            except Exception:  # noqa: BLE001
                db.rollback()
                result["contour_note"] = (
                    "Расчёт выполнен, но контур не сохранён в списке участков."
                )
                traceback.print_exc()
                job = db.get(models.CalcJob, job_id)

        _set(
            db,
            job,
            status=models.JobStatus.done,
            step=len(STEPS),
            calc_id=calc_id,
            contour_id=contour_id,
            result=result,
            finished_at=datetime.now(timezone.utc),
        )
    finally:
        db.close()


def _save_contour(db, job: models.CalcJob, result: dict, calc_id: str) -> str:
    """Кладёт посчитанный контур в список участков.

    Площадь берётся из расчёта, а не из полигона: это измеренная по долям
    пересечения пикселей величина, и расходиться с площадью полигона она
    может заметно.
    """
    contour_id = next_contour_id(db)
    period = result.get("period", {})
    db.add(
        models.SavedContour(
            contour_id=contour_id,
            name=job.name.strip() or "Контур без названия",
            source_name=(job.source_name or "").strip() or "контур пользователя",
            source_kind=job.source_kind or "file",
            geometry=job.geometry,
            area_ha=result.get("area_ha") or 0.0,
            year_start=period.get("year_start") or job.year_start,
            year_end=period.get("year_end") or job.year_end,
            calc_id=calc_id,
            created_by=job.created_by,
        )
    )
    db.commit()
    return contour_id


def recover_orphans() -> None:
    """Помечает неудачными задачи, чей поток не пережил перезапуск.

    Поток демонский: при перезапуске сервиса он просто исчезает, а строка
    в базе остаётся в состоянии «считаем» навсегда. Мастер честно
    опрашивает её полчаса и только потом сдаётся, хотя считать уже
    некому с первой секунды.

    Продолжить с места остановки нельзя: промежуточного состояния расчёт
    не хранит. Поэтому говорим правду — задача прервана, запустите
    заново, — вместо вечного вращения.
    """
    db = SessionLocal()
    try:
        stuck = db.scalars(
            select(models.CalcJob).where(
                models.CalcJob.status.in_([models.JobStatus.queued, models.JobStatus.running])
            )
        ).all()
        for job in stuck:
            job.status = models.JobStatus.failed
            job.error = (
                "Расчёт прерван перезапуском сервиса. Промежуточное состояние "
                "не сохраняется — запустите расчёт заново."
            )
            job.finished_at = datetime.now(timezone.utc)
        if stuck:
            db.commit()
            print(f"jobs: прервано перезапуском — {len(stuck)}")
    except Exception:  # noqa: BLE001
        db.rollback()
        traceback.print_exc()
    finally:
        db.close()


def start(job_id: str) -> None:
    """Запускает задачу в фоне.

    Поток демонский: если сервис перезапускают, он не держит выключение.
    Незавершённая задача останется в состоянии «считаем» — это видно, и
    расчёт можно повторить, а вот зависшее выключение чинить некому.
    """
    threading.Thread(target=run, args=(job_id,), daemon=True).start()
