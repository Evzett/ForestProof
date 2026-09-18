import { useState } from "react";
import { Link } from "react-router-dom";
import { Card, ClaimPill, LevelPill, formatNumber } from "../../components/ui";
import { AddPlotButton, PageHead } from "../../components/AppShell";
import { useWizard } from "../../components/Wizard";
import {
  CALCULATIONS,
  CLAIM_CHECK,
  DATA_COMPLETENESS,
  FEED,
  PROJECTS,
  PROVENANCE,
  SUMMARY,
  WATCHLIST,
} from "../../data/mock";
import "./Sections.css";

/* Территории, Наблюдение, Расчёты, Методика.
   Требования FR-66 — FR-78. */

/* ================= Территории ================= */
export function Territories() {
  const { open } = useWizard();
  const own = PROJECTS.filter((p) => p.mode === "territory_only");

  return (
    <>
      <PageHead
        title="Территории"
        subtitle="Свои участки без зарегистрированного проекта: скрининг площадки, оценка пригодности, наблюдение"
        action={<AddPlotButton />}
      />

      <div className="terr-grid">
        {own.map((p) => (
          <Card key={p.project_id} className="terr">
            <div className="terr__map">
              <img src={p.preview_path} alt="" />
              <span className="terr__badge">без проекта</span>
            </div>
            <h3 className="terr__name">{p.name}</h3>
            <p className="terr__meta">
              {formatNumber(p.area_ha)} га · биомасса {p.agb_t_ha} ± {p.agb_sd_t_ha} т/га
            </p>
            <div className="terr__row">
              <span>уязвимость</span>
              <LevelPill level={p.vulnerability_level} />
            </div>
            <div className="terr__row">
              <span>пожарная экспозиция</span>
              <LevelPill level={p.fire_exposure} />
            </div>
            <p className="terr__source">граница: {p.boundary_source}</p>
            <Link to={`/app/plot/${p.project_id}`} className="terr__open">
              открыть →
            </Link>
          </Card>
        ))}

        <div className="terr terr--add">
          <span className="terr__plus">+</span>
          <b>Добавить участок</b>
          <p>Загрузите GeoJSON или Shapefile, обведите полигон на карте или введите координаты</p>
          <button className="btn btn--dark" type="button" onClick={() => open()}>
            <span>Начать</span>
          </button>
        </div>
      </div>

      <Card title="Чем территория отличается от проекта">
        <p className="ov-note" style={{ marginTop: 0 }}>
          У территории нет зарегистрированного проекта, поэтому заявлять нечего: вкладка сверки
          не считается и не показывается. Всё остальное работает одинаково — покров по годам,
          биомасса, нарушения, уязвимость, экономика. В экономическом сценарии пользователь сам
          задаёт ожидаемый объём эффекта и цену, и на экране подписано, что допущения его, а не
          проекта.
        </p>
      </Card>
    </>
  );
}

/* ================= Наблюдение ================= */
export function Monitoring() {
  const [watched, setWatched] = useState(WATCHLIST);

  const notWatched = PROJECTS.filter((p) => !watched.some((w) => w.project_id === p.project_id));

  const add = () => {
    const next = notWatched[0];
    if (!next) return;
    setWatched((prev) => [
      ...prev,
      {
        project_id: next.project_id,
        name: next.name,
        subtitle: next.subtitle,
        last_check: "только что",
        new_events: 0,
        recent_loss: next.recent_loss_ha ? `${next.recent_loss_ha} га за 30 дней` : "нет",
        status: next.vulnerability_level === "low" ? "quiet" : "attention",
      },
    ]);
  };

  return (
    <>
      <PageHead
        title="Наблюдение"
        subtitle="Что изменилось на отслеживаемых участках с прошлой проверки"
        action={
          <button className="add-btn" type="button" onClick={add} disabled={notWatched.length === 0}>
            <span aria-hidden="true">+</span> добавить в наблюдение
          </button>
        }
      />

      <div className="banner">
        <b>С 1 марта 2027</b>
        <span>
          обращение к счёту резервирования становится регуляторной процедурой. Основание для него
          придётся подтверждать документально — регулярное наблюдение перестаёт быть добровольным.
        </span>
      </div>

      <Card
        title="Отслеживаемые участки"
        note={`${watched.length} из ${watched.length} проверены сегодня`}
        className="mb20"
      >
        {watched.length === 0 ? (
          <p className="ov-note" style={{ marginTop: 0 }}>
            Ни одного участка не отслеживается. Добавьте участок, чтобы видеть, что на нём
            изменилось между отчётами.
          </p>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>участок</th>
                <th>последняя проверка</th>
                <th className="num">новых событий</th>
                <th>свежие нарушения</th>
                <th>статус</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {watched.map((w) => (
                <tr key={w.project_id}>
                  <td>
                    <span className="tbl__name">
                      <Link to={`/app/plot/${w.project_id}`}>
                        <b>{w.name}</b>
                      </Link>
                      <span>{w.subtitle}</span>
                    </span>
                  </td>
                  <td style={{ color: "var(--c-muted-alt)" }}>{w.last_check}</td>
                  <td className="num" style={{ fontSize: 17, fontWeight: 600 }}>
                    {w.new_events}
                  </td>
                  <td>{w.recent_loss}</td>
                  <td>
                    {w.status === "attention" ? (
                      <span className="lvl lvl--high">требует внимания</span>
                    ) : (
                      <span className="lvl lvl--low">без изменений</span>
                    )}
                  </td>
                  <td>
                    <button
                      className="link-btn"
                      type="button"
                      onClick={() =>
                        setWatched((prev) => prev.filter((x) => x.project_id !== w.project_id))
                      }
                    >
                      убрать
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="Лента событий" note="все отслеживаемые участки">
        <ul className="feed">
          {FEED.map((f, i) => (
            <li key={i}>
              <span className="feed__date">{f.date}</span>
              <span className="feed__body">
                <b>{f.name}</b>
                <span>{f.text}</span>
              </span>
              <span className={`lvl lvl--${f.level}`}>
                {f.kind === "disturbance" ? "нарушение" : f.kind === "data" ? "данные" : "пересчёт"}
              </span>
            </li>
          ))}
        </ul>
        <p className="ov-note">
          Уведомления по почте и подписки на участки — следующий шаг, в прототипе не реализованы.
        </p>
      </Card>
    </>
  );
}

/* ================= Расчёты ================= */
function downloadCalc(calcId: string) {
  const payload = {
    calc_id: calcId,
    methodology_version: "1.0",
    algorithm_version: "calc-0.1",
    input_hash: PROVENANCE.input_hash,
    claim_check: CLAIM_CHECK,
    summary: SUMMARY,
    provenance: PROVENANCE,
    data_completeness: DATA_COMPLETENESS,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${calcId}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export function Calculations() {
  const [compare, setCompare] = useState<string[]>([]);

  const toggle = (id: string) =>
    setCompare((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 2 ? [...prev, id] : [prev[1], id]
    );

  const [a, b] = compare.map((id) => CALCULATIONS.find((c) => c.calc_id === id)!);
  const sameInput = a && b && a.input_hash === b.input_hash;

  return (
    <>
      <PageHead
        title="Расчёты"
        subtitle="Каждый расчёт сохраняется целиком: версия методики, версия алгоритма, хеш входных данных, даты снимков"
      />

      {compare.length === 2 && (
        <div className="selbar">
          <b>
            {a.calc_id} ↔ {b.calc_id}
          </b>
          <span className="selbar__hint">
            {sameInput
              ? "хеш входных данных совпадает — разницу даёт версия методики"
              : "входные данные разные, расчёты напрямую не сравнимы"}
          </span>
          <span className="selbar__spacer" />
          <button className="btn btn--lime" type="button" onClick={() => setCompare([])}>
            <span>Сбросить</span>
          </button>
        </div>
      )}

      <Card className="mb20">
        <div className="tbl__scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: 40 }} />
                <th>расчёт</th>
                <th>дата и время</th>
                <th>участок</th>
                <th>методика / алгоритм</th>
                <th>статус сверки</th>
                <th>хеш входных данных</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {CALCULATIONS.map((c) => (
                <tr key={c.calc_id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={compare.includes(c.calc_id)}
                      onChange={() => toggle(c.calc_id)}
                      aria-label={`сравнить ${c.calc_id}`}
                    />
                  </td>
                  <td>
                    <b>{c.calc_id}</b>
                  </td>
                  <td style={{ color: "var(--c-muted-alt)" }}>{c.calculated_at}</td>
                  <td>{c.plot_name}</td>
                  <td style={{ color: "var(--c-muted-alt)" }}>
                    {c.methodology_version} / {c.algorithm_version}
                  </td>
                  <td>
                    <ClaimPill status={c.claim_status} />
                  </td>
                  <td style={{ color: "var(--c-muted-alt)" }}>{c.input_hash}</td>
                  <td>
                    <span className="calc-actions">
                      <Link to={`/app/plot/${c.project_id}`}>открыть</Link>
                      <button
                        className="link-btn"
                        type="button"
                        onClick={() => downloadCalc(c.calc_id)}
                      >
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
          Отметьте два расчёта, чтобы сравнить их входные данные. Выгрузка в JSON нужна, чтобы
          расчёт можно было перепроверить независимо, не доверяя нашему интерфейсу.
        </p>
      </Card>

      <Card title="Зачем журнал">
        <div className="calc-why">
          <p className="ov-note" style={{ marginTop: 0 }}>
            Расчёт открывается по идентификатору и даёт те же числа: параметры сценария
            сохраняются внутри расчёта, а не в браузере. Одинаковый хеш у CALC-0147 и CALC-0148
            означает, что входные данные не менялись — расхождение в результате даёт разница
            версий методики, и это видно. Выгрузка в JSON позволяет перепроверить расчёт
            независимо, не доверяя нашему интерфейсу.
          </p>
          <dl className="calc-glossary">
            <div>
              <dt>версия методики</dt>
              <dd>какие формулы и пороги действовали</dd>
            </div>
            <div>
              <dt>версия алгоритма</dt>
              <dd>какой код считал</dd>
            </div>
            <div>
              <dt>хеш входных данных</dt>
              <dd>менялись ли исходники</dd>
            </div>
            <div>
              <dt>даты снимков</dt>
              <dd>на что именно смотрели</dd>
            </div>
          </dl>
        </div>
      </Card>
    </>
  );
}

/* ================= Методика ================= */
const SECTIONS = [
  { id: "what", label: "Что мы считаем" },
  { id: "formulas", label: "Формулы и коэффициенты" },
  { id: "sources", label: "Источники данных" },
  { id: "check", label: "Как устроена сверка" },
  { id: "not", label: "Чего мы не считаем" },
  { id: "limits", label: "Границы применимости" },
];

const WHAT = [
  [
    "Лесопокрытая площадь",
    "Годовой ряд за 10 лет по Hansen Global Forest Change и Dynamic World. Год без валидных наблюдений остаётся в ряду пустым, а не подменяется соседним.",
  ],
  [
    "Надземная биомасса",
    "ESA CCI Biomass, всегда вместе с погрешностью продукта. Если год продукта отличается от года расчёта, это указывается как допущение.",
  ],
  [
    "События нарушений",
    "Потери покрова по годам с площадью. Пересечение с данными о гарях MODIS даёт пожарные признаки. Отсутствие признаков не означает рубку.",
  ],
  [
    "Уязвимость территории",
    "Относительный скрининг по истории пожаров, доле потерь, рельефу, близости дорог и климату. Категория с драйверами, без числовой вероятности.",
  ],
];

const FORMULAS = [
  ["C = AGB × 0,47", "углеродная доля, IPCC"],
  ["CO₂ = C × 44/12", "молярное отношение"],
  ["Δ = (заявл. − набл.) / заявл. × 100 %", "порог существенности ±10 %"],
  ["выручка = Q × P × (1 − h)", "Q и h задаются, не выводятся"],
];

const NOT = [
  "базовые линии и дополнительность",
  "объём единиц к выпуску",
  "процент резервирования и буфер",
  "вердикт о добросовестности",
];

export function Methodology() {
  const [active, setActive] = useState("what");

  const go = (id: string) => {
    setActive(id);
    /* Плавная прокрутка игнорируется, если у пользователя отключены анимации
       или браузер их не поддерживает — тогда прыгаем сразу, а не стоим на месте. */
    const smooth = window.matchMedia?.("(prefers-reduced-motion: no-preference)").matches ?? false;
    document
      .getElementById(id)
      ?.scrollIntoView(smooth ? { behavior: "smooth", block: "start" } : { block: "start" });
  };

  return (
    <>
      <PageHead
        title="Методика"
        subtitle="Что именно считаем, по каким формулам, из каких источников — и чего не считаем принципиально"
      />

      <div className="meth">
        <Card className="meth__toc">
          <ul>
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className={active === s.id ? "is-on" : ""}
                  onClick={() => go(s.id)}
                >
                  {s.label}
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <div className="meth__body">
          <div id="what">
            <Card title="Что мы считаем" className="mb20">
              <dl className="meth__list">
                {WHAT.map(([t, d]) => (
                  <div key={t}>
                    <dt>{t}</dt>
                    <dd>{d}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          </div>

          <div className="meth__pair">
            <div id="formulas">
              <Card title="Формулы" note="в конфигурации, не в коде">
                <dl className="meth__formulas">
                  {FORMULAS.map(([f, d]) => (
                    <div key={f}>
                      <dt>{f}</dt>
                      <dd>{d}</dd>
                    </div>
                  ))}
                </dl>
              </Card>
            </div>

            <div id="not">
              <Card tone="dark" title="Чего мы не считаем">
                <ul className="meth__not">
                  {NOT.map((n) => (
                    <li key={n}>
                      <span aria-hidden="true">✕</span> {n}
                    </li>
                  ))}
                </ul>
                <p className="ov-note" style={{ color: "#b9c2ae" }}>
                  Это не пробелы, а осознанные границы метода. Заявленный эффект вида
                  предотвращённых выбросов помечается несопоставимым при любых данных.
                </p>
              </Card>
            </div>
          </div>

          <div id="sources">
            <Card title="Источники данных" className="mb20">
              <dl className="meth__formulas">
                {PROVENANCE.datasets.map((d) => (
                  <div key={d.name}>
                    <dt style={{ fontSize: 13 }}>{d.name}</dt>
                    <dd>{d.version}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          </div>

          <div id="check">
            <Card title="Как устроена сверка" className="mb20">
              <p className="ov-note" style={{ marginTop: 0 }}>
                Сверка ведётся на дату отчётности проекта, а не на сегодня: наблюдение берётся
                ближайшее валидное к этой дате. Иначе расхождение вылезет у всех проектов просто
                оттого, что прошло несколько лет. События, случившиеся после даты отчётности,
                выносятся в отдельный блок и на статус не влияют — отчёт физически не мог их
                содержать. Площадь сравнивается только с одноимённой величиной, а заявленный
                эффект вида предотвращённых выбросов всегда помечается несопоставимым.
              </p>
            </Card>
          </div>

          <div id="limits">
            <Card title="Границы применимости">
              <p className="ov-note" style={{ marginTop: 0 }}>
                Оценка уязвимости обучена на бореальных лесах Сибири и на другие зоны не
                переносится. Продукт биомассы имеет разрешение 100 метров, поэтому для участков
                меньше нескольких сотен гектаров погрешность становится сопоставимой со значением.
                Оптические данные не работают в полярную ночь и при устойчивой облачности — в такие
                периоды система отвечает «данных недостаточно» вместо результата.
              </p>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
