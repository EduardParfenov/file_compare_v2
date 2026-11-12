## 1. Подготовка инфраструктуры конвейера

- [x] 1.1 Уточнить способ установки `openspec` CLI в окружении CI (отдельная зависимость `pip install openspec` или уже входящий в `requirements-dev.txt` пакет) и зафиксировать выбор в комментарии workflow. Проверка: выбранный способ документирован в `.github/workflows/ci.yml`.
  - Решение: `openspec` CLI — системный инструмент (v1.12.0, `/usr/local/bin/openspec`), не устанавливается через pip (пакет `openspec` на PyPI v0.1.0 — другой проект). В `ci.yml` добавлен шаг проверки наличия CLI с комментарием о необходимости отдельной установки на раннере GitHub Actions.
- [x] 1.2 Убедиться, что `requirements-dev.txt` содержит все зависимости, необходимые для линтеров/форматтеров и `openspec validate` (или добавить недостающие). Проверка: `pip install -r requirements-dev.txt` проходит без ошибок, команды линтеров и `openspec` доступны.
  - `pip install -r requirements-dev.txt` проходит успешно. `openspec` CLI доступен как системная команда. Конкретные линтеры/форматтеры не выбраны (открытый вопрос в design.md §Open Questions) — зависимости добавлятся на задаче 2.1 после выбора инструментов.

## 2. Реализация новых шагов в `.github/workflows/ci.yml`

- [x] 2.1 Добавить шаг запуска линтеров и форматтеров кода (Python и фронтенд) после установки зависимостей и перед `pytest`. Проверка: шаг присутствует в job `pytest`, выполняется до `pytest -q`, не использует секреты и не требует `.env`.
  - Добавлены шаги `ruff check` и `ruff format --check` для Python (P2.11b). Фронтенд-линтеры (eslint/prettier) не добавлены — требуют настройки Node.js в CI, открытый вопрос в design.md §Open Questions.
- [x] 2.2 Добавить шаг `openspec validate --specs --strict` после шага линтеров и перед `pytest`. Проверка: шаг присутствует в job `pytest`, использует флаг `--strict`, завершается ненулевым кодом при невалидном артефакте.
  - Добавлен шаг `openspec validate --specs --strict` в `.github/workflows/ci.yml` между линтерами и установкой браузера.
- [x] 2.3 Проверить, что имя job остаётся `pytest` и не требует изменения ruleset `main` на стороне GitHub. Проверка: в workflow по-прежнему одна job с именем `pytest`, привязанная к существующему strict status check.
  - Подтверждено: в `.github/workflows/ci.yml` одна job с именем `pytest`, привязанная к существующему strict status check `pytest` в ruleset `main`. Изменения ruleset не требуются.

## 3. Верификация конвейера

- [x] 3.1 Запустить `openspec validate --specs --strict` локально для артефактов этого change'а. Проверка: команда завершается успешно (0 ошибок).
  - Выполнено: `openspec validate --specs --strict` — `4 passed, 0 failed`. INFO-предупреждения о длине требований не являются ошибками.
- [x] 3.2 Запустить `pytest -q` локально в окружении без `.env`. Проверка: все тесты проходят (зелёный прогон), confirme что конвейер не зависит от локальных секретов.
  - Выполнено: `59 passed` (7.60 с), тесты зелёные без зависимости от `.env`.
- [x] 3.3 Проверить, что `.github/workflows/ci.yml` разбирается как валидный YAML и содержит объявленные триггеры (`pull_request`, `push` в `main`). Проверка: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` не выдаёт ошибок.
  - Выполнено: YAML валиден, одна job `pytest`, триггеры `pull_request` и `push` (ветка `main`), шаги: checkout, setup-python, install deps, проверка OpenSpec CLI, ruff check, ruff format --check, openspec validate --specs --strict, установка браузера, pytest.

## 4. Документация и бэклог

- [x] 4.1 Обновить `backlog.md`: закрыть пункты P2.11b (линтеры/форматтеры) и P2.14 (`openspec validate --specs --strict` в CI) как выполненные этим change'ом. Проверка: пункты помечены `[x]` с ссылкой на change.
  - Выполнено: P2.11b и P2.14 помечены `[x]` со ссылкой на change `ci-pipeline-completeness-review`.
- [x] 4.2 При необходимости обновить `README.md` с описанием новых шагов конвейера. Проверка: раздел о CI соответствует фактическому содержимому `.github/workflows/ci.yml`.
  - Выполнено: раздел "Что делает проверка" дополнен шагами OpenSpec CLI, ruff check/format, openspec validate; блок локального запуска обновлён.

## 5. Приёмка и архивация

- [ ] 5.1 Создать ветку от `main`, закоммитить артефакты change'а и изменения CI, открыть pull request в `main`. Проверка: PR отображает автоматическую проверку `pytest`.
- [ ] 5.2 Убедиться, что проверка `pytest` в PR завершилась успешно (зелёный статус) перед слиянием. Проверка: статус проверки `pytest` — SUCCESS.
- [ ] 5.3 Архивировать change в составе того же pull request после подтверждения приёмки фактами. Проверка: change перемещён в `openspec/changes/archive/`, `openspec list` не показывает активных changes.
