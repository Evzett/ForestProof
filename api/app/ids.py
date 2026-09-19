"""Генерация сквозных читаемых идентификаторов (`proj-04`, `CALC-0151`,
`PLOT-0003`). Раздел 8 контракта не фиксирует алгоритм генерации `calc_id`,
только формат — здесь: глобальный автоинкремент с префиксом, без привязки
к `project_id` (см. QUESTIONS_FOR_R1.md, вопрос 1; ответа от Р1 на момент
реализации нет, выбран самый простой вариант, совместимый с примерами
контракта `CALC-0148`, `CALC-0150` для разных проектов)."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def _next_numeric_suffix(db: Session, column, pattern: str) -> int:
    values = db.scalars(select(column)).all()
    max_n = 0
    for value in values:
        m = re.match(pattern, value)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def next_project_id(db: Session) -> str:
    n = _next_numeric_suffix(db, models.Project.project_id, r"^proj-(\d+)$")
    return f"proj-{n:02d}"


def next_calc_id(db: Session) -> str:
    n = _next_numeric_suffix(db, models.Calculation.calc_id, r"^CALC-(\d+)$")
    return f"CALC-{n:04d}"


def next_plot_id(db: Session) -> str:
    n = _next_numeric_suffix(db, models.Plot.plot_id, r"^PLOT-(\d+)$")
    return f"PLOT-{n:04d}"


def next_contour_id(db: Session) -> str:
    n = _next_numeric_suffix(db, models.SavedContour.contour_id, r"^AOI-(\d+)$")
    return f"AOI-{n:04d}"
