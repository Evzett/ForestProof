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
  saveContour,
  type CalcResult,
  type GeoJsonPolygon,
  type SavedContour,
} from "../api";
import { CALC_STEPS } from "../data/mock";
import { formatArea, formatNumber } from "./ui";
import "./Wizard.css";
import { SAMPLE_CONTOURS, type SampleContour } from "../data/sampleContours";

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

type Method = "file" | "draw" | "coords" | "table";
type Point = { x: number; y: number };

const METHODS: [Method, string, string][] = [
  ["file", "Загрузить файл границы", "GeoJSON или Shapefile, система координат EPSG:4326"],
  ["draw", "Обвести полигон на карте", "если файла нет — контур рисуется кликами поверх снимка"],
  ["coords", "Ввести координаты", "список вершин в десятичных градусах, по одной паре в строке"],
  ["table", "Загрузить таблицу", "CSV со столбцами name, lat, lon, order — контуры из ведомости"],
];

/* Разбор ведомости с вершинами.

   Нужен не для красоты: у лесохозяйственных организаций контуры чаще
   лежат в таблице, чем в GeoJSON. Столбец name разделяет несколько
   участков в одном файле, order задаёт порядок обхода вершин.

   Разбор идёт здесь, на клиенте: на сервер уходит уже готовая геометрия,
   а не файл целиком. */
type TableContour = { name: string; points: { lat: number; lon: number }[] };

function parseContourTable(text: string): { contours: TableContour[]; error: string } {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length < 2) return { contours: [], error: "В таблице нет строк с данными" };

  const sep = [";", "\t", ","].find((s) => lines[0].includes(s)) ?? ",";
  const header = lines[0].split(sep).map((h) => h.trim().toLowerCase().replace(/^"|"$/g, ""));
  const col = (...names: string[]) => header.findIndex((h) => names.includes(h));

  const iLat = col("lat", "latitude", "широта");
  const iLon = col("lon", "lng", "longitude", "долгота");
  if (iLat < 0 || iLon < 0) {
    return { contours: [], error: "Не найдены столбцы lat и lon. Ожидается заголовок: name, lat, lon, order" };
  }
  const iName = col("name", "название", "участок");
  const iOrder = col("order", "порядок", "n");

  const rows: { name: string; lat: number; lon: number; order: number }[] = [];
  const bad: number[] = [];
  lines.slice(1).forEach((line, idx) => {
    const cells = line.split(sep).map((c) => c.trim().replace(/^"|"$/g, ""));
    const lat = Number(cells[iLat]?.replace(",", "."));
    const lon = Number(cells[iLon]?.replace(",", "."));
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      bad.push(idx + 2);
      return;
    }
    rows.push({
      name: (iName >= 0 ? cells[iName] : "") || "участок",
      lat,
      lon,
      order: iOrder >= 0 ? Number(cells[iOrder]) || idx : idx,
    });
  });

  if (rows.length === 0) {
    return { contours: [], error: "Ни одна строка не разобралась как пара широта/долгота" };
  }

  const byName = new Map<string, { lat: number; lon: number; order: number }[]>();
  for (const r of rows) {
    if (!byName.has(r.name)) byName.set(r.name, []);
    byName.get(r.name)!.push(r);
  }

  const contours: TableContour[] = [];
  for (const [name, pts] of byName) {
    if (pts.length < 3) continue;
    contours.push({
      name,
      points: [...pts].sort((a, b) => a.order - b.order).map(({ lat, lon }) => ({ lat, lon })),
    });
  }

  if (contours.length === 0) {
    return { contours: [], error: "В каждом контуре нужно хотя бы три вершины" };
  }
  return {
    contours,
    // Плохие строки не молчим: пользователь должен знать, что часть
    // ведомости не разобралась, а не гадать, почему площадь меньше.
    error: bad.length > 0 ? `Пропущено строк: ${bad.length} (${bad.slice(0, 5).join(", ")}…)` : "",
  };
}

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

/* Внешнее кольцо полигона в точках. У MultiPolygon берётся первая часть:
   оценка площади на экране нужна для понимания масштаба, а точную
   площадь по всем частям всё равно считает сервер. */
function outerRing(geom: GeoJsonPolygon): { lat: number; lon: number }[] {
  const ring =
    geom.type === "Polygon"
      ? (geom.coordinates as number[][][])[0]
      : (geom.coordinates as number[][][][])[0]?.[0];
  return (ring ?? []).map(([lon, lat]) => ({ lon, lat }));
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

  /* --- способ 4: таблица-ведомость --- */
  const tableInput = useRef<HTMLInputElement>(null);
  const [table, setTable] = useState<{ file: string; contours: TableContour[] } | null>(null);
  const [tableIndex, setTableIndex] = useState(0);
  const [tableError, setTableError] = useState("");

  /* Выбранный контур из ведомости. Объявлен здесь, а не рядом с разбором:
     от него зависят geometryReady и оценка площади ниже. */
  const tableContour = table?.contours[tableIndex] ?? null;

  /* Геометрия, которая уйдёт на расчёт. Раньше мастер разбирал файл ради
     числа вершин и выбрасывал сам полигон — считать было нечего. */
  const [geometry, setGeometry] = useState<GeoJsonPolygon | null>(null);
  /* Сохранённый контур и отдельная ошибка сохранения: расчёт мог удаться,
     а запись — нет, и путать эти два состояния нельзя. */
  const [saved, setSaved] = useState<SavedContour | null>(null);
  const [saveError, setSaveError] = useState("");
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

  /* Готовый контур вместо загрузки файла.

     Без него мастер требует принести GeoJSON, которого у человека на
     защите под рукой нет, и вся ветка «задать свой контур» остаётся
     непроверенной. Примеры лежат внутри участков с данными, поэтому
     расчёт по ним доходит до результата, а не до сообщения о том, что
     растров на эту территорию нет. */
  const useSample = (sample: SampleContour) => {
    setFileError("");
    setGeometry(sample.geometry as GeoJsonPolygon);
    setFile({
      name: `${sample.title}.geojson`,
      size: JSON.stringify(sample.geometry).length,
      vertices: sample.geometry.coordinates[0].length - 1,
    });
  };

  /* Полигон считается заданным, когда в нём есть что считать */
  const geometryReady =
    method === "file"
      ? file !== null
      : method === "draw"
        ? points.length >= 3
        : method === "table"
          ? tableContour !== null
          : parsed.points.length >= 3;

  const vertexCount =
    method === "file"
      ? file?.vertices
      : method === "draw"
        ? points.length
        : method === "table"
          ? (tableContour?.points.length ?? null)
          : parsed.points.length;

  /* Оценка площади на клиенте — только чтобы пользователь понял масштаб
     до расчёта. Настоящую площадь считает сервер по доле пересечения
     каждого пикселя с контуром, и она будет отличаться. */
  const drawnAreaHa =
    method === "coords" && parsed.points.length >= 3
      ? polygonAreaHa(parsed.points)
      : method === "table" && tableContour
        ? polygonAreaHa(tableContour.points)
        : /* Для файла площадь тоже считается по его собственным вершинам. */
          method === "file" && geometry
          ? polygonAreaHa(outerRing(geometry))
          : null;

  /* Проверки геометрии считаются по самому файлу. Раньше здесь стоял
     готовый список из data/mock: любому файлу показывалось «18 200 га» и
     «самопересечения не найдены», хотя площадь не измерялась, а
     пересечения не проверялись. Число на шаге проверки геометрии обязано
     быть про этот контур, иначе проверка ничего не проверяет. */
  const geometryChecks: { name: string; ok: true | "warn"; value: string }[] = geometryReady
    ? [
        {
          name: "Система координат",
          ok: true,
          value: "EPSG:4326 по спецификации GeoJSON",
        },
        {
          name: "Тип геометрии",
          ok: true,
          value:
            method === "file" && geometry
              ? `${geometry.type}, ${geometry.type === "Polygon" ? "одна часть" : `${geometry.coordinates.length} частей`}`
              : "Polygon, одна часть",
        },
        {
          name: "Число вершин",
          ok: true,
          value: vertexCount != null ? `${vertexCount}` : "—",
        },
        {
          name: "Площадь полигона",
          ok: true,
          value:
            drawnAreaHa !== null
              ? `примерно ${formatArea(Math.round(drawnAreaHa))} га`
              : "будет измерена расчётом",
        },
        {
          name: "Покрытие данными",
          ok: "warn",
          value: "проверяется расчётом",
        },
      ]
    : [];

  /* Источник границы обязателен (FR-21): все числа считаются по этому контуру,
     и если он обведён по лесничеству, допущение обязаны назвать мы. */
  const canSubmit = source.trim().length > 0;

  const pickTable = async (f: File) => {
    setTableError("");
    if (/\.xlsx?$/i.test(f.name)) {
      // XLSX — бинарный формат, разбор которого требует библиотеки.
      // Честнее сказать это сразу, чем принять файл и не посчитать.
      setTableError("XLSX пока не разбирается. Сохраните лист как CSV и загрузите его.");
      setTable(null);
      return;
    }
    const { contours, error } = parseContourTable(await f.text());
    if (contours.length === 0) {
      setTableError(error || "Таблица не разобралась");
      setTable(null);
      return;
    }
    setTableError(error);
    setTable({ file: f.name, contours });
    setTableIndex(0);
  };

  /* Геометрия для отправки: файл и таблица дают её напрямую, координаты
     собираются в полигон. Обводка на карте живёт в процентах экрана, а не
     в градусах, поэтому географией не является и на расчёт не уходит. */
  const requestGeometry = (): GeoJsonPolygon | null => {
    if (method === "file") return geometry;
    if (method === "coords" && parsed.points.length >= 3) return polygonFromPoints(parsed.points);
    if (method === "table" && tableContour) return polygonFromPoints(tableContour.points);
    return null;
  };

  /* Чем задана граница — это попадает в карточку контура, чтобы человек
     узнал свою загрузку среди прочих: имя файла, а не «Polygon». */
  const sourceLabel = (): string => {
    if (method === "file") return file?.name ?? "файл границы";
    if (method === "table") return table?.file ?? "таблица координат";
    if (method === "coords") return "координаты вершин";
    return "обводка на карте";
  };

  const runCalculation = async () => {
    setStep(3);
    setCalc(null);
    setCalcError("");
    setSaved(null);
    setSaveError("");

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
      const result = await postCalc({ geometry: geom, year_start: 2019, year_end: 2024 });
      setCalc(result);

      /* Контур сохраняется сразу после расчёта. Раньше загруженный файл
         разбирался в браузере, уходил на расчёт и исчезал: результат
         показывался один раз, и вернуться к нему было нельзя. Теперь он
         находится в списке, открывается повторно и попадает в сводку.

         Сохранение отделено от расчёта: если оно не удалось, результат
         всё равно показывается — он посчитан и записан в журнал, терять
         его из-за неудачной записи контура нельзя. */
      try {
        const contour = await saveContour({
          name: name.trim() || "Контур без названия",
          source_name: sourceLabel(),
          source_kind: method,
          geometry: geom,
          calc_id: result.calc_id,
        });
        setSaved(contour);
      } catch (err) {
        setSaveError(
          err instanceof ApiError ? err.message : "Расчёт готов, но контур не сохранён."
        );
      }
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

                  <div className="wz__samples">
                    <span className="wz__samples-label">или взять готовый пример</span>
                    <div className="wz__samples-row">
                      {SAMPLE_CONTOURS.map((sample) => (
                        <button
                          key={sample.id}
                          className="filter"
                          type="button"
                          onClick={() => useSample(sample)}
                          title={`${sample.parent} · ${sample.note}`}
                        >
                          {sample.title}
                        </button>
                      ))}
                    </div>
                    <p className="wz__samples-note">
                      Контуры лежат внутри участков, по которым у нас есть растры, — расчёт по
                      ним доходит до результата. Форма взята из проектных полигонов, границы
                      выдуманы: это пример работы сервиса, а не чей-то настоящий участок.
                    </p>
                  </div>
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

              {method === "table" && (
                <div className="wz__pane">
                  <input
                    ref={tableInput}
                    type="file"
                    accept=".csv,.tsv,.txt,.xlsx,.xls"
                    style={{ display: "none" }}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void pickTable(f);
                    }}
                  />
                  <button
                    className="btn btn--outline"
                    type="button"
                    onClick={() => tableInput.current?.click()}
                  >
                    <span>{table ? "Выбрать другую таблицу" : "Выбрать файл ведомости"}</span>
                  </button>

                  {table && (
                    <>
                      <div className="wz__file">
                        <b>{table.file}</b>
                        <span>
                          · контуров: {table.contours.length}
                          {tableContour && ` · вершин: ${tableContour.points.length}`}
                        </span>
                      </div>
                      {table.contours.length > 1 && (
                        <div className="wz__modes">
                          {table.contours.map((c, i) => (
                            <button
                              key={c.name + i}
                              type="button"
                              className={`wz__mode ${i === tableIndex ? "is-on" : ""}`}
                              onClick={() => setTableIndex(i)}
                            >
                              {c.name}
                            </button>
                          ))}
                        </div>
                      )}
                      <div className="wz__draw-foot">
                        <span>
                          {tableContour?.points.length ?? 0} вершин
                          {drawnAreaHa !== null &&
                            ` · примерно ${formatArea(Math.round(drawnAreaHa))} га`}
                        </span>
                      </div>
                    </>
                  )}

                  {tableError && <p className="wz__err">{tableError}</p>}

                  <p className="wz__note">
                    Ожидаются столбцы <b>name</b>, <b>lat</b>, <b>lon</b>, <b>order</b>. Несколько
                    участков в одном файле разделяются столбцом name, порядок обхода вершин задаёт
                    order. Разбор идёт здесь, в браузере: на сервер уходит готовая геометрия, а не
                    файл целиком.
                  </p>
                </div>
              )}

              <p className="wz__note">
                Контур можно задать четырьмя способами. Участки набора загружать не нужно — они уже
                посчитаны и открываются из каталога.
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
                {geometryChecks.map((c) => (
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
                Площадь здесь оценена по контуру на плоскости — чтобы понять масштаб до расчёта.
                Считать будет сервер по доле пересечения каждого пикселя с контуром, и значение
                будет другим. Покрытие данными выясняется там же: год без наблюдений даст прочерк,
                а не подстановку соседнего значения.
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
                  {calc !== null &&
                    (calc.stored === false
                      ? ` ${calc.storage_note ?? "Расчёт не записан в журнал."}`
                      : ` Расчёт ${calc.calc_id} записан в журнал.`)}
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
                  {saved ? (
                    <p className="wz__note">
                      Контур сохранён как {saved.contour_id} из «{saved.source_name}» — он остаётся
                      в разделе «Мои контуры» и учитывается в сводке по загруженным участкам.
                    </p>
                  ) : (
                    <p className="wz__note" style={{ color: "#9c3f66" }}>
                      {saveError ||
                        "Контур не сохранён: результат посчитан, но вернуться к нему из списка не получится."}
                    </p>
                  )}
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
              {/* Открывается ИМЕННО загруженный контур. Раньше здесь стоял
                  зашитый proj-03, и после своей загрузки открывался чужой
                  участок — ровно то, что замечают первым. */}
              <button
                className="btn btn--outline"
                type="button"
                disabled={saved === null}
                title={saved === null ? "Контур не сохранён — открывать нечего" : undefined}
                onClick={() => {
                  onClose();
                  if (saved) navigate(`/app/contours/${saved.contour_id}`);
                }}
              >
                <span>Открыть контур</span>
              </button>
            </>
          )}
        </footer>
      </div>
    </div>
  );
}
