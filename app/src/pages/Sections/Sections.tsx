import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Card, Checkbox, formatDecimal, formatNumber } from "../../components/ui";
import { PageHead } from "../../components/AppShell";
import { AREAS, ASSUMPTIONS, DATASETS, EVENTS, PARAMETERS } from "../../data/case";
import type { Area, Period } from "../../data/case";
import "./Sections.css";

/* Журнал расчётов и наблюдение.
   Методика вынесена в отдельный модуль — см. Methodology.tsx. */

/* ================= Журнал расчётов ================= */

type Entry = {
  calc_id: string;
  area: Area;
  period: Period;
  input_hash: string;
};

/* Идентификатор и хеш входа выводятся из самих параметров расчёта:
   одинаковый участок с одинаковым периодом даёт одинаковый хеш, и это
   проверяемо, а не сгенерировано случайно. */
function inputHash(area: Area, period: Period): string {
  const seed = `${area.aoi_id}|${period.year_start}|${period.year_end}|${area.baseline_id}|CCI_V7`;
  let h1 = 0x811c9dc5;
  let h2 = 0x01000193;
  for (let i = 0; i < seed.length; i++) {
    h1 = Math.imul(h1 ^ seed.charCodeAt(i), 0x01000193) >>> 0;
    h2 = Math.imul(h2 + seed.charCodeAt(i) * (i + 1), 0x85ebca6b) >>> 0;
  }
  return `${h1.toString(16).padStart(8, "0")}${h2.toString(16).padStart(8, "0")}`;
}

function buildJournal(): Entry[] {
  const entries: Entry[] = [];
  for (const area of AREAS) {
    for (const period of [area.period_2019_2024, ...area.periods.slice(0, 2)]) {
      entries.push({
        calc_id: `CALC-${area.aoi_id.replace("RU_", "")}-${period.year_start}${period.year_end}`,
        area,
        period,
        input_hash: inputHash(area, period),
      });
    }
  }
  return entries;
}

function downloadCalc(entry: Entry) {
  const payload = {
    calc_id: entry.calc_id,
    input_hash: entry.input_hash,
    methodology_version: "case-v1.0",
    algorithm_version: "calc-1.0",
    area: {
      aoi_id: entry.area.aoi_id,
      name: entry.area.name,
      bbox_wgs84: entry.area.bbox,
      area_ha: entry.area.area_ha,
    },
    period: entry.period,
    parameters: PARAMETERS,
    assumptions: ASSUMPTIONS,
    datasets: DATASETS,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${entry.calc_id}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

export function Calculations() {
  const journal = useMemo(buildJournal, []);
  const [compare, setCompare] = useState<string[]>([]);

  /* Сравнение попарное: журнал отвечает на вопрос «что изменилось между
     этими двумя расчётами». Третья строка ответа не уточняет, поэтому при
     двух отмеченных остальные гасим с объяснением, а не подменяем выбор. */
  const toggle = (id: string) =>
    setCompare((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 2 ? [...prev, id] : prev
    );

  const [a, b] = compare.map((id) => journal.find((e) => e.calc_id === id)!);
  const pair = compare.length === 2;
  const sameInput = pair && a.input_hash === b.input_hash;
  const sameArea = pair && a.area.aoi_id === b.area.aoi_id;

  return (
    <>
      <PageHead
        title="Расчёты"
        subtitle="Каждый расчёт сохраняется целиком: участок, период, версии методики и алгоритма, хеш входных данных, параметры и допущения"
      />

      {pair && (
        <div className="selbar">
          <b>
            {a.calc_id} ↔ {b.calc_id}
          </b>
          <span className="selbar__hint">
            {sameInput
              ? "хеш входных данных совпадает — разницу даёт только версия методики"
              : sameArea
                ? "тот же участок, другой период — результаты не складываются"
                : "разные участки, расчёты напрямую не сравнимы"}
          </span>
          <span className="selbar__spacer" />
          <button className="btn btn--lime" type="button" onClick={() => setCompare([])}>
            <span>Сбросить</span>
          </button>
        </div>
      )}

      {pair && (
        <Card title="Построчное сравнение" className="mb20">
          <div className="tbl__scroll">
            <table className="tbl">
              <thead>
                <tr>
                  <th>показатель</th>
                  <th className="num">{a.calc_id}</th>
                  <th className="num">{b.calc_id}</th>
                  <th className="num">разница</th>
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    ["площадь, га", (e: Entry) => e.period.area_ha, 1],
                    ["запас на начало, т C/га", (e: Entry) => e.period.c_start_t_ha, 2],
                    ["запас на конец, т C/га", (e: Entry) => e.period.c_end_t_ha, 2],
                    ["E, т CO₂-экв.", (e: Entry) => e.period.e_tco2e, 0],
                    ["H, т CO₂-экв.", (e: Entry) => e.period.h_tco2e, 0],
                    ["R, т CO₂-экв.", (e: Entry) => e.period.r_tco2e, 0],
                    ["единицы", (e: Entry) => e.period.units ?? 0, 0],
                  ] as [string, (e: Entry) => number, number][]
                ).map(([label, pick, digits]) => (
                  <tr key={label}>
                    <td>{label}</td>
                    <td className="num">{formatDecimal(pick(a), digits)}</td>
                    <td className="num">{formatDecimal(pick(b), digits)}</td>
                    <td className="num">
                      <b>{formatDecimal(pick(b) - pick(a), digits)}</b>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="ov-note">
            Накопленный результат за длинный период не равен сумме результатов за вложенные
            периоды и не должен с ними складываться — это был бы повторный учёт одного эффекта.
          </p>
        </Card>
      )}

      <Card className="mb20">
        <div className="tbl__scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: 40 }} title="отметьте два расчёта для сравнения">
                  ↔
                </th>
                <th>расчёт</th>
                <th>участок</th>
                <th>период</th>
                <th>методика / алгоритм</th>
                <th className="num">E, т CO₂-экв.</th>
                <th className="num">единицы</th>
                <th>хеш входных данных</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {journal.map((e) => (
                <tr key={e.calc_id}>
                  <td>
                    <Checkbox
                      checked={compare.includes(e.calc_id)}
                      disabled={pair && !compare.includes(e.calc_id)}
                      onChange={() => toggle(e.calc_id)}
                      label={`сравнить ${e.calc_id}`}
                      reason="выбрано два расчёта — снимите отметку с одного"
                    />
                  </td>
                  <td>
                    <b>{e.calc_id}</b>
                  </td>
                  <td>
                    <Link to={`/app/area/${e.area.aoi_id}`}>{e.area.name}</Link>
                  </td>
                  <td style={{ color: "var(--c-muted-alt)" }}>
                    {e.period.year_start}—{e.period.year_end}
                  </td>
                  <td style={{ color: "var(--c-muted-alt)" }}>case-v1.0 / calc-1.0</td>
                  <td className="num">{formatNumber(Math.round(e.period.e_tco2e))}</td>
                  <td className="num">
                    {e.period.units === null ? "—" : formatNumber(e.period.units)}
                  </td>
                  <td style={{ color: "var(--c-muted-alt)", fontSize: 11 }}>{e.input_hash}</td>
                  <td>
                    <span className="calc-actions">
                      <Link to={`/app/area/${e.area.aoi_id}`}>открыть</Link>
                      <button className="link-btn" type="button" onClick={() => downloadCalc(e)}>
                        JSON
                      </button>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="ov-note">
          Отметьте два расчёта, чтобы сравнить их построчно. Выгрузка в JSON нужна, чтобы расчёт
          можно было перепроверить независимо, не доверяя нашему интерфейсу.
        </p>
      </Card>

      <Card title="Зачем журнал">
        <div className="calc-why">
          <p className="ov-note" style={{ marginTop: 0 }}>
            Хеш входных данных выводится из участка, периода, идентификатора базовой линии и
            версии продукта биомассы. Совпадающий хеш означает, что вход не менялся: любая разница
            в результате тогда объясняется версией методики, и это видно. Параметры сценария
            сохраняются внутри расчёта, а не в браузере, поэтому открытый по идентификатору расчёт
            даёт те же числа.
          </p>
          <dl className="calc-glossary">
            <div>
              <dt>версия методики</dt>
              <dd>какие формулы, пороги и вычеты действовали</dd>
            </div>
            <div>
              <dt>версия алгоритма</dt>
              <dd>какой код считал</dd>
            </div>
            <div>
              <dt>хеш входных данных</dt>
              <dd>менялись ли участок, период и версии источников</dd>
            </div>
            <div>
              <dt>допущения</dt>
              <dd>корреляции ошибки, порог покрова, множитель интервала</dd>
            </div>
          </dl>
        </div>
      </Card>
    </>
  );
}

/* ================= Наблюдение ================= */

export function Monitoring() {
  const [watched, setWatched] = useState(() => AREAS.slice(0, 2).map((a) => a.aoi_id));
  const notWatched = AREAS.filter((a) => !watched.includes(a.aoi_id));

  const add = () => {
    if (notWatched.length === 0) return;
    setWatched((prev) => [...prev, notWatched[0].aoi_id]);
  };

  /* Лента строится из данных, а не из выдуманных новостей: событие с
     подтверждением и год крупнейшей потери покрова — это то, что
     действительно есть в наборе. */
  const feed = useMemo(() => {
    const items: { date: string; name: string; text: string; level: string }[] = [];
    for (const e of EVENTS) {
      const area = AREAS.find((a) => a.aoi_id === e.aoi_id)!;
      items.push({
        date: `${e.date_min} — ${e.date_max}`,
        name: area.name,
        text: `${e.cause_supported}; затронуто ${e.burned_pixels} из ${e.all_pixels} пикселей продукта, неопределённость даты ${e.uncertainty_days[0]}—${e.uncertainty_days[1]} дней`,
        level: "high",
      });
    }
    for (const area of AREAS) {
      const top = [...area.cover_loss].sort((a, b) => b.area_ha - a.area_ha)[0];
      if (top) {
        items.push({
          date: String(top.year),
          name: area.name,
          text: `крупнейшая потеря древесного покрова ${formatDecimal(top.area_ha, 1)} га; причина продуктом не определяется`,
          level: top.year >= 2019 ? "medium" : "none",
        });
      }
    }
    return items.sort((a, b) => b.date.localeCompare(a.date));
  }, []);

  return (
    <>
      <PageHead
        title="Наблюдение"
        subtitle="Что известно об изменениях на отслеживаемых участках и чем это подтверждено"
        action={
          <button
            className="add-btn"
            type="button"
            onClick={add}
            disabled={notWatched.length === 0}
          >
            <span aria-hidden="true">+</span> добавить в наблюдение
          </button>
        }
      />

      <div className="banner">
        <b>Наблюдение — дополнительная функция</b>
        <span>
          Обязательная часть кейса заканчивается отчётом по запросу. Слежение за участком между
          расчётами нужно владельцу проекта и инвестору: оно показывает, что изменилось с момента
          последнего отчёта и когда расчёт стоит повторить.
        </span>
      </div>

      <Card
        title="Отслеживаемые участки"
        note={`${watched.length} из ${AREAS.length}`}
        className="mb20"
      >
        {watched.length === 0 ? (
          <p className="ov-note" style={{ marginTop: 0 }}>
            Ни одного участка не отслеживается.
          </p>
        ) : (
          <div className="tbl__scroll">
            <table className="tbl">
              <thead>
                <tr>
                  <th>участок</th>
                  <th className="num">E за 2019—2024</th>
                  <th className="num">потери 2020—2024, га</th>
                  <th>подтверждённое событие</th>
                  <th>единицы</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {watched.map((id) => {
                  const area = AREAS.find((a) => a.aoi_id === id)!;
                  const p = area.period_2019_2024;
                  const loss = area.cover_loss
                    .filter((l) => l.year > 2019 && l.year <= 2024)
                    .reduce((s, l) => s + l.area_ha, 0);
                  const event = EVENTS.find((e) => e.aoi_id === id);
                  return (
                    <tr key={id}>
                      <td>
                        <span className="tbl__name">
                          <Link to={`/app/area/${id}`}>
                            <b>{area.name}</b>
                          </Link>
                          <span>{area.region}</span>
                        </span>
                      </td>
                      <td className="num">{formatNumber(Math.round(p.e_tco2e))}</td>
                      <td className="num">{formatDecimal(loss, 1)}</td>
                      <td>
                        {event ? (
                          <span className="lvl lvl--medium">{event.evidence_type}</span>
                        ) : (
                          <span className="lvl lvl--none">причина не установлена</span>
                        )}
                      </td>
                      <td>
                        {p.units === null ? (
                          <span className="dash">—</span>
                        ) : (
                          <span className="lvl lvl--none">{p.units}</span>
                        )}
                      </td>
                      <td>
                        <button
                          className="link-btn"
                          type="button"
                          onClick={() => setWatched((prev) => prev.filter((x) => x !== id))}
                        >
                          убрать
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Лента событий" note="из данных набора, без выдуманных новостей">
        <ul className="feed">
          {feed.map((f, i) => (
            <li key={i}>
              <span className="feed__date">{f.date}</span>
              <span className="feed__body">
                <b>{f.name}</b>
                <span>{f.text}</span>
              </span>
              <span className={`lvl lvl--${f.level}`}>
                {f.level === "high" ? "подтверждено" : "потеря покрова"}
              </span>
            </li>
          ))}
        </ul>
        <p className="ov-note">
          Уведомления по почте и подписки на участки в прототипе не реализованы. Строка «потеря
          покрова» означает снижение древесного покрова по Hansen, а не установленную вырубку.
        </p>
      </Card>
    </>
  );
}

export { Methodology } from "./Methodology";
