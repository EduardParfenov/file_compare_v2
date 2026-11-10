"""Тесты для модуля конфигурации `config.py`.

Проверяются:
- дефолтные значения `Settings` при отсутствии переменных окружения;
- загрузка значений из переменных окружения (с переопределением дефолтов);
- корректный тип порта (int).
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
