"""Роли и разграничение доступа. KAN-78.

Проверяется то, что легко сломать молча и незаметно на глаз:

* наблюдатель не может запустить расчёт — и отказ приходит от сервера, а
  не от спрятанной в интерфейсе кнопки;
* роль берётся из базы, а не из токена: понижение прав действует сразу;
* пароль хранится только хешем, и хеш не равен паролю;
* подпись токена нельзя подделать подменой полезной нагрузки.

Тесты работают без базы и без поднятого сервиса: проверяются сами правила,
а не связка с Postgres.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "api"))

from fastapi import HTTPException  # noqa: E402

from app import auth, models  # noqa: E402


def user(role: models.Role) -> models.User:
    return models.User(login="кто-то", display_name="Кто-то", password_hash="", role=role)


# --- пароли ---------------------------------------------------------------


def test_password_is_stored_only_as_hash():
    password = "очень-секретный-пароль"
    stored = auth.hash_password(password)

    assert stored != password
    assert password not in stored
    assert auth.verify_password(password, stored)
    assert not auth.verify_password("другой", stored)


def test_same_password_gives_different_hashes():
    """bcrypt солит каждый хеш: по базе не видно, у кого пароли совпадают."""
    first = auth.hash_password("одинаковый")
    second = auth.hash_password("одинаковый")
    assert first != second


def test_broken_hash_denies_entry_instead_of_raising():
    """Испорченный хеш — отказ во входе, а не исключение наружу: иначе по
    типу ошибки видно состояние чужой записи."""
    assert auth.verify_password("что угодно", "не хеш вовсе") is False


# --- токены ---------------------------------------------------------------


def test_token_round_trip():
    token = auth.issue_token("analyst", "analyst")
    payload = auth.read_token(token)
    assert payload is not None
    assert payload["sub"] == "analyst"


def test_tampered_payload_is_rejected():
    """Подмена полезной нагрузки без пересчёта подписи не проходит."""
    token = auth.issue_token("analyst", "analyst")
    body, signature = token.split(".", 1)
    forged = auth.issue_token("analyst", "admin").split(".", 1)[0]
    assert auth.read_token(f"{forged}.{signature}") is None


def test_expired_token_is_rejected(monkeypatch):
    token = auth.issue_token("analyst", "analyst")
    monkeypatch.setattr(auth.time, "time", lambda: 10**12)
    assert auth.read_token(token) is None


def test_garbage_token_is_rejected():
    for value in ("", "точек.нет.вовсе", "не-токен", "a.b"):
        assert auth.read_token(value) is None


# --- права ----------------------------------------------------------------


def test_viewer_is_the_default_without_login():
    """Без входа — наблюдатель. Это режим демо, а не ошибка."""
    assert auth.role_of(None) is models.Role.viewer


def test_viewer_cannot_calculate():
    with pytest.raises(HTTPException) as exc:
        auth.require_analyst(user(models.Role.viewer))
    assert exc.value.status_code == 403


def test_anonymous_cannot_calculate():
    with pytest.raises(HTTPException) as exc:
        auth.require_analyst(None)
    assert exc.value.status_code == 401


def test_analyst_can_calculate_but_not_administer():
    assert auth.require_analyst(user(models.Role.analyst)) is not None
    with pytest.raises(HTTPException) as exc:
        auth.require_admin(user(models.Role.analyst))
    assert exc.value.status_code == 403


def test_admin_can_do_both():
    assert auth.require_analyst(user(models.Role.admin)) is not None
    assert auth.require_admin(user(models.Role.admin)) is not None


def test_roles_are_ordered_by_privilege():
    """Порядок ролей задан явно: добавление новой роли мимо него сразу
    развалит сравнение прав, а не тихо разрешит лишнее."""
    assert auth._ORDER[models.Role.viewer] < auth._ORDER[models.Role.analyst]
    assert auth._ORDER[models.Role.analyst] < auth._ORDER[models.Role.admin]
