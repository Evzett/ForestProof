"""Заводит учётные записи. KAN-78.

    docker compose -f api/docker-compose.yml exec api python -m app.seed_users

Регистрации в сервисе нет намеренно: подтверждение почты на хакатоне —
время без баллов. Учётные записи заводятся заранее, этой командой.

Пароли берутся из окружения, а в код не зашиваются. Если переменная не
задана, пароль генерируется случайно и печатается ОДИН раз — записать
его нужно сразу: в базе лежит только хеш, восстановить пароль нельзя.
"""

import os
import secrets

from app.auth import hash_password
from app.database import SessionLocal
from app import models

ACCOUNTS = [
    ("analyst", "Аналитик", models.Role.analyst, "FORESTPROOF_ANALYST_PASSWORD"),
    ("admin", "Администратор", models.Role.admin, "FORESTPROOF_ADMIN_PASSWORD"),
]


def main() -> None:
    db = SessionLocal()
    try:
        for login, display_name, role, env_key in ACCOUNTS:
            password = os.environ.get(env_key, "").strip()
            generated = not password
            if generated:
                password = secrets.token_urlsafe(9)

            user = db.get(models.User, login)
            if user is None:
                db.add(
                    models.User(
                        login=login,
                        display_name=display_name,
                        password_hash=hash_password(password),
                        role=role,
                    )
                )
                action = "создана"
            else:
                # Пароль перезаписывается только когда он задан явно:
                # иначе повторный запуск молча менял бы рабочий пароль на
                # случайный и выбивал бы людей из сервиса.
                if generated:
                    print(f"{login}: учётная запись уже есть, пароль не меняли")
                    continue
                user.password_hash = hash_password(password)
                user.role = role
                action = "пароль обновлён"

            print(f"{login} ({role.value}): {action}")
            if generated:
                print(f"    пароль: {password}    ← показан один раз, сохраните его")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
