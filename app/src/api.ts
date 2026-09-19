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

/* Токен сессии. KAN-78.

   Сервер кладёт его ещё и в куку с httpOnly, но фронт живёт на другом
   порту, а на межсайтовый запрос кука не поедет. Поэтому для разработки
   и демо токен носим заголовком. В localStorage — чтобы вход пережил
   перезагрузку страницы: иначе аналитик терял бы его на каждом F5. */
const TOKEN_KEY = "forestproof_token";

function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    // Приватное окно или запрещённые данные сайта: работаем без памяти,
    // вход просто не переживёт перезагрузку.
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* см. readToken */
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  const token = readToken();
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
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

/* ---------- Роли и вход. KAN-78 ---------- */

export type Session = {
  authenticated: boolean;
  login: string | null;
  display_name: string | null;
  role: "viewer" | "analyst" | "admin";
  role_label: string;
  can: { view: boolean; calculate: boolean; upload: boolean; manage: boolean };
  token?: string;
};

export function getSession(): Promise<Session> {
  return request<Session>("/api/auth/me");
}

export function login(loginName: string, password: string): Promise<Session> {
  return request<Session>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ login: loginName, password }),
  });
}

export function logout(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
}

/* ---------- Сохранённые контуры. KAN-78 ---------- */

export type SavedContour = {
  contour_id: string;
  name: string;
  source_name: string;
  source_kind: string;
  geometry: GeoJsonPolygon;
  area_ha: number;
  year_start: number;
  year_end: number;
  calc_id: string | null;
  created_by: string | null;
  created_at: string;
  e_tco2e: number | null;
  units: number | null;
  reason: string | null;
};

export type ContourStats = {
  total: number;
  area_ha: number;
  with_units: number;
  units_unavailable: number;
  units_total: number;
  e_tco2e_total: number | null;
  losing_carbon: number;
  gaining_carbon: number;
};

export function getContours(): Promise<{ contours: SavedContour[] }> {
  return request<{ contours: SavedContour[] }>("/api/contours");
}

export function getContourStats(): Promise<ContourStats> {
  return request<ContourStats>("/api/contours/stats");
}

export function getContour(id: string): Promise<SavedContour & { result: CalcResult | null }> {
  return request<SavedContour & { result: CalcResult | null }>(`/api/contours/${id}`);
}

export function saveContour(body: {
  name: string;
  source_name: string;
  source_kind: string;
  geometry: GeoJsonPolygon;
  calc_id: string;
}): Promise<SavedContour> {
  return request<SavedContour>("/api/contours", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteContour(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/contours/${id}`, { method: "DELETE" });
}
