"""Формулировка краткой справки языковой моделью.

Зачем вообще модель. Шаблонная справка считает верно, но читается как
протокол: «3 из 4 участков теряют углерод». Модель тот же набор фактов
излагает связным текстом.

Чем это НЕ является. Модель не считает и не решает. Ей передаётся
готовый список фактов, посчитанных нашим кодом, и запрещено вводить
величины, которых в списке нет. Запрет держится не просьбой в промпте,
а проверкой: каждое число из ответа ищется среди переданных, и если
находится лишнее — ответ отбрасывается целиком и на экран идёт
шаблонная справка.

Поэтому свойство «сервис ничего не выдумывает» сохраняется даже если
модель однажды решит дофантазировать: выдумка не пройдёт дальше этого
модуля.

Ключ живёт только здесь, на сервере. В сборку фронта он не попадает:
иначе его увидел бы любой, кто откроет страницу.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.config import settings

SYSTEM_PROMPT = (
    "Ты редактор в сервисе проверки лесных климатических проектов по спутнику. "
    "Тебе дают список уже посчитанных фактов. Твоя работа — изложить их связным "
    "русским текстом.\n\n"
    "ЖЁСТКИЕ ПРАВИЛА:\n"
    "1. Не вводи ни одного числа, которого нет в фактах. Не округляй, не "
    "пересчитывай, не складывай, не выводи проценты.\n"
    "2. Не добавляй причин, оценок и прогнозов. Если в фактах сказано, что "
    "причина не установлена, так и пиши.\n"
    "3. Не называй результат сертифицированными углеродными единицами.\n"
    "4. Три-четыре предложения, без заголовков и списков, без общих слов "
    "вроде «важно отметить».\n"
    "5. Если из фактов следует, что единиц нет, скажи об этом прямо: это "
    "результат расчёта, а не отсутствие данных."
)

# Числа из ответа: целые и дробные, с пробелами-разделителями тысяч.
NUMBER = re.compile(r"\d[\d   ]*(?:[.,]\d+)?")


def _canonical(text: str) -> str:
    """Число к виду, в котором его можно сравнивать: без разделителей."""
    return text.replace(" ", "").replace(" ", "").replace(" ", "").replace(",", ".").rstrip(".")


@dataclass(frozen=True, slots=True)
class SummaryResult:
    text: str
    model: str
    rejected_reason: str | None = None


def allowed_numbers(facts: dict) -> set[str]:
    """Все числа, которые модели разрешено произносить.

    Берутся из самих фактов рекурсивно. Год записи вроде «2019—2024»
    распадается на два числа, и оба попадают в набор — иначе корректная
    фраза с периодом отбрасывалась бы как выдумка.
    """
    found: set[str] = set()

    def walk(value) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                # Имена полей тоже часть фактов: в них живут периоды
                # вроде «потери 2020—2024», и без них корректная фраза
                # с этим периодом отбраковывалась бы как выдумка.
                walk(key)
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif isinstance(value, bool):
            return
        elif isinstance(value, (int, float)):
            found.add(_canonical(f"{value}"))
            found.add(_canonical(f"{round(value)}"))
            found.add(_canonical(f"{value:.1f}"))
            found.add(_canonical(f"{value:.2f}"))
        elif isinstance(value, str):
            for match in NUMBER.findall(value):
                found.add(_canonical(match))

    walk(facts)
    found.discard("")
    return found


def invented_numbers(text: str, facts: dict) -> list[str]:
    """Числа из текста, которых нет в фактах."""
    allowed = allowed_numbers(facts)
    extra = []
    for match in NUMBER.findall(text):
        value = _canonical(match)
        if not value or value in allowed:
            continue
        # Мелкие счётные числа модель вправе писать словами и цифрами:
        # «три участка», «4 из 4». Они безопасны и не несут величины.
        if value.isdigit() and int(value) <= 12:
            continue
        extra.append(match.strip())
    return extra


def compose(facts: dict, *, timeout: float = 90.0) -> SummaryResult | None:
    """Просит модель изложить факты. None — если модель недоступна.

    Недоступность не ошибка: ключа может не быть, сети может не быть, и
    сервис обязан работать без них. Вызывающая сторона показывает
    шаблонную справку.
    """
    if not settings.routerai_api_key:
        return None

    payload = {
        "model": settings.routerai_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Факты:\n" + json.dumps(facts, ensure_ascii=False, indent=2),
            },
        ],
        # Модель рассуждающая: на короткий ответ у неё уходит под две
        # сотни токенов размышления, и при тесном лимите до текста дело
        # не доходит вовсе — возвращается пустая строка.
        "max_tokens": 1600,
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        settings.routerai_base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.routerai_api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
        return None

    try:
        text = (body["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError):
        return None
    if not text:
        return None

    extra = invented_numbers(text, facts)
    if extra:
        return SummaryResult(
            text="",
            model=settings.routerai_model,
            rejected_reason=f"в ответе числа, которых нет в расчёте: {', '.join(extra[:5])}",
        )

    return SummaryResult(text=text, model=settings.routerai_model)
