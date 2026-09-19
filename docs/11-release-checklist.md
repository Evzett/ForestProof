# Чек-лист финальной сборки

## Автоматическая проверка

```bash
python -m pytest tests -q
npm --prefix app ci
npm --prefix app run build
npm --prefix app run lint
python tools/build_provenance_manifest.py
git diff --exit-code data/provenance_manifest.json
```

Пропущенные raster-интеграционные тесты допускаются только на машине без архива организатора и внешнего кэша. На демонстрационном сервере они должны выполняться, а не пропускаться.

## Запуск production-сборки

```bash
cp .env.production.example .env
docker compose -f docker-compose.production.yml up --build -d
docker compose -f docker-compose.production.yml exec api python -m app.seed_users
curl http://localhost/healthz
curl http://localhost/api/areas
curl http://localhost/api/provenance
```

## Сквозной сценарий перед защитой

1. Открыть каталог без входа и показать 4 исходных и 8 производных участков.
2. Открыть `RU_MORDOVIA_03`, период 2020–2022, карту события и снимки до/после.
3. Показать знак E, границы L/U, базовую линию, причину `Q = 0` и источники.
4. Войти как аналитик.
5. Выбрать готовый пример контура, период 2020–2022 и запустить расчёт.
6. Проверить сохранение контура, журнала, хеша входа и PDF.
7. Отключить внешний интернет и повторно открыть сохранённый результат.
8. Скачать JSON/PDF и сопоставить ключевые числа с экраном.

## Стоп-условия

Сборка не сдаётся, если исправления существуют только отдельным ZIP, production URL недоступен, пример контура не считается, манифест не соответствует `case-data.json` или обязательные raster-тесты не были прогнаны на сервере с данными.
