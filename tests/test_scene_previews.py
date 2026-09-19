"""Превью снимка: яркость поднимается, цвет остаётся.

Превью собирается для показа, и обработка у него ровно одна —
растяжка контраста. Важно, чтобы она не превращалась в раскрашивание:
если растягивать каждый канал по своим процентилям, соотношение между
ними меняется, и лес выходит фиолетовым. Снимки, вложенные в набор,
именно такие.

Общий множитель на три канала меняет яркость, а не цвет. Эти тесты
стерегут это свойство — его легко потерять «оптимизацией».
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from scene_previews import stretch  # noqa: E402


def _bands(red: float, green: float, blue: float, size: int = 8):
    """Ровное поле одного цвета плюс тёмный и светлый край для процентилей."""
    base = np.full((size, size), 0.0)
    out = []
    for value in (red, green, blue):
        band = base + value
        band[0, 0] = value * 0.4
        band[-1, -1] = value * 1.8
        out.append(band)
    return out


def test_channel_ratios_survive_the_stretch() -> None:
    """Главное свойство: отношение каналов не меняется.

    Лес зелёный потому, что в нём зелёного больше, чем синего. Если
    растяжка это отношение переписывает, на снимке будет не лес, а
    мнение о нём.
    """
    red, green, blue = 900.0, 1400.0, 600.0
    result = stretch(_bands(red, green, blue))

    centre = result[4, 4]
    assert centre[1] > centre[0] > centre[2], "порядок каналов перевернулся"

    # Растяжка сдвигает и делит, поэтому исходное отношение каналов не
    # сохраняется буквально. Проверяется то, что должно сохраняться:
    # зелёный остаётся заметно выше синего, а не сравнивается с ним.
    # Через отношение это не проверить — тёмный канал после клипа может
    # стать нулём, и деление даст бесконечность, то есть «тест прошёл»
    # там, где смотреть уже не на что.
    gap_before = (green - blue) / max(red, green, blue)
    gap_after = float(centre[1] - centre[2])
    assert gap_after > 0.2, (
        f"зелёный сравнялся с синим: разрыв был {gap_before:.2f}, стал {gap_after:.2f}"
    )


def test_per_channel_stretch_would_flatten_the_colour() -> None:
    """Проверка от противного: так делать нельзя.

    Тест показывает, что именно ломается при поканальной растяжке —
    чтобы через полгода никто не «упростил» код обратно.
    """
    red, green, blue = 900.0, 1400.0, 600.0
    bands = _bands(red, green, blue)

    per_channel = []
    for band in bands:
        values = band[band > 0]
        low, high = np.percentile(values, [2, 98])
        per_channel.append(np.clip((band - low) / max(high - low, 1e-6), 0, 1))
    flattened = np.dstack(per_channel)[4, 4]

    assert abs(flattened[1] - flattened[2]) < 0.05, (
        "поканальная растяжка должна была сравнять каналы — иначе тест бессмысленен"
    )


def test_result_is_bounded() -> None:
    result = stretch(_bands(900.0, 1400.0, 600.0))
    assert result.min() >= 0.0 and result.max() <= 1.0


def test_empty_window_does_not_crash() -> None:
    """Окно за краем снимка — нули. Это не ошибка, это край данных."""
    empty = [np.zeros((4, 4)) for _ in range(3)]
    result = stretch(empty)
    assert result.shape == (4, 4, 3)
    assert not result.any()
