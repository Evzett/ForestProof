"""Вход, регистрация, профиль. KAN-78.

Регистрация открытая и выдаёт роль оператора: этого хватает, чтобы
загрузить свой контур и посчитать его, и не хватает, чтобы тронуть чужое.
Роли выше выдаёт только администратор — самоназначения нет ни в одной
точке входа.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth, models
from app.database import get_db
from app.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    ProfileRequest,
    RegisterRequest,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Палитра аватаров. Цвета из нашей системы, а не случайный hsl: аватар
# стоит рядом с интерфейсом и не должен выбиваться из него.
AVATAR_COLORS = ["#2f6b4f", "#7d5a3c", "#4a5f7a", "#6b4a6b", "#8a6d2f", "#3f6b6b"]


def initials(display_name: str, login: str) -> str:
    """Буквы для аватара: по слову имени, иначе первая буква логина."""
    words = [w for w in display_name.replace("-", " ").split() if w]
    if not words:
        return login[:1].upper()
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][:1] + words[1][:1]).upper()


def _describe(user: models.User | None) -> dict:
    """Ответ о текущем праве доступа.

    `can` отдаётся явным списком, чтобы интерфейс не повторял у себя
    правила ролей и не разошёлся с сервером. Это подсказка для отрисовки,
    а не ограничение: ограничение — проверка на сервере.
    """
    role = auth.role_of(user)
    return {
        "authenticated": user is not None,
        "login": user.login if user else None,
        "display_name": user.display_name if user else None,
        "role": role.value,
        "role_label": auth.ROLE_LABELS[role],
        "role_note": auth.ROLE_NOTES[role],
        "blocked": bool(user.blocked) if user else False,
        # Показывать ли кнопку возврата в демонстрационный режим. Фронт
        # не должен догадываться об этом по роли: на проде режима нет
        # вовсе, и кнопка была бы обещанием, которое некому выполнить.
        "demo_available": auth.demo_admin_allowed(),
        "avatar": (
            {
                "initials": initials(user.display_name, user.login),
                "color": user.avatar_color or AVATAR_COLORS[0],
            }
            if user
            else None
        ),
        "can": {
            "view": True,
            # Денежная оценка — ответ на вопрос инвестора, и показывать её
            # наблюдателю незачем: числа рублёвые, а участок непроверенный.
            "value": auth.at_least(user, models.Role.investor),
            "calculate": auth.at_least(user, models.Role.operator),
            "upload": auth.at_least(user, models.Role.operator),
            "publish": auth.at_least(user, models.Role.operator),
            "manage": auth.at_least(user, models.Role.admin),
        },
    }


def _issue(user: models.User, response: Response) -> dict:
    token = auth.issue_token(user.login, user.role.value)
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        max_age=auth.TOKEN_TTL_SECONDS,
        httponly=True,  # из JavaScript кука недоступна — это защита от кражи токена
        samesite="lax",
    )
    return {**_describe(user), "token": token}


@router.get("/me")
def me(user: models.User | None = Depends(auth.current_user)) -> dict:
    """Кто открыл сервис.

    В режиме демонстрации это администратор: см. `auth.current_user`.
    Без демо-режима и без входа — наблюдатель, и это тоже не ошибка.
    """
    return _describe(user)


@router.get("/roles")
def roles() -> dict:
    """Роли, которые можно назначить, с пояснениями.

    `viewer` в списке нет намеренно: это вид сервиса до входа, а не
    назначение. Показав его в выпадающем списке панели администратора,
    мы предложили бы «понизить человека до гостя» — действие, которого в
    сервисе не существует: для этого есть блокировка.
    """
    return {
        "roles": [
            {
                "value": role.value,
                "label": auth.ROLE_LABELS[role],
                "note": auth.ROLE_NOTES[role],
            }
            for role in auth.ASSIGNABLE
        ]
    }


@router.post("/register")
def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    """Новая учётная запись с ролью оператора.

    Роль в запросе не принимается вовсе — не «игнорируется», а не
    существует в форме запроса. Поле, которое можно прислать и которое
    иногда учитывается, однажды учтётся не тогда.
    """
    login = body.login.strip().lower()
    if not login.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise HTTPException(
            status_code=422,
            detail="Логин: латиница и цифры, допустимы дефис, точка и подчёркивание.",
        )

    user = models.User(
        login=login,
        display_name=body.display_name.strip() or login,
        password_hash=auth.hash_password(body.password),
        role=models.Role.operator,
        avatar_color=secrets.choice(AVATAR_COLORS),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Такой логин уже занят.") from None
    db.refresh(user)
    return _issue(user, response)


@router.post("/login")
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    user = db.get(models.User, body.login.strip().lower())
    # Один и тот же ответ на неизвестный логин и на неверный пароль:
    # иначе форма входа превращается в средство проверки, какие логины
    # существуют. Пароль в лог не попадает ни в каком виде.
    if user is None or not auth.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль.")
    # А вот про блокировку говорим прямо: пароль человек ввёл верный, и
    # «неверный логин или пароль» отправило бы его искать несуществующую
    # опечатку вместо того, чтобы написать администратору.
    if user.blocked:
        raise HTTPException(
            status_code=403,
            detail="Учётная запись заблокирована. Обратитесь к администратору.",
        )

    return _issue(user, response)


@router.post("/logout")
def logout(response: Response) -> dict:
    """Выход. Снимает сессию и, если сервис работает в режиме
    демонстрации, выключает его для этого браузера.

    Без второго выход не работал: токен снимался, и сервис тут же
    подставлял администратора обратно. Кнопка «Выйти» ничего не меняла,
    и объяснить это человеку было нечем.
    """
    response.delete_cookie(auth.COOKIE_NAME)
    if auth.demo_admin_allowed():
        response.set_cookie(
            auth.DEMO_OFF_COOKIE,
            "1",
            max_age=auth.TOKEN_TTL_SECONDS,
            samesite="lax",
        )
    return {"ok": True, "demo_available": auth.demo_admin_allowed()}


@router.post("/demo")
def demo(response: Response) -> dict:
    """Вернуться в демонстрационный режим после выхода.

    Нужна ровно потому, что выход теперь настоящий: выйдя, человек
    остаётся наблюдателем, и вернуть показ «как видит администратор»
    иначе можно было бы только чисткой кук.

    На проде ничего не включает и честно об этом говорит.
    """
    if not auth.demo_admin_allowed():
        raise HTTPException(
            status_code=404,
            detail="Демонстрационный режим на этой установке выключен. Нужен вход.",
        )
    response.delete_cookie(auth.DEMO_OFF_COOKIE)
    return {"ok": True}


@router.patch("/me")
def update_profile(
    body: ProfileRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_any),
) -> dict:
    """Своё имя и цвет аватара. Роль отсюда не меняется никогда."""
    if body.display_name is not None:
        name = body.display_name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Имя не может быть пустым.")
        user.display_name = name
    if body.avatar_color is not None:
        if body.avatar_color not in AVATAR_COLORS:
            raise HTTPException(status_code=422, detail="Такого цвета нет в палитре.")
        user.avatar_color = body.avatar_color
    db.commit()
    db.refresh(user)
    return _describe(user)


@router.post("/password")
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_any),
) -> dict:
    """Смена своего пароля. Текущий спрашиваем обязательно.

    Токен живёт сутки, и украденного токена хватило бы, чтобы сменить
    пароль и забрать учётную запись насовсем. Старый пароль — граница,
    которую одним токеном не перейти.
    """
    if not auth.verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=403, detail="Текущий пароль указан неверно.")
    user.password_hash = auth.hash_password(body.new_password)
    db.commit()
    return {"ok": True}


@router.get("/palette")
def palette() -> dict:
    """Цвета аватара — чтобы интерфейс не держал свою копию палитры."""
    return {"colors": AVATAR_COLORS}
