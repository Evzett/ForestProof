"""Tests for C5 summary integration into UI data and contracts."""

import json
from pathlib import Path

from forestproof_core.scenario_economics import PRICE_DISCLAIMER
from forestproof_core.summary_generator import generate_summary


REPO_ROOT = Path(__file__).resolve().parent.parent
CASE_DATA_PATH = REPO_ROOT / "app" / "src" / "data" / "case-data.json"


def test_case_data_areas_have_c5_summary():
    """Verify that case-data.json loaded by the UI contains C5 summary for each area."""
    assert CASE_DATA_PATH.exists(), f"case-data.json not found at {CASE_DATA_PATH}"
    with open(CASE_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    areas = data.get("areas", [])
    assert len(areas) >= 4, "Expected at least 4 case study areas"

    for area in areas:
        aoi_id = area["aoi_id"]
        assert "summary" in area, f"Area {aoi_id} must have summary field"
        summary = area["summary"]
        assert isinstance(summary, dict), f"Summary for {aoi_id} must be a dict"
        assert "text" in summary, f"Summary for {aoi_id} must have text"
        assert "source_fields" in summary, f"Summary for {aoi_id} must have source_fields"

        assert aoi_id in summary["text"]
        assert "2019–2024" in summary["text"]
        assert PRICE_DISCLAIMER in summary["text"]


def test_source_fields_are_preserved_and_traceable():
    """Verify that source_fields exist in the calculation data structure."""
    with open(CASE_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    for area in data.get("areas", []):
        summary = area["summary"]
        source_fields = summary["source_fields"]
        assert isinstance(source_fields, list)
        assert len(source_fields) >= 7

        expected_fields = [
            "aoi_id",
            "period_2019_2024.year_start",
            "period_2019_2024.year_end",
            "period_2019_2024.units",
            "period_2019_2024.scenario_economics.q",
            "period_2019_2024.scenario_economics.scenarios[1].price_rub",
            "period_2019_2024.scenario_economics.scenarios[1].value_rub",
            "period_2019_2024.scenario_economics.disclaimer",
        ]
        for field in expected_fields:
            assert field in source_fields, f"Missing source_field '{field}' in {area['aoi_id']}"


def test_summary_for_period_filtering_and_hiding():
    """Simulate summaryForPeriod logic from app/src/data/summary.ts:
    Summary is only shown for the period matching period_2019_2024; for other
    periods or when summary is absent, it returns None (block is hidden in UI).
    """
    with open(CASE_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    area = data["areas"][0]

    def summary_for_period(a, p):
        p_2019_2024 = a.get("period_2019_2024", {})
        if (
            p.get("year_start") != p_2019_2024.get("year_start")
            or p.get("year_end") != p_2019_2024.get("year_end")
        ):
            return None
        return a.get("summary")

    # 1. Matching period (2019-2024) -> summary is present
    period_2019_2024 = area["period_2019_2024"]
    res = summary_for_period(area, period_2019_2024)
    assert res is not None
    assert res == area["summary"]

    # 2. Non-matching sub-period (e.g. 2019-2020) -> returns None (block hidden)
    sub_period = {"year_start": 2019, "year_end": 2020}
    res_sub = summary_for_period(area, sub_period)
    assert res_sub is None, "Summary must be hidden (None) for non-matching period"

    # 3. Area without summary -> returns None (block hidden)
    area_no_summary = {**area}
    del area_no_summary["summary"]
    res_none = summary_for_period(area_no_summary, period_2019_2024)
    assert res_none is None, "When area has no summary, result must be None"


def test_generate_summary_reproducibility():
    """Verify that generate_summary re-run on area matches the saved summary."""
    with open(CASE_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    for area in data.get("areas", []):
        recomputed = generate_summary(area)
        assert recomputed is not None
        assert recomputed == area["summary"], f"Summary mismatch for {area['aoi_id']}"
