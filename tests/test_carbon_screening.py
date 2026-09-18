import pytest

from forestproof_core import (
    CarbonScreeningConfig,
    build_disturbance_events,
    build_measurement,
    calculate_co2_stock_per_ha,
)


CONFIG = CarbonScreeningConfig()
MEASUREMENT_KEYS = {
    "forest_area_ha_latest",
    "forest_area_change_pct",
    "agb_t_ha",
    "agb_sd_t_ha",
    "agb_source_year",
    "co2_stock_equivalent_t_ha",
    "co2_stock_total_t",
    "series",
}
EVENT_KEYS = {
    "event_id",
    "year",
    "area_ha",
    "event_type",
    "confidence",
    "physical_carbon_exposure_co2_t",
}


def observation(year, area, agb=100.0, valid=True, source_year=2022):
    return {
        "year": year,
        "forest_area_ha": area,
        "agb_t_ha": agb,
        "agb_sd_t_ha": 20.0 if agb is not None else None,
        "agb_source_year": source_year if agb is not None else None,
        "valid": valid,
    }


def test_measurement_uses_valid_years_and_preserves_biomass_source():
    geo = {
        "observations": [
            observation(2020, 1000.0),
            observation(2021, 10.0, valid=False),
            observation(2022, 900.0),
        ]
    }
    result = build_measurement(geo, CONFIG)

    assert set(result) == MEASUREMENT_KEYS
    assert result["forest_area_ha_latest"] == 900.0
    assert result["forest_area_change_pct"] == pytest.approx(-10.0)
    assert result["agb_t_ha"] == 100.0
    assert result["agb_sd_t_ha"] == 20.0
    assert result["agb_source_year"] == 2022
    assert result["co2_stock_equivalent_t_ha"] == pytest.approx(172.33333333333334)
    assert result["co2_stock_total_t"] == pytest.approx(155100.0)
    assert result["series"] == [
        {
            "year": 2020,
            "forest_area_ha": 1000.0,
            "co2_stock_total_t": pytest.approx(172333.33333333334),
        },
        {"year": 2021, "forest_area_ha": None, "co2_stock_total_t": None},
        {
            "year": 2022,
            "forest_area_ha": 900.0,
            "co2_stock_total_t": pytest.approx(155100.0),
        },
    ]


def test_formula_matches_manual_calculation_and_config_is_used():
    assert calculate_co2_stock_per_ha(148.0, CONFIG) == pytest.approx(
        148.0 * 0.47 * 44 / 12
    )
    custom = CarbonScreeningConfig(carbon_fraction=0.5, co2_to_carbon_ratio=4)
    assert calculate_co2_stock_per_ha(100.0, custom) == 200.0


def test_missing_agb_yields_null_carbon_without_losing_area():
    result = build_measurement(
        {"observations": [observation(2020, 1000, agb=None)]}, CONFIG
    )
    assert result["forest_area_ha_latest"] == 1000
    assert result["agb_t_ha"] is None
    assert result["agb_sd_t_ha"] is None
    assert result["agb_source_year"] is None
    assert result["co2_stock_equivalent_t_ha"] is None
    assert result["co2_stock_total_t"] is None
    assert result["series"][0]["co2_stock_total_t"] is None


def test_missing_area_keeps_stock_per_ha_but_total_is_null():
    result = build_measurement(
        {"observations": [observation(2020, None)]}, CONFIG
    )
    assert result["forest_area_ha_latest"] is None
    assert result["co2_stock_equivalent_t_ha"] == pytest.approx(100 * 0.47 * 44 / 12)
    assert result["co2_stock_total_t"] is None
    assert result["series"][0]["co2_stock_total_t"] is None


@pytest.mark.parametrize("observations", [[], [observation(2020, 1000)]])
def test_area_change_needs_two_valid_years(observations):
    assert build_measurement({"observations": observations}, CONFIG)[
        "forest_area_change_pct"
    ] is None


def test_latest_biomass_is_selected_from_a_valid_observation():
    result = build_measurement(
        {"observations": [
            observation(2020, 1000, agb=120, source_year=2018),
            observation(2021, 950, agb=None),
            observation(2022, 900, agb=999, valid=False),
        ]},
        CONFIG,
    )
    assert result["forest_area_ha_latest"] == 950
    assert result["agb_t_ha"] == 120
    assert result["agb_source_year"] == 2018
    assert result["co2_stock_total_t"] == pytest.approx(120 * 0.47 * 44 / 12 * 950)


def test_area_change_is_null_when_last_valid_year_has_no_area():
    result = build_measurement(
        {"observations": [
            observation(2020, 1000),
            observation(2021, 950),
            observation(2022, None),
        ]},
        CONFIG,
    )
    assert result["forest_area_ha_latest"] == 950
    assert result["forest_area_change_pct"] is None


def test_event_exposure_and_exact_contract_keys():
    geo = {
        "observations": [observation(2022, 900)],
        "disturbances": [
            {
                "event_id": "proj-01-2022-01",
                "year": 2022,
                "area_ha": 18.4,
                "event_type": "fire_supported",
                "confidence": "high",
                "fire_evidence": True,
                "sources": ["example"],
            },
            {
                "event_id": "proj-01-2022-02",
                "year": 2022,
                "event_type": "unknown",
                "confidence": "low",
            },
        ],
    }
    measurement = build_measurement(geo, CONFIG)
    events = build_disturbance_events(geo, measurement["co2_stock_equivalent_t_ha"])
    assert all(set(event) == EVENT_KEYS for event in events)
    assert events[0]["physical_carbon_exposure_co2_t"] == pytest.approx(
        100 * 0.47 * 44 / 12 * 18.4
    )
    assert events[1]["physical_carbon_exposure_co2_t"] is None
    forbidden = {"credits", "units_to_issue", "reserve_pct", "buffer_pct"}
    assert forbidden.isdisjoint(measurement)
    assert all(forbidden.isdisjoint(row) for row in measurement["series"])
    assert all(forbidden.isdisjoint(event) for event in events)


def test_missing_biomass_also_makes_event_exposure_null():
    geo = {
        "observations": [observation(2022, 900, agb=None)],
        "disturbances": [{"event_id": "e1", "area_ha": 10}],
    }
    measurement = build_measurement(geo, CONFIG)
    assert build_disturbance_events(
        geo, measurement["co2_stock_equivalent_t_ha"]
    )[0]["physical_carbon_exposure_co2_t"] is None
