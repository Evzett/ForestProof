"""Detect spatial tree-cover-loss events inside an arbitrary GeoJSON AOI.

The detector deliberately keeps observation and interpretation separate:
Hansen ``lossyear`` confirms a loss of tree cover, but does not establish its
cause. Fire may only be attached later when an independent MODIS or Sentinel
dNBR check supports it.
"""

from __future__ import annotations

import argparse
import calendar
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    from .geotiff import Raster, read_geotiff
except ImportError:  # direct execution from tools/
    from geotiff import Raster, read_geotiff


TREECOVER_THRESHOLD = 30


def _ring_area(ring: list[list[float]]) -> float:
    return abs(
        sum(
            ring[i][0] * ring[(i + 1) % len(ring)][1]
            - ring[(i + 1) % len(ring)][0] * ring[i][1]
            for i in range(len(ring))
        )
    ) / 2


def _clip_edge(
    points: list[list[float]], axis: int, boundary: float, keep_greater: bool
) -> list[list[float]]:
    if not points:
        return []

    def inside(point: list[float]) -> bool:
        return point[axis] >= boundary if keep_greater else point[axis] <= boundary

    def intersection(start: list[float], end: list[float]) -> list[float]:
        delta = end[axis] - start[axis]
        if delta == 0:
            return start[:]
        ratio = (boundary - start[axis]) / delta
        return [
            boundary if axis == 0 else start[0] + ratio * (end[0] - start[0]),
            boundary if axis == 1 else start[1] + ratio * (end[1] - start[1]),
        ]

    output: list[list[float]] = []
    previous = points[-1]
    previous_inside = inside(previous)
    for current in points:
        current_inside = inside(current)
        if current_inside:
            if not previous_inside:
                output.append(intersection(previous, current))
            output.append(current[:])
        elif previous_inside:
            output.append(intersection(previous, current))
        previous, previous_inside = current, current_inside
    return output


def _clip_ring_to_pixel(
    ring: list[list[float]], west: float, south: float, east: float, north: float
) -> list[list[float]]:
    points = [list(point[:2]) for point in ring]
    for axis, boundary, keep_greater in (
        (0, west, True),
        (0, east, False),
        (1, south, True),
        (1, north, False),
    ):
        points = _clip_edge(points, axis, boundary, keep_greater)
    return points


def _polygons(geometry: dict) -> list[list[list[list[float]]]]:
    if geometry.get("type") == "Feature":
        geometry = geometry["geometry"]
    if geometry.get("type") == "Polygon":
        return [geometry["coordinates"]]
    if geometry.get("type") == "MultiPolygon":
        return geometry["coordinates"]
    raise ValueError("AOI must be a GeoJSON Polygon or MultiPolygon")


def polygon_weights(raster: Raster, geometry: dict) -> np.ndarray:
    """Return exact pixel/AOI intersection areas in hectares.

    Each polygon ring is clipped to each candidate raster cell. Interior rings
    are subtracted, so concave polygons, holes and multipolygons work without
    GDAL/Shapely and edge pixels are not rounded up to full cells.
    """
    polygons = _polygons(geometry)
    rows, cols = raster.data.shape[1:]
    fractions = np.zeros((rows, cols), dtype=float)

    all_points = [p for polygon in polygons for ring in polygon for p in ring]
    min_lon = min(p[0] for p in all_points)
    max_lon = max(p[0] for p in all_points)
    min_lat = min(p[1] for p in all_points)
    max_lat = max(p[1] for p in all_points)
    col_start = max(0, int(np.floor((min_lon - raster.lon_origin) / raster.lon_step)))
    col_end = min(cols, int(np.ceil((max_lon - raster.lon_origin) / raster.lon_step)))
    row_start = max(0, int(np.floor((raster.lat_origin - max_lat) / raster.lat_step)))
    row_end = min(rows, int(np.ceil((raster.lat_origin - min_lat) / raster.lat_step)))

    pixel_degree_area = raster.lon_step * raster.lat_step
    for row in range(row_start, row_end):
        north = raster.lat_origin - row * raster.lat_step
        south = north - raster.lat_step
        for col in range(col_start, col_end):
            west = raster.lon_origin + col * raster.lon_step
            east = west + raster.lon_step
            intersection_area = 0.0
            for polygon in polygons:
                outer = _clip_ring_to_pixel(polygon[0], west, south, east, north)
                area = _ring_area(outer) if len(outer) >= 3 else 0.0
                for hole in polygon[1:]:
                    clipped_hole = _clip_ring_to_pixel(hole, west, south, east, north)
                    if len(clipped_hole) >= 3:
                        area -= _ring_area(clipped_hole)
                intersection_area += max(area, 0.0)
            fractions[row, col] = min(max(intersection_area / pixel_degree_area, 0.0), 1.0)
    return fractions * raster.pixel_area_ha()


def _components(mask: np.ndarray) -> Iterable[list[tuple[int, int]]]:
    """Yield 8-connected components from a boolean raster mask."""
    seen = np.zeros(mask.shape, dtype=bool)
    rows, cols = mask.shape
    for start_row, start_col in zip(*np.where(mask & ~seen)):
        if seen[start_row, start_col]:
            continue
        component: list[tuple[int, int]] = []
        queue = deque([(int(start_row), int(start_col))])
        seen[start_row, start_col] = True
        while queue:
            row, col = queue.popleft()
            component.append((row, col))
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = row + dr, col + dc
                    if (
                        (dr or dc)
                        and 0 <= rr < rows
                        and 0 <= cc < cols
                        and mask[rr, cc]
                        and not seen[rr, cc]
                    ):
                        seen[rr, cc] = True
                        queue.append((rr, cc))
        yield component


def _component_geometry(raster: Raster, pixels: list[tuple[int, int]]) -> dict:
    coordinates = []
    for row, col in pixels:
        west = raster.lon_origin + col * raster.lon_step
        east = west + raster.lon_step
        north = raster.lat_origin - row * raster.lat_step
        south = north - raster.lat_step
        coordinates.append([[[west, south], [east, south], [east, north], [west, north], [west, south]]])
    return {"type": "MultiPolygon", "coordinates": coordinates}


@dataclass(frozen=True)
class DetectionConfig:
    treecover_threshold_pct: int = TREECOVER_THRESHOLD
    min_event_area_ha: float = 0.0


def detect_hansen_events(
    gfc: Raster | str | Path,
    geometry: dict,
    period_start: int,
    period_end: int,
    *,
    aoi_id: str = "CUSTOM_AOI",
    co2_stock_t_ha: float | dict[int, float] | None = None,
    config: DetectionConfig = DetectionConfig(),
) -> list[dict]:
    """Detect annual spatial loss events for an arbitrary polygon.

    Hansen identifies the year, not the day or causal episode. Consequently,
    all patches from one year are one observable event with ``patch_count``;
    presenting every disconnected pixel as a separate event would claim more
    temporal precision than the source contains.
    """
    if period_start > period_end:
        raise ValueError("period_start must not be later than period_end")
    raster = read_geotiff(str(gfc)) if isinstance(gfc, (str, Path)) else gfc
    if raster.data.shape[0] < 2:
        raise ValueError("GFC raster must contain treecover2000 and lossyear bands")

    weights = polygon_weights(raster, geometry)
    treecover = raster.band(0).astype(float)
    lossyear = raster.band(1).astype(int)
    forest = treecover >= config.treecover_threshold_pct
    events: list[dict] = []

    for year in range(max(2001, period_start), min(2025, period_end) + 1):
        active = (lossyear == year - 2000) & forest & (weights > 0)
        patches = list(_components(active))
        pixels = [pixel for patch in patches for pixel in patch]
        area_ha = float(sum(weights[row, col] for row, col in pixels))
        if not pixels or area_ha < config.min_event_area_ha:
            continue
        stock = (
            co2_stock_t_ha.get(year)
            if isinstance(co2_stock_t_ha, dict)
            else co2_stock_t_ha
        )
        exposure = area_ha * stock if stock is not None else None
        events.append(
            {
                    "event_id": f"{aoi_id}-HANSEN-{year}",
                    "aoi_id": aoi_id,
                    "year": year,
                    "date_min": f"{year}-01-01",
                    "date_max": f"{year}-12-31",
                    "date_uncertainty_days": 365 if calendar.isleap(year) else 364,
                    "area_ha": area_ha,
                    "pixel_count": len(pixels),
                    "patch_count": len(patches),
                    "event_type": "tree_cover_loss",
                    "observation_status": "подтверждена потеря древесного покрова по Hansen",
                    "cause_status": "причина не установлена",
                    "cause_supported": False,
                    "confidence": "annual_product",
                    "estimated_carbon_exposure_tco2e": exposure,
                    "contribution_method": (
                        "Оценка площади события × запас CO₂-экв. на гектар; "
                        "не независимое измерение выброса и не прибавляется к изменению запаса."
                        if exposure is not None
                        else None
                    ),
                    "geometry": _component_geometry(raster, pixels),
                    "source": "Hansen Global Forest Change v1.13 lossyear",
                    "limitations": (
                        "Продукт задаёт год потери покрова, но не точную дату и не причину события."
                    ),
                }
        )
    return events


def _select_geometry(document: dict, aoi_id: str | None) -> tuple[dict, str]:
    if document.get("type") != "FeatureCollection":
        if document.get("type") == "Feature":
            properties = document.get("properties", {})
            return document["geometry"], aoi_id or properties.get("aoi_id", "CUSTOM_AOI")
        return document, aoi_id or "CUSTOM_AOI"
    features = document.get("features", [])
    if aoi_id is not None:
        features = [f for f in features if f.get("properties", {}).get("aoi_id") == aoi_id]
    if len(features) != 1:
        raise ValueError("GeoJSON FeatureCollection must resolve to exactly one feature")
    feature = features[0]
    selected_id = aoi_id or feature.get("properties", {}).get("aoi_id", "CUSTOM_AOI")
    return feature["geometry"], selected_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gfc", required=True, type=Path, help="GFC GeoTIFF clip/tile")
    parser.add_argument("--geojson", required=True, type=Path, help="AOI GeoJSON")
    parser.add_argument("--aoi-id", help="feature aoi_id and output identifier")
    parser.add_argument("--start", required=True, type=int, help="first analysis year")
    parser.add_argument("--end", required=True, type=int, help="last analysis year")
    parser.add_argument("--co2-stock-t-ha", type=float, help="stock used for exposure estimate")
    parser.add_argument("--min-area-ha", type=float, default=0.0)
    parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    args = parser.parse_args()

    document = json.loads(args.geojson.read_text(encoding="utf-8"))
    geometry, selected_id = _select_geometry(document, args.aoi_id)
    events = detect_hansen_events(
        args.gfc,
        geometry,
        args.start,
        args.end,
        aoi_id=selected_id,
        co2_stock_t_ha=args.co2_stock_t_ha,
        config=DetectionConfig(min_event_area_ha=args.min_area_ha),
    )
    result = json.dumps({"aoi_id": selected_id, "events": events}, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(result, encoding="utf-8")
    else:
        print(result)


if __name__ == "__main__":
    main()
