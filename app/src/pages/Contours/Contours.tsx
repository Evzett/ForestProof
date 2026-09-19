/* Загруженные контуры: список, сводка и карточка одного контура. KAN-78.

   Зачем раздел. Загруженный файл раньше жил ровно до закрытия окна
   мастера: расчёт записывался в журнал, но сам контур не сохранялся, и
   вернуться к нему было нельзя — ни списком, ни ссылкой. Раздел
   закрывает этот разрыв: файл сохраняется, находится и открывается
   повторно, а сводка считает статистику по загруженным участкам.

   Разграничение. Список и карточка открыты наблюдателю: демо должно
   просматриваться без входа. Загрузка и удаление — аналитику, удаление
   чужого — администратору, и это проверяет сервер, а не эти кнопки. */

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Card, StatPill, formatDecimal, formatNumber, plural } from "../../components/ui";
import { AddPlotButton, PageHead } from "../../components/AppShell";
import { useSession } from "../../data/session";
import {
  ApiError,
  deleteContour,
  getContour,
  getContourStats,
  getContours,
  type ContourStats,
  type SavedContour,
} from "../../api";
import "./Contours.css";

const SOURCE_LABEL: Record<string, string> = {
  file: "файл границы",
  table: "таблица координат",
  coords: "координаты вершин",
  draw: "обводка на карте",
};

function when(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/* ================= Список и сводка ================= */

export function Contours() {
  const { session } = useSession();
  const [rows, setRows] = useState<SavedContour[] | null>(null);
  const [stats, setStats] = useState<ContourStats | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");

  const load = useCallback(() => {
    setError("");
    Promise.all([getContours(), getContourStats()])
      .then(([list, summary]) => {
        setRows(list.contours);
        setStats(summary);
      })
      .catch((err) => {
        // Без бэкенда раздел пуст — и говорит об этом, а не показывает
        // выдуманный список: сохранённые контуры живут только на сервере.
        setRows([]);
        setStats(null);
        setError(err instanceof ApiError ? err.message : "Список контуров недоступен.");
      });
  }, []);

  useEffect(load, [load]);

  const remove = async (row: SavedContour) => {
    try {
      await deleteContour(row.contour_id);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Удалить не удалось.");
    }
  };

  /* Поиск по тому, чем человек запомнил свою загрузку: название, имя
     файла, номер контура и номер расчёта. По координатам не ищем —
     их никто не помнит. */
  const needle = query.trim().toLowerCase();
  const shown = (rows ?? []).filter((row) =>
    needle === ""
      ? true
      : [row.name, row.source_name, row.contour_id, row.calc_id ?? ""]
          .join(" ")
          .toLowerCase()
          .includes(needle)
  );

  return (
    <>
      <PageHead
        title="Мои контуры"
        subtitle="Границы, загруженные в сервис, и расчёты по ним. Участки набора посчитаны заранее и лежат в разделе «Участки»"
        action={<AddPlotButton label="Загрузить контур" />}
      />

      {stats && stats.total > 0 && (
        <div className="cnt-stats">
          <StatPill value={String(stats.total)} caption="загружено контуров" />
          <StatPill value={`${formatNumber(Math.round(stats.area_ha))} га`} caption="суммарная площадь" />
          <StatPill
            value={String(stats.losing_carbon)}
            caption={`${plural(stats.losing_carbon, ["теряет", "теряют", "теряют"])} углерод`}
          />
          {/* «Недоступно» показано отдельной плашкой, а не нулём:
              это разные ответы, и смешивать их нельзя (Е-05). */}
          <StatPill
            value={stats.units_unavailable > 0 ? String(stats.units_unavailable) : "—"}
            caption="единицы недоступны"
          />
        </div>
      )}

      {error && (
        <Card className="mb20">
          <p className="ov-note" style={{ marginTop: 0 }}>
            {error} Участки набора при этом открываются: они посчитаны заранее и сервиса не
            требуют.
          </p>
        </Card>
      )}

      {rows !== null && rows.length === 0 && !error && (
        <Card title="Пока ничего не загружено">
          <p className="ov-note" style={{ marginTop: 0 }}>
            {session.can.upload
              ? "Загрузите границу участка файлом GeoJSON, таблицей координат или списком вершин — расчёт пойдёт по тем же растрам и тем же кодом, что и участки набора."
              : "Просмотр открыт без входа. Чтобы загрузить свой контур и посчитать по нему, нужен вход аналитиком."}
          </p>
        </Card>
      )}

      {rows !== null && rows.length > 0 && (
        <Card
          title="Загруженные контуры"
          note={`${shown.length} из ${rows.length}`}
          className="mb20"
        >
          <label className="cnt-search">
            <span className="tile__label">поиск по названию, файлу или номеру</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="например: contour.geojson или AOI-0001"
            />
          </label>

          {shown.length === 0 ? (
            <p className="ov-note">
              По запросу «{query}» ничего не нашлось. Поиск идёт по названию, имени файла и номерам
              контура и расчёта.
            </p>
          ) : (
            <div className="tbl__scroll tbl__scroll--tall">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>контур</th>
                    <th>откуда</th>
                    <th className="num">площадь, га</th>
                    <th className="num">E, т CO₂-экв.</th>
                    <th className="num">единицы</th>
                    <th>кто и когда</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {shown.map((row) => (
                    <tr key={row.contour_id}>
                      <td>
                        <span className="tbl__name">
                          <Link to={`/app/contours/${row.contour_id}`}>
                            <b>{row.name}</b>
                          </Link>
                          <span>
                            {row.contour_id} · {row.year_start}—{row.year_end}
                          </span>
                        </span>
                      </td>
                      <td style={{ color: "var(--c-muted-alt)" }}>
                        {row.source_name}
                        <br />
                        <span style={{ fontSize: 11 }}>
                          {SOURCE_LABEL[row.source_kind] ?? row.source_kind}
                        </span>
                      </td>
                      <td className="num">{formatDecimal(row.area_ha, 1)}</td>
                      <td className="num">
                        {row.e_tco2e === null ? (
                          <span className="dash">—</span>
                        ) : (
                          `${row.e_tco2e > 0 ? "+" : ""}${formatNumber(Math.round(row.e_tco2e))}`
                        )}
                      </td>
                      <td className="num">
                        {row.units === null ? (
                          <span className="lvl lvl--none">недоступно</span>
                        ) : (
                          formatNumber(row.units)
                        )}
                      </td>
                      <td style={{ color: "var(--c-muted-alt)" }}>
                        {row.created_by ?? "—"}
                        <br />
                        <span style={{ fontSize: 11 }}>{when(row.created_at)}</span>
                      </td>
                      <td>
                        {/* Кнопка видна тому, кто по правилам может удалять.
                            Это удобство, а не ограничение: запрет стоит на
                            сервере и срабатывает в обход интерфейса тоже. */}
                        {session.can.upload &&
                          (session.can.manage || row.created_by === session.login) && (
                            <button
                              className="link-btn"
                              type="button"
                              onClick={() => remove(row)}
                            >
                              удалить
                            </button>
                          )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="ov-note">
            Площадь измерена по долям пересечения пикселей с контуром и может отличаться от площади
            полигона. Положительное E — потеря углерода из учитываемого пула, отрицательное —
            накопление.
          </p>
        </Card>
      )}
    </>
  );
}

/* ================= Карточка одного контура ================= */

export function ContourCard() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { session } = useSession();
  const [row, setRow] = useState<(SavedContour & { result: unknown }) | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    getContour(id)
      .then(setRow)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Контур недоступен."));
  }, [id]);

  if (error) {
    return (
      <>
        <PageHead title="Контур не открыт" />
        <Card>
          <p className="ov-note" style={{ marginTop: 0 }}>
            {error}
          </p>
          <div className="report-actions">
            <Link className="btn btn--outline btn--inline" to="/app/contours">
              <span>К списку контуров</span>
            </Link>
          </div>
        </Card>
      </>
    );
  }

  if (row === null) return null;

  const remove = async () => {
    try {
      await deleteContour(row.contour_id);
      navigate("/app/contours");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Удалить не удалось.");
    }
  };

  return (
    <>
      <PageHead
        title={row.name}
        subtitle={`${row.contour_id} · загружен из «${row.source_name}» · ${SOURCE_LABEL[row.source_kind] ?? row.source_kind}`}
      />

      <Card title="Что посчитано" note={row.calc_id ?? "расчёт не привязан"} className="mb20">
        <dl className="kv">
          <div>
            <dt>площадь по контуру</dt>
            <dd className="tabular">{formatDecimal(row.area_ha, 4)} га</dd>
          </div>
          <div>
            <dt>период</dt>
            <dd>
              {row.year_start}—{row.year_end}
            </dd>
          </div>
          <div>
            <dt>результат E</dt>
            <dd className="tabular">
              {row.e_tco2e === null
                ? "—"
                : `${row.e_tco2e > 0 ? "+" : ""}${formatNumber(Math.round(row.e_tco2e))} т CO₂-экв.`}
            </dd>
          </div>
          <div>
            <dt>потенциальные единицы</dt>
            <dd className="tabular">
              {row.units === null ? "недоступно" : formatNumber(row.units)}
              {row.reason ? ` · ${row.reason}` : ""}
            </dd>
          </div>
          <div>
            <dt>кто загрузил</dt>
            <dd>{row.created_by ?? "автор не записан"}</dd>
          </div>
          <div>
            <dt>когда</dt>
            <dd>{when(row.created_at)}</dd>
          </div>
        </dl>

        <p className="ov-note">
          Расчёт шёл по тем же растрам и тем же кодом, что и участки набора: формулы живут в
          расчётном ядре, интерфейс их не повторяет.
        </p>

        <div className="report-actions">
          <Link className="btn btn--outline btn--inline" to="/app/contours">
            <span>К списку контуров</span>
          </Link>
          {session.can.upload && (session.can.manage || row.created_by === session.login) && (
            <button className="btn btn--ghost btn--inline" type="button" onClick={remove}>
              <span>Удалить контур</span>
            </button>
          )}
        </div>
      </Card>

      <Card title="Граница">
        <p className="ov-note" style={{ marginTop: 0 }}>
          Геометрия сохранена целиком — по ней контур пересчитывается и воспроизводится независимо
          от интерфейса.
        </p>
        <pre className="cnt-geom">{JSON.stringify(row.geometry, null, 2)}</pre>
      </Card>
    </>
  );
}
