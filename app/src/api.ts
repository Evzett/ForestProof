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
      /* Куки ходят с каждым запросом. Без этого сервер не видел ни
         сессионной куки, ни отметки «человек вышел сам»: фронт живёт на
         другом порту, а на межсайтовый запрос браузер куки не шлёт, пока
         его об этом не попросят. Токен мы и так носим заголовком, но
         выход из демонстрационного режима держится именно на куке. */
      credentials: "include",
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

/* Роли сервиса. `viewer` — не назначаемая роль, а вид сервиса до входа:
   в списке панели администратора её нет. */
export type RoleName = "viewer" | "investor" | "operator" | "admin";

export type Avatar = { initials: string; color: string };

export type Session = {
  authenticated: boolean;
  login: string | null;
  display_name: string | null;
  role: RoleName;
  role_label: string;
  role_note: string;
  blocked: boolean;
  /** Доступен ли возврат в демонстрационный режим (на проде — нет). */
  demo_available: boolean;
  avatar: Avatar | null;
  can: {
    view: boolean;
    value: boolean;
    calculate: boolean;
    upload: boolean;
    publish: boolean;
    manage: boolean;
  };
  token?: string;
};

export type RoleInfo = { value: RoleName; label: string; note: string };

export function getSession(): Promise<Session> {
  return request<Session>("/api/auth/me");
}

export function login(loginName: string, password: string): Promise<Session> {
  return request<Session>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ login: loginName, password }),
  });
}

/** Регистрация. Роль назначает сервер — прислать её нельзя. */
export function register(body: {
  login: string;
  display_name: string;
  password: string;
}): Promise<Session> {
  return request<Session>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function logout(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
}

/** Вернуться в демонстрационный режим после выхода. */
export function enterDemo(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/auth/demo", { method: "POST" });
}

export function getRoles(): Promise<{ roles: RoleInfo[] }> {
  return request<{ roles: RoleInfo[] }>("/api/auth/roles");
}

export function getPalette(): Promise<{ colors: string[] }> {
  return request<{ colors: string[] }>("/api/auth/palette");
}

export function updateProfile(body: {
  display_name?: string;
  avatar_color?: string;
}): Promise<Session> {
  return request<Session>("/api/auth/me", { method: "PATCH", body: JSON.stringify(body) });
}

export function changePassword(current: string, next: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/auth/password", {
    method: "POST",
    body: JSON.stringify({ current_password: current, new_password: next }),
  });
}

/* ---------- Панель администратора. KAN-78 ---------- */

export type AdminUser = {
  login: string;
  display_name: string;
  role: RoleName;
  role_label: string;
  blocked: boolean;
  avatar: Avatar;
  created_at: string | null;
  contours: number;
  calculations: number;
};

export function getUsers(): Promise<{ users: AdminUser[] }> {
  return request<{ users: AdminUser[] }>("/api/admin/users");
}

export function updateUser(
  login: string,
  body: { role?: RoleName; blocked?: boolean }
): Promise<AdminUser> {
  return request<AdminUser>(`/api/admin/users/${login}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function resetUserPassword(login: string, password: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/admin/users/${login}/password`, {
    method: "POST",
    body: JSON.stringify({ new_password: password }),
  });
}

export type SourceState = {
  sources: { name: string; kind: string; auth: string; ready: boolean; note: string }[];
  cache: { name: string; path: string; size_mb: number }[];
  contour_maps: { path: string; size_mb: number; count: number };
};

export function getSources(): Promise<SourceState> {
  return request<SourceState>("/api/admin/sources");
}

export function clearSourceCache(): Promise<{ ok: boolean; freed_mb: number }> {
  return request<{ ok: boolean; freed_mb: number }>("/api/admin/sources/cache", {
    method: "DELETE",
  });
}

/* ---------- Фоновый расчёт. KAN-78 ---------- */

export type CalcJob = {
  job_id: string;
  status: "queued" | "running" | "done" | "failed";
  step: number;
  steps: string[];
  error: string | null;
  calc_id: string | null;
  created_by: string | null;
  result: CalcResult | null;
};

export function startCalcJob(body: CalcRequest): Promise<{
  job_id: string;
  status: string;
  steps: string[];
}> {
  return request("/api/calc/jobs", { method: "POST", body: JSON.stringify(body) });
}

export function getCalcJob(id: string): Promise<CalcJob> {
  return request<CalcJob>(`/api/calc/jobs/${id}`);
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
  published: boolean;
  created_at: string;
  e_tco2e: number | null;
  units: number | null;
  reason: string | null;
  /* Картинки приходят именем файла плюс приставкой `maps_base` — так же,
     как у участков набора. Склеивает их `mapAsset` из data/case. */
  maps: {
    stock: string;
    change: string;
    loss: string;
    change_span_tc_ha: number | null;
  } | null;
  maps_base: string | null;
  scene: { image: string; date: string } | null;
  scenes_count: number;
  events_count: number;
  evidence_notes: string[];
  data_sources: string[];
  baseline_kind: string | null;
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

export function getContours(mine = false): Promise<{ contours: SavedContour[] }> {
  return request<{ contours: SavedContour[] }>(`/api/contours${mine ? "?mine=true" : ""}`);
}

/** Публикация контура: автор решает, видят ли его остальные. */
export function publishContour(id: string, published: boolean): Promise<SavedContour> {
  return request<SavedContour>(`/api/contours/${id}/publish?published=${published}`, {
    method: "POST",
  });
}

/* ---------- Журнал расчётов ---------- */

export type JournalEntry = {
  calc_id: string;
  project_id: string | null;
  calculated_at: string;
  methodology_version: string;
  algorithm_version: string;
  model_version: string | null;
  input_hash: string;
  created_by: string | null;
  author: string | null;
  mine: boolean;
};

export function getCalculations(mine = false): Promise<{ calculations: JournalEntry[] }> {
  return request<{ calculations: JournalEntry[] }>(
    `/api/calculations${mine ? "?mine=true" : ""}`
  );
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
