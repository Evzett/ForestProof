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

from app import case_service, models
from app.database import SessionLocal
from app.hashing import compute_input_hash
from app.ids import next_calc_id

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
        _set(
            db,
            job,
            status=models.JobStatus.done,
            step=len(STEPS),
            calc_id=calc_id,
            result=result,
            finished_at=datetime.now(timezone.utc),
        )
    finally:
        db.close()


def start(job_id: str) -> None:
    """Запускает задачу в фоне.

    Поток демонский: если сервис перезапускают, он не держит выключение.
    Незавершённая задача останется в состоянии «считаем» — это видно, и
    расчёт можно повторить, а вот зависшее выключение чинить некому.
    """
    threading.Thread(target=run, args=(job_id,), daemon=True).start()
