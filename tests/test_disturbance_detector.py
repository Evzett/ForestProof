"""Детектор пространственных событий потери покрова.

Инструмент пришёл от команды отдельно и делает то, чего у нас не было:
находит внутри произвольного контура связные пятна потери и собирает их
в годовые события. Наш `cover_loss` даёт только площадь за год, без
разбиения на пятна и без геометрии.

Главное, что здесь проверяется, — согласие с уже посчитанным. Если
детектор даёт по участку другую площадь, чем основной расчёт, то один
из двух читает растр неправильно, и знать об этом надо сразу.

Второе — разделение наблюдения и причины. Hansen подтверждает потерю
покрова, но не её причину; детектор обязан это состояние сохранять,
а не подставлять «вырубку» по умолчанию.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from disturbance_detector import detect_hansen_events  # noqa: E402

DATA_DIR = REPO_ROOT / "data"
AOI = "RU_MORDOVIA_03"
GFC = DATA_DIR / AOI / "GFC_2025_v1_13.tif"
GEOJSON = DATA_DIR / "areas.geojson"
CASE_DATA = REPO_ROOT / "app" / "src" / "data" / "case-data.json"

needs_rasters = pytest.mark.skipif(
    not (GFC.exists() and GEOJSON.exists()),
    reason="растры набора не распространяются с Git",
)


def _geometry() -> dict:
    document = json.loads(GEOJSON.read_text(encoding="utf-8-sig"))
    for feature in document["features"]:
        if feature["properties"]["aoi_id"] == AOI:
            return feature["geometry"]
    raise AssertionError(f"контур {AOI} не найден")


@needs_rasters
def test_events_agree_with_the_main_calculation():
    """Сумма событий за период должна сойтись с cover_loss основного расчёта."""
    if not CASE_DATA.exists():
        pytest.skip("case-data.json не собран")

    events = detect_hansen_events(GFC, _geometry(), 2020, 2024, aoi_id=AOI)
    detected = sum(e["area_ha"] for e in events)

    areas = json.loads(CASE_DATA.read_text(encoding="utf-8"))["areas"]
    area = next(a for a in areas if a["aoi_id"] == AOI)
    expected = sum(l["area_ha"] for l in area["cover_loss"] if 2020 <= l["year"] <= 2024)

    # Допуск в гектар: детектор режет пиксель по контуру так же, как
    # основной расчёт, но порядок сложения другой.
    assert detected == pytest.approx(expected, abs=1.0)


@needs_rasters
def test_cause_is_never_invented():
    """Год потери известен, причина — нет. Детектор не вправе её дописывать."""
    events = detect_hansen_events(GFC, _geometry(), 2019, 2024, aoi_id=AOI)
    assert events, "на этом участке потери есть, событий быть не может только по ошибке"
    for event in events:
        assert event["cause_supported"] is False
        assert event["cause_status"] == "причина не установлена"
        assert event["event_type"] == "tree_cover_loss"


@needs_rasters
def test_year_stays_inside_the_requested_period():
    events = detect_hansen_events(GFC, _geometry(), 2021, 2023, aoi_id=AOI)
    assert events
    assert all(2021 <= e["year"] <= 2023 for e in events)


@needs_rasters
def test_exposure_is_labelled_as_an_estimate_not_a_measurement():
    """Оценка выброса по площади — это умножение, а не измерение.

    Если её подать как измеренную величину, она попадёт в расчёт единиц,
    где ей не место: изменение запаса уже посчитано по биомассе.
    """
    events = detect_hansen_events(GFC, _geometry(), 2022, 2022, aoi_id=AOI, co2_stock_t_ha=133.6)
    assert events
    for event in events:
        assert event["estimated_carbon_exposure_tco2e"] is not None
        assert "не независимое измерение" in event["contribution_method"]


@needs_rasters
def test_small_patches_can_be_filtered_without_changing_the_year():
    from disturbance_detector import DetectionConfig

    loose = detect_hansen_events(GFC, _geometry(), 2019, 2024, aoi_id=AOI)
    strict = detect_hansen_events(
        GFC, _geometry(), 2019, 2024, aoi_id=AOI, config=DetectionConfig(min_event_area_ha=1.0)
    )
    assert len(strict) <= len(loose)
    assert all(e["area_ha"] >= 1.0 for e in strict)
