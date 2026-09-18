"""Раздел 11 контракта, превью участка.

Реализован только "запасной вариант": контур полигона из GeoJSON на плоской
заливке, без спутниковой подложки — рендер RGB-композита требует доступа к
Earth Engine (зона Р3/Р4), сюда не входит. Работает офлайн и всё ещё
опознаёт форму участка (NFR-01) — по контракту это допустимая деградация,
"какой вариант использован — пишется в provenance.datasets".

Генерируется в момент расчёта и сохраняется на диск как
`data/previews/{calc_id}.png` — API отдаёт файл статикой, не по запросу.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 980, 400
PADDING_FRACTION = 0.10
BACKGROUND = (40, 54, 43)  # плоская заливка "лес без подложки"
OUTLINE = (255, 214, 90)
EVENT_FILL = (255, 90, 70)
TEXT_COLOR = (235, 235, 225)


def _polygon_rings(geometry: dict) -> list[list[tuple[float, float]]]:
    """Возвращает список внешних колец (Polygon → одно кольцо,
    MultiPolygon → по одному на часть) как [(lon, lat), ...]."""
    geom = geometry.get("geometry", geometry)  # принимает и Feature, и голую geometry
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Polygon":
        return [coords[0]]
    if gtype == "MultiPolygon":
        return [part[0] for part in coords]
    raise ValueError(f"unsupported geometry type for preview: {gtype}")


def _bbox(rings: list[list[tuple[float, float]]]) -> tuple[float, float, float, float]:
    lons = [pt[0] for ring in rings for pt in ring]
    lats = [pt[1] for ring in rings for pt in ring]
    return min(lons), min(lats), max(lons), max(lats)


def render_fallback_preview(
    geometry: dict,
    out_path: Path,
    *,
    calc_id: str,
    observation_date: str,
    event_points: list[tuple[float, float]] | None = None,
) -> None:
    rings = _polygon_rings(geometry)
    min_lon, min_lat, max_lon, max_lat = _bbox(rings)

    pad_x = (max_lon - min_lon) * PADDING_FRACTION or 0.01
    pad_y = (max_lat - min_lat) * PADDING_FRACTION or 0.01
    min_lon, max_lon = min_lon - pad_x, max_lon + pad_x
    min_lat, max_lat = min_lat - pad_y, max_lat + pad_y

    def to_px(lon: float, lat: float) -> tuple[float, float]:
        x = (lon - min_lon) / (max_lon - min_lon) * WIDTH
        # ось Y экрана растёт вниз, широта — вверх
        y = HEIGHT - (lat - min_lat) / (max_lat - min_lat) * HEIGHT
        return x, y

    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)

    for ring in rings:
        pixels = [to_px(lon, lat) for lon, lat in ring]
        # ImageDraw.polygon() не принимает width (только 1px outline) —
        # контур рисуем поверх замкнутой ломаной, чтобы задать толщину.
        draw.polygon(pixels, fill=None, outline=OUTLINE)
        draw.line(pixels + [pixels[0]], fill=OUTLINE, width=3)

    for lon, lat in event_points or []:
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            x, y = to_px(lon, lat)
            r = 5
            draw.ellipse([x - r, y - r, x + r, y + r], fill=EVENT_FILL)

    label = f"{calc_id} · снимок на {observation_date} · запасной вариант (контур, без подложки)"
    font = ImageFont.load_default()
    draw.text((12, HEIGHT - 20), label, fill=TEXT_COLOR, font=font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="PNG")
