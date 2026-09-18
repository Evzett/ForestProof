import { useMemo, useState, type ReactNode } from "react";
import { formatArea, formatDecimal } from "./ui";
import "./YearLossChart.css";

/* Диаграмма потерь покрова по годам. Оформление снято с макета
   «Нарушения по годам»: скруглённые столбцы с диагональной штриховкой,
   значение пилюлей поверх столбца, слева итог и легенда, выноска с
   долей самого тяжёлого года.

   Компонент общий для обзора и карточки участка: раньше это были две
   разные диаграммы с разными классами, и когда стили одной переписали
   по макету, вторая осталась без стилей вовсе — столбцы исчезли, а от
   графика остался ряд голых подписей с годами. */

export type LossRow = { year: number; area_ha: number };

export function YearLossChart({
  rows,
  isWithin,
  badgeLabel,
  caption,
  renderPicked,
  outsideLabel = "вне периода анализа",
  withinLabel = "внутри периода анализа",
}: {
  rows: LossRow[];
  isWithin: (year: number) => boolean;
  badgeLabel: string;
  caption: ReactNode;
  /* Что показать под выбранным годом. В обзоре это разбор по участкам,
     на карточке участка разбирать нечего — там своя подпись. */
  renderPicked?: (row: LossRow) => ReactNode;
  outsideLabel?: string;
  withinLabel?: string;
}) {
  const [pickedYear, setPickedYear] = useState<number | null>(null);

  const peak = useMemo(
    () => rows.reduce((a, b) => (b.area_ha > a.area_ha ? b : a), rows[0]),
    [rows]
  );
  const total = rows.reduce((s, l) => s + l.area_ha, 0);
  const peakShare = total > 0 ? (peak.area_ha / total) * 100 : 0;
  /* Выбранный год живёт, только пока он есть в показанном ряду: иначе
     после смены глубины ряда панель показывала бы год, которого на
     графике уже нет. */
  const picked = rows.find((l) => l.year === pickedYear) ?? null;

  /* Выноска ставится над самым высоким столбцом: столбцы равной ширины,
     поэтому центр нужного — это его порядковый номер плюс половина. */
  const calloutLeft = ((rows.findIndex((l) => l.year === peak.year) + 0.5) / rows.length) * 100;

  return (
    <div className="yloss">
      <div className="yloss__info">
        <span className="yloss__badge">{badgeLabel}</span>
        <div className="yloss__total tabular">
          {formatArea(Math.round(total))} <small>га</small>
        </div>
        <p className="yloss__caption">{caption}</p>

        {picked ? (
          <div className="yloss__picked">
            <div className="yloss__picked-head">
              <b>{picked.year}</b>
              <span>{formatDecimal(picked.area_ha, 1)} га</span>
              <button type="button" className="yloss__clear" onClick={() => setPickedYear(null)}>
                сбросить
              </button>
            </div>
            {renderPicked?.(picked)}
          </div>
        ) : (
          <ul className="yloss__legend">
            <li>
              <i className="yloss__dot yloss__dot--peak" />
              наибольший год ряда
            </li>
            <li>
              <i className="yloss__dot yloss__dot--within" />
              {withinLabel}
            </li>
            <li>
              <i className="yloss__dot yloss__dot--outside" />
              {outsideLabel}
            </li>
            <li className="yloss__hint">нажмите столбец, чтобы посмотреть год</li>
          </ul>
        )}
      </div>

      <div className="yloss__plot">
        {rows.map((l) => {
          const within = isWithin(l.year);
          const isPeak = l.year === peak.year;
          const share = peak.area_ha > 0 ? (l.area_ha / peak.area_ha) * 100 : 0;
          /* Столбцы разной высоты, но одной формы: нижняя граница в 14 %
             держит скруглённую пилюлю и в год, когда потеряли гектар.
             Без неё малые годы схлопываются в полоску. */
          const height = Math.max(share, 14);
          return (
            <div key={l.year} className="yloss__col">
              <button
                type="button"
                className={`yloss__bar ${
                  isPeak ? "yloss__bar--peak" : within ? "yloss__bar--within" : "yloss__bar--outside"
                } ${picked?.year === l.year ? "yloss__bar--picked" : ""}`.trim()}
                style={{ height: `${height}%` }}
                aria-pressed={picked?.year === l.year}
                onClick={() => setPickedYear(picked?.year === l.year ? null : l.year)}
                title={`${l.year}: ${formatDecimal(l.area_ha, 1)} га`}
              >
                {(isPeak || share >= 22) && (
                  <span className="yloss__value">{formatArea(Math.round(l.area_ha))} га</span>
                )}
              </button>
              <span className="yloss__year">{l.year}</span>
            </div>
          );
        })}

        <div
          className={`yloss__callout ${calloutLeft < 30 ? "yloss__callout--flip" : ""}`.trim()}
          style={{ left: `${calloutLeft}%` }}
        >
          <span className="yloss__share tabular">{formatDecimal(peakShare, 0)} %</span>
          <span className="yloss__of">ряда пришлось на {peak.year} год</span>
          <i className="yloss__leader" aria-hidden="true" />
        </div>
      </div>
    </div>
  );
}
