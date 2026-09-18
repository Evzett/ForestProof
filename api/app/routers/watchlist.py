"""Раздел 12 контракта — наблюдение. Подписки и уведомления не реализуются
в прототипе, только список и добавление/удаление."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app import models
from app.schemas import WatchlistAddRequest

router = APIRouter(prefix="/api", tags=["watchlist"])


@router.get("/watchlist")
def list_watchlist(db: Session = Depends(get_db)) -> dict:
    entries = db.scalars(
        select(models.WatchlistEntry).options(selectinload(models.WatchlistEntry.project))
    ).all()
    return {
        "items": [
            {
                "project_id": e.project_id,
                "name": e.project.name,
                "last_checked_at": e.last_checked_at.isoformat() if e.last_checked_at else None,
                "new_events_count": e.new_events_count,
                "recent_loss_ha": float(e.recent_loss_ha) if e.recent_loss_ha is not None else None,
                "status": e.status.value,
            }
            for e in entries
        ]
    }


@router.post("/watchlist")
def add_to_watchlist(body: WatchlistAddRequest, db: Session = Depends(get_db)) -> dict:
    project = db.get(models.Project, body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="проект не найден")

    existing = db.get(models.WatchlistEntry, body.project_id)
    if existing is None:
        db.add(models.WatchlistEntry(project_id=body.project_id))
        db.commit()
    return {"project_id": body.project_id, "watching": True}


@router.delete("/watchlist/{project_id}")
def remove_from_watchlist(project_id: str, db: Session = Depends(get_db)) -> dict:
    entry = db.get(models.WatchlistEntry, project_id)
    if entry is not None:
        db.delete(entry)
        db.commit()
    return {"project_id": project_id, "watching": False}
