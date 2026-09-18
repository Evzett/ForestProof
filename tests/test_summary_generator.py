"""C5 uses ready G2/H6 values without deriving new indicators."""

import re

from forestproof_core.scenario_economics import (
    PRICE_DISCLAIMER,
    ScenarioEconomicsConfig,
    calculate_scenario_value,
)
from forestproof_core.summary_generator import generate_summary


def ready_result(q=395):
    return {
        "aoi_id": "RU_TVER_01",
        "period_2019_2024": {
            "year_start": 2019,
            "year_end": 2024,
            "units": q,
            "available": q is not None,
            "scenario_economics": calculate_scenario_value(
                q,
                ScenarioEconomicsConfig((("low", 500), ("base", 1500), ("high", 4000))),
            ),
        },
    }


def source_value(result, field):
    value = result
    for part in re.split(r"\.(?![^\[]*\])", field):
        match = re.fullmatch(r"([^\[]+)\[(\d+)\]", part)
        value = value[match.group(1)][int(match.group(2))] if match else value[part]
    return value


def test_ready_result_has_short_summary_and_sources():
    result = ready_result()
    summary = generate_summary(result)
    assert summary is not None
    assert "RU_TVER_01" in summary["text"]
    assert "2019–2024" in summary["text"]
    assert "395 единиц" in summary["text"]
    assert "1500 ₽ составляет 592500 ₽" in summary["text"]
    assert PRICE_DISCLAIMER in summary["text"]
    assert len(summary["source_fields"]) >= 7
    assert summary["text"].count(".") == 3


def test_zero_units_is_neutral_and_still_has_zero_scenario_value():
    text = generate_summary(ready_result(0))["text"]
    assert "потенциальные единицы не сформированы" in text
    assert "1500 ₽ составляет 0 ₽" in text
    assert "плох" not in text and "неэффектив" not in text and "провал" not in text


def test_post_reporting_events_and_incomparable_effect_are_facts_only():
    result = ready_result()
    result["events_after_reference_date"] = {"count": 2, "year": 2025}
    result["effect_comparable"] = False
    summary = generate_summary(result)
    assert "После даты отчётности обнаружено 2 событий за 2025 год" in summary["text"]
    assert "эффект не сопоставляется по условиям методологии" in summary["text"].lower()
    assert "events_after_reference_date.count" in summary["source_fields"]
    assert "events_after_reference_date.year" in summary["source_fields"]
    assert summary["text"].count(".") == 4


def test_unavailable_or_incomplete_inputs_have_no_summary():
    assert generate_summary(ready_result(None)) is None
    result = ready_result()
    del result["period_2019_2024"]["scenario_economics"]
    assert generate_summary(result) is None
    result = ready_result()
    result["events_after_reference_date"] = {"count": 2}
    assert generate_summary(result) is None


def test_every_numeric_literal_is_traceable_to_source_fields():
    result = ready_result()
    result["events_after_reference_date"] = {"count": 2, "year": 2025}
    summary = generate_summary(result)
    sourced_text = " ".join(str(source_value(result, path)) for path in summary["source_fields"])
    for number in re.findall(r"\d+", summary["text"]):
        assert number in re.findall(r"\d+", sourced_text)


def test_forbidden_claims_are_not_generated_or_echoed():
    prohibited = (
        "гринвошинг", "мошенничество", "ложь", "недобросовестность",
        "вероятность пожара", "прогноз риска", "скрыл", "нарушение владельца",
    )
    for q in (0, 395):
        result = ready_result(q)
        result["effect_comparable"] = False
        result["events_after_reference_date"] = {"count": 1, "year": 2025}
        text = generate_summary(result)["text"].lower()
        assert all(word not in text for word in prohibited)
    contaminated = ready_result()
    contaminated["aoi_id"] = "ложь"
    assert generate_summary(contaminated) is None
