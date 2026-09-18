import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Card,
  Checkbox,
  FilterSelect,
  FilterToggle,
  SearchField,
  formatNumber,
} from "../../components/ui";
import { AddPlotButton, PageHead } from "../../components/AppShell";
import { useWizard } from "../../components/Wizard";
import { REGISTRY, REGISTRY_META } from "../../data/mock";
import type { DataStatus } from "../../types";

/* Каталог проектов. Требования FR-09 — FR-13.

   Показываем ВСЕ проекты из выгрузки, а не только посчитанные: иначе
   скрываем масштаб и напрашиваемся на вопрос о масштабируемости.
   У непосчитанных честно пишем причину — реестр не публикует геометрию. */

const STATUS_LABEL: Record<DataStatus, string> = {
  calculated: "рассчитан",
  no_geometry: "границы не загружены",
  in_progress: "в расчёте",
};

const STATUS_CLASS: Record<DataStatus, string> = {
  calculated: "lvl lvl--low",
  no_geometry: "lvl lvl--none",
  in_progress: "lvl lvl--medium",
};

const EFFECTS = [
  { value: "all", label: "вид эффекта: все" },
  { value: "removals", label: "поглощение" },
  { value: "avoided_emissions", label: "предотвращённые выбросы" },
];

/* Списки регионов и методологий собираются из самой выгрузки:
   захардкоженный список разъедется с данными на первом же импорте. */
function uniq(values: string[]) {
  return Array.from(new Set(values)).sort((a, b) => a.localeCompare(b, "ru"));
}

export default function Projects() {
  const [picked, setPicked] = useState<string[]>(["proj-01", "proj-02"]);
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState("all");
  const [method, setMethod] = useState("all");
  const [effect, setEffect] = useState("all");
  const [onlyGeometry, setOnlyGeometry] = useState(false);
  const navigate = useNavigate();
  const { open } = useWizard();

  const regions = useMemo(
    () => [
      { value: "all", label: "регион: все" },
      ...uniq(REGISTRY.map((r) => r.region)).map((v) => ({ value: v, label: v })),
    ],
    []
  );

  const methods = useMemo(
    () => [
      { value: "all", label: "методология: все" },
      ...uniq(REGISTRY.map((r) => r.methodology)).map((v) => ({ value: v, label: v })),
    ],
    []
  );

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return REGISTRY.filter((r) => {
      if (q && ![r.name, r.company, r.registry_number].some((f) => f.toLowerCase().includes(q)))
        return false;
      if (region !== "all" && r.region !== region) return false;
      if (method !== "all" && r.methodology !== method) return false;
      if (effect !== "all" && r.effect_kind !== effect) return false;
      if (onlyGeometry && r.data_status === "no_geometry") return false;
      return true;
    });
  }, [query, region, method, effect, onlyGeometry]);

  const filtersOn =
    query.trim() !== "" || region !== "all" || method !== "all" || effect !== "all" || onlyGeometry;

  const reset = () => {
    setQuery("");
    setRegion("all");
    setMethod("all");
    setEffect("all");
    setOnlyGeometry(false);
  };

  /* Сравнивать можно только посчитанные участки: у остальных нечего
     класть в матрицу. Ограничение сверху — четыре, дальше колонки
     перестают читаться. */
  const toggle = (id: string | null) => {
    if (!id) return;
    setPicked((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 4 ? [...prev, id] : prev
    );
  };

  const full = picked.length >= 4;

  return (
    <>
      <PageHead
        title="Проекты"
        subtitle="Все климатические проекты из открытой части реестра углеродных единиц"
        action={<AddPlotButton />}
      />

      <div className="filters">
        <SearchField
          value={query}
          onChange={setQuery}
          placeholder="поиск по названию, компании или номеру"
        />
        <FilterSelect value={region} onChange={setRegion} options={regions} label="регион" />
        <FilterSelect value={method} onChange={setMethod} options={methods} label="методология" />
        <FilterSelect value={effect} onChange={setEffect} options={EFFECTS} label="вид эффекта" />
        <FilterToggle on={onlyGeometry} onClick={() => setOnlyGeometry((v) => !v)}>
          только с границами
        </FilterToggle>
        {filtersOn && (
          <button className="filter filter--btn" type="button" onClick={reset}>
            сбросить ✕
          </button>
        )}
      </div>

      {picked.length >= 2 && (
        <div className="selbar">
          <b>Выбрано {picked.length} проекта</b>
          <span className="selbar__hint">
            {full ? "больше четырёх колонок не читается" : "сравнение доступно для 2–4"}
          </span>
          <span className="selbar__spacer" />
          <button className="btn btn--lime" type="button" onClick={() => navigate("/app/compare")}>
            <span>Сравнить</span>
            <span className="btn__arrow">→</span>
          </button>
        </div>
      )}

      <Card>
        <div className="tbl__scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: 40 }} title="отметьте два-четыре посчитанных проекта">
                  ✓
                </th>
                <th>№ в реестре</th>
                <th>Название</th>
                <th>Компания</th>
                <th>Методология</th>
                <th className="num">Единиц</th>
                <th>Данные</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const on = r.project_id ? picked.includes(r.project_id) : false;
                const blocked = !r.project_id;
                return (
                  <tr key={r.registry_number} style={on ? { background: "#f4f6ee" } : undefined}>
                    <td>
                      <Checkbox
                        checked={on}
                        disabled={blocked || (full && !on)}
                        onChange={() => toggle(r.project_id)}
                        label={`выбрать ${r.name} для сравнения`}
                        reason={
                          blocked
                            ? "участок ещё не посчитан: сравнивать нечего"
                            : "уже выбрано четыре проекта"
                        }
                      />
                    </td>
                    <td style={{ color: "var(--c-muted-alt)" }}>{r.registry_number}</td>
                    <td>
                      <span className="tbl__name">
                        <b>{r.name}</b>
                        <span>
                          {r.effect_kind === "avoided_emissions"
                            ? "предотвращённые выбросы"
                            : "поглощение"}
                        </span>
                      </span>
                    </td>
                    <td>{r.company}</td>
                    <td style={{ color: "var(--c-muted-alt)" }}>{r.methodology}</td>
                    <td className="num">
                      {r.units_in_circulation ? formatNumber(r.units_in_circulation) : "—"}
                    </td>
                    <td>
                      <span className={STATUS_CLASS[r.data_status]}>
                        {STATUS_LABEL[r.data_status]}
                      </span>
                    </td>
                    <td>
                      {r.data_status === "no_geometry" ? (
                        <button className="row-action" type="button" onClick={() => open(r.name)}>
                          загрузить границу
                        </button>
                      ) : r.project_id ? (
                        <Link to={`/app/plot/${r.project_id}`}>открыть →</Link>
                      ) : (
                        <span className="dash">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {rows.length === 0 && (
            <p className="empty">
              Под фильтры не подходит ни один проект из выгрузки.{" "}
              <button className="link-btn" type="button" onClick={reset}>
                сбросить фильтры
              </button>
            </p>
          )}
        </div>

        <p className="ov-note" style={{ marginTop: 22 }}>
          Показано {rows.length} из {REGISTRY.length} загруженных строк · всего в реестре{" "}
          {REGISTRY_META.total} · {REGISTRY_META.with_geometry} с загруженными границами.
          Отметить для сравнения можно только посчитанные участки: у остальных не загружена
          граница, а реестр геометрию проектов не публикует. Реквизиты и заявленные показатели
          импортируются из выгрузки целиком.
        </p>
      </Card>
    </>
  );
}
