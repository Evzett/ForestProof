/* Данные кейса: результат tools/extract_case_data.py по набору из data/.

   Числа здесь не выдуманы — это разность запасов по ESA CCI Biomass v7.0
   с площадным взвешиванием на градусной сетке. Проверка корректности:
   средние запасы 2015 и 2019 годов совпадают с reference_mean_*_tc_ha
   из methodology/baseline.csv до шестого знака.

   Когда появится API, этот модуль меняется на fetch по тому же контракту:
   форма объектов совпадает с ответом расчёта. */

import raw from "./case-data.json";

export type YearPoint = {
  year: number;
  area_ha: number;
  agb_t_ha: number;
  agb_sd_t_ha: number;
  c_t_ha: number;
  stock_tc: number;
  sigma_stock_tc: number;
};

export type SensitivityCell = {
  rho_spatial: number;
  rho_temporal: number;
  h_tco2e: number;
  h_over_r: number | null;
  units: number | null;
};

export type Period = {
  year_start: number;
  year_end: number;
  years: number;
  area_ha: number;
  c_start_t_ha: number;
  c_end_t_ha: number;
  stock_start_tc: number;
  stock_end_tc: number;
  delta_stock_tc: number;
  /** Положительное E — потеря углерода из учитываемого пула, отрицательное — накопление */
  e_tco2e: number;
  e_per_ha_year: number;
  sigma_e_tco2e: number;
  lower_tco2e: number;
  upper_tco2e: number;
  baseline_c_start_t_ha: number;
  baseline_c_end_t_ha: number;
  e_proj_tco2e: number;
  e_base_tco2e: number;
  leakage_tco2e: number;
  r_tco2e: number;
  h_tco2e: number;
  h_over_r: number | null;
  unc_share: number | null;
  r_adjusted_tco2e: number | null;
  buffer_tco2e: number | null;
  /** null — расчёт единиц недоступен, 0 — доступен и равен нулю. Это разные случаи. */
  units: number | null;
  reason: string | null;
  value_rub: { low: number; base: number; high: number };
  sensitivity?: SensitivityCell[][];
};

export type CoverLoss = { year: number; area_ha: number };

export type AreaMaps = {
  stock: string;
  change: string;
  loss: string;
  change_span_tc_ha: number;
  size: [number, number];
  loss_size: [number, number];
};

export type Area = {
  aoi_id: string;
  maps: AreaMaps | null;
  name: string;
  region: string;
  role: string;
  status: string;
  area_ha: number;
  area_ha_declared: number;
  bbox: [number, number, number, number];
  baseline_id: string;
  baseline_rate_tc_ha_year: number;
  baseline_stock_t_ha: Record<string, number>;
  series: YearPoint[];
  cover_loss: CoverLoss[];
  period_2019_2024: Period;
  periods: Period[];
};

export type CaseEvent = {
  event_id: string;
  aoi_id: string;
  evidence_type: string;
  cause_supported: string;
  date_min: string;
  date_max: string;
  burned_pixels: number;
  all_pixels: number;
  uncertainty_days: [number, number];
  source_id: string;
  context_url: string;
  limitations: string;
};

export type CaseParameters = {
  carbon_fraction: number;
  co2_per_carbon: number;
  unc_threshold: number;
  buffer_share: number;
  leakage_tco2e: number;
  rho_spatial: number;
  rho_temporal: number;
  k_sigma: number;
  treecover_threshold_pct: number;
  prices_rub: { low: number; base: number; high: number };
};

const data = raw as unknown as {
  generated_from: string;
  parameters: CaseParameters;
  areas: Area[];
  events: CaseEvent[];
};

export const PARAMETERS = data.parameters;
export const AREAS = data.areas;
export const EVENTS = data.events;
export const GENERATED_FROM = data.generated_from;

export const YEARS = [2019, 2020, 2021, 2022, 2023, 2024] as const;

export function areaById(id: string | undefined): Area {
  return AREAS.find((a) => a.aoi_id === id) ?? AREAS[0];
}

/* Контур запроса словами — он же попадает в отчёт */
export function formatBbox(box: [number, number, number, number]): string {
  const [w, s, e, n] = box;
  return `${w.toFixed(4)}, ${s.toFixed(4)} — ${e.toFixed(4)}, ${n.toFixed(4)}`;
}

export function eventsFor(aoiId: string): CaseEvent[] {
  return EVENTS.filter((e) => e.aoi_id === aoiId);
}

/* Расчёт за произвольную пару лет внутри 2019–2024.
   Пересчитанных на лету значений нет: все пары посчитаны скриптом,
   интерфейс только выбирает нужную. */
export function periodFor(area: Area, start: number, end: number): Period | null {
  if (start === 2019 && end === 2024) return area.period_2019_2024;
  return area.periods.find((p) => p.year_start === start && p.year_end === end) ?? null;
}

/* Наборы данных для блока происхождения. Версии и роли фиксированы
   каталогом файлов набора (file_catalog.csv). */
export const DATASETS = [
  {
    id: "CCI_V7",
    name: "ESA CCI Above-Ground Biomass",
    version: "v7.0, годовые карты 2015–2024",
    role: "основной источник биомассы и её погрешности",
    grid: "EPSG:4326, шаг 0,00088889° (~100 м)",
  },
  {
    id: "GFC_V1_13",
    name: "Hansen Global Forest Change",
    version: "v1.13, потери 2001–2025",
    role: "области и год потери древесного покрова",
    grid: "EPSG:4326, шаг 0,00025° (~30 м)",
  },
  {
    id: "MODIS_MCD64A1_061",
    name: "MODIS Burned Area",
    version: "коллекция 061",
    role: "признак горения и доступный интервал дат",
    grid: "синусоидальная проекция, ~463 м",
  },
  {
    id: "S2_L2A",
    name: "Sentinel-2 L2A",
    version: "снимки 2019–2024 с маской SCL",
    role: "визуальное подтверждение изменений, отбор по облачности",
    grid: "UTM, 20 м",
  },
] as const;

/* Пороговые значения и допущения расчёта — выводятся на экран целиком,
   потому что от них зависит результат, а не оформление. */
export const ASSUMPTIONS = [
  {
    key: "carbon_fraction",
    label: "углеродная доля CF",
    value: `${PARAMETERS.carbon_fraction} т C / т сухого вещества`,
    source: "МГЭИК 2006, том 4, глава 4, таблица 4.3, общее значение",
    kind: "опубликованное значение" as const,
  },
  {
    key: "co2",
    label: "перевод в CO₂",
    value: "44 / 12",
    source: "отношение молярных масс",
    kind: "константа" as const,
  },
  {
    key: "rho_spatial",
    label: "корреляция ошибки между пикселями",
    value: String(PARAMETERS.rho_spatial),
    source: "допущение переноса ошибки, независимыми измерениями не подтверждено",
    kind: "допущение" as const,
  },
  {
    key: "rho_temporal",
    label: "корреляция ошибки между годами",
    value: String(PARAMETERS.rho_temporal),
    source: "допущение переноса ошибки, независимыми измерениями не подтверждено",
    kind: "допущение" as const,
  },
  {
    key: "k_sigma",
    label: "множитель интервала",
    value: `${PARAMETERS.k_sigma} (нормальное приближение, охват 90 %)`,
    source: "сценарный диапазон, не эмпирическая калибровка",
    kind: "допущение" as const,
  },
  {
    key: "treecover",
    label: "порог древесного покрова для маски потерь",
    value: `${PARAMETERS.treecover_threshold_pct} %`,
    source: "порог по treecover2000 Hansen",
    kind: "допущение" as const,
  },
  {
    key: "unc",
    label: "порог вычета за неопределённость",
    value: `${PARAMETERS.unc_threshold * 100} %`,
    source: "сценарные правила кейса",
    kind: "условие кейса" as const,
  },
  {
    key: "buffer",
    label: "резерв",
    value: `${PARAMETERS.buffer_share * 100} %`,
    source: "сценарные правила кейса",
    kind: "условие кейса" as const,
  },
  {
    key: "leakage",
    label: "утечка LK",
    value: "0 т CO₂-экв.",
    source: "сценарное допущение об отсутствии переноса деятельности",
    kind: "условие кейса" as const,
  },
] as const;
