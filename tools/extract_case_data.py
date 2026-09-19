"""Считает по растрам кейса всё, что показывает сервис, и кладёт в JSON.

Запуск:
    python tools/extract_case_data.py --data <каталог data> --out app/src/data/case-data.json

Почему отдельным скриптом: расчёт детерминированный и зависит только от
файлов набора, поэтому его результат можно зафиксировать и воспроизвести
без запущенного бэкенда. Тот же код потом вызывается из API на произвольном
контуре — формулы здесь, а не в интерфейсе.

Проверка: средние запасы 2015 и 2019 годов, посчитанные этим скриптом,
совпадают с reference_mean_*_tc_ha из methodology/baseline.csv до шестого
знака. Это и есть подтверждение, что площадное взвешивание и перевод
в углерод сделаны так же, как их задумывал автор кейса.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
import math
from pathlib import Path
import sys

import numpy as np

# Keep the documented direct invocation (python tools/extract_case_data.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from forestproof_core.case_calculation import (  # noqa: E402
    CaseCalculationConfig,
    baseline_stock_by_year,
    calculate_period,
    calculate_year,
    carbon_density_t_ha,
    pixel_intersection_weights,
    potential_units,
    sigma_from_sums,
    uncertainty_half_width,
)
from forestproof_core.scenario_economics import (  # noqa: E402
    ScenarioEconomicsConfig,
    calculate_scenario_value,
)
from forestproof_core.summary_generator import generate_summary  # noqa: E402
from tools.fetch import _tile_name_cci, _tile_name_gfc, cci_url  # noqa: E402
from tools.geotiff import read_geotiff
from tools.sentinel_evidence import build_event_evidence, build_period_evidence

# ---------------------------------------------------------------- параметры

CONFIG = CaseCalculationConfig()

# Порог древесного покрова для маски GFC: доля кроны на 2000 год
TREECOVER_THRESHOLD = 30

# ------------------------------------------------------- источники растров --

# Участки кейса приходят с вырезанными растрами внутри `data/<AOI>/`.
# Участки, добавленные нами, приходят только контуром, и те же самые
# продукты для них читаются окном из тайла в кэше.
#
# Числа от этого не меняются: тайл и вложенный файл — один и тот же
# продукт, и по четырём участкам кейса они совпадают до шестого знака
# (см. tools/build_area_from_tiles.py и tests/test_area_from_tiles.py).
# Но версия продукта гарей отличается, поэтому источник каждого слоя
# пишется в выгрузку: на экране должно быть видно, откуда взято.

CCI_CACHE = Path("data/cache/cci-biomass")
GFC_CACHE = Path("data/cache/hansen-gfc")
GFC_TILE_VERSION = "Hansen GFC v1.12 (тайл)"
GFC_LOCAL_VERSION = "Hansen GFC v1.13 (вложен в набор)"


@dataclass(frozen=True, slots=True)
class YearRaster:
    """Биомасса и её погрешность за год плюс сетка, по которой считать вес."""

    agb: np.ndarray
    sd: np.ndarray
    grid: object
    source: str


@dataclass(frozen=True, slots=True)
class CoverRaster:
    """Сомкнутость крон на 2000 год и год потери покрова."""

    treecover: np.ndarray
    lossyear: np.ndarray
    grid: object
    source: str


def _bounds(box) -> tuple[float, float, float, float]:
    """Рамка запроса. Контур приходит то четвёркой чисел, то геометрией
    GeoJSON — тайл выбирается одинаково и по той, и по другой."""
    if isinstance(box, dict):
        lons: list[float] = []
        lats: list[float] = []

        def walk(node) -> None:
            if (
                isinstance(node, (list, tuple))
                and len(node) >= 2
                and all(isinstance(v, (int, float)) for v in node[:2])
            ):
                lons.append(float(node[0]))
                lats.append(float(node[1]))
                return
            if isinstance(node, (list, tuple)):
                for item in node:
                    walk(item)

        walk(box.get("coordinates", []))
        if not lons:
            raise ValueError("в геометрии нет координат")
        return min(lons), min(lats), max(lons), max(lats)
    return float(box[0]), float(box[1]), float(box[2]), float(box[3])


def _centre(box) -> tuple[float, float]:
    west, south, east, north = _bounds(box)
    return (west + east) / 2, (south + north) / 2


def open_cci(data_dir: Path, aoi: str, year: int, box) -> YearRaster:
    local = data_dir / aoi / f"CCI_Biomass_{year}.tif"
    if local.exists():
        raster = read_geotiff(str(local))
        agb = raster.band(0).astype(float)
        sd = raster.band(1).astype(float)
        if raster.nodata is not None:
            agb[agb == raster.nodata] = np.nan
            sd[sd == raster.nodata] = np.nan
        return YearRaster(agb, sd, raster, "вложен в набор")

    lon, lat = _centre(box)
    tile = _tile_name_cci(lon, lat)
    agb_path = CCI_CACHE / cci_url(tile, year, "AGB").rsplit("/", 1)[-1]
    sd_path = CCI_CACHE / cci_url(tile, year, "AGB_SD").rsplit("/", 1)[-1]
    for path in (agb_path, sd_path):
        if not path.exists():
            raise FileNotFoundError(
                f"нет ни {local}, ни тайла {path.name}; "
                "сначала: python tools/fetch.py --bbox <W S E N> --years ..."
            )

    window = _bounds(box)
    agb_raster = read_geotiff(str(agb_path), bbox=window)
    sd_raster = read_geotiff(str(sd_path), bbox=window)
    agb = agb_raster.band(0).astype(float)
    sd = sd_raster.band(0).astype(float)
    if agb_raster.nodata is not None:
        agb[agb == agb_raster.nodata] = np.nan
    if sd_raster.nodata is not None:
        sd[sd == sd_raster.nodata] = np.nan
    return YearRaster(agb, sd, agb_raster, f"тайл {tile}")


def open_gfc(data_dir: Path, aoi: str, box) -> CoverRaster:
    local = data_dir / aoi / "GFC_2025_v1_13.tif"
    if local.exists():
        raster = read_geotiff(str(local))
        return CoverRaster(
            raster.band(0).astype(float),
            raster.band(1).astype(int),
            raster,
            GFC_LOCAL_VERSION,
        )

    lon, lat = _centre(box)
    tile = _tile_name_gfc(lon, lat)
    loss_path = GFC_CACHE / f"Hansen_GFC-2024-v1.12_lossyear_{tile}.tif"
    cover_path = GFC_CACHE / f"Hansen_GFC-2024-v1.12_treecover2000_{tile}.tif"
    for path in (loss_path, cover_path):
        if not path.exists():
            raise FileNotFoundError(
                f"нет ни {local}, ни тайла {path.name}; "
                "сначала: python tools/fetch.py --bbox <W S E N> --cover"
            )

    window = _bounds(box)
    loss = read_geotiff(str(loss_path), bbox=window)
    cover = read_geotiff(str(cover_path), bbox=window)
    return CoverRaster(
        cover.band(0).astype(float),
        loss.band(0).astype(int),
        loss,
        f"{GFC_TILE_VERSION} {tile}",
    )


# ------------------------------------------------------------------- расчёт


def read_year(data_dir: Path, aoi: str, year: int, box, config: CaseCalculationConfig = CONFIG) -> dict:
    source = open_cci(data_dir, aoi, year, box)
    weights = pixel_intersection_weights(source.grid, box)
    result = calculate_year(year, source.agb, source.sd, weights, config)
    result["source"] = source.source
    return result


def gfc_loss_by_year(data_dir: Path, aoi: str, box) -> list[dict]:
    """Площадь потерь покрова по годам внутри контура, га.

    Потеря — снижение древесного покрова по продукту Hansen, а не
    установленная вырубка: причина здесь не определяется.
    """
    source = open_gfc(data_dir, aoi, box)
    weights = pixel_intersection_weights(source.grid, box)
    treecover = source.treecover
    lossyear = source.lossyear
    forest = treecover >= TREECOVER_THRESHOLD
    out = []
    for code in range(1, 26):
        mask = (lossyear == code) & forest
        area = float(weights[mask].sum())
        if area > 0:
            out.append({"year": 2000 + code, "area_ha": area})
    return out


def render_maps(data_dir: Path, aoi: str, box, out_dir: Path, config: CaseCalculationConfig = CONFIG) -> dict:
    """Пишет три PNG на участок: запас, изменение запаса и маска потерь.

    Карты рисуются по тем же пикселям, по которым считаются числа, поэтому
    пятно на карте и вклад в дельту — одно и то же место, а не иллюстрация.
    Разрешение файлов равно разрешению продукта: растягивать нечем и незачем.
    """
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    start = open_cci(data_dir, aoi, 2019, box)
    end = open_cci(data_dir, aoi, 2024, box)
    weights = pixel_intersection_weights(start.grid, box)
    inside = weights > 0

    c_start = carbon_density_t_ha(start.agb, config)
    c_end = carbon_density_t_ha(end.agb, config)
    delta = c_end - c_start

    def save(rgb: np.ndarray, alpha: np.ndarray, name: str) -> str:
        image = np.dstack([rgb, alpha]).astype(np.uint8)
        Image.fromarray(image, "RGBA").save(out_dir / name)
        return name

    # запас на конец периода: от светлого к тёмно-зелёному
    scale = np.clip(c_end / max(np.percentile(c_end[inside], 98), 1e-6), 0, 1)
    stock_rgb = np.dstack(
        [227 - 190 * scale, 232 - 140 * scale, 216 - 176 * scale]
    )
    save(stock_rgb, inside * 255, f"{aoi}_stock.png")

    # изменение: потеря — тёплый, накопление — лаймовый, ноль — прозрачный
    span = max(np.percentile(np.abs(delta[inside]), 98), 1e-6)
    norm = np.clip(delta / span, -1, 1)
    loss_side = np.clip(-norm, 0, 1)
    gain_side = np.clip(norm, 0, 1)
    change_rgb = np.dstack(
        [
            243 - 76 * gain_side - 60 * loss_side,
            243 - 24 * gain_side - 130 * loss_side,
            240 - 196 * gain_side - 175 * loss_side,
        ]
    )
    change_alpha = np.clip(np.abs(norm), 0.08, 1) * 255 * inside
    save(change_rgb, change_alpha, f"{aoi}_change.png")

    # потери покрова Hansen на своей, более мелкой сетке
    gfc_source = open_gfc(data_dir, aoi, box)
    gfc = gfc_source.grid
    gfc_weights = pixel_intersection_weights(gfc, box)
    lossyear = gfc_source.lossyear
    treecover = gfc_source.treecover
    recent = (lossyear >= 19) & (lossyear <= 24) & (treecover >= TREECOVER_THRESHOLD)
    older = (lossyear > 0) & (lossyear < 19) & (treecover >= TREECOVER_THRESHOLD)
    rgb = np.zeros((*lossyear.shape, 3))
    rgb[older] = [150, 152, 140]
    rgb[recent] = [154, 82, 64]
    alpha = ((recent | older) & (gfc_weights > 0)) * 255
    save(rgb, alpha, f"{aoi}_loss.png")

    return {
        "stock": f"{aoi}_stock.png",
        "change": f"{aoi}_change.png",
        "loss": f"{aoi}_loss.png",
        "change_span_tc_ha": float(span),
        "source_cci": start.source,
        "source_gfc": gfc_source.source,
        "size": [int(start.grid.data.shape[2]), int(start.grid.data.shape[1])],
        "loss_size": [int(lossyear.shape[1]), int(lossyear.shape[0])],
    }


# Пороги скрининга устойчивости. Это правила, а не обученная модель:
# четыре участка — не выборка, и назвать такое обучением было бы враньём.
# Каждый порог виден на экране, и любой из них можно оспорить.
RISK_RULES = [
    ("доля потерь покрова за 2001—2024", "loss_share_pct", [(5.0, 2), (1.0, 1)], "%"),
    ("число лет с потерями", "loss_years", [(8, 2), (4, 1)], ""),
    ("подтверждённый пожар на участке", "fire_confirmed", [(1, 2)], ""),
    ("волатильность годового ряда запаса", "volatility_rel", [(0.15, 2), (0.07, 1)], ""),
    ("отношение погрешности продукта к запасу", "sd_to_stock", [(0.5, 2), (0.3, 1)], ""),
    ("падающая историческая динамика", "baseline_decline", [(1.0, 2), (0.001, 1)], "т C/га/год"),
]


def render_terrain(
    data_dir: Path, aoi: str, box, out_dir: Path, config: CaseCalculationConfig = CONFIG
) -> dict | None:
    """Числовая сетка запаса по годам для объёмного рельефа на экране.

    Карты рисуются в PNG, но картинку нельзя выдавить в объём: в ней уже
    только цвет. Поэтому рядом кладётся та же сетка числами — те же
    пиксели, из которых считается ΔC, а не отдельная выгрузка.

    Годы выгружаются все, какие есть в наборе, а не два крайних. Период
    наблюдения на экране выбирается пользователем, и если рельеф знает
    только 2019 и 2024, то при любом другом выборе он показывает не то,
    что подписано сверху.

    Значения округляются до целых т C/га. Точность продукта — единицы
    процентов, дробная часть ничего не добавила бы, а вес вырос бы втрое.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    local = sorted(
        int(path.stem.split("_")[-1])
        for path in (data_dir / aoi).glob("CCI_Biomass_*.tif")
    )
    # У добавленных участков вложенных файлов нет — годы берутся те же,
    # что у участков кейса, и читаются окном из тайла.
    years = local or list(range(2015, 2025))
    if not years:
        return None

    first_source = open_cci(data_dir, aoi, years[0], box)
    first = first_source.grid
    weights = pixel_intersection_weights(first, box)
    inside = weights > 0
    if not inside.any():
        return None

    def grid(values: np.ndarray) -> list[int]:
        """Вне контура пишется −1, а не ноль: ноль — это тоже значение,
        и спутать «здесь нет леса» с «сюда не спрашивали» нельзя."""
        out = np.where(inside, np.rint(np.nan_to_num(values)), -1)
        return [int(v) for v in out.ravel()]

    grids: dict[str, list[int]] = {}
    peak = 0.0
    for year in years:
        density = carbon_density_t_ha(open_cci(data_dir, aoi, year, box).agb, config)
        grids[str(year)] = grid(density)
        peak = max(peak, float(np.percentile(density[inside], 99)))

    rows, cols = weights.shape

    # Год потери покрова, переложенный на сетку запаса. Hansen снимает
    # тридцатиметровым шагом, CCI — стометровым, поэтому в одну клетку
    # запаса попадает около дюжины пикселей Hansen. Берём самый поздний
    # год среди них: клетка помечается годом, когда её задело в последний
    # раз, и подсветка «что упало в 2022» не теряет клетки, задетые ещё
    # и раньше.
    loss_years = [0] * (rows * cols)
    try:
        gfc_source = open_gfc(data_dir, aoi, box)
    except FileNotFoundError:
        gfc_source = None
    if gfc_source is not None:
        gfc = gfc_source.grid
        cover = gfc_source.treecover
        lossyear = gfc_source.lossyear
        forest = cover >= TREECOVER_THRESHOLD
        marked = np.where(forest, lossyear, 0)

        lat0, lon0 = first.lat_origin, first.lon_origin
        for row in range(rows):
            top = lat0 - row * first.lat_step
            r0 = int(round((gfc.lat_origin - top) / gfc.lat_step))
            r1 = int(round((gfc.lat_origin - (top - first.lat_step)) / gfc.lat_step))
            if r1 <= r0 or r0 < 0 or r0 >= marked.shape[0]:
                continue
            for col in range(cols):
                if not inside[row, col]:
                    continue
                left = lon0 + col * first.lon_step
                c0 = int(round((left - gfc.lon_origin) / gfc.lon_step))
                c1 = int(round((left + first.lon_step - gfc.lon_origin) / gfc.lon_step))
                if c1 <= c0 or c0 < 0 or c0 >= marked.shape[1]:
                    continue
                block = marked[r0 : min(r1, marked.shape[0]), c0 : min(c1, marked.shape[1])]
                if block.size:
                    code = int(block.max())
                    if code > 0:
                        loss_years[row * cols + col] = 2000 + code

    return {
        "width": int(cols),
        "height": int(rows),
        "unit": "т C/га",
        "peak_t_ha": round(peak, 1),
        "pixel_area_ha": round(float(weights[inside].mean()), 4),
        "years": [int(y) for y in years],
        "grids": grids,
        "loss_years": loss_years,
    }


def stability_screening(series, cover_loss, area_ha, baseline_rate, has_fire) -> dict:
    """Скрининг устойчивости результата на горизонт кредитования.

    Отвечает на вопрос «насколько вероятно, что накопленное не удержится»,
    и НЕ влияет на число единиц: вычет за неопределённость выводится из H/R,
    резерв фиксирован условиями кейса. Числовой вероятности реверсии здесь
    нет — только категория и перечень сработавших признаков.
    """
    loss_total = sum(l["area_ha"] for l in cover_loss)
    diffs = [
        series[i]["c_t_ha"] - series[i - 1]["c_t_ha"] for i in range(1, len(series))
    ]
    mean_stock = sum(p["c_t_ha"] for p in series) / len(series)
    spread = (sum((d - sum(diffs) / len(diffs)) ** 2 for d in diffs) / len(diffs)) ** 0.5
    last = series[-1]

    features = {
        "loss_share_pct": loss_total / area_ha * 100,
        "loss_years": float(len(cover_loss)),
        "fire_confirmed": 1.0 if has_fire else 0.0,
        "volatility_rel": spread / mean_stock if mean_stock else 0.0,
        "sd_to_stock": last["agb_sd_t_ha"] / last["agb_t_ha"] if last["agb_t_ha"] else 0.0,
        "baseline_decline": max(0.0, -baseline_rate),
    }

    score = 0
    drivers = []
    for label, key, thresholds, unit in RISK_RULES:
        value = features[key]
        for limit, points in thresholds:
            if value >= limit:
                score += points
                drivers.append(
                    {
                        "label": label,
                        "value": value,
                        "unit": unit,
                        "threshold": limit,
                        "points": points,
                    }
                )
                break

    level = "high" if score >= 8 else "medium" if score >= 4 else "low"
    return {
        "level": level,
        "score": score,
        "max_score": sum(t[0][1] for _, _, t, _ in RISK_RULES),
        "features": features,
        "drivers": drivers,
        "method": "пороговые правила по шести признакам",
        "model_version": None,
        "limitation": (
            "Правила, а не обученная модель — и это выбор, а не нехватка данных: "
            "модель обучена на отдельной выборке и одиночный признак не бьёт, "
            "поэтому в продукт идут правила, которые видно насквозь. "
            "Настроено на бореальную и умеренную зону, на другие зоны не переносится. "
            "На число потенциальных единиц не влияет."
        ),
    }


def _sentinel_block(data_dir: Path, aoi: str, aoi_events: list[dict], box, maps_dir):
    """Use the current Sentinel evidence pipeline without affecting G2 stock."""
    if maps_dir is None:
        return None
    try:
        if aoi_events:
            return build_event_evidence(data_dir, aoi_events[0], box, maps_dir)
        return build_period_evidence(data_dir, aoi, box, maps_dir)
    except (FileNotFoundError, KeyError, ValueError) as error:
        return {"observations": [], "comparison": None, "unavailable": str(error)}


def build_aoi(
    data_dir: Path,
    meta: dict,
    baseline: list[dict],
    events: list[dict],
    maps_dir: Path | None,
    config: CaseCalculationConfig = CONFIG,
    geometry: dict | None = None,
) -> dict:
    box = (
        float(meta["bbox_west"]),
        float(meta["bbox_south"]),
        float(meta["bbox_east"]),
        float(meta["bbox_north"]),
    )
    aoi = meta["aoi_id"]
    contour = geometry if geometry is not None else box
    series = [read_year(data_dir, aoi, year, contour, config) for year in range(2015, 2025)]
    by_year = {row["year"]: row for row in series}
    area = series[0]["area_ha"]

    # Official yearly endpoints are the source of truth. Their per-hectare
    # values are scaled by the measured area inside calculate_period.
    base_stock = baseline_stock_by_year(baseline, aoi, meta["baseline_id"])
    base_rows = [r for r in baseline if r.get("aoi_id") == aoi and r.get("baseline_id") == meta["baseline_id"]]
    base_rate = float(base_rows[0]["historical_rate_tc_ha_yr"]) if base_rows else None
    economics_config = ScenarioEconomicsConfig(config.prices_rub)

    def period(start: int, end: int) -> dict:
        t0, t1 = by_year[start], by_year[end]
        result = calculate_period(t0, t1, base_stock.get(start), base_stock.get(end), config)
        economics = calculate_scenario_value(result["units"], economics_config)

        # Чувствительность к допущениям о корреляции: число единиц целиком
        # определяется ими, и это главный вывод, а не техническая деталь.
        grid = []
        for rs in config.rho_spatial_grid:
            row = []
            for rt in config.rho_temporal_grid:
                s0 = sigma_from_sums(t0["_sd_sum"], t0["_sd_sq_sum"], config, rs)
                s1 = sigma_from_sums(t1["_sd_sum"], t1["_sd_sq_sum"], config, rs)
                _, half = uncertainty_half_width(s0, s1, config, rt)
                cell = potential_units(
                    result["e_tco2e"], result["e_base_tco2e"], half, config
                )
                row.append(
                    {
                        "rho_spatial": rs,
                        "rho_temporal": rt,
                        "h_tco2e": half,
                        "h_over_r": cell["h_over_r"],
                        "units": cell["units"],
                    }
                )
            grid.append(row)

        return {
            **result,
            "scenario_economics": economics,
            "value_rub": {row["name"]: row["value_rub"] for row in economics["scenarios"]},
            "sensitivity": grid,
        }

    aoi_events = [e for e in events if e["aoi_id"] == aoi]
    has_fire = bool(aoi_events)
    loss = gfc_loss_by_year(data_dir, aoi, contour)

    area_result = {
        "aoi_id": aoi,
        "maps": render_maps(data_dir, aoi, contour, maps_dir, config) if maps_dir else None,
        "terrain": render_terrain(data_dir, aoi, contour, maps_dir, config) if maps_dir else None,
        "sentinel": _sentinel_block(data_dir, aoi, aoi_events, box, maps_dir),
        "stability": (
            stability_screening(series, loss, area, base_rate, has_fire)
            if base_rate is not None
            and all(row["c_t_ha"] is not None and row["agb_t_ha"] is not None for row in series)
            else None
        ),
        "name": meta["name"],
        "region": meta["region"],
        "role": meta["selection_role"],
        "status": meta["project_status"],
        "area_ha": area,
        "area_ha_declared": float(meta["area_ha"]),
        "bbox": list(box),
        "baseline_id": meta["baseline_id"],
        "baseline_rate_tc_ha_year": base_rate,
        "baseline_stock_t_ha": {str(k): v for k, v in sorted(base_stock.items())},
        "series": series,
        "cover_loss": loss,
        "period_2019_2024": period(2019, 2024),
        "periods": [
            {k: v for k, v in period(s, e).items() if k != "sensitivity"}
            for s in range(2019, 2024)
            for e in range(s + 1, 2025)
        ],
    }
    summary = generate_summary(area_result)
    if summary is not None:
        area_result["summary"] = summary
    return area_result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path, help="каталог data набора кейса")
    parser.add_argument("--out", required=True, type=Path, help="куда записать JSON")
    parser.add_argument("--maps", type=Path, default=None, help="каталог для PNG карт")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="сверить средние запасы 2015 и 2019 с опорными значениями baseline.csv",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="AOI",
        default=None,
        help="считать только перечисленные участки (например, четыре участка кейса)",
    )
    args = parser.parse_args()

    with open(args.data / "areas.csv", encoding="utf-8-sig") as handle:
        areas = list(csv.DictReader(handle))

    # Участки кейса вложены в репозиторий и считаются без сети. Добавленным
    # нами участкам нужны тайлы из кэша — гигабайты, которых на свежем
    # клоне нет. Отбор даёт воспроизвести расчёт по кейсу, не скачивая их.
    if args.only:
        wanted = set(args.only)
        unknown = wanted - {row["aoi_id"] for row in areas}
        if unknown:
            parser.error(f"нет таких участков в areas.csv: {', '.join(sorted(unknown))}")
        areas = [row for row in areas if row["aoi_id"] in wanted]
    with open(args.data / "methodology" / "baseline.csv", encoding="utf-8-sig") as handle:
        baseline = list(csv.DictReader(handle))
    with open(args.data / "events.csv", encoding="utf-8-sig") as handle:
        events = list(csv.DictReader(handle))
    with open(args.data / "methodology" / "parameters.csv", encoding="utf-8-sig") as handle:
        config = CaseCalculationConfig.from_parameter_rows(list(csv.DictReader(handle)))
    with open(args.data / "areas.geojson", encoding="utf-8-sig") as handle:
        geometries = {feature["properties"]["aoi_id"]: feature["geometry"]
                      for feature in json.load(handle)["features"]}

    payload = {
        "generated_from": "ESA CCI Biomass v7.0, Hansen GFC v1.13, MODIS MCD64A1 061",
        "parameters": {
            "carbon_fraction": config.carbon_fraction,
            "co2_per_carbon": config.co2_per_carbon,
            "unc_threshold": config.unc_threshold,
            "unc_stop_ratio": config.unc_stop_ratio,
            "buffer_share": config.buffer_share,
            "leakage_tco2e": config.leakage_tco2e,
            "rho_spatial": config.rho_spatial,
            "rho_temporal": config.rho_temporal,
            "k_sigma": config.k_sigma,
            "treecover_threshold_pct": TREECOVER_THRESHOLD,
            "prices_rub": dict(config.prices_rub),
        },
        "areas": [build_aoi(args.data, meta, baseline, events, args.maps,
                            config, geometries[meta["aoi_id"]]) for meta in areas],
        "events": [
            {
                "event_id": e["event_id"],
                "aoi_id": e["aoi_id"],
                "evidence_type": e["evidence_type"],
                "cause_supported": e["cause_supported"],
                "date_min": e["date_min_product"],
                "date_max": e["date_max_product"],
                "burned_pixels": int(e["burned_pixel_centers_in_aoi"]),
                "all_pixels": int(e["all_pixel_centers_in_aoi"]),
                "uncertainty_days": [
                    int(e["date_uncertainty_days_min"]),
                    int(e["date_uncertainty_days_max"]),
                ],
                "source_id": e["source_id"],
                "context_url": e["context_url"],
                "limitations": e["limitations"],
            }
            for e in events
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"записано {args.out} ({args.out.stat().st_size / 1024:.0f} КБ)")

    if args.verify:
        ok = verify_against_baseline(payload, baseline)
        if not ok:
            sys.exit(1)


def verify_against_baseline(payload: dict, baseline: list[dict]) -> bool:
    """Сверяет посчитанные средние запасы 2015 и 2019 с опорными значениями.

    Это самая короткая демонстрация того, что расчёт повторяет замысел
    автора кейса: если площадное взвешивание пикселей или перевод биомассы
    в углерод сделаны иначе, средние разойдутся уже в шестом знаке.

    Печатается фактическое расхождение, а не вердикт «совпало»: порог
    можно оспорить, а измеренную разницу — нет.
    """
    tolerance = 1e-6
    rows: list[tuple[str, int, float, float]] = []
    for area in payload["areas"]:
        aoi = area["aoi_id"]
        reference = next(
            (r for r in baseline if r.get("aoi_id") == aoi and r.get("baseline_id") == area["baseline_id"]),
            None,
        )
        if reference is None:
            continue
        computed = {row["year"]: row["c_t_ha"] for row in area["series"]}
        for year in (2015, 2019):
            expected = reference.get(f"reference_mean_{year}_tc_ha")
            if expected is None or computed.get(year) is None:
                continue
            rows.append((aoi, year, float(computed[year]), float(expected)))

    if not rows:
        print("\nпроверка невозможна: опорные средние в baseline.csv не найдены")
        return False

    width = max(len(aoi) for aoi, *_ in rows)
    worst = 0.0
    print("\nсверка с methodology/baseline.csv (reference_mean_*_tc_ha):")
    for aoi, year, got, expected in rows:
        delta = abs(got - expected)
        worst = max(worst, delta)
        mark = "ok" if delta <= tolerance else "РАСХОЖДЕНИЕ"
        print(
            f"  {aoi:<{width}}  {year}  посчитано {got:.9f}  опорное {expected:.9f}  "
            f"|Δ| {delta:.2e}  {mark}"
        )

    if worst <= tolerance:
        print(f"совпадение до шестого знака: наибольшее расхождение {worst:.2e}")
        return True
    print(
        f"\nнаибольшее расхождение {worst:.2e} превышает допуск {tolerance:.0e}.\n"
        "Совпадение до шестого знака не достигнуто — это разница в самом расчёте, "
        "а не в оформлении, и её нельзя списывать на округление."
    )
    return False


if __name__ == "__main__":
    main()
