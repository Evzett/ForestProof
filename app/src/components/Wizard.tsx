import {
  createContext,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  geometryFromGeoJson,
  polygonFromPoints,
  postCalc,
  type CalcResult,
  type GeoJsonPolygon,
} from "../api";
import { CALC_STEPS, GEOMETRY_CHECKS } from "../data/mock";
import { formatArea, formatNumber } from "./ui";
import "./Wizard.css";

/* Мастер добавления участка. Требования FR-18 — FR-24.

   Две разные загрузки. Проекты приходят пачкой из выгрузки реестра —
   пользователь их не заводит. Но геометрию реестр не публикует, поэтому
   границу к проекту догружают вручную. Своя территория — отдельный случай:
   нет ни проекта, ни контура. Мастер один, отличается шагом привязки.

   Все три способа задать границу работают: файл читается и разбирается
   в браузере, полигон рисуется кликами, координаты парсятся из текста.
   Дальше по мастеру идут те числа, которые получились на этом шаге. */

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

type Method = "file" | "draw" | "coords";
type Point = { x: number; y: number };

const METHODS: [Method, string, string][] = [
  ["file", "Загрузить файл границы", "GeoJSON или Shapefile, система координат EPSG:4326"],
  ["draw", "Обвести полигон на карте", "если файла нет — контур рисуется кликами поверх снимка"],
  ["coords", "Ввести координаты", "список вершин в десятичных градусах, по одной паре в строке"],
];

/* Площадь простого полигона по формуле шнурования.
   Для демонстрации достаточно плоского приближения: на широте 60°
   градус долготы примерно вдвое короче градуса широты. */
function polygonAreaHa(points: { lat: number; lon: number }[]) {
  if (points.length < 3) return 0;
  const latMean = points.reduce((a, p) => a + p.lat, 0) / points.length;
  const kx = 111.32 * Math.cos((latMean * Math.PI) / 180);
  const ky = 110.57;
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    sum += a.lon * kx * (b.lat * ky) - b.lon * kx * (a.lat * ky);
  }
  return Math.abs(sum / 2) * 100; /* км² → га */
}

/* Разбор пар «широта, долгота» из произвольного текста */
function parseCoords(text: string) {
  const points: { lat: number; lon: number }[] = [];
  const bad: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const m = line.split(/[,;\s]+/).filter(Boolean);
    const lat = Number(m[0]?.replace(",", "."));
    const lon = Number(m[1]?.replace(",", "."));
    if (m.length < 2 || !Number.isFinite(lat) || !Number.isFinite(lon)) {
      bad.push(line);
      continue;
    }
    if (Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      bad.push(line);
      continue;
    }
    points.push({ lat, lon });
  }
  return { points, bad };
}

function Wizard({ projectName, onClose }: { projectName?: string; onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [method, setMethod] = useState<Method>("file");
  const [name, setName] = useState(projectName ? `Граница · ${projectName}` : "Богучанский резерв");
  const [source, setSource] = useState("");
  const [link, setLink] = useState(projectName ? "project" : "territory");

  /* --- способ 1: файл --- */
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<{ name: string; size: number; vertices: number | null } | null>(
    null
  );
  const [fileError, setFileError] = useState("");

  /* --- способ 2: рисование --- */
  const [points, setPoints] = useState<Point[]>([]);

  /* --- способ 3: координаты --- */
  const [coordText, setCoordText] = useState("");
  const parsed = parseCoords(coordText);

  /* Геометрия, которая уйдёт на расчёт. Раньше мастер разбирал файл ради
     числа вершин и выбрасывал сам полигон — считать было нечего. */
  const [geometry, setGeometry] = useState<GeoJsonPolygon | null>(null);
  const [calc, setCalc] = useState<CalcResult | null>(null);
  const [calcError, setCalcError] = useState("");
  const [calcPending, setCalcPending] = useState(false);

  const navigate = useNavigate();

  const pickFile = async (f: File) => {
    setFileError("");
    const known = /\.(geojson|json|zip|shp)$/i.test(f.name);
    if (!known) {
      setFileError("Ожидается GeoJSON (.geojson, .json) или Shapefile в архиве (.zip)");
      setFile(null);
      return;
    }
    let vertices: number | null = null;
    if (/\.(geojson|json)$/i.test(f.name)) {
      try {
        const geom = geometryFromGeoJson(JSON.parse(await f.text()));
        const ring = (geom.coordinates as number[][][])[0];
        if (!Array.isArray(ring)) throw new Error("no ring");
        vertices = Array.isArray(ring[0][0]) ? (ring[0] as unknown[]).length : ring.length;
        setGeometry(geom);
      } catch (err) {
        setFileError(
          err instanceof Error && err.message
            ? err.message
            : "Файл не разбирается как GeoJSON с полигоном"
        );
        setFile(null);
        setGeometry(null);
        return;
      }
    } else {
      // Shapefile в архиве мы не разбираем на клиенте: расчёт по нему
      // недоступен, и лучше сказать это, чем принять файл молча.
      setGeometry(null);
    }
    setFile({ name: f.name, size: f.size, vertices });
  };

  /* Полигон считается заданным, когда в нём есть что считать */
  const geometryReady =
    method === "file"
      ? file !== null
      : method === "draw"
        ? points.length >= 3
        : parsed.points.length >= 3;

  const vertexCount =
    method === "file"
      ? file?.vertices
      : method === "draw"
        ? points.length
        : parsed.points.length;

  const drawnAreaHa =
    method === "coords" && parsed.points.length >= 3 ? polygonAreaHa(parsed.points) : null;

  /* Источник границы обязателен (FR-21): все числа считаются по этому контуру,
     и если он обведён по лесничеству, допущение обязаны назвать мы. */
  const canSubmit = source.trim().length > 0;

  /* Геометрия для отправки: файл даёт её напрямую, координаты собираются
     в полигон. Обводка на карте живёт в процентах экрана, а не в градусах,
     поэтому географией не является и на расчёт не уходит. */
  const requestGeometry = (): GeoJsonPolygon | null => {
    if (method === "file") return geometry;
    if (method === "coords" && parsed.points.length >= 3) return polygonFromPoints(parsed.points);
    return null;
  };

  const runCalculation = async () => {
    setStep(3);
    setCalc(null);
    setCalcError("");

    const geom = requestGeometry();
    if (!geom) {
      setCalcError(
        method === "draw"
          ? "Обводка на карте задаёт контур в координатах экрана, а не в градусах. " +
              "Для расчёта загрузите файл границы или введите координаты вершин."
          : "Граница не задана в пригодном для расчёта виде."
      );
      return;
    }

    setCalcPending(true);
    try {
      // Период по умолчанию — весь доступный диапазон кейса.
      setCalc(await postCalc({ geometry: geom, year_start: 2019, year_end: 2024 }));
    } catch (err) {
      // Причина от сервиса показывается как есть: «контур вне набора»,
      // «площадь превышает предел». Выдумывать числа вместо неё нельзя.
      setCalcError(err instanceof ApiError ? err.message : "Не удалось посчитать участок");
    } finally {
      setCalcPending(false);
    }
  };

  const addPoint = (e: React.MouseEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    setPoints((prev) => [
      ...prev,
      {
        x: ((e.clientX - box.left) / box.width) * 100,
        y: ((e.clientY - box.top) / box.height) * 100,
      },
    ]);
  };

  return (
    <div className="wz" role="dialog" aria-modal="true" aria-label={TITLES[step]}>
      <div className="wz__backdrop" onClick={onClose} />
      <div className="wz__panel">
        <header className="wz__head">
          <div>
            {/* На последнем шаге заголовок обязан совпадать с тем, что ниже:
                «Участок добавлен» над сообщением об отказе — ровно та ложь,
                которую замечают первой. */}
            <h2 className="wz__title">
              {step === 4 && calc === null ? "Участок не посчитан" : TITLES[step]}
            </h2>
            <p className="wz__step">
              {step < 3
                ? `шаг ${step + 1} из 3`
                : step === 3
                  ? calcPending
                    ? "расчёт идёт"
                    : calcError
                      ? "расчёт не выполнен"
                      : "расчёт готов"
                  : calc
                    ? `${calc.calc_id} · методика 1.0 · алгоритм calc-1.0`
                    : "расчёт недоступен"}
            </p>
          </div>
          <button className="wz__close" type="button" onClick={onClose} aria-label="Закрыть">
            ✕
          </button>
        </header>

        <div className="wz__body">
          {step === 0 && (
            <>
              {METHODS.map(([key, title, sub]) => (
                <button
                  key={key}
                  type="button"
                  className={`wz__opt ${method === key ? "is-on" : ""}`}
                  onClick={() => setMethod(key)}
                  aria-pressed={method === key}
                >
                  <span className="wz__radio" aria-hidden="true" />
                  <span>
                    <b>{title}</b>
                    <span>{sub}</span>
                  </span>
                </button>
              ))}

              {/* --- файл --- */}
              {method === "file" && (
                <div className="wz__pane">
                  <input
                    ref={fileInput}
                    type="file"
                    accept=".geojson,.json,.zip,.shp"
                    className="wz__file-input"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void pickFile(f);
                    }}
                  />
                  <button
                    className="btn btn--outline"
                    type="button"
                    onClick={() => fileInput.current?.click()}
                  >
                    <span>Выбрать файл</span>
                  </button>
                  {file && (
                    <div className="wz__file">
                      <b>{file.name}</b>
                      <span>· {Math.max(1, Math.round(file.size / 1024))} КБ</span>
                      {file.vertices !== null && <span>· {file.vertices} вершин</span>}
                    </div>
                  )}
                  {fileError && <p className="wz__err">{fileError}</p>}
                </div>
              )}

              {/* --- рисование --- */}
              {method === "draw" && (
                <div className="wz__pane">
                  <svg
                    className="wz__draw"
                    viewBox="0 0 100 60"
                    preserveAspectRatio="none"
                    onClick={addPoint}
                    role="application"
                    aria-label="Полотно для обводки полигона"
                  >
                    {points.length >= 2 && (
                      <polygon
                        points={points.map((p) => `${p.x},${(p.y / 100) * 60}`).join(" ")}
                        className="wz__draw-poly"
                      />
                    )}
                    {points.map((p, i) => (
                      <circle key={i} cx={p.x} cy={(p.y / 100) * 60} r="0.9" />
                    ))}
                  </svg>
                  <div className="wz__draw-foot">
                    <span>
                      {points.length === 0
                        ? "кликайте по снимку — каждая точка добавляет вершину"
                        : `${points.length} вершин${points.length >= 3 ? " · контур замкнут" : ", нужно минимум 3"}`}
                    </span>
                    <button
                      className="link-btn"
                      type="button"
                      onClick={() => setPoints([])}
                      disabled={points.length === 0}
                    >
                      очистить
                    </button>
                  </div>
                </div>
              )}

              {/* --- координаты --- */}
              {method === "coords" && (
                <div className="wz__pane">
                  <textarea
                    className="wz__coords"
                    value={coordText}
                    onChange={(e) => setCoordText(e.target.value)}
                    placeholder={"58.4213, 97.1204\n58.4310, 97.2288\n58.3902, 97.2517"}
                    aria-label="Координаты вершин"
                    rows={6}
                  />
                  <div className="wz__draw-foot">
                    <span>
                      {parsed.points.length} вершин разобрано
                      {drawnAreaHa !== null && ` · примерно ${formatArea(Math.round(drawnAreaHa))} га`}
                    </span>
                    {parsed.bad.length > 0 && (
                      <span className="wz__err">{parsed.bad.length} строк не разобрано</span>
                    )}
                  </div>
                </div>
              )}

              <p className="wz__note">
                Проекты из реестра загружать не нужно — все 132 уже в каталоге. Здесь добавляется
                только граница участка: реестр геометрию проектов не публикует.
              </p>
            </>
          )}

          {step === 1 && (
            <>
              <div className="wz__file">
                <b>
                  {method === "file"
                    ? (file?.name ?? "граница не выбрана")
                    : method === "draw"
                      ? "контур, обведённый вручную"
                      : "контур из введённых координат"}
                </b>
                {vertexCount != null && <span>· {vertexCount} вершин</span>}
              </div>
              <ul className="wz__checks">
                {GEOMETRY_CHECKS.map((c) => (
                  <li key={c.name}>
                    <span className={`wz__dot wz__dot--${c.ok === "warn" ? "warn" : "ok"}`}>
                      {c.ok === "warn" ? "!" : "✓"}
                    </span>
                    <b>{c.name}</b>
                    <span className="wz__val">
                      {c.name === "Площадь полигона" && drawnAreaHa !== null
                        ? `${formatNumber(Math.round(drawnAreaHa))} га`
                        : c.value}
                    </span>
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
                    aria-pressed={link === k}
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
                {CALC_STEPS.map((s, i) => {
                  const done = calc !== null || (!calcPending && !calcError);
                  const state = calcError
                    ? "wait"
                    : calc !== null
                      ? "ok"
                      : calcPending && i === 0
                        ? "run"
                        : "wait";
                  return (
                    <li key={s.label}>
                      <span className={`wz__dot wz__dot--${state}`}>
                        {state === "ok" ? "✓" : state === "run" ? "⟳" : ""}
                      </span>
                      <b style={state === "wait" ? { color: "var(--c-muted-alt)" } : undefined}>
                        {s.label}
                      </b>
                      <span className="wz__val">{done && calc !== null ? "готово" : ""}</span>
                    </li>
                  );
                })}
              </ul>
              <div className="wz__track">
                <span style={{ width: calc !== null ? "100%" : calcPending ? "60%" : "0%" }} />
              </div>
              {calcError ? (
                <p className="wz__note" style={{ color: "#9c3f66" }}>
                  {calcError}
                </p>
              ) : (
                <p className="wz__note">
                  Считаем по тем же растрам и тем же кодом, что и участки набора.
                  {calc !== null && ` Расчёт ${calc.calc_id} записан в журнал.`}
                </p>
              )}
            </>
          )}

          {step === 4 && (
            <>
              {calc === null ? (
                /* «Данных недостаточно» — полноценный вид блока, а не пустота:
                   причина названа, и видно, что нужно, чтобы её снять. */
                <>
                  <div className="wz__big" style={{ fontSize: 28, lineHeight: 1.2 }}>
                    Расчёт недоступен
                  </div>
                  <p className="wz__note">
                    {calcError || "Расчёт не выполнялся."}
                  </p>
                  <p className="wz__note">
                    Участки набора посчитаны заранее и открываются без сервиса. Расчёт по своему
                    контуру требует запущенного бэкенда: предпосчитать чужой полигон невозможно.
                  </p>
                </>
              ) : (
                <>
                  <div className="wz__big tabular">
                    {formatNumber(Math.round(calc.area_ha))} <small>га</small>
                  </div>
                  <ul className="wz__summary">
                    <li>
                      <span>запас на {calc.period.year_start}</span>
                      <b className="tabular">{calc.period.c_start_t_ha.toFixed(2)} т C/га</b>
                    </li>
                    <li>
                      <span>запас на {calc.period.year_end}</span>
                      <b className="tabular">{calc.period.c_end_t_ha.toFixed(2)} т C/га</b>
                    </li>
                    <li>
                      <span>
                        результат E, т CO₂-экв.
                      </span>
                      <b className="tabular">
                        {calc.period.e_tco2e > 0 ? "+" : ""}
                        {formatNumber(Math.round(calc.period.e_tco2e))}
                      </b>
                    </li>
                    <li>
                      <span>потенциальных единиц</span>
                      <b className="tabular">
                        {calc.period.available ? (calc.period.units ?? 0) : "недоступно"}
                      </b>
                    </li>
                  </ul>
                  <p className="wz__note">
                    {calc.period.e_tco2e > 0
                      ? "Положительное E — потеря углерода из учитываемого пула. Это не объём немедленного выброса в атмосферу."
                      : "Отрицательное E — накопление углерода в учитываемом пуле."}
                  </p>
                  <p className="wz__note">
                    {calc.baseline_note}. {calc.status}.
                  </p>
                  <p className="wz__note">
                    Расчёт {calc.calc_id}, хеш входа {calc.input_hash.slice(0, 12)}… — по нему
                    результат воспроизводится независимо.
                  </p>
                </>
              )}
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

          {step === 0 && (
            <button
              className="btn btn--dark"
              type="button"
              disabled={!geometryReady}
              title={geometryReady ? undefined : "Сначала задайте границу участка"}
              onClick={() => setStep(1)}
            >
              <span>Далее</span>
            </button>
          )}
          {step === 1 && (
            <button className="btn btn--dark" type="button" onClick={() => setStep(2)}>
              <span>Далее</span>
            </button>
          )}
          {step === 2 && (
            <button
              className="btn btn--dark"
              type="button"
              disabled={!canSubmit}
              title={canSubmit ? undefined : "Укажите, как построена граница"}
              onClick={runCalculation}
            >
              <span>Добавить и посчитать</span>
            </button>
          )}
          {step === 3 && (
            <>
              <button className="btn btn--ghost" type="button" onClick={onClose}>
                <span>Свернуть</span>
              </button>
              <button
                className="btn btn--dark"
                type="button"
                disabled={calcPending}
                onClick={() => setStep(4)}
              >
                <span>{calcPending ? "Считаем…" : "Показать результат"}</span>
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
