# Что я сделал и что нужно доделать руками — важно прочитать

## Почему руками, а не всё автоматически

Облачная песочница, в которой я работаю, в этой организации закрыта по
сети почти полностью: заблокирован реестр npm, заблокирован PyPI,
заблокирован render.com целиком, нет запущенного Docker-демона, а пуш в
`Evzett/ForestProof` отклоняется git-прокси («repository is not in this
session's authorized repository set»). Поэтому я не мог сам:
не запустить `npm install` для фронта, не собрать образ, не задеплоить на
Render, не запушить в репозиторий. Всё это я написал и проверил синтаксически
(`py_compile`, разбор YAML), но исполнить и подтвердить руками может только
локальная машина — у тебя это должно работать штатно.

## Что сделано (файлы в этом архиве)

- `api/` — FastAPI + SQLAlchemy + Alembic + Dockerfile + docker-compose.yml.
  Схема БД: `projects`, `project_registry`, `project_claims`, `observations`,
  `disturbance_events`, `calculations` (аудит-поля из раздела 8 контракта —
  `calc_id`, `project_id`, `calculated_at`, `methodology_version`,
  `algorithm_version`, `model_version`, `input_hash`, `observation_dates`,
  `datasets`, `parameters`, `result`).
- `render.yaml` — Blueprint для Render (веб-сервис + Postgres, healthcheck
  `/health`).
- `api/README.md` — команды запуска, миграций, деплоя.
- `QUESTIONS_FOR_R1.md` — вопросы по разделам 4–6 контракта.

## Что доделать руками, по порядку (~20–30 минут)

### 1. Разложить файлы в репозиторий

Распаковать архив в корень `ForestProof` так, чтобы получилось:

```
ForestProof/
  app/            (уже есть, фронт Р1)
  docs/           (уже есть)
  api/            (из архива)
  render.yaml     (из архива, в корень)
```

### 2. Проверить каркас фронта у себя (критерий А5.4)

```bash
cd ForestProof/app
npm install
npm run dev
```

Открыть `http://localhost:5173`. Если что-то не собирается — это и есть
"проблемы, озвученные до старта" из задачи; я не смог проверить это сам
(npm заблокирован в моей песочнице), так что первый реальный прогон — твой.

### 3. Собрать Docker с нуля (критерий А5.2)

```bash
cd ForestProof/api
docker compose build --no-cache
docker compose up
curl http://localhost:8000/health
```

### 4. Применить схему БД

```bash
docker compose exec api alembic upgrade head
```

### 5. Запушить в GitHub

```bash
cd ForestProof
git checkout -b feat/r2-env-and-db
git add api render.yaml
git commit -m "A5: окружение, схема БД с аудит-полями, Docker"
git push -u origin feat/r2-env-and-db
```

(если у тебя нет прав на пуш в `Evzett/ForestProof` — сделай fork и пушь
туда, либо попроси Р1 добавить тебя как collaborator).

### 6. Деплой на Render (критерий А5.1)

1. render.com → **New +** → **Blueprint** → выбрать репозиторий/ветку.
2. Render прочитает `render.yaml` и создаст `forestproof-api` + `forestproof-db`.
3. Дождаться деплоя, открыть `https://<имя-сервиса>.onrender.com/health`.
4. Ссылку — в комментарий к задаче А5.

### 7. Задать вопросы Р1 (критерий А5.5)

Текст готов в `QUESTIONS_FOR_R1.md` — можно просто вставить в чат.

## Если захочешь, чтобы я довёл руками через связку с твоим компьютером

Я могу подключиться к папке на твоём компьютере и класть файлы прямо
туда (без архива), но выполнять команды (`npm`, `docker`, `git push`) в
этой сессии я всё равно не могу — на твоём компьютере у меня нет доступа
к терминалу, только к файлам. Реальный браузер на твоём компьютере
(отдельный от этой песочницы) я использовать могу — если хочешь, я
пройду часть шагов в Render через него вживую, пока ты рядом для логина.
