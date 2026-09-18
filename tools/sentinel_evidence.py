"""Sentinel-2 evidence for the MODIS fire events supplied with the case.

The input clips are already radiometrically corrected L2A reflectance.  This
module selects observations around an event, masks them with SCL, creates
offline true-colour PNGs and reports quality inside the AOI.  It deliberately
does not turn a cloudy image into evidence: the valid fraction is carried into
the result and low-quality observations are labelled as such.
"""

from __future__ import annotations

import csv
import math
from datetime import date
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image, ImageDraw

from geotiff import Raster, read_geotiff


VALID_SCL = {4, 5, 6, 7}
MIN_USABLE_FRACTION = 0.50


def _utm_forward(lon: float, lat: float, zone: int) -> tuple[float, float]:
    """WGS84 longitude/latitude to UTM, sufficient for the small case AOIs."""
    a = 6378137.0
    ecc_sq = 0.00669437999014
    k0 = 0.9996
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    ecc_prime_sq = ecc_sq / (1 - ecc_sq)
    n = a / math.sqrt(1 - ecc_sq * math.sin(lat_r) ** 2)
    t = math.tan(lat_r) ** 2
    c = ecc_prime_sq * math.cos(lat_r) ** 2
    aa = math.cos(lat_r) * (lon_r - lon0)
    m = a * (
        (1 - ecc_sq / 4 - 3 * ecc_sq**2 / 64 - 5 * ecc_sq**3 / 256) * lat_r
        - (3 * ecc_sq / 8 + 3 * ecc_sq**2 / 32 + 45 * ecc_sq**3 / 1024)
        * math.sin(2 * lat_r)
        + (15 * ecc_sq**2 / 256 + 45 * ecc_sq**3 / 1024) * math.sin(4 * lat_r)
        - 35 * ecc_sq**3 / 3072 * math.sin(6 * lat_r)
    )
    easting = k0 * n * (
        aa
        + (1 - t + c) * aa**3 / 6
        + (5 - 18 * t + t**2 + 72 * c - 58 * ecc_prime_sq) * aa**5 / 120
    ) + 500000.0
    northing = k0 * (
        m
        + n
        * math.tan(lat_r)
        * (
            aa**2 / 2
            + (5 - t + 9 * c + 4 * c**2) * aa**4 / 24
            + (61 - 58 * t + t**2 + 600 * c - 330 * ecc_prime_sq) * aa**6 / 720
        )
    )
    if lat < 0:
        northing += 10_000_000.0
    return easting, northing


def _polygon_mask(raster, bbox: tuple[float, float, float, float], epsg: int) -> np.ndarray:
    west, south, east, north = bbox
    zone = epsg % 100
    corners = [(west, south), (west, north), (east, north), (east, south)]
    pixels = []
    for lon, lat in corners:
        x, y = _utm_forward(lon, lat, zone)
        col = (x - raster.lon_origin) / raster.lon_step
        row = (raster.lat_origin - y) / raster.lat_step
        pixels.append((col, row))
    rows, cols = raster.data.shape[1:]
    image = Image.new("1", (cols, rows), 0)
    ImageDraw.Draw(image).polygon(pixels, fill=1)
    return np.asarray(image, dtype=bool)


def _scene_rows(data_dir: Path, aoi: str) -> list[dict]:
    with open(data_dir / "scenes.csv", encoding="utf-8-sig") as handle:
        rows = [r for r in csv.DictReader(handle) if r["aoi_id"] == aoi]
    return sorted(rows, key=lambda row: row["datetime_utc"])


def _paths(data_dir: Path, row: dict) -> tuple[Path, Path]:
    return data_dir / row["reflectance_path"], data_dir / row["scl_path"]


def _read_reflectance(path: Path) -> Raster:
    """Read predictor-3 float TIFF pixels with tifffile, georeference locally."""
    data = tifffile.imread(path)
    if data.ndim == 3 and data.shape[0] != 6:
        data = np.moveaxis(data, -1, 0)
    # Georeference tags are independent of compressed pixel decoding. Read them
    # through tifffile as well, avoiding a second unsupported pixel decode.
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        scale = page.tags[33550].value
        tie = page.tags[33922].value
    return Raster(
        data=data,
        lon_origin=float(tie[3]),
        lat_origin=float(tie[4]),
        lon_step=float(scale[0]),
        lat_step=float(scale[1]),
        nodata=None,
        metadata="",
    )


def _quality(data_dir: Path, row: dict, bbox, epsg: int) -> tuple[float, np.ndarray, np.ndarray]:
    reflectance_path, scl_path = _paths(data_dir, row)
    reflectance = _read_reflectance(reflectance_path)
    scl = read_geotiff(str(scl_path)).band(0)
    inside = _polygon_mask(reflectance, bbox, epsg)
    valid = inside & np.isin(scl, list(VALID_SCL))
    fraction = float(valid.sum() / inside.sum()) if inside.any() else 0.0
    return fraction, inside, valid


def _render_scene(data_dir: Path, row: dict, bbox, epsg: int, output: Path) -> dict:
    reflectance_path, scl_path = _paths(data_dir, row)
    raster = _read_reflectance(reflectance_path)
    scl = read_geotiff(str(scl_path)).band(0)
    inside = _polygon_mask(raster, bbox, epsg)
    valid = inside & np.isin(scl, list(VALID_SCL))

    # B04/B03/B02. Stretch each scene only for display; quantitative comparison
    # below uses the original reflectance values.
    rgb = np.moveaxis(raster.data[[2, 1, 0]].astype(float), 0, -1)
    for channel in range(3):
        values = rgb[:, :, channel][valid & np.isfinite(rgb[:, :, channel])]
        low, high = np.percentile(values, [2, 98]) if values.size else (0.0, 1.0)
        rgb[:, :, channel] = np.clip((rgb[:, :, channel] - low) / max(high - low, 1e-6), 0, 1)
    rgb = np.power(rgb, 1 / 1.15)
    rgb = (rgb * 255).astype(np.uint8)
    rgb[inside & ~valid] = [214, 216, 211]
    rgba = np.dstack([rgb, inside.astype(np.uint8) * 255])

    image = Image.fromarray(rgba, "RGBA").resize(
        (raster.data.shape[2] * 3, raster.data.shape[1] * 3), Image.Resampling.NEAREST
    )
    draw = ImageDraw.Draw(image)
    draw.rectangle((1, 1, image.width - 2, image.height - 2), outline=(255, 255, 255, 230), width=3)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    fraction = float(valid.sum() / inside.sum()) if inside.any() else 0.0
    return {
        "date": row["datetime_utc"][:10],
        "scene_id": row["item_id"],
        "image": output.name,
        "valid_fraction": fraction,
        "usable": fraction >= MIN_USABLE_FRACTION,
        "scl_valid_classes": sorted(VALID_SCL),
    }


def _spectral_metrics(data_dir: Path, before: dict, after: dict, bbox, epsg: int) -> dict:
    before_r = _read_reflectance(_paths(data_dir, before)[0])
    after_r = _read_reflectance(_paths(data_dir, after)[0])
    _, _, before_valid = _quality(data_dir, before, bbox, epsg)
    _, _, after_valid = _quality(data_dir, after, bbox, epsg)
    common = before_valid & after_valid
    if not common.any():
        return {"comparable_fraction": 0.0, "delta_ndvi": None, "delta_nbr": None}

    def index(raster, left: int, right: int) -> np.ndarray:
        a = raster.band(left).astype(float)
        b = raster.band(right).astype(float)
        return np.divide(a - b, a + b, out=np.full_like(a, np.nan), where=np.abs(a + b) > 1e-8)

    # Band order: B02, B03, B04, B8A, B11, B12.
    before_ndvi, after_ndvi = index(before_r, 3, 2), index(after_r, 3, 2)
    before_nbr, after_nbr = index(before_r, 3, 5), index(after_r, 3, 5)
    inside = _polygon_mask(before_r, bbox, epsg)
    return {
        "comparable_fraction": float(common.sum() / inside.sum()),
        "delta_ndvi": float(np.nanmean(after_ndvi[common] - before_ndvi[common])),
        "delta_nbr": float(np.nanmean(after_nbr[common] - before_nbr[common])),
        "note": "Изменение индексов посчитано только по пикселям, пригодным на обе даты.",
    }


def build_event_evidence(data_dir: Path, event: dict, bbox, output_dir: Path) -> dict:
    """Build an auditable before/immediate-after/recovery evidence bundle."""
    aoi = event["aoi_id"]
    epsg = 32638  # Both supplied fire AOIs are in UTM zone 38N.
    start = date.fromisoformat(event["date_min_product"])
    end = date.fromisoformat(event["date_max_product"])
    rows = _scene_rows(data_dir, aoi)
    before = [r for r in rows if date.fromisoformat(r["datetime_utc"][:10]) < start]
    immediate = [r for r in rows if date.fromisoformat(r["datetime_utc"][:10]) > end and int(r["year"]) == start.year]
    recovery = [r for r in rows if int(r["year"]) == start.year + 1]

    def best(candidates: list[dict]) -> dict | None:
        if not candidates:
            return None
        return max(candidates, key=lambda r: _quality(data_dir, r, bbox, epsg)[0])

    # Prefer the latest pre-event season. A marginal quality difference must not
    # silently move the comparison back by one or two years.
    if before:
        latest_year = max(int(r["year"]) for r in before)
        before = [r for r in before if int(r["year"]) == latest_year]
    selected = [("before", best(before)), ("immediate_after", best(immediate)), ("recovery", best(recovery))]
    observations = []
    by_role = {}
    for role, row in selected:
        if row is None:
            continue
        rendered = _render_scene(
            data_dir, row, bbox, epsg, output_dir / f"{event['event_id']}_{role}.png"
        )
        rendered["role"] = role
        observations.append(rendered)
        by_role[role] = row

    comparison = None
    if "before" in by_role and "recovery" in by_role:
        comparison = _spectral_metrics(data_dir, by_role["before"], by_role["recovery"], bbox, epsg)
        comparison.update({"before_role": "before", "after_role": "recovery"})

    return {
        "observations": observations,
        "comparison": comparison,
        "quality_rule": "SCL классы 4, 5, 6 и 7; пригодность не ниже 50%",
        "display_note": "RGB-контраст нормирован отдельно для каждой даты; индексы считаются по исходному отражению.",
        "interpretation": (
            "Снимок сразу после события показывается даже при низком качестве, но не используется "
            "как самостоятельное подтверждение. Для сопоставления индексов выбрана пригодная сцена 2022 года."
        ),
    }
