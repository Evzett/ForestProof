import { AREAS, areaById, eventsFor, periodFor } from "./case";
import type { Area, Period } from "./case";

/* Проекты: заявленное против посчитанного — KAN-57.

   Реестра в кейсе нет, поэтому заявленную величину вводит пользователь.
   Сам механизм сверки при этом не меняется: правила перенесены из
   forestproof_core/claim_check.py буква в букву — порог существенности
   ±10 %, сверка на дату отчётности, предотвращённые выбросы несопоставимы
   всегда, события после даты отчётности отдельным блоком.

   Дублирование осознанное и временное: когда появится API, расчёт
   переедет туда, а здесь останется только форма.

   Жёсткое ограничение: расхождение с заявленным НЕ влияет на число
   потенциальных единиц. Единицы считаются относительно базовой линии
   кейса, и подмешать туда заявку значит нарушить правила расчёта. */

const STORAGE_KEY = "forestproof.projects";

/** Порог существенности из claim_check.py: claim_discrepancy_threshold_pct */
export const DISCREPANCY_THRESHOLD_PCT = 10;

export type EffectKind = "removals" | "avoided_emissions";

export type Project = {
  id: string;
  name: string;
  company: string;
  aoi_id: string;
  period_start: number;
  period_end: number;
  /** Заявленный объём эффекта за период, т CO₂-экв. */
  claimed_tco2e: number;
  reporting_date: string;
  effect_kind: EffectKind;
};

export type ClaimStatus =
  | "no_material_discrepancy"
  | "review_recommended"
  | "evidence_insufficient"
  | "not_comparable";

export type ClaimCheck = {
  status: ClaimStatus;
  reported: number;
  observed: number | null;
  discrepancy_pct: number | null;
  comparable: boolean;
  not_comparable_reason: string | null;
  likely_cause: string;
  events_after_reference_date: { year: number; area_ha: number; note: string }[];
  area: Area;
  period: Period | null;
};

export const STATUS_LABEL: Record<ClaimStatus, string> = {
  no_material_discrepancy: "расхождений нет",
  review_recommended: "требует проверки",
  evidence_insufficient: "данных недостаточно",
  not_comparable: "не сопоставимы",
};

export const STATUS_LEVEL: Record<ClaimStatus, "low" | "medium" | "high" | "none"> = {
  no_material_discrepancy: "low",
  review_recommended: "high",
  evidence_insufficient: "none",
  not_comparable: "none",
};

export const EFFECT_LABEL: Record<EffectKind, string> = {
  removals: "поглощение",
  avoided_emissions: "предотвращённые выбросы",
};

/* ---------------------------------------------------------- сверка ---- */

export function checkProject(project: Project): ClaimCheck {
  const area = areaById(project.aoi_id);
  const period = periodFor(area, project.period_start, project.period_end);

  /* Событие после даты отчётности — устаревание отчёта, а не расхождение:
     отчёт физически не мог его содержать. На статус не влияет. */
  const reportingYear = Number(project.reporting_date.slice(0, 4));
  const eventsAfter = area.cover_loss
    .filter((l) => l.year > reportingYear && l.year <= project.period_end)
    .map((l) => ({
      year: l.year,
      area_ha: l.area_ha,
      note: "потеря покрова после даты отчётности",
    }));

  const base = {
    reported: project.claimed_tco2e,
    events_after_reference_date: eventsAfter,
    area,
    period,
  };

  /* Предотвращённые выбросы — оценка того, сколько сгорело бы без
     проекта. Величина контрфактическая, базовых линий проекта мы не
     считаем, спутник её не видит. Несопоставимо при любых данных. */
  if (project.effect_kind === "avoided_emissions") {
    return {
      ...base,
      status: "not_comparable",
      observed: null,
      discrepancy_pct: null,
      comparable: false,
      not_comparable_reason:
        "заявлен эффект вида предотвращённых выбросов: величина контрфактическая и спутником не проверяется",
      likely_cause:
        "Строка показана, но не проверяется. Чтобы сверка стала возможной, нужен заявленный эффект вида поглощения.",
    };
  }

  if (!period) {
    return {
      ...base,
      status: "evidence_insufficient",
      observed: null,
      discrepancy_pct: null,
      comparable: false,
      not_comparable_reason: null,
      likely_cause: `Для пары ${project.period_start} — ${project.period_end} на участке нет сопоставимых состояний.`,
    };
  }

  if (!Number.isFinite(project.claimed_tco2e) || project.claimed_tco2e === 0) {
    return {
      ...base,
      status: "evidence_insufficient",
      observed: null,
      discrepancy_pct: null,
      comparable: false,
      not_comparable_reason: null,
      likely_cause: "Заявленный объём эффекта не задан или равен нулю — сравнивать не с чем.",
    };
  }

  /* Знак. Положительное E — потеря углерода, отрицательное — накопление.
     Заявленное поглощение положительно, поэтому наблюдение берётся
     со знаком минус: сравниваются одноимённые величины, а не значения
     с разной ориентацией оси. */
  const observed = -period.e_tco2e;
  const raw = ((observed - project.claimed_tco2e) / project.claimed_tco2e) * 100;
  /* Округляем до сотых: без этого совпадение до последнего знака
     показывается как «−0,0 %», и читается как крошечное расхождение. */
  const discrepancy = Math.abs(raw) < 0.005 ? 0 : raw;
  const material = Math.abs(discrepancy) > DISCREPANCY_THRESHOLD_PCT;

  return {
    ...base,
    status: material ? "review_recommended" : "no_material_discrepancy",
    observed,
    discrepancy_pct: discrepancy,
    comparable: true,
    not_comparable_reason: null,
    likely_cause: material
      ? observed < project.claimed_tco2e
        ? "Наблюдаемое накопление меньше заявленного. Возможные причины: нарушения внутри границ, другая граница участка, другой учитываемый пул."
        : "Наблюдаемое накопление больше заявленного. Возможные причины: заявлена только часть территории либо консервативная оценка проекта."
      : "Расхождение в пределах порога существенности. Это не подтверждение проекта, а отсутствие расхождения по нашим данным.",
  };
}

/* ------------------------------------------------------- хранение ---- */

export function loadProjects(): Project[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    /* приватное окно или запрет на хранилище — начинаем с пустого списка */
    return [];
  }
}

export function saveProjects(projects: Project[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(projects));
  } catch {
    /* не сохранилось — список живёт в памяти до перезагрузки */
  }
}

/* ------------------------------------------------ загрузка таблицей ---- */

export type ParseResult = { projects: Project[]; errors: string[] };

const COLUMNS = [
  "name",
  "company",
  "aoi_id",
  "period_start",
  "period_end",
  "claimed_tco2e",
  "reporting_date",
  "effect_kind",
] as const;

export const TEMPLATE_HEADER = COLUMNS.join(",");

export const TEMPLATE_ROW =
  "Богучанское лесовосстановление,ООО «Пример»,RU_TVER_01,2019,2024,9000,2024-12-31,removals";

/* Разделитель определяется по первой строке: Excel в русской локали
   сохраняет CSV с точкой с запятой, и файл, выгруженный оттуда,
   иначе читался бы одной колонкой. */
function splitRow(line: string, separator: string): string[] {
  const out: string[] = [];
  let current = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        quoted = !quoted;
      }
    } else if (ch === separator && !quoted) {
      out.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  out.push(current);
  return out.map((v) => v.trim());
}

export function parseProjectsCsv(text: string): ParseResult {
  const errors: string[] = [];
  const projects: Project[] = [];
  /* BOM от Excel съедает первый заголовок, если его не снять */
  const lines = text.replace(/^﻿/, "").split(/\r?\n/).filter((l) => l.trim());

  if (lines.length < 2) {
    return { projects, errors: ["В файле нет строк с данными — только заголовок или пусто."] };
  }

  const separator = (lines[0].match(/;/g) ?? []).length > (lines[0].match(/,/g) ?? []).length
    ? ";"
    : ",";
  const header = splitRow(lines[0], separator).map((h) => h.toLowerCase());

  const missing = COLUMNS.filter((c) => !header.includes(c));
  if (missing.length > 0) {
    return {
      projects,
      errors: [`В заголовке не хватает столбцов: ${missing.join(", ")}`],
    };
  }

  const known = new Set(AREAS.map((a) => a.aoi_id));

  lines.slice(1).forEach((line, index) => {
    const cells = splitRow(line, separator);
    const get = (key: string) => cells[header.indexOf(key)] ?? "";
    const rowNumber = index + 2;

    const aoi = get("aoi_id");
    if (!known.has(aoi)) {
      errors.push(`строка ${rowNumber}: участок «${aoi}» не найден в наборе`);
      return;
    }

    const claimed = Number(get("claimed_tco2e").replace(/\s/g, "").replace(",", "."));
    if (!Number.isFinite(claimed)) {
      errors.push(`строка ${rowNumber}: заявленный объём «${get("claimed_tco2e")}» не число`);
      return;
    }

    const start = Number(get("period_start"));
    const end = Number(get("period_end"));
    if (!(start < end)) {
      errors.push(`строка ${rowNumber}: конечный год должен быть больше начального`);
      return;
    }

    const kind = get("effect_kind") === "avoided_emissions" ? "avoided_emissions" : "removals";

    projects.push({
      id: `${aoi}-${start}-${end}-${Date.now()}-${index}`,
      name: get("name") || `Проект ${rowNumber}`,
      company: get("company"),
      aoi_id: aoi,
      period_start: start,
      period_end: end,
      claimed_tco2e: claimed,
      reporting_date: get("reporting_date") || `${end}-12-31`,
      effect_kind: kind,
    });
  });

  return { projects, errors };
}

/* Подсказка, какой объём был бы «в пределах порога» — чтобы форму
   можно было заполнить осмысленно, а не наугад. */
export function plausibleClaim(aoiId: string, start: number, end: number): number | null {
  const area = areaById(aoiId);
  const period = periodFor(area, start, end);
  if (!period) return null;
  return Math.round(-period.e_tco2e);
}

export function eventsNote(aoiId: string): number {
  return eventsFor(aoiId).length;
}
