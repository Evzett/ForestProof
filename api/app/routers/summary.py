"""Краткая справка, изложенная языковой моделью.

Эндпоинт нужен не ради самой модели, а ради ключа: он лежит на сервере
и в сборку фронта не попадает. Фронт присылает уже посчитанные факты и
получает текст либо отказ — считать на этой стороне нечего.
"""

from fastapi import APIRouter

from app import summary_ai
from app.config import settings
from app.schemas import SummaryRequest

router = APIRouter(prefix="/api", tags=["summary"])


@router.get("/summary/status")
def summary_status() -> dict:
    """Доступна ли модель. Фронт спрашивает это до показа кнопки."""
    configured = settings.routerai
    return {
        "available": configured is not None,
        "model": configured[1] if configured else None,
    }


@router.post("/summary")
def compose_summary(request: SummaryRequest) -> dict:
    """Излагает переданные факты связным текстом.

    Ответы, где появились числа вне переданных фактов, не возвращаются:
    вместо текста приходит `available: false` с причиной, и фронт
    показывает шаблонную справку. Проверка стоит здесь, а не в промпте,
    потому что промпт — это просьба, а проверка — гарантия.
    """
    facts = request.facts
    result = summary_ai.compose(facts)

    if result is None:
        return {
            "available": False,
            "reason": "модель недоступна: нет ключа или нет сети",
        }
    if result.rejected_reason:
        return {
            "available": False,
            "reason": result.rejected_reason,
            "model": result.model,
        }
    return {
        "available": True,
        "text": result.text,
        "model": result.model,
        "guarantee": (
            "Модель только формулирует. Числа посчитаны сервисом и сверены "
            "с ответом: величины вне расчёта отбраковываются."
        ),
    }
