import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Card, Checkbox, formatDecimal, formatNumber, plural } from "../../components/ui";
import { PageHead } from "../../components/AppShell";
import { AREAS, ASSUMPTIONS, DATASETS, EVENTS, PARAMETERS, YEARS } from "../../data/case";
import type { Area, Period } from "../../data/case";
import { useAiSummary } from "../../data/aiSummary";
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
          <button className="btn btn--lime btn--inline" type="button" onClick={() => setCompare([])}>
            <span>Сбросить</span>
          </button>
        </div>
      )}

      {pair && (
        <Card title="Построчное сравнение" className="mb20">
          <div className="tbl__scroll tbl__scroll--tall">
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
        <div className="tbl__scroll tbl__scroll--tall">
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

/* ================= Что изменилось с прошлого расчёта ================= */

/* Раньше здесь было «Наблюдение»: список тех же участков с лентой событий.
   Он не отвечал ни на один вопрос пользователя — что именно наблюдаем и
   что с этим делать. Постановка кейса такого раздела не требует вовсе.

   Теперь раздел отвечает на один вопрос: отчёт, который у меня на руках,
   ещё действителен? Для этого сохранённый расчёт сравнивается с тем, что
   есть в наборе сейчас: появились ли новые годы наблюдений, нашлись ли
   новые подтверждённые события, менялись ли версии продуктов. KAN-58. */

type ChangeWeight = "material" | "none";

type Change = {
  title: string;
  detail: string;
  weight: ChangeWeight;
};

const LATEST_YEAR = YEARS[YEARS.length - 1];

/* Год события берётся из ранней границы интервала: продукт гарей даёт дату
   с погрешностью, и поздняя граница может увести событие в следующий год. */
function eventYear(e: (typeof EVENTS)[number]): number {
  return Number(e.date_min.slice(0, 4));
}

function changesSince(entry: Entry): Change[] {
  const changes: Change[] = [];
  const { area, period } = entry;

  if (period.year_end < LATEST_YEAR) {
    changes.push({
      title: "появились новые годы наблюдений",
      detail: `расчёт заканчивается ${period.year_end}, а карты биомассы в наборе есть по ${LATEST_YEAR} включительно: ${period.year_end + 1}—${LATEST_YEAR} в отчёт не вошли`,
      weight: "material",
    });
  }

  const newEvents = EVENTS.filter(
    (e) => e.aoi_id === area.aoi_id && eventYear(e) > period.year_end
  );
  for (const e of newEvents) {
    changes.push({
      title: "в продукте гарей нашлось событие после расчёта",
      /* Оценка неопределённости даты есть только у событий набора.
         У найденных нами её нет, и «0—0 дней» выдало бы отсутствие
         оценки за точную дату. */
      detail:
        `${e.date_min} — ${e.date_max}: ${e.cause_supported}; ` +
        `затронуто ${e.burned_pixels} из ${e.all_pixels} пикселей` +
        (e.uncertainty_days[1] > 0
          ? `, неопределённость даты ${e.uncertainty_days[0]}—${e.uncertainty_days[1]} дней`
          : ""),
      weight: "material",
    });
  }

  const lateLoss = area.cover_loss.filter((l) => l.year > period.year_end && l.area_ha > 0);
  const lateLossHa = lateLoss.reduce((s, l) => s + l.area_ha, 0);
  if (lateLoss.length > 0) {
    /* Горизонты продуктов не совпадают: Hansen доходит до 2025, карты
       биомассы — до 2024. Потерю за 2025 пересчёт не покроет, и об этом
       нужно сказать, иначе кнопка обещает больше, чем делает. */
    const beyond = lateLoss.filter((l) => l.year > LATEST_YEAR).map((l) => l.year);
    changes.push({
      title: "после расчёта зафиксирована потеря древесного покрова",
      detail:
        `${formatDecimal(lateLossHa, 1)} га за ${lateLoss.map((l) => l.year).join(", ")} по Hansen. ` +
        "Это снижение покрова, а не установленная вырубка: причину продукт не определяет" +
        (beyond.length > 0
          ? `. Потеря за ${beyond.join(", ")} в пересчёт не войдёт: карты биомассы заканчиваются ${LATEST_YEAR} годом`
          : ""),
      weight: "material",
    });
  }

  /* Версии источников сравниваются честно: в наборе одна версия каждого
     продукта, и подставлять несуществующее обновление нельзя. Строка
     остаётся — пользователю важно видеть, что это проверено. */
  changes.push({
    title: "версии продуктов не менялись",
    detail: DATASETS.map((d) => `${d.name} — ${d.version}`).join("; "),
    weight: "none",
  });

  return changes;
}

/* Пересчёт — это тот же участок с концом периода на последнем доступном
   годе. Хеш входа считается той же функцией, что и в журнале: если он
   совпал, пересчитывать нечего, и это видно, а не заявлено. */
function recalcTarget(entry: Entry) {
  const start = entry.period.year_start;
  const end = LATEST_YEAR;
  const period = entry.area.periods.find((p) => p.year_start === start && p.year_end === end);
  return {
    start,
    end,
    period,
    available: Boolean(period),
    hash: period ? inputHash(entry.area, period) : null,
  };
}

export function Monitoring() {
  const journal = useMemo(buildJournal, []);

  /* Какие расчёты пересчитаны в этом сеансе. Сам пересчёт мгновенный:
     все пары лет посчитаны сервисом заранее, здесь берётся готовая. Но
     заменять сохранённый результат новым нельзя — тогда пропадёт то,
     ради чего раздел и нужен: видно должно быть оба числа сразу. */
  const [recalculated, setRecalculated] = useState<Set<string>>(new Set());
  const recalc = (calcId: string) =>
    setRecalculated((done) => new Set(done).add(calcId));
  /* Какой расчёт открыт подробно. Раздел отвечает на вопрос про
     конкретный участок, и заставлять пролистывать одиннадцать чужих
     карточек ради своей — значит прятать ответ. */
  const [opened, setOpened] = useState<string | null>(null);
  const [onlyStale, setOnlyStale] = useState(true);

  /* По одному сохранённому расчёту на участок — самому раннему по концу
     периода. Он и есть «прошлый расчёт»: остальные строки журнала уже
     новее и отвечают на тот же вопрос дважды. */
  const saved = useMemo(() => {
    const byArea = new Map<string, Entry>();
    for (const e of journal) {
      const kept = byArea.get(e.area.aoi_id);
      if (!kept || e.period.year_end < kept.period.year_end) byArea.set(e.area.aoi_id, e);
    }
    return [...byArea.values()];
  }, [journal]);

  const rows = useMemo(
    () =>
      saved.map((entry) => {
        const changes = changesSince(entry);
        return {
          entry,
          changes,
          material: changes.filter((c) => c.weight === "material"),
          target: recalcTarget(entry),
        };
      }),
    [saved]
  );

  const stale = rows.filter((r) => r.material.length > 0);

  /* Справку модель излагает сразу при открытии раздела — так же, как на
     обзоре, участке и в сравнении. Кнопка осталась как «пересобрать». */
  const {
    ai,
    note: aiNote,
    busy: asking,
    refresh: askModel,
  } = useAiSummary(`monitoring:${stale.length}/${rows.length}`, () => ({
    "раздел": "устаревание сохранённых расчётов",
    "сохранённых расчётов": rows.length,
    "стоит повторить": stale.length,
    "почему стоит повторить": stale.length
      ? "во входных данных появились изменения, влияющие на результат"
      : null,
    "участки, где расчёт устарел": stale.map((r) => r.entry.area.name),
    "ничего не пересчитывается само": true,
  }));

  /* По умолчанию открыт первый устаревший: именно он и есть повод
     зайти в этот раздел. */
  const shown = onlyStale && stale.length > 0 ? stale : rows;
  const current = shown.find((r) => r.entry.calc_id === opened) ?? shown[0];

  return (
    <>
      <PageHead
        title="Что изменилось с прошлого расчёта"
        subtitle="Сохранённый расчёт сравнивается с тем, что есть в наборе сейчас: новые годы наблюдений, новые подтверждённые события, версии продуктов"
      />

      <div className="banner">
        <b>
          {stale.length === 0
            ? "Все сохранённые расчёты актуальны"
            : `${stale.length} из ${rows.length} ${plural(rows.length, ["расчёта", "расчётов", "расчётов"])} стоит повторить`}
        </b>
        <span>
          Обязательная часть кейса заканчивается отчётом по запросу. Этот раздел нужен после него:
          он показывает владельцу проекта и инвестору, что отчёт устарел, не заставляя перечитывать
          его целиком. Ничего не пересчитывается само — решение остаётся за пользователем.
        </span>
      </div>

      <Card className="mon-summary mb20">
        <div className="ov-summary__head">
          <h2 className="card__title">Коротко по разделу</h2>
          <span className="lvl lvl--outline">
            {ai ? "изложено моделью" : asking ? "модель отвечает…" : "собрано шаблоном"}
          </span>
          <span className="ov-summary__spacer" />
          <button
            className="btn btn--dark btn--inline"
            type="button"
            onClick={askModel}
            disabled={asking}
          >
            {asking ? "модель отвечает…" : "пересобрать"}
          </button>
        </div>
        <p className="mon-summary__text">
          {ai
            ? ai.text
            : stale.length === 0
              ? "Все сохранённые расчёты опираются на те же входные данные, что лежат в наборе сейчас. Повторять их незачем."
              : `Из ${rows.length} сохранённых расчётов ${stale.length} опираются на устаревшие входные данные: в наборе появились годы наблюдений, которых в отчёт не вошли. Пересчёт даст другой хеш входа, а значит и другой отчёт.`}
        </p>
        <p className="ov-note">
          {ai
            ? `текст изложен моделью ${ai.model}; числа посчитаны сервисом и сверены с ответом`
            : "собрано шаблоном из посчитанного, без языковой модели"}
          {aiNote && ` · модель не подключилась: ${aiNote}`}
        </p>
      </Card>

      <Card className="mb20">
        <div className="ov-summary__head">
          <h2 className="card__title">Сохранённые расчёты</h2>
          <span className="ov-summary__spacer" />
          {stale.length > 0 && stale.length < rows.length && (
            <button
              className="filter"
              type="button"
              onClick={() => setOnlyStale((v) => !v)}
            >
              {onlyStale ? `показать все ${rows.length}` : `только устаревшие (${stale.length})`}
            </button>
          )}
        </div>

        <div className="tbl__scroll">
          <table className="tbl mon-table">
            <thead>
              <tr>
                <th>участок</th>
                <th>период</th>
                <th className="num">результат</th>
                <th className="num">единицы</th>
                <th>состояние</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((row) => (
                <tr
                  key={row.entry.calc_id}
                  className={
                    current?.entry.calc_id === row.entry.calc_id ? "mon-row mon-row--on" : "mon-row"
                  }
                  onClick={() => setOpened(row.entry.calc_id)}
                >
                  <td>{row.entry.area.name}</td>
                  <td className="tabular">
                    {row.entry.period.year_start}—{row.entry.period.year_end}
                  </td>
                  <td className="num tabular">
                    {formatNumber(Math.round(row.entry.period.e_tco2e))}
                  </td>
                  <td className="num tabular">
                    {row.entry.period.units === null ? "—" : row.entry.period.units}
                  </td>
                  <td>
                    <span className={`lvl lvl--${row.material.length > 0 ? "low" : "none"}`}>
                      {row.material.length > 0 ? "стоит пересчитать" : "актуален"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="ov-note">
          Нажмите строку, чтобы посмотреть, что именно изменилось во входных данных этого
          расчёта. Ничего не пересчитывается само.
        </p>
      </Card>

      <div className="mon-list">
      {(current ? [current] : []).map(({ entry, changes, material, target }) => (
        <Card
          key={entry.calc_id}
          title={entry.area.name}
          note={`${entry.calc_id} · вход ${entry.input_hash.slice(0, 12)}`}
          className="mb20"
        >
          <dl className="kv">
            <div>
              <dt>сохранённый расчёт</dt>
              <dd>
                {entry.period.year_start}—{entry.period.year_end} ·{" "}
                {formatNumber(Math.round(entry.period.e_tco2e))} т CO₂-экв. ·{" "}
                {entry.period.units === null ? "единицы недоступны" : `${entry.period.units} ед.`}
              </dd>
            </div>
            <div>
              <dt>вывод</dt>
              <dd>
                {material.length === 0
                  ? "пересчёт даст тот же результат: входные данные не изменились"
                  : `стоит пересчитать — ${plural(material.length, ["изменение", "изменения", "изменений"])} во входных данных`}
              </dd>
            </div>
          </dl>

          <ul className="feed" style={{ marginTop: 14 }}>
            {changes.map((c) => (
              <li key={c.title + c.detail}>
                <span className="feed__body">
                  <b>{c.title}</b>
                  <span>{c.detail}</span>
                </span>
                <span className={`lvl lvl--${c.weight === "material" ? "low" : "none"}`}>
                  {c.weight === "material" ? "влияет на результат" : "без изменений"}
                </span>
              </li>
            ))}
          </ul>

          {material.length > 0 && target.available && target.period && (
            <>
              {recalculated.has(entry.calc_id) ? (
                <div className="mon-recalc">
                  <div className="mon-recalc__head">
                    <b>
                      пересчёт за {target.start}—{target.end}
                    </b>
                    <span className="lvl lvl--low">готово</span>
                  </div>
                  <dl className="kv">
                    <div>
                      <dt>результат</dt>
                      <dd className="tabular">
                        {formatNumber(Math.round(target.period.e_tco2e))} т CO₂-экв.{" "}
                        <small>
                          было {formatNumber(Math.round(entry.period.e_tco2e))}
                        </small>
                      </dd>
                    </div>
                    <div>
                      <dt>потенциальные единицы</dt>
                      <dd className="tabular">
                        {target.period.units === null ? "недоступны" : target.period.units}
                        {target.period.reason ? ` · ${target.period.reason}` : ""}
                      </dd>
                    </div>
                    <div>
                      <dt>хеш входных данных</dt>
                      <dd className="tabular">
                        {target.hash?.slice(0, 12)} <small>вместо {entry.input_hash.slice(0, 12)}</small>
                      </dd>
                    </div>
                  </dl>
                  <div className="report-actions">
                    <Link
                      className="btn btn--outline"
                      to={`/app/area/${entry.area.aoi_id}?start=${target.start}&end=${target.end}`}
                    >
                      <span>Открыть полный отчёт →</span>
                    </Link>
                  </div>
                  <p className="ov-note">
                    Сохранённый расчёт остался на месте: раздел показывает, что изменилось, а
                    не подменяет прежний отчёт новым.
                  </p>
                </div>
              ) : (
                <div className="report-actions">
                  <button
                    className="btn btn--dark"
                    type="button"
                    onClick={() => recalc(entry.calc_id)}
                  >
                    <span>
                      Пересчитать за {target.start}—{target.end}
                    </span>
                  </button>
                </div>
              )}
            </>
          )}

          {material.length > 0 && target.available && target.hash && !recalculated.has(entry.calc_id) && (
            <p className="ov-note">
              Хеш входных данных после пересчёта: {target.hash.slice(0, 12)} вместо{" "}
              {entry.input_hash.slice(0, 12)} — это другой вход, а значит и другой отчёт.
            </p>
          )}

          {material.length > 0 && !target.available && (
            <p className="ov-note">
              Пересчёт за {target.start}—{target.end} в наборе не подготовлен: пару состояний для
              этих лет получить не из чего. Пересчитать можно на странице участка за доступный
              период.
            </p>
          )}
        </Card>
      ))}
      </div>

      <Card title="Чего этот раздел не делает">
        <ul className="drivers">
          <li>
            Не следит за участком сам: набор данных локальный и воспроизводимый, новые версии
            продуктов появляются при обновлении набора, а не в фоне.
          </li>
          <li>Не рассылает уведомления по почте — подписки в прототипе не реализованы.</li>
          <li>
            Не пересчитывает автоматически: пересчёт меняет число в отчёте, и это должно быть
            осознанным действием пользователя.
          </li>
        </ul>
      </Card>
    </>
  );
}

export { Methodology } from "./Methodology";
