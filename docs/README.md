# Документы ForestProof

## Источники истины

Для сдачи и защиты применяются, в порядке старшинства:

1. **Официальная постановка организатора.**
2. [`06-kejs-pereorientaciya.md`](06-kejs-pereorientaciya.md) — требования, формулы и пользовательский сценарий.
3. [`10-research-report.md`](10-research-report.md) — исследовательский отчёт по условиям кейса.
4. [`13-executive-summary.md`](13-executive-summary.md) — тот же отчёт кратко: путь команды, ключевые числа, выводы, ограничения.
5. [`12-arhitektura.md`](12-arhitektura.md) — архитектура: слои, путь данных, роли, обоснование решений.
6. [`09-pitch-10-slajdov.md`](09-pitch-10-slajdov.md) — сценарий презентации.
7. Корневой [`../README.md`](../README.md) — запуск, воспроизведение, развёртывание.
8. `../data/provenance_manifest.json` — машинный манифест происхождения опубликованных результатов.

## Отчёт в вёрстке

[`otchet/`](otchet/) — тот же исследовательский отчёт в `.docx` и `.pdf`,
с рисунками и формулами:

* `ForestProof-issledovatelskiy-otchet.docx` / `.pdf` — полная версия;
* `ForestProof-executive-summary.docx` — краткая.

Текстовая версия краткой — [`13-executive-summary.md`](13-executive-summary.md);
в репозитории её удобнее читать и она не расходится с кодом молча.

## Прочее

| Документ | О чём |
|---|---|
| [`04-kontrakty-dannyh.md`](04-kontrakty-dannyh.md) | контракты данных и имена полей |
| [`07-granicy-proekta.md`](07-granicy-proekta.md) | границы: что заявляем и чего не заявляем |
| [`07-issledovanie-skrining-ustojchivosti.md`](07-issledovanie-skrining-ustojchivosti.md) | скрининг устойчивости |
| [`08-obuchenie-modeli-ustojchivosti.md`](08-obuchenie-modeli-ustojchivosti.md) | обучение модели устойчивости |
| [`11-release-checklist.md`](11-release-checklist.md) | чек-лист выпуска |

## Архив

Документы `00`–`05` описывают раннюю концепцию до получения окончательной
постановки. Они сохранены как история проектирования и **не задают
поведение сдаваемого решения**. При расхождении применяются документы из
списка источников истины.
