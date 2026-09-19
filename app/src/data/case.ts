/* Данные кейса: результат tools/extract_case_data.py по набору из data/.

   Числа здесь не выдуманы — это разность запасов по ESA CCI Biomass v7.0
   с площадным взвешиванием на градусной сетке. Проверка корректности:
   средние запасы 2015 и 2019 годов совпадают с reference_mean_*_tc_ha
   из methodology/baseline.csv до шестого знака.

   Когда появится API, этот модуль меняется на fetch по тому же контракту:
   форма объектов совпадает с ответом расчёта. */

import raw from "./case-data.json";
import modelRaw from "./stability-model.json";

export type YearPoint = {
  year: number;
  area_ha: number;
  agb_t_ha: number;
  agb_sd_t_ha: number;
  c_t_ha: number;
  stock_tc: number;
  sigma_stock_tc: number;
  /* Суммы Σ(a·sd) и Σ(a·sd)², по которым σ пересчитывается для любой
     корреляции без повторного чтения растров. Служебные, поэтому с _. */
  _sd_sum?: number;
  _sd_sq_sum?: number;
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

export type StabilityDriver = {
  label: string;
  value: number;
  unit: string;
  threshold: number;
  points: number;
};

export type Stability = {
  level: "low" | "medium" | "high";
  score: number;
  max_score: number;
  features: Record<string, number>;
  drivers: StabilityDriver[];
  method: string;
  model_version: string | null;
  limitation: string;
};

export type SentinelObservation = {
  role: "before" | "immediate_after" | "recovery";
  date: string;
  scene_id: string;
  image: string;
  valid_fraction: number;
  usable: boolean;
  scl_valid_classes: number[];
  /** Версия обработки L2A: с 04.00 у продукта другой ноль отражения */
  processing_baseline: string;
  harmonised: boolean;
};

export type SentinelComparison = {
  comparable_fraction: number;
  delta_ndvi: number | null;
  delta_nbr: number | null;
  note?: string;
  baselines?: string[];
  before_role?: string;
  after_role?: string;
};

export type SentinelEvidence = {
  observations: SentinelObservation[];
  comparison: SentinelComparison | null;
  quality_rule?: string;
  display_note?: string;
  interpretation?: string;
  unavailable?: string;
};

export type Area = {
  aoi_id: string;
  summary?: CalculationSummary;
  /* Откуда брать картинки этого участка. У набора они лежат в сборке
     фронта, у загруженного контура — отдаются сервисом со своего адреса.
     У участков набора поле пустое: их обслуживает путь по умолчанию. */
  maps_base?: string | null;
  /* Чем задан участок. У набора — вырезками из продукта, у контура
     пользователя — геометрией, которую он прислал. */
  geometry?: unknown;
  geometry_source?: string;
  baseline_kind?: string;
  baseline_note?: string;
  data_sources?: string[];
  evidence?: {
    scenes: { image: string; date: string; role?: string; year?: number }[];
    events: Record<string, unknown>[];
    notes: string[];
  } | null;
  maps: AreaMaps | null;
  terrain: Terrain | null;
  sentinel: SentinelEvidence | null;
  /* Снимок, собранный нами для участков без вложенных в набор сцен:
     окно каналов Sentinel-2 прочитано из облака по контуру. */
  scene_preview: {
    image: string;
    date: string;
    scene_id: string;
    usable_fraction: number;
    cloud_percent: number | null;
    source: string;
    /* Пара снимков: начало периода и конец. Обложка берёт поздний,
       страница участка показывает оба. */
    shots?: {
      role: "before" | "after";
      year: number;
      image: string;
      date: string;
      scene_id: string;
      usable_fraction: number;
    }[];
  } | null;
  stability: Stability;
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

export type CalculationSummary = {
  text: string;
  source_fields: string[];
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
  /* Откуда взялось событие: пришло с набором кейса или найдено нашим
     поиском по продукту гарей. Показывается на экране — выдавать своё
     за данные набора нельзя. */
  source_kind?: string;
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

export type PriceKey = "low" | "base" | "high";

export const PRICE_SCENARIOS: { key: PriceKey; label: string; price: number }[] = [
  { key: "low", label: "минимальный", price: PARAMETERS.prices_rub.low },
  { key: "base", label: "базовый", price: PARAMETERS.prices_rub.base },
  { key: "high", label: "оптимистичный", price: PARAMETERS.prices_rub.high },
];

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

/* ---------- Модель устойчивости (KAN-54) ----------

   Второе мнение рядом с пороговыми правилами, а не вместо них.
   На четырёх участках модель проверить нечем, и она сама это пишет
   в поле verdict — оно выводится на экран целиком, а не прячется. */

export type Terrain = {
  width: number;
  height: number;
  unit: string;
  peak_t_ha: number;
  pixel_area_ha: number;
  years: number[];
  /* Сетка на каждый год набора, ключ — год строкой. Значение -1 означает
     «пиксель вне контура»: ноль тоже значение, и путать «здесь нет леса»
     с «сюда не спрашивали» нельзя. */
  grids: Record<string, number[]>;
  /* Год последней потери покрова в клетке, 0 — потери не было. Hansen
     снимает втрое мельче CCI, поэтому в клетку запаса попадает около
     дюжины его пикселей и берётся самый поздний год среди них. */
  loss_years: number[];
};

export type ModelForecast = {
  probability: number;
  category: "low" | "medium" | "high";
  feature_window: [number, number];
  horizon: [number, number];
  recent_loss_pct: number;
};

export type ModelPrediction = {
  aoi_id: string;
  available: boolean;
  reason?: string;
  /* Проверка: признаки 2001—2019, ответ про 2020—2024, который уже
     известен и показан рядом как факт. */
  probability?: number;
  category?: "low" | "medium" | "high";
  label?: number;
  future_loss_pct?: number;
  /* Прогноз: то же окно длиной девятнадцать лет, сдвинутое к концу
     данных. Ответ про 2025—2029 — его ещё никто не знает. */
  forecast?: ModelForecast | null;
};

export type StabilityModel = {
  method: string;
  features: string[];
  l2: number;
  weights: Record<string, number>;
  bias: number;
  standardisation: {
    mean: number[];
    scale: number[];
  };
  thresholds?: {
    medium: number;
    high: number;
  };
  predictions: ModelPrediction[];
  sample: {
    size: number;
    positives: number;
    minority_class: number;
    train: number;
    test: number;
    required_minority: number;
    sufficient: boolean;
  };
  quality: {
    roc_auc_train: number;
    roc_auc_test: number;
    best_single_feature: string;
    best_single_auc: number;
    beats_single_feature: boolean;
  };
  design: {
    feature_window: string;
    label_window: string;
    leakage: string;
    label_rule: string;
  };
  verdict: string;
  status: string;
};

export const MODEL = modelRaw as unknown as StabilityModel;

/* Горизонт скрининга — один на правила и на модель, и берётся он из
   расчёта, а не вписывается в подпись. Раньше в трёх местах стояло
   «2024—2029», а в данных лежало «2025—2029»: признаки считаются по
   данные включительно, а отвечает скрининг про следующую пятилетку. */
export const SCREENING_HORIZON: [number, number] = (() => {
  const known = MODEL.predictions.map((p) => p.forecast?.horizon).filter(Boolean) as [
    number,
    number,
  ][];
  return known[0] ?? [2025, 2029];
})();

export const SCREENING_HORIZON_LABEL = `${SCREENING_HORIZON[0]}—${SCREENING_HORIZON[1]}`;

/** Вычисляет прогноз обученной модели для любого произвольного или загруженного контура. */
export function computeContourModelPrediction(
  area: Area | Record<string, unknown>
): ModelPrediction {
  const aoiId = (area as Area).aoi_id ?? "custom";
  const areaHa = Number((area as Area).area_ha) || 1000;
  const coverLoss = (area as Area).cover_loss ?? [];

  const losses = new Map<number, number>();
  if (Array.isArray(coverLoss)) {
    for (const item of coverLoss) {
      if (typeof item?.year === "number" && typeof item?.area_ha === "number") {
        losses.set(item.year, item.area_ha);
      }
    }
  }

  // Окно прогноза [2006, 2024]
  const lossPctList: number[] = [];
  for (let y = 2006; y <= 2024; y++) {
    const ha = losses.get(y) ?? 0;
    lossPctList.push((ha / areaHa) * 100);
  }
  const totalLossPct = lossPctList.reduce((a, b) => a + b, 0);
  const yearsWithLoss = lossPctList.filter((p) => p > 0.1).length;
  const recentLossPct = lossPctList.slice(-3).reduce((a, b) => a + b, 0);
  const peakLossPct = Math.max(0, ...lossPctList);
  const meanTreecover = 70.0;
  const forestShare = Math.max(0.2, Math.min(1.0, 1.0 - totalLossPct / 100));

  const mean = MODEL.standardisation.mean;
  const scale = MODEL.standardisation.scale;
  const weights = [
    MODEL.weights["loss_share_2001_2019_pct"] ?? 0,
    MODEL.weights["loss_years_2001_2019"] ?? 0,
    MODEL.weights["recent_loss_2017_2019_pct"] ?? 0,
    MODEL.weights["peak_year_loss_pct"] ?? 0,
    MODEL.weights["mean_treecover_pct"] ?? 0,
    MODEL.weights["forest_share"] ?? 0,
  ];

  const features = [totalLossPct, yearsWithLoss, recentLossPct, peakLossPct, meanTreecover, forestShare];
  let logit = MODEL.bias;
  for (let i = 0; i < 6; i++) {
    const z = (features[i] - mean[i]) / (scale[i] || 1);
    logit += z * weights[i];
  }
  const prob = 1 / (1 + Math.exp(-Math.max(-30, Math.min(30, logit))));
  const category: "low" | "medium" | "high" = prob >= 0.65 ? "high" : prob >= 0.35 ? "medium" : "low";

  // Окно проверки на известном пятилетии [2001, 2019]
  const histList: number[] = [];
  for (let y = 2001; y <= 2019; y++) {
    const ha = losses.get(y) ?? 0;
    histList.push((ha / areaHa) * 100);
  }
  const histTotal = histList.reduce((a, b) => a + b, 0);
  const histYears = histList.filter((p) => p > 0.1).length;
  const histRecent = histList.slice(-3).reduce((a, b) => a + b, 0);
  const histPeak = Math.max(0, ...histList);
  const histFeat = [histTotal, histYears, histRecent, histPeak, meanTreecover, forestShare];
  let histLogit = MODEL.bias;
  for (let i = 0; i < 6; i++) {
    const z = (histFeat[i] - mean[i]) / (scale[i] || 1);
    histLogit += z * weights[i];
  }
  const histProb = 1 / (1 + Math.exp(-Math.max(-30, Math.min(30, histLogit))));
  const histCat: "low" | "medium" | "high" = histProb >= 0.65 ? "high" : histProb >= 0.35 ? "medium" : "low";

  const actualLoss2020_2024 = [2020, 2021, 2022, 2023, 2024]
    .map((y) => losses.get(y) ?? 0)
    .reduce((a, b) => a + b, 0);
  const actualLossPct = (actualLoss2020_2024 / areaHa) * 100;

  return {
    aoi_id: aoiId,
    available: true,
    probability: histProb,
    category: histCat,
    label: actualLossPct >= 1.0 ? 1 : 0,
    future_loss_pct: actualLossPct,
    forecast: {
      probability: prob,
      category,
      feature_window: [2006, 2024],
      horizon: [SCREENING_HORIZON[0], SCREENING_HORIZON[1]],
      recent_loss_pct: recentLossPct,
    },
  };
}

export function modelFor(
  aoiId: string,
  area?: Area | Record<string, unknown> | null
): ModelPrediction | undefined {
  const found = MODEL.predictions.find((p) => p.aoi_id === aoiId);
  if (found && found.forecast) return found;
  if (area) {
    return computeContourModelPrediction(area);
  }
  return found;
}

/* Подписи признаков — те же, что в tools/stability_features.py */
export const FEATURE_LABEL: Record<string, string> = {
  loss_share_2001_2019_pct: "доля площади, потерявшей покров за 2001—2019",
  loss_years_2001_2019: "число лет с заметной потерей",
  recent_loss_2017_2019_pct: "потери за последние три года перед прогнозом",
  peak_year_loss_pct: "потеря в самый тяжёлый год",
  mean_treecover_pct: "средняя сомкнутость крон на 2000 год",
  forest_share: "доля лесной площади участка",
};

/* Роли и названия участков приходят из набора кейса как есть — менять
   их нельзя, это данные. Но «мозаика потерь покрова» ничего не говорит
   тому, кто набор не открывал, поэтому к каждой роли идёт расшифровка
   обычными словами. */
export const ROLE_HINT: Record<string, string> = {
  "контрольный участок":
    "эталон: нарушений здесь не ждём. Нужен, чтобы проверить, что метод не выдумывает потери там, где их нет",
  "недавние потери покрова с неустановленной причиной":
    "«мозаика» — покров терялся не одним пятном, а россыпью мелких участков по всей территории. Продукт гарей причину не подтверждает",
  "повторные нарушения и пожар":
    "нарушения повторялись год за годом, и среди них есть подтверждённый пожар",
  "ранние потери покрова и последующий пожар":
    "основная потеря случилась задолго до периода анализа, пожар 2021 года пришёлся уже на восстановившийся лес",
};

/* Адрес картинки участка.

   У участков набора карты и снимки лежат в сборке фронта (`public/maps`),
   у загруженного контура их отдаёт сервис со своего адреса. Разница ровно
   в приставке, и держать это знание в каждом месте, где рисуется
   картинка, — верный способ однажды показать пустоту и не понять почему. */
export function mapAsset(area: Pick<Area, "maps_base">, file: string): string {
  if (!area.maps_base) return `/maps/${file}`;
  const origin = (import.meta.env.VITE_API_BASE ?? "").replace(/\/+$/, "");
  return `${origin}${area.maps_base}/${file}`;
}
