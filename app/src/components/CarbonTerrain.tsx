import { useEffect, useRef, useState } from "react";
import { formatDecimal } from "./ui";
import type { Terrain } from "../data/case";
import "./CarbonTerrain.css";

/* Объёмный рельеф запаса углерода.

   Та же сетка пикселей продукта, что и на плоской карте, но высота
   столбика — запас в т C/га, а цвет — изменение за период. Рисуется на
   canvas в изометрии: библиотеки для трёх измерений здесь не нужно, а
   тащить её ради трёх с половиной тысяч параллелепипедов тем более.

   Это не иллюстрация. Высоты берутся из тех же чисел, из которых
   считается ΔC, поэтому провал на рельефе и вклад в результат — одно
   и то же место. Заодно видно, что такое «пиксель продукта»: каждый
   столбик и есть один пиксель, около половины гектара.

   Тень и наклон граней — чистое оформление, они ничего не кодируют.
   Значение несут только высота и цвет, и об этом сказано подписью. */

const EMPTY = -1;

type View = { rotation: number; tilt: number };

function shade(base: [number, number, number], k: number): string {
  const [r, g, b] = base;
  return `rgb(${Math.round(r * k)} ${Math.round(g * k)} ${Math.round(b * k)})`;
}

/* Цвет столбика.

   Основа — сам запас: чем плотнее лес, тем темнее зелень. Поверх неё
   подмешивается коричневый там, где запас упал. Раскрашивать только по
   изменению было бы нагляднее, но неверно: получилась бы тепловая карта,
   на которой густой лес и голая земля одного цвета, если ни там ни там
   ничего не менялось. */
function colorFor(stock: number, delta: number, span: number): [number, number, number] {
  const density = Math.max(0, Math.min(1, stock));
  const green: [number, number, number] = [
    206 - 150 * density,
    222 - 130 * density,
    176 - 130 * density,
  ];
  const drop = Math.max(0, Math.min(1, -delta / (span || 1)));
  const brown: [number, number, number] = [156, 104, 72];
  return [
    green[0] + (brown[0] - green[0]) * drop,
    green[1] + (brown[1] - green[1]) * drop,
    green[2] + (brown[2] - green[2]) * drop,
  ];
}

export default function CarbonTerrain({ terrain, name }: { terrain: Terrain; name: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [year, setYear] = useState<"start" | "end">("end");
  const [view, setView] = useState<View>({ rotation: -0.62, tilt: 0.52 });
  const dragRef = useRef<{ x: number; y: number; rotation: number; tilt: number } | null>(null);

  const { width, height, start, end, peak_t_ha: peak } = terrain;
  const values = year === "end" ? end : start;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const cssWidth = canvas.clientWidth;
    const cssHeight = canvas.clientHeight;
    canvas.width = Math.round(cssWidth * dpr);
    canvas.height = Math.round(cssHeight * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssWidth, cssHeight);

    const cos = Math.cos(view.rotation);
    const sin = Math.sin(view.rotation);
    const tilt = view.tilt;

    /* Масштаб считается по самой проекции, а не по стороне сетки.
       При повороте габариты картинки меняются вдвое, и фиксированный
       шаг оставлял рельеф либо мелким пятном в центре, либо обрезанным
       по краям. Берём четыре угла, смотрим, во что они превратились,
       и подгоняем масштаб под холст. */
    const liftRatio = 1.9;
    const corners: [number, number, number][] = [
      [0, 0, 0],
      [width, 0, 0],
      [0, height, 0],
      [width, height, 0],
      [0, 0, 1],
      [width, 0, 1],
      [0, height, 1],
      [width, height, 1],
    ];
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const [cx, cy, ch] of corners) {
      const dx = cx - width / 2;
      const dy = cy - height / 2;
      const px = dx * cos - dy * sin;
      const py = (dx * sin + dy * cos) * tilt - ch * liftRatio;
      minX = Math.min(minX, px);
      maxX = Math.max(maxX, px);
      minY = Math.min(minY, py);
      maxY = Math.max(maxY, py);
    }
    const pad = 16;
    const step = Math.min(
      (cssWidth - pad * 2) / Math.max(maxX - minX, 1),
      (cssHeight - pad * 2) / Math.max(maxY - minY, 1)
    );
    const lift = step * liftRatio;
    const originX = cssWidth / 2 - ((minX + maxX) / 2) * step;
    const originY = cssHeight / 2 - ((minY + maxY) / 2) * step;

    const project = (gx: number, gy: number, h: number) => {
      const dx = gx - width / 2;
      const dy = gy - height / 2;
      const rx = dx * cos - dy * sin;
      const ry = dx * sin + dy * cos;
      return { x: originX + rx * step, y: originY + ry * step * tilt - h * lift };
    };

    /* Порядок обхода зависит от поворота: рисуем от дальних к ближним,
       иначе передние столбики окажутся под задними. */
    const backToFront: [number, number][] = [];
    for (let gy = 0; gy < height; gy++) {
      for (let gx = 0; gx < width; gx++) backToFront.push([gx, gy]);
    }
    backToFront.sort((a, b) => {
      const da = (a[0] - width / 2) * sin + (a[1] - height / 2) * cos;
      const db = (b[0] - width / 2) * sin + (b[1] - height / 2) * cos;
      return da - db;
    });

    const deltaSpan = Math.max(peak * 0.35, 1);
    for (const [gx, gy] of backToFront) {
      const index = gy * width + gx;
      const value = values[index];
      if (value === EMPTY) continue;

      const delta = end[index] === EMPTY || start[index] === EMPTY ? 0 : end[index] - start[index];
      const norm = Math.max(0, Math.min(1, value / (peak || 1)));
      const base = colorFor(norm, delta, deltaSpan);

      const top = project(gx, gy, norm);
      const topRight = project(gx + 1, gy, norm);
      const topDown = project(gx, gy + 1, norm);
      const bottom = project(gx, gy, 0);

      // верхняя грань
      ctx.fillStyle = shade(base, 1);
      ctx.beginPath();
      ctx.moveTo(top.x, top.y);
      ctx.lineTo(topRight.x, topRight.y);
      ctx.lineTo(topRight.x + (topDown.x - top.x), topRight.y + (topDown.y - top.y));
      ctx.lineTo(topDown.x, topDown.y);
      ctx.closePath();
      ctx.fill();

      // боковая грань — только тень, значения не несёт
      ctx.fillStyle = shade(base, 0.62);
      ctx.beginPath();
      ctx.moveTo(top.x, top.y);
      ctx.lineTo(topDown.x, topDown.y);
      ctx.lineTo(topDown.x, topDown.y + (bottom.y - top.y));
      ctx.lineTo(bottom.x, bottom.y);
      ctx.closePath();
      ctx.fill();

      ctx.fillStyle = shade(base, 0.78);
      ctx.beginPath();
      ctx.moveTo(top.x, top.y);
      ctx.lineTo(topRight.x, topRight.y);
      ctx.lineTo(topRight.x, topRight.y + (bottom.y - top.y));
      ctx.lineTo(bottom.x, bottom.y);
      ctx.closePath();
      ctx.fill();
    }
  }, [values, start, end, width, height, peak, view]);

  const onDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    dragRef.current = {
      x: event.clientX,
      y: event.clientY,
      rotation: view.rotation,
      tilt: view.tilt,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    setView({
      rotation: drag.rotation + (event.clientX - drag.x) * 0.006,
      /* Наклон ограничен: сверху рельеф превращается в плоскую карту,
         снизу столбики загораживают друг друга и смотреть не на что. */
      tilt: Math.max(0.18, Math.min(0.9, drag.tilt + (event.clientY - drag.y) * 0.003)),
    });
  };

  const onUp = () => {
    dragRef.current = null;
  };

  const lost = values.filter((v, i) => v !== EMPTY && end[i] < start[i]).length;
  const grown = values.filter((v, i) => v !== EMPTY && end[i] > start[i]).length;
  const total = values.filter((v) => v !== EMPTY).length;

  return (
    <div className="terrain">
      <div className="terrain__bar">
        <div className="terrain__years">
          <button
            type="button"
            className={year === "start" ? "is-on" : ""}
            onClick={() => setYear("start")}
          >
            {terrain.start_year}
          </button>
          <button
            type="button"
            className={year === "end" ? "is-on" : ""}
            onClick={() => setYear("end")}
          >
            {terrain.end_year}
          </button>
        </div>
        <span className="terrain__hint">тяните мышью, чтобы повернуть</span>
      </div>

      <canvas
        ref={canvasRef}
        className="terrain__canvas"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        role="img"
        aria-label={`Объёмный рельеф запаса углерода, ${name}, ${
          year === "end" ? terrain.end_year : terrain.start_year
        } год`}
      />

      <dl className="terrain__kv">
        <div>
          <dt>высота столбика</dt>
          <dd>запас, до {formatDecimal(peak, 0)} т C/га</dd>
        </div>
        <div>
          <dt>один столбик</dt>
          <dd>
            пиксель продукта, {formatDecimal(terrain.pixel_area_ha, 2)} га · всего {total}
          </dd>
        </div>
        <div>
          <dt>цвет</dt>
          <dd>
            <i className="terrain__dot terrain__dot--up" /> запас вырос на {grown} ·{" "}
            <i className="terrain__dot terrain__dot--down" /> упал на {lost}
          </dd>
        </div>
      </dl>

      <p className="ov-note">
        Высоты взяты из тех же чисел, из которых считается изменение запаса, поэтому провал на
        рельефе и вклад в результат — одно и то же место. Наклон граней и тень — оформление,
        значение несут только высота и цвет.
      </p>
    </div>
  );
}
