"""Признаки устойчивости результата и разметка — KAN-68.

Шесть признаков на участок, все — по тем же растрам, что и основной
расчёт. Это принципиально: модель не приносит нового источника данных
и поэтому не добавляет нового способа ошибиться.

Признаки считаются по списку участков, а не по четырём захардкоженным:
на четырёх строках обучать нечего, и таблица имеет смысл только когда
участков станет двенадцать или двадцать.

Рядом с каждым числом записано, из какого растра и за какие годы оно
получено, — иначе признак нельзя ни проверить, ни воспроизвести.

Запуск:
    python tools/stability_features.py --data data --out data/stability_features.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path

# Порог, выше которого потеря покрова за год считается заметной, доля площади.
# Ниже него годовые потери Hansen — это единичные пиксели на краях выделов.
LOSS_YEAR_THRESHOLD = 0.001

# Порог положительного класса разметки: потеря выше 5 % площади за период
# либо подтверждённое событие.
LABEL_LOSS_SHARE = 5.0


@dataclass(frozen=True)
class Feature:
    """Признак вместе с его происхождением.

    Происхождение — не украшение: без него число нельзя перепроверить,
    а значит нельзя и оспорить.
    """

    key: str
    label: str
    value: float
    source: str
    years: str
    unit: str = ""


def compute_features(area: dict, events: list[dict]) -> list[Feature]:
    """Шесть признаков по одному участку.

    На вход идёт объект участка из case-data.json — то есть ровно то,
    что посчитал основной расчёт, без повторного чтения растров.
    """
    aoi = area["aoi_id"]
    area_ha = area["area_ha"]
    series = area["series"]
    cover_loss = area["cover_loss"]

    loss_total = sum(row["area_ha"] for row in cover_loss)
    loss_years = [
        row for row in cover_loss if row["area_ha"] / area_ha > LOSS_YEAR_THRESHOLD
    ]

    # Волатильность ряда: стандартное отклонение годовых приростов запаса,
    # нормированное на средний запас. Абсолютное σ несравнимо между
    # участками с запасом 13 и 85 т C/га.
    stocks = [row["c_t_ha"] for row in series]
    steps = [b - a for a, b in zip(stocks, stocks[1:])]
    mean_stock = sum(stocks) / len(stocks) if stocks else 0.0
    if steps and mean_stock:
        mean_step = sum(steps) / len(steps)
        spread = (sum((x - mean_step) ** 2 for x in steps) / len(steps)) ** 0.5
        volatility = spread / mean_stock
    else:
        volatility = 0.0

    last = series[-1] if series else {"agb_t_ha": 0.0, "agb_sd_t_ha": 0.0}
    sd_ratio = last["agb_sd_t_ha"] / last["agb_t_ha"] if last["agb_t_ha"] else 0.0

    fire = next((e for e in events if e["aoi_id"] == aoi), None)
    fire_share = (
        fire["burned_pixels"] / fire["all_pixels"] if fire and fire["all_pixels"] else 0.0
    )

    first_year = series[0]["year"] if series else 0
    last_year = series[-1]["year"] if series else 0

    return [
        Feature(
            "loss_share_pct",
            "доля площади, потерявшей покров",
            loss_total / area_ha * 100,
            "Hansen GFC v1.13, канал lossyear",
            "2001—2024",
            "%",
        ),
        Feature(
            "loss_years",
            "число лет с заметной потерей",
            float(len(loss_years)),
            f"Hansen GFC v1.13, порог {LOSS_YEAR_THRESHOLD * 100:g} % площади за год",
            "2001—2024",
            "лет",
        ),
        Feature(
            "fire_share",
            "доля пикселей с признаком горения",
            fire_share,
            "MODIS MCD64A1 061, поле burned_pixel_centers_in_aoi",
            fire["date_min"][:4] if fire else "события нет",
        ),
        Feature(
            "volatility_rel",
            "волатильность годового ряда запаса",
            volatility,
            "ESA CCI Biomass v7.0, σ приростов к среднему запасу",
            f"{first_year}—{last_year}",
        ),
        Feature(
            "sd_to_stock",
            "отношение погрешности продукта к запасу",
            sd_ratio,
            "ESA CCI Biomass v7.0, канал AGB_SD",
            str(last_year),
        ),
        Feature(
            "baseline_decline",
            "падение исторической динамики",
            max(0.0, -area["baseline_rate_tc_ha_year"]),
            "базовая линия HIST-AGB-2015-2019-v1, коэффициент g",
            "2015—2019",
            "т C/га/год",
        ),
    ]


def label_area(area: dict, events: list[dict]) -> dict:
    """Разметка: было ли на участке существенное нарушение за 2019—2024.

    Положительный класс — подтверждённое событие ЛИБО потеря покрова
    больше 5 % площади за период. Два условия, а не одно: подтверждение
    есть не у всех нарушений, а потеря покрова бывает и без пожара.
    """
    aoi = area["aoi_id"]
    area_ha = area["area_ha"]
    period_loss = sum(
        row["area_ha"] for row in area["cover_loss"] if 2019 < row["year"] <= 2024
    )
    loss_share = period_loss / area_ha * 100
    has_event = any(e["aoi_id"] == aoi for e in events)

    return {
        "label": int(has_event or loss_share > LABEL_LOSS_SHARE),
        "loss_share_2020_2024_pct": loss_share,
        "has_confirmed_event": has_event,
        "rule": (
            f"подтверждённое событие либо потеря покрова больше {LABEL_LOSS_SHARE:g} % "
            "площади за 2019—2024"
        ),
    }


def build_table(case_data: dict) -> list[dict]:
    """Таблица «участок × признак» по всем участкам набора."""
    events = case_data.get("events", [])
    rows = []
    for area in case_data["areas"]:
        features = compute_features(area, events)
        marking = label_area(area, events)
        row = {
            "aoi_id": area["aoi_id"],
            "name": area["name"],
            "region": area["region"],
            "role": area["role"],
            "area_ha": round(area["area_ha"], 2),
            **{f.key: round(f.value, 6) for f in features},
            **marking,
        }
        rows.append(row)
    return rows


def provenance(case_data: dict) -> list[dict]:
    """Происхождение каждого признака — один раз, а не в каждой строке."""
    events = case_data.get("events", [])
    sample = case_data["areas"][0]
    return [
        {
            "key": f.key,
            "label": f.label,
            "unit": f.unit,
            "source": f.source,
            "years": f.years,
        }
        for f in compute_features(sample, events)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-data",
        type=Path,
        default=Path("app/src/data/case-data.json"),
        help="результат tools/extract_case_data.py",
    )
    parser.add_argument("--out", type=Path, default=Path("data/stability_features.csv"))
    args = parser.parse_args()

    case_data = json.loads(args.case_data.read_text(encoding="utf-8"))
    rows = build_table(case_data)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    meta_path = args.out.with_suffix(".provenance.json")
    meta_path.write_text(
        json.dumps(provenance(case_data), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"{args.out}: {len(rows)} строк, {len(rows[0]) } колонок")
    print(f"{meta_path}: происхождение {len(provenance(case_data))} признаков")
    positives = sum(r["label"] for r in rows)
    print(f"положительный класс: {positives} из {len(rows)}")
    for row in rows:
        print(
            f"  {row['aoi_id']:<16} label={row['label']}  "
            f"потери за период {row['loss_share_2020_2024_pct']:.2f} %  "
            f"событие {'есть' if row['has_confirmed_event'] else 'нет'}  "
            f"({row['role']})"
        )


if __name__ == "__main__":
    main()
