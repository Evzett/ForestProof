import { PARAMETERS } from "./case";
import type { Period, YearPoint } from "./case";

/* Пересчёт неопределённости и единиц на лету.

   Повторяет tools/extract_case_data.py буква в букву — это осознанное
   дублирование ради одной возможности: показать на экране, как меняется
   результат при других допущениях, не гоняя запрос на сервер. Когда
   появится API, расчёт переедет туда, а этот модуль останется только
   для интерактивного разбора.

   Порядок проверок важен и повторён точно: при R ≤ 0 отношение H/R
   не вычисляется вовсе, а не считается и отбрасывается. */

export type UnitsResult = {
  h: number;
  hOverR: number | null;
  unc: number | null;
  rAdjusted: number | null;
  buffer: number | null;
  units: number | null;
  reason: string | null;
};

/* Стандартное отклонение суммарного запаса при заданной корреляции
   ошибки между пикселями. Суммы Σ(a·sd) и Σ(a·sd)² посчитаны заранее
   по растрам — по ним σ восстанавливается для любого ρ. */
function stockSigma(point: YearPoint, rhoSpatial: number): number {
  const sum = point._sd_sum ?? 0;
  const sq = point._sd_sq_sum ?? 0;
  const variance = (1 - rhoSpatial) * sq + rhoSpatial * sum * sum;
  return PARAMETERS.carbon_fraction * Math.sqrt(Math.max(variance, 0));
}

export function halfWidth(
  start: YearPoint,
  end: YearPoint,
  rhoSpatial: number,
  rhoTemporal: number,
  kSigma: number
): number {
  const s0 = stockSigma(start, rhoSpatial);
  const s1 = stockSigma(end, rhoSpatial);
  const sigmaDelta = Math.sqrt(
    Math.max(s0 * s0 + s1 * s1 - 2 * rhoTemporal * s0 * s1, 0)
  );
  return kSigma * sigmaDelta * PARAMETERS.co2_per_carbon;
}

export function potentialUnits(r: number, h: number): UnitsResult {
  const base: UnitsResult = {
    h,
    hOverR: null,
    unc: null,
    rAdjusted: null,
    buffer: null,
    units: 0,
    reason: null,
  };

  if (!Number.isFinite(r) || !Number.isFinite(h) || h < 0) {
    return { ...base, units: null, reason: "входные данные неполные — расчёт единиц недоступен" };
  }
  if (r <= 0) {
    return { ...base, reason: "результат не превышает базовую линию" };
  }

  const ratio = h / r;
  if (ratio >= 1) {
    return { ...base, hOverR: ratio, reason: "неопределённость не меньше самого результата" };
  }

  const unc = Math.min(1, Math.max(0, ratio - PARAMETERS.unc_threshold));
  const rAdjusted = r * (1 - unc);
  return {
    h,
    hOverR: ratio,
    unc,
    rAdjusted,
    buffer: rAdjusted * PARAMETERS.buffer_share,
    units: Math.floor(rAdjusted * (1 - PARAMETERS.buffer_share)),
    reason: null,
  };
}

/* Полный пересчёт периода под другие допущения */
export function recompute(
  period: Period,
  start: YearPoint | undefined,
  end: YearPoint | undefined,
  rhoSpatial: number,
  rhoTemporal: number,
  kSigma: number
): UnitsResult & { lower: number; upper: number } {
  if (!start || !end) {
    const fallback = potentialUnits(period.r_tco2e, period.h_tco2e);
    return { ...fallback, lower: period.lower_tco2e, upper: period.upper_tco2e };
  }
  const h = halfWidth(start, end, rhoSpatial, rhoTemporal, kSigma);
  const result = potentialUnits(period.r_tco2e, h);
  return {
    ...result,
    lower: period.e_tco2e - h,
    upper: period.e_tco2e + h,
  };
}

/* Уровни охвата для нормального приближения. Числа стандартные,
   но статус диапазона от этого не меняется: он остаётся сценарным. */
export const COVERAGE = [
  { k: 1, label: "68 %" },
  { k: 1.645, label: "90 %" },
  { k: 1.96, label: "95 %" },
] as const;
