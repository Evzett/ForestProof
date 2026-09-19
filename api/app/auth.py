"""Роли и авторизация. KAN-78.

Три роли по возрастанию прав: наблюдатель, аналитик, администратор.

Главное решение: **по умолчанию сервис открыт в роли наблюдателя**, и на
пути к демо формы входа нет. Прежнее «регистрации нет» принималось именно
из-за риска, что форма входа сломает защиту. Вход появляется только там,
где начинается запись: загрузка контура, запуск расчёта, удаление.

Второе решение: **права проверяются здесь, на сервере**. Скрытая в
интерфейсе кнопка ограничением доступа не является — запрос можно послать
мимо интерфейса, и он должен быть отклонён.

Пароли хранятся только хешем bcrypt. Открытого пароля нет ни в базе, ни в
логах, ни в ответах API.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

# Срок жизни токена. Сутки: демо и защита укладываются с запасом, а
# вечный токен — это утечка, которую нечем отозвать.
TOKEN_TTL_SECONDS = 24 * 60 * 60

COOKIE_NAME = "forestproof_session"


def _secret() -> bytes:
    """Секрет подписи. Берётся из окружения и в репозиторий не попадает.

    Если переменная не задана, секрет генерируется на время жизни
    процесса: демо поднимается без настройки, но после перезапуска все
    выданные токены становятся недействительными — это лучше, чем
    зашитый в код секрет, одинаковый у всех, кто склонировал репозиторий.
    """
    value = os.environ.get("AUTH_SECRET", "").strip()
    if value:
        return value.encode("utf-8")
    global _EPHEMERAL_SECRET
    if _EPHEMERAL_SECRET is None:
        _EPHEMERAL_SECRET = secrets.token_bytes(32)
    return _EPHEMERAL_SECRET


_EPHEMERAL_SECRET: bytes | None = None


def hash_password(password: str) -> str:
    """Хеш пароля. bcrypt сам солит каждый хеш — одинаковые пароли дают
    разные строки, и по базе нельзя увидеть, у кого пароли совпадают."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        # Испорченный хеш в базе — это отказ во входе, а не исключение
        # наружу: иначе по типу ошибки видно состояние чужой записи.
        return False


def _b64(raw: bytes) -> str:
    return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return urlsafe_b64decode(text + pad)


def issue_token(login: str, role: str) -> str:
    """Подписанный токен: полезная нагрузка и HMAC-SHA256 от неё.

    Своя реализация вместо библиотеки JWT: нужен ровно один алгоритм
    подписи, и лишняя зависимость с настраиваемым `alg` — это известный
    класс ошибок (подмена алгоритма на none), который здесь невозможен.
    """
    payload = {"sub": login, "role": role, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64(signature)}"


def read_token(token: str) -> dict | None:
    """Разбирает токен. Любая неисправность — это «не авторизован», без
    подробностей: по тексту ошибки не должно быть видно, чем именно токен
    не понравился."""
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
        # Сравнение постоянного времени: обычное == утекает по времени.
        if not hmac.compare_digest(expected, _unb64(signature)):
            return None
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
        return None
    return payload


def _token_from_request(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip() or None
    return request.cookies.get(COOKIE_NAME)


def current_user(request: Request, db: Session = Depends(get_db)) -> models.User | None:
    """Пользователь запроса или None. Отсутствие входа — не ошибка:
    наблюдателю доступ к чтению открыт, и 401 на каждом экране сломал бы
    демо."""
    token = _token_from_request(request)
    if not token:
        return None
    payload = read_token(token)
    if payload is None:
        return None
    user = db.get(models.User, payload.get("sub", ""))
    # Роль берётся из базы, а не из токена: если роль понизили, старый
    # токен не должен сохранять прежние права.
    return user


def role_of(user: models.User | None) -> models.Role:
    """Роль запроса. Без входа — наблюдатель: это режим демо."""
    return user.role if user is not None else models.Role.viewer


_ORDER = {models.Role.viewer: 0, models.Role.analyst: 1, models.Role.admin: 2}


def _require(user: models.User | None, minimum: models.Role, action: str) -> models.User:
    if user is None:
        raise HTTPException(
            status_code=401,
            detail=f"{action} требует входа. Наблюдателю доступен просмотр без входа.",
        )
    if _ORDER[user.role] < _ORDER[minimum]:
        raise HTTPException(
            status_code=403,
            detail=f"{action} недоступно роли «{ROLE_LABELS[user.role]}».",
        )
    return user


ROLE_LABELS = {
    models.Role.viewer: "наблюдатель",
    models.Role.analyst: "аналитик",
    models.Role.admin: "администратор",
}


def require_analyst(user: models.User | None = Depends(current_user)) -> models.User:
    return _require(user, models.Role.analyst, "Действие")


def require_admin(user: models.User | None = Depends(current_user)) -> models.User:
    return _require(user, models.Role.admin, "Действие")
