## 1. Подготовка ветки и базовых фактов

- [ ] 1.1 Создать ветку `docs/align-agents-md-with-project-reality` от `main` (только после явного разрешения пользователя) и убедиться, что активна именно она: `git branch --show-current` выводит `docs/align-agents-md-with-project-reality`
- [ ] 1.2 Зафиксировать базовые факты до правок: вывод `pytest --collect-only -q` (фактическое число тестов), `ruff check`, `ruff format --check`, `openspec validate --specs` — факты сохраняются в тексте pull request как точка отсчёта

## 2. Правка AGENTS.md — устранение фактических ошибок

- [x] 2.1 §3 «Структура проекта»: удалить упоминание несуществующего `services/ai_context.py`, добавить фактические элементы репозитория (`services/__init__.py`, `pytest.ini`, `ruff.toml`, `.github/workflows/ci.yml`, `backlog.md`, `openspec/`) — проверка: каждый путь в дереве существует в репозитории (тест из §5)
- [x] 2.2 §5 «Линтер и форматтер»: заменить «конфиг в `pyproject.toml`» на фактический `ruff.toml` — проверка: файл `ruff.toml` существует, упоминаний `pyproject.toml` в `AGENTS.md` не осталось
- [x] 2.3 §5 «Типизация»: заменить рекомендацию `from typing import Optional, List, Dict` на стиль проекта (`from __future__ import annotations` + встроенные generic-типы `list[str]`, `dict[str, str]`, `X | None`) — проверка: рекомендация соответствует коду `config.py`, `main.py`, `services/*`
- [x] 2.4 §5 «Ограничения»: сформулировать лимиты (≤40 строк, ≤4 вложенности, ≤5 аргументов) как норму для нового и изменяемого кода с переходным периодом для существующего, со ссылкой на `backlog.md` — проверка: в `AGENTS.md` нет утверждения, что текущий кодек уже соответствует этим лимитам
- [x] 2.5 §6 «Примеры правильного кода»: привести пример к фактическому API (`extract_text_and_coords(pdf_path: str) -> dict`, `PdfHandlerError`, без `TextBlock`), в примере обработки ошибок использовать реальный `vllm_client.stream_analysis(prompt)` — проверка: примеры компилируются по смыслу и не содержат имён, отсутствующих в коде
- [x] 2.6 §7 «Частые ошибки агента»: заменить пример `settings.output_dir` (такого поля в `Settings` нет) на реальный способ построения путей — проверка: в `AGENTS.md` нет упоминаний `output_dir`
- [x] 2.7 §11 «Definition of Done»: уточнить контракт `GET /api/v1/health` — `status: "ok"` вместе с именем модели и признаком настройки подключения — проверка: формулировка соответствует ответу `main.health()` (`status`, `vllm_model`, `vllm_configured`)
- [x] 2.8 §14 «Ключевые API»: назвать фактические функции (`VllmClient.stream_analysis()`, `VllmClient.stream_analysis_with_image()`, `compute_diff()`, `compute_diff_with_coords()`, `extract_text_and_coords()`, `render_page_to_png()`), удалить `stream_chat()` и `services/ai_context.py`, уточнить роль `httpx` — проверка: все перечисленные имена найдены в исходниках (тест из §5)
- [x] 2.9 §4.3 «Тестовые данные»: отметить, что каталога `tests/fixtures/` в проекте нет и тесты используют синтетические PDF во временном каталоге — проверка: каталога `tests/fixtures/` действительно нет
- [x] 2.10 Сплошная проверка остаточных несоответствий: поиск по `AGENTS.md` упоминаний `stream_chat`, `ai_context`, `pyproject`, `output_dir`, `TextBlock`, `List`, `Dict` — проверка: поиск не находит ни одного вхождения

## 3. Правка README.md — синхронизация с фактическим состоянием

- [x] 3.1 Раздел «Структура проекта»: дополнить фактическими элементами (`tests/`, `pytest.ini`, `ruff.toml`, `openspec/`, `backlog.md`, `.github/workflows/ci.yml`) — проверка: структура в `README.md` совпадает с деревом §3 `AGENTS.md`
- [x] 3.2 Убрать конкретное число тестов (59) в двух местах, заменить формулировкой «полный набор тестов» и указать способ получить фактическое число (`pytest --collect-only -q`) — проверка: в `README.md` нет числа тестов, а команда получения присутствует
- [x] 3.3 Описание шага CI «Валидирует артефакты OpenSpec»: привести к фактической команде `openspec validate --specs` (без `--strict`) с пояснением причины отклонения и ссылкой на `backlog.md` P2.13 — проверка: описание совпадает с `.github/workflows/ci.yml`
- [x] 3.4 Формулировка о папке `input/`: согласовать с `AGENTS.md` — папка приватная, игнорируется Git, агент не читает её без явного разрешения; содержимое не описывается — проверка: обе формулировки не противоречат друг другу
- [x] 3.5 Сверить раздел «Правила ветвления и Pull-Request» с `AGENTS.md` §9 (запрет прямого коммита в `main`, обязательный PR, удаление ветки после слияния) и устранить расхождения в формулировках — проверка: оба документа утверждают одно и то же

## 4. Спецификация новой capability agent-governance

- [x] 4.1 Проверить дельту `specs/agent-governance/spec.md` на соответствие схеме: `openspec validate align-agents-md-with-project-reality --type change --strict` — проверка: валидация change'а проходит без замечаний
- [x] 4.2 Сверить каждое требование дельты с текстом новой редакции `AGENTS.md`: ни одно требование не противоречит правилам проекта, каждое имеет минимум один сценарий — проверка: сплошная сверка разделов §4, §5, §8, §10, §11 с требованиями дельты

## 5. Техническая фиксация достоверности документации

- [x] 5.1 Создать `tests/test_docs_consistency.py`: проверка существования файлов, упомянутых в `AGENTS.md` (упоминания вида `services/<имя>.py` и явный список служебных файлов), пути вычисляются от корня репозитория — проверка: `pytest tests/test_docs_consistency.py` проходит
- [x] 5.2 В том же файле: проверка наличия в исходниках имён публичного API, названных в §14 `AGENTS.md` (`stream_analysis`, `stream_analysis_with_image`, `compute_diff`, `compute_diff_with_coords`, `extract_text_and_coords`, `render_page_to_png`, `read_environment`, `from_env`, `vllm_configured`) — проверка: тест падает при временном удалении одного из имён из исходника и проходит после отката правки
- [x] 5.3 Не добавлять в тест проверок, зависящих от содержимого приватных папок (`input/`) и файла `.env` — проверка: в тесте нет обращений к `input/` и `.env` (проверяется поиском по файлу теста)

## 6. Обновление backlog.md

- [x] 6.1 Дополнить пункт P2.13 результатами текущего change'а: перечислены устранённые расхождения (несуществующие `services/ai_context.py`, `VllmClient.stream_chat()`, конфиг `pyproject.toml`, `settings.output_dir`, `TextBlock`, устаревшее число тестов в `README.md`, неверное описание команды валидации OpenSpec в CI) — проверка: пункт P2.13 содержит перечень устранённых расхождений
- [x] 6.2 Добавить пункт долга по лимитам длины функций с указанием конкретных нарушений (`pdf_handler.extract_text_and_coords` — 135 строк, `diff_engine.compute_diff` — 116, `main.compare` — 55, `vllm_client.stream_analysis_with_image` — 53, `vllm_client.stream_analysis` — 41) — проверка: пункт создан, задачи в нём не отмечены выполненными
- [x] 6.3 Зафиксировать в P2.13 (или рядом) известное расхождение: спецификация `continuous-integration` требует `openspec validate --specs --strict`, CI выполняет без `--strict` — проверка: расхождение явно записано как открытое

## 7. Приёмка и оформление pull request

- [x] 7.1 Локальная проверка полного набора: `ruff check`, `ruff format --check`, `pytest`, `openspec validate --specs` — проверка: все команды завершаются успешно, вывод приложен к pull request
- [ ] 7.2 Создать pull request в `main` из `docs/align-agents-md-with-project-reality` (только после явного разрешения пользователя) — проверка: получен идентификатор pull request, проверки запустились
- [ ] 7.3 Подтвердить приёмку фактами GitHub (идентификатор pull request и зелёный статус проверок), затем закрыть задачи приёмки в `tasks.md` — проверка: факт приёмки зафиксирован в чек-листе до архивирования
- [ ] 7.4 Заархивировать change `align-agents-md-with-project-reality` в том же pull request — проверка: change перенесён в `openspec/changes/archive/`, новая capability появилась в `openspec/specs/agent-governance/spec.md`
- [ ] 7.5 Слить pull request на GitHub и удалить рабочую ветку локально и на удалённом сервере — проверка: `main` содержит изменения, ветка `docs/align-agents-md-with-project-reality` отсутствует локально и на сервере
