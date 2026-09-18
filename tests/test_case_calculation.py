import json
import csv
import math
from pathlib import Path

import numpy as np
import pytest

from forestproof_core.case_calculation import (
    CaseCalculationConfig,
    baseline_mean,
    baseline_rate,
    baseline_stock_by_year,
    calculate_period,
    calculate_year,
    pixel_intersection_weights,
    potential_units,
    sigma_from_sums,
    uncertainty_half_width,
)
from tools.geotiff import Raster
from tools import extract_case_data


CONFIG = CaseCalculationConfig()
CASE_DATA = Path(__file__).resolve().parents[1] / "app/src/data/case-data.json"
REAL_DATA = Path(__file__).resolve().parents[1] / "data"


def test_geometric_pixel_area_and_partial_overlap():
    grid = Raster(
        data=np.zeros((2, 1, 2)),
        lon_origin=30.0,
        lat_origin=56.0,
        lon_step=0.00088889,
        lat_step=0.00088889,
        nodata=None,
        metadata="",
    )
    pixel_area = grid.pixel_area_ha()[0, 0]
    assert 0.5 < pixel_area < 0.6
    box = (30.0, 56.0 - grid.lat_step, 30.0 + 1.5 * grid.lon_step, 56.0)
    weights = pixel_intersection_weights(grid, box)
    assert weights[0, 0] == pytest.approx(pixel_area)
    assert weights[0, 1] == pytest.approx(pixel_area / 2)
    assert weights.sum() == pytest.approx(1.5 * pixel_area)
    triangle = {"type": "Polygon", "coordinates": [[[30.0, 56.0], [30.0 + grid.lon_step, 56.0], [30.0, 56.0 - grid.lat_step], [30.0, 56.0]]]}
    polygon_weights = pixel_intersection_weights(grid, triangle)
    assert polygon_weights[0, 0] == pytest.approx(pixel_area / 2)
    assert polygon_weights[0, 1] == 0


def test_area_weighted_stock_and_spatial_uncertainty():
    weights = np.array([[0.25, 0.75]])
    result = calculate_year(
        2019,
        np.array([[100.0, 200.0]]),
        np.array([[10.0, 20.0]]),
        weights,
        CONFIG,
    )
    assert result["area_ha"] == 1.0
    assert result["valid_area_ha"] == 1.0
    assert result["agb_t_ha"] == pytest.approx(175.0)
    assert result["stock_tc"] == pytest.approx((0.25 * 100 + 0.75 * 200) * 0.47)
    assert result["c_t_ha"] == pytest.approx(175 * 0.47)
    sd_sum = 0.25 * 10 + 0.75 * 20
    sd_sq_sum = (0.25 * 10) ** 2 + (0.75 * 20) ** 2
    variance = (1 - 0.5) * sd_sq_sum + 0.5 * sd_sum**2
    assert result["sigma_stock_tc"] == pytest.approx(0.47 * math.sqrt(variance))
    assert sigma_from_sums(sd_sum, sd_sq_sum, CONFIG) == pytest.approx(
        result["sigma_stock_tc"]
    )


def test_manual_100_ha_example_yields_e_and_395_units():
    weights = np.array([[50.0, 50.0]])
    sd = np.array([[1.54, 1.54]])
    start = calculate_year(2023, np.array([[100.0, 100.0]]), sd, weights, CONFIG)
    end = calculate_year(2024, np.array([[104.0, 104.0]]), sd, weights, CONFIG)
    result = calculate_period(start, end, 47.0, 47.0, CONFIG)
    assert start["stock_tc"] == pytest.approx(100 * 100 * 0.47)
    assert end["stock_tc"] == pytest.approx(100 * 104 * 0.47)
    assert result["delta_stock_tc"] == pytest.approx(188.0)
    assert result["e_tco2e"] == pytest.approx(-689.3333333333333)
    assert result["e_base_tco2e"] == 0
    assert result["units"] == 395


def test_baseline_rate_projection_clamp_and_effect():
    assert baseline_rate(10.0, 14.0, CONFIG) == 1.0
    assert baseline_mean(2024, 10.0, 14.0, CONFIG) == 19.0
    assert baseline_mean(2024, 5.0, 1.0, CONFIG) == 0.0
    start = {"year": 2019, "area_ha": 100.0, "stock_tc": 100.0, "sigma_stock_tc": 0}
    end = {"year": 2024, "area_ha": 100.0, "stock_tc": 100.0, "sigma_stock_tc": 0}
    result = calculate_period(start, end, 1.0, 0.0, CONFIG)
    assert result["e_base_tco2e"] == pytest.approx(100 * 44 / 12)


def test_temporal_uncertainty_and_scenario_interval():
    sigma_e, half_width = uncertainty_half_width(10.0, 20.0, CONFIG)
    expected_delta_sigma = math.sqrt(10**2 + 20**2 - 2 * 0.7 * 10 * 20)
    assert sigma_e == pytest.approx(expected_delta_sigma * 44 / 12)
    assert half_width == pytest.approx(1.645 * sigma_e)


def test_methodology_assumptions_are_configurable():
    custom = CaseCalculationConfig(
        carbon_fraction=0.5,
        rho_spatial=0.0,
        rho_temporal=0.0,
        k_sigma=2.0,
        unc_threshold=0.2,
        buffer_share=0.25,
        leakage_tco2e=5.0,
    )
    assert sigma_from_sums(10.0, 100.0, custom) == 5.0
    sigma_e, half_width = uncertainty_half_width(3.0, 4.0, custom)
    assert sigma_e == pytest.approx(5 * 44 / 12)
    assert half_width == pytest.approx(2 * sigma_e)
    result = potential_units(0.0, 105.0, 0.0, custom)
    assert result["r_tco2e"] == 100.0
    assert result["units"] == 75


def test_missing_covered_agb_does_not_become_zero_stock_or_units():
    weights = np.array([[1.0, 1.0]])
    sd = np.array([[1.0, 1.0]])
    start = calculate_year(2019, np.array([[100.0, np.nan]]), sd, weights, CONFIG)
    end = calculate_year(2020, np.array([[104.0, 104.0]]), sd, weights, CONFIG)
    assert start["valid_area_ha"] == 1.0
    assert start["missing_area_ha"] == 1.0
    assert start["stock_tc"] is None
    result = calculate_period(start, end, 47.0, 47.0, CONFIG)
    assert result["e_tco2e"] is None
    assert result["r_tco2e"] is None
    assert result["units"] is None
    assert result["available"] is False
    assert result["status"] == "unavailable"


def test_extractor_treats_raster_nodata_as_missing(monkeypatch):
    raster = Raster(
        data=np.array([[[100.0, -9999.0]], [[1.0, 1.0]]]),
        lon_origin=30.0,
        lat_origin=56.0,
        lon_step=0.00088889,
        lat_step=0.00088889,
        nodata=-9999.0,
        metadata="",
    )
    monkeypatch.setattr(extract_case_data, "read_geotiff", lambda _path: raster)
    box = (30.0, 56.0 - raster.lat_step, 30.0 + 2 * raster.lon_step, 56.0)
    result = extract_case_data.read_year(Path("unused"), "AOI", 2019, box)
    assert result["stock_tc"] is None
    assert result["valid_area_ha"] < result["area_ha"]


def test_missing_sd_keeps_stock_but_makes_units_unavailable():
    weights = np.array([[1.0, 1.0]])
    start = calculate_year(
        2019, np.array([[100.0, 100.0]]), np.array([[1.0, np.nan]]), weights, CONFIG
    )
    end = calculate_year(
        2020, np.array([[104.0, 104.0]]), np.array([[1.0, 1.0]]), weights, CONFIG
    )
    assert start["stock_tc"] == pytest.approx(94.0)
    assert start["sigma_stock_tc"] is None
    result = calculate_period(start, end, 47.0, 47.0, CONFIG)
    assert result["e_tco2e"] is not None
    assert result["h_tco2e"] is None
    assert result["units"] is None


def test_missing_baseline_makes_units_unavailable():
    start = {"year": 2019, "area_ha": 100.0, "stock_tc": 100.0, "sigma_stock_tc": 1.0}
    end = {"year": 2020, "area_ha": 100.0, "stock_tc": 104.0, "sigma_stock_tc": 1.0}
    result = calculate_period(start, end, None, None, CONFIG)
    assert result["e_tco2e"] is not None
    assert result["e_base_tco2e"] is None
    assert result["r_tco2e"] is None
    assert result["units"] is None


def test_nonpositive_r_skips_h_over_r():
    zero = potential_units(0.0, 0.0, 10.0, CONFIG)
    negative = potential_units(10.0, 0.0, 10.0, CONFIG)
    for result in (zero, negative):
        assert result["units"] == 0
        assert result["available"] is True
        assert result["h_over_r"] is None
        assert result["unc_share"] is None
    assert negative["r_tco2e"] < 0


def test_h_over_r_at_least_one_gives_zero_units():
    result = potential_units(0.0, 100.0, 100.0, CONFIG)
    assert result["h_over_r"] == 1.0
    assert result["units"] == 0
    assert result["r_adjusted_tco2e"] is None


def test_fractional_units_are_floored_once():
    result = potential_units(0.0, 10.99, 0.0, CONFIG)
    assert result["unc_share"] == 0
    assert result["r_adjusted_tco2e"] == 10.99
    assert result["units"] == math.floor(10.99 * 0.85) == 9


def test_invalid_area_period_and_nonfinite_values():
    with pytest.raises(ValueError, match="positive"):
        calculate_year(2019, np.array([[100.0]]), np.array([[1.0]]), np.zeros((1, 1)), CONFIG)
    start = {"year": 2019, "area_ha": 100.0, "stock_tc": 100.0, "sigma_stock_tc": 1.0}
    with pytest.raises(ValueError, match="period"):
        calculate_period(start, start, 47.0, 47.0, CONFIG)
    with pytest.raises(ValueError, match="period"):
        calculate_period(start, {**start, "year": math.inf}, 47.0, 47.0, CONFIG)
    with pytest.raises(ValueError, match="area"):
        calculate_period(start, {**start, "year": 2020, "area_ha": math.inf}, 47, 47, CONFIG)
    assert potential_units(math.nan, 100.0, 1.0, CONFIG)["units"] is None
    assert baseline_rate(math.inf, 47.0, CONFIG) is None


def test_saved_four_aoi_results_remain_consistent_with_pure_core():
    payload = json.loads(CASE_DATA.read_text(encoding="utf-8"))
    for area in payload["areas"]:
        prior = area["period_2019_2024"]
        by_year = {row["year"]: row for row in area["series"]}
        result = calculate_period(by_year[2019], by_year[2024], area["baseline_stock_t_ha"]["2019"], area["baseline_stock_t_ha"]["2024"], CONFIG)
        assert result["e_tco2e"] == pytest.approx(prior["e_tco2e"], abs=1e-6)
        # The serialized baseline values are rounded; the largest four AOI
        # reconstruction difference is about 1.4e-5 t CO2e.
        assert result["e_base_tco2e"] == pytest.approx(prior["e_base_tco2e"], abs=2e-5)
        assert result["h_tco2e"] == pytest.approx(prior["h_tco2e"], abs=1e-5)
        assert result["units"] == prior["units"] == 0


def test_extractor_assembles_from_supplied_baseline_without_raster_io(monkeypatch):
    area = json.loads(CASE_DATA.read_text(encoding="utf-8"))["areas"][0]
    by_year = {row["year"]: row for row in area["series"]}
    monkeypatch.setattr(extract_case_data, "read_year", lambda _dir, _aoi, year, _box, _config: by_year[year])
    monkeypatch.setattr(extract_case_data, "gfc_loss_by_year", lambda _dir, _aoi, _box: [])
    west, south, east, north = area["bbox"]
    meta = {
        "aoi_id": area["aoi_id"],
        "bbox_west": west,
        "bbox_south": south,
        "bbox_east": east,
        "bbox_north": north,
        "name": area["name"],
        "region": area["region"],
        "selection_role": area["role"],
        "project_status": area["status"],
        "area_ha": area["area_ha_declared"],
        "baseline_id": area["baseline_id"],
    }
    baseline = [{"aoi_id": area["aoi_id"], "baseline_id": area["baseline_id"], "pool": "AGB",
                 "year_start": str(year), "year_end": str(year + 1),
                 "historical_rate_tc_ha_yr": str(area["baseline_rate_tc_ha_year"]),
                 "baseline_stock_start_tc_ha": str(area["baseline_stock_t_ha"][str(year)]),
                 "baseline_stock_end_tc_ha": str(area["baseline_stock_t_ha"][str(year + 1)])}
                for year in range(2019, 2029)]
    result = extract_case_data.build_aoi(Path("unused"), meta, baseline, [], None)
    assert result["period_2019_2024"]["e_tco2e"] == pytest.approx(
        area["period_2019_2024"]["e_tco2e"]
    )
    assert result["period_2019_2024"]["units"] == 0
    economics = result["period_2019_2024"]["scenario_economics"]
    assert economics["q"] == 0
    assert [row["value_rub"] for row in economics["scenarios"]] == [0, 0, 0]
    assert "потенциальные единицы не сформированы" in result["summary"]["text"]
    assert result["baseline_stock_t_ha"]["2029"] == pytest.approx(
        area["baseline_stock_t_ha"]["2029"], abs=1e-8
    )

    missing_end = {**by_year[2024], "c_t_ha": None, "stock_tc": None}
    missing_by_year = {**by_year, 2024: missing_end}
    monkeypatch.setattr(
        extract_case_data,
        "read_year",
        lambda _dir, _aoi, year, _box, _config: missing_by_year[year],
    )
    incomplete = extract_case_data.build_aoi(Path("unused"), meta, baseline, [], None)
    assert incomplete["period_2019_2024"]["units"] is None
    assert incomplete["period_2019_2024"]["scenario_economics"]["available"] is False
    assert incomplete["period_2019_2024"]["value_rub"] == {
        "low": None, "base": None, "high": None
    }
    assert "summary" not in incomplete

    no_baseline = extract_case_data.build_aoi(Path("unused"), meta, [], [], None)
    assert no_baseline["baseline_rate_tc_ha_year"] is None
    assert no_baseline["period_2019_2024"]["units"] is None


@pytest.mark.skipif(
    not (REAL_DATA / "RU_TVER_01/CCI_Biomass_2019.tif").exists(),
    reason="local case rasters are not distributed with Git",
)
def test_real_case_methodology_and_rasters():
    with (REAL_DATA / "methodology/parameters.csv").open(encoding="utf-8-sig") as handle:
        config = CaseCalculationConfig.from_parameter_rows(list(csv.DictReader(handle)))
    with (REAL_DATA / "methodology/baseline.csv").open(encoding="utf-8-sig") as handle:
        baseline = list(csv.DictReader(handle))
    with (REAL_DATA / "areas.geojson").open(encoding="utf-8-sig") as handle:
        features = json.load(handle)["features"]
    assert config.co2_per_carbon == pytest.approx(44 / 12)
    assert config.unc_stop_ratio == 1.0
    for feature in features:
        props = feature["properties"]
        aoi = props["aoi_id"]
        stocks = baseline_stock_by_year(baseline, aoi, props["baseline_id"])
        assert sorted(stocks) == list(range(2019, 2030))
        start = extract_case_data.read_year(REAL_DATA, aoi, 2019, feature["geometry"], config)
        end = extract_case_data.read_year(REAL_DATA, aoi, 2024, feature["geometry"], config)
        assert start["area_ha"] == pytest.approx(float(props["area_ha"]), rel=2e-5)
        assert start["area_ha"] == pytest.approx(end["area_ha"], rel=1e-9)
        assert start["c_t_ha"] == pytest.approx(stocks[2019], abs=1e-5)
        assert start["agb_sd_t_ha"] > 0
        assert start["sigma_stock_tc"] > 0
        result = calculate_period(start, end, stocks[2019], stocks[2024], config)
        expected_base = -start["area_ha"] * (stocks[2024] - stocks[2019]) * config.co2_per_carbon
        assert result["e_base_tco2e"] == pytest.approx(expected_base)
        assert result["h_tco2e"] >= 0
        assert result["available"] is True


def test_baseline_rejects_missing_or_conflicting_periods():
    rows = [{"aoi_id": "A", "baseline_id": "B", "pool": "AGB", "year_start": "2019", "year_end": "2020",
             "baseline_stock_start_tc_ha": "10", "baseline_stock_end_tc_ha": "11"},
            {"aoi_id": "A", "baseline_id": "B", "pool": "AGB", "year_start": "2021", "year_end": "2022",
             "baseline_stock_start_tc_ha": "12", "baseline_stock_end_tc_ha": "13"}]
    with pytest.raises(ValueError, match="missing"):
        baseline_stock_by_year(rows, "A", "B")
    rows[1]["year_start"] = "2020"
    rows[1]["year_end"] = "2021"
    rows[1]["baseline_stock_start_tc_ha"] = "12"
    with pytest.raises(ValueError, match="conflict"):
        baseline_stock_by_year(rows, "A", "B")
