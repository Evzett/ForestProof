"""C1 carbon screening over the R4 geo-data contract (docs/04, sections 1 and 6).

The result describes physical CO2 stock equivalent, not emissions or credits.
One selected biomass observation is used for the whole area series; the output
keeps its agb_source_year so the series is not presented as annual biomass data.
"""

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class CarbonScreeningConfig:
    carbon_fraction: float = 0.47
    co2_to_carbon_ratio: float = 44 / 12


def calculate_co2_stock_per_ha(
    agb_t_ha: float | None, config: CarbonScreeningConfig
) -> float | None:
    if agb_t_ha is None:
        return None
    return agb_t_ha * config.carbon_fraction * config.co2_to_carbon_ratio


def calculate_total_co2_stock(
    co2_stock_equivalent_t_ha: float | None, forest_area_ha: float | None
) -> float | None:
    if co2_stock_equivalent_t_ha is None or forest_area_ha is None:
        return None
    return co2_stock_equivalent_t_ha * forest_area_ha


def _valid_observations(
    observations: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return sorted(
        (row for row in observations if row.get("valid") is True),
        key=lambda row: row["year"],
    )


def calculate_forest_area_change(
    observations: Sequence[Mapping[str, Any]],
) -> float | None:
    valid = _valid_observations(observations)
    if len(valid) < 2 or valid[0]["year"] == valid[-1]["year"]:
        return None
    first_area = valid[0].get("forest_area_ha")
    last_area = valid[-1].get("forest_area_ha")
    if first_area is None or last_area is None or first_area == 0:
        return None
    return (last_area - first_area) / first_area * 100


def build_measurement_series(
    observations: Sequence[Mapping[str, Any]],
    co2_stock_equivalent_t_ha: float | None,
) -> list[dict[str, Any]]:
    """Retain every R4 year; unavailable and invalid areas stay null."""
    series = []
    for row in sorted(observations, key=lambda item: item["year"]):
        area = row.get("forest_area_ha") if row.get("valid") is True else None
        series.append(
            {
                "year": row["year"],
                "forest_area_ha": area,
                "co2_stock_total_t": calculate_total_co2_stock(
                    co2_stock_equivalent_t_ha, area
                ),
            }
        )
    return series


def build_measurement(
    geo_data: Mapping[str, Any], config: CarbonScreeningConfig
) -> dict[str, Any]:
    """Return exactly the measurement block of the R3 -> R2 contract."""
    observations = geo_data.get("observations") or []
    valid = _valid_observations(observations)
    area_row = next(
        (row for row in reversed(valid) if row.get("forest_area_ha") is not None),
        None,
    )
    biomass_row = next(
        (row for row in reversed(valid) if row.get("agb_t_ha") is not None),
        None,
    )
    latest_area = area_row["forest_area_ha"] if area_row is not None else None
    agb = biomass_row["agb_t_ha"] if biomass_row is not None else None
    stock_per_ha = calculate_co2_stock_per_ha(agb, config)

    return {
        "forest_area_ha_latest": latest_area,
        "forest_area_change_pct": calculate_forest_area_change(observations),
        "agb_t_ha": agb,
        "agb_sd_t_ha": (
            biomass_row.get("agb_sd_t_ha") if biomass_row is not None else None
        ),
        "agb_source_year": (
            biomass_row.get("agb_source_year") if biomass_row is not None else None
        ),
        "co2_stock_equivalent_t_ha": stock_per_ha,
        "co2_stock_total_t": calculate_total_co2_stock(stock_per_ha, latest_area),
        "series": build_measurement_series(observations, stock_per_ha),
    }


def calculate_event_carbon_exposure(
    event_area_ha: float | None, co2_stock_equivalent_t_ha: float | None
) -> float | None:
    """Physical stock inside the event area; no emitted amount is inferred."""
    return calculate_total_co2_stock(co2_stock_equivalent_t_ha, event_area_ha)


def build_disturbance_events(
    geo_data: Mapping[str, Any], co2_stock_equivalent_t_ha: float | None
) -> list[dict[str, Any]]:
    """Project R4 events onto the events shape in the R3 -> R2 contract."""
    return [
        {
            "event_id": event.get("event_id"),
            "year": event.get("year"),
            "area_ha": event.get("area_ha"),
            "event_type": event.get("event_type"),
            "confidence": event.get("confidence"),
            "physical_carbon_exposure_co2_t": calculate_event_carbon_exposure(
                event.get("area_ha"), co2_stock_equivalent_t_ha
            ),
        }
        for event in (geo_data.get("disturbances") or [])
    ]
