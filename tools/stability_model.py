"""Модель устойчивости результата на 2024—2029 — KAN-54.

Логистическая регрессия с L2 на шести признаках из stability_features.py.
Без sklearn: тридцать строк на numpy читаются и проверяются, а лишняя
зависимость в требованиях — нет.

Главное, что надо понимать про эту модель и что она сама про себя пишет:

    На четырёх участках обучать нечего. Три положительных примера против
    одного отрицательного разделяются ЛЮБЫМ из шести признаков по
    отдельности, поэтому идеальная точность на обучении здесь ничего
    не доказывает, а скользящий контроль на четырёх точках не является
    проверкой. Коэффициенты — это компромисс регуляризации, а не оценки.

Поэтому в продукт по умолчанию идёт не она, а пороговые правила
(stability_screening в extract_case_data.py): у них каждый порог виден
и оспорим. Модель считается рядом и показывается как второе мнение —
с этой же оговоркой на экране.

Что модель всё-таки даёт полезного: ранжирование признаков по вкладу
и оценку того, сколько участков нужно, чтобы выборка начала что-то
значить.

Запуск:
    python tools/stability_model.py --features data/stability_features.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

FEATURE_KEYS = [
    "loss_share_pct",
    "loss_years",
    "fire_share",
    "volatility_rel",
    "sd_to_stock",
    "baseline_decline",
]

# Сильная регуляризация не случайна: при полной разделимости выборки
# коэффициенты без неё уходят в бесконечность, и «обученная модель»
# оказывается просто указателем на первый попавшийся признак.
L2 = 1.0
STEPS = 4000
LEARNING_RATE = 0.1

# Границы категорий по вероятности положительного класса
THRESHOLD_MEDIUM = 0.35
THRESHOLD_HIGH = 0.65


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def fit(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    """Логистическая регрессия с L2, полный градиентный спуск.

    Смещение не штрафуется: штраф на него смещал бы базовую частоту
    класса, а не форму разделяющей поверхности.
    """
    n, m = x.shape
    weights = np.zeros(m)
    bias = 0.0
    for _ in range(STEPS):
        p = sigmoid(x @ weights + bias)
        error = p - y
        grad_w = x.T @ error / n + L2 * weights / n
        grad_b = float(error.mean())
        weights -= LEARNING_RATE * grad_w
        bias -= LEARNING_RATE * grad_b
    return weights, bias


def standardise(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Приводит признаки к нулю и единице.

    Без этого доля потерь в процентах (десятки) задавит долю пикселей
    с признаком горения (доли единицы) просто масштабом.
    """
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale == 0] = 1.0
    return (x - mean) / scale, mean, scale


def category(probability: float) -> str:
    if probability >= THRESHOLD_HIGH:
        return "high"
    if probability >= THRESHOLD_MEDIUM:
        return "medium"
    return "low"


def leave_one_out(x: np.ndarray, y: np.ndarray) -> list[dict]:
    """Скользящий контроль по одному.

    На четырёх точках это не проверка качества, а проверка того,
    рассыпается ли модель от удаления одной строки. Если рассыпается —
    значит она держалась на этой строке.
    """
    results = []
    for i in range(len(y)):
        mask = np.ones(len(y), dtype=bool)
        mask[i] = False
        if len(set(y[mask].tolist())) < 2:
            # В обучении остался один класс — модель вырождена,
            # и это надо записать, а не пропустить молча.
            results.append({"index": i, "probability": None, "degenerate": True})
            continue
        x_train, mean, scale = standardise(x[mask])
        weights, bias = fit(x_train, y[mask])
        probability = float(sigmoid(((x[i] - mean) / scale) @ weights + bias))
        results.append({"index": i, "probability": probability, "degenerate": False})
    return results


def separability(x: np.ndarray, y: np.ndarray) -> list[dict]:
    """Какие признаки разделяют классы поодиночке.

    Если разделяет каждый, совместная модель ничего не добавляет —
    и это главный вывод при такой выборке.
    """
    out = []
    for index, key in enumerate(FEATURE_KEYS):
        positive = x[y == 1, index]
        negative = x[y == 0, index]
        if positive.size == 0 or negative.size == 0:
            out.append({"feature": key, "separates": None})
            continue
        gap = float(min(positive) - max(negative))
        out.append(
            {
                "feature": key,
                "separates": bool(min(positive) > max(negative) or max(positive) < min(negative)),
                "gap": gap,
                "positive_min": float(min(positive)),
                "negative_max": float(max(negative)),
            }
        )
    return out


def required_sample_size(features: int, per_feature: int = 10) -> int:
    """Сколько участков нужно, чтобы выборка начала что-то значить.

    Практическое правило для логистической регрессии: не меньше десяти
    наблюдений МЕНЬШЕГО класса на каждый признак. При шести признаках
    это шестьдесят участков меньшего класса.
    """
    return features * per_feature


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=Path("data/stability_features.csv"))
    parser.add_argument("--out", type=Path, default=Path("data/stability_model.json"))
    args = parser.parse_args()

    with open(args.features, encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    x = np.array([[float(row[key]) for key in FEATURE_KEYS] for row in rows])
    y = np.array([int(row["label"]) for row in rows])
    names = [row["aoi_id"] for row in rows]

    x_std, mean, scale = standardise(x)
    weights, bias = fit(x_std, y)
    probabilities = sigmoid(x_std @ weights + bias)

    loo = leave_one_out(x, y)
    marks = separability(x, y)

    minority = int(min((y == 1).sum(), (y == 0).sum()))
    needed = required_sample_size(len(FEATURE_KEYS))

    print(f"участков: {len(y)}, положительных: {int(y.sum())}, меньший класс: {minority}")
    print()
    print(f"{'участок':<16} {'факт':>5} {'модель':>8} {'категория':>10} {'скользящий':>11}")
    for i, name in enumerate(names):
        probability = loo[i]["probability"]
        loo_text = "вырожден" if loo[i]["degenerate"] else f"{probability:.3f}"
        print(
            f"{name:<16} {y[i]:>5} {probabilities[i]:>8.3f} "
            f"{category(float(probabilities[i])):>10} {loo_text:>11}"
        )

    print()
    print("вклад признаков (стандартизованные коэффициенты):")
    for key, weight in sorted(
        zip(FEATURE_KEYS, weights), key=lambda pair: abs(pair[1]), reverse=True
    ):
        print(f"  {key:<20} {weight:+.4f}")

    single = [m for m in marks if m.get("separates")]
    print()
    print(f"признаков, разделяющих классы поодиночке: {len(single)} из {len(FEATURE_KEYS)}")
    for m in single:
        print(f"  {m['feature']}")

    verdict = (
        f"Выборка не позволяет проверить модель: меньший класс — {minority} наблюдение, "
        f"при шести признаках практическое правило требует не меньше {needed}. "
        f"{len(single)} признаков из {len(FEATURE_KEYS)} разделяют классы поодиночке, "
        "поэтому идеальная точность на обучении ничего не доказывает. "
        "В продукт по умолчанию идут пороговые правила; модель показывается "
        "как второе мнение с этой же оговоркой."
    )
    print()
    print(verdict)

    payload = {
        "method": "логистическая регрессия с L2, без обучающей библиотеки",
        "features": FEATURE_KEYS,
        "l2": L2,
        "standardisation": {"mean": mean.tolist(), "scale": scale.tolist()},
        "weights": dict(zip(FEATURE_KEYS, weights.tolist())),
        "bias": float(bias),
        "thresholds": {"medium": THRESHOLD_MEDIUM, "high": THRESHOLD_HIGH},
        "predictions": [
            {
                "aoi_id": names[i],
                "label": int(y[i]),
                "probability": float(probabilities[i]),
                "category": category(float(probabilities[i])),
                "leave_one_out": loo[i]["probability"],
                "leave_one_out_degenerate": loo[i]["degenerate"],
            }
            for i in range(len(y))
        ],
        "separability": marks,
        "sample": {
            "size": int(len(y)),
            "positives": int(y.sum()),
            "minority_class": minority,
            "required_minority": needed,
            "sufficient": minority >= needed,
        },
        "verdict": verdict,
        "status": "второе мнение; по умолчанию работают пороговые правила",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nзаписано {args.out}")


if __name__ == "__main__":
    main()
