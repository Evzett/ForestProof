from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

app = FastAPI(title="ForestProof API", version="0.1.0")

# На хакатоне фронт и API живут на разных хостах/портах — открываем CORS
# полностью; сузить при появлении реального домена фронта.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    return {"service": "forestproof-api", "status": "ok"}


@app.get("/health")
def health() -> dict:
    """Используется Render health-check'ом (render.yaml, healthCheckPath)."""
    return {"status": "ok", "environment": settings.environment}
