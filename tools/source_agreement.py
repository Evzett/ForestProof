"""Расхождения между источниками, в числах — KAN-61.

Четыре продукта, четыре разрешения, четыре проекции. Они не обязаны
соглашаться, и там, где расходятся, важно понимать — почему.

    Hansen lossyear   30 м    градусы            факт потери покрова
    Sentinel-2 dNBR   20 м    UTM зоны сцены     падение спектрального индекса
    CCI Biomass      100 м    градусы            запас биомассы
    MODIS MCD64A1    463 м    синусоидальная     признак горения

Общий приём. Каждое сравнение сводится на сетку БОЛЕЕ ГРУБОГО из двух
источников, и пересчёт всегда идёт «из грубой сетки в мелкую»: берётся
центр грубого пикселя, переводится в проекцию мелкого, оттуда читается
значение. Так не нужен обратный перевод из UTM и из синусоидальной
проекции — а именно там ошибка была бы молчаливой: полигон всё равно
нарисуется, просто не в том месте.

Чего здесь нет и быть не может. Согласие двух спутниковых продуктов —
не валидация. Оба они меряют отражённый свет, оба могут ошибаться
одинаково, и ни один из них не был на участке. Постановка кейса
(раздел 6.4) говорит об этом прямо. Числа ниже отвечают на вопрос
«насколько источники расходятся», а не «который из них прав».

Запуск:
    python tools/source_agreement.py
    python tools/source_agreement.py --aoi RU_MORDOVIA_03
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geotiff import read_geotiff  # noqa: E402
from sentinel_evidence import (  # noqa: E402
    VALID_SCL,
    _polygon_mask,
    _read_reflectance,
    _utm_forward,
    utm_zone,
)

# Порог падения NBR, за которым говорят о нарушении покрова. Значение
# из практики дистанционного зондирования (умеренная тяжесть по шкале
# USGS), а не откалиброванное по нашим участкам: калибровать не на чем,
# наземных данных нет.
DNBR_THRESHOLD = 0.27

MIN_USABLE = 0.50

MODIS_CACHE = Path("data/cache/modis")
EARTH_RADIUS = 6371007.181
TILE_METERS = 1111950.5196666666
TILE_PIXELS = 2400
PIXEL_METERS = TILE_METERS / TILE_PIXELS
X_MIN = -20015109.354
Y_MAX = 10007554.677


# --- общая машинерия ---------------------------------------------------


def grid_centers(raster) -> tuple[np.ndarray, np.ndarray]:
    """Центры пикселей растра, заданного в градусах."""
    rows, cols = raster.data.shape[1:]
    lon = raster.lon_origin + (np.arange(cols) + 0.5) * raster.lon_step
    lat = raster.lat_origin - (np.arange(rows) + 0.5) * raster.lat_step
    return lon, lat


def _utm_forward_vec(lon: np.ndarray, lat: np.ndarray, zone: int):
    """Та же формула, что в sentinel_evidence, но по массиву.

    Переписывать формулу на numpy нельзя: разойдётся со скалярной
    версией, и расхождение будет тихим. Поэтому здесь цикл по ней же —
    участок это десятки тысяч пикселей, не миллионы.
    """
    xs = np.empty(lon.shape, dtype=float)
    ys = np.empty(lon.shape, dtype=float)
    flat_lon, flat_lat = lon.ravel(), lat.ravel()
    fx, fy = xs.ravel(), ys.ravel()
    for i in range(flat_lon.size):
        fx[i], fy[i] = _utm_forward(float(flat_lon[i]), float(flat_lat[i]), zone)
    return fx.reshape(lon.shape), fy.reshape(lon.shape)


def sample_utm_raster(values: np.ndarray, raster, lon: np.ndarray, lat: np.ndarray, zone: int):
    """Значения растра в UTM в точках, заданных в градусах.

    Ближайший пиксель, без интерполяции: источник дискретный, и
    сглаживать границу нарушения значило бы её выдумывать.
    """
    x, y = _utm_forward_vec(lon, lat, zone)
    col = ((x - raster.lon_origin) / raster.lon_step).astype(int)
    row = ((raster.lat_origin - y) / raster.lat_step).astype(int)
    rows, cols = values.shape
    ok = (col >= 0) & (col < cols) & (row >= 0) & (row < rows)
    out = np.full(lon.shape, np.nan)
    out[ok] = values[row[ok], col[ok]]
    return out, ok


def normalised_index(raster, left: int, right: int) -> np.ndarray:
    """Нормализованный индекс с тем же порогом знаменателя, что в конвейере."""
    a = raster.band(left).astype(float)
    b = raster.band(right).astype(float)
    total = a + b
    ratio = np.divide(a - b, total, out=np.full_like(a, np.nan), where=total > 0.01)
    return np.where(np.abs(ratio) <= 1.0, ratio, np.nan)


# --- источники ---------------------------------------------------------


def load_scenes(data_dir: Path, aoi: str) -> list[dict]:
    rows = []
    for name in ("scenes.csv", "scenes.derived.csv"):
        path = data_dir / name
        if not path.exists():
            continue
        with open(path, encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                if row["aoi_id"] != aoi or not row.get("reflectance_path"):
                    continue
                if float(row["scl_4_5_6_7_fraction_crop"] or 0) < MIN_USABLE:
                    continue
                rows.append(row)
    return sorted(rows, key=lambda r: r["datetime_utc"])


def pick_pair(scenes: list[dict], before_year: int, after_year: int):
    """Пара сцен «до/после» — в каждом году самая чистая внутри контура."""

    def best(year: int):
        same = [s for s in scenes if int(s["year"]) == year]
        if not same:
            return None
        return max(same, key=lambda s: float(s["scl_4_5_6_7_fraction_crop"]))

    a, b = best(before_year), best(after_year)
    return (a, b) if a and b and a["item_id"] != b["item_id"] else None


def event_pair(scenes: list[dict], data_dir: Path, aoi: str):
    """Пара сцен вплотную к событию: последняя до и первая после.

    Зачем отдельно от периода. Падение NBR затухает: гарь зарастает
    травой и подростом за один-два сезона, и к концу периода сигнал
    уже не тот, что через месяц после пожара. Сравнение двух пар
    показывает это прямо, а не рассуждением.
    """
    dates = []
    for name in ("events.csv", "events.derived.csv"):
        path = data_dir / name
        if not path.exists():
            continue
        with open(path, encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                if row.get("aoi_id") == aoi and row.get("date_min_product"):
                    dates.append(row["date_min_product"])
    if not dates:
        return None

    start = min(dates)
    moment = date.fromisoformat(start)

    def within(row, days_before: int, days_after: int) -> bool:
        taken = date.fromisoformat(row["datetime_utc"][:10])
        return -days_before <= (taken - moment).days <= days_after

    # Окно намеренно шире одного сезона. Ближайшая послепожарная сцена
    # может оказаться непригодной — над Мордовией так и вышло, — и тогда
    # ближайшее пригодное наблюдение приходится на следующее лето.
    before = [s for s in scenes if within(s, 400, 0) and s["datetime_utc"][:10] < start]
    after = [s for s in scenes if within(s, 0, 400) and s["datetime_utc"][:10] > start]
    if not before or not after:
        return None
    return max(before, key=lambda s: s["datetime_utc"]), min(after, key=lambda s: s["datetime_utc"])


def dnbr_field(data_dir: Path, before: dict, after: dict, bbox, zone: int):
    """Падение NBR между двумя сценами и маска пикселей, годных на обе даты.

    Знак: положительный dNBR означает падение, то есть возможное
    нарушение. Соглашение общепринятое, и менять его нельзя — порог
    0,27 взят из литературы именно в этом знаке.
    """
    epsg = 32600 + zone
    before_r = _read_reflectance(
        data_dir / before["reflectance_path"], before.get("processing_baseline", "")
    )
    after_r = _read_reflectance(
        data_dir / after["reflectance_path"], after.get("processing_baseline", "")
    )
    before_scl = read_geotiff(str(data_dir / before["scl_path"])).band(0)
    after_scl = read_geotiff(str(data_dir / after["scl_path"])).band(0)

    inside = _polygon_mask(before_r, bbox, epsg)
    good = inside & np.isin(before_scl, list(VALID_SCL)) & np.isin(after_scl, list(VALID_SCL))

    # Порядок каналов: B02, B03, B04, B8A, B11, B12 — NBR это B8A и B12.
    dnbr = normalised_index(before_r, 3, 5) - normalised_index(after_r, 3, 5)
    return dnbr, good, before_r, float(good.sum() / max(inside.sum(), 1))


def modis_burn_points(bbox, years: range) -> list[tuple[float, float, bool]]:
    """Центры пикселей MODIS внутри рамки и признак горения, из кэша гранул."""
    try:
        from pyhdf.SD import SD, SDC
    except ImportError:
        return []

    cols = np.arange(TILE_PIXELS)
    rows = np.arange(TILE_PIXELS)
    seen: dict[tuple[int, int], tuple[float, float, bool]] = {}

    for path in sorted(MODIS_CACHE.glob("*.hdf")):
        parts = path.stem.split(".")
        year = int(parts[1][1:5])
        if year not in years:
            continue
        tile = next(p for p in parts if p.startswith("h") and "v" in p)
        h, v = int(tile[1:3]), int(tile[4:6])

        x0 = X_MIN + h * TILE_METERS
        y0 = Y_MAX - v * TILE_METERS
        xs = x0 + (cols + 0.5) * PIXEL_METERS
        ys = y0 - (rows + 0.5) * PIXEL_METERS
        lat = np.degrees(ys / EARTH_RADIUS)
        lon = np.degrees(xs[None, :] / (EARTH_RADIUS * np.cos(np.radians(lat))[:, None]))
        inside_lat = (lat >= bbox[1]) & (lat <= bbox[3])
        inside = (lon >= bbox[0]) & (lon <= bbox[2]) & inside_lat[:, None]
        rr, cc = np.nonzero(inside)
        if rr.size == 0:
            continue

        handle = SD(str(path), SDC.READ)
        try:
            burn = handle.select("Burn Date").get()
        finally:
            handle.end()

        for r, c in zip(rr, cc):
            key = (int(r), int(c))
            fired = bool(burn[r, c] > 0)
            # Гранулы месячные: пиксель считается горевшим, если горел
            # хотя бы в одном месяце периода.
            if key not in seen or (fired and not seen[key][2]):
                seen[key] = (float(lon[r, c]), float(lat[r]), fired)
    return list(seen.values())


# --- три сравнения -----------------------------------------------------


def compare_hansen_dnbr(data_dir: Path, aoi: str, bbox, years: range, scenes, pair=None) -> dict:
    """Hansen 30 м против dNBR 20 м, на сетке Hansen."""
    pair = pair or pick_pair(scenes, min(years) - 1, max(years))
    if pair is None:
        return {"status": "нет пары годных сцен"}

    zone = utm_zone((bbox[0] + bbox[2]) / 2)
    dnbr, good, s_raster, comparable = dnbr_field(data_dir, pair[0], pair[1], bbox, zone)

    gfc = read_geotiff(str(data_dir / aoi / "GFC_2025_v1_13.tif"))
    lossyear = gfc.band(1).astype(int)
    lon, lat = grid_centers(gfc)
    lon_g, lat_g = np.meshgrid(lon, lat)
    inside = (lon_g >= bbox[0]) & (lon_g <= bbox[2]) & (lat_g >= bbox[1]) & (lat_g <= bbox[3])

    dnbr_at, in_scene = sample_utm_raster(
        np.where(good, dnbr, np.nan), s_raster, lon_g, lat_g, zone
    )
    valid = inside & in_scene & np.isfinite(dnbr_at)

    hansen_loss = valid & np.isin(lossyear, [y - 2000 for y in years])
    nbr_drop = valid & (dnbr_at >= DNBR_THRESHOLD)
    both = hansen_loss & nbr_drop
    either = hansen_loss | nbr_drop

    # pixel_area_ha отдаёт полную сетку площадей, а не колонку по широте:
    # размножать её ещё раз значит посчитать каждый пиксель столько раз,
    # сколько в растре столбцов.
    area_g = gfc.pixel_area_ha()
    assert area_g.shape == lossyear.shape
    total = float(area_g[valid].sum())
    if total <= 0:
        return {"status": "нет общей площади"}

    return {
        "status": "ок",
        "before_scene": pair[0]["item_id"],
        "after_scene": pair[1]["item_id"],
        "days_between": (
            date.fromisoformat(pair[1]["datetime_utc"][:10])
            - date.fromisoformat(pair[0]["datetime_utc"][:10])
        ).days,
        "comparable_fraction": round(comparable, 4),
        "compared_area_ha": round(total, 1),
        "hansen_loss_share": round(float(area_g[hansen_loss].sum()) / total, 4),
        "nbr_drop_share": round(float(area_g[nbr_drop].sum()) / total, 4),
        "both_share": round(float(area_g[both].sum()) / total, 4),
        "agreement_iou": (
            round(float(area_g[both].sum()) / float(area_g[either].sum()), 4)
            if either.any()
            else 0.0
        ),
        "hansen_inside_nbr": (
            round(float(area_g[both].sum()) / float(area_g[hansen_loss].sum()), 4)
            if hansen_loss.any()
            else None
        ),
    }


def compare_cci_hansen(data_dir: Path, aoi: str, bbox, years: range) -> dict:
    """CCI 100 м против Hansen 30 м, на сетке CCI (агрегация Hansen)."""
    first, last = min(years) - 1, max(years)
    cci_before = read_geotiff(str(data_dir / aoi / f"CCI_Biomass_{first}.tif"))
    cci_after = read_geotiff(str(data_dir / aoi / f"CCI_Biomass_{last}.tif"))
    gfc = read_geotiff(str(data_dir / aoi / "GFC_2025_v1_13.tif"))
    loss_mask = np.isin(gfc.band(1).astype(int), [y - 2000 for y in years])

    lon_c, lat_c = grid_centers(cci_before)
    lon_h, lat_h = grid_centers(gfc)

    # Каждый пиксель Hansen относится к той ячейке CCI, внутрь которой
    # попадает его центр. Обратное отнесение размножило бы одно значение
    # запаса на девять ячеек и завысило бы согласие.
    col_of = np.clip(
        ((lon_h - cci_before.lon_origin) / cci_before.lon_step).astype(int), 0, lon_c.size - 1
    )
    row_of = np.clip(
        ((cci_before.lat_origin - lat_h) / cci_before.lat_step).astype(int), 0, lat_c.size - 1
    )

    shape = (lat_c.size, lon_c.size)
    flat = (row_of[:, None] * lon_c.size + col_of[None, :]).ravel()
    counts = np.bincount(flat, minlength=shape[0] * shape[1]).reshape(shape)
    losses = np.bincount(
        flat, weights=loss_mask.ravel().astype(float), minlength=shape[0] * shape[1]
    ).reshape(shape)

    loss_share = np.where(counts > 0, losses / np.maximum(counts, 1), np.nan)

    before = cci_before.band(0).astype(float)
    after = cci_after.band(0).astype(float)
    for raster, values in ((cci_before, before), (cci_after, after)):
        if raster.nodata is not None:
            values[values == raster.nodata] = np.nan
    delta = after - before

    lon_g, lat_g = np.meshgrid(lon_c, lat_c)
    inside = (lon_g >= bbox[0]) & (lon_g <= bbox[2]) & (lat_g >= bbox[1]) & (lat_g <= bbox[3])
    valid = inside & (counts > 0) & np.isfinite(delta)
    if not valid.any():
        return {"status": "нет общих ячеек"}

    hansen_cell = valid & (loss_share > 0)
    cci_drop = valid & (delta < 0)
    both = hansen_cell & cci_drop
    either = hansen_cell | cci_drop
    cells = int(valid.sum())

    # Ранговая связь: по величине зависимость может быть немонотонной,
    # но порядок — то, что здесь осмысленно сравнивать.
    def ranks(values: np.ndarray) -> np.ndarray:
        order = values.argsort()
        out = np.empty(values.size)
        out[order] = np.arange(values.size, dtype=float)
        return out

    x, y = loss_share[valid], -delta[valid]
    rho = float(np.corrcoef(ranks(x), ranks(y))[0, 1]) if x.std() > 0 and y.std() > 0 else None

    return {
        "status": "ок",
        "cells_compared": cells,
        "hansen_cells_share": round(float(hansen_cell.sum()) / cells, 4),
        "cci_drop_share": round(float(cci_drop.sum()) / cells, 4),
        "both_share": round(float(both.sum()) / cells, 4),
        "agreement_iou": round(float(both.sum()) / float(either.sum()), 4) if either.any() else 0.0,
        "spearman_loss_vs_drop": None if rho is None else round(rho, 3),
        "mean_delta_where_hansen_loss": (
            round(float(np.nanmean(delta[hansen_cell])), 2) if hansen_cell.any() else None
        ),
        "mean_delta_where_no_loss": (
            round(float(np.nanmean(delta[valid & ~hansen_cell])), 2)
            if (valid & ~hansen_cell).any()
            else None
        ),
    }


def compare_modis_dnbr(data_dir: Path, aoi: str, bbox, years: range, scenes, pair=None) -> dict:
    """MODIS 463 м против dNBR 20 м, в центрах пикселей MODIS."""
    points = modis_burn_points(bbox, years)
    if not points:
        return {"status": "нет гранул MODIS в кэше за период"}

    pair = pair or pick_pair(scenes, min(years) - 1, max(years))
    if pair is None:
        return {"status": "нет пары годных сцен"}

    zone = utm_zone((bbox[0] + bbox[2]) / 2)
    dnbr, good, s_raster, _ = dnbr_field(data_dir, pair[0], pair[1], bbox, zone)

    lon = np.array([p[0] for p in points])
    lat = np.array([p[1] for p in points])
    fired = np.array([p[2] for p in points])
    values, in_scene = sample_utm_raster(np.where(good, dnbr, np.nan), s_raster, lon, lat, zone)
    ok = in_scene & np.isfinite(values)

    burned, intact = ok & fired, ok & ~fired
    return {
        "status": "ок",
        "pixels_compared": int(ok.sum()),
        "burned_pixels": int(burned.sum()),
        "mean_dnbr_burned": round(float(values[burned].mean()), 4) if burned.any() else None,
        "mean_dnbr_unburned": round(float(values[intact].mean()), 4) if intact.any() else None,
        "burned_above_threshold": (
            round(float((values[burned] >= DNBR_THRESHOLD).mean()), 4) if burned.any() else None
        ),
        "unburned_above_threshold": (
            round(float((values[intact] >= DNBR_THRESHOLD).mean()), 4) if intact.any() else None
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--aoi", action="append", help="можно указать несколько раз")
    parser.add_argument("--years", type=int, nargs=2, default=[2020, 2024])
    parser.add_argument("--out", type=Path, default=Path("data/source_agreement.json"))
    args = parser.parse_args()

    years = range(args.years[0], args.years[1] + 1)
    with open(args.data / "areas.csv", encoding="utf-8-sig") as handle:
        areas = list(csv.DictReader(handle))

    wanted = args.aoi or [a["aoi_id"] for a in areas]
    report = {
        "period": f"{args.years[0]}—{args.years[1]}",
        "dnbr_threshold": DNBR_THRESHOLD,
        "caveat": (
            "Согласие двух спутниковых продуктов не является независимой наземной "
            "валидацией: оба измеряют отражённый свет и могут ошибаться одинаково."
        ),
        "areas": {},
    }

    for meta in areas:
        aoi = meta["aoi_id"]
        if aoi not in wanted:
            continue
        if not (args.data / aoi / "GFC_2025_v1_13.tif").exists():
            print(f"{aoi:<18} растров нет локально — пропуск")
            continue

        bbox = (
            float(meta["bbox_west"]),
            float(meta["bbox_south"]),
            float(meta["bbox_east"]),
            float(meta["bbox_north"]),
        )
        scenes = load_scenes(args.data, aoi)
        near = event_pair(scenes, args.data, aoi)
        entry = {
            "hansen_vs_dnbr": compare_hansen_dnbr(args.data, aoi, bbox, years, scenes),
            "cci_vs_hansen": compare_cci_hansen(args.data, aoi, bbox, years),
            "modis_vs_dnbr": compare_modis_dnbr(args.data, aoi, bbox, years, scenes),
        }
        if near is not None:
            entry["hansen_vs_dnbr_near_event"] = compare_hansen_dnbr(
                args.data, aoi, bbox, years, scenes, pair=near
            )
            entry["modis_vs_dnbr_near_event"] = compare_modis_dnbr(
                args.data, aoi, bbox, years, scenes, pair=near
            )
        report["areas"][aoi] = entry

        one, two, three = entry["hansen_vs_dnbr"], entry["cci_vs_hansen"], entry["modis_vs_dnbr"]
        print(f"\n{aoi}")
        if one.get("status") == "ок":
            print(
                f"  Hansen vs dNBR : потеря Hansen {one['hansen_loss_share']:.1%} площади, "
                f"падение NBR {one['nbr_drop_share']:.1%}, оба {one['both_share']:.1%}, "
                f"совпадение {one['agreement_iou']:.3f}"
            )
        else:
            print(f"  Hansen vs dNBR : {one['status']}")
        if two.get("status") == "ок":
            print(
                f"  CCI vs Hansen  : ячеек {two['cells_compared']}, "
                f"с потерей Hansen {two['hansen_cells_share']:.1%}, "
                f"с падением запаса {two['cci_drop_share']:.1%}, "
                f"совпадение {two['agreement_iou']:.3f}, "
                f"ранговая связь {two['spearman_loss_vs_drop']}"
            )
        else:
            print(f"  CCI vs Hansen  : {two['status']}")
        if three.get("status") == "ок":
            print(
                f"  MODIS vs dNBR  : пикселей {three['pixels_compared']}, "
                f"горевших {three['burned_pixels']}, "
                f"средний dNBR горевших {three['mean_dnbr_burned']}, "
                f"негоревших {three['mean_dnbr_unburned']}"
            )
        else:
            print(f"  MODIS vs dNBR  : {three['status']}")

        near_one = entry.get("hansen_vs_dnbr_near_event")
        near_three = entry.get("modis_vs_dnbr_near_event")
        if near_one and near_one.get("status") == "ок":
            print(
                f"  то же вплотную к событию ({near_one['before_scene'][-14:-8]} -> "
                f"{near_one['after_scene'][-14:-8]}): падение NBR "
                f"{near_one['nbr_drop_share']:.1%} площади, совпадение "
                f"{near_one['agreement_iou']:.3f}"
            )
        if near_three and near_three.get("status") == "ок":
            print(
                f"  MODIS vs dNBR вплотную: горевших {near_three['mean_dnbr_burned']}, "
                f"негоревших {near_three['mean_dnbr_unburned']}, "
                f"выше порога у горевших {near_three['burned_above_threshold']}"
            )

    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nзаписано {args.out}")


if __name__ == "__main__":
    main()
