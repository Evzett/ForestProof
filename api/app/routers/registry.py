"""Раздел 12 контракта — каталог реестра (KAN-43)."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app import models

router = APIRouter(prefix="/api", tags=["registry"])


@router.get("/registry/projects")
def registry_catalog(db: Session = Depends(get_db)) -> dict:
    """Каталог ВСЕХ проектов из выгрузки реестра — не только посчитанных.
    Один запрос, без пагинации (раздел 12, "два правила")."""
    meta = db.scalars(select(models.RegistryImportMeta).order_by(models.RegistryImportMeta.imported_at.desc())).first()
    entries = db.scalars(select(models.RegistryCatalogEntry).order_by(models.RegistryCatalogEntry.registry_number)).all()

    return {
        "total": len(entries),
        "with_geometry": sum(1 for e in entries if e.project_id is not None),
        "export_date": meta.export_date.isoformat() if meta else None,
        "items": [
            {
                "registry_number": e.registry_number,
                "name": e.name,
                "company": e.company,
                "region": e.region,
                "methodology": e.methodology,
                "effect_kind": e.effect_kind.value if e.effect_kind else None,
                "units_in_circulation": e.units_in_circulation,
                "data_status": e.data_status.value,
                "project_id": e.project_id,
                "calc_id": e.calc_id,
            }
            for e in entries
        ],
    }
