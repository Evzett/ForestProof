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
import math
from pathlib import Path
import sys

import numpy as np

# Keep the documented direct invocation (python tools/extract_case_data.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
from tools.geotiff import read_geotiff

# ---------------------------------------------------------------- параметры

CONFIG = CaseCalculationConfig()

# Порог древесного покрова для маски GFC: доля кроны на 2000 год
TREECOVER_THRESHOLD = 30

# ------------------------------------------------------------------- расчёт


def read_year(data_dir: Path, aoi: str, year: int, box, config: CaseCalculationConfig = CONFIG) -> dict:
    raster = read_geotiff(str(data_dir / aoi / f"CCI_Biomass_{year}.tif"))
    weights = pixel_intersection_weights(raster, box)
    agb = raster.band(0).astype(float)
    sd = raster.band(1).astype(float)
    if raster.nodata is not None:
        agb[agb == raster.nodata] = np.nan
        sd[sd == raster.nodata] = np.nan
    return calculate_year(year, agb, sd, weights, config)


def gfc_loss_by_year(data_dir: Path, aoi: str, box) -> list[dict]:
    """Площадь потерь покрова по годам внутри контура, га.

    Потеря — снижение древесного покрова по продукту Hansen, а не
    установленная вырубка: причина здесь не определяется.
    """
    raster = read_geotiff(str(data_dir / aoi / "GFC_2025_v1_13.tif"))
    weights = pixel_intersection_weights(raster, box)
    treecover = raster.band(0).astype(float)
    lossyear = raster.band(1).astype(int)
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
    start = read_geotiff(str(data_dir / aoi / "CCI_Biomass_2019.tif"))
    end = read_geotiff(str(data_dir / aoi / "CCI_Biomass_2024.tif"))
    weights = pixel_intersection_weights(start, box)
    inside = weights > 0

    c_start = carbon_density_t_ha(start.band(0), config)
    c_end = carbon_density_t_ha(end.band(0), config)
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
    gfc = read_geotiff(str(data_dir / aoi / "GFC_2025_v1_13.tif"))
    gfc_weights = pixel_intersection_weights(gfc, box)
    lossyear = gfc.band(1).astype(int)
    treecover = gfc.band(0).astype(float)
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
        "size": [int(start.data.shape[2]), int(start.data.shape[1])],
        "loss_size": [int(lossyear.shape[1]), int(lossyear.shape[0])],
    }


# Каналы снимка в том порядке, в котором они лежат в файле
S2_BANDS = {"B02": 0, "B03": 1, "B04": 2, "B8A": 3, "B11": 4, "B12": 5}

# Классы маски SCL, которые считаем пригодными: растительность, голая почва,
# вода и неклассифицированное. Облака, тени и снег в пригодные не входят.
SCL_USABLE = {4, 5, 6, 7}


def _stretch(band: np.ndarray, lo_pct: float = 2, hi_pct: float = 98) -> np.ndarray:
    """Линейная растяжка по процентилям. Без неё снимок выходит чёрным:
    отражение леса лежит в узком нижнем диапазоне шкалы."""
    valid = band[np.isfinite(band)]
    if valid.size == 0:
        return np.zeros_like(band)
    lo, hi = np.percentile(valid, [lo_pct, hi_pct])
    if hi <= lo:
        return np.zeros_like(band)
    return np.clip((band - lo) / (hi - lo), 0, 1)


def _scene_date(name: str) -> str:
    """Дата съёмки из имени: S2A_38ULF_20210712_1_L2A_reflectance.tif"""
    for part in name.split("_"):
        if len(part) == 8 and part.isdigit():
            return f"{part[:4]}-{part[4:6]}-{part[6:]}"
    return ""


def _nbr(refl: np.ndarray) -> np.ndarray:
    """Normalized Burn Ratio: (NIR − SWIR2) / (NIR + SWIR2).

    Гарь резко снижает NBR, поэтому разность до и после показывает
    затронутую площадь. Это признак, а не доказательство пожара:
    та же картина возникает при сплошной рубке.
    """
    nir = refl[S2_BANDS["B8A"]]
    swir = refl[S2_BANDS["B12"]]
    denom = nir + swir
    # Нулевой знаменатель встречается на пикселях без данных: там не ноль
    # и не бесконечность, а отсутствие значения.
    # Порог по сумме отражений, а не по машинному нулю: сумма ниже 0,01
    # это шум или отсутствие данных, и отношение там даёт выбросы в сотни
    # единиц при физическом диапазоне NBR от −1 до 1.
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(denom > 0.01, (nir - swir) / denom, np.nan)
    return np.where(np.abs(ratio) <= 1.5, ratio, np.nan)


def render_sentinel(data_dir: Path, aoi: str, event_dates: tuple[str, str] | None, out_dir: Path):
    """Пара снимков до и после плюс карта dNBR.

    Сцены отбираются по доле пригодных пикселей маски SCL и по близости
    к событию. Если пригодной сцены в окне нет — так и пишем, а не берём
    ближайший сезон: снимок другого сезона покажет фенологию, а не потерю.
    """
    from PIL import Image

    folder = data_dir / aoi / "Sentinel2"
    if not folder.exists():
        return None

    scenes = []
    for path in sorted(folder.glob("*_reflectance.tif")):
        scl_path = Path(str(path).replace("_reflectance.tif", "_SCL.tif"))
        if not scl_path.exists():
            continue
        scl = read_geotiff(str(scl_path)).band(0)
        usable = float(np.isin(scl, list(SCL_USABLE)).mean())
        scenes.append({"path": path, "date": _scene_date(path.name), "usable": usable})

    if len(scenes) < 2:
        return None

    # Отбираем пару вокруг события; без события — первая и последняя сцены
    good = [s for s in scenes if s["usable"] >= 0.6] or scenes

    def month(scene) -> int:
        return int(scene["date"][5:7])

    def days(a: str, b: str) -> int:
        from datetime import date

        pa = date(int(a[:4]), int(a[5:7]), int(a[8:]))
        pb = date(int(b[:4]), int(b[5:7]), int(b[8:]))
        return abs((pa - pb).days)

    if event_dates:
        before_pool = [s for s in good if s["date"] < event_dates[0]]
        after_pool = [s for s in good if s["date"] > event_dates[1]]
        before = before_pool[-1] if before_pool else good[0]
        # Пару подбираем по близости месяца, а не просто по времени: снимок
        # другого сезона покажет фенологию, и разность NBR будет про листву,
        # а не про потерю. Из подходящих берём ближайший к событию.
        window = [s for s in after_pool if days(s["date"], event_dates[1]) <= 450]
        pool = window or after_pool or good[-1:]
        after = min(pool, key=lambda s: (abs(month(s) - month(before)), s["date"]))
    else:
        before = good[0]
        pool = [s for s in good if s["date"] > before["date"]] or good[-1:]
        after = min(
            pool, key=lambda s: (abs(month(s) - month(before)), -days(s["date"], before["date"]))
        )

    if before["path"] == after["path"]:
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    rasters = {}

    for key, scene in (("before", before), ("after", after)):
        raster = read_geotiff(str(scene["path"]))
        refl = raster.data.astype(float)
        rasters[key] = refl
        # Композит SWIR2 / NIR / Red: гарь на нём читается однозначно,
        # в натуральных цветах она сливается с тенью и вспаханным полем.
        rgb = np.dstack(
            [
                _stretch(refl[S2_BANDS["B12"]]),
                _stretch(refl[S2_BANDS["B8A"]]),
                _stretch(refl[S2_BANDS["B04"]]),
            ]
        )
        alpha = np.isfinite(refl[S2_BANDS["B04"]]) * 255
        image = np.dstack([rgb * 255, alpha]).astype(np.uint8)
        Image.fromarray(image, "RGBA").save(out_dir / f"{aoi}_s2_{key}.png")

    # dNBR: положительное значение — падение NBR, то есть потеря растительности
    dnbr = _nbr(rasters["before"]) - _nbr(rasters["after"])
    finite = dnbr[np.isfinite(dnbr)]
    span = float(np.percentile(np.abs(finite), 98)) if finite.size else 1.0
    span = max(span, 1e-6)
    norm = np.clip(dnbr / span, -1, 1)
    loss = np.clip(norm, 0, 1)
    gain = np.clip(-norm, 0, 1)
    rgb = np.dstack(
        [
            243 - 60 * loss - 76 * gain,
            243 - 130 * loss - 24 * gain,
            240 - 175 * loss - 196 * gain,
        ]
    )
    alpha = np.nan_to_num(np.clip(np.abs(norm), 0.06, 1)) * 255 * np.isfinite(dnbr)
    Image.fromarray(np.dstack([np.nan_to_num(rgb), alpha]).astype(np.uint8), "RGBA").save(
        out_dir / f"{aoi}_s2_dnbr.png"
    )

    return {
        "before": {
            "file": f"{aoi}_s2_before.png",
            "date": before["date"],
            "usable_pct": round(before["usable"] * 100, 1),
        },
        "after": {
            "file": f"{aoi}_s2_after.png",
            "date": after["date"],
            "usable_pct": round(after["usable"] * 100, 1),
        },
        "dnbr": {
            "file": f"{aoi}_s2_dnbr.png",
            "span": round(span, 3),
            "median": round(float(np.median(finite)), 4) if finite.size else None,
            "share_above_threshold_pct": (
                round(float((finite > 0.27).mean() * 100), 1) if finite.size else None
            ),
        },
        "composite": "SWIR2 · NIR · Red (B12, B8A, B04)",
        "size": [int(rasters["before"].shape[2]), int(rasters["before"].shape[1])],
        "scenes_total": len(scenes),
        "source": "Copernicus Sentinel-2 L2A через Element 84 Earth Search",
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
            "Правила, а не обученная модель: четырёх участков для обучения недостаточно. "
            "Настроено на бореальную и умеренную зону, на другие зоны не переносится. "
            "На число потенциальных единиц не влияет."
        ),
    }


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

    def period(start: int, end: int) -> dict:
        t0, t1 = by_year[start], by_year[end]
        result = calculate_period(t0, t1, base_stock.get(start), base_stock.get(end), config)

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
            "value_rub": {
                name: (None if result["units"] is None else result["units"] * price)
                for name, price in config.prices_rub
            },
            "sensitivity": grid,
        }

    aoi_events = [e for e in events if e["aoi_id"] == aoi]
    has_fire = bool(aoi_events)
    event_window = (
        (aoi_events[0]["date_min_product"], aoi_events[0]["date_max_product"])
        if aoi_events
        else None
    )
    loss = gfc_loss_by_year(data_dir, aoi, contour)

    return {
        "aoi_id": aoi,
        "maps": render_maps(data_dir, aoi, contour, maps_dir, config) if maps_dir else None,
        "sentinel": render_sentinel(data_dir, aoi, event_window, maps_dir) if maps_dir else None,
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path, help="каталог data набора кейса")
    parser.add_argument("--out", required=True, type=Path, help="куда записать JSON")
    parser.add_argument("--maps", type=Path, default=None, help="каталог для PNG карт")
    args = parser.parse_args()

    with open(args.data / "areas.csv", encoding="utf-8-sig") as handle:
        areas = list(csv.DictReader(handle))
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


if __name__ == "__main__":
    main()
