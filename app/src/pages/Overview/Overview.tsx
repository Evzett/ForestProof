import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Card,
  CircleBtn,
  FilterSelect,
  LevelPill,
  formatArea,
  plural,
  formatDecimal,
  formatNumber,
} from "../../components/ui";
import { PageHead } from "../../components/AppShell";
import { AREAS, PARAMETERS, PRICE_SCENARIOS, YEARS, formatBbox } from "../../data/case";
import { useScenario } from "../../data/scenario";
import { YearLossChart } from "../../components/YearLossChart";
import "./Overview.css";

/* Обзор — состояние набора и результатов по всем участкам сразу.

   Главная величина здесь не «сколько единиц получилось», а «на скольких
   участках расчёт вообще дал результат и почему на остальных не дал».
   Пустой результат — такой же ответ, как число, и он должен быть виден
   на первом экране, а не находиться в глубине карточки. */

const LOSS_RANGES = [
  { value: "2019", label: "период анализа" },
  { value: "2011", label: "с 2011 года" },
  { value: "all", label: "весь ряд, 25 лет" },
];

const PERIODS = [
  { value: "2019-2024", label: "2019 — 2024" },
  { value: "2019-2021", label: "2019 — 2021" },
  { value: "2021-2024", label: "2021 — 2024" },
  { value: "2023-2024", label: "2023 — 2024" },
];


/* Справка по набору целиком: на скольких участках расчёт дал результат,
   где потеря наибольшая и чем подтверждена причина.

   С карточкой «Краткая справка» на странице участка это не дубль: там
   генератор ядра отвечает про один участок за один период, здесь —
   про весь набор сразу. Вопросы разные, и свести их в один нельзя:
   первый нужен при разборе участка, второй при первом взгляде на набор.

   Собирается шаблоном из посчитанного, без языковой модели: так
   свойство «ничего не выдумывает» держится конструкцией.

   Возвращаются не склеенный абзац, а строки с выделенной величиной:
   сплошным текстом справка читалась как дисклеймер, и числа в ней
   терялись — а числа в ней и есть содержание. */
type SummaryLine = { value: string; unit?: string; text: string };

function buildSummary(startYear: number, endYear: number): SummaryLine[] {
  const rows = AREAS.map((a) => {
    const p =
      a.periods.find((x) => x.year_start === startYear && x.year_end === endYear) ??
      a.period_2019_2024;
    return { area: a, period: p };
  });
  const losing = rows.filter((r) => r.period.e_tco2e > 0);
  const withUnits = rows.filter((r) => (r.period.units ?? 0) > 0);
  const worst = [...rows].sort((a, b) => b.period.e_tco2e - a.period.e_tco2e)[0];

  return [
    {
      value: `${losing.length} из ${rows.length}`,
      text: `участков теряют углерод из учитываемого пула за ${startYear}—${endYear}`,
    },
    {
      value: formatNumber(Math.round(worst.period.e_tco2e)),
      unit: "т CO₂-экв.",
      text: `наибольшая потеря — ${worst.area.name}`,
    },
    {
      value: withUnits.length === 0 ? "ни один" : `${withUnits.length} из ${rows.length}`,
      text:
        withUnits.length === 0
          ? "участок не даёт потенциальных единиц: результат не превышает базовую линию либо не отличим от неё"
          : "участков дают потенциальные единицы",
    },
  ];
}

export default function Overview() {
  const { priceKey, price, label, setPriceKey } = useScenario();
  const [range, setRange] = useState("2019-2024");
  const [lossRange, setLossRange] = useState("2019");
  const [startYear, endYear] = range.split("-").map(Number);

  const rows = useMemo(
    () =>
      AREAS.map((a) => ({
        area: a,
        period:
          a.periods.find((x) => x.year_start === startYear && x.year_end === endYear) ??
          a.period_2019_2024,
      })),
    [startYear, endYear]
  );


  const [summary, setSummary] = useState(() => ({ lines: buildSummary(2019, 2024), at: "—" }));
  const [rebuilding, setRebuilding] = useState(false);

  const regenerate = () => {
    if (rebuilding) return;
    setRebuilding(true);
    window.setTimeout(() => {
      const now = new Date();
      setSummary({
        lines: buildSummary(startYear, endYear),
        at: `${now.toLocaleDateString("ru-RU")} ${now.toLocaleTimeString("ru-RU", {
          hour: "2-digit",
          minute: "2-digit",
        })}`,
      });
      setRebuilding(false);
    }, 450);
  };

  const totalArea = AREAS.reduce((s, a) => s + a.area_ha, 0);
  const losing = rows.filter((r) => r.period.e_tco2e > 0).length;
  const withUnits = rows.filter((r) => (r.period.units ?? 0) > 0).length;
  const totalLoss = AREAS.reduce(
    (s, a) =>
      s + a.cover_loss.filter((l) => l.year > 2019 && l.year <= 2024).reduce((x, l) => x + l.area_ha, 0),
    0
  );

  /* Ряд потерь покрова по всем участкам — годы из данных, а не выдуманная ось */
  const lossYears = useMemo(() => {
    const map = new Map<number, number>();
    for (const a of AREAS) {
      for (const l of a.cover_loss) map.set(l.year, (map.get(l.year) ?? 0) + l.area_ha);
    }
    return [...map.entries()].sort((a, b) => a[0] - b[0]).map(([year, area_ha]) => ({ year, area_ha }));
  }, []);

  /* Глубина ряда. По умолчанию показан период анализа: 2011 год весит
     больше всех остальных лет вместе, и на полном ряде он придавливает
     их в полоску толщиной в пиксель — график перестаёт что-либо значить.
     Полный ряд никуда не делся, он открывается фильтром. */
  const shownLoss = useMemo(() => {
    const from = lossRange === "all" ? -Infinity : Number(lossRange);
    return lossYears.filter((l) => l.year >= from);
  }, [lossYears, lossRange]);

  return (
    <>
      <PageHead
        title="Обзор"
        subtitle="Состояние набора, результаты по всем участкам и то, где расчёт не даёт ответа"
      />

      <div className="ov">
        <div className="ov-tiles">
          <div className="tile tile--light">
            <span className="tile__label">Участков в наборе</span>
            <span className="tile__value tabular">{AREAS.length}</span>
            <span className="tile__note">
              {formatDecimal(totalArea, 0)} га суммарно · 2019—2024
            </span>
            <span className="tile__btn">
              <CircleBtn to="/app/areas" label="Открыть каталог участков" />
            </span>
          </div>

          <div className="tile tile--dark">
            <span className="tile__label">Показывают потерю углерода</span>
            <span className="tile__value tabular">
              {losing}
              <span className="tile__unit">из {AREAS.length}</span>
            </span>
            <span className="tile__note">за выбранный период, по разности запасов</span>
          </div>

          <div className="tile tile--lime">
            <span className="tile__label">Дают потенциальные единицы</span>
            <span className="tile__value tabular">
              {withUnits}
              <span className="tile__unit">из {AREAS.length}</span>
            </span>
            <span className="tile__note">
              на остальных результат не отличим от базовой линии
            </span>
          </div>
        </div>

        <div className="ov-row2">
          <Card className="ov-summary">
            <div className="ov-summary__head">
              <h2 className="card__title">Краткая справка по набору</h2>
              <span className="lvl lvl--outline">собрано шаблоном</span>
              <span className="ov-summary__spacer" />
              <CircleBtn
                glyph="⟳"
                onClick={regenerate}
                spinning={rebuilding}
                label="Пересобрать справку"
              />
            </div>
            <ul className="ov-summary__list">
              {summary.lines.map((line) => (
                <li key={line.text}>
                  <span className="ov-summary__value tabular">
                    {line.value}
                    {line.unit && <small>{line.unit}</small>}
                  </span>
                  <span className="ov-summary__why">{line.text}</span>
                </li>
              ))}
            </ul>
            <p className="ov-note">
              собрано из посчитанного · без языковой модели · обновлено {summary.at}
            </p>
          </Card>

          <Card className="ov-assets">
            <div className="ov-summary__head">
              <h2 className="card__title">Потери древесного покрова</h2>
              <span className="ov-summary__spacer" />
              <CircleBtn to="/app/areas" label="Разобрать по участкам" />
            </div>
            <div className="ov-assets__value tabular">
              {formatArea(Math.round(totalLoss))} <small>га</small>
            </div>
            <p className="ov-note" style={{ marginTop: 10 }}>
              2020—2024 по всем участкам, Hansen GFC v1.13, порог покрова{" "}
              {PARAMETERS.treecover_threshold_pct} %. Потеря — снижение древесного покрова, а не
              установленная вырубка.
            </p>
          </Card>
        </div>

        <Card className="ov-chart">
          <div className="ov-chart__head">
            <h2 className="card__title">Результат по участкам</h2>
            <span className="ov-chart__dash" aria-hidden="true" />
            <FilterSelect value={range} onChange={setRange} options={PERIODS} label="период" />
          </div>

          <div className="tbl__scroll">
            <table className="tbl">
              <thead>
                <tr>
                  <th>участок</th>
                  <th className="num">площадь, га</th>
                  <th className="num">запас {startYear}</th>
                  <th className="num">запас {endYear}</th>
                  <th className="num">E, т CO₂-экв.</th>
                  <th className="num">диапазон</th>
                  <th className="num">R</th>
                  <th>единицы</th>
                  <th>устойчивость</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ area, period }) => (
                  <tr key={area.aoi_id}>
                    <td>
                      <span className="tbl__name">
                        <Link to={`/app/area/${area.aoi_id}`}>
                          <b>{area.name}</b>
                        </Link>
                        <span>{area.role}</span>
                      </span>
                    </td>
                    <td className="num">{formatDecimal(area.area_ha, 0)}</td>
                    <td className="num">{formatDecimal(period.c_start_t_ha, 1)}</td>
                    <td className="num">{formatDecimal(period.c_end_t_ha, 1)}</td>
                    <td className="num">
                      <b>{formatNumber(Math.round(period.e_tco2e))}</b>
                    </td>
                    <td className="num" style={{ color: "var(--c-muted-alt)" }}>
                      {formatNumber(Math.round(period.lower_tco2e))} …{" "}
                      {formatNumber(Math.round(period.upper_tco2e))}
                    </td>
                    <td className="num" style={{ color: "var(--c-muted-alt)" }}>
                      {formatNumber(Math.round(period.r_tco2e))}
                    </td>
                    <td>
                      {period.units === null ? (
                        <span className="lvl lvl--none">недоступно</span>
                      ) : period.units === 0 ? (
                        <span className="lvl lvl--none" title={period.reason ?? undefined}>
                          0
                        </span>
                      ) : (
                        <span className="lvl lvl--low">{formatNumber(period.units)}</span>
                      )}
                    </td>
                    <td>
                      <LevelPill level={area.stability.level} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="ov-note">
            Положительное E означает потерю углерода из учитываемого пула, отрицательное —
            накопление. Ноль в колонке единиц — расчёт выполнен и дал ноль; «недоступно» — расчёт
            не выполнялся из-за неполных входных данных. Это разные ответы. Устойчивость —
            скрининг на горизонт 2024—2029, на число единиц он не влияет.
          </p>
        </Card>

        <Card tone="dark" className="ov-market card--ink">
          <div className="ov-market__head">
            <h2 className="card__title">Условия расчёта</h2>
            <span className="ov-summary__spacer" />
            <CircleBtn tone="lime" to="/app/methodology" label="Открыть методику" />
          </div>

          <span className="ov-market__label">ценовой сценарий · {label}</span>
          <span className="ov-market__price tabular">
            {formatNumber(price)} <small>₽/ед.</small>
          </span>
          {/* Цены выбираются здесь и действуют во всём приложении.
              На физические показатели и на число единиц выбор не влияет:
              цена умножается уже на готовое Q. */}
          <ul className="ov-market__scenarios">
            {PRICE_SCENARIOS.map((sc) => (
              <li key={sc.key}>
                <button
                  type="button"
                  className={priceKey === sc.key ? "is-active" : ""}
                  aria-pressed={priceKey === sc.key}
                  onClick={() => setPriceKey(sc.key)}
                >
                  <span>{sc.label}</span>
                  <span className="tabular">{formatNumber(sc.price)} ₽</span>
                </button>
              </li>
            ))}
          </ul>
          <span className="ov-market__note">
            Заданы условиями кейса. Не прогноз рыночной цены
          </span>

          <div className="ov-market__divider" />
          <span className="ov-market__label">базовая линия</span>
          <span className="ov-market__value tabular">2019 — 2029</span>
          <span className="ov-market__note">
            продолжение исторической динамики 2015—2019, задана набором и не
            устанавливает дополнительность
          </span>

          <div className="ov-market__divider" />
          <Link to="/app/methodology" className="ov-market__cta">
            Как это считается
          </Link>
        </Card>

        <Card className="ov-gauge">
          <div className="ov-summary__head">
            <h2 className="card__title">Потери покрова по годам</h2>
            <span className="ov-summary__spacer" />
            <FilterSelect
              value={lossRange}
              onChange={setLossRange}
              options={LOSS_RANGES}
              label="глубина ряда"
            />
            <CircleBtn to="/app/areas" label="Открыть участки" />
          </div>

          <YearLossChart
            rows={shownLoss}
            isWithin={(year) => year >= YEARS[0] && year <= YEARS[YEARS.length - 1]}
            badgeLabel={`${shownLoss.length} ${plural(shownLoss.length, ["год", "года", "лет"])} наблюдения`}
            caption={
              <>
                суммарная площадь, потерявшая
                <br />
                древесный покров за показанные годы
              </>
            }
            renderPicked={(row) => (
              <ul className="yloss__breakdown">
                {AREAS.map((a) => ({
                  area: a,
                  area_ha: a.cover_loss.find((l) => l.year === row.year)?.area_ha ?? 0,
                }))
                  .filter((r) => r.area_ha > 0)
                  .sort((a, b) => b.area_ha - a.area_ha)
                  .map((r) => (
                    <li key={r.area.aoi_id}>
                      <Link to={`/app/area/${r.area.aoi_id}`}>{r.area.name}</Link>
                      <span className="tabular">{formatDecimal(r.area_ha, 1)} га</span>
                    </li>
                  ))}
              </ul>
            )}
          />

          <p className="ov-note">
            Площади, потерявшие древесный покров по Hansen GFC v1.13, порог покрова{" "}
            {PARAMETERS.treecover_threshold_pct} %. Причина потери продуктом не определяется:
            столбец отвечает на вопрос «сколько», а не «почему». По умолчанию показан период
            анализа: на полном ряде 2011 год даёт 74 % всех потерь и придавливает остальные
            двадцать четыре в полоску. Полный ряд открывается фильтром.
          </p>
        </Card>
      </div>

      <Card title="Что в наборе" className="ov-attention">
        <ul className="attention">
          {AREAS.map((a) => (
            <li key={a.aoi_id}>
              <Link to={`/app/area/${a.aoi_id}`} className="attention__name">
                {a.name}
              </Link>
              <span className="attention__why">
                {a.region} · {formatBbox(a.bbox)} · базовая линия{" "}
                {formatDecimal(a.baseline_rate_tc_ha_year, 3)} т C/га/год
              </span>
              <span
                className={a.role === "контрольный участок" ? "lvl lvl--low" : "lvl lvl--none"}
              >
                {a.role}
              </span>
            </li>
          ))}
        </ul>
        <p className="ov-note">
          Все четыре участка имеют статус исследовательских и не являются зарегистрированными
          климатическими проектами — это записано в самом наборе.
        </p>
      </Card>
    </>
  );
}
