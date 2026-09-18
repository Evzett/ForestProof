"""Раздел 8 контракта, `input_hash`.

SHA-256 от канонического JSON входных данных (ключи отсортированы, пробелы
убраны). Одинаковый вход обязан давать одинаковый хеш — на этом стоит
воспроизводимость расчётов.
"""

import hashlib
import json
from typing import Any


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def compute_input_hash(payload: Any) -> str:
    """Возвращает полную 64-символьную строку — не усекать при хранении
    (раздел 8: "в примерах этого файла она усечена для читаемости")."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
