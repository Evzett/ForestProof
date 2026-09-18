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

import numpy as np

from geotiff import read_geotiff

# ---------------------------------------------------------------- параметры

CF = 0.47  # т C / т сухого вещества, МГЭИК 2006, т. 4, гл. 4, табл. 4.3
CO2_PER_C = 44 / 12

# Доля неопределённости и резерв — сценарные условия кейса
UNC_THRESHOLD = 0.10
BUFFER_SHARE = 0.15
LEAKAGE = 0.0

# Модель переноса ошибки. Все три значения — допущения, а не измерения,
# поэтому выводятся на экран и проверяются на чувствительность.
RHO_SPATIAL = 0.5  # корреляция ошибки продукта между пикселями одного года
RHO_TEMPORAL = 0.7  # корреляция ошибки между двумя годами на той же территории
K_SIGMA = 1.645  # нормальное приближение, двусторонний охват 90 %

# Порог древесного покрова для маски GFC: доля кроны на 2000 год
TREECOVER_THRESHOLD = 30

PRICES = {"low": 500, "base": 1500, "high": 4000}

# Сетка чувствительности к допущениям о корреляции ошибки
RHO_SPATIAL_GRID = [0.0, 0.25, 0.5, 0.75, 1.0]
RHO_TEMPORAL_GRID = [0.0, 0.5, 0.7, 0.9, 0.95, 0.99]


# ------------------------------------------------------------------ утилиты


def bbox_weights(raster, west: float, south: float, east: float, north: float) -> np.ndarray:
    """Площадь пересечения каждого пикселя с прямоугольником запроса, га.

    Пиксель на краю входит частью — иначе площадь округляется до целых
    пикселей и расходится с эталоном на проценты.
    """
    rows, cols = raster.data.shape[1], raster.data.shape[2]
    lon_left = raster.lon_origin + np.arange(cols) * raster.lon_step
    lon_right = lon_left + raster.lon_step
    lat_top = raster.lat_origin - np.arange(rows) * raster.lat_step
    lat_bottom = lat_top - raster.lat_step

    frac_x = np.clip(np.minimum(lon_right, east) - np.maximum(lon_left, west), 0, None)
    frac_y = np.clip(np.minimum(lat_top, north) - np.maximum(lat_bottom, south), 0, None)
    frac = np.outer(frac_y / raster.lat_step, frac_x / raster.lon_step)
    return frac * raster.pixel_area_ha()


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    total = weights.sum()
    return float((values * weights).sum() / total) if total > 0 else math.nan


def stock_sigma(sd: np.ndarray, weights: np.ndarray, rho: float) -> float:
    """Стандартное отклонение суммарного запаса, т C.

    Корреляция ошибки между пикселями задана одним числом rho: при rho = 0
    ошибки независимы и в сумме гасятся, при rho = 1 складываются целиком.
    Промежуточное значение — допущение, которое проверяется отдельно.
    """
    terms = weights * sd
    independent = float((terms**2).sum())
    correlated = float(terms.sum() ** 2)
    variance = (1 - rho) * independent + rho * correlated
    return CF * math.sqrt(max(variance, 0.0))


# ------------------------------------------------------------------- расчёт


def sigma_pair(sd_terms: float, sq_terms: float, rho: float) -> float:
    """sigma по уже посчитанным суммам: Sum(a*sd) и Sum((a*sd)^2)."""
    variance = (1 - rho) * sq_terms + rho * sd_terms**2
    return CF * math.sqrt(max(variance, 0.0))


def read_year(data_dir: Path, aoi: str, year: int, box) -> dict:
    raster = read_geotiff(str(data_dir / aoi / f"CCI_Biomass_{year}.tif"))
    weights = bbox_weights(raster, *box)
    agb = raster.band(0).astype(float)
    sd = raster.band(1).astype(float)
    mean_agb = weighted_mean(agb, weights)
    area = float(weights.sum())
    terms = weights * sd
    return {
        "year": year,
        "area_ha": area,
        "agb_t_ha": mean_agb,
        "agb_sd_t_ha": weighted_mean(sd, weights),
        "c_t_ha": mean_agb * CF,
        "stock_tc": mean_agb * CF * area,
        "sigma_stock_tc": stock_sigma(sd, weights, RHO_SPATIAL),
        # суммы для пересчёта sigma при другой корреляции, без чтения растров
        "_sd_sum": float(terms.sum()),
        "_sd_sq_sum": float((terms**2).sum()),
    }


def gfc_loss_by_year(data_dir: Path, aoi: str, box) -> list[dict]:
    """Площадь потерь покрова по годам внутри контура, га.

    Потеря — снижение древесного покрова по продукту Hansen, а не
    установленная вырубка: причина здесь не определяется.
    """
    raster = read_geotiff(str(data_dir / aoi / "GFC_2025_v1_13.tif"))
    weights = bbox_weights(raster, *box)
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


def render_maps(data_dir: Path, aoi: str, box, out_dir: Path) -> dict:
    """Пишет три PNG на участок: запас, изменение запаса и маска потерь.

    Карты рисуются по тем же пикселям, по которым считаются числа, поэтому
    пятно на карте и вклад в дельту — одно и то же место, а не иллюстрация.
    Разрешение файлов равно разрешению продукта: растягивать нечем и незачем.
    """
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    start = read_geotiff(str(data_dir / aoi / "CCI_Biomass_2019.tif"))
    end = read_geotiff(str(data_dir / aoi / "CCI_Biomass_2024.tif"))
    weights = bbox_weights(start, *box)
    inside = weights > 0

    c_start = start.band(0).astype(float) * CF
    c_end = end.band(0).astype(float) * CF
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
    gfc_weights = bbox_weights(gfc, *box)
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


def potential_units(e_proj: float, e_base: float, half_width: float) -> dict:
    """Потенциальные единицы по правилам кейса.

    Порядок проверок важен: при R <= 0 отношение H/R не вычисляется вовсе,
    а не считается и отбрасывается — деления на ноль в этой ветке нет.
    """
    r = e_base - e_proj - LEAKAGE
    result = {
        "e_proj_tco2e": e_proj,
        "e_base_tco2e": e_base,
        "leakage_tco2e": LEAKAGE,
        "r_tco2e": r,
        "h_tco2e": half_width,
        "h_over_r": None,
        "unc_share": None,
        "r_adjusted_tco2e": None,
        "buffer_tco2e": None,
        "units": 0,
        "reason": None,
    }
    if not all(map(math.isfinite, (e_proj, e_base, half_width))) or half_width < 0:
        result["units"] = None
        result["reason"] = "входные данные неполные — расчёт единиц недоступен"
        return result
    if r <= 0:
        result["reason"] = "результат не превышает базовую линию"
        return result

    ratio = half_width / r
    result["h_over_r"] = ratio
    if ratio >= 1:
        result["reason"] = "неопределённость не меньше самого результата"
        return result

    unc = min(1.0, max(0.0, ratio - UNC_THRESHOLD))
    adjusted = r * (1 - unc)
    result.update(
        unc_share=unc,
        r_adjusted_tco2e=adjusted,
        buffer_tco2e=adjusted * BUFFER_SHARE,
        units=int(math.floor(adjusted * (1 - BUFFER_SHARE))),
    )
    return result


def build_aoi(data_dir: Path, meta: dict, baseline: list[dict], maps_dir: Path | None) -> dict:
    box = (
        float(meta["bbox_west"]),
        float(meta["bbox_south"]),
        float(meta["bbox_east"]),
        float(meta["bbox_north"]),
    )
    aoi = meta["aoi_id"]
    series = [read_year(data_dir, aoi, year, box) for year in range(2015, 2025)]
    by_year = {row["year"]: row for row in series}
    area = series[0]["area_ha"]

    base_rows = [r for r in baseline if r["aoi_id"] == aoi]
    base_stock = {int(r["year_start"]): float(r["baseline_stock_start_tc_ha"]) for r in base_rows}
    base_stock[2029] = float(
        next(r for r in base_rows if r["year_end"] == "2029")["baseline_stock_end_tc_ha"]
    )

    def period(start: int, end: int) -> dict:
        t0, t1 = by_year[start], by_year[end]
        delta_stock = t1["stock_tc"] - t0["stock_tc"]
        e_proj = -delta_stock * CO2_PER_C
        sigma_delta = math.sqrt(
            max(
                t0["sigma_stock_tc"] ** 2
                + t1["sigma_stock_tc"] ** 2
                - 2 * RHO_TEMPORAL * t0["sigma_stock_tc"] * t1["sigma_stock_tc"],
                0.0,
            )
        )
        sigma_e = sigma_delta * CO2_PER_C
        half = K_SIGMA * sigma_e
        e_base = -area * (base_stock[end] - base_stock[start]) * CO2_PER_C
        units = potential_units(e_proj, e_base, half)

        # Чувствительность к допущениям о корреляции: число единиц целиком
        # определяется ими, и это главный вывод, а не техническая деталь.
        grid = []
        for rs in RHO_SPATIAL_GRID:
            row = []
            for rt in RHO_TEMPORAL_GRID:
                s0 = sigma_pair(t0["_sd_sum"], t0["_sd_sq_sum"], rs)
                s1 = sigma_pair(t1["_sd_sum"], t1["_sd_sq_sum"], rs)
                sd_delta = math.sqrt(max(s0**2 + s1**2 - 2 * rt * s0 * s1, 0.0)) * CO2_PER_C
                cell = potential_units(e_proj, e_base, K_SIGMA * sd_delta)
                row.append(
                    {
                        "rho_spatial": rs,
                        "rho_temporal": rt,
                        "h_tco2e": K_SIGMA * sd_delta,
                        "h_over_r": cell["h_over_r"],
                        "units": cell["units"],
                    }
                )
            grid.append(row)

        return {
            "year_start": start,
            "year_end": end,
            "years": end - start,
            "area_ha": area,
            "c_start_t_ha": t0["c_t_ha"],
            "c_end_t_ha": t1["c_t_ha"],
            "stock_start_tc": t0["stock_tc"],
            "stock_end_tc": t1["stock_tc"],
            "delta_stock_tc": delta_stock,
            "e_tco2e": e_proj,
            "e_per_ha_year": e_proj / (area * (end - start)),
            "sigma_e_tco2e": sigma_e,
            "lower_tco2e": e_proj - half,
            "upper_tco2e": e_proj + half,
            "baseline_c_start_t_ha": base_stock[start],
            "baseline_c_end_t_ha": base_stock[end],
            **units,
            "value_rub": {
                name: (units["units"] or 0) * price for name, price in PRICES.items()
            },
            "sensitivity": grid,
        }

    return {
        "aoi_id": aoi,
        "maps": render_maps(data_dir, aoi, box, maps_dir) if maps_dir else None,
        "name": meta["name"],
        "region": meta["region"],
        "role": meta["selection_role"],
        "status": meta["project_status"],
        "area_ha": area,
        "area_ha_declared": float(meta["area_ha"]),
        "bbox": list(box),
        "baseline_id": meta["baseline_id"],
        "baseline_rate_tc_ha_year": float(base_rows[0]["historical_rate_tc_ha_yr"]),
        "baseline_stock_t_ha": {str(k): v for k, v in sorted(base_stock.items())},
        "series": series,
        "cover_loss": gfc_loss_by_year(data_dir, aoi, box),
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

    payload = {
        "generated_from": "ESA CCI Biomass v7.0, Hansen GFC v1.13, MODIS MCD64A1 061",
        "parameters": {
            "carbon_fraction": CF,
            "co2_per_carbon": CO2_PER_C,
            "unc_threshold": UNC_THRESHOLD,
            "buffer_share": BUFFER_SHARE,
            "leakage_tco2e": LEAKAGE,
            "rho_spatial": RHO_SPATIAL,
            "rho_temporal": RHO_TEMPORAL,
            "k_sigma": K_SIGMA,
            "treecover_threshold_pct": TREECOVER_THRESHOLD,
            "prices_rub": PRICES,
        },
        "areas": [build_aoi(args.data, meta, baseline, args.maps) for meta in areas],
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
