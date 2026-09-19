import type { Area } from "../data/case";
import "./CompareChart.css";

/* Запас углерода по годам для выбранных участков — один график.

   Зачем он здесь. Таблица сравнения отвечает на вопрос «какие числа
   получились», но не на вопрос «как они к этому пришли». Участок, где
   запас ровно падает пять лет подряд, и участок, где он рухнул в один
   год и держится, дают близкий итог за период и совершенно разные
   истории. В таблице это неразличимо, на линии — видно сразу.

   Почему линии, а не столбцы. Величина непрерывная и сравниваются
   формы, а не отдельные значения.

   Чего здесь нет. Диапазона неопределённости: он в разы шире самих
   линий, и залитая им картинка перестала бы отвечать на вопрос о
   форме. Ширина интервала показана в таблице числом — там её и видно
   честно, без попытки нарисовать. */

const LINE_COLORS = [
  "#2e3e28",
  "#7a9b3f",
  "#9c3f66",
  "#5b4a86",
  "#3f7a86",
  "#8a6a3f",
  "#4a7a5b",
  "#86503f",
];

const W = 760;
const H = 250;
const PAD = { top: 16, right: 16, bottom: 28, left: 46 };

export default function CompareChart({
  areas,
  hovered,
  onHover,
}: {
  areas: Area[];
  hovered?: string | null;
  onHover?: (aoiId: string | null) => void;
}) {
  const years = areas[0]?.series.map((p) => p.year) ?? [];
  if (areas.length === 0 || years.length === 0) return null;

  const values = areas.flatMap((a) => a.series.map((p) => p.c_t_ha));
  const min = Math.min(...values);
  const max = Math.max(...values);
  /* Ноль в шкалу не загоняется: запас нигде не близок к нулю, и
     растянутая до него ось сплющила бы все линии в одну полосу. Нижняя
     граница подписана, так что обмана в этом нет. */
  const lo = Math.floor((min - (max - min) * 0.12) / 5) * 5;
  const hi = Math.ceil((max + (max - min) * 0.12) / 5) * 5;

  const x = (year: number) =>
    PAD.left +
    ((year - years[0]) / Math.max(years[years.length - 1] - years[0], 1)) *
      (W - PAD.left - PAD.right);
  const y = (value: number) =>
    PAD.top + (1 - (value - lo) / Math.max(hi - lo, 1)) * (H - PAD.top - PAD.bottom);

  const ticks = [lo, lo + (hi - lo) / 2, hi];

  return (
    <div className="cmpchart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Запас углерода по годам">
        {ticks.map((t) => (
          <g key={t}>
            <line
              className="cmpchart__grid"
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(t)}
              y2={y(t)}
            />
            <text className="cmpchart__tick" x={PAD.left - 8} y={y(t) + 4} textAnchor="end">
              {Math.round(t)}
            </text>
          </g>
        ))}

        {years
          .filter((_, i) => i % 2 === 0 || i === years.length - 1)
          .map((year) => (
            <text key={year} className="cmpchart__tick" x={x(year)} y={H - 8} textAnchor="middle">
              {year}
            </text>
          ))}

        {areas.map((area, index) => {
          const dim = hovered != null && hovered !== area.aoi_id;
          const path = area.series
            .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.year)},${y(p.c_t_ha)}`)
            .join(" ");
          return (
            <g
              key={area.aoi_id}
              className={`cmpchart__line ${dim ? "cmpchart__line--dim" : ""}`.trim()}
              onMouseEnter={() => onHover?.(area.aoi_id)}
              onMouseLeave={() => onHover?.(null)}
            >
              <path d={path} stroke={LINE_COLORS[index % LINE_COLORS.length]} fill="none" />
              {area.series.map((p) => (
                <circle
                  key={p.year}
                  cx={x(p.year)}
                  cy={y(p.c_t_ha)}
                  r={hovered === area.aoi_id ? 3.5 : 2.5}
                  fill={LINE_COLORS[index % LINE_COLORS.length]}
                />
              ))}
            </g>
          );
        })}
      </svg>

      <ul className="cmpchart__legend">
        {areas.map((area, index) => (
          <li
            key={area.aoi_id}
            className={hovered === area.aoi_id ? "cmpchart__legend--on" : ""}
            onMouseEnter={() => onHover?.(area.aoi_id)}
            onMouseLeave={() => onHover?.(null)}
          >
            <i style={{ background: LINE_COLORS[index % LINE_COLORS.length] }} aria-hidden="true" />
            {area.name}
          </li>
        ))}
      </ul>

      <p className="ov-note">
        Запас углерода, т C/га, по годам наблюдений. Шкала не начинается с нуля — иначе
        различия между участками сплющились бы в одну полосу; нижняя граница подписана.
        Диапазон неопределённости здесь не показан: он в разы шире самих линий, и график
        перестал бы отвечать на вопрос о форме.
      </p>
    </div>
  );
}
