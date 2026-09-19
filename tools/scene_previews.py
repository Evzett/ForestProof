"""Спутниковые превью для участков, которых нет в наборе кейса.

Зачем. Снимки Sentinel-2 вложены в набор только для четырёх участков
кейса. У восьми добавленных их нет, и на карточках вместо снимка
оставалась карта изменений — пиксельная сетка, по которой непонятно,
что это за место.

Как. Сцена уже выбрана инструментом KAN-59 — по доле годных пикселей
внутри контура, а не по облачности всего тайла. Здесь у неё читаются
каналы B04, B03, B02 прямо из облака, окном по контуру: канал весит
около 150 МБ, окно участка — доли процента.

Растяжка контраста. Каналы растягиваются по 2-му и 98-му процентилю
и проходят гамму — иначе снимок выходит тёмным и синеватым, каким его
никто не публикует. Это делается ТОЛЬКО для показа: ни одно число
расчёта из этих картинок не берётся, они не участвуют ни в оценке
запаса, ни в определении потерь.

Запуск:
    python tools/scene_previews.py
    python tools/scene_previews.py --aoi RU_TVER_05 --year 2024
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.error
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geotiff import read_geotiff  # noqa: E402
from sentinel_evidence import _utm_forward, utm_zone  # noqa: E402
from sentinel_search import rank, search  # noqa: E402

# Ширина превью. Окно участка — около 400 пикселей по стороне, и
# растягивать его сильнее незачем: это добавит размер файла, но не
# добавит ни одной детали, которой нет в данных.
WIDTH = 640

OUT_DIR = Path("app/public/maps")
INDEX = Path("data/scene_previews.json")


def window_utm(bbox, zone: int) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for lon in (bbox[0], bbox[2]):
        for lat in (bbox[1], bbox[3]):
            x, y = _utm_forward(lon, lat, zone)
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def stretch(bands: list[np.ndarray]) -> np.ndarray:
    """Три канала к диапазону 0…1 ОДНИМ общим преобразованием.

    Ключевая деталь. Если растягивать каждый канал по своим
    процентилям, соотношение между ними меняется — и лес получается
    фиолетовым: в нём синего меньше всех, и растянутый до того же
    предела он вылезает вперёд. Именно так выглядят снимки, вложенные
    в набор.

    Общий множитель на все три канала меняет только яркость, не трогая
    цвет: зелёное остаётся зелёным. Это по-прежнему обработка для
    показа, но она не переписывает то, что снял прибор.

    Нули — край окна и отсутствие данных, в процентили они не идут:
    иначе снимок уползает в тень.
    """
    stack = np.dstack([b.astype(float) for b in bands])
    values = stack[stack > 0]
    if values.size == 0:
        return np.zeros_like(stack)
    low, high = np.percentile(values, [2, 98])
    return np.clip((stack - low) / max(high - low, 1e-6), 0, 1)


def render(scene: dict, bbox, target: Path) -> dict | None:
    zone = int(scene["epsg"]) % 100
    window = window_utm(bbox, zone)

    bands = []
    for name in ("red", "green", "blue"):
        href = scene["assets"].get(name)
        if not href:
            return None
        raster = read_geotiff(href, bbox=window)
        bands.append(raster.band(0))

    shape = min((b.shape for b in bands), key=lambda s: (s[0], s[1]))
    rgb = stretch([b[: shape[0], : shape[1]] for b in bands])
    # Гамма: отражение леса лежит в тёмной части диапазона, и без неё
    # снимок выходит почти чёрным.
    rgb = np.power(rgb, 1 / 1.7)

    image = Image.fromarray((rgb * 255).astype(np.uint8), "RGB")
    if image.width > WIDTH:
        height = round(image.height * WIDTH / image.width)
        image = image.resize((WIDTH, height), Image.Resampling.LANCZOS)

    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, optimize=True)
    return {
        "image": target.name,
        "date": scene["datetime_utc"][:10],
        "scene_id": scene["item_id"],
        "usable_fraction": round(scene.get("usable_fraction", 0.0), 4),
        "cloud_percent": scene.get("cloud_percent"),
        "source": "Sentinel-2 L2A, окно прочитано из облака по контуру",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--areas", type=Path, default=Path("data/areas.csv"))
    parser.add_argument("--aoi", action="append")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--season", default="06-01:09-15")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--index", type=Path, default=INDEX)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--force", action="store_true", help="перерисовать уже готовые")
    args = parser.parse_args()

    season_start, season_end = args.season.split(":")
    start, end = f"{args.year}-{season_start}", f"{args.year}-{season_end}"

    with open(args.areas, encoding="utf-8-sig") as handle:
        areas = list(csv.DictReader(handle))
    if args.aoi:
        areas = [a for a in areas if a["aoi_id"] in args.aoi]

    index: dict[str, dict] = {}
    if args.index.exists():
        index = json.loads(args.index.read_text(encoding="utf-8"))

    cache = Path("data/cache/sentinel")

    for meta in areas:
        aoi = meta["aoi_id"]
        target = args.out / f"{aoi}_scene.png"

        # Участки кейса уже имеют вложенные снимки — своё поверх набора
        # не кладём: там снимок пришёл с данными, и подменять его нашим
        # значило бы выдать одно за другое.
        if (Path("data") / aoi / "Sentinel2").exists():
            print(f"{aoi:<18} снимки есть в наборе — пропуск")
            continue
        if target.exists() and not args.force:
            print(f"{aoi:<18} превью уже есть — пропуск")
            continue

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

        ranked = rank(candidates, bbox, cache)
        if not ranked:
            print(f"{aoi:<18} ни одну маску SCL прочитать не удалось")
            continue

        best = ranked[0]
        try:
            info = render(best, bbox, target)
        except (urllib.error.URLError, OSError, ValueError, IndexError) as error:
            print(f"{aoi:<18} снимок не собрался: {type(error).__name__}: {error}")
            continue
        if info is None:
            print(f"{aoi:<18} у сцены нет каналов RGB")
            continue

        index[aoi] = info
        print(
            f"{aoi:<18} {info['scene_id']:<28} {info['date']}  "
            f"годных внутри контура {info['usable_fraction']:.0%}"
        )

    args.index.parent.mkdir(parents=True, exist_ok=True)
    args.index.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nзаписано {args.index}: превью на {len(index)} участках")


if __name__ == "__main__":
    main()
