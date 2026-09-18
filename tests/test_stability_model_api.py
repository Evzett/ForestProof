"""Прогноз обученной модели в ответе API.

До этого модель существовала только внутри сборки фронта: файл
`stability-model.json` импортировался в `case.ts` и показывался на экране,
а служба расчёта отдавала лишь пороговый скрининг. Со стороны это
выглядело как работающая модель, но по API её было не получить.

Тесты закрепляют три вещи: файл модели читается тот же самый, что видит
фронт; отсутствие файла не подменяется пороговыми правилами; участок вне
покрытия обучающих данных отвечает отказом, а не выдуманной категорией.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "api"))

from app import case_service  # noqa: E402


MODEL_EXISTS = case_service.MODEL_PATH.exists()
needs_model = pytest.mark.skipif(
    not MODEL_EXISTS, reason="модель обучается отдельной командой и в Git не хранится"
)


def _reset_cache():
    case_service.load_stability_model.cache_clear()


def test_model_path_is_the_one_the_frontend_imports():
    """API и экран обязаны читать один файл, иначе разойдутся молча."""
    assert case_service.MODEL_PATH == REPO_ROOT / "app" / "src" / "data" / "stability-model.json"


@needs_model
def test_forecast_matches_the_file():
    _reset_cache()
    payload = json.loads(case_service.MODEL_PATH.read_text(encoding="utf-8"))
    available = [p for p in payload["predictions"] if p.get("available")]
    assert available, "в модели нет ни одного посчитанного участка"

    for prediction in available:
        result = case_service.stability_forecast(prediction["aoi_id"])
        assert result["available"] is True
        assert result["forecast"] == prediction["forecast"]
        assert result["backtest"]["probability"] == prediction["probability"]
        assert result["backtest"]["actual_label"] == prediction["label"]
        assert result["quality"] == payload["quality"]


@needs_model
def test_forecast_horizon_is_in_the_future():
    """Прогноз должен смотреть вперёд, а не пересказывать проверку.

    Окно признаков заканчивается там, где начинается горизонт: если они
    пересекутся, модель будет предсказывать то, что уже видела.
    """
    _reset_cache()
    payload = json.loads(case_service.MODEL_PATH.read_text(encoding="utf-8"))
    for prediction in payload["predictions"]:
        forecast = prediction.get("forecast")
        if not forecast:
            continue
        feature_end = forecast["feature_window"][1]
        horizon_start = forecast["horizon"][0]
        assert horizon_start > feature_end


def test_unknown_area_is_refused_not_guessed():
    _reset_cache()
    result = case_service.stability_forecast("RU_NOT_IN_SET")
    if result is None:
        pytest.skip("файла модели нет — отвечать нечем, и это корректно")
    assert result["available"] is False
    assert result["reason"]
    assert "forecast" not in result


def test_missing_model_returns_none_not_threshold_rules(tmp_path, monkeypatch):
    """Без файла модели служба молчит.

    Подставить сюда пороговый скрининг было бы удобно и неверно: это
    другой метод, и выдавать его за модель значит врать о происхождении
    числа.
    """
    monkeypatch.setattr(case_service, "MODEL_PATH", tmp_path / "нет-такого.json")
    _reset_cache()
    try:
        assert case_service.load_stability_model() is None
        assert case_service.stability_forecast("RU_TVER_01") is None
    finally:
        _reset_cache()
