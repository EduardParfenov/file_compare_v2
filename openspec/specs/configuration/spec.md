# Configuration Specification

## Purpose

Позволяет приложению загружать переменные окружения из файла `.env` через `python-dotenv`, чтобы настройки (URL vLLM, модель, хост, порт, CORS) подхватывались из `.env` без необходимости экспортировать их в оболочку перед запуском.

## Requirements

### Requirement: Загрузка переменных окружения из файла .env

Система SHALL загружать переменные окружения из файла `.env` в корне проекта через библиотеку `python-dotenv` при старте приложения, чтобы значения из `.env` были доступны через `os.getenv()` в `config.settings`.

#### Scenario: Переменные из .env переопределяют дефолты

- **WHEN** файл `.env` существует в корне проекта и содержит `VLLM_API_URL=http://custom:9000/v1`
- **THEN** `config.settings.VLLM_API_URL` возвращает `"http://custom:9000/v1"` вместо дефолтного `"http://localhost:8000/v1"`

#### Scenario: Дефолтные значения применяются, когда .env отсутствует

- **WHEN** файл `.env` отсутствует и переменные окружения не заданы в оболочке
- **THEN** `config.settings.VLLM_API_URL` возвращает `"http://localhost:8000/v1"` (дефолтное значение)

#### Scenario: Переменные окружения из оболочки приоритетнее .env

- **WHEN** файл `.env` содержит `VLLM_API_URL=http://from-dotenv:9000/v1`, а в оболочке экспортировано `VLLM_API_URL=http://from-shell:9000/v1`
- **THEN** `config.settings.VLLM_API_URL` возвращает `"http://from-shell:9000/v1"` (значение из оболочки приоритетнее)
