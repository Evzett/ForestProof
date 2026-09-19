"""Поиск контуров, у которых потенциальных единиц больше нуля.

Зачем. На всех участках набора `Q = 0`, и причина одна: `R = E_base − E ≤ 0`,
результат не превышает базовую линию. Для демонстрации этого мало: сервис,
который всегда отвечает нулём, снаружи неотличим от сервиса, который
ничего не считает. Нужны примеры, где виден весь путь до числа.

Что должно сойтись. Два условия разом:

1. `R > 0` — за период участок потерял меньше, чем предсказывает его
   собственная базовая линия, или накопил, когда линия падала;
2. `H / R < 1` — полуширина интервала меньше самого результата. Условие
   жёстче первого: `H` растёт с площадью и с разбросом `AGB_SD`.

Отсюда портрет искомого участка: **резкая потеря запаса до 2019 года и
восстановление после**. Падение 2015→2019 задаёт круто падающую базовую
линию, восстановление 2019→2024 даёт небольшое или отрицательное `E`, и
разность выходит большой и положительной.

Как ищется. Область читается из продукта ОДИН раз — пять окон на всю
рамку поиска, — а дальше окна двигаются по массиву в памяти. Читать
продукт на каждое окно значило бы сотни обращений в облако: поиск шёл бы
часами вместо минут.

Формулы не дублируются: для каждого окна вызываются те же
`calculate_year` и `calculate_period`, что считают участки набора и
работают в сервисе. Найденный контур в сервисе даст ровно это же число.

Запуск:
    python tools/find_positive_units.py --bbox 40 58 44 60
    python tools/find_positive_units.py --bbox 40 58 44 60 --top 3
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from forestproof_core.case_calculation import (  # noqa: E402
    CaseCalculationConfig,
    calculate_period,
    calculate_year,
)
from tools.extract_case_data import open_cci  # noqa: E402

BASELINE_START = 2015
BASELINE_ANCHOR = 2019


def region_rasters(bbox, years: tuple[int, int]):
    """Все нужные годы одной рамкой.

    Читается 2015 (начало истории), 2019 (опора базовой линии) и оба года
    периода. Часто это три-четыре файла, а не четыре: годы совпадают.
    """
    wanted = sorted({BASELINE_START, BASELINE_ANCHOR, years[0], years[1]})
    box = {"type": "Polygon", "coordinates": [[
        [bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]], [bbox[0], bbox[1]],
    ]]}
    out = {}
    for year in wanted:
        print(f"  читаем {year}…", flush=True)
        out[year] = open_cci(Path("data"), "SEARCH", year, box)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"),
                        default=[40.0, 58.0, 43.0, 59.5], help="рамка поиска")
    parser.add_argument("--years", type=int, nargs=2, default=[2019, 2024])
    parser.add_argument("--window", type=int, default=32,
                        help="сторона окна в пикселях продукта (~100 м каждый)")
    parser.add_argument("--stride", type=int, default=16, help="шаг сетки в пикселях")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path("examples"))
    args = parser.parse_args()

    rows = list(csv.DictReader(open("data/methodology/parameters.csv", encoding="utf-8-sig")))
    config = CaseCalculationConfig.from_parameter_rows(rows)
    years = tuple(args.years)

    print("Читаем область из продукта (один раз на весь поиск):")
    rasters = region_rasters(args.bbox, years)
    grid = rasters[years[0]].grid

    # Веса — площадь каждого пикселя в гектарах. Считаются один раз на всю
    # область тем же способом, что и в расчёте, дальше режутся по окнам.
    from forestproof_core.case_calculation import pixel_intersection_weights

    rows_n, cols_n = rasters[years[0]].agb.shape
    full_box = (args.bbox[0], args.bbox[1], args.bbox[2], args.bbox[3])
    weights_full = pixel_intersection_weights(grid, full_box)

    print(f"область {rows_n}×{cols_n} пикселей, окно {args.window}, шаг {args.stride}")

    found: list[dict] = []
    checked = 0

    for row0 in range(0, rows_n - args.window + 1, args.stride):
        for col0 in range(0, cols_n - args.window + 1, args.stride):
            sl = (slice(row0, row0 + args.window), slice(col0, col0 + args.window))
            w = weights_full[sl]
            if w.sum() <= 0:
                continue

            readings = {}
            bad = False
            for year, raster in rasters.items():
                reading = calculate_year(year, raster.agb[sl], raster.sd[sl], w, config)
                if reading.get("c_t_ha") is None:
                    bad = True
                    break
                readings[year] = reading
            if bad:
                continue

            checked += 1
            c_2015 = readings[BASELINE_START]["c_t_ha"]
            c_2019 = readings[BASELINE_ANCHOR]["c_t_ha"]
            rate = (c_2019 - c_2015) / (BASELINE_ANCHOR - BASELINE_START)

            def stock(year: int, anchor=c_2019, g=rate) -> float:
                return max(0.0, anchor + g * (year - BASELINE_ANCHOR))

            result = calculate_period(
                readings[years[0]], readings[years[1]], stock(years[0]), stock(years[1]), config
            )
            units = result.get("units")
            if not units:
                continue

            west = grid.lon_origin + col0 * grid.lon_step
            north = grid.lat_origin - row0 * grid.lat_step
            east = west + args.window * grid.lon_step
            south = north - args.window * grid.lat_step
            found.append(
                {
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [round(west, 6), round(south, 6)],
                            [round(east, 6), round(south, 6)],
                            [round(east, 6), round(north, 6)],
                            [round(west, 6), round(north, 6)],
                            [round(west, 6), round(south, 6)],
                        ]],
                    },
                    "area_ha": readings[years[0]]["area_ha"],
                    "c_2015": c_2015,
                    "c_2019": c_2019,
                    "baseline_rate": rate,
                    **{k: result.get(k) for k in
                       ("e_tco2e", "e_base_tco2e", "r_tco2e", "h_tco2e", "h_over_r", "units", "unc_share")},
                }
            )
            print(
                f"  {west:7.3f} {south:6.3f}  {found[-1]['area_ha']:7.1f} га  "
                f"R {result['r_tco2e']:>11,.0f}  H/R {result['h_over_r']:.3f}  "
                f"единиц {units:>8,}".replace(",", " "),
                flush=True,
            )

    print(f"\nпроверено окон: {checked}, с единицами: {len(found)}")
    if not found:
        print("подходящих окон не нашлось — расширьте рамку или измените размер окна")
        return

    found.sort(key=lambda r: r["units"], reverse=True)
    args.out.mkdir(parents=True, exist_ok=True)

    for index, row in enumerate(found[: args.top], start=1):
        feature = {
            "type": "Feature",
            "properties": {
                "name": f"Пример {index}: потенциальных единиц {row['units']}",
                "area_ha": round(row["area_ha"], 2),
                "units": row["units"],
                "r_tco2e": round(row["r_tco2e"], 1),
                "h_over_r": round(row["h_over_r"], 4),
                "baseline_rate_tc_ha_yr": round(row["baseline_rate"], 4),
                "c_2015_tc_ha": round(row["c_2015"], 3),
                "c_2019_tc_ha": round(row["c_2019"], 3),
                "note": (
                    "Окно найдено перебором по продукту ESA CCI Biomass v7.0. "
                    "Базовая линия выведена по формуле кейса из собственной истории "
                    "2015→2019, как её выводит сервис для любого загруженного контура."
                ),
            },
            "geometry": row["geometry"],
        }
        target = args.out / f"primer-{index}-edinic-{row['units']}.geojson"
        target.write_text(
            json.dumps({"type": "FeatureCollection", "features": [feature]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"записан {target}")


if __name__ == "__main__":
    main()
