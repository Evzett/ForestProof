# ForestProof · API (Р2)

FastAPI + SQLAlchemy + Alembic + Postgres. Хранит проекты, метаданные
реестра, заявленные показатели, наблюдения по годам, события нарушений и
расчёты (с аудит-полями). Контракт полей — `docs/04-kontrakty-dannyh.md`,
имена не менять.

## Запуск локально (Docker)

```bash
cd api
docker compose up --build
```

Поднимет Postgres и API на `http://localhost:8000`. Проверка:

```bash
curl http://localhost:8000/health
# {"status":"ok","environment":"development"}
```

## Применить схему БД

Контейнер `api` уже содержит alembic и код моделей. Из корня `api/`:

```bash
docker compose exec api alembic upgrade head
```

(или локально, если Postgres поднят отдельно: `alembic upgrade head`,
предварительно выставив `DATABASE_URL`, см. `.env.example`).

## Сборка "с нуля" (критерий приёмки А5.2)

```bash
docker compose build --no-cache
```

Должна пройти без кэша слоёв — если ловите ошибку, чаще всего дело в
`requirements.txt` (версия пакета снята с PyPI) — тогда просто убрать
жёсткую версию у проблемного пакета.

## Структура

```
app/
  main.py        FastAPI-приложение, /, /health
  config.py      настройки (DATABASE_URL и т.п.)
  database.py    engine, Session, Base
  models.py      ORM-модели — вся схема БД, с аудит-полями (раздел 8 контракта)
migrations/       Alembic; migrations/versions/0001_initial_schema.py — начальная схема
Dockerfile
docker-compose.yml
render.yaml       (в корне репозитория) — деплой на Render
```

## Деплой на Render (пустой hello world, критерий А5.1)

1. Запушить эту ветку/репозиторий на GitHub (репозиторий должен содержать
   `render.yaml` в корне и папку `api/` рядом с `app/`).
2. На [render.com](https://render.com) → **New +** → **Blueprint**.
3. Выбрать репозиторий `ForestProof` — Render сам прочитает `render.yaml`
   и предложит создать `forestproof-api` (веб-сервис на Docker) и
   `forestproof-db` (Postgres). Подтвердить.
4. После деплоя открыть выданный Render URL вида
   `https://forestproof-api-xxxx.onrender.com/health` — должен вернуть
   `{"status":"ok",...}`. Эту ссылку — в комментарий к задаче А5.
5. Применить миграции на прод-базе один раз через Render Shell
   (вкладка **Shell** у сервиса `forestproof-api`):
   ```bash
   alembic upgrade head
   ```

Бесплатный план Render засыпает без трафика и поднимается ~30–60 сек на
первый запрос — на демо это стоит учитывать (можно держать вкладку с
`/health` открытой перед защитой).
