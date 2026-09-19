"""Сторож справки: знак — не часть числа.

Сторож отбраковывает ответ модели, если в нём есть величина, которой
нет в расчёте. Пока он считал минус частью числа, корректный ответ про
отрицательный результат отбрасывался целиком: в фактах −6485, модель
пишет «потеря 6485», направление сказано словом. Справка при этом
молча откатывалась к шаблону — и именно там, где результат
отрицательный, то есть почти везде.

Эти тесты стерегут обе стороны: знак прощается, выдумка — нет.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app.summary_ai import allowed_numbers, invented_numbers  # noqa: E402

FACTS = {
    "период": "2019—2024",
    "результат_tco2e": -6485,
    "наибольшая_потеря_tco2e": 126074,
    "потенциальные_единицы": 0,
    "площадь_га": 1750.5,
}


@pytest.mark.parametrize(
    "text",
    [
        "Результат за 2019—2024 составил 6485 т CO₂-экв.",
        "Результат 6 485 т CO₂-экв.",  # с узким неразрывным пробелом
        "Результат −6485 т CO₂-экв.",  # с типографским минусом
        "Результат -6485 т CO₂-экв.",
    ],
)
def test_sign_and_spacing_do_not_make_a_number_invented(text: str) -> None:
    assert invented_numbers(text, FACTS) == []


def test_invented_value_is_still_caught() -> None:
    """Главное свойство сторожа не должно пострадать от послабления."""
    assert invented_numbers("Потеря составила 9 999 т CO₂-экв.", FACTS) == ["9 999"]


def test_recomputed_value_is_caught() -> None:
    """Пересчёт — тоже выдумка: модели дано излагать, а не считать."""
    assert invented_numbers("В сумме 132 559 т CO₂-экв.", FACTS) == ["132 559"]


def test_small_counting_numbers_are_allowed() -> None:
    """«3 из 4» модель вправе написать цифрами: величины в этом нет."""
    assert invented_numbers("Единиц нет ни на одном из 4 участков.", FACTS) == []


def test_allowed_numbers_keeps_magnitudes_without_sign() -> None:
    allowed = allowed_numbers(FACTS)
    assert "6485" in allowed
    assert "1750.5" in allowed
    assert "2019" in allowed and "2024" in allowed
