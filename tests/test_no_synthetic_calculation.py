"""Пользовательские API-маршруты не должны выдавать выдуманные измерения."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_plot_route_has_no_synthetic_result_builder() -> None:
    source = (ROOT / "api/app/routers/plots.py").read_text(encoding="utf-8")
    forbidden = (
        "_build_synthetic_result",
        "calc-mock",
        "заглушка мастера",
        "area_ha * 0.86",
        "agb = 150.0",
    )
    for marker in forbidden:
        assert marker not in source


def test_plot_route_uses_the_case_calculation_pipeline() -> None:
    source = (ROOT / "api/app/routers/plots.py").read_text(encoding="utf-8")
    assert "case_service.calculate(" in source
