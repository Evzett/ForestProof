import { useMemo } from "react";
import { Link } from "react-router-dom";
import { Card, LevelPill, plural } from "./ui";
import { AREAS, MODEL, modelFor } from "../data/case";
import "./RiskSummary.css";

/* Сводка по рискам для обзора — KAN-35.

   На карточке участка категория отвечает на вопрос «что с этим
   участком». Здесь другой вопрос: «что с набором в целом» — сколько
   участков в какой категории и какие признаки срабатывают чаще
   остальных. На четырёх участках это читалось как четыре плитки, на
   десяти уже как распределение.

   Чего здесь нет и не будет.

   Числовой вероятности — ограничение Ф-02. Только категория и счёт
   участков. Шкалы 0—100 и цветового градиента, читающегося как число,
   тоже нет: три ступени, три цвета, и между ними ничего.

   Влияния на расчёт. Этот блок ничего не меняет в Q, UNC, B и V —
   связи нет в коде, и это закреплено тестом
   tests/test_stability_does_not_touch_units.py. */

const LEVELS = ["high", "medium", "low"] as const;

const LEVEL_TITLE: Record<(typeof LEVELS)[number], string> = {
  high: "высокая",
  medium: "средняя",
  low: "низкая",
};

export default function RiskSummary() {
  const stats = useMemo(() => {
    const byLevel: Record<string, typeof AREAS> = { high: [], medium: [], low: [] };
    const drivers = new Map<string, number>();

    for (const area of AREAS) {
      const stability = area.stability;
      if (!stability) continue;
      byLevel[stability.level]?.push(area);
      for (const driver of stability.drivers) {
        drivers.set(driver.label, (drivers.get(driver.label) ?? 0) + 1);
      }
    }

    /* Прогноз модели живёт отдельно от правил: у него своё окно
       признаков и свой горизонт. Считаем, на скольких участках он
       вообще получен — отказ тоже ответ, и его число видно. */
    const scored = AREAS.filter((a) => modelFor(a.aoi_id)?.forecast).length;
    const agree = AREAS.filter((a) => {
      const forecast = modelFor(a.aoi_id)?.forecast;
      return forecast && a.stability && forecast.category === a.stability.level;
    }).length;

    return {
      byLevel,
      drivers: [...drivers.entries()].sort((a, b) => b[1] - a[1]),
      counted: AREAS.filter((a) => a.stability).length,
      scored,
      agree,
    };
  }, []);

  const top = stats.drivers[0]?.[1] ?? 1;

  return (
    <Card
      title="Устойчивость результата по набору"
      note={`горизонт 2024—2029 · ${MODEL.method.split(",")[0]}`}
      className="risk"
    >
      <div className="risk__levels">
        {LEVELS.map((level) => {
          const areas = stats.byLevel[level] ?? [];
          return (
            <div key={level} className="risk__level">
              <div className="risk__count tabular">{areas.length}</div>
              <LevelPill level={level} />
              <ul className="risk__names">
                {areas.map((a) => (
                  <li key={a.aoi_id}>
                    <Link to={`/app/area/${a.aoi_id}`}>{a.name}</Link>
                  </li>
                ))}
                {areas.length === 0 && <li className="risk__empty">нет участков</li>}
              </ul>
              <span className="sr-only">{LEVEL_TITLE[level]}</span>
            </div>
          );
        })}
      </div>

      <p className="tile__label risk__subhead">какие признаки срабатывают чаще</p>
      <ul className="risk__drivers">
        {stats.drivers.map(([label, count]) => (
          <li key={label}>
            <span className="risk__driver-name">{label}</span>
            <span className="risk__bar" aria-hidden="true">
              <i style={{ width: `${(count / top) * 100}%` }} />
            </span>
            <span className="risk__driver-count tabular">
              {count} из {stats.counted}
            </span>
          </li>
        ))}
      </ul>

      <p className="ov-note">
        Категория получена пороговыми правилами по шести признакам, посчитанным по тем же
        растрам, что и основной расчёт. Обученная модель даёт прогноз отдельно: он получен на{" "}
        {stats.scored} {plural(stats.scored, ["участке", "участках", "участках"])} из{" "}
        {AREAS.length}, и на {stats.agree}{" "}
        {plural(stats.agree, ["из них совпал", "из них совпали", "из них совпали"])} с правилами.
        Числовой вероятности реверсии здесь нет: на выборке одной природной зоны такая цифра
        обещала бы точность, которой у неё нет. На число потенциальных единиц скрининг не влияет.
      </p>
    </Card>
  );
}
