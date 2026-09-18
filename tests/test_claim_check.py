import pytest

from forestproof_core.claim_check import (
    ClaimCheckConfig,
    build_claim_check,
    calculate_discrepancy_pct,
    select_reference_observation,
)


CONFIG = ClaimCheckConfig()
CLAIM_CHECK_KEYS = {
    "status",
    "reference_date",
    "observation_year_used",
    "rows",
    "events_after_reference_date",
    "likely_cause",
}
ROW_KEYS = {
    "metric",
    "reported",
    "observed",
    "observed_uncertainty",
    "discrepancy_pct",
    "comparable",
}
STATUSES = {
    "no_material_discrepancy",
    "review_recommended",
    "evidence_insufficient",
    "not_comparable",
}
REASONS = {"avoided_emissions", "area_kind_mismatch", "no_valid_observation"}


def project(**claim_overrides):
    claims = {
        "forest_area_ha": 1000.0,
        "area_kind": "forest_cover",
        "agb_t_ha": 100.0,
        "expected_effect_co2_t_year": 1200.0,
        "effect_kind": "avoided_emissions",
        "monitoring_date": "2023-06-01",
        "source": "registry_xlsx",
    }
    claims.update(claim_overrides)
    return {"mode": "with_project", "claims": claims}


def observation(year, area=1000.0, agb=100.0, sd=20.0, valid=True):
    return {
        "year": year,
        "forest_area_ha": area,
        "agb_t_ha": agb,
        "agb_sd_t_ha": sd,
        "agb_source_year": 2022,
        "valid": valid,
    }


def geo(observations=None, disturbances=None, polygon_area_ha=2000.0):
    return {
        "polygon_area_ha": polygon_area_ha,
        "observations": observations if observations is not None else [observation(2023)],
        "disturbances": disturbances if disturbances is not None else [],
    }


def row(result, metric):
    return next(item for item in result["rows"] if item["metric"] == metric)


def test_nearest_valid_reference_year_prefers_earlier_year_on_tie():
    observations = [
        observation(2022, area=1000),
        observation(2023, area=500, valid=False),
        observation(2024, area=800),
        observation(2026, area=200),
    ]
    result = build_claim_check(project(), geo(observations), CONFIG)
    assert result["reference_date"] == "2023-06-01"
    assert result["observation_year_used"] == 2022
    assert row(result, "forest_area_ha")["observed"] == 1000
    assert select_reference_observation(observations, "2025-06-01")["year"] == 2024


def test_forest_cover_area_uses_selected_observation():
    result = build_claim_check(
        project(forest_area_ha=1000),
        geo([observation(2022, area=900), observation(2026, area=1000)]),
        CONFIG,
    )
    area = row(result, "forest_area_ha")
    assert result["observation_year_used"] == 2022
    assert area["observed"] == 900
    assert area["discrepancy_pct"] == pytest.approx(-10)


def test_project_territory_area_uses_polygon_not_forest_cover():
    result = build_claim_check(
        project(area_kind="project_territory", forest_area_ha=2000),
        geo([observation(2023, area=900)], polygon_area_ha=1900),
        CONFIG,
    )
    area = row(result, "forest_area_ha")
    assert area["observed"] == 1900
    assert area["discrepancy_pct"] == pytest.approx(-5)


def test_biomass_and_uncertainty_come_from_same_reference_observation():
    result = build_claim_check(
        project(),
        geo([
            observation(2023, agb=90, sd=15),
            observation(2026, agb=130, sd=40),
        ]),
        CONFIG,
    )
    biomass = row(result, "agb_t_ha")
    assert biomass["observed"] == 90
    assert biomass["observed_uncertainty"] == 15
    assert biomass["discrepancy_pct"] == pytest.approx(-10)


def test_avoided_emissions_are_always_incomparable():
    result = build_claim_check(project(), geo(), CONFIG)
    effect = row(result, "expected_effect_co2_t_year")
    assert effect == {
        "metric": "expected_effect_co2_t_year",
        "reported": 1200.0,
        "observed": None,
        "observed_uncertainty": None,
        "discrepancy_pct": None,
        "comparable": False,
        "not_comparable_reason": "avoided_emissions",
    }


def test_removals_are_not_fabricated_from_biomass_or_stock():
    result = build_claim_check(project(effect_kind="removals"), geo(), CONFIG)
    effect = row(result, "expected_effect_co2_t_year")
    assert effect["reported"] == 1200.0
    assert effect["observed"] is None
    assert effect["observed_uncertainty"] is None
    assert effect["discrepancy_pct"] is None
    assert effect["comparable"] is False
    assert "not_comparable_reason" not in effect


def test_later_events_are_separate_and_do_not_change_status():
    disturbances = [
        {"event_id": "past", "year": 2022, "area_ha": 4, "event_type": "unknown"},
        {
            "event_id": "after",
            "year": 2023,
            "area_ha": 5,
            "event_type": "fire_supported",
            "detected_between": ["2023-07-01", "2023-08-01"],
        },
        {
            "event_id": "overlap",
            "year": 2023,
            "area_ha": 6,
            "event_type": "unknown",
            "detected_between": ["2023-05-01", "2023-07-01"],
        },
        {"event_id": "future", "year": 2024, "area_ha": 7, "event_type": "non_fire"},
    ]
    result = build_claim_check(project(), geo(disturbances=disturbances), CONFIG)
    assert result["status"] == "no_material_discrepancy"
    assert result["events_after_reference_date"] == [
        {"event_id": "after", "year": 2023, "area_ha": 5, "event_type": "fire_supported"},
        {"event_id": "future", "year": 2024, "area_ha": 7, "event_type": "non_fire"},
    ]
    assert all(item["metric"] != "event" for item in result["rows"])


def test_discrepancy_threshold_and_sign():
    within = build_claim_check(
        project(), geo([observation(2023, area=1100, agb=90)]), CONFIG
    )
    assert within["status"] == "no_material_discrepancy"
    assert row(within, "agb_t_ha")["discrepancy_pct"] == pytest.approx(-10)

    outside = build_claim_check(
        project(), geo([observation(2023, area=1101, agb=100)]), CONFIG
    )
    assert outside["status"] == "review_recommended"
    assert calculate_discrepancy_pct(100, 90) == -10
    assert calculate_discrepancy_pct(100, 110) == 10


def test_threshold_is_configurable():
    result = build_claim_check(
        project(),
        geo([observation(2023, area=1101)]),
        ClaimCheckConfig(claim_discrepancy_threshold_pct=15),
    )
    assert result["status"] == "no_material_discrepancy"


def test_no_valid_observation_gives_evidence_insufficient():
    result = build_claim_check(
        project(), geo([observation(2023, valid=False)]), CONFIG
    )
    assert result["status"] == "evidence_insufficient"
    assert result["observation_year_used"] is None
    for metric in ("forest_area_ha", "agb_t_ha"):
        assert row(result, metric)["not_comparable_reason"] == "no_valid_observation"


def test_all_incomparable_rows_give_not_comparable():
    result = build_claim_check(
        project(forest_area_ha=0, agb_t_ha=0), geo(), CONFIG
    )
    assert result["status"] == "not_comparable"
    assert all(item["comparable"] is False for item in result["rows"])


def test_territory_only_omits_claim_check_key_at_assembly():
    calculation = {"measurement": {}}
    block = build_claim_check({"mode": "territory_only", "claims": None}, geo(), CONFIG)
    if block is not None:
        calculation["claim_check"] = block
    assert "claim_check" not in calculation


def test_reported_zero_has_null_discrepancy_without_new_reason():
    result = build_claim_check(project(forest_area_ha=0), geo(), CONFIG)
    area = row(result, "forest_area_ha")
    assert area["observed"] == 1000
    assert area["discrepancy_pct"] is None
    assert area["comparable"] is False
    assert "not_comparable_reason" not in area
    assert calculate_discrepancy_pct(0, 0) is None


def test_missing_metric_does_not_use_a_different_year():
    result = build_claim_check(
        project(),
        geo([observation(2023, agb=None), observation(2024, agb=120)]),
        CONFIG,
    )
    biomass = row(result, "agb_t_ha")
    assert result["observation_year_used"] == 2023
    assert biomass["observed"] is None
    assert biomass["observed_uncertainty"] is None
    assert biomass["comparable"] is False


def test_output_keys_enums_and_neutral_likely_cause():
    result = build_claim_check(
        project(),
        geo([observation(2023, area=900, agb=110)], [
            {"event_id": "future", "year": 2024, "area_ha": 2, "event_type": "unknown"}
        ]),
        CONFIG,
    )
    assert set(result) == CLAIM_CHECK_KEYS
    assert result["status"] in STATUSES
    assert result["likely_cause"] == (
        "Наблюдаемая площадь отличается от заявленной. "
        "Наблюдаемая биомасса отличается от заявленной. "
        "После даты отчётности выявлено событие."
    )
    for item in result["rows"]:
        assert ROW_KEYS <= set(item) <= ROW_KEYS | {"not_comparable_reason"}
        if "not_comparable_reason" in item:
            assert item["not_comparable_reason"] in REASONS
    assert set(result["events_after_reference_date"][0]) == {
        "event_id", "year", "area_ha", "event_type"
    }
    serialized = str(result).lower()
    assert all(phrase not in serialized for phrase in (
        "проект врёт", "гринвошинг", "компания скрыла"
    ))
