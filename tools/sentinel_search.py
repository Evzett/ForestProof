"""Поиск снимков Sentinel-2 по произвольному контуру — KAN-59.

Зачем. `sentinel_evidence.py` умеет собирать доказательную базу, но
только из снимков, вложенных в набор кейса. У участков, добавленных
нами, вкладка с доказательствами пуста — не потому, что снимков нет, а
потому, что их некому найти.

Что делает. Спрашивает каталог STAC Element 84 (без авторизации),
скачивает маску SCL кандидатов и выбирает сцену по доле годных
пикселей **внутри контура**, а не по облачности всего тайла.

Почему именно так. Облачность в метаданных считается по сцене целиком,
120 на 120 километров. Участок занимает в ней тысячную долю, и сцена с
облачностью 40 % может быть над ним совершенно чистой — и наоборот.
Выбирать по метаданным значит выбирать наугад.

Что берётся из метаданных как есть:

    s2:processing_baseline — от него зависит сдвиг кодирования;
                             с версии 04.00 ESA сместила его на −1000 DN,
                             и без поправки NDVI выходит больше единицы;
    proj:epsg              — зона UTM сцены. Считать её по долготе можно,
                             но если каталог её уже сообщил, вычислять
                             заново незачем: разойтись с источником
                             в таком месте слишком дорого.

Запуск:
    python tools/sentinel_search.py --areas data/areas.csv
    python tools/sentinel_search.py --aoi RU_TVER_05 --year 2019
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geotiff import read_geotiff  # noqa: E402

STAC_URL = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
CACHE = Path("data/cache/sentinel")

# Классы SCL, которые считаются годными: растительность, голая почва,
# вода и тонкое облако. Те же, что в sentinel_evidence.py — иначе доля
# годных здесь и там означала бы разное.
VALID_SCL = {4, 5, 6, 7}

# Ниже этой доли сцена не доказательство, а картинка: по трети кадра
# нельзя судить, что стало с участком.
MIN_USABLE = 0.50

TIMEOUT = 15


def search(
    bbox: tuple[float, float, float, float],
    start: str,
    end: str,
    *,
    max_cloud: float = 60.0,
    limit: int = 20,
) -> list[dict]:
    """Кандидаты из каталога. Фильтр по облачности здесь грубый: он
    отсекает заведомо безнадёжное, а выбор делается позже по маске."""
    body = {
        "collections": [COLLECTION],
        "bbox": list(bbox),
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
        "limit": limit,
    }
    request = urllib.request.Request(
        STAC_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        payload = json.loads(response.read())

    out = []
    for feature in payload.get("features", []):
        properties = feature["properties"]
        assets = feature["assets"]
        if "scl" not in assets:
            continue
        out.append(
            {
                "item_id": feature["id"],
                "datetime_utc": properties["datetime"],
                "cloud_percent": properties.get("eo:cloud_cover"),
                "processing_baseline": properties.get("s2:processing_baseline"),
                "epsg": properties.get("proj:epsg"),
                "scl_href": assets["scl"]["href"],
                "assets": {
                    band: assets[band]["href"]
                    for band in ("red", "green", "blue", "nir", "swir16")
                    if band in assets
                },
            }
        )
    return out


def _download(url: str, target: Path, *, attempts: int = 2) -> Path:
    """Скачивание с провенансом рядом. Повторно не качает.

    Попыток несколько: облако изредка рвёт TLS на середине
    (DECRYPTION_FAILED_OR_BAD_RECORD_MAC), и терять из-за этого сцену
    незачем — при следующей попытке она скачивается без вопросов.
    """
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "ForestProof/1.0"})

    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response, open(part, "wb") as handle:
                while chunk := response.read(1 << 20):
                    handle.write(chunk)
            break
        except (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError):
            part.unlink(missing_ok=True)
            if attempt == attempts:
                raise
            time.sleep(attempt)

    part.replace(target)
    target.with_suffix(target.suffix + ".json").write_text(
        json.dumps({"url": url, "bytes": target.stat().st_size}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def _utm_forward(lon: float, lat: float, zone: int) -> tuple[float, float]:
    """WGS84 в UTM. Хватает для участков нашего размера."""
    a = 6378137.0
    ecc_sq = 0.00669437999014
    k0 = 0.9996
    lat_r, lon_r = math.radians(lat), math.radians(lon)
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    ecc_prime_sq = ecc_sq / (1 - ecc_sq)
    n = a / math.sqrt(1 - ecc_sq * math.sin(lat_r) ** 2)
    t = math.tan(lat_r) ** 2
    c = ecc_prime_sq * math.cos(lat_r) ** 2
    A = math.cos(lat_r) * (lon_r - lon0)
    m = a * (
        (1 - ecc_sq / 4 - 3 * ecc_sq**2 / 64 - 5 * ecc_sq**3 / 256) * lat_r
        - (3 * ecc_sq / 8 + 3 * ecc_sq**2 / 32 + 45 * ecc_sq**3 / 1024) * math.sin(2 * lat_r)
        + (15 * ecc_sq**2 / 256 + 45 * ecc_sq**3 / 1024) * math.sin(4 * lat_r)
        - (35 * ecc_sq**3 / 3072) * math.sin(6 * lat_r)
    )
    easting = k0 * n * (
        A + (1 - t + c) * A**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * ecc_prime_sq) * A**5 / 120
    ) + 500000.0
    northing = k0 * (
        m
        + n
        * math.tan(lat_r)
        * (
            A**2 / 2
            + (5 - t + 9 * c + 4 * c**2) * A**4 / 24
            + (61 - 58 * t + t**2 + 600 * c - 330 * ecc_prime_sq) * A**6 / 720
        )
    )
    return easting, northing


def usable_fraction(scl_path: Path, bbox: tuple[float, float, float, float], epsg: int) -> float:
    """Доля годных пикселей SCL внутри контура.

    Сцена лежит в метрах UTM, контур задан в градусах, поэтому контур
    переводится в метры зоны самой сцены. Зона берётся из EPSG каталога,
    а не вписывается: неверная зона даёт окно, уехавшее на сотни
    километров, и делает это молча.
    """
    raster = read_geotiff(str(scl_path))
    zone = int(epsg) % 100
    xs, ys = [], []
    for lon in (bbox[0], bbox[2]):
        for lat in (bbox[1], bbox[3]):
            x, y = _utm_forward(lon, lat, zone)
            xs.append(x)
            ys.append(y)

    left, right = min(xs), max(xs)
    bottom, top = min(ys), max(ys)

    cols = raster.data.shape[2]
    rows = raster.data.shape[1]
    c0 = int((left - raster.lon_origin) / raster.lon_step)
    c1 = int(math.ceil((right - raster.lon_origin) / raster.lon_step))
    r0 = int((raster.lat_origin - top) / raster.lat_step)
    r1 = int(math.ceil((raster.lat_origin - bottom) / raster.lat_step))

    c0, c1 = max(0, c0), min(cols, c1)
    r0, r1 = max(0, r0), min(rows, r1)
    if c1 <= c0 or r1 <= r0:
        return 0.0

    window = raster.band(0)[r0:r1, c0:c1].astype(int)
    if window.size == 0:
        return 0.0
    return float(np.isin(window, list(VALID_SCL)).mean())


def rank(
    candidates: list[dict], bbox: tuple[float, float, float, float], cache: Path
) -> list[dict]:
    """Кандидаты, отсортированные по доле годных пикселей внутри контура."""
    scored = []
    for candidate in candidates:
        target = cache / f"{candidate['item_id']}_SCL.tif"
        try:
            _download(candidate["scl_href"], target)
            fraction = usable_fraction(target, bbox, candidate["epsg"])
        except (urllib.error.URLError, OSError, ValueError, IndexError) as error:
            candidate["usable_fraction"] = None
            candidate["skip_reason"] = f"{type(error).__name__}: {error}"
            continue
        candidate["usable_fraction"] = fraction
        candidate["usable"] = fraction >= MIN_USABLE
        scored.append(candidate)

    return sorted(scored, key=lambda c: c["usable_fraction"], reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--areas", type=Path, default=Path("data/areas.csv"))
    parser.add_argument("--aoi", help="только один участок")
    parser.add_argument("--year", type=int, default=2024, help="год наблюдения")
    parser.add_argument("--season", default="06-01:09-15", help="окно сезона ММ-ДД:ММ-ДД")
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--out", type=Path, default=Path("data/scenes.derived.csv"))
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    season_start, season_end = args.season.split(":")
    start = f"{args.year}-{season_start}"
    end = f"{args.year}-{season_end}"

    with open(args.areas, encoding="utf-8-sig") as handle:
        areas = list(csv.DictReader(handle))
    if args.aoi:
        areas = [a for a in areas if a["aoi_id"] == args.aoi]

    rows: list[dict] = []
    for meta in areas:
        aoi = meta["aoi_id"]
        bbox = (
            float(meta["bbox_west"]),
            float(meta["bbox_south"]),
            float(meta["bbox_east"]),
            float(meta["bbox_north"]),
        )
        try:
            candidates = search(bbox, start, end, limit=args.limit)
        except (urllib.error.URLError, TimeoutError) as error:
            print(f"{aoi:<18} каталог недоступен: {error}")
            continue

        if not candidates:
            print(f"{aoi:<18} сцен за {start}—{end} не нашлось")
            continue

        ranked = rank(candidates, bbox, args.cache)
        if not ranked:
            print(f"{aoi:<18} ни одну маску SCL прочитать не удалось")
            continue

        best = ranked[0]
        mark = "годная" if best["usable"] else f"НЕГОДНАЯ, ниже порога {MIN_USABLE:.0%}"
        print(
            f"{aoi:<18} {best['item_id']:<28} {best['datetime_utc'][:10]}  "
            f"годных внутри контура {best['usable_fraction']:.1%}  "
            f"(облачность сцены {best['cloud_percent']:.0f} %)  · {mark}"
        )

        rows.append(
            {
                "scene_key": f"{aoi}__{best['item_id']}",
                "aoi_id": aoi,
                "item_id": best["item_id"],
                "datetime_utc": best["datetime_utc"],
                "year": args.year,
                "collection": COLLECTION,
                "processing_baseline": best["processing_baseline"],
                "source_scene_cloud_percent": best["cloud_percent"],
                "scl_4_5_6_7_fraction_crop": round(best["usable_fraction"], 6),
                "selection_role": "найдено поиском по контуру",
                "reflectance_path": "",
                "scl_path": str(args.cache / f"{best['item_id']}_SCL.tif"),
                "metadata_file": "STAC Element 84 Earth Search",
                "candidates_checked": len(ranked),
            }
        )

    if not rows:
        raise SystemExit("\nничего не найдено — файл не записан")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    usable = sum(1 for r in rows if r["scl_4_5_6_7_fraction_crop"] >= MIN_USABLE)
    print(f"\nзаписано {args.out}: {len(rows)} сцен, годных {usable}")


if __name__ == "__main__":
    main()
