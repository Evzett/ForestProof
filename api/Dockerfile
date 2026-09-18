# ForestProof API — образ для локальной разработки и для развёртывания.
#
# ВАЖНО: контекст сборки — КОРЕНЬ репозитория, не папка api/.
# Расчётное ядро (forestproof_core), инструменты (tools) и описания набора
# (data) лежат в корне, и без них API не посчитает ничего: KAN-51 вызывает
# именно их, а не повторяет формулы у себя.
#
#     docker build -f api/Dockerfile -t forestproof-api .
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app:/repo

# Системные зависимости для psycopg2-binary/сборки — минимальный набор.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Зависимости сервиса и расчётного слоя ставятся отдельными слоями:
# requirements.txt в корне меняется реже, чем код API.
COPY requirements.txt /repo/requirements.txt
COPY api/requirements.txt /app/requirements.txt
RUN pip install -r /repo/requirements.txt -r /app/requirements.txt

# Расчётный слой — в /repo, он же в PYTHONPATH.
COPY forestproof_core /repo/forestproof_core
COPY tools /repo/tools

# Описания набора: маленькие CSV и GeoJSON, без них не собрать базовую
# линию и список участков. Растры в образ не кладутся — они монтируются
# томом или скачиваются в кэш (tools/fetch.py).
COPY data /repo/data

COPY api /app

EXPOSE 8000

# $PORT приходит от хостинга; локально (docker-compose) не задан — 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
