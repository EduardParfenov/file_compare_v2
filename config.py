"""Чтение конфигурации приложения из переменных окружения.

Все настройки (URL и ключ vLLM, имя модели, хост и порт FastAPI, CORS)
берутся из переменных окружения (файл .env). Если .env не найден при первом
запуске, используются безопасные значения по умолчанию (fallbacks), чтобы
приложение могло стартовать без предварительной настройки.

Переменные окружения загружаются из файла .env через библиотеку python-dotenv
при импорте модуля. Значения из существующих переменных окружения (os.environ)
имеют приоритет над значениями из .env.
"""

import os

from dotenv import load_dotenv

load_dotenv(override=True)


def _getenv(name: str, default: str) -> str:
    """Получить значение переменной окружения с fallback на default."""
    return os.getenv(name, default)


def _getenv_int(name: str, default: int) -> int:
    """Получить целочисленное значение переменной окружения с fallback."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    """Настройки приложения, загружаемые из окружения с дефолтными значениями."""

    # --- vLLM (Qwen3-VL-8B) ---
    VLLM_API_URL: str = _getenv("VLLM_API_URL", "http://localhost:8000/v1")
    VLLM_MODEL_NAME: str = _getenv("VLLM_MODEL_NAME", "qwen3-vl-8b")
    VLLM_API_KEY: str = _getenv("VLLM_API_KEY", "")

    # --- FastAPI / Uvicorn ---
    FASTAPI_HOST: str = _getenv("FASTAPI_HOST", "0.0.0.0")
    FASTAPI_PORT: int = _getenv_int("FASTAPI_PORT", 8000)

    # --- CORS ---
    CORS_ORIGINS: str = _getenv("CORS_ORIGINS", "*")


settings = Settings()
