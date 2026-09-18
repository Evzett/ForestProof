"""Сборка ряда и базовой линии из открытых тайлов.

Расширенный набор пришёл без растров и без базовой линии — только
контуры. Значит, всё это надо вывести из тайлов, которые мы и так
качаем. Вопрос один: даёт ли такая сборка те же числа, что лежат в
самом кейсе.

Ответ проверяется здесь. Четыре исходных участка есть и в наборе, и в
тайлах; если по ним сходится, выведенной базовой линии для остальных
восьми можно верить. Если нет — нельзя, и тогда неважно, что код
запускается.
"""

import csv
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

CACHE = REPO_ROOT / "data" / "cache" / "cci-biomass"
BASELINE = REPO_ROOT / "data" / "methodology" / "baseline.csv"
AREAS = REPO_ROOT / "data" / "areas.csv"

needs_tiles = pytest.mark.skipif(
    not (CACHE.exists() and BASELINE.exists() and AREAS.exists()),
    reason="тайлы весят гигабайты и в Git не хранятся",
)


def _rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _box(meta: dict) -> tuple[float, float, float, float]:
    return (
        float(meta["bbox_west"]),
        float(meta["bbox_south"]),
        float(meta["bbox_east"]),
        float(meta["bbox_north"]),
    )


@needs_tiles
@pytest.mark.parametrize("year,field", [(2015, "reference_mean_2015_tc_ha"), (2019, "reference_mean_2019_tc_ha")])
def test_stock_from_tile_matches_the_case(year, field):
    """Запас, посчитанный по тайлу, равен запасу из набора.

    Это и есть ключевая проверка всей затеи: тайл с CEDA и вложенный в
    набор файл — один и тот же продукт, и если наше окно читается
    правильно, числа обязаны совпасть.
    """
    import build_area_from_tiles as builder

    baseline = _rows(BASELINE)
    areas = {a["aoi_id"]: a for a in _rows(AREAS)}

    checked = 0
    for aoi, meta in areas.items():
        reference = next((r for r in baseline if r["aoi_id"] == aoi), None)
        if reference is None:
            continue
        try:
            mine = builder.read_year_from_tile(_box(meta), year)["c_t_ha"]
        except SystemExit:
            continue  # тайла этого региона нет в кэше
        assert mine == pytest.approx(float(reference[field]), abs=builder.TOLERANCE_TC_HA)
        checked += 1

    if checked == 0:
        pytest.skip("ни одного тайла нужных регионов в кэше нет")


@needs_tiles
def test_derived_rate_matches_the_case():
    """Историческая динамика g, выведенная по формуле, равна заданной.

    g выводится из тех же двух средних, что лежат в наборе, поэтому
    совпадение здесь проверяет не арифметику, а то, что формула из
    документа 06 прочитана верно.
    """
    import build_area_from_tiles as builder

    baseline = _rows(BASELINE)
    areas = {a["aoi_id"]: a for a in _rows(AREAS)}

    checked = 0
    for aoi, meta in areas.items():
        reference = next((r for r in baseline if r["aoi_id"] == aoi), None)
        if reference is None:
            continue
        try:
            means = {
                y: builder.read_year_from_tile(_box(meta), y)["c_t_ha"]
                for y in (builder.BASELINE_START, builder.BASELINE_ANCHOR)
            }
        except SystemExit:
            continue
        derived = builder.baseline_for(means)
        assert derived["rate"] == pytest.approx(
            float(reference["historical_rate_tc_ha_yr"]), abs=0.005
        )
        checked += 1

    if checked == 0:
        pytest.skip("ни одного тайла нужных регионов в кэше нет")


@needs_tiles
def test_negative_rate_is_not_flattened():
    """Падающая динамика остаётся падающей.

    Соблазн подтянуть отрицательное g к нулю велик: с ним базовая линия
    падает, и «потеря без проекта» выходит больше фактической. Но кейс
    требует обрезать нулём сам запас, а не скорость, и Мордовия-03 с
    g = −2,481 — прямое тому подтверждение в самом наборе.
    """
    import build_area_from_tiles as builder

    reference = next(r for r in _rows(BASELINE) if r["aoi_id"] == "RU_MORDOVIA_03")
    rate = float(reference["historical_rate_tc_ha_yr"])
    assert rate < 0

    base = builder.baseline_for({2015: 46.34, 2019: 36.42})
    assert base["rate"] < 0
    # Запас обрезается нулём, а не разворачивается вверх.
    assert base["stock"](2100) == 0.0
    assert base["stock"](2020) < base["stock"](2019)
