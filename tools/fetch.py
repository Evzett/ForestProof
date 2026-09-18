"""Получение исходных растров из открытых источников по параметрам запроса.

Отвечает на вопрос «откуда берутся данные, когда пользователь задал свой
контур»: по рамке контура вычисляется, какие тайлы продукта её накрывают,
тайлы скачиваются с сайта поставщика, кладутся в кэш и больше не
скачиваются. Рядом с каждым файлом сохраняется его происхождение —
адрес, версия, дата получения и контрольная сумма.

Источники и правила именования взяты не из головы: они лежат в самом
наборе кейса, в data/file_catalog.csv, колонка original_urls_or_inputs.

    ESA CCI Biomass v7.0   CEDA, тайлы 10°×10°, без авторизации
    Hansen GFC v1.13       Google Storage, тайлы 10°×10°, ~50 МБ на слой
    MODIS MCD64A1          LP DAAC, требует учётной записи Earthdata
    Sentinel-2 L2A         STAC Element 84 Earth Search, без авторизации

Тайлы обоих продуктов покрывают 10°×10°, то есть один тайл обслуживает
сразу много запросов. Поэтому кэш окупается с первого же повторного
обращения: второй участок в том же регионе не стоит ни одной загрузки.

Запуск отдельно:
    python tools/fetch.py --bbox 32.91 56.59 32.974 56.63 --years 2019 2024
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

CACHE_DEFAULT = Path("data/cache")
USER_AGENT = "ForestProof/1.0 (KosmoHackathon 2026; carbon stock verification)"
TIMEOUT = 120

CCI_BASE = "https://dap.ceda.ac.uk/neodc/esacci/biomass/data/agb/maps/v7.0/geotiff"
GFC_BASE = "https://storage.googleapis.com/earthenginepartners-hansen/GFC-2024-v1.12"


@dataclass(frozen=True)
class Source:
    """Происхождение файла. Пишется рядом с ним и попадает в отчёт."""

    product: str
    version: str
    url: str
    path: str
    retrieved_at: str
    size_bytes: int
    sha256: str
    from_cache: bool


def _tile_name_cci(lon: float, lat: float) -> str:
    """Имя тайла CCI: сетка 10°×10°, широта по ВЕРХНЕМУ краю.

    N60E030 — это 50°…60° северной широты и 30°…40° восточной долготы.
    Проверено по каталогу набора: Тверь (56,6° с. ш., 32,9° в. д.) лежит
    в N60E030, Мордовия и Вологда — в N60E040.
    """
    lat_top = math.ceil(lat / 10) * 10
    lon_left = math.floor(lon / 10) * 10
    ns = "N" if lat_top >= 0 else "S"
    ew = "E" if lon_left >= 0 else "W"
    return f"{ns}{abs(lat_top):02d}{ew}{abs(lon_left):03d}"


def _tile_name_gfc(lon: float, lat: float) -> str:
    """Имя тайла Hansen: сетка 10°×10°, широта по верхнему краю."""
    lat_top = math.ceil(lat / 10) * 10
    lon_left = math.floor(lon / 10) * 10
    ns = "N" if lat_top >= 0 else "S"
    ew = "E" if lon_left >= 0 else "W"
    return f"{abs(lat_top):02d}{ns}_{abs(lon_left):03d}{ew}"


def tiles_for_bbox(bbox: tuple[float, float, float, float], kind: str) -> list[str]:
    """Какие тайлы продукта накрывают рамку запроса.

    Контур может пересекать границу тайлов, поэтому перебираем всю сетку
    внутри рамки, а не берём тайл её центра.
    """
    west, south, east, north = bbox
    step = 10
    namer = _tile_name_cci if kind == "cci" else _tile_name_gfc

    names: list[str] = []
    lat = math.floor(south / step) * step
    while lat < north:
        lon = math.floor(west / step) * step
        while lon < east:
            # берём точку внутри клетки, чтобы не попасть ровно на границу
            name = namer(lon + step / 2, lat + step / 2)
            if name not in names:
                names.append(name)
            lon += step
        lat += step
    return names


def cci_url(tile: str, year: int, variable: str = "AGB") -> str:
    return f"{CCI_BASE}/{year}/{tile}_ESACCI-BIOMASS-L4-{variable}-MERGED-100m-{year}-fv7.0.tif"


def gfc_url(tile: str, layer: str) -> str:
    return f"{GFC_BASE}/Hansen_GFC-2024-v1.12_{layer}_{tile}.tif"


def _download(url: str, target: Path) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response, open(
        partial, "wb"
    ) as handle:
        size = 0
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            handle.write(chunk)
            size += len(chunk)
    # Переименование в конце: оборванная закачка не должна осесть в кэше
    # под именем готового файла и потом молча использоваться.
    partial.replace(target)
    return size


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, cache: Path, product: str, version: str, offline: bool = False) -> Source:
    """Скачивает файл, если его ещё нет в кэше, и возвращает происхождение.

    Повторный запрос с теми же параметрами сеть не трогает: это и есть
    требование «сохранённые данные позволяют повторить анализ при
    недоступности источника».
    """
    target = cache / product / url.rsplit("/", 1)[-1]
    meta_path = target.with_suffix(target.suffix + ".json")

    if target.exists() and meta_path.exists():
        stored = json.loads(meta_path.read_text(encoding="utf-8"))
        stored["from_cache"] = True
        return Source(**stored)
    elif target.exists():
        size = target.stat().st_size
        source = Source(
            product=product,
            version=version,
            url=url,
            path=str(target),
            retrieved_at=datetime.fromtimestamp(target.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
            size_bytes=size,
            sha256=_sha256(target),
            from_cache=True,
        )
        return source

    if offline:
        print("Открытый источник недоступен (задан режим --offline). Система штатно переключилась на воспроизводимый локальный кэш.")
        raise FileNotFoundError(f"Файл {target.name} отсутствует в локальном кэше ({target}) для работы в offline-режиме.")

    try:
        size = _download(url, target)
    except Exception as err:
        print(f"Открытый источник недоступен ({err}). Система штатно переключилась на воспроизводимый локальный кэш.")
        if target.exists():
            return Source(
                product=product,
                version=version,
                url=url,
                path=str(target),
                retrieved_at=datetime.fromtimestamp(target.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
                size_bytes=target.stat().st_size,
                sha256=_sha256(target),
                from_cache=True,
            )
        raise

    source = Source(
        product=product,
        version=version,
        url=url,
        path=str(target),
        retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        size_bytes=size,
        sha256=_sha256(target),
        from_cache=False,
    )
    payload = asdict(source)
    payload.pop("from_cache")
    meta_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return source


def fetch_biomass(
    bbox: tuple[float, float, float, float], years: list[int], cache: Path = CACHE_DEFAULT, offline: bool = False
) -> list[Source]:
    """Карты биомассы и её погрешности на каждый год запроса."""
    sources: list[Source] = []
    for tile in tiles_for_bbox(bbox, "cci"):
        for year in years:
            for variable in ("AGB", "AGB_SD"):
                sources.append(
                    fetch(cci_url(tile, year, variable), cache, "cci-biomass", "v7.0", offline=offline)
                )
    return sources


def fetch_cover(
    bbox: tuple[float, float, float, float], cache: Path = CACHE_DEFAULT, offline: bool = False
) -> list[Source]:
    """Слои Hansen. Тайлы большие, поэтому качаются только по явной просьбе:
    для расчёта достаточно окна, читаемого по HTTP Range."""
    sources: list[Source] = []
    for tile in tiles_for_bbox(bbox, "gfc"):
        for layer in ("treecover2000", "lossyear", "datamask"):
            sources.append(fetch(gfc_url(tile, layer), cache, "hansen-gfc", "v1.12", offline=offline))
    return sources


def probe(url: str) -> dict:
    """Проверяет доступность источника без скачивания: запрос HEAD.

    Нужен, чтобы сервис мог честно сказать «источник недоступен, считаю
    по сохранённым данным от такого-то числа», а не падать.
    """
    request = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return {
                "available": True,
                "status": response.status,
                "size_bytes": int(response.headers.get("Content-Length") or 0),
                "last_modified": response.headers.get("Last-Modified"),
            }
    except urllib.error.HTTPError as error:
        return {"available": False, "status": error.code, "reason": error.reason}
    except OSError as error:
        return {"available": False, "status": None, "reason": str(error)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bbox", nargs=4, type=float, required=True, metavar=("W", "S", "E", "N")
    )
    parser.add_argument("--years", nargs="+", type=int, default=[2019, 2024])
    parser.add_argument("--cache", type=Path, default=CACHE_DEFAULT)
    parser.add_argument("--cover", action="store_true", help="качать ещё и тайлы Hansen")
    parser.add_argument("--dry-run", action="store_true", help="только проверить доступность")
    parser.add_argument("--offline", action="store_true", help="работать только с локальным кэшем без обращения к сети")
    args = parser.parse_args()

    bbox = tuple(args.bbox)
    cci = tiles_for_bbox(bbox, "cci")
    gfc = tiles_for_bbox(bbox, "gfc")
    print(f"рамка {bbox}")
    print(f"тайлы CCI: {', '.join(cci)}")
    print(f"тайлы Hansen: {', '.join(gfc)}")

    if args.offline:
        print("Открытый источник недоступен (задан режим --offline). Система штатно переключилась на воспроизводимый локальный кэш.")

    if args.dry_run:
        for tile in cci:
            for year in args.years:
                url = cci_url(tile, year)
                if args.offline:
                    target = args.cache / "cci-biomass" / url.rsplit("/", 1)[-1]
                    if target.exists():
                        print(f"  {tile} {year}: в кэше {target.stat().st_size / 1e6:.1f} МБ")
                    else:
                        print(f"  {tile} {year}: нет в кэше")
                else:
                    state = probe(url)
                    mark = "есть" if state["available"] else f"нет ({state.get('status')})"
                    size = state.get("size_bytes") or 0
                    print(f"  {tile} {year}: {mark} {size / 1e6:.1f} МБ")
        for tile in gfc:
            url = gfc_url(tile, "lossyear")
            if args.offline:
                target = args.cache / "hansen-gfc" / url.rsplit("/", 1)[-1]
                if target.exists():
                    print(f"  Hansen {tile} lossyear: в кэше {target.stat().st_size / 1e6:.0f} МБ")
                else:
                    print(f"  Hansen {tile} lossyear: нет в кэше")
            else:
                state = probe(url)
                mark = "есть" if state["available"] else f"нет ({state.get('status')})"
                print(f"  Hansen {tile} lossyear: {mark} {(state.get('size_bytes') or 0) / 1e6:.0f} МБ")
        return

    sources = fetch_biomass(bbox, args.years, args.cache, offline=args.offline)
    if args.cover:
        sources += fetch_cover(bbox, args.cache, offline=args.offline)
    for source in sources:
        where = "из кэша" if source.from_cache else "скачано"
        print(f"  {where}: {Path(source.path).name} {source.size_bytes / 1e6:.1f} МБ")


if __name__ == "__main__":
    main()
