"""Раздел 12, `POST /api/plots/validate` — проверки геометрии шага 2 мастера.

Только GeoJSON (Polygon/MultiPolygon, EPSG:4326). Шейп-файлы и другие форматы
загрузки на хакатон не входят — увеличивают объём разбора без влияния на
приёмку (контракт требует именно проверки из раздела 12, не поддержку формата).
"""

import math
from typing import Any

from shapely.geometry import shape
from shapely.validation import explain_validity

EARTH_RADIUS_M = 6_371_000.0
MAX_AREA_HA = 2_000.0


def parse_uploaded_geometry(raw: dict) -> dict:
    """Достаёт geometry из Feature/FeatureCollection/голой geometry.
    Бросает ValueError с понятным текстом, если структура неожиданная —
    вызывающий код превращает это в чек `geometry_type: ok=false`."""
    if raw.get("type") == "FeatureCollection":
        features = raw.get("features") or []
        if len(features) != 1:
            raise ValueError("ожидается ровно один Feature с границей участка")
        return features[0]["geometry"]
    if raw.get("type") == "Feature":
        return raw["geometry"]
    return raw


def area_ha_equirectangular(geom_dict: dict) -> float:
    """Площадь в гектарах, приближение равнопромежуточной проекцией вокруг
    центроида — точность достаточна для превью и предварительной проверки
    (не для расчётного ядра Р3, которое использует Earth Engine)."""
    geom = shape(geom_dict)
    centroid_lat_rad = math.radians(geom.centroid.y)
    m_per_deg_lon = (math.pi / 180) * EARTH_RADIUS_M * math.cos(centroid_lat_rad)
    m_per_deg_lat = (math.pi / 180) * EARTH_RADIUS_M
    area_deg2 = geom.area  # площадь в квадратных градусах
    area_m2 = area_deg2 * m_per_deg_lon * m_per_deg_lat
    return abs(area_m2) / 10_000.0


def run_geometry_checks(geom_dict: dict) -> tuple[list[dict], bool, float]:
    """Возвращает (checks, accepted, area_ha) — раздел 12: `ok` = true/false/"warn",
    предупреждение не блокирует, `false` блокирует (`accepted=false`)."""
    checks: list[dict] = []
    accepted = True
    area_ha = 0.0

    gtype = geom_dict.get("type")
    if gtype in ("Polygon", "MultiPolygon"):
        checks.append({"name": "geometry_type", "ok": True, "value": gtype})
    else:
        checks.append({"name": "geometry_type", "ok": False, "value": gtype or "не распознан"})
        accepted = False
        # Без валидного типа geometry дальнейшие геометрические проверки бессмысленны.
        checks.append({"name": "crs", "ok": False, "value": "не удалось прочитать координаты"})
        checks.append({"name": "self_intersections", "ok": False, "value": "не проверено"})
        checks.append({"name": "area_ha", "ok": False, "value": None})
        return checks, accepted, area_ha

    try:
        coords_flat = _flatten_coords(geom_dict)
    except (TypeError, ValueError, IndexError) as exc:
        checks.append({"name": "coordinates", "ok": False, "value": f"не удалось прочитать: {exc}"})
        return checks, False, area_ha
    if not coords_flat:
        checks.append({"name": "coordinates", "ok": False, "value": "координаты отсутствуют"})
        return checks, False, area_ha
    in_lonlat_range = all(-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0 for lon, lat in coords_flat)
    checks.append(
        {"name": "crs", "ok": bool(in_lonlat_range), "value": "EPSG:4326" if in_lonlat_range else "координаты вне диапазона lon/lat"}
    )
    if not in_lonlat_range:
        accepted = False

    geom = shape(geom_dict)
    if geom.is_empty:
        checks.append({"name": "geometry_empty", "ok": False, "value": "пустая геометрия"})
        accepted = False
    if geom.is_valid:
        checks.append({"name": "self_intersections", "ok": True, "value": "не найдены"})
    else:
        checks.append({"name": "self_intersections", "ok": False, "value": explain_validity(geom)})
        accepted = False

    area_ha = round(area_ha_equirectangular(geom_dict), 1)
    area_ok = 0 < area_ha <= MAX_AREA_HA
    checks.append(
        {
            "name": "area_ha",
            "ok": area_ok,
            "value": area_ha,
            "limit_ha": MAX_AREA_HA,
        }
    )
    if not area_ok:
        accepted = False

    return checks, accepted, area_ha


def _flatten_coords(geom_dict: dict) -> list[tuple[float, float]]:
    gtype = geom_dict.get("type")
    coords = geom_dict.get("coordinates")
    rings: list[list[Any]] = []
    if gtype == "Polygon":
        rings = coords
    elif gtype == "MultiPolygon":
        rings = [ring for part in coords for ring in part]
    return [(pt[0], pt[1]) for ring in rings for pt in ring]
