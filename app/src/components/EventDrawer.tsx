import { ConfidencePill } from "./ui";
import type { DisturbanceEvent, EventType } from "../types";
import "./EventDrawer.css";

/* Drawer исследования события. Требование FR-84.
   Открывается по клику на строку нарушения, экран под ним не перезагружается. */

const EVENT_LABEL: Record<EventType, string> = {
  fire_supported: "подтверждено пожаром",
  non_fire: "не связано с пожаром",
  vegetation_stress: "стресс растительности",
  unknown: "тип не определён",
};

export default function EventDrawer({
  event,
  onClose,
}: {
  event: DisturbanceEvent;
  onClose: () => void;
}) {
  /* Физическая экспозиция — запас углерода на затронутой площади.
     Это не выброшенный объём: сколько из него окислилось, мы не считаем. */
  const exposure = Math.round(event.area_ha * 232.9);

  return (
    <div className="dr" role="dialog" aria-modal="true" aria-label={`Событие ${event.year} года`}>
      <div className="dr__backdrop" onClick={onClose} />
      <aside className="dr__panel">
        <header className="dr__head">
          <h2>Событие {event.year} года</h2>
          <button className="wz__close" type="button" onClick={onClose} aria-label="Закрыть">
            ✕
          </button>
        </header>

        <div className="dr__big tabular">
          {event.area_ha} <small>га</small>
        </div>

        <dl className="dr__list">
          <div>
            <dt>тип события</dt>
            <dd>{EVENT_LABEL[event.event_type]}</dd>
          </div>
          <div>
            <dt>пожарные признаки</dt>
            <dd>
              {event.fire_evidence ? (
                <span className="lvl lvl--medium">обнаружены</span>
              ) : (
                <span className="lvl lvl--none">нет</span>
              )}
            </dd>
          </div>
          <div>
            <dt>окно обнаружения</dt>
            <dd>18.06 — 27.08.{event.year}</dd>
          </div>
          <div>
            <dt>доверие к событию</dt>
            <dd>
              <ConfidencePill value={event.confidence} />
            </dd>
          </div>
          <div>
            <dt>источники</dt>
            <dd>Hansen GFC v1.13 · MODIS MCD64A1</dd>
          </div>
        </dl>

        <p className="dr__label">Снимки до и после · P1</p>
        <div className="dr__shots">
          <figure>
            <img src="/images/card-problem.jpg" alt="" />
            <figcaption>до · 12.06.{event.year}</figcaption>
          </figure>
          <figure>
            <img src="/images/card-limits.jpg" alt="" />
            <figcaption>после · 03.09.{event.year}</figcaption>
          </figure>
        </div>

        <dl className="dr__list">
          <div>
            <dt>dNBR</dt>
            <dd className="tabular">0,41</dd>
          </div>
          <div>
            <dt>изменение NDVI</dt>
            <dd className="tabular">−0,22</dd>
          </div>
        </dl>

        <div className="dr__exposure">
          <p>Физическая углеродная экспозиция затронутой области</p>
          <div className="dr__exposure-value tabular">
            {exposure.toLocaleString("ru-RU")} <small>т CO₂-экв.</small>
          </div>
          <p className="wz__note">
            Это запас углерода на затронутой площади, а не выброшенный объём. Сколько из него
            окислилось — мы не считаем.
          </p>
        </div>
      </aside>
    </div>
  );
}
