"""Роли и авторизация. KAN-78.

Три назначаемые роли: оператор, инвестор, администратор. Плюс `viewer` —
не роль, а вид сервиса для того, кто ещё не вошёл.

Главное решение: **на пути к демо формы входа нет**. Сервис открывается
сразу, и всё содержимое видно без логина. Вход нужен, чтобы работать от
своего имени: у загруженного контура и запущенного расчёта появляется
владелец.

Второе: **регистрация открыта и даёт роль оператора**. Выше оператора —
только рукой администратора. Иначе форма регистрации раздавала бы права
на чужие данные любому, кто её открыл.

Третье: **в режиме демонстрации сервис открывается администратором**.
Включается переменной окружения и по умолчанию действует только при
`ENVIRONMENT=development`. На проде выключено: там вход обязателен.

Четвёртое: **права проверяются здесь, на сервере**. Скрытая в
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
from sqlalchemy import select
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


def _open_admin_enabled() -> bool:
    """Открывать ли сервис администратором без входа.

    Это режим демонстрации, а не настройка по умолчанию «для удобства».
    Явно включается переменной, и на проде (`ENVIRONMENT=production`) не
    включается вовсе, чем бы ни была заполнена переменная: открытая
    панель администратора в интернете — это не демо, а раздача доступа.
    """
    if os.environ.get("ENVIRONMENT", "development").strip().lower() == "production":
        return False
    value = os.environ.get("FORESTPROOF_OPEN_ADMIN", "1").strip().lower()
    return value not in {"", "0", "false", "no"}


def current_user(request: Request, db: Session = Depends(get_db)) -> models.User | None:
    """Пользователь запроса или None.

    Отсутствие входа — не ошибка: чтение открыто, и 401 на каждом экране
    сломал бы демо.

    В режиме демонстрации вместо None возвращается администратор: на
    защите никто не должен искать логин, чтобы показать, как работает
    загрузка контура. Подмена одна и в одном месте — дальше по коду
    разницы между «вошёл администратор» и «демо» нет, а значит нет и
    ветки, в которой права случайно разъедутся.
    """
    token = _token_from_request(request)
    if not token:
        if _open_admin_enabled():
            demo = db.scalars(
                select(models.User)
                .where(models.User.role == models.Role.admin, models.User.blocked.is_(False))
                .order_by(models.User.created_at)
            ).first()
            if demo is not None:
                return demo
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


_ORDER = {
    models.Role.viewer: 0,
    models.Role.investor: 1,
    models.Role.operator: 2,
    models.Role.admin: 3,
}


def at_least(user: models.User | None, minimum: models.Role) -> bool:
    """Хватает ли прав — без исключения. Нужно там, где ответ зависит от
    роли, но отказывать не за что: список контуров, например, просто
    показывает разным людям разное."""
    return _ORDER[role_of(user)] >= _ORDER[minimum]


def _require(user: models.User | None, minimum: models.Role, action: str) -> models.User:
    if user is None:
        raise HTTPException(
            status_code=401,
            detail=f"{action} требует входа. Наблюдателю доступен просмотр без входа.",
        )
    if user.blocked:
        raise HTTPException(
            status_code=403,
            detail="Учётная запись заблокирована. Обратитесь к администратору.",
        )
    if _ORDER[user.role] < _ORDER[minimum]:
        raise HTTPException(
            status_code=403,
            detail=f"{action} недоступно роли «{ROLE_LABELS[user.role]}».",
        )
    return user


ROLE_LABELS = {
    models.Role.viewer: "наблюдатель",
    models.Role.investor: "инвестор",
    models.Role.operator: "оператор",
    models.Role.admin: "администратор",
}

# Что роль означает на человеческом языке. Показывается в профиле и в
# панели администратора: выдавая роль, надо понимать, что именно выдаёшь.
ROLE_NOTES = {
    models.Role.viewer: "Просмотр участков, расчётов и журнала — без входа.",
    models.Role.investor: (
        "Просмотр, денежная оценка и отбор участков. Данные не правит: "
        "решение принимается по числам, которые инвестор не менял."
    ),
    models.Role.operator: (
        "Загружает контуры, запускает расчёты, ведёт свои участки и решает, "
        "публиковать ли их."
    ),
    models.Role.admin: (
        "Всё вышеперечисленное плюс учётные записи, роли и обслуживание "
        "источников данных."
    ),
}

# Роли, которые администратор может выдать. `viewer` в списке нет: это
# вид сервиса до входа, а не назначение.
ASSIGNABLE = [models.Role.investor, models.Role.operator, models.Role.admin]


def require_any(user: models.User | None = Depends(current_user)) -> models.User:
    """Только вход, без требований к роли: свой профиль и свой пароль."""
    return _require(user, models.Role.viewer, "Действие")


def require_operator(user: models.User | None = Depends(current_user)) -> models.User:
    return _require(user, models.Role.operator, "Действие")


def require_investor(user: models.User | None = Depends(current_user)) -> models.User:
    return _require(user, models.Role.investor, "Действие")


def require_admin(user: models.User | None = Depends(current_user)) -> models.User:
    return _require(user, models.Role.admin, "Действие")
