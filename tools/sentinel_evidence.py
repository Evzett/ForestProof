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
from PIL import Image, ImageDraw

from geotiff import Raster, read_geotiff


VALID_SCL = {4, 5, 6, 7}
MIN_USABLE_FRACTION = 0.50

# Сдвиг BOA_ADD_OFFSET, появившийся в Sentinel-2 L2A с версии обработки 04.00.
# В наборе он не снят, и сцены разных версий лежат на разных нулях.
BOA_ADD_OFFSET = 0.1
BASELINE_WITH_OFFSET = 4.0


def harmonise_reflectance(raster: Raster, processing_baseline: str) -> Raster:
    """Приводит отражение сцены к базе версий до 04.00.

    Зачем. С версии обработки 04.00 ESA сместила кодирование на
    BOA_ADD_OFFSET = −1000 DN, то есть на −0,1 в отражении. В наборе кейса
    сдвиг не снят, и это видно невооружённым глазом: на одном и том же
    участке в один и тот же сезон красный канал даёт +0,023 при версии
    02.12 и −0,085 при 05.00, а NDVI выходит 2,15 при физическом
    пределе 1.

    Без приведения любое сравнение индексов между сценами разных версий
    измеряет разницу форматов, а не изменение леса. Ошибка тихая: числа
    получаются правдоподобного вида, просто неверные.
    """
    try:
        baseline = float(processing_baseline)
    except (TypeError, ValueError):
        return raster
    if baseline < BASELINE_WITH_OFFSET:
        return raster

    data = raster.data.astype("float32", copy=True)
    data += BOA_ADD_OFFSET
    return Raster(
        data=data,
        lon_origin=raster.lon_origin,
        lat_origin=raster.lat_origin,
        lon_step=raster.lon_step,
        lat_step=raster.lat_step,
        nodata=raster.nodata,
        metadata=raster.metadata,
    )


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


def utm_zone(lon: float) -> int:
    """Номер зоны UTM по долготе центра контура.

    Прибивать зону к 38-й нельзя: она верна только для Мордовии. Тверь
    лежит в 36-й, Вологда в 37-й, и маска по контуру там уехала бы
    на сотни километров — молча, потому что полигон всё равно
    нарисовался бы.
    """
    return int((lon + 180) // 6) + 1


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


def _read_reflectance(path: Path, processing_baseline: str = "") -> Raster:
    """Отражение читается тем же читателем, что и остальные растры.

    Раньше здесь был tifffile: наш читатель не понимал предиктор 3
    (плавающее горизонтальное дифференцирование), которым записаны
    файлы отражения. Теперь понимает, поэтому tifffile и imagecodecs
    из зависимостей убраны — ради шести тегов тащить две геобиблиотеки
    незачем, а на машинах команды они же и не ставятся.
    """
    return harmonise_reflectance(read_geotiff(str(path)), processing_baseline)


def _quality(data_dir: Path, row: dict, bbox, epsg: int) -> tuple[float, np.ndarray, np.ndarray]:
    reflectance_path, scl_path = _paths(data_dir, row)
    reflectance = _read_reflectance(reflectance_path, row.get("processing_baseline", ""))
    scl = read_geotiff(str(scl_path)).band(0)
    inside = _polygon_mask(reflectance, bbox, epsg)
    valid = inside & np.isin(scl, list(VALID_SCL))
    fraction = float(valid.sum() / inside.sum()) if inside.any() else 0.0
    return fraction, inside, valid


# Во что переводится 98-й процентиль яркости. Не в единицу: тогда
# светлые участки — вырубки, поля, песок — сливаются в белое пятно,
# а лес выцветает. Значение подобрано по снимкам набора так, чтобы
# хвойный лес читался тёмно-зелёным, каким он и выглядит.
TARGET_WHITE = 0.45


def stretch_rgb(bands, mask=None):
    """Три канала к диапазону 0…1 ОДНИМ общим преобразованием.

    Ключевая деталь, из-за которой функция общая. Если растягивать
    каждый канал по своим процентилям, соотношение между ними
    меняется — и лес получается фиолетовым: синего в нём меньше всех,
    и растянутый до того же предела он вылезает вперёд. Именно так
    выглядели снимки, пока растяжек было две.

    Общий множитель на три канала меняет только яркость, не трогая
    цвет: зелёное остаётся зелёным. Это по-прежнему обработка для
    показа, но она не переписывает то, что снял прибор. Ни одно число
    расчёта из картинок не берётся.

    `mask` — пиксели, по которым считать процентили: за контуром и в
    облаках лежат значения, к участку отношения не имеющие, и по ним
    нельзя подбирать яркость.
    """
    stack = np.dstack([np.asarray(b, dtype=float) for b in bands])
    if mask is None:
        values = stack[stack > 0]
    else:
        values = stack[np.dstack([mask] * stack.shape[2]) & np.isfinite(stack) & (stack > 0)]
    if values.size == 0:
        return np.zeros_like(stack)

    # Множитель, а не растяжка от нижней границы. Вычитание низа — это
    # то, что делает лес кислотно-зелёным: отражение хвойного леса
    # лежит в узкой тёмной полосе (примерно 0,013…0,054), зелёный канал
    # в ней вдвое выше красного и синего, и после сдвига нуля эта
    # разница раздувается втрое.
    #
    # Чистый множитель сохраняет отношение каналов ровно таким, каким
    # его снял прибор: меняется яркость, цвет остаётся. Так же устроен
    # обычный true color у поставщиков снимков.
    high = float(np.percentile(values, 98))
    gain = TARGET_WHITE / max(high, 1e-6)
    return np.clip(stack * gain, 0, 1)


def _render_scene(data_dir: Path, row: dict, bbox, epsg: int, output: Path) -> dict:
    reflectance_path, scl_path = _paths(data_dir, row)
    raster = _read_reflectance(reflectance_path, row.get("processing_baseline", ""))
    scl = read_geotiff(str(scl_path)).band(0)
    inside = _polygon_mask(raster, bbox, epsg)
    valid = inside & np.isin(scl, list(VALID_SCL))

    # B04/B03/B02. Растяжка только для показа; все количественные
    # сравнения ниже идут по исходным значениям отражения.
    rgb = stretch_rgb(
        [raster.data[2], raster.data[1], raster.data[0]],
        mask=valid,
    )
    # Отражение леса лежит в тёмной части диапазона: без гаммы снимок
    # выходит почти чёрным.
    rgb = np.power(rgb, 1 / 1.6)
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
        "processing_baseline": row.get("processing_baseline", ""),
        "harmonised": float(row.get("processing_baseline") or 0) >= BASELINE_WITH_OFFSET,
    }


def _spectral_metrics(data_dir: Path, before: dict, after: dict, bbox, epsg: int) -> dict:
    before_r = _read_reflectance(
        _paths(data_dir, before)[0], before.get("processing_baseline", "")
    )
    after_r = _read_reflectance(
        _paths(data_dir, after)[0], after.get("processing_baseline", "")
    )
    _, _, before_valid = _quality(data_dir, before, bbox, epsg)
    _, _, after_valid = _quality(data_dir, after, bbox, epsg)
    common = before_valid & after_valid
    if not common.any():
        return {"comparable_fraction": 0.0, "delta_ndvi": None, "delta_nbr": None}

    def index(raster, left: int, right: int) -> np.ndarray:
        """Нормализованный индекс с физическим порогом знаменателя.

        Отражение L2A бывает слегка отрицательным после атмосферной
        коррекции, поэтому сумма каналов проходит через ноль и отношение
        улетает в сотни. Порог 0,01 отсекает такие пиксели, а обрезка
        по ±1 ловит остатки: у нормализованного индекса другого диапазона
        не бывает, и значение вне его — это не наблюдение, а деление.
        """
        a = raster.band(left).astype(float)
        b = raster.band(right).astype(float)
        total = a + b
        ratio = np.divide(a - b, total, out=np.full_like(a, np.nan), where=total > 0.01)
        return np.where(np.abs(ratio) <= 1.0, ratio, np.nan)

    # Band order: B02, B03, B04, B8A, B11, B12.
    before_ndvi, after_ndvi = index(before_r, 3, 2), index(after_r, 3, 2)
    before_nbr, after_nbr = index(before_r, 3, 5), index(after_r, 3, 5)
    inside = _polygon_mask(before_r, bbox, epsg)
    return {
        "comparable_fraction": float(common.sum() / inside.sum()),
        "delta_ndvi": float(np.nanmean(after_ndvi[common] - before_ndvi[common])),
        "delta_nbr": float(np.nanmean(after_nbr[common] - before_nbr[common])),
        "note": (
            "Изменение индексов посчитано только по пикселям, пригодным на обе даты, "
            "после приведения сцен к одной версии обработки."
        ),
        "baselines": [
            before.get("processing_baseline", ""),
            after.get("processing_baseline", ""),
        ],
    }


def build_event_evidence(data_dir: Path, event: dict, bbox, output_dir: Path) -> dict:
    """Build an auditable before/immediate-after/recovery evidence bundle."""
    aoi = event["aoi_id"]
    epsg = 32600 + utm_zone((bbox[0] + bbox[2]) / 2)
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


def build_period_evidence(
    data_dir: Path, aoi: str, bbox, output_dir: Path, years: tuple[int, int] = (2019, 2024)
) -> dict:
    """Наблюдения для участка, у которого подтверждённого события нет.

    Берём по одной пригодной сцене в начале и в конце периода, причём
    в один и тот же сезон: пара «июль → сентябрь» покажет фенологию,
    а не потерю, и разность индексов будет про листву.
    """
    epsg = 32600 + utm_zone((bbox[0] + bbox[2]) / 2)
    rows = _scene_rows(data_dir, aoi)
    if not rows:
        return {"observations": [], "comparison": None}

    first = [r for r in rows if int(r["year"]) == years[0]]
    last = [r for r in rows if int(r["year"]) == years[1]]
    if not first or not last:
        first, last = rows[:1], rows[-1:]

    def month(row: dict) -> int:
        return int(row["datetime_utc"][5:7])

    def quality(row: dict) -> float:
        return _quality(data_dir, row, bbox, epsg)[0]

    before = max(first, key=quality)
    # из последнего года берём ближайший по месяцу к начальному наблюдению
    after = min(last, key=lambda r: (abs(month(r) - month(before)), -quality(r)))

    observations = []
    by_role = {}
    for role, row in (("before", before), ("recovery", after)):
        rendered = _render_scene(
            data_dir, row, bbox, epsg, output_dir / f"{aoi}_{role}.png"
        )
        rendered["role"] = role
        observations.append(rendered)
        by_role[role] = row

    comparison = _spectral_metrics(data_dir, by_role["before"], by_role["recovery"], bbox, epsg)
    comparison.update({"before_role": "before", "after_role": "recovery"})

    return {
        "observations": observations,
        "comparison": comparison,
        "quality_rule": "SCL классы 4, 5, 6 и 7; пригодность не ниже 50%",
        "display_note": (
            "RGB-контраст нормирован отдельно для каждой даты; индексы считаются "
            "по исходному отражению."
        ),
        "interpretation": (
            "Подтверждённого события на участке нет, поэтому пара наблюдений взята "
            "по краям периода в один сезон. Изменение индексов показывает, что "
            "изменилось, но причину не устанавливает."
        ),
    }
