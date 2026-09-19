"""Application regression; only data I/O is replaced, never baseline/core math.

primer-1-series.json records read_year for the exact example geometry, years
2015..2024, ESA CCI Biomass v7.0 tile N60E040, retrieved 2026-09-19.
These measured inputs let CI exercise the real service without remote rasters.
"""
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
from app import case_service, jobs, models
from tools import extract_case_data as extract


@pytest.fixture
def data_layer(monkeypatch, tmp_path):
    series = json.loads((ROOT / "tests/fixtures/primer-1-series.json").read_text(encoding="utf-8"))
    by_year = {row["year"]: row for row in series}
    reads = []

    def read(_dir, aoi, year, geometry, _config):
        reads.append((aoi, year, geometry))
        return dict(by_year[year])

    monkeypatch.setattr(case_service, "read_year", read)
    monkeypatch.setattr(extract, "read_year", read)
    monkeypatch.setattr(case_service, "_maps_dir", lambda *args: tmp_path)
    monkeypatch.setattr(case_service, "_external_evidence", lambda *args: None)
    for name in ("render_maps", "render_terrain", "_sentinel_block"):
        monkeypatch.setattr(extract, name, lambda *args: None)
    monkeypatch.setattr(extract, "gfc_loss_by_year", lambda *args: [])
    return reads


def primer_geometry():
    return json.loads((ROOT / "examples/primer-1-edinic-29438.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"]


def assert_positive(result):
    period = result["period"]
    assert period["units"] == 29438
    assert period["r_tco2e"] == pytest.approx(52069.8362, abs=0.01)
    assert period["h_over_r"] == pytest.approx(0.434872229)
    assert period["h_over_r"] < 0.5
    assert period["status"] == "calculated"
    assert result["area_ha"] == pytest.approx(513.509786)


def test_positive_fixture_application_path(data_layer):
    assert_positive(case_service.calculate(primer_geometry(), 2019, 2024))


def test_positive_fixture_wizard_job_path(data_layer, monkeypatch):
    job = models.CalcJob(job_id="JOB-regression", geometry=primer_geometry(),
                         year_start=2019, year_end=2024, name="primer-1", created_by="test")
    db = Mock()
    db.get.return_value = job
    monkeypatch.setattr(jobs, "SessionLocal", lambda: db)
    monkeypatch.setattr(jobs, "next_calc_id", lambda _db: "CALC-regression")
    monkeypatch.setattr(jobs, "next_contour_id", lambda _db: "CONTOUR-regression")
    jobs.run(job.job_id)
    assert job.status is models.JobStatus.done
    assert job.contour_id == "CONTOUR-regression"
    assert_positive(job.result)


def test_user_inside_catalog_uses_own_history(data_layer):
    parent = case_service.load_case_set().areas[0]
    west, south = float(parent["bbox_west"]), float(parent["bbox_south"])
    geometry = {"type": "Polygon", "coordinates": [[[west + .001, south + .001],
        [west + .002, south + .001], [west + .002, south + .002],
        [west + .001, south + .002], [west + .001, south + .001]]]}
    assert case_service.covering_area(geometry) == parent
    original_baseline = parent["baseline_id"]
    result = case_service.calculate(geometry, 2019, 2024)
    assert result["baseline_id"] == case_service.DERIVED_BASELINE_ID
    assert result["baseline_stock_t_ha"]["2019"] == pytest.approx(40.001954093)
    assert result["baseline_rate_tc_ha_year"] == pytest.approx(-7.259368634)
    assert all(aoi == parent["aoi_id"] and geom == geometry for aoi, _, geom in data_layer)
    assert {year for _, year, _ in data_layer} >= {2015, 2019}
    assert parent["baseline_id"] == original_baseline
    catalog = case_service.calculate(case_service.load_case_set().geometries[parent["aoi_id"]],
                                     2019, 2024, own_geometry=False)
    assert catalog["baseline_id"] == original_baseline
    assert catalog["baseline_kind"] == "задана условиями кейса"


def test_short_period_still_has_zero_units(data_layer):
    period = case_service.calculate(primer_geometry(), 2019, 2021)["period"]
    assert period["units"] == 0
    assert period["h_over_r"] >= 1


def test_official_published_results_unchanged():
    for aoi in ("RU_TVER_01", "RU_VOLOGDA_02", "RU_MORDOVIA_03", "RU_MORDOVIA_04"):
        result = case_service.published_area_result(aoi, 2019, 2024)
        assert result["result_cache"]["used"] is True
        assert result["period"]["units"] == 0
        saved = case_service.load_published_results()[aoi]
        assert result["baseline_id"] == saved["baseline_id"]
        assert result["period"] == next(p for p in saved["periods"]
                                        if p["year_start"] == 2019 and p["year_end"] == 2024)
