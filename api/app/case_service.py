"""Расчёт по контуру и периоду — серверная обёртка над расчётным ядром.

KAN-51. Главное правило: здесь **нет ни одной формулы кейса**. Сервис
находит нужные растры, проверяет запрос и вызывает `tools.extract_case_data.
build_aoi` — тот же код, которым посчитан набор из четырёх участков.
Если бы формулы жили ещё и тут, два расчёта разошлись бы молча.

Почему именно `build_aoi`, а не сборка из отдельных функций ядра: он уже
принимает произвольную геометрию параметром `geometry` и собирает результат
в той же форме, что лежит в `case-data.json`. Фронт получает знакомую
структуру, а не вторую её версию.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


def _resolve_repo_root() -> Path:
    """Корень с ядром, инструментами и данными.

    Раскладка разная в репозитории и в образе: локально это `api/app/..`,
    а в контейнере api/ скопирован в /app, и тот же подъём на два уровня
    приводит в корень файловой системы. Поэтому проверяем по содержимому,
    а не по числу уровней.
    """
    env = os.environ.get("FORESTPROOF_ROOT")
    candidates = [Path(env)] if env else []
    candidates += [Path(__file__).resolve().parents[2], Path("/repo"), Path.cwd()]
    for candidate in candidates:
        if (candidate / "forestproof_core").is_dir() and (candidate / "data").is_dir():
            return candidate
    # Ничего не нашли — возвращаем первый кандидат, чтобы ошибка импорта
    # назвала конкретный путь, а не упала где-то глубже.
    return candidates[0]


REPO_ROOT = _resolve_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from forestproof_core.case_calculation import CaseCalculationConfig  # noqa: E402
from tools.extract_case_data import build_aoi, read_year  # noqa: E402

DATA_DIR = Path(os.environ.get("FORESTPROOF_DATA_DIR") or REPO_ROOT / "data")

# Картинки расчётов по загруженным контурам. Лежат внутри api/data —
# оттуда их отдаёт статика (/data), и отдельной раздачи не нужно.
MAPS_ROOT = Path(__file__).resolve().parent.parent / "data" / "contours"
MAPS_URL = "/data/contours"

# Границы запроса из постановки: период 2019–2024, площадь до 20 км².
YEAR_MIN, YEAR_MAX = 2019, 2024
MAX_AREA_HA = 2000.0


class CalculationError(Exception):
    """Запрос отклонён до расчёта. `reason` попадает на экран как есть."""

    def __init__(self, reason: str, *, status: int = 422) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


@dataclass(frozen=True, slots=True)
class CaseSet:
    areas: list[dict]
    baseline: list[dict]
    events: list[dict]
    config: CaseCalculationConfig
    geometries: dict[str, dict]


# Обученная модель устойчивости. Лежит рядом с фронтом, потому что её
# туда пишет tools/train_stability.py; API читает тот же самый файл, а не
# свою копию — иначе экран и ответ службы разошлись бы молча.
MODEL_PATH = REPO_ROOT / "app" / "src" / "data" / "stability-model.json"


@lru_cache(maxsize=1)
def load_stability_model() -> dict | None:
    """Прогноз обученной модели по участкам набора.

    Возвращает None, если файла нет: модель обучается отдельной командой
    и в репозитории может отсутствовать. Отдавать вместо неё пороговые
    правила под видом модели нельзя — это разные методы.
    """
    if not MODEL_PATH.exists():
        return None
    with open(MODEL_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def stability_forecast(aoi_id: str) -> dict | None:
    """Прогноз на 2025–2029 по одному участку, вместе с тем, чем он подкреплён."""
    model = load_stability_model()
    if not model:
        return None
    prediction = next(
        (p for p in model.get("predictions", []) if p.get("aoi_id") == aoi_id), None
    )
    if not prediction or not prediction.get("available"):
        return {
            "available": False,
            "reason": (prediction or {}).get("reason", "участок вне покрытия обучающих данных"),
        }
    return {
        "available": True,
        "method": model.get("method"),
        "forecast": prediction.get("forecast"),
        "backtest": {
            "probability": prediction.get("probability"),
            "category": prediction.get("category"),
            "actual_label": prediction.get("label"),
            "actual_loss_pct": prediction.get("future_loss_pct"),
        },
        "quality": model.get("quality"),
        "sample": model.get("sample"),
        "design": model.get("design"),
        "verdict": model.get("verdict"),
        "limitation": (
            "Прогноз не влияет на число потенциальных единиц: вычет за "
            "неопределённость выводится из H/R, резерв фиксирован условиями кейса."
        ),
    }


@lru_cache(maxsize=1)
def load_case_set() -> CaseSet:
    """Описания набора. Кэшируются: читаются с диска, меняются только вместе
    с самим набором."""

    def rows(path: Path) -> list[dict]:
        with open(path, encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))

    with open(DATA_DIR / "areas.geojson", encoding="utf-8-sig") as handle:
        geometries = {
            feature["properties"]["aoi_id"]: feature["geometry"]
            for feature in json.load(handle)["features"]
        }

    return CaseSet(
        areas=rows(DATA_DIR / "areas.csv"),
        baseline=rows(DATA_DIR / "methodology" / "baseline.csv"),
        events=rows(DATA_DIR / "events.csv"),
        config=CaseCalculationConfig.from_parameter_rows(rows(DATA_DIR / "methodology" / "parameters.csv")),
        geometries=geometries,
    )


def list_areas() -> list[dict]:
    """Участки набора для экрана выбора: имя, регион, роль, площадь."""
    case = load_case_set()
    return [
        {
            "aoi_id": meta["aoi_id"],
            "name": meta.get("name"),
            "region": meta.get("region"),
            "role": meta.get("selection_role"),
            "area_ha_declared": _as_float(meta.get("area_ha")),
            "bbox": [
                float(meta["bbox_west"]),
                float(meta["bbox_south"]),
                float(meta["bbox_east"]),
                float(meta["bbox_north"]),
            ],
        }
        for meta in case.areas
    ]


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def geometry_bbox(geometry: dict) -> tuple[float, float, float, float]:
    if geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise CalculationError("геометрия должна быть Polygon или MultiPolygon в WGS 84")
    polygons = (
        geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    )
    points = [point for polygon in polygons for ring in polygon for point in ring]
    if not points:
        raise CalculationError("в геометрии нет координат")
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    if not all(-180 <= lon <= 180 for lon in lons) or not all(-90 <= lat <= 90 for lat in lats):
        raise CalculationError("координаты вне диапазона WGS 84: ожидаются градусы широты и долготы")
    return min(lons), min(lats), max(lons), max(lats)


def covering_area(geometry: dict) -> dict | None:
    """Участок набора, чьи растры накрывают контур целиком.

    Нужен именно он: растры лежат по участкам, и контур, вылезающий за
    границу тайла, посчитается по обрезанным данным. Такой запрос честнее
    отклонить, чем посчитать наполовину.
    """
    west, south, east, north = geometry_bbox(geometry)
    for meta in load_case_set().areas:
        if (
            float(meta["bbox_west"]) <= west
            and float(meta["bbox_south"]) <= south
            and float(meta["bbox_east"]) >= east
            and float(meta["bbox_north"]) >= north
        ):
            return meta
    return None


def validate_request(geometry: dict, year_start: int, year_end: int) -> dict | None:
    """Проверки до расчёта (В-03, В-05).

    Возвращает участок набора, накрывающий контур, либо None — контур
    может лежать где угодно, и это штатный случай, а не отказ: продукты
    открытые, и данные под такой контур подтягиваются из источника.
    """
    if year_end <= year_start:
        raise CalculationError("конечный год должен быть больше начального")
    if not (YEAR_MIN <= year_start <= YEAR_MAX and YEAR_MIN <= year_end <= YEAR_MAX):
        raise CalculationError(f"период доступен только в диапазоне {YEAR_MIN}–{YEAR_MAX}")

    return covering_area(geometry)


# Историческое окно базовой линии — условия кейса: четырёхлетнее
# изменение 2015→2019 продолжается вперёд.
BASELINE_START = 2015
BASELINE_ANCHOR = 2019
BASELINE_HORIZON = 2029
DERIVED_BASELINE_ID = "HIST-AGB-2015-2019-v1"


def _derive_baseline(geometry: dict, aoi_id: str, config) -> tuple[list[dict], float]:
    """Базовая линия для контура, которого нет в наборе.

    Участкам кейса линия задана условием и пересчёту не подлежит. Для
    чужого контура её задать неоткуда, но и отказывать незачем: кейс сам
    описывает, как она строится — по собственной истории участка,
    g = (c̄2019 − c̄2015) / 4, дальше продолжение с обрезкой снизу нулём.

    Считается по тем же продуктам и тем же кодом, что и всё остальное:
    читаются два года истории, а не выдумывается коэффициент.

    Возвращает строки в форме baseline.csv — чтобы дальше по расчёту шла
    одна ветка, а не отдельная для «своих» и «чужих» участков.
    """
    # Два года истории читаются параллельно: ожидание сетевое, и ставить
    # их в очередь — лишние секунды на каждый запрос.
    with ThreadPoolExecutor(max_workers=2) as pool:
        start, anchor = pool.map(
            lambda year: read_year(DATA_DIR, aoi_id, year, geometry, config),
            (BASELINE_START, BASELINE_ANCHOR),
        )

    c_start, c_anchor = start.get("c_t_ha"), anchor.get("c_t_ha")
    if c_start is None or c_anchor is None:
        raise CalculationError(
            "по этому контуру нет данных биомассы за 2015 или 2019 год, "
            "а без них базовую линию не построить"
        )

    rate = (c_anchor - c_start) / (BASELINE_ANCHOR - BASELINE_START)

    def stock(year: int) -> float:
        # Обрезка нулём снизу: отрицательного запаса не бывает, и
        # продолжать падающую линию в минус значило бы считать по нему.
        return max(0.0, c_anchor + rate * (year - BASELINE_ANCHOR))

    rows = [
        {
            "baseline_id": DERIVED_BASELINE_ID,
            "aoi_id": aoi_id,
            "year_start": str(year),
            "year_end": str(year + 1),
            "pool": "AGB",
            "reference_mean_2015_tc_ha": f"{c_start:.9f}",
            "reference_mean_2019_tc_ha": f"{c_anchor:.9f}",
            "historical_rate_tc_ha_yr": f"{rate:.9f}",
            "baseline_stock_start_tc_ha": f"{stock(year):.9f}",
            "baseline_stock_end_tc_ha": f"{stock(year + 1):.9f}",
            "baseline_delta_tc_ha": f"{rate:.9f}",
            "kind": "выведена нами по формуле кейса",
            "history_product": "ESA CCI Biomass v7.0",
        }
        for year in range(BASELINE_ANCHOR, BASELINE_HORIZON)
    ]
    return rows, rate


def _scene_preview(evidence) -> dict | None:
    """Найденные снимки в той форме, в которой их ждёт экран участка.

    У участков, добавленных нами в набор, снимок лежит в `scene_preview`,
    и страница умеет показывать пару «до и после». Контур пользователя
    собирает такую же пару — значит и класть её надо туда же, а не
    заводить второе место, о котором экран не знает.
    """
    if evidence is None or not evidence.scenes:
        return None

    shots = sorted(evidence.scenes, key=lambda s: s.get("year", 0))
    latest = shots[-1]
    return {
        "image": latest["image"],
        "date": latest.get("date"),
        "scene_id": latest.get("scene_id"),
        "usable_fraction": latest.get("usable_fraction"),
        "cloud_percent": latest.get("cloud_percent"),
        "source": latest.get("source", "Sentinel-2 L2A, окно прочитано из облака по контуру"),
        "shots": [
            {
                "role": shot.get("role", "after"),
                "year": shot.get("year", 0),
                "image": shot["image"],
                "date": shot.get("date"),
                "scene_id": shot.get("scene_id"),
                "usable_fraction": shot.get("usable_fraction"),
            }
            for shot in shots
        ],
    }


def _external_evidence(geometry: dict, year_start: int, year_end: int, maps_dir: Path):
    """Снимки и гари по контуру из открытых каталогов.

    Отказ источника не роняет расчёт: числа по биомассе уже посчитаны, и
    терять их из-за недоступного каталога снимков нельзя. Причина
    возвращается оговоркой и показывается на экране — «не удалось
    подтвердить» и «подтверждений нет» это разные утверждения.
    """
    from tools.contour_evidence import Evidence, collect

    bbox = geometry_bbox(geometry)
    try:
        return collect(bbox, (year_start, year_end), maps_dir, "contour")
    except Exception as error:  # noqa: BLE001 — любой отказ источника терпим
        return Evidence(notes=[f"внешние источники недоступны: {type(error).__name__}"])


def _maps_dir(geometry: dict, year_start: int, year_end: int) -> Path:
    """Папка для картинок этого расчёта.

    Имя выводится из самого запроса, а не из случайного номера: один и
    тот же контур за тот же период попадает в ту же папку, картинки
    переиспользуются, и мусор не копится с каждым нажатием.
    """
    seed = json.dumps(
        {"geometry": geometry, "years": [year_start, year_end]},
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    target = MAPS_ROOT / digest
    target.mkdir(parents=True, exist_ok=True)
    return target


def calculate(
    geometry: dict, year_start: int, year_end: int, *, own_geometry: bool = True
) -> dict:
    """Полный расчёт по контуру. Форма результата — как у участка набора.

    `own_geometry` — контур прислал пользователь. Тогда под него ищутся
    свои снимки и гари: у участка набора они сняты по его собственной
    рамке и про чужой выдел внутри неё ничего не говорят. Запрос по
    идентификатору участка набора приходит с `own_geometry=False` — там
    снимки пришли вместе с данными кейса.

    Контур не обязан лежать внутри участка набора. Если он снаружи,
    данные под него подтягиваются из открытых источников окном по HTTP
    Range, а базовая линия выводится по формуле кейса из его собственной
    истории. Это и есть заявленная работа сервиса: проверить чужой
    участок, а не показать свой набор.
    """
    meta = validate_request(geometry, year_start, year_end)
    case = load_case_set()

    derived_baseline = meta is None
    if derived_baseline:
        # Своего идентификатора у чужого контура нет. Он нужен только
        # чтобы расчёт искал вырезку в наборе (её не будет) и подписывал
        # строки базовой линии — поэтому берётся заведомо несуществующий.
        aoi_id = "AOI-REQUEST"
        baseline_rows, _rate = _derive_baseline(geometry, aoi_id, case.config)
        west, south, east, north = geometry_bbox(geometry)
        meta = {
            "aoi_id": aoi_id,
            # Имя и регион заполняет тот, кто сохраняет контур: на этом шаге
            # мы знаем только координаты. Пустые строки, а не None — экран
            # ждёт текст, и падать на отсутствующем поле ему не за что.
            "name": f"Контур {west:.3f}, {south:.3f}",
            "region": "задан пользователем",
            "selection_role": "контур пользователя",
            "project_status": "расчёт по запросу",
            "baseline_id": DERIVED_BASELINE_ID,
            "bbox_west": west,
            "bbox_south": south,
            "bbox_east": east,
            "bbox_north": north,
            "area_ha": 0.0,
        }
    else:
        baseline_rows = case.baseline

    # Карты рисуются и для загруженного контура. Раньше сюда уходил None
    # с пометкой «карты не рендерим на каждый запрос», и из-за одной этой
    # строки у своего участка пустовали сразу три блока: карта изменений,
    # рельеф и снимок. Данные для них были, их просто некому было строить,
    # и загруженный контур выглядел второсортным рядом с участком набора.
    #
    # Папка задаётся хешем входа: одинаковый контур за тот же период даёт
    # те же картинки, и второй раз они не перерисовываются.
    maps_dir = _maps_dir(geometry, year_start, year_end)

    area = build_aoi(
        DATA_DIR,
        meta,
        baseline_rows,
        case.events,
        maps_dir,
        case.config,
        geometry,
    )

    measured = area.get("area_ha")
    if measured is not None and measured > MAX_AREA_HA:
        raise CalculationError(
            f"площадь контура {measured:.0f} га превышает предел {MAX_AREA_HA:.0f} га "
            "(20 км² по условиям кейса)"
        )

    periods = [
        p for p in area.get("periods", [])
        if p.get("year_start") == year_start and p.get("year_end") == year_end
    ]
    if not periods:
        raise CalculationError(f"период {year_start}–{year_end} не посчитан по этому контуру")

    # Источники слоёв берутся из самого расчёта, а не подписываются
    # задним числом: на экране должно быть видно, читался ли продукт из
    # вложенной вырезки, из тайла в кэше или прямо из облака.
    sources = sorted({row["source"] for row in area.get("series", []) if row.get("source")})

    # Снимки и гари собираются для ЛЮБОГО контура пользователя, а не
    # только для того, что лежит вне набора.
    #
    # Сначала было иначе, и это была ошибка: контур внутри участка кейса
    # оставался без снимка вовсе. Рассуждение «у родителя снимки уже есть»
    # не работает — они сняты по рамке родителя, в сотню раз большей, и
    # выдел в ней не разглядеть. Снимок должен быть про тот контур,
    # который загрузили, иначе он отвечает не на тот вопрос.
    #
    # Для запроса по идентификатору участка набора ничего не ищется: там
    # снимки пришли вместе с данными кейса, и подменять их своими нельзя.
    evidence = None
    if own_geometry:
        evidence = _external_evidence(geometry, year_start, year_end, maps_dir)
    # Возвращается ПОЛНЫЙ участок, а не выжимка из него.
    #
    # Раньше отсюда уходило полтора десятка отобранных полей, и загруженный
    # контур открывался урезанной карточкой «что посчитано и граница» —
    # рядом с участком набора, у которого семь вкладок, он выглядел
    # объектом другого сорта. При этом build_aoi считает ровно ту же
    # структуру, что лежит в case-data.json: ряды по годам, все пары лет,
    # базовую линию по годам, карты, рельеф, устойчивость и справку.
    # Отбирать из неё что-то — значит терять без причины.
    #
    # Поэтому экран участка один на оба случая: он получает знакомую
    # форму и не знает, пришла она из набора или из расчёта по запросу.
    return {
        **area,
        # Чем этот участок отличается от участка набора — тем и подписан.
        "geometry": geometry,
        "geometry_source": "запрос пользователя",
        "parent_area_name": meta.get("name"),
        "maps_base": f"{MAPS_URL}/{maps_dir.name}",
        "period": periods[0],
        "stability_model": None if derived_baseline else stability_forecast(meta["aoi_id"]),
        "baseline_kind": (
            "выведена нами по формуле кейса" if derived_baseline else "задана условиями кейса"
        ),
        "baseline_note": (
            "Базовая линия выведена по собственной истории контура: изменение запаса "
            "2015→2019 продолжено вперёд, как предписывает кейс. Условием она не задана, "
            "и дополнительность проекта не устанавливает"
            if derived_baseline
            else "Базовая линия взята у участка набора, внутри которого лежит контур: "
            "удельная траектория родительского участка и фактическая площадь запроса"
        ),
        # Снимки и события, найденные во внешних каталогах. У участка
        # набора они приходят с данными, у загруженного контура — отсюда.
        "evidence": evidence.as_dict() if evidence is not None else None,
        # Найденные снимки кладутся туда же, где их ищет экран участка.
        # Раньше они лежали только в `evidence`, и страница про них не
        # знала: снимки собирались, но показать их было негде.
        "scene_preview": _scene_preview(evidence),
        # Снимки родительского участка контуру не достаются. Они сняты по
        # его рамке — в сотню раз большей, — и выдел на них не найти.
        # Показать их под именем контура значило бы ответить не на тот
        # вопрос: «что это за место» про совсем другое место.
        "sentinel": None if own_geometry else area.get("sentinel"),
        "events": (evidence.events if evidence is not None else []),
        "data_sources": sources,
        "status": "расчёт по условиям кейса, а не сертифицированные единицы",
    }
