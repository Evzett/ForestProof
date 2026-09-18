import type { Area, CalculationSummary, Period } from "./case";

/** C5 is available only for the period supplied with the backend summary. */
export function summaryForPeriod(area: Area, period: Period): CalculationSummary | null {
  if (
    period.year_start !== area.period_2019_2024.year_start ||
    period.year_end !== area.period_2019_2024.year_end
  ) {
    return null;
  }
  return area.summary ?? null;
}
