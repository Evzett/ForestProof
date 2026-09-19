/* Обводка контура по настоящей карте. KAN-78.

   Раньше здесь была картинка и SVG поверх неё: клики складывались в
   проценты от ширины полотна и никуда дальше не шли. Контур выглядел
   нарисованным, а в API уходил пустой запрос — «обводка» не работала
   вовсе, и это было незаметно, потому что полигон на экране рисовался.

   Теперь карта настоящая: растровые тайлы OpenStreetMap, клик даёт
   долготу и широту, и в мастер возвращаются те же {lat, lon}, что
   приходят из списка координат. Дальше по коду разницы между способами
   ввода нет — и это главное, что даёт замена: один путь вместо двух.

   Почему MapLibre и OSM: библиотека свободная и без ключа, тайлы тоже.
   Ключ, который нужно где-то хранить и который однажды кончится, в
   демо, живущее на чужой машине, ставить не стоит.

   Тайлы идут из сети. Офлайн карта не загрузится — об этом честно
   написано на месте карты, а остальные три способа ввода контура
   работают без сети. */

import { useEffect, useMemo, useRef, useState } from "react";
/* Именованный импорт, а не default: в maplibre-gl 6 общего экспорта по
   умолчанию нет, и `import maplibregl from` собирается, но падает в
   рантайме на первом же обращении. */
import {
  Map as MapLibreMap,
  NavigationControl,
  ScaleControl,
  type MapMouseEvent,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "./DrawMap.css";

export type LatLon = { lat: number; lon: number };

/* Куда смотреть при открытии. Центры участков набора: рисовать контур
   имеет смысл там, где под ним есть растры, и начинать с пустого океана
   значит заставлять человека искать лес вручную. */
export const START_PLACES = [
  { id: "tver", label: "Тверская область", lat: 56.61, lon: 32.94, zoom: 11 },
  { id: "vologda", label: "Вологодская область", lat: 59.45, lon: 40.7, zoom: 11 },
  { id: "mordovia", label: "Мордовия", lat: 54.87, lon: 43.2, zoom: 11 },
  { id: "krasnoyarsk", label: "Красноярский край", lat: 58.2, lon: 96.5, zoom: 9 },
];

/* Площадь по формуле шнурков в локальной равнопромежуточной проекции.
   Та же, что в мастере: оценка масштаба до расчёта, не итоговое число. */
function areaHa(points: LatLon[]): number {
  if (points.length < 3) return 0;
  const latMean = points.reduce((a, p) => a + p.lat, 0) / points.length;
  const mPerDegLat = 111132.92;
  const mPerDegLon = 111412.84 * Math.cos((latMean * Math.PI) / 180);
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    sum += (a.lon * mPerDegLon) * (b.lat * mPerDegLat) - (b.lon * mPerDegLon) * (a.lat * mPerDegLat);
  }
  return Math.abs(sum / 2) / 10000;
}

const STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 19,
      // Указание авторства обязательно по условиям OSM и показывается
      // на самой карте — убирать его нельзя.
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

/* Контур рисуется поверх карты обычным SVG, а не слоем MapLibre.

   Слоем было нельзя. Источник geojson в MapLibre разбирается в
   веб-воркере, а воркер в нашей сборке не отвечает: источник навсегда
   остаётся в состоянии «загружается», `setData` уходит в никуда, и на
   карте не появляется ничего — при том, что тайлы грузятся, точки
   ставятся и площадь считается. Это было видно по `isStyleLoaded()`,
   который оставался ложным, и по `querySourceFeatures`, который всегда
   возвращал пусто.

   Чинить воркер ради десятка точек незачем. Оверлей — это ровно то, что
   нужно: координаты переводятся в пиксели через `map.project`, и весь
   рисунок остаётся обычным DOM. Заодно исчезает целый класс проблем со
   сборкой воркеров.

   Пересчёт идёт на каждое движение карты. Точек единицы, и разница
   между «дёшево» и «очень дёшево» здесь никого не волнует. */

export default function DrawMap({
  points,
  onChange,
}: {
  points: LatLon[];
  onChange: (points: LatLon[]) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const [failed, setFailed] = useState(false);
  /* Счётчик кадров. Его значение не важно — важно, что изменение
     заставляет пересчитать пиксели точек после движения карты. */
  const [frame, setFrame] = useState(0);
  const [place, setPlace] = useState(START_PLACES[0].id);

  /* Точки читаются обработчиком клика, который повешен один раз.
     Через состояние он видел бы только первый набор — замыкание
     запоминает то, что было на момент подписки. Ссылка всегда свежая. */
  const latest = useRef(points);
  latest.current = points;
  const emit = useRef(onChange);
  emit.current = onChange;

  useEffect(() => {
    if (!host.current || map.current) return;

    const start = START_PLACES[0];
    let instance: MapLibreMap;
    try {
      instance = new MapLibreMap({
        container: host.current,
        style: STYLE,
        center: [start.lon, start.lat],
        zoom: start.zoom,
        attributionControl: { compact: true },
      });
    } catch {
      // WebGL недоступен (старый браузер, отключённое ускорение).
      // Это не повод ронять весь мастер: три других способа ввода
      // контура работают, и об этом сказано на месте карты.
      setFailed(true);
      return;
    }
    map.current = instance;
    instance.addControl(new NavigationControl({ showCompass: false }), "top-right");
    instance.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");

    instance.on("error", (event) => {
      // Ошибка загрузки тайла — это отсутствие сети, а не поломка:
      // карта остаётся управляемой, просто серой.
      if (event?.error?.message?.includes("tile")) setFailed(true);
    });

    // Пересчёт пиксельных координат оверлея. Карта двигается — точки
    // едут вместе с ней, иначе контур «отклеился» бы при первом же
    // перетаскивании.
    const sync = () => setFrame((n) => n + 1);
    instance.on("move", sync);
    instance.on("zoom", sync);
    instance.on("resize", sync);
    instance.on("load", sync);

    const onClick = (event: MapMouseEvent) => {
      const { lng, lat } = event.lngLat;
      emit.current([...latest.current, { lat: +lat.toFixed(6), lon: +lng.toFixed(6) }]);
    };
    instance.on("click", onClick);

    // Правый клик снимает последнюю точку: промахнулся — верни, не
    // начиная заново. Меню браузера при этом не нужно.
    const onContext = (event: MapMouseEvent) => {
      event.preventDefault();
      emit.current(latest.current.slice(0, -1));
    };
    instance.on("contextmenu", onContext);

    return () => {
      instance.remove();
      map.current = null;
    };
  }, []);

  const jumpTo = (id: string) => {
    setPlace(id);
    const target = START_PLACES.find((p) => p.id === id);
    if (target && map.current) {
      map.current.flyTo({ center: [target.lon, target.lat], zoom: target.zoom });
    }
  };

  const ha = areaHa(points);

  /* Точки в пикселях полотна. Пересчитываются при каждом движении
     карты: `frame` в зависимостях именно для этого — его значение не
     используется, меняется только чтобы запустить пересчёт. */
  const pixels = useMemo(() => {
    const instance = map.current;
    if (!instance) return [];
    void frame;
    return points.map((p) => instance.project([p.lon, p.lat]));
  }, [points, frame]);

  return (
    <div className="drawmap">
      <div className="drawmap__bar">
        <label className="drawmap__jump">
          <span>перейти к</span>
          <select value={place} onChange={(e) => jumpTo(e.target.value)}>
            {START_PLACES.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <span className="drawmap__hint">
          левый клик — вершина, правый — убрать последнюю
        </span>
      </div>

      <div className="drawmap__canvas" ref={host}>
        {pixels.length > 0 && (
          /* Оверлей не ловит указатель: клик должен доходить до карты,
             иначе поставить вершину поверх уже нарисованного контура
             стало бы невозможно. */
          <svg className="drawmap__overlay" aria-hidden="true">
            {pixels.length >= 3 && (
              <polygon points={pixels.map((p) => `${p.x},${p.y}`).join(" ")} />
            )}
            {pixels.length === 2 && (
              <line x1={pixels[0].x} y1={pixels[0].y} x2={pixels[1].x} y2={pixels[1].y} />
            )}
            {pixels.map((p, i) => (
              <circle key={i} cx={p.x} cy={p.y} r="5" />
            ))}
          </svg>
        )}
        {failed && (
          <div className="drawmap__failed">
            <b>Карта не загрузилась</b>
            <span>
              Тайлы OpenStreetMap идут из сети, и без неё карты не будет. Контур можно задать
              файлом, списком координат или таблицей — эти способы работают офлайн.
            </span>
          </div>
        )}
      </div>

      <div className="drawmap__foot">
        <span>
          {points.length === 0
            ? "кликните по карте — каждая точка добавляет вершину"
            : `${points.length} вершин${points.length >= 3 ? ` · примерно ${Math.round(ha).toLocaleString("ru-RU")} га` : ", нужно минимум 3"}`}
        </span>
        <span className="drawmap__acts">
          <button
            className="link-btn"
            type="button"
            onClick={() => onChange(points.slice(0, -1))}
            disabled={points.length === 0}
          >
            отменить точку
          </button>
          <button
            className="link-btn"
            type="button"
            onClick={() => onChange([])}
            disabled={points.length === 0}
          >
            очистить
          </button>
        </span>
      </div>

      {points.length >= 3 && ha > 2000 && (
        <p className="drawmap__warn">
          Контур больше 2000 га — предела, заданного условиями кейса. Расчёт откажет: уменьшите
          обводку.
        </p>
      )}
    </div>
  );
}
