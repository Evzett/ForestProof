import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Card, FilterSelect, formatDecimal, formatNumber } from "../../components/ui";
import { PageHead } from "../../components/AppShell";
import { AREAS, YEARS } from "../../data/case";
import {
  DISCREPANCY_THRESHOLD_PCT,
  EFFECT_LABEL,
  STATUS_LABEL,
  STATUS_LEVEL,
  TEMPLATE_HEADER,
  TEMPLATE_ROW,
  checkProject,
  loadProjects,
  parseProjectsCsv,
  plausibleClaim,
  saveProjects,
  isExample,
} from "../../data/projects";
import type { EffectKind, Project } from "../../data/projects";
import "./ClaimProjects.css";

/* Раздел «Проекты»: заявленное против посчитанного.

   Дополнительная функция поверх обязательной части. Реестра в кейсе нет,
   поэтому заявленную величину вводит пользователь — механизм сверки от
   этого не меняется.

   Расхождение с заявленным не влияет на число потенциальных единиц:
   единицы считаются относительно базовой линии кейса. Это написано
   и в коде, и на экране. */

const AREA_OPTIONS = AREAS.map((a) => ({ value: a.aoi_id, label: a.name }));
const YEAR_OPTIONS = YEARS.map((y) => ({ value: String(y), label: String(y) }));
const EFFECT_OPTIONS = [
  { value: "removals", label: "поглощение" },
  { value: "avoided_emissions", label: "предотвращённые выбросы" },
];

export default function ClaimProjects() {
  const [projects, setProjects] = useState<Project[]>(loadProjects);
  const [errors, setErrors] = useState<string[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);

  const [form, setForm] = useState({
    name: "",
    company: "",
    aoi_id: AREAS[0].aoi_id,
    period_start: "2019",
    period_end: "2024",
    claimed: "",
    reporting_date: "2024-12-31",
    effect_kind: "removals" as EffectKind,
  });

  const update = (projects: Project[]) => {
    setProjects(projects);
    saveProjects(projects);
  };

  /* Подсказка: сколько показывают наши данные за ту же пару лет.
     Она нужна не чтобы подсказать «правильный» ответ, а чтобы было
     видно, с чем именно сравнивается заявка. */
  const hint = useMemo(
    () => plausibleClaim(form.aoi_id, Number(form.period_start), Number(form.period_end)),
    [form.aoi_id, form.period_start, form.period_end]
  );

  const add = () => {
    const claimed = Number(form.claimed.replace(/\s/g, "").replace(",", "."));
    if (!Number.isFinite(claimed) || claimed === 0) {
      setErrors(["Заявленный объём эффекта должен быть числом, отличным от нуля."]);
      return;
    }
    const start = Number(form.period_start);
    const end = Number(form.period_end);
    if (!(start < end)) {
      setErrors(["Конечный год должен быть больше начального."]);
      return;
    }
    setErrors([]);
    update([
      ...projects,
      {
        id: `${form.aoi_id}-${Date.now()}`,
        name: form.name || `Проект на участке ${form.aoi_id}`,
        company: form.company,
        aoi_id: form.aoi_id,
        period_start: start,
        period_end: end,
        claimed_tco2e: claimed,
        reporting_date: form.reporting_date,
        effect_kind: form.effect_kind,
      },
    ]);
    setForm({ ...form, name: "", company: "", claimed: "" });
  };

  const upload = async (file: File) => {
    if (/\.xlsx?$/i.test(file.name)) {
      setErrors([
        "Книгу Excel сначала надо сохранить как CSV: «Файл → Сохранить как → CSV UTF-8». " +
          "Разбор идёт в браузере, и распаковывать книгу на клиенте ради восьми колонок незачем.",
      ]);
      return;
    }
    const result = parseProjectsCsv(await file.text());
    setErrors(result.errors);
    if (result.projects.length > 0) update([...projects, ...result.projects]);
  };

  const downloadTemplate = () => {
    const blob = new Blob(["﻿" + TEMPLATE_HEADER + "\n" + TEMPLATE_ROW + "\n"], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "projects-template.csv";
    link.click();
    URL.revokeObjectURL(url);
  };

  const checks = useMemo(
    () => projects.map((p) => ({ project: p, check: checkProject(p) })),
    [projects]
  );

  return (
    <>
      <PageHead
        title="Проекты"
        subtitle="Заявленный результат проекта рядом с посчитанным по спутнику. Заявленное вводите вы: реестра в наборе кейса нет"
        action={
          <button className="add-btn" type="button" onClick={downloadTemplate}>
            <span aria-hidden="true">↓</span> шаблон таблицы
          </button>
        }
      />

      <div className="claim-form">
        <Card title="Завести проект" className="plot-block">
          <div className="claim-grid">
            <label className="wz__field">
              <span>название</span>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="например: Восстановление после пожара 2021"
              />
            </label>
            <label className="wz__field">
              <span>компания</span>
              <input
                value={form.company}
                onChange={(e) => setForm({ ...form, company: e.target.value })}
              />
            </label>

            <div className="claim-field">
              <span className="claim-field__label">участок</span>
              <FilterSelect
                value={form.aoi_id}
                onChange={(v) => setForm({ ...form, aoi_id: v })}
                options={AREA_OPTIONS}
                label="участок"
              />
            </div>

            <div className="claim-field">
              <span className="claim-field__label">период</span>
              <div className="claim-period">
                <FilterSelect
                  value={form.period_start}
                  onChange={(v) => setForm({ ...form, period_start: v })}
                  options={YEAR_OPTIONS.slice(0, -1)}
                  label="начальный год"
                />
                <span aria-hidden="true">—</span>
                <FilterSelect
                  value={form.period_end}
                  onChange={(v) => setForm({ ...form, period_end: v })}
                  options={YEAR_OPTIONS.filter((o) => Number(o.value) > Number(form.period_start))}
                  label="конечный год"
                />
              </div>
            </div>

            <label className="wz__field">
              <span>
                заявленный объём эффекта, т CO₂-экв. за период <em>обязательно</em>
              </span>
              <input
                value={form.claimed}
                onChange={(e) => setForm({ ...form, claimed: e.target.value })}
                placeholder={hint !== null ? `по нашим данным вышло ${formatNumber(hint)}` : ""}
              />
            </label>

            <label className="wz__field">
              <span>дата отчётности</span>
              <input
                type="date"
                value={form.reporting_date}
                onChange={(e) => setForm({ ...form, reporting_date: e.target.value })}
              />
            </label>

            <div className="claim-field">
              <span className="claim-field__label">вид эффекта</span>
              <FilterSelect
                value={form.effect_kind}
                onChange={(v) => setForm({ ...form, effect_kind: v as EffectKind })}
                options={EFFECT_OPTIONS}
                label="вид эффекта"
              />
            </div>
          </div>

          <div className="claim-actions">
            <button className="btn btn--dark btn--inline" type="button" onClick={add}>
              <span>Сверить</span>
            </button>
            <input
              ref={fileInput}
              type="file"
              accept=".csv,.txt,.xlsx,.xls"
              className="wz__file-input"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void upload(file);
                e.target.value = "";
              }}
            />
            <button
              className="btn btn--outline btn--inline"
              type="button"
              onClick={() => fileInput.current?.click()}
            >
              <span>Загрузить таблицей</span>
            </button>
          </div>

          {errors.length > 0 && (
            <ul className="claim-errors">
              {errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}

          <p className="ov-note">
            Таблица — CSV со столбцами <code>{TEMPLATE_HEADER}</code>. Разделитель распознаётся
            сам: Excel в русской локали сохраняет с точкой с запятой. Разбор идёт в браузере,
            файл на сервер не уходит.
          </p>
        </Card>
      </div>

      {checks.length === 0 ? (
        <Card title="Пока ни одного проекта">
          <p className="ov-note" style={{ marginTop: 0 }}>
            Заведите проект выше или загрузите таблицу. Сервис поставит заявленный объём рядом с
            посчитанным по спутнику за тот же период на той же территории и скажет, расходятся ли
            они существенно.
          </p>
        </Card>
      ) : (
        <>
          <Card className="mb20">
            <div className="tbl__scroll tbl__scroll--tall">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>проект</th>
                    <th>участок и период</th>
                    <th>вид эффекта</th>
                    <th className="num">заявлено</th>
                    <th className="num">по спутнику</th>
                    <th className="num">расхождение</th>
                    <th>статус</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {checks.map(({ project, check }) => (
                    <tr key={project.id}>
                      <td>
                        <span className="tbl__name">
                          <b>{project.name}</b>
                          {/* Заявленное число вводит человек, и у примеров
                              оно выдумано нами. Показывать выдуманную заявку
                              неотличимо от настоящей нельзя. */}
                          <span>
                            {isExample(project)
                              ? "пример: заявка выдумана, расчёт настоящий"
                              : project.company || "компания не указана"}
                          </span>
                        </span>
                      </td>
                      <td>
                        <span className="tbl__name">
                          <Link to={`/app/area/${project.aoi_id}`}>{check.area.name}</Link>
                          <span>
                            {project.period_start}—{project.period_end} · отчётность{" "}
                            {project.reporting_date}
                          </span>
                        </span>
                      </td>
                      <td style={{ color: "var(--c-muted-alt)" }}>
                        {EFFECT_LABEL[project.effect_kind]}
                      </td>
                      <td className="num">{formatNumber(project.claimed_tco2e)}</td>
                      <td className="num">
                        {check.observed === null ? (
                          <span className="dash">—</span>
                        ) : (
                          formatNumber(Math.round(check.observed))
                        )}
                      </td>
                      <td className="num">
                        {check.discrepancy_pct === null ? (
                          <span className="dash">—</span>
                        ) : (
                          `${formatDecimal(check.discrepancy_pct, 1)} %`
                        )}
                      </td>
                      <td>
                        <span className={`lvl lvl--${STATUS_LEVEL[check.status]}`}>
                          {STATUS_LABEL[check.status]}
                        </span>
                      </td>
                      <td>
                        <button
                          className="link-btn"
                          type="button"
                          onClick={() => update(projects.filter((p) => p.id !== project.id))}
                        >
                          убрать
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="ov-note">
              Порог существенности ±{DISCREPANCY_THRESHOLD_PCT} %. Сравниваются одноимённые
              величины: заявленное поглощение против наблюдаемого накопления за тот же период на
              той же территории. Максимально жёсткое, что система пишет, — «требует проверки».
            </p>
          </Card>

          {checks.map(({ project, check }) => (
            <Card
              key={project.id}
              title={project.name}
              note={`${check.area.name} · ${project.period_start}—${project.period_end}`}
              className="mb20"
            >
              <div className="claim-verdict">
                <span className={`lvl lvl--${STATUS_LEVEL[check.status]}`}>
                  {STATUS_LABEL[check.status]}
                </span>
                <span>{check.likely_cause}</span>
              </div>

              {check.not_comparable_reason && (
                <div className="disclaimer">{check.not_comparable_reason}</div>
              )}

              {check.events_after_reference_date.length > 0 && (
                <>
                  <p className="tile__label" style={{ margin: "18px 0 8px" }}>
                    появилось после даты отчётности
                  </p>
                  <ul className="drivers">
                    {check.events_after_reference_date.map((e) => (
                      <li key={e.year}>
                        {e.year} · {formatDecimal(e.area_ha, 1)} га — {e.note}
                      </li>
                    ))}
                  </ul>
                  <p className="ov-note">
                    На статус не влияет: отчёт от {project.reporting_date} физически не мог их
                    содержать. Это устаревание отчёта, а не несоответствие.
                  </p>
                </>
              )}

              <div className="disclaimer">
                Расхождение с заявленным не влияет на число потенциальных единиц — они считаются
                относительно базовой линии кейса. Формулировок «проект врёт» и «обнаружен
                гринвошинг» система не использует.
              </div>
            </Card>
          ))}
        </>
      )}
    </>
  );
}
