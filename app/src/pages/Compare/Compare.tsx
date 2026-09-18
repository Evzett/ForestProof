import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Card, Checkbox, formatDecimal, formatNumber, plural } from "../../components/ui";
import { PageHead } from "../../components/AppShell";
import { AREAS, EVENTS } from "../../data/case";
import "./Compare.css";

/* Сравнение участков.

   Сводного балла нет и быть не может: четыре группы строк отвечают на
   четыре разных вопроса — сколько запаса, как изменилось, насколько
   уверенно и что это даёт относительно базовой линии. Сложить их в одно
   число значит скрыть, какой именно вопрос вызвал сомнение.

   Контрольный участок стоит в той же таблице специально: он показывает,
   как ведёт себя метод там, где нарушений нет. */

type Row = {
  label: string;
  hint?: string;
  value: (a: (typeof AREAS)[number]) => string;
};

const GROUPS: { title: string; rows: Row[] }[] = [
  {
    title: "Участок",
    rows: [
      { label: "регион", value: (a) => a.region },
      { label: "роль в наборе", value: (a) => a.role },
      { label: "площадь, га", value: (a) => formatDecimal(a.area_ha, 1) },
    ],
  },
  {
    title: "Запас и его изменение, 2019 → 2024",
    rows: [
      { label: "запас 2019, т C/га", value: (a) => formatDecimal(a.period_2019_2024.c_start_t_ha, 2) },
      { label: "запас 2024, т C/га", value: (a) => formatDecimal(a.period_2019_2024.c_end_t_ha, 2) },
      {
        label: "ΔC, т C",
        value: (a) => formatNumber(Math.round(a.period_2019_2024.delta_stock_tc)),
      },
      {
        label: "E, т CO₂-экв.",
        hint: "положительное — потеря из учитываемого пула",
        value: (a) => formatNumber(Math.round(a.period_2019_2024.e_tco2e)),
      },
      {
        label: "e, т CO₂-экв./га/год",
        value: (a) => formatDecimal(a.period_2019_2024.e_per_ha_year, 3),
      },
    ],
  },
  {
    title: "Неопределённость",
    rows: [
      {
        label: "диапазон E",
        value: (a) =>
          `${formatNumber(Math.round(a.period_2019_2024.lower_tco2e))} … ${formatNumber(
            Math.round(a.period_2019_2024.upper_tco2e)
          )}`,
      },
      { label: "H, т CO₂-экв.", value: (a) => formatNumber(Math.round(a.period_2019_2024.h_tco2e)) },
      {
        label: "средняя ±SD продукта, т/га",
        value: (a) =>
          formatDecimal(a.series.find((s) => s.year === 2024)?.agb_sd_t_ha ?? 0, 1),
      },
    ],
  },
  {
    title: "Изменения покрова и подтверждения",
    rows: [
      {
        label: "потери 2020—2024, га",
        value: (a) =>
          formatDecimal(
            a.cover_loss.filter((l) => l.year > 2019 && l.year <= 2024).reduce((s, l) => s + l.area_ha, 0),
            1
          ),
      },
      {
        label: "крупнейшая потеря, год",
        value: (a) => {
          const top = [...a.cover_loss].sort((x, y) => y.area_ha - x.area_ha)[0];
          return top ? `${top.year} · ${formatDecimal(top.area_ha, 1)} га` : "—";
        },
      },
      {
        label: "событие с подтверждением",
        value: (a) => {
          const e = EVENTS.find((x) => x.aoi_id === a.aoi_id);
          return e ? e.cause_supported : "нет — причина не установлена";
        },
      },
    ],
  },
  {
    title: "Относительно базовой линии",
    rows: [
      {
        label: "историческая динамика, т C/га/год",
        value: (a) => formatDecimal(a.baseline_rate_tc_ha_year, 3),
      },
      {
        label: "E_base, т CO₂-экв.",
        value: (a) => formatNumber(Math.round(a.period_2019_2024.e_base_tco2e)),
      },
      { label: "R, т CO₂-экв.", value: (a) => formatNumber(Math.round(a.period_2019_2024.r_tco2e)) },
      {
        label: "H / R",
        value: (a) =>
          a.period_2019_2024.h_over_r === null
            ? "не вычисляется при R ≤ 0"
            : formatDecimal(a.period_2019_2024.h_over_r, 2),
      },
      {
        label: "потенциальные единицы",
        value: (a) =>
          a.period_2019_2024.units === null ? "недоступно" : formatNumber(a.period_2019_2024.units),
      },
    ],
  },
];

/* Справка по выбранным участкам. Как и в обзоре, собирается шаблоном
   из посчитанного: языковой модели здесь нет, и сказать что-то, чего
   нет в числах, справка не может по устройству. */
function buildCompareSummary(picked: (typeof AREAS)[number][]): string[] {
  if (picked.length < 2) return [];
  const worst = [...picked].sort(
    (a, b) => b.period_2019_2024.e_tco2e - a.period_2019_2024.e_tco2e
  )[0];
  const best = [...picked].sort(
    (a, b) => a.period_2019_2024.e_tco2e - b.period_2019_2024.e_tco2e
  )[0];
  const losing = picked.filter((a) => a.period_2019_2024.e_tco2e > 0);
  const spread = picked.map(
    (a) => a.period_2019_2024.upper_tco2e - a.period_2019_2024.lower_tco2e
  );
  const widest = picked[spread.indexOf(Math.max(...spread))];
  const control = picked.find((a) => a.role === "контрольный участок");

  const lines = [
    `Сравниваются ${picked.length} ${plural(picked.length, [
      "участок",
      "участка",
      "участков",
    ])}. Потерю углерода за 2019—2024 показывают ${losing.length} из ${picked.length}.`,
    `Наибольшая потеря — ${worst.name}: ${formatNumber(
      Math.round(worst.period_2019_2024.e_tco2e)
    )} т CO₂-экв. Наименьшая — ${best.name}: ${formatNumber(
      Math.round(best.period_2019_2024.e_tco2e)
    )} т CO₂-экв.`,
    `Самый широкий диапазон неопределённости у «${widest.name}» — ${formatNumber(
      Math.round(Math.max(...spread))
    )} т CO₂-экв. Это ширина интервала, а не ошибка расчёта: чем она больше, тем меньше разница между участками значит.`,
  ];

  if (control) {
    lines.push(
      `В выборке есть контрольный участок «${control.name}» — на нём нарушений не ожидается, и он показывает, как ведёт себя метод там, где терять нечего.`
    );
  } else {
    lines.push(
      "Контрольного участка в выборке нет. Без него не с чем сравнить поведение метода там, где нарушений заведомо не было."
    );
  }

  lines.push(
    "Сводного балла нет и не будет: группы отвечают на разные вопросы, и сложить их в одно число значит скрыть, какой именно вопрос вызвал сомнение."
  );
  return lines;
}

export default function Compare() {
  /* Раньше в таблицу сразу попадали все участки набора. При четырёх это
     ещё читалось, но сравнение — это выбор, а не список всего, что есть:
     как только участков станет двенадцать, таблица перестанет помещаться
     на экран, и выбирать всё равно придётся. */
  const [picked, setPicked] = useState<string[]>(() => AREAS.slice(0, 2).map((a) => a.aoi_id));

  const rows = useMemo(() => AREAS.filter((a) => picked.includes(a.aoi_id)), [picked]);
  const summary = useMemo(() => buildCompareSummary(rows), [rows]);

  const toggle = (id: string) =>
    setPicked((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  return (
    <>
      <PageHead
        title="Сравнение участков"
        subtitle="Сводного рейтингового балла нет: пять групп — пять разных вопросов"
        action={
          <Link to="/app/areas" className="filter">
            ← к участкам
          </Link>
        }
      />

      <div className="cmp-cards">
        {AREAS.map((a) => (
          <Card
            key={a.aoi_id}
            className={`cmp-card ${picked.includes(a.aoi_id) ? "cmp-card--on" : ""}`.trim()}
          >
            {a.maps && <img className="cmp-card__img" src={`/maps/${a.maps.change}`} alt="" />}
            <div className="cmp-card__body">
              <b>{a.name}</b>
              <span>
                {a.aoi_id} · {formatDecimal(a.area_ha, 1)} га
              </span>
              <span className={a.role === "контрольный участок" ? "lvl lvl--low" : "lvl lvl--none"}>
                {a.role}
              </span>
              <span className="cmp-card__pick">
                <Checkbox
                  checked={picked.includes(a.aoi_id)}
                  onChange={() => toggle(a.aoi_id)}
                  label={`сравнивать ${a.name}`}
                />
                <span>в сравнении</span>
              </span>
            </div>
          </Card>
        ))}
      </div>

      {rows.length < 2 ? (
        <Card className="cmp-empty">
          <p>
            Выберите хотя бы два участка. Сравнение одного участка с самим собой ничего не
            показывает, а таблица со всеми участками сразу — это уже не сравнение, а каталог.
          </p>
        </Card>
      ) : (
        <>
          <Card className="cmp-summary">
            <div className="ov-summary__head">
              <h2 className="card__title">Краткая справка по выбранным</h2>
              <span className="lvl lvl--outline">собрано шаблоном</span>
            </div>
            <ul className="cmp-summary__list">
              {summary.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            <p className="ov-note">
              собрано из посчитанного · без языковой модели · пересобирается при смене выбора
            </p>
          </Card>

      <Card>
        <div className="tbl__scroll">
          <table className="tbl cmp-table">
            <thead>
              <tr>
                <th>показатель</th>
                {rows.map((a) => (
                  <th key={a.aoi_id} className="num">
                    {a.aoi_id.replace("RU_", "")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {GROUPS.map((group) => (
                /* Фрагмент с ключом: группа даёт две строки подряд,
                   обернуть их в tbody нельзя — таблица уже в одном. */
                <Fragment key={group.title}>
                  <tr className="tbl__group">
                    <th colSpan={AREAS.length + 1}>{group.title}</th>
                  </tr>
                  {group.rows.map((row) => (
                    <tr key={group.title + row.label}>
                      <td>
                        {row.label}
                        {row.hint && <span className="cmp-hint">{row.hint}</span>}
                      </td>
                      {rows.map((a) => (
                        <td key={a.aoi_id} className="num">
                          {row.value(a)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        <p className="ov-note">
          Числа не раскрашены намеренно: раскрашенная целиком таблица — это и есть сводная оценка,
          просто нарисованная. Контрольный участок в Тверской области нужен для сравнения: если
          результат уезжает и там, дело в методе, а не в нарушении.
        </p>
      </Card>
        </>
      )}
    </>
  );
}
