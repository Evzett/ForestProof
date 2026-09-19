from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.app.geometry import run_geometry_checks
from api.app.schemas import CalcRequest


SMALL = {
    "type": "Polygon",
    "coordinates": [[[32.93, 56.60], [32.94, 56.60], [32.94, 56.61], [32.93, 56.61], [32.93, 56.60]]],
}


def test_calc_request_requires_exactly_one_geometry_source() -> None:
    with pytest.raises(ValidationError):
        CalcRequest(year_start=2019, year_end=2024)
    with pytest.raises(ValidationError):
        CalcRequest(geometry=SMALL, aoi_id="RU_TVER_01", year_start=2019, year_end=2024)


def test_calc_request_rejects_reversed_period() -> None:
    with pytest.raises(ValidationError):
        CalcRequest(aoi_id="RU_TVER_01", year_start=2024, year_end=2019)


def test_geometry_validation_has_no_invented_coverage_year() -> None:
    checks, accepted, area_ha = run_geometry_checks(SMALL)
    assert accepted
    assert area_ha > 0
    assert all(check["name"] != "satellite_coverage" for check in checks)


def test_geometry_validation_rejects_too_large_area() -> None:
    large = {
        "type": "Polygon",
        "coordinates": [[[32.0, 56.0], [33.0, 56.0], [33.0, 57.0], [32.0, 57.0], [32.0, 56.0]]],
    }
    checks, accepted, area_ha = run_geometry_checks(large)
    assert not accepted
    assert area_ha > 2_000
    assert next(check for check in checks if check["name"] == "area_ha")["ok"] is False


def test_geometry_validation_rejects_self_intersection() -> None:
    bow_tie = {
        "type": "Polygon",
        "coordinates": [[[32.0, 56.0], [33.0, 57.0], [33.0, 56.0], [32.0, 57.0], [32.0, 56.0]]],
    }
    checks, accepted, _ = run_geometry_checks(bow_tie)
    assert not accepted
    assert next(check for check in checks if check["name"] == "self_intersections")["ok"] is False
