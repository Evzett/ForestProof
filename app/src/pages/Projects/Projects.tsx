import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Card, formatNumber } from "../../components/ui";
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

export default function Projects() {
  const [picked, setPicked] = useState<string[]>(["proj-01", "proj-02"]);
  const navigate = useNavigate();
  const { open } = useWizard();

  const toggle = (id: string | null) => {
    if (!id) return;
    setPicked((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 4 ? [...prev, id] : prev
    );
  };

  return (
    <>
      <PageHead
        title="Проекты"
        subtitle="Все климатические проекты из открытой части реестра углеродных единиц"
        action={<AddPlotButton />}
      />

      <div className="filters">
        <span className="filter">⌕ поиск по названию, компании или номеру</span>
        <span className="filter">Красноярский край ▾</span>
        <span className="filter">методология: все ▾</span>
        <span className="filter">вид эффекта: все ▾</span>
        <span className="filter filter--on">только с границами</span>
      </div>

      {picked.length >= 2 && (
        <div className="selbar">
          <b>Выбрано {picked.length} проекта</b>
          <span className="selbar__hint">сравнение доступно для 2–4</span>
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
                <th style={{ width: 40 }} />
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
              {REGISTRY.map((r) => {
                const on = r.project_id ? picked.includes(r.project_id) : false;
                return (
                  <tr key={r.registry_number} style={on ? { background: "#f4f6ee" } : undefined}>
                    <td>
                      <input
                        type="checkbox"
                        checked={on}
                        disabled={!r.project_id}
                        onChange={() => toggle(r.project_id)}
                        aria-label={`выбрать ${r.name}`}
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
                        <button
                          className="row-action"
                          type="button"
                          onClick={() => open(r.name)}
                        >
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
        </div>

        <p className="ov-note" style={{ marginTop: 22 }}>
          Показано {REGISTRY.length} из {REGISTRY_META.total} · {REGISTRY_META.with_geometry} с
          загруженными границами · {REGISTRY_META.total - REGISTRY_META.with_geometry} ждут
          оцифровки. Реквизиты и заявленные показатели импортируются из выгрузки реестра целиком.
          Расчёт возможен там, где загружена граница участка: реестр геометрию проектов не
          публикует.
        </p>
      </Card>
    </>
  );
}
