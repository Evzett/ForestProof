"""Расчёт по контуру и периоду — серверная обёртка над расчётным ядром.

KAN-51. Главное правило: здесь **нет ни одной формулы кейса**. Сервис
находит нужные растры, проверяет запрос и вызывает `tools.extract_case_data.
build_aoi` — тот же код, которым посчитан набор из четырёх участков.
Если бы формулы жили ещё и тут, два расчёта разошлись бы молча.

Почему именно `build_aoi`, а не сборка из отдельных функций ядра: он уже
принимает произвольную геометрию параметром `geometry` и собирает результат
в той же форме, что лежит в `case-data.json`. Фронт получает знакомую
структуру, а не вторую её версию.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


def _resolve_repo_root() -> Path:
    """Корень с ядром, инструментами и данными.

    Раскладка разная в репозитории и в образе: локально это `api/app/..`,
    а в контейнере api/ скопирован в /app, и тот же подъём на два уровня
    приводит в корень файловой системы. Поэтому проверяем по содержимому,
    а не по числу уровней.
    """
    env = os.environ.get("FORESTPROOF_ROOT")
    candidates = [Path(env)] if env else []
    candidates += [Path(__file__).resolve().parents[2], Path("/repo"), Path.cwd()]
    for candidate in candidates:
        if (candidate / "forestproof_core").is_dir() and (candidate / "data").is_dir():
            return candidate
    # Ничего не нашли — возвращаем первый кандидат, чтобы ошибка импорта
    # назвала конкретный путь, а не упала где-то глубже.
    return candidates[0]


REPO_ROOT = _resolve_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from forestproof_core.case_calculation import CaseCalculationConfig  # noqa: E402
from tools.extract_case_data import build_aoi  # noqa: E402

DATA_DIR = Path(os.environ.get("FORESTPROOF_DATA_DIR") or REPO_ROOT / "data")

# Границы запроса из постановки: период 2019–2024, площадь до 20 км².
YEAR_MIN, YEAR_MAX = 2019, 2024
MAX_AREA_HA = 2000.0


class CalculationError(Exception):
    """Запрос отклонён до расчёта. `reason` попадает на экран как есть."""

    def __init__(self, reason: str, *, status: int = 422) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


@dataclass(frozen=True, slots=True)
class CaseSet:
    areas: list[dict]
    baseline: list[dict]
    events: list[dict]
    config: CaseCalculationConfig
    geometries: dict[str, dict]


@lru_cache(maxsize=1)
def load_case_set() -> CaseSet:
    """Описания набора. Кэшируются: читаются с диска, меняются только вместе
    с самим набором."""

    def rows(path: Path) -> list[dict]:
        with open(path, encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))

    with open(DATA_DIR / "areas.geojson", encoding="utf-8-sig") as handle:
        geometries = {
            feature["properties"]["aoi_id"]: feature["geometry"]
            for feature in json.load(handle)["features"]
        }

    return CaseSet(
        areas=rows(DATA_DIR / "areas.csv"),
        baseline=rows(DATA_DIR / "methodology" / "baseline.csv"),
        events=rows(DATA_DIR / "events.csv"),
        config=CaseCalculationConfig.from_parameter_rows(rows(DATA_DIR / "methodology" / "parameters.csv")),
        geometries=geometries,
    )


def list_areas() -> list[dict]:
    """Участки набора для экрана выбора: имя, регион, роль, площадь."""
    case = load_case_set()
    return [
        {
            "aoi_id": meta["aoi_id"],
            "name": meta.get("name"),
            "region": meta.get("region"),
            "role": meta.get("selection_role"),
            "area_ha_declared": _as_float(meta.get("area_ha")),
            "bbox": [
                float(meta["bbox_west"]),
                float(meta["bbox_south"]),
                float(meta["bbox_east"]),
                float(meta["bbox_north"]),
            ],
        }
        for meta in case.areas
    ]


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def geometry_bbox(geometry: dict) -> tuple[float, float, float, float]:
    if geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise CalculationError("геометрия должна быть Polygon или MultiPolygon в WGS 84")
    polygons = (
        geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    )
    points = [point for polygon in polygons for ring in polygon for point in ring]
    if not points:
        raise CalculationError("в геометрии нет координат")
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    if not all(-180 <= lon <= 180 for lon in lons) or not all(-90 <= lat <= 90 for lat in lats):
        raise CalculationError("координаты вне диапазона WGS 84: ожидаются градусы широты и долготы")
    return min(lons), min(lats), max(lons), max(lats)


def covering_area(geometry: dict) -> dict | None:
    """Участок набора, чьи растры накрывают контур целиком.

    Нужен именно он: растры лежат по участкам, и контур, вылезающий за
    границу тайла, посчитается по обрезанным данным. Такой запрос честнее
    отклонить, чем посчитать наполовину.
    """
    west, south, east, north = geometry_bbox(geometry)
    for meta in load_case_set().areas:
        if (
            float(meta["bbox_west"]) <= west
            and float(meta["bbox_south"]) <= south
            and float(meta["bbox_east"]) >= east
            and float(meta["bbox_north"]) >= north
        ):
            return meta
    return None


def validate_request(geometry: dict, year_start: int, year_end: int) -> dict:
    """Проверки до расчёта (В-03, В-05). Возвращает метаданные участка."""
    if year_end <= year_start:
        raise CalculationError("конечный год должен быть больше начального")
    if not (YEAR_MIN <= year_start <= YEAR_MAX and YEAR_MIN <= year_end <= YEAR_MAX):
        raise CalculationError(f"период доступен только в диапазоне {YEAR_MIN}–{YEAR_MAX}")

    meta = covering_area(geometry)
    if meta is None:
        raise CalculationError(
            "контур выходит за пределы участков набора. Растры для него не скачаны, "
            "и расчёт по обрезанным данным дал бы неверное число",
            status=422,
        )
    return meta


def calculate(geometry: dict, year_start: int, year_end: int) -> dict:
    """Полный расчёт по контуру. Форма результата — как у участка набора."""
    meta = validate_request(geometry, year_start, year_end)
    case = load_case_set()

    area = build_aoi(
        DATA_DIR,
        meta,
        case.baseline,
        case.events,
        None,  # карты не рендерим на каждый запрос: это отдельный шаг
        case.config,
        geometry,
    )

    measured = area.get("area_ha")
    if measured is not None and measured > MAX_AREA_HA:
        raise CalculationError(
            f"площадь контура {measured:.0f} га превышает предел {MAX_AREA_HA:.0f} га "
            "(20 км² по условиям кейса)"
        )

    periods = [
        p for p in area.get("periods", [])
        if p.get("year_start") == year_start and p.get("year_end") == year_end
    ]
    if not periods:
        raise CalculationError(f"период {year_start}–{year_end} не посчитан по этому контуру")

    return {
        "aoi_id": meta["aoi_id"],
        "parent_area_name": meta.get("name"),
        "geometry_source": "запрос пользователя",
        "area_ha": measured,
        "series": area.get("series"),
        "cover_loss": area.get("cover_loss"),
        "stability": area.get("stability"),
        "period": periods[0],
        "baseline_id": meta.get("baseline_id"),
        "baseline_note": (
            "Базовая линия взята у участка набора, внутри которого лежит контур: "
            "удельная траектория родительского участка и фактическая площадь запроса"
        ),
        "status": "расчёт по условиям кейса, а не сертифицированные единицы",
    }
