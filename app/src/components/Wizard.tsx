import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { CALC_STEPS, GEOMETRY_CHECKS } from "../data/mock";
import "./Wizard.css";

/* Мастер добавления участка. Требования FR-18 — FR-24.

   Две разные загрузки. Проекты приходят пачкой из выгрузки реестра —
   пользователь их не заводит. Но геометрию реестр не публикует, поэтому
   границу к проекту догружают вручную. Своя территория — отдельный случай:
   нет ни проекта, ни контура. Мастер один, отличается шагом привязки. */

type WizardState = { open: boolean; projectName?: string };
type Ctx = { open: (projectName?: string) => void };

const WizardCtx = createContext<Ctx>({ open: () => {} });
export const useWizard = () => useContext(WizardCtx);

export function WizardProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<WizardState>({ open: false });
  const api = useMemo<Ctx>(
    () => ({ open: (projectName?: string) => setState({ open: true, projectName }) }),
    []
  );

  return (
    <WizardCtx.Provider value={api}>
      {children}
      {state.open && (
        <Wizard projectName={state.projectName} onClose={() => setState({ open: false })} />
      )}
    </WizardCtx.Provider>
  );
}

const TITLES = [
  "Добавить участок",
  "Проверка геометрии",
  "Что это за участок",
  "Считаем участок",
  "Участок добавлен",
];

function Wizard({ projectName, onClose }: { projectName?: string; onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [method, setMethod] = useState("file");
  const [name, setName] = useState(projectName ? `Граница · ${projectName}` : "Богучанский резерв");
  const [source, setSource] = useState("");
  const [link, setLink] = useState(projectName ? "project" : "territory");
  const navigate = useNavigate();

  /* Источник границы обязателен (FR-21): все числа считаются по этому контуру,
     и если он обведён по лесничеству, допущение обязаны назвать мы. */
  const canSubmit = source.trim().length > 0;

  return (
    <div className="wz" role="dialog" aria-modal="true" aria-label={TITLES[step]}>
      <div className="wz__backdrop" onClick={onClose} />
      <div className="wz__panel">
        <header className="wz__head">
          <div>
            <h2 className="wz__title">{TITLES[step]}</h2>
            <p className="wz__step">
              {step < 3 ? `шаг ${step + 1} из 3` : step === 3 ? "расчёт идёт" : "CALC-0151 · методика v1.0 · алгоритм calc-0.1"}
            </p>
          </div>
          <button className="wz__close" type="button" onClick={onClose} aria-label="Закрыть">
            ✕
          </button>
        </header>

        <div className="wz__body">
          {step === 0 && (
            <>
              {[
                ["file", "Загрузить файл границы", "GeoJSON или Shapefile, система координат EPSG:4326"],
                ["draw", "Обвести полигон на карте", "если файла нет — контур рисуется вручную поверх снимка"],
                ["coords", "Ввести координаты", "список вершин в десятичных градусах, через запятую"],
              ].map(([key, title, sub]) => (
                <button
                  key={key}
                  type="button"
                  className={`wz__opt ${method === key ? "is-on" : ""}`}
                  onClick={() => setMethod(key)}
                  disabled={key !== "file"}
                >
                  <span className="wz__radio" aria-hidden="true" />
                  <span>
                    <b>{title}</b>
                    <span>{sub}</span>
                  </span>
                  {key !== "file" && <span className="wz__soon">позже</span>}
                </button>
              ))}
              <p className="wz__note">
                Проекты из реестра загружать не нужно — все 132 уже в каталоге. Здесь добавляется
                только граница участка: реестр геометрию проектов не публикует.
              </p>
            </>
          )}

          {step === 1 && (
            <>
              <div className="wz__file">
                <b>bogucha-reserve.geojson</b>
                <span>· 48 КБ</span>
              </div>
              <ul className="wz__checks">
                {GEOMETRY_CHECKS.map((c) => (
                  <li key={c.name}>
                    <span className={`wz__dot wz__dot--${c.ok === "warn" ? "warn" : "ok"}`}>
                      {c.ok === "warn" ? "!" : "✓"}
                    </span>
                    <b>{c.name}</b>
                    <span className="wz__val">{c.value}</span>
                  </li>
                ))}
              </ul>
              <p className="wz__note">
                Предупреждение не мешает расчёту: за 2017 год будет прочерк, а не подстановка
                соседнего значения.
              </p>
            </>
          )}

          {step === 2 && (
            <>
              <label className="wz__field">
                <span>название</span>
                <input value={name} onChange={(e) => setName(e.target.value)} />
              </label>

              <label className="wz__field">
                <span>
                  источник границы <em>обязательно</em>
                </span>
                <input
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  placeholder="например: обведена по контуру лесничества"
                />
              </label>
              <p className="wz__note">
                Способ построения границы выводится на экране расчёта: все числа считаются по ней,
                и это допущение должно быть названо нами, а не найдено проверяющим.
              </p>

              <div className="wz__modes">
                {[
                  ["project", "Привязать к проекту реестра"],
                  ["territory", "Территория без проекта"],
                ].map(([k, label]) => (
                  <button
                    key={k}
                    type="button"
                    className={`wz__mode ${link === k ? "is-on" : ""}`}
                    onClick={() => setLink(k)}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {link === "project" && (
                <div className="wz__result">
                  <div>
                    <b>{projectName ?? "Богучанский участок"}</b>
                    <span>04-2023-00000008 · АО «Лесинвест» · лесоразведение</span>
                  </div>
                  <span aria-hidden="true">✓</span>
                </div>
              )}
              <p className="wz__note">Без привязки блок сверки не считается — заявлять нечего.</p>
            </>
          )}

          {step === 3 && (
            <>
              <ul className="wz__checks">
                {CALC_STEPS.map((s, i) => (
                  <li key={s.label}>
                    <span className={`wz__dot wz__dot--${i < 2 ? "ok" : i === 2 ? "run" : "wait"}`}>
                      {i < 2 ? "✓" : i === 2 ? "⟳" : ""}
                    </span>
                    <b style={i > 2 ? { color: "var(--c-muted-alt)" } : undefined}>{s.label}</b>
                    <span className="wz__val">{i === 2 ? "идёт" : s.result}</span>
                  </li>
                ))}
              </ul>
              <div className="wz__track">
                <span style={{ width: "44%" }} />
              </div>
              <p className="wz__note">
                Окно можно закрыть — расчёт продолжится, готовый появится в журнале.
              </p>
            </>
          )}

          {step === 4 && (
            <>
              <div className="wz__big tabular">
                18 200 <small>га</small>
              </div>
              <ul className="wz__summary">
                <li>
                  <span>лесопокрытая площадь</span>
                  <b className="tabular">16 940 га</b>
                </li>
                <li>
                  <span>биомасса</span>
                  <b className="tabular">154 ± 26 т/га</b>
                </li>
                <li>
                  <span>полнота данных</span>
                  <b className="tabular">11 из 12 лет</b>
                </li>
                <li>
                  <span>уязвимость</span>
                  <span className="lvl lvl--low">низкая</span>
                </li>
              </ul>
              <p className="wz__note">
                {link === "project"
                  ? "Блок сверки посчитан: участок привязан к проекту 04-2023-00000008."
                  : "Вкладки сверки у этого участка нет: проекта нет, заявлять нечего."}
              </p>
            </>
          )}
        </div>

        <footer className="wz__foot">
          {step > 0 && step < 3 && (
            <button className="btn btn--ghost" type="button" onClick={() => setStep(step - 1)}>
              <span>Назад</span>
            </button>
          )}
          {step === 0 && (
            <button className="btn btn--ghost" type="button" onClick={onClose}>
              <span>Отмена</span>
            </button>
          )}
          <span className="wz__spacer" />

          {step < 2 && (
            <button className="btn btn--dark" type="button" onClick={() => setStep(step + 1)}>
              <span>Далее</span>
            </button>
          )}
          {step === 2 && (
            <button
              className="btn btn--dark"
              type="button"
              disabled={!canSubmit}
              onClick={() => setStep(3)}
            >
              <span>Добавить и посчитать</span>
            </button>
          )}
          {step === 3 && (
            <>
              <button className="btn btn--ghost" type="button" onClick={onClose}>
                <span>Свернуть</span>
              </button>
              <button className="btn btn--dark" type="button" onClick={() => setStep(4)}>
                <span>Показать результат</span>
              </button>
            </>
          )}
          {step === 4 && (
            <>
              <button
                className="btn btn--ghost"
                type="button"
                onClick={() => {
                  onClose();
                  navigate("/app/calculations");
                }}
              >
                <span>В журнал расчётов</span>
              </button>
              <button
                className="btn btn--outline"
                type="button"
                onClick={() => {
                  onClose();
                  navigate("/app/plot/proj-03");
                }}
              >
                <span>Открыть участок</span>
              </button>
            </>
          )}
        </footer>
      </div>
    </div>
  );
}
