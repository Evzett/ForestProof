/* Карточка загруженного контура. KAN-78.

   Списка здесь нет: загруженные контуры лежат в разделе «Участки»
   вместе с участками набора. Отдельный раздел означал бы, что свой
   участок — объект другого сорта, а это тот же расчёт тем же кодом.
   Разница только в происхождении границы и базовой линии, и она
   подписана прямо на карточке.

   Карточка открыта наблюдателю: демо должно просматриваться без входа.
   Удаление — автору или администратору, и это проверяет сервер. */

import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Card, formatDecimal, formatNumber } from "../../components/ui";
import { PageHead } from "../../components/AppShell";
import { useSession } from "../../data/session";
import { ApiError, deleteContour, getContour, type SavedContour } from "../../api";
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
            <Link className="btn btn--outline btn--inline" to="/app/areas">
              <span>К участкам</span>
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
      navigate("/app/areas");
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
          <Link className="btn btn--outline btn--inline" to="/app/areas">
            <span>К участкам</span>
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
