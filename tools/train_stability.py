"""Обучение модели устойчивости на настоящей выборке — KAN-54.

Отличие от stability_model.py: там четыре строки и проверить нечего,
здесь сотни участков и нормальный протокол.

Что делается:
  1. выборка делится на обучение и отложенную проверку — стратифицированно,
     чтобы доли классов совпали;
  2. стандартизация считается ТОЛЬКО по обучающей части, иначе отложенная
     подсматривает через среднее и разброс;
  3. логистическая регрессия с L2, подбор силы регуляризации по скользящему
     контролю внутри обучающей части;
  4. качество меряется ROC-AUC на отложенной, а не точностью: при
     несбалансированных классах точность показывает долю большего класса
     и ничего больше;
  5. базовый уровень — предсказание по одному лучшему признаку. Если
     модель его не бьёт, модель не нужна.

Запуск:
    python tools/train_stability.py --data data/training_set.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

FEATURES = [
    "loss_share_2001_2019_pct",
    "loss_years_2001_2019",
    "recent_loss_2017_2019_pct",
    "peak_year_loss_pct",
    "mean_treecover_pct",
    "forest_share",
]


def tile_for(box: tuple[float, float, float, float]) -> str:
    """Имя тайла Hansen по участку: сетка 10°×10°, широта по верхнему краю."""
    lon = (box[0] + box[2]) / 2
    lat = (box[1] + box[3]) / 2
    lon_left = int(math.floor(lon / 10) * 10)
    lat_top = int(math.ceil(lat / 10) * 10)
    lon_str = f"{abs(lon_left):03d}{'E' if lon_left >= 0 else 'W'}"
    lat_str = f"{abs(lat_top):02d}{'N' if lat_top >= 0 else 'S'}"
    return f"{lat_str}_{lon_str}"


TEST_SHARE = 0.30
FOLDS = 5
L2_GRID = [0.01, 0.1, 1.0, 10.0]
STEPS = 3000
LEARNING_RATE = 0.2


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def fit(x: np.ndarray, y: np.ndarray, l2: float) -> tuple[np.ndarray, float]:
    n, m = x.shape
    weights = np.zeros(m)
    bias = 0.0
    for _ in range(STEPS):
        error = sigmoid(x @ weights + bias) - y
        weights -= LEARNING_RATE * (x.T @ error / n + l2 * weights / n)
        bias -= LEARNING_RATE * float(error.mean())
    return weights, bias


def roc_auc(y: np.ndarray, score: np.ndarray) -> float:
    """Площадь под ROC через ранги — то же, что доля правильно
    упорядоченных пар «положительный выше отрицательного»."""
    positives = int(y.sum())
    negatives = int(len(y) - positives)
    if positives == 0 or negatives == 0:
        return float("nan")
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty(len(score), dtype=float)
    ranks[order] = np.arange(1, len(score) + 1)
    # средний ранг для совпадающих значений, иначе AUC зависит от порядка строк
    for value in np.unique(score):
        mask = score == value
        if mask.sum() > 1:
            ranks[mask] = ranks[mask].mean()
    return float((ranks[y == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def stratified_split(y: np.ndarray, share: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Деление с сохранением долей классов.

    Случайное деление при редком классе легко оставляет отложенную
    выборку без положительных примеров — и AUC на ней не считается.
    """
    rng = np.random.default_rng(seed)
    test_idx: list[int] = []
    for label in (0, 1):
        idx = np.where(y == label)[0]
        rng.shuffle(idx)
        take = max(1, int(round(len(idx) * share)))
        test_idx.extend(idx[:take].tolist())
    test = np.array(sorted(test_idx))
    train = np.array([i for i in range(len(y)) if i not in set(test_idx)])
    return train, test


def cross_validated_l2(x: np.ndarray, y: np.ndarray, seed: int) -> float:
    """Сила регуляризации подбирается внутри обучающей части."""
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(y))
    folds = np.array_split(order, FOLDS)
    best, best_auc = L2_GRID[0], -1.0

    for l2 in L2_GRID:
        scores = []
        for k in range(FOLDS):
            valid = folds[k]
            train = np.concatenate([folds[j] for j in range(FOLDS) if j != k])
            if len(set(y[train].tolist())) < 2 or len(set(y[valid].tolist())) < 2:
                continue
            mean, scale = x[train].mean(axis=0), x[train].std(axis=0)
            scale[scale == 0] = 1.0
            weights, bias = fit((x[train] - mean) / scale, y[train], l2)
            probability = sigmoid(((x[valid] - mean) / scale) @ weights + bias)
            scores.append(roc_auc(y[valid], probability))
        if scores:
            mean_auc = float(np.nanmean(scores))
            if mean_auc > best_auc:
                best, best_auc = l2, mean_auc
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/training_set.csv"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path("app/src/data/stability-model.json"))
    parser.add_argument("--score-areas", type=Path, default=Path("data/areas.csv"))
    parser.add_argument("--hansen", type=Path, default=Path("data/cache/hansen-gfc"))
    args = parser.parse_args()

    with open(args.data, encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    x = np.array([[float(r[k]) for k in FEATURES] for r in rows])
    y = np.array([int(r["label"]) for r in rows])

    positives = int(y.sum())
    minority = min(positives, len(y) - positives)
    print(f"выборка: {len(y)} участков, положительных {positives}, меньший класс {minority}")
    if minority < 2:
        raise SystemExit("меньший класс меньше двух наблюдений — делить нечего")

    train, test = stratified_split(y, TEST_SHARE, args.seed)
    print(f"обучение {len(train)}, отложенная {len(test)} (положительных {int(y[test].sum())})")

    l2 = cross_validated_l2(x[train], y[train], args.seed)
    print(f"сила регуляризации по скользящему контролю: L2 = {l2}")

    mean, scale = x[train].mean(axis=0), x[train].std(axis=0)
    scale[scale == 0] = 1.0
    weights, bias = fit((x[train] - mean) / scale, y[train], l2)

    train_auc = roc_auc(y[train], sigmoid(((x[train] - mean) / scale) @ weights + bias))
    test_score = sigmoid(((x[test] - mean) / scale) @ weights + bias)
    test_auc = roc_auc(y[test], test_score)

    # Базовый уровень: лучший одиночный признак на той же отложенной части.
    baselines = {}
    for i, key in enumerate(FEATURES):
        baselines[key] = roc_auc(y[test], x[test, i])
    best_key = max(baselines, key=lambda k: abs(baselines[k] - 0.5))
    best_single = baselines[best_key]

    print()
    print(f"ROC-AUC на обучении:   {train_auc:.3f}")
    print(f"ROC-AUC на отложенной: {test_auc:.3f}")
    print(f"лучший одиночный признак: {best_key} = {best_single:.3f}")
    beats = test_auc > max(best_single, 1 - best_single) + 0.02
    print(f"модель бьёт одиночный признак: {'да' if beats else 'нет'}")

    print()
    print("вклад признаков:")
    for key, weight in sorted(zip(FEATURES, weights), key=lambda p: abs(p[1]), reverse=True):
        print(f"  {key:<28} {weight:+.4f}")

    single_auc = max(best_single, 1 - best_single)
    if np.isnan(test_auc):
        verdict = "На отложенной выборке не оказалось обоих классов — оценка невозможна."
        status = "не проверена"
    elif test_auc < 0.65:
        verdict = (
            f"ROC-AUC на отложенной {test_auc:.3f} — разделения практически нет. "
            "По истории потерь будущие потери не предсказываются, и это содержательный "
            "результат, а не недоработка модели."
        )
        status = "разделения нет"
    elif beats:
        verdict = (
            f"Модель обучена на {len(train)} участках и проверена на {len(test)} отложенных: "
            f"ROC-AUC {test_auc:.3f} против {single_auc:.3f} у лучшего одиночного признака. "
            "Совместная модель даёт больше, чем любой признак по отдельности. Признаки "
            "считаются строго до 2019 года, метка — за 2020–2024, утечки между ними нет."
        )
        status = "обучена и проверена на отложенной выборке"
    else:
        verdict = (
            f"Разделение сильное: ROC-AUC на отложенной {test_auc:.3f} при {len(test)} "
            f"участках. Но почти всё оно даётся одним признаком — «{best_key}» в одиночку "
            f"даёт {single_auc:.3f}. Совместная модель добавляет {test_auc - single_auc:+.3f}, "
            "то есть ничего. Вывод: недавнее нарушение предсказывает будущее нарушение, "
            "и для этого модель не нужна — достаточно одного правила. В продукт идут "
            "пороговые правила, модель остаётся как проверка этого вывода."
        )
        status = "обучена; разделение сильное, но сводится к одному признаку"

    print()
    print(verdict)

    # Прогоняем обученную модель по участкам кейса теми же признаками,
    # что и обучающую выборку: иначе показывать на экране нечего,
    # а сравнивать признаки разных определений — значит обманывать себя.
    predictions = []
    try:
        import build_training_set as builder

        with open(args.score_areas, encoding="utf-8-sig") as handle:
            for meta in csv.DictReader(handle):
                box = (
                    float(meta["bbox_west"]),
                    float(meta["bbox_south"]),
                    float(meta["bbox_east"]),
                    float(meta["bbox_north"]),
                )
                # Тайл выбирается по самому участку. Раньше он был вписан
                # в код, и три участка из четырёх оставались без оценки
                # просто потому, что лежали восточнее 40°.
                tile = tile_for(box)
                loss_path = args.hansen / f"Hansen_GFC-2024-v1.12_lossyear_{tile}.tif"
                cover_path = args.hansen / f"Hansen_GFC-2024-v1.12_treecover2000_{tile}.tif"
                try:
                    row = builder.sample_plot(loss_path, cover_path, box)
                except (ValueError, IndexError, FileNotFoundError):
                    row = None
                if row is None:
                    # Тайл не скачан или участок не лесной — штатный случай,
                    # и молча ставить ему категорию нельзя.
                    predictions.append(
                        {"aoi_id": meta["aoi_id"], "available": False,
                         "reason": f"нет данных Hansen по тайлу {tile} либо участок не лесной"}
                    )
                    continue
                vector = np.array([[float(row[k]) for k in FEATURES]])
                probability = float(sigmoid(((vector - mean) / scale) @ weights + bias)[0])
                predictions.append(
                    {
                        "aoi_id": meta["aoi_id"],
                        "available": True,
                        "probability": probability,
                        "category": "high" if probability >= 0.65 else "medium" if probability >= 0.35 else "low",
                        "label": row["label"],
                        "future_loss_pct": row["future_loss_2020_2024_pct"],
                    }
                )
    except FileNotFoundError:
        pass

    if predictions:
        print()
        print("участки кейса по обученной модели:")
        for p in predictions:
            if p.get("available"):
                print(f"  {p['aoi_id']:<16} p={p['probability']:.3f} {p['category']:<7} факт={p['label']}")
            else:
                print(f"  {p['aoi_id']:<16} {p['reason']}")

    payload = {
        "predictions": predictions,
        "method": "логистическая регрессия с L2, подбор регуляризации по скользящему контролю",
        "features": FEATURES,
        "l2": l2,
        "standardisation": {"mean": mean.tolist(), "scale": scale.tolist()},
        "weights": dict(zip(FEATURES, weights.tolist())),
        "bias": float(bias),
        "thresholds": {"medium": 0.35, "high": 0.65},
        "sample": {
            "size": int(len(y)),
            "positives": positives,
            "minority_class": minority,
            "train": int(len(train)),
            "test": int(len(test)),
            "required_minority": len(FEATURES) * 10,
            "sufficient": bool(minority >= len(FEATURES) * 10),
        },
        "quality": {
            "roc_auc_train": train_auc,
            "roc_auc_test": test_auc,
            "best_single_feature": best_key,
            "best_single_auc": best_single,
            "beats_single_feature": bool(beats),
        },
        "design": {
            "feature_window": "2001–2019",
            "label_window": "2020–2024",
            "leakage": "исключена разделением периодов",
            "label_rule": "потеря покрова за 2020–2024 больше 1 % площади",
        },
        "verdict": verdict,
        "status": status,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nзаписано {args.out}")


if __name__ == "__main__":
    main()
