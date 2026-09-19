"""Готовит примеры контуров для мастера «Задать контур».

Форма взята из старых проектных полигонов (api/data/polygons): это живые
контуры в пятнадцать вершин, а не прямоугольник. Но лежат они в
Красноярском крае, за полторы тысячи километров от покрытия наших
растров, и посчитать по ним нечего. Поэтому берётся только форма: она
нормализуется и вписывается внутрь участков, где данные есть.

Так пример и выглядит как настоящий лесной выдел, и действительно
считается — а не упирается в «данных на эту территорию нет».
"""

import csv
import json
from pathlib import Path

ROOT = Path(".")
SOURCES = {
    "RU_VOLOGDA_02": "proj-02",
    "RU_TVER_01": "proj-03",
    "RU_MORDOVIA_03": "proj-01",
}
TITLES = {
    "RU_VOLOGDA_02": "Выдел в Вологодской области",
    "RU_TVER_01": "Выдел на контрольном участке",
    "RU_MORDOVIA_03": "Выдел на горевшем участке",
}
NOTES = {
    "RU_VOLOGDA_02": "мозаика мелких потерь покрова",
    "RU_TVER_01": "нарушений не ожидается — видно, как метод ведёт себя на спокойном лесе",
    "RU_MORDOVIA_03": "внутри контура пожар 2021 года",
}

areas = {}
with open("data/areas.csv", encoding="utf-8-sig") as handle:
    for row in csv.DictReader(handle):
        areas[row["aoi_id"]] = row


def shape_of(name: str) -> list[list[float]]:
    data = json.loads(Path(f"api/data/polygons/{name}.geojson").read_text(encoding="utf-8"))
    return data["geometry"]["coordinates"][0]


def fit(ring: list[list[float]], box, inset: float = 0.18) -> list[list[float]]:
    """Вписывает форму внутрь рамки участка, оставляя поля.

    Поля нужны не для красоты: контур, прижатый к краю растра, обрезался
    бы по границе окна, и пример показывал бы не форму, а её остаток.
    """
    west, south, east, north = box
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    span_lon = max(lons) - min(lons)
    span_lat = max(lats) - min(lats)

    pad_lon = (east - west) * inset
    pad_lat = (north - south) * inset
    target_w = (east - west) - 2 * pad_lon
    target_h = (north - south) - 2 * pad_lat

    out = []
    for lon, lat in ring:
        u = (lon - min(lons)) / span_lon
        v = (lat - min(lats)) / span_lat
        out.append([
            round(west + pad_lon + u * target_w, 6),
            round(south + pad_lat + v * target_h, 6),
        ])
    # Кольцо должно замыкаться той же точкой, а не почти той же.
    out[-1] = list(out[0])
    return out


entries = [{
    "id": "primer-1",
    "title": "Пример с положительным потенциалом — Вологодская область",
    "note": "Контрольный пример для проверки расчётного контура. На периоде 2019–2024 проходит фильтры текущей методики.",
    "parent": "Вологодская область",
    "period": [2019, 2024],
    "geometry": json.loads(Path("examples/primer-1-edinic-29438.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"],
}]
for aoi, source in SOURCES.items():
    meta = areas[aoi]
    box = (
        float(meta["bbox_west"]),
        float(meta["bbox_south"]),
        float(meta["bbox_east"]),
        float(meta["bbox_north"]),
    )
    ring = fit(shape_of(source), box)
    entries.append(
        {
            "id": aoi.lower().replace("ru_", ""),
            "title": TITLES[aoi],
            "note": NOTES[aoi],
            "parent": meta["name"],
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        }
    )

lines = [
    "/* Примеры контуров для мастера «Задать контур».",
    "",
    "   Первый — контрольный primer-1 из examples, период 2019–2024.",
    "   Форма остальных взята из старых проектных полигонов: это контуры в",
    "   пятнадцать вершин, а не прямоугольник, которым проще всего обойтись.",
    "   Лежали они, однако, в Красноярском крае — за полторы тысячи",
    "   километров от покрытия наших растров, — поэтому перенесена только",
    "   форма: она вписана внутрь участков, где данные есть.",
    "",
    "   Иначе пример упирался бы в «данных на эту территорию нет» и",
    "   показывал бы не работу сервиса, а границы набора.",
    "",
    "   Пересобрать: python tools/make_sample_contours.py */",
    "",
    "export type SampleContour = {",
    "  id: string;",
    "  title: string;",
    "  note: string;",
    "  parent: string;",
    "  period?: [number, number];",
    "  geometry: { type: \"Polygon\"; coordinates: number[][][] };",
    "};",
    "",
    "export const SAMPLE_CONTOURS: SampleContour[] = [",
]

for entry in entries:
    ring = entry["geometry"]["coordinates"][0]
    lines.append("  {")
    lines.append(f'    id: "{entry["id"]}",')
    lines.append(f'    title: "{entry["title"]}",')
    lines.append(f'    note: "{entry["note"]}",')
    lines.append(f'    parent: "{entry["parent"]}",')
    if "period" in entry:
        lines.append(f'    period: {entry["period"]},')
    lines.append('    geometry: {')
    lines.append('      type: "Polygon",')
    lines.append("      coordinates: [")
    lines.append("        [")
    for lon, lat in ring:
        lines.append(f"          [{lon}, {lat}],")
    lines.append("        ],")
    lines.append("      ],")
    lines.append("    },")
    lines.append("  },")

lines.append("];")
lines.append("")

Path("app/src/data/sampleContours.ts").write_text("\n".join(lines), encoding="utf-8")
print(f"записано app/src/data/sampleContours.ts: {len(entries)} контура")
for entry in entries:
    ring = entry["geometry"]["coordinates"][0]
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    print(f"  {entry['title']}: {min(lons):.4f}..{max(lons):.4f} x {min(lats):.4f}..{max(lats):.4f}")
