import { AREAS, PARAMETERS, areaById } from "./case";
import type { Area, Period } from "./case";
import type { ReportBlock } from "../reportPdf";
import sensitivityRaw from "./sensitivity-tver-2019-2020.json";

/* Исследовательский отчёт — KAN-53.

   Существенный вопрос выбран один: от чего на самом деле зависит число
   потенциальных единиц. Ответ оказался неудобным, и в этом вся ценность
   работы — метод разности запасов по CCI на территории около 1 800 га
   не обосновывает выпуск единиц при честном переносе ошибки.

   Все числа берутся из расчёта, а не вписаны в текст. Отчёт, в котором
   значения набраны руками, расходится с расчётом на первом же
   пересчёте, и тогда он не документ, а пересказ.

   Из одного набора блоков собирается и страница, и PDF. Иначе два
   представления одного отчёта живут врозь и однажды скажут разное. */

const CASE_IDS = ["RU_TVER_01", "RU_VOLOGDA_02", "RU_MORDOVIA_03", "RU_MORDOVIA_04"];

export const sensitivity = sensitivityRaw as {
  rho_spatial: number[];
  rho_temporal: number[];
  units: number[][];
  r: number;
  h: number;
};

function ru(value: number, digits = 0): string {
  return value.toLocaleString("ru-RU", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** Участки кейса. Добавленные нами в исследование не входят: вывод
 *  делается о наборе, который дал условие задачи. */
export function caseAreas(): Area[] {
  return CASE_IDS.map((id) => areaById(id)).filter(Boolean) as Area[];
}

export type PairStat = {
  aoi_id: string;
  name: string;
  period: Period;
};

/** Все пары лет с положительным R. Именно они — единственные кандидаты
 *  на выпуск единиц: при R ≤ 0 отношение H/R не вычисляется вовсе. */
export function positivePairs(): PairStat[] {
  const out: PairStat[] = [];
  for (const area of caseAreas()) {
    for (const period of area.periods) {
      if (period.r_tco2e !== null && period.r_tco2e > 0) {
        out.push({ aoi_id: area.aoi_id, name: area.name, period });
      }
    }
  }
  return out.sort((a, b) => (a.period.h_over_r ?? 0) - (b.period.h_over_r ?? 0));
}

export function totalPairs(): number {
  return caseAreas().reduce((sum, a) => sum + a.periods.length, 0);
}

export type ResearchFacts = {
  areas: number;
  pairs: number;
  positive: number;
  minRatio: number;
  minRatioRow: PairStat | null;
  worstBaseline: Area;
  sensitivityNonZero: number;
  sensitivityCells: number;
  sensitivityMax: number;
};

export function facts(): ResearchFacts {
  const areas = caseAreas();
  const positive = positivePairs();
  const flat = sensitivity.units.flat();
  const declining = [...areas].sort(
    (a, b) => a.baseline_rate_tc_ha_year - b.baseline_rate_tc_ha_year
  )[0];

  return {
    areas: areas.length,
    pairs: totalPairs(),
    positive: positive.length,
    minRatio: positive.length ? (positive[0].period.h_over_r ?? 0) : 0,
    minRatioRow: positive[0] ?? null,
    worstBaseline: declining,
    sensitivityNonZero: flat.filter((v) => v > 0).length,
    sensitivityCells: flat.length,
    sensitivityMax: Math.max(...flat),
  };
}

/** Отчёт как последовательность блоков. Их рисует и страница, и PDF. */
export function researchBlocks(): ReportBlock[] {
  const f = facts();
  const areas = caseAreas();
  const tver = areaById("RU_TVER_01");
  const declining = f.worstBaseline;
  const baselineLoss = declining.period_2019_2024.e_base_tco2e ?? 0;

  const blocks: ReportBlock[] = [
    {
      kind: "title",
      text: "От чего зависит число потенциальных единиц",
      sub: "Исследование чувствительности и роль контрольного участка · набор кейса, 2019—2024",
    },
    {
      kind: "note",
      text:
        "Отчёт отвечает на один вопрос: что именно определяет количество единиц, " +
        "которое выдаёт метод разности запасов по продукту ESA CCI Biomass. Все " +
        "числа взяты из расчёта сервиса и пересчитываются вместе с ним.",
    },

    { kind: "heading", text: "1. Ни один участок не даёт единиц" },
    {
      kind: "kv",
      rows: areas.map((a) => {
        const p = a.period_2019_2024;
        return [
          a.name,
          `R = ${ru(Math.round(p.r_tco2e ?? 0))} т CO₂-экв., единиц ${p.units ?? "недоступно"}`,
        ] as [string, string];
      }),
    },
    {
      kind: "note",
      text:
        `На всех ${f.areas} участках за 2019—2024 величина R не превышает нуля: результат ` +
        "не превышает базовую линию. При R ≤ 0 отношение H/R по правилам кейса не " +
        "вычисляется вовсе, а число единиц равно нулю. Это посчитанный ответ, а не " +
        "нехватка данных — разница принципиальная, и на экране она подписана.",
    },

    { kind: "heading", text: "2. Перебор всех пар лет ничего не меняет" },
    {
      kind: "kv",
      rows: [
        ["пар лет проверено", String(f.pairs)],
        ["из них R > 0", String(f.positive)],
        [
          "наименьшее H/R среди них",
          f.minRatioRow
            ? `${ru(f.minRatio, 1)} — ${f.minRatioRow.name}, ${f.minRatioRow.period.year_start}—${f.minRatioRow.period.year_end}`
            : "—",
        ],
      ],
    },
    {
      kind: "note",
      text:
        `Порог кейса — H/R < 1. Ни в одной из ${f.positive} комбинаций с положительным R ` +
        `отношение не опускается ниже ${ru(f.minRatio, 1)}, то есть полуширина ` +
        "интервала неопределённости в разы превышает сам результат. Перебор периодов " +
        "не выручает: дело не в неудачно выбранных годах.",
    },

    { kind: "heading", text: "3. Всё решают два допущения о корреляции ошибки" },
    {
      kind: "kv",
      rows: [
        ["участок", tver.name],
        ["период", "2019—2020"],
        ["R", `${ru(Math.round(sensitivity.r))} т CO₂-экв.`],
        ["H при допущениях кейса", `${ru(Math.round(sensitivity.h))} т CO₂-экв.`],
        [
          "ячеек с ненулевым результатом",
          `${f.sensitivityNonZero} из ${f.sensitivityCells}`,
        ],
      ],
    },
    {
      kind: "table",
      head: ["ρs \\ ρt", ...sensitivity.rho_temporal.map((v) => String(v))],
      rows: sensitivity.units.map((row, i) => [
        String(sensitivity.rho_spatial[i]),
        ...row.map((v) => (v > 0 ? ru(v) : "0")),
      ]),
    },
    {
      kind: "note",
      text:
        "Единицы появляются только в одном углу таблицы: при независимой ошибке между " +
        `пикселями (ρs = 0) и почти полной повторяемости между годами (ρt ≥ 0,9) — от ` +
        `${ru(Math.min(...sensitivity.units.flat().filter((v) => v > 0)))} до ${ru(f.sensitivityMax)} единиц. ` +
        "Во всех остальных сочетаниях — ноль. Ни ρs, ни ρt в наборе не заданы: это наши " +
        "допущения, и именно они, а не состояние леса, определяют ответ.",
    },

    { kind: "heading", text: "4. Контрольный участок: дело в методе, а не в лесе" },
    {
      kind: "kv",
      rows: [
        ["участок", tver.name],
        ["роль в наборе", tver.role],
        [
          "потери покрова 2020—2024",
          `${ru(
            tver.cover_loss
              .filter((l) => l.year > 2019 && l.year <= 2024)
              .reduce((s, l) => s + l.area_ha, 0),
            1
          )} га`,
        ],
        [
          "результат за период",
          `${ru(Math.round(tver.period_2019_2024.e_tco2e ?? 0))} т CO₂-экв.`,
        ],
        [
          "диапазон результата",
          `${ru(Math.round(tver.period_2019_2024.lower_tco2e ?? 0))} … ${ru(
            Math.round(tver.period_2019_2024.upper_tco2e ?? 0)
          )}`,
        ],
      ],
    },
    {
      kind: "note",
      text:
        "Контрольный участок нужен, чтобы отделить свойство метода от свойства леса. " +
        "Нарушений здесь нет, а диапазон результата всё равно на два порядка шире самого " +
        "результата. Значит ширина интервала — характеристика продукта и способа " +
        "переноса ошибки, а не признак неблагополучия территории.",
    },

    { kind: "heading", text: "5. Базовая линия меняет вывод сильнее данных" },
    {
      kind: "kv",
      rows: [
        ["участок", declining.name],
        [
          "историческая динамика g",
          `${ru(declining.baseline_rate_tc_ha_year, 3)} т C/га/год`,
        ],
        ["E_base, «потеря без проекта»", `${ru(Math.round(baselineLoss))} т CO₂-экв.`],
      ],
    },
    {
      kind: "note",
      text:
        "Историческая динамика здесь отрицательна, поэтому базовая линия продолжает " +
        `падение и предполагает потерю ${ru(Math.abs(Math.round(baselineLoss)))} т CO₂-экв. без ` +
        "всякого проекта. Проект, который просто удержал бы запас на месте, получил бы " +
        "по этой линии много единиц, ничего не вырастив. Базовая линия задана условием " +
        "кейса и дополнительности не устанавливает — но именно она, а не измерение, " +
        "определяет знак и величину результата относительно неё.",
    },

    { kind: "heading", text: "6. Чего эти числа не означают" },
    {
      kind: "list",
      items: [
        "Разрешение продуктов не совпадает: потери покрова снимаются шагом 30 м, биомасса — 100 м. Вклад изменившейся территории оценивается по доле площади и не является независимым измерением по тем же пикселям.",
        "Учитывается только надземная древесная биомасса. Почва, подстилка и мёртвая древесина в расчёт не входят, и «потеря углерода» здесь не равна выбросу в атмосферу.",
        "Ноль единиц — не оценка проекта и не отказ в нём: это результат расчёта по условиям кейса на территории такого размера.",
        "Вывод сделан для площади около 1 800 га. На большей территории пространственное усреднение ошибки работает иначе, и отношение H/R может оказаться другим.",
      ],
    },

    { kind: "heading", text: "7. Вывод" },
    {
      kind: "note",
      text:
        "На территории около 1 800 га метод разности запасов по ESA CCI Biomass не " +
        "обосновывает выпуск углеродных единиц при честном переносе ошибки продукта. " +
        "Число единиц определяется не состоянием леса, а двумя непроверяемыми " +
        "допущениями о корреляции ошибки и заданной базовой линией. Сервис показывает " +
        "это прямо и не подменяет ноль отсутствием данных.",
    },
    {
      kind: "kv",
      rows: [
        ["коэффициент углерода CF", String(PARAMETERS.carbon_fraction)],
        ["порог неопределённости", `${PARAMETERS.unc_threshold * 100} %`],
        ["резерв BUF", `${PARAMETERS.buffer_share * 100} %`],
        ["участков в наборе кейса", String(f.areas)],
      ],
    },
    {
      kind: "note",
      text:
        "Отчёт собран сервисом из посчитанного. Допущения ρs, ρt и k в наборе не заданы " +
        "и приняты нами; таблица чувствительности показывает, что от них зависит.",
    },
  ];

  void AREAS;
  return blocks;
}
