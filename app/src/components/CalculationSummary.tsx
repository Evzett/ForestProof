import type { Area, CalculationSummary as Summary, Period } from "../data/case";
import { PARAMETERS } from "../data/case";
import { useAiSummary } from "../data/aiSummary";
import { Card } from "./ui";

/* Краткая справка по участку.

   Текст излагает модель, числа считает сервис. Справка из набора
   остаётся под ним: если модель недоступна или её ответ отбракован
   сверкой, на экране должны остаться величины, а не пустота.

   Запрашивается сразу при открытии участка и заново при смене периода
   — справка о другом периоде это другая справка. */

function facts(area: Area, period: Period): Record<string, unknown> {
  return {
    участок: area.name,
    идентификатор: area.aoi_id,
    площадь_га: Number(area.area_ha.toFixed(1)),
    период: `${period.year_start}—${period.year_end}`,
    роль_в_наборе: area.role,
    запас_на_начало_tc_ha: Number(period.c_start_t_ha.toFixed(2)),
    запас_на_конец_tc_ha: Number(period.c_end_t_ha.toFixed(2)),
    результат_tco2e: Math.round(period.e_tco2e),
    диапазон_нижняя_tco2e: Math.round(period.lower_tco2e),
    диапазон_верхняя_tco2e: Math.round(period.upper_tco2e),
    базовая_линия_tco2e: Math.round(period.e_base_tco2e),
    R_tco2e: Math.round(period.r_tco2e),
    /* «Недоступно» и «ноль» — разные ответы (Е-05). Раньше здесь
       стояло `period.units ?? 0`, и модель получала ноль там, где
       единицы не считались вовсе, — а потом честно писала «единиц
       ноль». Сервис не выдумывает чисел, и подставлять их на входе в
       модель нельзя ровно по той же причине. */
    потенциальные_единицы:
      period.units === null ? "не считались: результат не превышает базовую линию" : period.units,
    причина_нуля: period.reason ?? "",
    цена_сценария_руб: PARAMETERS.prices_rub.base,
    оговорка: "это расчёт по условиям кейса, а не сертифицированные единицы",
  };
}

export default function CalculationSummary({
  summary,
  area,
  period,
}: {
  summary?: Summary | null;
  area?: Area;
  period?: Period;
}) {
  const key = area && period ? `plot:${area.aoi_id}:${period.year_start}-${period.year_end}` : "";
  const { ai, note, busy } = useAiSummary(key, () =>
    area && period ? facts(area, period) : {}
  );

  if (!summary && !ai) return null;

  return (
    <Card className="plot-summary">
      <div className="ov-summary__head">
        <h2 className="card__title">Краткая справка</h2>
        <span className="lvl lvl--outline">
          {ai ? "изложено моделью" : busy ? "модель отвечает…" : "собрано шаблоном"}
        </span>
      </div>

      <p>{ai ? ai.text : summary?.text}</p>

      {summary && (
        <details>
          <summary>Поля-источники</summary>
          <ul>
            {summary.source_fields.map((field) => (
              <li key={field}>
                <code>{field}</code>
              </li>
            ))}
          </ul>
        </details>
      )}

      <p className="ov-note">
        {ai
          ? `текст изложен моделью ${ai.model}; числа посчитаны сервисом и сверены с ответом`
          : "собрано шаблоном из посчитанного, без языковой модели"}
        {note && ` · модель не подключилась: ${note}`}
      </p>
    </Card>
  );
}
