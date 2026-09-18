import pytest

from forestproof_core.scenario_economics import (
    PRICE_DISCLAIMER,
    ScenarioEconomicsConfig,
    calculate_scenario_value,
)


CASE_PRICES = ScenarioEconomicsConfig(
    (("low", 500), ("base", 1500), ("high", 4000))
)


def test_case_example_395_units():
    result = calculate_scenario_value(395, CASE_PRICES)
    assert result["q"] == 395
    assert result["available"] is True
    assert result["reason"] is None
    assert result["scenarios"] == [
        {"name": "low", "price_rub": 500, "value_rub": 197500},
        {"name": "base", "price_rub": 1500, "value_rub": 592500},
        {"name": "high", "price_rub": 4000, "value_rub": 1580000},
    ]
    assert result["disclaimer"] == PRICE_DISCLAIMER


def test_zero_units_have_zero_scenario_value():
    result = calculate_scenario_value(0, CASE_PRICES)
    assert result["available"] is True
    assert [row["value_rub"] for row in result["scenarios"]] == [0, 0, 0]


def test_custom_prices_use_only_q_times_price():
    config = ScenarioEconomicsConfig((("first", 7), ("second", 13)))
    result = calculate_scenario_value(3, config)
    assert [(row["price_rub"], row["value_rub"]) for row in result["scenarios"]] == [
        (7, 21), (13, 39)
    ]


def test_unavailable_units_are_not_valued_as_zero():
    result = calculate_scenario_value(None, CASE_PRICES)
    assert result["q"] is None
    assert result["available"] is False
    assert result["reason"]
    assert [row["value_rub"] for row in result["scenarios"]] == [None, None, None]
    assert result["disclaimer"] == PRICE_DISCLAIMER


def test_invalid_units_and_prices_are_rejected():
    with pytest.raises(ValueError, match="Q"):
        calculate_scenario_value(-1, CASE_PRICES)
    with pytest.raises(ValueError, match="Q"):
        calculate_scenario_value(1.5, CASE_PRICES)
    with pytest.raises(ValueError, match="unique"):
        ScenarioEconomicsConfig((("low", 500), ("low", 1500)))
