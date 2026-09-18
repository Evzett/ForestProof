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

function shade3(base: [number, number, number], k: number): [number, number, number] {
  return [base[0] * k, base[1] * k, base[2] * k];
}

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

export default function CarbonTerrain({
  terrain,
  name,
  startYear,
  endYear,
  highlightYear = null,
  compact = false,
}: {
  terrain: Terrain;
  name: string;
  startYear: number;
  endYear: number;
  /* Год, который надо подсветить: клетки, потерявшие покров именно в
     нём, горят, остальные гаснут. Приходит от наведения на столбец
     диаграммы — так видно, куда именно пришёлся этот столбец. */
  highlightYear?: number | null;
  /* Урезанный вид для витрины сравнения: без переключателей и подписей,
     только сам лес. */
  compact?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [year, setYear] = useState<"start" | "end">("end");
  const [view, setView] = useState<View>({ rotation: -0.62, tilt: 0.52 });
  /* Два прочтения одних и тех же чисел. «Лес» показывает запас деревьями:
     их высота и густота — это т C/га, и на вырубке их просто нет.
     «Рельеф» — те же значения столбиками, когда нужно сравнить высоты,
     а не впечатлиться. */
  const [mode, setMode] = useState<"forest" | "relief">("forest");
  /* Проигрывание по годам. Данные за все годы уже лежат рядом, поэтому
     «плёнка» — это не новая выгрузка, а другой способ прочитать ту же
     сетку: видно, что участок не потерял всё разом. */
  const [playing, setPlaying] = useState(false);
  const [frame, setFrame] = useState<number | null>(null);
  const dragRef = useRef<{ x: number; y: number; rotation: number; tilt: number } | null>(null);

  const { width, height, peak_t_ha: peak } = terrain;
  /* Рельеф смотрит на тот же период, что выбран сверху. Если в наборе
     нужного года нет, берём ближайший имеющийся — молча показывать
     чужой год нельзя, поэтому фактический год подписан на кнопке. */
  const nearest = (wanted: number) =>
    terrain.years.reduce((a, b) => (Math.abs(b - wanted) < Math.abs(a - wanted) ? b : a));
  const yearA = nearest(startYear);
  const yearB = nearest(endYear);
  const start = terrain.grids[String(yearA)] ?? [];
  const end = terrain.grids[String(yearB)] ?? [];
  /* Во время проигрывания показывается кадр, а не выбранный год. */
  const frameYear = frame === null ? null : terrain.years[frame];
  const values =
    frameYear !== null
      ? terrain.grids[String(frameYear)] ?? end
      : year === "end"
        ? end
        : start;

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

    /* Дерево в изометрии: ствол и три яруса кроны. Рисуется сразу после
       своей клетки, поэтому порядок «от дальних к ближним» соблюдается
       и для деревьев — иначе ближние оказались бы за дальними. */
    const drawTree = (
      px: number,
      py: number,
      size: number,
      base: [number, number, number]
    ) => {
      const trunkW = Math.max(1, size * 0.09);
      const trunkH = size * 0.28;
      ctx.fillStyle = "rgb(92 68 48)";
      ctx.fillRect(px - trunkW / 2, py - trunkH, trunkW, trunkH);

      const tiers = 3;
      for (let i = 0; i < tiers; i++) {
        const t = i / tiers;
        const halfW = size * (0.34 - t * 0.09);
        const bottom = py - trunkH - size * 0.42 * i;
        const top = bottom - size * 0.46;
        ctx.fillStyle = shade(base, 1 - i * 0.12);
        ctx.beginPath();
        ctx.moveTo(px, top);
        ctx.lineTo(px + halfW, bottom);
        ctx.lineTo(px - halfW, bottom);
        ctx.closePath();
        ctx.fill();
      }
    };

    for (const [gx, gy] of backToFront) {
      const index = gy * width + gx;
      const value = values[index];
      if (value === EMPTY) continue;

      /* Коричневый оттенок означает «этот пиксель потерял запас между
         2019 и 2024». Это свойство пары лет, а не года, поэтому на виде
         2019 он не наносится: иначе картинка утверждала бы, что лес уже
         повреждён, хотя тогда он ещё стоял. */
      const delta =
        frameYear !== null || year === "start" || end[index] === EMPTY || start[index] === EMPTY
          ? 0
          : end[index] - start[index];
      const norm = Math.max(0, Math.min(1, value / (peak || 1)));
      let base = colorFor(norm, delta, deltaSpan);
      /* Подсветка года: задетые клетки горят лаймом, остальные гаснут.
         Гасим, а не прячем — иначе исчезал бы и контур участка, и было
         бы непонятно, к чему относится подсвеченное пятно. */
      if (highlightYear !== null) {
        base =
          terrain.loss_years[index] === highlightYear
            ? [167, 187, 47]
            : [base[0] * 0.45 + 120, base[1] * 0.45 + 122, base[2] * 0.45 + 112];
      }

      /* В режиме леса рельеф приземляется: высоту показывают деревья,
         и если поднимать ещё и землю, одно и то же число считалось бы
         дважды, а лес поехал бы по склону. */
      const groundH = mode === "forest" ? norm * 0.18 : norm;
      const top = project(gx, gy, groundH);
      const topRight = project(gx + 1, gy, groundH);
      const topDown = project(gx, gy + 1, groundH);
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

      /* Дерево ставится не на каждый пиксель: при трёх с половиной тысячах
         крон рисунок превращается в сплошной ковёр, где не видно ни
         просек, ни границы вырубки. Шахматная выборка оставляет половину
         и сохраняет рисунок нарушений. */
      if (mode === "forest" && (gx + gy) % 2 === 0 && norm > 0.08) {
        const centre = project(gx + 0.5, gy + 0.5, groundH);
        drawTree(centre.x, centre.y, step * (1.4 + norm * 3.6), shade3(base, 0.92));
      }
    }
    /* В зависимостях стоят ключи, а не сами сетки. Сетка — это три с
       половиной тысячи чисел, и React сравнивал бы её на каждый кадр
       поворота; вдобавок в отладочной сборке он печатает массив
       зависимостей целиком, заваливая консоль. Сами данные меняются
       только вместе с годом и участком, поэтому ключей достаточно. */
  }, [terrain, yearA, yearB, year, frameYear, highlightYear, width, height, peak, view, mode]);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setFrame((previous) => {
        const next = (previous === null ? -1 : previous) + 1;
        if (next >= terrain.years.length) {
          setPlaying(false);
          return null;
        }
        return next;
      });
    }, 620);
    return () => window.clearInterval(timer);
  }, [playing, terrain.years.length]);

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
    <div className={`terrain ${compact ? "terrain--compact" : ""}`.trim()}>
      {compact ? null : (
      <div className="terrain__bar">
        <div className="terrain__years">
          <button
            type="button"
            className={year === "start" ? "is-on" : ""}
            onClick={() => setYear("start")}
          >
            {yearA}
          </button>
          <button
            type="button"
            className={year === "end" ? "is-on" : ""}
            onClick={() => setYear("end")}
          >
            {yearB}
          </button>
        </div>
        <div className="terrain__modes">
          <button
            type="button"
            className={mode === "forest" ? "is-on" : ""}
            onClick={() => setMode("forest")}
          >
            лес
          </button>
          <button
            type="button"
            className={mode === "relief" ? "is-on" : ""}
            onClick={() => setMode("relief")}
          >
            рельеф
          </button>
        </div>
        <button
          type="button"
          className={`terrain__play ${playing ? "is-on" : ""}`.trim()}
          onClick={() => {
            if (playing) {
              setPlaying(false);
              setFrame(null);
            } else {
              setFrame(0);
              setPlaying(true);
            }
          }}
        >
          {playing ? `■ ${frameYear ?? ""}` : "▶ по годам"}
        </button>
        <span className="terrain__hint">тяните мышью, чтобы повернуть</span>
      </div>
      )}

      <canvas
        ref={canvasRef}
        className="terrain__canvas"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        role="img"
        aria-label={`Объёмный рельеф запаса углерода, ${name}, ${
          year === "end" ? yearB : yearA
        } год`}
      />

      {compact ? null : (
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
      )}

      {compact ? null : (
      <p className="ov-note">
        {mode === "forest"
          ? "Одно дерево — один пиксель продукта, его высота и есть запас на этом пикселе. Деревья стоят через клетку: при трёх с половиной тысячах крон рисунок превращается в сплошной ковёр, где не видно ни просек, ни границы вырубки."
          : "Высота столбика — запас на пикселе. Столбики удобнее, когда высоты надо сравнить между собой, а не разглядывать лес."}{" "}
        Коричневый оттенок появляется только на виде {yearB} и означает пиксели, потерявшие
        запас за выбранный период.{" "}
        Значения взяты из тех же чисел, из которых считается изменение запаса, поэтому провал на
        картинке и вклад в результат — одно и то же место. Тень и наклон граней — оформление.
      </p>
      )}
    </div>
  );
}
