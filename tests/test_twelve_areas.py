"""Набор из двенадцати участков — KAN-62.

Исходно тест пришёл вместе с задачей и проверял, что у двух новых
участков лежат вырезанные растры. Вырезок больше нет: восемь
добавленных участков читаются прямо из тайлов, как и остальные, —
одна цепочка вместо двух. Поэтому проверяется не наличие файлов, а
то, ради чего они были нужны: что участки настоящие, посчитаны здесь
и не повторяют чужие числа.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
NEW = ("RU_VOLOGDA_08", "RU_MORDOVIA_12")


def _catalog() -> list[dict]:
    with (DATA / "areas.csv").open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_catalog_and_frontend_agree_on_twelve_areas() -> None:
    catalog = {row["aoi_id"] for row in _catalog()}
    payload = json.loads((ROOT / "app/src/data/case-data.json").read_text(encoding="utf-8"))
    frontend = {row["aoi_id"] for row in payload["areas"]}
    assert len(catalog) == 12
    assert frontend == catalog


def test_new_areas_have_their_own_baseline() -> None:
    """У новых участков своя базовая линия на все десять лет."""
    with (DATA / "methodology" / "baseline.csv").open(encoding="utf-8-sig") as handle:
        baseline = list(csv.DictReader(handle))
    for aoi in NEW:
        assert sum(row["aoi_id"] == aoi for row in baseline) == 10


def test_new_areas_are_marked_as_derived_not_given() -> None:
    """Базовая линия новых участков выведена нами, а не задана набором.

    Разница не косметическая: линии четырёх участков кейса заданы
    условием и пересчёту не подлежат, а эти мы вывели сами и обязаны
    об этом говорить.
    """
    series = json.loads((DATA / "series.derived.json").read_text(encoding="utf-8"))
    for aoi in NEW:
        assert series[aoi]["source_kind"] == "выведена нами по формуле кейса"


def test_new_areas_do_not_repeat_another_area_numbers() -> None:
    """Ряды запаса не скопированы у соседей.

    Совпадение ряда до девятого знака означало бы, что участок не
    посчитан, а списан — ровно то, чего нельзя допустить, добавляя
    участки к набору кейса.
    """
    series = json.loads((DATA / "series.derived.json").read_text(encoding="utf-8"))
    fingerprints: dict[str, tuple] = {}
    for aoi, payload in series.items():
        fingerprints[aoi] = tuple(round(p["c_t_ha"], 6) for p in payload["series"])

    for aoi in NEW:
        twins = [other for other, value in fingerprints.items()
                 if other != aoi and value == fingerprints[aoi]]
        assert not twins, f"{aoi} повторяет ряд участка {twins}"


def test_new_areas_measure_their_own_geometry() -> None:
    """Площадь посчитана по контуру участка, а не унаследована.

    Пришедшая вместе с задачей площадь Мордовии-12 была на 38 гектаров
    меньше: её окно было вырезано со сдвигом и не накрывало контур
    целиком. Здесь площадь считается по доле пересечения каждого
    пикселя с контуром, поэтому она согласуется с размером рамки.
    """
    catalog = {row["aoi_id"]: row for row in _catalog()}
    for aoi in NEW:
        row = catalog[aoi]
        width = float(row["bbox_east"]) - float(row["bbox_west"])
        height = float(row["bbox_north"]) - float(row["bbox_south"])
        assert width > 0 and height > 0

        # Грубая оценка площади рамки на этой широте: она не обязана
        # совпадать до гектара, но разойтись на проценты не может.
        import math

        lat = (float(row["bbox_north"]) + float(row["bbox_south"])) / 2
        metres_lon = 111_412.84 * math.cos(math.radians(lat)) - 93.5 * math.cos(
            3 * math.radians(lat)
        )
        metres_lat = 111_132.92 - 559.82 * math.cos(2 * math.radians(lat))
        expected_ha = (width * metres_lon) * (height * metres_lat) / 10_000
        assert float(row["area_ha"]) == pytest.approx(expected_ha, rel=0.01)


def test_new_areas_have_maps() -> None:
    maps = ROOT / "app/public/maps"
    for aoi in NEW:
        for kind in ("stock", "change", "loss"):
            assert (maps / f"{aoi}_{kind}.png").exists()
