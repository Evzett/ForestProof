"""Deterministic short explanation of an already calculated G2/H6 result."""

from __future__ import annotations

import re
from collections.abc import Mapping

from forestproof_core.scenario_economics import PRICE_DISCLAIMER


_AOI_ID = re.compile(r"[A-Za-z0-9_/-]+\Z")


def generate_summary(calculation_result: Mapping[str, object]) -> dict | None:
    """Return an auditable summary, or None when its ready inputs are unavailable.

    This function only selects and formats supplied values. In particular, an
    event count and year must already be present; raw events are not analysed.
    """
    if not isinstance(calculation_result, Mapping):
        return None
    aoi_id = calculation_result.get("aoi_id")
    period = calculation_result.get("period_2019_2024")
    if not isinstance(aoi_id, str) or not _AOI_ID.fullmatch(aoi_id):
        return None
    if not isinstance(period, Mapping):
        return None

    start, end = period.get("year_start"), period.get("year_end")
    q = period.get("units")
    economics = period.get("scenario_economics")
    if (
        type(start) is not int or type(end) is not int or start <= 0 or end < start
        or period.get("available") is not True
        or type(q) is not int or q < 0
        or not isinstance(economics, Mapping)
        or economics.get("available") is not True
        or economics.get("q") != q
        or economics.get("disclaimer") != PRICE_DISCLAIMER
    ):
        return None

    scenarios = economics.get("scenarios")
    if not isinstance(scenarios, list):
        return None
    selected = next(
        ((index, row) for index, row in enumerate(scenarios)
         if isinstance(row, Mapping) and row.get("name") == "base"),
        None,
    )
    if selected is None:
        return None
    index, scenario = selected
    price, value = scenario.get("price_rub"), scenario.get("value_rub")
    if type(price) is not int or price < 0 or type(value) is not int or value < 0:
        return None

    prefix = "period_2019_2024"
    fields = [
        "aoi_id", f"{prefix}.year_start", f"{prefix}.year_end",
        f"{prefix}.units", f"{prefix}.scenario_economics.q",
        f"{prefix}.scenario_economics.scenarios[{index}].price_rub",
        f"{prefix}.scenario_economics.scenarios[{index}].value_rub",
        f"{prefix}.scenario_economics.disclaimer",
    ]
    carbon = (
        f"Расчёт сформировал потенциальный объём {q} единиц по условиям кейса"
        if q > 0 else
        "По условиям расчёта потенциальные единицы не сформированы"
    )
    sentences = [
        f"Участок {aoi_id} рассчитан за период {start}–{end}.",
        f"{carbon}; сценарная стоимость при цене {price} ₽ составляет {value} ₽.",
        f"{PRICE_DISCLAIMER}.",
    ]

    extra = []
    event = calculation_result.get("events_after_reference_date")
    if event is not None:
        if not isinstance(event, Mapping):
            return None
        count, year = event.get("count"), event.get("year")
        if type(count) is not int or count < 0 or type(year) is not int or year <= 0:
            return None
        if count > 0:
            extra.append(f"После даты отчётности обнаружено {count} событий за {year} год")
            fields.extend(["events_after_reference_date.count", "events_after_reference_date.year"])

    comparable = calculation_result.get("effect_comparable")
    if comparable is False:
        extra.append("Эффект не сопоставляется по условиям методологии")
        fields.append("effect_comparable")
    elif comparable is not None and comparable is not True:
        return None
    if extra:
        sentences.append("; ".join(extra) + ".")

    return {"text": " ".join(sentences), "source_fields": fields}
