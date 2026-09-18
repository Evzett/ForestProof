"""C2 comparison of project claims with independent R4 observations.

Annual observed removals are not present in the current R4 input contract.
The removals row is therefore shown as incomparable until that input is defined.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class ClaimCheckConfig:
    claim_discrepancy_threshold_pct: float = 10.0


def select_reference_observation(
    observations: Sequence[Mapping[str, Any]], monitoring_date: str | None
) -> Mapping[str, Any] | None:
    """Choose the nearest valid year; prefer the earlier year on a tie."""
    if monitoring_date is None:
        return None
    reference_year = date.fromisoformat(monitoring_date).year
    valid = (row for row in observations if row.get("valid") is True)
    return min(
        valid,
        key=lambda row: (abs(row["year"] - reference_year), row["year"]),
        default=None,
    )


def calculate_discrepancy_pct(
    reported: float | None, observed: float | None
) -> float | None:
    if reported is None or observed is None or reported == 0:
        return None
    return (observed - reported) / reported * 100


def _numeric_row(
    metric: str,
    reported: float | None,
    observed: float | None,
    observed_uncertainty: float | None,
    reason: str | None = None,
) -> dict[str, Any]:
    discrepancy = calculate_discrepancy_pct(reported, observed)
    comparable = discrepancy is not None and reason is None
    row = {
        "metric": metric,
        "reported": reported,
        "observed": observed,
        "observed_uncertainty": observed_uncertainty,
        "discrepancy_pct": discrepancy if comparable else None,
        "comparable": comparable,
    }
    if not comparable and reason is not None:
        row["not_comparable_reason"] = reason
    return row


def build_area_claim_row(
    claims: Mapping[str, Any],
    geo_data: Mapping[str, Any],
    observation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    area_kind = claims.get("area_kind")
    if area_kind == "forest_cover":
        observed = (
            observation.get("forest_area_ha") if observation is not None else None
        )
        reason = "no_valid_observation" if observation is None else None
    elif area_kind == "project_territory":
        observed = geo_data.get("polygon_area_ha")
        reason = None
    else:
        observed = None
        reason = "area_kind_mismatch"
    return _numeric_row(
        "forest_area_ha", claims.get("forest_area_ha"), observed, None, reason
    )


def build_agb_claim_row(
    claims: Mapping[str, Any], observation: Mapping[str, Any] | None
) -> dict[str, Any]:
    observed = observation.get("agb_t_ha") if observation is not None else None
    uncertainty = (
        observation.get("agb_sd_t_ha")
        if observation is not None and observed is not None
        else None
    )
    reason = "no_valid_observation" if observation is None else None
    return _numeric_row("agb_t_ha", claims.get("agb_t_ha"), observed, uncertainty, reason)


def build_effect_claim_row(claims: Mapping[str, Any]) -> dict[str, Any]:
    """Keep the reported effect visible without inventing observed removals."""
    effect_kind = claims.get("effect_kind")
    if effect_kind not in {"avoided_emissions", "removals"}:
        raise ValueError(f"Unsupported effect_kind: {effect_kind!r}")
    row = {
        "metric": "expected_effect_co2_t_year",
        "reported": claims.get("expected_effect_co2_t_year"),
        "observed": None,
        "observed_uncertainty": None,
        "discrepancy_pct": None,
        "comparable": False,
    }
    if effect_kind == "avoided_emissions":
        row["not_comparable_reason"] = "avoided_emissions"
    return row


def collect_events_after_reference_date(
    disturbances: Sequence[Mapping[str, Any]], reference_date: str | None
) -> list[dict[str, Any]]:
    """Include only events known to start strictly after the reference date."""
    if reference_date is None:
        return []
    reference = date.fromisoformat(reference_date)
    result = []
    for event in disturbances:
        year = event.get("year")
        after = year is not None and year > reference.year
        if year == reference.year:
            detected_between = event.get("detected_between")
            after = bool(
                detected_between
                and date.fromisoformat(detected_between[0]) > reference
            )
        if after:
            result.append(
                {
                    "event_id": event.get("event_id"),
                    "year": year,
                    "area_ha": event.get("area_ha"),
                    "event_type": event.get("event_type"),
                }
            )
    return result


def determine_claim_check_status(
    rows: Sequence[Mapping[str, Any]],
    has_reference_observation: bool,
    config: ClaimCheckConfig,
) -> str:
    if not has_reference_observation:
        return "evidence_insufficient"
    comparable = [row for row in rows if row["comparable"]]
    if not comparable:
        return "not_comparable"
    if any(
        abs(row["discrepancy_pct"]) > config.claim_discrepancy_threshold_pct
        for row in comparable
    ):
        return "review_recommended"
    return "no_material_discrepancy"


def build_likely_cause(
    rows: Sequence[Mapping[str, Any]],
    events_after_reference_date: Sequence[Mapping[str, Any]],
) -> str | None:
    """Use only neutral, deterministic statements supported by the output."""
    phrases = []
    for row in rows:
        if not row["comparable"] or row["discrepancy_pct"] == 0:
            continue
        if row["metric"] == "forest_area_ha":
            phrases.append("Наблюдаемая площадь отличается от заявленной.")
        elif row["metric"] == "agb_t_ha":
            phrases.append("Наблюдаемая биомасса отличается от заявленной.")
    if events_after_reference_date:
        phrases.append("После даты отчётности выявлено событие.")
    return " ".join(phrases) or None


def build_claim_check(
    project: Mapping[str, Any],
    geo_data: Mapping[str, Any],
    config: ClaimCheckConfig,
) -> dict[str, Any] | None:
    """Return the claim_check block, or None for territory-only projects.

    The final calculation assembler must omit the key when this returns None.
    """
    mode = project.get("mode")
    if mode == "territory_only":
        return None
    if mode != "with_project":
        raise ValueError(f"Unsupported mode: {mode!r}")

    claims = project.get("claims") or {}
    reference_date = claims.get("monitoring_date")
    observation = select_reference_observation(
        geo_data.get("observations") or [], reference_date
    )
    rows = [
        build_area_claim_row(claims, geo_data, observation),
        build_agb_claim_row(claims, observation),
        build_effect_claim_row(claims),
    ]
    events = collect_events_after_reference_date(
        geo_data.get("disturbances") or [], reference_date
    )
    return {
        "status": determine_claim_check_status(rows, observation is not None, config),
        "reference_date": reference_date,
        "observation_year_used": observation["year"] if observation is not None else None,
        "rows": rows,
        "events_after_reference_date": events,
        "likely_cause": build_likely_cause(rows, events),
    }
