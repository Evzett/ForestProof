from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
