import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  Card,
  FilterSelect,
  LevelPill,
  formatDecimal,
  formatNumber,
  plural,
} from "../../components/ui";
import ChangeMap from "../../components/ChangeMap";
import CarbonTerrain from "../../components/CarbonTerrain";
import CalculationSummary from "../../components/CalculationSummary";
import SeriesChart from "../../components/SeriesChart";
import {
  ASSUMPTIONS,
  DATASETS,
  FEATURE_LABEL,
  MODEL,
  PARAMETERS,
  PRICE_SCENARIOS,
  YEARS,
  areaById,
  eventsFor,
  modelFor,
  periodFor,
  SCREENING_HORIZON_LABEL,
} from "../../data/case";
import { useScenario } from "../../data/scenario";
import { summaryForPeriod } from "../../data/summary";
import { COVERAGE, recompute } from "../../data/units";
import type { Area, Period } from "../../data/case";
import type { ReportBlock } from "../../reportPdf";
import { YearLossChart } from "../../components/YearLossChart";
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
  "Устойчивость",
  "Отчёт",
] as const;

const YEAR_OPTIONS = YEARS.map((y) => ({ value: String(y), label: String(y) }));

const ROLE_LABEL: Record<string, string> = {
  before: "до",
  immediate_after: "сразу после",
  recovery: "следующий сезон",
};

export default function Plot() {
  const { id } = useParams();
  const area = areaById(id);
  const events = eventsFor(area.aoi_id);

  const [tab, setTab] = useState<(typeof TABS)[number]>("Запас");

  /* Период можно задать ссылкой: раздел «Что изменилось» ведёт сюда с уже
     выбранными годами пересчёта, и открывать страницу на периоде по
     умолчанию значило бы потерять то, ради чего пользователь пришёл.
     Год из ссылки принимается, только если он есть в наборе. */
  const [search] = useSearchParams();
  const yearFromLink = (key: string, fallback: string) => {
    const raw = search.get(key);
    return raw !== null && (YEARS as readonly number[]).includes(Number(raw)) ? raw : fallback;
  };
  const [start, setStart] = useState(() => yearFromLink("start", "2019"));
  const [end, setEnd] = useState(() => yearFromLink("end", "2024"));

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

  const summary = summaryForPeriod(area, period);

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
          {period.years} {plural(period.years, ["годовой переход", "годовых перехода", "годовых переходов"])} · учитываемый пул — живая надземная древесная биомасса
        </span>
      </div>

      <CalculationSummary summary={summary} area={area} period={period} />

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
      {tab === "Неопределённость" && <UncertaintyTab area={area} period={period} />}
      {tab === "Единицы" && <UnitsTab area={area} period={period} />}
      {tab === "Устойчивость" && <StabilityTab area={area} />}
      {tab === "Отчёт" && <ReportTab area={area} period={period} />}
    </>
  );
}

/* ------------------------------------------------------------ Запас ---- */

/* Знак результата. Крупно — сам знак, потому что вопрос здесь
   двоичный: прибавилось или убыло. Слово под ним поясняет, что этот
   знак означает в наших единицах, где положительное E — это потеря. */
function Sign({ value }: { value: number }) {
  const glyph = value > 0 ? "+" : value < 0 ? "−" : "0";
  const word = value > 0 ? "потеря углерода" : value < 0 ? "накопление" : "без изменения";
  const tone = value > 0 ? "is-loss" : value < 0 ? "is-gain" : "is-zero";
  return (
    <span className={`sign ${tone}`}>
      <b className="sign__glyph">{glyph}</b>
      <span className="sign__word">{word}</span>
    </span>
  );
}

function StockTab({ area, period }: { area: Area; period: Period }) {
  const start = area.series.find((p) => p.year === period.year_start);
  const end = area.series.find((p) => p.year === period.year_end);

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
          <Sign value={period.e_tco2e} />
          <span className="tile__note">
            Положительное E — потеря из учитываемого пула. Это не объём выброса в атмосферу.
          </span>
        </Card>
      </div>

      {/* Биомасса нигде не показывается без ±: погрешность продукта
          сопоставима со значением, и прятать её значит обещать точность. */}
      <Card
        title="Биомасса, из которой посчитан запас"
        note="ESA CCI Biomass v7.0, канал AGB_SD"
        className="plot-block"
      >
        <dl className="kv">
          <div>
            <dt>{period.year_start} год</dt>
            <dd className="tabular">
              {start ? (
                <>
                  {formatDecimal(start.agb_t_ha, 1)} ± {formatDecimal(start.agb_sd_t_ha, 1)} т/га
                </>
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div>
            <dt>{period.year_end} год</dt>
            <dd className="tabular">
              {end ? (
                <>
                  {formatDecimal(end.agb_t_ha, 1)} ± {formatDecimal(end.agb_sd_t_ha, 1)} т/га
                </>
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div>
            <dt>погрешность к значению</dt>
            <dd className="tabular">
              {end && end.agb_t_ha
                ? `${formatDecimal((end.agb_sd_t_ha / end.agb_t_ha) * 100, 0)} %`
                : "—"}
            </dd>
          </div>
        </dl>
        <p className="ov-note">
          Погрешность — свойство самого продукта, а не нашего расчёта. На этих участках она
          составляет около половины значения, и именно поэтому диапазон результата получается
          широким. Подробнее — вкладка «Неопределённость».
        </p>
      </Card>

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
  const base = area.baseline_stock_t_ha;

  let cumulative = 0;

  return (
    <>
      <Card
        title="Годовой ряд запаса"
        note={`ESA CCI Biomass v7.0 · ${period.year_start}—${period.year_end}`}
        className="plot-block"
      >
        <SeriesChart
          observed={shown.map((p) => ({ year: p.year, value: p.c_t_ha }))}
          baseline={shown.map((p) => ({
            year: p.year,
            value: base[String(p.year)] ?? null,
          }))}
        />
        <p className="ov-note">
          Сплошная линия — наблюдение, пунктир — сценарный запас базовой линии на тот же год.
          Заливка между ними и есть то, из чего получается R: выше базовой линии — накопление
          сверх сценария, ниже — отставание от него. Шкала подписана, потому что запас меняется
          на единицы процентов и без неё график выглядел бы ровным.
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
  /* Год под курсором на диаграмме. Живёт во вкладке, а не внутри
     диаграммы: его слушает объёмный лес, который стоит выше. */
  const [hoverYear, setHoverYear] = useState<number | null>(null);
  const share = (lossArea / area.area_ha) * 100;
  /* Вклад затронутой территории: доля площади, помноженная на результат.
     Это оценка вклада, а не измеренная величина по этим же пикселям. */
  const contribution = period.e_tco2e * (share / 100);

  return (
    <>
      {area.terrain && (
        <Card
          title="Запас углерода в объёме"
          note={`${period.year_start} и ${period.year_end}`}
          className="plot-block mb20"
        >
          <CarbonTerrain
            terrain={area.terrain}
            name={area.name}
            startYear={period.year_start}
            endYear={period.year_end}
            highlightYear={hoverYear}
          />
        </Card>
      )}

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
            <YearLossChart
              rows={area.cover_loss}
              isWithin={(year) => year > period.year_start && year <= period.year_end}
              badgeLabel={`${area.cover_loss.length} ${plural(area.cover_loss.length, ["год", "года", "лет"])} с потерями`}
              caption={
                <>
                  суммарная площадь, потерявшая
                  <br />
                  древесный покров на участке
                </>
              }
              withinLabel="внутри выбранного периода"
              outsideLabel="вне выбранного периода"
              onHoverYear={setHoverYear}
              renderPicked={(row) => (
                <p className="yloss__pickednote">
                  {row.year > period.year_start && row.year <= period.year_end
                    ? "год попадает в выбранный период, поэтому потеря учтена в результате"
                    : "год вне выбранного периода: на результат за период не влияет"}
                </p>
              )}
            />
            <p className="ov-note">
              Потеря — снижение древесного покрова по продукту Hansen. Отсутствие пожарных
              признаков не означает рубку: причина указывается только при наличии подтверждений,
              иначе остаётся неустановленной.
            </p>
          </>
        )}
      </Card>

      {/* Снимок, найденный нами. Показывается там, где в набор сцены не
          вложены: без него у восьми добавленных участков блока снимков
          не было вовсе, и страница молчала о том, как выглядит место. */}
      {(!area.sentinel || area.sentinel.observations.length === 0) && area.scene_preview && (
        <Card
          title="Снимок участка"
          note={`Sentinel-2 L2A · ${area.scene_preview.date}`}
          className="plot-block"
        >
          <div className="shots">
            <figure>
              <img src={`/maps/${area.scene_preview.image}`} alt={`Снимок участка ${area.name}`} />
              <figcaption>
                <b>{area.scene_preview.date}</b>
                <span>
                  сцена {area.scene_preview.scene_id} · годных пикселей внутри контура{" "}
                  {formatDecimal(area.scene_preview.usable_fraction * 100, 0)} %
                </span>
              </figcaption>
            </figure>
          </div>
          <p className="ov-note">
            Сцена найдена нашим поиском по контуру, а не вложена в набор: выбрана по доле
            годных пикселей внутри участка, а не по облачности всего кадра. Яркость приведена
            к виду для показа общим множителем на три канала — цвет при этом не меняется.
            Ни одно число расчёта из этой картинки не берётся.
          </p>
        </Card>
      )}

      {area.sentinel && area.sentinel.observations.length > 0 && (
        <Card
          title="Снимки до и после"
          note={`Sentinel-2 L2A · ${area.sentinel.observations.length} наблюдения`}
          className="plot-block"
        >
          <div className="shots">
            {area.sentinel.observations.map((o) => (
              <figure key={o.role}>
                <img src={`/maps/${o.image}`} alt={`Снимок: ${ROLE_LABEL[o.role]}`} />
                <figcaption>
                  <b>{ROLE_LABEL[o.role]}</b> · {o.date}
                  <br />
                  пригодных пикселей {formatDecimal(o.valid_fraction * 100, 0)} %
                  {!o.usable && " — ниже порога 50 %, как подтверждение не используется"}
                  <br />
                  версия обработки {o.processing_baseline}
                  {o.harmonised && " · приведена к общей базе"}
                </figcaption>
              </figure>
            ))}
          </div>

          {area.sentinel.comparison && (
            <dl className="kv">
              <div>
                <dt>изменение NDVI</dt>
                <dd className="tabular">
                  {area.sentinel.comparison.delta_ndvi === null
                    ? "—"
                    : formatDecimal(area.sentinel.comparison.delta_ndvi, 3)}
                </dd>
              </div>
              <div>
                <dt>изменение NBR</dt>
                <dd className="tabular">
                  {area.sentinel.comparison.delta_nbr === null
                    ? "—"
                    : formatDecimal(area.sentinel.comparison.delta_nbr, 3)}
                </dd>
              </div>
              <div>
                <dt>доля площади, пригодной на обе даты</dt>
                <dd className="tabular">
                  {formatDecimal(area.sentinel.comparison.comparable_fraction * 100, 0)} %
                </dd>
              </div>
            </dl>
          )}

          <p className="ov-note">
            {area.sentinel.interpretation}
          </p>
          <div className="disclaimer">
            Индексы посчитаны только по пикселям, пригодным на обе даты: разные маски сравнивали
            бы разные территории. Сцены приведены к одной версии обработки — с версии 04.00 у
            Sentinel-2 другой ноль отражения, и без приведения NDVI на этих же снимках выходил
            2,3 при физическом пределе 1. Падение NBR само по себе причину не устанавливает:
            сплошная рубка даёт похожую картину.
          </div>
        </Card>
      )}

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
                {e.source_kind && e.source_kind !== "пришло с набором кейса" && (
                  <span className="lvl lvl--outline">{e.source_kind}</span>
                )}
              </div>
              <dl className="kv">
                <div>
                  <dt>доступный интервал дат</dt>
                  <dd>
                    {e.date_min} — {e.date_max}
                    {/* Оценка неопределённости даты есть только у событий
                        набора. У найденных нами её нет, и писать «0—0 дней»
                        значило бы выдать отсутствие оценки за точную дату. */}
                    {e.uncertainty_days[1] > 0
                      ? ` · неопределённость ${e.uncertainty_days[0]}—${e.uncertainty_days[1]} дней`
                      : " · оценки неопределённости даты у этого события нет"}
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
                {/* Ссылка на внешнее сообщение есть не у каждого события:
                    у найденных нами её нет, и пустая ссылка в отчёте хуже,
                    чем её отсутствие. */}
                {e.context_url && (
                  <div>
                    <dt>контекст</dt>
                    <dd>
                      <a href={e.context_url} target="_blank" rel="noreferrer">
                        сообщение МЧС
                      </a>
                    </dd>
                  </div>
                )}
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

function UncertaintyTab({ area, period }: { area: Area; period: Period }) {
  /* Допущения переноса ошибки крутятся прямо здесь: суммы по растрам
     посчитаны заранее, поэтому σ, диапазон и число единиц пересчитываются
     мгновенно. Это не украшение — это единственный способ показать, что
     число единиц на этих данных определяется допущениями, а не лесом. */
  const [rhoS, setRhoS] = useState(PARAMETERS.rho_spatial);
  const [rhoT, setRhoT] = useState(PARAMETERS.rho_temporal);
  const [k, setK] = useState<number>(PARAMETERS.k_sigma);

  const start = area.series.find((p) => p.year === period.year_start);
  const end = area.series.find((p) => p.year === period.year_end);
  const live = recompute(period, start, end, rhoS, rhoT, k);

  const changed =
    rhoS !== PARAMETERS.rho_spatial ||
    rhoT !== PARAMETERS.rho_temporal ||
    k !== PARAMETERS.k_sigma;

  const reset = () => {
    setRhoS(PARAMETERS.rho_spatial);
    setRhoT(PARAMETERS.rho_temporal);
    setK(PARAMETERS.k_sigma);
  };

  const relative = Math.abs(live.h / (period.e_tco2e || 1)) * 100;

  return (
    <>
      <Card
        title="Допущения переноса ошибки"
        note={changed ? "изменены — расчёт пересобран" : "значения по умолчанию"}
        className="plot-block"
      >
        <div className="knobs">
          <label className="knob">
            <span className="knob__head">
              <b>корреляция между пикселями, ρs</b>
              <em className="tabular">{formatDecimal(rhoS, 2)}</em>
            </span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={rhoS}
              onChange={(e) => setRhoS(Number(e.target.value))}
            />
            <span className="knob__hint">
              0 — ошибки соседних пикселей независимы и в сумме гасятся; 1 — складываются целиком
            </span>
          </label>

          <label className="knob">
            <span className="knob__head">
              <b>корреляция между годами, ρt</b>
              <em className="tabular">{formatDecimal(rhoT, 2)}</em>
            </span>
            <input
              type="range"
              min={0}
              max={0.99}
              step={0.01}
              value={rhoT}
              onChange={(e) => setRhoT(Number(e.target.value))}
            />
            <span className="knob__hint">
              чем выше, тем сильнее ошибка повторяется на обеих датах и гасится в разности
            </span>
          </label>

          <div className="knob">
            <span className="knob__head">
              <b>охват интервала</b>
              <em className="tabular">k = {formatDecimal(k, 3)}</em>
            </span>
            <div className="knob__pills">
              {COVERAGE.map((c) => (
                <button
                  key={c.k}
                  type="button"
                  className={`filter filter--btn ${k === c.k ? "filter--on" : ""}`.trim()}
                  aria-pressed={k === c.k}
                  onClick={() => setK(c.k)}
                >
                  {c.label}
                </button>
              ))}
            </div>
            <span className="knob__hint">
              нормальное приближение; статус диапазона от выбора не меняется — он остаётся
              сценарным
            </span>
          </div>
        </div>

        {changed && (
          <button className="link-btn" type="button" onClick={reset} style={{ marginTop: 14 }}>
            вернуть значения по умолчанию
          </button>
        )}
      </Card>

      <div className="plot-row plot-row--even">
        <Card
          title="Диапазон результата"
          note="пересчитывается при изменении допущений"
          className="plot-block"
        >
          <div className="range">
            <span className="range__end tabular">{formatNumber(Math.round(live.lower))}</span>
            <span className="range__bar">
              <span className="range__dot" />
            </span>
            <span className="range__end tabular">{formatNumber(Math.round(live.upper))}</span>
          </div>
          <p className="range__mid tabular">
            оценка {formatNumber(Math.round(period.e_tco2e))} т CO₂-экв. · полуширина H ={" "}
            {formatNumber(Math.round(live.h))}
          </p>
          <dl className="kv">
            <div>
              <dt>σ результата</dt>
              <dd className="tabular">{formatNumber(Math.round(live.h / k))} т CO₂-экв.</dd>
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

        <Card
          tone={live.units ? "dark" : "soft"}
          title="Что получается при этих допущениях"
          className="plot-block"
        >
          <div className="econ__big tabular">
            {live.units === null ? "—" : formatNumber(live.units)}{" "}
            <small>{live.units === null ? "расчёт недоступен" : "единиц"}</small>
          </div>
          <dl className="kv">
            <div>
              <dt>R относительно базовой линии</dt>
              <dd className="tabular">{formatNumber(Math.round(period.r_tco2e))}</dd>
            </div>
            <div>
              <dt>H / R</dt>
              <dd className="tabular">
                {live.hOverR === null ? "не вычисляется при R ≤ 0" : formatDecimal(live.hOverR, 2)}
              </dd>
            </div>
            <div>
              <dt>вычет UNC</dt>
              <dd className="tabular">
                {live.unc === null ? "—" : `${formatDecimal(live.unc * 100, 0)} %`}
              </dd>
            </div>
          </dl>
          {live.reason && <p className="ov-note">{live.reason}</p>}
          <p className="ov-note">
            Двигайте ползунки выше и смотрите, что происходит. Физика при этом не меняется: E, R и
            базовая линия остаются теми же. Меняется только то, во что мы решили верить про ошибку
            продукта.
          </p>
        </Card>
      </div>

      <Card title="Как перенесена ошибка" className="plot-block">
        <ol className="chain">
          <li>
            <span>ошибка пикселя</span>
            <b className="tabular">AGB_SD × CF</b>
          </li>
          <li>
            <span>сумма по территории с корреляцией ρs</span>
            <b className="tabular">σ² = (1−ρs)Σ(aᵢsᵢ)² + ρs(Σaᵢsᵢ)²</b>
          </li>
          <li>
            <span>разность двух лет с корреляцией ρt</span>
            <b className="tabular">σΔ² = σ₀² + σ₁² − 2ρtσ₀σ₁</b>
          </li>
          <li>
            <span>полуширина интервала</span>
            <b className="tabular">H = {formatDecimal(k, 3)} × σΔ × 44/12</b>
          </li>
        </ol>
        <p className="ov-note">
          Погрешность продукта на этих участках составляет около половины значения биомассы.
          Именно поэтому при любой заметной корреляции между пикселями диапазон получается шире
          самого результата — и число единиц обнуляется по правилу кейса.
        </p>
      </Card>

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
                    <span className={a.kind === "допущение" ? "lvl lvl--medium" : "lvl lvl--none"}>
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
      {/* Экономика стоит первой: на вопрос «сколько это денег» человек
          смотрит раньше, чем на то, как получилось Q. Сам расчёт никуда
          не делся, он ниже — и именно в таком порядке его и читают. */}
      <Economics area={area} period={period} />

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
    </>
  );
}

/* --------------------------------------------------------- Экономика ---- */

/* Деньги здесь стоят за пределами углеродного расчёта: цена умножается
   на уже готовое Q и ни на один физический показатель не влияет.
   Поэтому экономика показывает не одно число, а от чего это число
   зависит — от сценария цены и от допущений о корреляции ошибки. */
function Economics({ area: _area, period }: { area: Area; period: Period }) {
  const { priceKey, price, label, setPriceKey } = useScenario();

  const units = period.units ?? 0;
  const value = units * price;
  const perHa = value / period.area_ha;

  /* Стоимость накопленного запаса — справочная величина, а не выручка:
     никто не платит за то, что лес уже стоит. Показываем, потому что
     инвестор всё равно её прикидывает, и лучше подписать её честно. */
  const stockValue = period.stock_end_tc * PARAMETERS.co2_per_carbon * price;

  /* Сколько денег получилось бы при разных допущениях о корреляции.
     Это и есть настоящая экономика на этих данных: результат меняется
     не от цены, а от того, во что мы решили верить про ошибку. */
  const grid = period.sensitivity ?? [];
  const best = grid
    .flat()
    .filter((c) => (c.units ?? 0) > 0)
    .sort((a, b) => (b.units ?? 0) - (a.units ?? 0))[0];

  return (
    <>
      <Card title="Ценовой сценарий" note="задан условиями кейса" className="plot-block">
        <div className="scen">
          {PRICE_SCENARIOS.map((s) => (
            <button
              key={s.key}
              type="button"
              className={priceKey === s.key ? "scen__item is-on" : "scen__item"}
              aria-pressed={priceKey === s.key}
              onClick={() => setPriceKey(s.key)}
            >
              {s.label} · {formatNumber(s.price)} ₽
            </button>
          ))}
        </div>
        <p className="ov-note">
          Выбранный сценарий действует во всём приложении. Цены заданы кейсом и не являются
          прогнозом рыночной цены — это три точки для оценки чувствительности, а не диапазон
          ожиданий.
        </p>
      </Card>

      <div className="plot-row plot-row--even">
        <Card tone="dark" title={`Стоимость единиц · ${label}`} className="plot-block">
          <div className="econ__big tabular">
            {formatNumber(value)} <small>₽</small>
          </div>
          <div className="econ__sub tabular">
            {formatNumber(units)} <small>единиц × {formatNumber(price)} ₽</small>
          </div>
          <dl className="kv">
            <div>
              <dt style={{ color: "#b9c2ae" }}>на гектар</dt>
              <dd className="tabular" style={{ color: "#fff" }}>
                {formatDecimal(perHa, 2)} ₽/га
              </dd>
            </div>
            <div>
              <dt style={{ color: "#b9c2ae" }}>резерв удержан</dt>
              <dd className="tabular" style={{ color: "#fff" }}>
                {period.buffer_tco2e === null
                  ? "—"
                  : `${formatDecimal(period.buffer_tco2e, 1)} т CO₂-экв.`}
              </dd>
            </div>
          </dl>
          <p className="ov-note" style={{ color: "#b9c2ae" }}>
            {units === 0
              ? "Единиц нет, поэтому и стоимости нет. Это результат расчёта, а не отсутствие данных."
              : "Расчёт по условиям кейса, а не сертифицированные единицы."}
          </p>
        </Card>

        <Card title="Стоимость накопленного запаса" note="справочно" className="plot-block">
          <div className="plot-tiles__value tabular">
            {formatDecimal(stockValue / 1_000_000, 1)} <small>млн ₽</small>
          </div>
          <p className="ov-note" style={{ marginTop: 10 }}>
            {formatNumber(Math.round(period.stock_end_tc))} т C на конец периода, переведённые в
            CO₂-эквивалент и умноженные на {formatNumber(price)} ₽.
          </p>
          <div className="disclaimer">
            Это не выручка и не то, что можно продать. Платят за поток, а не за запас: углерод,
            который уже лежит в лесу, накопился без проекта. Величина показана только как
            масштаб — чтобы видеть, что единицы составляют от неё доли процента.
          </div>
        </Card>
      </div>

      <Card
        title="От чего зависит выручка"
        note="стоимость при разных допущениях о корреляции ошибки"
        className="plot-block"
      >
        {grid.length === 0 ? (
          <p className="ov-note" style={{ marginTop: 0 }}>
            Сетка чувствительности для этого периода не посчитана.
          </p>
        ) : (
          <>
            <div className="tbl__scroll">
              <table className="tbl sens">
                <thead>
                  <tr>
                    <th>ρs \ ρt</th>
                    {grid[0].map((c) => (
                      <th key={c.rho_temporal} className="num">
                        {c.rho_temporal}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {grid.map((row) => (
                    <tr key={row[0].rho_spatial}>
                      <td>{row[0].rho_spatial}</td>
                      {row.map((c) => (
                        <td key={c.rho_temporal} className="num">
                          {c.units ? (
                            <b>{formatNumber(c.units * price)} ₽</b>
                          ) : (
                            <span className="dash">0</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="ov-note">
              {best
                ? `Максимум на этой сетке — ${formatNumber((best.units ?? 0) * price)} ₽ при ρs = ${best.rho_spatial} и ρt = ${best.rho_temporal}. Это самый благоприятный набор допущений, а не оценка.`
                : "Ни при каком сочетании допущений выручки не получается: результат не превышает базовую линию."}{" "}
              Цена меняет числа пропорционально и на сам факт наличия единиц не влияет — его
              определяют физика и неопределённость, а не рынок.
            </p>
          </>
        )}
      </Card>
    </>
  );
}

/* ---------------------------------------------------- Устойчивость ---- */

/* Прогноз показан отдельно от анализа прошедшего периода — этого прямо
   требует постановка. На число единиц скрининг не влияет: вычет за
   неопределённость выводится из H/R, резерв фиксирован условиями кейса. */
function StabilityTab({ area }: { area: Area }) {
  const s = area.stability;

  return (
    <>
      <div className="plot-row plot-row--even">
        <Card
        title="Устойчивость результата"
        note={`горизонт ${SCREENING_HORIZON_LABEL}`}
        className="plot-block"
      >
          <div className="vuln">
            <LevelPill level={s.level} />
          </div>
          <dl className="kv">
            <div>
              <dt>сработало признаков</dt>
              <dd className="tabular">{s.drivers.length} из 6</dd>
            </div>
            <div>
              <dt>сумма баллов</dt>
              <dd className="tabular">
                {s.score} из {s.max_score}
              </dd>
            </div>
            <div>
              <dt>метод</dt>
              <dd>{s.method}</dd>
            </div>
            <div>
              <dt>что считает эту оценку</dt>
              <dd>{s.model_version ?? "пороговые правила; обученная модель — ниже"}</dd>
            </div>
          </dl>
          <div className="disclaimer">{s.limitation}</div>
        </Card>

        <ModelForecastCard aoiId={area.aoi_id} rulesLevel={s.level} />
      </div>

      <Card title="Сработавшие признаки" note="каждый порог виден и оспорим" className="plot-block">
        <div className="tbl__scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>признак</th>
                <th className="num">значение</th>
                <th className="num">порог</th>
                <th className="num">баллов</th>
              </tr>
            </thead>
            <tbody>
              {s.drivers.map((d) => (
                <tr key={d.label}>
                  <td>{d.label}</td>
                  <td className="num">
                    {formatDecimal(d.value, d.value >= 10 ? 1 : 2)} {d.unit}
                  </td>
                  <td className="num" style={{ color: "var(--c-muted-alt)" }}>
                    ≥ {formatDecimal(d.threshold, 2)}
                  </td>
                  <td className="num">
                    <b>{d.points}</b>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {s.drivers.length === 0 && (
          <p className="ov-note" style={{ marginTop: 0 }}>
            Ни один признак не сработал: по имеющимся данным поводов сомневаться в устойчивости
            результата нет.
          </p>
        )}
        <p className="ov-note">
          Категория получена суммой баллов по шести признакам, посчитанным по тем же растрам, что
          и основной расчёт. Порог до 4 баллов — низкая, до 8 — средняя, выше — высокая.
        </p>
      </Card>

      <ModelEvidence aoiId={area.aoi_id} />

      <div className="plot-row plot-row--even">
        <Card title="Чего скрининг не делает" tone="soft" className="plot-block">
          <ul className="meth__not" style={{ color: "var(--c-ink-black)" }}>
            <li>
              <span aria-hidden="true">✕</span> не влияет на число потенциальных единиц
            </li>
            <li>
              <span aria-hidden="true">✕</span> не даёт числовой вероятности реверсии
            </li>
            <li>
              <span aria-hidden="true">✕</span> не заменяет официальный расчёт риска
            </li>
            <li>
              <span aria-hidden="true">✕</span> не переносится на другие природные зоны
            </li>
          </ul>
          <p className="ov-note">
            Вычет за неопределённость выводится из отношения H/R, резерв фиксирован условиями
            кейса — подставить сюда выход скрининга значило бы нарушить правила расчёта.
          </p>
        </Card>
      </div>
    </>
  );
}

/* ------------------------------------------------- Модель как второе мнение -- */

/* Модель считается на тех же шести признаках и показывается РЯДОМ
   с правилами, а не вместо них. Её собственный вывод о том, что
   проверить её нечем, выводится целиком: прятать такое — значит
   выдавать регуляризованный компромисс за оценку. */
/* Прогноз модели. Стоит рядом с пороговыми правилами, потому что это
   два ответа на один вопрос, и сравнивать их глазами — смысл экрана. */
function ModelForecastCard({ aoiId, rulesLevel }: { aoiId: string; rulesLevel: string }) {
  const prediction = modelFor(aoiId);
  const forecast = prediction?.forecast;

  if (!forecast) {
    return (
      <Card title="Прогноз модели" note="обученная модель" className="plot-block plot-block--dark">
        <div className="vuln">
          <span className="lvl lvl--none">прогноз недоступен</span>
        </div>
        <p className="ov-note">
          {prediction?.reason ?? "нет данных Hansen по тайлу этого участка"}
        </p>
      </Card>
    );
  }

  const agrees = forecast.category === rulesLevel;
  return (
    <Card
      title={`Прогноз модели на ${forecast.horizon[0]}—${forecast.horizon[1]}`}
      note="обученная модель"
      className="plot-block plot-block--dark"
    >
      <div className="vuln">
        <LevelPill level={forecast.category} />
        <span className={`lvl ${agrees ? "lvl--low" : "lvl--medium"}`}>
          {agrees ? "совпадает с правилами" : "расходится с правилами"}
        </span>
      </div>
      <dl className="kv">
        <div>
          <dt>признаки посчитаны по</dt>
          <dd className="tabular">
            {forecast.feature_window[0]}—{forecast.feature_window[1]}
          </dd>
        </div>
        <div>
          <dt>потери за последние три года</dt>
          <dd className="tabular">{formatDecimal(forecast.recent_loss_pct, 2)} %</dd>
        </div>
      </dl>
      <div className="disclaimer">
        Это и есть предсказание на следующие годы. Окно признаков той же длины, что при
        обучении, но сдвинуто к концу данных: модель смотрит на девятнадцать последних лет и
        отвечает про следующую пятилетку.{" "}
        <b>Показана категория, а не число.</b> Вероятность у модели есть, но на экран она не
        выводится: число вида «0,99» читается как измеренная вероятность реверсии, которой у
        нас нет и быть не может на выборке в восемьсот участков одной природной зоны. На число
        потенциальных единиц прогноз не влияет.
      </div>
    </Card>
  );
}

/* Всё, чем прогноз подкреплён: проверка на известном пятилетии, качество
   на отложенной выборке, вклад признаков и почему нет утечки. */
function ModelEvidence({ aoiId }: { aoiId: string }) {
  const prediction = modelFor(aoiId);
  const ranked = Object.entries(MODEL.weights).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const quality = MODEL.quality;
  const singleAuc = Math.max(quality.best_single_auc, 1 - quality.best_single_auc);

  return (
    <>
      <div className="plot-row plot-row--even">
        <Card title="Как проверен прогноз" note="известное пятилетие" className="plot-block">
          <p className="ov-note" style={{ marginTop: 0 }}>
            Ту же модель прогоняем по окну 2001—2019 и спрашиваем про 2020—2024 — период,
            который уже прошёл и чей исход известен. Это единственный способ узнать, чего
            стоит прогноз на {SCREENING_HORIZON_LABEL}.
          </p>
          {prediction?.available ? (
            <dl className="kv">
              <div>
                <dt>модель говорила</dt>
                <dd>
                  <LevelPill level={(prediction.category ?? "low") as "low" | "medium" | "high"} />
                </dd>
              </div>
              <div>
                <dt>что было на самом деле</dt>
                <dd>
                  {prediction.label === 1 ? "нарушение было" : "нарушения не было"} · потеря{" "}
                  {formatDecimal(prediction.future_loss_pct ?? 0, 2)} %
                </dd>
              </div>
            </dl>
          ) : (
            <p className="ov-note">{prediction?.reason ?? "проверка недоступна"}</p>
          )}
        </Card>

        <Card title="Качество на отложенной выборке" note={MODEL.method} className="plot-block">
          <dl className="kv">
            <div>
              <dt>участков в выборке</dt>
              <dd className="tabular">
                {MODEL.sample.size} · обучение {MODEL.sample.train}, отложенная {MODEL.sample.test}
              </dd>
            </div>
            <div>
              <dt>ROC-AUC на отложенной</dt>
              <dd className="tabular">
                <b>{formatDecimal(quality.roc_auc_test, 3)}</b>
              </dd>
            </div>
            <div>
              <dt>лучший одиночный признак</dt>
              <dd className="tabular">{formatDecimal(singleAuc, 3)}</dd>
            </div>
            <div>
              <dt>модель лучше одного признака</dt>
              <dd>
                {quality.beats_single_feature ? (
                  <span className="lvl lvl--low">да</span>
                ) : (
                  <span className="lvl lvl--medium">нет</span>
                )}
              </dd>
            </div>
          </dl>
          <p className="ov-note">
            Качество меряется ROC-AUC, а не точностью: при неравных классах точность показывает
            долю большего класса и ничего больше. Стандартизация считается только по обучающей
            части — иначе отложенная подсматривает через среднее и разброс.
          </p>
        </Card>
      </div>

      <div className="plot-row plot-row--even">
        <Card title="Вклад признаков" note="стандартизованные коэффициенты" className="plot-block">
          <dl className="meth__formulas">
            {ranked.map(([key, weight]) => (
              <div key={key}>
                <dt style={{ fontSize: 13 }}>{FEATURE_LABEL[key] ?? key}</dt>
                <dd className="tabular">
                  {weight > 0 ? "+" : ""}
                  {formatDecimal(weight, 3)}
                </dd>
              </div>
            ))}
          </dl>
          <p className="ov-note">
            Признак «{FEATURE_LABEL[quality.best_single_feature] ?? quality.best_single_feature}»
            в одиночку даёт почти всё разделение. Остальные пять добавляют{" "}
            {formatDecimal(quality.roc_auc_test - singleAuc, 3)} — то есть ничего.
          </p>
        </Card>

        <Card title="Почему здесь нет утечки" tone="soft" className="plot-block">
          <dl className="kv">
            <div>
              <dt>признаки считаются по</dt>
              <dd>{MODEL.design.feature_window}</dd>
            </div>
            <div>
              <dt>метка берётся за</dt>
              <dd>{MODEL.design.label_window}</dd>
            </div>
            <div>
              <dt>правило метки</dt>
              <dd>{MODEL.design.label_rule}</dd>
            </div>
          </dl>
          <p className="ov-note">
            Если бы метка и признак считались по одному периоду, модель предсказывала бы
            собственный вход: точность вышла бы прекрасная и бессмысленная. Периоды разведены,
            поэтому задача настоящая — предсказать будущее по прошлому.
          </p>
        </Card>
      </div>
    </>
  );
}

/* ------------------------------------------------------------- Отчёт ---- */

function ReportTab({ area, period }: { area: Area; period: Period }) {
  const summary = summaryForPeriod(area, period);
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
    ...(summary ? { summary } : {}),
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

  /* PDF собирается из тех же величин, что уже показаны выше, а не считается
     заново: второй источник тех же чисел рано или поздно разойдётся с первым
     и отчёт перестанет соответствовать экрану. */
  const pdfBlocks = (): ReportBlock[] => {
    const num = (v: number) => formatNumber(Math.round(v));
    const rangeLine = `${num(period.e_tco2e)} т CO₂-экв. (${num(period.lower_tco2e)} … ${num(period.upper_tco2e)})`;
    const unitsLine =
      period.units === null
        ? `недоступно${period.reason ? ` · ${period.reason}` : ""}`
        : `${formatNumber(period.units)}${period.reason ? ` · ${period.reason}` : ""}`;

    return [
      {
        kind: "title",
        text: "Отчёт о расчёте",
        sub: `${calcId} · сформирован ${generatedAt}`,
      },
      {
        kind: "kv",
        rows: [
          ["территория", `${area.name}, ${area.region}`],
          ["площадь", `${formatDecimal(area.area_ha, 1)} га`],
          ["период", `${period.year_start}—${period.year_end}`],
          ["учитываемый пул", "живая надземная древесная биомасса"],
          ["результат", rangeLine],
          ["потенциальные единицы", unitsLine],
          ["методика и алгоритм", "case-v1.0 / calc-1.0"],
          ["статус данных", "воспроизводимый локальный кэш открытых продуктов"],
        ],
      },
      { kind: "heading", text: "Как получен результат" },
      {
        kind: "steps",
        rows: [
          [
            "Растры",
            `ESA CCI Biomass v7.0, биомасса и канал AGB_SD за ${period.year_start} и ${period.year_end}.`,
          ],
          [
            "Площадь",
            `${formatDecimal(period.area_ha, 4)} га по доле пересечения каждого пикселя с контуром; пиксель сетки CCI на этой широте — около 0,54 га, а не гектар.`,
          ],
          [
            "Запас",
            `биомасса × CF ${PARAMETERS.carbon_fraction} = ${formatDecimal(period.c_start_t_ha, 2)} т C/га на ${period.year_start} и ${formatDecimal(period.c_end_t_ha, 2)} на ${period.year_end}.`,
          ],
          [
            "Изменение",
            `ΔC = ${num(period.delta_stock_tc)} т C, затем × 44/12 и знак меняется: E = ${period.e_tco2e > 0 ? "+" : ""}${num(period.e_tco2e)} т CO₂-экв. ${period.e_tco2e > 0 ? "— потеря из учитываемого пула." : "— накопление."}`,
          ],
          [
            "Неопределённость",
            `перенос AGB_SD при ρs ${PARAMETERS.rho_spatial}, ρt ${PARAMETERS.rho_temporal}, k ${PARAMETERS.k_sigma} даёт H = ${num(period.h_tco2e)} т CO₂-экв. Это сценарный диапазон, а не эмпирически откалиброванный интервал.`,
          ],
          [
            "Базовая линия",
            `историческая динамика g = ${formatDecimal(area.baseline_rate_tc_ha_year, 3)} т C/га/год даёт E_base = ${num(period.e_base_tco2e)} т CO₂-экв.`,
          ],
          [
            "Единицы",
            `R = E_base − E − LK = ${num(period.r_tco2e)} т CO₂-экв.` +
              (period.r_tco2e <= 0
                ? " ≤ 0 → Q = 0, отношение H/R не вычисляется."
                : period.h_over_r !== null && period.h_over_r >= 1
                  ? ` · H/R = ${formatDecimal(period.h_over_r, 2)} ≥ 1 → Q = 0.`
                  : ` · вычет UNC ${period.unc_share === null ? "—" : formatDecimal(period.unc_share, 3)}, резерв ${PARAMETERS.buffer_share}, округление вниз → Q = ${period.units ?? "недоступно"}.`),
          ],
        ],
      },
      { kind: "heading", text: "Источники и версии" },
      {
        kind: "table",
        head: ["набор", "версия", "роль в расчёте", "сетка"],
        rows: DATASETS.map((d) => [d.name, d.version, d.role, d.grid]),
      },
      { kind: "heading", text: "Ограничения" },
      { kind: "list", items: report.limitations },
      {
        kind: "note",
        text: "Значения получены по условиям кейса и не являются сертифицированными углеродными единицами. Полный машинный набор параметров и промежуточных величин выгружается кнопкой «Выгрузить отчёт в JSON».",
      },
    ];
  };

  const [pdfState, setPdfState] = useState<"idle" | "busy" | "failed">("idle");

  const downloadPdf = async () => {
    setPdfState("busy");
    try {
      const { downloadReportPdf } = await import("../../reportPdf");
      await downloadReportPdf(`${calcId}.pdf`, pdfBlocks());
      setPdfState("idle");
    } catch {
      // Молча ничего не делать нельзя: пользователь ждёт файл и должен
      // узнать, что его не будет, а не гадать, сохранился он или нет.
      setPdfState("failed");
    }
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
            <dt>статус данных</dt>
            <dd>
              <span className="badge badge--ok" title="Штатный режим: воспроизводимый локальный кэш открытых продуктов CEDA / Google Storage">
                воспроизводимый локальный кэш · 18.09.2026
              </span>
            </dd>
          </div>
          <div>
            <dt>дата расчёта</dt>
            <dd>{generatedAt}</dd>
          </div>
        </dl>

        <h3 className="card__subtitle">источники и версии</h3>
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

        {/* Цепочка вывода. Проверяющему нужно не итоговое число, а то,
            как оно получено: какой параметр дал какую величину. Раньше
            отчёт показывал результат и источники, но не путь между ними. */}
        <h3 className="card__subtitle">как получен результат</h3>
        <ol className="steps">
          <li>
            <b>Растры</b>
            <span>
              ESA CCI Biomass v7.0, биомасса и канал AGB_SD за {period.year_start} и{" "}
              {period.year_end}
            </span>
          </li>
          <li>
            <b>Площадь</b>
            <span>
              {formatDecimal(period.area_ha, 4)} га по доле пересечения каждого пикселя с контуром;
              пиксель сетки CCI на этой широте — около 0,54 га, а не гектар
            </span>
          </li>
          <li>
            <b>Запас</b>
            <span>
              биомасса × CF {PARAMETERS.carbon_fraction} ={" "}
              {formatDecimal(period.c_start_t_ha, 2)} т C/га на {period.year_start} и{" "}
              {formatDecimal(period.c_end_t_ha, 2)} на {period.year_end}
            </span>
          </li>
          <li>
            <b>Изменение</b>
            <span>
              ΔC = {formatNumber(Math.round(period.delta_stock_tc))} т C, затем × 44/12 и знак
              меняется: E = {period.e_tco2e > 0 ? "+" : ""}
              {formatNumber(Math.round(period.e_tco2e))} т CO₂-экв.{" "}
              {period.e_tco2e > 0 ? "— потеря из учитываемого пула" : "— накопление"}
            </span>
          </li>
          <li>
            <b>Неопределённость</b>
            <span>
              перенос AGB_SD при ρs {PARAMETERS.rho_spatial}, ρt {PARAMETERS.rho_temporal}, k{" "}
              {PARAMETERS.k_sigma} даёт H = {formatNumber(Math.round(period.h_tco2e))} т CO₂-экв.
              Это сценарный диапазон, а не эмпирически откалиброванный интервал
            </span>
          </li>
          <li>
            <b>Базовая линия</b>
            <span>
              историческая динамика g = {formatDecimal(area.baseline_rate_tc_ha_year, 3)} т C/га/год
              даёт E_base = {formatNumber(Math.round(period.e_base_tco2e))} т CO₂-экв.
            </span>
          </li>
          <li>
            <b>Единицы</b>
            <span>
              R = E_base − E − LK = {formatNumber(Math.round(period.r_tco2e))} т CO₂-экв.
              {period.r_tco2e <= 0
                ? " ≤ 0 → Q = 0, отношение H/R не вычисляется"
                : period.h_over_r !== null && period.h_over_r >= 1
                  ? ` · H/R = ${formatDecimal(period.h_over_r, 2)} ≥ 1 → Q = 0`
                  : ` · вычет UNC ${period.unc_share === null ? "—" : formatDecimal(period.unc_share, 3)}, резерв ${PARAMETERS.buffer_share}, округление вниз → Q = ${period.units ?? "недоступно"}`}
            </span>
          </li>
        </ol>

        <h3 className="card__subtitle">ограничения</h3>
        <ul className="limits">
          {report.limitations.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>

        <div className="report-actions">
          <button
            className="btn btn--dark"
            type="button"
            onClick={downloadPdf}
            disabled={pdfState === "busy"}
          >
            <span>{pdfState === "busy" ? "Готовим PDF…" : "Скачать в PDF"}</span>
          </button>
          <button className="btn btn--outline" type="button" onClick={download}>
            <span>Выгрузить в JSON</span>
          </button>
        </div>
        {pdfState === "failed" && (
          <p className="ov-note" role="alert">
            PDF собрать не удалось — файл не скачан. Отчёт целиком есть в выгрузке JSON, а эту же
            страницу можно сохранить документом через печать браузера.
          </p>
        )}
        <p className="ov-note">
          PDF повторяет то, что на экране: результат с диапазоном, цепочку вывода, источники и
          ограничения — по нему видно, как получено число. JSON содержит все параметры, допущения и
          промежуточные величины — достаточно, чтобы повторить расчёт независимо от интерфейса.
        </p>
      </Card>
    </>
  );
}
