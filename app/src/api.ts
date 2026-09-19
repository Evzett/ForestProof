/* Единственный модуль, который ходит в сеть. KAN-69.

   Зачем отдельный слой, если экраны и так работают: четыре участка
   набора посчитаны заранее и лежат в case-data.json — это резервная
   копия демо, которая переживёт и отсутствие сети, и упавший бэкенд.
   Но свой контур предпосчитать нельзя по определению: файла с чужим
   полигоном не существует. Для него нужен сервер, и вот он.

   Правило: при недоступном API мы показываем причину, а не выдумываем
   числа. Правдоподобный результат, полученный ниоткуда, хуже честного
   «сервис расчёта недоступен». */

const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/+$/, "");

/** Адрес API. Пустая строка — тот же origin (за nginx на проде). */
export const apiBase = BASE;

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    // Сеть не ответила вовсе: сервис не запущен или недоступен.
    throw new ApiError("Сервис расчёта недоступен. Проверьте, что бэкенд запущен.", 0);
  }

  if (!response.ok) {
    // Причина отказа приходит от сервиса в detail и предназначена
    // пользователю: «контур вне набора», «год вне диапазона». Показываем
    // её как есть, а не подменяем общим «ошибка запроса».
    let reason = `Запрос отклонён (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") reason = body.detail;
    } catch {
      /* тело не JSON — остаётся общий текст */
    }
    throw new ApiError(reason, response.status);
  }

  return (await response.json()) as T;
}

export type ApiArea = {
  aoi_id: string;
  name: string | null;
  region: string | null;
  role: string | null;
  area_ha_declared: number | null;
  bbox: [number, number, number, number];
};

export type CalcRequest = {
  geometry?: GeoJsonPolygon;
  aoi_id?: string;
  year_start: number;
  year_end: number;
};

export type GeoJsonPolygon = {
  type: "Polygon" | "MultiPolygon";
  coordinates: number[][][] | number[][][][];
};

/** Период расчёта. Поля совпадают с Period из data/case.ts: форма одна,
    источник разный — иначе экраны пришлось бы писать дважды. */
export type CalcPeriod = {
  year_start: number;
  year_end: number;
  years: number;
  area_ha: number;
  c_start_t_ha: number;
  c_end_t_ha: number;
  e_tco2e: number;
  e_per_ha_year: number;
  e_base_tco2e: number;
  r_tco2e: number;
  h_tco2e: number;
  h_over_r: number | null;
  unc_share: number | null;
  units: number | null;
  available: boolean;
  status: string;
  reason: string | null;
  lower_tco2e: number;
  upper_tco2e: number;
  value_rub?: Record<string, number> | null;
};

export type CalcResult = {
  calc_id: string;
  calculated_at: string;
  input_hash: string;
  aoi_id: string;
  parent_area_name: string | null;
  area_ha: number;
  period: CalcPeriod;
  baseline_id: string | null;
  baseline_note: string;
  status: string;
  /* Записан ли расчёт в журнал. Недоступная база не отменяет расчёт,
     но означает, что этого расчёта не будет в списке сохранённых, —
     и сказать об этом обязаны мы, а не пропажа строки потом. */
  stored?: boolean;
  storage_note?: string;
};

export function getAreas(): Promise<{ areas: ApiArea[] }> {
  return request<{ areas: ApiArea[] }>("/api/areas");
}

export function postCalc(body: CalcRequest): Promise<CalcResult> {
  return request<CalcResult>("/api/calc", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Достаёт полигон из файла: Feature, FeatureCollection или голая геометрия. */
export function geometryFromGeoJson(raw: unknown): GeoJsonPolygon {
  const data = raw as Record<string, unknown>;
  const geometry =
    data?.type === "FeatureCollection"
      ? (data.features as Record<string, unknown>[] | undefined)?.[0]?.geometry
      : data?.type === "Feature"
        ? data.geometry
        : data;

  const geom = geometry as GeoJsonPolygon | undefined;
  if (!geom || (geom.type !== "Polygon" && geom.type !== "MultiPolygon")) {
    throw new Error("Ожидается Polygon или MultiPolygon в WGS 84");
  }
  if (!Array.isArray(geom.coordinates) || geom.coordinates.length === 0) {
    throw new Error("В геометрии нет координат");
  }
  return geom;
}

/** Замкнутый полигон из списка вершин — для обводки и ввода координат. */
export function polygonFromPoints(points: { lon: number; lat: number }[]): GeoJsonPolygon {
  const ring = points.map((p) => [p.lon, p.lat]);
  const first = ring[0];
  const last = ring[ring.length - 1];
  if (first && last && (first[0] !== last[0] || first[1] !== last[1])) {
    ring.push([first[0], first[1]]);
  }
  return { type: "Polygon", coordinates: [ring] };
}
