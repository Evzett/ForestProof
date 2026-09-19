from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import (
    admin,
    auth,
    calculations,
    case,
    contours,
    plots,
    projects,
    registry,
    summary,
    watchlist,
)

app = FastAPI(title="ForestProof API", version="0.1.0")

# Список источников задаётся окружением (CORS_ORIGINS). Звёздочка,
# стоявшая здесь «на время хакатона», означала, что любой сайт может
# послать запрос к API от имени открытой у человека вкладки.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(case.router)
app.include_router(contours.router)
app.include_router(summary.router)
app.include_router(projects.router)
app.include_router(calculations.router)
app.include_router(registry.router)
app.include_router(plots.router)
app.include_router(watchlist.router)

# Раздел 11 / NFR-01: превью и геометрия отдаются статикой с диска, без
# обращений во внешнюю сеть — демо обязано работать офлайн.
settings.data_root.mkdir(parents=True, exist_ok=True)
app.mount("/data", StaticFiles(directory=settings.data_root), name="data")


@app.get("/")
def root() -> dict:
    return {"service": "forestproof-api", "status": "ok"}


@app.get("/health")
def health() -> dict:
    """Используется Render health-check'ом (render.yaml, healthCheckPath)."""
    return {"status": "ok", "environment": settings.environment}
