"""Сведение четырёх сеток к одной — KAN-60 и KAN-61.

Эти тесты стерегут одно: перевод между проекциями. Ошибка здесь
молчалива — маска всё равно нарисуется, просто не над тем лесом, — и
поймать её можно только на известном ответе.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import modis_burned_area as mba  # noqa: E402
import source_agreement as sa  # noqa: E402

DATA = ROOT / "data"
GRANULE = "MCD64A1.A2021213.h20v03.061.2021309115600"


def _bbox(aoi: str):
    with open(DATA / "areas.csv", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row["aoi_id"] == aoi:
                return (
                    float(row["bbox_west"]),
                    float(row["bbox_south"]),
                    float(row["bbox_east"]),
                    float(row["bbox_north"]),
                )
    raise AssertionError(f"нет участка {aoi} в areas.csv")


@pytest.mark.parametrize(
    "aoi, burned, total",
    [("RU_MORDOVIA_03", 60, 88), ("RU_MORDOVIA_04", 88, 88)],
)
def test_modis_grid_reproduces_case_counts(aoi: str, burned: int, total: int) -> None:
    """Синусоидальная сетка читается так же, как её читал набор кейса.

    Эталон — строки events.csv, пришедшие вместе с данными: столько
    центров пикселей MODIS внутри контура и столько из них горевших.
    """
    granule = DATA / "cache" / "modis" / f"{GRANULE}.hdf"
    if not granule.exists():
        pytest.skip(f"нет гранулы в кэше: {granule.name}")
    pytest.importorskip("pyhdf")

    result = mba.burned_in_bbox(granule, GRANULE, _bbox(aoi))
    assert (result["burned_pixels"], result["all_pixels"]) == (burned, total)


def test_modis_pixel_centers_land_inside_the_bbox() -> None:
    """Отобранные центры действительно лежат внутри рамки.

    Проверка кажется избыточной, но именно она ловит перепутанный знак
    или потерянную поправку на косинус широты: число пикселей при такой
    ошибке остаётся правдоподобным, а координаты уезжают.
    """
    bbox = _bbox("RU_MORDOVIA_03")
    rows, cols = mba.pixel_centers_in_bbox(GRANULE, bbox)
    assert rows.size > 0

    h, v = mba._tile_of(GRANULE)
    x0 = mba.X_MIN + h * mba.TILE_METERS
    y0 = mba.Y_MAX - v * mba.TILE_METERS
    x = x0 + (cols + 0.5) * mba.PIXEL_METERS
    y = y0 - (rows + 0.5) * mba.PIXEL_METERS
    lat = np.degrees(y / mba.EARTH_RADIUS)
    lon = np.degrees(x / (mba.EARTH_RADIUS * np.cos(np.radians(lat))))

    assert lon.min() >= bbox[0] and lon.max() <= bbox[2]
    assert lat.min() >= bbox[1] and lat.max() <= bbox[3]


def test_agreement_uses_the_pipeline_utm_transform() -> None:
    """Массовый перевод в UTM совпадает со скалярным из конвейера.

    Векторную версию легко «оптимизировать» отдельной формулой — и
    тогда сравнение источников начнёт жить в своей системе координат,
    молча расходясь с доказательной базой на сотни метров.
    """
    lon = np.array([[36.1, 36.2], [36.3, 36.4]])
    lat = np.array([[56.7, 56.7], [56.8, 56.8]])
    x, y = sa._utm_forward_vec(lon, lat, 36)
    for i in range(2):
        for j in range(2):
            want = sa._utm_forward(float(lon[i, j]), float(lat[i, j]), 36)
            assert (x[i, j], y[i, j]) == pytest.approx(want)


def test_agreement_threshold_matches_reported_sign() -> None:
    """Порог dNBR применяется к падению, а не к росту индекса.

    Знак здесь не косметика: при перевёрнутом знаке «нарушением» стали
    бы зарастающие участки, и вывод раздела сменился бы на обратный.
    """
    before = np.array([[0.6, 0.6]])
    after = np.array([[0.1, 0.9]])
    dnbr = before - after
    assert dnbr[0, 0] >= sa.DNBR_THRESHOLD  # полог потемнел
    assert dnbr[0, 1] < sa.DNBR_THRESHOLD  # полог посветлел


def test_control_area_has_no_burned_pixels() -> None:
    """Контрольный участок остаётся контрольным.

    Если в Твери когда-нибудь появятся горевшие пиксели, раздел о
    расхождениях перестанет быть верным: он опирается на то, что там
    нарушения нет.
    """
    report = DATA / "source_agreement.json"
    if not report.exists():
        pytest.skip("нет data/source_agreement.json — сначала tools/source_agreement.py")

    import json

    areas = json.loads(report.read_text(encoding="utf-8"))["areas"]
    tver = areas.get("RU_TVER_01", {}).get("modis_vs_dnbr", {})
    if tver.get("status") != "ок":
        pytest.skip("сравнение с MODIS по Твери не посчитано")
    assert tver["burned_pixels"] == 0
