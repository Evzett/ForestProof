import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Card,
  CircleBtn,
  ClaimPill,
  ConfidencePill,
  LevelPill,
  WithError,
  formatDecimal,
  formatNumber,
} from "../../components/ui";
import EventDrawer from "../../components/EventDrawer";
import {
  CLAIM_CHECK,
  CONFIDENCE_PARTS,
  COVER_SERIES,
  DATA_COMPLETENESS,
  DISTURBANCE_SERIES,
  EVENTS,
  PROJECTS,
  PROVENANCE,
  SCENARIO,
  SUMMARY,
  VULNERABILITY,
} from "../../data/mock";
import type { DisturbanceEvent, EventType } from "../../types";
import "./Plot.css";

/* Карточка участка. Требования FR-25 — FR-50, FR-83, FR-84.

   Для территории без проекта вкладки сверки нет вовсе — она не показывается
   пустой, а отсутствует: заявлять нечего. */

const TABS = ["Обзор", "Измерение", "Нарушения", "Сверка", "Уязвимость", "Экономика", "Аудит"];

/* Отсутствие пожарных признаков не означает рубку: тип остаётся
   неопределённым, пока нет дополнительных сведений (FR-30). */
const EVENT_LABEL: Record<EventType, string> = {
  fire_supported: "подтверждено пожаром",
  non_fire: "не связано с пожаром",
  vegetation_stress: "стресс растительности",
  unknown: "тип не определён",
};

export default function Plot() {
  const { id } = useParams();
  const plot = PROJECTS.find((p) => p.project_id === id) ?? PROJECTS[0];
  const withProject = plot.mode === "with_project";
  const tabs = withProject ? TABS : TABS.filter((t) => t !== "Сверка");
  const [tab, setTab] = useState(tabs[0]);
  const [event, setEvent] = useState<DisturbanceEvent | null>(null);

  /* Допущения сценария: пользователь их меняет, но дисконт никогда
     не выводится из оценки уязвимости (FR-56). */
  const [price, setPrice] = useState(SCENARIO.default_price);
  const [manualPrice, setManualPrice] = useState(false);
  const [haircut, setHaircut] = useState(SCENARIO.default_haircut_pct);

  const max = Math.max(...DISTURBANCE_SERIES.map((d) => d.area_ha ?? 0), 1);
  const revenue = Math.round(SCENARIO.expected_effect_co2_t_year * price * (1 - haircut / 100));
  const perHa = Math.round(revenue / plot.area_ha);

  const showOverview = tab === "Обзор";

  return (
    <>
      <header className="plot-head">
        <Link to="/app/projects" className="plot-head__back" aria-label="Назад в каталог">
          ←
        </Link>
        <div>
          <h1 className="page-head__title">{plot.name}</h1>
          <p className="page-head__sub">
            {formatNumber(plot.area_ha)} га · {plot.subtitle} · граница: {plot.boundary_source}
          </p>
        </div>
      </header>

      <nav className="tabs">
        {tabs.map((t) => (
          <button
            key={t}
            type="button"
            className={t === tab ? "tabs__item tabs__item--on" : "tabs__item"}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </nav>

      {/* ---------------- Обзор ---------------- */}
      {showOverview && (
        <>
          <div className="plot-row">
            <Card className="plot-map">
              <div className="plot-map__canvas">
                <img src={plot.preview_path} alt="Превью участка" />
                <span className="plot-map__stamp">
                  Sentinel-2 · {DATA_COMPLETENESS.latest_observation_date}
                </span>
              </div>
            </Card>

            <Card className="plot-summary">
              <div className="ov-summary__head">
                <h2 className="card__title">Краткая справка</h2>
                <span className="lvl lvl--low">сгенерировано</span>
                <span className="ov-summary__spacer" />
                <CircleBtn glyph="⟳" />
              </div>
              <p className="ov-summary__text">{SUMMARY.text}</p>
              <div className="ov-summary__foot">
                <span>источник:</span>
                <span className="chip">{plot.calc_id}</span>
                <span>· только пересказ посчитанного</span>
              </div>
            </Card>
          </div>

          <div className="plot-tiles">
            <Card>
              <span className="tile__label">лесопокрытая площадь</span>
              <div className="plot-tiles__value tabular">
                {formatNumber(476210)} <small>га</small>
              </div>
              <span className="tile__note">−3,1 % за период наблюдения</span>
            </Card>
            <Card>
              <span className="tile__label">биомасса</span>
              <div className="plot-tiles__value">
                <WithError value={plot.agb_t_ha} error={plot.agb_sd_t_ha} /> <small>т/га</small>
              </div>
              <span className="tile__note">ESA CCI Biomass v6, год продукта 2022</span>
            </Card>
            <Card tone="dark">
              <span className="tile__label" style={{ color: "#b9c2ae" }}>
                эквивалент запаса CO₂
              </span>
              <div className="plot-tiles__value tabular" style={{ color: "var(--c-lime)" }}>
                110,9 <small style={{ color: "#b9c2ae" }}>млн т</small>
              </div>
              <span className="tile__note" style={{ color: "#b9c2ae" }}>
                232,9 т CO₂ на гектар
              </span>
            </Card>
            <Card tone="soft">
              <span className="tile__label">уязвимость</span>
              <div style={{ margin: "10px 0" }}>
                <LevelPill level={plot.vulnerability_level} />
              </div>
              <span className="tile__note">
                Аналитический скрининг, не расчёт риска реверсии. Числовой вероятности нет.
              </span>
            </Card>
          </div>
        </>
      )}

      {/* ---------------- Измерение ---------------- */}
      {tab === "Измерение" && (
        <>
          <Card title="Лесопокрытая площадь по годам" note="Hansen GFC v1.13 + Dynamic World" className="plot-block">
            <CoverChart />
            <p className="ov-note">
              Год без валидных наблюдений остаётся в ряду пустым, а не подменяется соседним:
              2017 и 2018 закрыты сплошной облачностью.
            </p>
          </Card>

          <div className="plot-row plot-row--even">
            <Card title="Полнота данных" className="plot-block">
              <dl className="kv">
                <div>
                  <dt>доступных периодов</dt>
                  <dd className="tabular">
                    {DATA_COMPLETENESS.periods_available} из {DATA_COMPLETENESS.periods_total} лет
                  </dd>
                </div>
                <div>
                  <dt>валидное покрытие территории</dt>
                  <dd className="tabular">{DATA_COMPLETENESS.valid_coverage_pct} %</dd>
                </div>
                <div>
                  <dt>последнее валидное наблюдение</dt>
                  <dd>{DATA_COMPLETENESS.latest_observation_date}</dd>
                </div>
                <div>
                  <dt>пропущенные годы</dt>
                  <dd>{DATA_COMPLETENESS.missing_years.join(", ")}</dd>
                </div>
              </dl>
              <p className="ov-note">
                Период — один год. Если валидных наблюдений в периоде сверки нет, блок возвращает
                «данных недостаточно» вместо результата.
              </p>
            </Card>

            <Card title="Доверие к измерению" className="plot-block">
              <div className="kv__head">
                <span>общий уровень</span>
                <ConfidencePill value={plot.measurement_confidence_overall} />
              </div>
              <dl className="kv">
                {CONFIDENCE_PARTS.map((c) => (
                  <div key={c.label}>
                    <dt>
                      {c.label}
                      <em>{c.basis}</em>
                    </dt>
                    <dd>
                      <ConfidencePill value={c.value} />
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="ov-note">
                Единой числовой оценки доверия вида «83 %» не существует — ни в данных, ни на
                экране.
              </p>
            </Card>
          </div>
        </>
      )}

      {/* ---------------- Нарушения ---------------- */}
      {(tab === "Нарушения" || showOverview) && (
        <Card title="История нарушений" note="Hansen v1.13 + MODIS MCD64A1" className="plot-block">
          <div className="bars">
            {DISTURBANCE_SERIES.map((d) => {
              const missing = d.area_ha === null;
              const h = missing ? 0 : Math.max(((d.area_ha as number) / max) * 170, 4);
              const tone = d.year === 2021 ? "peak" : d.year >= 2024 ? "fresh" : "plain";
              return (
                <div key={d.year} className="bars__col">
                  {missing ? (
                    <span className="bars__missing" title="нет валидных наблюдений" />
                  ) : (
                    <span className={`bars__bar bars__bar--${tone}`} style={{ height: `${h}px` }} />
                  )}
                  <span className="bars__year">{String(d.year).slice(2)}</span>
                </div>
              );
            })}
          </div>

          <table className="tbl" style={{ marginTop: 20 }}>
            <thead>
              <tr>
                <th>год</th>
                <th className="num">площадь, га</th>
                <th>тип события</th>
                <th>пожарные признаки</th>
                <th>доверие</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {EVENTS.map((e) => (
                <tr key={e.event_id} className="is-clickable" onClick={() => setEvent(e)}>
                  <td>{e.year}</td>
                  <td className="num">{e.area_ha}</td>
                  <td>{EVENT_LABEL[e.event_type]}</td>
                  <td>{e.fire_evidence ? "обнаружены" : "нет"}</td>
                  <td>
                    <ConfidencePill value={e.confidence} />
                  </td>
                  <td>
                    <button className="row-open" type="button" aria-label="Открыть событие">
                      →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <p className="ov-note">
            «Не связано с пожаром» не означает рубку: тип остаётся неопределённым, пока нет
            дополнительных сведений. Пустые столбцы — годы без валидных наблюдений.
          </p>
        </Card>
      )}

      {/* ---------------- Сверка ---------------- */}
      {withProject && (tab === "Сверка" || showOverview) && (
        <Card title="Расхождения с заявленным" className="plot-block">
          <div className="claim-head">
            Сверка ведётся на дату отчётности <b>{CLAIM_CHECK.reference_date}</b> · использовано
            валидное наблюдение {CLAIM_CHECK.observation_year_used} года, а не последнее доступное
          </div>

          <table className="tbl">
            <thead>
              <tr>
                <th>показатель</th>
                <th className="num">заявлено</th>
                <th className="num">независимые данные</th>
                <th className="num">расхождение</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {CLAIM_CHECK.rows.map((r) => (
                <tr key={r.metric} className={r.comparable ? "" : "is-muted"}>
                  <td>{r.label}</td>
                  <td className="num">{r.reported !== null ? formatNumber(r.reported) : "—"}</td>
                  <td className="num">{r.observed !== null ? formatNumber(r.observed) : "—"}</td>
                  <td className="num">
                    {r.discrepancy_pct !== null ? `${r.discrepancy_pct} %` : "—"}
                  </td>
                  <td>
                    {r.comparable ? (
                      <span
                        className={
                          Math.abs(r.discrepancy_pct ?? 0) > 10 ? "lvl lvl--high" : "lvl lvl--low"
                        }
                      >
                        {Math.abs(r.discrepancy_pct ?? 0) > 10 ? "вне ±10 %" : "в пределах"}
                      </span>
                    ) : (
                      <span className="lvl lvl--none">не сопоставимо</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <p className="ov-note">
            Заявленный эффект — предотвращённые выбросы: оценка того, сколько сгорело бы без
            проекта. Величина контрфактическая, базовых линий мы не считаем. Строка показана, но
            не проверяется.
          </p>

          {/* События после даты отчётности — не расхождение, а устаревание */}
          <div className="after">
            <div className="after__head">
              <b>Появилось после даты отчётности</b>
              <span>
                не расхождение — отчёт {CLAIM_CHECK.observation_year_used} года не мог их содержать
              </span>
            </div>
            {CLAIM_CHECK.events_after_reference_date.map((e) => (
              <button key={e.event_id} className="after__row" type="button" onClick={() => setEvent(e)}>
                <span>{e.year}</span>
                <span className="tabular">{e.area_ha} га</span>
                <span>{EVENT_LABEL[e.event_type]}</span>
                <span className="after__arrow">→</span>
              </button>
            ))}
          </div>

          <div className="claim-foot">
            <ClaimPill status={CLAIM_CHECK.status} />
            <span>{CLAIM_CHECK.likely_cause}</span>
          </div>

          <p className="ov-note">
            Формулировок «проект врёт» и «обнаружен гринвошинг» система не использует.
            Максимально жёсткое допустимое утверждение — «требует проверки».
          </p>
        </Card>
      )}

      {/* ---------------- Уязвимость ---------------- */}
      {tab === "Уязвимость" && (
        <Card title="Уязвимость климатического эффекта" className="plot-block">
          <div className="vuln">
            <LevelPill level={VULNERABILITY.level} />
          </div>
          <p className="tile__label" style={{ marginBottom: 10 }}>
            основные драйверы
          </p>
          <ul className="drivers">
            {VULNERABILITY.drivers.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
          <dl className="kv">
            <div>
              <dt>метод</dt>
              <dd>{VULNERABILITY.method}</dd>
            </div>
            <div>
              <dt>версия модели</dt>
              <dd>{VULNERABILITY.model_version ?? "модель не подключена, работает эвристика"}</dd>
            </div>
          </dl>
          <div className="disclaimer">
            Аналитический скрининг, а не официальный расчёт риска реверсии. Числовой вероятности
            вида «36,73 %» нет ни в данных, ни на экране: оценка подаётся аналитику как основание
            для суждения, а не как множитель к деньгам.
          </div>
        </Card>
      )}

      {/* ---------------- Экономика ---------------- */}
      {tab === "Экономика" && (
        <div className="plot-row plot-row--econ">
          <Card title="Допущения пользователя" note="подписаны источником" className="plot-block">
            <div className="field">
              <span className="tile__label">ожидаемый объём эффекта</span>
              <div className="field__box tabular">
                {formatNumber(SCENARIO.expected_effect_co2_t_year)} т CO₂/год
              </div>
              <span className="field__src">ⓘ заявлено проектом по данным реестра</span>
            </div>

            <div className="field">
              <span className="tile__label">цена углеродной единицы</span>
              <div className="scen">
                {SCENARIO.price_scenarios.map((s) => (
                  <button
                    key={s.key}
                    type="button"
                    className={!manualPrice && price === s.price ? "scen__item is-on" : "scen__item"}
                    onClick={() => {
                      setPrice(s.price);
                      setManualPrice(false);
                    }}
                  >
                    {s.label} {s.price} ₽
                  </button>
                ))}
                <input
                  className="scen__input tabular"
                  type="number"
                  value={price}
                  onChange={(e) => {
                    setPrice(Number(e.target.value) || 0);
                    setManualPrice(true);
                  }}
                  aria-label="цена вручную"
                />
              </div>
              <span className="field__src">
                ⓘ {manualPrice ? "задано пользователем — выбор сценария снят" : "сценарий из конфигурации"}
              </span>
            </div>

            <div className="field">
              <span className="tile__label">дисконт сценария</span>
              <div className="slider">
                <input
                  type="range"
                  min={0}
                  max={60}
                  step={5}
                  value={haircut}
                  onChange={(e) => setHaircut(Number(e.target.value))}
                  aria-label="дисконт сценария"
                />
                <b className="tabular">{haircut} %</b>
              </div>
              <span className="field__src">ⓘ задан пользователем вручную</span>
            </div>

            <div className="disclaimer">
              Дисконт задаёт аналитик. Он никогда не выводится из оценки уязвимости: официальный
              процент резервирования устанавливают методология и реестр, а не наша модель.
            </div>
          </Card>

          <div className="plot-econ-right">
            <Card tone="dark" title="Сценарная выручка" className="plot-block">
              <div className="econ__big tabular">
                {formatDecimal(revenue / 1_000_000)} <small>млн ₽ / год</small>
              </div>
              <div className="econ__sub tabular">
                {formatNumber(perHa)} <small>₽ / га · база: площадь полигона</small>
              </div>
              <p className="ov-note" style={{ color: "#b9c2ae" }}>
                Сценарная оценка, не NPV: {SCENARIO.npv_unavailable_reason}.
              </p>
            </Card>

            <Card title="Чувствительность" note="млн ₽ в год" className="plot-block">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>дисконт \ цена</th>
                    {SCENARIO.price_scenarios.map((s) => (
                      <th key={s.key} className="num">
                        {s.price} ₽
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[0, 20, 40].map((h) => (
                    <tr key={h}>
                      <td style={{ color: "var(--c-muted-alt)" }}>{h} %</td>
                      {SCENARIO.price_scenarios.map((s) => (
                        <td key={s.key} className="num">
                          {formatDecimal(
                            (SCENARIO.expected_effect_co2_t_year * s.price * (1 - h / 100)) /
                              1_000_000
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>
        </div>
      )}

      {/* ---------------- Аудит ---------------- */}
      {tab === "Аудит" && (
        <Card title="Аудит расчёта" note={plot.calc_id} className="plot-block">
          <dl className="kv">
            <div>
              <dt>версия методики</dt>
              <dd>v1.0</dd>
            </div>
            <div>
              <dt>версия алгоритма</dt>
              <dd>calc-0.1</dd>
            </div>
            <div>
              <dt>хеш входных данных</dt>
              <dd style={{ wordBreak: "break-all", fontSize: 13 }}>{PROVENANCE.input_hash}</dd>
            </div>
            <div>
              <dt>даты снимков</dt>
              <dd>{PROVENANCE.observation_dates.join(" · ")}</dd>
            </div>
            <div>
              <dt>коэффициенты</dt>
              <dd className="tabular">
                углеродная доля {PROVENANCE.parameters.carbon_fraction} · CO₂-фактор{" "}
                {PROVENANCE.parameters.co2_factor}
              </dd>
            </div>
          </dl>

          <p className="tile__label" style={{ margin: "18px 0 10px" }}>
            источники данных
          </p>
          <ul className="drivers">
            {PROVENANCE.datasets.map((d) => (
              <li key={d.name}>
                {d.name} — {d.version}
              </li>
            ))}
          </ul>

          <button
            className="btn btn--dark"
            type="button"
            style={{ marginTop: 20 }}
            onClick={() => downloadCalcJson(plot.calc_id)}
          >
            <span>Выгрузить расчёт в JSON</span>
          </button>
          <p className="ov-note">
            Выгрузка нужна, чтобы расчёт можно было перепроверить независимо, не доверяя нашему
            интерфейсу.
          </p>
        </Card>
      )}

      {event && <EventDrawer event={event} onClose={() => setEvent(null)} />}
    </>
  );
}

/* Ряд лесопокрытой площади: линия по точкам, разрывы на годах без данных */
function CoverChart() {
  const vals = COVER_SERIES.map((c) => c.forest_area_ha).filter((v): v is number => v !== null);
  const min = Math.min(...vals) * 0.995;
  const max = Math.max(...vals) * 1.002;

  return (
    <div className="cover">
      {COVER_SERIES.map((c) => {
        const missing = c.forest_area_ha === null;
        const h = missing ? 0 : (((c.forest_area_ha as number) - min) / (max - min)) * 170 + 12;
        return (
          <div key={c.year} className="cover__col">
            {missing ? (
              <span className="bars__missing" title="нет валидных наблюдений" />
            ) : (
              <span className="cover__bar" style={{ height: `${h}px` }}>
                <em className="tabular">{Math.round((c.forest_area_ha as number) / 1000)}k</em>
              </span>
            )}
            <span className="bars__year">{String(c.year).slice(2)}</span>
          </div>
        );
      })}
    </div>
  );
}

/* Выгрузка расчёта файлом — реальное действие, а не заглушка */
function downloadCalcJson(calcId: string) {
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
