import { AREAS, PARAMETERS, areaById } from "./case";
import type { Area, Period } from "./case";
import type { ReportBlock } from "../reportPdf";
import sensitivityRaw from "./sensitivity-tver-2019-2020.json";
import agreementRaw from "./source-agreement.json";

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

/* Сравнение источников идёт по участкам, для которых локально есть все
   четыре продукта. Контрольная Тверь в списке обязательна: она
   показывает, сколько расхождения даёт сам метод без нарушения. */
const AGREEMENT_IDS = CASE_IDS;

export const sensitivity = sensitivityRaw as {
  rho_spatial: number[];
  rho_temporal: number[];
  units: number[][];
  r: number;
  h: number;
};

/* Расхождения между источниками — KAN-61. Считает tools/source_agreement.py,
   здесь только изложение. Числа не пересчитываются на клиенте: сведение
   четырёх сеток к одной делается по растрам, а не по сводке. */
export const agreement = agreementRaw as {
  period: string;
  dnbr_threshold: number;
  caveat: string;
  areas: Record<string, Record<string, Record<string, number | string | null>>>;
};

function pct(value: number | string | null | undefined, digits = 1): string {
  return typeof value === "number" ? `${ru(value * 100, digits)} %` : "—";
}

function num(value: number | string | null | undefined, digits = 2): string {
  return typeof value === "number" ? ru(value, digits) : "—";
}

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

  /* Числа раздела 6 берутся из сводки, а не набираются в тексте: иначе
     абзац и таблица рядом разойдутся на первом же пересчёте. */
  const fire = agreement.areas.RU_MORDOVIA_03;
  const control = agreement.areas.RU_TVER_01;

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

    { kind: "heading", text: "6. Источники расходятся, и это измеримо" },
    {
      kind: "note",
      text:
        "Четыре продукта сняты с разным шагом — 20, 30, 100 и 463 метра — и в разных " +
        "проекциях. Каждое сравнение сведено на сетку более грубого из двух источников; " +
        "мелкий читается в центрах грубых пикселей. Столбец «совпадение» — доля площади, " +
        "где на нарушение указывают оба источника, к площади, где указывает хотя бы один.",
    },
    {
      kind: "table",
      head: ["участок", "потеря Hansen", "падение NBR", "оба", "совпадение"],
      rows: AGREEMENT_IDS.map((id) => {
        const a = agreement.areas[id]?.hansen_vs_dnbr ?? {};
        return [
          areaById(id)?.name ?? id,
          pct(a.hansen_loss_share),
          pct(a.nbr_drop_share),
          pct(a.both_share),
          num(a.agreement_iou, 3),
        ];
      }),
    },
    {
      kind: "note",
      text:
        "Hansen и dNBR почти не совпадают по площади: на горевшем участке в Мордовии оба " +
        `источника указывают на нарушение лишь на ${pct(fire.hansen_vs_dnbr.both_share)} ` +
        `площади при ${pct(fire.hansen_vs_dnbr.hansen_loss_share)} и ` +
        `${pct(fire.hansen_vs_dnbr.nbr_drop_share)} у каждого по отдельности. Причина не ` +
        "в чьей-то ошибке, а в том, что они отвечают на разные вопросы. Hansen фиксирует " +
        "год, в котором покров исчез совсем; dNBR меряет, насколько потемнел полог, и " +
        "реагирует на повреждение без сплошной потери. Плюс срок: между сценами периода " +
        `прошло ${num(fire.hansen_vs_dnbr.days_between, 0)} дней, и гарь успела зарасти.`,
    },
    {
      kind: "table",
      head: ["участок", "пара вплотную к событию", "падение NBR", "совпадение с Hansen"],
      rows: AGREEMENT_IDS.filter((id) => agreement.areas[id]?.hansen_vs_dnbr_near_event).map(
        (id) => {
          const a = agreement.areas[id].hansen_vs_dnbr_near_event;
          return [
            areaById(id)?.name ?? id,
            `${String(a.before_scene).slice(-14, -8)} → ${String(a.after_scene).slice(-14, -8)}` +
              ` (${num(a.days_between, 0)} дн.)`,
            pct(a.nbr_drop_share),
            num(a.agreement_iou, 3),
          ];
        }
      ),
    },
    {
      kind: "note",
      text:
        "Если взять сцены вплотную к пожару, падение NBR охватывает уже " +
        `${pct(fire.hansen_vs_dnbr_near_event?.nbr_drop_share)} площади вместо ` +
        `${pct(fire.hansen_vs_dnbr.nbr_drop_share)}. Сигнал есть, он просто затухает. ` +
        "Заметно и ограничение наблюдения: ближайший снимок после пожара, 12 сентября " +
        "2021 года, непригоден — годных пикселей внутри контура 1,7 %, — поэтому " +
        `ближайшее пригодное наблюдение отстоит от предыдущего на ` +
        `${num(fire.hansen_vs_dnbr_near_event?.days_between, 0)} дней.`,
    },
    {
      kind: "table",
      head: [
        "участок",
        "ячеек CCI",
        "с потерей Hansen",
        "с падением запаса",
        "совпадение",
        "ранговая связь",
      ],
      rows: AGREEMENT_IDS.map((id) => {
        const a = agreement.areas[id]?.cci_vs_hansen ?? {};
        return [
          areaById(id)?.name ?? id,
          num(a.cells_compared, 0),
          pct(a.hansen_cells_share),
          pct(a.cci_drop_share),
          num(a.agreement_iou, 3),
          num(a.spearman_loss_vs_drop, 2),
        ];
      }),
    },
    {
      kind: "note",
      text:
        "Здесь расхождение самое поучительное. Запас по CCI падает в половине и более " +
        "ячеек на каждом участке, включая контрольный, где потерь покрова нет вовсе: " +
        `${pct(control.cci_vs_hansen.cci_drop_share)} ячеек Твери показывают снижение ` +
        `запаса при потере Hansen в ${pct(control.cci_vs_hansen.hansen_cells_share)} ячеек. ` +
        "Значит падение запаса по CCI — это в основном не вырубка и не пожар, а " +
        "собственный шум продукта и переоценка модели между годами. Ранговая связь с " +
        "потерями Hansen положительная, но слабая: порядок ячеек совпадает лишь " +
        "отчасти. Отсюда прямое следствие для расчёта: считать по CCI разность запаса " +
        "можно, а приписывать её конкретному нарушению — нельзя.",
    },
    {
      kind: "table",
      head: ["участок", "пикселей MODIS", "горевших", "dNBR горевших", "dNBR негоревших"],
      rows: AGREEMENT_IDS.map((id) => {
        const base = agreement.areas[id]?.modis_vs_dnbr ?? {};
        const a = agreement.areas[id]?.modis_vs_dnbr_near_event ?? base;
        return [
          areaById(id)?.name ?? id,
          num(base.pixels_compared, 0),
          num(base.burned_pixels, 0),
          num(a.mean_dnbr_burned, 3),
          num(a.mean_dnbr_unburned, 3),
        ];
      }),
    },
    {
      kind: "note",
      text:
        "Это единственная пара источников, которая согласуется убедительно. На горевшем " +
        "участке в Мордовии средний dNBR в пикселях, помеченных MODIS как горевшие, равен " +
        `${num(fire.modis_vs_dnbr_near_event?.mean_dnbr_burned, 3)} против ` +
        `${num(fire.modis_vs_dnbr_near_event?.mean_dnbr_unburned, 3)} у остальных, и ` +
        `${pct(fire.modis_vs_dnbr_near_event?.burned_above_threshold, 0)} горевших пикселей ` +
        `проходят порог ${num(agreement.dnbr_threshold, 2)}. Два продукта разного ` +
        "разрешения, снятые разными приборами, указывают на одно место. На контрольном " +
        `участке в Твери горевших пикселей за весь период ` +
        `${num(control.modis_vs_dnbr.burned_pixels, 0)} из ` +
        `${num(control.modis_vs_dnbr.pixels_compared, 0)} — и dNBR там около нуля.`,
    },
    {
      kind: "note",
      text:
        "Что из этого следует для доверия к источникам. О факте исчезновения покрова " +
        "надёжнее судить по Hansen: он для этого и сделан. О тяжести повреждения — по " +
        "dNBR, но только по сценам вплотную к событию. О причине «пожар» — по MODIS, и " +
        "только по нему. О запасе биомассы — по CCI, но на уровне участка целиком, а не " +
        "отдельной ячейки. И ни одно из этих согласий не является наземной валидацией: " +
        "все четыре продукта меряют отражённый свет и могут ошибаться одинаково. Никто " +
        "из них не был в лесу.",
    },

    { kind: "heading", text: "7. Чего эти числа не означают" },
    {
      kind: "list",
      items: [
        "Разрешение продуктов не совпадает: потери покрова снимаются шагом 30 м, биомасса — 100 м. Вклад изменившейся территории оценивается по доле площади и не является независимым измерением по тем же пикселям.",
        "Учитывается только надземная древесная биомасса. Почва, подстилка и мёртвая древесина в расчёт не входят, и «потеря углерода» здесь не равна выбросу в атмосферу.",
        "Ноль единиц — не оценка проекта и не отказ в нём: это результат расчёта по условиям кейса на территории такого размера.",
        "Вывод сделан для площади около 1 800 га. На большей территории пространственное усреднение ошибки работает иначе, и отношение H/R может оказаться другим.",
      ],
    },

    { kind: "heading", text: "8. Вывод" },
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
