"""Контур вне участков набора. KAN-78.

Раньше такой запрос отклонялся: «контур выходит за пределы участков
набора». Это сводило сервис к показу своего набора — проверить чужой
участок было нельзя, хотя ровно в этом его работа.

Тесты закрепляют не сам сетевой поход, а правила вокруг него: что
контур снаружи больше не отвергается, что базовая линия для него
выводится по формуле кейса, и что выведенная линия честно помечена и не
выдаётся за заданную условием.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "api"))

from app import case_service  # noqa: E402

# Контур под Костромой: заведомо вне всех участков набора.
OUTSIDE = {
    "type": "Polygon",
    "coordinates": [[[41.90, 58.70], [41.93, 58.70], [41.93, 58.718], [41.90, 58.718], [41.90, 58.70]]],
}


def test_contour_outside_the_set_has_no_parent_area():
    assert case_service.covering_area(OUTSIDE) is None


def test_contour_outside_the_set_is_not_rejected():
    """Главное: отсутствие родительского участка — не отказ.

    Проверка идёт до сети: validate_request только проверяет запрос и
    возвращает участок либо None, растров не читает.
    """
    assert case_service.validate_request(OUTSIDE, 2019, 2024) is None


def test_period_rules_still_apply_outside_the_set():
    """Снятие одного ограничения не снимает остальные."""
    with pytest.raises(case_service.CalculationError):
        case_service.validate_request(OUTSIDE, 2024, 2019)
    with pytest.raises(case_service.CalculationError):
        case_service.validate_request(OUTSIDE, 2015, 2024)


def test_derived_baseline_follows_the_case_formula(monkeypatch):
    """g = (c̄2019 − c̄2015) / 4, дальше продолжение от 2019 с обрезкой нулём.

    Чтение растров подменяется: проверяется формула, а не сеть.
    """
    means = {2015: 40.0, 2019: 48.0}
    monkeypatch.setattr(
        case_service,
        "read_year",
        lambda _dir, _aoi, year, _geom, _cfg: {"c_t_ha": means[year]},
    )

    rows, rate = case_service._derive_baseline(OUTSIDE, "AOI-REQUEST", None)

    assert rate == pytest.approx((48.0 - 40.0) / 4)
    by_year = {int(r["year_start"]): float(r["baseline_stock_start_tc_ha"]) for r in rows}
    assert by_year[2019] == pytest.approx(48.0)
    assert by_year[2020] == pytest.approx(50.0)
    assert by_year[2024] == pytest.approx(58.0)


def test_falling_baseline_is_clipped_at_zero(monkeypatch):
    """Падающая линия не уходит в минус: отрицательного запаса не бывает."""
    means = {2015: 40.0, 2019: 8.0}
    monkeypatch.setattr(
        case_service,
        "read_year",
        lambda _dir, _aoi, year, _geom, _cfg: {"c_t_ha": means[year]},
    )

    rows, rate = case_service._derive_baseline(OUTSIDE, "AOI-REQUEST", None)

    assert rate < 0
    stocks = [float(r["baseline_stock_start_tc_ha"]) for r in rows]
    assert min(stocks) == 0.0
    assert all(value >= 0 for value in stocks)


def test_derived_baseline_is_marked_as_derived(monkeypatch):
    """Выведенная линия не выдаётся за заданную условием.

    Разница не косметическая: линии участков кейса заданы постановкой и
    пересчёту не подлежат, а эту мы вывели сами и обязаны об этом
    говорить — иначе проверяющий примет наше допущение за условие.
    """
    monkeypatch.setattr(
        case_service,
        "read_year",
        lambda _dir, _aoi, year, _geom, _cfg: {"c_t_ha": 40.0 if year == 2015 else 48.0},
    )
    rows, _ = case_service._derive_baseline(OUTSIDE, "AOI-REQUEST", None)
    assert all(row["kind"] == "выведена нами по формуле кейса" for row in rows)


def test_missing_history_is_refused_not_guessed(monkeypatch):
    """Нет данных за 2015 или 2019 — отказ с причиной, а не подставленный ноль."""
    monkeypatch.setattr(
        case_service,
        "read_year",
        lambda _dir, _aoi, year, _geom, _cfg: {"c_t_ha": None if year == 2015 else 48.0},
    )
    with pytest.raises(case_service.CalculationError, match="базовую линию"):
        case_service._derive_baseline(OUTSIDE, "AOI-REQUEST", None)
