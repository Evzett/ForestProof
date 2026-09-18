import { Link } from "react-router-dom";
import { Card, formatDecimal, formatNumber } from "../../components/ui";
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

export default function Compare() {
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
          <Card key={a.aoi_id} className="cmp-card">
            {a.maps && <img className="cmp-card__img" src={`/maps/${a.maps.change}`} alt="" />}
            <div className="cmp-card__body">
              <b>{a.name}</b>
              <span>
                {a.aoi_id} · {formatDecimal(a.area_ha, 1)} га
              </span>
              <span className={a.role === "контрольный участок" ? "lvl lvl--low" : "lvl lvl--none"}>
                {a.role}
              </span>
            </div>
          </Card>
        ))}
      </div>

      <Card>
        <div className="tbl__scroll">
          <table className="tbl cmp-table">
            <thead>
              <tr>
                <th>показатель</th>
                {AREAS.map((a) => (
                  <th key={a.aoi_id} className="num">
                    {a.aoi_id.replace("RU_", "")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {GROUPS.map((group) => (
                <>
                  <tr key={group.title} className="tbl__group">
                    <th colSpan={AREAS.length + 1}>{group.title}</th>
                  </tr>
                  {group.rows.map((row) => (
                    <tr key={group.title + row.label}>
                      <td>
                        {row.label}
                        {row.hint && <span className="cmp-hint">{row.hint}</span>}
                      </td>
                      {AREAS.map((a) => (
                        <td key={a.aoi_id} className="num">
                          {row.value(a)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </>
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
  );
}
