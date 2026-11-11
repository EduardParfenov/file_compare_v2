## Why

Файл `.env` с реальными секретами и настройками не загружается приложением. В `config.py` используется только `os.getenv()`, который читает значения из `os.environ`, но не из файла `.env`. Переменные окружения подхватываются только если они уже экспортированы в оболочку перед запуском приложения. Сценарий из `AGENTS.md` и `README.md` (`cp .env.example .env`) не работает — `.env` игнорируется.

## What Changes

- В `services/config.py`: добавить импорт `load_dotenv` из `python-dotenv` и вызвать `load_dotenv()` при импорте модуля, чтобы переменные из файла `.env` подхватывались `os.getenv()`.
- Добавить тест в `tests/test_config.py`, проверяющий, что значения из `.env` загружаются и переопределяют дефолты.

## Capabilities

### New Capabilities

- `configuration`: загрузка переменных окружения из файла `.env` через `python-dotenv`.

### Modified Capabilities

— (нет)

## Impact

- `services/config.py` — основной файл изменения (добавлен `load_dotenv()`).
- `tests/test_config.py` — новый тест загрузки `.env`.
- `services/diff_engine.py` — без изменений.
- `main.py` — без изменений (использует `config.settings`, который теперь загружает `.env`).
- `static/` — без изменений.
