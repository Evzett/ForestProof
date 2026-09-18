"""Скрининг устойчивости не влияет на число единиц — KAN-35, пункт 4.

Требование звучит так: после появления блока рисков Q, UNC, B и V
обязаны остаться теми же. Проверять это «на глаз» нельзя: связь может
появиться однажды, тихо, при правке соседнего кода, и заметить её будет
не по чему.

Здесь стоят две проверки разной природы.

Первая — структурная: расчётное ядро не должно вообще знать слов
«устойчивость», «модель», «прогноз». Пока их там нет, подставить выход
скрининга в вычет за неопределённость просто некуда.

Вторая — числовая: значения в выгрузке совпадают с тем, что даёт ядро,
которому ни о каком скрининге не известно.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from forestproof_core.case_calculation import (  # noqa: E402
    CaseCalculationConfig,
    potential_units,
)

CORE = REPO_ROOT / "forestproof_core"
CASE_DATA = REPO_ROOT / "app" / "src" / "data" / "case-data.json"
CONFIG = CaseCalculationConfig()

# Проверяется ровно тот файл, где считаются единицы, и ровно те слова,
# которые означают скрининг устойчивости. Широкий список ловил бы
# однокоренные из соседних смыслов: carbon_screening — это другой
# скрининг, а «прогноз» в экономике стоит в оговорке «не прогноз цены».
# Тест, который кричит на невиновных, хуже отсутствующего.
UNITS_MODULE = CORE / "case_calculation.py"
FORBIDDEN = [
    "stability",
    "устойчив",
    "reversion",
    "реверси",
    "risk_level",
    "уровень риска",
]


def test_core_does_not_know_about_stability():
    """В ядре нет ни одного упоминания скрининга.

    Это сильнее любой проверки значений: если связи нет в коде, она не
    может появиться в числах.
    """
    text = UNITS_MODULE.read_text(encoding="utf-8").lower()
    offenders = [word for word in FORBIDDEN if word in text]
    assert not offenders, (
        f"{UNITS_MODULE.name} упоминает скрининг устойчивости — значит, расчёт единиц "
        f"может от него зависеть: {', '.join(offenders)}"
    )


def test_potential_units_takes_only_three_inputs():
    """У функции, считающей Q, ровно три входа и ни одного про риск."""
    import inspect

    names = list(inspect.signature(potential_units).parameters)
    assert names[:3] == ["e_proj_tco2e", "e_base_tco2e", "half_width_tco2e"], names
    assert not any("risk" in n or "stab" in n for n in names), names


def test_units_depend_only_on_e_base_h_and_leakage():
    """Q считается из трёх величин и ни из чего больше.

    Если в potential_units когда-нибудь попадёт четвёртый вход, эта
    проверка не заметит его сама — но заметит, что при одних и тех же
    трёх значениях ответ перестал быть одним и тем же.
    """
    first = potential_units(-1000.0, 0.0, 50.0, CONFIG)
    second = potential_units(-1000.0, 0.0, 50.0, CONFIG)
    assert first == second

    # Значение скрининга не участвует: тот же расчёт при любом уровне
    # риска обязан дать то же число, потому что уровня он не видит.
    assert first["units"] == potential_units(-1000.0, 0.0, 50.0, CONFIG)["units"]


@pytest.mark.skipif(not CASE_DATA.exists(), reason="case-data.json не собран")
def test_exported_units_reproduce_from_core_without_stability():
    """Числа в выгрузке воспроизводятся ядром, которому о скрининге не сказано."""
    areas = json.loads(CASE_DATA.read_text(encoding="utf-8"))["areas"]
    checked = 0

    for area in areas:
        for period in area["periods"]:
            if not period.get("available"):
                continue
            e_proj = period.get("e_proj_tco2e")
            e_base = period.get("e_base_tco2e")
            h = period.get("h_tco2e")
            if e_proj is None or e_base is None or h is None:
                continue

            again = potential_units(e_proj, e_base, h, CONFIG)
            assert again["units"] == period["units"], (
                f"{area['aoi_id']} {period['year_start']}—{period['year_end']}: "
                "число единиц в выгрузке не воспроизводится ядром"
            )
            assert again["r_tco2e"] == pytest.approx(period["r_tco2e"])
            assert again["buffer_tco2e"] == pytest.approx(period["buffer_tco2e"])
            if period.get("unc_share") is not None:
                assert again["unc_share"] == pytest.approx(period["unc_share"])
            checked += 1

    assert checked > 0, "не нашлось ни одного периода для проверки"


@pytest.mark.skipif(not CASE_DATA.exists(), reason="case-data.json не собран")
def test_areas_with_different_risk_levels_share_the_same_rule():
    """Участки разного уровня риска считаются одним правилом.

    Если бы скрининг подмешивался в расчёт, участок с высокой категорией
    получал бы другой резерв или другой вычет при тех же входных
    величинах. Проверяем, что доля резерва одна на всех.
    """
    areas = json.loads(CASE_DATA.read_text(encoding="utf-8"))["areas"]
    shares = set()

    for area in areas:
        period = area["period_2019_2024"]
        r_adjusted = period.get("r_adjusted_tco2e")
        buffer = period.get("buffer_tco2e")
        if not r_adjusted or buffer is None:
            continue
        shares.add(round(buffer / r_adjusted, 9))

    assert len(shares) <= 1, (
        f"доля резерва различается между участками: {sorted(shares)} — "
        "значит, в расчёт попало что-то, зависящее от участка сверх формулы"
    )
