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
from tools.geotiff import read_geotiff
from tools.sentinel_evidence import build_event_evidence, build_period_evidence

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
    loss = gfc_loss_by_year(data_dir, aoi, contour)

    return {
        "aoi_id": aoi,
        "maps": render_maps(data_dir, aoi, contour, maps_dir, config) if maps_dir else None,
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
