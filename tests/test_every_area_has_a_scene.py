"""У каждого участка есть снимок — иначе карточка молчит о месте.

Снимки приходят двумя путями: четыре участка кейса несут их в наборе,
остальным собирает tools/scene_previews.py. Шаг легко забыть, добавляя
участок, и тогда на карточке вместо леса окажется карта изменений — а
заметят это уже на защите.

Тест сверяет каталог участков с тем, что попало в данные приложения, и
проверяет, что картинки действительно лежат на диске.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MAPS = ROOT / "app/public/maps"
CASE = json.loads((ROOT / "app/src/data/case-data.json").read_text(encoding="utf-8"))


def _scene_of(area: dict) -> dict | None:
    """Снимок участка: вложенный в набор либо собранный нами."""
    usable = [
        o
        for o in ((area.get("sentinel") or {}).get("observations") or [])
        if o.get("usable") and o.get("image")
    ]
    if usable:
        return max(usable, key=lambda o: o["date"])
    return area.get("scene_preview")


def test_every_area_in_the_catalog_reached_the_app() -> None:
    with (DATA / "areas.csv").open(encoding="utf-8-sig") as handle:
        catalog = {row["aoi_id"] for row in csv.DictReader(handle)}
    assert {a["aoi_id"] for a in CASE["areas"]} == catalog


def test_every_area_has_a_scene() -> None:
    without = [a["aoi_id"] for a in CASE["areas"] if _scene_of(a) is None]
    assert not without, (
        "у этих участков нет снимка: "
        + ", ".join(without)
        + ". Соберите: python tools/scene_previews.py, затем пересоберите данные."
    )


def test_scene_files_exist() -> None:
    missing = []
    for area in CASE["areas"]:
        scene = _scene_of(area)
        if scene and not (MAPS / scene["image"]).exists():
            missing.append(f"{area['aoi_id']} → {scene['image']}")
    assert not missing, "снимок записан в данные, но файла нет: " + ", ".join(missing)


def test_previews_are_not_claimed_as_part_of_the_case_set() -> None:
    """Собранное нами не выдаётся за данные набора.

    У участков кейса снимки пришли вместе с данными, у остальных их
    нашли и нарисовали мы. Разница существенная, и в данных она должна
    быть видна: превью лежит в отдельном поле со своей подписью.
    """
    for area in CASE["areas"]:
        preview = area.get("scene_preview")
        if preview is None:
            continue
        assert "scene_id" in preview and preview["date"]
        assert "окно" in preview["source"] or "контур" in preview["source"]
        # Если у участка есть вложенные наблюдения, превью не нужно и
        # быть его не должно: два источника на одну карточку — повод
        # однажды показать не тот снимок.
        observations = (area.get("sentinel") or {}).get("observations") or []
        assert not [o for o in observations if o.get("usable")], (
            f"{area['aoi_id']}: снимок есть и в наборе, и в превью"
        )
