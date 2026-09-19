from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_positive_sample_resets_period_and_is_first():
    import json
    import re

    samples = (ROOT / "app/src/data/sampleContours.ts").read_text(encoding="utf-8")
    first = samples.split("export const SAMPLE_CONTOURS")[1].split('id: "vologda_02"')[0]
    assert 'id: "primer-1"' in first
    assert "period: [2019, 2024]" in first
    fixture = json.loads((ROOT / "examples/primer-1-edinic-29438.geojson").read_text(encoding="utf-8"))
    points = [[float(x), float(y)] for x, y in re.findall(r"\[([\d.]+), ([\d.]+)\]", first) if "." in x]
    assert points == fixture["features"][0]["geometry"]["coordinates"][0]
    wizard = (ROOT / "app/src/components/Wizard.tsx").read_text(encoding="utf-8")
    apply = wizard.split("const applySample =")[1].split("\n  };")[0]
    assert "setYearStart(sample.period[0])" in apply
    assert "setYearEnd(sample.period[1])" in apply
    assert "useState(2019)" in wizard and "useState(2024)" in wizard


def test_wizard_sends_selected_period_not_hardcoded_period() -> None:
    source = (ROOT / "app/src/components/Wizard.tsx").read_text(encoding="utf-8")
    assert "year_start: yearStart" in source
    assert "year_end: yearEnd" in source
    assert "year_start: 2019, year_end: 2024" not in source


def test_drawn_geometry_is_real_geography() -> None:
    """Обводка даёт полигон в градусах, а не в координатах полотна.

    Проверка изменилась вместе с реализацией. Раньше обводка рисовалась
    поверх картинки, и координаты экрана пересчитывались в градусы по
    рамке этой картинки — отсюда `west + point.x / 100`. Теперь под
    обводкой настоящая карта: клик приходит с долготой и широтой, и
    пересчитывать нечего. Проверяем то, что важно на самом деле, —
    что точки обводки доходят до запроса тем же путём, что координаты
    из файла, а не теряются по дороге.
    """
    wizard = (ROOT / "app/src/components/Wizard.tsx").read_text(encoding="utf-8")
    assert 'method === "draw" && points.length >= 3' in wizard
    assert "polygonFromPoints(points)" in wizard

    drawmap = (ROOT / "app/src/components/DrawMap.tsx").read_text(encoding="utf-8")
    # Вершина берётся из события карты, а не из координат курсора.
    assert "event.lngLat" in drawmap
