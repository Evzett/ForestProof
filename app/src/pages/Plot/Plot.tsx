import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Card, FilterSelect, formatDecimal, formatNumber } from "../../components/ui";
import ChangeMap from "../../components/ChangeMap";
import {
  ASSUMPTIONS,
  DATASETS,
  PARAMETERS,
  YEARS,
  areaById,
  eventsFor,
  periodFor,
} from "../../data/case";
import type { Area, Period } from "../../data/case";
import "./Plot.css";

/* Карточка участка — основной экран сервиса.

   Порядок вкладок повторяет порядок рассуждения верификатора: сколько
   запаса и как изменилось → как менялось по годам → где именно и почему →
   насколько результату можно верить → сколько это единиц → отчёт.

   Знак результата: положительное E означает потерю углерода из
   учитываемого пула, отрицательное — накопление. Это не объём выброса
   в атмосферу: часть углерода переходит в мёртвую древесину и подстилку. */

const TABS = [
  "Запас",
  "Динамика",
  "Изменения",
  "Неопределённость",
  "Единицы",
  "Отчёт",
] as const;

const YEAR_OPTIONS = YEARS.map((y) => ({ value: String(y), label: String(y) }));

export default function Plot() {
  const { id } = useParams();
  const area = areaById(id);
  const events = eventsFor(area.aoi_id);

  const [tab, setTab] = useState<(typeof TABS)[number]>("Запас");
  const [start, setStart] = useState("2019");
  const [end, setEnd] = useState("2024");

  /* Конечный год должен быть больше начального — условие постановки.
     Вместо ошибки подтягиваем конец за началом: пользователь не обязан
     угадывать допустимую пару. */
  const startYear = Number(start);
  const endYear = Math.max(Number(end), startYear + 1);
  const period = periodFor(area, startYear, Math.min(endYear, 2024));

  if (!period) {
    return (
      <Card title="Расчёт недоступен">
        <p className="ov-note" style={{ marginTop: 0 }}>
          Для пары {startYear} — {endYear} в наборе нет сопоставимых состояний.
        </p>
      </Card>
    );
  }

  return (
    <>
      <header className="plot-head">
        <Link to="/app/areas" className="plot-head__back" aria-label="Назад к участкам">
          ←
        </Link>
        <div>
          <h1 className="page-head__title">{area.name}</h1>
          <p className="page-head__sub">
            {formatDecimal(area.area_ha, 1)} га · {area.region} · {area.role} ·{" "}
            {area.status}
          </p>
        </div>
      </header>

      <div className="period">
        <span className="period__label">период наблюдения</span>
        <FilterSelect
          value={start}
          onChange={setStart}
          options={YEAR_OPTIONS.slice(0, -1)}
          label="начальный год"
        />
        <span aria-hidden="true">—</span>
        <FilterSelect
          value={String(Math.min(endYear, 2024))}
          onChange={setEnd}
          options={YEAR_OPTIONS.filter((o) => Number(o.value) > startYear)}
          label="конечный год"
        />
        <span className="period__hint">
          {period.years} годовых перехода · учитываемый пул — живая надземная древесная биомасса
        </span>
      </div>

      <nav className="tabs">
        {TABS.map((t) => (
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

      {tab === "Запас" && <StockTab area={area} period={period} />}
      {tab === "Динамика" && <DynamicsTab area={area} period={period} />}
      {tab === "Изменения" && <ChangesTab area={area} period={period} events={events} />}
      {tab === "Неопределённость" && <UncertaintyTab period={period} />}
      {tab === "Единицы" && <UnitsTab area={area} period={period} />}
      {tab === "Отчёт" && <ReportTab area={area} period={period} />}
    </>
  );
}

/* ------------------------------------------------------------ Запас ---- */

function Sign({ value }: { value: number }) {
  return value > 0 ? (
    <span className="lvl lvl--high">потеря углерода</span>
  ) : (
    <span className="lvl lvl--low">накопление</span>
  );
}

function StockTab({ area, period }: { area: Area; period: Period }) {
  return (
    <>
      <div className="plot-tiles">
        <Card>
          <span className="tile__label">запас на {period.year_start}</span>
          <div className="plot-tiles__value tabular">
            {formatDecimal(period.c_start_t_ha, 2)} <small>т C/га</small>
          </div>
          <span className="tile__note">
            всего {formatNumber(Math.round(period.stock_start_tc))} т C
          </span>
        </Card>
        <Card>
          <span className="tile__label">запас на {period.year_end}</span>
          <div className="plot-tiles__value tabular">
            {formatDecimal(period.c_end_t_ha, 2)} <small>т C/га</small>
          </div>
          <span className="tile__note">
            всего {formatNumber(Math.round(period.stock_end_tc))} т C
          </span>
        </Card>
        <Card tone="dark">
          <span className="tile__label" style={{ color: "#b9c2ae" }}>
            результат за период
          </span>
          <div className="plot-tiles__value tabular" style={{ color: "var(--c-lime)" }}>
            {period.e_tco2e > 0 ? "+" : "−"}
            {formatNumber(Math.abs(Math.round(period.e_tco2e)))}{" "}
            <small style={{ color: "#b9c2ae" }}>т CO₂-экв.</small>
          </div>
          <span className="tile__note" style={{ color: "#b9c2ae" }}>
            {formatDecimal(period.e_per_ha_year, 3)} т CO₂-экв./га/год
          </span>
        </Card>
        <Card tone="soft">
          <span className="tile__label">знак результата</span>
          <div style={{ margin: "10px 0" }}>
            <Sign value={period.e_tco2e} />
          </div>
          <span className="tile__note">
            Положительное E — потеря из учитываемого пула. Это не объём выброса в атмосферу.
          </span>
        </Card>
      </div>

      <div className="plot-row plot-row--even">
        <Card title="Как получен результат" className="plot-block">
          <ol className="chain">
            <li>
              <span>биомасса → углерод</span>
              <b className="tabular">
                c = b × {PARAMETERS.carbon_fraction}
              </b>
            </li>
            <li>
              <span>суммарный запас по площади пересечения пикселей</span>
              <b className="tabular">
                C = Σ aᵢ × cᵢ = {formatNumber(Math.round(period.stock_end_tc))} т C
              </b>
            </li>
            <li>
              <span>разность запасов</span>
              <b className="tabular">
                ΔC = {formatDecimal(period.delta_stock_tc, 1)} т C
              </b>
            </li>
            <li>
              <span>перевод в CO₂-эквивалент</span>
              <b className="tabular">
                E = −ΔC × 44/12 = {formatDecimal(period.e_tco2e, 1)}
              </b>
            </li>
            <li>
              <span>нормирование по площади и длительности</span>
              <b className="tabular">
                e = E / (A × Δt) = {formatDecimal(period.e_per_ha_year, 3)}
              </b>
            </li>
          </ol>
          <p className="ov-note">
            Площадь A = {formatDecimal(period.area_ha, 2)} га посчитана как сумма пересечений
            пикселей с контуром. На сетке в градусах пиксель CCI на этой широте примерно 0,54 га,
            а не гектар.
          </p>
        </Card>

        <Card title="Границы учитываемого пула" className="plot-block">
          <dl className="kv">
            <div>
              <dt>входит в расчёт</dt>
              <dd>живая надземная древесная биомасса</dd>
            </div>
            <div>
              <dt>не входит</dt>
              <dd>корни, мёртвая древесина, подстилка, почва, древесная продукция</dd>
            </div>
            <div>
              <dt>обе даты в одних границах</dt>
              <dd>включая участки, утратившие лесной покров</dd>
            </div>
            <div>
              <dt>двойной учёт</dt>
              <dd>последствия пожара отдельно не прибавляются к разности запасов</dd>
            </div>
          </dl>
          <div className="disclaimer">
            Отсутствие пула в расчёте не означает, что его запас равен нулю. Для полного
            углеродного баланса экосистемы нужны данные, которых в наборе нет.
          </div>
        </Card>
      </div>
    </>
  );
}

/* --------------------------------------------------------- Динамика ---- */

function DynamicsTab({ area, period }: { area: Area; period: Period }) {
  const shown = area.series.filter(
    (p) => p.year >= period.year_start && p.year <= period.year_end
  );
  const values = shown.map((p) => p.c_t_ha);
  const min = Math.min(...values) * 0.96;
  const max = Math.max(...values) * 1.02;
  const base = area.baseline_stock_t_ha;

  let cumulative = 0;

  return (
    <>
      <Card
        title="Годовой ряд запаса"
        note={`ESA CCI Biomass v7.0 · ${period.year_start}—${period.year_end}`}
        className="plot-block"
      >
        <div className="cover">
          {shown.map((p) => {
            const h = ((p.c_t_ha - min) / (max - min)) * 190 + 14;
            const baseline = base[String(p.year)];
            return (
              <div key={p.year} className="cover__col">
                <span className="cover__bar" style={{ height: `${h}px` }}>
                  <em className="tabular">{formatDecimal(p.c_t_ha, 1)}</em>
                </span>
                {baseline !== undefined && (
                  <span
                    className="cover__baseline"
                    style={{ bottom: `${((baseline - min) / (max - min)) * 190 + 14 + 22}px` }}
                    title={`базовая линия ${formatDecimal(baseline, 2)} т C/га`}
                  />
                )}
                <span className="bars__year">{p.year}</span>
              </div>
            );
          })}
        </div>
        <p className="ov-note">
          Столбик — наблюдение, штрих — сценарный запас базовой линии на тот же год. Карты CCI
          содержат годовые модельные оценки состояния, а не даты съёмки.
        </p>
      </Card>

      <Card title="Накопленное изменение" note="т C относительно начала периода" className="plot-block">
        <div className="tbl__scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>год</th>
                <th className="num">запас, т C/га</th>
                <th className="num">±SD продукта, т/га</th>
                <th className="num">суммарно, т C</th>
                <th className="num">накоплено, т C</th>
                <th className="num">базовая линия, т C/га</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((p, i) => {
                if (i > 0) cumulative = p.stock_tc - shown[0].stock_tc;
                return (
                  <tr key={p.year}>
                    <td>{p.year}</td>
                    <td className="num">{formatDecimal(p.c_t_ha, 2)}</td>
                    <td className="num">±{formatDecimal(p.agb_sd_t_ha, 1)}</td>
                    <td className="num">{formatNumber(Math.round(p.stock_tc))}</td>
                    <td className="num">{i === 0 ? "—" : formatNumber(Math.round(cumulative))}</td>
                    <td className="num" style={{ color: "var(--c-muted-alt)" }}>
                      {base[String(p.year)] !== undefined
                        ? formatDecimal(base[String(p.year)], 2)
                        : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="ov-note">
          Накопленный результат не складывается с годовыми результатами за тот же период — это
          был бы повторный учёт одного эффекта.
        </p>
      </Card>
    </>
  );
}

/* -------------------------------------------------------- Изменения ---- */

function ChangesTab({
  area,
  period,
  events,
}: {
  area: Area;
  period: Period;
  events: ReturnType<typeof eventsFor>;
}) {
  const inPeriod = area.cover_loss.filter(
    (l) => l.year > period.year_start && l.year <= period.year_end
  );
  const lossArea = inPeriod.reduce((a, b) => a + b.area_ha, 0);
  const share = (lossArea / area.area_ha) * 100;
  /* Вклад затронутой территории: доля площади, помноженная на результат.
     Это оценка вклада, а не измеренная величина по этим же пикселям. */
  const contribution = period.e_tco2e * (share / 100);

  return (
    <>
      <div className="plot-row">
        <Card title="Где изменился запас" note={`${period.year_start} → ${period.year_end}`} className="plot-block">
          <ChangeMap area={area} />
        </Card>

        <Card title="Вклад изменившейся территории" className="plot-block">
          <dl className="kv">
            <div>
              <dt>потери покрова за период</dt>
              <dd className="tabular">{formatDecimal(lossArea, 1)} га</dd>
            </div>
            <div>
              <dt>доля участка</dt>
              <dd className="tabular">{formatDecimal(share, 2)} %</dd>
            </div>
            <div>
              <dt>оценка вклада в результат</dt>
              <dd className="tabular">{formatNumber(Math.round(contribution))} т CO₂-экв.</dd>
            </div>
            <div>
              <dt>событий с подтверждением</dt>
              <dd className="tabular">{events.length}</dd>
            </div>
          </dl>
          <p className="ov-note">
            Вклад оценён по доле площади. Это не независимое измерение по тем же пикселям:
            разрешение продукта потерь (30 м) и продукта биомассы (100 м) не совпадает.
          </p>
        </Card>
      </div>

      <Card title="Потери древесного покрова по годам" note="Hansen GFC v1.13" className="plot-block">
        {area.cover_loss.length === 0 ? (
          <p className="ov-note" style={{ marginTop: 0 }}>
            Потерь покрова выше порога {PARAMETERS.treecover_threshold_pct} % на участке не найдено.
          </p>
        ) : (
          <>
            <div className="bars">
              {area.cover_loss.map((l) => {
                const peak = Math.max(...area.cover_loss.map((x) => x.area_ha));
                const h = Math.max((l.area_ha / peak) * 170, 3);
                const within = l.year > period.year_start && l.year <= period.year_end;
                return (
                  <div key={l.year} className="bars__col">
                    <span
                      className={`bars__bar bars__bar--${within ? "peak" : "plain"}`}
                      style={{ height: `${h}px` }}
                      title={`${l.year}: ${formatDecimal(l.area_ha, 1)} га`}
                    />
                    <span className="bars__year">{String(l.year).slice(2)}</span>
                  </div>
                );
              })}
            </div>
            <p className="ov-note">
              Тёмные столбцы попадают в выбранный период. Потеря — снижение древесного покрова по
              продукту Hansen, а не установленная вырубка: причина здесь не определяется.
            </p>
          </>
        )}
      </Card>

      <Card title="События с внешним подтверждением" className="plot-block">
        {events.length === 0 ? (
          <p className="ov-note" style={{ marginTop: 0 }}>
            Событий, подтверждённых внешними продуктами, на участке нет. Изменения покрова есть,
            но их причина не установлена — статус так и остаётся.
          </p>
        ) : (
          events.map((e) => (
            <div key={e.event_id} className="event">
              <div className="event__head">
                <b>{e.cause_supported}</b>
                <span className="lvl lvl--medium">{e.evidence_type}</span>
              </div>
              <dl className="kv">
                <div>
                  <dt>доступный интервал дат</dt>
                  <dd>
                    {e.date_min} — {e.date_max} · неопределённость {e.uncertainty_days[0]}—
                    {e.uncertainty_days[1]} дней
                  </dd>
                </div>
                <div>
                  <dt>доля затронутых пикселей продукта</dt>
                  <dd className="tabular">
                    {e.burned_pixels} из {e.all_pixels} ·{" "}
                    {formatDecimal((e.burned_pixels / e.all_pixels) * 100, 0)} %
                  </dd>
                </div>
                <div>
                  <dt>источник</dt>
                  <dd>{e.source_id}</dd>
                </div>
                <div>
                  <dt>контекст</dt>
                  <dd>
                    <a href={e.context_url} target="_blank" rel="noreferrer">
                      сообщение МЧС
                    </a>
                  </dd>
                </div>
              </dl>
              <div className="disclaimer">{e.limitations}</div>
            </div>
          ))
        )}
      </Card>
    </>
  );
}

/* -------------------------------------------- Неопределённость ---- */

function UncertaintyTab({ period }: { period: Period }) {
  const relative = Math.abs(period.h_tco2e / (period.e_tco2e || 1)) * 100;

  return (
    <>
      <div className="plot-row plot-row--even">
        <Card title="Диапазон результата" note="охват 90 %, нормальное приближение" className="plot-block">
          <div className="range">
            <span className="range__end tabular">{formatNumber(Math.round(period.lower_tco2e))}</span>
            <span className="range__bar">
              <span className="range__dot" />
            </span>
            <span className="range__end tabular">{formatNumber(Math.round(period.upper_tco2e))}</span>
          </div>
          <p className="range__mid tabular">
            оценка {formatNumber(Math.round(period.e_tco2e))} т CO₂-экв. · полуширина H ={" "}
            {formatNumber(Math.round(period.h_tco2e))}
          </p>
          <dl className="kv">
            <div>
              <dt>σ результата</dt>
              <dd className="tabular">{formatNumber(Math.round(period.sigma_e_tco2e))} т CO₂-экв.</dd>
            </div>
            <div>
              <dt>H к величине результата</dt>
              <dd className="tabular">{formatDecimal(relative, 0)} %</dd>
            </div>
            <div>
              <dt>источник ошибки</dt>
              <dd>канал AGB_SD продукта CCI, попиксельно</dd>
            </div>
          </dl>
          <div className="disclaimer">
            Это сценарный диапазон, а не эмпирически откалиброванный интервал: независимых
            наземных измерений углерода в наборе нет, и калибровать его не на чем.
          </div>
        </Card>

        <Card title="Как перенесена ошибка" className="plot-block">
          <ol className="chain">
            <li>
              <span>ошибка пикселя</span>
              <b className="tabular">AGB_SD × CF</b>
            </li>
            <li>
              <span>сумма по территории с корреляцией ρs</span>
              <b className="tabular">
                σ² = (1−ρs)Σ(aᵢsᵢ)² + ρs(Σaᵢsᵢ)²
              </b>
            </li>
            <li>
              <span>разность двух лет с корреляцией ρt</span>
              <b className="tabular">σΔ² = σ₀² + σ₁² − 2ρtσ₀σ₁</b>
            </li>
            <li>
              <span>полуширина интервала</span>
              <b className="tabular">H = {PARAMETERS.k_sigma} × σΔ × 44/12</b>
            </li>
          </ol>
          <p className="ov-note">
            Пространственная корреляция ρs = {PARAMETERS.rho_spatial} и временная ρt ={" "}
            {PARAMETERS.rho_temporal} — допущения. Их влияние показано ниже и оказывается
            решающим.
          </p>
        </Card>
      </div>

      {period.sensitivity && (
        <Card
          title="Чувствительность к допущениям о корреляции"
          note="число единиц или отношение H/R"
          className="plot-block"
        >
          <div className="tbl__scroll">
            <table className="tbl sens">
              <thead>
                <tr>
                  <th>ρs \ ρt</th>
                  {period.sensitivity[0].map((c) => (
                    <th key={c.rho_temporal} className="num">
                      {c.rho_temporal}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {period.sensitivity.map((row) => (
                  <tr key={row[0].rho_spatial}>
                    <td>{row[0].rho_spatial}</td>
                    {row.map((c) => (
                      <td key={c.rho_temporal} className="num">
                        {c.units ? (
                          <b>{formatNumber(c.units)}</b>
                        ) : c.h_over_r === null ? (
                          <span className="dash">—</span>
                        ) : (
                          <span style={{ color: "var(--c-muted-alt)" }}>
                            H/R {formatDecimal(c.h_over_r, 1)}
                          </span>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="ov-note">
            Прочерк — результат не превышает базовую линию, единицы не считаются вовсе. Там, где
            стоит H/R, неопределённость не меньше самого результата и число единиц равно нулю по
            правилу кейса. Единицы появляются только при независимой ошибке между пикселями и
            почти полной её повторяемости между годами — то есть при самом благоприятном наборе
            допущений, который нечем подтвердить.
          </p>
        </Card>
      )}

      <Card title="Принятые допущения" className="plot-block">
        <div className="tbl__scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>параметр</th>
                <th>значение</th>
                <th>статус</th>
                <th>происхождение</th>
              </tr>
            </thead>
            <tbody>
              {ASSUMPTIONS.map((a) => (
                <tr key={a.key}>
                  <td>{a.label}</td>
                  <td className="tabular">{a.value}</td>
                  <td>
                    <span
                      className={
                        a.kind === "допущение" ? "lvl lvl--medium" : "lvl lvl--none"
                      }
                    >
                      {a.kind}
                    </span>
                  </td>
                  <td style={{ color: "var(--c-muted-alt)" }}>{a.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

/* ----------------------------------------------------------- Единицы ---- */

function UnitsTab({ area, period }: { area: Area; period: Period }) {
  const available = period.units !== null;

  return (
    <>
      <div className="plot-row plot-row--even">
        <Card title="Сравнение с базовой линией" className="plot-block">
          <dl className="kv">
            <div>
              <dt>результат по данным, E_proj</dt>
              <dd className="tabular">{formatNumber(Math.round(period.e_proj_tco2e))}</dd>
            </div>
            <div>
              <dt>результат базовой линии, E_base</dt>
              <dd className="tabular">{formatNumber(Math.round(period.e_base_tco2e))}</dd>
            </div>
            <div>
              <dt>утечка LK</dt>
              <dd className="tabular">{period.leakage_tco2e}</dd>
            </div>
            <div>
              <dt>результат относительно базовой линии, R</dt>
              <dd className="tabular">
                <b>{formatNumber(Math.round(period.r_tco2e))}</b>
              </dd>
            </div>
          </dl>
          <p className="ov-note">
            Базовая линия {area.baseline_id} продолжает историческую динамику 2015—2019:{" "}
            {formatDecimal(area.baseline_rate_tc_ha_year, 3)} т C/га/год. Это условие кейса, а не
            установленная дополнительность реального проекта.
          </p>
        </Card>

        <Card tone="dark" title="Потенциальные единицы" className="plot-block">
          <div className="econ__big tabular">
            {available ? formatNumber(period.units ?? 0) : "—"}{" "}
            <small>{available ? "единиц" : "расчёт недоступен"}</small>
          </div>
          {period.reason && (
            <p className="ov-note" style={{ color: "#b9c2ae" }}>
              {period.reason}
            </p>
          )}
          <p className="ov-note" style={{ color: "#b9c2ae" }}>
            Расчёт по условиям кейса, а не сертифицированные единицы. Одна единица — 1 т CO₂-экв.
            после вычетов.
          </p>
        </Card>
      </div>

      <Card title="Ход расчёта единиц" className="plot-block">
        <ol className="chain">
          <li>
            <span>R = E_base − E_proj − LK</span>
            <b className="tabular">{formatDecimal(period.r_tco2e, 1)}</b>
          </li>
          <li>
            <span>H — полуширина диапазона</span>
            <b className="tabular">{formatDecimal(period.h_tco2e, 1)}</b>
          </li>
          <li>
            <span>H / R</span>
            <b className="tabular">
              {period.h_over_r === null ? "не вычисляется при R ≤ 0" : formatDecimal(period.h_over_r, 3)}
            </b>
          </li>
          <li>
            <span>UNC = min(1, max(0, H/R − 0,10))</span>
            <b className="tabular">
              {period.unc_share === null ? "—" : formatDecimal(period.unc_share, 3)}
            </b>
          </li>
          <li>
            <span>R_adj = R × (1 − UNC)</span>
            <b className="tabular">
              {period.r_adjusted_tco2e === null ? "—" : formatDecimal(period.r_adjusted_tco2e, 1)}
            </b>
          </li>
          <li>
            <span>резерв B = R_adj × 0,15</span>
            <b className="tabular">
              {period.buffer_tco2e === null ? "—" : formatDecimal(period.buffer_tco2e, 1)}
            </b>
          </li>
          <li>
            <span>Q = floor(R_adj × 0,85)</span>
            <b className="tabular">{available ? formatNumber(period.units ?? 0) : "—"}</b>
          </li>
        </ol>
        <p className="ov-note">
          При R ≤ 0 отношение H/R не вычисляется вовсе. При H/R ≥ 1 число единиц равно нулю:
          неопределённость не меньше самого результата. Дробный остаток после округления вниз
          в Q не включается.
        </p>
      </Card>

      <Card title="Сценарная стоимость" note="V = Q × p" className="plot-block">
        <div className="tbl__scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>сценарий цены</th>
                <th className="num">цена, ₽/ед.</th>
                <th className="num">стоимость, ₽</th>
              </tr>
            </thead>
            <tbody>
              {(["low", "base", "high"] as const).map((key) => (
                <tr key={key}>
                  <td>{key === "low" ? "низкий" : key === "base" ? "базовый" : "высокий"}</td>
                  <td className="num">{formatNumber(PARAMETERS.prices_rub[key])}</td>
                  <td className="num">{formatNumber(period.value_rub[key])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="ov-note">
          Цены заданы условиями кейса и не являются прогнозом рыночной цены.
        </p>
      </Card>
    </>
  );
}

/* ------------------------------------------------------------- Отчёт ---- */

function ReportTab({ area, period }: { area: Area; period: Period }) {
  const calcId = useMemo(
    () => `CALC-${area.aoi_id}-${period.year_start}-${period.year_end}`,
    [area.aoi_id, period.year_start, period.year_end]
  );
  const generatedAt = useMemo(() => new Date().toISOString().slice(0, 19).replace("T", " "), []);

  const report = {
    calc_id: calcId,
    generated_at: generatedAt,
    methodology_version: "case-v1.0",
    algorithm_version: "calc-1.0",
    area: {
      aoi_id: area.aoi_id,
      name: area.name,
      region: area.region,
      bbox_wgs84: area.bbox,
      area_ha: area.area_ha,
      role: area.role,
      status: area.status,
    },
    period: { start: period.year_start, end: period.year_end, transitions: period.years },
    pool: "живая надземная древесная биомасса",
    stock: {
      c_start_t_ha: period.c_start_t_ha,
      c_end_t_ha: period.c_end_t_ha,
      stock_start_tc: period.stock_start_tc,
      stock_end_tc: period.stock_end_tc,
      delta_stock_tc: period.delta_stock_tc,
      e_tco2e: period.e_tco2e,
      e_per_ha_year: period.e_per_ha_year,
      sign: period.e_tco2e > 0 ? "потеря углерода" : "накопление",
    },
    uncertainty: {
      sigma_e_tco2e: period.sigma_e_tco2e,
      lower_tco2e: period.lower_tco2e,
      upper_tco2e: period.upper_tco2e,
      h_tco2e: period.h_tco2e,
      method: "перенос AGB_SD с заданной пространственной и временной корреляцией",
      status: "сценарный диапазон, не эмпирическая калибровка",
    },
    baseline: {
      baseline_id: area.baseline_id,
      rate_tc_ha_year: area.baseline_rate_tc_ha_year,
      c_start_t_ha: period.baseline_c_start_t_ha,
      c_end_t_ha: period.baseline_c_end_t_ha,
      e_base_tco2e: period.e_base_tco2e,
    },
    units: {
      r_tco2e: period.r_tco2e,
      h_over_r: period.h_over_r,
      unc_share: period.unc_share,
      r_adjusted_tco2e: period.r_adjusted_tco2e,
      buffer_tco2e: period.buffer_tco2e,
      units: period.units,
      reason: period.reason,
      status: "расчёт по условиям кейса, не сертифицированные единицы",
      value_rub: period.value_rub,
    },
    parameters: PARAMETERS,
    assumptions: ASSUMPTIONS,
    datasets: DATASETS,
    cover_loss_ha_by_year: area.cover_loss,
    limitations: [
      "Независимых наземных измерений углерода в наборе нет.",
      "Сравнение спутниковых продуктов не является наземной валидацией.",
      "Причина изменения покрова указывается только при наличии подтверждения.",
      "Базовая линия задана условиями кейса и не устанавливает дополнительность.",
    ],
  };

  const download = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${calcId}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <Card title="Отчёт о расчёте" note={calcId} className="plot-block">
        <dl className="kv">
          <div>
            <dt>территория и период</dt>
            <dd>
              {area.name} · {formatDecimal(area.area_ha, 1)} га · {period.year_start}—
              {period.year_end}
            </dd>
          </div>
          <div>
            <dt>результат</dt>
            <dd className="tabular">
              {formatNumber(Math.round(period.e_tco2e))} т CO₂-экв. (
              {formatNumber(Math.round(period.lower_tco2e))} …{" "}
              {formatNumber(Math.round(period.upper_tco2e))})
            </dd>
          </div>
          <div>
            <dt>потенциальные единицы</dt>
            <dd className="tabular">
              {period.units === null ? "недоступно" : formatNumber(period.units)}
              {period.reason ? ` · ${period.reason}` : ""}
            </dd>
          </div>
          <div>
            <dt>методика и алгоритм</dt>
            <dd>case-v1.0 / calc-1.0</dd>
          </div>
          <div>
            <dt>дата расчёта</dt>
            <dd>{generatedAt}</dd>
          </div>
        </dl>

        <p className="tile__label" style={{ margin: "18px 0 10px" }}>
          источники и версии
        </p>
        <div className="tbl__scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>набор</th>
                <th>версия</th>
                <th>роль в расчёте</th>
                <th>сетка</th>
              </tr>
            </thead>
            <tbody>
              {DATASETS.map((d) => (
                <tr key={d.id}>
                  <td>
                    <b>{d.name}</b>
                  </td>
                  <td style={{ color: "var(--c-muted-alt)" }}>{d.version}</td>
                  <td style={{ color: "var(--c-muted-alt)" }}>{d.role}</td>
                  <td style={{ color: "var(--c-muted-alt)" }}>{d.grid}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="tile__label" style={{ margin: "18px 0 10px" }}>
          ограничения
        </p>
        <ul className="drivers">
          {report.limitations.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>

        <button className="btn btn--dark" type="button" style={{ marginTop: 20 }} onClick={download}>
          <span>Выгрузить отчёт в JSON</span>
        </button>
        <p className="ov-note">
          Выгрузка содержит все параметры, допущения, источники и промежуточные величины —
          достаточно, чтобы повторить расчёт независимо от интерфейса.
        </p>
      </Card>
    </>
  );
}
