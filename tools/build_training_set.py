"""Сборка обучающей выборки для модели устойчивости — KAN-68.

Четырёх участков набора для обучения не хватает: меньший класс — одно
наблюдение. Но тайлы, которые мы уже скачали, покрывают 10°×10°, то есть
пол-европейской России. Внутри них можно нарезать сотни участков того же
размера и посчитать по ним те же признаки — по тем же растрам, без
единого нового источника.

ГЛАВНОЕ — РАЗДЕЛЕНИЕ ВО ВРЕМЕНИ.

Если метку брать как «потеря покрова по Hansen», а признак — как «доля
потерь по Hansen», модель предсказывает собственный вход: точность
выходит прекрасная и бессмысленная. Поэтому:

    признаки  — только по данным до 2019 года включительно;
    метка     — потеря покрова за 2020–2024.

Это настоящая предсказательная задача без утечки и ровно то, что значит
«устойчивость результата на горизонте кредитования»: проверяем подход
на прошедшем пятилетии, применяем вперёд.

Запуск:
    python tools/build_training_set.py --tile 60N_030E --count 400
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path

import numpy as np

from geotiff import read_geotiff

# Размер нарезаемого участка. Взят как у участков набора — около 1800 га,
# то есть сторона примерно 0,064° по долготе и 0,04° по широте.
PLOT_LON = 0.064
PLOT_LAT = 0.040

# Граница леса: участок без деревьев в обучение не идёт — на нём нечего
# терять, и он только раздувает отрицательный класс.
MIN_TREECOVER_PCT = 30
MIN_FOREST_SHARE = 0.30

# Порог положительного класса: доля площади, потерявшая покров за
# 2020–2024. Один процент — это примерно 18 га на нашем размере участка.
LABEL_LOSS_PCT = 1.0

FEATURE_YEARS_END = 19  # lossyear 19 = 2019
LABEL_YEARS = range(20, 25)  # 2020–2024


def pixel_area_ha(lat_centers: np.ndarray, lon_step: float, lat_step: float) -> np.ndarray:
    """Площадь пикселя в гектарах по широте его центра."""
    m_lat = 111_132.92 - 559.82 * np.cos(2 * np.radians(lat_centers))
    m_lon = 111_412.84 * np.cos(np.radians(lat_centers)) - 93.5 * np.cos(
        3 * np.radians(lat_centers)
    )
    return (lat_step * m_lat) * (lon_step * m_lon) / 10_000.0


def weights_for(raster) -> np.ndarray:
    rows, cols = raster.data.shape[1], raster.data.shape[2]
    lat_centers = raster.lat_origin - (np.arange(rows) + 0.5) * raster.lat_step
    per_row = pixel_area_ha(lat_centers, raster.lon_step, raster.lat_step)
    return np.repeat(per_row[:, None], cols, axis=1)


def tile_bounds(tile: str) -> tuple[float, float, float, float]:
    """Границы тайла Hansen из его имени: 60N_030E."""
    lat_part, lon_part = tile.split("_")
    lat_top = int(lat_part[:-1]) * (1 if lat_part[-1] == "N" else -1)
    lon_left = int(lon_part[:-1]) * (1 if lon_part[-1] == "E" else -1)
    return (lon_left, lat_top - 10, lon_left + 10, lat_top)


def sample_plot(
    loss_path: Path,
    cover_path: Path,
    box: tuple[float, float, float, float],
    feature_end: int = FEATURE_YEARS_END,
    label_years: range | None = None,
) -> dict | None:
    """Признаки и метка по одному участку.

    Возвращает None, если участок не лесной: обучать различать поле
    от поля бессмысленно, а отрицательный класс от этого раздувается.

    Окно признаков сдвигается параметрами. Это нужно, чтобы применить
    обученную модель вперёд: признаки считаются по последним девятнадцати
    годам, какие есть, и модель отвечает про следующую пятилетку. Длина
    окна при этом та же, что при обучении, иначе признаки означали бы
    не то, на чём модель училась.
    """
    if label_years is None:
        label_years = LABEL_YEARS
    feature_start = feature_end - (FEATURE_YEARS_END - 1)
    loss = read_geotiff(str(loss_path), bbox=box)
    cover = read_geotiff(str(cover_path), bbox=box)

    lossyear = loss.band(0).astype(int)
    treecover = cover.band(0).astype(float)
    weights = weights_for(loss)

    total_ha = float(weights.sum())
    if total_ha <= 0:
        return None

    forest = treecover >= MIN_TREECOVER_PCT
    forest_share = float(weights[forest].sum() / total_ha)
    if forest_share < MIN_FOREST_SHARE:
        return None

    # --- признаки: только внутри окна признаков ---
    past = (lossyear >= feature_start) & (lossyear <= feature_end) & forest
    past_ha = float(weights[past].sum())

    years_with_loss = 0
    yearly = []
    for code in range(feature_start, feature_end + 1):
        year_ha = float(weights[(lossyear == code) & forest].sum())
        yearly.append(year_ha)
        if year_ha / total_ha * 100 > 0.1:
            years_with_loss += 1

    # последние три года окна признаков
    recent_ha = sum(yearly[-3:])
    peak_ha = max(yearly) if yearly else 0.0
    mean_cover = float((treecover * weights)[forest].sum() / max(weights[forest].sum(), 1e-9))

    # --- метка: потеря за годы после окна признаков, в признаки не входит ---
    future = np.isin(lossyear, list(label_years)) & forest
    future_ha = float(weights[future].sum())
    future_pct = future_ha / total_ha * 100

    return {
        "lon_west": round(box[0], 5),
        "lat_south": round(box[1], 5),
        "lon_east": round(box[2], 5),
        "lat_north": round(box[3], 5),
        "area_ha": round(total_ha, 2),
        "forest_share": round(forest_share, 4),
        "mean_treecover_pct": round(mean_cover, 2),
        "loss_share_2001_2019_pct": round(past_ha / total_ha * 100, 4),
        "loss_years_2001_2019": years_with_loss,
        "recent_loss_2017_2019_pct": round(recent_ha / total_ha * 100, 4),
        "peak_year_loss_pct": round(peak_ha / total_ha * 100, 4),
        "future_loss_2020_2024_pct": round(future_pct, 4),
        "label": int(future_pct > LABEL_LOSS_PCT),
        "feature_window": [2000 + feature_start, 2000 + feature_end],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tile",
        nargs="+",
        default=["60N_030E"],
        help="один или несколько тайлов; участки нарезаются из каждого поровну",
    )
    parser.add_argument("--cache", type=Path, default=Path("data/cache/hansen-gfc"))
    parser.add_argument("--count", type=int, default=400, help="сколько участков нарезать")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--out", type=Path, default=Path("data/training_set.csv"))
    args = parser.parse_args()

    rng = random.Random(args.seed)
    rows: list[dict] = []
    skipped = 0

    # Квота на тайл. Один регион — это один тип хозяйства и один режим
    # рубок; модель, обученная на нём, описывает его, а не лес вообще.
    # Поэтому участки берутся из каждого тайла поровну.
    per_tile = math.ceil(args.count / len(args.tile))

    for tile in args.tile:
        loss_path = args.cache / f"Hansen_GFC-2024-v1.12_lossyear_{tile}.tif"
        cover_path = args.cache / f"Hansen_GFC-2024-v1.12_treecover2000_{tile}.tif"
        for path in (loss_path, cover_path):
            if not path.exists():
                raise SystemExit(
                    f"нет файла {path}\nсначала: python tools/fetch.py --bbox <W S E N> --cover"
                )

        west, south, east, north = tile_bounds(tile)
        # Отступаем от краёв тайла: участок на границе вылезет за его пределы,
        # и окно придёт обрезанным без предупреждения.
        west, south = west + 0.2, south + 0.2
        east, north = east - 0.2 - PLOT_LON, north - 0.2 - PLOT_LAT

        taken = 0
        attempts = 0
        limit = per_tile * 8

        while taken < per_tile and attempts < limit:
            attempts += 1
            lon = rng.uniform(west, east)
            lat = rng.uniform(south, north)
            box = (lon, lat, lon + PLOT_LON, lat + PLOT_LAT)
            try:
                row = sample_plot(loss_path, cover_path, box)
            except (ValueError, IndexError):
                skipped += 1
                continue
            if row is None:
                skipped += 1
                continue
            row["tile"] = tile
            rows.append(row)
            taken += 1
            if taken % 50 == 0:
                print(f"  {tile}: {taken} участков, положительных {sum(r['label'] for r in rows)}")

        print(f"{tile}: взято {taken}, пропущено нелесных за проход {attempts - taken}")

    if not rows:
        raise SystemExit("не удалось набрать ни одного лесного участка")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    positives = sum(r["label"] for r in rows)
    meta = {
        "tiles": list(args.tile),
        "plots": len(rows),
        "positives": positives,
        "negatives": len(rows) - positives,
        "minority_class": min(positives, len(rows) - positives),
        "skipped_non_forest": skipped,
        "plot_size_deg": [PLOT_LON, PLOT_LAT],
        "label_rule": f"потеря покрова за 2020–2024 больше {LABEL_LOSS_PCT} % площади",
        "feature_window": "2001–2019",
        "label_window": "2020–2024",
        "leakage_note": (
            "Признаки считаются строго до 2019 года, метка — за 2020–2024. "
            "Пересечения периодов нет, поэтому модель предсказывает будущее, "
            "а не пересказывает собственный вход."
        ),
        "source": f"Hansen GFC v1.12, тайлы {', '.join(args.tile)}",
    }
    args.out.with_suffix(".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    print(f"записано {args.out}")
    print(f"участков: {len(rows)}, положительных: {positives}, отрицательных: {len(rows) - positives}")
    print(f"меньший класс: {meta['minority_class']}")
    print(f"пропущено нелесных: {skipped}")


if __name__ == "__main__":
    main()
