from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import calculations, case, plots, projects, registry, summary, watchlist

app = FastAPI(title="ForestProof API", version="0.1.0")

# На хакатоне фронт и API живут на разных хостах/портах — открываем CORS
# полностью; сузить при появлении реального домена фронта.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(case.router)
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
