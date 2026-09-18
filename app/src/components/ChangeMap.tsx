import { useState } from "react";
import type { Area } from "../data/case";
import { PARAMETERS, formatBbox } from "../data/case";
import "./ChangeMap.css";

/* Карта участка по тем же пикселям, по которым считаются числа.

   Это не подложка с тайлами: слои нарисованы из самих растров набора
   скриптом извлечения, поэтому пятно на карте и вклад в дельту запаса —
   одно и то же место. Разрешение слоёв равно разрешению продукта и
   намеренно не сглажено: показывать 100-метровый пиксель гладким
   градиентом значит обещать точность, которой нет. */

const LAYERS = [
  { key: "change", label: "изменение запаса", hint: "2019 → 2024, т C/га на пиксель" },
  { key: "stock", label: "запас на конец", hint: "т C/га, ESA CCI Biomass v7.0" },
  { key: "loss", label: "потери покрова", hint: "Hansen GFC v1.13, год потери" },
] as const;

export default function ChangeMap({ area }: { area: Area }) {
  const [layer, setLayer] = useState<(typeof LAYERS)[number]["key"]>("change");
  const maps = area.maps;

  if (!maps) {
    return (
      <p className="ov-note" style={{ marginTop: 0 }}>
        Слои карты для этого участка не построены.
      </p>
    );
  }

  const active = LAYERS.find((l) => l.key === layer)!;
  const size = layer === "loss" ? maps.loss_size : maps.size;

  return (
    <div className="cmap">
      <div className="cmap__tabs">
        {LAYERS.map((l) => (
          <button
            key={l.key}
            type="button"
            className={`cmap__tab ${layer === l.key ? "is-on" : ""}`.trim()}
            aria-pressed={layer === l.key}
            onClick={() => setLayer(l.key)}
          >
            {l.label}
          </button>
        ))}
      </div>

      <div className="cmap__canvas">
        <img
          src={`/maps/${maps[layer]}`}
          alt={`${active.label}: ${area.name}`}
          width={size[0]}
          height={size[1]}
        />
        <span className="cmap__scale">
          {size[0]} × {size[1]} пикселей продукта
        </span>
      </div>

      <div className="cmap__legend">
        {layer === "change" && (
          <>
            <span>
              <i className="cmap__swatch cmap__swatch--loss" /> потеря запаса
            </span>
            <span>
              <i className="cmap__swatch cmap__swatch--gain" /> накопление
            </span>
            <span className="cmap__note">
              шкала до ±{Math.round(maps.change_span_tc_ha)} т C/га
            </span>
          </>
        )}
        {layer === "stock" && (
          <span className="cmap__note">
            Темнее — больше запас. Шкала нормирована на 98-й процентиль участка.
          </span>
        )}
        {layer === "loss" && (
          <>
            <span>
              <i className="cmap__swatch cmap__swatch--recent" /> потеря в 2019—2024
            </span>
            <span>
              <i className="cmap__swatch cmap__swatch--old" /> потеря до 2019
            </span>
            <span className="cmap__note">
              порог древесного покрова {PARAMETERS.treecover_threshold_pct} %
            </span>
          </>
        )}
      </div>

      <p className="ov-note">
        <b>Что это за квадратики.</b> Один квадрат — один пиксель спутникового продукта, около
        100 метров в поперечнике и примерно 0,54 га на этой широте. Участок целиком занимает
        в продукте всего несколько тысяч таких пикселей, поэтому картинка и выглядит крупной
        мозаикой. Сглаживать её нельзя: гладкий градиент пообещал бы точность, которой в
        данных нет.
      </p>
      <p className="ov-note">
        {active.hint}. Контур запроса — {formatBbox(area.bbox)} в WGS 84. Причина изменения по
        карте не определяется: подтверждение берётся из продукта гарей и снимков.
      </p>
    </div>
  );
}
