import { Link } from "react-router-dom";
import { Card, CircleBtn, LevelPill, formatNumber } from "../../components/ui";
import { PageHead } from "../../components/AppShell";
import {
  DATA_COMPLETENESS,
  DISTURBANCE_SERIES,
  PROJECTS,
  REGISTRY_META,
  SUMMARY,
} from "../../data/mock";
import "./Overview.css";

/* Раздел «Обзор». Требования FR-05 — FR-08.

   На шкале выводится ВАЛИДНОЕ ПОКРЫТИЕ ТЕРРИТОРИИ, а не доверие к измерению:
   доверие числом показывать запрещено (FR-36), покрытие — измеренная доля
   площади, её можно. Подпись под шкалой обязательна. */

const TILES = [
  {
    label: "проектов в реестре",
    value: String(REGISTRY_META.total),
    unit: "",
    note: `открытая часть, выгрузка ${REGISTRY_META.export_date}`,
    tone: "light" as const,
  },
  {
    label: "единиц в обращении",
    value: REGISTRY_META.units_in_circulation_mln,
    unit: "млн",
    note: `${REGISTRY_META.issued_2026_mln} млн выпущено в 2026 году`,
    tone: "dark" as const,
  },
  {
    label: "с загруженными границами",
    value: String(REGISTRY_META.with_geometry),
    unit: `из ${REGISTRY_META.total}`,
    note: "реестр не публикует геометрию проектов",
    tone: "lime" as const,
  },
  {
    label: "ориентир цены",
    value: `~${REGISTRY_META.price_hint_rub}`,
    unit: "₽/ед",
    note: "по сделкам 2026 года, не котировка",
    tone: "light" as const,
  },
];

const PRICE_SCENARIOS = [
  { name: "пессимистичный", price: "400 ₽", active: false },
  { name: "базовый", price: "700 ₽", active: true },
  { name: "оптимистичный", price: "1 100 ₽", active: false },
];

export default function Overview() {
  const values = DISTURBANCE_SERIES.map((d) => d.area_ha ?? 0);
  const max = Math.max(...values, 1);
  const total = values.reduce((a, b) => a + b, 0);

  const ticks = 27;
  const filled = Math.round((ticks * DATA_COMPLETENESS.valid_coverage_pct) / 100);

  return (
    <>
      <PageHead
        title="Обзор"
        subtitle="Состояние реестра, наших данных и что изменилось за последний месяц"
      />

      <div className="ov-tiles">
        {TILES.map((t) => (
          <div key={t.label} className={`tile tile--${t.tone}`}>
            <span className="tile__label">{t.label}</span>
            <span className="tile__value tabular">
              {t.value}
              {t.unit && <span className="tile__unit">{t.unit}</span>}
            </span>
            <span className="tile__note">{t.note}</span>
          </div>
        ))}
      </div>

      <div className="ov-row">
        {/* Краткая справка: только пересказ посчитанного, новых выводов не делает */}
        <Card className="ov-summary">
          <div className="ov-summary__head">
            <h2 className="card__title">Краткая справка</h2>
            <span className="lvl lvl--low">сгенерировано</span>
            <span className="ov-summary__spacer" />
            <CircleBtn glyph="⟳" />
          </div>
          <p className="ov-summary__text">{SUMMARY.text}</p>
          <div className="ov-summary__foot">
            <span>опирается на</span>
            {SUMMARY.based_on.map((id) => (
              <span key={id} className="chip">
                {id}
              </span>
            ))}
            <span>· только пересказ посчитанного</span>
          </div>
        </Card>

        {/* Рынок и каталог — вертикальная карточка */}
        <Card tone="dark" className="ov-market">
          <div className="ov-market__head">
            <h2 className="card__title">Рынок и каталог</h2>
            <span className="ov-summary__spacer" />
            <CircleBtn tone="lime" />
          </div>
          <span className="ov-market__label">ориентир цены</span>
          <span className="ov-market__price tabular">
            ~700 <small>₽/ед</small>
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
      </div>

      <div className="ov-row ov-row--bottom">
        {/* Нарушения по годам. Столбики нормированы по максимуму ряда,
            иначе пик 2021 года схлопывает все остальные в линию.
            Год без валидных наблюдений остаётся пустым. */}
        <Card title="Нарушения по годам, га" note={`суммарно ${formatNumber(total)} га за 12 лет`} className="ov-chart">
          <div className="bars">
            {DISTURBANCE_SERIES.map((d) => {
              const missing = d.area_ha === null;
              const h = missing ? 0 : Math.max(((d.area_ha as number) / max) * 190, 4);
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
          <p className="ov-note">
            Пик 2021 года — пожар на 840 га. Пустые столбцы — годы без валидных наблюдений:
            значение не подставляется из соседних.
          </p>
        </Card>

        {/* Валидное покрытие — измеренная величина, не оценка доверия */}
        <Card title="Валидное покрытие" className="ov-gauge">
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
                  : `свежие нарушения ${p.recent_loss_ha} га`}
              </span>
              <LevelPill level={p.vulnerability_level} />
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
