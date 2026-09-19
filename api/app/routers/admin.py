"""Панель администратора. KAN-78.

Учётные записи, роли, блокировка, сброс пароля. Всё под
`require_admin` — проверка на сервере, а не спрятанная кнопка.

Удаления учётной записи здесь нет, и это решение, а не пропуск. За
человеком остаются расчёты и контуры; удалив запись, мы обнулили бы
подписи в журнале и оставили бы расчёты без автора. Блокировка закрывает
вход и сохраняет следы.
"""

import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth, case_service, models
from app.database import get_db
from app.routers.auth import initials
from app.schemas import AdminPasswordRequest, AdminUserRequest

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _row(user: models.User, contours: int, calcs: int) -> dict:
    return {
        "login": user.login,
        "display_name": user.display_name,
        "role": user.role.value,
        "role_label": auth.ROLE_LABELS[user.role],
        "blocked": bool(user.blocked),
        "avatar": {
            "initials": initials(user.display_name, user.login),
            "color": user.avatar_color or "#2f6b4f",
        },
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "contours": contours,
        "calculations": calcs,
    }


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.require_admin),
) -> dict:
    """Список учётных записей со счётчиком работы за каждой.

    Счётчики важнее, чем кажется: перед сменой роли видно, сколько за
    человеком расчётов, и понижение перестаёт быть слепым.
    """
    users = db.scalars(select(models.User).order_by(models.User.created_at)).all()

    contours = dict(
        db.execute(
            select(models.SavedContour.created_by, func.count()).group_by(
                models.SavedContour.created_by
            )
        ).all()
    )
    calcs = dict(
        db.execute(
            select(models.Calculation.created_by, func.count()).group_by(
                models.Calculation.created_by
            )
        ).all()
    )

    return {
        "users": [
            _row(u, int(contours.get(u.login, 0)), int(calcs.get(u.login, 0))) for u in users
        ]
    }


@router.patch("/users/{login}")
def update_user(
    login: str,
    body: AdminUserRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.require_admin),
) -> dict:
    user = db.get(models.User, login)
    if user is None:
        raise HTTPException(status_code=404, detail="Учётная запись не найдена.")

    if body.role is not None:
        try:
            role = models.Role(body.role)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Роли «{body.role}» нет.") from None
        # Администратор не понижает и не блокирует сам себя. Иначе
        # последний администратор одним нажатием запирает сервис снаружи,
        # и вернуть права будет некому.
        if user.login == admin.login and role is not models.Role.admin:
            raise HTTPException(
                status_code=409,
                detail="Нельзя снять роль администратора с самого себя.",
            )
        user.role = role

    if body.blocked is not None:
        if user.login == admin.login and body.blocked:
            raise HTTPException(status_code=409, detail="Нельзя заблокировать самого себя.")
        user.blocked = body.blocked

    db.commit()
    db.refresh(user)
    return _row(user, 0, 0)


@router.post("/users/{login}/password")
def reset_password(
    login: str,
    body: AdminPasswordRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.require_admin),
) -> dict:
    """Сброс чужого пароля. Старый не спрашивается: смысл сброса в том,
    что старого никто не знает. Новый администратор придумывает сам и
    передаёт человеку — сервис не рассылает паролей."""
    user = db.get(models.User, login)
    if user is None:
        raise HTTPException(status_code=404, detail="Учётная запись не найдена.")
    user.password_hash = auth.hash_password(body.new_password)
    db.commit()
    return {"ok": True, "login": login}


# ---------- Обслуживание источников ----------
#
# Расчёт по чужому контуру целиком зависит от внешних каталогов, и когда
# он падает, первый вопрос — «источник лежит или токен кончился». Раньше
# ответ на него жил в логах контейнера. Теперь — на экране.

CACHE_DIRS = {
    "Sentinel-2 (сцены)": Path("data/cache/sentinel"),
    "MODIS MCD64A1 (гари)": Path("data/cache/modis"),
    "Тайлы растров": Path("data/cache/tiles"),
}


def _root() -> Path:
    return Path(os.environ.get("FORESTPROOF_ROOT", ".")).resolve()


def _size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / 1024 / 1024, 1)


@router.get("/sources")
def sources(admin: models.User = Depends(auth.require_admin)) -> dict:
    """Состояние источников и кэша.

    «Ключ задан» — это не «источник работает»: проверить второе значило бы
    ходить в сеть на каждое открытие панели. Показываем то, что знаем
    точно, и не выдаём догадку за проверку.
    """
    root = _root()
    token = bool(os.environ.get("EARTHDATA_TOKEN", "").strip())
    return {
        "sources": [
            {
                "name": "ESA CCI Biomass v7.0",
                "kind": "биомасса",
                "auth": "не требуется",
                "ready": True,
                "note": "Читается окном по HTTP Range из архива CEDA.",
            },
            {
                "name": "Hansen GFC v1.13",
                "kind": "потери покрова",
                "auth": "не требуется",
                "ready": True,
                "note": "Читается окном по HTTP Range из Google Storage.",
            },
            {
                "name": "Sentinel-2 L2A",
                "kind": "снимки",
                "auth": "не требуется",
                "ready": True,
                "note": "Каталог STAC Element 84, поиск по рамке контура.",
            },
            {
                "name": "MODIS MCD64A1 061",
                "kind": "гари",
                "auth": "Earthdata Bearer",
                "ready": token,
                "note": (
                    "Токен задан в окружении."
                    if token
                    else "EARTHDATA_TOKEN не задан — гари искаться не будут."
                ),
            },
        ],
        "cache": [
            {"name": name, "path": str(path), "size_mb": _size_mb(root / path)}
            for name, path in CACHE_DIRS.items()
        ],
        "contour_maps": {
            "path": str(case_service.MAPS_ROOT),
            "size_mb": _size_mb(case_service.MAPS_ROOT),
            "count": (
                len([p for p in case_service.MAPS_ROOT.iterdir() if p.is_dir()])
                if case_service.MAPS_ROOT.exists()
                else 0
            ),
        },
    }


@router.delete("/sources/cache")
def clear_cache(admin: models.User = Depends(auth.require_admin)) -> dict:
    """Чистит кэш скачанного. Карты контуров не трогает.

    Кэш — копия того, что лежит в сети: удалишь, и следующий расчёт
    скачает заново, потеряв только время. Карты контуров — результат
    расчёта, который уже показан в интерфейсе; стереть их значило бы
    сделать пустыми страницы сохранённых участков.
    """
    root = _root()
    freed = 0.0
    for path in CACHE_DIRS.values():
        target = root / path
        freed += _size_mb(target)
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
    return {"ok": True, "freed_mb": round(freed, 1)}
