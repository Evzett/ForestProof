import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Card,
  Checkbox,
  FilterSelect,
  FilterToggle,
  SearchField,
  formatDecimal,
  formatNumber,
  plural,
} from "../../components/ui";
import { AddPlotButton, PageHead } from "../../components/AppShell";
import { AREAS, EVENTS, ROLE_HINT, formatBbox } from "../../data/case";
import type { Area } from "../../data/case";
import "./Areas.css";

/* Каталог участков. В наборе кейса это исследовательские участки,
   а не зарегистрированные климатические проекты — так и подписано
   в самом наборе, и подменять это словом «проект» нельзя. */

const ROLES = [
  { value: "all", label: "роль: все" },
  { value: "контрольный участок", label: "контрольный участок" },
  { value: "повторные нарушения и пожар", label: "нарушения и пожар" },
  { value: "ранние потери покрова и последующий пожар", label: "ранние потери и пожар" },
  {
    value: "недавние потери покрова с неустановленной причиной",
    label: "потери без установленной причины",
  },
];

const SIGNS = [
  { value: "all", label: "результат: любой" },
  { value: "loss", label: "потеря углерода" },
  { value: "gain", label: "накопление" },
];

/* Самое свежее годное наблюдение. Негодные сцены сюда не попадают:
   снимок, закрытый облаком на 98 %, показывает облако, а не лес, — и
   на обложке выглядел бы как поломка, хотя это штатное состояние
   наблюдения. */
function coverScene(area: Area): { image: string; date: string } | null {
  const usable = (area.sentinel?.observations ?? []).filter((o) => o.usable && o.image);
  if (usable.length === 0) return null;
  const latest = usable.reduce((a, b) => (a.date >= b.date ? a : b));
  return { image: latest.image, date: latest.date };
}

export default function Areas() {
  /* Что на обложке: снимок или карта изменений. Переключатель общий на
     все карточки — свой на каждой превратил бы список в россыпь
     органов управления, а сравнивать участки проще, когда они показаны
     одинаково. */
  const [cover, setCover] = useState<"scene" | "change">("scene");

  const [query, setQuery] = useState("");
  const [region, setRegion] = useState("all");
  const [role, setRole] = useState("all");
  const [sign, setSign] = useState("all");
  const [onlyEvents, setOnlyEvents] = useState(false);
  const [picked, setPicked] = useState<string[]>([AREAS[0].aoi_id, AREAS[2].aoi_id]);
  const navigate = useNavigate();

  const regions = useMemo(
    () => [
      { value: "all", label: "регион: все" },
      ...Array.from(new Set(AREAS.map((a) => a.region)))
        .sort((a, b) => a.localeCompare(b, "ru"))
        .map((v) => ({ value: v, label: v })),
    ],
    []
  );

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return AREAS.filter((a) => {
      if (q && ![a.name, a.aoi_id, a.region].some((f) => f.toLowerCase().includes(q))) return false;
      if (region !== "all" && a.region !== region) return false;
      if (role !== "all" && a.role !== role) return false;
      if (sign === "loss" && a.period_2019_2024.e_tco2e <= 0) return false;
      if (sign === "gain" && a.period_2019_2024.e_tco2e > 0) return false;
      if (onlyEvents && !EVENTS.some((e) => e.aoi_id === a.aoi_id)) return false;
      return true;
    });
  }, [query, region, role, sign, onlyEvents]);

  const filtersOn =
    query.trim() !== "" || region !== "all" || role !== "all" || sign !== "all" || onlyEvents;

  const reset = () => {
    setQuery("");
    setRegion("all");
    setRole("all");
    setSign("all");
    setOnlyEvents(false);
  };

  const toggle = (id: string) =>
    setPicked((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 4 ? [...prev, id] : prev
    );

  const full = picked.length >= 4;

  return (
    <>
      <PageHead
        title="Участки"
        subtitle={`${AREAS.length} ${plural(AREAS.length, [
          "исследовательский участок",
          "исследовательских участка",
          "исследовательских участков",
        ])} в наборе. Это не зарегистрированные климатические проекты — так помечены сами данные`}
        action={<AddPlotButton label="Задать свой контур" />}
      />

      <div className="filters">
        <SearchField
          value={query}
          onChange={setQuery}
          placeholder="поиск по названию, региону или идентификатору"
        />
        <FilterSelect value={region} onChange={setRegion} options={regions} label="регион" />
        <FilterSelect value={role} onChange={setRole} options={ROLES} label="роль участка" />
        <FilterSelect value={sign} onChange={setSign} options={SIGNS} label="знак результата" />
        <FilterToggle on={onlyEvents} onClick={() => setOnlyEvents((v) => !v)}>
          только с подтверждённым событием
        </FilterToggle>
        {filtersOn && (
          <button className="filter filter--btn" type="button" onClick={reset}>
            сбросить ✕
          </button>
        )}
      </div>

      {picked.length >= 2 && (
        <div className="selbar">
          <b>Выбрано {picked.length}</b>
          <span className="selbar__hint">
            {full ? "больше четырёх колонок не читается" : "сравнение доступно для 2–4 участков"}
          </span>
          <span className="selbar__spacer" />
          <button
            className="btn btn--lime btn--inline"
            type="button"
            onClick={() => navigate(`/app/compare?ids=${picked.join(",")}`)}
          >
            <span>Сравнить</span>
            <span className="btn__arrow">→</span>
          </button>
        </div>
      )}

      <div className="areas__cover-switch">
        <span>на обложке</span>
        <button
          type="button"
          className={cover === "scene" ? "filter filter--on" : "filter"}
          onClick={() => setCover("scene")}
        >
          спутниковый снимок
        </button>
        <button
          type="button"
          className={cover === "change" ? "filter filter--on" : "filter"}
          onClick={() => setCover("change")}
        >
          карта изменений
        </button>
      </div>

      <div className="areas scrollbox">
        {rows.map((a) => {
          const p = a.period_2019_2024;
          const events = EVENTS.filter((e) => e.aoi_id === a.aoi_id);
          const loss = a.cover_loss
            .filter((l) => l.year > 2019 && l.year <= 2024)
            .reduce((s, l) => s + l.area_ha, 0);
          return (
            <Card key={a.aoi_id} className="area">
              <div className="area__map">
                {(() => {
                  const scene = cover === "scene" ? coverScene(a) : null;
                  if (scene) {
                    return (
                      <>
                        <img src={`/maps/${scene.image}`} alt={`Снимок участка ${a.name}`} />
                        <span className="area__date">снимок {scene.date}</span>
                      </>
                    );
                  }
                  return a.maps ? (
                    <>
                      <img src={`/maps/${a.maps.change}`} alt="" />
                      <span className="area__date">
                        {cover === "scene" ? "годного снимка нет" : "изменение запаса"}
                      </span>
                    </>
                  ) : null;
                })()}
                <span className="area__pick">
                  <Checkbox
                    checked={picked.includes(a.aoi_id)}
                    disabled={full && !picked.includes(a.aoi_id)}
                    onChange={() => toggle(a.aoi_id)}
                    label={`выбрать ${a.name} для сравнения`}
                    reason="уже выбрано четыре участка"
                  />
                </span>
                <span className="area__role">{a.role}</span>
              </div>

              <h3 className="area__name">
                <Link to={`/app/area/${a.aoi_id}`}>{a.name}</Link>
              </h3>
              <p className="area__meta">
                {a.aoi_id} · {a.region} · {formatDecimal(a.area_ha, 1)} га
              </p>
              {ROLE_HINT[a.role] && <p className="area__hint">{ROLE_HINT[a.role]}</p>}

              <dl className="area__kv">
                <div>
                  <dt>запас 2019 → 2024</dt>
                  <dd className="tabular">
                    {formatDecimal(p.c_start_t_ha, 1)} → {formatDecimal(p.c_end_t_ha, 1)} т C/га
                  </dd>
                </div>
                <div>
                  <dt>результат за период</dt>
                  <dd className="tabular">
                    {p.e_tco2e > 0 ? "+" : "−"}
                    {formatNumber(Math.abs(Math.round(p.e_tco2e)))} т CO₂-экв.
                  </dd>
                </div>
                <div>
                  <dt>диапазон</dt>
                  <dd className="tabular">
                    {formatNumber(Math.round(p.lower_tco2e))} …{" "}
                    {formatNumber(Math.round(p.upper_tco2e))}
                  </dd>
                </div>
                <div>
                  <dt>базовая линия</dt>
                  <dd className="tabular">
                    {formatDecimal(a.baseline_rate_tc_ha_year, 3)} т C/га/год
                  </dd>
                </div>
                <div>
                  <dt>потери покрова 2020—2024</dt>
                  <dd className="tabular">{formatDecimal(loss, 1)} га</dd>
                </div>
                <div>
                  <dt>потенциальные единицы</dt>
                  <dd>
                    {p.units === null ? (
                      <span className="lvl lvl--none">недоступно</span>
                    ) : p.units === 0 ? (
                      <span className="lvl lvl--none">0</span>
                    ) : (
                      <span className="lvl lvl--low">{formatNumber(p.units)}</span>
                    )}
                  </dd>
                </div>
              </dl>

              <p className="area__why">
                {p.reason ?? "результат превышает базовую линию"}
                {events.length > 0 && ` · событие с подтверждением: ${events[0].cause_supported}`}
              </p>
              <p className="area__bbox">контур {formatBbox(a.bbox)}</p>

              <p className="area__legend">
                <b>изменение запаса 2019 → 2024.</b> Один квадрат — один пиксель продукта
                ESA CCI, около 0,54 га. Коричневый — потеря, зелёный — накопление. Картинка
                не сглажена намеренно: сглаживание дорисовало бы детали, которых в данных нет.
              </p>

              <Link to={`/app/area/${a.aoi_id}`} className="row-action area__open">
                открыть расчёт →
              </Link>
            </Card>
          );
        })}
      </div>

      {rows.length === 0 && (
        <Card>
          <p className="empty">
            Под фильтры не подходит ни один участок.{" "}
            <button className="link-btn" type="button" onClick={reset}>
              сбросить фильтры
            </button>
          </p>
        </Card>
      )}

      <Card title="Что означают роли участков" className="mb20">
        <p className="ov-note" style={{ marginTop: 0 }}>
          Роль задана самим набором в поле <code>selection_role</code>. Контрольный участок нужен,
          чтобы отличать реальное изменение от свойств метода: если на нём результат уезжает так
          же, как на участке с нарушением, дело в данных, а не в лесе. Все четыре участка имеют
          статус исследовательских и не являются зарегистрированными климатическими проектами.
        </p>
      </Card>
    </>
  );
}
