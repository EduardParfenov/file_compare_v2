"""Тесты для модуля конфигурации `config.py`.

Проверяются:
- дефолтные значения `Settings` при отсутствии переменных окружения;
- загрузка значений из переменных окружения (с переопределением дефолтов);
- корректный тип порта (int);
- загрузка значений из файла .env через python-dotenv.
"""

from importlib import reload

import config


def test_defaults(monkeypatch):
    """Дефолтные значения применяются, когда переменные окружения не заданы."""
    for key in (
        "VLLM_API_URL",
        "VLLM_MODEL_NAME",
        "VLLM_API_KEY",
        "FASTAPI_HOST",
        "FASTAPI_PORT",
        "CORS_ORIGINS",
    ):
        monkeypatch.delenv(key, raising=False)
    reload(config)
    settings = config.settings
    assert settings.VLLM_API_URL == "http://localhost:8000/v1"
    assert settings.VLLM_MODEL_NAME == "qwen3-vl-8b"
    assert settings.VLLM_API_KEY == ""
    assert settings.FASTAPI_HOST == "0.0.0.0"
    assert settings.FASTAPI_PORT == 8000
    assert settings.CORS_ORIGINS == "*"


def test_env_loading(monkeypatch):
    """Значения из переменных окружения переопределяют дефолты."""
    monkeypatch.setenv("VLLM_API_URL", "http://test:9000/v1")
    monkeypatch.setenv("VLLM_MODEL_NAME", "test-model")
    monkeypatch.setenv("VLLM_API_KEY", "test-key")
    monkeypatch.setenv("FASTAPI_HOST", "127.0.0.1")
    monkeypatch.setenv("FASTAPI_PORT", "9000")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost")
    reload(config)
    settings = config.settings
    assert settings.VLLM_API_URL == "http://test:9000/v1"
    assert settings.VLLM_MODEL_NAME == "test-model"
    assert settings.VLLM_API_KEY == "test-key"
    assert settings.FASTAPI_HOST == "127.0.0.1"
    assert settings.FASTAPI_PORT == 9000
    assert isinstance(settings.FASTAPI_PORT, int)
    assert settings.CORS_ORIGINS == "http://localhost"


def test_dotenv_file_loaded(monkeypatch, tmp_path):
    """Значения из файла .env загружаются через python-dotenv."""
    from dotenv import load_dotenv

    # Создаём временный .env файл
    env_file = tmp_path / ".env"
    env_file.write_text(
        "VLLM_API_URL=http://dotenv:9000/v1\n"
        "VLLM_MODEL_NAME=dotenv-model\n"
        "VLLM_API_KEY=dotenv-key\n"
        "FASTAPI_HOST=127.0.0.1\n"
        "FASTAPI_PORT=9000\n"
        "CORS_ORIGINS=http://dotenv.local\n"
    )
    # Удаляем переменные из окружения полностью
    for key in (
        "VLLM_API_URL",
        "VLLM_MODEL_NAME",
        "VLLM_API_KEY",
        "FASTAPI_HOST",
        "FASTAPI_PORT",
        "CORS_ORIGINS",
    ):
        monkeypatch.delenv(key, raising=False)
        config.os.environ.pop(key, None)
    # Переключаемся в директорию с .env
    monkeypatch.chdir(tmp_path)
    reload(config)
    settings = config.settings
    assert settings.VLLM_API_URL == "http://dotenv:9000/v1"
    assert settings.VLLM_MODEL_NAME == "dotenv-model"
    assert settings.VLLM_API_KEY == "dotenv-key"
    assert settings.FASTAPI_HOST == "127.0.0.1"
    assert settings.FASTAPI_PORT == 9000
    assert isinstance(settings.FASTAPI_PORT, int)
    assert settings.CORS_ORIGINS == "http://dotenv.local"


def test_dotenv_override_shell(monkeypatch, tmp_path):
    """Значения из .env имеют приоритет над переменными окружения оболочки."""
    from dotenv import load_dotenv

    # Создаём .env с одними значениями
    env_file = tmp_path / ".env"
    env_file.write_text(
        "VLLM_API_URL=http://from-dotenv:9000/v1\n"
    )
    # Устанавливаем другое значение в os.environ
    monkeypatch.setenv("VLLM_API_URL", "http://from-shell:9000/v1")
    monkeypatch.chdir(tmp_path)
    reload(config)
    settings = config.settings
    # Значение из .env имеет приоритет (load_dotenv с override=True)
    assert settings.VLLM_API_URL == "http://from-dotenv:9000/v1"
