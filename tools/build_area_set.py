"""Набор из двенадцати участков: четыре из кейса плюс восемь добавленных.

Восемь добавленных закрывают то, чего в кейсе не было:

    RU_TVER_05       второй контрольный участок без нарушений
    RU_TVER_06       накопление запаса
    RU_VOLOGDA_07    сплошная вырубка с чёткой границей
    RU_VOLOGDA_08    повторная выборка мозаичных потерь
    RU_VOLOGDA_09    лесовосстановление и подрост
    RU_MORDOVIA_10   гарь с подтверждением MODIS
    RU_MORDOVIA_11   падающая историческая динамика, g < 0
    RU_MORDOVIA_12   восстановление после нарушения

Последние два пришли из KAN-62 вместе с вырезанными растрами и
картами. Геометрия взята оттуда, а базовая линия и площадь посчитаны
здешней цепочкой: в исходном виде площадь Мордовии-12 была занижена на
38 гектаров, потому что считалась по окну, округлённому до границ
пикселей, а не по доле пересечения пикселя с контуром.

Что делает скрипт. Собирает `areas.csv`, `areas.geojson` и
`methodology/baseline.csv` из исходного набора и выведенных данных,
сохраняя оригиналы рядом с суффиксом `.case`. Строки базовой линии для
четырёх участков кейса берутся из набора как есть — пересчитывать то,
что задано условием, нельзя, даже если наш расчёт даёт то же самое.

Запуск:
    python tools/build_area_set.py
    python tools/build_area_set.py --restore   # вернуть исходные четыре
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

DATA = Path("data")

KEEP_ADDED = [
    "RU_TVER_05",
    "RU_TVER_06",
    "RU_VOLOGDA_07",
    "RU_VOLOGDA_08",
    "RU_VOLOGDA_09",
    "RU_MORDOVIA_10",
    "RU_MORDOVIA_11",
    "RU_MORDOVIA_12",
]

FILES = [
    DATA / "areas.csv",
    DATA / "areas.geojson",
    DATA / "methodology" / "baseline.csv",
]


def backup() -> None:
    """Исходный набор сохраняется рядом: он основание расчёта, и потерять
    его, перезаписав своим, нельзя."""
    for path in FILES:
        keep = path.with_suffix(path.suffix + ".case")
        if path.exists() and not keep.exists():
            shutil.copy2(path, keep)
            print(f"сохранено {keep.name}")


def restore() -> None:
    for path in FILES:
        keep = path.with_suffix(path.suffix + ".case")
        if keep.exists():
            shutil.copy2(keep, path)
            print(f"восстановлено {path.name}")


def rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()

    if args.restore:
        restore()
        return

    backup()

    case_areas = rows(DATA / "areas.csv.case")
    case_ids = [a["aoi_id"] for a in case_areas]
    expanded = {a["aoi_id"]: a for a in rows(DATA / "areas.expanded.csv")}
    derived = rows(DATA / "baseline.derived.csv")

    missing = [a for a in KEEP_ADDED if a not in expanded]
    if missing:
        raise SystemExit(f"в расширенном наборе нет участков: {', '.join(missing)}")

    chosen = case_ids + KEEP_ADDED

    # --- areas.csv ---
    # Площадь добавленных участков берётся из расчёта по растрам, а не
    # из каталога: в каталоге она может быть посчитана по округлённому
    # окну и разойтись с тем, что потом считает сервис.
    measured = json.loads((DATA / "series.derived.json").read_text(encoding="utf-8"))
    out_areas = [a for a in case_areas]
    for aoi in KEEP_ADDED:
        row = dict(expanded[aoi])
        area = measured.get(aoi, {}).get("area_ha")
        if area is None:
            raise SystemExit(f"{aoi}: нет площади в series.derived.json — сначала build_area_from_tiles.py")
        row["area_ha"] = f"{area:.4f}"
        out_areas.append(row)
    with open(DATA / "areas.csv", "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(case_areas[0].keys()))
        writer.writeheader()
        for row in out_areas:
            writer.writerow({k: row.get(k, "") for k in case_areas[0].keys()})

    # --- areas.geojson ---
    case_geo = json.loads((DATA / "areas.geojson.case").read_text(encoding="utf-8-sig"))
    expanded_geo = json.loads((DATA / "areas.expanded.geojson").read_text(encoding="utf-8-sig"))
    by_id = {f["properties"]["aoi_id"]: f for f in expanded_geo["features"]}
    features = list(case_geo["features"])
    for aoi in KEEP_ADDED:
        feature = by_id.get(aoi)
        if feature is None:
            continue
        # Площадь в свойствах обязана совпадать с тем, что считает
        # сервис по этим же пикселям: иначе каталог и карта разойдутся,
        # и первым это заметит расчёт, а не человек.
        area = measured.get(aoi, {}).get("area_ha")
        if area is not None:
            feature = dict(feature)
            feature["properties"] = {**feature["properties"], "area_ha": round(area, 4)}
        features.append(feature)
    (DATA / "areas.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # --- baseline.csv ---
    # Для участков кейса строки берутся из набора без изменений: они
    # заданы условием, и наш пересчёт, даже совпадающий, их не заменяет.
    case_baseline = rows(DATA / "methodology" / "baseline.csv.case")
    fields = list(case_baseline[0].keys())
    out_baseline = list(case_baseline)
    for row in derived:
        if row["aoi_id"] in KEEP_ADDED:
            out_baseline.append({k: row.get(k, "") for k in fields})

    with open(DATA / "methodology" / "baseline.csv", "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out_baseline)

    covered = {r["aoi_id"] for r in out_baseline}
    gaps = [a for a in chosen if a not in covered]
    if gaps:
        raise SystemExit(f"без базовой линии остались: {', '.join(gaps)}")

    print(f"\nучастков: {len(out_areas)} ({len(case_ids)} из кейса + {len(KEEP_ADDED)} добавлено)")
    print(f"строк базовой линии: {len(out_baseline)}")
    print("\nдальше: python tools/extract_case_data.py --data data "
          "--out app/src/data/case-data.json --maps app/public/maps")


if __name__ == "__main__":
    main()
