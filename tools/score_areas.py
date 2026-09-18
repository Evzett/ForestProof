"""Оценка участков обученной моделью — без переобучения.

Зачем отдельный инструмент. `train_stability.py` делает две разные
вещи сразу: подбирает модель и прогоняет её по участкам. Пока участки
не менялись, разницы не было. Но как только в набор добавляются новые
контуры, запуск того же скрипта означает «подбери модель заново», и
это ровно то, чего делать нельзя: модель, которая меняется под каждый
загруженный участок, ничего не проверяет.

Здесь модель только применяется. Веса, стандартизация и порог берутся
из файла как есть и не пересчитываются ни при каких условиях. Если
обучающая выборка изменилась, это видно по отпечатку — скрипт скажет,
но подбирать заново не станет.

Запуск:
    python tools/score_areas.py
    python tools/score_areas.py --areas data/areas.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

import build_training_set as builder
from train_stability import FEATURES, sigmoid, tile_for

MODEL_PATH = Path("app/src/data/stability-model.json")
FORECAST_FEATURE_END = 24  # окно признаков кончается 2024 годом
FORECAST_HORIZON = (2025, 2029)


def fingerprint(path: Path) -> str | None:
    """Отпечаток обучающей выборки.

    Нужен, чтобы заметить подмену: если выборка изменилась, а модель
    осталась прежней, числа на экране относятся к другой выборке, чем
    подписано под ними.
    """
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def category(probability: float) -> str:
    return "high" if probability >= 0.65 else "medium" if probability >= 0.35 else "low"


def score_one(model: dict, row: dict) -> float:
    """Вероятность по обученным весам. Ничего не подбирается."""
    mean = np.array(model["standardisation"]["mean"])
    scale = np.array(model["standardisation"]["scale"])
    weights = np.array([model["weights"][k] for k in FEATURES])
    bias = float(model["bias"])
    vector = np.array([float(row[k]) for k in FEATURES])
    return float(sigmoid(((vector - mean) / scale) @ weights + bias))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--areas", type=Path, default=Path("data/areas.csv"))
    parser.add_argument("--hansen", type=Path, default=Path("data/cache/hansen-gfc"))
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    parser.add_argument("--training-set", type=Path, default=Path("data/training_set.csv"))
    args = parser.parse_args()

    if not args.model.exists():
        raise SystemExit(
            f"нет файла модели {args.model}\n"
            "модель обучается отдельно: python tools/train_stability.py"
        )
    model = json.loads(args.model.read_text(encoding="utf-8"))

    stored = model.get("training_fingerprint")
    current = fingerprint(args.training_set)
    if stored and current and stored != current:
        print(
            f"ВНИМАНИЕ: обучающая выборка изменилась ({stored} -> {current}).\n"
            "Модель не переобучается — она применяется как есть. Если выборку\n"
            "меняли намеренно, запустите обучение отдельно и осознанно.\n"
        )

    predictions = []
    with open(args.areas, encoding="utf-8-sig") as handle:
        for meta in csv.DictReader(handle):
            aoi = meta["aoi_id"]
            box = (
                float(meta["bbox_west"]),
                float(meta["bbox_south"]),
                float(meta["bbox_east"]),
                float(meta["bbox_north"]),
            )
            tile = tile_for(box)
            loss_path = args.hansen / f"Hansen_GFC-2024-v1.12_lossyear_{tile}.tif"
            cover_path = args.hansen / f"Hansen_GFC-2024-v1.12_treecover2000_{tile}.tif"

            if not loss_path.exists() or not cover_path.exists():
                predictions.append(
                    {"aoi_id": aoi, "available": False, "reason": f"тайл Hansen {tile} не скачан"}
                )
                print(f"  {aoi:<18} тайл {tile} не скачан")
                continue

            try:
                row = builder.sample_plot(loss_path, cover_path, box)
                ahead = builder.sample_plot(
                    loss_path,
                    cover_path,
                    box,
                    feature_end=FORECAST_FEATURE_END,
                    label_years=range(25, 25),
                )
            except (ValueError, IndexError, FileNotFoundError) as error:
                predictions.append(
                    {"aoi_id": aoi, "available": False,
                     "reason": f"растр не читается: {type(error).__name__}"}
                )
                print(f"  {aoi:<18} растр не читается")
                continue

            if row is None:
                predictions.append(
                    {"aoi_id": aoi, "available": False,
                     "reason": (
                         f"участок не проходит порог леса: сомкнутость крон ниже "
                         f"{builder.MIN_TREECOVER_PCT} % более чем на "
                         f"{round((1 - builder.MIN_FOREST_SHARE) * 100)} % площади"
                     )}
                )
                print(f"  {aoi:<18} не проходит порог леса")
                continue

            probability = score_one(model, row)
            forecast = None
            if ahead is not None:
                ahead_p = score_one(model, ahead)
                forecast = {
                    "probability": ahead_p,
                    "category": category(ahead_p),
                    "feature_window": ahead["feature_window"],
                    "horizon": list(FORECAST_HORIZON),
                    "recent_loss_pct": ahead["recent_loss_2017_2019_pct"],
                }

            predictions.append(
                {
                    "aoi_id": aoi,
                    "available": True,
                    "probability": probability,
                    "category": category(probability),
                    "label": row["label"],
                    "future_loss_pct": row["future_loss_2020_2024_pct"],
                    "forecast": forecast,
                }
            )
            ahead_text = (
                f"прогноз p={forecast['probability']:.3f} {forecast['category']}"
                if forecast
                else "прогноз недоступен"
            )
            print(f"  {aoi:<18} проверка p={probability:.3f} {category(probability):<7} {ahead_text}")

    # Перезаписываются только предсказания. Всё, что описывает саму
    # модель — веса, качество, выборка — остаётся нетронутым.
    model["predictions"] = predictions
    args.model.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")

    scored = sum(1 for p in predictions if p.get("available"))
    print(f"\nоценено {scored} из {len(predictions)}; модель не переобучалась")
    print(f"ROC-AUC на отложенной остался {model['quality']['roc_auc_test']:.3f}")


if __name__ == "__main__":
    main()
