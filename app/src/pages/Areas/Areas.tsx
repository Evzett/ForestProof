import { useEffect, useMemo, useState } from "react";
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
import { ApiError, getContours, type SavedContour } from "../../api";
import "./Areas.css";

/* Каталог участков. В наборе кейса это исследовательские участки,
   а не зарегистрированные климатические проекты — так и подписано
   в самом наборе, и подменять это словом «проект» нельзя.

   Загруженные пользователем контуры лежат здесь же, а не в отдельном
   разделе. Отдельный раздел означал бы, что свой участок — что-то другое,
   второго сорта. На деле это ровно тот же объект: тот же расчёт, теми же
   формулами, по тем же продуктам. Разница только в происхождении границы
   и базовой линии, и она подписана на карточке.

   Данные под чужой контур подтягиваются из открытых источников окном по
   HTTP Range — в этом и состоит работа сервиса. Участки набора посчитаны
   заранее и показываются без сети; свои контуры приходят от API. */

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

const ORIGINS = [
  { value: "all", label: "происхождение: все" },
  { value: "case", label: "участки набора" },
  { value: "mine", label: "мои контуры" },
];

/* Самое свежее годное наблюдение. Негодные сцены сюда не попадают:
   снимок, закрытый облаком на 98 %, показывает облако, а не лес, — и
   на обложке выглядел бы как поломка, хотя это штатное состояние
   наблюдения. */
function coverScene(area: Area): { image: string; date: string } | null {
  /* Снимки, вложенные в набор, идут первыми: они пришли с данными
     кейса, и подменять их собранными нами нельзя. Для остальных
     участков берётся наше превью. */
  const usable = (area.sentinel?.observations ?? []).filter((o) => o.usable && o.image);
  if (usable.length > 0) {
    const latest = usable.reduce((a, b) => (a.date >= b.date ? a : b));
    return { image: latest.image, date: latest.date };
  }
  if (area.scene_preview) {
    return { image: area.scene_preview.image, date: area.scene_preview.date };
  }
  return null;
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
  const [origin, setOrigin] = useState("all");
  const [picked, setPicked] = useState<string[]>([AREAS[0].aoi_id, AREAS[2].aoi_id]);
  const navigate = useNavigate();

  /* Свои контуры живут на сервере: предпосчитать их нельзя, и без API их
     просто нет. Это не ошибка — участки набора при этом открываются. */
  const [mine, setMine] = useState<SavedContour[]>([]);
  const [mineError, setMineError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getContours()
      .then((data) => !cancelled && setMine(data.contours))
      .catch((err) => {
        if (cancelled) return;
        setMine([]);
        setMineError(
          err instanceof ApiError && err.status !== 0
            ? err.message
            : "Сервис расчёта недоступен — загруженные контуры не показаны."
        );
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
    if (origin === "mine") return [];
    return AREAS.filter((a) => {
      if (q && ![a.name, a.aoi_id, a.region].some((f) => f.toLowerCase().includes(q))) return false;
      if (region !== "all" && a.region !== region) return false;
      if (role !== "all" && a.role !== role) return false;
      if (sign === "loss" && a.period_2019_2024.e_tco2e <= 0) return false;
      if (sign === "gain" && a.period_2019_2024.e_tco2e > 0) return false;
      if (onlyEvents && !EVENTS.some((e) => e.aoi_id === a.aoi_id)) return false;
      return true;
    });
  }, [query, region, role, sign, onlyEvents, origin]);

  /* Свои контуры фильтруются теми же условиями, какие к ним применимы.
     Роли и подтверждённого события у них нет — по этим фильтрам они
     отсеиваются целиком, а не притворяются подходящими. */
  const mineRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (origin === "case") return [];
    if (role !== "all" || onlyEvents || region !== "all") return [];
    return mine.filter((c) => {
      if (q && ![c.name, c.contour_id, c.source_name].some((f) => f.toLowerCase().includes(q)))
        return false;
      if (sign === "loss" && !(c.e_tco2e !== null && c.e_tco2e > 0)) return false;
      if (sign === "gain" && !(c.e_tco2e !== null && c.e_tco2e <= 0)) return false;
      return true;
    });
  }, [mine, query, region, role, sign, onlyEvents, origin]);

  const filtersOn =
    query.trim() !== "" ||
    region !== "all" ||
    role !== "all" ||
    sign !== "all" ||
    origin !== "all" ||
    onlyEvents;

  const reset = () => {
    setQuery("");
    setRegion("all");
    setRole("all");
    setSign("all");
    setOrigin("all");
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
        subtitle={
          `${AREAS.length} ${plural(AREAS.length, [
            "исследовательский участок",
            "исследовательских участка",
            "исследовательских участков",
          ])} в наборе — это не зарегистрированные климатические проекты, так помечены сами данные` +
          (mine.length > 0
            ? `, плюс ${mine.length} ${plural(mine.length, [
                "загруженный контур",
                "загруженных контура",
                "загруженных контура",
              ])}: данные под них подтянуты из открытых источников`
            : ". Свой контур считается по тем же продуктам — загрузите границу")
        }
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
        <FilterSelect
          value={origin}
          onChange={setOrigin}
          options={ORIGINS}
          label="происхождение участка"
        />
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
        {/* Свои контуры идут первыми: человек пришёл смотреть на свой
            участок, а не искать его среди двенадцати чужих. */}
        {mineRows.map((c) => (
          <Card key={c.contour_id} className="area area--mine">
            <div className="area__map area__map--plain">
              <span className="area__role">ваш контур</span>
              <span className="area__plain-note">
                карта изменений строится для участков набора заранее; по своему контуру
                показываются числа расчёта
              </span>
            </div>

            <h3 className="area__name">
              <Link to={`/app/contours/${c.contour_id}`}>{c.name}</Link>
            </h3>
            <p className="area__meta">
              {c.contour_id} · {formatDecimal(c.area_ha, 1)} га · {c.year_start}—{c.year_end}
            </p>
            <p className="area__hint">
              загружен из «{c.source_name}»{c.created_by ? `, ${c.created_by}` : ""}
            </p>

            <dl className="area__kv">
              <div>
                <dt>результат за период</dt>
                <dd className="tabular">
                  {c.e_tco2e === null
                    ? "—"
                    : `${c.e_tco2e > 0 ? "+" : "−"}${formatNumber(Math.abs(Math.round(c.e_tco2e)))} т CO₂-экв.`}
                </dd>
              </div>
              <div>
                <dt>потенциальные единицы</dt>
                <dd>
                  {c.units === null ? (
                    <span className="lvl lvl--none">недоступно</span>
                  ) : c.units === 0 ? (
                    <span className="lvl lvl--none">0</span>
                  ) : (
                    <span className="lvl lvl--low">{formatNumber(c.units)}</span>
                  )}
                </dd>
              </div>
              <div>
                <dt>расчёт</dt>
                <dd className="tabular">{c.calc_id ?? "—"}</dd>
              </div>
            </dl>

            <p className="area__why">{c.reason ?? "результат превышает базовую линию"}</p>

            <p className="area__legend">
              <b>данные подтянуты из открытых источников.</b> Биомасса и её погрешность читаются
              окном из продукта ESA CCI, потери покрова — из Hansen GFC. Базовая линия выведена по
              собственной истории контура 2015 → 2019, как предписывает кейс: условием она не
              задана и дополнительность не устанавливает.
            </p>

            <Link to={`/app/contours/${c.contour_id}`} className="row-action area__open">
              открыть расчёт →
            </Link>
          </Card>
        ))}

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

      {rows.length === 0 && mineRows.length === 0 && (
        <Card>
          <p className="empty">
            Под фильтры не подходит ни один участок.{" "}
            <button className="link-btn" type="button" onClick={reset}>
              сбросить фильтры
            </button>
          </p>
        </Card>
      )}

      {mineError && origin !== "case" && (
        <Card className="mb20">
          <p className="ov-note" style={{ marginTop: 0 }}>
            {mineError} Участки набора посчитаны заранее и открываются без него.
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
