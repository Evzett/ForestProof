"""Pure calculations for the raster based case in docs/06-kejs-pereorientaciya.md.

Arrays and geometrically derived pixel areas are supplied by the caller. This
module reads no files and does not use the legacy C1/C2 project contracts.
"""

from dataclasses import dataclass
from fractions import Fraction
import math
from typing import Any, Mapping, Protocol

import numpy as np


def _finite_or_none(value: float | None) -> float | None:
    return value if value is not None and math.isfinite(value) else None


@dataclass(frozen=True, slots=True)
class CaseCalculationConfig:
    carbon_fraction: float = 0.47
    co2_per_carbon: float = 44 / 12
    rho_spatial: float = 0.5
    rho_temporal: float = 0.7
    k_sigma: float = 1.645
    unc_threshold: float = 0.10
    unc_stop_ratio: float = 1.0
    buffer_share: float = 0.15
    leakage_tco2e: float = 0.0
    baseline_start_year: int = 2015
    baseline_anchor_year: int = 2019
    baseline_end_year: int = 2029
    rho_spatial_grid: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
    rho_temporal_grid: tuple[float, ...] = (0.0, 0.5, 0.7, 0.9, 0.95, 0.99)
    prices_rub: tuple[tuple[str, int], ...] = (
        ("low", 500), ("base", 1500), ("high", 4000)
    )

    def __post_init__(self) -> None:
        coefficients = (
            self.carbon_fraction,
            self.co2_per_carbon,
            self.rho_spatial,
            self.rho_temporal,
            self.k_sigma,
            self.unc_threshold,
            self.unc_stop_ratio,
            self.buffer_share,
            self.leakage_tco2e,
        )
        if not all(math.isfinite(value) for value in coefficients):
            raise ValueError("Case calculation coefficients must be finite")
        if self.carbon_fraction <= 0 or self.co2_per_carbon <= 0 or self.k_sigma < 0:
            raise ValueError("Conversion factors must be positive and k_sigma nonnegative")
        if not all(
            0 <= value <= 1
            for value in (
                self.rho_spatial,
                self.rho_temporal,
                self.unc_threshold,
                self.buffer_share,
            )
        ):
            raise ValueError("Correlations and shares must be between zero and one")
        if self.unc_stop_ratio <= 0:
            raise ValueError("UNC stop ratio must be positive")
        if self.leakage_tco2e < 0:
            raise ValueError("Leakage must be nonnegative")
        if self.baseline_anchor_year <= self.baseline_start_year:
            raise ValueError("Baseline anchor must follow the historical start")
        if self.baseline_end_year < self.baseline_anchor_year:
            raise ValueError("Baseline end must not precede the anchor")
        if not all(
            math.isfinite(value) and 0 <= value <= 1
            for value in self.rho_spatial_grid + self.rho_temporal_grid
        ):
            raise ValueError("Sensitivity correlations must be between zero and one")
        if not all(math.isfinite(price) and price >= 0 for _, price in self.prices_rub):
            raise ValueError("Scenario prices must be nonnegative")

    @classmethod
    def from_parameter_rows(cls, rows: list[Mapping[str, str]]) -> "CaseCalculationConfig":
        """Parse the case methodology CSV; rho and k remain explicit assumptions."""
        values = {row["parameter"]: row["value"] for row in rows}

        def number(key: str) -> float:
            return float(Fraction(values[key]))

        return cls(
            carbon_fraction=number("CF_AGB"),
            co2_per_carbon=number("CO2_per_C"),
            unc_threshold=number("UNC_allowance"),
            unc_stop_ratio=number("UNC_stop_ratio"),
            buffer_share=number("BUF"),
            leakage_tco2e=number("LK"),
            baseline_start_year=int(number("history_start_year")),
            baseline_anchor_year=int(number("history_end_year")),
            baseline_end_year=int(number("scenario_end_year")),
            prices_rub=tuple((name, int(number("price_" + name))) for name in ("low", "base", "high")),
        )


class PixelGrid(Protocol):
    data: np.ndarray
    lon_origin: float
    lat_origin: float
    lon_step: float
    lat_step: float

    def pixel_area_ha(self) -> np.ndarray: ...


def carbon_density_t_ha(
    agb_t_ha: np.ndarray, config: CaseCalculationConfig
) -> np.ndarray:
    """Aboveground carbon density from dry aboveground biomass."""
    return np.asarray(agb_t_ha, dtype=float) * config.carbon_fraction


def pixel_intersection_weights(
    grid: PixelGrid, bbox: tuple[float, float, float, float] | Mapping[str, Any]
) -> np.ndarray:
    """Hectares of each grid pixel intersecting a WGS84 rectangle or polygon.

    The grid's pixel_area_ha() computes the geometric area by latitude; the
    intersection fraction clips edge pixels. A pixel is never assumed to be
    one hectare.
    """
    geometry = bbox if isinstance(bbox, Mapping) else None
    if geometry is not None:
        if geometry.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError("geometry must be a GeoJSON Polygon or MultiPolygon")
        polygons = (geometry["coordinates"] if geometry["type"] == "MultiPolygon"
                    else [geometry["coordinates"]])
        points = [point for polygon in polygons for ring in polygon for point in ring]
        bbox = (min(p[0] for p in points), min(p[1] for p in points),
                max(p[0] for p in points), max(p[1] for p in points))
    west, south, east, north = bbox
    if not all(math.isfinite(v) for v in bbox) or west >= east or south >= north:
        raise ValueError("bbox must be finite and have positive width and height")
    if not all(
        math.isfinite(value)
        for value in (grid.lon_origin, grid.lat_origin, grid.lon_step, grid.lat_step)
    ) or grid.lon_step <= 0 or grid.lat_step <= 0:
        raise ValueError("grid steps must be positive")
    rows, cols = grid.data.shape[1:]
    lon_left = grid.lon_origin + np.arange(cols) * grid.lon_step
    lon_right = lon_left + grid.lon_step
    lat_top = grid.lat_origin - np.arange(rows) * grid.lat_step
    lat_bottom = lat_top - grid.lat_step
    frac_x = np.clip(np.minimum(lon_right, east) - np.maximum(lon_left, west), 0, None)
    frac_y = np.clip(np.minimum(lat_top, north) - np.maximum(lat_bottom, south), 0, None)
    fraction = np.outer(frac_y / grid.lat_step, frac_x / grid.lon_step)
    pixel_area = np.asarray(grid.pixel_area_ha(), dtype=float)
    if pixel_area.shape != (rows, cols) or not np.all(np.isfinite(pixel_area)):
        raise ValueError("geometric pixel areas must be finite and match the grid")
    if np.any(pixel_area <= 0):
        raise ValueError("geometric pixel areas must be positive")
    if geometry is None:
        return fraction * pixel_area

    # Clip every GeoJSON ring to each touched pixel. The area fraction is
    # dimensionless, then multiplied by the pixel's geometric hectare area.
    result = np.zeros((rows, cols), dtype=float)
    for row, col in np.argwhere(fraction > 0):
        left, right = lon_left[col], lon_right[col]
        bottom, top = lat_bottom[row], lat_top[row]
        fraction_sum = 0.0
        for polygon in polygons:
            for ring_index, ring in enumerate(polygon):
                clipped = [(float(x), float(y)) for x, y in ring]
                for axis, limit, keep_greater in ((0, left, True), (0, right, False),
                                                    (1, bottom, True), (1, top, False)):
                    output = []
                    for previous, current in zip(clipped[-1:] + clipped[:-1], clipped):
                        prev_inside = previous[axis] >= limit if keep_greater else previous[axis] <= limit
                        curr_inside = current[axis] >= limit if keep_greater else current[axis] <= limit
                        if prev_inside != curr_inside:
                            share = (limit - previous[axis]) / (current[axis] - previous[axis])
                            output.append((previous[0] + share * (current[0] - previous[0]),
                                           previous[1] + share * (current[1] - previous[1])))
                        if curr_inside:
                            output.append(current)
                    clipped = output
                    if not clipped:
                        break
                local = [(x - left, y - bottom) for x, y in clipped]
                area = abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2)
                               in zip(local, local[1:] + local[:1]))) / 2 if local else 0.0
                fraction_sum += area if ring_index == 0 else -area
        result[row, col] = pixel_area[row, col] * min(1.0, max(0.0, fraction_sum / (grid.lon_step * grid.lat_step)))
    return result


def baseline_stock_by_year(
    rows: list[Mapping[str, str]], aoi_id: str, baseline_id: str
) -> dict[int, float]:
    """Use official per-period baseline endpoints; reject gaps or conflicts."""
    matched = [r for r in rows if r.get("aoi_id") == aoi_id and r.get("baseline_id") == baseline_id and r.get("pool") == "AGB"]
    stocks: dict[int, float] = {}
    periods: set[tuple[int, int]] = set()
    for row in matched:
        start, end = int(row["year_start"]), int(row["year_end"])
        if end != start + 1 or (start, end) in periods:
            raise ValueError("baseline periods must be unique consecutive years")
        periods.add((start, end))
        for year, key in ((start, "baseline_stock_start_tc_ha"), (end, "baseline_stock_end_tc_ha")):
            value = float(row[key])
            if not math.isfinite(value) or value < 0:
                raise ValueError("baseline stock must be finite and nonnegative")
            if year in stocks and not math.isclose(stocks[year], value, abs_tol=1e-8):
                raise ValueError("baseline endpoints conflict")
            stocks[year] = value
    if periods and len(periods) != max(stocks) - min(stocks):
        raise ValueError("baseline has missing periods")
    return stocks


def sigma_from_sums(
    sd_sum: float | None,
    sd_sq_sum: float | None,
    config: CaseCalculationConfig,
    rho_spatial: float | None = None,
) -> float | None:
    """Spatial AGB uncertainty transferred to total carbon stock (t C)."""
    rho = config.rho_spatial if rho_spatial is None else rho_spatial
    if not math.isfinite(rho) or not 0 <= rho <= 1:
        raise ValueError("rho_spatial must be between zero and one")
    if sd_sum is None or sd_sq_sum is None:
        return None
    if not math.isfinite(sd_sum) or not math.isfinite(sd_sq_sum):
        return None
    if sd_sum < 0 or sd_sq_sum < 0:
        raise ValueError("AGB uncertainty sums must be nonnegative")
    variance = (1 - rho) * sd_sq_sum + rho * sd_sum**2
    if not math.isfinite(variance):
        return None
    return _finite_or_none(config.carbon_fraction * math.sqrt(max(variance, 0.0)))


def calculate_year(
    year: int,
    agb_t_ha: np.ndarray,
    agb_sd_t_ha: np.ndarray,
    weights_ha: np.ndarray,
    config: CaseCalculationConfig,
) -> dict[str, Any]:
    """Area weighted AGB stock and uncertainty for one raster year.

    Missing covered pixels invalidate the affected aggregate. Uncovered pixels
    may contain nodata without changing the result.
    """
    agb = np.asarray(agb_t_ha, dtype=float)
    sd = np.asarray(agb_sd_t_ha, dtype=float)
    weights = np.asarray(weights_ha, dtype=float)
    if agb.shape != sd.shape or agb.shape != weights.shape or weights.ndim != 2:
        raise ValueError("AGB, AGB_SD and weights must be matching 2D arrays")
    if not np.all(np.isfinite(weights)) or np.any(weights < 0):
        raise ValueError("pixel weights must be finite and nonnegative")
    area = float(weights.sum())
    if not math.isfinite(area) or area <= 0:
        raise ValueError("intersected area must be positive")

    inside = weights > 0
    agb_valid = np.isfinite(agb) & (agb >= 0)
    sd_valid = np.isfinite(sd) & (sd >= 0)
    complete_agb = bool(np.all(agb_valid[inside]))
    complete_sd = bool(np.all(sd_valid[inside]))
    valid_area = float(weights[inside & agb_valid & sd_valid].sum())

    agb_mean = stock = carbon_mean = None
    if complete_agb:
        biomass_total = float(np.sum(weights[inside] * agb[inside]))
        stock = float(np.sum(weights[inside] * carbon_density_t_ha(agb[inside], config)))
        if math.isfinite(biomass_total) and math.isfinite(stock):
            agb_mean = _finite_or_none(biomass_total / area)
            carbon_mean = _finite_or_none(stock / area)
            if agb_mean is None or carbon_mean is None:
                agb_mean = stock = carbon_mean = None
        else:
            stock = None

    sd_mean = sd_sum = sd_sq_sum = sigma_stock = None
    if complete_sd:
        sd_mean = float(np.sum(weights[inside] * sd[inside])) / area
        terms = weights[inside] * sd[inside]
        sd_sum = float(terms.sum())
        sd_sq_sum = float(np.sum(terms**2))
        sigma_stock = sigma_from_sums(sd_sum, sd_sq_sum, config)
        sd_mean = _finite_or_none(sd_mean)
        sd_sum = _finite_or_none(sd_sum)
        sd_sq_sum = _finite_or_none(sd_sq_sum)

    return {
        "year": year,
        "area_ha": area,
        "valid_area_ha": valid_area,
        "missing_area_ha": max(0.0, area - valid_area),
        "agb_t_ha": agb_mean,
        "agb_sd_t_ha": sd_mean,
        "c_t_ha": carbon_mean,
        "stock_tc": stock,
        "sigma_stock_tc": sigma_stock,
        "_sd_sum": sd_sum,
        "_sd_sq_sum": sd_sq_sum,
    }


def baseline_rate(
    c_start_tc_ha: float | None,
    c_anchor_tc_ha: float | None,
    config: CaseCalculationConfig,
) -> float | None:
    if c_start_tc_ha is None or c_anchor_tc_ha is None:
        return None
    if not math.isfinite(c_start_tc_ha) or not math.isfinite(c_anchor_tc_ha):
        return None
    rate = (c_anchor_tc_ha - c_start_tc_ha) / (
        config.baseline_anchor_year - config.baseline_start_year
    )
    return _finite_or_none(rate)


def baseline_mean(
    year: int,
    c_start_tc_ha: float | None,
    c_anchor_tc_ha: float | None,
    config: CaseCalculationConfig,
) -> float | None:
    rate = baseline_rate(c_start_tc_ha, c_anchor_tc_ha, config)
    if rate is None or not math.isfinite(year):
        return None
    return _finite_or_none(
        max(0.0, c_anchor_tc_ha + rate * (year - config.baseline_anchor_year))
    )


def uncertainty_half_width(
    sigma_start_tc: float | None,
    sigma_end_tc: float | None,
    config: CaseCalculationConfig,
    rho_temporal: float | None = None,
) -> tuple[float | None, float | None]:
    """Return sigma in t CO2e and scenario half width H in t CO2e."""
    rho = config.rho_temporal if rho_temporal is None else rho_temporal
    if not math.isfinite(rho) or not 0 <= rho <= 1:
        raise ValueError("rho_temporal must be between zero and one")
    if sigma_start_tc is None or sigma_end_tc is None:
        return None, None
    if not math.isfinite(sigma_start_tc) or not math.isfinite(sigma_end_tc):
        return None, None
    if sigma_start_tc < 0 or sigma_end_tc < 0:
        raise ValueError("stock sigmas must be nonnegative")
    variance = (
        sigma_start_tc**2
        + sigma_end_tc**2
        - 2 * rho * sigma_start_tc * sigma_end_tc
    )
    if not math.isfinite(variance):
        return None, None
    sigma_e = math.sqrt(max(variance, 0.0)) * config.co2_per_carbon
    if not math.isfinite(sigma_e):
        return None, None
    return sigma_e, _finite_or_none(config.k_sigma * sigma_e)


def potential_units(
    e_proj_tco2e: float | None,
    e_base_tco2e: float | None,
    half_width_tco2e: float | None,
    config: CaseCalculationConfig,
) -> dict[str, Any]:
    """Potential case units; unavailable, zero and positive are distinct."""
    e_proj_tco2e = _finite_or_none(e_proj_tco2e)
    e_base_tco2e = _finite_or_none(e_base_tco2e)
    half_width_tco2e = _finite_or_none(half_width_tco2e)
    result = {
        "e_proj_tco2e": e_proj_tco2e,
        "e_base_tco2e": e_base_tco2e,
        "leakage_tco2e": config.leakage_tco2e,
        "r_tco2e": None,
        "h_tco2e": half_width_tco2e,
        "h_over_r": None,
        "unc_share": None,
        "r_adjusted_tco2e": None,
        "buffer_tco2e": None,
        "units": None,
        "available": False,
        "status": "unavailable",
        "result_scope": "расчёт по условиям кейса, не сертифицированные углеродные единицы",
        "reason": None,
    }
    if e_proj_tco2e is None:
        result["reason"] = "нет сопоставимых данных AGB за обе даты"
        return result
    if e_base_tco2e is None:
        result["reason"] = "нет базовой линии для участка и периода"
        return result
    if half_width_tco2e is None:
        result["reason"] = "нет полной оценки неопределённости AGB_SD"
        return result
    if half_width_tco2e < 0:
        result["h_tco2e"] = None
        result["reason"] = "некорректная оценка неопределённости AGB_SD"
        return result

    r = e_base_tco2e - e_proj_tco2e - config.leakage_tco2e
    if not math.isfinite(r):
        result["reason"] = "неконечное значение разницы с базовой линией"
        return result
    result["r_tco2e"] = r
    if r <= 0:
        result["units"] = 0
        result["available"] = True
        result["status"] = "zero_nonpositive_result"
        result["reason"] = "результат не превышает базовую линию"
        return result

    ratio = half_width_tco2e / r
    result["h_over_r"] = ratio
    if ratio >= config.unc_stop_ratio:
        result["units"] = 0
        result["available"] = True
        result["status"] = "zero_uncertainty"
        result["reason"] = "неопределённость не меньше самого результата"
        return result

    unc = min(1.0, max(0.0, ratio - config.unc_threshold))
    adjusted = r * (1 - unc)
    buffer = adjusted * config.buffer_share
    result.update(
        unc_share=unc,
        r_adjusted_tco2e=adjusted,
        buffer_tco2e=buffer,
        units=math.floor(adjusted * (1 - config.buffer_share)),
        available=True,
        status="calculated",
    )
    return result


def calculate_period(
    start: Mapping[str, Any],
    end: Mapping[str, Any],
    baseline_c_start_tc_ha: float | None,
    baseline_c_end_tc_ha: float | None,
    config: CaseCalculationConfig,
) -> dict[str, Any]:
    """Compare annual stocks with official baseline endpoints for this period."""
    year_start, year_end = start["year"], end["year"]
    years = year_end - year_start
    area = start.get("area_ha")
    end_area = end.get("area_ha")
    if not math.isfinite(years) or years <= 0 or area is None or end_area is None:
        raise ValueError("positive period and area are required")
    if not all(math.isfinite(value) and value > 0 for value in (area, end_area)):
        raise ValueError("area must be finite and positive")
    if not math.isclose(area, end_area, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("both years must use the same area")

    stock_start = _finite_or_none(start.get("stock_tc"))
    stock_end = _finite_or_none(end.get("stock_tc"))
    delta_stock = e_proj = e_per_ha_year = None
    if stock_start is not None and stock_end is not None:
        delta_stock = stock_end - stock_start
        e_proj = -delta_stock * config.co2_per_carbon
        e_per_ha_year = e_proj / (area * years)
        if not all(math.isfinite(value) for value in (delta_stock, e_proj, e_per_ha_year)):
            delta_stock = e_proj = e_per_ha_year = None

    base_start = _finite_or_none(baseline_c_start_tc_ha)
    base_end = _finite_or_none(baseline_c_end_tc_ha)
    e_base = None
    if base_start is not None and base_end is not None:
        e_base = _finite_or_none(
            -area * (base_end - base_start) * config.co2_per_carbon
        )

    sigma_e, half_width = uncertainty_half_width(
        start.get("sigma_stock_tc"), end.get("sigma_stock_tc"), config
    )
    units = potential_units(e_proj, e_base, half_width, config)
    return {
        "year_start": year_start,
        "year_end": year_end,
        "years": years,
        "area_ha": area,
        "c_start_t_ha": _finite_or_none(start.get("c_t_ha")),
        "c_end_t_ha": _finite_or_none(end.get("c_t_ha")),
        "stock_start_tc": stock_start,
        "stock_end_tc": stock_end,
        "delta_stock_tc": delta_stock,
        "e_tco2e": e_proj,
        "e_per_ha_year": e_per_ha_year,
        "sigma_e_tco2e": sigma_e,
        "lower_tco2e": (
            _finite_or_none(e_proj - half_width)
            if e_proj is not None and half_width is not None
            else None
        ),
        "upper_tco2e": (
            _finite_or_none(e_proj + half_width)
            if e_proj is not None and half_width is not None
            else None
        ),
        "baseline_c_start_t_ha": base_start,
        "baseline_c_end_t_ha": base_end,
        **units,
    }
