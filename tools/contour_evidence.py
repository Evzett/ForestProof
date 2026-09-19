"""Доказательная база для произвольного контура — из открытых источников.

Зачем отдельный модуль. Части уже были написаны, но каждая под свою
задачу: `scene_previews` собирает снимки по списку участков из CSV,
`modis_burned_area` пишет события в CSV по тому же списку. Оба — сценарии
подготовки набора, запускаемые руками.

Сервису нужно другое: один контур, пришедший в запросе, прямо сейчас.
Здесь эти части собраны под такой вызов — без CSV, без списков и без
записи в набор. Формулы и разбор продуктов не дублируются: берутся те же
функции, что готовят набор, поэтому загруженный контур и участок кейса
считаются одним кодом.

Что собирается:

* **пара снимков Sentinel-2** на начало и конец периода — окно по контуру
  читается прямо из облака, каталог STAC авторизации не требует;
* **события гарей MODIS** — гранулы ищутся в CMR, скачиваются по токену
  Earthdata и разбираются тем же кодом, что и для участков кейса.

Правило то же, что и везде: недоступный источник — это «не удалось
подтвердить», а не «событий нет». Причина возвращается наружу и
показывается, а не прячется в лог.
"""

from __future__ import annotations

import sys
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import modis_burned_area as modis  # noqa: E402
from tools.scene_previews import render as render_scene  # noqa: E402
from tools.sentinel_search import rank, search  # noqa: E402

# Сезон съёмки. Зимний снимок показывает снег, а не лес, и сравнивать по
# нему «до и после» бессмысленно.
SEASON_START = "06-01"
SEASON_END = "09-15"

# Месяцы поиска гарей: вне сезона гореть нечему, а гранулы месячные и
# каждая — десятки мегабайт.
FIRE_MONTHS = (4, 10)

SENTINEL_CACHE = Path("data/cache/sentinel")
MODIS_CACHE = Path("data/cache/modis")


@dataclass(slots=True)
class Evidence:
    """Что удалось подтвердить по контуру и чем именно."""

    scenes: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"scenes": self.scenes, "events": self.events, "notes": self.notes}


def scene_pair(
    bbox: tuple[float, float, float, float],
    years: tuple[int, int],
    out_dir: Path,
    prefix: str,
    *,
    limit: int = 4,
) -> tuple[list[dict], list[str]]:
    """Снимок на начало периода и на конец.

    Сцена выбирается по доле годных пикселей ВНУТРИ контура, а не по
    облачности всей сцены: тайл в сто километров может быть закрыт
    наполовину, а наш участок — чистым, и наоборот.
    """
    shots: list[dict] = []
    notes: list[str] = []

    for year, role in zip(years, ("before", "after")):
        start, end = f"{year}-{SEASON_START}", f"{year}-{SEASON_END}"
        try:
            candidates = search(bbox, start, end, limit=limit)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            notes.append(f"{year}: каталог снимков недоступен ({type(error).__name__})")
            continue

        if not candidates:
            notes.append(f"{year}: сцен за сезон съёмки не нашлось")
            continue

        ranked = rank(candidates, bbox, SENTINEL_CACHE)
        if not ranked:
            notes.append(f"{year}: ни одну маску облачности прочитать не удалось")
            continue

        target = out_dir / f"{prefix}_scene_{role}.png"
        try:
            info = render_scene(ranked[0], bbox, target)
        except (urllib.error.URLError, OSError, ValueError, IndexError) as error:
            notes.append(f"{year}: снимок не собрался ({type(error).__name__})")
            continue

        if info is None:
            notes.append(f"{year}: у сцены нет нужных каналов")
            continue

        shots.append({**info, "role": role, "year": year})

    return shots, notes


def burned_events(
    bbox: tuple[float, float, float, float],
    years: tuple[int, int],
    *,
    min_burned: int = 1,
) -> tuple[list[dict], list[str]]:
    """События гарей по продукту MODIS за период.

    Требует токена Earthdata. Без него возвращается не пустой список, а
    оговорка: «подтверждения не искали» и «подтверждений нет» — разные
    утверждения, и путать их нельзя.
    """
    auth = modis.credentials()
    if auth is None:
        return [], [
            "гари не проверялись: нет доступа к Earthdata "
            "(EARTHDATA_TOKEN в окружении или .env)"
        ]

    events: list[dict] = []
    notes: list[str] = []
    first_month, last_month = FIRE_MONTHS

    for year in range(years[0], years[1] + 1):
        start = f"{year}-{first_month:02d}-01"
        end = f"{year}-{last_month:02d}-28"
        try:
            granules = modis.find_granules(bbox, start, end)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            notes.append(f"{year}: каталог гарей недоступен ({type(error).__name__})")
            continue

        for granule in granules:
            try:
                path = modis.download(granule, MODIS_CACHE, auth)
                result = modis.burned_in_bbox(path, granule["title"], bbox)
            except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
                notes.append(f"{granule['title']}: не разобрана ({type(error).__name__})")
                continue
            except ImportError:
                notes.append(
                    "гари не проверялись: не установлен pyhdf "
                    "(pip install -r requirements.txt)"
                )
                return events, notes

            if result["burned_pixels"] < min_burned:
                continue

            days = result["days"]
            events.append(
                {
                    "year": year,
                    "granule": granule["title"],
                    "burned_pixels": result["burned_pixels"],
                    "all_pixels": result["all_pixels"],
                    "date_min": modis._day_to_date(year, min(days)) if days else None,
                    "date_max": modis._day_to_date(year, max(days)) if days else None,
                    "evidence_type": "признак горения по продукту MODIS",
                    "cause_supported": "признак горения по продукту MODIS MCD64A1",
                    "source_id": "MODIS_MCD64A1_061",
                    "limitations": (
                        "Продукт отмечает факт горения, а не его причину и не объём "
                        "потерь. Дата известна с точностью продукта."
                    ),
                }
            )

    if not events and not notes:
        notes.append("гари искали, за период не нашлось")
    return events, notes


def collect(
    bbox: tuple[float, float, float, float],
    years: tuple[int, int],
    out_dir: Path,
    prefix: str,
    *,
    with_fire: bool = True,
) -> Evidence:
    """Всё, что можно подтвердить по контуру внешними источниками."""
    evidence = Evidence()

    shots, notes = scene_pair(bbox, years, out_dir, prefix)
    evidence.scenes.extend(shots)
    evidence.notes.extend(notes)

    if with_fire:
        events, fire_notes = burned_events(bbox, years)
        evidence.events.extend(events)
        evidence.notes.extend(fire_notes)

    return evidence
