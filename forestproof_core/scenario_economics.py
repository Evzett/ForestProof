"""Scenario value of potential case units calculated by G2."""

from dataclasses import dataclass


PRICE_DISCLAIMER = "Эти значения не являются прогнозом рыночной цены"


@dataclass(frozen=True, slots=True)
class ScenarioEconomicsConfig:
    """Named ruble prices supplied by the case methodology configuration."""

    prices_rub: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not self.prices_rub:
            raise ValueError("at least one price scenario is required")
        names: set[str] = set()
        for name, price in self.prices_rub:
            if not name or name in names or type(price) is not int or price < 0:
                raise ValueError("scenario names must be unique and prices nonnegative integers")
            names.add(name)


def calculate_scenario_value(
    q: int | None, config: ScenarioEconomicsConfig
) -> dict:
    """Apply only V = Q × price; ``None`` means G2 units are unavailable."""
    if q is not None and (type(q) is not int or q < 0):
        raise ValueError("Q must be a nonnegative integer or None")

    return {
        "q": q,
        "available": q is not None,
        "reason": None if q is not None else "расчёт потенциальных единиц недоступен",
        "scenarios": [
            {
                "name": name,
                "price_rub": price,
                "value_rub": None if q is None else q * price,
            }
            for name, price in config.prices_rub
        ],
        "disclaimer": PRICE_DISCLAIMER,
    }
