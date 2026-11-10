## 1. Подготовка окружения и зависимостей

- [x] 1.1 Добавить `pytest` в `requirements.txt` с точной версией и проверить установку в `.venv/` — подтвердить, что `pip install -r requirements.txt` завершается без ошибок и `pytest` импортируется
- [x] 1.2 Создать папку `tests/` в корне проекта — подтвердить, что папка `tests/` существует

## 2. Конфигурация и фикстуры тестов

- [x] 2.1 Создать `tests/conftest.py` с фикстурой TestClient FastAPI и фикстурами временных тестовых PDF-файлов — подтвердить, что `conftest.py` импортируется и TestClient создается без ошибок
- [x] 2.2 Написать тесты для `config.py` (дефолтные значения `Settings`, загрузка из переменных окружения) — подтвердить, что `pytest tests/test_config.py` проходит

## 3. Тесты движка diff

- [x] 3.1 Написать тесты для `services/diff_engine.py` (`compute_diff`: EQUAL/INSERT/DELETE делятся на левую `EQUAL`+`DELETE` и правую `EQUAL`+`INSERT` панели; INSERT не попадает влево, DELETE не попадает вправо) — подтвердить, что `pytest tests/test_diff_engine.py` проходит
- [x] 3.2 Написать тесты для `compute_diff_with_coords` (поля `coords_left`/`coords_right` присутствуют в результате) — подтвердить, что тесты проходят

## 4. Тесты обработки PDF

- [x] 4.1 Написать тесты для `services/pdf_handler.py` (`extract_text_and_coords`: возвращает плоский текст и координаты слов/блоков X, Y, ширина, высота) — подтвердить, что `pytest tests/test_pdf_handler.py` проходит
- [x] 4.2 Написать тест поведения при отсутствии текстового слоя в PDF (`PdfHandlerError` или пустой результат без ложных совпадений) — подтвердить, что тест проходит

## 5. Тесты роутов API

- [x] 5.1 Написать тесты для `GET /api/v1/health` (возвращает `status: ok`, `vllm_api_url`, `vllm_model`) — подтвердить, что тест проходит
- [x] 5.2 Написать тесты для `POST /api/v1/compare` с двумя тестовыми PDF (возвращает `left_panel`/`right_panel`, координаты, `summary`) — подтвердить, что тест проходит
- [x] 5.3 Написать тесты для ИИ-маршрутов (`/api/v1/analyze`, `/api/v1/ai-report-page`) с мокированием vLLM (возврат 502 при недоступности vLLM, корректная работа при моке) — подтвердить, что тесты проходят

## 6. Финальная проверка

- [x] 6.1 Запустить весь набор `pytest` из `.venv/` и подтвердить, что все тесты проходят
- [x] 6.2 Подтвердить изоляцию тестов: запуск не зависит от пользовательских файлов в `input/` и от доступности внешнего vLLM endpoint
- [x] 6.3 Добавить правило в AGENTS.md: при любой правке кода нужно дописывать и проверять, что все тесты зелёные, перед созданием pull-request

## 7. Исправление бага загрузки файлов на фронтенде

- [x] 7.1 Найти причину: кнопки «Оригинал (PDF)» и «Новая версия (PDF)» не открывают выбор файла — ошибка `The requested module '/static/app.js' does not provide an export named 'initApp'`; `initApp` не экспортировался из `static/app.js`, поэтому инициализация фронтенда не выполнялась
- [x] 7.2 Исправить: добавить `export` к `function initApp` в `static/app.js` и убрать дублирующий вызов `initApp()` в конце файла
- [x] 7.3 Найти и исправить вторую ошибку в `comparePdfs`: параметры `fileA`/`fileB` перекрывают внешние константы; в блоке `finally` обращение `fileA.files.length` к `File`-объекту вызывало `TypeError: Cannot read properties of undefined (reading 'length')` — заменить на `document.getElementById("fileA").files.length` / `document.getElementById("fileB").files.length`, а `btnCompare` — на `document.getElementById("btnCompare")`
- [x] 7.4 Добавить фронтенд-тест `tests/test_frontend_upload.py` (Playwright): загрузка двух PDF → включение кнопки «Сравнить» → ответ 200 от `/api/v1/compare`, без JS-ошибок
- [x] 7.5 Запустить полный набор `pytest` — 27 тестов проходят, 0 JS-ошибок
