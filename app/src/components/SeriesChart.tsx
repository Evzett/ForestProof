import { formatDecimal } from "./ui";
import "./SeriesChart.css";

/* Годовой ряд запаса вместе с базовой линией.

   Столбиками этот ряд не читается: запас меняется на проценты, и все
   столбики выходят одной высоты. Линия с собственной шкалой показывает
   и величину, и направление, а заливка между наблюдением и базовой
   линией — это ровно то, из чего потом получается R.

   Год без валидных наблюдений разрывает линию, а не соединяется через
   пропуск: соединить значило бы дорисовать данные, которых нет. */

type Point = { year: number; value: number | null };

const W = 720;
const H = 300;
const PAD = { top: 18, right: 18, bottom: 34, left: 54 };

export default function SeriesChart({
  observed,
  baseline,
  unit = "т C/га",
  observedLabel = "наблюдение",
  baselineLabel = "базовая линия",
}: {
  observed: Point[];
  baseline?: Point[];
  unit?: string;
  observedLabel?: string;
  baselineLabel?: string;
}) {
  const all = [...observed, ...(baseline ?? [])]
    .map((p) => p.value)
    .filter((v): v is number => v !== null);

  if (all.length === 0) {
    return <p className="ov-note">Валидных наблюдений в выбранном периоде нет.</p>;
  }

  const lo = Math.min(...all);
  const hi = Math.max(...all);
  /* Запас в этих рядах меняется на единицы процентов. Шкала от нуля
     сплющила бы всё в прямую, поэтому берём диапазон самих данных
     с запасом — и подписываем ось, чтобы масштаб был виден. */
  const pad = (hi - lo || Math.max(hi * 0.02, 1)) * 0.35;
  const min = lo - pad;
  const max = hi + pad;

  const years = observed.map((p) => p.year);
  const x = (year: number) =>
    PAD.left +
    ((year - years[0]) / Math.max(years[years.length - 1] - years[0], 1)) *
      (W - PAD.left - PAD.right);
  const y = (value: number) =>
    PAD.top + (1 - (value - min) / (max - min)) * (H - PAD.top - PAD.bottom);

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => min + t * (max - min));

  /* Линия рвётся на пропусках: каждый непрерывный кусок — свой path */
  const segments: Point[][] = [];
  let current: Point[] = [];
  for (const p of observed) {
    if (p.value === null) {
      if (current.length) segments.push(current);
      current = [];
    } else {
      current.push(p);
    }
  }
  if (current.length) segments.push(current);

  const path = (pts: Point[]) =>
    pts.map((p, i) => `${i ? "L" : "M"}${x(p.year)} ${y(p.value as number)}`).join(" ");

  const baseValid = (baseline ?? []).filter((p) => p.value !== null);

  /* Заливка между наблюдением и базовой линией — визуальный R */
  /* Подложка под линией наблюдения. Сама по себе она ничего не
     сообщает — это та же линия, только залитая вниз, — но без неё
     график из тонких штрихов на белом читался как чертёж, а не как
     показатель. Поэтому заливка бледная и без подписи. */
  const underlay =
    observed.filter((pp) => pp.value !== null).length > 1
      ? `${path(observed)} L${x(observed[observed.length - 1].year)} ${H - PAD.bottom} L${x(
          observed[0].year
        )} ${H - PAD.bottom} Z`
      : null;

  const band =
    baseValid.length === observed.length && observed.every((p) => p.value !== null)
      ? `${path(observed)} L${x(baseValid[baseValid.length - 1].year)} ${y(
          baseValid[baseValid.length - 1].value as number
        )} ${[...baseValid]
          .reverse()
          .map((p) => `L${x(p.year)} ${y(p.value as number)}`)
          .join(" ")} Z`
      : null;

  const last = observed.filter((p) => p.value !== null).at(-1);
  const lastBase = baseValid.at(-1);
  const above =
    last && lastBase ? (last.value as number) >= (lastBase.value as number) : true;

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Годовой ряд, ${unit}`}>
        <defs>
          <linearGradient id="chart-underlay" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--c-ink)" stopOpacity="0.20" />
            <stop offset="100%" stopColor="var(--c-ink)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line className="chart__grid" x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} />
            <text className="chart__axis" x={PAD.left - 10} y={y(t) + 4} textAnchor="end">
              {formatDecimal(t, 1)}
            </text>
          </g>
        ))}

        {underlay && <path className="chart__underlay" d={underlay} />}

        {band && <path className={`chart__band ${above ? "is-above" : "is-below"}`} d={band} />}

        {baseValid.length > 1 && (
          <path className="chart__baseline" d={path(baseValid)} />
        )}

        {segments.map((seg, i) => (
          <path key={i} className="chart__line" d={path(seg)} />
        ))}

        {observed.map((p) =>
          p.value === null ? (
            <text key={p.year} className="chart__gap" x={x(p.year)} y={H / 2} textAnchor="middle">
              нет данных
            </text>
          ) : (
            <g key={p.year}>
              <circle className="chart__halo" cx={x(p.year)} cy={y(p.value)} r="9" />
              <circle className="chart__dot" cx={x(p.year)} cy={y(p.value)} r="5" />
              <text
                className="chart__value"
                x={x(p.year)}
                y={y(p.value) - 13}
                textAnchor="middle"
              >
                {formatDecimal(p.value, 1)}
              </text>
            </g>
          )
        )}

        {observed.map((p) => (
          <text
            key={`x${p.year}`}
            className="chart__axis"
            x={x(p.year)}
            y={H - 10}
            textAnchor="middle"
          >
            {p.year}
          </text>
        ))}
      </svg>

      <div className="chart__legend">
        <span>
          <i className="chart__key chart__key--line" /> {observedLabel}
        </span>
        {baseValid.length > 0 && (
          <span>
            <i className="chart__key chart__key--base" /> {baselineLabel}
          </span>
        )}
        <span className="chart__scale">
          шкала {formatDecimal(min, 1)} — {formatDecimal(max, 1)} {unit}
        </span>
      </div>
    </div>
  );
}
