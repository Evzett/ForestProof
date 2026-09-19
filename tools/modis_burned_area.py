"""Продукт гарей MODIS по произвольному контуру — KAN-60.

Зачем. Причина изменения покрова у нас подтверждается ровно там, где
подтверждение пришло вместе с набором: два события на двух участках.
Для всех остальных статус — «не установлена». Не потому, что гарей не
было, а потому, что спросить было некому.

Что делает. Ищет гранулы MCD64A1 через CMR (без авторизации), скачивает
нужные с учётной записью Earthdata, читает слой `Burn Date` и считает,
сколько центров пикселей продукта внутри контура помечены как горевшие.

Почему центры пикселей, а не площадь. Пиксель MODIS — 500 метров, и
участок в 1800 га накрывается примерно сотней таких. Делить пиксель по
границе контура здесь нечем: продукт бинарный, «горело или нет», и доля
пикселя не означает доли гари. Набор кейса считает так же — по центрам,
— и сверка это подтверждает.

Проверка на известном ответе. У двух участков кейса подтверждение уже
есть: Мордовия-03 — 60 горевших центров из 88, Мордовия-04 — 88 из 88,
гранула MCD64A1.A2021213. Скрипт умеет это перепроверить (`--verify`).
Если не сходится — значит сетка читается неверно, и остальным ответам
верить нельзя.

Запуск:
    python tools/modis_burned_area.py --verify
    python tools/modis_burned_area.py --areas data/areas.csv --years 2019 2024
"""

from __future__ import annotations

import argparse
import csv
import http.cookiejar
import json
import os
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import numpy as np

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
SHORT_NAME = "MCD64A1"
VERSION = "061"
CACHE = Path("data/cache/modis")
ENV_FILE = Path(".env")

# Синусоидальная сетка MODIS.
EARTH_RADIUS = 6371007.181
TILE_METERS = 1111950.5196666666
TILE_PIXELS = 2400
PIXEL_METERS = TILE_METERS / TILE_PIXELS
X_MIN = -20015109.354
Y_MAX = 10007554.677

TIMEOUT = 15


def _env() -> dict[str, str]:
    """Переменные окружения плюс .env. Окружение имеет приоритет: на
    сервере секрета в файле нет и быть не должно."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    for key in ("EARTHDATA_TOKEN", "EARTHDATA_USERNAME", "EARTHDATA_PASSWORD"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def credentials() -> tuple[str, str] | str | None:
    """Доступ к Earthdata: токен, иначе пара логин-пароль, иначе ничего.

    Токен предпочтительнее: он не тянет за собой редирект на сервер
    входа и отзывается отдельно от самой учётной записи. Отсутствие
    любого доступа — не ошибка сразу: поиск гранул через CMR работает
    и без него, недоступна только выкачка файла.
    """
    env = _env()
    token = env.get("EARTHDATA_TOKEN")
    if token:
        return token
    user, password = env.get("EARTHDATA_USERNAME"), env.get("EARTHDATA_PASSWORD")
    return (user, password) if user and password else None


class _KeepAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """Earthdata уводит на сервер входа и обратно на сервер данных.

    Стандартный обработчик снимает заголовок авторизации при переходе на
    другой хост — разумная защита, но здесь она и ломает вход, потому
    что оба хоста принадлежат одной системе.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            auth = req.get_header("Authorization")
            if auth:
                new.add_unredirected_header("Authorization", auth)
        return new


def _opener(user: str, password: str):
    manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    manager.add_password(None, "https://urs.earthdata.nasa.gov", user, password)
    return urllib.request.build_opener(
        urllib.request.HTTPBasicAuthHandler(manager),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        _KeepAuthOnRedirect(),
    )


def find_granules(bbox: tuple[float, float, float, float], start: str, end: str) -> list[dict]:
    """Гранулы, накрывающие контур за период. Авторизации не требует."""
    query = {
        "short_name": SHORT_NAME,
        "version": VERSION,
        "bounding_box": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z",
        "page_size": 200,
    }
    with urllib.request.urlopen(f"{CMR}?{urllib.parse.urlencode(query)}", timeout=TIMEOUT) as r:
        entries = json.loads(r.read())["feed"]["entry"]

    out = []
    for entry in entries:
        hdf = [l["href"] for l in entry.get("links", []) if l["href"].endswith(".hdf")]
        if hdf:
            out.append(
                {
                    "title": entry["title"],
                    "url": hdf[0],
                    "time_start": entry.get("time_start", ""),
                    "time_end": entry.get("time_end", ""),
                }
            )
    return out


def download(granule: dict, cache: Path, auth: tuple[str, str] | str) -> Path:
    target = cache / f"{granule['title']}.hdf"
    if target.exists():
        return target
    cache.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(".part")

    headers = {"User-Agent": "ForestProof/1.0"}
    if isinstance(auth, str):
        headers["Authorization"] = f"Bearer {auth}"
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            _KeepAuthOnRedirect(),
        )
    else:
        opener = _opener(*auth)

    request = urllib.request.Request(granule["url"], headers=headers)
    with opener.open(request, timeout=TIMEOUT) as response, open(part, "wb") as handle:
        while chunk := response.read(1 << 20):
            handle.write(chunk)
    part.replace(target)
    return target


def _sinusoidal(lon: float, lat: float) -> tuple[float, float]:
    lat_r = math.radians(lat)
    return EARTH_RADIUS * math.radians(lon) * math.cos(lat_r), EARTH_RADIUS * lat_r


def _tile_of(title: str) -> tuple[int, int]:
    """Номера тайла h и v из имени гранулы: MCD64A1.A2021213.h20v03..."""
    part = next(p for p in title.split(".") if p.startswith("h") and "v" in p)
    return int(part[1:3]), int(part[4:6])


def pixel_centers_in_bbox(
    title: str, bbox: tuple[float, float, float, float]
) -> tuple[np.ndarray, np.ndarray]:
    """Индексы пикселей тайла, чьи ЦЕНТРЫ попадают внутрь рамки."""
    h, v = _tile_of(title)
    x0 = X_MIN + h * TILE_METERS
    y0 = Y_MAX - v * TILE_METERS

    # Центры всех пикселей тайла в метрах синусоидальной проекции.
    cols = np.arange(TILE_PIXELS)
    rows = np.arange(TILE_PIXELS)
    xs = x0 + (cols + 0.5) * PIXEL_METERS
    ys = y0 - (rows + 0.5) * PIXEL_METERS

    # Обратный перевод в градусы: широта из y напрямую, долгота из x с
    # поправкой на косинус широты — в синусоидальной проекции масштаб по
    # долготе зависит от широты, и без поправки окно уезжает тем сильнее,
    # чем дальше от экватора.
    lat = np.degrees(ys / EARTH_RADIUS)
    lat_r = np.radians(lat)
    lon = np.degrees(xs[None, :] / (EARTH_RADIUS * np.cos(lat_r)[:, None]))

    inside_lat = (lat >= bbox[1]) & (lat <= bbox[3])
    inside = (lon >= bbox[0]) & (lon <= bbox[2]) & inside_lat[:, None]
    return np.nonzero(inside)


def burned_in_bbox(path: Path, title: str, bbox: tuple[float, float, float, float]) -> dict:
    """Сколько центров пикселей внутри контура помечены как горевшие."""
    from pyhdf.SD import SD, SDC

    handle = SD(str(path), SDC.READ)
    try:
        burn_date = handle.select("Burn Date").get()
    finally:
        handle.end()

    rows, cols = pixel_centers_in_bbox(title, bbox)
    if rows.size == 0:
        return {"all_pixels": 0, "burned_pixels": 0, "days": []}

    values = burn_date[rows, cols]
    burned = values > 0
    return {
        "all_pixels": int(rows.size),
        "burned_pixels": int(burned.sum()),
        "days": sorted({int(d) for d in values[burned]}),
    }


def _day_to_date(year: int, day: int) -> str:
    return (date(year, 1, 1) + timedelta(days=day - 1)).isoformat()


def verify(cache: Path, auth: tuple[str, str] | str) -> bool:
    """Сверка с подтверждениями, пришедшими вместе с набором."""
    expected = [
        ("RU_MORDOVIA_03", 60, 88),
        ("RU_MORDOVIA_04", 88, 88),
    ]
    areas = {
        a["aoi_id"]: a
        for a in csv.DictReader(open("data/areas.csv", encoding="utf-8-sig"))
    }

    print("сверка с событиями набора (гранула августа 2021)")
    ok = True
    for aoi, want_burned, want_all in expected:
        meta = areas[aoi]
        bbox = (
            float(meta["bbox_west"]),
            float(meta["bbox_south"]),
            float(meta["bbox_east"]),
            float(meta["bbox_north"]),
        )
        granules = find_granules(bbox, "2021-08-01", "2021-08-31")
        if not granules:
            print(f"  {aoi}: гранул за август 2021 не нашлось")
            ok = False
            continue
        granule = granules[0]
        path = download(granule, cache, auth)
        result = burned_in_bbox(path, granule["title"], bbox)
        match = result["burned_pixels"] == want_burned and result["all_pixels"] == want_all
        ok = ok and match
        print(
            f"  {aoi:<16} наш {result['burned_pixels']}/{result['all_pixels']}, "
            f"в наборе {want_burned}/{want_all} — {'совпало' if match else 'РАСХОЖДЕНИЕ'}"
        )

    if not ok:
        print(
            "\nСетка читается не так, как её читал набор. Дальше идти нельзя:\n"
            "подтверждения по другим участкам были бы недостоверны."
        )
    else:
        print("  сверка пройдена\n")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--areas", type=Path, default=Path("data/areas.csv"))
    parser.add_argument("--years", type=int, nargs=2, default=[2019, 2024])
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--out", type=Path, default=Path("data/events.derived.csv"))
    parser.add_argument("--verify", action="store_true", help="только сверка с набором")
    parser.add_argument("--min-burned", type=int, default=1)
    parser.add_argument(
        "--months",
        type=int,
        nargs=2,
        default=[4, 10],
        help="месяцы поиска; вне сезона гореть нечему, а гранулы месячные и платные по трафику",
    )
    args = parser.parse_args()

    auth = credentials()
    if auth is None:
        raise SystemExit(
            "нет доступа к Earthdata\n"
            "положите EARTHDATA_TOKEN в .env (или пару EARTHDATA_USERNAME и "
            "EARTHDATA_PASSWORD); поиск гранул работает и без него, загрузка — нет"
        )

    if not verify(args.cache, auth):
        raise SystemExit(1)
    if args.verify:
        return

    start_year, end_year = args.years
    rows: list[dict] = []

    with open(args.areas, encoding="utf-8-sig") as handle:
        areas = list(csv.DictReader(handle))

    for meta in areas:
        aoi = meta["aoi_id"]
        bbox = (
            float(meta["bbox_west"]),
            float(meta["bbox_south"]),
            float(meta["bbox_east"]),
            float(meta["bbox_north"]),
        )
        found = []
        first_month, last_month = args.months
        last_day = 31 if last_month in (1, 3, 5, 7, 8, 10, 12) else 30
        for year in range(start_year, end_year + 1):
            try:
                granules = find_granules(
                    bbox,
                    f"{year}-{first_month:02d}-01",
                    f"{year}-{last_month:02d}-{last_day}",
                )
            except (urllib.error.URLError, TimeoutError) as error:
                print(f"{aoi:<18} {year}: каталог недоступен ({error})")
                continue

            for granule in granules:
                try:
                    path = download(granule, args.cache, auth)
                    result = burned_in_bbox(path, granule["title"], bbox)
                except (urllib.error.URLError, OSError) as error:
                    print(f"{aoi:<18} {granule['title']}: {type(error).__name__}")
                    continue
                if result["burned_pixels"] >= args.min_burned:
                    found.append((year, granule, result))

        if not found:
            print(f"{aoi:<18} признаков горения за {start_year}—{end_year} не найдено")
            continue

        for year, granule, result in found:
            days = result["days"]
            rows.append(
                {
                    "event_id": f"{aoi}_MODIS_FIRE_{granule['title'].split('.')[1][1:]}",
                    "aoi_id": aoi,
                    "evidence_type": "внешний продукт гарей",
                    "cause_supported": "признак горения по продукту MODIS",
                    "date_min_product": _day_to_date(year, min(days)) if days else "",
                    "date_max_product": _day_to_date(year, max(days)) if days else "",
                    "burned_pixel_centers_in_aoi": result["burned_pixels"],
                    "all_pixel_centers_in_aoi": result["all_pixels"],
                    "source_id": "MODIS_MCD64A1_061",
                    "evidence_file": str(args.cache / f"{granule['title']}.hdf"),
                    "granule": granule["title"],
                    "limitations": (
                        "Событие выделено по продукту MODIS. Точный контур пожара и наземные "
                        "измерения отсутствуют; продукт даёт признак горения, а не причину "
                        "возгорания."
                    ),
                }
            )
            print(
                f"{aoi:<18} {granule['title']:<44} "
                f"горело {result['burned_pixels']}/{result['all_pixels']} центров"
            )

    if not rows:
        print("\nни одного признака горения — файл не записан")
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nзаписано {args.out}: {len(rows)} событий на {len({r['aoi_id'] for r in rows})} участках")


if __name__ == "__main__":
    main()
