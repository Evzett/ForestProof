"""Вход, выход и «кто я». KAN-78.

Регистрации нет намеренно (см. постановку): учётные записи заводятся
заранее через `python -m app.seed_users`.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import auth, models
from app.database import get_db
from app.schemas import LoginRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
        "can": {
            "view": True,
            "calculate": role in (models.Role.analyst, models.Role.admin),
            "upload": role in (models.Role.analyst, models.Role.admin),
            "manage": role is models.Role.admin,
        },
    }


@router.get("/me")
def me(user: models.User | None = Depends(auth.current_user)) -> dict:
    """Кто открыл сервис. Без входа — наблюдатель, и это не ошибка."""
    return _describe(user)


@router.post("/login")
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    user = db.get(models.User, body.login.strip().lower())
    # Один и тот же ответ на неизвестный логин и на неверный пароль:
    # иначе форма входа превращается в средство проверки, какие логины
    # существуют. Пароль в лог не попадает ни в каком виде.
    if user is None or not auth.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль.")

    token = auth.issue_token(user.login, user.role.value)
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        max_age=auth.TOKEN_TTL_SECONDS,
        httponly=True,  # из JavaScript кука недоступна — это защита от кражи токена
        samesite="lax",
    )
    return {**_describe(user), "token": token}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(auth.COOKIE_NAME)
    return {"ok": True}
