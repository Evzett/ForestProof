"""Годовой ряд запаса и базовая линия по контуру — из скачанных тайлов.

Зачем. Набор кейса приходит с готовыми растрами по каждому участку и
готовой базовой линией в `baseline.csv`. Расширенный набор на двенадцать
участков пришёл без того и без другого: есть только контуры. Значит,
либо ждать растры от команды, либо собрать то же самое из открытых
тайлов, которые мы и так качаем.

Что здесь считается и что берётся как есть.

    ряд запаса      — считается: те же формулы, что в основном расчёте,
                      по окну тайла вместо вложенного файла;
    базовая линия   — выводится по формуле кейса из документа 06:
                      g = (c̄₂₀₁₉ − c̄₂₀₁₅) / 4
                      c_base(y) = max(0, c̄₂₀₁₉ + g·(y − 2019))

Второе важно пометить. У четырёх исходных участков базовая линия задана
набором, у остальных — выведена нами по формуле. Это разные основания,
и в выгрузке они различаются полем `source_kind`: путать «так сказано в
кейсе» с «так посчитали мы» нельзя.

Перед работой скрипт сверяется с известным ответом: считает RU_TVER_01
по тайлу и сравнивает с `baseline.csv`. Если расхождение больше
допуска, дальше идти нельзя — значит окно читается не то.

Запуск:
    python tools/build_area_from_tiles.py --check
    python tools/build_area_from_tiles.py --areas data/areas.expanded.csv \\
        --geojson data/areas.expanded.geojson --out data/baseline.derived.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from forestproof_core.case_calculation import CaseCalculationConfig  # noqa: E402
from fetch import _tile_name_cci, cci_url  # noqa: E402
from geotiff import read_geotiff  # noqa: E402

CONFIG = CaseCalculationConfig()
CACHE = Path("data/cache/cci-biomass")

BASELINE_START = 2015
BASELINE_ANCHOR = 2019
YEARS = range(2015, 2025)

# Допуск сверки с набором. Тайл и вложенный файл — один и тот же продукт,
# но вложенный обрезан заранее и по краю может отличаться на доли пикселя.
TOLERANCE_TC_HA = 0.01


def tile_name(lon: float, lat: float, band: str, year: int) -> str:
    """Имя файла тайла в кэше.

    Собирается теми же функциями, что и адрес загрузки: имя файла и имя
    в каталоге поставщика обязаны совпадать, и держать для этого вторую
    копию правила значит однажды разойтись с ней.
    """
    return cci_url(_tile_name_cci(lon, lat), year, band).rsplit("/", 1)[-1]


def pixel_area_ha(lat_centers: np.ndarray, lon_step: float, lat_step: float) -> np.ndarray:
    """Площадь пикселя в гектарах по широте его центра.

    На градусной сетке пиксель не квадратный и не равен гектару: на 56°
    северной широты он около 0,54 га. Брать гектар значило бы ошибиться
    почти вдвое.
    """
    m_lat = 111_132.92 - 559.82 * np.cos(2 * np.radians(lat_centers))
    m_lon = 111_412.84 * np.cos(np.radians(lat_centers)) - 93.5 * np.cos(
        3 * np.radians(lat_centers)
    )
    return (lat_step * m_lat) * (lon_step * m_lon) / 10_000.0


def bbox_weights(raster, box: tuple[float, float, float, float]) -> np.ndarray:
    """Доля площади каждого пикселя, попавшая внутрь рамки."""
    rows, cols = raster.data.shape[1], raster.data.shape[2]
    lat_edges = raster.lat_origin - np.arange(rows + 1) * raster.lat_step
    lon_edges = raster.lon_origin + np.arange(cols + 1) * raster.lon_step

    lat_overlap = np.clip(
        np.minimum(lat_edges[:-1], box[3]) - np.maximum(lat_edges[1:], box[1]), 0, None
    )
    lon_overlap = np.clip(
        np.minimum(lon_edges[1:], box[2]) - np.maximum(lon_edges[:-1], box[0]), 0, None
    )
    share = (lat_overlap[:, None] / raster.lat_step) * (lon_overlap[None, :] / raster.lon_step)

    lat_centers = raster.lat_origin - (np.arange(rows) + 0.5) * raster.lat_step
    full = pixel_area_ha(lat_centers, raster.lon_step, raster.lat_step)
    return share * full[:, None]


def read_year_from_tile(box: tuple[float, float, float, float], year: int) -> dict:
    """Запас и его погрешность за год по окну тайла."""
    lon = (box[0] + box[2]) / 2
    lat = (box[1] + box[3]) / 2

    agb_path = CACHE / tile_name(lon, lat, "AGB", year)
    sd_path = CACHE / tile_name(lon, lat, "AGB_SD", year)
    for path in (agb_path, sd_path):
        if not path.exists():
            raise SystemExit(f"нет тайла {path.name}\nсначала: python tools/fetch.py --bbox ...")

    agb = read_geotiff(str(agb_path), bbox=box)
    weights = bbox_weights(agb, box)
    inside = weights > 0
    if not inside.any():
        raise SystemExit("контур не попал в тайл")

    values = agb.band(0).astype(float)
    valid = inside & np.isfinite(values)
    area_ha = float(weights[valid].sum())

    carbon = values * CONFIG.carbon_fraction
    stock_tc = float((carbon * weights)[valid].sum())

    sd = read_geotiff(str(sd_path), bbox=box)
    sd_values = sd.band(0).astype(float) * CONFIG.carbon_fraction
    sd_mean = float((sd_values * weights)[valid].sum() / max(area_ha, 1e-9))

    return {
        "year": year,
        "area_ha": area_ha,
        "stock_tc": stock_tc,
        "c_t_ha": stock_tc / max(area_ha, 1e-9),
        "sd_t_ha": sd_mean,
    }


def baseline_for(series: dict[int, float]) -> dict:
    """Базовая линия по формуле кейса.

    Отрицательная историческая динамика не переворачивается и не
    обнуляется: кейс требует только обрезать сам запас снизу нулём.
    Участок с падающим запасом получает падающую базовую линию — и
    именно поэтому на нём «потеря без проекта» выходит больше
    фактической.
    """
    mean_2015 = series[BASELINE_START]
    mean_2019 = series[BASELINE_ANCHOR]
    rate = (mean_2019 - mean_2015) / (BASELINE_ANCHOR - BASELINE_START)

    def stock(year: int) -> float:
        return max(0.0, mean_2019 + rate * (year - BASELINE_ANCHOR))

    return {"mean_2015": mean_2015, "mean_2019": mean_2019, "rate": rate, "stock": stock}


def check_against_case() -> None:
    """Сверка с известным ответом до всякой работы."""
    rows = list(csv.DictReader(open("data/methodology/baseline.csv", encoding="utf-8-sig")))
    reference = next(r for r in rows if r["aoi_id"] == "RU_TVER_01")
    areas = list(csv.DictReader(open("data/areas.csv", encoding="utf-8-sig")))
    meta = next(a for a in areas if a["aoi_id"] == "RU_TVER_01")
    box = (
        float(meta["bbox_west"]),
        float(meta["bbox_south"]),
        float(meta["bbox_east"]),
        float(meta["bbox_north"]),
    )

    print("сверка с набором по RU_TVER_01")
    ok = True
    for year, field in ((2015, "reference_mean_2015_tc_ha"), (2019, "reference_mean_2019_tc_ha")):
        mine = read_year_from_tile(box, year)["c_t_ha"]
        theirs = float(reference[field])
        delta = abs(mine - theirs)
        mark = "совпало" if delta <= TOLERANCE_TC_HA else "РАСХОЖДЕНИЕ"
        if delta > TOLERANCE_TC_HA:
            ok = False
        print(f"  {year}: из тайла {mine:.6f}, в наборе {theirs:.6f}, разница {delta:.6f} — {mark}")

    if not ok:
        raise SystemExit(
            "\nЧисла из тайла расходятся с набором. Дальше идти нельзя: значит,\n"
            "окно читается не то, и выведенная базовая линия будет неверна."
        )
    print("  сверка пройдена\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--areas", type=Path, default=Path("data/areas.expanded.csv"))
    parser.add_argument("--geojson", type=Path, default=Path("data/areas.expanded.geojson"))
    parser.add_argument("--out", type=Path, default=Path("data/baseline.derived.csv"))
    parser.add_argument("--series-out", type=Path, default=Path("data/series.derived.json"))
    parser.add_argument("--check", action="store_true", help="только сверка, без выгрузки")
    args = parser.parse_args()

    check_against_case()
    if args.check:
        return

    known = {r["aoi_id"] for r in csv.DictReader(open("data/areas.csv", encoding="utf-8-sig"))}
    rows = list(csv.DictReader(open(args.areas, encoding="utf-8-sig")))

    baseline_rows: list[dict] = []
    all_series: dict[str, dict] = {}

    for meta in rows:
        aoi = meta["aoi_id"]
        box = (
            float(meta["bbox_west"]),
            float(meta["bbox_south"]),
            float(meta["bbox_east"]),
            float(meta["bbox_north"]),
        )
        try:
            series = {y: read_year_from_tile(box, y) for y in YEARS}
        except SystemExit as error:
            print(f"{aoi}: пропущен — {error}")
            continue

        means = {y: series[y]["c_t_ha"] for y in YEARS}
        base = baseline_for(means)
        source_kind = "задана набором" if aoi in known else "выведена нами по формуле кейса"

        all_series[aoi] = {
            "source_kind": source_kind,
            "area_ha": series[2019]["area_ha"],
            "series": [
                {
                    "year": y,
                    "c_t_ha": round(series[y]["c_t_ha"], 9),
                    "agb_sd_t_ha": round(series[y]["sd_t_ha"], 9),
                    "stock_tc": round(series[y]["stock_tc"], 6),
                }
                for y in YEARS
            ],
        }

        for year in range(2019, 2029):
            baseline_rows.append(
                {
                    "baseline_id": "HIST-AGB-2015-2019-v1",
                    "aoi_id": aoi,
                    "year_start": year,
                    "year_end": year + 1,
                    "pool": "AGB",
                    "reference_mean_2015_tc_ha": round(base["mean_2015"], 9),
                    "reference_mean_2019_tc_ha": round(base["mean_2019"], 9),
                    "historical_rate_tc_ha_yr": round(base["rate"], 9),
                    "baseline_stock_start_tc_ha": round(base["stock"](year), 9),
                    "baseline_stock_end_tc_ha": round(base["stock"](year + 1), 9),
                    "baseline_delta_tc_ha": round(
                        base["stock"](year + 1) - base["stock"](year), 9
                    ),
                    "kind": "сценарное допущение",
                    "history_product": "ESA CCI Biomass v7.0",
                    "source_kind": source_kind,
                    "clipped_at_zero": str(base["stock"](year + 1) <= 0).lower(),
                }
            )

        print(
            f"{aoi:<18} площадь {series[2019]['area_ha']:>9.2f} га  "
            f"c2019 {means[2019]:>7.2f}  g {base['rate']:>+7.3f} т C/га/год  · {source_kind}"
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(baseline_rows[0].keys()))
        writer.writeheader()
        writer.writerows(baseline_rows)
    args.series_out.write_text(
        json.dumps(all_series, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nзаписано {args.out} — {len(baseline_rows)} строк")
    print(f"записано {args.series_out} — {len(all_series)} участков")


if __name__ == "__main__":
    main()
