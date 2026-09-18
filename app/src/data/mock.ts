/* Мок-данные по контракту (docs/04-kontrakty-dannyh.md раздел 9).
   Заменяются на реальный API одной заменой импорта в src/api.ts.

   Требования к набору: один участок с расхождением, один без,
   один в режиме территории без проекта; разные уровни уязвимости
   и пожарной экспозиции; год без валидных наблюдений. */

import type {
  Calculation,
  ClaimCheck,
  DisturbanceEvent,
  FeedItem,
  ProjectSummary,
  RegistryItem,
  Summary,
  WatchItem,
} from "../types";

export const REGISTRY_META = {
  total: 132,
  with_geometry: 3,
  export_date: "17.09.2026",
  units_in_circulation_mln: "37,0",
  issued_2026_mln: "1,2",
  price_hint_rub: 700,
};

export const PROJECTS: ProjectSummary[] = [
  {
    project_id: "proj-01",
    name: "Нижне-Енисейский",
    subtitle: "РУСАЛ · 04-2023-00000012",
    mode: "with_project",
    area_ha: 504986,
    agb_t_ha: 135,
    agb_sd_t_ha: 24,
    historical_loss_share_pct: 7.2,
    recent_loss_ha: 1240,
    fire_exposure: "high",
    measurement_confidence_overall: "moderate",
    vulnerability_level: "medium",
    latest_observation_days_ago: 6,
    claim_status: "review_recommended",
    revenue_rub_per_ha: 501,
    preview_path: "/images/card-what.jpg",
    boundary_source: "обведена по контуру лесничества",
    calc_id: "CALC-0148",
  },
  {
    project_id: "proj-02",
    name: "Ачинское лесничество",
    subtitle: "Сибирский лес · 04-2024-00000031",
    mode: "with_project",
    area_ha: 25000,
    agb_t_ha: 160,
    agb_sd_t_ha: 28,
    historical_loss_share_pct: 3.1,
    recent_loss_ha: 0,
    fire_exposure: "low",
    measurement_confidence_overall: "high",
    vulnerability_level: "low",
    latest_observation_days_ago: 4,
    claim_status: "no_material_discrepancy",
    revenue_rub_per_ha: 518,
    preview_path: "/images/card-problem.jpg",
    boundary_source: "GeoJSON от заказчика",
    calc_id: "CALC-0149",
  },
  {
    project_id: "proj-03",
    name: "Кежемская площадка",
    subtitle: "проект не зарегистрирован",
    mode: "territory_only",
    area_ha: 31500,
    agb_t_ha: 171,
    agb_sd_t_ha: 31,
    historical_loss_share_pct: 7.8,
    recent_loss_ha: 42.1,
    fire_exposure: "high",
    measurement_confidence_overall: "low",
    vulnerability_level: "high",
    latest_observation_days_ago: 5,
    claim_status: null,
    revenue_rub_per_ha: null,
    preview_path: "/images/card-limits.jpg",
    boundary_source: "обведена по контуру лесничества",
    calc_id: "CALC-0150",
  },
];

export const REGISTRY: RegistryItem[] = [
  {
    registry_number: "04-2023-00000012",
    name: "Нижне-Енисейский",
    company: "АО «РУСАЛ КРАСНОЯРСК»",
    region: "Красноярский край",
    methodology: "Охрана лесов от пожаров (авиамониторинг)",
    effect_kind: "avoided_emissions",
    units_in_circulation: 1232611,
    data_status: "calculated",
    project_id: "proj-01",
    calc_id: "CALC-0148",
  },
  {
    registry_number: "04-2024-00000031",
    name: "Ачинское лесничество",
    company: "ООО «Сибирский лес»",
    region: "Красноярский край",
    methodology: "Лесовосстановление и содействие возобновлению",
    effect_kind: "removals",
    units_in_circulation: 45000,
    data_status: "calculated",
    project_id: "proj-02",
    calc_id: "CALC-0149",
  },
  {
    registry_number: "04-2023-00000008",
    name: "Богучанский участок",
    company: "АО «Лесинвест»",
    region: "Красноярский край",
    methodology: "Лесоразведение на неиспользуемых землях",
    effect_kind: "removals",
    units_in_circulation: 318400,
    data_status: "no_geometry",
    project_id: null,
    calc_id: null,
  },
  {
    registry_number: "04-2024-00000047",
    name: "Тасеевский",
    company: "ООО «КарбонСибирь»",
    region: "Красноярский край",
    methodology: "Охрана лесов от пожаров",
    effect_kind: "avoided_emissions",
    units_in_circulation: 96200,
    data_status: "no_geometry",
    project_id: null,
    calc_id: null,
  },
  {
    registry_number: "04-2022-00000003",
    name: "Приангарский",
    company: "ПАО «Сибирская генерация»",
    region: "Иркутская область",
    methodology: "Лесовосстановление",
    effect_kind: "removals",
    units_in_circulation: 740000,
    data_status: "no_geometry",
    project_id: null,
    calc_id: null,
  },
  {
    registry_number: "04-2025-00000066",
    name: "Усть-Илимский",
    company: "ООО «Грин Форест»",
    region: "Иркутская область",
    methodology: "Предотвращение обезлесения",
    effect_kind: "avoided_emissions",
    units_in_circulation: 12500,
    data_status: "in_progress",
    project_id: null,
    calc_id: null,
  },
  {
    registry_number: "04-2021-00000001",
    name: "Сахалинский пилотный",
    company: "Правительство Сахалинской области",
    region: "Сахалинская область",
    methodology: "Лесоклиматический проект",
    effect_kind: "removals",
    units_in_circulation: 2100000,
    data_status: "no_geometry",
    project_id: null,
    calc_id: null,
  },
];

/* Годовой ряд нарушений. 2017 и 2018 — без валидных наблюдений (NaN),
   год без данных остаётся в ряду пустым, а не подменяется соседним.

   Разбивка по типам нужна фильтру на обзоре. Сумма трёх типов равна
   area_ha: «тип не определён» — это отдельная категория, а не остаток.
   Отсутствие пожарных признаков рубкой не считается (FR-30). */
export type DisturbanceYear = {
  year: number;
  area_ha: number | null;
  fire_ha: number | null;
  non_fire_ha: number | null;
  unknown_ha: number | null;
};

export const DISTURBANCE_SERIES: DisturbanceYear[] = [
  { year: 2015, area_ha: 6, fire_ha: 6, non_fire_ha: 0, unknown_ha: 0 },
  { year: 2016, area_ha: 10, fire_ha: 4, non_fire_ha: 6, unknown_ha: 0 },
  { year: 2017, area_ha: null, fire_ha: null, non_fire_ha: null, unknown_ha: null },
  { year: 2018, area_ha: null, fire_ha: null, non_fire_ha: null, unknown_ha: null },
  { year: 2019, area_ha: 8, fire_ha: 0, non_fire_ha: 0, unknown_ha: 8 },
  { year: 2020, area_ha: 0, fire_ha: 0, non_fire_ha: 0, unknown_ha: 0 },
  { year: 2021, area_ha: 840, fire_ha: 840, non_fire_ha: 0, unknown_ha: 0 },
  { year: 2022, area_ha: 12, fire_ha: 0, non_fire_ha: 12, unknown_ha: 0 },
  { year: 2023, area_ha: 22, fire_ha: 14, non_fire_ha: 8, unknown_ha: 0 },
  { year: 2024, area_ha: 62, fire_ha: 0, non_fire_ha: 40, unknown_ha: 22 },
  { year: 2025, area_ha: 16, fire_ha: 16, non_fire_ha: 0, unknown_ha: 0 },
  { year: 2026, area_ha: 34, fire_ha: 18.4, non_fire_ha: 0, unknown_ha: 15.6 },
];

export const EVENTS: DisturbanceEvent[] = [
  {
    event_id: "proj-01-2021-01",
    year: 2021,
    area_ha: 840,
    event_type: "fire_supported",
    fire_evidence: true,
    confidence: "high",
  },
  {
    event_id: "proj-01-2024-01",
    year: 2024,
    area_ha: 320,
    event_type: "non_fire",
    fire_evidence: false,
    confidence: "moderate",
  },
  {
    event_id: "proj-01-2026-01",
    year: 2026,
    area_ha: 18.4,
    event_type: "fire_supported",
    fire_evidence: true,
    confidence: "moderate",
  },
];

export const CLAIM_CHECK: ClaimCheck = {
  status: "review_recommended",
  reference_date: "28.11.2023",
  observation_year_used: 2023,
  rows: [
    {
      metric: "forest_area_ha",
      label: "лесопокрытая площадь, га",
      reported: 504986,
      observed: 489300,
      discrepancy_pct: -3.1,
      comparable: true,
    },
    {
      metric: "agb_t_ha",
      label: "биомасса, т/га",
      reported: 135,
      observed: 118,
      discrepancy_pct: -12.6,
      comparable: true,
    },
    {
      metric: "expected_effect_co2_t_year",
      label: "объём эффекта, т CO₂/год",
      reported: 361600,
      observed: null,
      discrepancy_pct: null,
      comparable: false,
      not_comparable_reason: "avoided_emissions",
    },
  ],
  events_after_reference_date: [EVENTS[1], EVENTS[2]],
  likely_cause:
    "Наблюдаемая биомасса ниже заявленной на 12,6 % при погрешности продукта ±24 т/га.",
};

export const SUMMARY: Summary = {
  text: "Биомасса ниже заявленной на 12,6 % при погрешности продукта ±24 т/га. В 2026 году зафиксировано нарушение 18,4 га с пожарными признаками — после даты отчётности проекта. Заявленный эффект относится к предотвращённым выбросам и не проверяется.",
  generated_at: "19.09.2026 11:21",
  generator_version: "summary-0.1",
  based_on: ["CALC-0148", "CALC-0150"],
};

export const CALCULATIONS: Calculation[] = [
  {
    calc_id: "CALC-0151",
    project_id: "plot-04",
    plot_name: "Богучанский резерв",
    calculated_at: "19.09.2026 12:40",
    methodology_version: "v1.0",
    algorithm_version: "calc-0.1",
    input_hash: "9e2d770ac541…03b7",
    claim_status: null,
  },
  {
    calc_id: "CALC-0150",
    project_id: "proj-03",
    plot_name: "Кежемская площадка",
    calculated_at: "19.09.2026 11:20",
    methodology_version: "v1.0",
    algorithm_version: "calc-0.1",
    input_hash: "c71b4e02a9f3…8dd1",
    claim_status: null,
  },
  {
    calc_id: "CALC-0149",
    project_id: "proj-02",
    plot_name: "Ачинское лесничество",
    calculated_at: "19.09.2026 11:18",
    methodology_version: "v1.0",
    algorithm_version: "calc-0.1",
    input_hash: "4a0f9c13be77…21ac",
    claim_status: "no_material_discrepancy",
  },
  {
    calc_id: "CALC-0148",
    project_id: "proj-01",
    plot_name: "Нижне-Енисейский",
    calculated_at: "19.09.2026 11:14",
    methodology_version: "v1.0",
    algorithm_version: "calc-0.1",
    input_hash: "a3f9c1e77b02…44de",
    claim_status: "review_recommended",
  },
  {
    calc_id: "CALC-0147",
    project_id: "proj-01",
    plot_name: "Нижне-Енисейский",
    calculated_at: "19.09.2026 09:02",
    methodology_version: "v0.9",
    algorithm_version: "calc-0.1",
    input_hash: "a3f9c1e77b02…44de",
    claim_status: "evidence_insufficient",
  },
];

export const WATCHLIST: WatchItem[] = [
  {
    project_id: "proj-01",
    name: "Нижне-Енисейский",
    subtitle: "проект · РУСАЛ",
    last_check: "сегодня 09:14",
    new_events: 1,
    recent_loss: "18,4 га за 30 дней",
    status: "attention",
  },
  {
    project_id: "proj-03",
    name: "Кежемская площадка",
    subtitle: "территория без проекта",
    last_check: "сегодня 09:14",
    new_events: 1,
    recent_loss: "42,1 га за 30 дней",
    status: "attention",
  },
  {
    project_id: "proj-02",
    name: "Ачинское лесничество",
    subtitle: "проект · Сибирский лес",
    last_check: "сегодня 09:14",
    new_events: 0,
    recent_loss: "нет",
    status: "quiet",
  },
];

export const FEED: FeedItem[] = [
  {
    date: "27.08.2026",
    name: "Нижне-Енисейский",
    text: "нарушение 18,4 га, пожарные признаки обнаружены, доверие среднее",
    kind: "disturbance",
    level: "high",
  },
  {
    date: "19.08.2026",
    name: "Кежемская площадка",
    text: "нарушение 42,1 га, тип события не определён",
    kind: "disturbance",
    level: "medium",
  },
  {
    date: "11.08.2026",
    name: "Ачинское лесничество",
    text: "обновлён годовой ряд покрова за 2026 год",
    kind: "data",
    level: "low",
  },
  {
    date: "02.08.2026",
    name: "Нижне-Енисейский",
    text: "пересчёт по методике v1.0, расхождений с предыдущим расчётом нет",
    kind: "recalc",
    level: "none",
  },
];

export const DATA_COMPLETENESS = {
  periods_available: 10,
  periods_total: 12,
  valid_coverage_pct: 93,
  latest_observation_date: "11.09.2026",
  missing_years: [2017, 2018],
};

/* ---------- Ряд измерений по годам (вкладка «Измерение») ---------- */
export const COVER_SERIES: { year: number; forest_area_ha: number | null }[] = [
  { year: 2015, forest_area_ha: 504100 },
  { year: 2016, forest_area_ha: 503200 },
  { year: 2017, forest_area_ha: null },
  { year: 2018, forest_area_ha: null },
  { year: 2019, forest_area_ha: 500900 },
  { year: 2020, forest_area_ha: 500100 },
  { year: 2021, forest_area_ha: 492600 },
  { year: 2022, forest_area_ha: 491800 },
  { year: 2023, forest_area_ha: 489300 },
  { year: 2024, forest_area_ha: 483900 },
  { year: 2025, forest_area_ha: 482100 },
  { year: 2026, forest_area_ha: 476210 },
];

/* Доверие к измерению по составляющим. Числовой оценки не существует (FR-36). */
export const CONFIDENCE_PARTS: { label: string; value: "high" | "moderate" | "low"; basis: string }[] = [
  { label: "оптическое покрытие", value: "high", basis: "доля валидных наблюдений, облачность" },
  { label: "свежесть наблюдений", value: "high", basis: "давность последнего наблюдения" },
  { label: "неопределённость биомассы", value: "moderate", basis: "отношение погрешности к значению" },
  { label: "подтверждение из вторых источников", value: "high", basis: "сходятся ли Hansen и Dynamic World" },
];

/* Уязвимость: уровень и драйверы, без числовой вероятности (FR-39). */
export const VULNERABILITY = {
  level: "medium" as const,
  method: "эвристика по истории пожаров и доле потерь",
  model_version: null as string | null,
  drivers: [
    "повторяющиеся пожары в радиусе 10 км",
    "близость к лесовозной дороге",
    "сухость сезона выше нормы за последние 3 года",
  ],
};

/* Сценарная экономика. Дисконт задаёт аналитик и никогда
   не выводится из оценки уязвимости (FR-56). */
export const SCENARIO = {
  expected_effect_co2_t_year: 361600,
  effect_source: "project_reported" as const,
  price_scenarios: [
    { key: "pessimistic", label: "пессимистичный", price: 400 },
    { key: "base", label: "базовый", price: 700 },
    { key: "optimistic", label: "оптимистичный", price: 1100 },
  ],
  default_price: 700,
  default_haircut_pct: 20,
  area_basis: "polygon" as const,
  npv_available: false,
  npv_unavailable_reason: "нет CAPEX, OPEX, графика выпуска и срока проекта",
};

export const PROVENANCE = {
  datasets: [
    { name: "UMD/hansen/global_forest_change_2025_v1_13", version: "v1.13" },
    { name: "GOOGLE/DYNAMICWORLD/V1", version: "v1" },
    { name: "ESA/CCI/Above_Ground_Biomass/V6_0", version: "v6.0, год продукта 2022" },
    { name: "MODIS/061/MCD64A1", version: "061" },
  ],
  observation_dates: ["18.06.2026", "27.08.2026", "11.09.2026"],
  parameters: { carbon_fraction: 0.47, co2_factor: 3.6667, discount_rate: 0.18 },
  input_hash: "a3f9c1e77b0244de91c0b2f5a71e3d8c4b6f0a29d77e15c3b8a04e6f2d9317c55",
};

/* Шаги мастера добавления участка */
export const GEOMETRY_CHECKS: { name: string; ok: true | false | "warn"; value: string }[] = [
  { name: "Система координат", ok: true, value: "EPSG:4326" },
  { name: "Тип геометрии", ok: true, value: "Polygon, одна часть" },
  { name: "Самопересечения", ok: true, value: "не найдены" },
  { name: "Площадь полигона", ok: true, value: "18 200 га" },
  { name: "Спутниковое покрытие", ok: "warn", value: "11 из 12 лет, 2017 без данных" },
];

export const CALC_STEPS = [
  { label: "Лесопокрытая площадь по годам", result: "11 из 12 лет" },
  { label: "Биомасса с погрешностью", result: "154 ± 26 т/га" },
  { label: "События нарушений и пожарные признаки", result: "" },
  { label: "Полнота данных и доверие", result: "" },
  { label: "Уязвимость территории", result: "" },
];
