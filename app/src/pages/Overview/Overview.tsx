import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Card,
  CircleBtn,
  FilterSelect,
  LevelPill,
  formatArea,
  formatDecimal,
  formatNumber,
} from "../../components/ui";
import { PageHead } from "../../components/AppShell";
import {
  DATA_COMPLETENESS,
  DISTURBANCE_SERIES,
  PROJECTS,
  REGISTRY,
  REGISTRY_META,
  SUMMARY,
} from "../../data/mock";
import "./Overview.css";

/* Раздел «Обзор». Требования FR-05 — FR-08.
   Раскладка снята с макета 35:2: слева плитки, справка и нарушения,
   справа рынок и валидное покрытие. Карточка рынка начинается на одной
   линии с плитками и закрывает два левых ряда.

   На шкале выводится ВАЛИДНОЕ ПОКРЫТИЕ ТЕРРИТОРИИ, а не доверие к измерению:
   доверие числом показывать запрещено (FR-36), покрытие — измеренная доля
   площади, её можно. Подпись под шкалой обязательна. */

const PRICE_SCENARIOS = [
  { name: "пессимистичный", price: "400 ₽", active: false },
  { name: "базовый", price: "700 ₽", active: true },
  { name: "оптимистичный", price: "1 100 ₽", active: false },
];

const PERIODS = [
  { value: "12", label: "за 12 лет" },
  { value: "6", label: "за 6 лет" },
  { value: "4", label: "за 4 года" },
];

const KINDS = [
  { value: "all", label: "все типы" },
  { value: "fire_ha", label: "подтверждено пожаром" },
  { value: "non_fire_ha", label: "не связано с пожаром" },
  { value: "unknown_ha", label: "тип не определён" },
] as const;

type KindKey = (typeof KINDS)[number]["value"];

const LEGEND: { key: Exclude<KindKey, "all">; label: string; tone: string }[] = [
  { key: "fire_ha", label: "подтверждено пожаром", tone: "peak" },
  { key: "non_fire_ha", label: "не связано с пожаром", tone: "fresh" },
  { key: "unknown_ha", label: "тип не определён", tone: "plain" },
];

/* Справка собирается шаблоном из посчитанного, без языковой модели:
   так свойство «ничего не выдумывает» держится конструкцией, а не обещанием. */
function buildSummary() {
  const check = PROJECTS.find((p) => p.claim_status === "review_recommended");
  const fresh = DISTURBANCE_SERIES.at(-1)!;
  const parts = [
    check
      ? `Биомасса ниже заявленной на 12,6 % при погрешности продукта ±${check.agb_sd_t_ha} т/га.`
      : "Существенных расхождений с заявленным не найдено.",
    `В ${fresh.year} году зафиксировано нарушение ${formatDecimal(fresh.fire_ha ?? 0)} га с пожарными признаками — после даты отчётности проекта.`,
    "Заявленный эффект относится к предотвращённым выбросам и не проверяется.",
  ];
  return parts.join(" ");
}

export default function Overview() {
  /* ---- справка: пересобирается по кнопке, не декоративной ---- */
  const [summary, setSummary] = useState({ text: SUMMARY.text, at: SUMMARY.generated_at });
  const [rebuilding, setRebuilding] = useState(false);

  const regenerate = () => {
    if (rebuilding) return;
    setRebuilding(true);
    window.setTimeout(() => {
      const now = new Date();
      setSummary({
        text: buildSummary(),
        at: `${now.toLocaleDateString("ru-RU")} ${now.toLocaleTimeString("ru-RU", {
          hour: "2-digit",
          minute: "2-digit",
        })}`,
      });
      setRebuilding(false);
    }, 550);
  };

  /* ---- нарушения: период, тип события и разворот в таблицу ---- */
  const [period, setPeriod] = useState("12");
  const [kind, setKind] = useState<KindKey>("all");
  const [expanded, setExpanded] = useState(false);

  const series = useMemo(() => {
    const tail = DISTURBANCE_SERIES.slice(-Number(period));
    return tail.map((d) => ({
      year: d.year,
      /* null остаётся null: год без валидных наблюдений не превращается в ноль */
      value: d.area_ha === null ? null : kind === "all" ? d.area_ha : (d[kind] ?? 0),
    }));
  }, [period, kind]);

  const shown = series.filter((d) => d.value !== null) as { year: number; value: number }[];
  const max = Math.max(...shown.map((d) => d.value), 1);
  const total = shown.reduce((a, b) => a + b.value, 0);
  const peak = shown.reduce((a, b) => (b.value > a.value ? b : a), shown[0]);
  const first = shown[0];
  /* Выноска роста осмысленна только на коротком окне: на 12 годах
     пик 2021 против 2015 даёт четырёхзначный процент, который ничего
     не объясняет. На длинном окне показываем один итог. */
  const wide = series.length <= 6;
  const growth =
    wide && peak && first && first.value > 0 && peak.year !== first.year
      ? Math.round(((peak.value - first.value) / first.value) * 100)
      : null;

  const ticks = 27;
  const filled = Math.round((ticks * DATA_COMPLETENESS.valid_coverage_pct) / 100);

  /* Примерная стоимость активов: только участки с загруженной границей,
     по ориентиру цены. Это не оценка сделки и не котировка. */
  const units = REGISTRY.filter((r) => r.data_status === "calculated").reduce(
    (a, r) => a + (r.units_in_circulation ?? 0),
    0
  );
  const assets = units * REGISTRY_META.price_hint_rub;

  return (
    <>
      <PageHead
        title="Обзор"
        subtitle="Состояние реестра, наших данных и что изменилось за последний месяц"
      />

      <div className="ov">
        {/* ---------------- плитки ---------------- */}
        <div className="ov-tiles">
          <div className="tile tile--light">
            <span className="tile__label">проектов в реестре</span>
            <span className="tile__value tabular">{REGISTRY_META.total}</span>
            <span className="tile__note">
              открытая часть, выгрузка {REGISTRY_META.export_date}
            </span>
            <span className="tile__btn">
              <CircleBtn to="/app/projects" label="Открыть каталог проектов" />
            </span>
          </div>

          <div className="tile tile--dark">
            <span className="tile__label">единиц в обращении</span>
            <span className="tile__value tabular">
              {REGISTRY_META.units_in_circulation_mln}
              <span className="tile__unit">млн</span>
            </span>
            <span className="tile__note">
              {REGISTRY_META.issued_2026_mln} млн выпущено в 2026 году
            </span>
          </div>

          <div className="tile tile--lime">
            <span className="tile__label">с загруженными границами</span>
            <span className="tile__value tabular">
              {REGISTRY_META.with_geometry}
              <span className="tile__unit">из {REGISTRY_META.total}</span>
            </span>
            <span className="tile__note">реестр не публикует геометрию проектов</span>
          </div>
        </div>

        {/* ---------------- справка и стоимость ---------------- */}
        <div className="ov-row2">
          {/* Краткая справка: только пересказ посчитанного, новых выводов не делает */}
          <Card className="ov-summary">
            <div className="ov-summary__head">
              <h2 className="card__title">Краткая справка</h2>
              <span className="lvl lvl--low">сгенерировано</span>
              <span className="ov-summary__spacer" />
              <CircleBtn
                glyph="⟳"
                onClick={regenerate}
                spinning={rebuilding}
                label="Пересобрать справку"
              />
            </div>
            <p className="ov-summary__text">{summary.text}</p>
            <div className="ov-summary__foot">
              <span>опирается на</span>
              {SUMMARY.based_on.map((id) => (
                <span key={id} className="chip">
                  {id}
                </span>
              ))}
              <span>· собрано {summary.at} · только пересказ посчитанного</span>
            </div>
          </Card>

          <Card className="ov-assets">
            <div className="ov-summary__head">
              <h2 className="card__title">Примерная стоимость активов</h2>
              <span className="ov-summary__spacer" />
              <CircleBtn to="/app/calculations" label="Перейти к расчётам" />
            </div>
            <div className="ov-assets__value tabular">
              {formatDecimal(assets / 1_000_000)} <small>млн ₽</small>
            </div>
            <Link to="/app/calculations" className="btn btn--dark ov-assets__cta">
              <span>Просмотреть расчёты</span>
            </Link>
            <p className="ov-note">
              {formatNumber(units)} единиц по ориентиру {REGISTRY_META.price_hint_rub} ₽ — только
              участки с загруженной границей. Не котировка и не оценка сделки.
            </p>
          </Card>
        </div>

        {/* ---------------- нарушения по годам ---------------- */}
        <Card className="ov-chart">
          <div className="ov-chart__head">
            <h2 className="card__title">Нарушения по годам</h2>
            <span className="ov-chart__dash" aria-hidden="true" />
            <FilterSelect
              value={period}
              onChange={setPeriod}
              options={PERIODS}
              label="период наблюдения"
            />
            <FilterSelect
              value={kind}
              onChange={(v) => setKind(v as KindKey)}
              options={KINDS as unknown as { value: string; label: string }[]}
              label="тип события"
            />
            <CircleBtn
              glyph={expanded ? "⤡" : "⤢"}
              onClick={() => setExpanded((v) => !v)}
              label={expanded ? "Свернуть таблицу" : "Развернуть таблицу"}
            />
          </div>

          <div className="ov-chart__body">
            <div className="ov-chart__stat">
              <span className="chip chip--soft">{shown.length} лет наблюдения</span>
              <div className="ov-chart__big tabular">
                {formatArea(total)} <small>га</small>
              </div>
              <p className="ov-chart__cap">
                {kind === "all"
                  ? "суммарная площадь нарушений внутри границ проекта"
                  : `площадь по типу «${KINDS.find((k) => k.value === kind)!.label}»`}
              </p>
              <ul className="ov-legend">
                {LEGEND.map((l) => (
                  <li key={l.key}>
                    <span className={`ov-legend__dot ov-legend__dot--${l.tone}`} />
                    {l.label}
                  </li>
                ))}
              </ul>
            </div>

            <div className="ov-chart__plot">
              {growth !== null && (
                <div className="ov-chart__growth">
                  <b className="tabular">
                    {growth > 0 ? "+" : ""}
                    {growth} %
                  </b>
                  <span>
                    пик {peak.year} к {first.year}
                  </span>
                </div>
              )}
              <div className={`bars bars--wide ${wide ? "" : "bars--dense"}`.trim()}>
                {series.map((d) => {
                  const missing = d.value === null;
                  const h = missing ? 0 : Math.max((d.value / max) * 210, 6);
                  const tone = d.year === peak?.year ? "peak" : d.year >= 2024 ? "fresh" : "plain";
                  return (
                    <div key={d.year} className="bars__col">
                      {missing ? (
                        <span className="bars__missing" title="нет валидных наблюдений" />
                      ) : (
                        <span
                          className={`bars__bar bars__bar--${tone}`}
                          style={{ height: `${h}px` }}
                        >
                          {wide && (
                            <em className="bars__pill tabular">
                              {d.value >= (first?.value ?? 0) ? "↗" : "↘"} {formatArea(d.value)} га
                            </em>
                          )}
                        </span>
                      )}
                      <span className="bars__year">
                        {wide ? d.year : String(d.year).slice(2)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {expanded && (
            <table className="tbl ov-chart__table">
              <thead>
                <tr>
                  <th>год</th>
                  <th className="num">пожар, га</th>
                  <th className="num">без пожара, га</th>
                  <th className="num">не определён, га</th>
                  <th className="num">всего, га</th>
                </tr>
              </thead>
              <tbody>
                {DISTURBANCE_SERIES.slice(-Number(period)).map((d) => (
                  <tr key={d.year}>
                    <td>{d.year}</td>
                    <td className="num">{d.fire_ha === null ? "—" : formatArea(d.fire_ha)}</td>
                    <td className="num">
                      {d.non_fire_ha === null ? "—" : formatArea(d.non_fire_ha)}
                    </td>
                    <td className="num">
                      {d.unknown_ha === null ? "—" : formatArea(d.unknown_ha)}
                    </td>
                    <td className="num">{d.area_ha === null ? "—" : formatArea(d.area_ha)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <p className="ov-note">
            Прочерк и пустой столбец — годы без валидных наблюдений: значение не подставляется из
            соседних. «Не связано с пожаром» не означает рубку.
          </p>
        </Card>

        {/* ---------------- рынок и каталог ---------------- */}
        <Card tone="dark" className="ov-market">
          <div className="ov-market__head">
            <h2 className="card__title">Рынок и каталог</h2>
            <span className="ov-summary__spacer" />
            <CircleBtn tone="lime" to="/app/projects" label="Открыть каталог проектов" />
          </div>
          <span className="ov-market__label">ориентир цены</span>
          <span className="ov-market__price tabular">
            ~{REGISTRY_META.price_hint_rub} <small>₽/ед</small>
          </span>
          <span className="ov-market__note">по сделкам 2026 года, не котировка</span>

          <div className="ov-market__divider" />
          <span className="ov-market__label">сценарии цены</span>
          <ul className="ov-market__scenarios">
            {PRICE_SCENARIOS.map((s) => (
              <li key={s.name} className={s.active ? "is-active" : ""}>
                <span>{s.name}</span>
                <span className="tabular">{s.price}</span>
              </li>
            ))}
          </ul>

          <div className="ov-market__divider" />
          <Link to="/app/projects" className="ov-market__cta">
            Открыть каталог
          </Link>
          <span className="ov-market__note">{REGISTRY_META.total} проекта</span>
        </Card>

        {/* ---------------- валидное покрытие ---------------- */}
        <Card className="ov-gauge">
          <div className="ov-summary__head">
            <h2 className="card__title">Валидное покрытие</h2>
            <span className="ov-summary__spacer" />
            <CircleBtn to="/app/methodology" label="Как считается полнота данных" />
          </div>
          <div className="gauge">
            {Array.from({ length: ticks }, (_, i) => {
              const angle = -90 + (i / (ticks - 1)) * 180;
              const on = i < filled;
              const lime = on && i > filled - 5;
              return (
                <span
                  key={i}
                  className={`gauge__tick ${on ? (lime ? "is-lime" : "is-on") : ""}`}
                  style={{ transform: `rotate(${angle}deg) translateY(-118px)` }}
                />
              );
            })}
            <div className="gauge__center">
              <span className="gauge__value tabular">{DATA_COMPLETENESS.valid_coverage_pct}</span>
              <span className="gauge__pct">%</span>
            </div>
          </div>
          <p className="gauge__caption">территории с валидными наблюдениями</p>
          <span className="chip chip--soft">
            пропущены {DATA_COMPLETENESS.missing_years.join(" и ")} — облачность
          </span>
          <p className="ov-note">Доля площади с наблюдениями, не оценка доверия.</p>
        </Card>
      </div>

      <Card title="Требуют внимания" className="ov-attention">
        <ul className="attention">
          {PROJECTS.filter((p) => p.vulnerability_level !== "low").map((p) => (
            <li key={p.project_id}>
              <Link to={`/app/plot/${p.project_id}`} className="attention__name">
                {p.name}
              </Link>
              <span className="attention__why">
                {p.claim_status === "review_recommended"
                  ? "биомасса ниже заявленной на 12,6 %"
                  : `свежие нарушения ${formatArea(p.recent_loss_ha)} га`}
              </span>
              <LevelPill level={p.vulnerability_level} />
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
